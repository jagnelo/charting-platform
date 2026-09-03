# ETF Holdings Constituents — Approved Implementation Plan

## 1. Purpose and authority

This is the exhaustive, durable implementation plan for branch
`feat/etf-holdings-constituents`. It records the plan approved by the human on
2026-09-02 so a later Codex implementation session can resume without relying on
conversation history.

Implementation must occur only in the registered worktree:

`/Users/jagnelo/Documents/Projects/charting-platform/.ai/worktrees/feat-etf-holdings-constituents`

This document authorizes implementation direction, not closure. The branch must
stop at `ready_for_human_review`. It must not integrate into `staging` or
`master`, promote, deploy, delete worktrees, mutate another worktree, or clean
resources outside its repository-scoped workflow ownership.

Governing sources, in precedence order:

1. latest unambiguous human instruction;
2. automatically discovered `AGENTS.md`;
3. `docs/agent-orchestration.md`;
4. branch-owned schema-4 `plan.yaml`;
5. this implementation plan;
6. current code, tests, provider ledger, handoff, and validation evidence.

If sources disagree, preserve the stricter safety/evidence boundary and update
durable records in the same coherent checkpoint as the decision.

## 2. Authoritative starting baseline

### 2.1 Git and workflow

- Branch: `feat/etf-holdings-constituents`
- Parent role: `staging`
- Original staging base: `89bb5c05ad1635156285d392b7c39b3c341ad8f1`
- Latest staging merge commit: `9bc42091ac3d95bcc11ad8783692fb3cd8f9d2e4`
- Staging SHA incorporated by that merge: `8b885a2ffd9cbb8b20c626e2c0381d3fce5cdc35`
- Earlier fully represented branch checkpoint: `a8d618995fbd928c66117271bb7ac9152a935ab5`
- Validation tier: `full_integration`
- Required local profile: `docker_integration`
- Goal budget: unbounded unless the human later authorizes an exact positive
  budget; no budget is currently authorized.
- Human closure authorization: pending.

### 2.2 Provider state

Current code is authoritative. Derive these values again at each checkpoint;
never maintain them as an independent implementation constant.

| Classification | Count |
|---|---:|
| Registered issuer adapter configurations | 496 |
| Native/live-backed providers | 381 |
| Audited fallback-only providers | 115 |
| Native plus fallback | 496 |

The current 115 fallback audits divide into:

| Audit status | Count |
|---|---:|
| `issuer_access_blocked` | 8 |
| `needs_first_party_route_discovery` | 98 |
| `non_executable_public_source` | 3 |
| `provider_not_a_portfolio_publisher` | 6 |

The approved plan began from a 356-native/140-fallback baseline. The current
checkpoint has reconciled `docs/etf-provider-universe.md` and the branch-owned
ledger to 381 native and 115 fallback providers; code-derived counts remain the
authoritative truth and must be re-derived at every subsequent checkpoint.

### 2.3 Historical continuity

This is continuation work, not a rebuild:

| Checkpoint | Registered | Native | Fallback |
|---|---:|---:|---:|
| Initial July continuation context | 345 | 288 | 57 |
| Expanded named-issuer reconciliation | 496 | 332 | 164 |
| Prior checkpoint `a8d6189` | 496 | 339 | 157 |
| Approved-plan baseline | 496 | 356 | 140 |

Relative to `a8d6189`, current code includes native promotions for `academy`,
`acsi_funds`, `alerian`, `altshares`, `calvert`, `fairlead`, `impact_shares`,
`keating`, `leverage_shares`, `oakmark`, `oshares`, `range`, `redwood`, `rex`,
`sofi`, `sterling_fund`, `thrivent`, and `truth_social`.

`anfield` moved in the opposite direction after its issuer route returned 404;
it is deliberately fallback-only. Do not restore native status merely to match
an older count.

### 2.4 Validation already known and still required

Last known deterministic evidence at the current provider implementation:

- complete adapter unit module: 501 passed;
- default/non-opt-in live module: 2 passed, 404 skipped;
- Ruff over the adapter and ETF tests: passed.

Those are historical context and must not be presented as validation of a future
implementation SHA. The complete opt-in live matrix has not been rerun at the
356-native baseline. Older evidence at 339 native was 346 passed and 1 skipped;
that also is not current proof.

## 3. Non-negotiable correctness contracts

### 3.1 Native means a real provider-owned route

A provider can leave `FALLBACK_ISSUER_AUDITS` and count as native only when:

1. A complete holdings source is controlled by the issuer, fund sponsor, or an
   explicitly entitled first-party service.
2. The application can execute it under a documented public, free, or
   already-entitled access model.
3. It returns complete portfolio constituents, not prices, a factsheet, top-ten
   holdings, fund metadata, a different index, or SEC filing data.
4. The adapter owns a concrete `fetch_latest` entry point; registry-only
   aliasing to generic fallback is not native.
5. Symbol mapping is strict enough that the route cannot silently return the
   wrong fund.
6. Parsing handles the provider's actual schema, preamble, encoding, file type,
   date fields, cash/derivative rows, identifiers, and weight conventions.
7. Source provenance and as-of/freshness fields state what was truly supplied.
8. Empty, partial, stale, unauthorized, blocked, mismatched, or malformed
   responses fail explicitly or use a documented truthful fallback policy.
9. Deterministic fixtures test the provider-specific route and parser.
10. Concrete opt-in live coverage includes the adapter key in the exhaustive
    live-backed-provider matrix.
11. Current bounded live evidence proves the route executes, unless a genuine
    external outage is separately and narrowly evidenced after deterministic
    correctness is proved.

SEC-derived holdings must always remain labelled SEC-derived. Successful SEC
fallback is not native issuer coverage.

### 3.2 Fallback is an evidence-backed disposition

Every remaining fallback must record:

- adapter key and display name;
- controlled audit status;
- last attempted UTC date;
- first-party domains and routes examined;
- representative US ETF symbols/products;
- exact access/result category;
- why the source is incomplete, blocked, non-executable, irrelevant, inactive,
  or still undiscovered;
- whether an entitlement would change the result;
- next concrete action or terminal disposition;
- safe source references, never credentials, cookies, or sensitive payloads.

"Needs discovery" is a queue state, not an acceptable final conclusion after
the exhaustive pass.

### 3.3 Set and matrix invariants

At every coherent checkpoint:

```text
registered == native + fallback
native intersection fallback == empty
native union fallback == registered
every native key has provider-owned fetch behavior
every native key has deterministic route/parser tests
every native key has concrete live-test coverage
every fallback key has exactly one current ledger record
no ledger key exists outside the registered universe
```

Tests, not prose, must enforce these relationships.

## 4. Required AI-driven development lifecycle

### 4.1 Resume and preflight

Every implementation model must:

1. Enter only the exact ETF worktree.
2. Read `AGENTS.md`, `docs/agent-orchestration.md`, `plan.yaml`, this document,
   `handoff.md`, `session.json`, and `validation.jsonl` completely.
3. Run `make agent-context` and confirm the implementation role, exact branch,
   and exact assigned `.ai/worktrees/...` path.
4. Inspect status, local HEAD, remote feature HEAD, session, and writer claim.
5. Resume the supported session or start the repository-prescribed next session
   while preserving prior session IDs.
6. Do not install, switch, merge, rebase, reset, clean, or touch another
   worktree as a preflight shortcut.

### 4.2 Goal handling

Create or resume exactly one session-local Codex goal from the objective emitted
by `make agent-session-plan-ready`. Omit `token_budget` unless a later human
instruction records an exact authorization. Record the goal active through the
repository workflow.

Goals are execution aids; committed workstream state is durable truth. Do not
mark the goal complete before AC1–AC8 are complete. Do not mark it blocked just
because provider research is slow or one route is unavailable.

### 4.3 Changeset discipline

Use bounded, named changesets. Each provider or coherent provider-family
changeset should contain:

1. documented research/disposition;
2. adapter/config/audit changes;
3. deterministic fixtures and tests;
4. live-test registration and bounded probe evidence;
5. ledger and provider-universe updates;
6. current count/matrix evidence;
7. handoff/session/validation updates.

Before moving on:

- run focused provider tests and exhaustive invariants;
- run Ruff over touched Python files;
- inspect the diff for secrets, broad formatting, unrelated edits, stale counts,
  and unsupported claims;
- commit a coherent implementation context;
- push only the reviewed exact range to the feature branch;
- record a separate operations checkpoint commit/push when workflow commands
  update durable session state.

Never retry a rejected push indirectly. Record the exact SHA/range and transport
hold if egress rejects it.

### 4.4 Human-in-the-loop pause conditions

Request direction before:

- buying or requesting a new subscription, credential, account, browser login,
  or material entitlement;
- interpreting unclear licensing/automated-access terms in a way that changes
  product behavior;
- expanding the provider universe materially beyond the current 496;
- changing a public product contract or schema outside owned ETF paths;
- integrating, promoting, deploying, deleting branches/worktrees, or modifying
  another worktree;
- making a product decision that evidence alone cannot resolve.

An ordinary issuer-route failure is not a workstream blocker. Classify it
precisely and continue down the queue.

## 5. Phase A — repair durable state before provider changes

### A1. Re-derive registry truth

Use a read-only import/query against the adapter module to derive registered,
native, fallback, and status sets, plus missing/extra/intersection sets. Also
derive native keys lacking owned `fetch_latest`, deterministic coverage, or
concrete live-test coverage. Record the command and summary in
`validation.jsonl`; do not hard-code 356/140 into implementation logic.

### A2. Reconcile documentation

Update `docs/etf-provider-universe.md` from derived state: correct current
counts/statuses/names, native definition, and SHA-specific opt-in live evidence.
Keep historical counts only when explicitly dated and labelled historical.

### A3. Repair ownership and handoff

Keep feature operations metadata inside
`ops/workstreams/feat-etf-holdings-constituents/`. Do not claim global
`ops/state.json` or `ops/handoff.md`. Handoff must name exact SHA, evidence, and
next bounded changeset.

### A4. Exit gate

AC1 completes only after counts are derived and consistent, stale current-state
prose is reconciled, workstream validation passes, the durable-state checkpoint
contains no provider implementation, and local/remote SHAs match.

## 6. Phase B — exhaustive provider audit ledger

Create `ops/workstreams/feat-etf-holdings-constituents/provider-audit.yaml`.

### B1. Top-level contract

```yaml
schema: 1
branch: feat/etf-holdings-constituents
baseline_sha: <exact SHA>
baseline_registered_count: 496
baseline_native_count: 356
baseline_fallback_count: 140
ranking_method: <stable documented rule>
generated_at: <UTC timestamp>
providers: [...]
```

### B2. Provider record contract

```yaml
- adapter_key: example
  display_name: Example
  starting_status: needs_first_party_route_discovery
  current_status: queued
  queue_rank: 1
  representative_symbols: []
  estimated_us_etf_count: null
  estimated_us_etf_aum: null
  us_equity_breadth: null
  estimate_sources: []
  first_party_domains: []
  candidate_routes: []
  source_format: null
  access_model: public
  credential_required: false
  route_complete: false
  symbol_mapping_proven: false
  current_holdings_proven: false
  parser_fixture: null
  live_test: null
  attempt_history: []
  disposition: needs_first_party_route_discovery
  disposition_reason: <issuer-specific text>
  next_action: <one concrete action>
  implementation_sha: null
  validation_refs: []
```

Attempt history records UTC timestamp, route/domain, method, HTTP/result
category, lesson, and non-sensitive evidence reference.

### B3. Deterministic prioritization

Rank lexicographically by:

1. estimated US-listed ETF count, descending;
2. estimated ETF AUM, descending;
3. US-equity holdings breadth, descending;
4. expected source freshness/daily availability, descending;
5. adapter key ascending as stable tie-break.

Unknown values sort after known values at each dimension. Store evidence date
and source. Better evidence may re-rank the queue, but the calculation must stay
deterministic and committed.

### B4. Controlled statuses

- `queued`
- `in_research`
- `native_candidate`
- `native_promoted`
- `issuer_access_blocked`
- `non_executable_public_source`
- `provider_not_a_portfolio_publisher`
- `inactive_or_successor_disposition`
- `needs_first_party_route_discovery` (temporary only)
- `human_decision_required`

Do not invent a terminal status merely to reduce the open count.

### B5. Ledger invariants

Add deterministic validation proving all starting fallback keys appear once;
current fallbacks have non-promoted entries; promoted keys remain historically
recorded; active queue ranks are unique/contiguous; dates are ISO-8601; terminal
records have specific evidence; counts reconcile to code; and no secret-looking
fields or values are stored.

## 7. Phase C — normalize in-code fallback audits

Preserve `IssuerFallbackAudit` unless a small backward-compatible extension is
proved necessary. Normalize every `FALLBACK_ISSUER_AUDITS` item so status is
controlled, `last_checked` is real, reason names actual route/result evidence,
and access blocking is distinguished from 404, incomplete data, non-publisher,
staleness, and missing mapping. Never generalize one dead route into proof that
no source exists. Keep detailed attempt history in the ledger and concise
product-facing disposition in runtime code.

Phase C is complete only when no final fallback retains a generic untouched
discovery note.

## 8. Phase D — provider investigation loop

For each ranked provider:

1. Confirm issuer identity, current brand/successor, relevant US ETFs, and
   representative symbols. Distinguish issuer, adviser, sub-adviser, white-label
   platform, index owner, private-equity manager, and unrelated names.
2. Inspect legitimate first-party fund pages, network requests, holdings
   downloads, CSV/XLS/XLSX/JSON/XML endpoints, official APIs, embedded fund IDs,
   data centers, and already-entitled configured sources.
3. Never use a third-party aggregator as provider-owned proof, circumvent access
   controls, or store credentials/cookies.
4. Prove the response is full holdings for the requested fund, current enough,
   identifiable, and interpretable for weights, cash, derivatives, short rows,
   and multiple representative products.
5. Prove stable reproduction without private transient browser state, or an
   allowed deterministic session-init flow.
6. Select a precise status. A complete executable source becomes
   `native_candidate`; blocks, incompleteness, non-publisher relationships, and
   successor states retain specific evidence. If still unknown after bounded
   research, record a narrow next action and continue elsewhere.

## 9. Phase E — native implementation contract

### E1. Adapter construction

Implement the smallest truthful provider-specific adapter. Reuse shared request
or parsing primitives only when the provider contract truly matches. Define or
explicitly inherit provider-specific route construction, method/headers/body,
timeouts/retries, symbol mapping, response detection, parsing, normalized
fields, as-of extraction, provenance, freshness, and explicit failures.

### E2. Parsing cases

Cover applicable BOM/encoding, delimiter/quoting, spreadsheet sheets/preambles,
JSON wrappers/pagination, percent versus decimal weights, locale numbers,
missing identifiers, duplicates/share classes, shorts, cash, derivatives,
totals/footers, absent/stale dates, HTML errors with HTTP 200, wrong-fund
responses, and empty/partial portfolios.

Do not loosen global parsing for one malformed provider unless safety for every
existing consumer is regression tested.

### E3. Registry transition order

After adapter and deterministic tests exist:

1. wire the concrete adapter into `ISSUER_ADAPTER_CONFIGS`;
2. set native/live-backed flags truthfully;
3. remove the key from `FALLBACK_ISSUER_AUDITS`;
4. mark the ledger record promoted;
5. add concrete live coverage;
6. derive and verify the simple expected delta: native +1, fallback -1,
   registered unchanged;
7. regenerate/reconcile documentation.

Unexpected deltas require investigation before commit.

### E4. Minimum deterministic tests

For every promotion test route/request construction, known mapping, unknown
symbol behavior, realistic fixture parsing, source/as-of/freshness metadata,
malformed/empty/partial behavior, relevant HTTP/access failures, no false native
classification through SEC fallback, and exhaustive registry ownership.

Use small sanitized fixtures in established conventions. Never commit private
or unbounded source downloads.

### E5. Minimum live tests

Add the key to concrete coverage in
`backend/tests/live/test_etf_holdings_live_providers.py`. Probe representative
symbols, plausible nonempty full portfolios, requested-provider provenance,
plausible date, challenge/error payload detection, bounded request volume, and
diagnostics separating route drift from parser failure. Network probes stay
opt-in behind `RUN_LIVE_ETF_HOLDINGS_TESTS=1`.

A mock never replaces the live probe; a live probe never replaces deterministic
parser tests.

## 10. Starting fallback population

Seed the ledger from these 140 baseline keys. Re-derive and diff before commit;
if code changed, record the delta rather than silently copying this snapshot.

### 10.1 `issuer_access_blocked` — 8

- `aegon`
- `anfield`
- `guinness_atkinson`
- `manulife`
- `q3`
- `ridgeline`
- `westwood`
- `wisdomtree`

### 10.2 `non_executable_public_source` — 3

- `epwa`
- `pacific_investments`
- `planrock`

### 10.3 `provider_not_a_portfolio_publisher` — 6

- `epiris`
- `eurazeo`
- `marathon`
- `msc_group`
- `orix`
- `rock_point`

### 10.4 `needs_first_party_route_discovery` — 123

- `advisors_asset_management`
- `alphaclone`
- `alphamark_advisors`
- `amg_national`
- `amplius`
- `anydrus`
- `argent`
- `arin`
- `ars`
- `avory`
- `avos`
- `azimut`
- `baillie_gifford`
- `ballast`
- `bancreek`
- `beehive`
- `blueprint`
- `bridgeway`
- `brookstone`
- `bufferlabs`
- `bushido`
- `capforce`
- `castellan`
- `conductor_fund`
- `credit_suisse`
- `cresalta`
- `desjardins`
- `discipline_funds`
- `dvx_ventures`
- `ea_series_trust`
- `elements`
- `elm`
- `emirate_abu_dhabi`
- `esoterica`
- `etf_managers_group`
- `even_herd`
- `everence`
- `falconx`
- `fcf_advisors`
- `first_manhattan`
- `fitzgerald`
- `formula_folio`
- `fpa`
- `framework_digital_advisors`
- `freedom`
- `fundstrat`
- `gc_ferry_parent`
- `genter_capital`
- `gotham`
- `granite_group_advisors`
- `guggenheim`
- `hexis`
- `highland_capital`
- `hilton`
- `horizons`
- `hoya`
- `jlens`
- `knowledge_leaders`
- `logiq`
- `long_pond`
- `lsv`
- `m2_financial`
- `m_d_sass`
- `madison_avenue`
- `matrix`
- `max`
- `mcelhenny_sheffield`
- `measured_risk_portfolios`
- `merchant_investment_management`
- `meridian`
- `merk`
- `merlyn_ai`
- `mig_capital`
- `militia`
- `milliman`
- `moonvest`
- `nestyield`
- `new_age_alpha`
- `nicholas_wealth`
- `norris_perne_french`
- `north_square`
- `opus_capital_management`
- `pabrai`
- `panagram`
- `parnassus_investments`
- `pathfinder`
- `performance_trust`
- `portfolio_building_block`
- `premise_capital`
- `putnam`
- `pzena`
- `quadratic`
- `rareview_funds`
- `return_stacked`
- `river1`
- `riverfront`
- `robo_global`
- `roc`
- `rockefeller_capital`
- `saba_capital`
- `sammons_enterprises`
- `sapient`
- `saturna`
- `segall_bryant_hamill`
- `siren`
- `smi_funds`
- `sophus`
- `srh`
- `stance`
- `strategy_shares`
- `stratified`
- `subversive`
- `suncoast`
- `swedish_export_credit`
- `towle`
- `trimtabs`
- `tweedy_browne`
- `us_benchmark_series`
- `vega_financial`
- `vistashares`
- `wellesley_asset_management`
- `worth_charting`
- `yoke`

## 11. Per-changeset verification

Replace `<selector>` with provider-specific test names/keys. Codex shell calls
must carry the repository-required `rtk` prefix; commands stored here show the
underlying reproducible invocation.

1. Workstream validation:

   ```sh
   uv run --project backend python scripts/validate-workstream.py \
     ops/workstreams/feat-etf-holdings-constituents
   ```

2. Focused deterministic tests:

   ```sh
   uv run --project backend pytest \
     backend/tests/unit/services/test_etf_holdings_adapters.py \
     -k '<selector> or recognition_only_adapter_has_an_explicit_source_audit or every_live_backed_adapter_owns_its_fetch_entry_point' \
     -q --no-cov
   ```

3. Default live-module contracts:

   ```sh
   uv run --project backend pytest \
     backend/tests/live/test_etf_holdings_live_providers.py \
     -k 'provider_matrix_covers_every_registered_issuer_adapter or live_backed_providers_each_have_a_concrete_live_route_test' \
     -q --no-cov
   ```

4. Bounded changed-provider live probe:

   ```sh
   RUN_LIVE_ETF_HOLDINGS_TESTS=1 uv run --project backend pytest \
     backend/tests/live/test_etf_holdings_live_providers.py \
     -k '<selector> or provider_matrix_covers_every_registered_issuer_adapter or live_backed_providers_each_have_a_concrete_live_route_test' \
     -q --no-cov
   ```

5. Ruff:

   ```sh
   uv run --project backend ruff check \
     backend/app/services/etf_holdings_adapters.py \
     backend/tests/unit/services/test_etf_holdings_adapters.py \
     backend/tests/live/test_etf_holdings_live_providers.py
   ```

6. Derive provider counts/status/matrix and append concise SHA-specific evidence
   to `validation.jsonl`.
7. Run `git diff --check`; inspect unstaged and staged diffs.
8. Commit/push the coherent implementation context; then record and push the
   separate branch-owned operations checkpoint where required.

## 12. Milestones and failure classification

After each 5–10 promotions or coherent issuer family, run the complete adapter
unit module, default live module, full opt-in live module when rate limits
permit, Ruff, workstream/ledger validators, count query, workflow progress, and
clean/remote synchronization checks. If the full live matrix cannot reasonably
run every changeset, store each route's last live-probe date, but run the full
current matrix before review.

Classify live failures causally:

| Failure | Required response |
|---|---|
| DNS/network outage | Preserve deterministic evidence; record external condition; retry reasonably |
| 401/403/entitlement | Verify access model; classify blocked or request human decision |
| CAPTCHA/bot challenge | Do not bypass; classify access blocked |
| 404/410 | Find current official route/product state; do not retain native on a dead route |
| HTML/error body with 200 | Fail content validation and investigate route drift |
| Schema drift | Add fixture, repair narrowly, rerun deterministic and live tests |
| Empty/partial holdings | Fail promotion/native route unless explicitly explained |
| Stale as-of date | Distinguish calendar cadence from genuinely stale data |
| Wrong fund returned | Treat as critical symbol-mapping failure |

## 13. Final validation and review gate

After all 140 starting fallbacks have final ledger outcomes:

1. Re-derive final sets/counts/status totals and prove every invariant.
2. Run the complete deterministic adapter module.
3. Run the default live module.
4. Run the complete opt-in live provider matrix with
   `RUN_LIVE_ETF_HOLDINGS_TESTS=1`.
5. Run Ruff over all owned Python files.
6. Validate the workstream and provider ledger.
7. Run `make agent-session-validate SESSION_ID=<active-session-id>` for the
   required `docker_integration` profile. The repository-selected Docker-backed
   full-integration gate is mandatory; focused green tests do not replace it.
8. Push exact reviewed implementation and operations checkpoint commits.
9. Record exact-SHA CI. A green run for another SHA is not evidence.
10. Confirm repository-owned Docker resources are accounted for and use only
    scoped cleanup.
11. Confirm clean status and local HEAD equals remote feature HEAD.
12. Update ledger, provider universe, plan AC progress/gaps, handoff, validation
    records, and session state with exact evidence.
13. Set `ready_for_human_review` through repository workflow and stop. Do not
    integrate, promote, deploy, delete the branch, or claim human closure.

## 14. Definition of ready for human review

- All 140 starting fallbacks appear exactly once in historical ledger state.
- Every proven complete legitimate first-party route is implemented and
  validated as native.
- Every remaining provider has a dated issuer-specific defensible disposition;
  no untouched generic discovery placeholder is treated as final.
- Classification remains truthful even if the final native count is lower than
  hoped.
- Registry sets reconcile without intersections or omissions.
- Every native owns its route and has deterministic plus live coverage.
- Code, tests, live manifest, documentation, ledger, plan, handoff, and
  validation records agree.
- Complete deterministic, current opt-in live, Ruff, Docker integration, and
  exact-SHA CI evidence is current, with only narrowly documented genuine
  external outages distinguished from application failures.
- Branch is clean and synchronized.
- Closure remains pending; integration and deployment have not occurred.

## 15. Immediate next action

This original activation checklist is retained for historical continuity. The
current execution resumes after the completed GC Ferry Parent, Genter Capital,
and Gotham checkpoints; the live next action is recorded in the latest
execution section below.

Resume the branch workflow and active unbudgeted Codex goal. Begin AC1 and AC2,
not a speculative provider adapter:

1. derive registry/native/fallback sets from code;
2. reconcile any delta from 496/356/140;
3. create the complete provider ledger with controlled fields;
4. calculate/document the deterministic priority order;
5. add ledger/count invariants;
6. update stale provider-universe counts;
7. validate, commit, push, and checkpoint that durable-state changeset;
8. begin the highest-ranked provider investigation loop.

This ordering makes every later decision recoverable and safe to continue
across Codex models.

## 16. Previous execution checkpoint — 2026-09-02 (superseded by §17)

The approved plan is active in the dedicated feature worktree. The durable
implementation state has advanced beyond the historical 356/140 baseline as
follows:

| Classification | Current count |
|---|---:|
| Registered issuer adapter configurations | 496 |
| Native/live-backed providers | 374 |
| Audited fallback-only providers | 122 |

The current fallback status split is 8 `issuer_access_blocked`, 105
`needs_first_party_route_discovery`, 3 `non_executable_public_source`, and 6
`provider_not_a_portfolio_publisher`. The ledger still retains all 140 original
records exactly once, including the dated terminal dispositions for providers
that no longer remain in the runtime fallback set. There are 87 queued records
still requiring issuer-specific evidence or a final disposition.

Completed work in this execution includes the following native promotions and
dispositions already recorded in the branch-owned ledger: Guggenheim, ARS,
Avory, Ballast, Bancreek, BeeHive, Blueprint, Bridgeway, Brookstone,
BufferLABS, Bushido, CapForce, Castellan, Conductor Fund, CresAlta, Elm,
Esoterica, and Even Herd. ETF Managers Group is recorded as an
`inactive_or_successor_disposition` after Amplify's official acquisition and
fund-reorganization notice; Emirate Abu Dhabi, DVx Ventures, EA Series Trust,
and the other previously reviewed identities retain their evidence-specific
terminal or blocked dispositions.

The current implementation checkpoint is `0ac2cc29a7cfb1d8b27468a9c74618ad67c3a0f9`.
It adds `EvenHerdHoldingsAdapter` for EHLS, resolves the official product-page
declared daily `holdings.csv`, filters the EHLS account strictly, preserves
cash and long/short rows, records issuer-reported freshness and provenance,
and includes deterministic and opt-in live coverage. Deterministic adapter
tests pass 521/521; default live contracts pass 2 with 437 opt-in skips; the
bounded Even Herd live route passes 1/1; Ruff, workstream validation, and
whitespace checks pass. The full Docker-backed integration gate at
`2d96697d2fd98bad6c8c5796ff046cd6bbad4dfd` reached e2e-functional but recorded
153 passed, 106 skipped, and one failure in the unrelated
`F8p-current-history` Study Lab browser flow. A fresh-stack isolated retry
reproduced the failure as a missing histogram element (`toBeVisible` timeout),
not an ETF holdings error. AC7 therefore remains open pending an independent
repair or approved disposition of that pre-existing e2e gap; no unrelated
application code is changed by this workstream. The separate durable
operations checkpoint must record the updated ledger, handoff,
provider-universe counts, validation evidence, and session next action before
the next queue investigation.

The next ranked queue item at that checkpoint was `everence`; §17 records its
resolution. Continue the same evidence loop from the next queued provider:
inspect official product and holdings routes, promote only a complete
executable first-party source with strict identity and parser tests, otherwise
record a dated issuer-specific disposition. The Docker readiness check succeeds
under the narrow elevated permission required to access the local socket, while
the unprivileged sandbox cannot open that socket. The full Docker-backed
integration gate remains pending; this permission boundary is not permission to
weaken the native-route contract or to integrate the feature branch.

## 17. Current execution checkpoint — Everence/Praxis — 2026-09-02

The ranked `everence` audit is now resolved through the existing Praxis native
publisher route. The official Praxis ETF catalogue and individual holdings
pages identify PRXG, PRXV, and PRXI and declare complete current holdings CSVs
at the issuer's Azure publisher. The route is current as of September 2, 2026;
the PRXG, PRXV, and PRXI files contain 161, 277, and 277 account-scoped rows
respectively.

The implementation adds an explicit `EverenceHoldingsAdapter` that subclasses
the verified `PraxisHoldingsAdapter` rather than duplicating transport logic.
It preserves the Everence adapter key and parent/publisher relationship in
provenance, rejects unsupported symbols as native routes, filters each CSV to
the exact requested account, parses exchange-suffixed international tickers
such as `ASML NA`, preserves SEDOL identifiers, recognizes money-market/cash
rows, and records the issuer-disclosed composition date. The existing Praxis
adapter now shares the same exchange-aware symbol normalization and identifier
preservation, improving PRXI coverage without changing its verified route.

The code-derived split after this promotion is 496 registered, 375
native/live-backed, and 121 fallback-only providers. Fallback status counts are
8 issuer-access-blocked, 104 needs-first-party-route-discovery, 3
non-executable-public-source, and 6 non-portfolio-publisher. The ledger still
retains all 140 historical records exactly once, with `everence` now marked
`native_promoted`; 86 queued fallback records remain for the next audit pass.

Implementation checkpoint `1b29a6fb97bd353adce61b03b2aa216f56c83e53` contains
the route, tests, and live-manifest changes. The full deterministic adapter
module passes 522 tests; the default live module passes 2 with 440 opt-in
skips; and the bounded opt-in PRXG, PRXV, and PRXI checks pass 4 selected
cases (the fourth is the live-route matrix contract). Ruff, workstream
validation, and whitespace checks pass. The Docker-backed gate's existing
unrelated F8p-current-history Study Lab failure remains a separate AC7 gap and
must not be fixed from this ETF workstream.

## 18. Current execution checkpoint — FalconX/21Shares — 2026-09-02

The ranked `falconx` audit is now resolved as a parent-company promotion through
FalconX's independently managed 21Shares ETF/ETP subsidiary. FalconX's official
acquisition announcement establishes the parent/publisher relationship, while
the official 21Shares U.S. product catalogue currently lists ARKB, TETH, TOXR,
TSOL, TDOG, TDOT, TSUI, TCAN, THYP, and TKNS.

The catalogue's ARKB product page declares the primary and secondary API hosts
and the `/api/product_details/{ticker}` route. As of September 2, 2026, both
official hosts returned current September 1 product-detail payloads for all ten
symbols. The payloads contain complete parseable constituent data: one crypto
asset row for each single-asset product, four rows for TCAN, and nine rows for
TKNS, including cash or money-market entries where disclosed.

The implementation adds an explicit `FalconXHoldingsAdapter` that subclasses
the existing 21Shares transport, switches the parent route to the page-declared
primary and secondary hosts, restricts native readiness/fetching to the ten
verified U.S. symbols, and records FalconX as `parent_issuer` with 21Shares as
the publisher. The 21Shares parser's crypto classification now includes the
verified XRP, DOT, SUI, HYPE, and Canton Coin tickers in addition to its prior
asset set. Unsupported symbols remain `needs_issuer_route` unless SEC
identifiers enable the universal filing fallback.

The code-derived split after this promotion is 496 registered, 376
native/live-backed, and 120 fallback-only providers. Fallback status counts are
8 issuer-access-blocked, 103 needs-first-party-route-discovery, 3
non-executable-public-source, and 6 non-portfolio-publisher. The ledger still
retains all 140 historical records exactly once, with `falconx` now marked
`native_promoted`; 85 queued fallback records remain for the next audit pass.

Implementation checkpoint `2ffa2796a00391b482b03f1cb2a5be12a1a1be61` contains
the adapter, registry/config, deterministic parser/provenance test, and
ten-product opt-in live coverage. The focused FalconX/21Shares unit slice
passes 4 tests; the opt-in FalconX live route passes 1 test while exercising all
ten symbols; Ruff and whitespace checks pass. The full deterministic adapter
module and default live contract matrix must be rerun after the durable ledger
checkpoint. The Docker-backed gate's existing unrelated F8p-current-history
Study Lab failure remains a separate AC7 gap and must not be fixed from this ETF
workstream.

The next ranked queue item is `fcf_advisors`. Continue the same evidence loop:
inspect official product and holdings routes, promote only a complete executable
first-party source with strict identity and parser tests, otherwise record a
dated issuer-specific disposition. Do not integrate, promote, deploy, or push
the feature branch without the separately required authorization.

## 19. Current execution checkpoint — FCF Advisors successor disposition — 2026-09-02

The ranked `fcf_advisors` audit is resolved as an inactive/successor identity,
not as a duplicate native provider. Abacus Life's official rebrand and
acquisition announcement states that FCF Advisors was acquired and rebranded as
Abacus FCF Advisors. The current official Abacus FCF catalogue publishes ABFL,
ABLG, ABLD, ABOT, ABLS, and ABXB product pages, while the historical FCF
Advisors identity no longer presents a distinct publisher route.

Each current successor product page links a complete daily
`{SYMBOL}_allHoldings.csv` file from `abacusfcf.com`. Bounded read-only checks on
September 2, 2026 returned HTTP 200 for all six files; they contained 58, 51,
50, 52, 48, and 9 data rows respectively (plus headers), with issuer dates
shown as September 1, 2026 on the product pages. The existing
`AbacusGlobalHoldingsAdapter` already validates these pages, discovers the
declared files, parses identifiers/quantities/values/weights and cash rows, and
has deterministic plus opt-in live coverage.

No `FcfAdvisorsHoldingsAdapter` is added: current holdings belong to the
existing `abacus_global` successor identity, and registering a second native
route would misrepresent the provider universe and duplicate coverage. The
FCF ledger record keeps its runtime fallback key for historical discovery, but
its dated `current_status` and `disposition` are
`inactive_or_successor_disposition`; its next action is to resolve historical
symbols to `abacus_global` and reopen only if FCF Advisors becomes a distinct
current ETF publisher again.

The code-derived split remains 496 registered, 376 native/live-backed, and 120
fallback-only providers. Runtime fallback status counts remain 8
issuer-access-blocked, 103 needs-first-party-route-discovery, 3
non-executable-public-source, and 6 non-portfolio-publisher. The ledger still
retains all 140 historical records exactly once, and 84 queued fallback records
remain for the next audit pass. The next ranked queue item is
`first_manhattan`.

This successor-only audit changes durable evidence and queue state but no
runtime code. The focused ledger/reconciliation tests, workstream validator,
and whitespace checks pass. The existing full deterministic/live evidence at
the FalconX checkpoint remains valid; Docker integration still has the
unrelated F8p-current-history Study Lab gap.

## 20. Current execution checkpoint — First Manhattan — 2026-09-02

The ranked `first_manhattan` audit is resolved as a dated
`non_executable_public_source` disposition. First Manhattan's official
Excelsior ETF site identifies two current U.S. products, FMCX and FMCE, through
the home catalogue and their product pages. The official pages explicitly state
that, unlike traditional ETFs, the funds do not make their assets public daily
and instead disclose holdings sixty days after the end of each quarter. The
official FMCX prospectus independently confirms the non-transparent disclosure
model. No complete current holdings file or reproducible machine-readable
endpoint is declared by the issuer.

This evidence does not satisfy the feature's current holdings contract, which
requires a complete executable first-party artifact with current-date
provenance. No `FirstManhattanHoldingsAdapter` is added, and the identity is
not promoted through SEC filings or a third-party table. The ledger retains the
runtime fallback key for discovery compatibility while recording FMCX/FMCE,
the official domains and product routes, quarterly-sixty-day freshness, the
dated evidence refs, and the explicit non-executable disposition.

The code-derived split remains 496 registered, 376 native/live-backed, and 120
fallback-only providers. Runtime fallback status counts remain 8
issuer-access-blocked, 103 needs-first-party-route-discovery, 3
non-executable-public-source, and 6 non-portfolio-publisher; the First Manhattan
ledger disposition does not alter the runtime audit manifest. The exhaustive
ledger retains all 140 historical records exactly once, and 83 queued fallback
records remain. The next ranked queue item is `fitzgerald`.

This checkpoint changes the provider-audit evidence and queue state but no
runtime code. The focused ledger/reconciliation tests, workstream validator,
and whitespace checks must be recorded against the resulting durable SHA. The
existing full deterministic/live evidence at the FalconX checkpoint remains
valid; the current Docker-backed gate still has the unrelated reproducible
F8p-current-history Study Lab histogram timeout.

## 21. Current execution checkpoint — Fitzgerald/Nicholas Wealth — 2026-09-02

The ranked `fitzgerald` audit is promoted through the official XFUNDS by
Nicholas Wealth pages for the Fitz-Gerald Must Have Portfolio ETF (FITZ) and
the Fitz-Gerald Must Have Portfolio and Options Overlay ETF (FIZY). Each page
declares a holdings download whose page script resolves to a nonce-scoped
`twm_download=holdings&ticker={symbol}` CSV endpoint on `nicholasx.com`.

Bounded live requests on September 2, 2026 returned HTTP 200 CSV artifacts
dated September 2, 2026. FITZ returned 31 parseable rows and FIZY returned 112
rows, including the FIZY option positions. The new explicit
`FitzgeraldHoldingsAdapter` validates the requested product page and issuer
domain, discovers the current nonce-bearing download URL rather than relying
on a stale hard-coded nonce, enforces ticker scoping, preserves CUSIPs,
quantities, market values, weights, cash, and dates, and classifies FIZY option
contracts as derivatives with no tradable equity symbol. Its metadata records
Nicholas Wealth as publisher and parent issuer, the Fitz-Gerald product
relationship, current daily provenance, and the page-declared route.

The adapter configuration is native/live-backed and the live manifest covers
both FITZ and FIZY in one bounded opt-in test. The deterministic unit test
covers nonce discovery, issuer-domain rejection, current-date parsing,
account scoping, metadata, and derivative classification. The full
deterministic adapter module passes 524 tests; the default live contract matrix
passes 2 with 442 opt-in skips; the focused opt-in Fitzgerald test passes 1;
Ruff and whitespace checks pass.

The code-derived split after this promotion is 496 registered, 377
native/live-backed, and 119 fallback-only providers. Runtime fallback status
counts are 8 issuer-access-blocked, 102 needs-first-party-route-discovery, 3
non-executable-public-source, and 6 non-portfolio-publisher. The ledger retains
all 140 historical records exactly once, with `fitzgerald` marked
`native_promoted`; 82 queued fallback records remain and the next ranked item
is `formula_folio`. The separate `nicholas_wealth` identity remains queued for
its own identity audit; this promotion does not create a duplicate route for
that key.

Implementation checkpoint
`a1caaa0c6da2ded19891795b58e6e6ffe9ae09fd` contains the adapter, registry and
config, deterministic parser/provenance coverage, and opt-in live coverage.
The durable ledger/docs/session checkpoint must reference this code SHA. The
full current opt-in provider matrix and Docker-backed integration gate remain
pending at the 377-native baseline; the known unrelated F8p-current-history
Study Lab histogram timeout remains an AC7 gap.

## 22. Current execution checkpoint — FormulaFolios inactive/successor disposition — 2026-09-02

The ranked `formula_folio` audit found no current portfolio to promote. The
official SEC-hosted August 1, 2023 supplement names FormulaFolios Hedged Growth
ETF (FFHG), FormulaFolios Smart Growth ETF (FFSG), FormulaFolios Tactical Growth
ETF (FFTG), and FormulaFolios Tactical Income ETF (FFTI), and records the
Board-authorized orderly liquidation: trading ended October 6, 2023, the funds'
assets were expected to be liquidated and distributed on October 16, 2023, and
the funds would terminate after distribution. The official FormulaFolios site
is retained only as a historical candidate domain and does not establish a
current executable holdings route.

Brookstone's official combination announcement establishes that Brookstone and
FormulaFolios combined under the Brookstone name, with the FormulaFolios brand
retained for asset-management oversight. Current Brookstone ETFs and their
complete holdings routes are already represented by the distinct native
`brookstone` identity; no duplicate FormulaFolios adapter or SEC-derived native
route is warranted.

The ledger record now preserves FFHG, FFSG, FFTG, and FFTI, the historical and
successor domains, both dated official evidence references, the liquidation
dates, and an explicit `inactive_or_successor_disposition`. Route completeness,
symbol mapping, and current holdings proof remain false. The runtime
`FormulaFolioReconciledFallbackHoldingsAdapter` and audit manifest are retained
for historical/compatibility behavior, so runtime fallback status counts do not
change.

The code-derived split remains 496 registered, 377 native/live-backed, and 119
fallback-only providers. Runtime fallback status counts remain 8
issuer-access-blocked, 102 needs-first-party-route-discovery, 3
non-executable-public-source, and 6 non-portfolio-publisher. The exhaustive
ledger retains all 140 historical records exactly once, with
`formula_folio` now terminally recorded as inactive/successor; 81 queued
fallback records remain and the next ranked item is `fpa`. The separate
`brookstone` identity remains the current native successor route.

This checkpoint changes only issuer-audit evidence, queue state, and durable
documentation; no runtime code changes are required. The focused ledger and
reconciliation tests, workstream validator, whitespace checks, and validation
receipt must be recorded against the resulting documentation SHA. The complete
opt-in provider matrix and Docker-backed integration gate remain pending at the
377-native baseline, with the known unrelated reproducible F8p-current-history
Study Lab histogram timeout still an AC7 gap.

## 30. Current execution checkpoint — Granite Group Advisors non-portfolio disposition — 2026-09-03

The ranked `granite_group_advisors` audit resolved a wealth-management adviser
identity rather than a distinct ETF portfolio publisher. Granite Group Advisors'
official site describes customized wealth-management portfolios and allocation to
independent fund managers. Its official Form ADV says the firm does not offer
proprietary products such as target-date or lifestyle funds; it may purchase
exchange-traded funds for client accounts, but that is client-account activity,
not sponsorship or publication of ETF portfolios. SEC and AdviserInfo records
identify the organization as an investment adviser/manager and do not expose an
ETF trust, product catalogue, or issuer holdings feed.

The ledger now records `granite_group_advisors` as
`provider_not_a_portfolio_publisher`, preserving the official Granite Group and
SEC/AdviserInfo routes and dated evidence. No runtime adapter, registry,
fallback-manifest, or live-test change is required; manager/13F disclosures
remain explicitly ineligible as ETF constituents. The code-derived split remains
496 registered, 381 native/live-backed, and 115 fallback-only providers. Runtime
fallback status counts remain 8 issuer-access-blocked, 98
needs-first-party-route-discovery, 3 non-executable-public-source, and 6
non-portfolio-publisher. The exhaustive ledger retains all 140 historical
records exactly once, with 73 queued fallback records remaining; the next ranked
queued item is `hexis`.

This checkpoint changes only issuer-audit evidence, queue state, and durable
documentation. The current runtime implementation baseline remains
`5f8d0b9dacf7231ae9ea1a906d1360c798bd1812`; the ledger and documentation
receipt must reference the resulting documentation SHA and dated Granite Group
evidence. The complete deterministic adapter suite, full opt-in provider matrix,
and Docker-backed integration gate remain pending at the 381-native baseline;
the known unrelated reproducible F8p-current-history Study Lab histogram timeout
remains an AC7 gap.

## 29. Current execution checkpoint — Gotham ETFs native promotion — 2026-09-03

The ranked `gotham` audit found complete executable first-party routes for the
three current Gotham ETFs. Gotham's official catalogue and product pages
identify GSPY as The Gotham Enhanced 500 ETF, GVLU as The Gotham 1000 Value ETF,
and SHRT as The Gotham Short Strategies ETF. Each symbol-specific page exposes
an official `DownloadHoldings` CSV route on `gothametfs.com`; the current SAI
also identifies the three funds and directs investors to GothamETFs.com for
daily portfolio holdings. The official September 2, 2026 exports contained 502
GSPY rows, 481 GVLU rows, and 677 SHRT rows.

The new explicit `GothamHoldingsAdapter` maps only GSPY, GVLU, and SHRT to their
verified product download paths. It rejects unsupported symbols and unapproved
source URLs, requires the exact declared CSV schema and one consistent as-of
date, validates the final URL remains on the issuer host and requested product
path, parses percentage-point and dollar values, preserves CUSIPs and signed
shares, assigns USD, and records Gotham ETFs publisher / Gotham Asset Management
parent provenance. Cash & Other rows are normalized as cash; SHRT TRS rows are
normalized as derivatives with no tradable symbol while retaining signed short
quantities and source identifiers.

The deterministic unit test covers all three symbol mappings, probe behavior,
source URL rejection, complete-schema parsing, date/weight/value conversion,
cash semantics, and SHRT derivative/short semantics. The opt-in live test
fetches all three official CSV routes, enforces conservative minimum row counts,
checks current provenance/freshness, and requires SHRT cash, derivative, and
negative-position evidence. `gotham` is now in the native/live-backed registry,
the ETF.com reconciliation native set, and the exhaustive live-provider
manifest; it is removed from the fallback audit manifest.

The code-derived split after this promotion is 496 registered, 381
native/live-backed, and 115 fallback-only providers. Runtime fallback status
counts are 8 issuer-access-blocked, 98 needs-first-party-route-discovery, 3
non-executable-public-source, and 6 non-portfolio-publisher. The exhaustive
ledger retains all 140 historical records exactly once, with `gotham` marked
`native_promoted`; 74 queued fallback records remain and the next ranked item is
`granite_group_advisors`.

Implementation checkpoint SHA: `5f8d0b9dacf7231ae9ea1a906d1360c798bd1812`.
The provider-audit ledger and documentation checkpoint must reference this SHA
and the dated Gotham evidence. The focused Gotham unit and opt-in live checks
passed; the complete deterministic adapter suite, full opt-in provider matrix,
and Docker-backed integration gate remain pending at the 381-native baseline.
The known unrelated reproducible F8p-current-history Study Lab histogram
timeout remains an AC7 gap.

## 28. Current execution checkpoint — Genter Capital identity reconciliation — 2026-09-03

The ranked `genter_capital` audit resolved an alternate identity for an
existing native publisher rather than requiring a second adapter. Genter
Capital's official product pages and public settings document identify the
GENT, GEND, GENM, and GENW funds and bind each ticker to a fund-scoped
identifier. The repository already implements that route as `mcivy` through
Genter's disclosed Nottingham Company fund-data endpoint, with strict
symbol/fund/name checks, complete holdings parsing, cash and derivative
classification, effective-date freshness, deterministic coverage, and an
opt-in live GEND test. ETF Database's issuer-brand record also labels the
Genter products as McIvy Co. LLC / Genter Capital, confirming the identity
relationship.

The ledger now records `genter_capital` as
`inactive_or_successor_disposition`, preserving the four representative
symbols, official Genter and Nottingham routes, dated source evidence, and the
existing `mcivy` runtime configuration/live receipt. Route completeness and
symbol mapping remain false for the duplicate key so native ownership is not
double-counted; no runtime adapter, registry, fallback manifest, or live test
changes are required. The existing `mcivy` adapter remains the sole native
owner and should be extended only for additional Genter products after the
same identity-verified, complete current holdings contract is proven.

The code-derived split remains 496 registered, 380 native/live-backed, and 116
fallback-only providers. Runtime fallback status counts remain 8
issuer-access-blocked, 99 needs-first-party-route-discovery, 3
non-executable-public-source, and 6 non-portfolio-publisher. With GC Ferry
Parent and Genter Capital resolved in the ledger, 75 records remain queued and
`gotham` is the next planned audit item.

This checkpoint changes only issuer-audit evidence, queue state, and durable
documentation. The current runtime implementation baseline remains
`e33ddd8ebd919d14e1969af2aa36537864ece0f2`; the ledger and documentation
receipt must be recorded against the resulting documentation SHA. The complete
opt-in provider matrix and Docker-backed integration gate remain pending at the
380-native baseline, with the known unrelated reproducible F8p-current-history
Study Lab histogram timeout still an AC7 gap.

## 27. Current execution checkpoint — GC Ferry Parent identity reconciliation — 2026-09-03

The ranked `gc_ferry_parent` audit resolved a corporate-parent identity rather
than a distinct holdings publisher. The SEC's August 25, 2026 Form 8-K
identifies GC Ferry Parent, L.P. as the seller and GC Ferry Holdings, Inc. as
First Eagle in the proposed Victory Capital acquisition. The current First
Eagle Form ADV records the ownership chain from GC Ferry Parent through GC
Ferry Holdings and First Eagle Holdings to First Eagle Investment Management,
LLC, and identifies FEIM as adviser to the First Eagle ETF Trust. GC Ferry
Parent is therefore an ownership/holding identity above the publisher and does
not expose an independent ETF holdings route.

First Eagle's official ETF catalogue identifies the current FEGE, FEOE, USFE,
and FEMD products and links their publisher-owned product pages. Those pages,
not GC Ferry Parent, are the source of current holdings tables. The existing
`first_eagle` adapter remains the sole native owner for the publisher route;
creating a second GC Ferry adapter would duplicate ownership and misstate
provenance. No runtime adapter, registry, fallback manifest, or live test
changes are required for this identity disposition.

The provider-audit ledger now records `gc_ferry_parent` as
`provider_not_a_portfolio_publisher`, with the four representative First Eagle
symbols, dated SEC/Form ADV/catalogue evidence, explicit First Eagle publisher
resolution, and a reopen condition only if GC Ferry Parent later exposes a
distinct ETF portfolio route. The code-derived split remains 496 registered,
380 native/live-backed, and 116 fallback-only providers. Runtime fallback
status counts remain 8 issuer-access-blocked, 99 needs-first-party-route-
discovery, 3 non-executable-public-source, and 6 non-portfolio-publisher; 76
ledger records remain queued and `genter_capital` is the next planned audit
item.

This checkpoint changes only issuer-audit evidence, queue state, and durable
documentation. The current runtime implementation baseline remains
`e33ddd8ebd919d14e1969af2aa36537864ece0f2`; the ledger and documentation
receipt must be recorded against the resulting documentation SHA. The complete
opt-in provider matrix and Docker-backed integration gate remain pending at the
380-native baseline, with the known unrelated reproducible F8p-current-history
Study Lab histogram timeout still an AC7 gap.

## 26. Current execution checkpoint — Fundstrat Granny Shots — 2026-09-03

The ranked `fundstrat` audit found complete executable first-party routes for
the Fundstrat Granny Shots ETF family. The official full-holdings pages on
`grannyshots.com` identify and publish current portfolios for GRNY (Fundstrat
Granny Shots US Large Cap ETF), GRNJ (Fundstrat Granny Shots US Small- & Mid-Cap
ETF), and GRNI (Fundstrat Granny Shots US Large Cap & Income ETF). Each page
server-renders a complete table with Ticker, CUSIP, Name, Weight, Shares, and
Market Value fields plus a Holdings-as-of date of September 2, 2026. The live
row counts were 42 for GRNY, 62 for GRNJ, and 130 for GRNI.

The new explicit `FundstratHoldingsAdapter` maps only GRNY, GRNJ, and GRNI to
their verified full-holdings pages. It validates symbol-specific page identity,
rejects unapproved URLs, selects the complete table by required headers,
requires a bounded non-trivial row count, parses and requires the disclosed
holdings-as-of date, converts percentage and dollar strings, preserves CUSIPs
and shares, assigns USD, and records Fundstrat Capital as publisher/parent.
GRNI's `Type=Option` rows are mapped to derivative holdings with no tradable
symbol, while ordinary stock rows are normalized to equity holdings. The route
does not depend on SEC reconstruction or an undocumented endpoint.

The deterministic unit test covers all three symbol mappings, probe behavior,
unsupported symbols, source URL rejection, identity checks, complete-table
parsing, date parsing, weight/value conversion, identifier preservation, GRNI
option classification, and publisher/provenance metadata. The opt-in live test
fetches all three official pages, requires their observed minimum row counts,
checks current metadata, and requires derivative classification on GRNI. The
ETF.com brand reconciliation invariant now treats `fundstrat` as
native-promoted, the fallback manifest no longer lists it, and the
live-provider manifest owns the bespoke three-product route test.

The code-derived split after this promotion is 496 registered, 380
native/live-backed, and 116 fallback-only providers. Runtime fallback status
counts are 8 issuer-access-blocked, 99 needs-first-party-route-discovery, 3
non-executable-public-source, and 6 non-portfolio-publisher. The exhaustive
ledger retains all 140 historical records exactly once, with `fundstrat` marked
`native_promoted`; 77 queued fallback records remain and the next ranked item
is `gc_ferry_parent`.

Implementation checkpoint SHA: `e33ddd8ebd919d14e1969af2aa36537864ece0f2`.
The provider-audit ledger and documentation checkpoint must reference this SHA
and the dated Granny Shots evidence. The complete opt-in provider matrix and
Docker-backed integration gate remain pending at the 380-native baseline; the
known unrelated reproducible F8p-current-history Study Lab histogram timeout
remains an AC7 gap.

## 25. Current execution checkpoint — Freedom ETFs / FRDM — 2026-09-03

The ranked `freedom` audit found a complete, executable first-party route for
the Freedom 100 Emerging Markets ETF (`FRDM`). Freedom ETFs' official product
page at `https://freedometfs.com/frdm/` identifies the requested ticker and fund
name, declares a Fund Holdings table with the headers Ticker, Name, CUSIP,
SEDOL, Shares, Price, Market Value ($mm), and % of Net Assets, and publishes a
separate Effective Date table. The live page returned an effective date of
September 2, 2026 and 136 embedded holding rows, including a Cash & Other row.
The table is server-rendered in the issuer page HTML; no undocumented or paid
endpoint was required.

The new explicit `FreedomHoldingsAdapter` is scoped strictly to FRDM and the
verified product-page URL. It validates the page identity, rejects an
unapproved source URL, selects the table by its complete holdings schema,
requires a bounded complete result, parses the separate effective-date table,
converts Market Value ($mm) into dollar market values, converts percentage-point
weights into canonical decimals, preserves CUSIP/SEDOL/shares, assigns USD, and
classifies Cash & Other as cash. Metadata records the issuer page, effective-date
freshness, Freedom ETFs as publisher/parent, and the native snapshot
provenance. Long-form month-name dates are now accepted by the shared issuer
date parser because the official page uses `September 2, 2026`.

The deterministic unit test covers FRDM probing, unsupported-symbol routing,
source URL rejection, page identity, table parsing, effective-date parsing,
million-dollar conversion, weight conversion, identifiers, cash semantics, and
publisher/provenance metadata. The opt-in live test fetches the official page,
requires at least 100 rows and a cash row, and verifies the native metadata
contract. The ETFDB issuer-league reconciliation invariant now treats
`freedom` as native-promoted, the fallback manifest no longer lists it, and the
live-provider manifest owns the bespoke FRDM test.

The code-derived split after this promotion is 496 registered, 379
native/live-backed, and 117 fallback-only providers. Runtime fallback status
counts are 8 issuer-access-blocked, 100 needs-first-party-route-discovery, 3
non-executable-public-source, and 6 non-portfolio-publisher. The exhaustive
ledger retains all 140 historical records exactly once, with `freedom` marked
`native_promoted`; 78 queued fallback records remain and the next ranked item
is `fundstrat`.

Implementation checkpoint SHA: `5518a3c3f43556d81aedcbb0ff2c0e1de47fe7be`.
The provider-audit ledger and documentation checkpoint must reference this SHA
and the dated Freedom page/live evidence. The complete opt-in provider matrix
and Docker-backed integration gate remain pending at the 379-native baseline;
the known unrelated reproducible F8p-current-history Study Lab histogram timeout
remains an AC7 gap.

## 24. Current execution checkpoint — Framework Digital Advisors / GSR BESO — 2026-09-03

The ranked `framework_digital_advisors` audit found one current executable
first-party route. The official Framework/GSR product page at
`https://gsretps.io/etf/beso` identifies BESO as the GSR Crypto Core3 ETF and
declares the `gsr-transformer.gsr.io` API client. Its details endpoint returns
the matching BESO product identity and `updateAt: 2026-09-01T00:00:00.000Z`;
its holdings endpoint returns nine rows, including the underlying ETF/fund
positions and a Cash & Other row.

The new explicit `FrameworkDigitalAdvisorsHoldingsAdapter` validates the
official product-page identity, uses only the issuer-declared details and
holdings hosts, verifies the returned ticker, parses the JSON schema with
strict symbol/name requirements, converts percentage-point weights, classifies
underlying ETFs/funds and cash, and records the details `updateAt` date as
composition/as-of freshness. Metadata preserves GSR ETFs as the publisher and
Framework Digital Advisors as adviser/parent identity. The adapter is
deliberately scoped to BESO: SEC-listed DATZ and other candidate GSR symbols
currently return no product page or API data, so they are not silently
reconstructed through EDGAR.

The deterministic unit test covers product identity, official-domain rejection,
details/holdings request ordering, symbol mapping, fund/cash classification,
weight conversion, freshness, and parent/publisher provenance. The bounded
opt-in live test covers the current BESO API route and requires a cash row. The
ETFDB issuer-league reconciliation invariant now treats
`framework_digital_advisors` as native-promoted, and the live-provider manifest
owns a bespoke route test for the new adapter.

The code-derived split after this promotion is 496 registered, 378
native/live-backed, and 118 fallback-only providers. Runtime fallback status
counts are 8 issuer-access-blocked, 101 needs-first-party-route-discovery, 3
non-executable-public-source, and 6 non-portfolio-publisher. The exhaustive
ledger retains all 140 historical records exactly once, with
`framework_digital_advisors` marked `native_promoted`; 79 queued fallback
records remain and the next ranked item is `freedom`.

Implementation and validation records for this checkpoint must reference the
resulting adapter/config/test SHA and the dated Framework/GSR evidence. The
complete opt-in provider matrix and Docker-backed integration gate remain
pending at the 378-native baseline; the known unrelated reproducible
F8p-current-history Study Lab histogram timeout remains an AC7 gap.

## 23. Current execution checkpoint — FPA alias to First Pacific Advisors — 2026-09-02

The ranked `fpa` audit resolved an identity duplicate rather than adding a
second native adapter. First Pacific Advisors' official fund catalogue lists
the FPA Global Equity ETF (FPAG), FPA Short Duration Government ETF (FPAS), and
FPA Global Allocation ETF (FPAA), all advised by First Pacific Advisors, LP.
The repository already represents that same issuer as `first_pacific`, with a
provider-specific dated multi-fund CSV adapter, deterministic parser coverage,
and an opt-in live test for the verified FPAG route.

The official FPAG page-declared daily export returned a September 2, 2026 CSV
and the bounded opt-in `first_pacific` live test passed. The FPAS and FPAA
product pages currently render placeholder `X/X/XX` holdings dates and no
complete current rows in the bounded check; their current holdings routes are
therefore not independently proven. Because `fpa` is an abbreviation for the
same First Pacific Advisors identity, creating a duplicate native FPA adapter
would violate provider ownership and could double-count the issuer.

The ledger record now preserves FPAG, FPAS, and FPAA, the official FPA catalogue
and product domains, the verified FPAG daily route, the runtime
`first_pacific` configuration reference, and the explicit
`inactive_or_successor_disposition`. Route completeness and symbol mapping for
the duplicate key remain false; the existing `first_pacific` adapter remains
the sole native owner and should be extended to FPAS/FPAA only after each
product exposes a complete executable current holdings artifact and live proof.

The code-derived split remains 496 registered, 377 native/live-backed, and 119
fallback-only providers. Runtime fallback status counts remain 8
issuer-access-blocked, 102 needs-first-party-route-discovery, 3
non-executable-public-source, and 6 non-portfolio-publisher. The exhaustive
ledger retains all 140 historical records exactly once, with `fpa` recorded as
an inactive/successor alias; 80 queued fallback records remain and the next
ranked item is `framework_digital_advisors`.

This checkpoint changes only issuer-audit evidence, queue state, and durable
documentation; no runtime code changes are required. The focused
ledger/reconciliation tests, workstream validator, whitespace checks, and live
receipt must be recorded against the resulting documentation SHA. The complete
opt-in provider matrix and Docker-backed integration gate remain pending at the
377-native baseline, with the known unrelated reproducible F8p-current-history
Study Lab histogram timeout still an AC7 gap.

## 31. Current execution checkpoint — Hexis Capital Management / NICO — 2026-09-03

The ranked `hexis` audit found a complete, executable first-party route for the
Hexis Active Nicotine Engagement ETF (`NICO`). The official product page at
`https://hexis.capital/nico` identifies the fund and links to the public Hexis
FilePoint application. The FilePoint NICO view at
`https://hexis.filepoint.live/iframe_main.html` exposes a `Download Holdings`
control, and its official application script declares the exact daily holdings
CSV filename and route. The current CSV fetched on September 3, 2026 was dated
September 3, 2026 and contained 18 NICO rows, including equities,
exchange-suffixed international listings, signed TRS derivative positions, the
FXFXX money-market fund, and Cash&Other.

The new explicit `HexisHoldingsAdapter` is scoped strictly to NICO and the
issuer-owned FilePoint chain. It validates product identity, the FilePoint
iframe markers, the declared application-script filename, official host/path
preservation, NICO account identity, the complete CSV schema, and one
consistent as-of date. It splits exchange-suffixed symbols such as `033780 KS`,
classifies funds/cash/derivatives, preserves raw CUSIPs and signed quantities,
and records Hexis Capital Management/FilePoint publisher provenance plus the
product/app/script/snapshot routes. Unsupported symbols continue to use the
existing SEC fallback path only when a CIK is supplied; SEC data is not used to
silently promote an unverified product.

The deterministic unit test covers route declaration validation, request
ordering, NICO identity, schema/date checks, exchange mapping, fund/cash/TRS
classification, signed positions, and publisher/provenance metadata. The
opt-in live test fetches the current FilePoint CSV, requires at least 20 rows,
and verifies current-date, cash, derivative, and international-exchange
semantics. The ETFDB issuer-league reconciliation invariant now treats `hexis`
as native-promoted, removes it from the runtime fallback audit, and the
live-provider manifest owns the bespoke NICO route test.

The code-derived split after this promotion is 496 registered, 382
native/live-backed, and 114 fallback-only providers. Runtime fallback status
counts are 8 issuer-access-blocked, 97 needs-first-party-route-discovery, 3
non-executable-public-source, and 6 non-portfolio-publisher. The exhaustive
ledger retains all 140 historical records exactly once, with `hexis` marked
`native_promoted`; 72 queued fallback records remain and the next ranked item
is `highland_capital`.

Implementation and validation records for this checkpoint must reference the
resulting Hexis adapter/config/test SHA and dated Hexis product, FilePoint, SEC,
and live CSV evidence. The complete opt-in provider matrix and Docker-backed
integration gate remain pending at the 382-native baseline; the known unrelated
reproducible F8p-current-history Study Lab histogram timeout remains an AC7 gap.

## 32. Current execution checkpoint — Highland Capital non-executable source — 2026-09-03

The ranked `highland_capital` audit found a reachable issuer-owned holdings
artifact but no complete canonical symbol mapping. Highland Capital's official
ETF page at `https://www.highlandcap.com/etf/` identifies the HCM Large Cap
Growth ETF (`AQLG`) and links the current CSV
`https://www.highlandcap.com/wp-content/uploads/etf-holdings/AQLG_holdings_current.csv`.
The live file returned 130 rows with names, CUSIPs, quantities, and percentage
weights. Every row's `Ticker` field is blank. The same page identifies holdings
as of August 25, 2026, while the second Highland Capital Large Cap Value ETF
described in the current prospectus still has no assigned ticker or current
holdings route.

The official SEC prospectus at
`https://www.sec.gov/Archives/edgar/data/1771146/000177114626000253/ck0001771146-20260129.htm`
corroborates the AQLG product identity and directs investors to Highland's
website for daily holdings, but it does not repair the missing ticker-bearing
artifact. Third-party 13F/portfolio pages and external CUSIP lookups are not
acceptable substitutes for issuer-published constituent mapping. Highland is
therefore recorded as `non_executable_public_source`, with route completeness
and symbol mapping unproven; no runtime adapter or false native promotion is
added.

The ledger preserves the issuer page, CSV, and SEC evidence, records AQLG as
the representative symbol, and leaves the runtime fallback adapter unchanged.
The ledger now has 71 queued records; runtime fallback status counts remain
8 issuer-access-blocked, 97 needs-first-party-route-discovery, 3
non-executable-public-source, and 6 non-portfolio-publisher because the
code-derived Highland audit entry remains discovery while its ledger
disposition is more specific. The next ranked queue item is `hilton`.

The complete deterministic/live matrix and Docker-backed integration gate remain
pending at the 382-native baseline; the known unrelated reproducible
F8p-current-history Study Lab histogram timeout remains an AC7 gap.

## 33. Current execution checkpoint — Hilton SMCO/HBDC native promotion — 2026-09-03

The ranked `hilton` audit found a complete, executable first-party route for
both currently identified Hilton ETFs. The official Hilton ETFs home page and
product pages identify the Hilton Small-MidCap Opportunity ETF (`SMCO`) and the
Hilton BDC Corporate Bond ETF (`HBDC`). Each product page declares the shared
`https://hiltonetfjson.com/etf/AllHoldings.csv` download, and the dedicated
all-holdings pages provide the same route context. The current CSV returned on
September 3, 2026 contained one `2026-09-02` snapshot with 160 HBDC account
rows and 66 SMCO account rows.

The new `HiltonHoldingsAdapter` validates the requested SMCO/HBDC identity,
official product-page host/path, declared complete AllHoldings filename, data
host/path, complete schema, account filtering, and one consistent trade date.
It treats the issuer's percentage-point `Weightings` values as canonical
fractions, preserves CUSIPs and raw source fields, retains signed quantities,
and classifies SMCO equity, money-market fund, and Cash&Other rows alongside
HBDC fixed-income, fund, and cash rows. Metadata records the Hilton ETFs
publisher, Hilton Capital Management parent, official product/all-holdings/CSV
routes, dated issuer-disclosed freshness, and the native snapshot provenance.

The deterministic unit test covers unsupported symbols, source-route rejection,
product-page declaration, request ordering, account-scoped filtering, date and
weight conversion, fund/cash/fixed-income classification, and provenance. The
opt-in live test fetches both SMCO and HBDC from the current official CSV,
requires at least ten rows per account, and verifies each product's expected
holding classes and metadata. Hilton is removed from the runtime fallback
discovery audit and promoted in the exhaustive ledger.

The code-derived split after this promotion is 496 registered, 383
native/live-backed, and 113 fallback-only providers. Runtime fallback status
counts are 8 issuer-access-blocked, 96 needs-first-party-route-discovery, 3
non-executable-public-source, and 6 non-portfolio-publisher. The exhaustive
ledger retains all 140 historical records exactly once, with `hilton` marked
`native_promoted`; 70 queued fallback records remain and the next ranked item
is `horizons`.

The complete opt-in provider matrix and Docker-backed integration gate remain
pending at the 383-native baseline; the known unrelated reproducible
F8p-current-history Study Lab histogram timeout remains an AC7 gap.

## 34. Current execution checkpoint — Horizons inactive/successor disposition — 2026-09-03

The ranked `horizons` audit found no current independent Horizons U.S. ETF
publisher to promote. The official SEC reorganization document maps the former
Horizons DAX Germany ETF, Horizons NASDAQ 100 Covered Call ETF, and Horizons
S&P 500 Covered Call ETF into corresponding Global X DAX (`DAX`), Global X
Nasdaq 100 Covered Call (`QYLD`), and Global X S&P 500 Covered Call (`HSPX`)
funds. It states that Global X Management Company becomes adviser and that
the Horizons target funds are transferred in complete liquidation and
termination. Current Global X product pages expose the successor products and
their holdings sections. The legacy Horizons USA URL now redirects to the
Global X Canada site, and the last Horizons ETF Trust I financial statements
are historical.

Because the successor mapping is explicit and the current portfolio routes are
already owned by the existing `global_x` identity, a separate Horizons native
adapter would duplicate publisher ownership and misstate provenance. The
ledger therefore records `horizons` as a dated
`inactive_or_successor_disposition`, preserves the historical representative
symbols and SEC/Global X routes, and leaves the runtime fallback class intact.
No Holdings adapter, deterministic parser test, or live-provider entry is
added for Horizons; future work should reopen only if Horizons independently
sponsors a current U.S.-listed ETF and publishes a distinct complete
first-party holdings route.

The code-derived split remains 496 registered, 383 native/live-backed, and 113
fallback-only providers. Runtime fallback status counts remain 8
issuer-access-blocked, 96 needs-first-party-route-discovery, 3
non-executable-public-source, and 6 non-portfolio-publisher. The exhaustive
ledger retains all 140 historical records exactly once; 69 queued fallback
records remain and the next ranked item is `hoya`.

## 35. Current execution checkpoint — Hoya alias reconciliation — 2026-09-03

The ranked `hoya` audit confirmed that Hoya Capital's official HOMZ and RIET
product pages identify the current U.S.-listed ETFs, publish complete
identifier/CUSIP/shares/market-value holdings tables, and link the complete
fund workbooks through the issuer-owned
`download-holdings-usbanks.php?fund={symbol}` route. The official pages report
current holdings-as-of dates and identify Hoya Capital as the ETF issuer/adviser.

The repository already has a native `pettee` adapter for this same Hoya route.
It validates the symbol-specific product page, the page-declared workbook URL,
the workbook identity and required schema, and canonical row mapping while
preserving CUSIPs and Hoya Capital Real Estate provenance. The bounded opt-in
live test now exercises both HOMZ and RIET and passed for both current
workbooks.

The StockAnalysis `hoya` provider key is consequently recorded in the audit
ledger as an `inactive_or_successor_disposition` alias of `pettee`. The runtime
alias and URL-domain hints resolve Hoya Capital display names and
`hoyaetfs.com`/`hoyacapital.com` product URLs to the existing native adapter.
No duplicate Hoya adapter is added, and no SEC-derived fallback is promoted.
The code-derived split remains 496 registered, 383 native/live-backed, and 113
fallback-only providers; the exhaustive ledger now has 68 queued records and
the next ranked item is `jlens`.

## 36. Current execution checkpoint — JLens/TOV native promotion — 2026-09-03

The ranked `jlens` audit verified the official JLens page at
`https://investjewishly.org/`, which identifies TOV as the JLens 500 Jewish
Advocacy U.S. ETF and exposes a complete server-rendered Fund Holdings table.
The table includes ticker, name, CUSIP, SEDOL, shares, price, Market Value
($mm), and percentage-of-net-assets columns; a separate Fund Data & Pricing
table exposes the 2026-09-02 fund-data as-of date. The page is the first-party
route of record; the adapter does not infer a holdings composition date from
the pricing metadata.

`JLensHoldingsAdapter` is registered as the native `jlens` owner. It enforces
TOV and official-host identity, requires the complete holdings schema and a
minimum-row completeness guard, converts Market Value ($mm) into dollars,
preserves source identifiers/weights, and records JLens/Empowered Funds
publisher provenance plus the fund-data date. Deterministic and bounded opt-in
live tests cover parser mapping, value/date semantics, metadata, request
routing, and the current 498-row page.

The runtime fallback audit no longer contains `jlens`; the ledger record is
`native_promoted`, with the official route and both parser/live evidence refs.
The code-derived split is 496 registered, 384 native/live-backed, and 112
fallback-only providers; runtime fallback status counts are 8 blocked, 95 route
discovery, 3 non-executable, and 6 non-portfolio-publisher. The ledger has 67
queued fallback records remaining, with `knowledge_leaders` next. The known
unrelated F8p-current-history Study Lab histogram timeout remains the full
Docker integration blocker.

## 37. Current execution checkpoint — Knowledge Leaders/KNO native promotion — 2026-09-03

The ranked `knowledge_leaders` audit found an executable first-party route in
the official AXS Investments KNO product page and its declared FilePoint
iframe. AXS identifies KNO and CUSIP 46144X396; the FilePoint application
publishes the dated aggregate `BBH_AXS_ETF_PVAL_WEB.{YYYYMMDD}.csv` export.
The 2026-09-02 snapshot contains 83 KNO rows and a single composition date.

`KnowledgeLeadersHoldingsAdapter` validates both page and FilePoint hosts,
requires the declared schema, bounds date lookback to 15 days, filters the
multi-fund export to KNO, rejects mixed-date snapshots, preserves all available
identifiers and source fields, converts percentage weights, and explicitly
classifies cash and other-assets rows. The adapter records AXS Investments as
publisher and Knowledge Leaders Capital as strategy parent/originator. The
deterministic and bounded opt-in live tests cover route identity, date fallback,
filtering, mapping, provenance, and current row/classification behavior.

The runtime fallback audit no longer contains `knowledge_leaders`; its ledger
record is `native_promoted` with official route, parser fixture, and live
evidence references. The code-derived split is 496 registered, 385
native/live-backed, and 111 fallback-only providers; runtime statuses are 8
blocked, 94 route discovery, 3 non-executable, and 6 non-portfolio-publisher.
The ledger has 66 queued fallback records remaining, with `logiq` next. The
known unrelated F8p-current-history Study Lab histogram timeout remains the
Docker integration blocker.

## 38. Current execution checkpoint — Logiq/LCO native promotion — 2026-09-03

The ranked `logiq` audit found a complete executable first-party route on the
official LOGIQ ETF page at `https://logiqetf.com/`. The page identifies the
LOGIQ Contrarian Opportunities ETF (`LCO`) and declares both the fund-scoped
holdings download and static `TidalFG_Holdings_LCO.csv` export. The current
issuer CSV is dated 2026-09-02 and contains 86 LCO rows.

`LogiqHoldingsAdapter` subclasses the verified Tidal sponsor CSV path, adds
strict LOGIQ page identity and route-marker validation, enforces the static
issuer-domain CSV, requires at least 20 parsed rows, preserves CUSIPs,
quantities, market values, and percentage weights, and classifies CASH and
currency rows such as EUR as cash. It records LOGIQ ETF and LOGIQ Capital
Partners provenance and supports LCO only. Deterministic fixture coverage
exercises route declaration, source-domain checks, date and value parsing,
cash/currency classification, metadata, and unsupported symbols; bounded opt-in
live coverage exercises the current official route.

The runtime fallback audit no longer contains `logiq`; the ledger record is
`native_promoted` with official route, parser fixture, and live evidence refs.
The code-derived split is 496 registered, 386 native/live-backed, and 110
fallback-only providers; runtime statuses are 8 blocked, 93 route discovery, 3
non-executable, and 6 non-portfolio-publisher. The ledger has 65 queued
fallback records remaining, with `long_pond` next. The known unrelated
F8p-current-history Study Lab histogram timeout remains the Docker integration
blocker.

## 39. Current execution checkpoint — Long Pond/LPRE native promotion — 2026-09-03

The ranked `long_pond` audit found an executable first-party route in the
official Long Pond LPRE product page and its public CMS endpoint. The page at
`https://www.longpondetf.com/lpre` identifies the Long Pond Real Estate Select
ETF (`LPRE`) and declares a dated Holdings section. The CMS page route returns
the exact `longpond-lpre-HoldingsComponent-1` component and its six-column
holdings schema; the current 2026-09-01 payload contains 24 rows.

`LongPondHoldingsAdapter` validates the official product-page host and LPRE
identity, fetches the issuer CMS endpoint, validates the page/component/schema
identity, requires a complete dated payload, maps FIGI/ticker/quantity/value/
weight fields into canonical rows, and records Long Pond Capital / Exchange
Traded Concepts provenance. It does not reconstruct holdings through SEC
filings. The deterministic fixture covers the strict route and schema checks,
date/value/weight mapping, metadata, request sequence, and unsupported symbols;
the opt-in live test covers the current official route.

The runtime fallback audit no longer contains `long_pond`; its ledger record is
`native_promoted` with official route, parser fixture, and live evidence refs.
The code-derived split is 496 registered, 387 native/live-backed, and 109
fallback-only providers; runtime statuses are 8 blocked, 92 route discovery, 3
non-executable, and 6 non-portfolio-publisher. The ledger has 64 queued
fallback records remaining, with `lsv` next. The known unrelated F8p-current-
history Study Lab histogram timeout remains the Docker integration blocker.
## 40. Current execution checkpoint — LSV/LSVD native promotion — 2026-09-03

The ranked `lsv` audit found a complete executable first-party route on the
official LSV Asset Management product page at
`https://www.lsvasset.com/disciplined-value-etf/`. The page identifies the LSV
Disciplined Value ETF (`LSVD`), declares its 2026-09-01 holdings date, and links
the complete `https://www.lsvasset.com/ETFLive/LSVD-holdings.csv` export. The
current issuer file contains 136 rows and the exact Name, Ticker, ISIN, Number
of Shares, Market Value, and % of NAV schema.

`LsvHoldingsAdapter` validates the official page host and LSVD identity, requires
the page-declared CSV route and exact schema, converts percentage-point weights,
preserves ISIN/ticker/quantity/value fields, classifies Cash and the treasury-
obligations sweep rows as cash equivalents, and records LSV Asset Management /
The Advisors' Inner Circle Fund provenance. It does not reconstruct holdings
through SEC filings. The deterministic fixture covers route and schema checks,
date/value/weight mapping, cash classification, metadata, request routing, and
unsupported symbols; bounded opt-in live coverage exercises the current route.

The runtime fallback audit no longer contains `lsv`; its ledger record is
`native_promoted` with official route, parser fixture, and live evidence refs.
The code-derived split is 496 registered, 388 native/live-backed, and 108
fallback-only providers; runtime statuses are 8 blocked, 91 route discovery, 3
non-executable, and 6 non-portfolio-publisher. The ledger has 63 queued
fallback records remaining, with `m2_financial` next. The known unrelated
F8p-current-history Study Lab histogram timeout remains the Docker integration
blocker.
