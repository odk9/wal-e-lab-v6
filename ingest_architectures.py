#!/usr/bin/env python3
"""
ingest_architectures.py — Peuple la collection `architectures` dans Qdrant.

12 familles architecturales couvrant ~90% des apps backend.
Chaque famille = 1 point Qdrant avec :
  - Vecteur = embedding de la description (pour semantic search par le Family Classifier)
  - Payload = architecture de référence complète

Usage:
    .venv/bin/python3 ingest_architectures.py           # production
    .venv/bin/python3 ingest_architectures.py --dry-run  # preview sans écrire

Prérequis:
    - Qdrant collection "architectures" créée (setup_collections.py)
    - .venv avec qdrant-client, fastembed, numpy
"""

import sys
import time
import uuid

from embedder import embed_document
from qdrant_client import QdrantClient
from qdrant_client.models import FilterSelector, Filter, FieldCondition, MatchValue, PointStruct

# ─── Config ───────────────────────────────────────────────────────────────────
KB_PATH = "./kb_qdrant"
COLLECTION = "architectures"
TAG = "wale_architectures_v1"

# ─── Les 12 familles architecturales ──────────────────────────────────────────

ARCHITECTURES = [
    # ══════════════════════════════════════════════════════════════════════════
    # 1. CRUD API — Le socle de toute app backend
    # ══════════════════════════════════════════════════════════════════════════
    {
        "family": "crud_api",
        "description": (
            "REST API classique multi-entités avec CRUD complet. "
            "Base de données relationnelle, validation Pydantic/Zod, "
            "pagination, filtrage, tri. Le pattern le plus fondamental — "
            "presque tous les autres en héritent."
        ),
        "reference_repos": [
            "https://github.com/igorbenav/fastcrud",
            "https://github.com/fastapi/full-stack-fastapi-template",
            "https://github.com/hagopj13/node-express-boilerplate",
            "https://github.com/eddycjy/go-gin-example",
        ],
        "services": [
            "api_gateway",
            "database_layer",
            "validation_layer",
        ],
        "communication": [
            "REST/JSON",
            "SQL (ORM)",
        ],
        "base_patterns": [
            "crud", "model", "schema", "route", "test",
            "config", "dependency", "migration", "pagination",
            "error_handling",
        ],
        "tech_stacks": {
            "python": "fastapi+sqlalchemy+pydantic_v2",
            "typescript": "express+prisma",
            "go": "gin+gorm",
            "rust": "axum+sqlx",
        },
        "typical_entities": [
            "Resource", "Collection", "Entry",
        ],
        "scaling_pattern": "horizontal_stateless",
        "complexity": "simple",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 2. SaaS B2B — Multi-tenant avec auth, billing, admin
    # ══════════════════════════════════════════════════════════════════════════
    {
        "family": "saas_b2b",
        "description": (
            "Plateforme SaaS multi-tenant avec isolation des données par organisation. "
            "Authentification (JWT + OAuth2 social login), rôles et permissions (RBAC), "
            "billing (Stripe), onboarding, dashboard admin, audit logs. "
            "Chaque tenant a ses propres données isolées via row-level security ou schema séparé."
        ),
        "reference_repos": [
            "https://github.com/fastapi/full-stack-fastapi-template",
            "https://github.com/sahat/hackathon-starter",
            "https://github.com/fastapi-users/fastapi-users",
        ],
        "services": [
            "auth_service",
            "tenant_service",
            "billing_service",
            "admin_service",
            "notification_service",
            "audit_service",
        ],
        "communication": [
            "REST/JSON",
            "SQL (ORM)",
            "Stripe webhooks",
            "Email (SMTP/SES)",
        ],
        "base_patterns": [
            "crud", "auth_jwt", "auth_oauth2", "rbac",
            "multi_tenant", "billing_stripe", "webhook_handler",
            "audit_log", "email_notification", "rate_limiting",
            "pagination", "error_handling",
        ],
        "tech_stacks": {
            "python": "fastapi+sqlalchemy+pydantic_v2",
            "typescript": "express+prisma",
        },
        "typical_entities": [
            "Organization", "Member", "Subscription", "Invoice",
        ],
        "scaling_pattern": "horizontal_stateless + db_per_tenant_or_rls",
        "complexity": "complex",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 3. Bot Platform — Discord/Slack/Telegram bot + event handlers
    # ══════════════════════════════════════════════════════════════════════════
    {
        "family": "bot_platform",
        "description": (
            "Plateforme de bot conversationnel (Discord, Slack, Telegram). "
            "Gateway events (messages, reactions, slash commands), "
            "command router, session state, REST API compagnon pour la config, "
            "queue de tâches async pour les opérations longues. "
            "Architecture event-driven avec handlers par type d'événement."
        ),
        "reference_repos": [
            "https://github.com/Rapptz/discord.py",
            "https://github.com/bwmarrin/discordgo",
            "https://github.com/Chainlit/chainlit",
        ],
        "services": [
            "gateway_client",
            "command_router",
            "event_handler_registry",
            "session_manager",
            "rest_api_companion",
            "task_queue",
            "database_layer",
        ],
        "communication": [
            "WebSocket (gateway)",
            "REST/JSON (companion API)",
            "Redis pub/sub (inter-service)",
            "Task queue (Celery/asynq/Tokio tasks)",
        ],
        "base_patterns": [
            "websocket_client", "event_dispatcher", "command_handler",
            "session_state", "crud", "route", "background_task",
            "rate_limiting", "config", "error_handling",
            "embed_builder", "permission_check",
        ],
        "tech_stacks": {
            "python": "discord.py+fastapi+sqlalchemy+redis",
            "go": "discordgo+gin+gorm+redis",
            "typescript": "discord.js+express+prisma+redis",
        },
        "typical_entities": [
            "Command", "Handler", "Session", "Guild", "Channel",
        ],
        "scaling_pattern": "sharded_gateway + horizontal_api",
        "complexity": "medium",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 4. Realtime Collaboration — WebSocket + sync engine
    # ══════════════════════════════════════════════════════════════════════════
    {
        "family": "realtime_collab",
        "description": (
            "Application collaborative en temps réel — chat, whiteboard, "
            "éditeur partagé, jeu multijoueur léger. WebSocket bidirectionnel, "
            "state synchronization (CRDT ou OT), presence system (qui est en ligne), "
            "room/channel management. Nécessite une gestion fine des connexions "
            "et de la latence."
        ),
        "reference_repos": [
            "https://github.com/tokio-rs/axum",
            "https://github.com/gorilla/websocket",
        ],
        "services": [
            "websocket_server",
            "room_manager",
            "presence_service",
            "sync_engine",
            "message_broker",
            "persistence_layer",
            "rest_api",
        ],
        "communication": [
            "WebSocket (bidirectional)",
            "Redis pub/sub (cross-instance broadcast)",
            "REST/JSON (room management)",
            "SQL (persistence)",
        ],
        "base_patterns": [
            "websocket_server", "room_management", "presence_tracking",
            "message_broadcast", "connection_lifecycle", "heartbeat",
            "reconnection", "crud", "auth_jwt", "rate_limiting",
        ],
        "tech_stacks": {
            "python": "fastapi+websockets+redis",
            "go": "gin+gorilla/websocket+redis",
            "typescript": "express+ws+redis",
            "rust": "axum+tokio-tungstenite+redis",
        },
        "typical_entities": [
            "Room", "Participant", "Message", "Presence",
        ],
        "scaling_pattern": "sticky_sessions + redis_broadcast",
        "complexity": "complex",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 5. RAG Platform — Vector DB + retrieval + LLM chain
    # ══════════════════════════════════════════════════════════════════════════
    {
        "family": "rag_platform",
        "description": (
            "Plateforme RAG (Retrieval-Augmented Generation) — ingestion de documents, "
            "chunking, embedding, stockage vectoriel, retrieval, LLM chain pour la réponse. "
            "Pipeline d'ingestion offline (PDF/HTML/Markdown → chunks → vectors), "
            "API de recherche temps réel, cache Redis pour les queries fréquentes, "
            "UI Streamlit ou React pour l'interaction."
        ),
        "reference_repos": [
            "https://github.com/langchain-ai/langchain",
            "https://github.com/Chainlit/chainlit",
        ],
        "services": [
            "ingestion_pipeline",
            "chunker",
            "embedder_service",
            "vector_store",
            "retriever",
            "llm_chain",
            "cache_layer",
            "rest_api",
            "ui_layer",
        ],
        "communication": [
            "REST/JSON (API)",
            "Vector DB (Qdrant/Chroma/Pinecone)",
            "Redis (cache)",
            "LLM API (OpenAI/OpenRouter)",
            "File I/O (document ingestion)",
        ],
        "base_patterns": [
            "document_loader", "text_chunker", "embedding_service",
            "vector_upsert", "vector_search", "llm_chain",
            "prompt_template", "cache_layer", "crud", "route",
            "streaming_response", "config", "error_handling",
        ],
        "tech_stacks": {
            "python": "fastapi+langchain+qdrant+redis+streamlit",
            "typescript": "express+langchain.js+pinecone+redis",
        },
        "typical_entities": [
            "Document", "Chunk", "Collection", "Query", "Response",
        ],
        "scaling_pattern": "async_ingestion + cached_retrieval",
        "complexity": "medium",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 6. AI Chat Platform — LLM + session + streaming
    # ══════════════════════════════════════════════════════════════════════════
    {
        "family": "ai_chat",
        "description": (
            "Plateforme de chat IA — conversation multi-tour avec un LLM "
            "(local ou cloud). Gestion de session/historique, streaming SSE/WebSocket "
            "des réponses token par token, system prompts configurables, "
            "tool use / function calling, modèles interchangeables. "
            "UI Streamlit/Gradio ou React avec streaming."
        ),
        "reference_repos": [
            "https://github.com/Chainlit/chainlit",
            "https://github.com/ggerganov/llama.cpp",
        ],
        "services": [
            "chat_api",
            "session_manager",
            "llm_router",
            "tool_executor",
            "history_store",
            "streaming_handler",
            "ui_layer",
        ],
        "communication": [
            "REST/JSON (API)",
            "SSE or WebSocket (streaming)",
            "LLM API (OpenAI/Anthropic/local)",
            "SQL or Redis (session/history)",
        ],
        "base_patterns": [
            "chat_completion", "streaming_response", "session_management",
            "conversation_history", "system_prompt", "tool_use",
            "function_calling", "model_router", "crud", "route",
            "auth_jwt", "rate_limiting", "config",
        ],
        "tech_stacks": {
            "python": "fastapi+openai+redis+streamlit",
            "typescript": "express+openai+redis+react",
        },
        "typical_entities": [
            "Conversation", "Turn", "Agent", "Tool",
        ],
        "scaling_pattern": "stateless_api + session_in_redis",
        "complexity": "medium",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 7. ML Pipeline — Training + inference + model registry
    # ══════════════════════════════════════════════════════════════════════════
    {
        "family": "ml_pipeline",
        "description": (
            "Pipeline de machine learning complet — ingestion de données, "
            "preprocessing, training, evaluation, model registry, serving/inference. "
            "Event streaming (Redis Streams ou Kafka) pour le pipeline async, "
            "REST API pour l'inférence temps réel, monitoring des performances du modèle. "
            "Gestion des artefacts (modèles, datasets, métriques)."
        ),
        "reference_repos": [
            "https://github.com/huggingface/peft",
            "https://github.com/burn-rs/burn",
        ],
        "services": [
            "data_ingestion",
            "preprocessor",
            "trainer",
            "evaluator",
            "model_registry",
            "inference_api",
            "monitoring_service",
            "artifact_store",
        ],
        "communication": [
            "REST/JSON (inference API)",
            "Redis Streams or Kafka (pipeline events)",
            "S3/MinIO (artifact storage)",
            "SQL (metadata/registry)",
        ],
        "base_patterns": [
            "data_loader", "preprocessor", "training_loop",
            "model_evaluation", "model_registry", "inference_endpoint",
            "batch_inference", "monitoring", "crud", "route",
            "background_task", "config", "error_handling",
        ],
        "tech_stacks": {
            "python": "fastapi+pytorch+redis+sqlalchemy",
            "rust": "axum+burn+sqlx",
        },
        "typical_entities": [
            "Dataset", "Model", "Experiment", "Prediction",
        ],
        "scaling_pattern": "gpu_workers + async_pipeline + api_gateway",
        "complexity": "complex",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 8. Marketplace — Catalog + orders + payments + reviews
    # ══════════════════════════════════════════════════════════════════════════
    {
        "family": "marketplace",
        "description": (
            "Place de marché (e-commerce, services, digital goods). "
            "Catalogue produits avec recherche et filtres, panier, checkout, "
            "paiement (Stripe), gestion vendeurs/acheteurs, reviews et ratings, "
            "notifications (email + push), dashboard vendeur et admin."
        ),
        "reference_repos": [
            "https://github.com/sahat/hackathon-starter",
            "https://github.com/hagopj13/node-express-boilerplate",
        ],
        "services": [
            "catalog_service",
            "search_service",
            "cart_service",
            "checkout_service",
            "payment_service",
            "seller_service",
            "review_service",
            "notification_service",
            "admin_service",
        ],
        "communication": [
            "REST/JSON",
            "SQL (ORM)",
            "Stripe webhooks",
            "Redis (cart/session cache)",
            "Email (SMTP/SES)",
            "Full-text search (Elasticsearch/Meilisearch)",
        ],
        "base_patterns": [
            "crud", "auth_jwt", "auth_oauth2", "rbac",
            "full_text_search", "pagination", "filtering",
            "cart_management", "checkout_flow", "billing_stripe",
            "webhook_handler", "review_rating", "email_notification",
            "image_upload", "error_handling",
        ],
        "tech_stacks": {
            "python": "fastapi+sqlalchemy+pydantic_v2+stripe+redis",
            "typescript": "express+prisma+stripe+redis",
            "go": "gin+gorm+stripe+redis",
        },
        "typical_entities": [
            "Product", "Seller", "Buyer", "Cart", "Transaction", "Review",
        ],
        "scaling_pattern": "microservices_or_modular_monolith",
        "complexity": "complex",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 9. Fintech API — Transactions + ledger + compliance
    # ══════════════════════════════════════════════════════════════════════════
    {
        "family": "fintech_api",
        "description": (
            "API financière — gestion de comptes, transactions, ledger double-entry, "
            "compliance KYC/AML, webhooks sortants pour les événements financiers. "
            "Contraintes fortes : idempotence sur chaque opération, audit trail complet, "
            "isolation transactionnelle, chiffrement des données sensibles."
        ),
        "reference_repos": [
            "https://github.com/svix/svix-webhooks",
        ],
        "services": [
            "account_service",
            "transaction_service",
            "ledger_service",
            "compliance_service",
            "webhook_dispatcher",
            "audit_service",
            "admin_service",
        ],
        "communication": [
            "REST/JSON (API)",
            "SQL with SERIALIZABLE isolation",
            "Webhooks (outbound events)",
            "Message queue (idempotent processing)",
        ],
        "base_patterns": [
            "crud", "auth_jwt", "rbac", "double_entry_ledger",
            "idempotency_key", "transaction_processing",
            "webhook_dispatcher", "audit_log", "encryption",
            "rate_limiting", "pagination", "error_handling",
        ],
        "tech_stacks": {
            "python": "fastapi+sqlalchemy+pydantic_v2+celery",
            "go": "gin+gorm+asynq",
            "rust": "axum+sqlx+tokio",
        },
        "typical_entities": [
            "Account", "Transaction", "LedgerEntry", "Webhook",
        ],
        "scaling_pattern": "serializable_txn + idempotent_workers",
        "complexity": "complex",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 10. Streaming Platform — Catalog + streaming + recommendations
    # ══════════════════════════════════════════════════════════════════════════
    {
        "family": "streaming_platform",
        "description": (
            "Plateforme de streaming média (audio ou vidéo). "
            "Catalogue de contenu, moteur de recherche, streaming adaptatif (HLS/DASH), "
            "système de recommandation, gestion des playlists/collections, "
            "historique de lecture, abonnements. Architecture read-heavy avec cache agressif."
        ),
        "reference_repos": [
            "https://github.com/sentriz/gonic",
        ],
        "services": [
            "catalog_service",
            "search_service",
            "streaming_service",
            "recommendation_engine",
            "playlist_service",
            "playback_history",
            "subscription_service",
            "cdn_integration",
        ],
        "communication": [
            "REST/JSON (API)",
            "HLS/DASH (media streaming)",
            "Redis (cache + session)",
            "SQL (metadata)",
            "Full-text search (Meilisearch)",
            "CDN (media delivery)",
        ],
        "base_patterns": [
            "crud", "auth_jwt", "full_text_search", "pagination",
            "media_streaming", "playlist_management",
            "recommendation_engine", "playback_tracking",
            "cache_layer", "billing_stripe", "rate_limiting",
        ],
        "tech_stacks": {
            "python": "fastapi+sqlalchemy+redis+meilisearch",
            "go": "gin+gorm+redis+meilisearch",
            "typescript": "express+prisma+redis",
        },
        "typical_entities": [
            "Track", "Album", "Artist", "Playlist", "PlaybackEvent",
        ],
        "scaling_pattern": "cdn + read_replicas + aggressive_cache",
        "complexity": "complex",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 11. CMS Platform — Content management + headless API
    # ══════════════════════════════════════════════════════════════════════════
    {
        "family": "cms_platform",
        "description": (
            "Système de gestion de contenu headless — création et gestion "
            "de contenu structuré (articles, pages, media), API REST ou GraphQL "
            "pour la consommation front-end, système de révisions/drafts, "
            "gestion des médias (upload, resize, CDN), rôles éditoriaux "
            "(auteur, éditeur, admin), workflow de publication."
        ),
        "reference_repos": [
            "https://github.com/gothinkster/node-express-realworld-example-app",
        ],
        "services": [
            "content_service",
            "media_service",
            "revision_service",
            "publication_workflow",
            "taxonomy_service",
            "api_gateway",
            "admin_ui",
        ],
        "communication": [
            "REST/JSON or GraphQL",
            "SQL (content storage)",
            "S3/MinIO (media storage)",
            "CDN (media delivery)",
            "Webhooks (publication events)",
        ],
        "base_patterns": [
            "crud", "auth_jwt", "rbac", "image_upload",
            "media_processing", "revision_history", "draft_publish_workflow",
            "taxonomy_tags", "full_text_search", "pagination",
            "webhook_dispatcher", "cache_layer", "error_handling",
        ],
        "tech_stacks": {
            "python": "fastapi+sqlalchemy+pydantic_v2+s3",
            "typescript": "express+prisma+s3",
            "go": "gin+gorm+s3",
        },
        "typical_entities": [
            "Content", "Revision", "Media", "Taxonomy", "Author",
        ],
        "scaling_pattern": "read_cache + cdn_media + async_processing",
        "complexity": "medium",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 12. DevTools Platform — CLI + API + plugins
    # ══════════════════════════════════════════════════════════════════════════
    {
        "family": "devtools_platform",
        "description": (
            "Plateforme d'outils développeur — CLI interactive, REST API, "
            "système de plugins/extensions, intégration CI/CD (webhooks GitHub/GitLab), "
            "configuration par fichier (YAML/TOML). Architecture orientée commandes "
            "avec plugin registry et middleware chain."
        ),
        "reference_repos": [
            "https://github.com/modelcontextprotocol/python-sdk",
            "https://github.com/modelcontextprotocol/typescript-sdk",
        ],
        "services": [
            "cli_core",
            "api_server",
            "plugin_registry",
            "plugin_loader",
            "config_manager",
            "webhook_receiver",
            "auth_service",
        ],
        "communication": [
            "REST/JSON (API)",
            "stdio/JSON-RPC (plugin protocol)",
            "Webhooks (CI/CD events)",
            "File I/O (config files)",
        ],
        "base_patterns": [
            "cli_command_router", "plugin_system", "middleware_chain",
            "config_loader", "webhook_handler", "crud", "route",
            "auth_jwt", "auth_api_key", "rate_limiting",
            "json_rpc", "error_handling",
        ],
        "tech_stacks": {
            "python": "fastapi+click+pydantic_v2",
            "typescript": "express+commander+zod",
            "go": "gin+cobra",
            "rust": "axum+clap",
        },
        "typical_entities": [
            "Plugin", "Command", "Config", "Hook",
        ],
        "scaling_pattern": "stateless_api + plugin_isolation",
        "complexity": "medium",
    },
]


# ─── Ingestion ────────────────────────────────────────────────────────────────

def main() -> None:
    dry_run = "--dry-run" in sys.argv

    print(f"{'DRY RUN — ' if dry_run else ''}Ingestion architectures → {KB_PATH}/{COLLECTION}")
    print(f"Familles à ingérer : {len(ARCHITECTURES)}\n")

    client = QdrantClient(path=KB_PATH)

    # Vérifier que la collection existe
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION not in existing:
        print(f"❌ Collection '{COLLECTION}' introuvable. Lancer setup_collections.py d'abord.")
        sys.exit(1)

    count_before = client.count(COLLECTION).count
    print(f"Points avant : {count_before}")

    # Cleanup ancien tag si re-run
    try:
        client.delete(
            collection_name=COLLECTION,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[FieldCondition(key="_tag", match=MatchValue(value=TAG))]
                )
            ),
        )
        count_after_cleanup = client.count(COLLECTION).count
        if count_after_cleanup < count_before:
            print(f"Cleanup ancien tag '{TAG}' : {count_before - count_after_cleanup} points supprimés")
            count_before = count_after_cleanup
    except Exception:
        pass  # pas de points avec ce tag = OK

    # Préparer les points
    points = []
    for arch in ARCHITECTURES:
        # L'embedding est fait sur la description + family + services pour une bonne
        # recherche sémantique (ex: "Discord bot with slash commands" → bot_platform)
        embed_text = (
            f"{arch['family']}: {arch['description']} "
            f"Services: {', '.join(arch['services'])}. "
            f"Communication: {', '.join(arch['communication'])}. "
            f"Patterns: {', '.join(arch['base_patterns'])}."
        )
        vector = embed_document(embed_text)

        payload = {
            "family": arch["family"],
            "description": arch["description"],
            "reference_repos": arch["reference_repos"],
            "services": arch["services"],
            "communication": arch["communication"],
            "base_patterns": arch["base_patterns"],
            "tech_stacks": arch["tech_stacks"],
            "typical_entities": arch["typical_entities"],
            "scaling_pattern": arch["scaling_pattern"],
            "complexity": arch["complexity"],
            "created_at": int(time.time()),
            "_tag": TAG,
        }

        point = PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload=payload,
        )
        points.append(point)
        print(f"  ✅ {arch['family']:25} — {len(arch['services'])} services, {len(arch['base_patterns'])} base patterns")

    # Upsert
    if not dry_run:
        client.upsert(collection_name=COLLECTION, points=points)
        count_after = client.count(COLLECTION).count
    else:
        count_after = count_before

    # ── Rapport ──────────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print(f"  RAPPORT INGESTION ARCHITECTURES")
    print("=" * 60)
    print(f"  Mode              : {'DRY_RUN' if dry_run else 'PRODUCTION'}")
    print(f"  Familles ingérées : {len(ARCHITECTURES)}")
    print(f"  Points avant      : {count_before}")
    print(f"  Points après      : {count_after}")
    print()

    # Verification query : chercher "Discord bot" → devrait retourner bot_platform
    if not dry_run:
        from embedder import embed_query
        test_queries = [
            ("Discord bot with slash commands", "bot_platform"),
            ("E-commerce store with Stripe payments", "marketplace"),
            ("Document search with embeddings and LLM", "rag_platform"),
            ("REST API with CRUD endpoints", "crud_api"),
            ("Real-time chat with WebSocket", "realtime_collab"),
            ("ML model training and serving", "ml_pipeline"),
        ]

        print("  Verification queries :")
        print(f"  {'Query':<50} {'Expected':<20} {'Got':<20} {'OK':>4}")
        print(f"  {'-'*50} {'-'*20} {'-'*20} {'-'*4}")

        all_ok = True
        for query, expected in test_queries:
            vec = embed_query(query)
            results = client.query_points(
                collection_name=COLLECTION,
                query=vec,
                limit=1,
                with_payload=True,
            )
            if results.points:
                got = results.points[0].payload["family"]
                score = results.points[0].score
                ok = got == expected
                if not ok:
                    all_ok = False
                print(f"  {query[:49]:<50} {expected:<20} {got:<20} {'✅' if ok else '❌'} ({score:.4f})")
            else:
                all_ok = False
                print(f"  {query[:49]:<50} {expected:<20} {'<none>':<20} ❌")

        print()
        print(f"  Verdict : {'✅ PASS' if all_ok else '⚠️  Certaines queries ne matchent pas (acceptable si scores proches)'}")

    print("=" * 60)


if __name__ == "__main__":
    main()
