"""
normalizer.py — Agent KB Normaliseur.

Prend un RawPattern extrait par l'Extracteur et le convertit en
"langage Wal-e" selon la Charte Wal-e (Documentation/WAL-E_CHARTE_PYTHON_FASTAPI.md).

Entrée  : RawPattern (code brut)
Sortie  : str — code normalisé prêt pour la KB Qdrant

Modèle : qwen/qwen3-coder (480B A35B) — qualité code > vitesse
"""

from __future__ import annotations

import os

import httpx

from extractor import RawPattern

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
NORMALIZER_MODEL = "qwen/qwen3-coder"  # 480B A35B
CHARTE_VERSION = "1.0"

# Règles niveau 1 (universelles) condensées pour le prompt
_RULES_LEVEL_1 = """
U-1 : Imports ordonnés — stdlib → third-party → local, une ligne vide entre groupes, alphabétique.
U-2 : Zéro import inutilisé.
U-3 : Types explicites sur tous les paramètres et valeurs de retour.
U-4 : Zéro variable inutilisée (utiliser _ si intentionnel).
U-5 : Noms d'entités métier → Xxx (classe), xxx (variable/fonction), xxxs (pluriel).
U-6 : Fonctions < 40 lignes, une seule responsabilité.
U-7 : Zéro print() dans le code de production.
U-8 : Guard clauses plutôt que if/else imbriqués (profondeur max 2).
"""

# Règles niveau 2 (Python/FastAPI) condensées
_RULES_LEVEL_2_FASTAPI = """
F-1 : SQLAlchemy 2.0 — DeclarativeBase, Mapped[type], mapped_column(). Jamais Column/declarative_base().
F-2 : datetime.now(UTC) uniquement. Jamais datetime.utcnow().
F-3 : Pydantic V2 — ConfigDict(from_attributes=True), StrictBool, field_serializer pour datetime.
F-4 : Lifespan asynccontextmanager. Jamais @app.on_event.
F-5 : Prefix split — router = /xxxs, main = /api/v1.
F-6 : Path(ge=1, le=2147483647) sur tous les IDs.
F-7 : Rejeter query params inconnus sur GET list (422).
F-8 : Tests sync (def test_xxx, TestClient). Jamais async def test_.
F-9 : Fixture client avec SQLite in-memory.
F-10 : Routes async / tests sync — pas de mélange.
F-11 : get_db async generator standard.
F-12 : pyproject.toml avec known-first-party.
F-13 : main.py avec handler d'exception générique.
"""

# Règles niveau 3 par feature type
_RULES_LEVEL_3: dict[str, str] = {
    "auth_jwt": """
- Jamais stocker le mot de passe en clair — bcrypt (passlib).
- Token JWT avec expiration (exp claim). Access 15min, refresh 7 jours.
- get_current_user comme FastAPI Dependency.
- 401 si token expiré, 403 si permissions insuffisantes.
""",
    "redis_pubsub": """
- Toujours sérialiser en JSON (pas de pickle).
- Gérer la reconnexion dans le consumer.
- Consumer en background task.
- Channel name depuis constante.
""",
    "websocket": """
- Gérer WebSocketDisconnect proprement.
- ConnectionManager pour broadcast.
- Heartbeat ou timeout pour connexions inactives.
""",
    "discord_bot": """
- Déclarer les intents explicitement.
- Répondre dans les 3 secondes (sinon defer()).
- Séparer les cogs par domaine.
- Token depuis env var.
""",
    "ml_inference": """
- Valider l'input avant l'inférence (taille, format).
- Timeout explicite sur le modèle.
- Réponse structurée si échec.
- Modèle chargé une fois dans le lifespan.
""",
}


def normalize_pattern(pattern: RawPattern) -> str | None:
    """
    Normalise un pattern brut selon la Charte Wal-e.

    Args:
        pattern: RawPattern extrait par l'Extracteur

    Returns:
        Code normalisé (str), ou None si erreur LLM
    """
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY non défini.")

    # Construire le prompt selon le type de feature
    rules = _RULES_LEVEL_1

    if pattern.framework == "fastapi":
        rules += _RULES_LEVEL_2_FASTAPI

    level3 = _RULES_LEVEL_3.get(pattern.feature_type, "")
    if level3:
        rules += f"\nRègles spécifiques {pattern.feature_type} :{level3}"

    prompt = f"""Tu es le Normaliseur Wal-e. Réécris ce code {pattern.language} en appliquant exactement les règles ci-dessous.

NE change rien d'autre : pas la logique, pas les algorithmes, pas les commentaires pertinents.
Sortie : code normalisé UNIQUEMENT, sans explication ni balises markdown.

RÈGLES :
{rules}

CODE À NORMALISER ({pattern.feature_type} / {pattern.framework} / {pattern.file_role}) :
{pattern.raw_code}"""

    try:
        resp = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": NORMALIZER_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 4096,
                "temperature": 0,
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()

        # Nettoyer les backticks si le modèle les a ajoutés
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1]) if lines[-1] == "```" else "\n".join(lines[1:])

        return content

    except Exception as e:
        print(f"  ⚠️  Normaliseur erreur : {e}")
        return None
