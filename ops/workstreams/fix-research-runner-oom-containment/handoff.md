# fix/research-runner-oom-containment

Created from `staging` at `131ae8fea3aa777ba3894387080fee789b0b854c` (staging is marked degraded by this
probe, so `make worktree-create` refused ordinary creation; the branch was cut in the side session's
Claude worktree instead and integration is left to the orchestrator).

## Human authorization

- Request (relayed by the platform-usability orchestrator, 2026-11-25): find out why the `concurrent-memory`
  check in `ops/probe-research-runner-resources.sh` intermittently fails in the staging Exhaustive Integration
  Gate and fix the root cause without weakening what the probe asserts; do not deploy to production.
- Closure authorization: pending (the orchestrator closes and integrates).

## Failure

Staging runs 45438062679, 44882320174, 44856040730 and 44704760479 (all unrelated changes) failed at
`stage=research-runner-probes` / `stage=resources`. The only run with the probe's detailed annotation
(job 138601640216) shows `concurrent-memory: failures=8 restart_before=0 restart_after=1 exits=137 x8`
with `[container oom_killed=true restarts=1 status=restarting]`.

## Root cause

It is OOM victim selection, not per-process caps:

- The service (PID 1) keeps the interpreter plus numpy, pandas, scipy and statsmodels resident: 94 MiB
  anonymous + 62 MiB mapped library pages = about 156 MiB, even when idle (the probe stage runs right after
  stack-up, before any e2e job).
- The memcg OOM killer kills the task with the largest RSS + swap + page tables (+ `oom_score_adj`, which is 0
  for every task). The probe's eight `docker exec` processes grow towards 256 MiB in parallel on one CPU. When
  the cgroup fills before any single one outgrows PID 1 (768 MiB - 156 MiB over eight processes is about
  77 MiB each), PID 1 is the victim. The container dies, Docker kills every exec'd process (all exit 137) and
  `restart: unless-stopped` raises the restart count.
- Locally the probe usually passed only because of swap headroom (Docker's default memory+swap is 2x
  `mem_limit`, so each probe process reached about 260 MiB before the OOM) and staggered `docker exec` starts.
  With `--memory-swap 768m` the unmodified probe failed **6/6** with the exact CI signature; the kernel log
  showed the killed task as the 94 MiB anon / 62 MiB file service process. The hosted runner sits closer to
  that regime, hence the intermittent failures.
- The per-job `RLIMIT_AS` (512 MiB) is applied inside PID 1 only while a job runs and is restored afterwards;
  `docker exec` processes carry no rlimit, so "sum of per-process caps exceeds `mem_limit`" is not the
  mechanism. `mem_limit` (768 MiB) already exceeds the service footprint plus one job cap (156 + 512 MiB).

Why other fixes don't work:

- A container `oom_score_adj` (compose `oom_score_adj:`) is inherited by every `docker exec` process
  (verified: -500 on PID 1 and on exec'd processes), so the ordering is unchanged.
- The service cannot lower its own score (CAP_SYS_RESOURCE is dropped), cannot run jobs in children (seccomp
  denies clone/clone3/fork/vfork) and cannot use threads. Raising its memory or shrinking the probe would
  weaken the guarantee or the test.

## Fix

`backend/research_runner/runner.py`: `prefer_other_processes_for_oom()` raises `oom_score_adj` to 1000 for
every other process in the runner's PID namespace (never its own, never lowering one, ignoring vanished or
foreign-owned processes). Raising another same-uid process's score needs no capability and works under the
seccomp profile and `no-new-privileges`. The idle loop sweeps every 50 ms (job polling stays at 0.25 s), and
running jobs sweep at most every 50 ms through their cancellation check. Under memory pressure the kernel now
kills other processes in the sandbox before the service; the service stays last-resort only.

Unchanged: the probe and its assertions, compose limits, the seccomp profile and job rlimits.

## Validation

- Unmodified probe against the fixed image with `--memory-swap 768m` (failed 6/6 before): **10/10 pass**,
  6-8 processes contained per run, restart count 0.
- Default compose-equivalent config: 5/5 pass. Synchronized-start stress at 0.25 CPU: 5/5 service survived
  (sometimes all eight probe processes killed). Sandbox probe: every escape still denied.
- `test_research_runner.py` + `test_research_runner_deployment.py`: 130 passed. The statsmodels OLS test
  aborts the interpreter on this host on the unmodified tree too (pre-existing local issue, CI unaffected), so
  it was deselected locally.

## Next

Exact-source feature CI, then the orchestrator closes, integrates into staging and runs the Exhaustive
Integration Gate. Production deployment needs the human's explicit approval.
