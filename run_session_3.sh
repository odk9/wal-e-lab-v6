#!/bin/bash
# =============================================================================
# run_session_3.sh — Lance uniquement la Session 3 (Rust A/B/C + C++ A/B/C)
#
# Usage :
#   cd "/Users/onlydkira/Documents/Genesis One/Wal-e Lab 08-02-2026/Wal-e Lab V6"
#   chmod +x run_session_3.sh
#   ./run_session_3.sh
# =============================================================================

set -e

PROJECT_DIR="/Users/onlydkira/Documents/Genesis One/Wal-e Lab 08-02-2026/Wal-e Lab V6"
LOG_FILE="$PROJECT_DIR/run_session_3.log"

cd "$PROJECT_DIR"

# ── Empêcher le Mac de dormir ─────────────────────────────────────────────────
caffeinate -dims &
CAFFEINATE_PID=$!
trap "kill $CAFFEINATE_PID 2>/dev/null" EXIT

echo "=============================================" | tee "$LOG_FILE"
echo "  WAL-E LAB V6 — SESSION 3 (Rust + C++)" | tee -a "$LOG_FILE"
echo "  Started: $(date)" | tee -a "$LOG_FILE"
echo "=============================================" | tee -a "$LOG_FILE"

# ── Session 3 : Rust A/B/C + C++ A/B/C (6 repos) ───────────────────────────
echo "" | tee -a "$LOG_FILE"
echo ">>> SESSION 3 : Rust A/B/C + C++ A/B/C — Starting $(date)" | tee -a "$LOG_FILE"
echo "──────────────────────────────────────────────" | tee -a "$LOG_FILE"

cat "$PROJECT_DIR/batch_session_3.md" | claude -p --dangerously-skip-permissions 2>&1 | tee -a "$LOG_FILE"

echo "" | tee -a "$LOG_FILE"
echo ">>> SESSION 3 DONE — $(date)" | tee -a "$LOG_FILE"
echo "──────────────────────────────────────────────" | tee -a "$LOG_FILE"

# ── Vérification KB finale ────────────────────────────────────────────────────
echo "" | tee -a "$LOG_FILE"
echo ">>> KB FINAL COUNT:" | tee -a "$LOG_FILE"
.venv/bin/python3 -c "
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
echo "Log saved to: $LOG_FILE" | tee -a "$LOG_FILE"
echo "Check FIX_LOG.md for detailed violation/fix report." | tee -a "$LOG_FILE"
