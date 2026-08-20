# fix/workflow-hardening

Created from `master` at `aecea059fa39ee43fdae36ad935c401a6b5a607e`.

Implemented the runtime stale-allocation proof, corrected the worktree merge-base
closure guard, and implemented `integrate.py --continue` for paused semantic
conflict candidates. The ratio row-action path now remounts Golden Layout after
the snapshot response replaces the canonical workspace, keeping the visible
ratio in step with the persisted `=XLK/SPY` configuration. Focused runtime tests
pass 2/2; the deterministic F8e.2/F8e.2a browser pair passes; Ruff,
formatting, and diff-check pass. Remaining gap: semantic conflict edits still
require explicit agent review and staging before continuation.

The backend GitHub job now strips uv's path-dependent generated header before
comparing the compatibility export, and invokes pytest through `uv run` after the
frozen environment is installed. The first replay then exposed a second workflow
defect: the integration-only job applied the repository-wide coverage threshold
and failed after 369 passing tests at 47.78%. It now explicitly uses
`--cov-fail-under=0`, matching the Makefile; the branch replay and full candidate
gate must still be rerun.

The replay then exposed an Actions cleanup-only failure from setup-python's
unused `cache: pip` configuration after uv had installed dependencies. That cache
configuration is removed; uv remains the sole dependency cache.

Integration now requires a completed successful push-triggered GitHub replay for
the exact source SHA before validation can publish, and for the published master
SHA after push. A failed master replay records `.ai/master-degraded.json`, which
blocks later integration until the replay is repaired and a successful publish
clears the marker.

The first exact detached candidate reached the full browser gate but failed after
37/260 Playwright tests when the frontend proxy became unreachable at its
allocated port (`ECONNREFUSED 127.0.0.1:18081`), cascading to 119 failures; the
candidate stack was stopped by the exact project-scoped trap and its clean
worktree was removed. The source now adds an nginx frontend healthcheck so stack
startup waits for the browser proxy, and a fresh GitHub replay plus exact
candidate gate is required before promotion.

The authoritative gate now also builds all three production application images
for `linux/arm64`, inspects their platform metadata, and removes only its
temporary validation tags. The local hardening worktree passed that check at
`12a98620df34`; the source replay and exact candidate must still record it.

The first ARM64-enabled exact candidate failed only in the separate visual
replay command: its four setup probes used the Playwright default `localhost:80`
instead of the allocated candidate `STACK_URL`, producing four `ECONNREFUSED
::1:80` failures and skipping the remaining 100 visual cases. The candidate
stack was healthy throughout. The Make target now exports the runtime file for
that visual command as well; the candidate must be rebuilt and rerun.

The branch workflow also now starts E2E Compose with deterministic instrument and
market-data fixtures. A debounced user-settings watcher is guarded by the access
token so logout cannot issue a post-logout PATCH/401; its focused unit regression
passes alongside the existing frontend suite.

The authoritative gate now also renders the development and RPi Compose files
with explicit contract values and runs the frontend production build after the
type-check/unit coverage stage. The new source replay must verify this expanded
gate before exact integration.

The branch-owned helper scripts have now also been normalized with Ruff format;
the focused runtime tests and script lint/format checks pass at this boundary.

The first seeded provider/RPi replays completed backend and frontend jobs
successfully but exposed five browser failures. The canonical-search failure was
deterministic on Linux because the test used `Meta+A`; it now uses Playwright's
cross-platform `ControlOrMeta+A`. The pop-out, benchmark-family, and performance
failures reproduced as passing in focused runs against the isolated seeded stack
and are retained as full-suite replay evidence rather than hidden with changed
baselines or thresholds. The focused canonical-search, pop-out, benchmark-family,
and performance runs all pass locally after this correction; a fresh replay is
required.

The integration gate now executes the captured source workstream's `branch_tests`
through `scripts/run-branch-tests.py` after the seeded stack and visual checks.
The helper parses only the branch-local list, supports a listing mode for audit,
and returns the first failing command without converting retries into success.
