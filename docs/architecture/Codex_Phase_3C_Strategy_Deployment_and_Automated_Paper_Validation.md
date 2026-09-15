# Codex Phase 3C — Strategy Deployment & Automated Paper Validation

**Repository:** `CatfishZA/OpenTerminalUI`  
**Branch:** `feat/simulation-core`  
**Baseline:** Phase 3B checkpoint `2f2007d`  
**Status:** Implementation task specification  
**Phase:** 3C  
**Primary objective:** Connect a governance-approved exact strategy version to canonical PAPER execution so that completed market observations can drive the strategy automatically, generate auditable order intents, pass them through deterministic safety gates, and submit them through the existing Phase 2A PAPER engine without introducing a second execution/accounting path.

---

# 0. Plain-English goal

Phase 3C fills the largest remaining backend gap:

```text
Approved strategy
      ↓
Create controlled PAPER deployment
      ↓
Live/forward market observations arrive
      ↓
Strategy evaluates automatically
      ↓
Strategy emits order intent
      ↓
Safety/risk checks
      ↓
Existing canonical PAPER order engine
      ↓
Orders / fills / ledger / account / settlement
      ↓
Phase 2B reconciliation evidence
      ↓
Phase 3B can later approve PROD
```

The user should no longer need to manually place each PAPER order for a deployed strategy.

Important:

```text
PAPER deployment ≠ live broker execution
```

Phase 3C never places real-money orders and never creates a LIVE broker connection.

---

# 1. Existing system that Phase 3C must reuse

Do not build a parallel trading engine.

The repository already contains:

```text
Phase 2A  canonical PAPER execution
Phase 2B  BACKTEST ↔ PAPER reconciliation
Phase 2C  restart-safe strategy state patterns in REPLAY
Phase 3A  market-data integrity / corporate actions
Phase 3B  exact strategy governance and promotion
```

The existing PAPER service already owns canonical:

```text
orders
fills
account state
cash
positions
settlement
ledger
snapshots
events
```

Phase 3C adds the missing orchestration layer above that engine.

It must produce strategy order intents and send them through the same PAPER order path that manual PAPER orders already use.

---

# 2. Current gap

The current `/paper/deploy-strategy` endpoint creates a PAPER portfolio/run with strategy metadata, but it does not actually run the strategy as market observations arrive.

That endpoint must become a compatibility adapter into the Phase 3C deployment service, or be safely deprecated in favor of the canonical deployment API.

There must be no remaining path where “deploy strategy” merely writes a label while implying that an automated strategy is running.

---

# 3. Scope

Phase 3C includes:

- governance-gated PAPER deployment;
- exact strategy-version binding;
- immutable deployment provenance;
- persisted deployment lifecycle;
- strategy state/checkpoint persistence;
- automatic strategy evaluation on eligible completed market observations;
- canonical order-intent generation;
- idempotent order submission;
- no-same-observation execution/lookahead protection;
- deployment-level risk/safety controls;
- pause/resume/stop/halt controls;
- automatic fail-closed behavior;
- strategy-owned order tagging;
- restart/concurrency safety;
- market-input idempotency;
- Phase 2B reconciliation traceability;
- audit/deployment event history;
- migration;
- API;
- tests.

Phase 3C does **not** include:

- frontend redesign;
- final product navigation/workflow;
- live broker execution;
- real-money orders;
- automatic PROD promotion;
- automatic Phase 2B reconciliation creation;
- auto-liquidation on halt;
- short selling;
- leverage/margin expansion;
- intraday strategy research redesign;
- tick-level VERIFIED backtests;
- options/futures expansion;
- AI strategy decisions;
- strategy optimization;
- Phase 3D;
- Phase 3E.

---

# 4. Critical design rule: preserve one canonical economic truth

All strategy-generated PAPER orders must flow through the existing canonical PAPER service.

Do not create:

```text
paper_strategy_orders
paper_strategy_fills
paper_strategy_cash
paper_strategy_positions
```

as separate economic records.

The only economic truth remains:

```text
SimulationOrderORM
SimulationFillORM
SimulationLedgerEntryORM
canonical account persistence
canonical settlement
canonical snapshots
```

Phase 3C may add deployment/input/decision/intent tables for orchestration and audit, but those tables must never become a competing accounting system.

---

# 5. Governance gate

A governed automated PAPER deployment must reference an existing Phase 3B governance record.

Default eligible governance stages:

```text
STAGING
PROD
```

Blocked:

```text
CANDIDATE
REVOKED
```

STAGING is the normal stage for PAPER validation.

Do **not** require PROD before PAPER deployment because PROD itself depends on PAPER evidence.

At creation/start, verify:

```text
governance record exists
current stage is STAGING or PROD
strategy_key present
strategy_hash present
approved baseline_run_id present
latest approved evidence hash present
evidence_current == true
```

If governance becomes REVOKED or source evidence becomes invalid while a deployment is running, the deployment must fail closed before generating the next strategy order.

Recommended behavior:

```text
status -> HALTED
new strategy decisions blocked
open deployment-owned orders cancelled
existing positions left unchanged
```

Do not liquidate positions automatically.

---

# 6. Exact strategy identity

The deployment must copy strategy identity from governance/canonical evidence.

Canonical identity:

```text
strategy_key
strategy_hash
code_hash
```

The client must not be allowed to override:

```text
strategy_key
strategy_hash
code_hash
approved baseline run
approved strategy parameters
approved universe
```

If a user wants different parameters or a different universe, that is a different strategy version and must go back through VERIFIED BACKTEST + governance.

---

# 7. Strategy configuration source

Do not trust arbitrary `context` supplied by the deployment request.

Reconstruct the executable strategy configuration from the approved canonical baseline evidence:

```text
SimulationRunORM.request_json
SimulationRunORM.manifest_json
strategy_key
strategy_hash
```

Inspect the existing request/manifest shape and reuse the same canonical strategy resolver used by BACKTEST/REPLAY where possible.

After reconstructing the strategy configuration, verify that it resolves to the approved strategy identity.

If the exact executable configuration cannot be reconstructed:

```text
STRATEGY_CONFIG_UNRESOLVED
```

If the implementation/configuration resolves to a different strategy hash:

```text
STRATEGY_HASH_MISMATCH
```

No “close enough” deployment.

---

# 8. Strategy capability contract

The current canonical strategy adapter is based on strategy callbacks and persisted strategy state.

Phase 3C must introduce an explicit capability contract for PAPER deployment rather than silently feeding unsupported events into historical strategies.

At minimum expose whether a strategy supports:

```text
COMPLETED_BAR
```

Phase 3C v1 should support the currently governed daily strategy family through **completed daily bars**.

Do not evaluate a daily strategy on every raw market tick.

Why:

```text
VERIFIED BACKTEST is daily-bar based
REPLAY uses completed historical sessions/bars
running the same strategy on every tick would change its meaning
```

If a strategy does not support the deployment event type:

```text
STRATEGY_CAPABILITY_UNSUPPORTED
```

Future intraday/tick strategies can extend the contract later without changing Phase 3C semantics.

---

# 9. Market event separation

Keep two concepts separate:

## 9.1 Execution ticks

Existing PAPER ticks continue to drive:

```text
marks
existing open-order matching
fills
account valuation
```

## 9.2 Strategy decision observations

Governed daily strategies react only to:

```text
finalized COMPLETED_BAR observations
```

A completed bar must include canonical fields:

```text
source_event_id
instrument
interval
start_time
end_time
open
high
low
close
volume
source
complete=true
```

For Phase 3C v1:

```text
interval = 1d
```

Do not fire a strategy callback on an incomplete bar.

---

# 10. Integrate with the existing market-data path

Do not create a second standalone market-data product.

Create one reusable service entry point for market observations, then allow:

```text
existing HTTP ingestion
existing/future WebSocket/provider adapter
tests
```

to call it.

If the repository already has a completed-bar callback/event stream, integrate with it.

If not, add a narrow finalized-bar ingestion boundary for Phase 3C.

Suggested endpoint if needed:

```text
POST /paper/market/bar
```

The endpoint is not the core architecture; the deployment service is.

---

# 11. Causality / no-lookahead rule

This is non-negotiable.

For any market observation N:

```text
1. process fills/orders that were eligible before observation N
2. update canonical marks/account state
3. persist/accept observation N
4. evaluate the strategy using information available through N
5. emit strategy intents
6. run risk gates
7. submit accepted intents after observation N
8. new orders are first eligible on a later execution observation
```

A strategy-generated order must **never fill on the same market observation that caused the strategy to create it**.

For a daily bar-close signal:

```text
bar close at session D
      ↓
strategy decision after close
      ↓
order submitted
      ↓
first eligible execution observation after decision
```

This preserves the same causality principle established in the historical engine.

---

# 12. Warm-up market history

Many strategies require historical context before the first live decision.

Do not fabricate history and do not call uncontrolled provider fallback.

Default Phase 3C behavior:

```text
use approved baseline data_version_id as the persisted warm-up source
```

At deployment initialization:

```text
load the approved strategy’s required historical bars
only use bars available before the first forward/live decision time
then append deployment-observed completed bars
```

Do not mutate the approved data version.

Forward PAPER observations are deployment evidence, not retroactive edits to historical source data.

If warm-up history is insufficient:

```text
WARMUP_DATA_INSUFFICIENT
```

and do not generate strategy orders until the condition is satisfied or the deployment is stopped.

If the existing strategy adapter exposes `history_limit`, honor it.

---

# 13. Deployment lifecycle

Canonical statuses:

```text
CREATED
RUNNING
PAUSED
STOPPED
HALTED
FAILED
```

Meaning:

## CREATED

Deployment exists, canonical PAPER account/run is prepared, but strategy decisions are not running yet.

## RUNNING

Eligible market observations may trigger strategy decisions.

## PAUSED

No new strategy decisions or strategy orders.

Existing already-submitted canonical orders remain active and may fill.

## STOPPED

Terminal normal stop.

No new strategy decisions.

Cancel remaining deployment-owned open orders.

Do not liquidate positions.

## HALTED

Fail-closed safety stop caused by:

```text
kill switch
risk breach
governance revocation/evidence invalidation
critical strategy/runtime safety condition
```

Cancel remaining deployment-owned open orders.

Do not liquidate positions.

HALTED should not resume through the normal resume endpoint.

A future explicit reset/new deployment can be designed later.

## FAILED

Unexpected unrecoverable internal error.

Do not silently resume.

---

# 14. Valid lifecycle transitions

```text
CREATED -> RUNNING
RUNNING -> PAUSED
PAUSED  -> RUNNING
RUNNING -> STOPPED
PAUSED  -> STOPPED
CREATED -> STOPPED
RUNNING -> HALTED
PAUSED  -> HALTED
CREATED -> HALTED
RUNNING -> FAILED
PAUSED  -> FAILED
CREATED -> FAILED
```

Invalid transitions must return a stable error.

```text
INVALID_DEPLOYMENT_TRANSITION
```

STOPPED/HALTED/FAILED are terminal in Phase 3C.

---

# 15. Persistent deployment record

Create a dedicated Phase 3C table.

Suggested:

```text
paper_strategy_deployments
```

Suggested columns:

```text
id                         string(64) PK, pdep_*
user_id                    FK users
governance_record_id       FK strategy_governance_records
governance_decision_id     FK strategy_governance_decisions
baseline_run_id            FK simulation_runs
portfolio_id               FK virtual_portfolios
simulation_run_id          FK simulation_runs

strategy_key               string(160)
strategy_hash              string(128)
code_hash                  string(128) nullable only if governance permits creation
approved_evidence_hash     string(128)
policy_version             string(64)

status                     string(16)
symbols_json               JSON
strategy_config_json       JSON
strategy_config_hash       string(128)
risk_policy_json           JSON

strategy_state_json        JSON
checkpoint_hash            string(128)
last_input_event_id        string nullable
last_input_time            datetime nullable
last_decision_sequence     bigint
last_error                 text

created_at
started_at
paused_at
stopped_at
halted_at
updated_at
```

Use actual repository naming/types consistently.

The deployment record is the current-state projection.

---

# 16. Deployment provenance must be immutable

Once created, do not allow edits to:

```text
governance_record_id
governance_decision_id
baseline_run_id
strategy_key
strategy_hash
code_hash
approved_evidence_hash
strategy_config_json
strategy_config_hash
symbols/universe
```

Operational lifecycle and strategy state may change.

Risk policy changes during a running deployment should not be silently supported in Phase 3C.

If a different risk profile is required, create a new deployment.

This keeps PAPER validation evidence understandable.

---

# 17. Canonical PAPER run created by deployment

A Phase 3C deployment must create/use a canonical `SimulationMode.PAPER` run through the existing Phase 2A service.

The run must carry the exact approved identity:

```text
strategy_key = governance strategy_key
strategy_hash = governance strategy_hash
code_hash = governance code_hash when present
```

The PAPER run manifest/request should include compact deployment provenance:

```text
deployment_id
governance_record_id
governance_decision_id
approved_baseline_run_id
approved_evidence_hash
strategy_config_hash
risk_policy snapshot
```

Do not label a generic PAPER portfolio with a strategy string and call that sufficient deployment provenance.

---

# 18. Starting capital and universe

For a governance-comparable deployment, derive strategy-affecting configuration from the approved baseline.

Default:

```text
initial capital / account assumptions -> approved baseline when available
universe/symbols                    -> approved baseline
strategy params/context             -> approved baseline
```

Do not let the deployment API silently change the strategy universe or parameters.

If the current architecture cannot reconstruct a required baseline assumption, fail clearly rather than inventing one.

Operational execution/risk settings may be Phase 3C deployment settings, but they must be snapshotted and visible to reconciliation/governance evidence.

---

# 19. Strategy decision / intent persistence

Create append-only orchestration evidence.

Recommended tables:

```text
paper_strategy_inputs
paper_strategy_intents
paper_strategy_events
```

A smaller equivalent schema is acceptable if it preserves all required invariants.

## 19.1 Input record

Each strategy-driving observation should persist:

```text
deployment_id
source_event_id
instrument
input type
input timestamp
payload/digest
accepted sequence
processed status
created_at
```

Constraint:

```text
UNIQUE(deployment_id, source_event_id)
```

## 19.2 Intent record

Each emitted intent should persist:

```text
intent_id
input_id
ordinal
instrument
side
quantity
order_type
limit/stop
tif
intent fingerprint
risk decision
risk reason
canonical_order_id nullable
created_at
```

Constraint:

```text
UNIQUE(deployment_id, input_id, ordinal)
```

## 19.3 Deployment events

Append-only operational events, for example:

```text
CREATED
STARTED
PAUSED
RESUMED
STOPPED
HALTED
FAILED
INPUT_ACCEPTED
INPUT_DUPLICATE
DECISION_COMPLETED
INTENT_ACCEPTED
INTENT_REJECTED
ORDER_SUBMITTED
ORDER_RECOVERED
RISK_BREACH
GOVERNANCE_BLOCKED
```

Do not copy canonical economic fill/ledger history into these tables.

---

# 20. Deterministic intent IDs

Every emitted strategy intent must receive a deterministic deployment intent ID.

Base it on stable inputs such as:

```text
strategy_hash
canonical decision/input identity
instrument
intent ordinal
```

Do not use only a random UUID.

The same deployment checkpoint receiving the same input again must resolve to the same intent IDs.

Use the resulting identity as:

```text
strategy_order_id
```

on the canonical PAPER order.

Include compact metadata such as:

```text
deployment_id
governance_record_id
strategy_key
strategy_hash
source_event_id
intent_id
```

This gives Phase 2B and later audit work a clear lineage.

---

# 21. Order submission idempotency

A retry after partial failure must not create a duplicate canonical order.

Required behavior:

```text
same deployment
same processed input
same intent ordinal
=> at most one canonical order
```

Recommended pattern:

1. determine deterministic intent ID;
2. persist/claim the intent;
3. under the existing per-run lock, look for a canonical order already tied to that strategy intent ID;
4. if it exists, link/recover it;
5. otherwise submit once through `PaperSimulationService`;
6. persist the canonical order link.

Do not rely on HTTP clients never retrying.

---

# 22. Market input idempotency

Automated strategy-driving inputs require a stable:

```text
source_event_id
```

Do not use a bare timestamp as the only identity.

On duplicate input:

```text
no new strategy callback
no new strategy state mutation
no new intent
no new order
```

Return/record idempotent success.

If the exact source cannot provide a stable ID, the adapter may compute a deterministic digest from an authoritative immutable source envelope, but do not collapse legitimate repeated ticks/bars that merely have identical prices.

---

# 23. Strategy state and restart safety

Reuse the Phase 2C pattern where possible.

Persist strategy state after every processed strategy-driving input:

```text
strategy_state_json
checkpoint_hash
last_input_event_id
last_input_time
last_decision_sequence
```

On process restart:

```text
load deployment
reconstruct exact strategy
import strategy state
restore market read model/warmup history
continue from persisted input cursor
```

Restart must not:

```text
re-emit old intents
forget last signal
submit duplicate orders
change strategy identity
```

---

# 24. Input-processing atomicity

Within one deployment, processing must be serialized.

Use a per-deployment/per-simulation-run lock consistent with existing PAPER locking.

The logical unit is:

```text
claim input
restore state
build read model
run strategy
derive intents
risk-check intents
persist intent decisions
submit/recover canonical orders
export strategy state
advance checkpoint
append deployment events
```

Where lower-layer services commit internally, use deterministic IDs and recovery logic so a crash cannot create duplicate economic effects on retry.

Write explicit crash/retry tests.

---

# 25. Strategy error behavior

If strategy evaluation raises unexpectedly:

```text
do not submit partial later intents
record sanitized error
status -> FAILED
cancel deployment-owned open orders where safe
leave positions unchanged
```

If some intent/order was durably created before a crash, recovery must detect it by deterministic intent ID rather than submit it twice.

Do not swallow strategy exceptions and continue as if nothing happened.

---

# 26. Risk / safety policy

Create a centralized deployment risk policy.

This is an operational PAPER safety layer, not a new portfolio/accounting engine.

Suggested default controls:

```text
allowed instruments/universe
max_order_notional
max_position_pct_of_equity
max_open_strategy_orders
max_daily_loss_pct
```

Also include:

```text
manual kill switch
```

Use Decimal for monetary calculations.

Risk policy must be snapshotted at deployment creation.

---

# 27. Risk policy semantics

Risk checks inspect canonical PAPER state.

Do not maintain a separate risk position/cash truth.

For each strategy intent:

```text
read canonical account
read canonical positions
read current observable mark
estimate resulting exposure conservatively
apply deployment policy
```

If required valuation information is missing, fail closed:

```text
RISK_PRICE_UNAVAILABLE
```

Do not guess a price.

---

# 28. Risk must reject, not silently resize

If an intent violates a deployment limit:

```text
reject the entire intent
```

Do not silently reduce:

```text
quantity
order notional
position target
```

Silent resizing would change strategy intent and make reconciliation misleading.

Persist the rejected intent and reason.

Example codes:

```text
RISK_SYMBOL_NOT_ALLOWED
RISK_ORDER_NOTIONAL_EXCEEDED
RISK_POSITION_LIMIT_EXCEEDED
RISK_OPEN_ORDER_LIMIT_EXCEEDED
RISK_DAILY_LOSS_EXCEEDED
```

---

# 29. Daily loss safety

Define daily loss deterministically from canonical account/equity snapshots.

Recommended model:

```text
risk day = deployment/account market-local trading date
day_start_equity = first canonical equity snapshot for that risk day
current_equity = latest canonical equity after marks/fills
loss_pct = max(0, (day_start_equity - current_equity) / day_start_equity)
```

Persist the day-start anchor needed for restart safety.

If:

```text
loss_pct >= max_daily_loss_pct
```

then:

```text
status -> HALTED
block new strategy orders
cancel open deployment-owned strategy orders
leave positions unchanged
```

Do not auto-liquidate.

Avoid floating-point arithmetic.

---

# 30. Position-limit safety

`max_position_pct_of_equity` must be based on post-intent projected notional using the latest observable mark/limit/stop semantics conservatively.

Do not allow a BUY intent when the projected position exceeds the configured limit.

SELL intents that reduce a long-only position should normally be allowed through position-size checks, subject to canonical long-only/account rules.

Do not create short positions.

---

# 31. Kill switch

Add an explicit authenticated halt endpoint.

Suggested:

```text
POST /paper/deployments/{deployment_id}/halt
```

Require:

```text
reason
```

Halt behavior:

```text
status -> HALTED
stop new strategy decisions
cancel deployment-owned open strategy orders
leave manual PAPER orders untouched
leave positions untouched
append audit/deployment event
```

Do not treat kill switch as “sell everything”.

---

# 32. Order ownership

A deployment must be able to distinguish its own strategy orders from:

```text
manual PAPER orders
orders from another deployment
legacy PAPER orders
```

Every automated canonical order must carry:

```text
deployment_id
intent_id
strategy_key
strategy_hash
governance_record_id
```

in canonical metadata and/or stable strategy-order fields.

Pause/stop/halt cancellation routines must cancel only deployment-owned open orders.

Never cancel unrelated manual PAPER orders.

---

# 33. Manual PAPER compatibility

Existing manual PAPER workflows must continue to work.

Phase 3C must not require governance for:

```text
ordinary manually controlled PAPER portfolios
manual PAPER orders
legacy paper testing
```

Governance is required for the **automated strategy deployment** path.

Keep this distinction explicit.

---

# 34. Existing `/paper/deploy-strategy` compatibility

The current endpoint must not remain a misleading shortcut.

Preferred behavior:

```text
POST /paper/deploy-strategy
```

becomes a compatibility adapter into the canonical deployment service.

Do not continue accepting arbitrary strategy/context as trusted governed identity.

If backward compatibility requires legacy behavior, make it explicit and non-governed, for example:

```text
legacy/manual research deployment
```

but do not label it as Phase 3C governed automated deployment.

Prefer requiring:

```text
governance_record_id
```

for the canonical path.

---

# 35. Canonical deployment API

Add clean backend endpoints.

Suggested base:

```text
/api/paper/deployments
```

Follow existing router-prefix conventions in the repository.

## Create

```text
POST /paper/deployments
```

Conceptual request:

```json
{
  "governance_record_id": "gov_...",
  "name": "SMA v3 paper validation",
  "risk_policy": {
    "max_order_notional": "10000",
    "max_position_pct_of_equity": "0.25",
    "max_open_strategy_orders": 5,
    "max_daily_loss_pct": "0.05"
  }
}
```

Do not accept strategy hash/config/universe overrides.

## List

```text
GET /paper/deployments
```

Filters:

```text
status
strategy_key
governance_record_id
offset
limit
```

## Get

```text
GET /paper/deployments/{id}
```

## Start

```text
POST /paper/deployments/{id}/start
```

## Pause

```text
POST /paper/deployments/{id}/pause
```

## Resume

```text
POST /paper/deployments/{id}/resume
```

## Stop

```text
POST /paper/deployments/{id}/stop
```

Require reason for explicit terminal stop if consistent with product conventions.

## Halt / kill switch

```text
POST /paper/deployments/{id}/halt
```

Require reason.

## Events

```text
GET /paper/deployments/{id}/events
```

## Intents

```text
GET /paper/deployments/{id}/intents
```

These are orchestration/audit APIs, not duplicate economic order APIs.

---

# 36. Deployment response

Conceptual response:

```json
{
  "id": "pdep_123",
  "status": "RUNNING",
  "governance_record_id": "gov_123",
  "governance_stage": "STAGING",
  "strategy_key": "fixture:sma",
  "strategy_hash": "hash-A",
  "code_hash": "code-A",
  "baseline_run_id": "sim_backtest",
  "approved_evidence_hash": "...",
  "portfolio_id": "vp_...",
  "simulation_run_id": "sim_paper",
  "symbols": ["NSE:ABC"],
  "risk_policy": {},
  "checkpoint_hash": "...",
  "last_input_time": "...",
  "last_error": null
}
```

---

# 37. Authentication / ownership

All deployment state-changing endpoints require an authenticated user.

A user may control only deployments they own unless the existing authorization model explicitly grants administrative access.

Do not expose another user’s:

```text
deployment
PAPER portfolio
strategy state
intents
risk state
```

through guessed IDs.

---

# 38. Audit trail

Use existing audit logging for lifecycle actions.

Events should include at least:

```text
paper_strategy_deployment_created
paper_strategy_deployment_started
paper_strategy_deployment_paused
paper_strategy_deployment_resumed
paper_strategy_deployment_stopped
paper_strategy_deployment_halted
```

Payload should remain compact:

```text
deployment_id
governance_record_id
strategy_key
strategy_hash
simulation_run_id
from_status
to_status
reason when applicable
```

Strategy input/intent volume should live in Phase 3C deployment evidence tables, not flood the generic audit table.

---

# 39. Reconciliation lineage

Phase 2B must be able to understand that an order came from the governed deployment.

Automated order metadata must preserve:

```text
deployment_id
strategy_order_id / intent_id
strategy_key
strategy_hash
source decision/input identity
```

Do not change Phase 2B matching semantics unless a narrowly scoped compatibility fix is essential.

If a Phase 2B reconciliation is later run against the deployment PAPER run, it should be able to consume the canonical PAPER orders/fills normally.

Phase 3C does not automatically create a reconciliation report.

---

# 40. No automatic governance promotion

Stopping or successfully running a PAPER deployment must **not** automatically promote the strategy.

Required separation:

```text
Phase 3C creates PAPER evidence
Phase 2B creates reconciliation evidence
Phase 3B evaluates/promotes with human approval
```

Do not collapse these responsibilities.

---

# 41. No LIVE side effects

Search for all LIVE/broker execution hooks touched by the implementation.

Phase 3C must not:

```text
create SimulationMode.LIVE run
call broker submit APIs
use Kite order placement
use any real-money order endpoint
store broker credentials
place/cancel broker orders
```

Add an explicit regression test proving a governed PAPER deployment cannot invoke a broker execution path.

---

# 42. Failure policy

Fail closed for uncertainty that could create unintended strategy orders.

Examples:

```text
governance missing/revoked        -> HALT / reject
evidence hash drift              -> HALT
strategy config cannot resolve   -> reject start / FAIL
warm-up missing                  -> no orders
strategy exception               -> FAILED
risk price unavailable           -> reject intent
risk breach                      -> HALTED
duplicate input                  -> idempotent no-op
unsupported strategy capability  -> reject deployment/start
```

Do not “best effort” trade through these cases.

---

# 43. Stable errors

At minimum define stable codes for:

```text
DEPLOYMENT_NOT_FOUND
DEPLOYMENT_ACCESS_DENIED
GOVERNANCE_RECORD_REQUIRED
GOVERNANCE_RECORD_NOT_FOUND
GOVERNANCE_STAGE_NOT_DEPLOYABLE
GOVERNANCE_EVIDENCE_STALE
APPROVED_BASELINE_NOT_FOUND
STRATEGY_CONFIG_UNRESOLVED
STRATEGY_HASH_MISMATCH
STRATEGY_CAPABILITY_UNSUPPORTED
WARMUP_DATA_INSUFFICIENT
INVALID_DEPLOYMENT_TRANSITION
DEPLOYMENT_TERMINAL
MARKET_INPUT_ID_REQUIRED
MARKET_INPUT_INVALID
MARKET_INPUT_DUPLICATE
STRATEGY_EVALUATION_FAILED
RISK_PRICE_UNAVAILABLE
RISK_SYMBOL_NOT_ALLOWED
RISK_ORDER_NOTIONAL_EXCEEDED
RISK_POSITION_LIMIT_EXCEEDED
RISK_OPEN_ORDER_LIMIT_EXCEEDED
RISK_DAILY_LOSS_EXCEEDED
ORDER_SUBMISSION_RECOVERY_FAILED
KILL_SWITCH_REASON_REQUIRED
```

Use repository-standard API error shape.

---

# 44. Suggested service structure

Use repository conventions, but conceptually create:

```text
backend/paper_trading/deployment_domain.py
backend/paper_trading/deployment_policy.py
backend/paper_trading/deployment_repositories.py
backend/paper_trading/strategy_deployment_service.py
backend/paper_trading/strategy_market_read_model.py
backend/paper_trading/strategy_risk_service.py
```

or a similarly clean location.

Suggested responsibilities:

```text
StrategyDeploymentService
  create
  start
  pause
  resume
  stop
  halt
  process_completed_bar
  recover

StrategyRiskService
  evaluate_intent
  evaluate_daily_loss

DeploymentRepository
  lifecycle/state/checkpoint persistence
  input claiming
  intent/event persistence
```

Reuse `StrategyRunnerAdapter`/canonical strategy interfaces rather than inventing a second strategy API where possible.

---

# 45. Strategy market read model

The strategy must receive a market read model containing only information available at the decision time.

For a completed daily bar at time T:

```text
history <= T
```

Never include future bars.

Construct history from:

```text
persisted approved warm-up history
+
completed PAPER-forward bars already accepted by deployment
```

Do not expose future provider data accidentally through a generic historical query.

Add an explicit future-data protection test.

---

# 46. Account context

When strategy callbacks run, `StrategyContext` must reflect canonical PAPER state as of that decision point:

```text
cash
positions
account
equity/orders as supported by context
```

Do not construct synthetic account state from Virtual* compatibility rows when canonical state exists.

Virtual models remain projections only.

---

# 47. Order intent conversion

Strategy intents remain canonical `StrategyIntent` objects.

Convert them to PAPER orders without changing semantic fields:

```text
instrument
side
quantity
order_type
tif
limit_price
stop_price
```

Deployment metadata may be added.

Risk may reject but must not rewrite economic intent.

Existing canonical account/order validation still applies after Phase 3C risk checks.

---

# 48. DAY/GTC behavior

Preserve existing PAPER order semantics.

Do not redefine:

```text
DAY expiry
GTC persistence
limit trigger behavior
stop trigger behavior
partial fill behavior
settlement
reservations
```

Phase 3C merely creates orders through that engine.

---

# 49. Migration

Inspect the actual Alembic head first.

Expected conceptual next revision:

```text
0019_paper_strategy_deployments
```

Use the actual next valid revision.

Likely create:

```text
paper_strategy_deployments
paper_strategy_inputs
paper_strategy_intents
paper_strategy_events
```

A smaller normalized set is acceptable if all invariants are covered.

Required constraints/indexes include:

```text
unique deployment/source input identity
unique deployment/input/intent ordinal
unique deployment event sequence
indexes on deployment status
indexes on user_id
governance_record_id
simulation_run_id
portfolio_id
```

Migration must preserve all prior data.

Downgrade removes only Phase 3C-owned schema.

---

# 50. Migration compatibility

Certify:

```text
fresh database -> latest
0018 -> Phase 3C upgrade
Phase 3C -> 0018 downgrade
existing governance records retained
existing canonical PAPER runs retained
existing manual PAPER portfolios retained
existing reconciliation rows retained
existing replay rows retained
existing corporate-action rows retained
```

One Alembic head only.

---

# 51. Existing manual tick path

The existing manual/market tick ingestion path must remain compatible.

Do not force `source_event_id` requirements onto unrelated legacy/manual PAPER ticks unless it is required for a new automated strategy decision path.

If a tick is used only for execution matching, preserve existing behavior.

Automated strategy-driving completed-bar events must have the stronger idempotency identity.

---

# 52. Controlled reference strategy

Create a deterministic fixture strategy using the existing strategy interface.

Example behavior:

```text
on completed daily bar:
  signal transitions 0 -> 1 => BUY fixed quantity
  signal transitions 1 -> 0 => SELL held quantity
```

Use it to prove:

```text
strategy state persistence
no duplicate signals
no same-bar execution
order ownership
risk rejection
restart invariance
```

Do not modify production strategy semantics just to satisfy tests.

---

# 53. Acceptance tests — governance / creation

### PD01 — STAGING strategy can create deployment

### PD02 — PROD strategy can create deployment

### PD03 — CANDIDATE strategy blocked

Expected:

```text
GOVERNANCE_STAGE_NOT_DEPLOYABLE
```

### PD04 — REVOKED strategy blocked

### PD05 — stale governance evidence blocked

### PD06 — exact strategy identity copied from governance

### PD07 — client cannot spoof strategy key/hash/code hash

### PD08 — strategy params/universe come from approved baseline

### PD09 — unresolved strategy config blocked

### PD10 — strategy hash mismatch blocked

### PD11 — unsupported deployment capability blocked

### PD12 — deployment creates canonical PAPER simulation run

### PD13 — PAPER run contains governance/deployment provenance

### PD14 — no LIVE run created

### PD15 — no broker call made

---

# 54. Acceptance tests — lifecycle

### LC01 — CREATED does not evaluate strategy

### LC02 — start transitions CREATED -> RUNNING

### LC03 — pause transitions RUNNING -> PAUSED

### LC04 — PAUSED ignores strategy decision observations

### LC05 — PAUSED existing open order may still fill

### LC06 — resume transitions PAUSED -> RUNNING

### LC07 — stop cancels only deployment-owned open orders

### LC08 — stop leaves positions unchanged

### LC09 — halt cancels only deployment-owned open orders

### LC10 — halt leaves positions unchanged

### LC11 — halt requires reason

### LC12 — terminal deployment cannot normal-resume

### LC13 — invalid transitions rejected

### LC14 — governance revocation halts before next order generation

### LC15 — governance evidence drift halts before next order generation

---

# 55. Acceptance tests — market causality / strategy

### MS01 — incomplete bar never triggers strategy

### MS02 — completed daily bar triggers exactly one strategy evaluation

### MS03 — strategy market history contains no future bar

### MS04 — approved persisted warm-up history is used

### MS05 — provider/synthetic fallback is not used for warm-up

### MS06 — insufficient warm-up creates no orders

### MS07 — strategy state exported after decision

### MS08 — strategy state restored after restart

### MS09 — last signal survives restart

### MS10 — duplicate source_event_id does not rerun strategy

### MS11 — concurrent duplicate input creates one decision

### MS12 — emitted intent has deterministic ID

### MS13 — strategy order metadata contains deployment lineage

### MS14 — strategy-generated order cannot fill on triggering bar/input

### MS15 — strategy-generated order can fill on later eligible tick

### MS16 — strategy exception fails closed

### MS17 — restart after durable order but before checkpoint does not duplicate order

### MS18 — repeated retry recovers same canonical order

---

# 56. Acceptance tests — risk controls

### RK01 — allowed symbol passes universe gate

### RK02 — disallowed symbol rejected

### RK03 — max order notional enforced

### RK04 — max position percentage enforced

### RK05 — max open strategy orders enforced

### RK06 — missing valuation price fails closed

### RK07 — risk rejection persists intent/reason but creates no canonical order

### RK08 — risk service does not silently resize quantity

### RK09 — daily-loss anchor survives restart

### RK10 — daily-loss breach halts deployment

### RK11 — daily-loss halt cancels deployment-owned open orders

### RK12 — manual PAPER order is not cancelled by deployment halt

### RK13 — SELL reducing a valid long position is not incorrectly blocked by position-limit logic

### RK14 — no short position introduced

---

# 57. Acceptance tests — reconciliation / evidence

### RC01 — automated order is a normal canonical PAPER order

### RC02 — automated fill is a normal canonical PAPER fill

### RC03 — intent lineage survives into canonical order metadata

### RC04 — Phase 2B can consume the deployment PAPER run without special accounting path

### RC05 — Phase 3C does not auto-create Phase 2B report

### RC06 — Phase 3C does not auto-promote Phase 3B governance

### RC07 — stopping deployment leaves immutable evidence/history readable

---

# 58. Acceptance tests — compatibility / regression

### RG01 — existing manual PAPER portfolio creation unchanged

### RG02 — existing manual PAPER order submission unchanged

### RG03 — existing tick matching semantics unchanged

### RG04 — existing partial fills unchanged

### RG05 — existing settlement behavior unchanged

### RG06 — existing BACKTEST semantics unchanged

### RG07 — existing REPLAY semantics unchanged

### RG08 — Phase 2B reconciliation semantics unchanged

### RG09 — Phase 3A integrity behavior unchanged

### RG10 — Phase 3B promotion behavior unchanged

### RG11 — frontend untouched

### RG12 — no Phase 3D work started

---

# 59. Acceptance tests — migration / persistence

### MG01 — fresh migration to Phase 3C passes

### MG02 — 0018 -> Phase 3C upgrade passes

### MG03 — Phase 3C -> 0018 downgrade passes

### MG04 — one Alembic head

### MG05 — old governance records preserved

### MG06 — old PAPER portfolios preserved

### MG07 — old simulation/reconciliation rows preserved

### MG08 — deployment input unique constraint prevents duplicate processing

### MG09 — deployment intent uniqueness prevents duplicate semantic intent

### MG10 — deployment event sequence remains monotonic

---

# 60. Reference end-to-end scenario

Build one controlled scenario.

## Step A — approved strategy

Create:

```text
canonical VERIFIED DONE BACKTEST
strategy_key = fixture:sma
strategy_hash = hash-A
code_hash = code-A
valid data integrity
valid accounting reconciliation
```

Promote through Phase 3B to:

```text
STAGING
```

## Step B — create deployment

Create governed PAPER deployment.

Assert:

```text
exact strategy identity copied
canonical PAPER run created
status = CREATED
no broker calls
```

## Step C — start

```text
CREATED -> RUNNING
```

## Step D — completed bar

Feed an eligible completed daily bar that changes signal to BUY.

Assert:

```text
one input
one decision
one accepted intent
one canonical PAPER order
zero fills on the triggering observation
```

## Step E — next tick

Feed a later eligible tick.

Assert:

```text
canonical fill occurs under existing PAPER execution semantics
account/ledger/position update canonically
```

## Step F — duplicate/restart

Replay the same source event and restart the service.

Assert:

```text
no duplicate intent
no duplicate order
no duplicate fill caused by strategy replay
state/checkpoint stable
```

## Step G — risk halt

Trigger configured daily-loss/risk condition.

Assert:

```text
status = HALTED
no new strategy orders
open deployment-owned orders cancelled
manual PAPER order remains untouched
position remains open
```

## Step H — evidence

Assert the PAPER run remains a normal Phase 2A canonical run and can be supplied later to Phase 2B reconciliation.

Do not automatically reconcile or promote.

---

# 61. Suggested files

Inspect repository conventions first.

Likely create:

```text
backend/paper_trading/deployment_domain.py
backend/paper_trading/deployment_policy.py
backend/paper_trading/deployment_repositories.py
backend/paper_trading/strategy_deployment_service.py
backend/paper_trading/strategy_market_read_model.py
backend/paper_trading/strategy_risk_service.py
backend/alembic/versions/0019_paper_strategy_deployments.py

backend/tests/test_paper_strategy_deployment.py
backend/tests/test_paper_strategy_lifecycle.py
backend/tests/test_paper_strategy_execution.py
backend/tests/test_paper_strategy_idempotency.py
backend/tests/test_paper_strategy_risk.py
backend/tests/test_paper_strategy_governance.py
backend/tests/test_paper_strategy_migration.py
```

Likely modify narrowly:

```text
backend/api/routes/paper.py
backend/paper_trading/service.py
backend/models/core.py and/or simulation persistence models
backend/models/__init__.py
backend/simulation/adapters/strategy_runner_adapter.py
```

Only modify the strategy adapter if needed to expose a clean PAPER-compatible capability/state contract without changing existing BACKTEST/REPLAY results.

Do not modify frontend.

---

# 62. Implementation order

Recommended order:

```text
1. inspect strategy resolver/config identity and PAPER service
2. design migration/domain records
3. governance-gated deployment creation
4. lifecycle service
5. completed-bar market read model
6. strategy state/checkpoint recovery
7. deterministic input/intent idempotency
8. canonical PAPER order submission bridge
9. risk service + halt behavior
10. API compatibility adapter
11. reconciliation lineage tests
12. migration/regression certification
```

Do not start with UI.

---

# 63. Testing strategy

During implementation run narrow tests first.

Suggested groups:

```text
Phase 3C deployment/governance tests
Phase 3C lifecycle tests
Phase 3C strategy/causality tests
Phase 3C idempotency/restart tests
Phase 3C risk tests
Phase 3C migration tests
```

Then regressions:

```text
Phase 1
Phase 2A
Phase 2B
Phase 2C
Phase 3A
Phase 3B
full simulation suite
```

Then:

```text
python compile check
git diff --check
git status --short
git diff --stat
```

Finally rebuild Docker and run the full backend suite against the exact current tree:

```bash
docker compose up -d --build
docker compose exec backend python -m pytest backend/tests/ -q
```

Do not rely on a stale Docker image.

---

# 64. Non-regression contract

After Phase 3C:

```text
BACKTEST deterministic semantics unchanged
VERIFIED policy unchanged
REPLAY semantics unchanged
manual PAPER semantics unchanged
canonical PAPER accounting unchanged
Phase 2B reconciliation semantics unchanged
Phase 3A data-integrity/corporate-action semantics unchanged
Phase 3B governance semantics unchanged
no provider fallback introduced
no second accounting engine introduced
no LIVE broker execution introduced
no frontend redesign
```

---

# 65. Completion criteria

Phase 3C is complete when:

- a STAGING/PROD exact strategy version can create a governed PAPER deployment;
- deployment identity comes from governance, not client claims;
- approved strategy config can be reconstructed and verified;
- completed eligible market observations run the strategy automatically;
- raw execution ticks do not redefine daily strategy semantics;
- strategy state is restart-safe;
- duplicate market events cannot duplicate intents/orders;
- strategy-generated orders use canonical Phase 2A PAPER execution;
- no-same-observation execution is enforced;
- risk checks are deterministic and fail closed;
- risk never silently resizes strategy intent;
- pause/resume/stop/halt work;
- halt cancels only deployment-owned orders and does not liquidate;
- manual PAPER workflows remain intact;
- Phase 2B can use the resulting PAPER run normally;
- Phase 3B does not auto-promote;
- no broker/live-money path is invoked;
- migration is safe;
- prior phases remain green;
- full rebuilt-Docker backend suite passes;
- frontend is untouched;
- Phase 3D is not started.

---

# 66. Final Codex report

When complete, stop and report exactly:

## Deployment architecture

Report:

```text
governance gate
strategy config reconstruction
strategy capability model
market event model
causality ordering
warm-up source
strategy state/checkpoint model
input idempotency
intent idempotency
canonical order bridge
risk controls
lifecycle semantics
halt behavior
reconciliation lineage
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
tables
constraints/indexes
fresh upgrade
0018 -> Phase 3C upgrade
downgrade
one-head result
legacy PAPER retention
governance retention
simulation/reconciliation retention
```

## Tests

Report exact command/result for:

```text
Phase 3C tests
Phase 1
Phase 2A
Phase 2B
Phase 2C
Phase 3A
Phase 3B
full simulation suite
full rebuilt-Docker backend suite
compile check
git diff --check
```

## Scope confirmation

Explicitly answer:

```text
BACKTEST semantics changed? Yes/No
REPLAY semantics changed? Yes/No
manual PAPER semantics changed? Yes/No
PAPER accounting changed? Yes/No
Phase 2B reconciliation semantics changed? Yes/No
Phase 3A integrity semantics changed? Yes/No
Phase 3B governance semantics changed? Yes/No
automatic PROD promotion introduced? Yes/No
LIVE/broker execution introduced? Yes/No
frontend changed? Yes/No
Phase 3D started? Yes/No
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

# 67. Codex kickoff prompt

```text
Read Phase_3C_Strategy_Deployment_and_Automated_Paper_Validation.md in docs/architecture/.

Treat:
- OpenTerminalUI_Assessment_and_Direction.md as architectural context
- OpenTerminalUI_Simulation_Implementation_Blueprint.md as the canonical simulation foundation
- Phase 1A through Phase 1E as completed
- Phase 2A Canonical Paper Trading as completed
- Phase 2B Backtest/Paper Reconciliation as completed
- Phase 2C Historical Replay as completed
- Phase 3A Corporate Actions & Market-Data Integrity Hardening as completed
- Phase 3B Governance & Strategy Promotion as completed
- Codex_Phase_3C_Strategy_Deployment_and_Automated_Paper_Validation.md as the current implementation task

Work only on feat/simulation-core.
Baseline checkpoint is 2f2007d.

Implement Phase 3C exactly as specified.

Plain-English objective:
A governance-approved strategy should be able to run itself in PAPER mode. When eligible forward/live market observations arrive, the exact approved strategy evaluates automatically, emits order intents, passes deterministic safety checks, and submits accepted orders through the existing canonical PAPER engine.

Critical rules:

1. Do not build another trading/accounting engine.
2. All economic orders/fills/cash/positions/ledger/settlement remain canonical Phase 2A PAPER truth.
3. Automated deployment requires a Phase 3B governance record in STAGING or PROD.
4. The exact strategy_key + strategy_hash + approved configuration come from governance/baseline evidence, not client claims.
5. Do not let the deployment request silently change strategy params or universe.
6. Reconstruct the strategy from approved canonical baseline request/manifest and verify identity.
7. Explicitly model strategy deployment capability.
8. Phase 3C v1 must preserve the existing daily VERIFIED strategy semantics: strategy decisions are driven by finalized completed daily bars, not every raw tick.
9. Existing PAPER ticks continue to drive marks and order execution.
10. Enforce strict no-lookahead/no-same-observation execution. An order caused by observation N cannot fill on observation N.
11. Use persisted/versioned data for strategy warm-up. No provider/synthetic fallback.
12. Persist strategy state/checkpoints and restore them after restart.
13. Require stable source_event_id for strategy-driving observations.
14. Duplicate/concurrent input must not duplicate strategy evaluation, intent, or canonical order.
15. Give every emitted intent a deterministic identity and pass it as strategy_order_id/lineage on the canonical PAPER order.
16. Add a deterministic deployment risk layer based on canonical account state.
17. Risk may reject an intent but must never silently resize it.
18. Implement allowed-universe, max-order-notional, max-position-percent, max-open-strategy-orders, and max-daily-loss controls.
19. Risk/kill-switch HALT cancels only deployment-owned open orders and does not liquidate positions.
20. Manual PAPER orders/portfolios must remain compatible and must not require governance.
21. Harden or adapt the existing /paper/deploy-strategy endpoint so it cannot misleadingly create an arbitrary labeled portfolio as a governed automated deployment.
22. Preserve order/fill/settlement/partial-fill semantics in the canonical PAPER engine.
23. Phase 3C creates PAPER evidence only. Do not auto-create reconciliation and do not auto-promote governance.
24. Never create a LIVE run or call a broker order API.
25. Frontend is Phase 3D. Do not modify frontend.
26. Do not start Phase 3D or Phase 3E.
27. Inspect the actual Alembic head first and use the next valid revision.
28. Preserve all existing data/migrations.
29. Add focused crash/retry, duplicate-input, concurrency, restart-state and no-same-observation tests.
30. Do not commit or push.

At completion run targeted Phase 3C tests, all prior phase regression suites, full simulation tests, compile check, git diff --check, and one full backend suite using a rebuilt Docker image:

docker compose up -d --build
docker compose exec backend python -m pytest backend/tests/ -q

Stop once all completion criteria pass and return the requested report.
```

---

## End of Phase 3C specification
