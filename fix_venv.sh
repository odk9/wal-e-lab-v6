#!/bin/bash
# =============================================================================
# fix_venv.sh — Diagnostique et répare le venv pour les scripts d'ingestion
#
# Usage :
#   cd "/Users/onlydkira/Documents/Genesis One/Wal-e Lab 08-02-2026/Wal-e Lab V6"
#   chmod +x fix_venv.sh
#   ./fix_venv.sh
# =============================================================================

set -uo pipefail

PROJECT_DIR="/Users/onlydkira/Documents/Genesis One/Wal-e Lab 08-02-2026/Wal-e Lab V6"
PYTHON="$PROJECT_DIR/.venv/bin/python3"
PIP="$PROJECT_DIR/.venv/bin/pip"

echo "============================================="
echo "  DIAGNOSTIC VENV — WAL-E LAB V6"
echo "============================================="

# ── 1. Vérifier que le venv existe ──────────────────────────────────────────
echo ""
echo ">>> 1. Vérification du venv..."
if [ ! -f "$PYTHON" ]; then
    echo "❌ Python introuvable: $PYTHON"
    echo "   → Recréation du venv..."
    python3 -m venv "$PROJECT_DIR/.venv" --clear
    echo "   ✅ Venv recréé"
else
    echo "✅ Python trouvé: $PYTHON"
fi

# ── 2. Vérifier la version Python ───────────────────────────────────────────
echo ""
echo ">>> 2. Version Python..."
"$PYTHON" --version 2>&1

# ── 3. Vérifier le symlink ──────────────────────────────────────────────────
echo ""
echo ">>> 3. Symlink Python..."
ls -la "$PYTHON" 2>&1
REAL_PYTHON=$(readlink -f "$PYTHON" 2>/dev/null || python3 -c "import os; print(os.path.realpath('$PYTHON'))")
echo "   Pointe vers: $REAL_PYTHON"
if [ ! -f "$REAL_PYTHON" ]; then
    echo "❌ Le symlink est cassé! La cible n'existe plus."
    echo "   → Recréation du venv..."
    python3 -m venv "$PROJECT_DIR/.venv" --clear
    echo "   ✅ Venv recréé"
fi

# ── 4. Vérifier les packages critiques ──────────────────────────────────────
echo ""
echo ">>> 4. Test import qdrant_client..."
if "$PYTHON" -c "import qdrant_client; print(f'  qdrant_client {qdrant_client.__version__}')" 2>&1; then
    echo "✅ qdrant_client OK"
else
    echo "❌ qdrant_client MANQUANT — installation..."
    "$PIP" install qdrant-client
    echo "   ✅ qdrant_client installé"
fi

echo ""
echo ">>> 5. Test import fastembed..."
if "$PYTHON" -c "import fastembed; print(f'  fastembed OK')" 2>&1; then
    echo "✅ fastembed OK"
else
    echo "❌ fastembed MANQUANT — installation..."
    "$PIP" install fastembed
    echo "   ✅ fastembed installé"
fi

echo ""
echo ">>> 6. Test import numpy..."
if "$PYTHON" -c "import numpy; print(f'  numpy {numpy.__version__}')" 2>&1; then
    echo "✅ numpy OK"
else
    echo "❌ numpy MANQUANT — installation..."
    "$PIP" install numpy
    echo "   ✅ numpy installé"
fi

# ── 5. Test complet : simuler un import comme les scripts d'ingestion ───────
echo ""
echo ">>> 7. Test complet (simule un script d'ingestion)..."
"$PYTHON" -c "
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue, PointStruct
print('  ✅ Tous les imports OK')
c = QdrantClient(path='./kb_qdrant')
total = c.count(collection_name='patterns').count
print(f'  KB actuelle: {total} patterns')
" 2>&1

if [ $? -eq 0 ]; then
    echo ""
    echo "============================================="
    echo "  ✅ VENV OK — Prêt pour run_wave4_to_7.sh"
    echo "============================================="
else
    echo ""
    echo "============================================="
    echo "  ❌ PROBLÈME PERSISTANT"
    echo "  Essayer: python3 -m venv .venv --clear"
    echo "  Puis: .venv/bin/pip install qdrant-client fastembed numpy"
    echo "============================================="
fi
