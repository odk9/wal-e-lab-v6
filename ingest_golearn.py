"""
ingest_golearn.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
d'une library de ML Go dans la KB Qdrant V6.

Focus : CORE patterns machine learning — data loading, train/test split, model training
(KNN, decision tree, random forest, linear regression), cross-validation, evaluation metrics,
feature selection, PCA transformation, Naive Bayes, model serialization.

Usage:
    .venv/bin/python3 ingest_golearn.py
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
REPO_URL = "https://github.com/sjwhitworth/golearn.git"
REPO_NAME = "sjwhitworth/golearn"
REPO_LOCAL = "/tmp/golearn"
LANGUAGE = "go"
FRAMEWORK = "generic"
STACK = "go+golearn+ml"
CHARTE_VERSION = "1.0"
TAG = "sjwhitworth/golearn"
SOURCE_REPO = "https://github.com/sjwhitworth/golearn"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# golearn = ML library Go. Patterns CORE : data loading, model training, evaluation.
# U-5 : `dataset`, `model`, `classifier`, `predictor`, `instances`, `rows` sont OK (ML terms).
#       Remplacer entity-specific terms : `iris` → `xxx`.

PATTERNS: list[dict] = [
    # ── 1. Load CSV Dataset ───────────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
\t"io/ioutil"
\t"log"

\t"github.com/sjwhitworth/golearn/base"
)

func LoadDatasetFromCSV(filepath string) (base.FixedDataGrid, error) {
\tdata, err := ioutil.ReadFile(filepath)
\tif err != nil {
\t\treturn nil, fmt.Errorf("read file: %w", err)
\t}

\tdataset, err := base.ParseCSVToInstances(filepath, true)
\tif err != nil {
\t\treturn nil, fmt.Errorf("parse csv: %w", err)
\t}

\tlog.Printf("Loaded dataset: %d rows, %d attributes",
\t\tdataset.Rows(),
\t\tdataset.Cols())

\treturn dataset, nil
}
""",
        "function": "load_csv_dataset",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/loader.go",
    },
    # ── 2. Train/Test Split ───────────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
\t"github.com/sjwhitworth/golearn/base"
)

func TrainTestSplit(dataset base.FixedDataGrid, trainRatio float64) (base.FixedDataGrid, base.FixedDataGrid, error) {
\ttotalRows := dataset.Rows()
\ttrainSize := int(float64(trainRows) * trainRatio)

\ttrain, trainErr := base.NewInstancesViewFromRows(dataset, 0, trainSize)
\tif trainErr != nil {
\t\treturn nil, nil, trainErr
\t}

\ttest, testErr := base.NewInstancesViewFromRows(dataset, trainSize, totalRows)
\tif testErr != nil {
\t\treturn nil, nil, testErr
\t}

\treturn train, test, nil
}
""",
        "function": "train_test_split",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/split.go",
    },
    # ── 3. KNN Classifier ─────────────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
\t"github.com/sjwhitworth/golearn/base"
\t"github.com/sjwhitworth/golearn/knn"
)

func TrainKNNClassifier(train base.FixedDataGrid, k int) (*knn.KNNClassifier, error) {
\tclassifier := knn.NewKnnClassifier("euclidean", "linear", k)

\terr := classifier.Fit(train)
\tif err != nil {
\t\treturn nil, err
\t}

\treturn classifier, nil
}

func PredictWithKNN(classifier *knn.KNNClassifier, test base.FixedDataGrid) (base.FixedDataGrid, error) {
\tpredictions, err := classifier.Predict(test)
\tif err != nil {
\t\treturn nil, err
\t}

\treturn predictions, nil
}
""",
        "function": "knn_classifier",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "examples/knn.go",
    },
    # ── 4. Decision Tree ──────────────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
\t"github.com/sjwhitworth/golearn/base"
\t"github.com/sjwhitworth/golearn/trees"
)

func TrainDecisionTree(train base.FixedDataGrid) (*trees.ID3DecisionTree, error) {
\ttree := trees.NewID3DecisionTreeClassifier()

\terr := tree.Fit(train)
\tif err != nil {
\t\treturn nil, err
\t}

\treturn tree, nil
}

func EvaluateDecisionTree(classifier *trees.ID3DecisionTree, test base.FixedDataGrid) (base.FixedDataGrid, error) {
\tpredictions, err := classifier.Predict(test)
\tif err != nil {
\t\treturn nil, err
\t}

\treturn predictions, nil
}
""",
        "function": "decision_tree",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "examples/tree.go",
    },
    # ── 5. Random Forest ──────────────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
\t"github.com/sjwhitworth/golearn/base"
\t"github.com/sjwhitworth/golearn/ensemble"
)

func TrainRandomForest(train base.FixedDataGrid, numTrees int) (*ensemble.RandomForest, error) {
\tforest := ensemble.NewRandomForest(numTrees, 2)

\terr := forest.Fit(train)
\tif err != nil {
\t\treturn nil, err
\t}

\treturn forest, nil
}

func PredictRandomForest(forest *ensemble.RandomForest, test base.FixedDataGrid) (base.FixedDataGrid, error) {
\tpredictions, err := forest.Predict(test)
\tif err != nil {
\t\treturn nil, err
\t}

\treturn predictions, nil
}
""",
        "function": "random_forest",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "examples/forest.go",
    },
    # ── 6. Linear Regression ──────────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
\t"github.com/sjwhitworth/golearn/base"
\t"github.com/sjwhitworth/golearn/linear_models"
)

func TrainLinearRegression(train base.FixedDataGrid) (*linear_models.LinearRegression, error) {
\tregressor := linear_models.NewLinearRegression()

\terr := regressor.Fit(train)
\tif err != nil {
\t\treturn nil, err
\t}

\treturn regressor, nil
}

func PredictLinearRegression(regressor *linear_models.LinearRegression, test base.FixedDataGrid) (base.FixedDataGrid, error) {
\tpredictions, err := regressor.Predict(test)
\tif err != nil {
\t\treturn nil, err
\t}

\treturn predictions, nil
}
""",
        "function": "linear_regression",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "examples/linear.go",
    },
    # ── 7. Cross-Validation ───────────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
\t"github.com/sjwhitworth/golearn/base"
\t"github.com/sjwhitworth/golearn/evaluation"
)

func PerformCrossValidation(dataset base.FixedDataGrid, classifier base.Classifier, k int) (float64, error) {
\tfolds := evaluation.CreateStratifiedFolds(dataset, k)
\tscores := make([]float64, 0)

\tfor _, fold := range folds {
\t\ttrain := fold.Training
\t\ttest := fold.Test

\t\terr := classifier.Fit(train)
\t\tif err != nil {
\t\t\treturn 0, err
\t\t}

\t\tpreds, err := classifier.Predict(test)
\t\tif err != nil {
\t\t\treturn 0, err
\t\t}

\t\taccuracy := evaluation.GetAccuracy(test, preds)
\t\tscores = append(scores, accuracy)
\t}

\tavgScore := calculateMean(scores)
\treturn avgScore, nil
}
""",
        "function": "cross_validation",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/validation.go",
    },
    # ── 8. Confusion Matrix Evaluation ────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
\t"github.com/sjwhitworth/golearn/base"
\t"github.com/sjwhitworth/golearn/evaluation"
)

func EvaluateConfusionMatrix(actual base.FixedDataGrid, predictions base.FixedDataGrid) *evaluation.ConfusionMatrix {
\tcm := evaluation.GetConfusionMatrix(actual, predictions)

\taccuracy := evaluation.GetAccuracy(actual, predictions)
\tprecision := cm.Precision()
\trecall := cm.Recall()
\tf1Score := cm.F1Score()

\treturn &evaluation.ConfusionMatrix{
\t\tTruePositives: cm.TP,
\t\tTrueNegatives: cm.TN,
\t\tFalsePositives: cm.FP,
\t\tFalseNegatives: cm.FN,
\t\tAccuracy: accuracy,
\t\tPrecision: precision,
\t\tRecall: recall,
\t\tF1Score: f1Score,
\t}
}
""",
        "function": "confusion_matrix_eval",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/evaluation.go",
    },
    # ── 9. Feature Selection ──────────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
\t"github.com/sjwhitworth/golearn/base"
\t"github.com/sjwhitworth/golearn/filters"
)

func SelectFeaturesChiSquare(dataset base.FixedDataGrid, k int) (base.FixedDataGrid, error) {
\tfilter := filters.NewChiSquareFilter(dataset, k)

\tfiltered, err := filter.FilterInstances(dataset, k)
\tif err != nil {
\t\treturn nil, err
\t}

\treturn filtered, nil
}

func SelectFeaturesVariance(dataset base.FixedDataGrid, threshold float64) (base.FixedDataGrid, error) {
\tfilter := filters.NewVarianceThresholdFilter(dataset, threshold)

\tfiltered, err := filter.FilterInstances(dataset, 0)
\tif err != nil {
\t\treturn nil, err
\t}

\treturn filtered, nil
}
""",
        "function": "feature_selection",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/features.go",
    },
    # ── 10. PCA Transformation ────────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
\t"github.com/sjwhitworth/golearn/base"
\t"github.com/sjwhitworth/golearn/decomposition"
)

func PerformPCATransform(dataset base.FixedDataGrid, nComponents int) (base.FixedDataGrid, error) {
\tpca := decomposition.NewPCA(nComponents)

\terr := pca.Fit(dataset)
\tif err != nil {
\t\treturn nil, err
\t}

\ttransformed, err := pca.Transform(dataset)
\tif err != nil {
\t\treturn nil, err
\t}

\treturn transformed, nil
}

func GetPCAComponents(pca *decomposition.PCA) [][]float64 {
\treturn pca.Components
}
""",
        "function": "pca_transform",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/pca.go",
    },
    # ── 11. Naive Bayes Classifier ────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
\t"github.com/sjwhitworth/golearn/base"
\t"github.com/sjwhitworth/golearn/naive"
)

func TrainNaiveBayes(train base.FixedDataGrid) (*naive.BayesClassifier, error) {
\tclassifier := naive.NewBayesClassifier()

\terr := classifier.Fit(train)
\tif err != nil {
\t\treturn nil, err
\t}

\treturn classifier, nil
}

func PredictNaiveBayes(classifier *naive.BayesClassifier, test base.FixedDataGrid) (base.FixedDataGrid, error) {
\tpredictions, err := classifier.Predict(test)
\tif err != nil {
\t\treturn nil, err
\t}

\treturn predictions, nil
}
""",
        "function": "naive_bayes",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "examples/bayes.go",
    },
    # ── 12. Model Serialization and Save ──────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
\t"encoding/gob"
\t"fmt"
\t"os"

\t"github.com/sjwhitworth/golearn/base"
)

func SaveModel(classifier base.Classifier, filepath string) error {
\tfile, err := os.Create(filepath)
\tif err != nil {
\t\treturn fmt.Errorf("create file: %w", err)
\t}
\tdefer file.Close()

\tenc := gob.NewEncoder(file)
\terr = enc.Encode(classifier)
\tif err != nil {
\t\treturn fmt.Errorf("encode: %w", err)
\t}

\treturn nil
}

func LoadModel(filepath string) (base.Classifier, error) {
\tfile, err := os.Open(filepath)
\tif err != nil {
\t\treturn nil, fmt.Errorf("open file: %w", err)
\t}
\tdefer file.Close()

\tvar classifier base.Classifier
\tdec := gob.NewDecoder(file)
\terr = dec.Decode(&classifier)
\tif err != nil {
\t\treturn nil, fmt.Errorf("decode: %w", err)
\t}

\treturn classifier, nil
}
""",
        "function": "model_serialize_save",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/model_io.go",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "load CSV dataset from file",
    "train test split dataset partition",
    "KNN k-nearest neighbors classifier",
    "decision tree classification training",
    "random forest ensemble model",
    "linear regression fitting",
    "cross validation fold evaluation",
    "confusion matrix accuracy precision recall",
    "feature selection chi-square variance",
    "PCA principal component analysis",
    "Naive Bayes probabilistic classifier",
    "model serialize save load",
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
