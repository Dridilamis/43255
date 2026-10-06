# -*- coding: utf-8 -*-
"""
duplicate_entity_post_validator.py
==================================

Compare AVANT/APRES fusion doublons.

AVANT :
  MultiAgent/relation_repair/relation_repair_safe_corrected

APRES :
  MultiAgent/duplicate_entity/duplicate_entity_safe_merged

PASS si :
- aucun document manquant/supplémentaire
- aucune modification inattendue
- aucune nouvelle anomalie structurelle
- nombre de doublons de contenu diminue ou reste stable
"""

import json
import hashlib
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ONTOLOGY_DUPLICATES_DIR = ROOT.parent
STAGE4_DIR = ONTOLOGY_DUPLICATES_DIR.parent
REDUCTION_DIR = STAGE4_DIR.parent
PROJECT_DIR = REDUCTION_DIR.parent

BEFORE_DIR = ONTOLOGY_DUPLICATES_DIR / "duplicate_relations" / "duplicate_relation_cleaned"
AFTER_DIR = ROOT / "duplicate_entity_safe_merged"
CORRECTION_REPORT = AFTER_DIR / "duplicate_entity_merge_report.json"

GUIDELINE_CANDIDATES = [
    PROJECT_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
    REDUCTION_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
    STAGE4_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
    Path.cwd() / "Guideline_TRACE_Sepsis_v1.6.json",
]
REPORT_FILE = ROOT / "post_validation" / "duplicate_entity_post_validation_report.json"


def load_json(path):
    with path.open("r",encoding="utf-8") as f:
        return json.load(f)


def save_json(path,data):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def resolve_guideline():
    for p in GUIDELINE_CANDIDATES:
        if p.exists():
            return p

    raise FileNotFoundError(
        "Guideline introuvable."
    )


def normalize(text):
    text=unicodedata.normalize(
        "NFKD",
        str(text or "").lower(),
    )

    text="".join(
        c
        for c in text
        if not unicodedata.combining(c)
    )

    text=re.sub(
        r"[^a-z0-9/+.-]+",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def entity_id(e):
    return e.get("identifiant_entite") or e.get("id") or e.get("entity_id")


def entity_type(e):
    return e.get("categorie") or e.get("type") or e.get("entity_type") or ""


def entity_text(e):
    vals=[]

    for key in (
        "preuve",
        "name",
        "valeur",
        "libelle",
        "parametre",
        "texte",
        "text",
    ):
        v=e.get(key)

        if v not in (None,""):
            vals.append(str(v).strip())

    return " | ".join(vals)


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


def signatures():
    data=load_json(
        resolve_guideline()
    )

    root=data.get(
        "ontologie_sepsis_graph",
        data,
    )

    locked=root.get(
        "signatures_relations_verrouillees_v1_5",
        {},
    )

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


def audit(doc,sigs):
    entities={
        str(entity_id(e)):e
        for e in get_entities(doc)
        if entity_id(e) is not None
    }

    out=set()

    for r in get_relations(doc):
        rid=str(relation_id(r))
        rt=relation_type(r)
        sid=relation_source(r)
        tid=relation_target(r)

        s=entities.get(str(sid))
        t=entities.get(str(tid))

        if s is None:
            out.add(("ORPHAN_SOURCE",rid,str(sid)))

        if t is None:
            out.add(("ORPHAN_TARGET",rid,str(tid)))

        sig=sigs.get(rt)

        if not sig:
            continue

        if (
            s is not None
            and entity_type(s)!=sig["domaine"]
        ):
            out.add(
                (
                    "INVALID_SOURCE_TYPE",
                    rid,
                    entity_type(s),
                    sig["domaine"],
                )
            )

        if (
            t is not None
            and entity_type(t)!=sig["image"]
        ):
            out.add(
                (
                    "INVALID_TARGET_TYPE",
                    rid,
                    entity_type(t),
                    sig["image"],
                )
            )

    return out


def duplicate_content_count(doc):
    groups=defaultdict(set)

    for e in get_entities(doc):
        eid=entity_id(e)
        etype=entity_type(e)
        text=normalize(entity_text(e))

        if eid is None or not etype or not text:
            continue

        groups[
            (
                etype,
                text,
            )
        ].add(str(eid))

    return sum(
        1
        for ids in groups.values()
        if len(ids)>1
    )


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

    correction=load_json(
        CORRECTION_REPORT
    )

    sigs=signatures()

    before_names=set(before)
    after_names=set(after)

    common=before_names&after_names
    missing=before_names-after_names
    extra=after_names-before_names

    expected=set(
        correction.get(
            "modified_documents",
            []
        )
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

    duplicate_before=0
    duplicate_after=0

    for docname,doc in before.items():
        duplicate_before+=duplicate_content_count(doc)

        for a in audit(doc,sigs):
            bmap[(docname,)+tuple(a)]=a

    for docname,doc in after.items():
        duplicate_after+=duplicate_content_count(doc)

        for a in audit(doc,sigs):
            amap[(docname,)+tuple(a)]=a

    new=set(amap)-set(bmap)
    resolved=set(bmap)-set(amap)

    final_pass=(
        not missing
        and not extra
        and not unexpected
        and not absent
        and len(new)==0
        and duplicate_after<=duplicate_before
    )

    report={
        "validator":"duplicate_entity_post_validator",
        "status":"PASS" if final_pass else "FAIL",

        "summary":{
            "documents_checked":len(common),
            "expected_modified":len(expected),
            "actually_modified":len(actual),
            "unexpected_modified":len(unexpected),
            "missing_expected_changes":len(absent),
            "structural_anomalies_before":len(bmap),
            "structural_anomalies_after":len(amap),
            "new_structural_anomalies":len(new),
            "resolved_structural_anomalies":len(resolved),
            "duplicate_groups_before":duplicate_before,
            "duplicate_groups_after":duplicate_after,
            "missing_documents":len(missing),
            "extra_documents":len(extra),
        },
    }

    save_json(
        REPORT_FILE,
        report,
    )

    print("="*108)
    print("TRACE / SGCE - DUPLICATE ENTITY POST-VALIDATION")
    print("="*108)
    print(f"Documents vérifiés                  : {len(common)}")
    print(f"Documents attendus modifiés         : {len(expected)}")
    print(f"Documents réellement modifiés       : {len(actual)}")
    print(f"Modifications inattendues           : {len(unexpected)}")
    print(f"Corrections attendues absentes      : {len(absent)}")
    print()
    print(f"Anomalies structurelles AVANT       : {len(bmap)}")
    print(f"Anomalies structurelles APRES       : {len(amap)}")
    print(f"Nouvelles anomalies structurelles   : {len(new)}")
    print(f"Anomalies structurelles résolues    : {len(resolved)}")
    print()
    print(f"Groupes doublons AVANT              : {duplicate_before}")
    print(f"Groupes doublons APRES              : {duplicate_after}")
    print()
    print(
        f"STATUT FINAL DUPLICATE ENTITY       : "
        f"{'PASS' if final_pass else 'FAIL'}"
    )
    print()
    print(f"Rapport                             : {REPORT_FILE}")
    print()
    print("Aucune donnée clinique n'a été modifiée par ce post-validateur.")


if __name__=="__main__":
    main()
