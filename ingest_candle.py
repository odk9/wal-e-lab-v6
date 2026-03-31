"""
ingest_candle.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de huggingface/candle dans la KB Qdrant V6.

Focus : CORE patterns Rust tensor/ML — tensor creation, operations, layers,
model loading, quantization, inference, device management, custom modules,
attention mechanisms, tokenizer integration.

Usage:
    .venv/bin/python3 ingest_candle.py
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
REPO_URL = "https://github.com/huggingface/candle.git"
REPO_NAME = "huggingface/candle"
REPO_LOCAL = "/tmp/candle"
LANGUAGE = "rust"
FRAMEWORK = "generic"
STACK = "rust+candle+ml+tensor"
CHARTE_VERSION = "1.0"
TAG = "huggingface/candle"
SOURCE_REPO = "https://github.com/huggingface/candle"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Candle = ML tensor library for Rust.
# Patterns CORE : tensor creation, operations, layers, loading, quantization, inference.
# U-5 : `tensor`, `model`, `layer`, `weight`, `quantize`, `inference`, `context`,
#       `token`, `embedding` are technical terms — KEEP. Replace `data`, `result`, etc.

PATTERNS: list[dict] = [
    # ── 1. Tensor Creation and Initialization ────────────────────────────────
    {
        "normalized_code": """\
use candle::{Device, Result, Tensor};

pub fn create_tensor_from_vec(
    data: Vec<f32>,
    shape: &[usize],
    device: &Device,
) -> Result<Tensor> {
    let tensor = Tensor::new_strided(
        data,
        0,
        shape.to_vec(),
        vec![1; shape.len()],
    )?;
    tensor.to_device(device)
}

pub fn create_tensor_randn(
    shape: &[usize],
    dtype: DType,
    device: &Device,
) -> Result<Tensor> {
    let length: usize = shape.iter().fold(1, |a, b| a * b);
    let data: Vec<f32> = (0..length)
        .map(|_| fastrand::f32())
        .collect();
    let tensor = Tensor::new_strided(
        data,
        0,
        shape.to_vec(),
        vec![1; shape.len()],
    )?;
    tensor.to(dtype)?.to_device(device)
}
""",
        "function": "tensor_creation_initialization",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "candle-core/src/tensor/creation.rs",
    },
    # ── 2. Tensor Operations (Element-wise, Reduction) ─────────────────────────
    {
        "normalized_code": """\
use candle::{Tensor, Result};

impl Tensor {
    pub fn add(&self, other: &Tensor) -> Result<Tensor> {
        let left = self.broadcast_as(other.shape())?;
        let right = other.broadcast_as(self.shape())?;
        self.device().binary_op(&left, &right, BinaryOp::Add)
    }

    pub fn mul(&self, scalar: f32) -> Result<Tensor> {
        self.affine(scalar, 0.0)
    }

    pub fn softmax(&self, dim: usize) -> Result<Tensor> {
        let max = self.max_keepdim(dim)?;
        let exp = (self - max)?.exp()?;
        let sum = exp.sum_keepdim(dim)?;
        exp / sum
    }

    pub fn transpose(&self, dim1: usize, dim2: usize) -> Result<Tensor> {
        self.transpose_2d(dim1, dim2)
    }

    pub fn reshape(&self, shape: &[usize]) -> Result<Tensor> {
        self.reshape(shape)
    }
}
""",
        "function": "tensor_operations_element_reduction",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "candle-core/src/tensor/ops.rs",
    },
    # ── 3. Linear Layer Implementation ───────────────────────────────────────
    {
        "normalized_code": """\
use candle::{Tensor, Result, Device};
use candle::nn::{Init, VarBuilder};

pub struct Linear {
    weight: Tensor,
    bias: Option<Tensor>,
}

impl Linear {
    pub fn new(
        in_size: usize,
        out_size: usize,
        vb: VarBuilder,
    ) -> Result<Linear> {
        let weight = vb.get_with_hints(
            (out_size, in_size),
            "weight",
            Init::Randn {
                mean: 0.0,
                stdev: (2.0 / (in_size + out_size) as f64).sqrt() as f32,
            },
        )?;
        let bias = vb
            .get_with_hints((out_size,), "bias", Init::Zeros)
            .ok();
        Ok(Linear { weight, bias })
    }

    pub fn forward(&self, input: &Tensor) -> Result<Tensor> {
        let xxx = input.matmul(&self.weight.t()?)?;
        match &self.bias {
            None => Ok(xxx),
            Some(bias) => xxx.broadcast_add(bias),
        }
    }
}
""",
        "function": "linear_layer_forward_pass",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "candle-nn/src/linear.rs",
    },
    # ── 4. Embedding Layer ────────────────────────────────────────────────────
    {
        "normalized_code": """\
use candle::{Tensor, Result, Device};
use candle::nn::VarBuilder;

pub struct Embedding {
    embedding: Tensor,
    padding_idx: Option<usize>,
}

impl Embedding {
    pub fn new(
        num_embeddings: usize,
        embedding_dim: usize,
        vb: VarBuilder,
    ) -> Result<Embedding> {
        let embedding = vb.get_with_hints(
            (num_embeddings, embedding_dim),
            "weight",
            candle::nn::Init::Randn {
                mean: 0.0,
                stdev: 1.0,
            },
        )?;
        Ok(Embedding {
            embedding,
            padding_idx: None,
        })
    }

    pub fn forward(&self, input: &Tensor) -> Result<Tensor> {
        self.embedding.index_select(input, 0)
    }

    pub fn set_padding_idx(&mut self, padding_idx: Option<usize>) {
        self.padding_idx = padding_idx;
    }
}
""",
        "function": "embedding_layer_token_lookup",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "candle-nn/src/embedding.rs",
    },
    # ── 5. Model Forward Pass (Composition) ──────────────────────────────────
    {
        "normalized_code": """\
use candle::{Tensor, Result};
use candle::nn::VarBuilder;

pub struct Xxx {
    embedding: Embedding,
    encoder: TransformerEncoder,
    decoder: Linear,
}

impl Xxx {
    pub fn new(vb: VarBuilder, config: &XxxConfig) -> Result<Xxx> {
        Ok(Xxx {
            embedding: Embedding::new(
                config.vocab_size,
                config.hidden_size,
                vb.pp("embedding"),
            )?,
            encoder: TransformerEncoder::new(
                vb.pp("encoder"),
                config,
            )?,
            decoder: Linear::new(
                config.hidden_size,
                config.vocab_size,
                vb.pp("decoder"),
            )?,
        })
    }

    pub fn forward(&self, input_ids: &Tensor) -> Result<Tensor> {
        let embeddings = self.embedding.forward(input_ids)?;
        let encoder_output = self.encoder.forward(&embeddings)?;
        let logits = self.decoder.forward(&encoder_output)?;
        Ok(logits)
    }
}
""",
        "function": "model_forward_pass_composition",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "candle-transformers/src/models/xxx.rs",
    },
    # ── 6. Load SafeTensors Weights ──────────────────────────────────────────
    {
        "normalized_code": """\
use candle::{Tensor, Result, Device};
use candle::safetensors::load;
use std::path::Path;

pub fn load_safetensors_weights<P: AsRef<Path>>(
    path: P,
    device: &Device,
) -> Result<std::collections::HashMap<String, Tensor>> {
    let safetensors = load(path.as_ref(), device)?;
    Ok(safetensors)
}

pub fn load_model_weights<P: AsRef<Path>>(
    path: P,
    device: &Device,
) -> Result<()> {
    let weights = load_safetensors_weights(path, device)?;

    for (key, tensor) in weights.iter() {
        tracing::info!("Loaded weight: {} shape={:?}", key, tensor.shape());
    }
    Ok(())
}

pub fn save_model_weights<P: AsRef<Path>>(
    weights: &std::collections::HashMap<String, Tensor>,
    path: P,
) -> Result<()> {
    use candle::safetensors::save;
    save(&weights, path.as_ref())?;
    Ok(())
}
""",
        "function": "safetensors_weights_loading_saving",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "candle-core/src/safetensors.rs",
    },
    # ── 7. Quantized Model Loading ───────────────────────────────────────────
    {
        "normalized_code": """\
use candle::{Tensor, Result, Device};
use std::path::Path;

pub enum QuantizationScheme {
    QInt8,
    QInt4,
    QUInt8,
    QUInt4,
}

pub struct QuantizedModel {
    weights: std::collections::HashMap<String, Tensor>,
    scheme: QuantizationScheme,
}

impl QuantizedModel {
    pub fn load<P: AsRef<Path>>(
        path: P,
        scheme: QuantizationScheme,
        device: &Device,
    ) -> Result<QuantizedModel> {
        let weights = load_safetensors_weights(path, device)?;
        Ok(QuantizedModel { weights, scheme })
    }

    pub fn dequantize_weight(&self, name: &str) -> Result<Tensor> {
        let weight = &self.weights[name];
        match self.scheme {
            QuantizationScheme::QInt8 => weight.to(candle::DType::F32),
            QuantizationScheme::QInt4 => self.dequantize_int4(weight),
            _ => weight.clone(),
        }
    }

    fn dequantize_int4(&self, quantized: &Tensor) -> Result<Tensor> {
        let shape = quantized.shape();
        let data = quantized.to_vec1::<u8>()?;
        let unpacked: Vec<f32> = data
            .iter()
            .flat_map(|&b| vec![(b & 0x0F) as f32, (b >> 4) as f32])
            .collect();
        Tensor::new_strided(unpacked, 0, &shape, vec![1; shape.len().len()])
    }
}
""",
        "function": "quantized_model_loading_dequantization",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "candle-transformers/src/quantize.rs",
    },
    # ── 8. Device and CUDA Selection ────────────────────────────────────────
    {
        "normalized_code": """\
use candle::Device;

pub fn get_device(use_cuda: bool) -> candle::Result<Device> {
    if use_cuda {
        #[cfg(feature = "cuda")]
        {
            Device::new_cuda(0)
        }
        #[cfg(not(feature = "cuda"))]
        {
            tracing::warn!("CUDA not available, using CPU");
            Ok(Device::Cpu)
        }
    } else {
        Ok(Device::Cpu)
    }
}

pub fn get_device_by_id(device_id: Option<usize>) -> candle::Result<Device> {
    match device_id {
        Some(id) => {
            #[cfg(feature = "cuda")]
            {
                Device::new_cuda(id as u32)
            }
            #[cfg(not(feature = "cuda"))]
            {
                Err(candle::Error::Cuda("CUDA not compiled".into()))
            }
        }
        None => Ok(Device::Cpu),
    }
}

pub fn device_memory_status(device: &Device) -> candle::Result<String> {
    match device {
        Device::Cpu => Ok("CPU mode — no GPU memory tracking".to_string()),
        #[cfg(feature = "cuda")]
        Device::Cuda(cuda_device) => {
            Ok(format!("CUDA device {}", cuda_device.device_id()))
        }
        _ => Ok("Unknown device".to_string()),
    }
}
""",
        "function": "device_cuda_selection_memory",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "candle-core/src/device.rs",
    },
    # ── 9. Custom Module Implementation ──────────────────────────────────────
    {
        "normalized_code": """\
use candle::{Tensor, Result};
use candle::nn::VarBuilder;

pub trait Module: Send + Sync {
    fn forward(&self, input: &Tensor) -> Result<Tensor>;
}

pub struct CustomXxxModule {
    param1: Tensor,
    param2: Tensor,
}

impl CustomXxxModule {
    pub fn new(vb: VarBuilder, size: usize) -> Result<CustomXxxModule> {
        let param1 = vb.get_with_hints(
            (size, size),
            "param1",
            candle::nn::Init::Randn {
                mean: 0.0,
                stdev: 0.1,
            },
        )?;
        let param2 = vb.get_with_hints(
            (size,),
            "param2",
            candle::nn::Init::Zeros,
        )?;
        Ok(CustomXxxModule { param1, param2 })
    }
}

impl Module for CustomXxxModule {
    fn forward(&self, input: &Tensor) -> Result<Tensor> {
        let xxx = input.matmul(&self.param1)?;
        xxx.broadcast_add(&self.param2)
    }
}
""",
        "function": "custom_module_trait_implementation",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "candle-nn/src/module.rs",
    },
    # ── 10. Attention Mechanism (Self-Attention) ────────────────────────────
    {
        "normalized_code": """\
use candle::{Tensor, Result};
use candle::nn::VarBuilder;

pub struct Attention {
    query: Linear,
    key: Linear,
    value: Linear,
    output: Linear,
    num_heads: usize,
    head_dim: usize,
}

impl Attention {
    pub fn new(vb: VarBuilder, hidden_size: usize, num_heads: usize) -> Result<Attention> {
        let head_dim = hidden_size / num_heads;
        Ok(Attention {
            query: Linear::new(hidden_size, hidden_size, vb.pp("query"))?,
            key: Linear::new(hidden_size, hidden_size, vb.pp("key"))?,
            value: Linear::new(hidden_size, hidden_size, vb.pp("value"))?,
            output: Linear::new(hidden_size, hidden_size, vb.pp("output"))?,
            num_heads,
            head_dim,
        })
    }

    pub fn forward(&self, input: &Tensor, mask: Option<&Tensor>) -> Result<Tensor> {
        let query = self.query.forward(input)?;
        let key = self.key.forward(input)?;
        let value = self.value.forward(input)?;

        let scores = query.matmul(&key.t()?)? / (self.head_dim as f32).sqrt();
        let attention = if let Some(mask_tensor) = mask {
            (scores + mask_tensor)?.softmax(2)?
        } else {
            scores.softmax(2)?
        };

        let context = attention.matmul(&value)?;
        self.output.forward(&context)
    }
}
""",
        "function": "attention_mechanism_self_attention",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "candle-nn/src/attention.rs",
    },
    # ── 11. Tokenizer Integration ────────────────────────────────────────────
    {
        "normalized_code": """\
use candle::{Tensor, Result, Device};
use tokenizers::Tokenizer;

pub struct TokenizerPipeline {
    tokenizer: Tokenizer,
    device: Device,
}

impl TokenizerPipeline {
    pub fn new(tokenizer_path: &str, device: Device) -> Result<TokenizerPipeline> {
        let tokenizer = Tokenizer::from_file(tokenizer_path)
            .map_err(|e| candle::Error::Msg(e.to_string()))?;
        Ok(TokenizerPipeline { tokenizer, device })
    }

    pub fn encode_batch(&self, texts: &[&str]) -> Result<Vec<Vec<u32>>> {
        let encodings = self.tokenizer
            .encode_batch(texts, true)
            .map_err(|e| candle::Error::Msg(e.to_string()))?;

        let ids: Vec<Vec<u32>> = encodings
            .iter()
            .map(|enc| enc.get_ids().to_vec())
            .collect();
        Ok(ids)
    }

    pub fn encode_to_tensor(&self, text: &str) -> Result<Tensor> {
        let encoding = self.tokenizer
            .encode(text, true)
            .map_err(|e| candle::Error::Msg(e.to_string()))?;
        let ids = encoding.get_ids();
        Tensor::new_strided(
            ids.iter().map(|&id| id as f32).collect(),
            0,
            &[ids.len()],
            vec![1],
        )?.to_device(&self.device)
    }
}
""",
        "function": "tokenizer_integration_batch_encoding",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "candle-transformers/src/tokenizer.rs",
    },
    # ── 12. Inference Loop and Generation ───────────────────────────────────
    {
        "normalized_code": """\
use candle::{Tensor, Result};

pub struct InferenceConfig {
    pub max_tokens: usize,
    pub temperature: f32,
    pub top_k: usize,
    pub top_p: f32,
}

pub struct InferenceLoop {
    model: Box<dyn Model>,
    config: InferenceConfig,
}

impl InferenceLoop {
    pub fn new(model: Box<dyn Model>, config: InferenceConfig) -> InferenceLoop {
        InferenceLoop { model, config }
    }

    pub fn generate(&self, input_ids: &Tensor) -> Result<Vec<u32>> {
        let mut xxx = input_ids.to_vec1::<u32>()?.to_vec();
        let mut current = input_ids.clone();

        for _ in 0..self.config.max_tokens {
            let logits = self.model.forward(&current)?;
            let next_token = self.sample_next_token(&logits)?;

            if next_token == 2 {
                break;
            }
            xxx.push(next_token);
            current = Tensor::new_strided(
                vec![next_token as f32],
                0,
                &[1],
                vec![1],
            )?;
        }
        Ok(xxx)
    }

    fn sample_next_token(&self, logits: &Tensor) -> Result<u32> {
        let softmax = logits.softmax(logits.rank() - 1)?;
        let token_id = softmax.argmax(logits.rank() - 1)?;
        Ok(token_id.to_scalar::<u32>()?)
    }
}
""",
        "function": "inference_loop_token_generation",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "candle-transformers/src/inference.rs",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "Rust tensor creation initialization from vectors",
    "tensor operations element-wise softmax transpose",
    "linear layer weight bias forward pass",
    "embedding layer token lookup indexing",
    "model forward pass composition layers",
    "safetensors weights load save serialize",
    "quantized model loading dequantization int4",
    "device CUDA GPU selection memory",
    "custom module trait forward implementation",
    "attention mechanism self-attention heads",
    "tokenizer batch encoding token ids",
    "inference loop token generation sampling",
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
