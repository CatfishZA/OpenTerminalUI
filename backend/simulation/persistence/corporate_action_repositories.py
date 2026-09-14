from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from backend.simulation.domain.corporate_actions import CorporateAction, DividendEntitlement
from backend.simulation.domain.enums import CorporateActionType
from backend.simulation.domain.identifiers import InstrumentId
from backend.simulation.persistence.models import (
    SimulationAppliedCorporateActionORM,
    SimulationCorporateActionEntitlementORM,
)
from backend.simulation.persistence.serializers import to_primitive


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None and value.utcoffset() is not None else value.replace(tzinfo=timezone.utc)


class CorporateActionRepository:
    def __init__(self, db: Session, *, auto_commit: bool):
        self.db = db
        self.auto_commit = auto_commit

    def applied_ids(self, run_id: str) -> set[str]:
        return {
            row.corporate_action_source_id
            for row in self.db.query(SimulationAppliedCorporateActionORM).filter_by(run_id=run_id).all()
        }

    def entitlements(self, run_id: str) -> list[DividendEntitlement]:
        rows = self.db.query(SimulationCorporateActionEntitlementORM).filter_by(run_id=run_id).order_by(
            SimulationCorporateActionEntitlementORM.entitlement_date,
            SimulationCorporateActionEntitlementORM.id,
        ).all()
        return [DividendEntitlement(
            id=row.id, run_id=row.run_id,
            corporate_action_source_id=row.corporate_action_source_id,
            instrument=InstrumentId.parse(row.instrument_key),
            entitlement_date=row.entitlement_date, pay_date=row.pay_date,
            eligible_quantity=Decimal(str(row.eligible_quantity)),
            cash_amount_per_share=Decimal(str(row.cash_amount_per_share)),
            currency=row.currency, total_amount=Decimal(str(row.total_amount)),
            status=row.status, created_at=_aware(row.created_at), paid_at=_aware(row.paid_at),
        ) for row in rows]

    def save_applied(self, run_id: str, action: CorporateAction, at: datetime, payload: dict) -> None:
        row = self.db.query(SimulationAppliedCorporateActionORM).filter_by(
            run_id=run_id, corporate_action_source_id=action.id
        ).one_or_none()
        if row is None:
            self.db.add(SimulationAppliedCorporateActionORM(
                run_id=run_id, corporate_action_source_id=action.id,
                instrument_key=action.instrument.key, action_type=action.action_type.value,
                effective_time=at, payload_json=to_primitive(payload),
            ))
        self._finish()

    def save_entitlement(self, item: DividendEntitlement) -> None:
        row = self.db.get(SimulationCorporateActionEntitlementORM, item.id)
        if row is None:
            row = SimulationCorporateActionEntitlementORM(id=item.id, run_id=item.run_id)
        row.corporate_action_source_id = item.corporate_action_source_id
        row.instrument_key = item.instrument.key
        row.action_type = CorporateActionType.CASH_DIVIDEND.value
        row.entitlement_date = item.entitlement_date
        row.pay_date = item.pay_date
        row.eligible_quantity = item.eligible_quantity
        row.cash_amount_per_share = item.cash_amount_per_share
        row.currency = item.currency
        row.total_amount = item.total_amount
        row.status = item.status
        row.created_at = item.created_at or datetime.now(timezone.utc)
        row.paid_at = item.paid_at
        self.db.add(row)
        self._finish()

    def mark_action_paid(self, run_id: str, source_id: str, paid_at: datetime, ledger_id: str | None) -> None:
        row = self.db.query(SimulationAppliedCorporateActionORM).filter_by(
            run_id=run_id, corporate_action_source_id=source_id
        ).one()
        payment = {
            **dict(row.payload_json or {}),
            "payment_status": "PAID",
            "paid_at": paid_at.isoformat(),
        }
        if ledger_id is not None:
            payment["payment_ledger_id"] = ledger_id
        row.payload_json = payment
        self._finish()

    def count_applied(self, run_id: str) -> int:
        return self.db.query(SimulationAppliedCorporateActionORM).filter_by(run_id=run_id).count()

    def _finish(self) -> None:
        if self.auto_commit:
            self.db.commit()
        else:
            self.db.flush()
