# -*- coding: utf-8 -*-
import json
from pathlib import Path
BASE=Path(r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM\Reduction_hallucinations")
BEFORE=BASE/"temporal Etage 6"/"temporal_status_safe_corrected"
AFTER=BASE/"negation Etage 7"/"negation_safe_corrected"
REP=AFTER/"negation_correction_report.json"
OUT=BASE/"negation Etage 7"/"post_validation"/"negation_post_validation_report.json"
OUT.parent.mkdir(parents=True,exist_ok=True)
def load(p): return json.loads(p.read_text(encoding="utf-8"))
def eid(e): return e.get("identifiant_entite") or e.get("id") or e.get("entity_id")
def ents(d):
    a=list(d.get("global_entities",[]) or [])
    for p in d.get("pages",[]) or []: a.extend(p.get("entities",[]) or [])
    return a
def smap(d):
    r={}
    for e in ents(d): r.setdefault(str(eid(e)),[]).append((e.get("trace_context_status") or {}).get("clinical_status"))
    return r
ops=load(REP).get("operations",[])
expected={(x["document"],str(x["entity_id"])):x["after"] for x in ops}
fails=[]; unexpected=[]; docs=0
bn={p.name for p in BEFORE.glob("*.json") if not p.name.endswith("_report.json")}
an={p.name for p in AFTER.glob("*.json") if not p.name.endswith("_report.json")}
for name in sorted(bn&an):
    try: b=load(BEFORE/name); a=load(AFTER/name)
    except: continue
    docs+=1; bm=smap(b); am=smap(a)
    for i in set(bm)|set(am):
        if bm.get(i)!=am.get(i) and (name,i) not in expected:
            unexpected.append({"document":name,"entity_id":i})
for (name,i),new in expected.items():
    try: vals=smap(load(AFTER/name)).get(i,[])
    except: vals=[]
    if new not in vals: fails.append({"document":name,"entity_id":i,"expected":new,"actual":vals})
missing=sorted(bn-an); extra=sorted(an-bn)
passed=not fails and not unexpected and not missing and not extra
OUT.write_text(json.dumps({"post_validator":"negation_post_validator","mode":"FINAL_SAFE_REPAIR","summary":{"documents_verified":docs,"operations_expected":len(expected),"operations_fail":len(fails),"unexpected_clinical_changes":len(unexpected),"missing_documents_after":len(missing),"extra_documents_after":len(extra),"status":"PASS" if passed else "FAIL"},"fails":fails,"unexpected_changes":unexpected},ensure_ascii=False,indent=2),encoding="utf-8")
print("="*112); print("TRACE / SGCE - NEGATION POST-VALIDATION - FINAL SAFE REPAIR"); print("="*112)
print(f"Documents vÃ©rifiÃ©s                  : {docs}\nOpÃ©rations attendues                : {len(expected)}\nOpÃ©rations FAIL                     : {len(fails)}\nChangements cliniques inattendus    : {len(unexpected)}")
print(f"\nDocs manquants APRES                : {len(missing)}\nDocs supplÃ©mentaires APRES          : {len(extra)}")
print(f"\nSTATUT FINAL NEGATION REPAIR        : {'PASS' if passed else 'FAIL'}\n\nRapport                             : {OUT}")
print("\nAucune donnÃ©e clinique n'a Ã©tÃ© modifiÃ©e par ce post-validateur.")

