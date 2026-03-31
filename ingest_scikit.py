"""
ingest_scikit.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de scikit-learn/scikit-learn dans la KB Qdrant V6.

Focus : Machine learning patterns (training, pipelines, validation, hyperparameter tuning,
feature engineering, model selection, evaluation, persistence).

Patterns : train_test_split, pipeline_creation, cross_validation, grid_search_cv,
custom_transformer, classification_report, feature_scaling_standard, random_forest_classifier,
gradient_boosting_regressor, pca_dimensionality_reduction, kmeans_clustering, model_persistence_joblib.

Usage:
    .venv/bin/python3 ingest_scikit.py
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
REPO_URL = "https://github.com/scikit-learn/scikit-learn.git"
REPO_NAME = "scikit-learn/scikit-learn"
REPO_LOCAL = "/tmp/scikit-learn"
LANGUAGE = "python"
FRAMEWORK = "generic"
STACK = "python+scikit-learn+ml"
CHARTE_VERSION = "1.0"
TAG = "scikit-learn/scikit-learn"
SOURCE_REPO = "https://github.com/scikit-learn/scikit-learn"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# scikit-learn = machine learning library for Python.
# Patterns CORE : data splitting, pipeline composition, cross-validation, hyperparameter
# search, model evaluation, feature transformations, clustering, supervised learning.
#
# Python ML terms KEPT: estimator, transformer, pipeline, features, target, fit, predict,
# cross_val_score, GridSearchCV, train_test_split, RandomForestClassifier,
# StandardScaler, PCA, KMeans, confusion_matrix, classification_report, joblib.

PATTERNS: list[dict] = [
    # ── 1. Train-test split with stratification ──
    {
        "normalized_code": """\
from sklearn.model_selection import train_test_split
from sklearn.datasets import load_iris
import numpy as np

# Load data
X, y = load_iris(return_X_y=True)

# Stratified split to preserve class distribution
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

print(f"Training set size: {X_train.shape[0]}")
print(f"Test set size: {X_test.shape[0]}")
print(f"Training class distribution: {np.bincount(y_train)}")
""",
        "function": "train_test_split_stratified",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/train_test_split.py",
    },

    # ── 2. Pipeline creation ──
    {
        "normalized_code": """\
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.datasets import load_iris

X, y = load_iris(return_X_y=True)

# Define pipeline: scale → reduce dimensions → classify
pipeline = Pipeline([
    ("scaler", StandardScaler()),
    ("pca", PCA(n_components=2)),
    ("classifier", LogisticRegression(max_iter=200)),
])

# Single fit call processes all steps
pipeline.fit(X, y)
predictions = pipeline.predict(X)
score = pipeline.score(X, y)
print(f"Pipeline accuracy: {score:.3f}")
""",
        "function": "pipeline_creation",
        "feature_type": "model",
        "file_role": "utility",
        "file_path": "examples/pipeline.py",
    },

    # ── 3. Cross-validation scoring ──
    {
        "normalized_code": """\
from sklearn.model_selection import cross_val_score, KFold
from sklearn.ensemble import RandomForestClassifier
from sklearn.datasets import make_classification

X, y = make_classification(n_samples=200, n_features=20, n_classes=3, random_state=42)

estimator = RandomForestClassifier(n_estimators=50, random_state=42)

# 5-fold cross-validation
kfold = KFold(n_splits=5, shuffle=True, random_state=42)
scores = cross_val_score(estimator, X, y, cv=kfold, scoring="accuracy")

print(f"Cross-validation scores: {scores}")
print(f"Mean: {scores.mean():.3f}, Std: {scores.std():.3f}")
""",
        "function": "cross_validation_kfold",
        "feature_type": "model",
        "file_role": "utility",
        "file_path": "examples/cross_validation.py",
    },

    # ── 4. GridSearchCV hyperparameter tuning ──
    {
        "normalized_code": """\
from sklearn.model_selection import GridSearchCV
from sklearn.svm import SVC
from sklearn.datasets import load_iris

X, y = load_iris(return_X_y=True)

# Define parameter grid
param_grid = {
    "C": [0.1, 1, 10],
    "kernel": ["linear", "rbf"],
    "gamma": ["scale", "auto"],
}

# Grid search with 5-fold CV
grid_search = GridSearchCV(
    SVC(), param_grid, cv=5, scoring="accuracy", n_jobs=-1
)
grid_search.fit(X, y)

print(f"Best parameters: {grid_search.best_params_}")
print(f"Best cross-val score: {grid_search.best_score_:.3f}")
best_model = grid_search.best_estimator_
""",
        "function": "grid_search_hyperparameter_tuning",
        "feature_type": "model",
        "file_role": "utility",
        "file_path": "examples/grid_search.py",
    },

    # ── 5. Custom transformer ──
    {
        "normalized_code": """\
from sklearn.base import BaseEstimator, TransformerMixin
import numpy as np

class CustomTransformer(BaseEstimator, TransformerMixin):
    def __init__(self, power: float = 2):
        self.power = power

    def fit(self, X: np.ndarray, y=None):
        # Store statistics during fit
        self.mean_ = X.mean(axis=0)
        self.std_ = X.std(axis=0)
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        # Apply transformation
        X_centered = (X - self.mean_) / (self.std_ + 1e-8)
        return np.power(np.abs(X_centered), self.power)

    def get_feature_names_out(self, input_features=None):
        return np.array([f"feature_{i}" for i in range(input_features)])
""",
        "function": "custom_transformer_base",
        "feature_type": "model",
        "file_role": "utility",
        "file_path": "examples/custom_transformer.py",
    },

    # ── 6. Classification report ──
    {
        "normalized_code": """\
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.ensemble import RandomForestClassifier
from sklearn.datasets import load_iris
from sklearn.model_selection import train_test_split

X, y = load_iris(return_X_y=True)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)
y_pred = model.predict(X_test)

# Detailed classification metrics
print(classification_report(y_test, y_pred, target_names=["class_0", "class_1", "class_2"]))

# Confusion matrix
cm = confusion_matrix(y_test, y_pred)
print(f"Confusion matrix:\\n{cm}")
""",
        "function": "classification_metrics_report",
        "feature_type": "model",
        "file_role": "utility",
        "file_path": "examples/classification_report.py",
    },

    # ── 7. Feature scaling with StandardScaler ──
    {
        "normalized_code": """\
from sklearn.preprocessing import StandardScaler
from sklearn.datasets import make_regression
import numpy as np

X, y = make_regression(n_samples=100, n_features=5, random_state=42)

# Standardization: (x - mean) / std
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

# Verify scaling
print(f"Original mean: {X.mean(axis=0)}")
print(f"Scaled mean: {X_scaled.mean(axis=0)}")
print(f"Original std: {X.std(axis=0)}")
print(f"Scaled std: {X_scaled.std(axis=0)}")

# Transform new data
X_new = np.array([[1, 2, 3, 4, 5]])
X_new_scaled = scaler.transform(X_new)
""",
        "function": "feature_scaling_standard_scaler",
        "feature_type": "schema",
        "file_role": "utility",
        "file_path": "examples/feature_scaling.py",
    },

    # ── 8. Random Forest classifier ──
    {
        "normalized_code": """\
from sklearn.ensemble import RandomForestClassifier
from sklearn.datasets import load_breast_cancer
from sklearn.model_selection import train_test_split

X, y = load_breast_cancer(return_X_y=True)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Random forest with multiple trees
forest = RandomForestClassifier(
    n_estimators=100,
    max_depth=15,
    min_samples_split=5,
    min_samples_leaf=2,
    random_state=42,
    n_jobs=-1,
)

forest.fit(X_train, y_train)
accuracy = forest.score(X_test, y_test)
print(f"Random Forest accuracy: {accuracy:.3f}")

# Feature importance
importances = forest.feature_importances_
top_indices = importances.argsort()[-10:]
print(f"Top 10 important features: {top_indices}")
""",
        "function": "random_forest_classifier_ensemble",
        "feature_type": "model",
        "file_role": "utility",
        "file_path": "examples/random_forest.py",
    },

    # ── 9. Gradient boosting regressor ──
    {
        "normalized_code": """\
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.datasets import make_regression
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score

X, y = make_regression(n_samples=200, n_features=10, random_state=42)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Gradient boosting for regression
regressor = GradientBoostingRegressor(
    n_estimators=100,
    learning_rate=0.1,
    max_depth=5,
    subsample=0.8,
    random_state=42,
)

regressor.fit(X_train, y_train)
y_pred = regressor.predict(X_test)

mse = mean_squared_error(y_test, y_pred)
r2 = r2_score(y_test, y_pred)
print(f"MSE: {mse:.3f}, R2: {r2:.3f}")
""",
        "function": "gradient_boosting_regressor",
        "feature_type": "model",
        "file_role": "utility",
        "file_path": "examples/gradient_boosting.py",
    },

    # ── 10. PCA dimensionality reduction ──
    {
        "normalized_code": """\
from sklearn.decomposition import PCA
from sklearn.datasets import load_iris
import numpy as np

X, y = load_iris(return_X_y=True)

# PCA with variance preservation
pca = PCA(n_components=2)
X_reduced = pca.fit_transform(X)

print(f"Original shape: {X.shape}")
print(f"Reduced shape: {X_reduced.shape}")
print(f"Explained variance ratio: {pca.explained_variance_ratio_}")
print(f"Total variance explained: {pca.explained_variance_ratio_.sum():.3f}")

# Components (loadings)
print(f"First component: {pca.components_[0]}")
""",
        "function": "pca_dimensionality_reduction",
        "feature_type": "model",
        "file_role": "utility",
        "file_path": "examples/pca.py",
    },

    # ── 11. K-means clustering ──
    {
        "normalized_code": """\
from sklearn.cluster import KMeans
from sklearn.datasets import make_blobs
from sklearn.preprocessing import StandardScaler

X, y = make_blobs(n_samples=300, centers=4, n_features=3, random_state=42)
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

# K-means clustering
kmeans = KMeans(
    n_clusters=4,
    init="k-means++",
    max_iter=300,
    random_state=42,
    n_init=10,
)

labels = kmeans.fit_predict(X_scaled)
centers = kmeans.cluster_centers_
inertia = kmeans.inertia_

print(f"Cluster labels: {np.unique(labels)}")
print(f"Inertia: {inertia:.3f}")
print(f"Cluster centers shape: {centers.shape}")
""",
        "function": "kmeans_clustering",
        "feature_type": "model",
        "file_role": "utility",
        "file_path": "examples/kmeans.py",
    },

    # ── 12. Model persistence with joblib ──
    {
        "normalized_code": """\
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.datasets import load_iris

X, y = load_iris(return_X_y=True)

# Train model
model = RandomForestClassifier(n_estimators=50, random_state=42)
model.fit(X, y)

# Save model to disk
joblib.dump(model, "model.joblib", compress=3)
print("Model saved to model.joblib")

# Load model from disk
loaded_model = joblib.load("model.joblib")
predictions = loaded_model.predict(X[:5])
print(f"Predictions: {predictions}")

# Save pipeline with metadata
pipeline_metadata = {
    "model": model,
    "feature_names": ["feature_0", "feature_1", "feature_2", "feature_3"],
    "target_names": ["setosa", "versicolor", "virginica"],
}
joblib.dump(pipeline_metadata, "pipeline_metadata.joblib")
""",
        "function": "model_persistence_joblib",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/model_persistence.py",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "train test split stratified class distribution",
    "pipeline sequential preprocessing classification",
    "cross validation k-fold model evaluation scoring",
    "grid search hyperparameter tuning parameter grid",
    "custom transformer estimator fit predict",
    "classification report metrics confusion matrix",
    "feature scaling standardization normalization",
    "random forest ensemble multiple decision trees",
    "gradient boosting iterative error correction",
    "pca principal component analysis dimensionality reduction",
    "kmeans clustering unsupervised learning centroid",
    "joblib model persistence disk serialization",
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
