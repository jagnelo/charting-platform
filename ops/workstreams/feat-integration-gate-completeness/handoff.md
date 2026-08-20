# feat/integration-gate-completeness

Created from `master` at `15b4a77d1f5a06e625f4849c58c67a27748139bd`.

## Current boundary

The integration gate now has explicit migration compatibility, research-runner
isolation/resource, and reviewed live-provider targets. Migration checks are
conditional on changed Alembic files; provider checks are deterministic by
default and never imply live coverage without explicit credentials and
`RUN_LIVE_PROVIDER_TESTS=1`.

## Remaining validation

- Run the branch-declared syntax and provider-policy checks.
- Exercise the migration script on a migration-changing candidate before
  integrating this branch.
- Preserve the RPi deployment and provider-monitoring branches as separate
  exact-candidate integrations after this gate branch is accepted.
