# Parallel worktree and RPi deployment workflow

The implementation is accepted on master `e8b0f1ff960c7e7c3f3c2c2bef2b9024d35a7dc4`.
The exact master replay `32613559588` is green across backend, frontend,
Playwright, and the exhaustive integration gate, with a receipt under
`.ai/validation/e8b0f1ff960c7e7c3f3c2c2bef2b9024d35a7dc4.json`. The repair
addressed the exhaustive `F8e.swing-analysis` transport assumption: cached
indicator restoration is now asserted through the user-visible UI rather than
requiring a GET response. Earlier accepted replays remain historical evidence.
The final candidate was locally validated before publication. During the
earlier validation history Docker Desktop stalled once; the gate failed with
explicit Testcontainers socket timeouts, Docker was recovered without deleting
data, and the full candidate gate was rerun successfully. Docker Compose label
inspection used by safe worktree closure was also repaired. Provider
availability persistence/Settings coverage, isolated worktree/runtime
allocation, exact-candidate integration, CI replay, ARM64 image validation,
and manual RPi bundle tooling are integrated and independently replayed.

The deployment path remains deliberately manual. No target, credential, image
bundle, or secret belongs in this branch or in a validation receipt. The only
remaining gap is the real RPi rehearsal, which is blocked until the developer
supplies `.ai/deploy/rpi.env`, SSH key/strict host-key trust, the remote 0600
`shared/app.env`, and a direct exact validated-SHA deployment request. The
current `make rpi-preflight` safely refuses to mutate anything while that
configuration is absent. After the final gate, Docker storage exceeded the
local 10 GiB housekeeping threshold; the requested `docker system prune -af
--volumes` reclaimed 6.703 GiB, reducing images to 7.041 GiB, and all 18 active
containers and their worktree stacks remained running.
