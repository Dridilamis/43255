# -*- coding: utf-8 -*-
import json
from pathlib import Path
from collections import Counter

BASE_DIR=Path(r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM\Reduction_hallucinations")
M=BASE_DIR/"MultiAgent"
INP=M/"outputs"/"agent_d_decisions.json"
OUT=M/"outputs"/"agent_d_validated_decisions.json"
CLINICAL_DIR_CANDIDATES=[M/"agent_patient_reference_corrected",M/"agent_c_corrected"]

def load_json(p):
    with p.open("r",encoding="utf-8") as f:return json.load(f)

def resolve_dir():
    for d in CLINICAL_DIR_CANDIDATES:
        if d.exists() and any(d.glob("*.json")):return d
    raise FileNotFoundError("Contexte clinique introuvable.")

def eid(e):return e.get("identifiant_entite") or e.get("id") or e.get("entity_id")
def etype(e):return e.get("categorie") or e.get("type") or e.get("entity_type") or ""

def entities(doc):
    if isinstance(doc.get("global_entities"),list):return doc["global_entities"]
    z=[]
    for p in doc.get("pages",[]) or []:z+=p.get("entities",[]) or []
    return z

def find_entity(doc,x):
    return next((e for e in entities(doc) if str(eid(e))==str(x)),None)

def main():
    data=load_json(INP); decisions=data.get("decisions",[])
    cdir=resolve_dir()
    docs={}
    for p in cdir.glob("*.json"):
        try:docs[p.name]=load_json(p)
        except:pass

    out=[]
    for d in decisions:
        doc=docs.get(d.get("document"))
        md=d.get("metadata") or {}
        if d.get("action")=="RETYPE_ENTITY":
            ent=find_entity(doc or {},md.get("entity_id"))
            expected=md.get("expected_type")
            grounded=md.get("text_grounded") is True
            support=md.get("lexicon_support") or []
            if ent and expected and etype(ent)!=expected and grounded and support:
                fs,fa,reason="ACCEPT","RETYPE_ENTITY","RETYPE document-grounded et cohÃ©rent avec le type attendu."
            else:
                fs,fa,reason="REVIEW","NONE","RETYPE insuffisamment sÃ»r."
        else:
            fs,fa,reason="REVIEW","NONE","Aucune correction automatique validable."

        out.append({"candidate_id":d.get("candidate_id"),"document":d.get("document"),
                    "agent_decision":d,"final_status":fs,"final_action":fa,"reason":reason})

    sc=Counter(x["final_status"] for x in out)
    ac=Counter(x["final_action"] for x in out)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps({"validator":"agent_d_decision_validator","validated_decisions":out},ensure_ascii=False,indent=2),encoding="utf-8")

    print("="*96)
    print("TRACE / SGCE - AGENT D DECISION VALIDATOR")
    print("="*96)
    print(f"DÃ©cisions reÃ§ues                  : {len(decisions)}")
    print(f"DÃ©cisions validÃ©es                : {len(out)}")
    print("\nSTATUTS FINAUX");print("-"*96)
    for k,v in sc.items():print(f"{k:<40}: {v}")
    print("\nACTIONS FINALES");print("-"*96)
    for k,v in ac.items():print(f"{k:<40}: {v}")
    print(f"\nSortie                            : {OUT}")
    print("\nAucune donnÃ©e clinique n'a Ã©tÃ© modifiÃ©e.")

if __name__=="__main__":main()

