# fix/rpi-deployment-contract

Created from the validated `master` baseline at `4fc20898d33d0ecaef503728484779d852cf7933`; rebased after the diagnostic master promotion. Update this handoff at each coherent boundary.

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
