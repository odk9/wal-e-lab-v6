#!/bin/bash
# =============================================================================
# run_wave2.sh — Vague 2 : repos moyens (streaming/Instagram/AR/musique)
#
# Scripts : hlsjs, srs, pixelfed, jeeliz, funkwhale
# Total : 5 scripts, ~58 patterns
#
# Usage :
#   cd "/Users/onlydkira/Documents/Genesis One/Wal-e Lab 08-02-2026/Wal-e Lab V6"
#   chmod +x run_wave2.sh
#   ./run_wave2.sh
# =============================================================================

set -uo pipefail

PROJECT_DIR="/Users/onlydkira/Documents/Genesis One/Wal-e Lab 08-02-2026/Wal-e Lab V6"
PYTHON="$PROJECT_DIR/.venv/bin/python3"
LOG_FILE="$PROJECT_DIR/run_wave2.log"

cd "$PROJECT_DIR"

# ── Empêcher le Mac de dormir ─────────────────────────────────────────────────
caffeinate -dims &
CAFFEINATE_PID=$!
trap "kill $CAFFEINATE_PID 2>/dev/null" EXIT

echo "=============================================" | tee "$LOG_FILE"
echo "  WAL-E LAB V6 — VAGUE 2 (Streaming/IG/AR)" | tee -a "$LOG_FILE"
echo "  Started: $(date)"                           | tee -a "$LOG_FILE"
echo "=============================================" | tee -a "$LOG_FILE"

SCRIPTS=(
    "ingest_hlsjs.py"
    "ingest_srs.py"
    "ingest_pixelfed.py"
    "ingest_jeeliz.py"
    "ingest_funkwhale.py"
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
