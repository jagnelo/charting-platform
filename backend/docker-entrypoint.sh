#!/bin/sh
set -eu

# Runtime schema ownership belongs exclusively to Alembic.  FastAPI must never
# call metadata.create_all(), otherwise a fresh deployment is structurally
# unversioned and a later upgrade collides with existing tables.
alembic upgrade head

exec "$@"
