# -*- coding: utf-8 -*-
"""
temporal_status_post_validator.py
=================================

VÃ©rifie la rÃ©paration text-guided :
- seules les mÃ©tadonnÃ©es trace_context_status peuvent changer ;
- aucun document ajoutÃ©/supprimÃ© ;
- aucune entitÃ©/relation clinique changÃ©e ;
- les temporalitÃ©s SAFE_ACCEPT sont rÃ©ellement appliquÃ©es.
"""

import copy
import json
from pathlib import Path

BASE_DIR = Path(
    r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM"
    r"\Reduction_hallucinations"
)

BEFORE_DIR = (
    BASE_DIR / "numeric_unit Etage 5"
    / "numeric_unit_safe_corrected"
)

AFTER_DIR = (
    BASE_DIR / "temporal Etage 6"
    / "temporal_status_safe_corrected"
)

CORRECTION_REPORT = (
    AFTER_DIR
    / "temporal_status_correction_report.json"
)

OUTPUT_FILE = (
    BASE_DIR / "temporal Etage 6"
    / "post_validation"
    / "temporal_status_post_validation_report.json"
)

OUTPUT_FILE.parent.mkdir(
    parents=True,
    exist_ok=True,
)


def load_json(path):
    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


def is_clinical(path):
    if path.name.endswith(
        "_report.json"
    ):
        return False

    try:
        doc = load_json(path)
    except Exception:
        return False

    return (
        isinstance(doc, dict)
        and any(
            k in doc
            for k in (
                "pages",
                "global_entities",
                "global_relations",
            )
        )
    )


def strip_context_status(obj):
    obj = copy.deepcopy(
        obj
    )

    def walk(value):
        if isinstance(
            value,
            dict,
        ):
            for key in (
                "trace_context_status",
                "trace_temporal_status",
                "trace_temporal_status_audit",
                "temporal_status_annotation",
            ):
                value.pop(key, None)

            for v in value.values():
                walk(v)

        elif isinstance(
            value,
            list,
        ):
            for v in value:
                walk(v)

    walk(obj)

    return obj


def entity_id(e):
    return (
        e.get("identifiant_entite")
        or e.get("id")
        or e.get("entity_id")
    )


def all_temporal_values(
    doc,
    target_id,
):
    values = []

    target_id = str(
        target_id
    )

    collections = []

    if isinstance(
        doc.get("global_entities"),
        list,
    ):
        collections.append(
            doc["global_entities"]
        )

    for page in doc.get(
        "pages",
        [],
    ) or []:
        collections.append(
            page.get(
                "entities",
                [],
            )
            or []
        )

    for collection in collections:
        for e in collection:
            if str(
                entity_id(e)
            ) != target_id:
                continue

            ann = None
            for key in (
                "trace_context_status",
                "trace_temporal_status",
                "trace_temporal_status_audit",
                "temporal_status_annotation",
            ):
                if isinstance(e.get(key), dict):
                    ann = e[key]
                    break

            if isinstance(ann, dict):
                values.append(
                    ann.get("temporal_status")
                    or ann.get("temporality")
                    or ann.get("statut_temporel")
                )

    return values


def main():
    correction = load_json(
        CORRECTION_REPORT
    )

    before_files = {
        p.name:
            p
        for p in BEFORE_DIR.glob(
            "*.json"
        )
        if is_clinical(p)
    }

    after_files = {
        p.name:
            p
        for p in AFTER_DIR.glob(
            "*.json"
        )
        if is_clinical(p)
    }

    missing = sorted(
        set(before_files)
        - set(after_files)
    )

    extra = sorted(
        set(after_files)
        - set(before_files)
    )

    unexpected_clinical_changes = []

    for name in sorted(
        set(before_files)
        & set(after_files)
    ):
        before = load_json(
            before_files[
                name
            ]
        )

        after = load_json(
            after_files[
                name
            ]
        )

        if (
            json.dumps(
                strip_context_status(
                    before
                ),
                ensure_ascii=False,
                sort_keys=True,
            )
            != json.dumps(
                strip_context_status(
                    after
                ),
                ensure_ascii=False,
                sort_keys=True,
            )
        ):
            unexpected_clinical_changes.append(
                name
            )

    expected_ops = [
        x
        for x in correction.get(
            "operations",
            [],
        )
        if x.get(
            "status"
        )
        == "APPLIED"
    ]

    failed_ops = []

    for op in expected_ops:
        path = after_files.get(
            op.get(
                "document"
            )
        )

        if path is None:
            failed_ops.append({
                **op,
                "failure":
                    "DOCUMENT_NOT_FOUND",
            })

            continue

        values = all_temporal_values(
            load_json(path),
            op.get(
                "entity_id"
            ),
        )

        expected = op.get(
            "new_temporal_status"
        )

        if (
            not values
            or any(
                v != expected
                for v in values
                if v is not None
            )
        ):
            failed_ops.append({
                **op,
                "failure":
                    "TEMPORAL_STATUS_NOT_APPLIED_CONSISTENTLY",
            })

    passed = (
        not missing
        and not extra
        and not unexpected_clinical_changes
        and not failed_ops
        and correction.get(
            "summary",
            {},
        ).get(
            "errors",
            0,
        ) == 0
    )

    output = {
        "post_validator":
            "temporal_status_post_validator",

        "mode":
            "AUTONOMOUS_TEXT_GUIDED",

        "summary": {
            "documents_checked":
                len(
                    before_files
                ),

            "expected_operations":
                len(
                    expected_ops
                ),

            "failed_operations":
                len(
                    failed_ops
                ),

            "unexpected_clinical_changes":
                len(
                    unexpected_clinical_changes
                ),

            "missing_documents_after":
                len(
                    missing
                ),

            "extra_documents_after":
                len(
                    extra
                ),

            "status":
                (
                    "PASS"
                    if passed
                    else "FAIL"
                ),
        },

        "failed_operations":
            failed_ops,

        "unexpected_clinical_changes":
            unexpected_clinical_changes,
    }

    OUTPUT_FILE.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=" * 112)
    print("TRACE / SGCE - TEMPORAL STATUS POST-VALIDATION - AUTONOMOUS TEXT-GUIDED")
    print("=" * 112)
    print(
        f"Documents vÃ©rifiÃ©s                  : {len(before_files)}"
    )
    print(
        f"OpÃ©rations attendues                : {len(expected_ops)}"
    )
    print(
        f"OpÃ©rations FAIL                     : {len(failed_ops)}"
    )
    print(
        f"Changements cliniques inattendus    : "
        f"{len(unexpected_clinical_changes)}"
    )
    print()
    print(
        f"Docs manquants APRES                : {len(missing)}"
    )
    print(
        f"Docs supplÃ©mentaires APRES          : {len(extra)}"
    )
    print()
    print(
        f"STATUT FINAL TEMPORAL REPAIR        : "
        f"{'PASS' if passed else 'FAIL'}"
    )
    print()
    print(
        f"Rapport                             : {OUTPUT_FILE}"
    )
    print()
    print(
        "Aucune donnÃ©e clinique n'a Ã©tÃ© modifiÃ©e "
        "par ce post-validateur."
    )


if __name__ == "__main__":
    main()

