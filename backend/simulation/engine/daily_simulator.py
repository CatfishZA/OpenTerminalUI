from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from backend.simulation.domain.account import AccountState
from backend.simulation.domain.cash import CashBalance
from backend.simulation.domain.enums import LedgerEntryType
from backend.simulation.domain.events import LedgerEntry
from backend.simulation.domain.results import SimulationResult
from backend.simulation.domain.run import RunManifest, SimulationRunSpec
from backend.simulation.engine.daily_session_kernel import DailySessionKernel, DailySessionState
from backend.simulation.engine.result_builder import ResultBuilder
from backend.simulation.services.manifest_service import ManifestService, sha256_value
from backend.simulation.services.reconciliation_service import ReconciliationService


@dataclass(slots=True)
class DailySimulatorDependencies:
    market_data: Any
    corporate_actions: Any
    strategy: Any
    execution: Any
    commission: Any
    event_store: Any
    ledger: Any
    records: Any | None = None


class DailySimulator:
    """Deterministic long-only daily cash-equity batch orchestrator."""

    def __init__(self, dependencies: DailySimulatorDependencies):
        self.d = dependencies

    def run(self, spec: SimulationRunSpec, *, run_id: str | None = None, manifest: RunManifest | None = None) -> SimulationResult:
        data_manifest = self.d.market_data.manifest()
        bars = list(self.d.market_data.iter_daily_events(list(spec.universe), spec.start, spec.end))
        self._validate(spec, bars)
        run_id = run_id or f"sim_{sha256_value(spec)[:12]}"
        manifest = manifest or ManifestService(engine_version="sim-daily-v1b").build(
            run_id, spec, dataset_hash=data_manifest.dataset_hash,
            calendar_version=data_manifest.calendar_version, created_at=min(item.ts_open for item in bars),
        )
        result = ResultBuilder(run_id, manifest)
        account = AccountState(
            f"acct_{run_id[4:]}", spec.base_currency,
            cash={spec.base_currency: CashBalance(spec.base_currency, settled=spec.initial_cash)},
            equity=spec.initial_cash, buying_power=spec.initial_cash,
        )
        history = {instrument: [] for instrument in spec.universe}
        bars_by_session = {}
        for bar in bars:
            bars_by_session.setdefault(bar.ts_open.date(), {})[bar.instrument] = bar
        sessions = sorted(bars_by_session)
        opening = LedgerEntry(
            f"led_{run_id}_opening", run_id, account.account_id, min(item.ts_open for item in bars),
            LedgerEntryType.CASH_DEPOSIT, spec.base_currency, spec.initial_cash,
            metadata={"opening_balance": True},
        )
        result.ledger.append(opening)
        self.d.ledger.append(opening)
        state = DailySessionState(
            run_id, spec, account, result, history, {}, sessions, bars_by_session,
        )
        kernel = DailySessionKernel(self.d, state)
        kernel.start(min(item.ts_open for item in bars))
        for index in range(len(sessions)):
            kernel.process_session(index)
        last = max(bars_by_session[sessions[-1]].values(), key=lambda item: item.ts_close)
        kernel.finish(last.ts_close)
        reconciliation = ReconciliationService().reconcile(spec.initial_cash, result.ledger, result.fills, account)
        summary = {
            "status": "DONE", "initial_cash": spec.initial_cash, "final_equity": account.equity,
            "ending_cash": account.base_cash.total, "realized_pnl": account.realized_pnl,
            "unrealized_pnl": account.unrealized_pnl,
            "total_return": account.equity / spec.initial_cash - Decimal(1),
            "daily_bar_path_policy": spec.execution_profile.get("daily_bar_path_policy", "WORST_CASE"),
        }
        result_hash = sha256_value({
            "events": result.events, "orders": result.orders, "fills": result.fills,
            "ledger": result.ledger, "portfolio": result.portfolio_snapshots,
            "positions": result.position_snapshots, "summary": summary,
        })
        return result.build(summary, data_quality={"status": "VALID"}, reconciliation=reconciliation, result_hash=result_hash)

    @staticmethod
    def _validate(spec, bars):  # noqa: ANN001
        grouped = {instrument: [] for instrument in spec.universe}
        for bar in bars:
            if bar.instrument not in grouped:
                raise ValueError(f"INSTRUMENT_DATA_NOT_FOUND: {bar.instrument.key}")
            if spec.data_version_id and bar.data_version_id != spec.data_version_id:
                raise ValueError("VERIFIED_DATA_MISSING: data version mismatch")
            grouped[bar.instrument].append(bar)
        for instrument, values in grouped.items():
            if not values:
                raise ValueError(f"INSTRUMENT_DATA_NOT_FOUND: {instrument.key}")
            if values != sorted(values, key=lambda item: item.ts_open):
                raise ValueError("VERIFIED_DATA_MISSING: sessions are not monotonic")
            if len({item.ts_open.date() for item in values}) != len(values):
                raise ValueError("DUPLICATE_BAR")
        if spec.verification_level.value == "VERIFIED":
            expected = sorted({bar.ts_open.date() for bar in bars})
            for instrument, values in grouped.items():
                present = {bar.ts_open.date() for bar in values}
                missing = [day.isoformat() for day in expected if day not in present]
                if missing:
                    raise ValueError(f"VERIFIED_DATA_MISSING: instrument={instrument.key}; missing_sessions={missing}")
