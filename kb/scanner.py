"""
scanner.py — Agent KB Scanner.

Parcourt GitHub, identifie les repos pertinents par stack,
les télécharge via gitingest ou l'API GitHub directe.

Entrée  : liste de repos (repos.py)
Sortie  : fichiers de code téléchargés dans ./raw_repos/{owner}/{repo}/
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import httpx

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
RAW_REPOS_DIR = Path("./raw_repos")
EXTENSIONS = {".py", ".ts", ".go", ".rs"}  # extensions à télécharger


def _github_headers() -> dict:
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    return headers


def _parse_repo_url(url: str) -> tuple[str, str]:
    """Extrait owner/repo depuis une URL GitHub."""
    parts = url.rstrip("/").split("/")
    # https://github.com/owner/repo
    if len(parts) >= 5 and "github.com" in parts[2]:
        return parts[3], parts[4]
    raise ValueError(f"URL GitHub invalide : {url}")


def _get_default_branch(owner: str, repo: str, client: httpx.Client) -> str:
    """Récupère la branche par défaut du repo."""
    resp = client.get(
        f"https://api.github.com/repos/{owner}/{repo}",
        headers=_github_headers(),
    )
    resp.raise_for_status()
    return resp.json().get("default_branch", "main")


def _get_repo_tree(
    owner: str, repo: str, branch: str, client: httpx.Client
) -> list[dict]:
    """Récupère l'arbre de fichiers du repo (récursif)."""
    resp = client.get(
        f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1",
        headers=_github_headers(),
    )
    resp.raise_for_status()
    return resp.json().get("tree", [])


def _download_file(
    owner: str,
    repo: str,
    path: str,
    dest: Path,
    client: httpx.Client,
) -> None:
    """Télécharge un fichier depuis l'API raw GitHub."""
    url = f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/{path}"
    resp = client.get(url, headers=_github_headers())
    if resp.status_code != 200:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(resp.text, encoding="utf-8")


def scan_repo(url: str, max_files: int = 200) -> Path | None:
    """
    Scanne et télécharge les fichiers de code d'un repo GitHub.

    Args:
        url:       URL GitHub du repo
        max_files: nombre max de fichiers à télécharger (évite les mega-repos)

    Returns:
        Path vers le dossier local du repo, ou None si erreur
    """
    try:
        owner, repo = _parse_repo_url(url)
    except ValueError as e:
        print(f"  ⚠️  {e}")
        return None

    dest_dir = RAW_REPOS_DIR / owner / repo
    if dest_dir.exists() and any(dest_dir.rglob("*.py")):
        print(f"  ✓  {owner}/{repo} déjà téléchargé — skip.")
        return dest_dir

    print(f"  ⬇️  Téléchargement {owner}/{repo}...")

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        try:
            branch = _get_default_branch(owner, repo, client)
            tree = _get_repo_tree(owner, repo, branch, client)
        except httpx.HTTPStatusError as e:
            print(f"  ❌ Erreur API {owner}/{repo} : {e.response.status_code}")
            return None

        # Filtrer les fichiers pertinents
        code_files = [
            item
            for item in tree
            if item.get("type") == "blob"
            and Path(item["path"]).suffix in EXTENSIONS
            and not any(
                skip in item["path"]
                for skip in ["test", "__pycache__", "node_modules", "vendor", ".git"]
            )
        ][:max_files]

        for i, item in enumerate(code_files):
            dest_file = dest_dir / item["path"]
            _download_file(owner, repo, item["path"], dest_file, client)
            if i % 20 == 0 and i > 0:
                time.sleep(0.5)  # rate limit gentil

    print(f"  ✅ {owner}/{repo} : {len(code_files)} fichiers téléchargés → {dest_dir}")
    return dest_dir


def scan_all(repo_list: list[dict], priority_only: bool = False) -> list[Path]:
    """
    Scanne tous les repos de la liste.

    Args:
        repo_list:     liste de dicts avec au moins {"url": "..."}
        priority_only: si True, ne scanne que les repos priority="priority"

    Returns:
        Liste des paths locaux des repos téléchargés
    """
    if priority_only:
        repo_list = [r for r in repo_list if r.get("priority") == "priority"]

    print(f"Scanner : {len(repo_list)} repos à traiter...")
    paths = []
    for repo in repo_list:
        path = scan_repo(repo["url"])
        if path:
            paths.append(path)
        time.sleep(0.2)  # rate limit GitHub

    print(f"\n✅ Scanner terminé : {len(paths)}/{len(repo_list)} repos téléchargés.")
    return paths
