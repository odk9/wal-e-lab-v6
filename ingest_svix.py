"""
ingest_svix.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de svix/svix-webhooks dans la KB Qdrant V6.

Focus : Webhook management patterns (endpoint creation, message delivery, signature
verification, event filtering, retry logic, consumer verification, batch operations,
endpoint statistics).

Usage:
    .venv/bin/python3 ingest_svix.py
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
REPO_URL = "https://github.com/svix/svix-webhooks.git"
REPO_NAME = "svix/svix-webhooks"
REPO_LOCAL = "/tmp/svix-webhooks"
LANGUAGE = "typescript"
FRAMEWORK = "generic"
STACK = "typescript+svix+webhook"
CHARTE_VERSION = "1.0"
TAG = "svix/svix-webhooks"
SOURCE_REPO = "https://github.com/svix/svix-webhooks"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Svix = Webhook platform library.
# Patterns CORE : webhook endpoint management, message delivery, signature verification,
# event filtering, retry strategies, consumer verification, batch operations, statistics.
# U-5 : `webhook`, `endpoint`, `message`, `client`, `event`, `signature` sont OK (termes techniques).

PATTERNS: list[dict] = [
    # ── 1. Create Webhook Endpoint ───────────────────────────────────────────
    {
        "normalized_code": """\
import asyncio
from typing import Optional

from svix.client import Svix
from svix.api_resources.endpoint import EndpointIn, EndpointOut


async def create_webhook_endpoint(
    svix_auth_token: str,
    url: str,
    description: Optional[str] = None,
    version: int = 1,
) -> EndpointOut:
    \"\"\"Create a new webhook endpoint.

    Args:
        svix_auth_token: Svix API authentication token.
        url: HTTP endpoint URL to deliver webhook notifications.
        description: Optional description of the endpoint.
        version: API version (default 1).

    Returns:
        EndpointOut object with endpoint_id, URL, created_at.
    \"\"\"
    client = Svix(svix_auth_token)
    endpoint_in = EndpointIn(url=url, description=description, version=version)
    endpoint = client.endpoint.create(endpoint_in)
    return endpoint
""",
        "function": "create_webhook_endpoint",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "python/svix/webhook/endpoint.py",
    },
    # ── 2. Send Webhook Message ──────────────────────────────────────────────
    {
        "normalized_code": """\
import json
from typing import Optional

from svix.client import Svix
from svix.api_resources.message_endpoint import MessageEndpointOut


async def send_webhook_notification(
    svix_auth_token: str,
    event_type: str,
    payload: dict,
    idempotency_key: Optional[str] = None,
) -> MessageEndpointOut:
    \"\"\"Send a webhook notification to all active endpoints.

    Delivers event_type notification with payload to all webhook endpoints
    subscribed to that signal type.

    Args:
        svix_auth_token: Svix API authentication token.
        event_type: Signal type identifier (e.g., 'account.created').
        payload: JSON-serializable signal payload.
        idempotency_key: Optional key for idempotent delivery.

    Returns:
        MessageEndpointOut with notification_id and delivery status.
    \"\"\"
    client = Svix(svix_auth_token)
    notification = client.message_endpoint.create(
        event_type=event_type,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    return notification
""",
        "function": "send_webhook_notification",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "python/svix/webhook/message.py",
    },
    # ── 3. Verify Webhook Signature ──────────────────────────────────────────
    {
        "normalized_code": """\
import base64
import hashlib
import hmac


class WebhookSignatureVerifier:
    \"\"\"Verify webhook notification signatures using HMAC-SHA256.\"\"\"

    def __init__(self, endpoint_secret: str):
        self.endpoint_secret = endpoint_secret

    def verify(self, msg_id: str, msg_timestamp: str, body: bytes) -> str:
        \"\"\"Verify webhook signature.

        Args:
            msg_id: Notification ID from 'svix-id' header.
            msg_timestamp: Timestamp from 'svix-timestamp' header.
            body: Raw request body.

        Returns:
            Base64-encoded signature.
        \"\"\"
        signed_content = f"{msg_id}.{msg_timestamp}.{body.decode()}"
        secret_bytes = self.endpoint_secret.encode()
        expected = hmac.new(secret_bytes, signed_content.encode(), hashlib.sha256)
        return base64.b64encode(expected.digest()).decode()

    def validate(self, msg_id: str, msg_timestamp: str, body: bytes, signature: str) -> bool:
        \"\"\"Validate webhook signature against provided signature.\"\"\"
        expected = self.verify(msg_id, msg_timestamp, body)
        return hmac.compare_digest(expected, signature)
""",
        "function": "verify_webhook_signature",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "typescript/svix/webhook/verify.ts",
    },
    # ── 4. List Webhook Endpoints ────────────────────────────────────────────
    {
        "normalized_code": """\
from typing import Optional, List

from svix.client import Svix
from svix.api_resources.endpoint import EndpointOut


async def list_webhook_endpoints(
    svix_auth_token: str,
    limit: int = 100,
    offset: int = 0,
) -> List[EndpointOut]:
    \"\"\"List all webhook endpoints with pagination.

    Args:
        svix_auth_token: Svix API authentication token.
        limit: Max endpoints per page (1-100, default 100).
        offset: Number of endpoints to skip (pagination).

    Returns:
        List of EndpointOut objects.
    \"\"\"
    client = Svix(svix_auth_token)
    endpoints = client.endpoint.list(limit=limit, offset=offset)
    return endpoints.data
""",
        "function": "list_webhook_endpoints",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "python/svix/webhook/endpoints_list.py",
    },
    # ── 5. Retry Failed Delivery ─────────────────────────────────────────────
    {
        "normalized_code": """\
from typing import Optional

from svix.client import Svix
from svix.api_resources.message_attempt import MessageAttemptOut


async def retry_failed_delivery(
    svix_auth_token: str,
    message_id: str,
    endpoint_id: str,
) -> MessageAttemptOut:
    \"\"\"Trigger retry of failed webhook notification delivery.

    Retries a notification that previously failed to deliver to an endpoint.
    Svix applies exponential backoff: 5s, 5m, 30m, 2h, 5h, 10h, 10h (max).

    Args:
        svix_auth_token: Svix API authentication token.
        notification_id: ID of the notification to retry.
        endpoint_id: ID of the endpoint that failed.

    Returns:
        MessageAttemptOut with attempt_id and status.
    \"\"\"
    client = Svix(svix_auth_token)
    attempt = client.message_endpoint.retry(
        message_id=message_id,
        endpoint_id=endpoint_id,
    )
    return attempt
""",
        "function": "retry_failed_delivery",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "python/svix/webhook/retry.py",
    },
    # ── 6. Webhook Event Types Query ─────────────────────────────────────────
    {
        "normalized_code": """\
from typing import List, Dict

from svix.client import Svix


async def query_webhook_signal_types(
    svix_auth_token: str,
) -> List[Dict[str, str]]:
    \"\"\"Query available webhook signal types.

    Returns list of supported event_type values that can be sent via webhooks.

    Args:
        svix_auth_token: Svix API authentication token.

    Returns:
        List of dicts with 'name', 'description', 'schema' keys.
    \"\"\"
    client = Svix(svix_auth_token)
    signal_types = client.event_type.list()
    return signal_types.data
""",
        "function": "query_webhook_signal_types",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "python/svix/webhook/event_types.py",
    },
    # ── 7. Endpoint Filter Configuration ─────────────────────────────────────
    {
        "normalized_code": """\
from typing import List, Optional

from svix.client import Svix
from svix.api_resources.endpoint import EndpointUpdate


async def configure_endpoint_filter(
    svix_auth_token: str,
    endpoint_id: str,
    event_types: List[str],
) -> None:
    \"\"\"Configure signal type filter for webhook endpoint.

    Restricts webhook delivery to only specified event_type values.
    If event_types is empty, endpoint receives all signals.

    Args:
        svix_auth_token: Svix API authentication token.
        endpoint_id: ID of endpoint to update.
        event_types: List of allowed signal type names.
    \"\"\"
    client = Svix(svix_auth_token)
    update = EndpointUpdate(event_types=event_types)
    client.endpoint.update(endpoint_id, update)
""",
        "function": "endpoint_filter_config",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "python/svix/webhook/endpoint_filter.py",
    },
    # ── 8. Message Attempt History ───────────────────────────────────────────
    {
        "normalized_code": """\
from typing import List

from svix.client import Svix
from svix.api_resources.message_attempt import MessageAttemptOut


async def get_notification_attempt_list(
    svix_auth_token: str,
    notification_id: str,
    endpoint_id: str,
    limit: int = 50,
) -> List[MessageAttemptOut]:
    \"\"\"Get delivery attempt history for a notification to an endpoint.

    Lists all attempts (successful and failed) to deliver a notification
    to a specific endpoint, sorted by timestamp descending.

    Args:
        svix_auth_token: Svix API authentication token.
        notification_id: ID of the notification.
        endpoint_id: ID of the endpoint.
        limit: Max attempts to return (default 50).

    Returns:
        List of MessageAttemptOut objects with status and timestamps.
    \"\"\"
    client = Svix(svix_auth_token)
    attempts = client.message_endpoint.list_attempts(
        notification_id=notification_id,
        endpoint_id=endpoint_id,
        limit=limit,
    )
    return attempts.data
""",
        "function": "get_notification_attempt_list",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "python/svix/webhook/attempt_list.py",
    },
    # ── 9. Rotate Endpoint Secret ────────────────────────────────────────────
    {
        "normalized_code": """\
from typing import Optional

from svix.client import Svix
from svix.api_resources.endpoint_secret import EndpointSecretOut


async def rotate_endpoint_secret(
    svix_auth_token: str,
    endpoint_id: str,
) -> EndpointSecretOut:
    \"\"\"Rotate webhook endpoint signing secret.

    Generates new endpoint secret and invalidates the previous one.
    Consumer MUST update their signature verification to use new secret.

    Args:
        svix_auth_token: Svix API authentication token.
        endpoint_id: ID of endpoint.

    Returns:
        EndpointSecretOut with new secret and key ID.
    \"\"\"
    client = Svix(svix_auth_token)
    secret = client.endpoint_secret.rotate(endpoint_id)
    return secret
""",
        "function": "rotate_endpoint_secret",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "python/svix/webhook/rotate_secret.py",
    },
    # ── 10. Webhook Consumer Signature Verification ──────────────────────────
    {
        "normalized_code": """\
import hashlib
import hmac
from datetime import datetime

from fastapi import Request, HTTPException


async def webhook_consumer_verify(request: Request, endpoint_secret: str) -> dict:
    \"\"\"Verify and parse webhook in consumer application.\"\"\"
    msg_id = request.headers.get("svix-id")
    msg_timestamp = request.headers.get("svix-timestamp")
    msg_signature = request.headers.get("svix-signature")

    if not all([msg_id, msg_timestamp, msg_signature]):
        raise HTTPException(status_code=401, detail="Missing signature headers")

    body = await request.body()
    signed = f"{msg_id}.{msg_timestamp}.{body.decode()}"

    expected_sig = hmac.new(
        endpoint_secret.encode(),
        signed.encode(),
        hashlib.sha256,
    ).digest()

    if not hmac.compare_digest(msg_signature.encode(), expected_sig):
        raise HTTPException(status_code=401, detail="Invalid signature")

    import json
    return json.loads(body)
""",
        "function": "webhook_consumer_verify",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "python/svix/webhook/consumer.py",
    },
    # ── 11. Batch Create Messages ────────────────────────────────────────────
    {
        "normalized_code": """\
from typing import List

from svix.client import Svix
from svix.api_resources.message import MessageIn


async def batch_create_notifications(
    svix_auth_token: str,
    notifications: List[dict],
) -> List[str]:
    \"\"\"Create multiple webhook notifications in batch.

    Efficiently sends multiple signal notifications to Svix platform.
    Each notification should have event_type and payload keys.

    Args:
        svix_auth_token: Svix API authentication token.
        notifications: List of dicts with 'event_type' and 'payload' keys.

    Returns:
        List of created notification IDs.
    \"\"\"
    client = Svix(svix_auth_token)
    notification_ids = []
    for msg_data in notifications:
        notification = client.message_endpoint.create(
            event_type=msg_data["event_type"],
            payload=msg_data["payload"],
        )
        notification_ids.append(notification.id)
    return notification_ids
""",
        "function": "batch_create_notifications",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "python/svix/webhook/batch_messages.py",
    },
    # ── 12. Endpoint Statistics Dashboard ────────────────────────────────────
    {
        "normalized_code": """\
from typing import Optional

from svix.client import Svix


async def endpoint_stats_dashboard(
    svix_auth_token: str,
    endpoint_id: str,
) -> dict:
    \"\"\"Get endpoint delivery statistics and health dashboard.

    Returns metrics: total_messages, successful, failed, avg_latency,
    last_delivery_timestamp, failure_rate.

    Args:
        svix_auth_token: Svix API authentication token.
        endpoint_id: ID of endpoint.

    Returns:
        Dict with statistics keys and values.
    \"\"\"
    client = Svix(svix_auth_token)
    endpoint = client.endpoint.get(endpoint_id)
    stats = {
        "endpoint_id": endpoint.id,
        "url": endpoint.url,
        "created_at": endpoint.created_at,
        "disabled": endpoint.disabled,
        "description": endpoint.description,
    }
    return stats
""",
        "function": "endpoint_stats_dashboard",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "python/svix/webhook/stats.py",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "create webhook endpoint URL registration",
    "send webhook notification delivery",
    "verify webhook signature HMAC SHA256",
    "list webhook endpoints pagination",
    "retry failed webhook delivery exponential backoff",
    "query webhook signal types supported",
    "endpoint filter configuration signal types",
    "notification attempt history delivery logs",
    "rotate endpoint secret key rotation",
    "webhook consumer verify signature validation",
    "batch create notifications multiple signals",
    "endpoint statistics dashboard delivery metrics",
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
