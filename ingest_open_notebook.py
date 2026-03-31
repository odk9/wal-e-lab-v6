"""
ingest_open_notebook.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de lfnovo/open-notebook dans la KB Qdrant V6.

Focus : CORE patterns RAG/AI notebook (content-type chunking, embeddings, retrieval,
LangGraph state machines, transformations, chat memory, multi-provider LLMs).
PAS des patterns CRUD/API — patterns de génération et RAG.

Usage:
    .venv/bin/python3 ingest_open_notebook.py
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
REPO_URL = "https://github.com/lfnovo/open-notebook.git"
REPO_NAME = "lfnovo/open-notebook"
REPO_LOCAL = "/tmp/open-notebook"
LANGUAGE = "python"
FRAMEWORK = "langraph"
STACK = "langraph+surrealdb+fastembed"
CHARTE_VERSION = "1.0"
TAG = "lfnovo/open-notebook"
SOURCE_REPO = "https://github.com/lfnovo/open-notebook"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Open Notebook = RAG/AI notebook platform. Multi-modal content retrieval + LangGraph.
# Patterns CORE : content chunking, vector search, LLM orchestration, chat memory.
# U-5 : "Note" → "Xxx", "Source" → "XxxSource", "Notebook" → "XxxNotebook", etc.

PATTERNS: list[dict] = [
    # ── 1. Content-type aware chunking ───────────────────────────────────────
    {
        "normalized_code": """\
from typing import Callable

from langchain.text_splitter import (
    CharacterTextSplitter,
    HTMLHeaderTextSplitter,
    MarkdownHeaderTextSplitter,
)


def detect_content_type(content: str) -> str:
    \"\"\"Detect if content is HTML, Markdown, or plain text.\"\"\"
    content_lower = content.lower()
    if "<html" in content_lower or "<body" in content_lower:
        return "html"
    if "# " in content or "## " in content or "### " in content:
        return "markdown"
    return "plain"


def chunk_content(
    content: str,
    chunk_size: int = 1024,
    chunk_overlap: int = 200,
) -> list[str]:
    \"\"\"Chunk text with content-type aware splitter selection.\"\"\"
    content_type = detect_content_type(content)

    if content_type == "markdown":
        headers = [
            ("#", "h1"),
            ("##", "h2"),
            ("###", "h3"),
        ]
        splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=headers,
            return_each_line=False,
        )
        splits = splitter.split_text(content)
        return [s.page_content for s in splits]

    if content_type == "html":
        headers = [
            ("h1", "h1"),
            ("h2", "h2"),
            ("h3", "h3"),
        ]
        splitter = HTMLHeaderTextSplitter(
            headers_to_split_on=headers,
            return_each_line=False,
        )
        splits = splitter.split_text(content)
        return [s.page_content for s in splits]

    splitter = CharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separator="\\n",
    )
    return splitter.split_text(content)
""",
        "function": "content_type_aware_chunking",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/ingestion/chunker.py",
    },
    # ── 2. Mean pool embeddings for large text ───────────────────────────────
    {
        "normalized_code": """\
import numpy as np


def mean_pool_embeddings(
    embeddings: list[np.ndarray],
    normalize: bool = True,
) -> np.ndarray:
    \"\"\"Mean pool chunk embeddings → single normalized vector.\"\"\"
    if not embeddings:
        return np.array([])

    pooled = np.mean(embeddings, axis=0)

    if normalize:
        norm = np.linalg.norm(pooled, ord=2)
        if norm > 0:
            pooled = pooled / norm

    return pooled


def embed_large_text(
    text: str,
    embedder: object,
    chunk_size: int = 512,
    chunk_overlap: int = 100,
) -> np.ndarray:
    \"\"\"Embed large text: chunk → batch embed → mean pool → normalize.\"\"\"
    chunks = chunk_text(text, chunk_size, chunk_overlap)
    if not chunks:
        return np.array([])

    chunk_embeddings = embedder.embed_documents(chunks)
    chunk_embeddings = [
        np.array(e) / (np.linalg.norm(e) + 1e-8) for e in chunk_embeddings
    ]

    result = mean_pool_embeddings(chunk_embeddings, normalize=True)
    return result
""",
        "function": "mean_pool_embeddings",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/embedding/pooler.py",
    },
    # ── 3. RAG strategy generation (multi-search from question) ──────────────
    {
        "normalized_code": """\
from typing import Optional

from langchain_core.language_model import BaseLanguageModel


def generate_rag_strategy(
    question: str,
    llm: BaseLanguageModel,
    max_searches: int = 5,
) -> dict[str, object]:
    \"\"\"LLM generates multi-search strategy from input question.

    Returns:
        {
            "searches": [
                {
                    "query": "search term",
                    "extraction_instruction": "extract what...",
                    "priority": 1,  # higher = search first
                }
            ]
        }
    \"\"\"
    prompt = (
        "You are a RAG strategy planner. Given an input question, "
        f"generate up to {max_searches} "
        "targeted searches to answer it comprehensively.\\n\\n"
        f"Question: {question}\\n\\n"
        "For each search, provide:\\n"
        "1. A short search query (3-7 words)\\n"
        "2. Instructions for what to extract from results\\n"
        f"3. Priority (1=highest, {max_searches}=lowest)\\n\\n"
        "Format as JSON with \\"searches\\" key containing array of search objects."
    )
    response = llm.invoke(prompt)
    try:
        import json
        return json.loads(response.content)
    except Exception:
        return {"searches": [{"query": question, "extraction_instruction": "answer the question", "priority": 1}]}
""",
        "function": "rag_strategy_generation",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "src/retrieval/strategy.py",
    },
    # ── 4. RAG parallel search dispatch ──────────────────────────────────────
    {
        "normalized_code": """\
import asyncio
from typing import Any

from langchain_community.embeddings import OpenAIEmbeddings


async def parallel_search_dispatch(
    question: str,
    searches: list[dict],
    embedder: object,
    vector_search_fn: Any,
    llm: Any,
) -> list[dict]:
    \"\"\"Fan-out parallel searches: embed → vector search → LLM extraction.\"\"\"
    coroutines = []
    for search in searches:
        coroutines.append(
            _single_search(
                query=search["query"],
                extraction_instruction=search["extraction_instruction"],
                embedder=embedder,
                vector_search_fn=vector_search_fn,
                llm=llm,
            )
        )

    results = await asyncio.gather(*coroutines, return_exceptions=True)

    consolidated = []
    for r in results:
        if not isinstance(r, Exception):
            consolidated.append(r)

    return consolidated


async def _single_search(
    query: str,
    extraction_instruction: str,
    embedder: object,
    vector_search_fn: Any,
    llm: Any,
) -> dict:
    \"\"\"Execute one search: embed → retrieve → extract via LLM.\"\"\"
    query_vector = embedder.embed_query(query)
    results = vector_search_fn(query_vector, top_k=5)

    context = "\\n".join([r.get("text", "") for r in results[:3]])
    extraction_prompt = (
        f"{extraction_instruction}\\n\\n"
        f"Context:\\n{context}\\n\\n"
        "Provide extracted information concisely."
    )
    extracted = llm.invoke(extraction_prompt)

    return {
        "search_query": query,
        "extracted": extracted.content,
        "source_count": len(results),
    }
""",
        "function": "rag_parallel_search_dispatch",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "src/retrieval/dispatcher.py",
    },
    # ── 5. Vector search with threshold filtering ────────────────────────────
    {
        "normalized_code": """\
from typing import Optional


def vector_search_with_threshold(
    query_vector: list[float],
    index: object,
    minimum_score: float = 0.6,
    limit: int = 10,
) -> list[dict]:
    \"\"\"Vector similarity search with minimum_score threshold.\"\"\"
    raw_results = index.search(
        query=query_vector,
        limit=limit * 2,  # over-fetch to account for threshold filtering
    )

    filtered = []
    for result in raw_results:
        if result.get("score", 0.0) >= minimum_score:
            filtered.append(result)

    return filtered[:limit]


def adaptive_threshold_search(
    query_vector: list[float],
    index: object,
    initial_threshold: float = 0.6,
    min_results: int = 3,
    limit: int = 10,
) -> list[dict]:
    \"\"\"Search with adaptive threshold: lower if insufficient results.\"\"\"
    threshold = initial_threshold
    while threshold >= 0.3:
        results = vector_search_with_threshold(
            query_vector=query_vector,
            index=index,
            minimum_score=threshold,
            limit=limit,
        )
        if len(results) >= min_results:
            return results
        threshold -= 0.1

    return vector_search_with_threshold(
        query_vector=query_vector,
        index=index,
        minimum_score=0.3,
        limit=limit,
    )
""",
        "function": "vector_search_with_threshold",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/retrieval/search.py",
    },
    # ── 6. Fire and forget job submission with exponential backoff ──────────
    {
        "normalized_code": """\
import asyncio
import random
from typing import Any, Callable, Optional


async def submit_job_with_backoff(
    job_id: str,
    job_fn: Callable,
    args: tuple = (),
    kwargs: dict[str, Any] | None = None,
    max_retries: int = 15,
    base_delay_s: float = 0.1,
) -> dict[str, Any]:
    \"\"\"Fire-and-forget job with exponential backoff + jitter.\"\"\"
    if kwargs is None:
        kwargs = {}

    for attempt in range(max_retries):
        try:
            result = await job_fn(*args, **kwargs)
            return {
                "job_id": job_id,
                "status": "success",
                "result": result,
                "attempt": attempt + 1,
            }
        except Exception as exc:
            if attempt == max_retries - 1:
                return {
                    "job_id": job_id,
                    "status": "failed",
                    "error": str(exc),
                    "attempt": attempt + 1,
                }

            delay = base_delay_s * (2 ** attempt)
            jitter = random.uniform(0, delay * 0.1)
            await asyncio.sleep(delay + jitter)

    return {"job_id": job_id, "status": "exhausted", "attempt": max_retries}
""",
        "function": "fire_and_forget_job_submission",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/async/jobs.py",
    },
    # ── 7. Source ingestion workflow (LangGraph state machine) ──────────────
    {
        "normalized_code": """\
from typing import Any

from langgraph.graph import StateGraph
from langgraph.graph.graph import CompiledGraph


class XxxSourceState(dict):
    \"\"\"State for source ingestion workflow.\"\"\"
    source_id: str
    source_url: str
    source_content: str
    chunks: list[str]
    embeddings: list[object]
    transformations: list[str]
    status: str


def build_source_ingestion_graph() -> CompiledGraph:
    \"\"\"Build LangGraph workflow: extract → save → trigger transformations.\"\"\"
    workflow = StateGraph(XxxSourceState)

    workflow.add_node("extract", _extract_content)
    workflow.add_node("save", _save_to_db)
    workflow.add_node("chunk", _chunk_content)
    workflow.add_node("embed", _embed_chunks)
    workflow.add_node("transform", _trigger_transformations)

    workflow.set_entry_point("extract")
    workflow.add_edge("extract", "save")
    workflow.add_edge("save", "chunk")
    workflow.add_edge("chunk", "embed")
    workflow.add_edge("embed", "transform")
    workflow.add_edge("transform", "__end__")

    return workflow.compile()


async def _extract_content(state: XxxSourceState) -> XxxSourceState:
    \"\"\"Extract content from source_url.\"\"\"
    content = await fetch_url_content(state["source_url"])
    state["source_content"] = content
    state["status"] = "extracted"
    return state


async def _save_to_db(state: XxxSourceState) -> XxxSourceState:
    \"\"\"Save source to database.\"\"\"
    db_id = await save_xxx_source(state)
    state["source_id"] = db_id
    state["status"] = "saved"
    return state


async def _chunk_content(state: XxxSourceState) -> XxxSourceState:
    \"\"\"Chunk content.\"\"\"
    chunks = chunk_content(state["source_content"])
    state["chunks"] = chunks
    state["status"] = "chunked"
    return state


async def _embed_chunks(state: XxxSourceState) -> XxxSourceState:
    \"\"\"Embed all chunks in parallel.\"\"\"
    embeddings = await embed_documents_batch(state["chunks"])
    state["embeddings"] = embeddings
    state["status"] = "embedded"
    return state


async def _trigger_transformations(state: XxxSourceState) -> XxxSourceState:
    \"\"\"Fan-out parallel transformations on content.\"\"\"
    coroutines = [
        apply_xxx_transformation(state["source_content"], ttype)
        for ttype in ["summary", "keywords", "sentiment"]
    ]
    results = await asyncio.gather(*coroutines)
    state["transformations"] = results
    state["status"] = "transformed"
    return state
""",
        "function": "source_ingestion_workflow",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "src/ingestion/workflow.py",
    },
    # ── 8. Transformation pipeline (user-defined LLM transformations) ───────
    {
        "normalized_code": """\
import asyncio
from typing import Any

from langchain_core.language_model import BaseLanguageModel


async def apply_transformation(
    source_text: str,
    transformation_prompt: str,
    llm: BaseLanguageModel,
    embedder: Any,
) -> dict[str, object]:
    \"\"\"Apply custom LLM transformation: prompt + text → insight → embed.\"\"\"
    full_prompt = f\"\"\"\
{transformation_prompt}

Source text:
{source_text}

Provide the transformation result:
\"\"\"

    insight_response = llm.invoke(full_prompt)
    insight_text = insight_response.content

    insight_embedding = embedder.embed_query(insight_text)

    return {
        "insight": insight_text,
        "insight_embedding": insight_embedding,
        "transformation_prompt_hash": hash(transformation_prompt),
    }


async def batch_apply_transformations(
    source_text: str,
    transformation_templates: list[dict],
    llm: BaseLanguageModel,
    embedder: Any,
) -> list[dict]:
    \"\"\"Apply multiple transformations in parallel.\"\"\"
    coroutines = [
        apply_transformation(
            source_text=source_text,
            transformation_prompt=t["prompt"],
            llm=llm,
            embedder=embedder,
        )
        for t in transformation_templates
    ]

    results = await asyncio.gather(*coroutines, return_exceptions=True)
    return [r for r in results if not isinstance(r, Exception)]
""",
        "function": "transformation_pipeline",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "src/transformation/apply.py",
    },
    # ── 9. Chat with memory (LangGraph SQLite checkpointer) ─────────────────
    {
        "normalized_code": """\
from typing import Optional

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import StateGraph


class ChatSessionState(dict):
    \"\"\"Chat session state with memory.\"\"\"
    session_id: str
    history: list[dict]
    context: str
    model_name: str


def build_chat_graph_with_memory(
    db_path: str = "chat_memory.db",
) -> object:
    \"\"\"Build chat graph with SQLite checkpointer for memory.\"\"\"
    checkpointer = SqliteSaver(conn=db_path)

    workflow = StateGraph(ChatSessionState)
    workflow.add_node("chat", _chat_node)
    workflow.add_node("memory", _update_memory_node)

    workflow.set_entry_point("chat")
    workflow.add_edge("chat", "memory")
    workflow.add_edge("memory", "__end__")

    graph = workflow.compile(checkpointer=checkpointer)
    return graph


async def invoke_chat_with_memory(
    session_id: str,
    input_text: str,
    llm: object,
    graph: object,
) -> str:
    \"\"\"Invoke chat with persistent memory retrieval.\"\"\"
    config = {"configurable": {"thread_id": session_id}}

    state = {
        "session_id": session_id,
        "history": [{"role": "input", "content": input_text}],
        "context": "",
        "model_name": "gpt-4",
    }

    result = graph.invoke(state, config=config)
    return result.get("assistant_response", "")


async def _chat_node(state: ChatSessionState) -> ChatSessionState:
    \"\"\"Process chat input.\"\"\"
    last_input = state["history"][-1]["content"]
    response = llm.invoke(last_input)
    state["history"].append({"role": "assistant", "content": response.content})
    return state


async def _update_memory_node(state: ChatSessionState) -> ChatSessionState:
    \"\"\"Update memory with conversation turn.\"\"\"
    state["context"] = "\\n".join([m["content"] for m in state["history"][-10:]])
    return state
""",
        "function": "chat_with_memory",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "src/chat/memory.py",
    },
    # ── 10. Multi-provider LLM provisioning (OpenAI, Anthropic, Google, etc.)
    {
        "normalized_code": """\
from typing import Optional

from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.language_model import BaseLanguageModel


PROVIDER_MODELS: dict[str, dict[str, str]] = {
    "openai": {"model": "gpt-4-turbo", "api_key_env": "OPENAI_API_KEY"},
    "anthropic": {"model": "claude-3-5-sonnet-20241022", "api_key_env": "ANTHROPIC_API_KEY"},
    "google": {"model": "gemini-2.5-flash", "api_key_env": "GOOGLE_API_KEY"},
    "groq": {"model": "mixtral-8x7b-32768", "api_key_env": "GROQ_API_KEY"},
    "ollama": {"model": "neural-chat", "base_url": "http://localhost:11434"},
}


def get_llm(
    provider: str = "openai",
    model: Optional[str] = None,
    temperature: float = 0.7,
    **kwargs,
) -> BaseLanguageModel:
    \"\"\"Get LLM instance for given provider with unified interface.\"\"\"
    provider_lower = provider.lower()
    config = PROVIDER_MODELS.get(provider_lower, PROVIDER_MODELS["openai"])
    model_name = model or config.get("model")

    if provider_lower == "openai":
        return ChatOpenAI(
            model_name=model_name,
            temperature=temperature,
            **kwargs,
        )

    if provider_lower == "anthropic":
        return ChatAnthropic(
            model_name=model_name,
            temperature=temperature,
            **kwargs,
        )

    if provider_lower == "google":
        return ChatGoogleGenerativeAI(
            model=model_name,
            temperature=temperature,
            **kwargs,
        )

    if provider_lower == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=model_name,
            temperature=temperature,
            base_url=config.get("base_url", "http://localhost:11434"),
            **kwargs,
        )

    raise ValueError(f"Unknown provider: {provider}")


async def override_model_per_session(
    session_id: str,
    provider: str,
    model: str,
) -> None:
    \"\"\"Override model for a specific session.\"\"\"
    session_config = {
        "session_id": session_id,
        "llm_provider": provider,
        "llm_model": model,
    }
    await save_session_config(session_config)
""",
        "function": "multi_provider_model_provisioning",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "src/llm/providers.py",
    },
    # ── 11. Async URL content fetcher with error handling ────────────────────
    {
        "normalized_code": """\
import aiohttp
from typing import Optional


async def fetch_url_content(
    url: str,
    timeout_s: float = 10.0,
    max_redirects: int = 5,
) -> str:
    \"\"\"Fetch URL content with async HTTP, timeout, redirect handling.\"\"\"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=timeout_s),
                allow_redirects=True,
                ssl=False,
            ) as response:
                if response.status == 200:
                    return await response.text()
                raise ValueError(f"HTTP {response.status}: {url}")
        except asyncio.TimeoutError:
            raise TimeoutError(f"Timeout fetching {url} after {timeout_s}s")
        except Exception as exc:
            raise RuntimeError(f"Failed to fetch {url}: {str(exc)}")


async def fetch_urls_parallel(
    urls: list[str],
    max_concurrent: int = 5,
) -> dict[str, str]:
    \"\"\"Fetch multiple URLs in parallel with concurrency limit.\"\"\"
    sem = asyncio.Semaphore(max_concurrent)

    async def _fetch_with_sem(url: str) -> tuple[str, str]:
        async with sem:
            try:
                content = await fetch_url_content(url)
                return url, content
            except Exception as e:
                return url, f"ERROR: {str(e)}"

    coroutines = [_fetch_with_sem(u) for u in urls]
    results = await asyncio.gather(*coroutines)
    return dict(results)
""",
        "function": "async_url_content_fetcher",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/ingestion/fetcher.py",
    },
    # ── 12. Keyword extraction and indexing (TF-IDF + semantic) ──────────────
    {
        "normalized_code": """\
from sklearn.feature_extraction.text import TfidfVectorizer
from typing import Optional


def extract_keywords_tfidf(
    documents: list[str],
    max_features: int = 20,
    ngram_range: tuple = (1, 2),
) -> dict[str, list[str]]:
    \"\"\"Extract TF-IDF keywords from document collection.\"\"\"
    vectorizer = TfidfVectorizer(
        max_features=max_features,
        ngram_range=ngram_range,
        stop_words="english",
    )

    try:
        tfidf_matrix = vectorizer.fit_transform(documents)
        feature_names = vectorizer.get_feature_names_out()

        keywords_by_doc = {}
        for doc_idx, row in enumerate(tfidf_matrix):
            top_indices = row.data.argsort()[-10:][::-1]
            keywords = [feature_names[i] for i in top_indices]
            keywords_by_doc[f"doc_{doc_idx}"] = keywords

        return keywords_by_doc
    except ValueError:
        return {}


async def extract_semantic_keywords(
    text: str,
    embedder: object,
    llm: object,
    count: int = 10,
) -> list[str]:
    \"\"\"Extract semantic keywords via LLM.\"\"\"
    prompt = f\"\"\"\
Extract {count} key concepts/keywords that capture the essence of this text.
Return as comma-separated list.

Text:
{text[:1000]}
\"\"\"
    response = llm.invoke(prompt)
    keywords = [k.strip() for k in response.content.split(",")]
    return keywords[:count]
""",
        "function": "keyword_extraction_and_indexing",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/indexing/keywords.py",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "detect HTML Markdown plain text content type chunking",
    "mean pool embeddings for large text normalization",
    "RAG strategy generation multi-search LLM planning",
    "parallel vector search dispatch with extraction",
    "vector similarity search with threshold filtering adaptive",
    "fire and forget async job submission exponential backoff jitter",
    "LangGraph source ingestion workflow state machine extraction",
    "LLM transformation pipeline user-defined prompts embeddings",
    "chat with memory SQLite checkpointer LangGraph persistence",
    "multi-provider LLM interface OpenAI Anthropic Google Groq Ollama",
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
            results.append({
                "query": q,
                "function": "NO_RESULT",
                "file_role": "?",
                "score": 0.0,
                "code_preview": "",
                "norm_ok": False,
            })
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
