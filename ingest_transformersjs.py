"""
ingest_transformersjs.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
d'huggingface/transformers.js dans la KB Qdrant V6.

Focus : ML pipeline patterns pour NLP/vision (text classification, token classification,
text generation, translation, summarization, feature extraction, image classification,
object detection, speech recognition, custom model loading, quantization, zero-shot).

Usage:
    .venv/bin/python3 ingest_transformersjs.py
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
REPO_URL = "https://github.com/huggingface/transformers.js.git"
REPO_NAME = "huggingface/transformers.js"
REPO_LOCAL = "/tmp/transformers.js"
LANGUAGE = "typescript"
FRAMEWORK = "generic"
STACK = "typescript+transformersjs+ml+huggingface"
CHARTE_VERSION = "1.0"
TAG = "huggingface/transformers.js"
SOURCE_REPO = "https://github.com/huggingface/transformers.js"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Transformers.js = ML pipeline library for transformers (NLP/vision).
# Patterns CORE : pipeline creation, model loading, inference, quantization.
# U-5 : `pipeline`, `model`, `tokenizer`, `processor`, `tensor` sont OK (ML terms).

PATTERNS: list[dict] = [
    # ── 1. Text Classification Pipeline ────────────────────────────────────────
    {
        "normalized_code": """\
import { pipeline } from "@xenova/transformers";
import { logger } from "./logger";

async function classify_text(text: string): Promise<Array<{label: string; score: number}>> {
    const classifier = await pipeline(
        "text-classification",
        "Xenova/distilbert-base-uncased-finetuned-sst-2-english"
    );
    const result = await classifier(text, { topk: null });
    return result;
}

const text = "This movie is amazing! I love it.";
const predictions = await classify_text(text);
logger.info(predictions);
// Output: [
//   { label: "POSITIVE", score: 0.99 },
//   { label: "NEGATIVE", score: 0.01 }
// ]
""",
        "function": "pipeline_text_classification",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/text-classification.ts",
    },
    # ── 2. Token Classification Pipeline ───────────────────────────────────────
    {
        "normalized_code": """\
import { pipeline } from "@xenova/transformers";
import { logger } from "./logger";

async function extract_entities(text: string): Promise<Array<{entity: string; word: string; start: number; end: number; score: number}>> {
    const extractor = await pipeline(
        "token-classification",
        "Xenova/bert-base-multilingual-cased-ner"
    );
    const result = await extractor(text, {
        aggregation_strategy: "simple",
    });
    return result;
}

const text = "My name is Sarah and I live in Paris.";
const entities = await extract_entities(text);
logger.info(entities);
// Output: [
//   { entity: "B-PER", word: "Sarah", start: 11, end: 16, score: 0.98 },
//   { entity: "B-LOC", word: "Paris", start: 30, end: 35, score: 0.99 }
// ]
""",
        "function": "pipeline_token_classification",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/token-classification.ts",
    },
    # ── 3. Text Generation Pipeline ────────────────────────────────────────────
    {
        "normalized_code": """\
import { pipeline } from "@xenova/transformers";
import { logger } from "./logger";

async function generate_text(prompt: string, max_length: number = 50): Promise<Array<{generated_text: string}>> {
    const generator = await pipeline(
        "text-generation",
        "Xenova/distilgpt2"
    );
    const result = await generator(prompt, {
        max_new_tokens: max_length,
        temperature: 0.7,
    });
    return result;
}

const prompt = "Once upon a time,";
const output = await generate_text(prompt, 100);
logger.info(output[0].generated_text);
""",
        "function": "pipeline_text_generation",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/text-generation.ts",
    },
    # ── 4. Translation Pipeline ────────────────────────────────────────────────
    {
        "normalized_code": """\
import { pipeline } from "@xenova/transformers";
import { logger } from "./logger";

async function translate_text(text: string, source_lang: string, target_lang: string): Promise<Array<{translation_text: string}>> {
    const translator = await pipeline(
        "translation",
        "Xenova/m2m100_418M",
        { quantized: true }
    );
    const result = await translator(text, {
        src_lang: source_lang,
        tgt_lang: target_lang,
    });
    return result;
}

const result = await translate_text("Bonjour, est-ce que vous allez bien?", "fr", "en");
logger.info(result[0].translation_text);
// Output: "Hello, how are you?"
""",
        "function": "pipeline_translation",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/translation.ts",
    },
    # ── 5. Summarization Pipeline ──────────────────────────────────────────────
    {
        "normalized_code": """\
import { pipeline } from "@xenova/transformers";
import { logger } from "./logger";

async function summarize_text(text: string, max_length: number = 100): Promise<Array<{summary_text: string}>> {
    const summarizer = await pipeline(
        "summarization",
        "Xenova/distilbart-cnn-6-6",
        { quantized: true }
    );
    const result = await summarizer(text, {
        max_length,
        min_length: 30,
    });
    return result;
}

const passage = "The quick brown fox jumps over the lazy dog. " +
                "This sentence contains every letter of the English alphabet. " +
                "It is often used for testing typewriters and computer keyboards.";
const summary = await summarize_text(passage);
logger.info(summary[0].summary_text);
""",
        "function": "pipeline_summarization",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/summarization.ts",
    },
    # ── 6. Feature Extraction Pipeline ─────────────────────────────────────────
    {
        "normalized_code": """\
import { pipeline } from "@xenova/transformers";
import { Tensor } from "@xenova/transformers";
import { logger } from "./logger";

async function extract_features(text: string): Promise<{data: number[]; dims: number[]}> {
    const extractor = await pipeline(
        "feature-extraction",
        "Xenova/all-MiniLM-L6-v2"
    );
    const embeddings = await extractor(text, {
        pooling: "mean",
        normalize: true,
    });
    return embeddings;
}

const text1 = "The quick brown fox jumps.";
const text2 = "A fast brownish fox leaps.";
const features1 = await extract_features(text1);
const features2 = await extract_features(text2);

function cosine_similarity(a: number[], b: number[]): number {
    const dotproduct = a.reduce((sum, val, i) => sum + val * b[i], 0);
    return dotproduct;
}

const similarity = cosine_similarity(features1.data, features2.data);
logger.info(`Similarity: ${similarity}`);
""",
        "function": "pipeline_feature_extraction",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/feature-extraction.ts",
    },
    # ── 7. Image Classification Pipeline ───────────────────────────────────────
    {
        "normalized_code": """\
import { pipeline } from "@xenova/transformers";
import * as fs from "fs";
import { logger } from "./logger";

async function classify_image(image_path: string): Promise<Array<{label: string; score: number}>> {
    const classifier = await pipeline(
        "image-classification",
        "Xenova/vit-base-patch16-224"
    );

    const image = fs.readFileSync(image_path);
    const base64_image = image.toString("base64");
    const data_url = `data:image/jpeg;base64,${base64_image}`;

    const result = await classifier(data_url);
    return result;
}

const predictions = await classify_image("./path/to/image.jpg");
predictions.forEach((p) => {
    logger.info(`${p.label}: ${(p.score * 100).toFixed(2)}%`);
});
""",
        "function": "pipeline_image_classification",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/image-classification.ts",
    },
    # ── 8. Object Detection Pipeline ───────────────────────────────────────────
    {
        "normalized_code": """\
import { pipeline } from "@xenova/transformers";
import * as fs from "fs";
import { logger } from "./logger";

async function detect_objects(image_path: string): Promise<Array<{label: string; box: {xmin: number; ymin: number; xmax: number; ymax: number}; score: number}>> {
    const detector = await pipeline(
        "object-detection",
        "Xenova/detr-resnet-50"
    );

    const image = fs.readFileSync(image_path);
    const base64_image = image.toString("base64");
    const data_url = `data:image/jpeg;base64,${base64_image}`;

    const result = await detector(data_url, {
        threshold: 0.5,
    });
    return result;
}

const detections = await detect_objects("./path/to/image.jpg");
detections.forEach((d) => {
    logger.info(`Detected ${d.label} at [${d.box.xmin}, ${d.box.ymin}] with score ${d.score}`);
});
""",
        "function": "pipeline_object_detection",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/object-detection.ts",
    },
    # ── 9. Automatic Speech Recognition Pipeline ───────────────────────────────
    {
        "normalized_code": """\
import { pipeline } from "@xenova/transformers";
import * as fs from "fs";
import { logger } from "./logger";

async function transcribe_audio(audio_path: string): Promise<{text: string}> {
    const transcriber = await pipeline(
        "automatic-speech-recognition",
        "Xenova/whisper-tiny.en",
        { quantized: false }
    );

    const audio = fs.readFileSync(audio_path);
    const base64_audio = audio.toString("base64");
    const data_url = `data:audio/wav;base64,${base64_audio}`;

    const result = await transcriber(data_url);
    return result;
}

const transcript = await transcribe_audio("./path/to/audio.wav");
logger.info(`Transcribed: ${transcript.text}`);
""",
        "function": "pipeline_automatic_speech_recognition",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/automatic-speech-recognition.ts",
    },
    # ── 10. Custom Model Loading ───────────────────────────────────────────────
    {
        "normalized_code": """\
import { AutoTokenizer, AutoModelForSeq2SeqLM } from "@xenova/transformers";
import { logger } from "./logger";

interface ModelConfig {
    tokenizer: AutoTokenizer;
    model: AutoModelForSeq2SeqLM;
}

async function load_custom_model(model_id: string): Promise<ModelConfig> {
    const tokenizer = await AutoTokenizer.from_pretrained(model_id);
    const model = await AutoModelForSeq2SeqLM.from_pretrained(model_id, {
        dtype: "q8",
    });

    return { tokenizer, model };
}

async function run_inference(model_id: string, input_text: string): Promise<string> {
    const { tokenizer, model } = await load_custom_model(model_id);

    const inputs = await tokenizer(input_text);
    const output_ids = await model.generate(inputs.input_ids, {
        max_length: 100,
    });

    const decoded = tokenizer.batch_decode(output_ids, { skip_special_tokens: true });
    return decoded[0];
}

const result = await run_inference(
    "Xenova/t5-small",
    "translate English to French: Hello, how are you?"
);
logger.info(result);
""",
        "function": "custom_model_loading",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/model_loader.ts",
    },
    # ── 11. Quantized Model Loading ────────────────────────────────────────────
    {
        "normalized_code": """\
import { AutoModelForCausalLM, AutoTokenizer } from "@xenova/transformers";
import { logger } from "./logger";

interface QuantizationConfig {
    quantized: boolean;
    dtype: string;
    device: string;
}

interface ModelResult {
    tokenizer: AutoTokenizer;
    model: AutoModelForCausalLM;
}

async function load_quantized_model(model_id: string): Promise<ModelResult> {
    const options: QuantizationConfig = {
        quantized: true,
        dtype: "q8",
        device: "webgpu",
    };

    const tokenizer = await AutoTokenizer.from_pretrained(model_id);
    const model = await AutoModelForCausalLM.from_pretrained(model_id, options);

    logger.info(`Model loaded: ${model.model_id}, quantized: ${options.quantized}`);
    return { tokenizer, model };
}

async function inference_with_quantization(text: string): Promise<string> {
    const { tokenizer, model } = await load_quantized_model("Xenova/distilgpt2");

    const inputs = await tokenizer(text);
    const output = await model.generate(inputs.input_ids, {
        max_new_tokens: 50,
        temperature: 0.8,
    });

    const decoded = tokenizer.batch_decode(output);
    return decoded[0];
}

const output = await inference_with_quantization("Once upon");
logger.info(output);
""",
        "function": "quantized_model_loading",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/quantization.ts",
    },
    # ── 12. Zero-Shot Classification Pipeline ──────────────────────────────────
    {
        "normalized_code": """\
import { pipeline } from "@xenova/transformers";
import { logger } from "./logger";

async function zero_shot_classification(
    text: string,
    candidate_labels: string[]
): Promise<Array<{sequence: string; labels: string[]; scores: number[]}>> {
    const classifier = await pipeline(
        "zero-shot-classification",
        "Xenova/mobilebert-uncased-mnli"
    );

    const result = await classifier(text, candidate_labels, {
        multi_class: false,
    });

    return result;
}

const text = "I have a problem with my laptop that needs to be resolved.";
const labels = ["urgent", "bug", "feature_request", "support"];

const predictions = await zero_shot_classification(text, labels);
logger.info(predictions);
// Output: [
//   { sequence: text, labels: ["support", "bug", "urgent", "feature_request"],
//     scores: [0.75, 0.15, 0.07, 0.03] }
// ]
""",
        "function": "pipeline_zero_shot_classification",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/zero-shot-classification.ts",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "text classification pipeline sentiment analysis",
    "token classification named entity extraction",
    "text generation language model inference",
    "translation between languages",
    "text summarization abstractive",
    "feature extraction embeddings similarity",
    "image classification vision transformer",
    "object detection bounding boxes",
    "speech recognition transcription audio",
    "custom model loading from pretrained",
    "quantized model optimization memory",
    "zero shot classification without training",
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
