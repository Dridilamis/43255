# -*- coding: utf-8 -*-
"""
multiagent_retype_impact_validator.py
=====================================

TRACE / SGCE â€” Per-action impact validation for adjudicated RETYPE_ENTITY

Purpose
-------
The previous final correction applied RETYPE actions that were individually
plausible but could make OTHER relations of the same entity invalid.

This validator starts from the clean baseline:
    MultiAgent/agent_d_corrected

It DOES NOT trust multiagent_final_corrected.

For each APPLIED RETYPE proposed by:
    MultiAgent/multiagent_final_corrected/multiagent_correction_report.json

it simulates the RETYPE independently and audits ALL relations touching that
entity.

Decision:
- SAFE_ACCEPT:
    no new local anomaly AND at least one anomaly resolved
- NO_BENEFIT:
    no new anomaly, but no anomaly resolved
- REJECT_HARMFUL:
    one or more new local anomalies
- REVIEW:
    incomplete/unverifiable case

It also deduplicates repeated same (document, entity_id, new_type) proposals.

No clinical JSON is modified.
"""

import copy
import json
from pathlib import Path
from collections import Counter, defaultdict


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(
    r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM"
    r"\Reduction_hallucinations"
)

M = BASE_DIR / "MultiAgent"

BASELINE_DIR = (
    M
    / "agent_d_corrected"
)

CORRECTION_REPORT = (
    M
    / "multiagent_final_corrected"
    / "multiagent_correction_report.json"
)

GUIDELINE_CANDIDATES = [
    BASE_DIR
    / "Guideline_TRACE_Sepsis_v1.6.json",

    BASE_DIR.parent
    / "Guideline_TRACE_Sepsis_v1.6.json",
]

OUTPUT_FILE = (
    M
    / "outputs"
    / "multiagent_retype_impact_validation.json"
)


# ============================================================
# IO
# ============================================================

def load_json(path):
    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


def save_json(path, data):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def resolve_guideline():
    for path in GUIDELINE_CANDIDATES:
        if path.exists():
            return path

    raise FileNotFoundError(
        "Guideline TRACE-Sepsis introuvable."
    )


# ============================================================
# ENTITY / RELATION HELPERS
# ============================================================

def entity_id(entity):
    return (
        entity.get(
            "identifiant_entite"
        )
        or entity.get(
            "id"
        )
        or entity.get(
            "entity_id"
        )
    )


def entity_type(entity):
    return (
        entity.get(
            "categorie"
        )
        or entity.get(
            "type"
        )
        or entity.get(
            "entity_type"
        )
        or ""
    )


def relation_id(relation):
    return (
        relation.get(
            "identifiant_relation"
        )
        or relation.get(
            "id"
        )
        or relation.get(
            "relation_id"
        )
    )


def relation_type(relation):
    return (
        relation.get(
            "type_relation"
        )
        or relation.get(
            "relation"
        )
        or relation.get(
            "relation_type"
        )
        or relation.get(
            "predicate"
        )
        or relation.get(
            "type"
        )
        or ""
    )


def relation_source(relation):
    return (
        relation.get(
            "identifiant_entite_sujet"
        )
        or relation.get(
            "from_id"
        )
        or relation.get(
            "subject_id"
        )
        or relation.get(
            "source"
        )
    )


def relation_target(relation):
    return (
        relation.get(
            "identifiant_entite_objet"
        )
        or relation.get(
            "to_id"
        )
        or relation.get(
            "object_id"
        )
        or relation.get(
            "target"
        )
    )


def get_entities(doc):
    if isinstance(
        doc.get(
            "global_entities"
        ),
        list,
    ):
        return doc[
            "global_entities"
        ]

    out = []

    for page in (
        doc.get(
            "pages",
            []
        )
        or []
    ):
        out.extend(
            page.get(
                "entities",
                []
            )
            or []
        )

    return out


def get_relations(doc):
    if isinstance(
        doc.get(
            "global_relations"
        ),
        list,
    ):
        return doc[
            "global_relations"
        ]

    out = []

    for page in (
        doc.get(
            "pages",
            []
        )
        or []
    ):
        out.extend(
            page.get(
                "relations",
                []
            )
            or []
        )

    return out


def find_entity(
    doc,
    target_id,
):
    return next(
        (
            entity
            for entity in get_entities(
                doc
            )
            if str(
                entity_id(
                    entity
                )
            )
            == str(
                target_id
            )
        ),
        None,
    )


def entity_lists(doc):
    lists = []

    if isinstance(
        doc.get(
            "global_entities"
        ),
        list,
    ):
        lists.append(
            doc[
                "global_entities"
            ]
        )

    for page in (
        doc.get(
            "pages",
            []
        )
        or []
    ):
        if isinstance(
            page.get(
                "entities"
            ),
            list,
        ):
            lists.append(
                page[
                    "entities"
                ]
            )

    return lists


def retype_everywhere(
    doc,
    target_id,
    new_type,
):
    changed = 0

    for entity_list in entity_lists(
        doc
    ):
        for entity in entity_list:
            if str(
                entity_id(
                    entity
                )
            ) != str(
                target_id
            ):
                continue

            if "categorie" in entity:
                field = "categorie"

            elif "entity_type" in entity:
                field = "entity_type"

            else:
                field = "type"

            if entity.get(
                field
            ) != new_type:
                entity[
                    field
                ] = new_type

                changed += 1

    return changed


# ============================================================
# GUIDELINE SIGNATURES
# ============================================================

def load_signatures():
    guideline = load_json(
        resolve_guideline()
    )

    root = guideline.get(
        "ontologie_sepsis_graph",
        guideline,
    )

    locked = root.get(
        "signatures_relations_verrouillees_v1_5",
        {},
    )

    result = {}

    for rtype, spec in (
        locked.items()
        if isinstance(
            locked,
            dict,
        )
        else []
    ):
        if not isinstance(
            spec,
            dict,
        ):
            continue

        domain = spec.get(
            "domaine"
        )

        image = spec.get(
            "image"
        )

        if domain and image:
            result[
                rtype
            ] = {
                "domaine":
                    domain,

                "image":
                    image,
            }

    return result


# ============================================================
# LOCAL AUDIT
# ============================================================

def local_relations(
    doc,
    target_id,
):
    return [
        relation
        for relation in get_relations(
            doc
        )
        if (
            str(
                relation_source(
                    relation
                )
            )
            == str(
                target_id
            )
            or
            str(
                relation_target(
                    relation
                )
            )
            == str(
                target_id
            )
        )
    ]


def local_anomalies(
    doc,
    target_id,
    signatures,
):
    """
    Audits every relation touching target_id.

    This is the critical protection missing from the previous final validator.
    """

    entity_map = {
        str(
            entity_id(
                entity
            )
        ):
            entity
        for entity in get_entities(
            doc
        )
        if entity_id(
            entity
        )
        is not None
    }

    anomalies = []

    for relation in local_relations(
        doc,
        target_id,
    ):
        rid = relation_id(
            relation
        )

        rtype = relation_type(
            relation
        )

        source_id = relation_source(
            relation
        )

        target_rel_id = relation_target(
            relation
        )

        source = entity_map.get(
            str(
                source_id
            )
        )

        target = entity_map.get(
            str(
                target_rel_id
            )
        )

        if source is None:
            anomalies.append({
                "type":
                    "ORPHAN_SOURCE",

                "relation_id":
                    rid,

                "relation_type":
                    rtype,

                "endpoint":
                    source_id,
            })

        if target is None:
            anomalies.append({
                "type":
                    "ORPHAN_TARGET",

                "relation_id":
                    rid,

                "relation_type":
                    rtype,

                "endpoint":
                    target_rel_id,
            })

        signature = signatures.get(
            rtype
        )

        if not signature:
            continue

        if (
            source is not None
            and entity_type(
                source
            )
            != signature[
                "domaine"
            ]
        ):
            anomalies.append({
                "type":
                    "INVALID_SOURCE_TYPE",

                "relation_id":
                    rid,

                "relation_type":
                    rtype,

                "entity_id":
                    source_id,

                "actual_type":
                    entity_type(
                        source
                    ),

                "expected_type":
                    signature[
                        "domaine"
                    ],
            })

        if (
            target is not None
            and entity_type(
                target
            )
            != signature[
                "image"
            ]
        ):
            anomalies.append({
                "type":
                    "INVALID_TARGET_TYPE",

                "relation_id":
                    rid,

                "relation_type":
                    rtype,

                "entity_id":
                    target_rel_id,

                "actual_type":
                    entity_type(
                        target
                    ),

                "expected_type":
                    signature[
                        "image"
                    ],
            })

    return anomalies


def anomaly_key(
    anomaly,
):
    return (
        anomaly.get(
            "type"
        ),
        str(
            anomaly.get(
                "relation_id"
            )
        ),
        str(
            anomaly.get(
                "relation_type"
            )
        ),
        str(
            anomaly.get(
                "entity_id"
            )
        ),
        str(
            anomaly.get(
                "endpoint"
            )
        ),
        str(
            anomaly.get(
                "actual_type"
            )
        ),
        str(
            anomaly.get(
                "expected_type"
            )
        ),
    )


# ============================================================
# MAIN
# ============================================================

def main():
    if not BASELINE_DIR.exists():
        raise FileNotFoundError(
            f"Baseline introuvable : {BASELINE_DIR}"
        )

    if not CORRECTION_REPORT.exists():
        raise FileNotFoundError(
            f"Rapport de correction introuvable : "
            f"{CORRECTION_REPORT}"
        )

    signatures = load_signatures()

    correction_report = load_json(
        CORRECTION_REPORT
    )

    applied = [
        op
        for op in correction_report.get(
            "operations",
            []
        )
        if (
            op.get(
                "status"
            )
            == "APPLIED"
            and op.get(
                "action"
            )
            == "RETYPE_ENTITY"
        )
    ]

    # --------------------------------------------------------
    # Deduplicate identical actions first
    # --------------------------------------------------------

    grouped = defaultdict(
        list
    )

    for op in applied:
        key = (
            op.get(
                "document"
            ),
            op.get(
                "entity_id"
            ),
            op.get(
                "new_type"
            ),
        )

        grouped[
            key
        ].append(
            op
        )

    unique_actions = []

    duplicates_merged = 0

    for (
        document,
        target_id,
        new_type,
    ), items in grouped.items():

        duplicates_merged += (
            len(
                items
            )
            - 1
        )

        unique_actions.append({
            "document":
                document,

            "entity_id":
                target_id,

            "new_type":
                new_type,

            "candidate_ids": [
                x.get(
                    "candidate_id"
                )
                for x in items
            ],
        })

    results = []

    doc_cache = {}

    for action in unique_actions:
        document = action[
            "document"
        ]

        target_id = action[
            "entity_id"
        ]

        new_type = action[
            "new_type"
        ]

        path = (
            BASELINE_DIR
            / str(
                document
            )
        )

        if not path.exists():
            results.append({
                **action,

                "status":
                    "REVIEW",

                "reason":
                    "DOCUMENT_NOT_FOUND",

                "before_anomaly_count":
                    None,

                "after_anomaly_count":
                    None,

                "new_anomaly_count":
                    None,

                "resolved_anomaly_count":
                    None,
            })

            continue

        if document not in doc_cache:
            doc_cache[
                document
            ] = load_json(
                path
            )

        baseline = doc_cache[
            document
        ]

        entity = find_entity(
            baseline,
            target_id,
        )

        if entity is None:
            results.append({
                **action,

                "status":
                    "REVIEW",

                "reason":
                    "ENTITY_NOT_FOUND",

                "before_anomaly_count":
                    None,

                "after_anomaly_count":
                    None,

                "new_anomaly_count":
                    None,

                "resolved_anomaly_count":
                    None,
            })

            continue

        old_type = entity_type(
            entity
        )

        if old_type == new_type:
            results.append({
                **action,

                "old_type":
                    old_type,

                "status":
                    "ALREADY_SATISFIED",

                "reason":
                    "TYPE_ALREADY_CORRECT",

                "before_anomaly_count":
                    0,

                "after_anomaly_count":
                    0,

                "new_anomaly_count":
                    0,

                "resolved_anomaly_count":
                    0,
            })

            continue

        before_anomalies = local_anomalies(
            baseline,
            target_id,
            signatures,
        )

        simulated = copy.deepcopy(
            baseline
        )

        changed = retype_everywhere(
            simulated,
            target_id,
            new_type,
        )

        if changed <= 0:
            results.append({
                **action,

                "old_type":
                    old_type,

                "status":
                    "REVIEW",

                "reason":
                    "SIMULATION_NO_CHANGE",

                "before_anomaly_count":
                    len(
                        before_anomalies
                    ),

                "after_anomaly_count":
                    None,

                "new_anomaly_count":
                    None,

                "resolved_anomaly_count":
                    None,
            })

            continue

        after_anomalies = local_anomalies(
            simulated,
            target_id,
            signatures,
        )

        before_map = {
            anomaly_key(
                anomaly
            ):
                anomaly
            for anomaly in before_anomalies
        }

        after_map = {
            anomaly_key(
                anomaly
            ):
                anomaly
            for anomaly in after_anomalies
        }

        new_keys = (
            set(
                after_map
            )
            - set(
                before_map
            )
        )

        resolved_keys = (
            set(
                before_map
            )
            - set(
                after_map
            )
        )

        new_anomalies = [
            after_map[
                key
            ]
            for key in sorted(
                new_keys
            )
        ]

        resolved_anomalies = [
            before_map[
                key
            ]
            for key in sorted(
                resolved_keys
            )
        ]

        if len(
            new_anomalies
        ) > 0:
            status = (
                "REJECT_HARMFUL"
            )

            reason = (
                "RETYPE_CREATES_NEW_LOCAL_ANOMALIES"
            )

        elif len(
            resolved_anomalies
        ) > 0:
            status = (
                "SAFE_ACCEPT"
            )

            reason = (
                "RETYPE_RESOLVES_ANOMALY_WITHOUT_NEW_ANOMALY"
            )

        else:
            status = (
                "NO_BENEFIT"
            )

            reason = (
                "RETYPE_DOES_NOT_IMPROVE_LOCAL_STRUCTURE"
            )

        results.append({
            **action,

            "old_type":
                old_type,

            "status":
                status,

            "reason":
                reason,

            "before_anomaly_count":
                len(
                    before_anomalies
                ),

            "after_anomaly_count":
                len(
                    after_anomalies
                ),

            "new_anomaly_count":
                len(
                    new_anomalies
                ),

            "resolved_anomaly_count":
                len(
                    resolved_anomalies
                ),

            "new_anomalies":
                new_anomalies,

            "resolved_anomalies":
                resolved_anomalies,
        })

    status_counts = Counter(
        item[
            "status"
        ]
        for item in results
    )

    safe_actions = [
        {
            "document":
                item[
                    "document"
                ],

            "entity_id":
                item[
                    "entity_id"
                ],

            "old_type":
                item.get(
                    "old_type"
                ),

            "new_type":
                item[
                    "new_type"
                ],

            "candidate_ids":
                item[
                    "candidate_ids"
                ],
        }
        for item in results
        if item[
            "status"
        ]
        == "SAFE_ACCEPT"
    ]

    output = {
        "validator":
            "multiagent_retype_impact_validator",

        "baseline_directory":
            str(
                BASELINE_DIR
            ),

        "source_correction_report":
            str(
                CORRECTION_REPORT
            ),

        "summary": {
            "applied_retypes_in_previous_run":
                len(
                    applied
                ),

            "unique_retypes_evaluated":
                len(
                    unique_actions
                ),

            "duplicates_merged":
                duplicates_merged,

            "safe_accept":
                status_counts.get(
                    "SAFE_ACCEPT",
                    0,
                ),

            "reject_harmful":
                status_counts.get(
                    "REJECT_HARMFUL",
                    0,
                ),

            "no_benefit":
                status_counts.get(
                    "NO_BENEFIT",
                    0,
                ),

            "already_satisfied":
                status_counts.get(
                    "ALREADY_SATISFIED",
                    0,
                ),

            "review":
                status_counts.get(
                    "REVIEW",
                    0,
                ),

            "status_counts":
                dict(
                    status_counts
                ),
        },

        "safe_actions":
            safe_actions,

        "results":
            results,
    }

    save_json(
        OUTPUT_FILE,
        output,
    )

    print("=" * 108)
    print("TRACE / SGCE - RETYPE IMPACT VALIDATOR")
    print("=" * 108)

    print(
        f"RETYPE appliquÃ©s run prÃ©cÃ©dent       : "
        f"{len(applied)}"
    )

    print(
        f"RETYPE uniques Ã©valuÃ©s               : "
        f"{len(unique_actions)}"
    )

    print(
        f"Doublons fusionnÃ©s                   : "
        f"{duplicates_merged}"
    )

    print()

    print(
        f"SAFE_ACCEPT                          : "
        f"{status_counts.get('SAFE_ACCEPT', 0)}"
    )

    print(
        f"REJECT_HARMFUL                       : "
        f"{status_counts.get('REJECT_HARMFUL', 0)}"
    )

    print(
        f"NO_BENEFIT                           : "
        f"{status_counts.get('NO_BENEFIT', 0)}"
    )

    print(
        f"ALREADY_SATISFIED                    : "
        f"{status_counts.get('ALREADY_SATISFIED', 0)}"
    )

    print(
        f"REVIEW                               : "
        f"{status_counts.get('REVIEW', 0)}"
    )

    print()

    print(
        f"Actions sÃ»res Ã  rÃ©appliquer          : "
        f"{len(safe_actions)}"
    )

    print(
        f"Sortie                               : "
        f"{OUTPUT_FILE}"
    )

    print()

    print(
        "Aucune donnÃ©e clinique n'a Ã©tÃ© modifiÃ©e."
    )


if __name__ == "__main__":
    main()

