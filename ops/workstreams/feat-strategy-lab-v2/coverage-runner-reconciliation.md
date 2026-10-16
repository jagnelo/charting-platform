# Prospective Provider coverage-runner reconciliation

Status: prospective read-only design note, recorded 2026-10-16. This is not a
new Provider prerequisite, a source change, a merge authorization, or evidence
that the pending Provider checkpoint is accepted. Reconcile only after the
actual accepted green Provider staging release reaches this Strategy branch in
the prescribed Provider → ETF → TC2000 → Strategy order.

## Source observations

Strategy source `54fa13e1ba17a40de6f242e16d5a96d8217615cb` currently has no
`scripts/backend_coverage.py`. Its local `make test-backend-coverage` directly
runs `tests/unit`, `tests/integration`, and `app/strategy_lab_v2/tests` in the
same pytest coverage invocation and enforces the combined 75% threshold. Its CI
unit command conditionally includes `app/strategy_lab_v2/tests`; a separate CI
integration command runs `tests/integration`. Backend pytest configuration
retains `--cov-fail-under=55`.

The conditional CI path does not prove the Strategy package ran in every
attempt. On exact Strategy source `54fa13e1ba17a40de6f242e16d5a96d8217615cb`,
run `38820638540`, backend job `116716106264` failed at
`2026-10-15T23:00:25.0138175Z` with exit 152. The log shows the unit stream at
36%, in `tests/unit/services/test_research_runner.py`, then process termination.
It contains no pytest failure/traceback block or coverage summary; backend
integration and dependent E2E/Exhaustive jobs were skipped. The Strategy suite
was listed after `tests/unit` in the job command, but this run does not prove it
was reached or executed. This was not an aggregate 75% coverage failure.
Earlier successful CI run `38812646577` on `1fca3ec0` is historical evidence
only, not acceptance of exact source `54fa13e1`.

## Exact-source failure and bounded diagnosis

Observed evidence is an abrupt process exit, not a failed assertion. Exit 152
is consistent with the Linux shell convention `128 + SIGXCPU(24)`. In exact
source `54fa13e1`, `backend/research_runner/runner.py` applies a process-level
`RLIMIT_CPU` soft bound based on `ceil(current process CPU seconds + 15)` during
research execution and restores limits in `finally`. A CPU-limit signal during
an in-process unit test could terminate the whole pytest process before normal
cleanup/summary. The last visible file/progress and signal-like exit make this a
plausible lead; they do not prove which test or execution crossed a limit, nor
that the resource guard is the sole cause. Coordinator source investigation
also reported reproducing this exit class near a CPU-second boundary, which
strengthens the lead but is not a replacement for exact-attempt causality.

Do not infer that bounded shards alone fix the failure, alter `RLIMIT_CPU`,
increase limits, lower either coverage threshold, or blindly rerun the suite.
Diagnosis should first retain this exact job log/source linkage and inspect
existing runner limits/tests; after the authorized green Provider baseline,
bounded independent shards can isolate any reproducer without changing
production limits. A fix requires a reproduced causal path and regression
evidence. Keep the `1fca3ec0` success, the `54fa13e1` failure, and later CI
results as separate immutable receipts.

The pending Provider source inspected read-only at
`91164b355bf95da326063ce19caa33ed26003960` adds
`scripts/backend_coverage.py`. Its `TEST_ROOTS` are currently only
`tests/unit` and `tests/integration`; unit node IDs are run in bounded shards of
50 with per-process limits, while the integration suite runs separately with
a timeout. Coverage is erased once, appended across processes, then reported
with `--fail-under=75`. Its Make target calls this runner. Provider CI instead
uses a unit step, a separate integration step with `--cov-append`, and a final
combined `coverage report --fail-under=75` step. This inspected Provider source
is pending and is not an accepted/published green baseline.

## Required reconciliation after the actual green release

- Preserve the bounded local runner architecture and its resource/time limits;
  extend collection, prefix parsing, missing-root checks, and test execution so
  `app/strategy_lab_v2/tests` is a real third collected and executed root. Do
  not only collect its node IDs or omit them from the shard loop. Keep strategy
  tests in bounded processes (as an explicit shard group or joined bounded
  unit-like shards), and retain the separate bounded integration process.
- Preserve one erased coverage dataset followed by append-only coverage across
  every executed unit shard, the Strategy package suite, and integrations. Keep
  the combined `coverage report --fail-under=75` and XML output. Do not weaken
  the repository's existing backend pytest `--cov-fail-under=55` setting or
  substitute the 75% aggregate check for any package/unit check currently
  enforced.
- In CI, retain the actual package inclusion in the unit step, integration
  coverage append, and final aggregate 75% report. Confirm from the exact run's
  command/job evidence that the v2 package was actually executed and the unit
  process completed. Do not claim CI ran the bounded local helper or its shards
  unless the CI workflow actually invokes it; accurately describe the separate
  unit/integration CI commands.
- Add focused runner regressions for third-root collection and parsing,
  non-empty-root enforcement, bounded execution of every Strategy node ID, and
  coverage accumulation/threshold behavior. After full reconciliation, run the
  complete local combined backend gate and exact-source CI under the assigned
  heavy-gate order, then record exact source SHA, job commands, test totals and
  both thresholds.

This note does not authorize importing the pending Provider branch, editing its
worktree, creating an interim combined copy, changing migrations/namespaces,
starting heavy validation, or inventing a Provider API/runtime dependency.
Recheck source heads, namespaces, and current runtime contracts from the actual
released green staging baseline before implementation.
