"""
ingest_twitter_algo.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de twitter/the-algorithm dans la KB Qdrant V6.

Focus : CORE recommendation/feed ranking algorithm patterns.
Patterns conceptuellement traduits de Scala → Python (valide pour KB — représente les algorithmes).

Core concepts:
  - Candidate generation (in-network + out-of-network sources)
  - Heavy ranker (neural network scoring via gradient boosting)
  - Light ranker (feature-based pre-filter)
  - TwHIN graph embeddings + SimClusters community detection
  - Content-based filtering + engagement prediction
  - Blending/mixing ranked candidates
  - Diversity injection (avoid repetition)
  - Real-time feature computation
  - Trust & safety scoring

Usage:
    .venv/bin/python3 ingest_twitter_algo.py
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
REPO_URL = "https://github.com/twitter/the-algorithm.git"
REPO_NAME = "twitter/the-algorithm"
REPO_LOCAL = "/tmp/twitter_algo"
LANGUAGE = "python"
FRAMEWORK = "pytorch"
STACK = "pytorch+numpy+sklearn+faiss+gradient_boosting"
CHARTE_VERSION = "1.0"
TAG = "twitter/the-algorithm"
SOURCE_REPO = "https://github.com/twitter/the-algorithm"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Twitter recommendation algorithm = multi-stage ranking pipeline.
# Patterns CORE : candidate generation, ranking, blending, feature extraction.
#
# U-5 rules:
# - FORBIDDEN: user, post, tweet, item, comment, message, tag, order, event, task
# - KEEP: candidate, score, rank, feature, embedding, engagement, ranker, diversity, blend
# - RENAMES: tweet → entry, post → entry, user → xxx/consumer, item → candidate, comment → reply_entry

PATTERNS: list[dict] = [
    # ── 1. Candidate source: In-network generation (follower feed) ──────────────────
    {
        "normalized_code": """\
from typing import Optional
import numpy as np


class InNetworkCandidateSource:
    \"\"\"Generate candidates from followed xxxs (follower graph) in real-time.\"\"\"

    def __init__(self, max_candidates: int = 1000) -> None:
        self.max_candidates = max_candidates
        self.engagement_threshold: float = 0.1

    def get_candidates(
        self,
        consumer_id: int,
        followed_ids: list[int],
        recent_entries: list[dict],
    ) -> list[dict]:
        \"\"\"Fetch recent entries from followed xxxs.

        Args:
            consumer_id: xxxs requesting feed
            followed_ids: list of followed xxx IDs
            recent_entries: recent entries from each source

        Returns:
            list of candidates with engagement_score, time_decay
        \"\"\"
        candidates = []
        for entry_dict in recent_entries:
            candidates.append({
                "entry_id": entry_dict["id"],
                "source_id": entry_dict["author_id"],
                "engagement_score": self._compute_engagement(entry_dict),
                "time_decay": self._compute_time_decay(entry_dict["created_at"]),
            })
        candidates.sort(
            key=lambda c: c["engagement_score"] * c["time_decay"],
            reverse=True,
        )
        return candidates[: self.max_candidates]

    def _compute_engagement(self, entry: dict) -> float:
        \"\"\"Estimate engagement signal: likes + retweets + replies.\"\"\"
        return (
            entry.get("likes", 0) * 1.0
            + entry.get("retweets", 0) * 2.0
            + entry.get("replies", 0) * 3.0
        ) / (1.0 + entry.get("reach", 1.0))

    def _compute_time_decay(self, timestamp: int) -> float:
        \"\"\"Exponential decay: recent entries scored higher.\"\"\"
        age_hours = (int(time.time()) - timestamp) / 3600.0
        return np.exp(-age_hours / 24.0)
""",
        "function": "in_network_candidate_generation",
        "feature_type": "pipeline",
        "file_role": "model",
        "file_path": "ranking/candidate_source.py",
    },

    # ── 2. Candidate source: Out-of-network (explore) ──────────────────────────────
    {
        "normalized_code": """\
from typing import Optional
import numpy as np


class OutOfNetworkCandidateSource:
    \"\"\"Generate diverse candidates from outside follower graph (exploration).

    Uses clustering + diversity sampling to avoid homogeneous feeds.
    \"\"\"

    def __init__(
        self,
        max_candidates: int = 500,
        diversity_lambda: float = 0.3,
    ) -> None:
        self.max_candidates = max_candidates
        self.diversity_lambda = diversity_lambda  # weight: 0=exploitation, 1=pure explore

    def get_candidates(
        self,
        consumer_id: int,
        not_followed_ids: list[int],
        trending_entries: list[dict],
        community_clusters: list[list[int]],
    ) -> list[dict]:
        \"\"\"Fetch out-of-network entries, balanced by community diversity.\"\"\"
        candidates = []
        community_seen = set()

        for entry_dict in trending_entries:
            author_id = entry_dict["author_id"]
            community_id = self._get_community(author_id, community_clusters)

            # Diversity: avoid repeated communities
            if community_id in community_seen:
                continue
            community_seen.add(community_id)

            popularity = self._compute_popularity(entry_dict)
            score = (1.0 - self.diversity_lambda) * popularity
            score += self.diversity_lambda * np.random.uniform(0, 1)

            candidates.append({
                "entry_id": entry_dict["id"],
                "source_id": author_id,
                "diversity_score": score,
                "community": community_id,
            })

        candidates.sort(key=lambda c: c["diversity_score"], reverse=True)
        return candidates[: self.max_candidates]

    def _get_community(self, xxx_id: int, clusters: list[list[int]]) -> int:
        \"\"\"Find community ID for xxx using pre-computed SimClusters.\"\"\"
        for cidx, cluster in enumerate(clusters):
            if xxx_id in cluster:
                return cidx
        return -1

    def _compute_popularity(self, entry: dict) -> float:
        \"\"\"Global popularity: reach + engagement rate.\"\"\"
        reach = entry.get("reach", 1.0)
        engagement = entry.get("likes", 0) + entry.get("retweets", 0)
        return engagement / max(reach, 1.0)
""",
        "function": "out_of_network_candidate_generation",
        "feature_type": "pipeline",
        "file_role": "model",
        "file_path": "ranking/candidate_source.py",
    },

    # ── 3. Feature extraction: Real-time engagement prediction ──────────────────────
    {
        "normalized_code": """\
import numpy as np
from typing import Optional


class EngagementFeatureExtractor:
    \"\"\"Extract features for engagement prediction (likes, retweets, replies).

    Combines author signals, content signals, consumer signals, context.
    \"\"\"

    def __init__(self) -> None:
        self.cache: dict = {}

    def extract_features(
        self,
        entry_id: int,
        consumer_id: int,
        author_id: int,
        entry_content: str,
    ) -> np.ndarray:
        \"\"\"Extract feature vector for engagement prediction.\"\"\"
        author_features = self._extract_author_features(author_id)
        content_features = self._extract_content_features(entry_content)
        consumer_features = self._extract_consumer_features(consumer_id)
        context_features = self._extract_context_features(entry_id, consumer_id)

        return np.concatenate([
            author_features,
            content_features,
            consumer_features,
            context_features,
        ])

    def _extract_author_features(self, author_id: int) -> np.ndarray:
        \"\"\"Author: follower_count, authority, historical engagement.\"\"\"
        return np.array([
            np.log1p(self.cache.get(f"author_{author_id}_followers", 1.0)),
            self.cache.get(f"author_{author_id}_authority", 0.5),
            self.cache.get(f"author_{author_id}_avg_engagement", 0.3),
        ])

    def _extract_content_features(self, content: str) -> np.ndarray:
        \"\"\"Content: text_length, has_media, has_mention.\"\"\"
        return np.array([
            len(content.split()),
            1.0 if len(content) > 140 else 0.0,
            1.0 if "@" in content else 0.0,
        ])

    def _extract_consumer_features(self, consumer_id: int) -> np.ndarray:
        \"\"\"Consumer: follower_count, activity, recency.\"\"\"
        return np.array([
            np.log1p(self.cache.get(f"consumer_{consumer_id}_followers", 1.0)),
            self.cache.get(f"consumer_{consumer_id}_activity", 0.5),
            self.cache.get(f"consumer_{consumer_id}_online_recency", 0.8),
        ])

    def _extract_context_features(self, entry_id: int, consumer_id: int) -> np.ndarray:
        \"\"\"Context: impression_count, time_since_seen, position.\"\"\"
        return np.array([
            np.log1p(self.cache.get(f"entry_{entry_id}_impressions", 0.0)),
            self.cache.get(f"entry_{entry_id}_age_hours", 1.0),
            0.5,  # normalized feed position
        ])
""",
        "function": "engagement_feature_extraction",
        "feature_type": "feature",
        "file_role": "utility",
        "file_path": "ranking/features.py",
    },

    # ── 4. Heavy ranker: Gradient boosting ranking model ───────────────────────────
    {
        "normalized_code": """\
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from typing import Optional


class HeavyRanker:
    \"\"\"Neural-equivalent heavy ranker using gradient boosting.

    Learns complex interactions: engagement ~ f(author, content, consumer, context).
    Trained on historical engagement labels (likes, retweets, replies).
    \"\"\"

    def __init__(
        self,
        n_estimators: int = 100,
        max_depth: int = 6,
        learning_rate: float = 0.1,
    ) -> None:
        self.model = GradientBoostingRegressor(
            n_estimators=n_estimators,
            max_depth=max_depth,
            learning_rate=learning_rate,
            random_state=42,
        )
        self.is_trained = False

    def train(self, X: np.ndarray, y: np.ndarray) -> None:
        \"\"\"Train heavy ranker on historical engagement data.\"\"\"
        self.model.fit(X, y)
        self.is_trained = True

    def rank(self, candidates: list[dict], features_batch: np.ndarray) -> list[dict]:
        \"\"\"Score candidates via heavy ranker.\"\"\"
        if not self.is_trained:
            raise RuntimeError("Model not trained")

        scores = self.model.predict(features_batch)
        for candidate, score in zip(candidates, scores):
            candidate["heavy_rank_score"] = float(score)

        candidates.sort(key=lambda c: c["heavy_rank_score"], reverse=True)
        return candidates

    def get_feature_importance(self) -> np.ndarray:
        \"\"\"Inspect most important features for ranking.\"\"\"
        return self.model.feature_importances_
""",
        "function": "heavy_ranker_gradient_boosting",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "ranking/ranker.py",
    },

    # ── 5. Light ranker: Fast filtering before heavy ranker ──────────────────────────
    {
        "normalized_code": """\
import numpy as np


class LightRanker:
    \"\"\"Fast pre-filter: eliminate low-quality candidates before heavy ranker.

    Rule-based scoring: 100x faster than neural ranker.
    Reduces computational cost by filtering top K candidates.
    \"\"\"

    def __init__(self, filter_ratio: float = 0.1) -> None:
        self.filter_ratio = filter_ratio  # keep top 10% of candidates
        self.rules = [
            ("safety_score", 0.7),      # safety > 70%
            ("engagement_rate", 0.01),  # engagement rate > 1%
            ("recency_decay", 0.3),     # recent enough
        ]

    def score(self, candidate: dict) -> float:
        \"\"\"Quick heuristic score: combined weighting of rule scores.\"\"\"
        score = 1.0
        for rule_name, threshold in self.rules:
            candidate_value = candidate.get(rule_name, 0.0)
            rule_score = min(candidate_value / threshold, 1.0)
            score *= rule_score
        return score

    def filter(self, candidates: list[dict]) -> list[dict]:
        \"\"\"Apply light ranker, keep top K by score.\"\"\"
        for candidate in candidates:
            candidate["light_rank_score"] = self.score(candidate)

        candidates.sort(key=lambda c: c["light_rank_score"], reverse=True)

        cutoff = max(1, int(len(candidates) * self.filter_ratio))
        return candidates[:cutoff]
""",
        "function": "light_ranker_rule_based_filter",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "ranking/ranker.py",
    },

    # ── 6. TwHIN embeddings: Graph-based similarity ───────────────────────────────
    {
        "normalized_code": """\
import numpy as np
import faiss


class TwHINEmbedder:
    \"\"\"TwHIN (Twitter Heterogeneous Information Network) embeddings.

    Learn dense representations of xxxs and entries from the Twitter graph.
    Enables fast similarity search via FAISS.
    \"\"\"

    def __init__(self, embedding_dim: int = 256) -> None:
        self.embedding_dim = embedding_dim
        self.xxx_embeddings: dict[int, np.ndarray] = {}
        self.entry_embeddings: dict[int, np.ndarray] = {}
        self.faiss_index: Optional[faiss.IndexFlatL2] = None

    def add_embedding(
        self,
        entity_id: int,
        embedding: np.ndarray,
        entity_type: str = "entry",
    ) -> None:
        \"\"\"Store embedding for an entity (xxx or entry).\"\"\"
        if entity_type == "entry":
            self.entry_embeddings[entity_id] = embedding
        else:
            self.xxx_embeddings[entity_id] = embedding

    def build_index(self) -> None:
        \"\"\"Build FAISS index for fast similarity search.\"\"\"
        embeddings = np.array(list(self.entry_embeddings.values())).astype("float32")
        self.faiss_index = faiss.IndexFlatL2(self.embedding_dim)
        self.faiss_index.add(embeddings)

    def search_similar(
        self,
        query_embedding: np.ndarray,
        k: int = 100,
    ) -> list[int]:
        \"\"\"Find k most similar entries to query embedding.\"\"\"
        if self.faiss_index is None:
            raise RuntimeError("Index not built")

        query = query_embedding.reshape(1, -1).astype("float32")
        distances, indices = self.faiss_index.search(query, k)
        entry_ids = list(self.entry_embeddings.keys())
        return [entry_ids[idx] for idx in indices[0]]

    def consumer_to_candidate_similarity(
        self,
        consumer_id: int,
        candidate_id: int,
    ) -> float:
        \"\"\"Cosine similarity between consumer and candidate embeddings.\"\"\"
        consumer_emb = self.xxx_embeddings.get(consumer_id)
        candidate_emb = self.entry_embeddings.get(candidate_id)
        if consumer_emb is None or candidate_emb is None:
            return 0.0
        return float(np.dot(consumer_emb, candidate_emb) / (
            np.linalg.norm(consumer_emb) * np.linalg.norm(candidate_emb) + 1e-8
        ))
""",
        "function": "twhin_graph_embedding_faiss",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "ranking/embedder.py",
    },

    # ── 7. SimClusters: Community detection ────────────────────────────────────────
    {
        "normalized_code": """\
import numpy as np
from typing import Optional


class SimClusters:
    \"\"\"SimClusters: Identify interest-based communities in follower graph.

    Enables diverse candidate sourcing by balancing community representation.
    \"\"\"

    def __init__(self, n_clusters: int = 1024) -> None:
        self.n_clusters = n_clusters
        self.xxx_to_clusters: dict[int, list[float]] = {}  # xxx_id → [cluster_prob]

    def add_membership(
        self,
        xxx_id: int,
        cluster_probabilities: np.ndarray,
    ) -> None:
        \"\"\"Record XXX membership probabilities across clusters.\"\"\"
        self.xxx_to_clusters[xxx_id] = cluster_probabilities

    def get_top_clusters(
        self,
        xxx_id: int,
        k: int = 10,
    ) -> list[int]:
        \"\"\"Get top K cluster IDs for a XXX.\"\"\"
        probs = self.xxx_to_clusters.get(xxx_id)
        if probs is None:
            return []
        top_indices = np.argsort(probs)[-k:][::-1]
        return [int(idx) for idx in top_indices]

    def cluster_similarity(
        self,
        xxx_id_1: int,
        xxx_id_2: int,
    ) -> float:
        \"\"\"Cosine similarity of cluster memberships.\"\"\"
        probs_1 = self.xxx_to_clusters.get(xxx_id_1)
        probs_2 = self.xxx_to_clusters.get(xxx_id_2)
        if probs_1 is None or probs_2 is None:
            return 0.0
        return float(np.dot(probs_1, probs_2) / (
            np.linalg.norm(probs_1) * np.linalg.norm(probs_2) + 1e-8
        ))
""",
        "function": "simclusters_community_detection",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "ranking/clustering.py",
    },

    # ── 8. Blending: Mix candidates from multiple sources ──────────────────────────
    {
        "normalized_code": """\
from typing import Optional
import numpy as np


class BlendingPipeline:
    \"\"\"Blend ranked candidates from multiple sources.

    Interleave in-network, out-of-network, trending candidates.
    Adjust blend ratios by time-of-day and consumer segments.
    \"\"\"

    def __init__(
        self,
        in_network_ratio: float = 0.5,
        out_network_ratio: float = 0.3,
        trending_ratio: float = 0.2,
    ) -> None:
        self.in_network_ratio = in_network_ratio
        self.out_network_ratio = out_network_ratio
        self.trending_ratio = trending_ratio

    def blend(
        self,
        in_network_candidates: list[dict],
        out_network_candidates: list[dict],
        trending_candidates: list[dict],
        feed_size: int = 50,
    ) -> list[dict]:
        \"\"\"Interleave candidates respecting source ratios.\"\"\"
        in_net_count = int(feed_size * self.in_network_ratio)
        out_net_count = int(feed_size * self.out_network_ratio)
        trending_count = feed_size - in_net_count - out_net_count

        blended = []
        blended.extend(in_network_candidates[:in_net_count])
        blended.extend(out_network_candidates[:out_net_count])
        blended.extend(trending_candidates[:trending_count])

        return blended

    def adjust_for_segment(
        self,
        consumer_segment: str,
    ) -> None:
        \"\"\"Adjust ratios by consumer segment (e.g., power_xxx, casual).\"\"\"
        if consumer_segment == "power_xxx":
            self.in_network_ratio = 0.7
            self.out_network_ratio = 0.2
        elif consumer_segment == "casual":
            self.in_network_ratio = 0.4
            self.out_network_ratio = 0.4
""",
        "function": "blending_pipeline_source_mix",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "ranking/blender.py",
    },

    # ── 9. Diversity injection: Avoid repetitive content ──────────────────────────
    {
        "normalized_code": """\
import numpy as np


class DiversityFilter:
    \"\"\"Diversity scoring: avoid repetitive content in ranked feed.

    Tracks semantic similarity + author diversity.
    \"\"\"

    def __init__(
        self,
        min_author_diversity: float = 0.7,
        max_semantic_similarity: float = 0.85,
    ) -> None:
        self.min_author_diversity = min_author_diversity
        self.max_semantic_similarity = max_semantic_similarity
        self.selected_authors: set[int] = set()
        self.selected_embeddings: list[np.ndarray] = []

    def filter(
        self,
        candidates: list[dict],
        embeddings: dict[int, np.ndarray],
    ) -> list[dict]:
        \"\"\"Filter candidates ensuring diversity.\"\"\"
        result = []
        for candidate in candidates:
            author_id = candidate["source_id"]
            entry_embedding = embeddings.get(candidate["entry_id"])

            # Author diversity: avoid concentrating from few xxxs
            author_diversity = len(self.selected_authors) / max(len(result) + 1, 1)
            if author_id in self.selected_authors:
                author_diversity *= 0.5  # penalty for repeat author

            if author_diversity < self.min_author_diversity:
                continue

            # Semantic diversity: avoid duplicate/near-duplicate content
            if entry_embedding is not None:
                max_similarity = max([
                    self._cosine_similarity(entry_embedding, emb)
                    for emb in self.selected_embeddings
                ] + [0.0])

                if max_similarity > self.max_semantic_similarity:
                    continue

                self.selected_embeddings.append(entry_embedding)

            self.selected_authors.add(author_id)
            result.append(candidate)

        return result

    def _cosine_similarity(self, v1: np.ndarray, v2: np.ndarray) -> float:
        \"\"\"Cosine similarity between embeddings.\"\"\"
        return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-8))
""",
        "function": "diversity_filter_semantic_author",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "ranking/diversity.py",
    },

    # ── 10. Trust & safety scoring: Content moderation ──────────────────────────────
    {
        "normalized_code": """\
import numpy as np


class TrustSafetyScorer:
    \"\"\"Score content for safety and trust signals.

    Detects spam, harassment, misinformation. Reduces ranking for unsafe content.
    \"\"\"

    def __init__(self) -> None:
        self.spam_keywords: set[str] = {"buy", "click_here", "limited_offer"}
        self.harassment_indicators: list[str] = ["attack", "hateful"]
        self.misinformation_cache: dict[str, float] = {}

    def score(self, entry: dict) -> float:
        \"\"\"Compute trust/safety score (0.0 = unsafe, 1.0 = safe).\"\"\"
        spam_score = self._detect_spam(entry.get("content", ""))
        harassment_score = self._detect_harassment(entry.get("content", ""))
        misinformation_score = self._detect_misinformation(entry.get("url", ""))

        # Weighted combination
        safety = (
            0.4 * (1.0 - spam_score)
            + 0.4 * (1.0 - harassment_score)
            + 0.2 * misinformation_score
        )
        return max(0.0, min(safety, 1.0))

    def _detect_spam(self, content: str) -> float:
        \"\"\"Spam detection heuristic.\"\"\"
        for keyword in self.spam_keywords:
            if keyword in content.lower():
                return 0.8
        return 0.0

    def _detect_harassment(self, content: str) -> float:
        \"\"\"Harassment detection heuristic.\"\"\"
        for indicator in self.harassment_indicators:
            if indicator in content.lower():
                return 0.9
        return 0.0

    def _detect_misinformation(self, url: str) -> float:
        \"\"\"Check URL against misinformation cache.\"\"\"
        if url in self.misinformation_cache:
            return 1.0 - self.misinformation_cache[url]
        return 1.0  # default: assume safe
""",
        "function": "trust_safety_moderation_scoring",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "ranking/safety.py",
    },

    # ── 11. Real-time feature computation: Online feature server ───────────────────
    {
        "normalized_code": """\
from typing import Optional
import time


class RealTimeFeatureServer:
    \"\"\"Compute fresh features at ranking time (not pre-computed).

    Captures recency signals: online status, recent interactions, impressions.
    \"\"\"

    def __init__(self) -> None:
        self.cache: dict[str, tuple[float, float]] = {}  # key → (value, timestamp)
        self.cache_ttl: float = 300.0  # 5 minutes

    def get_feature(
        self,
        feature_key: str,
        compute_fn,
    ) -> float:
        \"\"\"Lazy-load feature: return cached or compute fresh.\"\"\"
        now = time.time()
        if feature_key in self.cache:
            cached_val, cached_time = self.cache[feature_key]
            if now - cached_time < self.cache_ttl:
                return cached_val

        # Compute fresh
        value = compute_fn()
        self.cache[feature_key] = (value, now)
        return value

    def get_consumer_engagement_today(self, consumer_id: int) -> float:
        \"\"\"Today's engagement rate for consumer.\"\"\"
        return self.get_feature(
            f"engagement_today_{consumer_id}",
            lambda: self._query_engagement_store(consumer_id),
        )

    def get_entry_impression_count(self, entry_id: int) -> float:
        \"\"\"Real-time impression count for entry.\"\"\"
        return self.get_feature(
            f"impressions_{entry_id}",
            lambda: self._query_impression_log(entry_id),
        )

    def _query_engagement_store(self, consumer_id: int) -> float:
        \"\"\"Query engagement store (stub).\"\"\"
        return 0.5

    def _query_impression_log(self, entry_id: int) -> float:
        \"\"\"Query impression log (stub).\"\"\"
        return 100.0
""",
        "function": "real_time_feature_server_online",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "ranking/features_realtime.py",
    },

    # ── 12. End-to-end ranking pipeline ───────────────────────────────────────────
    {
        "normalized_code": """\
from typing import Optional
import numpy as np


class RankingPipeline:
    \"\"\"Complete feed ranking pipeline: candidates → filter → rank → blend → diversity.\"\"\"

    def __init__(
        self,
        light_ranker,
        heavy_ranker,
        blender,
        diversity_filter,
        safety_scorer,
    ) -> None:
        self.light_ranker = light_ranker
        self.heavy_ranker = heavy_ranker
        self.blender = blender
        self.diversity_filter = diversity_filter
        self.safety_scorer = safety_scorer

    def rank_feed(
        self,
        consumer_id: int,
        in_network_candidates: list[dict],
        out_network_candidates: list[dict],
        feature_extractor,
    ) -> list[dict]:
        \"\"\"Execute full ranking pipeline.\"\"\"
        # Step 1: Light ranker filter
        all_candidates = in_network_candidates + out_network_candidates
        filtered = self.light_ranker.filter(all_candidates)

        # Step 2: Heavy ranker scoring
        features = np.array([
            feature_extractor.extract_features(
                c["entry_id"],
                consumer_id,
                c["source_id"],
                c.get("content", ""),
            )
            for c in filtered
        ])
        scored = self.heavy_ranker.rank(filtered, features)

        # Step 3: Safety filtering
        safe_candidates = [
            c for c in scored
            if self.safety_scorer.score(c) > 0.5
        ]

        # Step 4: Blend sources
        blended = self.blender.blend(
            in_network_candidates[:30],
            out_network_candidates[:20],
            safe_candidates[:10],
        )

        # Step 5: Diversity injection
        embeddings_map = {c["entry_id"]: np.random.randn(256) for c in blended}
        final_feed = self.diversity_filter.filter(blended, embeddings_map)

        return final_feed
""",
        "function": "ranking_pipeline_e2e",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "ranking/pipeline.py",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "in-network candidate generation from follower graph engagement ranking",
    "out-of-network exploration diverse candidates community clusters",
    "heavy ranker gradient boosting engagement prediction complex interactions",
    "light ranker fast rule-based filter before heavy ranker",
    "TwHIN graph embeddings FAISS similarity search",
    "SimClusters community detection follower graph clustering",
    "blending mix in-network out-of-network trending candidates",
    "diversity filter avoid repetitive semantic content author",
    "trust safety moderation spam harassment misinformation detection",
    "real-time feature server online engagement impressions",
    "end-to-end ranking pipeline candidate filter score blend diversity",
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
