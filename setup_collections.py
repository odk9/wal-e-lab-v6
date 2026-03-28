"""
setup_collections.py — Crée les collections Qdrant pour la KB Wal-e V6.
À lancer une seule fois avant la première ingestion.

Usage:
    source .venv/bin/activate
    python setup_collections.py
"""

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    HnswConfigDiff,
    PayloadSchemaType,
    VectorParams,
)

KB_PATH = "./kb_qdrant"


def create_patterns_collection(client: QdrantClient) -> None:
    """
    Collection `patterns` — patterns de features normalisés.

    Un point = un pattern de code (ex: routes CRUD FastAPI, modèle SQLAlchemy...)
    Filtrage par feature_type + framework + language + file_role.
    HNSW m=16 / ef_construct=100 pour une bonne qualité d'index.
    """
    client.create_collection(
        collection_name="patterns",
        vectors_config=VectorParams(
            size=384,                  # all-MiniLM-L6-v2
            distance=Distance.COSINE,
        ),
        hnsw_config=HnswConfigDiff(
            m=16,
            ef_construct=100,
        ),
    )

    # Index sur les 4 champs de filtrage fréquents
    for field in ("feature_type", "framework", "language", "file_role"):
        client.create_payload_index("patterns", field, PayloadSchemaType.KEYWORD)

    print("  ✅ Collection 'patterns' créée")
    print("     Payload : feature_type | framework | language | file_role")
    print("               stack | normalized_code | source_repo | charte_version | created_at")
    print("     Index   : feature_type, framework, language, file_role")


def create_architectures_collection(client: QdrantClient) -> None:
    """
    Collection `architectures` — familles applicatives de référence.

    Un point = une famille (crud_api, bot_platform, rag_platform...).
    Contient l'architecture de référence : services, communication, base_patterns.
    """
    client.create_collection(
        collection_name="architectures",
        vectors_config=VectorParams(
            size=384,
            distance=Distance.COSINE,
        ),
    )

    client.create_payload_index("architectures", "family", PayloadSchemaType.KEYWORD)

    print("  ✅ Collection 'architectures' créée")
    print("     Payload : family | description | reference_repos")
    print("               services | communication | base_patterns")
    print("     Index   : family")


def main() -> None:
    print(f"Connexion Qdrant → {KB_PATH}")
    client = QdrantClient(path=KB_PATH)

    existing = [c.name for c in client.get_collections().collections]
    print(f"Collections existantes : {existing or 'aucune'}\n")

    # patterns
    if "patterns" in existing:
        print("  ⚠️  'patterns' existe déjà — skip")
    else:
        create_patterns_collection(client)

    # architectures
    if "architectures" in existing:
        print("  ⚠️  'architectures' existe déjà — skip")
    else:
        create_architectures_collection(client)

    # Résumé
    print("\n--- Résumé ---")
    for name in ("patterns", "architectures"):
        info = client.get_collection(name)
        count = client.count(name).count
        size = info.config.params.vectors.size
        print(f"  {name:15} | {count} points | vecteurs {size} dims")

    print("\n✅ KB Qdrant prête.")


if __name__ == "__main__":
    main()
