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

INP=M/"outputs"/"agent_patient_reference_decisions.json"
OUT=M/"outputs"/"agent_patient_reference_validated_decisions.json"

def main():
    data=load_json(INP); ds=data.get("decisions",[])
    docs={}
    for p in CLINICAL_DIR.glob("*.json"):
        try: docs[p.name]=load_json(p)
        except:pass
    result=[]
    for d in ds:
        doc=docs.get(d.get("document"))
        md=d.get("metadata") or {}; cid=md.get("candidate_entity_id")
        ent=next((e for e in entities(doc or {}) if str(eid(e))==str(cid)),None)
        grounded=md.get("text_grounded") is True
        decision=d.get("decision"); action=d.get("action")
        if decision=="PATIENT" and action=="KEEP" and grounded and ent:
            fs,fa,reason="ACCEPT","KEEP","Classification patient validÃ©e; aucune suppression."
        elif decision=="REFERENCE" and grounded and ent:
            # Critical safety rule: reference classification != permission to delete.
            fs,fa,reason="REVIEW","NONE","RÃ©fÃ©rence probable confirmÃ©e textuellement, mais suppression/exclusion exige une preuve structurelle explicite."
        else:
            fs,fa,reason="REVIEW","NONE","DÃ©cision insuffisante pour une modification automatique."
        result.append({"candidate_id":d.get("candidate_id"),"document":d.get("document"),
                       "agent_decision":d,"final_status":fs,"final_action":fa,"reason":reason})
    sc=Counter(x["final_status"] for x in result); ac=Counter(x["final_action"] for x in result)
    save_json(OUT,{"validator":"agent_patient_reference_decision_validator",
                   "clinical_context_directory":str(CLINICAL_DIR),"validated_decisions":result})
    print("="*96);print("TRACE / SGCE - PATIENT / REFERENCE DECISION VALIDATOR");print("="*96)
    print(f"DÃ©cisions reÃ§ues                  : {len(ds)}")
    print(f"DÃ©cisions validÃ©es                : {len(result)}")
    print("\nSTATUTS FINAUX");print("-"*96)
    for k,v in sc.items():print(f"{k:<40}: {v}")
    print("\nACTIONS FINALES");print("-"*96)
    for k,v in ac.items():print(f"{k:<40}: {v}")
    print(f"\nSortie                            : {OUT}")
    print("\nAucune donnÃ©e clinique n'a Ã©tÃ© modifiÃ©e.")
if __name__=="__main__": main()

