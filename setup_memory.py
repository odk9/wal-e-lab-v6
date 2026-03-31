"""
setup_memory.py — Crée la collection Qdrant `memory` pour Wal-e Lab V6.

La mémoire permet à Wal-e de retenir 7 types de souvenirs :

  Pipeline (automatique) :
  - fix_log         : erreurs rencontrées et corrections appliquées
  - project_summary : bilan de chaque projet généré
  - lesson          : leçons généralisables (cross-projet)
  - decision        : choix structurants pris pendant un run
  - run_log         : log technique de chaque nœud

  Interaction (espace discussion) :
  - conversation    : résumé de chaque session chat Wal-e ↔ utilisateur
  - preference      : préférences persistantes de l'utilisateur

Même modèle d'embedding que la KB : nomic-ai/nomic-embed-text-v1.5-Q (768 dims).

Usage:
    .venv/bin/python3 setup_memory.py
"""

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    HnswConfigDiff,
    PayloadSchemaType,
    VectorParams,
)

KB_PATH = "./kb_qdrant"
VECTOR_SIZE = 768  # nomic-ai/nomic-embed-text-v1.5-Q


def create_memory_collection(client: QdrantClient) -> None:
    """
    Collection `memory` — mémoire persistante de Wal-e Lab.

    Un point = un souvenir (7 types possibles).

    Filtrage par :
      - memory_type  : "fix_log" | "project_summary" | "lesson" | "decision" |
                       "run_log" | "conversation" | "preference"
      - project_id   : identifiant unique du run pipeline
      - session_id   : identifiant de session discussion
      - language      : pour ne rappeler que des souvenirs pertinents au langage
      - framework     : idem par framework
      - error_type    : catégorie d'erreur (pour le fixer)
      - node          : nœud pipeline (pour les run_logs)
      - category      : catégorie de préférence (coding, stack, workflow, general)

    HNSW m=16 / ef_construct=100 — même config que patterns/wirings.
    """
    client.create_collection(
        collection_name="memory",
        vectors_config=VectorParams(
            size=VECTOR_SIZE,
            distance=Distance.COSINE,
        ),
        hnsw_config=HnswConfigDiff(
            m=16,
            ef_construct=100,
        ),
    )

    # Index sur les champs de filtrage fréquents
    for field in (
        "memory_type", "project_id", "session_id",
        "language", "framework", "error_type",
        "node", "category",
    ):
        client.create_payload_index("memory", field, PayloadSchemaType.KEYWORD)

    print("  ✅ Collection 'memory' créée (7 types)")
    print("     Types   : fix_log | project_summary | lesson | decision |")
    print("               run_log | conversation | preference")
    print("     Index   : memory_type, project_id, session_id, language,")
    print("               framework, error_type, node, category")


def main() -> None:
    print(f"Connexion Qdrant → {KB_PATH}")
    client = QdrantClient(path=KB_PATH)

    existing = [c.name for c in client.get_collections().collections]
    print(f"Collections existantes : {existing}\n")

    if "memory" in existing:
        print("  ⚠️  'memory' existe déjà — skip")
        print("     Pour recréer : client.delete_collection('memory') puis relancer")
    else:
        create_memory_collection(client)

    # Résumé
    print("\n--- Résumé ---")
    for name in ("patterns", "wirings", "architectures", "memory"):
        if name in existing or name == "memory":
            try:
                info = client.get_collection(name)
                count = client.count(name).count
                print(f"  {name:15} | {count} points | {info.config.params.vectors.size} dims")
            except Exception:
                pass

    print("\n✅ Mémoire Qdrant prête.")


if __name__ == "__main__":
    main()
