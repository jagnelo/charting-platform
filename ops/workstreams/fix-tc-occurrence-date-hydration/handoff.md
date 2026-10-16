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

## Next actions

1. Transplant only the approved fix commit and inspect the result against the
   staging base.
2. Run focused local checks where the environment supports them and obtain a
   clean exact-source CI result for the synchronized repair tip; no flaky test
   is acceptable.
3. Complete the branch-owned validation/closure receipt, then invoke the
   canonical guarded degraded remediation integration.
4. Keep staging degraded until the exact merged staging SHA passes the
   Exhaustive Integration Gate and a synchronized green receipt is recorded.
5. Continue the root goal with Provider → ETF → full TC2000 → Strategy Lab v2;
   do not treat this narrow repair as full TC acceptance.
