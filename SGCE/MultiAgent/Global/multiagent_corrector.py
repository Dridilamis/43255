# -*- coding: utf-8 -*-
import copy,json,shutil
from pathlib import Path
from collections import Counter
HERE=Path(__file__).resolve().parent;M=HERE.parent;SGCE=M.parent;INP=M/"outputs"/"multiagent_general_impact_validation.json";SOURCE=SGCE/"orphan_resolution"/"corrected";OUT=M/"corrected";REPORT=OUT/"multiagent_safe_correction_report.json"
def load(p):
    with p.open("r",encoding="utf-8") as f:return json.load(f)
def save(p,x):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding="utf-8")
def eid(e):return e.get("identifiant_entite") or e.get("id") or e.get("entity_id")
def elists(d):
    z=[]
    if isinstance(d.get("global_entities"),list):z.append(d["global_entities"])
    for p in d.get("pages",[]) or []:
        if isinstance(p.get("entities"),list):z.append(p["entities"])
    return z
def add(d,e,page):
    if isinstance(d.get("global_entities"),list):d["global_entities"].append(copy.deepcopy(e))
    pg=next((x for x in d.get("pages",[]) or [] if str(x.get("page"))==str(page)),None)
    if pg is not None:pg.setdefault("entities",[]).append(copy.deepcopy(e))
    elif not isinstance(d.get("global_entities"),list):raise ValueError("NO_ENTITY_CONTAINER")
def entity(i,t,text,page):
    return {"identifiant_entite":i,"categorie":t,"parametre":text,"valeur":None,"unite":None,"horodatage":"inconnu","preuve":text,"nie":False,"confiance":"elevee","type_inference":"correction_structurelle_sgce","page":page,"valeur_reference":None,"name":text,"type":t,"_sgce_created":True,"_sgce_operation":"CREATE_FROM_EXPLICIT_EVIDENCE"}
def main():
    safe=load(INP).get("safe_actions",[]) or []
    if OUT.exists():shutil.rmtree(OUT)
    OUT.mkdir(parents=True);copied=0
    for p in SOURCE.glob("*.json"):
        try:
            d=load(p)
            if any(k in d for k in ("pages","global_entities","global_relations")):shutil.copy2(p,OUT/p.name);copied+=1
        except:pass
    ops=[];mods=set();c=Counter();errors=0
    for a in safe:
        doc=a.get("document");act=a.get("action");fp=OUT/str(doc)
        try:
            d=load(fp);changed=0
            if act=="RETYPE_ENTITY":
                target=a.get("entity_id");new=a.get("new_type")
                for L in elists(d):
                    for e in L:
                        if str(eid(e))==str(target) and (e.get("categorie") or e.get("type"))!=new:e["categorie"]=new;e["type"]=new;changed+=1
            elif act=="CREATE_FROM_EXPLICIT_EVIDENCE":
                target=a.get("entity_id")
                if not any(str(eid(e))==str(target) for L in elists(d) for e in L):
                    add(d,entity(target,a.get("entity_type"),a.get("entity_text"),a.get("page_number")),a.get("page_number"));changed=1
            else:ops.append({**a,"status":"SKIP","reason":"UNSUPPORTED_ACTION"});c["SKIP"]+=1;continue
            if changed:save(fp,d);mods.add(doc);c[act]+=1;ops.append({**a,"status":"APPLIED","occurrences_changed":changed})
            else:ops.append({**a,"status":"SKIP","reason":"ALREADY_SATISFIED"});c["SKIP"]+=1
        except Exception as e:errors+=1;ops.append({**a,"status":"ERROR","reason":repr(e)})
    applied=sum(v for k,v in c.items() if k!="SKIP")
    rep={"corrector":"multiagent_safe_general_corrector","source_directory":str(SOURCE),"output_directory":str(OUT),"summary":{"documents_copied":copied,"safe_actions_received":len(safe),"operations_applied":applied,"operations_skipped":c["SKIP"],"documents_modified":len(mods),"errors":errors,"counts":dict(c)},"modified_documents":sorted(mods),"operations":ops};save(REPORT,rep)
    print("="*104);print("TRACE / SGCE - SAFE GENERAL CORRECTOR");print("="*104);print("Actions SAFE_ACCEPT reçues          :",len(safe));print("Opérations appliquées               :",applied);print("Documents modifiés                  :",len(mods));print("Erreurs                              :",errors);print("Sortie clinique                     :",OUT)
if __name__=="__main__":main()
