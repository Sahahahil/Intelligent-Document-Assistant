#!/usr/bin/env bash
# End-to-end smoke test: boots the Compose stack and drives both APIs.
#
#   scripts/smoke.sh            build, boot, check, tear down
#   scripts/smoke.sh --keep     ...and leave the stack running
#
# Needs: docker, curl, python3. An LLM key is optional - without one the
# chat turn is expected to answer 502 (the API is up, the upstream is not),
# which still passes.
#
# The script manages the Compose stack in this directory: it stops it when
# it finishes. The data survives - the volumes are kept.
set -euo pipefail

cd "$(dirname "$0")/.."

if docker compose version >/dev/null 2>&1; then
    COMPOSE=(docker compose)
else
    COMPOSE=(docker-compose)
fi

API="${SMOKE_API_URL:-http://localhost:8000}"
KEEP=0
if [ "${1:-}" = "--keep" ]; then KEEP=1; fi

WORK="$(mktemp -d)"

step() { printf '\n==> %s\n' "$1"; }
fail() { printf '\nFAIL: %s\n' "$1" >&2; exit 1; }

cleanup() {
    rm -rf "$WORK"
    if [ "$KEEP" -eq 0 ]; then
        step "Stopping the stack"
        "${COMPOSE[@]}" down >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

# request <method> <path> [json-body] - prints the status code, body in $WORK/body
request() {
    local method="$1" path="$2" body="${3:-}"
    if [ -n "$body" ]; then
        curl -sS --max-time 300 -o "$WORK/body" -w '%{http_code}' \
            -X "$method" "$API$path" -H 'Content-Type: application/json' -d "$body"
    else
        curl -sS --max-time 300 -o "$WORK/body" -w '%{http_code}' -X "$method" "$API$path"
    fi
}

step "Building and starting the stack"
"${COMPOSE[@]}" up -d --build

step "Waiting for the API to become ready"
for _ in $(seq 1 60); do
    curl -fsS --max-time 5 "$API/ready" >/dev/null 2>&1 && break
    sleep 2
done
READY="$(curl -fsS --max-time 10 "$API/ready" 2>/dev/null || true)"
case "$READY" in
    *'"status":"ready"'*) printf '%s\n' "$READY" ;;
    *) fail "the API never became ready: ${READY:-no answer}" ;;
esac

step "Liveness probe"
HEALTH="$(curl -fsS --max-time 10 "$API/health")"
case "$HEALTH" in
    *'"status":"ok"'*) printf '%s\n' "$HEALTH" ;;
    *) fail "/health did not answer ok: $HEALTH" ;;
esac

# --- API 1: document ingestion ---------------------------------------------
step "API 1 - ingesting a document"
printf 'The quarterly review is scheduled for the fifteenth of the month.\n' > "$WORK/smoke.txt"
INGEST_CODE="$(curl -sS --max-time 300 -o "$WORK/body" -w '%{http_code}' \
    -X POST "$API/api/v1/documents/ingest" \
    -F "file=@$WORK/smoke.txt;type=text/plain" \
    -F "chunking_strategy=recursive")"
INGEST="$(cat "$WORK/body")"
printf '%s\n' "$INGEST"
[ "$INGEST_CODE" = "201" ] || fail "the ingest failed (HTTP $INGEST_CODE)"
DOC_ID="$(printf '%s' "$INGEST" | python3 -c 'import json,sys; print(json.load(sys.stdin)["document_id"])')"

step "API 1 - the document is listed"
DOCUMENTS="$(curl -fsS "$API/api/v1/documents?limit=10")"
case "$DOCUMENTS" in
    *"$DOC_ID"*) printf 'listed %s\n' "$DOC_ID" ;;
    *) fail "the document is not listed: $DOCUMENTS" ;;
esac

# --- API 2: conversational RAG ---------------------------------------------
step "API 2 - a blank message is rejected"
BLANK_CODE="$(request POST /api/v1/chat '{"session_id": "smoke", "message": "   "}')"
BLANK="$(cat "$WORK/body")"
printf '%s\n' "$BLANK"
[ "$BLANK_CODE" = "422" ] || fail "a blank message should be rejected (HTTP $BLANK_CODE)"
case "$BLANK" in
    *'"code":"validation_error"'*) ;;
    *) fail "the blank message did not use the error envelope: $BLANK" ;;
esac

step "API 2 - a question"
LLM_KEY="$("${COMPOSE[@]}" exec -T api printenv LLM_API_KEY 2>/dev/null | tr -d '\r\n' || true)"
CHAT_CODE="$(request POST /api/v1/chat '{"session_id": "smoke", "message": "When is the quarterly review?"}')"
CHAT="$(cat "$WORK/body")"
printf '%s\n' "$CHAT"
if [ -n "$LLM_KEY" ]; then
    [ "$CHAT_CODE" = "200" ] || fail "the chat turn failed (HTTP $CHAT_CODE)"
else
    # No LLM key: the API is up and the upstream is not - that is the 502 path.
    [ "$CHAT_CODE" = "502" ] || fail "without an LLM key the chat should be 502 (HTTP $CHAT_CODE)"
    printf 'no LLM key - the upstream failure was the expected 502\n'
fi

step "API 1 - deleting the document"
curl -fsS -o /dev/null -X DELETE "$API/api/v1/documents/$DOC_ID"
printf 'deleted %s\n' "$DOC_ID"

# --- the bookings that were stored -----------------------------------------
step "API 2 - a stored booking is read back"
"${COMPOSE[@]}" exec -T postgres psql -U document_db -d document_db -q -c \
    "INSERT INTO bookings (session_id, name, email, interview_date, interview_time, status)
     VALUES ('smoke', 'Smoke Test', 'smoke@example.com', CURRENT_DATE + 1, '14:00', 'confirmed')
     ON CONFLICT DO NOTHING;"
BOOKINGS="$(curl -fsS "$API/api/v1/bookings?email=smoke@example.com")"
case "$BOOKINGS" in
    *'smoke@example.com'*) printf '%s\n' "$BOOKINGS" ;;
    *) fail "the booking is not listed: $BOOKINGS" ;;
esac

printf '\nSMOKE TEST PASSED\n'
