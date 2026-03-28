"""
retriever.py — Interface stable QdrantRetriever pour la KB V6.

Cette interface ne change pas entre V6 (local embedded) et V7+ (server mode).
Seule la ligne de connexion change :
  V6 : QdrantClient(path="./kb_qdrant")
  V7+ : QdrantClient(url="http://localhost:6333", api_key="...")
"""

from __future__ import annotations

from dataclasses import dataclass

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from embedder import embed

KB_PATH = "./kb_qdrant"


@dataclass
class Pattern:
    feature_type: str
    framework: str
    file_role: str
    normalized_code: str
    source_repo: str
    charte_version: str
    score: float


class QdrantRetriever:
    def __init__(self, path: str = KB_PATH) -> None:
        self.client = QdrantClient(path=path)  # local V6
        # Pour V7+ : self.client = QdrantClient(url="...", api_key="...")

    def search(
        self,
        feature_type: str,
        framework: str,
        query_text: str,
        limit: int = 5,
    ) -> list[Pattern]:
        """
        Recherche les patterns les plus proches pour une feature donnée.

        Args:
            feature_type: ex. "crud", "auth_jwt", "websocket", "redis_pubsub"
            framework:    ex. "fastapi", "express", "gin", "axum"
            query_text:   description textuelle de ce qu'on cherche
            limit:        nombre de résultats

        Returns:
            Liste de Pattern triée par score décroissant
        """
        embedding = embed(query_text)

        results = self.client.search(
            collection_name="patterns",
            query_vector=embedding,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="feature_type", match=MatchValue(value=feature_type)
                    ),
                    FieldCondition(
                        key="framework", match=MatchValue(value=framework)
                    ),
                ]
            ),
            limit=limit,
        )

        return [
            Pattern(
                feature_type=r.payload.get("feature_type", ""),
                framework=r.payload.get("framework", ""),
                file_role=r.payload.get("file_role", ""),
                normalized_code=r.payload.get("normalized_code", ""),
                source_repo=r.payload.get("source_repo", ""),
                charte_version=r.payload.get("charte_version", "1.0"),
                score=r.score,
            )
            for r in results
        ]

    def search_by_file_role(
        self,
        feature_type: str,
        framework: str,
        file_role: str,
        query_text: str,
        limit: int = 3,
    ) -> list[Pattern]:
        """
        Recherche ciblée par file_role (ex: "models", "routes", "tests").
        Utile quand le générateur a besoin d'un fichier spécifique.
        """
        embedding = embed(query_text)

        results = self.client.search(
            collection_name="patterns",
            query_vector=embedding,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="feature_type", match=MatchValue(value=feature_type)
                    ),
                    FieldCondition(
                        key="framework", match=MatchValue(value=framework)
                    ),
                    FieldCondition(
                        key="file_role", match=MatchValue(value=file_role)
                    ),
                ]
            ),
            limit=limit,
        )

        return [
            Pattern(
                feature_type=r.payload.get("feature_type", ""),
                framework=r.payload.get("framework", ""),
                file_role=r.payload.get("file_role", ""),
                normalized_code=r.payload.get("normalized_code", ""),
                source_repo=r.payload.get("source_repo", ""),
                charte_version=r.payload.get("charte_version", "1.0"),
                score=r.score,
            )
            for r in results
        ]

    def get_architecture(self, family: str) -> dict | None:
        """
        Récupère l'architecture de référence pour une famille applicative.

        Args:
            family: ex. "crud_api", "bot_platform", "rag_platform"

        Returns:
            Payload de la famille, ou None si non trouvée
        """
        results = self.client.search(
            collection_name="architectures",
            query_vector=[0.0] * 384,  # dummy — filtrage exact par keyword
            query_filter=Filter(
                must=[
                    FieldCondition(key="family", match=MatchValue(value=family))
                ]
            ),
            limit=1,
        )
        return results[0].payload if results else None

    def stats(self) -> dict:
        """Retourne les stats de la KB."""
        patterns_count = self.client.count("patterns").count
        arch_count = self.client.count("architectures").count
        return {
            "patterns": patterns_count,
            "architectures": arch_count,
        }
