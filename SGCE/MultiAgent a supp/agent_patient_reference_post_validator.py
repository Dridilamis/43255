# -*- coding: utf-8 -*-
from pathlib import Path
import json, re, shutil, hashlib
from collections import Counter

BASE_DIR = Path(r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM\Reduction_hallucinations")
M = BASE_DIR / "MultiAgent"
CLINICAL_DIR = M / "agent_c_corrected"

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

AFTER=M/"agent_patient_reference_corrected"
CORR=AFTER/"agent_patient_reference_correction_report.json"
OUTDIR=M/"agent_patient_reference_post_validation"
REPORT=OUTDIR/"agent_patient_reference_post_validation_report.json"

def h(doc):
    return hashlib.sha256(json.dumps(doc,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def clinical(d):
    z={}
    for p in d.glob("*.json"):
        if p.name.endswith("_report.json"):continue
        try:
            x=load_json(p)
            if any(k in x for k in ("pages","global_entities","global_relations")):z[p.name]=x
        except:pass
    return z

def main():
    b=clinical(CLINICAL_DIR); a=clinical(AFTER)
    common=set(b)&set(a); changed=[n for n in common if h(b[n])!=h(a[n])]
    missing=set(b)-set(a); extra=set(a)-set(b)
    report=load_json(CORR)
    # This stage currently classifies only; therefore zero clinical mutations are expected.
    final=not changed and not missing and not extra
    OUTDIR.mkdir(parents=True,exist_ok=True)
    save_json(REPORT,{"validator":"agent_patient_reference_post_validator",
                      "status":"PASS" if final else "FAIL",
                      "summary":{"documents_checked":len(common),
                                 "documents_changed":len(changed),
                                 "unexpected_changes":len(changed),
                                 "missing_documents":len(missing),
                                 "extra_documents":len(extra),
                                 "keep_verified":report.get("summary",{}).get("keep_verified",0)},
                      "changed_documents":sorted(changed),
                      "missing_documents":sorted(missing),"extra_documents":sorted(extra)})
    print("="*96);print("TRACE / SGCE - PATIENT / REFERENCE POST-VALIDATION");print("="*96)
    print(f"AVANT                              : {CLINICAL_DIR}")
    print(f"APRES                              : {AFTER}")
    print(f"\nDocuments vÃ©rifiÃ©s                 : {len(common)}")
    print(f"Documents modifiÃ©s                 : {len(changed)}")
    print(f"Modifications inattendues          : {len(changed)}")
    print(f"Docs manquants APRES               : {len(missing)}")
    print(f"Docs supplÃ©mentaires APRES         : {len(extra)}")
    print(f"\nSTATUT FINAL                       : {'PASS' if final else 'FAIL'}")
    print(f"\nRapport                            : {REPORT}")
    print("\nAucune donnÃ©e clinique n'a Ã©tÃ© modifiÃ©e par ce post-validateur.")
if __name__=="__main__": main()

