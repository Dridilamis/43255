# -*- coding: utf-8 -*-
import json, hashlib
from pathlib import Path

BASE_DIR=Path(r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM\Reduction_hallucinations")
M=BASE_DIR/"MultiAgent"
BEFORE_CANDIDATES=[M/"agent_patient_reference_corrected",M/"agent_c_corrected"]
AFTER=M/"agent_d_corrected"
CORR=AFTER/"agent_d_correction_report.json"
OUT=M/"agent_d_post_validation"/"agent_d_post_validation_report.json"

def load_json(p):
    with p.open("r",encoding="utf-8") as f:return json.load(f)

def save_json(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding="utf-8")

def resolve_before():
    for d in BEFORE_CANDIDATES:
        if d.exists() and any(d.glob("*.json")):return d
    raise FileNotFoundError("AVANT Agent D introuvable.")

def clinical(d):
    z={}
    for p in d.glob("*.json"):
        if p.name.endswith("_report.json"):continue
        try:
            x=load_json(p)
            if isinstance(x,dict) and any(k in x for k in ("pages","global_entities","global_relations")):z[p.name]=x
        except:pass
    return z

def h(x):
    return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def main():
    before=resolve_before();b=clinical(before);a=clinical(AFTER);corr=load_json(CORR)
    expected=set(corr.get("modified_documents",[]))
    common=set(b)&set(a)
    actual={n for n in common if h(b[n])!=h(a[n])}
    missing=set(b)-set(a);extra=set(a)-set(b)
    unexpected=actual-expected;absent=expected-actual
    final=not missing and not extra and not unexpected and not absent

    save_json(OUT,{"validator":"agent_d_post_validator","status":"PASS" if final else "FAIL",
                   "summary":{"documents_checked":len(common),"expected_modified":len(expected),
                              "actually_modified":len(actual),"unexpected_modified":len(unexpected),
                              "missing_expected_changes":len(absent),"missing_documents":len(missing),
                              "extra_documents":len(extra)},
                   "expected_modified_documents":sorted(expected),
                   "actually_modified_documents":sorted(actual),
                   "unexpected_modified_documents":sorted(unexpected),
                   "missing_expected_changes":sorted(absent)})

    print("="*96)
    print("TRACE / SGCE - AGENT D POST-VALIDATION")
    print("="*96)
    print(f"AVANT                              : {before}")
    print(f"APRES                              : {AFTER}")
    print(f"\nDocuments vÃ©rifiÃ©s                 : {len(common)}")
    print(f"Documents attendus modifiÃ©s        : {len(expected)}")
    print(f"Documents rÃ©ellement modifiÃ©s      : {len(actual)}")
    print(f"Modifications inattendues          : {len(unexpected)}")
    print(f"Corrections attendues absentes     : {len(absent)}")
    print(f"Docs manquants APRES               : {len(missing)}")
    print(f"Docs supplÃ©mentaires APRES         : {len(extra)}")
    print(f"\nSTATUT FINAL AGENT D               : {'PASS' if final else 'FAIL'}")
    print(f"\nRapport                            : {OUT}")
    print("\nAucune donnÃ©e clinique n'a Ã©tÃ© modifiÃ©e par ce post-validateur.")

if __name__=="__main__":main()

