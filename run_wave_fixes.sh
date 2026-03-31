#!/bin/bash
# Re-run ONLY the 11 scripts that failed Charte validation
# Fixes applied: G-1, G-2, R-1, R-2, T-1, T-3, F-1, F-2

cd "$(dirname "$0")"
PYTHON=".venv/bin/python3"
FAILED=0
PASSED=0

echo "=========================================="
echo "  WAL-E V6 — Re-run 11 fixed scripts"
echo "=========================================="
echo ""

for script in \
    ingest_zap.py \
    ingest_transformersjs.py \
    ingest_mcp_ts.py \
    ingest_candle.py \
    ingest_rasa.py \
    ingest_tracing_rs.py \
    ingest_cryptography.py \
    ingest_golearn.py \
    ingest_burn.py \
    ingest_rustcrypto.py \
    ingest_reqwest.py
do
    echo "--- Running $script ---"
    if $PYTHON "$script"; then
        echo "✅ $script OK"
        PASSED=$((PASSED + 1))
    else
        echo "❌ $script FAILED"
        FAILED=$((FAILED + 1))
    fi
    echo ""
done

echo "=========================================="
echo "  Results: $PASSED passed, $FAILED failed"
echo "=========================================="
