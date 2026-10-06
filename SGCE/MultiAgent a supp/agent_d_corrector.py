# -*- coding: utf-8 -*-
import json, shutil
from pathlib import Path
from collections import Counter

BASE_DIR=Path(r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM\Reduction_hallucinations")
M=BASE_DIR/"MultiAgent"
INP=M/"outputs"/"agent_d_validated_decisions.json"
SOURCE_CANDIDATES=[M/"agent_patient_reference_corrected",M/"agent_c_corrected"]
OUTDIR=M/"agent_d_corrected"
REPORT=OUTDIR/"agent_d_correction_report.json"

def load_json(p):
    with p.open("r",encoding="utf-8") as f:return json.load(f)

def save_json(p,x):
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding="utf-8")

def resolve_source():
    for d in SOURCE_CANDIDATES:
        if d.exists() and any(d.glob("*.json")):return d
    raise FileNotFoundError("Source clinique Agent D introuvable.")

def eid(e):return e.get("identifiant_entite") or e.get("id") or e.get("entity_id")

def retype_in_doc(doc, entity_id, new_type):
    changed=0
    lists=[]
    if isinstance(doc.get("global_entities"),list):lists.append(doc["global_entities"])
    for p in doc.get("pages",[]) or []:
        if isinstance(p.get("entities"),list):lists.append(p["entities"])

    for lst in lists:
        for e in lst:
            if str(eid(e))==str(entity_id):
                if "categorie" in e:e["categorie"]=new_type
                elif "entity_type" in e:e["entity_type"]=new_type
                else:e["type"]=new_type
                changed+=1
    return changed

def main():
    data=load_json(INP);decisions=data.get("validated_decisions",[])
    source=resolve_source()

    if OUTDIR.exists():shutil.rmtree(OUTDIR)
    OUTDIR.mkdir(parents=True)

    copied=0
    for p in source.glob("*.json"):
        if p.name.endswith("_report.json"):continue
        try:
            d=load_json(p)
            if isinstance(d,dict) and any(k in d for k in ("pages","global_entities","global_relations")):
                shutil.copy2(p,OUTDIR/p.name);copied+=1
        except:pass

    ops=[];modified=set();counts=Counter()

    for item in decisions:
        if item.get("final_status")!="ACCEPT" or item.get("final_action")!="RETYPE_ENTITY":continue
        d=item.get("agent_decision") or {};md=d.get("metadata") or {}
        docname=item.get("document");path=OUTDIR/docname

        if not path.exists():
            ops.append({"candidate_id":item.get("candidate_id"),"document":docname,"status":"ERROR","reason":"DOCUMENT_NOT_FOUND"})
            continue

        doc=load_json(path)
        changed=retype_in_doc(doc,md.get("entity_id"),md.get("expected_type"))

        if changed:
            save_json(path,doc);modified.add(docname);counts["RETYPE_ENTITY"]+=1
            status,reason="APPLIED","OK"
        else:
            status,reason="SKIP","ENTITY_NOT_FOUND_OR_NO_CHANGE"

        ops.append({"candidate_id":item.get("candidate_id"),"document":docname,
                    "action":"RETYPE_ENTITY","entity_id":md.get("entity_id"),
                    "new_type":md.get("expected_type"),"status":status,"reason":reason})

    save_json(REPORT,{"corrector":"agent_d_corrector","source_directory":str(source),
                      "output_directory":str(OUTDIR),
                      "summary":{"documents_copied":copied,"operations_applied":sum(counts.values()),
                                 "documents_modified":len(modified),"actions":dict(counts)},
                      "modified_documents":sorted(modified),"operations":ops})

    print("="*96)
    print("TRACE / SGCE - AGENT D CORRECTOR")
    print("="*96)
    print(f"Source clinique                    : {source}")
    print(f"Sortie clinique                    : {OUTDIR}")
    print(f"\nDocuments copiÃ©s                   : {copied}")
    print(f"OpÃ©rations appliquÃ©es              : {sum(counts.values())}")
    print(f"Documents modifiÃ©s                 : {len(modified)}")
    print(f"\nRapport                            : {REPORT}")
    print("\nLes fichiers sources n'ont pas Ã©tÃ© modifiÃ©s.")

if __name__=="__main__":main()

