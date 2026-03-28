"""
extractor.py — Agent KB Extracteur.

Prend un repo téléchargé, extrait les patterns de features :
1. AST parsing (Python) pour identifier les frontières syntaxiques
2. LLM pour labelliser les features cross-fichiers

Entrée  : Path vers un repo local
Sortie  : list[RawPattern] — patterns bruts avant normalisation
"""

from __future__ import annotations

import ast
import json
import os
from dataclasses import dataclass
from pathlib import Path

import httpx

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
EXTRACTOR_MODEL = "mimo-vl/mimo-v2-flash"  # rapide, pas de génération complexe

# Feature types reconnus
FEATURE_TYPES = [
    "crud",
    "auth_jwt",
    "websocket",
    "redis_pubsub",
    "ml_inference",
    "background_task",
    "discord_bot",
    "pagination",
    "file_upload",
    "email",
    "rate_limiting",
    "caching",
    "health_check",
    "config",
    "database_setup",
    "testing",
]

# Rôles de fichiers reconnus
FILE_ROLES = [
    "models",
    "schemas",
    "routes",
    "crud",
    "database",
    "main",
    "config",
    "tests",
    "middleware",
    "utils",
    "dependencies",
]


@dataclass
class RawPattern:
    feature_type: str
    framework: str
    language: str
    file_role: str
    raw_code: str
    source_repo: str
    source_file: str


def _detect_framework(repo_dir: Path) -> str:
    """Détecte le framework principal du repo."""
    # Cherche dans les fichiers de config
    for config_file in ["pyproject.toml", "requirements.txt", "setup.py", "package.json"]:
        config_path = repo_dir / config_file
        if config_path.exists():
            content = config_path.read_text(errors="ignore").lower()
            if "fastapi" in content:
                return "fastapi"
            if "express" in content or "\"express\"" in content:
                return "express"
            if "gin" in content:
                return "gin"
            if "axum" in content:
                return "axum"

    # Cherche dans les imports Python
    for py_file in repo_dir.rglob("*.py"):
        try:
            content = py_file.read_text(errors="ignore")
            if "from fastapi" in content or "import fastapi" in content:
                return "fastapi"
        except OSError:
            continue

    return "unknown"


def _detect_language(repo_dir: Path) -> str:
    """Détecte le langage principal."""
    extensions = {}
    for f in repo_dir.rglob("*"):
        if f.is_file():
            ext = f.suffix.lower()
            extensions[ext] = extensions.get(ext, 0) + 1

    lang_map = {".py": "python", ".ts": "typescript", ".go": "go", ".rs": "rust"}
    for ext, lang in lang_map.items():
        if extensions.get(ext, 0) > 0:
            return lang
    return "unknown"


def _guess_file_role(file_path: Path) -> str:
    """Devine le rôle d'un fichier depuis son nom/chemin."""
    name = file_path.stem.lower()
    parts = [p.lower() for p in file_path.parts]

    role_keywords = {
        "models": ["model", "models", "entity", "entities"],
        "schemas": ["schema", "schemas", "dto", "types", "interfaces"],
        "routes": ["route", "routes", "router", "endpoint", "endpoints", "views", "handlers"],
        "crud": ["crud", "repository", "repo", "service", "services"],
        "database": ["database", "db", "connection", "session"],
        "main": ["main", "app", "application", "server"],
        "config": ["config", "settings", "configuration", "env"],
        "tests": ["test", "tests", "spec"],
        "middleware": ["middleware", "auth", "authentication", "authorization"],
        "utils": ["utils", "helpers", "common", "shared"],
        "dependencies": ["dependencies", "deps", "inject"],
    }

    for role, keywords in role_keywords.items():
        if any(kw in name for kw in keywords) or any(
            kw in part for kw in keywords for part in parts
        ):
            return role

    return "utils"


def _extract_python_blocks(source: str) -> list[str]:
    """
    Extrait les blocs syntaxiques significatifs d'un fichier Python via AST.
    Retourne les classes et fonctions de plus de 5 lignes.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [source]  # retourne le fichier entier si parse échoue

    blocks = []
    lines = source.splitlines()

    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            start = node.lineno - 1
            end = node.end_lineno
            if end - start >= 5:  # blocs > 5 lignes seulement
                block = "\n".join(lines[start:end])
                blocks.append(block)

    return blocks if blocks else [source]


def _llm_label_pattern(code: str, framework: str) -> dict | None:
    """
    Utilise un LLM pour labelliser le feature_type d'un bloc de code.

    Returns:
        dict avec "feature_type" et "file_role", ou None si erreur
    """
    if not OPENROUTER_API_KEY:
        return None

    prompt = f"""Tu es un classificateur de code. Identifie le type de feature et le rôle du fichier.

Framework : {framework}
Code :
```
{code[:2000]}
```

Réponds UNIQUEMENT en JSON avec ces deux champs :
{{
  "feature_type": "<un parmi : {', '.join(FEATURE_TYPES)}>",
  "file_role": "<un parmi : {', '.join(FILE_ROLES)}>"
}}

Si le code ne correspond à aucun type reconnu, réponds : {{"feature_type": "unknown", "file_role": "utils"}}"""

    try:
        resp = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": EXTRACTOR_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 100,
                "temperature": 0,
            },
            timeout=20.0,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()

        # Parse JSON (parfois le LLM ajoute des backticks)
        if "```" in content:
            content = content.split("```")[1].replace("json", "").strip()

        return json.loads(content)
    except Exception:
        return None


def extract_patterns_from_repo(repo_dir: Path) -> list[RawPattern]:
    """
    Extrait tous les patterns d'un repo local.

    Args:
        repo_dir: Path vers le repo téléchargé

    Returns:
        Liste de RawPattern bruts (avant normalisation)
    """
    repo_url = f"https://github.com/{repo_dir.parent.name}/{repo_dir.name}"
    framework = _detect_framework(repo_dir)
    language = _detect_language(repo_dir)

    print(f"  Extracteur : {repo_dir.name} ({framework}/{language})")

    if framework == "unknown" or language == "unknown":
        print(f"  ⚠️  Framework/langage non détecté — skip.")
        return []

    patterns: list[RawPattern] = []
    py_files = list(repo_dir.rglob("*.py"))

    for file_path in py_files:
        # Skip fichiers trop gros ou générés
        try:
            source = file_path.read_text(errors="ignore")
        except OSError:
            continue

        if len(source) > 50_000 or len(source) < 100:  # skip vides ou énormes
            continue

        file_role_guess = _guess_file_role(file_path)
        blocks = _extract_python_blocks(source)

        for block in blocks:
            # Labellisation LLM
            label = _llm_label_pattern(block, framework)

            if label is None:
                # Fallback : utiliser la détection heuristique
                feature_type = _heuristic_feature_type(block)
                file_role = file_role_guess
            else:
                feature_type = label.get("feature_type", "unknown")
                file_role = label.get("file_role", file_role_guess)

            if feature_type == "unknown":
                continue

            patterns.append(
                RawPattern(
                    feature_type=feature_type,
                    framework=framework,
                    language=language,
                    file_role=file_role,
                    raw_code=block,
                    source_repo=repo_url,
                    source_file=str(file_path.relative_to(repo_dir)),
                )
            )

    print(f"  ✅ {len(patterns)} patterns extraits de {repo_dir.name}")
    return patterns


def _heuristic_feature_type(code: str) -> str:
    """Détection heuristique du feature_type par mots-clés."""
    code_lower = code.lower()

    heuristics = {
        "auth_jwt": ["jwt", "token", "bearer", "bcrypt", "hash_password", "verify_password"],
        "websocket": ["websocket", "ws://", "wss://", "websocketdisconnect"],
        "redis_pubsub": ["redis", "pubsub", "publish", "subscribe", "aioredis"],
        "ml_inference": ["predict", "inference", "model.predict", "torch", "tensorflow"],
        "background_task": ["backgroundtask", "celery", "background_tasks"],
        "discord_bot": ["discord", "commands.bot", "discord.ext"],
        "crud": ["@router.get", "@router.post", "@router.put", "@router.delete", "apirouter"],
        "database_setup": ["create_engine", "sessionmaker", "declarativebase", "init_db"],
        "testing": ["def test_", "pytest", "testclient", "fixture"],
    }

    for feature, keywords in heuristics.items():
        if any(kw in code_lower for kw in keywords):
            return feature

    return "unknown"
