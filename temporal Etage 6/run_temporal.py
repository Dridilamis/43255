# -*- coding: utf-8 -*-
from pathlib import Path
import subprocess, sys, json
ROOT=Path(__file__).resolve().parent
SCRIPTS=["temporal_status_candidate_builder.py","temporal_status_classifier.py","temporal_status_validator.py","temporal_status_safe_corrector.py","temporal_status_post_validator.py"]
for s in SCRIPTS:
    print(f"\n>>> {s}")
    r=subprocess.run([sys.executable,str(ROOT/s)],cwd=ROOT)
    if r.returncode!=0: raise SystemExit(r.returncode)
report=ROOT/"post_validation"/"temporal_status_post_validation_report.json"
if report.exists():
    d=json.loads(report.read_text(encoding="utf-8")); status=d.get("summary",{}).get("status")
    if status!="PASS": raise SystemExit(f"Temporal post-validation: {status}")
print("\nTEMPORAL ETAGE 6 : PASS")
