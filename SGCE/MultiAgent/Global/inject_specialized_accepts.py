# -*- coding: utf-8 -*-
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent;M=HERE.parent;O=M/"outputs";Q=M/"queues";ADJ=O/"multiagent_adjudication_report.json";DIRECT=O/"multiagent_direct_accepts.json";BQ=Q/"agent_b_queue_contextualized.json"
def load(p):
    with p.open("r",encoding="utf-8") as f:return json.load(f)
def save(p,x):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding="utf-8")
def first(*v):return next((x for x in v if x not in (None,"",[],{})),None)
def main():
    a=load(ADJ);cases=a.get("cases",[]) or [];existing={(str(x.get("family")),str(x.get("candidate_id"))) for x in cases}
    bi={str(x.get("candidate_id")):x for x in (load(BQ) if BQ.exists() else [])};direct=load(DIRECT).get("direct_accepts",[]) if DIRECT.exists() else [];added=0
    for x in direct:
        fam=str(x.get("family") or "").upper();cid=x.get("candidate_id");key=(fam,str(cid))
        if key in existing:continue
        d=x.get("agent_decision") or x;md=dict(d.get("metadata") or {});action=x.get("final_action") or d.get("action") or "NONE";prop=dict(md);prop["action"]=action
        if fam=="B":
            q=bi.get(str(cid),{});s=q.get("symbolic_candidate") or {};rel=s.get("relation") or {};eps=s.get("endpoint_validations") or [];ep=eps[0] if eps and isinstance(eps[0],dict) else {};pe=(d.get("proposed_entities") or [{}])[0]
            prop.update({"missing_endpoint":first(md.get("missing_endpoint"),ep.get("endpoint_value")),"entity_type":first(pe.get("type"),md.get("expected_type"),ep.get("expected_type")),"entity_text":first(pe.get("text"),d.get("evidence")),"relation_id":first(rel.get("identifiant_relation"),rel.get("id"),rel.get("relation_id"),s.get("relation_id")),"relation_type":first(rel.get("type_relation"),rel.get("relation"),rel.get("relation_type"),rel.get("type"),s.get("relation_type")),"role":first(ep.get("role"),"SOURCE" if s.get("source_missing") else None,"TARGET" if s.get("target_missing") else None),"page_number":first(md.get("page_number"),q.get("page_number"))})
        cases.append({"family":fam,"candidate_id":cid,"document":x.get("document"),"votes":[],"support_vote_count":0,"veto_vote_count":0,"mean_support_score":float(d.get("confidence") or 0),"documentary_support":bool(d.get("evidence") or md.get("text_grounded")),"adjudication_status":"RESOLVED_SPECIALIZED_ACCEPT","adjudication_action":action,"proposed_correction":{k:v for k,v in prop.items() if v not in (None,"",[],{})},"reason":"Validated specialized ACCEPT; impact validation mandatory."})
        existing.add(key);added+=1
    a["cases"]=cases;a.setdefault("summary",{})["specialized_accepts_injected"]=added;save(ADJ,a)
    print(f"Specialized ACCEPT injectés dans `cases` : {added}");print(f"Cas disponibles pour Action Resolver     : {len(cases)}")
if __name__=="__main__":main()
