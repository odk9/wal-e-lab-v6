#!/usr/bin/env python3
"""
validate_scripts.py — Pré-validation complète des scripts d'ingestion.

Vérifie TOUTES les règles de la Charte Wal-e (U-5, F-1, F-2, F-3, G-1, G-2,
R-1, R-2, T-1, T-2, T-3, J-1, J-2, J-3) sur chaque pattern de chaque script.

Utilisation :
    python validate_scripts.py ingest_zap.py ingest_candle.py ...
    python validate_scripts.py --all    # valide tous les ingest_*.py du dossier

Retourne exit code 0 si tout passe, 1 si au moins une violation détectée.
"""

import ast
import glob
import importlib.util
import os
import re
import sys

# Importer check_charte_violations depuis kb_utils.py (même dossier)
_here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("kb_utils", os.path.join(_here, "kb_utils.py"))
kb_utils = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kb_utils)
check_charte_violations = kb_utils.check_charte_violations


def extract_patterns_from_script(filepath: str) -> list[dict]:
    """
    Extrait les patterns (normalized_code, function, language) d'un script d'ingestion
    en analysant le source Python via AST + regex.
    """
    with open(filepath, encoding="utf-8") as f:
        source = f.read()

    patterns = []

    # Stratégie : chercher les blocs dict contenant normalized_code.
    # Le "function" et "language" peuvent être AVANT ou APRÈS normalized_code
    # dans le même dict, donc on cherche dans une fenêtre autour du match.

    # Cherche aussi les constantes globales LANGUAGE = "xxx", FRAMEWORK = "xxx" etc.
    global_lang_match = re.search(r'LANGUAGE\s*=\s*["\']([^"\']+)["\']', source)
    global_lang = global_lang_match.group(1) if global_lang_match else None

    def find_field_in_context(context: str, field: str, default: str) -> str:
        """Cherche un champ "field": "value" dans le contexte, ou utilise la constante globale."""
        m = re.search(rf'"{field}"\s*:\s*["\']([^"\']+)["\']', context)
        if m:
            return m.group(1)
        # Fallback : constante globale pour language
        if field == "language" and global_lang:
            return global_lang
        return default

    # Méthode 1 : triple double-quoted strings
    for match in re.finditer(
        r'(?:\"normalized_code\"|normalized_code)\s*[:=]\s*"""(.*?)"""',
        source,
        re.DOTALL,
    ):
        code = match.group(1)
        # Fenêtre : 500 chars avant + 500 chars après le bloc normalized_code
        ctx_start = max(0, match.start() - 500)
        ctx_end = min(len(source), match.end() + 500)
        context = source[ctx_start:ctx_end]
        fn_name = find_field_in_context(context, "function", "?")
        lang = find_field_in_context(context, "language", "python")
        patterns.append({"code": code, "function": fn_name, "language": lang})

    # Méthode 2 : triple single-quoted strings
    for match in re.finditer(
        r"(?:\"normalized_code\"|normalized_code)\s*[:=]\s*'''(.*?)'''",
        source,
        re.DOTALL,
    ):
        code = match.group(1)
        ctx_start = max(0, match.start() - 500)
        ctx_end = min(len(source), match.end() + 500)
        context = source[ctx_start:ctx_end]
        fn_name = find_field_in_context(context, "function", "?")
        lang = find_field_in_context(context, "language", "python")
        patterns.append({"code": code, "function": fn_name, "language": lang})

    return patterns


def validate_script(filepath: str) -> list[str]:
    """Valide tous les patterns d'un script. Retourne les violations."""
    patterns = extract_patterns_from_script(filepath)
    all_violations = []

    if not patterns:
        all_violations.append(f"  ⚠️  Aucun pattern trouvé dans {os.path.basename(filepath)}")
        return all_violations

    for p in patterns:
        violations = check_charte_violations(p["code"], p["function"], p["language"])
        for v in violations:
            all_violations.append(f"  {v}")

    return all_violations


def main():
    if len(sys.argv) < 2:
        print("Usage: python validate_scripts.py [--all | script1.py script2.py ...]")
        sys.exit(1)

    if sys.argv[1] == "--all":
        scripts = sorted(glob.glob(os.path.join(_here, "ingest_*.py")))
    else:
        scripts = [os.path.join(_here, s) if not os.path.isabs(s) else s for s in sys.argv[1:]]

    total_violations = 0
    total_patterns = 0
    total_scripts = 0

    for script in scripts:
        if not os.path.exists(script):
            print(f"❌ Fichier introuvable : {script}")
            continue

        total_scripts += 1
        patterns = extract_patterns_from_script(script)
        total_patterns += len(patterns)
        violations = validate_script(script)

        name = os.path.basename(script)
        if violations and not violations[0].startswith("  ⚠️"):
            print(f"❌ {name} — {len(violations)} violation(s) :")
            for v in violations:
                print(v)
            total_violations += len(violations)
        elif violations:
            print(f"⚠️  {name} — {violations[0].strip()}")
        else:
            print(f"✅ {name} — {len(patterns)} patterns, 0 violations")

    print()
    print(f"{'=' * 50}")
    print(f"  Scripts vérifiés : {total_scripts}")
    print(f"  Patterns scannés : {total_patterns}")
    print(f"  Violations totales : {total_violations}")
    print(f"  Verdict : {'✅ PASS' if total_violations == 0 else '❌ FAIL'}")
    print(f"{'=' * 50}")

    sys.exit(0 if total_violations == 0 else 1)


if __name__ == "__main__":
    main()
