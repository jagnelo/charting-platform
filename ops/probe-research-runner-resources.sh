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

# The process must be killed by the cgroup rather than surviving a 1 GiB
# allocation in the 768 MiB container. Docker reports SIGKILL as exit 137.
run_expect memory-cgroup 137 '' 'x = bytearray(1024 * 1024 * 1024); print(len(x))'

# The runner's /tmp is a 64 MiB no-exec tmpfs. A 70 MiB write must fail with
# ENOSPC and must not consume host or persistent result volume space.
run_expect tmpfs-capacity 1 'No space left on device' 'open("/tmp/pressure.bin", "wb").write(b"x" * (70 * 1024 * 1024))'

# Clean only the bounded temporary file if the failed write created one.
docker exec "$container" python -c 'import os; os.remove("/tmp/pressure.bin") if os.path.exists("/tmp/pressure.bin") else None' >/dev/null 2>&1 || true
