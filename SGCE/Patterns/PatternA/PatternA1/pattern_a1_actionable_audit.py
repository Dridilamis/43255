# -*- coding: utf-8 -*-
"""
pattern_a1_actionable_audit.py
==============================

Audit lisible des cas A1 potentiellement actionnables après validation.

Entrée :
    pattern_a1_validation/pattern_a1_validation_report.json

Sorties :
    pattern_a1_audit/pattern_a1_actionable_audit.json
    pattern_a1_audit/pattern_a1_actionable_audit.csv

Cas extraits :
    - MISSING_RELATION        -> LINK proposé
    - CONFIRMED_PATTERN_A     -> SPLIT proposé

IMPORTANT :
    - aucun JSON clinique n'est modifié ;
    - ce script ne confirme pas définitivement les corrections ;
    - il sert à examiner les 8 LINK et 17 SPLIT avant correction.
"""

import csv
import json
from pathlib import Path
from collections import Counter

PATTERN_A1_DIR = Path(__file__).resolve().parent
PATTERN_A_DIR = PATTERN_A1_DIR.parent
PATTERNS_DIR = PATTERN_A_DIR.parent
SGCE_DIR = PATTERNS_DIR.parent
BASE_DIR = SGCE_DIR.parent

INPUT_REPORT = PATTERN_A1_DIR / "validation" / "pattern_a1_validation_v2_report.json"

OUTPUT_DIR = PATTERN_A1_DIR / "audit"
OUTPUT_JSON = OUTPUT_DIR / "pattern_a1_actionable_audit.json"
OUTPUT_CSV = OUTPUT_DIR / "pattern_a1_actionable_audit.csv"

ACTIONABLE = {
    "MISSING_RELATION": "LINK",
    "CONFIRMED_PATTERN_A": "SPLIT",
}


def flatten_components(components):
    """
    Transforme:
      {"dose": ["40 mg"], "frequency": ["1/j"]}
    en:
      "dose=40 mg | frequency=1/j"
    """
    parts = []

    for kind, values in (components or {}).items():
        if not isinstance(values, list):
            values = [values]

        clean_values = [
            str(v).strip()
            for v in values
            if v not in (None, "")
        ]

        if clean_values:
            parts.append(
                f"{kind}=" + "; ".join(clean_values)
            )

    return " | ".join(parts)


def possible_overlap_warning(components):
    """
    Signale un point à vérifier manuellement lorsque la même chaîne
    ou une chaîne imbriquée est détectée dans plusieurs catégories.

    Exemple potentiel :
        dose = "2 g"
        rate = "2 g/24h"

    Ce n'est PAS automatiquement une erreur.
    """
    items = []

    for kind, values in (components or {}).items():
        if not isinstance(values, list):
            values = [values]

        for value in values:
            if value:
                items.append((kind, str(value).strip().lower()))

    warnings = []

    for i, (kind1, value1) in enumerate(items):
        for kind2, value2 in items[i + 1:]:
            if kind1 == kind2:
                continue

            if value1 == value2:
                warnings.append(
                    f"same_text:{kind1}<->{kind2}:{value1}"
                )
            elif value1 in value2 or value2 in value1:
                warnings.append(
                    f"nested_text:{kind1}<->{kind2}:{value1}<->{value2}"
                )

    # dédoublonnage
    return list(dict.fromkeys(warnings))


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not INPUT_REPORT.exists():
        raise FileNotFoundError(
            "Rapport de validation introuvable : "
            + str(INPUT_REPORT)
        )

    with INPUT_REPORT.open("r", encoding="utf-8") as f:
        report = json.load(f)

    results = report.get("results", [])

    actionable_rows = []

    for result in results:
        status = result.get("validation_status")

        if status not in ACTIONABLE:
            continue

        source = result.get("source_entity") or {}
        best = result.get("best_posology_match") or {}
        components = result.get("detected_components") or {}

        warnings = possible_overlap_warning(components)

        row = {
            "document": result.get("document"),
            "page": source.get("page"),
            "source_entity_id": source.get("id"),
            "traitement_name": source.get("name"),
            "traitement_preuve": source.get("preuve"),
            "detection_text": result.get("detection_text"),
            "signal_strength": result.get("signal_strength"),
            "number_component_types": result.get(
                "number_component_types"
            ),
            "detected_components": components,
            "detected_components_text": flatten_components(
                components
            ),
            "validation_status": status,
            "validation_reason": result.get(
                "validation_reason"
            ),
            "proposed_action": ACTIONABLE[status],

            # Cible POSOLOGIE pour les LINK
            "target_posology_id": best.get("target_id"),
            "target_posology_name": best.get("target_name"),
            "target_posology_preuve": best.get("target_preuve"),
            "target_posology_page": best.get("target_page"),

            # Scores
            "medication_anchor": best.get(
                "medication_anchor"
            ),
            "component_overlap": best.get(
                "component_overlap"
            ),
            "same_page_score": best.get(
                "same_page"
            ),
            "proof_overlap": best.get(
                "proof_overlap"
            ),
            "final_match_score": best.get(
                "final_score"
            ),

            # Contrôle manuel
            "component_overlap_warning": warnings,
            "needs_manual_review": True,
            "manual_decision": "",
            "manual_comment": "",
        }

        actionable_rows.append(row)

    counts = Counter(
        row["validation_status"]
        for row in actionable_rows
    )

    warning_count = sum(
        bool(row["component_overlap_warning"])
        for row in actionable_rows
    )

    output = {
        "pattern": "A1_TRAITEMENT_POSOLOGIE",
        "purpose": (
            "Audit des cas actionnables avant toute correction."
        ),
        "total_actionable_cases": len(actionable_rows),
        "status_counts": dict(counts),
        "cases_with_component_overlap_warning": warning_count,
        "instructions": {
            "LINK": (
                "Vérifier que la POSOLOGIE cible appartient bien "
                "au même traitement."
            ),
            "SPLIT": (
                "Vérifier que les informations posologiques sont "
                "explicitement contenues dans le TRAITEMENT et "
                "qu'une POSOLOGIE séparée est réellement attendue."
            ),
            "component_overlap_warning": (
                "Vérifier si deux catégories regex correspondent "
                "en réalité à une même expression posologique."
            ),
            "manual_decision_allowed": [
                "APPROVE",
                "REJECT",
                "AMBIGUOUS",
            ],
        },
        "cases": actionable_rows,
    }

    with OUTPUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(
            output,
            f,
            ensure_ascii=False,
            indent=2,
        )

    csv_fields = [
        "document",
        "page",
        "source_entity_id",
        "traitement_name",
        "traitement_preuve",
        "detection_text",
        "signal_strength",
        "number_component_types",
        "detected_components_text",
        "validation_status",
        "proposed_action",
        "target_posology_id",
        "target_posology_name",
        "target_posology_preuve",
        "target_posology_page",
        "medication_anchor",
        "component_overlap",
        "same_page_score",
        "proof_overlap",
        "final_match_score",
        "component_overlap_warning",
        "manual_decision",
        "manual_comment",
    ]

    with OUTPUT_CSV.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=csv_fields,
            extrasaction="ignore",
        )
        writer.writeheader()

        for row in actionable_rows:
            csv_row = dict(row)
            csv_row["component_overlap_warning"] = (
                " | ".join(
                    row["component_overlap_warning"]
                )
            )
            writer.writerow(csv_row)

    print("=" * 78)
    print("PATTERN A1 - AUDIT DES CAS ACTIONNABLES")
    print("=" * 78)
    print(f"Cas actionnables        : {len(actionable_rows)}")
    print(
        f"MISSING_RELATION / LINK : "
        f"{counts.get('MISSING_RELATION', 0)}"
    )
    print(
        f"PATTERN_A / SPLIT       : "
        f"{counts.get('CONFIRMED_PATTERN_A', 0)}"
    )
    print(
        f"Warnings chevauchement  : "
        f"{warning_count}"
    )
    print()
    print(f"JSON : {OUTPUT_JSON}")
    print(f"CSV  : {OUTPUT_CSV}")
    print()
    print("Aucun JSON clinique n'a été modifié.")
    print(
        "Ouvre le CSV pour examiner les cas avant correction."
    )


if __name__ == "__main__":
    main()
