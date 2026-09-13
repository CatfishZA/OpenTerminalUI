from __future__ import annotations

from typing import Any
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.deps import get_db
from backend.auth.deps import get_current_user
from backend.models import (
    User,
    VirtualOrder,
    VirtualOrderStatus,
    VirtualPortfolio,
    VirtualPosition,
    VirtualTrade,
)
from backend.paper_trading import get_paper_engine
from backend.simulation.services.paper_simulation_service import PaperSimulationService
from backend.simulation.persistence.models import SimulationRunORM

router = APIRouter()


class PortfolioCreateRequest(BaseModel):
    name: str = "Paper Portfolio"
    initial_capital: Decimal = Field(gt=0)
    base_currency: str = "INR"
    settlement_days: int = Field(default=1, ge=0, le=2)


class OrderCreateRequest(BaseModel):
    portfolio_id: str
    symbol: str
    side: str
    order_type: str = "market"
    quantity: Decimal = Field(gt=0)
    limit_price: Decimal | None = None
    sl_price: Decimal | None = None
    slippage_bps: Decimal = Decimal("5")
    commission: Decimal = Decimal("0")


class DeployStrategyRequest(BaseModel):
    name: str = "Strategy Paper Portfolio"
    initial_capital: Decimal = Field(default=Decimal("100000"), gt=0)
    symbol: str
    market: str = "NSE"
    strategy: str
    context: dict[str, Any] = Field(default_factory=dict)


def _portfolio_for_user(db: Session, portfolio_id: str, user_id: str) -> VirtualPortfolio:
    row = db.query(VirtualPortfolio).filter(VirtualPortfolio.id == portfolio_id, VirtualPortfolio.user_id == user_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return row


def _engine_metadata(db: Session, row: VirtualPortfolio) -> dict[str, Any]:
    if not row.simulation_run_id:
        return {"simulation_run_id": None, "engine": "legacy"}
    run = db.get(SimulationRunORM, row.simulation_run_id)
    request = dict(run.request_json or {}) if run is not None else {}
    return {
        "simulation_run_id": row.simulation_run_id,
        "engine": "canonical",
        "mode": run.mode if run is not None else "PAPER",
        "verification_level": run.verification_level if run is not None else "RESEARCH",
        "engine_version": run.engine_version if run is not None else "sim-paper-v2a",
        "execution_profile": request.get("execution_profile", {}),
        "commission_profile": request.get("commission_profile", {}),
        "settlement_profile": request.get("settlement_profile", {}),
        "strategy_key": run.strategy_key if run is not None else None,
        "started_at": run.started_at.isoformat() if run is not None and run.started_at else None,
    }


@router.post("/paper/portfolios")
def create_virtual_portfolio(
    payload: PortfolioCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    row = PaperSimulationService(db).create_portfolio(
        user_id=current_user.id,
        name=payload.name,
        initial_cash=payload.initial_capital,
        base_currency=payload.base_currency,
        settlement_profile={"settlement_days": payload.settlement_days},
    )
    return {
        "id": row.id,
        "name": row.name,
        "initial_capital": row.initial_capital,
        "current_cash": row.current_cash,
        "settled_cash": row.current_cash,
        "unsettled_cash": 0.0,
        "buying_power": row.current_cash,
        **_engine_metadata(db, row),
    }


@router.get("/paper/portfolios")
def list_virtual_portfolios(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    rows = (
        db.query(VirtualPortfolio)
        .filter(VirtualPortfolio.user_id == current_user.id)
        .order_by(VirtualPortfolio.created_at.desc())
        .all()
    )
    return {
        "items": [
            {
                "id": row.id,
                "name": row.name,
                "initial_capital": row.initial_capital,
                "current_cash": row.current_cash,
                "is_active": row.is_active,
                "created_at": row.created_at.isoformat(),
                **_engine_metadata(db, row),
            }
            for row in rows
        ]
    }


@router.post("/paper/orders")
async def place_virtual_order(
    payload: OrderCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    portfolio = _portfolio_for_user(db, payload.portfolio_id, current_user.id)
    side = payload.side.strip().lower()
    if side not in {"buy", "sell"}:
        raise HTTPException(status_code=400, detail="side must be buy or sell")
    order_type = payload.order_type.strip().lower()
    if order_type not in {"market", "limit", "sl"}:
        raise HTTPException(status_code=400, detail="order_type must be market/limit/sl")
    if order_type == "limit" and payload.limit_price is None:
        raise HTTPException(status_code=400, detail="limit_price is required for limit orders")
    if order_type == "sl" and payload.sl_price is None:
        raise HTTPException(status_code=400, detail="sl_price is required for sl orders")
    symbol = payload.symbol.strip().upper()
    if ":" not in symbol:
        symbol = f"NSE:{symbol}"
    if portfolio.simulation_run_id:
        try:
            row = await PaperSimulationService(db).submit_order(
                portfolio=portfolio,
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=payload.quantity,
                limit_price=payload.limit_price,
                stop_price=payload.sl_price,
                slippage_bps=payload.slippage_bps,
                commission=payload.commission,
                cached_tick=get_paper_engine().cached_tick_for(symbol),
            )
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        metadata = dict(row.signal_metadata or {})
        return {
            "id": row.id,
            "status": row.status,
            "symbol": row.symbol,
            "fill_price": row.fill_price,
            "fill_time": row.fill_time.isoformat() if row.fill_time else None,
            "simulation_order_id": row.simulation_order_id,
            "canonical_status": metadata.get("canonical_status"),
            "remaining_quantity": metadata.get("remaining_quantity"),
        }
    row = VirtualOrder(
        portfolio_id=payload.portfolio_id,
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=float(payload.quantity),
        limit_price=float(payload.limit_price) if payload.limit_price is not None else None,
        sl_price=float(payload.sl_price) if payload.sl_price is not None else None,
        status=VirtualOrderStatus.PENDING.value,
        slippage_bps=float(payload.slippage_bps),
        commission=float(payload.commission),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    await get_paper_engine().maybe_fill_market_order_now(db, row)
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "status": row.status,
        "symbol": row.symbol,
        "fill_price": row.fill_price,
        "fill_time": row.fill_time.isoformat() if row.fill_time else None,
    }


@router.get("/paper/portfolios/{portfolio_id}/positions")
async def get_positions(
    portfolio_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    portfolio = _portfolio_for_user(db, portfolio_id, current_user.id)
    canonical_account = None
    if portfolio.simulation_run_id:
        canonical_account = await PaperSimulationService(db).current_account(portfolio)
    rows = db.query(VirtualPosition).filter(VirtualPosition.portfolio_id == portfolio_id).all()
    mark_map = get_paper_engine()._mark_prices
    items = []
    for row in rows:
        mark = mark_map.get(row.symbol, row.avg_entry_price)
        unrealized = (mark - row.avg_entry_price) * row.quantity
        if canonical_account is not None:
            try:
                from backend.simulation.adapters.live_tick_adapter import instrument_from_legacy_symbol
                position = canonical_account.positions.get(instrument_from_legacy_symbol(row.symbol))
                if position is not None:
                    mark = float(position.last_mark or position.average_cost)
                    unrealized = float(position.unrealized_pnl)
            except ValueError:
                pass
        items.append(
            {
                "id": row.id,
                "symbol": row.symbol,
                "quantity": row.quantity,
                "avg_entry_price": row.avg_entry_price,
                "mark_price": mark,
                "unrealized_pnl": unrealized,
            }
        )
    return {"items": items}


@router.get("/paper/portfolios/{portfolio_id}/orders")
def get_orders(
    portfolio_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _portfolio_for_user(db, portfolio_id, current_user.id)
    rows = (
        db.query(VirtualOrder)
        .filter(VirtualOrder.portfolio_id == portfolio_id)
        .order_by(VirtualOrder.created_at.desc())
        .all()
    )
    return {
        "items": [
            {
                "id": row.id,
                "symbol": row.symbol,
                "side": row.side,
                "order_type": row.order_type,
                "quantity": row.quantity,
                "limit_price": row.limit_price,
                "sl_price": row.sl_price,
                "status": row.status,
                "fill_price": row.fill_price,
                "fill_time": row.fill_time.isoformat() if row.fill_time else None,
                "slippage_bps": row.slippage_bps,
                "commission": row.commission,
                "simulation_order_id": row.simulation_order_id,
                "canonical_status": (row.signal_metadata or {}).get("canonical_status"),
                "remaining_quantity": (row.signal_metadata or {}).get("remaining_quantity"),
            }
            for row in rows
        ]
    }


@router.get("/paper/portfolios/{portfolio_id}/trades")
def get_trades(
    portfolio_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _portfolio_for_user(db, portfolio_id, current_user.id)
    rows = (
        db.query(VirtualTrade)
        .filter(VirtualTrade.portfolio_id == portfolio_id)
        .order_by(VirtualTrade.timestamp.desc())
        .all()
    )
    return {
        "items": [
            {
                "id": row.id,
                "order_id": row.order_id,
                "symbol": row.symbol,
                "side": row.side,
                "quantity": row.quantity,
                "price": row.price,
                "timestamp": row.timestamp.isoformat(),
                "pnl_realized": row.pnl_realized,
                "simulation_fill_id": row.simulation_fill_id,
            }
            for row in rows
        ]
    }


@router.get("/paper/portfolios/{portfolio_id}/performance")
async def get_performance(
    portfolio_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    portfolio = _portfolio_for_user(db, portfolio_id, current_user.id)
    metrics = (
        await PaperSimulationService(db).performance(portfolio)
        if portfolio.simulation_run_id
        else get_paper_engine().portfolio_performance(db, portfolio_id)
    )
    if not metrics:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return metrics


@router.post("/paper/deploy-strategy")
def deploy_strategy(
    payload: DeployStrategyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    portfolio = PaperSimulationService(db).create_portfolio(
        user_id=current_user.id,
        name=payload.name.strip() or "Strategy Paper Portfolio",
        initial_cash=payload.initial_capital,
        base_currency="INR" if payload.market.strip().upper() in {"NSE", "BSE"} else "USD",
        strategy_key=payload.strategy,
        strategy_context={**payload.context, "symbol": payload.symbol, "market": payload.market},
    )
    return {"portfolio_id": portfolio.id, "status": "deployed", "simulation_run_id": portfolio.simulation_run_id}


@router.post("/paper/orders/{order_id}/cancel")
async def cancel_virtual_order(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    row = db.get(VirtualOrder, order_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Order not found")
    portfolio = _portfolio_for_user(db, row.portfolio_id, current_user.id)
    if not portfolio.simulation_run_id:
        if row.status != VirtualOrderStatus.PENDING.value:
            raise HTTPException(status_code=400, detail="terminal order cannot be cancelled")
        row.status = VirtualOrderStatus.CANCELLED.value
        db.commit()
        return {"id": row.id, "status": row.status}
    try:
        row = await PaperSimulationService(db).cancel_order(portfolio, row)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "id": row.id,
        "status": row.status,
        "canonical_status": (row.signal_metadata or {}).get("canonical_status"),
    }
