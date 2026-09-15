from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.governance.domain import (
    GovernanceCheck,
    GovernanceDecisionType,
    GovernanceEvaluation,
    GovernanceStage,
)
from backend.governance.policy import CanonicalGovernancePolicy, DEFAULT_GOVERNANCE_POLICY
from backend.governance.repositories import GovernanceRepository
from backend.models import (
    AuditLogORM,
    BacktestRun,
    ModelRegistryORM,
    ModelRun,
    StrategyGovernanceDecisionORM,
    StrategyGovernanceRecordORM,
    User,
)
from backend.simulation.domain.account import AccountState
from backend.simulation.domain.cash import CashBalance
from backend.simulation.domain.corporate_actions import CorporateAction
from backend.simulation.domain.enums import (
    CorporateActionType,
    LedgerEntryType,
    OrderSide,
    SimulationMode,
    SimulationRunStatus,
    VerificationLevel,
)
from backend.simulation.domain.events import LedgerEntry
from backend.simulation.domain.fills import Fill
from backend.simulation.domain.identifiers import InstrumentId
from backend.simulation.domain.positions import Position
from backend.simulation.persistence.models import (
    SimulationAppliedCorporateActionORM,
    SimulationFillORM,
    SimulationLedgerEntryORM,
    SimulationOrderORM,
    SimulationPortfolioSnapshotORM,
    SimulationPositionSnapshotORM,
    SimulationReconciliationItemORM,
    SimulationReconciliationORM,
    SimulationRunORM,
)
from backend.simulation.persistence.serializers import to_primitive
from backend.simulation.services.manifest_service import sha256_value
from backend.simulation.services.reconciliation_service import ReconciliationService


class GovernanceError(ValueError):
    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(f"{code}: {message}" if message else code)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _manifest_hash(run: SimulationRunORM) -> str | None:
    return dict(run.manifest_json or {}).get("manifest_hash")


class StrategyGovernanceService:
    """Evidence-only strategy promotion; canonical source records are read-only."""

    def __init__(self, db: Session, *, policy: CanonicalGovernancePolicy = DEFAULT_GOVERNANCE_POLICY):
        self.db = db
        self.policy = policy
        self.repository = GovernanceRepository(db)

    def evaluate(
        self,
        *,
        baseline_run_id: str,
        target_stage: GovernanceStage | str,
        paper_run_id: str | None = None,
        reconciliation_id: str | None = None,
    ) -> GovernanceEvaluation:
        target = self._stage(target_stage)
        if target not in {GovernanceStage.STAGING, GovernanceStage.PROD}:
            raise GovernanceError("INVALID_STAGE_TRANSITION")
        baseline = self.db.get(SimulationRunORM, baseline_run_id)
        if baseline is None:
            raise GovernanceError("BASELINE_RUN_NOT_FOUND")
        record = self.repository.by_identity(baseline.strategy_key, baseline.strategy_hash)
        current = GovernanceStage(record.current_stage) if record else GovernanceStage.CANDIDATE
        checks = self._baseline_checks(baseline)
        paper = None
        reconciliation = None
        if target is GovernanceStage.PROD:
            checks.extend(self._transition_checks(record, baseline))
            paper, reconciliation, prod_checks = self._prod_checks(
                baseline, paper_run_id, reconciliation_id
            )
            checks.extend(prod_checks)
        evidence = self._evidence_bundle(baseline, paper, reconciliation)
        evidence_hash = sha256_value(evidence)
        return GovernanceEvaluation(
            target,
            current,
            not any(check.blocking and not check.passed for check in checks),
            tuple(checks),
            evidence,
            evidence_hash,
        )

    def promote(
        self,
        *,
        baseline_run_id: str,
        target_stage: GovernanceStage | str,
        actor_user_id: str,
        reason: str,
        paper_run_id: str | None = None,
        reconciliation_id: str | None = None,
        registry_name: str | None = None,
        legacy_model_run_id: str | None = None,
    ) -> dict[str, Any]:
        actor = self._require_actor(actor_user_id)
        reason = reason.strip()
        if not reason:
            raise GovernanceError("PROMOTION_REASON_REQUIRED")
        evaluation = self.evaluate(
            baseline_run_id=baseline_run_id,
            target_stage=target_stage,
            paper_run_id=paper_run_id,
            reconciliation_id=reconciliation_id,
        )
        failure = next(
            (check for check in evaluation.checks if check.blocking and not check.passed),
            None,
        )
        if failure:
            raise GovernanceError(failure.failure_code or failure.code, failure.detail)
        baseline = self.db.get(SimulationRunORM, baseline_run_id)
        assert baseline is not None
        record = self.repository.by_identity(baseline.strategy_key, baseline.strategy_hash)
        from_stage = GovernanceStage(record.current_stage) if record else GovernanceStage.CANDIDATE
        if record is not None and from_stage is evaluation.target_stage:
            for prior in reversed(self.repository.history(record.id)):
                if (
                    prior.decision_type == GovernanceDecisionType.PROMOTE.value
                    and prior.to_stage == evaluation.target_stage.value
                    and prior.evidence_hash == evaluation.evidence_hash
                    and prior.policy_version == self.policy.version
                    and prior.actor_user_id == actor
                    and prior.reason == reason
                ):
                    return self._decision_dict(prior, record)
        request_hash = sha256_value({
            "strategy_key": baseline.strategy_key,
            "strategy_hash": baseline.strategy_hash,
            "from_stage": from_stage.value,
            "target_stage": evaluation.target_stage.value,
            "evidence_hash": evaluation.evidence_hash,
            "policy_version": self.policy.version,
            "actor_user_id": actor,
            "reason": reason,
        })
        existing = self.repository.decision_by_request(request_hash)
        if existing is not None:
            return self._decision_dict(existing, self.repository.get(existing.governance_record_id))
        if from_stage is evaluation.target_stage:
            raise GovernanceError("INVALID_STAGE_TRANSITION", "strategy is already at target stage")
        if record is None:
            record = StrategyGovernanceRecordORM(
                id=f"gov_{uuid4().hex}",
                strategy_key=baseline.strategy_key,
                strategy_hash=baseline.strategy_hash,
                current_stage=GovernanceStage.CANDIDATE.value,
                policy_version=self.policy.version,
                created_at=_now(),
                updated_at=_now(),
            )
            self.db.add(record)
            self.db.flush()
        decision = StrategyGovernanceDecisionORM(
            id=f"gdec_{uuid4().hex}",
            governance_record_id=record.id,
            decision_type=GovernanceDecisionType.PROMOTE.value,
            from_stage=from_stage.value,
            to_stage=evaluation.target_stage.value,
            baseline_run_id=baseline.id,
            paper_run_id=paper_run_id,
            reconciliation_id=reconciliation_id,
            policy_version=self.policy.version,
            policy_snapshot_json=to_primitive(self.policy.snapshot()),
            evidence_hash=evaluation.evidence_hash,
            evidence_json=to_primitive(evaluation.evidence),
            checks_json=to_primitive([check.as_dict() for check in evaluation.checks]),
            reason=reason,
            actor_user_id=actor,
            request_hash=request_hash,
            created_at=_now(),
        )
        self.db.add(decision)
        record.current_stage = evaluation.target_stage.value
        record.baseline_run_id = baseline.id
        record.latest_paper_run_id = paper_run_id
        record.latest_reconciliation_id = reconciliation_id
        record.latest_evidence_hash = evaluation.evidence_hash
        record.policy_version = self.policy.version
        record.updated_at = decision.created_at
        record.revoked_at = None
        self.db.add(self._audit("governance_strategy_promoted", record, decision, actor))
        self.db.flush()
        self._project_registry(
            record,
            decision,
            registry_name or baseline.strategy_key,
            legacy_model_run_id,
            baseline.id,
        )
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = self.repository.decision_by_request(request_hash)
            if existing is not None:
                return self._decision_dict(existing, self.repository.get(existing.governance_record_id))
            raise
        except Exception:
            self.db.rollback()
            raise
        return self._decision_dict(decision, record)

    def revoke(self, record_id: str, *, actor_user_id: str, reason: str) -> dict[str, Any]:
        actor = self._require_actor(actor_user_id)
        reason = reason.strip()
        if not reason:
            raise GovernanceError("PROMOTION_REASON_REQUIRED")
        record = self.repository.get(record_id)
        if record is None:
            raise GovernanceError("GOVERNANCE_RECORD_NOT_FOUND")
        if record.current_stage == GovernanceStage.REVOKED.value:
            raise GovernanceError("ALREADY_REVOKED")
        evidence = {
            "strategy": {"strategy_key": record.strategy_key, "strategy_hash": record.strategy_hash},
            "previous_evidence_hash": record.latest_evidence_hash,
            "policy": {"version": self.policy.version},
        }
        evidence_hash = sha256_value(evidence)
        request_hash = sha256_value({
            "record_id": record.id,
            "from_stage": record.current_stage,
            "target_stage": GovernanceStage.REVOKED.value,
            "evidence_hash": evidence_hash,
            "actor_user_id": actor,
            "reason": reason,
        })
        existing = self.repository.decision_by_request(request_hash)
        if existing is not None:
            return self._decision_dict(existing, record)
        created = _now()
        decision = StrategyGovernanceDecisionORM(
            id=f"gdec_{uuid4().hex}", governance_record_id=record.id,
            decision_type=GovernanceDecisionType.REVOKE.value,
            from_stage=record.current_stage, to_stage=GovernanceStage.REVOKED.value,
            baseline_run_id=record.baseline_run_id,
            paper_run_id=record.latest_paper_run_id,
            reconciliation_id=record.latest_reconciliation_id,
            policy_version=self.policy.version,
            policy_snapshot_json=to_primitive(self.policy.snapshot()),
            evidence_hash=evidence_hash, evidence_json=evidence,
            checks_json=[], reason=reason, actor_user_id=actor,
            request_hash=request_hash, created_at=created,
        )
        record.current_stage = GovernanceStage.REVOKED.value
        record.updated_at = created
        record.revoked_at = created
        record.latest_evidence_hash = evidence_hash
        self.db.add(decision)
        self.db.add(self._audit("governance_strategy_revoked", record, decision, actor))
        for projection in self.db.query(ModelRegistryORM).filter_by(governance_record_id=record.id).all():
            projection.stage = "revoked"
            projection.governance_decision_id = decision.id
            projection.evidence_hash = evidence_hash
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self._decision_dict(decision, record)

    def resolve_legacy_model_run(self, model_run_id: str) -> tuple[ModelRun, SimulationRunORM]:
        model_run = self.db.get(ModelRun, model_run_id)
        if model_run is None:
            raise GovernanceError("CANONICAL_EVIDENCE_REQUIRED", "legacy ModelRun not found")
        backtest = self.db.query(BacktestRun).filter_by(run_id=model_run.backtest_run_id).one_or_none()
        if backtest is None or not backtest.simulation_run_id:
            raise GovernanceError("CANONICAL_EVIDENCE_REQUIRED")
        simulation = self.db.get(SimulationRunORM, backtest.simulation_run_id)
        if simulation is None:
            raise GovernanceError("CANONICAL_EVIDENCE_REQUIRED")
        return model_run, simulation

    def get(self, record_id: str) -> dict[str, Any]:
        record = self.repository.get(record_id)
        if record is None:
            raise GovernanceError("GOVERNANCE_RECORD_NOT_FOUND")
        return self._record_dict(record)

    def history(self, record_id: str) -> list[dict[str, Any]]:
        if self.repository.get(record_id) is None:
            raise GovernanceError("GOVERNANCE_RECORD_NOT_FOUND")
        return [self._decision_dict(item) for item in self.repository.history(record_id)]

    def list(self, *, stage: str | None = None, strategy_key: str | None = None, offset: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        query = self.db.query(StrategyGovernanceRecordORM)
        if stage:
            query = query.filter_by(current_stage=self._stage(stage).value)
        if strategy_key:
            query = query.filter_by(strategy_key=strategy_key)
        rows = query.order_by(StrategyGovernanceRecordORM.updated_at.desc(), StrategyGovernanceRecordORM.id).offset(offset).limit(limit).all()
        return [self._record_dict(row) for row in rows]

    def _baseline_checks(self, baseline: SimulationRunORM) -> list[GovernanceCheck]:
        result = dict(baseline.result_json or {})
        data_quality = dict(result.get("data_quality") or {})
        persisted_reconciliation = dict(result.get("reconciliation") or {})
        checks = [
            self._check(
                "STRATEGY_IDENTITY_PRESENT",
                bool(baseline.strategy_key.strip() and baseline.strategy_hash.strip()),
                "STRATEGY_IDENTITY_MISMATCH",
                "exact strategy_key and strategy_hash required",
            ),
            self._check("BASELINE_BACKTEST", baseline.mode == SimulationMode.BACKTEST.value, "BASELINE_MODE_INVALID", baseline.mode),
            self._check("BASELINE_VERIFIED", baseline.verification_level == VerificationLevel.VERIFIED.value, "VERIFIED_BASELINE_REQUIRED", baseline.verification_level),
            self._check("BASELINE_DONE", baseline.status == SimulationRunStatus.DONE.value and not baseline.error, "BASELINE_NOT_DONE", baseline.status),
            self._check("DATA_VERSION_PRESENT", bool(baseline.data_version_id), "DATA_INTEGRITY_INVALID", "canonical data version required"),
            self._check("ENGINE_VERSION_PRESENT", bool(baseline.engine_version), "CANONICAL_EVIDENCE_REQUIRED", "canonical engine version required"),
            self._check("RESULT_PRESENT", bool(baseline.result_json), "RESULT_HASH_REQUIRED", "canonical result required"),
            self._check("RESULT_HASH_PRESENT", bool(baseline.result_hash), "RESULT_HASH_REQUIRED", "canonical result hash required"),
            self._check("MANIFEST_HASH_PRESENT", bool(_manifest_hash(baseline)), "MANIFEST_HASH_REQUIRED", "canonical manifest hash required"),
            self._check(
                "DATA_INTEGRITY_VALID",
                data_quality.get("status") == "VALID"
                and not data_quality.get("errors")
                and bool(data_quality.get("integrity_report_hash")),
                "DATA_INTEGRITY_INVALID",
                str(data_quality.get("status") or "missing"),
            ),
        ]
        accounting_ok = all(persisted_reconciliation.get(key) is True for key in ("cash", "positions", "equity"))
        if accounting_ok:
            accounting_ok = self._rerun_accounting_reconciliation(baseline)
        checks.append(self._check(
            "CANONICAL_ACCOUNTING_RECONCILED",
            accounting_ok,
            "CANONICAL_RECONCILIATION_FAILED",
            "cash, positions, and equity identities",
        ))
        useful = self.db.query(SimulationOrderORM).filter_by(run_id=baseline.id).count() > 0 or self.db.query(SimulationFillORM).filter_by(run_id=baseline.id).count() > 0
        checks.append(self._check("STRATEGY_EVIDENCE_NONEMPTY", useful, "CANONICAL_EVIDENCE_REQUIRED", "at least one canonical order or fill"))
        checks.append(GovernanceCheck(
            "CODE_HASH_PRESENT",
            bool(baseline.code_hash),
            False,
            "canonical code hash present" if baseline.code_hash else "CODE_HASH_MISSING",
            None,
        ))
        return checks

    def _transition_checks(self, record: StrategyGovernanceRecordORM | None, baseline: SimulationRunORM) -> list[GovernanceCheck]:
        return [
            self._check("STAGING_APPROVED", bool(record and record.current_stage == GovernanceStage.STAGING.value), "STAGING_APPROVAL_REQUIRED", "prior STAGING required"),
            self._check("APPROVED_BASELINE_PINNED", bool(record and record.baseline_run_id == baseline.id), "STAGING_APPROVAL_REQUIRED", "PROD must use approved baseline"),
            self._check("CODE_HASH_REQUIRED_FOR_PROD", bool(baseline.code_hash), "CODE_HASH_REQUIRED_FOR_PROD", "canonical baseline code hash"),
        ]

    def _prod_checks(self, baseline: SimulationRunORM, paper_run_id: str | None, reconciliation_id: str | None) -> tuple[SimulationRunORM | None, SimulationReconciliationORM | None, list[GovernanceCheck]]:
        checks: list[GovernanceCheck] = []
        paper = self.db.get(SimulationRunORM, paper_run_id) if paper_run_id else None
        checks.append(self._check("PAPER_RUN_PRESENT", bool(paper_run_id), "PAPER_RUN_REQUIRED", "canonical PAPER run required"))
        checks.append(self._check("PAPER_RUN_FOUND", paper is not None, "PAPER_RUN_NOT_FOUND", str(paper_run_id or "missing")))
        if paper is not None:
            checks.append(self._check("PAPER_MODE", paper.mode == SimulationMode.PAPER.value, "PAPER_MODE_INVALID", paper.mode))
            checks.append(self._check(
                "PAPER_STATUS_EVIDENCE",
                paper.status in {
                    SimulationRunStatus.RUNNING.value,
                    SimulationRunStatus.DONE.value,
                    SimulationRunStatus.FAILED.value,
                    SimulationRunStatus.CANCELLED.value,
                },
                "PAPER_MODE_INVALID",
                paper.status,
            ))
            checks.append(self._check(
                "PAPER_STRATEGY_EXACT",
                paper.strategy_key == baseline.strategy_key and paper.strategy_hash == baseline.strategy_hash,
                "PAPER_STRATEGY_MISMATCH",
                f"{paper.strategy_key}:{paper.strategy_hash}",
            ))
        reconciliation = self.db.get(SimulationReconciliationORM, reconciliation_id) if reconciliation_id else None
        checks.append(self._check("RECONCILIATION_PRESENT", bool(reconciliation_id), "RECONCILIATION_REQUIRED", "Phase 2B reconciliation required"))
        checks.append(self._check("RECONCILIATION_FOUND", reconciliation is not None, "RECONCILIATION_NOT_FOUND", str(reconciliation_id or "missing")))
        if reconciliation is not None:
            compatibility = dict(reconciliation.compatibility_json or {})
            summary = dict(reconciliation.summary_json or {})
            counts = dict(summary.get("match_counts") or {})
            pair_ok = reconciliation.baseline_run_id == baseline.id and reconciliation.paper_run_id == paper_run_id
            checks.extend([
                self._check("RECONCILIATION_DONE", reconciliation.status == "DONE" and bool(reconciliation.report_hash) and reconciliation.paper_cutoff_sequence > 0, "RECONCILIATION_REQUIRED", reconciliation.status),
                self._check("RECONCILIATION_PAIR", pair_ok, "RECONCILIATION_PAIR_MISMATCH", f"{reconciliation.baseline_run_id}/{reconciliation.paper_run_id}"),
                self._check("STRATEGY_IDENTITY_EXACT", compatibility.get("strategy_identity") == "EXACT", "PAPER_STRATEGY_MISMATCH", str(compatibility.get("strategy_identity"))),
                self._check("INTENT_COMPARABLE", compatibility.get("intent_comparable") is True, "RECONCILIATION_NOT_COMPARABLE", "intent_comparable"),
                self._check("ACCOUNTING_COMPARABLE", compatibility.get("accounting_comparable") is True, "RECONCILIATION_NOT_COMPARABLE", "accounting_comparable"),
                self._check("AMBIGUOUS_ALIGNMENT", int(counts.get("AMBIGUOUS", 0)) <= self.policy.prod_max_ambiguous_matches, "RECONCILIATION_AMBIGUOUS", str(counts.get("AMBIGUOUS", 0))),
                self._check("BASELINE_ONLY_ALIGNMENT", int(counts.get("BASELINE_ONLY", 0)) <= self.policy.prod_max_baseline_only, "RECONCILIATION_NOT_COMPARABLE", str(counts.get("BASELINE_ONLY", 0))),
                self._check("PAPER_ONLY_ALIGNMENT", int(counts.get("PAPER_ONLY", 0)) <= self.policy.prod_max_paper_only, "RECONCILIATION_NOT_COMPARABLE", str(counts.get("PAPER_ONLY", 0))),
            ])
            low_count = self.db.query(SimulationReconciliationItemORM).filter_by(
                reconciliation_id=reconciliation.id,
                match_confidence="LOW",
            ).count()
            checks.append(self._check("LOW_CONFIDENCE_ALIGNMENT", low_count <= self.policy.prod_max_low_confidence_matches, "RECONCILIATION_NOT_COMPARABLE", str(low_count)))
            paper_fills = int(dict(summary.get("paper_account") or {}).get("fill_count") or 0)
            matched = int(counts.get("MATCHED", 0))
            checks.append(self._check(
                "PAPER_EXECUTION_MEANINGFUL",
                matched >= self.policy.prod_min_matched_orders and paper_fills >= self.policy.prod_min_paper_fills,
                "PAPER_EVIDENCE_EMPTY",
                f"matched_orders={matched}; paper_fills={paper_fills}",
            ))
            source_hashes_ok = (
                reconciliation.baseline_manifest_hash == _manifest_hash(baseline)
                and reconciliation.baseline_result_hash == baseline.result_hash
            )
            checks.append(self._check("RECONCILIATION_SOURCE_HASHES", source_hashes_ok, "EVIDENCE_INTEGRITY_MISMATCH", "baseline hashes pinned by Phase 2B"))
        return paper, reconciliation, checks

    def _evidence_bundle(self, baseline: SimulationRunORM, paper: SimulationRunORM | None, reconciliation: SimulationReconciliationORM | None) -> dict[str, Any]:
        result = dict(baseline.result_json or {})
        quality = dict(result.get("data_quality") or {})
        bundle: dict[str, Any] = {
            "strategy": {
                "strategy_key": baseline.strategy_key,
                "strategy_hash": baseline.strategy_hash,
                "code_hash": baseline.code_hash,
                "engine_version": baseline.engine_version,
            },
            "baseline": {
                "simulation_run_id": baseline.id,
                "verification_level": baseline.verification_level,
                "data_version_id": baseline.data_version_id,
                "manifest_hash": _manifest_hash(baseline),
                "result_hash": baseline.result_hash,
                "data_integrity_status": quality.get("status"),
                "data_integrity_hash": quality.get("integrity_report_hash"),
                "data_integrity_error_count": len(quality.get("errors") or []),
                "warning_codes": sorted({item.get("code") for item in quality.get("warnings") or [] if item.get("code")}),
                "corporate_actions_applied": dict(quality.get("corporate_actions") or {}).get("applied", 0),
                "legacy_assumptions": sorted(quality.get("legacy_assumptions") or []),
                "accounting_reconciliation": "PASS" if all(dict(result.get("reconciliation") or {}).get(key) is True for key in ("cash", "positions", "equity")) else "FAIL",
            },
            "policy": self.policy.snapshot(),
        }
        if paper is not None:
            bundle["paper"] = {
                "simulation_run_id": paper.id,
                "status": paper.status,
                "manifest_hash": _manifest_hash(paper),
                "strategy_key": paper.strategy_key,
                "strategy_hash": paper.strategy_hash,
            }
        if reconciliation is not None:
            compatibility = dict(reconciliation.compatibility_json or {})
            summary = dict(reconciliation.summary_json or {})
            bundle["reconciliation"] = {
                "id": reconciliation.id,
                "report_hash": reconciliation.report_hash,
                "paper_cutoff_sequence": reconciliation.paper_cutoff_sequence,
                "paper_cutoff_time": _aware(reconciliation.paper_cutoff_time),
                "strategy_identity": compatibility.get("strategy_identity"),
                "intent_comparable": compatibility.get("intent_comparable"),
                "accounting_comparable": compatibility.get("accounting_comparable"),
                "match_counts": dict(summary.get("match_counts") or {}),
                "paper_fill_count": dict(summary.get("paper_account") or {}).get("fill_count"),
            }
        return to_primitive(bundle)

    def _rerun_accounting_reconciliation(self, baseline: SimulationRunORM) -> bool:
        snapshot = self.db.query(SimulationPortfolioSnapshotORM).filter_by(run_id=baseline.id).order_by(
            SimulationPortfolioSnapshotORM.snapshot_time.desc(),
            SimulationPortfolioSnapshotORM.id.desc(),
        ).first()
        if snapshot is None:
            return False
        request = dict(baseline.request_json or {})
        currency = str(request.get("base_currency") or "").upper()
        if not currency:
            return False
        unsettled = Decimal(str(snapshot.cash_unsettled))
        cash = CashBalance(
            currency,
            settled=Decimal(str(snapshot.cash_settled)),
            unsettled_receivable=max(unsettled, Decimal("0")),
            unsettled_payable=max(-unsettled, Decimal("0")),
            reserved=Decimal(str(snapshot.cash_reserved)),
        )
        position_rows = self.db.query(SimulationPositionSnapshotORM).filter_by(
            run_id=baseline.id,
            snapshot_time=snapshot.snapshot_time,
        ).all()
        positions = {
            InstrumentId.parse(row.instrument_key): Position(
                InstrumentId.parse(row.instrument_key),
                Decimal(str(row.quantity)),
                Decimal(str(row.average_cost)),
                Decimal(str(row.realized_pnl)),
                Decimal(str(row.unrealized_pnl)),
                Decimal(str(row.market_value)),
                Decimal(str(row.mark_price)),
            )
            for row in position_rows
        }
        account = AccountState(
            snapshot.account_id,
            currency,
            cash={currency: cash},
            positions=positions,
            realized_pnl=Decimal(str(snapshot.realized_pnl)),
            unrealized_pnl=Decimal(str(snapshot.unrealized_pnl)),
            equity=Decimal(str(snapshot.equity)),
            buying_power=Decimal(str(snapshot.buying_power)),
            fees=Decimal(str(snapshot.fees)),
        )
        ledger = [
            LedgerEntry(
                row.id, row.run_id, row.account_id, _aware(row.event_time),
                LedgerEntryType(row.entry_type), row.currency, Decimal(str(row.amount)),
                InstrumentId.parse(row.instrument_key) if row.instrument_key else None,
                row.order_id, row.fill_id, row.corporate_action_id, dict(row.metadata_json or {}),
            )
            for row in self.db.query(SimulationLedgerEntryORM).filter_by(run_id=baseline.id).all()
        ]
        fills = [
            Fill(
                row.id, row.run_id, row.order_id, row.account_id,
                InstrumentId.parse(row.instrument_key), OrderSide(row.side),
                Decimal(str(row.quantity)), Decimal(str(row.price)), _aware(row.executed_at),
                Decimal(str(row.commission)), Decimal(str(row.fees)), Decimal(str(row.slippage_bps)),
                row.liquidity_flag, row.execution_model,
            )
            for row in self.db.query(SimulationFillORM).filter_by(run_id=baseline.id).all()
        ]
        split_rows = self.db.query(SimulationAppliedCorporateActionORM).filter_by(
            run_id=baseline.id,
            action_type=CorporateActionType.SPLIT.value,
        ).all()
        actions = [
            CorporateAction(
                row.corporate_action_source_id,
                InstrumentId.parse(row.instrument_key),
                CorporateActionType.SPLIT,
                _aware(row.effective_time).date(),
                None,
                None,
                Decimal(str(dict(row.payload_json or {}).get("factor"))),
                None,
                None,
                baseline.data_version_id,
            )
            for row in split_rows
        ]
        try:
            ReconciliationService().reconcile(
                Decimal(str(request.get("initial_cash"))),
                ledger,
                fills,
                account,
                corporate_actions=actions,
                applied_corporate_action_ids={row.corporate_action_source_id for row in split_rows},
            )
        except Exception:
            return False
        return True

    def _project_registry(self, record: StrategyGovernanceRecordORM, decision: StrategyGovernanceDecisionORM, name: str, legacy_model_run_id: str | None, baseline_run_id: str) -> None:
        normalized = name.strip()
        projection = self.db.query(ModelRegistryORM).filter_by(
            name=normalized,
            governance_record_id=record.id,
        ).one_or_none()
        if projection is None:
            projection = ModelRegistryORM(name=normalized, created_at=decision.created_at)
        projection.run_id = legacy_model_run_id
        projection.stage = decision.to_stage.lower()
        projection.promoted_at = decision.created_at
        projection.metadata_json = {"policy_version": decision.policy_version}
        projection.simulation_run_id = baseline_run_id
        projection.governance_record_id = record.id
        projection.governance_decision_id = decision.id
        projection.evidence_hash = decision.evidence_hash
        projection.evidence_level = "CANONICAL"
        self.db.add(projection)

    @staticmethod
    def _check(code: str, passed: bool, failure_code: str, detail: str) -> GovernanceCheck:
        return GovernanceCheck(code, bool(passed), True, detail, failure_code)

    @staticmethod
    def _stage(value: GovernanceStage | str) -> GovernanceStage:
        try:
            return value if isinstance(value, GovernanceStage) else GovernanceStage(str(value).upper())
        except ValueError as exc:
            raise GovernanceError("INVALID_STAGE_TRANSITION") from exc

    def _require_actor(self, actor_user_id: str) -> str:
        actor = str(actor_user_id or "").strip()
        if not actor or self.db.get(User, actor) is None:
            raise GovernanceError("AUTHENTICATION_REQUIRED")
        return actor

    @staticmethod
    def _audit(event: str, record: StrategyGovernanceRecordORM, decision: StrategyGovernanceDecisionORM, actor: str) -> AuditLogORM:
        return AuditLogORM(
            user_id=actor,
            event_type=event,
            entity_type="strategy_governance",
            entity_id=record.id,
            payload_json={
                "decision_id": decision.id,
                "strategy_key": record.strategy_key,
                "strategy_hash": record.strategy_hash,
                "from_stage": decision.from_stage,
                "to_stage": decision.to_stage,
                "baseline_run_id": decision.baseline_run_id,
                "paper_run_id": decision.paper_run_id,
                "reconciliation_id": decision.reconciliation_id,
                "evidence_hash": decision.evidence_hash,
                "policy_version": decision.policy_version,
            },
            created_at=decision.created_at,
        )

    def _evidence_current(self, record: StrategyGovernanceRecordORM) -> bool:
        history = self.repository.history(record.id)
        if not history:
            return False
        decision = history[-1]
        if decision.decision_type == GovernanceDecisionType.REVOKE.value:
            return True
        evidence = dict(decision.evidence_json or {})
        baseline_evidence = dict(evidence.get("baseline") or {})
        baseline = self.db.get(SimulationRunORM, decision.baseline_run_id) if decision.baseline_run_id else None
        if baseline is None or baseline.result_hash != baseline_evidence.get("result_hash") or _manifest_hash(baseline) != baseline_evidence.get("manifest_hash"):
            return False
        if decision.reconciliation_id:
            reconciliation = self.db.get(SimulationReconciliationORM, decision.reconciliation_id)
            if reconciliation is None or reconciliation.report_hash != dict(evidence.get("reconciliation") or {}).get("report_hash"):
                return False
        return sha256_value(evidence) == decision.evidence_hash

    def _record_dict(self, record: StrategyGovernanceRecordORM) -> dict[str, Any]:
        return {
            "id": record.id,
            "strategy_key": record.strategy_key,
            "strategy_hash": record.strategy_hash,
            "current_stage": record.current_stage,
            "baseline_run_id": record.baseline_run_id,
            "latest_paper_run_id": record.latest_paper_run_id,
            "latest_reconciliation_id": record.latest_reconciliation_id,
            "latest_evidence_hash": record.latest_evidence_hash,
            "policy_version": record.policy_version,
            "evidence_current": self._evidence_current(record),
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
            "revoked_at": record.revoked_at.isoformat() if record.revoked_at else None,
        }

    def _decision_dict(self, decision: StrategyGovernanceDecisionORM, record: StrategyGovernanceRecordORM | None = None) -> dict[str, Any]:
        return {
            "id": decision.id,
            "governance_record_id": decision.governance_record_id,
            "decision_type": decision.decision_type,
            "from_stage": decision.from_stage,
            "to_stage": decision.to_stage,
            "baseline_run_id": decision.baseline_run_id,
            "paper_run_id": decision.paper_run_id,
            "reconciliation_id": decision.reconciliation_id,
            "policy_version": decision.policy_version,
            "evidence_hash": decision.evidence_hash,
            "reason": decision.reason,
            "actor_user_id": decision.actor_user_id,
            "created_at": decision.created_at.isoformat(),
            "current_stage": record.current_stage if record else None,
        }
