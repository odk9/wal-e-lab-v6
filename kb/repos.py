"""
repos.py — Liste des repos sources pour la KB V6.

Organisés par stack et domaine. Le Scanner utilise cette liste pour
télécharger et extraire les patterns.

Légende statut :
  "priority" — priorité haute, ingérer en premier
  "standard" — repos standard
  "optional" — intéressant mais pas critique
"""

# ---------------------------------------------------------------------------
# Python / FastAPI
# ---------------------------------------------------------------------------

FASTAPI_REPOS = [
    # Templates officiels / référence
    {"url": "https://github.com/tiangolo/full-stack-fastapi-template", "priority": "priority"},
    {"url": "https://github.com/fastapi/fastapi", "priority": "priority"},
    # CRUD + SQLAlchemy 2.0
    {"url": "https://github.com/igorbenav/fastcrud", "priority": "priority"},
    {"url": "https://github.com/jonra1993/fastapi-alembic-sqlmodel-async", "priority": "priority"},
    {"url": "https://github.com/fastapi-users/fastapi-users", "priority": "priority"},
    # Auth JWT
    {"url": "https://github.com/whythawk/full-stack-fastapi-postgresql", "priority": "standard"},
    {"url": "https://github.com/mjhea0/awesome-fastapi", "priority": "optional"},
    # WebSocket
    {"url": "https://github.com/tiangolo/fastapi/tree/master/docs_src/websockets", "priority": "standard"},
    # Background tasks
    {"url": "https://github.com/fastapi/fastapi/tree/master/docs_src/background_tasks", "priority": "standard"},
]

# ---------------------------------------------------------------------------
# Python / Discord bot
# ---------------------------------------------------------------------------

DISCORD_REPOS = [
    {"url": "https://github.com/Rapptz/discord.py", "priority": "priority"},
    {"url": "https://github.com/Pycord-Development/pycord", "priority": "standard"},
    {"url": "https://github.com/interactions-py/interactions.py", "priority": "standard"},
]

# ---------------------------------------------------------------------------
# Python / RAG + Vector DB
# ---------------------------------------------------------------------------

RAG_REPOS = [
    {"url": "https://github.com/langchain-ai/langchain", "priority": "priority"},
    {"url": "https://github.com/qdrant/qdrant-client", "priority": "priority"},
    {"url": "https://github.com/run-llama/llama_index", "priority": "standard"},
    {"url": "https://github.com/chroma-core/chroma", "priority": "standard"},
]

# ---------------------------------------------------------------------------
# Python / Redis
# ---------------------------------------------------------------------------

REDIS_REPOS = [
    {"url": "https://github.com/redis/redis-py", "priority": "priority"},
    {"url": "https://github.com/aio-libs/aioredis-py", "priority": "standard"},
]

# ---------------------------------------------------------------------------
# TypeScript / Express + Prisma
# ---------------------------------------------------------------------------

EXPRESS_REPOS = [
    {"url": "https://github.com/expressjs/express", "priority": "priority"},
    {"url": "https://github.com/prisma/prisma", "priority": "priority"},
    {"url": "https://github.com/microsoft/TypeScript-Node-Starter", "priority": "standard"},
    {"url": "https://github.com/w3tecch/express-typescript-boilerplate", "priority": "standard"},
]

# ---------------------------------------------------------------------------
# Go / Gin + GORM
# ---------------------------------------------------------------------------

GIN_REPOS = [
    {"url": "https://github.com/gin-gonic/gin", "priority": "priority"},
    {"url": "https://github.com/go-gorm/gorm", "priority": "priority"},
    {"url": "https://github.com/eddycjy/go-gin-example", "priority": "standard"},
    {"url": "https://github.com/vsouza/awesome-go", "priority": "optional"},
]

# ---------------------------------------------------------------------------
# Rust / Axum + SQLx
# ---------------------------------------------------------------------------

AXUM_REPOS = [
    {"url": "https://github.com/tokio-rs/axum", "priority": "priority"},
    {"url": "https://github.com/launchbadge/sqlx", "priority": "priority"},
    {"url": "https://github.com/davidpdrsn/axum-login", "priority": "standard"},
]

# ---------------------------------------------------------------------------
# Lookup par stack
# ---------------------------------------------------------------------------

REPOS_BY_STACK: dict[str, list[dict]] = {
    "fastapi": FASTAPI_REPOS,
    "discord": DISCORD_REPOS,
    "rag": RAG_REPOS,
    "redis": REDIS_REPOS,
    "express": EXPRESS_REPOS,
    "gin": GIN_REPOS,
    "axum": AXUM_REPOS,
}

# Tous les repos — pour ingestion complète
ALL_REPOS: list[dict] = [
    {"stack": stack, **repo}
    for stack, repos in REPOS_BY_STACK.items()
    for repo in repos
]

# Repos prioritaires seulement
PRIORITY_REPOS: list[dict] = [
    r for r in ALL_REPOS if r["priority"] == "priority"
]
