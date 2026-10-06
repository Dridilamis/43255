# -*- coding: utf-8 -*-
"""
pattern_b1_generic_corrector.py
===============================

SGCE — Pattern B1 Generic Corrector

Uses:
  PatternB1/pattern_b1_validation/pattern_b1_validation_report.json

Supported safe actions:
- RESOLVABLE_REFERENCE   -> RELINK
- CONFIRMED_MISSING_ENTITY -> CREATE_AND_LINK
- UNRESOLVABLE_REFERENCE -> SKIP
- AMBIGUOUS               -> SKIP

IMPORTANT:
This script only applies actions explicitly authorized by the validator.
It never guesses missing clinical content.

For CREATE_AND_LINK, the validator must provide:
- proposed_entity_type
- proposed_entity_text
"""

import copy
import json
import re
from collections import Counter
from pathlib import Path

PATTERN_B1_DIR = Path(__file__).resolve().parent
PATTERN_B_DIR = PATTERN_B1_DIR.parent
PATTERNS_DIR = PATTERN_B_DIR.parent
SGCE_DIR = PATTERNS_DIR.parent
BASE_DIR = SGCE_DIR.parent

PATTERN_A6_DIR = PATTERNS_DIR / "PatternA" / "PatternA6"

INPUT_DIR_CANDIDATES = [
    PATTERN_A6_DIR / "corrected",
]

VALIDATION_REPORT_CANDIDATES = [
    PATTERN_B1_DIR / "validation" / "pattern_b1_validation_report.json",
]

OUTPUT_DIR = PATTERN_B1_DIR / "corrected"
REPORT_PATH = OUTPUT_DIR / "pattern_b1_correction_report.json"

ENTITY_ID_RE = re.compile(r"^P(?P<page>\d+)_E(?P<num>\d+)$")


def resolve_existing(paths, label):
    for p in paths:
        if p.exists():
            return p
    raise FileNotFoundError(f"{label} introuvable.")


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def is_clinical_document(doc):
    return isinstance(doc, dict) and (
        isinstance(doc.get("global_entities"), list)
        or isinstance(doc.get("pages"), list)
    )


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


def find_page(doc, page_number):
    for p in doc.get("pages", []) or []:
        num = p.get("page")
        if num is None:
            num = p.get("page_number")
        if str(num) == str(page_number):
            return p
    return None


def next_entity_id(doc, page_number):
    max_num = 0
    for e in get_entities(doc):
        eid = entity_id(e)
        if not eid:
            continue
        m = ENTITY_ID_RE.match(str(eid))
        if m and str(m.group("page")) == str(page_number):
            max_num = max(max_num, int(m.group("num")))
    return f"P{page_number}_E{max_num + 1:03d}"


def add_entity(doc, entity):
    if isinstance(doc.get("global_entities"), list):
        doc["global_entities"].append(copy.deepcopy(entity))

    page = find_page(doc, entity_page(entity))
    if page is not None:
        page.setdefault("entities", [])
        page["entities"].append(copy.deepcopy(entity))


def replace_endpoint_in_relation(rel, role, new_value):
    if role == "SOURCE":
        for key in (
            "identifiant_entite_sujet", "from_id", "subject_id",
            "sujet", "subject"
        ):
            if key in rel:
                rel[key] = new_value
    elif role == "TARGET":
        for key in (
            "identifiant_entite_objet", "to_id", "object_id",
            "objet", "object"
        ):
            if key in rel:
                rel[key] = new_value


def locate_relation(doc, candidate):
    info = candidate.get("relation") or {}
    rid = info.get("relation_id")

    if rid:
        for r in get_relations(doc):
            if relation_id(r) == rid:
                return r

    rtype = info.get("relation_type")
    src = info.get("source_value")
    tgt = info.get("target_value")

    for r in get_relations(doc):
        if (
            relation_type(r) == rtype
            and str(relation_source(r)) == str(src)
            and str(relation_target(r)) == str(tgt)
        ):
            return r

    return None


def apply_candidate(doc, candidate):
    relation = locate_relation(doc, candidate)

    if relation is None:
        return {
            "operation": "SKIP",
            "modified": False,
            "reason": "RELATION_NOT_FOUND",
        }

    endpoint_validations = candidate.get("endpoint_validations", [])
    modifications = []

    for ep in endpoint_validations:
        status = ep.get("status")
        action = ep.get("recommended_future_action")
        role = ep.get("role")

        if status == "RESOLVABLE_REFERENCE" and action == "RELINK":
            new_id = ep.get("resolved_entity_id")
            if not new_id:
                continue

            replace_endpoint_in_relation(relation, role, new_id)

            modifications.append({
                "operation": "RELINK",
                "role": role,
                "new_entity_id": new_id,
            })

        elif status == "CONFIRMED_MISSING_ENTITY" and action == "CREATE_AND_LINK":
            proposed_type = ep.get("proposed_entity_type")
            proposed_text = ep.get("proposed_entity_text")

            if not proposed_type or not proposed_text:
                continue

            page = relation.get("page") or relation.get("page_number") or 1
            new_id = next_entity_id(doc, page)

            new_entity = {
                "identifiant_entite": new_id,
                "categorie": proposed_type,
                "type": proposed_type,
                "name": proposed_text,
                "valeur": proposed_text,
                "preuve": proposed_text,
                "page": page,
                "_sgce_created": True,
                "_sgce_pattern": "B1",
                "_sgce_operation": "CREATE_AND_LINK",
            }

            add_entity(doc, new_entity)
            replace_endpoint_in_relation(relation, role, new_id)

            modifications.append({
                "operation": "CREATE_AND_LINK",
                "role": role,
                "created_entity_id": new_id,
                "created_entity_type": proposed_type,
                "created_entity_text": proposed_text,
            })

    return {
        "operation": "APPLIED" if modifications else "SKIP",
        "modified": bool(modifications),
        "modifications": modifications,
        "reason": "" if modifications else "NO_SAFE_ACTION",
    }


def main():
    input_dir = resolve_existing(INPUT_DIR_CANDIDATES, "Entrée clinique B1")
    validation_path = resolve_existing(
        VALIDATION_REPORT_CANDIDATES,
        "Rapport validation B1"
    )

    validation = load_json(validation_path)
    validated = validation.get("validated_candidates", [])

    by_doc = {}
    for c in validated:
        by_doc.setdefault(c.get("document"), []).append(c)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    operations = []
    errors = []
    copied = 0
    modified_docs = 0
    skipped_nonclinical = []

    for path in sorted(input_dir.glob("*.json")):
        try:
            original = load_json(path)

            if not is_clinical_document(original):
                skipped_nonclinical.append(path.name)
                continue

            doc = copy.deepcopy(original)
            doc_modified = False

            for c in by_doc.get(path.name, []):
                try:
                    result = apply_candidate(doc, c)
                    result["document"] = path.name
                    result["validation_status"] = c.get("validation_status")
                    operations.append(result)
                    doc_modified = doc_modified or result.get("modified", False)
                except Exception as exc:
                    errors.append({
                        "document": path.name,
                        "error": str(exc),
                    })

            (OUTPUT_DIR / path.name).write_text(
                json.dumps(doc, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            copied += 1
            if doc_modified:
                modified_docs += 1

        except Exception as exc:
            errors.append({
                "document": path.name,
                "error": str(exc),
            })

    op_counts = Counter()
    for op in operations:
        for m in op.get("modifications", []):
            op_counts[m["operation"]] += 1

    report = {
        "pattern": "B1",
        "mode": "GENERIC_SAFE_CORRECTOR",
        "input_directory": str(input_dir),
        "validation_report": str(validation_path),
        "output_directory": str(OUTPUT_DIR),
        "summary": {
            "validated_candidates": len(validated),
            "relink_applied": op_counts.get("RELINK", 0),
            "create_and_link_applied": op_counts.get("CREATE_AND_LINK", 0),
            "documents_copied": copied,
            "documents_modified": modified_docs,
            "nonclinical_json_skipped": len(skipped_nonclinical),
            "errors": len(errors),
        },
        "operations": operations,
        "errors": errors,
    }

    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("=" * 82)
    print("SGCE - PATTERN B1 GENERIC CORRECTION")
    print("=" * 82)
    print(f"Entrée                  : {input_dir}")
    print(f"Validation              : {validation_path}")
    print(f"Sortie                  : {OUTPUT_DIR}")
    print()
    print(f"Candidats validés       : {len(validated)}")
    print(f"RELINK appliqués        : {op_counts.get('RELINK', 0)}")
    print(f"CREATE_AND_LINK         : {op_counts.get('CREATE_AND_LINK', 0)}")
    print(f"Documents copiés        : {copied}")
    print(f"Documents modifiés      : {modified_docs}")
    print(f"Erreurs                 : {len(errors)}")
    print()
    print(f"Rapport                 : {REPORT_PATH}")


if __name__ == "__main__":
    main()
