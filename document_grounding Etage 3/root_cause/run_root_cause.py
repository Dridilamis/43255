# -*- coding: utf-8 -*-
"""TRACE — Etage 3 / Root Cause : runner complet."""
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable

SCRIPTS = [
    "root_cause_entity_candidate_builder.py",
    "root_cause_entity_validator.py",
    "root_cause_entity_safe_corrector.py",
    "root_cause_entity_post_validator.py",
]

def main():
    print("=" * 104)
    print("TRACE - ETAGE 3 / ROOT CAUSE - PIPELINE COMPLET")
    print("=" * 104)
    print(f"Dossier : {ROOT}")
    print(f"Python  : {PYTHON}")

    missing = [name for name in SCRIPTS if not (ROOT / name).exists()]
    if missing:
        raise FileNotFoundError("Scripts manquants : " + ", ".join(missing))

    start_all = time.perf_counter()
    for i, name in enumerate(SCRIPTS, 1):
        print("\n" + "=" * 104)
        print(f"[{i}/{len(SCRIPTS)}] {name}")
        print("=" * 104)
        start = time.perf_counter()
        r = subprocess.run([PYTHON, str(ROOT / name)], cwd=str(ROOT))
        if r.returncode != 0:
            raise SystemExit(f"ECHEC : {name} (code {r.returncode})")
        print(f"[OK] {name} - {time.perf_counter()-start:.2f} s")

    out = ROOT / "root_cause_entity_safe_corrected"
    print("\n" + "=" * 104)
    print("ROOT CAUSE TERMINE")
    print("=" * 104)
    print(f"Sortie clinique : {out}")
    print(f"Durée totale    : {time.perf_counter()-start_all:.2f} s")

if __name__ == "__main__":
    main()
