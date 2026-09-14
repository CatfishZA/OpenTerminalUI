from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.simulation.api.routes import _instrument, get_simulation_db
from backend.simulation.api.schemas import ReplayAdvance, ReplayCreate, ReplayRunTo, ReplayStateResponse
from backend.simulation.domain.enums import SimulationMode
from backend.simulation.domain.identifiers import InstrumentId
from backend.simulation.domain.run import SimulationRunSpec
from backend.simulation.services.replay_simulation_service import ReplaySimulationError, ReplaySimulationService

router = APIRouter(prefix="/api/v1/simulation/replays", tags=["simulation-replay"])


def get_replay_service(db: Session = Depends(get_simulation_db)) -> ReplaySimulationService:
    return ReplaySimulationService(db)


def _spec(request: ReplayCreate) -> SimulationRunSpec:
    execution = {key: value for key, value in request.execution.model_dump(mode="python").items() if value is not None}
    commission = {key: value for key, value in request.commission.model_dump(mode="python").items() if value is not None}
    return SimulationRunSpec(
        mode=SimulationMode.REPLAY, verification_level=request.verification_level,
        strategy=request.strategy.key, strategy_context=request.strategy.context,
        universe=tuple(_instrument(item) for item in request.universe),
        start=request.start, end=request.end, initial_cash=request.account.initial_cash,
        base_currency=request.account.base_currency, data_version_id=request.data_version_id,
        execution_profile=execution,
        commission_profile=commission,
        settlement_profile={"settlement_days": request.account.settlement_days}, seed=request.seed,
        benchmark=_instrument(request.benchmark) if request.benchmark else None,
    )


def _response(value) -> ReplayStateResponse:  # noqa: ANN001
    return ReplayStateResponse(
        run_id=value.run_id, status=value.status.value, current_session=value.current_session,
        next_session=value.next_session, completed_sessions=value.completed_sessions,
        total_sessions=value.total_sessions, current_time=value.current_time,
        last_event_sequence=value.last_event_sequence, progress=value.progress,
        checkpoint_hash=value.checkpoint_hash,
    )


def _error(exc: ReplaySimulationError) -> HTTPException:
    not_found = exc.code == "REPLAY_RUN_NOT_FOUND"
    conflict = exc.code in {"REPLAY_ALREADY_DONE", "REPLAY_CANCELLED", "REPLAY_FAILED", "REPLAY_SESSION_CONFLICT"}
    code = status.HTTP_404_NOT_FOUND if not_found else status.HTTP_409_CONFLICT if conflict else status.HTTP_422_UNPROCESSABLE_ENTITY
    return HTTPException(status_code=code, detail={"code": exc.code, "message": str(exc)})


@router.post("", response_model=ReplayStateResponse, status_code=status.HTTP_201_CREATED)
async def create_replay(request: ReplayCreate, service: ReplaySimulationService = Depends(get_replay_service)) -> ReplayStateResponse:
    try:
        run_id = await service.create(_spec(request))
        return _response(await service.state(run_id))
    except ReplaySimulationError as exc:
        raise _error(exc) from exc


@router.get("/{run_id}", response_model=ReplayStateResponse)
async def replay_state(run_id: str, service: ReplaySimulationService = Depends(get_replay_service)) -> ReplayStateResponse:
    try:
        return _response(await service.state(run_id))
    except ReplaySimulationError as exc:
        raise _error(exc) from exc


@router.post("/{run_id}/advance", response_model=ReplayStateResponse)
async def advance_replay(run_id: str, request: ReplayAdvance, service: ReplaySimulationService = Depends(get_replay_service)) -> ReplayStateResponse:
    try:
        return _response(await service.advance(run_id, sessions=request.sessions))
    except ReplaySimulationError as exc:
        raise _error(exc) from exc


@router.post("/{run_id}/run-to", response_model=ReplayStateResponse)
async def run_replay_to(run_id: str, request: ReplayRunTo, service: ReplaySimulationService = Depends(get_replay_service)) -> ReplayStateResponse:
    try:
        return _response(await service.run_to(run_id, target_session=request.target_session))
    except ReplaySimulationError as exc:
        raise _error(exc) from exc


@router.post("/{run_id}/run-to-end", response_model=ReplayStateResponse)
async def run_replay_to_end(run_id: str, service: ReplaySimulationService = Depends(get_replay_service)) -> ReplayStateResponse:
    try:
        return _response(await service.run_to_end(run_id))
    except ReplaySimulationError as exc:
        raise _error(exc) from exc


@router.post("/{run_id}/cancel", response_model=ReplayStateResponse)
async def cancel_replay(run_id: str, service: ReplaySimulationService = Depends(get_replay_service)) -> ReplayStateResponse:
    try:
        return _response(await service.cancel(run_id))
    except ReplaySimulationError as exc:
        raise _error(exc) from exc


@router.get("/{run_id}/market")
async def replay_market(
    run_id: str, instrument: str, limit: int = Query(100, ge=1, le=1000),
    service: ReplaySimulationService = Depends(get_replay_service),
) -> dict:
    try:
        bars = await service.market(run_id, InstrumentId.parse(instrument), limit=limit)
        return {"run_id": run_id, "instrument": instrument, "items": bars, "count": len(bars)}
    except ReplaySimulationError as exc:
        raise _error(exc) from exc
