from __future__ import annotations

from sqlalchemy.orm import Session

from backend.models import StrategyGovernanceDecisionORM, StrategyGovernanceRecordORM


class GovernanceRepository:
    def __init__(self, db: Session):
        self.db = db

    def by_identity(self, strategy_key: str, strategy_hash: str) -> StrategyGovernanceRecordORM | None:
        return self.db.query(StrategyGovernanceRecordORM).filter_by(
            strategy_key=strategy_key,
            strategy_hash=strategy_hash,
        ).one_or_none()

    def get(self, record_id: str) -> StrategyGovernanceRecordORM | None:
        return self.db.get(StrategyGovernanceRecordORM, record_id)

    def decision_by_request(self, request_hash: str) -> StrategyGovernanceDecisionORM | None:
        return self.db.query(StrategyGovernanceDecisionORM).filter_by(request_hash=request_hash).one_or_none()

    def history(self, record_id: str) -> list[StrategyGovernanceDecisionORM]:
        return self.db.query(StrategyGovernanceDecisionORM).filter_by(
            governance_record_id=record_id
        ).order_by(StrategyGovernanceDecisionORM.created_at, StrategyGovernanceDecisionORM.id).all()
