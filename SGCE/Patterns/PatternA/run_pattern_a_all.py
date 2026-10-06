# -*- coding: utf-8 -*-

"""
SGCE — GLOBAL RUNNER PATTERN A
===============================

Exécute séquentiellement :

A1 → A2 → A3 → A4 → A5 → A6

Chaque Pattern utilise la sortie corrigée du Pattern précédent.

Chaîne :
SortieJson_Postprocessing
    ↓
A1
    ↓
PatternA1/corrected
    ↓
A2
    ↓
PatternA2/corrected
    ↓
A3
    ↓
PatternA3/corrected
    ↓
A4
    ↓
PatternA4/corrected
    ↓
A5
    ↓
PatternA5/corrected
    ↓
A6
    ↓
PatternA6/corrected
"""

import subprocess
import sys
import time
from pathlib import Path


# ============================================================
# 1. PATHS
# ============================================================

PATTERN_A_DIR = Path(__file__).resolve().parent

PIPELINE = [
    {
        "name": "A1",
        "description": "TRAITEMENT + POSOLOGIE",
        "folder": PATTERN_A_DIR / "PatternA1",
        "runner": "run_pattern_a1_all.py",
    },
    {
        "name": "A2",
        "description": "COMORBIDITE_ANTECEDENT + CONTEXTE_ACQUISITION",
        "folder": PATTERN_A_DIR / "PatternA2",
        "runner": "run_pattern_a2_all.py",
    },
    {
        "name": "A3",
        "description": "IMAGERIE_PROCEDURE + FOYER_INFECTIEUX",
        "folder": PATTERN_A_DIR / "PatternA3",
        "runner": "run_pattern_a3_all.py",
    },
    {
        "name": "A4",
        "description": "IMAGERIE_PROCEDURE + DEFAILLANCE_ORGANE",
        "folder": PATTERN_A_DIR / "PatternA4",
        "runner": "run_pattern_a4_all.py",
    },
    {
        "name": "A5",
        "description": "IMAGERIE_PROCEDURE + COMORBIDITE_ANTECEDENT",
        "folder": PATTERN_A_DIR / "PatternA5",
        "runner": "run_pattern_a5_all.py",
    },
    {
        "name": "A6",
        "description": "DONNEE_PATIENT + SYMPTOME",
        "folder": PATTERN_A_DIR / "PatternA6",
        "runner": "run_pattern_a6_all.py",
    },
]


# ============================================================
# 2. EXECUTION D'UN PATTERN
# ============================================================

def run_pattern(pattern):

    name = pattern["name"]
    description = pattern["description"]
    folder = pattern["folder"]
    runner = folder / pattern["runner"]

    print()
    print("=" * 90)
    print(f"SGCE — PATTERN {name}")
    print(description)
    print("=" * 90)

    if not folder.exists():
        raise FileNotFoundError(
            f"Dossier introuvable : {folder}"
        )

    if not runner.exists():
        raise FileNotFoundError(
            f"Runner introuvable : {runner}"
        )

    start = time.time()

    result = subprocess.run(
        [sys.executable, str(runner)],
        cwd=str(folder),
    )

    duration = time.time() - start

    if result.returncode != 0:
        raise RuntimeError(
            f"PATTERN {name} a échoué "
            f"(code={result.returncode})."
        )

    print()
    print(f"[OK] PATTERN {name}")
    print(f"Durée : {duration:.2f} secondes")


# ============================================================
# 3. MAIN
# ============================================================

def main():

    global_start = time.time()

    print()
    print("=" * 90)
    print("SGCE — GLOBAL PATTERN A PIPELINE")
    print("=" * 90)

    print()
    print("Ordre d'exécution :")
    print()
    print("A1 → A2 → A3 → A4 → A5 → A6")
    print()

    completed = []

    try:

        for pattern in PIPELINE:

            run_pattern(pattern)

            completed.append(pattern["name"])

    except Exception as exc:

        print()
        print("=" * 90)
        print("PIPELINE PATTERN A INTERROMPU")
        print("=" * 90)

        print()
        print(f"Patterns terminés : {completed}")
        print()
        print(f"Erreur : {exc}")
        print()

        sys.exit(1)

    total_duration = time.time() - global_start

    print()
    print("=" * 90)
    print("PATTERN A — PIPELINE TERMINÉ AVEC SUCCÈS")
    print("=" * 90)

    print()
    print("Patterns exécutés :")
    print("A1 → A2 → A3 → A4 → A5 → A6")

    print()
    print(
        f"Durée totale : "
        f"{total_duration:.2f} secondes"
    )

    print()
    print(
        "Sortie clinique finale : "
        f"{PATTERN_A_DIR / 'PatternA6' / 'corrected'}"
    )

    print()


# ============================================================
# 4. ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()