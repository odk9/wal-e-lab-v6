"""
memory.py — Mémoire persistante pour Wal-e Lab V6.

7 types de souvenirs dans une seule collection Qdrant `memory` :

  PIPELINE (automatique) :
  - fix_log         : chaque correction appliquée pendant le pipeline
  - project_summary : bilan complet d'un projet après déploiement
  - lesson          : leçon généralisable extraite des summaries
  - decision        : choix structurant pris pendant un run pipeline
  - run_log         : log technique de chaque nœud du pipeline

  INTERACTION (espace discussion Wal-e ↔ utilisateur) :
  - conversation    : résumé d'une session de discussion
  - preference      : préférence persistante de l'utilisateur

Moments de lecture :
  - recall_for_strategy()      : début pipeline (PRD → stratégie)
  - recall_for_fixer()         : avant chaque fix (erreur → solution connue)
  - recall_conversations()     : début session chat (contexte passé)
  - get_preferences()          : début pipeline ou session (profil utilisateur)
  - recall_decisions()         : pendant génération (décisions similaires)

Stockage : collection Qdrant `memory` (même instance que la KB).

Usage:
    from memory import (
        # Écriture
        log_fix, log_project_summary, log_lesson,
        log_decision, log_run, log_conversation, set_preference,
        # Lecture
        recall_for_strategy, recall_for_fixer,
        recall_conversations, get_preferences, recall_decisions,
        # Utilitaires
        count_memories, memory_stats, get_project_history,
        get_session_history, delete_project_memory,
    )
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
)

from embedder import embed_document, embed_query

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
KB_PATH = "./kb_qdrant"
COLLECTION = "memory"


def _get_client() -> QdrantClient:
    """Connexion Qdrant locale (même instance que la KB)."""
    return QdrantClient(path=KB_PATH)


def _make_id() -> str:
    """UUID unique pour chaque point mémoire."""
    return str(uuid.uuid4())


# ═══════════════════════════════════════════════════════════════════════════
# ÉCRITURE — 7 fonctions, 7 types de souvenirs
# ═══════════════════════════════════════════════════════════════════════════


def log_fix(
    *,
    project_id: str,
    prd_name: str,
    iteration: int,
    error_type: str,
    error_message: str,
    fix_applied: str,
    file_affected: str,
    score_before: float,
    score_after: float,
    language: str,
    framework: str,
    stack: str = "",
) -> str:
    """
    Écrit un fix_log après chaque cycle evaluator → fixer.

    Appelé par le nœud fixer du pipeline après avoir appliqué une correction.
    Le description est construit pour être cherchable sémantiquement :
      "Fix [error_type] in [file]: [fix_applied]"

    Returns:
        point_id (str) pour traçabilité.
    """
    description = (
        f"Fix {error_type} in {file_affected}: {fix_applied}. "
        f"Error was: {error_message}. "
        f"Score {score_before} → {score_after}."
    )

    vector = embed_document(description)
    point_id = _make_id()

    payload: dict[str, Any] = {
        "memory_type": "fix_log",
        "project_id": project_id,
        "prd_name": prd_name,
        "iteration": iteration,
        "error_type": error_type,
        "error_message": error_message,
        "fix_applied": fix_applied,
        "file_affected": file_affected,
        "score_before": score_before,
        "score_after": score_after,
        "language": language,
        "framework": framework,
        "stack": stack,
        "description": description,
        "created_at": int(time.time()),
        "_tag": f"memory/{project_id}",
    }

    client = _get_client()
    client.upsert(
        collection_name=COLLECTION,
        points=[PointStruct(id=point_id, vector=vector, payload=payload)],
    )
    return point_id


def log_project_summary(
    *,
    project_id: str,
    prd_name: str,
    language: str,
    framework: str,
    stack: str = "",
    final_score: float,
    score_a: float,
    score_b: float,
    score_c: float,
    total_iterations: int,
    errors_encountered: list[str],
    patterns_used: list[str],
    lessons: list[str],
    github_repo: str = "",
) -> str:
    """
    Écrit un project_summary en fin de pipeline (après deployer).

    Capture le bilan complet : scores, nombre d'itérations, erreurs,
    patterns utilisés, et leçons apprises.

    Returns:
        point_id (str).
    """
    description = (
        f"Project {prd_name} ({language}/{framework}): "
        f"score {final_score}/100 (A:{score_a}, B:{score_b}, C:{score_c}) "
        f"in {total_iterations} iterations. "
        f"Errors: {', '.join(errors_encountered[:5])}. "
        f"Lessons: {', '.join(lessons[:3])}."
    )

    vector = embed_document(description)
    point_id = _make_id()

    payload: dict[str, Any] = {
        "memory_type": "project_summary",
        "project_id": project_id,
        "prd_name": prd_name,
        "language": language,
        "framework": framework,
        "stack": stack,
        "final_score": final_score,
        "score_a": score_a,
        "score_b": score_b,
        "score_c": score_c,
        "total_iterations": total_iterations,
        "errors_encountered": errors_encountered,
        "patterns_used": patterns_used,
        "lessons": lessons,
        "github_repo": github_repo,
        "description": description,
        "created_at": int(time.time()),
        "_tag": f"memory/{project_id}",
    }

    client = _get_client()
    client.upsert(
        collection_name=COLLECTION,
        points=[PointStruct(id=point_id, vector=vector, payload=payload)],
    )
    return point_id


def log_lesson(
    *,
    lesson: str,
    source_project_id: str = "",
    language: str = "",
    framework: str = "",
    error_type: str = "",
    applies_to: str = "all",
) -> str:
    """
    Écrit une lesson généralisable (cross-projet).

    Peut être extraite automatiquement des project_summaries ou ajoutée
    manuellement. Les lessons sans language/framework s'appliquent à tout.

    Exemples :
      - "Les PRD marketplace nécessitent pagination cursor-based"
      - "Double prefix /api/v1 cause score C = 0 systématiquement"
      - "SQLAlchemy declarative_base() fait échouer pyright"

    Returns:
        point_id (str).
    """
    vector = embed_document(lesson)
    point_id = _make_id()

    payload: dict[str, Any] = {
        "memory_type": "lesson",
        "description": lesson,
        "source_project_id": source_project_id,
        "language": language,
        "framework": framework,
        "error_type": error_type,
        "applies_to": applies_to,
        "created_at": int(time.time()),
        "_tag": "memory/lessons",
    }

    client = _get_client()
    client.upsert(
        collection_name=COLLECTION,
        points=[PointStruct(id=point_id, vector=vector, payload=payload)],
    )
    return point_id


def log_decision(
    *,
    project_id: str,
    prd_name: str,
    decision: str,
    rationale: str,
    alternatives_considered: list[str] | None = None,
    impact: str = "",
    node: str = "",
    language: str = "",
    framework: str = "",
) -> str:
    """
    Écrit une décision structurante prise pendant un run pipeline.

    Exemples :
      - "Choisi pagination cursor-based au lieu d'offset pour ce marketplace PRD"
      - "Utilisé JWT au lieu d'OAuth2 car le PRD ne mentionne pas de provider externe"
      - "Ajouté rate limiting car le PRD mentionne une API publique"

    Appelé par les nœuds strategist, delta_analyzer, ou generator quand
    un choix non trivial est fait.

    Returns:
        point_id (str).
    """
    description = (
        f"Decision for {prd_name}: {decision}. "
        f"Rationale: {rationale}."
    )

    vector = embed_document(description)
    point_id = _make_id()

    payload: dict[str, Any] = {
        "memory_type": "decision",
        "project_id": project_id,
        "prd_name": prd_name,
        "decision": decision,
        "rationale": rationale,
        "alternatives_considered": alternatives_considered or [],
        "impact": impact,
        "node": node,
        "language": language,
        "framework": framework,
        "description": description,
        "created_at": int(time.time()),
        "_tag": f"memory/{project_id}",
    }

    client = _get_client()
    client.upsert(
        collection_name=COLLECTION,
        points=[PointStruct(id=point_id, vector=vector, payload=payload)],
    )
    return point_id


def log_run(
    *,
    project_id: str,
    prd_name: str,
    node: str,
    status: str,
    input_summary: str,
    output_summary: str,
    duration_ms: int = 0,
    iteration: int = 0,
    error: str = "",
    language: str = "",
    framework: str = "",
) -> str:
    """
    Écrit un log technique pour chaque nœud exécuté dans le pipeline.

    Appelé automatiquement par le graph LangGraph après chaque nœud.
    Permet de retracer exactement ce qui s'est passé pendant un run :
    quel nœud, quel input, quel output, combien de temps, quelle erreur.

    Args:
        node: nom du nœud ("analyst", "strategist", "generator", "evaluator", "fixer", "deployer")
        status: "success" | "error" | "skipped"
        input_summary: résumé de l'input (pas le payload complet)
        output_summary: résumé de l'output (pas le code complet)

    Returns:
        point_id (str).
    """
    description = (
        f"Pipeline node '{node}' [{status}] for {prd_name} (iter {iteration}): "
        f"in={input_summary[:100]}. out={output_summary[:100]}."
    )
    if error:
        description += f" Error: {error[:100]}."

    vector = embed_document(description)
    point_id = _make_id()

    payload: dict[str, Any] = {
        "memory_type": "run_log",
        "project_id": project_id,
        "prd_name": prd_name,
        "node": node,
        "status": status,
        "input_summary": input_summary,
        "output_summary": output_summary,
        "duration_ms": duration_ms,
        "iteration": iteration,
        "error": error,
        "language": language,
        "framework": framework,
        "description": description,
        "created_at": int(time.time()),
        "_tag": f"memory/{project_id}",
    }

    client = _get_client()
    client.upsert(
        collection_name=COLLECTION,
        points=[PointStruct(id=point_id, vector=vector, payload=payload)],
    )
    return point_id


def log_conversation(
    *,
    session_id: str,
    summary: str,
    topics: list[str],
    decisions_made: list[str] | None = None,
    action_items: list[str] | None = None,
    project_id: str = "",
    user: str = "",
) -> str:
    """
    Écrit le résumé d'une session de discussion Wal-e ↔ utilisateur.

    Appelé en fin de session dans l'espace discussion de Wal-e Lab.
    Le résumé est généré par LLM à partir de la conversation complète,
    comme la compaction de contexte que fait Claude.

    Contient :
      - summary     : résumé narratif de la session (2-5 phrases)
      - topics      : sujets abordés (["ingestion KB", "fix wirings", "mémoire"])
      - decisions   : décisions prises pendant la discussion
      - action_items: tâches à faire identifiées pendant la session

    Returns:
        point_id (str).
    """
    description = (
        f"Session {session_id}: {summary} "
        f"Topics: {', '.join(topics)}."
    )

    vector = embed_document(description)
    point_id = _make_id()

    payload: dict[str, Any] = {
        "memory_type": "conversation",
        "session_id": session_id,
        "summary": summary,
        "topics": topics,
        "decisions_made": decisions_made or [],
        "action_items": action_items or [],
        "project_id": project_id,
        "user": user,
        "description": description,
        "created_at": int(time.time()),
        "_tag": f"memory/conversation/{session_id}",
    }

    client = _get_client()
    client.upsert(
        collection_name=COLLECTION,
        points=[PointStruct(id=point_id, vector=vector, payload=payload)],
    )
    return point_id


def set_preference(
    *,
    key: str,
    value: str,
    category: str = "general",
    user: str = "",
) -> str:
    """
    Écrit ou met à jour une préférence utilisateur persistante.

    Les préférences survivent à toutes les sessions et projets.
    Elles sont chargées au début de chaque pipeline et session de discussion.

    Le point_id est déterministe (basé sur key+user) : un upsert sur la même
    clé REMPLACE l'ancienne valeur (pas de doublons).

    Catégories :
      - "coding"   : style de code ("toujours utiliser ruff", "pytest-bdd")
      - "stack"    : préférences tech ("Redis pour le cache", "PostgreSQL pas SQLite")
      - "workflow" : préférences process ("commits en anglais", "verbose logging")
      - "general"  : tout le reste

    Exemples :
      set_preference(key="linter", value="ruff, jamais flake8", category="coding")
      set_preference(key="test_style", value="pytest-bdd avec Given/When/Then", category="coding")
      set_preference(key="language", value="français pour les réponses", category="general")

    Returns:
        point_id (str).
    """
    description = f"User preference [{category}]: {key} = {value}"
    vector = embed_document(description)

    # ID déterministe → upsert remplace l'ancienne valeur
    point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"pref:{user}:{key}"))

    payload: dict[str, Any] = {
        "memory_type": "preference",
        "key": key,
        "value": value,
        "category": category,
        "user": user,
        "description": description,
        "created_at": int(time.time()),
        "_tag": "memory/preferences",
    }

    client = _get_client()
    client.upsert(
        collection_name=COLLECTION,
        points=[PointStruct(id=point_id, vector=vector, payload=payload)],
    )
    return point_id


# ═══════════════════════════════════════════════════════════════════════════
# LECTURE — 5 fonctions, 5 moments
# ═══════════════════════════════════════════════════════════════════════════


def recall_for_strategy(
    prd_description: str,
    language: str,
    framework: str = "",
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Rappelle les souvenirs pertinents AVANT la génération.

    Appelé au début du pipeline (après analyst, avant generator).
    Cherche :
      1. project_summaries similaires (PRD proches)
      2. lessons applicables au langage/framework

    Le pipeline utilise ces souvenirs pour :
      - Éviter les erreurs déjà rencontrées sur des PRD similaires
      - Adapter la stratégie (ex: plus d'itérations si PRD complexe)
      - Pré-charger les patterns qui ont fonctionné

    Args:
        prd_description: texte du PRD ou résumé analyst
        language: langage cible (filtre obligatoire)
        framework: framework cible (filtre optionnel)
        limit: max souvenirs retournés

    Returns:
        Liste de payloads triés par pertinence (score cosine).
    """
    vector = embed_query(prd_description)
    client = _get_client()

    # Filtre : summaries + lessons pour ce langage (ou lessons universelles)
    must_conditions = [
        FieldCondition(
            key="memory_type",
            match=MatchValue(value="project_summary"),
        ),
    ]

    # Query 1 : project_summaries filtrés par langage
    summary_filter = Filter(
        must=[
            FieldCondition(key="memory_type", match=MatchValue(value="project_summary")),
            FieldCondition(key="language", match=MatchValue(value=language)),
        ]
    )

    summaries = client.query_points(
        collection_name=COLLECTION,
        query=vector,
        query_filter=summary_filter,
        limit=limit // 2,
        with_payload=True,
    ).points

    # Query 2 : lessons (filtrées par langage OU universelles)
    # On fait 2 sous-queries car Qdrant n'a pas de OR natif sur must
    lesson_results = []

    # Lessons pour ce langage
    lang_filter = Filter(
        must=[
            FieldCondition(key="memory_type", match=MatchValue(value="lesson")),
            FieldCondition(key="language", match=MatchValue(value=language)),
        ]
    )
    lang_lessons = client.query_points(
        collection_name=COLLECTION,
        query=vector,
        query_filter=lang_filter,
        limit=limit // 2,
        with_payload=True,
    ).points
    lesson_results.extend(lang_lessons)

    # Lessons universelles (language = "")
    universal_filter = Filter(
        must=[
            FieldCondition(key="memory_type", match=MatchValue(value="lesson")),
            FieldCondition(key="language", match=MatchValue(value="")),
        ]
    )
    universal_lessons = client.query_points(
        collection_name=COLLECTION,
        query=vector,
        query_filter=universal_filter,
        limit=limit // 4,
        with_payload=True,
    ).points
    lesson_results.extend(universal_lessons)

    # Merge et tri par score
    all_results = []
    for point in summaries:
        entry = dict(point.payload)
        entry["_score"] = point.score
        entry["_source"] = "project_summary"
        all_results.append(entry)

    for point in lesson_results:
        entry = dict(point.payload)
        entry["_score"] = point.score
        entry["_source"] = "lesson"
        all_results.append(entry)

    all_results.sort(key=lambda x: x["_score"], reverse=True)
    return all_results[:limit]


def recall_for_fixer(
    error_message: str,
    language: str,
    error_type: str = "",
    framework: str = "",
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    Rappelle les fix connus AVANT d'appliquer une correction.

    Appelé par le nœud fixer du pipeline avant chaque tentative de fix.
    Cherche des fix_logs similaires (même type d'erreur, même langage).

    Le fixer utilise ces souvenirs pour :
      - Appliquer directement un fix connu (pas besoin de LLM)
      - Éviter des fix qui n'ont pas fonctionné
      - Prioriser les corrections par impact (score_after - score_before)

    Args:
        error_message: message d'erreur à corriger
        language: langage du projet (filtre obligatoire)
        error_type: catégorie d'erreur (filtre optionnel)
        framework: framework cible (filtre optionnel)
        limit: max souvenirs retournés

    Returns:
        Liste de payloads triés par pertinence, avec _score et _impact.
    """
    vector = embed_query(error_message)
    client = _get_client()

    # Filtre : fix_logs pour ce langage
    conditions = [
        FieldCondition(key="memory_type", match=MatchValue(value="fix_log")),
        FieldCondition(key="language", match=MatchValue(value=language)),
    ]

    # Ajouter error_type si fourni
    if error_type:
        conditions.append(
            FieldCondition(key="error_type", match=MatchValue(value=error_type))
        )

    fix_filter = Filter(must=conditions)

    results = client.query_points(
        collection_name=COLLECTION,
        query=vector,
        query_filter=fix_filter,
        limit=limit,
        with_payload=True,
    ).points

    fixes = []
    for point in results:
        entry = dict(point.payload)
        entry["_score"] = point.score
        # Impact = gain de score apporté par ce fix
        before = entry.get("score_before", 0)
        after = entry.get("score_after", 0)
        entry["_impact"] = after - before
        fixes.append(entry)

    # Tri par score sémantique (pertinence) — le fixer peut re-trier par impact
    fixes.sort(key=lambda x: x["_score"], reverse=True)
    return fixes


def recall_decisions(
    context: str,
    language: str = "",
    project_id: str = "",
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    Rappelle les décisions similaires prises dans le passé.

    Appelé par le strategist ou generator quand il doit faire un choix.
    Cherche des décisions passées sémantiquement proches du contexte actuel.

    Args:
        context: description du choix à faire (ex: "pagination pour une API marketplace")
        language: filtre par langage (optionnel)
        project_id: exclure un projet spécifique (optionnel, pour éviter le self-match)
        limit: max décisions retournées

    Returns:
        Liste de payloads triés par pertinence.
    """
    vector = embed_query(context)
    client = _get_client()

    conditions: list[FieldCondition] = [
        FieldCondition(key="memory_type", match=MatchValue(value="decision")),
    ]
    if language:
        conditions.append(
            FieldCondition(key="language", match=MatchValue(value=language))
        )

    results = client.query_points(
        collection_name=COLLECTION,
        query=vector,
        query_filter=Filter(must=conditions),
        limit=limit,
        with_payload=True,
    ).points

    decisions = []
    for point in results:
        entry = dict(point.payload)
        entry["_score"] = point.score
        # Exclure le projet courant si demandé
        if project_id and entry.get("project_id") == project_id:
            continue
        decisions.append(entry)

    return decisions


def recall_conversations(
    context: str,
    limit: int = 5,
    project_id: str = "",
) -> list[dict[str, Any]]:
    """
    Rappelle les sessions de discussion passées pertinentes.

    Appelé au début d'une nouvelle session de discussion Wal-e ↔ utilisateur
    pour charger le contexte des sessions précédentes. Fonctionne comme la
    mémoire de Claude : retrouve les discussions passées sémantiquement
    proches du sujet en cours.

    Args:
        context: description du sujet ou première question de l'utilisateur
        limit: max sessions retournées
        project_id: filtre optionnel par projet

    Returns:
        Liste de résumés de sessions triés par pertinence.
    """
    vector = embed_query(context)
    client = _get_client()

    conditions: list[FieldCondition] = [
        FieldCondition(key="memory_type", match=MatchValue(value="conversation")),
    ]
    if project_id:
        conditions.append(
            FieldCondition(key="project_id", match=MatchValue(value=project_id))
        )

    results = client.query_points(
        collection_name=COLLECTION,
        query=vector,
        query_filter=Filter(must=conditions),
        limit=limit,
        with_payload=True,
    ).points

    sessions = []
    for point in results:
        entry = dict(point.payload)
        entry["_score"] = point.score
        sessions.append(entry)

    return sessions


def get_preferences(
    category: str = "",
    user: str = "",
) -> list[dict[str, str]]:
    """
    Charge toutes les préférences de l'utilisateur.

    Appelé au début de chaque pipeline et session de discussion.
    Retourne une liste plate de {key, value, category} — pas de recherche
    sémantique ici, on veut TOUTES les préférences.

    Args:
        category: filtre optionnel ("coding", "stack", "workflow", "general")
        user: filtre optionnel par utilisateur

    Returns:
        Liste de dicts {key, value, category}.
    """
    client = _get_client()

    conditions: list[FieldCondition] = [
        FieldCondition(key="memory_type", match=MatchValue(value="preference")),
    ]
    if category:
        conditions.append(
            FieldCondition(key="category", match=MatchValue(value=category))
        )

    results = client.scroll(
        collection_name=COLLECTION,
        scroll_filter=Filter(must=conditions),
        limit=100,
        with_payload=True,
    )[0]

    prefs = []
    for point in results:
        p = point.payload
        prefs.append({
            "key": p.get("key", ""),
            "value": p.get("value", ""),
            "category": p.get("category", ""),
        })

    return prefs


# ═══════════════════════════════════════════════════════════════════════════
# UTILITAIRES
# ═══════════════════════════════════════════════════════════════════════════


def count_memories(memory_type: str = "") -> int:
    """Compte les souvenirs, optionnellement filtrés par type."""
    client = _get_client()
    if not memory_type:
        return client.count(COLLECTION).count

    result = client.count(
        collection_name=COLLECTION,
        count_filter=Filter(
            must=[FieldCondition(key="memory_type", match=MatchValue(value=memory_type))]
        ),
    )
    return result.count


def get_session_history(session_id: str) -> list[dict[str, Any]]:
    """
    Récupère l'historique complet d'une session de discussion.
    """
    client = _get_client()

    results = client.scroll(
        collection_name=COLLECTION,
        scroll_filter=Filter(
            must=[FieldCondition(key="session_id", match=MatchValue(value=session_id))]
        ),
        limit=100,
        with_payload=True,
    )[0]

    entries = [dict(p.payload) for p in results]
    entries.sort(key=lambda x: x.get("created_at", 0))
    return entries


def get_project_history(project_id: str) -> list[dict[str, Any]]:
    """
    Récupère tous les souvenirs d'un projet (fix_logs, run_logs, decisions, summary).
    Trié par created_at (chronologique).
    """
    client = _get_client()

    results = client.scroll(
        collection_name=COLLECTION,
        scroll_filter=Filter(
            must=[FieldCondition(key="project_id", match=MatchValue(value=project_id))]
        ),
        limit=100,
        with_payload=True,
    )[0]  # scroll returns (points, next_page_offset)

    entries = [dict(p.payload) for p in results]
    entries.sort(key=lambda x: x.get("created_at", 0))
    return entries


def delete_project_memory(project_id: str) -> int:
    """
    Supprime tous les souvenirs d'un projet (cleanup).
    Utilise le champ _tag pour un delete propre.

    Returns:
        Nombre de points supprimés.
    """
    client = _get_client()
    before = client.count(COLLECTION).count

    client.delete(
        collection_name=COLLECTION,
        points_selector=Filter(
            must=[FieldCondition(key="_tag", match=MatchValue(value=f"memory/{project_id}"))]
        ),
    )

    after = client.count(COLLECTION).count
    return before - after


def memory_stats() -> dict[str, Any]:
    """Statistiques globales de la mémoire (7 types)."""
    return {
        "total": count_memories(),
        "fix_logs": count_memories("fix_log"),
        "project_summaries": count_memories("project_summary"),
        "lessons": count_memories("lesson"),
        "decisions": count_memories("decision"),
        "run_logs": count_memories("run_log"),
        "conversations": count_memories("conversation"),
        "preferences": count_memories("preference"),
    }
