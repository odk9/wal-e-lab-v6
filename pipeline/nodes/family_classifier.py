"""
family_classifier.py — Node LangGraph V6 (NOUVEAU).

Classifie le PRD dans une famille applicative et charge
l'architecture de référence correspondante depuis la KB.

Modèle : google/gemini-2.5-flash-lite (classification courte)
"""

from __future__ import annotations

import os
import sys

import httpx

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent.parent / "kb"))
from retriever import QdrantRetriever

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
CLASSIFIER_MODEL = "google/gemini-2.5-flash-lite"

FAMILIES = [
    "crud_api",
    "bot_platform",
    "rag_platform",
    "ai_chat",
    "media_pipeline",
]


def family_classifier_node(state: dict) -> dict:
    """
    Node LangGraph — classifie le PRD dans une famille.

    Input  : state["prd_content"]
    Output : state["family"], state["reference_architecture"], state["family_identified"]
    """
    prd = state.get("prd_content", "")

    # 1. LLM classification
    family = _classify_family(prd)

    # 2. Chargement architecture de référence depuis KB
    retriever = QdrantRetriever()
    reference_arch = retriever.get_architecture(family)

    if reference_arch is None:
        print(f"  ⚠️  Famille '{family}' non trouvée en KB — fallback crud_api")
        family = "crud_api"
        reference_arch = retriever.get_architecture("crud_api") or {}

    print(f"  🏗️  Famille identifiée : {family}")
    print(f"     Services : {reference_arch.get('services', [])}")

    return {
        **state,
        "family": family,
        "reference_architecture": reference_arch,
        "family_identified": True,
    }


def _classify_family(prd_content: str) -> str:
    """Appelle le LLM pour classifier le PRD."""
    if not OPENROUTER_API_KEY:
        return _heuristic_classify(prd_content)

    prompt = f"""Classifie ce PRD dans une des familles applicatives suivantes.
Réponds avec UN SEUL mot (le nom de la famille), rien d'autre.

Familles disponibles :
- crud_api        : API REST CRUD simple (Todo, Blog, Inventory...)
- bot_platform    : Bot Discord/Slack avec API complémentaire
- rag_platform    : Plateforme RAG, vector search, embeddings
- ai_chat         : Interface de chat avec LLM, historique de sessions
- media_pipeline  : Pipeline de traitement media/audio/vidéo

PRD :
{prd_content[:3000]}

Famille :"""

    try:
        resp = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": CLASSIFIER_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 20,
                "temperature": 0,
            },
            timeout=20.0,
        )
        resp.raise_for_status()
        answer = resp.json()["choices"][0]["message"]["content"].strip().lower()

        # Normaliser la réponse
        for family in FAMILIES:
            if family in answer:
                return family

        return "crud_api"  # fallback

    except Exception as e:
        print(f"  ⚠️  Family Classifier LLM erreur : {e} — fallback heuristique")
        return _heuristic_classify(prd_content)


def _heuristic_classify(prd_content: str) -> str:
    """Fallback heuristique si le LLM est indisponible."""
    content_lower = prd_content.lower()

    if any(kw in content_lower for kw in ["discord", "bot", "slash command", "cog"]):
        return "bot_platform"
    if any(kw in content_lower for kw in ["rag", "vector", "embedding", "retrieval", "qdrant"]):
        return "rag_platform"
    if any(kw in content_lower for kw in ["chat", "conversation", "llm", "streamlit"]):
        return "ai_chat"
    if any(kw in content_lower for kw in ["audio", "video", "media", "stream", "pipeline"]):
        return "media_pipeline"

    return "crud_api"
