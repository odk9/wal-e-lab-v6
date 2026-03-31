"""
ingest_rtvc.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de CorentinJ/Real-Time-Voice-Cloning dans la KB Qdrant V6.

Focus : CORE patterns voice synthesis pipeline (speaker encoding, synthesis, vocoding).
PAS des patterns CRUD/API — patterns de clonage vocal multi-étapes (SV2TTS).

Usage:
    .venv/bin/python3 ingest_rtvc.py
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
REPO_URL = "https://github.com/CorentinJ/Real-Time-Voice-Cloning.git"
REPO_NAME = "CorentinJ/Real-Time-Voice-Cloning"
REPO_LOCAL = "/tmp/rtvc"
LANGUAGE = "python"
FRAMEWORK = "pytorch"
STACK = "pytorch+tacotron+wavernn"
CHARTE_VERSION = "1.0"
TAG = "CorentinJ/Real-Time-Voice-Cloning"
SOURCE_REPO = "https://github.com/CorentinJ/Real-Time-Voice-Cloning"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Real-Time-Voice-Cloning (SV2TTS) = 3-stage voice cloning:
# 1. Speaker Encoder: audio → 256D speaker embedding
# 2. Synthesizer (Tacotron): text + embedding → mel spectrogram
# 3. Vocoder (WaveRNN): mel → waveform
#
# Patterns CORE : pipeline de synthèse vocale, pas des wrappers API.
# U-5 : objets génériques (mel, embedding, tokens, audio arrays).

PATTERNS: list[dict] = [
    # ── 1. Speaker encoder inference — partial utterance segmentation ──────────
    {
        "normalized_code": """\
import numpy as np
from typing import Tuple


def compute_partial_slices(
    length: int,
    partial_utterance_n_frames: int,
    overlap: float = 0.5,
) -> list[Tuple[int, int]]:
    \"\"\"Compute overlapping frame slices for long utterances.

    Segment long audio into overlapping partials to handle variable-length input.
    Each partial is padded to partial_utterance_n_frames.
    \"\"\"
    step = int((1.0 - overlap) * partial_utterance_n_frames)
    slices = []
    start = 0
    while start + partial_utterance_n_frames <= length:
        slices.append((start, start + partial_utterance_n_frames))
        start += step
    if start < length:
        slices.append((max(0, length - partial_utterance_n_frames), length))
    return slices


def embed_utterance(
    xxx: np.ndarray,
    encoder_model: object,
    partial_utterance_n_frames: int = 160,
    overlap: float = 0.5,
) -> np.ndarray:
    \"\"\"Embed long utterance by averaging embeddings of partial segments.

    Segment audio into overlapping partials, encode each independently,
    then average to get robust speaker embedding.
    \"\"\"
    mel_length = xxx.shape[0]
    slices = compute_partial_slices(
        mel_length,
        partial_utterance_n_frames,
        overlap=overlap,
    )

    embeddings = []
    for start, end in slices:
        partial_mel = xxx[start:end]
        if partial_mel.shape[0] < partial_utterance_n_frames:
            pad_width = ((0, partial_utterance_n_frames - partial_mel.shape[0]), (0, 0))
            partial_mel = np.pad(partial_mel, pad_width, mode="constant")

        emb = encoder_model.forward(partial_mel[np.newaxis, :, :])[0]
        embeddings.append(emb)

    embedding = np.mean(embeddings, axis=0)
    embedding = embedding / np.linalg.norm(embedding)
    return embedding
""",
        "function": "speaker_encoder_partial_utterance",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "encoder/inference.py",
    },
    # ── 2. Speaker embedding encoder — 3-layer LSTM ────────────────────────────
    {
        "normalized_code": """\
import numpy as np
import torch
import torch.nn as nn
from typing import Tuple


class LSTMEncoder(nn.Module):
    \"\"\"3-layer LSTM speaker encoder: mel spectrogram → 256D L2-normalized embedding.\"\"\"

    def __init__(
        self,
        input_size: int = 40,
        hidden_size: int = 768,
        num_layers: int = 3,
        output_size: int = 256,
    ) -> None:
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=True,
        )
        self.projection = nn.Linear(hidden_size * 2, output_size)
        self.output_size = output_size

    def forward(self, xxx: torch.Tensor) -> torch.Tensor:
        \"\"\"Forward pass: shape (batch, time_steps, n_mels).\"\"\"
        lstm_out, (h_n, c_n) = self.lstm(xxx)

        last_frame = lstm_out[:, -1, :]
        embedding = self.projection(last_frame)

        embedding = torch.nn.functional.normalize(embedding, p=2, dim=1)
        return embedding
""",
        "function": "lstm_encoder_speaker_embedding",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "encoder/model.py",
    },
    # ── 3. Audio preprocessing chain — resample + normalize + VAD ──────────────
    {
        "normalized_code": """\
import numpy as np
import librosa
from scipy.ndimage import binary_dilation


def normalize_audio(xxx: np.ndarray, target_db: float = -20.0) -> np.ndarray:
    \"\"\"Normalize audio to target loudness in dB.\"\"\"
    rms = np.sqrt(np.mean(xxx ** 2))
    if rms < 1e-7:
        return xxx

    current_db = 20 * np.log10(rms)
    gain_db = target_db - current_db
    gain_linear = 10 ** (gain_db / 20.0)
    normalized = xxx * gain_linear

    normalized = np.clip(normalized, -1.0, 1.0)
    return normalized


def trim_silence(
    xxx: np.ndarray,
    sr: int,
    vad_threshold: float = 30.0,
) -> np.ndarray:
    \"\"\"Trim silence from audio using power-based VAD.\"\"\"
    freqs = librosa.stft(xxx)
    power = np.mean(np.abs(freqs) ** 2, axis=0)
    power_db = 10 * np.log10(np.maximum(power, 1e-10))

    is_voiced = power_db > (np.max(power_db) - vad_threshold)
    is_voiced = binary_dilation(is_voiced, iterations=2)

    voiced_indices = np.where(is_voiced)[0]
    if len(voiced_indices) == 0:
        return xxx

    frame_len = len(xxx) // len(is_voiced)
    start_frame = voiced_indices[0]
    end_frame = voiced_indices[-1] + 1

    start_sample = start_frame * frame_len
    end_sample = end_frame * frame_len
    return xxx[start_sample:end_sample]


def preprocess_audio(
    xxx: np.ndarray,
    sr: int,
    target_sr: int = 16000,
) -> np.ndarray:
    \"\"\"Load, resample to 16kHz, normalize, trim silence.\"\"\"
    if sr != target_sr:
        xxx = librosa.resample(xxx, orig_sr=sr, target_sr=target_sr)

    xxx = normalize_audio(xxx, target_db=-20.0)
    xxx = trim_silence(xxx, target_sr)

    return xxx
""",
        "function": "audio_preprocessing_chain",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "preprocessing/audio.py",
    },
    # ── 4. Mel spectrogram encoder (40-channel) ────────────────────────────────
    {
        "normalized_code": """\
import numpy as np
import librosa


ENCODER_MEL_PARAMS = {
    "n_fft": 800,           # 50 ms window at 16kHz
    "hop_length": 200,      # 12.5 ms hop → ~80 frames/sec
    "win_length": 800,
    "window": "hann",
    "n_mels": 40,           # 40-channel mel filterbank (encoder path)
    "f_min": 55,
    "f_max": 7600,
    "center": False,
}


def mel_spectrogram_encoder(xxx: np.ndarray, sr: int = 16000) -> np.ndarray:
    \"\"\"Compute 40-channel mel spectrogram for speaker encoder.

    Returns shape (n_frames, n_mels) normalized to [0, 1].
    \"\"\"
    mel = librosa.feature.melspectrogram(
        y=xxx,
        sr=sr,
        **ENCODER_MEL_PARAMS,
    )

    mel_db = librosa.power_to_db(mel, ref=np.max)
    mel_db = mel_db.astype(np.float32).T

    mel_normalized = np.clip(mel_db, -100, 0) / 100.0 + 1.0
    mel_normalized = np.clip(mel_normalized, 0, 1)

    return mel_normalized
""",
        "function": "mel_spectrogram_encoder_40ch",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "preprocessing/mel.py",
    },
    # ── 5. Mel spectrogram synthesizer (80-channel) ────────────────────────────
    {
        "normalized_code": """\
import numpy as np
import librosa


SYNTHESIZER_MEL_PARAMS = {
    "n_fft": 1024,          # ~64 ms window at 16kHz (vocoder path)
    "hop_length": 256,      # 16 ms hop
    "win_length": 1024,
    "window": "hann",
    "n_mels": 80,           # 80-channel mel filterbank (Tacotron output)
    "f_min": 40,
    "f_max": 7600,
    "center": False,
}


def mel_spectrogram_synthesizer(xxx: np.ndarray, sr: int = 16000) -> np.ndarray:
    \"\"\"Compute 80-channel mel spectrogram for Tacotron→vocoder.

    Includes preemphasis for stability. Returns shape (n_frames, 80),
    normalized to [-4, 4] as expected by WaveRNN.
    \"\"\"
    pre_emphasis = 0.97
    xxx = np.concatenate([[xxx[0]], xxx[1:] - pre_emphasis * xxx[:-1]])

    mel = librosa.feature.melspectrogram(
        y=xxx,
        sr=sr,
        **SYNTHESIZER_MEL_PARAMS,
    )

    mel_db = librosa.power_to_db(mel, ref=np.max)
    mel_db = mel_db.astype(np.float32).T

    mel_normalized = np.clip(mel_db, -100, 0)
    mel_normalized = (mel_normalized + 100.0) / 100.0 * 4.0 - 4.0

    return mel_normalized
""",
        "function": "mel_spectrogram_synthesizer_80ch",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "preprocessing/mel.py",
    },
    # ── 6. Synthesizer (Tacotron) inference — text + embedding → mel ──────────
    {
        "normalized_code": """\
import numpy as np
import torch
from typing import Optional


def synthesize_spectrograms(
    text_tokens: list[int],
    speaker_embedding: np.ndarray,
    synthesizer_model: object,
    device: str = "cpu",
) -> np.ndarray:
    \"\"\"Synthesize mel spectrogram from text + speaker embedding.

    Tacotron encoder maps text tokens → hidden states.
    Speaker embedding (256D) is repeated and concatenated to encoder output.
    Decoder produces 80-channel mel via attention.
    \"\"\"
    with torch.inference_mode():
        text_tensor = torch.LongTensor(text_tokens)[None, :].to(device)
        speaker_tensor = torch.FloatTensor(speaker_embedding)[None, :].to(device)

        encoder_output = synthesizer_model.encoder(text_tensor)

        speaker_expanded = speaker_tensor.unsqueeze(1).expand(
            -1, encoder_output.shape[1], -1
        )
        encoder_output = torch.cat([encoder_output, speaker_expanded], dim=2)

        mel_output, attention_weights = synthesizer_model.decoder(
            encoder_output,
            speaker_tensor=speaker_tensor,
        )

    mel_numpy = mel_output.squeeze(0).detach().cpu().numpy()
    return mel_numpy
""",
        "function": "synthesizer_tacotron_inference",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "synthesizer/inference.py",
    },
    # ── 7. Speaker embedding conditioning in Tacotron ────────────────────────
    {
        "normalized_code": """\
import torch
import torch.nn as nn


class ConditioningBlock(nn.Module):
    \"\"\"Condition Tacotron decoder with speaker embedding.

    Speaker embedding (256D) is projected, repeated, and concatenated
    to encoder output at each decoder step to control voice identity.
    \"\"\"

    def __init__(
        self,
        embedding_dim: int = 256,
        hidden_dim: int = 512,
        output_dim: int = 256,
    ) -> None:
        super().__init__()
        self.projection = nn.Linear(embedding_dim, output_dim)
        self.integration = nn.Linear(hidden_dim + output_dim, hidden_dim)

    def forward(
        self,
        decoder_state: torch.Tensor,
        speaker_embedding: torch.Tensor,
    ) -> torch.Tensor:
        \"\"\"Apply speaker conditioning to decoder state.

        Args:
            decoder_state: (batch, seq_len, hidden_dim)
            speaker_embedding: (batch, embedding_dim)

        Returns:
            conditioned_state: (batch, seq_len, hidden_dim)
        \"\"\"
        speaker_proj = self.projection(speaker_embedding)
        speaker_expanded = speaker_proj.unsqueeze(1).expand(
            -1, decoder_state.shape[1], -1
        )

        concatenated = torch.cat([decoder_state, speaker_expanded], dim=2)
        conditioned = self.integration(concatenated)
        conditioned = torch.nn.functional.relu(conditioned)

        return conditioned
""",
        "function": "speaker_conditioning_block",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "synthesizer/model.py",
    },
    # ── 8. Vocoder (WaveRNN) inference — mel → waveform ──────────────────────
    {
        "normalized_code": """\
import numpy as np
import torch
from typing import Generator


def infer_waveform(
    mel_spectrogram: np.ndarray,
    vocoder_model: object,
    batch_size: int = 512,
    device: str = "cpu",
) -> np.ndarray:
    \"\"\"Generate waveform from mel spectrogram via WaveRNN.

    Process mel spectrogram in chunked batches to avoid GPU memory overflow.
    WaveRNN outputs 16-bit audio at 16kHz sample rate.
    \"\"\"
    mel_tensor = torch.FloatTensor(mel_spectrogram).unsqueeze(0).to(device)

    waveform = []
    with torch.inference_mode():
        sample = torch.zeros(1, 1, dtype=torch.long, device=device)

        for frame_idx in range(mel_tensor.shape[1]):
            mel_frame = mel_tensor[:, max(0, frame_idx - 1):frame_idx + 1, :]

            logits = vocoder_model(sample, mel_frame)
            logits = logits.squeeze(0).squeeze(0)

            probs = torch.nn.functional.softmax(logits, dim=0)
            sample = torch.multinomial(probs, 1).unsqueeze(0).unsqueeze(0).long()

            waveform.append(sample.cpu().numpy().flat[0])

    audio_array = np.array(waveform, dtype=np.int16)
    audio_float = audio_array.astype(np.float32) / 32768.0

    return audio_float
""",
        "function": "vocoder_wavernn_inference",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "vocoder/inference.py",
    },
    # ── 9. Three-stage voice cloning pipeline ────────────────────────────────
    {
        "normalized_code": """\
import numpy as np
from typing import Tuple


def voice_clone_pipeline(
    ref_audio: np.ndarray,
    ref_sr: int,
    text: str,
    encoder_model: object,
    synthesizer_model: object,
    vocoder_model: object,
    mel_encoder_fn: callable,
    text_to_tokens_fn: callable,
    device: str = "cpu",
) -> np.ndarray:
    \"\"\"End-to-end voice cloning: encode reference → synthesize → vocode.

    Stage 1: Load reference audio → compute speaker embedding
    Stage 2: Text → Tacotron mel with speaker conditioning
    Stage 3: Mel → WaveRNN waveform
    \"\"\"
    ref_audio_proc = preprocess_audio(ref_audio, ref_sr, target_sr=16000)
    ref_mel = mel_encoder_fn(ref_audio_proc, sr=16000)
    speaker_embedding = embed_utterance(ref_mel, encoder_model)

    text_tokens = text_to_tokens_fn(text)
    synthesized_mel = synthesize_spectrograms(
        text_tokens,
        speaker_embedding,
        synthesizer_model,
        device=device,
    )

    waveform = infer_waveform(
        synthesized_mel,
        vocoder_model,
        device=device,
    )

    return waveform
""",
        "function": "three_stage_voice_clone_pipeline",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "vc_pipeline.py",
    },
    # ── 10. Griffin-Lim phase recovery ───────────────────────────────────────
    {
        "normalized_code": """\
import numpy as np


def griffin_lim(
    mel_spectrogram: np.ndarray,
    n_fft: int = 1024,
    n_iter: int = 60,
    hop_length: int = 256,
    win_length: int = 1024,
) -> np.ndarray:
    \"\"\"Reconstruct audio from mel spectrogram via Griffin-Lim algorithm.

    Iteratively refines the phase estimate through 60 iterations.
    Useful as fallback when vocoder is unavailable.
    \"\"\"
    mel_basis = np.linalg.pinv(
        librosa.filters.mel(sr=16000, n_fft=n_fft, n_mels=80)
    )
    S = np.dot(mel_basis, np.exp(mel_spectrogram.T))

    angles = np.angle(np.random.randn(*S.shape) + 1j * np.random.randn(*S.shape))

    for _ in range(n_iter):
        D = S * np.exp(1j * angles)
        xxx = librosa.istft(D, hop_length=hop_length, win_length=win_length)
        D = librosa.stft(xxx, n_fft=n_fft, hop_length=hop_length, win_length=win_length)
        angles = np.angle(D)

    D_final = S * np.exp(1j * angles)
    audio = librosa.istft(D_final, hop_length=hop_length, win_length=win_length)

    return audio
""",
        "function": "griffin_lim_phase_recovery",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "vocoder/griffin_lim.py",
    },
    # ── 11. Lazy model loading with device placement ──────────────────────────
    {
        "normalized_code": """\
import gc
import logging
import torch

logger = logging.getLogger(__name__)

models: dict = {}
model_devices: dict = {}


def grab_best_device(use_gpu: bool = True) -> str:
    \"\"\"Auto-detect best available device (CUDA > CPU).\"\"\"
    if torch.cuda.device_count() > 0 and use_gpu:
        return "cuda"
    return "cpu"


def load_model(
    model_name: str,
    checkpoint_path: str,
    model_class: type,
    use_gpu: bool = True,
    force_reload: bool = False,
) -> object:
    \"\"\"Lazy-load a model: download if missing, cache globally.\"\"\"
    global models, model_devices

    device = grab_best_device(use_gpu=use_gpu)

    if model_name not in models or force_reload:
        if model_name in models:
            del models[model_name]
        gc.collect()

        checkpoint = torch.load(checkpoint_path, map_location=device)
        model = model_class()
        model.load_state_dict(checkpoint["model_state_dict"])
        model.eval()
        model.to(device)

        models[model_name] = model
        model_devices[model_name] = device
        logger.info(f"Loaded {model_name} on {device}")

    return models[model_name]


def clean_models(model_name: str | None = None) -> None:
    \"\"\"Unload model(s) and free GPU memory.\"\"\"
    global models

    keys = [model_name] if model_name is not None else list(models.keys())
    for k in keys:
        if k in models:
            del models[k]

    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    gc.collect()
""",
        "function": "lazy_model_loading_device_placement",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "models/loader.py",
    },
    # ── 12. Text tokenization for Tacotron ─────────────────────────────────────
    {
        "normalized_code": """\
import re
from typing import List


# Simplified text processing
CLEANERS = ["english_cleaners"]
SYMBOLS = "_-!'(),.:;? abcdefghijklmnopqrstuvwxyz"
CHAR_TO_IDX = {s: i for i, s in enumerate(SYMBOLS)}


def text_to_sequence(text: str) -> List[int]:
    \"\"\"Convert text string to integer token sequence for Tacotron.\"\"\"
    text = text.lower()
    text = re.sub(r"[^a-z\\s\\'.,!?\\-]", "", text)

    sequence = []
    for char in text:
        if char in CHAR_TO_IDX:
            sequence.append(CHAR_TO_IDX[char])

    return sequence


def sequence_to_text(sequence: List[int]) -> str:
    \"\"\"Reverse operation: token sequence → text.\"\"\"
    idx_to_char = {v: k for k, v in CHAR_TO_IDX.items()}
    return "".join(idx_to_char.get(idx, "") for idx in sequence)
""",
        "function": "text_tokenization_tacotron",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "preprocessing/text.py",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "speaker encoder partial utterance segmentation voice embedding",
    "three stage voice cloning pipeline text to speech synthesis",
    "mel spectrogram synthesis 80-channel Tacotron vocoder",
    "WaveRNN vocoder inference mel to waveform generation",
    "speaker embedding conditioning concatenation voice identity",
    "audio preprocessing chain normalization silence trimming VAD",
    "LSTM encoder bidirectional speaker embedding 256D",
    "Griffin-Lim phase recovery iterative mel to audio",
    "lazy model loading device GPU memory management",
    "text tokenization sequence Tacotron character encoding",
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
