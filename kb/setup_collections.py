"""
setup_collections.py — Initialise les collections Qdrant pour la KB V6.
À lancer une seule fois avant la première ingestion.

Usage:
    cd kb/
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


def setup_patterns_collection(client: QdrantClient) -> None:
    """Collection principale — patterns de features normalisés."""
    existing = [c.name for c in client.get_collections().collections]

    if "patterns" in existing:
        print("Collection 'patterns' déjà existante — skip.")
        return

    client.create_collection(
        collection_name="patterns",
        vectors_config=VectorParams(
            size=384,  # all-MiniLM-L6-v2
            distance=Distance.COSINE,
        ),
        hnsw_config=HnswConfigDiff(
            m=16,
            ef_construct=100,
        ),
    )

    # Index sur les champs de filtrage fréquents
    client.create_payload_index(
        "patterns", "feature_type", PayloadSchemaType.KEYWORD
    )
    client.create_payload_index("patterns", "framework", PayloadSchemaType.KEYWORD)
    client.create_payload_index("patterns", "language", PayloadSchemaType.KEYWORD)
    client.create_payload_index("patterns", "file_role", PayloadSchemaType.KEYWORD)
    client.create_payload_index("patterns", "charte_version", PayloadSchemaType.KEYWORD)

    print("✅ Collection 'patterns' créée avec index payload.")


def setup_architectures_collection(client: QdrantClient) -> None:
    """Collection secondaire — familles architecturales de référence."""
    existing = [c.name for c in client.get_collections().collections]

    if "architectures" in existing:
        print("Collection 'architectures' déjà existante — skip.")
        return

    client.create_collection(
        collection_name="architectures",
        vectors_config=VectorParams(
            size=384,
            distance=Distance.COSINE,
        ),
    )

    client.create_payload_index(
        "architectures", "family", PayloadSchemaType.KEYWORD
    )

    print("✅ Collection 'architectures' créée.")


def seed_architectures(client: QdrantClient) -> None:
    """Seed les familles architecturales de base."""
    from embedder import embed

    families = [
        {
            "family": "crud_api",
            "description": "API REST CRUD simple — une ou plusieurs entités, pagination, filtres basiques.",
            "reference_repos": [
                "https://github.com/tiangolo/full-stack-fastapi-template",
            ],
            "services": ["api_service", "database"],
            "communication": ["REST"],
            "base_patterns": ["crud", "auth_jwt", "pagination"],
        },
        {
            "family": "bot_platform",
            "description": "Bot Discord ou Slack avec API REST complémentaire et gestion d'événements.",
            "reference_repos": [
                "https://github.com/Rapptz/discord.py",
            ],
            "services": ["bot_service", "api_service", "event_handler"],
            "communication": ["Discord Gateway", "REST", "Redis pub/sub"],
            "base_patterns": ["discord_bot", "crud", "event_bus", "background_task"],
        },
        {
            "family": "rag_platform",
            "description": "Plateforme RAG — ingestion de documents, vector search, cache Redis, UI Streamlit.",
            "reference_repos": [
                "https://github.com/langchain-ai/langchain",
            ],
            "services": ["ingestor_service", "retriever_service", "ui_service", "cache"],
            "communication": ["REST", "Redis cache"],
            "base_patterns": ["vector_search", "document_ingestion", "redis_cache", "streamlit_ui"],
        },
        {
            "family": "ai_chat",
            "description": "Interface de chat avec LLM local ou API, gestion de sessions, historique.",
            "reference_repos": [
                "https://github.com/streamlit/streamlit",
            ],
            "services": ["chat_service", "session_manager", "llm_client"],
            "communication": ["REST", "WebSocket"],
            "base_patterns": ["chat_session", "llm_inference", "streamlit_ui", "websocket"],
        },
        {
            "family": "media_pipeline",
            "description": "Pipeline de traitement media asynchrone — ingestion, traitement ML, streaming résultats.",
            "reference_repos": [],
            "services": ["ingestor", "processor", "ml_service", "api_service", "event_bus"],
            "communication": ["Redis Streams", "REST", "WebSocket"],
            "base_patterns": ["ml_inference", "redis_pubsub", "background_task", "websocket", "crud"],
        },
    ]

    existing = client.count("architectures").count
    if existing > 0:
        print(f"Collection 'architectures' déjà seedée ({existing} familles) — skip.")
        return

    from qdrant_client.models import PointStruct
    import uuid

    points = []
    for fam in families:
        text = f"{fam['family']} {fam['description']} {' '.join(fam['base_patterns'])}"
        points.append(
            PointStruct(
                id=str(uuid.uuid4()),
                vector=embed(text),
                payload=fam,
            )
        )

    client.upsert(collection_name="architectures", points=points)
    print(f"✅ {len(families)} familles architecturales seedées.")


def main() -> None:
    print(f"Connexion Qdrant local : {KB_PATH}")
    client = QdrantClient(path=KB_PATH)

    setup_patterns_collection(client)
    setup_architectures_collection(client)
    seed_architectures(client)

    # Résumé
    for name in ["patterns", "architectures"]:
        info = client.get_collection(name)
        count = client.count(name).count
        print(f"  {name}: {count} points, vectors_size={info.config.params.vectors.size}")

    print("\n✅ KB Qdrant prête.")


if __name__ == "__main__":
    main()
