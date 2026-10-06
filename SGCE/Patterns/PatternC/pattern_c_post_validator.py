# -*- coding: utf-8 -*-
"""
pattern_c_post_validator.py
===========================

SGCE — Pattern C Differential Post-Validator

Compare:
- BEFORE C : PatternB/PatternB2/pattern_b2_corrected
- AFTER C  : PatternC/pattern_c_corrected

Checks:
1) Same clinical documents before/after.
2) No unexpected clinical modifications.
3) If Pattern C corrections exist on another dataset:
   - removed reified entity is absent
   - created relation exists exactly
4) No new duplicate entity IDs.
5) No new duplicate relation IDs.
6) No new orphan relation endpoints.
7) No new invalid TRACE-Sepsis domain/image signatures.
8) Pre-existing anomalies do NOT fail Pattern C.
9) Only anomalies introduced by Pattern C are critical.

This validator does NOT modify clinical JSONs.
"""

import csv
import json
from collections import Counter
from pathlib import Path


# ============================================================
# 1. PATHS
# ============================================================

PATTERN_C_DIR = Path(__file__).resolve().parent
PATTERNS_DIR = PATTERN_C_DIR.parent
SGCE_DIR = PATTERNS_DIR.parent
BASE_DIR = SGCE_DIR.parent

PATTERN_B2_DIR = PATTERNS_DIR / "PatternB" / "PatternB2"

BEFORE_DIR = PATTERN_B2_DIR / "corrected"
AFTER_DIR = PATTERN_C_DIR / "corrected"
CORRECTION_REPORT = AFTER_DIR / "pattern_c_correction_report.json"

GUIDELINE_CANDIDATES = [
    BASE_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
    BASE_DIR.parent / "Guideline_TRACE_Sepsis_v1.6.json",
    Path.cwd() / "Guideline_TRACE_Sepsis_v1.6.json",
    PATTERN_C_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
]

OUTPUT_DIR = PATTERN_C_DIR / "post_validation"
OUTPUT_JSON = OUTPUT_DIR / "pattern_c_post_validation_report.json"
OUTPUT_CSV = OUTPUT_DIR / "pattern_c_post_validation_documents.csv"
ANOMALIES_CSV = OUTPUT_DIR / "pattern_c_new_anomalies.csv"

# ============================================================
# 2. HELPERS
# ============================================================

def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def is_clinical_document(doc):
    return (
        isinstance(doc, dict)
        and (
            isinstance(doc.get("global_entities"), list)
            or isinstance(doc.get("pages"), list)
        )
    )


def entity_id(e):
    return (
        e.get("identifiant_entite")
        or e.get("id")
        or e.get("entity_id")
    )


def entity_type(e):
    return (
        e.get("categorie")
        or e.get("type")
        or ""
    )


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

    out = []

    for page in doc.get("pages", []) or []:
        out.extend(
            page.get("entities", []) or []
        )

    return out


def get_relations(doc):
    if isinstance(doc.get("global_relations"), list):
        return doc["global_relations"]

    out = []

    for page in doc.get("pages", []) or []:
        out.extend(
            page.get("relations", []) or []
        )

    return out


def clinical_signature(doc):
    return json.dumps(
        doc,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


# ============================================================
# 3. GUIDELINE SIGNATURES
# ============================================================

def resolve_guideline():
    for path in GUIDELINE_CANDIDATES:
        if path.exists():
            return path
    return None


def get_locked_signatures(guideline):
    if guideline is None:
        return {}

    root = guideline.get(
        "ontologie_sepsis_graph",
        guideline,
    )

    locked = root.get(
        "signatures_relations_verrouillees_v1_5",
        {},
    )

    signatures = {}

    if isinstance(locked, dict):
        for rtype, spec in locked.items():
            if not isinstance(spec, dict):
                continue

            domain = spec.get("domaine")
            image = spec.get("image")

            if domain and image:
                signatures[rtype] = {
                    "domaine": domain,
                    "image": image,
                }

    return signatures


# ============================================================
# 4. STRUCTURAL ANOMALIES
# ============================================================

def collect_structural_anomalies(doc, signatures):
    entities = get_entities(doc)
    relations = get_relations(doc)

    anomalies = []

    entity_ids = [
        entity_id(e)
        for e in entities
        if entity_id(e)
    ]

    relation_ids = [
        relation_id(r)
        for r in relations
        if relation_id(r)
    ]

    entity_counts = Counter(entity_ids)
    relation_counts = Counter(relation_ids)

    # Duplicate IDs
    for eid, count in entity_counts.items():
        if count > 1:
            anomalies.append(
                (
                    "DUPLICATE_ENTITY_ID",
                    str(eid),
                    str(count),
                )
            )

    for rid, count in relation_counts.items():
        if count > 1:
            anomalies.append(
                (
                    "DUPLICATE_RELATION_ID",
                    str(rid),
                    str(count),
                )
            )

    entity_map = {
        entity_id(e): e
        for e in entities
        if entity_id(e)
    }

    # Relations
    for r in relations:
        rid = relation_id(r)
        rtype = relation_type(r)
        src = relation_source(r)
        tgt = relation_target(r)

        if src and src not in entity_map:
            anomalies.append(
                (
                    "ORPHAN_RELATION_SOURCE",
                    str(rid),
                    str(src),
                )
            )

        if tgt and tgt not in entity_map:
            anomalies.append(
                (
                    "ORPHAN_RELATION_TARGET",
                    str(rid),
                    str(tgt),
                )
            )

        if (
            signatures
            and rtype in signatures
            and src in entity_map
            and tgt in entity_map
        ):
            expected = signatures[rtype]

            src_type = entity_type(
                entity_map[src]
            )

            tgt_type = entity_type(
                entity_map[tgt]
            )

            if src_type != expected["domaine"]:
                anomalies.append(
                    (
                        "INVALID_RELATION_SOURCE_TYPE",
                        str(rid),
                        (
                            f"{rtype}: "
                            f"{src_type} != "
                            f"{expected['domaine']}"
                        ),
                    )
                )

            if tgt_type != expected["image"]:
                anomalies.append(
                    (
                        "INVALID_RELATION_TARGET_TYPE",
                        str(rid),
                        (
                            f"{rtype}: "
                            f"{tgt_type} != "
                            f"{expected['image']}"
                        ),
                    )
                )

        elif (
            signatures
            and rtype
            and rtype not in signatures
        ):
            anomalies.append(
                (
                    "UNAUTHORIZED_RELATION_TYPE",
                    str(rid),
                    str(rtype),
                )
            )

    return set(anomalies)


# ============================================================
# 5. LOAD DOCUMENTS
# ============================================================

def load_documents(directory, excluded=None):
    excluded = set(excluded or [])

    docs = {}
    skipped = []
    errors = []

    for path in sorted(directory.glob("*.json")):
        if path.name in excluded:
            continue

        try:
            doc = load_json(path)

            if is_clinical_document(doc):
                docs[path.name] = doc
            else:
                skipped.append(path.name)

        except Exception as exc:
            errors.append({
                "document": path.name,
                "error": str(exc),
            })

    return docs, skipped, errors


# ============================================================
# 6. VALIDATE APPLIED OPERATIONS
# ============================================================

def validate_operations(after_docs, correction_report):
    results = []

    for op in correction_report.get("operations", []):
        if not op.get("modified", False):
            continue

        document = op.get("document")
        doc = after_docs.get(document)

        result = {
            "document": document,
            "candidate_id": op.get("candidate_id"),
            "operation": op.get("operation"),
            "passed": False,
            "checks": [],
        }

        if doc is None:
            result["checks"].append({
                "check": "DOCUMENT_EXISTS",
                "passed": False,
            })
            results.append(result)
            continue

        entities = {
            entity_id(e): e
            for e in get_entities(doc)
            if entity_id(e)
        }

        relations = get_relations(doc)

        removed_entity_id = op.get(
            "removed_entity_id"
        )

        created_relation_id = op.get(
            "created_relation_id"
        )

        created_relation_type = op.get(
            "created_relation_type"
        )

        source_id = op.get(
            "source_entity_id"
        )

        target_id = op.get(
            "target_entity_id"
        )

        removed_ok = (
            removed_entity_id
            not in entities
        )

        relation_ok = any(
            relation_id(r) == created_relation_id
            and relation_type(r) == created_relation_type
            and str(relation_source(r)) == str(source_id)
            and str(relation_target(r)) == str(target_id)
            for r in relations
        )

        source_ok = (
            source_id in entities
        )

        target_ok = (
            target_id in entities
        )

        result["checks"].extend([
            {
                "check": "REIFIED_ENTITY_REMOVED",
                "passed": removed_ok,
            },
            {
                "check": "CREATED_RELATION_EXISTS",
                "passed": relation_ok,
            },
            {
                "check": "SOURCE_ENTITY_EXISTS",
                "passed": source_ok,
            },
            {
                "check": "TARGET_ENTITY_EXISTS",
                "passed": target_ok,
            },
        ])

        result["passed"] = all(
            c["passed"]
            for c in result["checks"]
        )

        results.append(result)

    return results


# ============================================================
# 7. MAIN
# ============================================================

def main():
    if not BEFORE_DIR.exists():
        raise FileNotFoundError(
            f"Dossier AVANT Pattern C introuvable : {BEFORE_DIR}"
        )

    if not AFTER_DIR.exists():
        raise FileNotFoundError(
            f"Dossier APRES Pattern C introuvable : {AFTER_DIR}"
        )

    if not CORRECTION_REPORT.exists():
        raise FileNotFoundError(
            f"Rapport correction Pattern C introuvable : {CORRECTION_REPORT}"
        )

    guideline_path = resolve_guideline()

    guideline = (
        load_json(guideline_path)
        if guideline_path
        else None
    )

    signatures = get_locked_signatures(
        guideline
    )

    correction_report = load_json(
        CORRECTION_REPORT
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    before_docs, before_skipped, before_errors = load_documents(
        BEFORE_DIR
    )

    after_docs, after_skipped, after_errors = load_documents(
        AFTER_DIR,
        excluded={
            "pattern_c_correction_report.json"
        },
    )

    before_names = set(
        before_docs.keys()
    )

    after_names = set(
        after_docs.keys()
    )

    missing_after = sorted(
        before_names - after_names
    )

    extra_after = sorted(
        after_names - before_names
    )

    common_names = sorted(
        before_names & after_names
    )

    # Documents expected to change
    expected_modified_docs = {
        op.get("document")
        for op in correction_report.get(
            "operations",
            []
        )
        if op.get("modified")
        and op.get("document")
    }

    document_results = []
    new_anomalies = []

    total_preexisting = 0
    total_introduced = 0
    total_resolved = 0
    changed_docs = 0
    unexpected_changes = 0
    missing_expected_changes = 0

    for name in common_names:
        before = before_docs[name]
        after = after_docs[name]

        before_anoms = collect_structural_anomalies(
            before,
            signatures,
        )

        after_anoms = collect_structural_anomalies(
            after,
            signatures,
        )

        preexisting = (
            before_anoms
            & after_anoms
        )

        introduced = (
            after_anoms
            - before_anoms
        )

        resolved = (
            before_anoms
            - after_anoms
        )

        total_preexisting += len(
            preexisting
        )

        total_introduced += len(
            introduced
        )

        total_resolved += len(
            resolved
        )

        identical = (
            clinical_signature(before)
            == clinical_signature(after)
        )

        changed = not identical

        if changed:
            changed_docs += 1

        expected_change = (
            name in expected_modified_docs
        )

        unexpected_change = (
            changed
            and not expected_change
        )

        missing_expected = (
            expected_change
            and not changed
        )

        if unexpected_change:
            unexpected_changes += 1

        if missing_expected:
            missing_expected_changes += 1

        status = (
            "PASS"
            if (
                len(introduced) == 0
                and not unexpected_change
                and not missing_expected
            )
            else "FAIL"
        )

        document_results.append({
            "document": name,
            "expected_to_change": expected_change,
            "clinical_content_changed": changed,
            "unexpected_content_change": unexpected_change,
            "missing_expected_change": missing_expected,
            "preexisting_anomalies": len(preexisting),
            "introduced_by_pattern_c": len(introduced),
            "resolved_by_pattern_c": len(resolved),
            "status": status,
        })

        for anomaly in sorted(
            introduced,
            key=str,
        ):
            new_anomalies.append({
                "document": name,
                "anomaly_type": anomaly[0],
                "reference": (
                    anomaly[1]
                    if len(anomaly) > 1
                    else ""
                ),
                "details": (
                    anomaly[2]
                    if len(anomaly) > 2
                    else ""
                ),
            })

    # Explicit operation validation
    operation_results = validate_operations(
        after_docs,
        correction_report,
    )

    operations_expected = len(
        operation_results
    )

    operations_pass = sum(
        1
        for r in operation_results
        if r["passed"]
    )

    operations_fail = (
        operations_expected
        - operations_pass
    )

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
        and total_introduced == 0
        and operations_fail == 0
        and unexpected_changes == 0
        and missing_expected_changes == 0
        and not missing_after
        and not extra_after
        and len(before_errors) == 0
        and len(after_errors) == 0
    )

    report = {
        "pattern": "C",
        "validation_type": "DIFFERENTIAL_POST_VALIDATION",
        "before_directory": str(BEFORE_DIR),
        "after_directory": str(AFTER_DIR),
        "correction_report": str(CORRECTION_REPORT),
        "guideline": (
            str(guideline_path)
            if guideline_path
            else None
        ),

        "summary": {
            "documents_verified": len(document_results),
            "documents_pass": pass_docs,
            "documents_fail": fail_docs,

            "expected_modified_documents":
                len(expected_modified_docs),

            "clinical_documents_changed":
                changed_docs,

            "unexpected_content_changes":
                unexpected_changes,

            "missing_expected_changes":
                missing_expected_changes,

            "operations_expected":
                operations_expected,

            "operations_pass":
                operations_pass,

            "operations_fail":
                operations_fail,

            "preexisting_anomalies":
                total_preexisting,

            "introduced_by_pattern_c":
                total_introduced,

            "resolved_by_pattern_c":
                total_resolved,

            "missing_after_documents":
                len(missing_after),

            "extra_after_documents":
                len(extra_after),

            "locked_signatures_loaded":
                len(signatures),

            "before_load_errors":
                len(before_errors),

            "after_load_errors":
                len(after_errors),

            "final_status":
                "PASS" if final_pass else "FAIL",
        },

        "documents": document_results,
        "operation_results": operation_results,
        "new_anomalies": new_anomalies,
        "missing_after_documents": missing_after,
        "extra_after_documents": extra_after,
        "before_errors": before_errors,
        "after_errors": after_errors,
    }

    OUTPUT_JSON.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # Document CSV
    with OUTPUT_CSV.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        fields = [
            "document",
            "expected_to_change",
            "clinical_content_changed",
            "unexpected_content_change",
            "missing_expected_change",
            "preexisting_anomalies",
            "introduced_by_pattern_c",
            "resolved_by_pattern_c",
            "status",
        ]

        writer = csv.DictWriter(
            f,
            fieldnames=fields,
        )

        writer.writeheader()

        for row in document_results:
            writer.writerow(row)

    # New anomalies CSV
    with ANOMALIES_CSV.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        fields = [
            "document",
            "anomaly_type",
            "reference",
            "details",
        ]

        writer = csv.DictWriter(
            f,
            fieldnames=fields,
        )

        writer.writeheader()

        for row in new_anomalies:
            writer.writerow(row)

    # Console
    print("=" * 84)
    print("SGCE - PATTERN C DIFFERENTIAL POST-VALIDATION")
    print("=" * 84)

    print(f"AVANT Pattern C               : {BEFORE_DIR}")
    print(f"APRES Pattern C               : {AFTER_DIR}")
    print()

    print(f"Documents vérifiés            : {len(document_results)}")
    print(f"PASS                          : {pass_docs}")
    print(f"FAIL                          : {fail_docs}")
    print()

    print(
        f"Documents attendus modifiés   : "
        f"{len(expected_modified_docs)}"
    )

    print(
        f"Documents réellement modifiés : "
        f"{changed_docs}"
    )

    print(
        f"Modifications inattendues     : "
        f"{unexpected_changes}"
    )

    print(
        f"Corrections attendues absentes: "
        f"{missing_expected_changes}"
    )

    print()

    print(
        f"Opérations attendues          : "
        f"{operations_expected}"
    )

    print(
        f"Opérations PASS               : "
        f"{operations_pass}"
    )

    print(
        f"Opérations FAIL               : "
        f"{operations_fail}"
    )

    print()

    print(
        f"Anomalies pré-existantes      : "
        f"{total_preexisting}"
    )

    print(
        f"Nouvelles anomalies Pattern C : "
        f"{total_introduced}"
    )

    print(
        f"Anomalies résolues Pattern C  : "
        f"{total_resolved}"
    )

    print()

    print(
        f"Docs manquants APRES          : "
        f"{len(missing_after)}"
    )

    print(
        f"Docs supplémentaires APRES    : "
        f"{len(extra_after)}"
    )

    print()

    print(
        f"Signatures TRACE chargées     : "
        f"{len(signatures)}"
    )

    print()

    print(
        f"STATUT FINAL PATTERN C        : "
        f"{'PASS' if final_pass else 'FAIL'}"
    )

    print()

    print(
        f"Rapport JSON                  : "
        f"{OUTPUT_JSON}"
    )

    print(
        f"Rapport documents CSV         : "
        f"{OUTPUT_CSV}"
    )

    print(
        f"Nouvelles anomalies CSV       : "
        f"{ANOMALIES_CSV}"
    )

    print()

    print(
        "Aucune donnée clinique n'a été modifiée "
        "par ce post-validateur."
    )


if __name__ == "__main__":
    main()
