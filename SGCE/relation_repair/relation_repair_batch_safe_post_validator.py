# -*- coding: utf-8 -*-
"""
relation_repair_batch_safe_post_validator.py
============================================

Post-validation globale du lot relationnel sûr.

AVANT :
  MultiAgent/multiagent_safe_final_corrected

APRES :
  MultiAgent/relation_repair/relation_repair_safe_corrected

PASS seulement si :
- aucun document manquant/supplémentaire
- aucune modification inattendue
- 0 nouvelle anomalie ontologique
- anomalies après <= anomalies avant
"""

import json
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
SGCE_DIR = HERE.parent
BASE_DIR = SGCE_DIR.parent
BEFORE_DIR = SGCE_DIR / "Patterns" / "PatternD" / "corrected"
AFTER_DIR = HERE / "corrected"
CORRECTION_REPORT = AFTER_DIR / "relation_repair_safe_correction_report.json"
GUIDELINE_CANDIDATES = [
    BASE_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
    BASE_DIR.parent / "Guideline_TRACE_Sepsis_v1.6.json",
    Path.cwd() / "Guideline_TRACE_Sepsis_v1.6.json",
    HERE / "Guideline_TRACE_Sepsis_v1.6.json",
]
REPORT_FILE = HERE / "post_validation" / "relation_repair_batch_safe_post_validation_report.json"


def load_json(path):
    with path.open("r",encoding="utf-8") as f:
        return json.load(f)


def save_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(
        json.dumps(data,ensure_ascii=False,indent=2),
        encoding="utf-8",
    )


def resolve_guideline():
    for p in GUIDELINE_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError("Guideline introuvable.")


def entity_id(e):
    return e.get("identifiant_entite") or e.get("id") or e.get("entity_id")


def entity_type(e):
    return e.get("categorie") or e.get("type") or e.get("entity_type") or ""


def relation_id(r):
    return r.get("identifiant_relation") or r.get("id") or r.get("relation_id")


def relation_type(r):
    return (
        r.get("type_relation")
        or r.get("relation")
        or r.get("relation_type")
        or r.get("predicate")
        or r.get("type")
        or ""
    )


def relation_source(r):
    return (
        r.get("identifiant_entite_sujet")
        or r.get("from_id")
        or r.get("subject_id")
        or r.get("source")
    )


def relation_target(r):
    return (
        r.get("identifiant_entite_objet")
        or r.get("to_id")
        or r.get("object_id")
        or r.get("target")
    )


def get_entities(doc):
    if isinstance(doc.get("global_entities"),list):
        return doc["global_entities"]
    out=[]
    for p in doc.get("pages",[]) or []:
        out.extend(p.get("entities",[]) or [])
    return out


def get_relations(doc):
    if isinstance(doc.get("global_relations"),list):
        return doc["global_relations"]
    out=[]
    for p in doc.get("pages",[]) or []:
        out.extend(p.get("relations",[]) or [])
    return out


def load_signatures():
    data=load_json(resolve_guideline())
    root=data.get("ontologie_sepsis_graph",data)
    locked=root.get("signatures_relations_verrouillees_v1_5",{})

    result={}

    for name,spec in (
        locked.items()
        if isinstance(locked,dict)
        else []
    ):
        if (
            isinstance(spec,dict)
            and spec.get("domaine")
            and spec.get("image")
        ):
            result[name]={
                "domaine":spec["domaine"],
                "image":spec["image"],
            }

    return result


def audit_document(doc,sigs):
    entity_map={
        str(entity_id(e)):e
        for e in get_entities(doc)
        if entity_id(e) is not None
    }

    anomalies=set()

    for r in get_relations(doc):
        rid=str(relation_id(r))
        rt=relation_type(r)
        sid=relation_source(r)
        tid=relation_target(r)

        s=entity_map.get(str(sid))
        t=entity_map.get(str(tid))

        if s is None:
            anomalies.add(("ORPHAN_SOURCE",rid,str(sid)))

        if t is None:
            anomalies.add(("ORPHAN_TARGET",rid,str(tid)))

        sig=sigs.get(rt)

        if not sig:
            anomalies.add(("UNAUTHORIZED_RELATION",rid,str(rt)))
            continue

        if s is not None and entity_type(s)!=sig["domaine"]:
            anomalies.add(
                ("INVALID_SOURCE_TYPE",rid,entity_type(s),sig["domaine"])
            )

        if t is not None and entity_type(t)!=sig["image"]:
            anomalies.add(
                ("INVALID_TARGET_TYPE",rid,entity_type(t),sig["image"])
            )

    return anomalies


def clinical_docs(directory):
    docs={}

    for p in directory.glob("*.json"):
        if p.name.endswith("_report.json"):
            continue

        try:
            x=load_json(p)

            if (
                isinstance(x,dict)
                and any(
                    k in x
                    for k in (
                        "pages",
                        "global_entities",
                        "global_relations",
                    )
                )
            ):
                docs[p.name]=x

        except:
            pass

    return docs


def h(doc):
    return hashlib.sha256(
        json.dumps(
            doc,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",",":"),
        ).encode("utf-8")
    ).hexdigest()


def main():
    before=clinical_docs(BEFORE_DIR)
    after=clinical_docs(AFTER_DIR)
    correction=load_json(CORRECTION_REPORT)
    sigs=load_signatures()

    before_names=set(before)
    after_names=set(after)

    common=before_names&after_names
    missing=before_names-after_names
    extra=after_names-before_names

    expected=set(
        correction.get("modified_documents",[])
    )

    actual={
        name
        for name in common
        if h(before[name])!=h(after[name])
    }

    unexpected=actual-expected
    absent=expected-actual

    bmap={}
    amap={}

    for docname,doc in before.items():
        for a in audit_document(doc,sigs):
            bmap[(docname,)+tuple(a)]=a

    for docname,doc in after.items():
        for a in audit_document(doc,sigs):
            amap[(docname,)+tuple(a)]=a

    new=set(amap)-set(bmap)
    resolved=set(bmap)-set(amap)

    final_pass=(
        not missing
        and not extra
        and not unexpected
        and not absent
        and len(new)==0
        and len(amap)<=len(bmap)
    )

    report={
        "validator":"relation_repair_batch_safe_post_validator",
        "status":"PASS" if final_pass else "FAIL",

        "summary":{
            "documents_checked":len(common),
            "expected_modified":len(expected),
            "actually_modified":len(actual),
            "unexpected_modified":len(unexpected),
            "missing_expected_changes":len(absent),
            "anomalies_before":len(bmap),
            "anomalies_after":len(amap),
            "new_anomalies":len(new),
            "resolved_anomalies":len(resolved),
            "missing_documents":len(missing),
            "extra_documents":len(extra),
        },

        "new_anomalies":[list(x) for x in sorted(new)],
        "resolved_anomalies":[list(x) for x in sorted(resolved)],
    }

    save_json(REPORT_FILE,report)

    print("="*108)
    print("TRACE / SGCE - RELATION REPAIR BATCH SAFE POST-VALIDATION")
    print("="*108)
    print(f"AVANT                               : {BEFORE_DIR}")
    print(f"APRES                               : {AFTER_DIR}")
    print()
    print(f"Documents vérifiés                  : {len(common)}")
    print(f"Documents attendus modifiés         : {len(expected)}")
    print(f"Documents réellement modifiés       : {len(actual)}")
    print(f"Modifications inattendues           : {len(unexpected)}")
    print(f"Corrections attendues absentes      : {len(absent)}")
    print()
    print(f"Anomalies AVANT                     : {len(bmap)}")
    print(f"Anomalies APRES                     : {len(amap)}")
    print(f"Nouvelles anomalies                 : {len(new)}")
    print(f"Anomalies résolues                  : {len(resolved)}")
    print()
    print(f"Docs manquants APRES                : {len(missing)}")
    print(f"Docs supplémentaires APRES          : {len(extra)}")
    print()
    print(
        f"STATUT FINAL BATCH SAFE            : "
        f"{'PASS' if final_pass else 'FAIL'}"
    )
    print()
    print(f"Rapport                             : {REPORT_FILE}")
    print()
    print("Aucune donnée clinique n'a été modifiée par ce post-validateur.")


if __name__=="__main__":
    main()
