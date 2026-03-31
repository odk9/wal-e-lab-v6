"""
ingest_peft.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de huggingface/peft dans la KB Qdrant V6.

Focus : Fine-tuning and adaptation patterns (LoRA, QLoRA, prefix tuning, prompt tuning,
IA3, model configuration, training loops, adapter management, inference modes, Hub integration).

Patterns : lora_config_setup, get_peft_model, peft_model_save_load, qlora_4bit_config,
adapter_merge_unload, prefix_tuning_config, prompt_tuning_config, ia3_config,
training_loop_peft, multi_adapter_switch, peft_inference_mode, push_to_hub_peft.

Usage:
    .venv/bin/python3 ingest_peft.py
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
REPO_URL = "https://github.com/huggingface/peft.git"
REPO_NAME = "huggingface/peft"
REPO_LOCAL = "/tmp/peft"
LANGUAGE = "python"
FRAMEWORK = "generic"
STACK = "python+peft+finetuning+huggingface"
CHARTE_VERSION = "1.0"
TAG = "huggingface/peft"
SOURCE_REPO = "https://github.com/huggingface/peft"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# PEFT (Parameter-Efficient Fine-Tuning) = library for efficient model adaptation.
# Patterns CORE : LoRA configuration, model wrapping, QLoRA 4-bit quantization,
# adapter management, prefix/prompt tuning, inference modes, model persistence,
# multi-adapter switching, Hub integration.
#
# Python fine-tuning terms KEPT: adapter, lora, rank, alpha, config, model, get_peft_model,
# save_pretrained, load_adapter, merge_adapter_weights, unload_adapter, infer_lora_dim,
# qlora, quantization_config, training_args, trainer, push_to_hub, inference_mode.

PATTERNS: list[dict] = [
    # ── 1. LoRA configuration setup ──
    {
        "normalized_code": """\
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer

# Configure LoRA adapter
lora_config = LoraConfig(
    r=8,  # Rank of the low-rank matrix
    lora_alpha=32,  # Scaling factor
    target_modules=["q_proj", "v_proj"],  # Target attention layers
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
)

# Load base model and apply LoRA
model = AutoModelForCausalLM.from_pretrained("gpt2")
model = get_peft_model(model, lora_config)

# Check trainable parameters
model.print_trainable_parameters()
print(f"Trainable params: {model.get_num_params(only_trainable=True)}")
""",
        "function": "lora_config_setup",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/lora_setup.py",
    },

    # ── 2. Get PEFT model ──
    {
        "normalized_code": """\
from peft import get_peft_model, LoraConfig
from transformers import AutoModelForSequenceClassification

# Load model
model = AutoModelForSequenceClassification.from_pretrained("bert-base-uncased")

# Define LoRA configuration
config = LoraConfig(
    r=16,
    lora_alpha=32,
    target_modules=["query", "value"],
    lora_dropout=0.1,
    bias="none",
    task_type="SEQ_CLS",
)

# Wrap with PEFT
peft_model = get_peft_model(model, config)

# Model is now trainable with minimal parameters
trainable = peft_model.get_num_params(only_trainable=True)
total = peft_model.get_num_params()
print(f"Trainable: {trainable}, Total: {total}, Ratio: {100*trainable/total:.2f}%")
""",
        "function": "get_peft_model_wrapper",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "examples/get_peft_model.py",
    },

    # ── 3. PEFT model save and load ──
    {
        "normalized_code": """\
from peft import get_peft_model, LoraConfig, AutoPeftModelForCausalLM
from transformers import AutoModelForCausalLM

# Train model with LoRA
lora_config = LoraConfig(r=8, lora_alpha=16, target_modules=["q_proj", "v_proj"])
model = AutoModelForCausalLM.from_pretrained("gpt2")
peft_model = get_peft_model(model, lora_config)

# Save adapter weights
peft_model.save_pretrained("./lora_adapter")
print("Adapter saved to ./lora_adapter")

# Load adapter back
loaded_model = AutoPeftModelForCausalLM.from_pretrained("./lora_adapter")
print("Adapter loaded successfully")

# Or load adapter into base model
base_model = AutoModelForCausalLM.from_pretrained("gpt2")
from peft import PeftModel
model_with_adapter = PeftModel.from_pretrained(base_model, "./lora_adapter")
""",
        "function": "peft_model_save_load",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/peft_save_load.py",
    },

    # ── 4. QLoRA 4-bit quantization configuration ──
    {
        "normalized_code": """\
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, BitsAndBytesConfig
import torch

# 4-bit quantization configuration
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
)

# Load model with quantization
model = AutoModelForCausalLM.from_pretrained(
    "meta-llama/Llama-2-7b",
    quantization_config=bnb_config,
    device_map="auto",
)

# Apply LoRA on quantized model
lora_config = LoraConfig(
    r=8,
    lora_alpha=16,
    target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
)

peft_model = get_peft_model(model, lora_config)
peft_model.print_trainable_parameters()
""",
        "function": "qlora_4bit_config",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/qlora_quantization.py",
    },

    # ── 5. Adapter merge and unload ──
    {
        "normalized_code": """\
from peft import get_peft_model, LoraConfig, PeftModel
from transformers import AutoModelForCausalLM

# Load model with adapter
lora_config = LoraConfig(r=8, lora_alpha=16, target_modules=["q_proj", "v_proj"])
model = AutoModelForCausalLM.from_pretrained("gpt2")
peft_model = get_peft_model(model, lora_config)

# Merge adapter weights into base model
merged_model = peft_model.merge_and_unload()
print("Adapter merged into base model")
print(f"Merged model size: {merged_model.num_parameters()}")

# Save merged model
merged_model.save_pretrained("./merged_model")

# Alternatively, merge but keep original structure
peft_model_merged = peft_model.merge_adapter_weights()
peft_model.unload_adapter()  # Remove adapter from active module

# Load new adapter after unloading previous
peft_model.load_adapter("./other_adapter", adapter_name="new_adapter")
""",
        "function": "adapter_merge_unload",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/adapter_merge.py",
    },

    # ── 6. Prefix tuning configuration ──
    {
        "normalized_code": """\
from peft import PrefixTuningConfig, get_peft_model
from transformers import AutoModelForSeq2SeqLM

# Prefix tuning configuration
prefix_config = PrefixTuningConfig(
    num_virtual_tokens=20,
    task_type="SEQ_2_SEQ_LM",
    encoder_hidden_size=768,
    encoder_reparameterization_type="mlp",
)

# Load model and apply prefix tuning
model = AutoModelForSeq2SeqLM.from_pretrained("t5-base")
peft_model = get_peft_model(model, prefix_config)

# Only prefix tokens are trainable
trainable = peft_model.get_num_params(only_trainable=True)
total = peft_model.get_num_params()
print(f"Trainable params: {trainable}/{total}")

# Use model for training
input_ids = [101, 2054, 2003, 1045, 102]  # Example tokens
outputs = peft_model.generate(input_ids, max_length=50)
""",
        "function": "prefix_tuning_config",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/prefix_tuning.py",
    },

    # ── 7. Prompt tuning configuration ──
    {
        "normalized_code": """\
from peft import PromptTuningConfig, TaskType, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer

# Prompt tuning configuration
prompt_config = PromptTuningConfig(
    task_type=TaskType.CAUSAL_LM,
    num_virtual_tokens=8,
    prompt_tuning_init_text="Classify the sentiment: ",
    tokenizer_name_or_path="gpt2",
)

# Load model and apply prompt tuning
model = AutoModelForCausalLM.from_pretrained("gpt2")
peft_model = get_peft_model(model, prompt_config)

tokenizer = AutoTokenizer.from_pretrained("gpt2")

# Forward pass with virtual tokens prepended
text = "This widget is amazing!"
inputs = tokenizer(text, return_tensors="pt")
outputs = peft_model(**inputs)

print(f"Trainable params: {peft_model.get_num_params(only_trainable=True)}")
""",
        "function": "prompt_tuning_config",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/prompt_tuning.py",
    },

    # ── 8. IA3 configuration ──
    {
        "normalized_code": """\
from peft import IA3Config, get_peft_model, TaskType
from transformers import AutoModelForCausalLM

# IA3 (Infused Adapter by Inhibiting and Amplifying Inner Activations)
ia3_config = IA3Config(
    task_type=TaskType.CAUSAL_LM,
    target_modules=["k_proj", "v_proj", "dense"],
    feedforward_modules=["dense"],
)

# Load model and apply IA3
model = AutoModelForCausalLM.from_pretrained("gpt2")
peft_model = get_peft_model(model, ia3_config)

# IA3 learns scaling and inhibition parameters
trainable = peft_model.get_num_params(only_trainable=True)
print(f"IA3 trainable params: {trainable}")

# Use model
text = "Once upon a time"
input_ids = [text]  # Tokenize in actual usage
outputs = peft_model(input_ids)
""",
        "function": "ia3_config",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/ia3_config.py",
    },

    # ── 9. Training loop with PEFT ──
    {
        "normalized_code": """\
from peft import get_peft_model, LoraConfig
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
)
from datasets import load_dataset

# Load dataset
dataset = load_dataset("glue", "mrpc")

# Model and tokenizer
model = AutoModelForSequenceClassification.from_pretrained("bert-base-uncased")
tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")

# Apply LoRA
lora_config = LoraConfig(r=8, lora_alpha=16, target_modules=["query", "value"])
model = get_peft_model(model, lora_config)

# Training arguments
training_args = TrainingArguments(
    output_dir="./results",
    num_train_epochs=3,
    per_device_train_batch_size=16,
    learning_rate=2e-4,
    save_strategy="epoch",
)

# Trainer
trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=dataset["train"],
)

trainer.train()
""",
        "function": "training_loop_peft",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "examples/training_loop.py",
    },

    # ── 10. Multi-adapter switching ──
    {
        "normalized_code": """\
from peft import get_peft_model, LoraConfig, PeftModel
from transformers import AutoModelForCausalLM

# Load base model
model = AutoModelForCausalLM.from_pretrained("gpt2")

# Create LoRA config
lora_config = LoraConfig(r=8, lora_alpha=16, target_modules=["c_attn"])
peft_model = get_peft_model(model, lora_config, adapter_name="adapter_1")

# Add second adapter
lora_config_2 = LoraConfig(r=16, lora_alpha=32, target_modules=["c_attn"])
peft_model.add_adapter("adapter_2", lora_config_2)

# Switch active adapter
peft_model.set_adapter("adapter_1")
output_1 = peft_model.generate([101], max_length=50)

# Switch to second adapter
peft_model.set_adapter("adapter_2")
output_2 = peft_model.generate([101], max_length=50)

# Disable all adapters
peft_model.disable_adapter_layers()
output_base = peft_model.generate([101], max_length=50)

# Get active adapter name
active = peft_model.active_adapter
print(f"Active adapter: {active}")
""",
        "function": "multi_adapter_switch",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/multi_adapter.py",
    },

    # ── 11. PEFT inference mode ──
    {
        "normalized_code": """\
from peft import get_peft_model, LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

# Load and prepare model
lora_config = LoraConfig(r=8, lora_alpha=16, target_modules=["q_proj", "v_proj"])
model = AutoModelForCausalLM.from_pretrained("gpt2")
peft_model = get_peft_model(model, lora_config)

tokenizer = AutoTokenizer.from_pretrained("gpt2")

# Switch to inference mode
peft_model.eval()

# Use inference_mode context manager for efficiency
with torch.inference_mode():
    prompt = "The quick brown fox"
    inputs = tokenizer(prompt, return_tensors="pt")
    outputs = peft_model.generate(**inputs, max_length=50)
    generated_text = tokenizer.decode(outputs[0])
    print(f"Generated: {generated_text}")

# Or merge and infer with base model
merged_model = peft_model.merge_and_unload()
with torch.inference_mode():
    outputs = merged_model.generate(**inputs, max_length=50)
""",
        "function": "peft_inference_mode",
        "feature_type": "pipeline",
        "file_role": "utility",
        "file_path": "examples/inference_mode.py",
    },

    # ── 12. Push adapter to Hub ──
    {
        "normalized_code": """\
from peft import get_peft_model, LoraConfig
from transformers import AutoModelForCausalLM

# Load and prepare model
model = AutoModelForCausalLM.from_pretrained("gpt2")
lora_config = LoraConfig(r=8, lora_alpha=16, target_modules=["c_attn"])
peft_model = get_peft_model(model, lora_config)

# Save adapter locally
peft_model.save_pretrained("./gpt2-lora-adapter")

# Push to Hugging Face Hub
peft_model.push_to_hub(
    "gpt2-lora-sentiment",
    token="hf_...",  # Your HF token
    private=False,
)

# Push with additional metadata
peft_model.push_to_hub(
    repo_id="gpt2-lora-sentiment",
    commit_message="Add LoRA adapter for sentiment analysis",
    private=False,
)

print("Adapter pushed to https://huggingface.co/account/gpt2-lora-sentiment")

# Load from Hub later
from peft import PeftModel
base = AutoModelForCausalLM.from_pretrained("gpt2")
model_hub = PeftModel.from_pretrained(base, "account/gpt2-lora-sentiment")
""",
        "function": "push_to_hub_peft",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/push_to_hub.py",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "lora rank alpha target modules configuration",
    "get peft model wrapper adapter",
    "save load adapter pretrained model",
    "qlora 4bit quantization bitsandbytes",
    "merge adapter weights unload",
    "prefix tuning virtual tokens",
    "prompt tuning initialization text",
    "ia3 inhibiting amplifying inner activations",
    "training loop transformers trainer",
    "multi-adapter switching set active",
    "inference mode merge unload torch",
    "push hub huggingface repository",
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
