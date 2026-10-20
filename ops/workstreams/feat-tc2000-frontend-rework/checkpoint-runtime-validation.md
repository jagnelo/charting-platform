# Fresh checkpoint fixture validation route

## Current TC visual font runtime disposition — 2026-10-20

For this TC reference set, run every visual profile in the pinned
`mcr.microsoft.com/playwright:v1.62.1-noble` image **without** a host DejaVu
font mount. This supersedes the earlier normalized-font recommendation below.
The exact uniform no-mount run on product source
`35ee3c0263c5255ecd8d9dafee4cd48c8e46c163` passed all104 visual cases across
the four existing profiles in15.7minutes, one worker, zero retries, with the
original references and0.005 tolerance. Do not mix host-mounted and unmounted
profiles within a matrix.

The matched network-none fontconfig A/B used the same cached Noble image. With
no host mount, `monospace` resolved to WenQuanYi Zen Hei Mono and
`ui-monospace` to WenQuanYi Zen Hei; with the read-only host DejaVu mount they
resolved to DejaVu Sans Mono and DejaVu Sans. Arial remained Liberation Sans.
The three formerly mismatching Study structured-result/sandbox-error profiles
then passed unchanged in the no-mount focused comparison. The previous
host-mounted full run remains preserved as101/104 red, along with all three
focused A/B results; no references, assertions, masks, skips or tolerance were
changed. This is TC-reference-specific runtime evidence, not a global font
policy or official V25 parity.

Prepared 2026-10-15 while canonical matrix process11617 remains active. This
route passed Compose config validation and subsequently initialized six healthy
services after matrix11617 ended. The unchanged floating-window visual case
passes on the fresh fixture (14.4s). Four-profile focused replay passed16/16
in2.8m. The temporary six-service project, four generated fixture volumes and
its network were removed afterward; original assigned resources are intact.

The assigned stack's dataset fixture expires one day after initialization.
Its reused data now reports Stale, but floating-window acceptance correctly
requires Current. Do not edit freshness timestamps or weaken that assertion.
Use a fresh isolated fixture initialized by the existing opt-in E2E seed.

Use the repository's docker-compose.yml plus scratch override
`/tmp/tc2000-checkpoint-fresh.override.yml`. The override selects the cached
TC image for each service, mounts current backend app/Alembic read-only and
current production frontend/dist read-only, bounds memory, and makes the
network internal. Keep the original research-runner isolation settings.
The cached backend's uv.lock, requirements.txt, Dockerfile and runner Dockerfile
hashes match current source exactly (read-only verification). The runtime is
validation infrastructure, not a combined Git checkout or upstream integration.

Configuration validated with:

```sh
WORKTREE_ID=feat-tc2000-frontend-rework-f63d60aebc \
POSTGRES_HOST_PORT=28332 BACKEND_HOST_PORT=28308 FRONTEND_HOST_PORT=28388 \
SECRET_KEY=tc-checkpoint-isolated-test-secret \
E2E_SEED_INSTRUMENTS=true E2E_SEED_MARKET_DATA=true \
docker compose --env-file /dev/null -p tc2000-checkpoint-fresh-9d78e1 \
  -f docker-compose.yml -f /tmp/tc2000-checkpoint-fresh.override.yml config --quiet
```

Before startup, recheck coordinator source freezes, unused ports, and the exact
project's existing containers/volumes. Build the current frontend serially;
then use the same invocation with `up -d --no-build --wait`. This creates its
own four fixture volumes. No existing assigned volume is attached. The empty
env-file avoids loading deployment credentials; the internal bridge prevents
provider egress. On this Docker host, the internal bridge does not publish the
configured host ports. Keep the pinned Noble browser on that same internal
Compose network and use Compose DNS with `STACK_URL=http://frontend`; do not
use host networking, a host-port relay, or an external CDN proxy. Current
source contains no static OneSignal SDK include. With the OneSignal App ID
unset, no SDK request is made; an explicitly configured user action remains the
only supported opt-in load path. Keep provider routing/refresh disabled and all
provider/OneSignal keys blank in the visual fixture.

Historical 2026-10-15 setup recommendation (superseded by the exact TC A/B
evidence above): the host DejaVu directory was previously recommended as a
read-only mount for a normalized matrix. Do not apply that mount to the current
TC references. The unchanged run command still covers all four existing
viewport/DPI projects, one worker and zero retries, with
`RUN_BOARD_VISUAL_PARITY=1`; preserve every state assertion, screenshot, mask
and the `0.005` tolerance. Allow enough bounded wall time for all104 cases and
retain the full terminal report/artifacts before scoped cleanup.

Cleanup must target **only** `tc2000-checkpoint-fresh-9d78e1`, using that same
Compose invocation with `down --volumes`. Verify exact project labels before
cleanup. Never invoke the generic branch resource cleanup: it discovers by
worktree label and could remove the assigned stack as well. Retain logs and
results before deleting this newly generated fixture. Verify the assigned
six containers and four original volumes are intact afterward.

This route preserves the pending exact full integration requirement. A series
of individually green checks is not a passing `make validate-integration`
receipt; record the actual invoked checks and any remaining wrapper limitation.

Current frontend production build passed (520 modules,14.14s). Cached research
runner's curated.py, runner.py, validation.py and canonical_indicators.py hashes
match current source. Its shell-fork denial during a checksum command is a
sandbox restriction, not PID exhaustion (one PID observed); direct Python
read-only checksums succeeded.
