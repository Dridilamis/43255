# -*- coding: utf-8 -*-
"""Merge unresolved orphan relations into Agent-B queue without duplicating candidates."""
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
M=HERE.parent
SGCE=M.parent
B=M/"queues"/"agent_b_queue.json"
ORPH=SGCE/"orphan_resolution"/"outputs"/"orphan_relation_unresolved_queue.json"

def load(p):
    with p.open("r",encoding="utf-8") as f:return json.load(f)
def save(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding="utf-8")
def main():
    b=load(B) if B.exists() else []
    if isinstance(b,dict): b=b.get("candidates",b.get("queue",[]))
    o=load(ORPH) if ORPH.exists() else {}
    oc=o.get("candidates",[]) if isinstance(o,dict) else o
    seen={(str(x.get("document")),str(x.get("relation_id") or (x.get("symbolic_candidate") or {}).get("relation_id")),
           str(x.get("candidate_id"))) for x in b}
    added=0
    for x in oc:
        key=(str(x.get("document")),str(x.get("relation_id")),str(x.get("candidate_id")))
        if key in seen: continue
        y={
          "candidate_id":"ORB_"+str(x.get("candidate_id")),
          "document":x.get("document"),
          "subpattern":"B1_ORPHAN_RESIDUAL",
          "original_status":"UNRESOLVED_ORPHAN",
          "symbolic_candidate":{
             "pattern":"B1","candidate_kind":"ORPHAN_RELATION",
             "relation_id":x.get("relation_id"),"relation_type":x.get("relation_type"),
             "source_id":x.get("source_id"),"target_id":x.get("target_id"),
             "source_missing":x.get("source_missing"),"target_missing":x.get("target_missing"),
             "existing_source_entity":x.get("existing_source_entity"),
             "existing_target_entity":x.get("existing_target_entity"),
             "entity_catalog":x.get("entity_catalog",[]),
             "status":"UNRESOLVED_ORPHAN","recommended_future_action":"REVIEW"
          }
        }
        b.append(y); added+=1
    save(B,b)
    print(f"Agent B queue: orphanes résiduelles ajoutées={added}; total={len(b)}")
if __name__=="__main__":main()
