# fix/chart-template-pointer-interaction

Created from `staging` at `5267f11a491795d85ee35b56cabbe550394f3823`.

## Human authorization

- Recorded at: 2026-10-15T17:44:28.775011+00:00
- Request: Human approved the coordinator proposal to open a narrowly scoped chart-template pointer repair and stated: Yes I approve, and you do not need my acceptance to close it off, it is a waste of time for me to individually verify each individual fix in all the 4 parallel development branches - do this yourself, with care, I just want to get to the merged-into-staging state to finally try this out. Scope: repair physical desktop overlap between populated comparison chips and Plots; preserve no-comparison default and passing narrow layout; validate with ordinary pointer actions, required full profile and exact CI; coordinator owns technical closure and staging integration. No other feature worktree writes, Help oracle changes, provider calls, deployment or data cleanup.
- Closure authorization: pending; do not integrate or deploy until the human explicitly authorizes closure.
- Planning state: ready; PTR1-PTR5 and full_stack_browser retain all required validation. Delegated technical closure will be recorded after validation; deployment remains unauthorized.

## Active changeset: pointer-repair-plan

Owns this workstream only. Existing source is bootstrap commit
`936074d3679b0b76687dd0d39231417c56eecda6`, clean and pushed before preflight.
Writer claim: `4f5ba990-9325-4502-b830-8f1c5ea4572b`; preflight found no owned
containers or volumes. Start from exact green staging `5267f11a`, run
`38773602828`; all required jobs passed before worktree creation.

TC's populated +23.50% real-app cross-check at source `389069a3` shows the
desktop Plots center hitting Remove RSP; its ordinary Plots click times out.
Remove RSP itself passes. The 390x800 TC Classic on-screen 365px chart passes
both ordinary clicks and menu open/close. The full receipt is published in TC
HEAD `6051b078` / evidence commit `13ecdb22`; do not modify that source.

Coordinator-only Chromium diagnostic `/tmp/chart-pointer-diagnostic` confirms
the earlier layering proposal can merely reverse which control is blocked.
A separated right-hand Plots slot with comparisons present makes all controls
independently clickable at desktop and narrow widths in that diagnostic. This
is a candidate, not application acceptance. Preserve the default left150px
Plots placement when no comparison exists and the existing narrow two-row
behavior. Reproduce and validate on this worktree's actual seeded application.

Do not update Help snapshots, import TC/ETF/Provider code, spend provider quota,
delete test accounts or touch other feature stacks. The single TC test account
reported in its retained DB is not this repair's cleanup target. The Help-only
interim reference-policy question is still pending and is a separate issue.

Next: validate/publish this plan, then open the product-geometry context from a
clean synchronized boundary. Use only this worktree's assigned resources for
application validation and preserve exact before/after evidence.
