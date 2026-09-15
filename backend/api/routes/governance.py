from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.deps import get_db
from backend.auth.deps import get_current_user
from backend.governance.domain import GovernanceStage
from backend.governance.service import GovernanceError, StrategyGovernanceService
from backend.models import ModelRun, User
from backend.oms.service import log_audit

router = APIRouter()


class RunMetaRequest(BaseModel):
    run_id: str
    data_version_id: str | None = None
    code_hash: str | None = None
    execution_profile: dict[str, Any] = Field(default_factory=dict)


class PromoteRequest(BaseModel):
    registry_name: str
    run_id: str
    stage: str = Field(default="staging", pattern="^(staging|prod)$")
    metadata: dict[str, Any] = Field(default_factory=dict)
    paper_run_id: str | None = None
    reconciliation_id: str | None = None
    reason: str = ""


class StrategyEvaluationRequest(BaseModel):
    baseline_run_id: str
    target_stage: str = Field(pattern="^(STAGING|PROD|staging|prod)$")
    paper_run_id: str | None = None
    reconciliation_id: str | None = None


class StrategyPromotionRequest(StrategyEvaluationRequest):
    reason: str
    registry_name: str | None = None


class RevokeRequest(BaseModel):
    reason: str


def _governance_error(exc: GovernanceError) -> HTTPException:
    status = 404 if exc.code in {
        "BASELINE_RUN_NOT_FOUND", "PAPER_RUN_NOT_FOUND", "RECONCILIATION_NOT_FOUND",
        "GOVERNANCE_RECORD_NOT_FOUND",
    } else 409
    return HTTPException(status_code=status, detail={"code": exc.code, "message": str(exc)})


@router.post("/governance/runs/register")
def register_run_meta(
    payload: RunMetaRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    row = db.query(ModelRun).filter(ModelRun.id == payload.run_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Model run not found")
    row.data_version_id = payload.data_version_id
    row.code_hash = payload.code_hash
    row.execution_profile_json = payload.execution_profile
    db.commit()
    log_audit(
        db=db,
        event_type="governance_run_registered",
        entity_type="model_run",
        entity_id=row.id,
        payload={"data_version_id": payload.data_version_id, "code_hash": payload.code_hash},
        user_id=current_user.id,
    )
    return {"status": "updated", "run_id": row.id}


@router.get("/governance/runs/compare")
def compare_runs(
    run_ids: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict[str, Any]:
    ids = [x.strip() for x in run_ids.split(",") if x.strip()]
    rows = db.query(ModelRun).filter(ModelRun.id.in_(ids)).all()
    return {
        "items": [
            {
                "id": row.id,
                "experiment_id": row.experiment_id,
                "status": row.status,
                "data_version_id": row.data_version_id,
                "code_hash": row.code_hash,
                "execution_profile": row.execution_profile_json if isinstance(row.execution_profile_json, dict) else {},
                "started_at": row.started_at,
                "finished_at": row.finished_at,
            }
            for row in rows
        ]
    }


@router.post("/governance/model-registry/promote")
def promote_model(
    payload: PromoteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    service = StrategyGovernanceService(db)
    try:
        model_run, simulation = service.resolve_legacy_model_run(payload.run_id)
        return service.promote(
            baseline_run_id=simulation.id,
            target_stage=GovernanceStage(payload.stage.upper()),
            actor_user_id=current_user.id,
            reason=payload.reason,
            paper_run_id=payload.paper_run_id,
            reconciliation_id=payload.reconciliation_id,
            registry_name=payload.registry_name,
            legacy_model_run_id=model_run.id,
        )
    except GovernanceError as exc:
        raise _governance_error(exc) from exc


@router.post("/governance/strategies/evaluate")
def evaluate_strategy(
    payload: StrategyEvaluationRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return StrategyGovernanceService(db).evaluate(
            baseline_run_id=payload.baseline_run_id,
            target_stage=payload.target_stage,
            paper_run_id=payload.paper_run_id,
            reconciliation_id=payload.reconciliation_id,
        ).as_dict()
    except GovernanceError as exc:
        raise _governance_error(exc) from exc


@router.post("/governance/strategies/promote")
def promote_strategy(
    payload: StrategyPromotionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return StrategyGovernanceService(db).promote(
            baseline_run_id=payload.baseline_run_id,
            target_stage=payload.target_stage,
            actor_user_id=current_user.id,
            reason=payload.reason,
            paper_run_id=payload.paper_run_id,
            reconciliation_id=payload.reconciliation_id,
            registry_name=payload.registry_name,
        )
    except GovernanceError as exc:
        raise _governance_error(exc) from exc


@router.get("/governance/strategies")
def list_strategies(
    stage: str | None = None,
    strategy_key: str | None = None,
    offset: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return {"items": StrategyGovernanceService(db).list(
            stage=stage, strategy_key=strategy_key, offset=max(0, offset), limit=min(max(1, limit), 200)
        )}
    except GovernanceError as exc:
        raise _governance_error(exc) from exc


@router.get("/governance/strategies/{record_id}")
def get_strategy(
    record_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return StrategyGovernanceService(db).get(record_id)
    except GovernanceError as exc:
        raise _governance_error(exc) from exc


@router.get("/governance/strategies/{record_id}/history")
def strategy_history(
    record_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return {"items": StrategyGovernanceService(db).history(record_id)}
    except GovernanceError as exc:
        raise _governance_error(exc) from exc


@router.post("/governance/strategies/{record_id}/revoke")
def revoke_strategy(
    record_id: str,
    payload: RevokeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return StrategyGovernanceService(db).revoke(
            record_id, actor_user_id=current_user.id, reason=payload.reason
        )
    except GovernanceError as exc:
        raise _governance_error(exc) from exc
