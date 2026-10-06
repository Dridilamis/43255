# -*- coding: utf-8 -*-
"""
relation_repair_batch_impact_validator.py
=========================================

Validation transactionnelle/cumulative des corrections relationnelles.

Source saine :
  MultiAgent/multiagent_safe_final_corrected

Entrée :
  MultiAgent/relation_repair/outputs/relation_repair_validated_decisions.json

Principe :
- prend uniquement les décisions ACCEPT précédentes
- déduplique les actions identiques
- ordre de priorité :
    1) REPLACE_RELATION
    2) RETYPE_SOURCE
    3) RETYPE_TARGET
- applique chaque correction sur une COPIE DE TRAVAIL cumulative
- après chaque action, audite TOUT LE DOCUMENT
- SAFE_ACCEPT seulement si :
    * 0 nouvelle anomalie
    * >= 1 anomalie résolue
- si rejetée, rollback automatique
- aucun JSON clinique n'est modifié

Sortie :
  MultiAgent/relation_repair/outputs/relation_repair_batch_safe_actions.json
"""

import copy
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
SGCE_DIR = HERE.parent
BASE_DIR = SGCE_DIR.parent
BASELINE_DIR = SGCE_DIR / "Patterns" / "PatternD" / "corrected"
VALIDATED_FILE = HERE / "outputs" / "relation_repair_validated_decisions.json"
GUIDELINE_CANDIDATES = [
    BASE_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
    BASE_DIR.parent / "Guideline_TRACE_Sepsis_v1.6.json",
    Path.cwd() / "Guideline_TRACE_Sepsis_v1.6.json",
    HERE / "Guideline_TRACE_Sepsis_v1.6.json",
]
OUTPUT_FILE = HERE / "outputs" / "relation_repair_batch_safe_actions.json"


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def resolve_guideline():
    for p in GUIDELINE_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError("Guideline TRACE introuvable.")


def entity_id(e):
    return e.get("identifiant_entite") or e.get("id") or e.get("entity_id")


def entity_type(e):
    return e.get("categorie") or e.get("type") or e.get("entity_type") or ""


def relation_id(r):
    return r.get("identifiant_relation") or r.get("id") or r.get("relation_id")


def relation_type(r):
    return (
        r.get("type_relation")
        or r.get("relation")
        or r.get("relation_type")
        or r.get("predicate")
        or r.get("type")
        or ""
    )


def relation_source(r):
    return (
        r.get("identifiant_entite_sujet")
        or r.get("from_id")
        or r.get("subject_id")
        or r.get("source")
    )


def relation_target(r):
    return (
        r.get("identifiant_entite_objet")
        or r.get("to_id")
        or r.get("object_id")
        or r.get("target")
    )


def get_entities(doc):
    if isinstance(doc.get("global_entities"), list):
        return doc["global_entities"]
    out=[]
    for p in doc.get("pages",[]) or []:
        out.extend(p.get("entities",[]) or [])
    return out


def get_relations(doc):
    if isinstance(doc.get("global_relations"), list):
        return doc["global_relations"]
    out=[]
    for p in doc.get("pages",[]) or []:
        out.extend(p.get("relations",[]) or [])
    return out


def find_entity(doc, target_id):
    return next(
        (e for e in get_entities(doc) if str(entity_id(e)) == str(target_id)),
        None,
    )


def find_relation(doc, target_id):
    return next(
        (r for r in get_relations(doc) if str(relation_id(r)) == str(target_id)),
        None,
    )


def set_entity_type(entity, new_type):
    if "categorie" in entity:
        entity["categorie"] = new_type
    elif "entity_type" in entity:
        entity["entity_type"] = new_type
    else:
        entity["type"] = new_type


def set_relation_type(relation, new_type):
    if "type_relation" in relation:
        relation["type_relation"] = new_type
    elif "relation_type" in relation:
        relation["relation_type"] = new_type
    elif "predicate" in relation:
        relation["predicate"] = new_type
    elif "relation" in relation:
        relation["relation"] = new_type
    else:
        relation["type"] = new_type


def load_signatures():
    data = load_json(resolve_guideline())
    root = data.get("ontologie_sepsis_graph", data)
    locked = root.get("signatures_relations_verrouillees_v1_5", {})

    result = {}

    for name, spec in (
        locked.items()
        if isinstance(locked, dict)
        else []
    ):
        if (
            isinstance(spec, dict)
            and spec.get("domaine")
            and spec.get("image")
        ):
            result[name] = {
                "domaine": spec["domaine"],
                "image": spec["image"],
            }

    return result


def audit_document(doc, signatures):
    entity_map = {
        str(entity_id(e)): e
        for e in get_entities(doc)
        if entity_id(e) is not None
    }

    anomalies = set()

    for r in get_relations(doc):
        rid = str(relation_id(r))
        rtype = relation_type(r)
        sid = relation_source(r)
        tid = relation_target(r)

        source = entity_map.get(str(sid))
        target = entity_map.get(str(tid))

        if source is None:
            anomalies.add(("ORPHAN_SOURCE", rid, str(sid)))

        if target is None:
            anomalies.add(("ORPHAN_TARGET", rid, str(tid)))

        sig = signatures.get(rtype)

        if not sig:
            anomalies.add(("UNAUTHORIZED_RELATION", rid, str(rtype)))
            continue

        if (
            source is not None
            and entity_type(source) != sig["domaine"]
        ):
            anomalies.add(
                (
                    "INVALID_SOURCE_TYPE",
                    rid,
                    entity_type(source),
                    sig["domaine"],
                )
            )

        if (
            target is not None
            and entity_type(target) != sig["image"]
        ):
            anomalies.add(
                (
                    "INVALID_TARGET_TYPE",
                    rid,
                    entity_type(target),
                    sig["image"],
                )
            )

    return anomalies


def apply_action(doc, action, params):
    if action == "REPLACE_RELATION":
        relation = find_relation(doc, params.get("relation_id"))

        if relation is None:
            return False, "RELATION_NOT_FOUND"

        new_type = params.get("new_relation_type")

        if not new_type:
            return False, "NEW_RELATION_TYPE_MISSING"

        if relation_type(relation) == new_type:
            return False, "ALREADY_SATISFIED"

        set_relation_type(relation, new_type)
        return True, "APPLIED"

    if action in ("RETYPE_SOURCE", "RETYPE_TARGET"):
        entity = find_entity(doc, params.get("entity_id"))

        if entity is None:
            return False, "ENTITY_NOT_FOUND"

        new_type = params.get("new_type")

        if not new_type:
            return False, "NEW_ENTITY_TYPE_MISSING"

        if entity_type(entity) == new_type:
            return False, "ALREADY_SATISFIED"

        set_entity_type(entity, new_type)
        return True, "APPLIED"

    return False, "UNSUPPORTED_ACTION"


def action_signature(item):
    d = item.get("agent_decision") or {}
    action = item.get("final_action")
    p = d.get("parameters") or {}

    if action == "REPLACE_RELATION":
        return (
            item.get("document"),
            action,
            p.get("relation_id"),
            p.get("new_relation_type"),
        )

    return (
        item.get("document"),
        action,
        p.get("entity_id"),
        p.get("new_type"),
    )


def action_priority(item):
    return {
        "REPLACE_RELATION": 0,
        "RETYPE_SOURCE": 1,
        "RETYPE_TARGET": 2,
    }.get(item.get("final_action"), 99)


def main():
    if not BASELINE_DIR.exists():
        raise FileNotFoundError(
            f"Baseline introuvable : {BASELINE_DIR}"
        )

    payload = load_json(VALIDATED_FILE)

    accepted = [
        item
        for item in payload.get("validated_decisions", [])
        if item.get("final_status") == "ACCEPT"
    ]

    # Deduplicate exact actions
    unique = []
    seen = set()
    duplicates = 0

    for item in accepted:
        sig = action_signature(item)

        if sig in seen:
            duplicates += 1
            continue

        seen.add(sig)
        unique.append(item)

    # Relation replacement first; then entity retyping
    unique.sort(
        key=lambda x: (
            str(x.get("document")),
            action_priority(x),
            str(x.get("candidate_id")),
        )
    )

    signatures = load_signatures()

    working_docs = {}

    for path in BASELINE_DIR.glob("*.json"):
        if path.name.endswith("_report.json"):
            continue

        try:
            doc = load_json(path)

            if (
                isinstance(doc, dict)
                and any(
                    k in doc
                    for k in (
                        "pages",
                        "global_entities",
                        "global_relations",
                    )
                )
            ):
                working_docs[path.name] = doc

        except Exception:
            pass

    current_anomalies = {
        name: audit_document(doc, signatures)
        for name, doc in working_docs.items()
    }

    baseline_anomaly_total = sum(
        len(v)
        for v in current_anomalies.values()
    )

    results = []
    safe_actions = []

    for item in unique:
        document = item.get("document")
        action = item.get("final_action")
        d = item.get("agent_decision") or {}
        params = d.get("parameters") or {}

        current_doc = working_docs.get(document)

        if current_doc is None:
            results.append({
                "candidate_id": item.get("candidate_id"),
                "document": document,
                "action": action,
                "status": "REVIEW",
                "reason": "DOCUMENT_NOT_FOUND",
            })
            continue

        before = current_anomalies[document]

        simulated = copy.deepcopy(current_doc)

        applied, apply_reason = apply_action(
            simulated,
            action,
            params,
        )

        if not applied:
            results.append({
                "candidate_id": item.get("candidate_id"),
                "document": document,
                "action": action,
                "parameters": params,
                "status": (
                    "ALREADY_SATISFIED"
                    if apply_reason == "ALREADY_SATISFIED"
                    else "REVIEW"
                ),
                "reason": apply_reason,
            })
            continue

        after = audit_document(
            simulated,
            signatures,
        )

        new = after - before
        resolved = before - after

        if new:
            status = "REJECT_HARMFUL"
            reason = "CREATES_NEW_DOCUMENT_ANOMALIES"

        elif resolved:
            status = "SAFE_ACCEPT"
            reason = "MONOTONIC_IMPROVEMENT"

            # Commit safe action in working memory.
            working_docs[document] = simulated
            current_anomalies[document] = after

            safe_actions.append({
                "candidate_id": item.get("candidate_id"),
                "document": document,
                "action": action,
                "parameters": params,
                "before_anomaly_count": len(before),
                "after_anomaly_count": len(after),
                "new_anomaly_count": 0,
                "resolved_anomaly_count": len(resolved),
            })

        else:
            status = "NO_BENEFIT"
            reason = "NO_STRUCTURAL_IMPROVEMENT"

        results.append({
            "candidate_id": item.get("candidate_id"),
            "document": document,
            "action": action,
            "parameters": params,
            "status": status,
            "reason": reason,
            "before_anomaly_count": len(before),
            "after_anomaly_count": len(after),
            "new_anomaly_count": len(new),
            "resolved_anomaly_count": len(resolved),
        })

    final_anomaly_total = sum(
        len(v)
        for v in current_anomalies.values()
    )

    counts = Counter(
        x.get("status")
        for x in results
    )

    action_counts = Counter(
        x.get("action")
        for x in safe_actions
    )

    output = {
        "validator":
            "relation_repair_batch_impact_validator",

        "baseline_directory":
            str(BASELINE_DIR),

        "summary": {
            "accepted_actions_received":
                len(accepted),

            "unique_actions_evaluated":
                len(unique),

            "duplicates_merged":
                duplicates,

            "safe_accept":
                counts.get("SAFE_ACCEPT", 0),

            "reject_harmful":
                counts.get("REJECT_HARMFUL", 0),

            "no_benefit":
                counts.get("NO_BENEFIT", 0),

            "already_satisfied":
                counts.get("ALREADY_SATISFIED", 0),

            "review":
                counts.get("REVIEW", 0),

            "baseline_anomalies":
                baseline_anomaly_total,

            "projected_final_anomalies":
                final_anomaly_total,

            "projected_resolved_anomalies":
                baseline_anomaly_total - final_anomaly_total,

            "safe_actions_by_type":
                dict(action_counts),
        },

        "safe_actions":
            safe_actions,

        "results":
            results,
    }

    save_json(OUTPUT_FILE, output)

    print("=" * 108)
    print("TRACE / SGCE - RELATION REPAIR BATCH IMPACT VALIDATOR")
    print("=" * 108)

    print(f"ACCEPT précédents                  : {len(accepted)}")
    print(f"Actions uniques évaluées           : {len(unique)}")
    print(f"Doublons fusionnés                 : {duplicates}")
    print()

    print(f"SAFE_ACCEPT                        : {counts.get('SAFE_ACCEPT',0)}")
    print(f"REJECT_HARMFUL                     : {counts.get('REJECT_HARMFUL',0)}")
    print(f"NO_BENEFIT                         : {counts.get('NO_BENEFIT',0)}")
    print(f"ALREADY_SATISFIED                  : {counts.get('ALREADY_SATISFIED',0)}")
    print(f"REVIEW                             : {counts.get('REVIEW',0)}")

    print()
    print("ACTIONS SURES PAR TYPE")
    print("-" * 108)

    for name,count in action_counts.most_common():
        print(f"{str(name):<48}: {count}")

    print()
    print(f"Anomalies baseline                 : {baseline_anomaly_total}")
    print(f"Anomalies projetées après lot sûr  : {final_anomaly_total}")
    print(
        f"Anomalies projetées résolues       : "
        f"{baseline_anomaly_total-final_anomaly_total}"
    )

    print()
    print(f"Sortie                             : {OUTPUT_FILE}")
    print()
    print("Aucun JSON clinique n'a été modifié.")


if __name__ == "__main__":
    main()
