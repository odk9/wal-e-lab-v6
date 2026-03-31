"""
ingest_podcastfy.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de souzatharsis/podcastfy dans la KB Qdrant V6.

Focus : CORE patterns content-to-audio pipeline (multi-source extraction,
TTS provider abstraction, audio assembly, LLM generation strategies).

Usage:
    .venv/bin/python3 ingest_podcastfy.py
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
REPO_URL = "https://github.com/souzatharsis/podcastfy.git"
REPO_NAME = "souzatharsis/podcastfy"
REPO_LOCAL = "/tmp/podcastfy"
LANGUAGE = "python"
FRAMEWORK = "generic"
STACK = "llm+tts+pydub+content_extraction"
CHARTE_VERSION = "1.0"
TAG = "souzatharsis/podcastfy"
SOURCE_REPO = "https://github.com/souzatharsis/podcastfy"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Podcastfy = content-to-podcast pipeline.
# Patterns CORE : extraction multi-source, TTS factory, audio assembly, LLM generation.
# U-5 : entités normalisées (ContentExtractor = XxxExtractor, etc.)

PATTERNS: list[dict] = [
    # ── 1. Content extraction router — type detection → specialized extractor ─
    {
        "normalized_code": """\
import logging
import re
from typing import Union
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class XxxExtractor:
    \"\"\"Route content extraction to specialized handlers based on source type.\"\"\"

    def __init__(self) -> None:
        self.youtube_transcriber = YoutubeTranscriber()
        self.website_extractor = WebsiteExtractor()
        self.pdf_extractor = PdfExtractor()
        self.config = load_config()
        self.extractor_config = self.config.get("content_extractor", {})

    def is_url(self, source: str) -> bool:
        \"\"\"Check if the source is a valid URL.\"\"\"
        try:
            if not source.startswith(("http://", "https://")):
                source = "https://" + source
            result = urlparse(source)
            return all([result.scheme, result.netloc])
        except ValueError:
            return False

    def extract_content(self, source: str) -> str:
        \"\"\"Extract content by detecting source type and dispatching.

        Routes: .pdf → PdfExtractor, YouTube URL → Transcriber, else → WebsiteExtractor
        \"\"\"
        try:
            if source.lower().endswith(".pdf"):
                return self.pdf_extractor.extract_content(source)
            elif self.is_url(source):
                youtube_patterns = self.extractor_config["youtube_url_patterns"]
                if any(pattern in source for pattern in youtube_patterns):
                    return self.youtube_transcriber.extract_transcript(source)
                else:
                    return self.website_extractor.extract_content(source)
            else:
                raise ValueError("Unsupported source type")
        except Exception as e:
            logger.error("Error extracting content from %s: %s", source, str(e))
            raise
""",
        "function": "content_extraction_router_multitype",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "podcastfy/content_parser/content_extractor.py",
    },
    # ── 2. TTS provider factory — pluggable multi-provider ────────────────────
    {
        "normalized_code": """\
from abc import ABC, abstractmethod
from typing import ClassVar, Optional


class XxxProvider(ABC):
    \"\"\"Abstract base class for TTS provider implementations.\"\"\"

    COMMON_SSML_LABELS: ClassVar[list[str]] = ["lang", "p", "phoneme", "s", "sub"]

    @abstractmethod
    def generate_audio(self, text: str, voice: str, model: str, voice2: str) -> bytes:
        \"\"\"Generate audio from text.

        Returns:
            Audio data as bytes.
        \"\"\"

    def get_supported_labels(self) -> list[str]:
        \"\"\"Get SSML labels supported by this provider.\"\"\"
        return self.COMMON_SSML_LABELS.copy()

    def validate_parameters(self, text: str, voice: str, model: str) -> None:
        \"\"\"Validate input before generation.\"\"\"
        if not text:
            raise ValueError("Text cannot be empty")
        if not voice:
            raise ValueError("Voice must be specified")
        if not model:
            raise ValueError("Model must be specified")


class XxxProviderFactory:
    \"\"\"Factory for creating TTS provider instances by name.\"\"\"

    _providers: dict[str, type[XxxProvider]] = {}

    @classmethod
    def create(
        cls,
        provider_name: str,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> XxxProvider:
        \"\"\"Create a provider instance by name.\"\"\"
        provider_class = cls._providers.get(provider_name.lower())
        if not provider_class:
            available = ", ".join(cls._providers.keys())
            raise ValueError(f"Unsupported provider: {provider_name}. Choose from: {available}")
        if api_key:
            return provider_class(api_key, model)
        return provider_class(model=model)

    @classmethod
    def register_provider(cls, name: str, provider_class: type[XxxProvider]) -> None:
        \"\"\"Register a new provider dynamically.\"\"\"
        cls._providers[name.lower()] = provider_class
""",
        "function": "tts_provider_factory_abstract",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "podcastfy/tts/factory.py",
    },
    # ── 3. Dialogue splitting — Person1/Person2 tag parsing ───────────────────
    {
        "normalized_code": """\
import re
from typing import list


def split_dialogue(
    input_text: str,
    ending_text: str,
    supported_labels: list[str] | None = None,
) -> list[tuple[str, str]]:
    \"\"\"Split dialogue text into (speaker1, speaker2) pairs.

    Parses <Person1>...</Person1><Person2>...</Person2> markup.
    Handles edge cases: input starting with Person2, missing closing markup.
    \"\"\"
    input_text = clean_markup(input_text, supported_labels=supported_labels)
    if input_text.strip().startswith("<Person2>"):
        input_text = "<Person1> ... </Person1>" + input_text
    if input_text.strip().endswith("</Person1>"):
        input_text += f"<Person2>{ending_text}</Person2>"
    pattern = r"<Person1>(.*?)</Person1>\\s*<Person2>(.*?)</Person2>"
    matches = re.findall(pattern, input_text, re.DOTALL)
    return [
        (" ".join(p1.split()).strip(), " ".join(p2.split()).strip())
        for p1, p2 in matches
    ]
""",
        "function": "dialogue_tag_splitting",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "podcastfy/tts/base.py",
    },
    # ── 4. SSML markup cleaning — preserve supported, strip unsupported ───────
    {
        "normalized_code": """\
import re


def clean_markup(
    input_text: str,
    additional_labels: list[str] | None = None,
    supported_labels: list[str] | None = None,
) -> str:
    \"\"\"Remove unsupported markup while preserving known SSML labels.

    Args:
        input_text: text containing mixed markup
        additional_labels: extra labels to preserve (e.g., speaker labels)
        supported_labels: base set of allowed labels
    \"\"\"
    if additional_labels is None:
        additional_labels = ["Person1", "Person2"]
    if supported_labels is None:
        supported_labels = ["lang", "p", "phoneme", "s", "sub"]
    all_supported = supported_labels + additional_labels
    pattern = r"</?(?!(?:" + "|".join(all_supported) + r")\\b)[^>]+>"
    cleaned = re.sub(pattern, "", input_text)
    cleaned = re.sub(r"\\n\\s*\\n", "\\n", cleaned)
    for label in additional_labels:
        others = "|".join(additional_labels)
        cleaned = re.sub(
            f"<{label}>(.*?)(?=<(?:{others})>|$)",
            f"<{label}>\\\\1</{label}>",
            cleaned,
            flags=re.DOTALL,
        )
    return cleaned.strip()
""",
        "function": "ssml_markup_cleaning_preserve",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "podcastfy/tts/base.py",
    },
    # ── 5. Content generation strategy pattern ────────────────────────────────
    {
        "normalized_code": """\
from abc import ABC, abstractmethod


class ContentGenerationStrategy(ABC):
    \"\"\"Abstract strategy for content generation from extracted text.\"\"\"

    @abstractmethod
    def validate(self, input_text: str) -> bool:
        \"\"\"Validate input before generation.\"\"\"

    @abstractmethod
    def compose_prompt_params(self, input_text: str) -> dict:
        \"\"\"Build prompt parameters from input.\"\"\"

    @abstractmethod
    def generate(self, input_text: str) -> str:
        \"\"\"Execute the generation strategy.\"\"\"

    @abstractmethod
    def clean(self, output: str) -> str:
        \"\"\"Clean and finalize generated output.\"\"\"


class StandardContentStrategy(ContentGenerationStrategy):
    \"\"\"Single-pass generation for normal-length content.\"\"\"

    def validate(self, input_text: str) -> bool:
        return len(input_text.strip()) > 0

    def compose_prompt_params(self, input_text: str) -> dict:
        return {"content": input_text, "style": self.conversation_style}

    def generate(self, input_text: str) -> str:
        self.validate(input_text)
        params = self.compose_prompt_params(input_text)
        return self.llm_client.generate(params)

    def clean(self, output: str) -> str:
        output = self._clean_scratchpad(output)
        output = self._fix_alternating_markers(output)
        return output


class LongFormContentStrategy(ContentGenerationStrategy):
    \"\"\"Chunked generation with cross-chunk context maintenance.\"\"\"

    def generate(self, input_text: str) -> str:
        chunks = self._split_into_chunks(input_text)
        accumulated_context = ""
        full_output = ""
        for chunk in chunks:
            params = self.compose_prompt_params(chunk)
            params["previous_context"] = accumulated_context
            result = self.llm_client.generate(params)
            result = self.clean(result)
            full_output += result
            accumulated_context += result
        return full_output

    def _split_into_chunks(self, text: str) -> list[str]:
        \"\"\"Split text at sentence boundaries respecting min/max chunk sizes.\"\"\"
        sentences = text.split(". ")
        chunks: list[str] = []
        current_chunk = ""
        for sentence in sentences:
            if len(current_chunk) + len(sentence) > self.max_chunk_size:
                if len(current_chunk) >= self.min_chunk_size:
                    chunks.append(current_chunk.strip())
                    current_chunk = sentence
                else:
                    current_chunk += ". " + sentence
            else:
                current_chunk += ". " + sentence
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        return chunks
""",
        "function": "content_generation_strategy_pattern",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "podcastfy/content_generator.py",
    },
    # ── 6. Audio segment assembly — split, generate, merge ────────────────────
    {
        "normalized_code": """\
import io
import os
from pathlib import Path

from pydub import AudioSegment


def assemble_audio_segments(
    dialogue_pairs: list[tuple[str, str]],
    provider: object,
    voice1: str,
    voice2: str,
    model: str,
    output_path: str,
    codec: str = "libmp3lame",
    bitrate: str = "320k",
) -> str:
    \"\"\"Generate audio for each dialogue segment and merge into final file.

    1. For each (speaker1, speaker2) pair, generate audio separately
    2. Sort segments by index + speaker sequence
    3. Concatenate using pydub and export

    Returns:
        Path to the final assembled audio file.
    \"\"\"
    temp_dir = Path(output_path).parent / "temp_segments"
    temp_dir.mkdir(parents=True, exist_ok=True)
    for idx, (text_1, text_2) in enumerate(dialogue_pairs):
        audio_1 = provider.generate_audio(text_1, voice1, model, voice2)
        segment_path_1 = temp_dir / f"{idx}_question.mp3"
        segment_path_1.write_bytes(audio_1)
        audio_2 = provider.generate_audio(text_2, voice2, model, voice1)
        segment_path_2 = temp_dir / f"{idx}_answer.mp3"
        segment_path_2.write_bytes(audio_2)
    segment_files = sorted(
        temp_dir.glob("*.mp3"),
        key=lambda p: (int(p.stem.split("_")[0]), p.stem.endswith("answer")),
    )
    combined = AudioSegment.empty()
    for segment_file in segment_files:
        combined += AudioSegment.from_file(str(segment_file))
    combined.export(output_path, format="mp3", codec=codec, bitrate=bitrate)
    return output_path
""",
        "function": "audio_segment_assembly_merge",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "podcastfy/text_to_speech.py",
    },
    # ── 7. Multi-chunk audio from provider (streaming TTS) ────────────────────
    {
        "normalized_code": """\
import io

from pydub import AudioSegment


def combine_audio_chunks(
    audio_chunks: list[bytes],
    output_path: str,
    codec: str = "libmp3lame",
    bitrate: str = "320k",
) -> str:
    \"\"\"Combine multiple audio byte chunks into a single file.

    Used when TTS provider returns pre-segmented audio (multi-speaker mode).
    \"\"\"
    combined = AudioSegment.empty()
    for chunk in audio_chunks:
        segment = AudioSegment.from_file(io.BytesIO(chunk))
        combined += segment
    combined.export(output_path, format="mp3", codec=codec, bitrate=bitrate)
    return output_path
""",
        "function": "audio_chunk_combine_pydub",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "podcastfy/text_to_speech.py",
    },
    # ── 8. Client orchestrator facade — end-to-end pipeline ───────────────────
    {
        "normalized_code": """\
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def process_content(
    urls: list[str] | None = None,
    transcript_file: str | None = None,
    tts_provider: str = "openai",
    generate_audio: bool = True,
    config_overrides: dict | None = None,
) -> str:
    \"\"\"End-to-end pipeline: extract content → generate script → synthesize audio.

    Steps:
        1. If transcript_file provided, load directly
        2. Else: extract from URLs → generate conversational script via LLM
        3. If generate_audio: synthesize via TTS provider → assemble segments
        4. Return path to output file (transcript or audio)
    \"\"\"
    config = load_config()
    if config_overrides:
        config.update(config_overrides)
    if transcript_file and os.path.exists(transcript_file):
        with open(transcript_file) as f:
            transcript = f.read()
    else:
        extractor = XxxExtractor()
        combined_content = ""
        for url in (urls or []):
            content = extractor.extract_content(url)
            combined_content += content + "\\n\\n"
        generator = XxxGenerator(config=config)
        transcript = generator.generate(combined_content)
        transcript_path = os.path.join(config["output_dir"], "transcript.txt")
        with open(transcript_path, "w") as f:
            f.write(transcript)
    if not generate_audio:
        return transcript_path
    api_key = config.get(f"{tts_provider}_api_key")
    provider = XxxProviderFactory.create(tts_provider, api_key=api_key)
    output_path = os.path.join(config["output_dir"], "output.mp3")
    synthesize(transcript, provider, output_path, config)
    return output_path
""",
        "function": "pipeline_orchestrator_facade",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "podcastfy/client.py",
    },
    # ── 9. Configuration loading — env + YAML + runtime override ──────────────
    {
        "normalized_code": """\
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv


class XxxConfig:
    \"\"\"Two-layer config: .env for secrets, YAML for settings.

    Precedence: runtime override > YAML file > environment variables > defaults
    \"\"\"

    def __init__(self, yaml_path: str | None = None) -> None:
        load_dotenv()
        self._data: dict = {}
        if yaml_path and Path(yaml_path).exists():
            with open(yaml_path) as f:
                self._data = yaml.safe_load(f) or {}
        self._set_api_keys()

    def _set_api_keys(self) -> None:
        \"\"\"Load API keys from environment variables.\"\"\"
        key_names = [
            "GEMINI_API_KEY",
            "OPENAI_API_KEY",
            "ELEVENLABS_API_KEY",
        ]
        for key in key_names:
            setattr(self, key, os.getenv(key, ""))

    def get(self, key: str, default: object = None) -> object:
        \"\"\"Get a config value with optional default.\"\"\"
        return self._data.get(key, default)

    def update(self, overrides: dict) -> None:
        \"\"\"Apply runtime overrides.\"\"\"
        self._data.update(overrides)

    def configure(self, **kwargs) -> None:
        \"\"\"Configure via keyword arguments.\"\"\"
        self._data.update(kwargs)
""",
        "function": "config_env_yaml_override",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "podcastfy/utils/config.py",
    },
    # ── 10. LLM content generation with grounding (web search) ────────────────
    {
        "normalized_code": """\
import logging

logger = logging.getLogger(__name__)


def generate_topic_content(topic: str) -> str:
    \"\"\"Generate content about a topic using LLM with web search grounding.

    Uses Gemini API with Google Search tool for up-to-date factual content.
    \"\"\"
    from google import genai
    from google.genai import types

    client = genai.Client()
    grounding_tool = types.Tool(google_search=types.GoogleSearch())
    config = types.GenerateContentConfig(tools=[grounding_tool])
    prompt = (
        f"Search the web for comprehensive information about {topic}. "
        "Provide a detailed overview covering key concepts, recent developments, "
        "important facts and statistics, and different perspectives."
    )
    logger.info("Generating content with search grounding for: %s", topic)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=config,
    )
    return response.text
""",
        "function": "llm_content_generation_grounded_search",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "podcastfy/content_parser/content_extractor.py",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "content extraction from URL PDF YouTube multi-source router",
    "TTS text-to-speech provider factory abstract base class",
    "audio segment assembly merge multiple speakers pydub",
    "content generation strategy pattern long-form chunked",
    "pipeline orchestrator facade end-to-end content to audio",
    "SSML markup tag cleaning preserve supported strip unsupported",
    "configuration loading YAML environment variables override",
    "LLM content generation with web search grounding",
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
                "query": q, "function": hit.payload.get("function", "?"),
                "file_role": hit.payload.get("file_role", "?"),
                "score": hit.score, "code_preview": hit.payload.get("normalized_code", "")[:50],
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
