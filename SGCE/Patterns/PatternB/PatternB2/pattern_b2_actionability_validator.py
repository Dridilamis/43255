# -*- coding: utf-8 -*-
"""
pattern_b2_actionability_validator.py
=====================================

SGCE — Pattern B2 Actionability Validator

Input:
  pattern_b2_validation_report.json

Goal:
  Convert CONFIRMED_DOCUMENT_GROUNDED candidates into SAFE actionable cases
  only if the missing intermediate entity B can be tied to a precise,
  non-ambiguous documentary mention.

This stage DOES NOT modify clinical JSONs.
"""

import csv
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

VALIDATION_REPORT_CANDIDATES = [
    PATTERN_B2_DIR / "validation" / "pattern_b2_validation_report.json",
]

OUTPUT_DIR = PATTERN_B2_DIR / "actionability"
OUTPUT_JSON = OUTPUT_DIR / "pattern_b2_actionability_report.json"
OUTPUT_CSV = OUTPUT_DIR / "pattern_b2_actionable_candidates.csv"

def resolve_existing(candidates, label):
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(f"{label} introuvable.")


def normalize(s):
    if s is None:
        return ""
    s = str(s).strip().lower()
    return re.sub(r"\s+", " ", s)


def usable_evidence_terms(candidate):
    terms = candidate.get("evidence_terms") or []

    cleaned = []
    for t in terms:
        t = str(t).strip()
        if len(t) < 4:
            continue
        if t not in cleaned:
            cleaned.append(t)

    reduced = []
    for t in sorted(cleaned, key=len, reverse=True):
        nt = normalize(t)
        if any(nt in normalize(x) for x in reduced):
            continue
        reduced.append(t)

    return reduced


def main():
    validation_path = resolve_existing(
        VALIDATION_REPORT_CANDIDATES,
        "Rapport de validation B2"
    )

    with validation_path.open("r", encoding="utf-8") as f:
        report = json.load(f)

    candidates = report.get("validated_candidates", [])

    grounded = [
        c for c in candidates
        if c.get("validation_status") == "CONFIRMED_DOCUMENT_GROUNDED"
    ]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    seen_actionable = set()

    for c in grounded:
        evidence = usable_evidence_terms(c)

        base_key = (
            c.get("document"),
            c.get("chain_id"),
            c.get("middle_type_missing"),
            (c.get("source_entity") or {}).get("id"),
            (c.get("target_entity") or {}).get("id"),
        )

        row = {
            **c,
            "usable_evidence_terms": evidence,
            "actionability_status": None,
            "recommended_action": "NONE",
            "selected_evidence": None,
            "actionability_reason": "",
        }

        if not evidence:
            row["actionability_status"] = "NO_USABLE_EVIDENCE"
            row["actionability_reason"] = (
                "Aucune mention documentaire suffisamment exploitable."
            )

        elif len(evidence) > 1:
            row["actionability_status"] = "MULTIPLE_EVIDENCE_AMBIGUOUS"
            row["actionability_reason"] = (
                "Plusieurs mentions candidates pour l'entité intermédiaire; "
                "création automatique non sûre."
            )

        else:
            selected = evidence[0]
            dedup_key = base_key + (normalize(selected),)

            if dedup_key in seen_actionable:
                row["actionability_status"] = "REDUNDANT"
                row["actionability_reason"] = (
                    "Cas déjà représenté par un candidat actionable équivalent."
                )
            else:
                seen_actionable.add(dedup_key)
                row["actionability_status"] = "ACTIONABLE_CREATE_AND_LINK"
                row["recommended_action"] = "CREATE_AND_LINK"
                row["selected_evidence"] = selected
                row["actionability_reason"] = (
                    "Une seule mention documentaire exploitable pour l'entité "
                    "intermédiaire; cas suffisamment déterministe pour préparer "
                    "une correction automatique."
                )

        results.append(row)

    counts = Counter(r["actionability_status"] for r in results)

    summary = {
        "grounded_candidates_input": len(grounded),
        "actionable_create_and_link":
            counts.get("ACTIONABLE_CREATE_AND_LINK", 0),
        "multiple_evidence_ambiguous":
            counts.get("MULTIPLE_EVIDENCE_AMBIGUOUS", 0),
        "no_usable_evidence":
            counts.get("NO_USABLE_EVIDENCE", 0),
        "redundant":
            counts.get("REDUNDANT", 0),
        "protected":
            counts.get("MULTIPLE_EVIDENCE_AMBIGUOUS", 0)
            + counts.get("NO_USABLE_EVIDENCE", 0)
            + counts.get("REDUNDANT", 0),
    }

    out_report = {
        "pattern": "B2",
        "stage": "ACTIONABILITY_VALIDATION",
        "input_validation_report": str(validation_path),
        "summary": summary,
        "candidates": results,
    }

    OUTPUT_JSON.write_text(
        json.dumps(out_report, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    fields = [
        "candidate_id", "document", "strength",
        "source_type", "relation_1", "middle_type_missing",
        "relation_2", "target_type",
        "actionability_status", "recommended_action",
        "selected_evidence", "usable_evidence_terms",
        "actionability_reason",
    ]

    with OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()

        for r in results:
            w.writerow({
                "candidate_id": r.get("candidate_id", ""),
                "document": r.get("document", ""),
                "strength": r.get("strength", ""),
                "source_type": r.get("source_type", ""),
                "relation_1": r.get("relation_1", ""),
                "middle_type_missing": r.get("middle_type_missing", ""),
                "relation_2": r.get("relation_2", ""),
                "target_type": r.get("target_type", ""),
                "actionability_status": r.get("actionability_status", ""),
                "recommended_action": r.get("recommended_action", ""),
                "selected_evidence": r.get("selected_evidence", "") or "",
                "usable_evidence_terms": " | ".join(
                    r.get("usable_evidence_terms", [])
                ),
                "actionability_reason": r.get("actionability_reason", ""),
            })

    print("=" * 82)
    print("SGCE - PATTERN B2 ACTIONABILITY VALIDATION")
    print("=" * 82)
    print(f"Rapport entrée                  : {validation_path}")
    print()
    print(f"Candidats grounded en entrée   : {len(grounded)}")
    print(
        f"ACTIONABLE_CREATE_AND_LINK     : "
        f"{counts.get('ACTIONABLE_CREATE_AND_LINK', 0)}"
    )
    print(
        f"MULTIPLE_EVIDENCE_AMBIGUOUS    : "
        f"{counts.get('MULTIPLE_EVIDENCE_AMBIGUOUS', 0)}"
    )
    print(
        f"NO_USABLE_EVIDENCE             : "
        f"{counts.get('NO_USABLE_EVIDENCE', 0)}"
    )
    print(
        f"REDUNDANT                      : "
        f"{counts.get('REDUNDANT', 0)}"
    )
    print()
    print(f"Cas protégés                   : {summary['protected']}")
    print()
    print(f"Rapport JSON                   : {OUTPUT_JSON}")
    print(f"CSV audit                      : {OUTPUT_CSV}")
    print()
    print("Aucun JSON clinique n'a été modifié.")


if __name__ == "__main__":
    main()
