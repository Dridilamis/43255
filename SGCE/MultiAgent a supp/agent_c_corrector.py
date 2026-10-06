# -*- coding: utf-8 -*-
"""
agent_c_corrector.py
TRACE / SGCE â€” Generic Agent C Corrector

Input:
  MultiAgent/outputs/agent_c_validated_decisions.json
  MultiAgent/agent_b_corrected

Output:
  MultiAgent/agent_c_corrected

Only ACCEPT decisions are applied.
Supported actions:
  REMOVE_REIFIED_ENTITY
  MERGE (only if explicitly validated)

Source files are never modified.
"""

import copy
import json
import shutil
from collections import Counter
from pathlib import Path


BASE_DIR = Path(
    r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM"
    r"\Reduction_hallucinations"
)
MULTIAGENT_DIR = BASE_DIR / "MultiAgent"

DECISIONS_FILE = MULTIAGENT_DIR / "outputs" / "agent_c_validated_decisions.json"

INPUT_DIR_CANDIDATES = [
    MULTIAGENT_DIR / "agent_b_corrected",
    BASE_DIR / "PatternD" / "pattern_d_corrected",
]

OUTPUT_DIR = MULTIAGENT_DIR / "agent_c_corrected"
REPORT_FILE = OUTPUT_DIR / "agent_c_correction_report.json"


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def resolve_input_dir():
    for directory in INPUT_DIR_CANDIDATES:
        if directory.exists() and any(directory.glob("*.json")):
            return directory
    raise FileNotFoundError("Aucun dossier clinique d'entrÃ©e valide.")


def entity_id(entity):
    return (
        entity.get("identifiant_entite")
        or entity.get("id")
        or entity.get("entity_id")
    )


def relation_source(rel):
    return (
        rel.get("identifiant_entite_sujet")
        or rel.get("from_id")
        or rel.get("subject_id")
        or rel.get("source")
    )


def relation_target(rel):
    return (
        rel.get("identifiant_entite_objet")
        or rel.get("to_id")
        or rel.get("object_id")
        or rel.get("target")
    )


def iter_entity_lists(doc):
    if isinstance(doc.get("global_entities"), list):
        yield "global_entities", doc["global_entities"]

    for i, page in enumerate(doc.get("pages", []) or []):
        if isinstance(page.get("entities"), list):
            yield f"pages[{i}].entities", page["entities"]


def iter_relation_lists(doc):
    if isinstance(doc.get("global_relations"), list):
        yield "global_relations", doc["global_relations"]

    for i, page in enumerate(doc.get("pages", []) or []):
        if isinstance(page.get("relations"), list):
            yield f"pages[{i}].relations", page["relations"]


def find_entity(doc, eid):
    for _, entities in iter_entity_lists(doc):
        for entity in entities:
            if str(entity_id(entity)) == str(eid):
                return entity
    return None


def relations_for_entity(doc, eid):
    out = []
    for location, relations in iter_relation_lists(doc):
        for rel in relations:
            if (
                str(relation_source(rel)) == str(eid)
                or str(relation_target(rel)) == str(eid)
            ):
                out.append((location, rel))
    return out


def remove_entity_everywhere(doc, eid):
    removed = 0

    for _, entities in iter_entity_lists(doc):
        before = len(entities)
        entities[:] = [
            e for e in entities
            if str(entity_id(e)) != str(eid)
        ]
        removed += before - len(entities)

    return removed


def replace_endpoint(rel, old_id, new_id):
    source_keys = (
        "identifiant_entite_sujet",
        "from_id",
        "subject_id",
        "source",
    )
    target_keys = (
        "identifiant_entite_objet",
        "to_id",
        "object_id",
        "target",
    )

    changed = 0

    for key in source_keys:
        if key in rel and str(rel.get(key)) == str(old_id):
            rel[key] = new_id
            changed += 1

    for key in target_keys:
        if key in rel and str(rel.get(key)) == str(old_id):
            rel[key] = new_id
            changed += 1

    return changed


def merge_entity(doc, source_id, target_id):
    source = find_entity(doc, source_id)
    target = find_entity(doc, target_id)

    if source is None or target is None:
        return False, "MERGE_ENTITY_NOT_FOUND", 0

    if str(source_id) == str(target_id):
        return False, "MERGE_SOURCE_EQUALS_TARGET", 0

    rewired = 0

    for _, relations in iter_relation_lists(doc):
        for rel in relations:
            rewired += replace_endpoint(
                rel,
                source_id,
                target_id,
            )

    removed = remove_entity_everywhere(
        doc,
        source_id,
    )

    if removed == 0:
        return False, "MERGE_SOURCE_NOT_REMOVED", rewired

    return True, "APPLIED", rewired


def extract_validated_decisions(payload):
    if isinstance(payload, dict):
        values = payload.get("validated_decisions", [])
        return values if isinstance(values, list) else []
    return []


def main():
    if not DECISIONS_FILE.exists():
        raise FileNotFoundError(
            f"DÃ©cisions validÃ©es introuvables : {DECISIONS_FILE}"
        )

    input_dir = resolve_input_dir()
    payload = load_json(DECISIONS_FILE)
    decisions = extract_validated_decisions(payload)

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Copy only clinical JSONs; reports are generated separately.
    copied = 0
    for src in sorted(input_dir.glob("*.json")):
        try:
            data = load_json(src)
        except Exception:
            continue

        if not isinstance(data, dict):
            continue

        shutil.copy2(src, OUTPUT_DIR / src.name)
        copied += 1

    operations = []
    modified_docs = set()
    applied_counter = Counter()
    skip_counter = Counter()
    errors = 0

    for item in decisions:
        candidate_id = item.get("candidate_id")
        document = item.get("document")
        final_status = item.get("final_status")
        action = item.get("final_action")

        if final_status != "ACCEPT":
            skip_counter["NOT_ACCEPTED"] += 1
            continue

        if action in (None, "", "NONE"):
            skip_counter["NO_ACTION"] += 1
            continue

        doc_path = OUTPUT_DIR / str(document)

        if not doc_path.exists():
            errors += 1
            operations.append({
                "candidate_id": candidate_id,
                "document": document,
                "action": action,
                "status": "ERROR",
                "reason": "DOCUMENT_NOT_FOUND",
            })
            continue

        try:
            doc = load_json(doc_path)
            before = copy.deepcopy(doc)

            agent_decision = item.get("agent_decision") or {}
            metadata = agent_decision.get("metadata") or {}

            if action == "REMOVE_REIFIED_ENTITY":
                eid = metadata.get("candidate_entity_id")

                if not eid:
                    status = "SKIP"
                    reason = "ENTITY_ID_MISSING"

                elif find_entity(doc, eid) is None:
                    status = "SKIP"
                    reason = "ENTITY_NOT_FOUND"

                elif relations_for_entity(doc, eid):
                    status = "SKIP"
                    reason = "ENTITY_HAS_ACTIVE_RELATIONS"

                else:
                    removed = remove_entity_everywhere(doc, eid)

                    if removed > 0:
                        status = "APPLIED"
                        reason = "OK"
                    else:
                        status = "SKIP"
                        reason = "ENTITY_NOT_REMOVED"

                op_details = {
                    "entity_id": eid,
                }

            elif action == "MERGE":
                source_id = (
                    metadata.get("merge_source_id")
                    or metadata.get("source_entity_id")
                )
                target_id = (
                    metadata.get("merge_target_id")
                    or metadata.get("target_entity_id")
                )

                if not source_id or not target_id:
                    status = "SKIP"
                    reason = "MERGE_ENDPOINTS_MISSING"
                    rewired = 0
                else:
                    ok, reason, rewired = merge_entity(
                        doc,
                        source_id,
                        target_id,
                    )
                    status = "APPLIED" if ok else "SKIP"

                op_details = {
                    "source_entity_id": source_id,
                    "target_entity_id": target_id,
                    "rewired_endpoints": rewired,
                }

            else:
                status = "SKIP"
                reason = "UNSUPPORTED_ACTION"
                op_details = {}

            if status == "APPLIED":
                if doc != before:
                    save_json(doc_path, doc)
                    modified_docs.add(document)
                    applied_counter[action] += 1
                else:
                    status = "SKIP"
                    reason = "NO_EFFECT"
                    skip_counter[reason] += 1
            else:
                skip_counter[reason] += 1

            operations.append({
                "candidate_id": candidate_id,
                "document": document,
                "action": action,
                "status": status,
                "reason": reason,
                **op_details,
            })

        except Exception as exc:
            errors += 1
            operations.append({
                "candidate_id": candidate_id,
                "document": document,
                "action": action,
                "status": "ERROR",
                "reason": str(exc),
            })

    applied = sum(applied_counter.values())
    skipped = sum(skip_counter.values())

    report = {
        "corrector": "agent_c_corrector",
        "source_directory": str(input_dir),
        "output_directory": str(OUTPUT_DIR),
        "decisions_file": str(DECISIONS_FILE),
        "summary": {
            "documents_copied": copied,
            "operations_received": sum(
                1 for x in decisions
                if x.get("final_status") == "ACCEPT"
                and x.get("final_action") not in (None, "", "NONE")
            ),
            "operations_applied": applied,
            "operations_skipped": skipped,
            "documents_modified": len(modified_docs),
            "errors": errors,
            "actions_applied": dict(applied_counter),
            "skip_reasons": dict(skip_counter),
        },
        "modified_documents": sorted(modified_docs),
        "operations": operations,
    }

    save_json(REPORT_FILE, report)

    print("=" * 100)
    print("TRACE / SGCE - GENERIC AGENT C CORRECTOR")
    print("=" * 100)
    print(f"EntrÃ©e dÃ©cisions                    : {DECISIONS_FILE}")
    print(f"Source clinique                     : {input_dir}")
    print(f"Sortie clinique                     : {OUTPUT_DIR}")
    print()
    print(f"Documents cliniques copiÃ©s          : {copied}")
    print(f"OpÃ©rations reÃ§ues                   : {report['summary']['operations_received']}")
    print(f"OpÃ©rations appliquÃ©es               : {applied}")
    print(f"OpÃ©rations SKIP                     : {skipped}")
    print(f"Documents modifiÃ©s                  : {len(modified_docs)}")
    print(f"Erreurs                             : {errors}")

    if applied_counter:
        print()
        print("ACTIONS APPLIQUEES")
        print("-" * 100)
        for name, count in applied_counter.most_common():
            print(f"{name:<44}: {count}")

    if skip_counter:
        print()
        print("RAISONS SKIP")
        print("-" * 100)
        for name, count in skip_counter.most_common():
            print(f"{name:<44}: {count}")

    print()
    print(f"Rapport                              : {REPORT_FILE}")
    print()
    print("Les fichiers sources n'ont pas Ã©tÃ© modifiÃ©s.")


if __name__ == "__main__":
    main()

