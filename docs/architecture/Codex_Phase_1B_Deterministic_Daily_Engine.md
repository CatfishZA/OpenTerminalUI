# Codex Phase 1B — Deterministic Daily Simulation Engine

**Repository:** `CatfishZA/OpenTerminalUI`  
**Working branch:** `feat/simulation-core`  
**Phase 1A checkpoint:** `2059e10 feat(simulation): add Phase 1A simulation core scaffold`  
**Phase:** 1B  
**Objective:** Implement the first real deterministic daily simulation engine on top of the Phase 1A contracts, persistence, API shell, and repository structure.

## 1. Required reading

Before changing code, read these repository documents completely:

```text
docs/architecture/OpenTerminalUI_Assessment_and_Direction.md
docs/architecture/OpenTerminalUI_Simulation_Implementation_Blueprint.md
docs/architecture/Codex Phase 1A — Simulation Core Scaffold.md
docs/architecture/Codex Phase 1B — Deterministic Daily Simulation Engine.md
```

Treat the assessment as architectural context, the implementation blueprint as the technical source of truth, and this document as the current task. Inspect the Phase 1A implementation before modifying it.

## 2. Branch and safety rules

Work only on `feat/simulation-core`.

Do not modify, merge into, or switch to `main`. Do not create a new branch unless explicitly instructed. Do not push or merge unless explicitly instructed. Do not implement Phase 1C or later work.

## 3. Phase 1B objective

Turn the Phase 1A shell into a functioning deterministic daily cash-equity simulator with chronological event ordering, no same-close look-ahead, next-session-open execution for close-generated signals, one shared account across assets, market/limit/stop orders, DAY/GTC lifecycles, partial fills, commissions, cash/position accounting, realized/unrealized P&L, T+N settlement, immutable event persistence, EOD snapshots, deterministic replay, and ledger reconciliation.

## 4. Explicit non-goals

Do NOT implement legacy `/backtests` route migration, paper-trading migration, frontend changes, historical replay UI, options, futures, margin accounts, short inventory/locates, multi-currency accounting, live broker adapters, tick matching, L2/L3, queue-position modeling, complex auction routing, tax-lot accounting, NautilusTrader, LEAN, or performance optimization that changes semantics.

Do not refactor unrelated repository areas.

## 5. Existing files that must remain untouched unless strictly necessary

Do not modify:

```text
backend/core/single_asset_backtest.py
backend/core/portfolio_backtest.py
backend/portfolio_backtests/engine.py
backend/paper_trading/service.py
```

Do not redirect legacy backtest routes to the new simulator. Do not modify frontend behavior. If a change outside `backend/simulation/` is required, explain why and keep it minimal.

## 6. Primary implementation files

Work primarily in:

```text
backend/simulation/engine/event_clock.py
backend/simulation/engine/dispatcher.py
backend/simulation/engine/order_manager.py
backend/simulation/engine/matching_engine.py
backend/simulation/engine/account_engine.py
backend/simulation/engine/settlement_engine.py
backend/simulation/engine/valuation_engine.py
backend/simulation/engine/daily_simulator.py
backend/simulation/engine/result_builder.py

backend/simulation/execution/fixed_bps.py
backend/simulation/execution/volume_participation.py
backend/simulation/execution/impact_curve.py
backend/simulation/execution/commissions.py

backend/simulation/persistence/repositories.py
backend/simulation/persistence/serializers.py

backend/simulation/services/simulation_service.py
backend/simulation/services/reconciliation_service.py

backend/simulation/adapters/strategy_runner_adapter.py
backend/simulation/adapters/versioned_data_adapter.py
```

Modify domain or port definitions only where Phase 1A interfaces are insufficient.

## 7. Required deterministic daily event sequence

Implement:

```text
10  SESSION_START
20  SETTLEMENT
30  CORPORATE_ACTION
40  BAR_OPEN
50  OPEN_ORDER_MATCH
60  STRATEGY_OPEN_CALLBACK
70  INTRADAY_ORDER_PROCESSING
80  BAR_CLOSE
90  STRATEGY_CLOSE_CALLBACK
100 POST_CLOSE_ORDER_VALIDATION
110 MARK
120 VALUATION
130 PORTFOLIO_SNAPSHOT
140 SESSION_END
```

Equal timestamps must use event priority. Every persisted event gets a strictly increasing run sequence. `(run_id, sequence)` must be unique.

## 8. No-look-ahead invariant

A strategy may only consume information available at the current event time.

For a daily close strategy:

```text
BAR_CLOSE(T)
→ calculate signal
→ submit intent/order
→ eligible no earlier than BAR_OPEN(T+1)
```

Forbidden:

```text
signal based on close(T)
→ fill at close(T)
```

Encode order eligibility explicitly.

## 9. Market data requirements

Use the Phase 1A versioned data adapter.

For VERIFIED runs: `data_version_id` required; persisted versioned history required; no provider fallback; no synthetic OHLC; no venue substitution; no silent missing-bar filling.

Validate monotonic sessions, no duplicates, valid OHLC, non-negative volume, and instrument/venue identity. Do not expose future rows to strategy context.

## 10. Trading calendar behavior

Use an existing exchange/calendar service if available through an adapter. Otherwise create the smallest clean calendar abstraction needed. Do not assume every weekday is a trading day if exchange-session information exists. Fixture calendars are acceptable in tests. Avoid adding a large dependency unless necessary.

## 11. Account model

Use one account across all instruments. Required state:

```text
cash
positions
open orders
realized P&L
unrealized P&L
equity
buying power
```

Phase 1B is cash-account only. Insufficient cash policy: reject order. Do not silently allow negative buying power.

## 12. Cash model

Maintain at minimum:

```text
settled
unsettled_receivable
unsettled_payable
reserved
available
```

Use `Decimal`.

Required identity:

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

Interest/borrow may remain operationally unused in this phase.

## 13. Settlement engine

Support configurable T+0, T+1, and T+2.

Execution and settlement are separate. For a sale: execution changes economic position/P&L on T; proceeds become unsettled receivable; they become settled cash on settlement date. Purchase principal reduces buying availability at execution. Avoid double-counting cash.

## 14. Order lifecycle

Implement:

```text
OrderType: MARKET, LIMIT, STOP
TimeInForce: DAY, GTC
OrderStatus: CREATED, ACCEPTED, PARTIALLY_FILLED, FILLED, CANCELLED, EXPIRED, REJECTED
```

State transitions must be explicit. Orders must not disappear silently.

## 15. Market-order behavior

Default daily behavior:

```text
submitted after close(T)
→ eligible at open(T+1)
```

Base reference price is next eligible open, then apply execution/slippage model.

## 16. Partial fills

With bar volume `V` and max participation `P`:

```text
max simulated quantity = V × P
```

Example: BUY 10,000, volume 20,000, participation 10% => fill 2,000, remaining 8,000, status `PARTIALLY_FILLED`.

GTC remainder carries. DAY remainder expires at session end. Persist all fills separately.

## 17. Fixed-BPS execution model

BUY:

```text
fill = reference × (1 + bps / 10,000)
```

SELL:

```text
fill = reference × (1 - bps / 10,000)
```

Use Decimal-compatible calculations.

## 18. Volume-participation execution model

At minimum:

```text
max_participation
base_slippage_bps
volume_weighted_bps
```

Cap quantity, return explicit partial fills, deterministic slippage, no account mutation.

## 19. Limit-order behavior

BUY limit: if `open <= limit`, may fill from open subject to execution rules; otherwise if `low <= limit`, limit was touched.

SELL limit: mirror logic.

If daily bar cannot resolve chronology relative to other triggered orders, use daily-bar path policy.

## 20. Stop-order behavior

SELL stop triggers when market reaches/touches `<= stop`; BUY stop triggers when market reaches/touches `>= stop`. After trigger, treat as market-style execution under the daily-bar policy. Do not grant favorable chronology when the bar is ambiguous.

## 21. Daily-bar path policy

Support:

```text
OHLC
OLHC
WORST_CASE
```

For VERIFIED runs, default `WORST_CASE` for ambiguous same-bar outcomes. Record policy in manifest/result metadata.

## 22. Commission model

Minimum:

```text
commission = max(notional × bps / 10,000, minimum)
```

Charge per fill unless configured otherwise. Persist commission in fill, ledger, and account state.

## 23. Fill processing

Processing order:

```text
1. execution model creates fill
2. commission model calculates costs
3. event is persisted
4. account engine consumes fill
5. ledger entries are created
6. position changes
7. settlement obligation/receivable is created
```

Execution model may not mutate account state.

## 24. Position accounting

Weighted-average cost is acceptable.

Required fields:

```text
quantity
average_cost
realized_pnl
unrealized_pnl
market_value
last_mark
```

Use pre-fill cost basis for realized P&L.

Example:

```text
BUY 100 @ 10
SELL 100 @ 12
```

Expected: realized P&L 200, quantity 0, average cost reset only after realization.

## 25. Ledger behavior

Ledger is authoritative for cash movements.

Required entry types:

```text
CASH_DEPOSIT
TRADE_PRINCIPAL
COMMISSION
FEE
SETTLEMENT
```

Corporate-action ledger behavior may remain Phase 1C unless already straightforward.

## 26. Valuation

At EOD:

```text
market value = quantity × official close
```

Compute gross/net exposure, realized/unrealized P&L, cash, and equity. Be explicit and consistent about unsettled cash treatment in equity vs buying power.

## 27. Portfolio snapshots

Persist one per session with at least:

```text
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

## 28. Position snapshots

Persist EOD snapshots containing:

```text
instrument
quantity
average_cost
mark_price
market_value
realized_pnl
unrealized_pnl
```

Use deterministic ordering.

## 29. Event journal

Persist at least:

```text
SESSION_START
SETTLEMENT
BAR_OPEN
ORDER_SUBMITTED
ORDER_ACCEPTED
ORDER_REJECTED
ORDER_TRIGGERED
ORDER_PARTIAL_FILL
ORDER_FILL
ORDER_EXPIRED
BAR_CLOSE
STRATEGY_CALLBACK
MARK
PORTFOLIO_SNAPSHOT
SESSION_END
```

Each event includes run_id, sequence, event_id, event_type, event_time, processing_time, payload. Sequence must be deterministic.

## 30. Deterministic identifiers

Avoid random UUIDs in deterministic comparisons. Prefer IDs derived from stable run/order/fill/event sequence inputs. If DB PKs remain random, replay tests must compare canonical content independent of those IDs.

## 31. Strategy adapter behavior

For existing daily strategies:

```text
BAR_CLOSE(T)
→ calculate signal through T close
→ create target/order intent
→ eligible from next session open
```

Strategy code may not mutate account, access persistence directly, access future bars, or assign fill prices.

## 32. Target-position conversion

Use deterministic conversion. Phase 1B may remain long-only:

```text
1 → long target
0 → flat
-1 → reject/ignore if shorting disabled
```

Use existing run configuration where possible.

## 33. SimulationService execution

Status lifecycle:

```text
QUEUED
VALIDATING_DATA
BUILDING_MANIFEST
RUNNING
FINALIZING
DONE
```

Failure => `FAILED`.

Do not return DONE unless engine completes, snapshots persist, reconciliation passes, and result building succeeds.

## 34. Reconciliation service

At completion verify:

```text
ledger-derived cash == account cash
fill-derived positions == final positions
equity == economic cash + marked positions
```

On failure, mark run FAILED with `LEDGER_RECONCILIATION_FAILED`.

## 35. Result builder

Return canonical fields at minimum:

```text
run_id
status
manifest
initial_cash
final_equity
ending_cash
realized_pnl
unrealized_pnl
total_return
equity_curve
daily_returns
orders
fills
portfolio_snapshots
data_quality
reconciliation
```

Do not fabricate unsupported legacy metrics.

## 36. Phase 1B acceptance tests

Create under `backend/tests/simulation/`:

### AT-01 — No same-close look-ahead

`test_no_lookahead_daily.py`

Day 1 close = 100, Day 2 open = 120. Close-generated BUY must fill no earlier than Day 2 open. Forbidden: Day 1 close fill.

### AT-02 — Deterministic replay

`test_deterministic_replay.py`

Same spec/data/seed/config must produce identical canonical event sequence, orders, fills, ledger, snapshots, final equity, and result hash excluding explicitly nondeterministic wall-clock metadata.

### AT-06 — Shared cash across assets

`test_shared_cash_multi_asset.py`

Initial cash 100,000. Two simultaneous 70,000 purchases must not both be accepted. Second is rejected by insufficient-cash policy.

### AT-07 — Partial-fill lifecycle

`test_partial_fills.py`

BUY 10,000, bar volume 20,000, participation 10% => first fill 2,000, remaining 8,000. GTC carries. DAY expires.

### AT-08 — Commission and cash identity

`test_execution_costs.py`

Exact Decimal relationship:

```text
ending cash
=
starting cash
- buy principal
- buy commission
+ sell principal
- sell commission
```

### AT-09 — Full-exit realized P&L

`test_full_exit_realized_pnl.py`

BUY 100 @ 10, SELL 100 @ 12, no fees => realized P&L 200, final quantity 0.

### AT-12 — Settlement

`test_cash_settlement.py`

T+1 sale: economic P&L recognized T; proceeds unsettled T; proceeds settled T+1.

### AT-13 — Ledger reconciliation

`test_ledger_balance.py`

Ledger cash == account cash; fills reconstruct positions; equity == economic cash + marked positions.

### AT-14 — Event ordering

`test_event_ordering.py`

Sequence strictly increases, equal-time events obey priority, close callback occurs after BAR_CLOSE, close-generated order cannot execute before next eligible open.

## 37. Additional required unit tests

Add focused tests for:

```text
market order next-open execution
limit buy
limit sell
stop trigger
DAY expiry
GTC carry
insufficient cash rejection
minimum commission
participation cap
portfolio EOD mark
settlement queue processing
```

Use unique filenames that are not accidentally ignored by `.gitignore`.

## 38. Test cadence

Do not run the full repository suite after every change.

During development, run targeted tests such as:

```bash
pytest backend/tests/simulation/test_no_lookahead_daily.py
pytest backend/tests/simulation/test_partial_fills.py
pytest backend/tests/simulation/test_ledger_balance.py
```

After a coherent component is complete:

```bash
pytest backend/tests/simulation/
```

Only at Phase 1B completion perform broader verification.

## 39. End-of-phase verification

At the end run:

```text
1. all backend/tests/simulation/
2. selected existing legacy backtest regression tests
3. Python compile check for backend/simulation/
4. git diff --check
```

Do not rerun frontend tests/build unless frontend files changed.

Run the full backend suite once at the end only if targeted simulation and selected legacy tests are green. If prohibitively slow, report it rather than repeatedly rerunning it.

## 40. Performance expectations

Correctness first. Avoid obvious pathological complexity, but no benchmark is required.

## 41. Error handling

Use stable codes where applicable:

```text
INSUFFICIENT_CASH
INVALID_ORDER
ORDER_REJECTED
UNSUPPORTED_ORDER_TYPE
ENGINE_INVARIANT_FAILED
LEDGER_RECONCILIATION_FAILED
VERIFIED_DATA_MISSING
```

## 42. Persistence rules

Persist through repository interfaces:

```text
events
orders
fills
ledger entries
portfolio snapshots
position snapshots
run status/result metadata
```

Do not return only in-memory canonical state.

## 43. Atomic fill/account update

A fill, ledger consequences, position update, and settlement obligation must succeed atomically or the run must fail cleanly. Use the smallest clean SQLAlchemy transaction boundary supported by the current architecture.

## 44. Reuse Phase 1A contracts

Do not duplicate Order, Fill, LedgerEntry, SimulationEvent, SimulationRunSpec, RunManifest, PortfolioSnapshot, or PositionSnapshot. Extend only if necessary and document any interface corrections.

## 45. No fabricated financial outputs

Do not invent fills, prices, dataset hashes, metrics, or sessions. Every output must derive from the run spec, versioned market data, strategy output, execution assumptions, and accounting events.

## 46. Code quality rules

Use Decimal, timezone-aware datetime, typed functions, small deterministic units, clear state transitions, and explicit invariants.

Avoid hidden global state, wall-clock-dependent behavior, implicit randomness, silent fallback, float-based canonical cash math, and direct strategy account mutation.

## 47. Deliverables

When complete, report:

1. Summary of implemented behavior.
2. Files created.
3. Files modified.
4. Domain/interface changes from Phase 1A.
5. Engine components implemented.
6. Acceptance tests added.
7. Targeted test results.
8. End-of-phase regression results.
9. Any failures.
10. Deviations from blueprint.
11. Known limitations.
12. Confirmation legacy engines/routes remain untouched.
13. Confirmation no frontend work was performed.
14. Confirmation Phase 1C was not started.
15. Recommended Phase 1C task.

Do not commit or push unless explicitly instructed.

## 48. Completion criteria

Phase 1B is complete only when AT-01, AT-02, AT-06, AT-07, AT-08, AT-09, AT-12, AT-13, and AT-14 all pass, and all of the following hold:

- close-generated signals cannot fill at the same close;
- multi-asset orders share one cash account;
- order remainder behavior is explicit;
- partial fills persist correctly;
- realized P&L is correct on full exit;
- settlement is separate from execution;
- ledger reconstructs cash;
- fills reconstruct positions;
- snapshots reconcile to final equity;
- event ordering is deterministic;
- repeated runs are reproducible;
- legacy engines remain unchanged;
- no frontend migration has started.

## 49. Stop condition

When Phase 1B acceptance criteria pass, STOP.

Do not begin legacy `/backtests` integration, frontend provenance UI, paper trading, broader corporate-action account processing, or Phase 1C. Report completion and wait for the next instruction.
