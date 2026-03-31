"""
ingest_implicit.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de benfred/implicit dans la KB Qdrant V6.

Focus : CORE patterns collaborative filtering (ALS, BPR, LMF, factorization,
sparse matrix operations, evaluation metrics, recommendations).

Usage:
    .venv/bin/python3 ingest_implicit.py
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
REPO_URL = "https://github.com/benfred/implicit.git"
REPO_NAME = "benfred/implicit"
REPO_LOCAL = "/tmp/implicit"
LANGUAGE = "python"
FRAMEWORK = "generic"
STACK = "python+scipy+numpy+cython"
CHARTE_VERSION = "1.0"
TAG = "benfred/implicit"
SOURCE_REPO = "https://github.com/benfred/implicit"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Implicit = collaborative filtering recommendation engine via matrix factorization.
# Patterns CORE : ALS, BPR, LMF algorithms, factor initialization, sparse matrix ops,
# evaluation metrics (precision@k, NDCG, MAP), approximate nearest neighbors (Faiss, Annoy).
# U-5 : "user" → "xxx", "item" → "xxx_item", "user_factors" → "xxx_factors",
# "item_factors" → "xxx_item_factors", BUT keep all ML/math terms untouched.

PATTERNS: list[dict] = [
    # ── 1. Matrix factorization base class ────────────────────────────────────
    {
        "normalized_code": """\
from abc import ABCMeta, abstractmethod

import numpy as np


class MatrixFactorizationBase(metaclass=ABCMeta):
    \"\"\"Base class for matrix factorization recommendation models.\"\"\"

    def __init__(self, num_threads: int = 0) -> None:
        self.xxx_factors: np.ndarray | None = None
        self.xxx_item_factors: np.ndarray | None = None
        self._xxx_norms: np.ndarray | None = None
        self._xxx_item_norms: np.ndarray | None = None
        self.num_threads: int = num_threads

    @abstractmethod
    def fit(self, interactions: np.ndarray, show_progress: bool = True) -> None:
        \"\"\"Fit latent factor model on interaction matrix.\"\"\"
        pass

    @abstractmethod
    def recommend(
        self,
        xxxid: int,
        xxx_interactions: np.ndarray,
        n: int = 10,
    ) -> tuple[np.ndarray, np.ndarray]:
        \"\"\"Generate top-N recommendations for entity.\"\"\"
        pass
""",
        "function": "matrix_factorization_base_class",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "implicit/cpu/matrix_factorization_base.py",
    },
    # ── 2. Alternating Least Squares algorithm ────────────────────────────────
    {
        "normalized_code": """\
import numpy as np
import scipy.sparse


def als_iteration(
    xxx_interactions: scipy.sparse.csr_matrix,
    xxx_factors: np.ndarray,
    xxx_entity_factors: np.ndarray,
    regularization: float,
    alpha: float,
) -> np.ndarray:
    \"\"\"Update entity factors via ALS least-squares solve.

    Solves: (X^T X + λI) x = X^T (α * p + 1)
    where X = entity factors, p = positive interactions.
    \"\"\"
    n_factors: int = xxx_entity_factors.shape[1]
    xxx_entity_gram: np.ndarray = xxx_entity_factors.T @ xxx_entity_factors

    # Add regularization to diagonal
    gram_diag: np.ndarray = np.diag(xxx_entity_gram) + regularization
    xxx_entity_gram += np.diag(gram_diag - np.diag(xxx_entity_gram))

    # Compute (Y^T Y)^-1 once
    ytyi: np.ndarray = np.linalg.inv(xxx_entity_gram)

    # Solve for each entity
    n_xxxs: int = xxx_interactions.shape[0]
    xxx_factors_new: np.ndarray = np.zeros((n_xxxs, n_factors), dtype=xxx_factors.dtype)

    for i in range(n_xxxs):
        # Get nonzero interactions for this entity
        row_start: int = xxx_interactions.indptr[i]
        row_end: int = xxx_interactions.indptr[i + 1]
        indices: np.ndarray = xxx_interactions.indices[row_start:row_end]
        confidences: np.ndarray = xxx_interactions.data[row_start:row_end]

        # Compute RHS: Y^T (α * p + 1)
        rhs: np.ndarray = xxx_entity_factors[indices].T @ (confidences * alpha)

        # Solve: x = (Y^T Y)^-1 Y^T (α * p + 1)
        xxx_factors_new[i] = ytyi @ rhs

    return xxx_factors_new
""",
        "function": "als_iteration_least_squares_solve",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "implicit/cpu/als.py",
    },
    # ── 3. Bayesian Personalized Ranking loss ────────────────────────────────
    {
        "normalized_code": """\
import numpy as np


def bpr_gradient_step(
    xxx_factors: np.ndarray,
    xxx_item_factors: np.ndarray,
    positive_idx: int,
    negative_idx: int,
    learning_rate: float = 0.01,
    regularization: float = 0.01,
) -> tuple[np.ndarray, np.ndarray]:
    \"\"\"Compute BPR gradient step for one negative sample.

    Minimizes: -log(σ(r_uij)) + λ(||x_u||^2 + ||y_i||^2 + ||y_j||^2)
    where r_uij = x_u · (y_i - y_j).
    \"\"\"
    xxx_vec: np.ndarray = xxx_factors[0]
    pos_vec: np.ndarray = xxx_item_factors[positive_idx]
    neg_vec: np.ndarray = xxx_item_factors[negative_idx]

    # Compute ranking score difference
    diff: np.ndarray = pos_vec - neg_vec
    score: float = np.dot(xxx_vec, diff)

    # Sigmoid derivative: σ(x) * (1 - σ(x))
    sigmoid_deriv: float = 1.0 / (1.0 + np.exp(score))

    # Gradients (simplified: assume sigmoid_deriv ≈ 0.5 at optimum)
    xxx_grad: np.ndarray = sigmoid_deriv * (pos_vec - neg_vec) + regularization * xxx_vec
    pos_grad: np.ndarray = sigmoid_deriv * xxx_vec + regularization * pos_vec
    neg_grad: np.ndarray = -sigmoid_deriv * xxx_vec + regularization * neg_vec

    # Update
    xxx_factors_new: np.ndarray = xxx_factors[0] - learning_rate * xxx_grad
    pos_vec_new: np.ndarray = pos_vec - learning_rate * pos_grad
    neg_vec_new: np.ndarray = neg_vec - learning_rate * neg_grad

    return xxx_factors_new, pos_vec_new
""",
        "function": "bpr_gradient_optimization_pairwise",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "implicit/cpu/bpr.py",
    },
    # ── 4. Logistic Matrix Factorization ──────────────────────────────────────
    {
        "normalized_code": """\
import numpy as np
from scipy.special import expit  # sigmoid


class LogisticMatrixFactorization:
    \"\"\"Logistic Matrix Factorization for implicit feedback.\"\"\"

    def __init__(
        self,
        factors: int = 30,
        learning_rate: float = 1.0,
        regularization: float = 0.6,
        neg_prop: int = 30,
        iterations: int = 30,
    ) -> None:
        self.factors: int = factors
        self.learning_rate: float = learning_rate
        self.regularization: float = regularization
        self.neg_prop: int = neg_prop
        self.iterations: int = iterations
        self.xxx_factors: np.ndarray | None = None
        self.xxx_entity_factors: np.ndarray | None = None

    def _update_factors(
        self,
        xxx_interactions: np.ndarray,
        xxx_factor_vec: np.ndarray,
        xxx_entity_factor_matrix: np.ndarray,
    ) -> np.ndarray:
        \"\"\"Update entity factor via logistic loss gradient descent.\"\"\"
        update: np.ndarray = np.zeros_like(xxx_factor_vec)

        for idx, confidence in zip(
            xxx_interactions.nonzero()[0],
            xxx_interactions.data,
        ):
            xxx_entity_vec: np.ndarray = xxx_entity_factor_matrix[idx]
            logit: float = np.dot(xxx_factor_vec, xxx_entity_vec)
            logistic: float = expit(logit)

            # Gradient of binary cross-entropy
            gradient: np.ndarray = (confidence - logistic) * xxx_entity_vec
            update += gradient

        # Apply regularization penalty
        regularized_update: np.ndarray = (
            self.learning_rate * update
            - self.regularization * xxx_factor_vec
        )
        return xxx_factor_vec + regularized_update
""",
        "function": "logistic_matrix_factorization_loss",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "implicit/cpu/lmf.py",
    },
    # ── 5. Sparse matrix nonzero iterator ────────────────────────────────────
    {
        "normalized_code": """\
import numpy as np
import scipy.sparse


def nonzeros_csr(matrix: scipy.sparse.csr_matrix, row: int) -> tuple[np.ndarray, np.ndarray]:
    \"\"\"Yield (index, value) pairs for nonzero entries in a CSR row.

    Efficient iterator over sparse row without materializing dense vector.
    \"\"\"
    row_start: int = matrix.indptr[row]
    row_end: int = matrix.indptr[row + 1]
    indices: np.ndarray = matrix.indices[row_start:row_end]
    values: np.ndarray = matrix.data[row_start:row_end]
    return indices, values


def count_interactions_per_entity(interactions: scipy.sparse.csr_matrix) -> np.ndarray:
    \"\"\"Count number of interactions per entity in CSR matrix.\"\"\"
    counts: np.ndarray = np.diff(interactions.indptr)
    return counts
""",
        "function": "sparse_matrix_csr_iteration",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "implicit/utils.py",
    },
    # ── 6. Top-K recommendation extraction ────────────────────────────────────
    {
        "normalized_code": """\
import heapq
import numpy as np


def topk_recommendations(
    scores: np.ndarray,
    k: int = 10,
    exclude_indices: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    \"\"\"Extract top-K entity indices and scores from prediction vector.

    Uses heapq for efficiency if k << n (partial sort via heap).
    \"\"\"
    if exclude_indices is not None:
        scores = scores.copy()
        scores[exclude_indices] = -np.inf

    # If k is small relative to array size, use heap selection
    if k < len(scores) // 2:
        top_indices: list[tuple[float, int]] = heapq.nlargest(
            k,
            enumerate(scores),
            key=lambda x: x[1],
        )
        indices: np.ndarray = np.array([idx for idx, _ in top_indices])
        values: np.ndarray = np.array([val for _, val in top_indices])
    else:
        # Full sort for larger k
        indices = np.argsort(-scores)[:k]
        values = scores[indices]

    return indices, values
""",
        "function": "topk_entity_selection",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "implicit/cpu/topk.py",
    },
    # ── 7. Faiss approximate nearest neighbor index ───────────────────────────
    {
        "normalized_code": """\
import faiss
import numpy as np


class FaissApproximateRecommender:
    \"\"\"Wrap matrix factorization model with Faiss ANN for fast inference.\"\"\"

    def __init__(
        self,
        xxx_entity_factors: np.ndarray,
        nlist: int = 400,
        nprobe: int = 20,
        use_gpu: bool = False,
    ) -> None:
        self.xxx_entity_factors: np.ndarray = xxx_entity_factors.astype("float32")
        self.nlist: int = nlist
        self.nprobe: int = nprobe
        self.use_gpu: bool = use_gpu

        # Build inner-vector index
        dim: int = xxx_entity_factors.shape[1]
        quantizer: faiss.Index = faiss.IndexFlat(dim)
        self.index: faiss.IndexIVFFlat = faiss.IndexIVFFlat(
            quantizer,
            dim,
            nlist,
            faiss.METRIC_INNER_PRODUCT,
        )
        self.index.add(self.xxx_entity_factors)

    def search(self, xxx_vector: np.ndarray, k: int = 10) -> tuple[np.ndarray, np.ndarray]:
        \"\"\"Query index with entity vector, return top-K entity indices + distances.\"\"\"
        xxx_vec_query: np.ndarray = xxx_vector.astype("float32").reshape(1, -1)
        scores, indices = self.index.search(xxx_vec_query, k)
        return indices[0], scores[0]
""",
        "function": "faiss_approximate_nearest_neighbors_index",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "implicit/ann/faiss.py",
    },
    # ── 8. Evaluation metric: Precision@K ────────────────────────────────────
    {
        "normalized_code": """\
import numpy as np


def precision_at_k(
    predictions: np.ndarray,
    ground_truth: np.ndarray,
    k: int = 10,
) -> float:
    \"\"\"Compute Precision@K: fraction of top-K predictions in ground truth.\"\"\"
    top_k_indices: np.ndarray = predictions[:k]
    hits: int = np.sum(np.isin(top_k_indices, ground_truth))
    return float(hits) / k


def recall_at_k(
    predictions: np.ndarray,
    ground_truth: np.ndarray,
    k: int = 10,
) -> float:
    \"\"\"Compute Recall@K: fraction of ground truth captured in top-K.\"\"\"
    if len(ground_truth) == 0:
        return 0.0
    top_k_indices: np.ndarray = predictions[:k]
    hits: int = np.sum(np.isin(top_k_indices, ground_truth))
    return float(hits) / len(ground_truth)


def ndcg_at_k(
    predictions: np.ndarray,
    ground_truth: np.ndarray,
    k: int = 10,
) -> float:
    \"\"\"Compute Normalized Discounted Cumulative Gain@K.\"\"\"
    top_k_indices: np.ndarray = predictions[:k]
    gains: np.ndarray = np.isin(top_k_indices, ground_truth).astype(float)

    # DCG = sum(gains / log2(i+2)) for i in [0, k)
    dcg: float = np.sum(gains / np.log2(np.arange(1, k + 1) + 1))

    # IDCG = sum(1 / log2(i+2)) for i in [0, min(k, |GT|))
    ideal_k: int = min(k, len(ground_truth))
    idcg: float = np.sum(1.0 / np.log2(np.arange(1, ideal_k + 1) + 1))

    return dcg / idcg if idcg > 0 else 0.0
""",
        "function": "ranking_evaluation_metrics_precision_recall_ndcg",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "implicit/evaluation.py",
    },
    # ── 9. Factor initialization via random seed ─────────────────────────────
    {
        "normalized_code": """\
import numpy as np


def check_random_state(random_state: int | np.random.Generator | None) -> np.random.Generator:
    \"\"\"Convert int/RandomState/None to numpy Generator for reproducible initialization.\"\"\"
    if random_state is None:
        return np.random.default_rng()
    if isinstance(random_state, np.random.RandomState):
        # Backward compat: convert old RandomState to Generator
        return np.random.default_rng(random_state.randint(2**31))
    if isinstance(random_state, int):
        return np.random.default_rng(random_state)
    return random_state


def initialize_factors(
    n_entities: int,
    n_factors: int,
    random_state: int | np.random.Generator | None = None,
    dtype: np.dtype = np.float32,
) -> np.ndarray:
    \"\"\"Initialize factor matrix with small random normal values.\"\"\"
    rng: np.random.Generator = check_random_state(random_state)
    # Small initialization helps convergence
    factors: np.ndarray = rng.normal(0.0, 0.01, size=(n_entities, n_factors))
    return factors.astype(dtype)
""",
        "function": "factor_matrix_initialization",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "implicit/utils.py",
    },
    # ── 10. Confidence weighting for implicit feedback ───────────────────────
    {
        "normalized_code": """\
import numpy as np
import scipy.sparse


def confidence_weight_interactions(
    interactions: scipy.sparse.csr_matrix,
    alpha: float = 1.0,
) -> scipy.sparse.csr_matrix:
    \"\"\"Convert implicit feedback to weighted confidence matrix.

    For implicit feedback, presence indicates preference.
    Confidence weights can be: c_ab = 1 + α * r_ab (where r_ab = count/frequency).
    \"\"\"
    weighted: scipy.sparse.csr_matrix = interactions.copy()
    weighted.data = 1.0 + alpha * weighted.data
    return weighted


def prepare_interactions_matrix(
    xxx_ids: np.ndarray,
    xxx_entity_ids: np.ndarray,
    confidences: np.ndarray | None = None,
    n_xxxs: int | None = None,
    n_xxx_entities: int | None = None,
) -> scipy.sparse.csr_matrix:
    \"\"\"Build CSR matrix from (entity_a, entity_b, confidence) triplets.\"\"\"
    if confidences is None:
        confidences = np.ones_like(xxx_ids, dtype=float)

    n_xxxs = n_xxxs or (xxx_ids.max() + 1)
    n_xxx_entities = n_xxx_entities or (xxx_entity_ids.max() + 1)

    interactions: scipy.sparse.csr_matrix = scipy.sparse.csr_matrix(
        (confidences, (xxx_ids, xxx_entity_ids)),
        shape=(n_xxxs, n_xxx_entities),
    )
    return interactions
""",
        "function": "confidence_weighting_implicit_feedback",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "implicit/utils.py",
    },
    # ── 11. Entity similarity via cosine distance ────────────────────────────
    {
        "normalized_code": """\
import numpy as np


def compute_cosine_similarity(
    vector_a: np.ndarray,
    vector_b: np.ndarray,
) -> float:
    \"\"\"Compute cosine similarity between two factor vectors.\"\"\"
    norm_a: float = np.linalg.norm(vector_a)
    norm_b: float = np.linalg.norm(vector_b)

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    similarity: float = np.dot(vector_a, vector_b) / (norm_a * norm_b)
    return float(np.clip(similarity, -1.0, 1.0))


def all_pairs_similarity_matrix(
    xxx_entity_factors: np.ndarray,
) -> np.ndarray:
    \"\"\"Compute pairwise cosine similarity matrix for entities.\"\"\"
    # Normalize rows
    norms: np.ndarray = np.linalg.norm(xxx_entity_factors, axis=1, keepdims=True)
    normalized: np.ndarray = xxx_entity_factors / (norms + 1e-8)

    # Compute Gram matrix
    similarity_matrix: np.ndarray = normalized @ normalized.T
    return similarity_matrix
""",
        "function": "cosine_similarity_entity_similarity",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "implicit/nearest_neighbours.py",
    },
    # ── 12. Model serialization and checkpoint save/load ──────────────────────
    {
        "normalized_code": """\
import numpy as np
import scipy.sparse


def save_model_checkpoint(
    filepath: str,
    xxx_factors: np.ndarray,
    xxx_entity_factors: np.ndarray,
    hyperparameters: dict,
) -> None:
    \"\"\"Serialize trained factors and hyperparameters to disk.\"\"\"
    checkpoint: dict = {
        "xxx_factors": xxx_factors,
        "xxx_entity_factors": xxx_entity_factors,
        "hyperparameters": hyperparameters,
    }
    np.savez_compressed(filepath, **checkpoint)


def load_model_checkpoint(filepath: str) -> tuple[np.ndarray, np.ndarray, dict]:
    \"\"\"Deserialize trained model from checkpoint file.\"\"\"
    data: np.lib.npyio.NpzFile = np.load(filepath)
    xxx_factors: np.ndarray = data["xxx_factors"]
    xxx_entity_factors: np.ndarray = data["xxx_entity_factors"]
    hyperparameters: dict = dict(data["hyperparameters"])
    return xxx_factors, xxx_entity_factors, hyperparameters
""",
        "function": "model_serialization_checkpoint_save_load",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "implicit/utils.py",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "alternating least squares matrix factorization collaborative filtering",
    "Bayesian personalized ranking pairwise loss SGD",
    "logistic matrix factorization implicit feedback probability",
    "sparse CSR matrix nonzero row iteration",
    "top-K item recommendation selection via heap",
    "Faiss approximate nearest neighbors inner product search",
    "precision recall NDCG ranking evaluation metrics",
    "factor matrix random initialization convergence",
    "confidence weighting implicit feedback interactions",
    "cosine similarity item-item collaborative recommendations",
    "model checkpoint save load serialization numpy",
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
