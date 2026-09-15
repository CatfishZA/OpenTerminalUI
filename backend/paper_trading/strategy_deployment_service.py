from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from backend.governance.service import StrategyGovernanceService
from backend.models import (
    AuditLogORM,
    PaperStrategyDeploymentORM,
    PaperStrategyInputORM,
    PaperStrategyIntentORM,
    SimulationOrderORM,
    SimulationRunORM,
    StrategyGovernanceDecisionORM,
    StrategyGovernanceRecordORM,
    VirtualOrder,
    VirtualPortfolio,
)
from backend.paper_trading.deployment_domain import (
    CompletedBarObservation,
    DeploymentError,
    DeploymentStatus,
    StrategyCapability,
    TERMINAL_DEPLOYMENT_STATUSES,
)
from backend.paper_trading.deployment_policy import DeploymentRiskPolicy
from backend.paper_trading.deployment_repositories import DeploymentRepository
from backend.paper_trading.strategy_market_read_model import DeploymentMarketReadModel, observation_payload
from backend.paper_trading.strategy_risk_service import StrategyRiskService
from backend.simulation.adapters.strategy_runner_adapter import StrategyRunnerAdapter
from backend.simulation.domain.enums import EventType, OrderStatus, OrderType, TimeInForce
from backend.simulation.domain.events import SimulationEvent
from backend.simulation.domain.identifiers import InstrumentId
from backend.simulation.domain.strategy import OrderApi, StrategyContext, StrategyIntent
from backend.simulation.persistence.serializers import to_primitive
from backend.simulation.services.manifest_service import sha256_value
from backend.simulation.services.paper_simulation_service import PaperSimulationService

DEPLOYMENT_POLICY_VERSION = "paper-deployment-v1"
_DEPLOYMENT_LOCKS: dict[str, asyncio.Lock] = {}
_VENUE_TIMEZONES = {"NSE": "Asia/Kolkata", "BSE": "Asia/Kolkata", "NYSE": "America/New_York", "NASDAQ": "America/New_York", "AMEX": "America/New_York"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None and value.utcoffset() is not None else value.replace(tzinfo=timezone.utc)


class _NoopOrderApi(OrderApi):
    def submit(self, intent: StrategyIntent) -> None:
        return None

    def cancel(self, order_id: str) -> None:
        return None


class StrategyDeploymentService:
    """Governed automation above the canonical Phase 2A PAPER engine."""

    def __init__(self, db: Session):
        self.db = db
        self.repository = DeploymentRepository(db)
        self.paper = PaperSimulationService(db)
        self.risk = StrategyRiskService(db)

    @staticmethod
    def lock_for(deployment_id: str) -> asyncio.Lock:
        return _DEPLOYMENT_LOCKS.setdefault(deployment_id, asyncio.Lock())

    def create(
        self,
        *,
        governance_record_id: str,
        user_id: str,
        name: str,
        risk_policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = self.db.get(StrategyGovernanceRecordORM, governance_record_id)
        if record is None:
            raise DeploymentError("GOVERNANCE_RECORD_NOT_FOUND")
        self._require_deployable(record)
        baseline = self.db.get(SimulationRunORM, record.baseline_run_id)
        if baseline is None:
            raise DeploymentError("APPROVED_BASELINE_NOT_FOUND")
        config = self._strategy_config(baseline)
        adapter = StrategyRunnerAdapter(config["strategy"], dict(config["strategy_context"]))
        if not adapter.supports(StrategyCapability.COMPLETED_BAR.value):
            raise DeploymentError("STRATEGY_CAPABILITY_UNSUPPORTED")
        decision = self._approved_decision(record)
        policy = DeploymentRiskPolicy.from_request(risk_policy)
        deployment_id = f"pdep_{uuid4().hex}"
        provenance = {
            "deployment_id": deployment_id,
            "governance_record_id": record.id,
            "governance_decision_id": decision.id,
            "approved_baseline_run_id": baseline.id,
            "approved_evidence_hash": record.latest_evidence_hash,
            "strategy_config_hash": sha256_value(config),
            "risk_policy": policy.snapshot(),
        }
        portfolio = self.paper.create_portfolio(
            user_id=user_id,
            name=name.strip() or "Strategy Paper Validation",
            initial_cash=Decimal(str(config["initial_cash"])),
            base_currency=config["base_currency"],
            strategy_key=record.strategy_key,
            strategy_context=dict(config["strategy_context"]),
            execution_profile=dict(config["execution_profile"]),
            commission_profile=dict(config["commission_profile"]),
            settlement_profile=dict(config["settlement_profile"]),
            strategy_hash=record.strategy_hash,
            code_hash=baseline.code_hash,
            request_metadata={"deployment": provenance, "universe": config["universe"]},
            manifest_metadata={"deployment": provenance, "universe_hash": sha256_value(config["universe"])},
        )
        created = _now()
        deployment = PaperStrategyDeploymentORM(
            id=deployment_id,
            user_id=user_id,
            governance_record_id=record.id,
            governance_decision_id=decision.id,
            baseline_run_id=baseline.id,
            portfolio_id=portfolio.id,
            simulation_run_id=portfolio.simulation_run_id,
            name=name.strip() or "Strategy Paper Validation",
            strategy_key=record.strategy_key,
            strategy_hash=record.strategy_hash,
            code_hash=baseline.code_hash,
            approved_evidence_hash=record.latest_evidence_hash,
            policy_version=DEPLOYMENT_POLICY_VERSION,
            status=DeploymentStatus.CREATED.value,
            symbols_json=list(config["universe"]),
            strategy_config_json=to_primitive(config),
            strategy_config_hash=sha256_value(config),
            risk_policy_json=policy.snapshot(),
            strategy_state_json={},
            last_decision_sequence=0,
            created_at=created,
            updated_at=created,
        )
        self.db.add(deployment)
        self.db.flush()
        self.repository.append_event(deployment.id, "CREATED", created, provenance)
        self.db.add(self._audit("paper_strategy_deployment_created", deployment, None, DeploymentStatus.CREATED.value))
        self.db.commit()
        return self.as_dict(deployment)

    async def start(self, deployment_id: str, *, user_id: str) -> dict[str, Any]:
        async with self.lock_for(deployment_id):
            deployment = self._owned(deployment_id, user_id)
            self._verify_governance_or_raise(deployment)
            self._transition(deployment, {DeploymentStatus.CREATED}, DeploymentStatus.RUNNING, "STARTED")
            return self._commit_state(deployment, "paper_strategy_deployment_started")

    async def pause(self, deployment_id: str, *, user_id: str) -> dict[str, Any]:
        async with self.lock_for(deployment_id):
            deployment = self._owned(deployment_id, user_id)
            self._transition(deployment, {DeploymentStatus.RUNNING}, DeploymentStatus.PAUSED, "PAUSED")
            deployment.paused_at = _now()
            return self._commit_state(deployment, "paper_strategy_deployment_paused")

    async def resume(self, deployment_id: str, *, user_id: str) -> dict[str, Any]:
        async with self.lock_for(deployment_id):
            deployment = self._owned(deployment_id, user_id)
            self._verify_governance_or_raise(deployment)
            self._transition(deployment, {DeploymentStatus.PAUSED}, DeploymentStatus.RUNNING, "RESUMED")
            return self._commit_state(deployment, "paper_strategy_deployment_resumed")

    async def stop(self, deployment_id: str, *, user_id: str, reason: str) -> dict[str, Any]:
        async with self.lock_for(deployment_id):
            deployment = self._owned(deployment_id, user_id)
            self._transition(
                deployment,
                {DeploymentStatus.CREATED, DeploymentStatus.RUNNING, DeploymentStatus.PAUSED},
                DeploymentStatus.STOPPED,
                "STOPPED",
                reason=reason,
            )
            deployment.stopped_at = _now()
            await self._cancel_owned_orders(deployment)
            return self._commit_state(deployment, "paper_strategy_deployment_stopped", reason)

    async def halt(self, deployment_id: str, *, user_id: str, reason: str) -> dict[str, Any]:
        if not reason.strip():
            raise DeploymentError("KILL_SWITCH_REASON_REQUIRED")
        async with self.lock_for(deployment_id):
            deployment = self._owned(deployment_id, user_id)
            await self._halt_locked(deployment, reason)
            return self.as_dict(deployment)

    async def process_completed_bar(self, deployment_id: str, observation: CompletedBarObservation) -> dict[str, Any]:
        if not observation.complete:
            return {"status": "IGNORED", "reason": "INCOMPLETE_BAR"}
        async with self.lock_for(deployment_id):
            deployment = self.repository.get(deployment_id)
            if deployment is None:
                raise DeploymentError("DEPLOYMENT_NOT_FOUND")
            if deployment.status != DeploymentStatus.RUNNING.value:
                return {"status": "IGNORED", "reason": f"DEPLOYMENT_{deployment.status}"}
            if observation.instrument.key not in set(deployment.symbols_json or []):
                raise DeploymentError("RISK_SYMBOL_NOT_ALLOWED")
            existing = self.repository.input_by_source(deployment.id, observation.source_event_id)
            if existing is not None:
                if existing.payload_hash != sha256_value(observation_payload(observation)):
                    raise DeploymentError("MARKET_INPUT_INVALID", "source_event_id payload mismatch")
                if existing.processed_status == "PROCESSING":
                    recovered = await self._recover_input_locked(deployment, existing)
                    if recovered:
                        return {"status": "RECOVERED", "input_id": existing.id, "source_event_id": existing.source_event_id}
                self.repository.append_event(deployment.id, "INPUT_DUPLICATE", _now(), {"source_event_id": observation.source_event_id})
                self.db.commit()
                return {"status": "DUPLICATE", "input_id": existing.id, "source_event_id": existing.source_event_id}
            try:
                self._verify_governance_or_raise(deployment)
            except DeploymentError as exc:
                await self._halt_locked(deployment, exc.code)
                return {"status": "HALTED", "reason": exc.code}
            portfolio = self.db.get(VirtualPortfolio, deployment.portfolio_id)
            if portfolio is None:
                raise DeploymentError("DEPLOYMENT_NOT_FOUND")
            account = await self.paper.mark_account(
                portfolio,
                instrument=observation.instrument,
                price=observation.close,
                at=observation.end_time,
                source=f"completed-bar:{observation.source}",
            )
            policy = DeploymentRiskPolicy.from_request(deployment.risk_policy_json)
            daily = self.risk.evaluate_daily_loss(
                deployment, account, risk_day=self._risk_day(observation), policy=policy
            )
            if not daily.accepted:
                await self._halt_locked(deployment, daily.reason or "RISK_DAILY_LOSS_EXCEEDED")
                return {"status": "HALTED", "reason": daily.reason}
            payload = observation_payload(observation)
            input_row = PaperStrategyInputORM(
                deployment_id=deployment.id,
                source_event_id=observation.source_event_id,
                instrument_key=observation.instrument.key,
                input_type=StrategyCapability.COMPLETED_BAR.value,
                input_time=observation.end_time,
                payload_json=payload,
                payload_hash=sha256_value(payload),
                accepted_sequence=self.repository.next_input_sequence(deployment.id),
                processed_status="PROCESSING",
                created_at=_now(),
            )
            self.db.add(input_row)
            self.db.flush()
            self.repository.append_event(deployment.id, "INPUT_ACCEPTED", _now(), {"input_id": input_row.id, "source_event_id": observation.source_event_id})
            try:
                intents, strategy = self._evaluate(deployment, observation, account)
                accepted = 0
                rejected = 0
                for ordinal, intent in enumerate(intents):
                    row, was_accepted = await self._persist_and_submit_intent(
                        deployment, input_row, ordinal, intent, observation, account, policy
                    )
                    accepted += int(was_accepted)
                    rejected += int(not was_accepted)
                deployment.strategy_state_json = to_primitive(strategy.export_state())
                deployment.last_input_event_id = observation.source_event_id
                deployment.last_input_time = observation.end_time
                deployment.last_decision_sequence += 1
                deployment.checkpoint_hash = self._checkpoint_hash(deployment)
                deployment.updated_at = _now()
                input_row.processed_status = "PROCESSED" if intents else "NO_INTENT"
                input_row.processed_at = _now()
                self.repository.append_event(deployment.id, "DECISION_COMPLETED", _now(), {
                    "input_id": input_row.id, "intent_count": len(intents),
                    "accepted_count": accepted, "rejected_count": rejected,
                    "checkpoint_hash": deployment.checkpoint_hash,
                })
                self.db.commit()
                return {
                    "status": "PROCESSED", "input_id": input_row.id,
                    "intent_count": len(intents), "accepted_count": accepted,
                    "rejected_count": rejected, "checkpoint_hash": deployment.checkpoint_hash,
                }
            except DeploymentError as exc:
                if exc.code == "WARMUP_DATA_INSUFFICIENT":
                    input_row.processed_status = "BLOCKED"
                    input_row.error_code = exc.code
                    input_row.processed_at = _now()
                    deployment.last_input_event_id = observation.source_event_id
                    deployment.last_input_time = observation.end_time
                    deployment.updated_at = _now()
                    self.repository.append_event(deployment.id, "DECISION_BLOCKED", _now(), {"input_id": input_row.id, "reason": exc.code})
                    self.db.commit()
                    return {"status": "BLOCKED", "input_id": input_row.id, "reason": exc.code}
                self.db.rollback()
                raise
            except Exception as exc:
                self.db.rollback()
                deployment = self.repository.get(deployment_id)
                if deployment is not None:
                    deployment.status = DeploymentStatus.FAILED.value
                    deployment.last_error = f"STRATEGY_EVALUATION_FAILED: {type(exc).__name__}"
                    deployment.updated_at = _now()
                    self.repository.append_event(deployment.id, "FAILED", _now(), {"error": deployment.last_error})
                    await self._cancel_owned_orders(deployment)
                    self.db.commit()
                raise DeploymentError("STRATEGY_EVALUATION_FAILED") from exc

    async def recover(self, deployment_id: str, *, user_id: str) -> dict[str, Any]:
        async with self.lock_for(deployment_id):
            deployment = self._owned(deployment_id, user_id)
            rows = self.db.query(PaperStrategyInputORM).filter_by(
                deployment_id=deployment.id, processed_status="PROCESSING"
            ).order_by(PaperStrategyInputORM.accepted_sequence).all()
            recovered = 0
            for row in rows:
                recovered += int(await self._recover_input_locked(deployment, row))
            self.db.commit()
            return {"deployment_id": deployment.id, "recovered_inputs": recovered}

    def list(self, *, user_id: str, status: str | None = None, strategy_key: str | None = None, governance_record_id: str | None = None, offset: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        query = self.db.query(PaperStrategyDeploymentORM).filter_by(user_id=user_id)
        if status:
            query = query.filter_by(status=status.upper())
        if strategy_key:
            query = query.filter_by(strategy_key=strategy_key)
        if governance_record_id:
            query = query.filter_by(governance_record_id=governance_record_id)
        return [self.as_dict(row) for row in query.order_by(PaperStrategyDeploymentORM.created_at.desc()).offset(offset).limit(limit)]

    def get(self, deployment_id: str, *, user_id: str) -> dict[str, Any]:
        return self.as_dict(self._owned(deployment_id, user_id))

    def events(self, deployment_id: str, *, user_id: str) -> list[dict[str, Any]]:
        self._owned(deployment_id, user_id)
        return [{"id": row.id, "sequence": row.sequence, "event_type": row.event_type, "event_time": _aware(row.event_time).isoformat(), "payload": row.payload_json} for row in self.repository.events(deployment_id)]

    def intents(self, deployment_id: str, *, user_id: str) -> list[dict[str, Any]]:
        self._owned(deployment_id, user_id)
        return [{
            "id": row.intent_id, "input_id": row.input_id, "ordinal": row.ordinal,
            "instrument": row.instrument_key, "side": row.side, "quantity": str(row.quantity),
            "order_type": row.order_type, "tif": row.tif, "limit_price": str(row.limit_price) if row.limit_price is not None else None,
            "stop_price": str(row.stop_price) if row.stop_price is not None else None,
            "risk_decision": row.risk_decision, "risk_reason": row.risk_reason,
            "canonical_order_id": row.canonical_order_id, "metadata": row.metadata_json,
        } for row in self.repository.intents(deployment_id)]

    def _evaluate(self, deployment: PaperStrategyDeploymentORM, observation: CompletedBarObservation, account):  # noqa: ANN001
        config = dict(deployment.strategy_config_json or {})
        instruments = tuple(InstrumentId.parse(item) for item in config["universe"])
        market = DeploymentMarketReadModel(
            self.db,
            deployment_id=deployment.id,
            data_version_id=config["data_version_id"],
            instruments=instruments,
            decision_time=observation.end_time,
        )
        required = self._required_history(dict(config["strategy_context"]))
        if len(market.history(observation.instrument, limit=required)) < required:
            raise DeploymentError("WARMUP_DATA_INSUFFICIENT")
        strategy = StrategyRunnerAdapter(config["strategy"], dict(config["strategy_context"]))
        strategy.import_state(dict(deployment.strategy_state_json or {}))
        ctx = StrategyContext(observation.end_time, account, account.positions, account.cash, market, _NoopOrderApi())
        event = SimulationEvent(
            run_id=deployment.simulation_run_id,
            sequence=deployment.last_decision_sequence + 1,
            event_id=f"decision_{observation.source_event_id}",
            event_type=EventType.STRATEGY_CLOSE_CALLBACK,
            event_time=observation.end_time,
            processing_time=_now(),
            instrument=observation.instrument,
            payload={"source_event_id": observation.source_event_id},
        )
        return strategy.on_event(ctx, event), strategy

    async def _persist_and_submit_intent(self, deployment, input_row, ordinal, intent, observation, account, policy):  # noqa: ANN001
        basis = {
            "strategy_hash": deployment.strategy_hash,
            "source_event_id": input_row.source_event_id,
            "instrument": intent.instrument.key,
            "ordinal": ordinal,
        }
        intent_id = f"pint_{sha256_value(basis)[:48]}"
        fingerprint = sha256_value({
            **basis, "side": intent.side.value, "quantity": intent.quantity,
            "order_type": intent.order_type.value, "tif": intent.tif.value,
            "limit_price": intent.limit_price, "stop_price": intent.stop_price,
        })
        price = intent.limit_price or intent.stop_price or observation.close
        decision = self.risk.evaluate_intent(deployment, account, intent, price=price, policy=policy)
        row = PaperStrategyIntentORM(
            intent_id=intent_id, deployment_id=deployment.id, input_id=input_row.id, ordinal=ordinal,
            instrument_key=intent.instrument.key, side=intent.side.value, quantity=intent.quantity,
            order_type=intent.order_type.value, tif=intent.tif.value,
            limit_price=intent.limit_price, stop_price=intent.stop_price,
            intent_fingerprint=fingerprint,
            risk_decision="ACCEPTED" if decision.accepted else "REJECTED",
            risk_reason=decision.reason,
            metadata_json=to_primitive(intent.metadata), created_at=_now(),
        )
        self.db.add(row)
        self.db.flush()
        if not decision.accepted:
            self.repository.append_event(deployment.id, "INTENT_REJECTED", _now(), {"intent_id": intent_id, "reason": decision.reason})
            if decision.reason == "RISK_DAILY_LOSS_EXCEEDED":
                await self._halt_locked(deployment, decision.reason)
            return row, False
        self.repository.append_event(deployment.id, "INTENT_ACCEPTED", _now(), {"intent_id": intent_id})
        existing = self.db.query(SimulationOrderORM).filter_by(
            run_id=deployment.simulation_run_id, strategy_order_id=intent_id
        ).one_or_none()
        if existing is not None:
            row.canonical_order_id = existing.id
            self.repository.append_event(deployment.id, "ORDER_RECOVERED", _now(), {"intent_id": intent_id, "order_id": existing.id})
            return row, True
        portfolio = self.db.get(VirtualPortfolio, deployment.portfolio_id)
        metadata = {
            "deployment_id": deployment.id,
            "intent_id": intent_id,
            "governance_record_id": deployment.governance_record_id,
            "strategy_key": deployment.strategy_key,
            "strategy_hash": deployment.strategy_hash,
            "source_event_id": input_row.source_event_id,
            "max_participation": str(dict(deployment.strategy_config_json).get("execution_profile", {}).get("max_participation", "1")),
            "commission_bps": str(dict(deployment.strategy_config_json).get("commission_profile", {}).get("bps", "5")),
        }
        virtual = await self.paper.submit_order(
            portfolio=portfolio,
            symbol=f"{intent.instrument.venue}:{intent.instrument.symbol}",
            side=intent.side.value.lower(),
            order_type={OrderType.MARKET: "market", OrderType.LIMIT: "limit", OrderType.STOP: "sl"}[intent.order_type],
            quantity=intent.quantity,
            limit_price=intent.limit_price,
            stop_price=intent.stop_price,
            slippage_bps=Decimal(str(dict(deployment.strategy_config_json).get("execution_profile", {}).get("slippage_bps", "0"))),
            commission=Decimal("0"),
            cached_tick=None,
            submitted_at=observation.end_time,
            reconciliation_key=intent_id,
            strategy_order_id=intent_id,
            time_in_force=intent.tif,
            eligible_at=observation.end_time + timedelta(microseconds=1),
            order_metadata=metadata,
        )
        row.canonical_order_id = virtual.simulation_order_id
        self.repository.append_event(deployment.id, "ORDER_SUBMITTED", _now(), {"intent_id": intent_id, "order_id": virtual.simulation_order_id})
        return row, True

    async def _recover_input_locked(self, deployment: PaperStrategyDeploymentORM, input_row: PaperStrategyInputORM) -> bool:
        intents = self.db.query(PaperStrategyIntentORM).filter_by(
            deployment_id=deployment.id, input_id=input_row.id
        ).order_by(PaperStrategyIntentORM.ordinal).all()
        if not intents:
            return False
        for intent in intents:
            order = self.db.query(SimulationOrderORM).filter_by(
                run_id=deployment.simulation_run_id, strategy_order_id=intent.intent_id
            ).one_or_none()
            if intent.risk_decision == "ACCEPTED" and order is None:
                return False
            if order is not None:
                intent.canonical_order_id = order.id
                self.repository.append_event(deployment.id, "ORDER_RECOVERED", _now(), {"intent_id": intent.intent_id, "order_id": order.id})
        observation = self._observation_from_input(input_row)
        portfolio = self.db.get(VirtualPortfolio, deployment.portfolio_id)
        account = await self.paper.current_account(portfolio, at=observation.end_time)
        _discarded, strategy = self._evaluate(deployment, observation, account)
        deployment.strategy_state_json = to_primitive(strategy.export_state())
        deployment.last_input_event_id = input_row.source_event_id
        deployment.last_input_time = input_row.input_time
        deployment.last_decision_sequence += 1
        deployment.checkpoint_hash = self._checkpoint_hash(deployment)
        deployment.updated_at = _now()
        input_row.processed_status = "PROCESSED"
        input_row.processed_at = _now()
        self.repository.append_event(deployment.id, "DECISION_RECOVERED", _now(), {"input_id": input_row.id, "checkpoint_hash": deployment.checkpoint_hash})
        return True

    async def _halt_locked(self, deployment: PaperStrategyDeploymentORM, reason: str) -> None:
        current = DeploymentStatus(deployment.status)
        if current in TERMINAL_DEPLOYMENT_STATUSES:
            raise DeploymentError("DEPLOYMENT_TERMINAL")
        previous = deployment.status
        deployment.status = DeploymentStatus.HALTED.value
        deployment.halted_at = _now()
        deployment.updated_at = _now()
        deployment.last_error = reason
        self.repository.append_event(deployment.id, "HALTED", _now(), {"from_status": previous, "reason": reason})
        if reason.startswith("RISK_"):
            self.repository.append_event(deployment.id, "RISK_BREACH", _now(), {"reason": reason})
        if reason.startswith("GOVERNANCE_"):
            self.repository.append_event(deployment.id, "GOVERNANCE_BLOCKED", _now(), {"reason": reason})
        await self._cancel_owned_orders(deployment)
        self.db.add(self._audit("paper_strategy_deployment_halted", deployment, previous, deployment.status, reason))
        self.db.commit()

    async def _cancel_owned_orders(self, deployment: PaperStrategyDeploymentORM) -> None:
        rows = self.db.query(SimulationOrderORM).filter(
            SimulationOrderORM.run_id == deployment.simulation_run_id,
            SimulationOrderORM.status.in_([OrderStatus.ACCEPTED.value, OrderStatus.PARTIALLY_FILLED.value]),
        ).all()
        portfolio = self.db.get(VirtualPortfolio, deployment.portfolio_id)
        for row in rows:
            if dict(row.metadata_json or {}).get("deployment_id") != deployment.id:
                continue
            virtual = self.db.query(VirtualOrder).filter_by(simulation_order_id=row.id).one_or_none()
            if virtual is not None:
                await self.paper.cancel_order(portfolio, virtual, at=_now())

    def _verify_governance_or_raise(self, deployment: PaperStrategyDeploymentORM) -> None:
        record = self.db.get(StrategyGovernanceRecordORM, deployment.governance_record_id)
        if record is None:
            raise DeploymentError("GOVERNANCE_RECORD_NOT_FOUND")
        self._require_deployable(record)
        if record.latest_evidence_hash != deployment.approved_evidence_hash or record.baseline_run_id != deployment.baseline_run_id:
            raise DeploymentError("GOVERNANCE_EVIDENCE_STALE")

    def _require_deployable(self, record: StrategyGovernanceRecordORM) -> None:
        if record.current_stage not in {"STAGING", "PROD"}:
            raise DeploymentError("GOVERNANCE_STAGE_NOT_DEPLOYABLE")
        if not record.strategy_key or not record.strategy_hash or not record.baseline_run_id or not record.latest_evidence_hash:
            raise DeploymentError("GOVERNANCE_EVIDENCE_STALE")
        try:
            current = StrategyGovernanceService(self.db).get(record.id)["evidence_current"]
        except Exception as exc:
            raise DeploymentError("GOVERNANCE_EVIDENCE_STALE") from exc
        if not current:
            raise DeploymentError("GOVERNANCE_EVIDENCE_STALE")

    def _approved_decision(self, record: StrategyGovernanceRecordORM) -> StrategyGovernanceDecisionORM:
        rows = self.db.query(StrategyGovernanceDecisionORM).filter_by(
            governance_record_id=record.id,
            decision_type="PROMOTE",
            to_stage=record.current_stage,
            evidence_hash=record.latest_evidence_hash,
        ).order_by(StrategyGovernanceDecisionORM.created_at.desc()).all()
        if not rows:
            raise DeploymentError("GOVERNANCE_EVIDENCE_STALE")
        return rows[0]

    @staticmethod
    def _strategy_config(baseline: SimulationRunORM) -> dict[str, Any]:
        raw = dict(baseline.request_json or {})
        required = ("strategy", "strategy_context", "universe", "initial_cash", "base_currency", "data_version_id", "execution_profile", "commission_profile", "settlement_profile")
        if any(key not in raw or raw[key] in (None, [], "") for key in required):
            raise DeploymentError("STRATEGY_CONFIG_UNRESOLVED")
        if raw["strategy"] != baseline.strategy_key:
            raise DeploymentError("STRATEGY_HASH_MISMATCH")
        context = dict(raw.get("strategy_context") or {})
        if sha256_value({"key": raw["strategy"], "context": context}) != baseline.strategy_hash:
            raise DeploymentError("STRATEGY_HASH_MISMATCH")
        universe = [item if isinstance(item, str) else InstrumentId(**item).key for item in raw["universe"]]
        try:
            for item in universe:
                InstrumentId.parse(item)
        except Exception as exc:
            raise DeploymentError("STRATEGY_CONFIG_UNRESOLVED") from exc
        return {
            "strategy": raw["strategy"], "strategy_context": context,
            "universe": universe, "initial_cash": str(raw["initial_cash"]),
            "base_currency": str(raw["base_currency"]), "data_version_id": str(raw["data_version_id"]),
            "execution_profile": dict(raw["execution_profile"]),
            "commission_profile": dict(raw["commission_profile"]),
            "settlement_profile": dict(raw["settlement_profile"]),
        }

    @staticmethod
    def _required_history(context: dict[str, Any]) -> int:
        return max(1, int(context.get("long_window", context.get("lookback", 1))))

    @staticmethod
    def _risk_day(observation: CompletedBarObservation) -> str:
        zone = ZoneInfo(_VENUE_TIMEZONES.get(observation.instrument.venue, "UTC"))
        return observation.end_time.astimezone(zone).date().isoformat()

    @staticmethod
    def _observation_from_input(row: PaperStrategyInputORM) -> CompletedBarObservation:
        raw = dict(row.payload_json or {})
        return CompletedBarObservation(
            source_event_id=raw["source_event_id"], instrument=InstrumentId.parse(raw["instrument"]),
            interval=raw["interval"], start_time=datetime.fromisoformat(raw["start_time"]),
            end_time=datetime.fromisoformat(raw["end_time"]), open=Decimal(raw["open"]),
            high=Decimal(raw["high"]), low=Decimal(raw["low"]), close=Decimal(raw["close"]),
            volume=Decimal(raw["volume"]), source=raw["source"], complete=bool(raw["complete"]),
        )

    def _owned(self, deployment_id: str, user_id: str) -> PaperStrategyDeploymentORM:
        row = self.repository.get(deployment_id)
        if row is None:
            raise DeploymentError("DEPLOYMENT_NOT_FOUND")
        if row.user_id != user_id:
            raise DeploymentError("DEPLOYMENT_ACCESS_DENIED")
        return row

    def _transition(self, deployment, allowed, target, event, reason=""):  # noqa: ANN001
        current = DeploymentStatus(deployment.status)
        if current in TERMINAL_DEPLOYMENT_STATUSES:
            raise DeploymentError("DEPLOYMENT_TERMINAL")
        if current not in allowed:
            raise DeploymentError("INVALID_DEPLOYMENT_TRANSITION")
        deployment.status = target.value
        deployment.updated_at = _now()
        if target is DeploymentStatus.RUNNING and deployment.started_at is None:
            deployment.started_at = deployment.updated_at
        self.repository.append_event(deployment.id, event, deployment.updated_at, {"from_status": current.value, "to_status": target.value, **({"reason": reason} if reason else {})})

    def _commit_state(self, deployment, audit_event: str, reason: str = "") -> dict[str, Any]:  # noqa: ANN001
        event = self.repository.events(deployment.id)[-1]
        payload = dict(event.payload_json or {})
        self.db.add(self._audit(audit_event, deployment, payload.get("from_status"), deployment.status, reason))
        self.db.commit()
        return self.as_dict(deployment)

    @staticmethod
    def _checkpoint_hash(deployment: PaperStrategyDeploymentORM) -> str:
        return sha256_value({
            "deployment_id": deployment.id,
            "strategy_hash": deployment.strategy_hash,
            "strategy_state": deployment.strategy_state_json,
            "last_input_event_id": deployment.last_input_event_id,
            "last_input_time": deployment.last_input_time,
            "last_decision_sequence": deployment.last_decision_sequence,
        })

    @staticmethod
    def _audit(event: str, deployment: PaperStrategyDeploymentORM, from_status: str | None, to_status: str, reason: str = "") -> AuditLogORM:
        return AuditLogORM(
            user_id=deployment.user_id, event_type=event, entity_type="paper_strategy_deployment",
            entity_id=deployment.id,
            payload_json={
                "deployment_id": deployment.id, "governance_record_id": deployment.governance_record_id,
                "strategy_key": deployment.strategy_key, "strategy_hash": deployment.strategy_hash,
                "simulation_run_id": deployment.simulation_run_id,
                "from_status": from_status, "to_status": to_status,
                **({"reason": reason} if reason else {}),
            },
            created_at=_now(),
        )

    @staticmethod
    def as_dict(row: PaperStrategyDeploymentORM) -> dict[str, Any]:
        return {
            "id": row.id, "name": row.name, "status": row.status,
            "governance_record_id": row.governance_record_id,
            "governance_decision_id": row.governance_decision_id,
            "strategy_key": row.strategy_key, "strategy_hash": row.strategy_hash,
            "code_hash": row.code_hash, "baseline_run_id": row.baseline_run_id,
            "approved_evidence_hash": row.approved_evidence_hash,
            "portfolio_id": row.portfolio_id, "simulation_run_id": row.simulation_run_id,
            "symbols": list(row.symbols_json or []), "risk_policy": dict(row.risk_policy_json or {}),
            "checkpoint_hash": row.checkpoint_hash,
            "last_input_time": _aware(row.last_input_time).isoformat() if row.last_input_time else None,
            "last_error": row.last_error,
            "created_at": _aware(row.created_at).isoformat(),
        }
