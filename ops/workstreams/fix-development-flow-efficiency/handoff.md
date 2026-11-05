# fix/development-flow-efficiency

## Current state

Root-authorized workflow repair is implemented locally in the assigned branch.
The native unbudgeted goal on this same visible thread is active. The Root
bootstrap exception is recorded in `plan.yaml`: the reviewed local plan and
exclusive claim remain required; a plan-only push is skipped; normal clean,
synchronized exact-source checks still apply at integration.

## Changes

- Added exact changed-path lanes. Metadata/workstream changes run durable
  hash/scope/narrative guards; workflow-only changes run workflow regressions.
  Both require an exact trusted successful full product qualification for the
  parent SHA and prove the current diff contains only allowlisted paths. Missing
  prior evidence, unknown paths, product changes, and renames touching runtime
  inputs fall back to broad validation.
- Staging remains the single full integration gate at cross-feature batch
  boundaries. Master promotion now checks the exact successful staging workflow,
  push event, SHA, complete required job set, and synchronized refs, then runs
  release identity/provenance checks. The promotion helper requires exact
  staging and master run IDs and the explicit same-SHA reuse mode; the master
  verifier itself checks the complete successful staging job set. A small
  `Exhaustive Integration Gate` compatibility status lets the current Root
  coordinator finish its transition, while its job text states that product
  suites were not rerun. Receipt schema 2 records same-SHA reuse explicitly,
  and the RPi receipt guard still accepts legacy `github_replay=pass` receipts.
- The observer makes one status-only read per three minutes for up to 243
  minutes, covering the 45-minute backend prerequisite plus the 180-minute
  exhaustive gate; it fetches job details once after terminal status and reports
  expiry as pending, and seeks at most 12 retry attempts only after a failed
  allowlisted setup step. Rate-limit/access failure remains unavailable evidence.

## Measured cost implication

The observed feature baseline is about 31 minutes backend plus 23 minutes
browser tests per push, roughly 54 minutes; workstream-only closure repeated the
same jobs. Eligible guarded pushes avoid those product jobs after exact parent
qualification. The focused workflow suite completed 192 tests in 2.31 seconds
locally, and the required runtime/YAML narrative guard passed in 9.21 seconds.
The prior roughly two-hour master replay is removed for the identical staging
SHA; master release verification has a 10-minute job bound. Staging still runs
the full gate once per meaningful batch.

## Validation

- Workflow tests: 195 passed in 2.91 seconds after the observer and promotion guards.
- After the final `branch-tests.json` broad-lane correction, the affected
  classifier/temp-Git sequence and local-profile checks passed 9/9 in 0.56
  seconds; the full workflow suite was not rerun for this allowlist-only edit.
- Workstream record validator: passed for this branch's ready plan.
- Runtime/YAML narrative guard: passed, 1 test in 9.23 seconds with `--no-cov`.
- Ruff check and format check: passed for all changed Python files.
- `git diff --check`: passed.
- No full product/browser/Docker/provider suite was rerun locally; no pass is
  claimed for any skipped suite beyond trusted, exact same-source prior evidence.

## Closure state

Root accepted the bounded implementation under the human's standing delegation;
the plan records that authorization and `ready_for_integration` status. The
final pushed-source CI run is still pending. Root owns integration capture,
promotion, and deployment after exact-source CI passes. The live ticker repair
release remains independent.
