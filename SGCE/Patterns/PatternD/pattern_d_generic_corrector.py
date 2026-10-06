# -*- coding: utf-8 -*-
"""
pattern_d_generic_corrector.py
==============================

SGCE — Pattern D Generic Safe Corrector

Input:
  PatternD/pattern_d_validation/pattern_d_validation_report.json

Clinical input:
  PatternC/pattern_c_corrected

Supported safe actions:
- RELINK
- RETYPE_ENTITY
- REMOVE_INVALID_RELATION

All AMBIGUOUS / protected cases are skipped.

Original clinical JSONs are NEVER modified.
Corrected copies are written to:
  PatternD/pattern_d_corrected
"""

import copy
import json
from collections import Counter
from pathlib import Path


# ============================================================
# 1. PATHS
# ============================================================

PATTERN_D_DIR = Path(__file__).resolve().parent
PATTERNS_DIR = PATTERN_D_DIR.parent
SGCE_DIR = PATTERNS_DIR.parent
BASE_DIR = SGCE_DIR.parent

PATTERN_C_DIR = PATTERNS_DIR / "PatternC"
INPUT_DIR = PATTERN_C_DIR / "corrected"

VALIDATION_REPORT = PATTERN_D_DIR / "validation" / "pattern_d_validation_report.json"

OUTPUT_DIR = PATTERN_D_DIR / "corrected"
REPORT_PATH = OUTPUT_DIR / "pattern_d_correction_report.json"


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


# ============================================================
# 3. ENTITY TYPE UPDATE
# ============================================================

def update_entity_type_in_place(entity, new_type):
    """
    Keep all known type aliases synchronized.
    """
    changed = False

    for key in ("categorie", "type", "entity_type", "type_entite"):
        if key in entity:
            if entity.get(key) != new_type:
                entity[key] = new_type
                changed = True

    # Ensure at least the two main aliases exist.
    if "categorie" not in entity:
        entity["categorie"] = new_type
        changed = True

    if "type" not in entity:
        entity["type"] = new_type
        changed = True

    entity["_sgce_corrected"] = True
    entity["_sgce_pattern"] = "D"
    entity["_sgce_operation"] = "RETYPE_ENTITY"

    return changed


def retype_entity_everywhere(doc, eid, new_type):
    """
    Update both global_entities and page entities if both exist.
    """
    occurrences = 0

    if isinstance(doc.get("global_entities"), list):
        for e in doc["global_entities"]:
            if str(entity_id(e)) == str(eid):
                update_entity_type_in_place(e, new_type)
                occurrences += 1

    for page in doc.get("pages", []) or []:
        if isinstance(page.get("entities"), list):
            for e in page["entities"]:
                if str(entity_id(e)) == str(eid):
                    update_entity_type_in_place(e, new_type)
                    occurrences += 1

    return occurrences


# ============================================================
# 4. RELINK
# ============================================================

def replace_relation_endpoint_in_place(relation, role, new_entity_id):
    changed = False

    if role == "SOURCE":
        aliases = (
            "identifiant_entite_sujet",
            "from_id",
            "subject_id",
        )
    else:
        aliases = (
            "identifiant_entite_objet",
            "to_id",
            "object_id",
        )

    found_any = False

    for key in aliases:
        if key in relation:
            found_any = True
            if str(relation.get(key)) != str(new_entity_id):
                relation[key] = new_entity_id
                changed = True

    # Ensure canonical field exists.
    canonical = (
        "identifiant_entite_sujet"
        if role == "SOURCE"
        else "identifiant_entite_objet"
    )

    if canonical not in relation:
        relation[canonical] = new_entity_id
        changed = True

    relation["_sgce_corrected"] = True
    relation["_sgce_pattern"] = "D"
    relation["_sgce_operation"] = "RELINK"

    return changed or found_any


def relink_relation_everywhere(doc, rid, role, new_entity_id):
    occurrences = 0

    if isinstance(doc.get("global_relations"), list):
        for r in doc["global_relations"]:
            if str(relation_id(r)) == str(rid):
                replace_relation_endpoint_in_place(
                    r,
                    role,
                    new_entity_id,
                )
                occurrences += 1

    for page in doc.get("pages", []) or []:
        if isinstance(page.get("relations"), list):
            for r in page["relations"]:
                if str(relation_id(r)) == str(rid):
                    replace_relation_endpoint_in_place(
                        r,
                        role,
                        new_entity_id,
                    )
                    occurrences += 1

    return occurrences


# ============================================================
# 5. REMOVE INVALID RELATION
# ============================================================

def remove_relation_everywhere(doc, rid):
    removed = 0

    if isinstance(doc.get("global_relations"), list):
        before = len(doc["global_relations"])

        doc["global_relations"] = [
            r
            for r in doc["global_relations"]
            if str(relation_id(r)) != str(rid)
        ]

        removed += before - len(doc["global_relations"])

    for page in doc.get("pages", []) or []:
        if isinstance(page.get("relations"), list):
            before = len(page["relations"])

            page["relations"] = [
                r
                for r in page["relations"]
                if str(relation_id(r)) != str(rid)
            ]

            removed += before - len(page["relations"])

    return removed


# ============================================================
# 6. APPLY ONE VALIDATED CANDIDATE
# ============================================================

def apply_candidate(doc, candidate):
    status = candidate.get("validation_status")
    action = candidate.get("recommended_future_action")
    details = candidate.get("action_details") or {}
    relation_info = candidate.get("relation") or {}

    rid = relation_info.get("relation_id")

    # --------------------------------------------------------
    # Protected
    # --------------------------------------------------------

    if action not in {
        "RELINK",
        "RETYPE_ENTITY",
        "REMOVE_INVALID_RELATION",
    }:
        return {
            "operation": "SKIP",
            "modified": False,
            "reason": status or "PROTECTED",
        }

    # --------------------------------------------------------
    # RELINK
    # --------------------------------------------------------

    if action == "RELINK":
        role = details.get("role")
        old_entity_id = details.get("old_entity_id")
        new_entity_id = details.get("new_entity_id")

        if role not in {"SOURCE", "TARGET"}:
            return {
                "operation": "SKIP",
                "modified": False,
                "reason": "INVALID_RELINK_ROLE",
            }

        if not rid or not new_entity_id:
            return {
                "operation": "SKIP",
                "modified": False,
                "reason": "INCOMPLETE_RELINK_DATA",
            }

        relation = find_relation(doc, rid)
        replacement = find_entity(doc, new_entity_id)

        if relation is None:
            return {
                "operation": "SKIP",
                "modified": False,
                "reason": "RELATION_NOT_FOUND",
            }

        if replacement is None:
            return {
                "operation": "SKIP",
                "modified": False,
                "reason": "REPLACEMENT_ENTITY_NOT_FOUND",
            }

        current_endpoint = (
            relation_source(relation)
            if role == "SOURCE"
            else relation_target(relation)
        )

        # Safety: the endpoint must still be the one validated.
        if (
            old_entity_id
            and str(current_endpoint) != str(old_entity_id)
        ):
            return {
                "operation": "SKIP",
                "modified": False,
                "reason": "RELATION_ENDPOINT_CHANGED_SINCE_VALIDATION",
            }

        occurrences = relink_relation_everywhere(
            doc,
            rid,
            role,
            new_entity_id,
        )

        if occurrences == 0:
            return {
                "operation": "SKIP",
                "modified": False,
                "reason": "RELINK_FAILED",
            }

        return {
            "operation": "RELINK",
            "modified": True,
            "relation_id": rid,
            "role": role,
            "old_entity_id": old_entity_id,
            "new_entity_id": new_entity_id,
            "new_entity_type": entity_type(replacement),
            "occurrences_updated": occurrences,
        }

    # --------------------------------------------------------
    # RETYPE ENTITY
    # --------------------------------------------------------

    if action == "RETYPE_ENTITY":
        eid = details.get("entity_id")
        old_type = details.get("old_type")
        new_type = details.get("new_type")

        if not eid or not new_type:
            return {
                "operation": "SKIP",
                "modified": False,
                "reason": "INCOMPLETE_RETYPE_DATA",
            }

        entity = find_entity(doc, eid)

        if entity is None:
            return {
                "operation": "SKIP",
                "modified": False,
                "reason": "ENTITY_NOT_FOUND",
            }

        # Safety: current type must still be the validated old type.
        if old_type and entity_type(entity) != old_type:
            return {
                "operation": "SKIP",
                "modified": False,
                "reason": "ENTITY_TYPE_CHANGED_SINCE_VALIDATION",
            }

        occurrences = retype_entity_everywhere(
            doc,
            eid,
            new_type,
        )

        if occurrences == 0:
            return {
                "operation": "SKIP",
                "modified": False,
                "reason": "RETYPE_FAILED",
            }

        return {
            "operation": "RETYPE_ENTITY",
            "modified": True,
            "entity_id": eid,
            "old_type": old_type,
            "new_type": new_type,
            "occurrences_updated": occurrences,
        }

    # --------------------------------------------------------
    # REMOVE INVALID RELATION
    # --------------------------------------------------------

    if action == "REMOVE_INVALID_RELATION":
        remove_rid = (
            details.get("relation_id")
            or rid
        )

        if not remove_rid:
            return {
                "operation": "SKIP",
                "modified": False,
                "reason": "MISSING_RELATION_ID",
            }

        relation = find_relation(
            doc,
            remove_rid,
        )

        if relation is None:
            return {
                "operation": "SKIP",
                "modified": False,
                "reason": "RELATION_NOT_FOUND",
            }

        removed = remove_relation_everywhere(
            doc,
            remove_rid,
        )

        if removed == 0:
            return {
                "operation": "SKIP",
                "modified": False,
                "reason": "RELATION_REMOVAL_FAILED",
            }

        return {
            "operation": "REMOVE_INVALID_RELATION",
            "modified": True,
            "relation_id": remove_rid,
            "relation_type": relation_info.get("relation_type"),
            "removed_occurrences": removed,
        }

    return {
        "operation": "SKIP",
        "modified": False,
        "reason": "UNKNOWN_ACTION",
    }


# ============================================================
# 7. MAIN
# ============================================================

def main():
    if not INPUT_DIR.exists():
        raise FileNotFoundError(
            f"Entrée Pattern D introuvable : {INPUT_DIR}"
        )

    if not VALIDATION_REPORT.exists():
        raise FileNotFoundError(
            f"Rapport validation Pattern D introuvable : "
            f"{VALIDATION_REPORT}"
        )

    validation = load_json(
        VALIDATION_REPORT
    )

    validated = validation.get(
        "validated_candidates",
        []
    )

    by_document = {}

    for candidate in validated:
        by_document.setdefault(
            candidate.get("document"),
            []
        ).append(candidate)

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
        INPUT_DIR.glob("*.json")
    ):
        if path.name == "pattern_c_correction_report.json":
            continue

        try:
            original = load_json(path)

            if not is_clinical_document(original):
                nonclinical.append(path.name)
                continue

            doc = copy.deepcopy(
                original
            )

            document_modified = False

            for candidate in by_document.get(
                path.name,
                []
            ):
                try:
                    result = apply_candidate(
                        doc,
                        candidate,
                    )

                    result["document"] = path.name
                    result["candidate_id"] = candidate.get(
                        "candidate_id"
                    )
                    result["validation_status"] = candidate.get(
                        "validation_status"
                    )

                    operations.append(
                        result
                    )

                    if result.get("modified"):
                        document_modified = True

                except Exception as exc:
                    errors.append({
                        "document": path.name,
                        "candidate_id": candidate.get(
                            "candidate_id"
                        ),
                        "error": str(exc),
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
                "document": path.name,
                "error": str(exc),
            })

    applied = [
        op
        for op in operations
        if op.get("modified") is True
    ]

    operation_counts = Counter(
        op.get("operation")
        for op in applied
    )

    skip_counts = Counter(
        op.get("reason")
        for op in operations
        if not op.get("modified")
    )

    report = {
        "pattern": "D",
        "mode": "GENERIC_SAFE_CORRECTOR",
        "input_directory": str(INPUT_DIR),
        "validation_report": str(VALIDATION_REPORT),
        "output_directory": str(OUTPUT_DIR),

        "summary": {
            "validated_candidates": len(validated),

            "operations_applied":
                len(applied),

            "relink_applied":
                operation_counts.get(
                    "RELINK",
                    0,
                ),

            "retype_entity_applied":
                operation_counts.get(
                    "RETYPE_ENTITY",
                    0,
                ),

            "remove_invalid_relation_applied":
                operation_counts.get(
                    "REMOVE_INVALID_RELATION",
                    0,
                ),

            "documents_copied":
                copied,

            "documents_modified":
                modified_documents,

            "nonclinical_json_skipped":
                len(nonclinical),

            "errors":
                len(errors),
        },

        "skip_reasons":
            dict(skip_counts),

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

    print("=" * 88)
    print("SGCE - PATTERN D GENERIC CORRECTION")
    print("=" * 88)

    print(
        f"Entrée                         : "
        f"{INPUT_DIR}"
    )

    print(
        f"Validation                     : "
        f"{VALIDATION_REPORT}"
    )

    print(
        f"Sortie                         : "
        f"{OUTPUT_DIR}"
    )

    print()

    print(
        f"Candidats validés              : "
        f"{len(validated)}"
    )

    print(
        f"Opérations appliquées          : "
        f"{len(applied)}"
    )

    print(
        f"RELINK appliqués               : "
        f"{operation_counts.get('RELINK', 0)}"
    )

    print(
        f"RETYPE_ENTITY appliqués        : "
        f"{operation_counts.get('RETYPE_ENTITY', 0)}"
    )

    print(
        f"REMOVE_INVALID_RELATION        : "
        f"{operation_counts.get('REMOVE_INVALID_RELATION', 0)}"
    )

    print()

    print(
        f"Documents copiés               : "
        f"{copied}"
    )

    print(
        f"Documents modifiés             : "
        f"{modified_documents}"
    )

    print(
        f"JSON non cliniques ignorés     : "
        f"{len(nonclinical)}"
    )

    print(
        f"Erreurs                        : "
        f"{len(errors)}"
    )

    print()

    if skip_counts:
        print("Raisons SKIP :")

        for reason, count in (
            skip_counts.most_common()
        ):
            print(
                f"  {str(reason):<45}: {count}"
            )

        print()

    print(
        f"Rapport                        : "
        f"{REPORT_PATH}"
    )

    print()

    print(
        "Les fichiers sources n'ont pas été modifiés."
    )


if __name__ == "__main__":
    main()
