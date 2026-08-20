# feat/integration-gate-completeness

Created from `master` at `15b4a77d1f5a06e625f4849c58c67a27748139bd`.

## Current boundary

The integration gate now has explicit migration compatibility, research-runner
isolation/resource, and reviewed live-provider targets. Migration checks are
conditional on changed Alembic files; provider checks are deterministic by
default and never imply live coverage without explicit credentials and
`RUN_LIVE_PROVIDER_TESTS=1`.

The retained Linux master-gate artifact exposed that Playwright had 104
Darwin-only visual references, so the Linux replay could not even compare
screenshots. The exact 104 Linux actuals from that deterministic replay are
now checked in as `*-linux.png` references. This adds the missing platform
oracle only; masks, thresholds, and test cases are unchanged.

## Remaining validation

- Run the branch-declared syntax, provider-policy, and Darwin/Linux reference
  parity checks.
- Exercise the migration script on a migration-changing candidate before
  integrating this branch.
- Preserve the RPi deployment and provider-monitoring branches as separate
  exact-candidate integrations after this gate branch is accepted.
