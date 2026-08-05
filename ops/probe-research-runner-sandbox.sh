#!/usr/bin/env bash
set -euo pipefail

container="${1:?usage: $0 <research-runner-container>}"

security_json="$(docker inspect -f '{{json .HostConfig.SecurityOpt}}' "$container")"
case "$security_json" in
  *no-new-privileges*seccomp=*|*seccomp=*no-new-privileges*) ;;
  *) echo "missing no-new-privileges/seccomp profile: $security_json" >&2; exit 1 ;;
esac

probe() {
  local name="$1" expected="$2" code="$3" output status
  set +e
  output="$(docker exec "$container" python -c "$code" 2>&1)"
  status=$?
  set -e
  if [[ "$output" != *"$expected"* ]]; then
    printf '%s: unexpected status=%s output=%s\n' "$name" "$status" "$output" >&2
    exit 1
  fi
  printf '%s: denied (status=%s)\n' "$name" "$status"
}

probe unshare '-1 1' 'import ctypes; x=ctypes.CDLL(None,use_errno=True).unshare(0x10000000); print(x,ctypes.get_errno())'
probe setns '-1 1' 'import ctypes,os; f=os.open("/proc/self/ns/mnt",0); x=ctypes.CDLL(None,use_errno=True).setns(f,0); print(x,ctypes.get_errno())'
probe mount '-1 1' 'import ctypes; x=ctypes.CDLL(None,use_errno=True).mount(b"none",b"/tmp",b"tmpfs",0,None); print(x,ctypes.get_errno())'
probe ptrace '-1 1' 'import ctypes; x=ctypes.CDLL(None,use_errno=True).ptrace(0,0,0,0); print(x,ctypes.get_errno())'
probe fork 'Operation not permitted' 'import os; os.fork()'
probe network '101' 'import socket; s=socket.socket(); s.settimeout(1); print(s.connect_ex(("1.1.1.1",80)))'
probe subprocess 'Operation not permitted' 'import subprocess; subprocess.run(["id"],check=True)'
probe root-write 'Read-only file system' 'open("/runner/escape","w").write("x")'
