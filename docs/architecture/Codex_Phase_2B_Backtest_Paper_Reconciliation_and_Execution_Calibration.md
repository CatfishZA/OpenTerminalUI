# Codex Phase 2B — Backtest/Paper Reconciliation & Execution Calibration

**Repository:** `CatfishZA/OpenTerminalUI`  
**Branch:** `feat/simulation-core`  
**Baseline:** Phase 2A checkpoint `5e60902`  
**Status:** Implementation task specification  
**Primary objective:** Add an immutable comparison layer over canonical BACKTEST and PAPER runs so the system can explain where intended orders, fills, costs, settlement, and account outcomes diverge—without changing either execution engine.

---

## 1. Engineering decision

Phase 2B is **not a new simulator**.

Phase 1 created the authoritative deterministic BACKTEST path. Phase 2A moved new PAPER portfolios onto the same canonical orders, fills, account, settlement, ledger, events, and snapshots.

Phase 2B adds a read-only cross-run reconciliation layer:

```text
                    SAME STRATEGY / INTENT
                             │
               ┌─────────────┴─────────────┐
               ▼                           ▼
        CANONICAL BACKTEST            CANONICAL PAPER
        historical daily bars          live ticks
               │                           │
               ├──── orders ───────────────┤
               ├──── fills ────────────────┤
               ├──── ledger ───────────────┤
               ├──── snapshots ────────────┤
               └──── account state ────────┘
                             │
                             ▼
                 BACKTEST/PAPER RECONCILIATION
                             │
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
      Intent delta      Execution delta     Cost/account delta
          └──────────────────┼──────────────────┘
                             ▼
                   IMMUTABLE VARIANCE REPORT
                             │
                             ▼
                 EXECUTION-CALIBRATION EVIDENCE
```

Paper execution is still simulated. Never describe PAPER output as real broker execution, actual market impact, true exchange queue behavior, or real slippage.

Use terms such as:

```text
paper simulated slippage
paper observed spread
paper observed tick liquidity
execution-assumption drift
fill-behavior variance
```

---

## 2. Phase 2B objectives

Implement a canonical subsystem that:

1. explicitly pairs one BACKTEST run with one PAPER run;
2. validates how comparable the pair is;
3. captures an immutable PAPER cutoff;
4. aligns corresponding orders without assuming canonical IDs match;
5. aggregates partial fills correctly;
6. identifies unmatched, rejected, cancelled, partial, delayed, and differently-sized execution;
7. compares execution assumptions and canonical fill behavior;
8. compares commissions, fees, settlement configuration, and account results;
9. captures PAPER spread/liquidity evidence at fill time;
10. persists immutable reports and detailed alignment rows;
11. exposes canonical reconciliation APIs;
12. leaves both source runs unchanged.

The existing `ReconciliationService` remains the intra-run accounting identity checker. Do not replace it. Create a separate cross-run service.

---

## 3. Current canonical source of truth

Phase 2B must use existing canonical artifacts:

```text
simulation_runs
simulation_events
simulation_orders
simulation_fills
simulation_ledger_entries
simulation_position_snapshots
simulation_portfolio_snapshots
simulation_settlement_obligations
```

BACKTEST already exposes:

```text
manifest
result hash
orders
fills
ledger
portfolio snapshots
position snapshots
events
```

New PAPER portfolios already use:

```text
SimulationMode.PAPER
VerificationLevel.RESEARCH
SimulationRunStatus.RUNNING
OrderManager
AccountEngine
SettlementEngine
ValuationEngine
canonical execution/commission models
```

Do not create parallel financial records.

---

## 4. Scope

### Included

- BACKTEST ↔ PAPER pairing;
- VERIFIED baseline support;
- optional RESEARCH baseline with explicit warning;
- compatibility assessment;
- PAPER cutoff capture;
- explicit correlation-key matching;
- deterministic fallback matching;
- confidence labels;
- unmatched-order reporting;
- partial-fill aggregation;
- fill-ratio comparison;
- simulated slippage comparison;
- effective commission/fee comparison;
- fill latency comparison;
- PAPER bid/ask spread evidence;
- PAPER tick-size/liquidity evidence;
- execution-profile drift;
- settlement-profile drift;
- account/result side-by-side comparison;
- deterministic report hashing;
- immutable persisted reports;
- canonical API endpoints;
- migration and regression tests;
- optional additive correlation fields on PAPER order submission.

### Not Phase 2B

Do not implement:

- historical replay;
- strategy automation loops;
- live broker routing;
- real-money execution;
- exchange acknowledgements;
- broker account reconciliation;
- L2/L3 queue simulation;
- automatic slippage/model tuning;
- automatic strategy promotion;
- options/futures expansion;
- FX/multi-currency reconciliation;
- governance changes;
- frontend redesign;
- a new chart/dashboard;
- a new backtest engine;
- a new paper engine;
- Phase 3.

---

## 5. Core invariants

### 5.1 Source runs are immutable

Reconciliation may read source runs but must not mutate:

```text
orders
fills
ledger
events
snapshots
settlements
manifest
result hash
run status
```

It may write only Phase 2B-owned reconciliation/observation records.

### 5.2 Reports are immutable

A PAPER run can remain RUNNING.

Every reconciliation must persist:

```text
paper_cutoff_sequence
paper_cutoff_time
```

Once built, the report never changes.

If PAPER progresses, create a new reconciliation.

Do not implement “refresh in place”.

### 5.3 Decimal remains authoritative

Use `Decimal` for all reconciliation-critical arithmetic:

```text
VWAP
notional
fill ratio
slippage bps
commission bps
fee bps
spread bps
participation
cash/equity deltas
```

### 5.4 Missing evidence remains missing

Never fabricate:

```text
spread
tick size
liquidity
correlation keys
broker fills
settlement-calendar equivalence
```

---

## 6. New domain model

Create:

```text
backend/simulation/domain/reconciliation.py
```

Suggested enums:

```text
ReconciliationStatus:
    BUILDING
    DONE
    FAILED

AlignmentPolicy:
    KEYED_THEN_SIGNATURE
    KEYS_ONLY

MatchStatus:
    MATCHED
    BASELINE_ONLY
    PAPER_ONLY
    AMBIGUOUS

MatchBasis:
    RECONCILIATION_KEY
    STRATEGY_ORDER_ID
    UNIQUE_SIGNATURE
    ORDINAL_FALLBACK
    NONE

MatchConfidence:
    EXACT
    HIGH
    MEDIUM
    LOW
    NONE
```

Suggested request model:

```python
@dataclass(frozen=True, slots=True)
class BacktestPaperReconciliationSpec:
    baseline_run_id: str
    paper_run_id: str
    alignment_policy: AlignmentPolicy = AlignmentPolicy.KEYED_THEN_SIGNATURE
    paper_cutoff_sequence: int | None = None
    allow_research_baseline: bool = False
    include_low_confidence_matches: bool = True
```

---

## 7. Source-run validation

### Baseline

`baseline_run_id` must:

```text
exist
mode == BACKTEST
status == DONE
```

Default:

```text
verification_level == VERIFIED
```

If baseline is RESEARCH:

```text
allow_research_baseline=false -> VERIFIED_BASELINE_REQUIRED
allow_research_baseline=true  -> permit + explicit warning
```

Never upgrade a RESEARCH baseline to VERIFIED in a report.

### PAPER

`paper_run_id` must:

```text
exist
mode == PAPER
```

PAPER may be RUNNING or terminal.

Reject identical source IDs.

### Currency

Phase 2B supports identical base currency only.

Currency mismatch:

```text
CURRENCY_MISMATCH
```

Do not add FX conversion.

### Instruments

Require at least one canonical instrument overlap.

Otherwise:

```text
NO_INSTRUMENT_OVERLAP
```

---

## 8. Compatibility assessment

Every report needs a multidimensional compatibility block.

Example:

```json
{
  "strategy_identity": "EXACT",
  "accounting_comparable": true,
  "intent_comparable": true,
  "execution_assumptions_comparable": true,
  "settlement_comparable": true,
  "performance_comparable": false,
  "instrument_overlap": ["NSE:EQUITY:RELIANCE:INR"],
  "warnings": ["MARKET_PERIODS_DIFFER", "EXECUTION_PROFILE_DIFFERS"]
}
```

Strategy identity:

```text
EXACT:
strategy_key equal and strategy_hash equal

KEY_ONLY:
strategy_key equal but hash differs/unavailable

DIFFERENT:
strategy_key differs
```

A manual PAPER session may still support account/execution analysis, but `intent_comparable` must be false unless explicit correlation keys exist.

Do not collapse compatibility into one boolean.

---

## 9. PAPER cutoff consistency

Use the existing Phase 2A per-run lock.

Conceptually:

```python
async with PaperSimulationService.lock_for(paper_run_id):
    cutoff_sequence = requested_or_current_max_sequence()
    cutoff_time = event_time(cutoff_sequence)
    snapshot required PAPER artifacts
```

If a supplied cutoff does not exist:

```text
PAPER_CUTOFF_NOT_FOUND
```

A generated report must be persisted immediately after calculations.

Important: `simulation_orders` can reflect later mutable order state, so old reconciliation GETs must return stored report data—not silently recompute against later PAPER state.

---

## 10. Correlation keys

Canonical order IDs differ between modes.

Never use:

```text
baseline_order.id == paper_order.id
```

as the general matching mechanism.

Support optional correlation metadata:

```text
reconciliation_key
strategy_order_id
```

Existing PAPER API clients must continue working without these fields.

Preferred matching precedence:

1. exact `reconciliation_key`;
2. exact `strategy_order_id`;
3. deterministic unique signature;
4. optional low-confidence ordinal fallback.

Do not change strategy execution semantics to add correlation metadata.

---

## 11. Deterministic order alignment

Default policy:

```text
KEYED_THEN_SIGNATURE
```

### Pass 1 — reconciliation key

Unique equal key:

```text
basis = RECONCILIATION_KEY
confidence = EXACT
```

### Pass 2 — strategy order ID

Unique equal non-null ID:

```text
basis = STRATEGY_ORDER_ID
confidence = HIGH
```

### Pass 3 — unique signature

For remaining orders use:

```text
instrument key
side
order type
original quantity
normalized limit/stop
relative ordinal within instrument/side/type stream
```

If unique:

```text
basis = UNIQUE_SIGNATURE
confidence = MEDIUM
```

Absolute date equality is not required because historical BACKTEST and live PAPER may represent different periods.

### Pass 4 — ordinal fallback

Only if:

```text
include_low_confidence_matches=true
```

and the candidate is unambiguous.

```text
basis = ORDINAL_FALLBACK
confidence = LOW
```

### Ambiguity rule

If multiple candidates are equally plausible:

```text
do not guess
```

Record:

```text
match_status = AMBIGUOUS
```

---

## 12. Order comparison

For each aligned order compare:

```text
instrument
side
order type
original quantity
time in force
limit price
stop price
final status
filled quantity
remaining quantity
fill count
partial-fill occurrence
cancellation
rejection
submitted-to-accepted latency
submitted-to-first-fill latency
submitted-to-completion latency
```

Suggested divergence codes:

```text
SIDE_MISMATCH
ORDER_TYPE_MISMATCH
QUANTITY_MISMATCH
LIMIT_PRICE_MISMATCH
STOP_PRICE_MISMATCH
STATUS_MISMATCH
BASELINE_ONLY
PAPER_ONLY
AMBIGUOUS_MATCH
PARTIAL_FILL_DIFFERENCE
FILL_RATIO_DIFFERENCE
CANCEL_DIFFERENCE
REJECTION_DIFFERENCE
```

---

## 13. Fill aggregation

One order can have many fills.

Aggregate per order:

```text
fill_count
filled_quantity
fill_ratio
VWAP
total_notional
total_commission
total_fees
effective_commission_bps
effective_fee_bps
quantity-weighted slippage_bps
first_fill_time
last_fill_time
```

Formulae:

```text
VWAP
= sum(price * quantity) / sum(quantity)

effective_commission_bps
= total_commission / total_notional * 10_000

effective_fee_bps
= total_fees / total_notional * 10_000
```

If there is no fill, metrics requiring a fill are `null`.

---

## 14. Execution comparison

Expose for matched orders:

```text
baseline_fill_ratio
paper_fill_ratio
fill_ratio_delta

baseline_vwap
paper_vwap

baseline_simulated_slippage_bps
paper_simulated_slippage_bps
simulated_slippage_delta_bps

baseline_effective_commission_bps
paper_effective_commission_bps
commission_delta_bps

baseline_partial_fill
paper_partial_fill

baseline_time_to_first_fill
paper_time_to_first_fill
```

### Price-delta guard

Historical BACKTEST VWAP and live PAPER VWAP may come from different market periods.

Do not label their raw price difference as slippage.

Expose raw values if useful, but:

```text
direct_price_delta_valid = false
```

unless using a controlled equivalent-price fixture.

---

## 15. PAPER execution observations

Phase 2B needs execution-time PAPER evidence.

Do **not** persist every incoming tick.

Persist one compact observation only when a canonical PAPER fill is created.

Create a Phase 2B concept:

```text
ExecutionObservation
    id
    run_id
    order_id
    fill_id
    instrument
    observed_at
    tick_price
    bid
    ask
    tick_size
    tick_source
    liquidity_assumption
```

At the point where `PaperSimulationService` saves a successful canonical fill, save the exact fill-causing `MarketTick`.

This is additive observability only.

It must not alter:

```text
fill eligibility
fill price
fill quantity
commission
accounting
settlement
order status
tick freshness
```

### Spread

When bid and ask exist:

```text
mid = (bid + ask) / 2
spread_bps = (ask - bid) / mid * 10_000
```

Otherwise:

```text
spread_bps = null
```

### Participation

When tick size > 0:

```text
fill_participation = fill_quantity / tick_size
```

Otherwise:

```text
fill_participation = null
```

Existing Phase 2A fills will not have observation rows. Keep them missing; do not backfill invented data.

---

## 16. Execution-calibration evidence

Phase 2B compares assumptions and observed PAPER simulation behavior.

Report configured values from both source runs:

```text
execution model
slippage bps
max participation
commission model
commission value/bps
settlement days
daily path policy where applicable
```

Report PAPER fill-time evidence:

```text
spread bps coverage/distribution
tick-size coverage
fill participation distribution
simulated slippage distribution
effective commission bps
partial-fill rate
cancellation rate
rejection rate
time-to-first-fill distribution
```

Suggested statistics:

```text
count
mean
median
p90
p95
min
max
```

Implement deterministic statistics without adding NumPy/Pandas solely for this phase.

### No automatic tuning

Do not write calibration results back into:

```text
backtest execution profile
paper execution profile
strategy config
saved presets
governance records
```

Phase 2B produces evidence only.

---

## 17. Assumption drift

Generate explicit drift codes such as:

```text
SLIPPAGE_PROFILE_DIFFERENT
COMMISSION_PROFILE_DIFFERENT
MAX_PARTICIPATION_DIFFERENT
SETTLEMENT_DAYS_DIFFERENT
DAILY_PATH_NOT_APPLICABLE_TO_PAPER
PAPER_SPREAD_DATA_PARTIAL
PAPER_LIQUIDITY_DATA_PARTIAL
PAPER_EXECUTION_OBSERVATION_MISSING
SETTLEMENT_CALENDAR_NOT_EQUIVALENT
```

Severity:

```text
INFO
WARNING
MATERIAL
```

Be conservative. A configuration-string difference alone is not automatically MATERIAL.

---

## 18. Settlement comparison

Compare:

```text
configured settlement days
pending PAPER obligations at cutoff
settled PAPER obligations at cutoff
baseline settlement behavior
calendar metadata where available
```

The current PAPER engine uses configured date offsets.

If calendar equivalence cannot be proven, report:

```text
SETTLEMENT_CALENDAR_NOT_EQUIVALENT
```

Do not fabricate holiday-calendar adjustments.

---

## 19. Account/result comparison

Expose side-by-side:

```text
initial cash
final/current equity
settled cash
unsettled cash
reserved cash
realized P&L
unrealized P&L
fees
gross exposure
net exposure
position count
order count
fill count
```

### Performance guard

For ordinary historical BACKTEST vs live PAPER:

```text
performance_comparable = false
```

Still return both sets of values.

Do not causally attribute return/P&L differences to execution unless the comparison is a controlled equivalent-market fixture.

---

## 20. Controlled-equivalence fixtures

Phase 2B must prove the reconciliation machinery using controlled canonical fixtures.

### Fixture A — zero divergence

```text
same instrument
same intended side
same quantity
same reconciliation_key
equivalent reference price
zero commission
zero fees
zero slippage
sufficient liquidity
T+0
```

Expected:

```text
EXACT match
fill-ratio delta = 0
simulated-slippage delta = 0
commission delta = 0
quantity delta = 0
no unexplained divergence
```

### Fixture B — intentional liquidity divergence

Same intent, but PAPER tick size constrains fill.

Expected:

```text
BACKTEST fills fully
PAPER fills partially
divergence classified as partial-fill/liquidity behavior
strategy identity remains matched
```

Do not create another simulator for the fixtures.

---

## 21. Persistence

Inspect the actual Alembic head first.

Expected conceptual migration:

```text
0015_backtest_paper_reconciliation.py
```

Use the next valid revision if head differs.

### 21.1 `simulation_reconciliations`

Suggested columns:

```text
id                          string(64) PK  # rec_*
baseline_run_id             FK simulation_runs
paper_run_id                FK simulation_runs
status                      string(16)
alignment_policy            string(32)
allow_research_baseline     bool
include_low_confidence      bool

paper_cutoff_sequence       bigint
paper_cutoff_time           datetime

baseline_manifest_hash      string(128) nullable
baseline_result_hash        string(128) nullable
paper_manifest_hash         string(128) nullable

request_hash                string(128)
report_hash                 string(128) nullable

compatibility_json          JSON
summary_json                JSON
calibration_json            JSON
report_json                 JSON

error                       text
created_at                  datetime
completed_at                datetime nullable
```

Indexes:

```text
baseline_run_id
paper_run_id
created_at
request_hash
```

Recommended:

```text
UNIQUE(request_hash)
```

The resolved PAPER cutoff is part of `request_hash`.

### 21.2 `simulation_reconciliation_items`

```text
id                          bigint PK
reconciliation_id           FK
sequence                    bigint
item_type                   string(16)
instrument_key              string(160)

baseline_order_id           string(64) nullable
paper_order_id              string(64) nullable

match_status                string(24)
match_basis                 string(32)
match_confidence            string(16)

divergence_codes_json       JSON
metrics_json                JSON
```

Constraint:

```text
UNIQUE(reconciliation_id, sequence)
```

Indexes:

```text
(reconciliation_id, item_type)
(reconciliation_id, instrument_key)
match_status
```

### 21.3 `simulation_execution_observations`

```text
id                          string(64) PK
run_id                      FK simulation_runs
order_id                    FK simulation_orders
fill_id                     FK simulation_fills UNIQUE
instrument_key              string(160)

observed_at                 datetime
tick_price                  numeric
bid                         numeric nullable
ask                         numeric nullable
tick_size                   numeric nullable
tick_source                 string(128) nullable
liquidity_assumption        string(64) nullable

metadata_json               JSON
```

This is fill-time evidence, not general tick storage.

---

## 22. Migration rules

Migration must:

- preserve all existing simulation and paper data;
- support current SQLite/Postgres conventions;
- upgrade from actual Phase 2A head;
- downgrade by removing only Phase 2B-owned schema;
- not rebuild canonical source tables unnecessarily.

Verify:

```text
fresh full migration chain
Phase 2A -> Phase 2B
Phase 2B -> Phase 2A
source BACKTEST/PAPER rows retained
```

---

## 23. Service structure

Keep:

```text
backend/simulation/services/reconciliation_service.py
```

for existing intra-run identities.

Create:

```text
backend/simulation/services/backtest_paper_reconciliation_service.py
backend/simulation/services/execution_calibration_service.py
backend/simulation/persistence/reconciliation_repositories.py
```

### `BacktestPaperReconciliationService`

Suggested interface:

```python
async def create(spec) -> ReconciliationReport: ...
def get(reconciliation_id) -> ReconciliationReport: ...
def items(reconciliation_id, ...) -> list[...]: ...
def list_for_run(run_id, ...) -> list[...]: ...
```

Responsibilities:

```text
validate runs
capture PAPER cutoff
load source artifacts
assess compatibility
align orders
aggregate fills
classify divergence
call calibration service
persist immutable report/items
hash report
```

### `ExecutionCalibrationService`

Prefer pure calculations.

It must not mutate execution profiles.

---

## 24. API

Create a dedicated router, e.g.:

```text
backend/simulation/api/reconciliation_routes.py
```

### POST `/api/v1/simulation/reconciliations`

Request:

```json
{
  "baseline_run_id": "sim_backtest123",
  "paper_run_id": "sim_paper456",
  "paper_cutoff_sequence": null,
  "alignment_policy": "KEYED_THEN_SIGNATURE",
  "allow_research_baseline": false,
  "include_low_confidence_matches": true
}
```

Response:

```json
{
  "reconciliation_id": "rec_...",
  "status": "DONE",
  "baseline_run_id": "sim_backtest123",
  "paper_run_id": "sim_paper456",
  "paper_cutoff_sequence": 184,
  "report_hash": "..."
}
```

Synchronous generation is acceptable in Phase 2B.

### GET `/api/v1/simulation/reconciliations/{id}`

Return immutable report.

### GET `/api/v1/simulation/reconciliations/{id}/items`

Filters:

```text
item_type
match_status
instrument
offset
limit
```

### GET `/api/v1/simulation/runs/{run_id}/reconciliations`

List reports where run is baseline or paper source.

No frontend work is required.

---

## 25. Stable errors

Use stable codes:

```text
RECONCILIATION_NOT_FOUND
BASELINE_RUN_NOT_FOUND
PAPER_RUN_NOT_FOUND
BASELINE_MODE_INVALID
PAPER_MODE_INVALID
BASELINE_NOT_DONE
VERIFIED_BASELINE_REQUIRED
CURRENCY_MISMATCH
PAPER_CUTOFF_NOT_FOUND
NO_INSTRUMENT_OVERLAP
RECONCILIATION_BUILD_FAILED
```

Strategy mismatch is normally a compatibility warning, not a hard failure.

---

## 26. Deterministic report hash

Hash canonical report content including:

```text
source run ids
source manifest hashes
baseline result hash where available
resolved PAPER cutoff
alignment policy
compatibility
summary
calibration
ordered detail items
```

Exclude:

```text
database auto IDs
created_at
completed_at
processing timestamps
```

Identical source snapshot + identical cutoff + identical request must yield identical `report_hash`.

Do not modify or recompute source run hashes.

---

## 27. Narrow PAPER integration

Modify the narrowest PAPER path.

When `PaperSimulationService` successfully persists a fill, persist one execution observation from the exact `MarketTick` that caused that fill.

Capture:

```text
tick.price
tick.bid
tick.ask
tick.size
tick.source
liquidity assumption
```

Add a regression test proving this new observability does not change:

```text
fill price
fill quantity
commission
ledger
account state
settlement
order status
```

---

## 28. No BACKTEST semantic changes

Phase 2B may read BACKTEST artifacts.

It must not change:

```text
DailySimulator event ordering
lookahead protections
BAR_CLOSE signal timing
next-open eligibility
daily-path handling
volume participation
commission calculation
cash reservation
settlement
VERIFIED data policy
provider/synthetic fallback policy
```

If controlled fixtures need keys, put them in strategy-intent metadata/test fixtures.

Do not alter execution semantics.

---

## 29. Existing `/paper/*` compatibility

All Phase 2A PAPER requests/responses remain supported.

Optional correlation fields are additive only.

Existing Paper Trading frontend must continue working with no frontend changes.

---

## 30. Suggested file treatment

### Create

```text
backend/simulation/domain/reconciliation.py
backend/simulation/services/backtest_paper_reconciliation_service.py
backend/simulation/services/execution_calibration_service.py
backend/simulation/persistence/reconciliation_repositories.py
backend/simulation/api/reconciliation_routes.py

backend/alembic/versions/0015_backtest_paper_reconciliation.py
# or next valid revision

backend/tests/simulation/test_reconciliation_pairing.py
backend/tests/simulation/test_reconciliation_alignment.py
backend/tests/simulation/test_reconciliation_calibration.py
backend/tests/simulation/test_reconciliation_cutoff.py
backend/tests/simulation/test_reconciliation_api.py
backend/tests/simulation/test_reconciliation_migration.py
```

### Modify narrowly

Likely:

```text
backend/simulation/persistence/models.py
backend/simulation/services/paper_simulation_service.py
backend/simulation/api/schemas.py
backend/simulation/api/__init__.py
backend/simulation/domain/__init__.py
backend/simulation/services/__init__.py
backend/simulation/persistence/__init__.py
backend/api/router.py
```

Possibly:

```text
backend/api/routes/paper.py
```

only for optional additive correlation fields.

Do not modify frontend files.

Do not modify `DailySimulator` unless a genuine correctness defect is discovered; if so, stop and report before broadening scope.

---

## 31. Acceptance tests

Phase 2B is not complete until these are covered.

### R01 — valid VERIFIED BACKTEST + PAPER pair
Reconciliation succeeds and cutoff is persisted.

### R02 — wrong baseline mode rejected
Expected `BASELINE_MODE_INVALID`.

### R03 — wrong paper mode rejected
Expected `PAPER_MODE_INVALID`.

### R04 — RESEARCH baseline denied by default
Expected `VERIFIED_BASELINE_REQUIRED`.

### R05 — RESEARCH baseline allowed explicitly
Report succeeds with RESEARCH warning; never relabel VERIFIED.

### R06 — currency mismatch rejected
Expected `CURRENCY_MISMATCH`.

### R07 — cutoff captured under PAPER lock
Stable sequence/time captured while PAPER can receive ticks.

### R08 — historical report immutable
Later PAPER activity does not change existing report/hash.

### R09 — same resolved request idempotent
Same pair + cutoff + policy yields same request hash and avoids semantic duplication.

### R10 — exact reconciliation-key match
`basis=RECONCILIATION_KEY`, `confidence=EXACT`.

### R11 — strategy-order-id match
Unique equal IDs produce HIGH confidence.

### R12 — unique signature fallback
Deterministic MEDIUM match.

### R13 — ambiguous match not guessed
Record `AMBIGUOUS`.

### R14 — baseline-only order
Record `BASELINE_ONLY`.

### R15 — paper-only order
Record `PAPER_ONLY`.

### R16 — partial fills aggregate correctly
Validate quantity, ratio, VWAP, costs, first/last fill.

### R17 — Decimal VWAP
Use values exposing float error; exact Decimal result required.

### R18 — effective commission bps
Validate formula exactly.

### R19 — simulated slippage delta
Weighted canonical slippage comparison; never call it real slippage.

### R20 — PAPER spread observation
Bid/ask captured and spread bps correct.

### R21 — missing bid/ask honest
Spread remains null.

### R22 — liquidity observation
Tick size yields participation; missing size yields null + preserved assumption.

### R23 — observation capture has zero execution side effects
Canonical Phase 2A results unchanged.

### R24 — settlement drift
T+1 baseline vs T+2 PAPER yields `SETTLEMENT_DAYS_DIFFERENT`.

### R25 — settlement calendar warning
Unprovable equivalence yields `SETTLEMENT_CALENDAR_NOT_EQUIVALENT`.

### R26 — controlled zero-divergence fixture
Equivalent intent/reference/costs/liquidity reconciles cleanly.

### R27 — controlled partial-fill divergence
PAPER liquidity constraint is attributed to fill/liquidity behavior, not strategy mismatch.

### R28 — performance guard
Ordinary historical vs live pair has `performance_comparable=false`.

### R29 — deterministic report hash
Unchanged sources + same cutoff/spec produce same hash.

### R30 — source runs unchanged
Manifest/result hashes and canonical artifact counts unchanged after reconciliation.

### R31 — existing intra-run reconciliation preserved
Current ledger/cash/position/equity reconciliation tests stay green.

### R32 — existing PAPER API preserved
Create/order/cancel/performance remains green.

### R33 — existing VERIFIED invariants preserved
No-lookahead, determinism, verified-data policy, compatibility tests stay green.

### R34 — migration upgrade/downgrade
Fresh chain, Phase 2A→2B, 2B→2A, source rows retained.

### R35 — API pagination/filtering
Items endpoint respects filters and bounds.

### R36 — no frontend dependency
No new reconciliation UI required; current frontend remains functional.

---

## 32. Manual/API acceptance

At completion:

1. obtain one completed canonical BACKTEST run;
2. obtain one canonical PAPER run with at least one canonical fill;
3. POST a reconciliation;
4. GET the report;
5. GET detail items;
6. verify source artifacts remain unchanged;
7. progress PAPER if possible;
8. confirm old report is unchanged;
9. create a new reconciliation and confirm later cutoff.

If no live tick source is available, use the controlled canonical fixture.

Do not fabricate a live-market demonstration.

---

## 33. Testing strategy

During development:

```text
1. alignment/domain tests
2. calibration tests
3. cutoff/immutability tests
4. API tests
5. migration tests
6. Phase 2A PAPER tests
7. focused Phase 1/VERIFIED tests
```

Final exact-tree checks:

```text
pytest backend/tests/simulation/ -q
selected existing paper API regression tests
Python compile check
git diff --check
git status --short
git diff --stat
```

Run the full backend suite once only after targeted tests are green and if time permits.

If the known Windows `tmp_path` issue appears, rerun only affected tests using repository-local temporary storage and document it.

---

## 34. Non-regression contract

These must remain true:

```text
VERIFIED has no synthetic fallback
VERIFIED requires persisted versioned data
no same-close lookahead
canonical money arithmetic uses Decimal
canonical PAPER does not call legacy _fill_order()
legacy unlinked portfolios remain legacy
missing/stale PAPER ticks do not fabricate fills
PAPER cash reservations remain authoritative
PAPER settlement survives restart
event sequence remains monotonic
Virtual* remains a compatibility projection
```

Reconciliation is not a new financial authority.

---

## 35. Completion criteria

Phase 2B is complete when:

- BACKTEST/PAPER pairs can be explicitly reconciled;
- compatibility is assessed honestly;
- PAPER cutoff is immutable;
- alignment is deterministic and confidence-labelled;
- ambiguity is never guessed;
- partial fills aggregate correctly;
- execution-assumption drift is reported;
- PAPER fill-time spread/liquidity evidence is captured when available;
- missing historical observations remain missing;
- settlement differences are reported;
- performance comparison is guarded;
- report hashes are deterministic;
- source runs remain unchanged;
- APIs work;
- migration upgrade/downgrade works;
- Phase 2A tests remain green;
- focused Phase 1/VERIFIED tests remain green;
- no frontend redesign occurred;
- Phase 3 was not started.

---

## 36. Final Codex report

When complete, stop and report:

### Implementation
- domain/services/repositories/routes;
- source pairing;
- alignment strategy;
- cutoff behavior;
- execution-observation capture;
- calibration metrics;
- persistence/hash behavior.

### Files
Separate created and modified files.

### Migration
Report:

```text
revision
down_revision
tables added
indexes/constraints
upgrade result
downgrade result
source-data retention
```

### Tests
Report exact commands/results for:

```text
Phase 2B tests
Phase 2A PAPER tests
focused Phase 1/VERIFIED tests
simulation suite
compile check
git diff --check
```

### Scope confirmation
Explicitly state:

```text
DailySimulator semantics changed? Yes/No
VERIFIED fallback policy changed? Yes/No
PAPER accounting changed? Yes/No
frontend changed? Yes/No
live broker introduced? Yes/No
automatic model tuning introduced? Yes/No
Phase 3 started? Yes/No
```

### Git
Report:

```text
git status --short
git diff --stat
```

Do not commit or push.

Wait for review.

---

# 37. Codex kickoff prompt

```text
Read all documents in docs/architecture/.

Treat:
- OpenTerminalUI_Assessment_and_Direction.md as architectural context
- OpenTerminalUI_Simulation_Implementation_Blueprint.md as the canonical simulation foundation
- Phase 1A through Phase 1E as completed
- Codex_Phase_2A_Canonical_Paper_Trading_Unification.md as completed Phase 2A context
- Codex_Phase_2B_Backtest_Paper_Reconciliation_and_Execution_Calibration.md as the current task

Implement Phase 2B exactly as specified.

Work only on feat/simulation-core.

This phase adds an immutable comparison/reconciliation layer over existing canonical BACKTEST and PAPER runs.

It is NOT:
- a new simulator
- historical replay
- a paper-engine rewrite
- a backtest-engine rewrite
- live brokerage
- real-money execution
- automatic execution-model tuning
- a frontend redesign

Critical requirements:
- source runs remain immutable
- existing intra-run ReconciliationService remains intact
- PAPER cutoff is captured under the existing per-run PAPER lock
- reports are immutable
- order matching never assumes canonical IDs are shared
- explicit reconciliation keys are preferred
- fallback matches are deterministic and confidence-labelled
- ambiguous matches are never guessed
- partial fills are aggregated with Decimal
- PAPER spread/liquidity evidence comes only from actual fill-causing ticks
- missing observations remain null
- PAPER execution is described as simulated, not real broker execution
- performance deltas are not causally attributed across different market periods
- no execution configuration is automatically rewritten
- VERIFIED semantics remain unchanged
- Phase 2A PAPER accounting remains unchanged
- existing /paper/* compatibility remains intact

Inspect the real Alembic head before creating the migration.
Use the next valid revision.

Use targeted tests during implementation.
At the end run the required Phase 2B, Phase 2A, Phase 1/VERIFIED, migration, compile, and git checks.

Do not commit or push.

Stop after Phase 2B completion criteria pass and return the full requested report.
```

---

## End of Phase 2B specification
