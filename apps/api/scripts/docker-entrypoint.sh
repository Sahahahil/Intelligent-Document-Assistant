#!/usr/bin/env bash
# Container entrypoint: migrate, then serve.
#
# Alembic owns the schema — the app never creates tables itself, so the
# container and a local `alembic upgrade head` end up with the same schema.
set -euo pipefail

# Postgres may still be starting when this runs. Retry a few times, then give
# up loudly rather than crash-looping on a migration that cannot connect.
for attempt in 1 2 3 4 5; do
    if alembic upgrade head; then
        break
    fi
    if [ "$attempt" -eq 5 ]; then
        echo "alembic upgrade failed after 5 attempts" >&2
        exit 1
    fi
    echo "alembic upgrade failed (attempt ${attempt}); retrying in 2s..." >&2
    sleep 2
done

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
