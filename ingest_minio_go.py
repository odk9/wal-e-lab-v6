"""
ingest_minio_go.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de minio/minio-go dans la KB Qdrant V6.

Focus : CORE patterns S3-compatible object storage (Client init, bucket ops,
stream I/O, presigned URLs, list with iterators, metadata, copy, notifications).

PAS des patterns CRUD/API — patterns de manipulation S3 natifs.

Usage:
    .venv/bin/python3 ingest_minio_go.py
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
REPO_URL = "https://github.com/minio/minio-go.git"
REPO_NAME = "minio/minio-go"
REPO_LOCAL = "/tmp/minio-go"
LANGUAGE = "go"
FRAMEWORK = "generic"
STACK = "go+minio+s3+object_storage"
CHARTE_VERSION = "1.0"
TAG = "minio/minio-go"
SOURCE_REPO = "https://github.com/minio/minio-go"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# MinIO Go = S3-compatible client pour stockage objet.
# Patterns CORE : init client, opérations bucket/object, streaming I/O, presigned,
# list avec iterators, metadata, multipart, notifications.
# U-5 : garder Client/BucketInfo/ObjectInfo/Context, remplacer user→xxx, item→element

PATTERNS: list[dict] = [
    # ── 1. Client initialization with endpoint + credentials ──────────────────
    {
        "normalized_code": """\
import (
	"context"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)


func new_xxx_client(
	endpoint string,
	access_key string,
	secret_key string,
	use_ssl bool,
) (*minio.Client, error) {
	creds := credentials.NewStaticProvider(access_key, secret_key, "")
	opts := &minio.Options{
		Creds:  creds,
		Secure: use_ssl,
	}
	client, err := minio.New(endpoint, opts)
	if err != nil {
		return nil, err
	}
	return client, nil
}
""",
        "function": "client_init_endpoint_credentials",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "api.go",
    },
    # ── 2. PutObject with io.Reader + progress tracking ──────────────────────
    {
        "normalized_code": """\
import (
	"context"
	"io"

	"github.com/minio/minio-go/v7"
)


func put_xxx_stream(
	ctx context.Context,
	client *minio.Client,
	bucket_name string,
	object_name string,
	reader io.Reader,
	content_type string,
	progress io.Reader,
) (minio.UploadInfo, error) {
	opts := minio.PutObjectOptions{
		ContentType: content_type,
		Progress:    progress,
	}
	info, err := client.PutObject(
		ctx,
		bucket_name,
		object_name,
		reader,
		-1,
		opts,
	)
	if err != nil {
		return minio.UploadInfo{}, err
	}
	return info, nil
}
""",
        "function": "put_object_stream_progress",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "api-put-object.go",
    },
    # ── 3. GetObject returns io.ReadCloser (streaming read) ──────────────────
    {
        "normalized_code": """\
import (
	"context"
	"io"

	"github.com/minio/minio-go/v7"
)


func get_xxx_stream(
	ctx context.Context,
	client *minio.Client,
	bucket_name string,
	object_name string,
) (io.ReadCloser, error) {
	opts := minio.GetObjectOptions{}
	reader, err := client.GetObject(ctx, bucket_name, object_name, opts)
	if err != nil {
		return nil, err
	}
	return reader, nil
}
""",
        "function": "get_object_stream_readcloser",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "api-get-object-file.go",
    },
    # ── 4. FPutObject — upload file from disk ────────────────────────────────
    {
        "normalized_code": """\
import (
	"context"

	"github.com/minio/minio-go/v7"
)


func upload_xxx_file(
	ctx context.Context,
	client *minio.Client,
	bucket_name string,
	object_name string,
	file_path string,
	content_type string,
) (minio.UploadInfo, error) {
	opts := minio.PutObjectOptions{
		ContentType: content_type,
	}
	info, err := client.FPutObject(
		ctx,
		bucket_name,
		object_name,
		file_path,
		opts,
	)
	if err != nil {
		return minio.UploadInfo{}, err
	}
	return info, nil
}
""",
        "function": "upload_object_from_file",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "api-put-object.go",
    },
    # ── 5. FGetObject — download object to disk ──────────────────────────────
    {
        "normalized_code": """\
import (
	"context"

	"github.com/minio/minio-go/v7"
)


func download_xxx_file(
	ctx context.Context,
	client *minio.Client,
	bucket_name string,
	object_name string,
	file_path string,
) error {
	opts := minio.GetObjectOptions{}
	err := client.FGetObject(ctx, bucket_name, object_name, file_path, opts)
	if err != nil {
		return err
	}
	return nil
}
""",
        "function": "download_object_to_file",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "api-get-object-file.go",
    },
    # ── 6. PresignedGetObject — generate temporary read URL ────────────────────
    {
        "normalized_code": """\
import (
	"context"
	"net/url"
	"time"

	"github.com/minio/minio-go/v7"
)


func presigned_xxx_get_url(
	ctx context.Context,
	client *minio.Client,
	bucket_name string,
	object_name string,
	expiry time.Duration,
) (*url.URL, error) {
	req_params := url.Values{}
	presigned_url, err := client.PresignedGetObject(
		ctx,
		bucket_name,
		object_name,
		expiry,
		req_params,
	)
	if err != nil {
		return nil, err
	}
	return presigned_url, nil
}
""",
        "function": "presigned_get_object_url_expiry",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "api-presigned.go",
    },
    # ── 7. PresignedPutObject — generate temporary write URL ──────────────────
    {
        "normalized_code": """\
import (
	"context"
	"net/url"
	"time"

	"github.com/minio/minio-go/v7"
)


func presigned_xxx_put_url(
	ctx context.Context,
	client *minio.Client,
	bucket_name string,
	object_name string,
	expiry time.Duration,
) (*url.URL, error) {
	req_params := url.Values{}
	presigned_url, err := client.PresignedPutObject(
		ctx,
		bucket_name,
		object_name,
		expiry,
	)
	if err != nil {
		return nil, err
	}
	return presigned_url, nil
}
""",
        "function": "presigned_put_object_url_expiry",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "api-presigned.go",
    },
    # ── 8. ListObjects with iterator (Go 1.22+ range over func) ──────────────
    {
        "normalized_code": """\
import (
	"context"

	"github.com/minio/minio-go/v7"
)


func list_xxx_objects(
	ctx context.Context,
	client *minio.Client,
	bucket_name string,
	prefix string,
	recursive bool,
) ([]minio.ObjectInfo, error) {
	opts := minio.ListObjectsOptions{
		Prefix:    prefix,
		Recursive: recursive,
	}
	results := []minio.ObjectInfo{}
	for element := range client.ListObjects(ctx, bucket_name, opts) {
		if element.Err != nil {
			return nil, element.Err
		}
		results = append(results, element)
	}
	return results, nil
}
""",
        "function": "list_objects_iterator_prefix_recursive",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "api-list.go",
    },
    # ── 9. StatObject — get object metadata (size, ETag, modified) ────────────
    {
        "normalized_code": """\
import (
	"context"

	"github.com/minio/minio-go/v7"
)


func stat_xxx_metadata(
	ctx context.Context,
	client *minio.Client,
	bucket_name string,
	object_name string,
) (minio.ObjectInfo, error) {
	opts := minio.StatObjectOptions{}
	info, err := client.StatObject(ctx, bucket_name, object_name, opts)
	if err != nil {
		return minio.ObjectInfo{}, err
	}
	return info, nil
}
""",
        "function": "stat_object_metadata_etag_size",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "api-stat-object.go",
    },
    # ── 10. CopyObject — server-side copy with transform ──────────────────────
    {
        "normalized_code": """\
import (
	"context"

	"github.com/minio/minio-go/v7"
)


func copy_xxx_server_side(
	ctx context.Context,
	client *minio.Client,
	src_bucket string,
	src_object string,
	dst_bucket string,
	dst_object string,
) (minio.UploadInfo, error) {
	src := minio.CopySrcOptions{
		Bucket: src_bucket,
		Object: src_object,
	}
	dst := minio.CopyDestOptions{
		Bucket: dst_bucket,
		Object: dst_object,
	}
	info, err := client.CopyObject(ctx, dst, src)
	if err != nil {
		return minio.UploadInfo{}, err
	}
	return info, nil
}
""",
        "function": "copy_object_server_side_options",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "api-copy-object.go",
    },
    # ── 11. SetBucketNotification — configure event notifications ────────────
    {
        "normalized_code": """\
import (
	"context"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/notification"
)


func set_xxx_notification(
	ctx context.Context,
	client *minio.Client,
	bucket_name string,
	config notification.Configuration,
) error {
	err := client.SetBucketNotification(ctx, bucket_name, config)
	if err != nil {
		return err
	}
	return nil
}
""",
        "function": "bucket_notification_configure",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "api-bucket-notification.go",
    },
    # ── 12. RemoveObject — delete single object ──────────────────────────────
    {
        "normalized_code": """\
import (
	"context"

	"github.com/minio/minio-go/v7"
)


func remove_xxx_object(
	ctx context.Context,
	client *minio.Client,
	bucket_name string,
	object_name string,
) error {
	opts := minio.RemoveObjectOptions{}
	err := client.RemoveObject(ctx, bucket_name, object_name, opts)
	if err != nil {
		return err
	}
	return nil
}
""",
        "function": "remove_object_delete",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "api-remove-object.go",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "initialize MinIO client with endpoint and credentials",
    "upload object stream with progress reader",
    "download object as streaming reader",
    "presigned URL temporary access GET",
    "presigned URL temporary access PUT",
    "list bucket objects with iterator prefix recursive",
    "get object metadata size ETag timestamp",
    "server-side copy object between buckets",
    "configure bucket event notifications",
    "delete remove object from bucket",
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
                "norm_ok": len(check_charte_violations(hit.payload.get("normalized_code", ""), hit.payload.get("function", ""), language=LANGUAGE)) == 0,
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
