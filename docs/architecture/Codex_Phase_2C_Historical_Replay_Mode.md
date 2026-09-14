# Codex Phase 2C — Historical Replay Mode

**Repository:** `CatfishZA/OpenTerminalUI`  
**Branch:** `feat/simulation-core`  
**Baseline:** Phase 2B checkpoint `e5be486`  
**Status:** Implementation task specification  
**Phase:** 2C  
**Primary objective:** Add a deterministic, restart-safe historical REPLAY mode that advances persisted historical market data one session at a time through the same canonical execution/accounting machinery used by BACKTEST, without creating another financial engine.

---

## 0. Read this first

Phase 2C makes the existing `SimulationMode.REPLAY` operational.

The critical rule is:

> **REPLAY is not another backtest engine.**

Target architecture:

```text
Persisted Versioned Historical Data
                │
                ▼
          REPLAY CLOCK
                │
                ▼
      Shared Daily Session Kernel
                │
      ┌─────────┼──────────┐
      ▼         ▼          ▼
 OrderManager  Matching   Strategy Adapter
      │         │          │
      └─────────┼──────────┘
                ▼
        Shared AccountEngine
                │
        Shared SettlementEngine
                │
        Shared ValuationEngine
                │
                ▼
 Orders / Fills / Ledger / Events / Snapshots
                │
                ▼
        Persistent Replay Session
```

Replay must not:

- precompute the full result and merely hide future rows;
- expose future bars to the replay strategy;
- fabricate minute/tick data from daily OHLC;
- introduce a second accounting model;
- introduce a second order lifecycle;
- change BACKTEST or PAPER semantics.

---

# 1. Product/engineering interpretation

Phase 2C is a **backend historical replay foundation**.

The canonical persisted historical source is currently daily EOD data, so initial replay granularity is:

```text
ONE TRADING SESSION
```

A replay can:

```text
create
inspect state
advance one session
advance N sessions
run to a target session
run to end
cancel
resume after service/process restart
inspect canonical orders/fills/events/ledger/snapshots
inspect market bars only up to the replay cursor
```

Phase 2C does not invent intraday history.

Future minute/tick replay should be able to replace/extend the historical market adapter without changing canonical replay/accounting contracts.

---

# 2. Objectives

Implement a canonical REPLAY subsystem that:

1. creates `SimulationMode.REPLAY` runs;
2. uses persisted versioned historical data;
3. never silently fetches provider data during replay;
4. validates the requested range before replay begins;
5. advances a deterministic replay clock by trading session;
6. exposes only information available at the current replay time;
7. shares the same daily session semantics as canonical BACKTEST;
8. shares canonical order, matching, accounting, settlement, valuation, ledger and persistence;
9. persists replay cursor/control state;
10. persists canonical financial artifacts incrementally;
11. resumes safely after restart;
12. prevents duplicate events/orders/fills after retry/restart;
13. makes each completed session an atomic checkpoint;
14. finalizes into a normal canonical `SimulationResult`;
15. preserves BACKTEST, PAPER, reconciliation and VERIFIED behavior;
16. adds canonical replay APIs;
17. requires no frontend redesign.

---

# 3. Non-goals

Do not implement:

- live broker execution;
- real-money trading;
- historical tick reconstruction;
- synthetic minute bars;
- L2/L3 replay;
- exchange queue simulation;
- manual discretionary replay order entry;
- chart playback UI;
- wall-clock backend playback timers;
- playback speed scheduler;
- automatic replay/backtest reconciliation;
- Phase 3 corporate-action expansion;
- strategy governance;
- options/futures replay;
- FX replay;
- multiple currencies;
- short selling;
- a separate replay accounting engine.

Manual/discretionary historical trading can be added later on top of this foundation.

Phase 2C is deterministic strategy-driven historical replay.

---

# 4. Current architecture to preserve

The domain already contains:

```text
SimulationMode.BACKTEST
SimulationMode.REPLAY
SimulationMode.PAPER
SimulationMode.LIVE
```

Canonical BACKTEST currently uses:

```text
DailySimulator
OrderManager
MatchingEngine
AccountEngine
SettlementEngine
ValuationEngine
ResultBuilder
VersionedDataAdapter
StrategyRunnerAdapter
```

Canonical PAPER shares the financial machinery through its live-clock orchestration.

Phase 2B reconciliation must remain unchanged.

The existing `SimulationService` remains the canonical run/read facade.

---

# 5. Architectural decision: shared daily session kernel

The current `DailySimulator` is a complete batch event loop.

Historical REPLAY requires the same daily behavior incrementally.

Do **not** copy the DailySimulator loop into a replay service.

Instead perform a narrow behavior-preserving extraction of the daily **one-session processing kernel**.

Suggested module:

```text
backend/simulation/engine/daily_session_kernel.py
```

The shared kernel owns behavior that must remain identical between BACKTEST and REPLAY:

```text
settlement timing
corporate-action hook timing
BAR_OPEN ordering
eligible open-order matching
strategy open callbacks
daily-bar intraday order processing
BAR_CLOSE availability
strategy close callbacks
next-session eligibility
DAY expiry
MARK
valuation
position snapshots
portfolio snapshots
SESSION_END
```

`DailySimulator` becomes a batch orchestrator over this kernel.

`ReplaySimulationService` invokes the same kernel one session at a time.

### Hard rule

Do not maintain two implementations of daily order/event semantics.

If a safe shared-kernel extraction cannot be made without changing Phase 1 semantics, stop and report before duplicating the event loop.

---

# 6. BACKTEST behavior-preservation gate

Before editing `DailySimulator`, run focused existing tests that define:

```text
no lookahead
event ordering
next-open eligibility
daily path policy
partial fills
cash reservation
shared cash
settlement
full-exit realized P&L
determinism
VERIFIED strict data policy
```

After extraction those exact behaviors must remain green.

The extraction must not change:

```text
event ordering
event timestamps
strategy callback timing
order eligibility timestamps
order statuses
fill prices
fill quantities
commission
ledger amounts
portfolio snapshots
position snapshots
result summary
existing result-hash behavior
```

Phase 2C may reorganize code but must not change observable BACKTEST semantics.

---

# 7. Replay data policy

## 7.1 Persisted data only

All REPLAY runs require:

```text
data_version_id
```

This applies even when `verification_level=RESEARCH`.

Reasons:

- restart determinism;
- cursor reproducibility;
- no provider drift mid-session;
- no hidden future fetch;
- no synthetic execution input.

No REPLAY run may silently call an external provider to fill missing history.

No synthetic history.

No market/venue substitution.

## 7.2 Verification levels

Phase 2C supports:

```text
VERIFIED
RESEARCH
```

and rejects:

```text
SYNTHETIC
```

VERIFIED replay uses current strict VERIFIED data rules.

RESEARCH replay still uses selected persisted versioned data but remains explicitly non-verified.

SYNTHETIC replay returns:

```text
REPLAY_SYNTHETIC_UNSUPPORTED
```

---

# 8. Replay granularity and cursor

The atomic replay unit is one complete trading session.

The cursor lives **between sessions**.

Example:

```text
created
  cursor = before 2025-01-02

advance(1)
  process every canonical event for 2025-01-02
  commit session atomically
  cursor = after 2025-01-02

advance(1)
  process next session
```

Do not checkpoint halfway through a trading session in Phase 2C.

This is essential for:

```text
restart safety
atomicity
order/fill uniqueness
settlement recovery
strategy-state recovery
deterministic retry
```

---

# 9. Canonical event ordering

REPLAY inherits the same event semantics as BACKTEST.

Conceptually:

```text
SESSION_START
SETTLEMENT
CORPORATE_ACTION

BAR_OPEN (canonical instrument order)
OPEN_ORDER_MATCH
eligible existing-order matching

STRATEGY_OPEN_CALLBACK

INTRADAY_ORDER_PROCESSING
limit/stop/daily-path handling

BAR_CLOSE (canonical instrument order)
STRATEGY_CLOSE_CALLBACK

new intents accepted for next eligibility

POST_CLOSE_ORDER_VALIDATION
DAY expiry

MARK
VALUATION
PORTFOLIO_SNAPSHOT
SESSION_END
```

Order/fill/ledger events remain interleaved in the same logical positions as BACKTEST.

Exact ordering must come from the shared kernel, not an independently copied replay loop.

---

# 10. Replay domain

Create:

```text
backend/simulation/domain/replay.py
```

Suggested enum:

```python
class ReplayControlStatus(str, Enum):
    READY = "READY"
    ADVANCING = "ADVANCING"
    PAUSED = "PAUSED"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
```

Suggested projection:

```python
@dataclass(frozen=True, slots=True)
class ReplayState:
    run_id: str
    status: ReplayControlStatus
    current_session: date | None
    next_session: date | None
    completed_sessions: int
    total_sessions: int
    current_time: datetime | None
    last_event_sequence: int
    progress: Decimal
    checkpoint_hash: str | None
```

Before first advance:

```text
current_session = null
next_session = first session
completed_sessions = 0
```

---

# 11. Replay specification

Reuse `SimulationRunSpec` for financial and strategy configuration.

Do not weaken its validation.

The replay run must carry:

```text
mode = REPLAY
verification level
strategy
strategy context
universe
start/end
initial cash
base currency
data version
execution profile
commission profile
settlement profile
seed
benchmark optional
```

Phase 2C remains:

```text
cash equities
long only
daily historical data
```

---

# 12. Replay creation lifecycle

Creating a replay must:

1. validate request;
2. force/require `mode=REPLAY`;
3. require `data_version_id`;
4. reject SYNTHETIC;
5. resolve data-version metadata;
6. load and validate persisted historical coverage;
7. determine deterministic ordered sessions;
8. build canonical manifest;
9. create `simulation_runs`;
10. create replay-state row;
11. initialize canonical opening cash state according to shared bootstrap semantics;
12. set canonical run status to `RUNNING`;
13. set replay control status to `READY`.

No market session is processed until `advance` or `run-to-end`.

Creation must not generate future signals/orders.

---

# 13. Strategy lifecycle and state

An uninterrupted BACKTEST logically calls:

```text
strategy.on_start(...)
session callbacks...
strategy.on_finish(...)
```

REPLAY must preserve this lifecycle.

### First advance

Before the first session:

```text
initialize/restore strategy
call on_start exactly once
```

### Intermediate steps

Persist and restore strategy state.

### Finalization

After the final `SESSION_END`:

```text
call on_finish exactly once
```

The current strategy adapter contains `_last_signal` state.

Replay must persist the minimum JSON-safe strategy state needed for deterministic resume.

Add narrow methods such as:

```python
def export_state(self) -> dict[str, Any]: ...
def import_state(self, state: dict[str, Any]) -> None: ...
```

For `StrategyRunnerAdapter`, state includes at minimum:

```text
last signal by canonical instrument
```

Do not serialize arbitrary Python objects.

Adding state import/export must not change BACKTEST strategy behavior.

---

# 14. No-future-data market read model

Replay strategy callbacks may only see information available at replay time.

At `BAR_OPEN`:

```text
current session close/high/low are unavailable
```

At `BAR_CLOSE`:

```text
current complete bar is available
```

Future sessions are never visible.

Do not preload future bars into strategy-visible history.

Implement a replay-safe `MarketReadModel` or equivalent that enforces the same availability rules as BACKTEST.

---

# 15. Replay-scoped market API

Add:

```text
GET /api/v1/simulation/replays/{run_id}/market
```

Suggested query:

```text
instrument
limit
```

Return only bars available up to the replay cursor.

Before first completed session, do not expose later historical bars through this replay endpoint.

This is a replay-view API, not a replacement for general historical-data APIs.

---

# 16. Atomic session persistence

This is a critical invariant.

For one replay-session advance:

```text
either:
  every event/order/fill/ledger/snapshot/settlement/checkpoint is persisted
or:
  none is persisted
```

The replay cursor moves only after the whole session succeeds.

The current persistence helpers may commit per artifact.

Do not use per-artifact commits inside replay execution.

Use either:

- a replay-specific transaction-aware repository; or
- an opt-in unit-of-work mode added safely to existing repositories.

Suggested:

```text
backend/simulation/persistence/replay_repositories.py
```

`ReplaySimulationService` owns the transaction.

On failure:

```text
rollback entire session
cursor unchanged
```

---

# 17. Replay persistence schema

Inspect the actual Alembic head first.

Expected conceptual next migration:

```text
0016_historical_replay.py
```

Use the next valid revision if head differs.

Add:

## `simulation_replay_sessions`

Suggested columns:

```text
run_id                 FK simulation_runs, PK

control_status         string(16)

start_session          date
end_session            date

current_session        date nullable
next_session           date nullable

completed_sessions     integer
total_sessions         integer

last_event_sequence    bigint
strategy_state_json    JSON

initialized            boolean
finish_called          boolean

checkpoint_hash        string(128) nullable

created_at             datetime
updated_at             datetime
completed_at           datetime nullable
```

Indexes:

```text
control_status
updated_at
```

### Financial authority rule

Do not copy canonical financial state into replay JSON.

The replay row must not become authority for:

```text
cash
positions
orders
fills
ledger
settlement obligations
```

Those remain in canonical simulation tables.

---

# 18. Account restoration

A replay must resume after process restart.

Reconstruct current account from canonical persisted state, including:

```text
latest replay portfolio snapshot
latest replay position snapshots
open canonical orders
persisted settlement obligations
fees/P&L/cash fields
```

Use ledger/fills for validation where useful.

Do not restore from:

```text
Virtual*
legacy paper tables
PAPER service cache
```

A helper such as:

```text
backend/simulation/services/canonical_account_loader.py
```

is acceptable if it is clearly reusable and behavior-preserving.

---

# 19. Settlement persistence

REPLAY must survive restart.

Use the existing canonical:

```text
simulation_settlement_obligations
```

for REPLAY fills.

When a replay fill creates an obligation:

```text
persist it in the same session transaction
```

At due replay sessions:

```text
load pending obligations
process settlement
persist canonical settlement/ledger state
```

Configured:

```text
T+0
T+1
T+2
```

must remain restart-safe.

Do not change PAPER settlement semantics.

---

# 20. Event sequencing

Replay event sequence is persisted and monotonic.

For each session derive sequence from canonical persisted state, e.g.:

```text
MAX(sequence) + 1
```

Do not trust process-local counters after restart.

The existing:

```text
UNIQUE(run_id, sequence)
```

constraint remains authoritative protection.

Retry after rollback must not duplicate canonical events.

---

# 21. Restart-safe order/fill identifiers

Do not use process-local counters that reset.

Order/fill IDs must be deterministic/unique within the replay run after restart.

Derive sequence from persisted state or replay checkpoint.

The economic order/fill sequence must be invariant to:

```text
advance(1) repeatedly
advance(N)
run-to-end
service restart between calls
```

---

# 22. Concurrency control

Add per-replay-run serialization.

Suggested:

```python
_REPLAY_LOCKS: dict[str, asyncio.Lock]
```

or a shared canonical lock helper.

State-changing replay calls must serialize:

```text
advance
run-to
run-to-end
cancel
finalize
```

Two concurrent requests must never process the same session twice.

Do not use a global lock across unrelated runs.

---

# 23. Replay service

Create:

```text
backend/simulation/services/replay_simulation_service.py
```

Suggested interface:

```python
async def create(spec) -> str
async def state(run_id) -> ReplayState
async def advance(run_id, *, sessions: int = 1) -> ReplayState
async def run_to(run_id, *, target_session: date) -> ReplayState
async def run_to_end(run_id) -> ReplayState
async def cancel(run_id) -> ReplayState
async def market(run_id, instrument, ...) -> ...
```

All execution paths must invoke the same one-session method.

---

# 24. Advance behavior

`advance` requires:

```text
sessions >= 1
```

Process at most requested sessions.

After each successful session:

```text
commit canonical artifacts
persist strategy state
persist replay checkpoint
```

If final session reached:

```text
finalize
run = DONE
replay = DONE
```

Otherwise:

```text
run = RUNNING
replay = PAUSED
```

---

# 25. Run-to-target

Support:

```text
target_session
```

Rules:

- target must belong to the replay calendar;
- target cannot precede current cursor;
- process through target inclusive;
- pause after target unless it is final session.

Stable error:

```text
REPLAY_TARGET_INVALID
```

No in-place rewind.

Create a new replay to restart earlier history.

---

# 26. Run-to-end

`run_to_end` processes all remaining sessions through the same one-session advancement method.

Do not create a second “fast” engine.

Final economic state must be equivalent to repeatedly calling `advance(1)`.

---

# 27. Cancellation

Cancelling a non-terminal replay:

```text
preserves all completed artifacts
does not rewind
does not delete history
does not finalize as DONE
```

Set:

```text
replay control status = CANCELLED
simulation run status = CANCELLED
```

A cancelled replay cannot resume in Phase 2C.

---

# 28. Failure behavior

If a session fails:

```text
rollback session
keep cursor at prior completed session
mark replay FAILED
mark canonical run FAILED
persist stable error
```

No partial session artifacts may remain.

Do not silently skip bad data or strategy failures.

---

# 29. Completion/finalization

After final session:

1. call `on_finish` exactly once;
2. run existing intra-run reconciliation;
3. load persisted canonical artifacts deterministically;
4. build a canonical `SimulationResult`;
5. calculate/store result hash under existing policy;
6. store `result_json`;
7. set canonical run `DONE`;
8. set replay control `DONE`;
9. persist completed checkpoint.

The existing generic endpoint:

```text
GET /api/v1/simulation/runs/{run_id}
```

must return a normal canonical result after completion.

---

# 30. Canonical result assembly

Incremental replay cannot rely on an in-memory `ResultBuilder` surviving the full run.

At finalization assemble result from persisted:

```text
orders
fills
ledger
events
portfolio snapshots
position snapshots
manifest
```

in deterministic order.

A reusable helper such as:

```text
backend/simulation/services/canonical_result_assembler.py
```

is acceptable.

Preserve current `ResultBuilder` behavior for:

```text
equity curve
daily returns
summary
reconciliation
```

Do not change BACKTEST result contracts.

---

# 31. Checkpoint hash

After each completed session calculate a deterministic checkpoint hash from:

```text
run id
current session
last event sequence
latest portfolio snapshot
open canonical orders
pending settlement obligations
strategy state
```

Exclude:

```text
updated_at
processing wall-clock time
database auto IDs
```

Purpose:

```text
restart verification
corruption detection
deterministic-resume testing
```

This does not replace final result hash.

---

# 32. Progress

Replay progress:

```text
completed_sessions / total_sessions
```

Expose:

```text
completed_sessions
total_sessions
progress
current_session
next_session
```

Replay-specific state endpoint is authoritative for cursor/progress.

Do not add `PAUSED` to global `SimulationRunStatus` unless there is a compelling cross-mode reason.

---

# 33. Replay API

Create:

```text
backend/simulation/api/replay_routes.py
```

Mount under:

```text
/api/v1/simulation
```

## Create

### `POST /api/v1/simulation/replays`

Mode is implicit REPLAY.

Request reuses canonical strategy/account/execution fields.

Example:

```json
{
  "verification_level": "VERIFIED",
  "strategy": {
    "key": "example:sma_crossover",
    "context": {
      "short_window": 20,
      "long_window": 50,
      "quantity": 10
    }
  },
  "universe": [{
    "symbol": "RELIANCE",
    "venue": "NSE",
    "asset_class": "EQUITY",
    "currency": "INR"
  }],
  "start": "2024-01-01",
  "end": "2024-12-31",
  "account": {
    "initial_cash": 100000,
    "base_currency": "INR",
    "settlement_days": 1
  },
  "data_version_id": "version-id",
  "execution": {
    "model": "fixed_bps",
    "slippage_bps": 3,
    "daily_bar_path_policy": "WORST_CASE"
  },
  "commission": {
    "model": "bps",
    "bps": 5,
    "minimum": 0
  },
  "seed": 42
}
```

Response:

```json
{
  "run_id": "sim_...",
  "mode": "REPLAY",
  "status": "READY",
  "completed_sessions": 0,
  "total_sessions": 252,
  "next_session": "2024-01-02"
}
```

## State

### `GET /api/v1/simulation/replays/{run_id}`

## Advance

### `POST /api/v1/simulation/replays/{run_id}/advance`

```json
{"sessions": 1}
```

Suggested bound:

```text
1 <= sessions <= 100
```

## Run to target

### `POST /api/v1/simulation/replays/{run_id}/run-to`

```json
{"target_session": "2024-06-28"}
```

## Run to end

### `POST /api/v1/simulation/replays/{run_id}/run-to-end`

## Cancel

### `POST /api/v1/simulation/replays/{run_id}/cancel`

## Available historical market view

### `GET /api/v1/simulation/replays/{run_id}/market`

---

# 34. Existing generic artifact APIs

Because REPLAY uses canonical tables, existing endpoints must work while replay is paused/running:

```text
GET /api/v1/simulation/runs/{run_id}/orders
GET /api/v1/simulation/runs/{run_id}/fills
GET /api/v1/simulation/runs/{run_id}/ledger
GET /api/v1/simulation/runs/{run_id}/events
GET /api/v1/simulation/runs/{run_id}/portfolio
GET /api/v1/simulation/runs/{run_id}/positions
GET /api/v1/simulation/runs/{run_id}/manifest
```

Only artifacts accumulated so far may exist.

---

# 35. Stable errors

Use/reuse stable codes:

```text
REPLAY_RUN_NOT_FOUND
REPLAY_MODE_INVALID
REPLAY_DATA_VERSION_REQUIRED
REPLAY_SYNTHETIC_UNSUPPORTED
REPLAY_DATA_MISSING
REPLAY_ALREADY_DONE
REPLAY_CANCELLED
REPLAY_FAILED
REPLAY_TARGET_INVALID
REPLAY_ADVANCE_INVALID
REPLAY_SESSION_CONFLICT
REPLAY_CHECKPOINT_MISMATCH
REPLAY_ENGINE_INVARIANT_FAILED
```

Reuse existing data-quality errors when they already express the failure correctly.

---

# 36. BACKTEST ↔ REPLAY economic equivalence

This is a core Phase 2C invariant.

Given identical:

```text
strategy
strategy context
universe
date range
initial cash
base currency
data version
execution profile
commission profile
settlement profile
seed
```

a BACKTEST and REPLAY run-to-end must be economically equivalent.

Ignore identity fields expected to differ:

```text
run id
IDs containing run id
manifest created_at
mode
processing metadata
```

Compare normalized:

```text
ordered event types/times
order side/type/quantity/status/eligibility
fill side/quantity/price/commission/fees/slippage/time
ledger type/currency/amount/time
position snapshot economic values
portfolio snapshot economic values
final equity
realized P&L
unrealized P&L
fees
return
```

Expected:

```text
value-for-value equivalent
```

If this fails, diagnose the semantic divergence rather than masking it.

---

# 37. Step-size invariance

Identical replay specs driven as:

```text
A: advance(1) repeatedly
B: advance(10) in batches
C: run_to_end
```

must yield equivalent normalized canonical output.

---

# 38. Restart invariance

Test:

1. create replay;
2. advance several sessions;
3. dispose service/DB session;
4. construct new service/DB session;
5. reload replay;
6. verify checkpoint;
7. continue to end.

Compare against uninterrupted replay.

No duplicate:

```text
events
orders
fills
ledger
settlements
snapshots
```

---

# 39. Atomicity failure injection

Inject a failure after some session artifacts are produced but before checkpoint commit.

After rollback assert:

```text
cursor unchanged
completed_sessions unchanged
no new session events
no new fills
no new ledger rows
no new snapshots
```

Retry without failure and assert exactly one successful session.

---

# 40. Strategy-state restart

Use a strategy where duplicate behavior would occur if `_last_signal` were lost.

Advance until strategy state is meaningful.

Restart.

Continue.

Assert no duplicate signal-change order is created due to memory reset.

---

# 41. Future-data protection

Test explicitly:

- strategy history excludes future sessions;
- replay market API excludes future sessions;
- BAR_OPEN callback cannot see current close/high/low;
- BAR_CLOSE callback sees completed current bar;
- next-session data remains unavailable.

---

# 42. Multi-instrument deterministic ordering

For multiple instruments, canonical ordering must match BACKTEST.

Use canonical instrument key ordering.

Shared cash remains global.

Test competing BUY intents with insufficient cash and verify REPLAY equals BACKTEST.

---

# 43. Daily path behavior

REPLAY uses the exact existing BACKTEST daily path policy:

```text
OHLC
OLHC
WORST_CASE
```

Do not create replay-specific path logic.

Stop/limit ambiguity resolves identically.

---

# 44. Corporate actions

Invoke the same current corporate-action hook at the same event location as BACKTEST.

Do not expand corporate-action capability in Phase 2C.

Corporate-action hardening remains later work.

---

# 45. Precision

Financial arithmetic remains Decimal for:

```text
cash
prices
commissions
fees
settlement
P&L
positions
snapshots
```

Do not introduce float accounting in replay.

---

# 46. Migration rules

The migration must:

- add only replay-owned state schema;
- preserve all Phase 1/2A/2B rows;
- support current SQLite/PostgreSQL patterns;
- upgrade from actual Phase 2B head;
- downgrade by removing only replay-owned schema.

Verify:

```text
fresh full chain
Phase 2B -> Phase 2C
Phase 2C -> Phase 2B
BACKTEST rows survive
PAPER rows survive
reconciliation rows survive
```

---

# 47. Suggested file treatment

## Create

```text
backend/simulation/domain/replay.py
backend/simulation/engine/daily_session_kernel.py
backend/simulation/services/replay_simulation_service.py
backend/simulation/persistence/replay_repositories.py
backend/simulation/api/replay_routes.py

backend/alembic/versions/0016_historical_replay.py
# or next valid revision

backend/tests/simulation/test_replay_creation.py
backend/tests/simulation/test_replay_advance.py
backend/tests/simulation/test_replay_equivalence.py
backend/tests/simulation/test_replay_restart.py
backend/tests/simulation/test_replay_atomicity.py
backend/tests/simulation/test_replay_future_data.py
backend/tests/simulation/test_replay_api.py
backend/tests/simulation/test_replay_migration.py
```

Optional if clearly useful:

```text
backend/simulation/services/canonical_result_assembler.py
```

## Modify narrowly

Likely:

```text
backend/simulation/engine/daily_simulator.py
backend/simulation/adapters/strategy_runner_adapter.py
backend/simulation/persistence/models.py
backend/simulation/api/schemas.py
backend/simulation/api/__init__.py
backend/simulation/domain/__init__.py
backend/simulation/engine/__init__.py
backend/simulation/services/__init__.py
backend/simulation/persistence/__init__.py
backend/api/router.py
```

Possibly:

```text
backend/simulation/services/simulation_service.py
```

for clean replay-aware status/result integration.

Do not modify frontend files.

Do not modify PAPER or Phase 2B semantics.

---

# 48. Acceptance tests

Phase 2C is not complete until all relevant behaviors are covered.

### RP01 — create VERIFIED replay
Mode REPLAY, VERIFIED, data version linked, run RUNNING, replay READY.

### RP02 — data version required for all replay
RESEARCH without `data_version_id` fails too.

### RP03 — SYNTHETIC replay rejected
`REPLAY_SYNTHETIC_UNSUPPORTED`.

### RP04 — no provider fallback
Missing persisted history fails without provider call.

### RP05 — one-session advance
Exactly one session completes.

### RP06 — N-session advance
Exact N deterministic sessions complete.

### RP07 — run-to-target
Stops exactly at target.

### RP08 — run-to-end
Finalizes canonical result.

### RP09 — generic result endpoint
Completed replay returns DONE result.

### RP10 — generic artifact endpoints while paused
Artifacts-so-far are accessible.

### RP11 — replay market endpoint hides future bars

### RP12 — strategy history hides future bars

### RP13 — BAR_OPEN cannot see current close

### RP14 — BAR_CLOSE sees completed current bar

### RP15 — close-generated intent cannot fill same close

### RP16 — event ordering matches BACKTEST

### RP17 — BACKTEST/REPLAY normalized economic equivalence

### RP18 — step-size invariance

### RP19 — restart-resume invariance

### RP20 — strategy state restored after restart

### RP21 — event sequence monotonic across restart

### RP22 — order IDs restart-safe

### RP23 — fill IDs restart-safe

### RP24 — session transaction rollback is atomic

### RP25 — T+1/T+2 settlement survives restart

### RP26 — T+0 behavior remains correct

### RP27 — shared-cash multi-asset result matches BACKTEST

### RP28 — partial-fill behavior matches BACKTEST

### RP29 — limit-order behavior matches BACKTEST

### RP30 — stop-order behavior matches BACKTEST

### RP31 — OHLC/OLHC/WORST_CASE behavior matches BACKTEST

### RP32 — DAY expiry matches BACKTEST

### RP33 — GTC survives pause/restart

### RP34 — Decimal precision has no float drift

### RP35 — intra-run cash/position/equity reconciliation passes

### RP36 — `on_finish`/finalization occurs once

### RP37 — cancel retains artifacts and blocks future advance

### RP38 — DONE replay cannot advance

### RP39 — concurrent advance cannot double-process a session

### RP40 — migration fresh/upgrade/downgrade/data-retention passes

### RP41 — Phase 1 BACKTEST/VERIFIED regressions pass

### RP42 — Phase 2A PAPER regressions pass

### RP43 — Phase 2B reconciliation regressions pass

### RP44 — no frontend dependency

---

# 49. Controlled equivalence fixture

Use a small deterministic persisted dataset:

```text
instrument:
NSE:EQUITY:RELIANCE:INR

sessions:
5–10 daily bars

strategy:
simple deterministic signal transition

execution:
fixed BPS = 0

commission:
0

settlement:
T+0 or T+1

seed:
fixed
```

Run as BACKTEST.

Run same economics as REPLAY session-by-session.

Compare normalized canonical output.

Then run another REPLAY with `run_to_end`.

Both REPLAY paths must be equivalent to each other and economically equivalent to BACKTEST.

---

# 50. Status lifecycle

Canonical run status remains:

```text
QUEUED
VALIDATING_DATA
BUILDING_MANIFEST
RUNNING
FINALIZING
DONE
FAILED
CANCELLED
```

Replay control state:

```text
READY
ADVANCING
PAUSED
DONE
FAILED
CANCELLED
```

Suggested mapping:

```text
after create:
  run=RUNNING
  replay=READY

during step:
  run=RUNNING
  replay=ADVANCING

between steps:
  run=RUNNING
  replay=PAUSED

complete:
  run=DONE
  replay=DONE

failure:
  run=FAILED
  replay=FAILED

cancel:
  run=CANCELLED
  replay=CANCELLED
```

---

# 51. No wall-clock scheduler

Do not add a backend replay timer.

A future UI can implement visual playback speed by repeatedly calling:

```text
advance(1)
```

This keeps replay deterministic, testable and restart-safe.

No Celery/Redis timer is required.

---

# 52. Manual/API validation

At completion:

1. create a small VERIFIED replay;
2. GET state;
3. verify cursor before first session;
4. advance one session;
5. inspect events/orders/portfolio;
6. verify replay market history only shows available sessions;
7. advance more;
8. restart service if practical;
9. verify cursor/checkpoint reload;
10. continue;
11. run to end;
12. verify canonical result endpoint;
13. compare against equivalent BACKTEST;
14. create a second replay and verify cancel behavior.

If local market rows are unavailable, use deterministic persisted fixtures.

Do not fabricate provider data.

---

# 53. Testing strategy

Before shared-kernel extraction:

```text
run focused Phase 1 daily-simulator invariants
```

During implementation:

```text
replay domain/state
shared-kernel equivalence
advance
future-data
restart
atomicity
API
migration
```

Then:

```text
Phase 1 deterministic/VERIFIED regressions
Phase 2A PAPER regressions
Phase 2B reconciliation regressions
```

Final exact-tree:

```text
pytest backend/tests/simulation/ -q
Python compile check
git diff --check
git status --short
git diff --stat
```

Run the full backend suite once after targeted/simulation tests are green and if time permits.

If the known Windows temporary-directory issue appears, use repository-local temporary storage and document it.

---

# 54. Non-regression contract

After Phase 2C:

```text
VERIFIED BACKTEST still has no fallback
DailySimulator economics remain unchanged
PAPER accounting remains canonical
PAPER live-tick behavior unchanged
Phase 2B reports remain immutable
Phase 2B matching semantics unchanged
legacy unlinked PAPER portfolios remain legacy
no frontend redesign
no live broker execution
```

---

# 55. Completion criteria

Phase 2C is complete only when:

- REPLAY runs are operational;
- replay requires persisted versioned data;
- daily replay never exposes future bars;
- one-session stepping works;
- batched stepping works;
- run-to-target works;
- run-to-end works;
- restart recovery works;
- strategy state recovers;
- each session is atomic;
- event sequencing survives restart;
- settlement survives restart;
- BACKTEST and REPLAY use one shared daily session kernel;
- normalized BACKTEST/REPLAY equivalence passes;
- step-size invariance passes;
- canonical result finalization works;
- generic artifact APIs work;
- migration upgrade/downgrade works;
- Phase 1/2A/2B regressions remain green;
- no frontend changes are required;
- Phase 3 is not started.

---

# 56. Final Codex report

When complete, stop and report:

## Implementation

Describe:

```text
shared daily session-kernel extraction
replay domain/control state
data policy
cursor/checkpoint design
strategy-state persistence
account restoration
settlement persistence
atomic session transaction
result finalization
API endpoints
```

## BACKTEST preservation

Explicitly state whether any observable `DailySimulator` behavior changed.

Provide before/after focused regression results.

## Equivalence

Report:

```text
BACKTEST vs REPLAY normalized equivalence
step-size invariance
restart invariance
```

## Files

Separate:

```text
created
modified
```

## Migration

Report:

```text
revision
down_revision
tables added
indexes
upgrade
downgrade
Phase 1/2A/2B data retention
```

## Tests

Report exact commands/results:

```text
Phase 2C tests
Phase 1 regressions
Phase 2A PAPER regressions
Phase 2B reconciliation regressions
full simulation suite
compile check
git diff --check
```

If full backend suite is run, report separately.

## Scope confirmation

Explicitly answer:

```text
DailySimulator semantics changed? Yes/No
VERIFIED fallback policy changed? Yes/No
PAPER accounting changed? Yes/No
Phase 2B reconciliation semantics changed? Yes/No
frontend changed? Yes/No
live broker introduced? Yes/No
synthetic replay data introduced? Yes/No
manual replay trading introduced? Yes/No
Phase 3 started? Yes/No
```

## Git

Report:

```text
git status --short
git diff --stat
```

Do not commit or push.

Wait for review.

---

# 57. Codex kickoff prompt

```text
Read Phase_2C_Historical_Replay_Mode.md in docs/architecture/.

Treat:
- OpenTerminalUI_Assessment_and_Direction.md as architectural context
- OpenTerminalUI_Simulation_Implementation_Blueprint.md as the canonical simulation foundation
- Phase 1A through Phase 1E as completed
- Codex_Phase_2A_Canonical_Paper_Trading_Unification.md as completed
- Codex_Phase_2B_Backtest_Paper_Reconciliation_and_Execution_Calibration.md as completed
- Codex_Phase_2C_Historical_Replay_Mode.md as the current implementation task

Implement Phase 2C exactly as specified.

Work only on feat/simulation-core.

Phase 2C makes SimulationMode.REPLAY operational.

Critical rule:
REPLAY is NOT another backtest engine.

Do not copy DailySimulator into replay.

Extract one shared behavior-preserving daily session kernel so:
- BACKTEST uses it in batch mode
- REPLAY uses it incrementally one trading session at a time

Observable BACKTEST semantics must remain unchanged.

REPLAY must:
- use persisted versioned historical data only
- require data_version_id for all replay runs
- reject SYNTHETIC replay
- never use provider/synthetic fallback
- advance one complete daily session atomically
- persist cursor/control state
- persist strategy state needed for deterministic resume
- restore canonical account/open orders/settlements after restart
- use canonical orders/fills/ledger/events/snapshots
- use shared OrderManager/MatchingEngine/AccountEngine/SettlementEngine/ValuationEngine
- expose no future bars to strategy callbacks or replay market APIs
- preserve next-open/no-lookahead timing
- persist settlement obligations so restart is safe
- serialize state-changing calls per replay run
- finalize into normal canonical SimulationResult
- produce normalized economic equivalence with BACKTEST for identical specs
- be invariant to stepping pattern and service restart

The atomic unit is one daily trading session because the current persisted historical source is EOD daily data.

Do not fabricate intraday data.
Do not add backend wall-clock replay timers.
Do not add manual/discretionary replay trading.
Do not redesign frontend.
Do not change PAPER behavior.
Do not change Phase 2B reconciliation behavior.
Do not implement live brokerage.
Do not start Phase 3.

Inspect the real Alembic head before adding the migration.
Use the next valid revision.

Before refactoring DailySimulator, run focused existing Phase 1 invariants.
After extraction, prove those exact behaviors remain green.

Use targeted tests during implementation.
At completion run the required Phase 2C, Phase 1, Phase 2A, Phase 2B, migration, compile, simulation-suite and git checks.

Do not commit or push.

Stop when Phase 2C completion criteria pass and return the full requested report.
```

---

## End of Phase 2C specification
