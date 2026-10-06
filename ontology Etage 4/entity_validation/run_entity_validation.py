# -*- coding: utf-8 -*-
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable

STEPS = [
    ROOT / "audit_initial" / "final_ontology_audit.py",
    ROOT / "entity_validation_candidate_builder.py",
    ROOT / "entity_validation_classifier.py",
    ROOT / "entity_validation_validator.py",
    ROOT / "entity_validation_safe_corrector.py",
]

def main():
    print("=" * 110)
    print("TRACE — ETAGE 4 / ENTITY VALIDATION")
    print("=" * 110)
    print(f"Dossier : {ROOT}")
    print(f"Python  : {PYTHON}")

    start = time.perf_counter()
    for i, script in enumerate(STEPS, 1):
        print("\n" + "=" * 110)
        print(f"[{i}/{len(STEPS)}] {script.name}")
        print("=" * 110)

        if not script.exists():
            raise FileNotFoundError(f"Script introuvable : {script}")

        r = subprocess.run(
            [PYTHON, str(script)],
            cwd=str(script.parent),
            check=False,
        )
        if r.returncode != 0:
            print(f"ECHEC : {script.name} (code {r.returncode})")
            raise SystemExit(r.returncode)

        print(f"[OK] {script.name}")

    final_dir = ROOT / "entity_validation_safe_corrected"
    print("\n" + "=" * 110)
    print("ENTITY VALIDATION TERMINE")
    print("=" * 110)
    print(f"Sortie clinique : {final_dir}")
    print(f"Durée totale    : {time.perf_counter() - start:.2f} s")

if __name__ == "__main__":
    main()
