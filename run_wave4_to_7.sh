#!/bin/bash
# =============================================================================
# run_wave4_to_7.sh — Waves 4-7 : Auth/Payment/Realtime/Search/Storage/
#                      Email/Cache/Jobs/Monitoring/Deploy
#
# 30 scripts, ~350 patterns, 0 violations
#
# Usage :
#   cd "/Users/onlydkira/Documents/Genesis One/Wal-e Lab 08-02-2026/Wal-e Lab V6"
#   chmod +x run_wave4_to_7.sh
#   ./run_wave4_to_7.sh
# =============================================================================

set -uo pipefail

PROJECT_DIR="/Users/onlydkira/Documents/Genesis One/Wal-e Lab 08-02-2026/Wal-e Lab V6"
PYTHON="$PROJECT_DIR/.venv/bin/python3"
LOG_FILE="$PROJECT_DIR/run_wave4_to_7.log"

cd "$PROJECT_DIR"

# ── Empêcher le Mac de dormir ─────────────────────────────────────────────────
caffeinate -dims &
CAFFEINATE_PID=$!
trap "kill $CAFFEINATE_PID 2>/dev/null" EXIT

echo "=============================================" | tee "$LOG_FILE"
echo "  WAL-E LAB V6 — WAVES 4-7 (30 scripts)"    | tee -a "$LOG_FILE"
echo "  Started: $(date)"                           | tee -a "$LOG_FILE"
echo "=============================================" | tee -a "$LOG_FILE"

SCRIPTS=(
    # Wave 4 — Auth
    "ingest_authlib.py"
    "ingest_passport.py"
    "ingest_goth.py"
    # Wave 4 — Payment
    "ingest_djstripe.py"
    "ingest_stripe_node.py"
    "ingest_async_stripe.py"
    # Wave 4 — Real-time
    "ingest_channels.py"
    "ingest_socketio.py"
    "ingest_gorilla_ws.py"
    # Wave 5 — Search
    "ingest_tantivy.py"
    "ingest_bleve.py"
    "ingest_meilisearch_js.py"
    # Wave 5 — File storage
    "ingest_minio_py.py"
    "ingest_minio_go.py"
    # Wave 5 — Email
    "ingest_fastapi_mail.py"
    "ingest_nodemailer.py"
    "ingest_email_go.py"
    # Wave 6 — Cache
    "ingest_redis_py.py"
    "ingest_go_redis.py"
    "ingest_ioredis.py"
    # Wave 6 — Background jobs
    "ingest_celery.py"
    "ingest_bullmq.py"
    "ingest_asynq.py"
    # Wave 7 — Monitoring
    "ingest_otel_python.py"
    "ingest_otel_go.py"
    "ingest_otel_js.py"
    # Wave 7 — Deploy
    "ingest_compose.py"
    "ingest_pulumi.py"
    "ingest_ansible.py"
)

TOTAL=${#SCRIPTS[@]}
PASSED=0
FAILED=0

for i in "${!SCRIPTS[@]}"; do
    SCRIPT="${SCRIPTS[$i]}"
    NUM=$((i + 1))
    echo "" | tee -a "$LOG_FILE"
    echo ">>> [$NUM/$TOTAL] $SCRIPT — Starting $(date)" | tee -a "$LOG_FILE"
    echo "──────────────────────────────────────────────" | tee -a "$LOG_FILE"

    if "$PYTHON" "$PROJECT_DIR/$SCRIPT" 2>&1 | tee -a "$LOG_FILE"; then
        echo "✅ $SCRIPT — DONE" | tee -a "$LOG_FILE"
        PASSED=$((PASSED + 1))
    else
        echo "❌ $SCRIPT — FAILED (exit code $?)" | tee -a "$LOG_FILE"
        FAILED=$((FAILED + 1))
    fi
done

# ── Vérification KB finale ────────────────────────────────────────────────────
echo "" | tee -a "$LOG_FILE"
echo "=============================================" | tee -a "$LOG_FILE"
echo "  RÉSULTAT: $PASSED/$TOTAL réussis, $FAILED échoués" | tee -a "$LOG_FILE"
echo "=============================================" | tee -a "$LOG_FILE"

echo "" | tee -a "$LOG_FILE"
echo ">>> KB FINAL COUNT:" | tee -a "$LOG_FILE"
"$PYTHON" -c "
from qdrant_client import QdrantClient
c = QdrantClient(path='./kb_qdrant')
total = c.count(collection_name='patterns').count
print(f'Total patterns in KB: {total}')
tags = {}
offset = None
while True:
    result = c.scroll(collection_name='patterns', limit=100, offset=offset, with_payload=True)
    points, next_offset = result
    for p in points:
        tag = p.payload.get('_tag', '?')
        lang = p.payload.get('language', '?')
        key = f'{tag} ({lang})'
        tags[key] = tags.get(key, 0) + 1
    if next_offset is None:
        break
    offset = next_offset
for key, count in sorted(tags.items()):
    print(f'  {key}: {count}')
" 2>&1 | tee -a "$LOG_FILE"

echo "" | tee -a "$LOG_FILE"
echo "Finished: $(date)" | tee -a "$LOG_FILE"
echo "Log saved to: $LOG_FILE" | tee -a "$LOG_FILE"
