#!/usr/bin/env bash

# Bounded live resource-pressure probes for the isolated research runner.
# These probes intentionally run inside the branch-scoped container and accept
# only the expected kernel/cgroup failure modes. They never write to the host.

set -euo pipefail

container="${1:?usage: $0 <research-runner-container>}"

config="$(docker inspect -f 'memory={{.HostConfig.Memory}} nano_cpus={{.HostConfig.NanoCpus}} pids={{.HostConfig.PidsLimit}} network={{.HostConfig.NetworkMode}} readonly={{.HostConfig.ReadonlyRootfs}} uid={{.Config.User}}' "$container")"
case "$config" in
  *"memory=805306368"*"nano_cpus=1000000000"*"pids=128"*"network=none"*"readonly=true"*"uid=10001:10001"*) ;;
  *) echo "unexpected resource/isolation configuration: $config" >&2; exit 1 ;;
esac
printf 'configuration: %s\n' "$config"

run_expect() {
  local name="$1" expected_status="$2" expected_text="$3" code="$4"
  local output rc
  set +e
  output="$(docker exec "$container" python -c "$code" 2>&1)"
  rc=$?
  set -e
  if [[ "$rc" -ne "$expected_status" || "$output" != *"$expected_text"* ]]; then
    printf '%s: unexpected status=%s output=%s\n' "$name" "$rc" "$output" >&2
    exit 1
  fi
  printf '%s: denied (status=%s)\n' "$name" "$rc"
}

# The process must be killed by the cgroup rather than surviving a 2 GiB
# allocation in the 768 MiB container. (A nominal 1 GiB Python allocation can
# remain below the effective resident limit because the allocator does not
# fault every requested page.) Write every page so the allocation is resident
# RSS rather than merely virtual address space; Docker reports SIGKILL as exit
# 137 when the memory limit is enforced. Reading untouched zero pages is not
# sufficient on Linux: the kernel may satisfy those reads from the shared zero
# page and a hosted runner can otherwise let the probe exit 0.
run_expect memory-cgroup 137 '' 'x = bytearray(2 * 1024 * 1024 * 1024); [x.__setitem__(offset, 1) for offset in range(0, len(x), 4096)]; print(len(x))'

# The runner's /tmp is a 64 MiB no-exec tmpfs. A 70 MiB write must fail with
# ENOSPC and must not consume host or persistent result volume space.
run_expect tmpfs-capacity 1 'No space left on device' 'open("/tmp/pressure.bin", "wb").write(b"x" * (70 * 1024 * 1024))'

# Clean only the bounded temporary file if the failed write created one.
docker exec "$container" python -c 'import os; os.remove("/tmp/pressure.bin") if os.path.exists("/tmp/pressure.bin") else None' >/dev/null 2>&1 || true

# Exercise aggregate cgroup pressure with eight short-lived processes. At
# least one process must be contained/killed, while the service itself must not
# restart. The probe intentionally uses bounded 128 MiB allocations and sleeps
# only three seconds; it cannot create an unbounded workload.
restart_before="$(docker inspect -f '{{.RestartCount}}' "$container")"
pids=()
for index in 1 2 3 4 5 6 7 8; do
  docker exec "$container" python -c 'import time; x=bytearray(256 * 1024 * 1024); [x.__setitem__(offset, 1) for offset in range(0, len(x), 4096)]; time.sleep(3)' \
    >"/tmp/tc2000-resource-pressure-${index}.log" 2>&1 &
  pids+=("$!")
done
failures=0
for pid in "${pids[@]}"; do
  if ! wait "$pid"; then failures=$((failures + 1)); fi
done
restart_after="$(docker inspect -f '{{.RestartCount}}' "$container")"
rm -f /tmp/tc2000-resource-pressure-*.log
if [[ "$failures" -lt 1 || "$restart_before" != "$restart_after" ]]; then
  printf 'concurrent-memory: unexpected failures=%s restart_before=%s restart_after=%s\n' \
    "$failures" "$restart_before" "$restart_after" >&2
  exit 1
fi
printf 'concurrent-memory: contained %s process failure(s), restart count unchanged (%s)\n' \
  "$failures" "$restart_after"
