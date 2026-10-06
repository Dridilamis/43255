# -*- coding: utf-8 -*-
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent;M=HERE.parent;SGCE=M.parent;ROOT=SGCE.parent;BEFORE=SGCE/"orphan_resolution"/"corrected";AFTER=M/"corrected";CORR=AFTER/"multiagent_safe_correction_report.json";OUT=M/"post_validation"/"multiagent_safe_post_validation_report.json";GUIDES=[ROOT/"Guideline_TRACE_Sepsis_v1.6.json",ROOT.parent/"Guideline_TRACE_Sepsis_v1.6.json"]
def load(p):
    with p.open("r",encoding="utf-8") as f:return json.load(f)
def save(p,x):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding="utf-8")
def f(x,*k):
    for a in k:
        v=x.get(a)
        if v not in (None,"",[],{}):return v
def eid(e):return f(e,"identifiant_entite","id","entity_id")
def et(e):return f(e,"categorie","type","entity_type") or ""
def rid(r):return f(r,"identifiant_relation","id","relation_id")
def rt(r):return f(r,"type_relation","relation","relation_type","predicate","type") or ""
def rs(r):return f(r,"identifiant_entite_sujet","from_id","subject_id","source")
def ro(r):return f(r,"identifiant_entite_objet","to_id","object_id","target")
def ents(d):
    return d["global_entities"] if isinstance(d.get("global_entities"),list) else [e for p in d.get("pages",[]) or [] for e in p.get("entities",[]) or []]
def rels(d):
    return d["global_relations"] if isinstance(d.get("global_relations"),list) else [r for p in d.get("pages",[]) or [] for r in p.get("relations",[]) or []]
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
def docs(path):
    z={}
    for p in path.glob("*.json"):
        if p.name.endswith("_report.json"):continue
        try:
            d=load(p)
            if any(k in d for k in ("pages","global_entities","global_relations")):z[p.name]=d
        except:pass
    return z
def main():
    b=docs(BEFORE);a=docs(AFTER);s=sigs();rep=load(CORR);expected=set(rep.get("modified_documents",[]));common=set(b)&set(a);missing=set(b)-set(a);extra=set(a)-set(b);actual={n for n in common if b[n]!=a[n]};bm={(n,*x) for n in common for x in audit(b[n],s)};am={(n,*x) for n in common for x in audit(a[n],s)};new=am-bm;fixed=bm-am;unexpected=actual-expected;absent=expected-actual;ok=not missing and not extra and not unexpected and not absent and not new
    summary={"documents_verified":len(common),"expected_modified":len(expected),"actually_modified":len(actual),"unexpected_modifications":len(unexpected),"expected_corrections_absent":len(absent),"anomalies_before":len(bm),"anomalies_after":len(am),"new_anomalies":len(new),"resolved_anomalies":len(fixed),"missing_documents":len(missing),"extra_documents":len(extra),"final_status":"PASS" if ok else "FAIL"}
    save(OUT,{"validator":"multiagent_safe_general_post_validator","summary":summary,"new_anomalies":[list(x) for x in sorted(new)],"resolved_anomalies":[list(x) for x in sorted(fixed)]})
    print("="*108);print("TRACE / SGCE - SAFE GENERAL POST-VALIDATION");print("="*108)
    for k,v in summary.items():print(f"{k:<36}: {v}")
    print("Rapport                             :",OUT)
if __name__=="__main__":main()
