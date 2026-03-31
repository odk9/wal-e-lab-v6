"""
ingest_tantivy.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de quickwit-oss/tantivy dans la KB Qdrant V6.

Focus : CORE patterns full-text search engine (Schema definition, Index creation,
Document indexing, Query parsing, Boolean/phrase queries, Searcher + Collector,
Tokenizer pipeline, Snippet generation, Merge policy).

NOT patterns : API wrappers, CLI tools, example code.

Usage:
    .venv/bin/python3 ingest_tantivy.py
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
REPO_URL = "https://github.com/quickwit-oss/tantivy.git"
REPO_NAME = "quickwit-oss/tantivy"
REPO_LOCAL = "/tmp/tantivy"
LANGUAGE = "rust"
FRAMEWORK = "generic"
STACK = "rust+tantivy+fulltext_search"
CHARTE_VERSION = "1.0"
TAG = "quickwit-oss/tantivy"
SOURCE_REPO = "https://github.com/quickwit-oss/tantivy"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Tantivy = Full-text search engine (Rust equivalent of Lucene).
# Patterns CORE : Schema, Index creation, Document indexing, Query parsing,
# Boolean/phrase queries, Searcher, Collector (TopDocs), Tokenizer, Snippets,
# Merge policy.
# U-5 : user → xxx, item → element, product → offering, order → sequence,
# event → signal, tag → label, message → payload, task → job, post → entry,
# comment → annotation. KEEP: Document, Schema, Field, Index, Searcher, Query,
# Collector, Tokenizer, Facet, Snippet, Term, impl, trait, struct, enum,
# Result, Option, Vec.

PATTERNS: list[dict] = [
    # ── 1. Schema definition with field builder pattern ───────────────────────
    {
        "normalized_code": """\
use tantivy::schema::*;

fn create_schema() -> Schema {
    let mut schema_builder = Schema::builder();

    let title = schema_builder.add_text_field(
        "title",
        TEXT | STORED,
    );

    let body = schema_builder.add_text_field(
        "body",
        TextOptions::default()
            .set_stored()
            .set_indexing_options(
                TextFieldIndexing::default()
                    .set_tokenizer("default")
                    .set_index_option(IndexRecordOption::WithFreqsAndPositions),
            ),
    );

    let timestamp = schema_builder.add_u64_field(
        "timestamp",
        INDEXED | STORED,
    );

    schema_builder.build()
}
""",
        "function": "schema_builder_field_definition",
        "feature_type": "schema",
        "file_role": "schema",
        "file_path": "src/schema/mod.rs",
    },
    # ── 2. Index creation and document writer setup ───────────────────────────
    {
        "normalized_code": """\
use tantivy::Index;

fn index_and_writer(schema: Schema, index_path: &Path) -> tantivy::Result<(Index, IndexWriter)> {
    let index = Index::create_in_dir(index_path, schema)?;

    let index_writer = index.writer(100_000_000)?;

    Ok((index, index_writer))
}


fn add_element_to_index(
    index_writer: &mut IndexWriter,
    title: Field,
    body: Field,
    title_text: &str,
    body_text: &str,
) -> tantivy::Result<()> {
    index_writer.add_document(doc!(
        title => title_text,
        body => body_text,
    ))?;
    Ok(())
}
""",
        "function": "index_create_writer_add_document",
        "feature_type": "crud",
        "file_role": "model",
        "file_path": "src/core/searcher.rs",
    },
    # ── 3. Searcher and search result collection ──────────────────────────────
    {
        "normalized_code": """\
use tantivy::collector::TopDocs;
use tantivy::DocAddress;

fn search_index(
    index: &Index,
    query_text: &str,
    fields_to_search: Vec<Field>,
) -> tantivy::Result<Vec<(f32, DocAddress)>> {
    let reader = index.reader()?;
    let searcher = reader.searcher();

    let query_parser = QueryParser::for_index(&index, fields_to_search);
    let query = query_parser.parse_query(query_text)?;

    let top_docs: Vec<(f32, DocAddress)> = searcher.search(
        &query,
        &TopDocs::with_limit(10).order_by_score(),
    )?;

    Ok(top_docs)
}
""",
        "function": "searcher_topdocs_collector_execute",
        "feature_type": "crud",
        "file_role": "route",
        "file_path": "src/core/searcher.rs",
    },
    # ── 4. Boolean query with AND/OR/NOT operators ──────────────────────────
    {
        "normalized_code": """\
use tantivy::query::{BooleanQuery, Occur, TermQuery};

fn build_boolean_query(
    field: Field,
    must_terms: Vec<&str>,
    should_terms: Vec<&str>,
    must_not_terms: Vec<&str>,
) -> BooleanQuery {
    let mut boolean_query = BooleanQuery::new();

    for term_str in must_terms {
        let term = Term::from_field_text(field, term_str);
        boolean_query.push(Box::new(TermQuery::new(term)), Occur::Must);
    }

    for term_str in should_terms {
        let term = Term::from_field_text(field, term_str);
        boolean_query.push(Box::new(TermQuery::new(term)), Occur::Should);
    }

    for term_str in must_not_terms {
        let term = Term::from_field_text(field, term_str);
        boolean_query.push(Box::new(TermQuery::new(term)), Occur::MustNot);
    }

    boolean_query
}
""",
        "function": "boolean_query_must_should_mustnot",
        "feature_type": "crud",
        "file_role": "route",
        "file_path": "src/query/boolean_query.rs",
    },
    # ── 5. Phrase query (adjacent terms with positions) ──────────────────────
    {
        "normalized_code": """\
use tantivy::query::PhraseQuery;
use tantivy::Term;

fn phrase_search(
    field: Field,
    phrase_terms: Vec<&str>,
) -> tantivy::Result<PhraseQuery> {
    let mut phrase_query = PhraseQuery::new(
        phrase_terms
            .iter()
            .map(|t| Term::from_field_text(field, t))
            .collect(),
    );

    Ok(phrase_query)
}
""",
        "function": "phrase_query_adjacent_terms",
        "feature_type": "crud",
        "file_role": "route",
        "file_path": "src/query/phrase_query.rs",
    },
    # ── 6. Fuzzy query with Levenshtein distance ─────────────────────────────
    {
        "normalized_code": """\
use tantivy::query::FuzzyTermQuery;
use tantivy::Term;

fn fuzzy_search(
    field: Field,
    term_text: &str,
    distance: u8,
) -> FuzzyTermQuery {
    let term = Term::from_field_text(field, term_text);

    FuzzyTermQuery::new(term, distance, true)
}
""",
        "function": "fuzzy_query_levenshtein_distance",
        "feature_type": "crud",
        "file_role": "route",
        "file_path": "src/query/fuzzy_query.rs",
    },
    # ── 7. Query parser with default operators ──────────────────────────────
    {
        "normalized_code": """\
use tantivy::query::QueryParser;

fn parse_user_query(
    index: &Index,
    fields_to_search: Vec<Field>,
    query_string: &str,
) -> tantivy::Result<Box<dyn Query>> {
    let mut query_parser = QueryParser::for_index(&index, fields_to_search);

    query_parser.set_default_conjunction(true);
    query_parser.set_field_boost(fields_to_search[0], 2.0);

    let query = query_parser.parse_query(query_string)?;

    Ok(query)
}
""",
        "function": "query_parser_user_string_parse",
        "feature_type": "crud",
        "file_role": "route",
        "file_path": "src/query/query_parser.rs",
    },
    # ── 8. Tokenizer configuration with stemmer and stop words ──────────────
    {
        "normalized_code": """\
use tantivy::tokenizer::{SimpleTokenizer, StopWordFilter, Stemmer, TextAnalyzer};

fn create_text_analyzer() -> TextAnalyzer {
    let tokenizer = SimpleTokenizer::default();

    TextAnalyzer::new(tokenizer)
        .filter(StopWordFilter::default())
        .filter(Stemmer::new("english"))
}
""",
        "function": "tokenizer_pipeline_stemmer_stopwords",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "src/tokenizer/mod.rs",
    },
    # ── 9. Snippet generator with highlighting ──────────────────────────────
    {
        "normalized_code": """\
use tantivy::snippet::{Snippet, SnippetGenerator};

fn generate_snippet(
    searcher: &Searcher,
    doc_address: DocAddress,
    field: Field,
    query: &dyn Query,
) -> tantivy::Result<Snippet> {
    let mut snippet_generator = SnippetGenerator::create(searcher, &query, field)?;

    snippet_generator.set_snippet_size(150);
    snippet_generator.set_html_pre_tag("<em>");
    snippet_generator.set_html_post_tag("</em>");

    let snippet = snippet_generator.snippet_from_doc_address(doc_address)?;

    Ok(snippet)
}
""",
        "function": "snippet_generator_highlighting_fragment",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/snippet/mod.rs",
    },
    # ── 10. Merge policy configuration for segment merging ────────────────────
    {
        "normalized_code": """\
use tantivy::indexer::LogMergePolicy;

fn configure_merge_policy(
    merge_factor: usize,
    min_merge_size: usize,
    min_layer_size: usize,
) -> LogMergePolicy {
    let mut merge_policy = LogMergePolicy::default();

    merge_policy.set_min_merge_size(min_merge_size);
    merge_policy.set_min_layer_size(min_layer_size);
    merge_policy.set_level_log_size(merge_factor as f64);

    merge_policy
}
""",
        "function": "merge_policy_log_configuration",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "src/indexer/merge_policy.rs",
    },
    # ── 11. Concurrent index writer with commit and delete ───────────────────
    {
        "normalized_code": """\
use tantivy::{Index, IndexWriter, Term};

fn concurrent_indexing(
    index: &Index,
) -> tantivy::Result<()> {
    let mut index_writer = index.writer(100_000_000)?;

    for i in 0..1000 {
        let field = index.schema().get_field("element_id")?;
        let element_id = Term::from_field_u64(field, i);

        index_writer.add_document(doc!(field => i))?;

        if i % 100 == 0 {
            index_writer.commit()?;
        }
    }

    let delete_field = index.schema().get_field("element_id")?;
    index_writer.delete_term(Term::from_field_u64(delete_field, 42));

    index_writer.commit()?;

    Ok(())
}
""",
        "function": "index_writer_concurrent_batch_commit_delete",
        "feature_type": "crud",
        "file_role": "utility",
        "file_path": "src/indexer/index_writer.rs",
    },
    # ── 12. Faceted search with term aggregation ─────────────────────────────
    {
        "normalized_code": """\
use tantivy::aggregation::{Aggregation, AggregationCollector};

fn faceted_search(
    searcher: &Searcher,
    query: &dyn Query,
    facet_field: Field,
) -> tantivy::Result<AggregationResults> {
    let mut aggregations = Aggregations::default();

    aggregations.insert(
        "by_label".to_string(),
        Aggregation::Bucket(
            BucketAggregation::Terms(
                TermsAggregation::default()
                    .set_field(facet_field)
                    .set_size(20),
            ),
        ),
    );

    let agg_collector = AggregationCollector::from_aggs(aggregations, Default::default());

    let agg_results = searcher.search(&query, &agg_collector)?;

    Ok(agg_results)
}
""",
        "function": "faceted_search_terms_aggregation",
        "feature_type": "crud",
        "file_role": "route",
        "file_path": "src/aggregation/mod.rs",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "define schema with text field indexed and stored",
    "create index and add documents with index writer",
    "search index with query parser and top docs collector",
    "boolean query AND OR NOT operators Occur",
    "phrase query adjacent terms with positions",
    "fuzzy query Levenshtein distance matching",
    "parse user query string with default operators",
    "tokenizer pipeline stemmer lowercase stop words",
    "snippet generator highlighting query terms",
    "merge policy configuration log merge factor",
    "concurrent index writer add delete commit batch",
    "faceted search term aggregation bucket",
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
