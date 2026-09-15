from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backend.models import DataVersionORM, User
from backend.models.user import UserRole
from backend.simulation.persistence.models import (
    SimulationFillORM,
    SimulationLedgerEntryORM,
    SimulationOrderORM,
    SimulationPortfolioSnapshotORM,
    SimulationPositionSnapshotORM,
    SimulationReconciliationItemORM,
    SimulationReconciliationORM,
    SimulationRunORM,
)

NOW = datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)
INSTRUMENT = "NSE:EQUITY:ABC:INR"


def seed_actor(db, user_id: str = "actor-1") -> User:  # noqa: ANN001
    actor = User(id=user_id, email=f"{user_id}@example.com", hashed_password="x", role=UserRole.ADMIN)
    db.add(actor)
    db.flush()
    return actor


def seed_baseline(
    db,  # noqa: ANN001
    *,
    run_id: str = "sim_baseline",
    strategy_hash: str = "strategy-hash-a",
    mode: str = "BACKTEST",
    verification: str = "VERIFIED",
    status: str = "DONE",
    code_hash: str | None = "code-hash-a",
    result_hash: str | None = "result-hash-a",
    manifest_hash: str | None = "manifest-hash-a",
    data_status: str = "VALID",
    accounting: bool = True,
    with_order: bool = True,
) -> SimulationRunORM:
    if db.get(DataVersionORM, "version-a") is None:
        db.add(DataVersionORM(id="version-a", name="version-a", source="fixture", is_active=True, metadata_json={}))
        db.flush()
    result = {
        "data_quality": {
            "status": data_status,
            "errors": [] if data_status == "VALID" else [{"code": "INVALID_OHLC"}],
            "warnings": [],
            "integrity_report_hash": "integrity-hash-a",
            "corporate_actions": {"applied": 0},
            "legacy_assumptions": [],
        },
        "reconciliation": {"cash": accounting, "positions": accounting, "equity": accounting},
        "summary": {"total_return": "-0.10"},
    }
    run = SimulationRunORM(
        id=run_id, mode=mode, verification_level=verification, status=status,
        strategy_key="fixture:sma", strategy_hash=strategy_hash, code_hash=code_hash,
        data_version_id="version-a", engine_version="fixture-engine", seed=42,
        request_json={"initial_cash": "10000", "base_currency": "INR"},
        manifest_json={"manifest_hash": manifest_hash} if manifest_hash else {},
        result_json=result, result_hash=result_hash, error="", created_at=NOW,
        started_at=NOW, finished_at=NOW + timedelta(hours=1),
    )
    db.add(run)
    db.flush()
    db.add(SimulationLedgerEntryORM(
        id=f"led_{run_id}_opening", run_id=run_id, account_id=f"acct_{run_id}",
        event_time=NOW, entry_type="CASH_DEPOSIT", currency="INR", amount=Decimal("10000"),
        metadata_json={"opening_balance": True},
    ))
    cash = Decimal("10000")
    market_value = Decimal("0")
    if with_order:
        order_id = f"ord_{run_id}"
        fill_id = f"fill_{run_id}"
        db.add(SimulationOrderORM(
            id=order_id, run_id=run_id, account_id=f"acct_{run_id}", instrument_key=INSTRUMENT,
            side="BUY", order_type="MARKET", quantity=Decimal("10"), remaining_quantity=Decimal("0"),
            tif="GTC", status="FILLED", submitted_at=NOW, accepted_at=NOW,
            completed_at=NOW + timedelta(seconds=1), metadata_json={"reconciliation_key": "intent-1"},
        ))
        db.add(SimulationFillORM(
            id=fill_id, run_id=run_id, order_id=order_id, account_id=f"acct_{run_id}",
            instrument_key=INSTRUMENT, side="BUY", quantity=Decimal("10"), price=Decimal("100"),
            commission=Decimal("0"), fees=Decimal("0"), slippage_bps=Decimal("0"),
            executed_at=NOW + timedelta(seconds=1), execution_model="fixture", metadata_json={},
        ))
        db.add(SimulationLedgerEntryORM(
            id=f"led_{run_id}_trade", run_id=run_id, account_id=f"acct_{run_id}",
            event_time=NOW + timedelta(seconds=1), entry_type="TRADE_PRINCIPAL", currency="INR",
            amount=Decimal("-1000"), instrument_key=INSTRUMENT, order_id=order_id,
            fill_id=fill_id, metadata_json={},
        ))
        cash = Decimal("9000")
        market_value = Decimal("1000")
        db.add(SimulationPositionSnapshotORM(
            run_id=run_id, account_id=f"acct_{run_id}", snapshot_time=NOW + timedelta(hours=1),
            instrument_key=INSTRUMENT, quantity=Decimal("10"), average_cost=Decimal("100"),
            mark_price=Decimal("100"), market_value=market_value,
            realized_pnl=Decimal("0"), unrealized_pnl=Decimal("0"),
        ))
    db.add(SimulationPortfolioSnapshotORM(
        run_id=run_id, account_id=f"acct_{run_id}", snapshot_time=NOW + timedelta(hours=1),
        cash_settled=cash, cash_unsettled=Decimal("0"), cash_reserved=Decimal("0"),
        gross_exposure=market_value, net_exposure=market_value, market_value=market_value,
        realized_pnl=Decimal("0"), unrealized_pnl=Decimal("0"), fees=Decimal("0"),
        equity=cash + market_value, buying_power=cash,
    ))
    db.flush()
    return run


def seed_paper(db, baseline: SimulationRunORM, *, run_id: str = "sim_paper", strategy_hash: str | None = None) -> SimulationRunORM:  # noqa: ANN001
    paper = SimulationRunORM(
        id=run_id, mode="PAPER", verification_level="RESEARCH", status="RUNNING",
        strategy_key=baseline.strategy_key, strategy_hash=strategy_hash or baseline.strategy_hash,
        code_hash=baseline.code_hash, data_version_id=None, engine_version="paper-fixture", seed=42,
        request_json={"initial_cash": "10000", "base_currency": "INR"},
        manifest_json={"manifest_hash": f"manifest-{run_id}"}, error="", created_at=NOW,
        started_at=NOW,
    )
    db.add(paper)
    db.flush()
    order_id = f"ord_{run_id}"
    fill_id = f"fill_{run_id}"
    db.add(SimulationOrderORM(
        id=order_id, run_id=run_id, account_id=f"acct_{run_id}", instrument_key=INSTRUMENT,
        side="BUY", order_type="MARKET", quantity=Decimal("10"), remaining_quantity=Decimal("0"),
        tif="GTC", status="FILLED", submitted_at=NOW, accepted_at=NOW,
        completed_at=NOW + timedelta(seconds=1), metadata_json={"reconciliation_key": "intent-1"},
    ))
    db.add(SimulationFillORM(
        id=fill_id, run_id=run_id, order_id=order_id, account_id=f"acct_{run_id}",
        instrument_key=INSTRUMENT, side="BUY", quantity=Decimal("10"), price=Decimal("101"),
        commission=Decimal("0"), fees=Decimal("0"), slippage_bps=Decimal("0"),
        executed_at=NOW + timedelta(seconds=1), execution_model="simulated-paper", metadata_json={},
    ))
    db.flush()
    return paper


def seed_reconciliation(
    db, baseline: SimulationRunORM, paper: SimulationRunORM,  # noqa: ANN001
    *, reconciliation_id: str = "rec_valid", intent: bool = True, accounting: bool = True,
    ambiguous: int = 0, low: int = 0, baseline_only: int = 0, paper_only: int = 0,
    matched: int = 1, paper_fills: int = 1, status: str = "DONE",
) -> SimulationReconciliationORM:
    counts = {
        "MATCHED": matched, "AMBIGUOUS": ambiguous,
        "BASELINE_ONLY": baseline_only, "PAPER_ONLY": paper_only,
    }
    row = SimulationReconciliationORM(
        id=reconciliation_id, baseline_run_id=baseline.id, paper_run_id=paper.id,
        status=status, alignment_policy="KEYED_THEN_SIGNATURE", allow_research_baseline=False,
        include_low_confidence=True, paper_cutoff_sequence=3, paper_cutoff_time=NOW,
        baseline_manifest_hash=baseline.manifest_json["manifest_hash"],
        baseline_result_hash=baseline.result_hash,
        paper_manifest_hash=paper.manifest_json["manifest_hash"],
        request_hash=f"request-{reconciliation_id}", report_hash=f"report-{reconciliation_id}",
        compatibility_json={
            "strategy_identity": "EXACT", "intent_comparable": intent,
            "accounting_comparable": accounting, "performance_comparable": False,
        },
        summary_json={"match_counts": counts, "paper_account": {"fill_count": paper_fills}},
        calibration_json={"automatic_tuning": False}, report_json={}, error="",
        created_at=NOW, completed_at=NOW,
    )
    db.add(row)
    db.flush()
    for sequence in range(low):
        db.add(SimulationReconciliationItemORM(
            reconciliation_id=row.id, sequence=sequence + 1, item_type="ORDER",
            match_status="MATCHED", match_basis="ORDINAL_FALLBACK", match_confidence="LOW",
            divergence_codes_json=[], metrics_json={},
        ))
    db.flush()
    return row
