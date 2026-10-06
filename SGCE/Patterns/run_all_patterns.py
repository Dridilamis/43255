# -*- coding: utf-8 -*-
"""
SGCE - GLOBAL PATTERNS RUNNER
=============================

Exécute automatiquement :

Pattern A
    ↓
Pattern B
    ↓
Pattern C
    ↓
Pattern D

Ordre strict :
A → B → C → D

Le pipeline s'arrête immédiatement si une étape échoue.
"""

import subprocess
import sys
import time
from pathlib import Path


# ============================================================
# PATHS
# ============================================================

PATTERNS_DIR = Path(__file__).resolve().parent

PIPELINE = [
    {
        "name": "PATTERN A",
        "runner": (
            PATTERNS_DIR
            / "PatternA"
            / "run_pattern_a_all.py"
        ),
    },
    {
        "name": "PATTERN B",
        "runner": (
            PATTERNS_DIR
            / "PatternB"
            / "run_pattern_b_all.py"
        ),
    },
    {
        "name": "PATTERN C",
        "runner": (
            PATTERNS_DIR
            / "PatternC"
            / "run_pattern_c_all.py"
        ),
    },
    {
        "name": "PATTERN D",
        "runner": (
            PATTERNS_DIR
            / "PatternD"
            / "run_pattern_d_all.py"
        ),
    },
]


# ============================================================
# RUN ONE PATTERN
# ============================================================

def run_pattern(name, runner):

    if not runner.exists():
        raise FileNotFoundError(
            f"Runner introuvable pour {name} :\n"
            f"{runner}"
        )

    print("\n")
    print("=" * 100)
    print(f"START : {name}")
    print("=" * 100)
    print(f"Runner : {runner}")
    print()

    start = time.time()

    result = subprocess.run(
        [sys.executable, str(runner)],
        cwd=str(runner.parent),
    )

    duration = time.time() - start

    if result.returncode != 0:
        print()
        print("=" * 100)
        print(f"ECHEC : {name}")
        print("=" * 100)
        print(
            f"Code retour : {result.returncode}"
        )
        print(
            f"Durée       : {duration:.2f} sec"
        )

        raise RuntimeError(
            f"Le pipeline SGCE a été arrêté sur {name}."
        )

    print()
    print("-" * 100)
    print(f"[OK] {name}")
    print(f"Durée : {duration:.2f} sec")
    print("-" * 100)

    return duration


# ============================================================
# MAIN
# ============================================================

def main():

    global_start = time.time()

    print("=" * 100)
    print("SGCE - STRUCTURAL GROUNDING")
    print("GLOBAL PATTERNS PIPELINE")
    print("=" * 100)

    print()
    print("Ordre d'exécution :")
    print()
    print("Pattern A")
    print("   ↓")
    print("Pattern B")
    print("   ↓")
    print("Pattern C")
    print("   ↓")
    print("Pattern D")
    print()

    durations = {}

    for item in PIPELINE:

        duration = run_pattern(
            item["name"],
            item["runner"],
        )

        durations[item["name"]] = duration

    total_duration = (
        time.time()
        - global_start
    )

    final_output = (
        PATTERNS_DIR
        / "PatternD"
        / "corrected"
    )

    final_validation = (
        PATTERNS_DIR
        / "PatternD"
        / "post_validation"
    )

    print("\n")
    print("=" * 100)
    print("TOUS LES PATTERNS SGCE TERMINÉS AVEC SUCCÈS")
    print("=" * 100)

    print()
    print("Résumé des durées :")

    for name, duration in durations.items():
        print(
            f"  {name:<15} : "
            f"{duration:.2f} sec"
        )

    print()
    print(
        f"Durée totale : "
        f"{total_duration:.2f} sec"
    )

    print()
    print(
        f"Sortie clinique finale : "
        f"{final_output}"
    )

    print(
        f"Post-validation finale : "
        f"{final_validation}"
    )

    print()
    print("=" * 100)


if __name__ == "__main__":
    main()