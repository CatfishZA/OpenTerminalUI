# Codex Phase 2A — Canonical Paper-Trading Unification

**Repository:** `CatfishZA/OpenTerminalUI`  
**Working branch:** `feat/simulation-core`  
**Phase 1A checkpoint:** `2059e10 feat(simulation): add Phase 1A simulation core scaffold`  
**Phase 1B checkpoint:** `7be9c00 feat(simulation): implement Phase 1B deterministic daily engine`  
**Phase 1C checkpoint:** `6647f2a feat(simulation): integrate Phase 1C verified backtest workflow`  
**Phase 1D checkpoint:** `f478f4f feat(backtesting): add Phase 1D verified workflow UI`  
**Phase:** 2A  
**Objective:** Move new paper-trading portfolios and orders onto the same canonical order lifecycle, execution, accounting, settlement, ledger, event, and persistence machinery used by the deterministic simulation platform, while preserving the existing `/paper/*` API and Paper Trading UI.

---

## 1. Required reading

Before changing code, read:

```text
docs/architecture/OpenTerminalUI_Assessment_and_Direction.md
docs/architecture/OpenTerminalUI_Simulation_Implementation_Blueprint.md
docs/architecture/Codex Phase 1A — Simulation Core Scaffold.md
docs/architecture/Codex_Phase_1B_Deterministic_Daily_Engine.md
docs/architecture/Codex_Phase_1C_Backtest_Integration.md
docs/architecture/Codex_Phase_1D_Visual_Verified_Workflow.md
docs/architecture/Codex Phase 2A — Canonical Paper-Trading Unification.md
```

Treat the Assessment as context, the Blueprint as technical source of truth, Phases 1A–1D as completed work, and this document as the current task.

Inspect the actual current versions of:

```text
backend/paper_trading/service.py
backend/api/routes/paper.py
backend/simulation/domain/
backend/simulation/engine/
backend/simulation/execution/
backend/simulation/persistence/
backend/simulation/services/
frontend/src/pages/PaperTrading.tsx
```

---

## 2. Branch and safety rules

Work only on `feat/simulation-core`.

Do not modify or merge `main`.

Do not push or merge unless explicitly instructed.

Do not start Phase 2B.

Do not redesign the Paper Trading frontend.

Do not alter VERIFIED backtest semantics.

Do not add live broker routing.

---

## 3. Current problem

The current paper engine is a separate accounting system.

It currently:

```text
maintains its own mark cache
evaluates pending orders directly from ticks
uses float accounting
calculates fill price itself
mutates VirtualPortfolio cash directly
mutates VirtualPosition directly
creates VirtualTrade directly
calculates performance from legacy trade state
```

The product therefore has:

```text
VERIFIED Backtest
→ canonical simulator/account/ledger

Paper Trading
→ legacy VirtualPortfolio/VirtualPosition accounting
```

Phase 2A must end this split for all **new paper portfolios**.

---

## 4. Known legacy paper defects not to preserve

Do not preserve these as canonical behavior:

1. Full-exit realized P&L can be calculated after average cost has been reset.
2. Cash is mutated directly rather than through the canonical ledger.
3. Financial state uses binary floats.
4. Market/limit/stop execution is duplicated outside the shared engine.
5. Tick queue overflow is silently ignored.
6. Partial-fill lifecycle is not canonical.
7. Sale settlement is not separated from execution.
8. Paper orders/fills do not produce canonical ledger/event evidence.

Fix these by changing authority, not by adding more legacy accounting.

---

## 5. Target architecture

```text
Live Tick / Quote
      │
      ▼
Canonical Paper Execution Session
      │
      ├── OrderManager
      ├── tick matching
      ├── execution model
      ├── commission model
      ├── AccountEngine
      ├── SettlementEngine
      ├── ValuationEngine
      ├── canonical ledger
      ├── canonical events
      ├── canonical orders/fills
      └── canonical snapshots
               │
               ▼
Compatibility Projection
      │
      ├── VirtualPortfolio
      ├── VirtualOrder
      ├── VirtualPosition
      └── VirtualTrade
               │
               ▼
Existing /paper/* API and existing frontend
```

Canonical state is authoritative.

`Virtual*` rows become compatibility projections for the existing API/UI.

---

## 6. Phase 2A scope

Implement:

- new paper portfolio → canonical PAPER session;
- manual MARKET orders;
- manual LIMIT orders;
- manual STOP orders;
- GTC lifecycle;
- partial fills when usable liquidity size exists;
- fixed-BPS slippage;
- commission compatibility;
- shared cash across instruments;
- long-only positions;
- Decimal accounting;
- T+0/T+1/T+2 settlement support;
- persisted settlement obligations;
- canonical ledger/events/orders/fills;
- canonical position/portfolio snapshots;
- restart recovery;
- compatibility projection to existing `Virtual*` rows;
- existing `/paper/*` route compatibility.

---

## 7. Explicit non-goals

Do NOT implement:

- live real-money trading;
- broker adapters;
- strategy automation callbacks;
- historical replay;
- backtest-vs-paper reconciliation dashboard;
- calibration UI;
- L2/L3 queue priority;
- short selling;
- borrow/locates;
- margin;
- multi-currency paper portfolios;
- options/futures;
- DAY expiry unless already trivial and correctly testable;
- Paper Trading frontend redesign;
- migration of all historical legacy paper portfolios;
- optimizer/governance integration.

---

## 8. Preserve public Paper API

Keep compatible:

```text
POST /paper/portfolios
GET  /paper/portfolios
POST /paper/orders
GET  /paper/portfolios/{portfolio_id}/positions
GET  /paper/portfolios/{portfolio_id}/orders
GET  /paper/portfolios/{portfolio_id}/trades
GET  /paper/portfolios/{portfolio_id}/performance
POST /paper/deploy-strategy
```

Additive fields are allowed.

Existing frontend request/response fields must remain valid.

---

## 9. Preserve PaperTradingPage

Do not redesign:

```text
frontend/src/pages/PaperTrading.tsx
```

The current workflow must still support:

```text
create portfolio
select portfolio
market/limit/SL order
positions
recent orders
trade blotter
performance
HotKeyPanel
```

Only make minimal frontend/API type changes if required for compatibility.

---

## 10. Use SimulationMode.PAPER

Use the existing:

```text
SimulationMode.PAPER
```

Each new canonical paper portfolio must link to a `simulation_runs` row:

```text
mode = PAPER
status = RUNNING
```

Do not create a parallel run system.

---

## 11. Paper verification semantics

Do not label live paper trading `VERIFIED`.

Live market input is not a frozen historical dataset.

Use:

```text
verification_level = RESEARCH
```

for canonical PAPER sessions unless an already-existing domain value is more appropriate.

Shared execution/accounting semantics do not imply historical reproducibility.

---

## 12. Do not weaken SimulationRunSpec

`SimulationRunSpec` is closed-date historical-run oriented.

Paper sessions are:

```text
open-ended
live-input
universe-expandable
```

Do not make historical start/end/universe validation optional globally.

Create:

```text
backend/simulation/domain/paper.py
```

Suggested type:

```python
@dataclass(frozen=True, slots=True)
class PaperSessionSpec:
    portfolio_id: str
    initial_cash: Decimal
    base_currency: str
    execution_profile: dict[str, Any]
    commission_profile: dict[str, Any]
    settlement_profile: dict[str, Any]
    started_at: datetime
    strategy_key: str = "manual:paper"
    strategy_context: dict[str, Any] = field(default_factory=dict)
```

Use timezone-aware datetime and Decimal.

---

## 13. Canonical paper service

Create:

```text
backend/simulation/services/paper_simulation_service.py
```

Responsibilities:

```text
create paper session
load/recover session
submit order
cancel order
consume market tick
process due settlements
update marks
value account
persist artifacts
update compatibility projections
return current canonical account state
```

Do not place this orchestration inside FastAPI routes.

---

## 14. Do not use DailySimulator as live runtime

Do not push ticks through `DailySimulator`.

Reuse the shared components beneath it:

```text
OrderManager
AccountEngine
SettlementEngine
ValuationEngine
execution models
commission models
canonical persistence/domain objects
```

Create a live/tick orchestration layer instead.

---

## 15. Paper execution engine

Create:

```text
backend/simulation/engine/paper_execution.py
```

Suggested class:

```python
class PaperExecutionEngine:
    ...
```

It must orchestrate shared components.

It must not duplicate cash/P&L calculations already implemented by `AccountEngine`.

---

## 16. Canonical MarketTick

Create:

```text
backend/simulation/domain/ticks.py
```

Suggested:

```python
@dataclass(frozen=True, slots=True)
class MarketTick:
    instrument: InstrumentId
    ts: datetime
    price: Decimal
    size: Decimal | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    source: str | None = None
```

Requirements:

- aware timestamp;
- positive price;
- non-negative optional size;
- Decimal values;
- provider-specific dicts do not enter matching logic.

---

## 17. Tick adapter

Create:

```text
backend/simulation/adapters/live_tick_adapter.py
```

Responsibilities:

```text
normalize venue/symbol
construct InstrumentId
extract timestamp
extract LTP
extract optional size/bid/ask
record source
reject malformed tick
```

Do not put provider parsing in the core engine.

---

## 18. Instrument mapping

Preserve existing symbols like:

```text
NSE:RELIANCE
NASDAQ:AAPL
```

Canonical examples:

```text
RELIANCE / NSE / EQUITY / INR
AAPL / NASDAQ / EQUITY / USD
```

Bare legacy symbols may continue defaulting to NSE for backward compatibility.

Unknown explicit venue must fail rather than silently substitute another venue.

---

## 19. Single-currency rule

Phase 2A paper portfolios remain single-currency.

An order whose instrument currency differs from portfolio base currency must fail explicitly.

Do not perform implicit FX conversion.

---

## 20. New portfolio creation

For a new portfolio, atomically:

```text
create VirtualPortfolio compatibility row
create canonical PAPER SimulationRun
create canonical account
create opening CASH_DEPOSIT ledger entry
create opening portfolio snapshot
link VirtualPortfolio.simulation_run_id
commit
```

Do not leave a usable half-created portfolio on failure.

---

## 21. Migration/link fields

Create the next valid Alembic migration after inspecting the real current head.

Add at minimum:

### VirtualPortfolio

```text
simulation_run_id
nullable
indexed
FK simulation_runs.id ON DELETE SET NULL
```

Recommended:

### VirtualOrder

```text
simulation_order_id
nullable
indexed
FK simulation_orders.id ON DELETE SET NULL
```

### VirtualTrade

```text
simulation_fill_id
nullable
indexed
FK simulation_fills.id ON DELETE SET NULL
```

Suggested migration suffix:

```text
_paper_simulation_link
```

Do not assume revision number.

---

## 22. Persist settlement obligations

Paper sessions must survive restart.

Add canonical table:

```text
simulation_settlement_obligations
```

Fields:

```text
id
run_id
account_id
fill_id
currency
amount
settlement_date
status
created_at
settled_at
```

Statuses:

```text
PENDING
SETTLED
```

Use Numeric/Decimal-compatible storage and useful run/date indexes.

---

## 23. Settlement repository

Add repository support for:

```text
create obligation
list outstanding by run
mark settled
load for recovery
```

Do not depend on only in-memory `AccountState.settlements`.

---

## 24. Opening ledger authority

Canonical opening cash must be represented by:

```text
CASH_DEPOSIT = initial capital
```

`VirtualPortfolio.current_cash` is not the authoritative ledger.

---

## 25. AccountEngine authority

Use:

```text
backend/simulation/engine/account_engine.py
```

for:

```text
cash
average cost
realized P&L
fees
settlement receivables
positions
```

Canonical portfolios must not use legacy `_fill_order()`, `_update_position()`, or `_realized_pnl()` for financial state.

---

## 26. Full-exit P&L invariant

Through the public paper path:

```text
BUY 100 @ 10
SELL 100 @ 12
```

with no fees must yield:

```text
realized P&L = 200
quantity = 0
average cost = 0 only after realization
```

This specifically protects against the old paper bug.

---

## 27. Canonical order lifecycle

Use:

```text
CREATED
ACCEPTED
PARTIALLY_FILLED
FILLED
CANCELLED
EXPIRED
REJECTED
```

Default paper TIF:

```text
GTC
```

Do not expose DAY until session expiry semantics are correctly implemented.

Optional `time_in_force` may be additive, but unsupported DAY can be explicitly rejected.

---

## 28. Legacy order-type mapping

Keep legacy API input:

```text
market → MARKET
limit  → LIMIT
sl     → STOP
```

Do not rename request fields.

---

## 29. Tick matching engine

The existing `MatchingEngine` uses daily bars.

Do not create fake one-tick `MarketBar` objects.

Create:

```text
backend/simulation/engine/tick_matching_engine.py
```

Reuse canonical:

```text
Order
Fill
OrderSide
OrderType
execution model
```

---

## 30. MARKET semantics

A paper MARKET order:

```text
accepted at T
→ immediately eligible
→ fills on first eligible fresh market input at or after T
```

A fresh cached tick may be used.

Do not fill from an older pre-order tick without timestamp eligibility checks.

---

## 31. LIMIT semantics

BUY:

```text
tick.price <= limit
```

SELL:

```text
tick.price >= limit
```

Then apply canonical execution/slippage.

---

## 32. STOP semantics

BUY stop:

```text
tick.price >= stop
```

SELL stop:

```text
tick.price <= stop
```

On trigger:

```text
emit ORDER_TRIGGERED
execute market-style against triggering eligible input
```

---

## 33. Execution model reuse

Do not duplicate BPS fill-price math in paper code.

Reuse Phase 1 execution models.

Minimum:

```text
fixed_bps
```

If volume-participation can consume tick size through a small clean adapter, support it.

---

## 34. Default slippage

Preserve current UI/API default:

```text
slippage_bps = 5
```

Map it into the canonical fixed-BPS model.

Use Decimal internally.

---

## 35. Commission compatibility

Current paper API accepts absolute:

```text
commission
```

Preserve it.

If needed add to canonical commissions:

```python
FixedCommissionModel(amount: Decimal)
```

Policy:

```text
commission > 0
→ fixed commission per fill

commission == 0
→ preserve old default equivalent of 5 bps
```

Do not implement default commission in legacy paper accounting.

---

## 36. Partial fills

When usable tick size exists and the selected profile limits participation:

```text
fill quantity = min(remaining, simulated available quantity)
```

State becomes:

```text
PARTIALLY_FILLED
```

Remaining quantity stays open.

If size is unknown, fixed-BPS default may full-fill, but record the unknown-liquidity assumption in metadata.

Do not pretend unknown size is known volume.

---

## 37. Shared cash

One paper portfolio has one account across symbols.

Example:

```text
cash = 100000
A requires 70000
B requires 70000
```

Both cannot consume the same cash.

---

## 38. Cash reservation

Accepted BUY orders must reserve buying resources.

Cancelling/rejecting/completing releases the correct reservation.

Multiple open orders must not each spend the same available cash.

---

## 39. Long-only sell validation

SELL greater than canonical long position must be rejected.

No negative quantity.

No implicit short.

---

## 40. Settlement

Reuse `SettlementEngine`.

Support:

```text
T+0
T+1
T+2
```

Default:

```text
T+1
```

Execution and settlement remain separate.

---

## 41. Sale proceeds

With T+1:

```text
sell fill on T
position/P&L changes on T
principal becomes unsettled
principal settles on T+1
```

Do not make sale proceeds immediately settled just because legacy paper did.

---

## 42. Due-settlement processing

Process due settlements:

- before evaluating a new order;
- during market activity;
- before returning current account/performance where practical.

Settlement must not require a new fill on settlement date.

Do not add heavy distributed scheduling.

---

## 43. Restart recovery

Canonical paper state must survive process/service restart.

Recover:

```text
latest portfolio snapshot
latest position snapshots
open canonical orders
cash settled/unsettled/reserved
realized/unrealized P&L
fees
buying power
outstanding settlements
current event sequence
```

Do not rely only on Python in-memory state.

---

## 44. Snapshot persistence

Persist canonical snapshots after state-changing events:

```text
portfolio creation
fill
partial fill
reservation-changing cancellation
settlement
```

Do not persist a DB snapshot for every raw tick.

---

## 45. Valuation

Use `ValuationEngine`.

Canonical equity:

```text
economic cash + marked positions
```

Do not calculate authoritative equity from `VirtualTrade` P&L.

---

## 46. Mark cache

An in-memory mark cache may remain for fast UI valuation.

It is market state, not accounting authority.

Losing it after restart must not corrupt cash, positions, average cost, or realized P&L.

---

## 47. Tick queue behavior

Do not silently discard overflow.

If queue fills:

- increment an observable overflow/coalescing counter;
- log/report it;
- preserve newest tick per symbol through coalescing where practical;
- do not silently lose the only latest mark for a symbol with an active order.

Do not add Kafka or external infrastructure.

---

## 48. Per-session concurrency

API submission and tick matching can race.

Create per-run locks:

```text
simulation_run_id → asyncio.Lock
```

Serialize for the same run:

```text
submit
cancel
fill
settlement
projection update
```

Different sessions may run independently.

---

## 49. Persistent event sequence

Paper event sequence must increase monotonically per run.

After restart, continue after persisted maximum sequence.

Keep `(run_id, sequence)` unique.

---

## 50. Paper event types

Use existing event types wherever possible:

```text
ORDER_SUBMITTED
ORDER_ACCEPTED
ORDER_REJECTED
ORDER_TRIGGERED
ORDER_PARTIAL_FILL
ORDER_FILL
ORDER_CANCELLED
MARK
VALUATION
LEDGER_ENTRY
PORTFOLIO_SNAPSHOT
SETTLEMENT
```

Do not persist every raw tick as an event.

---

## 51. Canonical IDs and legacy links

Canonical order example:

```text
ord_<paper-run>_<sequence>
```

Keep `VirtualOrder.id` as compatibility/public ID.

Link:

```text
VirtualOrder.simulation_order_id
```

Likewise:

```text
VirtualTrade.simulation_fill_id
```

---

## 52. Canonical ledger

Each fill must create canonical ledger effects through `AccountEngine`.

Expected entry types:

```text
TRADE_PRINCIPAL
COMMISSION
FEE
SETTLEMENT
```

Cash must be ledger-reconstructable.

---

## 53. Compatibility projection direction

For canonical portfolios:

```text
canonical state → Virtual* projection
```

Never use:

```text
Virtual* state → canonical accounting
```

Projection failure must roll back the state-changing transaction.

---

## 54. VirtualPortfolio projection

Keep `current_cash`.

For Phase 2A define it as:

```text
canonical available/settled buying cash
```

Recommended additive API fields:

```text
settled_cash
unsettled_cash
buying_power
simulation_run_id
engine
```

Canonical portfolio:

```text
engine = canonical
```

Legacy:

```text
engine = legacy
```

---

## 55. VirtualPosition projection

Copy from canonical positions:

```text
quantity
avg_entry_price
```

Do not independently recompute average cost.

---

## 56. VirtualOrder projection

Map canonical status to legacy compatibility.

Recommended additive fields:

```text
simulation_order_id
canonical_status
remaining_quantity
```

Do not hide canonical partial/rejected status if additive fields can expose it.

---

## 57. VirtualTrade projection

Create one compatibility trade row per canonical fill.

Partial fills therefore create multiple trade rows.

`pnl_realized` must reflect canonical accounting, not old `_realized_pnl()` logic.

---

## 58. Existing PaperTradingEngine

Do not delete it immediately.

It may remain:

```text
legacy engine for pre-2A portfolios
```

and/or:

```text
thin facade delegating canonical portfolios
```

For a canonical portfolio it must never execute legacy `_fill_order()` accounting.

Tests must prove this.

---

## 59. Legacy portfolio transition policy

Do not fabricate canonical history.

### New portfolios

```text
simulation_run_id present
→ canonical
```

### Existing pre-2A portfolios

```text
simulation_run_id null
→ legacy path remains
```

Phase 2B can address migration/reconciliation.

Optional automatic upgrade is allowed only for provably pristine portfolios:

```text
no trades
no positions
no meaningful orders
current_cash == initial_capital
```

---

## 60. Place-order flow

For canonical portfolio:

```text
POST /paper/orders
→ validate user/portfolio
→ PaperSimulationService.submit_order()
→ canonical Order
→ compatibility VirtualOrder
→ immediate eligible tick evaluation if fresh
→ response in existing shape
```

Do not route canonical orders through legacy `_fill_order()`.

---

## 61. Fresh cached tick

Immediate market evaluation may use cached market input only if timestamp is fresh.

Suggested:

```text
max_cached_tick_age_seconds = 15
```

Make it configurable/testable.

If stale or absent:

```text
leave order accepted/open
```

Do not fabricate a fill.

---

## 62. Add cancel endpoint

Add:

```text
POST /paper/orders/{order_id}/cancel
```

Canonical cancellation:

```text
release reservation
transition CANCELLED
persist
emit ORDER_CANCELLED
snapshot
update compatibility projection
```

Do not cancel terminal orders.

Frontend does not need to use this yet.

---

## 63. Positions/orders/trades APIs

For canonical portfolios preserve existing response shapes.

Positions derive from canonical current state/projection.

Orders derive from canonical status/projection.

Trades correspond to canonical fills.

Recommended additive provenance fields are allowed.

---

## 64. Performance route

For canonical portfolios, performance must use canonical account/fill/snapshot data.

Preserve expected fields:

```text
equity
pnl
cumulative_return
daily_pnl_curve
sharpe_ratio
max_drawdown
win_rate
avg_win_loss_ratio
profit_factor
trade_count
```

Compatibility statistics can remain simple, but:

```text
equity
cash
PnL
positions
fees
```

must come from canonical state.

---

## 65. Strategy deployment endpoint

Keep:

```text
POST /paper/deploy-strategy
```

Phase 2A behavior:

```text
create canonical paper portfolio/session
store strategy key/context as provenance
return existing portfolio_id/status
```

Do not start live strategy callbacks.

For manual portfolio:

```text
strategy_key = manual:paper
```

For deployed portfolio:

```text
strategy_key = supplied strategy
```

The old cancelled marker-order hack should not be needed for canonical portfolios.

---

## 66. Paper session provenance

Expose additive metadata sufficient to identify:

```text
simulation_run_id
mode = PAPER
engine_version = sim-paper-v2a
execution profile
commission profile
settlement profile
strategy key
started_at
```

Do not invent a historical `data_version_id` for live paper trading.

---

## 67. Session lifecycle

Active paper session:

```text
RUNNING
```

Do not mark session `DONE` after every order.

No portfolio-close endpoint is required in Phase 2A.

---

## 68. Canonical artifact access

For the PAPER run, mode-agnostic artifact retrieval should work:

```text
orders
fills
ledger
events
portfolio snapshots
position snapshots
```

Do not force paper sessions through DailySimulator.

Do not broaden historically backtest-specific manifest/result semantics unsafely.

---

## 69. Atomic fill transaction

A paper fill transaction must atomically include:

```text
fill persistence
ledger persistence
settlement obligation
canonical order update
canonical snapshots
compatibility projection
```

If any step fails:

```text
rollback
```

No half-applied fill.

---

## 70. Suggested new files

Likely:

```text
backend/simulation/domain/paper.py
backend/simulation/domain/ticks.py
backend/simulation/adapters/live_tick_adapter.py
backend/simulation/adapters/paper_legacy_adapter.py
backend/simulation/engine/tick_matching_engine.py
backend/simulation/engine/paper_execution.py
backend/simulation/services/paper_simulation_service.py
backend/simulation/persistence/paper_repositories.py
```

Reuse existing ORM models for orders/fills/ledger/events/snapshots.

---

## 71. Decimal and time boundaries

Convert external floats to Decimal at the API/adapter boundary.

Canonical:

```text
quantity
price
cash
commission
fees
P&L
marks
```

must use Decimal.

Canonical datetimes must be timezone aware.

Only compatibility/JSON boundaries may convert outward.

---

## 72. Error handling

Use stable errors where applicable:

```text
PAPER_PORTFOLIO_NOT_FOUND
PAPER_SESSION_NOT_FOUND
PAPER_PORTFOLIO_MIGRATION_REQUIRED
INVALID_ORDER
ORDER_REJECTED
INSUFFICIENT_CASH
UNSUPPORTED_ORDER_TYPE
UNSUPPORTED_ASSET_CLASS
STALE_MARK
ENGINE_INVARIANT_FAILED
LEDGER_RECONCILIATION_FAILED
```

Reuse existing codes where possible.

Do not turn all failures into generic 500s.

---

## 73. No silent worker errors

Current paper worker catches and ignores exceptions.

For canonical execution:

```text
log failure with run/order/instrument context
rollback inconsistent transaction
continue processing later work
```

One failing order must not corrupt or stop unrelated sessions.

---

## 74. Reconciliation

Add paper reconciliation at least for tests:

```text
ledger-derived cash == canonical account cash
fills reconstruct canonical positions
VirtualPosition == canonical current position
VirtualPortfolio.current_cash == documented canonical projected cash
```

Full reconciliation on every tick is not required.

---

## 75. Backtest regression safety

Do not materially alter:

```text
DailySimulator
AccountEngine
OrderManager
SettlementEngine
ValuationEngine
```

unless a shared bug is proven.

If a common component changes, add focused paper and existing backtest regression tests.

---

# Acceptance Tests

## 76. AT-P01 — Portfolio creates PAPER session

Public API creation must yield:

```text
VirtualPortfolio
simulation_run_id
SimulationRun(mode=PAPER,status=RUNNING)
opening CASH_DEPOSIT
opening portfolio snapshot
```

## 77. AT-P02 — Exact opening cash

With `100000.25`, canonical ledger/account/snapshot reconcile exactly with Decimal.

## 78. AT-P03 — MARKET uses canonical engine

Patch legacy `_fill_order()` to raise. Submit market order and eligible tick.

Expected canonical order/fill/ledger/projection, with no legacy fill call.

## 79. AT-P04 — LIMIT behavior

BUY limit 100:

```text
tick 101 → no fill
tick 100 → fill
```

Also test sell-limit against an existing position.

## 80. AT-P05 — STOP behavior

SELL stop 95:

```text
tick 96 → no trigger
tick 95 → ORDER_TRIGGERED + fill
```

## 81. AT-P06 — Shared cash/reservation

Initial cash 100000. Two orders each requiring ~70000 cannot both consume the account.

## 82. AT-P07 — Full-exit realized P&L

Public paper path:

```text
BUY 100 @ 10
SELL 100 @ 12
```

No costs. Expected realized P&L 200, quantity 0, average cost reset only after realization.

## 83. AT-P08 — Costs and cash identity

Known tick/slippage/commission. Verify exact Decimal ledger/cash relationship.

## 84. AT-P09 — T+1 settlement survives restart

Sell on T. Verify unsettled cash, persisted obligation, service restart, settlement T+1, SETTLEMENT ledger/event.

## 85. AT-P10 — Restart recovery

Recover position, open order, reserved cash, outstanding settlement, and event sequence after service recreation.

## 86. AT-P11 — Event sequence after restart

Events before/after restart remain strictly increasing and unique.

## 87. AT-P12 — Partial fill lifecycle

With size-aware participation fixture: partial fill, remaining quantity, later fill, multiple canonical fills and compatibility trades.

## 88. AT-P13 — Cancel releases reservation

Unfilled BUY limit → reserve → cancel. Reservation released; no fill/trade.

## 89. AT-P14 — Oversell rejected

Hold 10, sell 11. No negative position and no fill.

## 90. AT-P15 — Multi-asset shared account

Two symbols share one PAPER run/account and buying power.

## 91. AT-P16 — Public API compatibility

Exercise create/list/place/positions/orders/trades/performance. Existing required fields remain.

## 92. AT-P17 — Canonical artifact retrieval

While PAPER run is RUNNING, retrieve orders, fills, ledger, events, portfolio and position snapshots.

## 93. AT-P18 — Projection reconciliation

Virtual portfolio/positions/orders/trades reconcile to canonical state.

## 94. AT-P19 — Queue overflow observable

Tiny queue test proves overflow/coalescing count and latest state is not silently lost.

## 95. AT-P20 — Worker exception isolation

One forced order failure rolls back and later work still processes; other sessions unaffected.

## 96. AT-P21 — Legacy portfolio compatibility

`simulation_run_id = null` portfolio receives no fabricated canonical history and follows documented legacy path.

## 97. AT-P22 — Deploy strategy only creates provenance

Deployment creates canonical PAPER session with strategy/context; no automated strategy loop.

## 98. AT-P23 — Phase 1 regression

Focused no-look-ahead, full-exit P&L, ledger reconciliation, settlement and shared-cash tests remain green.

## 99. AT-P24 — Existing Paper Trading UI smoke

Run existing focused frontend test if present; otherwise add one small mocked compatibility smoke. Do not redesign the page.

---

## 100. Likely modified files

Expected:

```text
backend/paper_trading/service.py
backend/api/routes/paper.py
backend/models/core.py
backend/models/__init__.py
backend/simulation/domain/paper.py
backend/simulation/domain/ticks.py
backend/simulation/adapters/live_tick_adapter.py
backend/simulation/adapters/paper_legacy_adapter.py
backend/simulation/engine/tick_matching_engine.py
backend/simulation/engine/paper_execution.py
backend/simulation/execution/commissions.py
backend/simulation/services/paper_simulation_service.py
backend/simulation/persistence/models.py
backend/simulation/persistence/repositories.py
backend/simulation/persistence/paper_repositories.py
backend/alembic/versions/<next>_paper_simulation_link.py
backend/tests/simulation/
backend/tests/
```

Frontend should remain unchanged unless minimal compatibility/type testing requires it.

---

## 101. Files that should not be rewritten

Do not rewrite:

```text
backend/core/single_asset_backtest.py
backend/core/portfolio_backtest.py
backend/portfolio_backtests/engine.py
backend/simulation/engine/daily_simulator.py
frontend/src/pages/Backtesting.tsx
frontend/src/pages/PaperTrading.tsx
```

---

## 102. Test cadence

During development use targeted tests only:

```bash
pytest backend/tests/simulation/test_paper_session.py
pytest backend/tests/simulation/test_paper_orders.py
pytest backend/tests/simulation/test_paper_settlement.py
pytest backend/tests/simulation/test_paper_recovery.py
```

Then:

```bash
pytest backend/tests/simulation/ -k "paper"
```

Do not repeatedly run the full backend suite.

---

## 103. End-of-phase verification

At completion run:

```text
1. all Phase 2A paper canonical tests
2. focused existing paper API tests
3. focused Phase 1 simulation invariants
4. selected backtest integration smoke tests
5. Python compile check for changed backend packages
6. git diff --check
7. git status --short
```

If frontend is unchanged, do not run the entire frontend suite.

If frontend changes, run targeted frontend test and production build once.

Run full backend once only if targeted tests are green and time permits.

---

## 104. Migration verification

Verify upgrade from current head, new FKs/indexes, settlement table, existing Virtual* data retention, and repository-standard downgrade behavior.

Do not delete legacy paper tables.

---

## 105. Manual verification

Run local app and verify existing Paper Trading screen:

```text
create new portfolio
select it
submit market order
submit limit order
observe status
observe positions
observe trade blotter
observe performance
```

If live input is unavailable, do not fabricate fills. Use test fixtures and report the limitation.

---

## 106. No parity claim yet

Phase 2A establishes:

```text
Backtest and Paper share canonical financial mechanics
```

It does not yet establish:

```text
Backtest fills == Paper fills
```

That requires Phase 2B reconciliation/calibration.

---

## 107. Deliverables

When complete report:

1. Summary.
2. Files created.
3. Files modified.
4. Migration created.
5. Canonical paper session design.
6. Tick normalization/matching.
7. Shared engine components reused.
8. Commission behavior.
9. Settlement persistence.
10. Restart recovery.
11. Compatibility projection.
12. Legacy portfolio transition policy.
13. `/paper/*` compatibility.
14. Acceptance tests.
15. Targeted results.
16. Phase 1 regression results.
17. Full backend result if run.
18. Environment-only failures.
19. Manual Paper Trading verification.
20. Deviations.
21. Known limitations.
22. Confirmation VERIFIED backtest semantics unchanged.
23. Confirmation live broker routing not implemented.
24. Confirmation strategy automation not started.
25. Confirmation Phase 2B not started.
26. Recommended Phase 2B task.

Do not commit or push unless explicitly instructed.

---

## 108. Completion criteria

Phase 2A is complete only when AT-P01 through AT-P24 pass, except an explicitly inapplicable optional UI test may be documented, and:

- all new paper portfolios have canonical PAPER runs;
- canonical paper orders do not use legacy `_fill_order()` accounting;
- fills are canonical Fill records;
- cash/positions use AccountEngine;
- settlement persists and survives restart;
- ledger reconstructs paper cash;
- fills reconstruct positions;
- full-exit P&L is correct;
- shared cash applies across symbols;
- reservations prevent over-allocation;
- partial fills work when size is available;
- event sequence survives restart;
- queue overflow is not silent;
- `/paper/*` remains compatible;
- current Paper Trading UI still works;
- old portfolios are not given fabricated canonical history;
- Phase 1 backtest invariants remain green;
- no live broker execution exists;
- no automated strategy loop exists.

---

## 109. Stop condition

When Phase 2A criteria pass:

**STOP.**

Do not begin:

- backtest-vs-paper reconciliation UI;
- execution calibration;
- spread/impact calibration;
- automated deployed-strategy callbacks;
- historical replay;
- broker adapters;
- real-money execution;
- Phase 2B.

Report completion and wait.
