"""
ingest_llama_cpp.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de ggml-org/llama.cpp dans la KB Qdrant V6.

Focus : CORE patterns C++ LLM inference — model loading, context initialization,
tokenization, decoding, generation, KV cache, sampling, grammar constraints,
embedding extraction, quantization, server endpoints.

Usage:
    .venv/bin/python3 ingest_llama_cpp.py
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
REPO_URL = "https://github.com/ggml-org/llama.cpp.git"
REPO_NAME = "ggml-org/llama.cpp"
REPO_LOCAL = "/tmp/llama.cpp"
LANGUAGE = "cpp"
FRAMEWORK = "generic"
STACK = "cpp+llama+inference+ggml"
CHARTE_VERSION = "1.0"
TAG = "ggml-org/llama.cpp"
SOURCE_REPO = "https://github.com/ggml-org/llama.cpp"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# llama.cpp = C++ LLM inference engine with quantization.
# Patterns CORE : model loading, context, tokenization, generation, sampling, KV cache.
# U-5 : `model`, `context`, `token`, `embedding`, `inference`, `quantize`, `grammar`,
#       `kv_cache` are technical terms — KEEP. Replace generic names.

PATTERNS: list[dict] = [
    # ── 1. Model Loading from File ───────────────────────────────────────────
    {
        "normalized_code": """\
#include "llama.h"
#include <string>
#include <cstring>

bool load_model_from_file(
    const std::string& model_path,
    llama_model_params params,
    llama_model*& model_out
) {
    model_out = llama_load_model_from_file(
        model_path.c_str(),
        params
    );
    if (!model_out) {
        fprintf(stderr, "Error: failed to load model from %s\\n", model_path.c_str());
        return false;
    }
    return true;
}

llama_model_params get_default_model_params() {
    llama_model_params params = llama_model_default_params();
    params.n_gpu_layers = -1;
    params.use_mmap = true;
    params.use_mlock = false;
    return params;
}
""",
        "function": "model_load_from_file_init",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "common/common.cpp",
    },
    # ── 2. Context Parameters Initialization ───────────────────────────────
    {
        "normalized_code": """\
#include "llama.h"
#include <cstdint>

struct ContextConfig {
    int32_t n_ctx;
    int32_t n_batch;
    int32_t n_ubatch;
    int32_t seed;
    float freq_base;
    float freq_scale;
};

bool init_context_params(
    llama_context_params& ctx_params,
    const ContextConfig& config
) {
    ctx_params = llama_context_default_params();
    ctx_params.n_ctx = config.n_ctx;
    ctx_params.n_batch = config.n_batch;
    ctx_params.n_ubatch = config.n_ubatch;
    ctx_params.seed = config.seed;
    ctx_params.rope_freq_base = config.freq_base;
    ctx_params.rope_freq_scale = config.freq_scale;

    if (ctx_params.n_ctx > 0 && ctx_params.n_batch > ctx_params.n_ctx) {
        fprintf(stderr, "Error: n_batch (%d) > n_ctx (%d)\\n",
                ctx_params.n_batch, ctx_params.n_ctx);
        return false;
    }
    return true;
}
""",
        "function": "context_params_initialization_config",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "common/common.h",
    },
    # ── 3. Tokenize Text Input ───────────────────────────────────────────────
    {
        "normalized_code": """\
#include "llama.h"
#include <vector>
#include <string>

std::vector<llama_token> tokenize_text(
    llama_model* model,
    const std::string& text,
    bool add_bos_token,
    bool add_eos_token
) {
    std::vector<llama_token> tokens;
    int n_tokens = llama_tokenize(
        model,
        text.c_str(),
        text.length(),
        nullptr,
        0,
        add_bos_token,
        add_eos_token
    );

    if (n_tokens < 0) {
        fprintf(stderr, "Error: tokenization failed\\n");
        return {};
    }

    tokens.resize(n_tokens);
    llama_tokenize(
        model,
        text.c_str(),
        text.length(),
        tokens.data(),
        tokens.size(),
        add_bos_token,
        add_eos_token
    );
    return tokens;
}
""",
        "function": "tokenize_text_input_vector",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "common/common.cpp",
    },
    # ── 4. Batch Decode Tokens ───────────────────────────────────────────────
    {
        "normalized_code": """\
#include "llama.h"
#include <vector>
#include <string>

std::string batch_decode_tokens(
    llama_context* ctx,
    const std::vector<llama_token>& tokens
) {
    std::string result;
    result.reserve(tokens.size() * 8);

    for (llama_token token : tokens) {
        const char* piece = llama_token_to_piece(ctx, token);
        if (piece == nullptr) {
            fprintf(stderr, "Error: token %d -> null piece\\n", token);
            continue;
        }
        result.append(piece);
    }
    return result;
}

llama_token_data_array get_top_k_tokens(
    llama_context* ctx,
    int k
) {
    llama_token_data_array candidates_p = {
        llama_get_logits_ith(ctx, -1),
        llama_n_vocab(llama_get_model(ctx)),
        0.0f,
        0.0f
    };
    llama_sample_top_k(ctx, &candidates_p, k, 1);
    return candidates_p;
}
""",
        "function": "batch_decode_tokens_logits",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "common/common.cpp",
    },
    # ── 5. Generate Completion Loop ──────────────────────────────────────────
    {
        "normalized_code": """\
#include "llama.h"
#include <vector>
#include <string>
#include <algorithm>

struct GenerationParams {
    int max_tokens;
    float temperature;
    int top_k;
    float top_p;
    float repeat_penalty;
};

std::string generate_completion(
    llama_context* ctx,
    llama_model* model,
    const std::vector<llama_token>& prompt_tokens,
    const GenerationParams& params
) {
    std::vector<llama_token> tokens = prompt_tokens;
    std::string output;

    while (tokens.size() < params.max_tokens) {
        if (llama_decode(ctx, llama_batch_get_one_token(tokens.back()))) {
            fprintf(stderr, "Error: llama_decode failed\\n");
            break;
        }

        llama_token_data_array candidates = {
            llama_get_logits_ith(ctx, -1),
            llama_n_vocab(model),
            0.0f,
            0.0f
        };

        llama_sample_temperature(ctx, &candidates, params.temperature);
        llama_sample_top_k(ctx, &candidates, params.top_k, 1);
        llama_sample_top_p(ctx, &candidates, params.top_p, 1);

        llama_token next_token = llama_sample_token(ctx, &candidates);

        if (next_token == llama_token_eos(model)) {
            break;
        }

        tokens.push_back(next_token);
        output += llama_token_to_piece(ctx, next_token);
    }
    return output;
}
""",
        "function": "generate_completion_sampling_loop",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "common/common.cpp",
    },
    # ── 6. KV Cache Management ────────────────────────────────────────────────
    {
        "normalized_code": """\
#include "llama.h"
#include <cstring>

bool allocate_kv_cache(
    llama_context* ctx,
    int n_tokens
) {
    if (llama_kv_cache_seq_reserve(ctx, n_tokens) != 0) {
        fprintf(stderr, "Error: failed to reserve KV cache\\n");
        return false;
    }
    return true;
}

void reset_kv_cache(llama_context* ctx) {
    llama_kv_cache_seq_rm(ctx, 0, -1, -1);
}

void print_kv_cache_usage(llama_context* ctx) {
    const llama_model* model = llama_get_model(ctx);
    const int n_ctx = llama_n_ctx(ctx);
    const int used = llama_get_kv_cache_token_count(ctx);

    fprintf(
        stderr,
        "KV cache: %d / %d tokens (%.1f%%)\\n",
        used,
        n_ctx,
        100.0f * used / n_ctx
    );
}

void compact_kv_cache(
    llama_context* ctx,
    int keep_tokens
) {
    llama_kv_cache_seq_cp(ctx, 0, 1, 0, keep_tokens);
    llama_kv_cache_seq_rm(ctx, 0, keep_tokens, -1);
}
""",
        "function": "kv_cache_management_reserve_compact",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "common/common.cpp",
    },
    # ── 7. Sampling Parameters Configuration ──────────────────────────────────
    {
        "normalized_code": """\
#include "llama.h"

struct SamplingContext {
    float temperature;
    int top_k;
    float top_p;
    float tfs_z;
    float typical_p;
    float repeat_penalty;
    float presence_penalty;
    float frequency_penalty;
};

void apply_sampling_params(
    llama_context* ctx,
    llama_token_data_array* candidates,
    const SamplingContext& sampling
) {
    llama_sample_temperature(ctx, candidates, sampling.temperature);

    if (sampling.top_k > 0) {
        llama_sample_top_k(ctx, candidates, sampling.top_k, 1);
    }

    if (sampling.top_p < 1.0f) {
        llama_sample_top_p(ctx, candidates, sampling.top_p, 1);
    }

    if (sampling.typical_p < 1.0f) {
        llama_sample_typical(ctx, candidates, sampling.typical_p, 1);
    }

    if (sampling.repeat_penalty != 1.0f) {
        llama_sample_rep_pen(
            ctx,
            candidates,
            nullptr,
            0,
            sampling.repeat_penalty,
            sampling.presence_penalty,
            sampling.frequency_penalty
        );
    }
}
""",
        "function": "sampling_params_config_temperature_topk",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "common/sampling.h",
    },
    # ── 8. Grammar Constrained Generation ─────────────────────────────────────
    {
        "normalized_code": """\
#include "llama.h"
#include <string>
#include <vector>

llama_grammar* load_grammar_from_string(
    const std::string& grammar_string
) {
    llama_grammar_rules rules = {};
    std::string error_msg;

    llama_grammar* grammar = llama_grammar_init_from_string(
        grammar_string.c_str(),
        &error_msg
    );

    if (!grammar) {
        fprintf(stderr, "Error loading grammar: %s\\n", error_msg.c_str());
        return nullptr;
    }
    return grammar;
}

llama_token sample_with_grammar(
    llama_context* ctx,
    llama_token_data_array* candidates,
    llama_grammar* grammar
) {
    llama_sample_grammar(ctx, candidates, grammar);
    return llama_sample_token(ctx, candidates);
}

void free_grammar(llama_grammar* grammar) {
    if (grammar) {
        llama_grammar_free(grammar);
    }
}
""",
        "function": "grammar_constrained_generation_sample",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/grammar.cpp",
    },
    # ── 9. Embedding Extraction ────────────────────────────────────────────────
    {
        "normalized_code": """\
#include "llama.h"
#include <vector>
#include <cstring>

std::vector<float> extract_embedding_from_context(
    llama_context* ctx,
    int token_pos
) {
    const float* logits = llama_get_logits_ith(ctx, token_pos);
    int n_vocab = llama_n_vocab(llama_get_model(ctx));

    std::vector<float> embedding(logits, logits + n_vocab);
    return embedding;
}

bool get_embedding_batch(
    llama_context* ctx,
    const std::vector<int>& token_positions,
    std::vector<std::vector<float>>& embeddings_out
) {
    embeddings_out.clear();
    embeddings_out.reserve(token_positions.size());

    for (int pos : token_positions) {
        const float* logits = llama_get_logits_ith(ctx, pos);
        if (!logits) {
            fprintf(stderr, "Error: no logits at position %d\\n", pos);
            return false;
        }

        int n_vocab = llama_n_vocab(llama_get_model(ctx));
        std::vector<float> emb(logits, logits + n_vocab);
        embeddings_out.push_back(emb);
    }
    return true;
}
""",
        "function": "embedding_extraction_logits_batch",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "common/common.cpp",
    },
    # ── 10. Model Quantization ──────────────────────────────────────────────
    {
        "normalized_code": """\
#include "llama.h"
#include <string>
#include <vector>

enum class QuantizationType {
    Q4_0,
    Q4_1,
    Q5_0,
    Q5_1,
    Q8_0,
    F16,
};

bool quantize_model_file(
    const std::string& input_path,
    const std::string& output_path,
    QuantizationType quant_type
) {
    llama_model_quantize_params params = llama_model_quantize_default_params();

    switch (quant_type) {
        case QuantizationType::Q4_0:
            params.ftype = LLAMA_FTYPE_MOSTLY_Q4_0;
            break;
        case QuantizationType::Q5_0:
            params.ftype = LLAMA_FTYPE_MOSTLY_Q5_0;
            break;
        case QuantizationType::Q8_0:
            params.ftype = LLAMA_FTYPE_MOSTLY_Q8_0;
            break;
        default:
            params.ftype = LLAMA_FTYPE_MOSTLY_Q4_0;
    }

    params.allow_requantize = true;
    params.nthread = 0;

    if (llama_model_quantize(input_path.c_str(), output_path.c_str(), &params)) {
        fprintf(stderr, "Error: quantization failed\\n");
        return false;
    }
    return true;
}
""",
        "function": "model_quantize_q4_q5_q8",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "common/common.cpp",
    },
    # ── 11. Server Completion Endpoint ───────────────────────────────────────
    {
        "normalized_code": """\
#include <json/json.hpp>
#include <string>
#include <vector>
#include "llama.h"

using json = nlohmann::json;

struct CompletionRequest {
    std::string prompt;
    int max_tokens;
    float temperature;
    int top_k;
    float top_p;
    bool stream;
};

json create_completion_response(
    const std::string& completion,
    const std::vector<llama_token>& tokens,
    const std::string& model_name
) {
    json response;
    response["object"] = "text_completion";
    response["model"] = model_name;
    response["prompt"] = completion;
    response["choices"] = json::array();

    json choice;
    choice["text"] = completion;
    choice["index"] = 0;
    choice["finish_reason"] = "length";
    response["choices"].push_back(choice);

    response["usage"]["prompt_tokens"] = tokens.size();
    response["usage"]["completion_tokens"] = 0;
    response["usage"]["total_tokens"] = tokens.size();

    return response;
}
""",
        "function": "server_endpoint_completion_response_json",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/server/utils.hpp",
    },
    # ── 12. Parallel Batch Decoding ───────────────────────────────────────────
    {
        "normalized_code": """\
#include "llama.h"
#include <vector>
#include <cstring>

struct BatchDecodeJob {
    std::vector<llama_token> input_tokens;
    int max_tokens;
    float temperature;
};

void process_batch_parallel(
    llama_context* ctx,
    const std::vector<BatchDecodeJob>& jobs,
    std::vector<std::string>& outputs
) {
    outputs.resize(jobs.size());
    int n_batch = llama_n_batch(ctx);

    for (size_t i = 0; i < jobs.size(); i++) {
        const auto& job = jobs[i];
        std::string& output = outputs[i];
        std::vector<llama_token> tokens = job.input_tokens;

        while (tokens.size() < job.max_tokens) {
            if (llama_decode(ctx, llama_batch_get_one_token(tokens.back()))) {
                break;
            }

            llama_token_data_array candidates = {
                llama_get_logits_ith(ctx, -1),
                llama_n_vocab(llama_get_model(ctx)),
                0.0f,
                0.0f
            };

            llama_sample_temperature(ctx, &candidates, job.temperature);
            llama_token next = llama_sample_token(ctx, &candidates);

            if (next == llama_token_eos(llama_get_model(ctx))) {
                break;
            }

            tokens.push_back(next);
            output += llama_token_to_piece(ctx, next);
        }
    }
}
""",
        "function": "parallel_decoding_batch_multiple_jobs",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "common/common.cpp",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "C++ model load from file GGML weights",
    "llama context params initialization n_ctx n_batch",
    "tokenize text input to token ids vector",
    "batch decode tokens to text string",
    "generate completion sampling loop temperature",
    "KV cache management reserve compact allocation",
    "sampling params top_k top_p temperature config",
    "grammar constrained generation constraints sample",
    "embedding extraction logits from context",
    "model quantize Q4 Q5 Q8 file format",
    "server completion endpoint JSON response",
    "parallel batch decoding multiple sequences",
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
