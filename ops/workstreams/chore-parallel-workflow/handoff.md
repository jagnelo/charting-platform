# Parallel worktree and RPi deployment workflow

The implementation is accepted on master `27cac6d3132ec29bdbdb6d339ed0d04ca52bd7b3`.
The exact master replay `32606866786` is green across backend, frontend,
Playwright, and the exhaustive integration gate, with a receipt under
`.ai/validation/27cac6d3132ec29bdbdb6d339ed0d04ca52bd7b3.json`. The source
repair replay `32605651305` and the earlier accepted replays remain historical
evidence. The final candidate was locally validated before publication. During
the earlier validation history Docker Desktop stalled once; the gate failed
with explicit Testcontainers socket timeouts, Docker was recovered without
deleting data, and the full candidate gate was rerun successfully. The latest
candidate also repaired Docker Compose label inspection used by safe worktree
closure. Provider availability persistence/Settings coverage, isolated
worktree/runtime allocation, exact-candidate integration, CI replay, ARM64
image validation, and manual RPi bundle tooling are integrated and independently
replayed.

The deployment path remains deliberately manual. No target, credential, image
bundle, or secret belongs in this branch or in a validation receipt. The only
remaining gap is the real RPi rehearsal, which is blocked until the developer
supplies `.ai/deploy/rpi.env`, SSH key/strict host-key trust, the remote 0600
`shared/app.env`, and a direct exact validated-SHA deployment request. After
the latest gate, Docker storage was above the local 10 GiB housekeeping
threshold; the requested prune reclaimed 5.05 GiB and all 18 active containers
and their worktree stacks remained running.
