from __future__ import annotations

from typing import Any, Generator

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from backend.shared.db import SessionLocal
from backend.simulation.api.schemas import (
    CollectionResponse,
    SimulationManifestResponse,
    SimulationRunCreate,
    SimulationRunCreated,
    SimulationResultResponse,
    SimulationStatusResponse,
)
from backend.simulation.domain.identifiers import InstrumentId
from backend.simulation.domain.run import SimulationRunSpec
from backend.simulation.persistence.serializers import to_primitive
from backend.simulation.services.simulation_service import SimulationNotFoundError, SimulationService

router = APIRouter(prefix="/api/v1/simulation", tags=["simulation"])


def get_simulation_db() -> Generator[Session, None, None]:
    """Local lightweight DB dependency keeps the canonical API independently importable."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_simulation_service(db: Session = Depends(get_simulation_db)) -> SimulationService:
    return SimulationService(db)


def _instrument(value) -> InstrumentId:  # noqa: ANN001
    return InstrumentId(
        symbol=value.symbol,
        venue=value.venue,
        asset_class=value.asset_class,
        currency=value.currency,
    )


def _to_spec(request: SimulationRunCreate) -> SimulationRunSpec:
    return SimulationRunSpec(
        mode=request.mode,
        verification_level=request.verification_level,
        strategy=request.strategy.key,
        strategy_context=request.strategy.context,
        universe=tuple(_instrument(item) for item in request.universe),
        start=request.start,
        end=request.end,
        initial_cash=request.account.initial_cash,
        base_currency=request.account.base_currency,
        data_version_id=request.data_version_id,
        execution_profile=request.execution.model_dump(mode="python"),
        commission_profile=request.commission.model_dump(mode="python"),
        settlement_profile={"settlement_days": request.account.settlement_days},
        seed=request.seed,
        benchmark=_instrument(request.benchmark) if request.benchmark else None,
    )


def _orm_dict(row: Any) -> dict[str, Any]:
    return to_primitive({column.key: getattr(row, column.key) for column in inspect(row).mapper.column_attrs})


def _not_found(exc: SimulationNotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "SIMULATION_RUN_NOT_FOUND", "run_id": str(exc)})


@router.post("/runs", response_model=SimulationRunCreated, status_code=status.HTTP_202_ACCEPTED)
async def create_run(
    request: SimulationRunCreate,
    service: SimulationService = Depends(get_simulation_service),
) -> SimulationRunCreated:
    try:
        run_id = await service.submit(_to_spec(request))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return SimulationRunCreated(run_id=run_id, status="queued", verification_level=request.verification_level)


@router.get("/runs/{run_id}/status", response_model=SimulationStatusResponse)
async def run_status(run_id: str, service: SimulationService = Depends(get_simulation_service)) -> SimulationStatusResponse:
    try:
        current = await service.status(run_id)
    except SimulationNotFoundError as exc:
        raise _not_found(exc) from exc
    return SimulationStatusResponse(
        run_id=current.run_id,
        status=current.status.value.lower(),
        progress=current.progress,
        stage=current.stage,
        error=current.error,
    )


@router.get("/runs/{run_id}", response_model=SimulationResultResponse)
async def run_result(run_id: str, service: SimulationService = Depends(get_simulation_service)) -> SimulationResultResponse:
    try:
        return SimulationResultResponse(**(await service.result(run_id)))
    except SimulationNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get("/runs/{run_id}/manifest", response_model=SimulationManifestResponse)
async def run_manifest(run_id: str, service: SimulationService = Depends(get_simulation_service)) -> dict[str, Any]:
    try:
        return to_primitive(await service.manifest(run_id))
    except SimulationNotFoundError as exc:
        raise _not_found(exc) from exc


async def _collection(run_id: str, call) -> CollectionResponse:  # noqa: ANN001
    try:
        rows = await call()
    except SimulationNotFoundError as exc:
        raise _not_found(exc) from exc
    items = [_orm_dict(row) for row in rows]
    return CollectionResponse(run_id=run_id, items=items, count=len(items))


@router.get("/runs/{run_id}/orders", response_model=CollectionResponse)
async def run_orders(run_id: str, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000), service: SimulationService = Depends(get_simulation_service)) -> CollectionResponse:
    return await _collection(run_id, lambda: service.orders(run_id, offset=offset, limit=limit))


@router.get("/runs/{run_id}/fills", response_model=CollectionResponse)
async def run_fills(run_id: str, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000), service: SimulationService = Depends(get_simulation_service)) -> CollectionResponse:
    return await _collection(run_id, lambda: service.fills(run_id, offset=offset, limit=limit))


@router.get("/runs/{run_id}/ledger", response_model=CollectionResponse)
async def run_ledger(run_id: str, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000), service: SimulationService = Depends(get_simulation_service)) -> CollectionResponse:
    return await _collection(run_id, lambda: service.ledger(run_id, offset=offset, limit=limit))


@router.get("/runs/{run_id}/events", response_model=CollectionResponse)
async def run_events(
    run_id: str,
    from_sequence: int | None = Query(None, ge=0),
    to_sequence: int | None = Query(None, ge=0),
    event_type: str | None = None,
    instrument: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    service: SimulationService = Depends(get_simulation_service),
) -> CollectionResponse:
    if from_sequence is not None and to_sequence is not None and to_sequence < from_sequence:
        raise HTTPException(status_code=422, detail="to_sequence must not precede from_sequence")
    return await _collection(
        run_id,
        lambda: service.events(
            run_id,
            from_sequence=from_sequence,
            to_sequence=to_sequence,
            event_type=event_type,
            instrument=instrument,
            limit=limit,
        ),
    )


@router.get("/runs/{run_id}/portfolio", response_model=CollectionResponse)
async def run_portfolio(run_id: str, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000), service: SimulationService = Depends(get_simulation_service)) -> CollectionResponse:
    return await _collection(run_id, lambda: service.portfolio(run_id, offset=offset, limit=limit))


@router.get("/runs/{run_id}/positions", response_model=CollectionResponse)
async def run_positions(run_id: str, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000), service: SimulationService = Depends(get_simulation_service)) -> CollectionResponse:
    return await _collection(run_id, lambda: service.positions(run_id, offset=offset, limit=limit))
