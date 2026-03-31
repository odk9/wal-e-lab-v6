"""
ingest_mlpack.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
d'une library de ML C++ dans la KB Qdrant V6.

Focus : CORE patterns machine learning C++ — data loading, model training (KNN, decision tree,
random forest, linear regression, K-means, PCA, logistic regression, neural networks, Naive Bayes),
cross-validation, model save/load.

Usage:
    .venv/bin/python3 ingest_mlpack.py
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
REPO_URL = "https://github.com/mlpack/mlpack.git"
REPO_NAME = "mlpack/mlpack"
REPO_LOCAL = "/tmp/mlpack"
LANGUAGE = "cpp"
FRAMEWORK = "generic"
STACK = "cpp+mlpack+ml+armadillo"
CHARTE_VERSION = "1.0"
TAG = "mlpack/mlpack"
SOURCE_REPO = "https://github.com/mlpack/mlpack"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# mlpack = ML library C++. Patterns CORE : data loading, model training, evaluation.
# U-5 : `dataset`, `model`, `classifier`, `data`, `mat`, `vec` sont OK (ML/Armadillo terms).
#       Remplacer entity-specific terms : `iris` → `xxx`.

PATTERNS: list[dict] = [
    # ── 1. Load CSV Data ─────────────────────────────────────────────────────
    {
        "normalized_code": """\
#include <mlpack.hpp>

using namespace mlpack;

bool LoadDatasetFromCSV(const std::string& filepath,
                        arma::mat& data,
                        arma::Row<size_t>& labels) {
  bool success = data::Load(filepath, data, true, false);
  if (!success) {
    std::cerr << "Failed to load dataset from " << filepath << std::endl;
    return false;
  }

  if (data.n_rows > 0) {
    labels = arma::conv_to<arma::Row<size_t>>::from(data.row(data.n_rows - 1));
    data.shed_row(data.n_rows - 1);
  }

  std::cout << "Loaded: " << data.n_rows << " features, "
            << data.n_cols << " instances" << std::endl;
  return true;
}
""",
        "function": "load_csv_data",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/loader.cpp",
    },
    # ── 2. KNN Classifier ─────────────────────────────────────────────────────
    {
        "normalized_code": """\
#include <mlpack.hpp>

using namespace mlpack;

void TrainKNNClassifier(const arma::mat& train,
                        const arma::Row<size_t>& trainLabels,
                        size_t k,
                        knn::KNN<>& model) {
  knn::KNN<> knnModel(train, trainLabels);
  model = knnModel;
}

void PredictWithKNN(const knn::KNN<>& model,
                     const arma::mat& test,
                     arma::Row<size_t>& predictions) {
  model.Classify(test, predictions);
}
""",
        "function": "knn_classifier",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "examples/knn.cpp",
    },
    # ── 3. Decision Tree Training ─────────────────────────────────────────────
    {
        "normalized_code": """\
#include <mlpack.hpp>

using namespace mlpack;

void TrainDecisionTree(const arma::mat& train,
                       const arma::Row<size_t>& trainLabels,
                       tree::DecisionTree<>& model) {
  tree::DecisionTreeClassifier dt(train, trainLabels);
  model = dt;
}

void PredictDecisionTree(const tree::DecisionTree<>& model,
                         const arma::mat& test,
                         arma::Row<size_t>& predictions) {
  model.Classify(test, predictions);
}
""",
        "function": "decision_tree_train",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "examples/tree.cpp",
    },
    # ── 4. Random Forest Classifier ───────────────────────────────────────────
    {
        "normalized_code": """\
#include <mlpack.hpp>

using namespace mlpack;

void TrainRandomForest(const arma::mat& train,
                       const arma::Row<size_t>& trainLabels,
                       size_t numTrees,
                       ensemble::RandomForest<>& model) {
  ensemble::RandomForest<> forest(train, trainLabels, 2, numTrees);
  model = forest;
}

void PredictRandomForest(const ensemble::RandomForest<>& model,
                         const arma::mat& test,
                         arma::Row<size_t>& predictions) {
  model.Classify(test, predictions);
}
""",
        "function": "random_forest_classifier",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "examples/forest.cpp",
    },
    # ── 5. Linear Regression ──────────────────────────────────────────────────
    {
        "normalized_code": """\
#include <mlpack.hpp>

using namespace mlpack;

void TrainLinearRegression(const arma::mat& train,
                           const arma::vec& trainResponses,
                           regression::LinearRegression& model) {
  regression::LinearRegression lr(train, trainResponses);
  model = lr;
}

void PredictLinearRegression(const regression::LinearRegression& model,
                             const arma::mat& test,
                             arma::vec& predictions) {
  model.Predict(test, predictions);
}
""",
        "function": "linear_regression",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "examples/linear.cpp",
    },
    # ── 6. K-Means Clustering ─────────────────────────────────────────────────
    {
        "normalized_code": """\
#include <mlpack.hpp>

using namespace mlpack;

void PerformKMeansClustering(const arma::mat& data,
                             size_t numClusters,
                             arma::Row<size_t>& assignments,
                             arma::mat& centroids) {
  kmeans::KMeans<> kmeans;
  kmeans.Cluster(data, numClusters, assignments, centroids);
}

double GetKMeansInertia(const arma::mat& data,
                        const arma::Row<size_t>& assignments,
                        const arma::mat& centroids) {
  double inertia = 0.0;
  for (size_t i = 0; i < data.n_cols; ++i) {
    inertia += arma::norm(data.col(i) - centroids.col(assignments[i]));
  }
  return inertia;
}
""",
        "function": "kmeans_clustering",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "examples/kmeans.cpp",
    },
    # ── 7. PCA Decomposition ──────────────────────────────────────────────────
    {
        "normalized_code": """\
#include <mlpack.hpp>

using namespace mlpack;

void PerformPCADecomposition(const arma::mat& data,
                             size_t numComponents,
                             arma::mat& transformed) {
  preprocessing::PCA pca;
  arma::mat components;

  pca.Apply(data, numComponents, transformed);
}

arma::mat GetPCAComponents(const preprocessing::PCA& pca) {
  return pca.Mean();
}
""",
        "function": "pca_decomposition",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/pca.cpp",
    },
    # ── 8. Logistic Regression ────────────────────────────────────────────────
    {
        "normalized_code": """\
#include <mlpack.hpp>

using namespace mlpack;

void TrainLogisticRegression(const arma::mat& train,
                             const arma::Row<size_t>& trainLabels,
                             regression::LogisticRegression<>& model) {
  regression::LogisticRegression<> lr(train, trainLabels);
  model = lr;
}

void PredictLogisticRegression(const regression::LogisticRegression<>& model,
                               const arma::mat& test,
                               arma::Row<size_t>& predictions) {
  model.Classify(test, predictions);
}
""",
        "function": "logistic_regression",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "examples/logistic.cpp",
    },
    # ── 9. Neural Network FFN ─────────────────────────────────────────────────
    {
        "normalized_code": """\
#include <mlpack.hpp>

using namespace mlpack;

void BuildAndTrainFFN(const arma::mat& train,
                      const arma::mat& trainLabels,
                      ann::FFN<>& model) {
  model.Add<ann::Linear<>>(train.n_rows, 128);
  model.Add<ann::ReLU<>>();
  model.Add<ann::Dropout<>>(0.3);
  model.Add<ann::Linear<>>(128, trainLabels.n_rows);
  model.Add<ann::Softmax<>>();
}

void TrainFFN(const arma::mat& train,
              const arma::mat& trainLabels,
              ann::FFN<>& model) {
  ens::Adam optimizer(0.001, 64, 0.9, 0.999, 1e-8);
  model.Train(train, trainLabels, optimizer);
}
""",
        "function": "neural_network_ffn",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "examples/ffn.cpp",
    },
    # ── 10. Naive Bayes Classifier ────────────────────────────────────────────
    {
        "normalized_code": """\
#include <mlpack.hpp>

using namespace mlpack;

void TrainNaiveBayesClassifier(const arma::mat& train,
                               const arma::Row<size_t>& trainLabels,
                               bayes::NaiveBayesClassifier<>& model) {
  bayes::NaiveBayesClassifier<> nb(train, trainLabels);
  model = nb;
}

void PredictNaiveBayes(const bayes::NaiveBayesClassifier<>& model,
                       const arma::mat& test,
                       arma::Row<size_t>& predictions) {
  model.Classify(test, predictions);
}
""",
        "function": "naive_bayes_classifier",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "examples/bayes.cpp",
    },
    # ── 11. Cross-Validation ──────────────────────────────────────────────────
    {
        "normalized_code": """\
#include <mlpack.hpp>

using namespace mlpack;

double PerformCrossValidation(const arma::mat& data,
                              const arma::Row<size_t>& labels,
                              size_t folds) {
  std::vector<double> scores;

  for (size_t i = 0; i < folds; ++i) {
    arma::uvec testIndices = arma::linspace<arma::uvec>(
        i * data.n_cols / folds,
        (i + 1) * data.n_cols / folds - 1,
        data.n_cols / folds);

    arma::mat trainData = data.cols(
        arma::find(arma::linspace<arma::uvec>(0, data.n_cols - 1, data.n_cols) < i * data.n_cols / folds));

    knn::KNN<> model(trainData, labels);

    arma::Row<size_t> predictions;
    model.Classify(data.cols(testIndices), predictions);

    double accuracy = arma::accu(predictions == labels.cols(testIndices)) /
                     (double)testIndices.n_elem;
    scores.push_back(accuracy);
  }

  return arma::mean(arma::vec(scores));
}
""",
        "function": "cross_validation",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/validation.cpp",
    },
    # ── 12. Model Save/Load ───────────────────────────────────────────────────
    {
        "normalized_code": """\
#include <mlpack.hpp>

using namespace mlpack;

template<typename T>
bool SaveModel(const T& model, const std::string& filepath) {
  std::ofstream ofs(filepath, std::ios::binary);
  if (!ofs.is_open()) {
    std::cerr << "Cannot open file: " << filepath << std::endl;
    return false;
  }

  {
    cereal::BinaryOutputArchive ar(ofs);
    ar(model);
  }

  ofs.close();
  return true;
}

template<typename T>
bool LoadModel(T& model, const std::string& filepath) {
  std::ifstream ifs(filepath, std::ios::binary);
  if (!ifs.is_open()) {
    std::cerr << "Cannot open file: " << filepath << std::endl;
    return false;
  }

  {
    cereal::BinaryInputArchive ar(ifs);
    ar(model);
  }

  ifs.close();
  return true;
}
""",
        "function": "model_save_load",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/model_io.cpp",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "load CSV data from file C++",
    "KNN k-nearest neighbors classifier",
    "decision tree training classification",
    "random forest ensemble classifier",
    "linear regression fitting prediction",
    "K-means clustering algorithm",
    "PCA principal component decomposition",
    "logistic regression binary classification",
    "neural network feedforward training",
    "Naive Bayes probabilistic classifier",
    "cross-validation fold evaluation",
    "model serialization save load cereal",
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
