#!/bin/sh
set -eu

# Runtime schema ownership belongs exclusively to Alembic.  FastAPI must never
# call metadata.create_all(), otherwise a fresh deployment is structurally
# unversioned and a later upgrade collides with existing tables.
#
# Migrations are applied only by the API server process (the image's default
# CMD / the compose `backend` service) or when explicitly requested with
# RUN_MIGRATIONS=true.  Any other command (`python some_script.py`, an arq
# worker, a shell) skips them, so a one-off `docker run <image> <cmd>` with a
# production DATABASE_URL can never silently migrate production.
# RUN_MIGRATIONS=false always skips, even for the API server.
is_api_server() {
    case "${1:-}" in
        uvicorn|gunicorn) return 0 ;;
        python|python3)
            [ "${2:-}" = "-m" ] && { [ "${3:-}" = "uvicorn" ] || [ "${3:-}" = "gunicorn" ]; }
            return $?
            ;;
    esac
    return 1
}

case "$(printf '%s' "${RUN_MIGRATIONS:-}" | tr '[:upper:]' '[:lower:]')" in
    true|1|yes) migrate=1 ;;
    false|0|no) migrate=0 ;;
    "") if is_api_server "$@"; then migrate=1; else migrate=0; fi ;;
    *)
        echo "docker-entrypoint: invalid RUN_MIGRATIONS='${RUN_MIGRATIONS}' (use true or false)" >&2
        exit 64
        ;;
esac

if [ "$migrate" = "1" ]; then
    alembic upgrade head
else
    echo "docker-entrypoint: skipping alembic upgrade (not the API server; set RUN_MIGRATIONS=true to force)" >&2
fi

exec "$@"
