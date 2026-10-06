# -*- coding: utf-8 -*-
"""
pattern_a6_auto_corrector.py
============================

SGCE — Pattern A6 Auto-Corrector / Pass-through

A6:
DONNEE_PATIENT --presente_symptome--> SYMPTOME

Run actuel:
- 13 ALREADY_CORRECT
- 0 MISSING_RELATION
- 0 CONFIRMED_PATTERN_A
- 0 AMBIGUOUS

Donc:
- 0 LINK
- 0 SPLIT
- 13 SKIP
- aucun contenu clinique modifié

Le but est de produire PatternA6/pattern_a6_corrected
pour conserver la continuité du pipeline.
"""

import json
import copy
from collections import Counter
from pathlib import Path


PATTERN_A6_DIR = Path(__file__).resolve().parent
PATTERN_A_DIR = PATTERN_A6_DIR.parent
PATTERNS_DIR = PATTERN_A_DIR.parent
SGCE_DIR = PATTERNS_DIR.parent
BASE_DIR = SGCE_DIR.parent
PATTERN_A5_DIR = PATTERN_A_DIR / "PatternA5"

INPUT_DIR_CANDIDATES = [
    PATTERN_A5_DIR / "corrected",
]

VALIDATION_REPORT_CANDIDATES = [
    PATTERN_A6_DIR / "validation" / "pattern_a6_validation_report.json",
]

OUTPUT_DIR = PATTERN_A6_DIR / "corrected"
REPORT_PATH = OUTPUT_DIR / "pattern_a6_correction_report.json"

def resolve_input_dir():
    for p in INPUT_DIR_CANDIDATES:
        if p.exists() and any(p.glob("*.json")):
            return p
    raise FileNotFoundError("Dossier clinique d'entrée A6 introuvable.")


def resolve_validation_report():
    for p in VALIDATION_REPORT_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError("Rapport de validation A6 introuvable.")


def is_clinical_document(doc):
    return (
        isinstance(doc, dict)
        and (
            isinstance(doc.get("global_entities"), list)
            or isinstance(doc.get("pages"), list)
        )
    )


def main():
    input_dir = resolve_input_dir()
    validation_report = resolve_validation_report()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    validation = json.loads(
        validation_report.read_text(encoding="utf-8")
    )

    validated = validation.get("validated_candidates", [])

    status_counts = Counter(
        item.get("validation_status", "")
        for item in validated
    )

    operations = []
    for item in validated:
        status = item.get("validation_status")
        source = item.get("source_entity") or {}

        if status == "ALREADY_CORRECT":
            operations.append({
                "document": item.get("document"),
                "operation": "SKIP",
                "source_entity_id": source.get("entity_id"),
                "reason": "ALREADY_CORRECT",
                "modified": False,
            })
        elif status == "AMBIGUOUS":
            operations.append({
                "document": item.get("document"),
                "operation": "SKIP",
                "source_entity_id": source.get("entity_id"),
                "reason": "AMBIGUOUS_PROTECTED",
                "modified": False,
            })
        else:
            # Sécurité : ce script ne doit rien corriger dans le run actuel.
            operations.append({
                "document": item.get("document"),
                "operation": "SKIP",
                "source_entity_id": source.get("entity_id"),
                "reason": f"UNEXPECTED_STATUS_{status}",
                "modified": False,
            })

    copied = 0
    modified = 0
    skipped_nonclinical = []
    errors = []

    for path in sorted(input_dir.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))

            if not is_clinical_document(doc):
                skipped_nonclinical.append(path.name)
                continue

            # copie exacte sémantiquement, aucune correction
            out_doc = copy.deepcopy(doc)

            (OUTPUT_DIR / path.name).write_text(
                json.dumps(out_doc, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            copied += 1

        except Exception as exc:
            errors.append({
                "document": path.name,
                "error": str(exc),
            })

    report = {
        "pattern": "A6",
        "name": "DONNEE_PATIENT + SYMPTOME",
        "relation": "presente_symptome",
        "mode": "PASS_THROUGH_NO_CORRECTION_REQUIRED",
        "input_directory": str(input_dir),
        "validation_report": str(validation_report),
        "output_directory": str(OUTPUT_DIR),

        "summary": {
            "validated_candidates": len(validated),
            "already_correct": status_counts.get("ALREADY_CORRECT", 0),
            "missing_relation": status_counts.get("MISSING_RELATION", 0),
            "confirmed_pattern_a": status_counts.get("CONFIRMED_PATTERN_A", 0),
            "ambiguous": status_counts.get("AMBIGUOUS", 0),

            "operations_applied": 0,
            "link": 0,
            "split": 0,
            "skip": len(operations),

            "documents_copied": copied,
            "documents_modified": modified,
            "nonclinical_json_skipped": len(skipped_nonclinical),
            "errors": len(errors),
        },

        "operations": operations,
        "nonclinical_json_skipped": skipped_nonclinical,
        "errors": errors,
    }

    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("=" * 76)
    print("SGCE - PATTERN A6 AUTOMATIC CORRECTION")
    print("=" * 76)
    print(f"Entrée                  : {input_dir}")
    print(f"Validation              : {validation_report}")
    print(f"Sortie                  : {OUTPUT_DIR}")
    print()
    print(f"Candidats validés       : {len(validated)}")
    print(f"ALREADY_CORRECT         : {status_counts.get('ALREADY_CORRECT', 0)}")
    print(f"MISSING_RELATION        : {status_counts.get('MISSING_RELATION', 0)}")
    print(f"CONFIRMED_PATTERN_A     : {status_counts.get('CONFIRMED_PATTERN_A', 0)}")
    print(f"AMBIGUOUS               : {status_counts.get('AMBIGUOUS', 0)}")
    print()
    print("Opérations appliquées   : 0")
    print("LINK                    : 0")
    print("SPLIT                   : 0")
    print(f"SKIP                    : {len(operations)}")
    print()
    print(f"Documents copiés        : {copied}")
    print(f"Documents modifiés      : {modified}")
    print(f"JSON non cliniques ignorés : {len(skipped_nonclinical)}")
    print(f"Erreurs                 : {len(errors)}")
    print()
    print(f"Rapport                 : {REPORT_PATH}")
    print()
    print("Aucune correction clinique n'a été appliquée.")


if __name__ == "__main__":
    main()
