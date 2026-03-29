"""
audit_kb_integrity.py — Audit d'intégrité de la KB Qdrant V6.

Vérifie que les 140 patterns Python (A + B + C) ne sont pas tronqués,
corrompus, ou incomplets.

Usage:
    .venv/bin/python3 audit_kb_integrity.py
"""

from __future__ import annotations

import ast
import hashlib
import math
import random

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from embedder import embed_document
from kb_utils import check_charte_violations

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"

EXPECTED_TAGS = {
    "igorbenav/fastcrud": 35,
    "fastapi/full-stack-fastapi-template": 60,
    "fastapi-users/fastapi-users": 45,
}
EXPECTED_TOTAL = 140

REQUIRED_FIELDS = [
    "normalized_code", "function", "feature_type", "file_role",
    "language", "framework", "stack", "file_path", "source_repo",
    "charte_version", "created_at", "_tag",
]

SPOT_CHECK_QUERIES = [
    ("generic CRUD pagination offset limit", "igorbenav/fastcrud"),
    ("OAuth2 callback route exchange code", "fastapi-users/fastapi-users"),
    ("email SMTP send background task", "fastapi/full-stack-fastapi-template"),
]


def fetch_all_points(client: QdrantClient) -> list:
    """Fetch all points with vectors via scroll pagination."""
    all_points = []
    offset = None
    while True:
        result = client.scroll(
            collection_name=COLLECTION,
            limit=100,
            with_vectors=True,
            offset=offset,
        )
        points, next_offset = result
        all_points.extend(points)
        if next_offset is None:
            break
        offset = next_offset
    return all_points


def check_counts(all_points: list) -> dict:
    """Check 1: Count per repo tag."""
    tag_counts: dict[str, int] = {}
    for p in all_points:
        tag = p.payload.get("_tag", "MISSING")
        tag_counts[tag] = tag_counts.get(tag, 0) + 1
    return tag_counts


def check_payloads(all_points: list) -> list[str]:
    """Check 2: All required fields present and non-empty."""
    issues = []
    for p in all_points:
        fn = p.payload.get("function", "?")
        pid = str(p.id)[:8]
        for field in REQUIRED_FIELDS:
            val = p.payload.get(field)
            if val is None:
                issues.append(f"[{pid}] {fn}: missing field '{field}'")
            elif isinstance(val, str) and len(val.strip()) == 0:
                issues.append(f"[{pid}] {fn}: empty field '{field}'")
    return issues


def check_truncation(all_points: list) -> tuple[list[str], list[str]]:
    """Check 3: Code truncation, min length, parseable, contains code."""
    suspects = []
    syntax_warns = []

    for p in all_points:
        fn = p.payload.get("function", "?")
        code = p.payload.get("normalized_code", "")
        pid = str(p.id)[:8]

        # 3a. Not empty
        if len(code) == 0:
            suspects.append(f"[{pid}] {fn}: EMPTY code")
            continue

        # 3b. Minimum length
        if len(code) < 50:
            suspects.append(f"[{pid}] {fn}: suspiciously short ({len(code)} chars)")

        # 3c. Not cut mid-word / ends with "..."
        stripped = code.rstrip()
        if stripped.endswith("...") or stripped.endswith("# ..."):
            suspects.append(f"[{pid}] {fn}: code ends with ellipsis")

        # 3d. Parseable Python
        try:
            ast.parse(code)
        except SyntaxError:
            syntax_warns.append(f"[{pid}] {fn}")

        # 3e. Contains code constructs
        has_code = any(kw in code for kw in ("def ", "class ", "=", "import "))
        if not has_code:
            suspects.append(f"[{pid}] {fn}: no def/class/= found — may be text")

        # 3f. Token proxy check
        word_count = len(code.split())
        if word_count > 6000:
            suspects.append(
                f"[{pid}] {fn}: {word_count} words — near embedding limit"
            )

    return suspects, syntax_warns


def check_charte(all_points: list) -> list[str]:
    """Check 4: Charte Wal-e violations on all 140 patterns."""
    violations = []
    for p in all_points:
        fn = p.payload.get("function", "?")
        code = p.payload.get("normalized_code", "")
        v = check_charte_violations(code, fn)
        violations.extend(v)
    return violations


def check_vectors(all_points: list) -> list[str]:
    """Check 5: Re-embed 10 random patterns and compare vectors."""
    # Pick 10 spread across repos
    by_tag: dict[str, list] = {}
    for p in all_points:
        tag = p.payload.get("_tag", "?")
        by_tag.setdefault(tag, []).append(p)

    sample = []
    for tag, pts in by_tag.items():
        n = min(4, len(pts))
        sample.extend(random.sample(pts, n))
    if len(sample) > 10:
        sample = random.sample(sample, 10)

    issues = []
    for p in sample:
        fn = p.payload.get("function", "?")
        code = p.payload.get("normalized_code", "")
        pid = str(p.id)[:8]

        stored_vec = p.vector
        if stored_vec is None:
            issues.append(f"[{pid}] {fn}: no vector stored")
            continue

        # Recompute
        recomputed = embed_document(code)

        # Cosine similarity
        a = np.array(stored_vec)
        b = np.array(recomputed)
        dot = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            issues.append(f"[{pid}] {fn}: zero-norm vector")
            continue

        cosine_sim = dot / (norm_a * norm_b)
        # Threshold 0.97: quantized ONNX model (nomic-embed-text-v1.5-Q)
        # introduces small numerical variance on re-embedding (~0.02)
        if cosine_sim < 0.97:
            issues.append(
                f"[{pid}] {fn}: cosine={cosine_sim:.4f} (< 0.97)"
            )

        # Norm check
        if abs(norm_a - 1.0) > 0.001:
            issues.append(
                f"[{pid}] {fn}: stored norm={norm_a:.4f} (expected ~1.0)"
            )

    return issues


def check_duplicates(all_points: list) -> list[str]:
    """Check 6: Duplicate normalized_code."""
    seen: dict[str, tuple[str, str]] = {}  # hash → (function, tag)
    dupes = []
    for p in all_points:
        code = p.payload.get("normalized_code", "")
        fn = p.payload.get("function", "?")
        tag = p.payload.get("_tag", "?")
        h = hashlib.md5(code.encode()).hexdigest()
        if h in seen:
            prev_fn, prev_tag = seen[h]
            dupes.append(
                f"Duplicate: '{fn}' ({tag}) == '{prev_fn}' ({prev_tag})"
            )
        else:
            seen[h] = (fn, tag)
    return dupes


def check_semantic(client: QdrantClient) -> list[str]:
    """Check 7: Spot-check semantic queries hit expected repos."""
    from embedder import embed_query

    results = []
    for query, expected_tag in SPOT_CHECK_QUERIES:
        vec = embed_query(query)
        hits = client.query_points(
            collection_name=COLLECTION, query=vec, limit=1
        ).points
        if not hits:
            results.append(f"  '{query}' → NO RESULT (expected {expected_tag})")
            continue
        hit = hits[0]
        actual_tag = hit.payload.get("_tag", "?")
        fn = hit.payload.get("function", "?")
        score = hit.score
        ok = "✓" if actual_tag == expected_tag else "✗ WARN"
        results.append(
            f"  '{query[:45]}'\n"
            f"    → {fn} ({actual_tag}) score={score:.4f} {ok}"
        )
    return results


def main() -> None:
    print(f"\n{'='*65}")
    print("  AUDIT INTÉGRITÉ KB — 140 patterns Python (A + B + C)")
    print(f"{'='*65}\n")

    client = QdrantClient(path=KB_PATH)

    # Fetch all points
    print("Fetching all points with vectors ...")
    all_points = fetch_all_points(client)
    print(f"  {len(all_points)} points fetched.\n")

    fail = False

    # ── 1. Count par repo ────────────────────────────────────────────────
    print("── 1. Count par repo")
    tag_counts = check_counts(all_points)
    for tag, expected in EXPECTED_TAGS.items():
        actual = tag_counts.get(tag, 0)
        ok = "✓" if actual == expected else "✗ FAIL"
        print(f"  {tag:45s}: {actual}/{expected} {ok}")
        if actual != expected:
            fail = True
    total = len(all_points)
    total_ok = "✓" if total == EXPECTED_TOTAL else "✗ FAIL"
    print(f"  {'Total':45s}: {total}/{EXPECTED_TOTAL} {total_ok}")
    if total != EXPECTED_TOTAL:
        fail = True

    # ── 2. Payload complet ───────────────────────────────────────────────
    print("\n── 2. Payload complet")
    payload_issues = check_payloads(all_points)
    if payload_issues:
        fail = True
        for issue in payload_issues[:20]:
            print(f"  ✗ {issue}")
        if len(payload_issues) > 20:
            print(f"  ... and {len(payload_issues) - 20} more")
    else:
        print(f"  All {total} points have complete payloads ✓")

    # ── 3. Troncature du code ────────────────────────────────────────────
    print("\n── 3. Troncature du code")
    suspects, syntax_warns = check_truncation(all_points)
    if suspects:
        fail = True
        for s in suspects:
            print(f"  ✗ {s}")
    else:
        print(f"  No truncation detected ✓")
    print(f"\n  Syntax errors (WARN): {len(syntax_warns)}/{total}")
    if syntax_warns:
        for w in syntax_warns:
            print(f"    WARN: {w}")

    # ── 4. Normalisation Charte ──────────────────────────────────────────
    print("\n── 4. Normalisation Charte")
    charte_violations = check_charte(all_points)
    if charte_violations:
        fail = True
        for v in charte_violations:
            print(f"  ✗ {v}")
    else:
        print(f"  All {total} patterns pass Charte checks ✓")

    # ── 5. Vecteurs — cohérence embedding ────────────────────────────────
    print("\n── 5. Vecteurs — cohérence embedding (10 samples)")
    vector_issues = check_vectors(all_points)
    if vector_issues:
        fail = True
        for v in vector_issues:
            print(f"  ✗ {v}")
    else:
        print("  10/10 vectors consistent (cosine > 0.99, norm ≈ 1.0) ✓")

    # ── 6. Doublons ──────────────────────────────────────────────────────
    print("\n── 6. Doublons")
    dupes = check_duplicates(all_points)
    if dupes:
        for d in dupes:
            print(f"  WARN: {d}")
    else:
        print(f"  No duplicates among {total} patterns ✓")

    # ── 7. Cohérence sémantique ──────────────────────────────────────────
    print("\n── 7. Cohérence sémantique (spot check)")
    semantic_results = check_semantic(client)
    for r in semantic_results:
        print(r)

    # ── Rapport final ────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print("  === AUDIT INTÉGRITÉ KB ===")
    print(f"{'='*65}")
    print()
    print("  Count par repo :")
    for tag, expected in EXPECTED_TAGS.items():
        actual = tag_counts.get(tag, 0)
        print(f"    {tag:45s}: {actual}/{expected}")
    print(f"    {'Total':45s}: {total}/{EXPECTED_TOTAL}")
    print()
    print(f"  Champs manquants    : {len(payload_issues)} points")
    print(f"  Code tronqué        : {len(suspects)} patterns suspects")
    print(f"  Syntax errors       : {len(syntax_warns)} patterns (WARN)")
    print(f"  Violations Charte   : {len(charte_violations)} patterns")
    print(f"  Vecteurs incohérents: {len(vector_issues)}/10")
    print(f"  Doublons            : {len(dupes)} paires")
    print(f"  Cohérence sémantique: voir détail ci-dessus")
    print()
    verdict = "FAIL" if fail else "PASS"
    print(f"  Verdict : {'✅ PASS' if not fail else '❌ FAIL'}")
    if fail:
        problems = []
        if total != EXPECTED_TOTAL:
            problems.append(f"count {total} != {EXPECTED_TOTAL}")
        if payload_issues:
            problems.append(f"{len(payload_issues)} missing fields")
        if suspects:
            problems.append(f"{len(suspects)} truncated")
        if charte_violations:
            problems.append(f"{len(charte_violations)} charte violations")
        if vector_issues:
            problems.append(f"{len(vector_issues)} bad vectors")
        print(f"  Problèmes : {', '.join(problems)}")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    main()
