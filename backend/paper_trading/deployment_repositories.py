from __future__ import annotations

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models import (
    PaperStrategyDeploymentORM,
    PaperStrategyEventORM,
    PaperStrategyInputORM,
    PaperStrategyIntentORM,
)


class DeploymentRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, deployment_id: str) -> PaperStrategyDeploymentORM | None:
        return self.db.get(PaperStrategyDeploymentORM, deployment_id)

    def for_user(self, deployment_id: str, user_id: str) -> PaperStrategyDeploymentORM | None:
        return self.db.query(PaperStrategyDeploymentORM).filter_by(id=deployment_id, user_id=user_id).one_or_none()

    def input_by_source(self, deployment_id: str, source_event_id: str) -> PaperStrategyInputORM | None:
        return self.db.query(PaperStrategyInputORM).filter_by(
            deployment_id=deployment_id, source_event_id=source_event_id
        ).one_or_none()

    def next_input_sequence(self, deployment_id: str) -> int:
        return int(self.db.query(func.coalesce(func.max(PaperStrategyInputORM.accepted_sequence), 0)).filter_by(
            deployment_id=deployment_id
        ).scalar()) + 1

    def append_event(self, deployment_id: str, event_type: str, at: datetime, payload: dict | None = None) -> PaperStrategyEventORM:
        sequence = int(self.db.query(func.coalesce(func.max(PaperStrategyEventORM.sequence), 0)).filter_by(
            deployment_id=deployment_id
        ).scalar()) + 1
        row = PaperStrategyEventORM(
            deployment_id=deployment_id,
            sequence=sequence,
            event_type=event_type,
            event_time=at,
            payload_json=payload or {},
        )
        self.db.add(row)
        self.db.flush()
        return row

    def events(self, deployment_id: str) -> list[PaperStrategyEventORM]:
        return self.db.query(PaperStrategyEventORM).filter_by(deployment_id=deployment_id).order_by(
            PaperStrategyEventORM.sequence
        ).all()

    def intents(self, deployment_id: str) -> list[PaperStrategyIntentORM]:
        return self.db.query(PaperStrategyIntentORM).filter_by(deployment_id=deployment_id).order_by(
            PaperStrategyIntentORM.created_at, PaperStrategyIntentORM.ordinal
        ).all()
