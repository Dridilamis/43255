# -*- coding: utf-8 -*-
"""
pattern_a2_differential_post_validator.py
=========================================

SGCE — Pattern A2 Differential Post-Validator

Objectif
--------
Comparer automatiquement :
- AVANT A2 : PatternA1/pattern_a1_corrected
- APRES A2 : PatternA2/pattern_a2_corrected

Vérifications principales
-------------------------
1) Les opérations LINK attendues existent bien après correction.
2) Les opérations SPLIT attendues ont bien créé :
   - un CONTEXTE_ACQUISITION,
   - la relation a_pour_contexte_acquisition.
3) Les endpoints des relations existent.
4) La signature TRACE-Sepsis v1.6 est respectée :
   COMORBIDITE_ANTECEDENT -> CONTEXTE_ACQUISITION.
5) Aucun nouvel ID dupliqué critique n'est introduit.
6) Aucun nouvel endpoint orphelin n'est introduit.
7) Les anomalies déjà présentes avant A2 sont distinguées
   des anomalies introduites par A2.

Important
---------
Le validator est DIFFERENTIEL :
une anomalie déjà présente avant A2 ne fait pas échouer A2.
Seules les nouvelles anomalies introduites par A2 sont critiques.
"""

import json
from collections import Counter, defaultdict
from pathlib import Path


# ============================================================
# 1. PATHS
# ============================================================

PATTERN_A2_DIR = Path(__file__).resolve().parent
PATTERN_A_DIR = PATTERN_A2_DIR.parent
PATTERNS_DIR = PATTERN_A_DIR.parent
SGCE_DIR = PATTERNS_DIR.parent
BASE_DIR = SGCE_DIR.parent
PATTERN_A1_DIR = PATTERN_A_DIR / "PatternA1"

BEFORE_DIR_CANDIDATES = [PATTERN_A1_DIR / "corrected"]
AFTER_DIR = PATTERN_A2_DIR / "corrected"
CORRECTION_REPORT = AFTER_DIR / "pattern_a2_correction_report.json"
OUTPUT_DIR = PATTERN_A2_DIR / "post_validation"
OUTPUT_JSON = OUTPUT_DIR / "pattern_a2_post_validation_report.json"

SOURCE_TYPE = "COMORBIDITE_ANTECEDENT"
TARGET_TYPE = "CONTEXTE_ACQUISITION"
RELATION_TYPE = "a_pour_contexte_acquisition"


# ============================================================
# 2. HELPERS
# ============================================================

def resolve_before_dir():
    for p in BEFORE_DIR_CANDIDATES:
        if p.exists() and any(p.glob("*.json")):
            return p
    raise FileNotFoundError("Dossier AVANT A2 introuvable.")


def entity_id(e):
    return (
        e.get("identifiant_entite")
        or e.get("id")
        or e.get("entity_id")
    )


def entity_type(e):
    return e.get("categorie") or e.get("type") or ""


def relation_id(r):
    return (
        r.get("identifiant_relation")
        or r.get("id")
        or r.get("relation_id")
    )


def relation_type(r):
    return (
        r.get("type_relation")
        or r.get("relation")
        or r.get("type")
        or ""
    )


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

    result = []
    for p in doc.get("pages", []) or []:
        result.extend(p.get("entities", []) or [])
    return result


def get_relations(doc):
    if isinstance(doc.get("global_relations"), list):
        return doc["global_relations"]

    result = []
    for p in doc.get("pages", []) or []:
        result.extend(p.get("relations", []) or [])
    return result


def is_clinical_document(doc):
    return (
        isinstance(doc, dict)
        and (
            isinstance(doc.get("global_entities"), list)
            or isinstance(doc.get("pages"), list)
        )
    )


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# 3. STRUCTURAL ANOMALIES
# ============================================================

def collect_structural_anomalies(doc):
    entities = get_entities(doc)
    relations = get_relations(doc)

    anomalies = []

    entity_ids = [entity_id(e) for e in entities if entity_id(e)]
    relation_ids = [relation_id(r) for r in relations if relation_id(r)]

    entity_counter = Counter(entity_ids)
    relation_counter = Counter(relation_ids)

    # Duplicate entity IDs
    for eid, count in entity_counter.items():
        if count > 1:
            anomalies.append(
                ("DUPLICATE_ENTITY_ID", str(eid), count)
            )

    # Duplicate relation IDs
    for rid, count in relation_counter.items():
        if count > 1:
            anomalies.append(
                ("DUPLICATE_RELATION_ID", str(rid), count)
            )

    entity_map = {
        entity_id(e): e
        for e in entities
        if entity_id(e)
    }

    # Orphan relation endpoints
    for r in relations:
        rid = relation_id(r)
        src = relation_source(r)
        tgt = relation_target(r)

        if src and src not in entity_map:
            anomalies.append(
                ("ORPHAN_SOURCE", str(rid), str(src))
            )

        if tgt and tgt not in entity_map:
            anomalies.append(
                ("ORPHAN_TARGET", str(rid), str(tgt))
            )

        # Signature A2 strict check
        if relation_type(r) == RELATION_TYPE:
            src_ent = entity_map.get(src)
            tgt_ent = entity_map.get(tgt)

            if src_ent is not None and entity_type(src_ent) != SOURCE_TYPE:
                anomalies.append(
                    (
                        "INVALID_A2_SOURCE_TYPE",
                        str(rid),
                        entity_type(src_ent),
                    )
                )

            if tgt_ent is not None and entity_type(tgt_ent) != TARGET_TYPE:
                anomalies.append(
                    (
                        "INVALID_A2_TARGET_TYPE",
                        str(rid),
                        entity_type(tgt_ent),
                    )
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

    result = {
        "document": op.get("document"),
        "operation": op.get("operation"),
        "source_entity_id": op.get("source_entity_id"),
        "passed": False,
        "checks": [],
    }

    operation = op.get("operation")
    src_id = op.get("source_entity_id")

    src = entity_map.get(src_id)

    # Source must still exist and remain COMORBIDITE_ANTECEDENT
    source_ok = (
        src is not None
        and entity_type(src) == SOURCE_TYPE
    )

    result["checks"].append({
        "check": "SOURCE_PRESERVED_AND_TYPED",
        "passed": source_ok,
    })

    if not source_ok:
        return result

    # --------------------------------------------------------
    # LINK
    # --------------------------------------------------------
    if operation == "LINK":
        tgt_id = op.get("target_entity_id")
        tgt = entity_map.get(tgt_id)

        target_ok = (
            tgt is not None
            and entity_type(tgt) == TARGET_TYPE
        )

        rel_ok = any(
            relation_type(r) == RELATION_TYPE
            and relation_source(r) == src_id
            and relation_target(r) == tgt_id
            for r in relations
        )

        result["checks"].extend([
            {
                "check": "TARGET_CONTEXT_EXISTS",
                "passed": target_ok,
            },
            {
                "check": "EXPECTED_A2_RELATION_EXISTS",
                "passed": rel_ok,
            },
        ])

        result["passed"] = (
            source_ok
            and target_ok
            and rel_ok
        )

    # --------------------------------------------------------
    # SPLIT
    # --------------------------------------------------------
    elif operation == "SPLIT":
        tgt_id = op.get("created_target_entity_id")
        tgt = entity_map.get(tgt_id)

        target_ok = (
            tgt is not None
            and entity_type(tgt) == TARGET_TYPE
        )

        sgce_ok = bool(
            tgt
            and tgt.get("_sgce_created") is True
            and tgt.get("_sgce_subcase")
            == "A2_COMORBIDITE_CONTEXTE_ACQUISITION"
        )

        rel_ok = any(
            relation_type(r) == RELATION_TYPE
            and relation_source(r) == src_id
            and relation_target(r) == tgt_id
            for r in relations
        )

        surface = (
            tgt.get("valeur")
            if tgt is not None
            else None
        )

        surface_ok = bool(
            surface
            and str(surface).strip()
        )

        result["checks"].extend([
            {
                "check": "CREATED_CONTEXT_EXISTS",
                "passed": target_ok,
            },
            {
                "check": "SGCE_PROVENANCE_PRESENT",
                "passed": sgce_ok,
            },
            {
                "check": "CONTEXT_SURFACE_NON_EMPTY",
                "passed": surface_ok,
            },
            {
                "check": "EXPECTED_A2_RELATION_EXISTS",
                "passed": rel_ok,
            },
        ])

        result["passed"] = (
            source_ok
            and target_ok
            and sgce_ok
            and surface_ok
            and rel_ok
        )

    else:
        # SKIP operations are not expected in this run.
        result["passed"] = True
        result["checks"].append({
            "check": "NO_MODIFICATION_REQUIRED",
            "passed": True,
        })

    return result


# ============================================================
# 5. MAIN
# ============================================================

def main():
    before_dir = resolve_before_dir()

    if not AFTER_DIR.exists():
        raise FileNotFoundError(
            f"Dossier APRES A2 introuvable : {AFTER_DIR}"
        )

    if not CORRECTION_REPORT.exists():
        raise FileNotFoundError(
            f"Rapport correction A2 introuvable : {CORRECTION_REPORT}"
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    correction_report = load_json(
        CORRECTION_REPORT
    )

    expected_operations = [
        op
        for op in correction_report.get("operations", [])
        if op.get("modified") is True
    ]

    operations_by_doc = defaultdict(list)

    for op in expected_operations:
        operations_by_doc[
            op.get("document")
        ].append(op)

    before_files = {}

    for path in before_dir.glob("*.json"):
        try:
            doc = load_json(path)
            if is_clinical_document(doc):
                before_files[path.name] = doc
        except Exception:
            pass

    after_files = {}

    for path in AFTER_DIR.glob("*.json"):
        if path.name == CORRECTION_REPORT.name:
            continue

        try:
            doc = load_json(path)
            if is_clinical_document(doc):
                after_files[path.name] = doc
        except Exception:
            pass

    all_names = sorted(
        set(before_files) | set(after_files)
    )

    document_results = []
    operation_results = []

    global_preexisting = 0
    global_introduced = 0
    global_resolved = 0

    missing_after_docs = []
    missing_before_docs = []

    for name in all_names:
        before = before_files.get(name)
        after = after_files.get(name)

        if before is None:
            missing_before_docs.append(name)
            continue

        if after is None:
            missing_after_docs.append(name)
            continue

        before_anoms = collect_structural_anomalies(
            before
        )
        after_anoms = collect_structural_anomalies(
            after
        )

        preexisting = after_anoms & before_anoms
        introduced = after_anoms - before_anoms
        resolved = before_anoms - after_anoms

        global_preexisting += len(preexisting)
        global_introduced += len(introduced)
        global_resolved += len(resolved)

        doc_ops = operations_by_doc.get(
            name,
            [],
        )

        doc_op_results = []

        for op in doc_ops:
            op_result = validate_operation(
                after,
                op,
            )

            operation_results.append(
                op_result
            )
            doc_op_results.append(
                op_result
            )

        operations_pass = all(
            r["passed"]
            for r in doc_op_results
        )

        no_new_critical = (
            len(introduced) == 0
        )

        document_pass = (
            operations_pass
            and no_new_critical
        )

        document_results.append({
            "document": name,
            "expected_operations": len(doc_ops),
            "operation_checks_passed": operations_pass,
            "preexisting_anomalies": len(preexisting),
            "introduced_by_a2": len(introduced),
            "resolved_by_a2": len(resolved),
            "introduced_anomalies": [
                list(x)
                for x in sorted(
                    introduced,
                    key=str,
                )
            ],
            "status": (
                "PASS"
                if document_pass
                else "FAIL"
            ),
        })

    passed_ops = sum(
        1
        for r in operation_results
        if r["passed"]
    )

    failed_ops = (
        len(operation_results)
        - passed_ops
    )

    link_results = [
        r for r in operation_results
        if r["operation"] == "LINK"
    ]

    split_results = [
        r for r in operation_results
        if r["operation"] == "SPLIT"
    ]

    pass_docs = sum(
        1
        for d in document_results
        if d["status"] == "PASS"
    )

    fail_docs = (
        len(document_results)
        - pass_docs
    )

    final_pass = (
        fail_docs == 0
        and failed_ops == 0
        and global_introduced == 0
        and not missing_after_docs
        and not missing_before_docs
    )

    report = {
        "pattern": "A2",
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
                1 for r in link_results if r["passed"]
            ),

            "split_expected": len(split_results),
            "split_pass": sum(
                1 for r in split_results if r["passed"]
            ),

            "preexisting_anomalies": global_preexisting,
            "introduced_by_a2": global_introduced,
            "resolved_by_a2": global_resolved,

            "missing_before_documents": len(missing_before_docs),
            "missing_after_documents": len(missing_after_docs),

            "final_status": (
                "PASS"
                if final_pass
                else "FAIL"
            ),
        },

        "operation_results": operation_results,
        "documents": document_results,
        "missing_before_documents": missing_before_docs,
        "missing_after_documents": missing_after_docs,
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
    print("SGCE - PATTERN A2 DIFFERENTIAL POST-VALIDATION")
    print("=" * 76)
    print(f"AVANT A2                : {before_dir}")
    print(f"APRES A2                : {AFTER_DIR}")
    print()
    print(f"Documents vérifiés      : {len(document_results)}")
    print(f"PASS                    : {pass_docs}")
    print(f"FAIL                    : {fail_docs}")
    print()
    print(f"Opérations attendues    : {len(expected_operations)}")
    print(f"Opérations PASS         : {passed_ops}")
    print(f"Opérations FAIL         : {failed_ops}")
    print()
    print(f"LINK                    : {sum(1 for r in link_results if r['passed'])}/{len(link_results)}")
    print(f"SPLIT                   : {sum(1 for r in split_results if r['passed'])}/{len(split_results)}")
    print()
    print(f"Anomalies pré-existantes: {global_preexisting}")
    print(f"Nouvelles anomalies A2  : {global_introduced}")
    print(f"Anomalies résolues A2   : {global_resolved}")
    print()
    print(f"Docs manquants APRES    : {len(missing_after_docs)}")
    print(f"Docs manquants AVANT    : {len(missing_before_docs)}")
    print()
    print(f"STATUT FINAL A2         : {'PASS' if final_pass else 'FAIL'}")
    print()
    print(f"Rapport                 : {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
