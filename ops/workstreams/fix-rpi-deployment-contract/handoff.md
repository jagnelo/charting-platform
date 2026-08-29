# fix/rpi-deployment-contract

Created from the accepted `master` baseline at `ad39700aa0eb109fc9a3dbc7f684a099cb2e9e51`; rebased after provider monitoring and CI timeout-hardening promotion. Update this handoff at each coherent boundary.

The RPi helper now bundles the exact application images plus pinned ARM64
Postgres/Redis images, uses a local file lock and the fixed remote Compose lock,
keeps shared secrets out of release metadata, refuses Pi-side pulls/builds, and
records bundle/prior-release/schema/smoke metadata. The authenticated smoke now
checks health, login, stable workspace reads, and provider availability. A real
preflight/deployment rehearsal still requires the developer's RPi target and
0600 shared environment file.

The branch also carries the corrected independent CI replay contract: generated
uv headers are normalized, pytest runs through `uv run`, and integration-only
coverage does not apply the combined threshold.

Preflight now checks stopped Compose containers (`docker ps -a`) as well as
running ones and fails closed when `ss` is unavailable, so a reserved-port
collision cannot be silently missed. Focused deployment contract tests pass 4/4.

The remote deployment lock now uses `flock` on a file rather than a directory,
so an interrupted SSH process releases the lock automatically. Preflight fails
closed if `flock` is unavailable.

The branch E2E workflow now enables both deterministic instrument and market-data
fixtures. This matches the exact local gate and prevents chart/workstation
failures caused by accidentally starting the stack in its default unseeded mode.

The transaction now uploads the manifest and release Compose file as `.part`
metadata, verifies their source/tree, bundle, and Compose checksums remotely, and
only then moves the incoming files into place. The release Compose passes the
bounded provider-probe timeout to backend and worker services.

The backup verification path now invokes `pg_restore --list` inside the
already-running charting Postgres container instead of executing the incoming
runtime image before `docker load`. This preserves the backup-before-load
transaction ordering and avoids an implicit Pi-side image pull. The focused
deployment contract suite remains green at 5/5; an actual preflight and
authenticated LAN rehearsal still require the developer-supplied RPi config.

## 2026-08-27 — Focused deployment-contract refresh

The declared deployment checks were rerun on the clean branch: `tests/deployment/test_rpi_contract.py`
passed `5/5`; Ruff check/format and Python syntax checks for `scripts/rpi.py` passed; and
`git diff --check` passed. No Pi was contacted and no deployment was attempted. The remaining
blocker is intentionally external: target configuration, SSH trust, shared environment secrets,
and a direct human-requested deployment are still required for real preflight and LAN rehearsal.

## 2026-08-29 — Branch superseded by explicit human decision

The human explicitly requested that this `fix/` branch be closed because RPi deployment is not
currently in scope and should later be treated as a separately planned feature. The deployment
implementation is already present in the green staging/master history; this branch's remaining
tail is operational evidence only. The branch is therefore marked `superseded`, no Pi was contacted,
and the remote branch remains available as an audit record. Any future deployment work must start
from a fresh branch based on green `staging` with a new request and target-specific validation.
