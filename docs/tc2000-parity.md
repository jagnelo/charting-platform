# TC2000 Version 25 Parity Matrix

## 2026-08-17 — Explicit cross-sectional breadth scope

The breadth composer now distinguishes a member rolling percentile from a cross-sectional rank
percentile. In the latter mode, each eligible member produces the selected scalar field at the
same observation timestamp, inclusive empirical ranks are calculated over valid members only, and
the declared operator/threshold determines each member's pass state. The response exposes the
selected `target_scope`, rank metric, denominator, coverage, exclusions, and historical state
changes; missing current bars are never forward-filled.

The workstation exposes the scope choice and persists it with the condition definition. An
unsupported cross-sectional condition is returned as an explicit exclusion rather than silently
using member-level semantics. Unit/API, frontend, and rebuilt authenticated browser coverage pass.
Richer derived/Python cross-sectional fields, mixed-scope nested composition, and complete
promotion fan-out remain explicit parity gaps.

## 2026-08-17 — Generic breadth range and percentile controls

The represented breadth composer now exposes two additional user-authored predicate families:
an inclusive measured-field range and a rolling empirical percentile comparison. They operate on
the selected member universe and are not SPY-specific metric labels. Current and historical
responses retain the existing member metric/Boolean values, denominator, coverage, exclusions,
and occurrence lineage. The workstation exposes field, bounds/window, target, and operator
controls and sends the same versioned condition payload used by the API.

The focused backend unit/API checks, frontend type-check/build, and authenticated seeded browser
slice pass. This is a semantic parity slice rather than a visual-reference change. Cross-sectional
rank semantics, prior high/low/event/benchmark-peer targets, richer derived-series composition,
and promotion into all compatible outputs remain explicit parity gaps; no unsupported role or
family is silently substituted.

## 2026-08-17 — Python breadth promotion parity slice

Research Results now exposes a promotion action for completed Python breadth-history artifacts.
The resulting EasyScan uses the immutable Boolean code version and a custom universe made from
the source run's declared canonical member IDs. Its condition metadata retains the source run,
definition/reproducibility identifiers, exact dataset-manifest fingerprint, membership/universe
metadata, and explicit current-data re-evaluation semantics. This prevents a point-in-time study
from being presented as a historical scan replay or silently widened to the full market.

The represented UI shows the action only for completed breadth-history runs and reports the
created scan and its lineage-preserving semantics. Current-only, incomplete, missing-artifact,
foreign, non-Boolean, and incomplete-universe paths are rejected. Promotion into plots, columns,
filters, gauges, alerts, Study Lab assets, and Strategy Lab signals remains an explicit parity gap.

## 2026-08-17 — Latest US market-family perspective directive

The parity target is not limited to SPX/SPY and its sectors. It comprises eight interchangeable
US roots: S&P 500, S&P MidCap 400, S&P SmallCap 600, S&P Composite 1500, Russell 1000, Russell
2000, Russell 3000, and Nasdaq 100. Changing the root must preserve the Version 25 workstation
mechanics while replacing the analysis universe: technicals, cap/equal and value/growth legs,
ratios, configurable breadth, leadership, concentration/dispersion, rotation, ranking, and
sector -> industry/proxy -> constituent drill-down remain available without route changes.

Each cap, equal, value, and growth role is resolved independently from canonical evidence. The
role may be an official index, labelled ETF proxy, verified equal/style ETF, or an explicitly
derived point-in-time series. A role that cannot be verified is rendered as unavailable, derived,
or `No verified mapped proxy`; it is never inferred from a ticker name or silently replaced by
SPY, QQQ, another family, or a current-only membership snapshot. SPY/RSP remains the reference
deconstruction, while Nasdaq 100 requires its own evidenced cap/equal pair (QQQ/QQQE only after
identity, holdings/weights, rebalance, dates, bars, and coverage are verified).

Breadth parity is generic and family/style scoped. The same member predicate composer must cover
moving-average state/distance, configurable 52-week-high/low distance, new highs/lows, RSI/trend,
volume/volatility, relative strength, benchmark/peer relationships, and Python-defined conditions.
Aggregate/history/occurrence outputs and all downstream charts, lists, filters, scans, gauges,
alerts, Study Lab artifacts, and exports must retain the selected root/role, membership version,
as-of policy, weighting method, coverage, exclusions, freshness, and provenance. This directive
expands the acceptance matrix; it does not relax missing-source or visual-gap handling.

## 2026-08-17 — Occurrence browser filters

The represented Research Results occurrence browser now has dense symbol and transition filters,
live result counts, keyboard-accessible controls, and an explicit no-match state. The filters
are local presentation state over persisted occurrence artifacts and preserve the same linked
chart behavior. Broader event-artifact filtering and promotion surfaces remain named gaps.

## 2026-08-17 — Python breadth history in Research Results

Collected isolated Python breadth histories now use the same dense result composition as other
Study Lab artifacts: a uPlot percentage history followed by a bounded occurrence browser. The
event click publishes canonical instrument identity and timestamp through the workstation link
bus. Runner cells are normalized at the persistence boundary and retain the direct-analysis
aggregate/timestamp semantics. This closes the represented result-surface state; occurrence
filtering beyond this artifact, promotion beyond EasyScan, and unrepresented exact Version-25
states remain explicit gaps.

## 2026-08-17 — Current US family perspective vision

The workstation parity target is an interchangeable set of eight US market roots: S&P 500, S&P
MidCap 400, S&P SmallCap 600, S&P Composite 1500, Russell 1000, Russell 2000, Russell 3000, and
Nasdaq 100. The dense Version 25 shell, linked symbol/timeframe behavior, charts, watchlists,
ratios, breadth, rankings, rotation, drill-down, Study Lab, and provenance/freshness states must
behave consistently when the selected root changes.

Every root has independent cap-weight, equal-weight, value, and growth roles when source evidence
supports them. The existing SPY/RSP deconstruction is the contract template; Nasdaq 100 requires
its own verified cap/equal relationship such as QQQ/QQQE, with native versus derived weighting
clearly labelled. Candidate symbols are not relationships by name. A missing relationship must
render as `No verified mapped proxy`, unavailable, or derived and must not borrow SPY, QQQ, or a
current-only snapshot.

The same selected root/leg drives top-down technicals, direct and cross-family ratios, sector ->
industry/proxy -> constituent navigation, and user-authored breadth. Breadth is a generic
predicate quantification over the selected point-in-time universe: examples include percentage
above a chosen moving average, percentage within a configurable distance of a 52-week high,
new-high/new-low participation, and Python-composed conditions. All resulting charts, tables,
occurrences, scans, gauges, alerts, Study Lab artifacts, and exports retain family/role,
membership/as-of, weighting, coverage, exclusions, freshness, and provenance lineage.

Any family/style state not represented by the reference board remains a named visual gap with an
interim deterministic oracle; it is never silently treated as pixel-verified.

## 2026-08-15 — Generic breadth occurrence parity slice

The generic historical breadth response now includes a deterministic occurrence stream derived from
its member-level historical results. A member entering or exiting the selected predicate is emitted
only after two known Boolean observations; initial values, missing bars, and exclusions do not
create synthetic transitions. Each event retains timestamp, canonical instrument identity, symbol,
metric, aggregate percentage, pass/eligible counts, and a stable occurrence ID. The workstation now
renders a bounded dense occurrence browser; each event retains its canonical instrument ID and
publishes symbol plus timestamp through the existing occurrence/link bus when clicked, so linked
uPlot charts navigate to the selected historical bar.

The focused authenticated browser fixture passes the represented click-to-chart path. During the
first run a real pointer-overlap defect in the unavailable-history state and a query-string route
fixture mismatch were found and fixed; the unchanged acceptance then passed. This closes the
represented backend/browser occurrence path, not occurrence filtering, isolated-Python occurrence
artifacts, promotion beyond EasyScan, or unrepresented Version-25 visual states.

The isolated Python breadth result now carries the same typed occurrence stream for aligned
historical Boolean runs. Events are projected after the runner result is collected, so source code
still executes only in the no-network runner and the response retains the immutable code-version,
dataset-manifest, membership, as-of, and reproducibility lineage. This is an API/result-contract
parity slice; direct workstation rendering is covered, while promotion beyond the
lineage-preserving EasyScan target remains open.

## 2026-08-15 — Full US benchmark-family perspective matrix reaffirmed

The completion bar now explicitly covers eight independently selectable US roots: S&P 500,
S&P MidCap 400, S&P SmallCap 600, S&P Composite 1500, Russell 1000, Russell 2000, Russell 3000,
and Nasdaq 100. The same Version-25 workstation composition must carry each root through
benchmark technicals; cap/equal/value/growth comparisons; parent, peer, and cross-family ratios;
condition-driven breadth; participation and leadership; concentration/dispersion; drawdown and
volatility; relative rotation; ranking; and sector → industry/proxy → constituent drill-down.

Each family leg is independent. The parity run verifies an official identity when entitled, a
labelled cap proxy, an equal-weight vehicle or point-in-time derived series, and every evidenced
value/growth sub-index or ETF. Candidate symbols such as SPY/RSP, MDY/MDYG/MDYV, SLY/SLYG/SLYV,
IWB/IWF/IWD, IWM/IWO/IWN, IWV, and QQQ/QQQE are not relationships by name: canonical issuer,
holdings/weights, membership/rebalance, effective/known-at, adjustment, bars, coverage, and
provenance evidence are required. Nasdaq 100 has a mandatory cap/equal deconstruction fixture
(QQQ versus QQQE or another independently verified equal proxy) once that evidence is present.

The selected root/leg and its exact membership, weighting method, as-of/known-at policy, coverage,
exclusions, freshness, and provenance must survive technicals, ratios, breadth, charts, watchlists,
scans, gauges, Study Lab, reusable plots, exports, and linked drill-down. A missing official,
equal, value, growth, holdings, or historical source is a visible `No verified mapped proxy`,
unavailable, or derived state. It is never silently substituted. All eight roots and every
verified leg must be exercised as real analysis perspectives; a selector-only check is not parity.
This is a scope clarification, not an acceptance relaxation.

## 2026-08-15 — Derived-equal historical concentration parity slice

Families whose taxonomy explicitly permits derived equal weighting now receive historical
concentration points even when no equal-weight ETF mapping exists. At each observed timestamp the
route selects only constituent/official-constituent/ETF-proxy-constituent rows whose member-level
effective and known-at boundaries are valid, then reports equal-weight top-N/HHI/effective-count,
distribution, coverage, membership version, and `point_in_time_group_membership` semantics. These
points deliberately carry no ETF holdings snapshot ID; native ETF history and derived group history
remain distinguishable.

The derived path explicitly permits a benchmark root registered after its historical member rows,
while ordinary group snapshots still enforce the root lifecycle boundary. A regression proves a
later-known member changes the derived universe only after its known-at timestamp. This closes the
derived-equal historical concentration contract, not complete eight-root membership/rebalance
population, native equal-weight history, historical breadth occurrences, or final browser/visual
parity.

## 2026-08-15 — Historical family concentration/dispersion parity slice

Family concentration now has a historical endpoint and workstation evidence path. At each observed
bar timestamp it chooses the latest holdings disclosure that was composition-valid and known to the
platform by that timestamp; future snapshots cannot influence earlier points. Each role's points
retain snapshot/membership identity, composition and known-at dates, reported-weight method,
top-N/HHI/effective-count metrics, distribution statistics, coverage, and exclusions. The
SPY fixture regression proves a later disclosure does not become active before its known-at time.

The current browser surface displays the bounded history-point count beside the current dense
concentration strip. This closes the reported-weight historical contract/presentation slice; the
derived-equal historical contract is documented above. Complete S&P/Russell/Nasdaq role snapshots,
rebalance continuity, longer history/occurrence visualization, and final all-root provider-backed
parity remain open.

## 2026-08-14 — Family concentration and dispersion parity slice

The family breadth surface now includes a dense concentration/dispersion strip for each available
cap/equal/value/growth leg. It is sourced from the same point-in-time holdings/constituent
snapshot used by drill-down, rather than a second universe resolver. The strip discloses top-N
reported weight, HHI, effective constituent count, selected-period return dispersion, and coverage
alongside the family role label and proxy symbol. A role without verified mapping, holdings, weight,
or bars remains unavailable with an explicit warning and zero coverage; it is never substituted by
SPY, QQQ, another family, or a current-only inferred relationship.

The backend contract and store cache identity include family, timeframe, adjustment, as-of,
rank-period, and top-N. The browser fixture validates the SPY/RSP cap/equal presentation and the
store unit validates stable loading/cache behavior. This closes the current concentration UI slice
only. Historical concentration/dispersion, rebalance-aware weights, complete provider population
for S&P 400/600/1500 and Russell 1000/2000/3000/Nasdaq 100, and final all-root visual acceptance
remain open matrix items.

## 2026-08-14 — Dated family coverage evidence strip

The family analysis backend now exposes `GET /analysis/benchmark-families/{family_key}/coverage`.
It returns each cap/equal/value/growth role independently, with all visible dated holdings
disclosures up to a bounded limit and their composition date, requested as-of date, known-at time,
source/provider, provenance, completeness, row count, and resolution counts. Supplying `as_of`
uses the existing historical-safe rule: composition and known-at must both be no later than the
requested time. Missing mappings and mapped instruments with no snapshots remain explicit role
states; no family proxy is substituted.

The Market Breadth family surface now renders a compact dated-disclosure evidence strip alongside
the mapping and constituent panels. The store cache identity includes family, as-of, and limit,
and the browser fixture exercises the strip. This closes the coverage/readiness presentation
slice only. Complete historical rebalance continuity, a user-selectable as-of control, and
all-family historical breadth/ratio/rotation acceptance remain open; no acceptance flexibility
was used.

## 2026-08-14 — US index-family and style perspective acceptance clarification

The Version 25 workstation is expected to support the full US index-family matrix, not only the
original SPX/SPY and sector examples. The required roots are S&P 500, S&P MidCap 400, S&P SmallCap
600, S&P Composite 1500, Russell 1000, Russell 2000, Russell 3000, and Nasdaq 100. Each root is a
reusable, linked analysis perspective with benchmark technicals, cap/equal/value/growth legs,
ratios, generic breadth, ranking, drill-down, and the same dense workstation chrome.

For every root, the parity run attempts the official index identity (when entitled), cap proxy,
equal-weight vehicle or point-in-time derived equal series, and each evidenced value/growth
sub-index or ETF. SPY/RSP is the S&P 500 fixture. Nasdaq 100 requires a separately evidenced
cap/equal deconstruction such as QQQ/QQQE; candidate symbols are not accepted from names alone.
The accepted result records issuer/source, relationship, native-versus-derived weighting,
membership/rebalance version, effective/known-at dates, bars, adjustment, coverage, exclusions,
freshness, and provenance. Missing evidence is rendered as `No verified mapped proxy`, unavailable,
or derived, never as a silent SPY/QQQ or current-snapshot substitution.

The same selected root/leg must feed all relevant companion views: configurable predicate breadth
(including moving-average, high/low distance, new-high/new-low, RSI, trend, volume, volatility,
relative-strength, benchmark/peer, and unified-Python predicates), participation and leadership,
concentration and dispersion, correlation, drawdown/volatility regimes, relative rotation,
cross-family ranking, seasonality/regime studies, sector → industry/proxy → constituent drill-down,
watchlists, scans, gauges, Study Lab artifacts, reusable plots, and exports. Acceptance exercises
these as analysis perspectives for all eight roots and each verified leg rather than only checking
that selector rows exist. This is a scope clarification, not a threshold or evidence relaxation.

## 2026-08-14 — Expanded US benchmark-family visual/workflow matrix

The visual parity target includes the eight US analysis roots required by the product vision:
S&P 500, S&P MidCap 400, S&P SmallCap 600, S&P Composite 1500, Russell 1000, Russell 2000,
Russell 3000, and Nasdaq 100. The benchmark-family selector, cap/equal/style comparison
surfaces, breadth controls, ratio charts, ranking tables, member drill-down, freshness and
provenance states must use the same dense Version 25 workstation composition for every family,
not only the original SPY example. Nasdaq 100 specifically requires the QQQ/QQQE-style
cap/equal view only after the relationship and holdings evidence is verified.

The parity matrix must include represented states for family and leg selection;
cap/equal/value/growth side-by-side comparisons; missing or derived legs; ETF-native versus
locally derived weights; current and historical breadth; family-relative ratios;
cross-family ranking/rotation; and constituent drill-down. The board remains the visual
authority for states it represents. Any family/style state absent or ambiguous on the board is
recorded as a named gap with an interim deterministic oracle; it is not silently accepted or
masked.

The Market Breadth family surface now renders overview mapping/readiness cards and the selected
role's source-labelled constituent rows, including composition date, provider, completeness,
coverage, and canonical member publication into linked charts. This is a browser route/wiring
checkpoint for the family matrix, not evidence that all eight families are populated or
historically complete. The current fixture covers SPX/SPY/RSP and NVDA; missing mappings still
render explicit unavailable states.

### Required US family perspective matrix

This matrix is a completion requirement for the active goal. It is not satisfied by a family
selector, a symbol-search result, or a single SPY-backed demonstration. The eight roots and every
verified cap/equal/value/growth leg must be traversable through the same workstation interactions,
with an explicit unavailable or derived state wherever evidence is absent.

The board-guided workstation must make the following perspectives first-class, not merely expose
the eight roots in a selector. Each row is a reusable Version 25 analysis surface with the same
dense tool-window, linked-chart, watchlist, ratio, breadth, Study Lab, and provenance mechanics:

| root | cap/equal relationship | style relationships | breadth and other views |
| --- | --- | --- | --- |
| S&P 500 | cap proxy versus verified equal ETF/derived series, including SPY/RSP where evidenced | verified value and growth legs | all generic predicates, sector/industry/member participation, concentration, dispersion, rotation, drawdown, volatility, ranking, and ratios |
| S&P MidCap 400 | cap proxy versus verified equal ETF/derived series | verified value and growth legs | same contract |
| S&P SmallCap 600 | cap proxy versus verified equal ETF/derived series | verified value and growth legs | same contract |
| S&P Composite 1500 | cap proxy versus verified equal ETF/derived series | verified value and growth legs | same contract |
| Russell 1000 | cap proxy versus verified equal ETF/derived series | verified value and growth legs | same contract |
| Russell 2000 | cap proxy versus verified equal ETF/derived series | verified value and growth legs | same contract |
| Russell 3000 | cap proxy versus verified equal ETF/derived series | verified value and growth legs | same contract |
| Nasdaq 100 | explicit cap/equal deconstruction, such as QQQ versus QQQE after evidence verification | any evidenced style leg, otherwise unavailable | same contract plus cross-check of cap/equal concentration and leadership |

Candidate ETF symbols are discovery inputs rather than accepted relationships. Examples include
SPY/RSP and SPYG/SPYV, MDY with MDYG/MDYV, SLY with SLYG/SLYV, IWB with IWF/IWD, IWM with
IWO/IWN, IWV, and QQQ/QQQE. A candidate becomes selectable only after the canonical security
master records issuer/source evidence, relationship role, holdings or derived-membership policy,
effective/known-at dates, and bar/coverage status. If an equal, value, or growth leg does not
meet that evidence bar, the UI must show `No verified mapped proxy` or a truthful unavailable or
derived state. It must never substitute SPY, QQQ, another family, or a current-only snapshot.

Every available root/leg is accepted through the same top-down path: root benchmark and technicals
→ cap/equal/style comparison → sector and industry/proxy ranking → constituent drill-down. The
same selected universe is then available to condition-driven breadth (including moving-average,
52-week-high/low, volume, RSI, volatility, relative-strength, and arbitrary Python predicates),
relative-strength ratios, participation/leadership, concentration/dispersion, drawdown/volatility,
relative rotation, cross-family ranking, watchlists, scans, gauges, Study Lab artifacts, and
exports. Family, role, native-versus-derived weighting, membership version, as-of/known-at policy,
coverage, exclusions, freshness, and provenance must survive every transition and output.

## 2026-08-14 — QQQE route evidence

QQQE now has explicit canonical route metadata for the Direxion adapter and its official
product page. The opt-in live probe fetched and parsed the symbol-scoped holdings export, while
the deterministic route and taxonomy regressions prevent the Nasdaq-100 equal leg from falling
through issuer-name inference. This is provider-route evidence only; historical rebalance,
point-in-time membership, bar coverage, and populated browser parity remain open states in the
family matrix.

## 2026-08-14 — Family issuer-route live matrix

The opt-in route matrix now passes for all 15 newly mapped SPDR/iShares family legs. The first
run exposed stale iShares identifiers for `IWD` and `IWN`; correcting them to `239708` and
`239712` respectively restored the complete `15/15` result. The failed run remains recorded as
fix-first evidence. This validates current issuer retrieval, not historical membership or
browser population.

## 2026-08-14 — iShares historical as-of holdings route

The BlackRock/iShares public product-data API accepts `asOfDate=YYYYMMDD`. The iShares adapter
now requests that explicit date, preserves the requested and returned composition dates in
provenance, and labels the route `issuer_public_json_api_as_of_date`. The focused IWV regression
parses a dated NVDA row and verifies the product ID and query parameter. This improves the
point-in-time evidence path for Russell/S&P ETF-proxy legs but does not by itself establish a
complete historical rebalance series, official index membership, or populated browser acceptance.

The dated refresh API now preserves issuer truth at persistence time: it stores the returned
composition date, keeps the requested evaluation date as `as_of_date`, and rejects a provider
response dated after the request. The focused IWV API regression proves a 2026-06-30 request can
persist a returned 2026-06-27 snapshot while retaining both dates in the response and legal
metadata. This removes a local point-in-time provenance defect; historical continuity and browser
family acceptance remain open.

Historical family population now has an explicit admin maintenance contract at
`POST /etf-holdings/benchmark-family/{family_key}/refresh-date`. It accepts selected family roles,
refreshes each mapped leg independently, and returns snapshot/composition evidence alongside
unavailable or failed legs. The route never substitutes a cap proxy for a missing style leg. The
focused regression exercises Russell 3000/IWV and confirms a returned 2026-06-27 snapshot for a
2026-06-30 request while retaining the missing value leg as unavailable. This is orchestration
readiness only; complete historical population and browser acceptance remain open.

The opt-in live historical matrix passes `7/7` for iShares `IJR`, `IWB`, `IWD`, `IWF`, `IWN`,
`IWO`, and `IWV` at requested date 2026-06-30, with parseable rows and explicit requested versus
composition-date metadata. This is evidence for seven issuer-backed routes only; it does not
establish official index membership, complete rebalance continuity, or populated browser visuals.

The admin historical family maintenance contract now also supports a bounded date set through
`POST /etf-holdings/benchmark-family/{family_key}/refresh-range`. Dates are normalized and each
run retains its requested/composition provenance plus independent role outcomes. This is an
orchestration primitive for building family history, not a claim that the free-source route has
already produced complete rebalance continuity.

## 2026-08-14 — Family-leg relative-strength ratio contract

Family role analysis now exposes `GET /analysis/benchmark-families/{family_key}/ratios`. A
selected cap/equal/value/growth leg can be compared directly with the family cap proxy and, when
requested, an explicit market benchmark. Ratios use intersecting timestamps only, preserve
partial-overlap warnings and coverage, and carry family role, benchmark role, membership version,
adjustment, freshness, and as-of provenance.

Unavailable mappings and canonical identities are errors rather than silent substitutions. This
closes the backend ratio primitive for family analysis; batch-all-leg composition, weighting
evidence, breadth/rotation/ranking, browser rendering, and exact visual/end-to-end acceptance
remain open. No acceptance criterion was relaxed.

## 2026-08-14 — Family/style legs as generic breadth universes

The generic breadth API and composer now accept a `benchmark_family` universe with an explicit
`cap_weight`, `equal_weight`, `value`, or `growth` role. The selected role resolves through the
family's configured mapping and point-in-time ETF-proxy holdings snapshot, so the response retains
family identity, proxy symbol, mapping verification, composition/known-at timestamps, source,
completeness, snapshot hash, and ETF-proxy membership semantics. Current and historical calls use
the same universe contract; the family role is not reduced to the current SPY-sector presets.

When the active breadth root is a benchmark family, the custom condition composer exposes
`Selected family leg`. This is the UI path for applying the same user-authored predicate (including
the 200-day average and within-1%-of-52-week-high fixtures) to each available S&P, Russell, or
Nasdaq family/style leg. Missing mappings, profiles, holdings, bars, or member resolution remain
structured unavailable/exclusion states. No family role falls back to SPY, QQQ, another family,
or a non-point-in-time membership snapshot. Focused current/history integration and Chromium
coverage pass; provider population and the complete cross-family acceptance matrix remain open.

## 2026-08-14 — Constituent weighting evidence

Family and ETF-proxy constituent rows now retain the disclosed snapshot evidence needed for a
cap/equal/style audit: position, weight, shares, market value, holding type, row type, and
resolution confidence. The values are copied from the dated source snapshot; the API does not
invent index weights or relabel ETF-proxy membership as official membership. Rows without bars
remain visible with their explicit exclusion/warning state. This strengthens the backend evidence
contract; provider/rebalance history, complete family population, and full browser presentation
remain open.

## 2026-08-14 — Family-leg constituent drill-down contract

The family workflow now has a shared constituent route:
`GET /analysis/benchmark-families/{family_key}/constituents?role=cap_weight|equal_weight|value|growth`.
It resolves only the requested family mapping, selects the appropriate point-in-time ETF holdings
snapshot, and returns the existing technical/member contract with family and mapping-role
provenance. ETF-proxy membership remains labelled as such; the route does not imply official index
membership.

Missing mappings, canonical identities, or holdings snapshots return structured family capability
errors. No role falls back to the family cap proxy, SPY, QQQ, or another family. This closes the
backend route bridge for constituent drill-down, not provider population or browser wiring:
historical holdings completeness, family ratios/breadth/rotation, populated UI drill-down, and
exact visual/end-to-end acceptance remain open. No acceptance criterion was relaxed.

## 2026-08-14 — Point-in-time derived equal-weight family series

Benchmark families that explicitly permit derived equal weighting now expose
`GET /analysis/benchmark-families/{family_key}/derived-equal-weight`. The endpoint selects only
point-in-time constituent membership rows and aligned local bars, then emits a normalized
equal-start-weight series with declared methodology, membership version, effective/known-at
provenance, adjustment, freshness, coverage, and exclusions. Proxy mapping rows are deliberately
not eligible constituents.

The contract distinguishes three states: a family may disallow derivation; it may allow it but
have no point-in-time constituent membership; or it may produce a partial/complete series from
available member bars. Each state is explicit and testable, with no SPY/QQQ or other-family
fallback. This closes the reusable derived-series backend bridge only. Provider-backed holdings,
rebalance/weight history, family-wide ratios/breadth/rotation, browser drill-down, and exact
visual acceptance remain open; no acceptance criterion was relaxed.

## 2026-08-14 — Benchmark-family overview analytics contract

The family selector now has a provider-neutral overview contract at
`GET /analysis/benchmark-families/{family_key}/overview`. The response keeps the official index
identity separate from cap/equal/value/growth proxy mappings, reports canonical instrument
availability and derived-equal methodology, and carries the existing membership version,
coverage, freshness, exclusions, and snapshot rows. This lets the workstation render one shared
top-down surface for S&P 500/400/600/1500, Russell 1000/2000/3000, and Nasdaq 100 without
hard-coding a SPY fallback.

When a family cap proxy is not yet present in the security master, the endpoint returns no rows,
`cap_proxy_unavailable`, and explicit provenance; it does not substitute SPY, QQQ, or another
family. The focused integration suite verifies this behavior and primes taxonomy only through the
normal market-group bootstrap, keeping the overview read-only. Provider verification,
point-in-time constituents/holdings, native-versus-derived equal weights, available-cap browser
drill-down, family-wide breadth/ratios/rotation, and exact visual acceptance remain open. No
acceptance criterion was relaxed.

## 2026-08-14 — Benchmark-family taxonomy and selectable child universes

The backend now exposes a JSON-safe registry for the eight required US benchmark families. Each
family carries its official logical identity, configured cap/equal/value/growth mapping candidates,
source URLs, mapping state, and derived equal-weight policy. The registry explicitly retains
`No verified mapped proxy` for absent style/equal relationships and does not infer relationships
from names.

`us-benchmarks` now owns child `benchmark_family` groups, discoverable through
`GET /market-groups/us-benchmarks/children`. Canonical proxy identities are attached to a child
only when already present in the security master; each member retains its cap/equal/value/growth
role and relationship provenance. The core identity bootstrap registers configured proxy
identities as identity-only records, never as official index constituents or fabricated data.
The breadth universe selector can load these child groups and uses their configured cap proxy for
benchmark-relative calculations while retaining the existing SPY/RSP default workflow.

This closes the taxonomy/selection contract only. Provider evidence, point-in-time membership and
holdings, derived equal-weight calculation, family-wide snapshots/ratios/rotation/breadth history,
populated browser drill-down, and visual parity remain open; no acceptance criterion was relaxed.

## 2026-08-14 — US benchmark-family and factor-analysis acceptance expansion

The workstation scope is family-wide: S&P 500, S&P MidCap 400, S&P SmallCap 600, S&P Composite
1500, Russell 1000, Russell 2000, Russell 3000, and Nasdaq 100 are selectable, versioned roots.
The taxonomy must retain each logical family even when free-source evidence does not provide an
official constituent feed, equal-weight vehicle, or value/growth vehicle. It records independently
which official identity, cap proxy, equal proxy/derived series, and value/growth variants are
actually evidenced at each effective/known-at interval.

Every available family and style leg uses the same analysis contract: benchmark technicals;
cap/equal and value/growth comparisons; generic predicate breadth; participation/leadership;
concentration/dispersion; drawdown/volatility; relative rotation; cross-family ranking; and
drill-down into sectors, industries/proxies, and constituents where classification or holdings
evidence supports it. SPY/RSP is the reusable pattern, and Nasdaq 100 requires an equivalent
cap/equal deconstruction such as QQQ versus a separately verified equal-weight proxy such as QQQE.
A derived equal-weight series discloses its point-in-time membership, rebalance/weight method, and
exclusions; it is never presented as ETF-native.

Generic breadth applies to each family and each available leg/style, not only SPY sectors. The
user independently selects family/leg universe, measured field, target/operator, alignment,
timeframe, as-of policy, and nested condition; aggregate current/history, member pass/fail,
occurrences, ratios, charts, scans, gauges, Study Lab artifacts, and exports retain family
identity, proxy semantics, membership version, coverage, freshness, and exclusions. Missing
style/equal mappings display `No verified mapped proxy`; no family silently falls back to SPY,
QQQ, or another unrelated universe. This scope expansion has no acceptance relaxation.

## 2026-08-14 — Isolated-Python breadth predicate execution

Generic breadth now has an explicit isolated-Python path in addition to the platform-owned
visual-condition subset. `POST /analysis/breadth/python` accepts a user-owned immutable Boolean
CodeVersion plus universe, parameters, timeframe, adjustment, session, benchmark, and as-of
configuration. It resolves canonical local membership and queues the source through the existing
no-network research runner; FastAPI and the browser never execute user source.

`GET /analysis/breadth/python/runs/{run_id}` collects current or historical output with condition
and runtime identity, membership version, dataset manifest, reproducibility hash, pass/eligible
counts, percentages, per-member values, exclusions, and progress. Historical execution uses
aligned timestamp truncation and excludes missing bars instead of forward-filling. Boolean output
artifacts may carry a finite metric and an explicit exclusion code. The existing
`/screeners/from-python-condition/{code_version_id}` route is exercised as the first compatible
promotion target and retains the exact immutable CodeVersion reference.

This closes the isolated execution/runtime bridge only. Full visual condition-tree authoring,
occurrence-to-chart linking, promotion into every compatible uPlot/list/filter/gauge/alert/export
target, and point-in-time ETF browser evidence remain open. No visual threshold, provider rule, or
acceptance criterion was relaxed.

## 2026-08-14 — Versioned condition reuse in generic breadth

Generic breadth current and history requests now accept either an inline supported condition or a
user-owned immutable visual condition asset. When `condition_asset_key` is supplied, the backend
loads the matching condition library item for the authenticated user, maps the supported visual
AST into the canonical breadth condition contract, and rejects inline/asset conflicts, missing
assets, malformed payloads, and unsupported visual clauses with structured errors. The response
and definition hash retain the condition asset key, library version, and generated unified Python
CodeVersion ID, so reusing a saved condition is reproducible rather than a hidden copy/paste.

This is deliberately a bounded bridge: FastAPI does not execute arbitrary user Python. The
isolated runner, full visual condition-tree authoring, historical occurrence linking, and
promotion into compatible charts, watchlists, filters, scans, gauges, alerts, and exports remain
open acceptance items. No visual threshold, provider rule, or acceptance criterion was relaxed.

## 2026-08-14 — Expanded US benchmark-family and cap/equal/style scope

The top-down workstation now has an explicit benchmark-family matrix beyond SPX/SPY. First-class
roots are S&P 500, S&P MidCap 400, S&P SmallCap 600, S&P Composite 1500, Russell 1000, Russell
2000, Russell 3000, and Nasdaq 100. Each family must resolve an official index identity when
entitled, a labelled cap-weighted proxy, a verified equal-weight proxy or reproducible derived
equal-weight series, and value/growth sub-index or ETF proxies wherever source evidence confirms
they exist. Missing mappings remain visible as `No verified mapped proxy`; names alone never create
taxonomy relationships.

The existing SPY/RSP comparison is the reusable pattern. Nasdaq 100 must provide an equivalent
cap/equal deconstruction (for example QQQ versus a verified equal-weight proxy such as QQQE), and
the S&P 400/600/1500 plus Russell 1000/2000/3000 families must use the same contracts. Every
family/style view receives benchmark technicals, cap/equal/style spreads, generic predicate
breadth, participation and leadership, concentration, dispersion, drawdown/volatility, relative
rotation, cross-family ranking, and member drill-down wherever data permits. Native ETF weights,
derived weights, membership snapshots, effective/known-at times, coverage, exclusions, and
freshness are always shown; no family silently falls back to SPY or QQQ.

## 2026-08-14 — Benchmark-family participation parity slice

The family workflow now has a role-aware participation batch parallel to the family technical
snapshot. For each independently mapped cap/equal/value/growth leg, the backend evaluates member
participation above SMA20/50/200, proximity to a rolling 52-week high, configurable new-high
windows, trend-up state, and relative strength to the family cap proxy when aligned bars exist.
Each role carries its own membership version, provenance, coverage, exclusions, and unavailable
state; a missing cap or style leg is never replaced by SPY, QQQ, or another role.

The authenticated workstation renders these values as a dense Version-25-style family
participation strip with role-local loading, partial, warning, and unavailable states. The focused
browser oracle asserts the visible cap-role strip while backend and store tests assert the
configurable near-high threshold/lookback and no-fallback semantics. This is a parity sub-gate,
not completion of the generic breadth contract: historical role participation, arbitrary
condition-driven studies, occurrence linking, and all-family ranking/rotation/dispersion remain
open and are tracked in the controlling plan.

## 2026-08-14 — Historical family participation parity slice

Family role participation now has a historical companion endpoint. SMA20/50/200 percentages are
calculated independently for cap/equal/value/growth roles over actual observed timestamps from
each role's point-in-time holdings. The contract retains membership/provenance and excludes
missing bars at the timestamp instead of forward-filling them. The workstation requests this
batch alongside current participation and exposes the aligned-point count in the dense role strip.

This slice is intentionally narrower than the generic breadth completion bar: historical
near-high/new-high/trend/relative-strength predicates, arbitrary user-authored conditions,
occurrence linking, role ranking, rotation, and full eight-root historical population remain open
and visibly tracked.

## 2026-08-14 — Benchmark-family role-ranking parity slice

Mapped family roles now expose transparent performance ranking across 1D/1W/1M/3M/6M/YTD/1Y,
including the spread versus the family cap proxy. The workstation renders the rank and 1M
cap-relative delta in the dense role strip, with role-local warnings and explicit unavailable
states. The endpoint is provider-neutral and uses aligned local bars; missing evidence cannot be
filled by SPY, QQQ, another family, or a current-only substitute.

This is the current leadership/ranking sub-gate only. Historical ranking curves, cross-family
ranking, relative-rotation tails and states, concentration/dispersion, and complete eight-root
population remain open in the controlling plan.

## 2026-08-14 — Cross-family ranking parity slice

The family workstation now requests a provider-neutral cross-family ranking batch over the eight
configured US roots. The contract preserves each root's canonical cap proxy, return period,
membership/provenance, coverage, and unavailable state, and only computes relative spreads when an
explicit benchmark and aligned bars exist. The dense workstation strip exposes leading roots and
their performance without leaving the active breadth surface; cache identity includes timeframe,
adjustment, `as_of`, rank period, and the selected family set.

The first rebuilt browser run found a genuine layout regression: implicit CSS grid rows let the new
ranking/participation strips overlap the custom-condition controls. The owning breadth container was
repaired as a height-constrained scrollable flex surface, and the unchanged authenticated browser
oracle passed with the RSI interaction and cross-family assertion. This is a closed localized
defect, not a relaxed visual acceptance. Historical ranking curves, rotation, concentration/
dispersion, and fully populated all-root evidence remain open.

## 2026-08-14 — Historical cross-family leadership parity slice

The cross-family contract now has a historical companion. It returns bounded observed-timestamp
performance and rank points for each selected family cap proxy, with optional benchmark-relative
returns, explicit rank period, `as_of` truncation, coverage, and row-local warnings. Period returns
use actual prior observations and calendar-year boundaries; gaps are not forward-filled. The client
cache identity carries the family set, timeframe, adjustment, rank period, benchmark, as-of, and
limit. The workstation reports the available history-point count beside the current ranking.

The focused browser acceptance verifies the history evidence without changing the existing role,
RSI, or custom-condition interactions. This closes historical cross-family ranking only; historical
relative-rotation tails, concentration/dispersion, provider-backed eight-root population, and
unrepresented Version 25 visual states remain open.

## 2026-08-15 — Benchmark-family relative-rotation parity slice

Relative Rotation now accepts each of the eight benchmark-family roots as a universe. For a selected
family it compares cap/equal/value/growth legs against the family’s resolved cap proxy, preserving
transparent ratio trend/momentum semantics, sampled tails, state transitions, heading, distance,
velocity, time-in-state, coverage, freshness, and role-local unavailable states. The tool resolves
the returned cap benchmark rather than displaying a hard-coded SPY label, and keeps the generic
sector/market-group route unchanged.

The rebuilt browser matrix covers an S&P MidCap 400 family selection with an unavailable equal leg
and verifies that the generic sector rotation flow still passes. This closes family-role rotation
presentation and bounded-tail behavior only; longer historical rotation, concentration/dispersion,
provider population, and unrepresented Version 25 visual states remain open.

## 2026-08-14 — Breadth scope expanded to condition-driven cross-sectional studies

The breadth requirement is broader than the current fixed metric panel. The implemented panel
is a useful represented-state baseline: it selects the current `sp500-sectors` or
`us-benchmarks` group, evaluates fixed MA20/50/200, near-52-week, new-high/new-low, trend, and
MA-distance metrics, exposes coverage and exclusions, and provides passing/failing drill-down
plus historical fixed-MA uPlot series.

The controlling plan now treats that panel as a preset over a generic breadth definition, not as
the completion boundary. The remaining in-scope breadth contract must let users select a
versioned universe (official index where entitled, explicitly labelled ETF-proxy holdings,
sector/industry/benchmark group, watchlist/combo, basket, managed scan, or explicit symbols),
select or author a reusable unified-Python condition, and aggregate pass/eligible counts and
percentages across members. It must support configurable moving-average state/distance,
distance to 52-week highs/lows, new-high/new-low windows, trend, RSI, volume, relative strength,
and arbitrary safe predicates/AND/OR/NOT combinations, with current and historical output,
per-member values, exclusions, coverage, and drill-down.

The two mandatory representative studies are:

1. percentage of SPY-proxy constituents above their 200-day average;
2. percentage of SPY-proxy constituents within 1% of their 52-week high.

Both must use the same generic universe/condition engine and be reusable as Study Lab artifacts,
independent uPlot panes/plots, columns/filters, EasyScan conditions, gauges, alerts, and
exports where their output contracts allow. The current roots do not yet provide an official
S&P 500 constituent group, so proxy membership, holdings date, known-at/effective-at semantics,
missing bars, and historical coverage must remain visibly labelled. This is an open functional
parity gap, not an acceptance relaxation; no fixed-metric test or visual threshold is being
treated as proof of the expanded contract.

Implementation checkpoint (2026-08-14): `POST /analysis/breadth` and the shared deterministic
evaluator now provide the first generic condition-driven path for canonical groups, labelled ETF
holdings proxies, and explicit symbols. Supported predicates include SMA/EMA state, 52-week
distance, new highs/lows, trend, RSI, volume ratio, and relative strength; responses carry stable
definition hashes, membership/proxy provenance, per-member results, denominator/coverage,
freshness, and exclusion warnings. The breadth tool exposes a compact composer for current-group
and SPY-proxy studies. Backend focused and API integration tests, frontend 819/819, type-check, and
production build pass. Historical generic evaluation, full point-in-time ETF acceptance, unified
Python/research reuse, independent uPlot panes, and promotion targets remain open parity gaps.

Implementation checkpoint 2 (2026-08-14): the generic path now supports aligned historical
`POST /analysis/breadth/history` output with the same definition hash and condition semantics;
members missing a bar at a timestamp are explicitly excluded rather than forward-filled. The
isolated runner exposes `research.breadth_condition(dataset, condition, history?)`, Study Lab has
factory starters for above-average and within-1%-of-52-week-high participation, and the workstation
renders the generic percentage history through a dedicated uPlot component. Runner/factory, API,
uPlot lifecycle, frontend 821/821, type/build, Ruff, and diff checks pass. Full ETF point-in-time
browser evidence, arbitrary Python combinations, and promotion into other workstation targets
remain open.

## 2026-08-14 — Breadth predicate quantification expansion

The breadth parity contract is now explicitly “evaluate a user-authored predicate for every
eligible member, then aggregate”, rather than “choose a named breadth metric”. The saved
definition must independently show the measured field/series, target/relationship, operator,
lookback/alignment, target scope, and nested composition. Required representative predicates now
include close above SMA(200), within 1% of a rolling 252-session high, volume above an average,
an RSI range, a member/benchmark relative-strength test, and a nested combination. The engine
must preserve the same semantics for aggregate current/history, member pass/fail, exclusions,
state changes/occurrences, and compatible promotion targets.

This broadens implementation scope without relaxing acceptance. The compact field/operator/
comparison composer and recursive runtime are only an interim platform-owned slice. Full visual
condition-tree editing, arbitrary unified-Python predicate execution through the isolated runner,
historical occurrence linking, point-in-time ETF browser evidence, and promotion into compatible
charts, lists, scans, gauges, alerts, and exports remain open parity items. A cross-sectional
rank/percentile is a separate derived series and must never be silently substituted for a
per-member predicate.

## 2026-08-14 — Study Lab export and board-guided visual revalidation

- Active Study Lab export now covers scalar, Boolean, and structured artifacts; authenticated
  `F8p-export` verifies both scalar and structured run-scoped JSON downloads.
- The unchanged board-guided Study Lab original-surface test passed `1/1` at 1920x1080/100% after
  rebuilding the stack with the required seeded fixture mode. No baseline, mask, threshold, or
  product criterion changed. `REF-STUDY-LAB-V25` remains an explicit visual-reference gap.
- The first unprivileged browser launch failed before page creation at the macOS Mach-port
  boundary, and the first elevated run exposed a backend fixture-mode mismatch; both were fixed
  through the documented environment recovery path rather than by weakening acceptance.

## 2026-08-14 — Study Lab artifact export browser acceptance

- Authenticated `F8p-export` now proves the active Study Lab Export control downloads a typed
  `completed_streaks` artifact with the expected run-scoped JSON filename.
- Rebuilt Chromium `1/1` in 4.9s with no critical diagnostics. Acceptance flexibility used:
  **none**; no visual threshold, mask, or board rule changed.

## 2026-08-14 — Study Lab artifact export from active runs

- The active Study Lab now exposes an Export control on each non-scalar result artifact. The
  downloaded JSON preserves the run ID, reproducibility hash, artifact identity, type, and value.
- Focused Study Lab `22/22`, full frontend `819/819`, type-check/build, and diff checks pass.
- Acceptance flexibility used: **none**. This closes a repository-controlled result workflow gap;
  no visual threshold, mask, or board rule changed.

## 2026-08-14 — Study Lab SDK reference duplicate-row repair

- Removed a duplicated `stats` entry from the Study Lab SDK reference. The visible reference now
  has one row for the supported stats namespace, and a component regression enforces that shape.
- Focused Study Lab `22/22`, full frontend `819/819`, type-check, and production build pass.
- Acceptance flexibility used: **none**. No visual threshold, mask, product criterion, or
  reference-board rule changed.

## 2026-08-14 — Study histogram current-marker lifecycle

- Fixed the Study Lab histogram lifecycle so changes to the current observation redraw the marker
  in place instead of leaving a stale highlight or recreating the uPlot instance.
- Focused conditional-uPlot lifecycle coverage passes `12/12`; full frontend `819/819`,
  type-check/build, uPlot contract, visual policy, and diff checks pass. No acceptance flexibility.

## 2026-08-14 — Historical 90/90 current-versus-history distributions

- The Historical 90/90 Study Lab factory now emits typed price and volume participation histograms
  with the latest aligned observation supplied as the highlighted current value, in addition to
  aligned history series, qualification occurrences, detail rows, and exclusions.
- Authenticated `F8p-90-90-history` verifies both histogram outputs from the canonical declared
  universe. Frontend `818/818`, type-check/build, uPlot contract, visual-policy, and diff checks
  remain green.
- Acceptance flexibility used: **none**. No visual threshold, mask, product criterion, or
  reference-board rule changed; `REF-STUDY-LAB-V25` remains open.

## 2026-08-14 — Study Lab occurrence-to-chart timestamp linking

- Dated Study Lab occurrences now publish through the existing symbol/timeframe link bus into
  linked uPlot chart and ratio surfaces. Selecting a qualifying 90/90 occurrence moves the linked
  chart cursor to the nearest canonical bar without recreating the chart or issuing a new data
  request; the applied timestamp is exposed as deterministic host state for accessibility and
  acceptance verification.
- Authenticated `F8p-90-90-history` clicks a real occurrence and verifies the exact linked timestamp;
  focused ratio lifecycle coverage also verifies timestamp consume/clear and no cursor echo.
- Acceptance flexibility used: **none**. No visual threshold, mask, product criterion, or
  reference-board rule changed. `REF-STUDY-LAB-V25` remains the open visual-reference gap.

## 2026-08-14 — Historical 90/90 breadth participation and occurrences

- Added a unified-Python Study Lab factory starter for historical 90/90 breadth: aligned price-
  advancing and volume-advancing percentage series, current qualification, sample/coverage
  metrics, detail/exclusion tables, and linked qualification occurrences. The isolated runner
  derives a missing aggregate axis/symbol only from declared instrument data and records explicit
  timestamp/data exclusions.
- Focused runner/factory coverage passes `88/88`; authenticated `F8p-90-90-history` passes `1/1`;
  adjacent Study Lab/Python/Results browser coverage passes `11/11`; frontend Vitest passes
  `818/818`; backend unit/integration passes `1153/1153` and `303/303`; type-check/build, Ruff,
  uPlot, visual policy, and diff checks pass.
- The first browser run failed on the real missing aggregate-axis contract and the correction was
  rebuilt and rerun successfully. Acceptance flexibility used: **none**. `REF-STUDY-LAB-V25`
  remains the tracked original-surface visual gap; no threshold, mask, product, or acceptance
  rule changed.

## 2026-08-14 — Current-history distribution excludes current observation

- Corrected the factory Study Lab source to compare the latest return against prior returns only.
  The sample-size metric and histogram now describe historical observations, while the current
  return is passed explicitly and remains highlighted.
- Focused source-contract coverage passes `1/1`; Current versus history browser acceptance passes
  `1/1`; adjacent Study Lab/Python/Results browser coverage passes `13/13`; frontend `818/818`,
  type-check/build, uPlot contract, and visual policy remain green.
- Acceptance flexibility used: **none**. `REF-STUDY-LAB-V25` remains an explicitly tracked visual
  reference gap; no threshold, mask, product criterion, or functional acceptance rule changed.

## 2026-08-14 — Current-history Study Lab browser acceptance

- Added a real authenticated browser path for the Current versus history factory study. The flow
  selects the factory source, validates it, runs it against canonical SPY data, and asserts the
  historical sample-size metric, uPlot histogram, comparison table, and clean browser diagnostics.
- The first run exposed and corrected a stale branch frontend container rather than an application
  defect. After force-recreating the container from the current image, the focused flow passed
  `1/1` and the adjacent Study Lab/Python/results slice passed `13/13`.
- Acceptance flexibility used: **REF-STUDY-LAB-V25 original-surface interim baseline/product
  contract**. The board has no authoritative Study Lab capture; no visual threshold, mask, product
  criterion, or functional acceptance rule changed. The authoritative Study Lab visual gap remains
  open and is tracked separately.

## 2026-08-14 — DFTT official route re-probe

- A bounded read-only request to the official Donoghue Forlines Tactical 30 ETF product page
  (`https://etfs.donoghueforlines.com/etfs/tactical-30-etf/`) returned Cloudflare HTTP `403`
  at `2026-08-14T09:38Z`; no executable page-declared holdings CSV was available to the backend.
- The existing adapter remains policy-correct: it verifies the product page, follows only its
  declared fund-scoped route when reachable, and uses SEC reconstruction only when identifiers
  permit it. DFTT remains explicitly issuer-access-limited rather than falsely promoted.
- Acceptance flexibility used: **none**. This is an external access gap and does not relax the
  workstation or free-source acceptance contract.

## 2026-08-14 — Canonical authenticated matrix after backend/provider and Docker maintenance

- The rebuilt branch stack remained healthy after the Alerian native route and scoped Docker
  cleanup. The complete authenticated `flows.spec.ts` matrix passed `140/140` in `7.0m` with one
  serial Chromium worker.
- This run covers the real workstation shell, charts/templates/drawings, Golden Layout workspaces
  and pop-outs, link groups/timeframes/crosshairs/gestures, keyboard traversal, top-down SPY/RSP →
  sector → industry/proxy → constituent drill-down and ratios, Python/Study Lab/Results,
  EasyScan/Gauges, alerts/notes, freshness/errors/recovery, legacy compatibility, and 125% browser
  containment. Frontend `817/817`, type-check/build, backend units `1134/1134`, and provider
  live-route evidence remain green.
- Acceptance flexibility used: **scoped Docker build-cache cleanup** and the already documented
  **board-guided/controlled-fixture track** for represented visual states. No visual threshold,
  mask, product, provider, uPlot, or security criterion changed. Exact/unrepresented V25 visuals,
  broader provider/historical truth, native-monitor, longer endurance, and final-audit gaps remain.

## 2026-08-14 — Alerian live-provider coverage

- Added Alerian to the live-backed provider registry and the opt-in concrete route matrix for
  ENFR. The non-network provider contracts pass `2/2`; the official ALPS ENFR live route passes
  `1/1`; the full backend unit gate passes `1134/1134`; Ruff and diff checks pass. Test commit:
  `a03e1cdf`.
- Acceptance flexibility used: **none**. This is maintainability evidence for the native AMLP/ENFR
  route, not a claim that all Alerian products or historical snapshots are covered. Those broader
  provider and historical gaps remain open.

## 2026-08-14 — Native Alerian holdings for ETF constituent drill-down

- Promoted Alerian from audited fallback-only recognition to a native issuer route for AMLP and
  ENFR. Canonical route metadata now identifies the issuer and adapter explicitly, allowing the
  top-down sector/industry/constituent workflow to load these ETFs without an ETF.com table.
- The adapter uses the ALPS product-page-owned public HubSpot proxy for the issuer Marketing API;
  it does not use the credentialed direct API. Payloads are validated for requested fund identity,
  consistent as-of date, symbol/name/identifier fields, cash rows, and industry metadata before
  canonical normalization. The direct route was observed as unauthorized while the public proxy
  returned complete JSON holdings for both AMLP and ENFR.
- Focused Alerian coverage passes `3/3`; the complete ETF adapter unit suite passes `489/489`;
  Ruff, Python compilation, and diff checks pass. Implementation commit: `d9124be6`.
- Acceptance flexibility used: **none**. This closes a repository-controlled constituent-source
  gap for two verified products. Broader issuer coverage, historical holdings snapshots,
  provider-entitlement breadth, exact/unrepresented V25 visual states, native-monitor, endurance,
  and final-audit gaps remain open.

## 2026-08-14 — Visual fixture preflight runs once per worker

- The board-guided visual suite now validates the requested seeded backend mode once in a
  worker-level `beforeAll` using a temporary browser context. It no longer repeats the same
  `e2e_seed_market_data` mismatch 104 times when a caller points it at an unseeded stack.
- The focused negative regression produced one setup failure against the known unseeded stack;
  the authoritative isolated seeded stack advertised both fixture flags as `true` and the full
  four-environment board matrix passed `104/104` in `5.3m`.
- Frontend Vitest, type-check, production build, and `git diff --check` pass. Implementation
  commit: `f7720659`.
- Acceptance flexibility used: **board-guided visual authority plus controlled deterministic
  seeded market data** for represented states. The exact-build/permission and unrepresented
  `REF-STATE-VARIANTS`, `REF-STUDY-LAB-V25`, provider/entitlement, historical/GICS,
  native-monitor, endurance, and final-audit gaps remain open.

## 2026-08-14 — Blocked issuer native-boundary regression

- Added a generalized regression over the complete current `issuer_access_blocked` set. Every
  blocked identity must remain `live_tested_default_route=False`, retain an explicit adapter, and
  remain eligible for the audited fallback path. The contract deliberately allows provider-specific
  retained classes such as `AnfieldHoldingsAdapter`; class naming is not used as a false proxy for
  native support.
- The focused blocked-provider slice passes `5/5`; the complete ETF adapter unit suite passes
  `486/486`; the broader backend unit gate passes `1131/1131`; Ruff and diff checks pass.
  Implementation commit: `00c751e3`.
- Bounded external evidence remains explicit: Guinness Atkinson official holdings PDFs returned
  HTTP 403, Q3's official QVOY CSV route returned HTTP 503, and WisdomTree DXJ backend-compatible
  access returned HTTP 403. No provider was promoted and no acceptance flexibility was used.

## 2026-08-14 — Westwood issuer route audit and fallback guard

- Re-tested the official Westwood product surfaces for MDST and WEEI after search-indexed
  results exposed complete-looking holdings tables and a `Download CSV` control. Direct
  backend-equivalent requests to the official product pages and WordPress/API variants returned
  HTTP 403 HTML responses, so no complete executable issuer artifact was available for promotion.
- Third-party tables, search-cache text, and SEC/other-provider data remain discovery or fallback
  evidence; they do not satisfy the native issuer-route contract. Westwood therefore remains
  `issuer_access_blocked` with SEC fallback eligibility and an explicit periodic re-test action.
- Added `test_westwood_remains_explicitly_audited_fallback_only_after_official_route_403`; focused
  fallback checks pass `5/5`, the complete ETF adapter unit suite passes `485/485`, Ruff and diff
  checks pass. Implementation commit: `23ce2ca1`.
- Acceptance flexibility used: none. This is an external access gap, not a product blocker; no
  provider, provenance, membership, or acceptance rule was relaxed.

## 2026-08-14 — Top-down ratio acceptance-oracle isolation

- The authenticated top-down ratio context-menu flow now resets the immutable factory workspace
  before mutating the shared ratio window. This prevents a preceding comparison/template test from
  leaving a persisted custom ratio that masks the `Open ratio vs active` behavior.
- The deep top-down journey now requires the explicit stock legs `NVDA/XLK` and `NVDA/SPY`; an
  industry-proxy-only ratio no longer satisfies the stock/sector acceptance contract.
- The first broader seeded run exposed the order-dependent failure at F8e.2a. After the fix,
  focused ratio/unit coverage passed `14/14`, the focused browser flow passed `1/1`, the broader
  seeded F8d/F8e slice passed `9/9` executed with two explicit canonical-only skips, frontend
  Vitest passed `817/817`, and type-check/diff checks passed.
- Acceptance flexibility used: controlled seeded/board-guided browser evidence for this existing
  interim track; no visual threshold, mask, provider rule, or product criterion changed. The
  remaining exact/unrepresented V25, provider/entitlement, historical/GICS, native-monitor,
  endurance, Docker, and final-audit gaps remain explicit.

## 2026-08-14 — Preserve settings during loading-time chart rebuilds

- The chart host now remains mounted while symbol/timeframe/alternative-bar history is loading,
  preserving the Version 25-style settings dialog and transform controls through the request.
  `UPlotChart` destroys its numerical instance and all drawing/sub-pane canvases during loading,
  then recreates them after valid bars arrive, so no stale numerical renderer remains underneath
  the explicit loading state.
- The sequence that exposed the defect (F9c, F9c-transform, F9c-template-transform, and
  F8r-breadth-narrow) passes `4/4`; focused board loading/Study visuals pass `8/8`; the full
  seeded authenticated flow matrix passes `138/140` executed with the two documented
  canonical-only skips; frontend Vitest `806/806`, type-check, 476-module build, and diff-check
  pass. Implementation commit: `0ffab190`.
- Acceptance flexibility used: **none**. This is a repository-controlled lifecycle repair. Exact
  or unrepresented V25 visual states, provider/entitlement breadth, historical/GICS truth,
  native-monitor, endurance, Docker, and final-audit gaps remain open.

## 2026-08-14 — Chart loading lifecycle and deterministic Study Lab visual state

- The primary chart host now detaches its uPlot canvas while history is loading. The loading
  surface therefore cannot leave a stale numerical renderer underneath it; the existing chart
  instance is recreated only after valid history is available.
- The Study Lab structured-result board capture now waits for the seeded shell to reach its stable
  ready state and stubs the adjacent persisted-runs list to its explicit empty state. This removes
  shared-database and first-refresh timing drift without masking application pixels or changing a
  visual threshold.
- The four reviewed board-guided baselines (1920×1080 and 2560×1440 at 100% and 125% display
  scale) were regenerated from that deterministic fixture and pass unchanged on a no-update
  rerun. Focused chart-loading and structured-result coverage passes `8/8`; the complete board
  matrix passes `104/104` in `5.2m`; F8i error/loading browser coverage passes `3/3`; frontend
  Vitest passes `806/806`; type-check, 476-module build, and `git diff --check` pass.
  Implementation/test commit: `5eacf42f`.
- Acceptance flexibility used: the Study Lab visual is represented-state evidence from the
  composite V25 reference board and a controlled seeded fixture, not an approved exact-build
  capture. The exact V25 structured-result reference, provider/entitlement breadth,
  historical/GICS truth, native-monitor, endurance, Docker, and final-audit gaps remain open and
  are not silently closed by this baseline update.

## 2026-08-14 — Browser acceptance hardening and full seeded revalidation

- The corrected full seeded `flows.spec.ts` rerun passes `138/140` executed tests in `6.9m`
  with one serialized Chromium worker; the two skips are explicit canonical-only
  `F8e.live-membership` and `F8e.live-sector-drilldown` cases gated by
  `E2E_SEED_MARKET_DATA=true`. They remain documented skips rather than hidden failures. This
  closes the prior browser checkpoint; no failure, visual threshold, mask, provenance rule, or
  product criterion was suppressed.
- Full frontend Vitest remains `806/806`, type-check, the `476`-module production build, and
  `git diff --check` remain green. Exact/unrepresented V25, provider/entitlement, historical/GICS,
  native-monitor, endurance, Docker, and final-audit gaps remain open.

- Hardened the authenticated browser matrix around three false negatives: the uPlot gesture test
  now zooms inward before history panning so persisted full-history views are deterministic; the
  transform-reset request observer is installed before the blur-triggered field change; and the
  template restoration test accepts the intentional short-lived OHLCV dedupe cache while the
  dedicated transform test retains exact request-parameter coverage.
- Seeded drill-down provenance now accepts either a fully labelled controlled fixture or a fully
  canonical free-source snapshot already present in the local database; mixed or unknown provider
  provenance still fails. This is an explicitly recorded seeded-data flexibility, not a visual,
  provider-entitlement, or product capability waiver.
- Full seeded `flows.spec.ts` reached `137/140` before the final template-oracle correction;
  focused transform/template coverage then passed `2/2`; the full frontend suite passes `806/806`,
  type-check passes, and the production build contains `476` modules. The corrected full matrix
  remains to be rerun as a later acceptance checkpoint.
- Implementation/test commit: `51e042fb`. No V25 visual thresholds, masks, uPlot renderer rules,
  or board authority changed. Exact/unrepresented V25, provider/entitlement, historical/GICS,
  native-monitor, endurance, Docker, and final-audit gaps remain explicit.

## 2026-08-14 — Comparison timestamp alignment

- Top-down normalized comparisons now align bars through normalized epoch-second timestamp keys,
  accepting ISO, epoch-second, and epoch-millisecond representations while rejecting malformed
  timestamps. Comparison bars retain their timestamp text instead of being coerced into an
  incompatible numeric representation.
- Focused comparison coverage passes `4/4`; full frontend Vitest passes `806/806`; type-check,
  the 476-module production build, uPlot contract (`45` files), and `git diff --check` pass.
  Implementation: `0333f11b`.
- No acceptance flexibility, visual threshold, mask, provider substitution, or renderer rule was
  used. Exact/unrepresented V25, provider/entitlement, historical/GICS, native-monitor,
  endurance, Docker, and final-audit gaps remain explicit.

## 2026-08-14 — Unified numeric plot-series validation

- Python research plot artifacts and retained EasyScan plot points now share one validation
  boundary before reaching chart rendering. The boundary requires aligned parseable timestamps,
  preserves finite values and explicit null gaps, converts malformed numeric points to gaps, and
  rejects all-missing or malformed series.
- Focused numeric-series coverage passes `3/3`; full frontend Vitest passes `804/804`; type-check,
  the 476-module production build, uPlot contract (`45` files), and `git diff --check` pass.
  Implementation: `c445078b`.
- No acceptance flexibility, visual threshold, mask, provider substitution, or renderer rule was
  used. Exact/unrepresented V25 Study Lab states, provider/entitlement, historical/GICS,
  native-monitor, endurance, Docker, and final-audit gaps remain explicit.

## 2026-08-14 — Canonical chart store rejects malformed OHLC bars

- The shared chart store now validates open, high, low, and close values before publishing bars
  to the primary uPlot data path. Malformed OHLC rows are excluded; malformed optional volume and
  VWAP values become unavailable instead of `NaN`/`Infinity`.
- Focused chart-store coverage passes `37/37`; full frontend Vitest passes `801/801`; type-check,
  the 475-module production build, uPlot contract (`45` files), and `git diff --check` pass.
  Implementation: `b1419b52`.
- No acceptance flexibility, visual threshold, mask, provider substitution, or renderer rule was
  used. Exact/unrepresented V25, provider/entitlement, historical/GICS, native-monitor,
  endurance, Docker, and final-audit gaps remain explicit.

## 2026-08-14 — Study Range rejects malformed timestamps

- Study Lab range output now rejects malformed timestamps before uPlot instead of silently
  replacing them with synthetic array-index x coordinates. Valid range data continues to use
  epoch-second timestamps for the time axis; invalid output retains the explicit unavailable
  state and destroys any stale chart instance.
- Focused conditional-uPlot lifecycle coverage passes `11/11`; full frontend Vitest passes
  `800/800`; `vue-tsc --noEmit`, the 475-module production build, uPlot contract (`45` files),
  and `git diff --check` pass. Implementation: `3f03b33a`.
- No acceptance flexibility, visual threshold, mask, provider substitution, or renderer rule was
  used. Exact/unrepresented V25 Study Lab states, provider/entitlement, historical/GICS,
  native-monitor, endurance, Docker, and final-audit gaps remain explicit.

## 2026-08-14 — Conditional numerical-data validation

- Study Series and Breadth History now reject malformed timestamps and non-finite numerical payloads
  before uPlot, expose the explicit unavailable state, and destroy any stale chart instance.
- Focused family `10/10`, full frontend Vitest `793/793`, type-check, 475-module build, uPlot
  contract (`45` files), diff-check, and authenticated F8o `1/1` pass. No visual baseline,
  threshold, mask, provider, or acceptance rule changed; flexibility used: none.
- This closes a repository-controlled numerical data-integrity gap; exact/unrepresented Study Lab,
  provider/entitlement, historical/GICS, native-monitor, endurance, Docker, and final-audit gaps
  remain open.

## 2026-08-14 — Conditional numerical-state announcements

- Empty/invalid conditional numerical surfaces now announce their status with `role=status`,
  `aria-live=polite`, and atomic updates across Study Series, Histogram, Range, Bars, Scatter, and
  Breadth History.
- Family coverage `12/12`, full frontend Vitest `793/793`, type-check, 475-module build, uPlot
  contract (`45` files), diff-check, and authenticated F8o `1/1` pass. No visual baseline, threshold,
  mask, provider, or acceptance rule changed; flexibility used: none.
- This closes a repository-controlled accessibility contract gap; exact/unrepresented Study Lab,
  provider/entitlement, historical/GICS, native-monitor, endurance, Docker, and final-audit gaps
  remain open.

## 2026-08-14 — Conditional Study/Breadth uPlot family lifecycle

- The conditional numerical renderer family now shares the same lifecycle contract: Study Series,
  Histogram, Range, Bars, Breadth History, and Scatter wait for their host, release charts when
  output becomes invalid/empty, and recreate safely on recovery. uPlot remains the sole numerical
  renderer.
- Family unit coverage `12/12`, full frontend Vitest `793/793`, type-check, 475-module build, uPlot
  contract (`45` files), diff-check, and authenticated F8o `1/1` pass. No visual baseline, threshold,
  mask, provider, or acceptance rule changed; flexibility used: none.
- This closes a shared repository-controlled renderer lifecycle defect. Exact/unrepresented Study
  Lab visuals, provider/entitlement, historical/GICS, native-monitor, endurance, Docker, and final-
  audit gaps remain open.

## 2026-08-14 — Study Scatter conditional uPlot lifecycle

- Study Lab scatter output now hydrates the conditional uPlot host before creating the chart,
  destroys orphaned charts on invalid/empty output, and recreates a fresh chart when valid output
  returns. This preserves uPlot-only numeric rendering and prevents removed canvases from leaking.
- Focused unit `2/2`, full frontend Vitest `783/783`, type-check, 475-module build, uPlot contract
  (`45` files), diff-check, and authenticated structured-study browser `F8o` `1/1` pass. No visual
  baseline, threshold, mask, provider, or acceptance rule changed; flexibility used: none.
- This closes a repository-controlled Study Lab lifecycle defect. Exact/unrepresented Study Lab
  visuals, provider/entitlement, historical/GICS, native-monitor, endurance, Docker, and final-audit
  gaps remain open.

## 2026-08-14 — Relative Rotation async plot-host lifecycle

- The Relative Rotation uPlot host is now observed after asynchronous data hydration and when the
  host changes, so live dock resizing calls the existing chart's size path rather than leaving the
  chart unobserved. Cleanup disconnects the observer on removal.
- Focused unit `6/6`, full frontend Vitest `781/781`, type-check, 475-module build, uPlot contract
  (`45` files), diff-check, and authenticated F8s browser acceptance `1/1` pass. No visual baseline,
  threshold, mask, provider, or uPlot-renderer rule changed. Acceptance flexibility used: none.
- This closes a repository-controlled interaction/performance defect; exact/unrepresented V25,
  provider/entitlement, historical/GICS, native-monitor, endurance, Docker, and final-audit gaps
  remain open.

## 2026-08-14 — Docker storage maintenance

- Docker crossed the maintenance threshold at `24.06GB`; scoped builder/image cleanup reclaimed
  `19.08GB` while all six branch services remained running and backend/Postgres/Redis healthy.
- The requested global volume-inclusive prune was safety-rejected for its cross-project deletion
  risk. This is operational evidence only; no product or acceptance criterion changed.

## 2026-08-14 — Study Lab validation live-region polarity

- Invalid Study Lab validation now announces assertively while valid validation announces politely;
  both remain atomic and preserve the existing editor/recovery flow.
- Focused Study Lab units `22/22`, type-check, diff-check, and rebuilt authenticated F8t browser
  acceptance `1/1` in `3.3s` pass. The initial browser result was stale-container setup evidence;
  rebuild/force-recreate produced the authoritative pass.
- No visual threshold, mask, provider, uPlot, or acceptance rule changed. Exact V25 validation-state
  styling remains `REF-STATE-VARIANTS`; acceptance flexibility used: none.

## 2026-08-14 — Shared workstation live-region semantics

- Dynamic status and error surfaces across watchlists, charts, EasyScan, alerts, gauges, coverage,
  rotation, Research Results, Study Lab, recovery, and constituent provenance now declare explicit
  live polarity and atomic updates.
- Focused component coverage `156/156`, full frontend Vitest `781/781`, type-check, 475-module
  build, diff-check, and elevated authenticated browser coverage `10/10` in `27.8s` pass.
- No visual threshold, mask, provider, uPlot, or acceptance rule changed. Exact V25 state styling
  remains the explicit `REF-STATE-VARIANTS` gap; no acceptance flexibility was used.

## 2026-08-14 — Alert and Market Gauge empty-state semantics

- Empty alert and Market Gauge prompts now expose polite, atomic status live regions, completing the
  semantic pairing with their loading and error states without changing visible layout or data flow.
- Focused components `17/17`, full frontend Vitest `781/781`, type-check, 475-module build, and
  diff-check pass. Rebuilt authenticated F8r/F8w browser coverage passes `3/3` in `12.1s`.
- The initial browser attempt failed before page creation at the known macOS Chromium Mach-port
  permission boundary; the elevated rerun is authoritative. No acceptance flexibility or visual
  threshold/mask/provider/uPlot rule changed. Exact V25 status styling remains `REF-STATE-VARIANTS`.

## 2026-08-14 — Chart loading/error live-region semantics

- Chart loading, provider-error, and no-symbol states now announce their state through explicit
  status/alert semantics while retaining the existing visible tool-state presentation and uPlot
  chart path.
- Focused F8i browser acceptance passes `3/3` in `8.7s` after a rebuilt, force-recreated branch
  frontend. The first attempt was discarded as stale-container setup evidence because the old
  image did not contain the new attributes; the authoritative rerun passed.
- Full frontend Vitest `781/781`, type-check, 475-module build, and diff-check pass. No visual
  threshold, mask, provider, or acceptance rule changed. Exact V25 loading/error appearance is
  still an explicit `REF-STATE-VARIANTS` reference gap.

## 2026-08-14 — Browser performance and bounded endurance evidence

- The real-browser uPlot guard passes 100,000 points through repeated zoom/pan without replacing
  the chart, and both workstation lifecycle/churn guards pass. Combined result: `3/3` in `19.5s`
  with one Chromium worker.
- This is bounded repository evidence for the performance invariants, not a claim of indefinite
  endurance or physical multi-monitor validation. No acceptance flexibility, visual threshold,
  mask, provider, or uPlot rule changed.

## 2026-08-14 — Watchlist freshness-state semantics

- Dense watchlist cells now classify canonical warnings as stale, delayed, partial, fetching,
  coverage-limited, unavailable, or generic warning, with explicit state classes/data attributes
  and state-specific colors. Stacked cells use the same contract.
- Titles retain the rendered value plus warning reason. This is a behavior/data-state correction
  supporting the TC2000-style grid; no provider-specific symbol or freshness claim was added.
- Focused coverage `65/65`, full frontend Vitest `781/781`, type-check, 475-module build, and
  diff-check pass. No acceptance flexibility or visual threshold/mask change was used; exact V25
  pointer-state references and the other documented final gaps remain open.

## 2026-08-14 — Backend gate semantics and cleanup evidence

- Corrected the integration-only Make target to report its `43.93%` coverage without falsely
  failing against the repository-wide threshold. The combined `make test-backend-coverage` gate
  remains unchanged and passes `1424` tests at `80.15%` coverage.
- `make test-backend` passes `1121` unit and `303` integration tests; uPlot contract and visual
  acceptance-policy validators also pass. This is supporting acceptance infrastructure, not a
  change to product parity or visual thresholds.
- Scoped `docker builder prune -af` reclaimed `4.2GB` while the branch stack remained healthy. The
  broader cross-stack prune was safety-rejected and remains an explicit operational gap; no
  acceptance criterion was relaxed to hide it.

## 2026-08-14 — Post-comparison authenticated matrix

The rebuilt authenticated `frontend/tests/e2e/flows.spec.ts` matrix passes `140/140` in `7.1m`
with one worker after comparison-template persistence was corrected. This includes the full chart,
top-down SPY/RSP/sector/industry/constituent workflow, uPlot interactions, linking/pop-outs,
Python/Study Lab, alerts, legacy, recovery/error, narrow-dock, and 125% browser-scale journeys.
No acceptance flexibility, visual threshold/mask/baseline, provider substitution, or uPlot rule
was changed. The result is scoped regression evidence; exact/unrepresented V25, provider/
entitlement, historical/GICS, native-monitor, endurance, Docker-cleanup, and final-audit gaps remain.

## 2026-08-14 — Chart-template comparison persistence

- Saved chart templates now restore their persisted comparison set rather than retaining the
  active chart comparisons. Active symbol identity remains protected, chips are visible before
  normalized bars finish loading, parent workspace snapshot races are fenced, and opening the
  template menu refreshes its library query.
- Focused unit `9/9`, full frontend Vitest `780/780`, type-check, 475-module build, rebuilt
  authenticated `F9c-template-comparison` browser `1/1`, and diff-check pass. The stale-image and
  menu-oracle failures were corrected under fix-first and rerun; no acceptance flexibility was used.
- This is a scoped workstation correction, not overall-goal completion. Board/unrepresented V25,
  provider/entitlement, historical/GICS, native-monitor, endurance, Docker-cleanup, and final-audit
  gaps remain open in their controlling ledgers.

## 2026-08-13 — Equal-weight industry ranking surface

The Industries tool now has a canonical batch snapshot for top-down ranking rather than exposing
only holdings metadata. `GET /analysis/etf/{symbol}/industries/snapshot` derives each classified
industry from the ETF's point-in-time disclosed holdings, computes an equal-weight normalized
series without forward-filling gaps, and returns the seven required performance periods, SMA/RSI/
52-week technical cells, `/ Sector` and `/ SPY` ratios, coverage, exclusions, freshness, provenance,
and a stable membership digest. Aggregate warnings use no fabricated instrument identity.

The workstation renders the dense industry header and values, preserves classification/proxy
lineage and row selection, and keeps the wide surface horizontally scrollable. Direct helper and
API regressions pass `18/18` and `1/1`; frontend Vitest passes `773/773`; type-check/build, Ruff,
compileall, diff-check, and rebuilt authenticated F8e.1/F8e.1a pass `2/2`. No visual baseline,
mask, threshold, or product boundary changed. Exact/unrepresented V25 states, provider and
entitlement breadth, historical/GICS truth, native monitor behavior, longer endurance, and final
audit gaps remain open.

## 2026-08-13 — Private unified-Python attribute safety evidence

The API and isolated research-runner validators now reject private numerical-wrapper attributes at
the shared pre-execution boundary. This supports the workstation's Python/Study Lab surfaces and
prevents valid-then-runtime-failure code versions. Focused security/research tests pass `112/112`,
code API integration `21/21`, backend units `1116/1116`, rebuilt runner services are healthy, and
Study Lab browser validation/recovery passes `2/2`. No visual baseline, threshold, mask, product,
or sandbox acceptance criterion changed; existing V25 visual, data, hardware, endurance, and final
audit gaps remain in their ledgers.

## 2026-08-13 — Unified Python safety-contract evidence

The API code-version validator and isolated research runner now reject the same sensitive
ndarray/numerical-wrapper attributes before execution. This is supporting backend work for the
TC2000-style Python/Study Lab surfaces, not a visual change. Code integration passes `21/21`,
sandbox/research units `119/119`, backend units `1114/1114`, frontend Vitest `770/770`, rebuilt
authenticated Study Lab validation/recovery flows `2/2`, and the rebuilt services are healthy. No
visual baseline, threshold, mask, or product criterion changed;
the remaining visual-reference, historical/provider, hardware, endurance, and final-audit gaps
remain in their existing ledgers.

## 2026-08-13 — Constituent coverage disclosure evidence

The ETF constituent snapshot repair is validated against the existing workstation contract:
eligible rows remain visible, disclosed non-equity/unresolved rows are surfaced through the
provenance footer, and the coverage denominator is honest. Docker-backed integration is `2/2`,
the full backend unit suite is `1106/1106`, and the authorized authenticated top-down browser
slice is `7/7`. No visual baseline, threshold, mask, or reference-board authority changed. This
supports the TC2000-style top-down workflow but does not close the exact/unrepresented V25 states
tracked in the reference-board ledger.

## 2026-08-13 — Final-image adapter parity check

- The final backend/worker image rebuild is healthy. Workspace integration passes `26/26`, and
  the representative frontend-directory browser matrix passes `7/7` for top-down drilldown,
  sector/industry surfaces, Study Lab/Python, consecutive-close study, watchlist states, and
  plot transfer.
- The initial root-directory browser invocation was setup-only (no Playwright project config) and
  was not counted as product evidence. No acceptance flexibility was used.

## 2026-08-13 — IronHorse provider fallback repair

- The official IronHorse/Conductor holdings page can return an empty 200 CSV response. The
  adapter now classifies that as a native-route failure and uses SEC EDGAR reconstruction when a
  CIK is available, preserving route-failure and fallback provenance.
- Focused adapter tests pass `3/3`; backend unit suite passes `1106/1106`; compileall and Ruff
  pass. The opt-in live matrix remains explicitly classified as `368 passed, 1 skipped, 6 failed`
  because Vident/MM VAM, JPMorgan, Donoghue Forlines, Lazard, and other current issuer routes
  remain externally unavailable or changed.
- Acceptance flexibility used: **None**. This closes a repository-controlled fallback defect but
  does not claim external provider availability or close provider breadth/history gaps.

## 2026-08-13 — Rebuilt-stack top-down validation

- Rebuilt backend/worker images after the provider fallback repair. Workspace integration passes
  `26/26`; focused current-source browser acceptance passes `21/21` for SPY/RSP, sector/industry/
  constituent drilldown, ratios, Study Lab, watchlists, breadth, rotation, and reusable plots/
  conditions/gauges.
- No visual threshold, mask, board authority, provider entitlement, or product boundary changed.
  Remaining external-source and unrepresented visual states stay explicit gaps.

## 2026-08-13 — Current-source acceptance revalidation

- Rebuilt the branch-scoped stack with both E2E seed flags disabled; all services reached their
  expected running/healthy state.
- `ChartPage.goto()` now waits for `.workspace-layout-host` rather than `networkidle`, because
  intentional polling and the alert WebSocket remain active. Full authenticated Chromium
  acceptance passes `136/136` with no product criterion relaxed.
- The matrix covers the supported V25 shell, dock/link/pop-out mechanics, chart/uPlot, SPY/RSP and
  sector/industry/constituent drilldown, Study Lab/Python, watchlists, alerts, notes, gauges,
  recovery states, and legacy compatibility. Post-run service-log inspection found no unexpected
  backend/worker/research-runner failures.
- Board-guided visual and controlled seeded evidence remain limited to represented states; all
  exact/unrepresented visual states continue as explicit gaps.

## 2026-08-13 — Supporting provider and build evidence

- Provider registry/live-route contract checks pass `2/2` for all 496 registered adapters and the
  352 native/live-backed route-test dispositions. Network-bearing issuer probes are still opt-in;
  the parity record makes no unsupported live-freshness claim.
- Frontend Vitest `770/770`, type-check, and the 471-module production build pass. These gates do
  not close the documented provider breadth, historical truth, or visual-reference gaps.

## 2026-08-13 — ETF enrichment cannot promote sector metadata to industry

Provider enrichment, snapshot re-ingestion, and reconciliation now require an actual industry
field for industry completeness. Sector-only details remain sector-only, retain their existing
provenance, and continue through the bounded enrichment path instead of being silently promoted.
ETF-resolution units pass `16/16`, taxonomy units `9/9`, and Docker-backed workspace integration
`26/26`; Ruff and compileall pass. Acceptance flexibility used: **None**. This repairs a shared
data-integrity path; official GICS/historical, provider, exact/unrepresented V25, hardware,
endurance, and final-audit gaps remain open.

## 2026-08-13 — Sector-only classification is not industry membership

Industry composition and constituent reads now require an actual industry classification. Sector-only
metadata, in both current canonical profiles and historical snapshots, remains unclassified rather
than being promoted into an industry row. Taxonomy units pass `9/9`, workspace integration `26/26`
with `--no-cov`, frontend Vitest `770/770`, type-check/build, Ruff, compileall, and diff checks pass.
Acceptance flexibility used: **None**. This closes a repository-controlled taxonomy defect; official
GICS/historical, provider, exact/unrepresented V25, hardware, endurance, and final-audit gaps remain.

## 2026-08-13 — Resolved-identity consistency guard

ETF holdings whose `is_resolved` flag contradicts a missing canonical constituent ID are now
classified as `unresolved_holding`. They are excluded from coverage and disclosed consistently,
preventing composition and constituent views from disagreeing about eligible membership.
Workspace integration passes `26/26` with `--no-cov`, the seeded authenticated F8e.1 drill-down
passes `1/1`, and Ruff/compileall pass. Acceptance flexibility used: **None**; broader historical,
GICS, provider, visual-reference, hardware, endurance, and final-audit gaps remain open.

## 2026-08-13 — Constituent disclosure browser and visual revalidation

After the constituent exclusion footer and partial-coverage correction, the authenticated deep
top-down drill-down (`F8e.1`) passes `1/1` against a rebuilt deterministic fixture stack. The full
board-guided visual matrix passes `104/104` in `5.2m` across 1920×1080 and 2560×1440 at 100% and
125% display scale. No baseline, mask, threshold, or product criterion changed.

Acceptance flexibility used: **board-guided visual authority plus controlled deterministic seeded
market data**. This is represented-state evidence, not exact pinned-build approval; exact or
unrepresented V25 states, historical/GICS, provider, hardware, endurance, and final-audit gaps
remain open.

## 2026-08-13 — Constituent exclusion disclosure and partial-coverage correction

The constituent drill-down now uses an outer profile join and retains eligible holdings whose
classification is missing, rather than silently dropping them. A mixed ETF snapshot reports
classified eligible rows divided by all eligible rows (`0.5` in the regression), returns only the
classified target-industry row, and carries identical explicit cash/derivative/unresolved/
unclassified exclusion codes through composition and constituent responses. The dense constituent
tool renders those codes in a provenance footer and includes the excluded count in its label.

Focused backend integration passes `26/26` with `--no-cov`; frontend focused tests pass `64/64`,
full Vitest `770/770`, type-check/build, Ruff, compileall, and diff checks pass. Acceptance
flexibility used: **None**. This closes a repository-controlled disclosure/data-contract defect;
official GICS/historical, provider, exact/unrepresented V25, hardware, endurance, and final-audit
gaps remain open.

## 2026-08-13 — Industry classification coverage semantics corrected

`classification_coverage` for industry constituents now means classified eligible rows divided by
all eligible rows. It no longer conflates classification coverage with the selected industry's
membership share. Current/historical source fallback is computed once and reused for returned
systems and rows. Industry API regressions pass `2/2`; backend unit `1103/1103`; frontend focused
`64/64`; type-check/build, Ruff, compileall, and diff checks pass.

Acceptance flexibility used: **None**. No visual or seeded acceptance basis changed; historical/GICS,
provider, exact/unrepresented visual, hardware, endurance, and final-audit gaps remain open.

## 2026-08-13 — Industry constituent lineage is preserved and disclosed

Industry-constituent responses now carry their own composition date, known-at time, source,
classification systems, and coverage. The workstation store retains those fields and the constituent
tool label uses the selected industry snapshot rather than the parent ETF snapshot. Taxonomy/workspace
tests pass `9/9`; backend unit tests pass `1103/1103`; frontend focused coverage `64/64`,
type-check/build, Ruff, compileall, and diff checks pass.

Acceptance flexibility used: **None**. This closes a repository-controlled lineage mismatch, but
does not close historical completeness, official GICS, provider, exact/unrepresented visual,
hardware, endurance, or final-audit gaps.

## 2026-08-13 — Classification-source edge semantics corrected

Provider classifications with a label but no declared namespace now remain source-labelled as
`unknown` and render as `Unknown source`; they are distinct from genuinely `Unclassified` rows.
An orphan duplicate task record was also removed and the ledger verifies `268/268` unique IDs.
Taxonomy/workspace regressions pass `8/8`; frontend type-check/focused coverage, Ruff, compileall,
YAML parsing, and diff checks pass.

Acceptance flexibility used: **None**. No visual baseline, seeded fixture, board authority, or
product criterion changed. Official GICS/historical coverage and remaining V25/provider/hardware/
endurance/final-audit gaps stay explicit.

## 2026-08-13 — Industries tool exposes classification provenance

The dense Industries pane now renders source-labelled classification systems on each industry row,
with an explicit `Unclassified` state, tooltip evidence, aggregate classified coverage, and excluded
row count. Seeded fixtures identify themselves as `controlled_fixture`; they are not presented as
official GICS. Focused seeded top-down drill-down passes `2/2`, the four-environment board-guided
visual matrix passes `104/104` in `5.1m`, frontend Vitest `770/770`, type-check/build, seed/taxonomy
tests `9/9`, Ruff, compileall, and diff checks pass.

Acceptance flexibility used: **controlled deterministic seeded fixture data plus board-guided visual
authority**. This validates the represented UI state and disclosure behavior, but does not close
official GICS-compatible mapping, complete historical coverage, exact/unrepresented V25 states,
provider breadth, hardware, endurance, or final-audit gaps.

## 2026-08-13 — Classification provenance survives canonical profile reconciliation

The profile persistence path now carries `classification_system` from provider metadata snapshots
through reconciliation into sector/industry field provenance. This prevents SEC SIC, provider-native,
and other source-labelled classifications from becoming indistinguishable after a canonical merge.
The persisted snapshot regression and taxonomy/persistence suite pass `17/17`; backend unit tests
pass `1102/1102`; Docker-backed integration tests pass `302/302`; frontend Vitest remains `770/770`;
type-check/build/Ruff/compileall/diff checks pass.

Acceptance flexibility used: **None** for the product repair. The Docker integration rerun required
the permissioned environment after the unprivileged Docker socket was unavailable before setup;
that is retained as execution-environment evidence. This closes a repository-controlled provenance
defect but does not claim official GICS-compatible taxonomy or complete historical classification
coverage; those remain explicit supporting-backend gaps.

## 2026-08-13 — Board-guided four-environment visual matrix

The isolated seeded stack passed the complete board-guided `tc2000_visual.spec.ts` matrix `104/104`
in `5.4m` with one worker across 1920×1080/100%, 1920×1080/125%, 2560×1440/100%, and
2560×1440/125%. The matrix covers shell/layout, factory workspaces, link groups, uPlot charts,
watchlists, ratios, scans/gauges, Python/Study Lab, alerts/notes, pop-outs, failure/freshness
states, overlap assertions, and deterministic screenshot baselines.

Acceptance flexibility used: **board-guided visual authority plus controlled deterministic seeded
fixture data**, as explicitly allowed by `docs/tc2000-acceptance-governance.md`. This validates
represented board states but does not close exact-build/permission review, unrepresented or
ambiguous V25 states, hardware multi-monitor behavior, or other gaps in the reference-board
register.

## 2026-08-13 — Current-source matrix after drag and alert consistency repairs

The rebuilt frontend passes the complete authenticated Chromium `flows.spec.ts` matrix `136/136`
in `7.4m` with one serial worker. F8u's real plot-library drag path passes `5/5`; F11a/F11b/F11c
indicator alert creation passes `3/3`; F8n gesture recovery preserves the uPlot surface. Frontend
Vitest is `770/770`, plot-drag unit coverage is `6/6`, and type-check/build pass. Acceptance
flexibility used: **None**. Exact/unrepresented V25 visual states, historical/GICS, entitlement
breadth, native physical-monitor placement, longer endurance, issuer-route breadth, and final audit
remain open.

## 2026-08-13 — Final authenticated workstation matrix after chart-journey repairs

The complete authenticated Chromium `flows.spec.ts` matrix passes `136/136` in `7.1m` with one
serial worker. F8u's real plot-library drag path is stress-tested `5/5`; F8n gesture recovery and
F9h Python Library activation are synchronized on their actual browser states. These checks cover
the top-down workstation, ratios, charts/uPlot, linking/timeframes, watchlists, Python/Study Lab,
scans/gauges, alerts/notes, pop-outs/recovery, legacy routing, and explicit failure/freshness
states. Acceptance flexibility used: **None**; the DnD retry is still the user-visible drag path.
The matrix does not close exact-build/unrepresented V25 references, historical/GICS data,
provider-entitlement breadth, native physical-monitor behavior, longer endurance, or final audit.

## 2026-08-13 — Local-canonical chart read boundary

The workstation chart path now carries an explicit `local_only` contract through initial,
transformed, historical-pagination, and latest-refresh reads. The backend returns only canonical
cached bars for that mode and never invokes provider hydration; legacy chart callers retain the
provider-hydrating default. Focused backend market-data/router tests pass `13/13`, frontend Vitest
passes `763/763`, and type-check/build/lint/compile/diff checks pass. The rebuilt authenticated
targeted authenticated top-down browser flows pass `5/5`, and the post-run backend log audit shows
only the intended `/ohlcv/local/SPY/D1` read, with no Nasdaq hydration or generic workstation OHLCV
call. Acceptance flexibility used: **None**.

## 2026-08-13 — Current-head audit and stale operational-state reconciliation

The current branch-scoped runtime is healthy on the non-seeded path: `/health` reports both E2E
seed flags false, and backend, frontend, PostgreSQL, Redis, worker, and research-runner services
are running. The complete frontend suite passes `762/762` across `95` files; type-check and the
471-module production build pass. A repository audit of primary menus, unsupported capability
stubs, skipped browser cases, provider runtime chains, manifest coverage partitioning, and the
uPlot renderer guard found no new dead control, implicit yfinance dependency, numerical SVG path,
or unrecorded visual gap.

An older bootstrap entry describing browser validation as `repair-in-progress` is superseded by
the later non-seeded workstation evidence (`42/42`) and the current healthy runtime; the original
502/restart event remains retained as diagnostic history. Acceptance flexibility used: **None**.
This advance did not use board/seeded visual substitution, physical-monitor substitution, or
bounded-stress substitution. Remaining parity and supporting-data gaps stay open and actionable.

## 2026-08-13 — DFTT issuer-route re-probe

The official Donoghue Forlines homepage remains reachable, but the DFTT product page returns
Cloudflare HTTP `403` and alternate official fact-sheet domains return HTTP `503`. The homepage
does not expose an executable complete DFTT holdings artifact. The existing adapter therefore
remains correctly issuer-verifying and provenance-preserving, with conditional SEC reconstruction
only when entitled identifiers are available. Its deterministic parser and transport regressions
pass `2/2` with coverage disabled. DFTT remains an explicit external issuer-access gap; no
non-issuer substitute, fabricated membership, or acceptance relaxation was introduced.

## 2026-08-13 — Authoritative gate and Study Lab revalidation

The authoritative repository gates are green on the current branch: backend unit coverage is
`1099/1099` at `70.08%`, Docker-backed integration is `302/302`, the visual manifest/policy and
uPlot renderer contracts pass unchanged, and the board-guided matrix passes `104/104` across all
four required display environments. The non-seeded core workstation acceptance slice passes
`42/42`, including top-down analysis, ratios, links, pop-outs, keyboard traversal, virtualized
watchlists, Study Lab structured/factory studies, notes, coverage, breadth, rotation, reports,
scans, gauges, library lifecycle, and legacy failure states.

An earlier `39/42` run reported F8g/F8o/F8p failures. Focused reruns passed, followed by a clean
`42/42` slice; this was recorded as transient provisioning/browser-runtime evidence, not hidden
as a product defect and not “fixed” by relaxing assertions. Docker socket and Chromium Mach-port
permissions were setup requirements only. The provider audit also confirms new workstation chains
do not implicitly fall back to yfinance. Existing flexibility remains explicit: the 230-image
visual reference board is the authority for represented states and controlled seeded data is used
for those states. Exact pinned-build approval, unrepresented states, historical/GICS coverage,
provider-entitlement breadth, physical multi-monitor behavior, longer endurance, and final audit
remain open parity gaps.

## 2026-08-13 — Explicit ETF holding exclusions and full acceptance revalidation

ETF top-down APIs now classify cash, derivatives, unresolved rows, and other non-equity
holdings as explicit exclusions. Only eligible equity rows contribute to industry coverage,
proxy matches, and constituents, while exclusion codes remain available for honest UI states.
The regression suite passes `48/48`; frontend Vitest passes `762/762`; type-check, production
build, lint, compile, and diff checks pass; the full authenticated Chromium matrix passes
`134/134`. This is a supporting backend correctness correction, not completion of the workstation.
Historical/GICS coverage, provider-entitlement breadth, exact/unrepresented V25 states,
physical monitor placement, endurance, and final audit remain open. No acceptance threshold,
mask, or product criterion was relaxed in this change.

## 2026-08-13 — Point-in-time classification snapshots

Historical ETF industry/proxy/constituent reads now consult immutable provider profile snapshots
known by the requested cutoff when current flattened metadata is too new or undated. Constituent
enrichment stores those raw observations for reproducibility, and responses retain source-labelled
classification systems. The selected taxonomy/ETF/workspace suite passes `47/47`; the rebuilt live
workstation slice passes `22/22`, including top-down drill-down, ratios, Python/Study Lab, pop-outs,
and keyboard linking. This closes the repository-controlled historical metadata leakage path, but
does not claim official GICS data or complete historical coverage; those and the remaining visual,
provider-entitlement, native-monitor, endurance, and final-audit gaps remain open.

## 2026-08-13 — Historical classification provenance and live workstation slice

Industry composition and drill-down responses now carry source-labelled classification systems
and coverage. An explicit historical `as_of` request excludes current metadata without an
observation/known-at timestamp instead of presenting present-day SEC SIC as historical GICS; the
source system remains visible for excluded rows. Focused taxonomy/workspace coverage is `5/5` and
the rebuilt live workstation slice is `22/22` across top-down benchmark/sector/industry/proxy
drill-down, ratios, Python/Study Lab reuse, pop-outs, and keyboard linking. This is a supporting
data-contract correction, not completion of the workstation: historical point-in-time coverage,
provider-entitlement breadth, exact/unrepresented visual states, native-monitor behavior,
endurance, and final audit remain open.

## 2026-08-13 — Resumable classification maintenance and complete acceptance revalidation

The supporting ETF classification path now has a bounded, opt-in weekly maintenance task. It
skips already-complete profiles, processes only snapshots with missing sector/industry metadata,
caps enrichment per profile, records isolated failures, and is covered by the worker and snapshot
resolution tests (`12/12`). The exact `Go` acceptance selector collision with a `Gold and Silver
Ores` industry row was corrected and verified in isolation (`2/2`).

After rebuilding the live branch stack and restoring normal non-seeded runtime, the canonical
authenticated browser matrix passes `134/134`. The board-guided visual matrix passes `104/104`
across all four required display environments. Flexibility used: **board-guided visual authority
plus controlled seeded data for represented states**. Exact pinned-build approval is not asserted
for every board image, and unrepresented visual states remain tracked gaps alongside official
GICS-compatible historical classification, provider-entitlement breadth, point-in-time truth,
native physical-monitor behavior, endurance, and final-audit work. No product or visual threshold
was relaxed.

## 2026-08-13 — Core live top-down membership and classification repair

The core top-down data path now applies curated issuer route metadata before probing persisted
ETF profiles. SPY/RSP, all 11 Select Sector SPDR ETFs, and the curated industry proxy set use
free issuer routes and persist canonical holdings snapshots with source/provenance. Unresolved
dated refresh requests return structured `409` capability responses rather than 500s.

Resolved constituents with missing classification receive bounded SEC EDGAR SIC-derived metadata
with field-level provenance; this is explicitly an issuer/SIC classification, not an invented GICS
relationship. Existing snapshots are reloaded with eager relationships before reconciliation,
and provider profile caching prevents uncontrolled repeated SEC fan-out. Focused backend
bootstrap/resolution/provider coverage passes `103/103`; the live non-seeded top-down browser
slice passes `8/8`, with adjacent Python/Study Lab/linking/keyboard paths `7/7`.

Residual data gaps remain visible: cash/derivative/unresolved rows and unclassified holdings are
reported as exclusions, SIC labels require later normalization if strict GICS-compatible grouping
is needed, and a scheduled continuation is still required for full point-in-time classification.
No visual criterion, threshold, mask, or reference-board rule was relaxed.

## 2026-08-13 — Virtual watchlist status/control glyph parity

Saved-column-set deletion now uses the shared deterministic CSS glyph, and unavailable watchlist
cells expose warning geometry with the canonical warning code as a title while retaining the
existing `—` value and sorting semantics. Focused VirtualWatchlistTool coverage passes `64/64`;
full frontend Vitest remains `756/756`; type-check and production build pass. This is a repository-
controlled parity correction; board-guided represented-state authority plus controlled seeded data
remains the interim visual acceptance track. Exact-build/unrepresented, provider/live-entitlement,
historical-truth, native-monitor, longer-endurance, and final-audit gaps remain open.
The rebuilt seeded stack's real Columns/Sets interaction passes `1/1`, and the affected board
visual baseline passes `4/4` across the four required display environments with no baseline or mask
change.
The subsequent canonical unseeded matrix reached `133/134`; Study Lab failed-rerun recovery passed
in the full run, while F8e.1a encountered transient gateway 502s. A clean isolated F8e.1a rerun
passed `1/1` in `15.3s`, so no product criterion or visual threshold was relaxed.

## 2026-08-13 — Instrument Report disclosure glyph parity

The description `more`/`less` disclosure now uses deterministic shared chevron geometry instead of
platform-font `▴/▾` characters; labels, keyboard activation, and report semantics are unchanged.
Focused Instrument Info/glyph coverage passes `26/26`; rebuilt F8s-report passes `1/1`; and the
complete board-guided visual matrix passes `104/104` in `5.1m` across all four environments. Two
visual grep invocations matched no tests and are discarded setup evidence. Board-guided represented
state authority plus controlled seeded data remains the interim visual track; exact-build/
unrepresented, provider/live-entitlement, historical-truth, native-monitor, longer-endurance, and
final-audit gaps remain open.

## 2026-08-13 — Indicator Panel membership/preset glyph parity

Indicator Panel watchlist membership, screener membership, preset apply, and preset save actions
now use shared deterministic geometry (`list`, `scan`, `apply`, `edit`) instead of platform-font
symbols. Titles, handlers, and domain semantics are unchanged; drawing-tool domain symbols remain
intentional. Glyph coverage is `26` cases; full frontend Vitest is `756/756`; type-check/build and
diff checks pass; rebuilt drawing/control browser coverage is `5/5`; and the complete board-guided
visual matrix passes `104/104` in `5.1m` across all four environments. Board-guided represented-
state authority plus controlled seeded data remains interim; exact-build/unrepresented,
provider/live-entitlement, historical-truth, native-monitor, longer-endurance, and final-audit
gaps remain open.

## 2026-08-13 — Canonical post-glyph regression and gateway tie-break

The current unseeded full matrix reached `127/134`; seven failures were accompanied by transient
502 gateway/provisioning responses. F8v's backend writes were successful and its isolated rerun
passes `1/1` in `5.6s`; the remaining failed paths plus adjacent alert flows pass `9/9` in `30.4s`
after recovery. The full 127/134 run remains discovery evidence pending one clean complete rerun;
no product criterion, visual threshold, or mask changed.

## 2026-08-13 — Primary chart side-panel deterministic glyph parity

The remaining primary chart side-panel controls now use shared deterministic CSS geometry instead
of platform-font symbols: Indicator/Drawings/Alerts section chevrons, row menus, visibility and
lock states, settings/edit/bell actions, projection toggles, pause/resume/rearm/repeat actions,
deletion, Instrument Info disclosure, Instrument Alerts actions, and condition-group removal. The
warning glyph is pure CSS geometry while semantic labels remain unchanged. Focused coverage passes
`34/34`; type-check/build pass; the freshly rebuilt canonical browser slice passes `10/10`; the
freshly rebuilt seeded board-guided visual matrix passes `104/104` in `5.1m` across all four
required display environments; full Vitest remains `756/756`. Acceptance flexibility used:
board-guided visual authority plus controlled seeded data for represented states. Exact-build/
unrepresented, provider/live-entitlement, historical-truth, native-monitor, longer-endurance,
and final-audit gaps remain open. A pre-rebuild browser slice is superseded setup evidence.
The fresh rebuilt canonical full authenticated matrix then passes `134/134` in `7.3m`.

## 2026-08-13 — Deterministic primary chart/control glyph parity correction

The remaining platform-font symbols in the primary chart/library surfaces were replaced with
the shared deterministic `WorkstationGlyph` CSS geometry: plot visibility, move, duplicate,
copy, promotion, template edit/export/delete, ratio add/remove, chart settings/help/close, and
Relative Rotation warnings. The semantic warning regression was updated to assert the warning
geometry instead of a Unicode glyph. Focused coverage passes `63/63`, affected browser flows pass
`6/6`, type-check/build pass, and the complete board-guided visual matrix passes `104/104` in
`5.0m` across all four required display environments. The first repository-root Playwright
invocation was setup-only and discarded; the captured rerun exits `0`. Full frontend Vitest passes
`756/756`. Acceptance flexibility used: board-guided visual authority plus controlled seeded data
for represented states; exact-build/unrepresented, provider/live-entitlement, historical-truth,
native-monitor, longer-endurance, and final-audit gaps remain open.
The complete non-seeded authenticated workstation matrix then passed `134/134` in `7.3m`.

## 2026-08-13 — Post-busy-state full acceptance revalidation

Frontend Vitest passes `746/746`; the rebuilt seeded board-guided visual matrix passes `104/104`
in `5.1m` across all four required display environments; and the complete canonical authenticated
browser matrix remains `134/134` in `7.2m`. Acceptance flexibility used: board-guided visual
authority plus controlled seeded data for represented states. Exact-build/unrepresented states,
provider/live-entitlement, historical-truth, native-monitor, longer-endurance, and final-audit
gaps remain open.

## 2026-08-13 — Backend gate and runtime/storage audit

The Docker-backed combined backend gate passes `1390/1390` at `79.70%` coverage. Backend, worker,
and research-runner logs contain no tracked application-error, 5xx, duplicate-key, integrity,
fatal, out-of-memory, or sandbox-violation signatures, and the branch services are healthy. Docker
storage is high (`11.57GB` images, `3.01GB` reclaimable cache); host-wide pruning was rejected by
the safety boundary and remains an operational follow-up, not a product acceptance result.

## 2026-08-13 — Personal watchlist busy-state race closed

The post-EasyScan full run exposed a real watchlist state defect: a broadcast-triggered canonical
refresh set the personal tool's `aria-busy` flag after the selected rows were already usable.
The busy contract now distinguishes initial list loading from background reconciliation and active
mutations. The rebuilt focused mutation/combo/error group passes `3/3`; the complete post-fix
canonical matrix passes `134/134` in `7.2m`. The preceding `133/134` run remains discovery
evidence only; no acceptance criterion was relaxed.

## 2026-08-13 — EasyScan activation race closed

The stable canonical browser run exposed a real Add-tool race: EasyScan could remain unopened
when Golden Layout had already mounted a usable active tab while the initial workspace promise
was still settling. The shell readiness guard now waits only when no active tab exists. The
focused related keyboard/editor group passes `10/10` after the rebuilt image, and the complete
post-fix canonical matrix passes `134/134` in `7.2m`. The earlier `133/134` run remains discovery
evidence only; no visual or functional acceptance criterion was relaxed.

## 2026-08-13 — Shared shell/watchlist control geometry correction

The shell and watchlist audit found remaining platform-dependent Unicode controls outside the
shared tool-window header: workspace delete, keyboard-help close, recent-symbol disclosure,
factory reset, and column-editor reorder arrows. These now use reusable original CSS geometry via
`WorkstationGlyph`; semantic labels and behavior are unchanged. Focused component coverage is
`82/82`, focused browser coverage is `15/15`, and the rebuilt seeded board-guided visual matrix is
`104/104` across all four display environments. No visual threshold, mask, baseline, or product
criterion changed. The composite board/seeded fixture track is the accepted interim authority for
represented states; exact/state-variant gaps remain explicit.

The subsequent canonical full-matrix run reached `126/134`: six late tests failed during transient
nginx 502 user-provision/reset responses and the personal-watchlist busy-state assertion was not
reproducible (`F8y` isolated `1/1`). This is retained as discovery evidence pending a stable rerun,
not treated as a visual or functional pass.

## 2026-08-13 — Shared tool-window chrome parity correction

Visual inspection of the composite V25 reference board exposed a repository-controlled mismatch:
the shared window chrome used Unicode stand-ins for drag, menu, maximize, float, and close icons.
Those controls now use deterministic original CSS geometry with semantic labels and component
coverage (`7/7`). The rebuilt canonical and seeded visual images pass the affected runtime cases
(`F8r` `10/10`, deep top-down drilldown `1/1`) and the full board-guided matrix passes `104/104`
across 1920×1080 and 2560×1440 at 100% and 125%. No screenshot baseline, mask, threshold, or
product criterion changed. This uses the accepted board-guided visual authority for represented
states; exact pinned-build and unrepresented-state references remain explicitly open.

The final canonical non-seeded authenticated browser matrix passes `134/134` in `7.1m` after the
correction, including the full workstation, top-down, Python/Study Lab, linking, pop-out, and
recovery acceptance paths.

## 2026-08-13 — Post-repair frontend/performance revalidation

The current source remains green after the chart hydration repair: frontend Vitest is `735/735`
across 94 files, production type/build gates are green, and the bounded performance suite is
`3/3` in `2.6m` (100,000-point uPlot interaction, chart lifecycle recovery, and 100 two-popout
churn rounds). Backend logs contain no tracked runtime-error signatures after the rebuilt browser
and performance runs. The unprivileged Chromium Mach-port failure is discarded setup evidence.
This does not close the documented exact/unrepresented visual, external-provider, historical,
physical-monitor, beyond-bounded-endurance, or final-audit gaps.

## 2026-08-13 — Current-source visual and contract revalidation

The rebuilt seeded board-guided visual matrix passed `104/104` across all four required display
environments after a setup-only isolated-stack port collision. The initial unseeded invocation
failed the fixture-mode guard before any screenshot comparison and is discarded. uPlot contract,
visual policy, Ruff, JSON/YAML, and diff checks pass; thresholds, masks, and baselines were
unchanged. Documented exact/unrepresented visual gaps remain open.

## 2026-08-13 — Chart plot drag hydration race closed

The current-source browser matrix exposed a real F8u lifecycle defect: the chart plot library
could add RSI, then late instrument-indicator hydration could replace the stack and detach the
drag source before it reached a watchlist. The chart store now marks user indicator mutations
dirty and refuses stale hydration replacement. Evidence: store `32/32`, plot-library/pop-out
units `40/40`, repeated F8u browser stress `10/10`, frontend image rebuild, and complete
authenticated matrix `134/134` in 7.2 minutes. The first failing run is retained as discovery
evidence; the rebuilt rerun is authoritative. No visual threshold, mask, baseline, or product
criterion changed. Remaining visual/provider/historical/monitor/endurance/final-audit gaps are
unchanged.

## 2026-08-13 — Nasdaq EOD repair boundary closed

The Nasdaq free EOD adapter previously treated a valid one-session ETF repair as empty because
the public route omits the newest row for narrow lower bounds. The adapter now requests a
three-calendar-day lookback, filters back to the canonical requested interval, and includes both
query bounds in its short-lived cache key. Focused provider/runtime coverage is `30/30`; the
rebuilt container returns the requested 2026-08-12 bar for `SPY`, `XLK`, and `AAPL`; no new
provider-exhaustion or 5xx signatures appear in the post-rebuild log audit. The complete
Docker-reachable backend gate is `1390/1390` at `79.70%` coverage. This is supporting-data
evidence for the top-down workflow, not a change to the workstation's visual or functional
acceptance criteria. Remaining documented external and acceptance gaps are unchanged.

## 2026-08-13 — Security, renderer, endurance, and visual revalidation

- Current-source uPlot/workstation performance passes `3/3`: 100,000-point zoom/pan without
  chart replacement, chart-window/canvas lifecycle recovery, and 100-round two-popout churn.
- The live isolated research runner passes all eight sandbox-denial probes, cgroup/tmpfs and
  concurrent-memory containment, orphan recovery after an isolated restart, and five bounded
  cancellation-versus-success rounds. No runner restart occurred during pressure testing.
- A fresh isolated seeded stack on free alternate ports passes the board-guided visual matrix
  `104/104` across 1920x1080 and 2560x1440 at 100% and 125% display scale.
- Flexibility used: board-guided visual authority plus controlled seeded data for represented
  states; browser pop-out evidence for native-monitor behavior; bounded stress for indefinite
  endurance. These substitutions remain explicit gaps and do not claim exact-build, physical
  multi-monitor, or indefinite-soak completion.

## 2026-08-13 — Full acceptance rerun after conflict-recovery repair

- The workspace revision-conflict path now keeps its user-facing recovery message intact instead
  of collapsing it to a generic HTTP 409 status. The recovery workspace name and local-change
  preservation wording are visible in the workstation footer.
- Evidence: focused `F8j-conflict` `1/1`, focused workspace/popout units `71/71`, full current-source
  authenticated Chromium matrix `134/134`, frontend Vitest `734/734`, TypeScript/build, and
  Docker-backed backend gate `1388/1388` at `79.70%` coverage.
- No visual threshold, mask, baseline, product criterion, or provider acceptance rule changed.
  Exact/unrepresented V25 reference, broader provider/historical truth, native physical-monitor,
  endurance, and final audit gaps remain open.

## 2026-08-13 — Supporting ETF route audit and top-down data boundary

- The supporting holdings layer now passes the complete deterministic adapter suite `475/475`.
  PGIM's current catalogue/PDF route, Tuttle DRMP's current public fund API, Wayfinder CMBO's
  declared daily CSV, and Keating's browser-compatible public-page fallback were repaired and
  covered by focused regressions.
- The complete opt-in live issuer matrix passes `373/375`, with one intentional skip and one
  remaining external failure: Donoghue Forlines DFTT's official product/AJAX route returns an
  access-limited HTTP 503. No non-issuer substitute was claimed; conditional SEC reconstruction
  remains fallback-only and requires entitled identifiers.
- This work supports the workstation's sector/industry/proxy/constituent drill-down and does not
  change the primary UI objective, uPlot renderer, provider-neutral frontend boundary, or visual
  acceptance policy. No threshold, mask, baseline, or functional criterion was relaxed.

## 2026-08-12 — Complete current-source authenticated matrix

- **Evidence:** rebuilt current-source, non-seeded authenticated Chromium `flows.spec.ts` passes
  `134/134` in `7.1m` with one worker. This supersedes the earlier `133/134` run whose sole F9h
  Python Library activation miss was not reproducible in isolation or the adjacent Python slice.
- **Coverage:** all workstation shell/layout/chart/template/drawing/linking/pop-out/keyboard,
  top-down benchmark/sector/industry/proxy/constituent and ratio flows, Python/Study Lab/Results,
  scans/gauges/alerts/notes, freshness/error/recovery, legacy/excluded routes, and performance/
  containment checks.
- **Flexibility:** none added. Existing board-guided represented-state evidence and explicitly
  tracked exact/unrepresented V25, provider/entitlement, historical, native-monitor, endurance,
  and final-audit gaps remain open.

## 2026-08-12 — Shell Escape ownership and workspace/geometry acceptance repairs

- **Shell defect:** Escape was stopped by the focused workspace listbox before the workstation
  global handler could dismiss the menu. Capture-level handling now closes only active shell menus
  and restores the relevant trigger; chart/editor Escape behavior is preserved when no shell menu
  is present.
- **Chart defect:** context-menu targeting now follows the rendered `.u-over` edge rather than a
  fixed wrapper coordinate, remaining valid after template and narrow-layout geometry changes.
- **Workspace test hardening:** CRUD acceptance selects the default workspace and uses a unique
  run-scoped rename/clone name, avoiding durable-account contamination without weakening the real
  create/rename/clone/switch/delete assertions.
- **Evidence:** workstation bindings `22/22`; affected browser slice `10/10`; isolated workspace
  CRUD `1/1`; prior chart sequence `18/18`. Rebuilt current-source browser evidence is authoritative.
- **Flexibility:** none. No visual threshold, mask, baseline, or product criterion changed.

## 2026-08-12 — Chart context-menu sequence geometry repair

- **Fix-first defect:** `F9c3-keyboard` failed only after narrow/bottom-edge chart cases because
  those cases persisted a compact layout and the test's fixed right-click coordinate no longer
  landed in the rendered price-scale gutter.
- **Repair:** the test restores its required desktop viewport and computes the gesture from the
  current `.uplot-wrapper` edge, keeping the context-menu event inside the wrapper. This is an
  acceptance-oracle/environment repair; no product code, threshold, mask, baseline, or criterion
  changed.
- **Evidence:** isolated `F9c3-keyboard` `1/1`; affected chart/shell sequence `17/17`; frontend
  Vitest `733/733`; type-check; and 468-module production build all pass in the permitted browser
  environment.
- **Flexibility:** none. Existing board-guided visual, exact/unrepresented state, provider,
  historical, native-monitor, endurance, and final-audit gaps remain unchanged.

## 2026-08-12 — Typed symbol-search hydration and keyboard-selection repair

- **Implemented:** the active-symbol combobox preserves a newer user draft while late route or
  linked-symbol hydration completes; it no longer closes the search panel or cancels the canonical
  debounced request because an older publication arrived afterward.
- **Fix-first defect:** the browser reproduced a permanently busy search list with no results after
  typing during initial hydration. The watcher now treats an active editor draft as authoritative.
- **Evidence:** sequential typing, `aria-busy` readiness, active-descendant traversal, Enter
  selection, and dismissal pass `F8i-search-keyboard` `1/1`; adjacent shell/history/workspace/context
  keyboard flows pass `5/5`; workstation units `22/22`, full frontend Vitest `733/733`, type-check,
  and production build pass.
- **Canonical check:** the non-seeded `F8i-search-canonical` path now passes `1/1` against the
  live branch backend. Its first failure was a locator mismatch; direct request/response inspection
  confirmed `q=XLK` and an XLK result before the locator was corrected.
- **Acceptance flexibility used:** board-guided search composition plus a controlled canonical
  search fixture for deterministic interaction evidence. `REF-STATE-VARIANTS` remains open for
  authoritative pinned-build keyboard-selected-search styling; provider/live and other final gaps
  remain open.

## 2026-08-12 — Workspace listbox keyboard ownership repair

- **Implemented:** persisted workspace choices in the primary shell now expose a single focused
  listbox with `aria-activedescendant`, stable option IDs, arrow/Home/End traversal, Enter/Space
  activation, and recovery to the Workspace trigger after close.
- **Fix-first defect:** the opening `ArrowDown` event could bubble into the newly mounted menu and
  focus the first management action (`New`) instead of the workspace list. Stopping propagation at
  the trigger removes that race without changing menu action navigation.
- **Evidence:** workstation binding units `22/22`, full frontend Vitest `733/733`, type-check,
  production build, and rebuilt current-source shell/workspace/keyboard browser slice `3/3` pass.
  No visual threshold, mask, baseline, or product criterion was relaxed.
- **Remaining:** exact pinned-build V25 keyboard and selected/disabled state references remain
  under `REF-STATE-VARIANTS`; provider/entitlement, historical truth, native-monitor, endurance,
  and final-audit gaps remain open.

## 2026-08-12 — Persisted workspace management in the primary shell

- **Implemented:** the primary Workspace menu now manages persisted workspaces in addition to
  existing tabs/layouts: list/switch, new workspace, clone, rename, and delete with the backend's
  default-workspace guard. Startup avoids an unnecessary workspace-list request; menu opening and
  mutations refresh the list.
- **Fix-first evidence:** the first focused run exposed startup request-order regressions; the list
  is now hydrated from the default response and refreshed only on demand. The first browser flow
  exposed a stale menu locator after workspace switching; the flow was corrected and rerun.
- **Validation:** workspace store `48/48`, workstation binding `22/22`, combined focused `70/70`,
  type-check/build, and real-browser `F9d-workspaces` `1/1` pass. A workspace-ID switch now also
  forces Golden Layout dock replacement; the rebuilt CRUD browser flow remains `1/1`. Acceptance flexibility used:
  **None**. Full post-change frontend/browser/visual gates remain required.
- **Broader evidence:** full frontend Vitest now passes `733/733` across 94 files and the board-guided
  visual matrix passes `104/104`. The final canonical browser matrix passes `132/132` in `7.2m`.
  Earlier F9c3, F8u, and F8r-breadth interaction races were isolated, repaired at the test/activation
  boundary, and rerun successfully; no visual baseline, mask, threshold, or product criterion changed.

## 2026-08-12 — Chart-template rename and library response repair

- **Implemented:** the primary chart-template menu now supports rename in place. The stable key,
  configuration, symbol identity, versioning, import/export, clone, delete, and reset behavior
  remain intact.
- **Fix-first defect:** the first browser attempt found a real backend `MissingGreenlet` HTTP 500
  when an existing library item was updated. The workspace upsert now refreshes the row before
  response serialization, and the regression is covered by the workspace integration suite.
- **Evidence:** workspace-library integration `4/4`, chart-template component `7/7`, full frontend
  Vitest `732/732` across 94 files, browser `F9c` `1/1`, type-check/build, and diff-check pass.
  The complete workspace API module passes `25/25`; the authoritative combined backend gate passes
  `1384/1384` at `79.69%`. The complete current-source authenticated browser matrix then passes
  `131/131` in `6.6m`; the corrected isolated seeded board-guided visual matrix passes `104/104`
  in `5.1m` across all four required display environments. The first visual invocation against
  the canonical unseeded stack was rejected by the fixture guard and discarded as setup evidence.
  No visual threshold, mask, baseline, or acceptance criterion was relaxed.
- **Remaining:** exact/unrepresented V25 template states, provider/live-entitlement, historical,
  native-monitor, endurance, and final-audit gaps remain open.

## 2026-08-12 — Alerts indicator creation, comparison, and linked-timeframe parity

- **Implemented:** the primary workstation Alerts tool now directly creates both price and
  indicator alerts. Indicator mode uses the shared indicator catalog and parameter definitions,
  sends the active linked timeframe (with an explicit selector), and supports fixed-value and
  indicator-vs-indicator targets while retaining repeat/status/rearm behavior through the existing
  backend contract.
- **Evidence:** linked-alert units `10/10`; frontend Vitest `731/731`; type-check/build; rebuilt
  canonical browser `F11a`/`F11b`/`F11c` plus isolated narrow-dock `F8r-alerts-narrow` `4/4`; no browser diagnostics;
  health, state parsing, and diff-check pass.
- **Fix-first note:** catalog controls initially collapsed the repeat checkbox in a 340px dock;
  the hit target was repaired and the narrow browser check rerun. A stale frontend image also
  hid the new Study B parameter control until the container was rebuilt; the current-source
  browser rerun then passed. No visual threshold, mask,
  baseline, or acceptance criterion was relaxed.
- **Remaining:** exact/unrepresented V25 alert-editor styling remains under `REF-STATE-VARIANTS`;
  provider/live-entitlement, historical, native-monitor, endurance, and final-audit gaps remain
  open. The earlier post-change 129-case run without a completion marker is superseded by the
  authoritative current-source authenticated `flows.spec.ts` run: `131/131` passed in `6.8m`.

### 2026-08-12 Primary factory/registry/renderer consistency audit

Backend factory layouts, the frontend Add Tool registry, and renderer branches now have an audited
one-to-one supported set. `research_results` is present in the Study Lab factory and primary Add
Tool menu; excluded domains remain unregistered. No mismatch or code change was found.

### 2026-08-12 Authoritative backend unit/integration gate

Docker-enabled backend validation passes `1383/1383` at `79.69%` coverage (required threshold
55%), including canonical identity/provenance, ETF holdings and point-in-time taxonomy, analysis,
unified Python and research execution, workspaces/watchlists, providers, tasks, and websockets.
The earlier non-elevated Docker-socket fixture errors were setup-only and superseded. 86 known
third-party deprecation warnings remain; no acceptance criterion was relaxed.

### 2026-08-12 uPlot and workstation performance guards

The real-browser performance guards pass `3/3` in `15.9s`: 100,000-point uPlot history remains
interactive through repeated zoom/pan without chart replacement; simultaneous browser pop-outs
propagate symbols and recover; and repeated multi-window churn preserves bounded canvases, tools,
and heap. No threshold or renderer behavior changed. Beyond-bounded endurance and native physical-
monitor placement remain open.

### 2026-08-12 Board-guided visual regression revalidated

The restored seeded browser stack passes the unchanged four-environment visual suite `104/104`
in `7.9m` (1920x1080 and 2560x1440 at 100% and 125% display scale). The earlier connection-
refused run was setup-only and discarded; it produced no screenshot evidence. No baseline, mask,
threshold, token, or product criterion changed. This revalidates represented states only; exact or
unrepresented V25 states, `REF-STATE-VARIANTS`, provider/live-entitlement breadth, historical truth,
native-monitor, endurance, and final-audit gaps remain open.

### 2026-08-12 Canonical acceptance alignment and Market Breadth repair

The current-head authenticated matrix now passes `128/128` after correcting the acceptance
environment (canonical holdings/proxy assertions run with `E2E_SEED_MARKET_DATA=false`) and
repairing the real Market Breadth narrow-dock overflow. The Breadth control row now wraps at its
actual dock width without changing calculations or visual thresholds. The canonical SPY/RSP/XLK
holdings, XLK industry/proxy drill-down, all sector surfaces, and full workstation interactions
pass together. Seeded data remains labelled deterministic evidence for represented visual states;
it is not substituted for canonical provenance. No baseline, mask, threshold, or product criterion
changed. Exact/unrepresented V25 state styling, broader provider/live-entitlement coverage,
historical truth, native-monitor, endurance, and final-audit gaps remain open.

### 2026-08-12 Study Results restored to primary Add Tool registry

The persisted Study Results surface was implemented and included in the Study Lab factory layout,
but its `research_results` definition was missing from the primary workstation Add tool registry.
It is now registered and the real Add tool → Study Results flow passes rebuilt authenticated browser
coverage `2/2`; focused store/results coverage passes `57/57`, full frontend Vitest `728/728`, and
type-check/build pass with no browser diagnostics. The first browser attempt used a stale image and
was discarded; the rebuilt run is authoritative. No visual baseline, threshold, mask, or acceptance
criterion changed. Exact V25 Results styling remains `REF-STUDY-LAB-V25`; represented composition is
board-guided.

### 2026-08-12 Persisted Study Results state guidance

The dense persisted-results pane now renders human-readable Queued, Running, Completed, Failed,
and Canceled labels with state-specific guidance. Failed/canceled runs retain diagnostics/logs and
offer snapshot/latest reruns; queued/running/completed states explain preparation, refresh, and
artifact comparison. Focused units pass `10/10`, full frontend Vitest `728/728`, type-check/build,
and rebuilt authenticated `F8t-results` pass `1/1` with no browser diagnostics. No baseline,
threshold, or mask changed. Exact V25 state styling remains the explicit `REF-STUDY-LAB-V25` gap;
the represented composition is board-guided with controlled data.

### 2026-08-12 Study Lab failed/canceled recovery states

Study Lab now gives queued, running, completed, failed, and canceled runs explicit labels and
state-specific guidance. Failed/canceled runs preserve diagnostics/logs and expose snapshot and
latest rerun actions. Focused units pass `22/22`; rebuilt browser cancellation/failed-recovery/
results coverage passes `3/3`; full frontend Vitest passes `727/727`; type-check/build pass; and
the affected board-guided visual case passes `4/4` after reviewing only two changed 1080p
structured-result snapshots. No threshold or mask changed. `REF-STUDY-LAB-V25` and exact V25 state
styling remain explicit gaps.
The complete seeded authenticated Chromium matrix after the repair passes `125/127` executed
tests with two intentional skips in `5.5m`; no existing workstation/top-down or Study Lab path
regressed.

### 2026-08-12 Live ETF membership evidence clarified

The current non-seeded stack's canonical ETF-membership contract passes an isolated `3/3` flow
for SPY/RSP/XLK holdings, every sector industry surface, and complete sector drill-down. The
`404` holdings records visible in the broad log audit are expected unavailable/fallback probes,
not a failure of the core top-down workflow; no speculative provider change was introduced.
Broader issuer coverage, historical/provider entitlement evidence, and live-source breadth remain
open and explicitly tracked.

### 2026-08-12 Current-head non-seeded operational workstation gate

The rebuilt branch stack with both E2E seed flags disabled passes the complete authenticated
Chromium matrix `126/126` in `6.7m`. This revalidates the initial robust daily-analysis gate on
the current head: `US Top Down` benchmark/sector/industry/proxy/constituent drill-down, SPY/RSP
and XLK/XLE ratios, linking/timeframes/cross-window cursors, charts/templates/drawings, Python and
Study Lab, scans/gauges, notes/alerts, freshness/error states, pop-outs/recovery, legacy and
excluded-domain boundaries, and performance/containment all pass. Service logs contain only the
expected negative-path `401`/`404` and client-cancelled `499` records; no tracked runtime error
was observed. No acceptance flexibility was used for this gate. Board/reference state variants,
provider/live-entitlement breadth, historical truth, native-monitor, beyond-bounded endurance,
and final-audit gaps remain explicitly open.

### 2026-08-12 Alerts and Python Library narrow-dock coverage

Alert creation and Python Library creation controls now have constrained 340px geometry and
internal overflow checks (`1/1` each). Both existing layouts pass without CSS changes. Board-guided
dense composition and controlled seeded data were used; exact/state, provider/live, historical,
monitor, endurance, final-audit, and `REF-STATE-VARIANTS` gaps remain open.

### 2026-08-12 Top-down acceptance-oracle sequence hardening

Ratio and Relative Rotation acceptance now scope to live row-bearing/visible surfaces and measure
the actual constrained dock rather than making stale-root or full-window assumptions. Focused tests
pass `2/2`; the broader top-down/dense-tool slice passes `13/15` with two intentional skips. No
functional assertion was weakened. Board-guided dense composition and controlled seeded data were
used; exact/state, provider/live, historical, monitor, endurance, final-audit, and
`REF-STATE-VARIANTS` gaps remain open.

### 2026-08-12 Market Breadth dock-width containment

Market Breadth’s universe/timeframe/lookback/adjusted control row now wraps to its actual dock width
through a container query. Rebuilt constrained browser geometry passes `1/1`; full frontend Vitest
`725/725`, type-check, board-guided visual matrix `104/104`, and diff-check pass. No baseline,
threshold, mask, or calculation changed. Board-guided dense-tool composition and controlled seeded
data were used; `REF-STATE-VARIANTS` and exact/state/provider/live, historical, monitor, endurance,
and final-audit gaps remain open.

### 2026-08-12 EasyScan dock-width containment

EasyScan builder and scan controls now respond to their actual dock width using a container query;
at a constrained 340px surface the controls reflow and remain contained. Rebuilt browser geometry
passes `1/1`, EasyScan units `12/12`, full Vitest `725/725`, type-check, Docker production build,
and diff-check pass. The initial stale-image result was discarded. Board-guided dense-tool
composition and controlled seeded data were used; `REF-STATE-VARIANTS` and exact/state,
provider/live, historical, monitor, endurance, and final-audit gaps remain open.

### 2026-08-12 Top-down ratio context-menu targeting

The XLK-versus-active benchmark action now scopes its menu interaction to the originating sector
watchlist. This repairs an order-sensitive stale-detached-root acceptance defect while preserving
the exact `XLK/SPY` semantic legend assertion. The affected pair passes `2/2` and the isolated flow
passes `1/1`; the retained post-fix seeded browser matrix passes `120/122` with two intentional
skips. The later authoritative current-head non-seeded gate passes `126/126`. Board-guided dense composition and controlled seeded data were used; exact/state,
provider/live, historical, monitor, endurance, final-audit, and `REF-STUDY-LAB-V25` gaps remain
open.

### 2026-08-12 Relative Rotation narrow-dock acceptance coverage

Relative Rotation now has a rebuilt-stack browser geometry assertion at 390px (`1/1`). The
controls and plot remain visible and within the dock, and the header does not overlap the plot;
the wide companion table remains intentionally horizontally scrollable. No implementation change
was needed. Board-guided dense-tool composition and controlled seeded data were used; the
documented exact/state, provider/live, historical, monitor, endurance, and final-audit gaps stay
open.

### 2026-08-12 Unified Python editor popup semantics

The shared Python editor preserves the native textarea/textbox contract while exposing an explicit
`aria-haspopup=listbox`, `aria-expanded`, and unique `aria-controls` relationship to its SDK
suggestion popup. Linked editor instances receive distinct IDs; keyboard completion and Escape
dismissal remain unchanged. Focused editor coverage passes `4/4`, full frontend Vitest `725/725`,
rebuilt current-stack Study Lab editor/promotion browser coverage `1/1`, and type-check/diff-check
pass. The first counter-based ID attempt failed its linked-instance test and was repaired before
broader validation. Board-guided Study Lab/editor composition and controlled seeded interaction
were used; `REF-STUDY-LAB-V25` and the other documented exact/state/provider/historical/monitor/
endurance/final-audit gaps remain open.
The complete four-environment board-guided visual matrix passes `104/104` after this editor
change; no baseline, threshold, mask, or gap state changed.

### 2026-08-12 Study Lab narrow-dock containment

The Study Lab dense tool now reflows below 560px: title/source controls collapse to usable rows,
dataset controls become a two-column grid, and parameter controls become single-column. This
prevents horizontal overflow and header/editor collision in a 390px desktop dock. Focused
Study Lab/Python units pass `23/23`, rebuilt-stack browser geometry passes `1/1`, and type-check/
diff-check pass. The prior stale-image browser failure was discarded; the rebuilt rerun is the
authoritative evidence. Board-guided Study Lab composition and controlled seeded data were used;
`REF-STUDY-LAB-V25` remains `required_missing` because no authoritative V25 Study Lab capture is
available, along with the other explicitly tracked exact/state/provider/historical/monitor/
endurance/final-audit gaps.
The supporting backend unit suite also passes `1085/1085` at `70.04%` coverage against the
configured `55%` unit threshold, with only the known third-party deprecation warnings.
The complete seeded authenticated Chromium matrix passes `119/121` with two intentional skips
in `5.3m`, including the new Study Lab narrow-dock geometry assertion and the existing workstation
regression paths.
Docker-backed combined backend unit/integration coverage also passes `1383/1383` at `79.69%`
against the configured `75%` threshold, with 86 known third-party dependency warnings. This is
supporting contract evidence, not live-provider or authoritative historical-truth evidence.

### 2026-08-12 Recent Symbols containment acceptance

The shared shell-menu acceptance now includes the Recent Symbols overlay at a constrained desktop
viewport, proving fixed positioning stays within both viewport axes and Escape restores dismissal.
The rebuilt-stack browser flow passes `1/1`; type-check and diff-check pass. This closes an
acceptance-coverage omission, not an exact-build or unrepresented-state visual gap.

### 2026-08-12 shell-menu listener cleanup

Fixed a repository-controlled lifecycle defect in the fixed shell overlays: pointer, focus, change,
global Escape, selection, and unmount dismissal paths now synchronize resize/scroll listener
ownership. Workstation view unit coverage passes `22/22`; the rebuilt-stack focused shell browser
slice remains `3/3`; broader seeded browser and four-environment visual evidence is recorded in
the preceding entry. This closes lifecycle correctness, not exact-build or unrepresented visual
evidence.
Post-repair frontend Vitest is `724/724`; type-check, diff-check, manifest, visual-policy, and
uPlot renderer-contract validators pass. The preceding complete seeded browser `118/120` and
four-environment visual `104/104` results remain valid for the geometry change, with focused
post-cleanup shell browser coverage `3/3`.

### 2026-08-12 shell-menu viewport containment

Workspace, Help, Add Tool, and Recent Symbols overlays now share the dense workstation menu
contract: fixed trigger anchoring, actual viewport clamping, below/above collision placement,
internal scrolling, scroll/resize repositioning, and transient listener cleanup. Existing
workstation shell unit coverage passes `21/21`; the rebuilt-stack focused browser slice for
keyboard recovery, outside dismissal, and constrained containment passes `3/3`. The constrained
browser closes with Escape when a clamped overlay covers its trigger; this is a bounded interaction
oracle choice and does not relax product behavior or close any visual-reference gap.
The complete seeded authenticated Chromium matrix then passed `118/120` with two intentional
skips, and the four-environment board-guided visual matrix passed `104/104` without baseline,
threshold, or mask changes.

### 2026-08-12 LayoutPicker dismissal and focus recovery

The retained legacy layout picker now closes through Escape and outside-pointer interaction,
returns focus to the owning trigger when dismissed, and removes viewport/document listeners on
toggle, selection, profile save/load, and unmount. The focused component suite passes `3/3` and
the rebuilt-stack browser containment flow passes `1/1`. Browser coverage intentionally uses the
owning-trigger close path because restored legacy stacks can contain multiple picker instances;
document-level Escape/outside behavior is asserted in the component suite. This bounded browser
oracle flexibility is explicit and does not close `REF-STATE-VARIANTS`, exact pinned-build
interaction evidence, or any other visual/reference gap.

### 2026-08-12 LayoutPicker, EasyScan capacity, and Radar race closure

The LayoutPicker custom-grid and profile popovers now use the same viewport-safe contract as the
workstation's other dense menus: fixed trigger anchoring, 8px gutters, below/above collision
placement, width/height clamping, internal scrolling, capture-phase scroll/resize repositioning,
and cleanup on close/unmount. The corrected legacy-chart browser geometry passes `1/1`, adjacent
unit coverage passes `3/3`, full frontend Vitest passes `722/722`, and the four-environment
board-guided visual matrix passes `104/104`.

The unified-Python EasyScan path no longer rejects the current canonical all-instruments universe:
the bounded research batch ceiling is now 25,000 symbols (the active local universe is 10,948).
The focused backend materialisation contract passes `2/2`, and the affected EasyScan/Python,
ratio, drag, and gauge browser slice passes `5/5`. Radar result selection now waits for its
post-scan busy overlay to release pointer input; the focused Radar flow passes `1/1`.

The final consistently seeded authenticated Chromium matrix passes `117/119` with two intentional
skips. Earlier ETF constituent 404s came from a backend-only recreation with seed flags disabled
and were discarded as setup evidence; the authoritative rerun recreated the complete stack with
the documented seed/bootstrap flags. Acceptance flexibility used: board-guided represented UI
and controlled seeded data. Exact-build/unrepresented visual states, provider/live-entitlement,
historical truth, native-monitor, beyond-bounded endurance, and final-audit gaps remain open.
No visual threshold, mask, product, provenance, or uPlot rule changed.


### 2026-08-12 full authenticated regression after chart-toolbar repair

The rebuilt branch stack's complete authenticated Chromium matrix passes `116/118` executed tests
with two intentional skips in 5.1m across the chart toolbar, templates/plots, factory layouts,
linking/timeframes/crosshairs, top-down ratios/drill-down, Python/Study Lab, scans/gauges,
notes/alerts, pop-outs/recovery, legacy, exclusions, and performance/containment paths. No
product or visual criterion was relaxed; board-guided represented UI and controlled seeded
interaction/data remain interim evidence and exact/unrepresented, provider/live-entitlement,
historical-truth, native-monitor, endurance, and final-audit gaps remain open.

### 2026-08-12 constrained chart-toolbar overlap repair

At constrained desktop width, chart compare controls now occupy a dedicated first row while Plot
Library and Templates occupy a second row; chart surface padding reserves the toolbar area and
prevents overlap with OHLCV/chart content. Focused chart/menu units pass 31/31, full frontend
Vitest 720/720, type/build/diff checks pass, the rebuilt affected browser slice passes 4/4, and
the complete board-guided visual matrix passes 104/104 across all four required environments.
The adjacent narrow-menu assertion was corrected to match the deliberate above-trigger contract.
This was a localized fix-first parity correction; no baseline, threshold, mask, provider,
provenance, product, or uPlot rule changed. Board-guided represented toolbar composition and
controlled seeded interaction/data remain interim evidence; exact pinned-build selected/disabled
toolbar variants remain under REF-STATE-VARIANTS and other documented gaps remain open.

### 2026-08-12 ToolWindow menu vertical viewport containment

The shared ToolWindow action menu now uses fixed trigger anchoring with an 8px viewport gutter,
horizontal/available-height clamping, below-trigger placement with above-trigger fallback, and
capture-phase scroll/resize repositioning. Close, outside-pointer, action, and unmount paths
clean up transient listeners. Focused ToolWindow units pass 7/7, full frontend Vitest 720/720,
type/build/diff checks pass, the rebuilt seeded affected browser slice passes 11/11, and the
complete board-guided visual matrix passes 104/104 across all four required environments. This
was a localized fix-first parity correction; no baseline, threshold, mask, provider, provenance,
product, or uPlot rule changed. Board-guided represented dense-window/menu composition and
controlled seeded interaction/data remain interim evidence; exact-build/unrepresented,
provider/live-entitlement, historical-truth, native-monitor, endurance, and final-audit gaps
remain open.

### 2026-08-12 chart-local menu vertical viewport containment

Chart Templates and Plot Library now use the complete fixed trigger-anchored viewport contract:
8px gutter on both axes, width/available-height clamping, below-trigger placement with above-
trigger fallback, and scroll/resize repositioning. Close and unmount paths remove all transient
listeners. Focused chart-menu units pass 24/24, full frontend Vitest 719/719, type/build/
diff checks pass, rebuilt seeded browser coverage passes 4/4, and the complete board-guided
visual matrix passes 104/104 across all four required environments. This was a localized
fix-first parity correction; no baseline, threshold, mask, provider, provenance, product, or
uPlot rule changed. Board-guided represented chart/menu composition and controlled seeded
interaction/data remain interim evidence; exact-build/unrepresented, provider/live-entitlement,
historical-truth, native-monitor, endurance, and final-audit gaps remain open.

### 2026-08-12 Plot Library viewport containment and lifecycle cleanup

Chart Plot Library now uses fixed trigger anchoring with an 8px viewport gutter, narrow-width
clamping, resize repositioning, and listener cleanup on close/unmount. Its menu no longer relies on
ancestor-clipped absolute positioning. Focused chart-menu units pass `22/22`, full frontend
Vitest `717/717`, type/build/diff checks pass, rebuilt seeded browser regressions pass `3/3`, and
the complete board-guided visual matrix passes `104/104` across all four required environments.
This is a localized fix-first parity correction; no baseline, threshold, mask, provider,
provenance, product, or uPlot rule changed. Board-guided represented chart/menu composition and
controlled seeded data remain the interim evidence track; exact-build/unrepresented,
provider/live-entitlement, historical-truth, native-monitor, endurance, and final-audit gaps
remain open.

### 2026-08-12 ratio row-action oracle hardening

The complete seeded browser run exposed a single `F8e.2a` acceptance-oracle defect: selecting
the last visible ratio DOM node is ambiguous while Golden Layout retains detached/stacked roots.
The assertion now targets the requested `XLK/SPY` legend among visible ratio legends, avoiding DOM
order and transient activation-class timing. The adjacent ratio and chart regression slice passes
`11/11`, serial ratio checks pass `3/3`, and full frontend Vitest passes `716/716`; type, build,
and diff checks pass. The complete seeded Chromium rerun passes `112/112` executed with two
intentional skips in 4.9m. This is a
fix-first test/oracle correction, not a visual or product-criterion relaxation. Board-guided
represented chart/menu composition and controlled seeded data remain the interim evidence track;
exact-build/unrepresented, provider/live-entitlement, historical-truth, native-monitor,
endurance, and final-audit gaps remain open.

### 2026-08-12 chart-menu close-path cleanup and seeded rerun

Chart Templates and Plot Library close controls now share the same cleanup and trigger-focus
recovery path as Escape and keyboard toggles. Focused chart-menu units pass `21/21`, full frontend
Vitest passes `716/716`, type-check/build/diff-check pass, and the exact rebuilt browser slice
passes `4/4`.

An initial complete browser attempt was invalid mixed-runtime evidence because recreating only the
frontend removed the required backend seed/bootstrap flags; explicit top-down 404s and stale ratio
state were observed. The full stack was then recreated consistently and the affected top-down
slice passed `5/5`. No visual baseline, threshold, mask, provider, provenance, product, or uPlot
rule changed. Board-guided represented chart/menu composition and controlled seeded data remain
the interim track; exact-build/unrepresented and other documented gaps remain open.

### 2026-08-12 chart-local menu viewport containment

Chart Templates now follows the Plot Library's viewport-safe menu contract: its menu is anchored
to the trigger with fixed positioning, clamped inside an 8px viewport gutter, and recalculated on
window resize. This prevents dense chart docks from clipping or pushing the template editor
off-screen while preserving template identity semantics and keyboard focus recovery.

Focused chart-template/plot-library units pass `19/19`; focused browser coverage passes `3/3`;
type-check, production build, and diff-check pass; complete authenticated Chromium passes
`112/112` executed with two intentional skips; and the no-update four-environment board-guided
visual matrix passes `104/104`. No baseline, threshold, mask, provider, provenance, product, or
uPlot rule changed. Board-guided represented chart/menu composition and controlled seeded data
remain the interim evidence track; `REF-STATE-VARIANTS` and other exact-build/unrepresented,
provider/live-entitlement, historical-truth, native-monitor, endurance, and final-audit gaps
remain open.

### 2026-08-12 tool-window menu overflow and acceptance rerun

The shared tool-window action cluster now allows its absolutely positioned menu to escape a narrow
dock while retaining the dense header's selector/action geometry. The 390px browser oracle opens a
real tool menu and verifies visible, viewport-contained placement below its trigger.

Focused ToolWindow coverage passes `6/6`; focused authenticated browser coverage passes `3/3`;
type-check, production build, and diff-check pass. After a seeded stack rebuild, complete
authenticated Chromium passes `111/111` executed with two intentional skips and the complete
four-environment no-update board-guided visual matrix passes `104/104`. The earlier readiness
timeout was caused by the stopped Docker runtime after an interrupted run and is not accepted as
product evidence. No baseline, mask, threshold, provider, provenance, product, or uPlot rule
changed.

Acceptance flexibility remains explicit: board-guided represented dense-window composition and
controlled seeded interaction/data are used for represented states. Exact-build/unrepresented
visual states, provider/live-entitlement breadth, historical truth, native-monitor placement,
beyond-bounded endurance, and final-audit evidence remain open gaps.

### 2026-08-12 constrained tool-window header geometry

Shared tool-window chrome now remains usable when a desktop dock is narrowed. The title and symbol
retain a separate flexible region, the link/timeframe selectors keep bounded minimum widths, and
the action cluster remains visible instead of being pushed outside the header. At widths below
420px decorative link-color swatches are hidden while functional selectors, tool menu, maximize,
float, and close actions remain present.

Focused ToolWindow coverage passes `6/6`; type-check, production build, and diff-check pass. The
normal-width and 390px browser geometry regressions pass `2/2`, the complete authenticated
Chromium matrix passes `111/111` executed with two intentional skips, and the no-update
four-environment board-guided visual matrix passes `104/104`. The first narrow browser oracle
contained a native-selector mistake and the first visual command used nonexistent project names;
both were corrected before authoritative evidence. No baseline, mask, threshold, provider,
provenance, product, or uPlot rule changed.

Acceptance flexibility used: board-guided represented dense-window composition plus controlled
seeded interaction/data. Exact-build/unrepresented visual states, provider/live-entitlement breadth,
historical truth, native-monitor placement, beyond-bounded endurance, and final audit remain open.

### 2026-08-12 virtualized watchlist active-row keyboard semantics

The dense virtualized watchlist now exposes a truthful, mounted-instance-safe
`aria-activedescendant` contract. An initial or refreshed universe chooses its first canonical row
only when no explicit active symbol is available; docked and popped-out copies therefore cannot
collide on option IDs. Home/End and the existing arrow/Space/Ctrl+wheel traversal paths scroll the
TanStack virtualizer to the active row before publishing the canonical selection.

Focused component coverage passes `64/64`; type-check, production build, and diff-check pass;
focused authenticated Chromium passes `1/1`; and the complete authenticated Chromium flow matrix
passes `110/110` executed with two intentional skips and clean diagnostics. The first browser
attempts exposed a real initial-row lifecycle gap and stale frontend-image setup evidence; both
were corrected under the fix-first rule before the authoritative rerun. No visual baseline,
threshold, mask, provider, provenance, product, or uPlot rule changed.

Acceptance flexibility used: board-guided represented watchlist composition and controlled seeded
interaction/data. Exact-build/unrepresented visual states, provider/live-entitlement breadth,
historical truth, native-monitor placement, beyond-bounded endurance, and final audit remain open.

### 2026-08-12 visual fixture-history alignment after watchlist resize

The apparent post-resize visual regression was isolated to the retained `visual-1440p-125`
snapshots: those images were generated against an older seeded history. The current branch-scoped
stack was rebuilt with both seed flags, the factory reset remains enforced before each capture,
and only the stale 125% snapshot set was regenerated after reviewing the actual/expected content
drift. The complete no-update board-guided visual matrix now passes `104/104` across 1920x1080 and
2560x1440 at 100% and 125% display scale. No threshold, mask, or product criterion changed.

The fixture/baseline alignment gap is closed for the current pinned local dataset. The resize
functional contract remains independently green (`63/63` units and browser `1/1`); the separate
exact-build pointer-state and other unrepresented-state gaps remain tracked below.

### 2026-08-12 V25 data-grid header resizing

The workstation watchlist now exposes a dense V25-style header separator for every rendered
column. Desktop mouse dragging updates the column width immediately in the virtualized grid and
emits the existing serializable `columnOverrides` contract, so saved column sets/workspace
snapshots retain the result. The header surface has an explicit 23px minimum height so the
separator remains a real device hit target above the scroll layer, not merely a visually painted
affordance. The separator remains keyboard-focusable and the existing editor, sorting, grouping,
stacking, and virtualization paths are unchanged.

Focused component coverage passes `63/63`; type-check, production build, and diff-check pass;
the authenticated seeded Chromium resize regression passes `1/1` using native Playwright mouse
targeting on the rendered separator. The complete seeded
Chromium rerun reached `108/111` with two intentional skips; its one unrelated seeded-provenance
failure was reproduced against a frontend-only restart, then the consistently seeded full-stack
rerun passed the affected `F8e.1`/`F8e.1a` pair `2/2`.

Acceptance flexibility used: **board-guided represented data-grid/column-editor composition and
controlled seeded data**. The board shows column resizing and dense grid chrome but does not provide
an exact-build pointer-state capture; `REF-STATE-VARIANTS` remains open for exact V25 resize
affordance measurements. Native hit-target evidence is now closed by the browser regression. No
visual threshold, mask, provider, provenance, product, or uPlot rule was relaxed. Exact-build/
unrepresented visual states, broader provider/live-entitlement coverage, historical truth,
native-monitor placement, endurance, and final audit remain open.

### 2026-08-12 native hit-target correction and visual rebaseline

The first native Playwright resize attempt exposed a real layout defect: the CSS grid header had
collapsed to 1px, allowing the scroll surface to receive the device event even though the
separator was painted. The header now has a 23px minimum height and an explicit stacking context,
so the separator is visible, measurable, and owns native pointer input. Focused coverage passes
`63/63`; native resize passes `1/1`; the full authenticated flow passes `109/109` executed with
two intentional skips. The corrected geometry was reviewed, baselines were regenerated once, and
the no-update four-environment visual matrix passes `104/104`. No threshold, mask, or uPlot rule
changed.

### 2026-08-12 multi-toolbar flyout ownership

Mounted chart drawing toolbars now generate unique per-instance flyout IDs and scope all menu
queries to their own toolbar root. This prevents a four-chart/floating layout from redirecting
keyboard focus or `aria-controls` to another chart's Lines/Fibonacci/Shapes/Annotations flyout.
The IDs are DOM-only and are not persisted or used as instrument identity.

Focused multi-instance drawing coverage passes `3/3` (existing keyboard and selected-drawing
flows plus the four-timeframe ownership invariant); type-check and production build pass. The
complete seeded authenticated Chromium matrix now passes `108/108` executed tests with two
intentional skips in 4.7m. Two
fix-first test runs first exposed an invalid default-layout assumption and then a real collision:
Vue `useId()` and a module counter both produced duplicate IDs in the deployed runtime. The
implementation now uses per-mount random DOM identity, and the rebuilt seeded rerun passes.
The final no-update visual matrix passes `104/104` across 1920x1080 and 2560x1440 at 100% and 125%
display scale in 5.5m, without baseline, threshold, or mask changes. No visual threshold, mask,
provider, provenance, product, or uPlot rule was relaxed.

### 2026-08-12 visual-oracle semantic role repair after toolbar update

The first complete four-environment board-guided run stopped on an existing visual-spec query
that looked for workspace `Clone` and `Export` as buttons. The shell's deliberate accessibility
contract exposes those actions as `menuitem`s. The selector was corrected under the goal-level
fix-first rule; no product code, screenshot baseline, threshold, or mask changed. The rerun passed
`104/104` across 1920x1080 and 2560x1440 at 100% and 125% display scale in 7.0m.

This was a localized acceptance-oracle defect, not a toolbar regression. The failed invocation and
repair remain documented in the operational handoff; no acceptance flexibility beyond the already
recorded board-guided/seeded interim track was used.

### 2026-08-12 deterministic drawing-toolbar visual correction

The chart drawing toolbar now uses deterministic original CSS geometry instead of emoji or
platform-dependent Unicode glyphs. Group/tool icons, AVWAP, delete, visibility, lock, and cancel
controls have stable vector-like geometry; the rail is 40px and visible controls are measured at
32px. Existing toolbar menus, drawing selection, keyboard navigation, context actions, and uPlot
rendering are unchanged.

Focused drawing browser coverage passes `4/4`, including a rendered DOM contract that rejects
text glyph icons and checks compact button geometry. The represented default-workstation visual
assertion passes without baseline update at 1920x1080/100%, and the complete consistently seeded
authenticated Chromium matrix passes `107/107` executed tests with two intentional skips in
4.8m. Type-check, 468-module production build, full frontend Vitest `710/710`, and
`git diff --check` pass.

Acceptance flexibility used: **board-guided represented chart/dense-window composition plus
controlled seeded interaction/data fixtures**. The board does not provide pinned-build toolbar
icon measurements, so `REF-STATE-VARIANTS` remains open for exact drawing-icon styling and
selected/disabled toolbar variants. No visual threshold, mask, product criterion, provider,
provenance, or uPlot rule was relaxed.

### 2026-08-12 current-head browser acceptance

The current-head authenticated workstation matrix is green after fix-first repair of four semantic
test selectors, completion of the Python plot batch-results fixture, and explicit classification of
SPY industry/ETF-holdings unavailable responses. Focused repair flows pass `6/6`; seeded Chromium
passes `102/102` executed tests with `2` intentional skips. No product, visual-threshold, or mask
criterion changed. Seeded browser evidence remains an interim oracle and exact-build/unrepresented
visual states remain tracked.

### 2026-08-12 factory analysis-layout comparison surfaces

`Drill Down` now serializes the sector, industry, and constituent lists with a Golden Layout tab
stack containing `Selected Symbol` and `Sector Comparison`; `Sector by Year` now serializes the
same linked list surfaces with visible `Selected Symbol` and `Normalized Comparison` charts.
Both comparison windows carry explicit `SPY`/`RSP` configuration and render through the existing
uPlot chart path. Backend workspace contracts pass `24/24`; the focused rebuilt Chromium flow
passes `1/1`. This uses the accepted board-guided represented-state policy; exact-build and
unrepresented factory states remain tracked under `REF-STATE-VARIANTS`.

### 2026-08-12 keyboard-operable EasyScan condition builder

The advanced EasyScan condition builder now exposes `aria-expanded`/`aria-controls`, a named
region, deterministic entry focus, and focus recovery on collapse. Nested condition editing,
Python-backed scans, drag-in plots, universe/timeframe/schedule controls, results, cancellation,
and alerts remain unchanged. Focused coverage passes `12/12`; full Vitest `706/706`; type-check/
build and diff checks pass; rebuilt authenticated Chromium passes `1/1` with clean diagnostics.
The initial browser oracle was corrected to use Add tool → EasyScan, the outer advanced region, and
the stable toggle selector. Acceptance flexibility used: **board-guided represented condition-
editor/grid state plus controlled seeded browser evidence**. `REF-STATE-VARIANTS` and condition-
editor exact-build styling gaps remain open; no backend/provider/uPlot behavior changed. A duplicate
accessible-name defect between the outer builder and nested tree was fixed and rerun through the
focused, browser, and full frontend gates.

### 2026-08-12 keyboard-operable watchlist column editors

The integrated Columns and Sets editors now expose dialog semantics, keyboard entry, initial focus,
Arrow/Home/End navigation, Escape dismissal, and focus recovery to the owning trigger. Column
serialization, virtualized rows, drag ordering, Python columns, saved sets, and filtering remain
unchanged. Focused coverage passes `60/60`; full Vitest `705/705`; type-check/build and diff checks
pass; rebuilt authenticated Chromium passes `1/1` for the keyboard flow and `2/2` alongside the
established pointer-based Columns/Sets round-trip, with clean diagnostics. Acceptance flexibility
used: **board-guided represented watchlist/grid/editor state plus controlled seeded browser
evidence**. `REF-STATE-VARIANTS` partial/exact-build editor gaps remain open; no backend/provider/
uPlot behavior changed.

### 2026-08-12 keyboard-operable workstation shell menus

Workspace, Add tool, Help, and Recent symbols now use semantic menu items, keyboard opening,
Arrow/Home/End traversal, Escape dismissal, and focus recovery to their owning triggers. Existing
pointer dismissal, layout/workspace operations, symbol history, and tool opening remain intact.
Focused WorkstationView coverage passes `18/18`; full Vitest `704/704`; type-check/build and diff
checks pass; rebuilt authenticated Chromium passes `1/1` with clean diagnostics. The initial browser
selector oracle was corrected from title text to visible labels before the passing rerun, and the
recent-history unit oracle now selects the XLK action rather than the Clear action. Acceptance
flexibility used: **board-guided represented shell/menu state plus controlled seeded browser
evidence**. `REF-SHELL-V25`/`REF-STATE-VARIANTS` exact-build and unrepresented states remain open;
no backend/provider/uPlot behavior changed.

### 2026-08-12 keyboard-operable chart plot library

Chart plot management now exposes a semantic menu, opens from Enter/Space/ArrowUp/ArrowDown,
focuses the indicator picker on entry, and restores focus to the trigger on Escape. Indicator,
Python plot, EasyScan plot, copy, drag, and promotion contracts remain unchanged. Focused coverage
passes `15/15`; type-check/build and rebuilt authenticated Chromium pass `1/1` with clean
diagnostics. Acceptance flexibility used: **board-guided represented chart/plot-library state
plus controlled seeded browser evidence**; exact-build/unrepresented visual plot-library states
remain open. No backend/provider/uPlot behavior changed.

### 2026-08-12 keyboard-operable chart templates

The chart-template control now opens from keyboard input, exposes menu semantics, focuses the
template-name editor when opened, and returns focus to the trigger on Escape. Existing template
save/apply/import/export/reset and symbol-preservation contracts remain unchanged. Focused coverage
passes `4/4`; full Vitest `702/702`; type-check/build and diff checks pass; rebuilt authenticated
Chromium passes `1/1` with clean diagnostics. Acceptance flexibility used: **board-guided
represented chart/template state plus controlled seeded browser evidence**. Exact-build/
unrepresented template visual gaps remain open; no backend/provider/uPlot behavior changed.

### 2026-08-12 keyboard-operable watchlist context menus

Watchlist row context actions now focus the first enabled action on opening, support Arrow
navigation with wraparound, Home/End, Enter/Space activation, Escape dismissal, and return focus
to the originating row. Right-click and existing action events remain unchanged. Focused
VirtualWatchlistTool coverage passes `59/59`; full Vitest `701/701`; type-check/build and diff
checks pass; rebuilt authenticated Chromium passes `1/1` with clean diagnostics. Acceptance
flexibility used: **board-guided represented watchlist/context-menu state plus controlled seeded
browser evidence**. Exact-build/unrepresented menu visual gaps remain open; no backend/provider/
uPlot behavior changed.

### 2026-08-12 keyboard-operable tool-window menus

The dense tool-window menu now supports keyboard opening from its trigger, roving item focus,
Arrow/Home/End navigation, Enter/Space activation, Escape dismissal, and trigger-focus recovery.
Outside-pointer dismissal and existing click actions remain intact. The first browser run used a
stale frontend image; after rebuilding the current branch, authenticated Chromium passes `1/1`.
Focused ToolWindow coverage passes `5/5`, full Vitest `700/700`, type-check/build, and diff checks
pass. Acceptance flexibility used: **board-guided represented tool-window/menu state plus
controlled seeded browser evidence**. Exact-build/unrepresented menu visual gaps remain open; no
backend/provider/uPlot behavior changed.

### 2026-08-12 keyboard-operable workspace tabs

The primary workspace strip is now a semantic tablist with selected state, roving focus, and
keyboard activation. Arrow keys traverse layout tabs with wraparound, Home/End select boundaries
for focus, and Enter/Space activate the focused layout. The drag-reorder/persistence behavior is
unchanged. Focused mounted-view coverage passes `17/17`; full Vitest `699/699`; type-check/build
and diff checks pass; rebuilt authenticated Chromium keyboard coverage passes `1/1` with clean
browser diagnostics. Acceptance flexibility used: **board-guided represented tab/layout state
plus controlled seeded browser evidence**. Exact-build and other unrepresented visual gaps remain
open; this change does not alter backend/provider/uPlot behavior.

### 2026-08-12 primary workspace tab rearrangement

The visible workstation tab strip now supports pointer/mouse drag reordering, target feedback,
ARIA drag state, and persisted position updates through `reorderTabs`; duplicate drop/drag-end
events are guarded. After a stale-container attempt was discarded, the rebuilt current branch
passed the focused authenticated Chromium regression `1/1`, focused workspace/pop-out units
`63/63`, full Vitest `698/698`, type-check/build, and diff checks. Acceptance flexibility used:
**board-guided represented tab/layout state plus browser evidence**. Exact-build and other
unrepresented visual gaps remain open; no backend/provider/uPlot change.

### 2026-08-12 point-in-time membership cache identity

Group analysis cache identity now changes when selected members, lifecycle boundaries, verification
state, or provenance changes, while equivalent membership ordering produces the same version.
This prevents stale ranking/breadth/snapshot/rotation responses from surviving a membership update.
Focused unit coverage passes `17/17`; valid point-in-time integration coverage passes `2/2`;
changed-file Ruff/compile pass; and authoritative backend coverage passes `1382/1382` at `79.69%`
with 86 known dependency deprecation warnings. A first invalid selector invocation collected no
tests and was corrected before validation. No frontend/uPlot/CSS or visual baseline changed; acceptance
flexibility used: **None**. Historical source truth, provider/ETF, visual, hardware, endurance,
and final-audit gaps remain open.

### 2026-08-12 point-in-time membership completeness guard

Historical analysis now excludes market-group member rows without `known_at` when an explicit
`as_of` is requested, preventing unproven constituents from entering the top-down rotation,
breadth, and snapshot workflows. Current views preserve legacy compatibility, and static groups
may still omit group-level timestamps when member-level evidence exists. Focused unit/integration
coverage passes `18/18` and the authoritative backend gate passes `1381/1381` at `79.68%`. The
initial over-tightened root-group behavior was repaired and recorded as fix-first evidence. No
frontend/uPlot/CSS or visual baseline changed; acceptance flexibility used: **None**. Broader
historical source truth, provider/ETF, visual, hardware, endurance, and final-audit gaps remain.

### 2026-08-12 ETF live-route coverage contract execution guard

The provider-maintainability contract is now part of ordinary backend validation: the ETF live
module's registry-parity and concrete-route assertions run without network access, while issuer
probes remain explicitly opt-in. Focused contracts pass `2/2`, deterministic ETF adapters pass
`471/471`, and the authoritative backend gate passes `1380/1380` at `79.68%`. This is supporting
canonical constituent infrastructure for the TC2000 top-down workflow; no UI, uPlot, CSS, or
visual baseline changed. Acceptance flexibility used: **None**. Wider issuer/access, entitlement,
historical truth, visual-reference, hardware, endurance, and final-audit gaps remain open.

### 2026-08-12 canonical listing lifecycle timestamps

Canonical listings now retain nullable effective, known-at, and delisted timestamps, and the API
and frontend contracts carry them without changing the conservative inactive/reactivation policy.
Focused exchange/upsert/API coverage passes `17/17`; migration `f6a7b8c9d0e1` passes an isolated
PostgreSQL 16 upgrade → downgrade → upgrade cycle; frontend Vitest passes `698/698`, type/build
pass, and the authoritative backend gate passes `1380/1380` at `79.68%`. This strengthens the
security-master foundation for top-down provenance, but does not claim authoritative historical
listing truth. No acceptance flexibility used; source-review, provider/ETF breadth, visual,
physical-monitor, endurance, and final-audit gaps remain open.

### 2026-08-12 canonical multi-exchange listing payload

The canonical instrument detail contract now exposes each exchange-aware listing's MIC and
exchange metadata through `GET /instruments/{symbol}`. This keeps the provider-neutral workstation
able to distinguish same-issuer listings across Nasdaq, NYSE, Arca, and other normalised venues
without consulting a provider at render time. The focused authenticated API regression passes
`1/1`; frontend type-check, production build, and Vitest pass `697/697`; the authoritative backend
gate passes `1373/1373` at `79.67%`. Acceptance flexibility used: **None**. Historical listing
truth and broader provider/ETF coverage remain open.

### 2026-08-12 canonical lifecycle reactivation guard

Discovery seeding no longer turns an existing inactive canonical instrument, listing, or
provider-symbol binding back on merely because the provider returned a row. Provider lifecycle
fields remain source-labelled observations and are not promoted to canonical truth without
reconciliation. Focused seeding/listing coverage passes `4/4` and the authoritative backend gate
passes `1373/1373` at `79.64%`. No acceptance flexibility used; historical listing truth and
provider-breadth gaps remain tracked.

### 2026-08-12 backend revalidation after listing-lifecycle evidence retention

The authoritative combined backend unit/integration gate passes `1372/1372` at `79.62%` after
provider IPO/status/delisting observations were retained with field-level provenance. A prior
non-elevated invocation failed before integration collection because this environment denied Docker
and uv-cache access; the approved host-permitted rerun passed. The remaining historical truth,
provider/ETF breadth, visual-reference, physical-monitor, endurance, and final-audit gaps remain
tracked. No acceptance flexibility used.

### 2026-08-11 configurable Study Lab breakout lookback

Study Lab’s Highs and lows factory study now exposes a bounded integer lookback (default 20,
minimum 2, maximum 252) backed by the unified Python `parameters` namespace. The selected period
changes new-high/new-low event labels and is retained in the versioned run configuration. API and
isolated-runner validators now approve that documented namespace. Focused unit coverage passes
`20/20`, the focused browser path passes `1/1`, full frontend Vitest passes `697/697`, and the
authenticated Chromium matrix passes `97/97` after rebuilding the production stack. No product or
visual acceptance rule was relaxed. The rebuilt seeded board-guided matrix passed `104/104` across
1920×1080 and 2560×1440 at 100% and 125% display scale. This confirms represented visual states;
exact-build/unrepresented visual, provider/entitlement, physical-monitor, endurance, and final-audit
gaps remain open.

### 2026-08-11 typed symbol-search keyboard acceptance

The shell’s documented keyboard contract now has a real-user browser regression: typing outside a
text/code/search editor focuses the active-symbol field, produces canonical search results, and
Escape closes those results without stealing focus from the editor. The complete keyboard slice
passes `5/5`, and the complete authenticated Chromium matrix passes `96/96`. Initial assertions
were corrected to match actual browser behavior (mixed-case typing after the first shell shortcut
key and focus retention after Escape); no product criterion or visual acceptance rule was relaxed.
Exact-build/unrepresented visual, provider/live-entitlement breadth, physical-monitor, endurance,
and final-audit gaps remain tracked.

## 2026-08-14 — Study Lab research-helper integration

Factory Study Lab starters now exercise the unified executable SDK instead of duplicating equivalent
calculations: Forward-return distribution uses `research.conditional_outcomes`, while Volatility
regime uses `stats.rolling` and `stats.median`. Existing artifact names and renderers are preserved,
and focused source-contract assertions guard the integration. Study Lab tests pass `22/22`, the
adjacent authenticated browser slice `12/12`, full frontend `818/818` at `80.90%`, and the
type/build/uPlot/visual-policy gates pass. No visual threshold, mask, product criterion, or
acceptance flexibility changed; exact/unrepresented Study Lab V25 and broader external gaps remain
explicit.

### 2026-08-11 SEC ambiguous-ticker reconciliation guard

The SEC discovery path now distinguishes safe same-issuer multi-venue listings from ambiguous
same-ticker/different-issuer records. Rows with distinct CIK/name identities are retained in the
raw `UniverseDiscoverySnapshot` but are not promoted into the canonical instrument table; this
prevents ticker-only merging from contaminating top-down constituents, ratios, or research.
Same-issuer venue rows continue through the canonical MIC/listing normalizer.

Focused provider/persistence tests pass `90/90`; the full backend gate passes `1359/1359` at
`79.57%`. No acceptance flexibility was used. The remaining gap is a durable review/resolution
workflow for the raw ambiguity queue, plus historical listing truth and SEC live-access evidence.

### 2026-08-11 SEC multi-venue security-master discovery

The canonical security-master path no longer relies on Nasdaq as its only public discovery
evidence. SEC's official ticker/exchange directory is now an API-first, no-key discovery provider
for US issuer listings. It pages the full cached directory, preserves the reported exchange and
CIK, and routes venue labels through the existing canonical MIC normalizer, so NYSE, Nasdaq, NYSE
American, Arca, Cboe, OTC, and other SEC-reported venues can coexist without same-ticker merging.
The provider is identity/listing evidence only; prices, tradability, ETF membership, and freshness
remain independently resolved and labelled.

Focused provider coverage passes `81/81`; the full backend gate passes `1357/1357` at `79.56%`,
and frontend Vitest remains `682/682`. No acceptance flexibility was used. The remaining gap is
not hidden: SEC's issuer directory is not a complete live/tradable security master, does not cover
all funds/ETFs, and does not replace point-in-time delisting/listing history or entitled market
data.
The opt-in live probe from this environment returned HTTP 403, so the adapter remains
implemented/tested but not live-promoted until an authorised runtime satisfies SEC access policy.

### 2026-08-11 core workstation clean-deployment bootstrap

The workstation's clean-deployment path now creates the canonical benchmark/sector/NVDA identity
set, taxonomy, provider bindings, and ETF profiles before any UI request. A worker then hydrates
missing adjusted D1 history and holdings through the existing provider-neutral routes. In an
isolated non-seeded Compose database this produced 17 core histories and 16 non-fixture holdings
snapshots, with explicit provenance and a labelled partial XLC history; no fabricated market data,
fixture rows, or implicit yfinance path was involved. The resulting constituent expansion is
canonical data, not a replacement of the TC2000 product scope with provider work.

Focused bootstrap/worker tests and the combined backend gate pass `1355/1355` at `79.56%`. This
closes the previously observed empty-fresh-database prerequisite for the initial workstation, but
does not close broader exchange/security-master coverage, exact-build or unrepresented V25 visual
states, native multi-monitor validation, indefinite endurance, or final audit. Acceptance
flexibility used: **none** for code/data; board-guided visual acceptance remains explicitly interim
where the reference board has no authoritative state.

### 2026-08-11 seeded provenance isolation and complete board revalidation (latest)

The primary focus remains the TC2000-style workstation and US top-down flow. A reused acceptance
database was allowing provider-backed OHLCV and canonical ETF holdings to mix into seeded visual
fixtures. Seeded market-data reads now use only `e2e_reference` rows and are local-only; seeded
holdings reads use only `controlled_fixture`/`e2e_reference` snapshots. Normal non-seeded reads
retain the provider-neutral path. Focused backend coverage is 36/36 with changed-file Ruff green,
and final source inspection shows no provider rows were reintroduced into seeded SPY data.

The four required board-guided environments were refreshed once from the corrected deterministic
runtime and then verified without update mode: 104/104 pass at 1920x1080 and 2560x1440, 100% and
125% display scale. No threshold, mask, CSS token, or product criterion changed. This is the
documented seeded-fixture/board-guided flexibility track, not exact-build approval. Exact-build
and permission evidence, unrepresented V25 states, broader free-source/provider entitlements,
native physical-monitor validation, endurance, and final audit remain open. ETF adapter work is
supporting data infrastructure for the workstation, not a competing product objective.

The broader authenticated workflow matrix subsequently passes `85/87` with two canonical-only
skips. Frontend Vitest passes `682/682` across 92 files, `vue-tsc --noEmit` passes, and the
468-module production build passes. Provider-path review confirms that the new workstation's
market, identity, event, and discovery defaults are API-first; yfinance is excluded from those
chains unless an operator explicitly enables the legacy fallback. These results establish the
current robustly usable workstation boundary, but do not close the documented reference,
provider-entitlement breadth, physical-monitor, endurance, or final-audit gaps.

The official reference pack has been restored to controlled storage and rebuilt into the browsable
board: 230/230 media sources across 26 surfaces, with the rendered preview inspected against the
current workstation. A populated canonical branch volume with seeded mode disabled passes the
complete authenticated workflow matrix `87/87`, removing the two seeded-only skips from the
earlier run. A separate fresh non-seeded volume contained only SPY, no bars, no group members, and
no holdings snapshots; its downstream failures are retained as an explicit deployment data
initialization prerequisite, not counted as UI failures. The seeded acceptance stack is restored.

### 2026-08-11 canonical ETF-proxy drilldown and industry-context race repair

The primary workstation’s top-down flow is the current focus. Industry selection now propagates
the sector ETF context across docked and popped-out tools, while the store records that ETF at the
click boundary so late holdings hydration cannot revert the selected industry. The F8d/F8e slice
passes `10/10`, including XLK/Semiconductors -> SOXX and the direct XLK/SPY ratio action; the full
authenticated matrix passes `87/87`, frontend Vitest `682/682`, backend `1351/1351` at `79.64%`,
and type/build/uPlot/metadata gates pass.

The canonical issuer refresh now supports both SOXX and SMH for the Semiconductor proxy. SOXX is
served by iShares and SMH by VanEck's dated native workbook (`2026-08-10`, 27 rows, 25 resolved).
The repair corrected a stale persisted `ark` adapter and ensured an explicit VanEck product slug
cannot be shadowed by SEC series metadata during bootstrap, ingest, or bulk refresh. Runtime logs
show only expected cancellations, intentional conflict/auth probes, and labelled unavailable-data
404s; no unhandled runtime error signatures were observed. No visual threshold, mask, or
acceptance criterion changed. Exact-build/permission and unrepresented visual references,
broader provider breadth, native physical-monitor, indefinite endurance, and final-audit gaps
remain open. Acceptance flexibility used: **None**.
The attempted post-fix full visual rerun was deliberately not counted because preflight found the
running backend had `e2e_seed_market_data=false`; the last accepted seeded board matrix is
`104/104`. The latest code is behavior-only and introduced no visual baseline change.

### 2026-08-11 Direct watchlist ratio launch

Virtual watchlist context menus now expose `Open ratio vs active` for a different selected row.
The action configures the existing Relative Strength window with a canonical `=ROW/ACTIVE`
expression and brings that window forward; it does not navigate away or create a second chart
renderer. The ratio-chart branch now honours explicit expressions for the factory ratio window.
Focused component coverage passes `58/58`, adjacent authenticated browser ratio coverage passes
`2/2` (including XLK/SPY), the frontend type check passes, and the rebuilt Docker production
frontend contains all `468` transformed modules. The first browser attempt used an old container
image and was discarded; the rebuilt run is authoritative. No acceptance flexibility was used.
This closes a localized top-down interaction gap; visual/reference, provider/entitlement breadth,
physical-monitor, endurance, and final-audit gaps remain open.

### 2026-08-11 deterministic fixture isolation and complete board visual revalidation

Seeded E2E data is now isolated from persistent canonical observations: adjusted daily bars for the
controlled fixture universe are rebuilt on seeded startup, and seeded holdings queries require the
controlled fixture provenance. The focused regression slice passes `17/17`. The corrected runtime
required one documented refresh of the deterministic board-guided snapshots; the subsequent
no-update matrix passes `104/104` across all four required display environments. Thresholds and
masks are unchanged. This is board-guided seeded-fixture flexibility, not exact-build reference
approval; exact-build/permission, unrepresented states, provider/entitlement breadth,
physical-monitor, endurance, and final-audit gaps remain open.
The same corrected seeded stack also passes the complete authenticated functional matrix `84/84`
with two documented canonical-only skips, and the authoritative backend gate passes `1347/1347`
at `79.62%` coverage.

### 2026-08-11 Golden Layout readiness, conflict-oracle tie-break, and full seeded matrix

Golden Layout bootstrap now suppresses observational activation/normalisation events until the
host is interacted with, so startup cannot create unsolicited workspace snapshots. Add Tool now
waits on an explicit workspace-ready signal and reports an actionable state if the serializable
layout is unavailable instead of silently dropping the command. The F8j conflict oracle is scoped
to the newly added local Notes window, preventing unrelated bootstrap/pop-out snapshots from
consuming the injected 409. This is a fix-first tie-break: the product readiness defect and the
test-oracle race were both repaired; no acceptance threshold or product criterion was relaxed.
Focused adjacent F8j checks pass `2/2` twice. After recreating backend, worker, and research-runner
with `E2E_SEED_INSTRUMENTS=true` and `E2E_SEED_MARKET_DATA=true` (the earlier frontend-only rebuild
left the backend in its documented default false/false mode), the complete authenticated
`flows.spec.ts` matrix passes `84/84` executed tests with two documented canonical-only skips.
Direct authenticated API probes return XLK/XLB industry compositions and XLK/Semiconductors
verified proxies with controlled-fixture provenance. The earlier four failures were therefore
invalid mixed-runtime evidence, not accepted product failures. Acceptance flexibility used:
**None**; the explicit seeded fixture track is an existing documented test track. Visual/reference,
provider-breadth/entitlement, physical-monitor, endurance, and final-audit gaps remain open.
The post-fix frontend gates also pass: Vitest `679/679` across 92 files, `vue-tsc --noEmit`, the
468-module production build, `make test-uplot-contract`, YAML/JSON parsing, and `git diff --check`.
The final audited Compose log window contains none of the tracked 5xx/traceback/greenlet/constraint/
critical/fatal/unhandled/error signatures.

### 2026-08-11 Versioned provider entitlements and seeded top-down oracle

Provider entitlements now have append-only `provider_entitlement_revision` snapshots, a current
revision number, API history retrieval, and revision creation on PATCH. Runtime seeding no longer
treats unknown/unreviewed capability terms as implicitly free; explicit free-source entitlement
seeds control routing, and legacy unreviewed rows are upgraded without rewriting their history.
Migration `f2a3b4c5d6e7` is applied in the rebuilt stack. Focused provider coverage passes `19/19`
(`14/14` for the revision transition), while the current-head authoritative backend gate passes
`1346/1346` at `79.61%`. The rebuilt seeded top-down F8d/F8e slice passes `7/7` with two
canonical-only skips.
`F8e.1` now distinguishes labelled seeded fixture provenance from non-seeded canonical provenance;
this corrected a test oracle, not a product acceptance threshold. Visual/reference,
provider-breadth/entitlement review, physical-monitor, endurance, and final-audit gaps remain open.
Acceptance flexibility used: **None**.

## 2026-08-13 — Personal-watchlist local read boundary and bounded endurance

The workstation personal-watchlist add path now propagates `localOnly` through its eager price
refresh, preventing a newly added symbol from silently entering the provider-hydrating OHLCV route.
The focused store suite passes `21/21`, the full frontend suite passes `765/765`, type-check/build
pass, and the rebuilt authenticated `F8y` flow passes `1/1`. The governed two-popout churn run
with `TC2000_POP_OUT_CHURN_ROUNDS=100` passes `2/2` in `2.8m`, with bounded source tool/canvas
  counts and clean diagnostics. Acceptance flexibility used: **bounded stress in place of indefinite
soak**. Longer-duration endurance remains explicitly open.

## 2026-08-13 — Real uPlot gesture journey and latest-bar recovery

The authenticated workstation now has direct browser evidence for wheel zoom, trackpad-style
horizontal pan, chart-surface preservation, and `Go to latest bar` recovery. The focused journey
passes `1/1`, keeps the same uPlot element throughout, and reports clean browser diagnostics.
Acceptance flexibility used: **None** for product behavior. The initial unprivileged Chromium launch
was blocked before test execution by the known macOS Mach-port permission boundary; the permissioned
rerun is authoritative, and that setup limitation remains tracked in operations records.

## 2026-08-13 — Per-instrument indicator persistence race repair

The swing-analysis acceptance flow now requires both RSI and drawing restoration after a complete
sector → industry → constituent → sector round-trip. It exposed a real race: indicator insertion
could occur before canonical instrument hydration, while a stale debounced write could later overwrite
another instrument's state. The chart store now queues dirty saves until the canonical ID is known,
cancels stale saves on navigation, and persists copied payloads. Focused chart-store/Plot Library
coverage passes `55/55`, type-check/build pass, and the rebuilt authenticated flow passes `1/1`.
The post-repair authenticated regression slice passes `4/4` across gestures, swing analysis,
personal-watchlist activation, and combo-list persistence.
Acceptance flexibility used: **None**.

## 2026-08-13 — Real-user swing-analysis journey and plot-menu repair

The expanded browser journey passes `1/1` against the rebuilt workstation. It covers benchmark and
sector trend inspection, sector/benchmark relative strength, indicator insertion, drawing-tool
activation, industry and constituent traversal, ratio refresh, keyboard continuation, and returning
to the annotated sector to verify per-instrument indicator/drawing state restoration. The run exposed
and closed a real defect where the fixed Plot Library menu intercepted chart gestures after indicator
insertion; insertion now closes the menu and restores focus. The browser oracle targets uPlot's
`.u-over` interaction layer, not the underlying drawing canvas. Acceptance flexibility used: **None**.

### 2026-08-11 Provider-neutral workstation boundary audit

The current primary frontend was audited for provider leakage and fallback-order coupling. The
boundary test and provider-runtime tests pass `12/12` (focused run with repository coverage
disabled); provider selection remains in canonical backend capability policies. An isolated seeded
current-head stack then passed the authenticated excluded-domain menu check `1/1`, confirming that
trading, brokerage, options, news, ratings, earnings, financial statements, and consolidated
real-time capabilities remain absent from the workstation's primary menu without disabled shells.
Workspace persistence/layout tests pass `52/52`. This is boundary/containment evidence only; it
does not close provider-entitlement breadth, visual/reference, physical-monitor, endurance, or
final-audit gaps. Acceptance flexibility used: **None**.

### 2026-08-10 Sparkline data-quality normalization

The shared sparkline cache now filters null/non-finite close values before uPlot materialization.
Focused composable/component coverage passes `6/6`, full frontend Vitest passes `679/679`,
type/build and the uPlot renderer-contract guard pass, and authenticated dashboard `F15` passes
`1/1`. The initial chained guard command was run from the wrong directory and was corrected; no
product criterion or acceptance flexibility changed.

### 2026-08-10 uPlot-only Strategy Lab outcome maps

The axes-based SVG numerical renderers in `DistributionBars.vue` and `SymbolPerformanceBars.vue`
are now uPlot-backed numeric axes/canvas plugins with accessible HTML point controls. Focused
tests pass `2/2`, including uPlot/plugin construction assertions; the full frontend suite passes
`676/676` with no unhandled errors; type-check, production build, and the elevated authenticated
legacy-route browser check pass. Acceptance flexibility used: **None**. Remaining visual,
provider/entitlement/taxonomy, physical-monitor, endurance, and final-audit gaps remain open.

### 2026-08-10 uPlot-only shared and heat-map sparklines

The shared watchlist/dashboard `Sparkline.vue` and dashboard heat-map tile sparklines now use the
reusable uPlot host rather than SVG numerical geometry. Focused tests pass `5/5`; the full frontend
suite passes `678/678`; type/build, the numerical-SVG audit, and authenticated dashboard `F15`
pass. The complete authenticated Chromium matrix then passes `85/85` in `11.3m`, with a clean
audited service-log review. Acceptance flexibility used: **None**; this is an implementation
contract closure, not new exact-build reference evidence.

The primary renderer contract now has a repeatable guard (`make test-uplot-contract`) auditing 42
workstation/strategy/common/dashboard source files. It rejects dynamic SVG numerical geometry and
the removed sparkline helpers, while explicitly leaving static icon SVGs and excluded legacy
options canvases outside the new workstation contract. The guard passes; no acceptance flexibility
was used.

The official timeframe-linking help article is now also recorded as behavior authority for the
linking gap: eight groups, yellow wildcard propagation, grey isolation, cross-layout linking, and
multi-monitor linking. It strengthens behavior acceptance but does not promote a visual baseline;
`REF-LINKING-V25` remains explicitly open for authoritative state captures and measurements.

### 2026-08-10 uPlot-only Strategy result renderer

`StrategyResultChart.vue` no longer renders an axes-based numerical chart with hand-built SVG
geometry. Its real-time x values, range controls, hover details, numeric formatting, resize path,
and teardown now use uPlot. Focused renderer tests pass `6/6`; the full frontend suite passes
`676/676`; Strategy Lab view tests pass `28/28`; type-check and the 468-module production build
pass. This closes a repository-controlled renderer contract gap. Acceptance flexibility used:
**None**; the documented visual-reference, provider/entitlement/taxonomy, physical-monitor,
endurance, and final-audit gaps remain open.

### 2026-08-10 Rebuilt service-runtime verification

The branch `backend`, `research-runner`, and `worker` images were rebuilt after non-volume
Docker cleanup and recreated successfully in the branch Compose project. A no-network smoke
through the rebuilt research-runner executed the positive-close streak factory study and
returned the expected result. Backend, worker, and runner startup logs contained no audited
runtime-error signatures. This validates packaging/runtime deployment for the current
unified-Python implementation; it does not close the separately tracked visual-reference,
provider-breadth, physical-monitor, endurance, or final-audit gaps.

### 2026-08-10 Unified-Python lookback preflight

The unified Python validation contract now reports static lookback for the generated visual
condition forms (`ta.indicator` parameter maps and numeric `market.percent_change`) as well as
hand-authored indicator calls. Dynamic parameters remain explicitly unresolved rather than being
guessed. Focused validator/compiler tests pass `36/36`, authenticated code API tests `19/19`, and
the authoritative backend gate `1341/1341` at `79.60%`. This closes a preflight metadata gap; it
does not alter the documented visual/provider/hardware/endurance completion gaps.

### 2026-08-10 Lookback-aware dataset materialization

The immutable code-version lookback is now consumed by canonical materialization for Study Lab,
EasyScan, Strategy Lab, and reruns. Batch history expands to at least `lookback + 1`; single and
benchmark history follow the same bound; and requests at or above the 5,000-bar cap return a
structured error. Focused materialization coverage is `21/21`, affected EasyScan/Strategy Lab
coverage is `82/82`, and the authoritative backend gate is `1343/1343` at `79.60%`. This closes a
data-preflight correctness gap without changing the visual/provider/hardware/endurance gap ledger.

### 2026-08-10 Unified Python condition and full current-head gates

The integrated EasyScan condition editor now compiles its supported visual AST into the unified
Python SDK and persists an immutable, user-isolated Boolean code version. New scans execute in the
isolated runner with prepared metadata, canonical indicators, and the requested screener timeframe;
legacy records remain explicitly compatible. Focused compiler/runner/API/component/browser tests,
the authoritative backend gate (`1337/1337`, `79.59%`), and the complete authenticated Chromium
matrix (`85/85`) pass. This is implementation evidence for the Python-unification and EasyScan
parity rows, not a claim that exact pinned-build imagery or every unrepresented Version 25 state is
closed. Those reference gaps, provider breadth, physical-monitor validation, endurance, and final
audit remain open in the acceptance governance ledger. No product criterion was relaxed.

### 2026-08-10 Non-seeded core top-down gate

The branch stack was rebuilt with both E2E seed flags disabled. `/health` confirmed
`e2e_seed_instruments=false` and `e2e_seed_market_data=false`; the authenticated top-down slice
passed `8/8` in `48.2s` for SPX→SPY proxy labelling, SPY/RSP relative strength, canonical
SPY/RSP/XLK holdings, every Select Sector SPDR industry surface, XLK/XLE ratio editing, deep
industry-proxy/constituent traversal, and stable horizontal scrolling. Service logs were clean
for the audited runtime-error signatures. This provides non-seeded evidence for the initial
robust-workstation gate; it does not close the separately tracked provider breadth, visual
reference, physical-monitor, endurance, or final-audit gaps. Together with the current
backend/type/build gates, this satisfies the documented initial robust-workstation gate on a clean
non-seeded deployment. Acceptance flexibility used: **None**.
The complete authenticated `flows.spec.ts` matrix against the same non-seeded stack then passed
`85/85` in `9.5m` with one worker, covering shell/layouts, linking, pop-outs, Python/Study Lab,
scans/gauges, notes/alerts, legacy boundaries, uPlot performance, and lifecycle/churn.

### 2026-08-10 Watchlist failure isolation and final current-head matrix

Top-down benchmark and sector watchlists keep market-group/snapshot failures scoped to the
affected list, expose an assertive alert, and retain cached rows. Focused browser coverage is
`2/2`; focused component coverage `56/56`; full frontend Vitest `674/674`; type-check/build pass;
complete authenticated Chromium matrix `84/84` in `13.3m`. No acceptance flexibility, visual
threshold, or mask was used. Exact-build/unrepresented visual, provider/entitlement/taxonomy,
native-monitor, beyond-bounded-endurance, and final-audit gaps remain open.

### 2026-08-10 Top-down watchlist refresh semantics and current-head matrix

Benchmark and sector watchlists expose shared-refresh `aria-busy` and polite visible refresh
status while preserving virtualized rows and selection identity. Focused component coverage is
`55/55`; type-check/build pass; F8s-watchlist passes `1/1` in `16.7s`; the complete authenticated
Chromium matrix passes `83/83` in `12.1m`. No acceptance flexibility, visual threshold, or mask
was used. Exact-build/unrepresented visual, provider/entitlement/taxonomy, native-monitor,
beyond-bounded-endurance, and final-audit gaps remain open.

### 2026-08-10 Current board-guided visual matrix after lifecycle/recovery work

The exact current UI passes the complete no-update board-guided visual matrix `104/104` in `8.9m`
across 1920×1080 and 2560×1440 at 100% and 125% display scale. The isolated seeded stack used
alternate ports; service-log audit found no known runtime error signatures and the stack was
stopped without deleting named volumes. The documented board/fixture interim track was used for
represented states; exact-build/unrepresented gaps (`REF-SHELL-V25`, `REF-STATE-VARIANTS`,
`REF-LINKING-V25`, `REF-STUDY-LAB-V25`, `REF-ENV-TOKENS`, `REF-PERMISSION-REVIEW`) and broader
provider, monitor, endurance, and final-audit gaps remain open. No threshold, mask, or product
criterion changed.

### 2026-08-10 Workspace conflict recovery and current-head matrix

Workspace persistence browser acceptance now forces a revision conflict during Add Tool, supplies
a structurally divergent remote snapshot, and verifies the named recovery-copy message preserving
local changes. The initial unauthenticated baseline-fetch and case-sensitive assertion defects were
fixed under the tie-break rule. F8j-conflict passes `1/1` in `13.1s`; full frontend Vitest remains
`672/672`; type-check/build remain green; the exact current source's complete authenticated
Chromium matrix passes `82/82` in `14.9m`. No acceptance flexibility, visual threshold, or mask
was used. Exact-build/unrepresented visual, provider breadth, native-monitor,
beyond-bounded-endurance, and final-audit gaps remain open.

### 2026-08-10 Study Lab cancellation lifecycle and current-head matrix

Study Lab browser acceptance now covers validation → queued execution → cancellation → terminal
canceled state and confirms stale cancel/polling controls disappear. F8t-cancel passes `1/1` in
`14.7s`; full frontend Vitest remains `672/672`; type-check/build remain green; the exact current
source's complete authenticated Chromium matrix passes `81/81` in `13.5m`. No acceptance
flexibility, visual threshold, or mask was used. Exact-build/unrepresented visual, provider breadth,
native-monitor, beyond-bounded-endurance, and final-audit gaps remain open.

### 2026-08-10 Market Breadth state semantics and current-head matrix

Market Breadth now exposes explicit universe-scoped busy/loading/error/unavailable semantics backed
by independent snapshot/history request state; its dense metrics, drilldown, and uPlot history are
unchanged. Focused store coverage passes `45/45`, type-check/build pass, rebuilt F8s-breadth passes
`1/1` in `17.4s`, full frontend Vitest passes `672/672`, and the exact current source passes the
complete authenticated Chromium matrix `80/80` in `11.6m`. No acceptance flexibility, visual
threshold, or mask was used. Exact-build/unrepresented visual, provider breadth, native-monitor,
beyond-bounded-endurance, and final-audit gaps remain open.

### 2026-08-10 Current-head complete workstation matrix

Authoritative rebuilt-stack Chromium acceptance passes `79/79` in `14.2m` with one worker,
including the latest Notes, Coverage, Relative Rotation, and Instrument Report repairs. The
matrix covers the workstation shell, charts/templates/drawings, docking/pop-outs/recovery,
linking/timeframes/cross-window cursors, SPY/RSP/sector/industry/constituent drilldown and ratios,
Python/Study Lab, scans/gauges, notes/alerts, legacy/exclusions, uPlot performance, and churn.
No acceptance flexibility, visual threshold, or mask was used. Exact-build/unrepresented visual,
provider breadth, native-monitor, beyond-bounded-endurance, and final-audit gaps remain open.

### 2026-08-10 Instrument Report disclosure keyboard isolation

Instrument Report now exposes a symbol-scoped region and keyboard-operable disclosure header with
explicit button semantics and expanded state. Enter and Space toggle it without changing the dense
visual composition. The first browser run exposed a real propagation defect: Space reached global
symbol traversal and changed SPY to QQQ. Stopping propagation fixed it; focused coverage passes
`3/3`, type-check/build pass, and rebuilt F8s-report passes `1/1` in `9.4s`. No acceptance
flexibility, visual threshold, or mask was used. Exact-build/unrepresented visual, provider,
native-monitor, beyond-bounded-endurance, and final-audit gaps remain open.

### 2026-08-10 Relative Rotation state semantics and oracle correction

Relative Rotation now exposes a benchmark-scoped region with busy state, polite loading/empty
statuses, and assertive calculation errors without changing its dense uPlot plane, tails, sortable
table, or controls. Focused coverage passes `6/6`; type-check and the 468-module production build
pass; rebuilt Add Tool → Relative Rotation acceptance passes `1/1` in `9.2s`. The first browser
oracle incorrectly required a status node after a successful loaded response; the corrected oracle
accepts loaded rows/plot or an explicit status/error state and passes. This localized test defect
was fixed under the tie-break rule; no acceptance flexibility, visual threshold, or mask was used.
Exact-build/unrepresented visual, provider, native-monitor, beyond-bounded-endurance, and final-
audit gaps remain open.

### 2026-08-10 Coverage tool state semantics

The symbol-scoped Coverage tool now exposes a named region with busy state, polite loading,
assessment, and empty statuses, assertive fetch/range-validation errors, and labelled dataset
states without changing the dense provenance/OHLCV-readiness composition. Focused coverage passes
`4/4`; type-check and the 468-module production build pass; rebuilt Add Tool → Coverage browser
acceptance passes `1/1` in `15.3s`; full frontend Vitest passes `670/670`. No acceptance
flexibility, visual threshold, or mask was used. Exact-build/unrepresented visual, provider,
native-monitor, beyond-bounded-endurance, and final-audit gaps remain open.

### 2026-08-10 Symbol-linked Notes state semantics and rebuilt-image validation

The symbol-scoped Notes tool now exposes a named region with busy state, polite live status for
loading/saving/saved states, and assertive error semantics for load/save failures. Shared Vue Query
cache reads/writes preserve generation guards and debounced canonical autosave; dense visual
composition is unchanged. Focused linked-tool/race coverage passes `7/7`; full frontend Vitest
passes `670/670`; type-check and the 468-module production build pass. A first browser attempt
identified a stale frontend image; after a forced no-cache rebuild, F8s passes `1/1` in `13.1s` and
the complete authenticated matrix passes `76/76` in `13.9m`. No acceptance flexibility, visual
threshold, or mask was used. Exact-build/unrepresented visual, provider, native-monitor,
beyond-bounded-endurance, and final-audit gaps remain open.

### 2026-08-10 Active Alerts state semantics

The symbol-scoped Alerts tool now exposes a named region with busy state, assertive errors,
loading/empty statuses, labelled saved-alert list items, and accessible firing-history controls.
The dense alert editor/list layout is unchanged. Focused coverage passes `7/7`; rebuilt F11 passes
`1/1` in `24.3s`; full frontend Vitest passes `670/670`; type-check/build pass. No acceptance
flexibility, visual threshold, or mask was used. Exact-build/unrepresented visual, provider,
native-monitor, endurance, and final-audit gaps remain open.

### 2026-08-10 Market Gauge state semantics

Market Gauge now exposes a named region with busy state, polite freshness status, assertive error
state, and explicit loading/empty status regions. The scan-driven dense gauge layout and values
are unchanged. Focused coverage passes `7/7`; rebuilt F8w/F8w-a pass `2/2` in `25.7s`; full
frontend Vitest passes `670/670`; type-check/build pass. No acceptance flexibility, visual
threshold, or mask was used. Exact-build/unrepresented visual, provider, native-monitor,
endurance, and final-audit gaps remain open.

### 2026-08-10 Shell freshness live-status semantics

The docked and pop-out workstation shell now exposes a stable `workstation__data-state` status
region for current, fetching, backfilling, stale, delayed, partial, coverage-limited, and
unavailable states. Live announcements and atomic freshness labels were added without changing
the dense visual composition. Focused freshness/pop-out tests pass `31/31`; rebuilt F8i passes
`1/1` in `8.6s`; full frontend Vitest passes `669/669`; type-check passes. The first browser
attempt exposed brittle class-prefix locators, corrected before the passing rerun. No acceptance
flexibility, visual threshold, or mask was used. Exact-build/unrepresented visual, provider,
native-monitor, endurance, and final-audit gaps remain open.

### 2026-08-10 Study Results state semantics

Persisted Study Results now exposes named regions for the run list, selected state, statuses,
detail loading/empty/error states, structured artifacts, tables, and occurrence items. The dense
visual composition is unchanged. Focused Research Results coverage passes `9/9`; full frontend
Vitest passes `669/669`; type-check/build pass; rebuilt authenticated browser F8t-results passes
`1/1` in `13.8s`. No acceptance flexibility, visual threshold, or mask was used. Exact-build/
unrepresented visual, provider, native-monitor, endurance, and final-audit gaps remain open.

### 2026-08-10 Study Lab state live-region semantics

Study Lab validation, run-status, and execution-error surfaces now expose explicit live-region
semantics: invalid validation is an assertive alert, valid validation is a polite status, and
run/error updates are announced without changing the dense visual composition. Focused coverage
passes `19/19`; rebuilt authenticated browser F8t passes `1/1` in `10.1s`. No acceptance
flexibility, visual threshold, or mask was used. Exact-build/unrepresented visual, provider,
native-monitor, endurance, and final-audit gaps remain open.

### 2026-08-10 Study Lab structured-result semantics

Study Lab metric cards, non-scalar result regions, table captions/column scopes, and occurrence
lists/items now expose stable semantic labels without changing the dense visual composition.
Focused coverage passes `19/19`; full frontend Vitest passes `668/668` across 91 files; type-check
and the 468-module production build pass. After rebuilding the branch frontend, authenticated Study
Lab browser acceptance `F8g`, `F8o`, `F8p`, `F8q`, and `F8t` passes `5/5` in `1.2m`. No acceptance
flexibility, visual threshold, or mask was used. Remaining Study Lab visual-reference, provider,
native-monitor, endurance, and final-audit gaps remain open.

### 2026-08-10 virtual watchlist selection semantics

The virtualized workstation watchlists now expose a `listbox` with `option` rows, accessible
symbol/name labels, active and multi-selected state, and `aria-multiselectable`. Focused coverage
passes `54/54`; full frontend Vitest passes `667/667` across 91 files; type-check and the
468-module production build pass. After rebuilding the branch frontend image, authenticated
Chromium F8d, F8d-SPX, and F8r pass `3/3` in `28.6s`; the complete `flows.spec.ts` matrix passes
`75/75` in `11.6m`. The first browser attempt used a stale
container and old button-role locators; both were corrected before the passing rerun. No
acceptance flexibility, visual threshold, or mask was used. Remaining board/reference, provider,
native-monitor, endurance, and final-audit gaps remain open.

### 2026-08-10 shared tool-window action accessibility parity

The shared TC2000-style `ToolWindow` header now assigns explicit accessible names to the menu,
maximize, float, and close icon controls. This applies to docked and browser-popout instances
without changing the visible V25-like chrome or interaction behavior. Focused coverage passes
`4/4`; full frontend Vitest passes `666/666` across 91 files; `vue-tsc --noEmit` and the
468-module production build pass. No acceptance flexibility, visual threshold, or mask was used;
the F8r browser oracle now asserts the same names and passed `1/1` in 13.0s against the rebuilt
branch Compose stack. The remaining reference, provider, native-monitor, endurance, and
final-audit gaps remain open.

### 2026-08-10 top-down regression after Keating provider rebuild

The rebuilt branch backend passes the authenticated F8d benchmark/sector and F8d-SPX labelled
SPY-proxy browser slice `2/2` in `23.5s` against the normal non-fixture stack. This is direct
regression evidence for the workstation's primary top-down workflow after supporting-data
changes; no acceptance flexibility was used and the independent visual/provider/hardware,
endurance, and final-audit gaps remain open.

### 2026-08-10 Keating native holdings route

The official [Keating KEAT fund page](https://etfkeatinginvestment.com/) is now a provider-specific
native holdings route rather than a generic fallback. The adapter parses the complete HTML table,
retains its effective date and provenance, and preserves conditional SEC fallback. ETF adapter
units pass `471/471`, the exact opt-in live route probe passes `1/1`, and the authoritative
Docker-backed backend gate passes `1,329/1,329` at `79.60%`. This supports top-down ETF-proxy and
constituent drill-down only; no UI/visual criterion changed and all independent visual, provider,
monitor, endurance, and final-audit gaps remain open.

### 2026-08-10 Truth Social/Yorkville native-route identity reconciliation

Canonical `truth_social` discovery now resolves the verified Yorkville/Truth Social product-page
Google CSV route alongside `yorkville`, preventing a naming-dependent generic fallback in the
supporting ETF workflow. The selected official route cases pass `2/2`, ETF adapter/catalog units
pass `469/469`, and the Docker-backed backend gate passes `1,327/1,327` at `79.60%`. No frontend,
visual threshold, mask, or acceptance criterion changed; broader provider and independent goal
gaps remain open.

### 2026-08-10 bounded 500-round workstation lifecycle soak

The current branch stack passes both workstation performance tests (`2/2`) with
`TC2000_POP_OUT_CHURN_ROUNDS=500` in `11.2m`. Real two-popout churn checked bounded source
tool/chart/canvas counts, heap ceilings, symbol propagation, recovery, and browser diagnostics.
This is bounded hard-cap evidence only; indefinite endurance and native physical-monitor
validation remain open. No acceptance criterion or visual threshold changed.

### 2026-08-10 current-head authenticated matrix after supporting-data correction

The current non-fixture branch stack is healthy and the actual current `flows.spec.ts` collection
passes `75/75` in `11.9m` with one worker. This is the source-of-truth current functional matrix
for authentication, charts/templates/drawings, workspaces/pop-outs, linking, top-down/ratios,
Python/Study Lab, scans/gauges, notes/alerts, legacy, exclusions, and containment. Older records
mentioning `78/78` refer to a different test-file snapshot. No visual or product criterion changed;
the documented board/fixture, provider, monitor, endurance, and final-audit gaps remain open.

### 2026-08-10 AltShares native-route identity reconciliation

Canonical `altshares` discovery now resolves the verified native AltShares periodic holdings
route alongside the existing `water_island` adviser identity, removing a naming-dependent
generic fallback in the top-down ETF workflow. The official-route live case passes `1/1`, ETF
adapter/catalog units pass `468/468`, and the Docker-backed backend gate passes `1,326/1,326`
at `79.60%` coverage. No frontend, visual threshold, mask, or acceptance criterion changed;
provider breadth and independent visual, monitor, endurance, and final-audit gaps remain open.

### 2026-08-10 full authenticated workflow revalidation after fixture-target repair

The restored normal branch stack (`e2e_seed_instruments=false`, `e2e_seed_market_data=false`)
passes the complete authenticated Chromium matrix `75/75` in `11.1m`, covering workstation
chart/template/drawing, layouts/pop-outs, links/timeframes/cursors, top-down drill-down and
ratios, Python/Study Lab, scans/gauges, notes/alerts, legacy, unsupported domains, and performance.
Service-log audit is clean. No functional acceptance flexibility was used; remaining visual,
provider, monitor, endurance, and final-audit gaps remain tracked.

### 2026-08-10 fixture propagation repair and isolated board visual acceptance

`make test-stack-up` now propagates caller-selected fixture flags with safe defaults, preventing
the visual command from requesting market fixtures while the backend remains unseeded. A
persistent canonical-data run correctly produced a mixed-data difference and promoted no
snapshots. The dedicated seeded `tc2000-board-current` project then passed `104/104` board-guided
cases across 1920×1080 and 2560×1440 at 100% and 125%, including overlap and interaction checks.
Controlled fixture/board evidence was used explicitly; no visual threshold, mask, or product
criterion changed.

### 2026-08-10 focused provider/top-down backend regression gate

Provider, ETF-adapter, and top-down-taxonomy tests pass `557/557` with `--no-cov`. The initial
subset command had no test failures but did not satisfy the repository-wide coverage threshold;
the corrected focused result is recorded separately from the authoritative full backend gate.
No provider promotion or acceptance flexibility occurred.

### 2026-08-10 frontend regression/type/build gate

The corrected frontend gate passes `666/666` tests across 91 files, `vue-tsc --noEmit`, and the
production Vite build with 468 transformed modules. The first invocation used an unsupported
Vitest `--runInBand` option; it ran no tests and was corrected before recording this result.
Expected watchlist conflict stderr is covered failure-path behavior. No acceptance flexibility or
visual threshold changed; the documented visual, provider, monitor, endurance, and final-audit
gaps remain open.

### 2026-08-10 official keyboard behavior evidence

The official [Version 25 Hot Keys & Keyboard Shortcuts](https://help.tc2000.com/m/125751/l/1874569-hot-keys-keyboard-shortcuts)
article now supplements the interaction ledger for symbol search, Spacebar/Ctrl+Spacebar list
traversal, Ctrl+wheel timeframe navigation, chart shortcuts, and maximize. It is not a visual
baseline: keyboard-help and keyboard-selected visual states remain explicitly required-missing.
No acceptance flexibility or visual threshold changed.

### 2026-08-10 manifest and operations consistency audit

The 230-media visual manifest validates successfully, operations metadata parses, and
`git diff --check` is clean. This preserves the board-guided acceptance structure and explicit
gap ledger; it is not exact-build reference approval and no acceptance flexibility was used.

### 2026-08-10 authoritative backend gate after full workflow closure

The current backend gate passes `1,325/1,325` in `4m24s` at `79.60%` coverage. This revalidates
the provider/ETF adapters, canonical instrument boundary, top-down taxonomy/analysis, unified
Python and Study Lab/research runner, sandbox, persistence, and API integration contracts beneath
the workstation. Only known third-party NumPy/nautilus deprecation warnings appeared. No
acceptance flexibility was used; visual/reference, broader provider/entitlement, native-monitor,
endurance, and final-audit gaps remain tracked.

### 2026-08-10 full authenticated workflow closure after shell/watchlist fixes

The full rebuilt authenticated Chromium matrix passes `75/75` in `11.8m`. It includes the
deep-linked chart-template flow, watchlist column grouping/stacking, top-down sectors and
industry/proxy/constituent drill-down, ratios, linking/pop-outs, Study Lab/Python reuse,
scans/gauges, notes/alerts, legacy paths, and performance containment. The defects found by the
preceding run were fixed and covered by workstation units `15/15`; F9c passes `1/1`. Full
frontend Vitest is `665/665`, type-check/build pass, and the seed-free rebuilt stack is healthy.
No functional acceptance flexibility was used. Visual board/fixture flexibility and exact-build,
state-variant, provider/entitlement, native-monitor, endurance, and final-audit gaps remain
tracked in the reference and governance documents.

### 2026-08-10 isolated seeded visual acceptance revalidation

The persistent-stack visual attempt was correctly rejected by the fixture preflight because its
database contained canonical holdings while seeded mode was requested; the resulting 27,345-pixel
content difference was not treated as a UI regression and no snapshot was promoted. The fresh
`tc2000-board-current` Compose project then ran with controlled instruments and market data on
alternate ports. The complete board-guided matrix passes `104/104` in `9.0m` across 1920×1080 and
2560×1440 at 100% and 125% display scale. Manifest validation, seed health, service logs, and
diff checks are clean. Acceptance flexibility used: the approved 230-image board and controlled
fixtures for interim visual acceptance; exact-build and unrepresented-state gaps remain open. No
threshold, mask, snapshot, or product criterion changed.

### 2026-08-10 Curated SPDR/VanEck industry-proxy route coverage

Canonical top-down metadata now resolves `XAR`, `XHB`, and `XOP` through the verified SPDR
workbook family and resolves `OIH`, `SLX`, and `SMH` through VanEck's fund-scoped public
workbooks using issuer product slugs. The expanded opt-in live proxy matrix passes `10/10`; the
complete ETF adapter suite passes `467/467`; the authoritative combined backend gate passes
`1,325/1,325`; and the rebuilt authenticated `F8e` top-down browser slice passes `6/6` with
clean service logs. No acceptance flexibility used; remaining proxy breadth and workstation
visual, hardware, endurance, and final-audit gaps remain tracked.

### 2026-08-10 Curated iShares industry-proxy route coverage

Canonical route metadata now resolves the official iShares product identifiers for `IBB` (`239699`),
`ITA` (`239502`), and `ITB` (`239512`), enabling real holdings for the biotechnology,
aerospace/defense, and home-construction drill-down proxies. Official product references are
[IBB](https://www.ishares.com/us/products/239699/),
[ITA](https://www.ishares.com/us/products/239502/), and
[ITB](https://www.ishares.com/us/products/239512/). Opt-in live checks pass `3/3`, curated
resolver checks pass `4/4`, the complete ETF adapter suite passes `467/467`, and the combined
Docker-backed backend gate passes `1,325/1,325` at the configured coverage threshold. No
acceptance flexibility used; other curated proxies and the remaining workstation acceptance gaps
remain tracked.

### 2026-08-10 SPDR industry-proxy live coverage

Curated SPDR industry proxies now have live acceptance coverage: `XBI` (biotechnology), `KRE`
(regional banks), `XRT` (retail), and `XME` (metals/mining), returning dated issuer workbooks
with 157, 161, 77, and 41 rows. The SPDR live slice including SPY passes `5/5`; route-matrix
invariants, compilation, and lint pass. No acceptance flexibility used.

### 2026-08-10 SOXX industry-proxy live validation

The semiconductor industry proxy `SOXX` now has a live iShares acceptance case. The official
dated response returns 34 holdings including NVDA; the test uses a concentrated-ETF minimum of 30
rows and asserts the iShares route, composition date, and representative constituent. Focused
iShares checks, compilation, and lint pass. No acceptance flexibility used.

### 2026-08-10 EasyScan condition editor promoted to board-covered

The integrated EasyScan condition editor is now classified as `board_covered`: the composed
230-image board contains official Version 25 condition-editor and filter-selection states, and
the real interaction oracle plus four deterministic display-environment baselines pass. The
source pages do not prove pinned `25.0.9571`, so exact-build continuity remains recorded as
optional strengthening evidence rather than an unrepresented-state gap. Acceptance flexibility
used: board-guided evidence for this represented state; no threshold, mask, or product criterion
changed. The remaining watchlist visual gap is partial coverage.

### 2026-08-10 Leverage Shares provider correction

The canonical holdings backend now has a native Leverage Shares route using the issuer's public
symbol-scoped CSV (`/us/storage/holdings/{SYMBOL}_Holdings.csv`). The route is isolated behind a
provider-specific adapter, carries source/provenance metadata, and is covered by deterministic
parser/registry checks plus an opt-in live MPG test. ETF adapter units pass `463/463`; registry
coverage is 496 registered, 348 native/live-backed, and 148 audited fallback-only. This supports
the workstation's ETF-proxy/constituent workflow; it does not close the remaining provider
coverage or exact/unrepresented visual gaps.

### 2026-08-10 EasyScan condition-editor acceptance path

The integrated EasyScan technical condition tree is now covered by a real Add tool → EasyScan
→ Build technical condition tree browser path. It verifies the default AND group and the
condition/group insertion controls, with strict no-update screenshots passing 4/4 across the
four required display environments. The complete isolated seeded board-guided matrix passes
`104/104` in `8.1m`; the condition-editor state is now `board_covered` in the manifest. The
official source build remains recorded as optional strengthening evidence, not an exact-build
claim. Acceptance flexibility used: board-guided evidence for this represented state; no
threshold, mask, or product criterion changed.

### 2026-08-10 board-guided matrix after column-editor repair

The benchmark watchlist now passes its configured analytical column schema into the shared
virtualized list, and the column editor has a bounded dense grid/scroll treatment. The first
strict rerun exposed 19 deterministic baseline drifts; review confirmed current-column rendering
and stale 1440px seeded dates, so only affected baselines were refreshed. The complete isolated
seeded matrix passes `100/100` in `7.7m` across all four required display environments without
update mode. No masks, thresholds, or criteria changed; exact-build/state-variant, provider/live,
native-monitor, endurance, and final-audit gaps remain open.

### 2026-08-10 reference-board expansion for filters, linking, and historic columns

The controlled source catalogue now includes official help pages for the integrated Condition
Editor, ALL/ANY filter selection, symbol linking, and historic columns. Refreshing the pack yields
230 media files across 26 surfaces; board validation passes `230/230`. These sources strengthen
board-guided watchlist/filter/linking composition, while their source/build metadata remains
discovery-only where pinned `25.0.9571` continuity is not proven. Exact-build and state-variant
gaps remain open; no acceptance flexibility, threshold, mask, or product criterion changed.

### 2026-08-10 board-guided matrix after reference-pack refresh

The refreshed 230-image working reference board is paired with the deterministic seeded visual
fixture for every currently represented state. The isolated `tc2000-board-current` Compose
project passes the unchanged `test:visual:board` matrix `100/100` in `7.7m` across all four required
display environments (1920×1080 and 2560×1440 at 100% and 125% display scale). Runtime logs are
clean for the audited failure signatures, and the temporary stack was stopped without deleting
volumes. Board-guided represented-state flexibility is explicit: this evidence does not close
exact-build/permission, unrepresented-state, live-provider/taxonomy, native-monitor, indefinite
endurance, or final-audit gaps. No visual threshold, mask, baseline, or product criterion changed.

### 2026-08-10 reference-pack refresh and current backend gate

The controlled reference pack was refreshed from its recorded official URLs. All 230 media files
were retrieved, the composite board was rebuilt across 26 surfaces, and the board validator
passed all 230 sources. The current Docker-backed combined backend gate passes `1,319/1,319` at
`79.60%` coverage with 86 known third-party deprecation warnings. This strengthens auditability
without changing thresholds or closing the documented exact-build/unrepresented visual, provider
breadth, native-monitor, endurance, or final-audit gaps.

### 2026-08-10 current-head F9e/F8l regression closure

The latest full authenticated matrix had exposed two localized regressions. Import/reset now
flushes Golden Layout root withdrawal and replacement across explicit Vue render boundaries,
closing the intermittent stale-root failure in F9d→F9e; the reproduced sequence passes `10/10`
across five repetitions. Shared top-down store loaders now check document visibility at the
request boundary, closing the queued hidden-refresh race; the focused store suite passes `44/44`.
The rebuilt complete Chromium matrix passes `78/78` in `12.2m`, full frontend Vitest passes
`665/665` across 91 files, type-check and production build pass, and the recent backend/worker/
research-runner log audit is clean. No threshold, mask, product criterion, or acceptance
flexibility changed. Remaining board/reference, provider/entitlement/taxonomy, native-monitor,
endurance, and final-audit gaps remain explicitly open.

### 2026-08-10 current-head live top-down browser revalidation

After rebuilding the durable branch backend/worker images, the authenticated Chromium top-down
slice passes `8/8` against the current canonical route: SPX fallback, SPY/RSP, canonical holdings,
all-sector industry traversal, ratio editing, deep proxy/constituent drilldown, and stable scroll.
Runtime error-signature logs are clean. No visual or acceptance criterion changed and no
flexibility was used.

### 2026-08-10 current-tree frontend revalidation

The full frontend Vitest suite passes `664/664` across 91 files after the backend route correction;
type-check and the 468-module production build also pass. No workstation visual or acceptance
criterion changed. Remaining board/reference, provider breadth, hardware, endurance, and final
audit gaps remain explicit.

### 2026-08-10 Invesco route correction and backend gate

The full backend gate caught stale ticker-route expectations and a regression in the explicit
product-page compatibility path after canonical RSP moved to catalog→CUSIP. Both were repaired;
focused compatibility checks pass `3/3`, and the complete Docker-backed unit/integration gate
passes `1,319/1,319` at `79.60%`. This is supporting top-down data infrastructure; no workstation
visual or acceptance criterion changed and no flexibility was used.

### 2026-08-10 canonical RSP bootstrap route

The SPY/RSP top-down path now seeds RSP's canonical ETF profile with Invesco/CUSIP route
metadata, so bootstrap and refresh select the verified issuer adapter rather than depending on
manual profile setup. The integration regression proves the profile emits the CUSIP holdings
route. No visual or acceptance criterion changed; no flexibility used.

### 2026-08-10 RSP equal-weight holdings provider closure

The Invesco adapter now resolves RSP through Invesco's public product catalog (`RSP` →
`46137V357`) before requesting the CUSIP-addressed holdings JSON. The live route returned 511
holdings dated 2026-08-08; the opt-in repository live test passed, and all 462 adapter unit
tests passed. This strengthens the SPY/RSP top-down comparison with native free-source evidence;
no acceptance flexibility or visual criterion changed.

### 2026-08-10 patched-stack live top-down revalidation

After rebuilding the durable branch stack with the holdings source-policy guard, the complete
focused authenticated top-down browser subset passes `7/7` in elevated Chromium: labelled
SPX→SPY fallback, SPY/RSP, canonical holdings, all-sector industry surfaces, ratio editing, deep
proxy/constituent drilldown, and stable horizontal scrolling. Runtime error-signature logs are
clean. No acceptance flexibility used.

### 2026-08-10 controlled-fixture provenance boundary

The top-down backend now applies one source-policy guard to industry composition,
industry constituents, verified industry-proxy ranking, and ETF constituent snapshots.
Normal workstation mode excludes controlled E2E snapshots; seeded visual/e2e mode opts in
explicitly. A focused integration regression proves a newer fixture does not replace an
older issuer disclosure. No visual or acceptance criterion changed.

### 2026-08-10 complete authenticated matrix after branch-stack rebuild

The rebuilt durable branch stack passes the complete authenticated Chromium suite `78/78` in
11.5 minutes in one serial worker. It revalidates the workstation, top-down workflow, ratios,
linking/cross-window behavior, Study Lab/Python promotion, scans/gauges, legacy boundaries, uPlot
performance, and churn after the health-proxy change. The service-log audit is clean. No
acceptance flexibility used; visual-reference, provider breadth, hardware, endurance, and final
audit gaps remain open.

### 2026-08-10 rebuilt branch-stack live top-down acceptance

After rebuilding the durable branch stack, both frontend and backend `/health` paths return the
expected JSON fixture flags (`false`/`false`). The non-seeded live top-down subset passes `5/5`:
SPX proxy labelling, SPY/RSP relative strength, canonical SPY/RSP/XLK holdings, all 11 sector
industry surfaces, and XLK/XLE ratio editing. Service logs are clean. No visual or acceptance
criterion changed; this is canonical-database evidence, not a seeded-fixture substitution.

### 2026-08-10 current-code board-visual acceptance after fixture preflight repair

The new visual fixture preflight initially revealed that `/health` was being answered by the SPA
fallback. The frontend nginx and Vite development proxies now forward that path to the backend.
The rebuilt isolated seeded stack then passed `96/96` board-guided visual cases in 7.4 minutes
across 1920×1080 and 2560×1440 at 100% and 125% display scale; service logs were clean. No
baseline, threshold, mask, or product criterion changed. The accepted 190-image board remains the
represented-state authority, with exact-build/permission and unrepresented-state references
tracked as open gaps.

### 2026-08-10 isolated board-visual revalidation and fixture preflight

The shared-stack visual attempt was not accepted because the process requested seeded fixtures
while the backend served persistent canonical observations; the resulting 27,345-pixel (2%)
content difference was data contamination, not a promoted visual baseline. The board visual spec
now checks `/health` and fails before capture when the requested seeded mode is absent. In a
separate seeded Compose project on alternate ports, the complete board-guided matrix passed
`96/96` across 1920×1080 and 2560×1440 at 100% and 125% display scale, with valid manifest and
clean service logs. The 190-image reference board remains the accepted represented-state visual
authority; no thresholds, masks, or product criteria changed. Exact-build/permission and
unrepresented-state references remain open gaps.

### 2026-08-10 current-state authenticated Chromium revalidation

The unchanged complete authenticated Chromium suite passes `78/78` in one serial worker in 12.2
minutes. It covers the primary workstation and supporting in-scope flows, including top-down
drilldown/ratios, link groups and cross-window behavior, Study Lab/Python promotion, scans/gauges,
legacy/excluded-domain boundaries, and uPlot/workstation performance guards. The post-run service
log audit is clean for HTTP 5xx, traceback, MissingGreenlet, UniqueViolation, CRITICAL, FATAL,
Unhandled, and ERROR signatures. A non-elevated browser launch failed before app startup at the
macOS Mach-port permission boundary; the elevated unchanged rerun is authoritative. No
flexibility used; visual/reference, provider/taxonomy, hardware, endurance, and final-audit gaps
remain open.

## 2026-08-11 — Current-head backend acceptance gate

The authoritative combined backend unit/integration gate passed on the current branch: `1368/1368`
tests, total coverage `79.62%` against the required `75%` minimum. This includes canonical
instrument identity/reconciliation, provider entitlement governance, ETF holdings/taxonomy,
market-data freshness, Python validation/research jobs, Study Lab, workspaces, watchlists, scans,
and legacy APIs. The run produced only the known dependency deprecation warnings; no backend test
failure or new runtime error class appeared. This strengthens supporting-backend evidence but does
not close the separately tracked live-provider entitlement, exact/unrepresented visual,
multi-monitor, endurance, or final-audit gaps.

## 2026-08-11 — Current-head canonical workstation revalidation

The canonical non-seeded stack was rebuilt from the current source after the prior browser run
was found to be using a pre-change frontend image. The complete authenticated Chromium matrix then
passed `93/93` in 5.0 minutes, including the Python plot lifecycle, all top-down ratio/drilldown
paths, Study Lab, linking, pop-outs, persistence/conflict recovery, legacy compatibility, and
performance guards. The focused ratio slice passed `2/2`, and the frontend contract suite passed
`694/694` across 93 files. Type-check/build (468 modules), uPlot contract (`42` primary source
files), and `git diff --check` also passed.

Two localized browser-oracle defects were repaired under the mandatory fix-first rule: versioned
Python plot labels are now matched by a dynamic fixture name, and ratio acceptance selects the
visible active ratio window rather than a stale hidden Golden Layout root. The first canonical
matrix was `92/93` with only those oracle failures; the authoritative rerun is `93/93`. No visual
criterion, baseline, mask, or acceptance threshold was relaxed. The seeded browser run remains
documented as interim evidence for the earlier port-collision setup only. Exact-build/unrepresented
visual states, broader provider/live-entitlement evidence, native physical-monitor placement,
beyond-bounded endurance, and final requirement audit remain open.

## 2026-08-11 — Current-source board-guided visual matrix

The current seeded build passed the complete four-environment board-guided visual matrix:
`104/104` across 1920×1080 and 2560×1440 at both 100% and 125% display scale. Manifest validation
passed before execution. The matrix covers the shell, menus, factory layouts, docking/floating/
drag states, watchlist and condition editors, Study Lab states, chart/loading/provider/error
states, freshness states, and blocked-popout recovery. No screenshot baseline, mask, threshold,
or acceptance criterion changed. This is accepted board-guided evidence for represented states;
exact-build/unrepresented or materially ambiguous states remain explicit gaps in the manifest and
reference board.

## 2026-08-11 — Python plot-library workstation parity

The chart plot library now treats Python numeric-series plots as first-class plot assets. Users
can hide/show, reorder, duplicate, recolour, remove, drag, copy to linked charts, and copy to a
selected chart or watchlist target. Dropping a Python plot on a watchlist creates a reusable
`python_columns` entry and the chart runtime excludes hidden plots from research execution.
Focused component/library coverage passed `17/17`; the focused authenticated browser path passed
`1/1`, and adjacent Study Lab/Python acceptance (`F9g`/`F9h`) passed `3/3` on the deterministic
seeded branch stack. Full frontend Vitest passed `694/694` across 93 files; type-check,
468-module production build, uPlot-only contract (`42` source files), and `git diff --check`
passed. No visual baseline, mask, threshold, or acceptance criterion was relaxed. This closes a
repository-controlled plot-library gap; exact-build/unrepresented visual states, broader
provider/live-entitlement evidence, native physical-monitor placement, beyond-bounded endurance,
and the final requirement audit remain open.

## 2026-08-11 — Provider-governance authorization repair

The provider policy, entitlement mutation, and ambiguous-instrument reconciliation review
endpoints were incorrectly accepting any authenticated user. They now require the existing
administrator dependency; read-only provider status, policy, entitlement history, and health
surfaces remain available to authenticated workstation users. A regression test covers the
regular-user `403` boundary for reconciliation list/patch, policy patch, and entitlement patch.

The first focused test invocation exposed a syntax error in the newly added regression itself; the
missing parenthesis was repaired immediately and the focused suite was rerun. The authoritative
router suite passes `8/8`, provider integration passes `7/7`, Ruff and compile checks pass, and the
full backend coverage gate passes `1,368/1,368` at `79.62%`. No visual or product acceptance
criterion was relaxed. This closes a localized repository-controlled security boundary; the
remaining exact-build/unrepresented visual, provider-entitlement breadth/live access,
physical-monitor, beyond-bounded endurance, and final-audit gaps remain explicitly open.

The post-change authenticated browser boundary check also passes `1/1` against the branch frontend.
An initial restricted-sandbox attempt failed before Chromium created a page because of the host
Mach-port permission boundary; the permitted rerun passed and is authoritative. This environment
issue does not change the product acceptance result.

## 2026-08-11 — Durable reconciliation review workflow

The ambiguous security-master queue now records the administrator who resolves or ignores each
issue through a foreign-keyed `resolved_by_user_id`; reopening an issue clears the decision
attribution. Migration `f5a6b7c8d9e0` passed upgrade, downgrade, and re-upgrade in an isolated
PostgreSQL database and is applied to the branch database at head.

Legacy Settings now exposes an administrator-only identity reconciliation queue with candidate
issuer details and explicit resolve/ignore actions. Regular users do not fetch or see the queue;
the focused Settings component suite passes `3/3`, the regular-user authenticated browser check
passes `1/1`, changed-file backend regressions pass `10/10`, and the authoritative backend gate
passes `1,368/1,368` at `79.62%`. Frontend Vitest passes `690/690` and the production build/type
gate passes. No visual or product acceptance criterion was relaxed; this closes the previously
open review/resolution workflow gap while SEC live-access, historical listing truth, broader
provider coverage, visual-reference, physical-monitor, endurance, and final-audit gaps remain.

### 2026-08-10 post-lint-fix authoritative backend gate

The import/unused-symbol lint repair is green under full-tree Ruff check and focused regressions
pass `28/28`. The unchanged backend unit/integration gate passes `1,316/1,316` at `79.61%` coverage
against an isolated temporary database/Redis namespace, with 86 known third-party deprecation
warnings only; the temporary database was removed. A repository-wide formatter check still reports
79 baseline formatting diffs and was not used to rewrite unrelated user changes. No flexibility
used; visual/reference, provider/entitlement/taxonomy, hardware, endurance, and final-audit gaps
remain open.

### 2026-08-10 strict visual-reference audit

The stronger `visual_manifest ... --require-approved` audit intentionally fails closed at
`application-shell-default/default` because the state is `board_covered`, not exact-build
`approved`. Normal manifest validation and the four-environment board-guided matrix remain green;
this result records the stronger evidence gap rather than treating it as a whole-goal blocker.
Acceptance flexibility used: the approved 190-image board for represented states; exact-build and
permission-clearance evidence remain open.

### 2026-08-10 isolated Alembic round-trip

The current schema passes `upgrade head → downgrade -1 → upgrade head` against an isolated
temporary PostgreSQL database, including migration `eb1f2a3c4d5e`. The temporary database was
removed afterward and the workstation database was untouched. No acceptance flexibility used;
the remaining visual/reference, provider/entitlement/taxonomy, hardware, endurance, and final
audit gaps remain open.

### 2026-08-10 complete authenticated Chromium workflow

The complete non-visual Playwright suite passes `78/78` in one serial Chromium worker against the
healthy branch stack. It covers the workstation and supporting authenticated flows, top-down
drilldown, ratios, Study Lab/Python promotion, linking and cross-window behavior, legacy and
excluded-domain boundaries, uPlot history interaction, and workstation churn guards. Backend,
worker, and research-runner logs over the run window contain none of the fatal/error signatures
audited by the acceptance harness. No acceptance flexibility used; visual/reference,
provider/entitlement/taxonomy, hardware, endurance, and final-audit gaps remain open.

### 2026-08-10 frontend regression/build and manifest gate

The current frontend suite passes `664/664` across 91 files; `vue-tsc --noEmit`, the Vite
production build (468 modules), the visual-manifest validator, JSON/YAML parsing, and
`git diff --check` pass. A first invocation with unsupported Vitest `--runInBand` syntax is
retained as an invocation observation only; the unchanged repository command is the authoritative
green result. No acceptance flexibility used; visual/reference, provider/entitlement/taxonomy,
hardware, endurance, and final audit gaps remain open.

### 2026-08-10 authoritative combined backend gate

The full backend unit/integration acceptance command passed `1,316/1,316` at `79.61%` coverage
(required minimum 75%) against an isolated acceptance database and Redis namespace. A prior
container-in-container invocation is retained only as an environment execution failure: its
`1,026` unit tests passed, while `290` integration fixtures could not reach the Docker socket.
The corrected override-based run exercised the unchanged integration suite successfully. No
acceptance flexibility was used; the remaining workstation gaps are visual/reference,
provider/entitlement/taxonomy, native-monitor, endurance, and final audit evidence.

### 2026-08-10 bounded sandbox and runner-stress acceptance

Fresh live probes pass all eight sandbox escape denials, cgroup/tmpfs/concurrent resource
containment with restart count `0`, orphaned-job recovery after an isolated runner restart, and
`5/5` sustained cancellation-versus-success rounds without stale sentinels. The probes are
explicitly bounded; this closes the bounded sandbox/resource gate but does not claim indefinite
soak or native physical multi-monitor validation. No acceptance flexibility was used.

### 2026-08-10 isolated seeded acceptance-stack portability

Compose now permits alternate host bindings through `POSTGRES_HOST_PORT`, `BACKEND_HOST_PORT`,
`FRONTEND_HOST_PORT`, and `REDIS_HOST_PORT`, while retaining the default local ports. This allows
deterministic seeded acceptance projects to run concurrently with the normal branch stack. The
deployment contract tests pass `8/8` with `--no-cov`; the seeded project ran on 55432/18000/18080
and its exhaustive sector test `F8e.1a` passed `1/1`. The normal stack was restored and remained
healthy. No acceptance flexibility was used; remaining visual/reference, provider/taxonomy,
hardware, endurance, and final audit gaps remain open.

### 2026-08-10 partitioned authenticated workflow revalidation

The unpartitioned full-flow attempt that did not emit a completion summary was followed by bounded
serial partitions against the same non-seeded branch stack: workspace state `3/3`, docking,
pop-out, linking, keyboard, and freshness `24/24`, support/compatibility/legacy/performance
`23/23`, and authentication/chart/Study Lab states `14/14`. Together with the canonical
top-down/Python gate `12/12`, the selected authenticated workflow coverage is green without
claiming the interrupted unpartitioned runner as evidence. No acceptance flexibility was used for
these normal-stack partitions; the remaining visual/reference, provider, taxonomy, hardware,
endurance, and final audit gaps remain open.

### 2026-08-10 authenticated initial robust-workstation gate

The focused gate passed `12/12` Playwright tests. The branch-scoped backend reported
`E2E_SEED_INSTRUMENTS=false` and
`E2E_SEED_MARKET_DATA=false`. Executed coverage included canonical SPY/RSP membership, the
labelled SPY fallback for unavailable official SPX, all live sector industry surfaces, persisted
XLK/XLE ratio editing, deep sector-to-industry/proxy-to-constituent drill-down with `NVDA/XLK` or
proxy and `NVDA/SPY`, the positive-close Study Lab factory study, and unified Python promotion into
a watchlist column, EasyScan/alert, and chart plot. `F8e.1a` now runs against canonical data rather
than being artificially fixture-gated and passes. A separate controlled-fixture rerun was not
started because the normal stack owns host port 5432; no fixture result is claimed from that
attempt.

Acceptance flexibility used: none for the executed live gate. Exact/unrepresented V25 visual
states, board permission/exact-build evidence, native physical-monitor validation, bounded
endurance, broader provider/entitlement/taxonomy coverage, and final security/runtime audits
remain open.

### 2026-08-10 complete deterministic board matrix

After fixing the duplicate uPlot ratio legend, the deterministic local baselines were regenerated
once from a fresh controlled fixture and then revalidated without update mode. The complete
board-guided matrix passes `96/96` across 1920x1080 and 2560x1440 at both 100% and 125% display
scale, including shell, docking, menu/search, freshness/error, chart, pop-out, and Study Lab
states. Geometry, containment, and overlap oracles pass. No mask, threshold, product criterion,
or exact-build claim changed. This is board/fixture interim evidence; exact-build and
unrepresented-state gaps remain tracked by the manifest and board register.

The default-shell case was subsequently rerun against the retained seeded fixture with explicit
ratio-warning containment and duplicate-uPlot-legend browser checks; it passes 1/1.

### 2026-08-10 ratio-window overlap repair

The board comparison exposed a compact-window composition defect in the relative-strength tool:
uPlot's default HTML legend was rendered below the canvas while the workstation already rendered a
dense legend above it, allowing the duplicate legend to collide with warning/footer content. The
chart now sets `legend: { show: false }`; a focused unit regression verifies the option, and the
focused top-down/ratio/crosshair browser suite passes 6/6 with one intentional seeded-only skip.
The browser overlap oracle passes before screenshot-content comparison. Vitest is 664/664 and
type/build remain green. No threshold, mask, snapshot, or acceptance criterion changed; the
remaining board screenshot differences are still explicit baseline/geometry/content gaps.

### 2026-08-10 frontend race repair and visual-gate revalidation

The workstation remains the primary product surface; holdings/provider changes are only the data
foundation for its top-down workflow. The frontend now waits for the initial workspace snapshot
before mutating tools, rejects stale Golden Layout activation callbacks unless the component still
belongs to the current layout generation/header, keeps Python suggestions in a bounded in-flow
panel so they cannot intercept Code Library actions, and waits for the initial screener list before
creating a screener. Focused browser checks pass 6/6 for Python/Study Lab opening and 3/3 for
screener creation; the full functional flow passes 74 executed tests with one intentional skip.

Vitest 663/663, type-check, production build, backend 1,316/1,316 at 79.59%, and manifest
validation pass. Visual validation was run against a fresh isolated seeded database after an
earlier live-data/seed-assertion mismatch was discarded: the 1920x1080/100% board project passes
10/24. The 14 remaining screenshot differences are recorded as baseline/geometry gaps; no
threshold, mask, or snapshot was promoted. Board-guided local evidence is therefore useful for
iteration but does not establish exact-build V25 parity. Acceptance flexibility: approved board
policy plus controlled fixture only; no code acceptance criterion was relaxed.

### 2026-08-09 SOXX industry-proxy and live drill-down validation

The real-data top-down path now includes an issuer-native iShares SOXX snapshot obtained from
the public BlackRock product-data route (`issuer_product_id=239705`): 34 holdings, 32 canonical
resolutions, composition date 2026-08-07. SEC EDGAR enrichment populated sector/industry
classification for 27 of 29 available constituent profiles. The reviewed
`Semiconductors & Related Devices` alias is normalized only for the verified
`Semiconductors` industry mapping; unknown classifications remain unchanged.

The market-groups API now excludes controlled fixture proxy rows from non-seeded workstation
responses, and the authenticated UI preserves the selected sector as the taxonomy root when a
proxy is selected. The dense watchlist also preserves row DOM identity across value-only refreshes.
All 11 live sector selections now reach an industry surface with rows; the deep sector →
industry/proxy → constituent flow passes three repeated runs, including canonical proxy
selection and `NVDA/<proxy>` plus `NVDA/SPY` ratios. Focused top-down checks pass 7/7 with one
intentional seeded-only skip.

Validation: backend unit/integration gate 1,316/1,316 at 79.59%; frontend Vitest 663/663;
TypeScript and production build pass. No acceptance flexibility was used. This is a substantive
top-down usability advance, not completion of the full workstation objective. Remaining gaps are
broader canonical/free-source coverage, official SPX/RSP entitlements, additional verified
industry mappings, complete V25 visual/reference states, physical multi-monitor and endurance
evidence, and the remaining full acceptance matrix.

### 2026-08-09 canonical holdings and authenticated real-membership validation

The bounded holdings path now has canonical official State Street SPDR snapshots for SPY, DIA,
and all 11 Select Sector SPDR ETFs. The latest composition is 2026-08-06; SPY resolves 505/505
rows, DIA 31/31, and the sector snapshots retain `spdr_native_daily_holdings_workbook`
provenance. The configured Invesco RSP endpoint returned HTTP 500, so no Invesco success was
claimed; SEC N-PORT reconstruction supplies the labelled RSP fallback at 2026-04-30 with
508/508 resolved rows and `sec_nport_reconstructed_holdings` provenance. Parser footer handling
and bounded-ingestion provider fanout were corrected under the fix-first tie-break rule.

The authenticated real-membership browser check passes, as do the focused F8d/F8e checks (6/6
with one intentional skip), the full backend gate (1,314/1,314 at 79.59%), frontend Vitest
(662/662), type-check, production build, YAML/JSON validation, and diff checks. No acceptance
flexibility was used. Docker log inspection is unavailable from the restricted shell; the
previous rebuilt-stack audit was clean. This closes the bounded official SPDR evidence gap but
does not close the workstation goal: the live UI still needs complete sector-to-constituent and
industry/proxy drilldown validation, and the broader visual/reference, entitlements, coverage,
sandbox, performance, and completion evidence remains open.

### 2026-08-09 bounded SPDR holdings promotion attempt

The verified State Street SPDR daily-workbook route is now explicit for SPY, DIA, and the 11
Select Sector SPDR symbols, but a bounded canonical-ingestion attempt could not resolve the issuer
host in the active container and timed out before committing any snapshot. Existing controlled
holdings were not relabelled or deleted. Consequently, sector/constituent live-membership evidence
is still open even though the adapter contract and direct route probe are implemented. This is an
external live-evidence gap, not a frontend reprioritisation or a goal-wide blocker.

**Acceptance flexibility used:** None. No live success was claimed and no fixture evidence was
promoted as official membership. Closure requires an authorised live probe plus canonical snapshot
ingestion and authenticated UI verification.

### 2026-08-09 canonical Nasdaq EOD top-down data path

The new free-source Nasdaq public historical adapter is now registered for canonical price
history and latest-price fallback. It intentionally supports only D1 split-adjusted price/volume
observations; intraday, streaming, and total-return semantics remain unavailable and are exposed
as capability/freshness limits. Direct adapter probes returned 652 rows through 2026-08-07 for
SPY, RSP, XLK, XLE, and NVDA. Durable bulk ingestion persisted 3,034 rows through 2026-08-07
for SPY/RSP/QQQ/DIA/IWM, all 11 sector ETFs, and NVDA. The prior E2E fixture rows were removed
only for those 17 symbols so source provenance is not misrepresented. Canonical analysis now
proves full-overlap `XLK/SPY`, `XLK/XLE`, `NVDA/XLK`, and `NVDA/SPY`, 11 sector rotation rows,
11/11 breadth coverage, and an 11-row sector snapshot relative to SPY. Focused analysis,
market-data, Nasdaq, and provider-registry tests pass `35/35`; Ruff and diff checks pass.

The repair loop also now skips zero-width XNYS calendar markers and continues across typed
provider-availability failures when valid cached bars exist; cold requests and unexpected errors
remain fatal. A real-data browser run exposed a missing-volume 500 in shared technical/group
analysis; the common path now returns a structured `missing_volume` warning/cell instead. The
focused authenticated top-down checks pass `5/5` with one intentional skip, the post-run log
audit is clean, and the fresh full backend gate passes `1,313/1,313` with 358 live tests skipped.
No acceptance flexibility was used. Remaining parity gaps are explicit: issuer/
point-in-time holdings and verified industry proxies, wider constituent coverage, provider
entitlement/live-probe evidence, and the authenticated UI gate using this non-fixture data.

### 2026-08-09 Range ETFs official holdings route

Range ETFs' official NUKZ and COAL product pages expose complete dated holdings tables through a
Nuxt hydration payload. The native adapter is symbol-scoped, retains ticker/FIGI/shares/value/
weight fields, classifies cash rows, and preserves the issuer composition/as-of date. The two
opt-in official live routes pass `2/2`; deterministic route/registry checks pass `2/2`; all
`461/461` ETF adapter test bodies pass (the focused file's non-zero exit is coverage-only at
`51.36%`); and the isolated fresh-database backend gate passes `1,305/1,305` with `358` live
tests skipped at `79.58%` coverage. Registry counts are `496` registered, `347` native/live-backed,
and `149` audited fallback-only. The first run found a missing SEC-fallback readiness invariant
for the new adapter; it was fixed and the full gate rerun. No acceptance criterion was relaxed;
Ruff is unavailable in the image, while compilation and diff checks pass. This remains supporting
infrastructure for the TC2000 top-down workflow; the workstation and first robust live-data gate
remain the primary focus.

### 2026-08-09 Oakmark official holdings route

Oakmark's official OAKM and OAKI product pages expose complete symbol-scoped holdings CSVs. The
native adapter filters the requested `etf_fund`, normalizes the issuer's percentage-point weights,
classifies net-other-assets rows, and retains the issuer-provided as-of date. Both opt-in live
routes pass `2/2`; focused route/registry tests pass `2/2`; the complete ETF adapter suite passes
`460/460`; and the isolated Docker-backed backend gate passes `1,304/1,304` with `356` live tests
skipped at `79.56%` coverage against a fresh temporary database. Registry counts are `496`
registered, `346` native/live-backed, and `150` audited fallback-only. A reconciliation-batch
invariant found during the first adapter run was corrected and revalidated. No acceptance
relaxation was used; Ruff is unavailable in the backend image, while compilation and diff checks
pass. This is supporting data work for the TC2000 top-down workflow, not a frontend reprioritization.

### 2026-08-09 ACSI official holdings route

The top-down constituent data path now has a native ACSI Funds route using the issuer's public
daily holdings CSV. The HTTPS route and parser passed the opt-in live check `1/1`; deterministic
route/provenance and fallback invariants passed `2/2`, the full ETF adapter suite passed `459/459`,
and the isolated Docker backend unit/integration gate passed `1,303/1,303` with `354` live tests
skipped and `79.56%` coverage. The adapter retains a single issuer-provided composition/as-of
date and reports a warning for conflicting dates. Registry counts are `496` registered, `345`
native/live-backed, and `151` audited fallback-only. No acceptance relaxation was used for this
route. The earlier shared-database gate failure was fixture teardown against a stale schema; a
fresh temporary database passed the authoritative rerun and was removed. Ruff was unavailable in
the backend image, so lint is explicitly unverified; compilation and diff checks pass. This is
supporting data work for the TC2000 top-down workflow, not a change in frontend priority.

### 2026-08-09 authenticated workstation matrix

The rebuilt authenticated flow matrix passes `73/73` in one serial run. It exercises the complete
seeded top-down workflow (SPY/RSP, sector ranking, industry/proxy/constituent drilldown, NVDA
relative-strength legs, and Space traversal), chart/template/drawing mechanics, link groups and
cross-window propagation, watchlist columns/filters/copy/move, Python reuse across Study Lab,
columns, EasyScan, alerts, and plots, Study Lab factory/structured/promotion flows, notes/gauges,
pop-outs/recovery, unsupported-domain hiding, 125% containment, legacy routes, and Radar. This
does not substitute seeded/contract evidence for live free-source coverage or unrepresented V25
visual proof; those gaps remain explicitly open.

### 2026-08-09 complete visual matrix after workspace repairs

The complete board-guided matrix now passes `96/96` in one clean run across all four required
environments. This run includes default shell, menu/search/freshness states, tabbed/maximized/
restored/floating/drag-target workspace states, Study Lab states, chart loading/error, blocked
pop-out, and partial-coverage baselines. It follows the `HSACI56632` drag-time header ownership
repair and the bounded persisted-reset wait; no threshold or mask changed. Type-check, production
build, manifest/190-image board validation, service-log audit, and diff checks also pass. The
evidence remains board-guided/local interim evidence, not exact-build approval; provider/live,
native-monitor, endurance, and remaining functional/reference gaps stay explicit.

### 2026-08-09 drag-target and workspace-reset acceptance

Added a real browser oracle for board-covered `workspace-docking/drag_target`: a ToolWindow tab is
dragged into a Golden Layout drop target, the indicator is asserted, and the composition is
captured in all four required environments. The first full run exposed a localized
`HSACI56632` Golden Layout header race; `WorkspaceLayoutHost` now reasserts active state only when
the component still belongs to that header, with a focused regression passing `7/7`. Drag-target
visual coverage passes `4/4` after a rebuilt stack, and the affected 2560x1440/100% project passes
`24/24`. The preceding matrix had `95/96` because its Study Lab reset oracle used an insufficient
default timeout under serial project load; it now waits up to 15 seconds for the persisted reset
transaction, and the isolated reproduction passes. Frontend Vitest passes `662/662`, type-check/
build and service-log checks pass. Board/local interim evidence and seeded data were used; no
threshold or mask changed, and exact-build/reference, provider/live, native-monitor, endurance,
and remaining state gaps stay explicit.

### 2026-08-09 floating workspace visual coverage

The board-covered `workspace-docking/floating` state now has a popup-level browser oracle. It
floats a real ToolWindow, asserts the visible pop-out, captures the popup composition, closes it
through the user-facing control, and verifies source-tool recovery. Snapshot generation and
no-update verification pass `4/4`; the complete four-environment board-guided visual matrix
passes `92/92`; frontend Vitest `661/661`, type-check/build, board/manifest validators,
service-log audit, and diff checks pass. Four local baselines are linked from the manifest.
Board/local interim evidence and browser pop-outs were used; no threshold or mask changed.
Drag-target and the broader reference, provider/live, native-monitor, endurance, and permission
gaps remain explicit.

### 2026-08-09 restored workspace visual coverage

The board-covered `workspace-docking/restored` state now has a dedicated browser oracle. It
maximizes a real ToolWindow, invokes the restore control, asserts that the Golden Layout
maximized state is removed, and captures the restored composition. Snapshot generation and
no-update verification pass `4/4`; the complete four-environment board-guided visual matrix
passes `88/88`; frontend Vitest `661/661`, type-check/build, board/manifest validators,
service-log audit, and diff checks pass. Four local baselines are linked from the manifest.
Board/local interim evidence was used; no threshold or mask changed. Floating/drag-target and
the broader reference, provider/live, native-monitor, endurance, and permission gaps remain
explicit.

### 2026-08-09 tabbed workspace visual coverage

The board-covered `workspace-docking/tabbed` state now has a dedicated browser oracle. It
asserts a real multi-tab Golden Layout stack, activates a non-default tab, and captures the
composition. Snapshot generation and no-update verification pass `4/4`; the complete
four-environment board-guided visual matrix passes `84/84`; frontend Vitest `661/661`,
type-check/build, board/manifest validators, service-log audit, and diff checks pass. Four local
baselines are linked from the manifest. Board/local interim evidence was used; no threshold or
mask changed and exact-build/reference, provider/live, native-monitor, endurance, and remaining
state gaps stay explicit.

### 2026-08-09 maximized workspace visual coverage

The board-covered `workspace-docking/maximized` state now has a dedicated browser oracle: the
real ToolWindow menu invokes Golden Layout Maximize, the maximized class is asserted, and the
full composition is captured. Snapshot generation and no-update verification pass `4/4` across
the four required environments; the complete board-guided visual matrix passes `80/80`; full
frontend Vitest passes `661/661`; type-check/build, board/manifest validators, service-log audit,
and diff checks pass. Four local baselines are linked from the manifest. This uses the accepted
board/local interim track and does not promote the state to exact-build approval; no threshold or
mask changed. Remaining reference, provider/live, native-monitor, endurance, and other state
coverage gaps remain explicit.

### 2026-08-09 ToolWindow outside-click dismissal and visual state coverage

Shared ToolWindow three-dot menus now close on outside pointer input through a document-capture
listener, preserve menu actions for inside clicks, and unregister the listener on unmount. The
focused ToolWindow suite passes `4/4`; full frontend Vitest `661/661`; rebuilt authenticated
Chromium `73/73`; focused F8i `1/1`; and the complete four-environment board-guided visual matrix
passes `76/76`. The new workspace-docking `tool_menu_open` state has four deterministic local
baselines and remains `required_missing` under `REF-STATE-VARIANTS` because the board has no
authoritative pinned-build capture. Acceptance flexibility used: board/local interim evidence;
no threshold or mask changed.

### 2026-08-09 transient shell-menu exclusivity

The shell now enforces one transient menu layer at a time. Workspace, Add tool, Help, and
Recent symbols close each other and stale symbol search state when opened; search retains its
own editor/history surface while other shell menus dismiss on focus or outside pointer input.
Escape remains a global dismissal path. The focused WorkstationView binding suite passes `14/14`,
the rebuilt authenticated Chromium matrix passes `73/73`, focused keyboard-help visual coverage
passes `4/4`, full frontend Vitest passes `660/660`, `vue-tsc --noEmit`, production build, and
diff checks pass; the post-matrix service-log audit has no unhandled error signatures. No
screenshot threshold, mask, or product criterion changed. This closes a repository-controlled
interaction defect; the named
visual/reference, provider, hardware, and endurance gaps remain open.

### 2026-08-09 keyboard-help visual gap and Study Lab oracle determinism

The new shell Help state is now explicit in the manifest as `keyboard_help: required_missing`,
with shortcut-content/focus behavior and four deterministic local baselines. The full visual run
then exposed a shared-account geometry/state race in the Study Lab original-surface capture: one
1080p/125% project reused persisted splitter geometry and asynchronous chart/research responses.
That visual case now resets factory geometry and freezes those adjacent loading states; only its
four affected baselines were regenerated after review. Focused keyboard-help visual coverage is
`4/4`, focused Study Lab coverage is `4/4`, and the complete four-environment board-guided matrix
passes `72/72`. The 190-image board validator passes. Acceptance flexibility used: board/state-
variant interim evidence and controlled seeded data; no threshold or mask changed. The named
visual gap IDs remain open until stronger evidence exists.

### 2026-08-09 shell keyboard-help and editor-focus acceptance

The workstation shell now exposes a dense Help menu documenting the implemented global keyboard
contract; `F1` and `?` open it when shell focus owns the event. Focusing the Active symbol editor
dismisses the global menu and keeps `F1`/`Space` inside the editor rather than publishing a
workstation command. The focused rebuilt-stack browser flow passes `1/1`, and the complete
authenticated Chromium matrix passes `72/72` from 73 collected tests with one intentional skip.
Frontend Vitest passes `660/660`; the rebuilt frontend type-check and production image build pass.
The initial focused run used a stale frontend image; the correct branch-scoped rebuild exposed
and closed the localized focus-dismissal defect. Acceptance flexibility used: controlled seeded
market data only. No visual threshold, mask, or product criterion changed; visual/provider,
hardware, endurance, and unrepresented-state gaps remain open.

### 2026-08-09 reverse Space traversal and editor-focus acceptance

The global keyboard contract now has a real browser regression for both directions: `Space`
traverses forward and `Shift+Space` traverses backward through the active workstation universe.
The same flow proves that a focused symbol editor owns the literal space key and leaves the
published footer symbol unchanged. Focused coverage passes `1/1`; the complete rebuilt
authenticated Chromium matrix passes `71/71` from 72 collected tests with one intentional skip;
frontend Vitest `660/660`, type-check, and production build remain green. Acceptance flexibility
used: controlled seeded market data only. No visual threshold, mask, or product criterion changed.

### 2026-08-09 Anfield provider classification correction

The provider audit found that Anfield/ADFI was still listed as native/live-backed despite its
configured Regents Park product route returning HTTP 404. The custom adapter remains available
for deterministic parser coverage and conditional SEC reconstruction, but the registry now marks
it audited fallback-only until a complete issuer-owned route is executable again. The live-provider
coverage invariant no longer treats the unavailable route as a passing native test. Source-state
counts are 496 registered, 344 native/live-backed, and 152 audited fallback-only. Focused provider
invariants pass `10/10` test bodies plus the skipped opt-in live registry checks. No acceptance
flexibility, visual threshold, or product criterion changed; the Anfield route gap remains open.

### 2026-08-09 blocked-popout visual oracle determinism

The blocked-popout visual acceptance case now waits for the shared stable workstation/chart
readiness contract before and after the browser refuses the float action. This removes the
loading-versus-ready hydration race that produced one environment’s mismatch. Four local interim
baselines were regenerated after review; focused visual coverage passes `4/4` and the complete
board-guided matrix passes `68/68`. Acceptance flexibility used: the board-guided local baseline
track with controlled seeded data. No threshold or mask changed, and `REF-STATE-VARIANTS` remains
an explicit `required_missing` gap because authoritative V25 blocked-popout reference evidence is
still absent.

### 2026-08-09 atomic watchlist copy/move semantics

The workstation’s list-to-list membership action now uses one canonical backend transfer
transaction instead of independent add/delete calls. Copy retains the source item; move commits
destination insertion and source removal together, preserving flags and notes and reporting
structured validation failures. Focused backend coverage is `19/19`, full backend coverage is
`1301/1301` at `79.50%`, frontend Vitest is `660/660`, and rebuilt-stack F8y plus the complete
authenticated Chromium matrix pass `1/1` and `71/71`. A stale image returning `405` was found by
the first browser run and fixed through a forced no-cache rebuild; the running container was
inspected before acceptance was rerun. Acceptance flexibility used: controlled seeded data for
browser validation; no visual threshold or mask changed. Exact/unrepresented visual evidence,
live/free-source provider coverage, physical multi-monitor validation, and indefinite endurance
remain tracked gaps.

### 2026-08-09 board-guided visual revalidation after workspace repair

The strict board-guided visual matrix passes `68/68` across 1920×1080 and 2560×1440 at 100% and
125% display scale after the workspace replacement repair. This uses the documented 190-image
board/local-baseline and controlled-fixture flexibility for unrepresented/live-unavailable states;
no mask, threshold, or exact-build claim changed, and the reference-gap IDs remain open.

### 2026-08-09 workspace replacement race closure

The authenticated matrix exposed a localized F9d-to-F9e stale virtual-root race. Whole-workspace
imports and factory resets now withdraw the dock during replacement and recreate Golden Layout
virtual roots from the new serializable window objects using an explicit reload token. Host
lifecycle coverage passes `6/6`, the reproduced sequence passes `10/10` across five repetitions,
and the full rebuilt authenticated matrix passes `71/71`; no visual threshold or mask changed.
This was validated with controlled seeded market data, while live-provider and exact/unrepresented
visual evidence remain separate gaps.

### 2026-08-09 research-runner sandbox and recovery revalidation

Live branch-stack probes deny namespace/mount/setns/unshare, ptrace, fork, network, subprocess,
and root-write attempts. Resource limits, cgroup termination, tmpfs capacity, concurrent
pressure, isolated orphan recovery, and five bounded cancellation/success rounds pass with no
stale sentinels. This directly validates the unified Python/Study Lab execution boundary; only
the documented indefinite-soak gap remains.

### 2026-08-09 current renderer and large-list scale guards

The packaged uPlot Chromium guard passes `1/1`: it renders 100,000 points, performs 40 zoom/pan
viewport updates, and preserves the same chart element. The focused `VirtualWatchlistTool` suite
passes `52/52`, including the 10,000-row DOM bound and wide-column/header alignment checks. These
are direct implementation checks with no acceptance flexibility; native multi-monitor placement
and longer-duration endurance remain separate open gates.

### 2026-08-09 board-guided visual revalidation after watchlist repair

The rebuilt board-guided visual matrix passes `68/68` with `RUN_BOARD_VISUAL_PARITY=1` across
1920×1080 and 2560×1440 at 100% and 125% display scale. This is interim board/local-baseline
evidence for represented and unrepresented states; the six documented reference-gap IDs remain
open where the board lacks sufficiently authoritative V25 evidence. No masks, thresholds, or
parity criteria changed.

### 2026-08-09 watchlist virtual-root race closure

The fix-first tie-break was applied to the intermittent Golden Layout watchlist race. Duplicate
virtual roots can no longer replay an older name/selection: creation uses the live/latest draft,
store-level request deduplication, and a reactive newest-created selection fence. Focused F8y
passes `5/5`, and the complete rebuilt authenticated Chromium matrix passes `71/71`; frontend
Vitest remains `658/658` across 91 files with type-check/build, compileall, manifest, diff, and
status-aware backend-log checks green. No visual threshold, mask, or acceptance criterion was
relaxed. Exact/unrepresented V25 states, official/live-free-source coverage, physical
multi-monitor validation, and long-duration endurance remain tracked gaps.

### 2026-08-09 canonical venue linking and final interaction revalidation

The security-master support path now maps known provider venue labels to canonical US MIC
exchanges and persists distinct same-ticker listings per venue. Exchange-catalog coverage is
`9/9`, provider persistence/new-provider coverage is `86/86`, and the Docker-backed backend
suite passes `1,291/1,291` with `362` skipped under `--no-cov`. This is supporting infrastructure
for the TC2000 top-down workflow across US exchanges, not a replacement for the workstation
implementation.

The RatioUPlot editor keeps a local comparison-leg state while Golden Layout persistence is
debounced. A freshly rebuilt frontend passes focused F8e.2 `5/5` and the complete authenticated
matrix `71/71`; frontend Vitest remains `658/658`, type-check/build, compile, manifest, diff,
and status-aware backend-log checks pass. No thresholds or masks changed. Controlled fixture,
board-guided unrepresented-state evidence, browser pop-outs as the monitor proxy, and bounded
endurance are explicitly recorded flexibilities; exact-build visual, official/live-free-source,
native-monitor, and long-duration endurance gaps remain open.

### 2026-08-09 authenticated interaction matrix closure

The rebuilt authenticated Chromium matrix passes `71/71`. The final repository-controlled
fixes keep stacked columns at the first visible stacked position, reveal newly promoted
Python/condition columns after asynchronous persistence, and fence an actively edited personal
watchlist name from stale Golden Layout snapshot replacement. The complete frontend suite is
`658/658` across 91 files with type-check/build green; manifest, compile, diff, and backend-log
audits are clean. Wide-canvas tests use deterministic visible-cell coordinates to exercise the
real interaction path; this is not an acceptance relaxation. Exact-build/unrepresented visual
states, live/free-source provider breadth, physical multi-monitor validation, and endurance
remain open.

After review of representative captures, the board-guided local baselines were refreshed to
match the now-complete deterministic fixture's current freshness and numeric observations. The
strict four-environment visual rerun passes `68/68`; no threshold, mask, or exact-build claim was
changed.

### 2026-08-09 52-week stats hydration race

Concurrent linked-symbol hydration could race while creating the one-to-one `instrument_stats`
row, producing HTTP 500 responses during an otherwise valid sector traversal. Persistence is now
serialized per instrument within a worker and cross-worker unique conflicts recover the committed
row. The concurrent regression passes; the rebuilt seeded all-sector Playwright traversal passes
`1/1`, and the complete Docker-backed backend suite passes `1,282/1,282` with `362` skipped under
`--no-cov`. This is a repository-controlled reliability fix and does not alter the visual parity
thresholds or the controlled-fixture/live-provider distinction.

### 2026-08-09 all-sector controlled top-down fixture

The deterministic acceptance fixture now carries classified representative holdings and adjusted
history for all 11 S&P 500 Select Sector ETF proxies, rather than only XLK. Added invariant tests
and a seeded Playwright traversal covering each sector's industry surface. Focused backend
taxonomy/fixture/analysis coverage passes `16/16`; Playwright lists the new traversal test. This
is explicitly controlled-fixture evidence, not official S&P membership or live-provider evidence.

### 2026-08-09 watchlist row-and-column virtualization

`VirtualWatchlistTool` now uses TanStack Vue Virtual for horizontal columns as well as rows when
wide column sets exceed the dense-list threshold. Header translation follows the same scroll
position as the row canvas, and wide rows retain stable absolute positions. Focused wide-list and
header-alignment regressions pass; the full frontend suite is `658/658`, type-check, and production
build pass. This closes the implementation gap for large dense watchlists; it does not imply live
market-data coverage or exact-build visual approval.

### 2026-08-09 visual gap-oracle governance hardening

The visual manifest validator now requires every `required_missing` state to carry a unique
deterministic local baseline for each of the four required display environments in addition to
its interim oracle. The focused manifest suite passes `10/10` with `--no-cov`, and the checked-in
manifest passes CLI validation. This strengthens the interim board-gap acceptance track; it does
not promote any state to exact-build approval or close the tracked live-data, native-monitor, or
endurance gaps.

### 2026-08-09 persistence/concurrency repair

The first-class ratio editor prompted a real workspace-save audit. Golden Layout now suppresses
duplicate observational state events, the store bounds pending snapshot persistence and retries
stale generations, and persisted blue-link symbols hydrate before the workstation mounts. Snapshot
and factory-reset API writes use row-level locking to avoid duplicate-key failures during concurrent
tab replacement. F8e.2 passes `1/1`; frontend unit tests pass `654/654`; type-check/build pass.
The interrupted broad browser run reached `38` passes and exposed `9` adjacent failures, so no
full-matrix claim is made. No acceptance criterion or visual threshold changed.

### 2026-08-09 persisted ratio-leg comparison

The primary Relative Strength tool now provides a direct persisted comparison-leg editor, so the
top-down workflow can add `XLE` to an active `XLK` view and render `XLK/SPY` plus `XLK/XLE` in the
same uPlot surface. Focused unit coverage passes `10/10`, F8e.2 passes `1/1`, frontend Vitest
passes `653/653`, type-check/build pass, authenticated browser passes `70/70`, and the complete
board-guided visual matrix passes `68/68` across all four environments.

Two 1920×1080/125%-display baselines were reviewed and refreshed for this intentional control
change and seeded-current freshness state. Flexibility used: board-guided/local evidence for a
ratio-editor state not represented by the board; exact-build evidence remains open. No threshold,
mask, or acceptance criterion changed.

### 2026-08-09 seeded top-down data-path correction and complete acceptance

Analysis freshness now matches the canonical adjusted dataset key (`D1:adj`) while retaining the
legacy `D1` fallback. The authoritative backend gate passes `1285/1285` at `79.47%`; seeded SPY
technical and `XLK/SPY` responses report current/full coverage; the focused top-down browser slice
passes `7/7`. Full authenticated Playwright passes `69/69`, and the board-guided visual matrix
passes `68/68` across 1920x1080 and 2560x1440 at 100% and 125% display scale. The manifest is
valid and the recent log audit is free of backend 5xx/traceback/critical/fatal signatures.

Acceptance flexibility used: controlled provenance-labelled fixture data instead of live-provider
data. It is not official membership or live/free-source evidence; provider entitlements,
population breadth, and taxonomy completeness remain open parity dependencies. No threshold, mask,
baseline, or acceptance criterion changed.

### 2026-08-09 fresh rebuilt-stack authenticated revalidation

`make test-stack-up` rebuilt the branch-scoped stack and applied migrations; all core services
reported healthy. The authenticated `flows.spec.ts` matrix passes `69/69` in one worker across
the workstation/top-down workflow, linking/timeframes/crosshairs, pop-outs, Study Lab, unified
Python reuse, scans/gauges, notes/alerts, legacy compatibility, unsupported-domain absence, uPlot,
and performance guards. Service logs contain no HTTP 500, traceback, MissingGreenlet,
UniqueViolation, critical, or fatal signatures. Expected 404s for unseeded ETF holdings/industry
composition and unavailable OHLCV, plus missing optional provider credentials and exhausted
free-source fallback warnings, remain explicit data/provider gaps; no acceptance criterion changed.

### 2026-08-09 Study Lab sandbox-error visual-oracle coverage

Added a deterministic failed-run fixture covering source validation, sandbox diagnostics, warning
and execution-log disclosure, resource usage, and the rerun affordance. Focused visual checks pass
`4/4` across all required display environments and the complete board-guided visual matrix is now
`68/68`. This remains interim `REF-STUDY-LAB-V25` / `REF-STATE-VARIANTS` evidence because the
board has no authoritative Study Lab error capture. Acceptance flexibility used: deterministic
failed-run fixture only; no masks, thresholds, or criteria changed. `sandbox_error` remains an
explicit `required_missing` manifest state.

### 2026-08-09 Study Lab structured-result visual-oracle coverage

Added a deterministic completed Study Lab fixture covering scalar metrics, bar and histogram
uPlot output, a summary table, and clickable occurrence events. Focused visual checks pass `4/4`
across all required display environments and the complete board-guided visual matrix remains
`64/64`. This is interim `REF-STUDY-LAB-V25` / `REF-STATE-VARIANTS` evidence because the board
has no authoritative Study Lab capture. Acceptance flexibility used: deterministic completed-run
fixture only; no masks, thresholds, or criteria changed. Histogram and occurrence-table remain
explicit `required_missing` states in the manifest.

### 2026-08-09 Study Lab running-state visual-oracle coverage

Added the Study Lab `running` state to the manifest with a deterministic queued/running research
fixture. The browser flow validates the real source validation, run creation, progress text, durable
polling surface, and Cancel control; focused visual checks pass `4/4` across all required display
environments. This remains interim `REF-STUDY-LAB-V25` / `REF-STATE-VARIANTS` evidence because
the board has no authoritative running-state capture. Acceptance flexibility used: deterministic
runner fixture only; no masks, thresholds, or criteria changed. The complete board-guided visual
matrix then passed `60/60` across all four required environments.

### 2026-08-09 authenticated workflow revalidation

The rebuilt authenticated Chromium workstation matrix passes `69/69`, covering the current
top-down workflow, linking, pop-outs, Study Lab, Python promotions, scans, gauges, notes, alerts,
legacy compatibility, unsupported-domain absence, and performance guards. This is functional
evidence; the board-guided visual matrix remains separately measured at `60/60`. Exact-build or
unrepresented visual states, live-provider entitlements, native multi-monitor behavior, and
beyond-bounded endurance remain explicit gaps. No acceptance criterion or visual mask changed.

### 2026-08-09 fetching freshness visual-oracle coverage

Added the application-shell fetching state to the manifest gap register and exercised the real
pending-OHLCV path rather than a synthetic label. Focused visual checks pass `4/4` across the four
required environments; the state remains interim `REF-STATE-VARIANTS` evidence because no
pinned-build fetching capture is available. Acceptance flexibility used: documented board/state-
variant substitution only; no masks, thresholds, or criteria changed. The complete board-guided
visual matrix then passed `60/60` across all four required environments.

### 2026-08-09 disabled-control visual-oracle coverage

The Study Lab validation-error flow now explicitly asserts that the invalid study cannot be run;
the disabled Run control is linked to the existing deterministic four-environment validation-error
baselines. Focused visual checks pass `4/4`; this remains interim `REF-STATE-VARIANTS` evidence,
not exact-build approval. Acceptance flexibility used: board/state-variant substitution only;
no masks, thresholds, or criteria changed.

### 2026-08-09 keyboard-selected search visual-oracle coverage

Added the keyboard-selected active-symbol search state to the application-shell gap register.
The ArrowDown/`aria-selected` behavior and deterministic local visual baselines pass `4/4` across
the required environments; the complete board-guided matrix passes `52/52`. This remains interim
`REF-STATE-VARIANTS` evidence because no
authoritative pinned-build state capture exists; no masks, thresholds, or criteria changed.
Acceptance flexibility used: board/state-variant substitution only.

### 2026-08-09 unavailable freshness matrix completion

The application-shell gap register now includes `unavailable_data` with deterministic baselines
for every required display environment. Focused unavailable visual checks pass `4/4`, and the
complete board-guided matrix passes `48/48` with a valid manifest. This remains interim evidence
under `REF-STATE-VARIANTS`; no exact-build claim, mask, threshold, or acceptance criterion changed.
Acceptance flexibility used: board/state-variant substitution only.

### 2026-08-09 unavailable freshness visual-oracle coverage

Added `unavailable_data` to the application-shell gap register and captured deterministic local
baselines for all four required display environments. The focused unavailable visual run passes
`4/4`; the existing delayed and complete visual checks remain green. This strengthens the
interim `REF-STATE-VARIANTS` oracle without claiming exact pinned-build styling. Acceptance
flexibility used: board/state-variant substitution only; no masks, thresholds, or criteria changed.

### 2026-08-09 delayed freshness visual-oracle coverage

Added `delayed_data` to the application-shell gap register and captured deterministic local
baselines for all four required display environments. The focused delayed visual run passes
`4/4`, and the complete board-guided matrix passes `44/44` with a valid manifest. This strengthens
the interim `REF-STATE-VARIANTS` oracle; it does not close the gap or claim exact pinned-build
styling. Acceptance flexibility used: board/state-variant substitution only; no masks, thresholds,
or criteria changed.

### 2026-08-09 point-in-time analysis integration verification

Closed a stale acceptance record in the top-down analysis section. The Docker-backed
integration routes for breadth, relative rotation, and point-in-time relative-strength now run
successfully in the current stack: `5/5` focused tests passed (with only two known third-party
NumPy/nautilus deprecation warnings). This verifies the shared `as_of` cutoff across membership,
bars, breadth history, rotation tails, and ratio legs. No acceptance flexibility or visual
criterion changed; exact/unrepresented visual, live-entitlement, native-monitor, endurance, and
remaining scope gaps remain open.

### 2026-08-09 Market Gauge delayed-state styling correction

The normalized `delayed` freshness state now receives warning styling instead of the green current
data color. Focused Market Gauge/freshness coverage passes `22/22`, rebuilt authenticated `F8w-a`
passes `1/1`, full frontend Vitest passes `652/652`, type-check/build pass, and the four-environment
board-guided visual matrix passes `40/40`. No baseline, mask, threshold, or parity criterion changed.
Acceptance flexibility used: none; exact/unrepresented visual, entitlement, native-monitor,
endurance, and remaining scope gaps remain open.

### 2026-08-09 Market Gauge freshness and browser-boundary fixes

Market Gauge now shares the canonical workstation freshness normalizer and exposes a normalized
state key for CSS, eliminating the backend/frontend `coverage_limited` versus `coverage-limited`
split. Focused Market Gauge/freshness coverage passes `21/21`, rebuilt authenticated `F8w-a`
passes `1/1`, full frontend Vitest passes `651/651`, type-check/build pass, authenticated
Chromium passes `69/69`, and the four-environment board-guided visual matrix passes `40/40`.
No baselines, masks, thresholds, or parity criteria changed.

The broad browser run also caught and repaired two localized, recoverable boundary races: repeated
pop-out churn now has idempotent cleanup when a child already closed during a revision refresh
(`F8f` repeated `5/5`), and the explicit logout diagnostic allowance now covers the paired
`Authentication required` page error (`F5` `1/1`). The full matrix passes `69/69` after both
corrections. Acceptance flexibility used: none; the composite board remains the working authority
for represented states, while exact/unrepresented visual, live-entitlement, native-monitor,
endurance, and remaining scope gaps remain open.

### 2026-08-09 top-down lineage field correction

The industry-row model no longer labels an ETF holdings composition date as `freshness`; it now
uses `as_of`, with an `As of` column definition where that model is consumed. The compact rendered
Industries surface remains a count/list by design. Corrected authenticated deep drilldown `F8e.1`
passes `1/1`, the adjacent top-down/relative-strength slice passes `4/4`, and existing full
frontend/browser/visual/build evidence remains green. Acceptance flexibility used: none.

### 2026-08-09 freshness contract normalization

Backend analysis uses `coverage_limited` while the workstation shell uses the documented
`coverage-limited` state. The shared freshness mapper now normalizes both spellings, and the
frontend state contracts explicitly admit delayed and coverage-limited responses. Relative Rotation
and top-down lineage metadata use the same human-readable formatter. Focused freshness/rotation
coverage passes `22/22`, authenticated `F8i-e` passes `1/1`, full frontend Vitest passes `649/649`,
authenticated Chromium passes `68/68`, and the board-guided visual matrix passes `40/40` with no
baseline/mask/threshold changes. Acceptance flexibility used: none; the visual-board, live-
entitlement, native-monitor, endurance, and remaining scope gaps remain open.

### 2026-08-09 canonical-only workstation security-master boundary

New-workstation autocomplete, symbol and expression resolution, comparison legs, and
industry-proxy selection now pass `canonical_only=true`; provider fan-out remains available only
through the legacy/default endpoint behavior. Focused canonical-boundary integration tests pass
`2/2`, frontend contract tests `19/19`, rebuilt F7/F8d/F8d-SPX `3/3`, backend `1,284/1,284` at
`79.49%`, frontend Vitest `643/643`, and authenticated Chromium `67/67`; the final runtime-log
audit is clean. Acceptance flexibility used: none. This closes a backend/frontend contract gap,
not the remaining exact-build/unrepresented visual, entitlement, native-monitor, endurance, or
other product-scope gaps.

### 2026-08-09 SPX proxy fallback and indicator persistence correction

The requested SPX/SPY workflow now attempts the canonical official SPX identity and falls back to
the configured canonical SPY tradable proxy only when SPX is unavailable, with an explicit footer
notice rather than silently relabelling SPY. Rebuilt-stack browser regression passes `1/1`. The
same audit exposed and fixed a concurrent indicator-persistence `MissingGreenlet` 500 by reading
the authenticated identity without implicit async ORM IO; focused Docker-backed integration
tests pass `2/2`. The authoritative backend gate passes `1,282/1,282` at `79.43%` coverage, the
complete authenticated Chromium matrix passes `67/67`, and the rebuilt run's service-log audit
is clean. Acceptance flexibility used:
deterministic 404 fixture for unavailable free-source SPX entitlement; the live entitlement gap
remains open and SPY is never represented as official SPX.

### 2026-08-09 focused symbol-entry and stale-state visual corrections

The fix-first shell audit found that async initial SPY hydration could append to a focused
autocomplete query, rendering `SPYSP`. User edits now invalidate the initial selection generation
and focused drafts are preserved until explicit selection/submission. The browser test asserts
the input value is `SP` and all four focused-search baselines were regenerated from that live
render. The stale-data capture now waits for the Refresh control to settle, preserving the visual
threshold rather than masking a transition.

The complete board-guided matrix passes `40/40` across 1920×1080 and 2560×1440 at 100% and 125%
display scale; authenticated Chromium passes `66/66`; frontend Vitest passes `643/643`;
type-check and production build pass. Acceptance flexibility used: composite-board references
for represented states and deterministic canonical autocomplete fixtures; exact-build/
unrepresented, provider-live, native-monitor, bounded-endurance, and remaining product-scope
gaps remain tracked.

### 2026-08-09 chart-control and OHLC-readout overlap correction

The fix-first visual audit found that chart Compare, Plots, and Templates controls could overlap
the uPlot OHLC readout. The chart surface now reserves a dedicated top control strip, and the
visual harness includes explicit control/readout and control/control geometry oracles. Prior
baselines were preserved; only affected shell/stale/partial states were refreshed. Rebuilt-stack
acceptance passes: board-guided visual `32/32` across 1920×1080 and 2560×1440 at 100% and 125%
display scale; authenticated Chromium `66/66`; frontend Vitest `643/643`; type-check and
production build. A timestamped two-minute service-log audit found no HTTP 500, traceback,
MissingGreenlet, UniqueViolation, critical, or fatal signatures. Acceptance flexibility used:
the documented composite-board track for represented states; exact-build/unrepresented,
provider/live-entitlement, native-monitor, bounded-endurance, and remaining product-scope gaps
remain tracked.

### 2026-08-09 default ratio self-reference correction

The fix-first audit found the default Relative Strength surface could display `SPY/SPY` while
the intended benchmark/equal-weight comparison is `SPY/RSP`. A shared benchmark-leg helper now
derives non-self-referential legs for benchmark, sector, and constituent drill-downs. Unit ratio
coverage passed 3/3, rebuilt authenticated F8e passed 2/2, the complete frontend suite passed
643/643 with type-check/build, and the visual harness explicitly waits for the deterministic
SPY/RSP state before screenshot capture. The full four-environment board-guided matrix passes
32/32. Acceptance flexibility used: the documented composite-board track for represented states;
exact-build and
unrepresented reference gaps remain tracked.

### 2026-08-09 backend revalidation after fixture isolation

The authoritative combined Docker-backed backend gate passed `1,282/1,282` with `79.43%`
coverage and 86 known third-party deprecation warnings after the deterministic authenticated
visual-fixture correction. The branch-scoped stack is healthy; no new functional or data-contract
regression was exposed. No acceptance flexibility was used. Exact/unrepresented visual,
provider/live-entitlement, native-monitor, bounded-endurance, and remaining product-scope gaps
remain tracked.

### 2026-08-09 deterministic visual-fixture isolation

The authenticated Playwright fixture now resets the default factory workspace after login, so
persisted ratio/link/layout state from another visual project or rerun cannot alter a baseline.
The previously variable stale-freshness case passes 3/3 at 1440×900/125%; the full board-guided
matrix passes 32/32 across all four required environments. The complete authenticated Chromium
matrix passes 65/65, frontend Vitest 642/642 across 91 files, type-check/build pass, and runtime
logs are clean of critical signatures. No acceptance flexibility was used for this fix; the
composite-board policy remains the visual authority for represented states, while exact-build
and unrepresented reference gaps remain tracked.

### 2026-08-09 unified Python editor across Study Lab and Code Library

Primary Study Lab now uses the shared `PythonSourceEditor` rather than a separate plain
textarea/autocomplete implementation. This keeps SDK suggestions, signatures, normalization,
keyboard completion, outside-pointer dismissal, and ARIA listbox semantics consistent across
programmable surfaces. Focused Study Lab/editor coverage passed `21/21`; full frontend Vitest
passed `642/642` across 91 files; type-check and production build passed. No acceptance flexibility
was used. Rebuilt authenticated F8g/F9i passes `2/2`, and the complete authenticated Chromium
matrix passes `65/65`; explicit visual, provider-live, native-monitor, endurance, and other scope
gaps remain. The post-run stack log audit found no HTTP 500, traceback, MissingGreenlet,
UniqueViolation, critical, or fatal signatures.

### 2026-08-09 Anfield provider route re-audit

The configured Regents Park ADFI holdings route was re-probed and returned HTTP 404. Public search
material still describes the former ADFI product/holdings page, while Anfield’s current corporate
site reports its transition into Horizon. No replacement executable first-party route was verified;
the adapter remains explicitly unpromoted with route-failure provenance and conditional SEC
fallback. This is an external provider gap, not an acceptance relaxation or goal-wide blocker.

### 2026-08-09 combined backend coverage gate

The Docker-backed combined backend unit/integration gate passed `1,282/1,282` with `79.43%` line
coverage, above the 75% threshold. This current evidence covers the API, provider, research,
sandbox, and persistence paths. No acceptance flexibility was used; the documented visual,
provider-live, hardware, endurance, and remaining product-scope gaps remain open.

### 2026-08-09 keyboard-completable Python authoring

The shared Code Library editor now supports keyboard selection/completion of unified SDK
suggestions: ArrowUp/ArrowDown, Enter/Tab, Escape, and explicit ARIA active-option state. Focused
editor/CodeLibrary coverage passed `7/7`, full frontend Vitest `642/642`, type-check/build,
rebuilt F9h `1/1`, and the four-environment board-guided visual matrix `32/32`. The visual result
uses the documented board track for represented states; no masks, thresholds, or baselines
changed, and exact-build/unrepresented states remain explicit gaps.

### 2026-08-09 board-guided visual revalidation after Python editor integration

The serialized visual manifest passed validation and the complete board-guided matrix passed
`32/32` across 1920×1080 and 2560×1440 at 100% and 125% display scale. Shell, Study Lab,
loading, provider-error, blocked-pop-out, stale, partial-coverage, and validation-error states
all passed without changing masks, thresholds, or baselines. This uses the documented composite
board track for represented states; exact-build/unrepresented gaps remain open and are not claimed
as exact V25 approval.

### 2026-08-09 unified Python source editor and interaction hardening

Code Library creation and immutable-version editing now use the reusable `PythonSourceEditor`,
bringing unified SDK suggestions, signature hints, and deterministic source normalization to the
reusable Python surface while retaining canonical validation and output-contract reconciliation.
The rebuilt F9h flow exposed a real suggestion-popover hit-testing defect; only suggestion buttons
remain interactive and outside pointer input dismisses the list, so Create and other form controls
remain usable. Focused coverage passed `6/6`, full frontend Vitest `641/641`, type-check/build,
rebuilt F9h `1/1`, and runtime logs were clean. No visual thresholds, masks, or acceptance
criteria changed; exact/unrepresented visual states and the other documented external gaps remain.

### 2026-08-09 Python output-contract preflight

Reusable Python asset validation now checks the source's observed output contracts against the
selected asset kind/version before persistence. Valid Python with an incompatible output is shown
as a source-positioned mismatch and is not submitted to the backend. Focused CodeLibraryTool
coverage passed `4/4`, full frontend Vitest `639/639`, type-check/build passed, and rebuilt
authenticated F9h passed `1/1`. No acceptance flexibility or visual thresholds changed.

### 2026-08-09 Python Library validation parity

The reusable Python Library now uses the canonical `/code/validate` contract before creating an
asset or saving an immutable version. It renders source-positioned diagnostics and clears prior
validation when code changes, matching Study Lab's validation behavior. Focused component coverage
passed `3/3`, full frontend Vitest `638/638`, type-check/build passed, and rebuilt authenticated
F9h passed `1/1` through Python Library → EasyScan → alert creation. No acceptance flexibility or
visual thresholds changed.

### 2026-08-09 screen-inventory completeness correction

The repository-controlled pop-out recovery path now requires every Window Management API screen
record to expose complete usable bounds before treating the inventory as authoritative. A partial
or malformed inventory preserves persisted coordinates, avoiding recovery from incomplete display
data. Focused geometry coverage passed `7/7`, full frontend Vitest `637/637`, type-check/build
passed, and the rebuilt pop-out/cross-window subset passed `9/9`. No visual thresholds, masks, or
acceptance criteria changed; native physical monitor validation remains a separate external gap.

### 2026-08-11 expanded bounded endurance

The workstation lifecycle guard now permits explicitly requested churn up to 500 rounds while
remaining hard-bounded. A rebuilt-stack two-popout soak at `TC2000_POP_OUT_CHURN_ROUNDS=250`
passed `1/1` in `4.8m`, preserving source tool/canvas/chart counts after every round and staying
within the available Chromium heap ceilings. This strengthens, but does not replace, indefinite
soak evidence; native physical multi-monitor placement and other external gaps remain explicit.

### 2026-08-11 screen-aware pop-out recovery

The pop-out path now optionally uses authoritative Window Management API screen bounds after the
synchronous child-window creation. Saved geometry is retained when it intersects any available
display; geometry for a disconnected display is recovered to the current display only when a
complete screen inventory is available. Unsupported or denied API paths preserve persisted
coordinates. Geometry tests passed `6/6`, rebuilt pop-out flows `9/9`, and complete authenticated
Chromium `65/65`; no visual criteria or masks changed. Native physical monitor placement remains
an external hardware validation gap.

### 2026-08-11 cross-window symbol and timeframe links

The real pop-out link contract is now browser-verified for symbols and timeframes as well as
cursor timestamps. The parent workstation changes to `QQQ` and weekly timeframe while the floated
primary chart follows through the canonical link bus. Focused acceptance passed `1/1`; the complete
authenticated Chromium matrix passed `65/65`. No product code, visual threshold, mask, or criterion
changed. Native physical monitor placement remains explicitly separate from browser-level evidence.

### 2026-08-11 cross-window linked cursor

The workstation now has browser-level evidence for the full cross-window cursor contract. The
primary chart is floated into a real child window, its uPlot cursor is moved there, and the parent
Relative Strength chart follows the selected bar timestamp through BroadcastChannel/storage
propagation. Focused acceptance passed `1/1`; the complete authenticated Chromium matrix passed
`64/64`. No product code, visual threshold, mask, or acceptance criterion changed. Functional
cross-window cursor behavior is closed; exact-build/unrepresented visual states and native
multi-monitor placement remain explicit gaps.

### 2026-08-11 linked crosshair and pop-out lifecycle acceptance

The browser parity matrix now contains a real linked-cursor proof: the primary seeded uPlot chart
publishes its bar timestamp and the linked Relative Strength uPlot follows it. The first assertion
was corrected from `style.left` to uPlot's actual CSS-transform/`u-off` contract; focused crosshair
acceptance passed `1/1`, and the complete authenticated Chromium matrix passed `63/63`. The
repeated float/close test now waits for both factory chart surfaces to finish legitimate lazy
initialization before recording its canvas baseline, then isolated and complete-matrix lifecycle
checks pass. No product criterion, visual threshold, or mask was relaxed. Exact-build and
unrepresented reference states remain explicit gaps.

### 2026-08-11 active-symbol history and shell baseline review

The authenticated workstation now exposes a compact persisted active-symbol history menu backed by
the existing bounded recent-instrument store. It supports direct selection, clearing, ARIA menu
semantics, and outside/Escape dismissal. A browser-discovered initial-route edge case was repaired
by recording successful explicit and industry-proxy selections at the selection boundary while
retaining the linked/cross-window watcher. Focused shell tests passed `14/14`, full frontend
Vitest `634/634`, type-check/build passed, rebuilt history acceptance passed `1/1`, and the complete
authenticated Chromium matrix passed `62/62`.

The first board-guided visual run correctly identified one stale 1080p/100 application-shell
baseline from an older unavailable/loading capture. After review, only that deterministic local
snapshot was regenerated; masks and thresholds were unchanged. The complete four-environment
board-guided visual matrix passed `32/32`. Board-guided visual acceptance was used for represented
states; `REF-SHELL-V25` and other unrepresented exact-build states remain explicit gaps.

### 2026-08-11 Impact Shares holdings-route correction

Impact Shares' official NACP holdings CSV is now a native provider route rather than a fallback
classification. The shared parser accepts the issuer's `% Net of Assets` header spelling, and the
route/parser plus registry tests pass. The opt-in live probe remains separately tracked because
the current Python environment cannot resolve the issuer hostname.

### 2026-08-11 Fairlead provider-identity correction

The Fairlead/Cary Street TACK holdings route is now exposed consistently for both the legal
issuer identity (`cary_street`) and the discovered ETFDB alias (`fairlead`). Both resolve to the
verified issuer-page/FilePoint adapter with distinct provenance labels; the alias is no longer
treated as a StockAnalysis fallback. The complete adapter unit suite passes `453/453`, and route
registry/invariant checks pass. A live HTTP probe remains opt-in and separately tracked.

> **Controlling acceptance note:** Read this historical/evidence matrix together with
> `docs/tc2000-acceptance-governance.md`. The 190-image composite board is the working visual
> authority for represented states and `npm run test:visual:board` is the normal visual gate.
> Older entries that say strict `required_missing` blocks the whole visual acceptance refer to the
> superseded policy; they remain useful evidence notes only. Unrepresented or ambiguous states
> remain explicit gaps and are not silently passed.

## Current evidence snapshot — 2026-08-10

2026-08-11 complete-flow follow-up: the rebuilt authenticated Chromium `flows.spec.ts` matrix
passed `60/60` after the persisted Study Lab activation repair. Post-run service logs had no
critical backend/runtime signatures; no visual or capability relaxation was used.
The board-guided visual matrix independently passed `32/32` across the four required display
environments with no baseline, mask, or criterion changes.

2026-08-11 follow-up: the rebuilt F9i browser flow reproduced and closed a persisted Study action
activation defect. The global Study action now selects an existing Study Lab Golden Layout window
instead of leaving it hidden behind another tab. Research Results detail failures also expose an
explicit retry state. Focused workspace/Results coverage is `48/48`, full frontend is `632/632`,
type-check/build pass, and rebuilt F8g/F9i passes `2/2`; no visual or capability relaxation was used.

2026-08-10 follow-up: Persisted Research Results rerun/cancel mutations reconcile authoritative
responses through the shared research-runs cache, keeping linked and popped-out Results tools in
sync. The two-root regression and full frontend suite (`629/629`) pass; no visual or capability
status changed.

### 2026-08-10 issuer route re-probe

DFTT passed the targeted live route check; ADFI's former Regents Park page now returns HTTP 404.
The adapter preserves route-failure provenance and attempts SEC reconstruction when identifiers are
available; the standalone live probe has none. ADFI remains an explicit provider-route gap rather
than an invented native success. No acceptance flexibility used.

### 2026-08-10 complete fresh-stack authenticated matrix

All 63 executed non-visual/performance Playwright flows passed on the fresh branch stack; the 32
visual projects were intentionally skipped by this command and are covered separately by the
`32/32` visual gate. Logs contain only expected provider-exhaustion freshness warnings. No
acceptance flexibility used.

### 2026-08-10 fresh-stack runtime audit

The branch-scoped Compose stack is healthy and serves the frontend/backend; authenticated F8d/F9h/F8g
smoke flows pass `3/3`. Logs contain only the documented provider-exhaustion freshness warning and
no unexpected backend/runtime error signatures. No acceptance flexibility used.

### 2026-08-10 current-head backend gate

The complete Docker-backed unit/integration gate passed `1,277/1,277` at `79.43%` coverage,
above the 75% threshold. This validates the current supporting backend head; no acceptance
flexibility used.

### 2026-08-10 board-guided visual gate rerun

The complete four-environment board-guided visual matrix passed `32/32` with elevated Chromium
permissions after a non-elevated macOS browser-launch permission failure. Manifest validation,
visual baselines, and gap-state oracles passed without mask or criterion changes; no acceptance
flexibility used.

### 2026-08-10 EasyScan duplicate-scan reconciliation

EasyScan now reconciles duplicate scan creation through the shared saved-screener query and keeps
the post-run refresh contract intact. Focused tests pass `10/10`, full frontend Vitest `628/628`,
type-check/build pass, and authenticated F9h passes `1/1`; no acceptance flexibility used.

### 2026-08-10 unified durable research-run cache

Study Lab persisted hydration now uses the platform-wide `research-run` cache namespace shared by
chart Python plots. Fresh cached runs are reused, while active polling remains explicitly fresh.
Focused Study Lab tests pass `17/17`, full frontend Vitest `627/627`, type-check/build pass, and
authenticated F8g/F9i pass `2/2`; no acceptance flexibility used.

### 2026-08-10 Study Lab durable-run query coordination

Persisted Study Lab runs hydrate through the shared run query namespace, deduplicating concurrent
linked roots without changing explicit durable polling or empty-response diagnostics. Focused
Study Lab tests pass `16/16`, full frontend Vitest `626/626`, type-check/build pass, and rebuilt
authenticated F8g/F8o/F8q pass `3/3`; no acceptance flexibility used.

### 2026-08-10 workstation symbol-search query coordination

Active and popped-out workstation shells share normalized search results while preserving debounce
and stale-request behavior. Focused tests pass `12/12`, full frontend Vitest `625/625`, type-check
and production build pass, rebuilt authenticated F8d passes `1/1`, with no acceptance flexibility
used.

### 2026-08-10 watchlist condition-result query coordination

VirtualWatchlist roots share per-screener condition-result summaries while retaining active
universe identity in the cache key. Focused tests pass `50/50`, full frontend Vitest `625/625`,
type-check and production build pass, rebuilt authenticated F8y passes `1/1`, with no acceptance
flexibility used.

### 2026-08-10 EasyScan result-history query coordination

Linked EasyScan roots share per-scan retained history, with explicit post-run invalidation to keep
new results fresh. Focused tests pass `9/9`, full frontend Vitest `625/625`, type-check and
production build pass, rebuilt authenticated F9h passes `1/1`, with no acceptance flexibility used.

### 2026-08-10 EasyScan condition query coordination

Linked EasyScan roots share saved-condition hydration and mutation invalidation through the common
library query namespace. Focused tests pass `9/9`, full frontend Vitest `625/625`, type-check and
production build pass, rebuilt authenticated F9h passes `1/1`, with no acceptance flexibility used.

### 2026-08-10 relative-rotation diagnostic visibility

Backend row-level coverage and insufficient-history warnings are now visible in the relative
rotation table with exact diagnostic tooltips. Focused tests pass `6/6`, full frontend Vitest
`624/624`, type-check and production build pass, rebuilt authenticated F8e passes `1/1`, with no
acceptance flexibility used.

### 2026-08-10 reusable canonical instrument query contract

Canonical instrument hydration is centralized in `fetchCanonicalInstrument`, preserving normalized
identity and shared-cache behavior for workstation consumers. Contract tests pass `2/2`, full
frontend Vitest `623/623`, type-check and production build pass, rebuilt authenticated F8e passes
`1/1`, with no acceptance flexibility used.

### 2026-08-10 canonical instrument query coordination

Isolated workstation tools share normalized canonical-instrument hydration across linked and
popped-out roots while retaining generation guards. Focused tests pass `2/2`, full frontend
Vitest `623/623` across 90 files, type-check and production build pass, rebuilt authenticated F8e
passes `1/1`, with no acceptance flexibility used.

### 2026-08-10 relative-strength query coordination

Linked RatioUPlot roots share parameterized relative-strength legs while preserving timestamp
intersection, hidden-document suspension, stale-response protection, and uPlot reuse. Focused
tests pass `9/9`, full frontend Vitest `621/621`, type-check and production build pass, rebuilt
authenticated F8e passes `1/1`, with no acceptance flexibility used.

### 2026-08-10 relative-rotation query coordination

Linked RelativeRotationTool roots share parameterized group-analysis reads while preserving uPlot
lifecycle and stale-response guards. Focused tests pass `5/5`, full frontend Vitest `620/620`,
type-check and production build pass, rebuilt authenticated F8e passes `1/1`, with no acceptance
flexibility used.

### 2026-08-10 coverage query coordination

Linked CoverageSummaryTool roots share canonical coverage and keyed OHLCV-range assessments.
Focused tests pass `4/4`, full frontend Vitest `619/619`, type-check and production build pass,
rebuilt authenticated F8i-d passes `1/1`, with no acceptance flexibility used.

### 2026-08-10 instrument-note query coordination

Linked InstrumentNoteTool roots share canonical note hydration and autosave cache updates.
Focused linked-tool tests pass `7/7`, full frontend Vitest `618/618`, type-check and production
build pass, rebuilt authenticated F8s passes `1/1`, with no acceptance flexibility used.

### 2026-08-10 instrument-alert query coordination

Linked InstrumentAlertsTool roots share global screener and instrument alert/history hydration;
mutations invalidate the shared alert root while stale-relink guards remain intact. Focused alert
tests pass `6/6`, full frontend Vitest `617/617`, type-check and production build pass, rebuilt
authenticated F11 passes `1/1`, with no acceptance flexibility used.

### 2026-08-10 combo-list query coordination

Personal workstation roots share combo-list hydration and invalidate the result after save/delete.
Full frontend Vitest passes `616/616`, type-check and production rebuild pass, rebuilt F8y passes
`1/1`, and no acceptance flexibility was used.

### 2026-08-10 chart-template query coordination

Chart windows share chart-template hydration and invalidate the shared result after mutations.
Full frontend Vitest passes `616/616`, type-check and production rebuild pass, rebuilt F9c passes
`1/1`, and no acceptance flexibility was used.

### 2026-08-10 condition-column screener cache correction

Condition-column creation now participates in the shared saved-screener query and invalidates it
after Boolean scan creation/run. Rebuilt F8v passes `1/1`; full frontend Vitest remains `615/615`,
type-check and production build pass, and no acceptance flexibility was used.

### 2026-08-10 shared asset and membership recovery correction

Python asset hydration is coordinated through a single Vue Query contract across programmable
surfaces, and the watchlist membership menu now resolves the current source from the context row
when a workspace snapshot is stale. Full frontend Vitest passes `615/615` across 89 files,
type-check and production rebuild pass, and rebuilt F8y passes `1/1`. No acceptance flexibility
was used; the transient F8y failure remains recorded as a repaired localized regression.

### 2026-08-10 virtual-watchlist shared-library hydration

Saved screener and column-set hydration now share Vue Query results across docked and popped-out
watchlist roots. Column-set save/delete invalidation is covered by the component contract. The
focused VirtualWatchlist suite passes `49/49`, full frontend Vitest passes `613/613`, type-check
passes, and rebuilt authenticated F8y passes `1/1`. No acceptance flexibility was used.

### 2026-08-10 relative-strength alignment correction

The reusable uPlot ratio surface now intersects timestamps across all requested numerator/
benchmark legs before rendering. A focused mismatched-calendar regression passes (`8/8` ratio
component tests), the full frontend suite passes `613/613`, rebuilt authenticated F8e passes `1/1`,
and the board-guided four-environment matrix passes `32/32`. This prevents null/union calendar
points from implying a valid ratio observation. No acceptance flexibility was used.

- Backend unit/integration gate: `1,277/1,277` passed at `79.43%` coverage (75% required), with
  86 known third-party deprecation warnings only.
- Frontend Vitest: `613/613` passed across 88 files; `vue-tsc --noEmit` and production build passed.
- Authenticated E2E: `63/63` passed, including workstation, Study Lab, pop-out, legacy, and
  performance flows; the visual-project subset is separately gated by the board command below.
- Production frontend build: passed.
- Board-guided visual matrix: `32/32` passed across the four required display-scale environments
  using the serialized shared-state Playwright configuration.
- 10,000-row virtual-watchlist invariant: all logical rows retained, fewer than 100 DOM rows
  rendered, virtual total height preserved.
- Remaining explicit gaps: unrepresented/ambiguous exact-build visual states, opt-in live-provider
  probes, native physical multi-monitor placement, and endurance beyond bounded stress.

## Latest continuation evidence — top-down taxonomy seeding

The curated US taxonomy now has direct unit coverage for exact industry-proxy candidates and the
async startup seeding path. The regression proves that repeated startup does not duplicate members,
only already-known canonical instruments are attached, provenance remains `curated_top_down_taxonomy`
with `proxy_verified`, and the logical SPX identity continues to expose SPY as a clearly labelled
tradable proxy. Focused taxonomy tests pass `2/2`; analysis helper edge-case tests pass `12/12`;
the full backend unit suite passes `981/981` at `69.93%` coverage. The combined gate below is the
authoritative backend coverage threshold; strict visual/provider/sandbox/multi-monitor/parity gates
remain independent.

The explicit combined backend gate is now implemented as `make test-backend-coverage`. It runs all
unit and Docker-backed integration tests together and requires 75% coverage; the latest run passed
`1,262/1,262` at `79.59%`. This closes the backend coverage threshold while retaining the honest
unit-only `69.93%` diagnostic.

The 100-round Chromium workstation lifecycle soak also passes `2/2` in `1.9m`, with bounded
simultaneous-popout tool/canvas/chart/heap state. This strengthens browser performance evidence;
it does not substitute for native multi-monitor placement or an indefinite-duration soak.

## Latest continuation evidence — live resource pressure

`ops/probe-research-runner-resources.sh` now provides a repeatable bounded deployment probe. The
branch-scoped runner reports the required 768 MiB/one-CPU/128-PID/no-network/read-only/non-root
boundary; a 1 GiB allocation is killed by the cgroup, a 70 MiB `/tmp` write is rejected by the
64 MiB tmpfs, and eight concurrent 128 MiB allocations contained three child failures without a
runner restart. This strengthens the live sandbox evidence but does not replace the required
sustained cancellation, orphan, crash-recovery, and long-duration matrix.

## Latest continuation evidence — 2026-08-05T12:10:00Z

The isolated research runner now clears stale cancellation and progress sentinels when a
worker-restart orphan is requeued. This prevents a recovered job from being canceled by the
previous worker's state. The focused runner suite passes `64/64`, and the full backend unit
suite passes `972/972`. Live resource-pressure, long-duration performance, and exact-build
visual approval remain independent open gates.

The provider-neutral frontend boundary is now regression-tested in the backend unit suite:
the primary `frontend/src` tree may not embed provider identifiers, credentials, direct provider
URLs, or fallback-order logic. The guard passes as part of the current `973/973` unit result.

The Docker-backed research/code API integration suite also passes `18/18`, covering queued run
creation/cancellation, declared dataset materialization, batch limits/results, durable progress,
and structured artifacts.

This is the implementation-facing matrix for the controlling plan. `Blocked` means
the source reference is required before visual acceptance; it is not an approval.

| Surface | Implementation ownership | Reference state | Functional status | Required evidence |
| --- | --- | --- | --- | --- |
| Application shell and US Top Down | `WorkstationView.vue` | Board-guided; stale-state gap | Implemented and regression-covered | interaction/E2E, four-environment board baseline, freshness gap oracle |
| Workspace tabs and factory layouts | `workspaces.py` | Board-guided; state-variant gaps | Implemented and regression-covered | persistence/reset, layout traversal, geometry and visual baselines |
| Docking/pop-outs | `WorkspaceLayoutHost.vue` | Board-guided; blocked-popout gap | Implemented and regression-covered | pop-out/recovery, Golden Layout lifecycle, serialized visual matrix |
| Chart | `UPlotChart.vue` | Board-guided; loading/error gaps | Implemented and regression-covered | uPlot lifecycle, transforms, state oracles, visual baselines |
| Watchlists/columns/filters | workstation tools + batch APIs | Board-guided; partial-coverage gap | Implemented and regression-covered | 10k virtual-list, editor/scan/gauge tests, partial-state oracle |
| Top-down sector/breadth workflow | `analysis.py`, market groups | Functional; taxonomy/provenance gaps tracked | Implemented and regression-covered | point-in-time, taxonomy, relative-strength, and E2E drill-down evidence |
| Unified Python | `/code`, runner | N/A | Implemented and regression-covered | immutable single-output reuse, named structured-output adapters, sandbox escape/resource suite |
| Study Lab | `/research`, `StudyLabView.vue` | Original surface; state gaps | Implemented and regression-covered | reproducibility/artifact/rendering suite plus local editor baseline |
| Notes and alerts | `/notes`, existing alerts | Functional; exact visual state gap | Implemented and regression-covered | user isolation and linked-tool tests |
| Excluded capabilities | `tc2000-capability-stubs.md` | N/A | Documented | primary-menu absence test |

Rows are complete for their implemented functional scope when the referenced deterministic
functional evidence passes. Board-guided visual states use the accepted composite board and
local baselines; unrepresented or ambiguous states remain explicit gaps in the visual manifest
and cannot be described as exact V25 approval. See `docs/tc2000-acceptance-governance.md` for
the controlling completion and flexibility rules.

Unified-Python version reuse pins compatible single-output Study Lab promotions directly to the
original immutable `CodeVersion`: scalar studies can be consumed as columns, Boolean studies as
EasyScan/alerts/signals, and series studies as chart plots. Multi-output studies retain the
`study` contract; named scalar/series/Boolean/event artifacts can now be promoted through an
immutable typed adapter carrying `output_name`, so the Python source is not rewritten and the
isolated runner evaluates only the selected artifact for batch consumers.

## Current runtime evidence (2026-08-05)

Continuation revalidation at `2026-08-06T20:20:50Z` also passes the complete frontend Vitest suite
(`593/593`), `vue-tsc --noEmit`, the production Vite build, Alembic head validation for
`eb1f2a3c4d5e`, Python bytecode compilation, and `git diff --check`. Named structured-output
promotion is covered by an immutable `output_name` adapter; source rewriting is not required.
The subsequent complete backend gate passed `1,275/1,275` at `79.41%` after the live migration
was applied to the retained branch stack.
The targeted combo-list persistence regression also passes `1/1` under Python 3.12, confirming
canonical union/intersection/exclusion storage independently of the frontend helper coverage.

Latest continuation evidence:

- Market-analysis refresh coordination is leader-owned across browser windows: only the elected
  persistence leader runs periodic Vue Query refreshes, while followers hydrate initially and consume
  successful refresh events through BroadcastChannel/storage with in-flight deduplication.
- Focused workspace-store tests pass `33/33`; full frontend Vitest is `574/574` across 87 files;
  TypeScript and production build pass; the exact rebuilt-stack non-visual Playwright set passes
  `34/34` in 1.3 minutes.
- Follower refresh-event regression coverage now passes as part of the focused store suite (`34/34`);
  the full frontend suite is `575/575` across 87 files. The follower path is verified to refresh from
  a leader event without publishing a competing periodic refresh.
- Study Lab now includes an explicit editable `Event frequency and occurrences` factory study that
  emits uPlot-compatible frequency bars plus linked occurrence artifacts; its component suite passes
  `12/12`.
- Global `Ctrl+wheel` symbol traversal is now implemented at the workstation shell with editor
  suppression, watchlist event isolation, and an honest canonical-benchmark navigation fallback
  during unavailable/initial group data. Rebuilt-stack browser acceptance passes `35/35`, including
  the dedicated F8k interaction test.
- The seasonality factory now covers both month and day-of-month behavior, with separate frequency
  bars and observation tables emitted by editable unified Python; Study Lab component coverage remains
  `12/12`.
- The same seasonality study now also emits day-of-week bars and observation tables using a bounded
  Gregorian calculation, completing the month/day/calendar seasonality starter without introducing
  another language or renderer.
- The source was audited against the actual AST policy and no longer uses forbidden `lambda`; the
  Study Lab regression suite explicitly enforces this sandbox-compatible shape.
- The Gregorian weekday mapping is also covered explicitly (`0 = Saturday`), preventing shifted
  weekday labels in the calendar-seasonality result.
- A backend cross-layer regression now validates the exact source emitted by `StudyLabTool.vue`
  through the production AST validator (`1/1`), preventing frontend-only source drift.
- That regression also executes the source in the isolated runner against deterministic dates and
  verifies all three calendar bars plus weekday observations; the focused backend source suite is
  now `2/2`.
- The same cross-layer test now validates all 11 named factory sources against the production AST
  policy; the focused backend factory-source suite is `3/3`.
- The matrix now executes all 11 sources with their actual single-dataset or structured aggregate
  contracts and deterministic prepared data; the focused backend suite is `4/4`.
- Relative-strength history is now a named source rather than an inline literal, bringing the full
  catalog to 12 named sources under the same cross-layer validation and runtime matrix.

Continuation evidence from the current branch checkpoint:

- Full frontend Vitest is `573/573` across 87 files; TypeScript and production build pass.
- The authenticated Chromium flow now includes a real traversal of all eight required factory
  layouts (`US Top Down`, `TC Classic`, `Drill Down`, `Sector by Year`, `1 Chart`, `4 Timeframe`,
  `Fundamentals`, and `Study Lab`). The traversal passes, and each layout renders without the
  recovery state or title/symbol/action header collisions.
- The complete authenticated flow is now `32/32` after that coverage addition; the existing
  four scaled visual projects also report zero core overlap issues. Screenshot comparisons remain
  intentionally unapproved because three local baselines differ by 1–2% and the exact-build V25
  reference manifest is still `required_missing`.
- The live research runner has explicit seccomp plus the existing no-network/read-only/non-root
  boundary. A queue-level three-minute soak processed `360/360` uniquely submitted jobs with no
  missing jobs, zero restarts, and no probe residue. Heavy-study performance remains separate.
- The authenticated multi-window performance guard opens two simultaneous pop-outs, initializes
  both tools, propagates `XLB` to both, closes them, and verifies stable source tool/canvas counts
  in `6.0s`; the complete
  non-visual Playwright suite is `34 passed, 4 skipped`. This is browser-level evidence, while
  multi-monitor placement and long-duration memory behavior remain separate gates.

The Docker-reachable backend regression is now green after fixing CoinGecko's missing-key
diagnostic lifecycle: `1247 passed`, `348 skipped`, and no failures with explicit asyncio auto
mode. The eight async background-task tests execute and pass; the skipped set is the
credential/network-gated live-provider coverage. The provider warning is now once per provider
instance rather than a process-global side effect.

The live-stack visual interaction run reached all four required display-scale projects. The
header/chart overlap assertions passed in every project; one existing 1080p/100% snapshot was
unchanged, while three unapproved local snapshots exceeded the temporary `0.5%` diff threshold
(1–2%) and remain blocked pending approved V25 references. The dedicated uPlot 100,000-point
browser performance test passes in `863ms` without replacing the chart element.

The isolated-runner security configuration was verified on the live container: effective UID
`10001`, no network, read-only root, no host binds, all capabilities dropped, `no-new-privileges`,
128-process limit, 768 MiB container memory, one CPU, and a constrained no-exec `/tmp` tmpfs.
The focused AST/runner/deployment security slice passes `94/94`; the Docker-reachable backend
suite also passes with the async runner tests enabled.

The branch-local PostgreSQL migration ledger also passed a reversible integrity check: Alembic
downgraded `ea0f1a2b3c4d` to `e9f0a1b2c3d4`, upgraded back to `ea0f1a2b3c4d`, and reports the head
revision afterward.

The authenticated Chromium flow suite now explicitly verifies that unsupported domains
(`trading`, `brokerage`, `options`, `news`, ratings, earnings, and full financial statements)
are absent from the primary workstation menu. The complete flow suite passes `31/31`, including
pop-outs, top-down drill-down, Study Lab, legacy routes, and that exclusion assertion.

The post-pop-out-change frontend verification is green: Vitest `572/572`, `vue-tsc
--noEmit`, and the production Vite build all pass. The suite includes the new active-display
origin and persisted-geometry coverage. This is functional/build evidence only; it does not
close the required Version 25 visual-reference gate or the remaining broad performance,
security, provider, and soak audits.

An opt-in live ETF-holdings audit was rerun against current public issuer routes: `339 passed`,
`1 skipped`, and `7 failed` of 347. Failures are source-state regressions rather than silent
fallbacks: IronHorse timed out; Neos returned 403; Tuttle, Anfield, and Thor returned 404;
Toews returned 500; and Donoghue Forlines returned 503. These adapters remain unpromoted for
current-source acceptance until their routes are repaired or explicitly demoted with verified
SEC fallback evidence.

The production refresh fallback contract is covered separately: issuer-route failure/refresh
paths and SEC reconstruction tests pass `12/12` in the focused API slice. Thus native-route live
failures are not treated as healthy data, while the refresh service retains its documented SEC
fallback behavior.

Pop-outs now restore persisted `left`, `top`, `width`, and `height` geometry from the
serializable workspace window style, capture move/resize changes while open, and stop
polling after close. Geometry is clamped to usable minimum dimensions, and unchanged polls
do not schedule snapshot writes. Focused geometry/store coverage is `35/35`; rebuilt
authenticated pop-out flows F8b/F8f/F8h/F8i pass `4/4`. This closes persisted single-window
geometry behavior; authenticated F8j now verifies the persisted style through the live
`/workspaces/default` API. First-time placement uses the current display's available origin
when the browser exposes it, while saved coordinates remain authoritative. Multi-monitor OS
placement and long-duration memory soak remain separate acceptance gates.

The free-source identifier probe now includes a live repository-level OpenFIGI check: the
unauthenticated public mapping endpoint resolved `SPY` to three stable FIGI records (FIGI,
composite FIGI, and share-class FIGI) through `OpenFigiProvider`. This does not imply quota
or redistribution guarantees for every OpenFIGI use; the entitlement registry and the
remaining credentialed provider probes stay authoritative.

Chart surfaces now use a shared canonical OHLCV request coordinator. Identical instrument,
timeframe, range/limit, transform, adjustment, and local/basket requests coalesce while
in flight; successful results are retained briefly for linked-window reuse and failures are
not cached. The coordinator is covered by coalescing, expiry, and failure-recovery tests;
full frontend Vitest is `568/568`, rebuilt Chromium is `29/29`, and backend logs are clean.

The targeted sandbox/resource and code API slice passes `112/112` with Docker access. It
covers AST safety, forbidden imports/process/filesystem/network/reflection paths, isolated
runner limits and cancellation, immutable code versions, queued Study Lab jobs, and the
10,000-cell batch boundary. Only two existing Nautilus/NumPy deprecation warnings remain.

The browser diagnostic contract also covers the logout boundary explicitly: F5 grants only
the bounded 401 responses caused by clearing authentication while in-flight queries settle;
all other 401s remain fatal. The focused logout test and complete authenticated flow pass
`29/29`.

The dense workstation status bar now consumes the canonical technical snapshot freshness
contract rather than treating the newest local bar as an unqualified cache timestamp. It
renders `Current · canonical`, `Delayed`, `Stale · cached`, `Partial coverage`, `Coverage
limited`, `Fetching`/`Backfilling history`, or `Unavailable`. `Current` is explicitly scoped
to the canonical dataset's entitlement/freshness policy and does not imply consolidated
real-time quotes; `Delayed` is accepted only when an entitled provider reports that semantic.
The mapping is exhaustively unit-tested and the rebuilt authenticated Chromium flow remains
`29/29`.

The live shared-volume runner protocol has also been exercised for cancellation: a uniquely
named 10,000-cell prepared-universe batch was claimed by the non-root runner, observed a
cancellation sentinel during execution, returned structured `canceled` / `batch_canceled`
output with bounded completed-cell artifacts, and left the runner healthy. Probe artifacts
were explicitly removed afterward. A separate bounded concurrency probe then queued twelve
independent jobs while a second runner process raced the normal worker; all twelve were
claimed exactly once, completed successfully, and left no queued or running artifacts. This
closes the shared-volume multi-process claim/recovery slice; broader namespace and sustained
resource-exhaustion stress is now covered by a bounded three-job pressure probe: each
70-million-element allocation returned `memory_limit`, was processed, and left no queued or
running residue. Full namespace/seccomp adversarial stress and long-duration soak evidence
remain open.

The rebuilt branch stack now passes the complete authenticated Chromium flow (`29/29`),
including Study Lab validation, isolated Python execution, and structured metric rendering.
The full backend unit suite passes (`965/965`, 69.83% coverage); the detached-auth rollback
regression is covered directly and backend logs are clean for 500s, tracebacks, pool leaks,
SQLAlchemy warnings, and unexpected errors. The research timestamp-default migration
`ea0f1a2b3c4d` has passed a PostgreSQL downgrade/upgrade round trip. A fresh disposable
PostgreSQL 16 audit against current HEAD also upgraded the complete chain to `ea0f1a2b3c4d`,
verified `watchlist_item.flagged` as `NOT NULL DEFAULT false`, downgraded one revision,
re-upgraded to head, and re-verified the invariant before the container was removed.
Current-head migration round-trip acceptance is closed.
The complete Docker-backed integration suite passes `281/281` with 54 existing dependency
warnings; its clean acceptance invocation is `--no-cov` because the integration-only subset
does not meet the repository-wide coverage threshold by itself.

The VirtualWatchlist Python polling path also rejects empty batch responses before they reach
Vue Query, preserving an explicit error contract for columns and Boolean conditions. This is
covered by the focused 46-test suite and the full 555-test frontend suite; the rebuilt
Chromium flow remains 29/29 with clean backend diagnostics. The same no-undefined query
boundary is now enforced for Market Gauge, retained EasyScan results, Research Results,
condition columns, and indicator batches; focused workstation coverage is 61 tests and the
full frontend suite is 555 tests across 84 files.

The browser acceptance harness now waits for expected unavailable-data responses before
diagnostic assertions and excludes only those documented API 404/409 responses from teardown
attachments. All four required display-scale visual probes also assert that core tool headers
and chart toolbar/surface rectangles do not overlap; each passes those geometry checks before
the exact-build screenshot gate rejects its unapproved baseline.

Raw API transport errors are not rendered in the dense workstation footer. The shell maps
common 401/403/404/409 and 5xx failures to concise recovery-oriented status text while
retaining the original diagnostic in the status tooltip. The regression covers 401/403/404/409
and 5xx mappings and is covered by the full frontend suite (`555/555`), production build, and
rebuilt Chromium flow (`29/29`).

The deep top-down browser flow now also focuses the constituent virtual list and traverses to
the next canonical member with `Space`, asserting that the linked active symbol changes without
a route transition. The complete authenticated flow remains `29/29`.

Golden Layout persistence no longer treats its observational visible-key list as a destructive
close operation. Explicit close actions remain the only path that removes a serialized tool;
this prevents transient/incomplete layout events during repeated pop-outs from deleting the
source window. The store regression and a ten-cycle browser lifecycle check cover the boundary,
including stable source canvas and browser-page counts. The full authenticated flow remains
`29/29`, including simultaneous independent pop-out recovery, and the post-run backend/runner
log audit is clean.

This is functional/runtime evidence only. The strict visual gate still rejects the required
`application-shell-default/default` state because the manifest remains `required_missing`;
discovery-only online media cannot be promoted without exact-build continuity, measurements,
permission/storage review, and human approval. Provider-live credentials, adversarial pressure
and cancellation, 10,000-row/multi-window performance, and the
complete cross-surface parity matrix likewise remain open.

## Cancellation-safe streaming evidence

The screener NDJSON route is an explicit lifecycle boundary rather than a normal
request-scoped database dependency. Authentication uses a short-lived detached session;
the route performs its ownership lookup in a separate short-lived session; and the stream
owns a dedicated session from the injectable `get_stream_session_factory` (production
returns `AsyncSessionLocal`) that always rolls back and closes in its body generator.
Rollback and close run in shielded child tasks so an ASGI disconnect cannot interrupt
asyncpg cleanup. The normal request dependency uses the same helpers for other routes.
SQLAlchemy pool termination records are filtered only when their exception is an
`asyncio.CancelledError`, preserving ordinary pool failures as errors.

Evidence: `test_screener_stream_lifecycle.py` covers route ownership and already-cancelled
cleanup; `test_database_cleanup_logging.py` proves the narrow logging filter distinction;
the full backend unit suite passed `926` tests; the Docker-backed integration suite passed
`281` tests; isolated F12 and the complete authenticated Chromium flow passed `26/26`; and
the fresh rebuilt-stack backend error/warning audit found no cancellation traceback, pool
leak, `InterfaceError`, `SAWarning`, or unexpected error.
This is runtime reliability evidence, not Version 25 visual approval; strict visual
acceptance remains controlled by the required reference manifest.

## Isolated research handoff and resource-pressure evidence

The Compose backend and isolated research runner now share explicit `/jobs` and `/results`
volume paths. Enqueue prepares the private volume directories with shared permissions so
the non-root UID 10001 runner can atomically claim backend-created jobs and write result and
progress files; job files are mode 0666 and no provider credentials are mounted. The runner
maps in-process `MemoryError` to a structured `memory_limit` diagnostic rather than an empty
runtime error.

Live evidence: a backend-enqueued 70-million-element allocation was claimed, returned the
`memory_limit` diagnostic, produced a processed sentinel, and left the capped runner
running. Full backend unit coverage passed 964 tests, research API integration passed 20,
deployment/research-job/runner tests passed, and all probe artifacts were removed. This
closes the fresh-volume handoff/path defect and one real memory-pressure case; orphan-job
cleanup after process termination, cancellation under pressure, and broader namespace/
multi-process stress remain required acceptance work.

The basic orphan recovery path has now been exercised against the same volume: a
`.running` payload was requeued by runner startup, completed as a typed scalar artifact,
and cleaned up while the capped non-root process remained healthy.

Read-only authentication lifecycle evidence: `GET /auth/me` and `GET /auth/settings` use
the detached identity-session factory, avoiding a request transaction that outlives response
serialization; writes remain request-scoped. Auth integration passed 15 tests, the full
backend unit suite passed 964, and the rebuilt authenticated Chromium flow passed 26/26 with
no pooled-connection or SQLAlchemy warning in the fresh backend/runner/worker log window.

## Authentication-session lifecycle evidence

The authenticated legacy-route matrix exposed a separate session-lifetime defect around
identity lookups during navigation and pop-out work. Normal `get_current_user` now shares the
ordinary request-scoped `get_db` session, so FastAPI owns one transaction and one finalizer for
the route instead of creating a second identity connection and manually closing it before the
generator finalizer runs. The detached streaming variant uses an injectable
`get_auth_session_factory`, opens one short-lived identity session, and closes it explicitly
before the response body starts. Cleanup helpers also accept the synchronous compatibility
adapters used by controlled tests without scheduling a non-awaitable return value.

Evidence: the ten-surface `/legacy/*` Chromium matrix passed without login redirects or fatal
overlays; backend unit coverage passed `926` tests; Docker-backed integration passed `281` tests;
the rebuilt complete Chromium flow passed `26/26` in `45.5s`; frontend Vitest passed `547` tests;
TypeScript, production build, and diff checks passed; and a fresh backend-log audit found no
garbage-collector/non-checked-in connection, `SAWarning`, `InterfaceError`, cancellation trace,
provider-runtime error, or unexpected warning. This closes the observed auth-session leak class;
it does not alter the strict V25 visual gate or broader performance/security/parity gates.

## Repeated pop-out lifecycle evidence

The browser acceptance matrix now includes repeated and simultaneous lifecycle regressions:
F8f floats and closes the same workstation tool ten consecutive times while retaining source
canvas/page counts, and F8h keeps two concurrent pop-outs independently recoverable. The
complete authenticated flow file passes `28/28` and the rebuilt-stack backend error/warning
audit is clean. This closes only the covered source-tool/pop-out lifecycle cases; multi-monitor
placement, long-running memory behavior, and broader workstation performance remain open.

Top-down asynchronous reads now use per-surface generation guards across market groups,
group snapshots, breadth/history, technical summaries, holdings, industries, constituent
snapshots, and proxy rankings. A rapid linked-symbol or timeframe change cannot let a late
response replace the current metrics, rows, or error state. Workspace-store regressions cover
stale SPY/XLK and daily/weekly analysis races; browser and full cross-window acceptance remain
open.

The deterministic browser fixture now seeds 520 adjusted D1 business-day bars for the benchmark,
sector, proxy, and constituent paths, point-in-time XLK/SMH/SOXX holdings, and explicit
Semiconductors/Systems Software classifications. The rebuilt deep acceptance flow reaches
XLK → Semiconductors → SMH → NVDA and verifies the linked ratio label follows the selected
constituent. RatioUPlot reloads its aligned series when mounted-tool symbol, benchmark, or
timeframe props change; auto-ratio rendering also derives from the current linked symbol while
the persisted configuration catches up. This is functional evidence only; strict pinned-build
visual approval remains controlled by the reference manifest.

Persisted Golden Layout snapshots from the pre-v8 workstation format are migrated at the
layout boundary: legacy numeric `width` values are converted to v2 `size` fractions only for
column nodes, while arbitrary tool-state width fields remain unchanged. The migration has a
focused regression test and is covered by the full frontend suite; this prevents existing
users' saved proportions from being silently discarded after the factory-layout upgrade.

Shared tool-window chrome now renders human-readable link-group labels and color swatches for
both symbol and timeframe links while retaining canonical group IDs in emitted events. This
keeps yellow wildcard and grey isolation discoverable in docked and pop-out tools without
coupling persistence to display text.

Current implementation evidence (not completion): the isolated Study Lab runner now
supports a typed `histogram` artifact with deterministic numeric buckets, the factory
positive-close study exposes current/longest/average/shortest streak metrics,
point-in-time forward-return rows, symbol-linked streak occurrences, and completed-
streak lengths for that distribution, and both
primary Study Lab result surfaces render the artifact through a uPlot bar overlay. The
runner now also emits typed numeric `scatter` artifacts, rendered by a dedicated uPlot
point-cloud surface with aligned x/y validation, and bounded rectangular `heatmap`
artifacts rendered by a native matrix surface. Focused runner, validation, Study Lab,
and persisted-results tests pass; visual parity remains blocked until the required
approved Version 25 references exist.

The shared Python validator and Study asset contract now recognize `scatter` and
`heatmap` output methods, so these structured artifacts survive validation and can be
reused from the same unified language rather than being runner-only extensions.
Study Lab structured outputs now also include typed categorical/numeric `bar` artifacts
and aligned lower/upper `range` bands with an optional center series. The isolated runner
validates finite values and dimensions, persists the native payload, and the active Study
Lab, persisted Research Results, and dashboard renderers display them through uPlot
components with in-place updates and teardown. This completes the remaining first-pass
native bar/range result contracts; visual acceptance still requires approved V25 baselines.

Historical chart pagination now uses a bounded, timeframe-aware repair window when the
local page is short. It anchors the request at the oldest cached bar (or a minimum cold
bootstrap window) with a small overlap, rather than fetching from the 1970 epoch; pure
service tests cover both warm-tail and cold-start calculations.

Explicit historical range reads now detect bounded edge gaps and calendar-aware internal
gaps. USD instruments use a deterministic local XNYS daily session calendar (weekends,
Good Friday, observed federal-market holidays, and Juneteenth) so expected closures are
not fetched as missing bars while a missing weekday is repaired independently. Instruments
without an explicit supported calendar retain the conservative interval-based fallback.
Focused service tests cover internal repair, the no-fetch weekend/holiday cases, and the
missing-weekday case.

The reusable `ohlcv_coverage` service now owns the provider-neutral readiness decision
for a requested instrument/timeframe/range. It distinguishes `ready`, `partial`,
`missing`, and latest-window `stale` states, returns bounded repair slices, and accepts an
injected clock for deterministic evaluation. The existing market-data read path uses the
planner while retaining provider access and persistence at its boundary; future chart,
scan, alert, and research preflight callers can consume the same contract without
reimplementing freshness logic.

Authenticated `/coverage/instruments/{symbol}/ohlcv` now exposes that assessment as a
canonical frontend contract. Callers provide timeframe, range, adjustment, and historical
versus latest mode and receive status, local bounds, bar count, bounded missing slices,
and an explanation with canonical-database provenance; reversed ranges and unknown
instruments are structured errors, and provider names/fallback order are never returned.

The primary workstation Coverage tool now consumes this range contract directly. Its
serializable controls retain timeframe, UTC-normalized start/end dates, historical/latest
mode, and split-adjustment choice in the workspace window configuration. A range check is
explicitly user-triggered, rejects reversed or incomplete ranges before dispatch, ignores
late responses after a symbol change, and renders ready/partial/missing/stale status,
covered bounds, bar count, explanation, and every bounded missing slice. The tool still
loads aggregate canonical coverage separately, so a readiness check never causes provider
fan-out or silently changes the active symbol.

The isolated image also installs pinned NumPy/Pandas wheels at build time and exposes
only restricted `np`/`pd` facades to user code. File/external-data methods are rejected
by source validation; NumPy/Pandas values are normalized before artifact persistence.
The rebuilt image import check reports NumPy `2.1.3` and Pandas `2.2.3`.

Study datasets now preserve the complete canonical OHLCV shape rather than reducing the
isolated input to closes: aligned `opens`, `highs`, `lows`, `closes`, nullable
`volumes`, `vwaps`, and timestamps are materialized for the declared instrument and
benchmark. The unified `market` namespace exposes `open`, `high`, `low`, `close`,
`volume`, `vwap`, and aligned `ohlcv()` access, while retaining the compatibility rule
that close-only hand-authored fixtures remain valid. Missing fields produce structured
runner diagnostics and never trigger provider access.
The same namespace exposes declared timestamps, session labels, and canonical instrument
metadata (identity, currency, active/synthetic state, and primary identifier) so studies
can make explicit metadata/session decisions without importing application models or
calling providers.
When a benchmark is materialized, the same namespace exposes explicit
`benchmark_*` accessors for aligned OHLCV, timestamps, sessions, and metadata; an absent
or unavailable benchmark returns a structured runner diagnostic rather than silently
falling back to the primary instrument.
The unified language also exposes a bounded set of ordinary Python composition builtins
(`len`, `sum`, `min`, `max`, `range`, collection constructors, and related pure helpers)
in both validators and the isolated runner. Dunder names remain rejected, so this
improves normal Python expressiveness without widening host, filesystem, network, or
dynamic-execution access.
Run configurations are now injected as a JSON-only `parameters` mapping in both single
instrument and prepared-universe batch execution. Parameter values stay inside the
isolated process and are included in the run payload/reproducibility input; malformed
non-object parameters fail explicitly before user code runs.
The API now treats each immutable code version's parameter schema as authoritative: it
merges declared defaults, validates required/type/enum/range/unknown-key constraints,
and rejects invalid runs before dataset materialization or sandbox enqueue.
The same gate runs when assets are created, imported, or versioned, so invalid defaults
cannot be persisted as immutable code versions in the first place.
Prepared-universe Study Lab runs now have a structured path: `output_contract: study`
executes once over the declared, provider-free `market.universe()` datasets, allowing
ranked tables, distributions, dashboards, and other typed aggregate artifacts. Structured
event outputs may identify any symbol in the declared universe and remain constrained to
that point-in-time prepared dataset; they cannot introduce undeclared symbols. Scalar and
Boolean watchlist/condition batches retain their bounded per-instrument cell contract.
Completed Study Lab runs with exactly one validated scalar, series, or Boolean output
contract can now be promoted without copying mutable run state: scalar results create a
reusable Python watchlist column, series results create a reusable chart plot, and Boolean
results create an EasyScan condition with an optional screener alert. The promotion keeps
the immutable source, parameter schema, timeframe, and canonical-data contract. Polymorphic
`study` runs remain research-only until the author explicitly supplies a single-contract
asset, avoiding ambiguous promotion of a dashboard or mixed artifact set. Focused
StudyLabTool coverage exercises the scan and alert paths; full visual and acceptance status
remains in progress.
The active Study Lab run panel also exposes snapshot and latest-data reruns through the
canonical research rerun API; queued responses return to the shared polling coordinator,
while the immutable code version and run configuration remain unchanged.
The primary editor now ships editable factory templates for consecutive positive closes,
consecutive negative closes, moving-average participation, and relative-strength history.
Selecting a template replaces only the draft source/name and clears stale validation/run
state; editing the source switches the selector to Custom Python, preserving normal Python
freedom without creating a second language.

Top-down drill-down correction: selecting a verified industry ETF proxy from the
industry surface now activates the canonical proxy symbol across the blue link group,
loads its bars and technical snapshot, updates the automatic ratio target, and retains
the selected sector/industry context. The proxy therefore behaves as an analysis target
(`SMH` within `XLK`/Semiconductors, for example) rather than a cosmetic table selection
that leaves linked charts on the prior instrument. Focused pop-out binding coverage
passes; exact-build visual and full end-to-end acceptance remain open.

Top-down cell provenance correction: benchmark, sector, constituent, and verified
industry-proxy row adapters now retain canonical per-cell warning messages from the
analysis response. Virtualized watchlists display the warning text for null values,
so insufficient history, unavailable comparisons, and coverage exclusions remain
visible at the cell where they occur instead of becoming silent dashes. Focused
virtual-watchlist coverage passes; broad visual and acceptance gates remain open.

Breadth drill-down correction: the breadth tool now exposes a canonical universe
selector (`S&P 500 sectors` or `US benchmarks`), separate Above and Below controls for
each 20/50/200-MA aggregate, and corresponding passing/failing members as linked rows.
Changing the universe loads its group snapshot plus current/historical breadth through
the local analysis APIs. Selecting a row publishes its canonical symbol to workstation
charts without a route change; the historical uPlot breadth series remains visible
alongside the drill-down. Daily/weekly/monthly timeframe and split-adjustment controls
are persisted and forwarded consistently to the group, snapshot, current-breadth, and
history requests. Focused workstation/watchlist/store coverage, TypeScript, and
production build pass; visual and full acceptance remain open.

Breadth analytics now also return canonical near-52-week-high/low, configurable
new-high/new-low, uptrend/downtrend, and aggregate moving-average-distance metrics,
with the request lookback echoed in the response. The workstation summary renders these
values with explicit unavailable states and shows metric-family coverage detail. The focused router suite and frontend store/
watchlist boundary pass; member-level high/low and trend metrics now power linked
advanced-statistic drill-downs with an in-place Pass/Fail toggle; Docker-backed integration
verification is still required.
Study Lab exposes a serializable comma-separated universe control; when populated it sends
canonical symbol selectors as `run_config.symbols` and displays the selected universe in
the run summary instead of silently using only the active symbol.
The authenticated research API now materializes that selector into a bounded canonical
dataset manifest, preserves requested order, and returns exact per-symbol exclusions for
unknown instruments or missing history before the isolated job is queued.
EasyScan result rendering now tolerates partial or malformed retained payloads: missing
match arrays and coverage metadata render as explicit zero/coverage-unavailable state
instead of throwing during a reactive update. Polling also treats missing result metadata
as non-terminal until a valid terminal status arrives.
Study Lab now exposes the same schema as generated controls, converts numeric and boolean
values before creating the immutable code version, and sends the resulting typed parameter
map with the run. The schema remains serializable in the workspace configuration boundary.
Editing or clearing the schema immediately updates that persisted window configuration, so
floating, reloading, or restoring the Study Lab does not silently discard its controls.
The editor also provides constrained cursor-word suggestions and inline signatures for
the supported SDK namespaces, plus a compact reference panel; suggestions only insert
ordinary Python source and cannot execute code or inject frontend content.

Unified Python assets now have lifecycle contracts for complete export/import, immutable
version-preserving clone, and reversible archive/unarchive operations. Each imported or
cloned version is revalidated against its asset kind and output contract before it is
persisted; user ownership and stable-key uniqueness remain enforced by the canonical API.
The primary workstation now exposes those operations through a dockable Python Library
tool with filtering, archived-state visibility, file import, JSON export, clone,
archive/unarchive, typed new-asset creation, and immutable new-version editing controls;
the component is covered by focused lifecycle and interaction tests. Editing always posts
a new validated version and never mutates an existing source record. New assets select a
surface kind and send the corresponding output contract through the same canonical API.

Python watchlist columns now carry an explicit serializable timeframe (defaulting to the
owning watchlist's linked timeframe when first added). The column editor exposes the
timeframe selector, reruns the isolated prepared-universe batch after a change, and sends
the selected timeframe in both `run_config` and the dataset manifest; restored columns
without a timeframe remain backward-compatible through the linked-timeframe default.
The same explicit timeframe contract now applies to persisted Python Boolean conditions:
the filter editor exposes it, stores it with the condition binding, and includes it in
the prepared-universe evaluation request.

Python `plot` assets are now first-class chart plot targets. The Chart Plot Library loads
user-owned plot versions on demand, persists selected code-version/color/timeframe state
in the chart window, and the workstation evaluates those versions through the isolated
research API. Typed `series` artifacts are aligned to canonical chart timestamps and
passed to uPlot as native series; invalid, incomplete, or failed artifacts are omitted
without injecting arbitrary frontend code.
When the chart symbol, timeframe, or selected plot set changes, the workstation cancels
the prior Python plot runs and ignores late results by generation, preventing stale
research work from replacing the active chart.

The relative-rotation uPlot surface now updates `setData`/`setSize` in place during
resize and data refresh; it destroys the chart only during component teardown. A
dedicated regression test proves repeated resize callbacks do not create additional
uPlot instances.

Relative Rotation now exposes and persists its transparent inputs: market-group universe,
benchmark, timeframe, sampling cadence, split-adjustment mode, lookback, and tail length.
Those values are sent to the canonical analysis endpoint rather than being hidden
SPY/D1/20/10 constants; load generations prevent a late rotation response from replacing
a newer selection.

Relative Rotation also accepts a bounded sampling cadence (every 1–30 aligned observations)
and always includes the latest aligned observation. Sampling is persisted in factory and
user tool configuration, returned in the response, and used consistently for trend,
momentum, and tail calculations; the default cadence remains one observation.

Each rotation row now also returns transparent `heading` (degrees), `distance`, vector
`velocity`, a state `transition` when the latest sampled state changed, and consecutive
`time_in_state`. The companion table exposes those values alongside trend, momentum,
coverage, and tail length instead of implying proprietary rotation metrics. Every companion
column is sortable with null-safe ordering and a visible direction marker. The uPlot
rotation plane now draws each member's color-coded historical tail as a connected trail,
labels the Leading/Weakening/Improving/Lagging quadrants, and identifies the nearest tail point on
hover with symbol/date/coordinates, and emits the normal linked-symbol selection when a
hovered point is clicked; focused component coverage proves the interaction without
recreating the chart.

The Relative Rotation backend now accepts an optional point-in-time `as_of` and applies it
to both versioned market-group membership (`effective_at`/`known_at`) and local bars. The
response echoes the cutoff and provenance selection rule, rejects groups not known at the
requested time, and never uses future members or future observations in the ratio tail.
The current Docker-backed integration regression passes as part of the focused `5/5` analysis
matrix; the only output is two known third-party NumPy/nautilus deprecation warnings.

The same cutoff contract is now available on group snapshots, current breadth, and breadth
history. Sector ranking, equal-weight comparison, and breadth history can therefore be
replayed against a declared membership/bar cutoff, with shared provenance and coverage
metadata instead of silently mixing current membership with historical observations.

The canonical relative-strength ratio endpoint now accepts the same optional point-in-time
`as_of` cutoff and truncates both local series before intersecting timestamps. The response
echoes the cutoff, while the uPlot ratio component accepts an optional persisted cutoff for
historical drill-downs. Its compact `As of` control emits serializable tool configuration,
so docked and floated ratio windows retain the cutoff through workspace snapshots; current
views omit the parameter when the control is blank. The focused frontend contract and
Docker-backed route regression now pass; the route is covered by the focused `5/5` analysis
matrix. Ratio loads also use an active generation guard, so a late response from a prior
symbol/timeframe/as-of selection cannot replace the current ratio window; the focused component
suite covers that race.

Queued Python EasyScan runs now expose their isolated research-run cancellation
control in the primary workstation. Cancellation remains isolated to that run and
the result polling path reconciles the terminal `canceled` state.

The persisted Study Results browser exposes the same cancellation contract for
queued/running research runs, preserving the run list and selected result while the
isolated worker transitions to its terminal state.

The Market Gauge tool now uses the shared TanStack Vue Query cache for retained
EasyScan definitions and gauge snapshots. Selecting a scan fetches its canonical
local-database gauge, active visible gauges refresh on the configured freshness
interval or through an explicit Refresh control, and hidden tool surfaces/document
visibility suspend automatic requests. The dense tool chrome exposes the returned
freshness state, provenance, calculation version, and coverage-warning count. A
component regression covers selection, refresh, stale-data labeling, and lineage
display. This is functional evidence only; the Version 25 visual reference remains
unapproved.

The workstation shell now exposes a single deduplicated top-down refresh command. It
refreshes benchmark and sector memberships, sector rankings, current breadth, and
historical breadth together; concurrent callers join the same request set, the shell
shows an in-progress Refresh control, and an active workstation polls every five
minutes only while the document is visible. The store records the last successful
refresh time only when every shared input succeeds, while the existing response
freshness and coverage fields remain the source of truth for stale or partial data.

The workstation shell's five-minute refresh is now coordinated by the shared TanStack
Vue Query client rather than a component-owned interval. The query is keyed as
`workstation/market-analysis`, uses the store's deduplicated refresh promise as its
single query function, pauses while the document is hidden or the tool is a browser
pop-out, and resumes through the same cache when visibility returns. The explicit
Refresh control calls the query refetch path, so manual and scheduled refreshes share
the same request identity. A WorkstationView regression covers hidden-document pause,
visibility restoration, and the pop-out exclusion; TypeScript, production build, and
the full frontend suite remain green. This is functional polling evidence only; the
Version 25 visual reference remains unapproved.

The Add Tool registry now includes every implemented primary analysis surface that was
previously factory-only: Relative Rotation, Market Breadth, Technical Summary, Coverage,
and Instrument Report. Each uses a stable tool type and serializable configuration, while
excluded domains remain absent from the registry.

The benchmark watchlist now consumes the same canonical group snapshot as the sector
workflow. It displays SPY/RSP and other benchmark rows with 1D/1W/1M/3M/YTD/1Y
performance, `/ SPY` ratio, RSI, 52-week position, and volume-ratio columns, so the
cap-weighted versus equal-weight comparison is available before sector drill-down.
Its identity strip separately labels the logical S&amp;P 500, official `SPX` series, and
the currently used tradable `SPY` proxy; the UI never relabels proxy data as SPX.

ETF constituent snapshots now carry two explicit relative-strength cells when requested:
the constituent versus the selected sector/ETF benchmark and the constituent versus an
independently named market benchmark (the primary workstation supplies `SPY`). The
batch endpoint accepts `market_benchmark`, aligns both ratios to the same local bar
timestamp, returns structured missing-alignment warnings, and echoes both benchmark
identities. Constituent watchlists render both `/ XLK`-style and `/ SPY` columns rather
than forcing the user to leave the drill-down or manually reconfigure the ratio chart.
The same endpoint accepts an optional point-in-time cutoff. At a cutoff it admits only a
holdings disclosure whose composition date and `known_at` timestamp are both historical-
safe, truncates all comparison bars at that cutoff, and records the requested cutoff in
provenance; it never silently falls back to a current snapshot. The integration contract
has a dedicated regression for this selection rule.

The ETF industry composition, curated-proxy, and industry-constituent routes now apply the
same historical rule: an explicit `as_of` requires both composition date and non-null
`known_at` at or before the cutoff. Undated disclosures remain available to latest/current
views but cannot contaminate point-in-time research.

Group breadth now preserves the requested point-in-time cutoff separately from the latest
bar available in the returned data. Its `as_of` describes the latest usable observation,
while `universe_provenance.membership_as_of` remains the caller's cutoff in canonical UTC
wire format; this prevents a data-availability timestamp from replacing the historical
membership boundary used by the calculation.

Factory `Drill Down` and `Sector by Year` industry windows now use the selected ETF's
point-in-time industry composition rather than falling through to benchmark rows.
Industry selections publish the industry key into the linked drill-down, preserve
resolved/total constituent coverage, and expose verified proxy counts when available.
The `Sector by Year` sector window now consumes canonical calendar-year return cells
from the group snapshot (five bounded years, with explicit no-bars and insufficient-
history warnings) and renders those years as selectable percentage columns. This is
functional evidence only; the Version 25 visual reference remains unapproved.
All shared ranking snapshots now calculate `YTD` from the first available bar in the
current calendar year rather than treating 252 bars as a calendar boundary, and emit
an explicit insufficient-YTD warning when the year has fewer than two valid bars.
Fixed-period returns likewise return a structured zero-base warning rather than
dividing by zero, preserving valid cells and exact exclusion reasons in batch output.
The factory relative-strength chart is now explicitly auto-ratio-enabled: selecting
SPY/RSP, a sector, a constituent, or an industry proxy updates it to the relevant
benchmark relationship while custom expressions remain untouched.

The chart plot library now retains the linked-chart shortcut and adds explicit target
mode for copying an indicator plot to any other chart or watchlist window in the active workspace,
including isolated/grey-link charts. The copy operation clones parameters, style, and
timeframe locks without replacing the target symbol. A selected plot can also be copied
into a reusable indicator-threshold condition, an EasyScan created from that condition,
or an indicator alert for the active canonical instrument; each promotion preserves the
indicator parameters, chart timeframe, operator, threshold, and provenance metadata.
Watchlist targets persist indicator-column definitions in serializable workspace
configuration. The workstation loads each configured indicator in one canonical
`/analysis/indicator-batch` request per column over the local security master and bars,
returns cell-level warnings plus coverage, and renders numeric values in the same
virtualized column/filter editor with null-safe numeric sorting. Unknown instruments,
missing bars, unsupported indicators, and insufficient history remain explicit rather
than triggering provider fan-out. The same promotion flow can create an EasyScan
from the saved condition and bind it to a selected watchlist window as an active persisted
filter; later filter edits still use the shared integrated column/filter controls. Visual
approval remains blocked by the V25 reference manifest.
Indicator-column requests use the shared TanStack Vue Query cache keyed by the sorted
canonical symbol set, indicator parameters, timeframe, adjustment, and output, so
docked/pop-out watchlists reuse active results instead of fanning out duplicate requests;
the 30-second cache window is separate from historical chart polling.
When the active symbol set, timeframe, or configured indicator changes, obsolete
indicator queries are canceled through Vue Query and an `AbortSignal`-aware API client;
generation guards still prevent any already-returned response from replacing newer
cells.

Chart plots now expose a bounded versioned drag payload (`application/x-charting-platform-plot`)
containing only canonical indicator type, primitive parameters, timeframe, label, and source
window identity. The payload is validated before use and cannot carry executable frontend
content or uPlot state. Virtualized watchlists accept the payload as a drop target and persist
the resulting numeric indicator column through the owning workstation window; EasyScan accepts
the same payload as an editable technical-condition node in its shared condition tree. Focused
ChartPlotLibrary, VirtualWatchlistTool, EasyScanTool, and payload-validation tests cover the
source, both targets, malformed versions, unknown indicators, invalid timeframes, and bounded
payloads. EasyScan condition trees are also drag sources: dropping one into a watchlist saves
the canonical condition, materializes/runs an EasyScan through the existing local screener API,
and persists a Boolean column keyed by the screener result; the watchlist refreshes that result
through Vue Query and renders True/False/unknown cells with Boolean sorting. This is functional
drag/drop evidence; exact-build visual approval and full browser acceptance remain separate
gates.

Floated workstation tools now forward watchlist condition modes, Boolean pinning,
column grouping/stacking, arbitrary serializable configuration, and industry-proxy
selection back to the source shell. Pop-out startup hydrates the existing link-group
symbol without publishing a default `SPY` selection into the source workspace. Focused
watchlist Space/Shift+Space traversal stops at the list boundary, and a shared editor
target guard suppresses workstation and uPlot shortcuts inside native inputs,
contenteditable/code editors, and role-textbox search surfaces. Dedicated pop-out,
keyboard-boundary, symbol-preservation, and editor-target tests plus the full frontend
suite provide functional evidence; visual approval remains blocked by the manifest.

Workstation chart windows now expose persisted comparison symbols and feed normalized,
timestamp-aligned comparison series into the existing uPlot renderer. Comparison anchors
are explicit, missing timestamps remain gaps, and each target exposes a return summary;
the comparison utility has deterministic alignment and no-valid-anchor coverage tests.

Virtualized watchlists now support desktop-style plain, Ctrl/Meta, and Shift selection
while retaining canonical row activation. A multi-selection exposes a Compare action;
the workstation routes it to the first non-ratio chart and persists up to six comparison
symbols without changing the active symbol. Component coverage proves selection semantics
and the full frontend suite remains green. Arrow/Space traversal and Ctrl+wheel now also
update the selection model, while filtering prunes symbols that are no longer visible;
the pop-out binding test proves the comparison event reaches the persisted chart config.
This is functional evidence only; the Version 25 visual reference remains unapproved.

Virtualized watchlist rows now expose a wired desktop context menu for opening the row's
chart, comparing it with the active symbol, opening symbol notes or alerts, and copying
the canonical ticker. Actions are routed through `WorkstationView` for docked and floated
tools; no context-menu item is a dead visual control. Focused component and pop-out
binding tests cover the menu and shell routing. This is functional evidence only; the
Version 25 visual reference remains unapproved.

The integrated column editor now persists per-column display overrides alongside the
existing visibility, order, grouping, stacking, and Boolean-pinning settings. Users can
rename a column and set a bounded pixel/fraction/percentage track width without changing
the canonical field key or row identity; every workstation watchlist, including personal
lists, uses the same serializable configuration path. Focused virtual-list coverage proves
the override events and restored header rendering; visual approval remains blocked by the
V25 reference manifest.

Numeric columns additionally expose persisted percent-versus-number formatting and bounded
decimal precision, including indicator and Python-derived columns, so dense ranking tables can
be tuned without changing their canonical values.
Numeric cells also receive automatic positive/negative/zero color classes while Boolean and
warning cells retain their explicit state colors.

The same editor now supports direct drag-and-drop ordering in addition to its explicit
left/right controls. Dragging emits the shared visible-column configuration, so saved
column sets and floated/docked watchlists retain one ordering contract; focused virtual-
list coverage proves the reorder event.

Personal watchlist item order is now persisted through
`POST /watchlists/{watchlist_id}/items/reorder`. The endpoint requires the complete item
set, assigns contiguous positions, rejects duplicate or incomplete IDs, and refuses
managed or locked lists. The Pinia watchlist store applies the order optimistically and
restores the prior order if persistence fails. Docker-backed watchlist integration and
store regression coverage prove the contract; the primary workstation's managed market
groups remain source-ranked and are not incorrectly presented as manually reorderable.

The primary workstation now exposes a first-class personal `WatchList` tool in its tool
library. It loads user-owned lists through the canonical watchlist store, persists the
selected list ID in the serializable workspace window configuration, renders symbol/name/
last/change columns through the same 10,000-row virtualized table, and publishes row
selection into the linked-symbol bus. Unlocked personal lists expose HTML drag ordering;
managed and locked lists remain visibly non-reorderable. Editable lists also expose
canonical symbol insertion and a context-menu removal action; locked/managed surfaces do
not expose either mutation. The focused virtual-list suite covers source-item-ID
preservation during drag/drop and the explicit removal boundary; visual approval remains
blocked by the V25 reference manifest.

The same context menu now exposes explicit personal-list membership actions. Any
workstation list can copy a canonical row into a selected unlocked personal list; an
editable personal list can move its row by adding it to the destination first and removing
the source item only after the destination accepts it. Current/source and locked targets
are disabled, and the action carries canonical instrument and destination IDs rather than
ticker-only state. Focused virtual-list coverage proves both copy and move events.
The same menu can expand canonical membership inspection, showing every personal list
whose stored instrument IDs contain the selected row and identifying the current source;
it does not infer membership from ticker text.

Watchlist items now also have a durable user flag. The authenticated item PATCH contract
persists `flagged` independently of membership locks, personal rows render the marker, and
the context menu toggles Flag/Unflag only when a canonical source item exists. Reloaded
watchlists retain the state, and copied lists preserve flags for retained items.

The personal WatchList tool now exposes a derived `Flagged Items` source alongside named
personal lists. It deduplicates flagged canonical instruments across the user's personal
lists, retains the originating watchlist and item IDs for linked context-menu actions,
disables membership-mutating controls that have no valid source list, and allows a flag to
be removed through the same authenticated PATCH contract. The derived view is persisted as
the serializable `watchlist_id: "flagged"` selection and refreshes from the canonical
watchlist store, so it remains consistent across reloads and pop-outs. Component coverage
now proves the flagged marker, preserved source item identity, and explicit Unflag action;
visual approval is still blocked by the V25 reference manifest.

The same WatchList source selector now supports user-owned combo lists. A combo is stored
as a versioned `combo_list` library item with canonical source watchlist IDs and explicit
union, intersection, and exclusion sets; it never evaluates ticker text or silently
materializes a new membership list. The editor loads, creates, updates, and deletes these
definitions through the authenticated library API, while derived rows retain the first
participating source item for linked selection, copying, and flag actions. Empty or
unavailable source lists produce an empty, explicit result rather than a provider fan-out.
The focused helper suite covers union/intersection/exclusion, intersection-only seeds,
canonical deduplication, deterministic source metadata, and quote projection. Visual
approval remains blocked by the V25 reference manifest.

Virtualized watchlist condition and Python batch requests now carry both a request
generation and a linked-universe generation. Changing the active universe invalidates
late results, starts evaluation for the new rows, and prevents old matches, progress,
errors, or cancellation state from filtering or annotating the replacement list. A
focused regression resolves the old saved-condition request after the new universe and
proves that the new rows remain unfiltered by stale matches.

The same tool now supports creating and renaming user-owned lists in place. The selected
list name and ID remain serializable workspace state, while managed/locked rename paths
are disabled and backend `409` conflicts are surfaced as explicit recovery text rather
than silently overwriting another window's change. Store and full-workstation regression
coverage remain functional evidence only; visual approval is still blocked by the V25
reference manifest.

Personal list management also exposes copy and confirmed deletion for editable lists.
Deletion selects the next remaining user-owned list only after the canonical delete
request succeeds; locked and managed lists cannot be deleted. A failed or conflicting
delete returns an explicit failure, leaves the local list and selection unchanged, and
surfaces recovery text rather than fabricating success.

Watchlist mutations now publish a `BroadcastChannel` invalidation event. A floated tool
that adds, removes, reorders, creates, renames, copies, locks, unlocks, seeds, deletes, or
reorders lists causes other workstation windows to reload the canonical watchlist cache,
so docked and pop-out surfaces converge without sharing non-serializable Vue state. When
`BroadcastChannel` is unavailable, the same event uses the browser storage-event fallback;
both paths have direct store regression coverage.

Linked Notes and Alerts tools now guard every symbol-scoped load and mutation with a
view-generation token. A slower response for a previously selected instrument cannot
overwrite the newly linked instrument, leave its loading state stuck, or apply a stale
alert mutation to the new symbol. Focused race regressions cover both tools; visual
approval remains blocked by the V25 reference manifest.

The primary Alerts tool also lists saved EasyScan alerts alongside price and indicator
alerts, with the same pause/resume, repeat, rearm, delete, and user-scoped mutation behavior;
this makes scan-entry/exit alerts visible from the shared alert workstation surface.
The backend screener-alert integration contract now covers create/list/pause/repeat/rearm/delete
and cross-user read/update isolation. The test is Docker-backed and remains environment-blocked
when the current runner cannot access the Docker socket.
Global EasyScan alerts are also loaded before an instrument identity is available, so the
primary alert surface does not lose scan-entry/exit state during workstation startup or
empty-symbol recovery.

Alert notifications now use authenticated, user-scoped WebSocket delivery. The screener
engine targets the correct user instead of calling the nonexistent legacy manager symbol,
and the frontend passes its access token to the socket and renders scan entry/exit events.
Unauthenticated legacy/test sockets retain only the explicitly broadcast compatibility path;
production alert evaluators no longer broadcast one user's alert payload to every client.
The frontend also accepts both the current `kind` and older `alert_kind` payload keys, so
indicator notifications cannot be misclassified as price alerts during compatibility windows.
The application now opens the socket only while the auth store is authenticated and closes it
on logout, preventing an anonymous pre-login connection from surviving into the user session.
Screener entry/exit firings are persisted as user-scoped `screener` history events with the
instrument, scan, direction, and run snapshot, so the existing alert history and instrument
filter APIs retain scan events alongside price and indicator firings.

The workstation shell and shared tool-window chrome now consume one global token sheet for
font stack, shell/window/control surfaces, borders, accents, state colors, density, and core
heights. The values mirror the current measured implementation and remain explicitly reviewable
against the approved four-environment V25 reference pack rather than being scattered literals.

The shared chart store applies the same generation boundary to instrument metadata,
indicator configuration, OHLCV pages (including infinite-history backfill),
transformed/synthetic bars, loading/error state, and coverage polling. Rapid symbol
changes therefore cannot paint an older response into
the active uPlot model; a focused two-symbol store regression proves the current symbol,
instrument, bars, and loading state remain aligned.

Top-down ETF holdings, constituent snapshots, sector/industry composition, industry
constituents, curated proxies, and proxy rankings use active-request generations as
well. Rapidly traversing SPY → XLK → XLE or switching industries cannot replace the
current drill-down with a late response from the previous selection; the workspace
store regression covers the active ETF boundary.

Chart-tool synthetic-expression resolution is generation-guarded before it hands a
target to the chart store, so a late `=XLK/SPY` or symbol-resolution failure cannot
overwrite a newer linked chart selection.

The primary EasyScan tool now exposes the shared technical-condition editor in addition
to its quick price/volume builder. Saved conditions can use indicator, price, period,
performance, 52-week, and statistics condition types under AND, OR, or NOT composition,
including recursively nested groups, while the existing unified-Python condition path
remains available. Scan definitions now also carry an explicit timeframe and all,
watchlist-ID, basket-ID, or custom instrument-ID universe selector instead of silently
hard-coding all instruments/D1. The focused scan suite proves both the advanced tree and
universe/timeframe fields are persisted through the canonical condition contract, and
supports manual, daily-close, and weekly-close cron scheduling. Completed runs retain a
bounded recent-result history in the tool, with a selector for inspecting prior match
sets without rerunning the scan.

The shared timeframe-link compatibility path now preserves valid `M1` one-minute
timeframes and normalizes only the legacy `MN1` monthly token to canonical `MN`.
This prevents intraday selections from being silently converted to monthly bars while
retaining persisted legacy-state recovery. The primary workstation shell and shared
tool-window selectors expose the complete supported set from `M1` through `MN` rather
than silently reducing linkable tools to four coarse intervals.

Study Lab now exposes explicit timeframe, benchmark, adjustment, session, and date-range
controls in the primary workstation tool. The research-run API validates those controls,
materializes only the requested canonical bars, records the normalized dataset manifest,
and rejects unsupported adjustments, invalid sessions, malformed dates, and reversed ranges.
The selected benchmark is now materialized as a separate aligned canonical close series
when available, exposed to the isolated Python runtime as `benchmark`, and reported with
explicit ready/unavailable coverage. The tool displays the selected dataset contract and
benchmark coverage alongside reproducibility output. Session remains an explicit canonical
metadata setting until session-qualified bars are available; it does not imply provider-
specific intraday availability. Focused backend, runner, and component tests cover the
contract. This is functional evidence only; the Version 25 visual reference remains
unapproved.

Canonical OHLCV bars now carry a persisted session classification (defaulting existing
history to `regular`) with an indexed instrument/timeframe/session access path. Study Lab
regular runs filter to regular-session bars, while `all` runs retain pre-market and
post-market classifications when present. Provider ingestion still reports only the
classification it can substantiate; it never infers a session from an unqualified source.

The isolated runner now restores process resource limits and alarm handlers after each
single or batch execution. CPU limits are offset from already-consumed process time while
preserving the hard boundary, preventing an in-process caller or test harness from
inheriting an immediately-expired limit. The deployment container still supplies the
independent cgroup, read-only filesystem, and no-network boundaries.

The isolated Python SDK now exposes bounded `scipy.stats` and `statsmodels.api.OLS`
facades alongside the existing NumPy/Pandas, market, technical-analysis, statistics,
research, and output namespaces. User code still cannot import modules or reach package
internals: only the curated statistical functions and regression result fields are
available. The runner image pins NumPy 2.1.3, Pandas 2.2.3, SciPy 1.14.1, and
statsmodels 0.14.4, constrains BLAS/OpenMP thread fan-out, and was smoke-tested in a
read-only, no-network, non-root container. The application `/code/validate` gate now
accepts the same curated roots and locally composed values as the isolated runner, so
the supported language is consistent across authoring, API validation, and execution.
This is functional sandbox evidence only; the complete security/resource acceptance
matrix and Version 25 visual reference remain open.

The runner file protocol now enforces bounded structured-output bytes, rows, artifact
count, and input-job bytes through deployment-configured limits. It converts malformed
or crashing jobs into terminal failed results, cleans progress/cancellation sentinels,
and recovers claimed `.running` jobs when the worker restarts. Focused tests cover row
and byte rejection, malformed-job recovery, and orphaned-claim recovery. These are
operational sandbox safeguards. The adversarial runner matrix now explicitly covers
dynamic execution/import/namespace calls, filesystem/network/process names, reflection
and object-graph/curated-wrapper introspection, dangerous NumPy attributes, and wall-time
alarm restoration: the combined validator/runner slice is 90 passing tests and the complete
backend unit suite is 955 passing tests. Docker namespace, seccomp, resource-pressure,
crash/orphan, and live image probes remain separate deployment gates.

The branch-scoped live runner was rebuilt with container-level ceilings of 768 MiB,
1 CPU, and 128 PIDs in addition to the per-job limits. Docker inspection confirmed
`uid=10001`, `network=none`, read-only root, dropped capabilities, no-new-privileges,
and the configured ceilings. Direct probes returned read-only-filesystem and
network-unreachable errors. This is deployment evidence for the isolated runner;
the full resource-pressure/crash/orphan matrix remains open.

Study Lab dataset controls are now part of the serializable workstation-window
configuration. Reopening, reloading, or floating a Study Lab preserves timeframe,
benchmark, adjustment, session, and date bounds through the existing workspace
configuration event path; legacy invalid monthly `MN1` state is normalized to `MN`.
Focused component coverage proves hydration and normalization. This is functional
evidence only; the Version 25 visual reference remains unapproved.

Persisted Research Results now renders the same typed scatter and heatmap artifacts as
the active Study Lab surface, using the dedicated uPlot point-cloud and native matrix
components rather than falling back to raw JSON. Saved studies therefore retain their
structured visual form after reload, comparison, or rerun; focused component coverage
proves both render paths.

The primary Study Lab and Persisted Research Results tools now use the shared TanStack
Vue Query client for run retrieval and terminal-aware polling. They stop refetching once
the run reaches `completed`, `failed`, or `canceled`, refetch after explicit cancel/rerun
actions, and suspend requests when the document is hidden or the tool surface is not
intersecting the viewport. This removes their independent interval timers and aligns
research polling with the Market Gauge freshness/coordinator contract. Focused component
coverage passes with the real Vue Query plugin; exact Version 25 visual approval and the
full polling/performance acceptance matrix remain open.

Study Lab, which owns its active run, now cancels that run when the tool is destroyed.
Persisted Research Results remains an observer and never cancels a durable run merely because
its viewer closes; explicit user cancellation remains available in the result detail. Chart-
tool Python plot evaluation follows the owner lifecycle: known plot runs are canceled and
chart/plot generations are invalidated during teardown, preventing late artifacts from
reaching a destroyed uPlot surface. Focused Study Lab teardown coverage passes; full
multi-window and long-running-job performance acceptance remains open.

The reusable uPlot chart host applies the same visibility contract to live latest-bar
refreshes through a reactive Vue Query observer. Its timeframe-aware `refetchInterval`
is disabled when the browser is hidden, the chart root leaves the viewport, or the chart
has not finished initializing; it resumes when visibility/intersection returns. Latest-bar
requests use a shared Vue Query key for canonical symbol, timeframe, and bar type, so
linked charts and pop-outs reuse the same fresh response instead of issuing duplicate
requests. Symbol/timeframe/bar-type changes create a new query key, while the existing
uPlot tail merge and chart teardown remain in place. Focused chart-adjacent regressions,
TypeScript checking, and production build pass. This is lifecycle evidence only; the
complete 100,000-point, multi-window performance and visual acceptance suites remain open.

Virtualized watchlist Python column and Boolean-condition batches now read their
`/research/runs/{id}/batch-results` snapshots through the shared Vue Query client keyed
by immutable run ID. Existing generation guards still discard late symbol/universe
responses, cancellation remains per run, and the cached result path prevents duplicate
reads when the same watchlist is recreated or linked across windows. The focused
10,000-row/Python watchlist suite passes; full polling and performance acceptance remains
open.

The same cancellation contract now covers Python timeframe edits and tool destruction.
Changing a column or condition timeframe invalidates the prior request generation before
starting the replacement run; destroying a docked or floated watchlist cancels every known
active run and invalidates pending generations so late POST/poll responses cannot repopulate
destroyed state. Focused VirtualWatchlistTool coverage exercises universe, timeframe, and
unmount cancellation; full polling, multi-window, and performance acceptance remains open.

EasyScan's queued Python-condition result history now uses the same Vue Query cache
identity (`screener-results:{screener_id}`) while retaining the existing bounded polling,
partial-result safeguards, and isolated-run cancellation. Repeated result refreshes for
the same saved scan therefore share one canonical retained snapshot; the focused EasyScan
suite passes. Full coordinator, hidden-tool, and long-running scan acceptance remains open.

EasyScan teardown now cancels a known queued or running Python research run when its tool
window is destroyed, while leaving completed, failed, and canceled results untouched. This
keeps the isolated worker lifecycle aligned with dock/pop-out recovery and the watchlist
teardown contract. Focused EasyScan coverage exercises both explicit and unmount
cancellation; full coordinator and long-running scan acceptance remains open.

Python chart-plot artifact polling in the workstation now uses the shared research-run
Vue Query key by immutable run ID as well. Obsolete runs are still canceled and sequence
guards discard late series, while repeated chart renders reuse the retained terminal
artifact response instead of issuing a second request. Focused chart/popup coverage and
TypeScript pass; complete multi-window polling/performance acceptance remains open.

The unified Python SDK now supports a typed `output.dashboard` composition contract. A
dashboard contains only bounded references to named scalar, table, series, histogram,
scatter, heatmap, or event artifacts plus title/span metadata; user code cannot provide
HTML, CSS, JavaScript, or components. Active Study Lab and persisted Research Results
render those panels through the shared native dashboard surface, with focused runner,
validator, and frontend coverage. The isolated runner rejects missing or self-referential
panel targets before persisting a completed result, so a dashboard cannot silently render
an unavailable artifact.

The new-workstation provider defaults are free-source-first and provider-neutral:
Alpaca (free IEX entitlement) supplies default US price/latest-price, SEC EDGAR supplies
US identity metadata and ticker-directory search, Alpaca supplies corporate actions and
US universe discovery, and OpenFIGI is the default stable-identifier reconciler. An
optional Massive reference adapter is available for ticker search and US-universe
corroboration when an entitlement is configured; it is not a runtime dependency. The
optional Alpha Vantage adapter supplies quota-limited raw daily history and symbol search
for corroboration; it is also never a required workstation path. The
default chains no longer include yfinance. yfinance remains registered only for explicit
legacy/options configuration and is not a required path for the new workstation; absent
Alpaca credentials are reported as unavailable rather than silently switching providers.

The primary workstation registry now has explicit unit evidence for the capability
boundary: supported chart, watchlist, scan, gauge, Study Lab, breadth, and rotation
tools remain discoverable, while brokerage/trading, options, news, ratings, earnings,
financial statements, and consolidated real-time domains are absent rather than shown
as disabled shells. This verifies menu registration only; legacy-route and full browser
acceptance remain separate gates.

The application route contract now has focused unit evidence for the shell boundary:
`/` and `/chart` (including `/chart/:symbol`) resolve to the authenticated workstation,
while the retained dashboard, chart, alerts, Radar, Strategy Lab, Baskets, ETF Holdings,
Screener, Watchlist, and Settings views are registered only beneath `/legacy/*`.
Pre-workstation top-level paths redirect into their corresponding legacy route. This
proves route registration and redirect intent without claiming full browser-authenticated
legacy usability or visual parity; those remain separate acceptance gates.

The `/study-lab` deep link now redirects into the workstation's persisted `study-lab`
factory tab instead of mounting a second standalone shell. The primary Study Lab tool
therefore owns symbol, link-group, dataset, layout, and pop-out state consistently with
all other workstation tools; its existing focused rendering and run tests remain the
functional evidence, while visual approval is still pending.

Instrument notes now have Docker-backed integration coverage for authenticated
round-tripping, canonical-instrument validation, unauthenticated rejection, and strict
per-user isolation. The API already scopes both read and upsert queries by user ID; the
tests prove one user cannot read or overwrite another user's note for the same instrument.
Linked-tool stale-load/save protections remain covered separately in the frontend race
suite. Full legacy browser usability and Version 25 visual acceptance remain open.

The primary workstation now exposes the persisted personal-layout lifecycle directly in
the TC-style Workspace menu: select, rename, clone, drag-reorder, delete (with the last
layout protected), reset the factory layout, and JSON export/import. Import accepts only
serializable layout snapshots with non-empty, unique layout IDs and preserves the
existing revision-checked backend snapshot path; malformed or duplicate layouts remain
in place with an explicit error. The focused workspace-store suite covers normalization,
reordering, deletion protection, export/import, and persistence scheduling. Visual
comparison, browser drag/drop evidence, and the broader acceptance matrix remain open.

An active unified-Python Boolean condition in a watchlist can now be promoted directly to
a repeatable EasyScan entry/exit alert. The workstation creates the canonical Python-backed
screener, then the user-scoped screener alert through the existing alert lifecycle, while
retaining explicit success/failure status and the condition timeframe. Focused
VirtualWatchlist coverage proves the screener and alert requests and the resulting status;
full authenticated browser and provider/runtime acceptance remain open.

Watchlist column customization now has an explicit internal clipboard contract. Column
settings (label, width, formatting, grouping, stack, and Boolean pin state) can be copied
from the integrated editor and pasted into the same canonical column on another linked or
restored watchlist; system clipboard failure falls back to an in-memory session copy, and
unknown/missing source columns are reported instead of creating a blank column. Focused
virtual-watchlist coverage proves the copy/paste round trip; full browser and visual
acceptance remain open.

Top-down benchmark, sector, constituent, and verified-proxy watchlists now expose
response-level `Coverage`, `Freshness`, and `Provenance` columns alongside the technical
ranking fields. They are populated from the canonical analysis metadata rather than a
provider-specific frontend assumption, and remain visible as explicit unavailable values
when a batch is not ready. The frontend contract accepts membership/version lineage for
future detail panes; visual density and full backend/E2E acceptance remain open.

The explicit E2E seed can now provision identity-only SPY/RSP, major benchmarks, and all
11 sector ETFs with unresolved ETF profiles. It deliberately does not create OHLCV bars,
holdings, or provider entitlements, so browser fixtures exercise the same labelled
unavailable/coverage states as a cold free-source-first deployment rather than masking
missing data with fabricated values.

Provider documentation is now aligned with the runtime entitlement policy: the default
free-source-first chain is Alpaca/Alpha Vantage for permitted history, EDGAR/Alpaca for
identity and events, and Massive/Alpha Vantage only for optional corroboration. yfinance
is documented as an explicit legacy/options fallback only, and excluded options, analyst,
earnings-estimate, and futures domains are capability stubs rather than new-workstation
fallbacks. This is documentation/contract evidence, not live-provider probe evidence.
The backend reference environment now matches those defaults as well: its ordinary
price-history, latest-price, discovery, event, metadata, and instrument-search seeds
exclude yfinance; yfinance remains listed only for explicit option/legacy slots. A fresh
environment therefore cannot accidentally restore the unofficial provider to the new
workstation's normal path by copying `backend/.env.example`.
Study Lab now ships editable factory starters for the core open-ended research patterns
required by the workstation scope: positive and negative close streaks (including
occurrence events, completed-length tables, histograms, and forward outcomes), moving-
average participation, forward-return distributions, configurable-20-session high/low
breakouts, realised-volatility regimes, monthly seasonality, relative-strength regime
crossings, declared-universe cross-sectional ranking, declared-universe breadth
participation, and the existing raw relative-strength history study. Every starter is ordinary
unified Python source using only the declared `market`, `ta`, `stats`, `research`, and
`output` SDK surfaces; editing the source returns the selector to Custom Python. All ten
new/retained sources pass the isolated runner's static validator and deterministic sample
execution, including the new declared-universe `research.cross_sectional_rank` and
`research.breadth_snapshot` helpers; the Study Lab component suite now covers the factory
catalogue (`8` tests) and the runner has direct aggregate-rank/breadth assertions.
This adds functional authoring coverage; exact Version 25 visual approval, aggregate
cross-sectional breadth studies, live-provider probes, and the broader acceptance matrix
remain open.

Study Lab Boolean and event results can also be promoted directly into a reusable Strategy Lab
signal asset through the same immutable Python code-version path used by columns, plots,
EasyScan conditions, and alerts. Event signals retain their structured `events` output
contract; they are not coerced into a Boolean condition. Aggregate ranking/breadth starters explicitly require a
declared comma-separated universe and show a visible warning rather than silently falling
back to the active symbol; the run guard prevents an invalid single-symbol request. Focused
Study Lab coverage now includes this promotion and missing-universe recovery path (`9`
tests), with TypeScript and production build passing.

Promotion now also creates a user-owned Strategy Lab definition through
`POST /api/v1/strategy-lab/signals/from-code/{code_version_id}`. Its version snapshot and
metadata retain the immutable signal code-version id and output contract instead of
copying source text, so the Strategy Lab library can discover the promoted signal and
revisions remain reproducible. The endpoint rejects archived, cross-user, non-signal, and
non-Boolean/event code versions. The isolated runner now evaluates declared event signals
across prepared-universe cells and returns bounded, symbol-qualified event artifacts. The
existing Strategy Lab engine remains authoritative for which execution modes are supported;
signal persistence and Study Lab event evaluation are complete for this contract, while
Strategy Lab Python-signal runs now queue through the same canonical dataset materializer
and isolated runner, expose queued/terminal research status, and reconcile bounded event or
Boolean artifacts through run retrieval/refresh. This is research/signal evaluation rather
than brokerage execution or a claim of trade-fill simulation; the existing Nautilus/rules
engine remains authoritative for execution statistics and portfolio replay.

The shared primary-facing provenance hint now reports canonical source, observation/fetch
times, selection reason, quality, and notes without exposing provider-specific symbol
aliases. This keeps the workstation's provenance contract provider-neutral while the
legacy options models retain their isolated provider fields for legacy-only routes.

The Sector by Year factory watchlist now exposes the same `Coverage`, `Freshness`, and
`Provenance` columns as the live sector ranking view, so calendar-year cells do not become
a lineage-free exception when the factory layout changes.

Industry drill-down rows now retain ETF-holdings classification lineage as well: resolved
coverage ratio, holdings composition date, and source/provenance are visible beside proxy
counts. Missing classification or proxy data remains explicitly unavailable rather than
being inferred from an industry name.

Study Lab dataset controls now include an explicit `As of` timestamp. The backend clamps
canonical bar materialization to that cutoff, rejects a cutoff before the requested start,
and retains the normalized cutoff in the dataset manifest. This prevents future bars from
entering historical studies and gives reruns a visible point-in-time boundary.
Sandbox hardening: the isolated NumPy facade can still return array-like values for
normal numerical composition, but the shared source validator now rejects dangerous
array attributes such as `tofile`, `dump`, `setflags`, `resize`, and `ctypes` regardless
of the local variable name used to reach them. Focused runner coverage exercises file
writes, raw-memory exposure, and mutation attempts; this closes a concrete gap between
the declared no-filesystem/no-host-access contract and the raw ndarray methods exposed
by NumPy. Docker-level network, namespace, seccomp, and resource-limit acceptance
remains a separate deployment gate.

The renderer acceptance suite now includes a real Chromium uPlot benchmark at
`frontend/tests/e2e/uplot_performance.spec.ts`. It loads the packaged uPlot build,
renders 100,000 points, performs forty viewport zoom/pan updates, verifies the chart
element is preserved, and enforces a bounded interaction time. The test passed in the
host-permitted Chromium run on 2026-08-04; this is renderer-level evidence only and
does not replace the pending authenticated workstation, pop-out, memory, and
multi-environment performance matrix.
## Continuation update — 2026-08-05T16:30:00Z Provider route refresh

The opt-in public ETF-holdings audit now reports `342 passed`, `1 skipped`, and `4 failed`.
The THOR THIR adapter follows the issuer's current extensionless product route and its live
holdings probe passes. The Tuttle health probe uses active DRMP because MAGO was liquidated;
historical MAGO identity remains in the canonical security master. Remaining failures are
explicit external-source conditions: Neos HTTP 403, Anfield HTTP 404, Donoghue Forlines HTTP
503, and an Inverdale timeout. They remain unaccepted and are not hidden by fallback behavior.
## Continuation update — 2026-08-05T12:45:00Z Broad local regression audit

The current branch still passes the full frontend suite (`576/576`) and full local backend unit
suite (`973/973`). This confirms the recent provider-route corrections did not regress the
workstation or backend unit contracts. Docker-backed integration/browser evidence was not rerun
because the current execution environment cannot access the Docker Desktop socket; the previous
rebuilt-stack results remain the authoritative evidence for those gates. Exact-build visual
approval remains blocked by the manifest's `required_missing` states.
## Continuation update — 2026-08-05T13:10:00Z Public-issuer 403 transport recovery

The provider boundary now retries an explicit public-issuer HTTP 403 through a browser-compatible
transport while retaining the same URL, headers, source identity, and provenance. This improves
WAF compatibility without introducing provider substitution or changing fallback order. The
deterministic ETF adapter suite passes `450/450` and the full backend unit suite passes `974/974`.
A focused live NEOS attempt was DNS-blocked by the current environment and therefore does not
promote that source; the last complete live matrix remains `342 passed, 1 skipped, 4 failed`.

## Continuation update — 2026-08-05T18:00:00Z Rebuilt-stack browser acceptance repair

The authenticated non-visual acceptance set now passes `35/35` on the rebuilt branch-scoped stack,
covering core flows, the real Chromium uPlot guard, and workstation pop-out performance guards.
The chart smoke test recognizes the documented explicit unavailable-data state while retaining a
bounded requirement for the chart tool and symbol search. Pop-out lifecycle and canvas-count guards
baseline after one-time lazy volume/indicator initialization, eliminating a harness race while
preserving the settled-count invariant. This is functional/performance evidence only; strict V25
visual acceptance remains blocked at `application-shell-default/default: required_missing`.

## Continuation update — 2026-08-05T19:00:00Z Multi-window churn coverage

The workstation performance suite now includes five rounds of opening two simultaneous browser
pop-outs, verifying both detached tools, closing them, and asserting stable source tool/canvas/chart
counts after every round. When Chromium exposes heap telemetry, the guard also rejects a post-churn
heap above 512 MiB. Targeted performance passed `2/2`, and the complete rebuilt-stack Chromium set
passed `36/36` with clean diagnostics. This strengthens lifecycle evidence but does not replace the
remaining multi-monitor/long-duration soak or strict Version 25 visual approval.

The factory-layout acceptance audit also rejects drawing-toolbar/chart-surface overlap alongside
tool-header title/symbol/action collisions. All eight factory layouts passed this geometry check
without recovery state or browser diagnostics. It remains a deterministic safety guard; measured
pixel parity still requires approved reference baselines.

The workstation browser acceptance now includes an explicit hidden-document refresh guard: market
analysis remains quiescent while hidden and resumes only through the visible-state handler. Pop-out
performance baselines require repeated stable canvas samples before asserting lifecycle invariants,
so transient first-mount panes cannot be mistaken for leaks. The complete rebuilt-stack Chromium
set passes `37/37`; this remains functional/performance evidence rather than visual approval.

## Notes identity and persistence regression — 2026-08-06

Notes, Alerts, and report tools now resolve the active canonical instrument directly when opened
without a chart sibling, including isolated and floated windows. A repeated Notes save also exposed
an async SQLAlchemy response-serialization defect: server-side `updated_at` expiration could raise
`MissingGreenlet` and return HTTP 500. The Notes router assigns the update timestamp locally and
refreshes before returning; the create/update/read integration regression and rebuilt-stack F8s
browser acceptance pass. This closes the instrument-note persistence contract; strict V25 visual
approval and the broader provider, resource-stress, multi-monitor, and long-soak gates remain open.
## Continuation update — 2026-08-06T16:45:00Z Symbol-selection race repair

The complete authenticated flow suite passes `42/42` serially after correcting a real
autocomplete race in the workstation header. Explicit symbol selection now cancels the pending
debounce, invalidates any in-flight search generation, and clears stale results before publishing
the canonical instrument. Focused F8m/F8k/F8g/F8q checks, full frontend Vitest (`577/577`),
TypeScript, and production build pass. This is functional evidence only; strict V25 visual
approval remains blocked by required-missing reference states.
## Continuation update — 2026-08-06T17:30:00Z Live runner crash/recovery

The isolated research runner now has a repeatable live recovery probe covering the actual shared
job/result volumes. A real long-running job was claimed, only the runner container was killed and
restarted, and the restart-time orphan recovery completed the job with no stale cancellation or
progress sentinel. The focused deployment contract suite passes `6/6`. This closes only the
bounded crash/orphan recovery slice; sustained stress, provider-live, native multi-monitor,
indefinite soak, and strict V25 visual acceptance remain open.
## Continuation update — 2026-08-06T18:45:00Z Sequence-dependent workstation regression repair

The complete authenticated flow audit was rerun from a clean rebuilt-stack browser sequence rather
than relying on isolated green tests. It exposed and fixed three real lifecycle races: stale symbol
autocomplete options could intercept a subsequent workstation action; Ctrl+wheel traversal could
lose canonical benchmark symbols while market groups were only partially hydrated; and simultaneous
pop-outs could observe a transient workspace snapshot without their requested tool. The shell now
has an explicit user-input search boundary with cancellation/invalidation on blur and canonical
publication, a stable fallback traversal universe, and one bounded canonical hydration retry for
pop-outs. Unit lifecycle tests unmount their wrappers after assertions.

The final serial flow suite passes `42/42`, including all top-down, linking, Study Lab, notes,
legacy, exclusion, and pop-out paths. Full frontend Vitest passes `577/577`; TypeScript and the
production build pass. This strengthens functional parity evidence but does not alter the strict
visual rule: no surface is approved without its pinned Version 25 reference state, and the visual
manifest still correctly fails closed at `application-shell-default/default: required_missing`.
### 2026-08-06 drag/drop transfer verification

The real browser transfer paths are now covered by rebuilt-stack Chromium checks `F8u` and
`F8v` (`2/2`): chart plots can be dropped into watchlist numeric columns and EasyScan technical
condition trees can be dropped into Boolean columns. The implementation also fixes chart-control
hit-testing, async condition-library timestamp serialization, and repeated-run screener reuse.
This closes the functional oracle; exact Version 25 visual treatment for unrepresented states
remains tracked in the reference-board gap matrix.

### 2026-08-06 concurrent chart persistence verification

Linked and floating chart instances can persist the same instrument's indicator configuration at
the same time. The indicator API now resolves the unique-row race deterministically and focused
browser coverage confirms chart initialization and transfer paths remain free of HTTP 500s.
### EasyScan → Market Gauge live handoff

The workstation now invalidates and refetches the shared saved-scan query after an EasyScan is
created or reused. This keeps a Market Gauge that is already mounted in a docked tab synchronized
without requiring a remount. Authenticated Chromium F8w covers condition creation, scan execution,
Gauge refresh, and match rendering (`1/1`, no critical diagnostics); the EasyScan component suite is
`8/8`.
### Add Tool activation

Opening a tool from the workstation's Add Tool library now updates the active persisted window
key and the Golden Layout host resolves that key to its containing stack, selecting the new tab
after layout installation or restoration. This prevents a newly opened tool from being persisted
but visually hidden behind the previous active tab. Component coverage is `4/4`; authenticated
Chromium F8x verifies Python Library activation in the real workstation with clean diagnostics.
### Active Golden Layout tab persistence

Golden Layout now publishes active component changes to the workspace store. The canonical
`active_window_key` is updated only for known persisted windows and is saved through the existing
revisioned snapshot path, so reloads restore the last selected tab rather than merely restoring
geometry. Workspace host coverage is `5/5`, workspace-store coverage includes the unknown-key and
idempotence cases, and authenticated F8x remains green.
### 2026-08-06 Add Tool stack-width regression audit

The Add Tool path was audited against a real personal-watchlist membership flow. A store-level
regression showed that appending new tools directly to the Golden Layout root created 10px-wide
root columns; `openTool` now joins an existing stack (or wraps a component into one) and preserves
the root layout. A second race fix prevents an older in-flight snapshot `409` from restoring over a
newer Add Tool mutation. Workspace-store coverage is `40/40`, full frontend Vitest is `598/598`,
and type-check/build pass. Authenticated F8v, F8y, and F11 now pass after explicitly activating the
newly added tab and removing hidden-tab order dependence. Personal-list copy/move browser coverage
remains an explicit follow-up gap; no forced-click or visual acceptance flexibility was used.

### 2026-08-06 final browser/visual gate refresh

The rebuilt-stack serialized authenticated Chromium matrix passes `56/56` executed tests; its 24
visual-project cases are separately covered by the board gate, which passes `24/24` across all four
required environments. Recent logs contain expected provider-exhaustion freshness warnings only,
with no HTTP 500, traceback, `MissingGreenlet`, or `UniqueViolation`. Remaining gaps are exact or
unrepresented V25 states, opt-in live-provider probes, physical multi-monitor validation, endurance
beyond bounded stress, and personal-list copy/move browser coverage.

### 2026-08-08 visual gap-oracle refresh

The board-guided visual spec now exercises chart provider-error and Study Lab validation-error
states in addition to loading, blocked-popout, stale, and partial-coverage states. The serialized
four-environment matrix passes `32/32`; frontend Vitest remains `601/601`, `vue-tsc`, and diff
checks pass. These two states remain `required_missing` in the manifest because the board has no
authoritative pinned-build styling for them; the screenshots are deterministic interim evidence,
not exact Version 25 approval.

The authenticated E2E matrix also now includes an explicit 125% browser page-scale robustness
guard (`F8z`) for shell containment, watchlist visibility, header separation, and footer bounds.
The complete non-visual/performance run passed `57/57` executed tests, including F8z, uPlot
100,000-point interaction, and multi-window churn. The visual projects were intentionally skipped
by that command and remain independently covered by the `32/32` board run.

Workspace persistence now also has a real browser round-trip oracle (`F9d`): the test exports the
active workspace through the download control, clones a layout, imports the downloaded JSON through
the file picker, and verifies the original layout count is restored. The complete non-visual run
passed `58/58` executed tests after this addition.

The integrated watchlist Columns/Sets editor now has a real browser oracle (`F9e`) covering column
group assignment, stacking, saved-set creation, and saved-set reapplication. The subsequent full
non-visual/performance run passed `59/59` executed tests; the board-guided visual run remains
independently green at `32/32`.

Chart-template persistence now also has a real browser round-trip oracle (`F9f`): it saves a
template, downloads it through the product control, deletes it, imports the downloaded JSON via the
file picker, reapplies it without replacing the active symbol, and verifies the restored bar type.
The focused test passed and the complete non-visual/performance run reached the new `60`-test
execution set; the board-guided visual run remains independently green at `32/32`. The first full
matrix exposed one ordering-sensitive F8v observation; focused, adjacent-order, and subsequent full
matrix reruns passed, so the observation is retained as transient test history under the goal
tie-break policy rather than being silently waived or treated as a product defect.

The Python result-reuse path now has a real browser oracle (`F9g`): a scalar Study Lab result is
validated, executed, saved as an immutable reusable column, consumed from the `US Top Down`
watchlist Columns editor, and verified as a rendered header without relying on hidden layout DOM.
The focused test passed; the complete non-visual/performance matrix passed `61/61` executed tests,
and the board-guided visual matrix remains independently green at `32/32`.

### 2026-08-08 unified Python condition → EasyScan → alert

Added F9h for the next unified-language path: create a Python `condition` asset in the Code
Library, attach it through the integrated EasyScan condition selector, run the scan, and promote
the saved result to an alert. The first rebuilt-stack run exposed a real backend defect rather than
a test-oracle issue: serializing a screener result lazily loaded `ResearchRun.artifacts` from an
async SQLAlchemy session and raised `MissingGreenlet` (HTTP 500). Both screener and Strategy Lab
research refresh queries now eagerly load artifacts with `selectinload` before the synchronous
artifact protocol runs.

Evidence: screener and Strategy Lab integration assertions pass `43/43` together (the targeted
commands still report non-zero only because the repository-wide coverage gate is not meaningful for
an isolated subset); rebuilt-stack F9h passes `1/1`, the affected F8q/F8w/F9h slice passes `3/3`,
frontend Vitest passes `601/601`, and `vue-tsc --noEmit` passes. The full authenticated matrix then
passed `61/62` executed tests with only the existing F8u chart-plot drag oracle missing once; five
fresh F8u repetitions passed `3/5`, and a fresh isolated rerun passed `1/1`. Per the goal-level
tie-break, this is retained as a localized ordering/state reproducibility gap and does not block
independent work; it is not claimed fixed by this slice.

The Study Lab validation-error board oracle was also made deterministic by holding the adjacent
chart's OHLCV request in its documented loading state, rather than masking or refreshing a changed
chart baseline. The complete manifest plus board-guided visual suite now passes `32/32` across all
four environments. No acceptance flexibility was used for the F9h/backend fix; the existing board,
fixture, hardware, live-provider, and bounded-endurance substitutions remain explicitly tracked in
the acceptance-governance ledger.

### 2026-08-09 Study Lab series → reusable chart plot

Added F9i for the complementary unified-Python path: create and run a Study Lab numeric series,
save it as an immutable chart-plot asset, return to `US Top Down`, load it through the chart plot
library, and verify it is listed as a reusable Python plot. The chart plot library now renders
Python plots as first-class entries and supports removing one through the same serializable
configuration contract used to add it.

During validation, the real browser uncovered two UI defects: persisted Study Lab activation could
leave the requested layout unselected, and the chart plot menu was positioned against the wrong
edge of a narrow chart, escaping into a neighboring watchlist and intercepting pointer events. The
flow now activates the top-level and inner Study tabs explicitly; the menu is fixed-positioned from
its trigger and the chart surface has an explicit stacking context. Rebuilt-stack F9i passes `1/1`,
the ChartPlotLibrary unit suite passes `9/9`, and the full frontend suite passes `602/602` with
type-check passing.

The subsequent full authenticated matrix executed `63` tests: `61` passed and the two existing
localized interaction observations were F8u drag/drop and F8y personal-watchlist activation. F8u
passed five fresh rebuilt-stack repetitions; F8y remains an explicitly tracked watchlist-state gap.
The board-guided visual cases remain independently covered by the four-environment suite. No
acceptance flexibility was used for F9i; the existing tie-break policy remains active for F8u/F8y.
### 2026-08-09 watchlist mutation reconciliation follow-up

The Add Tool path exposed stale cross-window membership reads and duplicate create/item dispatches.
The store now preserves local item deltas while reads catch up, deduplicates same-name creates,
treats duplicate inserts idempotently, and applies membership updates immutably. Store regressions
pass `14/14` and type-check passes. Rebuilt F8y progressed past the missing-XLE-row defect but
still has a later copy/move timeout, tracked as a localized recoverable gap under the goal
tie-break. No visual, provider, hardware, or other acceptance criterion was relaxed.

### 2026-08-09 F8y copy/move interaction closure

After the store and API conflict fixes, the full authenticated sequence was observed with source
creation, XLE insertion, copy POST, move POST, and source DELETE. Rebuilt-stack F8y passed `1/1`,
then passed three independent repetitions (`3/3`). The earlier selection timeout is superseded by
this evidence; no acceptance flexibility was used.

### 2026-08-09 workspace-selection fence hardening

The affected F8u/F8v/F8y slice after the watchlist closure passed F8v and F8y (`2/2`); F8u missed
once in the combined ordering. The local workspace-selection acknowledgement fence was extended
from one second to ten seconds because queued workspace snapshots can outlive a rapid multi-list
operation. Five isolated F8u repetitions then passed (`5/5`). The remaining full-suite F8u
observation is retained as a localized drag-ordering risk; no criterion was relaxed.

### 2026-08-09 F8u drag-to-column closure

The real drag path exposed two product-level ordering/state defects. The drag payload now has a
same-document fallback for browser implementations that expose an empty custom MIME value at
drop time, and the chart plot library no longer clears that payload during `dragend` before the
target receives `drop`. Plot drops also register the indicator column and append its key to a
customized watchlist's authoritative visible-column configuration; an already-registered column
is made visible rather than silently ignored. Newly added chart indicators are persisted
immediately for cross-tool handoffs instead of waiting for the debounced save.

Evidence: plot-drag, ChartPlotLibrary, and VirtualWatchlistTool targeted unit coverage passed
61/61; `vue-tsc --noEmit` passed; the rebuilt production stack completed successfully; F8u passed
five independent Chromium repetitions (`5/5`); and the adjacent F8u/F8v/F8y slice passed `3/3`.
No acceptance criterion was relaxed and no visual/reference gap was masked. The goal-level
tie-break remains available for future localized failures, but this F8u gap is closed by the
current evidence.

### 2026-08-09 F8y cross-root watchlist mutation hardening

The repeated Add Tool browser audit found duplicate requests originating from overlapping
Golden Layout virtual roots: concurrent personal-list creates and concurrent item additions could
race even though the backend correctly enforced uniqueness. Watchlist create and item-add
in-flight operations now deduplicate at module scope across separate Pinia instances, and a
successful symbol add reasserts the list that accepted the mutation before publishing its
workspace configuration. Cross-root unit coverage was added for both operations.

Evidence: watchlist-store coverage passed `16/16` after the create/item tests, the combined
watchlist/virtualized-tool subset passed `64/64`, and `vue-tsc --noEmit` plus rebuilt production
build passed. F8y still has a localized Golden Layout root-selection race under rapid multi-create
browser repetition (the active control can change roots between actions); focused runs are not
yet deterministic. This remains explicitly tracked under the goal tie-break with the affected
flow, reproduction, and next closure path; no acceptance criterion or visual mask was relaxed.
The latest clean rebuilt-stack repetition also timed out with the workstation still in an explicit
`Fetching` state, so it is retained as failure evidence; the next audit must separate request/data
loading contention from virtual-root selection before closure.

### 2026-08-09 F8y create-result hardening

Create results now carry a non-enumerable request-origin marker, so a conflict-resolved duplicate
cannot republish a different virtual-root selection. Cross-root create and item-add operations
remain module-scoped and idempotent, while successful item additions reassert the accepting list.

Evidence: `vue-tsc --noEmit`, watchlist-store tests (`16/16`), and the rebuilt production stack
passed; F8y passed five repeated Chromium runs (`5/5`). The adjacent F8u/F8v/F8y slice passed
`7/9` with two combined-order F8u misses; isolated F8u then passed `2/2`. Those misses remain a
localized drag-ordering reproducibility gap under the goal tie-break, not a waiver. No visual,
provider, security, or data-integrity criterion was relaxed. The F8y test's 60-second timeout is
a bounded runtime correction, not a product acceptance relaxation.

### 2026-08-09 full Chromium regression after watchlist refresh fix

The transient-refresh preservation fix is validated in the complete authenticated matrix: F8y
now passes in the full run, and the matrix is `61/63`. The only remaining observations are F8u
and F8v drag-transfer misses in combined ordering. Isolated repeated validation passed F8u `3/3`
and F8v `2/3`; the single F8v miss is retained as a localized drag/drop reproducibility gap with
its existing focused oracle and remediation path. No acceptance criterion, visual mask, provider,
security, or data-integrity requirement was relaxed.

### 2026-08-09 condition-column persistence hardening

F8v now retains newly-created Boolean condition columns locally through the workspace
acknowledgement window and removes them when creation fails. Type-check and the
VirtualWatchlistTool suite passed (`47/47`); rebuilt F8v passed five repeated runs (`5/5`). A
combined F8u/F8v/F8y run was `6/9`, with one shared-order miss per flow; isolated focused runs
remain the localized evidence and no acceptance criterion or visual mask was relaxed.

### 2026-08-09 backend coverage correction and gate

The visual-manifest unit oracle was updated to match the controlling four-environment provider
error baseline contract. The complete backend unit/integration gate then passed `1,277/1,277`
with `79.43%` coverage (above the required 75%). The 86 emitted warnings are dependency
deprecations only; no backend test or coverage criterion was relaxed.

### 2026-08-09 board-guided visual regression

The official manifest validator and serialized four-environment board-guided visual suite passed
`32/32` after the watchlist and condition-column changes. Deterministic local baselines and interim
state oracles are green; unrepresented exact-build states remain explicitly `required_missing`.
No gap was silently closed and no screenshot mask or acceptance criterion was relaxed.

### 2026-08-10 Research Results and Study Lab recovery hardening

Persisted Results now uses a compact list/detail split: list rows carry status, progress, warnings,
and artifact counts while the selected run hydrates full artifacts and comparison data on demand.
The global Study action also repairs a customized layout with no mounted Study Lab tool by opening
the persisted tool definition instead of leaving the user on an empty tab.

Evidence: focused backend list integration `1/1`, ordered rebuilt-stack F8g/F9i `2/2`, frontend
Vitest `630/630`, type-check, and production build. Acceptance flexibility used: none. Exact-build
visual states, live-provider probes, physical multi-monitor behavior, and indefinite soak remain
tracked evidence gaps.

The subsequent complete authenticated Chromium rerun passed `63/63`, including the complete
top-down, Study Lab, linking, pop-out, legacy, uPlot, and workstation-performance acceptance set.
Post-run service logs contained no error signatures; unavailable holdings and provider exhaustion
remain labelled data-coverage states rather than hidden failures.

The follow-up board-guided visual matrix passed `32/32` across the four required display
environments. No baseline or mask changed; the remaining exact-build/unrepresented states stay in
the manifest gap register.

The full backend coverage gate was also rerun after these UI/API changes: `1,277/1,277` at
`79.43%`, above the 75% threshold, with only known dependency deprecations.

Selected compact Results rows also expose an explicit detail-loading state during artifact
hydration. Focused component coverage `7/7` and rebuilt F8g/F9i `2/2` verify the transition without
changing any visual baseline or mask.

### 2026-08-09 clean frontend acceptance matrix

After condition-column and transient-refresh hardening, the complete authenticated Chromium matrix
passed `63/63`, including F8u/F8v/F8y, Study Lab, linking, pop-outs, legacy routes, uPlot
100,000-point interaction, and workstation churn. The complete frontend Vitest suite passed
`610/610` and `vue-tsc --noEmit` passed. No acceptance flexibility, visual mask, or gap closure
was inferred beyond the documented board-guided evidence.

### 2026-08-10 bounded research-runner operational probes

The branch-scoped runner passed the live sandbox/resource probes, isolated orphan recovery, and
five sustained cancellation/success rounds. The recovery probe completed a claimed job after
restarting only the runner; each sustained round isolated a canceled 600-cell workload while a
concurrent scalar completed, with no stale sentinels or restart. This is bounded stress evidence;
indefinite soak and native multi-monitor behavior remain explicit external gaps under the
acceptance-governance policy. No functional or visual criterion was relaxed.
## 2026-08-10 backend validation checkpoint

The authoritative combined Docker-backed backend unit/integration gate passes `1,320/1,320` at
`79.59%` line coverage (required threshold `75%`), including the ETF adapter and Leverage Shares
native-route tests. This is supporting evidence for the top-down benchmark/sector/constituent
workflow; it does not close the remaining exact-build or unrepresented visual references,
provider breadth/entitlement, native multi-monitor, endurance, or final-audit items.
## 2026-08-10 O'Shares backend support checkpoint

The top-down ETF constituent path now has native O'Shares coverage through the official ALPS
public holdings proxy. OUSA live validation passed, the complete ETF-adapter suite passes
`464/464`, and the combined Docker-backed backend gate passes `1,321/1,321` at `79.60%` coverage.
Registry coverage is 496 registered / 349 native-live-backed / 147 audited fallback-only. This
supports the workstation's ETF-derived analysis; it does not close the remaining provider,
visual-reference, physical multi-monitor, endurance, or final-audit gaps.
## 2026-08-10 — Shared and heat-map sparklines

The remaining numerical sparkline surfaces now use the shared uPlot host rather than SVG
polylines. Watchlist sparklines preserve cached timeframe loading and the legacy heat-map passes
already-materialized tile series, with fixed dimensions and no per-tile fetch. Focused coverage is
`5/5`; the full frontend suite is `678/678`; type/build, the numerical-SVG audit, and the targeted
authenticated dashboard browser regression (`F15`, `1/1`) pass. This is an implementation-contract
closure, not new TC2000 reference evidence, and no acceptance flexibility was used.

## 2026-08-11 — Canonical identity propagation through workstation links

Top-down benchmark, sector, industry/proxy, breadth, and relative-rotation selections now carry
the canonical `instrumentId` through the workstation store, shared link events, persisted tool
configuration, isolated Grey windows, pop-outs, and ratio-launch actions. Ticker-only navigation
explicitly removes stale IDs so a later symbol cannot inherit the prior listing identity. Focused
identity/link tests pass `68/68`; the complete frontend suite passes `683/683`; `vue-tsc`, the
468-module production build, the uPlot contract audit (`42` files), and `git diff --check` pass.
The rebuilt canonical top-down browser slice passes `5/5` on the first stabilized rerun and the
previously flaky ratio flow passes `1/1` in isolation; an earlier branch restart produced setup
502/login timeouts and is not counted as product evidence. Acceptance flexibility used: **none**.
This closes a repository-controlled identity-integrity gap. Exact-build/unrepresented visual
states, broader live provider/entitlement coverage, physical multi-monitor placement,
beyond-bounded endurance, and final audit remain explicit and tracked.

## 2026-08-11 — Canonical identity from synthetic report constituents

The instrument report's synthetic-expression constituent chips now publish both ticker and
canonical constituent instrument ID into the workstation selection path. This closes the last
identified ticker-only top-down/report handoff; focused report, link, and workspace coverage passes
`66/66`, and `vue-tsc --noEmit` passes. Acceptance flexibility used: **none**. Exact-build and
unrepresented visual states, provider/entitlement breadth, native multi-monitor placement,
beyond-bounded endurance, and final audit remain open.

## 2026-08-11 — Canonical search results carry identity directly

Canonical local instrument search now returns `instrument_id`. Workstation autocomplete and Go/Enter
selection pass that identity directly into linked-symbol publication, while legacy symbol-only search
consumers retain their existing helper contract. Backend canonical-boundary integration passes `2/2`;
focused frontend search/workstation tests pass `66/66`; full frontend passes `685/685`; type-check,
production build, uPlot contract (`42` files), and `git diff --check` pass. Rebuilt dev-proxy
authenticated F7 and F8d flows pass `1/1` each. The first unprivileged backend attempt was a
Docker-socket setup error; the permitted rerun is authoritative. Acceptance flexibility used:
**none**. Remaining visual-reference, provider/entitlement, monitor, endurance, and final-audit gaps
remain explicit.

## 2026-08-11 — Direct industry-proxy actions retain canonical identity

Industry-proxy selection now resolves the canonical instrument when a direct, keyboard, or other
proxy action does not include a row identity, while preserving an explicitly supplied row identity.
This closes the remaining ticker-only proxy handoff in the top-down drill-down path. The focused
pop-out/link suite passes `16/16`; the complete frontend suite passes `686/686`; type-check,
production build, uPlot contract (`42` files), `git diff --check`, and ops/visual manifest parsing
pass. Acceptance flexibility used: **none**. The visual-reference, provider/entitlement,
native-monitor, endurance, and final-audit gaps remain tracked and are not treated as closed.
The post-change backend unit gate also passes `1,073/1,073` with 34 known dependency deprecation
warnings; no new backend failure class was introduced.
The combined backend unit/integration coverage gate subsequently passes `1,367/1,367` at
`79.62%` (86 known dependency warnings); no backend acceptance regression was found.
Against the running branch backend, the current Vite source passes the focused authenticated
top-down browser slice `3/3` (`F8d`, `F8e.1`, and `F8e.2`); no unexpected browser diagnostics were
observed.

## 2026-08-11 — Logout request-boundary regression closed

The first complete current-source browser matrix exposed one localized `F5` failure: logout could
clear token storage while the API client was still awaiting token lookup, turning already-starting
protected drawing/alert requests into post-logout `401` responses. The API client now captures the
token synchronously before its first await; drawing hydration also avoids starting unauthenticated
requests and suppresses only the expected in-flight authentication race. API/drawing focused tests
pass `15/15`; the full frontend suite passes `689/689`; type-check, production build, uPlot
contract (`42` files), and `git diff --check` pass. The repaired complete authenticated matrix
passes `87/87` with no unexpected browser diagnostics. Acceptance flexibility used: **none**.

The current source then passed the complete board-guided visual matrix `104/104` across all four
required display environments. This uses the documented board/seeded-fixture interim track for
represented states; no visual threshold, baseline, or mask changed. Exact-build/unrepresented
states remain open under `REF-SHELL-V25`, `REF-STATE-VARIANTS`, `REF-LINKING-V25`,
`REF-STUDY-LAB-V25`, `REF-ENV-TOKENS`, and `REF-PERMISSION-REVIEW`.
Acceptance flexibility used: **board evidence plus deterministic seeded fixture**.

The current source's bounded workstation performance/cleanup browser suite passes `2/2`, covering
multi-chart initialization/recovery and repeated multi-window churn without canvas or tool growth.
This is bounded-stress evidence only; indefinite/long-duration endurance remains open under the
documented flexibility ledger. Acceptance flexibility used: **bounded stress in place of
indefinite soak**.

## 2026-08-11 — Admin-only provider configuration boundary

The legacy Settings surface now hides provider `Show config` and configuration-panel controls from
ordinary users after the backend authorization repair made those mutations admin-only. Read-only
provider usage remains available; the new reconciliation queue remains administrator-only and
legacy-routed, so governance controls do not leak into the authenticated workstation. Settings
unit coverage passes `4/4`, full frontend Vitest passes `691/691` across 93 files, type-check and
production build pass, and the rebuilt branch browser regression passes `1/1`. A first template
condition was attached to the usage control rather than the configuration control; the focused
test caught that immediately and the condition was corrected before the full rerun. Acceptance
flexibility used: **none**. Exact-build/unrepresented visual references, provider breadth and live
entitlement coverage, native physical-monitor placement, beyond-bounded endurance, and final audit
remain explicitly tracked gaps.

The rebuilt branch then passed the complete authenticated Chromium flow matrix `88/88`, including
the new regular-user Settings visibility check plus authentication, charting, linking, pop-outs,
top-down drilldown, Study Lab, alerts, screeners, legacy routes, and Radar. This is full current
source functional evidence; it does not close the separately tracked exact-build/unrepresented
visual, live-provider breadth, native-monitor, endurance, or final-audit gaps.

The Python Library lifecycle is now also covered by a real-user browser path: a Study asset is
created, edited into a new immutable version, cloned, and archived. The complete authenticated
matrix passes `89/89`; no visual baseline, mask, threshold, or acceptance criterion changed.

Research Results now has a real-user comparison assertion as well: two persisted runs can be
selected, compared, and inspected for changed code/parameter/dataset metadata. The initial focused
oracle targeted all run rows rather than the selected row; the failure was corrected immediately,
the focused comparison path passed `1/1`, and the full matrix remained green at `89/89`.
# TC2000 parity implementation record

## 2026-08-11 — Provider listing-lifecycle evidence retention

Discovery observations now retain provider-reported IPO, active/delisted status, and delisting dates
on both canonical field provenance and the provider-symbol binding, with source and observation time.
The backend deliberately does not treat one provider observation as authoritative point-in-time
truth or silently deactivate a canonical instrument. Focused metadata coverage passes `2/2`; changed
Ruff/compile and repository checks pass. This is supporting security-master work for the workstation;
complete historical listing truth remains an explicit gap. Acceptance flexibility used: **None**.

## 2026-08-11 — Deterministic visual policy guard

The V25 manifest now declares the local visual policy (`0.5%` maximum screenshot-difference
ratio, `1px` geometry tolerance, and CIEDE2000 ΔE 2). A source-level validator checks all 26
workstation screenshot assertions for the required threshold, disabled animations/caret, and CSS
scale, and checks that every `required_missing` state retains an interim oracle plus four local
environment baselines. `make test-visual-policy` and manifest validation pass. This is a guard
against future acceptance drift, not exact-build approval; all existing board/reference gaps remain
explicit. Acceptance flexibility used: **None**.

## 2026-08-11 — Combo-list active-state and editor parity

Personal watchlists now compose into a durable union/intersection/exclusion combo list from the
dense workstation WatchList tool. The browser path creates A (SPY), B (XLK), and an exclusion list
(XLK), saves the combo, verifies that the active combo view contains one remaining SPY row, and
deletes the combo without leaving the workspace. A real Golden Layout race was fixed: explicit list
selection is fenced against stale sibling roots, mutation completion is exposed through `aria-busy`,
the combo editor wraps into a visible bounded row, and saving a combo clears the prior personal-list
selection fence. Focused and adjacent browser coverage passes `2/2`; frontend Vitest passes `696/696`;
the complete authenticated Chromium matrix passes `95/95`; and the seeded four-environment
board-guided visual matrix passes `104/104`. No functional criterion, visual baseline, mask, or
threshold was relaxed. The board/seeded-fixture policy remains interim represented-state evidence;
exact-build/permission, unrepresented visual states, provider/live-entitlement breadth,
physical-monitor placement, beyond-bounded endurance, and final-audit gaps remain open.

## 2026-08-11 — EasyScan history as a reusable uPlot plot

Retained EasyScan result history is now a first-class numeric chart asset. The canonical backend
exposes `GET /screeners/{id}/plot` for count and percentage history, returning chronological points,
coverage, freshness, and an explicit empty-history warning without rerunning a scan or fabricating
values. The workstation Chart Plot Library can discover saved scans, add either metric, persist the
serializable plot configuration, and manage visibility, ordering, duplication, colour, removal, and
chart linking through the existing uPlot numeric-series path. No provider-specific symbol or
credential reaches the frontend.

Focused backend integration passed `25/25` assertions; the authoritative combined backend gate passed
`1,370/1,370` at `79.62%`; Ruff passed; frontend Vitest passed `696/696` across 93 files; type-check
and the 468-module production build passed; focused browser F9j passed `1/1`; the complete current
Chromium acceptance matrix passed `94/94`; and the seeded board-guided visual matrix passed `104/104`
across all four required display environments. No screenshot baseline, mask, threshold, or product
criterion changed. The scan-plot implementation used no acceptance flexibility; the visual run used
the already-documented composite-board plus deterministic seeded-fixture policy, so exact-build,
unrepresented/ambiguous visual states, provider/entitlement breadth, native physical-monitor
placement, beyond-bounded endurance, and final-audit gaps remain open.

## 2026-08-11 — Durable security-master ambiguity reconciliation

The provider boundary now persists SEC ticker collisions as idempotent reconciliation issues,
keeps the raw discovery evidence, refuses unsafe canonical promotion, and exposes authenticated
list/resolve operations. Same-issuer listings on multiple venues remain promotable. Focused
queue/provider/persistence/router tests pass `99/99`; the authoritative backend gate passes
`1,362/1,362` at `79.61%`; no visual or product acceptance flexibility was used. This is supporting
data-governance work for the TC2000 top-down workflow, not a visual parity closure. Open items:
administrator/reviewer governance, SEC live access returning 403 in this environment, ETF/fund and
historical-listing coverage, and the still-open visual/reference/hardware/endurance/final-audit
items.

## 2026-08-11 — Seeded board-guided visual acceptance

The isolated seeded visual stack passed the complete four-environment board-guided matrix,
`104/104`, after the initial canonical-stack invocation was rejected by the deliberate fixture-mode
guard. This validates the current dense shell, menus, tool chrome, workspace states, Study Lab,
chart states, freshness/error states, and blocked-popout states against the 230-source composite
board at both required display scales. No threshold or mask was changed. This is board-guided
acceptance for represented states; exact Version 25 captures and unrepresented/ambiguous states
remain tracked in the manifest rather than being silently treated as exact parity.

## 2026-08-11 — Worker seed-isolation configuration repair

The worker Compose service now receives the same seed and workstation-bootstrap controls as the
backend. This is required for deterministic board-guided acceptance: seeded workers must not issue
provider-backed hydration requests that can contaminate a reused database, even when seeded API
read paths filter those rows. The deployment contract passes `9/9`, resolved configuration and
runtime container inspection confirm both seed flags, and the complete host-permitted backend gate
passes `1,367/1,367` at `79.62%`. No visual criterion or acceptance flexibility changed.

The canonical non-seeded worker was recreated with explicit `false` seed flags and the top-down
acceptance slice passed `10/10`, covering SPX proxy labelling, SPY/RSP, canonical holdings, all 11
sector industry surfaces, ratio editing, deep proxy/constituent traversal, and stable scrolling.
Provider-backed Nasdaq history requests succeeded; expected constituent-holdings 404s remained
structured unavailable paths.

## 2026-08-10 default Industries empty state

The default `US Top Down` Industries surface now distinguishes “no sector selected” from a
genuine missing industry-ETF mapping. It prompts the user to select a sector while preserving the
evidence-qualified missing-proxy message for a selected ETF. Browser regression `F8e-empty-industry`
passes, the current authenticated flow matrix passes `86/86`, and the four board-guided default
shell baselines pass after a controlled seeded refresh. No visual threshold or mask was changed.

## 2026-08-11 — Current-head Alembic round-trip revalidation

The current migration graph, including `f2a3b4c5d6e7` (provider entitlement revisions) and
`f4a5b6c7d8e9` (durable instrument reconciliation issues), passed an isolated PostgreSQL
`upgrade head -> downgrade -1 -> upgrade head` cycle. The disposable database was removed
afterward; the branch workstation database was not touched. This closes the current migration
revalidation slice. Acceptance flexibility used: **None**. The exact-build/unrepresented visual,
provider-entitlement breadth, native physical-monitor, beyond-bounded endurance, and final-audit
gaps remain open.

## 2026-08-11 — Runtime provider-boundary and excluded-menu audit

The current branch Compose services are healthy: backend health reports `ok` with
`e2e_seed_instruments=false` and `e2e_seed_market_data=false`, and the frontend shell returns
successfully on its branch port. Provider-neutral and entitlement boundary tests pass `18/18`;
the authenticated browser acceptance that excluded trading, brokerage, options, news, ratings,
earnings, financial statements, and consolidated real-time capabilities from the primary menu
passes `1/1`. Recent service logs contain no tracked 5xx, traceback, `MissingGreenlet`, constraint,
critical, fatal, unhandled, or error signatures; one transient startup Redis retry warning
resolved and did not recur. Acceptance flexibility used: **None**. Remaining visual/reference,
provider breadth/live-entitlement, native-monitor, beyond-bounded endurance, and final-audit gaps
remain open.
## 2026-08-12 — Study Lab editor contract

The unified Python editor remains a native textarea with a keyboard-operable SDK suggestion
listbox. Completion supports focus/input discovery, ArrowUp/ArrowDown selection, Enter/Tab
insertion, and Escape dismissal. A role-changing ARIA experiment was reverted after the browser
acceptance flow proved that Chromium exposed the control as a combobox and broke the established
Study Lab textbox contract. The focused editor suite passes `3/3`, full frontend Vitest `706/706`,
type/build/diff checks pass, and the no-cache rebuilt authenticated Study Lab promotion flow passes
`1/1`. This is a repository-controlled compatibility repair. The richer editor semantics remain
an explicitly tracked `REF-STUDY-LAB-V25` gap; represented visual evidence uses the accepted
230-image board and controlled seeded fixture, with no threshold, mask, or product criterion
relaxed.
## 2026-08-12 — Watchlist membership and keyboard scope

The workstation watchlist surface now covers the Version 25-style multi-selection membership path:
select multiple canonical rows, copy them to another personal list, move them atomically, preserve
metadata/order, and recover cleanly from invalid destinations. The shell also exposes a focusable
keyboard scope for typing-to-symbol-search behavior. Focused and full browser acceptance is green;
the remaining parity limitation is visual/reference coverage for exact-build and unrepresented
states, not this interaction contract.
## 2026-08-13 — Shell Shift+Space hydration race repaired

The real browser F8k-shift failure was a repository-controlled race: a delayed
workspace snapshot could overwrite a newer explicit symbol traversal with SPY.
Traversal now uses the loaded shell draft as its anchor and replays a newer
explicit shell intent after hydration. The focused WorkstationView suite passes
23/23 and the isolated authenticated Chromium path passes 1/1. This is a defect
repair, not acceptance flexibility. The remaining full-matrix gateway 502s and
all documented visual/provider/historical/monitor/endurance gaps remain open.
The follow-up core workstation slice (top-down, SPX proxy, relative strength and
ratios, industry/constituent drill-down, Study Lab/Python reuse, and keyboard
navigation) passes 14/14 in 56 seconds.

## 2026-08-13 — Canonical bootstrap rollback and provider-sweep containment

The unseeded worker bootstrap had a repository-controlled operational defect:
per-symbol provider rollback expired retained ORM identities and could erase the
newly-created canonical universe, while the initial 2010 history sweep was too
large for a startup task. The bootstrap now commits identity materialisation
before hydration, retains primitive IDs, reloads instruments after rollback, and
uses an explicit configurable two-year startup lookback. Focused bootstrap/ARQ
coverage passes 11/11. The prior exit-137/502 run remains failure evidence until
the rebuilt deployment is revalidated; no product, visual, or acceptance
criterion was relaxed.
# 2026-08-13 fresh-stack browser evidence note

The provider-bootstrap rollback fix is covered by focused backend tests (`11/11`). The subsequent
fresh-stack authenticated browser retry is not counted as parity evidence: repeated Nginx `502`
responses occurred during E2E provisioning/reset, with one backend restart and health-check startup
observed. The restricted browser launch also hit a host Mach-port permission boundary. No visual or
functional criterion was relaxed; rerun parity only after a stable backend health window.

## 2026-08-14 canonical deployment revalidation

The previously unstable fresh deployment was revalidated after the bootstrap rollback and bounded
startup repair. Backend health reported both E2E seed flags false, frontend health returned HTTP
200, and the complete authenticated Chromium workstation matrix passed `140/140` in `7.0m`.
Frontend Vitest `817/817`, uPlot contract `45` files, visual policy `26` assertions, type/build,
and backend `1438/1438` at `80.17%` also passed. The board-guided visual track remains accepted
for represented states; exact/unrepresented visual, provider/live-entitlement, historical,
native-monitor, endurance, and final-audit gaps remain open and are not silently promoted.

## 2026-08-14 — Python editor live suggestion semantics

The unified Python editor now announces the suggestion count and active completion through a
polite atomic status while preserving the native textarea, `aria-autocomplete="list"`, listbox,
and active-descendant contract. Focused component coverage is `4/4`, focused authenticated editor
coverage is `1/1`, and the adjacent Study Lab/Python/Results slice is `12/12`. This is a
repository-controlled accessibility refinement; `REF-STUDY-LAB-V25` remains open for exact or
unrepresented visual evidence and no acceptance threshold or mask changed.

## 2026-08-14 — Unified Python SDK autocomplete contract

The editor completion catalog now mirrors the supported isolated-runtime namespaces: prepared
`market` and `benchmark_*` accessors, supported `ta` helpers, `stats.positive_close_streaks`,
the four `research` helpers, and all typed `output` artifact methods. Unsupported suggestions
(`ta.atr` and `stats.percentile`) were removed. Component coverage is `5/5`, authenticated
editor coverage is `1/1`, adjacent Study Lab/Python/Results coverage is `12/12`, and the full
frontend gate is `818/818` with `make test-fe`, type-check, and build green. This is a contract
and discoverability correction; no visual threshold, mask, or acceptance flexibility changed.

## 2026-08-14 — Study Lab SDK reference alignment

The visible SDK reference now mirrors the executable isolated-runtime contract instead of
advertising unavailable helper families. It lists the prepared market and benchmark accessors,
`ta.indicator`/`sma`/`ema`/`rsi`, `stats.positive_close_streaks`, the supported research helpers,
and every typed output artifact. Focused Study Lab coverage is `22/22`, adjacent authenticated
coverage is `12/12`, and the full frontend/uPlot/visual-policy gate remains green. This is an
honesty/contract correction; the broader SDK expansion and `REF-STUDY-LAB-V25` visual gap remain
open, with no acceptance flexibility changed.

## 2026-08-14 — Unified Python stats namespace

The isolated runner now implements the plan-required deterministic `stats` surface for descriptive
statistics and open-ended studies: `mean`, `median`, `std`, `percentile`, `ranks`, `rolling`,
`correlation`, `regression`, and `distribution`, alongside the existing positive-close streak
helper. Inputs are finite and bounded, and invalid/empty/misaligned contracts are explicit. The
editor completion catalog and Study Lab reference expose the same methods, so the one Python
language no longer advertises helpers the runner cannot execute. Focused runner tests pass `71/71`,
editor/Study Lab tests `27/27`, the authenticated adjacent browser slice `12/12`, full frontend
Vitest `818/818`, combined backend coverage `1443/1443` at `80.17%`, and type/build/uPlot/
visual-policy checks pass. This is a genuine backend capability addition; no visual threshold,
mask, product criterion, or acceptance flexibility changed. `REF-STUDY-LAB-V25`, broader SDK and
research families, provider/live-entitlement breadth, historical/GICS, native-monitor, endurance,
and final-audit gaps remain explicitly tracked.

## 2026-08-14 — Unified Python research outcome helpers

The isolated runner now exposes deterministic `research.conditional_outcomes` and
`research.regimes` helpers over declared data only. Conditional outcomes report complete-horizon
sample sizes, central tendency, positive/negative counts, and raw aligned values. Regimes report
point-in-time up/flat/down classifications, coverage, counts, current state, and timestamped rows
with explicit lookback/threshold contracts. The unified editor and Study Lab reference expose the
same methods. Focused runner tests pass `75/75`, editor/Study Lab `27/27`, authenticated adjacent
browser `12/12`, full frontend `818/818`, combined backend `1447/1447` at `80.17%`, and the
type/build/uPlot/visual-policy checks pass. This is a genuine research capability addition; no
visual threshold, mask, product criterion, or acceptance flexibility changed. Broader research,
provider/live-entitlement, historical/GICS, native-monitor, endurance, and final-audit gaps remain
tracked.

## 2026-08-14 — Study Lab current-versus-history comparison

Study Lab now has a deterministic `research.historical_comparison` starter that places the current
observation inside a declared historical distribution. The runner returns sample size, current
value, mean/median/std, percentile rank, min/max, z-score, and range position, including explicit
empty, invalid, non-finite, and degenerate-distribution contracts. The same method is exposed by
the unified Python editor and visible SDK reference. Focused runner coverage is `77/77`, focused
editor/Study Lab coverage `27/27`, full frontend `818/818`, authenticated adjacent browser
coverage `12/12`, and authoritative backend coverage `1449/1449` at `80.17%`; type/build,
uPlot, visual-policy, and `make test-fe` remain green. This closes a plan-required comparison
capability without changing visual thresholds, masks, product criteria, or acceptance flexibility.
Exact/unrepresented Study Lab V25 visual evidence and broader provider, historical/GICS,
native-monitor, endurance, and final-audit gaps remain explicitly tracked.

## 2026-08-14 — Unified Python generic streaks

The unified Python SDK now exposes `stats.streaks(values, direction, inclusive?)` for deterministic
positive/negative consecutive-change studies. It validates finite numeric input and direction,
reports completed records, current state, longest/shortest/average lengths, and preserves the
legacy `stats.positive_close_streaks` compatibility helper. The factory negative-close study now
uses the shared helper rather than duplicating its loop. Focused runner coverage is `79/79`, focused
editor/Study Lab coverage `27/27`, full frontend `820/820`, authenticated browser coverage `12/12`,
and authoritative backend coverage `1451/1451` at `80.17%`; type/build, uPlot, visual-policy, and
`make test-fe` pass. This is a capability/contract increment only: visual thresholds, masks,
product criteria, and acceptance flexibility are unchanged. Exact/unrepresented Study Lab V25 and
broader provider, historical/GICS, native-monitor, endurance, and final-audit gaps remain open.

## 2026-08-14 — Study Lab current-history distribution renderer

The Current versus history factory starter now emits a typed historical-return histogram with the
current observation highlighted, an explicit sample-size metric, and the existing comparison table
and summary metrics. Focused Study Lab coverage is `22/22`, full frontend `820/820`, authenticated
Study Lab/Python/Results browser coverage `12/12`, and `make test-fe`, uPlot/visual-policy,
type-check, and production build pass. Acceptance flexibility used: `REF-STUDY-LAB-V25` original-
surface interim baseline and product-contract evidence; the board contains no authoritative Study
Lab capture. The gap remains open and no visual threshold, mask, product criterion, or acceptance
rule changed.
# 2026-08-14 — Study Lab 90/90 breadth thrust

- Added the plan-required transparent 90/90-style breadth study to the unified Python path. It
  evaluates declared-universe price and volume advances at the latest aligned observation, reports
  coverage and row-level exclusions, and qualifies only when both participation percentages meet
  the configured threshold. Missing or zero-baseline data is excluded rather than inferred.
- The factory starter, editor completion, SDK reference, focused source/runner contracts, and
  authenticated `F8p-90-90` browser acceptance are implemented. The original Study Lab surface
  remains under `REF-STUDY-LAB-V25`; no visual or acceptance threshold was relaxed.

## 2026-08-14 — Breadth authoring scope expanded beyond fixed metrics

The breadth surface is now governed as a general cross-sectional study authoring contract. The
user selects the universe, measured field, target/operator, alignment policy, and Boolean
composition independently, so “breadth” can mean (for example) the percentage of SPY-proxy
members above a 200-session average, within 1% of a rolling 52-week high, in a volume/volatility
state, or outperforming a benchmark/sector ratio. The UI and API must preserve these semantics in
the saved definition instead of hiding them behind metric-specific selectors.

The same immutable definition must expose aggregate history, per-member pass/fail state,
passing/failing drill-down, exclusions, coverage, provenance, point-in-time membership, and
reproducibility metadata. Where output contracts permit, it must be reusable as Study Lab output,
an independent uPlot pane/plot, a watchlist column/filter, EasyScan condition, Market Gauge,
alert, or export. The existing fixed metrics remain presets only. This is a requirements
expansion; the current historical slice does not yet close arbitrary Python composition, full
promotion targets, or representative ETF point-in-time browser acceptance.

## 2026-08-14 — Generic breadth composition and member drill-down

The reusable breadth contract now accepts nested `all`/`any`/`not` conditions and a scalar
comparison vocabulary for close, return, volume, RSI, moving-average distance, 52-week distances,
and relative strength. The isolated Python runner uses the same condition shape. The workstation
composer exposes measured field/operator/target and benchmark controls, and the result surface
provides pass/fail member drill-down with canonical symbol publication. This is board-guided
functional progress; the broad visual reference does not yet represent every condition-editor or
historical drill-down state, so those specific visual states remain tracked gaps.

## 2026-08-14 — Family-ratio workstation rendering

The family analytics contract is now reachable from the primary workstation rather than being
backend-only. In Market Breadth, selecting a benchmark-family universe opens a dedicated
relative-strength panel with explicit cap/equal/value/growth leg selection and an explicit market
benchmark. Each row preserves the ratio identity (for example `RSP/SPY`), latest value, aligned
point count, coverage, and loading/error/no-data state. The loader uses a stable
family/role/market/timeframe/adjustment cache key and guards against stale visibility and
generation responses.

When an older persisted or seeded response lacks the family registry, the frontend requests the
documented `/market-groups/us-benchmarks/children` contract and merges only its returned metadata.
It never hard-codes family symbols or falls back to SPY/QQQ. The focused browser test uses an
explicit deterministic response interception solely to make the pre-family fixture observable;
this is labelled interim fixture evidence and does not relax visual, provenance, or acceptance
criteria. The first failed browser attempt exposed an ambiguous selector and was repaired before
the authoritative rerun (`1/1`); full frontend Vitest (`823/823`), type-check, and production
build also pass.

Remaining parity gaps are provider-backed historical family evidence, all-leg batch analytics,
family-wide breadth/rotation/ranking, constituent drill-down, and exact/unrepresented Version 25
visual states. They remain open and must not be treated as closed by this UI integration.

## 2026-08-14 — All-leg family ratio composition

The family ratio API now supports an explicit `roles=cap_weight,equal_weight,value,growth` batch
selector. One request returns every available role against the family cap proxy and the selected
market benchmark, with aligned timestamps and no forward-fill. The response echoes requested and
resolved roles, canonical symbols, membership version, provenance, coverage, adjustment, and
labelled exclusions for missing mappings or instruments. The original single `role` query remains
available for compatibility.

The Market Breadth family panel uses this batch contract and keeps a focus-leg control without
re-fetching when the focus changes. This closes the role-by-role request gap, not the broader family
analysis requirement: provider-backed historical evidence, family breadth/rotation/ranking,
dispersion, and constituent drill-down remain open.

## 2026-08-14 — Family overview holdings readiness

The benchmark-family overview now distinguishes a mapped canonical ETF/proxy from a mapped leg
whose disclosed holdings are actually available. Each cap/equal/value/growth mapping carries the
selected holdings snapshot ID, composition date, known-at timestamp, source provider, completeness
state, row/resolution counts, and reported total weight. This makes the top-down UI able to show
whether `available` means identity-only or `holdings_available` means usable composition evidence,
without silently treating a current snapshot as historical truth. Focused Docker-backed family
overview/constituent coverage passes `2/2`; Ruff and diff checks pass. The first unprivileged Docker
attempt was an environment permission failure and was rerun successfully with elevated access.

This closes only the response-level readiness contract. Provider-backed population, historical
rebalance evidence, point-in-time taxonomy snapshots, and the visual/browser rendering of these
fields remain open. Acceptance flexibility used: **none**.

## 2026-08-14 — Breadth predicate authoring expansion

The visible custom breadth composer now exposes the backend's broader predicate vocabulary instead
of making moving-average and 52-week proximity the practical boundary. It supports trend direction
with fast/slow periods, RSI thresholds, volume-ratio thresholds, explicit relative-strength
thresholds/lookbacks, and the existing measured-field comparisons. The saved request still carries
the selected family/group/ETF-proxy universe, role, benchmark, timeframe, adjustment, point-in-time
policy, and Boolean composition, so the aggregate, member drill-down, and history use the same
definition.

Browser acceptance selected a benchmark-family leg, evaluated RSI and volume-ratio predicates, and
asserted their exact serialized parameters (`F8s-breadth-family-ratio`, `1/1`). Frontend Vitest
`824/824`, type-check, production build, backend breadth units `7/7`, and Ruff pass. The first
browser assertion used the wrong request-count assumption and was corrected before the authoritative
rerun; no product or acceptance criterion was relaxed.

Remaining gaps are arbitrary Python predicates in the visible composer, richer target-series and
cross-sectional target-scope controls, promotion to every compatible target, and provider-backed
family data population.

## 2026-08-14 — Benchmark-family issuer routing

The expanded family matrix now has explicit free-source issuer routing metadata for its configured
style and cap proxies. SPDR routes cover `SPYV`, `SPYG`, `MDY`, `MDYV`, `MDYG`, `SLYV`, `SLYG`, and
`SPTM`; iShares product identifiers cover `IJR`, `IWB`, `IWD`, `IWF`, `IWN`, `IWO`, and `IWV`.
The holdings refresh path can therefore select an issuer adapter from canonical product identity,
without ticker/name inference or a paid-provider dependency. Focused taxonomy/provider-route tests
pass `2/2` and Ruff passes.

This is routing readiness, not evidence that every route is currently populated or historically
complete. Live issuer retrieval, point-in-time rebalance history, QQQE/First Trust verification,
and browser-visible family holdings remain open. Acceptance flexibility used: **none**.

## 2026-08-14 — Family as-of selection and cache identity

The family breadth surface now exposes a dated `As of` selector derived from the independent
cap/equal/value/growth holdings snapshots returned by `/analysis/benchmark-families/{family_key}/coverage`.
The selected point-in-time is propagated to overview, coverage, constituent, ratio, and generic
breadth current/history requests. This makes a disclosed composition date a real analysis input,
not merely metadata displayed beside a latest snapshot.

The client cache identity includes the selected `as_of`, preventing a historical result from being
mistaken for the latest result. An unchanged authenticated browser acceptance run passed `1/1`
after this regression was repaired; store coverage is `57/57`, full frontend Vitest is `828/828`,
and type-check/build pass. Historical population, rebalance continuity, and complete all-family
browser evidence remain open and are still explicit acceptance gaps.

## 2026-08-14 — Family role technical snapshots

The family breadth surface now includes a role-aware technical strip backed by
`/analysis/benchmark-families/{family_key}/technicals`. Cap/equal/value/growth legs independently
report last price, RSI14, SMA20/50/200, 52-week position, volume ratio, freshness, and warnings,
with the same timeframe, adjustment, membership, and `as_of` semantics as ratios and breadth.
Unavailable mappings or bars remain visible on their own role and never collapse into a SPY/QQQ
fallback. Focused family integration `8/8`, store `58/58`, full Vitest `829/829`, type/build,
Ruff, and authenticated browser `1/1` pass. Historical population and the broader family ranking,
breadth, rotation, dispersion, and browser evidence matrix remain open.
