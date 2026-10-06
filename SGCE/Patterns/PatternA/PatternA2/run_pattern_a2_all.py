# -*- coding: utf-8 -*-
import subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PIPELINE = [
    "pattern_a2_detector.py",
    "pattern_a2_validator.py",
    "pattern_a2_auto_corrector.py",
    "pattern_a2_post_validator.py",
]

def main():
    print("="*80)
    print("SGCE - PATTERN A2")
    print("COMORBIDITE_ANTECEDENT -> CONTEXTE_ACQUISITION")
    print("="*80)
    for name in PIPELINE:
        path = HERE / name
        print("\n" + "="*80)
        print("RUNNING :", name)
        print("="*80)
        if not path.exists():
            raise FileNotFoundError(f"Script introuvable : {path}")
        r = subprocess.run([sys.executable, str(path)], cwd=str(HERE))
        if r.returncode != 0:
            raise RuntimeError(f"Échec de {name} (code={r.returncode})")
        print("[OK]", name)
    print("\n" + "="*80)
    print("PATTERN A2 TERMINÉ AVEC SUCCÈS")
    print("="*80)
    print("Sortie :", HERE / "corrected")

if __name__ == "__main__":
    main()
