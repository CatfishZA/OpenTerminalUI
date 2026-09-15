# Codex Phase 3B — Governance & Strategy Promotion

**Repository:** `CatfishZA/OpenTerminalUI`  
**Branch:** `feat/simulation-core`  
**Baseline:** Phase 3A checkpoint `c2aae69`  
**Status:** Implementation task specification  
**Primary objective:** Replace the current trust-by-button model-promotion path with an evidence-based, auditable governance layer built on canonical VERIFIED BACKTEST evidence and, for final approval, canonical PAPER + Phase 2B reconciliation evidence.

---

## 0. Plain-English goal

Phase 3B answers:

> Has this exact strategy version been tested properly enough to move forward?

```text
Research idea
    │
    ▼
VERIFIED BACKTEST
    │
    ▼
STAGING APPROVAL
(allowed to move toward paper validation)
    │
    ▼
PAPER evidence + reconciliation
    │
    ▼
PROD APPROVAL
(governance-approved strategy version)
```

Important:

```text
PROD APPROVAL ≠ live broker trading
```

Phase 3B never submits an order, creates a broker connection, or automatically starts a PAPER session.

---

## 1. Why this phase is needed

The repository already has a governance route and model registry. The current promotion endpoint accepts a `ModelRun` and directly writes a `staging` or `prod` registry entry.

It does not currently require canonical evidence such as:

```text
SimulationRun
VERIFIED status
manifest/result hashes
valid versioned data
Phase 3A data integrity
accounting reconciliation
PAPER evidence
Phase 2B reconciliation
exact strategy-version identity
```

Phase 3B hardens that path.

Existing legacy governance data remains readable. New promotions must use canonical simulation evidence.

---

## 2. Scope

Phase 3B includes exact strategy-version identity, canonical governance records, evidence evaluation, STAGING and PROD gates, immutable promotion/revocation decisions, deterministic evidence hashing, actor/reason audit trails, Phase 1 VERIFIED evidence, Phase 3A integrity evidence, Phase 2A PAPER evidence, Phase 2B reconciliation evidence, compatibility with linked legacy `ModelRun`/`BacktestRun` records, compatibility projection to the existing `model_registry`, APIs, migration, and tests.

Phase 3B does **not** implement live brokerage, auto-deployment, automatically creating PAPER sessions, automatically running strategies, profitability optimization, AI approval, enterprise two-person approval, RBAC redesign, portfolio-level governance, retraining, parameter tuning, auto-revocation due to newer datasets, frontend redesign, or Phase 3C.

---

## 3. Governance principle

Governance evaluates **evidence quality**, not whether a strategy is profitable.

Do not hardcode rules such as:

```text
Sharpe > 1
return > 20%
max drawdown < 10%
win rate > 60%
```

Default governance asks:

```text
Was this exact strategy version tested?
Was the run VERIFIED?
Was the data valid?
Is the result reproducible?
Did canonical accounting reconcile?
Is PAPER evidence from the same strategy version?
Is the BACKTEST/PAPER reconciliation valid and unambiguous?
```

Performance metrics may be displayed as evidence but are not default promotion gates.

---

## 4. Strategy version identity

The governed unit is:

```text
strategy_key + strategy_hash
```

Optional provenance:

```text
code_hash
engine_version
```

Same `strategy_key` but different `strategy_hash` means a different governed strategy version. Approval never transfers automatically across hashes.

---

## 5. Governance stages

Canonical stages:

```text
CANDIDATE
STAGING
PROD
REVOKED
```

**CANDIDATE:** strategy version exists but has not passed STAGING evidence.

**STAGING:** exact strategy version has valid canonical VERIFIED BACKTEST evidence and is approved to proceed toward PAPER validation. No PAPER session is automatically created.

**PROD:** exact strategy version has STAGING approval + canonical PAPER evidence + Phase 2B reconciliation + explicit human approval. PROD means governance-approved, not broker-live.

**REVOKED:** approval explicitly withdrawn. History remains immutable.

Valid transitions:

```text
CANDIDATE -> STAGING
STAGING   -> PROD
REVOKED   -> STAGING  (fresh evaluation)
REVOKED   -> PROD     (fresh STAGING + PROD requirements)
```

Invalid:

```text
CANDIDATE -> PROD
```

---

## 6. STAGING evidence gate

Require a canonical baseline run with:

```text
mode = BACKTEST
verification_level = VERIFIED
status = DONE
```

Required provenance:

```text
strategy_key
strategy_hash
data_version_id
engine_version
manifest hash
result hash
```

Required quality:

```text
Phase 3A data-integrity status VALID
no hard integrity errors
canonical intra-run accounting reconciliation PASS
run error empty
canonical result exists
```

Default usefulness rule:

```text
at least one canonical order or fill
```

No positive-P&L requirement.

---

## 7. Code-hash policy

`SimulationRunORM.code_hash` may be null on older/local runs.

For **STAGING**, missing code hash is a warning:

```text
CODE_HASH_MISSING
```

It does not block STAGING when strategy hash, manifest hash, result hash, engine version, and data version are valid.

For **PROD**, code hash is required by default:

```text
CODE_HASH_REQUIRED_FOR_PROD
```

Client-supplied legacy code hashes must never satisfy this requirement. Use canonical run provenance.

---

## 8. Phase 3A data-integrity evidence

STAGING evidence must include:

```text
data_version_id
integrity status
integrity report hash
error count
warning codes
corporate actions applied
legacy assumptions
```

Hard errors block STAGING.

Warnings are only blocking when policy explicitly classifies them as blocking. No RESEARCH assumption may be promoted into VERIFIED evidence.

---

## 9. Intra-run accounting evidence

Before STAGING, require canonical accounting identities to pass using the existing intra-run `ReconciliationService`:

```text
ledger cash == account cash
fill-derived positions == account positions
equity identity holds
```

Stable failure:

```text
CANONICAL_RECONCILIATION_FAILED
```

Do not substitute Phase 2B cross-run reconciliation for this check.

---

## 10. PROD evidence gate

PROD requires current stage `STAGING` plus PAPER evidence.

Required PAPER run:

```text
mode = PAPER
same strategy_key
same strategy_hash
canonical simulation run
```

The PAPER run may still be RUNNING if an immutable Phase 2B cutoff/report exists.

Required Phase 2B reconciliation:

```text
status = DONE
baseline_run_id == approved VERIFIED baseline
paper_run_id == supplied PAPER run
report_hash present
paper cutoff present
strategy identity EXACT
intent_comparable == true
accounting_comparable == true
```

Default strict alignment requirements:

```text
ambiguous matches == 0
low-confidence matches == 0
baseline-only == 0
paper-only == 0
```

Execution differences such as slippage, partial fills, latency, or commissions do not automatically block PROD unless a future/configured policy defines a material threshold.

Do not invent such thresholds in Phase 3B.

---

## 11. Minimum PAPER evidence

A PAPER reconciliation with no meaningful execution is insufficient for PROD.

Default gate:

```text
matched_orders > 0
paper fills > 0
```

Failure:

```text
PAPER_EVIDENCE_EMPTY
```

This is an evidence-quality rule, not a profitability rule.

---

## 12. Performance-comparison guard

Preserve Phase 2B honesty: ordinary historical BACKTEST and live-clock PAPER performance is not causally comparable.

Do not require:

```text
paper return close to backtest return
paper P&L > 0
```

Governance should use intent alignment, accounting validity, execution evidence, and provenance—not false P&L equivalence.

---

## 13. Human approval

Every state-changing governance action requires an authenticated user.

Promotion/revocation requires a non-empty `reason`.

Persist:

```text
actor user id
reason
decision time
from stage
to stage
policy version
evidence hash
```

No automatic promotion after successful simulations.

---

## 14. Governance policy version

Create one central policy version, e.g.:

```text
canonical-governance-v1
```

Snapshot effective values into every decision.

Suggested default policy:

```text
staging_requires_verified = true
staging_requires_valid_data = true
staging_requires_accounting_reconciliation = true
staging_allow_missing_code_hash = true
staging_allow_empty_strategy = false

prod_requires_staging = true
prod_requires_code_hash = true
prod_requires_paper = true
prod_requires_reconciliation = true
prod_requires_exact_strategy_identity = true
prod_max_ambiguous_matches = 0
prod_max_low_confidence_matches = 0
prod_max_baseline_only = 0
prod_max_paper_only = 0
prod_min_matched_orders = 1
prod_min_paper_fills = 1
```

No performance thresholds.

---

## 15. Governance evidence bundle

Create a deterministic evidence bundle containing compact provenance rather than giant artifact arrays.

Conceptual shape:

```json
{
  "strategy": {
    "strategy_key": "...",
    "strategy_hash": "...",
    "code_hash": "...",
    "engine_version": "..."
  },
  "baseline": {
    "simulation_run_id": "sim_...",
    "verification_level": "VERIFIED",
    "data_version_id": "...",
    "manifest_hash": "...",
    "result_hash": "...",
    "data_integrity_hash": "...",
    "accounting_reconciliation": "PASS"
  },
  "paper": {
    "simulation_run_id": "sim_...",
    "status": "RUNNING"
  },
  "reconciliation": {
    "id": "rec_...",
    "report_hash": "...",
    "cutoff_sequence": 123,
    "intent_comparable": true,
    "accounting_comparable": true
  },
  "policy": {
    "version": "canonical-governance-v1"
  }
}
```

STAGING evidence omits PAPER/reconciliation.

---

## 16. Evidence hash

Calculate deterministic `evidence_hash` from canonical JSON including strategy identity, baseline provenance, data-quality evidence, accounting reconciliation, PAPER/reconciliation provenance where applicable, and policy snapshot.

Exclude actor, timestamps, free-form reason, display metadata, and auto-increment IDs.

Same evidence + same policy must yield the same hash.

---

## 17. Source evidence is read-only

Governance may read canonical simulations and reconciliation reports but must not mutate:

```text
simulation run
manifest
result
result hash
reconciliation report
PAPER orders/fills
data version
strategy code
```

Governance only writes governance-owned records and compatibility registry projections.

---

## 18. Persistence — strategy governance record

Create `strategy_governance_records`.

Suggested columns:

```text
id                        string(64) PK, gov_*
strategy_key              string(160)
strategy_hash             string(128)
current_stage             string(16)
baseline_run_id           FK simulation_runs
latest_paper_run_id       FK simulation_runs nullable
latest_reconciliation_id  FK simulation_reconciliations nullable
latest_evidence_hash      string(128)
policy_version            string(64)
created_at                datetime
updated_at                datetime
revoked_at                datetime nullable
```

Constraint:

```text
UNIQUE(strategy_key, strategy_hash)
```

This is the current-state projection.

---

## 19. Persistence — immutable decisions

Create `strategy_governance_decisions`.

Suggested columns:

```text
id                    string(64) PK, gdec_*
governance_record_id  FK strategy_governance_records
decision_type         string(16)  # PROMOTE / REVOKE
from_stage            string(16)
to_stage              string(16)
baseline_run_id       FK simulation_runs
paper_run_id          FK simulation_runs nullable
reconciliation_id     FK simulation_reconciliations nullable
policy_version        string(64)
policy_snapshot_json  JSON
evidence_hash         string(128)
evidence_json         JSON
checks_json           JSON
reason                text
actor_user_id         FK users nullable on delete
request_hash          string(128)
created_at            datetime
```

Constraint:

```text
UNIQUE(request_hash)
```

Decisions are append-only.

---

## 20. Explicit check results

Evaluation returns checks such as:

```json
[
  {
    "code": "BASELINE_VERIFIED",
    "passed": true,
    "blocking": true,
    "detail": "..."
  },
  {
    "code": "CODE_HASH_PRESENT",
    "passed": false,
    "blocking": false,
    "detail": "..."
  }
]
```

Promotion is eligible only when all blocking checks pass.

---

## 21. Existing `model_registry` compatibility

Keep `model_registry` for current UI/compatibility, but do not use it as the authority for new governance decisions.

If required, add nullable fields:

```text
simulation_run_id
governance_record_id
governance_decision_id
evidence_hash
evidence_level
```

`evidence_level` values:

```text
LEGACY
CANONICAL
```

Existing rows remain readable and are considered LEGACY when no canonical governance reference exists.

New promotions create/update a compatibility registry projection with `staging`/`prod` stage plus canonical references.

---

## 22. Legacy `ModelRun` compatibility

Current governance APIs use `ModelRun`.

When supplied a legacy `ModelRun.id`, resolve:

```text
ModelRun
  -> backtest_run_id
  -> BacktestRun
  -> simulation_run_id
  -> canonical SimulationRun
```

If canonical link exists, evaluate canonical evidence.

If not:

```text
CANONICAL_EVIDENCE_REQUIRED
```

Do not fabricate canonical history.

---

## 23. Legacy metadata endpoint boundary

Keep `/governance/runs/register` for legacy compatibility if needed.

However client-written values such as:

```text
data_version_id
code_hash
execution_profile
```

must never satisfy canonical governance checks.

Canonical governance reads only canonical simulation provenance and persisted canonical reconciliation evidence.

---

## 24. Harden existing promote endpoint

Existing:

```text
POST /governance/model-registry/promote
```

must route through the new governance service.

Preserve existing request fields where practical:

```text
registry_name
run_id
stage
metadata
```

Interpret:

```text
stage=staging -> STAGING governance promotion
stage=prod    -> PROD governance promotion
```

Add optional/required canonical fields as needed:

```text
paper_run_id
reconciliation_id
reason
```

There must be no direct old insert bypass after Phase 3B.

---

## 25. Governance service

Create repository-appropriate files such as:

```text
backend/governance/domain.py
backend/governance/policy.py
backend/governance/repositories.py
backend/governance/service.py
```

Suggested service interface:

```python
class StrategyGovernanceService:
    def evaluate(...): ...
    def promote(...): ...
    def revoke(...): ...
    def get(...): ...
    def history(...): ...
```

Promotion must evaluate and persist in one transaction.

Do not trust client-side evaluation output.

---

## 26. TOCTOU protection

`promote()` must rerun evidence evaluation from canonical source data inside the promotion transaction.

Persist the evidence hash actually approved.

Never accept a client-provided evidence hash as proof.

---

## 27. Idempotency

Repeated identical promotion requests with identical strategy version, target stage, source evidence, policy, actor, and reason must not create duplicate semantic decisions.

Use deterministic `request_hash` + uniqueness.

Return existing decision when identical.

---

## 28. Revocation

Add explicit revoke support requiring authenticated actor + non-empty reason.

Revocation:

```text
does not delete strategy
does not delete source runs
does not delete evidence
does not delete history
does not trigger PAPER/LIVE actions
```

Append immutable decision and update current-state projection.

---

## 29. Re-promotion after revocation

Re-promotion must re-evaluate current canonical evidence and create a new immutable decision.

Do not reactivate old decisions.

---

## 30. Evidence freshness

Optionally verify approved source hashes when reading governance records.

Expose:

```text
evidence_current = true/false
```

If a supposedly immutable source hash changed:

```text
EVIDENCE_INTEGRITY_MISMATCH
```

Do not auto-rewrite or auto-revoke in Phase 3B.

---

## 31. Newer datasets

A newer data version does not automatically invalidate an existing approval.

Approval remains pinned to its original:

```text
data_version_id
manifest hash
result hash
```

Later validation creates new evidence/decisions.

---

## 32. Canonical APIs

Add/extend governance APIs:

```text
POST /api/governance/strategies/evaluate
POST /api/governance/strategies/promote
GET  /api/governance/strategies/{id}
GET  /api/governance/strategies/{id}/history
GET  /api/governance/strategies
POST /api/governance/strategies/{id}/revoke
```

Evaluation does not mutate state.

List endpoint supports stage, strategy_key, offset, limit.

Existing `/governance/model-registry/promote` remains as compatibility adapter.

---

## 33. Stable errors

At minimum:

```text
GOVERNANCE_RECORD_NOT_FOUND
BASELINE_RUN_NOT_FOUND
CANONICAL_EVIDENCE_REQUIRED
BASELINE_MODE_INVALID
VERIFIED_BASELINE_REQUIRED
BASELINE_NOT_DONE
RESULT_HASH_REQUIRED
MANIFEST_HASH_REQUIRED
DATA_INTEGRITY_INVALID
CANONICAL_RECONCILIATION_FAILED
STRATEGY_IDENTITY_MISMATCH
INVALID_STAGE_TRANSITION
STAGING_APPROVAL_REQUIRED
CODE_HASH_REQUIRED_FOR_PROD
PAPER_RUN_REQUIRED
PAPER_RUN_NOT_FOUND
PAPER_MODE_INVALID
PAPER_STRATEGY_MISMATCH
RECONCILIATION_REQUIRED
RECONCILIATION_NOT_FOUND
RECONCILIATION_PAIR_MISMATCH
RECONCILIATION_NOT_COMPARABLE
RECONCILIATION_AMBIGUOUS
PAPER_EVIDENCE_EMPTY
PROMOTION_REASON_REQUIRED
ALREADY_REVOKED
EVIDENCE_INTEGRITY_MISMATCH
```

---

## 34. Audit logging

Use existing audit logging for state changes.

Events:

```text
governance_strategy_promoted
governance_strategy_revoked
```

Audit payload includes record/decision IDs, strategy identity, stages, source evidence IDs, evidence hash, and policy version.

Do not duplicate huge evidence JSON in generic audit storage.

---

## 35. No execution side effects

Promotion must never:

```text
create PAPER portfolio
start PAPER session
submit order
cancel order
start REPLAY
create LIVE run
connect broker
change strategy configuration
change execution profile
change data version
```

Governance records evidence/permission only.

---

## 36. Migration

Inspect actual Alembic head first.

Expected conceptual revision:

```text
0018_strategy_governance.py
```

Use the next valid revision.

Create:

```text
strategy_governance_records
strategy_governance_decisions
```

Optionally add compatibility columns to `model_registry`.

Preserve all legacy and canonical data from Phases 1–3A.

Existing model-registry entries remain readable as legacy entries.

Downgrade removes only Phase 3B-owned schema/columns.

---

## 37. Suggested files

Create, as appropriate:

```text
backend/governance/domain.py
backend/governance/policy.py
backend/governance/repositories.py
backend/governance/service.py
backend/alembic/versions/0018_strategy_governance.py
backend/tests/test_governance_evaluation.py
backend/tests/test_governance_promotion.py
backend/tests/test_governance_prod_evidence.py
backend/tests/test_governance_revocation.py
backend/tests/test_governance_legacy_compat.py
backend/tests/test_governance_migration.py
```

Modify narrowly:

```text
backend/api/routes/governance.py
backend/models/core.py
backend/models/__init__.py
backend/api/router.py
```

Do not change DailySimulator, Replay timing, PAPER accounting, Phase 2B reconciliation semantics, or frontend.

---

## 38. Acceptance tests

Phase 3B is not complete until the following are covered:

```text
G01  valid VERIFIED baseline eligible for STAGING
G02  RESEARCH baseline blocked
G03  PAPER baseline blocked
G04  non-DONE baseline blocked
G05  missing result hash blocked
G06  missing manifest hash blocked
G07  invalid Phase 3A integrity blocked
G08  failed intra-run reconciliation blocked
G09  same key+hash resolves same governance record
G10  changed strategy hash creates different governed version
G11  STAGING persists immutable decision
G12  STAGING causes no PAPER/order side effects
G13  no-trade baseline blocked by default
G14  missing code hash is STAGING warning
G15  direct CANDIDATE->PROD blocked
G16  PROD requires code hash
G17  PROD requires canonical PAPER
G18  PAPER strategy mismatch blocked
G19  PROD requires Phase 2B reconciliation
G20  reconciliation pair mismatch blocked
G21  intent_comparable=false blocks PROD
G22  accounting_comparable=false blocks PROD
G23  ambiguous matches block PROD
G24  low-confidence matches block default PROD
G25  baseline-only blocks default PROD
G26  paper-only blocks default PROD
G27  empty PAPER evidence blocks PROD
G28  valid PAPER + reconciliation permits PROD
G29  positive PAPER P&L is NOT required
G30  PROD creates no LIVE/broker side effect
G31  evidence hash deterministic
G32  client cannot spoof evidence hash
G33  legacy editable metadata cannot satisfy canonical gate
G34  linked legacy ModelRun resolves to canonical SimulationRun
G35  unlinked legacy ModelRun blocked
G36  old model_registry rows survive migration
G37  canonical promotion creates registry compatibility projection
G38  duplicate promotion request idempotent
G39  authentication required
G40  promotion reason required
G41  revoke appends immutable decision
G42  revoke preserves evidence/history
G43  repeated revoke handled safely
G44  re-promotion re-evaluates evidence
G45  newer data version does not mutate old approval
G46  source hash mismatch is detectable
G47  promotion audit written
G48  revocation audit written
G49  Phase 1 regressions pass
G50  Phase 2A regressions pass
G51  Phase 2B regressions pass
G52  Phase 2C regressions pass
G53  Phase 3A regressions pass
G54  migration fresh/upgrade/downgrade passes
G55  frontend untouched
```

---

## 39. Controlled governance scenario

Baseline fixture:

```text
BACKTEST
VERIFIED
DONE
strategy_key = fixture:sma
strategy_hash = hash-A
code_hash = code-A
data_version_id = version-A
manifest hash present
result hash present
data integrity VALID
account reconciliation PASS
orders/fills > 0
```

Expected: STAGING eligible.

Then PAPER fixture:

```text
mode = PAPER
strategy_key = fixture:sma
strategy_hash = hash-A
```

Phase 2B reconciliation:

```text
baseline = approved VERIFIED run
paper = PAPER run
intent_comparable = true
accounting_comparable = true
matched orders > 0
ambiguous = 0
low-confidence = 0
baseline-only = 0
paper-only = 0
paper fills > 0
report hash present
```

Expected: PROD eligible.

Assert governance created no PAPER session, no order, and no LIVE run.

---

## 40. Legacy compatibility scenario

```text
ModelRun
  -> backtest_run_id = bt_123
BacktestRun
  -> run_id = bt_123
  -> simulation_run_id = sim_123
```

Compatibility promotion using ModelRun ID must resolve `sim_123` and use canonical evidence.

If `simulation_run_id` is null, fail with `CANONICAL_EVIDENCE_REQUIRED`.

---

## 41. Testing strategy

Recommended order:

```text
1. policy/evaluation unit tests
2. STAGING promotion tests
3. PROD evidence tests
4. legacy compatibility tests
5. revoke/idempotency tests
6. API tests
7. migration tests
8. prior-phase regressions
```

Final checks:

```text
pytest governance tests
pytest backend/tests/simulation/ -q
python compile check
git diff --check
git status --short
git diff --stat
```

Then run full backend suite once in rebuilt Docker:

```text
docker compose up -d --build
docker compose exec backend python -m pytest backend/tests/ -q
```

If Windows host Python is unavailable, do not treat that as an application failure.

---

## 42. Non-regression contract

After Phase 3B:

```text
VERIFIED policy unchanged
no provider fallback introduced
BACKTEST semantics unchanged
REPLAY semantics unchanged
PAPER accounting unchanged
Phase 2B reconciliation semantics unchanged
Phase 3A integrity/corporate actions unchanged
source simulations remain immutable
no frontend redesign
no live broker execution
```

---

## 43. Completion criteria

Phase 3B is complete when exact strategy versions have canonical governance records; STAGING requires trustworthy VERIFIED BACKTEST evidence; PROD requires STAGING + canonical PAPER/reconciliation evidence; promotion is not profitability-based; code provenance is required for PROD; evidence is snapshotted and hashed; decisions are immutable and idempotent; revocation is auditable; old registry rows remain readable; legacy ModelRuns cannot bypass canonical evidence; old promote endpoint routes through canonical governance; promotion causes no execution side effects; migration is safe; all prior simulation behavior remains green; full backend suite passes; no frontend work is required; Phase 3C is not started.

---

## 44. Final Codex report

When complete, stop and report:

### Governance implementation

```text
strategy identity
STAGING gate
PROD gate
policy version
evidence bundle/hash
legacy ModelRun resolution
registry compatibility projection
promotion/revocation behavior
audit behavior
```

### Files

Separate created and modified.

### Migration

```text
revision
down_revision
tables
legacy registry columns if any
indexes/constraints
fresh upgrade
Phase 3A -> 3B upgrade
downgrade
legacy registry retention
canonical simulation retention
```

### Tests

Exact commands/results for Phase 3B, Phase 1, Phase 2A, Phase 2B, Phase 2C, Phase 3A, simulation suite, full backend suite, compile, and `git diff --check`.

### Scope confirmation

```text
BACKTEST semantics changed? Yes/No
REPLAY semantics changed? Yes/No
PAPER accounting changed? Yes/No
Phase 2B reconciliation semantics changed? Yes/No
Phase 3A data integrity changed? Yes/No
automatic PAPER deployment introduced? Yes/No
live broker introduced? Yes/No
profitability thresholds introduced? Yes/No
frontend changed? Yes/No
Phase 3C started? Yes/No
```

### Git

```text
git status --short
git diff --stat
```

Do not commit or push. Wait for review.

---

# 45. Codex kickoff prompt

```text
Read all documents in docs/architecture/.

Treat:
- OpenTerminalUI_Assessment_and_Direction.md as architectural context
- OpenTerminalUI_Simulation_Implementation_Blueprint.md as the canonical simulation foundation
- Phase 1A through Phase 1E as completed
- Phase 2A Canonical Paper Trading as completed
- Phase 2B Backtest/Paper Reconciliation as completed
- Phase 2C Historical Replay as completed
- Phase 3A Corporate Actions & Market-Data Integrity Hardening as completed
- Codex_Phase_3B_Governance_and_Strategy_Promotion.md as the current implementation task

Implement Phase 3B exactly as specified.

Work only on feat/simulation-core.

Plain-English objective:
A strategy must not become staging or prod just because someone clicked promote. New promotions must be backed by canonical evidence.

Critical rules:
1. Govern exact strategy_key + strategy_hash.
2. STAGING requires canonical VERIFIED DONE BACKTEST evidence.
3. STAGING requires valid Phase 3A data-integrity evidence.
4. STAGING requires canonical intra-run accounting reconciliation.
5. Client-written legacy metadata is never canonical evidence.
6. PROD requires prior STAGING.
7. PROD requires code_hash by default.
8. PROD requires canonical PAPER evidence for the same exact strategy version.
9. PROD requires DONE Phase 2B reconciliation for the approved baseline/PAPER pair.
10. Require intent_comparable and accounting_comparable.
11. Default PROD policy blocks ambiguous, low-confidence, baseline-only and paper-only alignment.
12. Require meaningful PAPER execution evidence.
13. Do not require positive return, Sharpe, win rate, or arbitrary performance thresholds.
14. Persist immutable decisions and deterministic evidence hashes.
15. Every promotion/revocation requires authenticated actor and reason.
16. Existing model_registry rows remain readable as legacy.
17. Legacy ModelRun may resolve via BacktestRun.simulation_run_id to canonical evidence.
18. Legacy-only ModelRuns must not be promoted with fabricated canonical evidence.
19. Harden /governance/model-registry/promote to route through canonical governance.
20. No old direct-insert bypass may remain.
21. Promotion must never create PAPER sessions, submit orders, or create LIVE execution.
22. PROD is governance state only, not live deployment.
23. Preserve BACKTEST, REPLAY, PAPER, Phase 2B and Phase 3A behavior.
24. Do not redesign frontend.
25. Do not start Phase 3C.
26. Do not commit or push.

Inspect the actual Alembic head and current ModelRegistryORM/ModelRun/BacktestRun schema before migration. Use the next valid revision.

Use targeted governance tests during implementation. At completion run governance tests, all prior-phase regressions, full simulation suite, compile check, git diff --check, and one full backend suite in rebuilt Docker.

Stop when Phase 3B completion criteria pass and return the complete requested report.
```

---

## End of Phase 3B specification
