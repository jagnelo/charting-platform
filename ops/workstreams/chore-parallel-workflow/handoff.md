# Parallel worktree and RPi deployment workflow

The implementation is accepted on master `40b86a496512b767200f65a91e35529845342ab0`.
The exact master replay `32514372931` is green across backend, frontend,
Playwright, and the exhaustive integration gate, with a receipt under
`.ai/validation/40b86a496512b767200f65a91e35529845342ab0.json`. The source
repair replay `32507967151` and the earlier accepted replays remain historical
evidence. The final candidate was locally validated before publication. During
that validation Docker Desktop stalled once; the gate failed with explicit
Testcontainers socket timeouts, Docker was recovered without deleting data,
and the full candidate gate was rerun successfully. Provider availability
persistence/Settings coverage, isolated worktree/runtime allocation,
exact-candidate integration, CI replay, ARM64 image validation, and manual RPi
bundle tooling are integrated and independently replayed.

The deployment path remains deliberately manual. No target, credential, image
bundle, or secret belongs in this branch or in a validation receipt. The only
remaining gap is the real Pi rehearsal, which is blocked until the developer
supplies `.ai/deploy/rpi.env`, SSH key/strict host-key trust, the remote 0600
`shared/app.env`, and a direct exact validated-SHA deployment request.
