"""
state.py — TypedDict partagé entre tous les nodes du pipeline LangGraph V6.
"""

from __future__ import annotations

from typing import Any, TypedDict


class WaleState(TypedDict, total=False):
    # --- Input ---
    prd_path: str          # chemin vers le PRD.md
    prd_content: str       # contenu brut du PRD

    # --- Analyst ---
    language: str          # "python" | "typescript" | "go" | "rust"
    framework: str         # "fastapi" | "express" | "gin" | "axum"
    features: list[str]    # features détectées dans le PRD
    complexity: str        # "SIMPLE" | "MEDIUM" | "COMPLEX"
    project_name: str      # nom du projet extrait du PRD

    # --- Family Classifier (NOUVEAU V6) ---
    family: str            # "crud_api" | "bot_platform" | "rag_platform" | ...
    reference_architecture: dict  # architecture de référence pour cette famille
    family_identified: bool

    # --- Delta Analyzer (NOUVEAU V6) ---
    delta_features: list[str]  # features qui diffèrent de l'architecture de référence
    delta_analyzed: bool

    # --- Strategist ---
    plan: dict[str, Any]   # modules/waves du projet
    waves: list[list[str]] # ordre de génération des fichiers

    # --- Retriever (amélioré V6) ---
    kb_patterns: dict[str, list[str]]  # {feature_type: [normalized_code, ...]}
    kb_patterns_loaded: bool

    # --- Generator ---
    project_dir: str       # dossier du projet généré
    generated_files: dict[str, str]  # {path: code}

    # --- Setup ---
    setup_done: bool

    # --- Evaluator ---
    score: float           # 0-100
    score_a: float         # ruff + pyright
    score_b: float         # pytest
    score_c: float         # schemathesis
    eval_output: str       # output brut des évaluateurs

    # --- Fixer ---
    fix_errors: list[str]  # erreurs priorisées à corriger
    iteration: int
    max_iterations: int
    converged: bool

    # --- Deployer ---
    github_repo_url: str
    deployed: bool

    # --- Meta ---
    target_score: float    # score cible (défaut 80)
    run_id: str            # ID unique de ce run
