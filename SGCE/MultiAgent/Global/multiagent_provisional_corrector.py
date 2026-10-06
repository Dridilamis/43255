# -*- coding: utf-8 -*-
"""
TRACE / SGCE - Provisional Multi-Agent Corrector

Consumes multiagent_resolved_actions.json.
Applies fully specified ACTIONABLE actions on a COPY of AgentD/corrected.
This provisional output is used by the impact validator. The safe final corrector
still rebuilds final output from the clean AgentD baseline for RETYPE actions.
"""
import json, shutil
from pathlib import Path
from collections import Counter

HERE=Path(__file__).resolve().parent
MULTIAGENT_DIR=HERE.parent
SGCE_DIR=MULTIAGENT_DIR.parent
SOURCE=SGCE_DIR / "orphan_resolution" / "corrected"
INP=MULTIAGENT_DIR/"outputs"/"multiagent_resolved_actions.json"
OUT=MULTIAGENT_DIR/"provisional_corrected"
REPORT=MULTIAGENT_DIR/"outputs"/"multiagent_provisional_correction_report.json"

def load(p):
    with p.open("r",encoding="utf-8") as f:return json.load(f)
def save(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding="utf-8")
def eid(e): return e.get("identifiant_entite") or e.get("id") or e.get("entity_id")
def et(e): return e.get("categorie") or e.get("entity_type") or e.get("type") or ""
def set_et(e,v):
    if "categorie" in e:e["categorie"]=v
    elif "entity_type" in e:e["entity_type"]=v
    else:e["type"]=v
def entity_lists(d):
    z=[]
    if isinstance(d.get("global_entities"),list):z.append(d["global_entities"])
    for p in d.get("pages",[]) or []:
        if isinstance(p.get("entities"),list):z.append(p["entities"])
    return z
def relation_lists(d):
    z=[]
    if isinstance(d.get("global_relations"),list):z.append(d["global_relations"])
    for p in d.get("pages",[]) or []:
        if isinstance(p.get("relations"),list):z.append(p["relations"])
    return z
def rid(r):return r.get("identifiant_relation") or r.get("id") or r.get("relation_id")
def rs(r):return r.get("identifiant_entite_sujet") or r.get("from_id") or r.get("subject_id") or r.get("source")
def ro(r):return r.get("identifiant_entite_objet") or r.get("to_id") or r.get("object_id") or r.get("target")
def set_rs(r,v):
    for k in ("identifiant_entite_sujet","from_id","subject_id","source"):
        if k in r:r[k]=v;return
    r["source"]=v
def set_ro(r,v):
    for k in ("identifiant_entite_objet","to_id","object_id","target"):
        if k in r:r[k]=v;return
    r["target"]=v
def first(x,*keys):
    if not isinstance(x,dict):return None
    for k in keys:
        v=x.get(k)
        if v not in (None,"",[],{}):return v
    return None
def params(a):
    # Resolver versions may store parameters directly or under metadata/parameters.
    p={}
    for obj in (a,a.get("parameters") or {},a.get("metadata") or {},a.get("resolved_parameters") or {}):
        if isinstance(obj,dict):p.update({k:v for k,v in obj.items() if v not in (None,"",[],{})})
    return p
def main():
    if OUT.exists():shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    for p in SOURCE.glob("*.json"):
        try:
            d=load(p)
            if any(k in d for k in ("pages","global_entities","global_relations")):shutil.copy2(p,OUT/p.name)
        except:pass
    data=load(INP); acts=data.get("resolved_actions",data if isinstance(data,list) else [])
    ops=[];counts=Counter();modified=set()
    for a in acts:
        if a.get("status")!="ACTIONABLE":continue
        action=a.get("action"); doc=a.get("document"); p=params(a)
        fp=OUT/str(doc)
        if not fp.exists():
            ops.append({"document":doc,"action":action,"status":"SKIP","reason":"DOCUMENT_NOT_FOUND"});continue
        d=load(fp); changed=0
        try:
            if action=="RETYPE_ENTITY":
                target=first(p,"entity_id","target_entity_id","candidate_entity_id")
                new=first(p,"new_type","proposed_type","expected_type")
                old=None
                for L in entity_lists(d):
                    for e in L:
                        if str(eid(e))==str(target):
                            old=old or et(e)
                            if new and et(e)!=new:set_et(e,new);changed+=1
                op={"document":doc,"action":action,"entity_id":target,"old_type":old,"new_type":new}
            elif action in ("RELINK","RELINK_EXISTING_ENTITY"):
                relid=first(p,"relation_id","target_relation_id")
                old=first(p,"old_endpoint_id","missing_endpoint","endpoint_value")
                new=first(p,"new_endpoint_id","replacement_entity_id","existing_entity_id")
                role=str(first(p,"role","endpoint_role") or "").upper()
                for L in relation_lists(d):
                    for r in L:
                        if relid and str(rid(r))!=str(relid):continue
                        if role=="SOURCE" or (not role and str(rs(r))==str(old)):
                            if new and str(rs(r))!=str(new):set_rs(r,new);changed+=1
                        elif role=="TARGET" or (not role and str(ro(r))==str(old)):
                            if new and str(ro(r))!=str(new):set_ro(r,new);changed+=1
                op={"document":doc,"action":action,"relation_id":relid,"new_endpoint_id":new}
            elif action in ("REMOVE_INVALID_RELATION","REMOVE_RELATION"):
                relid=first(p,"relation_id","target_relation_id")
                for L in relation_lists(d):
                    before=len(L);L[:]=[r for r in L if str(rid(r))!=str(relid)];changed+=before-len(L)
                op={"document":doc,"action":action,"relation_id":relid}
            elif action=="KEEP":
                op={"document":doc,"action":action};changed=0
            else:
                op={"document":doc,"action":action,"status":"SKIP","reason":"UNSUPPORTED_OR_DESTRUCTIVE_ACTION_PROTECTED"}
                ops.append(op);counts["SKIP"]+=1;continue
            op["status"]="APPLIED" if changed else ("VERIFIED_NO_CHANGE" if action=="KEEP" else "SKIP")
            op["occurrences_changed"]=changed;ops.append(op)
            if changed:save(fp,d);modified.add(doc);counts[action]+=1
        except Exception as e:
            ops.append({"document":doc,"action":action,"status":"ERROR","reason":repr(e)});counts["ERROR"]+=1
    save(REPORT,{"corrector":"multiagent_provisional_corrector","source_directory":str(SOURCE),
                 "output_directory":str(OUT),"summary":{"actions_received":len(acts),
                 "operations_applied":sum(counts.values())-counts["SKIP"]-counts["ERROR"],
                 "documents_modified":len(modified),"counts":dict(counts)},
                 "modified_documents":sorted(modified),"operations":ops})
    print("="*104);print("TRACE / SGCE - PROVISIONAL CORRECTOR");print("="*104)
    print("Documents modifiés :",len(modified));print("Rapport :",REPORT)
if __name__=="__main__":main()
