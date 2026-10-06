# -*- coding: utf-8 -*-
"""
numeric_unit_post_validator.py
==============================

Post-validation renforcée avec preuve avant/après.

Vérifie :
- toutes les opérations APPLIED ;
- aucune relation modifiée ;
- les corrections annoncées ont réellement changé valeur et/ou unité ;
- aucun document perdu ou ajouté.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REDUCTION_DIR = ROOT.parent
BEFORE_DIR = (REDUCTION_DIR / "ontology Etage 4" / "ontology_duplicates"
              / "duplicate_entities" / "duplicate_entity_safe_merged")
AFTER_DIR = ROOT / "numeric_unit_safe_corrected"
CORRECTION_REPORT = AFTER_DIR / "numeric_unit_correction_report.json"
OUTPUT_FILE = ROOT / "post_validation" / "numeric_unit_post_validation_report.json"
OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def is_clinical(path):
    if path.name.endswith("_report.json"):
        return False

    try:
        doc = load_json(path)
    except Exception:
        return False

    return (
        isinstance(doc, dict)
        and any(
            k in doc
            for k in ("pages", "global_entities", "global_relations")
        )
    )


def relation_dump(doc):
    if isinstance(doc.get("global_relations"), list):
        rels = doc["global_relations"]
    else:
        rels = [
            r
            for p in doc.get("pages", []) or []
            for r in p.get("relations", []) or []
        ]

    return json.dumps(
        rels,
        ensure_ascii=False,
        sort_keys=True,
    )


def main():
    correction = load_json(CORRECTION_REPORT)

    before_files = {
        p.name: p
        for p in BEFORE_DIR.glob("*.json")
        if is_clinical(p)
    }

    after_files = {
        p.name: p
        for p in AFTER_DIR.glob("*.json")
        if is_clinical(p)
    }

    missing = sorted(
        set(before_files) - set(after_files)
    )

    extra = sorted(
        set(after_files) - set(before_files)
    )

    relation_changes = []

    for name in sorted(
        set(before_files) & set(after_files)
    ):
        before = load_json(before_files[name])
        after = load_json(after_files[name])

        if relation_dump(before) != relation_dump(after):
            relation_changes.append(name)

    applied_ops = [
        op
        for op in correction.get("operations", [])
        if op.get("status") == "APPLIED"
    ]

    ineffective_ops = []

    for op in applied_ops:
        before_value = op.get("before_value")
        before_unit = op.get("before_unit")
        after_value = op.get("after_value")
        after_unit = op.get("after_unit")

        changed = (
            before_value != after_value
            or before_unit != after_unit
        )

        if not changed:
            ineffective_ops.append(op)

    # V7.1 - contrôle de l'unicité des opérations par slot logique.
    slot_keys = []
    entity_keys = []
    for op in applied_ops:
        slot_keys.append((str(op.get("document")), str(op.get("entity_id")), str(op.get("mode"))))
        entity_keys.append((str(op.get("document")), str(op.get("entity_id"))))

    duplicate_slot_operations = []
    seen_slots = set()
    for key in slot_keys:
        if key in seen_slots and key not in duplicate_slot_operations:
            duplicate_slot_operations.append(key)
        seen_slots.add(key)

    unique_entities_corrected = len(set(entity_keys))
    unique_slots_corrected = len(set(slot_keys))

    consolidation_conflicts = correction.get("consolidation_conflicts", []) or []

    passed = (
        not missing
        and not extra
        and not relation_changes
        and not ineffective_ops
        and not duplicate_slot_operations
        and correction.get("summary", {}).get("errors", 0) == 0
    )

    report = {
        "post_validator":
            "numeric_unit_post_validator",

        "mode":
            "TEXT_GUIDED_SAFE_REPAIR_WITH_TRACE",

        "summary": {
            "documents_checked":
                len(before_files),

            "applied_operations":
                len(applied_ops),

            "effective_slot_operations":
                len(applied_ops) - len(ineffective_ops),

            "unique_slots_corrected":
                unique_slots_corrected,

            "unique_entities_corrected":
                unique_entities_corrected,

            "duplicate_slot_operations":
                len(duplicate_slot_operations),

            "consolidation_conflicts_protected":
                len(consolidation_conflicts),

            "ineffective_operations":
                len(ineffective_ops),

            "documents_with_relation_changes":
                len(relation_changes),

            "missing_documents_after":
                len(missing),

            "extra_documents_after":
                len(extra),

            "status":
                "PASS" if passed else "FAIL",
        },

        "ineffective_operations":
            ineffective_ops,

        "relation_changes":
            relation_changes,

        "duplicate_slot_operations":
            [list(x) for x in duplicate_slot_operations],

        "consolidation_conflicts_protected":
            consolidation_conflicts,
    }

    OUTPUT_FILE.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=" * 112)
    print("TRACE / SGCE - NUMERIC UNIT POST-VALIDATION - BEFORE/AFTER TRACE")
    print("=" * 112)
    print(f"Documents vérifiés                  : {len(before_files)}")
    print(f"Opérations appliquées               : {len(applied_ops)}")
    print(f"Corrections de slots effectives     : {len(applied_ops) - len(ineffective_ops)}")
    print(f"Slots logiques uniques corrigés     : {unique_slots_corrected}")
    print(f"Entités logiques uniques corrigées  : {unique_entities_corrected}")
    print(f"Doublons d'opération même slot      : {len(duplicate_slot_operations)}")
    print(f"Conflits protégés                   : {len(consolidation_conflicts)}")
    print(f"Opérations sans changement réel     : {len(ineffective_ops)}")
    print(f"Documents avec relations modifiées  : {len(relation_changes)}")
    print()
    print(f"Docs manquants APRES                : {len(missing)}")
    print(f"Docs supplémentaires APRES          : {len(extra)}")
    print()
    print(
        f"STATUT FINAL NUMERIC UNIT REPAIR    : "
        f"{'PASS' if passed else 'FAIL'}"
    )
    print()
    print(f"Rapport                             : {OUTPUT_FILE}")
    print()
    print(
        "Aucune donnée clinique n'a été modifiée "
        "par ce post-validateur."
    )


if __name__ == "__main__":
    main()
