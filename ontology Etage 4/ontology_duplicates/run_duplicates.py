# -*- coding: utf-8 -*-
from pathlib import Path
import subprocess, sys, time
ROOT=Path(__file__).resolve().parent
STEPS=[
    ("DUPLICATE RELATIONS",ROOT/"duplicate_relations"/"run_duplicate_relations.py"),
    ("DUPLICATE ENTITIES",ROOT/"duplicate_entities"/"run_duplicate_entities.py"),
]
def main():
    start=time.perf_counter()
    print("="*108); print("TRACE — ETAGE 4 / DUPLICATES"); print("="*108)
    for i,(label,s) in enumerate(STEPS,1):
        print("\n"+"#"*108); print(f"[{i}/{len(STEPS)}] {label}"); print("#"*108)
        r=subprocess.run([sys.executable,str(s)],cwd=str(s.parent))
        if r.returncode:
            print(f"\n[STOP] {label} a échoué. L'étape suivante n'est pas lancée.")
            raise SystemExit(r.returncode)
    print("\n"+"="*108); print("PIPELINE DUPLICATES TERMINE — PASS"); print("="*108)
    print("Sortie officielle :",ROOT/"duplicate_entities"/"duplicate_entity_safe_merged")
    print(f"Duree totale      : {time.perf_counter()-start:.2f} s")
if __name__=="__main__": main()
