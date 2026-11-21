# fix/quota-ledger-indexes

Created from `staging` at `896ad20fc8652fb4882c5e851cc8f3bf77982b45`.

## Human authorization

- Recorded at: 2026-11-21T00:31:33.715906+00:00
- Request: Continue the refresh-queue throughput gap ('Yes, start it'): after release 896ad20f, production throughput stayed flat because every provider call serialises on the SQLite quota ledger write lock, and its admission queries full-scan the append-only baseline/reservation tables (~240 ms lock hold per admission). Index the hot ledger queries for new and existing ledgers.
- Closure authorization: pending; do not integrate or deploy until the human explicitly authorizes closure.
- Planning state: draft; the implementation agent must complete scope, acceptance criteria, tests, and local validation profile before creating a goal.

Update this handoff at each coherent boundary.
