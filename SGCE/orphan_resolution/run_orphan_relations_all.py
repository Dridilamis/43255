# -*- coding: utf-8 -*-
"""
TRACE / SGCE - ORPHAN RELATIONS GLOBAL RUNNER

Ordre :
1. Candidate Builder
2. Resolver
3. Decision Validator
4. Safe Corrector
5. Residual Corrector
6. Final Post-Validator
"""
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

PIPELINE = [
    "orphan_relation_candidate_builder.py",
    "orphan_relation_resolver.py",
    "orphan_relation_decision_validator.py",
    "orphan_relation_safe_corrector.py",
    "orphan_relation_residual_corrector.py",
    "orphan_relation_post_validator.py",
]

def run_script(name):
    script = HERE / name
    if not script.exists():
        raise FileNotFoundError(f"Script introuvable : {script}")

    print("\n" + "=" * 108)
    print(f"RUNNING : {name}")
    print("=" * 108)

    start = time.time()
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(HERE),
    )
    duration = time.time() - start

    if result.returncode != 0:
        raise RuntimeError(
            f"Échec de {name} (code={result.returncode})"
        )

    print(f"[OK] {name} ({duration:.2f} sec)")

def main():
    global_start = time.time()

    print("=" * 108)
    print("TRACE / SGCE - ORPHAN RELATIONS COMPLET")
    print("=" * 108)
    print("Entrée : relation_repair/corrected")
    print("Sortie : orphan_resolution/corrected (20 REVIEW conservés et routés vers Multi-Agent)")

    for name in PIPELINE:
        run_script(name)

    duration = time.time() - global_start

    print("\n" + "=" * 108)
    print("ORPHAN RELATIONS TERMINÉ AVEC SUCCÈS")
    print("=" * 108)
    print(f"Durée totale            : {duration:.2f} sec")
    print(f"Sortie clinique finale  : {HERE / 'corrected'}")
    print(f"Post-validation         : {HERE / 'post_validation'}")

if __name__ == "__main__":
    main()
