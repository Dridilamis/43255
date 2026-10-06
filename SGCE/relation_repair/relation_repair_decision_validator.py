# -*- coding: utf-8 -*-
"""Valide les décisions de l'agent avant la simulation d'impact."""
import json
from pathlib import Path
from collections import Counter
HERE=Path(__file__).resolve().parent
CANDIDATES=HERE/"queues"/"relation_repair_queue.json"
DECISIONS=HERE/"outputs"/"relation_repair_decisions.json"
OUTPUT=HERE/"outputs"/"relation_repair_validated_decisions.json"
ALLOWED={"REPLACE_RELATION","RETYPE_SOURCE","RETYPE_TARGET"}
MIN_CONFIDENCE=0.78
def load(p):
    with p.open("r",encoding="utf-8") as f:return json.load(f)
def save(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding="utf-8")
def main():
    cand=load(CANDIDATES); payload=load(DECISIONS)
    dec=payload.get("decisions",[]) if isinstance(payload,dict) else payload
    cmap={str(x.get("candidate_id")):x for x in cand}; out=[]
    for d in dec:
        c=cmap.get(str(d.get("candidate_id"))); a=d.get("action"); p=d.get("parameters") or {}
        reasons=[]; ok=True
        if c is None: ok=False; reasons.append("CANDIDATE_NOT_FOUND")
        if d.get("decision")!="CORRECT": ok=False; reasons.append("AGENT_NOT_CORRECT")
        if a not in ALLOWED: ok=False; reasons.append("ACTION_NOT_ALLOWED")
        if float(d.get("confidence") or 0)<MIN_CONFIDENCE: ok=False; reasons.append("CONFIDENCE_TOO_LOW")
        if a=="REPLACE_RELATION":
            if not p.get("relation_id") or not p.get("new_relation_type"):
                ok=False; reasons.append("MISSING_PARAMETERS")
            if c and str(p.get("relation_id"))!=str(c.get("relation_id")):
                ok=False; reasons.append("RELATION_ID_MISMATCH")
        elif a in ("RETYPE_SOURCE","RETYPE_TARGET"):
            expected_id=c.get("source_id") if c and a=="RETYPE_SOURCE" else (c.get("target_id") if c else None)
            expected_type=c.get("source_type_expected") if c and a=="RETYPE_SOURCE" else (c.get("target_type_expected") if c else None)
            if not p.get("entity_id") or not p.get("new_type"):
                ok=False; reasons.append("MISSING_PARAMETERS")
            if c and str(p.get("entity_id"))!=str(expected_id):
                ok=False; reasons.append("ENTITY_ID_MISMATCH")
            if c and str(p.get("new_type"))!=str(expected_type):
                ok=False; reasons.append("EXPECTED_TYPE_MISMATCH")
        out.append({"candidate_id":d.get("candidate_id"),"document":d.get("document"),
                    "relation_id":d.get("relation_id"),"agent_decision":d,
                    "final_status":"ACCEPT" if ok else "REVIEW",
                    "final_action":a if ok else "NONE",
                    "validation_reasons":reasons or ["VALIDATED"]})
    c=Counter(x["final_status"] for x in out)
    save(OUTPUT,{"validator":"relation_repair_decision_validator","summary":dict(c),"validated_decisions":out})
    print("="*104);print("TRACE / SGCE - RELATION REPAIR DECISION VALIDATOR");print("="*104)
    print(f"Décisions reçues : {len(dec)}");print(f"ACCEPT            : {c.get('ACCEPT',0)}")
    print(f"REVIEW            : {c.get('REVIEW',0)}");print(f"Sortie            : {OUTPUT}")
if __name__=="__main__":main()
