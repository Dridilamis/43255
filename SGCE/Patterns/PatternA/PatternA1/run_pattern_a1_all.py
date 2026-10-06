# -*- coding: utf-8 -*-
"""
run_pattern_a1_all.py

Runner principal du Pattern A1
TRAITEMENT -> traitement_a_pour_posologie -> POSOLOGIE
"""

import subprocess
import sys
from pathlib import Path


PATTERN_A1_DIR = Path(__file__).resolve().parent

PIPELINE = [
    "pattern_a1_detector.py",
    "pattern_a1_validator.py",
    "pattern_a1_actionable_audit.py",
    "pattern_a1_auto_corrector.py",
    "pattern_a1_differential_post_validator.py",
]


def run_script(script_name):
    script_path = PATTERN_A1_DIR / script_name

    if not script_path.exists():
        raise FileNotFoundError(
            f"Script introuvable : {script_path}"
        )

    print()
    print("=" * 80)
    print(f"RUNNING : {script_name}")
    print("=" * 80)

    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(PATTERN_A1_DIR),
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Échec de {script_name} "
            f"(code={result.returncode})"
        )

    print(f"[OK] {script_name}")


def main():

    print("=" * 80)
    print("SGCE - PATTERN A1")
    print("TRAITEMENT -> POSOLOGIE")
    print("=" * 80)

    for script in PIPELINE:
        run_script(script)

    print()
    print("=" * 80)
    print("PATTERN A1 TERMINÉ AVEC SUCCÈS")
    print("=" * 80)

    print()
    print("Sortie clinique finale :")
    print(PATTERN_A1_DIR / "corrected")

    print()
    print("Post-validation :")
    print(PATTERN_A1_DIR / "post_validation")


if __name__ == "__main__":
    main()