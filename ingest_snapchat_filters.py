"""
ingest_snapchat_filters.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de charlielito/snapchat-filters-opencv dans la KB Qdrant V6.

Focus : CORE computer vision patterns (face detection, landmark detection, overlay,
color space, masking, alpha blending, real-time camera loops).

PAS des patterns CRUD/API — patterns de traitement d'images et vidéo.

Usage:
    .venv/bin/python3 ingest_snapchat_filters.py
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
REPO_URL = "https://github.com/charlielito/snapchat-filters-opencv.git"
REPO_NAME = "charlielito/snapchat-filters-opencv"
REPO_LOCAL = "/tmp/snapchat-filters-opencv"
LANGUAGE = "python"
FRAMEWORK = "generic"
STACK = "python+opencv+dlib+numpy"
CHARTE_VERSION = "1.0"
TAG = "charlielito/snapchat-filters-opencv"
SOURCE_REPO = "https://github.com/charlielito/snapchat-filters-opencv"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Snapchat filters = real-time face detection and overlay via OpenCV + dlib.
# Patterns CORE : face detection, landmark detection, alpha blending, color space,
# region of interest (ROI) extraction, contour/convex hull, morphological operations.

PATTERNS: list[dict] = [
    # ── 1. Haar cascade face detection pipeline ────────────────────────────────
    {
        "normalized_code": """\
import cv2
import numpy as np


def apply_haar_filter(
    img: np.ndarray,
    haar_cascade: cv2.CascadeClassifier,
    scale_factor: float = 1.1,
    min_neighbors: int = 5,
    min_size_width: int = 30,
) -> np.ndarray:
    \"\"\"Detect objects (faces, eyes, etc.) using Haar cascade classifier.

    Args:
        img: BGR image as numpy array
        haar_cascade: cv2.CascadeClassifier loaded with XML cascade
        scale_factor: scale factor for image pyramid (1.05-1.4, higher=faster but less accurate)
        min_neighbors: minimum neighbors for cascade (4-6 typical)
        min_size_width: minimum detection size (square dimension)

    Returns:
        Array of (x, y, w, h) bounding boxes for detected objects
    \"\"\"
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    features = haar_cascade.detectMultiScale(
        gray,
        scaleFactor=scale_factor,
        minNeighbors=min_neighbors,
        minSize=(min_size_width, min_size_width),
        flags=cv2.CASCADE_SCALE_IMAGE,
    )
    return features
""",
        "function": "haar_cascade_face_detect",
        "feature_type": "detection",
        "file_role": "utility",
        "file_path": "main.py",
    },
    # ── 2. Alpha blending sprite overlay ───────────────────────────────────────
    {
        "normalized_code": """\
import cv2
import numpy as np


def draw_sprite(
    frame: np.ndarray,
    sprite: np.ndarray,
    x_offset: int,
    y_offset: int,
) -> np.ndarray:
    \"\"\"Overlay sprite with alpha channel onto frame using alpha blending.

    Handles boundary conditions (sprite extends beyond frame edges).
    Uses alpha channel (channel 3) as transparency mask: 255=opaque, 0=transparent.

    Args:
        frame: target BGR image (3 channels)
        sprite: BGRA image (4 channels, alpha in [3])
        x_offset: x position in frame
        y_offset: y position in frame

    Returns:
        Frame with sprite blended at (x_offset, y_offset)
    \"\"\"
    h_sprite, w_sprite = sprite.shape[0], sprite.shape[1]
    h_frame, w_frame = frame.shape[0], frame.shape[1]

    if y_offset + h_sprite >= h_frame:
        sprite = sprite[0 : h_frame - y_offset, :, :]

    if x_offset + w_sprite >= w_frame:
        sprite = sprite[:, 0 : w_frame - x_offset, :]

    if x_offset < 0:
        sprite = sprite[:, abs(x_offset) :, :]
        w_sprite = sprite.shape[1]
        x_offset = 0

    h_sprite, w_sprite = sprite.shape[0], sprite.shape[1]

    for channel in range(3):
        alpha = sprite[:, :, 3] / 255.0
        frame[
            y_offset : y_offset + h_sprite,
            x_offset : x_offset + w_sprite,
            channel,
        ] = (
            sprite[:, :, channel] * alpha
            + frame[
                y_offset : y_offset + h_sprite,
                x_offset : x_offset + w_sprite,
                channel,
            ]
            * (1.0 - alpha)
        )

    return frame
""",
        "function": "alpha_blending_sprite_overlay",
        "feature_type": "composite",
        "file_role": "utility",
        "file_path": "main.py",
    },
    # ── 3. Sprite resize and position adjustment ──────────────────────────────
    {
        "normalized_code": """\
import cv2
import numpy as np


def adjust_sprite_to_bbox(
    sprite: np.ndarray,
    bbox_width: int,
    bbox_y_pos: int,
) -> tuple[np.ndarray, int]:
    \"\"\"Resize sprite to match bounding box width and adjust position.

    Handles clipping when sprite extends above frame boundary.

    Args:
        sprite: BGRA image to scale
        bbox_width: target width (scale sprite proportionally)
        bbox_y_pos: y position of bounding box in frame

    Returns:
        Tuple of (resized_sprite, adjusted_y_position)
    \"\"\"
    h_sprite, w_sprite = sprite.shape[0], sprite.shape[1]
    scale_factor = float(bbox_width) / w_sprite
    sprite = cv2.resize(sprite, (0, 0), fx=scale_factor, fy=scale_factor)

    h_sprite, w_sprite = sprite.shape[0], sprite.shape[1]
    y_origin = bbox_y_pos - h_sprite

    if y_origin < 0:
        sprite = sprite[abs(y_origin) :, :, :]
        y_origin = 0

    return sprite, y_origin
""",
        "function": "sprite_resize_and_position",
        "feature_type": "transform",
        "file_role": "utility",
        "file_path": "main.py",
    },
    # ── 4. dlib facial landmark detection ──────────────────────────────────────
    {
        "normalized_code": """\
import cv2
import numpy as np
import dlib
from imutils import face_utils


def detect_facial_landmarks(
    frame: np.ndarray,
    detector: dlib.fhog_object_detector,
    predictor: dlib.shape_predictor,
) -> tuple[list[dlib.rectangle], list[np.ndarray]]:
    \"\"\"Detect faces and extract 68-point facial landmarks using dlib.

    Args:
        frame: BGR input frame
        detector: dlib.get_frontal_face_detector()
        predictor: dlib.shape_predictor (68-point model)

    Returns:
        Tuple of (face_rectangles, landmarks_arrays) where each landmark
        is shape (68, 2) numpy array of (x, y) points
    \"\"\"
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    rects = detector(gray, 0)

    landmarks_list = []
    for rect in rects:
        shape = predictor(gray, rect)
        shape = face_utils.shape_to_np(shape)
        landmarks_list.append(shape)

    return rects, landmarks_list
""",
        "function": "dlib_facial_landmark_detect",
        "feature_type": "detection",
        "file_role": "utility",
        "file_path": "facial_landmarks.py",
    },
    # ── 5. Calculate inclination angle between two points ──────────────────────
    {
        "normalized_code": """\
import math


def calculate_inclination(
    point1: tuple[float, float],
    point2: tuple[float, float],
) -> float:
    \"\"\"Calculate rotation angle between two points (degrees).

    Used for aligning overlays (e.g., rotating hat to match head tilt).

    Args:
        point1: (x, y) tuple
        point2: (x, y) tuple

    Returns:
        Angle in degrees
    \"\"\"
    x1, y1 = point1[0], point1[1]
    x2, y2 = point2[0], point2[1]
    incl = -180.0 / math.pi * math.atan((float(y2 - y1)) / (x2 - x1))
    return incl
""",
        "function": "point_inclination_angle",
        "feature_type": "geometry",
        "file_role": "utility",
        "file_path": "facial_landmarks.py",
    },
    # ── 6. Compute bounding box from landmark points ──────────────────────────
    {
        "normalized_code": """\
import numpy as np


def calculate_boundbox(points: np.ndarray) -> tuple[int, int, int, int]:
    \"\"\"Compute (x, y, w, h) bounding box from set of (x, y) points.

    Used to extract regions around eyes, nose, mouth from landmark array.

    Args:
        points: shape (n, 2) array of (x, y) coordinates

    Returns:
        Tuple (x, y, w, h) of bounding box
    \"\"\"
    x = int(np.min(points[:, 0]))
    y = int(np.min(points[:, 1]))
    w = int(np.max(points[:, 0]) - x)
    h = int(np.max(points[:, 1]) - y)
    return x, y, w, h


def extract_face_region(
    points: np.ndarray,
    region_type: int,
) -> tuple[int, int, int, int]:
    \"\"\"Extract bounding box for specific facial region from 68-point landmarks.

    Region mapping:
        1: left eyebrow (points 17-22)
        2: right eyebrow (points 22-27)
        3: left eye (points 36-42)
        4: right eye (points 42-48)
        5: nose (points 29-36)
        6: mouth (points 48-68)

    Args:
        points: shape (68, 2) landmark array
        region_type: integer 1-6 for region selection

    Returns:
        (x, y, w, h) bounding box for region
    \"\"\"
    if region_type == 1:
        region_points = points[17:22]
    elif region_type == 2:
        region_points = points[22:27]
    elif region_type == 3:
        region_points = points[36:42]
    elif region_type == 4:
        region_points = points[42:48]
    elif region_type == 5:
        region_points = points[29:36]
    elif region_type == 6:
        region_points = points[48:68]
    else:
        return 0, 0, 0, 0

    return calculate_boundbox(region_points)
""",
        "function": "landmark_boundbox_extraction",
        "feature_type": "geometry",
        "file_role": "utility",
        "file_path": "facial_landmarks.py",
    },
    # ── 7. Real-time video capture and frame processing loop ──────────────────
    {
        "normalized_code": """\
import cv2
import numpy as np


def video_capture_loop(
    frame_callback,
    camera_id: int = 0,
    should_continue: bool = True,
) -> None:
    \"\"\"Real-time camera capture loop with frame processing.

    Reads frames from webcam at camera_id and applies callback function
    to each frame. Handles frame read errors and cleanup on exit.

    Args:
        frame_callback: function(frame: np.ndarray) -> None
        camera_id: camera device index (default 0 for primary camera)
        should_continue: loop control flag for continuous capture
    \"\"\"
    cap = cv2.VideoCapture(camera_id)

    try:
        while should_continue:
            ret, frame = cap.read()

            if not ret:
                break

            frame_callback(frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
""",
        "function": "realtime_video_capture_loop",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "main.py",
    },
    # ── 8. Color space conversion (BGR to HSV for color detection) ───────────
    {
        "normalized_code": """\
import cv2
import numpy as np


def detect_color_range(
    frame: np.ndarray,
    lower_bound: np.ndarray,
    upper_bound: np.ndarray,
) -> np.ndarray:
    \"\"\"Detect pixels within color range using HSV color space.

    More robust to lighting variations than RGB/BGR.
    Useful for segmentation operations (e.g., detect red cloth for invisibility cloak).

    Args:
        frame: BGR input frame
        lower_bound: lower HSV threshold [H, S, V] (e.g., [0, 120, 70])
        upper_bound: upper HSV threshold [H, S, V] (e.g., [10, 255, 255])

    Returns:
        Binary mask where detected colors are 255, others are 0
    \"\"\"
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, lower_bound, upper_bound)
    return mask
""",
        "function": "hsv_color_range_detect",
        "feature_type": "segmentation",
        "file_role": "utility",
        "file_path": "scripts/invisibility_cloak.py",
    },
    # ── 9. Morphological operations (open, dilate, erode) ────────────────────
    {
        "normalized_code": """\
import cv2
import numpy as np


def morphological_cleanup(
    mask: np.ndarray,
    kernel_size: tuple[int, int] = (3, 3),
) -> np.ndarray:
    \"\"\"Apply morphological operations to clean binary mask.

    Removes noise (open) and connects broken regions (dilate).
    Typical sequence: open (remove small noise) → dilate (fill gaps).

    Args:
        mask: binary mask (single channel, uint8)
        kernel_size: morphological kernel size (odd number)

    Returns:
        Cleaned binary mask
    \"\"\"
    kernel = np.ones(kernel_size, np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_DILATE, kernel)
    return mask
""",
        "function": "morphological_cleanup_mask",
        "feature_type": "filter",
        "file_role": "utility",
        "file_path": "scripts/invisibility_cloak.py",
    },
    # ── 10. Convex hull and contour drawing ──────────────────────────────────
    {
        "normalized_code": """\
import cv2
import numpy as np


def extract_contour_hull(
    landmarks: np.ndarray,
    frame: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    \"\"\"Convert landmark points to convex hull and create binary mask.

    Used to isolate face region or other polygonal areas.

    Args:
        landmarks: shape (n, 2) landmark points
        frame: frame for mask dimensions

    Returns:
        Tuple of (convex_hull, binary_mask)
    \"\"\"
    hull = cv2.convexHull(landmarks)

    mask = np.zeros(frame.shape[:2], dtype=np.uint8)
    cv2.drawContours(mask, [hull], -1, 255, -1)

    return hull, mask
""",
        "function": "contour_hull_mask_extraction",
        "feature_type": "segmentation",
        "file_role": "utility",
        "file_path": "scripts/blur_face.py",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "Haar cascade face detection with scale factor",
    "alpha blending sprite overlay BGRA transparency",
    "sprite resize and adjust position bounding box",
    "dlib facial landmark detection 68 points",
    "calculate angle inclination between points",
    "bounding box extraction from landmark points",
    "real-time video capture webcam loop",
    "HSV color space range detection segmentation",
    "morphological operations open dilate erode",
    "convex hull contour mask extraction face",
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
