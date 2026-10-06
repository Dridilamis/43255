# -*- coding: utf-8 -*-
"""
SGCE — Pattern B1 Differential Post-Validator

Compare:
  BEFORE = PatternA/PatternA6/corrected
  AFTER  = PatternB/PatternB1/corrected

Vérifie les corrections B1 autorisées par le validator/corrector :
- RELINK
- CREATE_AND_LINK
- intégrité des endpoints
- unicité des IDs d'entités
- conservation des documents
- aucune nouvelle relation orpheline introduite par B1
"""
import csv
import json
from collections import Counter
from pathlib import Path

PATTERN_B1_DIR = Path(__file__).resolve().parent
PATTERN_B_DIR = PATTERN_B1_DIR.parent
PATTERNS_DIR = PATTERN_B_DIR.parent
SGCE_DIR = PATTERNS_DIR.parent
BASE_DIR = SGCE_DIR.parent
PATTERN_A6_DIR = PATTERNS_DIR / "PatternA" / "PatternA6"

BEFORE_DIR = PATTERN_A6_DIR / "corrected"
AFTER_DIR = PATTERN_B1_DIR / "corrected"
CORRECTION_REPORT = AFTER_DIR / "pattern_b1_correction_report.json"

OUTPUT_DIR = PATTERN_B1_DIR / "post_validation"
OUTPUT_JSON = OUTPUT_DIR / "pattern_b1_post_validation_report.json"
OUTPUT_CSV = OUTPUT_DIR / "pattern_b1_post_validation_anomalies.csv"

def load_json(p):
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)

def is_clinical(doc):
    return isinstance(doc, dict) and (
        isinstance(doc.get("global_entities"), list)
        or isinstance(doc.get("pages"), list)
    )

def eid(e):
    return e.get("identifiant_entite") or e.get("id") or e.get("entity_id")

def rid(r):
    return r.get("identifiant_relation") or r.get("id") or r.get("relation_id")

def rsrc(r):
    return (r.get("identifiant_entite_sujet") or r.get("from_id")
            or r.get("subject_id") or r.get("sujet") or r.get("subject"))

def rtgt(r):
    return (r.get("identifiant_entite_objet") or r.get("to_id")
            or r.get("object_id") or r.get("objet") or r.get("object"))

def entity_texts(e):
    vals=[]
    for k in ("name","valeur","libelle","preuve","parametre","texte","text"):
        v=e.get(k)
        if v not in (None,""):
            vals.append(str(v).strip().lower())
    return vals

def entities(doc):
    if isinstance(doc.get("global_entities"), list):
        return doc["global_entities"]
    out=[]
    for p in doc.get("pages",[]) or []:
        out.extend(p.get("entities",[]) or [])
    return out

def relations(doc):
    if isinstance(doc.get("global_relations"), list):
        return doc["global_relations"]
    out=[]
    for p in doc.get("pages",[]) or []:
        out.extend(p.get("relations",[]) or [])
    return out

def endpoint_resolves(v, ents):
    if v in (None,""):
        return False
    s=str(v).strip()
    ids={str(eid(e)).strip() for e in ents if eid(e)}
    if s in ids:
        return True
    low=s.lower()
    return any(low in entity_texts(e) for e in ents)

def anomalies(doc):
    es=entities(doc); rs=relations(doc)
    ids=[str(eid(e)) for e in es if eid(e)]
    dup={x for x,c in Counter(ids).items() if c>1}
    out=set()
    for x in dup:
        out.add(("DUPLICATE_ENTITY_ID",x))
    for r in rs:
        key=str(rid(r) or f"{rsrc(r)}->{rtgt(r)}")
        if not endpoint_resolves(rsrc(r),es):
            out.add(("ORPHAN_SOURCE",key))
        if not endpoint_resolves(rtgt(r),es):
            out.add(("ORPHAN_TARGET",key))
    return out

def main():
    if not BEFORE_DIR.exists():
        raise FileNotFoundError(f"Entrée AVANT B1 introuvable : {BEFORE_DIR}")
    if not AFTER_DIR.exists():
        raise FileNotFoundError(f"Sortie APRÈS B1 introuvable : {AFTER_DIR}")
    if not CORRECTION_REPORT.exists():
        raise FileNotFoundError(f"Rapport de correction introuvable : {CORRECTION_REPORT}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    correction=load_json(CORRECTION_REPORT)
    ops=correction.get("operations",[])

    before_files={}
    after_files={}
    for p in BEFORE_DIR.glob("*.json"):
        try:
            d=load_json(p)
            if is_clinical(d): before_files[p.name]=d
        except Exception:
            pass
    for p in AFTER_DIR.glob("*.json"):
        try:
            d=load_json(p)
            if is_clinical(d): after_files[p.name]=d
        except Exception:
            pass

    anomalies_rows=[]
    docs_pass=docs_fail=0
    pre_total=new_total=resolved_total=0

    all_names=sorted(set(before_files)|set(after_files))
    for name in all_names:
        b=before_files.get(name); a=after_files.get(name)
        if b is None:
            anomalies_rows.append({"document":name,"kind":"MISSING_BEFORE","detail":""})
            docs_fail+=1; continue
        if a is None:
            anomalies_rows.append({"document":name,"kind":"MISSING_AFTER","detail":""})
            docs_fail+=1; continue

        ba=anomalies(b); aa=anomalies(a)
        new=aa-ba; resolved=ba-aa
        pre_total += len(ba)
        new_total += len(new)
        resolved_total += len(resolved)

        if new:
            docs_fail+=1
            for kind,detail in sorted(new):
                anomalies_rows.append({"document":name,"kind":kind,"detail":detail})
        else:
            docs_pass+=1

    # Validation explicite des opérations enregistrées.
    operation_checks=[]
    op_fail=0
    relink_expected=create_expected=0
    relink_pass=create_pass=0

    for op in ops:
        name=op.get("document")
        after=after_files.get(name)
        for m in op.get("modifications",[]) or []:
            typ=m.get("operation")
            ok=False
            detail=""
            if after is None:
                detail="Document AFTER absent"
            elif typ=="RELINK":
                relink_expected+=1
                new_id=m.get("new_entity_id")
                ok=any(str(eid(e))==str(new_id) for e in entities(after))
                detail=f"new_entity_id={new_id}"
                if ok: relink_pass+=1
            elif typ=="CREATE_AND_LINK":
                create_expected+=1
                new_id=m.get("created_entity_id")
                matches=[e for e in entities(after) if str(eid(e))==str(new_id)]
                ok=(len(matches)==1 and matches[0].get("_sgce_pattern")=="B1")
                detail=f"created_entity_id={new_id}"
                if ok: create_pass+=1
            else:
                continue
            if not ok: op_fail+=1
            operation_checks.append({
                "document":name,"operation":typ,"pass":ok,"detail":detail
            })

    final_pass=(docs_fail==0 and op_fail==0)

    report={
        "pattern":"B1",
        "mode":"DIFFERENTIAL_POST_VALIDATION",
        "before_directory":str(BEFORE_DIR),
        "after_directory":str(AFTER_DIR),
        "correction_report":str(CORRECTION_REPORT),
        "summary":{
            "documents_checked":len(all_names),
            "documents_pass":docs_pass,
            "documents_fail":docs_fail,
            "operations_recorded":len(ops),
            "relink_expected":relink_expected,
            "relink_pass":relink_pass,
            "create_and_link_expected":create_expected,
            "create_and_link_pass":create_pass,
            "operation_fail":op_fail,
            "preexisting_anomalies":pre_total,
            "new_anomalies_b1":new_total,
            "resolved_anomalies_b1":resolved_total,
            "final_status":"PASS" if final_pass else "FAIL",
        },
        "operation_checks":operation_checks,
        "new_anomalies":anomalies_rows,
    }
    OUTPUT_JSON.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")

    with OUTPUT_CSV.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["document","kind","detail"])
        w.writeheader(); w.writerows(anomalies_rows)

    print("="*78)
    print("SGCE - PATTERN B1 DIFFERENTIAL POST-VALIDATION")
    print("="*78)
    print(f"AVANT B1                : {BEFORE_DIR}")
    print(f"APRES B1                : {AFTER_DIR}")
    print()
    print(f"Documents vérifiés      : {len(all_names)}")
    print(f"PASS                    : {docs_pass}")
    print(f"FAIL                    : {docs_fail}")
    print()
    print(f"RELINK                  : {relink_pass}/{relink_expected}")
    print(f"CREATE_AND_LINK         : {create_pass}/{create_expected}")
    print(f"Opérations FAIL         : {op_fail}")
    print()
    print(f"Anomalies pré-existantes: {pre_total}")
    print(f"Nouvelles anomalies B1  : {new_total}")
    print(f"Anomalies résolues B1   : {resolved_total}")
    print()
    print(f"STATUT FINAL B1         : {'PASS' if final_pass else 'FAIL'}")
    print()
    print(f"Rapport JSON            : {OUTPUT_JSON}")
    print(f"Rapport CSV             : {OUTPUT_CSV}")

    if not final_pass:
        raise SystemExit(1)

if __name__=="__main__":
    main()
