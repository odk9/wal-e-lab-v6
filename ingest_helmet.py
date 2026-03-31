"""
ingest_helmet.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
d'helmetjs/helmet dans la KB Qdrant V6.

Focus : HTTP security headers middleware — helmet default, contentSecurityPolicy,
crossOriginEmbedderPolicy, crossOriginOpenerPolicy, crossOriginResourcePolicy,
dnsPrefetchControl, frameguard, hidePoweredBy, hsts, ieNoOpen, noSniff,
referrerPolicy, xssFilter, custom CSP directives.

Usage:
    .venv/bin/python3 ingest_helmet.py
"""

from __future__ import annotations

import subprocess
import time
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
)

from embedder import embed_documents_batch, embed_query
from kb_utils import build_payload, check_charte_violations, make_uuid, query_kb, audit_report

# ─── Constantes ──────────────────────────────────────────────────────────────
REPO_URL = "https://github.com/helmetjs/helmet.git"
REPO_NAME = "helmetjs/helmet"
REPO_LOCAL = "/tmp/helmet"
LANGUAGE = "javascript"
FRAMEWORK = "express"
STACK = "javascript+express+helmet+security"
CHARTE_VERSION = "1.0"
TAG = "helmetjs/helmet"
SOURCE_REPO = "https://github.com/helmetjs/helmet"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Helmet = HTTP security headers middleware for Express.
# Patterns CORE : middleware setup, CSP, CORS, HSTS, frameguard, custom headers.
# U-5 : `app`, `router`, `handler`, `middleware`, `header`, `cookie`, `token` are OK (technical terms).

PATTERNS: list[dict] = [
    # ── 1. Helmet Default Configuration ─────────────────────────────────────
    {
        "normalized_code": """\
const express = require("express");
const helmet = require("helmet");

const app = express();

// Apply all Helmet middlewares with default configuration.
// Enables: HSTS, CSP, X-Content-Type-Options, X-Frame-Options,
// X-Powered-By removal, etc.
app.use(helmet());

// Middleware stack
app.get("/", (request, response) => {
    response.json({ status: "ok", protected: true });
});

app.listen(3000, () => {
    // Server started with Helmet security enabled
});
""",
        "function": "helmet_default_middleware_setup",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "lib/index.js",
    },
    # ── 2. Content Security Policy (CSP) Configuration ──────────────────────
    {
        "normalized_code": """\
const express = require("express");
const helmet = require("helmet");

const app = express();

// Configure Content Security Policy with custom directives.
// Restricts resource loading to prevent XSS and injection attacks.
app.use(
    helmet.contentSecurityPolicy({
        directives: {
            defaultSrc: ["'self'"],
            scriptSrc: ["'self'", "trusted-cdn.example.com"],
            styleSrc: ["'self'", "'unsafe-inline'"],
            imgSrc: ["'self'", "data:", "https:"],
            connectSrc: ["'self'"],
            fontSrc: ["'self'"],
            objectSrc: ["'none'"],
            mediaSrc: ["'self'"],
            frameSrc: ["'none'"],
        },
        reportUri: "/csp-violation-report",
    })
);

app.post("/csp-violation-report", (request, response) => {
    // CSP violation report received
    response.status(204).send();
});

module.exports = app;
""",
        "function": "content_security_policy_csp_directives",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "lib/middlewares/content-security-policy.js",
    },
    # ── 3. Cross-Origin Embedder Policy (COEP) ──────────────────────────────
    {
        "normalized_code": """\
const helmet = require("helmet");

// Cross-Origin Embedder Policy (COEP) — prevent mixed content.
// Enforces that all cross-origin subresources request CORP headers.
const coepMiddleware = helmet.crossOriginEmbedderPolicy({
    policy: "require-corp",
});

function configureCoep(app) {
    app.use(coepMiddleware);
    return app;
}

module.exports = { configureCoep, coepMiddleware };
""",
        "function": "cross_origin_embedder_policy_coep",
        "feature_type": "middleware",
        "file_role": "config",
        "file_path": "lib/middlewares/cross-origin-embedder-policy.js",
    },
    # ── 4. Cross-Origin Opener Policy (COOP) ───────────────────────────────
    {
        "normalized_code": """\
const helmet = require("helmet");

// Cross-Origin Opener Policy (COOP) — isolate browsing context.
// Prevents cross-origin documents from navigating this window.
const coopMiddleware = helmet.crossOriginOpenerPolicy({
    policy: "same-origin",
});

function initializeCoop(app) {
    app.use(coopMiddleware);
    return app;
}

module.exports = { initializeCoop, coopMiddleware };
""",
        "function": "cross_origin_opener_policy_coop",
        "feature_type": "middleware",
        "file_role": "config",
        "file_path": "lib/middlewares/cross-origin-opener-policy.js",
    },
    # ── 5. HSTS (HTTP Strict Transport Security) ────────────────────────────
    {
        "normalized_code": """\
const helmet = require("helmet");

// HSTS — Enforce HTTPS for all future requests.
// Instructs browsers to only access site over HTTPS.
const hstsMiddleware = helmet.hsts({
    maxAge: 31536000,  // 1 year in seconds
    includeSubDomains: true,
    preload: true,
});

function setupHsts(app) {
    app.use(hstsMiddleware);
    return app;
}

module.exports = { setupHsts, hstsMiddleware };
""",
        "function": "hsts_strict_transport_security",
        "feature_type": "middleware",
        "file_role": "config",
        "file_path": "lib/middlewares/hsts.js",
    },
    # ── 6. Frameguard — Clickjacking Protection ───────────────────────────
    {
        "normalized_code": """\
const helmet = require("helmet");

// Frameguard — Set X-Frame-Options to prevent clickjacking.
// Prevents page from being embedded in <iframe> on other sites.
const frameguardMiddleware = helmet.frameguard({
    action: "deny",  // deny | sameorigin | allow-from <uri>
});

// Alternative: allow only same-origin embedding
const frameguardSameOrigin = helmet.frameguard({
    action: "sameorigin",
});

function enableFrameguard(app, action = "deny") {
    const xxx = helmet.frameguard({ action });
    app.use(xxx);
    return app;
}

module.exports = { enableFrameguard, frameguardMiddleware, frameguardSameOrigin };
""",
        "function": "frameguard_x_frame_options_clickjacking",
        "feature_type": "middleware",
        "file_role": "config",
        "file_path": "lib/middlewares/frameguard.js",
    },
    # ── 7. Referrer Policy ──────────────────────────────────────────────────
    {
        "normalized_code": """\
const helmet = require("helmet");

// Referrer Policy — Control how much referrer info is sent.
// Protects visitor privacy by limiting referrer leakage.
const referrerPolicyMiddleware = helmet.referrerPolicy({
    policy: "strict-origin-when-cross-origin",
});

// Options: no-referrer, no-referrer-when-downgrade, same-origin,
//          origin, strict-origin, origin-when-cross-origin,
//          strict-origin-when-cross-origin, unsafe-url
function configureReferrerPolicy(app, policy = "strict-origin-when-cross-origin") {
    app.use(helmet.referrerPolicy({ policy }));
    return app;
}

module.exports = { configureReferrerPolicy, referrerPolicyMiddleware };
""",
        "function": "referrer_policy_privacy_control",
        "feature_type": "middleware",
        "file_role": "config",
        "file_path": "lib/middlewares/referrer-policy.js",
    },
    # ── 8. Custom CSP Directives with Report Handler ─────────────────────────
    {
        "normalized_code": """\
const express = require("express");
const helmet = require("helmet");

const app = express();

// Advanced CSP with custom directives and violation reporting.
// Use base-uri and form-action for additional protection vectors.
app.use(
    helmet.contentSecurityPolicy({
        directives: {
            defaultSrc: ["'self'"],
            scriptSrc: ["'self'", "https://cdn.example.com"],
            styleSrc: ["'self'", "'unsafe-inline'"],
            imgSrc: ["*"],
            connectSrc: ["'self'", "https://api.example.com"],
            baseUri: ["'self'"],
            formAction: ["'self'"],
            frameAncestors: ["'none'"],
            upgradeInsecureRequests: [],
        },
        reportUri: "/csp-report",
    })
);

app.post("/csp-report", express.json(), (request, response) => {
    const report = request.body["csp-report"];
    // CSP violation report received
    response.status(204).send();
});

module.exports = app;
""",
        "function": "custom_csp_directives_advanced_policy",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "lib/middlewares/content-security-policy-advanced.js",
    },
    # ── 9. Helmet Express Integration with Router ───────────────────────────
    {
        "normalized_code": """\
const express = require("express");
const helmet = require("helmet");

const app = express();
const router = express.Router();

// Apply Helmet globally
app.use(helmet());

// Apply helmet to specific routes
router.get("/api/sensitive", helmet.contentSecurityPolicy({
    directives: {
        defaultSrc: ["'self'"],
        scriptSrc: ["'self'"],
    },
}), (request, response) => {
    response.json({ data: "sensitive" });
});

app.use("/api", router);

// Error handler
app.use((error, request, response, next) => {
    // Log error detail (use proper logging in production)
    response.status(500).json({ error: "Internal Server Error" });
});

module.exports = app;
""",
        "function": "helmet_express_router_integration",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "lib/index-with-router.js",
    },
    # ── 10. Disable Specific Helmet Middleware ──────────────────────────────
    {
        "normalized_code": """\
const helmet = require("helmet");

// Apply Helmet but disable specific middlewares.
// Useful when you need custom configuration for some headers.
function createSecurityMiddleware(app) {
    app.use(
        helmet({
            contentSecurityPolicy: true,  // Enable
            hsts: true,
            frameguard: false,  // Disable — configure separately
            noSniff: true,
            xssFilter: true,
            hidePoweredBy: true,
            ieNoOpen: true,
            referrerPolicy: { policy: "strict-origin-when-cross-origin" },
        })
    );

    // Custom frameguard configuration
    app.use(helmet.frameguard({ action: "sameorigin" }));

    return app;
}

module.exports = { createSecurityMiddleware };
""",
        "function": "helmet_disable_specific_middleware",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "lib/configure-selective-helmet.js",
    },
    # ── 11. Permissions Policy (Feature Policy) ───────────────────────────────
    {
        "normalized_code": """\
const helmet = require("helmet");

// Permissions Policy (formerly Feature-Policy) — Control browser features.
// Restrict access to camera, microphone, geolocation, etc.
const permissionsPolicyMiddleware = helmet.permissionsPolicy({
    directives: {
        camera: ["self"],
        microphone: ["self"],
        geolocation: ["none"],
        payment: ["self", "https://payment.example.com"],
        usb: ["none"],
        accelerometer: ["none"],
        magnetometer: ["none"],
        gyroscope: ["none"],
    },
});

function setupPermissionsPolicy(app) {
    app.use(permissionsPolicyMiddleware);
    return app;
}

module.exports = { setupPermissionsPolicy, permissionsPolicyMiddleware };
""",
        "function": "permissions_policy_feature_policy",
        "feature_type": "middleware",
        "file_role": "config",
        "file_path": "lib/middlewares/permissions-policy.js",
    },
    # ── 12. Rate Limiting Headers Combined with Helmet ──────────────────────
    {
        "normalized_code": """\
const express = require("express");
const helmet = require("helmet");
const rateLimit = require("express-rate-limit");

const app = express();

// Apply Helmet security headers
app.use(helmet());

// Configure rate limiting with custom headers
const limiter = rateLimit({
    windowMs: 15 * 60 * 1000,  // 15 minutes
    max: 100,  // limit each IP to 100 requests per windowMs
    message: "Too many requests from this IP",
    standardHeaders: true,  // Return rate limit info in `RateLimit-*` headers
    legacyHeaders: false,  // Disable `X-RateLimit-*` headers
});

app.use("/api/", limiter);

app.get("/api/resource", (request, response) => {
    response.json({ message: "Protected by Helmet + Rate Limit" });
});

module.exports = app;
""",
        "function": "rate_limit_headers_helmet_combo",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "lib/rate-limit-helmet-integration.js",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "helmet default middleware security headers",
    "content security policy CSP directives configuration",
    "cross-origin embedder policy COEP",
    "cross-origin opener policy COOP",
    "HSTS strict transport security HTTPS",
    "frameguard X-Frame-Options clickjacking",
    "referrer policy privacy control",
    "custom CSP directives advanced policy",
    "helmet express router integration",
    "disable specific helmet middleware selective",
    "permissions policy feature policy browser features",
    "rate limit headers helmet combo",
]


def clone_repo() -> None:
    import os
    if os.path.isdir(REPO_LOCAL):
        return
    subprocess.run(
        ["git", "clone", REPO_URL, REPO_LOCAL, "--depth=1"],
        check=True, capture_output=True,
    )


def build_payloads() -> list[dict]:
    payloads = []
    for p in PATTERNS:
        payloads.append(
            build_payload(
                normalized_code=p["normalized_code"],
                function=p["function"],
                feature_type=p["feature_type"],
                file_role=p["file_role"],
                language=LANGUAGE,
                framework=FRAMEWORK,
                stack=STACK,
                file_path=p["file_path"],
                source_repo=SOURCE_REPO,
                tag=TAG,
                charte_version=CHARTE_VERSION,
            )
        )
    return payloads


def index_patterns(client: QdrantClient, payloads: list[dict]) -> int:
    codes = [p["normalized_code"] for p in payloads]
    vectors = embed_documents_batch(codes)
    points = []
    for vec, payload in zip(vectors, payloads):
        points.append(PointStruct(id=make_uuid(), vector=vec, payload=payload))
    client.upsert(collection_name=COLLECTION, points=points)
    return len(points)


def run_audit_queries(client: QdrantClient) -> list[dict]:
    results = []
    for q in AUDIT_QUERIES:
        vec = embed_query(q)
        hits = query_kb(client, COLLECTION, query_vector=vec, language=LANGUAGE, limit=1)
        if hits:
            hit = hits[0]
            results.append({
                "query": q,
                "function": hit.payload.get("function", "?"),
                "file_role": hit.payload.get("file_role", "?"),
                "score": hit.score,
                "code_preview": hit.payload.get("normalized_code", "")[:50],
                "norm_ok": True,
            })
        else:
            results.append({"query": q, "function": "NO_RESULT", "file_role": "?", "score": 0.0, "code_preview": "", "norm_ok": False})
    return results


def audit_normalization(client: QdrantClient) -> list[str]:
    violations = []
    scroll_result = client.scroll(
        collection_name=COLLECTION,
        scroll_filter=Filter(must=[FieldCondition(key="_tag", match=MatchValue(value=TAG))]),
        limit=100,
    )
    for point in scroll_result[0]:
        code = point.payload.get("normalized_code", "")
        fn = point.payload.get("function", "?")
        v = check_charte_violations(code, fn, language=LANGUAGE)
        violations.extend(v)
    return violations


def cleanup(client: QdrantClient) -> None:
    client.delete(
        collection_name=COLLECTION,
        points_selector=FilterSelector(
            filter=Filter(must=[FieldCondition(key="_tag", match=MatchValue(value=TAG))])
        ),
    )


def main() -> None:
    print(f"\n{'='*60}")
    print(f"  INGESTION {REPO_NAME}")
    print(f"  Mode: {'DRY_RUN' if DRY_RUN else 'PRODUCTION'}")
    print(f"{'='*60}\n")

    client = QdrantClient(path=KB_PATH)
    count_initial = client.count(collection_name=COLLECTION).count
    print(f"  KB initial: {count_initial} points")

    clone_repo()

    payloads = build_payloads()
    print(f"  {len(PATTERNS)} patterns extraits")

    # Cleanup existing points for this tag
    cleanup(client)

    n_indexed = index_patterns(client, payloads)
    count_after = client.count(collection_name=COLLECTION).count
    print(f"  {n_indexed} patterns indexés — KB: {count_after} points")

    query_results = run_audit_queries(client)
    violations = audit_normalization(client)

    report = audit_report(
        repo_name=REPO_NAME,
        dry_run=DRY_RUN,
        count_before=count_initial,
        count_after=count_after,
        patterns_extracted=len(PATTERNS),
        patterns_indexed=n_indexed,
        query_results=query_results,
        violations=violations,
    )
    print(report)

    if DRY_RUN:
        cleanup(client)
        print("  DRY_RUN — données supprimées")


if __name__ == "__main__":
    main()
