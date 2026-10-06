# -*- coding: utf-8 -*-
"""
agent_b_corrector.py
====================

TRACE / SGCE â€” Correcteur gÃ©nÃ©rique Pattern B

Objectif
--------
Appliquer uniquement les corrections Pattern B explicitement validÃ©es
et dÃ©dupliquÃ©es.

Actions supportÃ©es :
- CREATE_FROM_EXPLICIT_EVIDENCE
- CREATE_AND_LINK
- RELINK
- RELINK_EXISTING_ENTITY
- REMOVE_RELATION

Actions protÃ©gÃ©es / non appliquÃ©es :
- NONE
- REVIEW
- REFINE_ENTITY_SPAN
- KEEP
- CONFLICT
- toute action inconnue

Le script est gÃ©nÃ©rique :
- ne dÃ©pend pas des 2 corrections actuelles ;
- fonctionne sur d'autres corpus TRACE compatibles ;
- dÃ©tecte automatiquement la structure entitÃ©s/relations ;
- conserve les fichiers sources intacts ;
- crÃ©e un rapport complet d'audit.
"""

import json
import re
import shutil
from pathlib import Path
from collections import Counter, defaultdict


# ============================================================
# 1. PATHS
# ============================================================

BASE_DIR = Path(
    r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM"
    r"\Reduction_hallucinations"
)

MULTIAGENT_DIR = BASE_DIR / "MultiAgent"

INPUT_FILE_CANDIDATES = [
    MULTIAGENT_DIR
    / "outputs"
    / "agent_b_deduplicated_decisions.json",

    MULTIAGENT_DIR
    / "outputs"
    / "agent_b_validated_decisions.json",
]

SOURCE_DIR_CANDIDATES = [
    BASE_DIR
    / "PatternD"
    / "pattern_d_corrected",

    BASE_DIR
    / "PatternC"
    / "pattern_c_corrected",

    BASE_DIR
    / "PatternB"
    / "PatternB2"
    / "pattern_b2_corrected",
]

OUTPUT_DIR = (
    MULTIAGENT_DIR
    / "agent_b_corrected"
)

REPORT_FILE = (
    OUTPUT_DIR
    / "agent_b_correction_report.json"
)


# ============================================================
# 2. BASIC IO
# ============================================================

def load_json(path):
    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
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


def resolve_input_file():
    for path in INPUT_FILE_CANDIDATES:
        if path.exists():
            return path

    raise FileNotFoundError(
        "Aucun rapport Pattern B dÃ©dupliquÃ©/validÃ© trouvÃ©."
    )


def resolve_source_dir():
    for path in SOURCE_DIR_CANDIDATES:
        if (
            path.exists()
            and any(
                path.glob("*.json")
            )
        ):
            return path

    raise FileNotFoundError(
        "Aucun dossier clinique source valide trouvÃ©."
    )


# ============================================================
# 3. GENERIC ENTITY HELPERS
# ============================================================

def entity_id(entity):
    if not isinstance(entity, dict):
        return None

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
    if not isinstance(entity, dict):
        return ""

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


def entity_text(entity):
    if not isinstance(entity, dict):
        return ""

    values = []

    for key in (
        "preuve",
        "name",
        "valeur",
        "libelle",
        "parametre",
        "texte",
        "text",
    ):
        value = entity.get(
            key
        )

        if value not in (
            None,
            "",
        ):
            value = str(
                value
            ).strip()

            if (
                value
                and value not in values
            ):
                values.append(
                    value
                )

    return " | ".join(
        values
    )


def entity_page(entity):
    if not isinstance(entity, dict):
        return None

    return (
        entity.get(
            "page"
        )
        or entity.get(
            "page_number"
        )
        or entity.get(
            "numero_page"
        )
    )


# ============================================================
# 4. GENERIC RELATION HELPERS
# ============================================================

def relation_id(relation):
    if not isinstance(relation, dict):
        return None

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
    if not isinstance(relation, dict):
        return ""

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
    if not isinstance(relation, dict):
        return None

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
    if not isinstance(relation, dict):
        return None

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


def set_relation_source(
    relation,
    value,
):
    """
    Conserve le schÃ©ma original de la relation.
    """

    if (
        "identifiant_entite_sujet"
        in relation
    ):
        relation[
            "identifiant_entite_sujet"
        ] = value

    elif "from_id" in relation:
        relation[
            "from_id"
        ] = value

    elif "subject_id" in relation:
        relation[
            "subject_id"
        ] = value

    elif "source" in relation:
        relation[
            "source"
        ] = value

    else:
        relation[
            "identifiant_entite_sujet"
        ] = value


def set_relation_target(
    relation,
    value,
):
    if (
        "identifiant_entite_objet"
        in relation
    ):
        relation[
            "identifiant_entite_objet"
        ] = value

    elif "to_id" in relation:
        relation[
            "to_id"
        ] = value

    elif "object_id" in relation:
        relation[
            "object_id"
        ] = value

    elif "target" in relation:
        relation[
            "target"
        ] = value

    else:
        relation[
            "identifiant_entite_objet"
        ] = value


# ============================================================
# 5. DOCUMENT STRUCTURE
# ============================================================

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

    result = []

    for page in (
        doc.get(
            "pages",
            []
        )
        or []
    ):
        result.extend(
            page.get(
                "entities",
                []
            )
            or []
        )

    return result


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

    result = []

    for page in (
        doc.get(
            "pages",
            []
        )
        or []
    ):
        result.extend(
            page.get(
                "relations",
                []
            )
            or []
        )

    return result


def find_page(
    doc,
    page_number,
):
    if page_number is None:
        return None

    for page in (
        doc.get(
            "pages",
            []
        )
        or []
    ):
        candidate = (
            page.get(
                "page"
            )
            or page.get(
                "page_number"
            )
            or page.get(
                "numero_page"
            )
        )

        try:
            if int(
                candidate
            ) == int(
                page_number
            ):
                return page

        except Exception:
            continue

    return None


def find_entity(
    doc,
    target_id,
):
    for entity in get_entities(
        doc
    ):
        if str(
            entity_id(
                entity
            )
        ) == str(
            target_id
        ):
            return entity

    return None


def find_relation(
    doc,
    target_id,
):
    for relation in get_relations(
        doc
    ):
        if str(
            relation_id(
                relation
            )
        ) == str(
            target_id
        ):
            return relation

    return None


def relations_using_endpoint(
    doc,
    endpoint_id,
):
    result = []

    for relation in get_relations(
        doc
    ):
        if (
            str(
                relation_source(
                    relation
                )
            )
            == str(
                endpoint_id
            )
            or
            str(
                relation_target(
                    relation
                )
            )
            == str(
                endpoint_id
            )
        ):
            result.append(
                relation
            )

    return result


# ============================================================
# 6. PAGE / ID HELPERS
# ============================================================

ENTITY_ID_RE = re.compile(
    r"^P(?P<page>\d+)_E(?P<num>\d+)$",
    flags=re.I,
)

RELATION_ID_RE = re.compile(
    r"^P(?P<page>\d+)_R(?P<num>\d+)$",
    flags=re.I,
)


def infer_page_from_entity_id(
    endpoint_id,
):
    match = ENTITY_ID_RE.match(
        str(
            endpoint_id
        )
    )

    if match:
        return int(
            match.group(
                "page"
            )
        )

    return None


def next_entity_id(
    doc,
    page_number,
):
    """
    UtilisÃ© uniquement si aucun ID cible explicite n'est fourni.
    """

    max_number = 0

    for entity in get_entities(
        doc
    ):
        eid = entity_id(
            entity
        )

        if not eid:
            continue

        match = ENTITY_ID_RE.match(
            str(
                eid
            )
        )

        if (
            match
            and int(
                match.group(
                    "page"
                )
            )
            == int(
                page_number
            )
        ):
            max_number = max(
                max_number,
                int(
                    match.group(
                        "num"
                    )
                ),
            )

    return (
        f"P{int(page_number)}"
        f"_E{max_number + 1:03d}"
    )


def next_relation_id(
    doc,
    page_number,
):
    max_number = 0

    for relation in get_relations(
        doc
    ):
        rid = relation_id(
            relation
        )

        if not rid:
            continue

        match = RELATION_ID_RE.match(
            str(
                rid
            )
        )

        if (
            match
            and int(
                match.group(
                    "page"
                )
            )
            == int(
                page_number
            )
        ):
            max_number = max(
                max_number,
                int(
                    match.group(
                        "num"
                    )
                ),
            )

    return (
        f"P{int(page_number)}"
        f"_R{max_number + 1:03d}"
    )


# ============================================================
# 7. GENERIC BUILDERS
# ============================================================

def build_entity(
    entity_id_value,
    entity_type_value,
    text_value,
    page_number,
    evidence=None,
    confidence="elevee",
):
    """
    EntitÃ© TRACE gÃ©nÃ©rique.
    """

    return {
        "identifiant_entite":
            entity_id_value,

        "categorie":
            entity_type_value,

        "parametre":
            None,

        "valeur":
            text_value,

        "unite":
            None,

        "horodatage":
            None,

        "preuve":
            evidence
            or text_value,

        "nie":
            False,

        "confiance":
            confidence,

        "type_inference":
            "correction_agentique_document_grounded",

        "page":
            page_number,

        "valeur_reference":
            None,

        "name":
            text_value,

        "type":
            entity_type_value,

        "_sgce_created":
            True,

        "_sgce_pattern":
            "B",

        "_sgce_operation":
            "CREATE_FROM_EXPLICIT_EVIDENCE",

        "_sgce_agent":
            "agent_pattern_b",
    }


def build_relation(
    relation_id_value,
    relation_type_value,
    source_id,
    target_id,
    page_number,
):
    return {
        "identifiant_relation":
            relation_id_value,

        "type_relation":
            relation_type_value,

        "identifiant_entite_sujet":
            source_id,

        "identifiant_entite_objet":
            target_id,

        "page":
            page_number,

        "_sgce_created":
            True,

        "_sgce_pattern":
            "B",

        "_sgce_operation":
            "CREATE_AND_LINK",

        "_sgce_agent":
            "agent_pattern_b",
    }


# ============================================================
# 8. INSERT / REMOVE
# ============================================================

def append_entity(
    doc,
    entity,
    page_number,
):
    eid = entity_id(
        entity
    )

    added_global = False
    added_page = False

    # Global
    if isinstance(
        doc.get(
            "global_entities"
        ),
        list,
    ):
        if not any(
            str(
                entity_id(
                    existing
                )
            )
            == str(
                eid
            )
            for existing
            in doc[
                "global_entities"
            ]
        ):
            doc[
                "global_entities"
            ].append(
                entity
            )

        added_global = True

    # Page
    page = find_page(
        doc,
        page_number,
    )

    if page is not None:
        if not isinstance(
            page.get(
                "entities"
            ),
            list,
        ):
            page[
                "entities"
            ] = []

        if not any(
            str(
                entity_id(
                    existing
                )
            )
            == str(
                eid
            )
            for existing
            in page[
                "entities"
            ]
        ):
            page[
                "entities"
            ].append(
                dict(
                    entity
                )
            )

        added_page = True

    # No standard structure found
    if (
        not added_global
        and not added_page
    ):
        doc[
            "global_entities"
        ] = [
            entity
        ]

        added_global = True

    return {
        "added_global":
            added_global,

        "added_page":
            added_page,
    }


def append_relation(
    doc,
    relation,
    page_number,
):
    rid = relation_id(
        relation
    )

    added_global = False
    added_page = False

    if isinstance(
        doc.get(
            "global_relations"
        ),
        list,
    ):
        if not any(
            str(
                relation_id(
                    existing
                )
            )
            == str(
                rid
            )
            for existing
            in doc[
                "global_relations"
            ]
        ):
            doc[
                "global_relations"
            ].append(
                relation
            )

        added_global = True

    page = find_page(
        doc,
        page_number,
    )

    if page is not None:
        if not isinstance(
            page.get(
                "relations"
            ),
            list,
        ):
            page[
                "relations"
            ] = []

        if not any(
            str(
                relation_id(
                    existing
                )
            )
            == str(
                rid
            )
            for existing
            in page[
                "relations"
            ]
        ):
            page[
                "relations"
            ].append(
                dict(
                    relation
                )
            )

        added_page = True

    if (
        not added_global
        and not added_page
    ):
        doc[
            "global_relations"
        ] = [
            relation
        ]

        added_global = True

    return {
        "added_global":
            added_global,

        "added_page":
            added_page,
    }


def remove_relation_by_id(
    doc,
    rid,
):
    removed = 0

    if isinstance(
        doc.get(
            "global_relations"
        ),
        list,
    ):
        before = len(
            doc[
                "global_relations"
            ]
        )

        doc[
            "global_relations"
        ] = [
            relation
            for relation
            in doc[
                "global_relations"
            ]
            if str(
                relation_id(
                    relation
                )
            )
            != str(
                rid
            )
        ]

        removed += (
            before
            - len(
                doc[
                    "global_relations"
                ]
            )
        )

    for page in (
        doc.get(
            "pages",
            []
        )
        or []
    ):
        if not isinstance(
            page.get(
                "relations"
            ),
            list,
        ):
            continue

        before = len(
            page[
                "relations"
            ]
        )

        page[
            "relations"
        ] = [
            relation
            for relation
            in page[
                "relations"
            ]
            if str(
                relation_id(
                    relation
                )
            )
            != str(
                rid
            )
        ]

        removed += (
            before
            - len(
                page[
                    "relations"
                ]
            )
        )

    return removed


# ============================================================
# 9. INPUT NORMALIZATION
# ============================================================

def normalize_input_report(
    report,
):
    """
    Rend compatibles :
    - agent_b_deduplicated_decisions.json
    - agent_b_validated_decisions.json
    """

    operations = []

    # --------------------------------------------------------
    # Preferred: deduplicated report
    # --------------------------------------------------------

    if isinstance(
        report.get(
            "unique_corrections"
        ),
        list,
    ):
        for item in report[
            "unique_corrections"
        ]:
            operations.append(
                {
                    **item,
                    "_input_source":
                        "deduplicated",
                }
            )

        # Conflicts / refine cases are deliberately not actionable.
        return operations

    # --------------------------------------------------------
    # Fallback: validated report
    # --------------------------------------------------------

    validated = report.get(
        "validated_decisions",
        [],
    )

    for item in validated:
        final_status = item.get(
            "final_status"
        )

        final_action = item.get(
            "final_action"
        )

        if final_status != "ACCEPT":
            continue

        decision = (
            item.get(
                "agent_decision"
            )
            or {}
        )

        proposed_entities = (
            decision.get(
                "proposed_entities"
            )
            or []
        )

        metadata = (
            decision.get(
                "metadata"
            )
            or {}
        )

        proposed_entity = (
            proposed_entities[
                0
            ]
            if len(
                proposed_entities
            )
            == 1
            else None
        )

        operation = {
            "document":
                item.get(
                    "document"
                ),

            "missing_endpoint":
                metadata.get(
                    "missing_endpoint"
                ),

            "page_number":
                metadata.get(
                    "page_number"
                ),

            "status":
                final_status,

            "action":
                final_action,

            "proposed_entity":
                proposed_entity,

            "evidence":
                decision.get(
                    "evidence"
                ),

            "source_candidate_ids": [
                item.get(
                    "candidate_id"
                )
            ],

            "_input_source":
                "validated",
        }

        # Generic metadata, useful for RELINK/REMOVE future data.
        operation.update(
            {
                "existing_entity_id":
                    item.get(
                        "existing_entity_id"
                    )
                    or metadata.get(
                        "existing_entity_id"
                    )
                    or metadata.get(
                        "new_entity_id"
                    ),

                "relation_id":
                    metadata.get(
                        "relation_id"
                    ),

                "role":
                    metadata.get(
                        "role"
                    ),

                "relation_type":
                    metadata.get(
                        "relation_type"
                    ),
            }
        )

        operations.append(
            operation
        )

    return operations


# ============================================================
# 10. OPERATION: CREATE
# ============================================================

def apply_create(
    doc,
    operation,
):
    proposed = (
        operation.get(
            "proposed_entity"
        )
        or {}
    )

    endpoint_id = (
        operation.get(
            "missing_endpoint"
        )
    )

    entity_type_value = (
        proposed.get(
            "type"
        )
    )

    text_value = (
        proposed.get(
            "text"
        )
    )

    evidence = operation.get(
        "evidence"
    )

    page_number = (
        operation.get(
            "page_number"
        )
        or infer_page_from_entity_id(
            endpoint_id
        )
    )

    if not entity_type_value:
        return {
            "status":
                "SKIP",

            "reason":
                "MISSING_ENTITY_TYPE",
        }

    if not text_value:
        return {
            "status":
                "SKIP",

            "reason":
                "MISSING_ENTITY_TEXT",
        }

    if page_number is None:
        return {
            "status":
                "SKIP",

            "reason":
                "MISSING_PAGE_NUMBER",
        }

    # Explicit missing endpoint is preferred.
    if endpoint_id:
        if find_entity(
            doc,
            endpoint_id,
        ):
            return {
                "status":
                    "SKIP",

                "reason":
                    "ENDPOINT_ALREADY_EXISTS",

                "endpoint_id":
                    endpoint_id,
            }

        new_id = endpoint_id

    else:
        new_id = next_entity_id(
            doc,
            page_number,
        )

    # For B1, an opaque endpoint should normally already be referenced
    # by an existing relation. If an explicit endpoint exists but no relation
    # references it, automatic creation is blocked.
    linked_relations = []

    if endpoint_id:
        linked_relations = (
            relations_using_endpoint(
                doc,
                endpoint_id,
            )
        )

        if not linked_relations:
            return {
                "status":
                    "SKIP",

                "reason":
                    "NO_RELATION_REFERENCES_MISSING_ENDPOINT",

                "endpoint_id":
                    endpoint_id,
            }

    entity = build_entity(
        new_id,
        entity_type_value,
        text_value,
        page_number,
        evidence,
    )

    insertion = append_entity(
        doc,
        entity,
        page_number,
    )

    return {
        "status":
            "APPLIED",

        "operation":
            "CREATE_FROM_EXPLICIT_EVIDENCE",

        "created_entity_id":
            new_id,

        "entity_type":
            entity_type_value,

        "entity_text":
            text_value,

        "page_number":
            page_number,

        "relations_using_endpoint": [
            {
                "relation_id":
                    relation_id(
                        relation
                    ),

                "relation_type":
                    relation_type(
                        relation
                    ),

                "source":
                    relation_source(
                        relation
                    ),

                "target":
                    relation_target(
                        relation
                    ),
            }
            for relation
            in linked_relations
        ],

        "insertion":
            insertion,
    }


# ============================================================
# 11. OPERATION: RELINK
# ============================================================

def apply_relink(
    doc,
    operation,
):
    old_endpoint = (
        operation.get(
            "missing_endpoint"
        )
        or operation.get(
            "old_endpoint"
        )
    )

    new_entity_id = (
        operation.get(
            "existing_entity_id"
        )
        or operation.get(
            "new_entity_id"
        )
    )

    role = (
        operation.get(
            "role"
        )
        or ""
    ).upper()

    target_relation_id = (
        operation.get(
            "relation_id"
        )
    )

    if not old_endpoint:
        return {
            "status":
                "SKIP",

            "reason":
                "MISSING_OLD_ENDPOINT",
        }

    if not new_entity_id:
        return {
            "status":
                "SKIP",

            "reason":
                "MISSING_NEW_ENTITY_ID",
        }

    if find_entity(
        doc,
        new_entity_id,
    ) is None:
        return {
            "status":
                "SKIP",

            "reason":
                "NEW_ENTITY_NOT_FOUND",

            "new_entity_id":
                new_entity_id,
        }

    candidates = []

    for relation in get_relations(
        doc
    ):
        if (
            target_relation_id
            and str(
                relation_id(
                    relation
                )
            )
            != str(
                target_relation_id
            )
        ):
            continue

        if (
            str(
                relation_source(
                    relation
                )
            )
            == str(
                old_endpoint
            )
            or str(
                relation_target(
                    relation
                )
            )
            == str(
                old_endpoint
            )
        ):
            candidates.append(
                relation
            )

    if not candidates:
        return {
            "status":
                "SKIP",

            "reason":
                "NO_RELATION_TO_RELINK",
        }

    changed = []

    for relation in candidates:
        before_source = relation_source(
            relation
        )

        before_target = relation_target(
            relation
        )

        if (
            role in (
                "",
                "SOURCE",
            )
            and str(
                before_source
            )
            == str(
                old_endpoint
            )
        ):
            set_relation_source(
                relation,
                new_entity_id,
            )

        if (
            role in (
                "",
                "TARGET",
            )
            and str(
                before_target
            )
            == str(
                old_endpoint
            )
        ):
            set_relation_target(
                relation,
                new_entity_id,
            )

        if (
            str(
                relation_source(
                    relation
                )
            )
            != str(
                before_source
            )
            or str(
                relation_target(
                    relation
                )
            )
            != str(
                before_target
            )
        ):
            changed.append(
                {
                    "relation_id":
                        relation_id(
                            relation
                        ),

                    "before_source":
                        before_source,

                    "before_target":
                        before_target,

                    "after_source":
                        relation_source(
                            relation
                        ),

                    "after_target":
                        relation_target(
                            relation
                        ),
                }
            )

    if not changed:
        return {
            "status":
                "SKIP",

            "reason":
                "RELINK_NO_CHANGE",
        }

    return {
        "status":
            "APPLIED",

        "operation":
            "RELINK",

        "old_endpoint":
            old_endpoint,

        "new_entity_id":
            new_entity_id,

        "relations_changed":
            changed,
    }


# ============================================================
# 12. OPERATION: REMOVE RELATION
# ============================================================

def apply_remove_relation(
    doc,
    operation,
):
    rid = operation.get(
        "relation_id"
    )

    if not rid:
        return {
            "status":
                "SKIP",

            "reason":
                "MISSING_RELATION_ID",
        }

    if find_relation(
        doc,
        rid,
    ) is None:
        return {
            "status":
                "SKIP",

            "reason":
                "RELATION_NOT_FOUND",

            "relation_id":
                rid,
        }

    removed = remove_relation_by_id(
        doc,
        rid,
    )

    if removed <= 0:
        return {
            "status":
                "SKIP",

            "reason":
                "RELATION_REMOVE_FAILED",
        }

    return {
        "status":
            "APPLIED",

        "operation":
            "REMOVE_RELATION",

        "relation_id":
            rid,

        "removed_occurrences":
            removed,
    }


# ============================================================
# 13. OPERATION: CREATE AND LINK
# ============================================================

def apply_create_and_link(
    doc,
    operation,
):
    create_result = apply_create(
        doc,
        operation,
    )

    if (
        create_result.get(
            "status"
        )
        != "APPLIED"
    ):
        return create_result

    # If existing relation already referenced opaque endpoint,
    # entity creation alone resolves B1.
    if create_result.get(
        "relations_using_endpoint"
    ):
        create_result[
            "operation"
        ] = "CREATE_AND_LINK"

        create_result[
            "link_mode"
        ] = "EXISTING_RELATION_ENDPOINT_RESOLVED"

        return create_result

    # Generic future B2 explicit relation support
    relation_type_value = (
        operation.get(
            "relation_type"
        )
    )

    source_id = (
        operation.get(
            "source_id"
        )
    )

    target_id = (
        operation.get(
            "target_id"
        )
    )

    created_entity_id = (
        create_result.get(
            "created_entity_id"
        )
    )

    created_role = (
        operation.get(
            "created_entity_role"
        )
        or operation.get(
            "role"
        )
        or ""
    ).upper()

    if (
        not relation_type_value
        or not source_id
        and created_role != "SOURCE"
        or not target_id
        and created_role != "TARGET"
    ):
        # Entity created, but no explicit new relation can safely be made.
        create_result[
            "operation"
        ] = "CREATE_FROM_EXPLICIT_EVIDENCE"

        create_result[
            "link_mode"
        ] = "NO_NEW_RELATION_METADATA"

        return create_result

    if created_role == "SOURCE":
        source_id = created_entity_id

    elif created_role == "TARGET":
        target_id = created_entity_id

    if (
        find_entity(
            doc,
            source_id,
        )
        is None
        or find_entity(
            doc,
            target_id,
        )
        is None
    ):
        create_result[
            "warning"
        ] = (
            "Entity created but relation endpoints "
            "could not be verified."
        )

        return create_result

    page_number = (
        operation.get(
            "page_number"
        )
        or infer_page_from_entity_id(
            created_entity_id
        )
    )

    rid = next_relation_id(
        doc,
        page_number,
    )

    relation = build_relation(
        rid,
        relation_type_value,
        source_id,
        target_id,
        page_number,
    )

    append_relation(
        doc,
        relation,
        page_number,
    )

    create_result[
        "operation"
    ] = "CREATE_AND_LINK"

    create_result[
        "created_relation_id"
    ] = rid

    create_result[
        "created_relation_type"
    ] = relation_type_value

    return create_result


# ============================================================
# 14. MASTER APPLY
# ============================================================

ACTION_ALIASES = {
    "CREATE_FROM_EXPLICIT_EVIDENCE":
        "CREATE_FROM_EXPLICIT_EVIDENCE",

    "CREATE_AND_LINK":
        "CREATE_AND_LINK",

    "RELINK":
        "RELINK",

    "RELINK_EXISTING_ENTITY":
        "RELINK",

    "REMOVE_RELATION":
        "REMOVE_RELATION",
}


PROTECTED_ACTIONS = {
    None,
    "",
    "NONE",
    "KEEP",
    "REVIEW",
    "REFINE_ENTITY_SPAN",
    "CONFLICT",
}


def apply_operation(
    doc,
    operation,
):
    action = operation.get(
        "action"
    )

    if action in PROTECTED_ACTIONS:
        return {
            "status":
                "PROTECTED",

            "reason":
                f"ACTION_NOT_AUTOMATICALLY_APPLIED:{action}",
        }

    canonical = ACTION_ALIASES.get(
        action
    )

    if canonical is None:
        return {
            "status":
                "PROTECTED",

            "reason":
                f"UNKNOWN_ACTION:{action}",
        }

    if canonical == "CREATE_FROM_EXPLICIT_EVIDENCE":
        return apply_create(
            doc,
            operation,
        )

    if canonical == "CREATE_AND_LINK":
        return apply_create_and_link(
            doc,
            operation,
        )

    if canonical == "RELINK":
        return apply_relink(
            doc,
            operation,
        )

    if canonical == "REMOVE_RELATION":
        return apply_remove_relation(
            doc,
            operation,
        )

    return {
        "status":
            "PROTECTED",

        "reason":
            f"UNHANDLED_ACTION:{canonical}",
    }


# ============================================================
# 15. MAIN
# ============================================================

def main():
    input_file = resolve_input_file()

    source_dir = resolve_source_dir()

    report = load_json(
        input_file
    )

    operations_to_apply = normalize_input_report(
        report
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Copy clinical source JSONs
    # --------------------------------------------------------

    source_files = [
        path
        for path in source_dir.glob(
            "*.json"
        )
        if path.is_file()
    ]

    clinical_files = []

    for src in source_files:
        # Ignore known report files if present inside clinical directory.
        try:
            content = load_json(
                src
            )

            is_clinical = (
                isinstance(
                    content,
                    dict,
                )
                and (
                    isinstance(
                        content.get(
                            "global_entities"
                        ),
                        list,
                    )
                    or isinstance(
                        content.get(
                            "pages"
                        ),
                        list,
                    )
                )
            )

            if not is_clinical:
                continue

        except Exception:
            continue

        shutil.copy2(
            src,
            OUTPUT_DIR
            / src.name,
        )

        clinical_files.append(
            src
        )

    # --------------------------------------------------------
    # Group operations by document
    # --------------------------------------------------------

    by_document = defaultdict(
        list
    )

    for operation in operations_to_apply:
        document = operation.get(
            "document"
        )

        if document:
            by_document[
                document
            ].append(
                operation
            )

    operation_logs = []

    errors = []

    modified_documents = set()

    # --------------------------------------------------------
    # Apply
    # --------------------------------------------------------

    for (
        document,
        operations,
    ) in by_document.items():

        target_path = (
            OUTPUT_DIR
            / document
        )

        if not target_path.exists():
            for operation in operations:
                operation_logs.append(
                    {
                        "document":
                            document,

                        "status":
                            "ERROR",

                        "reason":
                            "DOCUMENT_NOT_FOUND_IN_SOURCE",

                        "requested_action":
                            operation.get(
                                "action"
                            ),
                    }
                )

            continue

        try:
            doc = load_json(
                target_path
            )

            changed = False

            for operation in operations:
                result = apply_operation(
                    doc,
                    operation,
                )

                result[
                    "document"
                ] = document

                result[
                    "requested_action"
                ] = operation.get(
                    "action"
                )

                result[
                    "source_candidate_ids"
                ] = operation.get(
                    "source_candidate_ids",
                    [],
                )

                result[
                    "missing_endpoint"
                ] = operation.get(
                    "missing_endpoint"
                )

                operation_logs.append(
                    result
                )

                if result.get(
                    "status"
                ) == "APPLIED":
                    changed = True

            if changed:
                save_json(
                    target_path,
                    doc,
                )

                modified_documents.add(
                    document
                )

        except Exception as exc:
            errors.append(
                {
                    "document":
                        document,

                    "error":
                        repr(
                            exc
                        ),
                }
            )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    status_counts = Counter(
        item.get(
            "status"
        )
        for item in operation_logs
    )

    applied_action_counts = Counter(
        item.get(
            "operation"
        )
        for item in operation_logs
        if item.get(
            "status"
        )
        == "APPLIED"
    )

    skip_reason_counts = Counter(
        item.get(
            "reason"
        )
        for item in operation_logs
        if item.get(
            "status"
        )
        in {
            "SKIP",
            "PROTECTED",
            "ERROR",
        }
    )

    output_report = {
        "corrector":
            "agent_b_corrector",

        "mode":
            "GENERIC_PATTERN_B_CORRECTION",

        "input_file":
            str(
                input_file
            ),

        "source_directory":
            str(
                source_dir
            ),

        "output_directory":
            str(
                OUTPUT_DIR
            ),

        "summary": {
            "clinical_documents_copied":
                len(
                    clinical_files
                ),

            "operations_received":
                len(
                    operations_to_apply
                ),

            "operations_applied":
                status_counts.get(
                    "APPLIED",
                    0,
                ),

            "operations_skipped":
                status_counts.get(
                    "SKIP",
                    0,
                ),

            "operations_protected":
                status_counts.get(
                    "PROTECTED",
                    0,
                ),

            "operation_errors":
                status_counts.get(
                    "ERROR",
                    0,
                ),

            "documents_modified":
                len(
                    modified_documents
                ),

            "applied_action_counts":
                dict(
                    applied_action_counts
                ),

            "skip_reason_counts":
                dict(
                    skip_reason_counts
                ),

            "exceptions":
                len(
                    errors
                ),
        },

        "modified_documents":
            sorted(
                modified_documents
            ),

        "operations":
            operation_logs,

        "errors":
            errors,
    }

    save_json(
        REPORT_FILE,
        output_report,
    )

    # --------------------------------------------------------
    # Console
    # --------------------------------------------------------

    print("=" * 100)
    print("TRACE / SGCE - GENERIC AGENT B CORRECTOR")
    print("=" * 100)

    print(
        f"EntrÃ©e dÃ©cisions                    : "
        f"{input_file}"
    )

    print(
        f"Source clinique                     : "
        f"{source_dir}"
    )

    print(
        f"Sortie clinique                     : "
        f"{OUTPUT_DIR}"
    )

    print()

    print(
        f"Documents cliniques copiÃ©s          : "
        f"{len(clinical_files)}"
    )

    print(
        f"OpÃ©rations reÃ§ues                   : "
        f"{len(operations_to_apply)}"
    )

    print(
        f"OpÃ©rations appliquÃ©es               : "
        f"{status_counts.get('APPLIED', 0)}"
    )

    print(
        f"OpÃ©rations SKIP                     : "
        f"{status_counts.get('SKIP', 0)}"
    )

    print(
        f"OpÃ©rations protÃ©gÃ©es                : "
        f"{status_counts.get('PROTECTED', 0)}"
    )

    print(
        f"Documents modifiÃ©s                  : "
        f"{len(modified_documents)}"
    )

    print(
        f"Erreurs                             : "
        f"{len(errors)}"
    )

    print()

    print("ACTIONS APPLIQUEES")
    print("-" * 100)

    if applied_action_counts:
        for (
            action,
            count,
        ) in applied_action_counts.most_common():
            print(
                f"{str(action):<45}: {count}"
            )
    else:
        print(
            "Aucune action appliquÃ©e."
        )

    if skip_reason_counts:
        print()
        print("RAISONS SKIP / PROTECTION")
        print("-" * 100)

        for (
            reason,
            count,
        ) in skip_reason_counts.most_common():
            print(
                f"{str(reason):<60}: {count}"
            )

    print()

    print(
        f"Rapport                              : "
        f"{REPORT_FILE}"
    )

    print()

    print(
        "Les fichiers sources n'ont pas Ã©tÃ© modifiÃ©s."
    )


if __name__ == "__main__":
    main()

