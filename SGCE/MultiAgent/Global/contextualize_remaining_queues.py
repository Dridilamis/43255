# -*- coding: utf-8 -*-
"""Contextualise C, Patient/Reference et D en réutilisant le texte déjà attaché aux queues
ou, à défaut, le contexte B correspondant. Ne modifie aucun JSON clinique."""
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
MULTIAGENT_DIR=HERE.parent
Q=MULTIAGENT_DIR/"queues"
PAIRS=[
 ("agent_c_queue.json","agent_c_queue_contextualized.json"),
 ("patient_reference_queue.json","agent_patient_reference_queue_contextualized.json"),
 ("agent_d_queue.json","agent_d_queue_contextualized.json"),
]
def load(p):
    with p.open("r",encoding="utf-8") as f:return json.load(f)
def save(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding="utf-8")
def main():
    bctx={}
    bp=Q/"agent_b_queue_contextualized.json"
    if bp.exists():
        for x in load(bp):
            bctx[(str(x.get("document")),str(x.get("candidate_id")))]=x.get("text_context") or {}
    for srcn,dstn in PAIRS:
        src,dst=Q/srcn,Q/dstn
        if not src.exists():
            save(dst,[]); print(f"[EMPTY] {dst.name}"); continue
        out=[]
        for x in load(src):
            y=dict(x)
            tc=y.get("text_context")
            if not isinstance(tc,dict):
                tc=bctx.get((str(y.get("document")),str(y.get("candidate_id"))),{})
            y["text_context"]=tc or {}
            out.append(y)
        save(dst,out); print(f"{src.name}: {len(out)} -> {dst.name}")
if __name__=="__main__":main()
