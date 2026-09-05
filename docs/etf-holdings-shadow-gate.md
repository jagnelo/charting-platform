# ETF Holdings Tier 0 Shadow Gate

This runbook defines the post-integration and post-deployment acceptance gate
for the ETF holdings capability. It is deliberately separate from local
validation: a branch can pass deterministic tests while the production gate
remains unproven until real canary observations have accumulated.

## Scope and window

- The gate covers the symbols in the Tier 0 symbol-priority ledger in
  `ops/workstreams/feat-etf-holdings-constituents/provider-audit.yaml`.
- Evaluate a rolling 30-day UTC window, inclusive of the window start and end.
- Each canary observation is retained in the adapter state's bounded
  `extra_data.canary_history` list. The list keeps the most recent 90 records,
  which provides enough room for daily checks and recovery evidence without
  creating an unbounded payload.
- A missing-profile result is not an eligible check. Circuit-open, route-not-
  ready, transport, parser, identity, and source-data failures are eligible
  observations and count against the gate when they occur in the window.

## Pass criteria

The gate passes only when all of the following are true:

1. At least 95% of eligible Tier 0 observations are passing checks.
2. A passing check has `status=success`, `availability=current`,
   `usable_for_current_analysis=true`, explicit identity verification, a
   complete snapshot, an allowed issuer/successor/licensed-vendor source tier,
   and an unexpired freshness deadline.
3. No symbol has two consecutive observations with a missed freshness deadline
   (`availability=stale` or an observation date after its recorded deadline).
4. Every eligible Tier 0 symbol has at least one non-missing-profile
   observation in the window. A symbol with no observation is a coverage gap,
   not an uncounted success.
5. There are zero silent identity/schema/completeness violations. In
   particular, an observation must never claim `current` or current-analysis
   usability while identity, completeness, source tier, or symbol-level audit
   evidence is non-current.

The service function
`app.services.etf_holdings_capability.evaluate_tier0_shadow_gate` returns the
machine-readable result, including the exact window, eligible and passing
counts, success rate, per-symbol freshness streaks, missing-symbol coverage,
and violation details. Administrators can read the same result from
`GET /api/v1/etf-holdings/shadow-gate` (optionally passing `as_of=YYYY-MM-DD`
for a deterministic replay). The endpoint reads persisted bounded canary
history only; it never triggers issuer fetches or manufactures observations.

The same capability response carries dated `symbol_audit.evidence_refs` for
the Tier 0 ledger and the ranked Tier 1 fallback cohorts processed so far. Those references
are explanatory audit evidence only: an `unavailable`, `not_applicable`, or
`unknown` audit outcome remains non-usable for current analysis, even if a
stored snapshot or SEC reconstruction is present. New cohort entries must be
added to the branch ledger and runtime map together, with an exact provider
identity match; an identity mismatch falls back to `unknown` until reconciled.

## Operational procedure

1. Confirm that the shared provider-platform entitlement, quota, health, and
   budget bridge is deployed and that the ETF canary is enabled through the
   approved configuration only. No provider credential or paid source may be
   introduced as part of the gate.
2. Read `GET /api/v1/etf-holdings/shadow-gate` from the production read-only
   admin telemetry path. The response aggregates persisted `canary_history`
   records for every Tier 0 symbol; the underlying evidence retains source
   URL/provider, transport, schema fingerprint, row counts, completeness,
   freshness, latency, failure class, failure streak, circuit state, recovery,
   and capability fields.
3. Store the machine-readable response alongside the deployment SHA and
   provider-platform entitlement revision. For offline replay or alternate
   storage, group the persisted records by symbol and call
   `evaluate_tier0_shadow_gate` with the UTC evaluation date.
4. If the result fails, keep the affected symbol unavailable/degraded in the
   product, investigate the recorded route/identity/schema/completeness cause,
   and do not waive the threshold by relabelling SEC, stale, partial, blocked,
   or unverified evidence as current.
5. A human reviewer closes AC14 only after the 30-day result is a pass and the
   result, deployment SHA, configuration revision, and any incident links are
   attached to the ETF workstream handoff. Until then AC14 remains open.

## Evidence and alerting

Alert on any silent violation immediately, on a second consecutive freshness
miss for a symbol, and when the projected 30-day eligible-check rate falls
below 95%. Route drift, issuer access blocks, schema changes, identity
mismatches, and incomplete rows must retain their explicit failure class and
must not be collapsed into a generic provider success.
