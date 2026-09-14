from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable
from uuid import uuid4

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.simulation.domain.enums import SimulationMode, SimulationRunStatus, VerificationLevel
from backend.simulation.domain.reconciliation import (
    AlignmentPolicy,
    BacktestPaperReconciliationSpec,
    MatchBasis,
    MatchConfidence,
    MatchStatus,
    ReconciliationStatus,
)
from backend.simulation.persistence.models import (
    SimulationEventORM,
    SimulationExecutionObservationORM,
    SimulationFillORM,
    SimulationOrderORM,
    SimulationPortfolioSnapshotORM,
    SimulationPositionSnapshotORM,
    SimulationReconciliationORM,
    SimulationRunORM,
    SimulationSettlementObligationORM,
)
from backend.simulation.persistence.reconciliation_repositories import ReconciliationRepository
from backend.simulation.persistence.serializers import to_primitive
from backend.simulation.services.execution_calibration_service import ExecutionCalibrationService
from backend.simulation.services.manifest_service import sha256_value
from backend.simulation.services.paper_simulation_service import PaperSimulationService


class BacktestPaperReconciliationError(ValueError):
    def __init__(self, code: str, message: str | None = None):
        self.code = code
        super().__init__(f"{code}: {message}" if message else code)


def _d(value: object | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal("0.00000001")).normalize()


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _manifest_hash(run: SimulationRunORM) -> str | None:
    return dict(run.manifest_json or {}).get("manifest_hash")


class BacktestPaperReconciliationService:
    """Immutable cross-run comparison. Canonical source artifacts are read-only."""

    def __init__(self, db: Session):
        self.db = db
        self.repository = ReconciliationRepository(db)
        self.calibration = ExecutionCalibrationService()

    async def create(self, spec: BacktestPaperReconciliationSpec) -> dict[str, Any]:
        baseline, paper = self._validate_runs(spec)
        async with PaperSimulationService.lock_for(paper.id):
            cutoff_sequence, cutoff_time = self._resolve_cutoff(paper.id, spec.paper_cutoff_sequence)
            baseline_orders, baseline_fills = self._snapshot_baseline(baseline.id)
            paper_orders, paper_fills, observations = self._snapshot_paper(paper.id, cutoff_sequence)
            self._validate_comparability(baseline, paper, baseline_orders, paper_orders)
            request_hash = sha256_value(
                {
                    "baseline_run_id": baseline.id,
                    "paper_run_id": paper.id,
                    "paper_cutoff_sequence": cutoff_sequence,
                    "alignment_policy": spec.alignment_policy.value,
                    "allow_research_baseline": spec.allow_research_baseline,
                    "include_low_confidence_matches": spec.include_low_confidence_matches,
                }
            )
            existing = self.repository.by_request_hash(request_hash)
            if existing is not None:
                return dict(existing.report_json)

            baseline_aggregates = self._aggregates(baseline_orders, baseline_fills)
            paper_aggregates = self._aggregates(paper_orders, paper_fills)
            compatibility = self._compatibility(
                baseline, paper, baseline_orders, paper_orders, spec.allow_research_baseline
            )
            items = self._align(
                baseline_orders,
                paper_orders,
                baseline_aggregates,
                paper_aggregates,
                policy=spec.alignment_policy,
                include_low=spec.include_low_confidence_matches,
            )
            observation_payload = self._observation_payload(observations, paper_fills)
            calibration = self.calibration.build(
                baseline_request=dict(baseline.request_json or {}),
                paper_request=dict(paper.request_json or {}),
                baseline_aggregates=list(baseline_aggregates.values()),
                paper_aggregates=list(paper_aggregates.values()),
                observations=observation_payload,
                paper_orders=paper_orders,
            )
            summary = self._summary(
                baseline,
                paper,
                cutoff_time,
                items,
                baseline_orders,
                baseline_fills,
                paper_orders,
                paper_fills,
            )
            reconciliation_id = f"rec_{uuid4().hex[:16]}"
            hash_basis = {
                "baseline_run_id": baseline.id,
                "paper_run_id": paper.id,
                "baseline_manifest_hash": _manifest_hash(baseline),
                "baseline_result_hash": baseline.result_hash,
                "paper_manifest_hash": _manifest_hash(paper),
                "paper_cutoff_sequence": cutoff_sequence,
                "paper_cutoff_time": cutoff_time,
                "alignment_policy": spec.alignment_policy,
                "compatibility": compatibility,
                "summary": summary,
                "calibration": calibration,
                "items": items,
            }
            report_hash = sha256_value(hash_basis)
            completed_at = datetime.now(timezone.utc)
            report = to_primitive(
                {
                    "reconciliation_id": reconciliation_id,
                    "status": ReconciliationStatus.DONE,
                    **hash_basis,
                    "request_hash": request_hash,
                    "report_hash": report_hash,
                    "created_at": completed_at,
                    "completed_at": completed_at,
                }
            )
            row = SimulationReconciliationORM(
                id=reconciliation_id,
                baseline_run_id=baseline.id,
                paper_run_id=paper.id,
                status=ReconciliationStatus.DONE.value,
                alignment_policy=spec.alignment_policy.value,
                allow_research_baseline=spec.allow_research_baseline,
                include_low_confidence=spec.include_low_confidence_matches,
                paper_cutoff_sequence=cutoff_sequence,
                paper_cutoff_time=cutoff_time,
                baseline_manifest_hash=_manifest_hash(baseline),
                baseline_result_hash=baseline.result_hash,
                paper_manifest_hash=_manifest_hash(paper),
                request_hash=request_hash,
                report_hash=report_hash,
                compatibility_json=to_primitive(compatibility),
                summary_json=to_primitive(summary),
                calibration_json=to_primitive(calibration),
                report_json=report,
                error="",
                created_at=completed_at,
                completed_at=completed_at,
            )
            persistence_items = [
                {
                    "sequence": index,
                    "item_type": item["item_type"],
                    "instrument_key": item.get("instrument_key"),
                    "baseline_order_id": item.get("baseline_order_id"),
                    "paper_order_id": item.get("paper_order_id"),
                    "match_status": item["match_status"],
                    "match_basis": item["match_basis"],
                    "match_confidence": item["match_confidence"],
                    "divergence_codes_json": item["divergence_codes"],
                    "metrics_json": item["metrics"],
                }
                for index, item in enumerate(items, 1)
            ]
            try:
                self.repository.add_report(row, persistence_items)
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise
            return report

    def get(self, reconciliation_id: str) -> dict[str, Any]:
        row = self.repository.get(reconciliation_id)
        if row is None:
            raise BacktestPaperReconciliationError("RECONCILIATION_NOT_FOUND")
        return dict(row.report_json)

    def items(self, reconciliation_id: str, **filters: Any) -> list[dict[str, Any]]:
        if self.repository.get(reconciliation_id) is None:
            raise BacktestPaperReconciliationError("RECONCILIATION_NOT_FOUND")
        return [
            {
                "sequence": row.sequence,
                "item_type": row.item_type,
                "instrument_key": row.instrument_key,
                "baseline_order_id": row.baseline_order_id,
                "paper_order_id": row.paper_order_id,
                "match_status": row.match_status,
                "match_basis": row.match_basis,
                "match_confidence": row.match_confidence,
                "divergence_codes": row.divergence_codes_json,
                "metrics": row.metrics_json,
            }
            for row in self.repository.items(reconciliation_id, **filters)
        ]

    def list_for_run(self, run_id: str, *, offset: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        if self.db.get(SimulationRunORM, run_id) is None:
            raise BacktestPaperReconciliationError("RECONCILIATION_NOT_FOUND", "source run does not exist")
        return [
            {
                "reconciliation_id": row.id,
                "baseline_run_id": row.baseline_run_id,
                "paper_run_id": row.paper_run_id,
                "status": row.status,
                "paper_cutoff_sequence": row.paper_cutoff_sequence,
                "paper_cutoff_time": row.paper_cutoff_time.isoformat(),
                "report_hash": row.report_hash,
                "created_at": row.created_at.isoformat(),
            }
            for row in self.repository.list_for_run(run_id, offset=offset, limit=limit)
        ]

    def _validate_runs(self, spec: BacktestPaperReconciliationSpec) -> tuple[SimulationRunORM, SimulationRunORM]:
        if spec.baseline_run_id == spec.paper_run_id:
            raise BacktestPaperReconciliationError("BASELINE_MODE_INVALID", "source run ids must differ")
        baseline = self.db.get(SimulationRunORM, spec.baseline_run_id)
        if baseline is None:
            raise BacktestPaperReconciliationError("BASELINE_RUN_NOT_FOUND")
        paper = self.db.get(SimulationRunORM, spec.paper_run_id)
        if paper is None:
            raise BacktestPaperReconciliationError("PAPER_RUN_NOT_FOUND")
        if baseline.mode != SimulationMode.BACKTEST.value:
            raise BacktestPaperReconciliationError("BASELINE_MODE_INVALID")
        if paper.mode != SimulationMode.PAPER.value:
            raise BacktestPaperReconciliationError("PAPER_MODE_INVALID")
        if baseline.status != SimulationRunStatus.DONE.value:
            raise BacktestPaperReconciliationError("BASELINE_NOT_DONE")
        if baseline.verification_level != VerificationLevel.VERIFIED.value:
            if baseline.verification_level != VerificationLevel.RESEARCH.value or not spec.allow_research_baseline:
                raise BacktestPaperReconciliationError("VERIFIED_BASELINE_REQUIRED")
        if paper.status not in {
            SimulationRunStatus.RUNNING.value,
            SimulationRunStatus.DONE.value,
            SimulationRunStatus.FAILED.value,
            SimulationRunStatus.CANCELLED.value,
        }:
            raise BacktestPaperReconciliationError("PAPER_MODE_INVALID", "PAPER run is neither running nor terminal")
        return baseline, paper

    def _resolve_cutoff(self, run_id: str, requested: int | None) -> tuple[int, datetime]:
        query = self.db.query(SimulationEventORM).filter_by(run_id=run_id)
        event = (
            query.filter_by(sequence=requested).one_or_none()
            if requested is not None
            else query.order_by(SimulationEventORM.sequence.desc()).first()
        )
        if event is None:
            raise BacktestPaperReconciliationError("PAPER_CUTOFF_NOT_FOUND")
        return int(event.sequence), _aware(event.event_time)

    def _snapshot_baseline(self, run_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        orders = self.db.query(SimulationOrderORM).filter_by(run_id=run_id).order_by(SimulationOrderORM.submitted_at, SimulationOrderORM.id).all()
        fills = self.db.query(SimulationFillORM).filter_by(run_id=run_id).order_by(SimulationFillORM.executed_at, SimulationFillORM.id).all()
        return [self._order_dict(row) for row in orders], [self._fill_dict(row) for row in fills]

    def _snapshot_paper(self, run_id: str, cutoff: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        events = (
            self.db.query(SimulationEventORM)
            .filter(SimulationEventORM.run_id == run_id, SimulationEventORM.sequence <= cutoff)
            .order_by(SimulationEventORM.sequence)
            .all()
        )
        order_ids = {row.order_id for row in events if row.order_id}
        fill_ids = {row.fill_id for row in events if row.fill_id}
        order_rows = self.db.query(SimulationOrderORM).filter(SimulationOrderORM.id.in_(order_ids)).all() if order_ids else []
        fill_rows = self.db.query(SimulationFillORM).filter(SimulationFillORM.id.in_(fill_ids)).all() if fill_ids else []
        status_by_order: dict[str, tuple[str, datetime]] = {}
        accepted_at_by_order: dict[str, datetime] = {}
        event_status = {
            "ORDER_ACCEPTED": "ACCEPTED",
            "ORDER_REJECTED": "REJECTED",
            "ORDER_PARTIAL_FILL": "PARTIALLY_FILLED",
            "ORDER_FILL": "FILLED",
            "ORDER_CANCELLED": "CANCELLED",
        }
        for event in events:
            if event.order_id and event.event_type in event_status:
                event_time = _aware(event.event_time)
                status_by_order[event.order_id] = (event_status[event.event_type], event_time)
                if event.event_type == "ORDER_ACCEPTED":
                    accepted_at_by_order[event.order_id] = event_time
        fills = [self._fill_dict(row) for row in fill_rows]
        filled_by_order: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        for fill in fills:
            filled_by_order[fill["order_id"]] += _d(fill["quantity"]) or Decimal("0")
        orders = []
        for row in order_rows:
            item = self._order_dict(row)
            status, status_time = status_by_order.get(row.id, ("CREATED", _aware(row.submitted_at)))
            item["status"] = status
            item["accepted_at"] = accepted_at_by_order.get(row.id)
            item["completed_at"] = status_time if status in {"FILLED", "CANCELLED", "EXPIRED", "REJECTED"} else None
            item["remaining_quantity"] = max(Decimal("0"), (_d(item["quantity"]) or Decimal("0")) - filled_by_order[row.id])
            orders.append(item)
        orders.sort(key=lambda item: (item["submitted_at"], item["id"]))
        observations = (
            self.db.query(SimulationExecutionObservationORM).filter(SimulationExecutionObservationORM.fill_id.in_(fill_ids)).all()
            if fill_ids else []
        )
        return orders, fills, [self._observation_dict(row) for row in observations]

    @staticmethod
    def _order_dict(row: SimulationOrderORM) -> dict[str, Any]:
        return {
            "id": row.id,
            "instrument_key": row.instrument_key,
            "side": row.side,
            "order_type": row.order_type,
            "quantity": _d(row.quantity),
            "remaining_quantity": _d(row.remaining_quantity),
            "tif": row.tif,
            "limit_price": _d(row.limit_price),
            "stop_price": _d(row.stop_price),
            "status": row.status,
            "submitted_at": _aware(row.submitted_at),
            "accepted_at": _aware(row.accepted_at) if row.accepted_at else None,
            "completed_at": _aware(row.completed_at) if row.completed_at else None,
            "strategy_order_id": row.strategy_order_id,
            "metadata": dict(row.metadata_json or {}),
        }

    @staticmethod
    def _fill_dict(row: SimulationFillORM) -> dict[str, Any]:
        return {
            "id": row.id,
            "order_id": row.order_id,
            "quantity": _d(row.quantity),
            "price": _d(row.price),
            "commission": _d(row.commission),
            "fees": _d(row.fees),
            "slippage_bps": _d(row.slippage_bps),
            "executed_at": _aware(row.executed_at),
        }

    @staticmethod
    def _observation_dict(row: SimulationExecutionObservationORM) -> dict[str, Any]:
        return {
            "fill_id": row.fill_id,
            "tick_price": _d(row.tick_price),
            "bid": _d(row.bid),
            "ask": _d(row.ask),
            "tick_size": _d(row.tick_size),
            "tick_source": row.tick_source,
            "liquidity_assumption": row.liquidity_assumption,
        }

    def _validate_comparability(self, baseline: SimulationRunORM, paper: SimulationRunORM, baseline_orders: list[dict[str, Any]], paper_orders: list[dict[str, Any]]) -> None:
        if self._base_currency(baseline) != self._base_currency(paper):
            raise BacktestPaperReconciliationError("CURRENCY_MISMATCH")
        baseline_instruments = {row["instrument_key"] for row in baseline_orders}
        paper_instruments = {row["instrument_key"] for row in paper_orders}
        if not baseline_instruments.intersection(paper_instruments):
            raise BacktestPaperReconciliationError("NO_INSTRUMENT_OVERLAP")

    @staticmethod
    def _base_currency(run: SimulationRunORM) -> str | None:
        request = dict(run.request_json or {})
        return request.get("base_currency") or dict(request.get("account") or {}).get("base_currency")

    def _aggregates(self, orders: list[dict[str, Any]], fills: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        by_order: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for fill in fills:
            by_order[fill["order_id"]].append(fill)
        result = {}
        for order in orders:
            aggregate = self.calibration.aggregate_fills(order, by_order[order["id"]])
            aggregate["status"] = order["status"]
            result[order["id"]] = aggregate
        return result

    def _compatibility(self, baseline: SimulationRunORM, paper: SimulationRunORM, baseline_orders: list[dict[str, Any]], paper_orders: list[dict[str, Any]], allow_research: bool) -> dict[str, Any]:
        if baseline.strategy_key != paper.strategy_key:
            identity = "DIFFERENT"
        elif baseline.strategy_hash == paper.strategy_hash:
            identity = "EXACT"
        else:
            identity = "KEY_ONLY"
        explicit = any(order["metadata"].get("reconciliation_key") or order["strategy_order_id"] for order in baseline_orders + paper_orders)
        warnings = ["MARKET_PERIODS_DIFFER"]
        if baseline.verification_level == VerificationLevel.RESEARCH.value and allow_research:
            warnings.append("RESEARCH_BASELINE")
        if dict(baseline.request_json or {}).get("execution_profile") != dict(paper.request_json or {}).get("execution_profile"):
            warnings.append("EXECUTION_PROFILE_DIFFERS")
        overlap = sorted({row["instrument_key"] for row in baseline_orders} & {row["instrument_key"] for row in paper_orders})
        return {
            "strategy_identity": identity,
            "accounting_comparable": True,
            "intent_comparable": explicit or (identity != "DIFFERENT" and paper.strategy_key != "manual:paper"),
            "execution_assumptions_comparable": True,
            "settlement_comparable": True,
            "performance_comparable": False,
            "instrument_overlap": overlap,
            "warnings": warnings,
        }

    def _align(self, baseline: list[dict[str, Any]], paper: list[dict[str, Any]], baseline_aggregates: dict[str, dict[str, Any]], paper_aggregates: dict[str, dict[str, Any]], *, policy: AlignmentPolicy, include_low: bool) -> list[dict[str, Any]]:
        remaining_b = {row["id"]: row for row in baseline}
        remaining_p = {row["id"]: row for row in paper}
        items: list[dict[str, Any]] = []

        def explicit(field: str, basis: MatchBasis, confidence: MatchConfidence) -> None:
            b_groups = self._groups(remaining_b.values(), field)
            p_groups = self._groups(remaining_p.values(), field)
            for value in sorted(set(b_groups) & set(p_groups)):
                bs, ps = b_groups[value], p_groups[value]
                if len(bs) == len(ps) == 1:
                    b, p = bs[0], ps[0]
                    items.append(self._matched_item(b, p, basis, confidence, baseline_aggregates, paper_aggregates))
                    remaining_b.pop(b["id"]); remaining_p.pop(p["id"])
                else:
                    for b in bs:
                        items.append(self._ambiguous_item(b, value, basis, ps))
                        remaining_b.pop(b["id"])
                    for p in ps:
                        remaining_p.pop(p["id"])

        explicit("reconciliation_key", MatchBasis.RECONCILIATION_KEY, MatchConfidence.EXACT)
        explicit("strategy_order_id", MatchBasis.STRATEGY_ORDER_ID, MatchConfidence.HIGH)

        if policy is AlignmentPolicy.KEYED_THEN_SIGNATURE:
            self._match_signature(remaining_b, remaining_p, items, baseline_aggregates, paper_aggregates)
            if include_low:
                self._match_ordinal(remaining_b, remaining_p, items, baseline_aggregates, paper_aggregates)

        for order in sorted(remaining_b.values(), key=self._order_sort):
            items.append(self._unmatched_item(order, MatchStatus.BASELINE_ONLY, baseline_aggregates[order["id"]]))
        for order in sorted(remaining_p.values(), key=self._order_sort):
            items.append(self._unmatched_item(order, MatchStatus.PAPER_ONLY, paper_aggregates[order["id"]]))
        return items

    @staticmethod
    def _groups(orders: Iterable[dict[str, Any]], field: str) -> dict[str, list[dict[str, Any]]]:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for order in orders:
            value = order["metadata"].get(field) if field == "reconciliation_key" else order.get(field)
            if value:
                groups[str(value)].append(order)
        return groups

    @staticmethod
    def _order_sort(order: dict[str, Any]) -> tuple[Any, str]:
        return order["submitted_at"], order["id"]

    @staticmethod
    def _stream(order: dict[str, Any]) -> tuple[str, str, str]:
        return order["instrument_key"], order["side"], order["order_type"]

    def _with_ordinals(self, orders: Iterable[dict[str, Any]]) -> dict[str, int]:
        counters: dict[tuple[str, str, str], int] = defaultdict(int)
        result = {}
        for order in sorted(orders, key=self._order_sort):
            stream = self._stream(order)
            result[order["id"]] = counters[stream]
            counters[stream] += 1
        return result

    def _match_signature(self, remaining_b: dict[str, dict[str, Any]], remaining_p: dict[str, dict[str, Any]], items: list[dict[str, Any]], ba: dict[str, dict[str, Any]], pa: dict[str, dict[str, Any]]) -> None:
        b_ord, p_ord = self._with_ordinals(remaining_b.values()), self._with_ordinals(remaining_p.values())
        def signature(order: dict[str, Any], ordinal: int) -> tuple[Any, ...]:
            return (*self._stream(order), order["quantity"], order["limit_price"], order["stop_price"], ordinal)
        p_by_signature: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
        for p in remaining_p.values(): p_by_signature[signature(p, p_ord[p["id"]])].append(p)
        for b in sorted(list(remaining_b.values()), key=self._order_sort):
            candidates = p_by_signature.get(signature(b, b_ord[b["id"]]), [])
            if len(candidates) == 1 and candidates[0]["id"] in remaining_p:
                p = candidates[0]
                items.append(self._matched_item(b, p, MatchBasis.UNIQUE_SIGNATURE, MatchConfidence.MEDIUM, ba, pa))
                remaining_b.pop(b["id"]); remaining_p.pop(p["id"])

    def _match_ordinal(self, remaining_b: dict[str, dict[str, Any]], remaining_p: dict[str, dict[str, Any]], items: list[dict[str, Any]], ba: dict[str, dict[str, Any]], pa: dict[str, dict[str, Any]]) -> None:
        b_ord, p_ord = self._with_ordinals(remaining_b.values()), self._with_ordinals(remaining_p.values())
        p_lookup = {(self._stream(p), p_ord[p["id"]]): p for p in remaining_p.values()}
        for b in sorted(list(remaining_b.values()), key=self._order_sort):
            p = p_lookup.get((self._stream(b), b_ord[b["id"]]))
            if p is not None and p["id"] in remaining_p:
                items.append(self._matched_item(b, p, MatchBasis.ORDINAL_FALLBACK, MatchConfidence.LOW, ba, pa))
                remaining_b.pop(b["id"]); remaining_p.pop(p["id"])

    def _matched_item(self, baseline: dict[str, Any], paper: dict[str, Any], basis: MatchBasis, confidence: MatchConfidence, ba: dict[str, dict[str, Any]], pa: dict[str, dict[str, Any]]) -> dict[str, Any]:
        divergences = []
        for field, code in (("side", "SIDE_MISMATCH"), ("order_type", "ORDER_TYPE_MISMATCH"), ("quantity", "QUANTITY_MISMATCH"), ("limit_price", "LIMIT_PRICE_MISMATCH"), ("stop_price", "STOP_PRICE_MISMATCH"), ("status", "STATUS_MISMATCH")):
            if baseline[field] != paper[field]: divergences.append(code)
        b, p = ba[baseline["id"]], pa[paper["id"]]
        if b["partial_fill"] != p["partial_fill"]: divergences.append("PARTIAL_FILL_DIFFERENCE")
        if b["fill_ratio"] != p["fill_ratio"]: divergences.append("FILL_RATIO_DIFFERENCE")
        if (baseline["status"] == "CANCELLED") != (paper["status"] == "CANCELLED"): divergences.append("CANCEL_DIFFERENCE")
        if (baseline["status"] == "REJECTED") != (paper["status"] == "REJECTED"): divergences.append("REJECTION_DIFFERENCE")
        metrics = {
            "baseline": {"order": self._order_metrics(baseline), "fills": to_primitive(b)},
            "paper": {"order": self._order_metrics(paper), "fills": to_primitive(p)},
            "fill_ratio_delta": self._delta(p.get("fill_ratio"), b.get("fill_ratio")),
            "simulated_slippage_delta_bps": self._delta(p.get("simulated_slippage_bps"), b.get("simulated_slippage_bps")),
            "commission_delta_bps": self._delta(p.get("effective_commission_bps"), b.get("effective_commission_bps")),
            "direct_price_delta_valid": False,
        }
        return self._item(baseline, paper, MatchStatus.MATCHED, basis, confidence, divergences, metrics)

    @staticmethod
    def _order_metrics(order: dict[str, Any]) -> dict[str, Any]:
        return to_primitive(
            {
                key: order.get(key)
                for key in (
                    "instrument_key", "side", "order_type", "quantity", "remaining_quantity", "tif",
                    "limit_price", "stop_price", "status", "submitted_at", "accepted_at", "completed_at",
                )
            }
        )

    @staticmethod
    def _delta(left: object | None, right: object | None) -> str | None:
        if left is None or right is None: return None
        return str((Decimal(str(left)) - Decimal(str(right))).normalize())

    def _ambiguous_item(self, baseline: dict[str, Any], value: str, basis: MatchBasis, candidates: list[dict[str, Any]]) -> dict[str, Any]:
        return self._item(baseline, None, MatchStatus.AMBIGUOUS, basis, MatchConfidence.NONE, ["AMBIGUOUS_MATCH"], {"key": value, "paper_candidate_order_ids": sorted(row["id"] for row in candidates)})

    def _unmatched_item(self, order: dict[str, Any], status: MatchStatus, aggregate: dict[str, Any]) -> dict[str, Any]:
        baseline = order if status is MatchStatus.BASELINE_ONLY else None
        paper = order if status is MatchStatus.PAPER_ONLY else None
        return self._item(
            baseline, paper, status, MatchBasis.NONE, MatchConfidence.NONE, [status.value],
            {status.value.lower(): {"order": self._order_metrics(order), "fills": to_primitive(aggregate)}},
        )

    @staticmethod
    def _item(baseline: dict[str, Any] | None, paper: dict[str, Any] | None, status: MatchStatus, basis: MatchBasis, confidence: MatchConfidence, divergences: list[str], metrics: dict[str, Any]) -> dict[str, Any]:
        source = baseline or paper or {}
        return {
            "item_type": "ORDER", "instrument_key": source.get("instrument_key"),
            "baseline_order_id": baseline.get("id") if baseline else None,
            "paper_order_id": paper.get("id") if paper else None,
            "match_status": status.value, "match_basis": basis.value, "match_confidence": confidence.value,
            "divergence_codes": divergences, "metrics": to_primitive(metrics),
        }

    @staticmethod
    def _observation_payload(observations: list[dict[str, Any]], fills: list[dict[str, Any]]) -> list[dict[str, Any]]:
        quantities = {row["id"]: row["quantity"] for row in fills}
        return [{**row, "fill_quantity": quantities.get(row["fill_id"])} for row in observations]

    def _summary(self, baseline: SimulationRunORM, paper: SimulationRunORM, cutoff_time: datetime, items: list[dict[str, Any]], baseline_orders: list[dict[str, Any]], baseline_fills: list[dict[str, Any]], paper_orders: list[dict[str, Any]], paper_fills: list[dict[str, Any]]) -> dict[str, Any]:
        counts = {status.value: sum(item["match_status"] == status.value for item in items) for status in MatchStatus}
        return {
            "match_counts": counts,
            "baseline_account": self._account_summary(baseline, None, len(baseline_orders), len(baseline_fills)),
            "paper_account": self._account_summary(paper, cutoff_time, len(paper_orders), len(paper_fills)),
            "performance_attribution": "not_causal_across_different_market_periods",
        }

    def _account_summary(self, run: SimulationRunORM, cutoff_time: datetime | None, order_count: int, fill_count: int) -> dict[str, Any]:
        query = self.db.query(SimulationPortfolioSnapshotORM).filter_by(run_id=run.id)
        if cutoff_time is not None: query = query.filter(SimulationPortfolioSnapshotORM.snapshot_time <= cutoff_time)
        snapshot = query.order_by(SimulationPortfolioSnapshotORM.snapshot_time.desc(), SimulationPortfolioSnapshotORM.id.desc()).first()
        position_time_query = self.db.query(func.max(SimulationPositionSnapshotORM.snapshot_time)).filter_by(run_id=run.id)
        if cutoff_time is not None:
            position_time_query = position_time_query.filter(SimulationPositionSnapshotORM.snapshot_time <= cutoff_time)
        position_time = position_time_query.scalar()
        positions = [] if position_time is None else self.db.query(SimulationPositionSnapshotORM).filter_by(run_id=run.id, snapshot_time=position_time).all()
        request = dict(run.request_json or {})
        initial = request.get("initial_cash") or dict(request.get("account") or {}).get("initial_cash")
        result = {"initial_cash": initial, "order_count": order_count, "fill_count": fill_count, "position_count": sum((_d(row.quantity) or Decimal("0")) != 0 for row in positions)}
        for name in ("equity", "cash_settled", "cash_unsettled", "cash_reserved", "realized_pnl", "unrealized_pnl", "fees", "gross_exposure", "net_exposure"):
            result[name] = str(getattr(snapshot, name)) if snapshot is not None else None
        if run.mode == SimulationMode.PAPER.value:
            obligations = self.db.query(SimulationSettlementObligationORM).filter(SimulationSettlementObligationORM.run_id == run.id)
            if cutoff_time is not None: obligations = obligations.filter(SimulationSettlementObligationORM.created_at <= cutoff_time)
            rows = obligations.all()
            result["pending_settlement_count"] = sum(row.settled_at is None or _aware(row.settled_at) > cutoff_time for row in rows)
            result["settled_settlement_count"] = len(rows) - result["pending_settlement_count"]
        return result
