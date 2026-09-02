#!/usr/bin/env bash

# Retry only transient dependency/bootstrap commands. Test, build, migration,
# lint, and application failures must be invoked directly so they remain red.
set -u -o pipefail

if [[ "${1:-}" != "--" || $# -lt 2 ]]; then
  echo "usage: scripts/ci-retry.sh -- command [args...]" >&2
  exit 2
fi
shift

max_attempts="${CI_RETRY_MAX_ATTEMPTS:-3}"
backoffs="${CI_RETRY_BACKOFF_SECONDS:-10 30}"
attempt=1
status=0

while (( attempt <= max_attempts )); do
  echo "::group::retryable setup attempt ${attempt}/${max_attempts}"
  "$@"
  status=$?
  echo "::endgroup::"
  if (( status == 0 )); then
    exit 0
  fi
  if (( attempt == max_attempts )); then
    echo "setup command failed after ${max_attempts} attempts (exit ${status})" >&2
    exit "$status"
  fi
  delay="0"
  if (( attempt == 1 )); then
    delay="${backoffs%% *}"
  else
    delay="${backoffs##* }"
  fi
  echo "setup command failed on attempt ${attempt}; retrying in ${delay}s" >&2
  sleep "$delay"
  attempt=$((attempt + 1))
done

exit "$status"
