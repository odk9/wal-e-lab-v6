"""
researcher.py — Node amélioré V6.

V5 : une query générique par projet → contexte bruité
V6 : query par feature delta → patterns ciblés depuis KB Qdrant

Input  : state["delta_features"], state["framework"], state["language"]
Output : state["kb_patterns"], state["kb_patterns_loaded"]
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent.parent / "kb"))

KB_PATH = os.environ.get("KB_PATH", "../kb/kb_qdrant")


def researcher_node(state: dict) -> dict:
    """Node LangGraph — récupère les patterns KB pour chaque feature delta."""
    delta_features = state.get("delta_features", [])
    framework = state.get("framework", "fastapi")
    language = state.get("language", "python")

    # Vérifier si la KB est disponible
    from pathlib import Path
    kb_path = Path(KB_PATH)

    if not kb_path.exists() or not any(kb_path.iterdir()):
        print("  ⚠️  KB Qdrant non disponible — skip retrieval (patterns SYSTEM_PROMPT utilisés)")
        return {
            **state,
            "kb_patterns": {},
            "kb_patterns_loaded": True,
        }

    try:
        from retriever import QdrantRetriever
        retriever = QdrantRetriever(path=str(kb_path))
        stats = retriever.stats()

        if stats["patterns"] == 0:
            print("  ⚠️  KB vide — skip retrieval")
            return {**state, "kb_patterns": {}, "kb_patterns_loaded": True}

        print(f"  🔍 KB : {stats['patterns']} patterns disponibles")

        kb_patterns: dict[str, list[str]] = {}

        for feature in delta_features:
            patterns = retriever.search(
                feature_type=feature,
                framework=framework,
                query_text=f"{feature} {framework} {language}",
                limit=3,
            )

            if patterns:
                kb_patterns[feature] = [p.normalized_code for p in patterns]
                print(f"     {feature} : {len(patterns)} patterns trouvés (score max: {patterns[0].score:.3f})")
            else:
                print(f"     {feature} : aucun pattern trouvé")

        return {
            **state,
            "kb_patterns": kb_patterns,
            "kb_patterns_loaded": True,
        }

    except Exception as e:
        print(f"  ⚠️  Researcher erreur : {e} — skip retrieval")
        return {**state, "kb_patterns": {}, "kb_patterns_loaded": True}
