# -*- coding: utf-8 -*-
"""
pattern_a6_differential_post_validator.py
=========================================

SGCE — Pattern A6 Differential Post-Validation

Compare:
- BEFORE A6 : PatternA5/pattern_a5_corrected
- AFTER A6  : PatternA6/pattern_a6_corrected

A6:
DONNEE_PATIENT --presente_symptome--> SYMPTOME

Current expected state:
- 13 ALREADY_CORRECT
- 0 LINK
- 0 SPLIT
- 13 SKIP
- 0 clinical modification

Goal:
Verify that A6 introduced no structural anomaly and that all clinical
documents were preserved correctly.
"""

import json
from collections import Counter
from pathlib import Path


# ============================================================
# 1. PATHS
# ============================================================

PATTERN_A6_DIR = Path(__file__).resolve().parent
PATTERN_A_DIR = PATTERN_A6_DIR.parent
PATTERNS_DIR = PATTERN_A_DIR.parent
SGCE_DIR = PATTERNS_DIR.parent
BASE_DIR = SGCE_DIR.parent
PATTERN_A5_DIR = PATTERN_A_DIR / "PatternA5"

BEFORE_DIR_CANDIDATES = [
    PATTERN_A5_DIR / "corrected",
]

AFTER_DIR = PATTERN_A6_DIR / "corrected"
CORRECTION_REPORT = AFTER_DIR / "pattern_a6_correction_report.json"

OUTPUT_DIR = PATTERN_A6_DIR / "post_validation"
OUTPUT_JSON = OUTPUT_DIR / "pattern_a6_post_validation_report.json"

SOURCE_TYPE = "DONNEE_PATIENT"
TARGET_TYPE = "SYMPTOME"
RELATION_TYPE = "presente_symptome"


# ============================================================
# 2. HELPERS
# ============================================================

def resolve_before_dir():
    for p in BEFORE_DIR_CANDIDATES:
        if p.exists() and any(p.glob("*.json")):
            return p

    raise FileNotFoundError(
        "Dossier AVANT A6 introuvable."
    )


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


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


def is_clinical_document(doc):
    return (
        isinstance(doc, dict)
        and (
            isinstance(
                doc.get("global_entities"),
                list,
            )
            or isinstance(
                doc.get("pages"),
                list,
            )
        )
    )


# ============================================================
# 3. STRUCTURAL AUDIT
# ============================================================

def collect_structural_anomalies(doc):
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
    # Duplicate entity IDs
    # --------------------------------------------------------

    for eid, count in entity_counts.items():
        if count > 1:
            anomalies.append(
                (
                    "DUPLICATE_ENTITY_ID",
                    str(eid),
                    count,
                )
            )

    # --------------------------------------------------------
    # Duplicate relation IDs
    # --------------------------------------------------------

    for rid, count in relation_counts.items():
        if count > 1:
            anomalies.append(
                (
                    "DUPLICATE_RELATION_ID",
                    str(rid),
                    count,
                )
            )

    entity_map = {
        entity_id(e): e
        for e in entities
        if entity_id(e)
    }

    # --------------------------------------------------------
    # Orphans + A6 relation domain/range
    # --------------------------------------------------------

    for r in relations:

        rid = relation_id(r)
        src = relation_source(r)
        tgt = relation_target(r)

        if src and src not in entity_map:
            anomalies.append(
                (
                    "ORPHAN_SOURCE",
                    str(rid),
                    str(src),
                )
            )

        if tgt and tgt not in entity_map:
            anomalies.append(
                (
                    "ORPHAN_TARGET",
                    str(rid),
                    str(tgt),
                )
            )

        if relation_type(r) == RELATION_TYPE:

            src_ent = entity_map.get(src)
            tgt_ent = entity_map.get(tgt)

            if (
                src_ent is not None
                and entity_type(src_ent)
                != SOURCE_TYPE
            ):
                anomalies.append(
                    (
                        "INVALID_A6_SOURCE_TYPE",
                        str(rid),
                        entity_type(src_ent),
                    )
                )

            if (
                tgt_ent is not None
                and entity_type(tgt_ent)
                != TARGET_TYPE
            ):
                anomalies.append(
                    (
                        "INVALID_A6_TARGET_TYPE",
                        str(rid),
                        entity_type(tgt_ent),
                    )
                )

    return set(anomalies)


# ============================================================
# 4. CLINICAL CONTENT SIGNATURE
# ============================================================

def clinical_signature(doc):
    """
    Canonical signature used to verify that A6 pass-through did not
    modify clinical content.

    The correction report itself is excluded because it is not a
    clinical document.
    """

    return json.dumps(
        doc,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


# ============================================================
# 5. MAIN
# ============================================================

def main():

    before_dir = resolve_before_dir()

    if not AFTER_DIR.exists():
        raise FileNotFoundError(
            f"Dossier APRES A6 introuvable : "
            f"{AFTER_DIR}"
        )

    if not CORRECTION_REPORT.exists():
        raise FileNotFoundError(
            f"Rapport correction A6 introuvable : "
            f"{CORRECTION_REPORT}"
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    correction_report = load_json(
        CORRECTION_REPORT
    )

    before_docs = {}
    after_docs = {}

    # --------------------------------------------------------
    # BEFORE
    # --------------------------------------------------------

    for path in sorted(
        before_dir.glob("*.json")
    ):
        try:
            doc = load_json(path)

            if is_clinical_document(doc):
                before_docs[path.name] = doc

        except Exception:
            pass

    # --------------------------------------------------------
    # AFTER
    # --------------------------------------------------------

    for path in sorted(
        AFTER_DIR.glob("*.json")
    ):

        if (
            path.name
            == CORRECTION_REPORT.name
        ):
            continue

        try:
            doc = load_json(path)

            if is_clinical_document(doc):
                after_docs[path.name] = doc

        except Exception:
            pass

    before_names = set(before_docs)
    after_names = set(after_docs)

    missing_after = sorted(
        before_names - after_names
    )

    missing_before = sorted(
        after_names - before_names
    )

    common_names = sorted(
        before_names & after_names
    )

    document_results = []

    total_preexisting = 0
    total_introduced = 0
    total_resolved = 0
    clinical_content_changed = 0

    for name in common_names:

        before = before_docs[name]
        after = after_docs[name]

        before_anomalies = (
            collect_structural_anomalies(
                before
            )
        )

        after_anomalies = (
            collect_structural_anomalies(
                after
            )
        )

        preexisting = (
            before_anomalies
            & after_anomalies
        )

        introduced = (
            after_anomalies
            - before_anomalies
        )

        resolved = (
            before_anomalies
            - after_anomalies
        )

        same_content = (
            clinical_signature(before)
            == clinical_signature(after)
        )

        if not same_content:
            clinical_content_changed += 1

        total_preexisting += len(
            preexisting
        )

        total_introduced += len(
            introduced
        )

        total_resolved += len(
            resolved
        )

        status = (
            "PASS"
            if (
                len(introduced) == 0
                and same_content
            )
            else "FAIL"
        )

        document_results.append({
            "document":
                name,

            "clinical_content_identical":
                same_content,

            "preexisting_anomalies":
                len(preexisting),

            "introduced_by_a6":
                len(introduced),

            "resolved_by_a6":
                len(resolved),

            "introduced_anomalies": [
                list(x)
                for x in sorted(
                    introduced,
                    key=str,
                )
            ],

            "status":
                status,
        })

    pass_docs = sum(
        1
        for d in document_results
        if d["status"] == "PASS"
    )

    fail_docs = (
        len(document_results)
        - pass_docs
    )

    summary_from_correction = (
        correction_report.get(
            "summary",
            {},
        )
    )

    operations_applied = (
        summary_from_correction.get(
            "operations_applied",
            0,
        )
    )

    link_count = (
        summary_from_correction.get(
            "link",
            0,
        )
    )

    split_count = (
        summary_from_correction.get(
            "split",
            0,
        )
    )

    skip_count = (
        summary_from_correction.get(
            "skip",
            0,
        )
    )

    # A6 current expected case:
    # zero clinical operations.
    unexpected_operations = (
        operations_applied != 0
        or link_count != 0
        or split_count != 0
    )

    final_pass = (
        fail_docs == 0
        and total_introduced == 0
        and clinical_content_changed == 0
        and not missing_before
        and not missing_after
        and not unexpected_operations
    )

    report = {
        "pattern":
            "A6",

        "validation_type":
            "DIFFERENTIAL_POST_VALIDATION",

        "before_directory":
            str(before_dir),

        "after_directory":
            str(AFTER_DIR),

        "correction_report":
            str(CORRECTION_REPORT),

        "summary": {
            "documents_verified":
                len(document_results),

            "documents_pass":
                pass_docs,

            "documents_fail":
                fail_docs,

            "operations_applied":
                operations_applied,

            "link":
                link_count,

            "split":
                split_count,

            "skip":
                skip_count,

            "clinical_documents_changed":
                clinical_content_changed,

            "preexisting_anomalies":
                total_preexisting,

            "introduced_by_a6":
                total_introduced,

            "resolved_by_a6":
                total_resolved,

            "missing_before_documents":
                len(missing_before),

            "missing_after_documents":
                len(missing_after),

            "final_status":
                (
                    "PASS"
                    if final_pass
                    else "FAIL"
                ),
        },

        "documents":
            document_results,

        "missing_before_documents":
            missing_before,

        "missing_after_documents":
            missing_after,
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
    print(
        "SGCE - PATTERN A6 "
        "DIFFERENTIAL POST-VALIDATION"
    )
    print("=" * 76)

    print(
        f"AVANT A6                : "
        f"{before_dir}"
    )

    print(
        f"APRES A6                : "
        f"{AFTER_DIR}"
    )

    print()

    print(
        f"Documents vérifiés      : "
        f"{len(document_results)}"
    )

    print(
        f"PASS                    : "
        f"{pass_docs}"
    )

    print(
        f"FAIL                    : "
        f"{fail_docs}"
    )

    print()

    print(
        f"Opérations appliquées   : "
        f"{operations_applied}"
    )

    print(
        f"LINK                    : "
        f"{link_count}"
    )

    print(
        f"SPLIT                   : "
        f"{split_count}"
    )

    print(
        f"SKIP                    : "
        f"{skip_count}"
    )

    print()

    print(
        f"Documents cliniques modifiés : "
        f"{clinical_content_changed}"
    )

    print()

    print(
        f"Anomalies pré-existantes: "
        f"{total_preexisting}"
    )

    print(
        f"Nouvelles anomalies A6  : "
        f"{total_introduced}"
    )

    print(
        f"Anomalies résolues A6   : "
        f"{total_resolved}"
    )

    print()

    print(
        f"Docs manquants APRES    : "
        f"{len(missing_after)}"
    )

    print(
        f"Docs manquants AVANT    : "
        f"{len(missing_before)}"
    )

    print()

    print(
        f"STATUT FINAL A6         : "
        f"{'PASS' if final_pass else 'FAIL'}"
    )

    print()

    print(
        f"Rapport                 : "
        f"{OUTPUT_JSON}"
    )


if __name__ == "__main__":
    main()
