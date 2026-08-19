# TC2000 Workstation Acceptance Governance

## 2026-08-19 — Generic breadth-to-Study-Lab reuse gate

The generic breadth acceptance contract now includes a direct save action: after evaluating a
user-authored predicate, the user can create an immutable Study Lab definition without converting
the universe to ticker text. The persisted asset must retain the exact predicate AST, canonical
source ID (including locked index/ETF sources), timeframe, adjustment, and as-of semantics. The
Python source is only a sandboxed SDK wrapper; it is never executed in the browser or FastAPI.

Focused payload tests pass `2/2`, full frontend Vitest passes `918/918`, and type/build checks pass.
This is an incremental reuse gate, not a waiver of the remaining target-specific promotion fan-out
or Version 25 promotion-visual gaps. No acceptance flexibility was used.

## 2026-08-19 — Full four-environment seeded visual matrix synchronized

The remaining display-scale projects were refreshed for the same deterministic seeded hydration
change: 80 images across four environments. Unchanged reruns pass `26/26` in each project,
`104/104` combined, with overlap checks, masks, and the 0.5% per-image threshold untouched.

Acceptance flexibility: **seeded fixture evidence for represented current product states only**.
It does not approve exact TC2000 V25 imagery or close canonical provider/history, entitlement,
unrepresented-state, or final whole-goal gates.

## 2026-08-19 — Seeded 1080p baseline refresh is explicitly interim evidence

The 1080p seeded visual project was stale after canonical fixture hydration changed the visible
constituent/industry and gap-state content. Twenty-two snapshots were refreshed, targeted reruns
passed `22/22`, and the unchanged full project passed `26/26`. This gate records a deterministic
product-state correction only: no screenshot masks, pixel thresholds, or exact-reference rules
were weakened.

Acceptance flexibility: **seeded fixture evidence for board-covered current states**. It does not
approve exact TC2000 V25 visuals, provider-backed universe/history completeness, or the unrun
125%/1440p projects; those remain tracked open gates.

## 2026-08-19 — Recursive Market Map and cross-tab handoff gate

The Market Map acceptance oracle now covers two repository-controlled correctness conditions:
recursive sector/industry rectangles must not interleave sibling groups, and a publication from a
map in one workspace tab must update the canonical Breadth/Study Lab window even when the active-tab
pointer is still settling. Layout `6/6`, authenticated handoff `1/1`, family matrix `4/4`, full
frontend `916/916`, type-check, and production build pass. The initial browser permission failure
occurred before product startup and was rerun with elevated browser permissions.

No acceptance flexibility was used. Exact Version 25 nested-map geometry and action-row visuals
remain a specifically recorded `required_missing` board gap; functional acceptance is not being
substituted for that visual track.

## 2026-08-19 — Top-down browser evidence uses explicit data modes

The seeded acceptance path now covers the trader's full top-down interaction sequence and the
eight-family map/breadth/rotation matrix. Fixture-dependent tests declare `E2E_SEED_MARKET_DATA=true`;
canonical provider tests require the separate `E2E_CANONICAL_MARKET_DATA=true` opt-in. This is a
test-oracle boundary, not a product shortcut: the default stack is identity-only and must expose
unavailable/stale coverage honestly. The canonical live-source gate remains open until a hydrated,
network-enabled free-source run passes. No acceptance flexibility was used.

## 2026-08-19 — Python comparison targets may use the prepared benchmark dataset

The recursive Python breadth condition editor now exposes an explicit right-side dataset choice:
the same member or the selected benchmark. Acceptance requires `right_scope` to be persisted in
the resolved immutable tree, a benchmark symbol to be declared when that scope is selected, and
the isolated runner to evaluate both series at the exact observation timestamp. Missing benchmark
bars must produce `python_series_benchmark_unavailable` and reduce eligibility; stale values must
not be forward-filled. Cross-sectional scope applies its group statistic only after the member /
benchmark comparison has been materialized. Focused runner coverage is `3/3` and editor coverage
is `9/9`; no acceptance flexibility was used. Exact Version 25 control geometry for this newly
represented state remains a `required_missing` board gap.

## 2026-08-19 — Boolean-column browser gate added

The Boolean-column promotion gate now has an authenticated end-to-end oracle for the previously
uncovered single-output path (`F8g-boolean-column`). It proves authoring, validation, isolated
execution, the dedicated typed-column action, return to the source workstation, and consumption
through the watchlist column editor. The first run launched Chromium successfully but stopped at
the environment boundary because the branch-scoped API was not listening (`ECONNREFUSED ::1:80`).
After `make test-stack-up` rebuilt, force-recreated, waited for, and migrated the branch stack, the
unchanged browser test passed `1/1` with no critical diagnostics. No implementation fallback or
acceptance relaxation was used.

## 2026-08-19 — Boolean Study results use a typed column promotion gate

The shared programmable-surface contract now permits a completed Study Lab Boolean artifact to be
promoted into a watchlist column. Acceptance requires all of the following: the source artifact is
Boolean; the created asset declares `kind=column` and `output_contract=boolean`; the frontend keeps
Boolean values typed rather than converting them to numeric flags; and immutable lineage records
the source run, source code version, reproducibility hash, dataset manifest, run configuration,
output name, target, and semantics. The column is then eligible for the ordinary list sorting,
pinning, filtering, and saved-column behavior.

This gate applies to both structured Boolean artifacts and single-output Boolean studies; the
latter receive a dedicated `kind=column` asset instead of reusing the executable study asset. The
lineage is metadata only and cannot be executed as user code. An aggregate, event, or
cross-sectional study that cannot provide a per-row Boolean contract must return a structured
capability error instead of being silently coerced. Focused evidence is Study Lab `24/24` and
Docker-backed API `2/2`; the unprivileged attempt was blocked only by the Docker socket boundary
and the unchanged elevated run passed. Acceptance flexibility used: **None**. Exact V25 action-row
visuals remain board-tracked as `required_missing`.

## 2026-08-19 — Scheduled family snapshots preserve the universal heatmap contract

Benchmark-family constituent sets remain locked, system-owned watchlists consumed by the same
Market Map as personal, combo, managed, sector, industry, ETF, and explicit lists. To make those
locked sources usable in a deployment rather than only in fixtures, an opt-in worker refreshes a
bounded set of completed month-end request dates for every configured family role and queues the
canonical member-bar history jobs for refreshed snapshots. These dates are maintenance boundaries,
not claims about an issuer's official rebalance calendar; adapters must preserve the latest evidenced
composition on or before the request and expose unavailable/failed roles explicitly.

The scheduler fans out deterministic one-family/one-date jobs (`_job_id` is stable and retries are
idempotent) so a slow free provider route cannot make the whole matrix one long worker invocation.
Each unit owns its provider transaction and exact snapshot-to-member-history queue handoff; a queue
or unit failure remains local evidence rather than suppressing the other family roots.

The scheduled path never runs from an interactive map/source read and does not add provider-specific
heatmap behavior. Its settings are `BENCHMARK_FAMILY_HOLDINGS_REFRESH_ENABLED` and bounded
`BENCHMARK_FAMILY_HOLDINGS_REFRESH_LOOKBACK_DATES`, both disabled/limited by default. Focused tests
cover date selection, disabled/enabled task behavior, member-history queueing, and worker
registration, one-unit fan-out, and queue handoff. Deployment population, complete point-in-time continuity, and exact V25 maintenance
visuals remain open acceptance gaps; no flexibility was used.

## 2026-08-19 — Bounded SEC maintenance must not starve family roles

The scheduled, unfiltered SEC holdings backfill must prioritize the canonical proxy symbols for all
configured benchmark families before spending its bounded ETF-profile budget on unrelated funds.
This priority is maintenance ordering only: explicit administrator symbol filters remain exact,
filing identity checks remain authoritative, and no missing membership is fabricated or substituted.
The source remains a locked, source-polymorphic watchlist and ordinary Market Map reads remain
provider-free.

The acceptance evidence is a bootstrap regression derived from `benchmark_family_proxy_symbols()`
plus the direct provider route matrix. It proves attempted family population, not successful
hydration: `5/5` focused SEC/task tests, `7/7` workstation-bootstrap tests, `1260/1260` backend
unit tests, `63/63` ETF-holdings integration tests, Ruff, compileall, and diff checks pass.
Acceptance flexibility used: **None**. Dated snapshot completeness, rebalance continuity,
point-in-time weights, canonical member bars, and V25 maintenance visuals remain tracked gaps.

## 2026-08-19 — Family roles must disclose canonical member-bar readiness

Family-role coverage acceptance has two separate evidence axes: dated holdings disclosure and
canonical adjusted member-bar readiness. The backend must report D1/W1/MN member counts with both
any-bar coverage and the analysis-ready floors (252/52/24 bars); the workstation must show the D1
covered-versus-ready distinction. A locked source may remain followable and selectable while
`pending` or `partial`, but it cannot be presented as technically complete. No provider calls are
allowed in this coverage read; hydration remains an explicit maintenance operation.

The regression uses a two-member snapshot where both members have bars but only one meets the D1
floor, and the rebuilt browser oracle verifies the visible readiness label. Workspaces `52/52`,
Watchlists `47/47`, backend units `1258/1258`, frontend Vitest `915/915`, focused Chromium `1/1`,
type/build, Ruff, compileall, and diff checks pass. Acceptance flexibility used: **None**. Exact
V25 coverage-row copy/geometry is still board-tracked where unrepresented; data population and
complete historical member bars remain implementation gaps, not waived criteria.

## 2026-08-19 — Historical Market Map records require observation and knowledge cutoffs

For a historical Market Map over any locked index/ETF watchlist or arbitrary source, a profile
snapshot is eligible only when both its provider observation date and its local `fetched_at` date
are on or before the requested `end`/`as_of`. This prevents an observation backfilled later from
changing an earlier heatmap's area, sector, or industry grouping. The rule is enforced in the
shared backend source contract and is independent of whether the source is editable or locked.

The regression intentionally includes an old observation fetched after the evaluation date; it is
excluded and the earlier known snapshot remains visible. Focused Market Map unit `5/5`, Docker-
backed watchlist integration `47/47`, full backend units `1258/1258`, Ruff, compileall, and diff
checks pass. Acceptance flexibility used: **None**. The exact V25 warning/hover presentation is
still `required_missing` where the reference board has no authoritative capture.

## 2026-08-19 — Source-polymorphic Market Map and historical classification gate

The acceptance model treats an index/index-ETF constituent universe as a locked, platform-owned
watchlist, not as a separate heatmap product. Arbitrary personal, combo, explicit, sector,
industry, managed, ETF, and index sources must use the same Market Map contract; only membership
mutation permissions differ. This is a functional invariant and is covered separately from exact
Version 25 visual parity.

For historical system-managed maps, current classification metadata is not an acceptable hidden
fallback. The backend must use a profile snapshot observed at or before the requested evaluation
time, return its provenance, and mark absent evidence as `Unclassified` with a structured warning.
The frontend must expose that provenance in the member detail. No acceptance flexibility was used
for this gate. The reference board does not yet contain an authoritative exact-build capture of
the provenance detail, so its geometry/copy remains a tracked `required_missing` visual state.

## 2026-08-19 — Repeated Market Map close/reopen must preserve the workstation

The family acceptance gate now opens and closes the universal Market Map for every configured US
benchmark root. A close is accepted only when the serializable layout remains valid, the surviving
stack has a valid active tab, the host reinstalls without a Golden Layout exception, and the next
family can be opened through the same source-polymorphic action. The current rebuilt Chromium gate
passes `2/2`; the host component gate is `8/8`; full frontend Vitest is `915/915`; type-check,
build, and diff-check pass. Acceptance flexibility used: **None**.

The test-only ETF snapshot payload is a deterministic fixture to isolate the family source/action
contract. It does not claim provider-backed holdings completeness. Exact V25 close/action geometry,
provider-backed family population, point-in-time weights, canonical member-bar history, combo
version reconstruction, and the final visual-board audit remain explicitly open.

## 2026-08-19 — Downstream tools must disclose selected-source lineage

When a Market Map selection is handed into Study Lab, the receiving tool must show selected member
count, locked explicit-source semantics, parent source ID, and exact canonical explicit source ID.
The editable universe-source control must remain the explicit source and must not be replaced with
the parent or active symbol. The current component gate is `24/24`, and the full frontend gate is
`906/906` with type-check/build/diff-check green. No acceptance flexibility was used. Exact V25
badge geometry and durable explicit-source catalog persistence remain tracked gaps.

## 2026-08-19 — Selected-source handoffs must retain canonical subset identity

The universal-watchlist acceptance gate now covers both a source-wide and a selection-scoped
Market Map handoff. Source-wide actions retain the locked/index/ETF/personal/combo source ID;
selection actions must deduplicate valid canonical instrument IDs and publish an explicit source
without changing the parent membership. Breadth and Study Lab must retain parent source lineage,
scope, selected IDs/symbols, and publication origin, and Breadth must keep an observable synthetic
locked selector entry for an ephemeral explicit source. If a subset is too large for the explicit
identity bound, the UI must preserve the parent source and instruct the user to save a personal
watchlist rather than silently truncating it.

Focused component/helper gates are `29/29` and `3/3`; authenticated Chromium
`F8s-market-map-watchlist` is `1/1`; full frontend Vitest is `905/905`; type-check/build/
diff-check pass. A first browser assertion assumed the wrong tile ordering (`explicit:1`); the
product correctly published the selected tile's canonical ID (`explicit:2`), and the assertion
was corrected to verify the canonical explicit shape and one-member label. This is a localized
test repair under the fix-first tie-break, not acceptance flexibility. Exact V25 selected-action
geometry and durable explicit-source persistence remain `required_missing`/open.

## 2026-08-19 — Locked-source clone conflicts must be recoverable, not blocking

The universal watchlist acceptance gate requires clone membership writes to be sequential and
observable. A recoverable conflict may leave a personal snapshot partially populated, but the UI
must disclose `completed/total`, retain failed canonical IDs, and expose a retry that writes only
those IDs. Successful writes must not be duplicated; the immutable source, membership version,
composition/effective/known-at lineage, and source selection must remain unchanged. The focused
unit gate is `29/29`; authenticated Chromium `F8s-market-map-watchlist` is `1/1`, including a
conflict followed by retry; full frontend Vitest is `902/902`. The browser diagnostic whitelist is
limited to the one intentionally injected handled 409; unrelated console/request failures remain
fatal. Exact V25 retry geometry/copy and provider-backed source history are still open. Acceptance
flexibility used: **None**.

## 2026-08-19 — Clone locked sources only from canonical resolved membership

The universal watchlist contract now includes a durable `Clone snapshot` operation. The source
resolver is authoritative: the UI must obtain the complete canonical member set (with a
composition-date `as_of` when available) before creating a personal copy. A map response with
missing bars or zero resolved members cannot produce a partial clone. The clone description keeps
membership/effective/known/composition lineage so the user can audit what was copied.

Tie-break evidence: the first browser fixture failed because its encoded source path returned the
wrong payload; the product correctly stopped rather than cloning an empty set. The fixture was
fixed at its boundary and the unchanged rerun passed. Unit `28/28`, browser `1/1`, full Vitest
`901/901`, type-check/build/diff-check pass. Exact V25 action geometry, conflict/retry visuals,
provider-backed history, and all-family population remain acceptance gaps. Acceptance flexibility:
**None**.

## 2026-08-19 — Role-aware locked-watchlist Map handoff

The benchmark-family Map control is now governed as a role-aware locked-watchlist handoff. The
selected family role is part of the canonical source identity, so equal/value/growth cannot be
collapsed into the cap-weight source or reconstructed from a ticker. A role may be selected only
when the overview reports an available symbol and verified holdings evidence; otherwise it remains
visible as unavailable and the action is rejected. This is the tie-break for ambiguous role data:
preserve the explicit unavailable state and fix the owning data/contract boundary before adding a
fallback.

The rebuilt authenticated equal-weight flow passes `F8s-family-map-drilldown` `1/1`, with full
frontend Vitest `900/900`, type-check, build, and diff-check green. This does not waive provider,
point-in-time, historical, or exact V25 visual criteria. Required follow-up remains role-member
population and the missing selector/disabled-state visual references. Acceptance flexibility used:
**None**.

## 2026-08-19 — Eight-root family entry oracle

Authenticated Chromium `F8s-family-matrix` passes `1/1` across all eight required US benchmark
roots. It verifies each canonical official-index/tradable-proxy identity and opens the Nasdaq 100
locked cap constituent source through the shared Market Map. The first fixture used guessed
`SP1500`/`RUT` identities; the browser failure led to the authoritative `SPSUPX`/`RTY` correction
before the unchanged rerun passed. This is a recorded fix, not acceptance flexibility.

The oracle covers family entry and source identity only. It does not prove provider-backed member
bars, historical continuity, style-role evidence, or every family-specific breadth/ratio/rotation/
Study Lab/reuse surface. Those remain explicit acceptance gaps.

## 2026-08-19 — Browser and provider evidence for the one-watchlist heatmap oracle

The functional oracle now includes authenticated Chromium coverage (`F8s-market-map-watchlist`,
`1/1`) for a locked index/benchmark-style source and an editable personal source using one Market
Map request/renderer. Public issuer/SEC route probes pass `32/32` for mapped issuer-direct legs and
`10/10` for QQQE plus dated fallback cases. The complete 406-case adapter sweep is `398 passed,
1 skipped, 7 failed` on isolated non-core external endpoints; these remain explicit adapter-quality
gaps. Frontend type-check, Vitest `900/900`, build, and diff-check pass.
The companion authenticated family drill-down oracle also passes `1/1`, selecting S&P 500 and
opening its canonical locked cap-weight constituent source. A missing `freshness` fixture field
was fixed after the browser exposed the malformed-response crash path; no product fallback was
used.

This evidence does not approve exact V25 pixels and does not prove database ingestion or historical
truth. Exact source-picker geometry, all-root population/member bars, point-in-time rebalance
continuity, and family-role browser drill-down remain explicit open criteria. Acceptance
flexibility used: **None**; no visual threshold, mask, provider requirement, or source semantics
were relaxed. Mapped-family route evidence is positive but bounded; it does not make the full
provider adapter suite green or prove all-root database population.

## 2026-08-19 — One heatmap oracle for arbitrary and locked watchlists

The acceptance contract does not permit an index or ETF constituent heatmap to become a special-case
renderer. The same Market Map behavior must work for any canonical source; `locked` controls
membership mutation only. Follow/pin are user preferences and must never create, delete, or rewrite
the locked constituent source. Backend source identity, membership version, point-in-time policy,
provenance, freshness, exclusions, and coverage must survive the handoff.

The current functional oracle is backend integration `4/4` across personal, locked market-group,
ETF-holdings, and combo sources plus frontend `900/900`. Acceptance flexibility used: **None**.
Exact V25 source-picker visuals and authenticated browser proof remain tracked gaps rather than being
silently inferred from unit coverage.

## 2026-08-19 — Family role drill-down must preserve role-specific source identity

When a selected benchmark-family role row has a verified, holdings-backed mapping, its desktop
context menu must publish `benchmark-family:<family>:<role>` to Market Map. The action must preserve
the locked source's membership/version/provenance semantics and must not reconstruct a universe
from the row ticker. If the mapping is unverified, unavailable, or has no holdings evidence, the
action is absent and the role's explicit unavailable state remains visible; no other role is used.

Focused row/source validation is `70/70`; full frontend Vitest is `900/900`; type-check,
production build, and diff checks pass. Acceptance flexibility used: **None**. Exact V25 context
menu visuals, browser role drill-down, provider-backed holdings/history, and visual references
remain open.

## 2026-08-19 — Benchmark-family Map handoff must preserve constituent semantics

When the authenticated benchmark-list is switched to a family root, its Map action must open a
locked constituent WatchlistSource, not the family group containing the cap/equal/value/growth
proxy instruments. The accepted source identity is `benchmark-family:<family>:cap_weight` for the
default root action; role-specific equal/value/growth identities are reserved for explicit role
actions and must remain unavailable when their holdings evidence is absent. The source resolver,
Market Map, breadth, history, and linked-analysis contracts remain shared with arbitrary
watchlists. No ticker-only reconstruction or silent fallback is permitted.

Focused source/list/map validation is `164/164`; full frontend Vitest is `899/899`; type-check,
production build, and diff checks pass. Acceptance flexibility used: **None**. Exact V25 handoff
geometry, role-specific actions, provider-backed holdings, historical continuity, and browser
drill-down remain open acceptance gaps.

## 2026-08-19 — Study Lab promotion cannot widen its declared universe

Generic Study Lab Boolean promotion is accepted only when the completed run contains canonical
member IDs in its materialized dataset. The workstation must create a `custom` EasyScan over the
deduplicated declared IDs, preserve the source run/code version, reproducibility hash, source
universe ID, membership version, source IDs, and explicit current-data re-evaluation semantics in
condition provenance, and retain the selected timeframe. If no canonical IDs are present, the
workstation must refuse promotion and show a structured recovery message; it must never silently
use `all` or reconstruct membership from ticker text. The backend applies the same guard to
external `study_run_promotion` requests.

This is a lineage/safety gate, not a claim that promotion preserves a historical point-in-time
snapshot: the promoted EasyScan evaluates current canonical data over the fixed declared members,
and `point_in_time_source_preserved` is explicitly false. Focused Study Lab coverage is `23/23`
and the screener integration suite is `26/26`; frontend full Vitest is `894/894`; type-check,
production build, Ruff, compileall, and diff checks pass. No acceptance flexibility was used.
The board still lacks an authoritative exact V25 promotion/source-lineage capture, and broader
historical snapshot promotion, output-target fan-out, provider completeness, and exact V25 parity
remain open.

## 2026-08-19 — Large-universe Market Map rendering gate

The universal heatmap must not create row-count-proportional Vue tile DOM for large arbitrary
watchlists. For more than 1,500 valid cells, acceptance requires one canvas-backed map using the
same canonical source ID, membership version, deterministic layout, colour/area coverage,
freshness, provenance, and warning contract as the normal DOM-backed view. The canvas must paint
all valid geometry, preserve hover/detail and selected-member publication, keep zoom/pan usable,
and suppress selection after a drag. A compact symbol/name search must provide keyboard selection;
the canvas member-count label and hover card are the summary/detail accessibility oracle rather
than an unbounded hidden options list.

The focused regression proves a 10,000-member response creates zero `.market-map-tool__tile`
elements, invokes canvas painting, retains the accessible member count, rejects a drag-click, and
selects a member through the keyboard search. Market Map is `26/26`; full frontend Vitest is
`893/893`; type-check/build/diff checks pass. The board has no authoritative V25 large-universe
capture, canvas/text-density treatment, or keyboard-search reference; those remain
`required_missing` visual gaps. This gate does not relax visual thresholds and does not prove
interactive/soak stress beyond the bounded 10,000-member regression, provider-backed family
completeness, historical reconciliation, or exact V25 parity.

## 2026-08-19 — Universal watchlist-to-heatmap launch gate

The heatmap is accepted as a universal watchlist surface, not an index-only feature. A virtual
watchlist may expose `Map` only with a canonical source contract. Durable personal, combo,
ETF-holdings, benchmark-family, and market-group sources must be passed unchanged; their resolved
descriptor remains the authority for locked membership, provenance, membership version, coverage,
freshness, and point-in-time behavior. A filtered constituent, proxy, or flagged view may use a
locked explicit canonical-ID source, but it must never rebuild the universe from ticker text or
silently claim the parent ETF/index membership. Opening the tool must persist the source override
before rendering and must leave the source available for the same history, breadth, Python, export,
and linked-analysis contracts as a manually selected source.

The focused virtual-watchlist and workspace-store regressions are `66/66` and `67/67`; full
frontend Vitest is `892/892`; type-check/build/diff checks pass. No acceptance flexibility,
provider substitution, or interactive provider fan-out was used. The board lacks an authoritative
V25 capture for the exact list-level action geometry, handoff copy, and explicit-subset locked
state; those remain a `required_missing` visual gap. This gate does not close provider-backed
family population, historical reconciliation, or large-list map rendering.

## 2026-08-19 — Family snapshot hydration must use the exact snapshot boundary

When a provider-backed holdings run succeeds, acceptance requires the worker to queue canonical
member history from the refreshed snapshot IDs, not by resolving the public source with the old
composition date as `as_of` (the snapshot was learned now and must not leak backward in time).
Queue evidence must retain available/selected/limited/unresolved counts and queue errors per unit.
All canonical history paths must share one deterministic job identity so overlapping personal,
locked index/ETF, bootstrap, and family refreshes deduplicate instead of creating parallel fetches.

The service/worker/bootstrap suite is `21/21`, the Docker-backed generic refresh regression is
`1/1`, backend units are `1236/1236`, and Ruff/compileall/diff checks pass. This gate proves the
handoff and idempotence contract only; provider route completeness, all-root historical truth,
entitlements, large-list rendering, and exact V25 maintenance/progress visuals remain open. No
acceptance flexibility was used.

## 2026-08-19 — Family holdings maintenance must be durable and cancellable

The provider-backed holdings maintenance gate now requires a persisted admin run before any
provider call. The run must retain normalized family/role/date scope, total and completed units,
per-unit results, refreshed/unavailable/failed counts, cancellation, and terminal state. Worker
execution is one date/family unit at a time, commits progress after each unit, isolates failures,
and observes cancellation between units. Status and cancellation must not fan out to providers;
interactive workstation reads must remain provider-neutral.

The focused planner/worker suite is `16/16`, worker regressions are `13/13`, the Docker-backed
create/status/cancel regression is `1/1`, ETF holdings integration is `63/63`, backend units are
`1234/1234`, and Ruff/compileall/diff checks pass. No acceptance flexibility was used. The local
configured database was unreachable for direct Alembic current/round-trip evidence; disposable
integration migrations passed, so live migration round-trip remains an environment gap rather than
a product claim. Durable orchestration does not close provider route completeness, official
membership/rebalance evidence, all-root population, or exact V25 maintenance visuals.

## 2026-08-19 — Continuity cannot be inferred from snapshot availability

The family-history acceptance gate now requires separate evidence for snapshot availability and
observed disclosure continuity. The coverage endpoint must collapse same-date revisions, honour
the requested `as_of`, report exact intervals wider than the declared 45-day diagnostic policy,
and identify a response window that reached its snapshot limit. `gapped` means only that returned
composition dates are widely spaced; it is not a claim that an issuer owes a disclosure on every
missing date. `coverage` remains the fraction of mapped roles with at least one snapshot and must
not be reinterpreted as a continuity score.

The workstation must show these states and preserve the warning/provenance lineage. Older clients
may omit the optional fields, but new clients must not hide them. Focused logic is `6/6`, the
Docker-backed endpoint regression is `1/1`, backend units are `1229/1229`, frontend Vitest is
`889/889`, and type/build, Ruff, compileall, and diff checks pass. No acceptance flexibility was
used. This closes a visibility gap only; provider-backed family population, historical
reconciliation, all-root acceptance, and exact V25 maintenance/progress visuals remain open.

## 2026-08-19 — Durable refresh-run and arbitrary-watchlist heatmap gate

The heatmap acceptance oracle remains source-polymorphic: an index/index-ETF constituent set is a
locked system-managed watchlist, not a separate visualization. It must use the same source ID,
membership-version, point-in-time, coverage, provenance, freshness, map, breadth, and linked-chart
contracts as a personal or combo watchlist; only membership editing differs. Any explicit history
hydration request must create a user-owned durable run containing the resolved source IDs, versions,
selected canonical IDs, timeframes, cutoff, bound, queue counts, and errors. Status is readable only
by the owner, aggregates existing local worker progress, and never starts a provider request.

Cancellation must persist even during Redis outage and must signal active worker jobs before and
between timeframe calls. Shared deterministic per-instrument jobs remain idempotent; an
`already_queued` job owned by an earlier run is not silently claimed as cancelable by a later run.
The response and acceptance evidence must retain that limitation. Focused durable-run/worker tests,
full watchlist integration `44/44`, backend unit suite `1223/1223`, Ruff, compileall, and diff checks
are required for this gate. No visual threshold, mask, provider entitlement, or exact-build V25
criterion is relaxed; exact V25 maintenance/progress visuals and provider-backed historical
continuity remain open.

## 2026-08-19 — Core bootstrap hands holdings into canonical member-history hydration

When the opt-in core workstation bootstrap is enabled, acceptance must verify that it commits the
provider-backed ETF-holdings snapshots before resolving the locked
`benchmark-family:<family>:<role>` sources and queueing canonical MN/W1/D1 member-history jobs.
The bootstrap result must preserve queued/already-queued counts, truncation, selected/available
counts, and per-leg availability. No interactive Market Map, breadth, chart, or watchlist read may
invoke this provider path. The source-level history-status endpoint remains the observation surface
for local coverage and worker progress.

The workstation-bootstrap/worker suite passes `15/15`, full backend units pass `1222/1222`, and
Ruff, compileall, and diff checks pass. No acceptance flexibility was used. This gate proves only
the committed handoff and queue lineage; provider route completeness, all eight family/role
membership and bar population, historical rebalance continuity, durable cancellation, entitlement
reconciliation, all-root acceptance, and exact Version 25 maintenance/progress visuals remain
substantive open gaps.

## 2026-08-19 — Source-level heatmap readiness and progress is explicit

### Market Map timeframe gate

The Market Map timeframe selector must accept Daily (`D1`), Weekly (`W1`), and Monthly (`MN`) for
any canonical source. The chosen value must be present in the serializable tool configuration,
batch-map request, history-status/refresh request, isolated Python run, reusable definition, and
snapshot restoration. Changing it must clear stale history-run state and re-read local readiness;
it must not mutate membership or invoke a provider from the browser. The focused component,
backend Market Map unit, full frontend, type/build, and diff gates are required.

The board has no authoritative V25 capture for this selector's geometry/copy or loading treatment,
so those states remain an explicit `required_missing` visual gap. This is not acceptance flexibility
and does not relax provider, point-in-time, large-list, or exact visual requirements.

### Market Map actionability gate

The source-level readiness contract must be visible in the workstation, not only available through
an API. When a Market Map has a canonical source selected, the tool must show its local adjusted-
OHLCV readiness (`pending`, `partial`, `fetching`, `failed`, `ready`, or `unavailable`), covered
member counts, and any hard bound/truncation. It must offer an explicit bounded Refresh history
action that posts the same source ID without changing locked membership. While work is pending or
fetching, the tool may poll the provider-free status endpoint; changing source or destroying the
tool must stop polling. Queue failures and stale/partial coverage remain visible rather than being
presented as complete data.

The component gate proves the exact request payload, queue-count feedback, locked-source label,
and partial-status rendering. Frontend Vitest `890/890`, type-check/build, and diff checks are
required. This gate does not relax the visual board or data-quality criteria: exact V25 maintenance
geometry, provider-backed population, canonical history continuity, and large-list performance
remain open and must be tracked explicitly.

### Durable refresh progress gate

When Refresh history returns a durable run ID, Market Map must expose that run's owner-scoped
status and bounded completed-versus-selected progress and must offer Cancel refresh while the run
is queued or running. The cancel action may signal worker cancellation, but must retain cached bars
and must never mutate a locked source's membership. Queue-unavailable, already-queued, failed, and
canceled outcomes are explicit. Polling stops on cancellation, terminal run state, source change,
or tool teardown. This status supplements (and never replaces) source-level local coverage.

The regression must prove the run-status lookup and exact cancel payload. Frontend Vitest `890/890`,
type-check/build, and diff checks are required. This gate does not relax provider completeness,
point-in-time reconciliation, large-list performance, or visual-board acceptance.

The universal locked-watchlist gate now includes source-level history readiness. For every
canonical source ID, `GET /api/v1/watchlists/sources/history-status/{source_id}` must use the
same point-in-time membership resolver as Market Map, breadth, and explicit history refresh, and
must expose the source's membership version/locked state, exclusions, truncation, adjusted-OHLCV
coverage, and per-timeframe worker progress. The response must classify the source as `pending`,
`partial`, `fetching`, `failed`, `ready`, or `unavailable` without provider calls. A locked
index/ETF/sector/industry source is therefore a non-editable membership watchlist, not a separate
heatmap implementation; the same contract applies to personal, managed, combo, and explicit
canonical lists.

The focused status unit suite passes `4/4`, the Docker-backed endpoint regression passes `1/1`,
complete watchlist integration passes `44/44`, and full backend units pass `1221/1221`, with Ruff,
formatting, compileall, and diff checks passing. This closes readiness visibility only. Durable
refresh-run identity/cancellation, provider-backed membership and bar population for all eight
families/roles, historical composition continuity, entitlement reconciliation, all-root
acceptance, and exact Version 25 maintenance/progress visuals remain open and must not be hidden
behind the relaxed status contract.

## 2026-08-19 — Source-polymorphic history maintenance is explicit

Every canonical watchlist source used by the workstation may be hydrated only through an explicit
bounded maintenance request. `POST /api/v1/watchlists/sources/history-refresh` resolves personal,
managed, index, ETF-holdings, benchmark-family, combo, and explicit sources using the same
user-scoped point-in-time resolver as Market Map and breadth. The response preserves membership
versions, locked state, exclusions, unavailable sources, deduplicated counts, `as_of`, queue
failures, duplicate jobs, and truncation. The API queues the existing provider-neutral worker;
it never makes a provider call during an interactive map, breadth, grid, or chart read.

The source planner/unit and Docker-backed queue regression pass, as do the complete watchlist and
ETF holdings integration files, full backend units, Ruff, compileall, and diff checks. No
acceptance flexibility was used. Provider-backed membership/bar continuity, historical
reconciliation, durable progress/cancellation, entitlements, and exact V25 maintenance visuals
remain open and must not be inferred from a successful queue response.

## 2026-08-19 — Family constituent history hydration is explicit and bounded

Locked index/index-ETF constituent watchlists are system-managed sources, not editable personal
lists, but they must still be maintainable as data universes. The admin history-refresh contract
resolves only locally evidenced membership, uses the same source IDs and point-in-time resolver as
interactive Market Map/breadth, deduplicates overlapping roots/roles, and refuses unknown roots,
roles, timeframes, or over-limit requests. It queues existing bulk-history jobs rather than making
provider calls in the API request. Empty, unavailable, excluded, truncated, already-queued, and
queue-failure outcomes remain visible in the response.

The planner and API regressions pass, full backend units pass `1217/1217`, and the complete ETF
holdings API file passes `62/62` under the Docker-backed environment. No visual threshold, mask,
provider entitlement, or acceptance rule was relaxed. The remaining gap is substantive rather than
semantic: all roots still need real provider-backed membership/bar continuity and historical
reconciliation, and the exact V25 maintenance/progress presentation is not yet board-approved.

## 2026-08-19 — YTD consistency across top-down views

Every shared family/ranking/technical YTD cell and historical return point must use the latest
aligned observation strictly before the current calendar-year boundary. If it does not exist, the
result is `insufficient_ytd_history`; a first-in-year close, forward-filled value, or provider read
is forbidden. This is the same rule already required by `/analysis/market-map`, so switching between
heatmaps, role rankings, breadth companion views, and linked charts cannot change the denominator.

The focused analysis-router suite is `20/20`, full backend units are `1215/1215`, and the affected
Docker-backed watchlist/Market Map integration is `42/42`. No acceptance flexibility, threshold,
mask, or provider entitlement was changed. Exact V25 YTD selector/baseline disclosure remains a
reference-board gap.

## 2026-08-19 — Calendar-period Market Map return contract

For `MTD` and `YTD`, the shared Market Map must use the most recent covered session strictly before
the calendar month/year boundary as the denominator. The boundary shown in response metadata is
still the requested calendar start. If that prior session is absent, the cell is excluded with
`insufficient_history`; the evaluator must not quietly use the first in-window bar, forward-fill,
or ask a provider during an interactive read. This rule is source-polymorphic and therefore covers
arbitrary personal lists, locked index/ETF universes, combos, and explicit canonical selections.

Unit coverage is `5/5` for the period helper, the Docker-backed watchlist/Market Map integration is
`42/42`, and full backend units are `1214/1214`. No threshold, mask, provider entitlement, or
acceptance criterion was relaxed. Exact V25 period selector, calendar-boundary, and insufficient
history visuals remain a tracked reference-board gap.

## 2026-08-18 — Historical Relative Rotation semantics

`history_length` is an optional bounded request/configuration field from `0` through `1000`.
`0` keeps the existing lightweight tail-only behavior; a positive value returns the latest
available rotation coordinates after exact timestamp alignment and the requested `as_of` cutoff.
The service does not forward-fill a missing ratio leg, and it returns the existing coverage and
warning lineage when points are unavailable. `history_length` is part of the request/cache and
workspace configuration lineage, and the UI must not silently truncate a user value beyond the
declared bound.

The interim functional oracle is backend integration `2/2`, complete watchlist/workspace analysis
`91/91`, frontend component `8/8`, full Vitest `889/889`, type/build, and rebuilt-stack browser
`F8s-rotation-family 1/1`. No acceptance flexibility was used. Exact Version 25 history/tail
control measurements and long-curve visual baselines remain tracked until the reference board
contains an authoritative state.

## 2026-08-18 — Provider disagreements must be visible, not silently resolved

For Market Map numeric area fields, each provider's latest field-bearing persisted snapshot at the
evaluation timestamp is a candidate. Provider entitlement/precedence still determines the displayed
value, but a material disagreement (more than the declared one-percent relative tolerance) must be
retained in cell provenance with candidate IDs, providers, values, observation times, spread, and
resolution policy, and must produce a cell and response warning. A new candidate must alter cache
identity. No provider call, averaging, silent fallback, or hidden conflict is acceptable.

The provider-precedence integration regression, helper tests `2/2`, and complete watchlist/workspace
suite `91/91` pass, with Ruff, compileall, and diff checks. This is a repository-controlled
completion with no acceptance flexibility. Broader provider reconciliation and exact V25 conflict
visual treatment remain explicit gaps.

## 2026-08-18 — Cached holdings must retain provider-quality state

Every locked ETF/index-proxy source must expose both its local holdings usability and its adapter
route state. The descriptor and family coverage response must retain adapter key, status,
confidence, snapshot source quality, completeness, row/resolution counts, total weight, and
published-at evidence. A cached snapshot remains selectable when a later provider attempt fails,
but the failure status must remain visible to downstream freshness/error presentation; no read may
probe a provider or silently replace the source.

The focused source/coverage tests pass 2/2, and the complete watchlist/workspace analysis suites
pass 91/91. This is a repository-controlled contract completion with no acceptance flexibility;
provider entitlement policy, historical reconciliation, and exact V25 status visuals remain gaps.

## 2026-08-18 — Known-at tie-break is mandatory for same-date holdings revisions

For every locked ETF/index-proxy source, historical resolution must select the latest snapshot
whose composition date and known-at timestamp are both eligible for the evaluation time. When
multiple eligible snapshots share a composition date, known-at is the authoritative tie-break;
database insertion order is only the final deterministic fallback. The Market Map regression
proves an earlier evaluation receives the 0.25 early-known revision and a later evaluation
receives the 0.75 late-known revision. The complete watchlist integration file passes 42/42.

This is a repository-controlled data-integrity repair, not acceptance flexibility. Provider route
quality, complete historical population, and exact V25 revision visuals remain separate gaps.

## 2026-08-19 — Locked Market Map availability is source-polymorphic

The locked-watchlist contract applies the same availability semantics to ordinary market-group
and ETF-holdings sources as to benchmark-family legs. A populated source reports `available`;
an empty group reports `membership_not_loaded`; and an ETF profile without a holdings snapshot
reports `holdings_snapshot_not_loaded`. The shared picker keeps each source visible for audit,
labels it `Unavailable`, disables it, and never substitutes another universe.

The Docker-backed descriptor/API pair passes `2/2`; focused Market Map `24/24`, full frontend
Vitest `888/888`, type-check, production build, Ruff, compileall, and diff checks pass. No
acceptance flexibility was used. Provider entitlement/quality reconciliation, historical
snapshot continuity, and exact V25 availability badges/copy/geometry remain tracked gaps.

## 2026-08-19 — Unavailable family-source picker state

The universal locked-watchlist acceptance must keep missing benchmark-family roles visible and
auditable, while preventing accidental use as if they had data. Market Map options with canonical
availability `unavailable`, `profile_not_loaded`, or `holdings_snapshot_not_loaded` are labelled
`Unavailable` and disabled; the source is not removed and no substitute is selected. An available
source is preferred on initial load. This is a fix-first implementation of a local UI defect, not
a relaxation of the missing-data contract.

Focused Market Map `24/24`, full frontend Vitest `888/888`, type-check, production build, and diff
checks are the interim functional oracle. No acceptance flexibility was used. Exact Version 25
unavailable-role copy, badges, disabled geometry, and provider-backed population remain tracked
gaps.

## 2026-08-19 — Family-leg Python Market Map source handoff

The universal locked-watchlist acceptance includes Python-backed Market Map colour/area outputs,
not only built-in metrics. A `benchmark-family:<family>:<role>` source must reach the isolated
runner as `kind=watchlist` with its canonical source ID and point-in-time policy, exactly like the
other source kinds. The focused component regression and full frontend suite are the interim
oracle for this handoff. The local omission that rejected family-leg Python maps was repaired;
it was a code defect under repository control, not a semantic ambiguity or acceptance waiver.

No acceptance flexibility was used. Provider-backed family population, historical continuity,
promotion fan-out, and exact Version 25 source-picker/derived-weight/unavailable visuals remain
tracked gaps.

## 2026-08-19 — QQQE historical-route sub-gate

The QQQE equal-weight leg must resolve its Direxion trust/series/class identity explicitly and
must use SEC EDGAR for dated requests. The live sub-gate requires a substantial parseable filing,
SEC source/provider provenance, a requested cutoff, the latest-filing-at-or-before policy, and a
composition date no later than the cutoff. The current daily Direxion CSV remains a separate
current-data route. Passing this sub-gate does not relax daily membership, exact rebalance, index
truth, provider-population, or Version 25 visual requirements.

## 2026-08-19 — Live SEC route evidence sub-gate

The QQQ historical fallback has a separate opt-in live sub-gate. The unchanged elevated probe must
return a substantial parseable portfolio and prove SEC source/provider, requested cutoff,
latest-filing-at-or-before policy, and a composition date not later than the cutoff. DNS or
network sandbox failures are execution-environment evidence and require an unchanged elevated
rerun; they must not be converted into a skipped product assertion. Passing this gate still does
not waive daily holdings, exact rebalance, official-membership, or Version 25 source-disclosure
requirements.

## 2026-08-19 — Historical holdings route sub-gate

The QQQ dated-holdings path is accepted only as a labelled SEC filing reconstruction. The
adapter must pass the requested cutoff into SEC filing discovery, preserve source and policy
metadata, and fail explicitly when no filing is known at or before that cutoff. This sub-gate does
not relax the broader acceptance requirement for daily composition continuity, exact rebalance
weights, or official index-membership truth; those remain tracked gaps and must not be represented
as if this fallback closed them.

## 2026-08-19 — Identity-first family-route sub-gate

Before a configured benchmark-family role is considered refreshable, acceptance must resolve its
canonical symbol metadata to a registered holdings adapter explicitly. The matrix test must
iterate all four roles for all eight roots: a mapped role requires an issuer, explicit adapter,
and registered adapter class; a missing role requires `verification_state=not_verified` and must
remain unavailable. This prevents a working-looking route from depending on weak issuer/name
inference or silently borrowing another family.

The current oracle passes `20` mapped and `12` unavailable cells, the complete ETF holdings
integration file passes `61/61`, and the opt-in QQQ live route selection passes `3/3`. The live
result is deliberately bounded to current route reachability/parseability; it does not close
historical QQQ/QQQE weighting, rebalance, official-index membership, or exact Version 25 route
status visuals. No acceptance flexibility was used.

## 2026-08-19 — Bulk population sub-gate for universal locked family watchlists

The provider-population acceptance must be able to invoke the admin-only bulk refresh contract for
all eight benchmark roots and for a bounded historical date range. It must verify deterministic
family/role ordering, duplicate removal, the eight-family/64-date bounds, snapshot/composition
lineage, and independent `refreshed`, `unavailable`, `route_not_ready`, and `failed` outcomes.
Injecting one family/issuer failure must leave the other family attempts and their committed
results intact; no route may substitute another family, ticker, or provider. This endpoint is an
administrative/backfill path only: ordinary Market Map/watchlist reads must remain local and must
not perform one provider request per tile/member.

The interim oracle is the complete ETF holdings integration file (`61/61`) plus the affected
Market Map/workstation integration suites (`90/90`), Ruff, formatting, compileall, and diff checks.
No acceptance flexibility was used. This sub-gate does not claim that the free-source database is
fully populated, that historical membership is complete, or that the exact V25 refresh/source
picker/unavailable/revision visuals are represented; those remain explicit data/reference gaps.

## 2026-08-19 — Market Map composition must match the requested evaluation time

For a Market Map with `area_metric=weight`, acceptance must verify that a system-managed
benchmark-family, ETF-holdings, or market-group source uses the latest composition known at the
requested `end` when `as_of` is omitted, and uses the explicit `as_of` when supplied. A personal,
managed, or combo watchlist remains a current selection for a chart-period request unless it has
an explicit historical cutoff. The map response and tile provenance must retain the selected
membership version, composition/effective/known timestamps, and exact exclusions. The two-snapshot
ETF regression and full `104/104` affected backend suite are the interim oracle; this does not close
historical participation/ranking/rotation batches or exact V25 weight-badge visuals.

## 2026-08-19 — Family breadth current/as-of semantic tie-break

The direct benchmark-family derived-equal breadth acceptance must assert both modes: a saved
`point_in_time=true` universe uses its requested `as_of`, while current mode does not apply a
historical cutoff merely because an optional timestamp is present. The shared source resolver and
focused family regressions are the interim oracle. The localized mismatch was repaired and tested;
it is recorded here as a closed defect, not a goal-wide blocker or acceptance waiver.

## 2026-08-19 — Locked benchmark-family source sub-gate

Acceptance must treat every evidenced benchmark-family leg as a source-polymorphic locked
watchlist, not as a separate heatmap implementation. For each available cap/equal/value/growth
leg, exercise `GET /watchlists/sources`, historical source resolution, Market Map, generic breadth,
and compatible reuse surfaces with the exact canonical source ID. Membership must be immutable to
the user while follow/clone and linked publication remain available. A permitted derived equal
leg must use the declared point-in-time constituent set, equal weights, explicit methodology, and
the same source/cache lineage; an absent role must remain visibly unavailable with no substitution.

The current interim oracle is the all-role family matrix regression plus the complete affected
watchlists/workspaces/taxonomy suite (`103/103`). Its opt-in browser data is explicitly labelled
controlled fixture data and proves source-contract coverage, not live membership truth. Exact
Version 25 source-picker geometry,
labels, badges, follow/clone placement, derived-weight disclosure, and unavailable-role visuals
remain reference-board gaps and must stay in the gap ledger until represented by reviewed evidence.

## 2026-08-19 — Cross-sectional breadth aggregate-plot sub-gate

For a completed historical Python breadth run with a cross-sectional numeric target or recursive
condition tree, acceptance must verify that Research Results can create one reusable `plot` asset
whose declared output is the aligned aggregate `percentage_history` series. The generated asset
must retain source run/code/definition/reproducibility/manifest/universe and target/tree lineage,
declare the explicit `breadth_aggregate_percentage` isolated-run adapter, and reject duplicate
promotion. A rerun through `/research/runs` must materialize the complete declared universe (not
the active chart symbol), execute once inside the isolated runner, and return a finite series
artifact suitable for uPlot. The chart library must retain the locked source ID or explicit source
symbols when adding the plot, so changing the active symbol cannot silently collapse the aggregate
to one member. Aggregate plots remain incompatible with scalar watchlist columns; no cross-section
may be flattened into a per-member value.

This closes the represented aggregate chart target only. Exact Version 25 promotion wording,
placement, and chart-library visual state remain a tracked reference-board gap; they do not relax
the lineage, full-universe, sandbox, or rerun acceptance requirements.

Market Map acceptance must also verify CSV export from a loaded map. The export must contain every
returned cell and its canonical grouping, metric, coverage, observation-time, and warning fields;
it must work for locked and editable sources without mutating selection, membership, or route state.
Acceptance must also inspect `area_provenance` for each covered cell. Equal and Python areas must
identify their derivation, source weights must retain effective/known-at and membership lineage,
volume must identify its local observation bar, and current market-cap metadata must explicitly
state that it is not point-in-time. This provenance gate does not waive the separate requirement
for historical market-cap/weight reconstruction.

## 2026-08-19 — Explicit canonical selection sub-gate

Acceptance must allow a user to enter multiple symbols in Market Map, resolve each through the
canonical security master, deduplicate the resulting instrument IDs, and submit an explicit source
without provider fan-out. The backend must reject malformed/oversized IDs, report missing canonical
instruments, mark the source locked and non-point-in-time, and preserve the same map metrics,
coverage, cache, snapshot, and linked-analysis contract as other sources. The input must be
persisted in tool state and offer the durable personal-watchlist save path. Historical membership
versioning and exact V25 explicit-source visual geometry remain separate open gates.

The migration gate must also exercise upgrade/downgrade of `fa0b1c2d3e4f` and verify that a
near-limit explicit source ID survives cache and snapshot persistence without truncation.

The explicit-entry performance gate must verify one `POST /instruments/resolve-canonical` request
for a multi-symbol selection, canonical ID order after duplicate removal, explicit missing-symbol
reporting, and zero provider-discovery calls. A selection of 501 symbols must be rejected before
database/provider work. The configured local PostgreSQL service was unavailable during the first
implementation checkpoint, so live migration upgrade/downgrade evidence remains a final audit gap;
the missing service must not be presented as a passing migration test.

The durability gate must exercise `Save as watchlist` from an explicit source and verify that every
canonical member in the source descriptor is added, including a member whose map cell has no current
bar/area geometry. The action must remain user-isolated and must not mutate the locked source.

## 2026-08-19 — Universal combo-source sub-gate

Acceptance must treat a user-owned combo list as the same Market Map universe contract as an index,
ETF, managed scan, or personal watchlist. The combo descriptor must be user-isolated, explicitly
`source_kind=combo`, locked for direct membership edits, and traceable to its library
definition/version. Union, intersection, exclusion, duplicate, deterministic-order, and
`as_of`-exclusion behavior must be asserted through `/watchlists/sources/{source_id}` and then
through `POST /analysis/market-map`. The map must preserve source identity and expose the same
grouping, metrics, coverage, cache, snapshot, selection, and publication actions. A combo may be
edited only by changing its definition; that creates a new membership version. Full historical
definition/version reconstruction, explicit-symbol descriptors, and final V25 visual approval
remain separate open gates.

## 2026-08-19 — Arbitrary Market Map period sub-gate

For every canonical WatchlistSource, acceptance must verify the Market Map preset periods and a
`CUSTOM` completed-session range. Start/end dates must reach the batch request, produce matching
period bounds and a distinct cache identity, persist through tool configuration, and remain
available for locked and editable sources alike. Assertions must account for each distinct period
request; no period may silently reuse a different range.

## 2026-08-19 — Member-series-to-column promotion sub-gate

For a completed isolated Python breadth-history run, acceptance must verify that a member-scoped
numeric series can be saved as a reusable watchlist column. The persisted scalar CodeVersion must
retain the source run/code/definition/reproducibility/dataset/universe lineage and declare the
`latest_series_to_scalar` adapter; the isolated runner must request the series and return the latest
finite value without API-side Python execution. Research Results must expose success and duplicate
states. Cross-sectional aggregates and recursive Boolean trees must return explicit capability
errors rather than being silently projected into per-symbol values. This sub-gate passes only for
the represented member scope; filters, gauges, alerts, Study Lab, Strategy Lab, and broader
cross-sectional promotion remain named open gates.

## 2026-08-19 — Numeric breadth to EasyScan sub-gate

For a completed member-scoped numeric breadth run with a validated finite operator and threshold,
acceptance must verify that “Promote to EasyScan” creates a distinct immutable Boolean condition
version. Its diagnostics must retain source lineage and declare `series_target_to_boolean`; the
isolated runner must request the numeric series, apply the declared relation, and return a Boolean
cell without API-side execution. The original series version remains unchanged. Cross-sectional
aggregates and recursive Boolean trees must return structured capability errors for this target.
This gate does not claim filters, gauges, alerts, Study Lab, Strategy Lab, or richer multi-output
fan-out complete.

## 2026-08-19 — Cross-sectional breadth Study Lab promotion sub-gate

For a completed historical Python breadth run, acceptance must verify that the Research Results
action can create one immutable `study` asset through the isolated `research.breadth_python`
adapter. The generated version must preserve source code/version, parameters, condition tree,
series target scope/statistic/operator, universe and membership version, dataset-manifest hash,
definition/reproducibility lineage, and explicit aggregate-study semantics. A rerun of that
version must return aligned percentage/group-value series, current member rows, exclusions, and
historical points without executing Python in FastAPI or flattening a cross-sectional result into
a per-member plot/column. Duplicate promotion must return a structured conflict. This sub-gate
closes only the aggregate Study Lab target; remaining promotion fan-out is still evaluated
independently per target contract.

## 2026-08-19 — Recursive/cross-sectional Boolean promotion sub-gate

For a completed historical breadth run whose Boolean result is represented by a recursive or
cross-sectional condition tree, acceptance must verify that `Promote to EasyScan` creates a
distinct immutable Boolean code version rather than reusing or flattening the numeric anchor.
The generated screener must retain the resolved tree, source run/code/dataset/universe lineage,
and `condition_tree_to_boolean` adapter metadata. Running that screener must place the same tree in
the isolated job payload and produce the expected Boolean member result. Direct promotion into
non-Boolean targets remains a separate open gate.

## 2026-08-19 — Boolean breadth target fan-out sub-gate

For a completed member-scoped Boolean breadth-history result, acceptance must verify that Research
Results offers alert, Market Gauge, and Strategy signal targets in addition to EasyScan. The first
three actions must reuse one generated immutable Boolean EasyScan and preserve the source run,
condition version, universe, dataset, and reproducibility lineage. The alert payload must target
that scan; the Strategy signal must reference the scan's immutable Boolean code version; and a
repeat click or a different target must not create duplicate scans.

Cross-sectional aggregates and non-Boolean series remain outside this sub-gate and must retain
structured capability gating. A missing exact V25 capture for this successive-promotion state is a
visual-board gap only; deterministic action/API assertions remain the interim oracle and do not
relax the functional lineage requirement.

## 2026-08-18 — Universal source and recursive Python sub-gate

The heatmap/breadth acceptance oracle treats every canonical source as one universe contract.
For a locked index or ETF source, acceptance checks immutable membership, versioned composition
lineage, and rejection of direct membership edits; it then exercises the same map, hierarchy,
selection, linked-chart, breadth, scan, alert, and Study Lab actions used by personal, managed,
combo, sector, industry, proxy, and explicit-symbol sources. Following or pinning a locked source
must never hide the source from analysis or force a route change; cloning is the explicit editable
operation.

The isolated-Python sub-gate now covers a recursive tree containing member and cross-sectional
numeric-series Python leaves plus built-in predicates. It verifies owned-code resolution,
Boolean-contract handoff, job-file preservation, once-per-timestamp cross-sectional materialization,
timestamp-aligned member/benchmark history execution, and compatibility with existing scalar/Boolean/series/event batch
paths. No provider access is permitted. The gate now also verifies direct member-level and
cross-sectional comparison of two owned numeric-series outputs using difference and ratio-minus-one
semantics, including a benchmark-derived source. Cross-sectional acceptance derives the pair per
member, applies the declared same-timestamp group statistic, and retains the member-minus-group
metric and exclusions. Richer multi-stage derived composition and universal promotion fan-out
remain named capability gaps; they cannot be represented as passing through a member-only fallback.

## 2026-08-17 — Mixed-scope breadth sub-gate

The breadth/Market Map and isolated Study Lab runners must accept a compound tree containing both a
cross-sectional percentile leaf and member-level leaves. They verify one universe-wide rank pass,
member predicate evaluation, tri-state `all`/`any`/`not` composition, clause diagnostics,
denominator/exclusion semantics, current-bar alignment, historical no-forward-fill behavior, and
no provider fan-out. The same condition must serialize through the visual tree editor and
authenticated browser flow.
Arbitrary Python target-series leaves remain open and cannot be treated as silently equivalent. The
explicit group-statistic leaf is accepted only for its declared mean, median, minimum, maximum, and
standard-deviation set, with the member-minus-group metric retained. A two-series comparison is
accepted only when both owned series pass the isolated series contract before aggregation.

## 2026-08-17 — Cross-sectional Market Map breadth sub-gate

The Market Map breadth gate now includes a cross-sectional fixture: a locked or editable source can
colour tiles from a root or nested percentile condition using the same local, aligned member
metrics as the generic breadth endpoint. Acceptance checks rank, threshold, pass/fail colour,
exclusion, clause diagnostics, and no provider fan-out. The visual editor serializes
`target_scope` at the condition node and does not leave contradictory nested scope state. The
declared group-statistic set is now covered; arbitrary Python target-series leaves and richer
derived statistics remain open; no acceptance flexibility was used.

## 2026-08-17 — Market-map acceptance sub-gate

For every available S&P 500/400/600/1500, Russell 1000/2000/3000, and Nasdaq 100 root/role, the
runner must select the universe, render sector and industry hierarchy, and exercise 1D, 1W, MTD,
YTD, 1Y, and custom completed-session periods. It must verify independent area (market cap,
point-in-time weight, equal, or declared numeric field) and colour (absolute/relative return,
technical, breadth, or compatible Python series), exact rollups, weighting method,
coverage/exclusions, freshness/provenance, and point-in-time semantics.

The same run must prove that an index/ETF universe is a locked system-managed watchlist: it can be
followed, pinned, selected, cloned as a dated snapshot, and reused by the map, grid, scans,
breadth, alerts, and linked charts, while direct membership edits are rejected and a refreshed
composition creates a new version with effective/known-at/source lineage. Screener-managed and
personal lists must continue to use the same source contract with their own mutation rules.

The source-contract sub-gate now passes backend integration and frontend store coverage for
descriptor listing, locked index-source metadata, user isolation, member resolution, and exact
historical exclusion of members not known at `as_of`. This does not satisfy the parent map gate;
treemap metrics, rollups, periods, rendering, and publication remain open.

The Python breadth promotion sub-gate now verifies that a completed member-level numeric-series
run creates a reusable uPlot `plot` asset with source-run, code-version, definition, reproducibility,
manifest, and universe lineage. It also verifies explicit rejection of cross-sectional aggregate
runs and recursive Boolean trees, preventing a group result from being silently presented as a
per-symbol plot. Promotion to columns, filters, gauges, alerts, Study Lab artifacts, and Strategy
Lab signals remains separately tracked.

The backend batch sub-gate now has a deterministic contract at `POST /analysis/market-map`. Its
fixture coverage proves that a personal source can produce sector/industry nodes and independently
weighted tiles from local bars and metadata, while missing bars remain visible as cell warnings.
The complete response is persisted by a user-isolated cache identity containing request semantics,
membership version, member IDs, and local bar watermarks; repeated requests and the explicit cache
restore route return the persisted result without provider fan-out. Built-in breadth predicate
colour output now uses the shared condition evaluator and retains pass/fail tile values, condition
metrics, exact exclusions, and the serialized condition definition. This is not visual acceptance:
named snapshots, all requested periods/metrics, isolated Python colour outputs, point-in-time
market-cap area, the renderer, and complete historical population remain explicit open gates. No
acceptance flexibility was used for this slice.

The workstation consumer sub-gate now passes component coverage for source selection, locked-source
lineage, batch request configuration, deterministic proportional tile geometry, configuration
persistence, tile-to-symbol publication, hover detail, palette/coverage legend, additive
multi-selection, nested breadcrumbs, wheel/button zoom, pointer panning, failed-map status, and
direct publication into Breadth and Study Lab, plus visible persisted-cache status. The same interaction contract applies to arbitrary
watchlist sources; index/ETF sources are locked only for membership mutation. Direct publication
preserves the full canonical source as the analysis universe and carries selected members as
context; subset extraction remains the editable-list action. This is still an interaction/
component oracle, not a Version 25 visual pass: named snapshots and board-guided visual gates
remain open. The watchlist publication gate covers creating/populating an
editable personal list and rejecting managed/locked targets.

The browser gate covers hover detail, palette/legend, zoom/pan, sort, drill-down, selection,
multi-selection, map-to-chart/watchlist/breadth/Study-Lab publication, loading/partial/stale/
unavailable/error/recovery states, and large-universe rendering without one provider request per
tile. The old dashboard heat map is not an acceptance substitute: its 500-ID cap and fixed metrics
remain a compatibility gap until the workstation batch map contract exists.

## 2026-08-17 — Eight-root US family/style acceptance (latest requirement)

The complete top-down acceptance matrix contains eight interchangeable roots: S&P 500, S&P
MidCap 400, S&P SmallCap 600, S&P Composite 1500, Russell 1000, Russell 2000, Russell 3000,
and Nasdaq 100. The run must attempt the official identity (when entitled), cap-weighted proxy,
equal-weight vehicle or point-in-time derived equal series, and every independently evidenced
value/growth sub-index or ETF for each root. This is an acceptance expansion, not permission to
silently omit unavailable roles.

For each available `(root, role)`, acceptance exercises technicals, cap/equal and value/growth
spreads, direct and cross-family ratios, sector/industry/proxy ranking, configurable predicate
breadth, participation/leadership, concentration/dispersion, drawdown/volatility/correlation,
relative rotation, seasonality/regime context, constituent drill-down, and reuse through
watchlists, filters, scans, gauges, alerts, Study Lab, plots, and exports. Every response and
artifact retains role, weighting method, membership/rebalance version, effective/known-at policy,
adjustment, coverage, exclusions, freshness, and provenance.

The Nasdaq 100 requires a dedicated cap/equal deconstruction equivalent to SPY/RSP. QQQ/QQQE is
only a candidate fixture until independent identity, holdings, weighting, rebalance, historical
bars, and point-in-time membership evidence pass. If a value, growth, equal, official-index, or
holdings relationship cannot be verified, the expected result is an explicit unavailable, derived,
or `No verified mapped proxy` state with a closure condition in the gap ledger. Selector presence,
name similarity, another family's product, or a current-only snapshot never satisfies this gate.

The acceptance runner is parameterised by `(root, role, view)` across the Cartesian matrix, with
the eight roots (S&P 500/400/600/1500, Russell 1000/2000/3000, Nasdaq 100), every independently
verified cap/equal/value/growth role, and the complete supported view set. For each row it must
exercise technicals, normalized performance, cap/equal and style spreads, parent/peer/cross-family
ratios, sector/industry/proxy ranking, user-authored breadth, participation/leadership,
concentration/dispersion, rotation, risk/regime views, and constituent drill-down without changing
routes. The same row identity and evidence lineage must survive into watchlists, filters, scans,
gauges, alerts, Study Lab, plots, and exports. An unavailable role is still an asserted outcome
(`No verified mapped proxy`, unavailable, or derived) with evidence and a closure condition; it is
not an omitted test case or a silent fallback.

### Required breadth/deconstruction traversal

The family run is incomplete unless it exercises user-authored breadth against every available
root/role and against the resolved sector, industry/proxy, and constituent universes. At minimum,
fixtures cover moving-average participation, configurable distance to prior/52-week extremes,
volume, RSI, volatility, relative-strength, event, benchmark/peer, group-aggregate, and Python
targets. The assertion is the declared percentage of eligible members satisfying the predicate,
with member-versus-cross-sectional scope, exact alignment, denominator, membership/as-of version,
coverage, exclusions, and provenance checked in both current and historical results.

Nasdaq 100 has an additional mandatory cap/equal deconstruction gate: the cap and equal legs must
be selectable independently, produce aligned technical/ratio/spread values, and accept the same
breadth definition so that leadership and participation differences are observable. The SPY/RSP
fixture is the behavioral template, not a substitute for Nasdaq or the other seven families.

## 2026-08-17 — Numeric Python-series breadth sub-gate

Acceptance now includes a bounded isolated-runner fixture whose condition CodeVersion emits a
numeric series and whose breadth definition declares a threshold relation. The run must verify
current and exact-timestamp historical output, numeric per-member metrics, Boolean pass/fail
projection, denominator/coverage/exclusions, code and dataset lineage, and reproducibility. The
source must execute only in the dedicated sandbox. The authenticated Python Library and breadth
composer must also verify asset selection, operator/threshold authoring, durable queue/poll status,
current/history rendering, numeric member metrics, pass/fail drill-down, and workspace retention;
the rebuilt Chromium select → configure → evaluate path now passes. Direct series-to-series/
reference targets, Python-series leaves inside recursive visual trees, and full promotion fan-out
remain open gates and are not implied by this slice.

## 2026-08-17 — Prior high/low breadth sub-gate

Acceptance now includes a reusable prior-window extreme predicate: for every eligible member, the
latest close is compared against the high or low of a declared preceding window, with the current
bar excluded and signed distance/operator/threshold retained in the definition. Current,
historical, recursive, diagnostic, and occurrence paths are covered by the backend, workstation,
integration, and authenticated-browser gates. Event/benchmark-peer targets, arbitrary derived
Python composition, and promotion fan-out remain open gates. No visual, provider, or acceptance
flexibility changed.

## 2026-08-17 — Recursive breadth diagnostics sub-gate

Current and historical generic breadth acceptance must return a structured trace for every
evaluated AST clause, not only an opaque aggregate exclusion. The trace records a stable recursive
path, clause kind, pass/fail/excluded status, metric, and exact exclusion code for each member.
The workstation exposes the trace in the dense result and member drill-down surfaces. Unit,
database-backed API, full frontend, type/build, and rebuilt authenticated Chromium checks pass.
Event/benchmark-peer target series, arbitrary derived-Python composition, and promotion fan-out
remain open gates. No visual threshold, provider rule, or acceptance flexibility changed.

## 2026-08-17 — Eight-root factor/style acceptance matrix

This is the user-confirmed active scope expansion. Acceptance must treat the S&P 500/400/600/1500,
Russell 1000/2000/3000, and Nasdaq 100 perspectives as equally first-class, including any
independently evidenced value/growth legs and Nasdaq-100 cap/equal deconstruction; it is not enough
to prove the original SPY/RSP fixture.

The top-down acceptance run must treat S&P 500, S&P MidCap 400, S&P SmallCap 600, S&P Composite
1500, Russell 1000, Russell 2000, Russell 3000, and Nasdaq 100 as eight complete, interchangeable
workstation perspectives. For each root, the run must attempt the official identity, cap proxy,
equal-weight vehicle or reproducible point-in-time derived series, and every evidenced value and
growth sub-index/ETF. It must exercise each available leg through technicals, cap/equal and
value/growth comparisons, parent/peer/cross-family ratios, generic predicate breadth, participation,
concentration/dispersion, rotation, drawdown/volatility, ranking, seasonality/regime context,
sector -> industry/proxy -> constituent drill-down, Study Lab, scans, gauges, plots, alerts, and
exports.

The phrase “if they exist” is resolved by canonical evidence, not by guessing likely tickers. A
candidate leg is selectable only after issuer/source, relationship role, membership or weighting
method, effective/known-at dates, historical bars, coverage, and freshness are present. Missing or
ambiguous legs must render `No verified mapped proxy`, unavailable, or derived and must stay in the
gap ledger. The run must never substitute SPY/QQQ, another root, or a current-only snapshot. Nasdaq
100 has a mandatory cap/equal deconstruction equivalent to SPY/RSP (QQQ/QQQE only after its own
identity, holdings, rebalance, date, and bar evidence passes). No visual, provenance, provider, or
historical acceptance threshold is relaxed by this expansion.

## 2026-08-17 — Recursive breadth condition-tree sub-gate

The authenticated breadth editor must support arbitrary nested `all`/`any` groups and exactly
one child for `not`, not only a fixed primary-plus-secondary pair. Every supported visual leaf
predicate must remain editable inside any group, and the serialized AST must be the same versioned
condition contract used by current evaluation, history, occurrences, denominators, exclusions,
and provenance. The rebuilt Chromium flow proves a nested `all(any(new_high_low))` payload and the
component suite covers recursive add/remove/operator behavior, NOT cardinality, and leaf editing.
The first rerun exposed stale range-input and inherited-leaf test fixtures; explicit value/reset
assertions fixed the oracle and the unchanged flow passed. No product criterion, visual limit,
provider rule, or acceptance flexibility changed. Per-clause diagnostics, event/benchmark-peer
targets, derived Python composition, and full promotion fan-out remain open gates.

## 2026-08-17 — Breadth OR/NOT composition sub-gate

The breadth editor must distinguish single, `all`, `any`, and `not` composition. `all` and `any`
must serialize two explicit child conditions, while `not` must serialize exactly one child; the
backend remains authoritative for recursive evaluation, exclusions, and historical semantics.
Authenticated Chromium verifies both nested request shapes. The initial rerun found a test-order
defect where the percentile assertion inherited `not`; the oracle was corrected to reset to single
before that independent case and the unchanged flow passed. No product criterion, visual limit,
mask, or provider rule was relaxed. Recursive visual authoring, event/benchmark-peer targets,
derived Python composition, and promotion fan-out remain open gates.

## 2026-08-17 — New-high/new-low breadth sub-gate

The breadth editor must allow the user to select `new_high_low` versus a configurable prior
window and choose high or low direction. The existing 52-week-distance predicate must likewise
distinguish near-high from near-low. Acceptance verifies the serialized condition kind, direction,
and lookback through an authenticated browser interaction against the rebuilt stack, while the
backend evaluator and historical/no-forward-fill contract remain unchanged. A first run found
duplicate accessible labels for the legacy and custom lookback inputs; those labels were separated
and the unchanged 1/1 oracle passed. No acceptance threshold, visual mask, provider rule, or goal
criterion was relaxed. Event composition, benchmark/peer targets, arbitrary derived Python, and
promotion fan-out remain tracked gaps.

## 2026-08-17 — Cross-sectional percentile Study Lab sub-gate

The Study Lab factory must expose an editable unified-Python starter for cross-sectional
percentile breadth. Given an explicit declared universe, it must rank valid member scalar values
at each timestamp, apply the selected percentile/operator, and expose current percentage,
pass/eligible counts, aligned historical series, member rows, and exact exclusions. The runner
must reject unsupported cross-sectional kinds explicitly; it must not evaluate them as member
conditions. Focused runner, full runner, Study Lab component, frontend type-check, production
build, and full Vitest evidence pass. No acceptance threshold, visual mask, provider rule, or
completion criterion was relaxed. Derived Python target-series/group-statistics and promotion
targets remain tracked gaps; mixed-scope composition is now covered by the shared local and
isolated evaluators.

## 2026-08-17 — Cross-sectional breadth scope sub-gate

Acceptance must distinguish `target_scope=member` from `target_scope=cross_sectional`. For the
cross-sectional percentile path, all members observed at the same timestamp are ranked from the
declared scalar field before the operator/percentile threshold is applied. Ties use deterministic
inclusive empirical ranks; members without a current bar or valid scalar are excluded from both
the rank universe and pass denominator with exact reasons. Current and historical responses must
preserve scope, rank metric, membership/timestamp alignment, coverage, and occurrences.

An unsupported cross-sectional condition must be visibly rejected/excluded and must not fall back
to member semantics. The implemented sub-gate passes backend unit/API, frontend type/build, and
rebuilt authenticated browser evidence. No visual threshold, provider rule, or acceptance
flexibility changed. Cross-sectional Python/derived-series, richer derived statistics, and
remaining promotion targets remain tracked gaps.

## 2026-08-17 — Breadth range and rolling-percentile sub-gate

For the selected family/style/watchlist universe, acceptance must prove that a range predicate
uses the declared field and inclusive lower/upper bounds and that a percentile predicate uses the
declared rolling window, percentile target, and operator. Both current and historical paths must
retain eligible denominator, coverage, member-level metric/Boolean values, exclusions, and
occurrence semantics. Invalid bounds or parameters must be structured exclusions, never implicit
false values. The same condition payload must be visible in the workstation request and API
response.

This sub-gate is implemented and validated by backend unit/API checks, frontend type/build, and
the authenticated seeded browser flow. It does not relax visual thresholds, provenance rules,
provider rules, or the eight-root completion bar. Cross-sectional percentile/rank, prior/event,
benchmark/peer, richer derived-series, and remaining promotion targets are named open gaps and
must be closed or explicitly reported in later checkpoints.

## 2026-08-17 — Python breadth EasyScan promotion sub-gate

For a completed isolated Python breadth-history run, acceptance must verify that Research Results
can create an EasyScan without executing source in FastAPI or contacting a provider. The scan must
reuse the immutable Boolean code version and source member IDs, preserve the source run ID,
definition/reproducibility identifiers, exact dataset-manifest fingerprint, membership/as-of
metadata, and explicitly state that the target re-evaluates current data over those source IDs.
It must not claim historical replay semantics or silently substitute an all-instruments universe.

Acceptance also verifies structured rejection for current-only, incomplete, artifact-less,
foreign/non-Boolean, and incomplete-universe runs, plus duplicate-name conflict handling and the
visible Research Results success/error state. Other compatible promotion targets remain open and
must use the same lineage contract when implemented.

## 2026-08-17 — Expanded US-family acceptance directive

The active completion bar covers eight complete US market perspectives: S&P 500, S&P MidCap 400,
S&P SmallCap 600, S&P Composite 1500, Russell 1000, Russell 2000, Russell 3000, and Nasdaq 100.
For each root, acceptance must attempt the official identity (when entitled), cap-weighted proxy,
equal-weight vehicle or point-in-time derived equal series, and independently evidenced value and
growth variants. It must then exercise benchmark technicals, cap/equal/style spreads, direct and
cross-family ratios, generic predicate breadth, participation/leadership, concentration/dispersion,
correlation, drawdown/volatility, relative rotation, ranking, seasonality/regime, and the
sector -> industry/proxy -> constituent workflow, including reusable plots, scans, gauges, Study
Lab artifacts, alerts, and exports.

The Nasdaq 100 has a dedicated cap/equal sub-gate equivalent to the SPY/RSP behavior. QQQ/QQQE is
only a candidate until canonical identity, issuer relationship, holdings or derived membership,
weighting/rebalance method, effective/known-at dates, bars, coverage, exclusions, and provenance
are verified. Native ETF weights and locally derived equal weights must remain visibly distinct.
Every family/style leg is independent; a missing or unverified role must produce `No verified
mapped proxy`, unavailable, or derived state and must never silently fall back to SPY, QQQ,
another family, or current-only membership.

Breadth acceptance is parameterised by the selected root and leg. It must prove that a user-authored
predicate (for example moving-average state/distance, configurable distance to a 52-week high/low,
new highs/lows, RSI/trend, volume/volatility, relative strength, benchmark/peer comparison, or
unified Python) is evaluated over that exact point-in-time universe and retains scope, membership,
weighting, as-of/known-at, coverage, exclusions, freshness, and provenance through history,
occurrences, charts, lists, filters, scans, gauges, alerts, Study Lab, and export. Selector-only
coverage or a single SPY fixture does not satisfy this gate; missing provider/history/style/equal,
visual, and browser-population evidence remains an explicit tracked gap.

### Daily perspective workflow acceptance

For each of the eight roots and every verified cap/equal/value/growth leg, the acceptance run must
exercise the same user journey rather than only loading a family row: benchmark technicals;
cap/equal and value/growth leadership; sector and industry/proxy ranking; condition-driven breadth
and participation; concentration/dispersion; relative rotation; drawdown/volatility; seasonality
and regime context; and constituent drill-down. The Nasdaq 100 cap/equal fixture must be usable in
the same way as SPY/RSP after canonical relationship and holdings evidence is verified. Ratios and
linked views must retain family/role, membership/as-of, weighting, coverage, exclusions, freshness,
and provenance throughout. This is a clarification of the existing completion bar, not an
acceptance relaxation; missing or unrepresented states stay in the gap ledger.

### US family view-matrix acceptance

The daily workflow test is parameterised by `(family, role)` and must run for every verified
cap/equal/value/growth role under each of S&P 500/400/600/1500, Russell 1000/2000/3000, and
Nasdaq 100. The required sequence is benchmark/leg technicals; cap/equal and value/growth
spreads; direct and cross-family ratios; sector/industry/proxy ranking; user-authored breadth and
participation; concentration/dispersion; relative rotation; drawdown/volatility/correlation;
seasonality/regime context; and constituent drill-down. The same role must then be usable as a
watchlist column/filter, EasyScan, Market Gauge, alert, Study Lab study, reusable uPlot plot, and
export artifact where the output contract permits.

The fixture records an explicit result for every requested role. A role with no independently
verified instrument or reproducible point-in-time series is `No verified mapped proxy`, unavailable,
or derived, with source/effective/known-at/coverage evidence and a closure condition. It is not a
silent omission or cross-family fallback, and it does not prevent independent roots with valid
evidence from continuing through their own acceptance runs.

### Benchmark/peer series breadth sub-gate

For a `series_comparison` condition, acceptance must verify that the saved definition names the
member field, reference field, relation (`difference` or `ratio`), operator, threshold, and
canonical `reference_symbol`. Current and historical runs must align member and reference bars on
the exact observation timestamp, exclude missing/misaligned references with
`benchmark_missing_at_timestamp`, and preserve the same diagnostics, occurrences, denominator,
coverage, and definition hash. A browser request must prove that the compact editor emits the
selected fields and relation. Event-series, arbitrary derived-Python, and full promotion targets
remain tracked gaps rather than being implied by this sub-gate.

### Group/peer aggregate target sub-gate

When `reference_universe` is supplied, acceptance must verify that it is resolved through the
canonical local universe and point-in-time membership path, not interpreted as a symbol. The
derived reference must declare `derived_equal_weight_return_index`, exact-timestamp/no-forward-fill
alignment, member count, covered-member summary, membership version, and supported target fields.
Current and historical `series_comparison` results must retain that lineage and treat an absent
reference point as `benchmark_missing_at_timestamp`; partial reference membership is reported as
coverage metadata rather than silently filled. The workstation must expose symbol versus
equal-weight group aggregate authoring and emit the same immutable definition in both requests.
Event targets, arbitrary Python target series, and full promotion fan-out remain open.

### Event-calendar target sub-gate

For an `event` condition, acceptance must verify that the target is resolved from the canonical
local instrument-event dataset, not a provider call made during ordinary breadth evaluation. The
definition must preserve event type, trailing-day window, estimate policy, operator, event-dataset
kind, loaded/unavailable member coverage, event count, and `event_time_at_or_before_observation`
alignment. A loaded empty calendar is an eligible false result; no fetch state is an explicit
`event_data_unavailable` exclusion. Current and historical results must agree at each timestamp,
never carry an event forward, and retain diagnostics/denominator semantics. Compact and recursive
authoring plus authenticated browser coverage must serialize the same immutable event definition.
Promotion into plots, columns, filters, gauges, alerts, Study Lab, and Strategy Lab remains a
separate open gate. The first browser run exposed a stale sibling-configuration race; it was fixed
at the local draft boundary and the unchanged broader flow passed. No acceptance flexibility was
used.

## 2026-08-17 — Research Results occurrence-filter sub-gate

The persisted Python breadth occurrence browser now supports an accessible symbol substring
filter and entered/exited transition filter, with a live visible-count and explicit no-match
state. Filtering operates on the immutable persisted occurrence rows and does not alter the
definition, denominator, or provenance. The filtered click path continues through the existing
canonical occurrence/link bus. Component and type-check evidence passes; filtering for other
event artifact classes and promotion beyond the lineage-preserving EasyScan target remain open
gates.

## 2026-08-17 — Persisted Python breadth occurrence sub-gate

When an isolated Python breadth-history run is collected, the generic Research Results surface
must receive the same occurrence contract as the direct analysis endpoint. The collection boundary
may normalize runner cells into canonical member rows and derive aggregate counts, but it must
not execute source or fetch market data. Persisted events must retain stable ID, UTC timestamp,
canonical instrument ID, symbol, transition kind, metric, percentage, pass count, and eligible
count. The result tool must render the uPlot history and a bounded event browser; clicking an event
must publish through the existing workstation occurrence/link bus with canonical identity and
timestamp. Unit, router/service, database-backed integration, frontend component, type/build, and
full Vitest evidence now pass. Filtering and promotion beyond EasyScan remain open gates.

## 2026-08-17 — Current US family perspective completion bar

The active product vision now requires eight interchangeable US top-down roots: S&P 500, S&P
MidCap 400, S&P SmallCap 600, S&P Composite 1500, Russell 1000, Russell 2000, Russell 3000,
and Nasdaq 100. Each root is a complete analysis perspective, not a label in a selector. The
acceptance run must attempt its official identity (when entitled), cap proxy, equal-weight
vehicle or point-in-time derived equal series, and each evidenced value/growth leg, then drive
the same technical, ratio, condition-driven breadth, participation, leadership,
concentration/dispersion, correlation, drawdown/volatility, rotation, ranking,
sector -> industry/proxy -> constituent, watchlist, scan, gauge, Study Lab, reusable-plot, and
export paths.

The S&P 500 SPY/RSP comparison is the reference behavior for the broader cap/equal contract. The
Nasdaq 100 must have an independently evidenced cap/equal deconstruction (QQQ/QQQE is a candidate
pair, not an assumption). Native ETF weighting and locally derived equal weighting must remain
separate and disclose membership/rebalance version, effective/known-at dates, weights, coverage,
exclusions, freshness, and provenance. Value/growth legs are attempted independently for every
root; if a leg cannot be verified, the correct result is a visible `No verified mapped proxy`,
unavailable, or derived state. No family may silently fall back to SPY, QQQ, another root, or a
current-only snapshot.

Breadth acceptance is consequently family- and leg-parameterised. The predicate composer must be
able to evaluate arbitrary supported member-level conditions (including moving-average state or
distance, configurable 52-week-high/low distance, new highs/lows, RSI/trend, volume/volatility,
relative strength, benchmark/peer relationships, and unified Python) over each selected
point-in-time universe, and preserve that scope through history, occurrences, charts, lists,
filters, scans, gauges, alerts, Study Lab, and exports. A single SPY demonstration or a family
selector with no populated data does not pass. Missing provider, history, style/equal, visual,
or browser evidence remains a named gap and is reported rather than hidden.

## 2026-08-15 — Generic breadth occurrence sub-gate

For every supported generic breadth history definition, acceptance must verify that occurrences are
derived from the same per-member historical results as the aggregate percentage. `member_entered`
and `member_exited` events require two known Boolean observations and preserve canonical instrument
identity, timestamp, metric, percentage, pass/eligible counts, and stable identity. Initial,
missing-bar, and excluded observations must not create transitions. The workstation must render a
bounded occurrence browser and route a click through the existing occurrence/link bus with the
canonical instrument ID and timestamp, updating the linked chart context. The service/API and
represented authenticated browser fixtures pass this sub-gate. Occurrence filtering, isolated-
Python artifacts, promotion beyond EasyScan, and unrepresented Version-25 occurrence states
remain open gates.

The first browser attempt exposed a localized, recoverable overlap between the unavailable generic
history state and the occurrence list, plus an exact-route fixture that did not match query
parameters. Both were repaired in branch-controlled code/tests, then the focused browser test,
full frontend unit suite, type-check, production build, and diff checks were rerun. No acceptance
threshold or flexibility was changed; the residual risk is limited to unrepresented visual states
tracked in the board/manifest gap ledger.

The isolated-Python sub-gate additionally requires aligned historical Boolean runs to expose the
same occurrence schema after collection: two known member states, canonical instrument identity,
timestamp, metric when supplied, aggregate counts, stable ID, and immutable code/dataset lineage.
The source must remain isolated; FastAPI may project the persisted result but may not execute user
code. Router `19/19`, runner `88/88`, and database-backed generic/Python integration `4/4` pass.
Direct UI rendering is covered; promotion beyond EasyScan remains an explicit open gate.

## 2026-08-15 — Eight-root US analysis and Nasdaq-100 cap/equal gate

The family acceptance matrix consists of S&P 500, S&P MidCap 400, S&P SmallCap 600, S&P
Composite 1500, Russell 1000, Russell 2000, Russell 3000, and Nasdaq 100. For each root, the
acceptance run must attempt the official identity (when entitled), cap proxy, equal-weight vehicle
or point-in-time derived equal series, and every evidenced value/growth leg. It must then exercise
the same technical, ratio, configurable breadth, participation, leadership, concentration,
dispersion, drawdown/volatility, rotation, ranking, and sector/industry/proxy/constituent
workflow. A selector row or one SPY-backed fixture is insufficient.

The Nasdaq 100 sub-gate specifically requires a QQQ-versus-QQQE-style cap/equal deconstruction
only after canonical identity, issuer/relationship, holdings or derived-membership, weighting,
effective/known-at, bar, and coverage evidence has passed. Native ETF weights and locally derived
equal weights are separate methods. Every result carries family/leg identity, membership version,
as-of policy, coverage, exclusions, freshness, and provenance. Missing evidence remains a named
`No verified mapped proxy`, unavailable, or derived state and cannot borrow SPY, QQQ, another
family, or a current-only snapshot. This is an expansion of the acceptance scope, not a relaxed
criterion; unresolved provider, historical, visual, and browser gaps stay in the gap ledger.

## 2026-08-15 — Derived-equal historical concentration sub-gate

For a family with `derived_equal_weight.allowed=true` and no verified equal ETF mapping, acceptance
must call concentration history and verify member-level effective/known-at selection at each bar,
equal-weight method disclosure, membership version, `point_in_time_group_membership` semantics,
null holdings snapshot ID, coverage, and no future-member leakage. A taxonomy root’s later
registration timestamp may not suppress historical member rows in this explicitly reconstructed
path, but ordinary group snapshots may not bypass the stricter root lifecycle policy. The S&P
MidCap-400 fixture proves the one-to-two-member transition and is now passing; complete provider
population, declared rebalance schedules, and all-root browser/visual acceptance remain open.

## 2026-08-15 — Historical concentration/dispersion sub-gate

Historical concentration acceptance must prove timestamp-safe disclosure selection. For each point,
the selected snapshot's composition date and `known_at` must precede the bar timestamp, while the
response preserves snapshot ID, membership version, weight method, top-N/HHI/effective count,
distribution, coverage, and exclusions. A later disclosure must not alter earlier points. The
current two-snapshot fixture and browser history evidence satisfy this contract for the represented
SPY/RSP state, while the derived-equal member-level contract is covered by the dedicated sub-gate
above. Complete eight-root/provider population and broader historical occurrence/visual acceptance
remain explicit open gates.

## 2026-08-14 — Concentration/dispersion sub-gate

For every selected benchmark family leg, the acceptance run must verify that concentration and
cross-sectional dispersion use the same membership snapshot and as-of/known-at policy as the
constituent drill-down. The response must identify whether weights are reported holdings weights,
locally derived equal weights, or unavailable; expose top-N weight, HHI, effective constituent
count, return distribution, covered/eligible/excluded counts, freshness, and exact warnings. A
missing role or weight source is an explicit unavailable/zero-coverage result and cannot borrow a
different family or role. The current SPY/RSP fixture and browser strip are deterministic evidence
for the presentation contract only; historical curves, rebalance continuity, all-eight-root
provider population, and complete style-leg acceptance remain required gates.

Status: `Controlling completion and exception policy`

This policy makes the TC2000 workstation goal rigorous and finishable without pretending that
external evidence or hardware which is unavailable in the current environment has been tested.
It supplements `docs/project-todos.md` section 14 and
`docs/tc2000-visual-parity.md`; where an older document makes an external condition a blanket
completion blocker, this document controls.

## Evidence tracks

### Board-guided visual parity

The 230-image composite board in `docs/tc2000-reference-board.md` is the accepted visual and
interaction authority for every state it represents. A board-covered state is accepted when the
implementation has a measured deterministic local baseline, interaction coverage, and no
unexplained geometry, containment, overlap, console, or accessibility regression. It does not
need a locally captured permission-cleared screenshot of build `25.0.9571`.

Later exact-build evidence can improve or correct a board entry. It must identify a concrete
conflict before reopening already accepted board-guided work.

### Explicit visual gaps

A state with no sufficiently applicable board evidence is a gap, not a pass. It may proceed with
an original-but-TC2000-consistent component decision and an interim test oracle, but the gap must
remain recorded in the board register and visual manifest. The record must name the affected
surface/state, missing evidence, implementation decision, interim oracle, remaining risk, and
evidence that would close it.

### External service and hardware evidence

Provider adapters are accepted through deterministic fixtures, entitlement enforcement,
provenance/fallback behavior, and every live probe that is configured and authorised in the
environment. A missing credential or unavailable provider is a recorded live-evidence gap, not a
reason to block unrelated implementation or to claim live success.

Browser pop-out, cross-window synchronization, restoration, and placement tests are the
acceptance evidence for multi-window behavior. Native physical multi-monitor placement is a
recorded hardware-validation gap and a later audit, not a global blocker.

Endurance is evaluated by documented bounded stress runs, not an impossible “indefinite soak”.
The current minimum is the checked-in sustained runner/resource/cancellation probes plus the
100-round two-pop-out churn guard. Any higher budget must state duration/count, workload,
resource ceilings, outcome, and diagnostics.

## Mandatory flexibility ledger

Every time implementation or acceptance relies on one of the policies above, the developer must
say so in the progress report and append/update a row in the appropriate register:

| Situation | Required record |
|---|---|
| Board is used instead of a direct exact-build image | visual manifest state entry and the board gap register if the evidence is partial |
| No visual reference exists | `docs/tc2000-reference-board.md` gap row plus interim test/oracle |
| Fixture/contract evidence substitutes for a live provider | `ops/handoff.md` and provider/capability records |
| Browser evidence substitutes for physical multi-monitor hardware | `ops/handoff.md` and the applicable parity item |
| Bounded stress substitutes for indefinite operation | `ops/handoff.md` with exact budget and results |

Each progress report must contain a short **Acceptance flexibility used** section. It either lists
the specific ledger entries used in that advance or states `None`. A flexibility is never
implicit, and a gap is never removed merely because an interim oracle passed.

The developer must announce the applicable flexibility in progress commentary before starting
the implementation or evidence run that relies on it. The completion report repeats the same
entry, names the gap that remains open, and links the evidence produced. This prevents a relaxed
criterion from being applied silently or discovered only after a result is presented.

## Current-goal operating rule

The active Codex goal uses this policy as its acceptance interpretation. The following
substitutions are currently authorised for continued implementation, but none is a completion
claim:

This is an explicit goal update, not an informal interpretation: the 230-image browsable
reference board is the working visual target for represented states, while missing exact-build
captures are tracked as state-level gaps. The goal therefore remains active and actionable
against the board; it must not be marked blocked solely because the stronger exact-build audit
cannot run for a represented state. Conversely, the relaxed rule must never be used to silently
close an uncovered state, suppress a mismatch, or present interim evidence as exact-build proof.

| Relaxed criterion | Evidence currently allowed | Gap that remains open |
|---|---|---|
| Locally captured, permission-cleared exact-build V25 media for represented states | The 230-image browsable reference board, its provenance/measurements, and deterministic local baselines | Any state or detail not sufficiently represented by the board; stronger exact-build evidence may still correct a concrete conflict |
| Live provider credentials for every acceptance run | Canonical DB fixtures, adapter contracts, entitlement tests, and authorised live probes where configured | Live coverage/terms/quota evidence unavailable in this environment |
| Native physical multi-monitor validation | Browser pop-out, cross-window sync, restoration, and blocked-pop-out tests | Physical monitor placement and OS window-manager behavior |
| Indefinite soak testing | Bounded churn/resource/cancellation runs with an explicit budget | Longer-duration operational endurance beyond the recorded budget |

These rows must be repeated in the relevant handoff entry whenever used. The implementation may
continue past them, but the corresponding gap IDs remain actionable until closure evidence is
recorded. A progress report that uses none of these substitutions must say `Acceptance flexibility
used: None` explicitly.

### Required reporting wording

Every advance that relies on a relaxed criterion must identify the substitution before the work
or evidence run starts, then repeat it after the run with: (a) the gap ID(s) still open, (b) the
interim evidence produced, and (c) the concrete evidence or environmental condition needed to
close the gap. “Accepted” means accepted on the documented interim track only; it never means
the gap has disappeared.

## Completion decision

The workstation may be presented for user-led fine-tuning when all in-scope implementation,
functional, security, migration, performance, and deterministic visual/interactions acceptance
checks pass; every board-covered state has evidence; and every remaining external or
unrepresented-state limitation is explicitly recorded with its interim oracle and closure path.

It must not claim exact TC2000 verification for a gap, conceal a limitation with a broad image
mask, invent provider data, or loosen the product boundaries. The outstanding flexibility ledger
is part of the handoff and remains actionable follow-up work.

## Initial robust workstation gate (not overall completion)

The first genuinely usable TC2000-style workstation is a narrower operational gate inside the
single continuous goal. It may be presented for daily top-down analysis once the following are
true in a clean authenticated deployment:

- the `US Top Down` layout opens directly into the workstation shell;
- SPY/RSP benchmark comparison, all 11 sector views, sector-to-industry/proxy/constituent
  drill-down, and `XLK/SPY`, `XLK/XLE`, `NVDA/XLK`, and `NVDA/SPY` ratios work without seeded
  fixture-only routing;
- the primary chart, linked symbol/timeframe groups, keyboard traversal, watchlist sorting and
  filtering, persistence, pop-outs, notes, alerts, and freshness/error states work together;
- Python code can be reused as a column, condition/scan, alert, and chart/study output, and the
  positive-close streak Study Lab example completes with inspectable metrics and occurrences;
- the clean browser, backend, type/build, and service-log gates pass with no known shared-state,
  security, or data-integrity defect.

This gate does **not** require all 496 ETF issuers to have native routes. Provider work is
prioritised by the universes needed for the core US workflow; the remaining issuer audits,
broader free-source coverage, exact-build/reference gaps, native physical-monitor validation,
and endurance evidence remain open completion work and must stay visible in the handoff. Seeded
fixtures may continue to support deterministic regression tests, but they cannot be the sole
evidence for this initial live-workstation gate.

### 2026-08-11 gate evidence

The rebuilt branch deployment satisfies this operational gate on the canonical, non-seeded path:

- branch health reports `e2e_seed_instruments=false` and `e2e_seed_market_data=false`;
- the complete authenticated Chromium matrix passes `88/88`, including live canonical benchmark
  and sector membership, SPY/RSP comparison, sector-to-industry/proxy/constituent drilldown,
  ratio editing and automatic ratios, linking, keyboard traversal, persistence, pop-outs, notes,
  alerts, freshness/error states, Python reuse, and the positive-close Study Lab study;
- the frontend Vitest suite passes `691/691`, type-check and production build pass, and the
  branch service/log audit is clean for tracked runtime-error signatures.

This establishes the initial daily-analysis workstation as operational. It is not the overall
completion claim: exact-build/unrepresented visual states, broader free-source/provider evidence,
native physical-monitor placement, beyond-bounded endurance, and the final requirement audit remain
open and actionable. Acceptance flexibility used: **None**.

### Expanded benchmark-family gate

#### Role participation sub-gate

For every family root and every independently mapped cap/equal/value/growth role, the acceptance
run must exercise the role-participation batch and verify that the UI renders side-by-side
participation values without collapsing roles or substituting another universe. The check must
cover SMA participation, near-52-week-high threshold/lookback parameters, trend participation,
coverage/eligible/excluded counts, membership/provenance lineage, and role-local unavailable or
partial states. Relative strength to the family cap is shown only when aligned bars exist and must
retain the same warning semantics.

This sub-gate proves the current participation presentation and its data contract only. It does
not waive historical participation, arbitrary/nested user predicates, occurrence linking, Study
Lab promotion, or the wider ranking/rotation/concentration/dispersion gates. Missing data remains
an explicit gap; no acceptance flexibility is used.

#### Historical role participation sub-gate

The family acceptance run must also call the historical role batch with a bounded limit and verify
that each available role returns aligned SMA20/50/200 points with its own membership/provenance
lineage. A missing current bar at a timestamp must reduce that role's eligible coverage rather
than being forward-filled. Missing mappings or holdings must remain role-local unavailable states.
This sub-gate validates historical SMA participation only; it does not close historical
near-high/new-high/trend/relative-strength studies, arbitrary condition history, occurrence
linking, ranking, rotation, or complete family population. No acceptance flexibility is used.

#### Family role-ranking sub-gate

The family run must request a declared rank period and verify independent cap/equal/value/growth
return cells, rank order, and cap-relative spreads. The UI must show the role order without hiding
unavailable mappings or inventing a benchmark. This sub-gate covers current leadership ranking
only; historical ranking, cross-family ranking, relative rotation, concentration, and dispersion
remain separate gates. No acceptance flexibility is used.

#### Cross-family ranking sub-gate

The family acceptance run must call `GET /analysis/benchmark-families/ranking` for the complete
configured root set and for an explicit subset. It must verify rank-period selection, independent
canonical cap-proxy cells, membership/provenance and coverage lineage, role-local unavailable
states, and optional benchmark-relative spreads only on aligned bars. The workstation must render
the result without a route change and must not substitute a different family. The authenticated
browser oracle must additionally verify that the cross-family strip does not overlap the custom
condition editor or alter its controls; this is a required interaction/layout check, not a maskable
pixel exception. Historical curves, rotation tails, concentration, dispersion, and populated
provider evidence remain separate gates. No acceptance flexibility is used.

#### Historical cross-family ranking sub-gate

The acceptance run must call `GET /analysis/benchmark-families/ranking/history` for the complete
root set and an explicit subset, with a declared rank period, bounded limit, and `as_of`. It must
verify observed-timestamp points, rank order at each timestamp, optional benchmark-relative values,
coverage, freshness, and row-local unavailable states. The result must not forward-fill gaps or
borrow another family's cap proxy. The workstation must expose that historical evidence beside
the current cross-family ranking and retain the same condition-editor interaction/layout checks.
Relative-rotation tails, concentration, dispersion, and complete provider-backed population remain
separate gates. No acceptance flexibility is used.

#### Benchmark-family relative-rotation sub-gate

For every configured family root, acceptance must call the family relative-rotation contract with
declared timeframe, sampling, lookback, tail length, adjustment, and optional `as_of`. It must
verify cap/equal/value/growth role identity, cap-relative aligned ratios, transparent trend and
momentum, state/transition/time-in-state fields, tail timestamps, coverage, freshness, and explicit
unavailable states. A family must use its own cap proxy; SPY, QQQ, another family, or a current-only
substitute is not permitted. The uPlot tool must expose all eight family choices, resolve the cap
benchmark in its region label, preserve the generic group rotation route, and keep missing style
legs visible without covering controls. Longer historical tails, concentration, dispersion, and
fully populated provider evidence remain separate gates. No acceptance flexibility is used.

#### Dated holdings coverage sub-gate

Before a family/leg can be presented as historically usable, acceptance must call
`GET /analysis/benchmark-families/{family_key}/coverage` and verify that cap/equal/value/growth
roles retain independent snapshot dates, source/provenance, completeness, resolution, and
composition-versus-known-at semantics. An explicit `as_of` must exclude future disclosures and
must not fail by substituting another role. The workstation must expose these statuses and counts
without implying that a role with zero snapshots has historical coverage. This sub-gate proves
coverage evidence and honest presentation; it does not waive the separate requirement for a
complete rebalance/membership history or user-selectable historical drill-down.

#### Latest US-family perspective clarification

The family gate covers eight complete US analysis perspectives: S&P 500, S&P MidCap 400, S&P
SmallCap 600, S&P Composite 1500, Russell 1000, Russell 2000, Russell 3000, and Nasdaq 100. For
each root, the acceptance run must attempt the official identity (where entitled), cap proxy,
equal-weight vehicle or explicitly derived equal series, and every evidenced value/growth
sub-index or ETF. It must then run the same technical, cap/equal/style spread, parent/peer ratio,
condition-driven breadth, participation/leadership, concentration/dispersion, correlation,
drawdown/volatility, relative rotation, cross-family ranking, seasonality/regime, and
sector/industry/proxy/constituent drill-down contracts. The Nasdaq 100 cap/equal fixture is
QQQ/QQQE (or another verified pair) only after canonical identity, relationship, holdings, and
bar evidence passes.

This is not satisfied by selector presence or a single SPY-backed demonstration. Each mapped leg
must preserve role, native-versus-derived weighting, membership/rebalance version, effective and
known-at semantics, adjustment, coverage, exclusions, freshness, and provenance through charts,
watchlists, breadth results, ratios, scans, gauges, Study Lab artifacts, and exports. Missing or
unverified official/equal/value/growth/holdings evidence remains a named gap or explicit
`No verified mapped proxy`/unavailable/derived state; it never silently substitutes SPY, QQQ,
another family, a current-only snapshot, or a name-based relationship. No acceptance threshold is
relaxed by this clarification.

The family gate is also a visual/workflow matrix. The acceptance run must launch each of the
eight roots (S&P 500/400/600/1500, Russell 1000/2000/3000, Nasdaq 100), select every mapped
cap/equal/value/growth leg, and exercise the same top-down, breadth, ratio, ranking, rotation,
and member drill-down contracts. The Nasdaq 100 cap/equal fixture is QQQ versus QQQE only when
canonical identity, holdings, and relationship evidence are verified. Missing or ambiguous
family/style evidence is a labelled gap or unavailable state, never a silent fallback and never
a reason to lower the global visual thresholds.

The QQQE provider-route sub-gate is now evidenced: canonical route metadata selects the explicit
Direxion adapter, and an opt-in live probe parsed the public symbol-scoped holdings export. This
does not satisfy the broader Nasdaq-100 fixture by itself. Historical rebalance continuity,
point-in-time membership, bars, and populated browser cap/equal visuals remain separate required
acceptance cases.

The top-down completion bar now covers S&P 500/400/600/1500, Russell 1000/2000/3000, and Nasdaq
100, not only SPY/SPX. The authenticated and backend acceptance matrix must prove that each family
can be selected as a versioned universe and exposes, where source evidence permits, its official
identity, cap-weighted proxy, equal-weight proxy/derived series, and value/growth variants. A
missing mapping must display `No verified mapped proxy` with provenance; it cannot silently fall
back to SPY, QQQ, or an unrelated family.

For every available family/style variant, acceptance must exercise the same benchmark technicals,
cap/equal/style spread, generic predicate breadth, participation/leadership, concentration,
dispersion, drawdown/volatility, relative rotation, cross-family ranking, and member drill-down
contracts. Equal-weight results must state whether weights are ETF-native or locally derived from a
point-in-time membership snapshot. The Nasdaq 100 must have a cap/equal deconstruction equivalent
to SPY/RSP (for example QQQ versus a separately verified equal-weight proxy such as QQQE). This is
a scope expansion, not a relaxation; incomplete provider, membership, or visual evidence remains
an explicit gap.

The family gate also covers factor/style analysis, not only benchmark-versus-equal pairs. The
acceptance run must attempt the verified value and growth variants for S&P 500/400/600/1500 and
Russell 1000/2000/3000, record `No verified mapped proxy` for any family without an evidenced
variant, and prove that available variants inherit the benchmark technical, breadth,
participation, concentration/dispersion, volatility/drawdown, rotation, ranking, and member
drill-down contracts. Cross-family ratios (for example S&P 500 versus Russell 2000 or a value leg
versus its cap parent) must preserve timestamp alignment, adjustment, membership version,
coverage, and provenance. A current ETF snapshot cannot satisfy a historical family study without
an explicit current-snapshot/survivorship warning, and no relationship may be inferred from naming
alone.

#### Family/style acceptance fixture coverage

The family matrix is evaluated as eight complete perspectives, not as a count of selector rows.
For each of S&P 500, S&P MidCap 400, S&P SmallCap 600, S&P Composite 1500, Russell 1000,
Russell 2000, Russell 3000, and Nasdaq 100, the acceptance run must attempt the cap proxy,
equal-weight vehicle or derived equal series, and every evidenced value/growth sub-index or ETF.
The same selected family/leg must feed technicals, parent/peer ratios, generic breadth,
participation/leadership, concentration/dispersion, drawdown/volatility, relative rotation,
cross-family ranking, and sector → industry/proxy → constituent drill-down. For Nasdaq 100,
QQQ/QQQE is the explicit cap/equal fixture only after canonical identity, holdings, and
relationship evidence pass.

Candidate symbols such as SPY/RSP, SPYG/SPYV, MDY/MDYG/MDYV, SLY/SLYG/SLYV, IWB/IWF/IWD,
IWM/IWO/IWN, IWV, and QQQ/QQQE are discovery inputs and test fixtures, not permission to infer a
relationship. Each accepted leg must retain source/issuer evidence, role, membership or derived
weight method, effective/known-at dates, bar coverage, adjustment, freshness, and exclusions.
Absent or unverified legs must produce `No verified mapped proxy`, unavailable, or explicitly
derived output and remain in the gap ledger; they must not silently substitute SPY, QQQ, another
family, or a current-only snapshot. This broadens the required analysis perspectives and does not
relax any visual, provenance, historical, or functional threshold.

The dated holdings acceptance also distinguishes the requested evaluation date from the issuer's
returned composition date. A provider may return the nearest earlier snapshot; persistence must
retain that composition date, retain the requested date as `as_of_date`, reject future-dated
responses, and expose both values in provenance. Rewriting the returned date to the request would
invalidate point-in-time membership and is a failed acceptance case.

Family backfill acceptance additionally requires a bounded role-aware maintenance operation. A
requested family/date/role set must return one result per requested role, with snapshot and
composition evidence for refreshed legs and explicit unavailable or failure entries for the rest.
The operation must continue independent legs after one failure, and a missing value/growth/equal
mapping must never be represented as a cap-leg success. This proves orchestration semantics only;
it does not close the requirement for complete historical population across all families.

The range form of this operation accepts at most 64 requested dates, de-duplicates them, processes
them chronologically, and returns one dated summary per normalized date. Acceptance must verify
that a duplicate date does not trigger duplicate work and that a failure or unavailable mapping
on one date/role does not erase independent results for other dates/roles. The range contract
still cannot be used as evidence of complete official membership or rebalance continuity without
the corresponding source snapshots and point-in-time validation.

### Expanded condition-driven breadth gate

The fixed Market Breadth panel is not sufficient evidence for the broader breadth requirement.
Completion acceptance must prove one generic definition contract across multiple universe types
and conditions. At minimum, the authenticated browser and backend suites must demonstrate:

- a point-in-time, explicitly labelled SPY ETF-proxy constituent universe;
- percentage of eligible members above a configurable 200-day average;
- percentage of eligible members within 1% of their 52-week high;
- identical condition/universe semantics for current snapshots and aligned historical series;
- denominator, coverage, exclusions, provenance, membership date/version, and freshness visible
  at the result surface;
- passing/failing member drill-down and symbol publication into linked charts;
- reuse of the same definition as a Study Lab artifact and, where output contracts permit, a
  chart pane/plot, watchlist column/filter, EasyScan condition, Market Gauge, alert, and export;
- partial data, missing bars, incomplete holdings, current-snapshot-versus-point-in-time, and
  unsupported-capability paths returning explicit structured warnings rather than silently
  changing the universe or condition.

The existing MA20/50/200, near-high/low, new-high/low, trend, and distance controls remain
convenience presets and retain their current regression coverage. They cannot close this gate
unless they execute through the generic definition contract. No visual threshold or acceptance
flexibility is being relaxed by this expansion.

Implementation checkpoint (2026-08-14): the generic current-snapshot contract is now present at
`POST /analysis/breadth`, with local group, ETF-holdings-proxy, and explicit-symbol resolution;
deterministic condition evaluation; stable definition/membership hashes; per-member results;
coverage, freshness, and structured exclusions. The breadth tool exposes the first composer for
the two representative condition forms. This evidence closes only the initial backend/UI slice;
the historical, unified-Python, independent-uPlot, promotion, and full point-in-time ETF gates
remain required and are not being silently treated as complete.

Implementation checkpoint 2 (2026-08-14): aligned historical generic breadth and isolated Python
reuse are now implemented. The API and runner use the same condition definition, expose per-date
denominators/coverage/exclusions, and never forward-fill a member absent at a timestamp; the
workstation renders the history with uPlot and Study Lab includes two representative factory
starters. This does not close the gate: ETF point-in-time browser evidence, arbitrary Python
combination parity, and promotion/reuse acceptance remain mandatory.

#### Breadth “around what?” acceptance rule

Acceptance must verify that the user can choose what is being measured and what it is being tested
against, rather than only choosing among fixed breadth labels. The saved definition must expose:

- the canonical universe and point-in-time membership policy;
- the measured field or derived Python series;
- the target/relationship and operator (average, threshold, range, percentile, prior high/low,
  benchmark/peer ratio, event, or derived series);
- timeframe, lookback, session, adjustment, timestamp alignment, and as-of/known-at policy;
- nested AND/OR/NOT composition with clause-level diagnostics.

The acceptance fixtures must include both `close > SMA(close, 200)` and “within 1% of the rolling
252-session high” over the same explicitly labelled SPY ETF-proxy universe, plus at least one
relative-strength or volume/volatility relationship. Each fixture must show aggregate history,
per-member pass/fail, denominator/coverage, exact exclusions, provenance, and current-versus-
historical semantics. A fixed metric route or selector that cannot express the target relationship
does not satisfy this gate, even if its aggregate percentage is numerically correct.

#### Dated family analysis sub-gate

When a benchmark family has disclosed holdings snapshots, the workstation must offer those
composition dates as selectable `as_of` values. The chosen date must be carried consistently by
family overview, role constituents, ratio comparisons, and breadth current/history calculations;
the client must keep latest and historical results in distinct cache entries. Snapshot dates are
role-specific and may be unavailable, so the UI must preserve independent status and show no
verified date rather than borrowing SPY, QQQ, or another family's date. This sub-gate is covered
by store `57/57`, full frontend `828/828`, type/build, and authenticated browser `1/1` evidence.
It does not waive the remaining requirement to populate and validate historical evidence for all
eight family roots and their evidenced style legs.

#### Family technicals sub-gate

Selecting any family root must expose one independently labelled technical state for each configured
cap/equal/value/growth leg. The state includes last price, RSI14, SMA20/50/200, 52-week position,
volume ratio, freshness, warnings, timeframe, adjustment, membership version, and `as_of` lineage.
An unavailable role remains a role-local warning. It is not acceptable to show only the cap leg or
to substitute SPY/QQQ. This sub-gate is covered by family integration `8/8`, store `58/58`, full
frontend `829/829`, type/build, Ruff, and authenticated browser `1/1`; it does not close the
remaining historical-data, breadth, rotation, ranking, dispersion, or exact/unrepresented visual
gaps.

Implementation checkpoint 3 (2026-08-14): nested composition and scalar comparisons are now
implemented in both the canonical API evaluator and isolated Python runner. Focused service/runner
coverage passes `93/93`, generic API/history integration passes `2/2`, and the workstation exposes
field/operator/target/benchmark controls plus aggregate pass/fail member drill-down. This closes
the previously missing compositional API/runtime slice only. User-authored Python condition
execution, full visual condition-tree editing, chart-linked historical occurrences, and all
promotion targets remain mandatory acceptance work; no visual threshold or acceptance flexibility
was changed.

#### Latest breadth expansion — quantifier and target-scope contract

The acceptance oracle now treats breadth as `count(predicate(member, timestamp)) / eligible`
over the selected point-in-time universe. It is not sufficient to expose a larger list of preset
labels. The visual editor and API contract must independently identify the measured field/series,
the target/relationship, operator, lookback, timestamp alignment, and composition. The target
scope must be explicit: member-level thresholds, moving averages, prior highs/lows, benchmark or
peer ratios, events, and derived series are evaluated per member before aggregation; a
cross-sectional rank/percentile or group statistic is a separate derived output.

The representative acceptance set is expanded to include the existing 200-day and within-1%
52-week-high predicates plus volume-vs-average, an RSI range, a selected-member/benchmark ratio,
and a nested combination. Each must produce the same aggregate, member pass/fail, history,
state-change/occurrence, denominator, coverage, exclusion, provenance, and reproducibility
outputs. The same immutable definition must be reusable in Study Lab and every compatible
uPlot/list/filter/scan/gauge/alert/export target. Python is the authoritative escape hatch for
predicates outside the visual subset, but only through the isolated runner and declared dataset
manifest. This is a requirements expansion, not an acceptance relaxation; the compact composer,
platform-owned comparisons, visual tree, Python execution, historical linking, and promotion gaps
remain open until their own evidence passes.

### 2026-08-11 bounded endurance evidence

The governed two-popout churn guard was run with `TC2000_POP_OUT_CHURN_ROUNDS=100`. Both performance
tests passed (`2/2`) in `2.6m`: initial multi-chart/pop-out recovery remained bounded, and all 100
two-popout open/close rounds returned to the source tool/canvas baseline. Chromium memory ceilings
and browser diagnostics passed, and the narrowed backend/worker/research-runner runtime audit found
no tracked error signatures. This is the documented bounded-stress substitution for indefinite soak;
longer-duration endurance remains open. Acceptance flexibility used: **bounded stress in place of
indefinite soak**.

## Goal-level blocker tie-breaking

An isolated, recoverable defect in one tool or interaction must not block the entire TC2000 rework by default. The defect remains a named acceptance failure with a reproduction, attempted fixes, regression tests, and current evidence, while unrelated in-scope implementation and validation continue.

Escalate a defect to a goal-wide blocker only when at least one of these is true:

- it prevents a broad class of workflows or corrupts shared persisted state;
- it creates a security, data-integrity, sandbox, or irreversible-loss risk;
- it invalidates the acceptance oracle for a major surface rather than one localized state;
- no meaningful in-scope work or evidence can proceed independently;
- the same failure remains after three independently validated remediation attempts and the remaining work requires an external dependency or user decision.

A localized Add Tool tab-activation defect is therefore tracked as a blocking acceptance failure for that interaction, but does not by itself block the whole product goal. Each attempted fix must be followed by focused automated verification, broader regression checks where relevant, and an explicit report of whether the defect remains.

This rule is also an explicit instruction of the active Codex goal: when two acceptance signals
conflict, prefer the smallest scoped interpretation that preserves safety and truthful reporting.
Continue independent implementation and tests, record the weaker signal as an open acceptance gap,
and only stop the whole goal for the escalation conditions above. A transient or ordering-sensitive
test failure must be reproduced in isolation and in the nearest relevant sequence before it is
classified as a product blocker; if it cannot be reproduced, retain the failure evidence and add a
regression guard rather than treating it as resolved or blocking the goal.
## 2026-08-17 — Universal source watchlist acceptance

The source-universe gate treats every index, index ETF, market group, managed scan, combo, and
personal list as a selectable watchlist source. Locked system sources are immutable in membership
but remain usable by Market Map, breadth, scans, alerts, linked charts, and Study Lab; personal and
managed sources retain their own edit rules. The generic breadth API accepts canonical source IDs
(`watchlist:*`, `market-group:*`, `etf-holdings:*`) plus the legacy numeric personal-list shorthand,
resolves through the local provenance-aware source service, and preserves point-in-time exclusions.

Acceptance must prove the same predicate and target controls against at least one editable personal
list and one locked index/ETF source, including member denominator, pass/fail drill-down, current and
historical output, source lock/provenance, freshness, coverage, and no provider fan-out. The UI must
show source selection and lock status rather than presenting a fixed SPY-only breadth universe.
This sub-gate is implemented and covered by canonical watchlist-source integration `2/2`, frontend
full-suite `853/853`, `vue-tsc`, and production build. The subsequent Market Map publication and
durable-cache checkpoints close the direct launch and result-cache portions; named snapshots,
complete historical population, and final visual board approval remain open.

## 2026-08-17 — Isolated Python map-colour evidence

The Market Map Python-colour slice is accepted only as a completed-run consumer: the selected
condition asset must be user-owned and active, the run must be completed by the dedicated isolated
runner, and the map request may consume only its immutable `batch_cells` artifact. Focused frontend
coverage proves asset selection, queue/poll ordering, and run-ID submission; backend compile/schema
checks prove request validation, ownership/completion checks, numeric/Boolean validation, per-cell
warning preservation, and cache serialization. Docker-backed integration could not run in the
current sandbox because the Docker socket is permission-denied; this is an environmental validation
gap, not acceptance evidence. Event/peer/group predicates, richer Python output promotion,
point-in-time area weights, and exact visual baselines remain open.

## 2026-08-17 — Event predicate Market Map evidence

Event-colour acceptance uses the canonical local event calendar rather than provider fan-out. The
fixture must distinguish a member with a loaded empty calendar (eligible false) from a member whose
event data has never been loaded (`event_data_unavailable`), and must verify event type, lookback,
observation-time alignment, pass/fail colour, denominator, coverage, and cache identity. Focused
component/static checks cover authoring and contract wiring; Docker-backed integration remains
required when the authorized runtime is available. The exact event-programmable V25 visual state is
not represented in the board and remains an explicit visual gap.

## 2026-08-17 — Reference-source map comparison evidence

Reference-source acceptance verifies that a second canonical source is resolved independently,
that its membership version and source descriptor remain in the response, and that its derived
equal-weight series uses an explicit baseline, exact timestamp alignment, and no forward-fill.
Short-window relative-return maps must produce a value when two valid sessions exist, while missing
or unaligned reference bars remain explicit warnings. The focused Docker-backed integration fixture
passes this contract; richer cross-sectional group statistics and point-in-time area semantics
remain open.

## 2026-08-17 — Numeric Python area evidence

Area-output acceptance requires a completed user-owned isolated numeric-series run. Positive finite
values must drive tile area; missing, invalid, and non-positive values must remain explicit warnings;
Boolean runs must be rejected rather than coerced into geometry. The Docker-backed watchlist fixture
passes numeric sizing and Boolean rejection, with frontend authoring/persistence covered by the
Market Map component suite. Provider-declared numeric fields and point-in-time market-cap/weight
semantics remain open.

## 2026-08-17 — Provider numeric area evidence

Provider-field area acceptance requires an allow-listed field, local persisted value, and field-level
provenance. The fixture proves a provenance-bearing value sizes a tile and that an unproven value is
excluded with `unproven_area_field`; missing or malformed values follow the same explicit-warning
path. Workstation authoring and persistence are covered by the 11-case Market Map component suite.
Point-in-time market-cap/weight semantics and exact V25 visual approval remain open.

## 2026-08-17 — Market Map ordering evidence

Ordering acceptance covers largest-area, strongest-colour, and symbol A–Z modes inside the active
hierarchy node, null-last behavior, deterministic symbol tie-breaking, configuration persistence,
and unchanged canonical selection/publication. Focused component coverage is 11/11 and the full
frontend suite remains 860/860. Exact V25 ordering-control imagery is not represented and remains a
tracked visual gap.

The browser/component acceptance also requires the coverage distinction to be visible in the
workstation summary, legend, and tile detail. The focused Market Map suite now asserts combined,
colour, and area coverage labels for a fully covered map; partial fixtures must retain the same
labels with the appropriate reduced values.

The layout acceptance additionally proves that null, non-finite, and non-positive area cells produce
no drawable geometry while remaining available for warning and coverage inspection. This prevents
the frontend from undoing the backend's honest partial-data semantics.

The Market Map breadth gate now also requires the advanced editor to submit a nested condition tree,
not merely a named preset. Focused component acceptance proves a configurable 52-week predicate is
serialized into the same `color_metric=breadth` request; the shared condition-editor suite covers
the recursive add/remove/group mechanics. Python-derived leaves and full promotion fan-out remain
separate open gates.

## 2026-08-17 — Universal locked-watchlist heatmap evidence

The heatmap acceptance gate is source-polymorphic: the same request and renderer must work for an
editable personal list and a locked index/ETF, sector, industry, managed, combo, or explicit-symbol
source. The locked state is an authorization/membership property only; it must not remove the
source from follow, selection, hierarchy, sorting, snapshot, or cross-tool publication flows.

Coverage acceptance now checks three values at cell, node, and root level: colour coverage, area
coverage, and their combined minimum. A fixture with a valid colour and an unproven area field must
show colour coverage `1`, area coverage `0`, combined coverage `0`, no tile geometry for that member,
and the exact `unproven_area_field` warning. This prevents an apparently complete heatmap from hiding
missing sizing data while preserving the useful colour analysis. Docker-backed watchlist integration
passes `29/29`; focused Market Map component coverage is `11/11`; frontend type-check and production
build pass. The remaining gate is point-in-time weighting, family population, direct definition
promotion, and final visual-board approval.

## 2026-08-17 — Source follow/pin governance evidence

Canonical source descriptors may be followed or pinned without changing membership governance.
Authenticated settings persist user-isolated followed and pinned source IDs; the Market Map picker
orders pinned sources first and retains unfollowed locked index/ETF/group sources for direct
selection and analysis. Focused Market Map coverage and dedicated user-settings tests pass; this
closes preference persistence only and does not close point-in-time weighting, family population,
direct definition promotion, or visual-board gaps.

The source-publication gate now also accepts a full-source launch from Market Map without a tile
selection. The launched Breadth or Study Lab tool receives the canonical source as its complete
universe and optional selected-member context. A breadth map can additionally create an immutable
Study-Lab asset from its current condition/configuration, preserving the condition tree, source ID,
period/timeframe/adjustment defaults, and generated Python source. Promotion of that definition to
every compatible target remains an open versioning/promotion fan-out gate.

The promotion gate has partial closure: completed Boolean Study results visibly offer watchlist
filter and Market Gauge actions, and both reuse the same persisted EasyScan created from the
immutable Boolean code version. This is not treated as complete direct fan-out for arbitrary
multi-output Market Map/Study assets; target-specific output selection and lineage-preserving
promotion to every compatible target remain tracked.

The structured-artifact sub-gate now also passes: a completed multi-output Study exposes filter,
scan, Gauge, and alert actions for each Boolean artifact, creates a condition version with the
artifact output name, and reuses one EasyScan across those targets. Scalar/series/event artifacts
retain their compatible column/plot/signal actions. Full fan-out across every artifact type and
target, including direct map-created definitions, remains open; no acceptance flexibility was used.
## 2026-08-19 — Derived combo watchlists share the universal heatmap oracle

The authenticated universal-watchlist oracle now exercises three source classes in one flow:
locked canonical constituents, editable personal watchlists, and a user-owned derived combo source.
The combo source is selected as `combo:analysis-combo`, retains `source_kind=combo`, remains locked
for direct membership editing, and reaches the same Market Map batch request, tile renderer,
coverage/history status, and downstream publication contract. The test does not create a second
heatmap implementation or derive membership from ticker text.

`F8s-market-map-watchlist` passes `1/1`; full frontend Vitest remains `914/914`; type-check,
production build, and diff checks pass. No acceptance flexibility was used. Combo definition/version
reconstruction, provider-backed member-bar history, exact V25 source-picker/action visuals, and the
broader eight-root family matrix remain open and explicitly tracked.
