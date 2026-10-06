# -*- coding: utf-8 -*-
"""
pattern_c_generic_corrector.py
==============================

SGCE — Pattern C Generic Safe Corrector

Input:
  PatternC/pattern_c_validation/pattern_c_validation_report.json

Applies ONLY:
  CONFIRMED_REIFIED_RELATION
  + recommended_future_action == REPLACE_ENTITY_WITH_RELATION

Safety rules:
1) The reified entity must still exist.
2) It must not be referenced by any existing relation.
3) The target relation must not already exist.
4) The validated source and target entities must exist.
5) Only then:
   - remove the reified entity
   - create the validated TRACE-Sepsis relation
6) All other cases are SKIP.

This script is reusable on future datasets.
Original source files are never modified.
"""

import copy
import json
import re
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

INPUT_DIR = PATTERN_B2_DIR / "corrected"
VALIDATION_REPORT = PATTERN_C_DIR / "validation" / "pattern_c_validation_report.json"

OUTPUT_DIR = PATTERN_C_DIR / "corrected"
REPORT_PATH = OUTPUT_DIR / "pattern_c_correction_report.json"


REL_ID_RE = re.compile(
    r"^P(?P<page>\d+)_R(?P<num>\d+)$"
)


# ============================================================
# 2. HELPERS
# ============================================================

def load_json(path):
    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


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


def entity_page(e):
    if e.get("page") is not None:
        return e.get("page")
    return e.get("page_number")


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
    if isinstance(
        doc.get("global_entities"),
        list,
    ):
        return doc["global_entities"]

    out = []

    for page in doc.get(
        "pages",
        [],
    ) or []:
        out.extend(
            page.get(
                "entities",
                [],
            )
            or []
        )

    return out


def get_relations(doc):
    if isinstance(
        doc.get("global_relations"),
        list,
    ):
        return doc["global_relations"]

    out = []

    for page in doc.get(
        "pages",
        [],
    ) or []:
        out.extend(
            page.get(
                "relations",
                [],
            )
            or []
        )

    return out


def find_entity(doc, eid):
    for e in get_entities(doc):
        if str(entity_id(e)) == str(eid):
            return e
    return None


def find_page(doc, page_number):
    for page in doc.get(
        "pages",
        [],
    ) or []:

        current = page.get("page")

        if current is None:
            current = page.get(
                "page_number"
            )

        if str(current) == str(
            page_number
        ):
            return page

    return None


# ============================================================
# 3. RELATION IDS
# ============================================================

def next_relation_id(
    doc,
    page_number,
):
    max_num = 0

    for relation in get_relations(
        doc
    ):
        rid = relation_id(
            relation
        )

        if not rid:
            continue

        match = REL_ID_RE.match(
            str(rid)
        )

        if (
            match
            and str(
                match.group("page")
            )
            == str(page_number)
        ):
            max_num = max(
                max_num,
                int(
                    match.group("num")
                ),
            )

    return (
        f"P{page_number}_R"
        f"{max_num + 1:03d}"
    )


# ============================================================
# 4. ENTITY REMOVAL
# ============================================================

def remove_entity_by_id(
    doc,
    eid,
):
    removed = 0

    if isinstance(
        doc.get("global_entities"),
        list,
    ):
        before = len(
            doc["global_entities"]
        )

        doc["global_entities"] = [
            e
            for e in doc[
                "global_entities"
            ]
            if str(
                entity_id(e)
            )
            != str(eid)
        ]

        removed += (
            before
            - len(
                doc["global_entities"]
            )
        )

    for page in doc.get(
        "pages",
        [],
    ) or []:

        if isinstance(
            page.get("entities"),
            list,
        ):
            before = len(
                page["entities"]
            )

            page["entities"] = [
                e
                for e in page[
                    "entities"
                ]
                if str(
                    entity_id(e)
                )
                != str(eid)
            ]

            removed += (
                before
                - len(
                    page["entities"]
                )
            )

    return removed


# ============================================================
# 5. RELATION CREATION
# ============================================================

def relation_exists(
    doc,
    rtype,
    src_id,
    tgt_id,
):
    return any(
        relation_type(r) == rtype
        and str(
            relation_source(r)
        )
        == str(src_id)
        and str(
            relation_target(r)
        )
        == str(tgt_id)
        for r in get_relations(doc)
    )


def entity_is_referenced(
    doc,
    eid,
):
    references = []

    for r in get_relations(
        doc
    ):
        if (
            str(
                relation_source(r)
            )
            == str(eid)
            or str(
                relation_target(r)
            )
            == str(eid)
        ):
            references.append({
                "relation_id":
                    relation_id(r),

                "relation_type":
                    relation_type(r),

                "source":
                    relation_source(r),

                "target":
                    relation_target(r),
            })

    return references


def build_relation(
    rid,
    relation_name,
    source_id,
    target_id,
    page,
):
    return {
        "identifiant_relation":
            rid,

        "type_relation":
            relation_name,

        "identifiant_entite_sujet":
            source_id,

        "identifiant_entite_objet":
            target_id,

        "page":
            page,

        # aliases compatibility
        "relation":
            relation_name,

        "from_id":
            source_id,

        "to_id":
            target_id,

        "type":
            relation_name,

        # SGCE provenance
        "_sgce_created":
            True,

        "_sgce_pattern":
            "C",

        "_sgce_operation":
            "REPLACE_ENTITY_WITH_RELATION",
    }


def add_relation(
    doc,
    relation,
):
    rid = relation_id(
        relation
    )

    if isinstance(
        doc.get("global_relations"),
        list,
    ):
        if not any(
            relation_id(r) == rid
            for r in doc[
                "global_relations"
            ]
        ):
            doc[
                "global_relations"
            ].append(
                copy.deepcopy(
                    relation
                )
            )

    page = find_page(
        doc,
        relation.get("page"),
    )

    if page is not None:
        page.setdefault(
            "relations",
            [],
        )

        if not any(
            relation_id(r) == rid
            for r in page[
                "relations"
            ]
        ):
            page[
                "relations"
            ].append(
                copy.deepcopy(
                    relation
                )
            )


# ============================================================
# 6. APPLY ONE CANDIDATE
# ============================================================

def apply_candidate(
    doc,
    candidate,
):
    status = candidate.get(
        "validation_status"
    )

    action = candidate.get(
        "recommended_future_action"
    )

    if (
        status
        != "CONFIRMED_REIFIED_RELATION"
        or action
        != "REPLACE_ENTITY_WITH_RELATION"
    ):
        return {
            "operation":
                "SKIP",

            "modified":
                False,

            "reason":
                status,
        }

    reified = (
        candidate.get(
            "reified_entity"
        )
        or {}
    )

    source = (
        candidate.get(
            "validated_source_entity"
        )
        or {}
    )

    target = (
        candidate.get(
            "validated_target_entity"
        )
        or {}
    )

    relation_name = candidate.get(
        "validated_relation"
    )

    reified_id = reified.get(
        "id"
    )

    source_id = source.get(
        "id"
    )

    target_id = target.get(
        "id"
    )

    # --------------------------------------------------------
    # Required fields
    # --------------------------------------------------------

    if not all([
        reified_id,
        source_id,
        target_id,
        relation_name,
    ]):
        return {
            "operation":
                "SKIP",

            "modified":
                False,

            "reason":
                "INCOMPLETE_VALIDATED_DATA",
        }

    # --------------------------------------------------------
    # Entities must still exist
    # --------------------------------------------------------

    reified_entity = find_entity(
        doc,
        reified_id,
    )

    source_entity = find_entity(
        doc,
        source_id,
    )

    target_entity = find_entity(
        doc,
        target_id,
    )

    if reified_entity is None:
        return {
            "operation":
                "SKIP",

            "modified":
                False,

            "reason":
                "REIFIED_ENTITY_NOT_FOUND",
        }

    if source_entity is None:
        return {
            "operation":
                "SKIP",

            "modified":
                False,

            "reason":
                "SOURCE_ENTITY_NOT_FOUND",
        }

    if target_entity is None:
        return {
            "operation":
                "SKIP",

            "modified":
                False,

            "reason":
                "TARGET_ENTITY_NOT_FOUND",
        }

    # --------------------------------------------------------
    # Relation must not already exist
    # --------------------------------------------------------

    if relation_exists(
        doc,
        relation_name,
        source_id,
        target_id,
    ):
        return {
            "operation":
                "SKIP",

            "modified":
                False,

            "reason":
                "RELATION_ALREADY_EXISTS",
        }

    # --------------------------------------------------------
    # Reified entity must be structurally isolated
    # --------------------------------------------------------

    references = entity_is_referenced(
        doc,
        reified_id,
    )

    if references:
        return {
            "operation":
                "SKIP",

            "modified":
                False,

            "reason":
                "REIFIED_ENTITY_HAS_EXISTING_RELATIONS",

            "existing_relation_references":
                references,
        }

    # --------------------------------------------------------
    # Determine page
    # --------------------------------------------------------

    page = (
        entity_page(
            reified_entity
        )
        or entity_page(
            source_entity
        )
        or entity_page(
            target_entity
        )
        or 1
    )

    # --------------------------------------------------------
    # Remove reified entity
    # --------------------------------------------------------

    removed_occurrences = (
        remove_entity_by_id(
            doc,
            reified_id,
        )
    )

    if (
        removed_occurrences
        == 0
    ):
        return {
            "operation":
                "SKIP",

            "modified":
                False,

            "reason":
                "ENTITY_REMOVAL_FAILED",
        }

    # --------------------------------------------------------
    # Create relation
    # --------------------------------------------------------

    new_relation_id = (
        next_relation_id(
            doc,
            page,
        )
    )

    new_relation = build_relation(
        new_relation_id,
        relation_name,
        source_id,
        target_id,
        page,
    )

    add_relation(
        doc,
        new_relation,
    )

    return {
        "operation":
            "REPLACE_ENTITY_WITH_RELATION",

        "modified":
            True,

        "removed_entity_id":
            reified_id,

        "removed_entity_type":
            entity_type(
                reified_entity
            ),

        "removed_entity_text":
            reified.get(
                "text",
                "",
            ),

        "removed_entity_occurrences":
            removed_occurrences,

        "created_relation_id":
            new_relation_id,

        "created_relation_type":
            relation_name,

        "source_entity_id":
            source_id,

        "target_entity_id":
            target_id,

        "page":
            page,
    }


# ============================================================
# 7. MAIN
# ============================================================

def main():

    if not INPUT_DIR.exists():
        raise FileNotFoundError(
            f"Entrée Pattern C introuvable : "
            f"{INPUT_DIR}"
        )

    if not VALIDATION_REPORT.exists():
        raise FileNotFoundError(
            f"Rapport validation Pattern C introuvable : "
            f"{VALIDATION_REPORT}"
        )

    validation = load_json(
        VALIDATION_REPORT
    )

    validated = validation.get(
        "validated_candidates",
        [],
    )

    by_document = {}

    for candidate in validated:
        by_document.setdefault(
            candidate.get(
                "document"
            ),
            [],
        ).append(
            candidate
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    operations = []

    errors = []

    nonclinical = []

    copied = 0

    modified_documents = 0

    for path in sorted(
        INPUT_DIR.glob(
            "*.json"
        )
    ):

        try:
            original = load_json(
                path
            )

            if not is_clinical_document(
                original
            ):
                nonclinical.append(
                    path.name
                )
                continue

            doc = copy.deepcopy(
                original
            )

            document_modified = False

            for candidate in by_document.get(
                path.name,
                [],
            ):
                try:
                    result = apply_candidate(
                        doc,
                        candidate,
                    )

                    result[
                        "document"
                    ] = path.name

                    result[
                        "candidate_id"
                    ] = candidate.get(
                        "candidate_id"
                    )

                    operations.append(
                        result
                    )

                    if result.get(
                        "modified"
                    ):
                        document_modified = True

                except Exception as exc:
                    errors.append({
                        "document":
                            path.name,

                        "candidate_id":
                            candidate.get(
                                "candidate_id"
                            ),

                        "error":
                            str(exc),
                    })

            output_path = (
                OUTPUT_DIR
                / path.name
            )

            output_path.write_text(
                json.dumps(
                    doc,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            copied += 1

            if document_modified:
                modified_documents += 1

        except Exception as exc:
            errors.append({
                "document":
                    path.name,

                "error":
                    str(exc),
            })

    applied = [
        op
        for op in operations
        if op.get("modified") is True
    ]

    authorized = [
        cand for cand in validated
        if cand.get("validation_status") == "CONFIRMED_REIFIED_RELATION"
        and cand.get("recommended_future_action") == "REPLACE_ENTITY_WITH_RELATION"
    ]

    reason_counts = Counter(
        op.get(
            "reason",
            "APPLIED",
        )
        if not op.get(
            "modified"
        )
        else "APPLIED"
        for op in operations
    )

    report = {
        "pattern":
            "C",

        "mode":
            "GENERIC_SAFE_CORRECTOR",

        "input_directory":
            str(
                INPUT_DIR
            ),

        "validation_report":
            str(
                VALIDATION_REPORT
            ),

        "output_directory":
            str(
                OUTPUT_DIR
            ),

        "summary": {
            "validated_candidates":
                len(
                    validated
                ),

            "operations_authorized":
                len(authorized),

            "operations_applied":
                len(
                    applied
                ),

            "entities_removed":
                len(
                    applied
                ),

            "relations_created":
                len(
                    applied
                ),

            "documents_copied":
                copied,

            "documents_modified":
                modified_documents,

            "nonclinical_json_skipped":
                len(
                    nonclinical
                ),

            "errors":
                len(
                    errors
                ),
        },

        "skip_reasons":
            dict(
                reason_counts
            ),

        "operations":
            operations,

        "errors":
            errors,
    }

    REPORT_PATH.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "="
        * 82
    )

    print(
        "SGCE - PATTERN C GENERIC CORRECTION"
    )

    print(
        "="
        * 82
    )

    print(
        f"Entrée                    : "
        f"{INPUT_DIR}"
    )

    print(
        f"Validation                : "
        f"{VALIDATION_REPORT}"
    )

    print(
        f"Sortie                    : "
        f"{OUTPUT_DIR}"
    )

    print()

    print(
        f"Candidats validés         : "
        f"{len(validated)}"
    )

    print(
        f"Opérations autorisées     : "
        f"{len(authorized)}"
    )

    print(
        f"Opérations appliquées     : "
        f"{len(applied)}"
    )

    print(
        f"Entités réifiées supprimées: "
        f"{len(applied)}"
    )

    print(
        f"Relations créées          : "
        f"{len(applied)}"
    )

    print()

    print(
        f"Documents copiés          : "
        f"{copied}"
    )

    print(
        f"Documents modifiés        : "
        f"{modified_documents}"
    )

    print(
        f"JSON non cliniques ignorés: "
        f"{len(nonclinical)}"
    )

    print(
        f"Erreurs                   : "
        f"{len(errors)}"
    )

    print()

    print(
        "Raisons SKIP :"
    )

    for reason, count in (
        reason_counts.most_common()
    ):
        if reason == "APPLIED":
            continue

        print(
            f"  {reason:<45}: {count}"
        )

    print()

    print(
        f"Rapport                   : "
        f"{REPORT_PATH}"
    )

    print()

    print(
        "Les fichiers sources n'ont pas été modifiés."
    )


if __name__ == "__main__":
    main()
