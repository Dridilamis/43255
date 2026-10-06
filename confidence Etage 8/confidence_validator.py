# -*- coding: utf-8 -*-

"""TRACE — ETAGE 8 V2 — Conservative Confidence Validator."""
from pathlib import Path
import json
from collections import Counter
HERE=Path(__file__).resolve().parent
INP=HERE/"outputs"/"confidence_assessed.json"; OUT=HERE/"outputs"/"confidence_validated.json"
ALLOWED={"HIGH","MEDIUM","LOW","REVIEW"}

def main():
    x=json.loads(INP.read_text(encoding="utf-8")); out=[]; s=Counter()
    for z in x["items"]:
        q=dict(z); tc=dict(q["trace_confidence"]); e=q["evidence"]
        if tc["level"]=="HIGH" and not (e["document"]=="STRONG" and e["context"]=="SUPPORTED" and e["ontology"]=="CONSISTENT"):
            tc={"level":"REVIEW","reason":"HIGH refusé par le validateur: preuves insuffisantes.","method":"EVIDENCE_BASED_QUALITATIVE","is_probability":False}
        if tc["level"] not in ALLOWED: raise SystemExit("Niveau de confiance invalide.")
        tc["validated"]=True; q["trace_confidence"]=tc; out.append(q)
        s[tc["level"]]+=1; s[q["kind"]+"_"+tc["level"]]+=1
    OUT.write_text(json.dumps({"stage":"TRACE_STAGE_8_V2_VALIDATION","stats":dict(s),"items":out},ensure_ascii=False,indent=2),encoding="utf-8")
    print("="*110); print("TRACE / ETAGE 8 V2 - CONFIDENCE VALIDATOR"); print("="*110)
    for k,v in s.items(): print(f"{k:38}: {v}")
    print("Sortie :",OUT)
if __name__=="__main__": main()
