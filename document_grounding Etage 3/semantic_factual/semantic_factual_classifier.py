# -*- coding: utf-8 -*-

"""
semantic_factual_classifier.py
Classification conservatrice des relations.
IMPORTANT : UNSUPPORTED_FACT n'est jamais une preuve suffisante de fausseté.
"""
import json,re,unicodedata
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent
INPUT_FILE = ROOT / "queues" / "semantic_factual_candidates.json"
OUTPUT_FILE = ROOT / "outputs" / "semantic_factual_decisions.json"

def norm(s):
    s=unicodedata.normalize("NFKD",str(s or ""))
    s="".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+"," ",s).strip()
def tokens(s):
    return {x for x in re.findall(r"[a-z0-9µ°%]+",norm(s)) if len(x)>2}
def overlap(a,b):
    A=tokens(a);B=tokens(b)
    return len(A&B)/max(1,min(len(A),len(B))) if A and B else 0.0

def classify(x):
    y=dict(x); cls="AMBIGUOUS"; conf=0.0; reason="Preuve insuffisante."; action="NONE"
    if not x.get("source_resolved") or not x.get("target_resolved"):
        cls="UNRESOLVED_ENDPOINT";reason="Au moins un endpoint de relation n'est pas résolu."
    else:
        sp=x.get("source_proof") or ""; tp=x.get("target_proof") or ""
        st=x.get("source_text") or ""; tt=x.get("target_text") or ""
        # La relation est bien ancrée si chaque endpoint possède une preuve qui soutient sa propre mention.
        os=overlap(st,sp); ot=overlap(tt,tp)
        if sp and tp and os>=0.65 and ot>=0.65:
            cls="EXACT_OR_STRONG_SUPPORT";conf=min(1.0,(os+ot)/2);reason="Les deux endpoints sont fortement ancrés dans leurs preuves textuelles.";action="KEEP"
        elif (sp and os>=0.45) and (tp and ot>=0.45):
            cls="SEMANTIC_SUPPORT";conf=min(0.95,(os+ot)/2);reason="Les deux endpoints disposent d'un support lexical/semantique local.";action="KEEP"
        elif x.get("source_in_document") and x.get("target_in_document"):
            cls="DOCUMENT_LEVEL_SUPPORT";conf=0.70;reason="Les deux endpoints sont retrouvés dans le document, mais le lien relationnel local reste à confirmer.";action="NONE"
        else:
            cls="UNSUPPORTED_FACT";conf=0.0;reason="Le support textuel de la relation n'est pas suffisamment démontré.";action="NONE"
    # Garde négation: une relation impliquant un endpoint NEGATED n'est jamais supprimée automatiquement ici.
    if str(x.get("source_clinical_status") or "").upper()=="NEGATED" or str(x.get("target_clinical_status") or "").upper()=="NEGATED":
        if cls not in {"UNRESOLVED_ENDPOINT"}:
            cls="NEGATION_SENSITIVE";conf=0.0;reason="Relation impliquant un endpoint NEGATED : revue sémantique requise.";action="NONE"
    y.update({"classification":cls,"confidence":round(conf,4),"proposed_action":action,"classifier_reason":reason})
    return y

def main():
    data=json.loads(INPUT_FILE.read_text(encoding="utf-8")); cand=data.get("candidates",[])
    rows=[classify(x) for x in cand]; cc=Counter(x["classification"] for x in rows); ac=Counter(x["proposed_action"] for x in rows)
    OUTPUT_FILE.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps({"classifier":"semantic_factual_classifier","mode":"CONSERVATIVE_SUPPORT_AUDIT_V2",
      "source_candidate_count":len(cand),"summary":{"decisions_written":len(rows),"classification_counts":dict(cc),"action_counts":dict(ac)},"decisions":rows},
      ensure_ascii=False,indent=2),encoding="utf-8")
    print("="*112);print("TRACE / SGCE - SEMANTIC FACTUAL CLASSIFIER V2");print("="*112)
    print(f"Cas reçus                           : {len(cand)}")
    print("\nCLASSIFICATIONS");print("-"*112)
    for k,v in cc.items():print(f"{k:<52}: {v}")
    print("\nACTIONS PROPOSEES");print("-"*112)
    for k,v in ac.items():print(f"{k:<52}: {v}")
    print(f"\nSortie                              : {OUTPUT_FILE}\n\nAucune donnée clinique n'a été modifiée.")
if __name__=="__main__":main()
