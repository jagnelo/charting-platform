# Project TODO Memory

### 2026-08-13 — Canonical bootstrap post-repair runtime revalidation

- [x] Rebuilt the branch-scoped non-seeded stack with
      `CORE_WORKSTATION_BOOTSTRAP_ENABLED=true`, `CORE_WORKSTATION_BOOTSTRAP_LOOKBACK_DAYS=730`,
      and both E2E seed flags disabled. All six services became healthy/running, migrations
      applied, and container inspection confirmed the worker received the same bootstrap contract.
- [x] Revalidated the affected real-user paths against the rebuilt stack: authenticated top-down,
      SPX proxy, SPY/RSP and sector ratios, live sector/industry/proxy/constituent drill-down,
      swing-analysis traversal, consecutive-close and configurable-high/low Study Lab studies,
      and watchlist freshness/error paths pass `15/15` in one serial Chromium worker. Backend and
      worker logs contain no audited bootstrap failure, traceback, 5xx, MissingGreenlet,
      UniqueViolation, critical, or fatal signature.
- [ ] The prior startup bootstrap repair is now runtime-revalidated, but full authenticated-matrix
      rerun and final acceptance audit remain open. Exact/unrepresented V25 visual states,
      provider/entitlement breadth, historical/GICS truth, native physical-monitor behavior,
      beyond-bounded endurance, and final requirement audit remain tracked. Acceptance flexibility
      used: **None** for this operational/functional revalidation.

### 2026-08-13 — Complete authenticated matrix after canonical bootstrap rebuild

- [x] Re-ran the complete authenticated `frontend/tests/e2e/flows.spec.ts` matrix against the
      rebuilt non-seeded stack with one serial Chromium worker. All `136/136` tests passed in
      `6.5m`, covering authentication, charting/templates/drawings, workspaces/pop-outs,
      linking/timeframes/cross-window cursors, US top-down benchmark/sector/industry/proxy/
      constituent analysis and ratios, Python/Study Lab/Results/promotions, scans/gauges,
      alerts/notes, freshness/error/recovery, legacy compatibility, unsupported-domain absence,
      and performance/containment.
- [x] Post-run backend and worker logs contain no audited traceback, HTTP 5xx, MissingGreenlet,
      UniqueViolation, IntegrityError, critical, fatal, or bootstrap failure signature. No test
      skip, visual threshold, mask, product criterion, or acceptance boundary changed.
- [ ] This closes the pending post-bootstrap browser gate, not the overall goal. Exact/unrepresented
      V25 visual states, provider/entitlement breadth, historical/GICS truth, native physical-
      monitor behavior, beyond-bounded endurance, and final requirement audit remain open.
      Acceptance flexibility used: **None**.

### 2026-08-13 — Add Strategy Lab MAE/MFE excursion distributions

- [x] Added bar-based maximum adverse excursion (MAE) and maximum favorable excursion (MFE)
      rows to Strategy Lab trade distributions. Calculations use the materialized adjusted OHLCV
      bars held by each trade, include entry/exit bars, preserve long/short semantics, and retain
      rows with explicit null values when bars are unavailable instead of silently changing the
      sample.
- [x] Added MAE/MFE histograms and a uPlot-only `ExcursionBars` result panel with sample count,
      average excursions, accessible labeling, resize cleanup, and empty-state behavior.
- [x] Validation: Strategy Lab units `10/10`; frontend focused component/view tests `30/30`; the
      exact Docker-backed watchlist integration test `1/1`; full backend units `1118/1118`; full
      frontend Vitest `772/772`; type-check; 474-module production build; uPlot contract (45
      primary files); Ruff; compileall; and `git diff --check` pass. The unprivileged integration
      attempt failed before setup at the Docker socket permission boundary and was superseded by
      the elevated rerun. Implementation commit `adf668d7` is pushed and synchronized.
- [ ] Continue the open goal gaps: exact/unrepresented V25 states, provider/entitlement breadth,
      historical/GICS truth, native physical-monitor behavior, beyond-bounded endurance, and the
      final requirement-by-requirement audit. Acceptance flexibility used: **None**.

### 2026-08-13 — Remove stale Strategy Lab numerical-SVG residue

- [x] Audited the current Strategy Lab result surface against the uPlot-only renderer contract.
      `StrategyResultChart` already owns all numerical result charts, but the view retained dead
      `.equity-chart polyline` CSS from the pre-uPlot implementation. Removed the unused selectors
      and expanded `tests/visual/validate-uplot-renderer-contract.py` to audit the Strategy Lab view
      itself, preventing that renderer residue from silently returning. This is a repository-
      controlled cleanup; no acceptance flexibility used.

- [x] Validate the cleanup: focused Strategy Lab tests `34/34`, full frontend Vitest `770/770`,
      type-check, 471-module production build, uPlot contract, and `git diff --check` pass. The
      initial path-context Vitest invocation found no files and is discarded as setup evidence;
      the corrected frontend-relative invocation is authoritative. Implementation commit
      `f02bb3f9` is pushed; operational evidence remains to be checkpointed before the next context.

### 2026-08-13 — Finalize checkpoint metadata semantics

- [x] Document the Git self-reference boundary: `ops/state.json` records the last known
      pre-record checkpoint, while post-push `git status --short --branch` and matching
      `git rev-parse HEAD`/origin hashes prove the enclosing operational-record commit. Do not
      create an endless metadata-only commit loop trying to record a commit's own SHA. No product
      acceptance flexibility used.

### 2026-08-13 — Enforce explicit changeset closure and synchronized workflow state

- [x] Strengthen `docs/agent-orchestration.md` with a named changeset-closure protocol. Each
      context must declare its owned files, pass focused validation, inspect and scope its staged
      diff, create and push a self-contained implementation commit, then create and push the
      operational-record checkpoint and verify matching local/remote hashes plus a clean tree
      before another context starts.
- [x] Define the only permitted dirty-tree state: the named current context is still in progress,
      every outstanding file/reason is recorded in the handoff, and an exact next action exists.
      Unlabelled dirty work is an operational defect; no-op audits also close cleanly without
      placeholder edits.
- [x] Correct stale `ops/state.json` checkpoint metadata to synchronized `191b8375`. No product
      acceptance threshold or flexibility rule changed; the active TC2000 goal and its existing
      gaps remain open. Acceptance flexibility used: **None**.

### 2026-08-13 — Current-source goal audit and focused workstation revalidation

- [x] Re-read the controlling goal and section 14; no scope, product boundary, visual threshold,
      mask, or acceptance rule was changed. The active single completion bar remains open.
- [x] Visual manifest validation, frontend Vitest `770/770`, type-check, and the 471-module build
      pass. Static audit found no new primary-menu dead control, implicit workstation yfinance
      path, numerical SVG renderer, or untracked visual gap.
- [x] The unprivileged browser launch failed before execution at the known macOS Chromium
      Mach-port permission boundary. The permitted elevated authenticated rerun passes `24/24`
      for top-down drilldown, ratios, linking/crosshairs/gestures, keyboard traversal, Python/
      EasyScan reuse, plot transfer, alerts, drawing menus, combo watchlists, and 125% containment.
- [ ] Continue the open goal gaps: exact/unrepresented V25 states, provider/entitlement breadth,
      historical/GICS truth, native physical-monitor behavior, beyond-bounded endurance, and the
      final requirement-by-requirement audit. Acceptance flexibility used: **None**.

### 2026-08-13 — Close private unified-Python attribute validation gap

- [x] Add mandatory per-changeset commit/push hygiene and `.git/index.lock` recovery to the
      canonical agent workflow. Completed contexts must be committed, pushed, and verified clean
      before the next context begins; sandbox-denied Git operations must use the permitted narrow
      elevated Git boundary after checking real repository permissions. No product acceptance
      flexibility used; this is an operational workflow correction.

- [x] API and isolated-runner validation now rejects all private attributes consistently, including
      pandas wrapper internals, before execution. Focused security/research `112/112`, code API
      integration `21/21`, backend unit `1116/1116`, rebuilt backend/worker/research-runner health,
      Study Lab browser `2/2`, service-log scan, Ruff, compileall, and diff checks pass. Acceptance
      flexibility used: **None**; V25 visual, historical/GICS, provider, hardware, endurance, and
      final-audit gaps remain open.

### 2026-08-13 — Align unified Python validation with the isolated runner

- [x] The API code validator now rejects sensitive ndarray/numerical-wrapper attributes using the
      same denylist as the isolated no-network runner. This closes the repository-controlled gap
      where `/code/validate` could persist code that failed only at execution. Code integration
      `21/21`, sandbox/research units `119/119`, backend unit `1114/1114`, frontend Vitest
      `770/770`, type-check/build, rebuilt service health, service-log scan, Ruff, compileall, and
      diff checks pass; rebuilt authenticated Study Lab validation/recovery flows pass `2/2`.
      Acceptance flexibility used: **None**; V25 reference, historical/GICS,
      provider, hardware, endurance, and final-audit gaps remain open.
- [x] Review and contextually commit the accumulated work into categorized implementation/artifact
      and operational-record commits separating
      Python
      validation, backend platform, generated-artifact hygiene, frontend workstation, and
      documentation/acceptance evidence. The default sandbox denied `.git/index.lock`, but the
      permitted elevated Git boundary succeeded safely; the branch is pushed and verified
      synchronized with origin.

### 2026-08-13 — Preserve ETF disclosure exclusions in constituent coverage

- [x] ETF constituent snapshots now retain the disclosed holding denominator and expose stable
      cash, derivative, unresolved, and non-equity exclusion codes/messages while keeping eligible
      canonical equity rows available. Focused integration `2/2`, focused backend units `493/493`,
      backend unit `1106/1106`, rebuilt services, authorized browser slice `7/7`, Ruff, compileall,
      and diff checks pass. Acceptance flexibility used: **None**; historical/GICS, provider,
      exact/unrepresented V25, native-monitor, endurance, and final-audit gaps remain open.

### 2026-08-13 — Current-source workstation matrix and readiness contract

- [x] Rebuilt the branch-scoped stack with instrument and market-data seeding disabled; backend,
      frontend, PostgreSQL, Redis, worker, and research-runner services are healthy/running.
- [x] Corrected the E2E `ChartPage.goto()` readiness oracle: continuous workstation polling and
      WebSocket traffic make `networkidle` invalid; the helper now waits for the visible dock host
      and each flow waits for its exact state. Full authenticated Chromium acceptance passes
      `136/136`, including top-down analysis, ratios, linking, pop-outs, uPlot, Python/Study Lab,
      watchlists, alerts, notes, gauges, legacy compatibility, and recovery states.
- [x] Post-run backend/worker/research-runner logs contain no unexpected traceback, critical/fatal,
      integrity, or 5xx signatures. Acceptance flexibility used: **None**.
- Remaining exact/unrepresented V25, historical/GICS, provider-entitlement, native-monitor,
  longer-endurance, and final-audit gaps remain open and tracked.

### 2026-08-13 — Provider contract and Docker maintenance evidence

- [x] ETF provider contract slice passes `2/2`: 496 registered adapters agree with the registry
      metadata and the 352 native/live-backed adapters have concrete route-test dispositions;
      network-bearing probes remain opt-in and are not represented as live evidence.
- [x] Frontend Vitest `770/770`, type-check, and the 471-module production build pass after the
      readiness-helper correction.
- [ ] Docker maintenance remains open: `docker system df` reports 13.214 GB excluding volumes;
      the goal-requested global `docker system prune -af` was rejected as broad destructive
      cleanup by the safety boundary. No deletion or workaround was attempted.

### 2026-08-13 — IronHorse empty-download fallback repair

- [x] The opt-in live ETF matrix found the official IronHorse/Conductor page returning an empty
      200 response from its declared CSV download. The adapter now treats empty/malformed current
      rows as a failed native route and uses SEC EDGAR reconstruction when a CIK is available,
      preserving the route failure and fallback provenance.
- [x] Added an exact empty-200 regression; focused adapter tests pass `3/3`, backend unit suite
      passes `1106/1106`, compileall and Ruff pass. The full opt-in live matrix remains honest at
      `368 passed, 1 skipped, 6 failed`: Vident/MM VAM 502, JPMorgan timeout, Donoghue Forlines
      503, Lazard 404, and the remaining external route evidence are not silently accepted data.
- Acceptance flexibility used: **None**. Provider outages and route changes remain explicit
  capability gaps; the fallback repair is repository-controlled and closed with tests.

### 2026-08-13 — Rebuilt-stack top-down revalidation

- [x] Rebuilt backend/worker images after the IronHorse fallback repair; branch services returned
      healthy/running. Docker-backed workspace integration passes `26/26`.
- [x] Focused authenticated browser slice passes `21/21`, covering SPY/RSP relative strength,
      sector→industry→constituent drilldown, ratios, swing-analysis flow, Study Lab, watchlist
      freshness/error states, breadth, rotation, plot/condition transfer, and Market Gauge.
- Acceptance flexibility used: **None**. This is current-source behavior evidence; external
  provider routes, historical truth, board gaps, native monitor, endurance, and final audit remain.

### 2026-08-13 — Final-image adapter parity check

- [x] Final backend/worker rebuild is healthy; Docker-backed workspace integration passes `26/26`.
- [x] Representative browser checks from `frontend/` pass `7/7`: deep top-down drilldown,
      all-sector industry surfaces, Study Lab/Python, consecutive-close study, watchlist
      refresh/error, and plot-to-column transfer. The root-directory Playwright invocation was
      setup-only because no project configuration existed there; the frontend-directory rerun is
      authoritative.
- Acceptance flexibility used: **None**. Provider, historical, board, monitor, endurance, and
  final-audit gaps remain open.

### 2026-08-13 — Keep ETF enrichment strict at the industry boundary

- [x] Corrected the provider enrichment and snapshot re-ingestion paths so a sector-only
      `EquityDetail` remains incomplete for industry analysis and a provider profile can populate
      `industry` only from its actual `extra["industry"]` field. Sector metadata is retained
      separately when supplied and is never copied into `industry`.
- [x] Added regression coverage proving sector-only metadata is not promoted, field provenance is
      preserved, and holdings with sector-only details remain eligible for a bounded industry
      enrichment attempt. ETF-resolution units pass `16/16`; taxonomy units pass `9/9`; Docker-
      backed workspace integration passes `26/26`; Ruff and compileall pass.
- Acceptance flexibility used: **None**. This closes a repository-controlled write-path defect;
  official GICS/historical completeness, provider breadth, exact/unrepresented V25 states,
  hardware, endurance, and final audit remain open.

### 2026-08-13 — Keep sector-only metadata out of the industry taxonomy

- [x] The shared classification helper now requires an actual industry value. A sector label is
      never promoted to an industry merely because the provider omitted industry metadata; the
      same strict rule applies to historical profile snapshots.
- [x] Added unit coverage for current and historical sector-only observations and route coverage
      through the mixed ETF exclusion fixture. Taxonomy units pass `9/9`; workspace integration
      passes `26/26` with `--no-cov`; frontend Vitest passes `770/770`; type-check/build, Ruff,
      compileall, and diff checks pass.
- Acceptance flexibility used: **None**. Official GICS/historical completeness, provider breadth,
      exact/unrepresented V25 states, hardware, endurance, and final audit remain open.

### 2026-08-13 — Reject inconsistent resolved holding identities

- [x] A holding marked `is_resolved=true` without a canonical constituent instrument ID is now
      treated as `unresolved_holding`. It cannot inflate industry classification coverage or appear
      eligible in composition while being impossible for the constituent endpoint to return.
- [x] Added the inconsistent-identity regression to the explicit ETF exclusion fixture. Focused
      workspace integration passes `26/26` with `--no-cov`; authenticated seeded F8e.1 deep
      drill-down passes `1/1`; Ruff and compileall pass.
- Acceptance flexibility used: **None**. Historical/GICS, provider breadth, exact/unrepresented
      V25 states, hardware, endurance, and final audit remain open.

### 2026-08-13 — Revalidate constituent disclosure against browser and visual acceptance

- [x] Rebuilt the branch-scoped stack with deterministic market fixtures and validated the changed
      selected-industry constituent surface through the authenticated `F8e.1` deep drill-down:
      `1/1` passed, including industry/proxy/constituent loading, target selection, and keyboard
      traversal.
- [x] The complete board-guided `tc2000_visual.spec.ts` matrix passes `104/104` in `5.2m` across
      1920×1080 and 2560×1440 at 100% and 125% display scale after the provenance-footer change.
      No screenshot baseline, mask, threshold, or product criterion changed.
- Acceptance flexibility used: **board-guided visual authority plus controlled deterministic seeded
      market data**, as allowed by the acceptance-governance policy. This validates represented
      states only; exact pinned-build/unrepresented V25 states, historical/GICS, provider breadth,
      native multi-monitor behavior, longer endurance, and final audit remain open.

### 2026-08-13 — Disclose exclusions in the selected industry constituent tool

- [x] The constituent drill-down now retains eligible but unclassified holdings through an
      outer profile join, so missing canonical classification cannot silently disappear or inflate
      `classification_coverage`. The API regression proves a mixed snapshot reports `0.5` coverage,
      returns only the classified target-industry instrument, and carries the same explicit cash,
      derivative, unresolved, and unclassified exclusion codes through both composition and
      constituent responses.
- [x] The workstation constituent pane now shows the exclusion codes in a dense, tooltip-backed
      provenance footer and includes the excluded count in its label. This keeps the TC2000-style
      drill-down honest about why the visible list is smaller than the underlying ETF snapshot.
- [x] Focused backend integration tests pass `26/26` (the initial single-file coverage command also
      passed the tests but correctly failed its repository-wide coverage threshold at `28.61%`;
      the authoritative rerun used `--no-cov`); frontend focused tests pass `64/64`, full Vitest
      passes `770/770`, type-check/build, Ruff, compileall, and diff checks pass.
- Acceptance flexibility used: **None**. Official GICS-compatible/historical coverage, provider
      breadth, exact/unrepresented V25 states, hardware, endurance, and final audit remain open.

### 2026-08-13 — Correct industry constituent classification coverage semantics

- [x] Fixed the industry-constituent API so `classification_coverage` means classified eligible
      rows divided by all eligible rows. It no longer reports the selected industry's membership
      share as classification coverage; selected membership remains represented by the constituent
      list and its counts.
- [x] Unified current/historical source fallback while computing returned classification systems,
      preventing a historical constituent response from mixing current and snapshot provenance.
      Industry API regressions pass `2/2`; backend unit tests pass `1103/1103`; frontend focused
      tests pass `64/64`; type-check/build, Ruff, compileall, and diff checks pass.
- Acceptance flexibility used: **None**. Historical completeness, official GICS-compatible mapping,
      provider breadth, exact/unrepresented V25 states, hardware, endurance, and final audit remain open.

### 2026-08-13 — Preserve industry-constituent snapshot lineage in the workstation

- [x] The industry-constituent API now returns its own composition date, known-at time, source,
      classification systems, and classification coverage. The frontend store preserves that
      contract and the constituent tool displays the selected industry's lineage instead of the
      parent ETF holdings label.
- [x] Focused taxonomy/workspace API tests pass `9/9`; full backend unit tests pass `1103/1103`;
      frontend type-check, focused component tests `64/64`, and 471-module production build pass;
      Ruff, compileall, and diff checks pass.
- Acceptance flexibility used: **None** for this contract repair. Historical completeness, official
  GICS-compatible mapping, provider breadth, exact/unrepresented V25 states, hardware, endurance,
  and final audit remain explicit gaps.

### 2026-08-13 — Fix classification-source edge semantics and task-ledger integrity

- [x] Removed an orphan duplicate task ID from `ops/tasks.yaml`; a parser assertion now confirms
      all `268/268` task IDs are unique.
- [x] Tightened top-down classification semantics: a provider label with no namespace is retained
      as `unknown` and rendered as `Unknown source`, distinct from a genuinely `Unclassified` row.
      This prevents missing provenance from being mistaken for missing classification.
- [x] Added the unknown-namespace regression. Taxonomy/workspace regressions pass `8/8`; frontend
      type-check and focused VirtualWatchlist coverage pass; Ruff, compileall, YAML parsing, and
      `git diff --check` pass.
- Acceptance flexibility used: **None**. The seeded controlled-fixture and board-guided evidence
      remain unchanged; official GICS/historical coverage, exact/unrepresented V25 states, provider,
      hardware, endurance, and final-audit gaps remain open.

### 2026-08-13 — Surface classification provenance in the Industries tool

- [x] The Industries pane now exposes each row's source-labelled classification system (or
      `Unclassified`), provides a tooltip explaining the evidence, and shows aggregate classified
      coverage plus excluded-row count. This prevents SEC SIC/provider-native/fixture data from
      being visually mistaken for official GICS.
- [x] Seeded acceptance data now carries explicit `controlled_fixture` classification provenance.
      Focused seeded drill-down passes `2/2`; the complete four-environment board-guided visual
      matrix passes `104/104` in `5.1m`; frontend Vitest remains `770/770`; type-check/build,
      seed/taxonomy tests `9/9`, Ruff, compileall, and diff checks pass.
- Acceptance flexibility used: **controlled deterministic seeded fixture data plus board-guided
  visual authority** for this UI/browser advance. The fixture label is rendered in the product and
  is not an official GICS claim. Official GICS-compatible mapping, complete historical coverage,
  exact/unrepresented V25 states, provider breadth, hardware, endurance, and final audit remain open.

### 2026-08-13 — Preserve classification-system provenance through profile reconciliation

- [x] Repaired the canonical profile path so `classification_system` survives provider snapshot
      reconciliation and is retained in `EquityDetail.field_provenance` for sector and industry.
      SEC SIC, provider-native, and other source-labelled values can now be distinguished by the
      top-down API instead of becoming indistinguishable or `unknown` after a merge.
- [x] Added a persisted snapshot → reconciliation regression. Focused taxonomy/persistence tests
      pass `17/17`; full backend unit tests pass `1102/1102`; Docker-backed integration tests pass
      `302/302`; frontend Vitest `770/770`; type-check, 471-module build, Ruff, compileall, and
      diff checks pass.
- Acceptance flexibility used: **None** for the repair. The Docker-backed integration rerun used
      the permissioned Docker environment after the unprivileged socket boundary failed before
      test setup; official GICS-compatible mapping, historical profile breadth, and provider
      coverage remain open gaps rather than being inferred from this fix.

### 2026-08-13 — Board-guided four-environment visual matrix

- [x] Rebuilt the isolated seeded stack, applied migrations, and ran the complete board-guided
      `tc2000_visual.spec.ts` matrix across 1920×1080/100%, 1920×1080/125%, 2560×1440/100%,
      and 2560×1440/125% display environments: `104/104` passed in `5.4m` with one worker.
- [x] The run includes shell/layout, factory workspaces, linking, charts/uPlot, watchlists,
      ratios, scans/gauges, Python/Study Lab, alerts/notes, pop-outs, stale/loading/error states,
      overlap checks, and deterministic screenshot baselines.
- Acceptance flexibility used: **board-guided visual authority plus controlled deterministic
  seeded fixture data**. This is permitted by the acceptance-governance policy and is not an
  exact-build approval. Exact-build/permission review, unrepresented or ambiguous V25 states,
  hardware multi-monitor behavior, and remaining board gaps stay explicitly open.

### 2026-08-13 — Final matrix after shared drag and alert consistency repairs

- [x] Repaired the shared same-document plot-drag fallback and watchlist visibility path. The
      fallback remains bounded and actual drops clear it; accepted drops now always reassert the
      indicator definition and visible-column key, including an already-known indicator.
- [x] Repaired alert-list consistency by retaining successful indicator creations as pending rows
      until the invalidated canonical query observes them. API failures remain visible as errors.
- [x] Focused F8u real-drag stress passes `5/5`; F11a/F11b/F11c pass `3/3`; the complete current
      authenticated Chromium `flows.spec.ts` matrix passes `136/136` in `7.4m` with one worker.
      Full frontend Vitest passes `770/770`; plot-drag unit coverage passes `6/6`; type-check and
      production build pass.
- Acceptance flexibility used: **None**. The browser tests exercise the real drag/drop and alert
      paths; no visual threshold, board authority, seeded substitution, or product boundary was
      relaxed. Exact/unrepresented V25 states, historical/GICS coverage, provider-entitlement
      breadth, native multi-monitor behavior, longer endurance, issuer-route breadth, and final
      audit remain open.

### 2026-08-13 — Final authenticated matrix after chart interaction repairs

- [x] Repaired the browser-only F8u plot drag race by synchronizing the real plot-library
      close/reopen lifecycle and retrying the same custom-MIME drag path once when Chromium drops
      the payload during the fixed-menu transition. No synthetic configuration mutation was added.
- [x] Hardened F8n gesture acceptance to wait on the actual latest-bar recovery affordance after
      bounded historical pans, and synchronized F9h on the real Add Tool menu before opening Python
      Library. These are deterministic browser-journey repairs, not product-scope relaxations.
- [x] F8u stress passes `5/5`; the complete authenticated Chromium `flows.spec.ts` matrix passes
      `136/136` in `7.1m` with one serial worker. The run includes the full top-down, chart,
      linking, Python, Study Lab, watchlist, alerts, pop-out, legacy, and failure-state coverage.
- Acceptance flexibility used: **None**. The DnD retry remains the real user path; no visual
      threshold, board authority, product criterion, seeded substitution, or unsupported domain was
      relaxed. Exact/unrepresented V25 states, historical/GICS coverage, provider-entitlement
      breadth, native multi-monitor behavior, longer endurance, and final audit remain open.

### 2026-08-13 — Enforce local-canonical workstation chart reads

- [x] Traced the rebuilt non-seeded browser logs and found that workstation charts used the
      local route only for their first page, while transformed-bar requests, left-pagination,
      and latest refresh could fall back to the provider-hydrating OHLCV endpoints.
- [x] Added an explicit `local_only` API contract and propagated it through raw, transformed,
      paginated, and refreshed chart reads. Workstation chart stores now retain the mode across
      pagination and refresh; legacy chart callers retain the existing provider-hydrating default.
- [x] Added regression coverage for raw and transformed local-only routes plus workstation
      pagination. Focused backend market-data/router tests pass `13/13`; frontend Vitest passes
      `763/763`; type-check, 471-module production build, Ruff, compileall, and diff checks pass.
- [x] Rebuilt and reran targeted authenticated top-down workstation flows: `5/5` passed. Recent
      backend logs contain only the intended `/ohlcv/local/SPY/D1` read; no Nasdaq hydration or
      generic workstation OHLCV call was observed. Provider hydration remains available only to
      explicit maintenance/backfill and legacy paths.
- Acceptance flexibility used: **None**. This is a repository-controlled provider-boundary
  correction; no visual threshold, mask, board authority, seeded acceptance, or product scope was
  relaxed.

### 2026-08-13 — Close personal-watchlist add hydration leak and revalidate bounded endurance

- [x] Personal watchlist additions from the workstation now propagate the local-only read mode
      through their eager price refresh. Legacy watchlist/dashboard callers retain the explicit
      provider-hydrating default.
- [x] Focused watchlist store coverage passes `21/21`; the full frontend Vitest suite passes
      `765/765`; type-check and the 471-module production build pass. The rebuilt authenticated
      `F8y` personal-watchlist flow passes `1/1`.
- [x] Governed `TC2000_POP_OUT_CHURN_ROUNDS=100` performance workload passes `2/2` in `2.8m`;
      source tool/canvas counts remain bounded and browser diagnostics are clean.
- [ ] This does not close the longer-duration endurance gap. The 100-round run is explicitly
      bounded-stress evidence under the acceptance policy. Acceptance flexibility used:
      **bounded stress in place of indefinite soak**; longer-duration closure evidence remains a
      named goal gap.

### 2026-08-13 — Add real-user swing-analysis journey and close plot-menu interception

- [x] Added an end-to-end swing-trader journey covering benchmark/sector trend inspection,
      relative-strength comparison, indicator insertion, drawing-tool activation, industry and
      constituent traversal, ratio refresh, and keyboard continuation through the focused list.
- [x] The first browser run exposed a real UX defect: inserting an indicator left the fixed Plot
      Library menu over the chart and intercepted drawing gestures. Plot insertion now closes the
      menu and restores focus to its trigger; the component regression passes `19/19`.
- [x] Rebuilt browser journey passes `1/1` after correcting its oracle to reopen the library only
      for inspection, close it before the drawing gesture, and target uPlot's interactive `.u-over`
      surface rather than the underlying drawing canvas. The same journey verifies indicator state
      is restored when returning to the annotated sector after constituent traversal. Acceptance
      flexibility used: **None** for this code/test correction.

### 2026-08-13 — Validate real uPlot gestures and latest-bar recovery

- [x] Added an authenticated browser journey for real wheel zoom, trackpad-style horizontal pan,
      chart-surface identity preservation, and the `Go to latest bar` recovery control.
- [x] The permissioned rerun passes `1/1`; browser-level gestures change the rendered view without
      recreating the uPlot surface, and the latest control restores the current window. Browser
      diagnostics remain clean.
- Acceptance flexibility used: **None** for product behavior. The first unprivileged launch was
      blocked before test execution by the known macOS Chromium Mach-port permission boundary;
      the permissioned rerun is the authoritative browser evidence and the setup limitation remains
      recorded in the operations ledger.

### 2026-08-13 — Close per-instrument indicator persistence race in swing workflow

- [x] Strengthened the swing-trader browser journey to require both RSI and drawing restoration
      after sector → industry → constituent → sector navigation, rather than checking RSI only.
- [x] Repaired the repository-controlled race: indicator insertion can precede canonical instrument
      hydration, and stale debounced writes could otherwise overwrite a later instrument state.
      Pending saves are now queued until the instrument ID exists, stale saves are cancelled on
      navigation, and payloads are copied before persistence.
- [x] Focused chart-store/Plot Library coverage passes `54/54`; frontend type-check/build pass;
      rebuilt authenticated swing journey passes `1/1` with the persisted drawing-count oracle.
- [x] Post-repair authenticated regression slice passes `4/4` (`F8n-gesture`, strengthened swing
      analysis, personal-watchlist activation, and combo-list persistence). The direct queued-save
      contract now passes in focused store coverage `55/55`.
- Acceptance flexibility used: **None**. The earlier missing restoration assertion was treated as
      a real product defect, fixed under the goal tie-break, and verified without weakening the flow.

### 2026-08-13 — Current-head audit, static gates, and stale bootstrap-state reconciliation

- [x] Re-read the active goal and controlling acceptance policy. The current branch-scoped
      backend reports healthy with `e2e_seed_instruments=false` and
      `e2e_seed_market_data=false`; PostgreSQL, Redis, worker, research-runner, and frontend
      services are running.
- [x] Re-run the complete frontend Vitest suite: `762/762` tests pass across `95` files. The
      expected stderr from deliberately simulated API failures remains test-owned and produces
      no failing assertion.
- [x] Re-run frontend `type-check` and production build: both pass; Vite transforms `471`
      modules successfully.
- [x] Re-audit visible placeholders, unsupported domains, skipped browser cases, provider
      boundaries, visual manifest/gap partitioning, and uPlot-only enforcement. No new
      repository-controlled dead control, implicit yfinance path, numerical SVG renderer, or
      untracked visual gap was found in this pass.
- [x] Supersede the older bootstrap `repair-in-progress` wording with current evidence: the
      provider-backed startup starvation fix is deployed with opt-in hydration, and the later
      non-seeded core slice (`42/42`) plus current healthy stack supersede the earlier transient
      502/restart observation. The historical failure remains retained as diagnostic evidence.
- [ ] Continue the single completion bar. Remaining gaps are unchanged: exact or unrepresented
      V25 visual states, historical profile completeness and official GICS-compatible mapping,
      wider free-provider entitlement/live evidence, native physical multi-monitor validation,
      longer endurance, broad issuer-route completion, and final operational/documentation audit.
- [ ] Docker image storage is above the cleanup threshold. The broad `docker system prune -af`
      request was rejected by the execution safety boundary because it would delete unused
      objects across local stacks; no workaround or destructive cleanup was performed. A safer
      scoped cleanup can be attempted separately if required, without treating this as a product
      or acceptance blocker.
- Acceptance flexibility used: **None**. No board substitution, seeded visual data, physical
      monitor substitution, or bounded-stress substitution was used in this advance.

### 2026-08-13 — DFTT issuer-route re-probe and deterministic adapter boundary

- [x] Re-probed the official Donoghue Forlines ETF homepage and DFTT product/alternate official
      domains. The homepage is reachable, but the fund-scoped product route returns Cloudflare
      HTTP `403`; alternate official fact-sheet domains return HTTP `503`.
- [x] Inspected the public homepage for a complete declared holdings artifact. No executable
      fund-scoped CSV/XLS/PDF route was exposed there, so no non-issuer substitute or fabricated
      membership was promoted.
- [x] Existing DFTT adapter behavior remains policy-correct: it verifies the issuer product page,
      discovers the fund-scoped AJAX CSV, retries through the browser-compatible transport, and
      falls back to conditional SEC reconstruction only when entitled identifiers exist. Its two
      deterministic parser/transport regressions pass `2/2` with `--no-cov`.
- [ ] Keep DFTT as an external issuer-access gap. Closure requires a reachable complete official
      route or an independently entitled canonical holdings source; the current 503/403 evidence
      is not a repository-controlled defect and does not block the workstation goal.
- Acceptance flexibility used: **None**. No fixture was promoted as live evidence and no visual
      or product criterion was relaxed.

### 2026-08-13 — Authoritative backend, visual, and Study Lab gate revalidation

- [x] Docker-reachable backend unit suite passes `1099/1099` with `70.08%` total coverage
      against the configured `55%` threshold; integration suite passes `302/302`.
- [x] Visual manifest validation, acceptance-policy validation, and the uPlot renderer contract
      pass with unchanged `0.5%` screenshot, `1px` geometry, and `DeltaE2000 2` thresholds.
- [x] Board-guided visual acceptance passes `104/104` across 1920x1080 and 2560x1440 at
      100%/125% display scale. This uses the explicitly approved visual-reference-board
      authority and controlled seeded data for represented states; it does not close exact-build
      or unrepresented-state gaps.
- [x] The non-seeded core workstation acceptance slice passes `42/42`, covering top-down
      drill-down, ratios, links/crosshairs, pop-outs, keyboard traversal, watchlists, Study Lab,
      notes, coverage, breadth, rotation, reports, scans, gauges, library lifecycle, and legacy
      failure semantics.
- [x] The earlier `39/42` result was investigated. Focused F8g and F8o/F8p reruns passed, and
      the complete slice then passed; the failures were transient provisioning/browser-runtime
      conditions rather than a reproducible product defect. No code workaround, threshold,
      mask, or acceptance criterion was changed.
- [x] Provider-boundary audit confirms new-workstation capability chains exclude implicit yfinance
      fallback; yfinance remains limited to explicitly legacy/options capability paths.
- [ ] Continue the full goal audit. Remaining gaps are explicit: exact pinned-build or
      unrepresented V25 visual states, historical profile completeness and official
      GICS-compatible classification, broader free-provider entitlement evidence, native
      multi-monitor placement, longer endurance, and final operational/documentation audit.

### 2026-08-13 — Explicit ETF holding exclusion semantics and full browser revalidation

- [x] Added one canonical exclusion classifier for ETF-derived top-down analysis. Cash,
      currency/collateral, derivatives, unresolved rows, and other non-equity rows are now
      returned as explicit exclusion codes rather than silently entering industry/proxy or
      constituent membership.
- [x] Industry classification coverage counts only eligible equity rows; proxy candidate and
      constituent responses retain candidate/row exclusion reasons so the UI can distinguish
      unavailable membership from an empty industry.
- [x] Added Docker-backed regression coverage for cash, derivative, and unresolved holdings;
      the selected taxonomy/ETF/workspace backend suite passes `48/48`. Ruff, compileall,
      `git diff --check`, frontend type-check, production build, and frontend Vitest (`762/762`)
      pass.
- [x] Rebuilt the authenticated branch stack and ran the complete Chromium matrix: `134/134`
      passed, including top-down drill-down, ratios, Study Lab, linking, pop-outs, legacy
      routes, alerts, scans, and recovery paths.
- [ ] The overall goal remains open. Historical profile coverage, official GICS-compatible
      mapping, provider-entitlement breadth, exact or unrepresented V25 states, physical
      multi-monitor placement, longer endurance, and final audit remain tracked gaps. No
      acceptance flexibility was used for this correction; the existing board-guided visual
      authority/controlled seeded-data flexibility remains documented rather than hidden.

### 2026-08-13 — Point-in-time classification snapshots and live revalidation

- [x] Historical ETF industry/proxy/constituent reads now consult the latest immutable provider
      profile snapshot known by the requested `as_of` cutoff when current flattened metadata is
      newer or lacks a timestamp. Source-labelled classification systems remain explicit; current
      SEC SIC is not presented as historical GICS.
- [x] Constituent enrichment now retains the raw provider profile snapshot alongside the current
      `EquityDetail` projection. Added a source-labelled snapshot unit test and a historical industry
      integration assertion; the selected taxonomy/ETF/workspace suite passes `47/47`.
- [x] Fix-first regression: the bounded maintenance test used a reused `NVDA` fixture identity and
      became order-sensitive after the broader suite. It now uses a unique maintenance-only symbol;
      isolated and full selected runs pass. Ruff, compileall, and `git diff --check` pass.
- [x] Rebuilt live backend/worker after a scoped Docker disk-full recovery (only individually
      verified dangling images removed; named data volumes preserved). Health is green and the live
      workstation slice passes `22/22`.
- [ ] Remaining gaps are narrower but still open: historical snapshots are only as complete as the
      free metadata observations retained, SEC SIC remains non-GICS, exact/unrepresented V25 visual
      states, provider entitlement breadth, native-monitor behavior, longer endurance, and final
      requirement audit remain tracked. No visual/product acceptance flexibility was used here;
      the disk-space recovery is recorded as environment remediation, not acceptance evidence.

### 2026-08-13 — Historical classification provenance contract and live workstation slice

- [x] Added a source-labelled classification helper for ETF industry/constituent reads. It
      normalizes only reviewed aliases, preserves the classification system, and rejects a
      historical `as_of` classification when the current canonical field has no observation or
      known-at timestamp, preventing present-day metadata from leaking into past analysis.
- [x] Added classification-system and coverage fields to industry composition contracts and
      preserved the source system even when a row is excluded as not known at the requested date.
- [x] Added deterministic unit and Docker-backed integration coverage for current and historical
      classification behavior: `5/5` selected tests pass. Frontend `type-check` and production
      build pass; live rebuilt backend/worker health is green.
- [x] Ran the live non-seeded workstation slice covering Python/Study Lab reuse, pop-outs,
      top-down benchmark/sector/industry/proxy drill-down, ratios, and keyboard/link behavior:
      `22/22` Chromium tests pass.
- [ ] This closes a data-contract defect, not the overall TC2000 workstation goal. Historical
      classifications remain unavailable unless point-in-time field evidence exists; current SEC
      SIC metadata is still not an official GICS replacement. Exact/unrepresented V25 visual
      states, broader provider entitlements, native-monitor placement, longer endurance, and the
      final complete acceptance audit remain tracked gaps.

### 2026-08-13 — Resumable classification maintenance and complete workstation revalidation

- [x] Added an opt-in worker maintenance contract for missing ETF constituent classification.
      It processes only the latest non-fixture snapshot for profiles that still have missing
      sector/industry metadata, applies a hard per-profile enrichment cap, records isolated
      provider failures, and advances past already-complete profiles so repeated runs converge
      rather than repeatedly consuming the first profile batch.
- [x] Added configuration and Compose wiring for the bounded maintenance job, ARQ registration,
      weekly scheduling, disabled-by-default behavior, and focused worker/resolution coverage;
      targeted tests pass `12/12`, compileall and `git diff --check` pass.
- [x] Fixed a broad-suite acceptance selector that matched the shell `Go` control together with
      an industry row whose label began with `Go`; the exact control selector and isolated F7/
      F8k-type acceptance now pass `2/2`.
- [x] Rebuilt the isolated branch backend/worker, restored normal non-seeded runtime, and ran the
      complete canonical authenticated browser matrix: `134/134` passed in `9.2m`.
- [x] Ran the complete board-guided visual matrix: `104/104` passed across 1920x1080 and
      2560x1440 at 100% and 125% display scale. Acceptance flexibility used: **board-guided
      visual authority plus controlled seeded data for represented states**. This does not claim
      exact pinned-build approval for every image or cover unrepresented states.
- [ ] Remaining goal gaps are unchanged and explicit: exact/unrepresented V25 visual states,
      official GICS-compatible historical classification, unresolved/cash/derivative holdings,
      provider entitlement breadth/terms, point-in-time historical truth, native physical-monitor
      behavior, longer endurance, and the final complete audit. The normal non-seeded backend is
      healthy after visual validation; no product criterion, threshold, mask, or gap was hidden.

### 2026-08-13 — Core ETF membership and live top-down drill-down repair

- [x] Applied reviewed symbol-to-issuer metadata before adapter probes. SPY, RSP, all 11
      Select Sector SPDR ETFs, and the curated iShares/VanEck/ SPDR industry proxies now
      resolve through free issuer routes; bootstrap requests persisted canonical holdings
      snapshots with provenance rather than fixtures.
- [x] Changed unresolved dated ETF refreshes from opaque HTTP 500s to structured `409`
      capability responses; focused API regression coverage passes `3/3`.
- [x] Added bounded SEC EDGAR SIC-derived classification enrichment for resolved constituents,
      with field provenance and profile caching. Existing snapshots are reloaded safely for
      reconciliation without lazy-load or duplicate provider-symbol failures. Focused
      bootstrap/resolution/provider coverage passes `103/103`.
- [x] Reconciled the live benchmark and sector snapshots. XLK/XLB/XLRE/XLU now expose industry
      rows; the focused non-seeded top-down browser slice passes `8/8`, and adjacent
      keyboard/linking/Python/Study Lab paths pass `7/7`.
- [ ] Classification remains explicitly SEC SIC, not official GICS; unresolved/cash/derivative
      rows and remaining unclassified rows remain visible with exclusions. Enrichment is
      bounded per interactive request and needs a durable scheduled continuation for full
      universe coverage and historical point-in-time classifications.
- [ ] Acceptance flexibility used: **none for visual/product criteria**. Live free issuer
      routes and SEC metadata were used as the canonical supporting-data path. Board-guided
      represented-state visual authority, exact/unrepresented visual, provider-entitlement,
      historical truth, native-monitor, longer-endurance, and final-audit gaps remain open.

### 2026-08-13 — Provider bootstrap starvation repair and browser evidence

- [x] Made provider-backed workstation history/holdings hydration explicitly opt-in
      (`CORE_WORKSTATION_BOOTSTRAP_ENABLED=false` by default). API startup still materialises
      canonical identities/taxonomy; enabled maintenance runs retain bounded lookback, per-symbol
      rollback, and provenance. Focused worker/config/deployment tests pass `20/20`, compile and
      resolved Compose inspection pass.
- [ ] Re-run the isolated canonical browser matrix after Docker acceptance stacks are reduced. The
      prior rerun proved Study Lab validation/run, but promotion was interrupted by a backend restart
      while concurrent charting stacks generated Docker memory pressure; an earlier run also exposed
      sector/holdings 404 coverage limits in the unseeded path. These are not UI passes and are retained
      as runtime/provider evidence.
- [ ] Flexibility used in this advance: **none for product acceptance**. The provider bootstrap default
      is an operational scheduling correction, not a data-quality waiver. Board-guided visual evidence
      plus controlled seeded fixtures remain the documented interim visual track; live provider breadth,
      exact/unrepresented V25 states, historical truth, native monitor, endurance, and final audit stay
      open.

### 2026-08-13 — Fresh-stack browser revalidation outcome (superseded diagnostic)

- [x] The rebuilt backend/worker images start, but the focused authenticated rerun again encountered
      repeated Nginx `502` responses during E2E provisioning/reset. Container inspection recorded one
      backend restart and a health-check startup window, so this run is invalid as product acceptance
      evidence and is retained as a diagnostic failure. A restricted Playwright attempt also failed before page creation at the host Chromium
      Mach-port permission boundary; the permitted retry reached the app but hit the same gateway
      instability. No failure was suppressed or reclassified as success. Later authoritative
      non-seeded core evidence passes `42/42`, and the current branch stack is healthy; this older
      run is superseded rather than treated as a current blocker.
- [x] Focused bootstrap/ARQ coverage remains `11/11`; the later bounded-lookback/opt-in hydration
      correction has `20/20` worker/config/deployment coverage. No criterion, visual threshold,
      mask, or acceptance flexibility changed.

### 2026-08-13 — Virtual watchlist status/control glyph parity

- [x] Replace the saved-column-set delete text control with shared deterministic `WorkstationGlyph`
      geometry and render cell-level coverage warnings as semantic warning geometry with a title,
      while retaining the unavailable value and canonical warning code.
- [x] Correct the two watchlist unit oracles to assert warning geometry/message semantics rather
      than the platform-dependent Unicode warning string; focused VirtualWatchlistTool coverage
      passes `64/64`, full frontend Vitest passes `756/756`, type-check, and production build pass.
- [x] Rebuild the seeded stack and validate the real Columns/Sets interaction `1/1`; the affected
      board-guided visual case passes `4/4` across 1920×1080 and 2560×1440 at 100%/125% display
      scale with clean browser diagnostics.
- [ ] Continue the final acceptance audit. Acceptance flexibility used for this advance: **board-
      guided visual authority plus controlled seeded data for represented states**; exact-build/
      unrepresented, provider/live-entitlement, historical-truth, native-monitor, longer-endurance,
      and final-audit gaps remain open. No product criterion or visual threshold was relaxed.
- [x] Canonical unseeded `flows.spec.ts` rerun reached `133/134`: the corrected Study Lab failed-
      rerun fixture passes in the full run; the only failure was F8e.1a during transient gateway
      502s. Isolated F8e.1a then passes `1/1` in `15.3s`, so the transient run is retained as
      discovery evidence and not treated as a product failure.

### 2026-08-13 — Instrument Report disclosure glyph parity

- [x] Replace the description disclosure's platform-font `▴/▾` characters with shared deterministic
      chevron geometry while preserving the visible `more`/`less` labels, keyboard behavior, and
      accessible section/report semantics.
- [x] Focused Instrument Info and glyph coverage passes `26/26`; type-check passes. Rebuilt seeded
      runtime F8s-report interaction passes `1/1`; complete rebuilt board-guided visual matrix
      passes `104/104` in `5.1m` across all four display environments.
- [ ] Continue the final acceptance audit. Acceptance flexibility used: **board-guided visual
      authority plus controlled seeded data for represented states**; exact-build/unrepresented,
      provider/live-entitlement, historical-truth, native-monitor, longer-endurance, and final-
      audit gaps remain open. Two incorrect visual grep invocations found no tests and are discarded
      setup evidence; no product criterion, threshold, or mask was relaxed.

### 2026-08-13 — Indicator Panel membership/preset glyph parity

- [x] Replace platform-font membership and preset action symbols in Indicator Panel with shared
      deterministic geometry: list, scan, apply, and edit. Existing titles, handlers, and data
      semantics are unchanged; drawing-tool domain symbols remain intentionally distinct.
- [x] Extend glyph coverage to `26` geometry cases. Full frontend Vitest passes `756/756`, type-
      check, production build, and diff checks pass; rebuilt drawing/control browser slice passes
      `5/5`.
- [x] Rebuilt seeded board-guided visual matrix passes `104/104` in `5.1m` across all four display
      environments. The two no-test grep invocations are discarded setup evidence.
- [ ] Continue the final acceptance audit. Acceptance flexibility used: **board-guided visual
      authority plus controlled seeded data for represented states**; exact-build/unrepresented,
      provider/live-entitlement, historical-truth, native-monitor, longer-endurance, and final-
      audit gaps remain open. No criterion, threshold, or mask was relaxed.

### 2026-08-13 — Canonical post-glyph regression and gateway tie-break

- [x] The current unseeded full matrix reached `127/134`; the only seven failures were F8v plus
      F8w/F8w-a/F8x/F8x-library/F10/F11, with 502 gateway/provisioning evidence in the affected
      run. Backend logs for F8v show successful condition persistence, screener creation, indicator
      update, and workspace snapshot writes; no application error signature was present.
- [x] Revalidate every failed path independently after gateway recovery: F8v passes `1/1` in
      `5.6s`, and F8w/F8w-a/F8x/F8x-library/F10/F11/F11a/F11b/F11c pass `9/9` in `30.4s`.
- [ ] Retain the 127/134 result as discovery evidence and rerun a clean complete canonical matrix
      when the gateway remains stable. This is a runtime-stability follow-up, not a product or
      visual acceptance relaxation; board/seeded flexibility and all exact/provider/historical/
      hardware/endurance/final-audit gaps remain open.

### 2026-08-13 — Primary chart side-panel deterministic glyph parity

- [x] Replace remaining platform-font action symbols in the primary chart Indicator/Drawings/
      Alerts panel, Instrument Info, Instrument Alerts, and condition-group editor with shared
      `WorkstationGlyph` geometry, including section chevrons, visibility/lock state, menus,
      pause/resume/rearm, repeat, settings, and deletion controls.
- [x] Convert the warning glyph to CSS geometry rather than text content; preserve semantic labels
      and accessible control names.
- [x] Focused glyph/tool/condition coverage passes `34/34`; type-check and production build pass.
- [x] Freshly rebuilt canonical image validates the affected browser slice `10/10` (chart toolbar,
      report disclosure, alerts, and drawing interactions).
- [x] Freshly rebuilt seeded visual image validates the complete board-guided matrix: `104/104` in
      `5.1m` across 1920×1080 and 2560×1440 at 100% and 125% display scale.
- [x] Full frontend Vitest remains `756/756` across 95 files.
- [x] Fresh rebuilt canonical full authenticated matrix passes `134/134` in `7.3m` after the
      side-panel conversion; no shared-state, top-down, Study Lab, legacy, or browser-scale
      regression was introduced.
- [ ] Continue the final acceptance audit. Acceptance flexibility used: **board-guided visual
      authority plus controlled seeded data for represented states**; exact-build/unrepresented,
      provider/live-entitlement, historical-truth, native-monitor, longer-endurance, and final-
      audit gaps remain open. A browser slice run before the canonical image rebuild is superseded
      setup evidence and is not used as proof for this batch.

### 2026-08-13 — Deterministic primary chart/control glyph parity correction

- [x] Replace remaining platform-font control symbols in the primary workstation chart plot
      library, chart templates, ratio comparison chips, chart settings/help controls, and
      Relative Rotation warnings with the shared `WorkstationGlyph` CSS geometry component.
- [x] Add extended glyph geometry coverage and update the warning regression to assert semantic
      warning geometry rather than a platform-dependent Unicode character; focused coverage passes
      `63/63`.
- [x] Type-check and production build pass; affected authenticated browser flows pass `6/6`.
- [x] Re-run the complete board-guided visual matrix: `104/104` in `5.0m` across 1920×1080 and
      2560×1440 at 100% and 125% display scale. A first invocation detached before returning
      output and is discarded; the captured rerun exits `0` with all 104 cases passed.
- [x] Full frontend Vitest passes `756/756` across 95 files.
- [x] Re-run the complete non-seeded authenticated workstation matrix after the chart/rotation
      change: `134/134` in `7.3m`; no canonical functional, linking, top-down, Study Lab, legacy,
      or browser-containment regression was introduced.
- [ ] Continue the final acceptance audit. Acceptance flexibility used in this advance:
      **board-guided visual authority plus controlled seeded data for represented states**; the
      exact-build/unrepresented, provider/live-entitlement, historical-truth, native-monitor,
      longer-endurance, and final-audit gaps remain explicitly open. The initial repository-root
      Playwright invocation was setup-only and is not product evidence.

### 2026-08-13 — Post-busy-state full acceptance revalidation

- [x] Full frontend Vitest passes `746/746` across 95 files after the personal-watchlist busy
      contract correction; expected stderr is limited to deliberate failure-path assertions.
- [x] Rebuild the seeded visual stack on the documented alternate ports and rerun the board-guided
      matrix: `104/104` in `5.1m` across 1920×1080 and 2560×1440 at 100% and 125% display scale.
- [x] Reconfirm the complete canonical authenticated browser matrix remains `134/134` in `7.2m`.
- [ ] Continue the final acceptance audit. Acceptance flexibility used in this advance: **board-
      guided visual authority plus controlled seeded data for represented states**; exact-build,
      unrepresented-state, provider/live-entitlement, historical-truth, native-monitor, longer
      endurance, and final-audit gaps remain explicitly open.

### 2026-08-13 — Backend gate and runtime/storage audit

- [x] Docker-backed combined backend unit/integration gate passes `1390/1390` with `79.70%`
      coverage against the configured 75% threshold; 86 dependency warnings are non-failing.
- [x] Backend, worker, and research-runner logs contain no tracked traceback, application error,
      5xx, duplicate-key, integrity, fatal, out-of-memory, or sandbox-violation signatures after
      the acceptance runs; all branch services report healthy/running.
- [ ] Docker storage is above the cleanup threshold (`11.57GB` images, `3.01GB` reclaimable
      build cache). The requested host-wide `docker system prune -af` was rejected by the safety
      boundary because it could delete unrelated local stacks; no destructive workaround was
      attempted. A scoped cleanup or explicit host-level approval remains an operational follow-up.
- [ ] Continue the final acceptance audit. Acceptance flexibility used: **deterministic canonical
      fixtures/entitlement contracts where live provider credentials are unavailable**; live
      provider breadth and terms/quota evidence remain open.

### 2026-08-13 — Personal watchlist busy-state race closed

- [x] Fix the repository-controlled background-reconciliation race where a broadcast-triggered
      watchlist refresh marked an already-rendered selected personal list `aria-busy=true` after
      an Add mutation had completed. Busy state now reflects initial list selection or an active
      mutation, while retaining visible rows during canonical reconciliation.
- [x] Rebuild the frontend image; focused mutation/combo/error coverage passes `3/3`, and the
      complete post-fix canonical authenticated matrix passes `134/134` in `7.2m`. The preceding
      `133/134` run remains discovery evidence only. No acceptance threshold, mask, baseline,
      product criterion, or visual flexibility changed.
- [ ] Continue the final acceptance audit against the remaining documented exact/unrepresented
      visual, provider, historical-truth, native-monitor, endurance, and final-audit gaps.

### 2026-08-13 — EasyScan activation race closed

- [x] Fix the repository-controlled Add-tool race where EasyScan could remain unopened when
      Golden Layout had already exposed a usable active tab while the initial workspace promise
      was still settling. The shell now waits only when no active tab exists, preserving the
      existing bounded activation/retry behavior.
- [x] Rebuild the frontend image and verify the focused browser group passes `10/10` after the
      fix; the prior stable full run's `133/134` result is retained as discovery evidence.
- [x] Rerun the complete canonical matrix after the fix: `134/134` passed in `7.2m`. No
      acceptance threshold, mask, baseline, product criterion, or visual flexibility changed.

### 2026-08-13 — Shared shell/watchlist control geometry correction

- [x] Replace remaining platform-font Unicode control glyphs in the primary workstation shell and
      watchlist column editor (close, delete, reset, recent-symbol chevron, and left/right reorder)
      with reusable deterministic `WorkstationGlyph` CSS geometry. Semantic labels, keyboard
      behavior, and data/status glyphs remain unchanged.
- [x] Add geometry coverage for all supported control shapes; focused component, watchlist,
      tool-window, and pop-out tests pass `82/82`, with `vue-tsc --noEmit` green.
- [x] Rebuild the branch image and validate real interactions: focused shell/watchlist/containment
      browser coverage passes `15/15`; seeded board-guided visual matrix passes `104/104` across
      all four required environments.
- [x] Reproduce the late full-matrix personal-watchlist busy-state observation in isolation:
      `F8y` passes `1/1`. The remaining full-run failures were transient nginx 502 provisioning/
      reset responses plus that non-reproducible ordering-sensitive case; backend logs show normal
      2xx traffic and no application 5xx signature.
- [ ] Rerun the complete canonical matrix under a stable gateway and retain the transient 502 run
      as discovery evidence. Board-guided seeded visual flexibility was used for represented states;
      no threshold, mask, baseline, or product criterion changed. Exact/state/provider/native-
      monitor/endurance/final-audit gaps remain open.

### 2026-08-13 — Deterministic tool-window chrome parity correction

- [x] Replace shared tool-window header Unicode glyphs (drag, menu, maximize, float, close)
      with original CSS geometry so the workstation does not diverge from the dense V25 board
      language or depend on platform-font glyph rendering.
- [x] Add a component regression asserting all five geometry hooks are present and no temporary
      glyphs remain; focused ToolWindow tests pass `7/7`, TypeScript checking passes, and both the
      branch and seeded board frontend images rebuild successfully.
- [x] Revalidate the affected runtime: isolated F8r constrained-dock cases pass `10/10`, the
      canonical deep top-down drilldown passes `1/1`, and the seeded board-guided visual matrix
      passes `104/104` across all four display environments.
- [x] Final canonical non-seeded authenticated browser matrix passes `134/134` in `7.1m` after
      the correction; the earlier seed-flag mismatch is retained only as discarded setup evidence.
- [ ] Keep exact pinned-build/unrepresented visual states, native-monitor behavior, longer
      endurance, and external provider gaps in the ledger. Board-guided visual authority and
      seeded deterministic data were used for represented states; no threshold, mask, baseline,
      or product criterion was relaxed.

### 2026-08-13 — Post-repair frontend/performance acceptance revalidation

- [x] Frontend Vitest passes `735/735` across 94 files with coverage generated at 80.68%
      statements and 71.41% branches; expected stderr-only failure-path assertions are
      non-failing test output.
- [x] Permissioned current-source performance guard passes `3/3` in `2.6m`: 100,000-point
      uPlot zoom/pan, chart/canvas lifecycle recovery, and 100-round two-popout churn. The
      unprivileged Mach-port launch failure is setup-only evidence.
- [x] Post-run backend log audit has no tracked traceback, integrity, provider-exhaustion,
      Nasdaq-empty, or 5xx signatures; uPlot/visual-policy validators remain green.
- [ ] Continue final acceptance audit. Bounded stress, browser pop-out, board-guided represented
      states, and fixture/contract provider evidence remain explicit flexibility; exact/unrepresented
      V25 states, physical-monitor behavior, longer endurance, external provider gaps, and final
      audit remain open.

### 2026-08-13 — Current-source visual and contract revalidation

- [x] Re-run the uPlot renderer contract (`42` files), visual policy (`26` assertions with
      unchanged 0.5%/1px/ΔE2000-2 thresholds), Ruff, JSON/YAML parsing, and `git diff --check`.
- [x] Rebuild the isolated seeded visual stack on free ports after a setup-only PostgreSQL port
      collision, verify `e2e_seed_market_data=true`, and rerun board-guided visual acceptance:
      `104/104` across 1920×1080 and 2560×1440 at 100% and 125%. The unseeded invocation is
      discarded setup evidence; no visual baseline, mask, threshold, or flexibility changed.

### 2026-08-13 — Chart plot drag hydration race repaired

- [x] Fix the real F8u defect exposed after the rebuilt backend/frontend acceptance run: a
      late instrument-indicator hydration response could replace a plot added by the user while
      the Chart Plot Library was being dragged, detaching the source DOM node and losing the
      drag. The chart store now fences late hydration behind a user-dirty indicator state.
- [x] Add a store regression proving an RSI added during the pending indicator request survives
      the late response. Focused store tests pass `32/32`; plot-library and pop-out bindings pass
      `40/40`; repeated real-browser F8u validation passes `10/10`.
- [x] Rebuild the frontend image and rerun the full authenticated matrix: `134/134` passed in
      `7.2m`, including top-down workflow, Study Lab/Python reuse, links, pop-outs, alerts,
      notes, freshness, recovery, legacy, and exclusion paths.
- [ ] Continue the final acceptance audit. The first `133/134` run is retained as the defect
      discovery evidence; the post-rebuild run is authoritative. Existing exact/unrepresented
      V25 visual, external provider, historical-truth, native-monitor, beyond-bounded endurance,
      and final-audit gaps remain open.

### 2026-08-13 — Nasdaq EOD repair-boundary correction for top-down data

- [x] Fix the repository-controlled Nasdaq public EOD defect where a one-session repair
      request could return an empty ETF table, falsely exhausting the free-source provider
      chain. The adapter now widens the lower bound by three calendar days, keeps the exact
      caller interval after parsing, and keys its cache by both bounds so narrower and wider
      requests cannot collide.
- [x] Add deterministic regressions for the boundary and cache-key behavior; focused Nasdaq,
      market-data, and provider-runtime tests pass `30/30`, with lint and `git diff --check`
      clean.
- [x] Rebuild the canonical backend and worker. In-container verification returns the repaired
      session for `SPY`, `XLK`, and `AAPL`; the post-rebuild backend log scan has no new provider
      exhaustion, Nasdaq-empty, traceback, or 5xx signatures.
- [x] Re-run the Docker-reachable combined backend gate: `1390 passed`, 86 expected warnings,
      `79.70%` coverage against the 75% requirement.
- [ ] Continue the final workstation acceptance audit. This closes a supporting free-source
      data defect; it does not close the documented DFTT issuer-access, exact/unrepresented
      visual, native-monitor, beyond-bounded endurance, or final-audit gaps.

### 2026-08-13 — Fresh full acceptance after workspace-conflict recovery fix

- [x] Fix the real browser defect found by the rebuilt current-source matrix: conflict recovery
      created the recovery workspace but the workstation footer reduced the explicit preservation
      message to a generic 409 label. The footer now preserves and displays the recovery copy
      name and `local changes were preserved` wording.
- [x] Focused verification: TypeScript check, workspace-store/popout unit slice `71/71`, and
      focused `F8j-conflict` browser flow `1/1`.
- [x] Full rebuilt authenticated browser matrix: `134/134` flows passed in one serial Chromium
      worker. Full frontend Vitest remains `734/734`; production build, uPlot contract, and
      visual-policy validation pass.
- [x] Fresh Docker-backed backend unit/integration/coverage gate: `1388 passed`, `79.70%`
      coverage against the 75% requirement.
- [ ] Continue the final acceptance audit. No product, visual, threshold, mask, baseline, or
      data-quality flexibility was used for this repair; the previously documented board-guided
      visual flexibility and external DFTT route gap remain unchanged.

- [x] Revalidate current-source renderer and workstation performance: uPlot 100,000-point
      zoom/pan, chart-window/canvas lifecycle recovery, and 100-round two-popout churn pass
      `3/3` in `2.7m`.
- [x] Revalidate the live isolated research runner: all eight sandbox-denial probes, cgroup/tmpfs
      and concurrent-memory containment, orphan recovery after an isolated runner restart, and
      five bounded cancellation-versus-success rounds pass. Restart count remains unchanged
      during pressure testing.
- [x] Re-run the board-guided visual matrix against a fresh isolated seeded stack on free alternate
      ports: `104/104` across 1920x1080 and 2560x1440 at 100% and 125% display scale.
- [ ] Keep the documented flexibility explicit: board-guided visual authority plus controlled
      seeded data was used for represented visual states; browser pop-out and bounded stress are
      used for their respective hardware/endurance substitutions. Exact/unrepresented references,
      native physical-monitor placement, and beyond-bounded endurance remain open gaps.

### 2026-08-13 — Public ETF issuer route audit after supporting-data repairs

- [x] Repair the PGIM catalogue resolver so it searches the current official ticker-link
      markup even when unrelated legacy table entries are present; repair PDF row parsing for
      font-encoded identifier fragments such as `30730E+104`.
- [x] Add Tuttle DRMP's current IncomeBlast public fund API route while retaining the existing
      Google-Sheets route for products that still publish it. Normalize API percentage-point
      weights into canonical fractions and preserve source/provenance metadata.
- [x] Repair Wayfinder/Gladius CMBO resolution for the current `CMBO.html` page and its declared
      complete daily holdings CSV, while preserving the older inline embedded-dataset parser.
- [x] Add the bounded Keating `requests` transport fallback for the issuer's HTTP 403 response;
      it uses the same public page and does not add credentials or a secondary data provider.
- [x] Add deterministic regressions for the five repaired routes and run the complete adapter
      unit suite: `475 passed`.
- [x] Run the complete opt-in public issuer matrix with network access: `373 passed, 1 skipped,
      1 failed` after 500.00s. PGIM, Hashdex, Tuttle, Gladius, and Keating now pass live.
- [ ] Keep Donoghue Forlines DFTT explicitly open: its product page and fund-scoped AJAX holdings
      endpoint currently return access-limited HTTP 503 responses. The existing conditional SEC
      fallback remains the only non-issuer path and is not promoted as native evidence.
- [ ] Continue the final acceptance audit. Flexibility used here: **none for product or visual
      criteria**. The first network-restricted live invocation is discarded setup evidence; the
      permitted rerun is authoritative. The DFTT failure is recorded as an external issuer-access
      gap, not hidden or converted into a pass.

### 2026-08-13 Current-source and board-guided acceptance after race repairs

- [x] Repair workspace CRUD snapshot ordering: a queued Golden Layout snapshot can no longer
      overwrite a just-completed workspace rename/clone/delete mutation. Mutations now settle the
      outstanding save and invalidate queued snapshots; a store regression covers the ordering.
- [x] Repair shell workspace-menu keyboard focus by making the menu root a focusable ARIA menu
      container, so End/Home and item traversal have a deterministic focus target.
- [x] Repair the chart-plot-to-watchlist drag race: pointer events no longer close the plot library
      during drag, a transient source preview survives chart hydration, and active analysis drags
      preserve the source indicator stack. Repeated isolated F8u validation passes 10/10.
- [x] Validate the repaired product: workspace store 49/49, chart/plot focused units 49/49,
      frontend Vitest 734/734, type-check, production build, complete authenticated current-source
      browser matrix 134/134, and board-guided visual matrix 104/104 in 5.1m across 1920x1080 and
      2560x1440 at 100% and 125% display scale.
- [ ] Continue the final acceptance audit. The exact pinned-build/unrepresented V25 reference
      states, broader provider-entitlement and historical-truth breadth, native physical-monitor
      placement, longer endurance, and final backend/security/sandbox/service-log/repository audit
      remain open. Acceptance flexibility used: **board-guided visual authority plus controlled
      seeded data only** for represented visual states; no threshold, mask, baseline, or functional
      criterion was changed.

### 2026-08-12 Indicator configuration upsert race repair

- [x] Fix the real backend data-integrity defect found by the service-log audit: concurrent linked
      or floating charts could race through read-then-insert persistence and emit repeated
      `uq_user_instrument_indicators` duplicate-key errors.
- [x] Replace the PostgreSQL production path with one atomic `ON CONFLICT DO UPDATE` upsert,
      retain a non-PostgreSQL fallback, rebuild the branch backend, and verify health.
- [x] Validate focused endpoint coverage `2/2`, primary indicator-alert browser flows `3/3`,
      frontend Vitest `733/733`, type-check/build, and the full Docker-backed backend gate
      `1384/1384` at `79.68%` coverage. Post-rebuild backend/Postgres logs contain no new
      indicator duplicate-key signatures.
- [ ] Re-run the complete authenticated browser matrix after this backend change and retain the
      provider-entitlement warnings/live-source, historical truth, exact/unrepresented visual,
      native-monitor, endurance, and final-audit gaps. Acceptance flexibility used: **None**;
      the malformed guessed test-path invocation and focused-test coverage-threshold failure are
      discarded invocation evidence, not product results.

### 2026-08-12 Backend unit/integration audit boundary

- [x] Run the local backend unit suite: `1085 passed` (34 known warnings).
- [ ] Re-run the Docker-backed integration/coverage gate in a Docker-reachable environment.
      The current shell completed collection but 299 integration cases failed during
      `testcontainers` setup with Docker Unix-socket `PermissionError`; no application assertion
      failure is claimed from that run. The last authoritative Docker-backed combined result
      remains `1384/1384` at `79.69%` coverage.
- [ ] Keep live-provider, historical truth, sandbox/security, and final service-log audit gaps
      open until their environment-appropriate evidence is refreshed.

### 2026-08-12 Board-guided visual matrix after current-source repairs

- [x] Run the seeded board-guided `tc2000_visual.spec.ts` suite against the isolated acceptance
      frontend on port `18080`: `104/104` passed in `7.4m` across 1920×1080 and 2560×1440 at
      100% and 125% display scale.
- [x] Cover shell, menus, search, docking/tab/floating/restored/drag states, Study Lab, loading,
      stale/delayed/unavailable/partial freshness, provider-error, sandbox-error, and blocked
      pop-out recovery baselines without changing thresholds, masks, or baselines.
- [ ] Keep exact pinned-build/unrepresented state references (`REF-STATE-VARIANTS` and related
      board gaps), provider/historical, native-monitor, endurance, and final-audit work open.
      Acceptance flexibility used: board-guided reference authority plus controlled seeded data;
      this is represented-state evidence, not exact-build or live-provider proof.

### 2026-08-12 Full current-source authenticated matrix after shell/workspace repairs

- [x] Re-run the complete non-seeded `flows.spec.ts` matrix against the rebuilt branch frontend
      and canonical backend: `134/134` passed in `7.1m` with one worker.
- [x] Confirm the matrix includes authentication, charts/templates/drawings, shell/menu keyboard
      behavior, persisted workspaces, linking/timeframes/cross-window cursors, US top-down ratios
      and drill-down, Python/Study Lab/promotions, scans/gauges, alerts/notes, freshness/errors,
      pop-outs/recovery, legacy/excluded boundaries, and performance/containment.
- [x] The prior single F9h Python Library failure is superseded by this complete current-source
      pass; isolated F9h and the preceding Python slice also passed. No threshold, mask, baseline,
      product criterion, or acceptance flexibility changed.
- [ ] Continue backend/security/sandbox, board visual, provider/historical, native-monitor,
      endurance, and final repository acceptance gates before completion.

### 2026-08-12 Shell Escape ownership, chart geometry, and workspace CRUD hardening

- [x] Repair the real workstation Escape boundary: shell menus now dismiss during keyboard
      capture even when a nested workspace listbox stops bubbling; chart-local Escape remains
      untouched when no shell menu is open, and the originating shell trigger regains focus.
- [x] Add focused workspace-list Escape regression coverage; workstation bindings pass `22/22`.
- [x] Align the chart price-scale context-menu oracle with the rendered `.u-over` edge after
      preceding template/narrow-layout mutations; isolated and sequence validation pass.
- [x] Harden persisted workspace CRUD acceptance against durable test-state contamination by
      selecting the default workspace and using a unique run-scoped rename/clone name while
      preserving the real create/rename/clone/switch/delete path.
- [x] Validate current-source browser evidence: workspace/chart/EasyScan/shell slice passes
      `10/10` after rebuild, and isolated workspace CRUD passes `1/1`; no visual threshold, mask,
      baseline, or product criterion changed.
- [ ] Re-run the complete authenticated matrix and retain exact/unrepresented visual, provider,
      historical, native-monitor, endurance, and final-audit gaps.

### 2026-08-12 Chart context-menu sequence geometry repair

- [x] Reproduce the `F9c3-keyboard` failure after the preceding narrow and bottom-edge chart
      cases; the product menu was not reached because the persisted compact layout left the
      fixed coordinate outside the rendered price-scale gutter.
- [x] Apply the fix-first oracle repair: restore the required desktop viewport and derive the
      right-click from the current `.uplot-wrapper` edge, keeping the gesture inside the wrapper
      while targeting the rendered gutter. No product code, visual threshold, mask, baseline, or
      acceptance criterion changed.
- [x] Validate isolated `F9c3-keyboard` (`1/1`) and the complete affected chart/shell sequence
      (`17/17`) with the permitted current-source browser environment.
- [x] Validate the broader frontend gate: Vitest `733/733`, `vue-tsc --noEmit`, and the 468-module
      production build pass. The first `npm run test:unit` invocation was an invalid script name
      and is retained only as an invocation observation.
- [ ] Continue the full authenticated matrix and final acceptance audit; this localized oracle
      repair has no remaining product risk beyond the existing visual/provider/hardware/endurance
      gaps.

### 2026-08-12 Typed symbol-search hydration and keyboard-selection repair

- [x] Preserve a newer user-entered symbol draft while late route/linked-symbol hydration
      completes; do not close the combobox or cancel its canonical search request while the editor
      owns focus.
- [x] Add deterministic browser coverage for sequential typing, readiness semantics,
      `aria-activedescendant` ArrowDown/ArrowUp traversal, Enter selection, and dismissal.
- [x] Validate current-source `F8i-search-keyboard` `1/1`, adjacent shell/history/workspace/context
      keyboard flows `5/5`, workstation bindings `22/22`, full frontend Vitest `733/733`,
      type-check, and production build. No visual threshold, mask, baseline, or product criterion
      changed.
- [ ] Keep keyboard-selected-search styling under `REF-STATE-VARIANTS`; controlled fixture
      interaction evidence does not close the missing pinned-build state reference.
- [x] Add and pass a non-seeded canonical backend search check for XLK (`F8i-search-canonical`
      `1/1`). The first failure was an over-specific locator against the option's multi-line
      rendered text; the backend response was directly inspected and confirmed `q=XLK` with XLK
      data before the oracle was corrected. This is an acceptance-oracle repair, not a relaxed
      product assertion.

### 2026-08-12 Workspace listbox keyboard ownership repair

- [x] Make the persisted workspace list a keyboard-operable ARIA listbox with stable active
      descendant state, Home/End/arrow traversal, activation, and trigger-focus recovery.
- [x] Fix the event-boundary race where the opening `ArrowDown` bubbled into the newly mounted
      menu and focused `New` instead of the workspace list. The trigger now stops the opening
      event before the menu's generic action handler can consume it.
- [x] Validate focused workstation bindings `22/22`, full frontend Vitest `733/733`, type-check,
      production build, and neighboring real-browser shell/workspace/keyboard flows `3/3` against
      the rebuilt current-source frontend. No visual threshold, mask, baseline, or product
      criterion changed.
- [ ] Keep exact pinned-build V25 keyboard/selected/disabled state references and remaining
      provider, historical-truth, native-monitor, endurance, and final-audit gaps open.

### 2026-08-12 Persisted workspace management in the primary shell

- [x] Add workspace-level list, create, clone, switch, rename, and delete controls while
      preserving the existing tab/layout operations and default-workspace deletion guard.
- [x] Reuse the existing authenticated `/workspaces` CRUD/clone/delete contracts and keep startup
      hydration request-compatible; the initial extra list request caused four existing store
      regressions and was removed in favor of current-workspace hydration plus menu-time refresh.
- [x] Validate workspace store CRUD coverage `48/48`, workstation bindings `22/22`, combined focused
      regression `70/70`, type-check/build, and real-browser `F9d-workspaces` `1/1`.
- [x] Force Golden Layout dock replacement when switching persisted workspace IDs so tools from the
      previous workspace cannot remain mounted under the new workspace name; focused `70/70` and
      rebuilt browser `F9d-workspaces` `1/1` remain green.
- [x] Validate the current frontend after the shell addition: full Vitest `733/733` across 94 files,
      type-check/build, affected browser flows `2/2`, complete board-guided visual `104/104`, and
      final canonical browser `132/132` in `7.2m`. Earlier F9c3, F8u, and F8r-breadth interaction
      races were isolated, repaired at the test/activation boundary, and rerun successfully. No
      visual baseline, mask, threshold, or product criterion changed.
- [ ] Rerun the complete canonical browser matrix once more for one same-run `132/132` record;
      the isolated recovery proves the only failure was transient but is not silently promoted to
      a full-matrix pass.

### 2026-08-12 Chart-template rename and async library response repair

- [x] Add in-menu rename to the primary chart-template library while preserving stable keys,
      immutable versioning, chart configuration, import/export, clone, delete, and symbol identity.
- [x] Repair the backend library upsert response: refresh server-generated timestamps before
      async response serialization so in-place template updates cannot produce `MissingGreenlet`
      HTTP 500 errors.
- [x] Validate focused workspace-library integration `4/4`, chart-template component `7/7`,
      full frontend Vitest `732/732`, current-source browser `F9c` `1/1`, type-check/build,
      and diff-check.
- [x] Run the complete workspace API module `25/25` and authoritative combined backend gate
      `1384/1384` at `79.69%` coverage after the shared library response repair.
- [x] Re-run the complete current-source authenticated browser matrix after this localized repair;
      the canonical branch stack passes `131/131` in `6.6m` with one worker, including chart
      templates, workspace persistence, top-down analysis, Study Lab, alerts, linking, pop-outs,
      legacy boundaries, and narrow-dock checks.
- [x] Re-run the four-environment board-guided visual matrix against a fresh isolated seeded stack;
      the corrected run passes `104/104` in `5.1m` across 1920×1080 and 2560×1440 at 100% and
      125% display scale. An earlier invocation against the canonical unseeded stack was rejected
      by the fixture guard and is discarded setup evidence, not a visual result.
- [x] Validate Docker cleanup and repository state after the acceptance reruns: non-volume prune
      reclaimed `12.87GB`, named volumes were preserved, manifest/YAML/JSON parsing and
      `git diff --check` pass.
- [ ] Keep exact/unrepresented V25 template states, provider/entitlement, historical truth,
      native-monitor, endurance, and final-audit gaps open.

### 2026-08-12 Primary Alerts indicator creation, comparison, and linked-timeframe parity

- [x] Add direct Price/Indicator creation to the primary Alerts tool using the shared indicator
      catalog and existing `/alerts/indicator` contract; preserve price, EasyScan, chart-promotion,
      repeat, rearm, history, and status behavior.
- [x] Add fixed-value and indicator-vs-indicator comparison targets without changing the existing
      price-alert operator set; comparison indicator parameters are materialized from the shared
      catalog and the API payload omits threshold values for indicator targets.
- [x] Inherit the active linked timeframe while allowing explicit override; do not silently
      hard-code daily alerts.
- [x] Repair the 340px responsive hit-target regression exposed by the expanded editor.
- [x] Validate linked-alert units `10/10`, full frontend Vitest `731/731`, type-check/build,
      fixed-value and indicator-pair browser coverage `F11a`/`F11b`/`F11c` plus isolated
      `F8r-alerts-narrow` `4/4`, health, JSON parsing, and
      diff-check.
- [x] Re-run the complete current-source authenticated matrix after the final editor correction;
      `flows.spec.ts` passes `131/131` in `6.8m` with one worker, including `F11a`/`F11b`/`F11c`.
- [ ] Keep the earlier no-marker 129-case run documented as discarded evidence; it is superseded
      by the authoritative `131/131` current-source run.
- [ ] Continue exact/unrepresented V25 state, provider/entitlement, historical truth,
      native-monitor, endurance, and final-audit work.

### 2026-08-12 Primary factory/registry/renderer consistency audit

- [x] Cross-check backend factory tool types, frontend openable registry, and renderer branches;
      all supported tools match, including Study Results, and excluded domains remain absent.
- [ ] Keep this consistency check in the final audit after future tool additions.

### 2026-08-12 Authoritative backend unit/integration gate

- [x] Re-run backend unit/integration tests with Docker permission after the setup-only socket
      failure; authoritative result is `1383/1383`, `79.69%` coverage.
- [ ] Track and eventually remove/upgrade the 86 known third-party NumPy/pandas deprecation
      warnings; they are not current product failures.
- [ ] Continue provider breadth, historical truth, and final-audit work.

### 2026-08-12 uPlot and workstation performance guards

- [x] Validate real-browser 100,000-point uPlot zoom/pan without chart recreation.
- [x] Validate simultaneous pop-out recovery and repeated bounded multi-window churn; performance
      suite passes `3/3` in `15.9s`.
- [ ] Continue beyond-bounded endurance and native physical-monitor placement validation.

### 2026-08-12 Board-guided visual regression revalidated

- [x] Restore the missing frontend service after the setup-only connection-refused visual attempt;
      verify seeded `/health` before capture.
- [x] Run the unchanged four-environment visual suite: `104/104` passed in `7.9m` with one worker.
- [x] Keep baselines, masks, thresholds, tokens, and product criteria unchanged.
- [ ] Continue exact/unrepresented V25 state, `REF-STATE-VARIANTS`, provider/live-entitlement,
      historical, native-monitor, beyond-bounded endurance, and final-audit work.

### 2026-08-12 Canonical acceptance alignment, Market Breadth repair, and full matrix

- [x] Recreate the branch stack with `E2E_SEED_MARKET_DATA=false` for canonical holdings and
      proxy assertions; isolated repaired top-down flows pass `3/3`.
- [x] Repair Market Breadth’s 340px control-row overflow with dock-width wrapping; no calculation
      or acceptance threshold changed.
- [x] Validate the authoritative complete authenticated Chromium matrix: `128/128` in `9.5m`
      with one worker, including canonical top-down, ratios, drill-down, Study Lab/Results,
      docking/pop-outs, linking, keyboard, legacy boundaries, and narrow-dock checks.
- [ ] Keep the environment distinction explicit: seeded fixtures are labelled deterministic
      evidence only; canonical acceptance requires non-seeded provider-backed data. Continue
      tracking exact/unrepresented V25 states, provider/live-entitlement breadth, historical truth,
      native-monitor, beyond-bounded endurance, and final-audit gaps.

### 2026-08-12 Study Results restored to primary Add Tool registry

- [x] Register the implemented `research_results` tool in `OPENABLE_WORKSTATION_TOOLS` so persisted
      Study Results can be opened from the primary Add tool menu.
- [x] Validate focused store/results coverage `57/57`, full frontend Vitest `728/728`, type-check,
      production build, and rebuilt authenticated Add tool → Study Results/results flows `2/2`.
- [ ] Keep exact V25 Results styling under `REF-STUDY-LAB-V25`; the first stale-image browser run
      was discarded, and no visual baseline, threshold, mask, or acceptance criterion changed.

### 2026-08-12 Persisted Study Results state guidance

- [x] Replace raw persisted-run status text with human-readable labels and state-specific guidance.
- [x] Preserve diagnostics/logs and expose snapshot/latest rerun recovery for failed/canceled runs;
      verify focused units `10/10`, full frontend Vitest `728/728`, type-check/build, and rebuilt
      authenticated `F8t-results` `1/1`.
- [ ] Keep exact V25 Study Results state styling tracked as `REF-STUDY-LAB-V25`; no baseline,
      threshold, or mask was changed. No behavior acceptance flexibility used; board-guided
      composition and controlled data remain the declared visual limitation.

### 2026-08-12 Study Lab failed/canceled recovery states

- [x] Label durable queued/running/completed/failed/canceled states and provide explicit recovery
      guidance with snapshot/latest reruns for failed and canceled runs.
- [x] Validate focused units `22/22`, rebuilt browser cancellation/failed-recovery/results `3/3`,
      full frontend Vitest `727/727`, type-check/build, and affected visual case `4/4`.
- [x] Review and update only the two changed 1080p structured-result snapshots; no threshold or
      mask changed.
- [ ] Keep `REF-STUDY-LAB-V25` and exact V25 state styling gaps open. Flexibility used:
      board-guided Study Lab composition and controlled seeded data.
- [x] Re-run the complete seeded authenticated Chromium matrix: `125/127` executed tests with two
      intentional skips in `5.5m`; all existing workstation/top-down/Study Lab paths remain green.

### 2026-08-12 Live ETF membership evidence clarified

- [x] Isolated the current non-seeded canonical ETF membership and drill-down contract: `3/3`
      passed for SPY/RSP/XLK holdings, all sector industry surfaces, and complete sector drilldown.
- [x] Classify broad-run holdings `404` records as expected negative/fallback traffic; do not make
      a speculative provider change without a failing canonical contract.
- [ ] Continue broader ETF issuer, historical/provider-entitlement, and live-source coverage work.

### 2026-08-12 Current-head non-seeded operational workstation gate

- [x] Rebuild the branch stack with `E2E_SEED_INSTRUMENTS=false` and
      `E2E_SEED_MARKET_DATA=false`; services healthy and migrations applied.
- [x] Run the complete authenticated Chromium matrix: `126/126` in `6.7m` with one worker,
      including live top-down analysis, ratios, drill-down, links, charts, Python/Study Lab,
      scans/gauges, notes/alerts, pop-outs, legacy boundaries, and performance/containment.
- [x] Audit service logs: only expected negative-path `401`/`404` and client-cancelled `499`
      records; no tracked unhandled runtime error.
- [ ] Keep board/reference state variants, provider/live-entitlement breadth, historical truth,
      native-monitor, beyond-bounded endurance, and final-audit gaps open.

### 2026-08-12 Alerts and Python Library narrow-dock coverage

- [x] Add constrained 340px geometry/internal overflow checks for Alert creation and Python Library
      creation controls; both pass `1/1` without speculative production CSS changes.
- [ ] Keep exact/state, provider/live, historical, native-monitor, endurance, final-audit, and
      `REF-STATE-VARIANTS` gaps open. Flexibility used: board-guided dense composition and
      controlled seeded data.

### 2026-08-12 Top-down acceptance-oracle sequence hardening

- [x] Scope ratio selection/legend assertions to visible row-bearing surfaces and constrain the
      actual Relative Rotation surface before geometry measurement.
- [x] Validate focused ratio/rotation `2/2` and broader top-down/dense-tool `13/15` with two
      intentional skips; exact semantic assertions remain intact.
- [ ] Keep exact/state, provider/live, historical, native-monitor, endurance, final-audit, and
      `REF-STATE-VARIANTS` gaps open. Flexibility used: board-guided dense composition and
      controlled seeded data.

### 2026-08-12 Market Breadth dock-width containment

- [x] Wrap Market Breadth universe/timeframe/lookback/adjusted controls with a dock-width container
      query so a constrained 340px surface has no horizontal overflow.
- [x] Validate rebuilt browser geometry `1/1`, full frontend Vitest `725/725`, type-check,
      board-guided visual matrix `104/104`, and diff-check. No baseline or threshold changed.
- [ ] Keep `REF-STATE-VARIANTS` and exact/state, provider/live, historical, native-monitor,
      endurance, and final-audit gaps open. Flexibility used: board-guided dense-tool composition
      and controlled seeded data.

### 2026-08-12 EasyScan dock-width containment

- [x] Reflow EasyScan builder and scan controls with a dock-width container query so a constrained
      340px tool surface has no horizontal overflow.
- [x] Validate rebuilt browser geometry `1/1`, EasyScan units `12/12`, full frontend Vitest
      `725/725`, type-check, Docker production build, and diff-check. The first stale-image result
      was discarded after confirming the old fixed tracks.
- [ ] Keep `REF-STATE-VARIANTS` and exact/state, provider/live, historical, native-monitor,
      endurance, and final-audit gaps open. Flexibility used: board-guided dense-tool composition
      and controlled seeded data.

### 2026-08-12 Top-down ratio context-menu targeting

- [x] Scope `Open ratio vs active` to the live sector watchlist so stale detached Golden Layout
      roots cannot intercept the action; preserve the exact XLK/SPY assertion. Affected pair passes
      `2/2`, isolated flow `1/1`, diff-check passes.
- [x] Rerun the complete seeded browser matrix after this correction: `120/122` with two intentional
      skips in `5.3m`; this remains deterministic fixture evidence, superseded for the operational
      gate by the later current-head non-seeded `126/126` run. Keep all exact/state,
      provider/live, historical, native-monitor, endurance, final-audit, and `REF-STUDY-LAB-V25`
      gaps open. Flexibility used: board-guided dense-tool composition and controlled seeded data.

### 2026-08-12 Relative Rotation narrow-dock acceptance coverage

- [x] Add and pass rebuilt-stack browser geometry coverage `1/1` at 390px for Relative Rotation
      controls, plot containment, and header/plot separation; no implementation change was needed.
- [ ] Keep the exact/state, provider/live, historical, native-monitor, endurance, final-audit, and
      `REF-STUDY-LAB-V25` gaps open. Flexibility used: board-guided dense-tool composition and
      controlled seeded data.

### 2026-08-12 Unified Python editor popup semantics

- [x] Add unique per-instance `aria-controls`, `aria-haspopup=listbox`, and `aria-expanded` to
      the native Python textarea while preserving textbox queries and keyboard completion.
- [x] Fix the first counter-based linked-instance ID defect with UUID/fallback generation; focused
      editor units `4/4`, full frontend Vitest `725/725`, rebuilt Study Lab editor/promotion browser
      `1/1`, type-check, and diff-check pass.
- [ ] Keep `REF-STUDY-LAB-V25` and exact/state/provider/live, historical, native-monitor,
      endurance, and final-audit gaps open. Acceptance flexibility used: board-guided Study Lab
      editor composition plus controlled seeded interaction/data.
- [x] Re-run the complete four-environment board-guided visual matrix after the editor semantics
      change: `104/104`; no baseline, threshold, mask, or gap state changed.

### 2026-08-12 Study Lab narrow-dock containment

- [x] Reflow Study Lab header, dataset, parameter, and Python-editor controls below 560px so the
      dense tool remains contained and non-overlapping in a 390px desktop dock.
- [x] Validate focused Study Lab/Python units `23/23`, rebuilt-stack browser geometry `1/1`,
      type-check, and diff-check. A stale-image first attempt was discarded after confirming the
      old bundle; the rebuilt rerun is authoritative.
- [ ] Keep `REF-STUDY-LAB-V25` open because the board has no authoritative Study Lab capture, and
      continue tracking exact/state/provider/live, historical, native-monitor, endurance, and
      final-audit gaps. Acceptance flexibility used: board-guided Study Lab composition and
      controlled seeded data.
- [x] Re-run the supporting backend unit gate after the responsive repair: `1085/1085`, `70.04%`
      coverage against the configured `55%` threshold; known third-party deprecation warnings
      remain non-blocking.
- [x] Re-run the complete seeded authenticated Chromium matrix: `119/121` with two intentional
      skips in `5.3m`, including the new Study Lab narrow-dock assertion and existing workstation,
      top-down, Python, Study Lab, linking, legacy, and performance paths.
- [x] Re-run Docker-backed combined backend unit/integration coverage: `1383/1383`, `79.69%`
      against the configured `75%` threshold; 86 known third-party dependency warnings remain
      non-blocking. This deterministic contract gate does not close live-provider or historical
      truth gaps.

### 2026-08-12 Recent Symbols containment acceptance

- [x] Add constrained-viewport bounds and Escape recovery coverage for Recent Symbols (`1/1`).
- [ ] Keep exact-build/unrepresented visual and broader provider/backend gaps tracked.

### 2026-08-12 shell-menu listener cleanup

- [x] Synchronize fixed shell-menu resize/scroll listener ownership across pointer, focus, change,
      Escape, selection, and unmount dismissal paths.
- [x] Validate workstation unit coverage `22/22` and focused shell browser coverage `3/3`.
- [ ] Continue tracking exact-build/unrepresented visual and broader backend/operations gaps.
- [x] Re-run the full frontend suite after listener cleanup (`724/724`) and retain focused
      browser `3/3` plus preceding complete browser `118/120` and visual `104/104` evidence.

### 2026-08-12 shell-menu viewport containment

- [x] Move Workspace, Help, Add Tool, and Recent Symbols overlays to fixed trigger-anchored,
      viewport-clamped positioning with collision flipping and lifecycle cleanup.
- [x] Validate shell keyboard/outside dismissal and constrained containment: unit `21/21`,
      rebuilt-stack browser `3/3`, type-check, and diff-check.
- [ ] Preserve the documented Escape-close oracle for clamped menus and continue tracking exact
      pinned-build/unrepresented visual states separately.
- [x] Revalidate the complete seeded browser matrix (`118/120`, two intentional skips) and all
      four board-guided visual environments (`104/104`) after the shared shell change.

### 2026-08-12 LayoutPicker dismissal and focus recovery

- [x] Add Escape and outside-pointer dismissal to the retained legacy LayoutPicker.
- [x] Restore focus to the owning trigger and clean transient document/viewport listeners on
      every close, selection, profile, and unmount path.
- [x] Validate with focused component `3/3`, rebuilt-stack browser `1/1`, type-check, and
      diff-check.
- [ ] Keep the bounded multi-instance browser-oracle limitation documented; it does not close
      exact pinned-build or `REF-STATE-VARIANTS` gaps.

### 2026-08-12 LayoutPicker, EasyScan capacity, and Radar race closure

- [x] Repaired LayoutPicker custom-grid/profile popovers with fixed trigger anchoring, viewport
  gutters, collision flipping, bounded internal scrolling, scroll/resize repositioning, and
  complete listener cleanup. Focused unit/adjacent chart coverage `3/3`, corrected legacy-chart
  browser containment `1/1`, full frontend Vitest `722/722`, type-check/build/diff-check, and
  board-guided visual `104/104` pass.
- [x] Raised the bounded unified-Python/research batch ceiling from `10,000` to `25,000` symbols
  because the canonical all-instruments universe is already `10,948` rows. Focused backend
  materialisation contract tests pass `2/2`; EasyScan/Python/ratio/drag/gauge browser slice
  passes `5/5`.
- [x] Added the Radar post-scan idle-state synchronization required before result-row selection;
  focused Radar browser flow passes `1/1`.
- [x] Final rebuilt seeded authenticated Chromium matrix passes `117/119` with two intentional
  skips; all workstation/top-down/EasyScan/Python/Study Lab/linking/pop-out/legacy/performance
  paths are green.
- [ ] Continue the single completion bar. Board-guided represented states and controlled seeded
  data remain interim evidence; exact-build/unrepresented visual, provider/live-entitlement,
  historical truth, native-monitor, beyond-bounded-endurance, and final-audit gaps remain open.


### 2026-08-12 Full authenticated regression after chart-toolbar repair

- [x] Rebuilt branch-stack Chromium matrix passes `116/118` executed tests with two intentional
  skips in 5.1m across workstation, top-down, linking, pop-outs, Python/Study Lab,
  legacy/exclusions, and performance paths.
- [ ] This is broad regression evidence, not overall completion. Keep exact/unrepresented,
  provider/live-entitlement, historical truth, native-monitor, endurance, and final-audit gaps
  open; no product or visual criterion was relaxed.

### 2026-08-12 Constrained chart-toolbar overlap repair

- [x] Reflow compare controls to a first compact toolbar row and Plot Library/Templates to a
  second row below 520px, reserving chart surface padding so controls cannot overlap chart/OHLCV.
- [x] Add 390px browser geometry coverage and update the stale menu oracle for deliberate
  above-trigger placement. Focused units 31/31, full Vitest 720/720, type-check/build/diff,
  affected browser 4/4, and board-guided visual 104/104 pass.
- [ ] Keep REF-STATE-VARIANTS exact pinned-build selected/disabled toolbar details and the
  provider/live-entitlement, historical truth, native-monitor, endurance, and final-audit gaps
  open; no baseline, threshold, mask, product, provider, provenance, or uPlot rule changed.

### 2026-08-12 ToolWindow menu vertical viewport containment

- [x] Move the shared ToolWindow action menu to fixed trigger anchoring with bottom-edge
  flipping, available-height clamping, capture-phase scroll/resize repositioning, and complete
  close/outside-pointer/action/unmount cleanup.
- [x] Focused ToolWindow unit coverage 7/7, full frontend Vitest 720/720, type-check/build/
  diff-check, rebuilt seeded affected browser 11/11, and complete board-guided visual 104/104
  pass.
- [ ] Keep exact-build/unrepresented visual, provider/live-entitlement, historical truth,
  native-monitor, beyond-bounded-endurance, and final-audit gaps open; no baseline, threshold,
  mask, product, provider, provenance, or uPlot rule changed.

### 2026-08-12 Chart-local menu vertical viewport containment

- [x] Make Chart Templates and Plot Library flip above bottom-edge triggers, cap menu height,
  and reposition on capture-phase scroll and resize while retaining fixed trigger anchoring.
- [x] Remove both transient listeners on close/unmount and add bottom-edge geometry/listener
  regressions. Focused units 24/24, full frontend Vitest 719/719, type-check/build/diff-check,
  rebuilt seeded browser 4/4, and complete board-guided visual 104/104 pass.
- [ ] Keep exact-build/unrepresented visual, provider/live-entitlement, historical truth,
  native-monitor, beyond-bounded-endurance, and final-audit gaps open; no baseline, threshold,
  mask, product, provider, provenance, or uPlot rule changed.

### 2026-08-12 Plot Library viewport containment and lifecycle cleanup

- [x] Give Chart Plot Library the same fixed, trigger-anchored, 8px-gutter viewport contract as
  Chart Templates; clamp width for narrow desktop docks and remove resize listeners on close and
  unmount.
- [x] Focused chart-menu units `22/22`, full frontend Vitest `717/717`, type-check/build/diff,
  rebuilt seeded browser regressions `3/3`, and complete four-environment board-guided visual
  matrix `104/104` pass.
- [ ] Keep exact-build/unrepresented visual, provider/live-entitlement, historical truth,
  native-monitor, beyond-bounded-endurance, and final-audit gaps open; no baseline, threshold,
  mask, product, provider, provenance, or uPlot rule changed.

### 2026-08-12 ratio row-action oracle hardening

- [x] Harden `F8e.2a` to assert the requested `XLK/SPY` legend among visible ratio legends rather
  than the last DOM node or transient Golden Layout activation class.
- [x] Repaired ratio/chart regression slice `11/11`, serial ratio checks `3/3`, full frontend
  Vitest `716/716`, type-check, production build, and diff-check.
- [x] Complete seeded Chromium matrix rerun passes `112/112` executed with two intentional skips
  in 4.9m after this oracle correction. Keep board-guided
  represented states and controlled seeded data explicitly marked as interim; exact-build /
  unrepresented visual, provider/live-entitlement, historical truth, native-monitor,
  beyond-bounded-endurance, and final-audit gaps remain open.

### 2026-08-12 chart-menu close-path cleanup and seeded rerun

- [x] Route Templates and Plot Library header close buttons through cleanup/focus recovery rather
  than direct visibility mutation.
- [x] Focused units `21/21`, full frontend Vitest `716/716`, type-check/build/diff-check, focused
  browser `4/4`, and correctly seeded affected top-down/linking browser slice `5/5` pass.
- [ ] Keep exact-build/unrepresented visual, provider/live-entitlement, historical truth,
  native-monitor, beyond-bounded-endurance, and final-audit gaps open. The first complete browser
  attempt was invalid mixed-runtime setup evidence caused by recreating only the frontend; the
  full stack rerun with all seed/bootstrap flags passed the affected slice.

### 2026-08-12 chart-local menu viewport containment

- [x] Move Chart Templates from ancestor-clipped absolute positioning to a fixed,
  trigger-anchored menu with viewport clamping, resize repositioning, and unmount cleanup.
- [x] Add and pass 390px browser coverage for Templates and Plot Library; focused units `19/19`,
  focused browser `3/3`, type-check/build/diff-check, complete authenticated Chromium `112/112`
  executed with two intentional skips, and no-update visual matrix `104/104` across all four
  environments.
- [ ] Keep `REF-STATE-VARIANTS` and exact-build/unrepresented visual, provider/live-entitlement,
  historical truth, native-monitor, beyond-bounded-endurance, and final-audit gaps open. No
  baseline, threshold, mask, product, provider, provenance, or uPlot rule changed.

### 2026-08-12 tool-window menu overflow and acceptance rerun

- [x] Allow the shared tool-window action cluster's menu to render outside a constrained dock;
  preserve functional selectors and actions while avoiding viewport clipping.
- [x] Add and pass the 390px browser regression for menu visibility and trigger-relative placement;
  focused ToolWindow `6/6`, focused browser `3/3`, type-check/build/diff-check, complete seeded
  authenticated Chromium `111/111` executed with two intentional skips, and no-update visual
  matrix `104/104` across all four environments.
- [ ] Keep exact-build/unrepresented visual, provider/live-entitlement, historical truth,
  native-monitor, beyond-bounded-endurance, and final-audit gaps open. The first full-matrix
  timeout was stopped-stack setup evidence and was superseded by the healthy rebuilt-stack rerun;
  no baseline, threshold, mask, product, provider, provenance, or uPlot rule changed.

### 2026-08-12 constrained tool-window header geometry

- [x] Keep shared tool-window title/symbol regions separate from link/timeframe selectors and
  menu/maximize/float/close actions at normal and 390px desktop widths.
- [x] Add constrained flex/minimum-width behavior; hide only decorative link swatches below 420px
  so functional controls remain usable.
- [x] Focused ToolWindow `6/6`, type/build/diff checks, normal+narrow browser `2/2`, full
  authenticated Chromium `111/111` executed with two intentional skips, and no-update visual
  matrix `104/104` across all four environments pass.
- [ ] Keep exact-build/unrepresented visual, provider/live-entitlement, historical truth,
  native-monitor, beyond-bounded-endurance, and final-audit gaps open. The first browser/visual
  oracle invocations were setup errors corrected before acceptance; no baseline, threshold, mask,
  product, provider, provenance, or uPlot rule changed.

### 2026-08-12 virtualized watchlist active-descendant keyboard semantics

- [x] Added isolated per-mounted-list option IDs and a truthful `aria-activedescendant` contract
  to the dense virtualized watchlist.
- [x] Initial and refreshed universes establish the first canonical active row only when no
  explicit selection exists; Home/End and existing arrow/Space/Ctrl+wheel traversal scroll the
  virtualizer and publish the active row.
- [x] Focused component coverage `64/64`; full frontend Vitest `713/713`; type-check, production
  build, diff-check; focused authenticated Chromium `1/1`; complete authenticated Chromium
  `110/110` executed with two intentional skips.
- [ ] Keep exact-build/unrepresented visual states, provider/live-entitlement breadth, historical
  truth, native-monitor placement, beyond-bounded endurance, and final-audit gaps open. Fix-first
  browser evidence included a real initial-row lifecycle repair and stale-image setup correction;
  no visual baseline, threshold, mask, product, provider, provenance, or uPlot rule changed.

### 2026-08-12 visual fixture-history alignment

- [x] Isolated the apparent `visual-1440p-125` regression to retained snapshots generated against
  an older seeded history, rather than a watchlist or shell defect.
- [x] Rebuilt the branch-scoped stack with both seed flags, retained the per-test factory reset,
  regenerated only the stale 125% snapshots after reviewing the content drift, and reran the
  complete no-update matrix: `104/104` across all four required environments. No mask, threshold,
  or product criterion changed.
- [ ] Keep exact-build pointer-state and other unrepresented-state gaps open; native hit-target
  evidence is closed and the current local fixture/baseline alignment is pinned and green.

### 2026-08-12 native resize hit-target correction

- [x] Fixed the real collapsed-header geometry defect by giving the dense grid header a 23px
  minimum height and stacking it above the scroll surface.
- [x] Focused VirtualWatchlistTool coverage `63/63`, native resize browser `1/1`, full seeded
  authenticated Chromium `109/109` executed with 2 intentional skips, and no-update visual
  matrix `104/104` across all four required environments pass.
- [ ] Keep exact-build resize-affordance measurement and other unrepresented-state gaps open;
  native hit-target evidence is closed.

### 2026-08-12 V25 data-grid header resizing

- [x] Added a visible, focusable V25-style separator to rendered watchlist headers. Desktop mouse
  dragging applies an immediate pixel width to the virtualized grid and emits the existing
  serializable `columnOverrides` state used by workspace/column-set persistence.
- [x] Focused VirtualWatchlistTool coverage passes `63/63`; type-check, production build, and
  diff-check pass; authenticated seeded Chromium resize coverage passes `1/1` using native
  Playwright mouse targeting. The complete
  seeded matrix reached `108/111` with two intentional skips; the only failure was the known
  frontend-only restart/seed-provenance mismatch and the restored consistently seeded rerun of
  `F8e.1`/`F8e.1a` passes `2/2`.
- [ ] Keep `REF-STATE-VARIANTS` open for exact-build resize-affordance measurements and continue the
  next visible workstation parity gap. Board-guided grid composition and controlled seeded data
  were used; native hit-target evidence is closed. No threshold, mask, provider, provenance,
  product, or uPlot rule was relaxed.

### 2026-08-12 multi-toolbar flyout ownership

- [x] Scope drawing-toolbar popup IDs and keyboard queries to each mounted toolbar; use unique
  per-instance DOM identity so four-chart and floating layouts cannot cross-focus flyouts.
- [x] Focused ownership/keyboard/context browser coverage passes `3/3`; type-check and production
  build pass. The first two attempts are retained as fix-first evidence: one corrected a test's
  wrong assumption about the default chart count, and one exposed/then fixed a real duplicate-ID
  runtime defect.
- [x] Complete authenticated Chromium rerun passes `108/108` executed tests with two intentional
  skips in 4.7m. Final no-update board-guided visual matrix passes `104/104` across all four
  required environments in 5.5m; no baseline, threshold, or mask changed. No acceptance
  flexibility beyond the existing board-guided/seeded interim tracks is used.

### 2026-08-12 visual-oracle semantic role repair

- [x] Correct the board visual spec's workspace `Clone`/`Export` queries from `button` to the
  implemented semantic `menuitem` role after the first four-environment run exposed the stale
  selector.
- [x] Rerun the complete no-update board-guided visual matrix: `104/104` across all four required
  environments in 7.0m. No product, baseline, threshold, or mask changed; this was a localized
  oracle repair under the fix-first tie-break.

### 2026-08-12 deterministic drawing-toolbar visual correction

- [x] Replaced platform-dependent emoji/Unicode drawing-toolbar glyphs with deterministic original
  CSS geometry, tightened the rail to 40px and visible controls to 32px, and added explicit button
  type/name semantics for AVWAP and utility actions.
- [x] Focused drawing browser coverage passes `4/4`, including no-text-glyph and compact-geometry
  assertions; type-check, 468-module production build, full Vitest `710/710`, and diff-check pass.
  The no-update represented default-workstation visual assertion passes at 1920x1080/100%, and
  the complete seeded authenticated Chromium matrix passes `107/107` executed with two skips.
- [ ] The board has no pinned-build drawing-toolbar icon sheet or exact selected/disabled variants;
  retain this as a `REF-STATE-VARIANTS` gap with the current local contract as interim oracle.
  Acceptance flexibility used: board-guided chart composition and controlled seeded browser data;
  no threshold, mask, provider, provenance, product, or uPlot rule was relaxed.

### 2026-08-12 chart context-menu focus recovery

- [x] Return focus to the owning chart region after price-axis and drawing context-menu Escape,
  Deselect, Log Scale, and Reset Price Scale actions; keep the chart root keyboard-addressable.
- [x] Focused context-menu browser coverage passes `2/2`; type-check, production build, diff-check,
  and complete consistently seeded Chromium `107/107` executed with 2 intentional skips in 4.7m.
- [ ] Continue exact-build/unrepresented chart/menu visual evidence, provider/live-entitlement
  breadth, historical truth, native-monitor placement, beyond-bounded endurance, and final audit.
  Fix-first rebuilt the stale runtime before acceptance; no threshold, mask, product, provenance,
  provider, or uPlot rule was relaxed.

### 2026-08-12 selected-drawing context-menu regression

- [x] Cover the real selected-drawing interaction: create a persisted horizontal line, locate its
  rendered hit band, open the scoped Drawing actions menu, navigate to Deselect, and verify
  dismissal without browser diagnostics.
- [x] Focused browser coverage passes `1/1`; type-check, production build, diff-check, and complete
  consistently seeded Chromium `107/107` executed with 2 intentional skips in 4.7m.
- [ ] Continue exact-build/unrepresented chart/drawing-menu visual evidence, provider/live-
  entitlement breadth, historical truth, native-monitor placement, beyond-bounded endurance, and
  final audit. Fix-first replaced a brittle fixed-coordinate oracle with bounded rendered-surface
  probing; no threshold, mask, product, provenance, provider, or uPlot rule was relaxed.

### 2026-08-12 per-chart control identity and scoped context menus

- [x] Make chart dialog IDs unique per mounted chart instance and scope context-menu keyboard
  queries to the owning chart root, preventing focus/menu leakage between charts sharing a panel
  key. Add a browser invariant for unique settings dialog targets.
- [x] Focused dialog/context-menu browser coverage passes `2/2`; full Vitest `710/710`; type-check,
  production build, diff-check, and complete consistently seeded Chromium `106/106` executed with
  2 intentional skips in 4.7m.
- [ ] Continue exact-build/unrepresented chart/dialog/menu visual evidence, provider/live-
  entitlement breadth, historical truth, native-monitor placement, beyond-bounded endurance, and
  final audit. Fix-first repaired this shared correctness defect; no threshold, mask, product,
  provenance, provider, or uPlot rule was relaxed. Board-guided represented composition and
  controlled seeded data remain explicitly interim.

### 2026-08-12 chart context-menu keyboard semantics

- [x] Make price-axis and drawing right-click actions named semantic menus with menuitem roles,
  initial focus, Arrow/Home/End navigation, Enter/Space activation, and Escape dismissal while
  preserving pointer behavior and uPlot rendering.
- [x] Focused context-menu browser coverage passes `1/1`; full Vitest `710/710`; type-check,
  production build, diff-check, and complete consistently seeded Chromium `106/106` executed with
  2 intentional skips in 4.7m.
- [ ] Continue exact-build/unrepresented chart/menu visual evidence, provider/live-entitlement
  breadth, historical truth, native-monitor placement, beyond-bounded endurance, and final audit.
  Fix-first restored matching seed flags before the authoritative run; no threshold, mask, product,
  provenance, provider, or uPlot rule was relaxed.

### 2026-08-12 chart utility dialogs and active ratio targeting

- [x] Make uPlot chart utility controls semantically actionable: named/pressed auto and log
  controls, explicit help/settings dialogs, per-chart dialog ownership, deterministic first
  control focus, local Escape dismissal, trigger-focus recovery, and explicit event/latest-bar
  button semantics. Preserve the existing uPlot chart lifecycle and global editor shortcut guard.
- [x] Correct the top-down sector ratio acceptance to target the active visible ratio tool when
  the factory workspace retains SPY/RSP and launches XLK/SPY. Focused chart and ratio browser
  flows pass `1/1` each; full Vitest `710/710`; type-check/build; complete consistently seeded
  authenticated Chromium `105/105` with 2 intentional skips in 5.1m.
- [ ] Continue exact-build/unrepresented chart/dialog/ratio visual evidence
  (`REF-SHELL-V25`/`REF-STATE-VARIANTS`), provider/live-entitlement breadth, historical truth,
  native-monitor placement, beyond-bounded endurance, and final audit. Fix-first repaired real
  focus/close and selector defects; no threshold, mask, product criterion, provenance, provider,
  or uPlot rule was relaxed. Board-guided represented composition and controlled seeded data remain
  explicitly interim.

### 2026-08-12 primary workspace tab rearrangement (latest)

- [x] The main visible workspace tab strip now supports pointer/mouse drag rearrangement with
  drag-target feedback, `aria-grabbed`, idempotent drop/drag-end commits, and persistence through
  the existing workspace snapshot contract. The Workspace-menu drag path remains available.
- [x] The first browser run was against a stale container and was discarded as environment
  evidence; after rebuilding the branch frontend, the focused authenticated Chromium regression
  passed `1/1` in `2.7s`. Focused workspace/pop-out units pass `63/63`, full Vitest `698/698`,
  type-check/build and diff checks pass.
- [ ] Acceptance flexibility used: board-guided represented tab/layout state plus browser
  evidence. Exact-build and unrepresented visual gaps remain tracked; this was a frontend-only
  workstation change with no provider/backend/uPlot change.

### 2026-08-12 point-in-time membership cache identity (latest)

- [x] Group-backed analysis now derives `membership_version` from the selected group,
  member identities/order-independent membership, lifecycle boundaries, verification state, and
  provenance instead of the immutable group ID. Membership changes now invalidate cached
  rankings, breadth, snapshots, and rotation responses.
- [x] Focused analysis unit coverage passes `17/17`; valid point-in-time integration coverage
  passes `2/2`; changed-file Ruff/compile pass; and authoritative backend coverage passes
  `1382/1382` at `79.69%` with 86 known dependency deprecation warnings. A first invocation named
  a nonexistent selector and collected no tests; it was corrected before the passing validation.
  Acceptance flexibility used: none; no frontend/uPlot/CSS/visual baseline changed.
- [ ] This closes a cache-identity defect, not authoritative historical membership truth. Source
  reconciliation, provider/ETF breadth, exact/unrepresented visual states, native-monitor,
  endurance, and final whole-goal audit gaps remain open.

### 2026-08-12 point-in-time membership completeness guard (latest)

- [x] Explicit `as_of` analysis now requires each selected market-group member to have a
  `known_at` boundary; rows lacking it are excluded instead of being presented as historically
  proven. Current/latest views preserve legacy behavior, and group-level timestamp omission remains
  compatible when member-level evidence is available.
- [x] Focused analysis unit coverage passes `16/16`; point-in-time rotation and group snapshot/
  breadth integration coverage passes `2/2`; authoritative backend passes `1381/1381` at `79.68%`;
  changed-file Ruff/compile pass. The initial over-tightened group-root behavior was corrected
  under the fix-first rule and retained in the evidence ledger. Acceptance flexibility used: none.
- [ ] This closes an unsafe admission path, not authoritative historical membership truth. Broader
  source reconciliation, ETF/provider breadth, visual-reference, native-monitor, endurance, and
  final-audit gaps remain open.

### 2026-08-12 ETF live-route coverage contract execution guard (latest)

- [x] The ETF live-provider module now keeps its two non-network maintainability contracts
  executable on ordinary backend runs instead of skipping the whole module: registry parity and
  concrete live-route coverage for every promoted `LIVE_BACKED_ISSUER_ADAPTERS` member.
- [x] Focused contracts pass `2/2`; the complete module reports `2 passed, 373 skipped` with
  network probes still explicitly opt-in; Ruff/compile pass; deterministic ETF adapter tests pass
  `471/471`; and the authoritative backend gate passes `1380/1380` at `79.68%` with 86 known
  dependency deprecation warnings.
- [ ] This strengthens supporting ETF infrastructure for the TC2000 top-down workflow; it does
  not close broader issuer route/access, entitlement, historical truth, exact/unrepresented V25
  visual, native-monitor, endurance, or final-audit gaps. Acceptance flexibility used: **None**.

### 2026-08-12 canonical listing lifecycle timestamps (latest)

- [x] Canonical listings now retain nullable `effective_at`, `known_at`, and `delisted_at`
  timestamps. Provider discovery supplies IPO/delisting observations and ingestion time without
  silently changing `is_active`; profile ingestion can carry the same values through
  `ListingRecord` and provider bindings.
- [x] The lifecycle fields are exposed through the normal instrument and provenance payloads and
  the frontend listing type. Focused exchange/upsert/API coverage passes `17/17`; migration
  `f6a7b8c9d0e1` passes PostgreSQL 16 upgrade → downgrade → upgrade; frontend Vitest passes
  `698/698`, type-check/build pass, and the authoritative backend gate passes `1380/1380` at
  `79.68%` with 86 known dependency deprecation warnings.
- [ ] These are retained observations and a durable historical boundary, not independently
  verified listing truth. Source review, venue moves/relistings, authoritative delisted snapshots,
  broader provider/ETF coverage, exact-build/unrepresented V25 states, native-monitor validation,
  beyond-bounded endurance, and the final whole-goal audit remain open. Acceptance flexibility
  used: **None**.

### 2026-08-12 provenance listing exchange parity repair (latest)

- [x] The canonical instrument provenance endpoint now preserves the same nested exchange
  metadata already exposed by the normal instrument-detail response. MIC, venue name, country,
  session, and currency therefore remain available when the workstation or diagnostics inspect
  lineage rather than only the live instrument payload.
- [x] The exchange-aware listing integration regressions pass `2/2`, including an explicit
  no-exchange listing case; changed-file Ruff and compilation pass; the authoritative Docker-backed
  backend gate passes `1373/1373` at `79.67%`
  coverage with 86 known dependency deprecation warnings.
- [ ] This closes an API omission only. Historical listing truth, venue moves/relistings, broader
  provider/ETF coverage, exact-build/unrepresented V25 states, native-monitor validation,
  beyond-bounded endurance, and the final whole-goal audit remain open. Acceptance flexibility
  used: **None**.

### 2026-08-12 multi-exchange listing visibility and seeded board rerun (latest)

- [x] The existing exchange-aware `GET /instruments/{symbol}` contract is now consumed by
  `InstrumentInfoPanel`: every canonical listing shows its ticker, MIC/venue, and active/primary
  state so same-issuer multi-venue evidence is visible in the workstation rather than remaining
  API-only. A focused component regression passes `5/5`.
- [x] Frontend type-check, production build, and the complete Vitest suite pass `698/698` across
  93 files. The isolated seeded Compose stack (`E2E_SEED_INSTRUMENTS=true`,
  `E2E_SEED_MARKET_DATA=true`) is healthy on alternate host ports, and the no-update board-guided
  Playwright matrix passes `104/104` across 1920x1080 and 2560x1440 at 100% and 125% display
  scale in 5.4 minutes. No snapshots, masks, thresholds, or product criteria changed.
- [ ] An initial visual attempt against the default `localhost` stack was setup-only evidence:
  the stack was not running with market fixtures (`e2e_seed_market_data=false`) and the matrix did
  not reach screenshot comparison. The rerun used an isolated seeded stack; this is recorded as an
  environment recovery, not a product failure. Acceptance flexibility used: **None**.
- [ ] This improves visible security-master provenance but does not close historical
  listing/delisting truth, broader provider/ETF coverage, exact-build/unrepresented V25 states,
  native-monitor validation, beyond-bounded endurance, or the final whole-goal audit.

### 2026-08-12 listing report browser contract and eager-load repair (latest)

- [x] The controlled identity fixture now includes an explicitly labelled active primary SPY
  listing on `ARCX`, and the authenticated `F8s-report` browser flow asserts that the real
  instrument API response reaches the visible report row. Existing canonical listing evidence is
  not discarded; the assertion targets the seeded venue rather than assuming it is the only row.
- [x] The shared instrument-detail and full-reload query paths now eagerly load
  `InstrumentListing.exchange`. This repaired a real response-validation defect exposed by the new
  browser assertion: before the fix, `GET /instruments/SPY` returned HTTP 500 when nested exchange
  serialization triggered async lazy loading. Focused API integration passes `17/17`, focused seed/
  health tests pass `3/3` without the global coverage threshold, and changed-file Ruff/compile pass.
- [x] Rebuilt seeded authenticated browser report regression passes `1/1`; complete authenticated
  Chromium passes `95/95` executed tests with `106` suite-gated skips; full frontend Vitest passes
  `698/698`; type-check/build pass; authoritative backend passes `1373/1373` at `79.65%`; strict
  no-update board-guided visual passes `104/104` across all four display environments. No
  snapshots, masks, thresholds, or product criteria changed. Acceptance flexibility used: **None**.
- [ ] The original 500 and the initial over-specific one-row browser expectation are retained as
  fix-first evidence, not hidden. Remaining gaps are unchanged: historical listing truth, broader
  provider/ETF coverage, exact-build/unrepresented V25 states, native-monitor validation,
  beyond-bounded endurance, and final whole-goal audit.

### 2026-08-12 canonical multi-exchange listing payload (latest)

- [x] Expose the existing exchange-aware canonical listing relationship in `GET /instruments/{symbol}`
  and the frontend `InstrumentListing` type. Same-issuer listings now carry MIC, venue name,
  country, timezone, trading-session, and currency metadata without provider fan-out.
- [x] The focused authenticated API regression passes `1/1`; frontend type-check, production build,
  and Vitest pass `697/697`; the authoritative Docker-backed backend gate passes `1373/1373` at
  `79.67%`. Acceptance flexibility used: **None**.
- [ ] This closes the payload omission, not authoritative historical listing/delisting truth,
  venue-move/relisting reconciliation, broader provider/ETF coverage, visual-reference,
  native-monitor, endurance, or final-audit gaps.

### 2026-08-12 consolidated canonical listing model (latest)

- [x] Removed the unused duplicate `backend/app/models/instrument_listing.py` declaration. The
  existing `backend/app/models/listing.py` is now the single imported ORM model for the
  `instrument_listing` table, preserving the lifecycle guard, exchange-aware upsert behavior, and
  the existing migration/schema contract.
- [x] Repository-wide import search confirms no runtime or test code referenced the deleted
  duplicate; focused model import and listing persistence tests pass before the authoritative
  backend gate.
- [ ] This removes model-definition ambiguity but does not close historical listing/delisting
  truth, broader provider/ETF coverage, visual-reference, native-monitor, endurance, or final-audit
  gaps. Acceptance flexibility used: **None**.

### 2026-08-12 canonical lifecycle reactivation guard (latest)

- [x] Fixed a repository-controlled data-integrity defect in `seed_universe`: discovery rows no
  longer unconditionally reactivate an existing canonical instrument, canonical listing, or
  provider-symbol binding. Provider IPO/status/delisting observations remain provenance evidence;
  canonical lifecycle changes still require a separate reconciliation decision.
- [x] Focused seed/listing regressions pass `4/4`; changed-file Ruff, Python compilation, and
  `git diff --check` pass; the authoritative Docker-backed backend gate passes `1373/1373` at
  `79.64%` after the expanded guard.
- [ ] This closes the silent-reactivation defect, not authoritative historical listing truth.
  Delisted snapshots, venue moves/relistings, terms-reviewed promotion, broader provider/ETF
  coverage, and final audit remain open. Acceptance flexibility used: **None**.

### 2026-08-12 authoritative backend gate after listing-lifecycle evidence retention

- [x] The complete backend unit/integration gate passes `1372/1372` at `79.62%` coverage after
  retaining provider listing-lifecycle observations. The earlier non-elevated run was blocked
  before integration collection by local Docker/uv-cache permissions; the approved host-permitted
  rerun is the authoritative result.
- [ ] The 86 known dependency deprecation warnings are non-blocking; historical listing truth,
  broader provider/ETF coverage, and the final whole-goal audit remain open. Acceptance flexibility
  used: **None** for this validation.

### 2026-08-11 provider listing-lifecycle evidence retention (latest)

- [x] Preserve provider-reported IPO, active/delisted status, and delisting date from discovery
  rows in canonical instrument field provenance and the provider-symbol binding. The evidence is
  explicitly tagged as an observation with source and observed-at timestamps; it does not silently
  deactivate or merge canonical instruments.
- [x] Focused metadata regression passes `2/2`; changed-file Ruff, Python compilation, JSON/YAML
  parsing, and `git diff --check` pass.
- [ ] This improves the historical listing/delisting evidence boundary but is not authoritative
  point-in-time listing truth. A complete historical model still requires independently entitled
  delisted snapshots, listing moves/relistings, and review of provider terms. Acceptance flexibility
  used: **None**.

### 2026-08-11 visual acceptance policy guard (latest)

- [x] Tie the manifest's deterministic visual thresholds to every workstation screenshot
  assertion with a repository validator: `0.5%` maximum pixel-difference ratio, `1px` geometry
  tolerance, and `CIEDE2000 ΔE 2` policy values are now declared in the V25 manifest; all 26
  `toHaveScreenshot` assertions require the threshold plus disabled animation/caret and CSS-scale
  capture settings.
- [x] The validator also fails closed if a `required_missing` state loses its interim oracle or
  one of the four environment baselines. `make test-visual-policy`, manifest validation, uPlot
  contract validation, JSON parsing, and `git diff --check` pass.
- [ ] This strengthens acceptance governance only. It does not promote board-guided interim
  baselines to exact-build approval or close `REF-SHELL-V25`, `REF-STATE-VARIANTS`,
  `REF-LINKING-V25`, `REF-STUDY-LAB-V25`, `REF-ENV-TOKENS`, or `REF-PERMISSION-REVIEW`.
  Acceptance flexibility used: **None**.

### 2026-08-11 admin-only provider configuration boundary (latest)

- [x] Hide provider `Show config` and configuration-panel controls from ordinary users now that
  provider governance mutations are admin-only; read-only usage remains available and the admin
  reconciliation queue remains legacy-routed and administrator-only.
- [x] Settings unit coverage passes `4/4`, full frontend Vitest passes `691/691` across 93 files,
  type-check and production build pass, and the rebuilt branch browser regression passes `1/1`.
  A first template-condition placement was caught by the focused test and repaired before the
  authoritative rerun under the fix-first tie-break.
- [x] The complete authenticated Chromium flow matrix passes `88/88` against the rebuilt branch,
  including authentication, charting, linking, pop-outs, top-down drilldown, Study Lab, alerts,
  screeners, legacy routes, Radar, and this regular-user Settings boundary.
- [ ] Exact-build/unrepresented visual references, provider breadth/live entitlement coverage,
  native physical-monitor placement, beyond-bounded endurance, and final whole-goal audit remain
  open. Acceptance flexibility used: **None**.

### 2026-08-11 initial robust workstation gate

- [x] The rebuilt branch is operating on the canonical non-seeded path: health reports
  `e2e_seed_instruments=false` and `e2e_seed_market_data=false`.
- [x] The complete authenticated Chromium matrix passes `88/88`, covering the live top-down
  workflow, ratios, drilldown, linking, keyboard traversal, persistence, pop-outs, notes, alerts,
  freshness/error states, Python reuse, and the positive-close Study Lab study. Frontend Vitest
  passes `691/691`; type-check, production build, and tracked service-log audit pass.
- [x] This satisfies the initial daily-analysis workstation gate, not the single overall completion
  bar. Exact-build/unrepresented visual states, broader provider/live evidence, native physical
  monitor placement, beyond-bounded endurance, and final requirement audit remain open.
  Acceptance flexibility used: **None**.

### 2026-08-11 governed 100-round endurance guard

- [x] Ran `TC2000_POP_OUT_CHURN_ROUNDS=100` against the rebuilt branch performance suite. Both
  guards passed `2/2` in `2.6m`; all 100 two-popout open/close rounds returned to the source
  tool/canvas baseline, memory ceilings passed, and browser diagnostics remained clean.
- [x] Narrowed backend/worker/research-runner logs after the run contain no tracked runtime-error
  signatures.
- [ ] This is bounded-stress evidence only, explicitly substituting for indefinite soak under the
  governance policy. Longer-duration endurance remains open. Acceptance flexibility used:
  **bounded stress in place of indefinite soak**.

### 2026-08-11 Python Library lifecycle browser coverage

- [x] Added a real-user browser regression covering creation of a Study asset, immutable version
  creation, cloning, and archiving through the workstation's Python Library.
- [x] The complete authenticated Chromium matrix passes `89/89`; no visual baseline, mask,
  threshold, or acceptance criterion changed. Existing unit coverage continues to cover import and
  validation failure paths.
- [ ] Exact-build/unrepresented visual references, provider breadth/live entitlement coverage,
  native physical-monitor placement, beyond-bounded endurance, and final audit remain open.
  Acceptance flexibility used: **None**.

### 2026-08-11 Research Results comparison browser coverage

- [x] Extended the persisted Study Results browser path to select two runs, open the comparison
  panel, and inspect changed code-version, parameter, dataset, and reproducibility metadata.
- [x] The first focused assertion exposed a test-oracle selector that targeted both run rows; it
  was corrected under the fix-first tie-break. Focused comparison passed `1/1`, and the complete
  authenticated Chromium matrix remained green at `89/89`.
- [ ] Exact-build/unrepresented visual references, provider breadth/live entitlement coverage,
  native physical-monitor placement, beyond-bounded endurance, and final audit remain open.
  Acceptance flexibility used: **None**.

### 2026-08-11 durable reconciliation review workflow (latest)

- [x] Ambiguous security-master issues now persist server-attributed reviewer identity through
  `resolved_by_user_id`; reopening clears the attribution. Migration `f5a6b7c8d9e0` passed an
  isolated upgrade/downgrade/re-upgrade cycle and is applied to the branch database at head.
- [x] Added an admin-only legacy Settings review queue with candidate issuer details and explicit
  resolve/ignore actions. Regular users do not fetch or see it. Settings tests pass `3/3`, the
  authenticated regular-user browser check passes `1/1`, backend focused regressions pass `10/10`,
  backend coverage passes `1,368/1,368` at `79.62%`, frontend Vitest passes `690/690`, and
  type/build pass.
- [ ] Historical listing/delisting truth, SEC live-access promotion, broader provider coverage,
  visual/reference, native-monitor, endurance, and final-audit gaps remain open. Acceptance
  flexibility used: **None**.

### 2026-08-11 provider-governance authorization repair (latest)

- [x] Provider policy, entitlement mutation, and ambiguous-instrument reconciliation review
  endpoints now require the existing administrator dependency; ordinary authenticated users retain
  read-only provider visibility and receive `403` for governance mutations/review operations.
- [x] Added regression coverage for the regular-user boundary. The first invocation exposed a
  syntax error in the new test, which was repaired and rerun under the fix-first tie-break.
  Router tests pass `8/8`, provider integration passes `7/7`, Ruff/compile pass, and the full
  backend gate passes `1,368/1,368` at `79.62%`.
- [ ] This closes only the localized authorization defect. Exact-build/unrepresented visual states,
  broader provider entitlements/live evidence, native physical multi-monitor validation,
  beyond-bounded endurance, and the final whole-goal audit remain open. Acceptance flexibility
  used: **None**.

### 2026-08-11 current-head Alembic round-trip revalidation (latest)

- [x] Revalidated the complete current migration graph, including `f2a3b4c5d6e7` provider
  entitlement revisions and `f4a5b6c7d8e9` durable instrument reconciliation issues, against a
  separately named disposable PostgreSQL database. `upgrade head -> downgrade -1 -> upgrade
  head` passed; the downgrade removed and the upgrade restored the newest reconciliation queue
  migration.
- [x] Removed the disposable database after the run; the branch workstation database was not
  touched. This closes the current migration revalidation slice.
- [ ] Exact-build/unrepresented visual states, provider-entitlement breadth, native physical
  multi-monitor validation, beyond-bounded endurance, and the final whole-goal audit remain open.
  Acceptance flexibility used: **None**.

### 2026-08-11 runtime provider-boundary and excluded-menu audit (latest)

- [x] Current branch Compose services are healthy; `/health` reports `ok` with both E2E seed flags
  false, and the frontend shell responds successfully on the branch port.
- [x] Provider-neutral and entitlement boundary tests pass `18/18`. The authenticated excluded
  capability browser check passes `1/1`, confirming that trading, brokerage, options, news,
  ratings, earnings, financial statements, and consolidated real-time surfaces remain absent from
  the primary workstation menu.
- [x] Recent backend, worker, research-runner, and frontend logs contain none of the tracked
  5xx/traceback/MissingGreenlet/constraint/critical/fatal/unhandled/error signatures. A single
  transient startup Redis retry warning resolved and did not recur.
- [ ] This is runtime containment evidence, not closure of visual/reference, provider-breadth/live
  entitlement, native-monitor, beyond-bounded endurance, or final-audit gaps. Acceptance
  flexibility used: **None**.

### 2026-08-11 SEC ambiguous-ticker reconciliation guard (latest)

- [x] SEC discovery now marks a ticker as ambiguous when distinct CIK/name identities share it
  across venues. Same-issuer multi-venue rows remain eligible to create one canonical instrument
  with multiple listings; distinct issuers are retained in the raw `UniverseDiscoverySnapshot` and
  skipped by canonical seeding instead of being merged by ticker text.
- [x] Added provider and persistence regressions for columnar/object SEC payloads, duplicate
  tickers, and the no-promotion rule. Focused tests pass `90/90`; the authoritative backend gate
  passes `1359/1359` at `79.57%`; changed-file Ruff/compile checks pass.
- [ ] The raw snapshot is the current reconciliation queue; a user-facing review/resolution
  workflow and historical listing/delisting model remain open. SEC HTTP 403 live-access evidence
  is also still unresolved. Acceptance flexibility used: **none**.

### 2026-08-11 SEC multi-venue security-master discovery (latest)

- [x] Added SEC's official `company_tickers_exchange.json` directory as a provider-neutral,
  no-key US issuer/listing discovery source. It accepts both SEC payload shapes, caches the
  directory for 24 hours, pages deterministically, preserves reported venue labels and CIKs,
  and exposes only `EQUITY` discovery; it does not claim price coverage or current tradability.
- [x] Added SEC discovery after Alpaca in the configured universe chain. Canonical seeding now
  records exchange evidence through the existing listing normalizer and stores the SEC CIK/source
  metadata on the provider-symbol binding, covering venues beyond Nasdaq without collapsing
  same-ticker listings.
- [x] Added columnar/object payload, pagination, venue, and capability regressions. Focused SEC
  provider coverage passes `81/81`; registry and changed-file Ruff/compile checks pass; the full
  authoritative backend gate passes `1357/1357` at `79.56%`; frontend Vitest remains `682/682`.
- [ ] This improves the all-exchange identity boundary but does not make SEC a complete tradable
  universe or price source. Funds/ETFs, delistings, historical listing truth, provider-specific
  venue coverage, and live entitlement evidence remain explicitly governed gaps. Acceptance
  flexibility used: **none**. An opt-in live probe from this environment returned SEC HTTP 403,
  so live promotion remains unclaimed until an authorised runtime can satisfy SEC access policy.

### 2026-08-11 core workstation clean-deployment bootstrap (latest)

- [x] Added a provider-neutral curated bootstrap for the core US workstation universe: SPY, RSP,
  QQQ, DIA, IWM, all 11 Select Sector SPDR ETFs, and NVDA. It is idempotent, records canonical
  identity/listing provenance, creates the top-down taxonomy, and does not invent an SPX tradable
  instrument or synthetic prices.
- [x] Added worker-owned hydration for missing adjusted D1 history and ETF holdings. It reuses the
  existing entitled provider routes, writes real canonical observations with provenance, and is
  bounded, asynchronous, retryable, and disabled for E2E fixture mode. Fresh isolated Compose
  validation produced canonical history for all 17 core instruments and 16 non-fixture holdings
  snapshots; holdings resolution expanded the disposable database with real constituent identities.
- [x] Added focused bootstrap/worker tests and reran the authoritative backend gate: `1355/1355`
  passed at `79.56%` against the 75% threshold. No fixture data or yfinance fallback was used.
- [ ] This closes the fresh-deployment data-readiness defect, not the whole product goal. XLC has
  shorter but explicitly retained coverage (2046 versus 2513 D1 rows); broader all-exchange
  security-master coverage, exact/unrepresented V25 visual states, physical multi-monitor
  validation, long-duration endurance, and final audit remain open and tracked.
  Acceptance flexibility used: **none** for implementation or data correctness; the existing
  board-guided/populated-canonical visual track remains the only documented interim reference
  flexibility.

### 2026-08-11 seeded provenance isolation and complete board revalidation (latest)

- [x] Fixed a real acceptance-path defect in the TC2000 workstation: when the seeded browser
  stack reused a persistent database, market-data reads could refresh through a provider and ETF
  holdings reads could select canonical snapshots. Seeded OHLCV reads now select only
  `e2e_reference` rows and never invoke providers; seeded holdings reads select only
  `controlled_fixture`/`e2e_reference` snapshots. Normal non-seeded provider-neutral reads are
  unchanged.
- [x] Focused backend coverage passes 36/36, changed-file Ruff passes, and the authoritative
  combined backend gate passes 1351/1351 at 79.62% (75% threshold). The rebuilt isolated
  stack is healthy. The post-run database proves SPY D1 has only the 520 controlled rows and no
  provider rows were reintroduced; canonical holdings remain stored but are hidden from seeded
  acceptance reads rather than relabelled or deleted.
- [x] Refreshed only the previously contaminated untracked board baselines from the corrected
  fixture, then ran the normal no-update Playwright matrix: 104/104 across 1920x1080 and
  2560x1440 at 100% and 125%. No threshold, mask, CSS token, or product acceptance criterion
  changed. The earlier mixed-provenance failures and interrupted run are retained as defect
  evidence, not acceptance results.
- [ ] This is still TC2000 workstation/top-down work; ETF provider support is enabling backend
  infrastructure, not a product reprioritisation. Remaining gaps are exact-build/permission and
  unrepresented V25 references, broader free-source/provider entitlement coverage, native
  physical-monitor validation, long-duration endurance, and the final whole-goal audit.
  Acceptance flexibility used: the documented seeded-fixture/board-guided baseline refresh only;
  no visual threshold or product criterion was relaxed. Docker non-volume prune reclaimed
  16.12GB and preserved named volumes.
- [x] Broader workstation validation after the repair passes frontend Vitest `682/682` across 92
  files, `vue-tsc --noEmit`, and the 468-module production build. The complete authenticated
  workflow matrix passes `85/87` with two canonical-only skips; the skips are not seeded failures
  and remain documented as entitlement/canonical-data limitations. Provider defaults were audited:
  the new workstation uses API-first chains, while yfinance remains excluded from non-options
  chains unless explicitly enabled for legacy compatibility.
- [x] Restored the documented official reference pack into controlled storage and rebuilt the
  browsable board: 230 media sources across 26 surfaces, board validator `230/230`, and rendered
  preview inspected against the current workstation baseline. A fresh non-seeded database was
  also audited: it contains only the bootstrap SPY identity, zero bars, group members, and
  holdings snapshots, so its 16 downstream workflow failures are recorded as an explicit
  canonical-data initialization prerequisite rather than product failures. The populated branch
  volume with seeded mode disabled passes the complete authenticated workflow matrix `87/87`
  against retained canonical data; the seeded acceptance stack was restored and is healthy.
  Acceptance flexibility used: board-guided controlled reference storage and populated canonical
  volume; no visual threshold, mask, or functional criterion was relaxed. Docker prune reclaimed
  6.808GB while preserving active/named volumes.

### 2026-08-11 canonical ETF-proxy drilldown and industry-context race repair

- [x] Repaired the canonical top-down drilldown path: industry selections now carry their
  selected sector ETF context through docked and popped-out tools, and the store establishes the
  selected ETF synchronously before late holdings hydration can clear the selected industry.
  This closes a real UI race rather than weakening the acceptance oracle.
- [x] Rebuilt the branch stack with the repository-controlled provider path and refreshed the
  canonical SOXX and SMH issuer snapshots. XLK/Semiconductors now returns both SOXX and SMH with
  labelled canonical provenance: SOXX via iShares and SMH via VanEck's dated native workbook.
  SMH's stale historical `ark` adapter classification and SEC-series-id route shadowing were
  repaired so the explicit VanEck product slug wins during bootstrap, ingest, and bulk refresh.
- [x] Added deterministic browser response synchronization for the proxy drilldown and verified
  the focused top-down slice (F8d/F8e) passes `10/10`, including the direct XLK/SPY ratio launch.
  The complete authenticated `flows.spec.ts` matrix passes `87/87`; frontend Vitest passes
  `682/682` across 92 files; `vue-tsc`, the 468-module production build, uPlot contract,
  YAML/JSON parsing, and `git diff --check` pass. The authoritative backend gate passes
  `1351/1351` at `79.64%` coverage.
- [x] Runtime audit found only expected client cancellations, deliberate 401/409 conflict-oracle
  traffic, and explicit 404 unavailable-data responses for unseeded/non-entitled symbols; no
  unhandled exception, traceback, 5xx, MissingGreenlet, UniqueViolation, CRITICAL, FATAL, or
  unhandled-error signature was found.
- [x] A post-fix full board-matrix rerun was attempted with elevated Chromium execution, but the
  visual preflight correctly rejected the stack because its backend advertised
  `e2e_seed_market_data=false`; that run is setup evidence and is not counted. The accepted
  seeded board matrix remains `104/104` from the corrected stack. The latest changes alter event
  context and selection timing only, with no CSS/layout/token or screenshot baseline changes.
- [ ] This work is core workstation/top-down implementation, not a diversion into ETF providers.
  Provider work is enabling infrastructure for the workstation and remains incomplete for broad
  free-source coverage beyond the verified proxy set. Exact-build/reference approval,
  unrepresented V25 states, native multi-monitor validation, indefinite endurance, and final
  audit remain open. Acceptance flexibility used: **None**; SMH closure used the authorised
  public issuer route and live dated response, not fixture substitution.

### 2026-08-11 Direct watchlist ratio launch

- [x] Added the missing TC2000-style one-action relative-strength workflow to every virtual
  watchlist context menu: `Open ratio vs active` now emits a typed row action, is disabled for
  self-ratios, and configures the existing Relative Strength tool with `=ROW/ACTIVE` without a
  route change or duplicate chart renderer.
- [x] Fixed the ratio-chart rendering branch so an explicit row-launched expression is rendered
  as its numerator/denominator pair rather than being ignored by the factory ratio configuration.
- [x] Focused component coverage passes `58/58`; adjacent browser ratio coverage passes `2/2`,
  including the new XLK/SPY launch; `vue-tsc --noEmit` and the Docker production build (468
  modules) pass. The first browser attempt used a stale frontend image and was discarded as setup
  evidence; the rebuilt rerun passed. No acceptance flexibility was used.
- [ ] The broader visual/reference, provider-entitlement breadth, native-monitor, endurance, and
  final-audit gaps remain open. The new ratio action is now part of the essential top-down
  workflow and must remain covered by the full authenticated matrix.

### 2026-08-11 deterministic fixture isolation and complete board visual revalidation

- [x] Fixed seeded acceptance data contamination: E2E startup now deterministically replaces the
  controlled universe's adjusted D1 bars, and seeded ETF-holdings reads are restricted to the
  controlled fixture provenance. The focused regression slice passes `17/17`; this prevents a
  reused database from silently mixing canonical and fixture observations.
- [x] Refreshed the four required board-guided visual environments once from the corrected seeded
  runtime, then verified the resulting snapshots without update mode: `104/104` pass across
  1920x1080 and 2560x1440 at 100% and 125% display scale. No screenshot threshold or mask was
  changed; the refresh corrected stale data-state baselines and the current Industries prompt.
- [x] Rebuilt the same seeded stack and reran the complete authenticated functional matrix: `84/84`
  executed tests passed with two documented canonical-only skips; the post-run service-log audit
  found none of the tracked runtime-error signatures. The authoritative backend gate now passes
  `1347/1347` at `79.62%` coverage.
- [ ] This uses the explicitly documented seeded-fixture/board-guided flexibility only. It does
  not close exact-build/permission or unrepresented-state visual gaps, nor provider-entitlement
  breadth, native-monitor, long-duration endurance, or final-audit gaps.

### 2026-08-11 Golden Layout readiness, conflict-oracle tie-break, and full seeded matrix

- [x] Golden Layout bootstrap now suppresses observational activation/normalisation events until
  host interaction, preventing startup from creating unsolicited workspace snapshots. Add Tool
  waits for an explicit workspace-ready signal and reports an actionable unavailable-layout state
  rather than silently dropping the command.
- [x] F8j conflict injection is scoped to the newly added local Notes window, so legitimate
  bootstrap/pop-out cleanup snapshots cannot consume the 409 oracle. This follows the documented
  fix-first tie-break rule: the readiness defect and test setup race were fixed and validated,
  not hidden by relaxing acceptance. Focused adjacent F8j checks pass 2/2 twice.
- [x] Recreated backend/worker/research-runner with explicit seeded acceptance flags after a
  frontend-only rebuild left the backend in false/false mode. Direct authenticated API probes
  return XLK/XLB industry compositions and XLK/Semiconductors verified proxies. The complete
  authenticated flows matrix passes 84/84 executed tests with two documented canonical-only skips;
  Vitest passes 679/679 across 92 files, type-check/build (468 modules), the uPlot contract guard,
  YAML/JSON parsing, diff check, and the audited post-run service logs pass.
- [ ] Remaining visual/reference, provider-entitlement breadth, native-monitor, long-duration
  endurance, and final-audit gaps remain tracked. Acceptance flexibility used: None; the seeded
  fixture is the existing explicit browser-validation track and the mixed-runtime run was
  discarded as setup evidence, not treated as a product pass.

### 2026-08-11 Versioned provider entitlements and seeded top-down oracle

- [x] Provider entitlements now retain append-only revisions in
  `provider_entitlement_revision`; the current row carries its revision number, API PATCH creates
  a new immutable snapshot, and `/providers/entitlements/history/{provider}/{capability}` exposes
  the ordered history. Runtime seeding is idempotent and upgrades legacy `unreviewed` rows into a
  new reviewed revision without rewriting the old snapshot. Unknown/unreviewed capabilities are
  no longer implicitly free or runtime-usable; explicit free-source entitlement seeds control the
  workstation chains.
- [x] Added migration `f2a3b4c5d6e7`, model/service/router coverage, and tests for unreviewed
  exclusion, idempotent history, reviewed upgrade, API revisioning, and history retrieval. Focused
  provider/runtime/router coverage passes `19/19`, the revision-transition slice passes `14/14`,
  and the current-head authoritative backend gate passes `1346/1346` at `79.61%` (75% required).
- [x] Rebuilt an isolated seeded stack; Alembic reports `f2a3b4c5d6e7 (head)`, runtime logs are
  clean, and the top-down F8d/F8e slice passes `7/7` with two intentionally skipped canonical-only
  tests. Corrected `F8e.1` so seeded stacks assert labelled fixture provenance while non-seeded
  stacks still require canonical provenance; the prior seeded failure was a test-oracle/setup
  mismatch, not a product data claim.
- [ ] This closes a provider-governance implementation gap but not the broader provider
  entitlement/coverage audit, visual/reference, native-monitor, long-duration endurance, or final
  audit gaps. Acceptance flexibility used: **None**; the seeded/canonical oracle distinction is
  explicit and both evidence tracks remain required.

### 2026-08-11 Provider-neutral workstation boundary audit

- [x] Audited the current workstation source and provider runtime contract. The primary frontend
  contains no provider names, credentials, endpoint details, or fallback order; provider selection
  remains behind canonical APIs and capability metadata. Focused backend coverage passes `12/12`
  with `test_frontend_provider_boundary.py` and `test_provider_runtime.py` using `--no-cov`.
- [x] Rebuilt an isolated seeded current-head Compose stack and ran the authenticated excluded-domain
  menu acceptance `unsupported capability domains stay out of the primary workstation menu`: `1/1`.
  Trading, brokerage, options, news, ratings, earnings, financial statements, and consolidated
  real-time labels remain absent from the primary workstation menu, with no disabled/coming-soon
  shell exposed. Focused workspace persistence/layout Vitest coverage also passes `52/52`.
- [x] The initial focused backend invocation passed all tests but exited non-zero because the
  repository-wide coverage threshold cannot be met by a 12-test subset; it was rerun with
  `--no-cov` and passed cleanly. The first browser invocation targeted an unavailable port before
  the isolated stack existed; it was setup failure, then rerun against the rebuilt stack and passed.
- [ ] This closes no provider-breadth or entitlement gap: the audit proves boundary isolation and
  menu containment only. Provider entitlement breadth, visual/reference, physical-monitor,
  long-duration endurance, and final-audit gaps remain open. Acceptance flexibility used: **None**.

### 2026-08-10 Industries empty-state clarity and current-head closure

- [x] Corrected the default Industries tool state: when no sector/ETF is selected it now says
  `Select a sector to inspect its industries and verified ETF proxies` instead of falsely
  reporting missing proxy coverage for the active benchmark SPY. Once an ETF is selected, the
  evidence-qualified `No mapped ETF proxy for {ETF}` message remains unchanged.
- [x] Added authenticated browser regression `F8e-empty-industry` (`1/1`), full frontend Vitest
  passes `679/679`, the Docker frontend rebuild passes the 468-module production build, and the
  current complete authenticated matrix now passes `86/86` in `9.7m`. Post-run service logs are
  clean for all audited runtime-error signatures.
- [x] Ran the focused default-shell board visual against a fresh seeded acceptance project. The
  four-environment snapshot update was limited to the reviewed default-shell copy change and the
  four assertions pass `4/4` without update mode. No threshold or mask changed. A preliminary
  visual attempt against the persistent unseeded stack was rejected as invalid data-state evidence;
  a guessed nonexistent unit-test path was likewise corrected by running the actual full suite.
- [ ] The overall goal remains open for visual/reference, provider-entitlement breadth,
  native-monitor, long-duration endurance, and final-audit gaps. Acceptance flexibility used:
  **None** for the implementation; the fresh seeded board run remains the documented interim
  board-guided basis for represented states.

### 2026-08-10 Complete current-head authenticated workstation matrix

- [x] The complete authenticated `flows.spec.ts` matrix passes `85/85` in `9.6m` with one
  worker against the current branch stack. This includes authentication, charts/templates,
  docking/pop-outs/recovery, link groups/timeframes/cross-window cursors, SPX/SPY/RSP and all
  sector/industry/proxy/constituent drill-down, Python/Study Lab, scans/gauges, notes/alerts,
  legacy boundaries, unsupported-domain containment, uPlot performance, and lifecycle churn.
- [x] Post-run backend, worker, research-runner, and frontend service logs contain none of the
  audited HTTP-5xx, traceback, `MissingGreenlet`, `UniqueViolation`, `CRITICAL`, `FATAL`,
  `Unhandled`, or `ERROR` signatures; all branch services remain healthy/running.
- [ ] The overall goal remains open for visual/reference, provider-entitlement breadth,
  native-monitor, long-duration endurance, and final-audit gaps. Acceptance flexibility used:
  **None**.

### 2026-08-10 Study Lab/Research Results current-head browser revalidation

- [x] The focused authenticated browser slice for reusable Study Lab outputs, structured event
  studies, factory streaks, scan/alert promotion, validation recovery, queued cancellation, and
  semantic Study Results passes `8/8` in `1.1m` on the current stack.
- [x] The full frontend suite immediately afterward passes `679/679` across 92 files. The expected
  watchlist failure-path stderr remains covered behavior, not an unhandled test failure.
- [ ] The overall goal remains open for the documented visual/reference, provider-entitlement,
  native-monitor, long-duration endurance, and final-audit gaps. Acceptance flexibility used:
  **None**.

### 2026-08-10 Authoritative combined backend revalidation after current-head continuation

- [x] The repository-root backend gate now passes `1343/1343` in `240.69s` with `79.60%`
  combined coverage (above the required 75%). This includes the canonical security-master,
  exchange, ETF holdings/provider adapters, top-down analysis, unified Python/research/sandbox,
  persistence, and API integration suites.
- [x] The first local invocation was blocked before test collection by sandbox access to the shared
  `uv` cache; the identical command was rerun with approved elevated access and completed cleanly.
  The only output beyond passing tests was 86 known third-party NumPy/nautilus deprecation warnings.
- [ ] This validates the supporting backend contract; it does not close the TC2000 workstation's
  remaining board/reference, provider-entitlement breadth, native-monitor, long-duration endurance,
  or final-audit gaps. Acceptance flexibility used: **None**.

### 2026-08-10 Sparkline non-finite data normalization

- [x] The shared sparkline cache now drops null, non-numeric, and non-finite close values before
  deciding whether a series is renderable. This prevents provider-quality anomalies from poisoning
  uPlot scales or direction coloring while preserving the existing minimum-two-point contract.
- [x] Focused composable/component tests pass `6/6`; full frontend Vitest passes `679/679`;
  `vue-tsc`, production build, `make test-uplot-contract`, and authenticated dashboard `F15`
  (`1/1`) pass. The first chained contract invocation ran from `frontend/` and was corrected by
  rerunning from the repository root; no product failure or acceptance flexibility resulted.
- [ ] The overall goal remains open for documented visual/provider/hardware/endurance/final-audit
  gaps. Acceptance flexibility used: **None**.

### 2026-08-10 uPlot-only Strategy Lab outcome maps

- [x] Replaced the axes-based SVG numerical renderers in `DistributionBars.vue` and
  `SymbolPerformanceBars.vue` with uPlot-backed numeric axes/canvas plugins plus accessible
  HTML point controls. Existing loss/breakeven/win composition, histogram bars, point hover,
  keyboard focus, and detailed tooltips remain available.
- [x] Focused outcome-map tests pass `2/2` and assert that each component constructs uPlot with
  its numeric rendering plugin. The first full-suite run exposed missing positional methods in the
  shared jsdom uPlot double; defensive API guards were added, and the subsequent full suite passes
  `676/676` with no unhandled errors. Type-check, production build, and the elevated authenticated
  legacy-route browser check (`1/1`) pass.
- [ ] The overall TC2000 goal remains open for exact-build/unrepresented visual states,
  provider/entitlement/taxonomy breadth, physical-monitor validation, beyond-bounded endurance,
  and final requirement audit. Acceptance flexibility used: **None**.

- [x] The complete authenticated Chromium flow matrix was rerun after this shared renderer change:
  `85/85` in `11.3m` with one worker. Backend, worker, research-runner, and frontend logs contain
  none of the audited HTTP-5xx, traceback, `MissingGreenlet`, `UniqueViolation`, `CRITICAL`,
  `FATAL`, `Unhandled`, or `ERROR` signatures.
- [x] Docker hygiene was applied after measured usage exceeded 10GB: the authorized non-volume
  prune reclaimed `6.5GB`; all branch services remained running/healthy and named volumes were
  preserved. Post-cleanup Docker usage is approximately `6.7GB` including volumes.
- [x] Added official timeframe-linking behavior evidence to the manifest and `REF-LINKING-V25`
  record. It confirms eight groups, yellow wildcard propagation, grey isolation, cross-layout, and
  multi-monitor linking; manifest validation passes. It does not close the visual gap because no
  pinned-build screenshots or deterministic measurements are supplied.
- [x] Added `make test-uplot-contract` / `tests/visual/validate-uplot-renderer-contract.py` as a
  preventive guard over 42 primary workstation/strategy/common/dashboard source files. It rejects
  dynamic SVG numerical geometry and removed sparkline helpers while allowing static icons and
  excluded legacy options canvases; the guard passes. Acceptance flexibility used: **None**.

### 2026-08-10 uPlot-only Strategy result renderer

- [x] Replaced the axes-based SVG renderer in `StrategyResultChart.vue` with a lifecycle-safe
  uPlot host. The chart preserves real elapsed-time x-values, range selection/shifting, numeric
  formatting, dense hover details, legends, resize handling, and teardown; no axes-based numerical
  output remains in this component outside uPlot.
- [x] Added focused uPlot data/range/hover/axis-format/lifecycle tests (`6/6`), updated the shared
  jsdom uPlot double with `setScale`, and revalidated the full frontend suite (`676/676`),
  Strategy Lab view suite (`28/28`), type-check, and 468-module production build. The elevated
  authenticated legacy-route browser check passed `1/1` after the initial macOS Chromium launch
  was denied by `mach_port_rendezvous` permissions.
- [ ] The overall TC2000 goal remains open for the documented exact-build/unrepresented visual,
  provider/entitlement/taxonomy, physical-monitor, beyond-bounded-endurance, and final-audit gaps.
  Acceptance flexibility used: **None** for this implementation; the first browser launch failure
  is recorded as an environment launch issue, not a product pass or a goal blocker.

### 2026-08-10 Unified Python visual condition boundary

### 2026-08-10 Rebuilt service-runtime verification

- [x] Rebuilt the branch `backend`, `research-runner`, and `worker` images after Docker
  hygiene cleanup; all three services recreated and reached healthy status with the branch
  Compose project.
- [x] Ran the no-network research-runner smoke against the rebuilt image: the factory
  positive-close streak study completed and returned the expected current streak and records.
- [x] Startup log audit for backend, worker, and research-runner found no audited 5xx,
  traceback, `MissingGreenlet`, `UniqueViolation`, `CRITICAL`, `FATAL`, `Unhandled`, or
  `ERROR` signatures. This verifies runtime packaging in addition to the test-only gates.

- [x] Compile the supported visual EasyScan condition tree into the single versioned Python SDK,
  including logical groups, thresholds/crosses, performance, 52-week events, and prepared
  metadata/statistics; reject unsupported nodes with structured diagnostics.
- [x] Persist each new visual condition as a user-isolated immutable Boolean `CodeVersion`, retain
  the visual source tree and generated source, and route new `/from-condition` runs through the
  isolated Python runner while preserving an explicit legacy compatibility path.
- [x] Add prepared canonical metadata, canonical indicator evaluation, screener-timeframe dataset
  materialization, Market Gauge exclusion normalization, focused regressions, no-network runner
  smoke coverage, and the EasyScan first-run Python-version assertion.
- [x] Current gates: backend `1337/1337`, `79.59%` coverage; authenticated Chromium `85/85` after
  a `10/10` focused hidden-refresh repetition; branch service-log audit clean.
- [ ] Continue the overall TC2000 goal: exact-build/unrepresented visual references, provider /
  entitlement / taxonomy breadth, physical multi-monitor validation, beyond-bounded endurance,
  and final requirement audit remain open. No acceptance criterion was silently relaxed.
- [x] Thread the immutable code-version lookback into canonical dataset materialization for Study
  Lab, EasyScan, Strategy Lab, and reruns. Batch history now receives at least `lookback + 1`
  bars; single/benchmark history follows the same bounded requirement; lookbacks at or above the
  5,000-bar cap fail explicitly. Focused materialization coverage passes `21/21`, affected
  EasyScan/Strategy Lab coverage `82/82`, and the current backend gate passes `1343/1343` at
  `79.60%`. Docker hygiene reclaimed `12.29GB` of non-volume objects while preserving volumes.

### 2026-08-10 Non-seeded core top-down workstation gate

- [x] Rebuilt the branch stack with `E2E_SEED_INSTRUMENTS=false` and
  `E2E_SEED_MARKET_DATA=false`; `/health` confirmed both flags are false.
- [x] Authenticated Chromium top-down slice passes `8/8` in `48.2s` for SPX proxy labelling,
  SPY/RSP, canonical SPY/RSP/XLK holdings, all 11 sector industry surfaces, XLK/XLE ratio
  editing, deep industry-proxy/constituent drilldown, and stable horizontal scrolling.
- [x] Backend, worker, and research-runner logs are clean for the audited runtime-error
  signatures.
- [x] The complete authenticated `flows.spec.ts` matrix against the same non-seeded stack passes
  `85/85` in `9.5m` with one worker, covering shell/layouts, linking, pop-outs, Python/Study Lab,
  scans/gauges, notes/alerts, legacy boundaries, uPlot performance, and lifecycle/churn.
- [x] Together with the current backend/type/build gates, this satisfies the documented initial
  robust-workstation gate on a clean non-seeded deployment.
- [ ] The overall goal remains open: provider/entitlement/taxonomy breadth, board/reference
  gaps, physical monitor validation, beyond-bounded endurance, and final requirement audit remain
  open.
  Acceptance flexibility used: **None** for this run.

### 2026-08-10 Final current-head workstation acceptance matrix

- [x] Complete authenticated Chromium matrix passes `85/85` in `9.6m` after localized fix-first
  oracle repairs; full frontend Vitest passes `675/675`, type-check passes, and the 468-module
  production build passes.
- [x] Validate focused oracle repairs (`5/5` plus `4/4`) for pop-out hydration, Study Lab
  validation/promotion, watchlist drag readiness, freshness/OHLCV response timing, SPX proxy
  resolution, reset readiness, and source-tool churn.
- [ ] Continue closing remaining workstation/backend gaps. The board/fixture visual track is
  accepted for represented states, but exact-build/unrepresented references, provider/entitlement/
  taxonomy breadth, physical-monitor validation, beyond-bounded endurance, and final audit remain
  open and must stay visible.

### 2026-08-10 Watchlist failure isolation and final current-head matrix

- [x] Keep benchmark/sector market-group and snapshot failures list-scoped, visibly announced,
  and non-destructive to cached rows.
- [x] Validate busy/error browser paths (`2/2`), focused component coverage (`56/56`), full
  frontend Vitest (`674/674`), type-check/build, and authenticated Chromium (`84/84`).
- [ ] Continue closing remaining workstation/backend gaps; exact-build/unrepresented visual,
  provider/entitlement/taxonomy, physical-monitor, endurance, and final-audit gaps remain tracked.

### 2026-08-10 Watchlist refresh-state acceptance

- [x] Add explicit busy semantics to benchmark and sector virtualized watchlists without changing
  dense geometry or dropping rows during shared market-analysis refresh.
- [x] Add component and browser acceptance coverage: focused `55/55`, F8s-watchlist `1/1`, and
  complete authenticated Chromium `83/83`.
- [ ] Continue closing remaining workstation/backend gaps; visual-reference, provider/entitlement/
  taxonomy, physical-monitor, endurance, and final-audit gaps remain tracked.

### 2026-08-10 Current board-guided visual matrix after lifecycle/recovery work

The exact current UI passes the complete no-update board-guided visual matrix `104/104` in `8.9m`
across 1920×1080 and 2560×1440 at 100% and 125% display scale. The isolated seeded stack used
alternate ports, service-log audit found no known runtime error signatures, and it was stopped
without deleting named volumes. Acceptance flexibility used: documented 230-image board/fixture
interim authority for represented states. Exact-build/unrepresented gaps `REF-SHELL-V25`,
`REF-STATE-VARIANTS`, `REF-LINKING-V25`, `REF-STUDY-LAB-V25`, `REF-ENV-TOKENS`, and
`REF-PERMISSION-REVIEW`, plus provider/monitor/endurance/final-audit gaps, remain open; no
threshold, mask, or product criterion changed.

### 2026-08-10 Workspace conflict recovery and current-head matrix

Added browser acceptance for a forced revision conflict during Add Tool, deterministic concurrent
workspace divergence, named recovery-copy creation, and the user-facing preservation message. The
first oracle's unauthenticated baseline fetch and case-sensitive assertion were repaired. Focused
F8j-conflict passes `1/1` in `13.1s`; full frontend Vitest remains `672/672`; type-check/build
remain green; exact current source complete authenticated Chromium matrix passes `82/82` in
`14.9m`. No acceptance flexibility or visual threshold/mask changed; exact-build/unrepresented
visual, provider breadth, native-monitor, beyond-bounded-endurance, and final-audit gaps remain
open.

### 2026-08-10 Study Lab cancellation lifecycle and current-head matrix

Added the real browser lifecycle oracle for Study Lab validation, queued run, cancellation, and
terminal canceled state, including stale-control/polling cleanup. F8t-cancel passes `1/1` in
`14.7s`; full frontend Vitest remains `672/672`; type-check/build remain green; exact current
source complete authenticated Chromium matrix passes `81/81` in `13.5m`. No acceptance
flexibility or visual threshold/mask changed; exact-build/unrepresented visual, provider breadth,
native-monitor, beyond-bounded-endurance, and final-audit gaps remain open.

### 2026-08-10 Market Breadth state semantics and current-head matrix

Market Breadth now exposes explicit universe-scoped busy/loading/error/unavailable state through
independent snapshot/history request tracking while preserving its dense metric, drilldown, and
uPlot history composition. Focused store coverage passes `45/45`, type-check/build pass, rebuilt
F8s-breadth passes `1/1` in `17.4s`, full frontend Vitest passes `672/672`, and the exact current
source passes the complete authenticated Chromium matrix `80/80` in `11.6m`. No acceptance
flexibility or visual threshold/mask changed; exact-build/unrepresented visual, provider breadth,
native-monitor, beyond-bounded-endurance, and final-audit gaps remain open.

### 2026-08-10 Current-head complete workstation matrix

The rebuilt branch stack's complete authenticated Chromium `flows.spec.ts` matrix passes `79/79`
in `14.2m` with one worker after the latest Notes, Coverage, Relative Rotation, and Instrument
Report repairs. It covers the complete workstation/top-down/Python/Study Lab/scans/gauges/
legacy/exclusion/performance/churn acceptance surface. No acceptance flexibility or visual
threshold/mask changed; exact-build/unrepresented visual, provider breadth, native-monitor,
beyond-bounded-endurance, and final-audit gaps remain open.

### 2026-08-10 Instrument Report disclosure keyboard isolation

Instrument Report now exposes a symbol-scoped region and keyboard-operable disclosure header with
explicit button semantics and expanded state. Enter/Space toggle it without changing the dense
visual composition. The first browser run found Space bubbling into global symbol traversal and
changing SPY to QQQ; propagation is now stopped. Focused coverage passes `3/3`, type-check/build
pass, and rebuilt F8s-report passes `1/1` in `9.4s`. No acceptance flexibility or visual threshold/
mask changed; exact-build/unrepresented visual, provider, native-monitor, endurance, and final-
audit gaps remain open.

### 2026-08-10 Relative Rotation state semantics and oracle correction

Relative Rotation now exposes a benchmark-scoped region with busy state, polite loading/empty
statuses, and assertive calculation errors without changing its dense uPlot plane, tails, sortable
table, or controls. Focused coverage passes `6/6`; type-check/build pass; rebuilt Add Tool →
Relative Rotation acceptance passes `1/1` in `9.2s`. The first browser assertion incorrectly
required a status node after a successful loaded response; it was corrected to accept loaded rows/
plot or an explicit status/error state and the rerun passed. No acceptance flexibility, visual
threshold, or mask changed; exact-build/unrepresented visual, provider, native-monitor, endurance,
and final-audit gaps remain open.

### 2026-08-10 Coverage tool state semantics

The symbol-scoped Coverage tool now exposes a named region with busy state, polite loading,
assessment, and empty statuses, assertive fetch/range-validation errors, and labelled dataset
states without changing the dense provenance/OHLCV-readiness composition. Focused coverage passes
`4/4`; type-check/build pass; rebuilt Add Tool → Coverage browser acceptance passes `1/1` in
`15.3s`; full frontend Vitest passes `670/670`. No acceptance flexibility or visual threshold/mask
changed; exact-build/unrepresented visual, provider, native-monitor, endurance, and final-audit
gaps remain open.

### 2026-08-10 Symbol-linked Notes state semantics and rebuilt-image validation

The symbol-scoped Notes tool now exposes a named region with busy state, polite live status for
loading/saving/saved states, and assertive errors for load/save failures. Shared Vue Query note
reads/writes retain generation guards and debounced canonical autosave without changing the dense
composition. Focused linked-tool/race coverage passes `7/7`; full frontend Vitest passes `670/670`;
type-check/build pass. The first browser run caught a stale frontend image; a forced no-cache rebuild
corrected it. Rebuilt F8s passes `1/1` in `13.1s`, and the complete authenticated matrix passes
`76/76` in `13.9m`. No acceptance flexibility or visual threshold/mask changed; exact-build/
unrepresented visual, provider, native-monitor, endurance, and final-audit gaps remain open.

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
Focused coverage passes `19/19`; full frontend Vitest passes `668/668`, type-check and the
468-module production build pass. After rebuilding the branch frontend, authenticated Study Lab
browser acceptance `F8g`, `F8o`, `F8p`, `F8q`, and `F8t` passes `5/5` in `1.2m`. No acceptance
flexibility or visual criterion changed. Study Lab visual-reference, provider, native-monitor,
endurance, and final-audit gaps remain open.

### 2026-08-10 virtual watchlist selection semantics

The virtualized workstation watchlists now expose listbox/option semantics, accessible
symbol/name labels, active and multi-selected row state, and explicit multi-selection metadata.
Focused coverage passes `54/54`; full frontend Vitest passes `667/667`, type-check and the
468-module production build pass. After rebuilding the branch frontend image, authenticated
Chromium F8d, F8d-SPX, and F8r pass `3/3` in `28.6s`; the complete `flows.spec.ts` matrix passes
`75/75` in `11.6m`. The first browser attempt exposed a stale
container and old button-role locators; both were corrected before the passing rerun. No
acceptance flexibility or visual criterion changed. Board/reference, provider, native-monitor,
endurance, and final-audit gaps remain open.

### 2026-08-10 shared tool-window action accessibility parity

The shared TC2000-style tool-window header now exposes explicit accessible names for its menu,
maximize, float, and close icon controls in docked and browser-popout instances. Focused coverage
passes `4/4`; full frontend Vitest passes `666/666`, `vue-tsc --noEmit`, and the 468-module
production build pass. No acceptance flexibility or visual criterion changed. This closes a
repository-controlled shared-chrome accessibility gap; board/reference, provider, native-monitor,
endurance, and final-audit gaps remain open. The F8r browser oracle now asserts the same names and
passed 1/1 in 13.0s against the rebuilt branch Compose stack.

### 2026-08-10 top-down regression after Keating provider rebuild

After rebuilding the backend with Keating's native route, the authenticated F8d benchmark/sector
and F8d-SPX labelled SPY-proxy browser checks pass `2/2` in `23.5s` on the normal non-fixture stack.
This confirms the provider correction did not regress the core workstation drill-down path. No
acceptance flexibility was used; board, provider breadth, hardware, endurance, and final-audit
gaps remain tracked.

### 2026-08-10 Keating native holdings route

Promoted the official [Keating KEAT fund page](https://etfkeatinginvestment.com/) from a generic
fallback to a provider-specific complete HTML holdings adapter. Effective dates, provenance, and
conditional SEC fallback are preserved. ETF adapter/catalog units pass `471/471`, the exact live
route probe passes `1/1`, and the Docker-backed backend gate passes `1,329/1,329` at `79.60%`.
Registry state is `496` registered, `352` native/live-backed, and `144` audited fallback-only.
This is supporting ETF-proxy/constituent infrastructure, not a change of TC2000 UI direction;
visual-reference, broader provider, monitor, endurance, and final-audit gaps remain open.

### 2026-08-10 Truth Social/Yorkville native-route identity reconciliation

Closed a naming-dependent supporting-data gap: canonical `truth_social` discovery now selects the
verified Yorkville/Truth Social product-page Google CSV route instead of the generic fallback.
The selected official route cases pass `2/2`, ETF adapter/catalog units pass `469/469`, and the
Docker-backed backend gate passes `1,327/1,327` at `79.60%`. Registry state is 496 registered,
351 native/live-backed, and 145 audited fallback-only. No frontend or visual criterion changed;
provider breadth, visual reference, physical monitor, endurance, and final-audit gaps remain.

### 2026-08-10 bounded 500-round workstation lifecycle soak

The current branch stack passes both workstation performance tests (`2/2`) with
`TC2000_POP_OUT_CHURN_ROUNDS=500` in `11.2m`. Real two-popout open/close churn preserved source
tool/chart/canvas counts, heap ceilings, symbol propagation, recovery, and clean browser
diagnostics. This strengthens bounded evidence at the hard repository cap, but does not close
indefinite endurance or native physical-monitor validation. No acceptance criterion was relaxed.

### 2026-08-10 current-head authenticated matrix after supporting-data correction

The actual current normal branch stack reports both E2E seed flags false, and the current
`frontend/tests/e2e/flows.spec.ts` collection passes `75/75` in `11.9m` with one worker. It
covers the current authentication, chart/template/drawing, workspace/pop-out, linking,
top-down/ratio, Python/Study Lab, scans/gauges, notes/alerts, legacy, unsupported-domain, and
containment paths. Older `78/78` prose refers to a different test-file snapshot and is superseded
for current-count reporting. No UI/visual criterion changed; board/fixture flexibility and the
remaining reference, provider, monitor, endurance, and final-audit gaps remain open.

### 2026-08-10 AltShares native-route identity reconciliation

Fixed a real supporting-data gap in the top-down workflow: canonical `altshares` discovery now
selects the verified complete AltShares periodic portfolio report, alongside the existing
`water_island` adviser alias, instead of the generic fallback adapter. The official route live
case passes `1/1`, ETF adapter/catalog units pass `468/468`, and the Docker-backed backend gate
passes `1,326/1,326` at `79.60%`. No frontend or visual criterion changed. Provider breadth,
exact/unrepresented visual evidence, physical monitor, endurance, and final-audit gaps remain
explicitly tracked.

### 2026-08-10 full authenticated workflow revalidation after fixture-target repair

The normal non-fixture branch stack passes the complete authenticated Chromium matrix `75/75` in
`11.1m`, including the workstation/top-down, linking/pop-outs, Python/Study Lab, scans/gauges,
notes/alerts, legacy, unsupported-domain, and performance paths. Service logs are clean and no
functional acceptance flexibility was used; remaining visual/provider/monitor/endurance/final-
audit gaps remain tracked.

### 2026-08-10 fixture propagation repair and isolated board visual acceptance

The stack target now propagates explicit instrument/market fixture flags. The persistent canonical
stack was not used for visual baselines after its mixed-data difference was detected; a dedicated
seeded project passed the full `104/104` board-guided matrix across all four display environments,
with overlap and interaction checks. Controlled fixture/board flexibility remains explicitly
tracked; no threshold, mask, or product criterion changed.

### 2026-08-10 focused provider/top-down backend regression gate

The focused provider, ETF-adapter, and top-down-taxonomy suite passes `557/557` with `--no-cov`.
The subset's initial coverage-threshold exit was corrected and is not confused with the full
backend gate. No provider promotion or acceptance flexibility occurred; broader provider breadth
remains tracked.

### 2026-08-10 frontend regression/type/build gate

The current frontend gate passes `666/666` tests across 91 files, type-check, and production
build (468 transformed modules). The unsupported initial `--runInBand` invocation was corrected;
expected watchlist conflict stderr is intentional failure-path coverage. No acceptance flexibility
was used and the remaining visual/provider/monitor/endurance/final-audit gaps stay tracked.

### 2026-08-10 official keyboard behavior evidence

The official [Version 25 Hot Keys & Keyboard Shortcuts](https://help.tc2000.com/m/125751/l/1874569-hot-keys-keyboard-shortcuts)
article is recorded as behavior-only authority evidence for symbol search, list traversal,
timeframe navigation, chart shortcuts, and maximize. It does not close the corresponding visual
reference gaps because it contains no deterministic pinned-build screenshots or measurements.
Keep those states in the explicit gap ledger; no acceptance flexibility was used.

### 2026-08-10 manifest and operations consistency audit

The current visual manifest validates all 230 board media records; operations YAML/JSON parse and
`git diff --check` pass. This is structural evidence only: exact-build/state-variant, provider,
monitor, endurance, and final-audit gaps remain tracked and no acceptance flexibility was used.

### 2026-08-10 authoritative backend gate after full workflow closure

`make test-backend-coverage` passes `1,325/1,325` in `4m24s` with `79.60%` coverage, above the
75% gate. Provider/ETF, canonical instrument, top-down analysis, Python/research/sandbox,
persistence, and API paths remain green; only known third-party NumPy/nautilus deprecation
warnings appeared. No acceptance flexibility used. Continue with the explicitly tracked visual
state/reference, provider/entitlement breadth, native-monitor, endurance, and final-audit work.

### 2026-08-10 full authenticated workflow closure after shell/watchlist fixes

The broad rebuilt authenticated matrix now passes `75/75` in `11.8m` after fixing two localized
workstation defects: mounted watchlist configuration now updates by object identity/live input,
and deep-linked `/chart/SPY` initializes the active-symbol editor synchronously during workspace
hydration. Workstation unit regressions pass `15/15`, focused F9c passes `1/1`, frontend Vitest
passes `665/665`, and type-check/build, seed-free health, service-log audit, and diff checks pass.
No acceptance flexibility was used for these fixes. Continue tracking the documented board-guided
visual flexibility, exact-build/state-variant references, provider/entitlement breadth,
native-monitor, endurance, and final whole-product audit gaps.

### 2026-08-10 isolated seeded visual acceptance revalidation

The persistent-stack visual run was correctly discarded by the seed preflight because canonical
holdings were present while controlled fixture mode was requested; its 27,345-pixel difference
was not promoted. The fresh `tc2000-board-current` Compose project on alternate ports passes the
complete board-guided visual matrix `104/104` in `9.0m` across all four required display
environments. Manifest, seed health, service-log, and diff checks pass. Acceptance flexibility
used: the approved 230-image board and controlled fixtures for interim visual acceptance; exact-
build and unrepresented-state gaps remain open. No threshold, mask, snapshot, or product
criterion changed.

### 2026-08-10 Curated SPDR/VanEck industry-proxy routes

Closed the next canonical top-down proxy gap. `XAR`, `XHB`, and `XOP` now select the verified
SPDR workbook adapter; `OIH`, `SLX`, and `SMH` now carry issuer-resolved VanEck product slugs
(`oil-services-etf-oih`, `steel-etf-slx`, and `semiconductor-etf-smh`). The expanded opt-in live
proxy matrix passes `10/10`, the full ETF adapter suite passes `467/467`, the authoritative
Docker-backed backend gate passes `1,325/1,325` at the configured coverage threshold, and the
rebuilt authenticated `F8e` top-down browser slice passes `6/6` with clean service logs. No
acceptance flexibility used. Remaining proxy/provider breadth, visual-state/reference,
native-monitor/endurance, and final whole-product audit gaps remain open.

### 2026-08-10 Curated iShares industry-proxy routes

Added canonical iShares product identifiers for the curated `IBB` (biotechnology), `ITA`
(aerospace/defense), and `ITB` (home construction) industry proxies. The identifiers are
issuer-resolved from the official product pages—[IBB](https://www.ishares.com/us/products/239699/),
[ITA](https://www.ishares.com/us/products/239502/), and
[ITB](https://www.ishares.com/us/products/239512/)—and are now selected by the provider-neutral
bootstrap route. The opt-in live issuer checks pass `3/3`; the curated iShares unit checks pass
`4/4`, the complete ETF adapter suite passes `467/467`, compilation, Ruff, and `git diff --check`
pass, and the authoritative Docker-backed backend gate passes `1,325/1,325` at the configured
coverage threshold. No acceptance flexibility used. Remaining curated proxy routes, visual-state
gaps, native-monitor/endurance evidence, and the final whole-product audit remain open.

### 2026-08-10 SPDR industry-proxy live coverage

Added live acceptance coverage for curated SPDR industry proxies `XBI` (biotechnology), `KRE`
(regional banks), `XRT` (retail), and `XME` (metals/mining). The official issuer workbooks
returned dated parseable rows: 157, 161, 77, and 41 respectively. The five-case SPDR live slice
(including SPY) passes `5/5`; route-matrix invariants, compilation, and lint pass. No acceptance
flexibility used; iShares/VanEck and other curated industry proxies remain separately tracked.

### 2026-08-10 SOXX industry-proxy route validation

The curated semiconductor industry proxy `SOXX` now has a live acceptance case against the
official iShares product-data route. The dated response returned 34 parseable holdings including
NVDA; the initial 100-row assertion was corrected to a justified concentrated-ETF minimum of 30
and now passes with route/composition-date assertions. Focused iShares checks, compilation, and
lint pass. No acceptance flexibility used; broader industry-proxy coverage remains tracked.

### 2026-08-10 EasyScan condition editor board-coverage closure

The integrated condition-editor state is now `board_covered`: the composed board contains
official Version 25 condition-editor and filter-selection states, and the real interaction
oracle plus four deterministic local baselines pass. The source pages do not prove pinned
`25.0.9571`, so that remains optional strengthening evidence rather than an unrepresented-state
gap. Acceptance flexibility used: board-guided evidence for this represented state; no threshold,
mask, or product criterion changed. Partial coverage remains the watchlist visual gap.

### 2026-08-10 O'Shares native holdings route and full backend validation

O'Shares is now promoted from ETF.com route-discovery fallback to a provider-specific native
adapter using the official ALPS public holdings proxy. OUSA returned complete dated holdings
through the public route; deterministic parser/config tests pass, the elevated opt-in live
matrix passes `2/2`, the ETF adapter suite passes `464/464`, and the authoritative combined
backend gate passes `1,321/1,321` at `79.60%` coverage. Registry state is now 496 registered,
349 native/live-backed, and 147 audited fallback-only. No acceptance flexibility was used;
remaining provider, visual-reference, hardware, endurance, and final-audit gaps remain tracked.

### 2026-08-10 Docker storage maintenance after backend gate

Docker usage was `13.4GB` before maintenance. The authorised non-volume `docker system prune -af`
reclaimed `11.71GB`; post-cleanup usage is `4.10GB` (2.908GB images, 1.187GB named volumes,
and negligible containers), with all 28 named volumes preserved. This is operational hygiene,
not a product-scope change.

### 2026-08-10 Full backend gate after Leverage Shares promotion

The authoritative combined Docker-backed backend unit/integration gate now passes `1,320/1,320`
with `79.59%` line coverage against the required `75%` threshold. The run includes the complete
ETF adapter suite and the new Leverage Shares native-route coverage; only the known third-party
NumPy/nautilus deprecation warnings were emitted. This validates the supporting backend change,
not completion of the TC2000 workstation: exact-build/unrepresented visual states, remaining
provider breadth and entitlement coverage, physical multi-monitor evidence, endurance, and the
final whole-product audit remain tracked.

### 2026-08-10 Leverage Shares native holdings route

Promoted Leverage Shares from audited route-discovery fallback to a provider-specific native
adapter. The official U.S. route
`https://leverageshares.com/us/storage/holdings/{SYMBOL}_Holdings.csv` returned HTTP 200 for
MPG with dated CSV rows, equities, treasury collateral, and cash. The adapter now owns an
explicit fetch entry point and preserves issuer route/provenance metadata. Focused parser and
registry checks pass, the complete ETF-adapter unit suite passes `463/463`, the opt-in live MPG
probe passes `1/1`, and compilation/lint/diff checks pass. Registry coverage is now 496
registered, 348 native/live-backed, and 148 audited fallback-only. No acceptance flexibility was
used; remaining fallback-only providers and any blocked issuer routes stay tracked.

### 2026-08-10 EasyScan condition-editor acceptance path

Added a board-guided acceptance path for the integrated EasyScan technical condition tree. The
new browser oracle opens the real workstation tool through Add tool, expands the condition-group
editor, verifies AND semantics plus the +Condition/+Group controls, and captures deterministic
baselines for all four required display environments. Strict no-update verification passes 4/4;
the complete isolated seeded board matrix passes `104/104` in `8.1m` with clean backend,
worker, and research-runner logs. This is controlled-fixture/interim evidence: official V25
condition-editor help is discovery authority, but the state remains `required_missing` until a
pinned-build capture is available. No threshold, mask, or acceptance criterion changed.

### 2026-08-10 board-guided matrix after column-editor repair

The benchmark watchlist now passes its configured analytical column schema into the shared
virtualized list, and the column editor uses a bounded dense grid/scroll treatment rather than a
compressed horizontal strip. The first strict rerun exposed 19 deterministic screenshot drifts;
review confirmed intentional current-column rendering and stale 1440px seeded dates, so only
affected baselines were refreshed. The complete isolated seeded Compose matrix then passed
`100/100` in `7.7m` across all four required display environments without update mode. Logs were
clean and the stack was stopped without deleting evidence volumes. No masks, thresholds, or
acceptance criteria changed; the code repair is not acceptance flexibility. Exact-build/state-
variant, provider/live-entitlement/taxonomy, native-monitor, indefinite-endurance, and final-
audit gaps remain tracked.

### 2026-08-10 reference-board expansion for filters, linking, and historic columns

Added four official help-page sources to the controlled reference-pack fetch catalogue: the
integrated Condition Editor, ALL/ANY filter selection, symbol linking, and historic columns.
The refreshed pack contains 230 media files across 26 surfaces, and the composite board validator
passed `230/230`. The new pages strengthen board-guided implementation of watchlist/filter and
linking composition; page/build labels remain discovery evidence where they do not prove pinned
build `25.0.9571`, so related exact-build and state-variant gaps remain explicitly open. No
acceptance flexibility, screenshot threshold, mask, or product criterion changed.

### 2026-08-10 board-guided visual matrix after reference-pack refresh

The refreshed 230-image working reference board now has matching deterministic seeded
representations for the currently represented workstation states. The isolated Compose project
(`tc2000-board-current`, alternate ports, seeded instruments and market data) passes the complete
`test:visual:board` matrix `100/100` in `7.7m` across 1920×1080 and 2560×1440 at 100% and 125%
display scale. The backend, worker, and research-runner logs contain none of the audited HTTP 5xx,
traceback, `MissingGreenlet`, `UniqueViolation`, critical, fatal, unhandled, or error signatures.
The stack was stopped without deleting its evidence volumes. This is explicitly board-guided
represented-state evidence using the controlled fixture; it does not claim exact-build/permission
approval, coverage of unrepresented states, live-provider parity, native multi-monitor evidence,
indefinite endurance, or completion of the final requirement audit. No thresholds, masks, baselines,
or product criteria were relaxed.

### 2026-08-10 reference-pack refresh and current backend gate

The controlled reference pack was refreshed from its recorded official URLs: all 190 media files
were retrieved, the composite board was rebuilt across 22 surfaces, and the board validator
passed all 190 sources. The authoritative Docker-backed combined backend gate then passed
`1,319/1,319` at `79.60%` coverage with 86 known third-party deprecation warnings. These checks
do not close the already documented exact-build/unrepresented visual, provider breadth,
native-monitor, endurance, or final-audit gaps.

### 2026-08-10 current-head F9e/F8l regression closure

Applied the fix-first tie-break to the two regressions exposed by the latest complete browser
matrix. Workspace import and factory reset now flush Golden Layout withdrawal and replacement
boundaries so detached Vue roots cannot survive a fast snapshot response; the F9d→F9e sequence
passes `10/10` across five repetitions. Shared top-down store loaders now refuse queued market
analysis requests while the document is hidden; the new unit regression passes `44/44`. The
complete rebuilt authenticated Chromium matrix passes `78/78` in `12.2m`, full frontend Vitest
passes `665/665` across 91 files, `vue-tsc --noEmit`, production build, root `git diff --check`,
and the recent backend/worker/research-runner error-signature audit pass. No acceptance
flexibility used. The goal remains open for documented visual-reference, provider breadth,
hardware, endurance, and final completion-audit gaps.

### 2026-08-10 current-head live top-down browser revalidation

Rebuilt the durable branch backend/worker images so the browser exercised the current canonical
RSP route. The authenticated Chromium top-down slice passes `8/8`: benchmark/sector selection,
SPX→SPY fallback, SPY/RSP relative strength, canonical membership, all-sector industry surfaces,
ratio editing, deep proxy/constituent drilldown, and stable horizontal scrolling. The backend,
worker, and research-runner logs contain none of the audited 5xx/traceback/MissingGreenlet/
UniqueViolation/critical/fatal/unhandled/error signatures. No acceptance flexibility used.

### 2026-08-10 current-tree frontend revalidation after RSP backend correction

The unchanged frontend regression suite passes `664/664` across 91 files; `vue-tsc --noEmit`
and the production Vite build (468 modules) pass. This confirms the backend route correction did
not regress the workstation client. No visual threshold, mask, or acceptance criterion changed;
the documented board/reference, provider breadth, hardware, endurance, and final-audit gaps remain.

### 2026-08-10 Invesco route correction after full-gate regression

The first complete backend gate after the RSP route bridge exposed three stale contract
expectations plus one compatibility regression: catalog/probe assertions still expected the
rejected ticker URL, and explicit Invesco product-page profiles were incorrectly forced through
catalog resolution. The adapter now preserves product-page discovery for explicitly configured
profiles while canonical symbol-only profiles use catalog→CUSIP. Updated assertions and the
compatibility path pass the focused `3/3` regression and the complete backend gate `1,319/1,319`
at `79.60%` coverage. No acceptance flexibility used; the first failed gate is retained as the
fix-first evidence rather than hidden.

### 2026-08-10 canonical RSP bootstrap route wired

The verified Invesco RSP route is now reachable from the canonical ETF bootstrap path, not only
from a direct adapter call. Known route metadata seeds issuer `Invesco`, adapter `invesco`, and
CUSIP `46137V357`; the adapter catalog advertises catalog→CUSIP JSON access rather than the
rejected ticker URL. The canonical bootstrap integration regression and focused adapter tests
pass. No acceptance flexibility used.

### 2026-08-10 Invesco CUSIP-resolved RSP holdings route

Closed a core equal-weight data gap. Invesco's ticker-addressed holdings URL returns an
edge rejection, while its public product catalog resolves RSP to CUSIP `46137V357` and the
CUSIP-addressed holdings endpoint returns 511 rows with issuer effective date `2026-08-08`.
The adapter now resolves ticker→CUSIP through that catalog, caches the identity, fetches the
CUSIP route, preserves route/effective-date provenance, and retains SEC fallback on issuer
failure. The opt-in live RSP provider test passes, all 462 ETF-adapter unit tests pass, and no
acceptance flexibility was used.

### 2026-08-10 patched-stack top-down browser revalidation

Rebuilt the durable branch Compose stack with the holdings provenance guard and reran the
complete focused top-down UI subset: SPX fallback, SPY/RSP, canonical holdings, all-sector
industry traversal, ratio editing, deep proxy/constituent drilldown, and stable scrolling pass
`7/7` in elevated Chromium. The backend/worker/research-runner log audit is clean. No acceptance
flexibility used.

### 2026-08-10 controlled-holdings isolation in normal top-down reads

Closed a repository-controlled provenance leak: non-E2E market-group composition,
industry-constituent, and ETF-constituent analysis reads now exclude `controlled_fixture`
and `e2e_reference` snapshots through one shared policy helper. This matches the existing
proxy-ranking guard, so a newer browser fixture cannot override a canonical free-source
disclosure in the live workstation. The focused Docker-backed regression passes, including
composition/constituent selection of the issuer snapshot over the newer fixture. No acceptance
flexibility used; provider breadth and exact/unrepresented visual gaps remain open.

### 2026-08-10 complete authenticated matrix after branch-stack rebuild

The rebuilt durable branch stack passes the complete authenticated Chromium suite `78/78` in one
serial worker in 11.5 minutes. This revalidates authentication, workstation/layouts, docking and
pop-outs, linking/cross-window cursors/timeframes, keyboard behavior, live top-down drilldown and
ratios, Study Lab/Python promotion, scans/gauges, notes/alerts, legacy/excluded domains, uPlot
performance, and workstation churn after the frontend proxy change. The post-run backend/worker/
research-runner log audit is clean for HTTP 5xx, traceback, MissingGreenlet, UniqueViolation,
CRITICAL, FATAL, Unhandled, and ERROR signatures. Acceptance flexibility used: none. The goal
remains open for documented visual-reference, provider breadth, hardware, endurance, and final
completion-audit gaps.

### 2026-08-10 rebuilt branch-stack live top-down acceptance

The durable branch Compose stack was rebuilt after the health-proxy fix. Both public frontend
`/health` and direct backend `/health` now return JSON with `e2e_seed_instruments=false` and
`e2e_seed_market_data=false`, proving the deployed browser path exposes the backend mode contract.
The non-seeded live top-down subset passed `5/5`: labelled SPX-to-SPY fallback, SPY/RSP default
relative strength, canonical SPY/RSP/XLK holdings, all-sector industry surfaces, and the XLK/XLE
ratio editor. Backend/worker/research-runner logs were clean for the audited error signatures.
Acceptance flexibility used: none; this is live canonical-database evidence rather than seeded
fixture evidence. Broader exact/unrepresented visual, provider, hardware, endurance, and final
completion gaps remain tracked.

### 2026-08-10 Docker acceptance-build cleanup

Docker usage exceeded the goal's 10 GB cleanup threshold (`~11.9 GB` before cleanup). The
explicitly authorised `docker system prune -af` removed unused acceptance images and build cache,
reclaiming `8.083 GB`; active containers and named volumes were preserved. Post-cleanup usage is
approximately `3.9 GB` including volumes. Acceptance flexibility used: none.

### 2026-08-10 Anfield native-route re-audit

The current Anfield/Regents Park ADFI URL was rechecked directly after indexed search results
continued to describe a downloadable holdings file. The live issuer URL returned HTTP 404, so
the existing adapter remains fallback-only and no stale search result was promoted to native/live
support. This is an external provider-route gap with its existing SEC/conditional fallback and
does not affect the core SPY/RSP/sector workflow. Acceptance flexibility used: none.

### 2026-08-10 current-code board-visual acceptance after fixture preflight repair

The first rerun of the new fixture preflight exposed a deployment contract defect: the frontend
served the SPA shell for `/health`, so the preflight received HTML rather than JSON. The nginx
and Vite proxies now forward the exact health path to the backend. After rebuilding the isolated
seeded stack, the unchanged board command passes `96/96` in 7.4 minutes across all four required
display environments; the backend/worker/research-runner log audit is clean. No snapshots,
thresholds, masks, or product criteria changed. The temporary stack was stopped without deleting
volumes. The board-guided represented-state flexibility remains explicit; exact-build/permission,
unrepresented-state, provider/taxonomy, native-monitor, endurance, and final-audit gaps remain
tracked.

### 2026-08-10 isolated board-visual revalidation and fixture preflight

The first unchanged `test:visual:board` attempt against the persistent branch stack was
discarded: its backend was not in seeded mode, so canonical Nasdaq observations mixed with the
deterministic fixture and produced a 27,345-pixel (2%) content diff. This was a validation-harness
defect, not evidence of a geometry mismatch; no snapshots were promoted. The visual harness now
fails fast by checking `/health` when `E2E_SEED_MARKET_DATA=true`, and a focused backend health
regression covers the exposed fixture flags. A separate Compose project with seeded instruments
and market data on alternate ports then passed the complete board-guided matrix `96/96` across all
four required display environments; manifest and service-log audits were clean. The isolated
stack was stopped without deleting volumes and the persistent branch stack was left untouched.
Acceptance flexibility used: the approved 190-image board remains the represented-state visual
authority; no threshold, mask, or acceptance criterion was relaxed. The exact-build/permission,
unrepresented-state, provider/taxonomy, native-monitor, endurance, and final-audit gaps remain
tracked.

### 2026-08-10 current-state authenticated Chromium revalidation

The unchanged full authenticated Chromium matrix passes `78/78` in one serial worker in 12.2
minutes against the current branch stack. It covers authentication, workstation/layouts,
docking/pop-outs/recovery, linking/cross-window cursors and timeframes, keyboard behavior,
canonical SPY/RSP and sector/industry/proxy/constituent drilldown, ratios, Study Lab/Python
promotions, scans/gauges, notes/alerts, legacy boundaries, uPlot performance, and workstation
churn. The post-run backend/worker/research-runner log audit found no HTTP 5xx, traceback,
MissingGreenlet, UniqueViolation, CRITICAL, FATAL, Unhandled, or ERROR signatures. The initial
non-elevated launch failed before application startup at the macOS Chromium Mach-port permission
boundary; the elevated rerun is the authoritative result. No acceptance flexibility used. The
goal remains open for explicitly tracked visual-reference, provider/entitlement/taxonomy,
native-monitor, endurance, and final-audit gaps.

### 2026-08-10 post-lint-fix authoritative backend gate

The fix-first lint repair (import ordering in `instrument_mastering.py` and `instrument_sync.py`,
plus an unused test import) is validated: full-tree Ruff check passes and focused exchange-catalog,
ETF-resolution, and instrument-router regressions pass `28/28`. The unchanged Docker-backed
backend unit/integration command then passes `1,316/1,316` at `79.61%` coverage against a temporary
isolated PostgreSQL database and Redis namespace; 86 known third-party deprecation warnings only.
The temporary database was removed afterward. The repository-wide Ruff formatter check still
reports 79 pre-existing formatting diffs; the affected files' differences are unrelated expression
reflow and were not broad-reformatted. No acceptance flexibility used. The goal remains open for
visual/reference, provider/entitlement/taxonomy, native-monitor, endurance, and final-audit gaps.

### 2026-08-10 strict visual-reference audit

The stronger `visual_manifest ... --require-approved` audit fails closed at
`application-shell-default/default` because its lifecycle is `board_covered`, not exact-build
`approved`. This is the expected governance boundary, not a product/rendering failure: the normal
manifest validator and four-environment board-guided matrix remain the active acceptance track for
represented states. Acceptance flexibility used: the approved 190-image board substituted for
locally permission-cleared exact-build media; the stronger exact-build/permission gap remains
explicit and is not promoted or hidden.

### 2026-08-10 isolated Alembic round-trip

The current schema now passes an isolated `alembic upgrade head → downgrade -1 → upgrade head`
cycle on a temporary PostgreSQL database, including the current `eb1f2a3c4d5e` immutable
`code_versions.output_name` migration. The temporary database was removed after the cycle; the
branch workstation database was not touched. No acceptance flexibility used. Visual/reference,
provider/entitlement/taxonomy, native-monitor, endurance, and final completion-audit gaps remain.

### 2026-08-10 complete authenticated Chromium workflow

The complete non-visual Playwright suite now passes `78/78` in one serial Chromium worker against
the healthy branch stack. This closes the earlier incomplete unpartitioned-run observation and
covers authentication, workstation shell, factory layouts, docking/pop-outs/recovery, linking,
cross-window cursors, keyboard traversal, canonical top-down sector/industry/constituent flows,
ratios, Study Lab, unified Python promotions, EasyScan/gauges, notes/alerts, legacy compatibility,
and uPlot/workstation performance guards. A post-run audit of backend, worker, and research-runner
logs over the run window found no HTTP 500, traceback, MissingGreenlet, UniqueViolation, CRITICAL,
FATAL, Unhandled, or ERROR signatures. No acceptance flexibility used. Visual/reference,
provider/entitlement/taxonomy, native-monitor, endurance, and final completion-audit gaps remain.

### 2026-08-10 frontend regression/build and manifest gate

The current frontend suite passes `664/664` tests across 91 files. `vue-tsc --noEmit`, the Vite
production build (468 modules), the TC2000 V25 visual-manifest validator, JSON/YAML parsing, and
`git diff --check` also pass. Vitest emits only the existing intentionally exercised watchlist
conflict-path stderr. An initial command incorrectly supplied Jest's unsupported `--runInBand`
flag; the repository's actual Vitest command was then rerun unchanged and is the authoritative
result. No acceptance flexibility used. Visual/reference, provider/entitlement/taxonomy,
native-monitor, endurance, and final completion-audit gaps remain open.

### 2026-08-10 authoritative combined backend gate

The full Docker-backed backend unit/integration gate passed `1,316/1,316` at `79.61%` line
coverage, above the required 75% threshold, with 86 known third-party dependency deprecation
warnings only. The first invocation from inside the backend container produced `1,026` passing
unit tests but `290` integration fixture setup errors because Testcontainers could not access the
Docker socket; that was recorded as an execution-environment failure, not a product result. The
same suite was then rerun unchanged against an isolated temporary PostgreSQL database and Redis
namespace through the documented `TEST_DATABASE_URL`/`TEST_REDIS_URL` overrides and passed in full.
No acceptance flexibility was used. Visual/reference, provider/entitlement/taxonomy, native
monitor, endurance, and final completion-audit gaps remain open.

### 2026-08-10 bounded sandbox and runner-stress acceptance

The live branch research-runner now has fresh bounded security/recovery evidence: the sandbox
escape probe passes all eight denial cases; resource pressure passes the 768 MiB/1 CPU/128 PID/
no-network/read-only/non-root contract, cgroup kill, 64 MiB tmpfs ceiling, and eight-process
containment with restart count unchanged at `0`; orphan recovery completes after an isolated
runner restart; and the sustained queue probe passes `5/5` cancellation/success rounds with no
stale sentinels. The scripts remain hard-bounded. Acceptance flexibility used: none. This closes
the bounded sandbox/resource gate; indefinite soak and native multi-monitor validation remain
explicitly open, alongside the visual/reference/provider/taxonomy/final-audit gaps.

### 2026-08-10 isolated seeded acceptance-stack portability

Compose host bindings are now configurable through `POSTGRES_HOST_PORT`, `BACKEND_HOST_PORT`,
`FRONTEND_HOST_PORT`, and `REDIS_HOST_PORT`, preserving the existing defaults. This removes the
repository-controlled port collision that previously prevented a seeded acceptance stack from
running beside the normal branch stack. Deployment contract tests pass `8/8` with `--no-cov`, the
isolated seeded stack starts on 55432/18000/18080, and `F8e.1a` passes `1/1` against it. The
auxiliary stack was stopped without deleting volumes and the normal stack remained healthy with a
clean error-signature audit.

Acceptance flexibility used: none. This closes the fixture-environment reproducibility gap; board
guided visual interim states, exact-build/unrepresented visual states, broader provider/
entitlement/taxonomy coverage, native-monitor, endurance, and final security/runtime gaps remain.

### 2026-08-10 partitioned authenticated workflow revalidation

The previously non-terminating unpartitioned `flows.spec.ts` attempt was replaced by bounded,
serial partitions on the same healthy non-seeded branch stack. The partitions pass `3/3` for
workspace export/columns/templates, `24/24` for docking/pop-outs/linking/keyboard/freshness,
`23/23` for support tools/compatibility/legacy/performance, and `14/14` for authentication,
chart bootstrap, templates, and Study Lab state rendering. Together with the `12/12` canonical
top-down/ratio/Python gate, all selected in-scope workflow cases now have bounded passing
evidence. The old unpartitioned run remains an incomplete runner-behaviour observation, not a
product failure or a pass claim.

Acceptance flexibility used: none for these normal-stack workflow partitions. Board-guided visual
interim evidence, exact-build/unrepresented visual states, broader provider/entitlement/taxonomy
coverage, native-monitor, endurance, and final security/runtime gaps remain open.

### 2026-08-10 broad authenticated-suite follow-up

After the focused `12/12` robust-workstation gate, the full `flows.spec.ts` run was started against
the same non-seeded branch stack. It produced normal API traffic, but did not emit a completion
summary after an extended bounded wait and was interrupted rather than being treated as a pass.
The stack remained healthy and the post-run log audit found no HTTP 500, traceback, MissingGreenlet,
UniqueViolation, critical, fatal, or unhandled signatures. The focused gate remains authoritative;
the broad suite requires a partitioned rerun to identify the long-running boundary.

### 2026-08-10 authenticated robust-workstation gate advance

The focused initial robust-workstation acceptance set passed `12/12` tests. It ran against the
branch-scoped authenticated stack with
`E2E_SEED_INSTRUMENTS=false` and `E2E_SEED_MARKET_DATA=false`, so this evidence is not fixture-only.
The run covered the live/canonical SPY/RSP membership contract, labelled SPY proxy behaviour for
unavailable official SPX, all live sector industry surfaces, XLK/XLE ratio editing, deep
sector-to-industry/proxy-to-constituent drill-down with NVDA ratios, the positive-close Study Lab
factory study, and Python Study Lab promotion into a watchlist column, EasyScan/alert, and chart
plot. The formerly fixture-only exhaustive-sector test now runs against canonical data as well and
passes; its controlled-fixture counterpart could not be started concurrently because the normal
stack owns host port 5432, so that separate environment remains an infrastructure rerun item.

Acceptance flexibility used: none for the executed live gate. The board-guided visual track,
unrepresented V25 states, official exact-build/permission evidence, native physical monitor,
bounded endurance, broader provider/entitlement/taxonomy coverage, and final security/runtime
audit gaps remain explicitly open.

## Current continuation checkpoint — 2026-08-10T01:25:00Z

The complete board-guided visual matrix now passes `96/96` without snapshot-update mode across
1920x1080 and 2560x1440 at 100% and 125% display scale. The baselines were regenerated once from
a fresh controlled fixture after reviewing the default workstation render and correcting the
duplicate uPlot ratio legend; the stable rerun then passed without regeneration. Core overlap,
containment, interaction, loading/freshness, pop-out, chart, and Study Lab oracles all pass.

Acceptance flexibility used: the approved 190-image board and controlled fixture were used for
represented/interim states, as authorised by the governance ledger. No screenshot mask, diff
threshold, product boundary, or exact-build claim was changed. The 96/96 result is not exact-build
approval: `REF-SHELL-V25`, `REF-STATE-VARIANTS`, `REF-LINKING-V25`, `REF-STUDY-LAB-V25`,
`REF-ENV-TOKENS`, and `REF-PERMISSION-REVIEW` remain actionable where the board is incomplete or
the evidence is not pinned-build/permission-cleared. Live provider/entitlement, taxonomy,
multi-monitor, endurance, security, and final backend gaps remain open.

The default-shell visual oracle was then rerun against the retained seeded fixture after adding an
explicit ratio-warning containment check and visible duplicate-uPlot-legend check; it passes 1/1.

## Current continuation checkpoint — 2026-08-10T01:06:00Z

The board-guided visual comparison exposed and closed a compact-window defect: `RatioUPlot` was
allowing uPlot's default HTML legend to render below the canvas in addition to the workstation
legend, colliding with the warning/footer row. The uPlot legend is now explicitly disabled, and a
unit regression asserts the option remains disabled. The focused top-down/ratio/crosshair browser
suite passes 6/6 with one intentional seeded-only skip; the overlap oracle passes before the
remaining expected-content screenshot comparison.

Frontend Vitest is now 664/664, type-check and production build remain green. The prior visual
baseline result remains unchanged: the fresh deterministic board project passed 10/24 at
1920x1080/100%, and its 14 content/baseline differences remain tracked rather than refreshed.
Acceptance flexibility used: board-guided and controlled-fixture evidence only; no visual
threshold, mask, snapshot, or product criterion was relaxed. Remaining visual, exact-build,
unrepresented-state, live-provider, taxonomy, multi-monitor, endurance, and final-audit gaps stay
open.

## Current continuation checkpoint — 2026-08-10T00:59:00Z

The product focus remains the TC2000 Version 25 workstation. ETF/provider work is supporting
infrastructure for canonical top-down data and is not a reprioritisation away from the UI.
Four frontend race defects were fixed and verified: initial workspace hydration could overwrite an
early Add-tool action; stale Golden Layout activation callbacks could target detached headers
(`HSACI56632`); the Python autocomplete panel could intercept Code Library actions; and the initial
screener list load could overwrite a newly created screener. Focused reproductions pass 6/6 for
Python/Study Lab tool opening and 3/3 for screener creation. The complete functional flow file now
passes 74/74 executed tests with one intentional seeded-only skip.

Frontend Vitest passes 663/663, TypeScript and production build pass, and the authoritative backend
gate passes 1,316/1,316 at 79.59%. The visual manifest validates. The first board run accidentally
used a live-data backend while seeded assertions were enabled; it was discarded. A fresh isolated
seeded Compose project then produced 10/24 passes for the 1920x1080/100% visual project. The
remaining 14 failures are preserved as visual-baseline/geometry gaps; no snapshot, mask, threshold,
or exact-build claim was changed. The existing branch stack and data volume were restored after the
fixture run.

Acceptance flexibility used: only the already-approved board-guided policy and controlled seeded
fixture were used for visual states; the localized code fixes themselves used no relaxed criterion.
Open gaps are exact-build/permission-cleared measurement evidence, stale local visual baselines,
unrepresented V25 states, complete live-provider/entitlement coverage, broader taxonomy and
point-in-time holdings, native multi-monitor and endurance evidence, and the remaining final
security/performance/runtime audit. These remain tracked and are not being silently ignored.

## Current continuation checkpoint — 2026-08-09T22:44:50Z

The TC2000 workstation remains the primary objective. Supporting provider work delivered an
issuer-native iShares SOXX snapshot (34 rows, 32 resolved, 2026-08-07) and EDGAR classification
enrichment for 27/29 available constituents. The reviewed semiconductor classification alias is
explicitly scoped to the verified proxy mapping; it is not a general name-based taxonomy rule.

The non-seeded market-groups API now suppresses controlled fixture proxy rows, and selecting an
industry proxy keeps the sector taxonomy context intact. Virtualized watchlist rows no longer
detach during value-only refreshes. Authenticated real-data validation now covers all 11 sectors
and repeated sector → industry/proxy → constituent drilldown with `NVDA/<proxy>` and `NVDA/SPY`
ratios. Evidence: focused F8d/F8e 7/7 with one intentional seeded-only skip, backend 1,316/1,316
at 79.59%, frontend 663/663, type-check/build pass. Acceptance flexibility used: none.

This does not make the branch complete. The next work remains the broader TC2000 workstation
acceptance matrix: full board-guided visual states, remaining V25 mechanics, canonical coverage
and entitlements (including official SPX/RSP limitations), additional industry/proxy mappings,
Python/Study Lab end-to-end promotion, multi-monitor/endurance evidence, and final runtime/log
audits. ETF provider work is supporting infrastructure for those paths, not a change in product
priority.

## Current continuation checkpoint — 2026-08-09T22:13:51Z

The real-data top-down path advanced from provider setup into canonical holdings and
authenticated workstation validation. Official State Street SPDR workbooks now persist
canonical snapshots for SPY, DIA, and all 11 Select Sector SPDR ETFs (latest composition
2026-08-06); SPY is 505/505 resolved, DIA is 31/31, and the sector snapshots are official
SPDR-provenance rows. RSP's public Invesco route returned HTTP 500, so it was not claimed;
SEC N-PORT reconstruction supplies a labelled fallback snapshot (2026-04-30, 508/508
resolved, `sec_nport_reconstructed_holdings`). The parser and bounded-ingestion defects found
during this work were fixed rather than bypassed: legal/disclaimer rows are excluded and
optional per-row provider enrichment is disabled inside bounded issuer/SEC transactions.

Validation now includes the focused resolver/parser tests (2/2), the authenticated real
membership check, 6/6 focused F8d/F8e browser checks with one intentional skip, 1,314/1,314
backend unit/integration tests at 79.59% coverage, 662/662 frontend tests, TypeScript, the
production build, YAML/JSON parsing, and `git diff --check`. No acceptance flexibility was
used. Docker log inspection was unavailable from the restricted shell and is retained as an
environmental evidence gap; the earlier rebuilt-stack browser log audit was clean.

This remains supporting infrastructure for the TC2000 workstation, not a reprioritisation
away from it. The next work is the first robust live `US Top Down` gate through the actual UI:
canonical sector/constituent drilldown, verified industry/proxy mappings, ratios and breadth
in the authenticated workstation, followed by the remaining V25 interaction, visual,
provider-entitlement, sandbox, performance, and completion checks. The official SPDR path is
now closed for this bounded advance; RSP's Invesco-native route and broader provider coverage
remain explicitly open.

## Current continuation checkpoint — 2026-08-09T21:47:16Z

The TC2000 workstation remains the primary product objective. The board-guided authenticated
workstation mechanics are substantially exercised, and the canonical Nasdaq EOD path now powers
the core SPY/RSP/sector/NVDA price and ratio calculations. A bounded attempt was made to promote
the verified State Street SPDR daily-workbook route into canonical holdings for SPY, DIA, and the
11 Select Sector SPDR ETFs. The active container could not resolve the issuer host, the attempt
timed out without committing a snapshot, and no fixture holdings were relabelled. This is an
external live-evidence gap, not a product success or a goal blocker. The next product focus is
the first robust real-data workstation gate: canonical holdings/constituent drilldown, verified
industry/proxy mappings, and the authenticated UI path. Provider route work remains supporting
infrastructure only.

**Acceptance flexibility used:** None. The official route was not treated as live evidence because
the environment could not resolve it. The open gap is tracked until an authorised live probe and
canonical snapshot promotion succeed.

## Current continuation checkpoint — 2026-08-09T21:35:00Z

Added and exercised the free-source Nasdaq public historical adapter as the first canonical
provider-backed EOD path for the workstation's core US universe. It supports D1 split-adjusted
price/volume only (no intraday or total-return claims), is registered in the provider chain, and
uses bounded paging plus a short response cache. Direct probes returned 652 rows through
2026-08-07 for SPY, RSP, XLK, XLE, and NVDA. Durable bulk ingestion then persisted 3,034 rows
through 2026-08-07 for SPY/RSP/QQQ/DIA/IWM, all 11 sector ETFs, and NVDA; the obsolete E2E
fixture rows for only those 17 core symbols were removed rather than relabelled. Direct canonical
analysis now returns full-overlap `XLK/SPY`, `XLK/XLE`, `NVDA/XLK`, and `NVDA/SPY` ratios,
11/11 sector rotation rows, 11/11 breadth coverage, and an 11/11 sector snapshot with SPY
relative performance. The focused analysis/provider suite passes `35/35`, including the Nasdaq and
registry tests,
Ruff and `git diff --check` pass. A fix-first repair hardening skips zero-width exchange-calendar
gaps and tolerates only typed provider-availability failures when cached bars exist; cold loads
and unexpected errors still fail. No acceptance criterion was relaxed. The application database
now has truthful Nasdaq provenance for this core market path, while holdings, industry/proxy
coverage, broader constituent universe, live-entitlement evidence, and the full authenticated
workstation gate remain open. The next focus is to expose and validate this provider-backed data
through the rebuilt authenticated UI, not to expand peripheral provider coverage. The authenticated
top-down browser checks now pass `5/5` with one intentional skip against this real-data state. That
run exposed a missing-volume 500 in shared technical/group analysis; it now returns a structured
`missing_volume` cell/warning and the fresh full backend gate passes `1,313/1,313` with 358 live
tests skipped. The post-run log audit is clean.

## Current continuation checkpoint — 2026-08-09T20:36:07Z

Promoted Range ETFs' official product-page holdings payload into a native, symbol-scoped route
for NUKZ and COAL. The adapter parses the complete dated Nuxt holdings component, preserves
ticker/FIGI/shares/market-value/weight fields, classifies cash rows, and retains the issuer
composition/as-of date. Deterministic route and registry checks pass `2/2`; both opt-in live
official routes pass `2/2`; all `461/461` ETF adapter test bodies pass (the focused single-file
command exits only on its repository coverage threshold because it measures 51.36% in isolation);
the authoritative fresh-database backend gate passes `1,305/1,305` with `358` live tests skipped
at `79.58%` coverage. Registry state is `496` registered, `347` native/live-backed, and `149`
audited fallback-only. The first broad run exposed a missing SEC-fallback probe invariant for the
new adapter; that localized defect was fixed and the complete gate rerun. No acceptance criterion
was relaxed. Python compilation and `git diff --check` pass; Ruff remains unavailable in the image.
This is supporting data infrastructure for the TC2000 top-down workflow, not a reprioritization
away from the workstation. The next focus is the first robust live-data workstation gate and its
remaining UI/interaction/data-integrity gaps; provider coverage, visual-reference, native-monitor,
endurance, and other full-goal gaps remain open.

## Current continuation checkpoint — 2026-08-09T20:15:22Z

Promoted Oakmark's official symbol-scoped ETF holdings exports to a native route for OAKM and
OAKI. The issuer CSVs were verified as complete portfolios with ticker, CUSIP/SEDOL/ISIN, shares,
market value, weight, fund identifier, and as-of date; the adapter filters the requested fund and
preserves dated provenance, including two-digit issuer dates. Both opt-in live routes pass `2/2`,
focused Oakmark/registry tests pass `2/2`, the complete ETF adapter suite passes `460/460`, and
the isolated Docker backend gate passes `1,304/1,304` with `356` intentionally skipped live tests
at `79.56%` coverage. Registry state is now `496` registered, `346` native/live-backed, and `150`
audited fallback-only. A first adapter run exposed the existing reconciliation-batch invariant;
Oakmark was added to the native batch and the full suite was rerun successfully. No acceptance
criterion was relaxed. Ruff remains unavailable in the backend image; compilation and
`git diff --check` pass. This is supporting real-data infrastructure for the TC2000 top-down
workflow; remaining provider/live, visual/reference, native-monitor, endurance, and product gaps
remain open.

## Current continuation checkpoint — 2026-08-09T20:01:49Z

Promoted ACSI Funds' official daily holdings CSV into a native, symbol-scoped adapter for the
top-down constituent workflow. The public issuer route was verified over HTTPS and the opt-in
live parser test passed `1/1`; the deterministic route/provenance and fallback-classification
tests passed `2/2`, the complete ETF adapter suite passed `459/459`, and the isolated Docker
backend gate passed `1,303/1,303` with `354` intentionally skipped live tests at `79.56%`
coverage. The adapter preserves the issuer-provided composition/as-of date when the CSV is
consistent and leaves a warning when multiple dates are present. Registry state is now `496`
registered, `345` native/live-backed, and `151` audited fallback-only. The first broad run was
rejected by the shared application's stale schema during fixture teardown; rerunning against a
fresh temporary database passed, and that database was removed afterward. The container has no
Ruff executable, so lint remains an environment limitation rather than a claimed pass; Python
compilation and `git diff --check` pass. No product-scope or acceptance criterion was relaxed.
The TC2000 workstation remains the primary goal; this is supporting real-data infrastructure for
its sector/industry/constituent drilldown. Live coverage for the other fallback-only issuers,
board/reference gaps, native monitor behavior, endurance, and remaining workstation/backend
requirements remain open.

## Current continuation checkpoint — 2026-08-09T19:40:12Z

The rebuilt authenticated workstation flow matrix passes `73/73` in one serial run. It covers
authentication and legacy boundaries, factory layouts, chart/template/drawing mechanics, Python
reuse through columns/EasyScan/alerts/plots, pop-outs and cross-window symbols/timeframes/cursors,
link groups, freshness/error/recovery states, SPY/RSP and XLK/XLE ratios, all seeded sector
industry drilldowns, Study Lab scalar/structured/factory/promotion flows, notes, watchlist
copy/move, Market Gauges, alerts, unsupported-domain hiding, 125% containment, and Radar. This
is functional acceptance evidence with controlled seeded data where stated; no visual threshold,
mask, or product criterion changed. The clean `96/96` visual matrix remains current. The full
goal is still open for real free-source top-down population, provider/live evidence, exact or
unrepresented visual proof, native monitor behavior, endurance, and any remaining requirement-
level backend/product gap.

## Current continuation checkpoint — 2026-08-09T19:30:37Z

The repaired workstation now passes the complete board-guided visual matrix: `96/96` across
1920x1080 and 2560x1440 at 100% and 125% display scale. This is one clean run after the
Golden Layout drag-target header-race fix and the bounded persisted-reset synchronization fix;
no screenshot threshold, mask, or product acceptance criterion changed. Post-matrix type-check,
production build, service-log audit, manifest validation, 190-image board validation, and diff
checks pass. Board/local interim evidence and controlled seeded data remain explicitly in use.
This closes the recent visual-oracle repair loop, not the overall product goal: real free-source
top-down data population, remaining functional/chart/linking acceptance, Python/Study Lab depth,
provider/live evidence, native monitor behavior, endurance, and exact/unrepresented visual gaps
remain active.

## Current continuation checkpoint — 2026-08-09T19:10:21Z

Closed and verified the board-covered `workspace-docking/drag_target` interaction gap and a
matrix-only reset synchronization defect. The first full four-environment run exposed a
localized Golden Layout `HSACI56632` header race while a dragged component temporarily had no
owning header; `WorkspaceLayoutHost` now checks header ownership before reasserting active state,
with a focused regression passing `7/7`. Drag-target visual coverage passes `4/4` after a rebuilt
stack and the affected 2560x1440/100% project passes `24/24`. The preceding matrix completed
`95/96`; its one failure reproduced in isolation and was closed by extending the reset-status
oracle to a bounded 15-second persisted-workspace wait. No visual threshold, mask, or product
criterion changed. Frontend Vitest passes `662/662`, type-check/build pass, and the recent
service-log audit is clean. Board/local interim evidence and controlled seeded data were used;
these states remain locally measured against the composite board and not exact-build-approved.
Exact/unrepresented references, provider/live coverage, native monitor placement, bounded
endurance, and remaining workstation/chart/linking gaps remain open.

## Current continuation checkpoint — 2026-08-09T18:38:06Z

Closed the board-covered `workspace-docking/floating` visual gap with a popup-level oracle. The
browser floats a real source ToolWindow, asserts the visible pop-out, captures the popup
composition, closes it through the user-facing control, and verifies the source tool remains
docked. Snapshot generation and no-update verification pass `4/4`; the complete four-environment
board-guided visual matrix passes `92/92`; frontend Vitest remains `661/661`; type-check/build,
board/manifest validators, service-log audit, and `git diff --check` pass. Acceptance flexibility
used: browser pop-out plus board/local interim evidence; no threshold or mask changed. Tabbed,
maximized, restored, and floating states now have measured local baselines but remain subject to
the broader reference, environment, and permission gaps. Drag-target and remaining chart/link,
provider/live, native-monitor, and endurance gaps remain open.

## Current continuation checkpoint — 2026-08-09T18:17:23Z

Closed the paired board-covered `workspace-docking/restored` visual gap. The browser now
maximizes a real ToolWindow, invokes its restore control, asserts that Golden Layout leaves the
maximized state, and captures the restored composition. Snapshot generation and no-update
verification pass `4/4`; the complete four-environment board-guided visual matrix passes
`88/88`; frontend Vitest remains `661/661`; type-check/build, board/manifest validators,
service-log audit, and `git diff --check` pass. Acceptance flexibility used: board/local interim
evidence for the composite-board track; no threshold or mask changed. Tabbed, maximized, and
restored states now have measured local baselines but remain subject to the broader reference,
environment, and permission gaps. Floating/drag-target states, provider/live, native-monitor,
and endurance gaps remain open.

## Current continuation checkpoint — 2026-08-09T18:04:19Z

Closed the adjacent board-covered `workspace-docking/tabbed` visual gap. The browser now
asserts that the real Golden Layout stack exposes multiple tabs, activates a non-default tab,
and captures the resulting composition. Snapshot generation and no-update verification pass
`4/4`; the complete four-environment board-guided visual matrix passes `84/84`; frontend Vitest
remains `661/661`; type-check/build, board/manifest validators, service-log audit, and
`git diff --check` pass. Acceptance flexibility used: board/local interim evidence for the
composite-board track; no threshold or mask changed. Tabbed and maximized states now have local
measured baselines but remain subject to the broader reference/permission/environment gaps.
Remaining workspace/chart/link states, provider/live, native-monitor, and endurance gaps remain
open.

## Current continuation checkpoint — 2026-08-09T17:48:52Z

Closed the next shared workstation visual-acceptance gap: the board-covered
`workspace-docking/maximized` state now has a real browser interaction oracle and four
deterministic local baselines. The test opens a ToolWindow menu, invokes Maximize, asserts the
Golden Layout maximized state, and captures the resulting workstation composition. Snapshot
generation and no-update verification both pass `4/4`; the complete four-environment
board-guided visual matrix passes `80/80`; frontend Vitest passes `661/661`; type-check,
production build, board/manifest validators, service-log audit, and `git diff --check` pass.
Acceptance flexibility used: board/local interim evidence for the composite-board track; no
threshold or mask changed. The state is now measured locally but remains subject to the broader
`REF-STATE-VARIANTS`, `REF-ENV-TOKENS`, and `REF-PERMISSION-REVIEW` evidence gaps. Provider/live,
native-monitor, endurance, and the remaining workspace/chart/linking state coverage remain open.

## Current continuation checkpoint — 2026-08-09T17:32:34Z

Closed a shared tool-window chrome defect: each ToolWindow now dismisses its three-dot menu on
outside pointer input at document-capture level, while clicks inside the menu remain actionable
and unmount removes the listener. Added unit coverage and extended F8i with a real outside-click
assertion. Focused ToolWindow coverage passes `4/4`; full frontend Vitest passes `661/661`; the
rebuilt authenticated Chromium matrix passes `73/73`; focused F8i passes `1/1`; the complete
four-environment board-guided visual matrix passes `76/76`; the new `tool_menu_open` visual gap
has four deterministic local baselines; the 190-image board validator, manifest validator,
type-check, build, ops parsing, and diff checks pass. Acceptance flexibility used: the board/local
interim track for the newly unrepresented tool-menu state under `REF-STATE-VARIANTS`; it remains
`required_missing` and is not exact-build approval. No threshold or mask changed. Provider/live,
native-monitor, endurance, and other reference gaps remain explicit.

## Current continuation checkpoint — 2026-08-09T17:04:53Z

Closed a shell interaction-parity defect: workstation transient menus are now mutually
exclusive. Opening Workspace, Add tool, Help, or Recent symbols closes the other shell popovers
and any stale symbol listbox, while the search wrapper retains ownership of its own editor/history
surface. Outside pointer input and Escape continue to dismiss all transient menus. Added a unit
regression covering Workspace → Add tool → Help transitions and retained the browser F8k-help
coverage for the real-user path. Focused shell coverage passes `14/14`, the rebuilt authenticated
Chromium matrix passes `73/73`, focused keyboard-help visual coverage passes `4/4`, full frontend
Vitest passes `660/660`, `vue-tsc --noEmit`, production build, and `git diff --check` pass. The
post-matrix service-log audit has no unhandled error signatures; expected provider-freshness
warnings remain explicit. No visual threshold, mask, or product criterion changed. This is a
localized repository-controlled
TC2000 shell correction; the board/reference, live/free-source, native-monitor, and endurance
gaps remain explicit and the active goal continues.

## Current continuation checkpoint — 2026-08-09T16:58:25Z

Added the new shell Help state to the visual gap ledger and closed a board-guided oracle race
exposed by the full matrix. `keyboard_help` now has a named `required_missing` manifest state,
an interim shortcut-content/focus oracle, and deterministic local baselines in all four required
display environments. The Study Lab original-surface visual case now freezes its adjacent chart
and research-list loading states and resets factory geometry before capture; only its four
affected interim baselines were regenerated after review. Focused keyboard-help visual coverage
passes `4/4`, focused Study Lab coverage passes `4/4`, and the complete board-guided matrix passes
`72/72`. The reference-board validator confirms all 190 source images. Acceptance flexibility
used: board/state-variant interim evidence and controlled seeded data; no threshold or mask changed,
and `REF-SHELL-V25`, `REF-STATE-VARIANTS`, `REF-STUDY-LAB-V25`, `REF-ENV-TOKENS`, and
`REF-PERMISSION-REVIEW` remain open where applicable.

## Current continuation checkpoint — 2026-08-09T16:39:54Z

Closed a core shell discoverability and focus-boundary gap. The workstation now exposes a
TC2000-style Help menu with the implemented global keyboard contract, and `F1`/`?` opens the
same surface when shell focus owns the event. Moving focus into the Active symbol editor
dismisses the global menu and retains editor ownership of `F1`/`Space`; the focused browser flow
passes `1/1`, the complete rebuilt authenticated Chromium matrix passes `72/72` from 73
collected tests with one intentional skip, frontend Vitest passes `660/660`, and the rebuilt
frontend production image/type-check passes. The first focused browser attempt used a stale
frontend image; after the correct branch-scoped rebuild it exposed and closed the localized
focus-dismissal defect. Acceptance flexibility used: controlled seeded market data for browser
validation only; no visual threshold, mask, or product criterion changed. Visual/provider,
hardware, endurance, and other unrepresented-state gaps remain explicitly tracked.

## Current continuation checkpoint — 2026-08-09T16:23:30Z

Closed a core workstation keyboard-acceptance gap. The required real-user reverse traversal
(`Shift+Space`) now has a dedicated browser regression alongside the editor-focus guard: the
workstation traverses backward when the shell owns focus, while a focused symbol editor receives
the literal space and does not publish a new symbol. The focused flow passes `1/1`, and the full
rebuilt authenticated Chromium matrix passes `71/71` (72 collected, one intentional skip).
Frontend Vitest remains `660/660`; type-check and production build pass. Acceptance flexibility
used: controlled seeded market data for browser validation; no visual threshold, mask, or product
criterion changed. This closes a repository-controlled keyboard evidence gap; visual/provider,
hardware, and endurance gaps remain tracked.

## Current continuation checkpoint — 2026-08-09T16:05:08Z

Closed a provider-governance inconsistency exposed during the goal audit. Anfield/ADFI was
still classified as native/live-backed even though its configured Regents Park product route
returns HTTP 404 and no replacement executable first-party route has been verified. Anfield now
remains a custom isolated adapter with conditional SEC fallback, but is explicitly audited
fallback-only (`issuer_access_blocked`) until a complete issuer-owned route is re-established.
The live-provider registry no longer requires a false native success test. Current source-state
counts are 496 registered, 344 native/live-backed, and 152 audited fallback-only. Acceptance
flexibility used: none; this is a provenance/entitlement correction, not a relaxation. The
provider gap remains separate from the TC2000 workstation completion bar.

## Current continuation checkpoint — 2026-08-09T22:10:00Z

The complete board-guided visual run caught and closed a real acceptance-harness race in the
blocked-popout state. The test was taking its screenshot before canonical market hydration had
settled, so the 1080p/100 environment captured a ready workstation against a loading/unavailable
baseline while other environments happened to take the opposite path. The test now uses the
shared shell/chart readiness guard before and after the blocked action. The four affected
interim baselines were regenerated after review; focused coverage passes `4/4` and the complete
four-environment matrix passes `68/68`. Acceptance flexibility used: board-guided local
baselines and controlled seeded data; no threshold or mask changed. `REF-STATE-VARIANTS` remains
required_missing because authoritative V25 blocked-popout styling is still unavailable. This is
an acceptance-oracle repair, not a product-scope reduction.

The same continuation found 5.07 GB of reclaimable Docker build cache. A targeted
`docker builder prune -af` completed and verified zero build cache; the broader system-wide prune
was rejected by the safety boundary and not bypassed, preserving active images, containers, and
volumes.

## Current continuation checkpoint — 2026-08-09T21:30:00Z

The workstation watchlist membership workflow was hardened after reviewing the actual failure
semantics: “Move to list” previously issued independent add and delete requests, so a failed
delete could leave a symbol in both lists. The new canonical transfer endpoint performs copy or
move atomically, preserves flags/notes, enforces ownership/editability/duplicate/mode rules,
and updates both client memberships from one response. Backend focused tests pass `19/19`;
Ruff, frontend focused store tests `18/18`, full backend `1301/1301` at `79.50%`, frontend
Vitest `660/660`, type-check, and production build pass. The initial rebuilt-stack browser run
found a real stale-image `405`; a forced no-cache backend/worker rebuild was verified in the
running container and corrected the deployment validation. F8y passes `1/1`, the complete
authenticated Chromium matrix passes `71/71`, and runtime logs are clean. Acceptance flexibility
used: controlled seeded data for browser validation only; no visual threshold/mask/product
criterion changed. Exact/unrepresented board states, live/free-source provider breadth and
entitlements, native physical multi-monitor validation, and indefinite endurance remain explicit
gaps. This repair strengthens the TC2000 workstation’s list mechanics; ETF/provider work remains
supporting infrastructure for its top-down market workflow.

## Current continuation checkpoint — 2026-08-09T15:30:00Z

The strict board-guided visual matrix was rerun after the workspace replacement repair and passes
`68/68` across 1920×1080 and 2560×1440 at both 100% and 125% display scale. Acceptance flexibility
used: the 190-image board/local deterministic baselines and controlled seeded data for states
without live-provider evidence. No mask, threshold, or exact-build claim changed; the six
reference-gap IDs remain explicitly tracked.

The full authenticated matrix exposed and then closed a localized F9d-to-F9e workspace
replacement race. Import/factory reset replaced persisted window objects while Golden Layout
retained virtual Vue roots bound to the old objects, allowing column grouping/stacking edits to
disappear from the visible header. Imports/resets now withdraw the dock while the asynchronous
replacement is pending and use a reload token to recreate roots after the new snapshot is
installed; ordinary tool configuration edits remain in-place. Host lifecycle coverage passes
`6/6`, the reproduced sequence passes `10/10` across five repetitions, the rebuilt authenticated
matrix passes `71/71`, Vitest `659/659`, and type/build/compile/diff/ops/log checks pass.
Acceptance flexibility used: controlled seeded data only; no visual threshold or mask changed.
Exact/unrepresented visual and live-provider gaps remain explicit.

Live branch-stack research-runner probes were revalidated: namespace/mount/setns/unshare,
ptrace, fork, network, subprocess, and root-write attempts were denied; the deployed limits are
768 MiB memory, one CPU, 128 PIDs, no network, read-only root, and non-root UID 10001. The
2 GiB cgroup kill, tmpfs cap, concurrent-pressure containment, orphan recovery, and five
cancellation/success rounds all passed without stale sentinels. Acceptance flexibility used:
bounded stress instead of indefinite soak only; the security/resource/recovery checks used no
substitution. Indefinite operational endurance remains open.

Current-branch scale guards were revalidated after the bounded workstation run: real packaged
uPlot Chromium rendered 100,000 points and completed 40 zoom/pan updates without replacing the
chart element (`1/1`), while the focused virtual-watchlist suite passed `52/52` for the 10,000-row
DOM bound and wide-column virtualization/alignment. Acceptance flexibility used: `None` for these
direct checks. Physical multi-monitor behavior and longer-duration endurance remain open external
gates.

The workstation performance guards were revalidated with elevated Chromium permission after a
sandboxed browser launch failed before application startup. Chart-window initialization/recovery
and repeated pop-out cleanup pass with a 100-round churn budget in 2.1 minutes; canvas/tool counts
remain bounded and browser diagnostics are clean. Acceptance flexibility used: bounded stress in
place of indefinite soak and browser pop-outs in place of physical multi-monitor validation.
Long-duration endurance and native monitor placement remain explicit gaps; this evidence does not
close them.

The fix-first tie-break was exercised on the intermittent F8y Golden Layout race rather than
blocking the goal: stale virtual-root watchlist creates could replay an older name or selection.
Creation now reads the live/latest draft intent, deduplicates duplicate-root requests, and keeps
the newest created list selected until its workspace snapshot is acknowledged. Focused F8y passes
`5/5`; the complete rebuilt authenticated Chromium matrix passes `71/71`. Frontend Vitest is
`658/658` across 91 files, type-check/build, compileall, manifest, diff, and status-aware backend
log checks pass. No visual threshold, mask, or acceptance criterion was relaxed. Remaining gaps
are unchanged and explicit: exact/unrepresented V25 states, official/live-free-source breadth and
entitlements, native physical multi-monitor validation, and long-duration endurance.

The rebuilt board-guided visual matrix was then rerun with `RUN_BOARD_VISUAL_PARITY=1` across
all four configured environments and passed `68/68`. This uses the documented board/local-baseline
flexibility for represented and genuinely unrepresented states; `REF-SHELL-V25`,
`REF-STATE-VARIANTS`, `REF-LINKING-V25`, `REF-STUDY-LAB-V25`, `REF-ENV-TOKENS`, and
`REF-PERMISSION-REVIEW` remain explicitly tracked where their evidence is incomplete.

## Current continuation checkpoint — 2026-08-09T13:45:00Z

The supporting canonical security-master path now resolves known provider venue labels to
canonical US MIC exchanges and persists distinct same-ticker listings per venue instead of
silently conflating them. `exchange_catalog` unit coverage passes `9/9`; provider persistence
and new-provider coverage passes `86/86`; the authoritative Docker-backed backend suite passes
`1,291/1,291` with `362` skipped under `--no-cov`; and the final rebuilt-stack authenticated
Chromium matrix passes `71/71` after the RatioUPlot optimistic comparison-leg repair. Frontend
Vitest remains `658/658` across 91 files, `vue-tsc`, production build, compileall, manifest,
diff, and status-aware backend-log checks pass. This is enabling infrastructure for the
TC2000 top-down workflow, not a shift away from the workstation product.

The ratio editor was validated against a freshly rebuilt frontend image: focused F8e.2 passed
`5/5`, and the complete matrix passed `71/71`. The product now keeps a local comparison-leg
state while debounced Golden Layout persistence catches up, preventing a user-entered `XLE`
leg from disappearing. No visual threshold, mask, or acceptance criterion was relaxed.
Flexibility used remains explicit: controlled fixture data, board-guided local baselines for
unrepresented states, browser pop-outs as the multi-monitor proxy, and bounded rather than
long-duration endurance checks. Exact-build/unrepresented visual states, official/live-free-
source population and entitlement evidence, native physical multi-monitor validation, and
long-duration endurance remain open gaps.

## Current continuation checkpoint — 2026-08-09T12:45:00Z

The rebuilt authenticated acceptance matrix now passes `71/71` Chromium flows after closing
three repository-controlled workstation interaction defects: wide-column auto-reveal and
stack placement, immediate visibility for newly promoted Python/condition columns, and stale
personal-watchlist name drafts being overwritten by delayed Golden Layout snapshots. The full
frontend suite passes `658/658` across 91 files, `vue-tsc --noEmit`, production build,
manifest validation, Python compilation, `git diff --check`, and the post-run backend log audit
are clean. The visible-cell click coordinates used by the wide-canvas Playwright assertions are
deterministic interaction-test stabilization only; no visual threshold, mask, or acceptance
criterion was relaxed. Controlled all-sector fixture, exact/unrepresented visual states,
live/free-source breadth, physical multi-monitor behavior, and long-duration endurance remain
tracked gaps.

The board-guided visual suite was then rerun with the refreshed deterministic fixture baselines
after review of representative 100% and 125% captures. The strict rerun passes `68/68` across
1920×1080 and 2560×1440 at both display scales. This is a baseline refresh for the controlled
fixture's current/complete freshness and numeric observations, not a threshold or mask change;
the online TC2000 reference board and exact-build gaps remain unchanged.

## Current continuation checkpoint — 2026-08-09T13:12:00Z

The seeded all-sector browser traversal exposed a real linked-symbol hydration defect: concurrent
instrument requests could both create the one-to-one `instrument_stats` row and return HTTP 500 on
the unique constraint. The backend now serializes 52-week stats persistence per instrument inside
each worker and recovers the winning row when another worker wins the insert. A concurrent unit
regression passes; the rebuilt seeded traversal passes `1/1` with no critical browser diagnostics,
and recent backend logs contain no 500s or integrity failures. The complete Docker-backed backend
suite passes `1,282/1,282` with `362` skipped under `--no-cov`; frontend Vitest remains `658/658`,
type-check/build pass. This closes a repository-controlled concurrency defect only. The controlled
all-sector fixture is still interim evidence, not official/live membership evidence, and exact or
unrepresented visual states, live/free-source breadth, physical multi-monitor behavior, and
long-duration endurance remain tracked gaps.

## Current continuation checkpoint — 2026-08-09T12:55:00Z

Expanded the controlled top-down acceptance fixture from Technology-only holdings to all 11
S&P 500 Select Sector ETF proxies. Each sector now has deterministic representative holdings,
classified industries, adjusted OHLCV, point-in-time holdings snapshots, and provenance-labelled
analysis inputs. Added fixture invariants and a seeded Playwright traversal that visits every sector
and requires an industry surface. Focused backend top-down/fixture coverage passes `16/16`, the
Playwright suite now lists 71 tests, frontend Vitest remains `658/658`, and type-check/build/diff
checks pass. This strengthens controlled workflow evidence; it does not claim official index
membership or live provider coverage, which remain explicitly tracked gaps.

## Current continuation checkpoint — 2026-08-09T12:50:00Z

Closed a concrete workstation scalability gap: `VirtualWatchlistTool` now virtualizes both
rows and columns when a list exceeds the dense-column threshold. The header remains horizontally
aligned with the virtualized row canvas, while normal Version 25-sized lists retain the existing
CSS-grid path. A 100-column DOM/width regression and scroll-alignment regression pass; the full
frontend suite is `658/658`, `vue-tsc --noEmit`, and the production build pass. This is a product
implementation change, not a provider-data substitution. It does not close the separately tracked
live/free-source population, exact/unrepresented visual-reference, physical multi-monitor, or
long-duration endurance gaps.

## Current continuation checkpoint — 2026-08-09T14:00:00Z

Strengthened the visual acceptance guard rather than allowing unrepresented states to be tracked
only by prose: every `required_missing` manifest state now must declare at least one unique local
deterministic baseline for each of the four required display environments, in addition to its
interim oracle. The manifest validator regression suite passes `10/10`, and the checked-in
manifest validates. This does not promote any state to exact-build approval; the board-guided
visual track, live/free-source coverage, physical multi-monitor, and endurance gaps remain
explicitly open.

The complete authenticated Chromium matrix was then rerun against the healthy branch stack and
passed `85/85` in `11.3m` with one worker; the post-run service-log audit is clean for the audited
runtime-error signatures. This broad regression evidence closes validation for the shared renderer
change but does not close the separately tracked visual/provider/hardware/endurance/final-audit
gaps. No acceptance flexibility was used.

## Current continuation checkpoint — 2026-08-09T12:25:00Z

The remaining Study Lab/Python failures were fixed in the product path. `ChartPlotLibrary` now
uses the exact `update:python-plots` event contract and an optimistic serializable plot list, so a
newly saved Study Lab series appears immediately in the chart plot library. Workspace conflict
reconciliation now merges additive locally opened tools by stable instance key while retaining
recovery for explicit removals and identity/settings/membership conflicts. Component/store
regressions pass `60/60` and `43/43`; focused Python/Study Lab acceptance passes `5/5`; frontend
Vitest passes `656/656` across 91 files; type-check/build/backend compile/diff checks pass.

After rebuilding the branch stack, authenticated Chromium passes `70/70`, board-guided visual
parity passes `68/68` across all four required display environments, and the complete Docker-backed
backend gate passes `1,285/1,285` at `79.47%` (workspace integration `24/24`). Flexibility is explicit and bounded: deterministic
additive-race tie-break, controlled seeded market data, and board-guided/local evidence for
unrepresented visual states. Exact-build approval, live/free-source population and entitlements,
physical multi-monitor validation, long-duration endurance, and excluded-domain capability stubs
remain open gaps; no threshold, mask, feature boundary, or completion criterion was silently
relaxed.

## Current continuation checkpoint — 2026-08-09T13:20:00Z

The ratio editor uncovered and fixed a real persistence/concurrency chain. Golden Layout now
deduplicates identical `stateChanged` fingerprints; workspace saves retain a bounded pending timer,
retry stale generations, and hydrate the persisted blue-link symbol before tools mount. Snapshot
and factory-reset API writers now lock the workspace row so concurrent full-tab replacement returns
the intended 409 instead of a duplicate-key 500. Focused F8e.2 passes `1/1`, frontend Vitest
`654/654`, and type-check/build pass. A broad authenticated run was stopped after `38` passes with
`9` adjacent failures and `1` interrupted Study Lab path; this is evidence for remaining defects,
not completion. No acceptance flexibility was used for the fixes; board/local, controlled-fixture,
and exact-build reference gaps remain explicitly tracked.

## Current continuation checkpoint — 2026-08-09T10:40:00Z

Closed a direct top-down workflow gap: the primary Relative Strength tool now exposes a persisted
comparison-leg editor. The user can add/remove canonical legs such as `XLE` while viewing `XLK`,
producing `XLK/SPY` plus `XLK/XLE` in the same uPlot window without leaving the workstation.
Focused RatioUPlot coverage passes `10/10`; F8e.2 passes `1/1`; frontend Vitest passes `653/653`
across 91 files; type-check/build pass; authenticated browser passes `70/70`; and the complete
board-guided visual matrix passes `68/68` across all four environments.

Two 1920×1080/125%-display baselines were intentionally refreshed after visual review because the
new control is visible and the seeded fixture reports current freshness. Acceptance flexibility
used: board-guided/local baseline evidence for the previously unrepresented ratio-editor state;
exact-build evidence remains an explicit visual gap. No threshold, mask, baseline policy, or
acceptance criterion was silently relaxed.

## Current continuation checkpoint — 2026-08-09T09:08:00Z

The TC2000 workstation path was revalidated against a freshly rebuilt, repository-controlled
market fixture. A real backend defect was fixed: analysis freshness now resolves canonical
adjusted dataset keys such as `D1:adj` while retaining legacy `D1` compatibility. The focused
regression passed logically; the authoritative backend suite passes `1285/1285` at `79.47%`.
Seeded SPY technicals and `XLK/SPY` ratios now return current/full-coverage freshness, with the
focused top-down browser slice passing `7/7`.

The complete authenticated browser matrix passes `69/69`; the board-guided visual matrix passes
`68/68` across all four required display environments; the visual manifest validates; and recent
service logs have no 5xx, traceback, MissingGreenlet, UniqueViolation, critical, or fatal
signatures. Flexibility used: controlled, provenance-labelled fixture data rather than live
provider data. That evidence does not close live/free-source entitlement, population breadth,
official-membership, or taxonomy gaps; all remain explicitly tracked. No visual threshold, mask,
baseline, or acceptance criterion was relaxed.

## Current continuation checkpoint — 2026-08-09T08:34:23Z

Rebuilt the branch-scoped Docker stack with `make test-stack-up`, applied migrations, and verified
backend, frontend, worker, research-runner, Postgres, and Redis health. The authenticated
`flows.spec.ts` matrix passes `69/69` in one worker, covering the usable workstation/top-down
workflow, link groups/timeframes/crosshairs, browser pop-outs, Study Lab, unified Python reuse,
scans/gauges, notes/alerts, legacy compatibility, unsupported-domain absence, uPlot, and
performance guards. The post-run service-log audit found no HTTP 500, traceback, MissingGreenlet,
UniqueViolation, critical, or fatal signatures.

This does not close the backend data gaps: expected 404s remain where seeded ETF holdings/industry
composition or OHLCV are unavailable, and logs correctly expose missing optional provider
credentials/exhausted free-source fallback chains. Those are explicit provider/data-coverage gaps
to resolve or preserve as honest freshness/unavailable states; no acceptance criterion was relaxed.

## Current continuation checkpoint — 2026-08-09T12:30:00Z

Added deterministic visual acceptance for the Study Lab sandbox-error state. The browser fixture
validates source validation, failed-run creation, sandbox diagnostics, warning and execution-log
disclosure, resource-use presentation, and the rerun affordance; focused checks pass `4/4` across
all required display environments. The complete board-guided visual matrix is now `68/68`. This
remains interim `REF-STUDY-LAB-V25` / `REF-STATE-VARIANTS` evidence because the board has no
authoritative Study Lab error capture; acceptance flexibility used: deterministic failed-run
fixture only, with no masks, thresholds, or criteria changed. `sandbox_error` remains explicitly
`required_missing` in the manifest.

## Current continuation checkpoint — 2026-08-09T12:00:00Z

Added deterministic visual acceptance for the completed Study Lab structured-result state. The
browser fixture validates source validation, run creation, completed status, scalar metrics, bar
and histogram uPlot renderers, summary table, and clickable occurrence output; focused checks pass
`4/4` across all required display environments and the complete board-guided visual matrix remains
`64/64`. These are interim `REF-STUDY-LAB-V25` / `REF-STATE-VARIANTS` baselines because the board
does not represent Study Lab; acceptance flexibility used: deterministic completed-run fixture
only, with no masks, thresholds, or criteria changed. The manifest and gap ledger retain histogram
and occurrence-table as `required_missing`.

## Current continuation checkpoint — 2026-08-09T11:00:00Z

Added the Study Lab running-state visual oracle. A deterministic queued/running research fixture
now exercises the real validation, run, progress, polling, and cancellation surface, with local
baselines across all four required display environments; focused checks pass `4/4`. This remains
interim `REF-STUDY-LAB-V25` / `REF-STATE-VARIANTS` evidence because the vision board has no
authoritative running-state capture. Acceptance flexibility used: deterministic runner fixture
only; no masks, thresholds, or criteria changed. The complete board-guided visual matrix then
passed `60/60` across all four required environments.

## Current continuation checkpoint — 2026-08-09T10:30:00Z

Added the shell fetching freshness state to the application-shell visual gap register. The real
pending-OHLCV behavior now has deterministic local baselines across all four required display
environments; focused checks pass `4/4`. This remains interim `REF-STATE-VARIANTS` evidence because
the board does not provide pinned-build fetching styling. Acceptance flexibility used: documented
board/state-variant substitution only; no masks, thresholds, or criteria changed. Docker build
cache cleanup was completed safely with `docker builder prune -af`; images, containers, and volumes
were preserved. The broader `docker system prune -af` request was not used because it would be an
unbounded destructive cleanup. The complete board-guided visual matrix then passed `56/56` across
the four required environments.

## Current continuation checkpoint — 2026-08-09T10:00:00Z

Closed a disabled-control evidence gap in Study Lab: the validation-error visual flow now asserts
that the Run action is disabled, and the manifest links that state to the existing four-environment
baselines. Focused checks pass `4/4`; this remains interim `REF-STATE-VARIANTS` evidence because
no authoritative pinned-build styling exists. Acceptance flexibility used: board/state-variant
substitution only; no masks, thresholds, or criteria changed.

## Current continuation checkpoint — 2026-08-09T09:30:00Z

Added keyboard-selected active-symbol search to the application-shell visual gap register. The
ArrowDown/`aria-selected` interaction and four deterministic local baselines pass `4/4`; the
complete board-guided visual matrix now passes `52/52`. The state remains an interim
`REF-STATE-VARIANTS` oracle because the board lacks authoritative pinned-build styling.
Acceptance flexibility used: board/state-variant substitution only; no masks, thresholds, or
criteria changed.

## Current continuation checkpoint — 2026-08-09T09:00:00Z

Added unavailable freshness to the application-shell visual gap register. Four deterministic
interim baselines were captured and rerun successfully (`4/4`) across the required display
environments; the complete board-guided matrix now passes `48/48`. The state remains under
`REF-STATE-VARIANTS` because the board lacks authoritative pinned-build styling for it.
Acceptance flexibility used: board/state-variant substitution only; no masks, thresholds, or
criteria changed.

## Current continuation checkpoint — 2026-08-09T08:35:00Z

Added the delayed-freshness state to the board-guided visual acceptance track. Its deterministic
four-environment interim baselines are captured and re-run cleanly (`4/4` focused); the complete
visual matrix now passes `44/44` across 1920×1080 and 2560×1440 at 100%/125%, with the manifest
validator passing. `REF-STATE-VARIANTS` remains open because these are local interim baselines,
not exact pinned-build captures. Acceptance flexibility used: the documented board/state-variant
substitution only; no masks, thresholds, or criteria changed.

## Current continuation checkpoint — 2026-08-09T08:10:00Z

Closed a stale top-down acceptance record: Docker-backed integration verification for breadth,
relative rotation, and point-in-time relative-strength was available and executed in the current
stack. The focused analysis matrix passed `5/5`, covering aligned bars, membership/bar cutoffs,
breadth history, rotation tails, and ratio legs; only two known third-party NumPy/nautilus
deprecation warnings were emitted. No acceptance flexibility or visual criterion changed.
Exact/unrepresented visual, live-entitlement, native-monitor, endurance, and remaining
requirement-level gaps remain explicitly tracked.

## Current continuation checkpoint — 2026-08-09T07:50:00Z

Closed the remaining Market Gauge freshness-state presentation mismatch found in the fix-first
audit: normalized `delayed` is now styled as a freshness warning rather than inheriting the green
current-data color. The unit contract covers `coverage_limited`, `coverage-limited`, and `delayed`
(`22/22` focused tests); rebuilt authenticated `F8w-a` passes `1/1`; full frontend Vitest passes
`652/652` across 91 files; `vue-tsc` and the production build pass; and the complete board-guided
visual matrix remains `40/40` across all four required environments. No baseline, mask, threshold,
or acceptance criterion changed. Acceptance flexibility used: none; exact/unrepresented visual,
provider-entitlement, native-monitor, endurance, and remaining product-scope gaps remain explicit.

## Current continuation checkpoint — 2026-08-09T07:35:00Z

Closed a shared freshness contract defect in Market Gauge. It now uses the same workstation
normalizer as the shell and Relative Rotation, so backend `coverage_limited` and
`coverage-limited` both render as `Coverage limited` and use the normalized state key for
warning styling. Focused Market Gauge/freshness coverage passes `21/21`; rebuilt authenticated
`F8w-a` passes `1/1`; full frontend Vitest passes `651/651` across 91 files; `vue-tsc`,
production build, authenticated Chromium `69/69`, board-guided visual `40/40`, and the final
service-log audit pass. No visual baseline, mask, threshold, or acceptance criterion changed.

The same full browser run exposed two localized diagnostic/lifecycle races and they were repaired
under the fix-first tie-break: repeated pop-out cleanup now treats an already-closed disposable
child as idempotent cleanup (`F8f` repeated `5/5`), and the logout diagnostics helper filters the
single explicitly allowed `Authentication required` page error alongside expected 401 responses
(`F5` `1/1`). The complete matrix then passed `69/69`. Acceptance flexibility used: none for
these repository-controlled corrections; board-guided represented-state, exact/unrepresented
visual, live-provider, native-monitor, endurance, and remaining scope gaps stay explicit.

## Current continuation checkpoint — 2026-08-09T07:20:00Z

Corrected a top-down lineage naming defect exposed during the real drilldown audit: an industry
row model was assigning the ETF holdings composition date to a field named `freshness`. It now
uses `as_of`, and the associated column definition is labelled `As of` where that model is used;
the compact rendered Industries surface remains the intended count/list view. The corrected
deep drilldown passes `F8e.1` `1/1`; focused top-down/relative-strength flows pass `4/4`, focused
workstation unit coverage remains green, and type-check is clean.

The prior full gates remain valid for the shared formatter change: frontend Vitest `649/649`,
authenticated Chromium `68/68`, board-guided visual `40/40`, production build, and clean
runtime-log audit. Acceptance flexibility used: none. The visual-board, live-entitlement,
native-monitor, bounded-endurance, and remaining scope gaps remain explicit.

## Current continuation checkpoint — 2026-08-09T07:00:00Z

Closed a freshness-contract mismatch in the workstation. Backend analysis payloads use the
snake-case value `coverage_limited`, while the shell's documented state vocabulary is
`coverage-limited`; the shared mapper now normalizes both spellings and the state contracts
accept delayed/coverage-limited values explicitly. Relative Rotation and top-down lineage
metadata now use the same human-readable formatter. The focused unit regression passes `16/16`,
the real authenticated `F8i-e` browser regression passes `1/1`, and the full frontend suite
passes `649/649` with type-check and production build green.

The complete post-change authenticated Chromium matrix passes `68/68`, including all top-down,
Study Lab, linking, pop-out, legacy, and performance flows. The board-guided visual matrix was
also rerun at `40/40` across the four required environments, with the manifest valid and no
baseline, mask, or threshold changes. The final branch-stack log audit is clean.

Acceptance flexibility used: none for this repository-controlled correction. The composite board
continues as the active reference for represented states; exact/unrepresented visual states, live
provider entitlements, native physical multi-monitor behavior, beyond-bounded endurance, and
remaining requirement-level scope gaps remain explicitly tracked.

## Current continuation checkpoint — 2026-08-09T06:45:00Z

Closed a source-boundary gap in the new workstation. Canonical symbol search, symbol
resolution, expression resolution, comparison legs, and industry-proxy selection now request
`canonical_only=true`, so ordinary TC2000 workstation interaction reads the local canonical
security master and never fans out to providers. The legacy/default instrument endpoints still
retain explicit provider discovery for compatibility and scheduled/backfill workflows remain
the owner of provider fan-out. Focused canonical-boundary integration tests pass `2/2`; focused
frontend contract tests pass `19/19`; focused rebuilt-stack F7/F8d/F8d-SPX pass `3/3`.

The broad post-change gates are green: backend `1,284/1,284` at `79.49%` combined coverage,
frontend Vitest `643/643` across 91 files, `vue-tsc --noEmit`, production build, authenticated
Chromium `67/67`, and a final backend/worker/research-runner/frontend log audit with no HTTP
500, traceback, MissingGreenlet, UniqueViolation, critical, or fatal signatures.

Acceptance flexibility used: none for this source-controlled contract correction. The visual
board remains the active reference for represented states; exact-build/unrepresented visual
states, provider/live-entitlement probes, native physical multi-monitor behavior,
beyond-bounded endurance, and remaining requirement-level product/backend gaps remain explicit
open items rather than being treated as complete.

## Current continuation checkpoint — 2026-08-09T06:25:00Z

Closed two repository-controlled acceptance defects found while extending the requested
SPX/SPY benchmark workflow. `/chart/SPX` now attempts the official canonical SPX identity and,
when that series is unavailable, resolves the configured canonical SPY tradable proxy and shows
the explicit limitation in the workstation footer instead of leaving a dead symbol. A focused
rebuilt-stack browser regression passes `1/1`. The same browser audit exposed a real concurrent
indicator persistence `MissingGreenlet` 500; the endpoint now reads the authenticated identity
without triggering implicit async ORM IO. Its focused Docker-backed integration tests pass `2/2`.
The authoritative combined Docker-backed backend gate passes `1,282/1,282` at `79.43%` coverage
above the 75% threshold; the complete authenticated Chromium matrix passes `67/67`, including
the new SPX regression; and the final rebuilt-stack service-log audit has no critical signatures.
Frontend Vitest remains `643/643`, `vue-tsc --noEmit`, and production build pass.

Acceptance flexibility used: a deterministic 404 fixture proves the honest unavailable-official-
series fallback because free-source fixtures do not promise an entitled SPX series. The product
does not claim SPY is SPX; the notice remains visible. Exact-build/unrepresented visual states,
provider/live-entitlement probes, native physical multi-monitor behavior, beyond-bounded endurance,
and remaining requirement-level product/backend gaps remain explicitly open.

## Current continuation checkpoint — 2026-08-09T05:55:00Z

Closed a real symbol-entry race found by the fix-first shell audit. Async initial SPY hydration
could rewrite a focused user query between keystrokes, producing `SPYSP` in the active-symbol
field even though the autocomplete request was for `SP`. User edits now invalidate the initial
selection generation, and hydration/watchers preserve a focused, newer draft until the user
explicitly selects or submits it. The browser regression asserts the DOM value is exactly `SP`
and captures a live render with `SP`, then all four focused-search baselines were regenerated
from that asserted state.

The complete board-guided visual matrix passes `40/40` across the four required environments,
including shell default, menu-open, focused-search, Study Lab, loading, provider-error,
blocked-pop-out, stale, partial, and validation-error states. The stale-state capture was also
made deterministic by waiting for the Refresh control to settle; no visual threshold was raised.
The authenticated Chromium matrix passes `66/66`; frontend Vitest passes `643/643` across 91
files; `vue-tsc --noEmit` and the production build pass; and the post-run service-log audit has
no HTTP 500, traceback, MissingGreenlet, UniqueViolation, critical, or fatal signatures.

Acceptance flexibility used: the documented composite-board track for represented visual states
and deterministic canonical search fixtures where seeded data does not guarantee autocomplete.
The fixture does not close live-provider evidence. Exact-build/unrepresented visual states,
provider/live-entitlement probes, native physical multi-monitor behavior, beyond-bounded
endurance, and remaining requirement-level product/backend gaps remain explicitly open.

## Current continuation checkpoint — 2026-08-09T04:15:00Z

Closed a real workstation visual defect found by the fix-first geometry audit: chart Compare,
Plots, and Templates controls were drawn over the uPlot OHLC readout. The chart surface now
reserves a dedicated top control strip, and the board harness fails on control/readout or
control/control overlap instead of allowing a screenshot threshold to hide it. Preserved prior
baselines, refreshed only the affected shell/stale/partial states, and verified the rebuilt stack:
the complete board-guided visual matrix passes 32/32 across all four required environments;
the complete authenticated Chromium matrix passes 66/66; frontend Vitest passes 643/643;
`vue-tsc --noEmit` and production build pass; the final two-minute service-log audit contains
no HTTP 500, traceback, MissingGreenlet, UniqueViolation, critical, or fatal signatures.
Acceptance flexibility used: the documented composite-board track for represented visual states;
exact-build/unrepresented, provider/live-entitlement, native-monitor, bounded-endurance, and
remaining product-scope gaps remain explicitly open.

## Current continuation checkpoint — 2026-08-09T04:44:00Z

Closed a top-down workflow defect found during the fix-first acceptance audit: the default
Relative Strength window could render the meaningless `SPY/SPY` ratio because its benchmark
legs were derived from the selected holdings ETF instead of the automatic ratio contract. Added
the shared `autoRatioBenchmarks` derivation so SPY uses RSP, sectors use SPY, and constituents
use both sector ETF and SPY legs without self-reference. Added unit coverage (3/3 ratio tests),
rebuilt-stack authenticated F8e coverage (2/2, including the deep drill-down), frontend Vitest
passed 643/643, `vue-tsc --noEmit`, and production build passed. The visual harness now waits for
the deterministic `SPY/RSP` state before capturing the shell baseline; the complete board-guided
visual matrix passes 32/32 across all four required environments. Acceptance flexibility used:
the documented composite-board track for represented states; exact/unrepresented,
provider/live-entitlement, native-monitor, bounded-endurance, and remaining product-scope gaps
remain explicitly open.

## Current continuation checkpoint — 2026-08-09T03:33:12Z

Re-ran the authoritative combined Docker-backed backend gate after the browser-fixture change:
`1,282/1,282` passed with `79.43%` coverage and 86 known third-party deprecation warnings.
The branch-scoped stack remains healthy and the frontend/browser evidence remains `32/32`
board-guided visuals and `65/65` authenticated Chromium flows. A Docker usage audit measured
approximately 10.0 GB in use (about 8.5 GB reclaimable); the requested broad `docker system prune
-af` was rejected by the safety policy, so no deletion or workaround was attempted. This is an
operational cleanup limitation only, not a product or acceptance relaxation. Exact-build or
unrepresented visual, provider/live-entitlement, native-monitor, beyond-bounded endurance, and
remaining product-scope gaps remain explicitly open.

## Current continuation checkpoint — 2026-08-09T03:24:16Z

Closed a deterministic authenticated-browser isolation gap discovered while revalidating the
board. The Playwright login fixture now resets each user's default factory workspace after
login, preventing persisted ratio expressions, link selections, and layout mutations from a
previous visual project or rerun leaking into the next baseline. The isolated stale-freshness
state passes 3/3 at 1440×900/125%, and the complete four-environment board matrix passes 32/32.
The full authenticated Chromium matrix passes 65/65; frontend Vitest passes 642/642 across 91
files; `vue-tsc --noEmit`, production build, and the post-run stack log audit pass. Acceptance
flexibility used: none for the fixture or functional fixes; the documented composite-board track
continues to apply only to represented visual states. Exact-build/unrepresented visual,
provider/live-entitlement, native-monitor, beyond-bounded endurance, and remaining product-scope
gaps remain explicitly open.

## Current continuation checkpoint — 2026-08-09T03:01:36Z

Closed a unified-language consistency gap in the primary Study Lab. Study Lab had retained a
separate plain textarea/autocomplete implementation while Code Library used the shared
`PythonSourceEditor`; it now uses the shared editor for the same SDK suggestions, signatures,
normalization, keyboard completion, outside-pointer dismissal, and ARIA listbox semantics. The
focused Study Lab/editor suite passes `21/21`; rebuilt authenticated F8g/F9i passes `2/2`; the
complete authenticated Chromium matrix passes `65/65`; full frontend Vitest passes `642/642`
across 91 files; `vue-tsc --noEmit` and the production build pass. Acceptance flexibility used:
none. The post-run backend/worker/research-runner/frontend log audit found no HTTP 500,
traceback, MissingGreenlet, UniqueViolation, critical, or fatal signatures.
Visual-reference, provider-live, native-monitor, bounded-endurance, and other explicit goal gaps
remain tracked and unchanged.

## Current continuation checkpoint — 2026-08-09T05:10:00Z

Re-audited the tracked Anfield/ADFI holdings gap. The configured Regents Park product route still
returns HTTP 404; public search evidence describes the former ADFI page and holdings download, and
Anfield’s current corporate site reports that Anfield Capital Management is now part of Horizon.
No replacement executable first-party holdings endpoint was verified, so the adapter remains
unpromoted and preserves route-failure provenance plus conditional SEC fallback. Acceptance
flexibility used: none. This is an explicit external provider gap, not a goal-wide blocker.

## Current continuation checkpoint — 2026-08-09T04:50:00Z

The authoritative Docker-backed combined backend gate passed `1,282/1,282` unit/integration
tests with `79.43%` line coverage, above the required 75% threshold. This revalidates the current
API, provider, research, sandbox, and persistence paths after the frontend continuation. No
acceptance flexibility was used; visual/provider live-evidence, hardware, endurance, and remaining
product-scope gaps remain explicit.

## Current continuation checkpoint — 2026-08-09T04:30:00Z

The rebuilt stack passed the complete authenticated `flows.spec.ts` matrix `65/65` after the
keyboard-completable Python editor change. The matrix covers the current workstation, supporting
flows, legacy compatibility, unsupported-domain absence, and performance guards; the post-run
runtime log audit found no critical signatures. No acceptance flexibility was used for this
functional run. Exact-build/unrepresented visual, provider/live-entitlement, native monitor,
beyond-bounded endurance, and remaining product-scope gaps remain open.

## Current continuation checkpoint — 2026-08-09T04:00:00Z

Closed the keyboard-completion gap in the shared Python authoring surface. `PythonSourceEditor`
now supports ArrowUp/ArrowDown selection, Enter/Tab insertion, Escape dismissal, and explicit
listbox active-selection semantics without taking over normal editor navigation when suggestions
are closed. Focused editor/CodeLibrary coverage passed `7/7`; full frontend Vitest `642/642` across
91 files; type-check/build passed; rebuilt authenticated F9h passed `1/1`; and the final
four-environment board-guided visual matrix passed `32/32`. Board-guided flexibility was used for
represented visual states; no masks, thresholds, or baselines changed. Exact-build/unrepresented,
provider/live-entitlement, native monitor, beyond-bounded endurance, and remaining product-scope
gaps remain open.

## Current continuation checkpoint — 2026-08-09T03:50:00Z

Revalidated the workstation after the Python editor integration against the active 190-image
composite reference board. Manifest validation passed and all four required display environments
passed the complete board-guided matrix (`32/32`): shell, Study Lab, loading, provider-error,
blocked-pop-out, stale, partial-coverage, and validation-error states. Board-guided visual
flexibility was used for represented states; no masks, thresholds, or baselines changed. The
remaining exact-build/unrepresented gaps (`REF-SHELL-V25`, `REF-STATE-VARIANTS`, and related
manifest entries) remain explicitly open.

## Current continuation checkpoint — 2026-08-09T02:15:30Z

## Current continuation checkpoint — 2026-08-09T03:35:00Z

Closed the next reusable-Python authoring gap by adding `PythonSourceEditor` to Code Library new
asset and immutable-version editors. The shared editor offers context-aware unified SDK
suggestions/signatures and deterministic source normalization, while canonical validation and
output-contract preflight remain authoritative. A rebuilt F9h browser run exposed and closed a
real suggestion-popover pointer interception bug; focused editor/CodeLibrary tests pass `6/6`, full
frontend Vitest `641/641` across 91 files, `vue-tsc`, production build, rebuilt authenticated F9h
`1/1`, and runtime logs are clean of critical signatures. Acceptance flexibility used: none.
Exact/unrepresented visual states, provider/live-entitlement, native monitor, beyond-bounded
endurance, and remaining product-scope gaps remain open.

Closed the Python Library output-contract preflight gap. Validation now reconciles produced
contracts with the selected asset kind/version (series for plots, scalar for columns, boolean for
conditions, etc.), reports a source-positioned mismatch, and prevents a syntactically valid but
incompatible source from being persisted. Focused CodeLibraryTool coverage passed `4/4`, full
frontend Vitest `639/639`, type-check/build passed, and rebuilt authenticated F9h passed `1/1`.
Acceptance flexibility used: none. Exact/unrepresented visual states, provider/live-entitlement,
native monitor, beyond-bounded endurance, and remaining product-scope gaps remain open.

## Current continuation checkpoint — 2026-08-09T02:11:47Z

Aligned the reusable Python Library with Study Lab's canonical authoring contract. New asset and
immutable-version flows now validate through `/code/validate`, show source-positioned diagnostics,
and refuse persistence when validation fails; changing source invalidates prior validation. Added
valid/invalid component coverage (`3/3` focused), full frontend Vitest `638/638`, type-check/build,
rebuilt-stack authenticated F9h Python-library → EasyScan → alert acceptance `1/1`, and no browser
diagnostic failures. Acceptance flexibility used: none. Exact/unrepresented visual states,
provider/live-entitlement, native monitor, beyond-bounded endurance, and remaining product-scope
gaps remain open.

## Current continuation checkpoint — 2026-08-09T02:06:26Z

Closed a concrete screen-recovery correctness edge case found during continuation audit. The
Window Management API path now treats a display inventory as authoritative only when every
reported screen has complete usable bounds; a partially malformed inventory preserves the saved
pop-out coordinates instead of making a recovery decision from incomplete data. The focused
geometry suite passes `7/7`, full frontend Vitest `637/637`, type-check/build pass, and the rebuilt
pop-out/cross-window subset passes `9/9`. An earlier non-elevated Chromium launch and stale
root-level test artifact were cleaned up; the correctly configured elevated F8b rerun passes.
Acceptance flexibility used: none. Native physical multi-monitor behavior, exact/unrepresented
visual states, provider/live-entitlement coverage, beyond-bounded endurance, and remaining
product-scope gaps remain open.

## Current continuation checkpoint — 2026-08-11T23:00:00Z

Strengthened workstation lifecycle endurance evidence. The pop-out churn guard now permits up to
500 explicitly requested rounds while remaining hard-bounded; a real rebuilt-stack
`TC2000_POP_OUT_CHURN_ROUNDS=250` two-popout soak passed `1/1` in `4.8m`, preserving source
tool/canvas/chart counts on every round and satisfying the available Chromium heap ceilings.
`vue-tsc --noEmit` passed. No acceptance flexibility was used. This does not erase the separate
indefinite-soak gap; native physical multi-monitor placement, exact/unrepresented visual states,
provider/live-entitlement coverage, and remaining product-scope gaps remain open.

## Current continuation checkpoint — 2026-08-11T22:00:00Z

Implemented the repository-controlled portion of multi-monitor pop-out recovery. The synchronous
popup path now optionally queries the browser's Window Management API after creation, preserves
saved geometry when it intersects any available display, and moves/resizes a disconnected-display
window to a safe current-display default. Older browsers or denied permission leave coordinates
untouched, avoiding destructive single-screen guesses. Geometry tests pass `6/6`; type-check/build,
full frontend Vitest `636/636`, rebuilt pop-out subset `9/9`, and complete authenticated Chromium
`65/65` pass. The root-level npm invocation error was a setup mistake corrected by running from
`frontend/`. No acceptance flexibility was used. Native physical monitor placement still needs
hardware validation; exact/unrepresented visual, provider/live-entitlement, beyond-bounded
endurance, and remaining product-scope gaps remain open.

## Current continuation checkpoint — 2026-08-11T21:00:00Z

Closed the cross-window symbol/timeframe evidence gap. `F8n-cross-window-links` floats the real
primary chart, changes the parent workstation to `QQQ` and weekly timeframe, and verifies the
detached chart follows through the canonical link bus. Existing behavior passed unchanged:
focused acceptance `1/1`, complete rebuilt authenticated Chromium `65/65`. Together with the
cross-window cursor flow, all three linked event classes are now browser-verified. No acceptance
flexibility was used. Native physical multi-monitor placement, exact/unrepresented visual states,
provider/live-entitlement coverage, beyond-bounded endurance, and remaining product-scope gaps
remain explicitly open.

## Current continuation checkpoint — 2026-08-11T20:00:00Z

Closed the cross-window linked-cursor evidence gap. `F8n-cross-window` floats the actual primary
chart, moves its uPlot cursor in the child browser window, and verifies that the parent Relative
Strength chart follows through the canonical BroadcastChannel/storage link bus. The existing
implementation passed unchanged: focused acceptance `1/1`, complete rebuilt authenticated
Chromium `64/64`. No acceptance flexibility was used. Exact-build/unrepresented visual states,
native physical multi-monitor placement, provider/live-entitlement coverage, beyond-bounded
endurance, and remaining product-scope gaps remain explicitly open.

## Current continuation checkpoint — 2026-08-11T19:00:00Z

Closed the linked-crosshair browser-evidence gap for the current workstation implementation. A
new acceptance flow proves that moving the primary seeded uPlot cursor publishes the selected bar
timestamp and moves the linked Relative Strength cursor. The first test oracle read `style.left`,
but uPlot uses CSS `transform` plus `u-off`; that assertion was corrected and the focused flow
passed `1/1`. The repeated-float lifecycle oracle was also hardened to wait for both factory charts
to complete asynchronous initialization before taking its canvas baseline; this preserves the
actual no-accumulation criterion and avoids mistaking a legitimate late ratio canvas for a leak.
Isolated F8f passed and the complete rebuilt authenticated Chromium matrix passed `63/63`. No
acceptance flexibility was used. The board-guided visual gate remains `32/32`; exact-build,
unrepresented visual, native multi-monitor, provider/live-entitlement, endurance, and remaining
product-scope gaps remain open.

## Current continuation checkpoint — 2026-08-11T18:00:00Z

Implemented the planned active-symbol history interaction in the authenticated workstation shell
using the existing bounded persisted recent-instrument store. The compact menu supports selection,
clear, ARIA menu semantics, and outside/Escape dismissal. A real browser run exposed and closed the
initial-route edge case where `SPY` was already selected and therefore did not trigger the watcher;
successful explicit symbol and industry-proxy selections now record history, while linked changes
remain covered by the watcher. Focused shell tests passed `14/14`, full frontend Vitest `634/634`,
type-check/build passed, focused browser history acceptance `1/1`, and complete authenticated
Chromium `62/62`. A stale 1080p/100 local shell baseline was reviewed and regenerated only for the
new deterministic ready-state render; no mask or threshold changed, and the board-guided visual
matrix passed `32/32`. Board-guided acceptance for represented states was used; `REF-SHELL-V25`
and other unrepresented exact-build states remain tracked gaps.

## Current continuation checkpoint — 2026-08-11T17:00:00Z

Closed a localized TC2000 Version 25 workstation interaction gap: Workspace and Add Tool menus
now have explicit accessible menu semantics, dismiss deterministically on outside pointer input
and Escape, and preserve editor/symbol-search keyboard ownership. Capture-order handling was
required because nested Golden Layout surfaces could consume bubbling pointer events. The first
full browser run exposed five stale button-role assertions; those tests were corrected to the
new menuitem contract, then the rebuilt authenticated Chromium matrix passed `61/61`. Focused
shell tests passed `13/13`, full frontend Vitest `633/633` across 90 files, type-check/build
passed, and no acceptance flexibility was used. This fix does not close the separately tracked
exact-build visual, provider-entitlement, native multi-monitor, or endurance gaps.

## Current continuation checkpoint — 2026-08-11T16:00:00Z

Closed the REX Shares holdings-route gap under the mandatory fix-first tie-break. The official
TSLT product page returned HTTP 200 with a complete holdings CSV; the existing `RexHoldingsAdapter`
is now marked native/live-backed and removed from fallback audits. The first opt-in live assertion
was intentionally allowed to fail because the issuer artifact has no composition-date field; the
test was corrected to preserve that absence rather than infer a date, then the live REX matrix
passed `3/3` (including route invariants). The adapter suite passed `457/457`, and the authoritative
Docker-backed backend gate passed `1,282/1,282` at `79.43%` coverage with 86 known dependency
deprecation warnings. Anfield remains an explicit HTTP 404 route gap. Acceptance flexibility used:
none.

## Current continuation checkpoint — 2026-08-11T15:00:00Z

Closed the Sterling Fund Management/SCMC holdings-route gap under the mandatory fix-first
tie-break. The official Sterling Capital fund-scoped export returned HTTP 200 with a dated PDF
that the existing adapter parsed into 182 holdings; Sterling is now marked native/live-backed,
removed from fallback audits, and covered by a deterministic registry guard plus an opt-in live
test. The complete ETF adapter suite passed `456/456`, the focused live matrix passed `2/2`, and
the authoritative Docker-backed backend gate passed `1,281/1,281` at `79.43%` coverage with 86
known dependency deprecation warnings. Anfield remains an explicit HTTP 404 route gap. Acceptance
flexibility used: none.

## Current continuation checkpoint — 2026-08-11T14:00:00Z

Closed the Redwood/LeaderShares holdings-route gap under the mandatory fix-first tie-break. The
existing provider-specific adapter is now marked native/live-backed after the official
`funds/holdings-download?fund=leadershares-tactical-focused-etf` endpoint returned HTTP 200 with
the complete dated CSV; the opt-in live test passed for LSAT. Redwood was removed from the
fallback audit, and deterministic route/parser plus registry coverage pass. Anfield remains
explicitly unpromoted because its current product URL returns HTTP 404 and is separately tracked.
The authoritative Docker-backed backend gate then passed `1,280/1,280` at `79.43%` coverage with
86 known dependency deprecation warnings. Acceptance flexibility used: none.

## Current continuation checkpoint — 2026-08-11T13:00:00Z

Applied the mandatory fix-first tie-break to the latest provider corrections. Fairlead alias and
Impact Shares route/parser changes were re-run after documentation/goal updates: ETF adapter units
remain `454/454`, live-provider registry invariants are clean (`2 skipped` because opt-in HTTP is
disabled), Ruff, compileall, and `git diff --check` pass. REX/Sterling were not promoted from
audited status because issuer DNS is unavailable in this environment; that external evidence gap
is tracked and does not block independent workstation/backend work. Acceptance flexibility used:
none.

## Current continuation checkpoint — 2026-08-11T12:00:00Z

Closed the Impact Shares holdings-route gap. The official NACP product page's declared
`TidalFG_Holdings_NACP.csv` route is now a native `impact_shares` adapter rather than a
StockAnalysis fallback; the route returned HTTP 200 via curl. The parser also now recognizes the
issuer's `% Net of Assets` header spelling. Deterministic route/parser coverage, catalog and
fallback invariants pass; the complete ETF-adapter unit suite passes `454/454`, Ruff, compile,
and diff checks pass. The opt-in Python HTTP probe remains environment-DNS limited and is tracked
separately. Acceptance flexibility used: none.

## Current continuation checkpoint — 2026-08-11T11:00:00Z

Closed the Fairlead discovery-identity routing gap without changing the free-source boundary.
The `fairlead` ETFDB identity now resolves to its already verified Fairlead/Cary Street TACK
issuer-page/FilePoint holdings adapter, is marked native/live-backed, and is removed from the
fallback-only audit. The existing mocked issuer route is covered for both `cary_street` and
`fairlead` aliases; the complete ETF-adapter unit suite passes `453/453`, live-provider registry
and route-invariant checks pass (live HTTP cases remain opt-in/skipped), Ruff and diff checks pass.
The broad backend gate was green at `1,277/1,277` before this isolated registry correction; no
other backend contract changed. Acceptance flexibility used: none. A direct Fairlead live probe
remains opt-in and separately tracked.

## Current continuation checkpoint — 2026-08-11T06:00:00Z

The complete rebuilt authenticated `flows.spec.ts` Chromium matrix passed `60/60` after the
persisted Study Lab activation repair. The run covered the current top-down, layout/link/pop-out,
Study Lab, EasyScan, alerts, notes, drag/drop, legacy, uPlot, and workstation-performance flows;
post-run service logs contained no critical backend/runtime signatures. Acceptance flexibility used:
none. Provider-route, visual-reference, native-multi-monitor, and beyond-bounded-endurance gaps
remain explicitly tracked.

The same rebuilt head passed the board-guided visual matrix `32/32` across all four required
display environments. No snapshot, mask, or criterion changed; exact-build and unrepresented
visual states remain explicit manifest gaps.

## Current continuation checkpoint — 2026-08-11T08:00:00Z

The fix-first regression slice was rerun from the frontend project root after correcting an
invalid repository-root `test:unit` command: Workspace layout, Research Results, Study Lab, and
chart plot-library suites pass `41/41`. The supported full frontend command passes `632/632`;
`vue-tsc --noEmit` and the production build pass. This verifies the localized repairs in their
broader context without changing the acceptance bar or masking remaining gaps. Acceptance
flexibility used: none.

## Current continuation checkpoint — 2026-08-11T09:00:00Z

Closed one provider-route gap without weakening the free-source boundary: Academy's official VETZ
page-declared holdings CSV now has a native configured adapter rather than a StockAnalysis
fallback. Curl confirmed the official route returns a dated CSV; deterministic route/parser and
catalog tests pass, and the opt-in Python live probe is present but remains environment-blocked by
DNS resolution before HTTP. Acceptance flexibility used: none; the live-probe environment gap is
tracked separately.

## Current continuation checkpoint — 2026-08-11T10:00:00Z

Academy's native holdings promotion now passes the full backend verification chain: adapter units
`452/452`, Docker-backed integration `285/285`, and combined unit/integration `1,277/1,277` at
`79.43%` coverage. The earlier two unit regressions were fixed under the mandatory tie-break by
adding Academy's explicit fetch entry point and removing it from the fallback-only expectation.
The Python live-probe DNS limitation remains separately tracked; acceptance flexibility used: none.

## Current continuation checkpoint — 2026-08-11T02:00:00Z

The rebuilt browser audit reproduced and closed a localized persisted-Study action defect: when a
Study Lab window already existed, the global Study action changed layouts but did not activate that
Golden Layout window. `openStudyLab()` now explicitly selects the existing Study Lab instance.
Research Results detail loading also now exposes a retryable error state instead of falsely showing
an empty artifact result. Focused workspace/Results coverage passes `48/48`; full frontend Vitest
passes `632/632`; type-check/build pass; rebuilt F9i passes `1/1` and F8g/F9i passes `2/2`.
Acceptance flexibility used: none. Provider-route, visual-reference, native-multi-monitor, and
beyond-bounded-endurance gaps remain separately tracked.

## Current continuation checkpoint — 2026-08-10T18:00:00Z

Re-probed the two currently actionable issuer routes in the repository Python 3.12 environment:
Donoghue Forlines DFTT passed; Anfield ADFI failed because the formerly verified Regents Park
product URL now returns HTTP 404. The adapter attempted its SEC fallback, but the standalone probe
does not supply SEC identifiers. This remains a provider-route/entitlement gap, not a core
workstation blocker; no fallback or provenance contract was weakened. Acceptance flexibility used:
none.

## Current continuation checkpoint — 2026-08-10T17:00:00Z

The complete authenticated fresh-stack Playwright matrix passed `63/63` executed tests; the 32
visual projects were correctly skipped by the non-visual command. This covers authentication,
workstation layouts, linking, pop-outs, top-down drilldown, Study Lab, EasyScan, alerts, notes,
drag/drop, legacy routes, uPlot performance, and churn. Post-run logs contain only expected
provider-exhaustion freshness warnings; no 500/traceback/MissingGreenlet/UniqueViolation/critical/
fatal signatures. Acceptance flexibility used: none.

## Current continuation checkpoint — 2026-08-10T16:00:00Z

Started the branch-scoped full Compose stack and verified backend, Postgres, Redis, worker, and
research-runner health. Backend `/health` returned `status=ok`; frontend served on port 80;
authenticated fresh-stack smoke flows F8d/F9h/F8g passed `3/3`. Post-smoke logs contain only the
expected provider-exhaustion freshness warning for FRED OHLCV, with no 500/traceback/
MissingGreenlet/UniqueViolation/critical/fatal signatures. Acceptance flexibility used: none.

## Current continuation checkpoint — 2026-08-10T15:00:00Z

Ran the authoritative Docker-backed backend coverage gate against the current branch head:
`1,277/1,277` unit and integration tests passed with `79.43%` coverage, above the required 75%
threshold. No backend regression or new error class was observed. Acceptance flexibility used:
none.

## Current continuation checkpoint — 2026-08-10T14:00:00Z

Revalidated the controlling visual acceptance gate with elevated Chromium permissions after the
non-elevated launcher hit macOS `mach_port_rendezvous` permission failures before test execution.
Manifest validation passed and the complete board-guided four-environment matrix passed `32/32`.
No screenshot masks or criteria were changed; the launch failure is retained as environment-level
tie-break evidence. Acceptance flexibility used: none.

## Current continuation checkpoint — 2026-08-10T13:30:00Z

EasyScan duplicate-scan (`409`) reconciliation now reads the existing screener through the shared
`['workstation', 'screeners']` query namespace with a fresh fetch, preserving the intentional
post-run invalidation/refetch for Market Gauge roots. Focused EasyScan coverage passes `10/10`,
full frontend Vitest passes `628/628` across 90 files, type-check/build pass, and authenticated
F9h passes `1/1`. Acceptance flexibility used: none.

## Current continuation checkpoint — 2026-08-10T13:00:00Z

Unified durable research-run caching across Study Lab and chart Python plots: Study Lab now uses
`['workstation', 'research-run', run_id]`, reuses fresh persisted entries, and retains explicit
zero-stale polling for active jobs. Focused Study Lab coverage passes `17/17`, including shared
cache reuse; full frontend Vitest passes `627/627` across 90 files, type-check/build pass, and
authenticated F8g/F9i pass `2/2`. Acceptance flexibility used: none.

## Current continuation checkpoint — 2026-08-10T12:30:00Z

Study Lab persisted-run hydration now uses the shared `['workstation', 'study-run', run_id]`
Vue Query namespace, so concurrent linked/virtual roots deduplicate durable-run reads while the
existing explicit one-second polling path retains fresh status/error behavior. Focused Study Lab
coverage passes `16/16`, including the cross-root deduplication regression; full frontend Vitest
passes `626/626` across 90 files, `vue-tsc --noEmit`, production build, and rebuilt authenticated
F8g/F8o/F8q pass `3/3`. The active goal now explicitly requires fix-first tie-breaking for
repository-controlled defects. Acceptance flexibility used: none.

## Current continuation checkpoint — 2026-08-10T12:00:00Z

The authenticated workstation symbol search now uses a shared normalized-query Vue Query entry
with a 30-second freshness window, while its existing debounce and request-generation checks remain
in force. Focused workstation-shell tests pass `12/12`; full frontend Vitest passes `625/625`
across 90 files, type-check and production build pass, and rebuilt authenticated F8d passes `1/1`.
Acceptance flexibility used: none.

## Current continuation checkpoint — 2026-08-10T11:30:00Z

VirtualWatchlistTool condition-result summaries now use a shared per-screener query keyed by the
active universe member IDs, preserving refetches when linked universes change while deduplicating
identical roots. Focused VirtualWatchlist tests pass `50/50`; full frontend Vitest passes `625/625`
across 90 files, type-check and production build pass, and rebuilt authenticated F8y passes `1/1`.
Acceptance flexibility used: none.

## Current continuation checkpoint — 2026-08-10T11:00:00Z

EasyScan result history now uses a shared per-scan Vue Query key with short freshness, and a
completed run invalidates that key before loading retained history. Existing queued/cancellation
behavior is preserved. Focused EasyScan tests pass `9/9`; full frontend Vitest passes `625/625`
across 90 files, type-check and production build pass, and rebuilt authenticated F9h passes `1/1`.
Acceptance flexibility used: none.

## Current continuation checkpoint — 2026-08-10T10:30:00Z

EasyScan saved-condition hydration now uses the shared Vue Query library key
`['workstation', 'library-items', 'condition']`; condition saves update and invalidate that cache.
Two linked EasyScan roots deduplicate the library request. Focused EasyScan coverage passes `9/9`;
full frontend Vitest passes `625/625` across 90 files, type-check and production build pass, and
rebuilt authenticated F9h passes `1/1`. Acceptance flexibility used: none.

## Current continuation checkpoint — 2026-08-10T10:00:00Z

RelativeRotationTool now preserves and exposes backend row-level coverage/insufficient-history
warnings in the dense companion table, with tooltips for the exact diagnostic message. Focused
rotation coverage passes `6/6`; full frontend Vitest passes `624/624` across 90 files, type-check
and production build pass, and rebuilt authenticated F8e passes `1/1`. Acceptance flexibility used:
none.

## Current continuation checkpoint — 2026-08-10T09:00:00Z

Canonical instrument resolution is now factored into the reusable
`fetchCanonicalInstrument` query contract, so workstation orchestration and future tool surfaces
share one normalized identity/cache implementation. Contract tests pass `2/2`; full frontend
Vitest passes `623/623` across 90 files, type-check and production build pass, and rebuilt
authenticated F8e passes `1/1`. Acceptance flexibility used: none.

## Current continuation checkpoint — 2026-08-10T08:30:00Z

Canonical instrument resolution for isolated workstation tools now uses the shared query contract
`['workstation', 'instrument', normalizedSymbol]`. Concurrent linked/pop-out lookups deduplicate,
symbol normalization is explicit, and existing generation guards remain in place. The new query
contract tests pass `2/2`; full frontend Vitest passes `623/623` across 90 files, type-check and
production build pass, and rebuilt authenticated F8e passes `1/1`. Acceptance flexibility used:
none.

## Current continuation checkpoint — 2026-08-10T08:00:00Z

RatioUPlot now coordinates each relative-strength leg through shared Vue Query keys containing
the canonical numerator, benchmark, timeframe, as-of cutoff, and adjustment mode. Timestamp
intersection, visibility suspension, late-response guards, and uPlot reuse remain intact. The
focused ratio suite passes `9/9`; full frontend Vitest passes `621/621` across 89 files, type-check
and production build pass, and rebuilt authenticated F8e passes `1/1`. Acceptance flexibility used:
none.

## Current continuation checkpoint — 2026-08-10T07:30:00Z

RelativeRotationTool now coordinates identical group/benchmark/timeframe/parameter requests
through shared Vue Query keys while retaining its uPlot instance and load-generation guards.
The focused rotation suite passes `5/5`; full frontend Vitest passes `620/620` across 89 files,
type-check and production build pass, and rebuilt authenticated F8e passes `1/1`. Acceptance
flexibility used: none.

## Current continuation checkpoint — 2026-08-10T07:00:00Z

CoverageSummaryTool now coordinates canonical instrument coverage and parameterized OHLCV-range
assessments through shared Vue Query keys, preventing duplicate reads across linked windows while
retaining request-generation guards. Focused coverage tests pass `4/4`; full frontend Vitest
passes `619/619` across 89 files, type-check and production build pass, and rebuilt authenticated
F8i-d passes `1/1`. Acceptance flexibility used: none.

## Current continuation checkpoint — 2026-08-10T06:30:00Z

Instrument-note hydration now uses the shared Vue Query key `['workstation', 'instrument-note',
instrumentId]`; autosaves update that cache so linked windows share the newest persisted note.
The linked-note race and two-root deduplication tests pass; full frontend Vitest passes `618/618`
across 89 files, type-check and production build pass, and rebuilt authenticated F8s passes `1/1`.
Acceptance flexibility used: none.

## Current continuation checkpoint — 2026-08-10T06:00:00Z

Instrument-alert hydration now uses shared Vue Query entries for global screener alerts and
instrument price, indicator, screener, and firing-history bundles. Alert mutations invalidate the
shared alert root after applying their local optimistic view update. A two-root deduplication
regression and existing stale-relink/mutation tests pass; full frontend Vitest passes `617/617`
across 89 files, type-check and production build pass, and rebuilt authenticated F11 passes
`1/1`. Acceptance flexibility used: none.

## Current continuation checkpoint — 2026-08-10T05:30:00Z

Combo-list hydration in personal workstation tools now uses the shared Vue Query key
`['workstation', 'library-items', 'combo_list']`; save/delete mutations invalidate that result.
Full frontend Vitest passes `616/616` across 89 files, type-check and production rebuild pass,
and rebuilt authenticated F8y passes `1/1`. Acceptance flexibility used: none.

## Current continuation checkpoint — 2026-08-10T05:00:00Z

Chart-template hydration now uses the shared Vue Query key
`['workstation', 'library-items', 'chart_template']` across chart windows. Save/delete operations
invalidate and reload the shared result, preventing stale template menus in linked or popped-out
charts. The two-root regression passes, full frontend Vitest passes `616/616` across 89 files,
type-check and production rebuild pass, and rebuilt authenticated F9c passes `1/1`. Acceptance
flexibility used: none.

## Current continuation checkpoint — 2026-08-10T04:30:00Z

Condition-column creation in `WorkstationToolContent` now resolves existing screeners through the
shared `['workstation', 'screeners']` Vue Query contract and invalidates it after creating/running
the Boolean scan. This keeps Market Gauge, watchlists, and condition-column creation coherent
across mounted tools. Full frontend Vitest remains `615/615` across 89 files, type-check and
production rebuild pass, and rebuilt authenticated F8v passes `1/1`. Acceptance flexibility used:
none.

## Current continuation checkpoint — 2026-08-10T04:10:00Z

Unified Python asset hydration now uses one Vue Query contract (`['workstation', 'code-assets']`)
across EasyScan, virtual watchlists, chart plot libraries, and the Python library. Asset mutations
invalidate the shared result; concurrent hydration and post-invalidation refetch are regression-
covered. During rebuilt F8y validation, a real localized membership race was exposed: a stale
watchlist-level source identity disabled a valid target option. The context-row source identity
now takes precedence, with a focused regression. Full frontend Vitest passes `615/615` across 89
files, `vue-tsc --noEmit` passes, production rebuild passes, and rebuilt authenticated F8y passes
`1/1`. Acceptance flexibility used: none; the transient F8y failure was fixed under the goal-level
tie-break rule and remains documented with its reproduction and evidence.

## Current continuation checkpoint — 2026-08-10T03:40:00Z

Extended the shared Vue Query coordination to saved column sets in `VirtualWatchlistTool`.
Docked and popped-out roots now deduplicate `/workspaces/library/items?kind=column_set`, while
save/delete mutations invalidate and reload the shared result. The two-root regression passes,
the focused VirtualWatchlist suite passes `49/49`, the full frontend Vitest suite passes `613/613`
across 88 files, `vue-tsc --noEmit` passes, and rebuilt authenticated Chromium F8y passes `1/1`.
No acceptance flexibility was used; remaining external and unrepresented visual gaps stay tracked.

## Current continuation checkpoint — 2026-08-10T03:20:00Z

Closed a shared-state efficiency gap in `VirtualWatchlistTool`: saved-screener hydration now
uses the shared Vue Query key `['workstation', 'screeners']`, so docked and popped-out
watchlist roots deduplicate the identical `/screeners` request while preserving the existing
EasyScan invalidation contract. The two-root regression passes, the focused VirtualWatchlist
suite passes `48/48`, the full frontend Vitest suite passes `612/612` across 88 files,
`vue-tsc --noEmit` passes, and the rebuilt authenticated Chromium F8y workstation check passes
`1/1`. No acceptance flexibility was used. Remaining visual,
live-provider, native multi-monitor, and beyond-bounded-endurance gaps remain explicitly
tracked rather than treated as blockers for this localized correction.

## Current continuation checkpoint — 2026-08-10T03:00:00Z

Removed a duplicate `RatioUPlot` reload watcher that issued two identical relative-strength
requests whenever a linked symbol or timeframe changed. The exact request-count regression passes,
the focused ratio suite passes `8/8`, full frontend Vitest remains `611/611`, type-check passes,
and rebuilt authenticated F8e passes `1/1`. No acceptance flexibility was used.

## Current continuation checkpoint — 2026-08-10T02:45:00Z

Closed a relative-strength alignment correctness gap. `RatioUPlot` now intersects timestamps
across every requested ratio leg before constructing uPlot data, so mismatched calendars cannot
produce misleading union dates or implicit gap bridges. The new mismatch regression passes, the
full frontend Vitest suite is `611/611`, `vue-tsc --noEmit` passes, rebuilt authenticated F8e
passes `1/1`, and the four-environment board-guided visual matrix passes `32/32`. No acceptance
flexibility was used; exact-build/unrepresented, live-provider, physical multi-monitor, and
beyond-bounded-endurance gaps remain explicitly tracked.

## Current continuation checkpoint — 2026-08-10T02:30:00Z

Reconciled the current operational validation wording with the controlling acceptance governance:
the authenticated Chromium matrix (`63/63`) and board-guided visual matrix (`32/32`) are green,
while `required_missing` is retained only for uncovered or ambiguous visual states. The strict
manifest is not a whole-goal blocker. Historical evidence remains unchanged and no acceptance
flexibility was used.

## Acceptance governance — controlling update

`docs/tc2000-acceptance-governance.md` defines the current completion posture for the TC2000
workstation. The 190-image reference board is the accepted working visual authority for covered
states; direct exact-build captures are strengthening evidence or targeted gap closure, not a
global blocker. Live-provider, native multi-monitor, and indefinite-soak language in older audit
entries records historical evidence limits and must be read through that policy: use bounded
deterministic evidence, explicitly track the remaining gap, and report every flexibility used to
the user rather than silently treating it as complete. The applicable flexibility must be
announced before the dependent implementation or evidence run begins, then repeated in the
handoff with its open gap and closure path.

### Active-goal alignment (2026-08-08)

The active Codex goal now explicitly adopts the board-guided acceptance track. The 190-image
browsable Version 25 reference board is the visual working authority wherever it represents a
state, and the absence of a local permission-cleared exact-build capture is not a global blocker.
Unrepresented or materially ambiguous states remain named gaps with interim oracles and closure
evidence. Each time this flexibility is used it must be announced before the dependent work,
recorded in the handoff/manifest, and repeated in the user-facing update; no relaxed criterion
may be silently treated as complete.

## Current continuation checkpoint — 2026-08-08T18:30:00Z

Restored the missing deterministic visual oracles for chart provider-error and Study Lab
validation-error states. The board-guided visual suite now passes `32/32` across all four required
display environments; the manifest records all eight local baselines while both states remain
`required_missing` pending authoritative pinned-build styling evidence. Full frontend Vitest is
`601/601`, `vue-tsc --noEmit`, manifest validation, and `git diff --check` pass. This closes no
external visual gap and uses the documented board/fixture flexibility only as interim evidence.

## Current continuation checkpoint — 2026-08-08T19:15:00Z

Added the separate 125% browser page-scale robustness guard required by the workstation acceptance
plan. F8z checks shell containment, benchmark/sector visibility, tool-header separation, and
footer bounds under Chromium page scaling. The complete non-visual/performance E2E run passed
`57/57` executed tests; board-guided visual remains `32/32`. `vue-tsc --noEmit` and diff checks
pass. This adds browser-scale evidence but does not close native multi-monitor or long-duration
endurance gaps.

## Current continuation checkpoint — 2026-08-08T20:00:00Z

Added browser acceptance for workspace export/import round-tripping (F9d), covering the real
download, clone, file-picker import, and restored-layout path. The complete non-visual/performance
Playwright run passed `58/58` executed tests, including F9d and F8z; the board-guided visual suite
remains `32/32`. Type-check and repository metadata checks pass. This closes a functional evidence
gap, while native multi-monitor, beyond-bounded endurance, live-provider, and unrepresented visual
gaps remain open.

## Current continuation checkpoint — 2026-08-08T21:00:00Z

Added browser acceptance for the integrated watchlist Columns/Sets editor (F9e): grouping and
stacking a column, saving a named column set, and reapplying that set. The complete
non-visual/performance Playwright run passed `59/59` executed tests, including F9e, F9d, and F8z;
the board-guided visual suite remains `32/32`. Type-check and repository metadata checks pass.
This closes a functional watchlist-editor evidence gap; provider, hardware, endurance, and
unrepresented visual gaps remain open.

## Current continuation checkpoint — 2026-08-06T17:15:00Z

The official `npm run test:visual:board` command passes `24/24` in `1.4m` using the serialized
shared-state Playwright configuration across 1920×1080 and 2560×1440 at 100% and 125% display
scale. Manifest validation also passes. This is board-guided visual evidence with deterministic
local baselines; it does not promote any required-missing state to exact-build approval or close
the documented visual, live-provider, native-multi-monitor, or beyond-bounded-endurance gaps.

## Current continuation checkpoint — 2026-08-06T18:20:00Z

Unified Python cross-surface evidence was revalidated. Chart plot and Study Lab component tests
pass `23/23`; backend validator and factory-source tests pass `31/31`; Docker-backed screener and
Strategy Lab integration tests pass `41/41`. The typed immutable promotion adapters cover numeric
columns, plots, Boolean conditions, EasyScan, alerts, Study Lab artifacts, and Strategy signals.
The isolated runner boundary remains the sole execution path. This evidence does not close the
separate live-provider, native-multi-monitor, beyond-bounded-endurance, or unrepresented-visual
gaps.

## Current continuation checkpoint — 2026-08-06T18:35:00Z

Reconciled durable operational state with the controlling acceptance governance. `ops/tasks.yaml`
and the current `ops/state.json` visual record now explicitly distinguish the active board-guided
visual track from the stronger exact-build audit. Represented states are not blocked by absent
local exact-build captures; unrepresented or ambiguous states remain named, actionable gaps.

## Current continuation checkpoint — 2026-08-06T21:05:00Z

Closed the compatible single-output unified-Python version-reuse gap. Study Lab runs now retain
their immutable `code_version_id`; scalar, series, Boolean, and event outputs can be consumed
directly by compatible chart, column, EasyScan, alert, and Strategy-signal surfaces without
copying source into a second typed asset. Frontend regression is `69/69`, Docker-backed
screener/Strategy integration is `43/43`, and `vue-tsc --noEmit` passes.

## Current continuation checkpoint — 2026-08-06T20:07:24Z

Revalidated the unified-Python contract after constraining Study Lab asset creation to the
persisted `scalar`, `series`, `boolean`, and `events` contracts for direct reuse; structured
and multi-output programs correctly persist as `study`. The complete frontend Vitest suite is
`592/592`, the Study Lab component suite is `15/15`, `vue-tsc --noEmit` passes, and `git diff
--check` is clean. At this checkpoint structured multi-output promotion remained adapter-based;
the later `20:18:00Z` checkpoint below supersedes that gap with named immutable output adapters.

## Current continuation checkpoint — 2026-08-06T20:18:00Z

Closed the named structured-output promotion gap. `CodeVersion.output_name` is persisted through
Alembic `eb1f2a3c4d5e`, validated against the declared output contract, included in research job
manifests, and enforced by the isolated runner. Study Lab now exposes named promotion controls
for scalar columns, series plots, Boolean scans/alerts, and event signals from multi-output runs.
The Docker-backed code API suite passes `18/18`; runner, job, and validator unit tests pass `94/94`
(the narrow command reports only its expected coverage-threshold exit); frontend focused tests
pass `20/20` with TypeScript clean. This closes the previous direct-binding gap through an
immutable named adapter while preserving the single-output direct-reuse path.

## Current continuation checkpoint — 2026-08-06T20:20:50Z

Revalidated the structured-output promotion implementation after suppressing duplicate promotion
controls for compatible single-output runs. The full frontend Vitest suite passes `593/593`;
`vue-tsc --noEmit`, the production Vite build, Alembic head validation (`eb1f2a3c4d5e`), Python
bytecode compilation, and `git diff --check` all pass. No new acceptance flexibility was used;
board-guided visual, live-provider, native multi-monitor, and beyond-bounded-endurance gaps remain
explicit.

## Current continuation checkpoint — 2026-08-06T20:24:55Z

Applied the named structured-output migration to the retained branch Docker stack after rebuilding
the backend, worker, and isolated runner. Live PostgreSQL now reports Alembic head
`eb1f2a3c4d5e`, and the rebuilt backend health check is green. This is Docker-backed branch-stack
evidence, not live-provider evidence; provider, hardware, endurance, and unrepresented visual
gaps remain explicitly tracked.

## Current continuation checkpoint — 2026-08-06T20:29:00Z

The complete combined backend unit/integration gate passed `1,275/1,275` in `239.27s` at
`79.41%` coverage after the live structured-output migration. The 75% threshold is satisfied;
only 86 known third-party deprecation warnings were emitted. This is Docker-backed branch-stack
evidence and does not close live-provider, hardware, endurance, or unrepresented visual gaps.

## Current continuation checkpoint — 2026-08-06T20:32:49Z

The official `npm run test:visual:board` initially exposed a stale Nginx upstream after the
backend container was rebuilt; all 24 cases failed before page assertions with HTTP 502 during
E2E-user provisioning. Restarting only the retained branch frontend refreshed the upstream and
the complete serialized visual matrix then passed `24/24` in `1.3m`, including screenshot and
gap-state comparisons across all four required display environments. Board-guided/fixture/browser
flexibility was used and remains recorded; exact-build/unrepresented, live-provider, native
multi-monitor, and beyond-bounded-endurance gaps remain explicit.

## Current continuation checkpoint — 2026-08-06T20:36:00Z

Re-ran the complete `npm run test:e2e` suite after the branch backend rebuild and frontend
upstream refresh. `51` authenticated/non-visual/performance tests passed in `3.0m`; the 24 visual
cases are intentionally guarded and passed separately through the official board command. No new
browser or cross-surface regression appeared. Board-guided visual/browser flexibility remains
explicit; exact-build/unrepresented, live-provider, native multi-monitor, and beyond-bounded-
endurance gaps remain open.

## Current continuation checkpoint — 2026-08-06T20:42:00Z

Closed the previously stale combo-list persistence note. The targeted Docker-backed Python 3.12
workspace regression now passes `1/1`, preserving canonical union, intersection, exclusion, and
dependency metadata through the library API. Remaining combo-list work is browser/visual parity;
no live-provider or exact-build visual evidence was used.

## Current continuation checkpoint — 2026-08-06T20:10:09Z

Closed a research-observability gap: Study Lab and persisted Research Results now expose
structured diagnostics, warnings, execution logs, and resource usage returned by the canonical
research API. The full frontend suite passes `593/593`, including the new persisted-run health
surface regression; `vue-tsc --noEmit` and `git diff --check` remain clean.

The new run-health sections use the same dense tool-window language as the workstation and are
bounded with collapsible panels so logs and diagnostics cannot overlap result headers or charts.
Focused Study Lab/Research Results tests remain `20/20`; the frontend production build also passes.

## Current continuation checkpoint — 2026-08-07T17:00:00Z

Added four-environment deterministic local visual baselines for stale freshness and partial
technical coverage. The board-guided matrix passes `24/24` with elevated Playwright; both states
remain `required_missing` in the manifest because the baselines establish deterministic layout
and status rendering, not exact Version 25 reference approval. The manifest unit suite passes
`8/8` and the non-strict manifest validator remains green.

## Current continuation checkpoint — 2026-08-07T18:00:00Z

Added a four-environment deterministic chart provider-error baseline. The complete board-guided
visual matrix now passes `28/28`; the chart error state remains `required_missing` and its local
screenshots are explicitly interim evidence only.

## Current continuation checkpoint — 2026-08-07T19:00:00Z

The full frontend Vitest suite remains green at `592/592` across 88 files after the visual
baseline additions. The existing 10,000-row virtual-watchlist invariant remains covered: the
component exposes all 10,000 logical rows while rendering fewer than 100 DOM rows and preserving
the virtual total height.

## Current continuation checkpoint — 2026-08-07T22:00:00Z

The focused stale/partial visual gap suite passes `8/8` with one worker. A subsequent four-worker
full matrix run produced `12/24` because shared backend requests returned `Unavailable`/`Fetching`
before the mocked freshness responses were applied; this is recorded as an environment-contended
run and does not replace the earlier successful `24/24` evidence. The affected harness condition
must be revalidated before the visual matrix is next presented as current.

## Current continuation checkpoint — 2026-08-07T23:00:00Z

Playwright visual projects now default to one worker because all four display-scale projects share
the authenticated workspace and backend database. The serialized board-guided matrix passes
`24/24` in `2.7m`; `PLAYWRIGHT_WORKERS` remains an explicit override for isolated environments,
not the shared-state acceptance default.

## Current continuation checkpoint — 2026-08-08T00:00:00Z

The Playwright worker override now validates `PLAYWRIGHT_WORKERS` as a positive integer and falls
back to the serialized default for malformed values. `vue-tsc --noEmit`, Playwright test
discovery with an invalid override, and `git diff --check` pass.

## Current continuation checkpoint — 2026-08-08T01:00:00Z

The complete backend unit suite passes `991/991` in `56.18s` with 34 known third-party
deprecation warnings and no project test failures. This revalidates the manifest, provider,
security-master, research-runner, sandbox-contract, and workstation backend unit surfaces after
the latest acceptance-harness changes.

## Current continuation checkpoint — 2026-08-08T02:00:00Z

The complete frontend Vitest suite passes `592/592` across 88 files in `22.09s`; `vue-tsc
--noEmit` and `git diff --check` also pass. The only test stderr is intentional conflict-path
logging covered by the watchlist-store tests.

## Current continuation checkpoint — 2026-08-08T03:00:00Z

Reconciled `docs/tc2000-parity.md` with the controlling acceptance governance. Board-guided
surfaces now report their deterministic functional/visual status instead of blanket `Blocked`;
unrepresented and ambiguous states remain explicit manifest gaps. No exact-build approval or gap
closure was implied by this documentation update.

## Current continuation checkpoint — 2026-08-08T04:00:00Z

Added a current evidence snapshot to `docs/tc2000-parity.md`, consolidating backend `991/991`,
frontend `592/592`, serialized board-guided visual `24/24`, and the 10,000-row virtualization
invariant. The remaining external and unrepresented-state gaps remain explicitly listed.

## Current continuation checkpoint — 2026-08-08T05:00:00Z

The official `npm run test:visual:board` command passes end-to-end: manifest validation plus the
serialized four-environment board-guided matrix completes `24/24` in `1.5m`.

## Current continuation checkpoint — 2026-08-08T06:00:00Z

The complete `npm run test:e2e` acceptance command passes `51` authenticated/non-visual and
performance tests in `2.6m`; 24 visual-project cases are intentionally skipped because the board
visual suite requires its explicit environment flag and is independently green at `24/24`.

## Current continuation checkpoint — 2026-08-08T07:00:00Z

The official `make test-backend-coverage` gate passes `1,272/1,272` unit and integration tests in
`4m55.58s` at `79.41%` coverage, above the required 75%. The run produced 86 known dependency
warnings and no project test failures.

## Current continuation checkpoint — 2026-08-08T08:00:00Z

The production frontend build passes: `npm run build` completes TypeScript validation and Vite
production bundling in `12.29s`; `git diff --check` also passes.

## Current continuation checkpoint — 2026-08-08T09:00:00Z

Extended the parity current-evidence snapshot with the combined backend coverage gate
(`1,272/1,272`, `79.41%`), authenticated E2E (`51` passed), and production frontend build
evidence.

## Current continuation checkpoint — 2026-08-06T23:00:00Z

The complete backend matrix now passes with authorised Docker access: `1,270 passed`, `348
skipped`, and `86` deprecation warnings. The dedicated Docker-backed integration slice is
`281/281`; the remaining skips are configured live-provider probes and other explicitly opt-in
checks. This closes the previously environment-blocked backend integration evidence. Strict
Version 25 approval for unrepresented states, configured live-provider probes, native
multi-monitor placement, and endurance beyond bounded stress remain separate documented gaps.

## Current continuation checkpoint — 2026-08-07T01:45:00Z

The complete authenticated Chromium flow matrix now passes `48/48` after repairing canonical
benchmark deep-link hydration: route entry no longer depends on a transient metadata-search
response to populate the active symbol. The focused five-test regression slice also passes
`5/5`. Backend remains green at `1,270 passed, 348 skipped`; board-guided visual acceptance
remains `8/8`. The remaining documented gaps are limited to unrepresented visual states, opt-in
live-provider probes, native multi-monitor placement, and endurance beyond bounded stress.

## Current continuation checkpoint — 2026-08-07T04:30:00Z

The bounded performance matrix passes `3/3` with 100 pop-out churn rounds, including the
100,000-point uPlot interaction guard and multi-window lifecycle/heap checks. This satisfies the
governed bounded-performance evidence requirement. Indefinite endurance and native physical
multi-monitor behavior remain separate documented gaps.

## Current continuation checkpoint — 2026-08-07T06:00:00Z

The board-guided visual matrix now passes `12/12`, adding deterministic four-environment loading
state baselines. Loading remains a visual-manifest gap because no authoritative V25 loading capture
exists; the baselines narrow the implementation uncertainty without promoting the state to exact
TC2000 approval. Provider-error remains covered functionally by `F8i-a`.

## Current continuation checkpoint — 2026-08-07T07:00:00Z

The board-guided visual matrix now passes `16/16`, adding four-environment deterministic
blocked-pop-out recovery baselines. The state remains a manifest gap without authoritative V25
reference media; the baseline and `F8k-a` behavior test narrow, but do not erase, that gap.

## Current continuation checkpoint — 2026-08-07T11:00:00Z

The live branch-scoped research-runner probes are green: all eight sandbox escape attempts denied,
resource-pressure containment passed with unchanged restart count, orphan recovery completed, and
the sustained bounded cancellation probe passed `5/5` rounds. This closes the bounded sandbox,
resource, cancellation, and recovery evidence. Indefinite soak remains explicitly separate.

## Historical continuation checkpoint — 2026-08-06T07:00:00Z

The top-down analysis has direct unit coverage for its explicit industry-proxy registry, async
taxonomy seeding, and relative-rotation/point-in-time helper edge cases. The analysis helper suite
passes `12/12`, while the taxonomy suite passes `2/2`. The idempotence test verifies that all known
benchmark and sector proxy instruments are attached once with source/verification provenance and
that the SPX identity remains explicitly paired with SPY as the default tradable proxy. The full
backend unit suite passes `981/981` with `69.93%` coverage. The combined backend coverage gate
passes at `79.41%`; the unit-only slice remains separately reported at `69.90%`. Strict Version 25
visual approval, configured provider-live probes, sustained sandbox/resource stress, native
multi-monitor evidence, and the remaining cross-surface parity gates remain open.

The latest Chromium workstation performance run completed both guards twice with
`TC2000_POP_OUT_CHURN_ROUNDS=100`: `2/2` passed per run, including repeated simultaneous pop-out
lifecycle churn, bounded source tool/canvas/chart counts, and available heap ceilings.
The user-requested `docker system prune -af` cleanup reclaimed `7.319GB`; active branch services
remained healthy. Native multi-monitor placement and genuinely indefinite soak remain separate
acceptance gates.

The post-soak authenticated flow audit found and repaired one real interaction race: pressing
Enter in the active-symbol search (or using Go) could leave a stale autocomplete listbox mounted
over the workstation while the input remained focused, allowing it to intercept the next sector
or tool click. Explicit selection now closes and invalidates autocomplete before dispatching the
canonical symbol; Escape and mouse option selection use the same path. The focused F8m check passes
`1/1`; the remaining authenticated-flow tests were re-run in bounded partitions after the fix
(`35` pre-study/core/legacy tests and `7` Study Lab/notes tests passed), with no new application
failures. This closes the autocomplete regression only; it does not change the strict visual,
provider-live, native multi-monitor, sustained sandbox, or indefinite-soak gates.

The regression is now covered at the component level as well: the workstation shell test suite
asserts that Enter, Escape, mouse option selection, and the explicit Go action all remove the
autocomplete listbox while the search input remains focused. The focused suite passes `10/10`,
and the full frontend coverage run remains green with function coverage increased to `71.4%`.

The live sandbox resource probe also received a correctness repair. Its earlier nominal 1 GiB
allocation could remain below the effective resident-memory limit on this host and falsely report
success. The probe now faults in every page of a 2 GiB allocation and uses resident 256 MiB
allocations for the concurrent-pressure check. The corrected live run reports cgroup exit 137,
tmpfs `ENOSPC`, three contained concurrent failures, and unchanged runner restart count. The
deployment contract suite passes `6/6`; sustained cancellation/crash/resource stress remains a
separate broader gate.

The visible-list audit found a second concrete issue: Golden Layout could leave a mounted
virtualized watchlist using its one-row detached fallback even after its panel became visible.
`VirtualWatchlistTool` now re-measures on mount and on two animation frames, and the seeded visual
harness asserts that all five benchmark and eleven sector rows have distinct, non-overlapping
geometry before capture. The top-down F8d/F8e browser checks pass `2/2`; exact-build visual
comparison remains blocked only by the unapproved reference baselines, not by row geometry.

After that change, the complete frontend Vitest suite passes `578/578` across 87 files. The only
stderr remains the intentionally exercised watchlist conflict-path logging.

The isolated-runner orphan-recovery probe was rerun after the resource-probe correction and again
completed a claimed job after terminating/restarting only the research-runner, with no stale cancel
or progress artifacts. This remains bounded recovery evidence; the broader sustained stress matrix
is still required.

The Golden Layout host now has direct component regression coverage for virtual-tool installation,
serialised state-change emission, layout replacement, fingerprint-stable updates, and teardown.
The focused host suite passes `2/2`; the full frontend suite is `580/580` across 88 files and
`vue-tsc --noEmit` remains green. This strengthens lifecycle evidence without changing the
strict visual, provider-live, sustained-stress, multi-monitor, or indefinite-soak gates.

The next rebuilt-stack audit found two further persistence/lifecycle races. Virtual workstation
tools now keep a local link-group state while the native selector and parent workspace reconcile,
and Grey isolation records the displayed symbol plus a short-lived remote-snapshot override so an
in-flight save cannot restore the shared group. Study Lab now caches and hydrates its durable run,
persists the run source/contract in tool configuration, and continues polling queued/running jobs
even when Golden Layout briefly reports the tool outside the viewport. The full frontend suite is
`584/584` across 88 files, `vue-tsc --noEmit` passes, and isolated rebuilt-stack F8g, F8m, F8o, and
F8p checks pass. A complete 42-case browser run reached `41/42`; the sole F8p miss was a transient
browser-process permission failure and a privileged isolated rerun passed `1/1`. This is stronger
functional evidence, not completion: exact-build V25 visual approval, provider-live coverage,
sustained sandbox/resource stress, native multi-monitor placement, indefinite soak, and remaining
cross-surface parity gates stay open.

The subsequent acceptance audit ran the complete authenticated Chromium matrix with browser
process permissions and closed the prior environmental ambiguity: all `42/42` flow cases passed,
including Study Lab, linked-group isolation, timeframe propagation, pop-out recovery, notes, and
legacy compatibility. The backend unit suite initially exposed one stale assertion that still
expected implicit yfinance ordering; the test now explicitly opts into the legacy fallback while
the default workstation policy remains yfinance-free. The complete backend unit suite then passed
`983/983` with `69.91%` coverage. The strict visual command still fails closed at
`application-shell-default/default: required_missing`; no discovery screenshot was promoted.

The Docker-backed integration bodies also pass in full (`281/281`). Its standalone coverage
command exits non-zero only because it measures integration files in isolation and therefore falls
below the repository threshold; the authoritative combined unit+integration gate passes
`1264/1264` at `79.43%`, above the required 75%. This confirms the API/runtime paths against the
real PostgreSQL/Redis-backed test environment without weakening the documented coverage gate.

The live branch research-runner probes were rerun against the active Docker service: namespace,
mount, ptrace, fork, network, subprocess, and root-write attempts were denied; resident 2 GiB
pressure was cgroup-killed with status 137; the 70 MiB tmpfs write returned ENOSPC; three of eight
concurrent pressure workers were contained without a runner restart; and a claimed job completed
after an isolated runner restart with no stale sentinels. Ruff now passes the complete backend
application/test tree. These are bounded containment and recovery results; sustained stress,
long-running research responsiveness, and indefinite soak remain open.

The full authenticated browser sequence then exposed an order-dependent workspace race: stale
remote snapshots or pre-reset Golden Layout saves could restore a shared link group after the user
selected Grey, while a stale autocomplete listbox could intercept the next sector click. Search
visibility is now reactive and closes on outside pointer/focus/change capture; reset invalidates and
drains pending snapshots; remote workspace events no longer replace locally dirty state before its
revisioned save/merge path runs. The component/store regressions cover these contracts, the rebuilt
stack full flow passes `42/42`, and the full frontend suite passes `582/582` across 88 files.

The current branch runner was re-probed after the workspace changes. Namespace, mount, ptrace,
fork, network, subprocess, and root-write attempts remain denied; the 2 GiB resident allocation
is cgroup-killed, the 70 MiB tmpfs write returns ENOSPC, and concurrent pressure contains three
child failures without a runner restart. A claimed shared-volume job also completed after an
explicit runner restart with no stale cancellation/progress residue. This refreshes bounded
containment/recovery evidence but does not satisfy sustained or indefinite stress acceptance.

The provider runtime now enforces the documented yfinance boundary: the adapter remains registered
for explicit legacy compatibility, but default price/history/event/universe chains exclude it unless
`ENABLE_LEGACY_YFINANCE_FALLBACK=true` is deliberately configured. The backend image was rebuilt
and is healthy; focused provider-runtime/registry coverage passes `19/19`. This removes implicit
yfinance dependence from new workstation paths while preserving an auditable opt-in fallback.

The rebuilt frontend then received two interaction hardenings found by browser repetition: a Grey
link switch now captures the tool's displayed symbol through the component boundary and local
publication state, and Ctrl+wheel traversal is handled at workstation/window scope with a canonical
fallback universe when hydration is incomplete. Focused F8m passes `3/3`, focused traversal passes
`3/3`, the workstation binding suite passes `11/11`, and the full frontend suite remains green at
`582/582` after the final source changes. These close the observed races without changing the
strict visual, provider-live, sustained-stress, multi-monitor, or indefinite-soak gates.

Provider-route rechecks and the subsequent SEC-fallback repair leave three external issuer-route
failures: Davis 522, Anfield ADFI 404, and Donoghue Forlines 503. The targeted matrix is now
`285 passed, 1 skipped, 3 failed` with no route suppressed or promoted without deterministic/live
identity evidence; configured SEC identifiers can use the independent fallback path.

The 2026-08-05T22:15:00Z visual-harness audit temporarily enabled the deterministic E2E market
fixture and exercised all four required display environments. The current workstation rendered
seeded data, but the preserved untracked Playwright snapshots are stale failure-state artifacts;
three environments therefore differ from those snapshots. The backend was restored afterward,
and no snapshot was rewritten or treated as an approved V25 reference. The strict manifest gate
continues to fail closed at `application-shell-default/default: required_missing`.

The workstation performance guard now supports bounded long-soak execution through
`TC2000_POP_OUT_CHURN_ROUNDS` (capped at 100), samples Chromium heap usage after every churn
round, and checks both absolute and relative heap ceilings. The extended 100-round/two-popout
run passed twice, as did both workstation performance tests (`2/2`); broader OS-level
multi-monitor placement remains separate.

Added browser-level recovery coverage for a disconnected/externally closed pop-out: the source
workspace must retain the tool, allow it to be floated again in the same session, and close the
reopened window cleanly. The complete authenticated flow suite passed `35/35` after this change.

The link-group audit then exposed and fixed a real isolation defect: moving a shared tool to Grey
now persists its currently displayed symbol before detaching it from the shared bus. Browser
coverage proves Grey remains unchanged while Yellow follows subsequent linked selections. The
complete authenticated flow suite now passes `36/36`, with frontend type-check passing.

The browser acceptance harness now treats logout's in-flight 401 responses as an explicit,
bounded auth-boundary contract; unrelated unauthorized responses remain failures. Focused F5
and the complete rebuilt-stack Chromium acceptance pass `37/37`.

The targeted sandbox/resource and code API acceptance slice passes `112/112` with Docker
access. Broader multi-process namespace/resource stress remains an explicit open gate.

The live branch-runner probe now also exercises process creation: unshare, setns, mount, ptrace,
fork, network, subprocess, and root-write attempts are denied under the deployed policy. This is
stronger runtime evidence, but it does not by itself close the broader multi-process/resource stress
gate.

OHLCV request fan-out is now bounded across linked chart surfaces: chart-store, workstation,
comparison, and legacy chart reads share a short-lived canonical coordinator with immediate
failure eviction. Full frontend Vitest is `576/576`, and rebuilt Chromium workstation
acceptance now passes `37/37`, including hidden-refresh suspension, five rounds of two-popout
churn with settled tool/canvas/chart counts, and clean diagnostics. Remaining performance work is broader
multi-monitor/memory/polling evidence rather than identical-request duplication.

- Workstation freshness presentation now uses the canonical technical-analysis freshness
  contract and has exhaustive state mapping coverage (`565/565` frontend tests, TypeScript,
  production build, rebuilt Chromium `29/29`). The old timestamp-derived `Cached` shell state
  was removed because it could imply freshness the backend had not established.
- The current local audit also passes the full frontend Vitest suite (`576/576`) and full backend
  unit suite (`988/988`), with only the documented third-party deprecation warnings.
- Fresh Docker-backed backend integration also passes `281/281` in `164.63s`; branch-scoped
  services remained healthy and the post-run backend/worker/research-runner log audit found no
  unexpected error, traceback, connection-leak, or provider-runtime output.
- Remaining completion gates are governed by `docs/tc2000-acceptance-governance.md`: all
  in-scope functional and deterministic acceptance must pass; unrepresented visual states,
  configured live-provider probes, native physical multi-monitor behavior, and endurance beyond
  bounded stress remain explicit actionable gaps. Exact-build approval is targeted strengthening
  evidence, not a global gate, and must not be represented as completed when absent.

This file is the persistent deferred-work memory for the charting platform.

Purpose:
- Keep track of work that we explicitly chose to postpone.
- Preserve the surrounding context so a later pass does not lose the rationale.
- Act as the canonical place I should consult when you ask "what is still on the TODO list?"

Maintenance rules:
- When you ask to add something to the TODOs, I should add it here with context.
- When we fully solve one of these items, I should remove it from this file.
- If a TODO meaningfully changes shape, I should update the existing entry instead of duplicating it.
- This file is only for deferred or future work, not for work actively underway in the current turn.
- If another prompt, note, or agent hint disagrees with this file, prefer this file unless the user explicitly says otherwise.

Interpretation rules:
- Treat each entry as deferred work that was explicitly discussed and intentionally postponed.
- Do not use this file for the task currently in progress, vague brainstorming, or already completed work.
- Keep enough context that future sessions can understand why the item exists.
- Prefer updating an existing entry over creating a duplicate if the topic is the same.

Status legend:
- `Deferred`: explicitly postponed for later
- `Planned`: agreed future work that has not started yet

## Deferred TODOs

### 1. Expand test coverage further
Status: `Partially resolved — backend 75% gate restored; frontend coverage remains deferred`

Context:
- We stabilized the broken backend and frontend suites and got them green again.
- Measured coverage is still uneven: the backend unit-only slice is `69.93%`, while the combined
  unit plus Docker-backed integration gate now reaches `79.59%`.
- Frontend lines/statements/branches are strong, but function coverage remains the main weak point.

What remains:
- Raise frontend function coverage, especially around:
  - stores
  - composables
  - uPlot plugins
  - chart rendering helpers
- Raise backend coverage in currently under-covered routers/services/providers, especially:
  - core instrument and OHLCV flows
  - dashboard-facing routers
  - watchlist/provider/options routers
  - provider adapters and ingestion-heavy services
  - alerting, screener, sync/task, and background workflow paths
- Add broader integration and end-to-end coverage where unit coverage alone leaves behavioral gaps.

The backend target is now enforced by `make test-backend-coverage`, which runs the complete unit and
integration suites together with `--cov-fail-under=75`. Remaining coverage work is frontend-focused
and does not reopen the restored backend gate.

### 2. Enrich options navigation and contract-history UX
Status: `Deferred`

Context:
- Options contracts are now treated as proper instruments and can be opened in the main chart flow.
- The current options-chain interaction is still functional-but-basic.
- We explicitly agreed to think about deeper options navigation later.

What remains:
- Improve navigation from options chain to contract history.
- Decide whether to add:
  - quick-chart preview
  - split-pane contract chart
  - side drawer / modal inspection
  - better dashboard/widget-side inspection flow
- Make options exploration feel more fluid in both `/chart` and dashboard contexts.

Why this was deferred:
- The current path works, but the UX can be substantially better and deserves a focused design pass.

### 3. Add instrument/asset-type targeting controls for screeners and similar universe consumers
Status: `Deferred`

Context:
- Options contracts can currently participate in broader instrument workflows if present in the DB.
- This is not inherently wrong, but we agreed the platform should let users deliberately decide what kinds of instruments a screener or similar flow should target.

What remains:
- Add explicit include/exclude targeting for instrument classes, such as:
  - equities
  - ETFs
  - indices
  - forex
  - futures
  - options
  - crypto
  - synthetics
- Review whether similar filtering should exist in:
  - screeners
  - search/browse/discovery
  - any other "evaluate many instruments" workflows

Why this was deferred:
- The underlying behavior is acceptable for now, but targeted control is important before the universe grows further.

### 4. Extend provider-side options data support beyond the current baseline
Status: `Deferred`

Context:
- We agreed to squeeze as much practical value as possible out of current providers for options.
- The architecture is ready for full options timeseries.
- Current provider support is still limited in what it can truly deliver historically.

What remains:
- Push option contract OHLCV/history further where current providers allow it.
- Later support true historical timeseries for:
  - bid
  - ask
  - open interest
  - implied volatility
  - greeks
- Keep treating these as time-series data, even when a provider only gives snapshots at specific times.

Why this was deferred:
- The storage and provider-agnostic model came first.
- Richer provider capability work belongs in a dedicated follow-up pass.

### 5. Expand the Technical Radar / Level-of-Interest engine beyond the new v1 foundation
Status: `Deferred`

Context:
- We want the platform to automate a large part of the manual chart-scanning and level-finding work typically done by experienced technical analysts.
- The goal is not merely to label an instrument as "interesting", but to identify instruments approaching technically meaningful areas and explain why they are on the radar.
- The user explicitly wants this to be exhaustive up front: include a broad set of technical ideas and confluence mechanisms now, then later validate and prune what proves useful.
- The user also wants visual transparency: if the radar flags an instrument because of zones, wedges, channels, anchored VWAPs, moving averages, or other structures, the platform should let the user visually inspect those exact internal detections on charts.
- A first implementation pass now exists:
  - persisted `radar_run` / `radar_detection` records
  - a synchronous/manual scan trigger
  - a dedicated `/radar` page
  - a non-editable chart-side radar evidence layer separate from saved drawings
  - thread-aware continuity/history via persisted `radar_setup_thread` records
  - chart-side radar selection/toggling with thread context for the loaded instrument
  - the current Radar v2 baseline with:
    - persisted detection/thread state fields
    - breakout-retest / breakdown-retest families
    - action-level fields (`entry_price`, `invalidation_price`, `target_price`)
    - state-aware filtering/presentation in `/radar`
    - fakeout / failure / compression setup families
    - richer AVWAP anchor provenance plus all-time / YTD / rolling-window context
    - diagonal trendline / gap / simple pattern context
    - invalidated / resolved / stale transition persistence
    - saved radar views, instrument timelines, and a radar dashboard widget
  - initial setup types:
    - approaching support
    - approaching resistance
    - breakout
    - breakout retest
    - breakdown
    - breakdown retest
    - fakeout
    - fakedown
    - failed reclaim
    - failed breakdown recovery
    - compression support
    - compression resistance
    - reclaim
    - rejection
  - initial evidence sources:
    - clustered swing-based horizontal zones
    - anchored VWAP from recent/contextual anchors
    - EMA context
    - 52-week high/low context
    - all-time / YTD / rolling-window context
    - diagonal trendlines
    - gap zones
    - simple pattern structures
- That v1 should be treated as a foundation, not as the finished expression of the radar vision.

What this system should become:
- A broad **Technical Radar** / **Confluence Scanner** that continuously scans a very large instrument universe and produces ranked, evidence-backed technical opportunities.
- A discovery and triage layer that cuts down the human time spent manually scanning charts and searching for near-term technically interesting setups.
- A transparent system where the user can see the underlying technical structures that led to detection, not just an opaque score or alert.

Core product goals:
- Detect instruments approaching technically important price areas.
- Detect instruments interacting with support/resistance structures.
- Detect breakout, breakdown, fakeout, fakedown, reclaim, rejection, and retest behavior.
- Identify confluence between multiple structures and indicators.
- Rank and summarize instruments worthy of being placed on a daily radar/watchlist.
- Present the technical evidence visually so the user can audit and interpret the setup.

What remains:

- Strengthen the technical-structure extraction layer beyond the current v1 set, including:
  - horizontal support/resistance zones with better width/strength/merge logic
  - diagonal trendlines
  - channels
  - wedges
  - triangles
  - prior swing highs/lows
  - weekly/monthly highs and lows
  - multi-timeframe level propagation
  - opening gaps and gap boundaries
  - richer AVWAP anchor taxonomy tied to significant technical/contextual events
    - recent swing highs and swing lows
    - absolute highs/lows over the loaded history window, and later true all-time high/low anchors when sufficient history exists
    - 52-week high / 52-week low anchors when structurally relevant
    - year-to-date anchors such as YTD open, YTD high, and YTD low
    - major event anchors such as earnings gaps, large breakaway gaps, or other instrument-event timestamps when the provider stack can supply them reliably
    - optional user-auditable "anchor class" metadata so the UI can say not only that an AVWAP matters, but what kind of anchor it came from
  - explicit AVWAP anchor-selection / precedence rules so the engine can choose among multiple plausible anchors on the same symbol without becoming opaque, including:
    - when recent swing anchors outrank broader contextual anchors
    - when broader anchors (ATH/ATL, 52-week, YTD, event anchors) should dominate because they define the active market narrative
    - whether multiple AVWAPs should coexist as parallel evidence rather than forcing a single winner
    - how the chosen AVWAP anchor affects setup scoring versus merely acting as secondary confluence
  - stronger AVWAP provenance and validation, including:
    - storing the chosen AVWAP anchor timestamp and anchor type explicitly in radar evidence
    - chart-side labels/markers for the chosen anchor point
    - unit/integration coverage for obvious anchor-selection cases so the engine remains deterministic as the taxonomy expands
  - moving-average clusters and moving-average slope/context
  - later, if useful, volume-profile or other structural liquidity/acceptance zones

- Strengthen the event-detection layer beyond the current v1 set, including:
  - fakeout
  - fakedown
  - failed reclaim
  - failed breakdown recovery
  - compression / squeeze near a level
  - expansion away from a level
  - better sequencing rules for first break vs retest vs late continuation
  - clearer confirmation/invalidation state transitions

- Evolve the confluence/scoring layer from the current transparent heuristic blend into a more complete framework that can combine evidence such as:
  - zone strength
  - touch count
  - recency of interaction
  - timeframe importance
  - ATR-normalized distance to a level
  - overlap of multiple levels or structures
  - AVWAP / EMA / SMA clustering
  - trend state
  - momentum context
  - relative volume / participation context
  - gap context
  - historical quality of similar setups
  - forward-tracked outcome quality
  - regime/context-conditioned weighting
  - later, if useful, learned weighting on top of interpretable rule features

- Extend the persistent radar/setup model beyond the current run+detection+thread foundation so it can also store:
  - richer state transitions over time beyond the current `developing` / `confirmed` baseline
  - automatic handling of failed / invalidated / stale states
  - evolving score history instead of only one snapshot
  - richer setup-thread semantics beyond today’s nearby-level continuity matching
  - later outcome / forward-performance tracking

- Expand the UI surfaces beyond the current dedicated `/radar` page, including:
  - a richer radar list / scanner view
  - side-by-side comparison of multiple detections
  - fuller setup history / state-transition history beyond the current thread + history-browser surfaces
  - instrument-specific radar timelines or history views

- Expand visual evidence rendering on charts beyond the current v1 zone/line/marker overlays, including:
  - shaded support/resistance zones
  - trendlines
  - channels / wedges / triangles
  - marked AVWAP anchors and lines
  - EMA/SMA overlays involved in the setup
  - breakout / fakeout / retest markers
  - optionally visibility toggles for each radar evidence type
  - ideally some notion of "radar layer" separate from the user's own drawings
  - clearer provenance / legend for evidence layers
  - grouping/stacking for overlapping detections on one symbol
  - chart-side switching between active and historical detections

- Keep improving the radar’s human-readable explanation layer so it does more than output a label, e.g.:
  - setup type
  - score
  - why it matters
  - what structures are involved
  - what timeframe(s) are driving it
  - what would confirm it further
  - what would invalidate it
  - what specifically made this candidate outrank nearby alternatives
  - which evidence is primary versus merely supporting
  - what changed since the previous detection state

- Expand filter/ranking behavior beyond the current simple setup/symbol/score/freshness controls, such as:
  - breakout candidates
  - support-bounce candidates
  - resistance-approach candidates
  - highest-confluence setups
  - recent fakeouts
  - reclaim setups
  - strongest multi-timeframe level clusters
  - freshest detections
  - most actionable / closest-to-level detections
  - per-sector / per-industry / per-instrument-type slices

- Add stronger validation / research capabilities around the radar, such as:
  - tracking what happened after each detected setup
  - evaluating historical success rates of different definitions
  - instrument-category-specific behavior
  - regime-aware quality differences
  - leaderboard-style comparisons of setup definitions
  - false-positive review tooling
  - later, if useful, learned weighting on top of the rule-based engine

Entry, exit, and invalidation semantics to deepen from the current v2 slice:
- **Explicit entry / invalidation / target levels now exist**, but they are still heuristic and detector-local. Improve them into a more rigorous action model (e.g., breakout close vs retest hold vs reclaim confirmation) and make the rationale more explicit in evidence payloads.
- **Lifecycle refinement beyond the current stale model**: Radar no longer hard-expires detections by TTL; it now keeps them open until they become `target_hit`, `invalidated`, or contextually `stale`. Future work here should refine the stale heuristics further with better regime awareness, thread supersession semantics, and setup-family-specific decay rules rather than reintroducing fixed expiry windows.
- **Connection to trade signal engine (item 8)**: When item 8 is implemented, radar detections are the natural input — a detection with an entry level, invalidation level, and score becomes the seed for a structured trade plan. The invalidation level becomes the stop, and the implied target can be the opposing zone or a fixed R-multiple. Both systems should share schema vocabulary from the start (entry_price, stop_price, target_price, risk_multiple).

Nearer-term concrete follow-up phases worth treating as the next likely implementation path:
- Phase 2:
  - richer structure extraction
  - scheduled runs
  - stronger chart overlay controls
- Phase 3:
  - fakeout/compression/failure state modeling beyond the current retest slice
  - managed radar/watchlist workflows beyond one-off actions
  - richer alert orchestration and state-transition workflows
- Phase 4:
  - historical outcome tracking
  - score calibration
  - strategy/trade-signal integrations

Broader feature ideas explicitly worth keeping in scope for future exploration:
- multi-timeframe level stacking and propagation
- relative-strength context versus sector/index/benchmark
- trend-stage classification
- volatility compression / expansion context
- gap-fill probability context
- earnings/event-aware technical context
- market-structure state labeling
- crowding / repeated-level behavior
- zone aging and decay logic
- setup clustering around macro dates or earnings windows
- sector/industry heat around the same type of technical setup
- dashboards or widgets specifically for radar discoveries
- alerts derived from radar state transitions

Visualization expectations:
- Anything used internally by the radar to justify a candidate should, where practical, be visually inspectable by the user.
- The user should not have to blindly trust the radar.
- A detected setup should be explorable on the chart page and, where appropriate, in dashboard widgets.

Why this was deferred:
- The initial v1 landed, but the original radar vision is much broader than the currently implemented slice.
- The remaining work is still a major platform capability, not a small feature.
- It depends on stronger data coverage, better operational definitions, deeper validation, and richer visualization design.
- It deserves continued dedicated implementation passes with room for experimentation and later evidence-based pruning.

### 6. Build unattended multi-LLM orchestration for overnight development
Status: `Deferred`

Context:
- We discussed a future workflow where Codex and Claude can be used in sequence, with an orchestrator switching between them so platform development can continue unattended for long stretches such as overnight runs.
- The key requirement is continuity: when one worker expires or becomes unavailable, the next one should not have to reconstruct state from scratch or guess where work was left.
- A major constraint identified in the discussion is that nominal session limits are not reliable in practice. A worker may lose usable budget much earlier than expected, sometimes within minutes, which means a single final handoff at the end of a session is not enough.
- To address this, we introduced a repo-owned orchestration model:
  - one canonical orchestration document
  - repo-carried task/state/handoff/report files
  - explicit stop-before-expiry behavior
  - frequent intermediate checkpoints
- We also established the recommended tool direction:
  - use **LangGraph** as the orchestrator
  - treat **Codex CLI** and **Claude Code CLI** as interchangeable workers
  - do not treat the VS Code extensions as the automation surface
  - eventually, if stronger workflow durability is needed, consider adding Temporal underneath later

What this system should become:
- A reliable unattended development workflow that can:
  - read a task queue
  - launch the appropriate worker
  - guide that worker through repo-defined rules
  - validate code and UX changes
  - checkpoint progress frequently
  - rotate workers when one nears exhaustion
  - resume from repo state rather than ephemeral conversation memory
- A neutral orchestration setup that is LLM-agnostic enough for different coding agents to read the same project guidance and obey the same rules.

What remains:

- Build the actual orchestrator around the repository-owned workflow, likely using LangGraph, including:
  - worker selection
  - task loading
  - checkpoint scheduling
  - worker rotation
  - retry behavior
  - failure handling
  - end-of-run reporting

- Ensure the orchestrator treats the following as the single canonical entry point for all workers:
  - `docs/agent-orchestration.md`
- That file should remain the top-level instruction file which then directs workers to the live `ops/*` state files.

- Keep and evolve the repo-owned shared state model, including:
  - `ops/tasks.yaml`
  - `ops/handoff.md`
  - `ops/state.json`
  - `ops/run-report.md`
- These files should be treated as durable continuity memory between workers.

- Preserve and enforce the stop-before-expiry / continuity-first behavior, including:
  - workers must assume usable session budget may collapse early
  - workers must not postpone handoff writing until the end
  - workers must checkpoint during the session after meaningful progress
  - workers must switch into preservation mode if exhaustion risk rises
  - the orchestrator must still impose its own fallback checkpoint/stop rules rather than trusting the worker entirely

- Add orchestrator support for bounded-run / checkpoint behavior, such as:
  - periodic heartbeat prompts
  - periodic checkpoint requests
  - wall-clock soft stop
  - optional max-turn segmentation
  - forcing handoff mode before risky long validations or before likely exhaustion

- Add environment-level support so workers can safely validate the platform end to end, including controlled access to:
  - Docker / Docker Compose
  - Alembic migrations
  - backend/frontend test runners
  - Playwright and browser automation
  - backend and frontend logs
- The preferred future deployment model is a dedicated dev machine or isolated VM for unattended runs rather than exposing a worker to the user's full everyday host environment.

- Prefer an allowlisted-script model for infra control rather than unconstrained shell power where practical, e.g. dedicated scripts for:
  - infra up/down
  - migrations
  - backend tests
  - frontend tests/build
  - E2E flows
  - backend/frontend log collection

- Require unattended workers to validate not only code correctness but actual user-facing behavior when relevant, including:
  - browser interaction flows
  - layout/UX sanity
  - browser console errors
  - backend log errors
  - successful startup/health of the relevant services

- Define the reporting expectations for each unattended run, including:
  - tasks completed
  - tasks partially completed
  - assumptions made
  - blockers found
  - tests run
  - UX validation performed
  - errors encountered
  - exact next step if work remains

- Keep the repo-level agent discoverability in place:
  - root `AGENTS.md` should continue to point to the canonical orchestration doc
  - the canonical doc should remain the first thing an external orchestrator tells any worker to read

Why this was deferred:
- We set up the repository-side memory and rule structure first, but not the actual orchestrator.
- The real value comes from building the supervisor workflow around these rules, which is a separate piece of work from day-to-day platform development.

### 7. Build a Strategy Lab with backtesting, walk-forward testing, and paper forward testing, likely powered by Nautilus Trader as the simulation engine
Status: `In progress`

Context:
- Right after the Technical Radar / Level-of-Interest initiative, the next major research feature discussed was a strategy research and validation layer: a place where users can define strategies, run historical backtests, compare strategies against one another, and later forward test them in a paper/simulated manner.
- We explicitly discussed avoiding reinvention of the execution/backtesting engine if a mature system can handle that responsibility. Nautilus Trader was identified as a strong candidate because it already provides a serious event-driven backtesting/live-trading architecture, portfolio analytics, options support, and custom data capabilities.
- The agreed architectural direction is not to turn this platform into a thin wrapper around Nautilus Trader, but rather to keep this platform as the research/product/orchestration layer while treating Nautilus as a worker/simulation engine behind a provider-agnostic and platform-owned data model.
- The platform must remain the source of truth for:
  - canonical instruments and identifiers
  - watchlists, screeners, radar results, and user-defined universes
  - strategy definitions and versions
  - run configurations
  - stored backtest / forward-test results
  - analytics, comparisons, dashboards, and UI
- The external simulation engine should be treated as replaceable infrastructure. Even if Nautilus Trader becomes the first engine, the platform should not become tightly coupled to Nautilus-specific assumptions any more than it is coupled to any single data provider.

What this system should become:
- A broad **Strategy Lab** / **Research Lab** that allows users to:
  - define strategies ranging from simple rules to complex multi-instrument systems
  - run historical backtests over one instrument or a custom-selected instrument universe
  - run walk-forward and out-of-sample tests
  - compare strategies against one another
  - analyze risk, return, drawdown, robustness, correlation, and diversification characteristics
  - later, run simulated forward tests on freshly arriving data
- A persistent research environment where the platform can answer questions such as:
  - "How would this strategy have performed on this watchlist?"
  - "How does this strategy compare to another one over the same universe and date range?"
  - "Which strategies are the least correlated, so I can combine them in a portfolio?"
  - "How does performance differ by instrument category, market regime, or technical context?"

Guiding architectural principles:
- Keep the platform's internal domain model authoritative and provider-agnostic.
- Treat the simulation engine as an implementation detail hidden behind a strategy-execution abstraction layer.
- Keep a clean product boundary between present-looking platform surfaces and historical research:
  - Radar and Screeners remain primarily present-looking discovery/evaluation products operating on the latest sufficiently fresh data.
  - Historical "what would this have done in the past?" replay should not become an ad hoc mode inside those products.
  - Instead, the shared Strategy Lab / Research Lab should own historical replay, backtesting, walk-forward testing, and paper-forward evaluation for both user-authored strategies and platform-owned signal sources.
- Persist everything that matters:
  - strategy definitions
  - strategy versions
  - strategy parameter sets
  - test configurations
  - run artifacts
  - trade/fill logs
  - equity curves
  - portfolio curves
  - aggregate metrics
  - correlations
  - attribution
  - robustness results
- Keep strategy-research workflows compatible with other platform features, especially:
  - watchlists
  - screener outputs
  - Technical Radar candidate lists
  - instrument universes defined manually or dynamically
- Treat the research engine as capable of consuming multiple signal-source classes, not only user-authored strategy rules, including:
  - custom strategies defined by users
  - platform-owned Radar detections treated as a built-in signal family
  - later, if useful, screener-derived signal/event feeds or other platform-owned discovery engines
- Support a future in which another engine or custom executor could sit behind the same platform-owned orchestration interfaces.

What remains:

- Continue from the current Strategy Lab baseline now present in the codebase, which already establishes:
  - persisted strategy definitions, versions, and runs
  - a visual-first frontend builder for rule-based strategies instead of raw JSON authoring
  - a backend run path that now uses Nautilus Trader for backtesting/simulation instead of the earlier in-house placeholder path
  - persisted backtest outputs exposed in platform-owned result schemas and shown in a platform-native UI
  - a clean separation between this research layer and present-looking products like Radar and Screeners
- Evolve that baseline from "good first visual backtest workspace backed by Nautilus" into a serious research workstation that can credibly compete with stronger retail/professional strategy-testing products.

- Be explicit about the current product boundary and current limitations so future work does not overestimate how complete this feature already is:
  - The current user value is real:
    - users can visually define a strategy
    - persist and version it
    - run historical backtests, walk-forward passes, and paper-forward-style continuation windows
    - inspect summary metrics, equity curves, benchmark context, warnings, trades, per-symbol attribution, and richer distributions
  - But the current implementation is still materially earlier-stage than mature competitors.
  - It should be treated as a functioning v1 research product, not a finished research lab.

- Capture the current gaps versus stronger competitors and use them as the roadmap for continuing this feature:
  - **Walk-forward and paper-forward are now real product surfaces, but still not deep enough yet.**
    - The current surface now exposes real walk-forward research segments and refreshable paper-forward monitoring snapshots, but it is still not a full end-to-end research/deployment workflow.
    - Walk-forward still needs deeper split configuration, rolling calibration/evaluation behavior, and richer out-of-sample stability surfaces.
    - Paper-forward now persists monitor snapshots on refresh, but it still is not a continuously scheduled live simulated monitoring loop over newly arriving data.
    - This is one of the largest product gaps because many stronger competitors let users validate not only historical fit but also forward behavior.
  - **The visual rule builder is materially stronger now, but still not broad enough for every serious strategy.**
    - Current rule authoring now supports nested `All` / `Any` / `NOT` groups and grouped precedence instead of only a flat condition list, but it is still limited.
    - Missing:
      - broader condition families
      - richer multi-timeframe logic
      - more session/time/event filters
      - stronger validation of structurally invalid rule combinations
    - This makes the current builder useful for simple systems but too narrow for many real strategies.
  - **Execution modeling is still thinner than it should be.**
    - Current support is centered on:
      - bar-driven entries/exits
      - stop loss
      - R-multiple target
      - time exit
      - break-even promotion
      - trailing-stop adjustment
      - capped pyramiding / multi-entry behavior
      - slippage assumptions
      - basic commission-model assumptions
    - Missing:
      - partial exits
      - richer order semantics
      - more advanced contingent-order workflows
      - more nuanced time-in-force and expiry handling where relevant
      - deeper fee modeling such as exchange / regulatory fees and tiered broker schedules
    - This is a major realism gap versus competitors and a major determinant of whether a backtest says anything useful.
  - **Multi-symbol portfolio simulation is improved, but still not production-grade.**
    - Current multi-symbol handling now applies portfolio-level trade acceptance controls such as concurrent-position caps, portfolio-risk caps, and symbol-allocation caps before building the combined portfolio result.
    - This is still not yet a full portfolio-aware scheduler/executor.
    - Missing:
      - deeper capital contention modeling across simultaneous opportunities
      - realistic position prioritization policies
      - sector exposure caps
      - more realistic cash reservation and overlapping-trade handling
    - This is one of the biggest reasons current multi-symbol results should be considered directionally useful rather than fully production-grade.
  - **Analytics are still thinner than serious research platforms, even though the baseline is now broader.**
    - Current outputs are useful but still compact:
      - summary metrics
      - equity curve
      - benchmark overlay / excess-return context
      - drawdown curve
      - monthly/quarterly performance breakdowns
      - warnings
      - trade list
      - per-symbol attribution
      - trade histograms/distributions
    - Missing:
      - MAE/MFE distributions
      - deeper holding-time and trade-outcome analytics
      - broader strategy-to-strategy comparison surfaces
      - richer run-to-run diffing between revisions
      - broader cohort/regime analysis
    - Competitors extract a large amount of user value from rich post-run analysis; this remains an important growth area.
  - **Multi-strategy correlation and composition research is still too shallow.**
    - We discussed wanting users to go beyond isolated strategy runs and evaluate how multiple strategies behave together as a portfolio.
    - Missing:
      - rolling correlation stability between strategies rather than only static snapshots
      - covariance/clustering analysis of strategy behavior
      - marginal contribution to portfolio return, volatility, and drawdown when adding or removing one strategy from a mix
      - portfolio-of-strategies simulation with configurable capital-allocation and rebalance rules
      - optimization/screening flows that help users deliberately combine lower-correlation strategies to reduce drawdowns and smooth equity curves
    - This is an important competitive gap because many users ultimately care more about the behavior of the combined strategy portfolio than about the headline metrics of one isolated system.
  - **Parameter exploration and robustness analysis are still early.**
    - Missing:
      - richer parameter sweeps than the current bounded leaderboard
      - optimization batches
      - sensitivity heatmaps
      - robustness summaries across periods/universes
      - overfitting detection aids
      - version-to-version comparison under the same scenario matrix
    - Without this, users can test a strategy, but cannot yet systematically improve it at scale.
  - **Radar/screener/platform-signal research integration is only partially in place.**
    - One of the most important strategic goals discussed was to use Strategy Lab as the shared validation layer for both:
      - user-authored strategies
      - platform-owned signal sources like Radar
    - That second half is now started, but not yet broad enough.
    - Missing:
      - apples-to-apples comparison of custom strategies versus Radar signals
      - screener-derived signal replay rather than only latest-result screener universes
      - later, if valuable, screener-derived or other platform-owned signal/event replay
    - This is a major latent value source because it turns Strategy Lab into the place where platform intelligence is validated and improved, not just user-authored logic.
  - **Asset-model breadth and realism are still limited.**
    - The current Nautilus adapter is strongest for equity-style, OHLCV-bar-based strategies.
    - It is not yet a broad, fully generalized research layer for:
      - futures
      - options
      - FX
      - crypto
      - synthetic/expression instruments
    - Missing:
      - broader canonical instrument-to-Nautilus mapping
      - more complete venue/account/execution semantics per asset class
      - more nuanced data-shape support where the strategy depends on more than simple OHLCV bars
    - This means Strategy Lab is already real, but not yet broad enough to inherit the full breadth of the platform’s instrument universe.
  - **The results UI is still more of an enhanced report than a full research workstation.**
    - Current UI is now materially broader, with richer analytics panes, comparison, export, grouped rule authoring, and paper-forward refresh/monitor surfaces, but it is still not yet a full analysis environment.
    - Missing:
      - stronger result navigation
      - richer dedicated tabs/panels for analytics
      - stronger visual benchmarking
      - saved result views
      - revision history comparison workflows
      - broader export surfaces
    - This is not just polish; research UX determines whether users can actually learn anything from their runs.
  - **Backtest/live continuity is still underexploited.**
    - One major reason Nautilus is valuable is that it supports a deeper parity model between historical and forward/live semantics.
    - We are not using that deeply yet.
    - Missing:
      - a continuously scheduled paper-forward loop
      - deeper state continuity from historical run definitions into forward simulation
      - richer operational surfaces that let users monitor a running simulated strategy over fresh incoming data
    - This is a major future-value area.
  - **Benchmarking is better than before, but still not first-class enough.**
    - Benchmark symbols/config now feed benchmark curves and excess-return reporting, but the overall benchmarking workflow is still thinner than what users expect.
    - Missing:
      - relative drawdown reporting
      - benchmark cohort comparison
      - strategy-as-benchmark workflows where another strategy/run can be treated as the benchmark rather than only a passive instrument
      - benchmark-aware run summaries beyond the current baseline
    - This is important because users do not just care whether a strategy "made money"; they care whether it beat a passive alternative.
  - **The feature does not yet fully exploit the rest of the platform.**
    - Long-term value should come from Strategy Lab acting as the validation/research layer for:
      - watchlists
      - screeners
      - Radar
      - baskets
      - breadth views
      - economic events / context filters
    - Today that integration is still early.
    - This is one of the biggest strategic advantages available to this platform over standalone testing products, so it should be treated as a first-class roadmap lane.

- Distinguish clearly between the current flaws and the future opportunities for extracting more value:
  - Current flaws:
    - too narrow for many real-world strategies
    - too weak in portfolio realism
    - still too thin in result analysis relative to competitors
    - platform-signal research is started but not yet broad enough
    - too limited in asset/model breadth
  - Current value:
    - real no-code/low-code visual strategy authoring
    - real Nautilus-backed backtesting in the backend
    - versioned/persisted strategy research objects
    - an integrated foundation that already fits the rest of the platform better than an external standalone tool would
  - Major future value sources:
    - use Strategy Lab as the validation layer for Radar
    - use Strategy Lab as the experimentation/tuning layer for platform-owned signal engines
    - connect watchlists/screeners/baskets/Radar directly into research universes and signal sources
    - grow it into a differentiated integrated research layer rather than just a generic backtester UI

- Design and implement a platform-owned strategy domain model, including concepts such as:
  - strategy definition
  - strategy version
  - parameter schema
  - parameter set
  - run configuration
  - selected universe
  - benchmark configuration
  - test mode
  - execution assumptions
  - run result summary
  - detailed run artifacts

- Define clear test modes and make them first-class, including:
  - standard historical backtest
  - walk-forward / rolling out-of-sample testing
  - parameter sweep / optimization batches
  - robustness testing
  - paper forward testing on newly arriving data
  - eventually, if ever needed, live execution mode as a separate concern and not something entangled into the initial research architecture

- Introduce a strategy-execution abstraction layer in the backend so the platform can submit a run without caring whether the underlying engine is Nautilus Trader or something else, including:
  - engine registration / engine type
  - engine capabilities
  - engine job submission
  - engine run status tracking
  - engine artifact retrieval
  - engine error reporting
  - engine versioning / compatibility metadata

- Build a dedicated Nautilus Trader integration layer as the likely first implementation, including:
  - mapping our canonical instruments to Nautilus instrument representations
  - exporting our persisted market data into Nautilus-compatible input formats
  - handling data catalog generation if needed
  - converting our stored bars / quotes / options data / custom events into Nautilus-readable datasets
  - collecting Nautilus results and translating them back into platform-owned result schemas
  - insulating the rest of the platform from Nautilus-specific symbols, IDs, config conventions, and storage assumptions

- Be very careful around instrument identity and symbology:
  - Nautilus has its own instrument identity conventions
  - our platform already has a provider-agnostic canonical identity model
  - the strategy system must use the platform's canonical identity everywhere user-facing or persistent
  - any Nautilus-specific mapping should live only in the adapter/integration layer
  - this is especially important for:
    - international equities
    - indices
    - futures
    - options contracts
    - synthetic / expression instruments, if they ever become relevant to strategy testing

- Build a research-universe selection layer tightly integrated with the rest of the platform, so a strategy run can target:
  - a single instrument
  - a manual selection of instruments
  - a watchlist
  - screener results
  - radar-discovered instruments
  - later, dynamic universes refreshed by scheduled rules
- Be explicit that the current Strategy Lab screener-universe implementation is intentionally only a **snapshot universe** for now:
  - the current `Latest screener result` behavior should be treated as:
    - "take the screener membership as of run submission time"
    - freeze that basket
    - run the strategy historically over that fixed symbol set
  - keep this current approach in place for now because it is simpler, deterministic, and already useful for:
    - testing a strategy on a screener-defined basket
    - comparing strategies over the same frozen screener membership
    - ad hoc research without introducing time-varying universe lifecycle complexity
- Add a future **dynamic screener universe** mode for Strategy Lab rather than treating screener-universe research as permanently snapshot-only:
  - the long-term user-facing concept should likely be something closer to `Screener universe` or `Dynamic screener universe`, not only `Latest screener result`
  - the intended behavior is:
    - during a simulated run, the screener is re-evaluated through simulated time
    - at each refresh point, only the data that would have existed at that historical moment is used
    - the eligible symbol basket can change over time as the screener membership changes
  - this should be modeled as a time-varying **entry-eligibility universe**, not as a simplistic "replace the whole portfolio immediately" mechanism
- When implementing the dynamic screener universe mode, explicitly define and persist the following policies so behavior is unambiguous and testable:
  - **Refresh cadence**
    - every bar
    - every N bars
    - daily
    - weekly
    - or another configured rebalance cadence
  - **Evaluation timing**
    - whether the screener membership for a bar is computed:
      - on the close of that bar
      - on the next bar open
      - or on another explicit decision point
    - this matters because the screener output must not peek into data not yet available at the simulated decision moment
  - **Entry eligibility policy**
    - only symbols currently in the screener membership are eligible for new entries
    - newly-added symbols become eligible only from the next defined execution/rebalance point
    - symbols removed from the screener should no longer accept fresh entries unless they later re-enter
  - **Open-position removal policy**
    - define what happens when a symbol leaves the screener while a position is already open
    - supported policies should eventually include:
      - `hold_until_exit`
      - `force_exit_on_removal`
      - `grace_period_after_removal`
    - the most natural default discussed was:
      - a symbol leaving the screener only blocks new entries
      - existing positions continue to be managed by their own stop/target/time-exit logic until they close naturally
  - **Re-entry policy**
    - if a symbol leaves the screener and later re-enters, it should become eligible again
    - re-entry should still respect the strategy's own entry logic and portfolio rules rather than blindly re-open a position just because the screener includes it again
  - **Portfolio interaction policy**
    - because the eligible universe changes over time, dynamic screener universes must work cleanly with:
      - capital contention
      - concurrent-position limits
      - symbol-allocation caps
      - portfolio-risk caps
      - any later sector/exposure caps
    - this means the screener universe should be treated as an upstream candidate filter, not as a direct instruction to allocate capital to everything newly included
- Treat dynamic screener universes as a first-class simulation concern rather than a small UI tweak:
  - the backtest engine will need a scheduled screener-refresh mechanism during simulation
  - the strategy run must be able to evaluate screener conditions point-in-time against historical data available at each simulated step
  - run artifacts/results should make it possible to inspect:
    - when screener refreshes happened
    - how membership changed over time
    - which trades were allowed or blocked because of screener membership at that moment
  - if helpful, later expose a membership timeline artifact showing:
    - symbols entering/leaving the screener universe through time
    - position lifecycle relative to that changing universe
- Keep a clean product distinction between the two screener-universe modes once both exist:
  - **Snapshot screener universe**
    - fixed basket
    - easier to reason about
    - useful for static-basket research
  - **Dynamic screener universe**
    - membership evolves over simulated time
    - more realistic for strategy behavior
    - requires explicit lifecycle policies
- Do not blur these modes together silently:
  - users should know whether a strategy run used:
    - a frozen screener snapshot
    - or a time-evolving screener universe
  - this choice should be visible in run configuration and stored in run artifacts/results for reproducibility

- Add a first-class **portfolio rotation / scheduled rebalance strategy mode** to support strategies that are not merely "evaluate entry/exit rules independently for each symbol", using the Starter System PDF discussion as a concrete forcing case:
  - The Starter System should be treated as an example of a strategy that Strategy Lab should eventually be able to express **exactly**, not approximately:
    - use a point-in-time broad equity universe such as the Russell 3000
    - evaluate filters on a monthly schedule
    - rank all passing candidates cross-sectionally
    - select the five lowest RSI(2) names
    - allocate 20% of capital to each selected name
    - rebalance on the next monthly open
    - exit all positions at the next rebalance unless selected again
    - force exits when a market-regime condition turns off
    - produce a monthly action list the user can follow manually
  - This exposes a major missing capability in the current Strategy Lab baseline:
    - the current engine is strongest at per-instrument rule evaluation
    - portfolio controls are layered on top of independently-generated opportunities
    - this is not enough for strategies where the primary decision is "rank the whole universe, choose the best N, and build the portfolio from those choices"
  - Add an explicit strategy archetype / execution mode for:
    - single-instrument rule strategies
    - multi-instrument independent-signal strategies
    - portfolio rotation strategies
    - later, pair/spread strategies and multi-leg strategies
  - A portfolio rotation strategy needs a different internal lifecycle:
    - build candidate universe for a decision point
    - evaluate all filters point-in-time
    - rank the filtered candidates
    - select top-N / bottom-N / percentile buckets
    - compare selected target portfolio versus currently-held portfolio
    - generate exits, holds, entries, and weight adjustments
    - apply execution assumptions at the configured execution point
    - persist the rebalance artifact before moving to the next decision point

- Add point-in-time index/constituency universe support because serious portfolio-rotation systems cannot be tested faithfully against only today's survivors:
  - support universes such as:
    - Russell 3000 constituents as-of each historical date
    - S&P 500 constituents as-of each historical date
    - ETF holdings as-of each historical date where available
    - user-defined universes with membership-effective date ranges
  - Treat ETF holdings as a useful lower-cost proxy universe when official index-constituent history is unavailable or too expensive, but never silently equate the two:
    - official index constituents are the authoritative, usually licensed dataset
    - ETF holdings are the fund issuer's disclosed portfolio and may differ due to sampling, cash, derivatives, timing, corporate actions, or tracking methodology
    - runs should record whether they used official point-in-time index membership, ETF-holdings proxy membership, a latest holdings snapshot, or a manual/static universe
  - persist universe membership as a time-varying dataset:
    - universe identifier
    - instrument identifier
    - membership start date
    - membership end date
    - membership source/provider
    - confidence/provenance
    - optional weight/classification metadata where the source provides it
  - make survivorship-bias status visible in run configuration and results:
    - `point_in_time_universe`
    - `latest_membership_snapshot`
    - `manual_static_universe`
  - warn clearly when a strategy that claims to test an index universe is actually using a latest-only or manually frozen universe.
  - Allow the data-prep layer to request missing member instruments and their historical bars as part of run preflight instead of discovering missing coverage only after a run has produced misleading results.

- Add scheduled decision/rebalance calendars as first-class strategy inputs:
  - support cadences such as:
    - every bar
    - daily
    - weekly
    - monthly
    - quarterly
    - custom cron/calendar schedules
    - exchange-aware "last trading day of month"
    - exchange-aware "first trading day of month"
  - separate the **decision timestamp** from the **execution timestamp**:
    - screen on month-end close
    - execute at next monthly open
    - screen on today's close
    - execute on next bar open
    - screen intraday and execute immediately where data/execution assumptions allow
  - persist schedule semantics in run configuration:
    - calendar used
    - timezone
    - exchange/market holiday handling
    - decision price source
    - execution price source
    - handling of missing bars on the scheduled decision or execution day
  - expose scheduled events in run artifacts:
    - decision points
    - rebalance points
    - symbols evaluated at each point
    - selected basket at each point
    - target weights
    - executed portfolio changes

- Add cross-sectional ranking and candidate-selection primitives:
  - allow strategies to rank candidates by:
    - indicator values such as RSI(2)
    - price returns over configurable windows
    - volatility
    - liquidity
    - fundamental metrics
    - platform-computed statistics
    - custom expressions/factors later
  - support ranking directions:
    - lowest first
    - highest first
    - absolute distance from target value
    - percentile buckets
    - z-score / normalized ranking later
  - support selection policies:
    - top N
    - bottom N
    - top/bottom percentile
    - rank threshold
    - weighted by rank score
    - tie-breakers
  - persist the rank table for every decision point so the user can inspect:
    - symbols that passed filters
    - symbols that failed filters
    - the filter that rejected each failed symbol
    - each candidate's rank metric value
    - final rank position
    - selected/not-selected reason
  - This should unlock not only the Starter System, but also:
    - momentum rotation
    - mean-reversion baskets
    - low-volatility selection
    - high-quality/fundamental factor screens
    - sector rotation
    - ETF rotation
    - breadth-driven basket strategies

- Add portfolio construction and target-allocation rules instead of relying only on per-trade position sizing:
  - support target portfolio policies such as:
    - equal weight across selected symbols
    - fixed percent per selected symbol
    - volatility-scaled weights
    - rank-score-weighted allocation
    - inverse-volatility weighting
    - max position weight
    - min position weight
    - cash reserve target
  - support rebalance behavior:
    - full liquidation and rebuild
    - only trade differences from current holdings
    - hold selected names that remain selected
    - rebalance back to target weights
    - drift bands before rebalancing
    - minimum trade-size thresholds
  - explicitly model what happens when fewer than the target number of names pass:
    - leave unused capital in cash
    - redistribute among available names
    - skip the rebalance entirely
    - keep existing holdings until enough replacements exist
  - persist target-vs-actual portfolio state:
    - target symbols
    - target weights
    - actual filled weights
    - cash after rebalance
    - turnover
    - symbols bought/sold/held/skipped
    - rejected trades and rejection reasons

- Add cross-instrument and portfolio-level condition inputs:
  - allow a condition on one instrument/index to control trading in another universe:
    - "only open Russell 3000 positions when S&P 500 RSI(4) > 50"
    - "force exit all open positions when S&P 500 RSI(4) < 50"
    - "only run this strategy when VIX is below/above a threshold"
    - "only buy sector constituents when the sector ETF is above its moving average"
  - distinguish:
    - instrument-local conditions
    - benchmark/regime conditions
    - universe-level aggregate conditions
    - portfolio-state conditions
  - support regime conditions as:
    - entry gates
    - exit triggers
    - allocation scalers
    - cash/defensive-state switches
  - Persist regime state through time and show it in results:
    - when regime was on/off
    - which entries were blocked by regime
    - which positions were closed because regime turned off
    - whether the strategy was fully invested or sitting in cash

- Expand condition/stat/factor support required by portfolio-rotation strategies:
  - add rolling liquidity metrics:
    - 20-day average volume
    - 30-day average volume
    - 60-day / 3-month average volume
    - average dollar volume
    - median dollar volume
    - minimum liquidity over a lookback window
  - add price and tradability filters:
    - price greater/less than a threshold
    - adjusted versus unadjusted price basis
    - minimum trading history length
    - minimum bars available in lookback window
    - exclusion of suspended/untradable instruments where known
  - support indicator calculations on:
    - the candidate instrument
    - a benchmark/regime instrument
    - a sector/index/ETF proxy
    - later, a synthetic basket or expression instrument
  - ensure all filters are evaluated point-in-time using only data available at the decision timestamp.

- Add explicit forward **published strategy runtime** support so Strategy Lab strategies can produce passive, recurring action signals without turning Screener or Radar into strategy owners:
  - Strategy Lab should own:
    - strategy definition
    - versioning
    - backtests
    - validation
    - publish workflow
  - A published strategy runtime should own:
    - scheduled forward execution of published versions
    - persisted strategy state
    - current open simulated/manual-following portfolio state
    - recurring decision runs
    - signal/action generation
  - The runtime should generate actionable outputs such as:
    - buy these symbols
    - sell these symbols
    - hold these symbols
    - rebalance these weights
    - no action because regime is off
    - data coverage is insufficient
    - candidate excluded because it failed a filter
  - These outputs should be stored as strategy action sets, not as plain screener results:
    - action set id
    - strategy version id
    - decision timestamp
    - execution timestamp
    - target basket
    - current basket
    - diff/actions
    - quantities/weights if configured
    - rank/filter evidence
    - user acknowledgement status later
  - This runtime should be able to support "manual execution" workflows first:
    - the platform tells the user what the strategy says to do
    - the user decides whether/how to place trades outside the platform
    - the platform can later let the user mark actions as followed, skipped, or adjusted
  - Later, this can integrate with broker execution if/when the platform grows beyond research/manual-action workflows.

- Keep Screener and Radar as reusable inputs, not owners of stateful strategy execution:
  - Screener should remain useful for:
    - authoring/reusing filter condition sets
    - present-looking "what passes now?" discovery
    - scheduled screen results where the output is simply a matching instrument set
    - serving as one possible upstream candidate-filter component for Strategy Lab
  - Radar should remain useful for:
    - autonomous technical opportunity discovery
    - platform-owned signal families
    - candidate feeds into Strategy Lab/research
  - Neither Screener nor Radar should own:
    - target weights
    - open strategy positions
    - rebalance state
    - ranking-driven portfolio construction
    - portfolio-level exits
    - strategy action-set history
  - If a user wants a saved screener to feed a strategy:
    - Strategy Lab/runtime should reference the screener definition or condition set
    - the runtime should still own selection, allocation, state, and actions
  - If a user wants Radar to feed a strategy:
    - Radar should provide candidate events/detections
    - Strategy Lab/runtime should still own execution policy and portfolio state

- Add a reusable **condition-set / filter-set borrowing** mechanism between Screener and Strategy Lab without collapsing the products together:
  - allow a Strategy Lab strategy to:
    - import a Screener condition tree as a starting point
    - reference a saved Screener condition set by version
    - fork a Screener condition set into strategy-owned logic
    - expose strategy condition sets to Screener where the semantics are compatible
  - define compatibility boundaries:
    - pure point-in-time instrument filters can be shared
    - portfolio-level ranking/allocation rules cannot be represented as ordinary screeners
    - entry/exit semantics are strategy-owned, not screener-owned
    - rebalance cadence is strategy-owned, not screener-owned
  - Persist provenance:
    - imported from screener X version Y
    - still linked to screener version
    - forked and no longer linked
  - This gives users the practical benefit of reusing work from Screener while keeping Strategy Lab as the correct owner for serious strategy behavior.

- Add a strategy action / signal feed surface for published strategies:
  - This can be a new surface, or part of a broader Signals/Alerts area, but it should not live only inside the Strategy Lab edit page.
  - It should answer:
    - "Which published strategies have actions due now?"
    - "Which actions were generated by the latest scheduled run?"
    - "What changed versus last month/last run?"
    - "Which symbols entered or left the target basket?"
    - "Which actions are blocked by data quality, regime, or portfolio constraints?"
  - For a monthly rotation strategy, the user-facing output should be closer to:
    - next rebalance date
    - target basket
    - sell list
    - buy list
    - unchanged holds
    - target weights
    - ranking evidence
    - filter evidence
    - data warnings
  - It should later support notifications:
    - in-app alerts
    - email/push/webhook where appropriate
    - "rebalance due" reminders
    - "strategy regime turned off" alerts
    - "data coverage insufficient to generate reliable action" alerts

- Add strategy-state and manual-following tracking as a bridge between research and real user behavior:
  - Store the strategy runtime's expected/paper state separately from the user's actual brokerage state.
  - Allow the user to mark generated actions as:
    - followed
    - skipped
    - partially followed
    - modified
  - Later, connect this to a portfolio/journal feature so the platform can compare:
    - model strategy performance
    - paper/runtime performance
    - user's actually-followed performance
  - This is important for passive strategies where the platform produces actions but the user executes manually.

- Add run/result artifacts specifically for portfolio-rotation strategies:
  - candidate universe snapshot per decision point
  - filter pass/fail table per decision point
  - rank table per decision point
  - selected basket per decision point
  - target weights per decision point
  - rebalance trades per decision point
  - regime state timeline
  - cash allocation timeline
  - turnover timeline
  - constituents entering/leaving the eligible universe
  - selected symbols entering/leaving the target portfolio
  - reasons a symbol was not selected despite passing filters
  - reasons a current holding was sold
  - reasons no new positions were opened
  - These artifacts are essential because users need to trust not just the final return, but the month-by-month decision logic.

- Add a platform-owned signal-source abstraction for research/test runs so the same testing layer can evaluate:
  - user-authored strategies that generate entries/exits from rules
  - Radar detections replayed historically as a built-in black-box signal engine
  - eventually other platform-owned event/signal sources
- This abstraction should make it possible to ask questions such as:
  - "Give me all Radar breakout signals on D1 between 2023-01-01 and 2024-12-31."
  - "Replay all Radar signals in this score bucket using execution policy X."
  - "Compare my custom strategy against the platform Radar over the same universe and date range."
- The query/export contract for platform-owned signal sources should include, at minimum:
  - source type (`strategy`, `radar`, later others)
  - source version / engine version
  - signal/setup family
  - timeframe
  - signal timestamp
  - context timestamp if distinct
  - entry / invalidation / target semantics when available
  - score / confidence / rationale metadata where relevant

- Keep Radar itself non-configurable and present-looking, but make Radar historically researchable through this shared testing layer:
  - the `/radar` product should answer "what looks interesting now?" and "how has this active setup evolved recently?"
  - the Strategy Lab / Research Lab should answer "what would Radar have produced over this historical period?" and "how did those signals perform under execution policy X?"
  - this preserves Radar as a curated black box while still allowing internal tuning and user-facing trust/validation statistics

- Build a strategy-definition layer that can support multiple levels of user sophistication:
  - a visual rule builder for simpler strategies
  - a declarative intermediate schema or DSL for more expressive strategies
  - fully coded strategies for advanced users
- The platform should not force all users into raw engine code if they only want rule-based or parameterized strategies.
- The visual/declarative path should likely be platform-native and later compiled/transformed into an executable representation for the simulation engine.

- Support strategies with a wide range of possible logic, not just simple single-instrument trend following, including eventually:
  - indicator-driven entry/exit logic
  - price-action and pattern conditions
  - multi-timeframe conditions
  - universe-level filtering
  - ranking / top-N selection
  - volatility or liquidity filters
  - event-aware logic
  - options-aware logic if/when supported well enough
  - pair or relative-strength logic
  - portfolio-level allocation and rebalancing rules

- Model execution assumptions and market-friction settings explicitly, including:
  - bar-based vs richer-data assumptions
  - slippage models
  - commissions / fees
    - flat round-trip fees
    - flat per-order fees
    - percent-of-notional commissions
    - later: tiered fee schedules and venue/regulatory fee components
  - spread assumptions
  - latency assumptions where meaningful
  - fill models
  - venue/exchange awareness
  - position sizing models
  - leverage / margin assumptions
  - portfolio constraints
- These assumptions must be visible in run configs and persisted as part of the provenance of any run result.

- Extend the research engine beyond single-currency portfolio assumptions:
  - support a user portfolio base currency distinct from the traded instrument currency
  - translate P&L, exposure, and drawdown into the portfolio base currency for reporting
  - model FX conversion costs when buying instruments denominated in a different currency than the portfolio base
  - later support configurable spot-conversion pricing assumptions and broker-specific FX conversion fee schedules

- Build a data-preparation/export layer from the platform's DB to the simulation engine, including:
  - selecting the required historical window
  - selecting the required instruments / contracts
  - selecting the required timeframes
  - selecting supporting event/custom data
  - enforcing data coverage checks
  - documenting missing/stale data before or during a run
  - exporting data in a reusable cached form when possible
- This layer must be very mindful of:
  - data completeness
  - timeframe alignment
  - corporate actions / adjusted vs unadjusted series
  - options chain snapshots vs timeseries
  - future support for richer quote-level or tick-level data

- Treat result persistence as a first-class system rather than ephemeral output, storing at minimum:
  - run metadata
  - strategy version used
  - parameter set used
  - date range
  - selected universe
  - benchmark used
  - execution assumptions
  - engine used
  - run status
  - error logs / warnings
  - trade list
  - order/fill history
  - position history
  - equity curve
  - drawdown curve
  - exposure history
  - per-instrument contribution / attribution
  - summary metrics
  - artifacts generated by the engine

- Build a rich result-analytics layer on top of those stored results, including:
  - total return
  - annualized return
  - volatility
  - Sharpe / Sortino and similar ratios
  - drawdown metrics
  - win/loss metrics
  - expectancy
  - turnover
  - exposure metrics
  - per-instrument attribution
  - sector/category attribution where possible
  - benchmark-relative performance
  - rolling performance windows
  - regime breakdowns
  - trade distribution analytics

- Build explicit strategy-comparison tooling, including:
  - compare two or more strategy runs side-by-side
  - compare multiple parameterizations of the same strategy
  - compare strategies over the same universe/date range
  - compare strategies by regime
  - correlation matrix of strategy returns
  - rolling correlation stability across time/regimes
  - covariance/diversification analysis
  - clustering/similarity analysis of strategy behavior
  - portfolio-construction ideas such as combining less-correlated strategies
  - portfolio-of-strategies simulation with configurable weights, capital-allocation rules, and rebalance cadence
  - marginal contribution analysis: "what happens to portfolio return, volatility, Sharpe, and drawdown if this strategy is added or removed?"
  - optimization/screening flows that favor complementary lower-correlation strategies rather than only the highest standalone return
  - ranking by robustness instead of raw total return alone

- Support walk-forward / out-of-sample research directly rather than treating it as an afterthought, including:
  - segmented train/test windows
  - rolling calibration windows
  - rolling evaluation windows
  - parameter freeze vs periodic retuning behavior
  - aggregated walk-forward summaries
  - per-window stability views
  - degradation / drift diagnostics

- Add robustness-testing ideas that are valuable even before any machine-learning layer, including:
  - parameter sweeps
  - sensitivity analysis
  - Monte Carlo reshuffling where appropriate
  - start-date robustness
  - universe robustness
  - timeframe robustness
  - cost/slippage stress tests
  - data-delay / execution-delay stress assumptions
- The goal should be to separate "looks great on one chart" from "survives perturbation."

- Define what forward testing means in the platform and make it explicit that there are two distinct ideas:
  - walk-forward testing over historical data
  - paper forward testing on newly arriving data in simulated mode
- Later paper forward testing should reuse the same strategy definition and, where possible, the same simulation semantics as backtests, while operating on fresh platform-ingested data.

- Build a paper forward-testing mode that can eventually:
  - subscribe to selected active strategies
  - run on newly arriving bars/quotes/events
  - maintain paper positions and paper P&L
  - track divergence versus historical expectations
  - expose current paper state in the UI
  - alert when a strategy's current behavior meaningfully deviates from historical norms or risk thresholds

- Add frontend surfaces for the Strategy Lab, including:
  - strategy list / catalog
  - create/edit strategy view
  - strategy version history
  - run-configuration form
  - universe picker
  - backtest run history
  - walk-forward results view
  - strategy comparison view
  - portfolio-of-strategies comparison view
  - multi-strategy composition / allocation workspace
  - paper forward-testing monitor

- Add rich visualizations, such as:
  - equity curves
  - underwater/drawdown charts
  - rolling Sharpe / rolling return charts
  - trade distribution histograms
  - heatmaps by month/week/regime
  - parameter sweep heatmaps
  - correlation matrices between strategies
  - rolling correlation charts between strategies
  - portfolio contribution and marginal-risk charts for multi-strategy mixes
  - contribution / attribution charts
  - benchmark overlays
  - trade markers on the main chart where appropriate

- Tie the Strategy Lab into the rest of the platform where it makes sense, especially:
  - run a strategy against a watchlist directly
  - run a strategy against screener results
  - later run a strategy against Technical Radar candidate lists
  - allow chart/radar discoveries to feed directly into strategy research
  - eventually compare "radar-guided" strategies versus plain universe strategies

- Make this system compatible with options and more complex instruments over time, but stage expectations carefully:
  - initial strategy work may begin with bar-based underlying instruments
  - later support options strategies as data quality and engine capability allow
  - keep the architecture broad enough for multi-leg options and derivatives research later, even if not all of it is implemented immediately
- This point is especially important because the platform is already becoming more options-aware and the strategy system should not corner itself into equities-only assumptions.

- Add scheduling/orchestration support eventually, including:
  - queued backtest jobs
  - asynchronous run execution
  - batch research jobs
  - periodic re-runs when fresh data arrives
  - retention rules for large artifacts
  - cancellation / pause / retry semantics

- Track provenance and reproducibility very carefully:
  - which strategy version was used
  - which engine version was used
  - which data snapshot/coverage state was used
  - which assumptions were used
  - which benchmarks/universe definitions were used
  - which parameters were used
- A historical run should be reconstructable later as faithfully as practical.

- Be mindful of realistic limitations and caveats, especially if Nautilus Trader is used:
  - engine/library evolution and possible breaking changes
  - symbol and identity mismatch between the platform and Nautilus
  - data-realism limits when only bar data exists
  - richer realism only becoming available once richer quote/order-book data exists
  - licensing/commercialization implications that should be revisited before public productization

Broader feature ideas explicitly worth keeping in scope for future exploration:
- strategy templates and starter packs
- library of common technical/systematic strategy archetypes
- import/export of strategy definitions
- collaborative comparison of multiple strategies or parameter families
- scorecards for robustness vs overfitting risk
- regime-aware strategy ranking
- combination/ensemble strategies
- benchmark families beyond simple buy-and-hold
- strategy tagging and taxonomy
- automated reporting / PDF or shareable summaries
- linking strategy events back onto the chart page visually
- linking forward-tested active strategy state into dashboards
- using platform events, radar detections, or custom factor series as strategy inputs

Phasing expectations:
- Phase 1 should likely focus on:
  - backend abstraction for strategy engines
  - Nautilus Trader as the first engine implementation
  - platform-owned run configs and persisted results
  - bar-based historical backtesting
  - single-instrument and small-universe support
  - basic comparison analytics
- Phase 2 should likely add:
  - richer strategy-definition UX
  - parameter sweeps
  - walk-forward testing
  - stronger comparison and robustness tooling
- Phase 3 should likely add:
  - paper forward testing on new incoming data
  - better monitoring and alerting
  - tighter integration with radar/screener/watchlist workflows
- Later phases can expand toward:
  - richer data realism
  - advanced options strategies
  - more sophisticated portfolio construction
  - engine pluralism beyond Nautilus if needed

Interpretation expectations for future work:
- This should be treated as a major platform initiative, not a small feature.
- The platform should own the research workflow and user experience, even if Nautilus owns the underlying simulation semantics.
- The intent is not merely "add a backtest button", but to build a full strategy research environment that complements the Technical Radar and the broader analytics direction of the product.
- Visual overlays should make it easy to distinguish:
  - user-created drawings
  - instrument-linked technical evidence
  - ephemeral radar detections currently active

Suggested implementation philosophy:
- Do not try to perfectly imitate a human analyst in one opaque leap.
- Build a transparent technical-discovery engine that:
  - extracts structures
  - detects events around them
  - scores confluence
  - ranks candidates
  - visualizes its reasoning
- Start broad in scope, then later validate and filter for signal quality instead of prematurely narrowing the concept.

Why this was deferred:
- This is a major platform capability, not a small feature.
- It depends on strong data coverage, careful operational definitions, and good visualization design.
- It deserves a dedicated implementation pass with room for experimentation and later evidence-based pruning.

### 8. Build a Trade Signal, Virtual Trade Tracking, and Trader-Follower engine
Status: `Deferred`

Context:
- After discussing the Technical Radar and the Strategy Lab, we explored whether a full auto-trading layer should sit on top of them.
- The agreed conclusion was that full live auto-execution is a natural long-term extension, but not the right first step.
- The better intermediate product is a **trade signal generator plus virtual trade lifecycle tracker**:
  - the platform identifies a trade idea,
  - alerts the user,
  - defines and tracks the hypothetical trade in the background,
  - continues issuing alerts for entries, stop movement, partial exits, take profits, invalidations, and final exits,
  - while collecting forward-tested performance data as if the trade had been followed systematically.
- This gives most of the research and discipline benefits of automation without immediately taking on broker integration, live order routing, or full auto-trading risk.

What this system should become:
- A **Trade Signal & Lifecycle Engine** that turns strategy/radar detections into structured trade plans.
- A **manual-execution companion** for users: the user places the trade themselves, while the platform tracks the plan and keeps monitoring it.
- A **forward-testing layer** that measures how well the platform’s ideas and trade-management rules actually perform in live-market conditions over time.
- A **bridge layer** between:
  - Technical Radar candidate discovery
  - Strategy Lab research/backtesting
  - later paper trading
  - and eventually, if desired, semi-automated or fully automated execution

Core product goals:
- Generate structured trade idea alerts from technical/rule-based detections.
- Represent a full trade plan rather than only an entry alert.
- Track hypothetical trades continuously in the background after signal creation.
- Alert users when the trade transitions through important lifecycle states.
- Measure live forward-tested trade outcomes to validate setups and trade-management logic.
- Provide a disciplined, auditable trade journal even when execution is still manual.

What remains:
- Define the **signal-to-trade-plan transformation layer**, including:
  - how a Technical Radar setup or Strategy Lab rule becomes a candidate trade
  - entry model types, such as:
    - immediate market-style entry at signal
    - breakout trigger entry
    - pullback/retest entry
    - support-bounce style entry
    - reclaim/recovery entry
    - limit-style or zone-based entry logic
  - directional context:
    - long
    - short
    - both where appropriate
  - validity windows for entries:
    - same-session only
    - N bars only
    - expires if level already moved too far
    - expires on structure invalidation

- Define a persistent **trade plan model**, capturing things like:
  - instrument
  - signal source
  - source setup id / strategy run id / radar detection id
  - side (long/short)
  - entry logic
  - entry zone or entry trigger
  - stop loss
  - one or more profit targets
  - optional partial-take-profit structure
  - optional trailing-stop logic
  - invalidation logic
  - creation time
  - expiry time / entry validity window
  - current lifecycle status
  - notes / rationale / evidence payload
  - provenance of how the trade was derived

- Define the **virtual trade lifecycle state machine**, including statuses such as:
  - proposed
  - alerted
  - entry pending
  - entered
  - partially exited
  - trailing / management active
  - stopped out
  - target hit
  - fully exited
  - invalidated before entry
  - expired before entry
  - cancelled
  - manually overridden / user-dismissed

- Define the **trade-monitoring engine** that continuously evaluates open or pending trade plans against incoming data, including:
  - entry-trigger monitoring
  - stop-hit detection
  - target-hit detection
  - partial-target-hit detection
  - trailing-stop adjustment logic
  - break-even transition logic
  - time-based invalidation or forced exit logic
  - setup-quality decay / “setup no longer valid” logic
  - session or event-aware logic if relevant later

- Add a broad **alert-generation layer** around trade lifecycle events, including:
  - new trade setup generated
  - entry triggered
  - entry missed / expired
  - stop loss hit
  - take-profit level reached
  - partial exit reached
  - stop moved to break-even
  - trailing stop updated
  - trade invalidated
  - final exit completed
  - outcome summary alert / notification

- Define how the engine handles **pricing and hypothetical fills**, including:
  - whether fills are assumed on touch, close, or open of next bar
  - whether intrabar hit sequencing matters when stop and target are both touched
  - how gaps are handled
  - how slippage assumptions are represented
  - how fills differ across timeframes and data quality levels
  - how assumptions remain visible and auditable to users

- Add a persistent **virtual trade / forward-test ledger**, storing:
  - original trade plan
  - all lifecycle transitions
  - timestamps of each transition
  - hypothetical fills
  - realized and unrealized P&L
  - MFE / MAE
  - risk multiple (R)
  - duration in bars and wall-clock time
  - target sequence reached
  - reason for exit
  - whether the trade was user-followed or only platform-tracked
  - optional user annotation about whether the human actually took the trade

- Build a **trade journal / follower UI layer**, including:
  - list of active trade ideas
  - list of pending entries
  - list of active virtual trades
  - completed trades
  - outcome and statistics views
  - filtering by source, setup type, instrument, timeframe, side, and status
  - trade detail pages or panels showing:
    - the original setup rationale
    - planned entry/stop/targets
    - lifecycle history
    - current state
    - forward-tested performance

- Add chart-side visualization for the entire trade plan and lifecycle, including:
  - entry line / zone
  - stop line
  - target lines
  - partial target markers
  - trailing stop path if active
  - entry trigger marker
  - exit markers
  - invalidation marker
  - trade-state overlays or labels
  - ability to distinguish radar evidence from trade-plan overlays

- Tie this system to the rest of the platform so trade ideas can originate from:
  - Technical Radar detections
  - Strategy Lab forward-tested strategies
  - manually promoted user-selected chart setups
  - later screener outputs or other analytics engines

- Add **forward-testing analytics** so the platform can answer questions like:
  - which setup types generate the best live-tracked outcomes?
  - which entry models are most robust?
  - how often do trade ideas reach TP1, TP2, or stop first?
  - how often are signals invalidated before entry?
  - how does forward-tested outcome compare with historical backtest expectation?
  - which instruments, sectors, or regimes respond best to the engine’s trade ideas?

- Add a **portfolio / batch view** of live tracked trade ideas, including:
  - active trade count
  - net long/short bias
  - total hypothetical risk exposure
  - clustering by sector/industry/theme
  - overlapping setup concentration
  - strategy-source concentration
  - calendar/event exposure overlap

- Add user-control concepts around manual-following behavior, such as:
  - mark trade as “taken” or “ignored”
  - mark trade as “follow partially” or “watch only”
  - compare platform-tracked trade plan against actual user execution later if desired
  - allow the user to dismiss or pause certain signal sources

- Later, optionally extend this into progressively more automated layers, such as:
  - paper-trading execution simulation using the same trade plans
  - semi-automated “confirm before send” broker actions
  - eventually, full auto-execution for validated strategy subsets

Research and modeling expectations:
- Keep this initially focused on **signals plus virtual lifecycle tracking**, not true live broker automation.
- Treat all fills and outcomes as model-based and explicitly assumption-dependent.
- Ensure every tracked trade is transparent:
  - where it came from
  - why it exists
  - what rules govern it
  - how outcomes were computed

Broader feature ideas explicitly worth keeping in scope for future exploration:
- signal ranking by live forward-tested quality rather than only historical backtest quality
- user-configurable trade templates per setup type
- trade idea confidence intervals or quality bands
- regime-aware trade-plan templates
- sector / basket follower signals
- options-specific trade-following later
- multi-leg / scaling-in / scaling-out logic later
- correlation-aware throttling of simultaneous ideas
- event-aware pause logic around earnings or macro events
- strategy-vs-radar blended signal sources
- dashboard widgets for active trade ideas and tracked outcomes

Why this was deferred:
- It is a substantial subsystem in its own right and depends conceptually on the Technical Radar and Strategy Lab being better defined first.
- It is the safest and most useful intermediate step before any future broker-linked automation.
- It deserves a focused design and data-model pass rather than being smuggled in piecemeal under “alerts” or “paper trading.”

### 9. Activate paid providers for options data and forward earnings estimates
Status: `In progress — full completion contract still open`

Context:
- The platform now has a full free-provider stack (Alpaca, FRED, Binance, CoinGecko, EDGAR)
  covering US equity OHLCV, crypto, corporate actions, rates, and historical earnings.
- The following data types have no viable free alternative and are currently covered only by
  yfinance (unofficial, no SLA):
  - **US options chains with real greeks** — delta, gamma, theta, vega
  - **Forward earnings calendar** — upcoming confirmed/estimated earnings dates
  - **Analyst price targets and recommendations**

Low-budget candidates already anticipated in config.py (keys are present, providers not yet built):
- `MARKETDATA_API_KEY` → MarketData.app ($25/month) — US options with real greeks + earnings calendar
- `FMP_API_KEY` → Financial Modeling Prep ($15/month) — forward estimates, analyst data, richer fundamentals
- IBKR TWS API (free with account) — comprehensive US + international options, futures, real greeks;
  requires IB Gateway sidecar process and a throttled scheduler due to IBKR pacing limits

What remains:
- Implement `marketdata` provider (MarketData.app): `OptionChainProvider` with real greeks,
  `EventProvider` for earnings calendar
- Implement `fmp` provider (FMP): `EventProvider` for forward earnings + analyst data,
  `InstrumentMetadataProvider` for richer fundamentals
- Optionally implement `ibkr` provider (IBKR TWS): comprehensive coverage for priority instruments,
  requires IB Gateway sidecar and a pacing-aware scheduler queue
- Demote yfinance options/events capabilities to last-resort once paid providers are active

Why this was deferred:
- The free provider stack covers the high-volume refresh use case well.
- Options and forward estimates require a budget commitment; the user will decide when to activate.

### 9A. Add a free-source-first forward IPO and market-events calendar
Status: `In progress — full completion contract still open`

Context:
- The platform already has pieces that are adjacent to this problem, but not the actual subsystem we need:
  - persisted per-instrument event storage
  - a `/calendar` router
  - dashboard economic-calendar widget surfaces
  - historical and semi-forward instrument-level events from current providers such as yfinance/EDGAR
- What is still missing is a **market-wide, forward-looking event layer** that lets the platform look ahead, not just look back.
- We explicitly want this for two strategic reasons:
  - discover new tickers before or as they enter the instrument universe
  - give users forward visibility into market events so they can adjust portfolio exposure ahead of them
- The initial focus should be **US markets**, because free structured sources are far more realistic there than for EU or APAC right now.

Free-source provider direction confirmed from primary sources:
- **Massive** should be the first-class free IPO provider:
  - the Stocks docs expose `GET /vX/reference/ipos`
  - the endpoint is marked as included in **Stocks Basic Free**
  - docs describe both **upcoming and historical** IPO events starting from **2008**
  - docs expose statuses such as:
    - `rumor`
    - `pending`
    - `new`
    - `history`
    - `postponed`
    - `withdrawn`
    - `direct_listing_process`
  - docs also expose pagination and sort/order controls, so this can support both:
    - daily forward polling
    - backfill of historical IPOs for research/audit
- **Alpha Vantage** is a sensible free complementary provider:
  - docs expose `function=IPO_CALENDAR`
  - docs state it returns IPOs expected in the **next 3 months**
  - this is CSV-based and easy to ingest cheaply
  - Alpha Vantage also exposes `EARNINGS_CALENDAR` with `3month`, `6month`, and `12month` horizons, which is useful for broadening the same market-events subsystem beyond IPOs
  - Alpha Vantage `LISTING_STATUS` is also useful as a **post-listing reconciliation feed**, not a forward calendar:
    - use it to confirm when a previously future/pending IPO instrument has actually entered the listed universe
    - use it to enrich exchange / active-status / listing-date metadata after first trade support appears
    - do not confuse it with a future event source; it is for instrument-master follow-through after the event
- **SEC EDGAR** should be treated as a free **pipeline/enrichment source**, not the canonical IPO calendar:
  - SEC search/filings tools and APIs give us free access to registration/prospectus workflows
  - this is useful for tracking forms such as:
    - `S-1`
    - `S-1/A`
    - `F-1`
    - `F-1/A`
    - `424B*`
  - this will help us detect issuers moving through the IPO funnel earlier than a structured calendar sometimes will
  - but EDGAR should not be presented as an exact listing-date authority because it is filing-driven, not listing-calendar-driven
- **Massive market-holiday data** is also worth folding into the same subsystem:
  - `GET /v1/marketstatus/upcoming` is forward-looking and included in Stocks Basic Free
  - this is not an IPO feed, but it is a good example of a free market-calendar input that belongs in the same page/widget layer
- **Finnhub** can be kept as an evaluation candidate, not a committed provider yet:
  - official docs expose `/calendar/ipo?from=...&to=...`
  - Finnhub also offers a free API key
  - but we should not commit to building against it until we explicitly verify that the free tier truly allows this endpoint in practice and with acceptable quotas/terms

Product goals:
- Build a **forward market-events calendar** that is broader than today’s instrument-specific event history.
- Make IPOs a first-class event family with both:
  - calendar-facing UX
  - instrument-universe bootstrap implications
- Ensure this subsystem explicitly answers two different user questions:
  - **what is coming up?**
  - **what newly tradable instruments should now exist in our universe?**
- Support both:
  - a full page
  - a compact widget
- Treat this subsystem as part of both:
  - market research / monitoring
  - instrument-master / discovery

What remains:

- Add a new provider capability for **forward market events**, distinct from the current instrument-event history model:
  - examples:
    - `market_event_calendar`
    - or a clearly named equivalent
  - do not overload the current per-instrument event fetch path with market-wide future events
  - allow multiple providers to contribute to the same normalized market-event feed

- Add provider implementations for the free sources that actually make sense:
  - `massive`
    - ingest `reference/ipos`
    - support status filtering and pagination
    - store the provider payload and provider-specific status semantics
    - use this as the primary free IPO backbone
  - `alphavantage`
    - ingest `IPO_CALENDAR`
    - later also ingest `EARNINGS_CALENDAR` into the same broader market-events system
    - ingest `LISTING_STATUS` into the instrument-master follow-through side so future IPO placeholders can be promoted once the listing is real
    - normalize CSV payloads into the same event schema
  - `edgar`
    - add a supplementary IPO-pipeline detector for filings such as `S-1`, `S-1/A`, `F-1`, `F-1/A`, `424B*`
    - use this to enrich “watchlist of possible upcoming listings” rather than to claim exact listing dates
  - optionally `finnhub`
    - only after free-tier access is explicitly validated in practice
    - if validated, use it as another corroborating structured IPO source, not as the sole source of truth

- Introduce a normalized **market event** model that is not equity-price-history-centric:
  - event family:
    - `ipo`
    - `direct_listing`
    - `market_holiday`
    - later:
      - `earnings_calendar`
      - `fed/cpi/macro`
      - `lockup_expiry`
      - `index_rebalance`
      - `etf_rebalance`
  - event dates/timestamps:
    - announced date
    - expected listing date
    - actual listing date
    - last updated timestamp
  - lifecycle/status:
    - rumor
    - pending
    - priced
    - new/live
    - history/completed
    - postponed
    - withdrawn
    - direct listing
  - identifiers:
    - provisional ticker
    - issuer name
    - exchange / MIC
    - ISIN / CUSIP / other identifiers where available
    - SEC CIK / filing references where available
  - economics:
    - expected price range
    - final issue price
    - shares offered
    - offer size
    - currency
  - provenance:
    - source provider
    - source URL
    - raw payload snapshot
    - confidence / reconciliation state

- Build a reconciliation strategy across providers so we do not create duplicate IPO events or duplicate future instruments:
  - match first by:
    - ISIN
    - CUSIP
    - CIK
    - exchange + ticker + listing date
  - then by conservative issuer-name similarity only as a weaker fallback
  - keep provider-specific aliases and raw source ids for auditability
  - preserve conflicting provider claims instead of silently overwriting them

- Materialize **pre-listing instruments** as a first-class concept:
  - upcoming IPOs should be able to create instrument records before bars exist
  - these should be clearly marked as:
    - pre-listing / pending
    - not chartable yet if no price history exists
    - event-driven / future-facing rather than provider-price-history-backed
  - when the instrument actually lists and our normal instrument providers begin supporting it:
    - reconcile the pre-listing placeholder with the real listed instrument
    - preserve the IPO event history and source provenance
  - this should directly improve the instrument universe by letting us know about new tickers before first trade data arrives
  - the reconciliation flow should intentionally combine:
    - future event sources (Massive / Alpha IPO calendar / EDGAR pipeline)
    - post-listing confirmation sources (Alpha `LISTING_STATUS`, normal instrument search/materialization, regular metadata providers)
  - this lets us support the whole lifecycle:
    - rumor / pending
    - expected listing
    - listed but still thinly-covered
    - fully normal instrument in the broader platform

- Extend the calendar UX from instrument-specific history into a **market-wide forward planner**:
  - page:
    - list/calendar timeline of upcoming IPOs and other future market events
    - filters by event type, date range, exchange, status, and provider
    - sort by expected date, provider update recency, or event importance
    - search by issuer name, ticker, or identifier
  - widget:
    - compact “upcoming IPOs / market events” surface for dashboard use
    - configurable horizon such as:
      - 1 week
      - 1 month
      - 3 months
    - should be able to exist both:
      - as a general market-events widget
      - as a narrower “upcoming IPOs” widget for users specifically tracking future listings
  - interaction:
    - clicking a future IPO instrument should open its instrument details page if no chart exists yet, and the chart only once price history exists
    - hovering/clicking a market event should expose provenance and confidence:
      - which provider(s) reported it
      - whether the date is tentative or confirmed
      - whether the instrument is already listed in our master

- Make the subsystem useful for portfolio/risk workflows:
  - let users inspect upcoming IPOs and future event clusters by date
  - later allow strategies/radar/alerts to pause or adapt around forward event windows
  - surface event density such as:
    - many IPOs this week
    - major holiday-shortened week
    - large concentration of future earnings in selected watchlists
  - allow simple “watch ahead” workflows such as:
    - all upcoming IPOs in the next 14/30/90 days
    - all pending listings that do not yet exist as normal instruments
    - all events affecting a chosen exchange or watchlist
    - all events whose dates or statuses changed since last refresh

- Add explicit coverage semantics so users know how far ahead each provider can see:
  - Massive IPO coverage:
    - structured historical + upcoming, with status lifecycle
  - Alpha Vantage IPO coverage:
    - next 3 months only
  - Alpha Vantage earnings coverage:
    - 3/6/12 month forward windows
  - Alpha Vantage listing-status coverage:
    - post-listing universe confirmation, not a future-calendar source
  - EDGAR pipeline coverage:
    - filing-driven, not guaranteed listing-date accuracy
  - the UI should not pretend that all providers offer the same horizon or confidence
  - the UI should also clearly distinguish:
    - **future calendar confidence**
    - **instrument-master readiness**
    - **price-history readiness**

- Keep geography segmented in the design:
  - implement US first
  - keep provider/region fields in the schema so we can later add:
    - EU IPO/event sources
    - APAC IPO/event sources
  - do not hard-code the model to US-only assumptions even though the first provider stack will be US-heavy
  - for now, explicitly document that:
    - reliable free structured forward IPO coverage is strongest for the US
    - EU / APAC support should remain adapter-ready in the schema but not be promised until solid free sources are identified

Why this was deferred:
- The platform already has the beginnings of a calendar/event story, but not the forward-looking market-wide event model this needs.
- The best free implementation is broader than “just add one endpoint”; it touches:
  - providers
  - storage
  - instrument discovery/materialization
  - dashboards
  - calendar UX
  - later strategy/risk workflows
- It deserves a focused implementation pass instead of being quietly bolted onto the existing per-instrument event tables.

### 10. Expand provider chain seeding and scheduling for bulk universe refresh
Status: `In progress — full completion contract still open`

Context:
- Five new providers (Alpaca, FRED, Binance, CoinGecko, EDGAR) are registered but the
  PROVIDER_CHAIN_SEEDS defaults in config.py are still empty `{}`.
- The scheduler tasks (instrument_sync_tasks, data_tasks) are not yet wired to use the new
  providers in an ordered way for daily refresh cycles.

What remains:
- Set production-ready `PROVIDER_CHAIN_SEEDS` defaults per capability so new providers
  are automatically preferred over yfinance without manual env override.
- Review `INSTRUMENT_DAILY_METADATA_CAP` and `INSTRUMENT_DAILY_IDENTIFIER_CAP` — these
  may need tuning when Alpaca-discovered universe (~9 000 equities) is active.
- Add a scheduled daily task for Alpaca OHLCV batch refresh (leveraging the multi-symbol
  endpoint to refresh thousands of equities in ~10–15 requests).
- Add a scheduled task for corporate actions sync (Alpaca splits/dividends).
- Add a scheduled task for EDGAR earnings history enrichment for newly added instruments.

Why this was deferred:
- The providers are implemented and registered; wiring the scheduler is a separate operational
  concern that should be done alongside end-to-end testing of the new provider stack.

### 11. Custom instrument baskets, ETF holdings navigation, and breadth analysis
Status: `Planned`

Context:
- The platform already supports individual instruments and expression-based synthetics (e.g., `=SPY-QQQ`).
- The next natural building block is **user-defined instrument baskets**: named, weighted collections of instruments that can be treated as a first-class platform object, similar to a custom ETF.
- Beyond pure user-defined baskets, real ETFs carry composition data — the platform should eventually be able to materialise an ETF's holdings as a basket automatically, enabling holdings navigation ("show me all Nasdaq 100 constituents").
- Once baskets exist as objects, they become a natural surface for **breadth analysis**: computing aggregate technical properties across holdings to get a collective health view of the basket as a whole.
- These three concerns — basket construction, ETF holdings navigation, and breadth analysis — are closely coupled and should share a common data model from the start.

---

#### 10a. Custom basket construction

What this should become:
- A named, user-owned collection of instruments with associated weights.
- Weights can be equal (platform distributes 1/N automatically) or fully custom (user assigns fractions that must sum to 1.0, or raw market-value notional if the UX calls for it).
- A basket can be used anywhere an instrument is referenced: charted as a synthetic price series (using the weighted sum or index-relative formula), added to a watchlist, used as a screener universe, used as a breadth analysis target, or used as a Strategy Lab universe.
- Baskets are distinct from expression instruments (`=A-B`, `=A/B`) which are formula-based rather than weighted-membership-based.

What remains:

Backend:
- Baseline basket persistence and user-owned CRUD now exists:
  - `basket` and `basket_member` models support user-owned manual baskets and read-only system-managed ETF-derived baskets
  - manual baskets can be created, updated, listed, read, and deleted through authenticated APIs
  - member edits replace the full member set and require existing resolved instruments; arbitrary/unresolved typed symbols are rejected at the API boundary
  - equal-weight baskets store null member weights and can be interpreted as 1/N downstream
  - custom-weight baskets require every member to provide a weight and the weights must sum to 1.0
  - duplicate instruments are rejected
  - read-only/system-managed baskets cannot be edited or deleted through the manual basket API
  - auto-classification currently sets sector/industry when all members share the same metadata values
- Strategy Lab can now use a basket as a static universe through `universe_config.basket_id`, including coverage preview, saved strategy versions, run execution, and run-subset restriction to basket members.
- Still expand the basket API beyond the baseline where needed:
  - partial member operations if the UI benefits from add/remove/reweight endpoints rather than full member replacement
  - market-cap-weighted basket semantics once reliable constituent market-cap data is available
  - richer classification labels/tags for mixed-sector/thematic baskets
- Basket synthetic OHLCV now exists on the backend:
  - `GET /api/v1/baskets/{basket_id}/ohlcv/{timeframe}` returns a rebased-to-100 weighted cumulative-return series using aligned member OHLCV bars
  - equal-weight baskets are interpreted as 1/N
  - custom/source-weight baskets normalize explicit weights before computing the series
  - the first viable aligned bar is 100, making basket behavior easy to compare against constituent or benchmark returns
  - still wire this endpoint into the main Chart view so users can open a basket as a normal chart surface

Frontend:
- Strategy Lab now exposes Basket as a universe type and persists/loads `basket_id` from the visual builder.
- A dedicated basket builder UI now exists at `/baskets` and is accessible from the sidebar:
  - list manual and ETF-derived baskets
  - create new user-owned baskets
  - add instruments through the platform search picker
  - choose equal or custom weighting
  - edit custom weights with a real-time allocation indicator and sum validation
  - delete manual baskets through a platform modal
  - display ETF-derived baskets as read-only system-managed baskets
- Weight editor still needs richer interaction if useful:
  - drag/reorder members
  - bulk equalize/rebalance helper
  - optional add/remove/reweight actions that do not require replacing the entire member set
- Basket detail view: list all members, their weight, and a sparkline or mini-stat row per member.
- Ability to open a basket in the chart view as a synthetic price series.

---

#### 10b. Basket sector / industry classification

Context:
- If every member of a basket shares the same GICS sector (or industry), the basket clearly belongs to that sector/industry and can be classified automatically.
- When members span multiple sectors/industries, automatic classification breaks down. The right answer here is not fully settled:
  - One option is a user-selectable custom label from a predefined list (including a catch-all like "Multi-sector" or "Thematic").
  - Another option is a tag system where the basket carries multiple sector/theme tags.
  - A third option is purely user-free-text labeling.
  - Which of these is best depends on how the classification is used downstream (breadth grouping, screener filtering, radar slicing). This should be revisited once the downstream use cases are clearer.

What remains:
- Add a `sector` and `industry` field to the basket model, nullable.
- On basket creation/save, run an auto-classification pass: if all members share the same GICS sector, populate the field automatically. If they share the same industry sub-sector, populate industry as well.
- If members are mixed-sector, leave classification null and surface a prompt in the UI inviting the user to set a custom classification label.
- Build a lightweight classification UX: a picker or text field that offers predefined sector names plus a free-text "Thematic / Custom" escape hatch.
- Revisit and expand this once the breadth analysis feature (10c) and radar filter/slice feature (item 5) make it clear what the classification taxonomy needs to look like.

---

#### 10c. ETF holdings navigation and auto-materialised baskets

Context:
- Real ETFs are instruments in the platform's DB. Their holdings are composition data that can be sourced from providers (e.g., ETF.com, iShares disclosures, State Street, or financial data providers that expose holdings).
- Once ETF holdings data exists in the platform, an ETF can be treated as a system-managed basket automatically: the platform creates or refreshes a basket representing the ETF's current composition and weights.
- This enables: "click SPY, see all 503 holdings and their weights". Or: "click QQQ, open all Nasdaq 100 constituents as a basket and then chart any one of them".
- The holdings-navigation flow is especially valuable for users who want to do their own constituent-level research: e.g., scan through all S&P 500 members to find technically interesting setups, or look at which Nasdaq 100 members are near 52-week highs.
- ETF holdings are also an important low-cost proxy for index-constituent universes:
  - exact historical index membership, such as Russell 3000 constituents, is often licensed and expensive
  - ETF issuers frequently disclose current holdings, and regulatory filings can provide historical holdings snapshots
  - this gives the platform a practical starter path for "close enough" index-universe workflows without requiring expensive index-data contracts on day one
  - the product must clearly label these as ETF-holdings proxy universes, not official index-constituent universes

What remains:

Implementation status:
- Baseline ETF holdings infrastructure now exists:
  - persistent ETF profile, raw artifact, holdings snapshot, holding row, adapter-state, and ETF/index-proxy mapping tables
  - authenticated APIs for listing/searching ETFs with holdings, latest snapshots, available dates, nearest point-in-time snapshots, constituent timelines, unresolved rows, requested-range coverage summaries, manual ingestion, CSV ingestion, ETF profile routing updates, and manual refresh triggering
  - canonical parser support for common issuer CSV exports and simple XLSX/OpenXML holdings workbooks
  - metadata-only lightweight materialization of ETFs and holdings constituents through the existing instrument mastering model
  - explicit source/provenance fields, `as_of_date`, `known_at`, `published_at`, source quality, completeness, raw artifact retention, and adapter health tracking
  - scheduled refresh hook behind `ETF_HOLDINGS_REFRESH_ENABLED`
  - a usable free-source baseline where ETF profiles refresh through provider-specific holdings adapters instead of arbitrary profile-level download URLs
  - Chart page holdings panel with source/freshness/resolution metadata, filter/sort, selected holding details, previous/next navigation, and explicit constituent open actions
  - Strategy Lab can use ETF holdings as a strategy universe through the visual builder:
    - latest available snapshot mode
    - latest snapshot on/before a chosen date
    - dynamic point-in-time mode for rules backtests, where membership is filtered by the latest holdings snapshot known at each bar date
    - an explicit dynamic-universe constituent-removal policy for leaving positions open at the last eligible mark or realizing them as `constituent_removed` exits
    - dynamic-run result attribution with `dynamic_universe` snapshot metadata plus execution-log fields that identify the ETF snapshot, composition date, known-at timestamp, and membership status behind entries/removal exits
    - baseline frontend surfacing of dynamic membership attribution in the Strategy Lab execution log reason cell and reason filter search values
  - ETF holdings snapshots can be materialized into read-only, system-managed baskets through the backend basket model and API
  - user-owned manual basket CRUD exists on the backend, and Strategy Lab can consume baskets as static universes through the visual builder
  - ETF-derived system baskets can opt into dynamic ETF history in Strategy Lab through `universe_config.basket_snapshot_mode = "dynamic"`; this delegates point-in-time membership to the basket's source ETF holdings profile instead of treating the materialized basket as only a frozen member list
  - user-owned/manual baskets now persist composition snapshots on create/update and expose basket snapshot history through the backend API
  - Strategy Lab can opt manual baskets with stored composition snapshots into dynamic point-in-time replay through `basket_snapshot_mode = "dynamic"`
  - a basket builder/editor workspace now exists for user-owned baskets, and ETF-derived baskets are visible as read-only entries
  - a first backend basket synthetic OHLCV endpoint exists for rebased-to-100 basket return series
  - Chart can open basket synthetic series through `/chart/BASKET:{id}` from the basket builder, using the backend weighted basket OHLCV endpoint without treating the basket token as a normal watchlist/recent instrument
  - an adapter registry seam exists; only concrete provider-specific ETF issuer adapters are registered, and adapter-state health is persisted per profile/provider
  - issuer-aware CSV adapter routes now exist for major issuer keys:
    - ETF profiles can resolve holdings downloads from explicit issuer URLs, URL templates, issuer product ids, and issuer-specific file names instead of requiring every route to be stored as a raw `holdings_url`
    - ETF profiles can also provide issuer product/fund page URLs; the adapter can discover linked CSV/XLSX holdings files from those pages and then ingest the resolved file
    - ARK-style holdings file-name route construction is implemented against ARK's current public `assets.ark-funds.com` CSV files for known ARK ETF symbols
    - iShares/BlackRock product-id and State Street/SPDR symbol-based daily workbook routes are implemented as backend-reachable public constructors
    - issuer product-page discovery is implemented for explicit product URLs and for candidate symbol-addressable page templates; only backend-reachable routes should be treated as ready after live/provider probing
    - current backend-reachable live-tested issuer routes cover SPDR, iShares/BlackRock, ARK, VanEck, and Global X; these are the only issuer adapters currently treated as supported default routes
    - iShares/BlackRock now uses the current BlackRock product-data JSON holdings API for live-backed default routes; tested seeded product ids include IVV and IWM, so selecting IWM can bootstrap a full holdings snapshot on an empty branch instead of falling back to top-holdings page data
    - the live provider test matrix covers every registered issuer adapter, either as a successful backend-reachable route or as an explicit candidate-route gap, so unsupported providers cannot silently masquerade as supported
    - Invesco has an explicit JSON parser for configured source URLs, but its currently embedded public `dng-api` holdings endpoint returns HTTP 406 to backend requests and must not be auto-advertised as ready
    - Vanguard and Schwab candidate product pages remain useful routing hints, but backend-reachable full-holdings extraction is not yet live-proven and should remain a provider-support gap until current public routes can be fetched and parsed reliably
    - the intended architecture is one provider-specific implementation per ETF issuer/provider, just like market-data providers; explicit product URLs, issuer discovery feeds, and profile-level URL templates remain useful provider-configuration seams while that provider-specific catalogue is built, but they are not a substitute for claiming provider support
    - each provider implementation should be promoted to supported only when backend-reachable live tests prove that the provider-specific route fetches full holdings reliably
    - issuer adapters probe whether enough route metadata exists before refresh, and profiles without enough metadata are marked as needing issuer route configuration instead of silently pretending refresh support exists
    - admin `POST /api/v1/etf-holdings/{symbol}/probe-adapter` exposes route-readiness status, resolved source URL, confidence, and missing identifier requirements before a refresh is attempted
    - fetched issuer artifacts now run through explicit identity validation before ingestion:
      - ETF profiles can provide expected artifact identifiers such as expected ETF/fund symbol, name, CUSIP, or ISIN through `provider_aliases`
      - if expected identifiers are configured, the raw downloaded artifact must contain at least one of them before a snapshot is stored
      - generic downloaded table metadata extraction can infer ETF identity from conservative source fields such as two-column preamble metadata or explicit `Fund Ticker` / `ETF Name` style columns, while ignoring generic constituent `Ticker` columns
      - matched/unverified validation status is stored in snapshot/raw-artifact legal metadata for auditability
      - mismatched artifacts fail refresh rather than silently creating a holdings snapshot for the wrong ETF
    - successful issuer-adapter refreshes persist source URL, parser version, row counts, composition date, and adapter-state health
    - failed issuer-adapter refreshes classify common provider blocking/transient states such as HTTP 429, 403, and server/time-out failures into persisted adapter health, and successful retries clear stale rate-limit/blocking state
    - admin `GET /api/v1/etf-holdings/{symbol}/adapter-state` exposes persisted adapter health, including last success/failure, source URL, parser/count metadata, completeness, and rate-limit/blocking state
  - admin SEC N-PORT/N-PORT-P-style XML ingestion now exists as a reconstruction primitive:
    - raw SEC filing XML can be parsed into canonical holdings rows
    - report dates are inferred from the filing where possible
    - CUSIP/ISIN/SEDOL, shares, market value, currency, asset category, and percent-of-value weights are normalized where present
    - snapshots are stored as `sec_nport_reconstructed_holdings` with filing source identifiers, source URL, raw XML, and known/published timestamps preserved
  - admin legacy SEC N-Q/N-CSR-style XML/table ingestion now exists as an older-history reconstruction primitive:
    - simple table-like legacy filing XML can be parsed into canonical holdings rows
    - period/report dates, CUSIP/ISIN/SEDOL, shares, market value, currency, asset/security type, and percent-of-net-assets weights are normalized where present
    - snapshots are stored as `sec_legacy_reconstructed_holdings` with filing source identifiers, source URL, raw XML, and known/published timestamps preserved
  - an admin EDGAR N-PORT backfill primitive now exists:
    - ETF profiles with `sec_cik` can query SEC submissions metadata for recent N-PORT filings and older SEC submissions `files` archive pages
    - discovered N-PORT primary XML documents are downloaded, parsed, and ingested through the same filing-reconstructed holdings path
    - discovered legacy N-Q/N-CSR-style primary XML/table documents are downloaded, parsed, and ingested through the legacy filing-reconstructed holdings path
    - backfill jobs and accession-level filing state are persisted, making repeated backfills duplicate-safe and auditable
    - per-run summaries report discovered, ingested, skipped, and failed filings, with admin endpoints to inspect recent jobs and per-filing state
    - a bulk/admin SEC backfill endpoint and scheduled worker hook exist for processing ETF profiles with configured SEC CIKs under bounded limits
  - Screener and Radar can consume manual or ETF-derived baskets as universe inputs, alongside Strategy Lab basket/ETF snapshot universe support
  - Screener and Radar now expose frontend controls for selecting manual or ETF-derived baskets as run universes:
    - Screeners can save/load basket universes from the visual builder through `universe_basket_id`
    - Radar can run scans against either all instruments or a selected basket through the existing run action
  - the Chart ETF holdings panel now provides a compact browse workspace rather than only a flat table:
    - users can select a holding and inspect mini-stats such as weight, market value, shares, venue, identifiers, row type, resolution state, and resolution notes
    - users can move through the currently filtered/sorted holdings with previous/next controls
    - opening a constituent chart is now an explicit action from the selected holding details
  - a dedicated `/etf-holdings` browse workspace now exists for larger holdings lists:
    - ETF profiles with stored holdings can be searched and selected from a dedicated holdings surface
    - holdings rows are loaded through a server-side paginated/searchable/sortable API instead of requiring the frontend to load the whole snapshot
    - users can page through holdings, search by symbol/name/CUSIP/ISIN/SEDOL, sort by position/weight/value/shares/symbol/name/resolution, inspect selected holding details, and open a constituent chart
    - users can compare the selected snapshot against another stored snapshot to inspect holdings additions, removals, and weight changes through a dedicated diff view
    - the diff workspace now includes a first cross-snapshot research-summary layer with gross churn, total added/removed weight, total upweights/downweights, and largest additions/removals/reweights
    - the workspace now includes a first weight-evolution panel that ranks top constituent weight movers across stored snapshots and shows each mover's weight path over the available snapshot range
    - constituent timeline API responses now include per-point weight delta from the previous observed snapshot, making individual constituent reweighting paths inspectable without client-side recomputation
    - the workspace now includes a first turnover timeline that batch-navigates adjacent historical snapshots and summarizes each transition's churn, additions, removals, reweights, and top movers without requiring users to manually compare every pair
    - cross-ETF overlap analytics now exist through `POST /api/v1/etf-holdings/overlap-summary`, comparing selected ETF snapshots for shared/unique constituents, Jaccard overlap, shared weight, minimum-overlap weight, and top shared holdings
    - many-ETF overlap matrix analytics now exist through `POST /api/v1/etf-holdings/overlap-matrix`, returning row/column ETF symbols, per-cell overlap metrics, closest/most-distinct peers, and highest/lowest overlap pair callouts for heatmap-style research
    - overlap matrix requests can now expand their ETF set from profile metadata such as issuer, fund family, and search query instead of requiring every ETF symbol to be listed manually
    - the ETF holdings workspace now exposes a first compact overlap panel where users can select peer ETFs from the loaded profile list and inspect pairwise overlap cards plus a heatmap-style overlap matrix
    - the overlap panel also exposes a first issuer/family/search expansion flow for server-side overlap matrix comparisons without manually selecting every ETF
  - Remaining work is now primarily about downstream consumption and long-tail source maintenance:
    - source hardening baseline is now in place:
      - issuer adapters reject malformed/empty holdings artifacts instead of silently creating useless snapshots
      - adapter failure state distinguishes provider blocking/rate limits from parse/malformed failures
      - common issuer schema variants are normalized beyond the initial ticker/name/weight shape, including security identifier/CUSIP-like columns, issuer/title fields, fund weight aliases, shares/principal aliases, market-value aliases, local currency, country, exchange, cash rows, accounting negatives, and disclaimer-row skipping
      - legacy SEC parsing handles simple XML/table filings, simple HTML tables, split identity/value rows, month-name report dates, accounting negatives, and value-in-thousands schedules
      - ZIP/XLSX/CSV issuer artifacts, product-page discovery, fetched-artifact identity validation, route probes, adapter catalog inspection, and persisted adapter health form the current robustness baseline
    - remaining source work is long-tail maintenance rather than a core gap: unusual issuer-specific schemas, non-tabular/PDF-like disclosures, automatic website discovery beyond explicit configured feeds, and extra direct-download constructors where product-page discovery or configured feeds prove insufficient
  - richer Chart basket UX beyond the initial synthetic series route, such as synthetic basket metadata and better comparison/watchlist semantics
  - dynamic point-in-time Strategy Lab ETF/basket universes that rebalance through historical holdings snapshots during simulation, rather than using only a static snapshot
    - implemented ETF holdings baseline: Strategy Lab rules backtests can opt into `universe_config.etf_holdings.snapshot_mode = "dynamic"` from the visual builder to resolve the latest point-in-time ETF holdings snapshot for each bar date, avoiding look-ahead by honoring snapshot `known_at`
    - implemented ETF-derived basket baseline: Strategy Lab can save/load an ETF-derived basket with `basket_snapshot_mode = "dynamic"` and replay the source ETF profile's point-in-time holdings snapshots during rules backtests
    - implemented manual basket-history baseline: manual basket create/update operations persist composition snapshots, and Strategy Lab can replay those basket snapshots point-in-time when `basket_snapshot_mode = "dynamic"`
    - implemented ETF constituent-removal policy: dynamic ETF runs can either leave positions open at the last eligible mark or realize them as `constituent_removed` exits when the ETF no longer carries that instrument by run end
    - implemented baseline dynamic attribution: result summaries include the dynamic ETF snapshot set, execution-log rows include snapshot/membership fields showing which point-in-time ETF holdings snapshot drove entries and removal exits, and the Strategy Lab execution log surfaces this context compactly
    - still needed: richer basket rebalance policy controls, historical basket snapshot editing/import UX, and deeper attribution drilldowns/specialized filtering beyond the baseline execution-log context
  - richer cross-snapshot/cross-ETF holdings research beyond the current diff/summary, turnover timeline, top-mover weight-evolution views, constituent timeline deltas, overlap matrix API with issuer/family/search expansion, and compact overlap/matrix/family panel, especially saved comparison sets and deeper exposure clustering

Data / provider side:
- Implement ETF holdings ingestion as a **free-source-first** capability, not as a dependency on a paid holdings aggregator:
  - the platform should be able to build a useful ETF holdings database using public issuer disclosures and SEC filings before any paid holdings API is considered
  - paid API aggregators such as FMP, EODHD, Alpha Vantage, Finnhub, or ETF.com-style datasets can remain optional future accelerators/fallbacks, but should not be required for the baseline feature
  - premium official index constituent providers should be reserved only for workflows that explicitly require exact point-in-time index membership rather than ETF-holdings proxy membership
  - this roadmap item should therefore be treated as a real ingestion product, not merely a wrapper around one commercial data provider
- Split the ETF holdings problem into two complementary free-source tracks:
  - **historical backfill from SEC/EDGAR-hosted filings**
    - use SEC N-PORT / N-PORT-P structured data as the primary free structured historical source from the N-PORT era
    - use legacy SEC filings such as N-Q and N-CSR where practical to reconstruct older lower-frequency holdings history before N-PORT
    - preserve the fact that SEC-derived history is filing/reported holdings data, not official index membership
    - preserve both the holdings `as_of_date` and the date the filing became publicly available / known to the platform so Strategy Lab can avoid look-ahead bias
    - expect SEC backfills to be lower-frequency and delayed relative to issuer daily/weekly holdings files
    - treat SEC backfill parsing as a separate pipeline from issuer-current ingestion because the schemas, file formats, timing, and quality controls are different
    - baseline N-PORT/N-PORT-P XML parsing, manual/admin ingestion, recent and archived SEC submissions discovery/download ingestion, scheduled/bulk backfill hooks, and persistent accession/job dedupe now exist
    - baseline N-Q/N-CSR-style legacy XML/table parsing and manual/admin ingestion now exists for older pre-N-PORT history
    - baseline legacy SEC HTML schedule-of-investments table parsing now exists for simple EDGAR HTML filings with recognizable issuer/ticker/CUSIP/shares/value/percent columns
    - legacy SEC HTML parsing now also handles a common split-row schedule shape where security identity/CUSIP appears in one row and shares/value/percent appear in the following numeric row
    - automated EDGAR discovery/download/backfill orchestration for legacy N-Q/N-CSR-style filings now exists, including duplicate-safe accession state and bulk processing
    - still broaden legacy parser coverage for additional filing/table shapes, deeply nested/footnoted HTML filings, and PDF-like documents beyond the simple HTML table path
  - **forward daily/weekly snapshots from ETF issuer/provider disclosures**
    - build individual adapters for major US ETF issuers and fund families that publish holdings files or holdings pages
    - target iShares/BlackRock, State Street/SPDR, Vanguard, Invesco, Schwab, First Trust, Global X, VanEck, ARK, WisdomTree, ProShares, Direxion, JPMorgan, Dimensional, PIMCO, Franklin, Fidelity, and other large US-listed ETF sponsors over time
    - let each adapter understand that issuer's own URL structure, downloadable file formats, date fields, disclaimers, cash rows, derivative rows, currency fields, and naming conventions
    - store raw downloaded files/pages/artifacts before normalization so parser changes can be audited and historical ingestions can be replayed
    - schedule refreshes daily where the issuer appears to publish daily holdings, and weekly where daily refresh is unnecessary or not reliably available
    - keep the adapter framework tolerant of issuer website changes, because free public issuer files are valuable but brittle
- Provider-specific holdings adapter framework status:
  - a registry and common adapter interface now exists
  - the previous `configured_csv_url` fallback has been retired; arbitrary profile-level download URLs are not treated as provider support
  - major issuer adapter keys now use isolated provider-specific route adapters that resolve from that provider's own known route shape, product ids, issuer-specific file-name hints, or product-page discovery
    - issuer-aware adapters can now discover linked holdings CSV/XLSX/ZIP files from configured issuer product/fund page URLs before ingesting
    - product-page holdings discovery now scans conservative URL-bearing attributes and quoted page configuration strings, not only literal anchor `href` links, while still requiring holdings/portfolio/constituent file hints
  - concrete issuer-specific URL constructors now exist for:
    - ARK file-name based public CSV holdings files
    - iShares/BlackRock product-id based public CSV holdings files
    - State Street/SPDR symbol-based public daily holdings XLSX files
  - inferred issuer product-page templates now exist for:
    - Global X symbol-addressable fund pages, currently live-tested through product-page discovery
    - VanEck symbol-addressable holdings/download routes, currently live-tested through deterministic holdings workbook download
    - Vanguard symbol-addressable ETF profile pages as candidate route hints only, pending backend-reachable holdings extraction
    - Schwab symbol-addressable product pages as candidate route hints only, pending backend-reachable holdings extraction
    - Invesco explicit holdings source URLs through the JSON parser only; automatic backend route support is not currently live-backed because the embedded public API returns HTTP 406 to backend requests
  - admin route-readiness probing exists and persists adapter-state health for ready and under-configured profiles
  - admin adapter-state inspection now exposes persisted adapter health, including HTTP rate-limit/blocking classification from failed refreshes and clearing on successful retry
  - admin adapter-catalog inspection now exposes registered adapter keys, route identifiers, required identifiers, supported artifact formats, parser confidence, and explicit dated-fetch/ETF-discovery capability flags
  - issuer adapters now support explicit dated holdings URL templates, allowing admin-triggered fetch/ingest for a requested composition date when an issuer archive URL pattern is known
  - issuer adapters now support explicit issuer fund-list discovery feeds:
    - admin `POST /api/v1/etf-holdings/discover` can fetch a configured issuer CSV/XLSX/ZIP fund-list feed, parse ETF identity/route columns, materialize lightweight ETF instruments, and upsert ETF profiles
    - discovered profiles preserve issuer product ids, product URLs, holdings URLs, dated holdings URL templates, CUSIP/ISIN identifiers, discovery source URLs, and the raw discovery row in profile metadata
    - discovered profiles now also preserve SEC CIK/series/class ids and FIGI/composite/share-class FIGI aliases where the fund-list feed provides them, keeping issuer discovery connected to EDGAR backfills and instrument mastering
    - this is a deliberate explicit-feed ingestion path, not automatic broad website crawling or guessed ETF discovery
  - explicit fetched-artifact identity validation exists for profiles that provide expected fund identifiers
  - conservative generic fetched-artifact identity extraction exists for preamble metadata and explicit fund/ETF identity columns in downloaded table files
  - simple XLSX/OpenXML holdings workbooks and ZIP archives containing CSV/XLSX holdings files now ingest through the same common parser/identity-validation path without adding a spreadsheet dependency
  - source-hardening baseline is now in place:
    - malformed/empty issuer artifacts fail refresh and persist adapter failure state instead of producing empty snapshots
    - common issuer schema aliases, CUSIP-like security identifiers, cash rows, accounting negatives, and non-holding disclaimer rows are handled by the common parser
    - SEC legacy reconstruction handles simple XML/table filings, simple HTML tables, split identity/value rows, month-name dates, and value-in-thousands schedules
    - live issuer smoke tests now exist behind `RUN_LIVE_ETF_HOLDINGS_TESTS=1`, intentionally separated from deterministic CI so provider drift can be checked against real issuer websites/files without making the normal suite network-dependent
    - current live suite passes against backend-reachable public issuer routes for SPDR, iShares, ARK, Global X, and VanEck; iShares has an inline top-holdings parser for the current HTML-shell response, ARK uses its public assets CSV files, and VanEck uses its deterministic holdings workbook download route
  - still ongoing as source-coverage work, not merely incidental maintenance: unusual issuer-specific schemas beyond the common parser, richer issuer-specific identity extraction for non-tabular pages/PDFs/unusual issuer metadata formats, direct-download/API constructors for issuers where product-page discovery is insufficient, automatic issuer-specific historical-date discovery beyond explicitly configured dated URL templates, automatic per-issuer ETF discovery beyond explicit configured fund-list feeds, and backend-reachable live routes for currently blocked/non-static issuers such as Vanguard, Schwab, Invesco, First Trust, WisdomTree, ProShares, Direxion, JPMorgan, Dimensional, PIMCO, Franklin, and Fidelity
- Continue expanding the provider-specific holdings adapter framework:
  - each adapter should expose a common interface:
    - discover supported ETFs
      - implemented baseline: adapters can ingest explicitly configured issuer fund-list discovery feeds through the admin discovery endpoint, parse common ETF identity/route columns, and upsert ETF profiles without relying on ticker-only guessing
    - resolve issuer product id / slug / URL for a known ETF
    - fetch latest holdings
    - fetch holdings for a specific date when the issuer supports it
      - implemented baseline: issuer adapters can fetch a specific date from an explicit profile-level dated URL template using placeholders such as `{date}`, `{date_yyyymmdd}`, `{year}`, `{month}`, and `{day}`
    - parse raw holdings into canonical rows
    - report source metadata and parser confidence
    - probe whether an ETF belongs to that issuer/provider path
  - adapter output should normalize:
    - constituent symbol
    - constituent name
    - CUSIP / ISIN / SEDOL where available
    - weight
    - shares held
    - market value
    - asset class / holding type
    - currency
    - country / exchange where available
    - cash, futures, swaps, options, collateral, and other non-equity rows
    - source row id / source row hash
      - implemented: holdings rows persist a per-snapshot `source_row_hash` and expose it through API outputs for audit/replay tooling
  - adapter output should also preserve source-specific fields that do not fit the canonical schema yet so we do not throw away useful data too early
  - implemented for observability: admin adapter-catalog endpoint reports source metadata, parser confidence, supported formats, route identifiers, and which interface capabilities are still unavailable per adapter
- Add an ETF identity and adapter-routing layer so the platform knows which free issuer/provider path to use for each ETF:
  - never infer issuer solely from ticker
  - master each ETF using the existing instrument identity model plus ETF-specific identifiers:
    - symbol
    - exchange / MIC
    - fund name
    - issuer / sponsor / adviser / fund family when known
    - CUSIP
    - ISIN
    - FIGI / composite FIGI / share-class FIGI where available
    - SEC CIK
    - SEC series id
    - SEC class id
    - provider aliases and issuer product ids
    - implemented baseline: explicit issuer discovery feeds can now populate SEC CIK/series/class ids plus FIGI/composite/share-class FIGI aliases when those columns are present
  - use market-data-provider metadata as a candidate signal when it includes issuer/fund-family/sponsor fields
  - use SEC Investment Company Series/Class data as a canonical US fallback for ticker-to-CIK/series/class mapping
    - implemented baseline: admin `POST /api/v1/etf-holdings/discover-sec-funds` ingests SEC `company_tickers_mf`-style ticker mappings, materializes lightweight ETF instruments, and upserts ETF profiles with SEC CIK/series/class ids for EDGAR backfill routing
    - the SEC discovery endpoint supports the default SEC public file plus an explicit `source_url` override for mirrors/fixtures, and accepts both keyed-object and `fields`/`data` payload shapes
  - use identifier resolvers such as OpenFIGI where available to reconcile CUSIP/ISIN/FIGI/ticker/exchange aliases
  - maintain an issuer adapter registry with confidence-scored matchers:
    - exact issuer id / fund-family match
    - SEC registrant/fund family match
    - issuer product id match
    - domain/URL match
      - implemented: configured ETF profile/product/holdings URLs now contribute confidence-scored domain matching for known issuer adapters without falling back to ticker-only guessing
    - name-pattern match as a last resort only
  - after selecting an adapter, run a lightweight probe before ingesting holdings:
    - implemented: route-readiness probe that reports adapter status, confidence, resolved source URL, and missing route identifiers
    - implemented: fetched-artifact validation for explicitly configured expected ETF/fund name, symbol, CUSIP, or ISIN
    - implemented: conservative generic identity extraction from two-column preamble metadata and explicit fund/ETF identity columns in downloaded CSV/XLSX tables
    - still needed: richer issuer-specific automatic identity extraction/probing for non-tabular pages/PDFs and unusual issuer formats
  - if an ETF cannot be routed confidently, mark it as `holdings_adapter_unresolved` rather than silently trying a guessed provider path
- Store adapter/source health and coverage:
  - last successful refresh by ETF and adapter
  - last failed refresh and failure reason
  - source URL / SEC accession / raw artifact id
  - parser version
  - row count
  - resolved constituent count
  - unresolved constituent count
  - apparent composition date
  - observed publication date / ingestion date
  - whether the file appears complete, partial, delayed, empty, or malformed
  - whether the issuer blocks or rate-limits automated access
- Add clear source/provenance semantics for free ETF holdings data:
  - `issuer_current_holdings`: latest free issuer-disclosed holdings file/page
  - `issuer_self_snapshotted_holdings`: point-in-time history accumulated by our scheduled issuer adapters from today onward
  - `sec_nport_reconstructed_holdings`: historical holdings reconstructed from SEC N-PORT / N-PORT-P
  - `sec_legacy_reconstructed_holdings`: older lower-frequency holdings reconstructed from N-Q / N-CSR where practical
  - `paid_api_historical_holdings`: optional commercial source, not required by the free baseline
  - `official_index_constituents`: authoritative licensed index membership, separate from ETF holdings
- Add legal/usage metadata to every source and adapter:
  - public availability does not automatically mean unrestricted redistribution
  - store issuer terms/disclaimer review notes where known
  - distinguish internal research use, user-facing derived analytics, raw holdings redistribution, and commercial resale
  - avoid presenting this feature as "we own/redistribute issuer data" unless licensing has been checked
  - design the platform so we can initially show derived/normalized holdings for product functionality while preserving a path to stricter licensing controls later
- Introduce a scheduled refresh task that updates ETF holdings on a configurable cadence (daily or weekly is likely sufficient for non-leveraged index funds).
- Model ETF holdings as a special case of basket: a system-managed basket with a reference to the source ETF instrument, a composition_date field, and a flag distinguishing user-owned baskets from ETF-derived baskets.
- Persist ETF holdings snapshots over time instead of overwriting only the latest composition:
  - ETF instrument id
  - constituent instrument id
  - reported constituent symbol/name at source
  - weight
  - shares held where available
  - market value where available
  - cash/derivative/other holding classification where available
  - composition date
  - source/provider
  - ingestion timestamp
  - source file/report identifier where available
  - confidence/provenance flags
- Support multiple holdings-history quality levels and make them visible downstream:
  - `current_issuer_holdings`: latest issuer-published holdings snapshot
  - `self_snapshotted_holdings`: snapshots the platform has collected going forward
  - `filing_reconstructed_holdings`: lower-frequency historical holdings reconstructed from regulatory filings
  - `api_historical_holdings`: provider-supplied historical holdings snapshots
  - `official_index_constituents`: authoritative licensed index membership, when available
- Add explicit caveats and metadata so Strategy Lab, Screener, Radar, baskets, and breadth analysis know whether a holdings-derived universe is:
  - exact enough for navigation and current analysis
  - a reasonable proxy for historical research
  - too sparse/stale for a specific requested backtest date range
  - unsuitable for claims about official index membership
- Model timing carefully:
  - issuer files may be current or previous-close holdings
  - regulatory filings are delayed and should not be treated as known before their filing/public availability date in point-in-time simulations
  - reconstructed historical ETF holdings should preserve both `as_of_date` and `known_at` / `published_at` where available
  - Strategy Lab must avoid look-ahead bias when using historical holdings snapshots as dynamic universes.
- Add provider adapters that can ingest both API responses and downloadable issuer files:
  - normalize source symbols into canonical instruments through the platform's instrument resolver
  - instantiate lightweight instruments for holdings not yet known locally
  - preserve source-specific labels/symbols for auditability
  - record unmatched constituents so users can see which holdings could not be resolved
- For ETF/index proxy workflows, support mapping common index ETFs to their intended benchmark/index:
  - `SPY` / `VOO` / `IVV` as S&P 500 proxies
  - `QQQ` as a Nasdaq 100 proxy
  - `IWV` / `VTHR` or similar as Russell 3000 proxies
  - `IWM` / `VTWO` as Russell 2000 proxies
  - keep this mapping explicit and user-visible, because an ETF proxy is not the same as the official index.

Backend:
- ETF-derived baskets should be read-only from the user's perspective (no user-editable weights).
- Provide an endpoint to list/search ETFs that have holdings data available.
- Provide an endpoint to retrieve the holdings basket for a given ETF instrument.
- Provide an endpoint for the holdings navigation flow: given an ETF instrument id, return a paginated/searchable/sortable member list with weights, instrument details, and optional mini-stats per member.
- Provide endpoints to inspect holdings history and coverage:
  - latest holdings snapshot for an ETF
  - available composition dates for an ETF
  - holdings snapshot nearest to a requested date
  - historical membership timeline for a constituent within an ETF
  - unresolved/unmatched holdings for a provider/source
  - coverage summary showing whether a requested Strategy Lab date range has usable holdings snapshots
- Allow ETF holdings baskets to be used as first-class universes in:
  - Screener (backend/API/engine implemented for basket universes; frontend builder selector implemented)
  - Radar slicing/filtering where appropriate (backend/API/engine implemented for basket universes; frontend scan selector implemented)
  - Strategy Lab snapshot universes (implemented for static ETF holdings snapshots and baskets)
  - Strategy Lab dynamic point-in-time ETF holdings universes for rules backtests (implemented as an opt-in backend baseline using `snapshot_mode = "dynamic"`)
  - Strategy Lab dynamic point-in-time ETF-derived basket universes for rules backtests (implemented by delegating system-managed ETF baskets to their source ETF holdings history)
  - Strategy Lab dynamic point-in-time manual basket universes for rules backtests (implemented through persisted basket composition snapshots)
  - later, richer constituent-exit/rebalance policies and historical basket snapshot editing/import UX

Frontend:
- On the chart page, when viewing an ETF, surface a "Holdings" tab or panel showing the basket composition.
  - implemented: compact Chart panel with source/freshness/resolution metadata, filter/sort, selected holding details, previous/next navigation, and explicit constituent open actions.
- Provide a dedicated holdings browse workspace for larger ETFs:
  - implemented: `/etf-holdings` lists ETFs with stored holdings and loads holdings rows through the server-side paginated/searchable/sortable API.
  - implemented: selected holding details show weight, market value, shares, venue, identifiers, and resolution context.
  - implemented: first-pass holdings churn/addition/removal/reweight summaries and top constituent weight-evolution movers across stored snapshots.
  - still needed: richer market mini-stats such as price, change, distance to 52-week high, volatility, liquidity, and deeper cross-sectional historical analytics.
- The holdings panel should make it easy to open multiple instruments in sequence (e.g., step through constituents one by one) for manual scanning.
  - implemented in the compact Chart panel through previous/next selection controls and explicit constituent chart open actions.
- Later, a "chart all" or "compare all" shortcut that opens a screener-results-like view filtered to the ETF's holdings.
- Show holdings-source and freshness metadata directly in the ETF holdings UI:
  - source/provider
  - composition date
  - ingestion time
  - number of resolved holdings
  - number of unresolved holdings
  - whether the holdings are issuer-current, self-snapshotted, filing-reconstructed, API-historical, or official index constituents
- In Strategy Lab universe selection, allow the user to choose ETF-derived universes with clear semantics:
  - latest ETF holdings snapshot
  - platform-snapshotted point-in-time ETF holdings where available
  - filing-reconstructed holdings where available
  - official index constituents only if a premium source is configured
  - warn when the selected mode is a proxy or when historical coverage is incomplete.
  - implemented backend baseline: `snapshot_mode = "dynamic"` can use historical ETF holdings snapshots during rules backtests.
  - implemented ETF-derived basket baseline: `basket_snapshot_mode = "dynamic"` can use the source ETF holdings profile behind a system-managed ETF basket during rules backtests.
  - implemented manual basket baseline: `basket_snapshot_mode = "dynamic"` can use stored basket composition snapshots for user-authored basket history during rules backtests.
  - still needed: richer UI around historical basket snapshot inspection/import/editing and more detailed dynamic-membership drilldowns in results.

---

#### 10d. Breadth analysis over baskets and ETFs

Context:
- Once baskets exist and their member OHLCV histories are queryable, the platform can compute aggregate technical properties across the membership and surface a collective health view.
- Breadth analysis answers questions like: "What percentage of S&P 500 members are above their 200-day EMA right now?" or "How many Nasdaq 100 stocks are within 5% of their 52-week high?" or "What's the average distance to the 50-day SMA across this basket?".
- This kind of analysis is a tool used by technical macro analysts to evaluate whether a broad market move is being driven by wide participation or narrow concentration.
- The feature should be general enough to work on any user-defined basket or ETF-derived basket, not just major US indices.

What remains:

Computation engine:
- Define a set of per-member breadth metrics to compute, including (but not limited to):
  - percentage of members above their 20/50/100/200-day SMA or EMA
  - percentage of members within N% of their 52-week high or low
  - average distance (in % or ATR multiples) from a given EMA/SMA across members
  - percentage of members with recent volume above their N-day average
  - percentage of members in uptrend vs downtrend by a chosen definition (e.g., above 200 EMA = uptrend)
  - percentage of members making new N-day highs or lows
  - percentage of members above a user-specified price level or within a zone
- Implement a backend breadth computation service that takes a basket id, a reference date, and a set of requested metrics and returns a breadth snapshot.
- Optionally persist historical breadth snapshots so the platform can show a breadth indicator time series (e.g., "% above 200 EMA over the last 12 months") rather than only the current snapshot.

Frontend:
- A basket breadth panel / dashboard widget that shows a summary of current breadth metrics for a selected basket or ETF.
- A breadth chart: a time series showing how a selected breadth metric has evolved over time (e.g., a McClellan-oscillator-style view of participation).
- A drill-down from the breadth summary: click "38% of members are above 200 EMA" to see the list of which members are above vs below, sortable/filterable.
- A comparison view: show breadth for multiple baskets side by side (e.g., compare S&P 500 breadth vs Nasdaq 100 breadth vs a user-defined sector basket).
- Later: dashboard widgets specifically for basket breadth, so users can pin a breadth indicator to their main dashboard.

---

#### 10e. Cross-instrument correlation and relationship analysis

Context:
- While strategy-to-strategy correlation belongs primarily in Strategy Lab, we also discussed a separate need for **instrument-level correlation analysis** as a more general market-analysis tool.
- This should not be treated only as a strategy-testing concern. Users may want to answer questions such as:
  - "How correlated are these two instruments over the last 3/6/12 months?"
  - "Which members of this basket are moving most independently from the rest?"
  - "Which instruments are highly correlated so I should avoid doubling the same exposure?"
  - "Which instruments could diversify this watchlist or basket?"
- This feature sits naturally adjacent to baskets, ETF holdings navigation, breadth, watchlists, and Strategy Lab because all of those surfaces benefit from understanding cross-instrument relationships.

What remains:

Backend / analytics:
- Define a reusable correlation-analysis service that can compute, at minimum:
  - return correlation matrices across a selected set of instruments
  - rolling correlations between pairs or groups
  - covariance matrices
  - optionally beta-style relative sensitivity for common benchmark pairs
- Support multiple selectable lookback windows and return granularities so users can compare short-term vs medium-term vs long-term relationships.
- Support applying the service to:
  - arbitrary manually selected instruments
  - watchlists
  - baskets
  - ETF holdings baskets
  - Strategy Lab result universes where useful
- Later, if valuable, extend into adjacent relationship measures such as relative strength, cointegration/pair-candidate analysis, or cluster/group detection.

Frontend / product surfaces:
- A standalone correlation analysis view or panel where users can:
  - pick a set of instruments/watchlists/baskets
  - choose the lookback window and return granularity
  - inspect matrix and pairwise outputs
- Correlation heatmaps and sortable pair tables.
- Rolling pair-correlation charts for selected instrument pairs.
- Cross-basket or watchlist comparison views that highlight concentration vs diversification.
- Later, dashboard widgets for compact correlation snapshots or "top correlated / least correlated" lists.

Why this matters:
- This is useful even outside Strategy Lab because it helps users reason about hidden exposure concentration across watchlists, baskets, and manually selected instruments.
- It also creates a natural bridge into multi-strategy and portfolio-construction research by giving the platform a common language for diversification at both the instrument and strategy levels.

---

#### 10f. Relative Rotation Graph (RRG-style) relative-strength rotation analysis

Context:
- We discussed adding a **Relative Rotation Graph-style** view so users can track relative leadership and rotation across a peer set, with the first practical use case being **S&P sector ETFs** against a common benchmark such as the S&P 500.
- The same capability should then generalize to **any arbitrary basket of instruments**:
  - sector ETFs
  - country ETFs
  - factor ETFs
  - watchlists
  - ETF holdings subsets
  - user baskets
  - later even Strategy Lab result series or platform-owned signal baskets where useful
- Based on the source material we reviewed, the core idea is:
  - compute a **relative-strength series** of each instrument versus a selected benchmark
  - derive a normalized **trend-of-relative-strength** axis (`RS-Ratio`)
  - derive a normalized **momentum-of-relative-strength** axis (`RS-Momentum`)
  - plot each instrument on a two-dimensional plane whose axes cross at a neutral center and whose four quadrants describe the instrument's current relative phase
  - retain a **tail/history** so users can see the recent rotation path, not just the latest point
- The classic quadrant semantics are:
  - `Leading`: strong relative trend and strong relative momentum
  - `Weakening`: strong relative trend but fading relative momentum
  - `Lagging`: weak relative trend and weak relative momentum
  - `Improving`: weak relative trend but improving relative momentum
- The user's intended workflow is tactical sector allocation:
  - compare sector ETFs to a benchmark
  - see which sectors are emerging, rolling over, improving, or deteriorating
  - adjust portfolio positioning based on relative leadership and its evolution through time
- This should be treated as a **market-analysis / cross-instrument analytics** feature first, not only a Strategy Lab concern.

Important implementation note:
- The exact proprietary JdK normalization used in branded/commercial RRG implementations should not be assumed to be freely reproducible unless we intentionally license or explicitly clone it from an allowed/public method.
- Our implementation should therefore be framed as:
  - either a licensed/faithful RRG implementation if we later choose that path
  - or a clearly labeled **RRG-style relative rotation view** built from transparent relative-strength and momentum transforms
- Product naming, disclosure, and UX copy should respect the trademarked nature of `Relative Rotation Graphs` / `RRG` where relevant.

What remains:

Analytics / computation engine:
- Build a reusable **relative-rotation analytics service** that accepts:
  - a benchmark instrument
  - a peer universe of instruments
  - timeframe / bar granularity
  - lookback window
  - tail length
  - sampling frequency for the plotted tail points
- Compute a canonical **relative-strength series** for every instrument versus the benchmark:
  - typically ratio- or return-based relative performance
  - with explicit handling of missing bars, partial overlap, and benchmark/instrument calendar mismatches
  - with consistent point-in-time alignment rules so cross-instrument comparisons are not distorted by stale or shifted bars
- Derive two normalized dimensions per instrument:
  - a **relative-trend dimension** equivalent in spirit to `RS-Ratio`
  - a **relative-momentum dimension** equivalent in spirit to `RS-Momentum`
- Be explicit about the platform math:
  - if we cannot or should not reproduce the exact commercial JdK formula, document the transparent internal alternative
  - keep the transforms deterministic and auditable
  - expose enough metadata that advanced users can understand what the chart is based on
- Persist or cache computed rotation snapshots where useful so the platform can support:
  - historical replay
  - animation
  - dashboard widgets
  - cross-date comparison
  - export without recomputing large universes every time

Quadrant / state model:
- Classify each instrument into a current relative state:
  - leading
  - weakening
  - lagging
  - improving
- Also compute richer state descriptors beyond the raw quadrant:
  - distance from center
  - heading / angle of travel
  - rate of change of heading
  - recent quadrant transitions
  - time spent in current quadrant
  - acceleration / deceleration of rotation
- This richer state is important because users do not only care where an instrument is now, but:
  - whether it is moving deeper into leadership
  - whether it is curling over
  - whether it is improving with conviction
  - whether it is merely bouncing around near the origin without real signal

Primary product surface:
- Add a dedicated **Relative Rotation** workspace or analysis panel where users can:
  - choose a benchmark
  - choose a peer set
  - switch timeframes
  - adjust lookback and tail length
  - animate or scrub through history
  - inspect both the latest state and recent path
- The first-class preset should be **S&P sector ETFs**:
  - benchmark default: `SPY`, `IVV`, or the S&P 500 index if available
  - peer set default: the major US sector ETFs
  - one-click load should exist because this is the main intended use case
- But the selector model must remain generic so the same workspace can be reused for:
  - arbitrary instruments
  - watchlists
  - baskets
  - ETF-derived baskets
  - later, strategy or signal peer sets where that makes product sense

Visualization / UX:
- Plot instruments on a scatter-plot style canvas with:
  - horizontal axis for relative-trend
  - vertical axis for relative-momentum
  - clear neutral/origin crosshair
  - color-coded quadrants
  - labeled latest points
  - tails showing recent motion
- Support interaction suitable for dense universes:
  - hover tooltip with symbol, name, latest relative metrics, quadrant, heading, and recent change
  - click to pin one or more instruments
  - isolate/highlight selected symbols
  - hide or fade non-selected symbols
  - search within the plotted set
- Support both:
  - a **latest snapshot** view
  - a **time-evolution** view where the tail / animation is the star
- Handle clutter carefully:
  - adaptive label density
  - optional point-only mode
  - optional tail-only-on-selection mode
  - shorter tails automatically suggested when the plotted universe is large
- Make the visual feel native to the platform:
  - consistent typography, sizing, control layout, color tokens, hover behavior, and popups
  - no oversized or visually disconnected custom control block

Companion views:
- Add a sortable **rotation table** next to or below the graph showing:
  - symbol
  - current quadrant
  - relative-trend metric
  - relative-momentum metric
  - heading / angle
  - distance from center
  - recent quadrant transition
  - rank within selected peer set
- Add a **history strip / event log** for selected instruments:
  - when they moved between quadrants
  - when they crossed the neutral thresholds
  - how long they remained in leadership vs lagging states
- Add a **pair/trio comparison mode** where a few selected instruments can be seen with more detail and less clutter.

Data and coverage considerations:
- This depends on robust aligned OHLCV coverage for:
  - the benchmark
  - every instrument in the peer set
- The view should surface coverage limitations clearly:
  - partial overlap
  - benchmark starts later than the selected range
  - peer instruments with too little history to compute stable signals
- If coverage is insufficient, the platform should:
  - either exclude the instrument with a clear reason
  - or visually mark it as coverage-limited
  - but never silently compute a misleading path

Downstream integrations:
- Watchlists / baskets / ETF holdings:
  - allow any of these to be launched directly into the rotation workspace
- Correlation / breadth / relative-performance tooling:
  - share universe selectors and time-range controls with those analytics surfaces where possible
- Radar:
  - later, allow radar candidate sets to be inspected through a relative-rotation lens
  - this can help answer whether a technical setup is also occurring in a strengthening or weakening relative context
- Strategy Lab:
  - later, consider whether relative-rotation state should become:
    - an input condition family
    - a universe-ranking aid
    - or a comparative analysis surface for strategy output baskets
  - but do not force the initial implementation to depend on Strategy Lab

Validation and testing:
- Add unit coverage for:
  - relative-strength series construction
  - normalization/transformation math
  - quadrant classification
  - heading / angle / distance calculations
  - missing-data alignment rules
- Add integration coverage for:
  - benchmark-relative calculations across realistic ETF peer sets
  - coverage-warning semantics
  - server/API response shape if the computation is backend-driven
- Add frontend coverage for:
  - graph rendering
  - selection/highlight behavior
  - dense-universe decluttering behavior
  - tooltip correctness
  - table/graph cross-linking

Why this matters:
- This becomes a high-signal visual way to inspect **relative leadership rotation**, which is especially useful for:
  - sector rotation
  - macro/factor allocation
  - ETF peer comparisons
  - basket triage
- It also complements, rather than duplicates:
  - breadth analysis
  - correlation analysis
  - strategy research
- Breadth tells us how broad participation is.
- Correlation tells us how related instruments are.
- Relative rotation tells us **who is leading, who is improving, and how that leadership is evolving over time versus a benchmark**.

---

#### Shared design principles across 10a–10f

- **Baskets are first-class objects.** They are not just lists; they carry weights, metadata, classification, and a potential synthetic price series. The domain model should reflect this from the start.
- **ETF-derived baskets are a special case of the same model.** User baskets and ETF holdings baskets share the same backend schema and frontend surfaces; the distinction is managed vs unmanaged ownership and refresh semantics.
- **The basket model feeds other platform features.** Baskets should be usable as: chart synthetic instruments, screener universes (item 3), Strategy Lab universes (item 7), radar filter slices (item 5), and breadth analysis targets. These integrations should inform the basket schema design so it isn't retrofitted later.
- **Breadth analysis should be additive, not a re-architecture.** The breadth engine reads member OHLCV histories that already exist in the platform. It does not require new data infrastructure, only a computation layer on top of existing data.
- **Sector/industry classification for mixed baskets remains an open design question.** The taxonomy used for classification should be revisited once downstream use cases (breadth grouping, radar slicing) clarify what granularity is actually needed.
- **Cross-instrument correlation analysis should reuse the same universe-selection building blocks.** Watchlists, baskets, ETF holdings, and later Strategy Lab result sets should be usable as correlation-analysis inputs without needing a separate parallel selector model.
- **Relative-rotation analysis should reuse the same universe-selection and coverage primitives.** Benchmarks, watchlists, baskets, ETF-derived baskets, and later strategy/signal peer sets should all plug into the same selectors and OHLCV readiness rules rather than introducing another bespoke instrument-set model.

Phasing expectations:
- Phase 1: Custom basket creation/editing with equal and custom weights, basket charted as a synthetic price series, basic basket list/detail UI.
- Phase 2: ETF holdings data ingestion, ETF-as-basket materialisation, holdings navigation UI.
- Phase 3: Breadth analysis engine, breadth snapshot views, breadth time-series charting.
- Phase 4: Basket breadth dashboard widgets, cross-basket comparison views, integration with radar and screener universe selectors.
- Phase 5: Cross-instrument correlation analysis surfaces, rolling correlation views, and integration of those relationship tools into watchlists/baskets/Strategy Lab workflows.
- Phase 6: Relative-rotation analysis over arbitrary instrument sets, with S&P sector ETF presets, benchmark-relative tails, and richer downstream integration into watchlists/baskets/Radar/Strategy Lab where useful.

Why this was deferred:
- Baskets are a foundational building block but depend on having a stable instrument model (already done) and clear downstream consumers.
- ETF holdings data requires a dedicated provider integration.
- Breadth analysis depends on both basket membership and historical OHLCV coverage being in good shape.
- The right design for mixed-sector basket classification needs more downstream context before being finalised.

### 12. Build a platform-wide OHLCV coverage, freshness, and acquisition orchestration layer
Status: `Planned`

Context:
- The platform now has several different price-data consumers, but they do not all behave consistently:
  - chart OHLCV routes are read-through and may fetch/backfill on demand
  - first-time instrument discovery can enqueue broad history fetches in the background
  - indicator alerts currently fetch OHLCV on demand before evaluating
  - `run_screener` is DB-only
  - `stream_screener` is hybrid: DB-first, then fetches for instruments with no cached bars
  - radar is currently DB-only
  - nightly refresh and bulk-fetch flows explicitly seed or refresh OHLCV ahead of time
- This inconsistency is manageable while the platform is small, but it becomes increasingly dangerous as more evaluators come online.
- We explicitly want to preserve three platform rules:
  - external providers should only be contacted when there is strong evidence that the DB is missing required data or has gone stale enough to invalidate the use case
  - when data is missing, the platform should fetch only the missing slice, not an arbitrarily broad range
  - any mechanism that issues factual, price-based outcomes (alerts, screener matches, radar detections, future breadth or signal outputs) must not silently evaluate on stale or incomplete data
- This future item is about making those rules concrete and enforceable across the whole platform, not just inside one feature.

Why this deserves a dedicated roadmap item:
- This is not only a radar concern. It directly affects:
  - chart OHLCV loading
  - instrument detail widgets derived from OHLCV
  - screeners
  - indicator alerts
  - radar scans
  - breadth analysis over baskets and ETFs
  - future signal/trade-plan engines
  - future strategy or validation workflows that depend on OHLCV readiness
- If each subsystem keeps inventing its own "fetch if missing", "fresh enough", or "latest bars" logic, the platform will drift into multiple incompatible truth models:
  - one feature may skip an instrument because the DB is cold
  - another may fetch a fresh tail and produce a different answer
  - another may operate on stale bars and produce an answer that is factually out of date
- A shared orchestration layer is the cleanest way to preserve:
  - deterministic evaluation behavior
  - low provider dependency
  - bounded provider spending/quota usage
  - eventual consistency with market reality

Desired global policy:
- Split OHLCV consumers into three explicit classes and apply different rules to each.
- Also be explicit that this item governs **price/coverage acquisition**, not all provider communication in general.
- A separate but adjacent platform rule needs to be preserved:
  - some flows are fundamentally about **instrument discovery / identity / metadata**
  - other flows are about **OHLCV / freshness / historical coverage**
  - those must not be conflated, because the correct provider-access policy is different for each

#### 11a0. Separate instrument discovery/materialization from OHLCV acquisition

The platform should explicitly model two adjacent but different responsibilities:

- **Instrument discovery / identity / metadata**
  - "What is this thing?"
  - search results
  - canonical symbol resolution
  - provider symbol mappings
  - provider profile / metadata ingestion
  - provider-overlap reconciliation and mastering
- **Market-data acquisition / freshness / coverage**
  - "Do we have the price/history needed for this use case?"
  - OHLCV completeness
  - latest-bar freshness
  - missing-slice repair
  - background refresh/seed orchestration

This roadmap item is primarily about the second responsibility, but the first one must be documented alongside it so provider-access boundaries stay coherent.

Current gap we discussed:
- provider-backed search results can be shown in the UI without necessarily materializing a canonical `Instrument` row in the DB
- that creates downstream incoherence, because a symbol can be:
  - real according to provider search
  - visible/selectable in the UI
  - but still absent from the platform DB until some later route explicitly instantiates it
- this affects flows like Strategy Lab universes and any other picker-driven feature that assumes selected provider-backed instruments are already locally materialized

Desired future behavior:
- when the user selects a provider-backed instrument from a search/picker flow, the platform should be able to:
  - fetch lightweight metadata/profile details
  - instantiate or reconcile a canonical local `Instrument` row
  - register provider-symbol identity mappings
  - merge overlaps appropriately if the instrument already exists under another provider identity
- this should happen **without** automatically fetching OHLCV unless a separate policy explicitly asks for it

In other words:
- metadata discovery/materialization should be allowed to talk to providers
- broad OHLCV consumers should still be forbidden from doing ad hoc provider fetches inside evaluation loops

This gives the platform the desirable model we discussed:
- search/discovery makes an instrument locally known
- OHLCV/history is still fetched later on demand or by scheduled preparation flows
- features like Strategy Lab, Screener, Radar, and Alerts can then assume:
  - selected instruments are real platform objects
  - but price data may still be cold and must go through the shared OHLCV coordinator

Provider-access boundary to preserve:
- **Allowed to call providers for identity/metadata/materialization**
  - `/instruments/search` follow-up selection flows
  - explicit instrument-add or instrument-picker commit flows
  - `/instruments/{symbol}` resolution/lookup
  - expression constituent resolution
  - instrument mastering / background sync jobs
- **Not allowed to call providers directly for OHLCV as part of evaluation**
  - Radar
  - Screener
  - Strategy Lab
  - Alerts
  - breadth evaluators
  - any broad decision engine
- those OHLCV consumers must instead go through the shared coverage/freshness coordinator defined below

Search-time lightweight instrument materialization should therefore eventually become a first-class platform behavior:
- provider search may remain a lightweight discovery step by itself
- but once the user actually selects a result for use in the platform, the system should:
  - materialize/reconcile that instrument into the DB
  - persist canonical identity and provider-symbol mappings
  - optionally enqueue a background OHLCV bootstrap
- the OHLCV bootstrap, if any, should be asynchronous and policy-driven:
  - it should not block search UX unnecessarily
  - it should not blur the line between metadata instantiation and price acquisition

This should align cleanly with the rest of this roadmap item:
- interactive/search flows are allowed to create or reconcile instrument metadata
- OHLCV consumers remain DB-first and coordinator-driven
- first discovery may enqueue background history seeding
- evaluators later rely on preflight readiness rather than silently fetching bars themselves

#### 11a. Interactive, user-driven data views

Examples:
- chart OHLCV requests
- transformed-bar chart requests
- historical pagination while the user pans left on a chart
- instrument detail views that need one symbol's recent OHLCV-derived metrics
- later, narrow single-symbol analytical views

Policy:
- allow narrow read-through fetch/backfill
- allow on-demand repair of the exact requested historical slice
- allow limited freshness repair of the exact latest window needed for the request
- still route these through a shared coordinator so provider throttling and missing-slice logic remain centralized

Reason:
- the user explicitly requested a narrow unit of data
- read-through behavior is acceptable here because it is scoped, intentional, and observable

#### 11b. Broad evaluators / decision engines

Examples:
- radar scans
- scheduled screeners
- screener-alert post-processing
- indicator alerts
- future breadth snapshots
- future trade-signal engines
- future strategy/lifecycle engines that consume price-derived signals

Policy:
- do not let these flows perform ad hoc provider fetches inside the actual evaluation loop
- evaluate from DB-backed data only
- if data freshness/completeness is required, acquire it in a dedicated preflight phase before evaluation begins
- if preflight cannot produce adequate coverage, the evaluator should mark the run as partial/deferred/unavailable rather than silently evaluating stale data

Reason:
- these flows can touch many instruments and many timeframes
- letting each engine fetch on the fly is the fastest path to:
  - quota waste
  - inconsistent results
  - bad runtime performance
  - subtle race conditions between evaluation and refresh

#### 11c. Background maintenance / data-orchestration flows

Examples:
- nightly OHLCV refresh
- bulk instrument history fetch
- discovery-triggered initial history seeding
- future pre-market or post-close refresh waves
- future scheduled "prepare data for radar/screener/alerts" tasks

Policy:
- these are the preferred place for broad provider usage
- they may fetch at larger scale, but should still fetch precisely where possible
- they should aim to keep the DB sufficiently ready that evaluators rarely need to wait

Reason:
- this centralizes provider communication
- this makes rate limiting and retry behavior operationally visible
- this avoids broad evaluators becoming selfish and independently burning provider quota

Desired platform rules:
- Rule 1: never perform factual evaluation on known-stale or known-missing price data.
- Rule 2: never fetch broad history when a narrow missing slice will do.
- Rule 3: never allow multiple callers to independently hit providers for the same instrument/timeframe/range if the request can be coalesced.
- Rule 4: never allow a broad evaluator to spend provider quota without going through a shared coordinator.
- Rule 5: historical ranges already fully covered in the DB should not be treated as stale merely because they are old relative to the current wall clock.
- Rule 6: freshness semantics must be use-case aware, not just "is the latest bar older than now?".

What should be built:

#### 11d. Shared OHLCV coverage/freshness coordinator

Introduce one central service, rather than many feature-specific implementations, with an interface conceptually similar to:
- `ensure_ohlcv_coverage(instrument_id, timeframe, start, end, freshness_policy, mode)`

The exact final API can differ, but the coordinator should be responsible for:
- inspecting the current DB coverage for the exact instrument/timeframe/range requested
- determining whether the request is:
  - ready
  - partially covered
  - missing
  - stale
  - already being refreshed
  - unavailable due to provider/runtime constraints
- computing the exact missing slice rather than defaulting to broad "latest N" fetches unless that is truly the narrowest correct request
- coalescing overlapping requests from multiple callers
- reusing in-flight refresh work when one caller already requested the same coverage
- routing provider work through the existing provider runtime / throttling / health machinery
- returning explicit status so callers know whether they may proceed synchronously, should queue work, or must defer

The coordinator should understand the difference between:
- latest-window freshness
- historical-range completeness
- cold-start absence of any OHLCV
- partial historical gaps in the middle of a range
- synthetic instruments whose OHLCV is computed internally rather than fetched from providers

#### 11e. Formal freshness semantics by use case

Define "fresh enough" in a way that is aware of:
- timeframe
- market/session timing
- the consuming engine
- whether the use case needs the latest completed bar, a historical range, or a live latest-price signal

Examples:
- `D1` radar/screener:
  - should require the latest completed daily bar for the relevant session
  - should not demand a synthetic "today" bar before the daily bar has actually completed
- `W1` computations:
  - should care about the latest completed weekly bar, not naïvely treat mid-week partial state as missing unless the feature explicitly supports it
- historical chart pagination:
  - should care about completeness of the requested window, not freshness to the current timestamp
- price alerts:
  - may legitimately require a live latest-price capability rather than OHLCV-bar freshness alone
- indicator alerts:
  - should run against refreshed OHLCV snapshots at the required timeframe, ideally grouped by instrument/timeframe rather than fetching per-alert

This freshness logic should eventually become exchange-aware and asset-aware where relevant:
- weekends and holidays
- pre-market / regular session / post-market behavior
- `24/7` assets like crypto
- provider-specific publication timing for daily/weekly bars

#### 11f. Evaluation preflight for broad engines

Broad evaluators should move to a two-phase model.

Phase 1: coverage preflight
- determine the exact required OHLCV window per instrument and timeframe
- check freshness and completeness
- queue refresh/fill only for the instruments that need work
- optionally wait for a bounded refresh wave to complete
- mark unresolved instruments as unavailable/blocked rather than guessing

Phase 2: evaluation
- run the evaluator strictly against DB-backed data
- never mix provider fetches into the evaluation loop itself
- persist whether the run was:
  - full
  - partial
  - deferred
  - stale-blocked
  - provider-unavailable

This pattern should eventually apply to:
- radar scans
- `run_screener`
- `stream_screener`
- grouped indicator-alert evaluation
- future breadth snapshots
- future signal/strategy engines

#### 11g. Request coalescing and anti-selfishness controls

The future orchestration layer should explicitly prevent anti-patterns like:
- radar, screener, alerts, and chart loads all noticing the same stale `AAPL D1` coverage and each independently calling the provider

Add shared controls for:
- in-flight deduplication per `(instrument, timeframe, adjusted, range/freshness intent)`
- bounded concurrency by provider and capability
- global and per-provider refresh budgets
- caller-visible statuses such as:
  - `already_refreshing`
  - `queued`
  - `ready`
  - `deferred_due_to_budget`
  - `provider_unavailable`
  - `no_provider_support`

This should integrate with the provider runtime / policy / health system rather than bypassing it.

#### 11h. Precise missing-slice fetch logic

The implementation should aggressively avoid over-fetching.

Expected behaviors:
- if the DB has bars through `2026-05-05` and only `2026-05-06` is missing, fetch only that missing tail
- if the user paginates older chart history and the DB lacks only the older tail needed for that page, fetch only that tail
- if the DB already fully covers a historical range, do not fetch anything just because the range ends in the past
- if an instrument is new and entirely cold, fetch only the minimum viable bootstrap window needed for the current synchronous use case unless a broader background seed job is intentionally requested
- if a background bulk-fetch wave is already responsible for fuller history, synchronous flows should avoid redundantly asking for the entire history themselves

The coordinator should explicitly understand:
- latest-window repair
- historical-gap repair
- cold-start bootstrap
- overlap buffers for late-arriving bars or provider revisions

#### 11i. Better dataset-state tracking

The platform already has some dataset-state/provider-observation ideas, but this future work should deepen them for OHLCV specifically.

Track enough metadata to answer:
- what coverage window currently exists for this instrument/timeframe?
- when was it last observed from a provider?
- when should it be considered stale for each major consumption mode?
- did the most recent refresh succeed, partially succeed, return empty, or fail?
- is a refresh already in progress?
- what provider last supplied or refreshed the data?
- is the dataset totally absent or only partially missing?

This should make it possible to:
- avoid recalculating freshness naively on every caller
- explain why a symbol was skipped by radar or a screener
- later expose operational insight in admin or diagnostics surfaces

#### 11j. Unify currently inconsistent consumers

The current mixed behavior should be normalized over time.

Specific migration targets:
- radar:
  - keep the detector DB-only at evaluation time
  - add a preflight coverage stage
- `run_screener`:
  - move from "DB-only, no preflight" to "DB-only after preflight"
- `stream_screener`:
  - stop being a special fetch-on-the-fly exception
  - instead stream:
    - coverage-preflight progress
    - then evaluation progress
- indicator alerts:
  - stop refreshing OHLCV separately inside each alert path
  - group by `(instrument, timeframe)` and refresh once, then evaluate all alerts from the same DB snapshot
- chart/instrument OHLCV routes:
  - keep read-through semantics
  - but route through the same coordinator so missing-slice and freshness policy stay consistent across the app

#### 11k. Operational orchestration and scheduling

The shared design should also inform platform scheduling.

Questions to settle and later implement:
- which refresh waves should run automatically:
  - nightly / post-close `D1` refresh
  - weekly `W1` refresh
  - selected intraday refreshes for alert-heavy assets
  - discovery-triggered bootstrap refreshes
- what readiness guarantees should exist before:
  - scheduled screeners
  - future scheduled radar scans
  - alert checks
  - future breadth snapshots
- what intentional order should exist between:
  - OHLCV refresh
  - evaluator runs
  - downstream watchlist/notification/state-propagation workflows

The long-term goal is that broad evaluators rarely discover missing data themselves because scheduled refresh waves have already kept the DB sufficiently ready.

#### 11l. Failure handling and run semantics

The future system should not force every evaluation to be all-or-nothing.

Support nuanced outcomes such as:
- run completed with full coverage
- run completed with partial coverage
- run deferred because refresh work would exceed current budget or timeout
- run skipped because provider chain health made refresh unsafe/unreliable
- instrument skipped because no provider-backed OHLCV source exists for it

These statuses should become visible where appropriate in persisted run metadata for:
- radar runs
- screener runs
- later breadth/signal/strategy runs

This matters because:
- "no matches"
- "could not evaluate accurately"
- and "some instruments were unevaluable"
are materially different outcomes.

#### 11m. Testing and verification expectations

This roadmap item deserves explicit tests of its own.

Expected test coverage:
- exact missing-slice calculation
- historical-range completeness vs latest-window freshness
- no-fetch behavior when a historical range is already fully covered
- deduplication of concurrent refresh requests
- grouped refresh behavior for indicator alerts
- preflight + evaluation separation for radar and screeners
- correct partial/deferred run statuses
- protection against stale-data evaluations
- provider-budget and throttle behavior under multiple simultaneous callers

Integration scenarios should explicitly cover:
- a cold instrument with no bars
- an instrument missing only the most recent bar
- an instrument with historical gaps
- provider unavailability during preflight
- chart read-through paths and evaluator preflight paths both using the same coordinator

Open design questions to preserve for later:
- Should broad evaluators block synchronously for missing data up to a short deadline, or always queue and retry later?
- Which assets/timeframes deserve proactive readiness guarantees versus on-demand preflight?
- How much exchange/session awareness should live in the coordinator versus provider adapters or market-calendar utilities?
- Should the platform have a formal freshness-SLA registry per capability / asset class / timeframe?
- How should synthetic instruments inherit or aggregate constituent freshness?
- Should options-related spot-price consumers use the same OHLCV freshness gate or a lighter latest-price-specific policy?

Suggested implementation sequence:
- Phase 1:
  - document the platform policy explicitly
  - introduce a shared coverage/freshness coordinator API
  - keep existing market-data fetch helpers, but route decision logic through the new abstraction
- Phase 2:
  - migrate chart/instrument read-through OHLCV flows to the coordinator
  - migrate radar preflight
  - migrate `run_screener` and `stream_screener`
- Phase 3:
  - migrate grouped indicator-alert evaluation
  - add persisted run statuses and richer skip/defer semantics
  - deepen dataset-state visibility
- Phase 4:
  - align scheduling so refresh waves intentionally precede evaluation waves
  - extend the same model to breadth, signal, and strategy engines

Why this was deferred:
- The current platform already works well enough for chart read-through, basic background refresh, and feature-specific point solutions.
- Solving this correctly is architectural work, not a small feature patch.
- Its value rises as more broad evaluators come online, especially radar expansion, breadth analysis, and future signal/strategy engines.

### 13. Let multi-instrument dashboard widgets publish clicked instruments into dashboard link groups
Status: `Deferred`

Context:
- We discussed a future dashboard interaction model where clicking an instrument inside a multi-instrument widget would not have to navigate away from the dashboard.
- The main idea was that widgets such as:
  - radar
  - watchlists
  - screener results
  - heat maps
  - and similar multi-instrument widgets
  could eventually publish the clicked instrument into a chosen dashboard link group.
- Linked quote/chart/details/options widgets could then update live from that click, preserving dashboard flow instead of forcing a route change.
- We explicitly chose not to build this immediately, but we do not want to lose the concept.

What this should eventually solve:
- Allow multi-instrument widgets to act as dashboard instrument publishers, not only as isolated result lists.
- Preserve a clear distinction between:
  - widgets that consume a linked instrument
  - widgets that can publish one when a user clicks a row/tile/item
- Let users inspect a result locally first, then optionally broadcast that instrument context to the rest of the dashboard.

Open questions to settle later:
- How should a multi-instrument widget declare which link group it publishes into?
  - fixed per widget
  - chosen in widget config
  - chosen ad hoc during interaction
- Should a widget be allowed to consume one link group while publishing into another?
- What is the UX split between:
  - local row/detail inspection
  - broadcasting to a link group
  - opening the full `/chart` route
- How do we make this predictable enough that users understand whether they are:
  - selecting something locally
  - updating a dashboard-wide context
  - or navigating away?

Suggested direction:
- Treat this as a dashboard interaction-system feature, not as radar-only behavior.
- Keep current widget-local detail interactions simple until the broader publisher/consumer dashboard-link model is designed properly.

Why this was deferred:
- It is cross-cutting dashboard architecture, not a small widget tweak.
- We do not want to bolt it onto one widget first and then retrofit the dashboard model later.

### 14. Replace the primary frontend with a TC2000 Version 25-style workstation and build its supporting backend/research platform
Status: `In progress — single completion bar not yet satisfied`

#### Current continuation — 2026-08-12 listing visibility and browser contract repair

The exchange-aware listing API contract is now exercised through the real seeded workstation
report. The controlled identity fixture adds a labelled active-primary `SPY`/`ARCX` row; the
instrument-detail and reload query paths eagerly load nested exchanges, preventing async response
validation failures. The first browser attempt exposed the concrete `GET /instruments/SPY` HTTP
500, and the first assertion revision exposed that existing canonical evidence can coexist with
the seeded row; both were repaired under the mandatory fix-first tie-break.

Evidence: focused seed/health `3/3` (without the global coverage threshold), instrument API
integration `17/17`, changed-file Ruff/compile, frontend Vitest `698/698`, type-check/build,
seeded authenticated report `1/1`, full authenticated Chromium `95/95` executed with `106`
suite-gated skips, authoritative backend `1373/1373` at `79.65%`, and strict board-guided visual
`104/104` across the four required display environments. Acceptance flexibility used: **None**;
no visual baseline, mask, threshold, or product criterion changed. Historical listing truth,
provider/ETF breadth, exact/unrepresented visual states, native monitor, beyond-bounded endurance,
and final audit gaps remain open.

#### Current continuation — 2026-08-10 uPlot-only shared and heat-map sparklines

The renderer audit found that the shared watchlist/dashboard `Sparkline.vue` and dashboard
heat-map tile sparklines still emitted numerical SVG polylines. Both now use a reusable uPlot
host; materialized tile series are passed directly without per-tile API requests, while fetched
watchlist series retain their cache/timeframe behavior, loading/empty/color semantics, and
unmount teardown. Focused tests pass `5/5`, the full frontend suite passes `678/678`, the targeted
authenticated dashboard browser regression (`F15`) passes `1/1`, type-check and the 468-module
production build pass, the numerical-SVG audit finds only icon geometry, and `git diff --check`
passes. Acceptance flexibility used: **None**. Exact-build/unrepresented visual, provider/
entitlement/taxonomy, physical-monitor, beyond-bounded-endurance, and final-audit gaps remain
explicitly open.

The complete authenticated Chromium matrix was then rerun against the healthy branch stack and
passed `85/85` in `11.3m` with one worker; the post-run service-log audit is clean for the audited
runtime-error signatures. Docker usage had exceeded the goal's 10GB hygiene threshold, so the
authorized non-volume prune reclaimed `6.5GB`; branch services remained healthy, named volumes
were preserved, and post-cleanup usage is approximately `6.7GB` including volumes. No acceptance
flexibility was used.

#### Current continuation — 2026-08-10 uPlot-only Strategy Lab outcome maps

The remaining axes-based SVG numerical renderers in `DistributionBars.vue` and
`SymbolPerformanceBars.vue` now use uPlot numeric axes and canvas plugins, with accessible HTML
point overlays preserving keyboard focus and detailed hover tooltips. Focused tests pass `2/2` and
assert uPlot/plugin construction; the full frontend suite passes `676/676` with no unhandled
errors after a defensive fix for incomplete jsdom uPlot positional doubles; type-check, the
production build, and the elevated authenticated legacy-route browser check pass. Acceptance
flexibility used: **None**. This closes another repository-controlled renderer contract gap; the
documented visual-reference, provider, physical-monitor, endurance, and final-audit gaps remain.

#### Current continuation — 2026-08-10 uPlot-only Strategy result renderer

The remaining axes-based numerical chart in `StrategyResultChart.vue` has been moved from
hand-built SVG geometry to the shared uPlot rendering contract. Real elapsed timestamps remain
the x data, range controls now adjust the uPlot x scale without rebuilding data, hover details
continue to include per-series formatting/details and nearest-series ordering, and resize/unmount
paths release or resize the existing chart instance. Focused tests pass `6/6`; the full frontend
suite passes `676/676`; the Strategy Lab view suite passes `28/28`; type-check and the 468-module
production build pass. An elevated authenticated legacy-route browser check passes `1/1` after the
un-elevated attempt failed before page startup due to macOS Chromium permissions. Acceptance
flexibility used: **None**. This closes a repository-controlled renderer gap but does not close the
documented visual-reference, provider, physical-monitor, endurance, or final-audit gaps.

#### Current continuation — 2026-08-10 unified-Python lookback preflight

The unified Python validation boundary now reports static lookback requirements for both
hand-authored positional indicator calls and the canonical generated forms used by visual
conditions: `ta.indicator(..., {"period": 14}, ...)` and `market.percent_change(63)`. Dynamic
parameter expressions intentionally produce no misleading static hint. This metadata strengthens
dataset preflight/reproducibility without creating a second condition language or changing
execution. Focused validator/compiler coverage passes `36/36`, authenticated `/code/validate`
coverage passes `19/19`, and the authoritative combined backend gate passes `1341/1341` at
`79.60%` (75% required; 86 known third-party deprecation warnings). Acceptance flexibility used:
**None**. Exact-build/unrepresented visual, provider/entitlement/taxonomy, physical-monitor,
long-duration endurance, and final-audit gaps remain open.

The same immutable lookback now controls canonical dataset materialization across Study Lab,
EasyScan, Strategy Lab, and reruns. Batch datasets receive at least `lookback + 1` bars; single
and benchmark datasets use the same bounded requirement; and lookbacks at or above the 5,000-bar
cap fail explicitly rather than silently producing insufficient-history results. Focused
materialization coverage passes `21/21`, affected EasyScan/Strategy Lab coverage passes `82/82`,
and the current authoritative backend gate passes `1343/1343` at `79.60%`.

#### Current continuation — 2026-08-10 column-editor repair and 230-image board acceptance

The latest no-update acceptance evidence is:

- benchmark watchlists now receive their configured analytical columns, and the integrated
  column editor is a bounded dense grid with scrolling rather than a compressed strip;
- the first strict rerun exposed 19 deterministic screenshot drifts; review identified only the
  intentional column-schema render and stale 1440px seeded dates, so only those baselines were
  regenerated;
- complete isolated seeded board-guided visual matrix: `100/100` in `7.7m` across 1920×1080 and
  2560×1440 at 100% and 125% display scale, without update mode;
- frontend Vitest: `665/665`; `vue-tsc --noEmit`; 468-module production build; visual manifest,
  YAML/JSON parsing, `git diff --check`, and backend/worker/research-runner error-signature audit:
  pass;
- reference board: 230 media sources across 26 surfaces, validator `230/230`;
- isolated acceptance stack stopped without deleting its evidence volumes.

No acceptance flexibility was used for the code repair or baseline refresh. The 230-image board
and deterministic seeded fixture remain explicitly an interim represented-state acceptance track;
the unresolved gap records are still `REF-SHELL-V25`, `REF-STATE-VARIANTS`, `REF-LINKING-V25`,
`REF-STUDY-LAB-V25`, `REF-ENV-TOKENS`, and `REF-PERMISSION-REVIEW`, alongside broader free-source
provider/entitlement/taxonomy coverage, native physical multi-monitor validation, bounded-versus-
long-duration endurance, and the final requirement-by-requirement audit.

#### Current continuation — 2026-08-10 F9e/F8l closure, reference refresh, and final current-tree gates

The latest current-head acceptance evidence is now:

- import/reset render-boundary repair: F9d→F9e passes `10/10` across five repetitions;
- hidden top-down loader gate: focused store regression passes `44/44`;
- complete authenticated Chromium matrix: `78/78` in `12.2m` with one serial worker;
- full frontend Vitest: `665/665` across 91 files;
- `vue-tsc --noEmit`, production Vite build, root `git diff --check`, and recent backend/worker/
  research-runner error-signature audit: pass;
- authoritative Docker-backed combined backend gate: `1,319/1,319` at `79.60%` coverage;
- refreshed official reference pack and composite board: `230/230` media sources validated across
  26 surfaces, including official Condition Editor, filter-selection, symbol-linking, and
  historic-column pages.

The fix-first tie-break was applied to both localized browser defects; neither blocked the goal,
and no acceptance flexibility, visual threshold, mask, or product criterion was changed. The
single completion bar remains open for the documented exact-build/unrepresented visual states,
broader provider/entitlement/taxonomy evidence, native physical multi-monitor validation,
governed endurance beyond bounded stress, and the final requirement-by-requirement audit.

Branch:
- `feat/tc2000-frontend-rework`

Latest continuation superseding the older checkpoint below (2026-08-10T01:06Z): the board
comparison exposed and closed a repository-controlled compact-window defect in `RatioUPlot`.
uPlot's default HTML legend was duplicated below the canvas and could collide with warning/footer
content; `legend: { show: false }` is now explicit and covered by a unit regression. The focused
top-down/ratio/crosshair browser set passes 6/6 with one intentional seeded-only skip, and the
browser overlap oracle passes before expected-content screenshot comparison. Frontend Vitest is
664/664; type-check and production build pass. The current fresh seeded board project remains
10/24 at 1920x1080/100%, with 14 screenshot/content-baseline differences retained as open gaps;
no snapshot, mask, threshold, or product criterion was relaxed. This checkpoint does not close the
full goal: exact-build/unrepresented visuals, live provider/entitlement and taxonomy coverage,
native multi-monitor, endurance, and final audit requirements remain open.

The subsequent full board-guided matrix was regenerated once against a fresh controlled fixture
and then rerun without update mode: `96/96` across all four required display environments. This
supersedes the earlier 10/24 stale-baseline observation; the regenerated images are deterministic
local interim baselines, not exact-build approvals. The reference pack was subsequently expanded
to 230 media across 26 surfaces; the visual run remains valid because the application and local
baselines did not change.

Current implementation checkpoint (latest recorded continuation): the workstation shell, linked
Golden Layout mechanics, uPlot host/plugin path, top-down analysis contracts, row-and-column
virtualized watchlists, unified Python/Study Lab execution boundary, and free-source provider
governance are implemented and covered by deterministic/frontend/backend regressions. New-
workstation search, symbol/expression resolution, comparison legs, and industry-proxy selection
now explicitly read the local canonical security master (`canonical_only=true`); legacy/default
provider discovery remains available outside that path. The latest authenticated flow gate passes
`78/78`; the clean board-guided visual matrix passes `96/96` across the four required environments;
frontend type-check/build and the latest authoritative Docker-backed backend gate pass. The
230-image reference board remains the active visual authority for represented states. Completion
remains open for real free-source top-down population, unrepresented or ambiguous exact-build
visual states, opt-in live-provider evidence, native physical multi-monitor behavior, endurance
beyond the governed bounded stress budget, and any uncovered requirement-level product/backend
acceptance item; none is silently promoted by this checkpoint.

The latest freshness audit unified Market Gauge with the shared workstation normalizer, ensuring
backend `coverage_limited` and frontend `coverage-limited` produce the same visible state and
warning styling; delayed now receives the same explicit warning treatment. Focused coverage passes
`22/22`, rebuilt `F8w-a` passes `1/1`, and the complete browser/visual gates remain green. The broad
browser run also found and repaired two localized
tie-break cases: idempotent repeated-popout cleanup (`F8f` repeated `5/5`) and the explicitly
allowed logout `Authentication required` page diagnostic (`F5` `1/1`). No visual baseline, mask,
threshold, or acceptance criterion changed; the remaining external/reference and scope gaps stay
explicitly tracked.

The latest rendered audit also fixed a real virtual-watchlist viewport overflow defect and
a Study Lab Boolean promotion race. All four seeded visual environments pass independent
row-count, viewport-containment, and core-header overlap checks. Board-covered states use the
190-image reference board plus deterministic local baselines; loading, provider-error, stale,
partial, and blocked-pop-out baselines are retained as explicit interim evidence while their
manifest states remain `required_missing`.

The latest fix-first geometry audit also corrected chart Compare/Plots/Templates controls that
could overlap the uPlot OHLC readout. The chart surface reserves a dedicated top strip, and the
visual harness now rejects chart control/readout and control/control intersections. Prior affected
baselines were preserved before refresh; rebuilt board-guided visual `32/32` and authenticated
Chromium `66/66` pass with the corrected layout. This closes the repository-controlled overlap
defect but does not close exact-build/unrepresented, provider-live, hardware, endurance, or other
scope gaps.

The subsequent Study Lab audit closed a second class of asynchronous defects: queued runs now
continue polling until terminal, late persisted-run hydration cannot overwrite a newer run,
and destroyed virtual tools cancel runs whose create response arrives after unmount. The full
serial authenticated matrix now passes cleanly, including Study Lab, top-down drilldown,
linking, pop-outs, legacy routes, uPlot performance, and workstation churn.

The shared tool-window symbol-link selector now listens only to the native `change` event.
Browsers can emit both `input` and `change` for one select interaction; accepting both had
allowed duplicate link-bus publication and redundant workspace persistence/refresh work.
Focused component coverage now verifies one update for the combined browser event sequence.

The dock host's exposed destroy action now performs the same complete teardown as Vue
unmount: virtual Vue roots are released, Golden Layout is destroyed and dereferenced, and
the resize observer is disconnected. This closes an imperative pop-out/recovery cleanup
path that previously destroyed only Golden Layout and could retain observers or detached
tool roots.

The workstation root no longer re-processes symbol-link select changes during event capture.
`ToolWindow` is the single owner of link-group publication; the root capture handler now only
closes the search overlay. This prevents a single link selection from being persisted and
propagated twice while preserving the shell's outside-change dismissal behavior.

An elevated Chromium rerun of the focused authenticated workstation matrix passed F8m, F8n,
and F8r (yellow/grey symbol-link isolation, timeframe-link propagation, and tool-header
geometry separation) 3/3 in 9 seconds. The preceding un-elevated attempt failed before page
startup at macOS Chromium `mach_port_rendezvous` permission setup; it is recorded as an
environment launch failure, not a product failure.

The complete backend unit suite subsequently passed 988/988 with the repository coverage
gate satisfied at 69.90% (55% required). The run produced only the known Nautilus/pandas
deprecation warnings; no provider, research, sandbox, or workstation unit failure occurred.

The Docker-backed backend integration suite also passed its complete 281/281 matrix in
169.49 seconds with 54 known Nautilus/pandas warnings. The first un-elevated invocation
could not access the Docker socket and produced setup errors before tests ran; the elevated
rerun started the containers and is the authoritative result.

The reference-board validator confirms all 190 retrieved board images are locally present.
The strict visual-manifest validator intentionally fails closed when invoked with
`--require-approved` because the board-guided policy is not exact-build approval; this is a
targeted stronger audit, not a blanket blocker for the workstation. The non-strict manifest
validator and board-guided visual matrix are the active acceptance evidence, with every
unrepresented state recorded in the manifest and board gap register.

The first full serial browser matrix exposed a Study Lab polling race under accumulated browser
load: the backend runner completed the durable job, but a status-derived Vue Query interval
stopped after only two queued polls. The interval is now fixed at one second while the query's
existing terminal-state `enabled` predicate remains authoritative. Isolated F8g passed; the
serial reproduction is being rerun against this correction.

The follow-up reproduction showed that virtual-tool remounts could still discard the interval
before the persisted run was collected. Study Lab now owns an explicit one-second durable-run
poll loop and re-arms it whenever a run ID is created or hydrated. The rebuilt serial Study Lab
subset passes F8g/F8o/F8p/F8q 4/4 in 12 seconds.

The rebuilt full authenticated Chromium matrix now passes 43/43 in one elevated worker in
1.8 minutes, including all Study Lab, linking, pop-out, top-down, legacy, dashboard, screener,
and radar flows. This supersedes the earlier partition-only browser evidence for the current
frontend build, although it remains functional evidence rather than exact-build visual approval.

The bounded isolated-runner pressure probe now passes all five configured rounds: each canceled
600-cell batch observed cancellation and cleaned its sentinels while the concurrent scalar job
completed. This is stronger live pressure evidence, but does not replace indefinite soak or
broader multi-process resource/escape testing.

The live resource/isolation probe now passes the configured 768 MiB memory cgroup, 64 MiB tmpfs,
no-network/read-only/non-root configuration, and eight-process aggregate-pressure checks. The
orphaned-job recovery probe also completed a claimed job after killing and restarting only the
runner, with no stale cancellation or progress sentinel. Indefinite soak and adversarial escape
coverage remain separate gates.

The local four-environment visual harness also completed its deterministic geometry/containment
checks, but all four screenshot comparisons remain unapproved: measured differences are roughly
2% (above the 0.5% local threshold) against stale local snapshots, and the strict manifest still
marks the exact-build reference `required_missing`. No screenshot baseline was promoted.

The live sandbox escape probe also passed: unshare, setns, mount, ptrace, fork, network, subprocess,
and read-only-root writes were all denied under the configured seccomp/no-new-privileges runner.

The live-provider collection was executed without fabricating credentials: all 348 optional
ETF-provider/OpenFIGI probes were skipped by their credential/opt-in guards. Deterministic
provider and SEC no-key evidence remains green; configured multi-provider live acceptance still
requires entitled credentials and terms review.

The browser performance suites now pass all three local guards: 100,000-point uPlot zoom/pan,
multiple chart initialization/recovery without canvas/tool growth, and repeated multi-window
churn with a bounded source workspace. This closes the runnable performance slice; native
multi-monitor and indefinite soak evidence remain external/long-running gates.

The streaming screener also now treats indicator-cache persistence as an optional,
observable optimization: failed cache commits roll back, produce a structured warning,
and leave canonical scan results usable rather than silently poisoning the transaction.

Study Lab polling also enforces a non-null refresh contract: missing run payloads become
bounded query errors rather than `undefined` cache entries, with active-run destruction
and empty-response coverage covered by the component regression suite.

The active Compose ARQ worker now registers the existing canonical nightly OHLCV refresh
task at 05:00 UTC behind `MARKET_DATA_REFRESH_SCHEDULE_ENABLED`, disabled by default so
deployments must explicitly review free-provider entitlements and quotas before enabling
it. The task continues to write only through the canonical local database path.

The isolated research handoff is now deployable end-to-end: Compose gives the backend and
runner the same `/jobs` and `/results` volumes, the backend prepares those private shared
directories for UID 10001 before enqueueing, and the runner returns a structured
`memory_limit` diagnostic for in-process allocation pressure while surviving the job.
This closes the previously hidden fresh-volume permission/path gap; broader orphan-job,
multi-window, and full security/resource acceptance remain separate gates.

The basic orphaned-claimed-job case is also verified live: a `.running` job survived a
runner restart, was requeued at startup, completed from the canonical prepared payload,
and left no residue. Pressure concurrency/cancellation and broader sandbox stress remain
separate acceptance gates.

The live cancellation-under-pressure case is now also verified: a uniquely named 10,000-cell
prepared-universe batch was claimed by the non-root runner, observed its cancellation sentinel
during execution, returned a structured `canceled` / `batch_canceled` result with bounded
completed-cell artifacts, and left the runner healthy. Probe artifacts were removed explicitly.
This closes cancellation during a large batch; multi-process namespace/resource stress remains
an acceptance gate.

The repeated pop-out browser audit also exposed and closed a real persistence defect: Golden
Layout's transient visible-key observations could delete serialized source windows during
repeated float/close churn. `applyActiveLayout` now persists geometry only; explicit close
actions remain the sole destructive window operation. Store coverage and the ten-cycle browser
regression pass, simultaneous independent pop-out recovery, the tool-menu/drag-handle browser
check, and the full authenticated flow remain green at 29/29 with clean backend logs.

The deep top-down browser flow also exercises constituent traversal through the virtual list's
real `Space` keyboard path, asserting that the next canonical member becomes the active symbol
without leaving the workstation route.

Read-only authenticated identity/settings reads use the detached short-lived session path;
mutating authentication/settings routes retain the request-scoped transaction. The rebuilt
browser flow and backend/runner/worker log audit now remain clean across the repeated login,
streaming screener, workstation, and legacy-route matrix.

The detached-auth cleanup was regression-tested against rollback expiration: the fully
loaded identity is expunged before the shielded rollback/close sequence, so `/auth/me`,
`/auth/settings`, and streaming ownership checks receive a usable object after the session
has ended. The focused lifecycle suite passes 3 tests, the full backend unit suite passes
965 tests at 69.83% coverage, and the rebuilt authenticated Chromium flow passes all 29
flows, including Study Lab. The timestamp-default Alembic repair (`ea0f1a2b3c4d`) has also
passed a fresh current-head PostgreSQL 16 upgrade, one-step downgrade, re-upgrade, and
direct `watchlist_item.flagged` `NOT NULL DEFAULT false` invariant audit. These checks do
not relax the single completion bar or the still-open exact-build visual, provider-live,
pressure, multi-window performance, and broad parity gates.

VirtualWatchlist Python column and condition polling now rejects missing batch payloads with a
bounded error before Vue Query can cache `undefined`; this keeps empty/partial research data
explicit at the tool boundary. The same boundary is enforced for Market Gauge, retained
EasyScan results, Research Results, condition columns, and indicator batches. Focused
workstation coverage is 61 tests, the full frontend suite is 555 tests across 84 files, and
rebuilt Chromium remains 29/29. This hardening does not relax the
single completion bar or the exact-build visual/provider/pressure/performance/parity
gates.

The requested periodic Docker cleanup was also run after the rebuilt-stack acceptance pass;
active branch containers and named volumes were retained and 15.68GB of dangling Docker
state was reclaimed.

The Docker-backed integration suite also passes all 281 tests with 54 existing dependency
warnings. The integration-only coverage command remains a diagnostic subset and therefore
does not satisfy the repository-wide threshold; the acceptance run is recorded with
`--no-cov` while the full unit command remains the coverage gate.

Controlling objective:
- This section and `docs/tc2000-visual-parity.md` are the controlling specification for
  the branch and supersede every older or narrower frontend-rework plan where they
  conflict. Do not silently reduce, defer, phase, reinterpret, or substitute any part
  of this completion contract during implementation.
- Replace the authenticated primary frontend with a pixel-close, rebranded clone of
  TC2000 Version 25 desktop build `25.0.9571` and its interaction model.
- Treat this as one continuous implementation stint with one completion bar. Internal
  checkpoints are for repository continuity, not partial delivery, phased scope, or an
  MVP stopping point.
- Keep Vue 3, TypeScript, Vite, and uPlot. uPlot remains the only chart renderer because
  fast rendering, direct canvas control, and flexible plugins are non-negotiable.
- Use Golden Layout's Vue-compatible virtual-component model for arbitrary docking,
  tab stacks, maximizing, saved layouts, browser pop-outs, and multi-monitor use.
- Match TC2000 Version 25 desktop geometry, density, colors, control styling, window chrome,
  menus, dialogs, keyboard behavior, and interaction states as closely as practical,
  while retaining this platform's branding and using original CSS/SVG assets rather
  than TC2000 logos or proprietary images.
- Keep the existing frontend available under `/legacy/*`. Do not migrate its dashboards.
  Radar, Strategy Lab, Baskets, ETF Holdings administration, seasonality, options, and
  provider diagnostics remain available only through legacy routes and do not appear
  in the new primary interface.
- Exclude visible options, brokerage/trading, news, analyst ratings, earnings, and full
  financial statements. Create explicit capability contracts, source-level TODOs, and
  extension documentation for all excluded or data-blocked features without rendering
  misleading disabled shells in the primary interface.
- Continue using the current provider-neutral polling model. Do not add streaming quote
  infrastructure as part of this task.
- Make the backend/data work required by the workstation part of the same completion
  contract: API-first free-source reconciliation, canonical security mastering,
  point-in-time market groups, batch analytics, adjusted-history correctness, provider
  entitlement reporting, and isolated user-code execution are not follow-up projects.
- Use one Python-native market-analysis language and SDK for chart calculations,
  watchlist columns, EasyScan conditions, alerts, gauges, reusable signals, and
  open-ended studies. Do not build or expose separate PCF, Optuma, and Python languages.
- Add a first-class Study Lab to the primary workstation for Optuma-style event,
  statistical, breadth, regime, distribution, forward-outcome, and current-versus-
  history research. Keep it separate from the execution/backtesting Strategy Lab.

#### Completion contract

This work is complete only when:
- the new TC2000-style workstation is the default authenticated application;
- every in-scope window, workflow, keyboard interaction, persistence path, linking
  behavior, and error state below is implemented;
- the top-down US-market workflow can be completed without leaving the workstation;
- the unified Python language works consistently across every programmable surface and
  executes only in the dedicated sandboxed research worker;
- Study Lab can define, run, reproduce, inspect, and reuse non-chart-centric historical
  research with structured native results;
- the new workstation has no required yfinance, paid-API, provider-specific frontend,
  or reliable consolidated real-time dependency;
- current canonical watchlists, drawings, alerts, screeners, indicator presets, OHLCV,
  instrument metadata, ETF holdings, and baskets remain usable;
- legacy-only surfaces remain directly accessible but absent from the new navigation;
- backend, frontend, integration, end-to-end, visual, console, log, performance, and
  sandbox-security, provider, migration, and diff validation all pass;
- unsupported functions and product domains are documented and stubbed honestly;
- every in-scope visual surface and interaction state is backed by an approved
  Version 25 reference, measured design tokens, deterministic baselines, and passing
  behavioral plus screenshot comparisons;
- no temporary placeholder, dead control, unexplained visual mismatch, or unhandled
  known failure remains before handoff.

#### Version 25 visual-reference and parity contract

`docs/tc2000-visual-parity.md` is the complete visual implementation contract. It pins
TC2000 desktop build `25.0.9571`, records the official source catalogue, defines the
capture and measurement process, and prevents visual implementation from being based on
memory or informal resemblance.

Visual authority, highest to lowest:
1. authorised live desktop captures from Version 25 build `25.0.9571`;
2. official help material explicitly tagged Version 25;
3. official Version 23/24 help only when a live Version 25 capture proves the surface
   remains materially unchanged;
4. Version 20 help only as behavioral history;
5. third-party material for discovery only, never pixel acceptance.

"Authorised live capture" means a provenance-verifiable capture of the actual pinned
desktop build, not a capture that must be made locally by the implementation machine.
Permission-cleared online captures and controlled-storage reference packs are eligible
when the manifest verifies the build, state, capture environment, unmodified hash,
source/permission classification, and reviewer approval. Official Version 25 online
material is likewise eligible where it covers the required state. Third-party material
cannot become a visual baseline without independently establishing those facts.

The release notes at <https://www.tc2000.com/features/whatsnew> are the generation/build
authority. The generic download page currently exposes stale Version 24 copy and does not
override the dated release record or a captured Version 25 desktop.

Before a tool can satisfy visual completion:
- create `tests/visual/references/tc2000-v25/manifest.yaml`;
- obtain approved references for every required shell, window, menu, dialog, chart,
  watchlist, column/filter, gauge, alert, notes, and Study Lab state;
- record build, date, source, resolution, display scale, theme, crop, dynamic masks,
  measurements, interaction recipe, SHA-256, review status, and permission/storage
  classification for every reference;
- measure and centralize geometry, typography, spacing, borders, gradients, colors,
  icon boxes, scrollbars, shadows, overlay order, and interactive states;
- capture deterministic product baselines at 1920x1080 and 2560x1440, each at 100% and
  125% display scale with 100% browser zoom;
- separately verify layout robustness at 125% browser zoom;
- validate the corresponding mechanics through interaction tests; a static screenshot
  never proves linking, keyboard navigation, docking, pop-outs, chart interaction,
  editors, or recovery behavior.

Pixel acceptance:
- no unexplained geometry difference greater than one CSS pixel;
- tokenized dimensions and declared typography exactly match approved values;
- solid-color CIEDE2000 delta E is at most 2;
- the unmasked differing-pixel ratio is at most 0.5% per approved image;
- dynamic masks are minimal, named, owned, and justified;
- no broad mask or raised global threshold may hide a structural mismatch;
- every baseline change receives human review and an intentional-change note.

Reference images remain non-distributable test/reference material. Ship only original
platform branding, CSS, SVG, and iconography. If protected captures cannot be committed,
keep them in controlled storage and commit the manifest metadata, hashes, capture
instructions, and measurements needed to reproduce the comparison.

#### Desktop shell and workspace mechanics

Replace the icon-sidebar and route-per-feature model with a TC2000-style desktop shell:
- compact global menu bar;
- workspace/layout tab strip;
- active-symbol entry and symbol-history navigation;
- provider/freshness/status area;
- central dockable tool-window surface;
- original platform branding rather than TC2000 branding.

Every tool window must share a dense TC2000-style chrome with:
- title and active-symbol display where applicable;
- symbol-link selector;
- tool-specific menu;
- drag handle;
- tab-stack behavior;
- maximize/restore;
- float/pop-in;
- close;
- minimum-size and resize constraints;
- focused/active state that is visually distinct without consuming excessive space.

Workspace behavior:
- allow arbitrary row/column docking, tab stacks, drag rearrangement, maximization,
  browser pop-outs, and restoration of exact sizes and positions;
- use Golden Layout virtual components so Vue retains ownership of its component tree;
- persist only serializable tool configuration and state, never DOM nodes, uPlot
  instances, request caches, or transient hover/crosshair state;
- use one elected browser window as persistence leader;
- synchronize pop-outs using `BroadcastChannel`, with same-origin storage events as a
  fallback;
- synchronize symbol changes, active list rows, explicitly linked timeframes, crosshair
  timestamps, code/library changes, layout changes, and logout;
- transfer persistence leadership automatically if the leader closes;
- keep a window docked and show a clear notification if the browser blocks a pop-out;
- restore an unexpectedly closed pop-out to its source layout on the next load.

Reproduce TC2000 Version 25 symbol-link semantics:
- use the exact current Version 25 link-group names and colors captured in the visual-reference
  audit;
- windows in the same normal group follow symbol changes;
- yellow behaves as the global/wildcard receiver;
- gray remains isolated until manually changed;
- link behavior crosses workspace tabs and browser pop-outs;
- link events carry stable instrument identity, not only a display ticker.

Global keyboard behavior:
- typing while focus is outside an editor opens symbol search;
- `Space` and `Shift+Space` traverse the focused list forward/backward;
- arrow keys move list selection;
- `Enter` activates the selected item;
- `Ctrl+mouse-wheel` traverses symbols in the focused list;
- chart shortcuts retain zoom, pan, log scale, latest-bar, drawing cancel/delete, and
  help behavior;
- no global shortcut fires while a text, code, numeric, or search editor owns focus;
- tool menus expose the current shortcut so the interface remains discoverable.

#### Factory and personal layouts

Ship immutable factory layouts that users can clone:

`US Top Down` is the default layout and contains:
- major benchmark list;
- cap-weighted/equal-weight comparison;
- sector list;
- industry list;
- constituent list;
- primary chart;
- ratio/relative-strength chart;
- technical, breadth, provenance, and coverage summary.

`TC Classic` contains:
- watchlist;
- main chart;
- symbol notes in place of unavailable news.

`Drill Down` contains:
- sector list;
- industry list;
- component list;
- selected-symbol chart;
- tabbed sector-comparison chart.

`Sector by Year` contains:
- linked sector, industry, and constituent lists;
- selectable year-performance columns;
- selected-symbol and normalized-comparison charts.

`1 Chart` contains:
- an uncluttered full-workspace chart.

`4 Timeframe` contains:
- four symbol-linked uPlot charts with independently configurable timeframes.

`Fundamentals` contains:
- chart;
- supported fundamental/metadata columns;
- supported-data report.

`Study Lab` contains:
- Python editor and parameter controls;
- universe, benchmark, timeframe, date-range, adjustment, and session selectors;
- coverage/look-ahead/survivorship preflight;
- run progress, logs, and cancellation;
- structured metrics, tables, plots, event occurrences, and linked-chart inspection.

Do not create Trading or Options factory layouts. Personal workspaces and layout tabs
must support create, clone, rename, reorder, import, export, delete, and reset-from-
factory operations. Factory definitions remain versioned, read-only, and resettable.

#### uPlot chart-window implementation

Refactor the current large chart component into:
- a framework-neutral chart model;
- reusable uPlot host/lifecycle layer;
- independent uPlot plugins;
- TC2000-style chart-window wrapper;
- serializable chart/template configuration.

Preserve and harden:
- candlestick, OHLC, line, area, baseline, Heikin-Ashi, Renko, Kagi, and Point & Figure;
- infinite historical backfill;
- automatic and logarithmic scales;
- current-price and visible-range projections;
- comparison series and normalized comparisons;
- ratio/synthetic expressions such as `=XLK/SPY`, `=XLK/XLE`, and `=NVDA/XLK`;
- indicator overlays and independent sub-panes;
- resizing of sub-panes;
- chart drawings and drawing ordering;
- alert lines and firing markers;
- supported dividend and split markers;
- linked crosshairs;
- multi-chart layouts;
- cached-history and background-fetch messaging.

Chart templates must save and restore:
- plot stack and order;
- styles and colors;
- panes and pane heights;
- axes and scale settings;
- timeframe;
- adjustment/transform settings;
- drawing defaults;
- comparison settings;
- event-marker visibility;
- indicator parameters and timeframe locks.

Applying a template must not replace the active symbol. Templates support save, clone,
rename, import, export, delete, and factory reset.

The plot library must support:
- price history;
- every locally implemented indicator;
- relative strength against any selected symbol;
- normalized comparison plots;
- scan plots;
- watchlist/basket synthetic indexes;
- Python calculations that evaluate to numeric series.

Plot interaction must support:
- hover legend;
- edit, move, hide, duplicate, and delete;
- drag a numeric plot/indicator into a watchlist to create a value column;
- drag a condition into a watchlist to create a Boolean column;
- copy a plot or condition to another chart, watchlist, EasyScan, or alert through
  TC2000-style target mode.

uPlot performance rules:
- Golden Layout resize events flow through a single `ResizeObserver`/`setSize` path;
- ordinary resize, docking, tab switching, and maximization must not recreate uPlot;
- identical OHLCV requests are deduplicated across linked charts using symbol,
  timeframe, adjustment, range, and transformation query keys;
- hidden tabs suspend polling and expensive redraws;
- destroyed tool instances release canvases, observers, subscriptions, and plugins.

#### Watchlists, related lists, and column mechanics

Implement a virtualized TC2000-style watchlist window supporting at least 10,000 rows.

Supported list sources:
- personal lists;
- managed EasyScan result lists;
- system market-group lists;
- ETF/index-proxy constituent lists;
- sectors;
- industries;
- related items;
- combo lists using union, intersection, and exclusion rules.

Row behavior:
- mouse or keyboard selection publishes to the window's symbol-link group;
- active symbols remain visibly selected;
- personal lists support drag reordering;
- compatible lists support drag/drop copy or move;
- multi-select can launch comparison charts and bulk list operations;
- context menus support add, copy, move, remove, flag, note, chart, alert, related lists,
  and membership inspection;
- list selection is retained by instrument ID after sorting/filtering, not by row index.

Reusable column types:
- raw price and volume;
- numeric/value;
- Boolean/condition;
- tag or list membership;
- Python calculation;
- indicator output;
- relative strength and period performance;
- supported metadata/fundamental values;
- provenance/freshness where useful.

Column behavior:
- insert, delete, duplicate, rename, resize, and reorder;
- horizontal scrolling;
- vertical stacking of multiple values in one visual column;
- column grouping;
- saved reusable columns and column sets;
- configurable header, decimals, units, positive/zero/negative colors, alignment, and
  missing-value display;
- the current workstation editor now persists percent-versus-number format and bounded
  decimal precision for numeric, indicator, and Python-derived columns;
- ascending/descending click sort;
- manual ordering;
- Boolean/tag pinning above the remaining value sort;
- copy/paste through the internal library clipboard;
- drag an indicator/condition/calculation from another tool to create a column;
- refresh timestamp, current filter, polling state, and manual refresh in window chrome.

#### Unified Python market-analysis language

Use normal Python syntax with one versioned platform SDK across charts, watchlists,
EasyScan, alerts, gauges, reusable signals, and Study Lab. A simple calculation is a
short Python program such as `result = ta.rsi(market.close, 14)`; a larger study uses
the same syntax, editor, runtime, functions, versioning, and output contracts.

SDK namespaces:
- `market`: OHLCV, instruments, universes, benchmarks, metadata, events, sessions,
  memberships, and point-in-time data access;
- `ta`: the platform's technical indicators and transformations;
- `stats`: descriptive statistics, streaks, ranks, percentiles, rolling calculations,
  correlation, regression, and distributions;
- `research`: occurrences, forward returns, regimes, conditional outcomes, breadth,
  cross-sectional studies, and current-versus-history comparisons;
- `output`: typed metrics, tables, plots, event sets, and dashboards.

Language rules:
- do not implement independently executable PCF or Optuma syntax;
- reproduce useful TC2000/Optuma semantics through canonical Python SDK functions and
  searchable migration documentation;
- use the same saved code asset/version everywhere rather than copying source into each
  chart, column, scan, alert, or study;
- let the visual condition builder edit the supported subset of the same Python AST;
  Python source remains authoritative when code exceeds the visual subset;
- preserve source positions, dependency/required-lookback analysis, diagnostics, and
  recursive dependency detection;
- batch-evaluate by universe and timeframe so watchlists never issue per-cell calls;
- pin every consumer to an immutable code version and require an explicit upgrade when a
  newer version is published.

Every saved code version records:
- stable asset ID, name, intended output contract, source, parameters, and defaults;
- immutable version, SDK/runtime version, data dependencies, required lookback, and
  referenced symbols/universes;
- capability requirements, compile diagnostics, creator, and timestamps.

Code interfaces:
- SDK/capability registry and documentation;
- validate/compile and dependency preflight;
- scalar batch, numeric-series, Boolean-series, event-set, and structured-study execution;
- saved code CRUD/versioning/import/export through the workspace library;
- structured diagnostics, warnings, coverage failures, and execution-limit errors.

#### Sandboxed Python execution

Never execute user-authored Python inside FastAPI, the general ARQ worker, a browser
context, or any process that holds provider credentials.

Create a dedicated research execution service and worker image with:
- a non-root runtime and read-only root filesystem;
- an ephemeral per-run writable directory and no host filesystem mounts;
- no external network, secrets, provider credentials, subprocess creation, or runtime
  package installation;
- Linux namespace isolation plus seccomp/AppArmor restrictions where supported;
- explicit CPU, memory, wall-time, output-size, row-count, and file-size limits;
- heartbeats, forced termination, orphan cleanup, and structured limit failures.

Curated imports:
- explicitly approved numerical/research modules from the Python standard library;
- NumPy, pandas, SciPy, and statsmodels;
- the internal `market`, `ta`, `stats`, `research`, and `output` SDK namespaces.

Reject arbitrary imports, sockets, subprocesses, reflection into host internals,
unrestricted filesystem access, dynamic code execution, unsafe deserialization, and
runtime `pip` or package downloads. AST validation is a preflight and usability layer,
not the security boundary; the isolated process/container remains mandatory.

Execution flow:
1. parse the Python AST and return source-positioned diagnostics;
2. reject prohibited syntax/imports/attributes and validate the declared output type;
3. derive static data dependencies where possible and combine them with the explicit
   universe, benchmark, timeframe, date range, adjustment, and session configuration;
4. resolve all data through the canonical local database, never directly from a provider;
5. create a versioned dataset manifest and materialize read-only Arrow/Parquet inputs;
6. execute the pinned code/SDK/worker versions in the isolated worker;
7. validate and persist bounded structured outputs, logs, warnings, exclusions, resource
   use, and the reproducibility hash.

Dynamic market access is limited to instruments and universes already present in the run
manifest. Missing data produces a structured coverage failure rather than a provider
call. Interactive columns/scans use a warm worker pool and vectorized universe batches;
long studies use queued runs with progress, cancellation, and durable artifacts.

#### EasyScan, conditions, scan plots, and gauges

Generalize the current screener into a TC2000-style EasyScan workflow:
- select all instruments, asset class, watchlist, combo list, market group, basket,
  ETF-derived basket, or explicit symbols as universe;
- create nested AND/OR/NOT condition trees;
- add price, volume, indicator, metadata, relative-strength, or Python conditions;
- choose timeframe per condition;
- preview match counts;
- save, clone, rename, reorder, schedule, enable/disable, and delete;
- run synchronously for small prepared universes or stream progress for large/cold ones;
- cancel in-progress runs;
- display per-instrument preparation/evaluation failures;
- retain historical results.

Reusable actions:
- apply a saved condition as a watchlist filter;
- turn a condition into a Boolean column;
- create an alert from a condition;
- create a managed watchlist from an EasyScan;
- plot historical match count or percentage as a scan plot;
- create a market gauge from a saved scan;
- copy conditions between scans, columns, plots, and alerts.

Historical scan plots must start only when valid recorded history exists; do not fabricate
past membership or results.

The current Version 25 interaction model is authoritative: columns, True/False
conditions, filters, groups, stacks, and Market Gauges are edited as one integrated
watchlist workflow. Preserve EasyScan as the name and reusable saved-scan capability,
but do not reproduce the obsolete standalone Version 20 editor when current Version 25
behavior has replaced it.

#### Top-down US-market analysis

Create a versioned market taxonomy containing:
- logical benchmark identities separated from their official index series and tradable
  proxies, including SPX/S&P 500 where entitled plus SPY, RSP, QQQ, DIA, and IWM;
- all 11 Select Sector SPDR ETFs;
- normalized, source-labelled sectors and industries;
- verified industry ETF proxy associations;
- point-in-time ETF holdings memberships;
- representative, equal-weight, and comparison relationships;
- source, provenance, known-at time, composition date, and freshness.

Industry ETF semantics:
- treat industry ETFs as curated proxies associated with an industry, not as fictional
  children owned by a sector ETF;
- allow zero, one, or several verified proxy ETFs per industry;
- require source documentation and holdings/classification validation;
- expose “No mapped ETF proxy” when none is verified;
- never infer an ETF relationship solely from a similar name.

Index constituent semantics:
- use ETF holdings as an explicit proxy when official licensed constituents are absent;
- label the universe as ETF-proxy membership;
- surface snapshot date, known-at time, source quality, resolution count, and unresolved
  rows;
- fall back to metadata classification only with an equally explicit label;
- never silently claim official historical index membership.

Index-series semantics:
- use an official index series only when a configured provider entitlement supplies it;
- otherwise use a clearly labelled tradable proxy such as SPY;
- never display SPY data under an SPX label or imply that proxy holdings are official
  licensed index constituents.

Linked drill-down mechanics:
- selecting a benchmark loads technicals and its equal-weight comparison;
- selecting a sector loads industries, constituents, breadth, relative strength, and
  sector comparison;
- selecting an industry loads its constituents and verified proxy ETFs;
- selecting an industry proxy now publishes that proxy to the linked symbol group,
  loads its canonical bars/technicals, and preserves the selected sector/industry
  taxonomy context so the proxy can be compared against its sector without replacing
  the drill-down tree with the proxy's own holdings;
- selecting a constituent updates linked stock charts;
- one action creates sector/benchmark, industry-proxy/sector, stock/sector, and
  stock/benchmark ratio views;
- list traversal updates all windows in the same link group without route changes.
Ratio loads must discard late responses from an earlier symbol, timeframe, or point-in-time
selection so rapid top-down traversal cannot paint stale relative-strength data into the
active window.

Batch ranking columns:
- 1D, 1W, 1M, 3M, 6M, YTD, and 1Y performance;
- benchmark-relative performance;
- ratio trend and momentum;
- RSI;
- price relative to 20/50/200 moving averages;
- distance from 52-week high/low;
- volume ratio;
- provider coverage and freshness.

Top-down row adapters must preserve the backend `AnalysisCell.warning` message for
performance, relative-strength, technical, and calendar-year cells. The workstation
watchlist renders those messages (for example, `⚠ insufficient_history`) instead of
turning an unavailable value into an unexplained blank or dash.

Breadth analytics:
- percentage above configurable 20/50/200 moving averages;
- percentage near 52-week highs/lows;
- percentage making configurable-period highs/lows;
- percentage in configured uptrend/downtrend;
- aggregate distance from selected averages;
- current snapshot and historical series;
- click-through to passing/failing constituent lists;
- comparison of multiple groups side by side.

The primary breadth surface now exposes a canonical group selector, Above/Below controls
for the 20/50/200-MA states, and a linked passing/failing member drill-down. It loads
the selected group's snapshot and current/historical breadth through the existing local
analysis APIs; the drill-down preserves canonical symbol identity and publishes the
selected member to the workstation link group. Timeframe (daily/weekly/monthly) and
split-adjustment controls are persisted with the tool and forwarded to all four group,
snapshot, current-breadth, and historical-breadth requests.

The canonical breadth response also returns coverage-aware near-52-week-high/low
participation, configurable-lookback new-high/new-low participation, uptrend/downtrend
participation, and aggregate distance from the 20/50/200-day averages. The response
echoes the lookback and proximity parameters so saved studies remain reproducible;
the workstation currently surfaces the primary high/low, trend, new-high/new-low, and
MA-distance summaries while retaining the same explicit unavailable semantics.
It also returns `coverage_detail` for each metric family (individual moving averages,
near-52-week, new-high/new-low, trend, and each distance average), preventing a single
overall universe percentage from being misread as coverage for every statistic.
The response also carries point-in-time `member_metrics` keyed by canonical instrument ID,
so the workstation can open passing members for near-52-week, new-high/new-low, and trend
conditions without re-querying providers or deriving membership from aggregate percentages;
the active drilldown can switch between passing and failing members without changing the
selected condition or route.

The relative-rotation uPlot plane draws each member's color-coded sampled tail as a connected
trail before drawing its current/retained points and labels the four transparent state
quadrants, so the tail-length control represents visible history rather than only a count of
past observations.

Relative rotation:
- accept benchmark, peer universe, timeframe, lookback, sampling, and tail length;
- calculate aligned relative-strength series;
- derive transparent relative-trend and relative-momentum dimensions;
- classify leading, weakening, lagging, and improving;
- calculate heading, distance, velocity, recent transition, and time in state;
- provide interactive tails and sortable companion table;
- surface partial-overlap and insufficient-history warnings;
- call the feature “relative rotation,” not a proprietary JdK/RRG implementation.

#### API-first free-source backend and data foundation

The frontend must consume canonical platform APIs only. It must never know provider
symbols, credentials, quotas, endpoint shapes, or fallback ordering.

Use the existing capability-oriented provider runtime, priorities, token buckets,
cooldowns, health measurements, request logs, provenance, and circuit behavior as the
foundation, but replace single-provider field selection with source reconciliation.

Required free-source provider roles:
- US security universe: reconcile Massive reference tickers, Alpaca assets, and Alpha
  Vantage listing/delisting data rather than trusting any one list;
- corporate identity: use SEC CIK/ticker/exchange associations as an official identity
  anchor while acknowledging that SEC does not guarantee complete exchange coverage;
- identifiers: use OpenFIGI v3 for FIGI mapping and listing reconciliation;
- current/delayed prices: use Alpaca IEX and permitted delayed SIP data, always exposing
  feed, venue scope, observation time, and freshness;
- broad EOD corroboration: use Massive free aggregates/reference endpoints only where
  the configured entitlement currently permits them;
- deep raw daily history: use Alpha Vantage raw daily history within its quota;
- adjustments: derive locally reproducible split/dividend-adjusted views from stored raw
  bars and reconciled corporate actions;
- corporate actions: reconcile Alpaca and Massive events with SEC evidence where useful;
- fundamentals: use SEC submissions/XBRL and explicitly identify every derived value;
- taxonomy: normalize source-labelled sector/industry data, ETF membership evidence,
  SEC SIC, and curated mappings without claiming licensed GICS data unless entitled;
- ETF holdings: retain issuer-native adapters, raw artifacts, and SEC N-PORT/N-Q
  reconstruction;
- macro/regime inputs: retain FRED;
- optional validation: allow a quota-limited secondary source such as Twelve Data, but
  make no core workflow depend on it.

Primary source-documentation anchors:
- Massive reference tickers: <https://massive.com/docs/rest/stocks/tickers/all-tickers>;
- Alpha Vantage listing status and raw daily history:
  <https://www.alphavantage.co/documentation/>;
- Alpaca market-data plan/feed semantics:
  <https://docs.alpaca.markets/us/docs/about-market-data-api>;
- SEC EDGAR company ticker/exchange files and scope caveat:
  <https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data>;
- OpenFIGI v3 mapping and limits: <https://www.openfigi.com/api/documentation>.

Nasdaq Trader/exchange directory files may be ingested as audit or backfill evidence.
They are not the primary master, are not treated as Nasdaq-only coverage, and are never
a runtime dependency.

yfinance policy:
- remove yfinance from every default priority and every completion/acceptance path;
- keep it temporarily only as an explicitly enabled legacy fallback if an existing
  legacy capability still requires it;
- attach provider provenance to all retained yfinance-derived values;
- prohibit new-workstation tests, fixtures, or startup from requiring it;
- remove the adapter once the legacy capability audit proves it is unused.

The absence of consolidated free real-time data is an accepted product constraint, not a
reason to fabricate a real-time experience. The workstation must distinguish `current`,
`delayed`, `stale`, `fetching`, `partial`, `coverage-limited`, and `unavailable`.

#### Canonical security master and provider reconciliation

Retain and extend the active canonical identity model:
- `Instrument`;
- `InstrumentListing`;
- `InstrumentIdentifier`;
- `InstrumentProviderSymbol`;
- `InstrumentProviderCapabilityStatus`;
- field-level provenance.

Consolidate the unused duplicate instrument-listing model so one definition and migration
source remain authoritative.

For each provider observation:
- retain the raw record, provider symbol, capability, observation time, and source terms;
- match strong identifiers before ticker/name text;
- resolve canonical instrument, listing, exchange/MIC, share class, and active state;
- store field-level source, confidence, observed-at, effective-at, and known-at metadata;
- detect ticker reuse, symbol changes, listing moves, class-share ambiguity, mergers,
  delisting, and relisting;
- queue ambiguous candidates for review instead of silently merging them;
- maintain listing/provider status independently so one provider cannot incorrectly
  deactivate a canonical instrument.

The local database is the authoritative read path. Scheduled/backfill jobs update it;
ordinary UI reads do not trigger uncontrolled provider fan-out.

#### Historical data, adjustment, and point-in-time correctness

Store raw provider bars separately from canonical derived views and retain provider/feed/
venue provenance. Add deterministic conflict selection, gap/anomaly detection, corporate
action reconciliation, rebuildable adjustment factors, cached derived timeframes, and
coverage ranges.

Support raw, split-adjusted, and total-return modes with a versioned adjustment set.
Calculations and caches must include adjustment mode/version in their identity.

Research and analysis rules:
- resolve universe membership as it was known at the evaluation time;
- never expose future bars, future constituent knowledge, or revised future metadata to
  a historical signal;
- distinguish event/signal time from forward-outcome time;
- exclude and count events that lack a complete requested outcome horizon;
- align comparisons on intersecting valid timestamps;
- never forward-fill across a gap that changes ratio/rotation meaning;
- label survivorship-biased or current-snapshot universes and reject them when a study
  explicitly requires point-in-time membership;
- return excluded instruments/events and exact reasons with every batch/study result.

#### Provider entitlement and capability governance

Add a versioned provider-entitlement registry with:
- provider, capability, configured plan, authentication requirement, and free/paid state;
- permitted personal/internal/commercial use and redistribution restrictions;
- request/token quota, historical horizon, venue coverage, and real-time/delayed/EOD
  semantics;
- effective/review date, enabled environments, and current live-probe result.

A provider is usable only when both its adapter and configured entitlement permit the
requested capability. Do not hard-code today's free-plan promises as permanent facts.

Promoting a provider/capability to supported requires:
- deterministic response fixtures and parser tests;
- capability/completeness and provenance tests;
- throttling, retry, cooldown, and failure-classification tests;
- an opt-in backend-reachable live probe;
- an entitlement/terms review.

Provider removal, changed terms, throttling, or exhausted quota must degrade the affected
capability honestly without inventing data or breaking unrelated providers.

#### Batch analytics and coverage APIs

Add batch-oriented backend services for:
- market-group trees, members, proxies, and related groups;
- technical/ranking snapshots;
- relative strength and normalized comparison;
- breadth and relative rotation;
- scan and Python-code evaluation;
- Study Lab runs and artifacts;
- coverage, provenance, and freshness;
- notes and workspace persistence.

Batch requests accept a universe selector, timeframe, as-of time, adjustment mode,
requested built-ins/code versions, filters, sorting, and pagination.

Each returned cell includes value, observation time, adjustment mode, source/freshness,
and structured warning/error. Each response includes universe provenance/membership
version, coverage, exclusions/reasons, calculation/code version, and refresh time.

Cache identity must include universe membership version, timeframe/date range/as-of time,
adjustment set, code/indicator/SDK version, requested fields, and source dataset versions.

#### Alerts, notes, and supported reports

Restyle price, indicator, and screener alerts as TC2000-style tools/dialogs.

Alert creation sources:
- chart price level;
- plotted indicator;
- saved condition;
- Boolean Python calculation;
- EasyScan entry/exit.

Retain alert status, repeat/rearm behavior, firing history, chart markers, notification
delivery, and instrument filtering.

Add per-symbol notes:
- autosave;
- modified timestamp;
- watchlist note indicator;
- symbol-linked notes window;
- user isolation.

Supported-data report:
- instrument identity and listings;
- sector and industry;
- market cap, P/E, beta, and dividend yield where available;
- 52-week range;
- average volume;
- identifiers;
- field-level provider provenance and freshness.

Do not expose earnings estimates/results, analyst opinions, news, or unavailable financial
statement fields.

#### Frontend architecture

Retain:
- Vue 3;
- TypeScript;
- Vite;
- Pinia for local interaction/session state;
- uPlot and the reusable portions of its existing plugins.

Add:
- `golden-layout` for workspace docking and pop-outs;
- `@tanstack/vue-query` for server state, polling, caching, invalidation, and deduplication;
- `@tanstack/vue-table` and `@tanstack/vue-virtual` for dense virtualized lists.

Core modules:
- `WorkspaceShell`: global menus, tabs, active workspace, search, and status;
- `WorkspaceLayoutHost`: Golden Layout integration, save/load, pop-outs, and recovery;
- `ToolRegistry`: tool metadata, factory, capability requirements, and schema version;
- `ToolWindowHost`: shared dense TC2000 window chrome;
- `LinkBus`: symbol, timeframe, crosshair, and selection events;
- `LibraryStore`: code assets, conditions, columns, column sets, scans, studies, chart templates,
  layout templates, and combo lists;
- `UPlotHost`: chart lifecycle, data binding, plugins, and resize behavior;
- `CapabilityRegistry`: supported, partial, and unavailable product/data capabilities.

Create centralized TC2000 Version 25 design tokens for:
- typography;
- spacing;
- window borders and gradients;
- toolbar height;
- menu and dialog geometry;
- tabs;
- hover/focus/selection states;
- scrollbars;
- table density;
- positive/negative/neutral colors;
- z-index and overlay rules.

Use the measured Version 25 font stack with Segoe-compatible fallbacks. Validate the
four required display-scale environments and the separate 125% browser-zoom robustness
case defined in `docs/tc2000-visual-parity.md`.

#### New persistence and API contracts

Keep existing dashboard tables and APIs untouched for `/legacy/*`. Create new persistence:

`workspace`:
- user ID;
- name;
- default flag;
- position;
- revision;
- settings;
- schema version;
- timestamps.

`workspace_tab`:
- workspace ID;
- stable key;
- name;
- position;
- Golden Layout configuration;
- active-window key;
- timestamps.

`workspace_window`:
- tab ID;
- stable instance key;
- tool type;
- title;
- link group;
- configuration;
- style;
- state-schema version;
- position;
- timestamps.

`workspace_library_item`:
- user ID;
- kind: code, condition, column, column set, scan, study, chart template, layout
  template, or combo list;
- stable key;
- name;
- version;
- payload;
- dependency metadata;
- timestamps.

`market_code_asset` and `market_code_version`:
- user ID, stable key, name, description, and intended output contract;
- immutable Python source version and SDK/runtime version;
- parameters/defaults, dependency metadata, required lookback, referenced symbols/
  universes, capability requirements, diagnostics, and timestamps.

`research_definition`, `research_run`, and `research_artifact`:
- owner, code-version reference, universe/benchmark/timeframe/date-range configuration,
  parameters, adjustment/session settings, and timestamps;
- queued/running/succeeded/failed/cancelled status, progress, heartbeat, resource usage,
  warnings, exclusions, dataset/reproducibility hash, and structured logs;
- typed compressed result artifacts for metrics, tables, plots, event sets, and
  multi-panel dashboards, with queryable metadata retained in PostgreSQL.

`provider_entitlement` and `dataset_snapshot`:
- provider/capability/plan, authentication, free/paid status, permitted deployment use,
  redistribution restriction, quota, historical horizon, venue/freshness semantics,
  review date, and enabled environments;
- exact input versions, universe membership, adjustments, provenance, coverage, and
  prepared Arrow/Parquet artifact references used by a code execution.

`instrument_note`:
- user ID;
- instrument ID;
- content;
- timestamps;
- unique user/instrument constraint.

`market_group`:
- stable key;
- type;
- name;
- parent;
- representative/equal-weight instrument;
- source and provenance;
- effective/known-at metadata.

`market_group_member` and `market_group_proxy`:
- group/instrument relationship;
- weight;
- relationship type;
- source;
- effective and known-at times;
- verification state.

Workspace endpoints:
- list/create/get/patch/delete workspaces;
- clone workspace;
- atomically save a complete workspace snapshot;
- library CRUD;
- library import/export.

Workspace snapshot writes:
- accept `base_revision`;
- atomically persist settings, tabs, layouts, and window states;
- increment revision;
- return `409` for stale revisions;
- let the leader fetch, merge disjoint instance-key changes, and retry once;
- create a named recovery copy instead of silently overwriting an unresolved conflict.

Code/research endpoints:
- SDK/capability registry and documentation;
- validate/compile;
- dependency and coverage preflight;
- scalar/series/Boolean/event batch evaluation;
- code asset/version CRUD and import/export through the workspace library;
- research definition/version CRUD, run/cancel/progress/log/artifact/compare/export.

Market/analysis endpoints:
- market-group tree;
- group details and members;
- related groups for a symbol;
- batch analysis snapshot;
- relative strength;
- relative rotation;
- breadth;
- per-instrument note read/write.

Batch analysis request supports:
- universe selector;
- timeframe and as-of time;
- requested built-in/code-version columns;
- filter and sort definitions;
- pagination.

Every returned cell includes:
- value;
- observation time;
- source/freshness status;
- structured warning/error where applicable.

Every batch response includes:
- universe provenance;
- coverage summary;
- excluded instruments and reasons;
- refresh time.

#### Polling, caching, and data flow

Use Vue Query as the single client polling coordinator:
- active latest-price views poll according to provider freshness policy;
- historical ranges do not poll;
- hidden tabs suspend chart polling;
- watchlists use one batch refresh per window rather than one request per cell;
- pop-outs share invalidation messages;
- only the elected leader initiates a refresh for a shared query key;
- stale requests are canceled when symbol, universe, timeframe, or code version changes.

Expose `current`, `delayed`, `stale`, `fetching`, `partial`, `coverage-limited`, and
`unavailable` states.
Provider failures leave prior data visible with stale/error labeling and retry actions.

Cache batch code, relative-strength, rotation, breadth, and study-preflight results using:
- universe membership/version;
- timeframe;
- as-of time;
- code/indicator/SDK version;
- requested columns;
- adjustment mode.

Alignment rules:
- use intersecting valid timestamps for comparisons;
- never forward-fill across a gap that changes the meaning of a ratio or rotation path;
- identify and exclude insufficient-history instruments with reasons;
- preserve point-in-time membership where the requested universe supports it.

#### Legacy interface and capability stubs

Routing:
- `/` and authenticated default routes open the new workstation;
- `/chart/:symbol` opens the default workspace and publishes the symbol to the active
  link group;
- current authenticated pages move under `/legacy/*`;
- legacy Radar, Strategy Lab, Baskets, ETF Holdings administration, seasonality,
  options, and provider diagnostics have no new-shell menu entry.

Preserve canonical data:
- watchlists;
- drawings;
- alerts;
- screeners;
- indicator presets;
- instruments/OHLCV;
- ETF holdings;
- baskets.

Do not migrate legacy dashboard layouts.

Create `docs/tc2000-parity.md` with every reviewed TC2000 surface and:
- supported/partial/excluded status;
- implementation location;
- backend/data dependency;
- validation evidence.

Create `docs/tc2000-capability-stubs.md` covering:
- options;
- brokerage/trading;
- news;
- analyst ratings;
- earnings/full financial statements;
- unavailable data/SDK capabilities.

Each stub must have:
- stable capability ID;
- intended inputs/outputs;
- provider/data requirements;
- frontend tool contract;
- explicit source-level TODO;
- enabling conditions;
- tests proving unavailable tools stay out of visible menus.

Backend provider protocols and frontend descriptors may exist for these domains, but their
routers/tools must remain unregistered until implemented.

#### Study Lab

Add Study Lab as a first-class primary-workstation tool. It owns open-ended market and
statistical research that is not naturally a chart indicator, ratio, scan, alert, or
position-based backtest.

Study Lab and Strategy Lab remain distinct:
- Study Lab answers what happened, how often, under which state/regime, how outcomes were
  distributed, and how the current state compares with history;
- Strategy Lab owns entries, exits, fills, positions, capital, portfolio state,
  execution assumptions, walk-forward tests, and paper-forward strategy behavior;
- both share code assets, indicators/statistics, universe resolution, point-in-time
  membership, coverage reporting, artifacts, and reproducibility primitives;
- new Strategy Lab signals reference immutable unified-Python code versions;
- existing `RULES`, `DSL`, and `PYTHON` strategy versions remain executable through
  compatibility adapters so saved work is not destroyed, but new authoring converges on
  the unified language.

Study types:
- arbitrary event definitions and historical occurrence analysis;
- positive/negative streaks and general state-duration studies;
- before/after behavior and forward returns over multiple horizons;
- breadth events, thrusts, new-high/new-low behavior, and moving-average participation;
- price/breadth and cross-market divergences;
- volatility, trend, breadth, and relative-strength regimes;
- calendar/day/month seasonality;
- cross-sectional ranking, correlation, regression, and relationship studies;
- distributions, percentiles, analogues, and current-state-versus-history comparisons.

Authoring and run controls:
- Python editor with autocomplete, signatures, SDK documentation, source diagnostics,
  formatting, and parameter declarations;
- generated parameter controls plus universe, benchmark, timeframe, date-range,
  adjustment, and session selectors;
- input-size, coverage, point-in-time membership, look-ahead, and survivorship preflight;
- run, cancel, clone, version, compare, archive, import, export, rerun-same-snapshot, and
  rerun-latest-data actions;
- durable queued status, progress, heartbeat, structured logs, warnings, exclusions,
  resource use, and artifacts.

Structured native result types:
- metric cards;
- time series and range/band plots;
- numeric/categorical bars and histograms;
- scatter plots;
- heatmap/matrix views;
- event sets;
- ranked/detail tables;
- summary-statistics tables;
- multi-panel dashboards composed from these types.

Implementation checkpoint: the unified runner now exposes typed `output.bar(...)` and
`output.range(...)` methods for the numeric/categorical-bar and lower/upper-band contracts.
The active Study Lab, persisted Research Results, and dashboard surfaces render both through
uPlot-backed components, with finite-value/dimension validation and no user-supplied UI code.
The active run panel also supports rerunning the immutable study against its saved snapshot
or latest canonical data through the versioned research API.
The primary editor includes editable factory templates for positive/negative close streaks,
moving-average participation, and relative-strength history; changing source returns the
editor to Custom Python while retaining the single unified language.

uPlot plus platform-owned plugins renders every axes-based numeric result. Vue/HTML
renders tables, metric cards, and layout. Do not add a second chart library and do not
allow study-authored HTML, CSS, JavaScript, or frontend components.

Result behavior:
- show sample size, mean, median, percentiles, dispersion, and confidence context where
  meaningful;
- highlight the current observation against the historical distribution;
- allow filtering/drill-down into underlying events and excluded cases;
- publish a selected occurrence's instrument/date to linked charts;
- export tabular artifacts;
- compare code/parameter/dataset versions;
- promote a suitable Boolean result to an alert, scan condition, watchlist column, or
  Strategy Lab signal source;
- save a suitable numeric series as a reusable chart plot.

Implementation checkpoint: Study Lab signal promotion now persists a user-owned Strategy
Lab definition whose immutable version snapshot references the promoted unified-Python
`code_version_id` and output contract. Archived, cross-user, wrong-kind, and unsupported
output versions are rejected. Strategy execution still follows the existing Strategy Lab
engine capability contract; promotion no longer creates a code asset that is invisible to
the Strategy Lab library.

Ship editable factory studies for:
- consecutive positive/negative closes;
- event frequency and occurrence browsing;
- multi-horizon forward returns;
- 90/90-style breadth events;
- new-high/new-low and moving-average breadth;
- price/breadth divergence;
- volatility and trend regimes;
- month/day seasonality;
- relative-strength regime changes;
- cross-sectional sector/industry ranking.

#### Failure and recovery behavior

Missing ETF holdings:
- use metadata-derived constituents only when available;
- label the fallback source;
- never imply official index membership.

Missing industry proxy:
- keep the industry and stocks usable;
- show “No mapped ETF proxy.”

Missing or misaligned bars:
- exclude misleading calculations;
- expose the exact reason;
- preserve other valid peers.

Unsupported Python/data capability:
- preserve/save the code version;
- report every missing SDK/data capability and coverage requirement;
- block dependent scans/alerts/columns/studies without losing configuration.

Sandbox timeout/resource violation:
- terminate and clean up the isolated worker;
- preserve bounded logs and execution metadata;
- return a structured resource-limit/security error without affecting API workers.

Provider throttling/outage:
- retain cached data;
- expose freshness/provider state;
- follow provider-policy retries and limits.

Changed or invalid provider entitlement:
- disable only the affected provider/capability;
- expose the plan/terms/configuration reason;
- fall through only to independently entitled providers.

Missing SPX/index series:
- use a clearly labelled tradable proxy such as SPY when configured;
- never silently rename the proxy to the official index.

Unknown/corrupt workspace tool:
- retain raw snapshot;
- load known windows;
- replace only the affected window with a recovery/export panel.

Concurrent browser sessions:
- use revision checks;
- merge only disjoint changes;
- create a recovery copy when automatic merge is unsafe.

Large lists:
- virtualize rows and columns;
- keep stable selection by instrument ID;
- cancel stale calculations;
- show incremental scan progress.

#### Required validation and acceptance

Backend unit/integration coverage:
- workspace CRUD, cloning, snapshots, conflicts, recovery, and user isolation;
- unified Python behavior across scalar/series/Boolean/event/study output contracts;
- AST diagnostics, source spans, dependencies, lookback, versioning, and cycles;
- sandbox network/subprocess/filesystem/import/reflection/dynamic-execution escape tests;
- CPU, memory, time, output, cancellation, crash, and orphan-cleanup enforcement;
- implemented SDK/indicator parity against the authoritative indicator engine;
- structured unsupported-capability and coverage errors;
- security-master matching, ambiguity, ticker reuse, delisting, listing moves, and
  provider field conflicts;
- provider entitlement, quota, cooldown, live-probe, and provenance behavior;
- raw/adjusted bar rebuilding and corporate-action correction;
- point-in-time membership, look-ahead prevention, complete forward horizons, and
  survivorship-bias handling;
- market taxonomy hierarchy and proxy provenance;
- no-proxy industries;
- batch snapshot filtering, sorting, pagination, and partial cell errors;
- relative-strength alignment and missing-history exclusion;
- breadth and relative-rotation math;
- Study Lab definition/version/run/artifact/reproduction behavior;
- notes and library isolation/import/export;
- unchanged legacy API behavior.

Frontend unit/component coverage:
- Golden Layout bind/unbind lifecycle;
- uPlot cleanup and non-recreation on resize/tab changes;
- every link-group rule;
- cross-window message handling and persistence leadership;
- keyboard routing and input-focus suppression;
- column add/remove/reorder/stack/pin/sort/manual ordering;
- Python editor, diagnostics, version-upgrade, and capability states;
- Study Lab output renderers and occurrence-to-chart linking;
- template application without symbol replacement;
- polling suspension and request deduplication;
- snapshot conflict recovery and schema upgrades;
- excluded tools absent from primary menus.

End-to-end flows:
- launch directly into `US Top Down`;
- select SPY and compare with RSP;
- rank all 11 sectors against SPY;
- select XLK and load industries/proxies/constituents;
- select NVDA and automatically open `NVDA/XLK` and `NVDA/SPY`;
- traverse constituents with Space while linked charts update;
- prove different/gray link groups do not change;
- float a chart and prove symbol/crosshair/persistence synchronization;
- customize, stack, pin, save, and restore watchlist columns;
- create a Python value column, use it in EasyScan, and create an alert;
- create the positive-close streak study, render its metrics/histogram, and inspect
  historical occurrences on a linked chart;
- promote a Study Lab Boolean result into a scan or alert;
- save/reload/import/export chart and layout templates;
- create/edit/lock/persist drawings;
- verify missing holdings, missing index series, stale bars, provider/entitlement failure,
  unsupported Python/data capability, sandbox failure, popup blocking, workspace
  conflict, and corrupt-tool recovery;
- verify legacy routes remain usable but absent from the primary interface.

Visual acceptance:
- complete the full capture matrix in `docs/tc2000-visual-parity.md`, not only the
  representative happy-path screens;
- maintain deterministic baselines at 1920x1080 and 2560x1440 at both 100% and 125%
  display scale, plus the separate 125% browser-zoom robustness check;
- compare component crops and full layouts against approved TC2000 Version 25 references;
- enforce one-CSS-pixel geometry, exact token/typography, delta-E-at-most-2 solid-color,
  and at-most-0.5-percent unmasked pixel-difference limits;
- require every mask and visual-regression difference to be narrowly justified,
  reviewed, and fixed when it is not an intentional product divergence.

Performance acceptance:
- cached symbol changes render without full-shell reflow;
- 100,000-point uPlot series remains interactively zoomable/pannable;
- 10,000-row watchlists do not create DOM proportional to row count;
- linked charts issue no duplicate identical OHLCV requests;
- docking/resizing/tab changes do not recreate uPlot;
- hidden tools do not continue expensive polling/rendering;
- browser memory remains stable while repeatedly opening/closing chart windows.
- warm sandbox calculations are responsive enough for interactive columns/scans;
- long studies remain cancellable and do not degrade API responsiveness.

Final validation:
- backend unit and integration suites;
- frontend unit/component suites;
- TypeScript check;
- production build;
- Playwright;
- sandbox security and resource-limit suites;
- deterministic provider tests and configured opt-in live probes;
- visual-regression suite;
- browser console inspection;
- backend log inspection;
- YAML/JSON parsing;
- migration upgrade/downgrade verification;
- `git diff --check`.

#### Locked assumptions

- Reference interface: TC2000 Version 25 desktop, pinned to build `25.0.9571`.
- Fidelity: pixel-close geometry and interaction, rebranded with original assets.
- Runtime: desktop browser with browser pop-outs, not Electron/Tauri and not mobile.
- Market updates: current polling, not streaming.
- Programming language: one Python-native market-analysis language and SDK; no separate
  executable PCF or Optuma language.
- Python dependencies: curated built-in library set only; no user/runtime package installs.
- Study output: structured native results only; no arbitrary HTML/CSS/JavaScript.
- Study Lab: a primary-workstation tool distinct from legacy Strategy Lab.
- Data providers: API-first, multi-source, reconciled, free-source-first, and never
  provider-specific in the frontend.
- yfinance: absent from default/new-workstation paths and retained only as an explicit
  temporary legacy fallback until audited away.
- Security master: canonical local records reconciled from multiple APIs; exchange
  directory files are optional evidence only.
- Market truth: provider/feed/freshness/coverage are always visible; consolidated
  real-time data is not promised.
- Legacy dashboards: retained only in the legacy frontend and not migrated.
- Extra current platform tools: hidden outside the core clone rather than removed.
- External unsupported domains: hidden, stubbed, and documented.
- Delivery model: one continuous full implementation stint followed by user-led
  fine-tuning and bug fixing, with no MVP or phase boundary treated as completion.

Why this is planned:
- The current frontend exposes powerful backend capabilities as separate routes and dense,
  unrelated surfaces rather than as one coherent analysis workstation.
- The backend already provides the reusable instrument, OHLCV, indicator, drawing, alert,
  screener, synthetic-expression, basket, and ETF-holdings foundations.
- Rebuilding the primary interaction model around TC2000-style linked workspaces makes the
  requested top-down daily market analysis fast while retaining uPlot's performance.

## Notes

- This file intentionally focuses on postponed work that already came up in discussion.
- It is not meant to replace issue tracking if we later decide to formalize roadmap management elsewhere.
- This is the only file that should be treated as the canonical TODO memory for deferred work in this repo.
### 2026-08-08 implementation evidence — complete current acceptance refresh

- The clean authenticated Playwright matrix passes `55/55` with 24 visual projects intentionally
  separated into the board-guided command; the previous unusable `Invalid URL` artifact is not
  treated as product evidence.
- `npm run test:visual:board` validates the manifest and passes all `24/24` four-environment
  board-guided visual cases, including shell, Study Lab, loading, blocked-popout, stale, and
  partial-coverage baselines. This is the accepted board-guided track, not exact-build approval
  for the explicitly unrepresented states.
- `make test-backend-coverage` passes `1,277/1,277` at `79.43%` coverage with 86 known
  third-party deprecation warnings. Full frontend Vitest passes `596/596`; type-check,
  production build, and `git diff --check` pass.
- Acceptance flexibility used: deterministic local market fixtures and the 190-image composite
  reference board. Live-provider, physical multi-monitor, beyond-bounded-endurance, and named
  visual-reference gap records remain open and actionable.

### 2026-08-06 implementation evidence — transfer mechanics

- F8u/F8v now exercise chart-plot → watchlist numeric-column and technical-condition → Boolean-column
  drag/drop in the real rebuilt browser stack (`2/2`).
- Fixed the discovered chart comparison/plot-library overlap, condition-library `MissingGreenlet`
  response serialization, and idempotent screener reuse. Remaining visual-reference gaps are not
  treated as closed by these functional checks.

### 2026-08-08 continuation — unified Python condition scan/alert and deterministic visual oracle

- Added F9h browser coverage for creating a unified Python condition, selecting it in EasyScan,
  running the scan, and promoting the saved result to an alert.
- Fixed the real async SQLAlchemy `MissingGreenlet` HTTP 500 discovered by F9h: screener and
  Strategy Lab research-run queries now eager-load `ResearchRun.artifacts` before artifact
  collection. Combined targeted integration assertions pass `43/43`; isolated coverage-gate
  failures are threshold accounting, not failed assertions. Rebuilt F9h and the affected F8q/F8w
  slice pass `1/1` and `3/3` respectively.
- Stabilized the Study Lab validation-error visual oracle with a deterministic pending-OHLCV
  fixture. The complete board-guided manifest/visual run passes `32/32`; no broad mask or baseline
  refresh was used.
- Full authenticated E2E currently has `61` passes and one localized F8u miss in `62` executed
  tests; focused repetitions show `3/5` followed by a fresh isolated `1/1`. The explicit goal
  tie-break keeps F8u as a named reproducibility gap with evidence and regression coverage while
  independent work continues; it is not silently waived or promoted to a goal-wide blocker.

### 2026-08-09 continuation — Study Lab series reuse and chart-menu containment

- Added F9i for Study Lab numeric-series output → immutable chart-plot asset → chart plot library
  reuse. The chart library now displays Python plots as first-class entries and supports removing
  them through the serializable `python_plots` configuration.
- Fixed two real browser defects exposed by F9i: explicit activation of the top-level and inner
  Study Lab tabs after persisted-layout hydration, and chart plot menu anchoring/stacking so a
  narrow chart cannot place its fixed menu over a neighboring watchlist. Rebuilt-stack F9i passed
  `1/1`; ChartPlotLibrary unit coverage passed `9/9`; full frontend Vitest passed `602/602` and
  type-check passed.
- Full authenticated E2E executed `63` tests with `61` passing; F8u and F8y were the only misses.
  F8u passed five fresh repetitions and remains a transient drag oracle to monitor. F8y remains a
  localized personal-watchlist activation/state gap under the mandatory goal tie-break. Neither
  blocks independent work, and neither is silently waived.

### 2026-08-06 implementation evidence — concurrent chart persistence

The per-user instrument-indicator endpoint now handles simultaneous writes from linked or floated
charts by recovering from the unique-row conflict and updating the canonical row. This closes a
real backend error observed during the complete browser audit; integration and focused browser
regressions are recorded in the operational handoff.
#### Recent acceptance closure: EasyScan to Market Gauge

- Shared Vue Query saved-scan state is invalidated and refetched after EasyScan creation/reuse,
  preventing an already-mounted Market Gauge from presenting a stale scan list.
- Real-user acceptance: authenticated F8w creates/runs a uniquely named scan, refreshes the mounted
  Gauge, and verifies its match reading (`1/1`); focused EasyScan unit coverage is `8/8`.
- No visual/reference flexibility was used for this closure. Exact-build and unrepresented V25
  visual states, live-provider probes, physical multi-monitor validation, and indefinite soak remain
  separately tracked gaps.
## Current continuation checkpoint — 2026-08-06T22:35:00Z

Closed a concrete workstation interaction defect: Add Tool persisted new windows but did not
activate the corresponding Golden Layout tab. The host now resolves `active_window_key` to the
component's containing stack after installation and on restored-key changes. Workspace host unit
coverage passes `4/4`, authenticated Chromium F8x passes `1/1`, the complete frontend suite passes
`594/594`, and type-check/build/diff validation pass. No visual acceptance flexibility was used;
the board-guided track and all documented unrepresented-state gaps remain unchanged.
## Current continuation checkpoint — 2026-08-06T22:50:00Z

Closed the active-tab persistence gap exposed while fixing Add Tool activation. Golden Layout now
publishes active component changes; the workspace store validates the key, updates
`active_window_key`, and schedules the revisioned snapshot. Host tests pass `5/5`, workspace-store
tests cover unknown and repeated keys, authenticated F8x passes `1/1`, and the full frontend suite
passes `596/596`. No visual flexibility was used. The requested volume-inclusive Docker cleanup
was safety-rejected as host-wide destructive; read-only `docker system df` evidence was recorded
instead.
### 2026-08-06 implementation evidence — Add Tool stack audit

The workspace store now keeps newly opened tools in Golden Layout stacks instead of creating
10px-wide root columns and prevents stale in-flight snapshot `409` recovery from restoring over a
newer Add Tool mutation; store coverage is 40/40 and the full frontend suite is 598/598. The real
authenticated F8v/F8y/F11 flows now pass after explicitly activating newly added tabs instead of
relying on hidden DOM order. Personal-list copy/move browser coverage remains explicitly open; no
forced browser action or visual acceptance flexibility was used.

### 2026-08-06 final browser/visual gate refresh

The rebuilt-stack serialized authenticated Chromium matrix passes `56/56` executed tests; the
separate board-guided visual matrix passes `24/24` across all four required environments. Recent
logs contain only expected provider-exhaustion freshness warnings and no HTTP 500, traceback,
`MissingGreenlet`, or `UniqueViolation`. Exact/unrepresented V25 states, opt-in live-provider
probes, physical multi-monitor validation, endurance beyond bounded stress, and personal-list
copy/move browser coverage remain tracked gaps.

## Current continuation checkpoint — 2026-08-08T00:28:00Z

Closed the personal-watchlist membership race exposed by the real Add Tool browser path. Duplicate
name creates are now idempotent, locally-created rows survive lagging cross-window reloads, stale
workspace snapshot echoes cannot revert local selection, and virtualized-row refreshes no longer
prevent the context-menu copy/move pointer action. Focused watchlist store coverage is `12/12`, the
full frontend suite is `600/600`, type-check/build/diff pass, and rebuilt-stack authenticated F8y
passes `1/1` with successful copy and move requests. No visual acceptance flexibility was used.
The composite board remains the working visual authority; its six documented visual/reference gaps,
provider/live, native multi-monitor, sustained-stress, and remaining product-scope gaps remain open.

The final rebuilt-stack authenticated Chromium flow matrix then passed `53/53`; the earlier
`52/53` result is superseded because its sole F8y failure preceded the membership-race fix.

## Current continuation checkpoint — 2026-08-08T23:00:00Z

Added F9g coverage for the unified-Python reuse contract: a scalar Study Lab result can be saved
as an immutable watchlist-column asset and attached through the real `US Top Down` Columns editor.
Focused F9g passed; the complete authenticated Playwright matrix passed `61/61` executed tests
with 32 visual projects skipped, while the board-guided visual matrix remains independently green
at `32/32`. Full frontend Vitest passed `601/601`, `vue-tsc --noEmit`, and repository metadata
checks passed. No acceptance flexibility was used. Remaining gaps are unchanged: live-provider
evidence, native physical multi-monitor behavior, endurance beyond bounded stress, and explicitly
unrepresented/ambiguous V25 visual states.
2026-08-09: Watchlist mutation reconciliation added local-delta preservation, concurrent-create
deduplication, duplicate-item idempotency, and immutable membership updates. Store suite 14/14 and
type-check pass. Rebuilt F8y no longer loses XLE after Add, but a later copy/move interaction
timeout remains tracked as a localized tie-break gap; no acceptance flexibility used.
2026-08-09: F8y watchlist mutation/copy/move gap closed after the store/API reconciliation work. Diagnostic evidence observed source create, XLE add, copy POST, move POST, and source DELETE; rebuilt F8y passed 1/1 and 3/3 repetitions. No acceptance flexibility used.

## Current continuation checkpoint — 2026-08-10T00:10:00Z

The condition-column persistence and transient-refresh hardening now pass the complete local
acceptance set: frontend Vitest `610/610`, authenticated Chromium `63/63`, and board-guided visual
`32/32` across the four required environments. The complete backend unit/integration gate passes
`1,277/1,277` at `79.43%` coverage. Live sandbox/resource probes, runner-only orphan recovery,
and five sustained cancellation/success rounds also pass without stale sentinels or restart.

The remaining completion gaps are unchanged and explicit: unrepresented or ambiguous exact-build
V25 states, opt-in live-provider evidence, native physical multi-monitor placement, and endurance
beyond the bounded stress budget. The bounded stress substitution is recorded in the governance
and operations ledgers; no acceptance criterion or visual mask was relaxed. Docker storage was
measured at approximately 10.3 GB, but the requested broad prune was rejected by safety policy and
no destructive workaround was used.

## Current continuation checkpoint — 2026-08-10T00:48:00Z

Applied the fix-first tie-break rule to a real F8v regression found by an elevated browser rerun:
condition-column creation now registers the condition key in customized watchlists' visible-column
allow-list, so a successful drag cannot remain hidden. Focused F8v/F8y passed `2/2`; the full
frontend unit suite remains `610/610`, and the VirtualWatchlistTool slice passed `47/47` with
type-check green. A subsequent full Chromium run exposed one intermittent F8u plot-column miss
(`62/63`); the durable follow-up adds optimistic indicator-column reconciliation through the
workspace acknowledgement window. Focused F8u/F8v then passed `2/2`. No acceptance criterion or
visual mask was relaxed. The F8u intermittent result is retained as localized tie-break evidence
until another full matrix confirms closure; broader visual/reference, live-provider, native
multi-monitor, and indefinite-soak gaps remain unchanged.

The next top-down acceptance advance closed two real implementation defects. The dedicated
`ratio-chart` renderer was previously shadowed by the generic single-expression branch, so a
constituent could show only `NVDA/XLK`; branch ordering now preserves the multi-benchmark renderer,
and F8e explicitly verifies both `NVDA/XLK` (or the selected sector/proxy) and `NVDA/SPY`. The
chart-drop intermittency was traced to virtualized row buttons stopping the section drop event;
row drops now bubble while reorder logic remains guarded, with `dragenter` and `dropEffect=copy`
hardening. Focused F8e passed `1/1`, F8u/F8v/F8y passed `3/3`, repeated F8u passed `5/5`, full
authenticated Chromium passed `63/63`, frontend Vitest `610/610`, type-check passed, and the
board-guided visual matrix passed `32/32`. No acceptance criterion or visual mask was relaxed.

The closure rerun completed successfully: the full authenticated Chromium matrix passed `63/63`
after the indicator-column reconciliation, including F8u, F8v, and F8y. The previously observed
F8u miss is therefore closed with focused and complete-matrix evidence.

## 2026-08-10T18:30:00Z — Research Results shared mutation reconciliation

Rerun and cancel responses in Persisted Research Results now reassert their authoritative state
into the shared Vue Query `['workstation', 'research-runs']` cache after list reconciliation.
This closes a linked/pop-out stale-status race. Focused Research Results coverage passed `6/6`,
including two mounted roots sharing one cache; full frontend Vitest passed `629/629`, type-check
and production build passed. No acceptance flexibility, visual mask, or documented gap changed.

## 2026-08-10T19:00:00Z — Study Lab shared mutation reconciliation

Study Lab rerun/cancel controls now publish authoritative responses through the shared per-run
Vue Query cache used by persisted hydration and chart Python plots. Focused Study Lab and Research
Results tests pass `23/23`; full frontend remains `629/629`, with type-check and production build
passing. No acceptance flexibility, visual mask, or documented gap changed.

## 2026-08-10T19:30:00Z — Study Lab cross-root mutation regression

Added a two-root regression proving that canceling a durable Study Lab run propagates through the
shared per-run cache. Focused Study Lab/Research Results coverage passes `24/24`; full frontend
Vitest passes `630/630`, type-check and production build pass. No acceptance flexibility, visual
mask, or documented gap changed.

## 2026-08-10T20:30:00Z — Research Results payload and Study Lab entry-path hardening

Persisted Research Results list responses are now compact by default (`include_artifacts=false`)
and hydrate selected-run artifacts on demand; the rebuilt authenticated response measured 6,104
bytes versus approximately 2.7–3.3 MB previously. The global Study action now activates the
persisted Study Lab tab or mounts a Study Lab tool when a customized workspace has no such window.
Focused backend coverage passed `1/1`; ordered rebuilt-stack F8g/F9i passed `2/2`; full frontend
Vitest passed `630/630`, with type-check and production build passing. Acceptance flexibility used:
none. Exact-build/unrepresented visual states, opt-in live-provider evidence, physical
multi-monitor placement, and indefinite soak remain explicitly tracked.

## 2026-08-10T22:00:00Z — Complete browser matrix after hardening

The rebuilt branch-scoped stack passed the complete authenticated Chromium matrix `63/63` after
the Research Results compact list/detail and customized-workspace Study action repairs. This
includes top-down drilldown, Study Lab, link groups, pop-outs, legacy routes, uPlot performance,
and workstation churn. A strict backend/worker/research-runner log audit found no `ERROR`,
traceback, HTTP 500, `MissingGreenlet`, `UniqueViolation`, critical, or fatal signatures.
Acceptance flexibility used: none. Exact-build/unrepresented visual, live-provider,
physical multi-monitor, and indefinite-soak gaps remain explicit.

## 2026-08-10T23:00:00Z — Board-guided visual matrix after hardening

Manifest validation and the four-environment board-guided visual matrix passed `32/32` after the
Research Results and Study Lab changes. Shell, Study Lab, loading/error/freshness/partial, and
blocked-pop-out interim baselines remained deterministic at all required display environments.
No screenshot, mask, or acceptance criterion changed; exact-build/unrepresented states remain
explicit manifest gaps.

## 2026-08-11T00:00:00Z — Backend coverage confirmation after hardening

The complete backend unit/integration coverage gate passed `1,277/1,277` in 248.55 seconds at
`79.43%`, above the required 75% threshold. Only 86 known Nautilus/pandas dependency warnings
were emitted; no backend criterion was relaxed.

## 2026-08-11T00:30:00Z — Research Results detail hydration state

Selected compact Results rows now show an explicit detail-loading state while full artifacts
hydrate, eliminating a transient false-empty result. Focused Results coverage passed `7/7`, full
frontend Vitest `631/631`, type-check/build passed, and rebuilt F8g/F9i passed `2/2`. No acceptance
flexibility was used.

## 2026-08-11 — Durable security-master ambiguity reconciliation

SEC discovery ambiguity is now a durable, authenticated workflow rather than an opaque raw
snapshot alone. Distinct CIK/name identities sharing a ticker are persisted as idempotent
`InstrumentReconciliationIssue` rows; canonical seeding still refuses promotion, while same-issuer
multi-venue rows remain valid. Authenticated provider diagnostics can list open/resolved/ignored
issues and record an explicit resolution without rerunning discovery. Focused queue/provider/
persistence/router coverage passes `99/99`; changed-file Ruff and compilation pass; the complete
backend unit/integration gate passes `1,362/1,362` at `79.61%` (75% required, 86 known dependency
warnings). Acceptance flexibility used: **none**. Remaining gaps are review/admin workflow
governance, SEC live-access 403, ETF/fund and historical-listing completeness, and the broader
TC2000 visual/provider/final-audit work; none blocks independent workstation implementation.

## 2026-08-11 — Seeded board-guided visual acceptance and workstation revalidation

The disposable seeded Compose stack was rebuilt on alternate host ports so it could coexist with
the canonical populated stack. The four required board-guided display environments passed
`104/104` (`1920x1080` and `2560x1440`, each at 100% and 125% display scale) against the 230-source
composite reference board. The first attempt used the canonical non-seeded stack and was correctly
rejected by the fixture-mode guard; that is recorded as an environment misrun, not visual evidence.
The host-permitted browser run is the authoritative seeded result. No visual threshold, mask, or
acceptance criterion was relaxed. The exact-build/unrepresented reference states, live-provider
promotion, native multi-monitor placement, and beyond-bounded-endurance remain explicit gaps.

## 2026-08-11 — Worker seed-isolation configuration repair

The Compose worker now inherits `E2E_SEED_INSTRUMENTS`, `E2E_SEED_MARKET_DATA`,
`CORE_WORKSTATION_BOOTSTRAP_ENABLED`, and its timeout from the same deployment configuration as
the backend. This prevents a seeded visual stack from silently running provider-backed workstation
hydration in the background. The deployment contract passes `9/9`; resolved Compose inspection and
the recreated disposable worker confirm the flags at runtime. The host-permitted complete backend
gate passes `1,367/1,367` at `79.62%` with 86 known dependency warnings. No acceptance flexibility
was used; this closes a repository-controlled isolation gap.

The corrected worker was also followed by a four-environment default-workstation visual smoke
(`4/4`) and the full frontend suite (`682/682`). These are post-repair confirmations; no visual
baseline or mask changed.

The canonical non-seeded worker was then recreated with explicit `false` seed flags. The complete
top-down acceptance slice passed `10/10` (SPX proxy, SPY/RSP, canonical holdings, all-sector
industry surfaces, ratio editing, deep proxy/constituent traversal, and horizontal scrolling).
Provider-backed Nasdaq history requests returned successfully; expected stock-holdings 404s stayed
labelled unavailable paths. This confirms the worker fix does not regress real canonical hydration.
### 2026-08-10 uPlot-only shared and heat-map sparklines

- [x] Audited the remaining numerical SVG paths after the Strategy Lab renderer conversion. The
  shared `Sparkline.vue` and legacy dashboard heat-map tile sparklines were still emitting
  polyline geometry outside uPlot.
- [x] Replaced both paths with a reusable uPlot-backed fixed-size host. Materialized tile series
  are passed directly without per-tile API fetches; watchlist sparklines retain their existing
  cache/timeframe behavior, empty/loading states, color semantics, and teardown.
- [x] Added focused component coverage for uPlot construction, materialized-series rendering,
  empty state, SVG absence, API suppression, and destroy lifecycle (`5/5` including the existing
  composable tests). The full frontend suite passes `678/678`; type-check and the 468-module
  production build pass. The numerical-SVG audit now finds only icon geometry.
- [x] The targeted authenticated dashboard browser regression (`F15`) passes `1/1` against the
  healthy branch services. `git diff --check` passes. Acceptance flexibility used: **None**. This closes the
  repository-controlled renderer-contract gap; exact-build/unrepresented visual, provider/
  entitlement/taxonomy, physical-monitor, beyond-bounded-endurance, and final-audit gaps remain
  explicitly open.

### 2026-08-11 canonical instrument identity in workstation links

- [x] Propagate canonical instrument IDs from top-down rows, proxy/industry rows, breadth and
  relative-rotation selections into `selectToolSymbol`, shell publication, shared link events,
  persisted tool configuration, Grey isolation, pop-outs, and ratio launches.
- [x] Remove stale persisted IDs on ticker-only navigation and hydrate IDs from saved workspace
  configuration so identity survives reload without relying on ticker text.
- [x] Focused identity/link coverage passes `68/68`; full frontend Vitest passes `683/683` across
  92 files; `vue-tsc`, the 468-module production build, uPlot contract (`42` files), and
  `git diff --check` pass.
- [x] Rebuilt authenticated top-down rerun passes `5/5`; the isolated ratio-editor rerun passes
  `1/1`. The earlier restarted-stack 502/login timeout was setup-only and is retained as
  environment evidence, not product acceptance.
- [ ] Continue tracking exact-build/unrepresented visual references, live provider/entitlement
  breadth, native multi-monitor placement, beyond-bounded endurance, and final audit. Acceptance
  flexibility used: **none**; no criterion, baseline, or mask was relaxed.

### 2026-08-11 synthetic report identity handoff

- [x] Synthetic-expression constituent chips in the instrument report now emit canonical
  constituent IDs alongside ticker aliases, and the workstation report tool forwards them through
  the normal selection/link path.
- [x] Focused report/link/workspace coverage passes `66/66`; `vue-tsc --noEmit` passes.
- [ ] Exact-build/unrepresented visual references, provider breadth/entitlements, native
  multi-monitor placement, beyond-bounded endurance, and final audit remain explicit. Acceptance
  flexibility used: **none**.

### 2026-08-11 canonical search identity contract

- [x] Add `instrument_id` to canonical local search results and pass it through workstation
  autocomplete, Enter/Go, and linked-symbol publication without weakening legacy symbol-only
  search consumers.
- [x] Backend canonical-boundary integration passes `2/2`; focused frontend search/workstation
  tests pass `66/66`; full frontend Vitest passes `685/685`; type-check/build, uPlot contract
  (`42` files), and `git diff --check` pass.
- [x] Rebuilt dev-proxy authenticated F7 and F8d flows pass `1/1` each. The initial backend
  Docker-socket permission failure was setup-only and superseded by the permitted run.
- [ ] Continue the explicit visual-reference, provider/entitlement, native-monitor, endurance,
  and final-audit gaps. Acceptance flexibility used: **none**.

### 2026-08-12 primary workspace tab keyboard navigation

- [x] Make the visible layout strip a semantic tablist. Each layout tab now exposes selected
  state and a roving `tabindex`; ArrowLeft/ArrowRight/ArrowUp/ArrowDown traverse with wraparound,
  Home/End move focus to the first/last layout, and Enter/Space activate the focused layout.
  Existing pointer/mouse drag ordering and workspace snapshot persistence are unchanged.
- [x] Apply the fix-first tie-break to the first test-oracle defect: a detached Vue Test Utils
  mount cannot move `document.activeElement` away from `body`. Focus lookup now scopes to the
  event's owning tablist and the regression is mounted on `document.body`, making the browser and
  unit oracles agree without weakening the product behavior.
- [x] Focused mounted-view coverage passes `17/17`; full frontend Vitest passes `699/699`;
  type-check, production build, and `git diff --check` pass; the rebuilt authenticated Chromium
  keyboard flow passes `1/1` with clean browser diagnostics.
- [ ] Continue the remaining exact-build/unrepresented visual states, broader provider and live
  entitlement evidence, native physical-monitor placement, beyond-bounded endurance, and final
  requirement audit. Acceptance flexibility used: **board-guided represented tab/layout state
  plus controlled seeded browser evidence**; those visual/external gaps remain explicitly tracked.

### 2026-08-12 tool-window menu keyboard navigation

- [x] Make the dense tool-window menu keyboard-operable. Enter/Space/ArrowDown/ArrowUp on the
  trigger opens it; menu items support roving focus, Arrow navigation with wraparound, Home/End,
  Enter/Space activation, Escape dismissal, and focus recovery to the trigger. Existing pointer
  dismissal and click action contracts remain unchanged.
- [x] Apply the fix-first tie-break to the first browser run: the test reached a stale frontend
  image that lacked the new trigger handler. The branch frontend was rebuilt and the same browser
  flow passed, so the stale run is retained as environment evidence rather than product evidence.
- [x] Focused ToolWindow coverage passes `5/5`; full frontend Vitest passes `700/700`; type-check,
  production build, and `git diff --check` pass; rebuilt authenticated Chromium passes `1/1` with
  clean browser diagnostics.
- [ ] Continue exact-build/unrepresented menu visual evidence, broader provider/live-entitlement
  coverage, native physical-monitor placement, beyond-bounded endurance, and final audit.
  Acceptance flexibility used: **board-guided represented tool-window/menu state plus controlled
  seeded browser evidence**; the visual gap remains explicitly tracked.

### 2026-08-12 watchlist context-menu keyboard navigation

- [x] Make row context actions keyboard-operable. Opening a row menu focuses the first enabled
  action; Arrow keys wrap through actions, Home/End jump to boundaries, Enter/Space activate,
  Escape dismisses, and focus returns to the originating row. Existing right-click, chart,
  compare, ratio, note, alert, copy, list-transfer, flag, and remove actions remain intact.
- [x] Focused VirtualWatchlistTool coverage passes `59/59`; full frontend Vitest passes `701/701`;
  type-check, production build, and `git diff --check` pass; rebuilt authenticated Chromium
  passes `1/1` with clean browser diagnostics.
- [ ] Continue exact-build/unrepresented context-menu visual evidence, broader provider/live-
  entitlement coverage, native physical-monitor placement, beyond-bounded endurance, and final
  audit. Acceptance flexibility used: **board-guided represented watchlist/context-menu state
  plus controlled seeded browser evidence**; the visual gap remains explicitly tracked.

### 2026-08-11 EasyScan history plot closure

- [x] Expose retained EasyScan result history as canonical count and percentage numeric series with
  chronological points, coverage, freshness, and an explicit empty-history warning. The endpoint
  never reruns a scan or fabricates historical values.
- [x] Add the history assets to the workstation Chart Plot Library and existing uPlot numeric-series
  lifecycle: discover saved scans, add, persist, hide/show, reorder, duplicate, recolour, remove,
  and copy to linked/selected chart targets.
- [x] Focused backend integration passes `25/25`; backend Ruff passes; frontend component coverage
  includes the new lifecycle; focused browser F9j passes `1/1`; full frontend Vitest passes `696/696`,
  type-check/build pass, complete Chromium passes `94/94`, and the seeded board-guided visual matrix
  passes `104/104` across all required display environments.
- [x] Apply the tie-break rule: the first browser launch failure was Chromium host-sandbox setup,
  not product behavior; the permitted rerun passed. No implementation, visual threshold, mask, or
  baseline was relaxed.
- [ ] Continue the separately tracked exact-build/permission and unrepresented visual states,
  broader provider/live-entitlement coverage, native physical-monitor placement, beyond-bounded
  endurance, and final requirement audit.

### 2026-08-11 current-source board visual matrix

- [x] Validate the current seeded build against the complete four-environment board-guided matrix:
  `104/104` at 1920×1080 and 2560×1440, both 100% and 125% display scale.
- [x] Manifest validation passed before execution; shell, menus, factory layouts, docking/floating,
  watchlists/editors, Study Lab, chart/error/freshness, and blocked-popout states remain green.
- [x] No baseline, mask, threshold, or visual acceptance criterion changed. This closes no exact-
  build/unrepresented gap; those remain explicitly tracked in the manifest and reference board.

### 2026-08-11 current-head backend acceptance gate

- [x] Combined backend unit/integration coverage passes `1368/1368` with total coverage `79.62%`
  against the required `75%` minimum.
- [x] The gate covers canonical identity/reconciliation, provider governance, ETF holdings/taxonomy,
  freshness, Python/research execution, Study Lab, workspaces, watchlists, scans, and legacy APIs.
- [x] Only the known dependency deprecation-warning set was emitted; no backend failure or new
  runtime error class appeared.
- [ ] Continue live-provider entitlement breadth, exact/unrepresented visual states, native
  physical-monitor validation, beyond-bounded endurance, and final requirement audit.

### 2026-08-11 Python plot-library workstation parity

- [x] Treat Python numeric-series plots as first-class chart-library assets: hide/show, reorder,
  duplicate, recolour, remove, drag, copy to linked charts, and copy to a selected chart or
  watchlist target.
- [x] Dropping a Python plot onto a watchlist creates a reusable `python_columns` entry; hidden
  plots are excluded from research execution while remaining persisted in the chart definition.
- [x] Focused component/library coverage passed `17/17`; focused browser coverage passed `1/1`;
  adjacent Study Lab/Python browser acceptance passed `3/3` on the deterministic seeded branch
  stack; full frontend Vitest passed `694/694`, type-check/build, uPlot contract (`42` files),
  and `git diff --check` passed.
- [x] Fix-first browser test corrections were limited to selecting the required `US Top Down`
  factory layout, using the persisted `Benchmarks` target label, and matching its versioned plot
  name; no product acceptance criterion, visual mask, threshold, or baseline was relaxed.
- [ ] Continue exact-build/unrepresented visual states, broader provider/live-entitlement
  evidence, native physical-monitor placement, beyond-bounded endurance, and the final audit.

### 2026-08-11 canonical current-head workstation gate

- [x] Rebuilt the canonical non-seeded Compose stack from current source after identifying that
  the earlier browser container predated the Python plot changes.
- [x] Complete authenticated Chromium matrix passes `93/93` in 5.0 minutes; focused ratio slice
  passes `2/2`; frontend Vitest passes `694/694` across 93 files; type-check/build, uPlot audit
  (`42` files), and `git diff --check` pass.
- [x] Fix-first corrections make the new Python plot browser fixture dynamic/idempotent and make
  ratio acceptance target the visible active ratio window rather than a stale hidden Golden Layout
  root. The authoritative rerun is green; no visual criterion, mask, threshold, or baseline was
  relaxed.
- [ ] Continue exact-build/unrepresented visual states, broader provider/live-entitlement evidence,
  native physical-monitor placement, beyond-bounded endurance, and final requirement audit.

The current source subsequently passed the board-guided visual matrix `104/104` across all four
required display environments. Acceptance flexibility used: **board evidence plus deterministic
seeded fixture**; exact-build/unrepresented visual gaps remain explicitly open.

The current-source workstation performance suite passes `2/2` for multi-chart recovery and
repeated multi-window churn. This is bounded-stress evidence; indefinite/long-duration endurance
remains open. Acceptance flexibility used: **bounded stress in place of indefinite soak**.

### 2026-08-11 combo-list workstation parity closure

- [x] Close the repository-controlled combo-list browser/interaction gap: personal watchlists can
  be created, populated, selected, composed through union/intersection/exclusion, persisted as a
  reusable combo list, selected as the active WatchList view, and deleted again without a route
  change.
- [x] Apply the fix-first tie-break to the actual Golden Layout state defects found during the
  browser path: stale virtual roots could replay an older list selection, mutation completion was
  not observable, and the combo editor was clipped in the dense tool chrome. The repair fences the
  latest explicit selection, exposes `aria-busy`, wraps the editor into a bounded second row, and
  clears the personal-list fence when a combo becomes active.
- [x] Correct the browser oracle to use the semantic `listbox` role for native multi-selects and
  assert the intended result: A+B contains SPY and XLK, then excluding the XLK list leaves one
  visible SPY row. This was an acceptance-oracle correction, not a product criterion relaxation.
- [x] Focused combo and adjacent personal-watchlist browser checks pass `2/2`; frontend Vitest
  passes `696/696`; the rebuilt production frontend passes; complete authenticated Chromium passes
  `95/95`; and the rebuilt seeded board-guided visual matrix passes `104/104` across all four
  display environments.
- [ ] Continue exact-build/permission and unrepresented visual states, broader provider and live
  entitlement evidence, physical-monitor placement, beyond-bounded endurance, and final audit.
  Acceptance flexibility used: **none for combo functionality**; the visual result continues to use
  the documented composite board plus deterministic seeded fixture, so those visual evidence gaps
  remain open and tracked.

### 2026-08-11 typed symbol-search keyboard acceptance

- [x] Add a real-user regression for the shell contract that typing outside an editor focuses the
  active-symbol search, publishes the typed query, renders canonical results, and lets Escape close
  the result list while retaining editor focus.
- [x] The focused keyboard slice passes `5/5`; the complete authenticated Chromium matrix passes
  `96/96`, including linking, Space/Shift+Space, Ctrl+wheel, help-menu editor suppression, and the
  new typed-search path. No product criterion, visual baseline, mask, or threshold changed.
- [ ] Continue exact-build/unrepresented visual states, broader provider/live-entitlement evidence,
  physical-monitor placement, beyond-bounded endurance, and final audit. Acceptance flexibility used:
  **none**.

### 2026-08-11 configurable Study Lab breakout lookback

- [x] Close the Study Lab gap for configurable-period new-high/new-low studies. The factory source
  now consumes unified Python `parameters`, exposes a bounded integer control (default 20, minimum 2,
  maximum 252), and carries the selected lookback into event labels and forward-return outputs.
- [x] Align the API and isolated-runner validators so `parameters` is an approved read-only run
  namespace. The repair is covered by the validator unit suite and rebuilt backend/runner/worker.
- [x] Focused Study Lab unit coverage passes `20/20`; focused browser coverage passes `1/1`; full
  frontend Vitest passes `697/697` across 93 files; type-check/build pass; uPlot contract audit passes
  for 42 primary files; complete authenticated Chromium passes `97/97` in 5.3 minutes.
- [x] Re-ran the four-environment board-guided visual matrix after this visible control change:
  `104/104` passed in 5.4 minutes. Continue exact-build/unrepresented visual, provider/live-entitlement,
  physical-monitor, beyond-bounded-endurance, and final-audit gaps. Acceptance flexibility used:
  **none** for behavior; board-plus-seeded-fixture remains represented-state visual evidence only.

Post-change backend unit coverage passes `1,073/1,073` with 34 known dependency deprecation
warnings; no new backend failure class was introduced.
The combined backend unit/integration coverage gate subsequently passes `1,367/1,367` at
`79.62%` with 86 known dependency warnings; no backend acceptance regression was found.
The current source also passes the focused authenticated top-down browser slice `3/3` (`F8d`,
`F8e.1`, and `F8e.2`) against the running branch backend.

### 2026-08-11 logout request-boundary regression

- [x] Capture the API token synchronously before request preparation can yield across logout;
  avoid unauthenticated drawing hydration and suppress only the expected in-flight auth race.
- [x] API/drawing focused coverage passes `15/15`; full frontend Vitest passes `689/689`;
  type-check/build, uPlot contract (`42` files), and `git diff --check` pass.
- [x] The repaired complete authenticated browser matrix passes `87/87` with no unexpected
  diagnostics. The first `86/87` run and its F5 failure are retained as root-cause evidence.
- [ ] Continue the explicit visual-reference, provider/entitlement, native-monitor, endurance,
  and final-audit gaps. Acceptance flexibility used: **none**.

### 2026-08-11 direct industry-proxy identity handoff

- [x] Resolve a canonical instrument ID for direct industry-proxy actions when the originating
  row does not provide one; explicit row IDs still take precedence.
- [x] Focused pop-out/link coverage passes `16/16`; full frontend Vitest passes `686/686`;
  type-check/build, uPlot contract (`42` files), `git diff --check`, and ops/visual parsing pass.
- [ ] Continue the explicit visual-reference, provider/entitlement, native-monitor, endurance,
  and final-audit gaps. Acceptance flexibility used: **none**.

### 2026-08-12 chart template keyboard navigation

- [x] Make the chart-template control keyboard-operable. Enter/Space/ArrowDown opens it,
  explicit menu semantics are exposed, the template-name editor receives initial focus, and
  Escape closes the menu and restores trigger focus. Existing save/apply/import/export/reset and
  symbol-preservation behavior remains unchanged.
- [x] Focused ChartTemplateControl coverage passes `4/4`; full frontend Vitest passes `702/702`;
  type-check, production build, and `git diff --check` pass; rebuilt authenticated Chromium
  passes `1/1` with clean browser diagnostics.
- [ ] Continue exact-build/unrepresented template visual evidence, broader provider/live-
  entitlement coverage, native physical-monitor placement, beyond-bounded endurance, and final
  audit. Acceptance flexibility used: **board-guided represented chart/template state plus
  controlled seeded browser evidence**; the visual gap remains explicitly tracked.
### 2026-08-12 chart plot library keyboard navigation

- [x] Make the chart plot library keyboard-operable: semantic menu state, Enter/Space/arrow
  opening, first-control focus, Escape dismissal, and trigger-focus recovery.
- [x] Preserve existing indicator, Python plot, retained EasyScan plot, copy, drag, and promotion
  behavior. Focused component coverage passes `15/15`; type-check/build, `git diff --check`, and
  rebuilt authenticated Chromium coverage pass `1/1` with clean diagnostics.
- [ ] Continue exact-build/unrepresented plot-library visual evidence, broader provider/live-
  entitlement coverage, native physical-monitor placement, beyond-bounded endurance, and final
  audit. Acceptance flexibility used: **board-guided represented chart/plot-library state plus
  controlled seeded browser evidence**; the visual gap remains explicitly tracked.
### 2026-08-12 workstation shell menu keyboard navigation

- [x] Make Workspace, Add tool, Help, and Recent symbols menus keyboard-operable with semantic
  menu items, Enter/Space/Arrow opening, Arrow/Home/End navigation, Escape dismissal, and trigger
  focus recovery. Existing pointer/layout/symbol/tool behavior remains intact.
- [x] Focused WorkstationView coverage passes `18/18`; full frontend Vitest passes `704/704`;
  type-check, production build, `git diff --check`, and rebuilt authenticated Chromium pass `1/1`
  with clean diagnostics. Initial browser title-vs-visible-label selectors and the recent-history
  Clear-vs-symbol unit oracle were corrected and rerun under fix-first.
- [ ] Continue `REF-SHELL-V25`/`REF-STATE-VARIANTS` exact-build/unrepresented shell states,
  broader provider/live-entitlement evidence, native physical-monitor placement, beyond-bounded
  endurance, and final audit. Acceptance flexibility used: **board-guided represented shell/menu
  state plus controlled seeded browser evidence**; those visual gaps remain explicitly tracked.
### 2026-08-12 watchlist column-editor keyboard navigation

- [x] Make Columns and Sets editors keyboard-operable with dialog semantics, Enter/Space/arrow
  opening, initial focus, Arrow/Home/End movement, Escape dismissal, and trigger focus recovery.
- [x] Preserve virtualized rows, column overrides/order/group/stack/pin behavior, Python-column
  insertion, and saved column-set persistence. Focused coverage passes `60/60`; full frontend
  Vitest `705/705`; type-check, production build, `git diff --check`, and rebuilt authenticated
  Chromium pass `1/1` with clean diagnostics.
- [ ] Continue `REF-STATE-VARIANTS` partial/exact-build editor visual evidence, broader provider/
  live-entitlement coverage, native physical-monitor placement, beyond-bounded endurance, and
  final audit. Acceptance flexibility used: **board-guided represented watchlist/grid/editor
  state plus controlled seeded browser evidence**; gaps remain explicitly tracked.
### 2026-08-12 EasyScan condition-builder keyboard navigation

- [x] Make the advanced EasyScan condition builder expose expanded state and controls, receive
  deterministic focus on entry, and restore toggle focus on collapse without changing the shared
  condition AST or Python compilation contract.
- [x] Focused EasyScan coverage passes `12/12`; full frontend Vitest `706/706`; type-check,
  production build, `git diff --check`, and rebuilt authenticated Chromium pass `1/1` with clean
  diagnostics. Browser setup/selector assumptions were corrected under fix-first: Add tool →
  EasyScan, outer-region selection, and stable state-independent toggle targeting. A duplicate
  accessible-name defect between the outer builder and nested tree was also repaired with a
  distinct nested label and revalidated.
- [ ] Continue `REF-STATE-VARIANTS`/condition-editor exact-build styling evidence, broader provider/
  live-entitlement coverage, native physical-monitor placement, beyond-bounded endurance, and
  final audit. Acceptance flexibility used: **board-guided represented condition-editor/grid state
  plus controlled seeded browser evidence**; gaps remain explicitly tracked.
### 2026-08-12 Study Lab Python editor contract validation

- [x] Retain the native textarea contract for Study Lab's unified Python editor while preserving
  keyboard completion, listbox active-descendant state, Enter/Tab insertion, Arrow navigation, and
  Escape dismissal. A proposed `role=combobox`/`aria-autocomplete` enhancement was rejected after
  browser validation showed Chromium remapped the control and broke the established
  `textbox[name="Study Python source"]` contract; this is recorded as an accessibility refinement
  gap, not silently accepted as parity.
- [x] Focused PythonSourceEditor coverage passes `3/3`; full frontend Vitest passes `706/706`;
  type-check, production build, and `git diff --check` pass; no-cache rebuilt authenticated
  Study Lab promotion flow passes `1/1` with clean diagnostics.
- [ ] Revisit richer editor combobox semantics only through a non-role-changing implementation
  that preserves native textbox queries and browser behavior. `REF-STUDY-LAB-V25` exact-build /
  unrepresented editor states, provider/live-entitlement, historical truth, native-monitor,
  endurance, and final-audit gaps remain open. Flexibility used: board-guided represented Study
  Lab/editor state plus controlled seeded browser evidence; no visual threshold, mask, or product
  criterion was relaxed.
### 2026-08-12 factory analysis-layout comparison surfaces

- [x] Correct the immutable `Drill Down` factory layout to contain sector, industry, and
  constituent lists plus a tabbed `Selected Symbol` / `Sector Comparison` uPlot chart stack.
- [x] Correct `Sector by Year` to contain linked sector/industry/constituent lists plus visible
  `Selected Symbol` and `Normalized Comparison` chart windows. Comparison configuration is
  serializable (`SPY` with `RSP`) and remains provider-neutral.
- [x] Backend workspace regression passes `24/24` with Docker fixtures; frontend Vitest passes
  `706/706`; type-check, production build, Ruff, Python compile, and `git diff --check` pass;
  rebuilt seeded authenticated Chromium factory acceptance passes `1/1` with clean diagnostics.
- [ ] Continue exact-build/unrepresented factory-state references (`REF-STATE-VARIANTS`),
  provider/live-entitlement breadth, historical truth, native-monitor placement, beyond-bounded
  endurance, and final-audit gaps. Flexibility used: **board-guided represented factory-layout
  state plus controlled seeded browser evidence**; no visual threshold, mask, or product criterion
  was relaxed.
### 2026-08-12 current-head browser matrix and fix-first oracle repairs

- [x] Corrected the four localized browser oracles exposed by the complete Chromium run: workspace
  export/clone actions use `menuitem`, factory layouts use ARIA `tab`, recent-symbol history skips
  the `Clear` action, and `4 Timeframe` is opened through its tab role.
- [x] Supplied the Python plot fixture's canonical completed `/research/runs/{id}/batch-results`
  response and retained the structured output contract. Classified the conflict flow's SPY
  industry and ETF-holdings 404s through the existing handled-unavailable data policy.
- [x] Focused repair flows pass `6/6`; rebuilt seeded authenticated Chromium passes `102/102`
  executed tests with `2` intentional skips. Backend `1382/1382` at `79.69%`, frontend Vitest
  `706/706`, type-check/build, Ruff, compile, and diff checks pass.
- [ ] Continue exact-build/unrepresented visual states, provider/live-entitlement breadth,
  historical truth, native-monitor placement, beyond-bounded endurance, and final-audit gaps.
  Flexibility used: **controlled seeded market-data fixture for browser evidence**; no visual
  threshold, mask, or product criterion was relaxed.

### 2026-08-12 watchlist batch copy/move and keyboard-scope validation

- [x] Add an atomic canonical batch-transfer API for personal watchlist multi-selection. Copy and
  move preserve source ordering, notes/flags metadata, stable instrument IDs, duplicate rejection,
  lock/protection checks, and all-or-nothing failure semantics.
- [x] Wire the Version 25-style watchlist context menu to multi-row selection, list-to-list copy and
  move, and preserve the existing single-row event contract. Add focused backend/frontend
  regression coverage and a real browser flow covering selection, copy, move, source removal, and
  destination membership.
- [x] Fix two browser-only interaction oracles under fix-first: macOS additive selection uses the
  Meta modifier, and the Add-symbol flow waits for the tool's explicit `aria-busy=false` state.
  Make the workstation root focusable so global typing-to-search is deterministic without layout
  coordinates. Focused browser flow passes 1/1; full seeded Chromium passes 105/105 executed with
  2 intentional live-provider skips; backend passes 1385/1385 with Docker; frontend focused
  61/61, full Vitest 707/707, type-check, build, and diff checks pass.
- [ ] Continue exact-build/unrepresented visual states, provider/live-entitlement breadth,
  historical truth, native-monitor placement, beyond-bounded endurance, and final audit. The
  browser run used the documented controlled seeded fixture; no visual threshold, mask, product
  criterion, or data-provenance rule was relaxed. These remaining gaps stay explicitly tracked.

### 2026-08-12 symbol-search loading and no-result states

- [x] Add explicit Version 25-style symbol-search state handling: the canonical search listbox
  remains mounted while a query is pending, exposes `aria-busy`, reports loading through a live
  status, renders a recoverable error state, and renders an explicit no-result state instead of
  silently collapsing the search surface. Stable option IDs and active-descendant semantics now
  support keyboard selection.
- [x] Add mounted-view regression coverage for pending, empty, and rejected canonical search
  responses. Focused workstation binding coverage passes `21/21`; full frontend Vitest passes
  `710/710`; type-check, 468-module production build, and `git diff --check` pass. The rebuilt
  authenticated Chromium no-result flow passes `1/1`, and the adjacent real typing/Escape flow
  remains green.
- [ ] Continue the exact-build/unrepresented search-state visual gap (`REF-STATE-VARIANTS`),
  broader provider/live-entitlement coverage, historical truth, native-monitor placement,
  beyond-bounded endurance, and final audit. Fix-first corrected a held-request browser oracle
  and stale-runtime setup before the authoritative rerun; no product criterion, visual threshold,
  mask, or provenance rule was relaxed. The browser state is board-guided for represented shell
  composition and uses the controlled seeded fixture for deterministic data.
- [x] Recreate the complete seeded stack after frontend image replacement and rerun the broader
  acceptance matrix with matching backend/worker flags. Isolated top-down/watchlist regressions
  pass `3/3`; complete authenticated Chromium passes `103/103` executed tests with two intentional
  skips in 4.6 minutes. The mixed-runtime failures were preserved as setup evidence and did not
  result in any product or acceptance criterion being weakened.

### 2026-08-12 drawing-toolbar keyboard navigation

- [x] Make the shared chart drawing toolbar expose semantic flyout menus: group triggers now carry
  expanded/controls state, drawing flyouts use `role=menu`, and tools use `role=menuitem`.
- [x] Add Arrow/Home/End navigation, Enter/Space activation, Escape dismissal, and trigger-focus
  recovery while preserving the existing pointer selection and uPlot drawing path. Focused
  authenticated drawing coverage passes `3/3` (pointer and keyboard), frontend Vitest passes
  `710/710`, type-check, 468-module production build, and `git diff --check` pass. The complete
  consistently seeded Chromium matrix passes `104/104` executed tests with two intentional skips.
- [ ] Continue exact-build/unrepresented drawing visual/style evidence (`REF-STATE-VARIANTS`),
  provider/live-entitlement breadth, historical truth, native-monitor placement, beyond-bounded
  endurance, and final audit. Fix-first aligned the existing browser oracle with the new public
  ARIA contract; no visual threshold, mask, product criterion, or provenance rule was relaxed.
  Board-guided represented chart/drawing composition and controlled seeded data remain interim.
### 2026-08-13 — Shell Shift+Space hydration race repaired

- [x] Fixed the deterministic F8k-shift failure where a late persisted-workspace
      hydration could reassert SPY after the user had already traversed backward.
      Shell traversal now anchors on the canonical draft when it names a loaded
      symbol, and the newer explicit shell intent is replayed after hydration.
- [x] Added a focused regression for traversal during delayed `loadDefault`; the
      WorkstationView pop-out/bindings suite passes `23/23`.
- [x] Revalidated the real authenticated browser path: F8k-shift passes `1/1`.
      Full frontend Vitest passes `762/762`; type-check, production build, and
      `git diff --check` pass.
- [x] Revalidated the core workstation slice after the repair: authenticated
      top-down, SPX-proxy, relative-strength/ratio, industry and constituent
      drill-down, Study Lab/Python reuse, and keyboard paths pass `14/14` in
      `56s`.
- [ ] Keep the remaining canonical-matrix 502/provisioning failures separate from
      product evidence and rerun the complete matrix under a stable gateway.
      No visual threshold, mask, or acceptance criterion was relaxed. Board-guided
      seeded visual authority remains the explicitly documented flexibility; exact
      or unrepresented states, provider/live entitlements, historical truth,
      native-monitor, longer endurance, and final-audit gaps remain open.

### 2026-08-13 — Canonical bootstrap rollback and provider-sweep containment

- [x] Repaired the unseeded worker bootstrap's rollback boundary. Provider
      failures no longer retain expired ORM instruments across symbols or erase
      the canonical identity transaction; the worker regression suite passes
      `11/11` (bootstrap plus ARQ startup coverage).
- [x] Bounded startup hydration to an explicit configurable two-year lookback
      (`CORE_WORKSTATION_BOOTSTRAP_LOOKBACK_DAYS`, default `730`). Deep history is
      left to scheduled/provider maintenance, preventing a fresh deployment from
      monopolising the API host while still preparing the default workstation.
- [ ] Rebuild the deployment and rerun the authenticated core/full matrices.
      The earlier fresh-stack run is retained as a repository-controlled failure:
      backend exit `137` caused Nginx `502` responses during provisioning. This
      is a fix-first operational repair, not external-gap evidence and not an
      acceptance relaxation.
