#!/usr/bin/env bash

# Bounded live crash/recovery probe for the isolated research runner.
# It exercises the real shared-volume protocol: claim a job, terminate only
# the runner container, then verify restart-time orphan recovery completes the
# job without stale cancel/progress residue.

set -euo pipefail

container="${1:?usage: $0 <research-runner-container>}"
job_id="recovery-probe-$(date +%s)-$$"
payload="$(printf '%s' '{"source":"total = 0\nfor i in range(100000000):\n    total += i\noutput.scalar(\"recovered\", total)","dataset":{}}' | base64 | tr -d '\n')"

docker exec "$container" python -c \
  "import base64,pathlib; pathlib.Path('/jobs/${job_id}.json').write_bytes(base64.b64decode('${payload}'))"

running=""
for _ in $(seq 1 80); do
  if docker exec "$container" test -f "/jobs/${job_id}.running"; then
    running=1
    break
  fi
  sleep 0.1
done
if [[ -z "$running" ]]; then
  echo "runner did not claim ${job_id} before the bounded deadline" >&2
  exit 1
fi

started_before="$(docker inspect -f '{{.State.StartedAt}}' "$container")"
docker kill "$container" >/dev/null

for _ in $(seq 1 120); do
  state="$(docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null || true)"
  if [[ "$state" == "false" ]]; then
    break
  fi
  sleep 0.1
done
docker start "$container" >/dev/null

for _ in $(seq 1 160); do
  if docker exec "$container" test -f "/jobs/${job_id}.processed" && \
     docker exec "$container" test -f "/results/${job_id}.json"; then
    break
  fi
  sleep 0.1
done

started_after="$(docker inspect -f '{{.State.StartedAt}}' "$container")"
result="$(docker exec "$container" cat "/results/${job_id}.json" 2>/dev/null || true)"
if [[ "$started_before" == "$started_after" || "$result" != *'"status":"completed"'* || \
      "$(docker exec "$container" test -e "/jobs/${job_id}.cancel"; echo $?)" != "1" || \
      "$(docker exec "$container" test -e "/results/${job_id}.progress.json"; echo $?)" != "1" ]]; then
  printf 'recovery failed: started_before=%s started_after=%s result=%s\n' \
    "$started_before" "$started_after" "$result" >&2
  exit 1
fi

docker exec "$container" python -c \
  "from pathlib import Path; Path('/jobs/${job_id}.processed').unlink(missing_ok=True); Path('/results/${job_id}.json').unlink(missing_ok=True)"
printf 'recovery: orphaned job %s completed after isolated runner restart (%s -> %s)\n' \
  "$job_id" "$started_before" "$started_after"
