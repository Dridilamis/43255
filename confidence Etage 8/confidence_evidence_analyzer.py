# -*- coding: utf-8 -*-

"""TRACE — ETAGE 8 V2 — Evidence Analyzer. Aucun coefficient numérique."""
from pathlib import Path
import json
from collections import Counter
HERE=Path(__file__).resolve().parent
INP=HERE/"queues"/"confidence_candidates.json"
OUTDIR=HERE/"outputs"; OUT=OUTDIR/"confidence_evidence.json"

def main():
    OUTDIR.mkdir(parents=True,exist_ok=True)
    x=json.loads(INP.read_text(encoding="utf-8")); out=[]; s=Counter()
    for c in x["items"]:
        g=c["grounding"]["status"]
        doc={"FOUND":"STRONG","PARTIAL":"PARTIAL","AMBIGUOUS":"AMBIGUOUS","NOT_FOUND":"ABSENT"}[g]
        if c["kind"]=="ENTITY":
            onto="CONSISTENT" if c["ontology_type_valid"] is True else "CONFLICT" if c["ontology_type_valid"] is False else "UNKNOWN"
            context="SUPPORTED" if g=="FOUND" else "PARTIAL" if g=="PARTIAL" else "AMBIGUOUS" if g=="AMBIGUOUS" else "INSUFFICIENT"
        else:
            endpoints=c["source_exists"] and c["target_exists"]
            onto=("CONSISTENT" if endpoints and c["ontology_relation_valid"] is True
                  else "CONFLICT" if (not endpoints or c["ontology_relation_valid"] is False) else "UNKNOWN")
            context="SUPPORTED" if g=="FOUND" and endpoints else "PARTIAL" if g=="PARTIAL" and endpoints else "AMBIGUOUS" if g=="AMBIGUOUS" else "INSUFFICIENT"
        prev="TRACE_VALIDATED" if c.get("trace_validation_keys") else "NO_EXPLICIT_TRACE_METADATA"
        z=dict(c); z["evidence"]={"document":doc,"context":context,"ontology":onto,"previous_validation":prev}
        out.append(z); s[c["kind"]]+=1; s["document_"+doc]+=1; s["ontology_"+onto]+=1
    OUT.write_text(json.dumps({"stage":"TRACE_STAGE_8_V2_EVIDENCE","stats":dict(s),"items":out},ensure_ascii=False,indent=2),encoding="utf-8")
    print("="*110); print("TRACE / ETAGE 8 V2 - EVIDENCE ANALYZER"); print("="*110)
    for k,v in s.items(): print(f"{k:38}: {v}")
    print("Sortie :",OUT)
if __name__=="__main__": main()
