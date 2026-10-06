# -*- coding: utf-8 -*-

"""
semantic_factual_validator.py
Valide uniquement KEEP. Aucune suppression automatique sur simple absence de preuve.
"""
import json
from pathlib import Path
from collections import Counter
ROOT = Path(__file__).resolve().parent
CAND = ROOT / "queues" / "semantic_factual_candidates.json"
INP = ROOT / "outputs" / "semantic_factual_decisions.json"
OUT = ROOT / "outputs" / "semantic_factual_validated.json"

def load(p):return json.loads(Path(p).read_text(encoding="utf-8"))
def main():
    c=load(CAND).get("candidates",[]); d=load(INP).get("decisions",[])
    if len(c)!=len(d):raise RuntimeError(f"INCOHERENCE D'EXECUTION: {len(c)} candidats mais {len(d)} décisions.")
    if [str(x.get("candidate_id")) for x in c] != [str(x.get("candidate_id")) for x in d]:
        raise RuntimeError("INCOHERENCE D'EXECUTION: candidate_id différents.")
    rows=[];sc=Counter();ac=Counter()
    for x in d:
        cls=x.get("classification")
        if cls in {"EXACT_OR_STRONG_SUPPORT","SEMANTIC_SUPPORT"} and x.get("proposed_action")=="KEEP":
            fs="SUPPORTED_KEEP";fa="NONE";reason="Relation textuellement soutenue; aucune correction requise."
        elif cls=="UNRESOLVED_ENDPOINT":
            fs="REVIEW";fa="NONE";reason="Endpoint non résolu."
        elif cls=="NEGATION_SENSITIVE":
            fs="REVIEW";fa="NONE";reason="Relation sensible à la négation; pas de correction automatique."
        elif cls in {"UNSUPPORTED_FACT","DOCUMENT_LEVEL_SUPPORT","AMBIGUOUS"}:
            fs="REVIEW";fa="NONE";reason="Absence de preuve suffisante ≠ preuve de fausseté."
        else:
            fs="REVIEW";fa="NONE";reason="Cas non démontré pour correction automatique."
        y={**x,"final_status":fs,"final_action":fa,"validator_reason":reason};rows.append(y);sc[fs]+=1;ac[fa]+=1
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps({"validator":"semantic_factual_validator","mode":"CONSERVATIVE_NO_UNSUPPORTED_DELETION_V2",
      "summary":{"candidates_current_run":len(c),"decisions_received":len(d),"status_counts":dict(sc),"action_counts":dict(ac)},"validated":rows},
      ensure_ascii=False,indent=2),encoding="utf-8")
    print("="*112);print("TRACE / SGCE - SEMANTIC FACTUAL VALIDATOR V2");print("="*112)
    print(f"Décisions reçues                    : {len(d)}");print("\nSTATUTS FINAUX");print("-"*112)
    for k,v in sc.items():print(f"{k:<52}: {v}")
    print("\nACTIONS FINALES");print("-"*112)
    for k,v in ac.items():print(f"{k:<52}: {v}")
    print(f"\nSortie                              : {OUT}\n\nAucune donnée clinique n'a été modifiée.")
if __name__=="__main__":main()
