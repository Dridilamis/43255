# -*- coding: utf-8 -*-
"""
pattern_a5_differential_post_validator.py
=========================================

SGCE — Pattern A5 Differential Post-Validator

Compare:
- BEFORE A5 : PatternA4/pattern_a4_corrected
- AFTER A5  : PatternA5/pattern_a5_corrected

Checks:
1) Every expected LINK exists after correction.
2) Source is IMAGERIE_PROCEDURE.
3) Target is COMORBIDITE_ANTECEDENT.
4) Relation type is imagerie_objective_comorbidite.
5) No new duplicate IDs.
6) No new orphan endpoints.
7) Pre-existing anomalies are distinguished from anomalies introduced by A5.

Pre-existing anomalies do not fail A5.
Only anomalies introduced by A5 are critical.
"""

import json
from collections import Counter, defaultdict
from pathlib import Path


# ============================================================
# 1. PATHS
# ============================================================

PATTERN_A5_DIR = Path(__file__).resolve().parent
PATTERN_A_DIR = PATTERN_A5_DIR.parent
PATTERNS_DIR = PATTERN_A_DIR.parent
SGCE_DIR = PATTERNS_DIR.parent
BASE_DIR = SGCE_DIR.parent
PATTERN_A4_DIR = PATTERN_A_DIR / "PatternA4"

BEFORE_DIR_CANDIDATES = [
    PATTERN_A4_DIR / "corrected",
]

AFTER_DIR = PATTERN_A5_DIR / "corrected"
CORRECTION_REPORT = AFTER_DIR / "pattern_a5_correction_report.json"

OUTPUT_DIR = PATTERN_A5_DIR / "post_validation"
OUTPUT_JSON = OUTPUT_DIR / "pattern_a5_post_validation_report.json"

SOURCE_TYPE = "IMAGERIE_PROCEDURE"
TARGET_TYPE = "COMORBIDITE_ANTECEDENT"
RELATION_TYPE = "imagerie_objective_comorbidite"


# ============================================================
# 2. HELPERS
# ============================================================

def resolve_before_dir():
    for p in BEFORE_DIR_CANDIDATES:
        if p.exists() and any(p.glob("*.json")):
            return p
    raise FileNotFoundError("Dossier AVANT A5 introuvable.")


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def entity_id(e):
    return e.get("identifiant_entite") or e.get("id") or e.get("entity_id")


def entity_type(e):
    return e.get("categorie") or e.get("type") or ""


def relation_id(r):
    return (
        r.get("identifiant_relation")
        or r.get("id")
        or r.get("relation_id")
    )


def relation_type(r):
    return r.get("type_relation") or r.get("relation") or r.get("type") or ""


def relation_source(r):
    return (
        r.get("identifiant_entite_sujet")
        or r.get("from_id")
        or r.get("subject_id")
    )


def relation_target(r):
    return (
        r.get("identifiant_entite_objet")
        or r.get("to_id")
        or r.get("object_id")
    )


def get_entities(doc):
    if isinstance(doc.get("global_entities"), list):
        return doc["global_entities"]

    out = []
    for page in doc.get("pages", []) or []:
        out.extend(page.get("entities", []) or [])
    return out


def get_relations(doc):
    if isinstance(doc.get("global_relations"), list):
        return doc["global_relations"]

    out = []
    for page in doc.get("pages", []) or []:
        out.extend(page.get("relations", []) or [])
    return out


def is_clinical_document(doc):
    return (
        isinstance(doc, dict)
        and (
            isinstance(doc.get("global_entities"), list)
            or isinstance(doc.get("pages"), list)
        )
    )


# ============================================================
# 3. ANOMALY COLLECTION
# ============================================================

def collect_structural_anomalies(doc):
    entities = get_entities(doc)
    relations = get_relations(doc)

    anomalies = []

    entity_ids = [entity_id(e) for e in entities if entity_id(e)]
    relation_ids = [relation_id(r) for r in relations if relation_id(r)]

    ec = Counter(entity_ids)
    rc = Counter(relation_ids)

    for eid, count in ec.items():
        if count > 1:
            anomalies.append(("DUPLICATE_ENTITY_ID", str(eid), count))

    for rid, count in rc.items():
        if count > 1:
            anomalies.append(("DUPLICATE_RELATION_ID", str(rid), count))

    entity_map = {
        entity_id(e): e
        for e in entities
        if entity_id(e)
    }

    for r in relations:
        rid = relation_id(r)
        src = relation_source(r)
        tgt = relation_target(r)

        if src and src not in entity_map:
            anomalies.append(("ORPHAN_SOURCE", str(rid), str(src)))

        if tgt and tgt not in entity_map:
            anomalies.append(("ORPHAN_TARGET", str(rid), str(tgt)))

        if relation_type(r) == RELATION_TYPE:
            src_ent = entity_map.get(src)
            tgt_ent = entity_map.get(tgt)

            if src_ent is not None and entity_type(src_ent) != SOURCE_TYPE:
                anomalies.append(
                    ("INVALID_A5_SOURCE_TYPE", str(rid), entity_type(src_ent))
                )

            if tgt_ent is not None and entity_type(tgt_ent) != TARGET_TYPE:
                anomalies.append(
                    ("INVALID_A5_TARGET_TYPE", str(rid), entity_type(tgt_ent))
                )

    return set(anomalies)


# ============================================================
# 4. OPERATION VALIDATION
# ============================================================

def validate_operation(doc, op):
    entities = get_entities(doc)
    relations = get_relations(doc)

    entity_map = {
        entity_id(e): e
        for e in entities
        if entity_id(e)
    }

    operation = op.get("operation")
    src_id = op.get("source_entity_id")
    tgt_id = op.get("target_entity_id")
    rid = op.get("relation_id")

    result = {
        "document": op.get("document"),
        "operation": operation,
        "source_entity_id": src_id,
        "target_entity_id": tgt_id,
        "relation_id": rid,
        "checks": [],
        "passed": False,
    }

    src = entity_map.get(src_id)
    tgt = entity_map.get(tgt_id)

    source_ok = src is not None and entity_type(src) == SOURCE_TYPE
    target_ok = tgt is not None and entity_type(tgt) == TARGET_TYPE

    rel = next(
        (
            r for r in relations
            if (
                relation_type(r) == RELATION_TYPE
                and relation_source(r) == src_id
                and relation_target(r) == tgt_id
            )
        ),
        None,
    )

    relation_ok = rel is not None

    result["checks"].append({
        "check": "SOURCE_EXISTS_AND_TYPED",
        "passed": source_ok,
    })

    result["checks"].append({
        "check": "TARGET_EXISTS_AND_TYPED",
        "passed": target_ok,
    })

    result["checks"].append({
        "check": "EXPECTED_A5_RELATION_EXISTS",
        "passed": relation_ok,
    })

    if rid:
        rid_ok = any(
            relation_id(r) == rid
            and relation_type(r) == RELATION_TYPE
            and relation_source(r) == src_id
            and relation_target(r) == tgt_id
            for r in relations
        )

        result["checks"].append({
            "check": "EXPECTED_RELATION_ID_EXISTS",
            "passed": rid_ok,
        })
    else:
        rid_ok = relation_ok

    if operation == "LINK":
        result["passed"] = (
            source_ok
            and target_ok
            and relation_ok
            and rid_ok
        )
    else:
        result["passed"] = True

    return result


# ============================================================
# 5. MAIN
# ============================================================

def main():
    before_dir = resolve_before_dir()

    if not AFTER_DIR.exists():
        raise FileNotFoundError(
            f"Dossier APRES A5 introuvable : {AFTER_DIR}"
        )

    if not CORRECTION_REPORT.exists():
        raise FileNotFoundError(
            f"Rapport correction A5 introuvable : {CORRECTION_REPORT}"
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    correction_report = load_json(CORRECTION_REPORT)

    expected_operations = [
        op
        for op in correction_report.get("operations", [])
        if op.get("modified") is True
    ]

    operations_by_doc = defaultdict(list)

    for op in expected_operations:
        operations_by_doc[op.get("document")].append(op)

    before_docs = {}
    after_docs = {}

    for path in before_dir.glob("*.json"):
        try:
            doc = load_json(path)
            if is_clinical_document(doc):
                before_docs[path.name] = doc
        except Exception:
            pass

    for path in AFTER_DIR.glob("*.json"):
        if path.name == CORRECTION_REPORT.name:
            continue

        try:
            doc = load_json(path)
            if is_clinical_document(doc):
                after_docs[path.name] = doc
        except Exception:
            pass

    all_names = sorted(set(before_docs) | set(after_docs))

    document_results = []
    operation_results = []

    total_preexisting = 0
    total_introduced = 0
    total_resolved = 0

    missing_before = []
    missing_after = []

    for name in all_names:
        before = before_docs.get(name)
        after = after_docs.get(name)

        if before is None:
            missing_before.append(name)
            continue

        if after is None:
            missing_after.append(name)
            continue

        before_anoms = collect_structural_anomalies(before)
        after_anoms = collect_structural_anomalies(after)

        preexisting = before_anoms & after_anoms
        introduced = after_anoms - before_anoms
        resolved = before_anoms - after_anoms

        total_preexisting += len(preexisting)
        total_introduced += len(introduced)
        total_resolved += len(resolved)

        doc_ops = operations_by_doc.get(name, [])
        doc_op_results = []

        for op in doc_ops:
            res = validate_operation(after, op)
            operation_results.append(res)
            doc_op_results.append(res)

        operations_pass = all(
            r["passed"]
            for r in doc_op_results
        )

        status = (
            "PASS"
            if operations_pass and len(introduced) == 0
            else "FAIL"
        )

        document_results.append({
            "document": name,
            "expected_operations": len(doc_ops),
            "preexisting_anomalies": len(preexisting),
            "introduced_by_a5": len(introduced),
            "resolved_by_a5": len(resolved),
            "introduced_anomalies": [
                list(x)
                for x in sorted(introduced, key=str)
            ],
            "status": status,
        })

    pass_docs = sum(
        1 for d in document_results
        if d["status"] == "PASS"
    )

    fail_docs = len(document_results) - pass_docs

    passed_ops = sum(
        1 for r in operation_results
        if r["passed"]
    )

    failed_ops = len(operation_results) - passed_ops

    link_results = [
        r for r in operation_results
        if r["operation"] == "LINK"
    ]

    final_pass = (
        fail_docs == 0
        and failed_ops == 0
        and total_introduced == 0
        and not missing_before
        and not missing_after
    )

    report = {
        "pattern": "A5",
        "validation_type": "DIFFERENTIAL_POST_VALIDATION",
        "before_directory": str(before_dir),
        "after_directory": str(AFTER_DIR),
        "correction_report": str(CORRECTION_REPORT),

        "summary": {
            "documents_verified": len(document_results),
            "documents_pass": pass_docs,
            "documents_fail": fail_docs,

            "expected_operations": len(expected_operations),
            "operations_pass": passed_ops,
            "operations_fail": failed_ops,

            "link_expected": len(link_results),
            "link_pass": sum(
                1 for r in link_results
                if r["passed"]
            ),

            "preexisting_anomalies": total_preexisting,
            "introduced_by_a5": total_introduced,
            "resolved_by_a5": total_resolved,

            "missing_before_documents": len(missing_before),
            "missing_after_documents": len(missing_after),

            "final_status": "PASS" if final_pass else "FAIL",
        },

        "operation_results": operation_results,
        "documents": document_results,
        "missing_before_documents": missing_before,
        "missing_after_documents": missing_after,
    }

    OUTPUT_JSON.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=" * 76)
    print("SGCE - PATTERN A5 DIFFERENTIAL POST-VALIDATION")
    print("=" * 76)
    print(f"AVANT A5                : {before_dir}")
    print(f"APRES A5                : {AFTER_DIR}")
    print()
    print(f"Documents vérifiés      : {len(document_results)}")
    print(f"PASS                    : {pass_docs}")
    print(f"FAIL                    : {fail_docs}")
    print()
    print(f"Opérations attendues    : {len(expected_operations)}")
    print(f"Opérations PASS         : {passed_ops}")
    print(f"Opérations FAIL         : {failed_ops}")
    print()
    print(
        f"LINK                    : "
        f"{sum(1 for r in link_results if r['passed'])}/{len(link_results)}"
    )
    print()
    print(f"Anomalies pré-existantes: {total_preexisting}")
    print(f"Nouvelles anomalies A5  : {total_introduced}")
    print(f"Anomalies résolues A5   : {total_resolved}")
    print()
    print(f"Docs manquants APRES    : {len(missing_after)}")
    print(f"Docs manquants AVANT    : {len(missing_before)}")
    print()
    print(
        f"STATUT FINAL A5         : "
        f"{'PASS' if final_pass else 'FAIL'}"
    )
    print()
    print(f"Rapport                 : {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
