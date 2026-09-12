# OpenTerminalUI Assessment and Project Direction

**Repository:** `Hitheshkaranth/OpenTerminalUI`  
**Assessment baseline:** `main` at commit `9a4dd96dfa1e2c8d33db75c759dacfef9379de4e`  
**Assessment date:** 2026-09-12  
**Purpose:** Determine whether OpenTerminalUI should be used as the base for a high-fidelity strategy research, backtesting, historical replay, paper-trading, and eventual live-trading terminal.

---

## 1. Executive decision

OpenTerminalUI should be used as the application and terminal foundation.

We should **not** rebuild the full terminal from scratch. The repository already provides a substantial financial-terminal product surface: React/TypeScript frontend, FastAPI backend, market-data services, charting, strategy tooling, backtesting UI, Model Lab, Portfolio Lab, paper trading, OMS/risk/ops functionality, data-version concepts, point-in-time data services, governance scaffolding, and deployment infrastructure.

The main engineering change is concentrated in one area:

> Replace the current fragmented backtest/paper-trading execution and accounting logic with one deterministic, event-driven simulation and ledger core.

The new core will become authoritative for:

1. historical backtests;
2. historical replay;
3. paper trading;
4. portfolio simulation;
5. strategy validation;
6. eventual live-broker reconciliation.

The existing application, analytics, visualizations, strategy catalog, market-data interfaces, portfolio/risk screens, Model Lab, and most frontend components should be preserved and reconnected to the new engine.

---

## 2. What OpenTerminalUI already gives us

### 2.1 Application architecture

The repository is already a full-stack financial application rather than a UI prototype.

Existing architecture includes:

- React 18 + TypeScript frontend;
- Vite build tooling;
- Tailwind CSS;
- TanStack Query;
- Zustand;
- Lightweight Charts;
- Recharts;
- Nivo;
- React Mosaic / grid layout functionality;
- Three.js;
- FastAPI backend;
- SQLAlchemy;
- SQLite default persistence;
- PostgreSQL production support;
- Redis;
- WebSockets;
- Alembic migrations;
- Docker deployment;
- Playwright and Vitest frontend tests;
- Pytest backend tests.

This is a strong base for a professional strategy-testing terminal.

### 2.2 Existing terminal functionality worth preserving

The repository already exposes a broad financial-terminal feature surface, including:

- Mission Control / dashboards;
- security research;
- chart workstations;
- technical indicators;
- watchlists;
- screeners;
- factor analytics;
- portfolio analytics;
- risk analytics;
- correlation analysis;
- paper trading;
- position sizing;
- trade journal;
- alerts;
- backtesting;
- Model Lab;
- model governance;
- pair trading;
- statistical analysis;
- options and futures workspaces;
- derivatives analytics;
- macro/economic data;
- news/sentiment;
- OMS/compliance;
- operations/data-quality dashboards;
- saved workspaces/views;
- AI research functionality;
- plugins and scripting.

The project direction is therefore to **reuse this breadth** and concentrate new engineering on simulation correctness.

---

## 3. Existing backtesting functionality worth keeping

The current backtesting surface already includes useful components that should remain in the product.

### 3.1 Strategy catalog

`backend/core/strategy_runner.py`

The strategy catalog includes multiple prebuilt strategy families, including trend, mean-reversion, breakout, oscillator, volatility, and momentum strategies.

This should remain as:

- example strategy implementations;
- test fixtures;
- onboarding presets;
- regression cases for the new engine.

The strategy-generation code should not own portfolio accounting or execution. It should only produce intents/signals/orders through the new strategy adapter.

### 3.2 Backtest frontend

`frontend/src/pages/Backtesting.tsx`

The existing page already supports or references:

- price/chart view;
- equity curve;
- drawdown;
- monthly return heatmap;
- rolling metrics;
- performance metrics;
- trade analysis;
- strategy comparison;
- parameter surfaces;
- robustness analysis;
- parameter sweeps;
- Monte Carlo;
- walk-forward analysis;
- sensitivity analysis;
- workspace/mosaic layouts.

This is valuable and should be retained.

### 3.3 Research analytics

Existing modules such as the following should be retained and adapted to consume the new canonical result schema:

- `backend/core/backtest_analytics.py`
- `backend/core/backtest_robustness.py`
- `backend/core/monte_carlo.py`
- `backend/core/walk_forward.py`
- `backend/core/factor_analysis.py`
- `backend/core/param_optimizer.py`
- `backend/core/vectorized_backtest.py`

Vectorized research can remain useful for parameter screening, but a vectorized result must not be labeled a verified execution backtest unless it is rerun through the authoritative simulation engine.

### 3.4 Existing execution-model concepts

The repository already contains useful execution-model primitives.

`backend/core/execution_model.py` contains:

- fixed-BPS slippage;
- volume-weighted slippage;
- an impact curve;
- participation caps;
- partial-fill quantities.

`backend/execution_sim/simulator.py` contains additional cost concepts such as:

- commission;
- spread;
- slippage;
- ATR-related slippage;
- market impact;
- borrow cost.

These concepts are useful, but the implementations should be consolidated behind one execution interface.

---

## 4. Existing data infrastructure worth keeping

A deeper repository inspection identified more useful point-in-time/data-version infrastructure than the initial high-level assessment suggested.

### 4.1 Data versions

The repository already contains:

- `data_versions` persistence;
- active data-version APIs;
- data-version references on backtest/model records;
- frontend data-version controls.

Relevant paths include:

- `backend/api/routes/data_layer.py`
- `backend/services/data_version_service.py`
- `backend/models/core.py`
- `frontend/src/pages/Backtesting.tsx`
- `frontend/src/pages/ModelGovernance.tsx`

We should keep this model and strengthen it instead of creating a duplicate data-version system.

### 4.2 Point-in-time fundamentals and universes

`backend/api/routes/data_layer.py` already exposes point-in-time-related endpoints for:

- fundamentals;
- point-in-time fundamentals;
- universe membership;
- versioned price series.

This is important because survivorship bias and future-information leakage must be controlled by the same data-version framework used by the simulator.

### 4.3 Versioned price series and corporate-action adjustments

`backend/services/price_series_service.py` already:

- queries versioned EOD price rows;
- accepts a `data_version_id`;
- retrieves corporate actions;
- can return adjusted price series.

`backend/services/corp_actions_service.py` already provides corporate-action retrieval and cumulative adjustment-factor logic.

This should be preserved, but the simulation engine must distinguish between:

- adjusted research series; and
- actual corporate-action events applied to the account ledger.

For execution/accounting, a dividend or split should be an event, not merely a historical price adjustment.

---

## 5. Material issues identified

The current repository is useful, but several issues prevent us from treating its present backtest output as high-fidelity execution/accounting truth.

### 5.1 Same-close look-ahead risk

**File:** `backend/core/single_asset_backtest.py`

The current daily engine can generate a signal from a daily frame and execute that target using that same day's close.

For a strategy whose signal depends on the completed daily close, filling at that completed close can create look-ahead bias.

The new engine must separate:

- information time;
- decision time;
- order submission time;
- venue acceptance time;
- execution time.

Example valid policies:

- signal from day T close → execute at T+1 open;
- signal generated before an exchange MOC cutoff → execute at closing auction;
- signal from intraday data → execute only after the event timestamp that made the information available.

No strategy may implicitly receive the price that produced its own signal.

### 5.2 Portfolio return sequencing can use future exposure

**File:** `backend/portfolio_backtests/engine.py`

The weighted portfolio engine can rebalance using the current day's close and then apply that day's close-to-close return to the resulting portfolio weights.

That can grant the newly established exposure a return that occurred before the rebalance.

The replacement engine must update the account in chronological event order.

### 5.3 One current portfolio implementation is not a true shared account

**File:** `backend/core/portfolio_backtest.py`

The implementation runs asset simulations independently and combines/averages resulting equity curves.

A real portfolio requires one shared account containing:

- one cash ledger;
- positions;
- reserved buying power;
- pending orders;
- settlement state;
- fees;
- interest;
- margin;
- borrow;
- receivables/payables.

Every order must compete for the same capital and risk limits.

### 5.4 Execution logic is fragmented

Current execution concepts are spread across multiple locations, including:

- `backend/core/single_asset_backtest.py`
- `backend/core/execution_model.py`
- `backend/execution_sim/simulator.py`
- `backend/portfolio_backtests/engine.py`
- `backend/portfolio_lab/engine.py`
- `backend/paper_trading/service.py`

Different pathways therefore have different assumptions.

The project should have one canonical execution interface and lifecycle.

### 5.5 Order lifecycle is incomplete

Although partial-fill quantities can be calculated, an authoritative simulator also needs explicit behavior for the remainder of an order:

- DAY;
- GTC;
- IOC;
- FOK;
- cancel;
- replace;
- carry to next bar;
- venue/session expiry;
- triggered stop behavior;
- auction orders.

A partial fill is not complete until the remaining quantity's lifecycle is defined.

### 5.6 Synthetic data fallback is unacceptable for verified testing

**Files:**

- `backend/core/historical_data_service.py`
- `backend/services/backtest_jobs.py`
- `backend/portfolio_backtests/engine.py`

The current backtest path can fall back to generated synthetic data when market history is unavailable.

This is convenient for demos but must be prohibited for verified backtests.

A verified run must fail if required data is unavailable.

Synthetic data can remain available only as an explicitly labeled development/test mode.

### 5.7 Market fallback can silently change the requested market

**File:** `backend/services/backtest_jobs.py`

The job service can attempt alternative markets if the requested market does not return data.

This is unsafe for audited research because a ticker may resolve differently across venues.

A verified run must bind to a canonical instrument identifier and venue before execution.

### 5.8 Data-version infrastructure is not yet authoritative in the main backtest path

The repository already has data versions and versioned price APIs, but the current primary backtest job service still obtains data through `historical_data_service`.

Therefore the useful point-in-time foundation exists, but it is not consistently enforced by the simulation path.

Verified simulation must require a resolved `data_version_id` and data manifest.

### 5.9 Corporate actions are currently more useful for research-series adjustment than account simulation

**Files:**

- `backend/services/price_series_service.py`
- `backend/services/corp_actions_service.py`

Current code can adjust price history using corporate-action factors.

For a brokerage-style account simulation, corporate actions must instead produce ledger effects such as:

- share quantity changes;
- cash dividends;
- cash-in-lieu;
- symbol changes;
- mergers;
- spin-offs;
- delistings.

Adjusted series remain useful for research but cannot replace event accounting.

### 5.10 Paper trading and backtesting use different execution/accounting semantics

**File:** `backend/paper_trading/service.py`

The current paper engine has its own order-fill and account-update logic.

This creates the exact situation we want to avoid:

> A strategy can behave differently because the backtest engine and paper engine implement different rules.

The same OMS, order-state machine, fill model, ledger, fee model, and portfolio accounting code must be used in both modes.

### 5.11 Full-exit realized-P&L issue in current paper-trading service

**File:** `backend/paper_trading/service.py`

The current sell path updates the position before calculating realized P&L. On a complete exit, the position average price is reset to zero before the subsequent realized-P&L calculation reads it.

This creates an accounting defect for a full-position exit.

This is an example of why realized P&L should be generated from immutable execution/lot data rather than calculated after mutable position state has already been changed.

### 5.12 Governance is scaffold-level in some paths

**File:** `backend/experiments/service.py`

The current experiment service includes scaffold behavior such as:

- treating a hash of configuration as a `data_hash`;
- storing dummy metrics;
- returning a promotion receipt without fully wiring the experiment into paper execution.

The UI and database concepts are worth preserving, but verified runs require actual:

- dataset hash;
- code hash;
- engine version;
- strategy hash;
- execution profile;
- calendar version;
- universe version;
- corporate-action version;
- deterministic seed.

---

## 6. What we are keeping

The following categories should be treated as retained platform assets.

### Keep and extend

- terminal shell;
- React application;
- chart components;
- backtesting visualization panels;
- saved views/workspaces;
- strategy catalog;
- custom strategy scripting interface;
- analytics modules;
- parameter sweep workflows;
- Monte Carlo;
- walk-forward;
- Model Lab;
- Portfolio Lab UI;
- governance UI;
- data-quality UI;
- data-version model;
- PIT fundamentals/universe services;
- versioned price-series service;
- corporate-action data services;
- SQLAlchemy/Alembic infrastructure;
- PostgreSQL support;
- Redis/WebSocket infrastructure;
- Docker/deployment;
- authentication;
- permissions;
- audit/operations surfaces.

---

## 7. What we are replacing or making non-authoritative

The following current implementations should not remain authoritative for verified simulation.

### Replace as the verified execution path

- `backend/core/single_asset_backtest.py`
- `backend/core/portfolio_backtest.py`
- `backend/portfolio_backtests/engine.py`
- fragmented execution/cost logic;
- independent paper-trading account engine;
- synthetic fallback behavior;
- cross-market fallback behavior.

These files do not need to be deleted immediately. During migration they remain as compatibility/legacy implementations until the new engine passes regression and parity tests.

### Consolidate

- `backend/core/execution_model.py`
- `backend/execution_sim/simulator.py`
- portfolio execution logic;
- paper fill logic.

Their useful concepts should move behind canonical interfaces in the new simulation package.

---

## 8. Product architecture decision

The target product will use **one trading domain and one account ledger** across multiple operating modes.

| Mode | Clock | Market data | Order execution |
|---|---|---|---|
| Backtest | simulated | historical | simulated venue |
| Historical Replay | simulated/playback | historical | simulated venue |
| Paper | real | live | simulated venue |
| Live | real | live | broker/venue adapter |

A strategy should not need different business logic for each mode.

The execution environment changes through adapters.

---

## 9. Target event model

For daily equity simulation, the authoritative processing order will be explicit.

1. Load previous account state.
2. Process settlement.
3. Accrue financing/interest.
4. Accrue borrow fees.
5. Apply effective corporate actions.
6. Publish pre-market information events.
7. Execute scheduled strategy callbacks.
8. Process opening auction.
9. Match open orders.
10. Process intraday events if required.
11. Trigger stop/limit logic.
12. Process closing-auction cutoff.
13. Process closing auction.
14. Publish official close/marks.
15. Process expiry/contract events where relevant.
16. Calculate margin/risk.
17. Value the portfolio.
18. Calculate P&L attribution.
19. Persist the end-of-day account snapshot.
20. Persist the immutable event journal.

The event sequence is part of the engine specification and must be deterministic.

---

## 10. Accuracy tiers

We should make accuracy level visible in the product.

### VERIFIED

Requirements:

- explicit venue/instrument identity;
- explicit data version;
- no synthetic data;
- no silent market substitution;
- no missing required observations;
- deterministic engine;
- versioned execution assumptions;
- immutable run manifest;
- account ledger balances;
- reproducible output.

Only VERIFIED runs should be eligible for model promotion.

### RESEARCH

Allows:

- cached/provider data not yet frozen into a data version;
- less detailed execution assumptions;
- fast vectorized parameter exploration.

Results must be rerun through VERIFIED mode before promotion.

### SYNTHETIC / DEVELOPMENT

Allows:

- generated market data;
- test fixtures;
- simulated scenarios.

It must be visually and programmatically impossible to confuse this with historical performance.

---

## 11. Data granularity policy

Daily OHLC data can be highly accurate for strategies whose decisions and executions occur at well-defined daily boundaries.

Daily OHLC cannot determine the chronological order of events inside a bar.

For example:

- Open 100
- High 110
- Low 90
- Close 105

does not tell us whether 110 occurred before 90.

Therefore:

- pure EOD strategies may use daily bars;
- stop/limit ordering inside a daily bar requires an explicit path assumption or finer data;
- intraday strategies should use minute/trade/quote data;
- queue-sensitive strategies require L2/L3-type data.

The simulator must not claim precision that the source data cannot support.

---

## 12. External engine strategy

The architecture should not hard-code the project to a third-party simulation kernel.

Phase 1 will establish repository-owned:

- domain objects;
- event-clock contract;
- order lifecycle;
- ledger;
- persistence;
- API contracts;
- deterministic daily reference engine.

The engine interface will allow a future adapter for an external event-driven engine such as NautilusTrader or LEAN if that produces a better cost/fidelity outcome.

This avoids making the database/API/product model dependent on a third-party engine license or internal object model.

---

## 13. Migration strategy

We will migrate incrementally.

### Stage A — New core beside legacy core

Add the new simulation package and database tables without removing existing routes or pages.

### Stage B — Verified backtests use new engine

Existing `/api/backtests` and `/api/v1/backtest/*` routes become compatibility facades over the new simulation service.

### Stage C — Analytics consume canonical results

Existing analytics/visualization code consumes the new result adapter.

### Stage D — Paper trading moves to same engine

Live market events replace historical market events while the OMS/accounting code stays the same.

### Stage E — Retire legacy simulation implementations

Only after parity, compatibility, and migration tests pass.

---

## 14. Definition of success

The simulation platform is successful when all of the following are true:

- the same run manifest reproduces the same fills and final account state;
- changing a material assumption changes the manifest;
- a strategy cannot access information before its availability time;
- a daily-close signal cannot receive an implicit same-close fill;
- all assets compete for one account's cash and buying power;
- orders have explicit lifecycles;
- every fill creates balanced ledger effects;
- splits/dividends alter account state through events;
- verified runs cannot use synthetic data;
- verified runs cannot silently switch venue;
- paper and backtest modes share execution/accounting semantics;
- the UI can explain every order, fill, fee, cash movement, position movement, and NAV change;
- results remain compatible with the existing OpenTerminalUI analytics and visualization surface.

---

## 15. Repository evidence map

The assessment is based primarily on the following repository paths at commit `9a4dd96dfa1e2c8d33db75c759dacfef9379de4e`.

### Product and frontend

- `README.md`
- `PRODUCT.md`
- `frontend/package.json`
- `frontend/src/pages/Backtesting.tsx`
- `frontend/src/components/backtesting/`
- `frontend/src/pages/ModelGovernance.tsx`

### Existing backtest engines and jobs

- `backend/core/single_asset_backtest.py`
- `backend/core/backtesting_models.py`
- `backend/core/portfolio_backtest.py`
- `backend/portfolio_backtests/engine.py`
- `backend/services/backtest_jobs.py`
- `backend/api/routes/backtests.py`

### Strategy/research

- `backend/core/strategy_runner.py`
- `backend/core/param_optimizer.py`
- `backend/core/walk_forward.py`
- `backend/core/monte_carlo.py`
- `backend/core/backtest_analytics.py`
- `backend/core/backtest_robustness.py`
- `backend/core/factor_analysis.py`

### Execution/paper

- `backend/core/execution_model.py`
- `backend/execution_sim/simulator.py`
- `backend/paper_trading/service.py`
- `backend/api/routes/paper.py`

### Data and point-in-time infrastructure

- `backend/core/historical_data_service.py`
- `backend/api/routes/data_layer.py`
- `backend/services/price_series_service.py`
- `backend/services/data_version_service.py`
- `backend/services/pit_fundamentals_service.py`
- `backend/services/corp_actions_service.py`
- `backend/models/core.py`

### Governance

- `backend/experiments/service.py`
- `backend/experiments/models.py`
- `backend/api/routes/governance.py`

### Existing tests

- `backend/tests/test_single_asset_backtest.py`
- `backend/tests/test_single_asset_backtest_metrics.py`
- `backend/tests/test_experiments_registry.py`
- `backend/tests/test_governance_routes.py`

---

## 16. Project direction summary

We are **not** building a new financial terminal.

We are using OpenTerminalUI as the financial-terminal platform and replacing the part that determines whether a strategy result can be trusted.

The core principle is:

> Research may be fast and approximate; promoted strategy results must be deterministic, versioned, event-ordered, ledger-backed, and reproducible.

The next document defines the concrete repository implementation for Phase 1.
