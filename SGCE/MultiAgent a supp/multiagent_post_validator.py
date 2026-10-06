# -*- coding: utf-8 -*-
"""
multiagent_safe_post_validator.py
=================================

TRACE / SGCE â€” Post-validator for safe RETYPE correction

Compares:
  BEFORE = MultiAgent/agent_d_corrected
  AFTER  = MultiAgent/multiagent_safe_final_corrected

Validates:
- expected document modifications
- every SAFE_ACCEPT operation
- no unexpected modifications
- no missing/extra documents
- TRACE anomaly differential
- zero new structural anomaly

No clinical JSON is modified.
"""

import json
import hashlib
from pathlib import Path


BASE_DIR = Path(
    r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM"
    r"\Reduction_hallucinations"
)

M = BASE_DIR / "MultiAgent"

BEFORE_DIR = (
    M
    / "agent_d_corrected"
)

AFTER_DIR = (
    M
    / "multiagent_safe_final_corrected"
)

CORRECTION_REPORT = (
    AFTER_DIR
    / "multiagent_safe_correction_report.json"
)

GUIDELINE_CANDIDATES = [
    BASE_DIR
    / "Guideline_TRACE_Sepsis_v1.6.json",

    BASE_DIR.parent
    / "Guideline_TRACE_Sepsis_v1.6.json",
]

REPORT_FILE = (
    M
    / "multiagent_safe_post_validation"
    / "multiagent_safe_post_validation_report.json"
)


def load_json(path):
    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


def save_json(path, data):
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
    for path in GUIDELINE_CANDIDATES:
        if path.exists():
            return path

    raise FileNotFoundError(
        "Guideline TRACE-Sepsis introuvable."
    )


def entity_id(entity):
    return (
        entity.get("identifiant_entite")
        or entity.get("id")
        or entity.get("entity_id")
    )


def entity_type(entity):
    return (
        entity.get("categorie")
        or entity.get("type")
        or entity.get("entity_type")
        or ""
    )


def relation_id(relation):
    return (
        relation.get("identifiant_relation")
        or relation.get("id")
        or relation.get("relation_id")
    )


def relation_type(relation):
    return (
        relation.get("type_relation")
        or relation.get("relation")
        or relation.get("relation_type")
        or relation.get("predicate")
        or relation.get("type")
        or ""
    )


def relation_source(relation):
    return (
        relation.get("identifiant_entite_sujet")
        or relation.get("from_id")
        or relation.get("subject_id")
        or relation.get("source")
    )


def relation_target(relation):
    return (
        relation.get("identifiant_entite_objet")
        or relation.get("to_id")
        or relation.get("object_id")
        or relation.get("target")
    )


def get_entities(doc):
    if isinstance(
        doc.get(
            "global_entities"
        ),
        list,
    ):
        return doc[
            "global_entities"
        ]

    out=[]

    for page in (
        doc.get(
            "pages",
            []
        )
        or []
    ):
        out.extend(
            page.get(
                "entities",
                []
            )
            or []
        )

    return out


def get_relations(doc):
    if isinstance(
        doc.get(
            "global_relations"
        ),
        list,
    ):
        return doc[
            "global_relations"
        ]

    out=[]

    for page in (
        doc.get(
            "pages",
            []
        )
        or []
    ):
        out.extend(
            page.get(
                "relations",
                []
            )
            or []
        )

    return out


def find_entity(
    doc,
    target_id,
):
    return next(
        (
            e
            for e in get_entities(
                doc
            )
            if str(
                entity_id(e)
            )
            == str(
                target_id
            )
        ),
        None,
    )


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
        if isinstance(
            locked,
            dict,
        )
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

    out=[]

    for r in get_relations(doc):
        rid=relation_id(r)
        rt=relation_type(r)
        s_id=relation_source(r)
        t_id=relation_target(r)

        s=entities.get(str(s_id))
        t=entities.get(str(t_id))

        if s is None:
            out.append({
                "type":"ORPHAN_SOURCE",
                "relation_id":rid,
                "relation_type":rt,
                "endpoint":s_id,
            })

        if t is None:
            out.append({
                "type":"ORPHAN_TARGET",
                "relation_id":rid,
                "relation_type":rt,
                "endpoint":t_id,
            })

        sig=sigs.get(rt)

        if not sig:
            continue

        if (
            s is not None
            and entity_type(s)
            != sig["domaine"]
        ):
            out.append({
                "type":"INVALID_SOURCE_TYPE",
                "relation_id":rid,
                "relation_type":rt,
                "entity_id":s_id,
                "actual_type":entity_type(s),
                "expected_type":sig["domaine"],
            })

        if (
            t is not None
            and entity_type(t)
            != sig["image"]
        ):
            out.append({
                "type":"INVALID_TARGET_TYPE",
                "relation_id":rid,
                "relation_type":rt,
                "entity_id":t_id,
                "actual_type":entity_type(t),
                "expected_type":sig["image"],
            })

    return out


def anomaly_key(document,a):
    return (
        document,
        a.get("type"),
        str(a.get("relation_id")),
        str(a.get("relation_type")),
        str(a.get("entity_id")),
        str(a.get("endpoint")),
        str(a.get("actual_type")),
        str(a.get("expected_type")),
    )


def clinical_docs(directory):
    docs={}

    for path in directory.glob(
        "*.json"
    ):
        if path.name.endswith(
            "_report.json"
        ):
            continue

        try:
            data=load_json(path)

            if (
                isinstance(data,dict)
                and any(
                    key in data
                    for key in (
                        "pages",
                        "global_entities",
                        "global_relations",
                    )
                )
            ):
                docs[path.name]=data

        except Exception:
            pass

    return docs


def canonical_hash(doc):
    return hashlib.sha256(
        json.dumps(
            doc,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",",":"),
        ).encode("utf-8")
    ).hexdigest()


def main():
    if not BEFORE_DIR.exists():
        raise FileNotFoundError(
            f"Baseline introuvable : {BEFORE_DIR}"
        )

    if not AFTER_DIR.exists():
        raise FileNotFoundError(
            f"Sortie corrigÃ©e introuvable : {AFTER_DIR}"
        )

    if not CORRECTION_REPORT.exists():
        raise FileNotFoundError(
            f"Rapport correcteur introuvable : {CORRECTION_REPORT}"
        )

    before=clinical_docs(
        BEFORE_DIR
    )

    after=clinical_docs(
        AFTER_DIR
    )

    correction=load_json(
        CORRECTION_REPORT
    )

    sigs=signatures()

    before_names=set(before)
    after_names=set(after)

    common=sorted(
        before_names
        & after_names
    )

    missing=sorted(
        before_names
        - after_names
    )

    extra=sorted(
        after_names
        - before_names
    )

    expected=set(
        correction.get(
            "modified_documents",
            []
        )
    )

    actual={
        name
        for name in common
        if canonical_hash(
            before[name]
        )
        != canonical_hash(
            after[name]
        )
    }

    unexpected=sorted(
        actual
        - expected
    )

    absent=sorted(
        expected
        - actual
    )

    applied=[
        op
        for op in correction.get(
            "operations",
            []
        )
        if op.get(
            "status"
        )
        == "APPLIED"
    ]

    op_results=[]

    op_pass=0
    op_fail=0

    for op in applied:
        doc=after.get(
            op.get(
                "document"
            )
        )

        entity=(
            find_entity(
                doc,
                op.get(
                    "entity_id"
                ),
            )
            if doc
            else None
        )

        passed=(
            entity is not None
            and entity_type(
                entity
            )
            == op.get(
                "new_type"
            )
        )

        if passed:
            op_pass+=1
            status="PASS"
            reason="RETYPE_CONFIRMED"
        else:
            op_fail+=1
            status="FAIL"
            reason="RETYPE_POSTCONDITION_FAILED"

        op_results.append({
            "document":op.get("document"),
            "entity_id":op.get("entity_id"),
            "new_type":op.get("new_type"),
            "status":status,
            "reason":reason,
        })

    before_anomalies=[]
    after_anomalies=[]

    for document,doc in before.items():
        for a in audit(doc,sigs):
            before_anomalies.append(
                (document,a)
            )

    for document,doc in after.items():
        for a in audit(doc,sigs):
            after_anomalies.append(
                (document,a)
            )

    bmap={
        anomaly_key(d,a):{
            "document":d,
            **a,
        }
        for d,a in before_anomalies
    }

    amap={
        anomaly_key(d,a):{
            "document":d,
            **a,
        }
        for d,a in after_anomalies
    }

    new_keys=set(amap)-set(bmap)
    resolved_keys=set(bmap)-set(amap)

    new_anomalies=[
        amap[k]
        for k in sorted(new_keys)
    ]

    resolved_anomalies=[
        bmap[k]
        for k in sorted(resolved_keys)
    ]

    final_pass=(
        not missing
        and not extra
        and not unexpected
        and not absent
        and op_fail==0
        and len(new_anomalies)==0
    )

    report={
        "validator":"multiagent_safe_post_validator",
        "status":"PASS" if final_pass else "FAIL",
        "before_directory":str(BEFORE_DIR),
        "after_directory":str(AFTER_DIR),

        "summary":{
            "documents_checked":len(common),
            "expected_modified_documents":len(expected),
            "actually_modified_documents":len(actual),
            "unexpected_modifications":len(unexpected),
            "missing_expected_corrections":len(absent),
            "operations_checked":len(applied),
            "operations_pass":op_pass,
            "operations_fail":op_fail,
            "anomalies_before":len(before_anomalies),
            "anomalies_after":len(after_anomalies),
            "new_anomalies":len(new_anomalies),
            "resolved_anomalies":len(resolved_anomalies),
            "missing_documents_after":len(missing),
            "extra_documents_after":len(extra),
            "trace_signatures_loaded":len(sigs),
        },

        "new_anomalies":new_anomalies,
        "resolved_anomalies":resolved_anomalies,
        "operation_results":op_results,
    }

    save_json(
        REPORT_FILE,
        report,
    )

    print("="*108)
    print("TRACE / SGCE - SAFE FINAL POST-VALIDATION")
    print("="*108)

    print(
        f"AVANT                               : {BEFORE_DIR}"
    )

    print(
        f"APRES                               : {AFTER_DIR}"
    )

    print()

    print(
        f"Documents vÃ©rifiÃ©s                  : {len(common)}"
    )

    print(
        f"Documents attendus modifiÃ©s         : {len(expected)}"
    )

    print(
        f"Documents rÃ©ellement modifiÃ©s       : {len(actual)}"
    )

    print(
        f"Modifications inattendues           : {len(unexpected)}"
    )

    print(
        f"Corrections attendues absentes      : {len(absent)}"
    )

    print()

    print(
        f"OpÃ©rations vÃ©rifiÃ©es                : {len(applied)}"
    )

    print(
        f"OpÃ©rations PASS                     : {op_pass}"
    )

    print(
        f"OpÃ©rations FAIL                     : {op_fail}"
    )

    print()

    print(
        f"Anomalies AVANT                     : {len(before_anomalies)}"
    )

    print(
        f"Anomalies APRES                     : {len(after_anomalies)}"
    )

    print(
        f"Nouvelles anomalies                 : {len(new_anomalies)}"
    )

    print(
        f"Anomalies rÃ©solues                  : {len(resolved_anomalies)}"
    )

    print()

    print(
        f"Docs manquants APRES                : {len(missing)}"
    )

    print(
        f"Docs supplÃ©mentaires APRES          : {len(extra)}"
    )

    print()

    print(
        f"STATUT FINAL SAFE MULTI-AGENT       : "
        f"{'PASS' if final_pass else 'FAIL'}"
    )

    print()

    print(
        f"Rapport                             : {REPORT_FILE}"
    )

    print()

    print(
        "Aucune donnÃ©e clinique n'a Ã©tÃ© modifiÃ©e "
        "par ce post-validateur."
    )


if __name__=="__main__":
    main()

