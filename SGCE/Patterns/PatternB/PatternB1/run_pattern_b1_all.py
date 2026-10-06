# -*- coding: utf-8 -*-
"""Runner complet SGCE Pattern B1."""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

PIPELINE = [
    "pattern_b1_detector.py",
    "pattern_b1_validator.py",
    "pattern_b1_generic_corrector.py",
    "pattern_b1_post_validator.py",
]

def run_script(name):
    script = HERE / name
    if not script.exists():
        raise FileNotFoundError(f"Script introuvable : {script}")

    print("\n" + "=" * 80)
    print(f"RUNNING : {name}")
    print("=" * 80)

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(HERE)
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Échec de {name} (code={result.returncode})"
        )

    print(f"[OK] {name}")

def main():
    print("=" * 80)
    print("SGCE - PATTERN B1")
    print("Entité manquante implicite - endpoint relationnel absent")
    print("=" * 80)

    for script in PIPELINE:
        run_script(script)

    print("\n" + "=" * 80)
    print("PATTERN B1 TERMINÉ AVEC SUCCÈS")
    print("=" * 80)
    print(f"Sortie clinique finale : {HERE / 'corrected'}")
    print(f"Post-validation        : {HERE / 'post_validation'}")

if __name__ == "__main__":
    main()
