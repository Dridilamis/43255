# -*- coding: utf-8 -*-
"""
root_cause_entity_validator.py
==============================

TRACE / SGCE â€” Root-Cause Entity Validator

EntrÃ©e :
  document_grounding Etage 3/root_cause/queues/root_cause_entity_candidates.json

Contexte clinique :
  SGCE/MultiAgent/corrected

Validation :
- support >= 2 relations
- ratio de convergence >= 0.60
- simulation RETYPE_ENTITY sur TOUT le document
- aucune nouvelle anomalie structurelle
- au moins une anomalie structurelle rÃ©solue
- aucun conflit concurrent sur la mÃªme entitÃ©

Statuts :
- SAFE_RETYPE
- REJECT_HARMFUL
- NO_BENEFIT
- REVIEW

Aucune donnÃ©e clinique n'est modifiÃ©e.

Sortie :
  document_grounding Etage 3/root_cause/outputs/root_cause_entity_validated.json
"""

import copy
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
STAGE3_DIR = ROOT.parent
REDUCTION_DIR = STAGE3_DIR.parent
SGCE_DIR = REDUCTION_DIR / "SGCE"

# EntrÃ©e officielle de l'Ã©tage 3 : sortie finale SGCE / Multi-Agent.

GUIDELINE_CANDIDATES = [
    REDUCTION_DIR.parent / "ontologie_sepsis_graph_v1.6.json",
    REDUCTION_DIR / "ontologie_sepsis_graph_v1.6.json",
    Path(r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM\ontologie_sepsis_graph_v1.6.json"),
]

INPUT_FILE = ROOT / "queues" / "root_cause_entity_candidates.json"
INPUT_DIR = Path(__file__).resolve().parents[2] / "SGCE" / "MultiAgent" / "corrected"
CLINICAL_DIR = INPUT_DIR
OUTPUT_FILE = ROOT / "outputs" / "root_cause_entity_validated.json"

MIN_SUPPORT = 2
MIN_SUPPORT_RATIO = 0.60

def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_guideline():
    for path in GUIDELINE_CANDIDATES:
        if path.exists():
            return path
    raise FileNotFoundError("ontologie_sepsis_graph_v1.6.json introuvable.")

def entity_id(entity):
    return (
        entity.get("identifiant_entite")
        or entity.get("id")
        or entity.get("entity_id")
    )


def entity_type(entity):
    return (
        entity.get("categorie")
        or entity.get("type")
        or entity.get("entity_type")
        or ""
    )


def relation_id(relation):
    return (
        relation.get("identifiant_relation")
        or relation.get("id")
        or relation.get("relation_id")
    )


def relation_type(relation):
    return (
        relation.get("type_relation")
        or relation.get("relation")
        or relation.get("relation_type")
        or relation.get("predicate")
        or relation.get("type")
        or ""
    )


def relation_source(relation):
    return (
        relation.get("identifiant_entite_sujet")
        or relation.get("from_id")
        or relation.get("subject_id")
        or relation.get("source")
    )


def relation_target(relation):
    return (
        relation.get("identifiant_entite_objet")
        or relation.get("to_id")
        or relation.get("object_id")
        or relation.get("target")
    )


def get_entities(doc):
    if isinstance(doc.get("global_entities"), list):
        return doc["global_entities"]

    result = []

    for page in doc.get("pages", []) or []:
        result.extend(page.get("entities", []) or [])

    return result


def get_relations(doc):
    if isinstance(doc.get("global_relations"), list):
        return doc["global_relations"]

    result = []

    for page in doc.get("pages", []) or []:
        result.extend(page.get("relations", []) or [])

    return result


def entity_lists(doc):
    lists = []

    if isinstance(doc.get("global_entities"), list):
        lists.append(doc["global_entities"])

    for page in doc.get("pages", []) or []:
        if isinstance(page.get("entities"), list):
            lists.append(page["entities"])

    return lists


def find_entity(doc, target_id):
    for entity in get_entities(doc):
        if str(entity_id(entity)) == str(target_id):
            return entity

    return None


def set_entity_type(entity, new_type):
    if "categorie" in entity:
        entity["categorie"] = new_type
    elif "entity_type" in entity:
        entity["entity_type"] = new_type
    else:
        entity["type"] = new_type


def retype_everywhere(
    doc,
    target_id,
    new_type,
):
    changed = 0

    for entities in entity_lists(doc):
        for entity in entities:
            if str(entity_id(entity)) != str(target_id):
                continue

            if entity_type(entity) != new_type:
                set_entity_type(
                    entity,
                    new_type,
                )

                changed += 1

    return changed


def load_signatures():
    guideline = load_json(resolve_guideline())
    root = guideline.get("ontologie_sepsis_graph", guideline)
    relations_root = root.get("relations", {}) or {}
    signatures = {}
    if not isinstance(relations_root, dict):
        return signatures
    for group in relations_root.values():
        if not isinstance(group, dict):
            continue
        for name, spec in group.items():
            if not isinstance(spec, dict):
                continue
            domaine = spec.get("domaine")
            image = spec.get("image")
            if domaine and image:
                signatures[name] = {"domaine": domaine, "image": image}
    return signatures

def audit_document(
    doc,
    signatures,
):
    entities = {
        str(entity_id(entity)):
            entity
        for entity in get_entities(doc)
        if entity_id(entity) is not None
    }

    anomalies = set()

    for relation in get_relations(doc):
        rid = str(
            relation_id(relation)
        )

        rtype = relation_type(
            relation
        )

        source_id = relation_source(
            relation
        )

        target_id = relation_target(
            relation
        )

        source = entities.get(
            str(source_id)
        )

        target = entities.get(
            str(target_id)
        )

        if source is None:
            anomalies.add(
                (
                    "ORPHAN_SOURCE",
                    rid,
                    str(source_id),
                )
            )

        if target is None:
            anomalies.add(
                (
                    "ORPHAN_TARGET",
                    rid,
                    str(target_id),
                )
            )

        signature = signatures.get(
            rtype
        )

        if not signature:
            continue

        if (
            source is not None
            and entity_type(source)
            != signature["domaine"]
        ):
            anomalies.add(
                (
                    "INVALID_SOURCE_TYPE",
                    rid,
                    entity_type(source),
                    signature["domaine"],
                )
            )

        if (
            target is not None
            and entity_type(target)
            != signature["image"]
        ):
            anomalies.add(
                (
                    "INVALID_TARGET_TYPE",
                    rid,
                    entity_type(target),
                    signature["image"],
                )
            )

    return anomalies


def main():
    candidates = load_json(
        INPUT_FILE
    )

    signatures = load_signatures()

    docs = {}

    for path in CLINICAL_DIR.glob("*.json"):
        if path.name.endswith("_report.json"):
            continue

        try:
            docs[path.name] = load_json(path)
        except Exception:
            pass

    # Conflict detection:
    # same document/entity with different proposed target types
    grouped = defaultdict(list)

    for item in candidates:
        key = (
            item.get("document"),
            item.get("entity_id"),
        )

        grouped[key].append(
            item
        )

    conflicts = {}

    for key, items in grouped.items():
        types = {
            x.get("proposed_type")
            for x in items
            if x.get("proposed_type")
        }

        if len(types) > 1:
            conflicts[key] = sorted(types)

    validated = []

    for item in candidates:
        document = item.get(
            "document"
        )

        target_id = item.get(
            "entity_id"
        )

        proposed_type = item.get(
            "proposed_type"
        )

        support_count = int(
            item.get(
                "support_count",
                0,
            )
            or 0
        )

        support_ratio = float(
            item.get(
                "support_ratio",
                0.0,
            )
            or 0.0
        )

        key = (
            document,
            target_id,
        )

        if key in conflicts:
            validated.append({
                "candidate_id":
                    item.get("candidate_id"),

                "document":
                    document,

                "entity_id":
                    target_id,

                "current_type":
                    item.get("current_type"),

                "proposed_type":
                    proposed_type,

                "final_status":
                    "REVIEW",

                "reason":
                    "Plusieurs types cibles concurrents pour la mÃªme entitÃ©.",

                "conflicting_types":
                    conflicts[key],
            })

            continue

        if support_count < MIN_SUPPORT:
            validated.append({
                "candidate_id":
                    item.get("candidate_id"),

                "document":
                    document,

                "entity_id":
                    target_id,

                "current_type":
                    item.get("current_type"),

                "proposed_type":
                    proposed_type,

                "final_status":
                    "REVIEW",

                "reason":
                    "Support structurel insuffisant.",
            })

            continue

        if support_ratio < MIN_SUPPORT_RATIO:
            validated.append({
                "candidate_id":
                    item.get("candidate_id"),

                "document":
                    document,

                "entity_id":
                    target_id,

                "current_type":
                    item.get("current_type"),

                "proposed_type":
                    proposed_type,

                "final_status":
                    "REVIEW",

                "reason":
                    "Convergence insuffisante vers un type unique.",
            })

            continue

        doc = docs.get(
            document
        )

        if doc is None:
            validated.append({
                "candidate_id":
                    item.get("candidate_id"),

                "document":
                    document,

                "entity_id":
                    target_id,

                "current_type":
                    item.get("current_type"),

                "proposed_type":
                    proposed_type,

                "final_status":
                    "REVIEW",

                "reason":
                    "Document clinique introuvable.",
            })

            continue

        entity = find_entity(
            doc,
            target_id,
        )

        if entity is None:
            validated.append({
                "candidate_id":
                    item.get("candidate_id"),

                "document":
                    document,

                "entity_id":
                    target_id,

                "current_type":
                    item.get("current_type"),

                "proposed_type":
                    proposed_type,

                "final_status":
                    "REVIEW",

                "reason":
                    "EntitÃ© introuvable.",
            })

            continue

        if entity_type(entity) == proposed_type:
            validated.append({
                "candidate_id":
                    item.get("candidate_id"),

                "document":
                    document,

                "entity_id":
                    target_id,

                "current_type":
                    entity_type(entity),

                "proposed_type":
                    proposed_type,

                "final_status":
                    "NO_BENEFIT",

                "reason":
                    "Le type attendu est dÃ©jÃ  appliquÃ©.",
            })

            continue

        before = audit_document(
            doc,
            signatures,
        )

        simulated = copy.deepcopy(
            doc
        )

        changed = retype_everywhere(
            simulated,
            target_id,
            proposed_type,
        )

        if changed <= 0:
            validated.append({
                "candidate_id":
                    item.get("candidate_id"),

                "document":
                    document,

                "entity_id":
                    target_id,

                "current_type":
                    item.get("current_type"),

                "proposed_type":
                    proposed_type,

                "final_status":
                    "REVIEW",

                "reason":
                    "Simulation sans modification.",
            })

            continue

        after = audit_document(
            simulated,
            signatures,
        )

        new = after - before
        resolved = before - after

        if new:
            final_status = (
                "REJECT_HARMFUL"
            )

            reason = (
                "Le retypage crÃ©e de nouvelles anomalies structurelles."
            )

        elif resolved:
            final_status = (
                "SAFE_RETYPE"
            )

            reason = (
                "Le retypage rÃ©sout des anomalies sans en crÃ©er."
            )

        else:
            final_status = (
                "NO_BENEFIT"
            )

            reason = (
                "Le retypage n'apporte aucune amÃ©lioration structurelle."
            )

        validated.append({
            "candidate_id":
                item.get("candidate_id"),

            "document":
                document,

            "entity_id":
                target_id,

            "entity_text":
                item.get("entity_text"),

            "current_type":
                entity_type(entity),

            "proposed_type":
                proposed_type,

            "support_count":
                support_count,

            "support_ratio":
                support_ratio,

            "final_status":
                final_status,

            "reason":
                reason,

            "before_anomaly_count":
                len(before),

            "after_anomaly_count":
                len(after),

            "new_anomaly_count":
                len(new),

            "resolved_anomaly_count":
                len(resolved),
        })

    status_counts = Counter(
        x.get("final_status")
        for x in validated
    )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_FILE.write_text(
        json.dumps(
            {
                "validator":
                    "root_cause_entity_validator",

                "thresholds": {
                    "min_support":
                        MIN_SUPPORT,

                    "min_support_ratio":
                        MIN_SUPPORT_RATIO,
                },

                "validated":
                    validated,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=" * 104)
    print("TRACE / SGCE - ROOT CAUSE ENTITY VALIDATOR")
    print("=" * 104)

    print(
        f"Candidats reÃ§us                      : {len(candidates)}"
    )

    print()

    print("STATUTS")
    print("-" * 104)

    for name, count in (
        status_counts.most_common()
    ):
        print(
            f"{str(name):<48}: {count}"
        )

    print()

    print(
        f"Sortie                               : {OUTPUT_FILE}"
    )

    print()

    print(
        "Aucune donnÃ©e clinique n'a Ã©tÃ© modifiÃ©e."
    )


if __name__ == "__main__":
    main()

