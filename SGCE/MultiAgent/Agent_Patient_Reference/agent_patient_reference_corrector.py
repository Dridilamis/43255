# -*- coding: utf-8 -*-
from pathlib import Path
import json, re, shutil, hashlib
from collections import Counter

AGENT_DIR = Path(__file__).resolve().parent
MULTIAGENT_DIR = AGENT_DIR.parent
SGCE_DIR = MULTIAGENT_DIR.parent
BASE_DIR = SGCE_DIR.parent
M = MULTIAGENT_DIR
PATTERNS_DIR = SGCE_DIR / "Patterns"
CLINICAL_DIR = SGCE_DIR / "orphan_resolution" / "corrected"

def load_json(p):
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)

def save_json(p, x):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(x, ensure_ascii=False, indent=2), encoding="utf-8")

def eid(e):
    return e.get("identifiant_entite") or e.get("id") or e.get("entity_id")

def entities(doc):
    if isinstance(doc.get("global_entities"), list):
        return doc["global_entities"]
    z=[]
    for p in doc.get("pages",[]) or []: z += p.get("entities",[]) or []
    return z

def relations(doc):
    if isinstance(doc.get("global_relations"), list):
        return doc["global_relations"]
    z=[]
    for p in doc.get("pages",[]) or []: z += p.get("relations",[]) or []
    return z

def rsrc(r):
    return r.get("identifiant_entite_sujet") or r.get("from_id") or r.get("subject_id") or r.get("source")

def rtgt(r):
    return r.get("identifiant_entite_objet") or r.get("to_id") or r.get("object_id") or r.get("target")

INP=M/"outputs"/"agent_patient_reference_validated_decisions.json"
OUTDIR=M/"Agent_Patient_Reference"/"corrected"
REPORT=OUTDIR/"agent_patient_reference_correction_report.json"

def main():
    data=load_json(INP); ds=data.get("validated_decisions",[])
    if OUTDIR.exists(): shutil.rmtree(OUTDIR)
    OUTDIR.mkdir(parents=True)
    copied=0
    for p in CLINICAL_DIR.glob("*.json"):
        try:
            d=load_json(p)
            if any(k in d for k in ("pages","global_entities","global_relations")):
                shutil.copy2(p,OUTDIR/p.name);copied+=1
        except:pass
    # KEEP is intentionally a no-op. REVIEW/NONE is protected.
    ops=[]; protected=0
    for d in ds:
        if d.get("final_status")=="ACCEPT" and d.get("final_action")=="KEEP":
            ops.append({"candidate_id":d.get("candidate_id"),"document":d.get("document"),
                        "action":"KEEP","status":"VERIFIED_NO_CHANGE"})
        else: protected+=1
    save_json(REPORT,{"corrector":"agent_patient_reference_corrector",
                      "source_directory":str(CLINICAL_DIR),"output_directory":str(OUTDIR),
                      "summary":{"documents_copied":copied,"write_operations_applied":0,
                                 "keep_verified":len(ops),"protected_cases":protected,
                                 "documents_modified":0},"operations":ops})
    print("="*96);print("TRACE / SGCE - PATIENT / REFERENCE CORRECTOR");print("="*96)
    print(f"Source clinique                    : {CLINICAL_DIR}")
    print(f"Sortie clinique                    : {OUTDIR}")
    print(f"\nDocuments cliniques copiés         : {copied}")
    print(f"KEEP vérifiés                      : {len(ops)}")
    print(f"Cas protégés                       : {protected}")
    print("Opérations d'écriture appliquées   : 0")
    print("Documents modifiés                 : 0")
    print(f"\nRapport                            : {REPORT}")
    print("\nLes fichiers sources n'ont pas été modifiés.")
if __name__=="__main__": main()
