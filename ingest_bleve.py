"""
ingest_bleve.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de blevesearch/bleve dans la KB Qdrant V6.

Focus : CORE patterns full-text search (index creation, document mapping,
field types, query types, search requests, faceted search, custom analyzers).
PAS des patterns CRUD/API — patterns de recherche textuelle et indexation.

Usage:
    .venv/bin/python3 ingest_bleve.py
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
REPO_URL = "https://github.com/blevesearch/bleve.git"
REPO_NAME = "blevesearch/bleve"
REPO_LOCAL = "/tmp/bleve"
LANGUAGE = "go"
FRAMEWORK = "generic"
STACK = "go+bleve+fulltext_search"
CHARTE_VERSION = "1.0"
TAG = "blevesearch/bleve"
SOURCE_REPO = "https://github.com/blevesearch/bleve"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Bleve = full-text search engine pour Go.
# Patterns CORE : index creation/opening, document mapping, field types,
# query building (match, phrase, term, fuzzy, range, boolean), search requests,
# faceted search, custom analyzers.
# U-5 : entités métier renommées selon règles (document → element, query → xxxquery, etc.)

PATTERNS: list[dict] = [
    # ── 1. Create and open index with mapping ────────────────────────────────
    {
        "normalized_code": """\
package main

import (
\t"log"
\t
\t"github.com/blevesearch/bleve/v2"
)

func createIndexWithMapping(indexPath string) (bleve.Index, error) {
\tindexMapping := bleve.NewIndexMapping()
\tindex, err := bleve.New(indexPath, indexMapping)
\tif err != nil {
\t\treturn nil, err
\t}
\t
\tcount, err := index.DocCount()
\tif err != nil {
\t\tindex.Close()
\t\treturn nil, err
\t}
\tlog.Printf("Index created with %d documents", count)
\treturn index, nil
}
""",
        "function": "index_create_open_mapping",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "examples_test.go",
    },
    # ── 2. Index documents with field mapping ────────────────────────────────
    {
        "normalized_code": """\
package main

import (
\t"time"
\t
\t"github.com/blevesearch/bleve/v2"
)

type Element struct {
\tName    string
\tCreated time.Time
\tAge     int
}

func indexElements(index bleve.Index) error {
\telement := Element{
\t\tName:    "example name",
\t\tCreated: time.Now(),
\t\tAge:     30,
\t}
\t
\terr := index.Index("element-1", element)
\tif err != nil {
\t\treturn err
\t}
\t
\tcount, err := index.DocCount()
\tif err != nil {
\t\treturn err
\t}
\treturn nil
}
""",
        "function": "index_document_mapping",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "examples_test.go",
    },
    # ── 3. Text field mapping (standard analyzer) ────────────────────────────
    {
        "normalized_code": """\
package main

import (
\t"github.com/blevesearch/bleve/v2"
\t"github.com/blevesearch/bleve/v2/mapping"
)

func textFieldMappingExample() *mapping.FieldMapping {
\tfieldMapping := bleve.NewTextFieldMapping()
\tfieldMapping.Analyzer = "standard"
\tfieldMapping.Store = true
\tfieldMapping.Index = true
\treturn fieldMapping
}

func setupDocumentMapping() *mapping.DocumentMapping {
\tdocMapping := bleve.NewDocumentMapping()
\tdocMapping.AddFieldMapping("title", textFieldMappingExample())
\tdocMapping.AddFieldMapping("content", textFieldMappingExample())
\treturn docMapping
}
""",
        "function": "text_field_mapping_standard",
        "feature_type": "schema",
        "file_role": "utility",
        "file_path": "mapping.go",
    },
    # ── 4. Numeric field mapping (integer and float) ──────────────────────────
    {
        "normalized_code": """\
package main

import (
\t"github.com/blevesearch/bleve/v2"
\t"github.com/blevesearch/bleve/v2/mapping"
)

func numericFieldMappingExample() *mapping.FieldMapping {
\treturn bleve.NewNumericFieldMapping()
}

func setupDocumentMappingWithNumbers() *mapping.DocumentMapping {
\tdocMapping := bleve.NewDocumentMapping()
\tdocMapping.AddFieldMapping("priority", numericFieldMappingExample())
\tdocMapping.AddFieldMapping("price", bleve.NewNumericFieldMapping())
\treturn docMapping
}
""",
        "function": "numeric_field_mapping_integer_float",
        "feature_type": "schema",
        "file_role": "utility",
        "file_path": "mapping.go",
    },
    # ── 5. DateTime field mapping (temporal data) ────────────────────────────
    {
        "normalized_code": """\
package main

import (
\t"github.com/blevesearch/bleve/v2"
\t"github.com/blevesearch/bleve/v2/mapping"
)

func dateTimeFieldMappingExample() *mapping.FieldMapping {
\treturn bleve.NewDateTimeFieldMapping()
}

func setupDocumentMappingWithDates() *mapping.DocumentMapping {
\tdocMapping := bleve.NewDocumentMapping()
\tdocMapping.AddFieldMapping("created_at", dateTimeFieldMappingExample())
\tdocMapping.AddFieldMapping("updated_at", dateTimeFieldMappingExample())
\treturn docMapping
}
""",
        "function": "datetime_field_mapping_temporal",
        "feature_type": "schema",
        "file_role": "utility",
        "file_path": "mapping.go",
    },
    # ── 6. Boolean and GeoPoint field mappings ───────────────────────────────
    {
        "normalized_code": """\
package main

import (
\t"github.com/blevesearch/bleve/v2"
\t"github.com/blevesearch/bleve/v2/mapping"
)

func setupDocumentMappingWithSpecialTypes() *mapping.DocumentMapping {
\tdocMapping := bleve.NewDocumentMapping()
\tdocMapping.AddFieldMapping("is_active", bleve.NewBooleanFieldMapping())
\tdocMapping.AddFieldMapping("location", bleve.NewGeoPointFieldMapping())
\tdocMapping.AddFieldMapping("shape", bleve.NewGeoShapeFieldMapping())
\tdocMapping.AddFieldMapping("ip_address", bleve.NewIPFieldMapping())
\treturn docMapping
}
""",
        "function": "special_field_mapping_boolean_geo",
        "feature_type": "schema",
        "file_role": "utility",
        "file_path": "mapping.go",
    },
    # ── 7. Match query (text search) ──────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
\t"github.com/blevesearch/bleve/v2"
)

func matchQueryExample(index bleve.Index, searchText string) error {
\tquery := bleve.NewMatchQuery(searchText)
\tsearchRequest := bleve.NewSearchRequest(query)
\tsearchResults, err := index.Search(searchRequest)
\tif err != nil {
\t\treturn err
\t}
\tfor _, hit := range searchResults.Hits {
\t\tprintln("Matched:", hit.ID)
\t}
\treturn nil
}
""",
        "function": "match_query_text_search",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "examples_test.go",
    },
    # ── 8. Query types: match phrase, term, prefix, fuzzy ──────────────────────
    {
        "normalized_code": """\
package main

import (
\t"github.com/blevesearch/bleve/v2"
)

func buildQueryVariants(index bleve.Index) error {
\tphraseQuery := bleve.NewMatchPhraseQuery("exact phrase here")
\ttermQuery := bleve.NewTermQuery("single_term")
\tprefixQuery := bleve.NewPrefixQuery("prefix")
\tfuzzyQuery := bleve.NewFuzzyQuery("fuzzyterm")
\t
\tfor _, q := range []bleve.Query{phraseQuery, termQuery, prefixQuery, fuzzyQuery} {
\t\tsearchRequest := bleve.NewSearchRequest(q)
\t\t_, err := index.Search(searchRequest)
\t\tif err != nil {
\t\t\treturn err
\t\t}
\t}
\treturn nil
}
""",
        "function": "query_variants_phrase_term_prefix_fuzzy",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "examples_test.go",
    },
    # ── 9. Boolean query (must, should, must not) ────────────────────────────
    {
        "normalized_code": """\
package main

import (
\t"github.com/blevesearch/bleve/v2"
)

func booleanQueryExample(index bleve.Index) error {
\tboolQuery := bleve.NewBooleanQuery()
\tboolQuery.AddMust(bleve.NewMatchQuery("required"))
\tboolQuery.AddShould(bleve.NewMatchQuery("optional"))
\tboolQuery.AddMustNot(bleve.NewMatchQuery("excluded"))
\t
\tsearchRequest := bleve.NewSearchRequest(boolQuery)
\tsearchResults, err := index.Search(searchRequest)
\tif err != nil {
\t\treturn err
\t}
\treturn nil
}
""",
        "function": "boolean_query_must_should_must_not",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "examples_test.go",
    },
    # ── 10. Range queries: numeric and date ranges ───────────────────────────
    {
        "normalized_code": """\
package main

import (
\t"time"
\t
\t"github.com/blevesearch/bleve/v2"
)

func rangeQueriesExample(index bleve.Index) error {
\tmin := float64(10)
\tmax := float64(100)
\tnumQuery := bleve.NewNumericRangeQuery(&min, &max)
\t
\tstartDate := time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)
\tendDate := time.Date(2024, 12, 31, 23, 59, 59, 0, time.UTC)
\tdateQuery := bleve.NewDateRangeQuery(startDate, endDate)
\t
\tfor _, q := range []bleve.Query{numQuery, dateQuery} {
\t\tsearchRequest := bleve.NewSearchRequest(q)
\t\t_, err := index.Search(searchRequest)
\t\tif err != nil {
\t\t\treturn err
\t\t}
\t}
\treturn nil
}
""",
        "function": "range_queries_numeric_date",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "examples_test.go",
    },
    # ── 11. Search request with highlight and pagination ─────────────────────
    {
        "normalized_code": """\
package main

import (
\t"github.com/blevesearch/bleve/v2"
\t"github.com/blevesearch/bleve/v2/search/highlight/highlighter/ansi"
)

func searchWithHighlightAndPagination(index bleve.Index) error {
\tquery := bleve.NewMatchQuery("search_term")
\tsearchRequest := bleve.NewSearchRequest(query)
\t
\tsearchRequest.From = 0
\tsearchRequest.Size = 10
\tsearchRequest.Highlight = bleve.NewHighlight()
\tsearchRequest.Highlight.SetHighlighter("ansi")
\t
\tsearchResults, err := index.Search(searchRequest)
\tif err != nil {
\t\treturn err
\t}
\treturn nil
}
""",
        "function": "search_request_highlight_pagination",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "examples_test.go",
    },
    # ── 12. Faceted search (field aggregation) ───────────────────────────────
    {
        "normalized_code": """\
package main

import (
\t"time"
\t
\t"github.com/blevesearch/bleve/v2"
)

func facetedSearchExample(index bleve.Index) error {
\tfacet := bleve.NewFacetRequest("field_xxx", 10)
\tfacet.SetPrefixFilter("prefix_")
\t
\tdateFacet := bleve.NewFacetRequest("created_at", 5)
\tdateFacet.AddDateTimeRange("recent", time.Unix(0, 0), time.Now())
\t
\tquery := bleve.NewMatchAllQuery()
\tsearchRequest := bleve.NewSearchRequest(query)
\tsearchRequest.AddFacet("xxx_facet", facet)
\tsearchRequest.AddFacet("date_facet", dateFacet)
\t
\tsearchResults, err := index.Search(searchRequest)
\tif err != nil {
\t\treturn err
\t}
\treturn nil
}
""",
        "function": "faceted_search_field_aggregation",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "examples_test.go",
    },
    # ── 13. Batch indexing (bulk insert) ──────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
\t"github.com/blevesearch/bleve/v2"
)

type Element struct {
\tName string
\tID   string
}

func batchIndexElements(index bleve.Index, elements []Element) error {
\tbatch := index.NewBatch()
\t
\tfor _, element := range elements {
\t\terr := batch.Index(element.ID, element)
\t\tif err != nil {
\t\t\treturn err
\t\t}
\t\t
\t\tif batch.Size() >= 100 {
\t\t\terr = index.Batch(batch)
\t\t\tif err != nil {
\t\t\t\treturn err
\t\t\t}
\t\t\tbatch.Reset()
\t\t}
\t}
\t
\treturn index.Batch(batch)
}
""",
        "function": "batch_indexing_bulk_insert",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "index.go",
    },
    # ── 14. Index alias (search multiple indexes) ────────────────────────────
    {
        "normalized_code": """\
package main

import (
\t"github.com/blevesearch/bleve/v2"
)

func searchMultipleIndexesViaAlias(index1, index2 bleve.Index, query bleve.Query) error {
\talias, err := bleve.NewIndexAlias(index1, index2)
\tif err != nil {
\t\treturn err
\t}
\t
\tsearchRequest := bleve.NewSearchRequest(query)
\tsearchResults, err := alias.Search(searchRequest)
\tif err != nil {
\t\treturn err
\t}
\treturn nil
}
""",
        "function": "index_alias_multiple_search",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "index_alias_impl.go",
    },
    # ── 15. Sorting search results ───────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
\t"github.com/blevesearch/bleve/v2"
\t"github.com/blevesearch/bleve/v2/search"
)

func sortedSearchExample(index bleve.Index) error {
\tquery := bleve.NewMatchAllQuery()
\tsearchRequest := bleve.NewSearchRequest(query)
\t
\tsearchRequest.SortBy([]string{"_score"})
\tsearchRequest.SortByField("priority", false)
\tsearchRequest.SortByField("created_at", true)
\t
\tsearchResults, err := index.Search(searchRequest)
\tif err != nil {
\t\treturn err
\t}
\treturn nil
}
""",
        "function": "sorted_search_results",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "examples_test.go",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "create and open full-text search index with field mapping",
    "index documents with multiple field types and store",
    "text field mapping with standard analyzer",
    "numeric range query integer float search",
    "date time range query temporal data",
    "boolean query must should must not clauses",
    "match phrase term prefix fuzzy query variants",
    "faceted search aggregation by field with prefix filter",
    "batch indexing bulk insert documents in batches",
    "search results pagination highlight with offset",
    "sorting search results by score and field",
    "search multiple indexes via alias",
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
