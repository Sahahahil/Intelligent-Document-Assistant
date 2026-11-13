#!/usr/bin/env bash
# Initialise and start the local services this project needs:
#   PostgreSQL  -> localhost:5432  (database "document_db", role "document_db")
#   Redis       -> localhost:6379
# Qdrant needs nothing: it runs embedded, on disk, inside the app.
#
# Idempotent: safe to run again at any time.
set -euo pipefail

PGDATA="${PGDATA:-$HOME/.local/share/ida-postgres}"
PGPORT="${PGPORT:-5432}"
REDIS_PORT="${REDIS_PORT:-6379}"
DB_NAME="${DB_NAME:-document_db}"
DB_USER="${DB_USER:-document_db}"
DB_PASSWORD="${DB_PASSWORD:-document_db}"

missing=()
for cmd in initdb pg_ctl psql createdb redis-server; do
    command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
done
if [ ${#missing[@]} -gt 0 ]; then
    echo "Missing binaries: ${missing[*]}" >&2
    echo "Install them first:  sudo pacman -S postgresql redis" >&2
    exit 1
fi

# --- PostgreSQL -------------------------------------------------------------
if [ ! -s "$PGDATA/PG_VERSION" ]; then
    echo "==> initdb $PGDATA"
    initdb -D "$PGDATA" -U postgres --auth=trust >/dev/null
else
    echo "==> cluster already exists at $PGDATA"
fi

if pg_isready -h localhost -p "$PGPORT" >/dev/null 2>&1; then
    echo "==> PostgreSQL already listening on $PGPORT"
else
    echo "==> starting PostgreSQL on $PGPORT"
    pg_ctl -D "$PGDATA" -l "$PGDATA/server.log" -o "-p $PGPORT" start
    for _ in $(seq 1 30); do
        pg_isready -h localhost -p "$PGPORT" >/dev/null 2>&1 && break
        sleep 0.5
    done
fi

if psql -h localhost -p "$PGPORT" -U postgres -tAc \
        "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1; then
    echo "==> role $DB_USER already exists"
else
    echo "==> creating role $DB_USER"
    psql -h localhost -p "$PGPORT" -U postgres -c \
        "CREATE ROLE $DB_USER LOGIN PASSWORD '$DB_PASSWORD'" >/dev/null
fi

if psql -h localhost -p "$PGPORT" -U postgres -tAc \
        "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1; then
    echo "==> database $DB_NAME already exists"
else
    echo "==> creating database $DB_NAME"
    createdb -h localhost -p "$PGPORT" -U postgres -O "$DB_USER" "$DB_NAME"
fi

# --- Redis ------------------------------------------------------------------
if redis-cli -p "$REDIS_PORT" ping >/dev/null 2>&1; then
    echo "==> Redis already listening on $REDIS_PORT"
else
    echo "==> starting Redis on $REDIS_PORT"
    redis-server --daemonize yes --port "$REDIS_PORT" --dir "$PGDATA"
    for _ in $(seq 1 30); do
        redis-cli -p "$REDIS_PORT" ping >/dev/null 2>&1 && break
        sleep 0.5
    done
fi

cat <<EOF

Ready.

  PostgreSQL : postgresql://$DB_USER:$DB_PASSWORD@localhost:$PGPORT/$DB_NAME
  Redis      : redis://localhost:$REDIS_PORT/0
  Qdrant     : embedded, on disk (see QDRANT_PATH in .env)

Next:
  uv sync
  uv run alembic upgrade head
  uv run uvicorn app.main:app --reload
EOF
