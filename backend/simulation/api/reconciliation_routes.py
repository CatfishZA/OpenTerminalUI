from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.simulation.api.routes import get_simulation_db
from backend.simulation.api.schemas import ReconciliationCreate
from backend.simulation.domain.reconciliation import BacktestPaperReconciliationSpec
from backend.simulation.services.backtest_paper_reconciliation_service import (
    BacktestPaperReconciliationError,
    BacktestPaperReconciliationService,
)

router = APIRouter(prefix="/api/v1/simulation", tags=["simulation-reconciliation"])


def service(db: Session = Depends(get_simulation_db)) -> BacktestPaperReconciliationService:
    return BacktestPaperReconciliationService(db)


def error_response(exc: BacktestPaperReconciliationError) -> HTTPException:
    not_found = exc.code in {"RECONCILIATION_NOT_FOUND", "BASELINE_RUN_NOT_FOUND", "PAPER_RUN_NOT_FOUND"}
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND if not_found else status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": exc.code, "message": str(exc)},
    )


@router.post("/reconciliations")
async def create_reconciliation(
    request: ReconciliationCreate,
    reconciliation: BacktestPaperReconciliationService = Depends(service),
) -> dict:
    try:
        report = await reconciliation.create(
            BacktestPaperReconciliationSpec(
                baseline_run_id=request.baseline_run_id,
                paper_run_id=request.paper_run_id,
                paper_cutoff_sequence=request.paper_cutoff_sequence,
                alignment_policy=request.alignment_policy,
                allow_research_baseline=request.allow_research_baseline,
                include_low_confidence_matches=request.include_low_confidence_matches,
            )
        )
    except BacktestPaperReconciliationError as exc:
        raise error_response(exc) from exc
    return {
        "reconciliation_id": report["reconciliation_id"],
        "status": report["status"],
        "baseline_run_id": report["baseline_run_id"],
        "paper_run_id": report["paper_run_id"],
        "paper_cutoff_sequence": report["paper_cutoff_sequence"],
        "report_hash": report["report_hash"],
    }


@router.get("/reconciliations/{reconciliation_id}")
def get_reconciliation(
    reconciliation_id: str,
    reconciliation: BacktestPaperReconciliationService = Depends(service),
) -> dict:
    try:
        return reconciliation.get(reconciliation_id)
    except BacktestPaperReconciliationError as exc:
        raise error_response(exc) from exc


@router.get("/reconciliations/{reconciliation_id}/items")
def reconciliation_items(
    reconciliation_id: str,
    item_type: str | None = None,
    match_status: str | None = None,
    instrument: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    reconciliation: BacktestPaperReconciliationService = Depends(service),
) -> dict:
    try:
        items = reconciliation.items(
            reconciliation_id,
            item_type=item_type,
            match_status=match_status,
            instrument=instrument,
            offset=offset,
            limit=limit,
        )
    except BacktestPaperReconciliationError as exc:
        raise error_response(exc) from exc
    return {"reconciliation_id": reconciliation_id, "items": items, "count": len(items), "offset": offset, "limit": limit}


@router.get("/runs/{run_id}/reconciliations")
def run_reconciliations(
    run_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    reconciliation: BacktestPaperReconciliationService = Depends(service),
) -> dict:
    try:
        items = reconciliation.list_for_run(run_id, offset=offset, limit=limit)
    except BacktestPaperReconciliationError as exc:
        raise error_response(exc) from exc
    return {"run_id": run_id, "items": items, "count": len(items), "offset": offset, "limit": limit}
