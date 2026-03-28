"""
graph.py — Point d'entrée LangGraph V6.

Usage:
    cd pipeline/
    source .venv/bin/activate
    python graph.py chemin/vers/prd.md
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from langgraph.graph import END, StateGraph

load_dotenv()

# Nodes
from nodes.analyst import analyst_node
from nodes.delta_analyzer import delta_analyzer_node
from nodes.deployer import deployer_node
from nodes.evaluator import evaluator_node
from nodes.family_classifier import family_classifier_node
from nodes.fixer import fixer_node
from nodes.generator import generator_node
from nodes.researcher import researcher_node
from nodes.setup import setup_node
from nodes.strategist import strategist_node
from state import WaleState


def should_continue(state: WaleState) -> str:
    """
    Superviseur V6 — routing enrichi.
    Toujours Python, toujours déterministe.
    """
    # Convergence ou max itérations
    if state.get("converged"):
        return "deploy"
    if state.get("iteration", 0) >= state.get("max_iterations", 10):
        return "deploy"

    # Routing KB + familles (nouveau V6)
    if not state.get("family_identified"):
        return "family_classifier"
    if not state.get("delta_analyzed"):
        return "delta_analyzer"
    if not state.get("kb_patterns_loaded"):
        return "researcher"

    return "fix"


def build_graph() -> StateGraph:
    """Construit le graphe LangGraph V6."""
    graph = StateGraph(WaleState)

    # Nodes
    graph.add_node("analyst", analyst_node)
    graph.add_node("family_classifier", family_classifier_node)
    graph.add_node("strategist", strategist_node)
    graph.add_node("delta_analyzer", delta_analyzer_node)
    graph.add_node("researcher", researcher_node)
    graph.add_node("generator", generator_node)
    graph.add_node("setup", setup_node)
    graph.add_node("evaluator", evaluator_node)
    graph.add_node("fixer", fixer_node)
    graph.add_node("deployer", deployer_node)

    # Edges linéaires
    graph.set_entry_point("analyst")
    graph.add_edge("analyst", "family_classifier")
    graph.add_edge("family_classifier", "strategist")
    graph.add_edge("strategist", "delta_analyzer")
    graph.add_edge("delta_analyzer", "researcher")
    graph.add_edge("researcher", "generator")
    graph.add_edge("generator", "setup")
    graph.add_edge("setup", "evaluator")
    graph.add_edge("deployer", END)

    # Edge conditionnel depuis evaluator
    graph.add_conditional_edges(
        "evaluator",
        should_continue,
        {
            "family_classifier": "family_classifier",
            "delta_analyzer": "delta_analyzer",
            "researcher": "researcher",
            "fix": "fixer",
            "deploy": "deployer",
        },
    )

    # Fixer → generator (boucle de correction)
    graph.add_edge("fixer", "generator")

    return graph.compile()


def run_pipeline(prd_path: str) -> WaleState:
    """Lance le pipeline sur un PRD."""
    prd_file = Path(prd_path)
    if not prd_file.exists():
        print(f"❌ PRD non trouvé : {prd_path}")
        sys.exit(1)

    initial_state: WaleState = {
        "prd_path": str(prd_file),
        "prd_content": prd_file.read_text(encoding="utf-8"),
        "iteration": 0,
        "max_iterations": int(os.environ.get("MAX_ITERATIONS", "10")),
        "target_score": float(os.environ.get("TARGET_SCORE", "80")),
        "converged": False,
        "family_identified": False,
        "delta_analyzed": False,
        "kb_patterns_loaded": False,
        "run_id": str(uuid.uuid4())[:8],
    }

    print("=" * 60)
    print(f"WAL-E LAB V6 — Run {initial_state['run_id']}")
    print(f"PRD : {prd_path}")
    print("=" * 60)

    app = build_graph()
    final_state = app.invoke(initial_state)

    print("\n" + "=" * 60)
    print(f"Score final : {final_state.get('score', 0):.1f}/100")
    print(f"  Type A (ruff+pyright) : {final_state.get('score_a', 0):.1f}")
    print(f"  Type B (pytest)       : {final_state.get('score_b', 0):.1f}")
    print(f"  Type C (schemathesis) : {final_state.get('score_c', 0):.1f}")
    print(f"Famille : {final_state.get('family', 'unknown')}")
    print(f"GitHub  : {final_state.get('github_repo_url', 'non déployé')}")
    print("=" * 60)

    return final_state


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python graph.py <prd_path>")
        sys.exit(1)

    run_pipeline(sys.argv[1])
