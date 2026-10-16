# fix/staging-ci-watch-recovery

Created from `staging` at `b7eae4b0a509a135eb85fef2984633499b16617e`.

## Human authorization

- Recorded at: 2026-10-16T07:24:16.553433+00:00
- Request: Start coordinating the four-feature staging integration. Proceed until you either have no way to continue and/or require my action for something. Technical repairs: Yes I approve, and you do not need my acceptance to close it off; do this yourself, with care, I just want to get to the merged-into-staging state to finally try this out. Scope: repair coordinator read-only CI watch exhaustion and exact-source interrupted-watch recovery; no product/test-policy/deployment/data changes.
- Closure authorization: pending; do not integrate or deploy until the human explicitly authorizes closure.
- Planning state: draft; the implementation agent must complete scope, acceptance criteria, tests, and local validation profile before creating a goal.

## Current implementation plan

Coordinator-owned workflow repair under existing ACTIVE unbounded four-feature
root goal01a115f5-8fd9-7951-ab39-0e484eb17135, not a replacement goal or product
acceptance. Mandatory preflight established claim
b12c73e0-2ad3-420f-9fe9-4fa11209f8d7 from exact degraded stagingb7eae4b0.
The original canonical documentation merge succeeded, but public API polling
made two requests every five seconds and exhausted the unauthenticated allowance
before hosted tests finished. Preserve this interrupted-watch record and marker;
do not infer failing product tests or delete the marker manually.

Implement only conserved read-only polling and exact-current guarded receipt
reconciliation. Reuse existing closure/exhaustive gates; no source-feature
merge, data cleanup, API credential handling, or new browser fixture. WATCH1-3
and owned paths in plan.yaml are the contract. Delegate technical closure only
after actual tests and exact-source CI pass. Root goal remains active through
all four feature merges, joint human-usable validation and same-owner release.

## Implementation boundary 2026-10-16 07:30 UTC

Implemented conservative120-second public API watch, terminal-only job reads,
explicit unavailable/rate-limit diagnostics, and guarded `staging-reconcile`.
Original one-hour watch envelope retained as30polls, no test retry/tolerance
change. Reconciliation verifies recorded exact current/source/start ancestry,
holds the normal integration lock, invokes the existing mandatory exhaustive
gate, refetches clean synchronized staging, rejects changed attempt metadata,
persists a green receipt BEFORE marker release, and never merges or pushes.
75 workflow checks passed0.43s including real API-gate rejection and16negative
reconciliation cases; Ruff/check/format/profileunit/diff checks passed. Original
rate bucket headers remaining0of60, reset1792138791. Do not poll that bucket
before reset or infer passing CI from unavailable evidence. Connected GitHub
reads can independently observe hosted progress without manufacturing receipts.
No product code/reference/oracle/deployment/data changes. Implementation still
needs normal exact-source CI and canonical guarded remediation integration;
no local operational marker has been bypassed or removed by this work.

Final review additionally restricts reconciliation itself to the exact
persistent staging caller (feature/root-control callers refused). Expanded
regression suite76passed0.49s; previous75-case implementation receipt remains
historical. Final exact-source CI must cover this additional guard too.
