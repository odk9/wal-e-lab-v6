"""
ingest_burn.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
d'une library de ML Rust dans la KB Qdrant V6.

Focus : CORE patterns machine learning Rust — tensor creation, model definition,
forward pass, training loop, dataset loading, optimizer setup, loss functions,
backend selection, inference, module composition.

Usage:
    .venv/bin/python3 ingest_burn.py
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
REPO_URL = "https://github.com/tracel-ai/burn.git"
REPO_NAME = "tracel-ai/burn"
REPO_LOCAL = "/tmp/burn"
LANGUAGE = "rust"
FRAMEWORK = "generic"
STACK = "rust+burn+ml+deep-learning"
CHARTE_VERSION = "1.0"
TAG = "tracel-ai/burn"
SOURCE_REPO = "https://github.com/tracel-ai/burn"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Burn = ML framework Rust. Patterns CORE : tensor creation, model definition,
# training loop, dataset, optimizer, loss, inference.
# U-5 : `module`, `model`, `layer`, `tensor`, `backend`, `optimizer`, `dataset` OK (ML terms).
#       Remplacer entity-specific : `xxx_model` generic.

PATTERNS: list[dict] = [
    # ── 1. Tensor Creation ────────────────────────────────────────────────────
    {
        "normalized_code": """\
use burn::tensor::{Tensor, Device};

pub fn create_tensor<B: Backend>(shape: &[usize]) -> Tensor<B, 2> {
    let device = B::Device::default();
    Tensor::<B, 2>::zeros(shape, &device)
}

pub fn create_tensor_from_data<B: Backend>(
    data: Vec<f32>,
    shape: [usize; 2],
) -> Tensor<B, 2> {
    let device = B::Device::default();
    let data = burn::tensor::Data::new(data, shape.into());
    Tensor::from_data(data, &device)
}

pub fn create_random_tensor<B: Backend>(shape: [usize; 2]) -> Tensor<B, 2> {
    let device = B::Device::default();
    Tensor::random(shape, burn::tensor::Distribution::Normal(0.0, 1.0), &device)
}
""",
        "function": "tensor_creation",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/tensor.rs",
    },
    # ── 2. Linear Module Definition ───────────────────────────────────────────
    {
        "normalized_code": """\
use burn::module::{Module, Param};
use burn::tensor::Tensor;
use burn::nn::Linear;

#[derive(Module)]
pub struct LinearLayer<B: Backend> {
    linear: Linear<B>,
}

impl<B: Backend> LinearLayer<B> {
    pub fn new(in_features: usize, out_features: usize, device: &B::Device) -> Self {
        Self {
            linear: Linear::new(&Default::default(), in_features, out_features, device),
        }
    }

    pub fn forward(&self, input: Tensor<B, 2>) -> Tensor<B, 2> {
        self.linear.forward(input)
    }
}
""",
        "function": "linear_module",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "examples/linear.rs",
    },
    # ── 3. Model Definition ───────────────────────────────────────────────────
    {
        "normalized_code": """\
use burn::module::Module;
use burn::nn::{Linear, ReLU, Dropout, DropoutConfig};
use burn::tensor::Tensor;

#[derive(Module)]
pub struct NeuralNetwork<B: Backend> {
    linear1: Linear<B>,
    relu: ReLU,
    dropout: Dropout,
    linear2: Linear<B>,
}

impl<B: Backend> NeuralNetwork<B> {
    pub fn new(device: &B::Device) -> Self {
        let config = LinearConfig::new(784, 256);
        Self {
            linear1: config.init(device),
            relu: ReLU::new(),
            dropout: DropoutConfig::new(0.2).init(),
            linear2: LinearConfig::new(256, 10).init(device),
        }
    }

    pub fn forward(&self, input: Tensor<B, 2>) -> Tensor<B, 2> {
        let out = self.linear1.forward(input);
        let out = self.relu.forward(out);
        let out = self.dropout.forward(out);
        self.linear2.forward(out)
    }
}
""",
        "function": "model_definition",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "examples/model.rs",
    },
    # ── 4. Forward Pass ───────────────────────────────────────────────────────
    {
        "normalized_code": """\
use burn::tensor::Tensor;

pub fn forward_pass<B: Backend>(
    model: &NeuralNetwork<B>,
    batch: Tensor<B, 2>,
) -> Tensor<B, 2> {
    model.forward(batch)
}

pub fn forward_with_training<B: Backend>(
    model: &NeuralNetwork<B>,
    batch: Tensor<B, 2>,
    training: bool,
) -> Tensor<B, 2> {
    let intermediate = model.linear1.forward(batch);
    let intermediate = model.relu.forward(intermediate);

    let intermediate = if training {
        model.dropout.forward(intermediate)
    } else {
        intermediate
    };

    model.linear2.forward(intermediate)
}
""",
        "function": "forward_pass",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/forward.rs",
    },
    # ── 5. Training Configuration ─────────────────────────────────────────────
    {
        "normalized_code": """\
use burn::train::TrainingConfig;
use burn::optim::AdamConfig;

pub struct TrainConfig {
    pub learning_rate: f64,
    pub batch_size: usize,
    pub num_epochs: usize,
    pub checkpoint_freq: usize,
}

impl Default for TrainConfig {
    fn default() -> Self {
        Self {
            learning_rate: 0.001,
            batch_size: 32,
            num_epochs: 10,
            checkpoint_freq: 1,
        }
    }
}

pub fn create_training_config() -> TrainingConfig {
    TrainingConfig::new(
        AdamConfig::new(),
        0.001,
    )
}
""",
        "function": "training_config",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/config.rs",
    },
    # ── 6. Dataset Loader ─────────────────────────────────────────────────────
    {
        "normalized_code": """\
use burn::data::dataset::Dataset;
use std::path::Path;

pub struct DatasetLoader;

impl DatasetLoader {
    pub fn load_csv<P: AsRef<Path>>(path: P) -> Result<Vec<Vec<f32>>, String> {
        let content = std::fs::read_to_string(path)
            .map_err(|e| format!("Failed to read file: {}", e))?;

        let data: Vec<Vec<f32>> = content
            .lines()
            .skip(1)
            .filter_map(|line| {
                let values: Result<Vec<f32>, _> = line
                    .split(',')
                    .map(|s| s.trim().parse::<f32>())
                    .collect();
                values.ok()
            })
            .collect();

        Ok(data)
    }

    pub fn batch_data(data: Vec<Vec<f32>>, batch_size: usize) -> Vec<Vec<Vec<f32>>> {
        data.chunks(batch_size)
            .map(|chunk| chunk.to_vec())
            .collect()
    }
}
""",
        "function": "dataset_loader",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/dataset.rs",
    },
    # ── 7. Optimizer (Adam) ───────────────────────────────────────────────────
    {
        "normalized_code": """\
use burn::optim::{AdamConfig, Optimizer};
use burn::tensor::Tensor;

pub struct OptimizerSetup {
    pub learning_rate: f64,
    pub beta1: f64,
    pub beta2: f64,
    pub epsilon: f64,
}

impl Default for OptimizerSetup {
    fn default() -> Self {
        Self {
            learning_rate: 0.001,
            beta1: 0.9,
            beta2: 0.999,
            epsilon: 1e-8,
        }
    }
}

pub fn create_adam_optimizer<B: Backend>(
    setup: OptimizerSetup,
) -> AdamConfig {
    AdamConfig::new()
        .with_epsilon(setup.epsilon)
        .with_beta_1(setup.beta1)
        .with_beta_2(setup.beta2)
}
""",
        "function": "optimizer_adam",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/optimizer.rs",
    },
    # ── 8. Loss Function ──────────────────────────────────────────────────────
    {
        "normalized_code": """\
use burn::nn::loss::{CrossEntropyLoss, MseLoss};
use burn::tensor::Tensor;

pub fn cross_entropy_loss<B: Backend>(
    predictions: Tensor<B, 2>,
    targets: Tensor<B, 1>,
) -> Tensor<B, 1> {
    let loss_fn = CrossEntropyLoss::new();
    loss_fn.forward(predictions, targets)
}

pub fn mse_loss<B: Backend>(
    predictions: Tensor<B, 2>,
    targets: Tensor<B, 2>,
) -> Tensor<B, 1> {
    let loss_fn = MseLoss::new();
    loss_fn.forward(predictions, targets)
}

pub fn custom_loss<B: Backend>(
    predictions: Tensor<B, 2>,
    targets: Tensor<B, 2>,
) -> Tensor<B, 1> {
    let diff = predictions - targets;
    (diff * diff).mean()
}
""",
        "function": "loss_function",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/loss.rs",
    },
    # ── 9. Backend Selection ──────────────────────────────────────────────────
    {
        "normalized_code": """\
pub trait Backend: Send {
    type Device: std::fmt::Debug;

    fn device() -> Self::Device;
}

pub struct CpuBackend;

impl Backend for CpuBackend {
    type Device = ();

    fn device() -> Self::Device {
        ()
    }
}

pub struct GpuBackend;

impl Backend for GpuBackend {
    type Device = ();

    fn device() -> Self::Device {
        ()
    }
}

pub fn select_backend(use_gpu: bool) {
    if use_gpu {
        tracing::info!("Using GPU backend");
    } else {
        tracing::info!("Using CPU backend");
    }
}
""",
        "function": "backend_selection",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/backend.rs",
    },
    # ── 10. Model Save/Load ───────────────────────────────────────────────────
    {
        "normalized_code": """\
use burn::module::Module;
use std::path::Path;

pub trait ModelIO {
    fn save<P: AsRef<Path>>(&self, path: P) -> Result<(), String>;
    fn load<P: AsRef<Path>>(path: P) -> Result<Self, String> where Self: Sized;
}

pub fn save_model<B: Backend, P: AsRef<Path>>(
    model: &NeuralNetwork<B>,
    path: P,
) -> Result<(), String> {
    let serialized = serde_json::to_string(&model)
        .map_err(|e| format!("Serialization error: {}", e))?;

    std::fs::write(path, serialized)
        .map_err(|e| format!("Write error: {}", e))
}

pub fn load_model<B: Backend, P: AsRef<Path>>(
    path: P,
) -> Result<NeuralNetwork<B>, String> {
    let data = std::fs::read_to_string(path)
        .map_err(|e| format!("Read error: {}", e))?;

    serde_json::from_str(&data)
        .map_err(|e| format!("Deserialization error: {}", e))
}
""",
        "function": "model_save_load",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/model_io.rs",
    },
    # ── 11. Custom Module ─────────────────────────────────────────────────────
    {
        "normalized_code": """\
use burn::module::Module;
use burn::tensor::Tensor;

#[derive(Module)]
pub struct CustomModule<B: Backend> {
    layer1: Linear<B>,
    layer2: Linear<B>,
    activation: Relu,
}

impl<B: Backend> CustomModule<B> {
    pub fn new(in_features: usize, hidden: usize, out_features: usize, device: &B::Device) -> Self {
        Self {
            layer1: LinearConfig::new(in_features, hidden).init(device),
            layer2: LinearConfig::new(hidden, out_features).init(device),
            activation: Relu::new(),
        }
    }

    pub fn forward(&self, input: Tensor<B, 2>) -> Tensor<B, 2> {
        let hidden = self.activation.forward(self.layer1.forward(input));
        self.layer2.forward(hidden)
    }
}
""",
        "function": "custom_module",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "examples/custom_module.rs",
    },
    # ── 12. Inference (No Grad) ───────────────────────────────────────────────
    {
        "normalized_code": """\
use burn::tensor::Tensor;

pub fn inference<B: Backend>(
    model: &NeuralNetwork<B>,
    input: Tensor<B, 2>,
) -> Tensor<B, 2> {
    B::no_grad(|| {
        model.forward(input)
    })
}

pub fn batch_inference<B: Backend>(
    model: &NeuralNetwork<B>,
    batches: Vec<Tensor<B, 2>>,
) -> Vec<Tensor<B, 2>> {
    B::no_grad(|| {
        batches
            .iter()
            .map(|batch| model.forward(batch.clone()))
            .collect()
    })
}

pub fn predict_class<B: Backend>(
    model: &NeuralNetwork<B>,
    input: Tensor<B, 2>,
) -> usize {
    B::no_grad(|| {
        let logits = model.forward(input);
        logits.argmax(1).into_scalar() as usize
    })
}
""",
        "function": "inference_no_grad",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "examples/inference.rs",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "create tensor Rust Burn",
    "linear module neural network",
    "model definition architecture setup",
    "forward pass computation",
    "training configuration Adam optimizer",
    "dataset loader batch data",
    "Adam optimizer setup learning rate",
    "loss function cross entropy MSE",
    "backend selection CPU GPU",
    "model serialization save load",
    "custom module composition",
    "inference no_grad prediction",
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
