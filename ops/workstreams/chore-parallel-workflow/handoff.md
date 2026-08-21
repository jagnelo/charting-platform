# Parallel worktree and RPi deployment workflow

The implementation is accepted on master `49228b5ea118f76e992eb034626cff8fa615ba57`.
The exact master replay `32484097102` is green, with a receipt under
`.ai/validation/49228b5ea118f76e992eb034626cff8fa615ba57.json`. The prior
`64a1ea0695573a89adfcb044b6d37f459954c6ee` / `32477129793` replay remains
historical evidence. Provider availability persistence/Settings coverage,
isolated worktree/runtime allocation, exact-candidate integration, CI replay,
ARM64 image validation, and manual RPi bundle tooling are integrated and
independently replayed.

The deployment path remains deliberately manual. No target, credential, image
bundle, or secret belongs in this branch or in a validation receipt. The only
remaining gap is the real Pi rehearsal, which is blocked until the developer
supplies `.ai/deploy/rpi.env`, SSH key/strict host-key trust, the remote 0600
`shared/app.env`, and a direct exact validated-SHA deployment request.
