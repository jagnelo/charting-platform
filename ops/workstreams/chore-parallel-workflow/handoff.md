# Parallel worktree and RPi deployment workflow

The implementation is accepted on master `64a1ea0695573a89adfcb044b6d37f459954c6ee`.
The exact master replay `32477129793` is green, with a receipt under
`.ai/validation/64a1ea0695573a89adfcb044b6d37f459954c6ee.json`. Provider
availability persistence/Settings coverage, isolated worktree/runtime
allocation, exact-candidate integration, CI replay, ARM64 image validation, and
manual RPi bundle tooling are integrated and independently replayed.

The deployment path remains deliberately manual. No target, credential, image
bundle, or secret belongs in this branch or in a validation receipt. The only
remaining gap is the real Pi rehearsal, which is blocked until the developer
supplies `.ai/deploy/rpi.env`, SSH key/strict host-key trust, the remote 0600
`shared/app.env`, and a direct exact validated-SHA deployment request.
