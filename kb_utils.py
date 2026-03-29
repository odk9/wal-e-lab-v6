"""
kb_utils.py — Utilitaires partagés pour tous les scripts d'ingestion KB Wal-e Lab V6.

Importé par : ingest_fastcrud.py, ingest_*.py
"""

import re
import time
import uuid
from typing import Any

# ---------------------------------------------------------------------------
# Termes techniques qui CONTIENNENT des mots interdits mais ne sont PAS
# des noms d'entités métier. On les neutralise avant la vérification.
# Ajouter ici au fur et à mesure des faux positifs rencontrés.
# ---------------------------------------------------------------------------
TECHNICAL_TERMS: set[str] = {
    # "order" → sort_order, order_by, ordering, ordered, reorder, border
    "sort_order", "sort_orders", "order_by", "order_by_", "ordering",
    "ordered", "reorder", "reorders", "border", "borders",
    # "user" → username, userid, user_id, superuser, current_user
    "username", "usernames", "user_id", "user_ids", "userid",
    "superuser", "superusers", "current_user",
    # "item" → item_id, items_per_page, lineitem
    "item_id", "item_ids", "items_per_page", "lineitem", "lineitems",
    # "post" → postfix, repost
    "postfix", "repost", "reposts",
    # "tag" → _tag (champ KB interne)
    "_tag",
    # "type" → feature_type, file_type, content_type
    "feature_type", "file_type", "content_type", "type_hint",
    # "model" → model_config, model_dump, model_validate
    "model_config", "model_dump", "model_validate", "model_fields",
}

# Noms d'entités métier interdits dans le code normalisé
FORBIDDEN_ENTITIES: list[str] = [
    "todo", "todos", "task", "tasks", "post", "posts",
    "article", "articles", "product", "products", "user", "users",
    "item", "items", "order", "orders", "comment", "comments",
    "category", "categories", "tag", "tags", "note", "notes",
    "event", "events", "message", "messages", "blog", "blogs",
]


def check_charte_violations(code: str, function_name: str = "?") -> list[str]:
    """
    Vérifie qu'un pattern normalisé respecte les règles critiques de la Charte Wal-e.
    Retourne une liste de violations (vide = OK).

    Règles vérifiées :
      - U-5  : pas de noms d'entités métier (Xxx/xxx/xxxs obligatoires)
      - F-1  : pas de declarative_base() (SQLAlchemy 1.x interdit)
      - F-2  : pas de datetime.utcnow() (datetime.now(UTC) obligatoire)
      - F-3  : pas de class Config (ConfigDict obligatoire)
    """
    violations: list[str] = []

    # --- Lignes hors imports (les imports contiennent souvent des mots interdits) ---
    non_import_lines = [
        line for line in code.split("\n")
        if not line.strip().startswith(("from ", "import "))
    ]
    non_import_code = "\n".join(non_import_lines).lower()

    # Neutralise les termes techniques avant la vérification U-5
    sanitized = non_import_code
    for term in TECHNICAL_TERMS:
        sanitized = sanitized.replace(term.lower(), "___")

    # U-5 — Entités métier
    for entity in FORBIDDEN_ENTITIES:
        if re.search(rf"\b{entity}\b", sanitized):
            violations.append(
                f"[U-5] Entité métier '{entity}' dans pattern '{function_name}'"
            )

    # F-1 — SQLAlchemy 1.x
    if "declarative_base()" in code:
        violations.append(
            f"[F-1] declarative_base() détecté dans '{function_name}' "
            f"— utiliser DeclarativeBase"
        )

    # F-2 — datetime.utcnow
    if "datetime.utcnow" in code:
        violations.append(
            f"[F-2] datetime.utcnow() détecté dans '{function_name}' "
            f"— utiliser datetime.now(UTC)"
        )

    # F-3 — Pydantic V1
    if re.search(r"class\s+Config\s*:", code):
        violations.append(
            f"[F-3] class Config détecté dans '{function_name}' "
            f"— utiliser model_config = ConfigDict(...)"
        )

    return violations


def build_payload(
    normalized_code: str,
    function: str,
    feature_type: str,
    file_role: str,
    language: str,
    framework: str,
    stack: str,
    file_path: str,
    source_repo: str,
    tag: str,
    charte_version: str = "1.0",
) -> dict[str, Any]:
    """
    Construit le payload Qdrant standardisé pour un pattern.
    Garantit la présence de tous les champs obligatoires.
    """
    return {
        "normalized_code": normalized_code,
        "function": function,
        "feature_type": feature_type,
        "file_role": file_role,
        "language": language,
        "framework": framework,
        "stack": stack,
        "file_path": file_path,
        "source_repo": source_repo,
        "charte_version": charte_version,
        "created_at": int(time.time()),
        "_tag": tag,
    }


def make_uuid() -> str:
    """Génère un UUID string pour les IDs Qdrant."""
    return str(uuid.uuid4())


def audit_report(
    repo_name: str,
    dry_run: bool,
    count_before: int,
    count_after: int,
    patterns_extracted: int,
    patterns_indexed: int,
    query_results: list[dict],
    violations: list[str],
) -> str:
    """
    Génère le rapport final d'ingestion.
    query_results : liste de dicts {query, function, file_role, score, code_preview, norm_ok}
    """
    lines = [
        "",
        f"{'=' * 60}",
        f"  RAPPORT INGESTION {repo_name}",
        f"{'=' * 60}",
        f"  Mode              : {'DRY_RUN (données supprimées)' if dry_run else 'PRODUCTION (données conservées)'}",
        f"  Patterns extraits : {patterns_extracted}",
        f"  Patterns indexés  : {patterns_indexed}",
        f"  Count KB avant    : {count_before}",
        f"  Count KB après    : {count_after}",
        "",
        "  Résultats queries :",
        f"  {'Query':<45} {'Function':<30} {'Score':>6}  Norm",
        f"  {'-' * 45} {'-' * 30} {'-' * 6}  {'-' * 4}",
    ]

    for r in query_results:
        norm_flag = "✅" if r.get("norm_ok", True) else "❌"
        lines.append(
            f"  {r['query'][:44]:<45} {r['function'][:29]:<30} "
            f"{r['score']:>6.4f}  {norm_flag}"
        )

    lines.append("")
    if violations:
        lines.append(f"  ⚠️  Violations Charte ({len(violations)}) :")
        for v in violations:
            lines.append(f"     - {v}")
    else:
        lines.append("  ✅ Violations Charte : aucune")

    lines.append("")
    verdict = "✅ PASS" if not violations and patterns_indexed > 0 else "❌ FAIL"
    lines.append(f"  Verdict : {verdict}")
    lines.append(f"{'=' * 60}")
    lines.append("")

    return "\n".join(lines)
