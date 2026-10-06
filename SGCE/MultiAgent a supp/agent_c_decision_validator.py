# -*- coding: utf-8 -*-
"""
agent_c_decision_validator.py
=============================

TRACE / SGCE â€” Validateur dÃ©terministe Pattern C document-grounded

EntrÃ©es :
  MultiAgent/outputs/agent_c_decisions.json
  MultiAgent/agent_b_corrected

Valide notamment REMOVE_REIFIED_ENTITY uniquement si :
- l'entitÃ© existe encore
- text_grounded == True
- la preuve est non vide
- le type correspond encore
- aucune relation active ne rÃ©fÃ©rence l'entitÃ©
- l'entitÃ© du graphe reste compatible avec la preuve

MERGE :
- interdit sans source + cible explicites

Aucune donnÃ©e clinique n'est modifiÃ©e.
"""

import json
from collections import Counter
from pathlib import Path


BASE_DIR = Path(
    r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM"
    r"\Reduction_hallucinations"
)

MULTIAGENT_DIR = BASE_DIR / "MultiAgent"

AGENT_DECISIONS = (
    MULTIAGENT_DIR
    / "outputs"
    / "agent_c_decisions.json"
)

CLINICAL_DIR_CANDIDATES = [
    MULTIAGENT_DIR
    / "agent_b_corrected",

    BASE_DIR
    / "PatternD"
    / "pattern_d_corrected",
]

OUTPUT_FILE = (
    MULTIAGENT_DIR
    / "outputs"
    / "agent_c_validated_decisions.json"
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


def resolve_clinical_dir():
    for path in CLINICAL_DIR_CANDIDATES:
        if (
            path.exists()
            and any(
                path.glob("*.json")
            )
        ):
            return path

    raise FileNotFoundError(
        "Aucun dossier clinique valide trouvÃ©."
    )


# ============================================================
# HELPERS
# ============================================================

def entity_id(e):
    return (
        e.get("identifiant_entite")
        or e.get("id")
        or e.get("entity_id")
    )


def entity_type(e):
    return (
        e.get("categorie")
        or e.get("type")
        or e.get("entity_type")
        or ""
    )


def entity_text(e):
    vals = []

    for key in (
        "preuve",
        "name",
        "valeur",
        "libelle",
        "parametre",
        "texte",
        "text",
    ):
        value = e.get(key)

        if value not in (
            None,
            "",
        ):
            s = str(
                value
            ).strip()

            if (
                s
                and s not in vals
            ):
                vals.append(
                    s
                )

    return " | ".join(
        vals
    )


def relation_id(r):
    return (
        r.get("identifiant_relation")
        or r.get("id")
        or r.get("relation_id")
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
    eid,
):
    for entity in get_entities(
        doc
    ):
        if str(
            entity_id(
                entity
            )
        ) == str(
            eid
        ):
            return entity

    return None


def relations_for_entity(
    doc,
    eid,
):
    return [
        relation
        for relation
        in get_relations(
            doc
        )
        if (
            str(
                relation_source(
                    relation
                )
            )
            == str(
                eid
            )
            or
            str(
                relation_target(
                    relation
                )
            )
            == str(
                eid
            )
        )
    ]


def load_docs(
    directory,
):
    docs = {}

    for path in directory.glob(
        "*.json"
    ):
        try:
            doc = load_json(
                path
            )

            if isinstance(
                doc,
                dict,
            ):
                docs[
                    path.name
                ] = doc

        except Exception:
            pass

    return docs


# ============================================================
# REMOVE VALIDATION
# ============================================================

def validate_remove(
    decision,
    doc,
):
    metadata = (
        decision.get(
            "metadata"
        )
        or {}
    )

    eid = metadata.get(
        "candidate_entity_id"
    )

    expected_type = metadata.get(
        "candidate_entity_type"
    )

    grounded = (
        metadata.get(
            "text_grounded"
        )
        is True
    )

    evidence = str(
        decision.get(
            "evidence"
        )
        or ""
    ).strip()

    checks = []

    # 1. text grounding
    checks.append({
        "check":
            "TEXT_GROUNDED",

        "passed":
            grounded,
    })

    # 2. evidence exists
    evidence_ok = bool(
        evidence
    )

    checks.append({
        "check":
            "EVIDENCE_NON_EMPTY",

        "passed":
            evidence_ok,
    })

    # 3. entity id
    id_ok = bool(
        eid
    )

    checks.append({
        "check":
            "ENTITY_ID_AVAILABLE",

        "passed":
            id_ok,

        "entity_id":
            eid,
    })

    if not id_ok:
        return {
            "final_status":
                "REVIEW",

            "final_action":
                "NONE",

            "reason":
                "Identifiant de l'entitÃ© candidat absent.",

            "checks":
                checks,
        }

    # 4. entity exists
    entity = find_entity(
        doc,
        eid,
    )

    exists = (
        entity is not None
    )

    checks.append({
        "check":
            "ENTITY_EXISTS",

        "passed":
            exists,
    })

    if not exists:
        return {
            "final_status":
                "REVIEW",

            "final_action":
                "NONE",

            "reason":
                "L'entitÃ© n'existe plus dans le graphe courant.",

            "checks":
                checks,
        }

    # 5. type still matches
    actual_type = entity_type(
        entity
    )

    type_ok = (
        not expected_type
        or actual_type
        == expected_type
    )

    checks.append({
        "check":
            "ENTITY_TYPE_STILL_MATCHES",

        "passed":
            type_ok,

        "actual":
            actual_type,

        "expected":
            expected_type,
    })

    # 6. no active relations
    relations = relations_for_entity(
        doc,
        eid,
    )

    no_relations = (
        len(
            relations
        )
        == 0
    )

    checks.append({
        "check":
            "ENTITY_HAS_NO_ACTIVE_RELATIONS",

        "passed":
            no_relations,

        "relation_count":
            len(
                relations
            ),

        "relation_ids": [
            relation_id(
                r
            )
            for r in relations
        ],
    })

    # 7. graph entity text is compatible with document-grounded evidence
    actual_text = entity_text(
        entity
    )

    actual_parts = [
        x.strip()
        for x in actual_text.split(
            "|"
        )
        if x.strip()
    ]

    text_ok = (
        bool(
            actual_text
        )
        and bool(
            evidence
        )
        and (
            actual_text in evidence
            or evidence in actual_text
            or any(
                part in evidence
                for part in actual_parts
                if len(
                    part
                )
                >= 3
            )
        )
    )

    checks.append({
        "check":
            "ENTITY_TEXT_SUPPORTED_BY_DOCUMENT_EVIDENCE",

        "passed":
            text_ok,

        "actual_text":
            actual_text,

        "evidence":
            evidence,
    })

    # ACCEPT
    if (
        grounded
        and evidence_ok
        and exists
        and type_ok
        and no_relations
        and text_ok
    ):
        return {
            "final_status":
                "ACCEPT",

            "final_action":
                "REMOVE_REIFIED_ENTITY",

            "reason":
                (
                    "Suppression validÃ©e : entitÃ© document-grounded, "
                    "existante, isolÃ©e du graphe et compatible avec "
                    "la preuve textuelle source."
                ),

            "checks":
                checks,
        }

    # REVIEW, never force deletion
    return {
        "final_status":
            "REVIEW",

        "final_action":
            "NONE",

        "reason":
            (
                "Au moins une condition de sÃ©curitÃ© documentaire "
                "ou structurelle empÃªche la suppression automatique."
            ),

        "checks":
            checks,
    }


# ============================================================
# MERGE VALIDATION
# ============================================================

def validate_merge(
    decision,
    doc,
):
    metadata = (
        decision.get(
            "metadata"
        )
        or {}
    )

    source_id = (
        metadata.get(
            "merge_source_id"
        )
        or metadata.get(
            "source_entity_id"
        )
    )

    target_id = (
        metadata.get(
            "merge_target_id"
        )
        or metadata.get(
            "target_entity_id"
        )
    )

    grounded = (
        metadata.get(
            "text_grounded"
        )
        is True
    )

    checks = [
        {
            "check":
                "TEXT_GROUNDED",

            "passed":
                grounded,
        },
        {
            "check":
                "MERGE_SOURCE_EXPLICIT",

            "passed":
                bool(
                    source_id
                ),

            "source_id":
                source_id,
        },
        {
            "check":
                "MERGE_TARGET_EXPLICIT",

            "passed":
                bool(
                    target_id
                ),

            "target_id":
                target_id,
        },
    ]

    if (
        not grounded
        or not source_id
        or not target_id
    ):
        return {
            "final_status":
                "REVIEW",

            "final_action":
                "NONE",

            "reason":
                (
                    "MERGE interdit sans preuve documentaire "
                    "et source/cible explicitement identifiÃ©es."
                ),

            "checks":
                checks,
        }

    source = find_entity(
        doc,
        source_id,
    )

    target = find_entity(
        doc,
        target_id,
    )

    source_exists = (
        source is not None
    )

    target_exists = (
        target is not None
    )

    checks.extend([
        {
            "check":
                "MERGE_SOURCE_EXISTS",

            "passed":
                source_exists,
        },
        {
            "check":
                "MERGE_TARGET_EXISTS",

            "passed":
                target_exists,
        },
    ])

    if (
        not source_exists
        or not target_exists
    ):
        return {
            "final_status":
                "REVIEW",

            "final_action":
                "NONE",

            "reason":
                "Source ou cible du MERGE absente du graphe.",

            "checks":
                checks,
        }

    different = (
        str(
            source_id
        )
        != str(
            target_id
        )
    )

    compatible = (
        entity_type(
            source
        )
        == entity_type(
            target
        )
    )

    checks.extend([
        {
            "check":
                "SOURCE_DIFFERS_FROM_TARGET",

            "passed":
                different,
        },
        {
            "check":
                "MERGE_TYPES_COMPATIBLE",

            "passed":
                compatible,

            "source_type":
                entity_type(
                    source
                ),

            "target_type":
                entity_type(
                    target
                ),
        },
    ])

    if (
        grounded
        and different
        and compatible
    ):
        return {
            "final_status":
                "ACCEPT",

            "final_action":
                "MERGE",

            "reason":
                (
                    "MERGE document-grounded avec source/cible explicites "
                    "et types compatibles."
                ),

            "checks":
                checks,
        }

    return {
        "final_status":
            "REVIEW",

        "final_action":
            "NONE",

        "reason":
            "MERGE insuffisamment sÃ»r.",

        "checks":
            checks,
    }


# ============================================================
# MASTER
# ============================================================

def validate_decision(
    decision,
    doc,
):
    action = decision.get(
        "action"
    )

    if action == "NONE":
        return {
            "final_status":
                "REVIEW",

            "final_action":
                "NONE",

            "reason":
                "Aucune correction automatique proposÃ©e.",

            "checks":
                [],
        }

    if action == "REMOVE_REIFIED_ENTITY":
        return validate_remove(
            decision,
            doc,
        )

    if action == "MERGE":
        return validate_merge(
            decision,
            doc,
        )

    return {
        "final_status":
            "REVIEW",

        "final_action":
            "NONE",

        "reason":
            (
                f"Action Pattern C non validÃ©e automatiquement : "
                f"{action}"
            ),

        "checks":
            [],
    }


# ============================================================
# MAIN
# ============================================================

def main():
    if not AGENT_DECISIONS.exists():
        raise FileNotFoundError(
            f"DÃ©cisions Agent C introuvables : "
            f"{AGENT_DECISIONS}"
        )

    clinical_dir = resolve_clinical_dir()

    docs = load_docs(
        clinical_dir
    )

    agent_output = load_json(
        AGENT_DECISIONS
    )

    decisions = (
        agent_output.get(
            "decisions",
            []
        )
        if isinstance(
            agent_output,
            dict,
        )
        else []
    )

    validated = []

    for decision in decisions:
        document = decision.get(
            "document"
        )

        doc = docs.get(
            document
        )

        if doc is None:
            validated.append({
                "candidate_id":
                    decision.get(
                        "candidate_id"
                    ),

                "document":
                    document,

                "agent_decision":
                    decision,

                "final_status":
                    "REVIEW",

                "final_action":
                    "NONE",

                "reason":
                    "Document clinique courant introuvable.",

                "checks":
                    [],
            })

            continue

        result = validate_decision(
            decision,
            doc,
        )

        validated.append({
            "candidate_id":
                decision.get(
                    "candidate_id"
                ),

            "document":
                document,

            "agent_decision":
                decision,

            **result,
        })

    status_counts = Counter(
        item.get(
            "final_status"
        )
        for item in validated
    )

    action_counts = Counter(
        item.get(
            "final_action"
        )
        for item in validated
    )

    output = {
        "validator":
            "agent_c_decision_validator",

        "mode":
            "DOCUMENT_GROUNDED",

        "clinical_context_directory":
            str(
                clinical_dir
            ),

        "summary": {
            "decisions_received":
                len(
                    decisions
                ),

            "decisions_validated":
                len(
                    validated
                ),

            "status_counts":
                dict(
                    status_counts
                ),

            "action_counts":
                dict(
                    action_counts
                ),
        },

        "validated_decisions":
            validated,
    }

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_FILE.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=" * 96)
    print("TRACE / SGCE - AGENT C DECISION VALIDATOR DOCUMENT-GROUNDED")
    print("=" * 96)

    print(
        f"Contexte clinique                 : {clinical_dir}"
    )

    print(
        f"DÃ©cisions reÃ§ues                  : {len(decisions)}"
    )

    print(
        f"DÃ©cisions validÃ©es                : {len(validated)}"
    )

    print()
    print("STATUTS FINAUX")
    print("-" * 96)

    for name, count in (
        status_counts.most_common()
    ):
        print(
            f"{str(name):<40}: {count}"
        )

    print()
    print("ACTIONS FINALES")
    print("-" * 96)

    for name, count in (
        action_counts.most_common()
    ):
        print(
            f"{str(name):<40}: {count}"
        )

    print()
    print(
        f"Sortie                            : {OUTPUT_FILE}"
    )

    print()
    print(
        "Aucune donnÃ©e clinique n'a Ã©tÃ© modifiÃ©e."
    )


if __name__ == "__main__":
    main()

