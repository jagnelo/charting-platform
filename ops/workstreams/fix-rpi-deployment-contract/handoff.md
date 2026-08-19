# fix/rpi-deployment-contract

Created from `master` at `aecea059fa39ee43fdae36ad935c401a6b5a607e`. Update this handoff at each coherent boundary.

The RPi helper now bundles the exact application images plus pinned ARM64
Postgres/Redis images, uses a local file lock and the fixed remote Compose lock,
keeps shared secrets out of release metadata, refuses Pi-side pulls/builds, and
records bundle/prior-release/schema/smoke metadata. The authenticated smoke now
checks health, login, stable workspace reads, and provider availability. A real
preflight/deployment rehearsal still requires the developer's RPi target and
0600 shared environment file.
