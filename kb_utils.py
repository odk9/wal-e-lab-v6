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
#
# STRUCTURE : dict par langage. Seuls "_universal" + le langage du pattern
# sont chargés lors de la vérification. Ça évite qu'une exemption Rust
# masque un vrai nom d'entité dans un pattern Python.
#
# Ajouter ici au fur et à mesure des faux positifs rencontrés.
# ---------------------------------------------------------------------------
TECHNICAL_TERMS: dict[str, set[str]] = {
    # ── Termes partagés par TOUS les langages ─────────────────────────────
    "_universal": {
        # "order" → sort_order, order_by, ordering, ordered, reorder, border
        "sort_order", "sort_orders", "order_by", "order_by_", "ordering",
        "ordered", "reorder", "reorders", "border", "borders",
        "order by",            # clause SQL — universel
        # "user" → username, userid, user_id, superuser, current_user
        "username", "usernames", "user_id", "user_ids", "userid",
        "superuser", "superusers", "current_user",
        # "item" → item_id, items_per_page, lineitem
        "item_id", "item_ids", "items_per_page", "lineitem", "lineitems",
        # "post" → postfix, repost (mots anglais, pas HTTP)
        "postfix", "repost", "reposts",
        # "post" → HTTP method strings (universel web)
        '"post"',              # HTTP method string in CORS/method lists
        '"post",',             # HTTP method in array
        # "tag" / "tags" → _tag (champ KB interne)
        "_tag",
        # "message" → error messages (universel programmation)
        "errormessage",        # generic error property
        "detail=",             # generic response pattern
        # "type" → feature_type, file_type, content_type
        "feature_type", "file_type", "content_type", "type_hint",
        # "model" → model_config, model_dump, model_validate
        "model_config", "model_dump", "model_validate", "model_fields",
        # "event" → event_handler, event_loop, add_event (span/otel)
        "event_handler", "event_loop", "add_event",
        # "note" → notebook, annotation
        "notebook", "annotation",
        # "event" → log event, event_dict (structlog/logging core concept)
        "event_dict", "event_data", "log_event", "event =",
        # "message" → log message (core logging concept)
        "log_message",
    },

    # ── Python / FastAPI ──────────────────────────────────────────────────
    "python": {
        # "post" → HTTP method calls (TestClient, APIRouter)
        ".post(", "@router.post", "client.post", "agent.post",
        # "item" → dict .items()
        ".items()",
        # "tag" → FastAPI tags= parameter
        'tags=', 'tags=[',
        # "message" → emails.Message, XxxMessage, email headers, smtp
        "emails.message", "xxxmessage",
        "message-id", "msg_id",  # email header keys
        'get("message', 'get("msg', 'headers.get',  # email header access
        # "user" → SMTP auth
        '["user"]', '"user"', "smtp_user",
        # "task" → asyncio task types
        "asyncio.task", "asyncio.create_task",
        # "task" → Celery framework keywords and config keys (technical)
        "@shared_task", "@app.task", "task_serializer", "task_success",
        "task_failure", "task_retry", "task_prerun", "task_postrun",
        "task_received", "task_rejected", "task_revoked", "task_unknown",
        "task_time_limit", "task_soft_time_limit", "task_track_started",
        "task_routes", "task_default", "max_retries", "@current_app.task",
        "current_task", "get_task_logger", "task_id", "task.request",
        'task": "xxx', '"task":', 'task,', 'task)', 'task[',
        'tasks[', 'tasks"', '= chain(', '= group(', '= chord(',
        ".apply_async(", "update_state(", "task_queue",
        # Function definitions (not business entities)
        "long_running_job(", "process_job(", "safe_operation(",
        "critical_job(", "custom_throttled_job(", "bulk_process_job(",
        "rate_limited_job(", "housekeeping_job(",
        # "message" → logging/transport context (not entity)
        "being_dispatched", "about_to_be_sent", "being_sent",
        "published successfully", "being_retried", "being_processed",
        "logger.debug(", "logger.info(", "logger.error(",
        'worker_log_format=', 'worker_task_log_format=',
        '%(message)s', '%(levelname)s', '%(processName)s',
        # "task" → Celery execution context (not entity)
        "task execution", "task publish", "task publish", "task timeout",
        "task failed", "task succeeded", "task_id", "task_prerun",
        "task_postrun", "acks_late", "track_started", "bind=true",
        "# task", "# Job", "# Celery", "# Execution",
        "task retrying", "task receives", "task unknown",
        "task_received", "soft_time_limit", "time_limit",
        "bind=True", "bind = true", '"task":', "task (",
        # "event" → structlog event_dict, logging event (technical)
        "event_dict[", "event_dict,", "event_dict)", "event_dict =",
        "event[", "event,", "event)", "event =", "event.",
        "events =", "events[", "events)", "events,",
        # "message" → chainlit cl.Message, chatbot message (API class name)
        "cl.message", "cl.askusermessage", "cl.askactionmessage",
        "@cl.on_message", "@cl.on_action", "@cl.on_chat_start",
        "message(content", "message(author", ".send()", "msg =",
        "msg.", "msg)", "message =", "message.", "message)",
        "message,", "messages[", "messages)", "xxxmessagewith",
        "message object", "message object ___",  # docstring pattern
        ": cl.message)", "cl.message) -> none:",
        '"message:',  # dict string value
        '"and message:', '" and message:',
        # Chainlit message patterns in docstrings and function context
        "handle incoming user", "containing user input", "send response back to user",
        "send message with", "process message with", "handle message", "on_message",
        "handle incoming user message",  # docstring exact
        "process message using",  # docstring exact
        "process user query",  # docstring exact
        "process message using langchain",
        # "user" → chainlit cl.User, cl.user_session (API)
        "cl.user", "cl.user_session", "user_session", "user_id",
        '"role": "user"',  # dict string value
        '"user"',  # any quoted user string
        # Chainlit user/account context patterns
        "process_account_", "process_user_", "process_user_query",
        "process_account_choice", "get_account_", "get_user_",
        "xxxuserquery", "xxxusertask",
        "incoming user message", "user input", "current user",
        "current_account", "xxxuser", "xxxaccount",
        "handle user action", "ask user", "incoming user",
        "update session on message", "xxxauthuser", "xxxauthacc",
        "the reply parameter", "send message with",
        "ask user for", "handle user action",
        "authenticate user", "authenticate account", "custom authentication",
        "setup and manage user", "handle user message", "handle user action",
        "displayed to user", "called once when user", "return user object",
        "return account", "from chainlit.authentication import",
        "to user for better", "that user can", "return user",
        "import user", "def custom_authentication",
        "xxxusername", "-> user:", ") -> user:",
        "from chainlit.authentication import user",  # class name
        "xxxaccount = user(",  # class instantiation
        "return user ",  # return statement
    },

    # ── JavaScript / Express ──────────────────────────────────────────────
    "javascript": {
        # "post" → HTTP method calls (Express, supertest)
        ".post(", "app.post(", "router.post(",
        "method: 'post'",      # fetch options
        # "user" → req.user (Express/Passport), userAgent, OAuth scopes
        "req.user", "useragent", "user_agent",
        "user:email", "'user:email'",
        # "item" → menuItem, listItem (UI components)
        "menuitem", "listitem",
        # "model" → mongoose.model, Model.find
        "mongoose.model", ".model(",
        # "message" → error message, flash message (Express)
        ".message", "err.message",
        "{ message:", "message:", "{ message", ", message",
        "message,", "message }", "super(message)",
        "message =", "message)",
        "failuremessage",      # Passport option
        "flash(", "req.flash",
        "your message", "body.message", "sending message",
        # "event" → EventEmitter (Node)
        "addeventlistener", "eventemitter", "event_emitter",
        ".on(", ".emit(", ".once(",
        "event: {", "event:",
        # "order" → z-order, tab-order (CSS/HTML)
        "z-order", "tab-order", "taborder",
        # "item" → dict-like .items() pas pertinent en JS mais garde compat
        ".items()",
        # "tag" → tags= (Express/Passport)
        'tags=', 'tags=[',
        # "event" → logging event (pino/winston)
        "event,", "event)", "event =", "event.",
        "events[", "events)",
        # "message" → pino log message field
        "message:", "message,", "message)",
    },

    # ── TypeScript / NestJS ───────────────────────────────────────────────
    "typescript": {
        # Hérite des mêmes bases que JS pour Express
        ".post(", "app.post(", "router.post(",
        "method: 'post'",
        # "post" → @Post() decorator (routing-controllers / NestJS)
        "@post(",
        # "user" → req.user, userAgent, OAuth
        "req.user", "useragent", "user_agent",
        "user:email", "'user:email'",
        # "type" → TypeScript keywords
        "type ", "interface ",
        # "item" → menuItem, listItem
        "menuitem", "listitem",
        # "model" → .model(
        ".model(",
        # "message" → error messages (même set que JS)
        ".message", "err.message",
        "{ message:", "message:", "{ message", ", message",
        "message,", "message }", "super(message)",
        "message =", "message)",
        "failuremessage", "errormessage",
        "flash(", "req.flash",
        # "event" / "events" → EventDispatcher, EventSubscriber, EventEmitter
        "addeventlistener", "eventemitter", "event_emitter",
        "eventdispatcher", "eventsubscriber",
        ".on(", ".emit(", ".once(", "@on(",
        "event: {", "event:",
        # "order" → z-order, tab-order
        "z-order", "tab-order", "taborder",
        # "tag" → tags=
        'tags=', 'tags=[',
    },

    # ── Go / Gin ──────────────────────────────────────────────────────────
    "go": {
        # "model" → gorm.Model
        "gorm.model",
        # "order" → .Order("id desc") (GORM)
        '.order(',
        # "post" → HTTP method strings (déjà dans _universal: "post", "post",)
        ".post(",              # net/http method chaining
        # "todo" → context.TODO() (Go stdlib)
        "context.todo(",
        # "item" → error message "your requested Item"
        "requested item",
        # "message" → error message patterns
        ".message", "err.message", "message:", "message,",
        # "tag" / "tags" → audio metadata tags (taglib, normtag, tag readers in gonic)
        "tags.reader", "tags.tags", "tags =", "tagreader", "normtag", ".tags",
        "package tags", "type reader", "type metadata", "type properties",
        # "user" → db.User (database model, authentication)
        "db.user", "isuserauthenticated", ".user", "db.person",
        # "task" → asynq.Task (asynq framework type for background job queue)
        "asynq.task", "*asynq.task",
        # "event" → zap event, log event (technical)
        "event,", "event)", "event(",
        # "message" → zap log message field (technical)
        "message)", "message,",
        # "user" → zap logger field example
        "zap.string(", "zap.int(",
    },

    # ── Rust / Axum ───────────────────────────────────────────────────────
    "rust": {
        # "post" → routing::post (axum), method chaining, Method::POST
        "routing::post",
        "post(",               # axum standalone handler: post(create_xxx)
        ".post(",              # axum Router method chaining
        "post,",               # multi-line use: routing::{get, post, put}
        "post}",               # multi-line use: routing::{post}
        "method::post",        # hyper Method::POST constant
        'method="post"',       # HTML form method attribute
        # "item" → syn::Item (Rust AST), IntoIterator trait
        "syn::item",
        "intoiterator",        # IntoIterator trait
        "intoiterator<",
        # "event" → Event in webhook/async patterns (Stripe, Tokio, Axum)
        "event(",              # Event constructor in Stripe, tokio
        "event<",              # Event<T> generic type
        "event:",              # field binding: event: SomeEvent
        # "model" → derive(Model)
        "derive(",
        # "user" → Rust trait associated type, auth extractors
        "type user",           # associated type: type User = Xxx
        "self::user",          # Self::User (trait associated type)
        ".user",               # auth_session.user (field access)
        # "task" → tokio::task (spawn_blocking, etc.)
        "task::",              # tokio task::spawn_blocking
        # "message" → axum ws Message type, error handling, WebSocket
        "ws::message",
        "message::",           # ws::Message:: variants
        "message::text",       # Message::Text(...)
        "message::close",      # Message::Close(...)
        ", message)",          # let (status, message) = match
        "message) =",          # destructuring: let (..., message) =
        '"error": message',    # JSON error response construction
        # "event" → tracing_core::Event (tracing Layer trait)
        "event<",              # Event<'_> generic type
        "event>",              # closing of Event<'_>
        "&event",              # &Event<'_> reference
        "on_event",            # fn on_event() Layer trait method
        ", event)",            # function parameter
        "event::",             # Event:: variant access
        "log_entry",           # renamed Event parameter
    },

    # ── C++ (Crow / Drogon / uWebSockets) ─────────────────────────────────
    "cpp": {
        # "post" → HTTP POST in Crow/Drogon/uWS macros and methods
        '"post"_method',       # Crow HTTP method literal
        ", post)",             # Drogon PATH_ADD/ADD_METHOD_TO: Get, Post)
        ", post,",             # Drogon multi-method: Get, Post, Put
        "app.post(",           # uWebSockets HTTP POST handler
        "setup_post_routes",   # function name containing "post" for HTTP
        # "task" → Drogon coroutine return type Task<>
        "task<",               # drogon::Task<HttpResponsePtr>
        # "message" → WebSocket message handler/parameter/lambda key
        "on_message",
        "onmessage",
        "handlenewmessage",
        ".message =",          # uWS handler: .message = [](auto *ws, ...message...)
        "message,",            # message as lambda param followed by comma
        "message)",            # message as lambda param closing
        "string_view message", # std::string_view message (uWS param type)
        "broadcasting message",# log string "Broadcasting message:"
        # "user" → JSON config keys
        '"user":',             # JSON config: "user": "xxx_user"
        # "event" → spdlog log event (technical)
        "event,", "event)", "event(",
        # "message" → spdlog log message (technical)
        "message)", "message,", "message(",
    },

    # ── PHP / Laravel ──────────────────────────────────────────────────────
    "php": {
        # "order" → orderBy() Eloquent method with string literal
        "orderby(", "->orderby(", "->orderBy(", "orderBy('order'",
        # "item" → morphTo polymorphic relation (Laravel), function name
        "morphto(", ".morphto(", ".morphTo(", "function item()",
        # "tag" / "note" → ActivityPub JSON-LD type strings
        "'tag'", '"tag"', "'note'", '"note"',
        "'type' =>", '"type" =>',  # JSON object type discriminator
        # "message" → Laravel error messages
        "message():", "->message(",
        # "post" → HTTP routing (Laravel)
        "route.post", "route('", "@post", "->post(",
    },
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
    # Gère les imports multi-lignes (Rust use {...}, Go import (...), etc.)
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

    # Détection des blocs d'import multi-lignes (Rust: use x::{...};, Go: import (...))
    non_import_lines: list[str] = []
    in_multiline_import = False
    for line in code.split("\n"):
        stripped = line.strip()
        if stripped.startswith(prefixes):
            # Début d'import — vérifier si c'est un bloc multi-lignes
            if ("{" in stripped and "}" not in stripped) or (stripped == "import ("):
                in_multiline_import = True
            continue  # skip cette ligne (c'est un import)
        if in_multiline_import:
            # On est dans un bloc multi-lignes — skip jusqu'au fermant
            if "}" in stripped or stripped == ")":
                in_multiline_import = False
            continue
        non_import_lines.append(line)

    non_import_code = "\n".join(non_import_lines).lower()

    # Neutralise les termes techniques avant la vérification U-5
    # Ne charge que _universal + le langage du pattern → pas de faux négatifs cross-langage
    active_terms = TECHNICAL_TERMS.get("_universal", set()) | TECHNICAL_TERMS.get(language, set())
    sanitized = non_import_code
    for term in active_terms:
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
        # Détecte les callbacks imbriqués (3+ function() NON exemptées).
        # On exempte les `function` légitimes qui ont besoin du binding `this` :
        #   - assignation de propriété/méthode : `= function (`, `= async function (`
        #   - hooks Mongoose : `.pre(`, `.post(` suivi de function
        #   - strategy Passport : `new XxxStrategy(..., function (`
        #   - module.exports = function (
        # Seules les function() restantes (callbacks imbriqués) sont comptées.
        _THIS_BINDING_PATTERNS = (
            "= function",         # property/method assignment
            "= async function",   # async property/method assignment
            ".pre(",              # Mongoose pre hook
            ".post(",             # Mongoose post hook (hook, pas HTTP)
            ".get(function",      # Mongoose virtual getter
            "exports = function", # module.exports = function(app)
        )
        non_exempt_fn_count = 0
        for line in code.split("\n"):
            stripped = line.strip()
            has_function = "function(" in stripped or "function (" in stripped
            if not has_function:
                continue
            is_exempt = any(pat in stripped for pat in _THIS_BINDING_PATTERNS)
            if not is_exempt:
                non_exempt_fn_count += 1
        if non_exempt_fn_count >= 3:
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


def validate_before_insert(
    normalized_code: str,
    function_name: str,
    language: str,
    *,
    strict: bool = True,
) -> list[str]:
    """
    Valide un pattern AVANT insertion en KB.
    Appelle check_charte_violations() et lève ValueError si strict=True
    et qu'il y a des violations.

    Usage dans les scripts d'ingestion :
        violations = validate_before_insert(code, name, lang)
        # Si strict=True (défaut), lève ValueError → le pattern n'est PAS inséré.
        # Si strict=False, retourne les violations sans bloquer.

    Returns:
        Liste de violations (vide = OK).
    Raises:
        ValueError si strict=True et violations détectées.
    """
    violations = check_charte_violations(normalized_code, function_name, language)
    if violations and strict:
        raise ValueError(
            f"Charte violations bloquantes pour '{function_name}' "
            f"(language={language}):\n"
            + "\n".join(f"  - {v}" for v in violations)
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


def query_kb(
    client: Any,
    collection: str,
    query_vector: list[float],
    language: str | None = None,
    framework: str | None = None,
    feature_type: str | None = None,
    limit: int = 5,
) -> list[Any]:
    """
    Query la KB avec filtrage obligatoire par langage.

    RÈGLE V6 : toujours filtrer par language pour éviter la contamination
    cross-langage (un pattern Python qui remonte sur une query JS).

    Utilise client.query_points() (qdrant-client 1.17+).

    Args:
        client: QdrantClient instance
        collection: nom de la collection ("patterns")
        query_vector: vecteur de la query (via embed_query())
        language: filtre obligatoire — "python", "javascript", "typescript", "go", "rust"
        framework: filtre optionnel — "fastapi", "express", "gin", "axum"
        feature_type: filtre optionnel — "crud", "auth", "schema", "model", etc.
        limit: nombre de résultats max

    Returns:
        Liste de ScoredPoint (accéder via .payload, .score)
    """
    # Import local pour éviter la dépendance au top-level
    from qdrant_client.models import (
        FieldCondition,
        Filter,
        MatchValue,
    )

    must_conditions: list[FieldCondition] = []

    if language:
        must_conditions.append(
            FieldCondition(key="language", match=MatchValue(value=language))
        )
    if framework:
        must_conditions.append(
            FieldCondition(key="framework", match=MatchValue(value=framework))
        )
    if feature_type:
        must_conditions.append(
            FieldCondition(key="feature_type", match=MatchValue(value=feature_type))
        )

    query_filter = Filter(must=must_conditions) if must_conditions else None

    results = client.query_points(
        collection_name=collection,
        query=query_vector,
        query_filter=query_filter,
        limit=limit,
        with_payload=True,
    )

    return results.points


def build_wiring_payload(
    wiring_type: str,
    description: str,
    modules: list[str],
    connections: list[str],
    code_example: str,
    pattern_scope: str,
    language: str,
    framework: str,
    stack: str,
    source_repo: str,
    tag: str,
    charte_version: str = "1.0",
) -> dict[str, Any]:
    """
    Construit le payload Qdrant standardisé pour un wiring.
    Garantit la présence de tous les champs obligatoires.
    """
    return {
        "wiring_type": wiring_type,
        "description": description,
        "modules": modules,
        "connections": connections,
        "code_example": code_example,
        "pattern_scope": pattern_scope,
        "language": language,
        "framework": framework,
        "stack": stack,
        "source_repo": source_repo,
        "charte_version": charte_version,
        "created_at": int(time.time()),
        "_tag": tag,
    }


def query_wirings(
    client: Any,
    query_vector: list[float],
    language: str | None = None,
    framework: str | None = None,
    wiring_type: str | None = None,
    pattern_scope: str | None = None,
    limit: int = 5,
) -> list[Any]:
    """
    Query la collection wirings avec filtrage.

    Même règle que query_kb : toujours filtrer par language.

    Args:
        client: QdrantClient instance
        query_vector: vecteur de la query (via embed_query())
        language: filtre obligatoire — "python", "javascript", etc.
        framework: filtre optionnel — "fastapi", "express", etc.
        wiring_type: filtre optionnel — "import_graph", "dependency_chain", "flow_pattern"
        pattern_scope: filtre optionnel — "crud_simple", "crud_auth", etc.
        limit: nombre de résultats max

    Returns:
        Liste de ScoredPoint
    """
    from qdrant_client.models import (
        FieldCondition,
        Filter,
        MatchValue,
    )

    must_conditions: list[FieldCondition] = []

    if language:
        must_conditions.append(
            FieldCondition(key="language", match=MatchValue(value=language))
        )
    if framework:
        must_conditions.append(
            FieldCondition(key="framework", match=MatchValue(value=framework))
        )
    if wiring_type:
        must_conditions.append(
            FieldCondition(key="wiring_type", match=MatchValue(value=wiring_type))
        )
    if pattern_scope:
        must_conditions.append(
            FieldCondition(key="pattern_scope", match=MatchValue(value=pattern_scope))
        )

    query_filter = Filter(must=must_conditions) if must_conditions else None

    results = client.query_points(
        collection_name="wirings",
        query=query_vector,
        query_filter=query_filter,
        limit=limit,
        with_payload=True,
    )

    return results.points


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
