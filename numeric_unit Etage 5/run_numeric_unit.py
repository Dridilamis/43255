# -*- coding: utf-8 -*-

from pathlib import Path
import subprocess
import sys
import json

ROOT = Path(__file__).resolve().parent

SCRIPTS = [
    "numeric_unit_candidate_builder.py",
    "numeric_unit_validator.py",
    "numeric_unit_safe_corrector.py",
    "numeric_unit_post_validator.py",
]

print("=" * 110)
print("TRACE - NUMERIC + UNIT VALIDATION - ETAGE 5 V7.1")
print("=" * 110)
print(f"Dossier : {ROOT}")

for script_name in SCRIPTS:

    script_path = ROOT / script_name

    print()
    print("=" * 110)
    print(f">>> LANCEMENT : {script_name}")
    print("=" * 110)

    if not script_path.is_file():
        print(f"ERREUR : script introuvable : {script_path}")
        raise SystemExit(1)

    result = subprocess.run(
        [sys.executable, str(script_path)],
        check=False,
    )

    if result.returncode != 0:
        print()
        print(f"ECHEC : {script_name}")
        print(f"Code retour : {result.returncode}")
        raise SystemExit(result.returncode)

    print(f"OK : {script_name}")


# ------------------------------------------------------------
# VERIFICATION DU RAPPORT FINAL
# ------------------------------------------------------------

REPORT = (
    ROOT
    / "post_validation"
    / "numeric_unit_post_validation_report.json"
)

print()
print("=" * 110)
print("VERIFICATION FINALE")
print("=" * 110)

if not REPORT.is_file():
    print(f"ERREUR : rapport final introuvable : {REPORT}")
    raise SystemExit(1)

with REPORT.open(
    "r",
    encoding="utf-8",
) as f:
    data = json.load(f)

status = (
    data
    .get("summary", {})
    .get("status")
)

print(f"Statut post-validation : {status}")

if status != "PASS":
    print()
    print("NUMERIC + UNIT ETAGE 5 V7.1 : FAIL")
    raise SystemExit(1)

print()
print("=" * 110)
print("NUMERIC + UNIT ETAGE 5 V7.1 : PASS")
print("=" * 110)
print(f"Rapport : {REPORT}")