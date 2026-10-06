# -*- coding: utf-8 -*-
import json, shutil
from pathlib import Path
BASE=Path(r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM\Reduction_hallucinations")
SRC=BASE/"temporal Etage 6"/"temporal_status_safe_corrected"
DEC=BASE/"negation Etage 7"/"outputs"/"negation_validated.json"
OUT=BASE/"negation Etage 7"/"negation_safe_corrected"
REPORT=OUT/"negation_correction_report.json"
if OUT.exists(): shutil.rmtree(OUT)
shutil.copytree(SRC,OUT)
def load(p): return json.loads(p.read_text(encoding="utf-8"))
def save(p,x): p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding="utf-8")
def eid(e): return e.get("identifiant_entite") or e.get("id") or e.get("entity_id")
def entities(d):
    a=list(d.get("global_entities",[]) or [])
    for p in d.get("pages",[]) or []: a.extend(p.get("entities",[]) or [])
    return a
actions=[x for x in load(DEC).get("validated_decisions",[]) if x.get("final_status")=="SAFE_ACCEPT" and x.get("final_action") in ("SET_NEGATED","SET_AFFIRMED")]
ops=[]; errors=[]; modified=set()
for x in actions:
    path=OUT/x["document"]
    try:
        d=load(path); changed=0; before=None; new="NEGATED" if x["final_action"]=="SET_NEGATED" else "AFFIRMED"
        for e in entities(d):
            if str(eid(e))==str(x["entity_id"]):
                if not isinstance(e.get("trace_context_status"),dict): e["trace_context_status"]={}
                old=e["trace_context_status"].get("clinical_status")
                if before is None: before=old
                if old!=new:
                    e["trace_context_status"]["clinical_status"]=new; changed+=1
        if changed:
            save(path,d); modified.add(x["document"])
            ops.append({"document":x["document"],"entity_id":x["entity_id"],"action":x["final_action"],"before":before,"after":new,"physical_occurrences_changed":changed,"sentence":x.get("sentence"),"status":"APPLIED"})
    except Exception as exc: errors.append({"document":x.get("document"),"entity_id":x.get("entity_id"),"error":str(exc)})
save(REPORT,{"corrector":"negation_safe_corrector","mode":"FINAL_SAFE_REPAIR","summary":{"safe_actions_received":len(actions),"operations_applied":len(ops),"documents_modified":len(modified),"errors":len(errors)},"operations":ops,"errors":errors})
print("="*112); print("TRACE / SGCE - NEGATION SAFE CORRECTOR - FINAL SAFE REPAIR"); print("="*112)
print(f"Actions SAFE_ACCEPT reÃ§ues          : {len(actions)}\nOpÃ©rations appliquÃ©es               : {len(ops)}\nDocuments modifiÃ©s                  : {len(modified)}\nErreurs                             : {len(errors)}")
print("\nCORRECTIONS AVANT -> APRES"); print("-"*112)
for o in ops:
    print(f'{o["document"]} | {o["entity_id"]} | {o["action"]}\n  AVANT : {o["before"]!r}\n  APRES : {o["after"]!r}\n  TEXTE : {o["sentence"]!r}\n')
print(f"Sortie clinique                     : {OUT}\nRapport                             : {REPORT}")
print("\nLes fichiers sources n'ont pas Ã©tÃ© modifiÃ©s.")

