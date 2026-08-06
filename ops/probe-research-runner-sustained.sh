#!/usr/bin/env bash

# Sustained but bounded queue-pressure probe for the isolated research runner.
# Each round overlaps a cancelable prepared-universe batch with a successful
# scalar job. It verifies that cancellation is isolated, successful work keeps
# completing, and no progress/cancel/running sentinels survive cleanup.

set -euo pipefail

container="${1:?usage: $0 <research-runner-container>}"
rounds="${TC2000_RUNNER_STRESS_ROUNDS:-5}"

write_job() {
  local job_id="$1" payload="$2"
  local encoded
  encoded="$(printf '%s' "$payload" | base64 | tr -d '\n')"
  docker exec "$container" python -c \
    "import base64,pathlib; pathlib.Path('/jobs/${job_id}.json').write_bytes(base64.b64decode('${encoded}'))"
}

wait_for() {
  local path="$1" attempts="${2:-160}"
  for _ in $(seq 1 "$attempts"); do
    if docker exec "$container" test -e "$path"; then return 0; fi
    sleep 0.1
  done
  echo "timed out waiting for ${path}" >&2
  return 1
}

cleanup_job() {
  local job_id="$1"
  docker exec "$container" python -c \
    "from pathlib import Path; [Path('/jobs/${job_id}.' + suffix).unlink(missing_ok=True) for suffix in ('json','running','processed','cancel')]; [Path('/results/${job_id}.' + suffix).unlink(missing_ok=True) for suffix in ('json','progress.json')]"
}

for round in $(seq 1 "$rounds"); do
  prefix="sustained-${round}-$(date +%s)-$$"
  cancel_job="${prefix}-cancel"
  success_job="${prefix}-success"
  datasets='['
  for index in $(seq 1 600); do
    if [[ "$index" -gt 1 ]]; then datasets+=','; fi
    datasets+="{\"instrument_id\":${index},\"symbol\":\"S${index}\",\"closes\":[1,2,3]}"
  done
  datasets+=']'
  cancel_payload="{\"source\":\"total = 0\\nfor value in range(100000):\\n    total += value\\noutput.scalar('value', total + sum(market.close()))\",\"output_contract\":\"scalar\",\"dataset\":{\"datasets\":${datasets}}}"
  success_payload='{"source":"output.scalar(\"value\", sum(market.close()))","dataset":{"symbol":"SPY","closes":[1,2,3]}}'

  write_job "$cancel_job" "$cancel_payload"
  write_job "$success_job" "$success_payload"
  wait_for "/jobs/${cancel_job}.running"
  sleep 0.2
  docker exec "$container" touch "/jobs/${cancel_job}.cancel"

  wait_for "/jobs/${cancel_job}.processed" 300
  wait_for "/jobs/${success_job}.processed" 300
  cancel_result="$(docker exec "$container" cat "/results/${cancel_job}.json")"
  success_result="$(docker exec "$container" cat "/results/${success_job}.json")"
  if [[ "$cancel_result" != *'"status":"canceled"'* ]]; then
    echo "round ${round}: cancellation was not isolated: ${cancel_result}" >&2
    exit 1
  fi
  if [[ "$success_result" != *'"status":"completed"'* ]]; then
    echo "round ${round}: successful work did not complete: ${success_result}" >&2
    exit 1
  fi
  for suffix in running cancel; do
    if docker exec "$container" test -e "/jobs/${cancel_job}.${suffix}" || docker exec "$container" test -e "/jobs/${success_job}.${suffix}"; then
      echo "round ${round}: stale ${suffix} sentinel remains" >&2
      exit 1
    fi
  done
  if docker exec "$container" test -e "/results/${cancel_job}.progress.json" || docker exec "$container" test -e "/results/${success_job}.progress.json"; then
    echo "round ${round}: stale progress sentinel remains" >&2
    exit 1
  fi
  cleanup_job "$cancel_job"
  cleanup_job "$success_job"
  printf 'round %s/%s: canceled batch isolated and concurrent scalar completed\n' "$round" "$rounds"
done

printf 'sustained runner probe passed: %s bounded cancellation/success rounds\n' "$rounds"
