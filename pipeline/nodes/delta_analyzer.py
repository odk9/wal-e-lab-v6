"""
delta_analyzer.py — Node LangGraph V6 (NOUVEAU).

Compare les features du PRD à l'architecture de référence de la famille
et identifie le delta — ce qui nécessite des patterns spécifiques.

Modèle : google/gemini-2.5-flash (compréhension structurelle multi-fichiers)
"""

from __future__ import annotations

import json
import os

import httpx

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
DELTA_MODEL = "google/gemini-2.5-flash"


def delta_analyzer_node(state: dict) -> dict:
    """
    Node LangGraph — identifie le delta entre le PRD et l'architecture de référence.

    Input  : state["features"], state["reference_architecture"]
    Output : state["delta_features"], state["delta_analyzed"]
    """
    features = state.get("features", [])
    reference_arch = state.get("reference_architecture", {})
    prd_content = state.get("prd_content", "")

    delta = _compute_delta(features, reference_arch, prd_content)

    print(f"  🔍 Delta analyzer : {len(delta)} features spécifiques au PRD")
    for f in delta:
        print(f"     + {f}")

    return {
        **state,
        "delta_features": delta,
        "delta_analyzed": True,
    }


def _compute_delta(
    features: list[str],
    reference_arch: dict,
    prd_content: str,
) -> list[str]:
    """
    Identifie les features du PRD qui ne sont pas couvertes par l'architecture de référence.
    Ce sont les features qui nécessitent des patterns KB spécifiques.
    """
    base_patterns = reference_arch.get("base_patterns", [])

    if not OPENROUTER_API_KEY or not base_patterns:
        # Fallback : toutes les features sont dans le delta
        return features

    prompt = f"""Tu analyses un PRD et une architecture de référence.

Architecture de référence (patterns inclus par défaut) :
{json.dumps(base_patterns, indent=2)}

Features détectées dans le PRD :
{json.dumps(features, indent=2)}

Identifie les features du PRD qui NE SONT PAS couvertes par l'architecture de référence.
Ce sont les features spécifiques qui nécessitent des patterns additionnels.

Réponds UNIQUEMENT avec un tableau JSON de strings, ex: ["auth_jwt", "redis_pubsub"]
Si toutes les features sont couvertes, réponds: []"""

    try:
        resp = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": DELTA_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200,
                "temperature": 0,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()

        # Parse JSON
        if "```" in content:
            content = content.split("```")[1].replace("json", "").strip()

        delta = json.loads(content)
        return [f for f in delta if isinstance(f, str)]

    except Exception as e:
        print(f"  ⚠️  Delta Analyzer LLM erreur : {e} — fallback toutes features")
        # Fallback : features non couvertes par base_patterns
        return [f for f in features if f not in base_patterns]
