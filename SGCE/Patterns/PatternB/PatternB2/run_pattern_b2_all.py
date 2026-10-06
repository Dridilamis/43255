# -*- coding: utf-8 -*-
"""TRACE / SGCE - Runner complet Pattern B2."""
import subprocess
import sys
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
PATTERN_B_DIR = HERE.parent
GLOBAL_POST = PATTERN_B_DIR / "pattern_b_post_validator.py"

STEPS = [
    HERE / "pattern_b2_detector.py",
    HERE / "pattern_b2_validator.py",
    HERE / "pattern_b2_actionability_validator.py",
    HERE / "pattern_b2_relation_grounding_validator.py",
    HERE / "pattern_b2_auto_corrector.py",
]

def run(script):
    if not script.exists():
        raise FileNotFoundError(f"Script introuvable : {script}")
    print("\n" + "="*96)
    print("RUNNING :", script.name)
    print("="*96)
    start=time.time()
    r=subprocess.run([sys.executable,str(script)],cwd=str(script.parent))
    if r.returncode:
        raise RuntimeError(f"Échec de {script.name} (code={r.returncode})")
    print(f"[OK] {script.name} — {time.time()-start:.2f} sec")

def main():
    print("="*96)
    print("TRACE / SGCE - PATTERN B2 COMPLET")
    print("="*96)

    b1_corrected = PATTERN_B_DIR / "PatternB1" / "corrected"
    if not b1_corrected.exists():
        raise FileNotFoundError(f"Entrée B1 corrigée introuvable : {b1_corrected}")

    for script in STEPS:
        run(script)

    corrected=HERE/"corrected"
    if not corrected.exists():
        raise FileNotFoundError(f"Sortie B2 non créée : {corrected}")

    # Post-validation globale B après la correction B2.
    run(GLOBAL_POST)

    print("\n"+"="*96)
    print("PATTERN B2 TERMINÉ AVEC SUCCÈS")
    print("="*96)
    print("Entrée B2       :", b1_corrected)
    print("Sortie B2       :", corrected)
    print("Post-validation :", PATTERN_B_DIR/"post_validation")

if __name__=="__main__":
    main()
