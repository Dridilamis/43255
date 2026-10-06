# -*- coding: utf-8 -*-
import copy,json
from pathlib import Path
from collections import Counter
HERE=Path(__file__).resolve().parent;M=HERE.parent;SGCE=M.parent;BASE=SGCE/"orphan_resolution"/"corrected";INP=M/"outputs"/"multiagent_resolved_actions.json";OUT=M/"outputs"/"multiagent_general_impact_validation.json";COMPAT=M/"outputs"/"multiagent_retype_impact_validation.json";ROOT=SGCE.parent
GUIDES=[ROOT/"Guideline_TRACE_Sepsis_v1.6.json",ROOT.parent/"Guideline_TRACE_Sepsis_v1.6.json"]
def load(p):
    with p.open("r",encoding="utf-8") as f:return json.load(f)
def save(p,x):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding="utf-8")
def first(x,*ks):
    for k in ks:
        v=x.get(k)
        if v not in (None,"",[],{}):return v
def eid(e):return first(e,"identifiant_entite","id","entity_id")
def et(e):return first(e,"categorie","type","entity_type") or ""
def rid(r):return first(r,"identifiant_relation","id","relation_id")
def rt(r):return first(r,"type_relation","relation","relation_type","predicate","type") or ""
def rs(r):return first(r,"identifiant_entite_sujet","from_id","subject_id","source")
def ro(r):return first(r,"identifiant_entite_objet","to_id","object_id","target")
def elists(d):
    z=[]
    if isinstance(d.get("global_entities"),list):z.append(d["global_entities"])
    for p in d.get("pages",[]) or []:
        if isinstance(p.get("entities"),list):z.append(p["entities"])
    return z
def ents(d):
    return d["global_entities"] if isinstance(d.get("global_entities"),list) else [e for L in elists(d) for e in L]
def rels(d):
    if isinstance(d.get("global_relations"),list):return d["global_relations"]
    return [r for p in d.get("pages",[]) or [] for r in p.get("relations",[]) or []]
def fent(d,x):return next((e for e in ents(d) if str(eid(e))==str(x)),None)
def frel(d,x):return next((r for r in rels(d) if str(rid(r))==str(x)),None)
def sigs():
    gp=next((p for p in GUIDES if p.exists()),None)
    if not gp:return {}
    z=load(gp);z=z.get("ontologie_sepsis_graph",z);b=z.get("signatures_relations_verrouillees_v1_5",{})
    return {k:(v.get("domaine"),v.get("image")) for k,v in b.items() if isinstance(v,dict) and v.get("domaine") and v.get("image")}
def audit(d,s):
    idx={str(eid(e)):e for e in ents(d) if eid(e) is not None};o=set()
    for r in rels(d):
        rr=str(rid(r));a=idx.get(str(rs(r)));b=idx.get(str(ro(r)));sg=s.get(rt(r))
        if a is None:o.add(("ORPHAN_SOURCE",rr,str(rs(r))))
        if b is None:o.add(("ORPHAN_TARGET",rr,str(ro(r))))
        if sg and a is not None and et(a)!=sg[0]:o.add(("INVALID_SOURCE",rr,et(a),sg[0]))
        if sg and b is not None and et(b)!=sg[1]:o.add(("INVALID_TARGET",rr,et(b),sg[1]))
    return o
def params(a):
    p={}
    for z in (a,a.get("parameters") or {},a.get("metadata") or {},a.get("resolved_parameters") or {}):
        if isinstance(z,dict):p.update({k:v for k,v in z.items() if v not in (None,"",[],{})})
    return p
def add_entity(d,e,page):
    if isinstance(d.get("global_entities"),list):d["global_entities"].append(copy.deepcopy(e))
    pg=next((x for x in d.get("pages",[]) or [] if str(x.get("page"))==str(page)),None)
    if pg is not None:pg.setdefault("entities",[]).append(copy.deepcopy(e))
    elif not isinstance(d.get("global_entities"),list):raise ValueError("NO_ENTITY_CONTAINER")
def make_entity(i,t,text,page):
    return {"identifiant_entite":i,"categorie":t,"parametre":text,"valeur":None,"unite":None,"horodatage":"inconnu","preuve":text,"nie":False,"confiance":"elevee","type_inference":"correction_structurelle_sgce","page":page,"valeur_reference":None,"name":text,"type":t,"_sgce_created":True,"_sgce_operation":"CREATE_FROM_EXPLICIT_EVIDENCE"}
def main():
    actions=[a for a in load(INP).get("resolved_actions",[]) if a.get("status")=="ACTIONABLE"];sg=sigs();results=[];safe=[]
    for a in actions:
        doc=a.get("document");act=a.get("action");p=params(a);res={"candidate_id":a.get("candidate_id"),"document":doc,"action":act,"parameters":p};fp=BASE/str(doc)
        if not fp.exists():res.update(status="REVIEW",reason="DOCUMENT_NOT_FOUND");results.append(res);continue
        d=load(fp);before=audit(d,sg);sim=copy.deepcopy(d)
        try:
            if act=="RETYPE_ENTITY":
                target=first(p,"entity_id","target_entity_id","candidate_entity_id");newt=first(p,"new_type","proposed_type","expected_type");e=fent(sim,target)
                if not e or not newt:raise ValueError("INCOMPLETE_RETYPE")
                old=et(e)
                for L in elists(sim):
                    for x in L:
                        if str(eid(x))==str(target):x["categorie"]=newt;x["type"]=newt
                res.update(entity_id=target,old_type=old,new_type=newt)
            elif act=="CREATE_FROM_EXPLICIT_EVIDENCE":
                missing=first(p,"missing_endpoint","endpoint_id");typ=first(p,"entity_type","expected_type");text=first(p,"entity_text","text");relid=first(p,"relation_id","target_relation_id");role=str(first(p,"role","endpoint_role") or "").upper();page=first(p,"page_number","page");r=frel(sim,relid)
                if not all((missing,typ,text,relid)) or role not in {"SOURCE","TARGET"}:raise ValueError("INCOMPLETE_CREATE")
                if fent(sim,missing):raise ValueError("ENDPOINT_ALREADY_EXISTS")
                if r is None:raise ValueError("RELATION_NOT_FOUND")
                current=rs(r) if role=="SOURCE" else ro(r)
                if str(current)!=str(missing):raise ValueError("RELATION_NO_LONGER_POINTS_TO_MISSING_ENDPOINT")
                sig=sg.get(rt(r));expected=sig[0 if role=="SOURCE" else 1] if sig else None
                if expected and expected!=typ:raise ValueError("TYPE_SIGNATURE_MISMATCH")
                add_entity(sim,make_entity(missing,typ,text,page),page);res.update(entity_id=missing,entity_type=typ,entity_text=text,relation_id=relid,role=role,page_number=page)
            else:res.update(status="REVIEW",reason="UNSUPPORTED_ACTION");results.append(res);continue
            after=audit(sim,sg);new=after-before;fixed=before-after
            if new:st,reason="REJECT_HARMFUL","CREATES_NEW_ANOMALIES"
            elif fixed:st,reason="SAFE_ACCEPT","MONOTONIC_STRUCTURAL_IMPROVEMENT"
            else:st,reason="NO_BENEFIT","NO_STRUCTURAL_IMPROVEMENT"
            res.update(status=st,reason=reason,before_anomaly_count=len(before),after_anomaly_count=len(after),new_anomaly_count=len(new),resolved_anomaly_count=len(fixed))
            if st=="SAFE_ACCEPT":safe.append(dict(res))
        except Exception as e:res.update(status="REVIEW",reason=str(e))
        results.append(res)
    c=Counter(x["status"] for x in results);ac=Counter(x["action"] for x in safe)
    payload={"validator":"multiagent_general_impact_validator","baseline_directory":str(BASE),"summary":{"actionable_received":len(actions),"safe_accept":c["SAFE_ACCEPT"],"reject_harmful":c["REJECT_HARMFUL"],"no_benefit":c["NO_BENEFIT"],"review":c["REVIEW"],"safe_actions_by_type":dict(ac)},"safe_actions":safe,"results":results}
    save(OUT,payload);save(COMPAT,payload)
    print("="*108);print("TRACE / SGCE - GENERAL IMPACT VALIDATOR");print("="*108)
    print("Actions ACTIONABLE reçues           :",len(actions));print("SAFE_ACCEPT                          :",c["SAFE_ACCEPT"]);print("REJECT_HARMFUL                       :",c["REJECT_HARMFUL"]);print("NO_BENEFIT                           :",c["NO_BENEFIT"]);print("REVIEW                               :",c["REVIEW"]);print("Actions sûres par type              :",dict(ac));print("Sortie                               :",OUT)
if __name__=="__main__":main()
