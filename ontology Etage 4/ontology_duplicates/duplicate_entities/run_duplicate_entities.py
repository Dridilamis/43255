# -*- coding: utf-8 -*-
from pathlib import Path
import subprocess, sys, json, time
ROOT=Path(__file__).resolve().parent
STEPS=[
    ROOT/"duplicate_entity_candidate_builder.py",
    ROOT/"duplicate_entity_validator.py",
    ROOT/"duplicate_entity_safe_merger.py",
    ROOT/"duplicate_entity_post_validator.py",
]
def main():
    start=time.perf_counter()
    print("="*108); print("TRACE — ETAGE 4 / DUPLICATE ENTITIES"); print("="*108)
    for i,s in enumerate(STEPS,1):
        print("\n"+"="*108); print(f"[{i}/{len(STEPS)}] {s.name}"); print("="*108)
        r=subprocess.run([sys.executable,str(s)],cwd=str(ROOT))
        if r.returncode: raise SystemExit(r.returncode)
    report=ROOT/"post_validation"/"duplicate_entity_post_validation_report.json"
    if not report.exists(): raise SystemExit("Rapport post-validation introuvable.")
    status=json.loads(report.read_text(encoding="utf-8")).get("status")
    if status!="PASS": raise SystemExit("Duplicate Entities: post-validation FAIL. Pipeline arrêté.")
    print("\n"+"="*108); print("DUPLICATE ENTITIES TERMINE — PASS"); print("="*108)
    print("Sortie officielle :",ROOT/"duplicate_entity_safe_merged")
    print(f"Duree totale      : {time.perf_counter()-start:.2f} s")
if __name__=="__main__": main()
