# -*- coding: utf-8 -*-
"""
multiagent_safe_retype_corrector.py
===================================

TRACE / SGCE â€” Safe RETYPE Corrector

Input:
  MultiAgent/outputs/multiagent_retype_impact_validation.json

Source baseline:
  MultiAgent/agent_d_corrected

Applies ONLY:
  SAFE_ACCEPT actions

Output:
  MultiAgent/multiagent_safe_final_corrected

The previous multiagent_final_corrected directory is NOT used as source.
"""

import json
import shutil
from pathlib import Path
from collections import Counter


BASE_DIR = Path(
    r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM"
    r"\Reduction_hallucinations"
)

M = BASE_DIR / "MultiAgent"

INPUT_FILE = (
    M
    / "outputs"
    / "multiagent_retype_impact_validation.json"
)

SOURCE_DIR = (
    M
    / "agent_d_corrected"
)

OUTPUT_DIR = (
    M
    / "multiagent_safe_final_corrected"
)

REPORT_FILE = (
    OUTPUT_DIR
    / "multiagent_safe_correction_report.json"
)


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


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


def entity_lists(doc):
    lists = []

    if isinstance(doc.get("global_entities"), list):
        lists.append(doc["global_entities"])

    for page in doc.get("pages", []) or []:
        if isinstance(page.get("entities"), list):
            lists.append(page["entities"])

    return lists


def find_entity(doc, target_id):
    for entity_list in entity_lists(doc):
        for entity in entity_list:
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

    for entity_list in entity_lists(doc):
        for entity in entity_list:
            if str(entity_id(entity)) != str(target_id):
                continue

            if entity_type(entity) != new_type:
                set_entity_type(
                    entity,
                    new_type,
                )

                changed += 1

    return changed


def is_clinical_json(data):
    return (
        isinstance(data, dict)
        and any(
            key in data
            for key in (
                "pages",
                "global_entities",
                "global_relations",
            )
        )
    )


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Rapport d'impact introuvable : {INPUT_FILE}"
        )

    if not SOURCE_DIR.exists():
        raise FileNotFoundError(
            f"Baseline introuvable : {SOURCE_DIR}"
        )

    payload = load_json(
        INPUT_FILE
    )

    safe_actions = (
        payload.get(
            "safe_actions",
            []
        )
        or []
    )

    if OUTPUT_DIR.exists():
        shutil.rmtree(
            OUTPUT_DIR
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    copied = 0

    for src in sorted(
        SOURCE_DIR.glob("*.json")
    ):
        if src.name.endswith(
            "_report.json"
        ):
            continue

        try:
            data = load_json(
                src
            )

            if not is_clinical_json(
                data
            ):
                continue

        except Exception:
            continue

        shutil.copy2(
            src,
            OUTPUT_DIR / src.name,
        )

        copied += 1

    operations = []

    modified_documents = set()

    counts = Counter()

    errors = 0

    for action in safe_actions:
        document = action.get(
            "document"
        )

        target_id = action.get(
            "entity_id"
        )

        old_type = action.get(
            "old_type"
        )

        new_type = action.get(
            "new_type"
        )

        candidate_ids = (
            action.get(
                "candidate_ids"
            )
            or []
        )

        path = (
            OUTPUT_DIR
            / str(document)
        )

        if not path.exists():
            errors += 1

            operations.append({
                "document": document,
                "entity_id": target_id,
                "new_type": new_type,
                "candidate_ids": candidate_ids,
                "status": "ERROR",
                "reason": "DOCUMENT_NOT_FOUND",
            })

            continue

        try:
            doc = load_json(
                path
            )

            entity = find_entity(
                doc,
                target_id,
            )

            if entity is None:
                operations.append({
                    "document": document,
                    "entity_id": target_id,
                    "new_type": new_type,
                    "candidate_ids": candidate_ids,
                    "status": "SKIP",
                    "reason": "ENTITY_NOT_FOUND",
                })

                counts[
                    "SKIP_ENTITY_NOT_FOUND"
                ] += 1

                continue

            current_type = entity_type(
                entity
            )

            if current_type == new_type:
                operations.append({
                    "document": document,
                    "entity_id": target_id,
                    "old_type": current_type,
                    "new_type": new_type,
                    "candidate_ids": candidate_ids,
                    "status": "SKIP",
                    "reason": "ALREADY_SATISFIED",
                })

                counts[
                    "SKIP_ALREADY_SATISFIED"
                ] += 1

                continue

            changes = retype_everywhere(
                doc,
                target_id,
                new_type,
            )

            if changes <= 0:
                operations.append({
                    "document": document,
                    "entity_id": target_id,
                    "old_type": current_type,
                    "new_type": new_type,
                    "candidate_ids": candidate_ids,
                    "status": "SKIP",
                    "reason": "NO_CHANGE",
                })

                counts[
                    "SKIP_NO_CHANGE"
                ] += 1

                continue

            save_json(
                path,
                doc,
            )

            modified_documents.add(
                document
            )

            counts[
                "RETYPE_ENTITY"
            ] += 1

            operations.append({
                "document": document,
                "entity_id": target_id,
                "old_type": current_type,
                "expected_old_type": old_type,
                "new_type": new_type,
                "candidate_ids": candidate_ids,
                "occurrences_changed": changes,
                "status": "APPLIED",
                "reason": "SAFE_ACCEPT",
            })

        except Exception as exc:
            errors += 1

            operations.append({
                "document": document,
                "entity_id": target_id,
                "new_type": new_type,
                "candidate_ids": candidate_ids,
                "status": "ERROR",
                "reason": repr(exc),
            })

    applied = counts.get(
        "RETYPE_ENTITY",
        0,
    )

    skipped = sum(
        value
        for key, value
        in counts.items()
        if key.startswith(
            "SKIP_"
        )
    )

    report = {
        "corrector":
            "multiagent_safe_retype_corrector",

        "source_directory":
            str(SOURCE_DIR),

        "output_directory":
            str(OUTPUT_DIR),

        "impact_validation_file":
            str(INPUT_FILE),

        "summary": {
            "documents_copied":
                copied,

            "safe_actions_received":
                len(safe_actions),

            "operations_applied":
                applied,

            "operations_skipped":
                skipped,

            "documents_modified":
                len(modified_documents),

            "errors":
                errors,
        },

        "modified_documents":
            sorted(
                modified_documents
            ),

        "operations":
            operations,
    }

    save_json(
        REPORT_FILE,
        report,
    )

    print("=" * 104)
    print("TRACE / SGCE - SAFE RETYPE CORRECTOR")
    print("=" * 104)

    print(
        f"Baseline clinique                    : {SOURCE_DIR}"
    )

    print(
        f"Actions SAFE_ACCEPT reÃ§ues           : {len(safe_actions)}"
    )

    print(
        f"Documents copiÃ©s                     : {copied}"
    )

    print(
        f"OpÃ©rations appliquÃ©es                : {applied}"
    )

    print(
        f"OpÃ©rations SKIP                      : {skipped}"
    )

    print(
        f"Documents modifiÃ©s                   : {len(modified_documents)}"
    )

    print(
        f"Erreurs                              : {errors}"
    )

    print()

    print(
        f"Sortie clinique                      : {OUTPUT_DIR}"
    )

    print(
        f"Rapport                              : {REPORT_FILE}"
    )

    print()

    print(
        "Les fichiers sources n'ont pas Ã©tÃ© modifiÃ©s."
    )


if __name__ == "__main__":
    main()

