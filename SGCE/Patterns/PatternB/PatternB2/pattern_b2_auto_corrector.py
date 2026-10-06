# -*- coding: utf-8 -*-
"""
pattern_b2_generic_corrector.py
===============================

SGCE — Pattern B2 Generic Corrector

Uses:
  PatternB2/pattern_b2_relation_grounding/
  pattern_b2_relation_grounding_report.json

Only applies:
  ACTIONABLE_CHAIN_REWRITE
  + recommended_action = CREATE_B_REPLACE_DIRECT_WITH_TWO_HOP

For every safe candidate:
1) create missing intermediate entity B from selected_evidence;
2) remove the exact direct A->C relation identified by the validator;
3) add A --R1--> B;
4) add B --R2--> C.

All other candidates are skipped.

IMPORTANT:
- No action is taken without explicit documentary evidence for B.
- R1/R2 must already have been validated against locked TRACE-Sepsis signatures.
- Original input files are never modified.
"""

import copy
import json
import re
from collections import Counter
from pathlib import Path

PATTERN_B2_DIR = Path(__file__).resolve().parent
PATTERN_B_DIR = PATTERN_B2_DIR.parent
PATTERNS_DIR = PATTERN_B_DIR.parent
SGCE_DIR = PATTERNS_DIR.parent
BASE_DIR = SGCE_DIR.parent

PATTERN_B1_DIR = PATTERN_B_DIR / "PatternB1"

INPUT_DIR_CANDIDATES = [PATTERN_B1_DIR / "corrected"]

RELATION_GROUNDING_REPORT_CANDIDATES = [
    PATTERN_B2_DIR / "relation_grounding" / "pattern_b2_relation_grounding_report.json",
]

OUTPUT_DIR = PATTERN_B2_DIR / "corrected"
REPORT_PATH = OUTPUT_DIR / "pattern_b2_correction_report.json"

ENTITY_ID_RE = re.compile(r"^P(?P<page>\d+)_E(?P<num>\d+)$")
REL_ID_RE = re.compile(r"^P(?P<page>\d+)_R(?P<num>\d+)$")


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


def next_relation_id(doc, page_number):
    max_num = 0
    for r in get_relations(doc):
        rid = relation_id(r)
        if not rid:
            continue
        m = REL_ID_RE.match(str(rid))
        if m and str(m.group("page")) == str(page_number):
            max_num = max(max_num, int(m.group("num")))
    return f"P{page_number}_R{max_num + 1:03d}"


def add_entity(doc, entity):
    if isinstance(doc.get("global_entities"), list):
        doc["global_entities"].append(copy.deepcopy(entity))

    p = find_page(doc, entity_page(entity))
    if p is not None:
        p.setdefault("entities", [])
        p["entities"].append(copy.deepcopy(entity))


def build_relation(rid, rtype, src_id, tgt_id, page, operation):
    return {
        "identifiant_relation": rid,
        "type_relation": rtype,
        "identifiant_entite_sujet": src_id,
        "identifiant_entite_objet": tgt_id,
        "page": page,
        "relation": rtype,
        "from_id": src_id,
        "to_id": tgt_id,
        "type": rtype,
        "_sgce_created": True,
        "_sgce_pattern": "B2",
        "_sgce_operation": operation,
    }


def add_relation(doc, rel):
    if isinstance(doc.get("global_relations"), list):
        doc["global_relations"].append(copy.deepcopy(rel))

    p = find_page(doc, rel.get("page"))
    if p is not None:
        p.setdefault("relations", [])
        p["relations"].append(copy.deepcopy(rel))


def remove_relation_by_id(doc, rid):
    removed = 0

    if isinstance(doc.get("global_relations"), list):
        before = len(doc["global_relations"])
        doc["global_relations"] = [
            r for r in doc["global_relations"]
            if relation_id(r) != rid
        ]
        removed += before - len(doc["global_relations"])

    for p in doc.get("pages", []) or []:
        if isinstance(p.get("relations"), list):
            before = len(p["relations"])
            p["relations"] = [
                r for r in p["relations"]
                if relation_id(r) != rid
            ]
            removed += before - len(p["relations"])

    return removed


def apply_candidate(doc, candidate):
    if candidate.get("relation_grounding_status") != "ACTIONABLE_CHAIN_REWRITE":
        return {
            "operation": "SKIP",
            "modified": False,
            "reason": candidate.get("relation_grounding_status"),
        }

    if candidate.get("recommended_action") != "CREATE_B_REPLACE_DIRECT_WITH_TWO_HOP":
        return {
            "operation": "SKIP",
            "modified": False,
            "reason": "ACTION_NOT_AUTHORIZED",
        }

    src = candidate.get("source_entity") or {}
    tgt = candidate.get("target_entity") or {}

    src_id = src.get("id")
    tgt_id = tgt.get("id")

    evidence = candidate.get("selected_evidence")
    middle_type = candidate.get("middle_type_missing")
    r1 = candidate.get("relation_1")
    r2 = candidate.get("relation_2")

    direct_ids = candidate.get("direct_relation_ids") or []

    if not (
        src_id and tgt_id and evidence and middle_type
        and r1 and r2 and len(direct_ids) == 1
    ):
        return {
            "operation": "SKIP",
            "modified": False,
            "reason": "INCOMPLETE_ACTIONABLE_DATA",
        }

    direct_id = direct_ids[0]

    direct_rel = next(
        (r for r in get_relations(doc) if relation_id(r) == direct_id),
        None,
    )

    if direct_rel is None:
        return {
            "operation": "SKIP",
            "modified": False,
            "reason": "DIRECT_RELATION_NOT_FOUND",
        }

    page = (
        direct_rel.get("page")
        or direct_rel.get("page_number")
        or src.get("page")
        or tgt.get("page")
        or 1
    )

    new_entity_id = next_entity_id(doc, page)

    new_entity = {
        "identifiant_entite": new_entity_id,
        "categorie": middle_type,
        "type": middle_type,
        "name": evidence,
        "valeur": evidence,
        "preuve": evidence,
        "page": page,
        "_sgce_created": True,
        "_sgce_pattern": "B2",
        "_sgce_operation": "CREATE_MISSING_INTERMEDIATE_ENTITY",
    }

    add_entity(doc, new_entity)

    removed_count = remove_relation_by_id(doc, direct_id)

    rid1 = next_relation_id(doc, page)
    rel1 = build_relation(
        rid1,
        r1,
        src_id,
        new_entity_id,
        page,
        "CHAIN_REWRITE_R1",
    )
    add_relation(doc, rel1)

    rid2 = next_relation_id(doc, page)
    rel2 = build_relation(
        rid2,
        r2,
        new_entity_id,
        tgt_id,
        page,
        "CHAIN_REWRITE_R2",
    )
    add_relation(doc, rel2)

    return {
        "operation": "CREATE_B_REPLACE_DIRECT_WITH_TWO_HOP",
        "modified": True,
        "source_entity_id": src_id,
        "target_entity_id": tgt_id,
        "created_entity_id": new_entity_id,
        "created_entity_type": middle_type,
        "created_entity_text": evidence,
        "removed_direct_relation_id": direct_id,
        "removed_relation_occurrences": removed_count,
        "created_relation_1_id": rid1,
        "created_relation_1_type": r1,
        "created_relation_2_id": rid2,
        "created_relation_2_type": r2,
    }


def main():
    input_dir = resolve_existing(INPUT_DIR_CANDIDATES, "Entrée clinique B2")
    report_path = resolve_existing(
        RELATION_GROUNDING_REPORT_CANDIDATES,
        "Rapport relation-grounding B2"
    )

    grounding = load_json(report_path)

    candidates = grounding.get("candidates", [])

    by_doc = {}
    for c in candidates:
        by_doc.setdefault(c.get("document"), []).append(c)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    operations = []
    errors = []
    copied = 0
    modified_docs = 0
    nonclinical = []

    for path in sorted(input_dir.glob("*.json")):
        try:
            original = load_json(path)

            if not is_clinical_document(original):
                nonclinical.append(path.name)
                continue

            doc = copy.deepcopy(original)
            doc_modified = False

            for c in by_doc.get(path.name, []):
                try:
                    result = apply_candidate(doc, c)
                    result["document"] = path.name
                    result["candidate_id"] = c.get("candidate_id")
                    operations.append(result)

                    if result.get("modified"):
                        doc_modified = True

                except Exception as exc:
                    errors.append({
                        "document": path.name,
                        "candidate_id": c.get("candidate_id"),
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

    applied = [
        op for op in operations
        if op.get("modified") is True
    ]

    report = {
        "pattern": "B2",
        "mode": "GENERIC_SAFE_CORRECTOR",
        "input_directory": str(input_dir),
        "relation_grounding_report": str(report_path),
        "output_directory": str(OUTPUT_DIR),
        "summary": {
            "candidates_seen": len(candidates),
            "operations_applied": len(applied),
            "entities_created": len(applied),
            "direct_relations_removed": len(applied),
            "relations_created": len(applied) * 2,
            "documents_copied": copied,
            "documents_modified": modified_docs,
            "nonclinical_json_skipped": len(nonclinical),
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
    print("SGCE - PATTERN B2 GENERIC CORRECTION")
    print("=" * 82)
    print(f"Entrée                      : {input_dir}")
    print(f"Grounding report            : {report_path}")
    print(f"Sortie                      : {OUTPUT_DIR}")
    print()
    print(f"Candidats vus               : {len(candidates)}")
    print(f"Opérations appliquées       : {len(applied)}")
    print(f"Entités B créées            : {len(applied)}")
    print(f"Relations directes retirées : {len(applied)}")
    print(f"Nouvelles relations créées  : {len(applied) * 2}")
    print(f"Documents modifiés          : {modified_docs}")
    print(f"Erreurs                     : {len(errors)}")
    print()
    print(f"Rapport                     : {REPORT_PATH}")


if __name__ == "__main__":
    main()
