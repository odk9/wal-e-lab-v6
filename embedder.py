"""
embedder.py — Wrapper fastembed pour nomic-embed-text-v1.5-Q.

Points importants sur ce modèle :
  - Vecteurs 768 dims, 8192 tokens max (pas de troncature sur le code)
  - fastembed retourne des vecteurs NON normalisés — on normalise ici
  - Prefixes obligatoires :
      "search_document: " → pour indexer un pattern en KB
      "search_query: "    → pour une requête de recherche

Usage:
    from embedder import embed_document, embed_query
    vec = embed_document("def create_xxx(...)...")   # pour la KB
    vec = embed_query("FastAPI CRUD routes")          # pour chercher
"""

from __future__ import annotations

import numpy as np
from fastembed import TextEmbedding

MODEL_NAME = "nomic-ai/nomic-embed-text-v1.5-Q"
VECTOR_SIZE = 768

_model: TextEmbedding | None = None


def _get_model() -> TextEmbedding:
    """Charge le modèle une seule fois (singleton)."""
    global _model
    if _model is None:
        _model = TextEmbedding(MODEL_NAME)
    return _model


def _normalize(vec: np.ndarray) -> list[float]:
    """Normalise un vecteur L2 → norme = 1.0 (requis pour cosine similarity)."""
    norm = np.linalg.norm(vec)
    if norm == 0:
        return vec.tolist()
    return (vec / norm).tolist()


def embed_document(code: str) -> list[float]:
    """
    Embedding d'un pattern de code à stocker en KB.
    Prefix "search_document:" obligatoire pour ce modèle.
    """
    model = _get_model()
    text = f"search_document: {code}"
    raw = np.array(list(model.embed([text]))[0])
    return _normalize(raw)


def embed_query(query: str) -> list[float]:
    """
    Embedding d'une requête de recherche.
    Prefix "search_query:" obligatoire pour ce modèle.
    """
    model = _get_model()
    text = f"search_query: {query}"
    raw = np.array(list(model.embed([text]))[0])
    return _normalize(raw)


def embed_documents_batch(codes: list[str]) -> list[list[float]]:
    """
    Embedding d'un batch de patterns (plus efficace qu'un appel par pattern).
    À utiliser dans l'ingestor pour les gros volumes.
    """
    model = _get_model()
    texts = [f"search_document: {code}" for code in codes]
    raws = list(model.embed(texts))
    return [_normalize(np.array(raw)) for raw in raws]
