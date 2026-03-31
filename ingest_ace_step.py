"""
ingest_ace_step.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de ace-step/ACE-Step-1.5 dans la KB Qdrant V6.

Focus : CORE patterns AI music generation (diffusion pipeline, VAE encoding/decoding,
text conditioning, classifier-free guidance, audio normalization, format conversion).
PAS des patterns CRUD/API — patterns de génération audio multi-étapes.

Usage:
    .venv/bin/python3 ingest_ace_step.py
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
REPO_URL = "https://github.com/ace-step/ACE-Step-1.5.git"
REPO_NAME = "ace-step/ACE-Step-1.5"
REPO_LOCAL = "/tmp/ace-step"
LANGUAGE = "python"
FRAMEWORK = "pytorch"
STACK = "pytorch+diffusers+transformers"
CHARTE_VERSION = "1.0"
TAG = "ace-step/ACE-Step-1.5"
SOURCE_REPO = "https://github.com/ace-step/ACE-Step-1.5"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# ACE-Step = Music generation via latent diffusion + VAE codec.
# Patterns CORE : diffusion loop, VAE tiling, text conditioning, classifier-free guidance,
# audio normalization, format conversion, multi-device inference.
# U-5 : pas d'entités métier typiques ici — les objets sont des tensors/audio.

PATTERNS: list[dict] = [
    # ── 1. Diffusion generation pipeline — text → conditioning → diffusion → decode → audio ──
    {
        "normalized_code": """\
from typing import Optional

import torch
import torch.nn as nn
from diffusers import StableDiffusionPipeline
from transformers import AutoTokenizer, AutoModel


def diffusion_generation_pipeline(
    prompt: str,
    num_inference_steps: int = 50,
    guidance_scale: float = 7.5,
    height: int = 512,
    width: int = 512,
    generator: Optional[torch.Generator] = None,
    device: str = "cuda",
) -> torch.Tensor:
    \"\"\"Full diffusion pipeline: text conditioning → diffusion loop → latent decode.

    Args:
        prompt: Input text description for audio/music generation
        num_inference_steps: Number of diffusion denoising steps (quality vs speed tradeoff)
        guidance_scale: Classifier-free guidance strength (0.0=ignore, >1.0=follow prompt)
        height: Latent space height dimension
        width: Latent space width dimension
        generator: Torch generator for reproducibility
        device: Target device (cuda/cpu/mps)

    Returns:
        Generated audio tensor shape (batch, channels, samples)
    \"\"\"
    # Initialize tokenizer and text encoder
    tokenizer = AutoTokenizer.from_pretrained("openai/clip-vit-large-patch14")
    text_encoder = AutoModel.from_pretrained("openai/clip-vit-large-patch14")
    text_encoder = text_encoder.to(device)
    text_encoder.eval()

    # Tokenize and encode text prompt
    text_input = tokenizer(
        prompt,
        padding="max_length",
        max_length=77,
        return_tensors="pt",
    )
    with torch.no_grad():
        text_embeddings = text_encoder(text_input.input_ids.to(device)).last_hidden_state

    # Initialize diffusion scheduler and model
    scheduler = DPMSolverMultistepScheduler.from_pretrained(
        "stabilityai/xxx", subfolder="scheduler"
    )
    unet = UNetXxx2DConditionModel.from_pretrained(
        "stabilityai/xxx", subfolder="unet"
    )
    unet = unet.to(device)
    unet.eval()

    # Initialize latent tensor (Gaussian noise)
    latents = torch.randn(
        (1, 4, height // 8, width // 8),
        generator=generator,
        device=device,
    )
    latents = latents * scheduler.init_noise_sigma

    # Diffusion loop: denoise over num_inference_steps
    scheduler.set_timesteps(num_inference_steps, device=device)
    for t in scheduler.timesteps:
        # Classifier-free guidance: conditional + unconditional pass
        latent_model_input = scheduler.scale_model_input(latents, t)
        with torch.no_grad():
            noise_pred = unet(
                latent_model_input,
                t,
                encoder_hidden_states=text_embeddings,
            ).sample

        # Guidance blend
        latents = scheduler.step(noise_pred, t, latents).prev_sample

    # Decode latents to audio via VAE decoder
    with torch.no_grad():
        audio = vae_decode(latents)

    return audio
""",
        "function": "diffusion_generation_pipeline",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "ace_step/generation.py",
    },
    # ── 2. Tiled VAE encode — audio → overlapping chunks → encode → blend latents ──
    {
        "normalized_code": """\
import torch


def tiled_vae_encode(
    audio: torch.Tensor,
    vae_encoder: torch.nn.Module,
    tile_size: int = 512,
    tile_latent_size: int = 64,
    overlap: int = 8,
) -> torch.Tensor:
    \"\"\"Tiled VAE encoding: split large audio into overlapping chunks, encode each,
    blend results with overlap-discard to avoid seams.

    Args:
        audio: Input audio waveform shape (batch, channels, samples)
        vae_encoder: VAE encoder module
        tile_size: Audio tile size in samples
        tile_latent_size: Expected latent size per tile
        overlap: Overlap width in latent space for seamless blending

    Returns:
        Latent representation shape (batch, latent_channels, latent_height, latent_width)
    \"\"\"
    batch_size, channels, num_samples = audio.shape

    # Calculate tiling parameters
    num_tiles = (num_samples - overlap) // (tile_size - overlap) + 1
    latent_height = (num_tiles - 1) * (tile_latent_size - overlap) + tile_latent_size

    # Initialize output latent tensor
    latents = torch.zeros(
        (batch_size, 4, latent_height),
        device=audio.device,
        dtype=audio.dtype,
    )

    # Encode tiles with overlap blending
    for idx in range(num_tiles):
        start_sample = idx * (tile_size - overlap)
        end_sample = min(start_sample + tile_size, num_samples)

        # Extract tile
        audio_tile = audio[:, :, start_sample:end_sample]

        # Pad if necessary (last tile shorter)
        if audio_tile.shape[2] < tile_size:
            audio_tile = torch.nn.functional.pad(
                audio_tile, (0, tile_size - audio_tile.shape[2])
            )

        # Encode tile
        with torch.no_grad():
            latent_tile = vae_encoder(audio_tile)

        # Calculate output position
        latent_start = idx * (tile_latent_size - overlap)
        latent_end = latent_start + tile_latent_size

        # Blend with overlap-discard (linear crossfade in overlap region)
        if idx > 0:
            # Compute crossfade coefficients
            crossfade = torch.linspace(0.0, 1.0, overlap, device=latents.device)
            latents[:, :, latent_start:latent_start + overlap] = (
                (1.0 - crossfade) * latents[:, :, latent_start:latent_start + overlap]
                + crossfade * latent_tile[:, :, :overlap]
            )
            latents[:, :, latent_start + overlap:latent_end] = latent_tile[:, :, overlap:]
        else:
            latents[:, :, latent_start:latent_end] = latent_tile[:, :, :latent_end - latent_start]

    return latents
""",
        "function": "tiled_vae_encode",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "ace_step/codecs.py",
    },
    # ── 3. Tiled VAE decode — latent → overlapping chunks → decode → blend audio ──
    {
        "normalized_code": """\
import torch


def tiled_vae_decode(
    latents: torch.Tensor,
    vae_decoder: torch.nn.Module,
    tile_latent_size: int = 64,
    tile_sample_size: int = 512,
    overlap: int = 8,
) -> torch.Tensor:
    \"\"\"Tiled VAE decoding: split latent into overlapping chunks, decode each,
    blend results with overlap-discard to reconstruct audio waveform.

    Args:
        latents: Latent tensor shape (batch, latent_channels, latent_height)
        vae_decoder: VAE decoder module
        tile_latent_size: Latent tile size (number of frames per tile)
        tile_sample_size: Expected audio sample size per latent tile
        overlap: Overlap width in latent space

    Returns:
        Decoded audio waveform shape (batch, channels, samples)
    \"\"\"
    batch_size, latent_channels, latent_height = latents.shape

    # Calculate tiling parameters
    num_tiles = (latent_height - overlap) // (tile_latent_size - overlap) + 1
    audio_height = (num_tiles - 1) * (tile_sample_size - overlap) + tile_sample_size

    # Initialize output audio tensor
    audio = torch.zeros(
        (batch_size, 1, audio_height),
        device=latents.device,
        dtype=latents.dtype,
    )

    # Decode tiles with overlap blending
    for idx in range(num_tiles):
        latent_start = idx * (tile_latent_size - overlap)
        latent_end = min(latent_start + tile_latent_size, latent_height)

        # Extract latent tile
        latent_tile = latents[:, :, latent_start:latent_end]

        # Pad if necessary (last tile shorter)
        if latent_tile.shape[2] < tile_latent_size:
            latent_tile = torch.nn.functional.pad(
                latent_tile, (0, tile_latent_size - latent_tile.shape[2])
            )

        # Decode tile
        with torch.no_grad():
            audio_tile = vae_decoder(latent_tile)

        # Calculate output position
        audio_start = idx * (tile_sample_size - overlap)
        audio_end = audio_start + tile_sample_size

        # Blend with overlap-discard (linear crossfade)
        if idx > 0:
            # Compute crossfade coefficients
            overlap_samples = overlap * (tile_sample_size // tile_latent_size)
            crossfade = torch.linspace(0.0, 1.0, overlap_samples, device=audio.device)
            audio[:, :, audio_start:audio_start + overlap_samples] = (
                (1.0 - crossfade) * audio[:, :, audio_start:audio_start + overlap_samples]
                + crossfade * audio_tile[:, :, :overlap_samples]
            )
            audio[:, :, audio_start + overlap_samples:audio_end] = audio_tile[
                :, :, overlap_samples:audio_end - audio_start
            ]
        else:
            audio[:, :, audio_start:audio_end] = audio_tile[:, :, :audio_end - audio_start]

    return audio
""",
        "function": "tiled_vae_decode",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "ace_step/codecs.py",
    },
    # ── 4. Text conditioning preparation — caption + metadata → structured text → tokens → embeddings ──
    {
        "normalized_code": """\
from typing import Optional

import torch
from transformers import AutoTokenizer, AutoModel


def text_conditioning_preparation(
    caption: str,
    metadata: Optional[dict] = None,
    tokenizer_name: str = "openai/clip-vit-large-patch14",
    device: str = "cuda",
) -> torch.Tensor:
    \"\"\"Serialize caption + metadata as structured text, tokenize, and embed.

    Args:
        caption: Main text description for generation
        metadata: Optional dict with bpm, key, tempo, style, duration_seconds, etc.
        tokenizer_name: HuggingFace tokenizer identifier
        device: Target device (cuda/cpu/mps)

    Returns:
        Conditioning embeddings shape (batch, seq_len, embedding_dim)
    \"\"\"
    # Build structured text from caption + metadata
    text_parts = [caption]
    if metadata:
        if "bpm" in metadata:
            text_parts.append(f"BPM: {metadata['bpm']}")
        if "key" in metadata:
            text_parts.append(f"Key: {metadata['key']}")
        if "style" in metadata:
            text_parts.append(f"Style: {metadata['style']}")
        if "duration_seconds" in metadata:
            text_parts.append(f"Duration: {metadata['duration_seconds']}s")

    structured_text = " | ".join(text_parts)

    # Tokenize
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_name)
    text_input = tokenizer(
        structured_text,
        padding="max_length",
        max_length=77,
        return_tensors="pt",
        truncation=True,
    )

    # Load text encoder and compute embeddings
    text_encoder = AutoModel.from_pretrained(tokenizer_name)
    text_encoder = text_encoder.to(device)
    text_encoder.eval()

    with torch.no_grad():
        text_embeddings = text_encoder(
            text_input.input_ids.to(device)
        ).last_hidden_state

    return text_embeddings
""",
        "function": "text_conditioning_preparation",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "ace_step/conditioning.py",
    },
    # ── 5. Classifier-free guidance — conditional + unconditional pass, weighted blend ──
    {
        "normalized_code": """\
import torch


def classifier_free_guidance(
    noise_pred_conditional: torch.Tensor,
    noise_pred_unconditional: torch.Tensor,
    guidance_scale: float = 7.5,
) -> torch.Tensor:
    \"\"\"Blend conditional and unconditional noise predictions via classifier-free guidance.

    CFG formula: noise_pred = unconditional + guidance_scale * (conditional - unconditional)

    Args:
        noise_pred_conditional: Model prediction conditioned on text (shape: batch, channels, height, width)
        noise_pred_unconditional: Model prediction without condition (empty/null token)
        guidance_scale: Guidance strength (0.0=ignore prompt, 1.0=no guidance, >1.0=follow prompt)

    Returns:
        Guided noise prediction with same shape as inputs
    \"\"\"
    noise_pred_guided = (
        noise_pred_unconditional
        + guidance_scale * (noise_pred_conditional - noise_pred_unconditional)
    )
    return noise_pred_guided
""",
        "function": "classifier_free_guidance",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "ace_step/diffusion.py",
    },
    # ── 6. Audio normalization + fade ramps — peak normalization → target dB → fade in/out ──
    {
        "normalized_code": """\
import numpy as np


def audio_normalization_fade(
    audio: np.ndarray,
    target_db: float = -20.0,
    fade_in_duration: float = 0.1,
    fade_out_duration: float = 0.1,
    sample_rate: int = 48000,
) -> np.ndarray:
    \"\"\"Normalize audio to target dB peak and apply fade in/out ramps.

    Args:
        audio: Input audio waveform shape (samples,) or (channels, samples)
        target_db: Target peak level in dB (e.g., -20.0 dB)
        fade_in_duration: Fade-in ramp duration in seconds
        fade_out_duration: Fade-out ramp duration in seconds
        sample_rate: Audio sample rate in Hz

    Returns:
        Normalized audio with fade in/out applied
    \"\"\"
    # Ensure mono/stereo format
    if audio.ndim == 1:
        audio = audio[np.newaxis, :]

    # Peak normalization
    max_val = np.max(np.abs(audio))
    if max_val > 1e-6:  # Avoid division by near-zero
        target_linear = 10.0 ** (target_db / 20.0)
        audio = audio * (target_linear / max_val)

    # Fade-in ramp
    fade_in_samples = int(fade_in_duration * sample_rate)
    if fade_in_samples > 0:
        fade_in_ramp = np.linspace(0.0, 1.0, fade_in_samples)
        audio[:, :fade_in_samples] *= fade_in_ramp

    # Fade-out ramp
    fade_out_samples = int(fade_out_duration * sample_rate)
    if fade_out_samples > 0:
        fade_out_ramp = np.linspace(1.0, 0.0, fade_out_samples)
        audio[:, -fade_out_samples:] *= fade_out_ramp

    return audio.squeeze() if audio.shape[0] == 1 else audio
""",
        "function": "audio_normalization_fade",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "ace_step/audio_utils.py",
    },
    # ── 7. Audio format conversion — export to FLAC/WAV/MP3/OPUS via AudioSaver ──
    {
        "normalized_code": """\
import os
from dataclasses import dataclass
from typing import Literal

import numpy as np
import soundfile as sf
import pydub


@dataclass
class AudioSaver:
    \"\"\"Multi-format audio export utility.\"\"\"

    output_dir: str = "./outputs"
    sample_rate: int = 48000

    def __post_init__(self) -> None:
        os.makedirs(self.output_dir, exist_ok=True)

    def save(
        self,
        audio: np.ndarray,
        filename: str,
        format: Literal["flac", "wav", "mp3", "opus"] = "flac",
    ) -> str:
        \"\"\"Save audio in specified format.

        Args:
            audio: Waveform array shape (samples,) or (channels, samples)
            filename: Output filename without extension
            format: Output format (flac, wav, mp3, opus)

        Returns:
            Full path to saved file
        \"\"\"
        ext = format.lower()
        filepath = os.path.join(self.output_dir, f"{filename}.{ext}")

        # Ensure audio is in correct range [-1, 1]
        if np.max(np.abs(audio)) > 1.0:
            audio = audio / np.max(np.abs(audio))

        if format == "flac":
            sf.write(filepath, audio.T if audio.ndim > 1 else audio, self.sample_rate, subtype="PCM_16")
        elif format == "wav":
            sf.write(filepath, audio.T if audio.ndim > 1 else audio, self.sample_rate, subtype="PCM_16")
        elif format in ("mp3", "opus"):
            # Convert to pydub AudioSegment
            audio_int16 = (audio * 32767).astype(np.int16)
            audio_segment = pydub.AudioSegment(
                audio_int16.tobytes(),
                frame_rate=self.sample_rate,
                sample_width=2,
                channels=audio.ndim if audio.ndim > 1 else 1,
            )
            audio_segment.export(filepath, format=format)
        else:
            raise ValueError(f"Unsupported format: {format}")

        return filepath
""",
        "function": "audio_format_conversion",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "ace_step/audio_utils.py",
    },
    # ── 8. Generation params dataclass — comprehensive parameter dataclass with metadata ──
    {
        "normalized_code": """\
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GenerationParams:
    \"\"\"Comprehensive parameters for music generation pipeline.\"\"\"

    # Text conditioning
    prompt: str = ""
    negative_prompt: str = ""

    # Diffusion parameters
    num_inference_steps: int = 50
    guidance_scale: float = 7.5
    guidance_rescale: float = 0.0

    # Generation shape
    height: int = 512
    width: int = 512
    num_channels: int = 1

    # Audio-specific parameters
    sample_rate: int = 48000
    bpm: Optional[int] = None
    key: Optional[str] = None
    duration_seconds: float = 10.0

    # Seed and reproducibility
    seed: Optional[int] = None
    generator_device: str = "cuda"

    # LLM reasoning flags (for structured output)
    use_llm_reasoning: bool = True
    reasoning_max_tokens: int = 1024

    # Metadata
    style: str = "default"
    instruments: list[str] = field(default_factory=lambda: [])

    def to_dict(self) -> dict:
        \"\"\"Serialize to dictionary for logging.\"\"\"
        return {
            "prompt": self.prompt,
            "num_inference_steps": self.num_inference_steps,
            "guidance_scale": self.guidance_scale,
            "sample_rate": self.sample_rate,
            "bpm": self.bpm,
            "duration_seconds": self.duration_seconds,
            "style": self.style,
        }
""",
        "function": "generation_params_dataclass",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "ace_step/generation.py",
    },
    # ── 9. Latent masking for inpainting/repaint — source audio → mask → inject → crossfade ──
    {
        "normalized_code": """\
import torch


def latent_masking_repaint(
    source_audio: torch.Tensor,
    mask: torch.Tensor,
    source_latents: torch.Tensor,
    generated_latents: torch.Tensor,
    vae_encode_fn,
    crossfade_width: int = 8,
    device: str = "cuda",
) -> torch.Tensor:
    \"\"\"Inpainting via latent masking: inject source latents in masked regions,
    blend with generated latents via crossfade.

    Args:
        source_audio: Reference audio for inpainting source (shape: batch, channels, samples)
        mask: Binary mask (0=keep source, 1=regenerate) shape: (batch, 1, latent_height)
        source_latents: Pre-encoded source latents shape: (batch, latent_channels, latent_height)
        generated_latents: New generated latents shape: (batch, latent_channels, latent_height)
        vae_encode_fn: Function to encode audio to latents
        crossfade_width: Width of crossfade region at mask boundaries
        device: Target device

    Returns:
        Blended latent tensor with masked regions regenerated
    \"\"\"
    mask = mask.to(device)
    source_latents = source_latents.to(device)
    generated_latents = generated_latents.to(device)

    # Initialize output latents
    blended_latents = generated_latents.clone()

    # Inject source latents in masked=0 regions
    blended_latents = torch.where(
        mask == 0,
        source_latents,
        generated_latents,
    )

    # Apply crossfade at mask boundaries to smooth transitions
    # Find boundaries (transition from 0→1 or 1→0)
    mask_diff = torch.abs(mask[:, :, 1:] - mask[:, :, :-1])
    boundary_indices = torch.where(mask_diff > 0.5)

    for idx in boundary_indices[2]:  # Iterate over detected boundaries
        start = max(0, idx - crossfade_width)
        end = min(blended_latents.shape[2], idx + crossfade_width)

        # Linear crossfade blend
        crossfade_coeff = torch.linspace(
            0.0, 1.0, end - start, device=device
        )
        blended_latents[:, :, start:end] = (
            (1.0 - crossfade_coeff) * source_latents[:, :, start:end]
            + crossfade_coeff * generated_latents[:, :, start:end]
        )

    return blended_latents
""",
        "function": "latent_masking_repaint",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "ace_step/inpainting.py",
    },
    # ── 10. Constrained LLM decoding — logits processor enforcing valid BPM/key/duration ──
    {
        "normalized_code": """\
import torch
import torch.nn.functional as F
from typing import Optional


class ConstrainedLogitsProcessor:
    \"\"\"Logits processor enforcing valid parameter ranges during LLM audio code generation.\"\"\"

    def __init__(
        self,
        valid_bpms: list[int] = None,
        valid_keys: list[str] = None,
        min_duration: float = 1.0,
        max_duration: float = 300.0,
    ) -> None:
        self.valid_bpms = valid_bpms or list(range(60, 200, 5))
        self.valid_keys = valid_keys or [
            "C", "Csh", "D", "Dsh", "E", "F", "Fsh", "G", "Gsh", "A", "Ash", "B"
        ]
        self.min_duration = min_duration
        self.max_duration = max_duration
        self.bpm_tokens = None
        self.key_tokens = None

    def __call__(
        self,
        input_ids: torch.Tensor,
        scores: torch.Tensor,
    ) -> torch.Tensor:
        \"\"\"Mask invalid tokens in logits based on constraints.\"\"\"
        batch_size, vocab_size = scores.shape

        # Create mask for valid tokens (initialize as all valid)
        valid_mask = torch.ones(batch_size, vocab_size, device=scores.device, dtype=torch.bool)

        # Get current generated text to determine context
        if len(input_ids) > 0 and "bpm" in self._get_generated_text(input_ids):
            # Constrain BPM tokens
            if self.bpm_tokens is None:
                self.bpm_tokens = self._get_bpm_token_ids()
            invalid_bpm_tokens = set(range(vocab_size)) - set(self.bpm_tokens)
            for token_id in invalid_bpm_tokens:
                valid_mask[:, token_id] = False

        if len(input_ids) > 0 and "key" in self._get_generated_text(input_ids):
            # Constrain key tokens
            if self.key_tokens is None:
                self.key_tokens = self._get_key_token_ids()
            invalid_key_tokens = set(range(vocab_size)) - set(self.key_tokens)
            for token_id in invalid_key_tokens:
                valid_mask[:, token_id] = False

        # Apply mask: set invalid token logits to -inf
        scores = scores.masked_fill(~valid_mask, float("-inf"))

        return scores

    def _get_generated_text(self, input_ids: torch.Tensor) -> str:
        \"\"\"Decode input IDs to text (stub — depends on tokenizer).\"\"\"
        return ""

    def _get_bpm_token_ids(self) -> list[int]:
        \"\"\"Get token IDs corresponding to valid BPMs (stub).\"\"\"
        return list(range(10))

    def _get_key_token_ids(self) -> list[int]:
        \"\"\"Get token IDs corresponding to valid keys (stub).\"\"\"
        return list(range(12))
""",
        "function": "constrained_llm_decoding",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "ace_step/llm_constraints.py",
    },
    # ── 11. Multi-device inference — auto-detect GPU/MPS/CPU, tiling auto-tune, offload fallback ──
    {
        "normalized_code": """\
import torch
import logging

logger = logging.getLogger(__name__)


class MultiDeviceInference:
    \"\"\"Auto-detect and manage inference across GPU/MPS/CPU with adaptive tiling.\"\"\"

    def __init__(self, enable_mps: bool = True, enable_offload: bool = True) -> None:
        self.device = self._detect_device(enable_mps=enable_mps)
        self.enable_offload = enable_offload
        self.memory_budget_mb = self._get_memory_budget()
        self.tile_size = self._auto_tune_tile_size()
        logger.info(f"Device: {self.device}, Tile size: {self.tile_size}")

    def _detect_device(self, enable_mps: bool = True) -> str:
        \"\"\"Auto-detect best available device (CUDA > MPS > CPU).\"\"\"
        if torch.cuda.is_available():
            return "cuda"
        if enable_mps and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    def _get_memory_budget(self) -> float:
        \"\"\"Get available memory in MB based on device.\"\"\"
        if self.device == "cuda":
            return torch.cuda.get_device_properties(0).total_memory / 1e6
        elif self.device == "mps":
            return 8192.0  # Typical MPS allocation
        else:
            return 4096.0  # Conservative CPU estimate

    def _auto_tune_tile_size(self) -> int:
        \"\"\"Auto-tune tile size based on device and available memory.\"\"\"
        if self.device == "cuda":
            # GPU: larger tiles for parallel processing
            return 2048
        elif self.device == "mps":
            # Apple Silicon: moderate tiles
            return 1024
        else:
            # CPU: smaller tiles to avoid OOM
            return 512

    def infer_with_fallback(
        self,
        model_fn,
        input_tensor: torch.Tensor,
        **kwargs,
    ) -> torch.Tensor:
        \"\"\"Run inference with automatic fallback to CPU on OOM.\"\"\"
        try:
            input_tensor = input_tensor.to(self.device)
            with torch.inference_mode(), torch.no_grad():
                result = model_fn(input_tensor, **kwargs)
            return result
        except RuntimeError as e:
            if "out of memory" in str(e).lower():
                logger.warning(f"OOM on {self.device}, falling back to CPU")
                torch.cuda.empty_cache() if self.device == "cuda" else None
                input_tensor = input_tensor.to("cpu")
                with torch.inference_mode(), torch.no_grad():
                    result = model_fn(input_tensor, **kwargs)
                return result
            raise
""",
        "function": "multi_device_inference",
        "feature_type": "config",
        "file_role": "utility",
        "file_path": "ace_step/device_management.py",
    },
    # ── 12. Diffusion scheduler wrapper — timestep scheduling + noise scaling ──
    {
        "normalized_code": """\
import numpy as np
import torch


class DiffusionScheduler:
    \"\"\"Wrapper around diffusion scheduler with timestep scaling and noise management.\"\"\"

    def __init__(
        self,
        num_inference_steps: int = 50,
        beta_start: float = 0.0001,
        beta_end: float = 0.02,
        beta_schedule: str = "linear",
    ) -> None:
        self.num_inference_steps = num_inference_steps
        self.beta_start = beta_start
        self.beta_end = beta_end
        self.beta_schedule = beta_schedule

        # Compute betas, alphas, and cumulative coefficients
        self._init_alphas()

    def _init_alphas(self) -> None:
        \"\"\"Initialize alpha and beta schedules for noise scaling.\"\"\"
        if self.beta_schedule == "linear":
            betas = np.linspace(
                self.beta_start, self.beta_end, self.num_inference_steps
            )
        elif self.beta_schedule == "cosine":
            t = np.arange(0, self.num_inference_steps + 1) / self.num_inference_steps
            betas = np.sin((t + 0.008) / 1.008 * np.pi / 2) ** 2
            betas = betas[1:] - betas[:-1]
            betas = np.clip(betas, self.beta_start, self.beta_end)
        else:
            raise ValueError(f"Unknown schedule: {self.beta_schedule}")

        alphas = 1.0 - betas
        alphas_cumprod = np.cumprod(alphas)
        alphas_cumprod_prev = np.concatenate(([1.0], alphas_cumprod[:-1]))

        self.register_buffer("betas", torch.tensor(betas, dtype=torch.float32))
        self.register_buffer("alphas", torch.tensor(alphas, dtype=torch.float32))
        self.register_buffer("alphas_cumprod", torch.tensor(alphas_cumprod, dtype=torch.float32))
        self.register_buffer("alphas_cumprod_prev", torch.tensor(alphas_cumprod_prev, dtype=torch.float32))

    def register_buffer(self, name: str, tensor: torch.Tensor) -> None:
        \"\"\"Register a buffer (non-trainable tensor).\"\"\"
        setattr(self, name, tensor)

    def get_timesteps(self) -> torch.Tensor:
        \"\"\"Return timestep schedule (descending from num_steps-1 to 0).\"\"\"
        return torch.arange(self.num_inference_steps - 1, -1, -1)

    def scale_model_input(
        self,
        latents: torch.Tensor,
        t: int,
    ) -> torch.Tensor:
        \"\"\"Scale latents by sqrt(alpha_cumprod_t) for consistency.\"\"\"
        scale = torch.sqrt(self.alphas_cumprod[t])
        return latents * scale
""",
        "function": "diffusion_scheduler_wrapper",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "ace_step/schedulers.py",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "music generation diffusion pipeline with text conditioning and classifier-free guidance",
    "tiled VAE encoder overlapping chunks latent space encode decode",
    "text conditioning preparation prompt metadata tokenization embeddings",
    "classifier-free guidance conditional unconditional noise prediction blending",
    "audio normalization peak dB fade in fade out ramps",
    "audio format conversion FLAC WAV MP3 OPUS export multi-format",
    "generation parameters dataclass BPM key style duration LLM reasoning",
    "latent masking inpainting repaint source audio mask injection crossfade",
    "constrained LLM decoding logits processor valid BPM key duration ranges",
    "multi-device inference GPU MPS CPU auto-detect tiling memory management",
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
