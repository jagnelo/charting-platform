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
| Native/live-backed providers | 356 |
| Audited fallback-only providers | 140 |
| Native plus fallback | 496 |

The 140 fallback audits currently divide into:

| Audit status | Count |
|---|---:|
| `issuer_access_blocked` | 8 |
| `needs_first_party_route_discovery` | 123 |
| `non_executable_public_source` | 3 |
| `provider_not_a_portfolio_publisher` | 6 |

`docs/etf-provider-universe.md` still reports 339 native and 157 fallback. That
is stale evidence, not current truth. The first implementation checkpoint must
reconcile it from registry/audit structures.

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

## 16. Current execution checkpoint — 2026-09-02

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
whitespace checks pass. The separate durable operations checkpoint must record
the updated ledger, handoff, provider-universe counts, validation evidence,
and session next action before the next queue investigation.

The next ranked queue item is `everence`. Continue the same evidence loop:
inspect official product and holdings routes, promote only a complete
executable first-party source with strict identity and parser tests, otherwise
record a dated issuer-specific disposition. Docker-backed full integration is
not currently executable because the local Docker daemon/socket is unavailable;
this is an external validation gap, not permission to weaken the native-route
contract or to integrate the feature branch.
