# -*- coding: utf-8 -*-
"""
pattern_b2_relation_grounding_validator.py
==========================================

SGCE — Pattern B2 Relation-Grounding Validator

Purpose
-------
Refine the 16 ACTIONABLE_CREATE_AND_LINK candidates from the previous B2
actionability step.

A candidate is NOT safe merely because:
  A exists + textual evidence for B exists + C exists.

TRACE-Sepsis also requires relations to be document-supported. Therefore,
this validator only keeps cases where there is an actual structural relation
between the exact A and C endpoints that can plausibly represent a collapsed
A->B->C chain.

Classification
--------------
ACTIONABLE_CHAIN_REWRITE
    Exact A->C relation exists, but it is not a valid locked direct relation
    for the A/C types, while the proposed A->B and B->C relations are valid
    locked signatures. The missing B also has one explicit evidence term.

DIRECT_RELATION_ALREADY_VALID
    A->C already has a valid direct TRACE-Sepsis relation. No B2 rewrite.

NO_DIRECT_RELATIONAL_EVIDENCE
    A and C co-occur, but no exact A->C relation exists. Protected.

AMBIGUOUS_MULTIPLE_DIRECT_RELATIONS
    Multiple A->C relations exist and cannot be rewritten safely.

INVALID_CHAIN_SIGNATURE
    Proposed R1/R2 chain does not match locked signatures. Protected.

No clinical JSON is modified.
"""

import csv
import json
from collections import Counter
from pathlib import Path


PATTERN_B2_DIR = Path(__file__).resolve().parent
PATTERN_B_DIR = PATTERN_B2_DIR.parent
PATTERNS_DIR = PATTERN_B_DIR.parent
SGCE_DIR = PATTERNS_DIR.parent
BASE_DIR = SGCE_DIR.parent

PATTERN_B1_DIR = PATTERN_B_DIR / "PatternB1"

INPUT_DIR_CANDIDATES = [PATTERN_B1_DIR / "corrected"]

ACTION_REPORT_CANDIDATES = [
    PATTERN_B2_DIR / "actionability" / "pattern_b2_actionability_report.json",
]

GUIDELINE_CANDIDATES = [
    BASE_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
    BASE_DIR.parent / "Guideline_TRACE_Sepsis_v1.6.json",
    Path.cwd() / "Guideline_TRACE_Sepsis_v1.6.json",
    PATTERN_B2_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
]

OUTPUT_DIR = PATTERN_B2_DIR / "relation_grounding"
OUTPUT_JSON = OUTPUT_DIR / "pattern_b2_relation_grounding_report.json"
OUTPUT_CSV = OUTPUT_DIR / "pattern_b2_relation_grounding_candidates.csv"

def resolve_existing(candidates, label):
    for p in candidates:
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


def get_relations(doc):
    if isinstance(doc.get("global_relations"), list):
        return doc["global_relations"]

    out = []
    for p in doc.get("pages", []) or []:
        out.extend(p.get("relations", []) or [])
    return out


def get_root(guideline):
    return guideline.get("ontologie_sepsis_graph", guideline)


def get_locked_signatures(guideline):
    root = get_root(guideline)
    locked = root.get("signatures_relations_verrouillees_v1_5", {})
    out = {}

    for name, spec in locked.items():
        if not isinstance(spec, dict):
            continue
        dom = spec.get("domaine")
        img = spec.get("image")
        if dom and img:
            out[name] = (dom, img)

    return out


def direct_relation_is_valid(rtype, src_type, tgt_type, signatures):
    return signatures.get(rtype) == (src_type, tgt_type)


def proposed_chain_is_valid(candidate, signatures):
    r1 = candidate.get("relation_1")
    r2 = candidate.get("relation_2")
    a = candidate.get("source_type")
    b = candidate.get("middle_type_missing")
    c = candidate.get("target_type")

    return (
        signatures.get(r1) == (a, b)
        and signatures.get(r2) == (b, c)
    )


def main():
    input_dir = resolve_existing(INPUT_DIR_CANDIDATES, "Entrée clinique B2")
    action_path = resolve_existing(
        ACTION_REPORT_CANDIDATES, "Rapport d'actionnabilité B2"
    )
    guideline_path = resolve_existing(GUIDELINE_CANDIDATES, "Guideline")

    action_report = load_json(action_path)
    guideline = load_json(guideline_path)
    signatures = get_locked_signatures(guideline)

    candidates = [
        c for c in action_report.get("candidates", [])
        if c.get("actionability_status") == "ACTIONABLE_CREATE_AND_LINK"
    ]

    documents = {}
    for p in sorted(input_dir.glob("*.json")):
        try:
            doc = load_json(p)
            if is_clinical_document(doc):
                documents[p.name] = doc
        except Exception:
            pass

    results = []

    for c in candidates:
        doc_name = c.get("document")
        doc = documents.get(doc_name)

        row = {
            **c,
            "relation_grounding_status": None,
            "recommended_action": "NONE",
            "direct_relation_ids": [],
            "direct_relation_types": [],
            "relation_grounding_reason": "",
        }

        if doc is None:
            row["relation_grounding_status"] = "NO_DIRECT_RELATIONAL_EVIDENCE"
            row["relation_grounding_reason"] = "Document clinique introuvable."
            results.append(row)
            continue

        if not proposed_chain_is_valid(c, signatures):
            row["relation_grounding_status"] = "INVALID_CHAIN_SIGNATURE"
            row["relation_grounding_reason"] = (
                "La chaîne proposée R1/R2 ne respecte pas les signatures verrouillées."
            )
            results.append(row)
            continue

        src_id = (c.get("source_entity") or {}).get("id")
        tgt_id = (c.get("target_entity") or {}).get("id")

        direct = [
            r for r in get_relations(doc)
            if str(relation_source(r)) == str(src_id)
            and str(relation_target(r)) == str(tgt_id)
        ]

        row["direct_relation_ids"] = [relation_id(r) for r in direct]
        row["direct_relation_types"] = [relation_type(r) for r in direct]

        if not direct:
            row["relation_grounding_status"] = "NO_DIRECT_RELATIONAL_EVIDENCE"
            row["relation_grounding_reason"] = (
                "A et C sont présents, mais aucune relation directe A->C n'existe. "
                "La création de deux nouvelles relations serait une inférence."
            )
            results.append(row)
            continue

        if len(direct) > 1:
            # If all direct relations are identical in type, still ambiguous because
            # multiple instances may carry different provenance/attributes.
            row["relation_grounding_status"] = "AMBIGUOUS_MULTIPLE_DIRECT_RELATIONS"
            row["relation_grounding_reason"] = (
                "Plusieurs relations directes A->C existent; réécriture automatique non sûre."
            )
            results.append(row)
            continue

        r = direct[0]
        rtype = relation_type(r)

        if direct_relation_is_valid(
            rtype,
            c.get("source_type"),
            c.get("target_type"),
            signatures,
        ):
            row["relation_grounding_status"] = "DIRECT_RELATION_ALREADY_VALID"
            row["relation_grounding_reason"] = (
                "La relation directe A->C respecte déjà une signature TRACE-Sepsis; "
                "aucune entité intermédiaire ne doit être imposée."
            )
            results.append(row)
            continue

        # Exact invalid/collapsed direct relation + valid two-hop chain + unique B evidence.
        row["relation_grounding_status"] = "ACTIONABLE_CHAIN_REWRITE"
        row["recommended_action"] = "CREATE_B_REPLACE_DIRECT_WITH_TWO_HOP"
        row["relation_grounding_reason"] = (
            "Une relation directe A->C existe mais n'est pas valide pour les types A/C. "
            "La chaîne A->B->C proposée respecte deux signatures verrouillées et B possède "
            "une mention documentaire explicite unique."
        )
        results.append(row)

    counts = Counter(r["relation_grounding_status"] for r in results)

    actionable = counts.get("ACTIONABLE_CHAIN_REWRITE", 0)
    protected = len(results) - actionable

    report = {
        "pattern": "B2",
        "stage": "RELATION_GROUNDING_VALIDATION",
        "input_actionability_report": str(action_path),
        "guideline": str(guideline_path),
        "summary": {
            "actionable_candidates_input": len(candidates),
            "actionable_chain_rewrite": actionable,
            "direct_relation_already_valid":
                counts.get("DIRECT_RELATION_ALREADY_VALID", 0),
            "no_direct_relational_evidence":
                counts.get("NO_DIRECT_RELATIONAL_EVIDENCE", 0),
            "ambiguous_multiple_direct_relations":
                counts.get("AMBIGUOUS_MULTIPLE_DIRECT_RELATIONS", 0),
            "invalid_chain_signature":
                counts.get("INVALID_CHAIN_SIGNATURE", 0),
            "protected": protected,
        },
        "candidates": results,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    fields = [
        "candidate_id", "document",
        "source_type", "relation_1", "middle_type_missing",
        "relation_2", "target_type", "selected_evidence",
        "relation_grounding_status", "recommended_action",
        "direct_relation_ids", "direct_relation_types",
        "relation_grounding_reason",
    ]

    with OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()

        for r in results:
            w.writerow({
                "candidate_id": r.get("candidate_id", ""),
                "document": r.get("document", ""),
                "source_type": r.get("source_type", ""),
                "relation_1": r.get("relation_1", ""),
                "middle_type_missing": r.get("middle_type_missing", ""),
                "relation_2": r.get("relation_2", ""),
                "target_type": r.get("target_type", ""),
                "selected_evidence": r.get("selected_evidence", "") or "",
                "relation_grounding_status":
                    r.get("relation_grounding_status", ""),
                "recommended_action": r.get("recommended_action", ""),
                "direct_relation_ids":
                    " | ".join(str(x) for x in r.get("direct_relation_ids", [])),
                "direct_relation_types":
                    " | ".join(str(x) for x in r.get("direct_relation_types", [])),
                "relation_grounding_reason":
                    r.get("relation_grounding_reason", ""),
            })

    print("=" * 82)
    print("SGCE - PATTERN B2 RELATION-GROUNDING VALIDATION")
    print("=" * 82)
    print(f"Candidats actionnables en entrée      : {len(candidates)}")
    print()
    print(
        f"ACTIONABLE_CHAIN_REWRITE              : "
        f"{counts.get('ACTIONABLE_CHAIN_REWRITE', 0)}"
    )
    print(
        f"DIRECT_RELATION_ALREADY_VALID         : "
        f"{counts.get('DIRECT_RELATION_ALREADY_VALID', 0)}"
    )
    print(
        f"NO_DIRECT_RELATIONAL_EVIDENCE         : "
        f"{counts.get('NO_DIRECT_RELATIONAL_EVIDENCE', 0)}"
    )
    print(
        f"AMBIGUOUS_MULTIPLE_DIRECT_RELATIONS   : "
        f"{counts.get('AMBIGUOUS_MULTIPLE_DIRECT_RELATIONS', 0)}"
    )
    print(
        f"INVALID_CHAIN_SIGNATURE               : "
        f"{counts.get('INVALID_CHAIN_SIGNATURE', 0)}"
    )
    print()
    print(f"Cas protégés                          : {protected}")
    print()
    print(f"Rapport JSON                          : {OUTPUT_JSON}")
    print(f"CSV audit                             : {OUTPUT_CSV}")
    print()
    print("Aucun JSON clinique n'a été modifié.")


if __name__ == "__main__":
    main()
