# -*- coding: utf-8 -*-
"""TRACE / SGCE - Runner complet Pattern C."""
import subprocess, sys, time
from pathlib import Path

HERE=Path(__file__).resolve().parent
STEPS=[
    "pattern_c_detector.py",
    "pattern_c_validator.py",
    "pattern_c_generic_corrector.py",
    "pattern_c_post_validator.py",
]

def main():
    print("="*90)
    print("TRACE / SGCE - PATTERN C COMPLET")
    print("="*90)
    b2=HERE.parent/"PatternB"/"PatternB2"/"corrected"
    if not b2.exists():
        raise FileNotFoundError(f"Entrée Pattern B2 introuvable : {b2}")
    for name in STEPS:
        script=HERE/name
        if not script.exists():
            raise FileNotFoundError(f"Script introuvable : {script}")
        print("\n"+"="*90)
        print("RUNNING :",name)
        print("="*90)
        start=time.time()
        r=subprocess.run([sys.executable,str(script)],cwd=str(HERE))
        if r.returncode:
            raise RuntimeError(f"Échec de {name} (code={r.returncode})")
        print(f"[OK] {name} — {time.time()-start:.2f} sec")
    corrected=HERE/"corrected"
    if not corrected.exists():
        raise FileNotFoundError(f"Sortie Pattern C non créée : {corrected}")
    print("\n"+"="*90)
    print("PATTERN C TERMINÉ AVEC SUCCÈS")
    print("="*90)
    print("Sortie clinique finale :",corrected)
    print("Post-validation        :",HERE/"post_validation")

if __name__=="__main__":
    main()
