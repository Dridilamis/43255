# -*- coding: utf-8 -*-
"""
pattern_a5_auto_corrector.py
============================

SGCE â€” Pattern A5 Auto-Corrector

A5:
IMAGERIE_PROCEDURE
    --imagerie_objective_comorbidite-->
COMORBIDITE_ANTECEDENT

Expected current run:
- 1 MISSING_RELATION
- 1 LINK
- 0 SPLIT
"""

import copy
import json
import re
from collections import Counter
from pathlib import Path


BASE_DIR = Path(
    r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM"
    r"\Reduction_hallucinations"
)

INPUT_DIR_CANDIDATES = [
    BASE_DIR / "PatternA4" / "pattern_a4_corrected",
    BASE_DIR / "PatternA3" / "pattern_a3_corrected",
]

VALIDATION_REPORT_CANDIDATES = [
    BASE_DIR / "PatternA5" / "pattern_a5_validation" / "pattern_a5_validation_report.json",
    BASE_DIR / "pattern_a5_validation" / "pattern_a5_validation_report.json",
]

OUTPUT_DIR = BASE_DIR / "PatternA5" / "pattern_a5_corrected"
CORRECTION_REPORT = OUTPUT_DIR / "pattern_a5_correction_report.json"

SOURCE_TYPE = "IMAGERIE_PROCEDURE"
TARGET_TYPE = "COMORBIDITE_ANTECEDENT"
RELATION_TYPE = "imagerie_objective_comorbidite"


def resolve_input_dir():
    for p in INPUT_DIR_CANDIDATES:
        if p.exists() and any(p.glob("*.json")):
            return p
    raise FileNotFoundError("Aucun dossier JSON clinique trouvÃ©.")


def resolve_validation_report():
    for p in VALIDATION_REPORT_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError("Rapport de validation A5 introuvable.")


def entity_id(e):
    return e.get("identifiant_entite") or e.get("id") or e.get("entity_id")


def entity_type(e):
    return e.get("categorie") or e.get("type") or ""


def entity_page(e):
    return e.get("page") if e.get("page") is not None else e.get("page_number")


def relation_id(r):
    return r.get("identifiant_relation") or r.get("id") or r.get("relation_id")


def relation_type(r):
    return r.get("type_relation") or r.get("relation") or r.get("type") or ""


def relation_source(r):
    return r.get("identifiant_entite_sujet") or r.get("from_id") or r.get("subject_id")


def relation_target(r):
    return r.get("identifiant_entite_objet") or r.get("to_id") or r.get("object_id")


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
    return isinstance(doc, dict) and (
        isinstance(doc.get("global_entities"), list)
        or isinstance(doc.get("pages"), list)
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


def build_relation(new_id, source_id, target_id, page):
    return {
        "identifiant_relation": new_id,
        "type_relation": RELATION_TYPE,
        "identifiant_entite_sujet": source_id,
        "identifiant_entite_objet": target_id,
        "page": page,
        "relation": RELATION_TYPE,
        "from_id": source_id,
        "to_id": target_id,
        "type": RELATION_TYPE,
        "_sgce_created": True,
        "_sgce_pattern": "A",
        "_sgce_subcase": "A5_IMAGERIE_COMORBIDITE_ANTECEDENT",
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
        raise ValueError(f"Impossible d'ajouter la relation {rid}: page introuvable.")


def correct_candidate(doc, item):
    status = item.get("validation_status")
    action = item.get("recommended_future_action")
    source_id = (item.get("source_entity") or {}).get("entity_id")

    source = find_entity(doc, source_id, SOURCE_TYPE)
    if source is None:
        raise ValueError(f"Source {SOURCE_TYPE} {source_id} introuvable.")

    if status in {"ALREADY_CORRECT", "AMBIGUOUS"}:
        return {
            "operation": "SKIP",
            "source_entity_id": source_id,
            "reason": status,
            "modified": False,
        }

    if status == "MISSING_RELATION" and action == "LINK":
        target_id = (item.get("reliable_target") or {}).get("entity_id")

        if not target_id:
            raise ValueError(f"Cible fiable absente pour LINK {source_id}.")

        target = find_entity(doc, target_id, TARGET_TYPE)
        if target is None:
            raise ValueError(f"{TARGET_TYPE} {target_id} introuvable.")

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

        relation = build_relation(rid, source_id, target_id, page)
        add_relation(doc, relation)

        return {
            "operation": "LINK",
            "source_entity_id": source_id,
            "target_entity_id": target_id,
            "relation_id": rid,
            "relation_type": RELATION_TYPE,
            "modified": True,
        }

    if status == "CONFIRMED_PATTERN_A" and action == "SPLIT":
        return {
            "operation": "SKIP",
            "source_entity_id": source_id,
            "reason": "A5_SPLIT_NOT_ENABLED_IN_THIS_CONSERVATIVE_CORRECTOR",
            "modified": False,
        }

    return {
        "operation": "SKIP",
        "source_entity_id": source_id,
        "reason": "UNSUPPORTED_STATUS_ACTION_COMBINATION",
        "modified": False,
    }


def main():
    input_dir = resolve_input_dir()
    validation_report = resolve_validation_report()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    validation = json.loads(validation_report.read_text(encoding="utf-8"))
    validated = validation.get("validated_candidates", [])

    by_document = {}
    for item in validated:
        by_document.setdefault(item.get("document"), []).append(item)

    operations = []
    errors = []
    copied = 0
    modified_docs = 0
    skipped_nonclinical = []

    for path in sorted(input_dir.glob("*.json")):
        try:
            original = json.loads(path.read_text(encoding="utf-8"))

            if not is_clinical_document(original):
                skipped_nonclinical.append(path.name)
                continue

            doc = copy.deepcopy(original)
            doc_ops = []

            for item in by_document.get(path.name, []):
                try:
                    op = correct_candidate(doc, item)
                    op["document"] = path.name
                    operations.append(op)
                    doc_ops.append(op)
                except Exception as exc:
                    errors.append({
                        "document": path.name,
                        "source_entity_id": (item.get("source_entity") or {}).get("entity_id"),
                        "error": str(exc),
                    })

            (OUTPUT_DIR / path.name).write_text(
                json.dumps(doc, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            copied += 1
            if any(op.get("modified") for op in doc_ops):
                modified_docs += 1

        except Exception as exc:
            errors.append({"document": path.name, "error": str(exc)})

    counts = Counter(op["operation"] for op in operations)
    applied = sum(1 for op in operations if op.get("modified") is True)

    report = {
        "pattern": "A5",
        "name": "IMAGERIE_PROCEDURE + COMORBIDITE_ANTECEDENT",
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
            "documents_copied": copied,
            "documents_modified": modified_docs,
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
    print("SGCE - PATTERN A5 AUTOMATIC CORRECTION")
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
    print(f"Documents copiÃ©s        : {copied}")
    print(f"Documents modifiÃ©s      : {modified_docs}")
    print(f"JSON non cliniques ignorÃ©s : {len(skipped_nonclinical)}")
    print(f"Erreurs                 : {len(errors)}")
    print()
    print(f"Rapport                 : {CORRECTION_REPORT}")
    print()
    print("Les fichiers sources n'ont pas Ã©tÃ© modifiÃ©s.")


if __name__ == "__main__":
    main()

