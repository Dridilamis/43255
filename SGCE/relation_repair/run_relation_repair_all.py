# -*- coding: utf-8 -*-
import subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
PIPELINE=[
"relation_repair_candidate_builder.py",
"relation_repair_agent.py",
"relation_repair_decision_validator.py",
"relation_repair_batch_impact_validator.py",
"relation_repair_batch_safe_corrector.py",
"relation_repair_batch_safe_post_validator.py",
]
def main():
    print("="*108);print("TRACE / SGCE - RELATION REPAIR COMPLET");print("="*108)
    for name in PIPELINE:
        p=HERE/name
        print("\n"+"="*108);print("RUNNING :",name);print("="*108)
        r=subprocess.run([sys.executable,str(p)],cwd=str(HERE))
        if r.returncode!=0: raise RuntimeError(f"Échec de {name} (code={r.returncode})")
        print("[OK]",name)
    print("\n"+"="*108);print("RELATION REPAIR TERMINÉ AVEC SUCCÈS");print("="*108)
    print("Sortie clinique finale :",HERE/"corrected")
    print("Post-validation        :",HERE/"post_validation")
if __name__=="__main__":main()
