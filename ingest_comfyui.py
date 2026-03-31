"""
ingest_comfyui.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de comfyanonymous/ComfyUI dans la KB Qdrant V6.

Focus : CORE patterns node-based graph execution engine for Stable Diffusion.
PAS des patterns CRUD/API — patterns de graph execution, node discovery, model loading, sampling.

Usage:
    .venv/bin/python3 ingest_comfyui.py
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
REPO_URL = "https://github.com/comfyanonymous/ComfyUI.git"
REPO_NAME = "comfyanonymous/ComfyUI"
REPO_LOCAL = "/tmp/comfyui"
LANGUAGE = "python"
FRAMEWORK = "pytorch"
STACK = "pytorch+diffusers+pillow+comfyui"
CHARTE_VERSION = "1.0"
TAG = "comfyanonymous/ComfyUI"
SOURCE_REPO = "https://github.com/comfyanonymous/ComfyUI"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# ComfyUI = node-based DAG execution engine for diffusion models.
# Patterns CORE : graph execution, node registration, model loading, sampling loops.
# U-5 : utiliser 'node', 'graph', 'prompt', 'queue', 'sampler', etc. (techniques, pas métier)

PATTERNS: list[dict] = [
    # ── 1. Node registry discovery via class introspection ──────────────────────
    {
        "normalized_code": """\
import inspect
from typing import Any, Callable, Dict, Type


class NodeRegistry:
    \"\"\"Registry for discoverable node classes with input/output specs.\"\"\"

    def __init__(self) -> None:
        self.nodes: Dict[str, Type] = {}
        self.node_class_mappings: Dict[str, str] = {}

    def register(self, node_class: Type) -> None:
        \"\"\"Register a node class by introspecting classification and INPUT_TYPES.\"\"\"
        if not hasattr(node_class, "CLASSIFICATION"):
            return
        node_id = node_class.__name__
        self.nodes[node_id] = node_class
        self.node_class_mappings[node_id] = node_class.__module__

    def resolve_inputs(self, node_class: Type) -> Dict[str, Any]:
        \"\"\"Extract INPUT_TYPES spec from node class.\"\"\"
        if not hasattr(node_class, "INPUT_TYPES"):
            return {}
        input_types_fn = getattr(node_class, "INPUT_TYPES")
        if callable(input_types_fn):
            return input_types_fn()
        return input_types_fn

    def get_node_info(self, node_id: str) -> Dict[str, Any]:
        \"\"\"Get full node info (inputs, outputs, classification).\"\"\"
        if node_id not in self.nodes:
            raise ValueError(f"node {node_id} not found")
        node_class = self.nodes[node_id]
        return {
            "class": node_id,
            "inputs": self.resolve_inputs(node_class),
            "outputs": getattr(node_class, "RETURN_TYPES", ()),
            "classification": getattr(node_class, "CLASSIFICATION", "unknown"),
        }
""",
        "function": "node_registry_discovery_introspection",
        "feature_type": "model",
        "file_role": "utility",
        "file_path": "comfy/nodes.py",
    },
    # ── 2. Topological DAG execution with dependency resolution ────────────────
    {
        "normalized_code": """\
from typing import Any, Dict, List, Set, Tuple
import heapq


class GraphExecutor:
    \"\"\"Execute nodes in topological sequence respecting dependencies.\"\"\"

    def __init__(self, graph: Dict[str, Dict[str, Any]]) -> None:
        self.graph = graph
        self.executed: Dict[str, Any] = {}

    def build_dependency_graph(self) -> Dict[str, Set[str]]:
        \"\"\"Build node ID -> upstream node IDs mapping.\"\"\"
        deps: Dict[str, Set[str]] = {}
        for node_id, node_data in self.graph.items():
            deps[node_id] = set()
            inputs = node_data.get("inputs", {})
            for input_val in inputs.values():
                if isinstance(input_val, (list, tuple)) and len(input_val) >= 1:
                    upstream_id = str(input_val[0])
                    if upstream_id in self.graph:
                        deps[node_id].add(upstream_id)
        return deps

    def topological_sort(self) -> List[str]:
        \"\"\"Kahn's algorithm: sort nodes in topological sequence.\"\"\"
        deps = self.build_dependency_graph()
        in_degree = {nid: len(deps[nid]) for nid in self.graph}
        queue = [nid for nid in self.graph if in_degree[nid] == 0]
        sequence = []
        while queue:
            queue.sort()
            current = queue.pop(0)
            sequence.append(current)
            for nid in self.graph:
                if current in deps[nid]:
                    deps[nid].remove(current)
                    in_degree[nid] -= 1
                    if in_degree[nid] == 0:
                        queue.append(nid)
        return sequence

    def execute(self, registry: Any) -> Dict[str, Tuple[Any, ...]]:
        \"\"\"Execute graph in topological sequence, cache outputs.\"\"\"
        sequence = self.topological_sort()
        for node_id in sequence:
            node_data = self.graph[node_id]
            node_class_id = node_data["class_type"]
            node_class = registry.nodes[node_class_id]
            inputs = self._resolve_inputs(node_id, node_data["inputs"])
            instance = node_class()
            output = instance.execute(**inputs)
            self.executed[node_id] = output
        return self.executed

    def _resolve_inputs(self, node_id: str, input_spec: Dict) -> Dict:
        \"\"\"Replace node references with cached outputs.\"\"\"
        resolved = {}
        for key, val in input_spec.items():
            if isinstance(val, (list, tuple)) and len(val) >= 2:
                upstream_id = str(val[0])
                output_idx = val[1]
                if upstream_id in self.executed:
                    resolved[key] = self.executed[upstream_id][output_idx]
            else:
                resolved[key] = val
        return resolved
""",
        "function": "dag_topological_execution_resolver",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "comfy/graph.py",
    },
    # ── 3. Prompt queue with UUID-based execution tracking ──────────────────────
    {
        "normalized_code": """\
from typing import Any, Dict, Optional
import uuid
import json


class PromptQueue:
    \"\"\"Queue for managing diffusion generation prompts with execution history.\"\"\"

    def __init__(self, storage_path: str) -> None:
        self.queue: Dict[str, Dict[str, Any]] = {}
        self.current_index = 0
        self.storage_path = storage_path

    def add_prompt(
        self,
        prompt: Dict[str, Any],
        client_id: Optional[str] = None,
    ) -> str:
        \"\"\"Add a generation prompt to queue, return execution UUID.\"\"\"
        execution_uuid = str(uuid.uuid4())
        self.queue[execution_uuid] = {
            "prompt": prompt,
            "client_id": client_id,
            "status": "queued",
            "outputs": {},
        }
        return execution_uuid

    def get_next(self) -> Optional[tuple[str, Dict[str, Any]]]:
        \"\"\"Get next queued prompt for execution.\"\"\"
        for exe_id, entry in self.queue.items():
            if entry["status"] == "queued":
                self.queue[exe_id]["status"] = "running"
                return exe_id, entry["prompt"]
        return None

    def mark_complete(
        self,
        execution_uuid: str,
        outputs: Dict[str, Any],
    ) -> None:
        \"\"\"Mark execution complete with final outputs.\"\"\"
        if execution_uuid in self.queue:
            self.queue[execution_uuid]["status"] = "complete"
            self.queue[execution_uuid]["outputs"] = outputs

    def mark_failed(self, execution_uuid: str, detail: str) -> None:
        \"\"\"Mark execution as failed with error details.\"\"\"
        if execution_uuid in self.queue:
            self.queue[execution_uuid]["status"] = "failed"
            self.queue[execution_uuid]["detail"] = detail

    def serialize(self) -> str:
        \"\"\"Serialize queue to JSON for persistence.\"\"\"
        return json.dumps(self.queue, default=str)
""",
        "function": "prompt_queue_uuid_execution_tracking",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "comfy/server.py",
    },
    # ── 4. KSampler with sigma scheduler and classifier-free guidance ──────────
    {
        "normalized_code": """\
from typing import Optional, Tuple
import torch
import numpy as np


class KSampler:
    \"\"\"Stable Diffusion sampler with configurable schedulers and guidance.\"\"\"

    def __init__(
        self,
        model: torch.nn.Module,
        scheduler_name: str = "normal",
        steps: int = 20,
        cfg: float = 7.5,
        sampler_name: str = "euler",
    ) -> None:
        self.model = model
        self.scheduler_name = scheduler_name
        self.steps = steps
        self.cfg = cfg
        self.sampler_name = sampler_name

    def sample(
        self,
        seed: int,
        conditioning_pos: torch.Tensor,
        conditioning_neg: Optional[torch.Tensor] = None,
        latent: Optional[torch.Tensor] = None,
        denoise: float = 1.0,
    ) -> torch.Tensor:
        \"\"\"Execute sampling loop with classifier-free guidance.\"\"\"
        torch.manual_seed(seed)
        sigmas = self._get_sigmas(denoise)
        if latent is None:
            latent = torch.randn(
                (1, 4, 64, 64), dtype=torch.float32, device=self.model.device
            )
        for i in range(len(sigmas) - 1):
            sigma = sigmas[i]
            sigma_next = sigmas[i + 1]
            if self.cfg > 1.0 and conditioning_neg is not None:
                latent_uncond = self.model(
                    latent, sigma, conditioning_neg
                )
                latent_cond = self.model(latent, sigma, conditioning_pos)
                latent = latent_uncond + self.cfg * (
                    latent_cond - latent_uncond
                )
            else:
                latent = self.model(latent, sigma, conditioning_pos)
            latent = self._step(latent, sigma, sigma_next)
        return latent

    def _get_sigmas(self, denoise: float = 1.0) -> torch.Tensor:
        \"\"\"Build sigma schedule for scheduler.\"\"\"
        if self.scheduler_name == "normal":
            sigmas = np.linspace(1.0, 0.0, self.steps + 1)
        else:
            sigmas = np.array([1.0, 0.0])
        if denoise < 1.0:
            sigmas = sigmas[int((1.0 - denoise) * len(sigmas)):]
        return torch.from_numpy(sigmas).float()

    def _step(
        self, latent: torch.Tensor, sigma: float, sigma_next: float
    ) -> torch.Tensor:
        \"\"\"Single sampler step (Euler, DPM++, etc.).\"\"\"
        dt = sigma_next - sigma
        return latent + dt * (latent / (sigma + 1e-8))
""",
        "function": "ksampler_cfg_scheduler_sampling",
        "feature_type": "model",
        "file_role": "utility",
        "file_path": "comfy/samplers.py",
    },
    # ── 5. Latent VAE encode with tiling for large images ───────────────────────
    {
        "normalized_code": """\
from typing import Optional, Tuple
import torch
import torch.nn.functional as F


class LatentEncoder:
    \"\"\"Encode/decode images to/from latent space with tiled inference.\"\"\"

    def __init__(self, vae: torch.nn.Module, tile_size: int = 512) -> None:
        self.vae = vae
        self.tile_size = tile_size

    def encode(
        self,
        image: torch.Tensor,
        use_tiling: bool = True,
    ) -> torch.Tensor:
        \"\"\"Encode image to latent distribution.

        Args:
            image: tensor (batch, height, width, channels) in [0, 1]
            use_tiling: split large images into tiles to save VRAM

        Returns:
            latent distribution (batch, 4, h//8, w//8)
        \"\"\"
        image = image.permute(0, 3, 1, 2)
        if use_tiling and image.shape[-1] > self.tile_size:
            return self._encode_tiled(image)
        self.vae.eval()
        with torch.no_grad():
            distribution = self.vae.encode(image)
            latent = distribution.sample()
            return latent * 0.18215

    def _encode_tiled(self, image: torch.Tensor) -> torch.Tensor:
        \"\"\"Encode image via spatial tiling + blend boundaries.\"\"\"
        _, _, height, width = image.shape
        latent_list = []
        for y in range(0, height, self.tile_size):
            for x in range(0, width, self.tile_size):
                y_end = min(y + self.tile_size, height)
                x_end = min(x + self.tile_size, width)
                tile = image[:, :, y:y_end, x:x_end]
                with torch.no_grad():
                    dist = self.vae.encode(tile)
                    latent_tile = dist.sample() * 0.18215
                latent_list.append(latent_tile)
        return torch.cat(latent_list, dim=0)

    def decode(self, latent: torch.Tensor) -> torch.Tensor:
        \"\"\"Decode latent to image space.

        Args:
            latent: (batch, 4, h, w) latent tensor

        Returns:
            image (batch, height, width, 3) in [0, 1]
        \"\"\"
        latent = latent / 0.18215
        self.vae.eval()
        with torch.no_grad():
            image = self.vae.decode(latent).sample
            image = torch.clamp(image * 0.5 + 0.5, 0.0, 1.0)
        return image.permute(0, 2, 3, 1)
""",
        "function": "latent_vae_encode_decode_tiled",
        "feature_type": "model",
        "file_role": "utility",
        "file_path": "comfy/vae.py",
    },
    # ── 6. ControlNet conditioning pipeline ────────────────────────────────────
    {
        "normalized_code": """\
from typing import Optional, Tuple, Dict, Any
import torch


class ControlNetProcessor:
    \"\"\"Apply ControlNet conditioning to diffusion process.\"\"\"

    def __init__(self, controlnet_model: torch.nn.Module, scale: float = 1.0) -> None:
        self.controlnet = controlnet_model
        self.scale = scale

    def process(
        self,
        latent: torch.Tensor,
        control_image: torch.Tensor,
        prompt_embedding: torch.Tensor,
        timestep: int,
    ) -> Tuple[torch.Tensor, Dict[str, torch.Tensor]]:
        \"\"\"Process control signal and extract conditioning residuals.\"\"\"
        self.controlnet.eval()
        with torch.no_grad():
            control_down, control_mid = self.controlnet(
                latent,
                timestep,
                encoder_hidden_states=prompt_embedding,
                controlnet_cond=control_image,
            )
        conditioning = {
            "down": [self.scale * c for c in control_down],
            "mid": self.scale * control_mid,
        }
        return latent, conditioning

    def apply_to_unet(
        self,
        unet: torch.nn.Module,
        conditioning: Dict[str, torch.Tensor],
    ) -> torch.Tensor:
        \"\"\"Apply ControlNet conditioning to UNet forward pass.\"\"\"
        offset = 0
        for i, down_block in enumerate(unet.down_blocks):
            if i < len(conditioning["down"]):
                down_block.output += conditioning["down"][i]
                offset += 1
        unet.middle_block.output += conditioning["mid"]
        return unet
""",
        "function": "controlnet_conditioning_processor",
        "feature_type": "model",
        "file_role": "utility",
        "file_path": "comfy/controlnet.py",
    },
    # ── 7. Model manager with smart VRAM offloading ────────────────────────────
    {
        "normalized_code": """\
import gc
import logging
from typing import Optional, Dict, Any
import torch

logger = logging.getLogger(__name__)

model_cache: Dict[str, torch.nn.Module] = {}
device_memory: Dict[str, int] = {}


def get_torch_device() -> str:
    \"\"\"Auto-detect best available device: CUDA > CPU.\"\"\"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def unload_model(model_key: str, device: str = "cpu") -> None:
    \"\"\"Move model to CPU and clear CUDA cache.\"\"\"
    if model_key in model_cache:
        model = model_cache[model_key]
        model.to(device)
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        gc.collect()
        logger.info(f"unloaded model {model_key} to {device}")


def load_model_lazy(
    model_key: str,
    loader_fn,
    force_cpu: bool = False,
) -> torch.nn.Module:
    \"\"\"Lazy-load model with VRAM management.

    If model exists in cache, return it. Otherwise load via loader_fn
    and cache globally. Optionally force CPU.
    \"\"\"
    if model_key in model_cache:
        return model_cache[model_key]
    device = "cpu" if force_cpu else get_torch_device()
    model = loader_fn()
    model.to(device)
    model_cache[model_key] = model
    logger.info(f"loaded model {model_key} on {device}")
    return model


def cleanup_memory(target_mb: int = 1024) -> None:
    \"\"\"Free GPU memory by unloading non-essential models.\"\"\"
    if torch.cuda.is_available():
        current_mb = torch.cuda.memory_allocated() / 1e6
        if current_mb > target_mb:
            for key in list(model_cache.keys()):
                if key not in ["primary_model"]:
                    unload_model(key)
            torch.cuda.empty_cache()
""",
        "function": "model_manager_vram_offload",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "comfy/model_management.py",
    },
    # ── 8. CLIP text encoder with prompt tokenization ────────────────────────────
    {
        "normalized_code": """\
from typing import Optional, List
import torch


class CLIPTextProcessor:
    \"\"\"Encode text prompts to CLIP embeddings.\"\"\"

    def __init__(
        self,
        clip_model: torch.nn.Module,
        tokenizer: Any,
        max_length: int = 77,
    ) -> None:
        self.clip = clip_model
        self.tokenizer = tokenizer
        self.max_length = max_length

    def encode(
        self,
        prompt_positive: str,
        prompt_negative: Optional[str] = None,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        \"\"\"Tokenize and encode prompts to embeddings.

        Returns:
            (positive_embedding, negative_embedding) or (positive, zeros)
        \"\"\"
        positive_tokens = self.tokenizer.encode(
            prompt_positive, max_length=self.max_length, padding=True
        )
        positive_embedding = self._embed_tokens(positive_tokens)
        if prompt_negative:
            negative_tokens = self.tokenizer.encode(
                prompt_negative, max_length=self.max_length, padding=True
            )
            negative_embedding = self._embed_tokens(negative_tokens)
        else:
            negative_embedding = torch.zeros_like(positive_embedding)
        return positive_embedding, negative_embedding

    def _embed_tokens(self, tokens: torch.Tensor) -> torch.Tensor:
        \"\"\"Pass tokens through CLIP text encoder.\"\"\"
        self.clip.eval()
        with torch.no_grad():
            embedding = self.clip.encode_text(tokens)
            embedding = embedding / torch.norm(embedding, dim=-1, keepdim=True)
        return embedding
""",
        "function": "clip_text_prompt_encoder",
        "feature_type": "model",
        "file_role": "utility",
        "file_path": "comfy/clip.py",
    },
    # ── 9. Workflow JSON deserialization with validation ────────────────────────
    {
        "normalized_code": """\
from typing import Dict, Any, Optional
import json


class WorkflowValidator:
    \"\"\"Parse and validate ComfyUI workflow JSON schema.\"\"\"

    def __init__(self) -> None:
        self.errors: list[str] = []

    def load_workflow(self, workflow_path: str) -> Optional[Dict[str, Any]]:
        \"\"\"Load workflow JSON and validate structure.\"\"\"
        try:
            with open(workflow_path, "r") as f:
                workflow = json.load(f)
        except json.JSONDecodeError as e:
            self.errors.append(f"invalid JSON: {e}")
            return None
        if not isinstance(workflow, dict):
            self.errors.append("workflow must be dict at top level")
            return None
        for node_id, node_data in workflow.items():
            if not isinstance(node_data, dict):
                self.errors.append(
                    f"node {node_id} must be dict, got {type(node_data)}"
                )
            required_fields = ["class_type"]
            for field in required_fields:
                if field not in node_data:
                    self.errors.append(
                        f"node {node_id} missing required field '{field}'"
                    )
        return workflow if not self.errors else None

    def validate_connections(
        self, workflow: Dict[str, Any]
    ) -> bool:
        \"\"\"Verify all node references are valid (no dangling pointers).\"\"\"
        all_node_ids = set(workflow.keys())
        for node_id, node_data in workflow.items():
            inputs = node_data.get("inputs", {})
            for input_val in inputs.values():
                if isinstance(input_val, (list, tuple)) and len(input_val) >= 1:
                    upstream_id = str(input_val[0])
                    if upstream_id not in all_node_ids:
                        self.errors.append(
                            f"node {node_id} references missing upstream {upstream_id}"
                        )
        return len(self.errors) == 0
""",
        "function": "workflow_json_validator",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "comfy/server.py",
    },
    # ── 10. Checkpoint loader with half-precision and memory mapping ────────────
    {
        "normalized_code": """\
import logging
from typing import Dict, Any, Optional
import torch
import os

logger = logging.getLogger(__name__)

CHECKPOINT_CACHE_DIR = os.path.expanduser("~/.cache/comfyui")


def load_checkpoint(
    ckpt_path: str,
    device: str = "cuda",
    dtype: torch.dtype = torch.float16,
) -> torch.nn.Module:
    \"\"\"Load model checkpoint with dtype casting and memory mapping.\"\"\"
    os.makedirs(CHECKPOINT_CACHE_DIR, exist_ok=True)
    if not os.path.exists(ckpt_path):
        raise FileNotFoundError(f"checkpoint not found: {ckpt_path}")
    logger.info(f"loading checkpoint from {ckpt_path}")
    state_dict = torch.load(ckpt_path, map_location="cpu")
    model = create_model_skeleton()
    missing, extra = model.load_state_dict(state_dict, strict=False)
    if missing:
        logger.warning(f"missing keys: {missing}")
    if extra:
        logger.warning(f"extra keys: {extra}")
    model = model.to(device)
    if dtype in [torch.float16, torch.bfloat16]:
        model = model.to(dtype)
    model.eval()
    return model


def save_checkpoint(
    model: torch.nn.Module,
    save_path: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    \"\"\"Save model checkpoint with metadata.\"\"\"
    checkpoint = {
        "model": model.state_dict(),
        "metadata": metadata or {},
    }
    torch.save(checkpoint, save_path)
    logger.info(f"saved checkpoint to {save_path}")


def create_model_skeleton() -> torch.nn.Module:
    \"\"\"Factory function to create empty model structure.\"\"\"
    pass
""",
        "function": "checkpoint_load_save_dtype",
        "feature_type": "dependency",
        "file_role": "utility",
        "file_path": "comfy/model_management.py",
    },
    # ── 11. Image batch processing with tensor conversions ───────────────────────
    {
        "normalized_code": """\
from typing import List, Tuple
import torch
import numpy as np
from PIL import Image


class ImageBatchProcessor:
    \"\"\"Convert between PIL images, numpy arrays, and torch tensors.\"\"\"

    @staticmethod
    def pil_to_tensor(images: List[Image.Image]) -> torch.Tensor:
        \"\"\"Convert PIL images to torch tensor (batch, height, width, 3).\"\"\"
        arrays = [np.array(img).astype(np.float32) / 255.0 for img in images]
        tensor = torch.from_numpy(np.stack(arrays))
        return tensor

    @staticmethod
    def tensor_to_pil(tensor: torch.Tensor) -> List[Image.Image]:
        \"\"\"Convert torch tensor to PIL images.\"\"\"
        tensor = torch.clamp(tensor, 0.0, 1.0)
        arrays = (tensor.cpu().numpy() * 255).astype(np.uint8)
        if arrays.ndim == 3:
            arrays = np.expand_dims(arrays, axis=0)
        images = [Image.fromarray(arr) for arr in arrays]
        return images

    @staticmethod
    def composite(
        background: torch.Tensor,
        foreground: torch.Tensor,
        mask: torch.Tensor,
        x: int = 0,
        y: int = 0,
    ) -> torch.Tensor:
        \"\"\"Composite foreground onto background using mask (alpha blend).\"\"\"
        result = background.clone()
        h_fg, w_fg = foreground.shape[-2:]
        h_bg, w_bg = background.shape[-2:]
        x_end = min(x + w_fg, w_bg)
        y_end = min(y + h_fg, h_bg)
        mask = mask[y:y_end, x:x_end]
        result[y:y_end, x:x_end] = (
            background[y:y_end, x:x_end] * (1.0 - mask)
            + foreground[: y_end - y, : x_end - x] * mask
        )
        return result
""",
        "function": "image_batch_tensor_conversion",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "comfy/image.py",
    },
    # ── 12. LoRA model adapter with weight merging ─────────────────────────────
    {
        "normalized_code": """\
from typing import Dict, Optional
import torch
import torch.nn as nn


class LoraAdapter:
    \"\"\"Load and apply LoRA weight adaptation to base model.\"\"\"

    def __init__(
        self,
        base_model: nn.Module,
        lora_scale: float = 1.0,
    ) -> None:
        self.base_model = base_model
        self.lora_scale = lora_scale
        self.lora_weights: Dict[str, torch.Tensor] = {}

    def load_lora(self, lora_path: str) -> None:
        \"\"\"Load LoRA weights from checkpoint.\"\"\"
        ckpt = torch.load(lora_path, map_location="cpu")
        self.lora_weights = ckpt.get("lora_weights", {})

    def apply(self) -> nn.Module:
        \"\"\"Merge LoRA weights into base model parameters.\"\"\"
        for param_name, lora_delta in self.lora_weights.items():
            if hasattr(self.base_model, param_name):
                param = getattr(self.base_model, param_name)
                if param.shape == lora_delta.shape:
                    param.data = param.data + self.lora_scale * lora_delta
        return self.base_model

    def unapply(self) -> nn.Module:
        \"\"\"Remove LoRA weights from model (restore original).\"\"\"
        for param_name, lora_delta in self.lora_weights.items():
            if hasattr(self.base_model, param_name):
                param = getattr(self.base_model, param_name)
                if param.shape == lora_delta.shape:
                    param.data = param.data - self.lora_scale * lora_delta
        return self.base_model
""",
        "function": "lora_adapter_weight_merging",
        "feature_type": "model",
        "file_role": "utility",
        "file_path": "comfy/lora.py",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "node registry discovery with introspection input types",
    "topological sort DAG execution dependency resolution",
    "prompt queue UUID tracking execution status",
    "KSampler classifier-free guidance diffusion sampling",
    "latent VAE encode decode tiled inference VRAM",
    "ControlNet conditioning pipeline diffusion",
    "model manager lazy loading VRAM offload cleanup",
    "CLIP text encoder prompt tokenization embedding",
    "workflow JSON deserialization validation nodes",
    "checkpoint loader half-precision dtype conversion",
    "image batch tensor conversion PIL numpy torch",
    "LoRA adapter weight merging model fine-tuning",
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
            results.append({"query": q, "function": "NO_RESULT", "file_role": "?", "score": 0.0, "code_preview": "", "norm_ok": True})
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
