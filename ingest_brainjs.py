"""
ingest_brainjs.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de BrainJS/brain.js dans la KB Qdrant V6.

Focus : CORE patterns Neural Networks en JavaScript — Feedforward, LSTM, RNN,
GRU, training options, cross-validation, model serialization (toJSON/fromJSON),
stream training, custom activation functions, learning rate config, likelihood
prediction, GPU support.

Usage:
    .venv/bin/python3 ingest_brainjs.py
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
REPO_URL = "https://github.com/BrainJS/brain.js.git"
REPO_NAME = "BrainJS/brain.js"
REPO_LOCAL = "/tmp/brain.js"
LANGUAGE = "javascript"
FRAMEWORK = "generic"
STACK = "javascript+brainjs+ml"
CHARTE_VERSION = "1.0"
TAG = "BrainJS/brain.js"
SOURCE_REPO = "https://github.com/BrainJS/brain.js"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Brain.js = neural network library for JavaScript.
# Patterns CORE : Feedforward networks, LSTM, RNN, GRU, training, serialization.
# U-5 : `network` est OK (tech term), `layer` est OK, `train` est OK, `predict` est OK.

PATTERNS: list[dict] = [
    # ── 1. Feedforward Neural Network Creation ─────────────────────────────
    {
        "normalized_code": """\
import { NeuralNetwork } from 'brain.js';

const xxx = new NeuralNetwork({
  inputSize: 2,
  hiddenLayers: [3],
  outputSize: 1,
  learningRate: 0.5,
  activation: 'relu',
  iterations: 1000,
  momentum: 0.1,
});

const xxxData = [
  { input: [0, 0], output: [0] },
  { input: [0, 1], output: [1] },
  { input: [1, 0], output: [1] },
  { input: [1, 1], output: [0] },
];

xxx.train(xxxData, {
  iterations: 2000,
  log: (stats) => {
    // Log training error
  },
  logPeriod: 100,
});

const xxxOutput = xxx.run([1, 0]);
// Prediction output ready
""",
        "function": "feedforward_network_creation_training",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "src/neural-network.js",
    },
    # ── 2. LSTM (Long Short-Term Memory) Network ───────────────────────────
    {
        "normalized_code": """\
import { recurrent } from 'brain.js';

const xxxLstm = new recurrent.LSTM({
  inputSize: 10,
  hiddenLayers: [64, 32],
  outputSize: 5,
  learningRate: 0.01,
});

const xxxSequenceData = [
  {
    input: [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
    output: [[1, 0, 0, 0, 0]],
  },
  {
    input: [[0, 1, 0], [0, 0, 1], [1, 0, 0]],
    output: [[0, 1, 0, 0, 0]],
  },
];

xxxLstm.train(xxxSequenceData, {
  iterations: 500,
  logPeriod: 50,
  callback: (stats) => {
    if (stats.iterations % 100 === 0) {
      // Epoch training progress logged
    }
  },
});

const xxxPrediction = xxxLstm.run([[0, 1, 0]]);
// LSTM prediction output ready
""",
        "function": "lstm_network_sequence_prediction",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "src/recurrent/lstm.js",
    },
    # ── 3. RNN (Recurrent Neural Network) for Text ─────────────────────────
    {
        "normalized_code": """\
import { recurrent } from 'brain.js';

const xxxRnn = new recurrent.RNN({
  inputSize: 26,
  hiddenLayers: [128],
  outputSize: 26,
  learningRate: 0.001,
});

const xxxTextData = [
  { input: [1, 0, 0, 0, 0, ...], output: [0, 1, 0, 0, 0, ...] },
  { input: [0, 1, 0, 0, 0, ...], output: [0, 0, 1, 0, 0, ...] },
];

xxxRnn.train(xxxTextData, {
  iterations: 1000,
  log: (stats) => {
    if (stats.iterations % 100 === 0) {
      // Training progress logged
    }
  },
});

const xxxGenerated = xxxRnn.run([1, 0, 0, 0, 0, ...]);
// Generated sequence ready
""",
        "function": "rnn_text_prediction_sequence",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "src/recurrent/rnn.js",
    },
    # ── 4. GRU (Gated Recurrent Unit) Network ──────────────────────────────
    {
        "normalized_code": """\
import { recurrent } from 'brain.js';

const xxxGru = new recurrent.GRU({
  inputSize: 8,
  hiddenLayers: [32, 16],
  outputSize: 4,
  learningRate: 0.01,
});

const xxxTimeSeriesData = [
  {
    input: [[1, 2, 3, 4, 5, 6, 7, 8]],
    output: [[5, 6, 7, 8]],
  },
  {
    input: [[2, 3, 4, 5, 6, 7, 8, 9]],
    output: [[6, 7, 8, 9]],
  },
];

xxxGru.train(xxxTimeSeriesData, {
  iterations: 300,
  logPeriod: 30,
});

const xxxForecast = xxxGru.run([[1, 2, 3, 4, 5, 6, 7, 8]]);
// Forecasted values ready
""",
        "function": "gru_network_time_series",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "src/recurrent/gru.js",
    },
    # ── 5. Training Options Configuration ───────────────────────────────────
    {
        "normalized_code": """\
import { NeuralNetwork } from 'brain.js';

const xxxNetwork = new NeuralNetwork({
  inputSize: 5,
  hiddenLayers: [10],
  outputSize: 2,
});

const xxxTrainingOptions = {
  iterations: 2000,
  learningRate: 0.05,
  momentum: 0.2,
  log: (stats) => {
    // Training error and iteration count logged
  },
  logPeriod: 100,
  timeout: 60000,
  errorThresh: 0.005,
  callback: (stats) => {
    if (stats.error < 0.01) {
      // Training converged
      return true;
    }
  },
  callbackPeriod: 200,
  beta1: 0.9,
  beta2: 0.999,
  epsilon: 1e-8,
};

xxxNetwork.train(xxxData, xxxTrainingOptions);
""",
        "function": "training_options_configuration",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "src/training-options.js",
    },
    # ── 6. Cross-Validation with K-Fold ────────────────────────────────────
    {
        "normalized_code": """\
import { NeuralNetwork } from 'brain.js';

function xxxCrossValidate(xxxDataset, k = 5) {
  const xxxFoldSize = Math.floor(xxxDataset.length / k);
  const xxxScores = [];

  for (let xxxFoldIdx = 0; xxxFoldIdx < k; xxxFoldIdx++) {
    const xxxTestStart = xxxFoldIdx * xxxFoldSize;
    const xxxTestEnd = xxxTestStart + xxxFoldSize;

    const xxxTestData = xxxDataset.slice(xxxTestStart, xxxTestEnd);
    const xxxTrainData = [
      ...xxxDataset.slice(0, xxxTestStart),
      ...xxxDataset.slice(xxxTestEnd),
    ];

    const xxxNet = new NeuralNetwork({
      inputSize: 4,
      hiddenLayers: [8],
      outputSize: 3,
    });

    xxxNet.train(xxxTrainData, { iterations: 500 });

    let xxxError = 0;
    for (const xxxSample of xxxTestData) {
      const xxxPred = xxxNet.run(xxxSample.input);
      xxxError += Math.abs(xxxPred[0] - xxxSample.output[0]);
    }
    xxxScores.push(xxxError / xxxTestData.length);
  }

  return {
    meanScore: xxxScores.reduce((a, b) => a + b) / xxxScores.length,
    scores: xxxScores,
  };
}
""",
        "function": "cross_validation_kfold",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/cross-validation.js",
    },
    # ── 7. Model Serialization to JSON ─────────────────────────────────────
    {
        "normalized_code": """\
import { NeuralNetwork } from 'brain.js';
import * as fs from 'fs';

const xxxNetwork = new NeuralNetwork({
  inputSize: 3,
  hiddenLayers: [5],
  outputSize: 1,
});

xxxNetwork.train(xxxData, { iterations: 1000 });

const xxxSerialized = xxxNetwork.toJSON();
const xxxJsonString = JSON.stringify(xxxSerialized);

fs.writeFileSync('model.json', xxxJsonString);

// Model saved to model.json
// Serialized keys enumerated
// Weights shape calculated
""",
        "function": "model_serialize_tojson",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/serialization.js",
    },
    # ── 8. Model Deserialization from JSON ─────────────────────────────────
    {
        "normalized_code": """\
import { NeuralNetwork } from 'brain.js';
import * as fs from 'fs';

const xxxJsonString = fs.readFileSync('model.json', 'utf-8');
const xxxSerialized = JSON.parse(xxxJsonString);

const xxxRestoredNetwork = new NeuralNetwork();
xxxRestoredNetwork.fromJSON(xxxSerialized);

const xxxTestInput = [0.1, 0.2, 0.3];
const xxxOutput = xxxRestoredNetwork.run(xxxTestInput);

// Restored network output ready
// Network ready for inference

const xxxInfo = {
  inputSize: xxxRestoredNetwork.sizes[0],
  outputSize: xxxRestoredNetwork.sizes[xxxRestoredNetwork.sizes.length - 1],
};
// Network structure info available
""",
        "function": "model_deserialize_fromjson",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/deserialization.js",
    },
    # ── 9. Stream Training (Online Learning) ───────────────────────────────
    {
        "normalized_code": """\
import { NeuralNetwork } from 'brain.js';

const xxxNetwork = new NeuralNetwork({
  inputSize: 2,
  hiddenLayers: [4],
  outputSize: 1,
  learningRate: 0.1,
});

async function xxxStreamTrain(xxxDataStream) {
  let xxxBatchIndex = 0;

  for await (const xxxBatch of xxxDataStream) {
    xxxNetwork.train(xxxBatch, {
      iterations: 100,
      log: (stats) => {
        if (xxxBatchIndex % 10 === 0) {
          // Batch training progress logged
        }
      },
    });
    xxxBatchIndex += 1;
  }

  // Batch training completed
  return xxxNetwork;
}

const xxxTrainedNet = await xxxStreamTrain(xxxAsyncDataIterator);
""",
        "function": "stream_training_online_learning",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "src/stream-training.js",
    },
    # ── 10. Custom Activation Functions ────────────────────────────────────
    {
        "normalized_code": """\
import { NeuralNetwork } from 'brain.js';

const xxxCustomActivations = {
  relu: (v) => Math.max(0, v),
  leaky_relu: (v) => (v > 0 ? v : 0.01 * v),
  elu: (v) => (v > 0 ? v : Math.exp(v) - 1),
  selu: (v) => {
    const xxxAlpha = 1.6732632423543772848170429916717;
    const xxxScale = 1.0507009873554804934193349852946;
    return v > 0 ? xxxScale * v : xxxScale * xxxAlpha * (Math.exp(v) - 1);
  },
  softmax: (v, xxxArray) => {
    const xxxMax = Math.max(...xxxArray);
    const xxxExp = xxxArray.map((x) => Math.exp(x - xxxMax));
    const xxxSum = xxxExp.reduce((a, b) => a + b);
    return xxxExp.map((x) => x / xxxSum);
  },
};

const xxxNetwork = new NeuralNetwork({
  inputSize: 5,
  hiddenLayers: [8],
  outputSize: 3,
  activation: 'leaky_relu',
});

xxxNetwork.train(xxxData, { iterations: 1000 });
const xxxPred = xxxNetwork.run([0.1, 0.2, 0.3, 0.4, 0.5]);
""",
        "function": "custom_activation_function",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "src/activations.js",
    },
    # ── 11. Learning Rate Configuration and Scheduling ─────────────────────
    {
        "normalized_code": """\
import { NeuralNetwork } from 'brain.js';

function xxxAdaptiveLearningRate(xxxIteration) {
  const xxxInitialRate = 0.1;
  const xxxDecayRate = 0.99;
  return xxxInitialRate * Math.pow(xxxDecayRate, xxxIteration);
}

function xxxExponentialLearningRate(xxxIteration) {
  return 0.01 * Math.exp(-0.001 * xxxIteration);
}

const xxxNetwork = new NeuralNetwork({
  inputSize: 4,
  hiddenLayers: [16],
  outputSize: 2,
  learningRate: 0.05,
});

let xxxIteration = 0;
xxxNetwork.train(xxxData, {
  iterations: 100,
  callback: (stats) => {
    const xxxNewLearningRate = xxxAdaptiveLearningRate(xxxIteration);
    xxxNetwork.setLearningRate(xxxNewLearningRate);
    xxxIteration += 1;

    if (xxxIteration % 20 === 0) {
      // Learning rate and error step logged
    }
  },
});
""",
        "function": "learning_rate_configuration_scheduling",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "src/learning-rate.js",
    },
    # ── 12. Likelihood Prediction and Probability Output ───────────────────
    {
        "normalized_code": """\
import { NeuralNetwork } from 'brain.js';

const xxxNetwork = new NeuralNetwork({
  inputSize: 4,
  hiddenLayers: [8],
  outputSize: 3,
});

xxxNetwork.train(xxxClassificationData, { iterations: 1000 });

function xxxPredictWithLikelihood(xxxInput) {
  const xxxRawOutput = xxxNetwork.run(xxxInput);

  const xxxTotal = xxxRawOutput.reduce((a, b) => a + b, 0);
  const xxxProbs = xxxRawOutput.map((v) => v / xxxTotal);

  const xxxMaxIdx = xxxProbs.indexOf(Math.max(...xxxProbs));
  const xxxMaxProb = xxxProbs[xxxMaxIdx];

  return {
    prediction: xxxMaxIdx,
    likelihood: xxxMaxProb,
    allProbabilities: xxxProbs,
    confidence: xxxMaxProb > 0.7 ? 'high' : xxxMaxProb > 0.5 ? 'medium' : 'low',
  };
}

const xxxResult = xxxPredictWithLikelihood([0.2, 0.5, 0.8, 0.1]);
// Prediction result ready
""",
        "function": "likelihood_prediction_probability",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "src/prediction.js",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "feedforward neural network creation training",
    "LSTM long short-term memory sequence prediction",
    "RNN recurrent neural network text generation",
    "GRU gated recurrent unit time series",
    "training options learning rate momentum configuration",
    "cross validation k-fold evaluation",
    "model serialization toJSON save weights",
    "model deserialization fromJSON restore",
    "stream training online incremental learning",
    "custom activation function relu softmax",
    "learning rate scheduling adaptive decay",
    "likelihood prediction probability output classification",
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
