"""
embedder.py — Wrapper SentenceTransformer pour l'embedding local.

Modèle : all-MiniLM-L6-v2 (384 dims, rapide, ONNX compatible)
Pas d'API externe — tout tourne en local.
"""

from __future__ import annotations

from functools import lru_cache

from sentence_transformers import SentenceTransformer

_MODEL_NAME = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    """Charge le modèle une seule fois (singleton)."""
    return SentenceTransformer(_MODEL_NAME)


def embed(text: str) -> list[float]:
    """Encode un texte en vecteur normalisé (384 dims)."""
    model = _get_model()
    return model.encode(text, normalize_embeddings=True).tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Encode un batch de textes (plus efficace que embed() en boucle)."""
    model = _get_model()
    return model.encode(texts, normalize_embeddings=True, batch_size=32).tolist()
