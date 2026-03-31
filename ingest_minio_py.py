"""
ingest_minio_py.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de minio/minio-py dans la KB Qdrant V6.

Focus : CORE patterns S3-compatible object storage (Client init, bucket ops,
object upload/download, multipart, presigned URLs, metadata, encryption).

Usage:
    .venv/bin/python3 ingest_minio_py.py
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
REPO_URL = "https://github.com/minio/minio-py.git"
REPO_NAME = "minio/minio-py"
REPO_LOCAL = "/tmp/minio-py"
LANGUAGE = "python"
FRAMEWORK = "generic"
STACK = "python+minio+s3+object_storage"
CHARTE_VERSION = "1.0"
TAG = "minio/minio-py"
SOURCE_REPO = "https://github.com/minio/minio-py"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Minio = S3-compatible object storage client. Focus sur patterns réutilisables.
# U-5: bucket, object, client, endpoint, credentials, presigned, multipart,
#      upload, download, prefix, recursive, lifecycle, encryption, metadata,
#      etag, content_type — KEEP. user→xxx, item→element.

PATTERNS: list[dict] = [
    # ── 1. Client initialization with credentials ─────────────────────────
    {
        "normalized_code": """\
from minio import Minio


def initialize_client(
    endpoint: str,
    access_key: str,
    secret_key: str,
    region: str | None = None,
    secure: bool = True,
) -> Minio:
    \"\"\"Initialize MinIO client with static credentials.

    Args:
        endpoint: S3 endpoint hostname (e.g., 'play.min.io')
        access_key: S3 access key identifier
        secret_key: S3 secret key credential
        region: Optional AWS region name
        secure: Use TLS connection (default: True)

    Returns:
        Initialized Minio client instance
    \"\"\"
    client = Minio(
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        region=region,
        secure=secure,
    )
    return client
""",
        "function": "s3_client_initialization_credentials",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "minio/minio.py",
    },
    # ── 2. Bucket creation with object-lock ────────────────────────────────
    {
        "normalized_code": """\
from minio import Minio


def create_bucket(
    client: Minio,
    bucket_name: str,
    region: str = "us-east-1",
    object_lock: bool = False,
) -> None:
    \"\"\"Create a new bucket with optional object-lock protection.

    Args:
        client: Initialized Minio client
        bucket_name: Name of bucket to create
        region: AWS region for bucket (default: us-east-1)
        object_lock: Enable object-lock on bucket (immutability)

    Raises:
        S3Error: If bucket creation fails
    \"\"\"
    client.make_bucket(
        bucket_name=bucket_name,
        region=region,
        object_lock=object_lock,
    )
""",
        "function": "s3_bucket_creation_object_lock",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "minio/minio.py",
    },
    # ── 3. Check bucket existence ──────────────────────────────────────────
    {
        "normalized_code": """\
from minio import Minio


def check_bucket_exists(client: Minio, bucket_name: str) -> bool:
    \"\"\"Check if a bucket exists on the S3 service.

    Args:
        client: Initialized Minio client
        bucket_name: Name of bucket to check

    Returns:
        True if bucket exists, False otherwise
    \"\"\"
    return client.bucket_exists(bucket_name=bucket_name)
""",
        "function": "s3_bucket_exists_check",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "minio/minio.py",
    },
    # ── 4. Upload object with bytes/stream ─────────────────────────────────
    {
        "normalized_code": """\
from io import BytesIO

from minio import Minio


def upload_object_stream(
    client: Minio,
    bucket_name: str,
    object_name: str,
    data: BytesIO,
    length: int,
    content_type: str = "application/octet-stream",
    metadata: dict[str, str] | None = None,
) -> dict:
    \"\"\"Upload object from stream (BytesIO, file-like).

    Args:
        client: Initialized Minio client
        bucket_name: Destination bucket name
        object_name: Destination object name
        data: BytesIO stream or file-like object
        length: Total bytes to upload (-1 for unknown size)
        content_type: MIME type of object
        metadata: Custom metadata key-value pairs

    Returns:
        Upload response dict with etag and version_id
    \"\"\"
    result = client.put_object(
        bucket_name=bucket_name,
        object_name=object_name,
        data=data,
        length=length,
        content_type=content_type,
        user_metadata=metadata or {},
    )
    return {
        "object_name": result.object_name,
        "etag": result.etag,
        "version_id": result.version_id,
    }
""",
        "function": "s3_object_upload_stream_metadata",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "minio/minio.py",
    },
    # ── 5. Upload object from filesystem ───────────────────────────────────
    {
        "normalized_code": """\
from minio import Minio


def upload_object_from_file(
    client: Minio,
    bucket_name: str,
    object_name: str,
    file_path: str,
    content_type: str | None = None,
) -> dict:
    \"\"\"Upload object from local filesystem path.

    Args:
        client: Initialized Minio client
        bucket_name: Destination bucket name
        object_name: Destination object name
        file_path: Local file path to upload
        content_type: MIME type (auto-detected if None)

    Returns:
        Upload response dict with etag and version_id
    \"\"\"
    result = client.fput_object(
        bucket_name=bucket_name,
        object_name=object_name,
        file_path=file_path,
        content_type=content_type,
    )
    return {
        "object_name": result.object_name,
        "etag": result.etag,
        "version_id": result.version_id,
    }
""",
        "function": "s3_object_upload_filesystem",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "minio/minio.py",
    },
    # ── 6. Download object to stream ───────────────────────────────────────
    {
        "normalized_code": """\
from minio import Minio


def download_object_stream(
    client: Minio,
    bucket_name: str,
    object_name: str,
    offset: int = 0,
    length: int | None = None,
) -> bytes:
    \"\"\"Download object content as bytes.

    Args:
        client: Initialized Minio client
        bucket_name: Source bucket name
        object_name: Source object name
        offset: Start offset in bytes (default: 0)
        length: Number of bytes to read (None = entire object)

    Returns:
        Object content as bytes

    Important:
        Must close response context manager after reading.
    \"\"\"
    response = None
    try:
        response = client.get_object(
            bucket_name=bucket_name,
            object_name=object_name,
            offset=offset,
            length=length,
        )
        return response.read()
    finally:
        if response:
            response.close()
""",
        "function": "s3_object_download_stream",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "minio/minio.py",
    },
    # ── 7. Generate presigned GET URL ──────────────────────────────────────
    {
        "normalized_code": """\
from datetime import timedelta

from minio import Minio


def generate_presigned_get_url(
    client: Minio,
    bucket_name: str,
    object_name: str,
    expires: timedelta | None = None,
) -> str:
    \"\"\"Generate time-limited download URL for object.

    Args:
        client: Initialized Minio client
        bucket_name: Bucket containing object
        object_name: Object to access
        expires: URL expiry duration (default: 7 days)

    Returns:
        Presigned GET URL as string
    \"\"\"
    expires = expires or timedelta(days=7)
    url = client.presigned_get_object(
        bucket_name=bucket_name,
        object_name=object_name,
        expires=expires,
    )
    return url
""",
        "function": "s3_presigned_url_get_download",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "minio/minio.py",
    },
    # ── 8. Generate presigned PUT URL ──────────────────────────────────────
    {
        "normalized_code": """\
from datetime import timedelta

from minio import Minio


def generate_presigned_put_url(
    client: Minio,
    bucket_name: str,
    object_name: str,
    expires: timedelta | None = None,
) -> str:
    \"\"\"Generate time-limited upload URL for object.

    Args:
        client: Initialized Minio client
        bucket_name: Bucket for upload
        object_name: Object name to create
        expires: URL expiry duration (default: 7 days)

    Returns:
        Presigned PUT URL as string
    \"\"\"
    expires = expires or timedelta(days=7)
    url = client.presigned_put_object(
        bucket_name=bucket_name,
        object_name=object_name,
        expires=expires,
    )
    return url
""",
        "function": "s3_presigned_url_put_upload",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "minio/minio.py",
    },
    # ── 9. List objects with prefix and recursion ──────────────────────────
    {
        "normalized_code": """\
from minio import Minio


def list_objects_paginated(
    client: Minio,
    bucket_name: str,
    prefix: str | None = None,
    recursive: bool = False,
    start_after: str | None = None,
) -> list[dict]:
    \"\"\"List objects in bucket with optional prefix filtering.

    Args:
        client: Initialized Minio client
        bucket_name: Bucket to list
        prefix: Filter by object name prefix (e.g., 'my/path/')
        recursive: Recursively list all nested objects
        start_after: Start listing after this object name

    Returns:
        List of object metadata dicts with name, size, etag, modified
    \"\"\"
    objects = client.list_objects(
        bucket_name=bucket_name,
        prefix=prefix,
        recursive=recursive,
        start_after=start_after,
    )
    result = []
    for obj in objects:
        result.append({
            "name": obj.object_name,
            "size": obj.size,
            "etag": obj.etag,
            "modified": obj.last_modified,
        })
    return result
""",
        "function": "s3_object_list_prefix_recursive",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "minio/minio.py",
    },
    # ── 10. Get object metadata (stat) ─────────────────────────────────────
    {
        "normalized_code": """\
from minio import Minio


def get_object_metadata(
    client: Minio,
    bucket_name: str,
    object_name: str,
    version_id: str | None = None,
) -> dict:
    \"\"\"Retrieve object metadata without downloading content.

    Args:
        client: Initialized Minio client
        bucket_name: Bucket name
        object_name: Object name
        version_id: Optional specific version ID

    Returns:
        Object metadata dict with size, etag, content_type, modified
    \"\"\"
    response = client.stat_object(
        bucket_name=bucket_name,
        object_name=object_name,
        version_id=version_id,
    )
    return {
        "size": response.size,
        "etag": response.etag,
        "content_type": response.content_type,
        "last_modified": response.last_modified,
        "version_id": response.version_id,
        "metadata": response.metadata,
    }
""",
        "function": "s3_object_stat_metadata",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "minio/minio.py",
    },
    # ── 11. Copy object within or between buckets ──────────────────────────
    {
        "normalized_code": """\
from minio import Minio
from minio.args import Directive, SourceObject


def copy_object_between_buckets(
    client: Minio,
    source_bucket: str,
    source_object: str,
    dest_bucket: str,
    dest_object: str,
    replace_metadata: bool = False,
    metadata: dict[str, str] | None = None,
) -> dict:
    \"\"\"Copy object from source to destination bucket.

    Args:
        client: Initialized Minio client
        source_bucket: Source bucket name
        source_object: Source object name
        dest_bucket: Destination bucket name
        dest_object: Destination object name
        replace_metadata: Replace metadata during copy
        metadata: New metadata to set

    Returns:
        Copy result dict with object_name and version_id
    \"\"\"
    source = SourceObject(
        bucket_name=source_bucket,
        object_name=source_object,
    )
    metadata_directive = Directive.REPLACE if replace_metadata else None
    result = client.copy_object(
        bucket_name=dest_bucket,
        object_name=dest_object,
        source=source,
        user_metadata=metadata or {},
        metadata_directive=metadata_directive,
    )
    return {
        "object_name": result.object_name,
        "version_id": result.version_id,
    }
""",
        "function": "s3_object_copy_buckets",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "minio/minio.py",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "initialize S3 client with access key and secret key credentials",
    "create bucket with object-lock immutability protection",
    "upload object from filesystem to S3 bucket",
    "download object content from S3 as stream bytes",
    "generate presigned GET URL for time-limited download access",
    "generate presigned PUT URL for time-limited upload access",
    "list objects in bucket with prefix and recursive filtering",
    "get object metadata stat without downloading content",
    "copy object between S3 buckets with metadata",
    "check if S3 bucket exists",
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
            })
        else:
            results.append({"query": q, "function": "NO_RESULT", "file_role": "?", "score": 0.0, "code_preview": ""})
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
