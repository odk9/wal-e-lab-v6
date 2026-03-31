#!/bin/bash
# =============================================================================
# run_all_tests.sh — Lance 3 sessions Claude Code séquentielles
# Ingestion KB : 13 repos restants de la matrice de test
#
# Usage :
#   cd "/Users/onlydkira/Documents/Genesis One/Wal-e Lab 08-02-2026/Wal-e Lab V6"
#   chmod +x run_all_tests.sh
#   ./run_all_tests.sh
#
# Prérequis :
#   - claude CLI installé et accessible dans PATH
#   - .venv/ avec qdrant-client, fastembed, numpy
#   - Connexion internet (git clone + OpenRouter si besoin)
# =============================================================================

set -e

PROJECT_DIR="/Users/onlydkira/Documents/Genesis One/Wal-e Lab 08-02-2026/Wal-e Lab V6"
LOG_FILE="$PROJECT_DIR/run_all_tests.log"

cd "$PROJECT_DIR"

# ── Empêcher le Mac de dormir pendant l'exécution ─────────────────────────────
# caffeinate -dims : prevent Display sleep, Idle sleep, disk sleep, System sleep
# Le & + trap garantit que caffeinate est tué proprement à la fin (ou si erreur)
caffeinate -dims &
CAFFEINATE_PID=$!
trap "kill $CAFFEINATE_PID 2>/dev/null" EXIT

echo "=============================================" | tee "$LOG_FILE"
echo "  WAL-E LAB V6 — KB TEST MATRIX (13 repos)" | tee -a "$LOG_FILE"
echo "  Started: $(date)" | tee -a "$LOG_FILE"
echo "=============================================" | tee -a "$LOG_FILE"

# ── Session 1 : JS C + TS A/B/C (4 repos) ──────────────────────────────────
echo "" | tee -a "$LOG_FILE"
echo ">>> SESSION 1 : JS C + TS A/B/C — Starting $(date)" | tee -a "$LOG_FILE"
echo "──────────────────────────────────────────────" | tee -a "$LOG_FILE"

cat "$PROJECT_DIR/batch_session_1.md" | claude -p --dangerously-skip-permissions 2>&1 | tee -a "$LOG_FILE"

echo "" | tee -a "$LOG_FILE"
echo ">>> SESSION 1 DONE — $(date)" | tee -a "$LOG_FILE"
echo "──────────────────────────────────────────────" | tee -a "$LOG_FILE"

# ── Session 2 : Go A/B/C (3 repos) ──────────────────────────────────────────
echo "" | tee -a "$LOG_FILE"
echo ">>> SESSION 2 : Go A/B/C — Starting $(date)" | tee -a "$LOG_FILE"
echo "──────────────────────────────────────────────" | tee -a "$LOG_FILE"

cat "$PROJECT_DIR/batch_session_2.md" | claude -p --dangerously-skip-permissions 2>&1 | tee -a "$LOG_FILE"

echo "" | tee -a "$LOG_FILE"
echo ">>> SESSION 2 DONE — $(date)" | tee -a "$LOG_FILE"
echo "──────────────────────────────────────────────" | tee -a "$LOG_FILE"

# ── Session 3 : Rust A/B/C + C++ A/B/C (6 repos) ───────────────────────────
echo "" | tee -a "$LOG_FILE"
echo ">>> SESSION 3 : Rust A/B/C + C++ A/B/C — Starting $(date)" | tee -a "$LOG_FILE"
echo "──────────────────────────────────────────────" | tee -a "$LOG_FILE"

cat "$PROJECT_DIR/batch_session_3.md" | claude -p --dangerously-skip-permissions 2>&1 | tee -a "$LOG_FILE"

echo "" | tee -a "$LOG_FILE"
echo ">>> SESSION 3 DONE — $(date)" | tee -a "$LOG_FILE"
echo "──────────────────────────────────────────────" | tee -a "$LOG_FILE"

# ── Résumé final ─────────────────────────────────────────────────────────────
echo "" | tee -a "$LOG_FILE"
echo "=============================================" | tee -a "$LOG_FILE"
echo "  ALL 3 SESSIONS COMPLETE" | tee -a "$LOG_FILE"
echo "  Finished: $(date)" | tee -a "$LOG_FILE"
echo "=============================================" | tee -a "$LOG_FILE"

# Vérification KB finale
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
