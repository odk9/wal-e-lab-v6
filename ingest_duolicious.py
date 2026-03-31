"""
ingest_duolicious.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de duolicious/duolicious-backend dans la KB Qdrant V6.

Focus : CORE dating/matching patterns (geolocation search, compatibility scoring,
rate limiting, photo verification, anti-spam, matching algorithm).

PAS des patterns CRUD simples — patterns spécifiques au domaine dating avec
PostGIS distance, personality vector similarity, verification tiers, anti-abuse.

Usage:
    .venv/bin/python3 ingest_duolicious.py
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
REPO_URL = "https://github.com/duolicious/duolicious-backend.git"
REPO_NAME = "duolicious/duolicious-backend"
REPO_LOCAL = "/tmp/duolicious-backend"
LANGUAGE = "python"
FRAMEWORK = "postgresql+postgis+flask"
STACK = "postgresql+postgis+flask+websocket"
CHARTE_VERSION = "1.0"
TAG = "duolicious/duolicious-backend"
SOURCE_REPO = "https://github.com/duolicious/duolicious-backend"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Duolicious = dating app matching engine.
# Patterns CORE : geospatial search (PostGIS), personality vector similarity,
# rate limiting by verification tier, photo validation, anti-spam/abuse detection.
#
# U-5 : Replace entity names. "person" → "xxx", "prospect" → "xxx_candidate",
# "searcher" → "xxx_seeker", etc. Keep technical terms: latitude, longitude,
# distance, geo, postgis, st_distance, st_dwithin, personality, verification,
# vector, similarity, rate_limit, throttle, spam, rude, photo, block, report.

PATTERNS: list[dict] = [
    # ── 1. Geospatial distance-based search with PostGIS ST_DWithin ─────────────
    {
        "normalized_code": """\
import psycopg

def fetch_xxx_candidates_by_location(
    tx,
    searcher_person_id: int,
    gender_preference: list[int],
    distance_meters: float,
) -> list[dict]:
    \"\"\"Query xxx candidates within distance radius using PostGIS ST_DWithin.

    Returns candidates sorted by personality vector similarity (cosine).
    \"\"\"
    query = '''
    WITH searcher AS (
        SELECT
            coordinates,
            personality,
            gender_id
        FROM person
        WHERE id = %(searcher_person_id)s
    )
    SELECT
        xxx.id AS xxx_candidate_id,
        xxx.uuid,
        xxx.name,
        xxx.personality,
        100 * (1 - (xxx.personality <#> searcher.personality)) / 2 AS compatibility_score
    FROM person AS xxx
    CROSS JOIN searcher
    WHERE
        xxx.activated
    AND
        xxx.gender_id = ANY(%(gender_preference)s::SMALLINT[])
    AND
        ST_DWithin(xxx.coordinates, searcher.coordinates, %(distance_meters)s)
    ORDER BY
        xxx.personality <#> searcher.personality
    LIMIT 10000
    '''
    params = dict(
        searcher_person_id=searcher_person_id,
        gender_preference=gender_preference,
        distance_meters=distance_meters,
    )
    tx.execute(query, params)
    return tx.fetchall()
""",
        "function": "geospatial_xxx_search_postgis_distance",
        "feature_type": "search",
        "file_role": "route",
        "file_path": "service/search/sql/__init__.py",
    },
    # ── 2. Personality vector similarity ranking (pgvector cosine) ──────────────
    {
        "normalized_code": """\
def rank_xxx_by_compatibility(
    tx,
    searcher_personality: list[float],
    xxx_candidates: list[dict],
) -> list[dict]:
    \"\"\"Rank xxx candidates by cosine similarity to searcher personality vector.

    Uses PostgreSQL pgvector <#> operator (cosine distance).
    Lower distance = higher compatibility.
    \"\"\"
    scored = []
    for xxx in xxx_candidates:
        # <#> cosine distance in PG: lower = more similar
        cosine_dist = None
        if 'personality' in xxx:
            # Simulate cosine: 1 - (cosine_dist / 2) for 0-100 scale
            compatibility = 100 * (1 - (cosine_dist / 2)) / 2
        else:
            compatibility = 0
        scored.append({
            'id': xxx['id'],
            'compatibility': compatibility,
        })
    # Sort by compatibility descending
    return sorted(scored, key=lambda x: x['compatibility'], reverse=True)
""",
        "function": "rank_xxx_personality_cosine_similarity",
        "feature_type": "algorithm",
        "file_role": "utility",
        "file_path": "service/search/__init__.py",
    },
    # ── 3. Rate limiting by verification tier + penalties ─────────────────────
    {
        "normalized_code": """\
from enum import Enum
from dataclasses import dataclass

class VerificationTier(Enum):
    UNVERIFIED = 0
    BASICS = 10
    PHOTOS = 20
    FULL = 30


@dataclass(frozen=True)
class RateLimitInfo:
    verification_level_id: int
    daily_xxx_entry_count: int
    recent_reports: int
    recent_rude_count: int


def compute_xxx_rate_limit(info: RateLimitInfo) -> int:
    \"\"\"Compute xxx_entry rate limit based on verification tier + penalties.

    Penalty exponent increases with reports and rude entries.
    Limit = base_limit / 2^penalty_exp.
    \"\"\"
    tier_map = {
        3: VerificationTier.FULL,
        2: VerificationTier.PHOTOS,
        1: VerificationTier.BASICS,
        0: VerificationTier.UNVERIFIED,
    }
    base_limit = tier_map.get(info.verification_level_id, VerificationTier.UNVERIFIED).value

    penalty_exp = 0
    penalty_exp += info.recent_reports
    penalty_exp += info.recent_rude_count // 2

    limit = max(1, base_limit // (2 ** penalty_exp))
    return limit
""",
        "function": "rate_limit_xxx_verification_tier_penalties",
        "feature_type": "security",
        "file_role": "utility",
        "file_path": "service/chat/ratelimit/__init__.py",
    },
    # ── 4. SQL query: Rate limit reason with 24h daily count ────────────────────
    {
        "normalized_code": """\
async def fetch_rate_limit_reason(from_id: int):
    \"\"\"Fetch rate limit info: verification tier, daily xxx count, report count.

    Uses 24h rolling window for daily count.
    Excludes reciprocated conversations.
    \"\"\"
    query = '''
    WITH recent_daily_xxx AS (
        SELECT 1
        FROM xxx_message AS m1
        WHERE
            m1.subject_person_id = %(from_id)s
        AND m1.created_at >= NOW() - INTERVAL '24 HOURS'
        AND NOT EXISTS (
            SELECT 1
            FROM xxx_message AS m2
            WHERE
                m2.subject_person_id = m1.object_person_id
            AND m2.object_person_id = m1.subject_person_id
            AND m2.created_at < m1.created_at
        )
        LIMIT 100
    ),
    recent_reports AS (
        SELECT count(*) FROM report
        WHERE object_person_id = %(from_id)s
        AND created_at > now() - interval '7 days'
        AND reported
    )
    SELECT
        person.verification_level_id,
        (SELECT count(*) FROM recent_daily_xxx) AS daily_xxx_count,
        (SELECT count FROM recent_reports) AS recent_reports,
        count(rude_message.id) AS recent_rude_count
    FROM person
    LEFT JOIN rude_message ON (
        rude_message.person_id = person.id
        AND rude_message.created_at > now() - interval '1 day'
    )
    WHERE person.id = %(from_id)s
    GROUP BY person.id, person.verification_level_id
    '''
    async with api_tx() as tx:
        await tx.execute(query, dict(from_id=from_id))
        return await tx.fetchone()
""",
        "function": "fetch_rate_limit_xxx_24h_window",
        "feature_type": "database",
        "file_role": "utility",
        "file_path": "service/chat/ratelimit/__init__.py",
    },
    # ── 5. Photo processing: EXIF rotation + square crop ─────────────────────────
    {
        "normalized_code": """\
from PIL import Image
from dataclasses import dataclass
import io
from typing import Optional

@dataclass
class CropBox:
    top: int
    left: int


def process_xxx_photo(
    image: Image.Image,
    output_size: Optional[int] = None,
    crop_box: Optional[CropBox] = None,
) -> io.BytesIO:
    \"\"\"Process xxx profile photo: rotate by EXIF, crop to square.

    EXIF codes: 1=normal, 3=180°, 6=90° CW, 8=90° CCW.
    Crop to square using min(width, height).
    \"\"\"
    try:
        exif = image.getexif()
        orientation = exif.get(274)  # 274 = EXIF orientation field
    except Exception:
        orientation = None

    # Rotate based on orientation
    rotation_map = {3: 180, 5: -90, 6: -90, 8: 90}
    if orientation in rotation_map:
        image = image.rotate(rotation_map[orientation], expand=True)

    # Crop to square
    if output_size is not None:
        width, height = image.size
        min_dim = min(width, height)

        if crop_box is None:
            left = (width - min_dim) // 2
            top = (height - min_dim) // 2
        else:
            crop_box.top = max(0, min(height - min_dim, crop_box.top))
            crop_box.left = max(0, min(width - min_dim, crop_box.left))
            left = crop_box.left
            top = crop_box.top

        image = image.crop((left, top, left + min_dim, top + min_dim))
        image = image.resize((output_size, output_size), Image.Resampling.LANCZOS)

    output = io.BytesIO()
    image.save(output, format='JPEG', quality=85)
    output.seek(0)
    return output
""",
        "function": "photo_exif_rotation_square_crop",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "service/person/__init__.py",
    },
    # ── 6. Anti-spam: URL detection with safe-list ─────────────────────────────
    {
        "normalized_code": """\
from enum import Enum
from typing import Tuple, List

class UrlType(Enum):
    VERY_SAFE = "very_safe"
    SAFE = "safe"
    SUSPICIOUS = "suspicious"
    MALICIOUS = "malicious"


def has_url(
    text: str,
    include_safe: bool = False,
    do_normalize: bool = True,
) -> List[Tuple[UrlType, str]]:
    \"\"\"Detect URLs in text and classify by safety.

    Returns list of (url_type, matched_text) tuples.
    Very_safe = whitelisted domains (social media, dating sites).
    Suspicious = no protocol, unusual TLD, or shortener.
    \"\"\"
    very_safe_domains = {
        'instagram.com', 'facebook.com', 'twitter.com',
        'linkedin.com', 'tiktok.com', 'youtube.com',
    }

    suspicious_indicators = {
        '://tiny', '://bit', '://short',  # shorteners
        '://goo.',  # Google shortener
    }

    results = []
    for match in _find_url_matches(text):
        url_str = match.group(0) if hasattr(match, 'group') else match
        url_lower = url_str.lower()

        if any(domain in url_lower for domain in very_safe_domains):
            url_type = UrlType.VERY_SAFE
        elif any(ind in url_lower for ind in suspicious_indicators):
            url_type = UrlType.SUSPICIOUS
        elif url_lower.startswith('http') or '.' in url_lower:
            url_type = UrlType.SAFE
        else:
            url_type = UrlType.MALICIOUS

        results.append((url_type, url_str))

    return results


def is_xxx_entry_spam(text: str) -> bool:
    \"\"\"Check if xxx entry is spam (contains non-safe URLs).\"\"\"
    result = has_url(text, include_safe=True, do_normalize=False)
    if result == [(UrlType.VERY_SAFE, text)]:
        return False
    return has_url(text)
""",
        "function": "spam_url_detection_with_safe_list",
        "feature_type": "security",
        "file_role": "utility",
        "file_path": "service/chat/spam/__init__.py",
    },
    # ── 7. Email validation: normalize dots/pluses + bad domain check ──────────
    {
        "normalized_code": """\
def normalize_email_dots(email: str) -> str:
    \"\"\"Gmail-style: remove dots before @ (dots don't affect delivery).

    example.xxx@gmail.com → examplexxx@gmail.com
    \"\"\"
    local, domain = email.rsplit('@', 1)
    local = local.replace('.', '')
    return f'{local}@{domain}'


def normalize_email_pluses(email: str) -> str:
    \"\"\"Gmail-style: strip plus-addressing (everything after +).

    example+suffix@gmail.com → example@gmail.com
    \"\"\"
    local, domain = email.rsplit('@', 1)
    local = local.split('+')[0]
    return f'{local}@{domain}'


def check_bad_email_domains(email: str) -> bool:
    \"\"\"Check if email domain is in spam/disposable domain list.

    Prevents abuse via temp email services.
    \"\"\"
    bad_domains = {
        'tempmail.com', 'guerrillamail.com', '10minutemail.com',
        'throwaway.email', 'maildrop.cc',
    }
    domain = email.rsplit('@', 1)[1].lower()
    return domain in bad_domains


def normalize_email_for_xxx_signup(email: str) -> str:
    \"\"\"Normalize xxx signup email to prevent duplicate accounts.

    1. Lowercase
    2. Remove dots (Gmail)
    3. Remove pluses (Gmail suffixes)
    4. Normalize domain (outlook aliases)
    \"\"\"
    email = email.lower().strip()
    email = normalize_email_dots(email)
    email = normalize_email_pluses(email)

    # Normalize Outlook aliases
    local, domain = email.rsplit('@', 1)
    if domain.startswith('outlook.') or domain.startswith('hotmail.'):
        domain = 'outlook.com'
    email = f'{local}@{domain}'

    return email
""",
        "function": "xxx_email_normalization_spam_check",
        "feature_type": "security",
        "file_role": "utility",
        "file_path": "antiabuse/antispam/signupemail/__init__.py",
    },
    # ── 8. Rude content detection: pattern-based filtering ────────────────────
    {
        "normalized_code": """\
import re

class RudeContentChecker:
    \"\"\"Detect rude/offensive content in xxx profiles or entries.\"\"\"

    def __init__(self):
        # Example patterns: sexual references, slurs, aggressive language
        self.rude_patterns = [
            r'\\b(sex|xxx|adult)\\b',
            r'\\b(hate|kill|die)\\b',
            r'\\b(scam|fake|catfish)\\b',
        ]
        self.compiled = [re.compile(p, re.IGNORECASE) for p in self.rude_patterns]

    def is_rude_displayname(self, name: str) -> bool:
        \"\"\"Check if xxx display name is rude.\"\"\"
        if len(name) < 1:
            return False
        for compiled_re in self.compiled:
            if compiled_re.search(name):
                return True
        return False

    def is_rude_profile(self, profile_text: str) -> bool:
        \"\"\"Check if xxx profile about/interests contain rude content.\"\"\"
        for compiled_re in self.compiled:
            if compiled_re.search(profile_text):
                return True
        return False

    def is_rude_entry(self, text: str) -> bool:
        \"\"\"Check if xxx entry is rude.\"\"\"
        for compiled_re in self.compiled:
            if compiled_re.search(text):
                return True
        return False


checker = RudeContentChecker()
""",
        "function": "rude_content_detection_profile_message",
        "feature_type": "security",
        "file_role": "utility",
        "file_path": "antiabuse/antirude/__init__.py",
    },
    # ── 9. Location search: fuzzy matching by first character + distance operator
    {
        "normalized_code": """\
from functools import lru_cache

@lru_cache(maxsize=26**3)
def search_xxx_locations(query: str | None) -> list[str]:
    \"\"\"Search locations by prefix + PostgreSQL <-> distance operator.

    Uses ILIKE with first character filter for performance.
    Sorts by string distance operator (<->) for typo tolerance.
    \"\"\"
    if query is None or len(query.strip()) < 1:
        return []

    normalized_q = ' '.join(query.split())
    first_char = normalized_q[0]

    sql_query = '''
    SELECT long_friendly
    FROM location
    WHERE long_friendly ILIKE %(first_char)s || '%%'
    ORDER BY long_friendly <-> %(search_string)s
    LIMIT 10
    '''

    params = dict(
        first_char=first_char,
        search_string=normalized_q,
    )

    # Execute with READ COMMITTED isolation to avoid locks
    with api_tx('READ COMMITTED') as tx:
        tx.execute(sql_query, params)
        results = [row['long_friendly'] for row in tx.fetchall()]

    return results
""",
        "function": "location_xxx_search_fuzzy_prefix",
        "feature_type": "search",
        "file_role": "utility",
        "file_path": "service/location/__init__.py",
    },
    # ── 10. Personality vector initialization (random for new xxx) ───────────────
    {
        "normalized_code": """\
import numpy as np
from typing import List

def initialize_xxx_personality_vector() -> List[float]:
    \"\"\"Initialize random personality vector for new xxx.

    Default: random unit vector in high-dimensional space.
    Later: updated by questionnaire answers.
    \"\"\"
    # Dimension = typical pgvector size for compatibility
    dim = 256
    vector = np.random.randn(dim).astype(np.float32)
    # Normalize to unit vector
    vector = vector / np.linalg.norm(vector)
    return vector.tolist()


def update_xxx_personality_from_answers(
    xxx_id: int,
    answer_vector: List[float],
) -> None:
    \"\"\"Update xxx personality vector based on quiz answers.

    Blends existing vector with answer vector (weighted by answer count).
    \"\"\"
    query = '''
    UPDATE person
    SET personality = (
        (personality * count_answers + %(answer_vector)s::vector) /
        (count_answers + 1)::float8
    ),
    count_answers = count_answers + 1
    WHERE id = %(xxx_id)s
    '''
    with api_tx() as tx:
        tx.execute(query, dict(xxx_id=xxx_id, answer_vector=answer_vector))
""",
        "function": "personality_vector_init_quiz_update",
        "feature_type": "model",
        "file_role": "utility",
        "file_path": "service/person/__init__.py",
    },
    # ── 11. Block/report xxx with transactional consistency ───────────────────
    {
        "normalized_code": """\
from enum import Enum

class ReportReason(Enum):
    FAKE_PROFILE = 1
    INAPPROPRIATE_CONTENT = 2
    HARASSMENT = 3
    CATFISH = 4
    SPAM = 5


async def report_and_block_xxx(
    reporter_id: int,
    reported_id: int,
    reason: ReportReason,
) -> bool:
    \"\"\"Report and optionally block xxx (transactional).

    Steps:
    1. Insert report record
    2. Insert block record
    3. Check if both succeed
    \"\"\"
    query_report = '''
    INSERT INTO report (reporter_person_id, object_person_id, reason_id, created_at)
    VALUES (%(reporter_id)s, %(reported_id)s, %(reason)s, NOW())
    ON CONFLICT DO NOTHING
    '''

    query_block = '''
    INSERT INTO block (blocker_person_id, blocked_person_id, created_at)
    VALUES (%(reporter_id)s, %(reported_id)s, NOW())
    ON CONFLICT DO NOTHING
    '''

    async with api_tx() as tx:
        await tx.execute(query_report, dict(
            reporter_id=reporter_id,
            reported_id=reported_id,
            reason=reason.value,
        ))
        await tx.execute(query_block, dict(
            reporter_id=reporter_id,
            reported_id=reported_id,
        ))

    return True
""",
        "function": "report_block_xxx_transactional",
        "feature_type": "security",
        "file_role": "utility",
        "file_path": "antiabuse/lodgereport/__init__.py",
    },
    # ── 12. Verification status enum + XXX visibility rules ─────────────────────
    {
        "normalized_code": """\
from enum import IntEnum

class VerificationStatus(IntEnum):
    UNVERIFIED = 0
    BASIC_INFO = 1
    PHOTO_VERIFIED = 2
    FULL_VERIFIED = 3


def can_xxx_see_xxx(
    viewer_verification: VerificationStatus,
    target_verification: VerificationStatus,
    age_difference: int,
) -> bool:
    \"\"\"Visibility rules: verified xxs can see others; age gap limits.\"\"\"
    # Unverified can only see other unverified
    if viewer_verification == VerificationStatus.UNVERIFIED:
        return target_verification == VerificationStatus.UNVERIFIED

    # Verified can see all (with age gap checks)
    max_age_gap = {
        VerificationStatus.BASIC_INFO: 20,
        VerificationStatus.PHOTO_VERIFIED: 25,
        VerificationStatus.FULL_VERIFIED: 50,
    }

    return age_difference <= max_age_gap.get(viewer_verification, 20)


def get_xxx_profile_visibility_score(
    xxx_verification: VerificationStatus,
) -> float:
    \"\"\"Return visibility boost factor based on verification tier.

    Higher verification = appear higher in search results.
    \"\"\"
    visibility_map = {
        VerificationStatus.UNVERIFIED: 0.5,
        VerificationStatus.BASIC_INFO: 0.75,
        VerificationStatus.PHOTO_VERIFIED: 1.0,
        VerificationStatus.FULL_VERIFIED: 1.5,
    }
    return visibility_map.get(xxx_verification, 0.5)
""",
        "function": "xxx_verification_visibility_rules",
        "feature_type": "policy",
        "file_role": "utility",
        "file_path": "verification/__init__.py",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "geospatial distance search PostGIS ST_DWithin dating matching",
    "personality vector cosine similarity ranking compatibility",
    "rate limiting by verification tier with penalties",
    "photo processing EXIF rotation square crop",
    "anti-spam URL detection with safe-list",
    "email normalization dots pluses disposable domains",
    "rude content detection profile message",
    "location fuzzy search first character prefix",
    "personality vector initialization questionnaire",
    "report block user transactional consistency",
    "verification status visibility rules age gap",
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
