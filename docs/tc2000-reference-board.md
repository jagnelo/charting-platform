# TC2000 Version 25 composite reference board

## 2026-08-19 — Source-polymorphic heatmap reference note

The working board treats the heatmap as one TC2000-style surface over arbitrary watchlists. Locked
index/ETF constituent lists differ in membership governance and provenance, not in tile rendering
or downstream actions. The bounded dated family maintenance worker supports population of those
locked sources but does not create a distinct visual mode. Missing exact V25 maintenance, loading,
unavailable, and provenance captures remain `required_missing` rather than being inferred silently.

## 2026-08-19 — Scheduled family-population ordering has no new visual claim

The scheduled SEC maintenance path now prioritizes configured benchmark-family proxy identities
under a bounded profile quota. This is an internal provider-maintenance ordering change feeding the
existing locked/source-polymorphic watchlist contract; it does not add a visible tool or invent a
V25 maintenance panel.

Gap status: no visual state is promoted by this change. Existing `required_missing` maintenance
states for queued, partial, failed, retrying, and recovered family/ETF holdings remain open. Interim
oracle: task/service tests `5/5`, workstation bootstrap `7/7`, backend units `1260/1260`, ETF
holdings integration `63/63`, and direct family route audit `342 passed, 1 skipped`. No visual
threshold, mask, provider requirement, or acceptance rule was relaxed.

## 2026-08-19 — Market Map selection handoff controls remain unrepresented

The functional Market Map now offers `Open in Chart`, `Compare in Chart`, and `Relative
Strength` actions for selected canonical members, with identical behavior across locked
index/ETF and arbitrary watchlist sources.

Gap status: `required_missing` for the exact V25 toolbar placement, button labels, selected-state
chrome, disabled-state treatment, ratio handoff confirmation, and floating/docked variants.
Interim oracle: Market Map component `32/32`, workstation pop-out bindings `23/23`, full frontend
Vitest `914/914`, type-check, production build, and diff checks. No visual threshold or mask was
relaxed. Evidence needed to close the gap: a board capture showing this selected-member action
surface in the relevant V25 workspace state.

## 2026-08-19 — Lazard issuer outage/fallback needs a V25 visual oracle

The JPY locked source now has a functional outage path: Lazard directory 503, bounded SEC candidate
search, wrong-series rejection, and identity-verified recovery. This is visible behavior required
by the universal Market Map source lifecycle, but it is not a reason to invent a V25 screenshot.

Gap status: `required_missing` for exact V25 provider outage, candidate rejection, fallback progress,
stale/partial badges, retry, and recovery-complete visuals. Interim oracle: Lazard-focused tests `3/3`,
SEC/parser/adapter units `507/507`, live JPY `1/1`, Ruff, compileall, and diff checks. No visual
threshold or mask was relaxed.

## 2026-08-19 — Derivative-backed ETF exposure needs a V25 visual oracle

The NVD source now has a real provider-backed state in which the issuer reports cash and an NVDA
swap rather than a conventional equity workbook. The Market Map can therefore use the same locked
watchlist surface while displaying the source's derivative nature and coverage warning.

Gap status: `required_missing` for exact V25 rendering of derivative/cash rows, exposure-type badges,
coverage-warning copy, source-quality details, and how those rows appear in heatmap sizing/colour and
constituent drill-down. Interim oracle: GraniteShares-focused tests `3/3`, SEC/parser/adapter units
`506/506`, live NVD `1/1`, Ruff, compileall, and diff checks. No visual threshold or mask was relaxed.

## 2026-08-19 — Wrong-series and reorganization recovery states need V25 captures

The backend now rejects an SEC filing when its series/class identity does not match the selected
locked ETF source, and MAGA can move from successor Truth Social identity to curated predecessor
identity after its 2026 reorganization. These are functional correctness states for the universal
watchlist/heatmap pipeline, not reasons to accept an unverified visual approximation.

Gap status: `required_missing` for exact V25 source-maintenance visuals covering identity mismatch,
candidate-filing rejection, predecessor fallback, filing provenance, retry progress, and the final
ready/partial state. Interim oracle: wrong-series unit regression, SEC/parser/adapter units `505/505`,
live MAGA `1/1`, live TSCV `1/1`, Ruff, compileall, and diff checks. No visual threshold or mask was
relaxed; the missing capture remains tracked until the browsable V25 reference board supplies it.

## 2026-08-19 — Thrivent issuer-blocked fallback has no exact V25 visual oracle

The TSCV issuer CSV can return 403 to backend clients even though the official product page exposes
the download. The workstation now recovers with SEC EDGAR through curated fund identity and clearly
labels the result as a filing fallback, retaining the original issuer failure.

Gap status: `required_missing` for exact V25 maintenance/source-picker visuals covering issuer 403,
fallback progress, stale/partial coverage badges, retry, and recovery-complete states. Interim
oracle: adapter/taxonomy units `508/508`, focused provider regressions `11/11`, live TSCV `1/1`,
Ruff/compileall/diff checks. No visual threshold or mask was relaxed.

## 2026-08-19 — SFY primary/fallback state is functional but lacks exact V25 visuals

The SFY route now uses the currently linked SoFi holdings artifact and recovers through SEC EDGAR
when the issuer/WAF path fails. SEC reconstruction is explicitly marked `partial` when it returns
fewer than the verified primary route's 300 rows, so a degraded universe cannot masquerade as a
complete locked watchlist.

Gap status: `required_missing` for exact V25 provider-maintenance visuals covering stale route,
issuer failure, fallback progress, partial coverage warning, retry, and recovery-complete states.
Interim oracle: adapter/taxonomy units `507/507`, Ruff/compileall/diff checks, and opt-in live SFY
probe `1/1`. The implementation does not relax visual acceptance; it records the behavior to match
once an authoritative V25 capture exists.

## 2026-08-19 — Provider fallback behavior is functional but has no exact V25 visual oracle

The live QQQ provider route demonstrated a concrete recovery state: the Invesco current holdings
endpoint returned HTTP 500, while SEC EDGAR succeeded after the canonical route supplied its curated
identity. The workstation now preserves issuer-route failure/fallback provenance and can keep the
locked source usable through that free fallback.

Gap status: `required_missing` for exact V25 maintenance-panel and source-picker visuals covering
issuer failure, fallback progress, stale/partial badges, retry controls, and recovery completion.
Interim oracle: Invesco adapter unit `494/494` and opt-in live QQQ probe `1/1`. This evidence does
not relax visual acceptance; it only records the behavior available for implementation against the
reference board once an authoritative capture exists.

## 2026-08-19 — Explicit arbitrary-ETF add-source state remains a visual gap

The universal Market Map now lets the user enter a canonical ETF symbol and explicitly bootstrap
its locked constituent source. The source catalog is refreshed and the same `etf-holdings:<SYMBOL>`
map path is selected; pending membership remains honest when the provider/profile/snapshot is not yet
available. This is the functional bridge needed for “any index ETF is just another locked watchlist.”

Gap status: `required_missing` for exact V25 add-source/search placement, input affordance, loading/
retry/error copy, and pending-to-ready transition. Interim oracle: focused Market Map component
`32/32`, full frontend Vitest `914/914`, type-check, and production build. Evidence needed: a
reviewed V25 capture showing an arbitrary ETF search/add action and its source entering the same
heatmap as an existing managed universe. No visual threshold or mask was relaxed.

## 2026-08-19 — Nested arbitrary-watchlist map geometry is represented functionally and visibly

The implementation now partitions grouped Market Map sources by their top-level `group_path` before
laying out member tiles. This functional oracle covers the shared behavior for index/ETF, sector,
industry, managed, combo, and classified personal watchlists; explicit/unclassified lists remain
flat. The 10,000-member canvas path remains indexed and bounded.

Top-level and nested group frames/counts are now shown for HTML tiles and drawn on the large-universe canvas;
they are intentionally lightweight and non-interactive so member selection remains authoritative.
Gap status: `required_missing` for exact V25 group-title placement, nested-label hierarchy, borders/gutters, tile density,
text scaling, hover treatment, and root-versus-drill-down composition for arbitrary watchlists.
Interim oracle: grouped/frame layout regression plus focused component coverage `35/35`, full frontend
Vitest `912/912`, type-check, and production build. Evidence needed: reviewed V25 captures showing
an arbitrary user/managed list rendered with sector/industry group boundaries. No visual threshold
or mask was relaxed.

Canvas parity correction: group boundaries and labels are painted after member fills/text so the
interim hierarchy is not hidden in the large-universe path. Exact V25 styling remains `required_missing`.
The 10,000-member test now verifies that ordering rather than merely checking canvas existence.

## 2026-08-19 — Unresolved holdings state remains a required visual gap

The backend now distinguishes an existing locked ETF/index universe whose disclosed rows cannot yet
be resolved to canonical members. It remains selectable/followable, shows zero usable members, and
retains raw-row, resolved-count, unresolved-count, completeness, and retry provenance; it is not
silently presented as a ready heatmap. Family coverage likewise reports the role as pending and does
not count it toward covered families.

Gap status: `required_missing` for exact V25 wording, badges, disabled/enabled controls, partial tile
behavior, retry affordances, and transition from unresolved to ready. Interim oracle: focused
history/family tests `10/10`, watchlists integration `47/47`, family coverage `2/2`, Market Map
component `30/30`, backend unit `1249/1249`. Evidence needed: reviewed V25 captures of partial or
unresolved holdings, source-picker status, retry progress, and recovery. No visual threshold or mask
was relaxed.

## 2026-08-19 — Universal arbitrary-watchlist heatmap is a documented reference gap

The implementation now composes one heatmap surface for any source that can be represented as a
watchlist: canonical index/ETF constituents are locked system lists, while personal and saved
selections are editable or user-owned locked copies. The same surface supports grouping, area and
colour metrics, periods, member selection, breadth/Study Lab handoffs, and relative comparison.
Mapped sources remain visible while membership is pending, and the history strip reports `pending`
instead of incorrectly calling an existing locked source unavailable.

Gap status: `required_missing` for exact V25 captures of arbitrary-watchlist selection, locked versus
editable affordances, pending-to-ready transitions, heatmap density/labels, and the source-to-map
handoff. Interim oracle: arbitrary canonical ETF Market Map/history integration `2/2` and Ruff.
Evidence needed: a reviewed V25 capture showing a user-defined or managed watchlist opened in the
same map as an index/ETF universe. No visual threshold or mask was relaxed.

## 2026-08-19 — Family coverage pending-profile state remains a visual gap

The family coverage/maintenance contract now distinguishes three lifecycle states: missing
canonical mapping (`mapping_unavailable`), canonical identity awaiting ETF profile hydration
(`profile_not_loaded`), and a loaded profile awaiting dated holdings (`no_snapshot`). The same
state is used by the locked universal source picker and Market Map, so an existing constituent
watchlist is never presented as nonexistent.

Gap status: `required_missing` for exact V25 coverage-panel status badges, warning copy, loading
transitions, and relationship to the source picker. Interim oracle: focused coverage regression
`2/2`, workspace integration `50/50`, backend unit `1248/1248`, and explicit source provenance.
Evidence needed: reviewed V25 captures of mapped/unmapped, profile-pending, holdings-pending,
ready, retrying, and failed family-role states. No visual threshold or mask was relaxed.

## 2026-08-19 — Arbitrary canonical ETF pending source remains a visual gap

Canonical active ETFs without a hydrated ETF profile now appear in the same universal Market Map
source picker as locked index/sector/industry and ETF constituent universes. They are labelled
pending, remain followable/pinnable, and render an explicit empty coverage-aware map until the
normal holdings route hydrates them. This is the required source-polymorphic behavior for treating
every index/ETF constituent population as a hard watchlist while retaining user control over
following, cloning, and downstream analysis.

Gap status: `required_missing` for exact V25 source-picker grouping, pending wording, disabled versus
enabled affordances, empty-map geometry, and post-hydration transition for an arbitrary ETF with no
profile yet. Interim oracle: Docker-backed catalog → Market Map integration `1/1` and Ruff. Evidence
needed: a reviewed V25 capture showing an unhydrated managed ETF/source, its pending state, and the
same source transitioning to populated holdings. No visual threshold or mask was relaxed.

## 2026-08-19 — Family maintenance pending/unavailable state remains a visual gap

The family history planner now carries the same distinction as the universal Market Map: a mapped
locked role with missing local profile/holdings data is `pending`, while an unverified role is
`unavailable`. This prevents bootstrap/admin progress from making a real system watchlist appear
nonexistent, without inventing membership or contacting providers interactively.

Gap status: `required_missing` for exact V25 maintenance/progress wording, badges, and transition
geometry. Interim oracle: family/bootstrap/holdings tests `25/25`, admin history-refresh API `1/1`,
backend unit `1248/1248`, Ruff, compileall, and repository checks. Evidence needed: a reviewed V25
capture of a mapped family leg before and after holdings hydration, including pending, unavailable,
retrying, and ready states. No visual threshold or mask was relaxed.

## 2026-08-19 — Pending locked-source followability is a visual-reference gap

The implementation now treats a mapped index/ETF constituent universe as a system watchlist even
before its local membership snapshot has hydrated. The selector keeps it enabled and labels it
`Pending membership`; the source can be followed or pinned, while a truly unmapped role remains
`Unavailable`. This is the correct source-polymorphic behavior for the universal Market Map, but
the composed web reference board has no authoritative V25 capture for the exact pending-source
label, follow/pin affordance, empty-map state, or transition after hydration.

Gap status: `required_missing` for exact V25 geometry, wording, and transition visuals. Interim
oracle: component regression `30/30`, full frontend Vitest `909/909`, and TypeScript type-check.
Evidence needed: a reviewed V25 capture showing an existing managed/system watchlist before its
constituent data is ready, including the selector, status, follow/pin controls, and recovered map.
No visual threshold or mask was relaxed.

## 2026-08-19 — Incomplete holdings evidence must trigger a real retry

The backend contract now distinguishes a visible partial/unknown holdings state from a ready
locked-watchlist source all the way through the inner provider bootstrap. A latest snapshot is not
considered ready until it has resolved members and an explicit complete/reconstructed status, so
the source remains eligible for maintenance rather than silently reusing incomplete membership.

Gap status remains `required_missing` for the exact V25 retry/progress geometry and copy. Interim
oracle: holdings/bootstrap/worker tests `34/34`, ETF holdings integration `63/63`, and backend
unit suite `1247/1247`. Evidence needed to close the visual gap: reviewed V25 captures showing
partial snapshot, retrying provider, successful refresh, and failed/unavailable states.

## 2026-08-19 — Partial provider data must remain visibly retryable

The board-guided product contract now treats a short D1 history or `partial`/`unknown` holdings
snapshot as a retryable coverage state, not as a ready source. The bootstrap gate requires `252`
adjusted daily bars for the default technical surface and an explicitly complete/reconstructed,
resolved holdings snapshot before suppressing provider maintenance. This is a backend readiness
invariant; the board still lacks authoritative Version 25 geometry for the maintenance/progress
controls that should communicate it.

Gap status: `required_missing` for exact maintenance/progress visuals. Interim oracle: bootstrap
regressions `20/20`, backend unit suite `1241/1241`, and explicit freshness/coverage states in the
universal Market Map. Evidence needed to close the visual gap: a reviewed V25 capture of partial,
retrying, successful, and failed source-maintenance states.

## 2026-08-19 — Family history queue consistency is functional; exact maintenance visuals remain open

Benchmark-family history refreshes now use the same historical-bound and job-identity contract as
all other locked watchlist sources. The composite visual board still lacks authoritative V25
captures for the admin maintenance controls, queued historical family progress, and failure/partial
coverage states.

Gap status remains `required_missing` for those exact controls and copy. The complete ETF holdings
integration suite passes `63/63`; provider population and rebalance continuity are separate data
gaps and are not inferred from queue correctness.

## 2026-08-19 — Future-bar rejection is a backend invariant, not a visible V25 state

Historical source hydration now rejects provider rows after the requested evaluation end before
they reach chart, breadth, ratio, or Study Lab inputs. The composite visual board does not need a
new visual baseline for this internal guard, but any historical loading/partial/error reference
must not imply that future bars can appear in an as-of result.

Gap status remains `required_missing` for exact V25 history-maintenance controls, progress/error
copy, and coverage-state geometry. Provider depth, stale/partial responses, and rebalance
continuity remain separate data gaps; no visual criterion was relaxed.

## 2026-08-19 — Historical source hydration boundary is implemented; provider coverage remains open

The universal locked-watchlist heatmap now carries a requested historical evaluation end through
source refresh queueing and provider history hydration. The board's historical-source states must
therefore distinguish a correctly bounded `as_of` refresh from current/open-ended refresh, including
partial, unavailable, and insufficient-history messaging. No authoritative V25 capture currently
shows this exact maintenance interaction or copy.

Gap status: `required_missing` for exact V25 historical-refresh controls, progress/busy/error copy,
and coverage-state geometry. The backend transport contract is covered by worker/history `14/14`
and watchlists integration `45/45`; provider depth, completeness, and rebalance continuity remain
separate data gaps and are not treated as visually accepted.

## 2026-08-19 — Study Lab selected-source lineage imagery is missing

The product now has an explicit downstream lineage state for arbitrary heatmap selections: a
compact status identifies `Selected members · N`, locked explicit semantics, parent source, and
canonical explicit source ID. This is functional guidance for the composite board.

No authoritative exact-build V25 capture covers this badge's placement, typography, color, truncation,
or arrival state in Study Lab. Those references remain `required_missing`; no visual threshold or
mask was relaxed.

## 2026-08-19 — Selected-subset Market Map handoff is functional but visually unreferenced

The current product vision treats an arbitrary index/ETF/personal/combo watchlist and a selected
subset of that watchlist as the same universal heatmap family. The selected action now publishes
an explicit canonical subset, and Breadth exposes it as `Selected members · N` with locked/ephemeral
semantics. The browser oracle proves a one-member selected handoff; this supplies interim behavior
guidance only.

The web-sourced board has no authoritative exact-build V25 capture for the selected-member action,
subset-source badge, source-lineage disclosure, oversized-selection guard, or Breadth/Study Lab
arrival state. These remain `required_missing` and must be tracked rather than inferred from the
full-source or personal-list images. No mask, threshold, or visual acceptance rule was relaxed.

## 2026-08-19 — Clone retry state is a tracked visual gap

The functional interim oracle now covers a locked source with one intentionally recoverable member
conflict: the shared Market Map leaves a visible partial personal copy, identifies failed canonical
IDs, and completes it through a retry action. The composite web-sourced board has no sufficiently
authoritative exact-build V25 capture for partial counts, failed-ID disclosure, retry placement,
busy/disabled treatment, retry success, or retry failure. These states remain `required_missing`;
the functional test cannot approve pixel parity. No threshold, mask, or acceptance requirement was
relaxed.

## 2026-08-19 — Clone snapshot behavior covered; V25 action visuals missing

The working board now includes a shared `Clone snapshot` source action for locked and editable
watchlists. The implementation resolves the full canonical source, preserves dated membership
lineage, and creates an editable personal copy. Authenticated browser coverage confirms the
behavior for a locked source.

The board has no sufficiently authoritative V25 capture for clone-action placement, wording,
busy/success/error states, conflict handling, or the transition into the copied personal list.
Those states remain `required_missing`; the browser oracle is functional interim evidence only.
No screenshot threshold, mask, or acceptance requirement was relaxed.

## 2026-08-19 — Role selector behavior covered; exact V25 imagery still missing

The working product vision now includes a benchmark-family `Map role` control. The accepted
behavior is a single selector for cap-weight/equal-weight/value/growth that opens a locked source
with the exact family/role identity; unavailable roles remain visible and disabled. The rebuilt
browser oracle covers the available equal-weight transition (`F8s-family-map-drilldown`, `1/1`).

The composite web-sourced board has no authoritative exact-build V25 capture for this selector:
its geometry, labels, disabled options, focus/keyboard treatment, loading/error state, and
transition into the map are `required_missing`. Until those references are acquired, the browser
oracle is the functional interim authority only; it cannot approve pixel parity. No threshold,
mask, or acceptance requirement was relaxed.

## 2026-08-19 — Eight-root family selector remains functionally covered, visually incomplete

The authenticated `F8s-family-matrix` browser oracle now exercises all eight benchmark-family
roots and opens the Nasdaq 100 locked constituent source. This supplies an interim interaction
oracle for the family selector and source identity, but the board has no authoritative exact V25
family-selector geometry, eight-root option density, unavailable-role treatment, or transition
states. Those visual states remain `required_missing`; no visual threshold or mask was relaxed.

## 2026-08-19 — Functional browser/provider evidence does not replace missing V25 imagery

The new authenticated Chromium flow (`F8s-market-map-watchlist`, `1/1`) is now the functional
interim oracle for the represented behavior: locked index/ETF-style constituent sources and
editable personal lists share one heatmap, with source identity preserved on refresh. Public
issuer/SEC route probes add `32/32` issuer-direct and `10/10` fallback evidence. The complete
adapter sweep remains `398 passed, 1 skipped, 7 failed` on unrelated non-core issuer endpoints;
that is recorded as provider evidence, not silently treated as a product pass. These artifacts
help iterate the product but are not visual references and cannot approve pixel parity.
The family drill-down oracle (`F8s-family-map-drilldown`, `1/1`) additionally covers selecting
S&P 500 and opening the locked cap-weight constituent source. It is behavior evidence only; it
does not fill the missing exact-build V25 source-picker imagery.

The exact Version 25 source-picker composition, lock/follow/pin treatment, and list-to-map
transition remain `required_missing`; all-root provider population and historical continuity are
separate data gaps. No acceptance flexibility was used and no older-generation image is silently
substituted.

## 2026-08-19 — Arbitrary-watchlist heatmap remains a reference gap

The implementation now treats index/ETF constituents as locked watchlists and routes them through the
same Market Map as personal, combo, managed, and explicit sources. The board still lacks an exact
Version 25 capture showing the source picker mixing these kinds, the lock/follow/pin affordances, and
the transition from an arbitrary watchlist into the heatmap.

Gap status: `required_missing` for those exact source-picker and transition states. Functional
interim oracle: backend source-contract integration `4/4` and frontend suite `900/900`; no mask,
threshold, provider substitution, or acceptance flexibility was used.

## 2026-08-19 — Role-specific constituent context action is visually unrepresented

Available benchmark-family role rows now offer `Open constituents in Market Map` from the desktop
context menu. The action preserves the exact family/role source identity and is absent when the
role has no verified holdings evidence, avoiding a ticker-only or cross-role fallback. The board
has no authoritative exact-build V25 capture for this role-specific context-menu item, its
disabled/absent unavailable state, or the transition into the locked constituent map.

Gap status: `required_missing` for context-menu placement, ordering, copy, keyboard focus recovery,
and unavailable-role treatment. Interim oracle: focused row/source `70/70`, full frontend Vitest
`900/900`, type-check, production build, and diff checks. No threshold, mask, provider
substitution, or acceptance flexibility was used. Close with reviewed V25 role-row captures and
browser evidence for an available and unavailable role.

## 2026-08-19 — Family benchmark Map handoff has no exact V25 reference

The selected family benchmark list now opens the locked cap-weight constituent source
(`benchmark-family:<family>:cap_weight`) rather than mapping the four role ETFs as if they were
constituents. This is the functional interpretation of the family-as-managed-watchlist model and
uses the same universal heatmap surface. Equal/value/growth source identities are centralized for
future role-level actions, but no unavailable role is substituted.

Gap status: `required_missing` for exact V25 Map-button placement/copy, the transition into the
constituent map, and role-specific equal/value/growth Map affordances. Interim oracle: focused
source/list/map tests `164/164`, full frontend Vitest `899/899`, type-check, production build, and
diff checks. No threshold, mask, provider substitution, or acceptance flexibility was used. Close
with reviewed V25 list-to-constituent-map captures and browser evidence across a mapped and an
unavailable family role.

## 2026-08-19 — Family role evidence is functionally explicit but visually unrepresented

The selected family entry point now shows a role strip for cap, equal, value, and growth. Each
role carries the canonical verified symbol/label when available and an explicit mapping state when
it is not; `No verified mapped proxy` and unavailable states are retained instead of being omitted
or replaced by another family. This is the visual target for the implementation, but the composite
board has no authoritative exact-build V25 capture of this family-specific strip or its unavailable
states.

Gap status: `required_missing` for role-strip placement, typography, separators, loading/error and
unavailable-role treatment, and the family-selection transition. Interim oracle: focused
family-entry contracts `95/95`, full frontend Vitest `896/896`, type-check, production build, and
diff checks. No threshold, mask, provider substitution, or acceptance flexibility was used. Close
with reviewed V25 role/family captures and browser interaction evidence; until then the gap stays
tracked and does not count as visual parity.

## 2026-08-19 — Interchangeable family entry-point states remain visually unrepresented

The benchmark list now switches between the default Major US benchmarks/SPY surface and each
registered US family root. A selected root loads its own cap proxy and locked proxy-leg rows at the
active timeframe, preserves the same columns/links/Map handoff, and discloses the official index,
tradable proxy, loading, and error state.

Gap status: `required_missing` for exact V25 family-selector placement, option naming/order,
selected-family identity strip, loading/error geometry, and family-to-list transition. Interim
oracle: family-entry focused contracts `95/95`, full frontend Vitest `896/896`, type-check/build,
and diff checks. No visual threshold or mask was relaxed. Close with a board-authoritative family
entry capture and browser interaction evidence across at least one S&P, one Russell, and Nasdaq
root, including unavailable-role treatment.

## 2026-08-19 — Source-kind grouping and locked constituent semantics remain visually unrepresented

The universal Market Map now groups source choices into index/managed universes, ETF holdings,
market groups, personal watchlists, managed scans, combos, and explicit selections. The active
source kind and member count are shown next to Follow/Pin; locked index/ETF constituent sources
remain immutable while the preference is user-controlled. The same map path accepts any arbitrary
watchlist source.

Gap status: `required_missing` for exact-build V25 source-picker grouping, source-kind labels,
locked-membership disclosure, and Follow/Pin treatment. Interim oracle: Market Map `27/27`, full
frontend Vitest `895/895`, type-check, production build, and diff checks. No visual threshold or
mask was relaxed. Close with a reviewed V25 capture of the source picker and active-source action
row, then measure the labels, grouping, disabled/unavailable states, and lock treatment.

## 2026-08-19 — Study Lab promotion/source-lineage state is visually unrepresented

Generic Study Lab Boolean results now promote only to a fixed canonical custom universe and retain
run, dataset, membership, and reproducibility lineage. Missing canonical members produce an
explicit refusal instead of an `all`-universe fallback. The composite board has no authoritative
V25 capture showing the promotion action row, source/membership disclosure, current-data
re-evaluation warning, or the missing-dataset recovery state.

Gap status: `required_missing` for those exact promotion/source-lineage visuals. Interim oracle:
Study Lab `23/23`, screener integration `26/26`, full frontend Vitest `894/894`, type-check,
production build, Ruff, compileall, and diff checks. No screenshot threshold, mask, acceptance
flexibility, provider substitution, or historical-integrity rule was relaxed. Close this gap with
a reviewed V25 Study Lab promotion capture and measured interaction/error states; until then it is
tracked rather than silently treated as visual parity.

## 2026-08-19 — Large-universe Market Map treatment is visually unrepresented

The shared Market Map now switches arbitrary watchlists with more than 1,500 valid members to a
single canvas. It preserves deterministic treemap geometry, colour/selection paint, hover detail,
zoom/pan, drag suppression, and a keyboard symbol/name search so a 10,000-member universe does not
become a proportional tile DOM. The composite board has no sufficiently authoritative V25 capture
showing the corresponding large-universe density threshold, canvas/text policy, hover/selection
state, or keyboard-search affordance.

Gap status: `required_missing` for those visual states. Interim oracle: Market Map `26/26`, full
frontend Vitest `893/893`, type-check, production build, diff checks, and the 10,000-member
zero-tile-DOM regression. No screenshot threshold, mask, provider substitution, or acceptance
flexibility was used. Evidence needed to close the gap is a reviewed V25 large-watchlist/heatmap
capture (including dense and keyboard/member-selection states), followed by measured geometry and
token review. Until then this is tracked rather than silently treated as visual parity.

## 2026-08-19 — Watchlist-level Market Map launch is visually unrepresented

The shared virtualized watchlist now offers a `Map` action for any view backed by a canonical
universe. It can launch personal/combo/flagged lists, locked benchmark/sector/ETF sources, and
filtered constituent/proxy subsets into the same Market Map surface. The board does not contain
an authoritative V25 capture showing the exact placement, icon/text treatment, source handoff
copy, locked explicit-subset disclosure, or the transition into the already-configured map.

Gap status: `required_missing` for the list-level action and handoff visuals. Interim oracle:
virtual watchlist `66/66`, workspace-store `67/67`, full frontend Vitest `892/892`, type-check,
build, and diff checks. The implementation retains canonical source lineage and no acceptance
threshold or mask was relaxed. Evidence needed to close the gap is a sufficiently authoritative
V25 list/watchlist capture showing the equivalent action and transition; until then, this board
gap is tracked rather than silently treated as visual parity.

## 2026-08-19 — Market Map timeframe selector remains visually unrepresented

Market Map now lets the user select Daily, Weekly, or Monthly resolution for the same arbitrary
locked/personal watchlist universe. The chosen timeframe is carried through local history
readiness, explicit hydration, Python colour evaluation, map calculation, persistence, and named
snapshot restoration. The board does not contain an authoritative V25 capture showing this
selector's exact placement, labels, linked-timeframe behavior, or loading/partial-state treatment.

Gap status: `required_missing` for exact timeframe-control geometry/copy and represented loading or
coverage states. Interim oracle: Market Map component `25/25`, backend Market Map unit `5/5`, full
frontend Vitest `890/890`, type-check/build, and diff checks. No visual threshold or mask changed;
provider-backed family population, historical continuity, and exact V25 maintenance visuals remain
separate gaps.

## 2026-08-19 — YTD baseline disclosure remains visually unrepresented

The shared top-down analytics now use a prior-year-end session for YTD across Market Map, family
role ranking, technical summaries, and historical return series, with explicit insufficient-history
states when the baseline is missing. The composite board has no authoritative exact-build capture
for the YTD denominator disclosure, tooltip copy, or the corresponding uncovered warning in these
surfaces.

Gap status: `required_missing` for exact selector/baseline/insufficient-history geometry and copy.
Interim oracle: analysis-router `20/20`, backend units `1215/1215`, Docker-backed watchlist/Market
Map integration `42/42`, Ruff, compileall, and diff checks. No visual threshold or mask changed;
provider-backed family population and historical continuity remain separate gaps.

## 2026-08-19 — Market Map period-boundary visual gap

The universal Market Map now uses the last completed session before the calendar boundary for MTD
and YTD, with explicit insufficient-history state when that baseline is unavailable. The browsable
V25 board has no authoritative exact-build capture for the period selector's MTD/YTD boundary
labels, prior-close disclosure, or insufficient-history cell/legend treatment.

Gap status: `required_missing` for exact period-control geometry, boundary copy, baseline/detail
tooltip, and uncovered-state styling. Interim functional oracle: period helper `5/5`, backend unit
suite `1214/1214`, Docker-backed watchlist/Market Map integration `42/42`, focused Market Map
component `24/24`, and type/build checks. No visual threshold or mask was changed; provider-backed
family population and historical continuity remain separate gaps.

## 2026-08-18 — Relative Rotation history control gap

The board currently has no sufficiently authoritative Version 25 capture for the full Relative
Rotation history/tail control, its maximum-history affordance, or the long-curve rendering state.
The implementation therefore uses deterministic contract and interaction tests as the interim
oracle: bounded `history_length`, exact aligned/no-forward-fill/as-of semantics, persisted control,
and uPlot redraw without chart recreation. This is a required visual gap, not a pass and not an
acceptance relaxation. Close it with a reviewed V25 capture and measured control/curve geometry;
until then, do not broaden screenshot masks or claim pixel parity for this state.

## 2026-08-18 — Provider-field conflict state remains visually unrepresented

Market Map now exposes a deterministic provider-precedence value plus explicit conflict provenance
and `profile_field_conflict` warnings when eligible persisted profile snapshots materially disagree.
The board has no authoritative Version 25 capture for this diagnostic treatment: warning copy,
candidate-detail affordance, tooltip geometry, or stale/conflict badge state.

Gap status: `required_missing` for exact conflict badge/detail geometry and interaction treatment.
Interim oracle: provider-precedence integration, helper tests `2/2`, complete watchlist/workspace
integration `91/91`, Ruff, compileall, and diff checks. No acceptance flexibility was used.
Evidence needed: an authoritative V25 state reference or a documented decision that this diagnostic
state is outside visual parity; until then it remains a tracked visual gap.

## 2026-08-18 — Provider-quality fields have no exact V25 visual authority

Locked source descriptors now retain adapter status/confidence and snapshot quality/provenance,
including the case where cached holdings remain usable after a provider failure. The board has no
authoritative V25 capture for this route-status/freshness treatment in a source picker, coverage
panel, or Market Map header.

Gap status: required_missing for exact status badge, stale/error copy, confidence/quality detail,
and geometry. Interim oracle: focused source/coverage 2/2 and full watchlist/workspace analysis
91/91. No acceptance flexibility was used. Evidence needed: an authoritative V25 capture or an
explicit decision that this diagnostic state is outside visual parity.

## 2026-08-18 — Same-date holdings revision state remains visually unrepresented

The implementation now preserves point-in-time truth when two ETF/index-proxy holdings snapshots
share a composition date but become known at different times: Market Map selects the latest
known-at revision eligible at the requested evaluation timestamp. The board has no authoritative
V25 capture for the resulting revision/freshness disclosure, warning, or tile-area transition.

Gap status: required_missing for exact revision badges, copy, stale/partial state, and geometry.
Interim oracle: the Docker-backed same-date revision Market Map regression and full 42/42
watchlist integration file. No acceptance flexibility was used. Evidence needed: an authoritative
V25 revision-state reference or an explicit decision that this data-integrity disclosure is outside
visual parity; provider population and historical continuity remain separate gaps.

## 2026-08-19 — Availability badges for arbitrary locked universes remain a visual gap

The product vision now treats every index/index-ETF constituent set as a locked watchlist that
can feed the same Market Map as a personal or arbitrary list. The implementation distinguishes
populated sources (`available`) from an empty membership load (`membership_not_loaded`) and an
ETF profile with no holdings snapshot (`holdings_snapshot_not_loaded`); all remain visible for
audit, are labelled `Unavailable`, and are disabled rather than silently replaced.

The board has no authoritative exact-build V25 capture for these ordinary locked-source states.
Gap status: `required_missing` for the exact unavailable label, provenance badge, disabled-option
styling, and picker geometry across market groups and ETF holdings. Interim oracle: Docker-backed
descriptor/API `2/2`, focused Market Map `24/24`, full frontend `888/888`, type/build, Ruff,
compileall, and diff checks. No acceptance flexibility was used. Evidence needed: an authoritative
V25 capture or an explicit product decision that this state is outside visual parity; provider
quality and historical continuity remain separate gaps.

## 2026-08-19 — Unavailable family-source picker state remains unrepresented

The board contains no authoritative exact-build capture for a benchmark-family source picker that
shows a mapped-but-unavailable value/growth/equal role. The workstation now keeps that canonical
locked source visible, labels it `Unavailable`, disables accidental selection, and prefers an
available source at startup; it never hides or substitutes the role. The focused `24/24` Market
Map component suite and full frontend `888/888` suite are the interim interaction oracle.

Gap status: `required_missing` for exact V25 unavailable-role label, badge, disabled-option styling,
and picker geometry. Evidence needed: a reviewed V25 capture of this state or an explicit accepted
product decision that the state is outside visual parity. Provider-backed family population and
historical continuity remain separate data gaps.

## 2026-08-19 — Bulk family refresh has no authoritative visual reference

The board contains no sufficiently authoritative Version 25 capture for an administrator running
an all-family or historical holdings backfill, nor for the per-family/per-leg success, unavailable,
route-not-ready, failure, snapshot, and composition-date report. The backend now supplies this
operational contract through one canonical locked-watchlist population path; it is intentionally
not exposed as a workstation menu or represented as a user-facing V25 visual claim.

Gap status: `captured_unmeasured`/`required_missing` for the admin refresh/report surface. Interim
oracle: deterministic API schemas, savepoint failure isolation, the `61/61` ETF integration file,
and the `90/90` affected Market Map/workstation suites. Evidence needed to close the gap: an
authoritative V25 administrator/backfill capture or an explicit product decision that this
maintenance surface is out of visual-parity scope.

## 2026-08-19 — Evaluation-time weight state is a backend acceptance gap

The board does not contain an authoritative exact-build capture for a historical map switching
between dated holdings weights. The backend now selects system-managed composition at the map's
evaluation timestamp and preserves the selected snapshot lineage; personal/combo current-list
semantics are intentionally distinct. Exact V25 weight badge, disclosure, stale/partial, and
revision geometry remain unrepresented and must not be mistaken for visually approved parity.

## 2026-08-19 — Universal family-role acceptance coverage

The controlled reference environment now represents every configured, available benchmark-family
leg as a locked WatchlistSource so the Market Map and breadth acceptance path can be exercised
across all S&P/Russell/Nasdaq roots and roles. This improves the browsable product vision's
functional coverage without inventing a visual claim: the family source-picker, unavailable-role,
derived-weight, and membership-revision states still have no exact-build V25 capture and remain
tracked as board gaps.

## 2026-08-19 family-leg source composition gap narrowed

The board supports a single dense heatmap language for arbitrary lists, but it does not show the
exact Version 25 source-picker treatment for a benchmark family whose cap, equal, value, and
growth legs are separately selectable locked lists. The implementation now composes those legs
as `benchmark-family:<family>:<role>` sources, preserves the same map/list surface, labels
derived equal-weight membership and unavailable roles, and reuses the canonical source lineage
through Market Map and generic breadth. Source/resolver/cache and `88/88` integration assertions
are the interim oracle.

Still unrepresented: exact V25 labels/icons, follow/clone affordance placement, derived equal
weight disclosure, unavailable-role styling, revision/freshness badges, and the populated visual
appearance of every family. These remain tracked reference gaps rather than silent passes.

## 2026-08-19 numeric profile-area state gap narrowed

The board has no authoritative Version 25 treatment for choosing a numeric tile-area field from
multiple provider profile snapshots, especially when one provider lacks that field. The backend
now uses one source-neutral alias/precedence contract for market cap, volume, 52-week range, P/E,
beta, and dividend yield, selecting a covered point-in-time snapshot and explicitly warning on
stats fallback. Exact V25 field selector, tooltip, conflict badge, and mixed-coverage geometry are
still unrepresented; provenance and integration assertions are the interim oracle.

## 2026-08-19 historical entitlement-revision area gap narrowed

The board has no authoritative Version 25 state for a historical Market Map whose profile source
changed free/paid or review status between two as-of dates. The implementation now reconstructs
the latest immutable entitlement revision known at the map evaluation timestamp, prevents future
revisions from leaking backward, and exposes revision/effective-time evidence in tile provenance.
The current-row fallback for sources with no revision is visibly warned and remains a tracked
compatibility gap. Exact V25 badge, tooltip, warning-copy, and revision-history geometry remain
unrepresented; deterministic API provenance and historical regression tests are the interim oracle.

## 2026-08-19 provider-precedence area state gap narrowed

The board does not show how Version 25 labels a market-cap tile when multiple providers have
different profile observations, or when a persisted snapshot comes from a source that is no
longer entitled. The implementation now selects the enabled free adapter-capable provider chain,
records provider rank and entitlement verification in tile provenance, and keeps an unranked
snapshot only with explicit cell/response warning state. The provider-policy integration and
complete watchlist suite are the interim correctness oracle. Exact V25 tooltip/badge wording,
provider-conflict affordances, and historical entitlement-revision controls remain unrepresented.

## 2026-08-19 point-in-time area provenance gap narrowed

The board has no authoritative capture of Version 25’s tile treatment when market-cap area is
point-in-time, mixed-coverage, or falling back to current metadata. The implementation now uses
canonical profile snapshots where available, labels each tile with snapshot provenance in the
data contract, and surfaces a response warning for current-metadata fallbacks. Deterministic
integration and component assertions are the interim oracle. Exact tooltip/badge wording and
mixed-coverage geometry remain unrepresented.

## 2026-08-19 combo historical departure gap narrowed

No authoritative board state shows how Version 25 presents a combo whose union/intersection or
exclusion dependency changes across time. The implementation now applies dependency active
intervals at `as_of`, preserves deterministic active ordering, and reports departed members as
structured exclusions. Complete watchlists integration coverage is the interim oracle. Exact
combo revision badges/history controls and multi-episode re-entry visuals remain unrepresented.

## 2026-08-19 managed departure as-of gap narrowed

The board has no authoritative capture of how Version 25 displays a managed constituent during its
grace period versus after a historical departure. The implementation now keeps current grace
visibility but excludes `left_screener_at <= as_of` from historical WatchlistSource resolution,
returning the departure timestamp and a structured exclusion. The focused integration regression
is the interim oracle. Exact badges, copy, and history controls remain unrepresented; combo
re-entry and append-only membership history are separate backend gaps.

## 2026-08-19 locked market-group revision gap narrowed

The board still has no authoritative capture of how Version 25 presents a refreshed locked index,
sector, or industry membership/weight revision. The implementation now has deterministic
membership lineage for those sources: member-row changes alter the source version and map cache
identity, and the rendered map reports the new weight. Focused integration assertions are the
interim acceptance oracle for correctness. Exact V25 revision badges, refresh copy, timestamps,
and any user-facing history affordance remain unrepresented and must stay tracked until a
complementary reference closes them.

## 2026-08-19 Python map source-polymorphism reference gap

The board does not show whether Version 25 exposes a derived combo or ephemeral multi-symbol
selection as a Python-backed map universe. The implementation follows the established dense map
language and uses the canonical source ID for every locked, derived, personal, ETF, and explicit
universe; component/API source-preservation checks are the interim oracle. Exact V25 affordance
copy and badges for this state remain unrepresented.

## 2026-08-19 arbitrary-watchlist lineage reference gap

The composed board supports one heatmap language for locked index/ETF constituent universes,
derived combo lists, managed scans, and editable personal watchlists, but it does not show the
exact V25 visual treatment for a membership revision or a derived source invalidating a cached
map. The implementation now uses deterministic membership fingerprints and preserves the same
heatmap surface; source/resolver/cache assertions are the interim oracle. Exact badges, refresh
copy, and revision-history geometry remain unrepresented and must stay tracked until a
complementary reference is reviewed.

## 2026-08-19 aggregate breadth plot reference gap

The board has no authoritative V25 capture of the complete flow from a cross-sectional breadth
result to a reusable chart plot, including its source-universe retention and aggregate-series
rerun state. The interim oracle therefore checks the explicit `percentage_history` output contract,
full declared-universe materialization, isolated `breadth_aggregate_percentage` adapter, and chart
plot metadata carrying the locked source ID or explicit symbols. Exact button wording, placement,
plot-library badges, and any V25 target-mode affordance remain a named visual gap and must not be
silently inferred from the member-level plot surface.

## 2026-08-19 explicit-source reference gap

The board does not contain an authoritative V25 capture of the exact multi-symbol ad-hoc universe
entry, durable explicit-source library action, or its locked/ephemeral provenance treatment. The
workstation now uses the board's dense universe-control language, resolves symbols to canonical
IDs, and renders the same Market Map as saved lists and index/ETF sources. Durable selections also
flow through generic Breadth and isolated Python Market Map universe declarations using the same
canonical resolver. Functional resolution, deduplication, missing-symbol, map orchestration,
Breadth, and Python-universe tests are the interim oracle; historical explicit membership and
exact visual geometry remain tracked gaps.

The current implementation resolves a multi-symbol entry through a single canonical batch request;
the board has no authoritative visual reference for request progress, partial missing-symbol
feedback, or the 500-member validation state. Those states remain functional/performance gaps for
visual comparison, not reasons to invent a V25 appearance or silently accept provider fallback.

The board also has no authoritative capture of the explicit-source durability action or its
subsequent Breadth/Python reuse. The interim oracle is the source-descriptor member-ID set, the
user-owned locked library write, the saved-source → Breadth integration, and the provider-neutral
Python universe helper. The interim historical oracle now also requires a pre-`known_at` request to
show zero members with an explicit membership-not-known exclusion and a post-`known_at` request to
restore the exact saved IDs; exact V25 button wording/placement and source-library affordance remain
a tracked visual gap.
The same pre-`known_at` exclusion is required when a Market Map's historical `end` drives source
membership evaluation.

## 2026-08-19 universal derived-watchlist reference gap

The board supports the product decision that a combo watchlist should render in the same dense
heatmap language as an index/ETF constituent list or personal watchlist. The implementation now
exposes combo definitions as locked, derived `WatchlistSource` inputs and reuses the same Market
Map interaction contract. No authoritative V25 capture shows the exact combo-definition lineage or
locked-derived badge, so those details remain a tracked visual gap; deterministic source identity,
membership, and interaction tests are the interim acceptance oracle.

## 2026-08-19 Boolean breadth promotion reference gap

The board contains the dense Research Results/action language but no authoritative capture of the
exact Version 25 state after a Boolean breadth run is promoted successively to an alert, Market
Gauge, and Strategy signal. The implementation reuses one saved EasyScan and immutable code
version, and deterministic component/API assertions are the interim oracle. Button placement,
confirmation copy, and any target-specific V25 affordance remain a named visual gap until a
complementary reference is reviewed; this does not block the represented Research Results surface.

## 2026-08-18 universal-source and recursive-Python visual gap

The composed board supports the product decision that a locked index/ETF constituent list should
look and behave like any other TC2000 watchlist source when opened in a map: the membership is
managed and immutable, but the same dense heatmap, grouping, selection, linking, filtering, and
drill-down surfaces apply. It does not contain an authoritative V25 capture of the exact
locked-source lineage affordance or the recursive Python condition authoring/result state.

Those states therefore use the board's dense list/map/editor language plus deterministic
functional oracles. The functional tree path now supports both member and cross-sectional Python
leaves, but the exact V25 authoring/result geometry remains a tracked visual gap; no screenshot
threshold, mask, or older-generation reference is being promoted silently to close it.

## 2026-08-18 cross-sectional Python-series reference gap

The backend and isolated runner now support a Python numeric-series target whose comparison is
member-minus-group statistic, but the board has no authoritative V25 capture of that exact
authoring/result state. Functional acceptance is therefore covered by deterministic API/runner
oracles; exact visual acceptance remains a named gap until a complementary reference is found.

## 2026-08-17 mixed-scope breadth reference gap

The current board has no sufficiently authoritative Version 25 capture of a recursive breadth
condition that combines member-level and cross-sectional targets. The implementation uses the
board-guided dense condition-editor language and existing heatmap composition, with a deterministic
interim oracle covering scope labels, nested groups, clause diagnostics, pass/fail tiles, and
historical exclusions. The local API and isolated Study Lab runner now share the same nested
current/history evaluator, including the explicit group-statistic leaf. This remains a gap for exact
visual judgement; closure requires a reviewed
V25 capture or successor reference showing the mixed statistical authoring/result state.

## 2026-08-14 canonical workstation revalidation

The current non-seeded branch deployment was revalidated against the board-guided interaction
contract after the bootstrap repair. The complete authenticated workstation matrix passed `140/140`;
the four-environment board baselines and gap-directed state oracles remain the active visual track.
This run confirms represented shell density, tool-window containment, charts, grids, linking,
Study Lab composition, and top-down traversal behavior, but it does not promote any board image to
exact-build approval. `REF-SHELL-V25`, `REF-STATE-VARIANTS`, `REF-LINKING-V25`, `REF-STUDY-LAB-V25`,
`REF-ENV-TOKENS`, and `REF-PERMISSION-REVIEW` remain explicit where the board lacks authoritative
pinned-build state evidence.

## 2026-08-12 deterministic drawing-toolbar visual correction

The chart drawing toolbar was compared against the board's chart/comparison and dense-window
groups. The board supports the compact dark chart-tool composition, separators, flyout treatment,
and dense control language, but does not contain a pinned-build capture or measured icon sheet for
the drawing toolbar itself. The repository-controlled mismatch was therefore corrected without
invented exact-build claims: emoji and Unicode glyphs were replaced with deterministic original
CSS geometry, controls were tightened to a measured 32px button contract inside a 40px rail, and
utility controls received explicit accessible names and button types.

The focused drawing browser suite passes `4/4`, including the no-text-glyph and compact-geometry
contract, the no-update represented default-workstation visual assertion passes at 1920x1080/100%,
and the complete seeded authenticated Chromium matrix passes `107/107` executed tests with two
intentional skips. This is board-guided represented chart composition plus controlled seeded
interaction/data flexibility. It does not close the exact pinned-build drawing-icon/style gap:
`REF-STATE-VARIANTS` remains open for exact toolbar glyphs and unrepresented selected/disabled
variants, and stronger evidence would require a reviewed pinned-build capture or measurements.
No visual threshold, mask, uPlot renderer, provider, or product-scope rule changed.

## 2026-08-11 deterministic fixture isolation and complete revalidation

The seeded acceptance runtime was found to be mixing canonical bars/holdings with controlled
fixture rows when a persistent database already contained data. That was a real test-environment
defect, not a visual mismatch to be hidden: seeded E2E startup now replaces adjusted daily bars
for the controlled fixture universe, and seeded holdings reads are explicitly scoped to the
`controlled_fixture`/`e2e_reference` provenance. The focused router/seed regression slice passes
`17/17`.

Because the corrected runtime changed the deterministic observations (including the chart range,
sector values, and no-sector Industries prompt), the four-environment board-guided screenshots were
refreshed once from that runtime and then verified without update mode: `104/104` pass at
1920x1080 and 2560x1440, both at 100% and 125% display scale. The visual diff thresholds and masks
were not changed. This is explicitly seeded-fixture/board-guided flexibility, recorded to keep
the local oracle honest; it does not promote the web-sourced board to exact-build approval and
does not close the exact-build, permission, or unrepresented-state gaps below.

## 2026-08-10 acceptance update

The workstation now has a deterministic visual oracle for the integrated EasyScan condition
editor. The state is tracked as `watchlist-column-filter/condition_editor` with four local
display-scale baselines and is now board-covered because the composed board contains the
official Version 25 condition-editor/filter-selection states. The source pages do not prove
pinned build `25.0.9571`; that remains optional strengthening evidence, not an unrepresented-state
gap. The full board-guided matrix passes `104/104`; no visual threshold or mask was relaxed.

The retrieved reference pack is now composed into a single browsable visual board so
implementation decisions are made against a coherent product vision rather than isolated
screenshots.

## Build and review

The controlled pack is stored at `/private/tmp/tc2000-v25-reference-pack` and contains 230
retrieved images. It was refreshed and revalidated on 2026-08-10 from the recorded official
source URLs; the board validator passed all 230 local media sources. Generate the board with:

```bash
python3 tests/visual/build-tc2000-reference-board.py \
  /private/tmp/tc2000-v25-reference-pack \
  /private/tmp/tc2000-v25-reference-pack/reference-board.html

npx playwright screenshot --device='Desktop Chrome HiDPI' --full-page \
  file:///private/tmp/tc2000-v25-reference-pack/reference-board.html \
  /private/tmp/tc2000-v25-reference-pack/reference-board.png

python3 tests/visual/validate-tc2000-reference-board.py \
  /private/tmp/tc2000-v25-reference-pack/reference-board.html
```

The board groups every image by surface and labels it with source type, source build,
filename, and source-page link. It is an implementation and review aid; it does not merge
different product states into a claim that they are one deterministic screenshot.
The validator is a deterministic completeness check: it confirms that every generated image
card has a local source file. It does not promote any reference to an approved baseline.

## Current coverage

| Surface group | References | What it contributes |
|---|---:|---|
| Factory/default layouts | 47 | Dense workspace composition, layout tabs, chart/watchlist proportions |
| Data grids and columns | 53 | Column/filter editor, condition selection, grouping, stacking, historic columns, creation, use, appearance |
| Market gauges | 24 | Gauge creation, readings, condition-driven visuals |
| Charts and comparisons | 35 | Timeframes, comparisons, projections, markers, past performance |
| Windows and layout mechanics | 10 | Floating windows, tab repositioning, drag/drop composition |
| Notes and value-column workflows | 8 | Notes window and chart/watchlist transfer mechanics |
| Symbol linking | 6 | Link-color mechanics and linked-window behavior |
| Version 25 product/shared-layout evidence | 3 | Current product-level shell and shared-layout composition |

The grouped board exposes the intended visual language: dense dark chrome, compact title and
link controls, thin separators, small typography, data-grid-first workflows, chart panes with
minimal decoration, and frequent drag/drop transfer between tools.

### 2026-08-10 visual iteration note

The pack was expanded with official current Version 25 help pages for the integrated condition
editor, ALL/ANY filter selection, symbol linking, and historic columns. The resulting board now
contains 230 images across 26 surfaces. These additions strengthen the board-guided visual target
for watchlist/filter/linking composition; their source/build labels remain discovery evidence where
the page does not prove pinned build `25.0.9571`, so they do not silently close the related exact-
build or state-variant gaps.

The board-guided comparison of the compact relative-strength window exposed a concrete
repository-controlled mismatch: uPlot's default HTML legend was rendered below the plot while
the workstation-owned ratio legend was already rendered above it. `RatioUPlot` now disables the
duplicate legend, with a unit regression and a rebuilt browser overlap check. The earlier stale
baseline run was superseded: baselines were regenerated once from a fresh controlled fixture and
the complete matrix then passed `100/100` without update mode across all four required environments.
No mask or threshold was promoted. This uses the board-guided/fixture flexibility recorded in the
acceptance-governance ledger; it does not alter any gap's closure requirement. Exact-build and
unrepresented-state gaps remain in the register.

### 2026-08-12 deterministic fixture alignment after data-grid work

The first no-update visual run after adding watchlist header separators reported `90/104`, with
all `14` failures confined to the 2560x1440/125% project. Actual/expected review showed a common
historical-content mismatch across unrelated shell, chart, ratio, and freshness surfaces; it was
not a header geometry regression. The branch-scoped stack was rebuilt with both seed flags, the
per-test immutable factory reset was retained, and only the stale 125% snapshots were regenerated
after review. The complete no-update matrix then passed `104/104` across all four required
environments. No mask, threshold, or product criterion was changed. This closed the local
fixture-version alignment issue; the later native hit-target correction is recorded immediately
below.

The subsequent native hit-target audit found and fixed a repository-controlled geometry issue: the
header grid had collapsed to 1px, so the scroll surface intercepted real pointer input. The 23px
minimum-height/stacking correction was reviewed against the board's dense grid composition. Native
resize now passes `1/1`, the full authenticated flow passes `109/109` executed with two skips, and
the no-update four-environment visual matrix passes `104/104`. This closes the native hit-target
part of the resize gap; exact-build pointer-state measurements remain `REF-STATE-VARIANTS`.

## Gaps identified from the board

These are now explicit implementation/acceptance gaps rather than an undifferentiated
“visual references unavailable” state. Each gap has an interim oracle so development can
continue without disguising the absence of authoritative Version 25 evidence.

| Gap ID | Missing reference and affected acceptance cases | Current implementation treatment | Interim test/oracle | Evidence required to close the gap |
|---|---|---|---|---|
| `REF-SHELL-V25` | Any shell detail not sufficiently represented by the board, including exact pinned-build-only variants | Use the board’s factory-layout/product-image groups as the visual authority for represented density, proportions, chrome, and token direction; track only uncovered details as limited | Four seeded environment geometry/containment audits, deterministic screenshot harness, and browser shell interaction tests | Additional exact-build evidence only for the identified uncovered detail; it is not a blanket gate |
| `REF-STATE-VARIANTS` | Loading, stale, partial, provider-error, blocked-pop-out, recovery, focused, keyboard-selected, and disabled states | Implement explicit freshness/error/recovery states from platform contracts; do not infer their exact V25 styling from unrelated screenshots | Browser tests for stale/partial/error/recovery flows, including `F8i-a` provider-error, `F8i-b` loading, `F8i-c` stale, `F8i-d` partial, and `F8k-a` blocked pop-out, plus four-environment `chart-loading-gap`, `stale-freshness-gap`, `partial-coverage-gap`, and `blocked-popout-gap` baselines, accessibility/focus assertions, structured cell warnings, and the official V25 hotkey behavior article | Complete state capture set from the pinned build at a reviewed target environment |
| `REF-LINKING-V25` | All normal link groups, yellow wildcard, grey isolation, timeframe propagation, linked crosshair, and cross-window propagation | Preserve canonical-ID link bus and test behavioral semantics independently of missing visual proof | Link-group, keyboard, cross-window, and chart crosshair integration tests; official timeframe-linking behavior evidence is recorded in the manifest | Authoritative captures covering every link state and interaction, with timing and environment metadata |
| `REF-STUDY-LAB-V25` | Open-ended research editor, structured renderers, occurrence browser, sandbox-error and promotion surfaces | This is an original surface with no direct TC2000 analogue; use the board’s dense editor/grid language for composition and the product contracts for behavior | Four-environment `Study Lab original surface` local baselines (manifest-linked for `editor`) plus validation, run, cancellation, recovery, structured-output, occurrence-link, and promotion tests | A reviewed V25 analogue only if one is discovered; otherwise retain the original-surface exception and its local baseline |
| `REF-BREADTH-COMPOSER-V25` | User-authored breadth predicate editor, target-scope controls, aggregate/member/history views, occurrence linking, and promotion affordances | The board shows related dense condition/filter language but no sufficiently authoritative V25 capture of this complete cross-sectional study workflow; the recursive nested predicate tree and aggregate Study Lab promotion are implemented from the generic breadth contract, while target axes and exact promotion geometry remain explicit | Four-environment local baselines plus API/runner/browser tests for selected universe, measured field, target/operator, nested clauses, pass/fail drill-down, history, linked symbols, and aggregate Study Lab rerun; the authenticated tree flow proves `all(any(new_high_low))` | A reviewed V25 capture covering the generic breadth authoring/result/promotion states, or a reviewed successor reference that explicitly covers them |
| `REF-ENV-TOKENS` | Deterministic 1920×1080 and 2560×1440 captures at 100% and 125% display scale, with measured tokens | Maintain four seeded visual environments and tokenized geometry checks; keep screenshot comparison failures visible | Geometry/viewport containment, token assertions, and unmasked screenshot diff reporting | Captures and measurements for all four required environments, approved against the manifest |
| `REF-PERMISSION-REVIEW` | Permission classification for any future redistribution or exact-build baseline promotion | The board is valid for local implementation and acceptance guidance under its recorded provenance; permission review is required only before redistribution or promotion to a stronger exact-build baseline | Manifest schema/unit tests require source, hash, state, and review fields; board-guided regression remains valid | Permission decision, reviewer identity/date, storage classification, and optional stronger baseline entry |

The board is used immediately for implementation review, board-guided screenshot acceptance, and
gap-directed browser checks. No board image is promoted to exact-build `approved` merely because
it visually complements another image. That stronger status is optional evidence for a covered
state and targeted closure evidence for a documented gap; see
`docs/tc2000-acceptance-governance.md`.

This board is therefore the active visual reference for the current goal, not merely a discovery
artifact. Each UI iteration must consult the relevant board group, compare a deterministic local
render, and record any uncovered or ambiguous state below. Using the board in this way is an
explicit acceptance flexibility and must be reported as such; it does not erase the gap register.

## State coverage ledger

The manifest records `board_covered_states` and `board_gap_states` for every required surface.
Covered means the board provides enough applicable visual/interaction evidence to guide the
implementation; it still requires a measured local regression baseline before final acceptance.
Gap states are not ignored: they remain limited, receive an interim functional oracle, and need
specific closure evidence.

| Surface | Board-covered states | Remaining gap states |
|---|---|---|
| Application shell | default, menu open, focused search | keyboard help, keyboard-selected search, fetching, stale data, delayed data, unavailable data |
| Workspace docking | tabbed, maximized, floating, restored, drag target | tool menu open, blocked pop-out |
| Chart window | daily candles, linked crosshair, drawing, alert marker | loading, error |
| Watchlist/columns/filters | sorted, grouped, stacked, filtered, selected, column editor, condition editor | partial coverage |
| Breadth composer/results | dense condition/filter language only | target-scope editor, nested predicate tree, aggregate/member/history states, occurrence linking, promotion |
| Study Lab | none (original product surface) | editor, validation, disabled controls, running, histogram, occurrence table, sandbox error |

Provider-error and Study Lab validation-error states now also have deterministic local baselines
in all four required display environments. They remain `required_missing` because the board does
not provide authoritative pinned-build styling for those states; the added screenshots strengthen
the interim oracle but do not close either visual-reference gap.

Study Lab structured-result rendering now has the same four-environment interim baseline for its
histogram and occurrence-table states. The fixture exercises the completed run surface, scalar
metric, bar chart, histogram, table, and clickable occurrence event together; these states remain
`required_missing` under `REF-STUDY-LAB-V25` because the board contains no authoritative Study Lab
capture.

Study Lab sandbox failures now also have a four-environment interim baseline. The failed-run fixture
keeps the sandbox diagnostic, warning, execution log, resource usage, and rerun affordance visible;
`sandbox_error` remains `required_missing` because the board contains no authoritative error-state
capture for this original surface.

## 2026-08-11 current-source visual revalidation

After the logout/request-boundary repair, the current Vite source was rechecked against the seeded
visual backend. The four-environment board-guided matrix passed `104/104` at 1920×1080 and
2560×1440, both at 100% and 125% display scale. No threshold, baseline, or mask changed. This is
the documented board-plus-deterministic-fixture interim track; exact-build, permission, and the
unrepresented state gaps remain unchanged and actionable.
