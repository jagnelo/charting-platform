# fix/tc-occurrence-date-hydration

## Authorization and scope

This is a narrow coordinator-owned repair under the already-active root goal
`01a115f5-8fd9-7951-ab39-0e484eb17135`; it does not replace or narrow that
goal. The human delegated technical acceptance of necessary repairs while
authorizing central four-feature staging integration. This branch addresses
only the TC2000 chart-hydration race behind the exact staging E2E failure.

The repair starts at degraded persistent staging SHA
`e0cb269afc8460bdc814c93ec71c640f01b2b31f`. Its only product/test changes are
to be transplanted from TC commit `957216a1bbb0727dc7f5f26f644d84df911e5522`;
the full TC2000 branch remains scheduled in Provider → ETF → TC2000 → Strategy
Lab v2 order. Do not alter screenshots, visual tolerances, data, quotas, paid
features, deployment, or operational-trial policy.

## Evidence at start

- TC exact-source CI run `38954608461` on the fix commit succeeded, including
  Frontend Unit Tests, Backend Tests, Branch-declared Tests, and E2E Tests.
- Staging run `38947572686` on `e0cb269afc8460bdc814c93ec71c640f01b2b31f`
  passed backend, frontend unit, and Exhaustive Integration Gate. Playwright
  failed because test `F8s-breadth-family-ratio` expected linked timestamp
  `2026-06-27T00:00:00Z` but observed stale cursor timestamp
  `2025-12-29T21:00:00Z`; retry passed but the run remained red as flaky.
- The repair branch was bootstrapped by the guarded worktree helper from the
  exact synchronized degraded SHA, with `REMEDIATE_DEGRADED=1` authorization.

## Reconciliation note

The transplant conflicted only in `UPlotChart.vue`. The TC branch's added
`linkedCursorProgrammatic` guard assumes cursor hooks already present on the
full TC feature branch, but absent from degraded staging. The existing staging
chart publishes cursor timestamps through the shared workspace store, so its
explicit-timestamp gate is sufficient to preserve the asserted linked date.
Keep staging's chart component unchanged; the complete TC branch still retains
its programmatic-cursor behavior for its later ordered integration. No visual
snapshot or tolerance was changed.

Review also found that a timestamp-only cleanup could let an older in-flight
selection clear a newer selection for the same date. The repair adds a
per-selection token to the store hold and a regression covering same-date
supersession, then lets the owning request release only its own token.

## Current progress and next actions

- Planning is complete and the repair worktree has an exclusive claim under
  the already-active root goal; no competing goal was created.
- Repair source commit `0794384a9c431732376a00a947bd42912afbb5fc` contains only
  the store/view timestamp-race fix, its regression, and its workstream record;
  staging's `UPlotChart.vue` is unchanged. Focused store tests passed `75/75`,
  and `npm run build` passed locally. The assigned isolated Compose project
  `charting-stack-fix-tc-occurrence-date-hydration-5fe4d495` then passed the
  focused F8s-breadth-family-ratio Playwright regression `1/1` in 10.3 seconds
  against this exact source with `E2E_SEED_MARKET_DATA=true`. The targeted test
  stubs its market-data route and used only the isolated repair database.
- Repair exact-source CI run `38959676649` is not acceptable: Frontend Unit
  Tests passed, but Branch-declared Tests failed because a descriptive sentence
  was mistakenly placed in the executable `branch_tests` list and `/bin/sh`
  rejected it. Backend Tests and Playwright E2E later passed; the run remains
  irrecoverably red only because of the completed declaration job. This is a
  harness declaration error, not a product-test failure. The local plan now has
  an empty command list with an explanatory `branch_tests_reason`; the corrected
  declaration must be pushed and pass exact-source CI without flakes.
- The repair frontend package lock matches TC's lock blob exactly. An offline
  `npm ci` installed the locked dependencies, and Playwright collected exactly
  the target `F8s-breadth-family-ratio` case. The local execution completed
  against the isolated stack. The exact repair project was then brought down
  through `make test-stack-down`; read-only verification found no matching
  containers, volumes, or network, and confirmed the shared default Docker
  builder remained selected. Provider and TC-assigned stacks were untouched.
- The required local full-stack/browser regression is complete. Exact branch
  CI run `38963802695` matches source
  `7a5af939b034179ff055e296a3a43baeaffb91bd`: Frontend Unit, Backend,
  Branch-declared, and Playwright all succeeded; E2E reported 151 passed, 109
  skipped, with no retry, flaky test, or failure. The feature branch's
  Exhaustive Integration Gate was skipped by branch policy. Earlier red runs
  remain preserved as history, not acceptance.
- This closure-record commit must itself receive green exact-source CI. Once
  that exact pushed tip is green, the coordinator invokes only the canonical
  `make integrate BRANCH=fix/tc-occurrence-date-hydration
  REMEDIATE_DEGRADED=1` workflow, preserving base
  `e0cb269afc8460bdc814c93ec71c640f01b2b31f`. Keep the degraded marker until
  the exact merged staging SHA is synchronized and passes
  `Exhaustive Integration Gate`.
- `session.json` records the last known pre-record checkpoint `7a5af939`; the
  commit that contains this closure record cannot include its own final SHA.
  After committing, verify the actual `HEAD`, `origin/fix/tc-occurrence-date-hydration`,
  and clean worktree externally before starting the next integration context.
- Continue Provider → ETF → full TC2000 → Strategy Lab v2 afterward; this
  narrow repair is not full TC acceptance.
