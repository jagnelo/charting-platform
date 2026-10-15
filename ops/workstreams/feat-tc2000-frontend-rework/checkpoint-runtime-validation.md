# Fresh checkpoint fixture validation route

Prepared 2026-10-15 while canonical matrix process11617 remains active. This
route has passed Compose config validation only; it has not started services.
Wait for the existing matrix before another browser/runtime workload.

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
provider egress. Test http://127.0.0.1:28388 using the pinned Noble browser and
the existing unchanged fixture assertions. Start with floating-window freshness
to verify the fixture correction, then run required complete checks.

Cleanup must target **only** `tc2000-checkpoint-fresh-9d78e1`, using that same
Compose invocation with `down --volumes`. Verify exact project labels before
cleanup. Never invoke the generic branch resource cleanup: it discovers by
worktree label and could remove the assigned stack as well. Retain logs and
results before deleting this newly generated fixture. Verify the assigned
six containers and four original volumes are intact afterward.

This route preserves the pending exact full integration requirement. A series
of individually green checks is not a passing `make validate-integration`
receipt; record the actual invoked checks and any remaining wrapper limitation.
