# -*- coding: utf-8 -*-
"""TRACE — ETAGE 8 V2.1 — Runner global."""
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
SCRIPTS = [
    "confidence_candidate_builder.py",
    "confidence_evidence_analyzer.py",
    "confidence_assessor.py",
    "confidence_validator.py",
    "confidence_safe_annotator.py",
    "confidence_post_validator.py",
]

print("=" * 110)
print("TRACE - EVIDENCE-BASED CONFIDENCE ASSESSMENT - ETAGE 8 V2.1")
print("=" * 110)
print("Dossier :", HERE)

for script in SCRIPTS:
    path = HERE / script
    print("\n>>>", script)
    if not path.exists():
        raise SystemExit(f"ECHEC : script introuvable : {path}")
    result = subprocess.run([sys.executable, str(path)], cwd=str(HERE))
    if result.returncode:
        raise SystemExit(f"ECHEC : {script} (code {result.returncode})")

print("\nCONFIDENCE ETAGE 8 V2.1 : PASS")
