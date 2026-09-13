from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from backend.simulation.persistence.models import SimulationSettlementObligationORM


class PaperSettlementRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        obligation_id: str,
        run_id: str,
        account_id: str,
        fill_id: str,
        currency: str,
        amount: Decimal,
        settlement_date: date,
        created_at: datetime,
    ) -> SimulationSettlementObligationORM:
        row = SimulationSettlementObligationORM(
            id=obligation_id,
            run_id=run_id,
            account_id=account_id,
            fill_id=fill_id,
            currency=currency,
            amount=amount,
            settlement_date=settlement_date,
            status="PENDING",
            created_at=created_at,
        )
        self.db.add(row)
        return row

    def outstanding(self, run_id: str) -> list[SimulationSettlementObligationORM]:
        return (
            self.db.query(SimulationSettlementObligationORM)
            .filter_by(run_id=run_id, status="PENDING")
            .order_by(SimulationSettlementObligationORM.settlement_date, SimulationSettlementObligationORM.id)
            .all()
        )

    def due(self, run_id: str, session: date) -> list[SimulationSettlementObligationORM]:
        return (
            self.db.query(SimulationSettlementObligationORM)
            .filter(
                SimulationSettlementObligationORM.run_id == run_id,
                SimulationSettlementObligationORM.status == "PENDING",
                SimulationSettlementObligationORM.settlement_date <= session,
            )
            .order_by(SimulationSettlementObligationORM.settlement_date, SimulationSettlementObligationORM.id)
            .all()
        )

    @staticmethod
    def mark_settled(row: SimulationSettlementObligationORM, at: datetime) -> None:
        row.status = "SETTLED"
        row.settled_at = at

