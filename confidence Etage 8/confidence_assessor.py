# -*- coding: utf-8 -*-

"""
TRACE — ETAGE 8 V2 — Evidence-Based Confidence Assessor.
HIGH/MEDIUM/LOW/REVIEW = catégories opérationnelles TRACE, pas des probabilités.
LOW != FALSE. REVIEW != HALLUCINATION.
"""
from pathlib import Path
import json
from collections import Counter
HERE=Path(__file__).resolve().parent
INP=HERE/"outputs"/"confidence_evidence.json"; OUT=HERE/"outputs"/"confidence_assessed.json"

def assess(e):
    if e["ontology"]=="CONFLICT" or e["document"]=="AMBIGUOUS" or e["context"]=="AMBIGUOUS":
        return "REVIEW","Preuves ambiguës ou conflit structurel/ontologique."
    if e["document"]=="STRONG" and e["context"]=="SUPPORTED" and e["ontology"]=="CONSISTENT":
        return "HIGH","Ancrage documentaire fort, contexte supporté et cohérence ontologique."
    if e["document"] in ("STRONG","PARTIAL") and e["ontology"]!="CONFLICT":
        return "MEDIUM","Support présent mais incomplet sur au moins une dimension."
    return "LOW","Support disponible insuffisant; cela ne prouve pas que l'extraction est fausse."

def main():
    x=json.loads(INP.read_text(encoding="utf-8")); out=[]; s=Counter()
    for z in x["items"]:
        level,reason=assess(z["evidence"]); q=dict(z)
        q["trace_confidence"]={"level":level,"reason":reason,"method":"EVIDENCE_BASED_QUALITATIVE","is_probability":False}
        out.append(q); s[level]+=1; s[z["kind"]+"_"+level]+=1
    OUT.write_text(json.dumps({"stage":"TRACE_STAGE_8_V2_ASSESSMENT","stats":dict(s),"items":out},ensure_ascii=False,indent=2),encoding="utf-8")
    print("="*110); print("TRACE / ETAGE 8 V2 - CONFIDENCE ASSESSOR"); print("="*110)
    for k,v in s.items(): print(f"{k:38}: {v}")
    print("Sortie :",OUT)
if __name__=="__main__": main()
