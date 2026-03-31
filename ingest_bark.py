"""
ingest_bark.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de suno-ai/bark dans la KB Qdrant V6.

Focus : CORE patterns AI audio generation (TTS pipeline, model loading, inference).
PAS des patterns CRUD/API — patterns de génération audio multi-étapes.

Usage:
    .venv/bin/python3 ingest_bark.py
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
REPO_URL = "https://github.com/suno-ai/bark.git"
REPO_NAME = "suno-ai/bark"
REPO_LOCAL = "/tmp/bark"
LANGUAGE = "python"
FRAMEWORK = "pytorch"
STACK = "pytorch+transformers+encodec"
CHARTE_VERSION = "1.0"
TAG = "suno-ai/bark"
SOURCE_REPO = "https://github.com/suno-ai/bark"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Bark = TTS (text-to-speech) via multi-stage transformer pipeline.
# Patterns CORE : pipeline de génération audio, pas des wrappers API.
# U-5 : pas d'entités métier typiques ici — les objets sont des tensors/tokens.

PATTERNS: list[dict] = [
    # ── 1. Multi-stage TTS pipeline — text → semantic → coarse → fine → waveform ─
    {
        "normalized_code": """\
from typing import Optional, Union

import numpy as np


def text_to_semantic(
    text: str,
    history_prompt: Optional[Union[dict, str]] = None,
    temp: float = 0.7,
    silent: bool = False,
) -> np.ndarray:
    \"\"\"Generate semantic token array from text input.\"\"\"
    x_semantic = generate_text_semantic(
        text,
        history_prompt=history_prompt,
        temp=temp,
        silent=silent,
        use_kv_caching=True,
    )
    return x_semantic


def semantic_to_waveform(
    semantic_tokens: np.ndarray,
    history_prompt: Optional[Union[dict, str]] = None,
    temp: float = 0.7,
    silent: bool = False,
    output_full: bool = False,
) -> Union[np.ndarray, tuple[dict, np.ndarray]]:
    \"\"\"Convert semantic tokens → coarse → fine → audio waveform.\"\"\"
    coarse_tokens = generate_coarse(
        semantic_tokens,
        history_prompt=history_prompt,
        temp=temp,
        silent=silent,
        use_kv_caching=True,
    )
    fine_tokens = generate_fine(
        coarse_tokens,
        history_prompt=history_prompt,
        temp=0.5,
    )
    audio_arr = codec_decode(fine_tokens)
    if output_full:
        full_generation = {
            "semantic_prompt": semantic_tokens,
            "coarse_prompt": coarse_tokens,
            "fine_prompt": fine_tokens,
        }
        return full_generation, audio_arr
    return audio_arr
""",
        "function": "tts_multistage_pipeline",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "bark/api.py",
    },
    # ── 2. End-to-end generate audio from text ───────────────────────────────
    {
        "normalized_code": """\
from typing import Optional, Union

import numpy as np


def generate_audio(
    text: str,
    history_prompt: Optional[Union[dict, str]] = None,
    text_temp: float = 0.7,
    waveform_temp: float = 0.7,
    silent: bool = False,
    output_full: bool = False,
) -> Union[np.ndarray, tuple[dict, np.ndarray]]:
    \"\"\"Generate audio waveform from input text (end-to-end).

    Args:
        text: input text to synthesize
        history_prompt: voice cloning history (dict or preset name)
        text_temp: temperature for text-to-semantic (1.0 diverse, 0.0 conservative)
        waveform_temp: temperature for acoustic generation
        silent: disable progress bars
        output_full: return full generation dict for reuse as history

    Returns:
        numpy audio array at 24kHz sample rate
    \"\"\"
    semantic_tokens = text_to_semantic(
        text,
        history_prompt=history_prompt,
        temp=text_temp,
        silent=silent,
    )
    out = semantic_to_waveform(
        semantic_tokens,
        history_prompt=history_prompt,
        temp=waveform_temp,
        silent=silent,
        output_full=output_full,
    )
    if output_full:
        full_generation, audio_arr = out
        return full_generation, audio_arr
    return out
""",
        "function": "tts_generate_audio_e2e",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "bark/api.py",
    },
    # ── 3. Voice prompt save/load (voice cloning persistence) ─────────────────
    {
        "normalized_code": """\
import numpy as np


def save_as_prompt(filepath: str, full_generation: dict) -> None:
    \"\"\"Save generation output as a reusable voice prompt (.npz).\"\"\"
    assert filepath.endswith(".npz")
    assert isinstance(full_generation, dict)
    assert "semantic_prompt" in full_generation
    assert "coarse_prompt" in full_generation
    assert "fine_prompt" in full_generation
    np.savez(filepath, **full_generation)


def load_voice_prompt(filepath: str) -> dict:
    \"\"\"Load a saved voice prompt for cloning.\"\"\"
    data = np.load(filepath)
    return {
        "semantic_prompt": data["semantic_prompt"],
        "coarse_prompt": data["coarse_prompt"],
        "fine_prompt": data["fine_prompt"],
    }
""",
        "function": "voice_prompt_persistence",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "bark/api.py",
    },
    # ── 4. GPU/device auto-detection ──────────────────────────────────────────
    {
        "normalized_code": """\
import torch


def grab_best_device(use_gpu: bool = True) -> str:
    \"\"\"Auto-detect best available device (CUDA > MPS > CPU).\"\"\"
    if torch.cuda.device_count() > 0 and use_gpu:
        return "cuda"
    if (
        torch.backends.mps.is_available()
        and use_gpu
        and GLOBAL_ENABLE_MPS
    ):
        return "mps"
    return "cpu"
""",
        "function": "device_autodetect_gpu_mps_cpu",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "bark/generation.py",
    },
    # ── 5. Inference context manager (autocast + no_grad + cudnn) ─────────────
    {
        "normalized_code": """\
import contextlib

import torch


class InferenceContext:
    \"\"\"Context manager to configure cuDNN benchmark mode during inference.\"\"\"

    def __init__(self, benchmark: bool = False) -> None:
        self._chosen_cudnn_benchmark = benchmark
        self._cudnn_benchmark: bool | None = None

    def __enter__(self) -> None:
        self._cudnn_benchmark = torch.backends.cudnn.benchmark
        torch.backends.cudnn.benchmark = self._chosen_cudnn_benchmark

    def __exit__(self, exc_type, exc_value, exc_traceback) -> None:
        torch.backends.cudnn.benchmark = self._cudnn_benchmark


@contextlib.contextmanager
def inference_mode():
    \"\"\"Combined context: disable grad + autocast + cuDNN config.\"\"\"
    with InferenceContext(), torch.inference_mode(), torch.no_grad(), autocast():
        yield
""",
        "function": "inference_context_manager_autocast",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "bark/generation.py",
    },
    # ── 6. Lazy model loading with global cache + CPU offload ─────────────────
    {
        "normalized_code": """\
import gc
import logging
import os

import torch
from huggingface_hub import hf_hub_download

logger = logging.getLogger(__name__)

models: dict = {}
models_devices: dict = {}

REMOTE_MODEL_PATHS: dict[str, dict[str, str]] = {
    "text": {"repo_id": "xxx/xxx", "file_name": "text_2.pt"},
    "coarse": {"repo_id": "xxx/xxx", "file_name": "coarse_2.pt"},
    "fine": {"repo_id": "xxx/xxx", "file_name": "fine_2.pt"},
}


def clear_cuda_cache() -> None:
    \"\"\"Clear CUDA memory cache and synchronize.\"\"\"
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()


def clean_models(model_key: str | None = None) -> None:
    \"\"\"Unload model(s) from global cache and free GPU memory.\"\"\"
    global models
    keys = [model_key] if model_key is not None else list(models.keys())
    for k in keys:
        if k in models:
            del models[k]
    clear_cuda_cache()
    gc.collect()


def load_model(
    use_gpu: bool = True,
    use_small: bool = False,
    force_reload: bool = False,
    model_type: str = "text",
) -> object:
    \"\"\"Lazy-load a model: download from HF if missing, cache globally.

    Supports CPU offload mode: keep on CPU, move to GPU only at inference.
    \"\"\"
    global models, models_devices
    device = grab_best_device(use_gpu=use_gpu)
    model_key = model_type
    if OFFLOAD_CPU:
        models_devices[model_key] = device
        device = "cpu"
    if model_key not in models or force_reload:
        ckpt_path = get_ckpt_path(model_type, use_small=use_small)
        clean_models(model_key=model_key)
        model = _load_model(ckpt_path, device, model_type=model_type)
        models[model_key] = model
    return models[model_key]
""",
        "function": "lazy_model_loading_hf_cache",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "bark/generation.py",
    },
    # ── 7. Checkpoint loading with state_dict fixup ───────────────────────────
    {
        "normalized_code": """\
import logging

import torch

logger = logging.getLogger(__name__)


def load_checkpoint(
    ckpt_path: str,
    device: str,
    config_class: type,
    model_class: type,
) -> object:
    \"\"\"Load a model checkpoint with backward-compatible key fixup.

    Handles:
      - vocab_size → input_vocab_size/output_vocab_size migration
      - '_orig_mod.' prefix removal (DDP artifact)
      - Missing/extra key validation
    \"\"\"
    checkpoint = torch.load(ckpt_path, map_location=device)
    model_args = checkpoint["model_args"]
    if "input_vocab_size" not in model_args:
        model_args["input_vocab_size"] = model_args["vocab_size"]
        model_args["output_vocab_size"] = model_args["vocab_size"]
        del model_args["vocab_size"]
    config = config_class(**model_args)
    model = model_class(config)
    state_dict = checkpoint["model"]
    unwanted_prefix = "_orig_mod."
    for k in list(state_dict.keys()):
        if k.startswith(unwanted_prefix):
            state_dict[k[len(unwanted_prefix):]] = state_dict.pop(k)
    extra_keys = set(state_dict.keys()) - set(model.state_dict().keys())
    extra_keys = {k for k in extra_keys if not k.endswith(".attn.bias")}
    missing_keys = set(model.state_dict().keys()) - set(state_dict.keys())
    missing_keys = {k for k in missing_keys if not k.endswith(".attn.bias")}
    if extra_keys:
        raise ValueError(f"extra keys found: {extra_keys}")
    if missing_keys:
        raise ValueError(f"missing keys: {missing_keys}")
    model.load_state_dict(state_dict, strict=False)
    logger.info(
        "model loaded: %sM params, %.3f loss",
        round(model.get_num_params() / 1e6, 1),
        checkpoint["best_val_loss"].cpu().numpy(),
    )
    model.eval()
    model.to(device)
    del checkpoint, state_dict
    return model
""",
        "function": "checkpoint_load_statedict_fixup",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "bark/generation.py",
    },
    # ── 8. Audio codec decode (EnCodec: tokens → waveform) ────────────────────
    {
        "normalized_code": """\
import numpy as np
import torch
from encodec import EncodecModel


def load_codec_model(device: str) -> EncodecModel:
    \"\"\"Load pre-trained EnCodec model for audio decoding.\"\"\"
    model = EncodecModel.encodec_model_24khz()
    model.set_target_bandwidth(6.0)
    model.eval()
    model.to(device)
    return model


def codec_decode(fine_tokens: np.ndarray) -> np.ndarray:
    \"\"\"Decode fine acoustic tokens to audio waveform via EnCodec.

    Args:
        fine_tokens: shape (n_codebooks, time_steps) — 8 codebooks

    Returns:
        audio waveform as 1D numpy array at 24kHz
    \"\"\"
    device = next(codec_model.parameters()).device
    arr = torch.from_numpy(fine_tokens)[None]
    arr = arr.to(device)
    arr = arr.transpose(0, 1)
    emb = codec_model.quantizer.decode(arr)
    out = codec_model.decoder(emb)
    audio_arr = out.detach().cpu().numpy().squeeze()
    return audio_arr
""",
        "function": "audio_codec_decode_encodec",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "bark/generation.py",
    },
    # ── 9. Causal self-attention with KV caching ──────────────────────────────
    {
        "normalized_code": """\
import math

import torch
import torch.nn as nn
from torch.nn import functional as F


class CausalSelfAttention(nn.Module):
    \"\"\"Multi-head causal self-attention with optional KV caching.

    Supports Flash Attention (PyTorch 2.0+) with fallback to manual masking.
    KV cache enables incremental decoding for autoregressive generation.
    \"\"\"

    def __init__(self, config) -> None:
        super().__init__()
        assert config.n_embd % config.n_head == 0
        self.c_attn = nn.Linear(config.n_embd, 3 * config.n_embd, bias=config.bias)
        self.c_proj = nn.Linear(config.n_embd, config.n_embd, bias=config.bias)
        self.attn_dropout = nn.Dropout(config.dropout)
        self.resid_dropout = nn.Dropout(config.dropout)
        self.n_head = config.n_head
        self.n_embd = config.n_embd
        self.dropout = config.dropout
        self.flash = hasattr(torch.nn.functional, "scaled_dot_product_attention")
        if not self.flash:
            self.register_buffer(
                "bias",
                torch.tril(torch.ones(config.block_size, config.block_size)).view(
                    1, 1, config.block_size, config.block_size
                ),
            )

    def forward(
        self,
        x: torch.Tensor,
        past_kv: tuple[torch.Tensor, torch.Tensor] | None = None,
        use_cache: bool = False,
    ) -> tuple[torch.Tensor, tuple[torch.Tensor, torch.Tensor] | None]:
        B, T, C = x.size()
        q, k, v = self.c_attn(x).split(self.n_embd, dim=2)
        k = k.view(B, T, self.n_head, C // self.n_head).transpose(1, 2)
        q = q.view(B, T, self.n_head, C // self.n_head).transpose(1, 2)
        v = v.view(B, T, self.n_head, C // self.n_head).transpose(1, 2)
        if past_kv is not None:
            k = torch.cat((past_kv[0], k), dim=-2)
            v = torch.cat((past_kv[1], v), dim=-2)
        FULL_T = k.shape[-2]
        present = (k, v) if use_cache else None
        if self.flash:
            is_causal = past_kv is None
            y = torch.nn.functional.scaled_dot_product_attention(
                q, k, v, dropout_p=self.dropout, is_causal=is_causal
            )
        else:
            att = (q @ k.transpose(-2, -1)) * (1.0 / math.sqrt(k.size(-1)))
            att = att.masked_fill(
                self.bias[:, :, FULL_T - T : FULL_T, :FULL_T] == 0, float("-inf")
            )
            att = F.softmax(att, dim=-1)
            att = self.attn_dropout(att)
            y = att @ v
        y = y.transpose(1, 2).contiguous().view(B, T, C)
        y = self.resid_dropout(self.c_proj(y))
        return y, present
""",
        "function": "causal_self_attention_kv_cache",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "bark/model.py",
    },
    # ── 10. GPT config dataclass ──────────────────────────────────────────────
    {
        "normalized_code": """\
from dataclasses import dataclass


@dataclass
class GPTConfig:
    \"\"\"Configuration for GPT-style transformer model.\"\"\"

    block_size: int = 1024
    input_vocab_size: int = 10_048
    output_vocab_size: int = 10_048
    n_layer: int = 12
    n_head: int = 12
    n_embd: int = 768
    dropout: float = 0.0
    bias: bool = True
""",
        "function": "gpt_config_dataclass",
        "feature_type": "config",
        "file_role": "model",
        "file_path": "bark/model.py",
    },
    # ── 11. Transformer block (LayerNorm + Attention + MLP) ───────────────────
    {
        "normalized_code": """\
import torch.nn as nn


class LayerNorm(nn.Module):
    \"\"\"LayerNorm with optional bias (PyTorch default requires bias).\"\"\"

    def __init__(self, ndim: int, bias: bool) -> None:
        super().__init__()
        self.weight = nn.Parameter(torch.ones(ndim))
        self.bias = nn.Parameter(torch.zeros(ndim)) if bias else None

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return F.layer_norm(x, self.weight.shape, self.weight, self.bias, 1e-5)


class MLP(nn.Module):
    \"\"\"Feed-forward network: Linear → GELU → Linear → Dropout.\"\"\"

    def __init__(self, config) -> None:
        super().__init__()
        self.c_fc = nn.Linear(config.n_embd, 4 * config.n_embd, bias=config.bias)
        self.c_proj = nn.Linear(4 * config.n_embd, config.n_embd, bias=config.bias)
        self.dropout = nn.Dropout(config.dropout)
        self.gelu = nn.GELU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.c_fc(x)
        x = self.gelu(x)
        x = self.c_proj(x)
        x = self.dropout(x)
        return x


class TransformerBlock(nn.Module):
    \"\"\"Single transformer block: LN → Attention → LN → MLP.\"\"\"

    def __init__(self, config, layer_idx: int) -> None:
        super().__init__()
        self.ln_1 = LayerNorm(config.n_embd, bias=config.bias)
        self.attn = CausalSelfAttention(config)
        self.ln_2 = LayerNorm(config.n_embd, bias=config.bias)
        self.mlp = MLP(config)
        self.layer_idx = layer_idx

    def forward(
        self,
        x: torch.Tensor,
        past_kv: tuple | None = None,
        use_cache: bool = False,
    ) -> tuple[torch.Tensor, tuple | None]:
        attn_out, present = self.attn(
            self.ln_1(x), past_kv=past_kv, use_cache=use_cache
        )
        x = x + attn_out
        x = x + self.mlp(self.ln_2(x))
        return x, present
""",
        "function": "transformer_block_ln_attn_mlp",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "bark/model.py",
    },
    # ── 12. Preload all models for inference pipeline ─────────────────────────
    {
        "normalized_code": """\
import logging

logger = logging.getLogger(__name__)


def preload_models(
    text_use_gpu: bool = True,
    text_use_small: bool = False,
    coarse_use_gpu: bool = True,
    coarse_use_small: bool = False,
    fine_use_gpu: bool = True,
    fine_use_small: bool = False,
    codec_use_gpu: bool = True,
    force_reload: bool = False,
) -> None:
    \"\"\"Pre-load all pipeline models (text, coarse, fine, codec) into memory.\"\"\"
    if grab_best_device() == "cpu" and any([
        text_use_gpu, coarse_use_gpu, fine_use_gpu, codec_use_gpu
    ]):
        logger.warning("No GPU being used. Inference might be very slow!")
    load_model(model_type="text", use_gpu=text_use_gpu, use_small=text_use_small, force_reload=force_reload)
    load_model(model_type="coarse", use_gpu=coarse_use_gpu, use_small=coarse_use_small, force_reload=force_reload)
    load_model(model_type="fine", use_gpu=fine_use_gpu, use_small=fine_use_small, force_reload=force_reload)
    load_codec_model(use_gpu=codec_use_gpu, force_reload=force_reload)
""",
        "function": "preload_all_pipeline_models",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "bark/generation.py",
    },
    # ── 13. HuggingFace model download with cache ─────────────────────────────
    {
        "normalized_code": """\
import os

from huggingface_hub import hf_hub_download

CACHE_DIR = os.path.join(
    os.getenv("XDG_CACHE_HOME", os.path.join(os.path.expanduser("~"), ".cache")),
    "xxx",
    "xxx_v0",
)


def download_model(repo_id: str, file_name: str) -> None:
    \"\"\"Download a model file from HuggingFace Hub into local cache.\"\"\"
    os.makedirs(CACHE_DIR, exist_ok=True)
    hf_hub_download(repo_id=repo_id, filename=file_name, local_dir=CACHE_DIR)


def get_ckpt_path(model_type: str, use_small: bool = False) -> str:
    \"\"\"Get local checkpoint path, downloading if necessary.\"\"\"
    key = model_type
    if use_small:
        key += "_small"
    return os.path.join(CACHE_DIR, REMOTE_MODEL_PATHS[key]["file_name"])
""",
        "function": "huggingface_model_download_cache",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "bark/generation.py",
    },
    # ── 14. Audio generation constants ────────────────────────────────────────
    {
        "normalized_code": """\
CONTEXT_WINDOW_SIZE: int = 1024

SEMANTIC_RATE_HZ: float = 49.9
SEMANTIC_VOCAB_SIZE: int = 10_000

CODEBOOK_SIZE: int = 1024
N_COARSE_CODEBOOKS: int = 2
N_FINE_CODEBOOKS: int = 8
COARSE_RATE_HZ: int = 75

SAMPLE_RATE: int = 24_000
""",
        "function": "audio_generation_constants",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "bark/generation.py",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "text to speech multi-stage generation pipeline",
    "load PyTorch model checkpoint from HuggingFace",
    "causal self-attention with KV caching transformer",
    "audio codec decode tokens to waveform EnCodec",
    "GPU device auto-detection CUDA MPS CPU",
    "voice cloning prompt save and load numpy",
    "transformer block with layer norm and MLP",
    "preload all models into GPU memory for inference",
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
