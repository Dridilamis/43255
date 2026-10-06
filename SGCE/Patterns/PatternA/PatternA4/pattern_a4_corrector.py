# -*- coding: utf-8 -*-
"""
pattern_a4_auto_corrector.py
============================

SGCE â€” Pattern A4 Auto-Corrector

A4:
IMAGERIE_PROCEDURE
    --imagerie_objective_defaillance-->
DEFAILLANCE_ORGANE

DÃ©cisions:
- ALREADY_CORRECT -> SKIP
- MISSING_RELATION -> LINK
- CONFIRMED_PATTERN_A -> SPLIT non activÃ© ici
- AMBIGUOUS -> SKIP

Run actuel attendu:
- 1 LINK
- 0 SPLIT
"""

import copy
import json
import re
from collections import Counter
from pathlib import Path


# ============================================================
# 1. PATHS
# ============================================================

BASE_DIR = Path(
    r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM"
    r"\Reduction_hallucinations"
)

INPUT_DIR_CANDIDATES = [
    BASE_DIR / "PatternA3" / "pattern_a3_corrected",
    BASE_DIR / "PatternA2" / "pattern_a2_corrected",
]

VALIDATION_REPORT_CANDIDATES = [
    BASE_DIR / "PatternA4" / "pattern_a4_validation" / "pattern_a4_validation_report.json",
    BASE_DIR / "pattern_a4_validation" / "pattern_a4_validation_report.json",
]

OUTPUT_DIR = BASE_DIR / "PatternA4" / "pattern_a4_corrected"
CORRECTION_REPORT = OUTPUT_DIR / "pattern_a4_correction_report.json"

SOURCE_TYPE = "IMAGERIE_PROCEDURE"
TARGET_TYPE = "DEFAILLANCE_ORGANE"
RELATION_TYPE = "imagerie_objective_defaillance"


# ============================================================
# 2. HELPERS
# ============================================================

def resolve_input_dir():
    for p in INPUT_DIR_CANDIDATES:
        if p.exists() and any(p.glob("*.json")):
            return p
    raise FileNotFoundError("Aucun dossier JSON clinique trouvÃ©.")


def resolve_validation_report():
    for p in VALIDATION_REPORT_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError(
        "Rapport de validation A4 introuvable.\n"
        + "\n".join(f"- {p}" for p in VALIDATION_REPORT_CANDIDATES)
    )


def entity_id(e):
    return e.get("identifiant_entite") or e.get("id") or e.get("entity_id")


def entity_type(e):
    return e.get("categorie") or e.get("type") or ""


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


def find_page(doc, page_number):
    for page in doc.get("pages", []) or []:
        pnum = page.get("page")
        if pnum is None:
            pnum = page.get("page_number")
        if pnum == page_number:
            return page
    return None


def find_entity(doc, eid, expected_type):
    for e in get_entities(doc):
        if entity_id(e) == eid and entity_type(e) == expected_type:
            return e
    return None


def relation_exists(doc, source_id, target_id):
    return any(
        relation_type(r) == RELATION_TYPE
        and relation_source(r) == source_id
        and relation_target(r) == target_id
        for r in get_relations(doc)
    )


# ============================================================
# 3. IDS
# ============================================================

REL_ID_RE = re.compile(r"^P(?P<page>\d+)_R(?P<num>\d+)$")


def next_relation_id(doc, page_number):
    max_num = 0

    for r in get_relations(doc):
        rid = relation_id(r)
        if not rid:
            continue

        m = REL_ID_RE.match(str(rid))
        if m and int(m.group("page")) == int(page_number):
            max_num = max(max_num, int(m.group("num")))

    return f"P{int(page_number)}_R{max_num + 1:03d}"


# ============================================================
# 4. RELATION CREATION
# ============================================================

def build_relation(new_id, source_id, target_id, page):
    return {
        "identifiant_relation": new_id,
        "type_relation": RELATION_TYPE,
        "identifiant_entite_sujet": source_id,
        "identifiant_entite_objet": target_id,
        "page": page,

        # Aliases de compatibilitÃ©
        "relation": RELATION_TYPE,
        "from_id": source_id,
        "to_id": target_id,
        "type": RELATION_TYPE,

        # Provenance SGCE
        "_sgce_created": True,
        "_sgce_pattern": "A",
        "_sgce_subcase": "A4_IMAGERIE_DEFAILLANCE_ORGANE",
        "_sgce_operation": "LINK",
    }


def add_relation(doc, relation):
    rid = relation_id(relation)

    if isinstance(doc.get("global_relations"), list):
        if not any(relation_id(r) == rid for r in doc["global_relations"]):
            doc["global_relations"].append(copy.deepcopy(relation))

    page = find_page(doc, relation.get("page"))

    if page is not None:
        if not isinstance(page.get("relations"), list):
            page["relations"] = []

        if not any(relation_id(r) == rid for r in page["relations"]):
            page["relations"].append(copy.deepcopy(relation))

    if not isinstance(doc.get("global_relations"), list) and page is None:
        raise ValueError(
            f"Impossible d'ajouter la relation {rid}: page introuvable."
        )


# ============================================================
# 5. CORRECTION
# ============================================================

def correct_candidate(doc, item):
    status = item.get("validation_status")
    action = item.get("recommended_future_action")

    source_info = item.get("source_entity") or {}
    source_id = source_info.get("entity_id")

    source = find_entity(doc, source_id, SOURCE_TYPE)

    if source is None:
        raise ValueError(
            f"Source IMAGERIE_PROCEDURE {source_id} introuvable."
        )

    # Aucun changement
    if status in {"ALREADY_CORRECT", "AMBIGUOUS"}:
        return {
            "operation": "SKIP",
            "source_entity_id": source_id,
            "reason": status,
            "modified": False,
        }

    # LINK attendu
    if status == "MISSING_RELATION" and action == "LINK":
        target_info = item.get("reliable_target") or {}
        target_id = target_info.get("entity_id")

        if not target_id:
            raise ValueError(
                f"Cible fiable absente pour LINK {source_id}."
            )

        target = find_entity(doc, target_id, TARGET_TYPE)

        if target is None:
            raise ValueError(
                f"DEFAILLANCE_ORGANE {target_id} introuvable."
            )

        if relation_exists(doc, source_id, target_id):
            return {
                "operation": "SKIP",
                "source_entity_id": source_id,
                "target_entity_id": target_id,
                "reason": "RELATION_ALREADY_EXISTS_AT_CORRECTION_TIME",
                "modified": False,
            }

        page = entity_page(source)
        rid = next_relation_id(doc, page)

        relation = build_relation(
            rid,
            source_id,
            target_id,
            page,
        )

        add_relation(doc, relation)

        return {
            "operation": "LINK",
            "source_entity_id": source_id,
            "target_entity_id": target_id,
            "relation_id": rid,
            "relation_type": RELATION_TYPE,
            "modified": True,
        }

    # Pas de SPLIT automatique dans ce correcteur conservateur
    if status == "CONFIRMED_PATTERN_A" and action == "SPLIT":
        return {
            "operation": "SKIP",
            "source_entity_id": source_id,
            "reason": "A4_SPLIT_NOT_ENABLED_IN_THIS_CONSERVATIVE_CORRECTOR",
            "modified": False,
        }

    return {
        "operation": "SKIP",
        "source_entity_id": source_id,
        "reason": "UNSUPPORTED_STATUS_ACTION_COMBINATION",
        "modified": False,
    }


# ============================================================
# 6. MAIN
# ============================================================

def main():
    input_dir = resolve_input_dir()
    validation_report = resolve_validation_report()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with validation_report.open("r", encoding="utf-8") as f:
        validation = json.load(f)

    validated = validation.get("validated_candidates", [])

    by_document = {}
    for item in validated:
        filename = item.get("document")
        by_document.setdefault(filename, []).append(item)

    operations = []
    errors = []
    copied_documents = 0
    modified_documents = 0
    skipped_nonclinical = []

    for path in sorted(input_dir.glob("*.json")):
        try:
            with path.open("r", encoding="utf-8") as f:
                original = json.load(f)

            if not is_clinical_document(original):
                skipped_nonclinical.append(path.name)
                continue

            doc = copy.deepcopy(original)
            doc_operations = []

            for item in by_document.get(path.name, []):
                try:
                    op = correct_candidate(doc, item)
                    op["document"] = path.name
                    doc_operations.append(op)
                    operations.append(op)
                except Exception as exc:
                    errors.append({
                        "document": path.name,
                        "source_entity_id": (
                            item.get("source_entity") or {}
                        ).get("entity_id"),
                        "error": str(exc),
                    })

            out_path = OUTPUT_DIR / path.name
            out_path.write_text(
                json.dumps(doc, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            copied_documents += 1

            if any(op.get("modified") for op in doc_operations):
                modified_documents += 1

        except Exception as exc:
            errors.append({
                "document": path.name,
                "error": str(exc),
            })

    counts = Counter(op["operation"] for op in operations)

    applied = sum(
        1 for op in operations
        if op.get("modified") is True
    )

    report = {
        "pattern": "A4",
        "name": "IMAGERIE_PROCEDURE + DEFAILLANCE_ORGANE",
        "relation": RELATION_TYPE,
        "input_directory": str(input_dir),
        "validation_report": str(validation_report),
        "output_directory": str(OUTPUT_DIR),

        "summary": {
            "validated_candidates": len(validated),
            "operations_total": applied,
            "link": counts.get("LINK", 0),
            "split": counts.get("SPLIT", 0),
            "skip": counts.get("SKIP", 0),
            "documents_copied": copied_documents,
            "documents_modified": modified_documents,
            "nonclinical_json_skipped": len(skipped_nonclinical),
            "errors": len(errors),
        },

        "operations": operations,
        "nonclinical_json_skipped": skipped_nonclinical,
        "errors": errors,
    }

    CORRECTION_REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("=" * 76)
    print("SGCE - PATTERN A4 AUTOMATIC CORRECTION")
    print("=" * 76)
    print(f"EntrÃ©e                  : {input_dir}")
    print(f"Validation              : {validation_report}")
    print(f"Sortie                  : {OUTPUT_DIR}")
    print()
    print(f"Candidats validÃ©s       : {len(validated)}")
    print(f"OpÃ©rations appliquÃ©es   : {applied}")
    print(f"LINK                    : {counts.get('LINK', 0)}")
    print(f"SPLIT                   : {counts.get('SPLIT', 0)}")
    print(f"SKIP                    : {counts.get('SKIP', 0)}")
    print()
    print(f"Documents copiÃ©s        : {copied_documents}")
    print(f"Documents modifiÃ©s      : {modified_documents}")
    print(f"JSON non cliniques ignorÃ©s : {len(skipped_nonclinical)}")
    print(f"Erreurs                 : {len(errors)}")
    print()
    print(f"Rapport                 : {CORRECTION_REPORT}")
    print()
    print("Les fichiers sources n'ont pas Ã©tÃ© modifiÃ©s.")


if __name__ == "__main__":
    main()

