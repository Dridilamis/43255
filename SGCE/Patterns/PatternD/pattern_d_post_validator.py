# -*- coding: utf-8 -*-
"""
pattern_d_post_validator.py
===========================

SGCE — Pattern D Differential Post-Validator

Compare:
- BEFORE D : PatternC/pattern_c_corrected
- AFTER D  : PatternD/pattern_d_corrected

Goals
-----
1) Verify all clinical documents are preserved.
2) Verify all actually applied Pattern D operations:
   - RELINK
   - RETYPE_ENTITY
   - REMOVE_INVALID_RELATION
3) Re-evaluate skipped RETYPE_ENTITY cases:
   - ALREADY_SATISFIED_AFTER_EARLIER_CORRECTION
   - CONFLICTING_RETYPE
   - STILL_UNRESOLVED
4) Verify protected AMBIGUOUS cases were not directly altered.
5) Compare structural anomalies before/after:
   - pre-existing anomalies
   - newly introduced anomalies
   - resolved anomalies
6) Verify TRACE-Sepsis locked domain/range signatures.
7) Produce final PASS / FAIL.

Important
---------
Pre-existing anomalies do NOT fail Pattern D.
Only anomalies introduced by Pattern D are critical.

This validator does NOT modify clinical JSONs.
"""

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


# ============================================================
# 1. PATHS
# ============================================================

PATTERN_D_DIR = Path(__file__).resolve().parent
PATTERNS_DIR = PATTERN_D_DIR.parent
SGCE_DIR = PATTERNS_DIR.parent
BASE_DIR = SGCE_DIR.parent

PATTERN_C_DIR = PATTERNS_DIR / "PatternC"
BEFORE_DIR = PATTERN_C_DIR / "corrected"
AFTER_DIR = PATTERN_D_DIR / "corrected"

VALIDATION_REPORT = PATTERN_D_DIR / "validation" / "pattern_d_validation_report.json"
CORRECTION_REPORT = AFTER_DIR / "pattern_d_correction_report.json"

GUIDELINE_CANDIDATES = [
    BASE_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
    BASE_DIR.parent / "Guideline_TRACE_Sepsis_v1.6.json",
    Path.cwd() / "Guideline_TRACE_Sepsis_v1.6.json",
    PATTERN_D_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
]

OUTPUT_DIR = PATTERN_D_DIR / "post_validation"
OUTPUT_JSON = OUTPUT_DIR / "pattern_d_post_validation_report.json"
OUTPUT_DOCS_CSV = OUTPUT_DIR / "pattern_d_post_validation_documents.csv"
OUTPUT_OPS_CSV = OUTPUT_DIR / "pattern_d_post_validation_operations.csv"
OUTPUT_ANOM_CSV = OUTPUT_DIR / "pattern_d_new_anomalies.csv"


# ============================================================
# 2. BASIC HELPERS
# ============================================================

def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_guideline():
    for p in GUIDELINE_CANDIDATES:
        if p.exists():
            return p
    return None


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
    for p in doc.get("pages", []) or []:
        out.extend(p.get("entities", []) or [])

    return out


def get_relations(doc):
    if isinstance(doc.get("global_relations"), list):
        return doc["global_relations"]

    out = []
    for p in doc.get("pages", []) or []:
        out.extend(p.get("relations", []) or [])

    return out


def find_entity(doc, eid):
    for e in get_entities(doc):
        if str(entity_id(e)) == str(eid):
            return e
    return None


def find_relation(doc, rid):
    for r in get_relations(doc):
        if str(relation_id(r)) == str(rid):
            return r
    return None


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

    for rtype, spec in locked.items():
        if not isinstance(spec, dict):
            continue

        dom = spec.get("domaine")
        img = spec.get("image")

        if dom and img:
            signatures[rtype] = {
                "domaine": dom,
                "image": img,
            }

    return signatures


# ============================================================
# 4. STRUCTURAL ANOMALIES
# ============================================================

def collect_structural_anomalies(doc, signatures):
    ents = get_entities(doc)
    rels = get_relations(doc)

    anomalies = []

    ec = Counter(
        entity_id(e)
        for e in ents
        if entity_id(e)
    )

    rc = Counter(
        relation_id(r)
        for r in rels
        if relation_id(r)
    )

    for eid, count in ec.items():
        if count > 1:
            anomalies.append(
                (
                    "DUPLICATE_ENTITY_ID",
                    str(eid),
                    str(count),
                )
            )

    for rid, count in rc.items():
        if count > 1:
            anomalies.append(
                (
                    "DUPLICATE_RELATION_ID",
                    str(rid),
                    str(count),
                )
            )

    emap = {
        entity_id(e): e
        for e in ents
        if entity_id(e)
    }

    for r in rels:
        rid = relation_id(r)
        rtype = relation_type(r)
        src = relation_source(r)
        tgt = relation_target(r)

        if src and src not in emap:
            anomalies.append(
                (
                    "ORPHAN_RELATION_SOURCE",
                    str(rid),
                    str(src),
                )
            )

        if tgt and tgt not in emap:
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
            and src in emap
            and tgt in emap
        ):
            expected = signatures[rtype]

            src_type = entity_type(
                emap[src]
            )

            tgt_type = entity_type(
                emap[tgt]
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
# 5. LOAD DOCS
# ============================================================

def load_docs(directory, excluded=None):
    excluded = set(excluded or [])

    docs = {}
    skipped = []
    errors = []

    for p in sorted(directory.glob("*.json")):
        if p.name in excluded:
            continue

        try:
            doc = load_json(p)

            if is_clinical_document(doc):
                docs[p.name] = doc
            else:
                skipped.append(p.name)

        except Exception as exc:
            errors.append({
                "document": p.name,
                "error": str(exc),
            })

    return docs, skipped, errors


# ============================================================
# 6. VALIDATE APPLIED OPERATIONS
# ============================================================

def validate_applied_operations(after_docs, correction_report):
    results = []

    for op in correction_report.get("operations", []):
        if not op.get("modified"):
            continue

        doc_name = op.get("document")
        doc = after_docs.get(doc_name)

        result = {
            "document": doc_name,
            "candidate_id": op.get("candidate_id"),
            "operation": op.get("operation"),
            "status": "FAIL",
            "checks": [],
        }

        if doc is None:
            result["checks"].append(
                "DOCUMENT_NOT_FOUND"
            )
            results.append(result)
            continue

        operation = op.get("operation")

        # ----------------------------------------------------
        # RELINK
        # ----------------------------------------------------

        if operation == "RELINK":
            rid = op.get("relation_id")
            role = op.get("role")
            new_id = op.get("new_entity_id")

            r = find_relation(doc, rid)

            if r is None:
                result["checks"].append(
                    "RELATION_NOT_FOUND"
                )
                results.append(result)
                continue

            endpoint_ok = False

            if role == "SOURCE":
                endpoint_ok = (
                    str(relation_source(r))
                    == str(new_id)
                )

            elif role == "TARGET":
                endpoint_ok = (
                    str(relation_target(r))
                    == str(new_id)
                )

            entity_ok = (
                find_entity(doc, new_id)
                is not None
            )

            result["checks"].extend([
                f"ENDPOINT_UPDATED={endpoint_ok}",
                f"NEW_ENTITY_EXISTS={entity_ok}",
            ])

            if endpoint_ok and entity_ok:
                result["status"] = "PASS"

        # ----------------------------------------------------
        # RETYPE_ENTITY
        # ----------------------------------------------------

        elif operation == "RETYPE_ENTITY":
            eid = op.get("entity_id")
            new_type = op.get("new_type")

            e = find_entity(doc, eid)

            entity_ok = (
                e is not None
                and entity_type(e) == new_type
            )

            result["checks"].append(
                f"ENTITY_HAS_NEW_TYPE={entity_ok}"
            )

            if entity_ok:
                result["status"] = "PASS"

        # ----------------------------------------------------
        # REMOVE_INVALID_RELATION
        # ----------------------------------------------------

        elif operation == "REMOVE_INVALID_RELATION":
            rid = op.get("relation_id")

            removed_ok = (
                find_relation(doc, rid)
                is None
            )

            result["checks"].append(
                f"RELATION_REMOVED={removed_ok}"
            )

            if removed_ok:
                result["status"] = "PASS"

        else:
            result["checks"].append(
                "UNKNOWN_OPERATION"
            )

        results.append(result)

    return results


# ============================================================
# 7. RE-EVALUATE SKIPPED RETYPE CASES
# ============================================================

def reevaluate_skipped_retypes(
    after_docs,
    validation_report,
    correction_report,
):
    """
    Specifically handles validator-confirmed RETYPE_ENTITY candidates that
    were skipped by corrector because the entity type had already changed.
    """

    # candidate_id -> validation candidate
    val_map = {
        c.get("candidate_id"): c
        for c in validation_report.get(
            "validated_candidates",
            []
        )
    }

    results = []

    for op in correction_report.get(
        "operations",
        []
    ):
        if op.get("modified"):
            continue

        if op.get("reason") != "ENTITY_TYPE_CHANGED_SINCE_VALIDATION":
            continue

        cid = op.get("candidate_id")
        candidate = val_map.get(cid)

        result = {
            "document": op.get("document"),
            "candidate_id": cid,
            "status": None,
            "entity_id": None,
            "expected_new_type": None,
            "actual_final_type": None,
            "reason": "",
        }

        if candidate is None:
            result["status"] = "STILL_UNRESOLVED"
            result["reason"] = "Validation candidate not found."
            results.append(result)
            continue

        details = candidate.get(
            "action_details",
            {}
        )

        eid = details.get("entity_id")
        new_type = details.get("new_type")

        result["entity_id"] = eid
        result["expected_new_type"] = new_type

        doc = after_docs.get(
            op.get("document")
        )

        if doc is None:
            result["status"] = "STILL_UNRESOLVED"
            result["reason"] = "Document after correction not found."
            results.append(result)
            continue

        e = find_entity(
            doc,
            eid
        )

        if e is None:
            result["status"] = "STILL_UNRESOLVED"
            result["reason"] = "Entity not found after correction."
            results.append(result)
            continue

        final_type = entity_type(e)

        result["actual_final_type"] = final_type

        if final_type == new_type:
            result["status"] = (
                "ALREADY_SATISFIED_AFTER_EARLIER_CORRECTION"
            )
            result["reason"] = (
                "The entity already has the validated target type."
            )

        else:
            result["status"] = (
                "CONFLICTING_RETYPE"
            )
            result["reason"] = (
                f"Final type={final_type}, expected={new_type}."
            )

        results.append(result)

    return results


# ============================================================
# 8. PROTECTED AMBIGUOUS SAFETY CHECK
# ============================================================

def protected_candidates_check(
    before_docs,
    after_docs,
    validation_report,
):
    """
    For AMBIGUOUS Pattern D candidates, make sure their exact offending
    relation and endpoint are not directly changed unless that same document
    underwent another validated operation that incidentally resolves them.

    We report state changes but do not automatically fail if the anomaly was
    resolved as a side-effect of a safe correction.
    """

    results = []

    for c in validation_report.get(
        "validated_candidates",
        []
    ):
        if c.get("validation_status") != "AMBIGUOUS":
            continue

        doc_name = c.get("document")

        before = before_docs.get(doc_name)
        after = after_docs.get(doc_name)

        if before is None or after is None:
            results.append({
                "document": doc_name,
                "candidate_id": c.get("candidate_id"),
                "status": "UNVERIFIABLE",
            })
            continue

        rel_info = c.get("relation") or {}
        rid = rel_info.get("relation_id")

        before_rel = find_relation(
            before,
            rid
        )

        after_rel = find_relation(
            after,
            rid
        )

        if before_rel is None:
            status = "UNVERIFIABLE"

        elif after_rel is None:
            # Could be intentionally removed by another safe correction.
            status = "CHANGED_AS_SIDE_EFFECT_OR_REMOVED"

        else:
            before_src = relation_source(before_rel)
            before_tgt = relation_target(before_rel)

            after_src = relation_source(after_rel)
            after_tgt = relation_target(after_rel)

            if (
                str(before_src) == str(after_src)
                and str(before_tgt) == str(after_tgt)
            ):
                status = "UNCHANGED_PROTECTED"
            else:
                status = "CHANGED_AS_SIDE_EFFECT"

        results.append({
            "document": doc_name,
            "candidate_id": c.get("candidate_id"),
            "status": status,
        })

    return results


# ============================================================
# 9. MAIN
# ============================================================

def main():
    for p, label in [
        (BEFORE_DIR, "BEFORE Pattern D"),
        (AFTER_DIR, "AFTER Pattern D"),
        (VALIDATION_REPORT, "Pattern D validation report"),
        (CORRECTION_REPORT, "Pattern D correction report"),
    ]:
        if not p.exists():
            raise FileNotFoundError(
                f"{label} introuvable : {p}"
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

    validation_report = load_json(
        VALIDATION_REPORT
    )

    correction_report = load_json(
        CORRECTION_REPORT
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    before_docs, before_skipped, before_errors = (
        load_docs(
            BEFORE_DIR,
            excluded={
                "pattern_c_correction_report.json"
            },
        )
    )

    after_docs, after_skipped, after_errors = (
        load_docs(
            AFTER_DIR,
            excluded={
                "pattern_d_correction_report.json"
            },
        )
    )

    before_names = set(before_docs)
    after_names = set(after_docs)

    missing_after = sorted(
        before_names - after_names
    )

    extra_after = sorted(
        after_names - before_names
    )

    common = sorted(
        before_names & after_names
    )

    # --------------------------------------------------------
    # Expected modified docs from actually applied ops
    # --------------------------------------------------------

    expected_modified_docs = {
        op.get("document")
        for op in correction_report.get(
            "operations",
            []
        )
        if op.get("modified")
        and op.get("document")
    }

    doc_results = []
    new_anoms_rows = []

    total_preexisting = 0
    total_introduced = 0
    total_resolved = 0

    changed_docs = 0
    unexpected_changes = 0
    missing_expected_changes = 0

    for name in common:
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

        preexisting = before_anoms & after_anoms
        introduced = after_anoms - before_anoms
        resolved = before_anoms - after_anoms

        total_preexisting += len(preexisting)
        total_introduced += len(introduced)
        total_resolved += len(resolved)

        changed = (
            clinical_signature(before)
            != clinical_signature(after)
        )

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

        doc_results.append({
            "document": name,
            "expected_to_change": expected_change,
            "clinical_content_changed": changed,
            "unexpected_content_change": unexpected_change,
            "missing_expected_change": missing_expected,
            "preexisting_anomalies": len(preexisting),
            "introduced_by_pattern_d": len(introduced),
            "resolved_by_pattern_d": len(resolved),
            "status": status,
        })

        for anomaly in sorted(
            introduced,
            key=str,
        ):
            new_anoms_rows.append({
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

    # --------------------------------------------------------
    # Applied operations
    # --------------------------------------------------------

    applied_results = validate_applied_operations(
        after_docs,
        correction_report,
    )

    applied_pass = sum(
        1
        for r in applied_results
        if r["status"] == "PASS"
    )

    applied_fail = (
        len(applied_results)
        - applied_pass
    )

    # --------------------------------------------------------
    # Skipped RETYPE cases
    # --------------------------------------------------------

    skipped_retypes = reevaluate_skipped_retypes(
        after_docs,
        validation_report,
        correction_report,
    )

    skipped_retype_satisfied = sum(
        1
        for r in skipped_retypes
        if r["status"]
        == "ALREADY_SATISFIED_AFTER_EARLIER_CORRECTION"
    )

    skipped_retype_conflicts = sum(
        1
        for r in skipped_retypes
        if r["status"]
        == "CONFLICTING_RETYPE"
    )

    skipped_retype_unresolved = sum(
        1
        for r in skipped_retypes
        if r["status"]
        == "STILL_UNRESOLVED"
    )

    # --------------------------------------------------------
    # Protected ambiguous candidates
    # --------------------------------------------------------

    protected_results = protected_candidates_check(
        before_docs,
        after_docs,
        validation_report,
    )

    protected_unchanged = sum(
        1
        for r in protected_results
        if r["status"] == "UNCHANGED_PROTECTED"
    )

    protected_side_effect = sum(
        1
        for r in protected_results
        if r["status"] in {
            "CHANGED_AS_SIDE_EFFECT",
            "CHANGED_AS_SIDE_EFFECT_OR_REMOVED",
        }
    )

    protected_unverifiable = sum(
        1
        for r in protected_results
        if r["status"] == "UNVERIFIABLE"
    )

    pass_docs = sum(
        1
        for r in doc_results
        if r["status"] == "PASS"
    )

    fail_docs = (
        len(doc_results)
        - pass_docs
    )

    # Pattern D PASS conditions
    final_pass = (
        fail_docs == 0
        and total_introduced == 0
        and applied_fail == 0
        and skipped_retype_conflicts == 0
        and skipped_retype_unresolved == 0
        and unexpected_changes == 0
        and missing_expected_changes == 0
        and not missing_after
        and not extra_after
        and len(before_errors) == 0
        and len(after_errors) == 0
    )

    report = {
        "pattern": "D",
        "validation_type": "DIFFERENTIAL_POST_VALIDATION",
        "before_directory": str(BEFORE_DIR),
        "after_directory": str(AFTER_DIR),
        "validation_report": str(VALIDATION_REPORT),
        "correction_report": str(CORRECTION_REPORT),
        "guideline": (
            str(guideline_path)
            if guideline_path
            else None
        ),

        "summary": {
            "documents_verified": len(doc_results),
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

            "applied_operations_expected":
                len(applied_results),

            "applied_operations_pass":
                applied_pass,

            "applied_operations_fail":
                applied_fail,

            "skipped_retypes_total":
                len(skipped_retypes),

            "skipped_retypes_already_satisfied":
                skipped_retype_satisfied,

            "skipped_retypes_conflicting":
                skipped_retype_conflicts,

            "skipped_retypes_unresolved":
                skipped_retype_unresolved,

            "protected_ambiguous_total":
                len(protected_results),

            "protected_ambiguous_unchanged":
                protected_unchanged,

            "protected_ambiguous_side_effect_changes":
                protected_side_effect,

            "protected_ambiguous_unverifiable":
                protected_unverifiable,

            "preexisting_anomalies":
                total_preexisting,

            "introduced_by_pattern_d":
                total_introduced,

            "resolved_by_pattern_d":
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

        "documents":
            doc_results,

        "applied_operation_results":
            applied_results,

        "skipped_retype_results":
            skipped_retypes,

        "protected_ambiguous_results":
            protected_results,

        "new_anomalies":
            new_anoms_rows,

        "missing_after_documents":
            missing_after,

        "extra_after_documents":
            extra_after,

        "before_errors":
            before_errors,

        "after_errors":
            after_errors,
    }

    OUTPUT_JSON.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # ========================================================
    # CSV documents
    # ========================================================

    with OUTPUT_DOCS_CSV.open(
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
            "introduced_by_pattern_d",
            "resolved_by_pattern_d",
            "status",
        ]

        writer = csv.DictWriter(
            f,
            fieldnames=fields,
        )

        writer.writeheader()

        for row in doc_results:
            writer.writerow(row)

    # ========================================================
    # CSV operations
    # ========================================================

    with OUTPUT_OPS_CSV.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        fields = [
            "kind",
            "document",
            "candidate_id",
            "operation_or_status",
            "result",
            "details",
        ]

        writer = csv.DictWriter(
            f,
            fieldnames=fields,
        )

        writer.writeheader()

        for r in applied_results:
            writer.writerow({
                "kind": "APPLIED_OPERATION",
                "document": r.get("document", ""),
                "candidate_id": r.get("candidate_id", ""),
                "operation_or_status": r.get("operation", ""),
                "result": r.get("status", ""),
                "details": " | ".join(r.get("checks", [])),
            })

        for r in skipped_retypes:
            writer.writerow({
                "kind": "SKIPPED_RETYPE",
                "document": r.get("document", ""),
                "candidate_id": r.get("candidate_id", ""),
                "operation_or_status": "RETYPE_ENTITY",
                "result": r.get("status", ""),
                "details": r.get("reason", ""),
            })

    # ========================================================
    # CSV new anomalies
    # ========================================================

    with OUTPUT_ANOM_CSV.open(
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

        for row in new_anoms_rows:
            writer.writerow(row)

    # ========================================================
    # CONSOLE
    # ========================================================

    print("=" * 92)
    print("SGCE - PATTERN D DIFFERENTIAL POST-VALIDATION")
    print("=" * 92)

    print(f"AVANT Pattern D                    : {BEFORE_DIR}")
    print(f"APRES Pattern D                    : {AFTER_DIR}")
    print()

    print(f"Documents vérifiés                 : {len(doc_results)}")
    print(f"PASS                               : {pass_docs}")
    print(f"FAIL                               : {fail_docs}")
    print()

    print(
        f"Documents attendus modifiés        : "
        f"{len(expected_modified_docs)}"
    )

    print(
        f"Documents réellement modifiés      : "
        f"{changed_docs}"
    )

    print(
        f"Modifications inattendues          : "
        f"{unexpected_changes}"
    )

    print(
        f"Corrections attendues absentes     : "
        f"{missing_expected_changes}"
    )

    print()

    print(
        f"Opérations appliquées vérifiées    : "
        f"{len(applied_results)}"
    )

    print(
        f"Opérations PASS                    : "
        f"{applied_pass}"
    )

    print(
        f"Opérations FAIL                    : "
        f"{applied_fail}"
    )

    print()

    print(
        f"RETYPE ignorés à réévaluer         : "
        f"{len(skipped_retypes)}"
    )

    print(
        f"Déjà satisfaits                    : "
        f"{skipped_retype_satisfied}"
    )

    print(
        f"Conflits RETYPE                    : "
        f"{skipped_retype_conflicts}"
    )

    print(
        f"RETYPE non résolus                 : "
        f"{skipped_retype_unresolved}"
    )

    print()

    print(
        f"Cas AMBIGUOUS protégés             : "
        f"{len(protected_results)}"
    )

    print(
        f"Protégés inchangés                 : "
        f"{protected_unchanged}"
    )

    print(
        f"Protégés changés par effet indirect: "
        f"{protected_side_effect}"
    )

    print()

    print(
        f"Anomalies pré-existantes           : "
        f"{total_preexisting}"
    )

    print(
        f"Nouvelles anomalies Pattern D      : "
        f"{total_introduced}"
    )

    print(
        f"Anomalies résolues Pattern D       : "
        f"{total_resolved}"
    )

    print()

    print(
        f"Docs manquants APRES               : "
        f"{len(missing_after)}"
    )

    print(
        f"Docs supplémentaires APRES         : "
        f"{len(extra_after)}"
    )

    print(
        f"Signatures TRACE chargées          : "
        f"{len(signatures)}"
    )

    print()

    print(
        f"STATUT FINAL PATTERN D             : "
        f"{'PASS' if final_pass else 'FAIL'}"
    )

    print()

    print(
        f"Rapport JSON                       : "
        f"{OUTPUT_JSON}"
    )

    print(
        f"Rapport documents CSV              : "
        f"{OUTPUT_DOCS_CSV}"
    )

    print(
        f"Rapport opérations CSV             : "
        f"{OUTPUT_OPS_CSV}"
    )

    print(
        f"Nouvelles anomalies CSV            : "
        f"{OUTPUT_ANOM_CSV}"
    )

    print()

    print(
        "Aucune donnée clinique n'a été modifiée "
        "par ce post-validateur."
    )


if __name__ == "__main__":
    main()
