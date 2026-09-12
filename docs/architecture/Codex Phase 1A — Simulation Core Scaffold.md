# OpenTerminalUI — Phase 1A Implementation Task

You are working in the existing OpenTerminalUI repository.

Read these two attached documents completely before making changes:

1. `OpenTerminalUI_Assessment_and_Direction.md`
2. `OpenTerminalUI_Simulation_Implementation_Blueprint.md`

Treat the Implementation Blueprint as the primary technical specification and the Assessment document as architectural context.

## Objective

Start the implementation of the new deterministic simulation system, but DO NOT attempt to implement the full simulation engine in this task.

This first implementation pass is **Phase 1A — Simulation Core Scaffold**.

The goal is to establish the repository structure, domain contracts, persistence shell, API shell, compatibility boundaries, and test structure so subsequent tasks can implement the engine incrementally.

The existing OpenTerminalUI application must continue to start and existing functionality must remain intact.

---

# Work to complete

## 1. Create the simulation package structure

Create:

```text
backend/simulation/
├── __init__.py
├── domain/
│   ├── __init__.py
│   ├── enums.py
│   ├── identifiers.py
│   ├── instruments.py
│   ├── market.py
│   ├── events.py
│   ├── orders.py
│   ├── fills.py
│   ├── cash.py
│   ├── positions.py
│   ├── account.py
│   ├── corporate_actions.py
│   ├── strategy.py
│   ├── run.py
│   └── results.py
├── ports/
│   ├── __init__.py
│   ├── clock.py
│   ├── market_data.py
│   ├── strategy.py
│   ├── execution.py
│   ├── fees.py
│   ├── corporate_actions.py
│   ├── risk.py
│   ├── ledger.py
│   └── repositories.py
├── engine/
│   ├── __init__.py
│   ├── event_clock.py
│   ├── dispatcher.py
│   ├── order_manager.py
│   ├── matching_engine.py
│   ├── account_engine.py
│   ├── settlement_engine.py
│   ├── corporate_action_engine.py
│   ├── valuation_engine.py
│   ├── daily_simulator.py
│   └── result_builder.py
├── execution/
│   ├── __init__.py
│   ├── fixed_bps.py
│   ├── volume_participation.py
│   ├── impact_curve.py
│   └── commissions.py
├── adapters/
│   ├── __init__.py
│   ├── strategy_runner_adapter.py
│   ├── versioned_data_adapter.py
│   ├── corporate_actions_adapter.py
│   ├── legacy_result_adapter.py
│   └── websocket_progress_adapter.py
├── persistence/
│   ├── __init__.py
│   ├── models.py
│   ├── repositories.py
│   └── serializers.py
├── services/
│   ├── __init__.py
│   ├── simulation_service.py
│   ├── manifest_service.py
│   └── reconciliation_service.py
└── api/
    ├── __init__.py
    ├── schemas.py
    └── routes.py
```

Do not create empty placeholder files without useful contracts. Implement the domain models and interfaces described below sufficiently for imports and tests to work.

---

## 2. Implement the core domain models

Implement the Phase 1 domain definitions from the blueprint.

At minimum:

- `InstrumentId`
- `SimulationMode`
- `VerificationLevel`
- `OrderSide`
- `OrderType`
- `TimeInForce`
- `OrderStatus`
- `EventType`
- `LedgerEntryType`
- `MarketBar`
- `MarketDataManifest`
- `Order`
- `Fill`
- `CashBalance`
- `Position`
- `AccountState`
- `CorporateAction`
- `SimulationRunSpec`
- `RunManifest`
- `SimulationEvent`
- `LedgerEntry`
- `PortfolioSnapshot`
- `PositionSnapshot`
- `SimulationResult`

Use `Decimal` for accounting-critical monetary and quantity fields.

Use timezone-aware `datetime` objects.

Prefer immutable/frozen domain objects where state mutation is not appropriate.

Do not couple these domain models to SQLAlchemy.

---

## 3. Implement engine Protocol interfaces

Implement typed Python `Protocol` interfaces for:

- `ExecutionModel`
- `CommissionModel`
- `MarketDataSource`
- `StrategyAdapter`
- `CorporateActionSource`
- `EventStore`
- `LedgerRepository`
- `SimulationRunRepository`

The interfaces must follow the contracts in the blueprint.

Do not implement complicated engine behavior yet.

---

## 4. Create persistence models

Create the SQLAlchemy persistence shell for:

- `simulation_runs`
- `simulation_events`
- `simulation_orders`
- `simulation_fills`
- `simulation_ledger_entries`
- `simulation_position_snapshots`
- `simulation_portfolio_snapshots`
- `simulation_applied_corporate_actions`

Follow the schema in the blueprint.

Use `Numeric` rather than `Float` for accounting-critical database columns.

Make sure the models are imported into the application's SQLAlchemy metadata/model import path.

Do not remove or modify existing historical tables unnecessarily.

---

## 5. Add the Alembic migration

Create the next valid Alembic migration for the simulation-core tables.

Do not assume the revision number from the document if repository history has changed.

Inspect the current Alembic heads and create a valid migration extending the current head.

The migration must support PostgreSQL and the repository's normal SQLite development/test environment where feasible.

---

## 6. Create the canonical API shell

Mount a new API router under:

```text
/api/v1/simulation
```

Implement initial endpoints:

```text
POST /api/v1/simulation/runs
GET  /api/v1/simulation/runs/{run_id}/status
GET  /api/v1/simulation/runs/{run_id}
GET  /api/v1/simulation/runs/{run_id}/manifest
GET  /api/v1/simulation/runs/{run_id}/orders
GET  /api/v1/simulation/runs/{run_id}/fills
GET  /api/v1/simulation/runs/{run_id}/ledger
GET  /api/v1/simulation/runs/{run_id}/events
GET  /api/v1/simulation/runs/{run_id}/portfolio
GET  /api/v1/simulation/runs/{run_id}/positions
```

For Phase 1A, these endpoints may use repository/service shells and return appropriate not-yet-executed states where engine functionality is not implemented.

However:

- schemas must be real;
- routes must be mounted;
- invalid input must be validated;
- VERIFIED requests without `data_version_id` must already be rejected.

Do not return fabricated financial results.

---

## 7. Create `SimulationService`

Implement the application-facing service contract:

```python
class SimulationService:
    async def submit(...)
    async def status(...)
    async def result(...)
    async def manifest(...)
    async def orders(...)
    async def fills(...)
    async def events(...)
    async def ledger(...)
```

For this phase:

- create and persist the run;
- validate the basic request;
- build the initial manifest shell;
- move the run through the appropriate pre-execution state;
- do not fabricate execution results.

The service must be designed so the daily engine can be inserted in the next phase without changing the API.

---

## 8. Implement manifest hashing foundation

Create `manifest_service.py`.

Use SHA-256.

Canonicalize inputs before hashing.

Include at minimum:

- strategy key;
- strategy context;
- data version;
- execution configuration;
- commission configuration;
- settlement configuration;
- seed;
- engine version;
- code/git hash where available.

Do not use MD5.

Do not call a configuration hash a dataset hash.

Dataset hashes will be supplied by the data adapter later.

---

## 9. Add strict VERIFIED validation

A VERIFIED run must immediately fail validation if:

- `data_version_id` is missing;
- instrument identity does not include venue;
- unsupported asset class is supplied;
- invalid date range is supplied.

Do not add synthetic-data fallback.

Do not add market fallback.

---

## 10. Create strategy/data adapter shells

Create real typed adapter classes for:

- existing `backend/core/strategy_runner.py`;
- existing versioned price/data services;
- existing corporate-action services.

Do not move or duplicate the existing implementations yet.

The adapters should establish how the new simulation package will call them.

---

## 11. Do not replace the legacy backtester yet

Do NOT remove:

```text
backend/core/single_asset_backtest.py
backend/core/portfolio_backtest.py
backend/portfolio_backtests/engine.py
backend/services/backtest_jobs.py
backend/paper_trading/service.py
```

Do not redirect production legacy backtest requests to the unfinished simulator in this phase.

We first want the new system compiling and tested beside the legacy system.

---

## 12. Create initial tests

Create:

```text
backend/tests/simulation/
```

Implement tests for the scaffold itself.

At minimum:

### Domain tests
- Instrument identity equality/hash behavior.
- Decimal monetary fields.
- Order validation.
- Run-spec validation.
- VERIFIED requires data version.

### Manifest tests
- same configuration produces same deterministic manifest hash;
- changing strategy parameters changes hash;
- changing execution model changes hash;
- changing seed changes hash.

### Persistence tests
- simulation run can be inserted/read;
- event sequence uniqueness enforced;
- orders/fills/ledger rows persist correctly.

### API tests
- simulation router is mounted;
- creating valid RESEARCH run succeeds;
- VERIFIED run without `data_version_id` fails;
- malformed instrument identity fails;
- status endpoint works for a created run.

Do not mark unfinished engine tests as passing by mocking fake successful executions.

---

# Important engineering rules

## Preserve existing behavior

Do not make broad unrelated refactors.

Do not rename existing public routes.

Do not redesign the frontend.

Do not remove current models.

Do not delete the legacy engines.

## No fabricated data

Do not generate fake:

- fills;
- equity curves;
- metrics;
- manifests;
- dataset hashes.

Use explicit `not_executed`, `queued`, `validating`, or similar states instead.

## Accounting precision

Use `Decimal` and SQL `Numeric` for canonical accounting.

Do not use float for canonical ledger amounts.

## Separation of concerns

Keep:

```text
domain
ports
engine
persistence
services
api
adapters
```

as distinct layers.

The domain package may not import FastAPI or SQLAlchemy.

The engine package should not depend directly on FastAPI.

The strategy should never receive database access.

## Compatibility

Run the existing backend test suite after changes.

New changes must not intentionally break existing tests.

---

# Deliverables

When complete, provide:

1. A concise summary of changes.
2. Every file created.
3. Every existing file modified.
4. The Alembic revision created.
5. Tests added.
6. Test results.
7. Any existing tests that failed and why.
8. Any assumptions or deviations from the blueprint.
9. A recommended Phase 1B implementation task.

Do not proceed into Phase 1B automatically.

Phase 1B will implement the deterministic daily event clock, account engine, matching, and no-look-ahead execution semantics.