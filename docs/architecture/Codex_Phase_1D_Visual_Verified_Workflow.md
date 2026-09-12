# Codex Phase 1D — Visual VERIFIED Backtesting Workflow

**Repository:** `CatfishZA/OpenTerminalUI`  
**Working branch:** `feat/simulation-core`  
**Phase 1A checkpoint:** `2059e10 feat(simulation): add Phase 1A simulation core scaffold`  
**Phase 1B checkpoint:** `7be9c00 feat(simulation): implement Phase 1B deterministic daily engine`  
**Phase 1C checkpoint:** `6647f2a feat(simulation): integrate Phase 1C verified backtest workflow`  
**Phase:** 1D  
**Objective:** Make the deterministic VERIFIED backtesting workflow visible and usable inside the existing OpenTerminalUI Backtesting screen without redesigning the terminal, changing simulation semantics, or migrating paper trading.

---

## 1. Required reading

Before changing code, read these repository documents completely:

```text
docs/architecture/OpenTerminalUI_Assessment_and_Direction.md
docs/architecture/OpenTerminalUI_Simulation_Implementation_Blueprint.md
docs/architecture/Codex Phase 1A — Simulation Core Scaffold.md
docs/architecture/Codex_Phase_1B_Deterministic_Daily_Engine.md
docs/architecture/Codex_Phase_1C_Backtest_Integration.md
docs/architecture/Codex Phase 1D — Visual VERIFIED Backtesting Workflow.md
```

Treat the Assessment as architectural context, the Implementation Blueprint as the technical source of truth, Phase 1A/1B/1C as completed prior phases, and this document as the current implementation task.

Inspect the current `feat/simulation-core` tree and the actual `Backtesting.tsx` before making changes.

---

## 2. Branch and safety rules

Work only on `feat/simulation-core`.

Do not modify, merge into, or switch to `main`.

Do not push or merge unless explicitly instructed.

Do not start Phase 2.

Do not migrate paper trading.

Do not change deterministic simulation semantics unless a frontend/API contract bug makes a minimal compatibility change unavoidable.

---

## 3. Phase 1D objective

The existing Backtesting page must let a user clearly choose between:

```text
RESEARCH
VERIFIED
```

A VERIFIED user must be able to:

```text
select/confirm a data version
use a supported daily timeframe
configure supported deterministic execution assumptions
submit a VERIFIED run
see run progress/status
see that the result is VERIFIED
see the linked simulation run ID
see engine/data/manifest/result provenance
inspect canonical orders
inspect canonical fills
inspect canonical ledger entries
inspect canonical event sequence
```

The existing research charts, analytics, robustness, comparison tools, and workspace should continue to function.

---

## 4. Product principle

Do not build a separate “new backtester” page.

Use the existing:

```text
frontend/src/pages/Backtesting.tsx
```

The new simulator is a new execution mode within the existing terminal.

The UI should make the distinction obvious without duplicating the whole workflow.

---

## 5. Existing UI behavior to preserve

The current Backtesting page already provides:

- symbol search;
- market selection;
- capital;
- start/end dates;
- strategy selection;
- custom strategy script support;
- data timeframe selection;
- active data-version loading;
- execution-profile state;
- chart/result tabs;
- analytics;
- robustness;
- compare;
- parameter surfaces/sweeps;
- saved views;
- chart indicators.

Do not remove these capabilities.

Do not redesign unrelated panels.

---

## 6. Current integration mismatch to fix

The current page already stores:

```text
dataVersionId
executionProfile
```

but it submits data-version/execution details inside the legacy `config` object.

Phase 1C VERIFIED routing expects first-class request fields:

```text
verification_level
data_version_id
currency
timeframe
```

and supported config mappings such as:

```text
initial_cash
fee_bps
slippage_bps
position_size
```

Phase 1D must correct the frontend payload for VERIFIED mode.

Do not change Phase 1C routing semantics merely to accommodate an incorrect frontend payload.

---

## 7. Verification mode state

Add:

```ts
type VerificationMode = "RESEARCH" | "VERIFIED";
```

and page state:

```ts
const [verificationMode, setVerificationMode] = useState<VerificationMode>("RESEARCH");
```

Default must remain `RESEARCH`.

---

## 8. Verification selector UI

Add a compact, high-visibility control near the primary run configuration:

```text
Execution Mode

[ Research ] [ Verified ]

Research
Fast exploratory workflow. May use legacy/provider fallbacks.

Verified
Deterministic daily simulation using versioned persisted data,
no synthetic fallback, no market fallback.
```

Requirements:

- keyboard accessible;
- obvious selected state;
- brief explanatory copy;
- no modal required;
- switching mode must not submit anything.

---

## 9. VERIFIED visual identity

When mode is VERIFIED, display a clear `VERIFIED` badge in configuration and result areas.

When mode is RESEARCH, display `RESEARCH`.

Use neutral explanatory wording:

```text
RESEARCH = exploratory
VERIFIED = reproducible/versioned/deterministic
```

---

## 10. VERIFIED timeframe rule

Phase 1C supports VERIFIED only for `1d`.

When switching to VERIFIED:

- set `dataTimeframe` to `1d`, or block submit until it is `1d`;
- disable unsupported intraday choices;
- show: `Verified execution currently supports daily bars only.`

Switching back to RESEARCH restores normal timeframe choices.

Do not submit a VERIFIED intraday request if the UI can prevent it.

---

## 11. Date requirements

VERIFIED requires explicit `start` and `end`.

Disable Run if either is blank.

Show concise inline validation.

Do not silently fill missing VERIFIED dates from the current clock.

---

## 12. Data-version workflow

VERIFIED requires a persisted `data_version_id`.

The current page already calls `fetchActiveDataVersion()`.

Keep that behavior.

Phase 1D should preferably support selecting from available versions.

The backend currently exposes only the active version endpoint, so add a minimal read-only list endpoint if no equivalent already exists:

```text
GET /data/versions
```

Suggested response:

```json
{
  "items": [
    {
      "id": "...",
      "name": "...",
      "description": "...",
      "source": "...",
      "is_active": true,
      "created_at": "...",
      "metadata": {}
    }
  ]
}
```

Reuse `DataVersionORM`.

No migration is required.

Do not change activation semantics.

---

## 13. Data-version service helper

If needed, add:

```python
def list_data_versions(db: Session, limit: int = 100) -> list[DataVersionORM]:
    ...
```

Ordering:

```text
active first
then created_at descending
```

Keep `get_active_data_version()` unchanged unless a real bug requires a minimal correction.

---

## 14. Frontend data-version API

Add or extend frontend API functions:

```ts
fetchActiveDataVersion()
fetchDataVersions()
```

Use the shared API client.

Define a reusable type:

```ts
export type DataVersionInfo = {
  id: string;
  name: string;
  description?: string;
  source?: string;
  is_active: boolean;
  created_at?: string;
  metadata?: Record<string, unknown>;
};
```

---

## 15. Data-version selector behavior

For VERIFIED:

- show a select/dropdown;
- load available data versions;
- preselect the active version;
- display name plus source;
- visually mark active version;
- show selected version ID in provenance/detail;
- disable submit if no version exists.

For RESEARCH:

- selector may stay visible but secondary;
- no version requirement;
- preserve current behavior.

Do not create data versions from Backtesting in Phase 1D.

---

## 16. Currency behavior

The page already derives:

```text
NSE/BSE → INR
NYSE/NASDAQ/AMEX → USD
```

For VERIFIED send this as top-level `currency`.

Do not make currency manually editable in this phase.

Show it in the execution/provenance summary.

---

## 17. VERIFIED position sizing

Phase 1C rejects unsupported `position_fraction`.

The current page uses strategy `default_allocation` as `position_fraction`.

Do not send `position_fraction` in VERIFIED mode.

Add a simple VERIFIED quantity input:

```text
Order Quantity
```

Suggested state:

```ts
const [verifiedQuantity, setVerifiedQuantity] = useState(1);
```

Requirements:

- positive;
- default `1`;
- submit as `context.quantity`.

RESEARCH mode keeps existing allocation behavior.

Do not reinterpret an allocation fraction as share quantity.

---

## 18. VERIFIED commission/slippage mapping

The current UI tracks:

```text
commission_bps
slippage_model
slippage_bps
spread_bps
market_impact_bps
volume_cap_pct
```

Phase 1C VERIFIED compatibility currently supports fixed-BPS mapping through:

```text
config.fee_bps
config.slippage_bps
```

For VERIFIED:

- expose commission BPS;
- expose slippage BPS;
- label model `Fixed BPS`;
- show `WORST_CASE` bar-path policy read-only;
- show settlement `T+1` read-only;
- do not present unsupported spread/impact/volume-cap settings as active.

For RESEARCH preserve current richer execution-profile inputs.

---

## 19. VERIFIED request payload

Submit conceptually:

```ts
{
  symbol,
  asset: symbol,
  market,
  start,
  end,
  timeframe: "1d",
  strategy,
  verification_level: "VERIFIED",
  data_version_id: selectedDataVersionId,
  currency: currencyCode,
  context: {
    ...strategyContext,
    quantity: verifiedQuantity,
  },
  config: {
    initial_cash: tradeCapital,
    fee_bps: executionProfile.commission_bps,
    slippage_bps: executionProfile.slippage_bps,
  },
}
```

Do not include unsupported VERIFIED values such as:

```text
position_fraction
allow_short=true
intraday timeframe
unsupported execution-profile nesting
```

unless backend support is deliberately extended and tested.

---

## 20. RESEARCH request payload

When mode is RESEARCH:

- preserve current submission semantics;
- preserve current allocation behavior;
- preserve current richer config/execution-profile behavior;
- optionally send `verification_level: "RESEARCH"`;
- do not require `data_version_id`.

Backward compatibility is mandatory.

---

## 21. TypeScript API types

Extend `frontend/src/api/types.ts` or an appropriately scoped new type file.

`BacktestJobSubmitPayload` must include:

```ts
verification_level?: "RESEARCH" | "VERIFIED";
data_version_id?: string;
currency?: string;
```

Extend result typing for Phase 1C provenance:

```ts
verification_level?: "RESEARCH" | "VERIFIED";
simulation_run_id?: string;
data_version_id?: string;
engine_version?: string;
manifest_hash?: string;
result_hash?: string;
daily_bar_path_policy?: string;
manifest?: Record<string, unknown>;
orders?: SimulationOrder[];
fills?: SimulationFill[];
data_quality?: Record<string, unknown>;
```

Do not remove existing fields.

---

## 22. Canonical simulation API client

Create:

```text
frontend/src/api/simulation.ts
```

Export it through:

```text
frontend/src/api/client.ts
```

Implement typed functions:

```ts
fetchSimulationResult(simulationRunId)
fetchSimulationManifest(simulationRunId)
fetchSimulationOrders(simulationRunId, params?)
fetchSimulationFills(simulationRunId, params?)
fetchSimulationLedger(simulationRunId, params?)
fetchSimulationEvents(simulationRunId, params?)
fetchSimulationPortfolio(simulationRunId, params?)
fetchSimulationPositions(simulationRunId, params?)
```

Use existing endpoints:

```text
/api/v1/simulation/runs/{id}
/api/v1/simulation/runs/{id}/manifest
/api/v1/simulation/runs/{id}/orders
/api/v1/simulation/runs/{id}/fills
/api/v1/simulation/runs/{id}/ledger
/api/v1/simulation/runs/{id}/events
/api/v1/simulation/runs/{id}/portfolio
/api/v1/simulation/runs/{id}/positions
```

---

## 23. Simulation collection types

Create:

```ts
type SimulationCollection<T> = {
  run_id: string;
  items: T[];
  count: number;
};
```

Define typed records for:

```text
SimulationOrder
SimulationFill
SimulationLedgerEntry
SimulationEvent
SimulationPortfolioSnapshot
SimulationPositionSnapshot
SimulationManifest
```

Avoid untyped `Record<string, unknown>` for known artifact fields.

---

## 24. Provenance panel

Create a reusable component, suggested:

```text
frontend/src/components/backtesting/RunProvenancePanel.tsx
```

For VERIFIED show:

```text
Verification        VERIFIED
Legacy Run          bt_...
Simulation Run      sim_...
Data Version        ...
Engine              ...
Manifest Hash       ...
Result Hash         ...
Bar Path Policy     WORST_CASE
Currency            ...
Settlement          T+1
Commission          ... bps
Slippage            ... bps
```

Hashes may be visually abbreviated, but full values must remain accessible.

Do not hide the simulation run ID.

---

## 25. RESEARCH provenance

For RESEARCH show a smaller block:

```text
Verification        RESEARCH
Engine              Legacy research engine
Run                 bt_...
```

Do not invent a simulation run ID, manifest hash, or result hash.

---

## 26. Result verification badge

After completion, derive displayed verification from the returned result rather than the currently selected toggle.

Prefer:

```text
result.result.verification_level
```

when present.

Do not relabel an old result if the form controls change after completion.

---

## 27. Execution artifacts panel

Create a reusable component, suggested:

```text
frontend/src/components/backtesting/ExecutionArtifactsPanel.tsx
```

Tabs:

```text
Orders
Fills
Ledger
Events
```

Optional if straightforward:

```text
Portfolio
Positions
```

Keep this separate from the existing analytics VizTab system if that reduces risk.

---

## 28. Orders table

Show:

```text
Order ID
Instrument
Side
Type
Quantity
Remaining
TIF
Status
Submitted
Accepted
Completed
Limit
Stop
```

Requirements:

- local horizontal overflow;
- full IDs accessible;
- clear state styling;
- explicit empty state.

---

## 29. Fills table

Show:

```text
Fill ID
Order ID
Instrument
Side
Quantity
Price
Commission
Fees
Slippage BPS
Execution Model
Executed At
```

Use canonical fill data.

Do not recompute fills from legacy trades.

---

## 30. Ledger table

Show:

```text
Time
Type
Currency
Amount
Instrument
Order ID
Fill ID
```

Distinguish inflow/outflow without relying on color alone.

Do not collapse canonical ledger entries into synthetic P&L rows.

---

## 31. Event timeline

Show events ordered by sequence.

Useful fields:

```text
Sequence
Event Time
Event Type
Instrument
Order ID
Fill ID
Payload summary
```

Default limit around 100.

Support Load More/pagination when needed.

Do not fetch thousands of events at page load.

---

## 32. Artifact loading behavior

Fetch canonical artifacts only when:

```text
result done
AND verification_level == VERIFIED
AND simulation_run_id exists
```

Do not call simulation artifact endpoints for RESEARCH runs.

Lazy-load tabs if practical.

Cache loaded tab results in page/component state.

---

## 33. Artifact error behavior

If one artifact endpoint fails:

- keep main result visible;
- show error only inside that artifact panel;
- provide retry;
- do not relabel the run as failed.

Do not swallow errors silently.

---

## 34. Progress/status UI

Add a compact run-status area:

```text
Queued
Running
Done
Failed
```

If API progress exists, show it.

If exact progress is unavailable:

- use stage/indeterminate presentation;
- do not fabricate a precise percentage.

For VERIFIED, only show detailed stage names if the backend actually exposes them.

---

## 35. WebSocket progress

Backend already broadcasts `backtest_progress` events.

If an existing frontend websocket utility can consume them cleanly, use it.

Do not create a second websocket stack only for Backtesting.

If websocket integration materially expands scope, retain polling.

---

## 36. Failure presentation

Preserve stable VERIFIED codes such as:

```text
DATA_VERSION_REQUIRED
DATA_VERSION_NOT_FOUND
INSTRUMENT_DATA_NOT_FOUND
VERIFIED_DATA_MISSING
UNSUPPORTED_VERIFIED_TIMEFRAME
UNSUPPORTED_VERIFIED_CONFIG
UNSUPPORTED_VERIFIED_VENUE
```

Show code plus concise explanation.

Do not replace everything with only `Backtest failed`.

---

## 37. Data-quality presentation

For VERIFIED show returned canonical `data_quality`.

Do not invent a passed state.

If backend says `VALID`, display it.

---

## 38. Run IDs

For VERIFIED keep both visible:

```text
Backtest run:   bt_...
Simulation run: sim_...
```

The user-facing workflow uses `bt_*`.

Canonical evidence APIs use `sim_*`.

---

## 39. Saved-view integration

Where the existing saved-view contract supports arbitrary filters, persist:

```text
verificationMode
dataVersionId
verifiedQuantity
```

Do not persist run IDs, hashes, or artifact rows.

If saved-view changes become unexpectedly invasive, document and defer them rather than destabilizing Phase 1D.

---

## 40. Existing chart/results behavior

Existing tabs must continue to work:

```text
Price Chart
Equity Curve
Drawdown
Monthly Returns
Rolling Metrics
Metrics
Trade Analysis
Compare
3D Surface
Robustness
Param Sweep
```

For VERIFIED, use the Phase 1C adapted result.

Do not rewrite those panels unless a concrete compatibility bug appears.

---

## 41. Compare behavior

Do not add VERIFIED compare semantics.

Compare remains research/legacy for now.

If needed in VERIFIED mode, display:

```text
Strategy comparison currently uses the research engine.
```

Do not imply compared runs are VERIFIED.

---

## 42. Robustness and analytics

Phase 1C made these compatible with VERIFIED results.

Keep them working.

Do not change statistical implementation.

---

## 43. Parameter sweep

Parameter sweep remains exploratory research.

In VERIFIED mode, if necessary show:

```text
Parameter sweep is exploratory. Final candidates should be rerun as VERIFIED.
```

Do not implement candidate promotion yet.

---

## 44. Custom strategy behavior

Do not break custom strategy script support.

If VERIFIED custom strategies are not reliably supported by the current adapter, disable VERIFIED custom submission with a clear message rather than falling back silently.

Inspect actual current adapter behavior before deciding.

---

## 45. Minimal backend additions allowed

Phase 1D is frontend-focused.

Allowed backend additions are only additive/read-only support required by UI, such as:

```text
GET /data/versions
```

or exposing an already-existing status/provenance field.

Do not change:

```text
matching
accounting
settlement
fill semantics
event ordering
simulation timing
legacy/verified routing
```

without stopping and reporting a blocking defect.

---

## 46. No migration expected

Phase 1D should not require a migration.

If a migration seems necessary, stop and explain why before implementing it.

---

## 47. No paper-trading changes

Do not modify paper-trading backend or frontend.

Paper unification is later.

---

## 48. No governance changes

Do not modify model promotion/governance.

Provenance display is allowed; governance wiring is not.

---

## 49. No engine changes

Do not alter Phase 1B financial semantics for visual convenience.

Adapt UI or read-only serialization instead.

---

## 50. Suggested frontend files

Likely additions:

```text
frontend/src/api/simulation.ts

frontend/src/components/backtesting/VerificationModeControl.tsx
frontend/src/components/backtesting/RunProvenancePanel.tsx
frontend/src/components/backtesting/ExecutionArtifactsPanel.tsx

frontend/src/components/backtesting/artifacts/OrdersTable.tsx
frontend/src/components/backtesting/artifacts/FillsTable.tsx
frontend/src/components/backtesting/artifacts/LedgerTable.tsx
frontend/src/components/backtesting/artifacts/EventTimeline.tsx
```

Follow repository conventions and avoid unnecessary fragmentation.

---

## 51. Backtesting.tsx scope control

`Backtesting.tsx` is already large.

Keep its changes focused on:

```text
mode state
data-version state
verified quantity
payload construction
completed-result provenance
artifact panel mounting
validation/status
```

Move detailed artifact rendering into components.

---

## 52. Accessibility

New controls must:

- use semantic native controls;
- have visible labels;
- work by keyboard;
- expose selected state;
- have focus styles;
- not rely on color alone;
- use semantic table headers;
- avoid page-level horizontal overflow.

Artifact tables may scroll locally.

---

## 53. Responsive behavior

On narrow layouts:

```text
mode controls wrap
provenance stacks
artifact tabs remain tappable
tables scroll locally
```

Do not introduce fixed page widths.

---

## 54. Frontend test strategy

Use Vitest + Testing Library consistent with the repository.

Test user-visible behavior and outgoing payloads.

Do not rely only on snapshots.

---

## 55. AT-D01 — RESEARCH remains default

Render Backtesting.

Expected:

```text
RESEARCH selected
VERIFIED not selected
existing Run workflow available
```

---

## 56. AT-D02 — VERIFIED selector

Select VERIFIED.

Expected:

- VERIFIED selected;
- helper text visible;
- daily-only rule visible;
- data-version UI visible;
- quantity visible.

---

## 57. AT-D03 — VERIFIED daily-only

Start with an intraday timeframe in RESEARCH, switch to VERIFIED.

Expected:

```text
timeframe becomes 1d or submit is blocked until 1d
unsupported intraday choices disabled
```

No VERIFIED intraday request sent.

---

## 58. AT-D04 — VERIFIED requires data version

Mock no available version.

Expected:

```text
Run disabled
clear data-version-required message
```

No request.

---

## 59. AT-D05 — Data-version selection

Mock multiple versions.

Expected:

- active version preselected;
- another version selectable;
- selected ID submitted;
- active version identified.

---

## 60. AT-D06 — VERIFIED payload correctness

Assert request contains:

```text
verification_level = VERIFIED
data_version_id
currency
timeframe = 1d
context.quantity
config.initial_cash
config.fee_bps
config.slippage_bps
```

Assert unsupported VERIFIED `position_fraction` is absent.

---

## 61. AT-D07 — RESEARCH payload compatibility

Submit RESEARCH.

Existing payload semantics remain compatible.

No VERIFIED-only requirement blocks it.

---

## 62. AT-D08 — VERIFIED provenance

Mock completed VERIFIED result.

Expected visible:

```text
VERIFIED
bt_* ID
sim_* ID
data version
engine version
manifest hash
result hash
bar path policy
```

---

## 63. AT-D09 — RESEARCH provenance

Mock RESEARCH result.

Expected:

```text
RESEARCH
bt_* ID
legacy/research engine label
```

No fabricated sim ID/hashes.

---

## 64. AT-D10 — Canonical artifacts only for VERIFIED

VERIFIED with `simulation_run_id` → artifact calls use `sim_*`.

RESEARCH → no simulation artifact calls.

---

## 65. AT-D11 — Orders table

Mock canonical orders.

Verify key fields and statuses render.

---

## 66. AT-D12 — Fills table

Mock fills.

Verify quantity, price, commission, slippage, model, time.

---

## 67. AT-D13 — Ledger table

Mock ledger.

Verify canonical entries render without recomputing accounting.

---

## 68. AT-D14 — Event ordering

Verify events display ascending by canonical sequence.

---

## 69. AT-D15 — Artifact error isolation

Make ledger API fail while main result succeeds.

Expected:

- main result remains;
- ledger panel error/retry;
- run not relabeled failed.

---

## 70. AT-D16 — VERIFIED error clarity

Mock `VERIFIED_DATA_MISSING`.

UI preserves code and gives concise explanation.

---

## 71. AT-D17 — Status/progress

Mock queued → running → done.

Expected status updates and final result appears.

No fabricated exact percentage when unavailable.

---

## 72. AT-D18 — Existing RESEARCH analytics regression

Existing chart/equity/metrics/trade panels still render for RESEARCH.

---

## 73. AT-D19 — VERIFIED analytics regression

Phase 1C-compatible VERIFIED result does not crash existing result panels or analytics/robustness integrations.

---

## 74. AT-D20 — Data-version list endpoint

If added, backend test verifies:

- authenticated request succeeds;
- active version included;
- deterministic ordering;
- read-only behavior;
- existing active-version endpoint unchanged.

---

## 75. AT-D21 — Scope diff check

Confirm no paper-trading, governance, or simulation-engine semantic files changed beyond explicitly allowed read-only/API serialization work.

---

## 76. API client test coverage

Where repository patterns support it, test URL construction for:

```text
manifest
orders
fills
ledger
events
data versions
```

---

## 77. Optional Playwright smoke

If straightforward with existing fixtures, add one small smoke test:

```text
Backtesting loads
RESEARCH/VERIFIED selector visible
switch VERIFIED shows data-version/quantity controls
```

Do not create a large e2e suite.

---

## 78. Test cadence

During development, run targeted frontend tests only.

Examples:

```bash
npm test -- VerificationModeControl
npm test -- RunProvenancePanel
npm test -- ExecutionArtifactsPanel
npm test -- Backtesting
```

Use actual repository-supported Vitest filtering syntax.

For backend data-version endpoint changes, run only targeted backend tests.

Do not repeatedly run the full backend suite.

---

## 79. End-of-phase verification

At completion run:

```text
1. targeted Phase 1D frontend tests
2. full frontend Vitest suite once
3. frontend production build once
4. targeted backend tests for any backend endpoint changed
5. small existing simulation/backtest integration smoke subset
6. TypeScript compile via normal build
7. git diff --check
8. git status --short
```

Do not run the full backend suite unless backend changes exceed the permitted small read-only/API scope.

---

## 80. Manual browser verification

Run the local application and manually verify:

```text
RESEARCH mode
VERIFIED mode
daily-only state
data-version selector
quantity
commission/slippage
submit
queued/running/done/failed
verified provenance
orders
fills
ledger
events
research regression
```

If persisted VERIFIED data is unavailable locally, use existing repository test/seed mechanisms.

Do not use synthetic production data merely to populate the UI.

---

## 81. Screenshot evidence

If the repository already has a screenshot workflow, capture the updated Backtesting page after stability.

Do not replace the whole README gallery unless instructed.

---

## 82. No new dependency unless necessary

Do not add a frontend package for tabs, tables, badges, formatting, or progress.

Use existing React/Tailwind/components.

`package-lock.json` should not change unless `package.json` intentionally changes.

---

## 83. Resilience

New artifact components must tolerate:

```text
missing optional fields
empty arrays
null timestamps
large IDs
zero values
partial backend responses
```

Never render `undefined`, `NaN`, or `Infinity`.

Use `—` where appropriate.

---

## 84. Performance

Do not fetch all artifact collections before needed if lazy loading is easy.

Default collection limit:

```text
100
```

Use pagination/load-more instead of unbounded rendering.

---

## 85. Security/data boundary

Do not expose secrets, server paths, DB connection details, or strategy sandbox internals.

Showing run IDs, hashes, version IDs, orders, fills, ledger, and events is expected.

---

## 86. Deliverables

When complete report:

1. Summary of visual workflow.
2. Files created.
3. Files modified.
4. Minimal backend endpoint added, if any.
5. Verification-mode behavior.
6. Data-version behavior.
7. VERIFIED payload shape.
8. RESEARCH compatibility.
9. Provenance UI.
10. Artifact UI.
11. Progress/error handling.
12. Tests added.
13. Targeted frontend results.
14. Full frontend suite result.
15. Production build result.
16. Targeted backend results if backend changed.
17. Manual browser verification.
18. Screenshot captured, if any.
19. Known limitations.
20. Confirmation deterministic engine semantics unchanged.
21. Confirmation paper trading unchanged.
22. Confirmation governance unchanged.
23. Confirmation Phase 2 not started.
24. Recommended next phase.

Do not commit or push unless explicitly instructed.

---

## 87. Completion criteria

Phase 1D is complete only when AT-D01 through AT-D21 pass and:

- RESEARCH remains default;
- existing RESEARCH submission still works;
- VERIFIED is visibly selectable;
- VERIFIED only permits supported daily workflow;
- data version is required and visible/selectable;
- verified quantity is explicit;
- VERIFIED payload matches Phase 1C;
- completed VERIFIED result shows canonical provenance;
- orders/fills/ledger/events are inspectable using `sim_*`;
- artifact failures do not destroy the main result;
- stable backend error codes remain visible;
- existing analytics/chart panels still work;
- frontend tests pass;
- production build passes;
- no simulation execution/accounting semantics changed;
- no paper migration occurred.

---

## 88. Stop condition

When Phase 1D criteria pass:

**STOP.**

Do not begin:

- paper-trading migration;
- historical replay UI;
- model-governance promotion;
- optimizer-to-VERIFIED promotion workflow;
- intraday simulation;
- options/futures work;
- Phase 2.

Report completion and wait for the next instruction.
