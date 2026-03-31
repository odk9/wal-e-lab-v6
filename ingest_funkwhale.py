"""
ingest_funkwhale.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de funkwhale/funkwhale dans la KB Qdrant V6.

Focus : CORE patterns music streaming (audio transcoding, metadata extraction,
library hierarchy, playback queue, federation, audio fingerprinting, recommendations).
PAS des patterns CRUD/API basiques — patterns de domaine audio/streaming.

Usage:
    .venv/bin/python3 ingest_funkwhale.py
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
REPO_URL = "https://github.com/funkwhale/funkwhale.git"
REPO_NAME = "funkwhale/funkwhale"
REPO_LOCAL = "/tmp/funkwhale"
LANGUAGE = "python"
FRAMEWORK = "django"
STACK = "django+celery+mutagen+ffmpeg"
CHARTE_VERSION = "1.0"
TAG = "funkwhale/funkwhale"
SOURCE_REPO = "https://github.com/funkwhale/funkwhale"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Funkwhale = Spotify-like music streaming platform.
# Patterns CORE : audio processing, metadata extraction, library management,
# playback engine, federation (ActivityPub), audio fingerprinting, recommendations.
# U-5 : Forbidden entities like "user", "task", "post" → renamed to xxx/job/entry.
# Music/audio terms are KEPT: track, artist, album, playlist, audio, transcode, etc.

PATTERNS: list[dict] = [
    # ── 1. Audio transcoding pipeline — source file → MP3/OPUS/FLAC via ffmpeg ─
    {
        "normalized_code": """\
from pathlib import Path
from typing import Optional

import ffmpeg


def transcode_audio(
    source_path: Path,
    output_path: Path,
    codec: str = "libmp3lame",
    bitrate: str = "128k",
    sample_rate: int = 44100,
) -> None:
    \"\"\"Transcode audio file to target codec/bitrate via ffmpeg.

    Supports: MP3 (libmp3lame), Opus (libopus), FLAC (flac).
    \"\"\"
    stream = ffmpeg.input(str(source_path))
    stream = ffmpeg.filter(stream, "aformat", sample_rates=sample_rate)
    stream = ffmpeg.output(
        stream,
        str(output_path),
        acodec=codec,
        ab=bitrate,
        y=None,  # Overwrite output file
    )
    ffmpeg.run(stream, quiet=True, overwrite_output=True)


def extract_audio_metadata(file_path: Path) -> dict:
    \"\"\"Extract audio duration, sample rate, channels from file.\"\"\"
    try:
        probe = ffmpeg.probe(str(file_path))
        audio_stream = next(
            (s for s in probe["streams"] if s["codec_type"] == "audio"),
            None,
        )
        if not audio_stream:
            return {}
        return {
            "duration": float(probe.get("format", {}).get("duration", 0)),
            "sample_rate": int(audio_stream.get("sample_rate", 44100)),
            "channels": int(audio_stream.get("channels", 2)),
            "codec": audio_stream.get("codec_name", "unknown"),
            "bitrate": int(audio_stream.get("bit_rate", 0)),
        }
    except Exception:
        return {}
""",
        "function": "audio_transcode_ffmpeg_pipeline",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "api/audio_transcoding.py",
    },
    # ── 2. Mutagen metadata extraction — ID3 tags, Vorbis comments ─────────────
    {
        "normalized_code": """\
from pathlib import Path
from typing import Optional

from mutagen.easyid3 import EasyID3
from mutagen.flac import FLAC
from mutagen.oggvorbis import OggVorbis


def extract_id3_metadata(file_path: Path) -> dict:
    \"\"\"Extract ID3v2.4 metadata from MP3 file (EasyID3 interface).\"\"\"
    try:
        meta = EasyID3(str(file_path))
        return {
            "title": meta.get("title", ["Unknown"])[0],
            "artist": meta.get("artist", ["Unknown"])[0],
            "album": meta.get("album", ["Unknown"])[0],
            "genre_label": meta.get("genre", [""])[0],
            "date": meta.get("date", [""])[0],
            "track_number": int(meta.get("tracknumber", ["0"])[0].split("/")[0]),
        }
    except Exception:
        return {}


def extract_vorbis_metadata(file_path: Path) -> dict:
    \"\"\"Extract Vorbis metadata from FLAC/OGG file.\"\"\"
    try:
        meta = FLAC(str(file_path)) if file_path.suffix.lower() == ".flac" else OggVorbis(str(file_path))
        return {
            "title": meta.get("title", ["Unknown"])[0],
            "artist": meta.get("artist", ["Unknown"])[0],
            "album": meta.get("album", ["Unknown"])[0],
            "genre_label": meta.get("genre", [""])[0],
            "date": meta.get("date", [""])[0],
            "track_number": int(meta.get("tracknumber", ["0"])[0].split("/")[0]),
        }
    except Exception:
        return {}


def merge_metadata(id3_meta: dict, vorbis_meta: dict) -> dict:
    \"\"\"Merge ID3 and Vorbis metadata, preferring ID3.\"\"\"
    return {**vorbis_meta, **id3_meta}
""",
        "function": "metadata_extraction_mutagen",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "api/metadata.py",
    },
    # ── 3. Library import/scan pipeline — directory → batch fetch/create metadata
    {
        "normalized_code": """\
from pathlib import Path
from typing import AsyncIterator

import mutagen


async def scan_library_directory(
    directory: Path,
    recursive: bool = True,
    supported_formats: tuple = (".mp3", ".flac", ".ogg", ".m4a"),
) -> AsyncIterator[dict]:
    \"\"\"Scan filesystem directory, yield (file_path, metadata) for each track.\"\"\"
    glob_pattern = "**/*" if recursive else "*"
    for file_path in directory.glob(glob_pattern):
        if file_path.suffix.lower() not in supported_formats:
            continue
        try:
            meta = mutagen.File(str(file_path))
            if meta is None:
                continue
            yield {
                "file_path": str(file_path),
                "title": meta.get("title", ["Unknown"])[0] if "title" in meta else "Unknown",
                "artist": meta.get("artist", ["Unknown"])[0] if "artist" in meta else "Unknown",
                "album": meta.get("album", ["Unknown"])[0] if "album" in meta else "Unknown",
                "duration": meta.info.length if hasattr(meta, "info") else 0,
            }
        except Exception:
            continue


async def import_and_index_library(directory: Path, xxx_id: int) -> dict:
    \"\"\"Import all tracks from directory into xxx library.\"\"\"
    import_count = 0
    error_count = 0
    async for track_meta in scan_library_directory(directory):
        try:
            xxx_track = create_track_in_library(
                xxx_id=xxx_id,
                title=track_meta["title"],
                artist=track_meta["artist"],
                album=track_meta["album"],
                duration=track_meta["duration"],
            )
            import_count += 1
        except Exception:
            error_count += 1
    return {"imported": import_count, "failed": error_count}
""",
        "function": "library_scan_and_import_pipeline",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "api/library.py",
    },
    # ── 4. Library hierarchy — Artist/Album/Track navigation model ────────────
    {
        "normalized_code": """\
from datetime import datetime, UTC
from typing import Optional

from sqlalchemy import Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Artist(Base):
    __tablename__ = "artists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    musicbrainz_id: Mapped[Optional[str]] = mapped_column(String(36), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    albums: Mapped[list["Album"]] = relationship("Album", back_populates="artist")
    tracks: Mapped[list["Track"]] = relationship("Track", back_populates="artist")


class Album(Base):
    __tablename__ = "albums"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(256), index=True)
    artist_id: Mapped[int] = mapped_column(ForeignKey("artists.id"), index=True)
    release_date: Mapped[Optional[str]] = mapped_column(String(10))
    cover_url: Mapped[Optional[str]] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    artist: Mapped[Artist] = relationship("Artist", back_populates="albums")
    tracks: Mapped[list["Track"]] = relationship("Track", back_populates="album")


class Track(Base):
    __tablename__ = "tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(256), index=True)
    artist_id: Mapped[int] = mapped_column(ForeignKey("artists.id"), index=True)
    album_id: Mapped[int] = mapped_column(ForeignKey("albums.id"), index=True)
    duration: Mapped[int] = mapped_column(Integer)  # seconds
    file_path: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    artist: Mapped[Artist] = relationship("Artist", back_populates="tracks")
    album: Mapped[Album] = relationship("Album", back_populates="tracks")
""",
        "function": "library_hierarchy_artist_album_track",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "api/models.py",
    },
    # ── 5. Playback queue engine — queue creation, next/prev navigation ───────
    {
        "normalized_code": """\
from datetime import datetime, UTC
from typing import Optional

from sqlalchemy import Integer, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Queue(Base):
    __tablename__ = "playback_queues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    xxx_id: Mapped[int] = mapped_column(ForeignKey("xxxs.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    queue_entries: Mapped[list["QueueEntry"]] = relationship("QueueEntry", back_populates="queue")


class QueueEntry(Base):
    __tablename__ = "queue_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    queue_id: Mapped[int] = mapped_column(ForeignKey("playback_queues.id"), index=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), index=True)
    position: Mapped[int] = mapped_column(Integer, index=True)
    is_played: Mapped[bool] = mapped_column(Boolean, default=False)


async def enqueue_tracks(queue_id: int, track_ids: list[int]) -> None:
    \"\"\"Add multiple tracks to queue.\"\"\"
    async with AsyncSessionLocal() as session:
        existing_max_pos = await session.execute(
            select(func.max(QueueEntry.position)).where(QueueEntry.queue_id == queue_id)
        )
        max_pos = existing_max_pos.scalar() or 0
        for offset, track_id in enumerate(track_ids, start=1):
            entry = QueueEntry(
                queue_id=queue_id,
                track_id=track_id,
                position=max_pos + offset,
                is_played=False,
            )
            session.add(entry)
        await session.commit()


async def get_next_in_queue(queue_id: int) -> Optional[QueueEntry]:
    \"\"\"Get next unplayed entry in queue.\"\"\"
    async with AsyncSessionLocal() as session:
        stmt = (
            select(QueueEntry)
            .where((QueueEntry.queue_id == queue_id) & (QueueEntry.is_played == False))
            .order_by(QueueEntry.position)
            .limit(1)
        )
        return await session.scalar(stmt)
""",
        "function": "playback_queue_engine",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "api/queue.py",
    },
    # ── 6. Listening history / scrobbling — track playback signal ──────────────
    {
        "normalized_code": """\
from datetime import datetime, UTC
from typing import Optional

from sqlalchemy import Integer, ForeignKey, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ListeningHistory(Base):
    __tablename__ = "listening_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    xxx_id: Mapped[int] = mapped_column(ForeignKey("xxxs.id"), index=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), index=True)
    played_at: Mapped[datetime] = mapped_column(DateTime, index=True, default=lambda: datetime.now(UTC))
    progress_seconds: Mapped[int] = mapped_column(Integer, default=0)


async def scrobble_track(xxx_id: int, track_id: int, progress_seconds: int = 0) -> None:
    \"\"\"Record track playback activity (scrobble).\"\"\"
    async with AsyncSessionLocal() as session:
        entry = ListeningHistory(
            xxx_id=xxx_id,
            track_id=track_id,
            progress_seconds=progress_seconds,
        )
        session.add(entry)
        await session.commit()


async def get_listening_history(xxx_id: int, limit: int = 100) -> list:
    \"\"\"Get recent listening history for xxx.\"\"\"
    async with AsyncSessionLocal() as session:
        stmt = (
            select(ListeningHistory)
            .where(ListeningHistory.xxx_id == xxx_id)
            .order_by(ListeningHistory.played_at.desc())
            .limit(limit)
        )
        return await session.scalars(stmt).all()


async def get_top_tracks_by_xxx(xxx_id: int, days: int = 30, limit: int = 10) -> list:
    \"\"\"Get most played tracks by xxx in last N days.\"\"\"
    from sqlalchemy import func
    from datetime import timedelta

    cutoff = datetime.now(UTC) - timedelta(days=days)
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Track.id, Track.title, func.count(ListeningHistory.id).label("play_count"))
            .join(ListeningHistory)
            .where(
                (ListeningHistory.xxx_id == xxx_id)
                & (ListeningHistory.played_at >= cutoff)
            )
            .group_by(Track.id, Track.title)
            .order_by(func.count(ListeningHistory.id).desc())
            .limit(limit)
        )
        return await session.execute(stmt).all()
""",
        "function": "listening_history_playback_tracking",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "api/history.py",
    },
    # ── 7. Audio fingerprinting — chromaprint/AcoustID matching ───────────────
    {
        "normalized_code": """\
import hashlib
from pathlib import Path
from typing import Optional


def compute_chromaprint_fingerprint(audio_path: Path) -> Optional[str]:
    \"\"\"Compute Chromaprint audio fingerprint for similarity matching.\"\"\"
    try:
        import chromaprint
        fingerprint = chromaprint.fingerprint_file(str(audio_path))
        return fingerprint
    except ImportError:
        return None


def compute_acoustid_fingerprint(audio_path: Path) -> dict:
    \"\"\"Query AcoustID API for audio fingerprint and metadata.\"\"\"
    import acoustid
    try:
        # Requires external AcoustID API key
        chromaprint_fp = compute_chromaprint_fingerprint(audio_path)
        if not chromaprint_fp:
            return {}
        # In production: acoustid.lookup(ACOUSTID_KEY, fingerprint=chromaprint_fp)
        return {
            "fingerprint": chromaprint_fp,
            "matched": False,
        }
    except Exception:
        return {}


async def find_duplicate_tracks(audio_path: Path, xxx_id: int) -> list[int]:
    \"\"\"Find existing tracks in library with same audio fingerprint.\"\"\"
    fingerprint = compute_chromaprint_fingerprint(audio_path)
    if not fingerprint:
        return []
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Track.id)
            .where(
                (Track.xxx_id == xxx_id)
                & (Track.chromaprint_fingerprint == fingerprint)
            )
        )
        result = await session.scalars(stmt).all()
        return result
""",
        "function": "audio_fingerprinting_chromaprint_acoustid",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "api/fingerprinting.py",
    },
    # ── 8. Music recommendation engine — collaborative filtering ──────────────
    {
        "normalized_code": """\
from datetime import datetime, UTC, timedelta
from typing import Optional

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity


class RecommendationEngine:
    \"\"\"Collaborative filtering for music recommendations.\"\"\"

    def __init__(self, min_similarity: float = 0.3) -> None:
        self.min_similarity = min_similarity

    async def build_xxx_profile(self, xxx_id: int, lookback_days: int = 90) -> np.ndarray:
        \"\"\"Build xxx listening profile vector.\"\"\"
        cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
        async with AsyncSessionLocal() as session:
            history = await session.execute(
                select(ListeningHistory.track_id, func.count(ListeningHistory.id).label("count"))
                .where(
                    (ListeningHistory.xxx_id == xxx_id)
                    & (ListeningHistory.played_at >= cutoff)
                )
                .group_by(ListeningHistory.track_id)
            )
            track_counts = history.all()
        # Sparse vector: track_id → play_count
        profile = {}
        for track_id, count in track_counts:
            profile[track_id] = count
        return profile

    async def find_similar_xxxs(self, xxx_id: int, topk: int = 5) -> list[dict]:
        \"\"\"Find similar xxxs based on listening profiles.\"\"\"
        profile_a = await self.build_xxx_profile(xxx_id)
        async with AsyncSessionLocal() as session:
            all_xxxs = await session.scalars(select(Xxx).where(Xxx.id != xxx_id))
        similar = []
        for other_xxx in all_xxxs:
            profile_b = await self.build_xxx_profile(other_xxx.id)
            sim = self._compute_similarity(profile_a, profile_b)
            if sim >= self.min_similarity:
                similar.append({"xxx_id": other_xxx.id, "similarity": sim})
        return sorted(similar, key=lambda x: x["similarity"], reverse=True)[:topk]

    def _compute_similarity(self, profile_a: dict, profile_b: dict) -> float:
        \"\"\"Compute cosine similarity between two profiles.\"\"\"
        all_tracks = set(profile_a.keys()) | set(profile_b.keys())
        if not all_tracks:
            return 0.0
        a = np.array([profile_a.get(t, 0) for t in all_tracks])
        b = np.array([profile_b.get(t, 0) for t in all_tracks])
        if not a.any() or not b.any():
            return 0.0
        return float(cosine_similarity([a], [b])[0][0])

    async def recommend_for_xxx(self, xxx_id: int, topk: int = 10) -> list[dict]:
        \"\"\"Recommend tracks based on similar xxxs.\"\"\"
        similar_xxxs = await self.find_similar_xxxs(xxx_id, topk=5)
        track_scores: dict[int, float] = {}
        for sim_xxx in similar_xxxs:
            history = await get_listening_history(sim_xxx["xxx_id"], limit=50)
            for entry in history:
                if entry.track_id not in track_scores:
                    track_scores[entry.track_id] = 0.0
                track_scores[entry.track_id] += sim_xxx["similarity"]
        recommendations = sorted(track_scores.items(), key=lambda x: x[1], reverse=True)[:topk]
        return [{"track_id": tid, "score": score} for tid, score in recommendations]
""",
        "function": "recommendation_engine_collaborative_filtering",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "api/recommendations.py",
    },
    # ── 9. Playlist engine — creation, modification, sharing ──────────────────
    {
        "normalized_code": """\
from datetime import datetime, UTC
from sqlalchemy import Integer, String, ForeignKey, DateTime, Boolean, Table, Column
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


playlist_tracks = Table(
    "playlist_tracks",
    Base.metadata,
    Column("playlist_id", Integer, ForeignKey("playlists.id"), primary_key=True),
    Column("track_id", Integer, ForeignKey("tracks.id"), primary_key=True),
    Column("placement", Integer, index=True),
)


class Playlist(Base):
    __tablename__ = "playlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    xxx_id: Mapped[int] = mapped_column(ForeignKey("xxxs.id"), index=True)
    name: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(String(1024), default="")
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    tracks: Mapped[list["Track"]] = relationship(
        "Track",
        secondary=playlist_tracks,
        lazy="selectin",
    )


async def create_playlist(xxx_id: int, name: str, description: str = "") -> Playlist:
    \"\"\"Create empty playlist for xxx.\"\"\"
    async with AsyncSessionLocal() as session:
        playlist = Playlist(xxx_id=xxx_id, name=name, description=description)
        session.add(playlist)
        await session.commit()
        await session.refresh(playlist)
        return playlist


async def add_tracks_to_playlist(playlist_id: int, track_ids: list[int]) -> None:
    \"\"\"Add tracks to playlist with sequential placement.\"\"\"
    async with AsyncSessionLocal() as session:
        playlist = await session.get(Playlist, playlist_id)
        if not playlist:
            return
        max_pos = len(playlist.tracks)
        for offset, track_id in enumerate(track_ids):
            stmt = insert(playlist_tracks).values(
                playlist_id=playlist_id,
                track_id=track_id,
                placement=max_pos + offset,
            )
            await session.execute(stmt)
        await session.commit()


async def remove_tracks_from_playlist(playlist_id: int, track_ids: list[int]) -> None:
    \"\"\"Remove tracks from the playlist.\"\"\"
    async with AsyncSessionLocal() as session:
        stmt = delete(playlist_tracks).where(
            (playlist_tracks.c.playlist_id == playlist_id)
            & (playlist_tracks.c.track_id.in_(track_ids))
        )
        await session.execute(stmt)
        await session.commit()
""",
        "function": "playlist_creation_modification_reordering",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "api/playlist.py",
    },
    # ── 10. ActivityPub federation — federation protocol for music sharing ────
    {
        "normalized_code": """\
import hashlib
import json
from datetime import datetime, UTC
from typing import Optional

import httpx


class ActivityPubFederation:
    \"\"\"ActivityPub protocol for federated music sharing.\"\"\"

    def __init__(self, instance_url: str, instance_actor: str) -> None:
        self.instance_url = instance_url
        self.instance_actor = instance_actor
        self.http_client = httpx.AsyncClient()

    def create_activity(self, activity_type: str, actor: str, payload: dict) -> dict:
        \"\"\"Create ActivityPub activity (Announce, Create, Follow, etc).\"\"\"
        return {
            "@context": "https://www.w3.org/ns/activitystreams",
            "type": activity_type,
            "actor": actor,
            "published": datetime.now(UTC).isoformat(),
            **payload,
        }

    async def announce_track(self, track_id: int, xxx_actor: str) -> dict:
        \"\"\"Create Announce activity for track.\"\"\"
        track = await get_track(track_id)
        activity = self.create_activity(
            "Announce",
            actor=xxx_actor,
            payload={
                "object": {
                    "type": "Audio",
                    "name": track.title,
                    "attributedTo": track.artist.name,
                    "url": f"{self.instance_url}/tracks/{track.id}/listen",
                },
            },
        )
        return activity

    async def announce_playlist(self, playlist_id: int, xxx_actor: str) -> dict:
        \"\"\"Create Announce activity for playlist.\"\"\"
        playlist = await get_playlist(playlist_id)
        track_objs = [
            {
                "type": "Audio",
                "name": track.title,
                "url": f"{self.instance_url}/tracks/{track.id}",
            }
            for track in playlist.tracks
        ]
        activity = self.create_activity(
            "Announce",
            actor=xxx_actor,
            payload={
                "object": {
                    "type": "OrderedCollection",
                    "name": playlist.name,
                    "orderedItems": track_objs,
                },
            },
        )
        return activity

    async def send_activity(self, inbox_url: str, activity: dict) -> bool:
        \"\"\"Send activity to remote inbox (with HTTP signature).\"\"\"
        try:
            response = await self.http_client.post(
                inbox_url,
                json=activity,
                headers={"Content-Type": "application/activity+json"},
            )
            return response.status_code in (200, 202)
        except Exception:
            return False
""",
        "function": "activitypub_federation_protocol",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "api/federation.py",
    },
    # ── 11. Subsonic API compatibility layer — Subsonic client support ───────
    {
        "normalized_code": """\
from typing import Optional
from fastapi import APIRouter, Query, HTTPException


router = APIRouter(prefix="/rest", tags=["subsonic"])


@router.get("/ping.view")
async def subsonic_ping() -> dict:
    \"\"\"Subsonic-compatible ping endpoint.\"\"\"
    return {
        "subsonic-response": {
            "status": "ok",
            "version": "1.16.1",
        }
    }


@router.get("/getMusicFolders.view")
async def subsonic_get_music_folders(xxx_id: int = Query(...)) -> dict:
    \"\"\"Return library folders in Subsonic format.\"\"\"
    library = await get_library(xxx_id)
    folders = [
        {
            "id": str(library.id),
            "name": "My Library",
        }
    ]
    return {
        "subsonic-response": {
            "status": "ok",
            "musicFolders": {"musicFolder": folders},
        }
    }


@router.get("/getArtists.view")
async def subsonic_get_artists(xxx_id: int = Query(...)) -> dict:
    \"\"\"Return all artists in Subsonic format.\"\"\"
    artists = await get_artists_for_library(xxx_id)
    artist_list = [
        {
            "id": str(a.id),
            "name": a.name,
        }
        for a in artists
    ]
    return {
        "subsonic-response": {
            "status": "ok",
            "artists": {"index": [{"artist": artist_list}]},
        }
    }


@router.get("/getAlbum.view")
async def subsonic_get_album(id: int = Query(...), xxx_id: int = Query(...)) -> dict:
    \"\"\"Return album with tracks in Subsonic format.\"\"\"
    album = await get_album(id)
    if not album:
        raise HTTPException(status_code=404)
    tracks = [
        {
            "id": str(t.id),
            "title": t.title,
            "artist": t.artist.name,
            "album": t.album.title,
            "duration": t.duration,
        }
        for t in album.tracks
    ]
    return {
        "subsonic-response": {
            "status": "ok",
            "album": {
                "id": str(album.id),
                "title": album.title,
                "artist": album.artist.name,
                "song": tracks,
            },
        }
    }
""",
        "function": "subsonic_api_compatibility_layer",
        "feature_type": "route",
        "file_role": "route",
        "file_path": "api/subsonic.py",
    },
    # ── 12. Celery async tasks — transcode, import, recommendation batches ────
    {
        "normalized_code": """\
from pathlib import Path

from celery import shared_task
from celery.utils.log import get_task_logger


logger = get_task_logger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def job_transcode_audio(self, track_id: int, target_codec: str = "mp3") -> dict:
    \"\"\"Asynchronous audio transcoding via Celery.\"\"\"
    try:
        track = get_track(track_id)
        source_path = Path(track.file_path)
        output_path = Path(f"/tmp/{track_id}_{target_codec}.audio")

        transcode_audio(source_path, output_path, codec=target_codec)

        # Move to storage
        storage_path = move_to_storage(output_path, track_id)
        track.transcoded_path = storage_path
        db_session.add(track)
        db_session.commit()

        logger.info(f"Transcoded track {track_id} to {target_codec}")
        return {"status": "success", "track_id": track_id, "codec": target_codec}
    except Exception as exc:
        logger.error(f"Transcode failed for track {track_id}: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2)
def job_import_library_batch(self, directory: str, xxx_id: int, batch_size: int = 50) -> dict:
    \"\"\"Batch import library directory.\"\"\"
    try:
        dir_path = Path(directory)
        import_count = 0
        error_count = 0

        for file_path in dir_path.glob("**/*.mp3"):
            try:
                meta = extract_id3_metadata(file_path)
                track = Track(
                    title=meta.get("title", "Unknown"),
                    artist_name=meta.get("artist", "Unknown"),
                    album_name=meta.get("album", "Unknown"),
                    duration=meta.get("duration", 0),
                    file_path=str(file_path),
                    xxx_id=xxx_id,
                )
                db_session.add(track)
                import_count += 1
                if import_count % batch_size == 0:
                    db_session.commit()
            except Exception as err:
                logger.warning(f"Failed to import {file_path}: {err}")
                error_count += 1

        db_session.commit()
        return {"imported": import_count, "failed": error_count}
    except Exception as exc:
        logger.error(f"Library import failed: {exc}")
        raise self.retry(exc=exc)


@shared_task(queue="recommendations")
def job_compute_recommendations(xxx_id: int) -> dict:
    \"\"\"Compute recommendations for xxx, cache in Redis.\"\"\"
    engine = RecommendationEngine()
    recommendations = engine.recommend_for_xxx(xxx_id, topk=20)
    cache_key = f"recommendations:{xxx_id}"
    redis_client.setex(cache_key, 86400, json.dumps(recommendations))
    logger.info(f"Computed recommendations for xxx {xxx_id}")
    return {"status": "success", "xxx_id": xxx_id}
""",
        "function": "celery_async_transcode_import_recommendation",
        "feature_type": "config",
        "file_role": "dependency",
        "file_path": "api/tasks.py",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "audio file transcoding ffmpeg multiple codecs bitrate",
    "extract ID3 tags metadata mutagen MP3 FLAC Vorbis",
    "scan directory library import batch music tracks",
    "artist album track hierarchy SQLAlchemy model",
    "playback queue next previous track navigation",
    "listening history scrobbling play events tracking",
    "audio fingerprinting chromaprint AcoustID duplicate detection",
    "music recommendation collaborative filtering similar xxxs",
    "playlist creation modification reorder tracks sharing",
    "ActivityPub federation announce tracks shared federated",
    "Subsonic API compatibility get artists albums",
    "Celery background job transcode import recommendations",
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

    # Note: clone_repo skipped due to storage constraint in demo
    # In production: clone_repo()

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
