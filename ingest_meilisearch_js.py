"""
ingest_meilisearch_js.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de meilisearch/meilisearch-js dans la KB Qdrant V6.

Focus : CORE patterns instant search (Client initialization, index CRUD, search with
filters/facets/sort, multi-search, document operations, settings management, pagination,
geosearch, task queue, API key management).

Usage:
    .venv/bin/python3 ingest_meilisearch_js.py
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
REPO_URL = "https://github.com/meilisearch/meilisearch-js.git"
REPO_NAME = "meilisearch/meilisearch-js"
REPO_LOCAL = "/tmp/meilisearch-js"
LANGUAGE = "javascript"
FRAMEWORK = "generic"
STACK = "javascript+meilisearch+search"
CHARTE_VERSION = "1.0"
TAG = "meilisearch/meilisearch-js"
SOURCE_REPO = "https://github.com/meilisearch/meilisearch-js"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Meilisearch JS = instant search client. Patterns CORE : initialization,
# index management, search, filtering, facets, sorting, document CRUD, settings.
# U-5 : client → Xxx, query → query (KEEP — search domain), index → index (KEEP),
# document → element, documents → elements, filter → filter (KEEP), facet → facet (KEEP),
# sort → sort (KEEP), result → hit, results → hits, task → async_job, etc.

PATTERNS: list[dict] = [
    # ── 1. Meilisearch client initialization ────────────────────────────────
    {
        "normalized_code": """\
import { Meilisearch } from "meilisearch";

interface Config {
  host: string;
  apiKey?: string;
}

const initializeClient = (config: Config): Meilisearch => {
  return new Meilisearch({
    host: config.host,
    apiKey: config.apiKey,
  });
};

const client = initializeClient({
  host: "http://localhost:7700",
  apiKey: "xxxxxxxxxxxxxxxx",
});

export { client, initializeClient };
""",
        "function": "client_initialization_config",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "src/client.ts",
    },
    # ── 2. Create and delete index ──────────────────────────────────────────
    {
        "normalized_code": """\
import type { Index } from "meilisearch";

const createIndex = async (
  client: Meilisearch,
  indexUid: string,
): Promise<Index> => {
  const async_job = await client.createIndex(indexUid, {
    primaryKey: "id",
  });
  return await async_job.waitForCompletion();
};

const deleteIndex = async (
  client: Meilisearch,
  indexUid: string,
): Promise<void> => {
  await client.deleteIndex(indexUid);
};

const deleteIndexIfExists = async (
  client: Meilisearch,
  indexUid: string,
): Promise<boolean> => {
  return await client.deleteIndexIfExists(indexUid);
};
""",
        "function": "index_create_delete_operations",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "src/indexes.ts",
    },
    # ── 3. Get index and index information ───────────────────────────────────
    {
        "normalized_code": """\
import type { Index, IndexObject } from "meilisearch";

const getIndex = async (
  client: Meilisearch,
  indexUid: string,
): Promise<Index> => {
  return await client.getIndex(indexUid);
};

const getRawIndex = async (
  client: Meilisearch,
  indexUid: string,
): Promise<IndexObject> => {
  return await client.getRawIndex(indexUid);
};

const listAllIndexes = async (
  client: Meilisearch,
): Promise<Index[]> => {
  const result = await client.getIndexes();
  return result.results;
};

const getIndexStats = async (
  index: Index,
): Promise<IndexStats> => {
  return await index.getStats();
};
""",
        "function": "index_retrieval_and_info",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "src/indexes.ts",
    },
    # ── 4. Add and update documents ─────────────────────────────────────────
    {
        "normalized_code": """\
import type { Index } from "meilisearch";

interface Xxx {
  id: string;
  title: string;
  description: string;
  createdAt: Date;
}

const addElements = async (
  index: Index<Xxx>,
  elements: Xxx[],
): Promise<void> => {
  const async_job = await index.addDocuments(elements);
  await async_job.waitForCompletion();
};

const updateElements = async (
  index: Index<Xxx>,
  elements: Partial<Xxx>[],
): Promise<void> => {
  const async_job = await index.updateDocuments(elements);
  await async_job.waitForCompletion();
};

const addElementsInBatches = async (
  index: Index<Xxx>,
  elements: Xxx[],
  batchSize: number = 1000,
): Promise<void> => {
  const async_jobs = index.addDocumentsInBatches(elements, batchSize);
  for (const async_job of async_jobs) {
    await async_job.waitForCompletion();
  }
};
""",
        "function": "document_add_update_batch",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "src/indexes.ts",
    },
    # ── 5. Get and delete documents ─────────────────────────────────────────
    {
        "normalized_code": """\
import type { Index } from "meilisearch";

const getElement = async (
  index: Index<Xxx>,
  elementId: string,
): Promise<Xxx> => {
  return await index.getDocument(elementId);
};

const listElements = async (
  index: Index<Xxx>,
): Promise<Xxx[]> => {
  const result = await index.getDocuments();
  return result.results;
};

const deleteElement = async (
  index: Index<Xxx>,
  elementId: string,
): Promise<void> => {
  const async_job = await index.deleteDocument(elementId);
  await async_job.waitForCompletion();
};

const deleteElements = async (
  index: Index<Xxx>,
  elementIds: string[],
): Promise<void> => {
  const async_job = await index.deleteDocuments(elementIds);
  await async_job.waitForCompletion();
};

const deleteAllElements = async (
  index: Index<Xxx>,
): Promise<void> => {
  const async_job = await index.deleteAllDocuments();
  await async_job.waitForCompletion();
};
""",
        "function": "document_get_delete_operations",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "src/indexes.ts",
    },
    # ── 6. Search with filters, facets, and sort ────────────────────────────
    {
        "normalized_code": """\
import type { Index, SearchParams, SearchResponse } from "meilisearch";

interface SearchOptions {
  query: string;
  filter?: string[];
  facets?: string[];
  sort?: string[];
  limit?: number;
  offset?: number;
}

const performSearch = async (
  index: Index<Xxx>,
  options: SearchOptions,
): Promise<SearchResponse<Xxx>> => {
  const searchParams: SearchParams = {
    q: options.query,
    filter: options.filter,
    facets: options.facets,
    sort: options.sort,
    limit: options.limit || 10,
    offset: options.offset || 0,
  };
  return await index.search(options.query, searchParams);
};

const searchWithFacetFiltering = async (
  index: Index<Xxx>,
  query: string,
  facetFilters: string[],
): Promise<SearchResponse<Xxx>> => {
  return await index.search(query, {
    facetFilters,
    limit: 20,
  });
};

const paginatedSearch = async (
  index: Index<Xxx>,
  query: string,
  page: number,
  pageSize: number = 10,
): Promise<SearchResponse<Xxx>> => {
  return await index.search(query, {
    limit: pageSize,
    offset: (page - 1) * pageSize,
  });
};
""",
        "function": "search_filters_facets_sort",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "src/indexes.ts",
    },
    # ── 7. Multi-search across multiple indexes ──────────────────────────────
    {
        "normalized_code": """\
import type { Meilisearch, MultiSearchParams } from "meilisearch";

const multiSearch = async (
  client: Meilisearch,
  queries: {
    indexUid: string;
    q: string;
    filter?: string[];
  }[],
): Promise<SearchResponse[]> => {
  const multiSearchParams: MultiSearchParams = {
    queries: queries.map((q) => ({
      indexUid: q.indexUid,
      q: q.q,
      filter: q.filter,
    })),
  };
  const result = await client.multiSearch(multiSearchParams);
  return result.results as SearchResponse[];
};

const federatedSearch = async (
  client: Meilisearch,
  queries: {
    indexUid: string;
    q: string;
  }[],
): Promise<SearchResponse[]> => {
  return await client.multiSearch({
    federation: {},
    queries: queries.map((q) => ({
      ...q,
      federationOptions: { remote: "instance-1" },
    })),
  });
};
""",
        "function": "multi_search_federated_search",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "src/meilisearch.ts",
    },
    # ── 8. Search for facet values and similar documents ────────────────────
    {
        "normalized_code": """\
import type { Index, SearchForFacetValuesParams } from "meilisearch";

const searchFacetValues = async (
  index: Index<Xxx>,
  params: SearchForFacetValuesParams,
): Promise<string[]> => {
  const result = await index.searchForFacetValues(params);
  return result.facetHits.map((hit) => hit.value);
};

const searchSimilarElements = async (
  index: Index<Xxx>,
  id: string,
  limit: number = 10,
): Promise<SearchResponse<Xxx>> => {
  return await index.searchSimilarDocuments({
    id,
    limit,
  });
};
""",
        "function": "search_facets_similar_documents",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "src/indexes.ts",
    },
    # ── 9. Manage index settings (searchable, filterable, sortable) ──────────
    {
        "normalized_code": """\
import type { Index, Settings } from "meilisearch";

const updateSearchableAttributes = async (
  index: Index<Xxx>,
  attributes: string[],
): Promise<void> => {
  const async_job = await index.updateSettings({
    searchableAttributes: attributes,
  });
  await async_job.waitForCompletion();
};

const updateFilterableAttributes = async (
  index: Index<Xxx>,
  attributes: string[],
): Promise<void> => {
  const async_job = await index.updateSettings({
    filterableAttributes: attributes,
  });
  await async_job.waitForCompletion();
};

const updateSortableAttributes = async (
  index: Index<Xxx>,
  attributes: string[],
): Promise<void> => {
  const async_job = await index.updateSettings({
    sortableAttributes: attributes,
  });
  await async_job.waitForCompletion();
};

const getSettings = async (
  index: Index<Xxx>,
): Promise<Settings> => {
  return await index.getSettings();
};
""",
        "function": "settings_searchable_filterable_sortable",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "src/indexes.ts",
    },
    # ── 10. Pagination and pagination settings ──────────────────────────────
    {
        "normalized_code": """\
import type { Index, PaginationSettings } from "meilisearch";

const getPaginationSettings = async (
  index: Index<Xxx>,
): Promise<PaginationSettings> => {
  return await index.getPagination();
};

const updatePaginationSettings = async (
  index: Index<Xxx>,
  settings: PaginationSettings,
): Promise<void> => {
  const async_job = await index.updatePagination(settings);
  await async_job.waitForCompletion();
};

const resetPaginationSettings = async (
  index: Index<Xxx>,
): Promise<void> => {
  const async_job = await index.resetPagination();
  await async_job.waitForCompletion();
};
""",
        "function": "pagination_settings_management",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "src/indexes.ts",
    },
    # ── 11. Task queue and async job waiting ────────────────────────────────
    {
        "normalized_code": """\
import type { Meilisearch } from "meilisearch";

const waitForAsyncJob = async (
  client: Meilisearch,
  async_jobUid: number,
): Promise<AsyncJob> => {
  const async_job = await client.tasks.get(async_jobUid);
  return async_job;
};

const waitForAsyncJobCompletion = async (
  client: Meilisearch,
  async_jobUid: number,
  timeoutMs: number = 5000,
): Promise<AsyncJob> => {
  const async_job = await client.tasks.waitForCompletion(async_jobUid, {
    timeoutMs,
  });
  return async_job;
};

const getAsyncJobs = async (
  client: Meilisearch,
): Promise<AsyncJob[]> => {
  const result = await client.tasks.getTasks();
  return result.results;
};

const getAsyncJobsByStatus = async (
  client: Meilisearch,
  status: string,
): Promise<AsyncJob[]> => {
  const result = await client.tasks.getTasks({
    statuses: [status],
  });
  return result.results;
};
""",
        "function": "async_job_queue_wait_and_retrieve",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/task.ts",
    },
    # ── 12. API key management ──────────────────────────────────────────────
    {
        "normalized_code": """\
import type { Meilisearch, Key, KeyCreation } from "meilisearch";

const createApiKey = async (
  client: Meilisearch,
  options: KeyCreation,
): Promise<Key> => {
  return await client.createKey(options);
};

const getApiKey = async (
  client: Meilisearch,
  keyOrUid: string,
): Promise<Key> => {
  return await client.getKey(keyOrUid);
};

const listApiKeys = async (
  client: Meilisearch,
): Promise<Key[]> => {
  const result = await client.getKeys();
  return result.results;
};

const updateApiKey = async (
  client: Meilisearch,
  keyOrUid: string,
  options: KeyUpdate,
): Promise<Key> => {
  return await client.updateKey(keyOrUid, options);
};

const deleteApiKey = async (
  client: Meilisearch,
  keyOrUid: string,
): Promise<void> => {
  await client.deleteKey(keyOrUid);
};
""",
        "function": "api_key_crud_operations",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/meilisearch.ts",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "initialize Meilisearch client instance",
    "create and delete search indexes",
    "add update delete documents to index",
    "search with filters facets and sorting",
    "multi-search across multiple indexes",
    "manage searchable filterable sortable attributes",
    "pagination settings and offset limit",
    "task queue wait for task completion",
    "API key management create get delete",
    "search similar documents in index",
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
