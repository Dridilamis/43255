# -*- coding: utf-8 -*-
"""
pattern_b_post_validator.py
===========================

SGCE — PATTERN B GLOBAL DIFFERENTIAL POST-VALIDATOR

Scope
-----
Pattern B = B1 + B2

Compare:
- BEFORE Pattern B:
    PatternA/PatternA6/pattern_a6_corrected
    or PatternA6/pattern_a6_corrected

- AFTER Pattern B:
    PatternB2/pattern_b2_corrected
    fallback PatternB1/pattern_b1_corrected

Goals
-----
1) Verify that all clinical documents are preserved.
2) Distinguish PRE-EXISTING anomalies from NEW anomalies introduced by Pattern B.
3) Validate B1 corrections if they exist:
   - RELINK
   - CREATE_AND_LINK
4) Validate B2 corrections if they exist:
   - CREATE_B_REPLACE_DIRECT_WITH_TWO_HOP
5) Verify no new:
   - duplicate entity IDs
   - duplicate relation IDs
   - orphan relation endpoints
6) Verify TRACE-Sepsis relation signatures using Guideline v1.6 locked signatures.
7) Produce PASS/FAIL for the whole Pattern B.

IMPORTANT
---------
- Pre-existing anomalies do NOT fail Pattern B.
- Only anomalies introduced by Pattern B are critical.
- Works both on the current corpus (0 safe B corrections) and on future datasets
  where B1/B2 may actually modify documents.
- This validator does NOT modify clinical JSONs.
"""

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


# ============================================================
# 1. PATHS
# ============================================================

PATTERN_B_DIR = Path(__file__).resolve().parent
PATTERNS_DIR = PATTERN_B_DIR.parent
SGCE_DIR = PATTERNS_DIR.parent
BASE_DIR = SGCE_DIR.parent

PATTERN_A6_DIR = PATTERNS_DIR / "PatternA" / "PatternA6"
PATTERN_B1_DIR = PATTERN_B_DIR / "PatternB1"
PATTERN_B2_DIR = PATTERN_B_DIR / "PatternB2"

BEFORE_DIR_CANDIDATES = [
    PATTERN_A6_DIR / "corrected",
]

AFTER_DIR_CANDIDATES = [
    PATTERN_B2_DIR / "corrected",
    PATTERN_B1_DIR / "corrected",
]

B1_REPORT_CANDIDATES = [
    PATTERN_B1_DIR / "corrected" / "pattern_b1_correction_report.json",
]

B2_REPORT_CANDIDATES = [
    PATTERN_B2_DIR / "corrected" / "pattern_b2_correction_report.json",
]

GUIDELINE_CANDIDATES = [
    BASE_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
    BASE_DIR.parent / "Guideline_TRACE_Sepsis_v1.6.json",
    Path.cwd() / "Guideline_TRACE_Sepsis_v1.6.json",
    PATTERN_B_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
]

OUTPUT_DIR = PATTERN_B_DIR / "post_validation"
OUTPUT_JSON = OUTPUT_DIR / "pattern_b_post_validation_report.json"
OUTPUT_CSV = OUTPUT_DIR / "pattern_b_post_validation_documents.csv"
ANOMALIES_CSV = OUTPUT_DIR / "pattern_b_new_anomalies.csv"


# ============================================================
# 2. GENERIC HELPERS
# ============================================================

def resolve_existing_dir(candidates, label):
    for p in candidates:
        if p.exists() and any(p.glob("*.json")):
            return p
    raise FileNotFoundError(f"{label} introuvable.")


def resolve_existing_file(candidates):
    for p in candidates:
        if p.exists():
            return p
    return None


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
        or r.get("sujet")
        or r.get("subject")
    )


def relation_target(r):
    return (
        r.get("identifiant_entite_objet")
        or r.get("to_id")
        or r.get("object_id")
        or r.get("objet")
        or r.get("object")
    )


def get_entities(doc):
    """
    Prefer global_entities if available to avoid page/global mirror duplication.
    """
    if isinstance(doc.get("global_entities"), list):
        return doc["global_entities"]

    out = []
    for page in doc.get("pages", []) or []:
        out.extend(page.get("entities", []) or [])
    return out


def get_relations(doc):
    """
    Prefer global_relations if available to avoid page/global mirror duplication.
    """
    if isinstance(doc.get("global_relations"), list):
        return doc["global_relations"]

    out = []
    for page in doc.get("pages", []) or []:
        out.extend(page.get("relations", []) or [])
    return out


def clinical_signature(doc):
    return json.dumps(
        doc,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


# ============================================================
# 3. TRACE-SEPSIS LOCKED SIGNATURES
# ============================================================

def resolve_guideline():
    for p in GUIDELINE_CANDIDATES:
        if p.exists():
            return p
    return None


def get_locked_signatures(guideline):
    if guideline is None:
        return {}

    root = guideline.get("ontologie_sepsis_graph", guideline)

    locked = root.get(
        "signatures_relations_verrouillees_v1_5",
        {}
    )

    signatures = {}

    if isinstance(locked, dict):
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
# 4. STRUCTURAL ANOMALY COLLECTION
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

    # --------------------------------------------------------
    # Duplicate IDs
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Entity map
    # --------------------------------------------------------

    entity_map = {
        entity_id(e): e
        for e in entities
        if entity_id(e)
    }

    # --------------------------------------------------------
    # Relation checks
    # --------------------------------------------------------

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

        # Locked TRACE-Sepsis signature validation
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
# 5. LOAD CLINICAL DOCUMENTS
# ============================================================

def load_clinical_documents(directory, excluded_names=None):
    excluded_names = set(
        excluded_names or []
    )

    docs = {}
    skipped = []
    errors = []

    for path in sorted(
        directory.glob("*.json")
    ):
        if path.name in excluded_names:
            continue

        try:
            doc = load_json(path)

            if is_clinical_document(doc):
                docs[path.name] = doc
            else:
                skipped.append(
                    path.name
                )

        except Exception as exc:
            errors.append({
                "document":
                    path.name,

                "error":
                    str(exc),
            })

    return docs, skipped, errors


# ============================================================
# 6. VALIDATE B1 OPERATIONS
# ============================================================

def validate_b1_operations(after_docs, report):
    results = []

    if not report:
        return results

    for op in report.get(
        "operations",
        []
    ):
        if not op.get(
            "modified",
            False,
        ):
            continue

        doc_name = op.get(
            "document"
        )

        doc = after_docs.get(
            doc_name
        )

        result = {
            "pattern":
                "B1",

            "document":
                doc_name,

            "passed":
                False,

            "details":
                [],
        }

        if doc is None:
            result["details"].append(
                "DOCUMENT_AFTER_NOT_FOUND"
            )
            results.append(result)
            continue

        entities = {
            entity_id(e): e
            for e in get_entities(doc)
            if entity_id(e)
        }

        relations = get_relations(doc)

        mods = op.get(
            "modifications",
            []
        )

        if not mods:
            result["details"].append(
                "NO_MODIFICATION_DETAILS"
            )
            results.append(result)
            continue

        checks = []

        for m in mods:
            mtype = m.get(
                "operation"
            )

            if mtype == "RELINK":
                new_id = m.get(
                    "new_entity_id"
                )

                ok = (
                    new_id in entities
                )

                checks.append(ok)

                result["details"].append(
                    (
                        f"RELINK_ENTITY_EXISTS="
                        f"{ok}"
                    )
                )

            elif mtype == "CREATE_AND_LINK":
                new_id = m.get(
                    "created_entity_id"
                )

                expected_type = m.get(
                    "created_entity_type"
                )

                ent = entities.get(
                    new_id
                )

                ok = (
                    ent is not None
                    and entity_type(ent)
                    == expected_type
                )

                checks.append(ok)

                result["details"].append(
                    (
                        f"CREATED_ENTITY="
                        f"{ok}"
                    )
                )

        # General relation endpoint sanity after B1:
        entity_ids = set(
            entities.keys()
        )

        endpoints_ok = all(
            (
                not relation_source(r)
                or relation_source(r)
                in entity_ids
            )
            and (
                not relation_target(r)
                or relation_target(r)
                in entity_ids
            )
            for r in relations
        )

        checks.append(
            endpoints_ok
        )

        result["details"].append(
            (
                f"RELATION_ENDPOINTS_VALID="
                f"{endpoints_ok}"
            )
        )

        result["passed"] = (
            bool(checks)
            and all(checks)
        )

        results.append(result)

    return results


# ============================================================
# 7. VALIDATE B2 OPERATIONS
# ============================================================

def validate_b2_operations(after_docs, report):
    results = []

    if not report:
        return results

    for op in report.get(
        "operations",
        []
    ):
        if not op.get(
            "modified",
            False,
        ):
            continue

        doc_name = op.get(
            "document"
        )

        doc = after_docs.get(
            doc_name
        )

        result = {
            "pattern":
                "B2",

            "document":
                doc_name,

            "candidate_id":
                op.get(
                    "candidate_id"
                ),

            "passed":
                False,

            "details":
                [],
        }

        if doc is None:
            result["details"].append(
                "DOCUMENT_AFTER_NOT_FOUND"
            )
            results.append(result)
            continue

        entities = {
            entity_id(e): e
            for e in get_entities(doc)
            if entity_id(e)
        }

        relations = get_relations(doc)

        new_entity_id = op.get(
            "created_entity_id"
        )

        expected_type = op.get(
            "created_entity_type"
        )

        source_id = op.get(
            "source_entity_id"
        )

        target_id = op.get(
            "target_entity_id"
        )

        r1_id = op.get(
            "created_relation_1_id"
        )

        r1_type = op.get(
            "created_relation_1_type"
        )

        r2_id = op.get(
            "created_relation_2_id"
        )

        r2_type = op.get(
            "created_relation_2_type"
        )

        removed_id = op.get(
            "removed_direct_relation_id"
        )

        # ----------------------------------------------------
        # Created entity exists and has expected type
        # ----------------------------------------------------

        ent = entities.get(
            new_entity_id
        )

        entity_ok = (
            ent is not None
            and entity_type(ent)
            == expected_type
        )

        # ----------------------------------------------------
        # First relation exists exactly
        # ----------------------------------------------------

        r1_ok = any(
            relation_id(r) == r1_id
            and relation_type(r) == r1_type
            and relation_source(r) == source_id
            and relation_target(r) == new_entity_id
            for r in relations
        )

        # ----------------------------------------------------
        # Second relation exists exactly
        # ----------------------------------------------------

        r2_ok = any(
            relation_id(r) == r2_id
            and relation_type(r) == r2_type
            and relation_source(r) == new_entity_id
            and relation_target(r) == target_id
            for r in relations
        )

        # ----------------------------------------------------
        # Old direct relation removed
        # ----------------------------------------------------

        old_removed = not any(
            relation_id(r) == removed_id
            for r in relations
        )

        result["details"].extend([
            (
                f"CREATED_ENTITY="
                f"{entity_ok}"
            ),
            (
                f"RELATION_1="
                f"{r1_ok}"
            ),
            (
                f"RELATION_2="
                f"{r2_ok}"
            ),
            (
                f"OLD_DIRECT_REMOVED="
                f"{old_removed}"
            ),
        ])

        result["passed"] = all([
            entity_ok,
            r1_ok,
            r2_ok,
            old_removed,
        ])

        results.append(result)

    return results


# ============================================================
# 8. MAIN
# ============================================================

def main():
    before_dir = resolve_existing_dir(
        BEFORE_DIR_CANDIDATES,
        "Dossier AVANT Pattern B",
    )

    after_dir = resolve_existing_dir(
        AFTER_DIR_CANDIDATES,
        "Dossier APRES Pattern B",
    )

    b1_report_path = (
        resolve_existing_file(
            B1_REPORT_CANDIDATES
        )
    )

    b2_report_path = (
        resolve_existing_file(
            B2_REPORT_CANDIDATES
        )
    )

    b1_report = (
        load_json(b1_report_path)
        if b1_report_path
        else None
    )

    b2_report = (
        load_json(b2_report_path)
        if b2_report_path
        else None
    )

    guideline_path = (
        resolve_guideline()
    )

    guideline = (
        load_json(guideline_path)
        if guideline_path
        else None
    )

    signatures = (
        get_locked_signatures(
            guideline
        )
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    excluded_after = {
        "pattern_b1_correction_report.json",
        "pattern_b2_correction_report.json",
    }

    before_docs, before_skipped, before_errors = (
        load_clinical_documents(
            before_dir
        )
    )

    after_docs, after_skipped, after_errors = (
        load_clinical_documents(
            after_dir,
            excluded_names=excluded_after,
        )
    )

    before_names = set(
        before_docs
    )

    after_names = set(
        after_docs
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

    document_results = []
    new_anomalies_rows = []

    total_preexisting = 0
    total_introduced = 0
    total_resolved = 0
    clinical_content_changed = 0

    # Which docs were legitimately modified according to B reports?
    expected_modified_docs = set()

    for report in (
        b1_report,
        b2_report,
    ):
        if not report:
            continue

        for op in report.get(
            "operations",
            []
        ):
            if op.get(
                "modified"
            ):
                if op.get(
                    "document"
                ):
                    expected_modified_docs.add(
                        op["document"]
                    )

    for name in common_names:
        before = before_docs[name]
        after = after_docs[name]

        before_anoms = (
            collect_structural_anomalies(
                before,
                signatures,
            )
        )

        after_anoms = (
            collect_structural_anomalies(
                after,
                signatures,
            )
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

        actually_changed = (
            not identical
        )

        if actually_changed:
            clinical_content_changed += 1

        expected_to_change = (
            name in expected_modified_docs
        )

        unexpected_content_change = (
            actually_changed
            and not expected_to_change
        )

        missing_expected_change = (
            expected_to_change
            and not actually_changed
        )

        status = (
            "PASS"
            if (
                len(introduced) == 0
                and not unexpected_content_change
                and not missing_expected_change
            )
            else "FAIL"
        )

        document_results.append({
            "document":
                name,

            "expected_to_change":
                expected_to_change,

            "clinical_content_changed":
                actually_changed,

            "unexpected_content_change":
                unexpected_content_change,

            "missing_expected_change":
                missing_expected_change,

            "preexisting_anomalies":
                len(preexisting),

            "introduced_by_pattern_b":
                len(introduced),

            "resolved_by_pattern_b":
                len(resolved),

            "status":
                status,
        })

        for anomaly in sorted(
            introduced,
            key=str,
        ):
            new_anomalies_rows.append({
                "document":
                    name,

                "anomaly_type":
                    anomaly[0],

                "reference":
                    anomaly[1]
                    if len(anomaly) > 1
                    else "",

                "details":
                    anomaly[2]
                    if len(anomaly) > 2
                    else "",
            })

    # --------------------------------------------------------
    # Validate explicit operations
    # --------------------------------------------------------

    b1_operation_results = (
        validate_b1_operations(
            after_docs,
            b1_report,
        )
    )

    b2_operation_results = (
        validate_b2_operations(
            after_docs,
            b2_report,
        )
    )

    operation_results = (
        b1_operation_results
        + b2_operation_results
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

    # --------------------------------------------------------
    # Summary documents
    # --------------------------------------------------------

    pass_docs = sum(
        1
        for r in document_results
        if r["status"] == "PASS"
    )

    fail_docs = (
        len(document_results)
        - pass_docs
    )

    unexpected_changes = sum(
        1
        for r in document_results
        if r[
            "unexpected_content_change"
        ]
    )

    missing_expected_changes = sum(
        1
        for r in document_results
        if r[
            "missing_expected_change"
        ]
    )

    final_pass = (
        fail_docs == 0
        and total_introduced == 0
        and operations_fail == 0
        and not missing_after
        and not extra_after
        and unexpected_changes == 0
        and missing_expected_changes == 0
        and len(before_errors) == 0
        and len(after_errors) == 0
    )

    # --------------------------------------------------------
    # Output JSON
    # --------------------------------------------------------

    report = {
        "pattern":
            "B",

        "validation_type":
            "GLOBAL_DIFFERENTIAL_POST_VALIDATION",

        "before_directory":
            str(before_dir),

        "after_directory":
            str(after_dir),

        "guideline":
            (
                str(guideline_path)
                if guideline_path
                else None
            ),

        "b1_correction_report":
            (
                str(b1_report_path)
                if b1_report_path
                else None
            ),

        "b2_correction_report":
            (
                str(b2_report_path)
                if b2_report_path
                else None
            ),

        "summary": {
            "documents_verified":
                len(document_results),

            "documents_pass":
                pass_docs,

            "documents_fail":
                fail_docs,

            "expected_modified_documents":
                len(
                    expected_modified_docs
                ),

            "clinical_documents_changed":
                clinical_content_changed,

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

            "introduced_by_pattern_b":
                total_introduced,

            "resolved_by_pattern_b":
                total_resolved,

            "missing_after_documents":
                len(missing_after),

            "extra_after_documents":
                len(extra_after),

            "before_load_errors":
                len(before_errors),

            "after_load_errors":
                len(after_errors),

            "locked_signatures_loaded":
                len(signatures),

            "final_status":
                (
                    "PASS"
                    if final_pass
                    else "FAIL"
                ),
        },

        "documents":
            document_results,

        "operation_results":
            operation_results,

        "missing_after_documents":
            missing_after,

        "extra_after_documents":
            extra_after,

        "before_errors":
            before_errors,

        "after_errors":
            after_errors,

        "new_anomalies":
            new_anomalies_rows,
    }

    OUTPUT_JSON.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # Document CSV
    # --------------------------------------------------------

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
            "introduced_by_pattern_b",
            "resolved_by_pattern_b",
            "status",
        ]

        writer = csv.DictWriter(
            f,
            fieldnames=fields,
        )

        writer.writeheader()

        for row in document_results:
            writer.writerow(row)

    # --------------------------------------------------------
    # New anomalies CSV
    # --------------------------------------------------------

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

        for row in new_anomalies_rows:
            writer.writerow(row)

    # --------------------------------------------------------
    # Console
    # --------------------------------------------------------

    print("=" * 84)
    print("SGCE - PATTERN B GLOBAL DIFFERENTIAL POST-VALIDATION")
    print("=" * 84)

    print(
        f"AVANT Pattern B              : "
        f"{before_dir}"
    )

    print(
        f"APRES Pattern B              : "
        f"{after_dir}"
    )

    print()

    print(
        f"Documents vérifiés           : "
        f"{len(document_results)}"
    )

    print(
        f"PASS                         : "
        f"{pass_docs}"
    )

    print(
        f"FAIL                         : "
        f"{fail_docs}"
    )

    print()

    print(
        f"Documents attendus modifiés  : "
        f"{len(expected_modified_docs)}"
    )

    print(
        f"Documents réellement modifiés: "
        f"{clinical_content_changed}"
    )

    print(
        f"Modifications inattendues    : "
        f"{unexpected_changes}"
    )

    print(
        f"Corrections attendues absentes: "
        f"{missing_expected_changes}"
    )

    print()

    print(
        f"Opérations attendues         : "
        f"{operations_expected}"
    )

    print(
        f"Opérations PASS              : "
        f"{operations_pass}"
    )

    print(
        f"Opérations FAIL              : "
        f"{operations_fail}"
    )

    print()

    print(
        f"Anomalies pré-existantes     : "
        f"{total_preexisting}"
    )

    print(
        f"Nouvelles anomalies Pattern B: "
        f"{total_introduced}"
    )

    print(
        f"Anomalies résolues Pattern B : "
        f"{total_resolved}"
    )

    print()

    print(
        f"Docs manquants APRES         : "
        f"{len(missing_after)}"
    )

    print(
        f"Docs supplémentaires APRES   : "
        f"{len(extra_after)}"
    )

    print()

    print(
        f"Signatures TRACE chargées    : "
        f"{len(signatures)}"
    )

    print()

    print(
        f"STATUT FINAL PATTERN B       : "
        f"{'PASS' if final_pass else 'FAIL'}"
    )

    print()

    print(
        f"Rapport JSON                 : "
        f"{OUTPUT_JSON}"
    )

    print(
        f"Rapport documents CSV        : "
        f"{OUTPUT_CSV}"
    )

    print(
        f"Nouvelles anomalies CSV      : "
        f"{ANOMALIES_CSV}"
    )

    print()

    print(
        "Aucune donnée clinique n'a été modifiée "
        "par ce post-validateur."
    )


if __name__ == "__main__":
    main()
