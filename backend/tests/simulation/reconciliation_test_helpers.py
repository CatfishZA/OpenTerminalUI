from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backend.simulation.persistence.models import (
    SimulationEventORM,
    SimulationFillORM,
    SimulationOrderORM,
    SimulationPortfolioSnapshotORM,
    SimulationRunORM,
)

NOW = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
INSTRUMENT = "NSE:EQUITY:ABC:INR"


def run(db, run_id: str, *, mode: str, verification: str = "VERIFIED", status: str = "DONE", currency: str = "INR", strategy: str = "strategy:test", settlement_days: int = 1):  # noqa: ANN001
    row = SimulationRunORM(
        id=run_id,
        mode=mode,
        verification_level=verification,
        status=status,
        strategy_key=strategy,
        strategy_hash=f"hash:{strategy}",
        engine_version="fixture",
        seed=42,
        request_json={
            "initial_cash": "10000",
            "base_currency": currency,
            "execution_profile": {"model": "fixed_bps", "slippage_bps": "0", "max_participation": "1"},
            "commission_profile": {"model": "bps", "bps": "0"},
            "settlement_profile": {"settlement_days": settlement_days},
        },
        manifest_json={"manifest_hash": f"manifest:{run_id}"},
        result_hash=f"result:{run_id}" if mode == "BACKTEST" else None,
        created_at=NOW,
        started_at=NOW,
        finished_at=NOW + timedelta(hours=1) if status == "DONE" else None,
    )
    db.add(row)
    db.flush()
    return row


def order(db, run_id: str, order_id: str, *, quantity: str = "10", remaining: str = "0", status: str = "FILLED", submitted_at=NOW, key: str | None = None, strategy_order_id: str | None = None, instrument: str = INSTRUMENT, side: str = "BUY", order_type: str = "MARKET", limit_price: str | None = None):  # noqa: ANN001
    row = SimulationOrderORM(
        id=order_id,
        run_id=run_id,
        account_id=f"acct:{run_id}",
        instrument_key=instrument,
        side=side,
        order_type=order_type,
        quantity=Decimal(quantity),
        remaining_quantity=Decimal(remaining),
        tif="GTC",
        limit_price=Decimal(limit_price) if limit_price else None,
        stop_price=None,
        status=status,
        submitted_at=submitted_at,
        accepted_at=submitted_at,
        completed_at=submitted_at + timedelta(seconds=1) if status == "FILLED" else None,
        strategy_order_id=strategy_order_id,
        metadata_json={"reconciliation_key": key} if key else {},
    )
    db.add(row)
    db.flush()
    return row


def fill(db, run_id: str, order_id: str, fill_id: str, *, quantity: str = "10", price: str = "100", commission: str = "0", fees: str = "0", slippage: str = "0", at=NOW):  # noqa: ANN001
    row = SimulationFillORM(
        id=fill_id,
        run_id=run_id,
        order_id=order_id,
        account_id=f"acct:{run_id}",
        instrument_key=INSTRUMENT,
        side="BUY",
        quantity=Decimal(quantity),
        price=Decimal(price),
        commission=Decimal(commission),
        fees=Decimal(fees),
        slippage_bps=Decimal(slippage),
        executed_at=at,
        execution_model="fixture",
        metadata_json={},
    )
    db.add(row)
    db.flush()
    return row


def paper_events(db, run_id: str, order_id: str, fill_ids: list[str], *, start_sequence: int = 1):  # noqa: ANN001
    sequence = start_sequence
    for event_type, fill_id in [("ORDER_SUBMITTED", None), ("ORDER_ACCEPTED", None), *[("ORDER_FILL", item) for item in fill_ids]]:
        db.add(
            SimulationEventORM(
                run_id=run_id,
                sequence=sequence,
                event_id=f"evt:{run_id}:{sequence}",
                event_type=event_type,
                event_time=NOW + timedelta(seconds=sequence),
                processing_time=NOW + timedelta(seconds=sequence),
                instrument_key=INSTRUMENT,
                order_id=order_id,
                fill_id=fill_id,
                payload_json={},
            )
        )
        sequence += 1
    db.flush()
    return sequence - 1


def snapshot(db, run_id: str, *, at=NOW, equity: str = "10000"):  # noqa: ANN001
    db.add(
        SimulationPortfolioSnapshotORM(
            run_id=run_id,
            account_id=f"acct:{run_id}",
            snapshot_time=at,
            cash_settled=Decimal(equity),
            cash_unsettled=Decimal("0"),
            cash_reserved=Decimal("0"),
            gross_exposure=Decimal("0"),
            net_exposure=Decimal("0"),
            market_value=Decimal("0"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            fees=Decimal("0"),
            equity=Decimal(equity),
            buying_power=Decimal(equity),
        )
    )
    db.flush()


def canonical_pair(db, *, baseline_verification: str = "VERIFIED", baseline_currency: str = "INR", paper_currency: str = "INR", key: str | None = "intent-1", baseline_settlement: int = 1, paper_settlement: int = 1):  # noqa: ANN001
    baseline = run(db, "sim_baseline", mode="BACKTEST", verification=baseline_verification, currency=baseline_currency, settlement_days=baseline_settlement)
    paper = run(db, "sim_paper", mode="PAPER", verification="RESEARCH", status="RUNNING", currency=paper_currency, settlement_days=paper_settlement)
    order(db, baseline.id, "ord_baseline", key=key)
    fill(db, baseline.id, "ord_baseline", "fill_baseline")
    order(db, paper.id, "ord_paper", key=key)
    fill(db, paper.id, "ord_paper", "fill_paper", at=NOW + timedelta(seconds=3))
    cutoff = paper_events(db, paper.id, "ord_paper", ["fill_paper"])
    snapshot(db, baseline.id)
    snapshot(db, paper.id, at=NOW + timedelta(seconds=3))
    db.commit()
    return baseline, paper, cutoff
