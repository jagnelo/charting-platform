# fix/chart-template-key-generation

Created from `staging` at `79c8623fb122ccdd7c86e4b45e03b7e2c6708e7b`.

## Human authorization

- Recorded at: 2026-10-17T06:12:20.371918+00:00
- Request: Human-authorized narrow browser repair: replace unsupported crypto.randomUUID calls in chart-template and column-set key generation with crypto.getRandomValues, preserving the eight-hex key suffix and adding regressions. This unblocks Provider validation; do not bring in the full TC2000 feature or alter its roadmap.
- Closure authorization: pending; do not integrate or deploy until the human explicitly authorizes closure.
- Planning state: draft; the implementation agent must complete scope, acceptance criteria, tests, and local validation profile before creating a goal.

Update this handoff at each coherent boundary.
