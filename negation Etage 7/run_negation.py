# -*- coding: utf-8 -*-
from pathlib import Path
import subprocess, sys

HERE = Path(__file__).resolve().parent
SCRIPTS = [
    "negation_candidate_builder.py",
    "negation_scope_classifier.py",
    "negation_validator.py",
    "negation_safe_corrector.py",
    "negation_post_validator.py",
]
print("="*112)
print("TRACE - NEGATION VALIDATION - ETAGE 7 V2 SEMANTIC GUARD")
print("="*112)
print(f"Dossier : {HERE}")
for script in SCRIPTS:
    print(f"\n>>> {script}")
    r = subprocess.run([sys.executable, str(HERE/script)], cwd=str(HERE))
    if r.returncode != 0:
        raise SystemExit(f"ECHEC : {script}")
print("\nNEGATION ETAGE 7 V2 : PASS")
