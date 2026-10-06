# -*- coding: utf-8 -*-
"""
numeric_unit_safe_corrector.py
==============================

TEXT-GUIDED SAFE REPAIR WITH BEFORE/AFTER TRACE

Applique uniquement les SAFE_ACCEPT :
- SET_UNIT
- SET_VALUE_AND_UNIT
- NORMALIZE_UNIT

Le rapport contient désormais pour chaque correction :
- before_value
- before_unit
- after_value
- after_unit
- text_evidence
- confidence
- action
- status

Baseline :
  ontology Etage 4/ontology_duplicates/duplicate_entities/duplicate_entity_safe_merged

Sortie :
  numeric_unit Etage 5/numeric_unit_safe_corrected
"""

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REDUCTION_DIR = ROOT.parent
SOURCE_DIR = (REDUCTION_DIR / "ontology Etage 4" / "ontology_duplicates"
              / "duplicate_entities" / "duplicate_entity_safe_merged")
INPUT_FILE = ROOT / "outputs" / "numeric_unit_validated.json"
OUTPUT_DIR = ROOT / "numeric_unit_safe_corrected"
REPORT_FILE = OUTPUT_DIR / "numeric_unit_correction_report.json"


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def entity_id(e):
    return e.get("identifiant_entite") or e.get("id") or e.get("entity_id")


def entity_lists(doc):
    lists = []

    if isinstance(doc.get("global_entities"), list):
        lists.append(doc["global_entities"])

    for page in doc.get("pages", []) or []:
        if isinstance(page.get("entities"), list):
            lists.append(page["entities"])

    return lists


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


def get_value(entity, mode):
    if mode == "POSOLOGY_DOSE":
        if "dose_valeur" in entity:
            return entity.get("dose_valeur")

    if mode == "POSOLOGY_FLOW":
        if "debit" in entity:
            return entity.get("debit")

    if mode == "POSOLOGY_VOLUME":
        if "volume" in entity:
            return entity.get("volume")

    for key in ("valeur", "value", "valeur_mesuree"):
        if key in entity:
            return entity.get(key)

    return None


def get_unit(entity, mode):
    if mode == "POSOLOGY_DOSE":
        if "unite_dose" in entity:
            return entity.get("unite_dose")

    if mode == "POSOLOGY_FLOW":
        if "unite_debit" in entity:
            return entity.get("unite_debit")

    if mode == "POSOLOGY_VOLUME":
        if "unite_volume" in entity:
            return entity.get("unite_volume")

    for key in ("unite", "unit", "unite_mesure"):
        if key in entity:
            return entity.get(key)

    return None


def set_value(entity, new_value, mode):
    if mode == "POSOLOGY_DOSE" and "dose_valeur" in entity:
        entity["dose_valeur"] = new_value
        return True

    if mode == "POSOLOGY_FLOW" and "debit" in entity:
        entity["debit"] = new_value
        return True

    if mode == "POSOLOGY_VOLUME" and "volume" in entity:
        entity["volume"] = new_value
        return True

    for key in ("valeur", "value", "valeur_mesuree"):
        if key in entity:
            entity[key] = new_value
            return True

    return False


def set_unit(entity, new_unit, mode):
    if mode == "POSOLOGY_DOSE" and "unite_dose" in entity:
        entity["unite_dose"] = new_unit
        return True

    if mode == "POSOLOGY_FLOW" and "unite_debit" in entity:
        entity["unite_debit"] = new_unit
        return True

    if mode == "POSOLOGY_VOLUME" and "unite_volume" in entity:
        entity["unite_volume"] = new_unit
        return True

    for key in ("unite", "unit", "unite_mesure"):
        if key in entity:
            entity[key] = new_unit
            return True

    if any(
        key in entity
        for key in (
            "valeur",
            "value",
            "valeur_mesuree",
            "dose_valeur",
            "debit",
            "volume",
        )
    ):
        entity["unite"] = new_unit
        return True

    return False


def _action_priority(action):
    return {"SET_VALUE_AND_UNIT": 3, "SET_UNIT": 2, "NORMALIZE_UNIT": 1}.get(action.get("action"), 0)


def _evidence_priority(action):
    ev = action.get("validated_evidence") or action.get("text_evidence") or {}
    source = ev.get("source") if isinstance(ev, dict) else None
    return {"RAW_VALUE": 5, "ENTITY_TEXT": 4, "SENTENCE": 3,
            "PREVIOUS_SENTENCE": 1, "NEXT_SENTENCE": 1}.get(source, 0)


def consolidate_safe_actions(actions):
    """V7.1: une seule action par slot logique (document, entity_id, mode).

    Les modes différents d'une même entité ne sont PAS fusionnés aveuglément :
    ils peuvent représenter des champs cliniques distincts (VALUE, dose, débit,
    volume). Ils restent applicables, mais le rapport compte aussi les entités
    uniques corrigées afin de ne pas gonfler le nombre de corrections logiques.
    """
    groups = {}
    for action in actions:
        key = (str(action.get("document")), str(action.get("entity_id")), str(action.get("mode")))
        groups.setdefault(key, []).append(action)

    consolidated = []
    conflicts = []
    merged_count = 0

    for key, group in groups.items():
        if len(group) == 1:
            consolidated.append(group[0])
            continue

        # Vérifier la compatibilité des cibles proposées.
        units = {str(x.get("validated_unit")) for x in group if x.get("validated_unit") not in (None, "")}
        values = {str(x.get("validated_value")) for x in group
                  if x.get("action") == "SET_VALUE_AND_UNIT" and x.get("validated_value") not in (None, "")}

        if len(units) > 1 or len(values) > 1:
            conflicts.append({
                "document": key[0], "entity_id": key[1], "mode": key[2],
                "reason": "CONFLICTING_SAFE_ACTIONS_PROTECTED",
                "candidate_ids": [x.get("candidate_id") for x in group],
                "validated_units": sorted(units), "validated_values": sorted(values),
            })
            continue

        best = sorted(group, key=lambda x: (_action_priority(x), _evidence_priority(x)), reverse=True)[0]
        best = dict(best)
        best["merged_candidate_ids"] = [x.get("candidate_id") for x in group]
        best["merged_actions_count"] = len(group)
        consolidated.append(best)
        merged_count += len(group) - 1

    return consolidated, conflicts, merged_count


def main():
    payload = load_json(INPUT_FILE)

    actions = [
        item
        for item in payload.get("validated", [])
        if (
            item.get("status") == "SAFE_ACCEPT"
            and item.get("action") in {
                "SET_UNIT",
                "SET_VALUE_AND_UNIT",
                "NORMALIZE_UNIT",
            }
        )
    ]

    raw_safe_actions = list(actions)
    actions, consolidation_conflicts, merged_actions = consolidate_safe_actions(actions)

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    docs = [
        p
        for p in sorted(SOURCE_DIR.glob("*.json"))
        if is_clinical(p)
    ]

    for src in docs:
        shutil.copy2(src, OUTPUT_DIR / src.name)

    modified_docs = set()
    operations = []
    errors = []

    for action in actions:
        document = action.get("document")
        target_id = str(action.get("entity_id"))
        mode = action.get("mode")
        final_action = action.get("action")
        new_value = action.get("validated_value")
        new_unit = action.get("validated_unit")

        path = OUTPUT_DIR / str(document)

        if not path.exists():
            errors.append({
                "document": document,
                "entity_id": target_id,
                "error": "DOCUMENT_NOT_FOUND",
            })
            continue

        doc = load_json(path)

        found = 0
        changed = 0

        logical_before_value = None
        logical_before_unit = None
        logical_after_value = None
        logical_after_unit = None

        for e_list in entity_lists(doc):
            for entity in e_list:
                if str(entity_id(entity)) != target_id:
                    continue

                found += 1

                before_value = get_value(entity, mode)
                before_unit = get_unit(entity, mode)

                if logical_before_value is None:
                    logical_before_value = before_value
                if logical_before_unit is None:
                    logical_before_unit = before_unit

                before_dump = json.dumps(
                    entity,
                    ensure_ascii=False,
                    sort_keys=True,
                )

                if final_action == "SET_VALUE_AND_UNIT":
                    set_value(entity, new_value, mode)
                    set_unit(entity, new_unit, mode)

                elif final_action in ("SET_UNIT", "NORMALIZE_UNIT"):
                    set_unit(entity, new_unit, mode)

                entity["trace_numeric_unit_repair"] = {
                    "action": final_action,
                    "before_value": before_value,
                    "before_unit": before_unit,
                    "after_value": get_value(entity, mode),
                    "after_unit": get_unit(entity, mode),
                    "text_evidence": (
                        action.get("validated_evidence")
                        or action.get("text_evidence")
                    ),
                    "confidence": action.get("confidence"),
                    "source": "TRACE_SGCE_TEXT_GUIDED_NUMERIC_UNIT_REPAIR",
                }

                after_dump = json.dumps(
                    entity,
                    ensure_ascii=False,
                    sort_keys=True,
                )

                logical_after_value = get_value(entity, mode)
                logical_after_unit = get_unit(entity, mode)

                if before_dump != after_dump:
                    changed += 1

        if found == 0:
            errors.append({
                "document": document,
                "entity_id": target_id,
                "error": "ENTITY_NOT_FOUND",
            })
            continue

        if changed > 0:
            path.write_text(
                json.dumps(
                    doc,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            modified_docs.add(document)

        effective_change = (
            logical_before_value != logical_after_value
            or logical_before_unit != logical_after_unit
        )

        operations.append({
            "document": document,
            "entity_id": target_id,
            "entity_type": action.get("entity_type"),
            "parameter": action.get("parameter"),
            "mode": mode,
            "action": final_action,

            "before_value": logical_before_value,
            "before_unit": logical_before_unit,

            "after_value": logical_after_value,
            "after_unit": logical_after_unit,

            "text_evidence": (
                        action.get("validated_evidence")
                        or action.get("text_evidence")
                    ),
            "sentence": action.get("sentence"),
            "confidence": action.get("confidence"),

            "physical_occurrences_changed": changed,
            "effective_clinical_change": effective_change,

            "status": (
                "APPLIED"
                if changed > 0
                else "ALREADY_SATISFIED"
            ),
        })

    applied_ops = [
        x for x in operations
        if x.get("status") == "APPLIED"
    ]

    effective_ops = [
        x for x in applied_ops
        if x.get("effective_clinical_change") is True
    ]

    unique_entities_corrected = {
        (str(x.get("document")), str(x.get("entity_id")))
        for x in effective_ops
    }
    entities_with_multiple_slots = {}
    for x in effective_ops:
        k = (str(x.get("document")), str(x.get("entity_id")))
        entities_with_multiple_slots.setdefault(k, set()).add(str(x.get("mode")))
    entities_with_multiple_slots = {
        f"{k[0]}::{k[1]}": sorted(v)
        for k, v in entities_with_multiple_slots.items() if len(v) > 1
    }

    report = {
        "corrector": "numeric_unit_safe_corrector",
        "mode": "TEXT_GUIDED_SAFE_REPAIR_WITH_TRACE",

        "summary": {
            "safe_actions_received_raw": len(raw_safe_actions),
            "safe_actions_after_slot_consolidation": len(actions),
            "same_slot_actions_merged": merged_actions,
            "consolidation_conflicts_protected": len(consolidation_conflicts),
            "documents_copied": len(docs),
            "operations_applied": len(applied_ops),
            "effective_slot_changes": len(effective_ops),
            "unique_entities_corrected": len(unique_entities_corrected),
            "entities_with_multiple_numeric_slots_corrected": len(entities_with_multiple_slots),
            "documents_modified": len(modified_docs),
            "errors": len(errors),
        },

        "operations": operations,
        "consolidation_conflicts": consolidation_conflicts,
        "entities_with_multiple_slots": entities_with_multiple_slots,
        "errors": errors,
    }

    REPORT_FILE.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=" * 112)
    print("TRACE / SGCE - NUMERIC UNIT SAFE CORRECTOR - BEFORE/AFTER TRACE")
    print("=" * 112)
    print(f"Actions SAFE_ACCEPT reçues (brut)   : {len(raw_safe_actions)}")
    print(f"Actions après fusion même slot      : {len(actions)}")
    print(f"Actions même slot fusionnées        : {merged_actions}")
    print(f"Conflits protégés                   : {len(consolidation_conflicts)}")
    print(f"Documents copiés                    : {len(docs)}")
    print(f"Opérations appliquées               : {len(applied_ops)}")
    print(f"Corrections de slots effectives     : {len(effective_ops)}")
    print(f"Entités logiques corrigées          : {len(unique_entities_corrected)}")
    print(f"Entités multi-slots corrigées       : {len(entities_with_multiple_slots)}")
    print(f"Documents modifiés                  : {len(modified_docs)}")
    print(f"Erreurs                             : {len(errors)}")
    print()
    print("CORRECTIONS AVANT -> APRES")
    print("-" * 112)

    for op in effective_ops:
        print(
            f"{op['document']} | {op['entity_id']} | {op['action']}"
        )
        print(
            f"  AVANT : valeur={op['before_value']!r} | unité={op['before_unit']!r}"
        )
        print(
            f"  APRES : valeur={op['after_value']!r} | unité={op['after_unit']!r}"
        )
        print(
            f"  PREUVE: {op.get('text_evidence')}"
        )
        print()

    print(f"Sortie clinique                     : {OUTPUT_DIR}")
    print(f"Rapport                             : {REPORT_FILE}")
    print()
    print("Les fichiers sources n'ont pas été modifiés.")


if __name__ == "__main__":
    main()
