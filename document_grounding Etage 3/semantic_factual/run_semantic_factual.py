# -*- coding: utf-8 -*-
"""TRACE — Etage 3 / Semantic-Factual : runner complet."""
from pathlib import Path
import subprocess, sys, time

ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable

SCRIPTS = [
    "semantic_factual_candidate_builder.py",
    "semantic_factual_classifier.py",
    "semantic_factual_validator.py",
    "semantic_factual_review_analyzer.py",
    "semantic_factual_second_pass.py",
    "semantic_factual_second_pass_validator.py",
    "semantic_factual_third_pass.py",
    "semantic_factual_third_pass_validator.py",
    "semantic_factual_contradiction_validator.py",
    "semantic_factual_safe_corrector.py",
    "semantic_factual_post_validator.py",
]

def main():
    print("="*108)
    print("TRACE - ETAGE 3 / SEMANTIC-FACTUAL - PIPELINE COMPLET")
    print("="*108)
    print(f"Dossier : {ROOT}")
    print(f"Python  : {PYTHON}")

    missing=[x for x in SCRIPTS if not (ROOT/x).exists()]
    if missing:
        raise FileNotFoundError("Scripts manquants : "+", ".join(missing))

    start_all=time.perf_counter()
    for i,name in enumerate(SCRIPTS,1):
        print("\n"+"="*108)
        print(f"[{i}/{len(SCRIPTS)}] {name}")
        print("="*108)
        start=time.perf_counter()
        r=subprocess.run([PYTHON,str(ROOT/name)],cwd=str(ROOT))
        if r.returncode!=0:
            raise SystemExit(f"ECHEC : {name} (code {r.returncode})")
        print(f"[OK] {name} - {time.perf_counter()-start:.2f} s")

    out=ROOT/"semantic_factual_safe_corrected"
    print("\n"+"="*108)
    print("SEMANTIC-FACTUAL TERMINE")
    print("="*108)
    print(f"Sortie clinique : {out}")
    print(f"Durée totale    : {time.perf_counter()-start_all:.2f} s")

if __name__=="__main__":
    main()
