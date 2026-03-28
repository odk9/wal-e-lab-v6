"""
ingestor.py — Pipeline KB complet : Scanner → Extracteur → Normaliseur → Qdrant.

Usage:
    cd kb/
    source .venv/bin/activate
    python ingestor.py [--priority-only] [--skip-scan] [--max-repos N]

Options:
    --priority-only  : ne traite que les repos marqués priority="priority"
    --skip-scan      : saute le téléchargement (raw_repos/ déjà présent)
    --max-repos N    : limite à N repos (pour tests)
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from embedder import embed
from extractor import RawPattern, extract_patterns_from_repo
from normalizer import CHARTE_VERSION, normalize_pattern
from repos import ALL_REPOS, PRIORITY_REPOS
from scanner import scan_all

KB_PATH = "./kb_qdrant"
RAW_REPOS_DIR = Path("./raw_repos")


def _build_embedding_text(pattern: RawPattern) -> str:
    """Construit le texte à embedder pour un pattern."""
    return (
        f"{pattern.feature_type} {pattern.framework} {pattern.language} "
        f"{pattern.file_role} {pattern.raw_code[:500]}"
    )


def ingest_pattern(
    client: QdrantClient,
    pattern: RawPattern,
    normalized_code: str,
) -> bool:
    """
    Insère un pattern normalisé dans Qdrant.

    Returns:
        True si succès, False sinon
    """
    try:
        text = _build_embedding_text(pattern)
        vector = embed(text)

        point = PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload={
                "feature_type": pattern.feature_type,
                "framework": pattern.framework,
                "language": pattern.language,
                "file_role": pattern.file_role,
                "normalized_code": normalized_code,
                "source_repo": pattern.source_repo,
                "source_file": pattern.source_file,
                "charte_version": CHARTE_VERSION,
                "created_at": int(time.time()),
            },
        )

        client.upsert(collection_name="patterns", points=[point])
        return True

    except Exception as e:
        print(f"  ❌ Erreur upsert : {e}")
        return False


def run_ingestion(
    priority_only: bool = False,
    skip_scan: bool = False,
    max_repos: int | None = None,
) -> None:
    """
    Lance le pipeline KB complet.
    """
    print("=" * 60)
    print("WAL-E LAB V6 — KB Building Pipeline")
    print("=" * 60)

    # --- Étape 1 : Scanner ---
    if not skip_scan:
        print("\n[1/3] Scanner — Téléchargement des repos...")
        repo_list = PRIORITY_REPOS if priority_only else ALL_REPOS
        if max_repos:
            repo_list = repo_list[:max_repos]
        scan_all(repo_list, priority_only=False)  # déjà filtré
    else:
        print("\n[1/3] Scanner — skip (--skip-scan)")

    # --- Étape 2 : Extracteur ---
    print("\n[2/3] Extracteur — Extraction des patterns...")
    repo_dirs = sorted(RAW_REPOS_DIR.rglob("*"))
    repo_dirs = [d for d in repo_dirs if d.is_dir() and d.parent != RAW_REPOS_DIR]

    if max_repos:
        repo_dirs = repo_dirs[:max_repos]

    all_patterns: list[RawPattern] = []
    for repo_dir in repo_dirs:
        patterns = extract_patterns_from_repo(repo_dir)
        all_patterns.extend(patterns)
        time.sleep(0.1)

    print(f"\n  Total patterns extraits : {len(all_patterns)}")

    # --- Étape 3 : Normaliseur + Upsert Qdrant ---
    print("\n[3/3] Normaliseur + Qdrant — Normalisation et indexation...")
    client = QdrantClient(path=KB_PATH)

    success = 0
    skipped = 0
    errors = 0

    for i, pattern in enumerate(all_patterns):
        if i % 10 == 0:
            print(f"  Progression : {i}/{len(all_patterns)}...")

        normalized_code = normalize_pattern(pattern)

        if normalized_code is None:
            # Fallback : utiliser le code brut si le normaliseur échoue
            normalized_code = pattern.raw_code
            skipped += 1

        ok = ingest_pattern(client, pattern, normalized_code)
        if ok:
            success += 1
        else:
            errors += 1

        time.sleep(0.05)  # rate limit OpenRouter

    # --- Résumé ---
    total = client.count("patterns").count
    print("\n" + "=" * 60)
    print(f"✅ Ingestion terminée")
    print(f"   Patterns ingérés  : {success}")
    print(f"   Code brut (fallback) : {skipped}")
    print(f"   Erreurs           : {errors}")
    print(f"   Total KB patterns : {total}")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="KB Building Pipeline V6")
    parser.add_argument("--priority-only", action="store_true")
    parser.add_argument("--skip-scan", action="store_true")
    parser.add_argument("--max-repos", type=int, default=None)
    args = parser.parse_args()

    run_ingestion(
        priority_only=args.priority_only,
        skip_scan=args.skip_scan,
        max_repos=args.max_repos,
    )


if __name__ == "__main__":
    main()
