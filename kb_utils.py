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
    # "user" → username, userid, user_id, superuser, current_user, smtp auth
    "username", "usernames", "user_id", "user_ids", "userid",
    "superuser", "superusers", "current_user",
    '["user"]', '"user"',  # SMTP protocol key
    "smtp_user",
    # "item" → item_id, items_per_page, lineitem, dict .items()
    "item_id", "item_ids", "items_per_page", "lineitem", "lineitems",
    ".items()",   # dict method
    # "post" → HTTP method .post(, @router.post, postfix, repost
    ".post(",     # HTTP POST method (TestClient, APIRouter, supertest)
    "@router.post", "client.post", "agent.post",
    "postfix", "repost", "reposts",
    # "tag" / "tags" → _tag (champ KB interne), FastAPI tags= parameter
    "_tag",
    'tags=',      # FastAPI router tags parameter
    'tags=[',
    # "message" → emails.Message, XxxMessage, Express error response, flash message
    "emails.message",   # email lib class (lowercased)
    "xxxmessage",       # normalized schema name (lowercased)
    "detail=",          # generic response pattern
    "{ message:",       # Express/Passport error response object
    "message:",         # JS object key in error responses
    "failuremessage",   # Passport option
    "errormessage",     # generic error property
    ".message",         # JS Error.message property / Mongoose validation
    "err.message",      # JS error.message standard property
    # "type" → feature_type, file_type, content_type
    "feature_type", "file_type", "content_type", "type_hint",
    # "model" → model_config, model_dump, model_validate
    "model_config", "model_dump", "model_validate", "model_fields",
    # "event" → event_handler, event_loop, addEventListener, EventEmitter
    "event_handler", "event_loop", "addeventlistener", "eventemitter",
    "event_emitter",
    # "note" → notebook, annotation
    "notebook", "annotation",
    # --- JavaScript / Express ---
    # "user" → req.user (Express/Passport), userAgent, OAuth scopes
    "req.user", "useragent", "user_agent",
    "user:email",       # GitHub OAuth scope
    "'user:email'",     # GitHub OAuth scope (quoted)
    # "post" → app.post, router.post (Express HTTP methods)
    "app.post(", "router.post(", "app.post(",
    # "item" → menuItem, listItem (UI components)
    "menuitem", "listitem",
    # "model" → mongoose.model, Model.find (Mongoose)
    "mongoose.model", ".model(",
    # "message" → error message, flash message (Express)
    "flash(", "req.flash",
    # "event" → on('event', ...) (Node EventEmitter pattern)
    ".on(", ".emit(", ".once(",
    # "order" → z-order, tab-order (CSS/HTML)
    "z-order", "tab-order", "taborder",
    # --- TypeScript ---
    # "type" → TypeScript type keyword
    "type ", "interface ",
    # --- Go ---
    # "model" → gorm.Model
    "gorm.model",
    # "order" → Order("id desc") (GORM)
    '.order(',
    # --- Rust ---
    # "item" → syn::Item (Rust AST)
    "syn::item",
    # "model" → derive(Model)
    "derive(",
}

# Noms d'entités métier interdits dans le code normalisé
FORBIDDEN_ENTITIES: list[str] = [
    "todo", "todos", "task", "tasks", "post", "posts",
    "article", "articles", "product", "products", "user", "users",
    "item", "items", "order", "orders", "comment", "comments",
    "category", "categories", "tag", "tags", "note", "notes",
    "event", "events", "message", "messages", "blog", "blogs",
]


def check_charte_violations(
    code: str,
    function_name: str = "?",
    language: str = "python",
) -> list[str]:
    """
    Vérifie qu'un pattern normalisé respecte les règles critiques de la Charte Wal-e.
    Retourne une liste de violations (vide = OK).

    Applique :
      - Règles U-* (universelles) : tous les langages
      - Règles F-* (Python/FastAPI) : uniquement si language="python"
      - Règles J-* (JavaScript/Express) : uniquement si language="javascript"
      - Règles T-* (TypeScript) : uniquement si language="typescript"
      - Règles G-* (Go/Gin) : uniquement si language="go"
      - Règles R-* (Rust/Axum) : uniquement si language="rust"
    """
    violations: list[str] = []

    # ------------------------------------------------------------------
    # Filtrage des lignes d'import (varie selon le langage)
    # ------------------------------------------------------------------
    import_prefixes = {
        "python": ("from ", "import "),
        "javascript": ("import ", "require(", "const ", "var ", "let "),
        "typescript": ("import ", "require(", "const ", "var ", "let "),
        "go": ("import "),
        "rust": ("use ", "extern "),
        "cpp": ("#include"),
    }
    prefixes = import_prefixes.get(language, ("from ", "import "))

    non_import_lines = [
        line for line in code.split("\n")
        if not line.strip().startswith(prefixes)
    ]
    non_import_code = "\n".join(non_import_lines).lower()

    # Neutralise les termes techniques avant la vérification U-5
    sanitized = non_import_code
    for term in TECHNICAL_TERMS:
        sanitized = sanitized.replace(term.lower(), "___")

    # ------------------------------------------------------------------
    # U-5 — Entités métier (UNIVERSEL — tous les langages)
    # ------------------------------------------------------------------
    for entity in FORBIDDEN_ENTITIES:
        if re.search(rf"\b{entity}\b", sanitized):
            violations.append(
                f"[U-5] Entité métier '{entity}' dans pattern '{function_name}'"
            )

    # ------------------------------------------------------------------
    # F-* — Règles Python / FastAPI
    # ------------------------------------------------------------------
    if language == "python":
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

    # ------------------------------------------------------------------
    # J-* — Règles JavaScript / Express
    # ------------------------------------------------------------------
    if language == "javascript":
        # J-1 — var interdit → const ou let
        if re.search(r"\bvar\s+", code):
            violations.append(
                f"[J-1] 'var' détecté dans '{function_name}' "
                f"— utiliser const ou let"
            )

        # J-2 — callback hell → async/await
        # Détecte les callbacks imbriqués (3+ niveaux de function())
        if code.count("function(") >= 3 or code.count("function (") >= 3:
            violations.append(
                f"[J-2] Callbacks imbriqués dans '{function_name}' "
                f"— utiliser async/await"
            )

        # J-3 — console.log interdit (équivalent de U-7 pour JS)
        non_import_code_raw = "\n".join(non_import_lines)
        if "console.log(" in non_import_code_raw:
            violations.append(
                f"[J-3] console.log() détecté dans '{function_name}' "
                f"— supprimer ou utiliser un logger"
            )

    # ------------------------------------------------------------------
    # T-* — Règles TypeScript
    # ------------------------------------------------------------------
    if language == "typescript":
        # T-1 — any interdit
        if re.search(r":\s*any\b", code):
            violations.append(
                f"[T-1] Type 'any' détecté dans '{function_name}' "
                f"— utiliser un type explicite"
            )

        # T-2 — var interdit (même règle que JS)
        if re.search(r"\bvar\s+", code):
            violations.append(
                f"[T-2] 'var' détecté dans '{function_name}' "
                f"— utiliser const ou let"
            )

        # T-3 — console.log interdit
        non_import_code_raw = "\n".join(non_import_lines)
        if "console.log(" in non_import_code_raw:
            violations.append(
                f"[T-3] console.log() détecté dans '{function_name}' "
                f"— supprimer ou utiliser un logger"
            )

    # ------------------------------------------------------------------
    # G-* — Règles Go / Gin
    # ------------------------------------------------------------------
    if language == "go":
        # G-1 — panic interdit (sauf init)
        if "panic(" in code and "func init()" not in code:
            violations.append(
                f"[G-1] panic() détecté dans '{function_name}' "
                f"— retourner une erreur"
            )

        # G-2 — fmt.Println interdit (équivalent U-7)
        if "fmt.Println(" in code or "fmt.Printf(" in code:
            violations.append(
                f"[G-2] fmt.Print détecté dans '{function_name}' "
                f"— utiliser log.Logger"
            )

    # ------------------------------------------------------------------
    # R-* — Règles Rust / Axum
    # ------------------------------------------------------------------
    if language == "rust":
        # R-1 — unwrap interdit (sauf tests)
        if ".unwrap()" in code and "#[test]" not in code:
            violations.append(
                f"[R-1] .unwrap() détecté dans '{function_name}' "
                f"— utiliser ? ou match"
            )

        # R-2 — println! interdit
        if "println!(" in code:
            violations.append(
                f"[R-2] println!() détecté dans '{function_name}' "
                f"— utiliser tracing ou log"
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
