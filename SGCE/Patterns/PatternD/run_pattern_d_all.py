# -*- coding: utf-8 -*-
"""Runner complet SGCE Pattern D."""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

PIPELINE = [
    "pattern_d_anomaly_audit.py",
    "pattern_d_detector.py",
    "pattern_d_validator.py",
    "pattern_d_generic_corrector.py",
    "pattern_d_post_validator.py",
]

def run_script(name):
    script = HERE / name
    if not script.exists():
        raise FileNotFoundError(f"Script introuvable : {script}")

    print("\n" + "=" * 88)
    print(f"RUNNING : {name}")
    print("=" * 88)

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(HERE),
    )

    if result.returncode != 0:
        raise RuntimeError(f"Échec de {name} (code={result.returncode})")

    print(f"[OK] {name}")

def main():
    print("=" * 88)
    print("SGCE - PATTERN D")
    print("Violation de signature relationnelle (Domain-Range Mismatch)")
    print("=" * 88)

    for script in PIPELINE:
        run_script(script)

    print("\n" + "=" * 88)
    print("PATTERN D TERMINÉ AVEC SUCCÈS")
    print("=" * 88)
    print(f"Sortie clinique finale : {HERE / 'corrected'}")
    print(f"Post-validation        : {HERE / 'post_validation'}")

if __name__ == "__main__":
    main()
