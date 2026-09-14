# Codex Phase 3A — Corporate Actions & Market-Data Integrity Hardening

**Repository:** `CatfishZA/OpenTerminalUI`  
**Branch:** `feat/simulation-core`  
**Baseline:** Phase 2C checkpoint `d53be88`  
**Status:** Implementation task specification  
**Phase:** 3A  
**Primary objective:** Make canonical historical simulation more trustworthy by correctly applying stock splits and cash dividends and by refusing to run VERIFIED BACKTEST/REPLAY simulations on broken, inconsistent, incomplete, or mismatched persisted market data.

---

## 0. Plain-English goal

This phase has two jobs.

### Job A — Handle company events correctly

Examples:

```text
2-for-1 stock split:
100 shares at average cost 200
becomes
200 shares at average cost 100

Total economic cost basis does not magically double.
```

```text
Cash dividend:
Hold eligible shares
→ cash entitlement is created
→ cash is credited on the configured/known pay date
```

### Job B — Stop bad historical data from producing believable-looking but wrong backtests

Examples:

```text
duplicate daily bar
missing required session
negative volume
high < low
open outside high/low
wrong data version
corporate action with impossible values
```

VERIFIED runs must fail clearly rather than quietly guessing.

RESEARCH runs may be more permissive only where explicitly specified, and must carry warnings.

---

# 1. Why this phase exists

BACKTEST and REPLAY now share one canonical daily session kernel.

That makes Phase 3A the correct place to add corporate-action handling because both historical modes must see the same split/dividend behavior.

The shared daily kernel already has a `CORPORATE_ACTION` point in the session order, but the current implementation only emits an empty applied-action list.

The existing corporate-action adapter already converts stored actions into canonical `SPLIT` and `CASH_DIVIDEND` objects.

Phase 3A completes that path.

---

# 2. Critical scope boundary

This is a correctness/hardening phase.

Do not:

- redesign frontend;
- change strategy semantics;
- change BACKTEST/REPLAY order timing;
- change PAPER accounting;
- start LIVE broker work;
- add asset classes;
- auto-download missing VERIFIED data;
- silently repair suspicious prices;
- back-adjust source price rows in place;
- rewrite historical datasets during simulation.

---

# 3. Modes affected

## BACKTEST

Corporate actions and market-data checks must be fully integrated.

## REPLAY

Must use the exact same historical corporate-action behavior through the shared daily kernel.

BACKTEST and REPLAY must remain economically equivalent for identical specs/data.

## PAPER

Phase 3A must **not change canonical PAPER accounting behavior**.

The new corporate-action engine should be reusable later, but do not introduce unversioned live corporate-action processing into PAPER in this phase.

---

# 4. Corporate actions supported in Phase 3A

Support only:

```text
SPLIT
CASH_DIVIDEND
```

Do not implement yet:

```text
spin-offs
rights issues
mergers
symbol changes
delistings
stock dividends
special tax treatment
tender offers
cash-in-lieu rounding rules
```

If an unsupported action appears in VERIFIED source data, fail with a clear stable error.

Do not silently ignore it.

---

# 5. Canonical corporate-action engine

Create:

```text
backend/simulation/engine/corporate_action_engine.py
```

Suggested interface:

```python
class CorporateActionEngine:
    def apply_session_actions(
        self,
        account: AccountState,
        actions: Iterable[CorporateAction],
        session: date,
        *,
        open_orders: dict[str, Order],
    ) -> CorporateActionApplicationResult:
        ...
```

Use canonical:

```text
AccountState
Position
Order
LedgerEntry
Decimal
```

Do not depend on legacy backtest records or Virtual* PAPER tables.

---

# 6. Session timing

Corporate actions are processed at the existing shared daily-kernel point:

```text
SESSION_START
SETTLEMENT
CORPORATE_ACTION   ← apply Phase 3A actions here
BAR_OPEN
...
```

Relevant structural changes must occur before:

```text
BAR_OPEN valuation
open-order matching
strategy callbacks
```

Timing must be identical in BACKTEST and REPLAY.

---

# 7. Stock split behavior

Interpret factor as:

```text
2.0 = 2-for-1
0.5 = 1-for-2 reverse split
```

For an existing long position:

```text
new quantity     = old quantity × factor
new average cost = old average cost ÷ factor
```

Economic cost basis must remain unchanged, subject only to Decimal precision:

```text
old quantity × old average cost
==
new quantity × new average cost
```

Also adjust:

```text
last mark ÷ factor
```

A split must not create realized P&L.

A split must not create trade-principal cash movement.

---

# 8. Fractional split quantities

The canonical engine already uses Decimal quantities.

Preserve exact Decimal split mathematics.

Do not invent integer rounding or cash-in-lieu rules because canonical lot-size/whole-share policy is not modeled yet.

Example:

```text
3 shares
1-for-2 reverse split
→ 1.5 canonical shares
```

Do not silently round.

---

# 9. Split handling for open orders

Open orders must remain economically equivalent across a split.

For an order on the affected instrument:

```text
quantity           × factor
remaining quantity × factor
limit price        ÷ factor, if present
stop price         ÷ factor, if present
```

For accepted BUY-order cash reservations, preserve equivalent reserved economic value.

For SELL orders, committed share quantity adjusts by the same factor.

No short position may be introduced by split processing.

Persist adjusted canonical order state.

---

# 10. Split audit trail

For every applied split:

1. preserve source corporate-action ID;
2. create canonical applied-action record in `simulation_applied_corporate_actions`;
3. emit a `CORPORATE_ACTION` event containing at least:

```text
source action id
instrument
action type
factor
old quantity
new quantity
old average cost
new average cost
adjusted open-order IDs
```

A split must not create fake cash.

If a zero-amount ledger row conflicts with existing ledger conventions, use the event + applied-action record rather than inventing money.

---

# 11. Duplicate-application protection

A corporate action may only be applied once per run.

Use the existing uniqueness concept:

```text
(run_id, corporate_action_source_id)
```

Before applying, check whether it was already recorded.

This is essential for REPLAY retry/restart.

---

# 12. Cash dividend behavior

Cash dividends require two separate concepts:

```text
entitlement
payment
```

The implementation must know:

```text
who was eligible
how many shares were eligible
amount per share
when cash is paid
```

Do not simply add cash because a source row exists.

---

# 13. Dividend date policy

The canonical domain already supports:

```text
ex_date
record_date
pay_date
```

Phase 3A must stop pretending unknown dates are known.

## VERIFIED rule

For a VERIFIED cash dividend, require enough source information to determine:

```text
ex_date
pay_date
cash amount
currency
```

If required dividend dates are unavailable:

```text
CORPORATE_ACTION_DATE_INCOMPLETE
```

Do not silently set pay date equal to action date.

## RESEARCH rule

If a legacy dividend record contains only old `action_date`, RESEARCH may use the documented compatibility assumption:

```text
legacy action_date used as both effective entitlement date and payment date
```

but must emit:

```text
LEGACY_DIVIDEND_DATE_ASSUMPTION
```

Never apply this assumption to VERIFIED.

---

# 14. Dividend entitlement

For daily historical simulation, establish entitlement using holdings that exist immediately before the ex-date session begins.

Conceptually:

```text
eligible shares = position quantity entering ex-date session
```

Entitlement amount:

```text
eligible shares × cash amount per share
```

Persist enough canonical information that later position changes cannot alter the entitlement.

---

# 15. Dividend payment

On the known pay date/session:

```text
cash += dividend entitlement
```

Create canonical:

```text
DIVIDEND ledger entry
corporate-action/payment event
```

Update canonical cash/equity/buying power correctly.

Dividend cash must not change:

```text
position quantity
average cost
realized trading P&L
```

Do not mislabel dividend income as trading profit.

---

# 16. Dividend persistence / restart safety

REPLAY may establish entitlement and pay days later after service restart.

Persist dividend obligations.

Create a canonical table if no existing table cleanly represents this.

Suggested:

```text
simulation_corporate_action_entitlements
```

Possible fields:

```text
id
run_id
corporate_action_source_id
instrument_key
action_type
entitlement_date
pay_date
eligible_quantity
cash_amount_per_share
currency
total_amount
status          # PENDING / PAID
created_at
paid_at
```

Constraint:

```text
UNIQUE(run_id, corporate_action_source_id)
```

If a suitable existing canonical schema already covers this, reuse it instead of creating duplicate authority.

---

# 17. Corporate-action source hardening

Inspect the actual source model and migration history before editing.

The canonical `CorporateAction` domain already supports:

```text
ex_date
record_date
pay_date
factor
cash_amount
currency
data_version_id
```

If source persistence lacks fields needed for accurate VERIFIED dividends, add nullable compatibility fields rather than deleting/changing old fields.

Suggested additions only if missing:

```text
ex_date
record_date
pay_date
currency
source
metadata_json
```

Retain legacy:

```text
action_date
factor
amount
```

Existing rows must survive migration unchanged.

---

# 18. Corporate-action adapter policy

Harden:

```text
backend/simulation/adapters/corporate_actions_adapter.py
```

The adapter must:

- select actions for requested data version;
- avoid cross-version contamination;
- convert supported source types deterministically;
- preserve source action identity;
- prefer explicit ex/record/pay dates;
- expose compatibility warnings for legacy RESEARCH rows;
- reject incomplete VERIFIED actions;
- reject invalid factors/negative dividend amounts;
- order results deterministically;
- not silently skip unknown VERIFIED action types.

---

# 19. Data-version rule

For VERIFIED historical simulation, every corporate action used must belong to the requested data version.

Do not treat an unversioned corporate-action row as VERIFIED data.

Policy:

```text
VERIFIED:
  exact requested data_version_id required

RESEARCH:
  legacy null-version row may be allowed with warning
```

Warning:

```text
LEGACY_UNVERSIONED_CORPORATE_ACTION
```

---

# 20. Market-data integrity service

Create:

```text
backend/simulation/services/market_data_integrity_service.py
```

This becomes the canonical preflight validator for historical BACKTEST/REPLAY market data.

Do not duplicate different checks in each mode.

Suggested result:

```python
@dataclass(frozen=True)
class MarketDataIntegrityReport:
    status: str
    errors: tuple[DataQualityIssue, ...]
    warnings: tuple[DataQualityIssue, ...]
    instrument_summaries: ...
    corporate_action_summary: ...
    report_hash: str
```

---

# 21. Required bar checks

For every requested instrument/data version check:

### Existence

At least one bar exists.

### Version

Every bar belongs to requested data version.

### Date range

Bars fall inside requested start/end.

### Ordering

Session dates are monotonic.

### Duplicates

At most one daily bar per instrument/session.

### Positive prices

Require:

```text
open > 0
high > 0
low > 0
close > 0
```

### OHLC structure

Require:

```text
high >= open
high >= close
high >= low

low <= open
low <= close
low <= high
```

### Volume

Require:

```text
volume >= 0
```

Zero volume is allowed unless an existing instrument-specific rule says otherwise.

---

# 22. Session coverage

For VERIFIED multi-instrument simulations, required session coverage must remain internally consistent.

Do not fill missing sessions with:

```text
previous close
synthetic zero-volume bar
provider fallback
another venue
another symbol
```

If required coverage is missing:

```text
VERIFIED_DATA_MISSING
```

Return detail including instrument/date/data version.

---

# 23. Calendar honesty

Do not invent a perfect exchange calendar if the repository does not currently have one.

Use persisted/versioned calendar metadata when available.

If no authoritative session calendar exists:

- validate internal cross-instrument coverage;
- report the limitation;
- do not fabricate holidays/weekends.

Suggested warning:

```text
AUTHORITATIVE_CALENDAR_UNAVAILABLE
```

---

# 24. Suspicious price discontinuities

Large overnight moves can indicate:

```text
real market movement
split
bad data
missing corporate action
```

Do not auto-fix them.

Implement an optional conservative warning when a structural price ratio is extreme and no matching split exists nearby.

Suggested warning:

```text
SUSPICIOUS_PRICE_DISCONTINUITY
```

Warning only; never mutate source data.

---

# 25. Split-price consistency warning

For unadjusted data, a split often creates an approximate inverse price ratio.

Where enough data exists, compare previous close / split factor / next open and warn only if wildly inconsistent.

Suggested warning:

```text
SPLIT_PRICE_DISCONTINUITY_UNEXPLAINED
```

Do not auto-correct.

---

# 26. Source bars remain immutable

Never change persisted source prices during simulation.

Do not run:

```text
UPDATE PriceEodORM ...
```

to “fix” data.

Corporate actions change simulated account state, not historical source rows.

---

# 27. Adjusted vs unadjusted data policy

The current versioned adapter identifies the canonical source as unadjusted.

Phase 3A uses:

```text
unadjusted historical prices
+
explicit canonical corporate actions
```

Do not also back-adjust those bars inside simulation.

That would double-count splits/dividends.

If an adjusted dataset is supported later, guard against applying account-level corporate actions twice.

Suggested error:

```text
ADJUSTED_DATA_CORPORATE_ACTION_CONFLICT
```

---

# 28. Data-quality report in result/provenance

Historical BACKTEST and REPLAY result/provenance should include structured data-quality information.

At minimum:

```text
status
data_version_id
bar count
instrument coverage
errors
warnings
corporate actions found
corporate actions applied
legacy assumptions
integrity report hash
```

VERIFIED success:

```text
status = VALID
errors = []
```

---

# 29. Fail before trading

For VERIFIED BACKTEST/REPLAY, hard integrity validation must happen before the first strategy callback/order.

If validation fails:

```text
no fills
no trade ledger activity
no strategy execution
run FAILED
```

REPLAY creation may validate the entire stored range while still preventing future bars from being visible to the strategy cursor.

---

# 30. Applied corporate-action persistence

Use existing:

```text
simulation_applied_corporate_actions
```

as authoritative evidence that an action affected a run.

Persist source ID, instrument, action type, effective time and deterministic payload.

For split payload include:

```text
factor
position before/after
orders adjusted
```

For dividend include:

```text
eligible quantity
per-share amount
total amount
pay date
payment status/reference
```

---

# 31. Determinism

Given identical:

```text
run spec
data version
corporate-action source rows
code hash
engine version
seed
```

BACKTEST/REPLAY must produce identical:

```text
action ordering
position adjustments
open-order adjustments
dividend entitlements
dividend payments
ledger entries
events
snapshots
final economics
```

Replay restart must not change any action result.

---

# 32. BACKTEST ↔ REPLAY equivalence extension

Extend Phase 2C equivalence tests with:

```text
split fixture
cash-dividend fixture
split + open-order fixture
dividend + later-sell fixture
```

Normalized outputs must remain economically equivalent.

---

# 33. Split acceptance example

Fixture:

```text
Day 1:
BUY 100 @ 200

Before Day 3 open:
2-for-1 split
```

Expected before Day 3 matching:

```text
quantity = 200
average cost = 100
cost basis unchanged
no realized P&L
```

If an open GTC limit sell existed:

```text
SELL 100 @ 240
```

then after split:

```text
SELL 200 @ 120
```

Economic intent is unchanged.

---

# 34. Reverse-split acceptance example

```text
position:
3 shares @ 100

reverse split:
factor = 0.5

expected:
1.5 shares @ 200
cost basis = 300
```

No rounding, no cash-in-lieu, no realized P&L.

---

# 35. Dividend acceptance example

```text
position entering ex-date:
100 shares

dividend:
5 per share

entitlement:
500
```

Selling after entitlement but before pay date must not destroy entitlement.

On pay date:

```text
cash +500
DIVIDEND ledger +500
```

A position opened after entitlement receives no prior dividend.

---

# 36. Dividend restart acceptance example

REPLAY:

1. reach ex-date and create entitlement;
2. stop/restart service;
3. resume;
4. sell shares before pay date;
5. reach pay date.

Expected:

```text
original entitlement pays correctly once
```

No double payment.

---

# 37. Stable errors and warnings

Reuse existing errors where appropriate.

Suggested hard errors:

```text
CORPORATE_ACTION_INVALID
CORPORATE_ACTION_UNSUPPORTED
CORPORATE_ACTION_DATE_INCOMPLETE
CORPORATE_ACTION_VERSION_MISMATCH
CORPORATE_ACTION_DUPLICATE
ADJUSTED_DATA_CORPORATE_ACTION_CONFLICT
INVALID_OHLC
DUPLICATE_BAR
VERIFIED_DATA_MISSING
```

Suggested warnings:

```text
LEGACY_DIVIDEND_DATE_ASSUMPTION
LEGACY_UNVERSIONED_CORPORATE_ACTION
AUTHORITATIVE_CALENDAR_UNAVAILABLE
SUSPICIOUS_PRICE_DISCONTINUITY
SPLIT_PRICE_DISCONTINUITY_UNEXPLAINED
```

---

# 38. Migration

Inspect the actual Alembic head first.

Expected conceptual next revision:

```text
0017_corporate_actions_data_integrity.py
```

Use the next valid revision if head differs.

Migration may include:

```text
simulation_corporate_action_entitlements
```

and, only if current source schema lacks required fields:

```text
nullable corporate-action source date/currency/metadata columns
```

Preserve:

```text
Phase 1 simulation data
Phase 2A PAPER data
Phase 2B reconciliation data
Phase 2C replay data
legacy corporate-action rows
price rows
data versions
```

Downgrade removes only Phase 3A-owned schema changes.

Never delete legacy corporate-action source rows on downgrade.

---

# 39. Suggested implementation files

## Create

Likely:

```text
backend/simulation/engine/corporate_action_engine.py
backend/simulation/services/market_data_integrity_service.py
backend/simulation/persistence/corporate_action_repositories.py

backend/alembic/versions/0017_corporate_actions_data_integrity.py
# or next valid revision

backend/tests/simulation/test_corporate_action_splits.py
backend/tests/simulation/test_corporate_action_dividends.py
backend/tests/simulation/test_corporate_action_restart.py
backend/tests/simulation/test_market_data_integrity.py
backend/tests/simulation/test_corporate_action_equivalence.py
backend/tests/simulation/test_phase3a_migration.py
```

## Modify narrowly

Expected:

```text
backend/simulation/engine/daily_session_kernel.py
backend/simulation/adapters/corporate_actions_adapter.py
backend/simulation/adapters/versioned_data_adapter.py
backend/simulation/domain/corporate_actions.py
backend/simulation/persistence/models.py
backend/simulation/services/replay_simulation_service.py
backend/simulation/services/simulation_service.py
```

Possibly source model/service files only if required by actual schema.

Do not touch frontend.

Do not change PAPER semantics.

---

# 40. Acceptance tests

Phase 3A is not complete until these behaviors are covered.

### CA01 — normal split
Quantity multiplies, average cost divides, cost basis unchanged.

### CA02 — reverse split
Fractional Decimal quantity preserved exactly.

### CA03 — split creates no trade P&L
No realized trade P&L from structural adjustment.

### CA04 — split adjusts open limit order
Quantity/remaining/limit price adjusted economically.

### CA05 — split adjusts stop order
Quantity/remaining/stop price adjusted economically.

### CA06 — split preserves BUY reservation economics
No cash magically created/destroyed.

### CA07 — split adjusts SELL commitment
No accidental short exposure.

### CA08 — split applies once
Replay retry/restart cannot double-apply.

### CA09 — applied-action row persisted
Source ID and deterministic payload stored.

### CA10 — corporate-action event emitted
Event includes applied details.

### CA11 — dividend entitlement
Eligible shares captured at entitlement point.

### CA12 — dividend later sale
Selling after entitlement does not remove pending dividend.

### CA13 — dividend payment
Correct cash credited on pay date.

### CA14 — dividend not trade P&L
Payment not mislabeled as trading profit.

### CA15 — dividend paid once
Retry/restart cannot duplicate payment.

### CA16 — dividend restart
Entitlement survives service restart.

### CA17 — post-entitlement buyer excluded
Shares acquired after entitlement do not receive prior dividend.

### CA18 — VERIFIED incomplete dividend rejected
Missing required dates fail before trading.

### CA19 — RESEARCH legacy date assumption
Allowed only with explicit warning.

### CA20 — VERIFIED exact data-version action
Action belongs to requested version.

### CA21 — VERIFIED unversioned action rejected
No null-version action silently promoted to VERIFIED.

### CA22 — unsupported VERIFIED action rejected
Do not silently ignore.

### DQ01 — no bars
Clear instrument-data error.

### DQ02 — wrong data version
Rejected.

### DQ03 — duplicate daily bar
Rejected.

### DQ04 — non-monotonic sessions
Rejected.

### DQ05 — zero/negative OHLC
Rejected.

### DQ06 — high below open/close/low
Rejected.

### DQ07 — low above open/close/high
Rejected.

### DQ08 — negative volume
Rejected.

### DQ09 — zero volume
Allowed unless existing instrument rule says otherwise.

### DQ10 — missing VERIFIED session
Rejected without synthetic fill.

### DQ11 — inconsistent multi-instrument coverage
Rejected under VERIFIED policy.

### DQ12 — suspicious discontinuity
Warning only; source data unchanged.

### DQ13 — split consistency warning
No auto-correction.

### DQ14 — validation before strategy
Malformed VERIFIED data creates no trade artifacts.

### DQ15 — integrity report deterministic
Identical source rows/spec produce identical integrity hash.

### EQ01 — split BACKTEST/REPLAY equivalence
Normalized results equal.

### EQ02 — dividend BACKTEST/REPLAY equivalence
Normalized results equal.

### EQ03 — replay restart equivalence with pending dividend
Normalized result unchanged.

### REG01 — Phase 1 VERIFIED regressions
Pass.

### REG02 — Phase 2A PAPER regressions
Pass unchanged.

### REG03 — Phase 2B reconciliation regressions
Pass unchanged.

### REG04 — Phase 2C replay regressions
Pass.

### MIG01 — migration fresh chain
Pass.

### MIG02 — Phase 2C → Phase 3A upgrade
Pass.

### MIG03 — Phase 3A → Phase 2C downgrade
Pass with prior rows retained.

---

# 41. Data-integrity report example

```json
{
  "status": "VALID",
  "data_version_id": "dv_123",
  "instruments": {
    "NSE:EQUITY:RELIANCE:INR": {
      "bars": 252,
      "first_session": "2024-01-01",
      "last_session": "2024-12-31",
      "missing_sessions": []
    }
  },
  "corporate_actions": {
    "found": 2,
    "splits": 1,
    "cash_dividends": 1
  },
  "errors": [],
  "warnings": [],
  "report_hash": "..."
}
```

Do not return giant raw datasets in the report.

---

# 42. Manual/API validation

No new major UI is required.

At completion verify with deterministic persisted fixtures:

1. run VERIFIED BACKTEST containing a split;
2. inspect position/order state before/after split;
3. run same spec through REPLAY;
4. compare results;
5. run dividend fixture through ex-date/pay-date;
6. restart REPLAY between entitlement/payment;
7. verify one payment;
8. corrupt a test bar (duplicate/invalid OHLC);
9. confirm VERIFIED fails before trading;
10. confirm source row is not auto-modified.

---

# 43. Testing strategy

Recommended order:

```text
1. CorporateActionEngine split tests
2. dividend entitlement/payment tests
3. data-integrity validator tests
4. shared daily-kernel integration tests
5. BACKTEST/REPLAY equivalence
6. REPLAY restart tests
7. migration tests
8. Phase 1/2A/2B/2C regressions
```

Final exact-tree:

```text
pytest backend/tests/simulation/ -q
Python compile check
git diff --check
git status --short
git diff --stat
```

Run full backend suite once only after targeted/simulation tests are green and if time permits.

If the known Windows pytest temp-directory issue appears, use repository-local temporary storage and document it.

---

# 44. Non-regression contract

The following must remain true:

```text
no VERIFIED provider fallback
no synthetic VERIFIED history
no same-close lookahead
BACKTEST and REPLAY share the same daily kernel
PAPER accounting remains unchanged
Phase 2B reconciliation remains immutable
REPLAY restart safety remains intact
canonical money arithmetic remains Decimal
source historical bars remain immutable
```

---

# 45. Completion criteria

Phase 3A is complete when:

- splits correctly adjust canonical positions;
- splits correctly adjust open orders;
- splits are idempotent across retry/restart;
- cash dividends create persistent entitlement;
- cash dividends pay exactly once;
- VERIFIED dividend dates are not guessed;
- corporate actions are data-version correct;
- applied actions are audited;
- VERIFIED bar integrity checks are centralized;
- malformed market data fails before trading;
- no source row is silently repaired;
- data-quality report is deterministic;
- BACKTEST/REPLAY split/dividend equivalence passes;
- Phase 1/2A/2B/2C regressions remain green;
- migration upgrade/downgrade passes;
- no frontend redesign occurs;
- no PAPER accounting change occurs;
- no LIVE/broker work occurs.

---

# 46. Final Codex report

When complete, stop and report:

## Corporate actions

```text
split behavior
open-order adjustment behavior
dividend entitlement behavior
dividend payment behavior
restart/idempotence behavior
```

## Data integrity

Report checks implemented and hard-fail versus warning policy.

## Files

Separate created and modified files.

## Migration

Report:

```text
revision
down_revision
new tables/columns
indexes/constraints
fresh upgrade
upgrade from Phase 2C
downgrade
prior-data retention
```

## Equivalence/regression

Report exact results for:

```text
split BACKTEST/REPLAY
dividend BACKTEST/REPLAY
replay restart
Phase 1
Phase 2A
Phase 2B
Phase 2C
full simulation suite
```

## Scope confirmation

Explicitly answer:

```text
BACKTEST order timing changed? Yes/No
REPLAY timing changed? Yes/No
VERIFIED fallback changed? Yes/No
PAPER accounting changed? Yes/No
Phase 2B reconciliation semantics changed? Yes/No
source price rows modified by simulation? Yes/No
frontend changed? Yes/No
live broker introduced? Yes/No
Phase 3B started? Yes/No
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

# 47. Codex kickoff prompt

```text
begin with reading Phase_3A_Corporate_Actions_and_Market_Data_Integrity_Hardening.md in docs/architecture/.

Treat:
- OpenTerminalUI_Assessment_and_Direction.md as architectural context
- OpenTerminalUI_Simulation_Implementation_Blueprint.md as the canonical simulation foundation
- Phase 1A through Phase 1E as completed
- Phase 2A Canonical Paper Trading as completed
- Phase 2B Backtest/Paper Reconciliation as completed
- Phase 2C Historical Replay Mode as completed
- Codex_Phase_3A_Corporate_Actions_and_Market_Data_Integrity_Hardening.md as the current implementation task

Implement Phase 3A exactly as specified.

Work only on feat/simulation-core.

Plain-English objective:
Make historical BACKTEST and REPLAY more trustworthy by correctly handling stock splits/dividends and refusing to run VERIFIED simulations on broken or mismatched historical data.

Critical rules:

1. Use the shared daily session kernel.
2. Do not build separate corporate-action logic for BACKTEST and REPLAY.
3. Apply actions at the existing CORPORATE_ACTION point before BAR_OPEN.
4. Support only SPLIT and CASH_DIVIDEND in Phase 3A.
5. Splits must preserve economic cost basis.
6. Splits must adjust open orders deterministically.
7. Do not round fractional split quantities; use Decimal.
8. Corporate actions must apply at most once per run.
9. Cash dividends must create entitlement and pay exactly once.
10. VERIFIED dividend timing must not be guessed.
11. RESEARCH may use documented legacy date assumptions only with warnings.
12. VERIFIED corporate actions must match requested data version.
13. Centralize historical market-data integrity checks.
14. Reject duplicate bars, invalid OHLC, negative volume, wrong versions and missing VERIFIED coverage.
15. Do not fabricate missing bars.
16. Do not provider-fetch missing VERIFIED data.
17. Do not mutate source historical price rows.
18. Do not double-adjust source prices and account state.
19. Preserve BACKTEST/REPLAY economic equivalence.
20. Preserve Phase 1, 2A, 2B and 2C behavior.
21. Do not change PAPER accounting.
22. Do not redesign frontend.
23. Do not start Phase 3B.
24. Do not commit or push.

Inspect the actual Alembic head and current corporate-action source schema before creating a migration.
Use the next valid revision.

If accurate VERIFIED dividend handling requires nullable source fields, add them compatibly while preserving legacy rows.

Before changes, run focused existing BACKTEST/REPLAY equivalence and VERIFIED invariants.
Use targeted tests throughout.
At completion run Phase 3A tests, Phase 1/2A/2B/2C regressions, migration checks, full simulation suite, compile check and git diff --check.

Stop when all Phase 3A completion criteria pass and return the requested final report.
```

---

## End of Phase 3A specification
