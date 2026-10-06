# -*- coding: utf-8 -*-
"""Runner global SGCE Pattern A3."""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

PIPELINE = [
    "pattern_a3_detector.py",
    "pattern_a3_validator.py",
    "pattern_a3_auto_corrector.py",
    "pattern_a3_post_validator.py",
]

def run_script(name):
    path = HERE / name
    if not path.exists():
        raise FileNotFoundError(f"Script introuvable : {path}")

    print("\n" + "=" * 80)
    print(f"RUNNING : {name}")
    print("=" * 80)

    result = subprocess.run(
        [sys.executable, str(path)],
        cwd=str(HERE),
    )

    if result.returncode != 0:
        raise RuntimeError(f"Échec de {name} (code={result.returncode})")

    print(f"[OK] {name}")

def main():
    print("=" * 80)
    print("SGCE - PATTERN A3")
    print("IMAGERIE_PROCEDURE -> FOYER_INFECTIEUX")
    print("=" * 80)

    for script in PIPELINE:
        run_script(script)

    print("\n" + "=" * 80)
    print("PATTERN A3 TERMINÉ AVEC SUCCÈS")
    print("=" * 80)
    print("Sortie clinique finale :", HERE / "corrected")
    print("Post-validation        :", HERE / "post_validation")

if __name__ == "__main__":
    main()
