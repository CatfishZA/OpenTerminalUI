# OpenTerminalUI Simulation Core — Implementation Blueprint

**Repository:** `Hitheshkaranth/OpenTerminalUI`  
**Baseline:** `main` at commit `9a4dd96dfa1e2c8d33db75c759dacfef9379de4e`  
**Blueprint status:** Phase 1 build specification  
**Phase 1 name:** Deterministic Daily Simulation Core  
**Primary objective:** Introduce one authoritative simulation/accounting path without breaking the existing OpenTerminalUI frontend or public backtest workflow.

---

## 1. Engineering decision

Phase 1 will introduce a new repository-owned simulation domain under `backend/simulation/`.

The existing backtest APIs and frontend remain operational.

Verified runs will be routed through the new simulation core.

Legacy engines remain present temporarily but are classified as non-authoritative and are not permitted to produce `VERIFIED` runs.

The new architecture must be capable of supporting a later external execution-kernel adapter without changing:

- API contracts;
- database schema;
- domain objects exposed to application code;
- run manifests;
- frontend result models.

---

# 2. Phase 1 scope

Phase 1 delivers deterministic daily simulation for cash equities with a shared portfolio account.

### Included

- one deterministic event clock;
- explicit information/execution timing;
- one shared multi-asset account;
- market orders;
- limit orders;
- stop orders;
- DAY and GTC time-in-force;
- partial fills based on participation constraints;
- fixed and parameterized slippage;
- commission models;
- cash ledger;
- settled/unsettled cash representation;
- positions;
- realized/unrealized P&L;
- end-of-day NAV snapshots;
- splits;
- cash dividends;
- versioned data requirement;
- run manifests;
- deterministic seeds;
- canonical order/fill/event persistence;
- compatibility with current backtest routes;
- compatibility with existing analytics/result panels.

### Not Phase 1

These are designed for but not required for Phase 1 acceptance:

- tick-level queue simulation;
- L2/L3 order books;
- options exercise/assignment;
- futures margin/roll logic;
- complex portfolio margin;
- locate workflow;
- borrow inventory;
- multi-currency settlement;
- tax optimization;
- live broker connectivity;
- production-grade MOO/MOC/LOO/LOC auction routing;
- intraday historical replay UI;
- calibrated venue queue position.

The data model and interfaces must not block these future capabilities.

---

# 3. Target folder structure

Create the following package.

```text
backend/
├── simulation/
│   ├── __init__.py
│   │
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── enums.py
│   │   ├── identifiers.py
│   │   ├── instruments.py
│   │   ├── market.py
│   │   ├── events.py
│   │   ├── orders.py
│   │   ├── fills.py
│   │   ├── cash.py
│   │   ├── positions.py
│   │   ├── account.py
│   │   ├── corporate_actions.py
│   │   ├── strategy.py
│   │   ├── run.py
│   │   └── results.py
│   │
│   ├── ports/
│   │   ├── __init__.py
│   │   ├── clock.py
│   │   ├── market_data.py
│   │   ├── strategy.py
│   │   ├── execution.py
│   │   ├── fees.py
│   │   ├── corporate_actions.py
│   │   ├── risk.py
│   │   ├── ledger.py
│   │   └── repositories.py
│   │
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── event_clock.py
│   │   ├── dispatcher.py
│   │   ├── order_manager.py
│   │   ├── matching_engine.py
│   │   ├── account_engine.py
│   │   ├── settlement_engine.py
│   │   ├── corporate_action_engine.py
│   │   ├── valuation_engine.py
│   │   ├── daily_simulator.py
│   │   └── result_builder.py
│   │
│   ├── execution/
│   │   ├── __init__.py
│   │   ├── fixed_bps.py
│   │   ├── volume_participation.py
│   │   ├── impact_curve.py
│   │   └── commissions.py
│   │
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── strategy_runner_adapter.py
│   │   ├── versioned_data_adapter.py
│   │   ├── corporate_actions_adapter.py
│   │   ├── legacy_result_adapter.py
│   │   └── websocket_progress_adapter.py
│   │
│   ├── persistence/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── repositories.py
│   │   └── serializers.py
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── simulation_service.py
│   │   ├── manifest_service.py
│   │   └── reconciliation_service.py
│   │
│   └── api/
│       ├── __init__.py
│       ├── schemas.py
│       └── routes.py
│
├── tests/
│   └── simulation/
│       ├── conftest.py
│       ├── fixtures.py
│       ├── test_no_lookahead_daily.py
│       ├── test_deterministic_replay.py
│       ├── test_shared_cash_multi_asset.py
│       ├── test_order_lifecycle.py
│       ├── test_partial_fills.py
│       ├── test_execution_costs.py
│       ├── test_cash_settlement.py
│       ├── test_split_accounting.py
│       ├── test_dividend_accounting.py
│       ├── test_ledger_balance.py
│       ├── test_verified_data_policy.py
│       ├── test_run_manifest.py
│       ├── test_legacy_backtest_api.py
│       └── test_full_exit_realized_pnl.py
│
└── alembic/
    └── versions/
        └── 0009_simulation_core.py
```

If the active migration head changes before implementation, use the next valid Alembic revision number while retaining the descriptive suffix `simulation_core`.

---

# 4. Domain model

The simulation engine must use domain objects that are independent of SQLAlchemy and independent of the current frontend schema.

Use frozen dataclasses or Pydantic models where immutability is valuable.

## 4.1 Identifiers

### `InstrumentId`

```python
@dataclass(frozen=True)
class InstrumentId:
    symbol: str
    venue: str
    asset_class: str
    currency: str
```

Do not use an ambiguous bare symbol as the execution identity.

Examples:

```text
AAPL / NASDAQ / EQUITY / USD
RELIANCE / NSE / EQUITY / INR
```

### `AccountId`

String/UUID wrapper.

### `RunId`

Canonical simulation-run ID, e.g.:

```text
sim_4f3c6db0b13e
```

---

# 5. Core enums

Create in `backend/simulation/domain/enums.py`.

Required Phase 1 enums:

```text
SimulationMode
    BACKTEST
    REPLAY
    PAPER
    LIVE

VerificationLevel
    VERIFIED
    RESEARCH
    SYNTHETIC

OrderSide
    BUY
    SELL

OrderType
    MARKET
    LIMIT
    STOP

TimeInForce
    DAY
    GTC

OrderStatus
    CREATED
    ACCEPTED
    PARTIALLY_FILLED
    FILLED
    CANCELLED
    EXPIRED
    REJECTED

EventType
    SESSION_START
    SETTLEMENT
    CORPORATE_ACTION
    BAR_OPEN
    STRATEGY_CALLBACK
    ORDER_SUBMITTED
    ORDER_ACCEPTED
    ORDER_REJECTED
    ORDER_TRIGGERED
    ORDER_PARTIAL_FILL
    ORDER_FILL
    ORDER_CANCELLED
    ORDER_EXPIRED
    BAR_CLOSE
    MARK
    LEDGER_ENTRY
    PORTFOLIO_SNAPSHOT
    SESSION_END

LedgerEntryType
    CASH_DEPOSIT
    CASH_WITHDRAWAL
    TRADE_PRINCIPAL
    COMMISSION
    FEE
    DIVIDEND
    INTEREST
    BORROW_FEE
    SETTLEMENT
    CORPORATE_ACTION
    CASH_IN_LIEU
```

---

# 6. Market-data objects

## `MarketBar`

```python
@dataclass(frozen=True)
class MarketBar:
    instrument: InstrumentId
    ts_open: datetime
    ts_close: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    data_version_id: str
```

Important rule:

> `MarketBar.close` is not available to a strategy until `ts_close`.

The engine must enforce event availability.

## `MarketDataManifest`

Contains:

- `data_version_id`;
- dataset hash;
- symbol/venue coverage;
- date range;
- data source;
- adjusted/unadjusted flag;
- calendar version;
- corporate-action version;
- missing-data summary.

---

# 7. Strategy-domain objects

The legacy `StrategyRunner` can remain the strategy execution mechanism initially, but it must be wrapped behind a new interface.

## `StrategyContext`

Exposes only information available at the current event time.

Required methods/properties:

```python
ctx.now
ctx.account
ctx.positions
ctx.cash
ctx.market.history(...)
ctx.orders.market(...)
ctx.orders.limit(...)
ctx.orders.stop(...)
ctx.orders.cancel(...)
ctx.orders.target_quantity(...)
ctx.orders.target_percent(...)
```

The strategy does not mutate the account directly.

## `StrategyIntent`

The strategy adapter converts the current catalog's signal outputs into explicit order intents.

For an existing daily target-position strategy:

```text
signal generated at T close
→ intent timestamp = T close
→ earliest normal execution = T+1 open
```

This rule eliminates implicit same-close fills.

---

# 8. Order object

Create `backend/simulation/domain/orders.py`.

```python
@dataclass(frozen=True)
class Order:
    id: str
    run_id: str
    account_id: str
    instrument: InstrumentId
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    remaining_quantity: Decimal
    tif: TimeInForce
    submitted_at: datetime
    accepted_at: datetime | None
    limit_price: Decimal | None
    stop_price: Decimal | None
    status: OrderStatus
    strategy_order_id: str | None
    parent_order_id: str | None
    metadata: dict[str, Any]
```

Order state changes must be represented by events rather than mutating history.

---

# 9. Fill object

Create `backend/simulation/domain/fills.py`.

```python
@dataclass(frozen=True)
class Fill:
    id: str
    run_id: str
    order_id: str
    account_id: str
    instrument: InstrumentId
    side: OrderSide
    quantity: Decimal
    price: Decimal
    executed_at: datetime
    commission: Decimal
    fees: Decimal
    slippage_bps: Decimal
    liquidity_flag: str | None
    execution_model: str
```

A fill is immutable.

Positions and P&L must be derivable from fills plus account events.

---

# 10. Account model

Create `backend/simulation/domain/account.py`.

## `AccountState`

```python
@dataclass
class AccountState:
    account_id: str
    base_currency: str
    cash: dict[str, CashBalance]
    positions: dict[InstrumentId, Position]
    open_orders: dict[str, Order]
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    equity: Decimal
    buying_power: Decimal
```

For Phase 1, use a cash-account model with configurable settlement delay.

Do not allow each asset to own an independent cash balance.

---

# 11. Cash and settlement

`CashBalance` should represent at minimum:

```text
settled
unsettled_receivable
unsettled_payable
reserved
available
```

Phase 1 should support a configurable settlement cycle.

Example:

```text
US equity: T+1
configured test venue: T+0/T+2 for fixtures
```

The engine's accounting must distinguish a trade's economic execution time from its settlement time.

---

# 12. Position object

Create `backend/simulation/domain/positions.py`.

Required fields:

```text
instrument
quantity
average_cost
realized_pnl
unrealized_pnl
market_value
last_mark
```

Phase 1 can use weighted-average cost internally.

Future lot-specific accounting can plug into the same fill/ledger stream.

---

# 13. Ledger model

The ledger is authoritative.

Every change in account value that is not merely mark-to-market must produce a ledger entry.

## `LedgerEntry`

```python
@dataclass(frozen=True)
class LedgerEntry:
    id: str
    run_id: str
    account_id: str
    ts: datetime
    entry_type: LedgerEntryType
    currency: str
    amount: Decimal
    instrument: InstrumentId | None
    order_id: str | None
    fill_id: str | None
    corporate_action_id: str | None
    metadata: dict[str, Any]
```

Required invariant:

```text
ending cash
=
starting cash
+ deposits
- withdrawals
- purchase principal
+ sale principal
- commissions
- fees
+ dividends
+ interest
- borrow charges
+/- corporate-action cash
```

The acceptance suite must verify this identity.

---

# 14. Corporate-action objects

Create `backend/simulation/domain/corporate_actions.py`.

Phase 1:

```text
SPLIT
CASH_DIVIDEND
```

Required fields:

```text
id
instrument
action_type
ex_date
record_date
pay_date
factor
cash_amount
currency
data_version_id
```

The existing `CorpActionORM` and `corp_actions_service.py` remain the source adapter.

The simulation engine applies account effects.

Adjusted bars must not substitute for actual account events in verified accounting.

---

# 15. Run specification and manifest

## `SimulationRunSpec`

Create in `backend/simulation/domain/run.py`.

Required fields:

```text
mode
verification_level
strategy
strategy_context
universe
start
end
initial_cash
base_currency
data_version_id
execution_profile
commission_profile
settlement_profile
seed
benchmark
```

## `RunManifest`

Generated before execution.

Required manifest values:

```text
run_id
engine_version
git_commit
strategy_hash
strategy_key
strategy_context_hash
data_version_id
dataset_hash
universe_hash
corporate_actions_hash
calendar_version
execution_profile_hash
commission_profile_hash
settlement_profile_hash
seed
request_hash
created_at
```

The manifest must be immutable once a run enters `RUNNING`.

---

# 16. Event journal

Each run receives a strictly ordered event stream.

## Required fields

```text
run_id
sequence
event_id
event_type
event_time
processing_time
instrument_id
order_id
fill_id
payload
```

The pair `(run_id, sequence)` must be unique.

The `sequence` value is the deterministic order of processing.

For equal timestamps, event priority is controlled by the event clock.

---

# 17. Daily event priority

Phase 1 deterministic order:

```text
10 SESSION_START
20 SETTLEMENT
30 CORPORATE_ACTION
40 BAR_OPEN
50 OPEN_ORDER_MATCH
60 STRATEGY_OPEN_CALLBACK
70 INTRADAY_ORDER_PROCESSING
80 BAR_CLOSE
90 STRATEGY_CLOSE_CALLBACK
100 POST_CLOSE_ORDER_VALIDATION
110 MARK
120 VALUATION
130 PORTFOLIO_SNAPSHOT
140 SESSION_END
```

A close-based strategy callback occurs **after** `BAR_CLOSE`.

Orders created by that callback cannot execute against that already-completed close unless the strategy explicitly used a pre-close/auction event available before the close.

Phase 1 default behavior:

```text
daily close signal
→ next session open execution
```

---

# 18. Execution interfaces

Create protocols under `backend/simulation/ports/`.

## 18.1 `ExecutionModel`

```python
class ExecutionModel(Protocol):
    def match(
        self,
        order: Order,
        market_event: MarketBar,
        account: AccountState,
    ) -> list[Fill]:
        ...
```

Execution models may not mutate account state directly.

They produce fills.

The account engine consumes fills.

## 18.2 `CommissionModel`

```python
class CommissionModel(Protocol):
    def calculate(self, order: Order, fill_quantity: Decimal, fill_price: Decimal) -> Decimal:
        ...
```

## 18.3 `MarketDataSource`

```python
class MarketDataSource(Protocol):
    def manifest(self) -> MarketDataManifest:
        ...

    def iter_daily_events(
        self,
        instruments: list[InstrumentId],
        start: date,
        end: date,
    ) -> Iterable[MarketEvent]:
        ...
```

## 18.4 `StrategyAdapter`

```python
class StrategyAdapter(Protocol):
    def on_start(self, ctx: StrategyContext) -> None:
        ...

    def on_event(self, ctx: StrategyContext, event: SimulationEvent) -> list[StrategyIntent]:
        ...

    def on_finish(self, ctx: StrategyContext) -> None:
        ...
```

## 18.5 `CorporateActionSource`

```python
class CorporateActionSource(Protocol):
    def events(
        self,
        instruments: list[InstrumentId],
        start: date,
        end: date,
        data_version_id: str,
    ) -> Iterable[CorporateAction]:
        ...
```

## 18.6 `EventStore`

```python
class EventStore(Protocol):
    def append(self, event: SimulationEvent) -> None:
        ...

    def iter_run(self, run_id: str) -> Iterable[SimulationEvent]:
        ...
```

---

# 19. Execution models in Phase 1

Reuse concepts from `backend/core/execution_model.py`, but implement them behind the new interface.

## `FixedBpsExecutionModel`

Parameters:

```text
slippage_bps
max_participation
```

## `VolumeParticipationExecutionModel`

Parameters:

```text
max_participation
base_slippage_bps
volume_weighted_bps
```

Partial fill:

```text
maximum_fill_quantity = bar_volume × max_participation
```

If an order remains after the fill:

- DAY orders may remain active until session end;
- GTC orders carry to the next session;
- the remaining quantity is never silently discarded.

## `ImpactCurveExecutionModel`

Phase 1 may carry forward the current square-root-style impact calculation but must expose all parameters in the run manifest.

---

# 20. Matching rules

## Market order

Daily mode default:

```text
submitted after T close
→ eligible at T+1 open
```

Fill price:

```text
open ± execution slippage
```

## Limit buy

Eligible when market path definitively reaches or improves through the limit.

With daily bars, Phase 1 uses a documented deterministic assumption:

- if `open <= limit`, fill from the open subject to slippage rules;
- otherwise if `low <= limit`, fill at the limit subject to the configured daily-bar path rule.

Every result must state the bar-path assumption in the manifest.

## Limit sell

Mirror of limit buy.

## Stop order

Stops must not silently use favorable ordering when the daily OHLC cannot determine intrabar chronology.

Phase 1 manifest field:

```text
daily_bar_path_policy
```

Supported initial values:

```text
OHLC
OLHC
WORST_CASE
```

`WORST_CASE` should be the default VERIFIED policy when both stop and favorable target conditions are touched and order is ambiguous.

Future minute/tick data removes this ambiguity.

---

# 21. New database schema

Create models in:

`backend/simulation/persistence/models.py`

Add the models to the central import path used by metadata creation.

Create migration:

`backend/alembic/versions/0009_simulation_core.py`

or next available revision.

## 21.1 `simulation_runs`

| Column | Type | Notes |
|---|---|---|
| id | string(64) PK | `sim_*` |
| legacy_backtest_run_id | string(64) nullable | compatibility |
| mode | string(16) | BACKTEST/REPLAY/PAPER/LIVE |
| verification_level | string(16) | VERIFIED/RESEARCH/SYNTHETIC |
| status | string(16) | queued/running/done/failed |
| strategy_key | string(160) | |
| strategy_hash | string(128) | SHA-256 |
| code_hash | string(128) | Git revision/content hash |
| data_version_id | FK data_versions | required for VERIFIED |
| engine_version | string(64) | |
| seed | bigint | |
| request_json | JSON | canonical request |
| manifest_json | JSON | immutable after start |
| error | text | |
| created_at | datetime | |
| started_at | datetime nullable | |
| finished_at | datetime nullable | |

Indexes:

```text
status
strategy_key
data_version_id
created_at
legacy_backtest_run_id
```

## 21.2 `simulation_events`

| Column | Type |
|---|---|
| id | bigint PK |
| run_id | FK simulation_runs |
| sequence | bigint |
| event_id | string(64) |
| event_type | string(64) |
| event_time | datetime |
| instrument_key | string(160) nullable |
| order_id | string(64) nullable |
| fill_id | string(64) nullable |
| payload_json | JSON |

Constraint:

```text
UNIQUE(run_id, sequence)
```

Index:

```text
(run_id, event_time)
(run_id, event_type)
```

## 21.3 `simulation_orders`

| Column | Type |
|---|---|
| id | string(64) PK |
| run_id | FK |
| account_id | string(64) |
| instrument_key | string(160) |
| side | string(8) |
| order_type | string(16) |
| quantity | numeric |
| remaining_quantity | numeric |
| tif | string(8) |
| limit_price | numeric nullable |
| stop_price | numeric nullable |
| status | string(24) |
| submitted_at | datetime |
| accepted_at | datetime nullable |
| completed_at | datetime nullable |
| metadata_json | JSON |

## 21.4 `simulation_fills`

| Column | Type |
|---|---|
| id | string(64) PK |
| run_id | FK |
| order_id | FK simulation_orders |
| account_id | string(64) |
| instrument_key | string(160) |
| side | string(8) |
| quantity | numeric |
| price | numeric |
| commission | numeric |
| fees | numeric |
| slippage_bps | numeric |
| executed_at | datetime |
| execution_model | string(64) |
| metadata_json | JSON |

## 21.5 `simulation_ledger_entries`

| Column | Type |
|---|---|
| id | string(64) PK |
| run_id | FK |
| account_id | string(64) |
| event_time | datetime |
| entry_type | string(32) |
| currency | string(8) |
| amount | numeric |
| instrument_key | string(160) nullable |
| order_id | string(64) nullable |
| fill_id | string(64) nullable |
| corporate_action_id | string(64) nullable |
| metadata_json | JSON |

## 21.6 `simulation_position_snapshots`

End-of-day snapshots.

Columns:

```text
id
run_id
account_id
snapshot_time
instrument_key
quantity
average_cost
mark_price
market_value
realized_pnl
unrealized_pnl
```

Unique:

```text
(run_id, snapshot_time, instrument_key)
```

## 21.7 `simulation_portfolio_snapshots`

Columns:

```text
id
run_id
account_id
snapshot_time
cash_settled
cash_unsettled
cash_reserved
gross_exposure
net_exposure
market_value
realized_pnl
unrealized_pnl
fees
equity
buying_power
```

Unique:

```text
(run_id, snapshot_time)
```

## 21.8 `simulation_applied_corporate_actions`

Tracks exactly which action was applied.

Columns:

```text
id
run_id
corporate_action_source_id
instrument_key
action_type
effective_time
payload_json
```

Unique:

```text
(run_id, corporate_action_source_id)
```

---

# 22. Existing database structures to retain

Do not remove:

- `data_versions`;
- point-in-time fundamentals tables;
- universe membership tables;
- corporate-action source tables;
- current `backtest_runs`;
- model-lab tables;
- portfolio-lab tables;
- virtual/paper tables during migration.

`backtest_runs` remains the compatibility record while the frontend/API migration is in progress.

Add a link to the new `simulation_runs.id`.

---

# 23. API contracts

Create canonical routes in:

`backend/simulation/api/routes.py`

Mount under:

```text
/api/v1/simulation
```

## 23.1 Create run

### `POST /api/v1/simulation/runs`

Request:

```json
{
  "mode": "BACKTEST",
  "verification_level": "VERIFIED",
  "strategy": {
    "key": "example:sma_crossover",
    "context": {
      "short_window": 20,
      "long_window": 50
    }
  },
  "universe": [
    {
      "symbol": "AAPL",
      "venue": "NASDAQ",
      "asset_class": "EQUITY",
      "currency": "USD"
    }
  ],
  "start": "2020-01-01",
  "end": "2025-12-31",
  "account": {
    "initial_cash": 100000,
    "base_currency": "USD",
    "settlement_days": 1
  },
  "data_version_id": "uuid",
  "execution": {
    "model": "volume_participation",
    "max_participation": 0.10,
    "base_slippage_bps": 2.0,
    "daily_bar_path_policy": "WORST_CASE"
  },
  "commission": {
    "model": "bps",
    "bps": 1.0,
    "minimum": 0.0
  },
  "seed": 42
}
```

Response:

```json
{
  "run_id": "sim_4f3c6db0b13e",
  "status": "queued",
  "verification_level": "VERIFIED"
}
```

## 23.2 Run status

### `GET /api/v1/simulation/runs/{run_id}/status`

Response:

```json
{
  "run_id": "sim_4f3c6db0b13e",
  "status": "running",
  "progress": 62,
  "stage": "processing 2023-06-14"
}
```

## 23.3 Run result

### `GET /api/v1/simulation/runs/{run_id}`

Response contains:

```text
manifest
summary
equity_curve
drawdown
daily_returns
trades
orders
data_quality
```

Do not embed the full event journal by default.

## 23.4 Orders

### `GET /api/v1/simulation/runs/{run_id}/orders`

Supports pagination and filters.

## 23.5 Fills

### `GET /api/v1/simulation/runs/{run_id}/fills`

## 23.6 Ledger

### `GET /api/v1/simulation/runs/{run_id}/ledger`

## 23.7 Events

### `GET /api/v1/simulation/runs/{run_id}/events`

Query parameters:

```text
from_sequence
to_sequence
event_type
instrument
limit
```

## 23.8 Portfolio snapshots

### `GET /api/v1/simulation/runs/{run_id}/portfolio`

## 23.9 Position snapshots

### `GET /api/v1/simulation/runs/{run_id}/positions`

## 23.10 Manifest

### `GET /api/v1/simulation/runs/{run_id}/manifest`

This is a first-class endpoint because reproducibility is a product feature.

---

# 24. Existing API compatibility

Modify:

`backend/api/routes/backtests.py`

Do not remove existing endpoints.

### Existing

```text
POST /backtests
GET  /backtests/{run_id}/status
GET  /backtests/{run_id}/result
POST /v1/backtest/submit
GET  /v1/backtest/status/{run_id}
GET  /v1/backtest/result/{run_id}
```

### New behavior

These routes should:

1. translate the legacy request into a `SimulationRunSpec`;
2. call `SimulationService.submit()`;
3. store/map the resulting `simulation_run_id`;
4. adapt the canonical simulation result back to the current `BacktestResultResponse`.

This preserves the current frontend while the frontend migrates to the richer API.

---

# 25. Job service migration

Modify:

`backend/services/backtest_jobs.py`

### Remove from verified execution

- direct use of `BacktestEngine`;
- synthetic frame creation;
- automatic market fallback;
- direct `historical_data_service` dependency for verified runs.

### New role

`BacktestJobService` becomes a compatibility facade.

Pseudo-flow:

```python
async def submit(self, req: BacktestJobRequest) -> str:
    legacy_run_id = create_legacy_row(req)
    spec = legacy_request_adapter.to_simulation_spec(req)
    simulation_run_id = await simulation_service.submit(spec)
    link_legacy_to_simulation(legacy_run_id, simulation_run_id)
    return legacy_run_id
```

Status/result calls proxy to the linked simulation run.

---

# 26. Versioned data adapter

Create:

`backend/simulation/adapters/versioned_data_adapter.py`

This adapter should use:

- `backend/services/price_series_service.py`;
- existing active `data_version_id`;
- existing point-in-time universe service;
- existing corporate-action service.

### Verified policy

For `VERIFIED`:

- `data_version_id` is mandatory;
- price history must come from versioned persisted rows;
- no external provider fetch may silently fill missing history during the run;
- no synthetic data;
- no market substitution;
- missing required data fails the run.

### Research policy

For `RESEARCH`:

- provider retrieval may be allowed;
- results receive an explicit non-verified data-quality status.

---

# 27. Corporate-action adapter

Create:

`backend/simulation/adapters/corporate_actions_adapter.py`

Use existing corporate-action tables/services as source data.

Phase 1 behavior:

### Split

If:

```text
2-for-1 split
```

then:

```text
quantity × 2
average cost ÷ 2
total cost basis unchanged
```

Open orders must also be adjusted or cancelled according to the selected policy.

### Cash dividend

On the configured entitlement/pay-date rules:

```text
cash += eligible_shares × dividend_per_share
```

Produce:

- corporate-action event;
- ledger entry;
- event-journal entry.

---

# 28. Strategy adapter

Create:

`backend/simulation/adapters/strategy_runner_adapter.py`

Reuse:

`backend/core/strategy_runner.py`

The initial adapter converts existing integer signals into target-position intents.

Example:

```text
1  → long target
0  → flat
-1 → short target if allowed by run/account policy
```

Critical timing rule:

A signal calculated from bar T may only create orders after all fields used by that signal are available.

Default daily adapter:

```text
on BAR_CLOSE(T)
    calculate signal
    create order intent

on BAR_OPEN(T+1)
    order becomes executable
```

---

# 29. Legacy result adapter

Create:

`backend/simulation/adapters/legacy_result_adapter.py`

It converts canonical objects into the response shape currently expected by:

- `frontend/src/pages/Backtesting.tsx`;
- existing analytics functions;
- current `/backtests/{id}/result` endpoint.

Fields to preserve include:

```text
symbol
asset
bars
initial_cash
final_equity
pnl_amount
ending_cash
total_return
max_drawdown
sharpe
sortino
calmar
omega
profit_factor
win_rate
avg_win
avg_loss
VaR/CVaR fields
daily_returns
drawdown_series
rolling_metrics
trades
equity_curve
```

Where a legacy metric cannot be computed correctly, do not invent it.

---

# 30. Exact existing file treatment

## 30.1 Keep as core product assets

These stay and continue to be used:

```text
frontend/src/pages/Backtesting.tsx
frontend/src/components/backtesting/
frontend/src/components/portfolio/
frontend/src/pages/ModelLab.tsx
frontend/src/pages/ModelGovernance.tsx

backend/core/strategy_runner.py
backend/core/backtest_analytics.py
backend/core/backtest_robustness.py
backend/core/monte_carlo.py
backend/core/walk_forward.py
backend/core/factor_analysis.py
backend/core/vectorized_backtest.py

backend/api/routes/data_layer.py
backend/services/data_version_service.py
backend/services/price_series_service.py
backend/services/pit_fundamentals_service.py
backend/services/corp_actions_service.py

backend/shared/db.py
backend/models/
backend/alembic/
backend/shared/ws_manager.py
```

## 30.2 Modify

```text
backend/api/routes/backtests.py
```

Role: compatibility facade + canonical simulation routing.

```text
backend/services/backtest_jobs.py
```

Role: compatibility job wrapper; no authoritative execution.

```text
backend/core/strategy_runner.py
```

Role: strategy generation only; add adapter-safe output/timing metadata where required.

```text
backend/services/price_series_service.py
```

Add strict persisted-version mode. No provider fallback during VERIFIED simulation.

```text
backend/services/corp_actions_service.py
```

Add canonical action conversion for simulator use.

```text
backend/models/__init__.py
```

Export new simulation persistence models if required by current metadata conventions.

```text
backend/api/router.py
```

Mount `/v1/simulation` router.

```text
frontend/src/api/client.ts
```

Add simulation run/manifest/detail APIs.

```text
frontend/src/pages/Backtesting.tsx
```

Add:
- verification badge;
- data-version display;
- engine version;
- manifest link;
- execution assumptions;
- data-quality failure messaging.

## 30.3 Deprecate as authoritative engines

Keep temporarily for regression comparison:

```text
backend/core/single_asset_backtest.py
backend/core/portfolio_backtest.py
backend/portfolio_backtests/engine.py
backend/core/execution_model.py
backend/execution_sim/simulator.py
```

Rule:

> No new VERIFIED run may call these implementations directly.

They may remain callable by explicit legacy/research routes until migration completes.

## 30.4 Replace in Phase 2 after Phase 1 stability

```text
backend/paper_trading/service.py
```

The paper-trading API will eventually become a live-clock adapter over the same OMS/ledger.

Do not rewrite this in Phase 1 unless required to fix a production defect.

## 30.5 Harden governance after canonical runs exist

```text
backend/experiments/service.py
```

Replace dummy/scaffold run metadata with actual simulation manifest values.

Model promotion should reference a verified `simulation_run_id`.

---

# 31. `SimulationService` interface

Create:

`backend/simulation/services/simulation_service.py`

Suggested interface:

```python
class SimulationService:
    async def submit(self, spec: SimulationRunSpec) -> str:
        ...

    async def status(self, run_id: str) -> SimulationRunStatus:
        ...

    async def result(self, run_id: str) -> SimulationResult:
        ...

    async def manifest(self, run_id: str) -> RunManifest:
        ...

    async def orders(self, run_id: str, ...) -> list[Order]:
        ...

    async def fills(self, run_id: str, ...) -> list[Fill]:
        ...

    async def events(self, run_id: str, ...) -> list[SimulationEvent]:
        ...

    async def ledger(self, run_id: str, ...) -> list[LedgerEntry]:
        ...
```

The job scheduler implementation may initially remain an in-process asyncio queue to minimize scope.

A distributed worker can be introduced later without changing the service contract.

---

# 32. Daily simulator algorithm

Create:

`backend/simulation/engine/daily_simulator.py`

Conceptual loop:

```python
for session in calendar.sessions(start, end):
    dispatch(SESSION_START)

    settlement_engine.process(session)
    corporate_action_engine.process(session)

    for instrument in universe:
        dispatch(BAR_OPEN)

    order_manager.match_open_eligible_orders()

    strategy_adapter.on_open_events()

    # Phase 1 has no full intraday path unless order rules require
    # deterministic daily-bar path handling.

    for instrument in universe:
        dispatch(BAR_CLOSE)

    strategy_adapter.on_close_events()

    order_manager.validate_new_orders_for_next_eligibility()

    valuation_engine.mark_all_positions()
    account_engine.compute_equity()
    persist_portfolio_snapshot()
    persist_position_snapshots()

    expire_day_orders()
    dispatch(SESSION_END)
```

No event may be processed before its market-information timestamp.

---

# 33. Determinism requirements

Given:

- identical run specification;
- identical data version;
- identical code hash;
- identical engine version;
- identical seed;

the following must be byte-for-byte or value-for-value identical:

- ordered events;
- order states;
- fills;
- ledger entries;
- position snapshots;
- portfolio snapshots;
- final equity;
- run manifest hash.

Current system time must not affect a completed historical run except for metadata fields explicitly excluded from the deterministic hash.

---

# 34. Decimal policy

Do not use binary floating point for ledger-critical monetary arithmetic.

Use `Decimal` in:

- cash;
- order price;
- fill price;
- commission;
- fees;
- realized P&L;
- dividend cash;
- ledger amounts.

Market-research analytics can convert to NumPy floats after the canonical accounting result is created.

---

# 35. Instrument identity policy

Do not use ambiguous ticker strings internally.

Canonical key:

```text
{venue}:{asset_class}:{symbol}:{currency}
```

Example:

```text
NASDAQ:EQUITY:AAPL:USD
NSE:EQUITY:RELIANCE:INR
```

The adapter may still expose display symbols to the frontend.

---

# 36. Data quality contract

Before a VERIFIED run starts, validate:

- requested instrument exists;
- venue matches instrument;
- requested sessions have a calendar;
- required price bars exist;
- bar timestamps are monotonic;
- no duplicate session bars;
- OHLC values satisfy basic invariants;
- volume is non-negative;
- corporate-action records are internally valid;
- data version exists;
- no synthetic provenance;
- data range covers the requested run.

Failure returns a structured data-quality error.

No implicit fallback.

---

# 37. Run status lifecycle

Canonical states:

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

Existing legacy API can map these to its simpler status values.

---

# 38. Frontend changes for Phase 1

The existing Backtesting UI remains.

Add a compact run provenance section containing:

```text
Verification: VERIFIED
Data version: <id/name>
Engine: sim-daily-v1
Git commit: <hash>
Execution: volume_participation
Slippage: ...
Commission: ...
Settlement: T+1
Daily path: WORST_CASE
Seed: 42
Manifest: View
```

On data failure, show the actual missing/inconsistent data instead of launching synthetic history.

Add links/tabs for:

- orders;
- fills;
- ledger;
- event timeline.

These can initially be lightweight table views.

---

# 39. Existing analytics integration

The canonical `SimulationResult` should expose:

```text
equity_curve
daily_returns
trades/round_trips
drawdown
portfolio_snapshots
```

The existing analytics functions can consume an adapted form.

Important distinction:

- canonical records = orders, fills, ledger, positions, snapshots;
- derived analytics = Sharpe, Sortino, drawdown, win rate, etc.

Derived analytics must never be the source of account state.

---

# 40. Phase 1 acceptance tests

Phase 1 is not complete until the following tests pass.

---

## AT-01 — No same-close look-ahead

**File:** `backend/tests/simulation/test_no_lookahead_daily.py`

Fixture:

```text
Day 1 close = 100
Day 2 open  = 120
```

Strategy creates BUY signal using Day 1 completed close.

Expected:

```text
signal time = Day 1 close
order submitted >= Day 1 close
fill time = Day 2 open
fill base price = 120
```

Forbidden:

```text
fill price based on Day 1 close = 100
```

---

## AT-02 — Deterministic replay

**File:** `test_deterministic_replay.py`

Run the same fixture twice with identical:

- run spec;
- seed;
- data version;
- strategy;
- engine version.

Expected identical:

- event sequence;
- orders;
- fills;
- ledger;
- snapshots;
- final equity;
- deterministic result hash.

---

## AT-03 — Data-version requirement

**File:** `test_verified_data_policy.py`

Attempt VERIFIED run without `data_version_id`.

Expected:

```text
run rejected before execution
error code = DATA_VERSION_REQUIRED
```

---

## AT-04 — Synthetic data prohibited

Force missing persisted historical data.

Expected VERIFIED result:

```text
FAILED
error code = VERIFIED_DATA_MISSING
```

The engine must not call synthetic OHLC generation.

---

## AT-05 — No automatic market substitution

Request:

```text
symbol = ABC
venue = NASDAQ
```

Provide data only for another venue.

Expected:

```text
FAILED
error code = INSTRUMENT_DATA_NOT_FOUND
```

The engine may not silently execute a different venue.

---

## AT-06 — Shared cash across assets

**File:** `test_shared_cash_multi_asset.py`

Initial cash:

```text
100,000
```

Two strategies simultaneously request:

```text
AAPL purchase = 70,000
MSFT purchase = 70,000
```

Expected:

- total accepted purchases cannot exceed available account resources;
- second order is resized/rejected according to configured risk policy;
- no separate per-symbol capital accounts.

---

## AT-07 — Partial fill lifecycle

**File:** `test_partial_fills.py`

Order:

```text
BUY 10,000 shares
```

Bar volume:

```text
20,000
```

Participation:

```text
10%
```

Maximum fill:

```text
2,000 shares
```

Expected first event:

```text
filled = 2,000
remaining = 8,000
status = PARTIALLY_FILLED
```

For GTC, remaining quantity continues into the next eligible session.

For DAY, it expires at session end if still open.

---

## AT-08 — Commission and cash identity

**File:** `test_execution_costs.py`

Fixture contains one purchase and one sale with known commissions.

Expected:

```text
ending cash
=
starting cash
- buy principal
- buy commission
+ sell principal
- sell commission
```

Exact Decimal equality within currency precision.

---

## AT-09 — Full-exit realized P&L

**File:** `test_full_exit_realized_pnl.py`

Buy:

```text
100 shares @ 10
```

Sell entire position:

```text
100 shares @ 12
```

No fees.

Expected:

```text
realized P&L = 200
ending position = 0
average cost = 0 after realization
```

P&L must be calculated from pre-exit cost basis/fills, not the already-reset position.

---

## AT-10 — Split accounting

**File:** `test_split_accounting.py`

Before split:

```text
100 shares
average cost = 50
```

2-for-1 split.

Expected:

```text
200 shares
average cost = 25
total cost basis unchanged = 5,000
```

Ledger/event history includes the applied corporate action.

---

## AT-11 — Cash dividend

**File:** `test_dividend_accounting.py`

Eligible holdings:

```text
100 shares
dividend = 1.50/share
```

Expected:

```text
cash increase = 150
ledger entry = DIVIDEND +150
```

No change to share quantity.

---

## AT-12 — Settlement

**File:** `test_cash_settlement.py`

With T+1 settlement:

- sale executes on session T;
- economic P&L is recognized;
- sale proceeds enter unsettled receivable;
- proceeds move to settled cash on T+1.

The snapshot must expose both values.

---

## AT-13 — Ledger reconciliation

**File:** `test_ledger_balance.py`

For a multi-trade run:

Expected:

```text
reconstructed cash from ledger == account cash
reconstructed positions from fills/actions == position snapshot
NAV == cash + marked positions
```

All three must reconcile.

---

## AT-14 — Event ordering

For every run:

```text
sequence strictly increases
```

and events with equal timestamps follow the configured event priority.

A strategy callback may not precede the market event containing the data it consumes.

---

## AT-15 — Legacy API compatibility

**File:** `test_legacy_backtest_api.py`

Existing call:

```text
POST /api/backtests
```

must still return:

```json
{
  "run_id": "...",
  "status": "queued"
}
```

Current status/result endpoints must continue to work.

The underlying execution must come from the new simulation engine.

---

## AT-16 — Existing frontend result contract

A simulation run adapted through `legacy_result_adapter.py` must provide all fields required by the current `Backtesting.tsx` flow.

Frontend smoke/e2e tests must not regress.

---

## AT-17 — Manifest integrity

**File:** `test_run_manifest.py`

After run starts, modifying:

- strategy parameters;
- data version;
- execution assumptions;
- commission assumptions;
- seed;

must produce a different manifest hash.

Attempting to mutate an already-running manifest must fail.

---

## AT-18 — Missing-data failure explains itself

A verified run missing a session must return structured error details:

```json
{
  "code": "VERIFIED_DATA_MISSING",
  "instrument": "NASDAQ:EQUITY:AAPL:USD",
  "missing_sessions": ["2024-03-14"]
}
```

No generic "backtest failed" response.

---

# 41. Phase 1 migration tests against legacy engine

We should run a set of intentionally simple cases where legacy and new results are expected to agree.

Examples:

- buy-and-hold from next open;
- no fees;
- no corporate actions;
- single asset;
- no ambiguous stop/limit behavior.

These are not intended to prove the legacy engine correct.

They ensure the API/result adapter did not accidentally alter straightforward cases.

For cases involving known legacy look-ahead behavior, expected results should intentionally differ and the difference should be documented.

---

# 42. Performance target for Phase 1

Correctness is the priority.

Initial target:

```text
10 years
500 daily instruments
~1.25 million instrument/session bars
```

A standard fixed-strategy run should complete within an operationally acceptable interactive batch window on a developer workstation.

Do not sacrifice event/accounting correctness to hit a premature micro-benchmark.

Optimization can follow using:

- vectorized preprocessing;
- Polars;
- PyArrow;
- DuckDB;
- batch event generation;
- compiled execution kernels.

Canonical ledger/event semantics must remain unchanged.

---

# 43. Logging and observability

Every run should log structured stages:

```text
validate_data
resolve_instruments
build_manifest
load_market_events
load_corporate_actions
initialize_account
run_sessions
finalize_account
calculate_metrics
persist_result
```

WebSocket progress currently used by `backtest_jobs.py` should be preserved through:

`backend/simulation/adapters/websocket_progress_adapter.py`

---

# 44. Error taxonomy

Create stable codes.

Minimum:

```text
DATA_VERSION_REQUIRED
DATA_VERSION_NOT_FOUND
INSTRUMENT_NOT_FOUND
INSTRUMENT_DATA_NOT_FOUND
VERIFIED_DATA_MISSING
INVALID_OHLC
DUPLICATE_BAR
INVALID_CORPORATE_ACTION
INSUFFICIENT_CASH
INVALID_ORDER
ORDER_REJECTED
UNSUPPORTED_ORDER_TYPE
UNSUPPORTED_ASSET_CLASS
ENGINE_INVARIANT_FAILED
LEDGER_RECONCILIATION_FAILED
```

Frontend messages should use these codes rather than parsing arbitrary exception strings.

---

# 45. Security and strategy sandbox

The current strategy runner already includes sandbox-related logic.

Phase 1 must preserve that boundary.

Strategy code receives:

- immutable market context;
- account read model;
- order API.

It must not receive:

- SQLAlchemy session;
- raw persistence repositories;
- event-store mutation capability;
- future market rows.

---

# 46. Governance integration

After a VERIFIED run completes, Model Governance should store/reference:

```text
simulation_run_id
manifest hash
data_version_id
code hash
strategy hash
engine version
execution profile
metrics
```

Promotion to paper must refuse:

- SYNTHETIC runs;
- failed data-quality runs;
- runs without immutable manifests.

This replaces scaffold promotion semantics.

---

# 47. External-engine adapter point

Do not make Phase 1 dependent on NautilusTrader or LEAN.

After Phase 1 invariants pass, an external adapter can be evaluated under:

```text
backend/simulation/external/
    nautilus/
    lean/
```

Any external engine must emit the same canonical:

- Order;
- Fill;
- LedgerEntry;
- PositionSnapshot;
- PortfolioSnapshot;
- SimulationEvent.

This ensures vendor/kernel substitution does not leak into the application layer.

---

# 48. Definition of Phase 1 complete

Phase 1 is complete when:

- all acceptance tests AT-01 through AT-18 pass;
- existing backtest frontend remains functional;
- existing backtest API remains compatible;
- VERIFIED runs cannot use synthetic data;
- VERIFIED runs require a data version;
- same-close look-ahead is removed;
- one account is used across multiple assets;
- order partial fills have complete lifecycle semantics;
- fills reconcile to cash and positions;
- split/dividend events change account state correctly;
- repeated runs are deterministic;
- run manifests are immutable and reproducible;
- canonical records can explain final P&L transaction by transaction.

At that point OpenTerminalUI has a trustworthy daily simulation foundation.

Phase 2 can then move paper trading onto the same engine and add historical replay/intraday execution without redesigning the core.
