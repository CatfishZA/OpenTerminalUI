# Codex Phase 1C — Backtest Compatibility Integration

**Repository:** `CatfishZA/OpenTerminalUI`  
**Working branch:** `feat/simulation-core`  
**Phase 1A checkpoint:** `2059e10 feat(simulation): add Phase 1A simulation core scaffold`  
**Phase 1B checkpoint:** `7be9c00 feat(simulation): implement Phase 1B deterministic daily engine`  
**Objective:** Connect the existing OpenTerminalUI backtest workflow to the new deterministic simulator without breaking existing API contracts, frontend behavior, or legacy research workflows.

## 1. Required reading

Read completely before changing code:

```text
docs/architecture/OpenTerminalUI_Assessment_and_Direction.md
docs/architecture/OpenTerminalUI_Simulation_Implementation_Blueprint.md
docs/architecture/Codex Phase 1A — Simulation Core Scaffold.md
docs/architecture/Codex_Phase_1B_Deterministic_Daily_Engine.md
docs/architecture/Codex Phase 1C — Backtest Compatibility Integration.md
```

Treat the Assessment as context, the Blueprint as source of truth, Phase 1A/1B as completed work, and this document as the current task.

## 2. Safety rules

Work only on `feat/simulation-core`.

Do not switch to or modify `main`. Do not push or merge unless instructed. Do not start Phase 1D or Phase 2. Do not modify the frontend in this phase.

## 3. Integration model

Implement a deliberate dual path:

```text
Existing RESEARCH/default request
    → existing legacy backtest path

Explicit VERIFIED request
    → Phase 1B SimulationService + DailySimulator
```

The legacy engine remains available for existing research workflows.

The legacy engine must never execute a request labeled VERIFIED.

Do not silently fall back from VERIFIED to legacy behavior.

## 4. Preserve existing public routes

Keep these compatible:

```text
GET  /backtests/strategies
POST /backtests
POST /backtests/compare
GET  /backtests/{run_id}/status
GET  /backtests/{run_id}/result
GET  /backtests/{run_id}/analytics
GET  /backtests/{run_id}/robustness

POST /v1/backtest/submit
GET  /v1/backtest/status/{run_id}
GET  /v1/backtest/result/{run_id}
POST /v1/backtest/validate/walkforward
POST /v1/backtest/simulate/montecarlo
POST /v1/backtest/optimize
POST /v1/backtest/portfolio/submit
POST /v1/backtest/factor/decompose
```

Existing payloads must continue to work.

## 5. Do not rewrite legacy engines

Do not modify unless absolutely necessary:

```text
backend/core/single_asset_backtest.py
backend/core/portfolio_backtest.py
backend/portfolio_backtests/engine.py
backend/paper_trading/service.py
```

Phase 1C changes orchestration and compatibility, not legacy engine internals.

## 6. Primary files

Work mainly in:

```text
backend/services/backtest_jobs.py
backend/api/routes/backtests.py
backend/simulation/services/simulation_service.py
backend/simulation/services/simulator_factory.py          # new if useful
backend/simulation/adapters/backtest_request_adapter.py   # new
backend/simulation/adapters/legacy_result_adapter.py
backend/simulation/adapters/strategy_runner_adapter.py
backend/simulation/adapters/versioned_data_adapter.py
backend/simulation/persistence/repositories.py
backend/simulation/persistence/models.py
backend/models/core.py
backend/models/__init__.py
backend/alembic/versions/<next>_backtest_simulation_link.py
backend/tests/simulation/
```

## 7. Backward-compatible request fields

Extend the legacy submit model and `BacktestJobRequest` with optional fields:

```python
verification_level: str = "RESEARCH"
data_version_id: str | None = None
currency: str | None = None
```

Do not require these for old clients.

The default old request remains RESEARCH and follows the legacy path.

## 8. Routing rule

Make routing explicit, e.g.:

```python
def should_use_simulation_engine(req: BacktestJobRequest) -> bool:
    return req.verification_level.strip().upper() == "VERIFIED"
```

### RESEARCH/default

Use the existing legacy path unchanged.

### VERIFIED

Use only the deterministic simulation stack.

VERIFIED must never call:

```text
BacktestEngine
_build_synthetic_frame()
_fetch_with_market_fallback()
historical-data synthetic fallback
```

If unsupported, fail explicitly.

## 9. VERIFIED validation

Before creating a simulation run require:

```text
timeframe == "1d"
data_version_id present
start present
end present
asset class EQUITY
supported venue
supported currency
supported execution config
supported strategy/config semantics
```

Suggested stable errors:

```text
DATA_VERSION_REQUIRED
VERIFIED_START_REQUIRED
VERIFIED_END_REQUIRED
UNSUPPORTED_VERIFIED_TIMEFRAME
UNSUPPORTED_VERIFIED_VENUE
UNSUPPORTED_VERIFIED_CONFIG
UNSUPPORTED_EXECUTION_MODEL
UNSUPPORTED_COMMISSION_MODEL
```

No fallback.

## 10. Venue/currency mapping

Minimum mapping:

```text
NSE     → INR
BSE     → INR
NASDAQ  → USD
NYSE    → USD
AMEX    → USD
```

If `currency` is explicitly supplied, validate it where practical.

Unknown VERIFIED venue: fail. Do not guess.

## 11. Instrument mapping

For VERIFIED:

```python
InstrumentId(
    symbol=canonical_symbol,
    venue=req.market,
    asset_class="EQUITY",
    currency=resolved_currency,
)
```

No market substitution.

## 12. Link legacy and canonical runs

Add nullable `simulation_run_id` to `BacktestRun`.

Recommended schema:

```text
simulation_run_id STRING(64)
nullable
indexed
FK simulation_runs.id ON DELETE SET NULL
```

Create the next valid Alembic migration after inspecting the real current head.

Suggested suffix:

```text
_backtest_simulation_link
```

Keep public legacy IDs as `bt_*`. Canonical IDs remain `sim_*`.

## 13. VERIFIED submission flow

```text
POST /backtests
→ create BacktestRun (bt_*)
→ adapt request to SimulationRunSpec
→ SimulationService.submit(spec) creates sim_*
→ link bt_* to sim_*
→ queue bt_* job
→ worker executes linked simulation
```

The API still returns the `bt_*` ID.

## 14. RESEARCH submission flow

Keep current behavior:

```text
POST /backtests
→ create bt_*
→ legacy queue
→ legacy engine
→ legacy result_json
```

Do not create a SimulationRun for ordinary legacy requests.

## 15. Dedicated request adapter

Create:

```text
backend/simulation/adapters/backtest_request_adapter.py
```

Suggested interface:

```python
class BacktestRequestAdapter:
    def to_spec(self, req: BacktestJobRequest) -> SimulationRunSpec:
        ...
```

Responsibilities:

- parse dates;
- create InstrumentId;
- resolve currency;
- map initial cash;
- map strategy/context;
- map data version;
- map execution/commission/settlement;
- map seed;
- reject unsupported VERIFIED settings.

Do not build this spec inline in `backtest_jobs.py`.

## 16. Date policy

VERIFIED requires explicit `start` and `end`.

Do not use wall-clock “today” to fill missing VERIFIED dates.

Invalid range must fail.

## 17. Legacy config mapping

Map faithfully where supported.

### Initial cash

```text
config.initial_cash → SimulationRunSpec.initial_cash
default 100000
```

### Fees

```text
config.fee_bps
→ commission_profile = {
    model: "bps",
    bps: fee_bps,
    minimum: 0
}
```

### Slippage

```text
config.slippage_bps
→ execution_profile = {
    model: "fixed_bps",
    slippage_bps: slippage_bps,
    max_participation: 1,
    daily_bar_path_policy: "WORST_CASE"
}
```

Do not confuse fee BPS and slippage BPS.

## 18. Position sizing compatibility

Phase 1B is long-only and the strategy adapter uses explicit quantity.

For VERIFIED Phase 1C:

- support `context.quantity`;
- optionally map `config.position_size` if semantics are exact;
- if `position_fraction` cannot be represented faithfully, fail with `UNSUPPORTED_VERIFIED_CONFIG`;
- do not silently ignore shorting/sizing settings.

Do not claim compatibility that does not exist.

## 19. Strategy boundary

VERIFIED must use:

```text
backend/simulation/adapters/strategy_runner_adapter.py
```

Do not call `StrategyRunner` directly from the verified worker.

Preserve close-signal → next-open execution semantics.

## 20. Simulator factory

Create one integration factory, e.g.:

```text
backend/simulation/services/simulator_factory.py
```

Suggested:

```python
def build_daily_simulator(
    db: Session,
    spec: SimulationRunSpec,
) -> DailySimulator:
    ...
```

Construct:

```text
VersionedDataAdapter
StrategyRunnerAdapter
execution model
commission model
event store
ledger repository
record repository
corporate-action adapter/source
DailySimulator
```

Do not duplicate dependency construction in routes/jobs.

## 21. Execution factory

Support only models actually implemented and tested in Phase 1B.

Minimum:

```text
fixed_bps
volume_participation
```

Unknown model must fail. Do not silently substitute another model.

## 22. Commission factory

Support Phase 1B `bps` commission.

Unknown model must fail. Do not silently use zero commission.

## 23. Canonical service lifecycle

The verified worker must use:

```text
SimulationService.submit()
SimulationService.execute()
```

Do not bypass canonical run lifecycle by calling `DailySimulator.run()` directly from `BacktestJobService`.

## 24. Completed canonical result retrieval

Phase 1B currently executes a result in memory but canonical completed retrieval must be durable.

After Phase 1C, `SimulationService.result(run_id)` must return completed data after a fresh service/session is created.

Preferred choices:

### A. Reconstruct from persisted canonical records

Preferred if straightforward.

### B. Persist a derived result cache

If required, add fields such as:

```text
result_json
result_hash
```

to `simulation_runs` via migration.

If cached, canonical fills/ledger/orders/snapshots remain authoritative.

Document the choice.

## 25. SimulationService.result contract

Queued/running:

```json
{
  "run_id": "...",
  "status": "...",
  "stage": "...",
  "result": null
}
```

Done:

```json
{
  "run_id": "...",
  "status": "DONE",
  "stage": "done",
  "result": { "...": "canonical result" }
}
```

Failed: expose status/error, no fabricated result.

## 26. Legacy result adaptation

Use:

```text
backend/simulation/adapters/legacy_result_adapter.py
```

Flow:

```text
SimulationResult
→ LegacyResultAdapter
→ BacktestRun.result_json
```

Do not assemble legacy financial result fields in the worker.

## 27. Minimum adapted VERIFIED result

Provide honestly derived fields needed by existing UI/analytics:

```text
symbol
asset
bars
initial_cash
final_equity
pnl_amount
ending_cash
total_return
daily_returns
drawdown_series
trades
equity_curve
orders
fills
manifest
data_quality
verification_level
simulation_run_id
```

Also expose provenance:

```text
data_version_id
engine_version
manifest_hash
result_hash
daily_bar_path_policy
```

Do not invent metrics.

## 28. Existing metrics compatibility

Current result schema includes metrics such as:

```text
max_drawdown
sharpe
sortino
calmar
omega
profit_factor
win_rate
...
```

Where possible derive them from canonical equity/trade data using existing analytics utilities.

Do not use the legacy execution engine to calculate VERIFIED account results.

If a schema-required metric cannot yet be derived correctly, use a documented compatibility value only where unavoidable and report it as a limitation.

## 29. TradeRecord compatibility

Current `TradeRecord` expects:

```text
date
action
quantity
price
cash_after
position_after
hold_time_minutes
```

Derive from canonical fill chronology plus ledger/account state.

Do not use the old legacy BUY/SELL pairing algorithm as source of truth.

Long-only compatibility is sufficient.

## 30. EquityPoint compatibility

Current equity points expect:

```text
date
open
high
low
equity
cash
position
close
signal
```

Build from canonical portfolio/position snapshots and versioned bars.

If historical signal value is not persisted, neutral `signal` may be used only as a compatibility field. Canonical equity/cash/position/price values must remain real.

## 31. Legacy status mapping

Map simulation status to existing public status:

```text
QUEUED           → queued
VALIDATING_DATA  → running
BUILDING_MANIFEST→ running
RUNNING          → running
FINALIZING       → running
DONE             → done
FAILED           → failed
```

Return the public `bt_*` run ID.

## 32. WebSocket progress

Preserve:

```text
type = backtest_progress
run_id = bt_* ID
```

Suggested stages:

```text
10  validating data
25  building manifest
40  loading versioned data
60  running deterministic simulation
90  finalizing/reconciling
100 done
```

Do not emit 100 on failure.

## 33. Error propagation

On verified failure:

```text
BacktestRun.status = failed
BacktestRun.error = meaningful stable error/message
```

Canonical SimulationRun must also be FAILED where appropriate.

Do not hide specific errors behind generic failure text.

## 34. Explicit verified no-fallback rules

Tests must prove VERIFIED never calls:

```text
_build_synthetic_frame()
_fetch_with_market_fallback()
BacktestEngine.run()
```

Do not delete those legacy helpers yet; RESEARCH still uses them.

## 35. Scope exclusions

Do not migrate in Phase 1C:

```text
POST /v1/backtest/portfolio/submit
/backtests/compare verified semantics
vectorized sweep
parameter optimizer
walk-forward engine
Monte Carlo engine
paper trading
model governance
frontend
```

Existing behavior remains.

## 36. Analytics compatibility

Completed VERIFIED runs must work with:

```text
GET /backtests/{bt_id}/analytics
GET /backtests/{bt_id}/robustness
```

Ensure adapted result contains valid `equity_curve`, `trades`, and `daily_returns`.

## 37. Transaction safety

Do not leave a legacy row permanently running if simulation creation/execution fails.

Do not mark the legacy row done before:

```text
canonical simulation DONE
reconciliation passed
canonical result durable
legacy adapted result persisted
```

Keep transaction boundaries explicit.

## 38. Worker structure

Prefer clearly separate methods:

```python
async def _execute(self, run_id):
    ...
    if verified:
        await self._execute_verified(...)
    else:
        await self._execute_legacy(...)
```

Avoid deeply intertwined fallback logic.

The existing asyncio queue is acceptable. Do not add Celery/RQ.

## 39. Acceptance tests

Add unique filenames that are not ignored by `.gitignore`.

### AT-C01 — Old request remains legacy

Submit existing payload without new verification fields.

Expected:

- `bt_*` ID;
- legacy engine selected;
- no SimulationRun required;
- legacy response contract preserved.

### AT-C02 — VERIFIED creates linked simulation

Expected:

```text
BacktestRun.run_id = bt_*
BacktestRun.simulation_run_id = sim_*
SimulationRun verification = VERIFIED
```

### AT-C03 — VERIFIED uses new engine only

Mock/patch `BacktestEngine.run()` to fail if called.

VERIFIED run must succeed without calling it.

### AT-C04 — VERIFIED missing data version fails

No legacy fallback.

### AT-C05 — VERIFIED missing persisted data fails

Expected `VERIFIED_DATA_MISSING` or `INSTRUMENT_DATA_NOT_FOUND`.

No synthetic data.

### AT-C06 — VERIFIED never performs market fallback

Assert `_fetch_with_market_fallback()` is not called.

### AT-C07 — Legacy status compatibility

Verified linked job still exposes only compatible legacy statuses with `bt_*`.

### AT-C08 — Legacy result compatibility

`GET /backtests/{bt_id}/result` after verified completion returns `done` and a compatible non-null result.

### AT-C09 — Canonical result retrievable

`GET /api/v1/simulation/runs/{sim_id}` returns completed result after execution.

### AT-C10 — Analytics works on VERIFIED result

`GET /backtests/{bt_id}/analytics` succeeds.

### AT-C11 — Robustness works on VERIFIED result

`GET /backtests/{bt_id}/robustness` succeeds.

### AT-C12 — Provenance exposed

Verified legacy result includes:

```text
verification_level
simulation_run_id
data_version_id
engine_version
manifest_hash
result_hash
```

### AT-C13 — Unsupported VERIFIED timeframe rejected

Example `5m` → `UNSUPPORTED_VERIFIED_TIMEFRAME`.

### AT-C14 — Unsupported VERIFIED config rejected

Do not silently ignore unsupported sizing/shorting semantics.

### AT-C15 — Result survives fresh service/session

Execute, recreate SQLAlchemy session and `SimulationService`, retrieve same completed canonical result/result hash.

### AT-C16 — Legacy RESEARCH regression remains compatible

Selected existing legacy backtest regression still passes through legacy path.

## 40. Direct simulation API regression

Do not break:

```text
POST /api/v1/simulation/runs
GET /api/v1/simulation/runs/{id}/status
GET /api/v1/simulation/runs/{id}
GET /api/v1/simulation/runs/{id}/manifest
GET /api/v1/simulation/runs/{id}/orders
GET /api/v1/simulation/runs/{id}/fills
GET /api/v1/simulation/runs/{id}/ledger
GET /api/v1/simulation/runs/{id}/events
GET /api/v1/simulation/runs/{id}/portfolio
GET /api/v1/simulation/runs/{id}/positions
```

## 41. Test cadence

During development run targeted tests only, e.g.:

```bash
pytest backend/tests/simulation/test_backtest_request_adapter.py
pytest backend/tests/simulation/test_backtest_verified_integration.py
pytest backend/tests/simulation/test_legacy_result_adapter.py
```

Then:

```bash
pytest backend/tests/simulation/
```

Do not repeatedly run the full backend suite.

## 42. End-of-phase verification

At completion run:

```text
1. all backend/tests/simulation/
2. targeted legacy backtest API/job tests
3. analytics/robustness route tests
4. selected legacy backtest regressions
5. Python compile check for changed backend packages
6. git diff --check
7. git status --short
```

No frontend tests/build because frontend files must not change.

Run the full backend suite once at the end only after targeted tests are green. If the known Windows temp-directory issue appears, report it and rerun only affected tests using repository-local temp.

## 43. Deliverables

Report:

1. Summary.
2. Files created.
3. Files modified.
4. Migration created.
5. New request fields.
6. Routing rules.
7. VERIFIED adapter/factory behavior.
8. Canonical-result durability approach.
9. Legacy-result adaptation approach.
10. Acceptance tests added.
11. Targeted results.
12. Selected legacy results.
13. Full backend result if run.
14. Environment-only failures.
15. Deviations.
16. Known limitations.
17. Confirmation frontend untouched.
18. Confirmation paper trading untouched.
19. Confirmation legacy engine internals untouched.
20. Confirmation Phase 1D not started.
21. Recommended Phase 1D.

Do not commit or push unless explicitly instructed.

## 44. Completion criteria

Phase 1C is complete only when AT-C01 through AT-C16 pass and:

- old requests still use legacy execution;
- VERIFIED requests use the new simulator only;
- no VERIFIED synthetic fallback;
- no VERIFIED market fallback;
- public run IDs remain `bt_*`;
- verified `bt_*` rows link to `sim_*`;
- completed canonical results survive a fresh service/session;
- legacy result endpoint serves compatible verified output;
- analytics and robustness work on verified adapted output;
- provenance is exposed;
- unsupported verified configs fail explicitly;
- frontend unchanged;
- paper trading unchanged;
- legacy engine internals unchanged.

## 45. Stop condition

When Phase 1C criteria pass, **STOP**.

Do not begin:

- frontend verification/provenance UI;
- backtest page redesign;
- orders/fills/ledger UI;
- paper trading migration;
- governance promotion changes;
- optimizer migration;
- Phase 1D.

Report completion and wait.
