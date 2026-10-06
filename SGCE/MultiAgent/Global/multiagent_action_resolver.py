# -*- coding: utf-8 -*-
"""
multiagent_action_resolver.py
=============================

TRACE / SGCE — Multi-Agent Action Resolver

Entrée :
  MultiAgent/outputs/multiagent_adjudication_report.json

But
---
Transformer les cas :
  RESOLVED_CLASSIFICATION_ONLY

en actions concrètes UNIQUEMENT lorsque tous les paramètres requis
sont disponibles et cohérents.

Familles supportées
-------------------
B :
- CREATE_FROM_EXPLICIT_EVIDENCE
- RELINK_EXISTING_ENTITY
- REFINE_ENTITY_SPAN reste protégé

C :
- REMOVE_REIFIED_ENTITY
- MERGE uniquement si source + cible explicites

D :
- RETYPE_ENTITY
- RELINK si ancien/nouvel endpoint explicites
- REMOVE_INVALID_RELATION si relation_id explicite

PATIENT_REFERENCE :
- KEEP
- aucune suppression automatique d'un contenu référentiel

Sorties :
  MultiAgent/outputs/multiagent_resolved_actions.json

IMPORTANT
---------
- Aucun JSON clinique n'est modifié.
- Les 25 UNRESOLVED restent intacts.
- Une classification résolue ne devient PAS automatiquement une correction.
- Une action destructive sans paramètres complets reste REVIEW/NO_ACTION.
"""

import json
from pathlib import Path
from collections import Counter


# ============================================================
# 1. PATHS
# ============================================================

AGENT_DIR = Path(__file__).resolve().parent
MULTIAGENT_DIR = AGENT_DIR.parent
SGCE_DIR = MULTIAGENT_DIR.parent
BASE_DIR = SGCE_DIR.parent
M = MULTIAGENT_DIR
PATTERNS_DIR = SGCE_DIR / "Patterns"
INPUT_FILE = (
    M
    / "outputs"
    / "multiagent_adjudication_report.json"
)

OUTPUT_FILE = (
    M
    / "outputs"
    / "multiagent_resolved_actions.json"
)


# ============================================================
# 2. IO
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


# ============================================================
# 3. HELPERS
# ============================================================

def first_nonempty(*values):
    for value in values:
        if value not in (
            None,
            "",
            [],
            {},
        ):
            return value

    return None


def get_vote(
    case,
    agent_name,
):
    for vote in (
        case.get(
            "votes",
            []
        )
        or []
    ):
        if vote.get(
            "agent"
        ) == agent_name:
            return vote

    return {}


def vote_proposal(
    case,
    agent_name,
):
    vote = get_vote(
        case,
        agent_name,
    )

    proposal = vote.get(
        "proposal"
    )

    return (
        proposal
        if isinstance(
            proposal,
            dict,
        )
        else {}
    )


def metadata_of(case):
    """
    Reconstruit les métadonnées utilisables par le resolver.

    Compatible avec deux routes :
    1) cas issus de l'adjudication (votes / proposed_correction) ;
    2) ACCEPT directs issus des agents spécialisés, injectés dans `cases`.

    Aucun contenu clinique n'est inventé : seules des valeurs déjà présentes
    dans le cas courant sont propagées.
    """

    merged = {}

    def merge_dict(obj):
        if not isinstance(obj, dict):
            return

        for key, value in obj.items():
            if value not in (None, "", [], {}):
                merged[key] = value

    # 1. Métadonnées éventuellement conservées directement.
    merge_dict(case.get("metadata"))

    # 2. Décision de l'agent spécialisé.
    agent_decision = case.get("agent_decision")
    merge_dict(agent_decision)

    if isinstance(agent_decision, dict):
        merge_dict(agent_decision.get("metadata"))
        merge_dict(agent_decision.get("parameters"))
        merge_dict(agent_decision.get("proposed_correction"))
        merge_dict(agent_decision.get("symbolic_candidate"))

        # Certains agents stockent l'action sous proposed_action.
        if (
            "action" not in merged
            and agent_decision.get("proposed_action")
        ):
            merged["action"] = agent_decision.get("proposed_action")

    # 3. Candidat symbolique conservé au niveau du cas.
    merge_dict(case.get("symbolic_candidate"))

    # 4. Votes de l'adjudication.
    for vote in (case.get("votes", []) or []):
        proposal = vote.get("proposal")
        merge_dict(proposal)

        if isinstance(proposal, dict):
            merge_dict(proposal.get("metadata"))
            merge_dict(proposal.get("parameters"))

    # 5. Correction proposée par l'adjudication.
    correction = case.get("proposed_correction")
    merge_dict(correction)

    # 6. Paramètres éventuellement déjà matérialisés.
    merge_dict(case.get("parameters"))

    # 7. Champs directs du cas injecté.
    direct_keys = (
        "action",
        "final_action",
        "proposed_action",
        "recommended_action",
        "entity_type",
        "expected_type",
        "entity_text",
        "text",
        "missing_endpoint",
        "endpoint_id",
        "relation_id",
        "target_relation_id",
        "relation_type",
        "role",
        "endpoint_role",
        "page_number",
        "old_endpoint",
        "new_entity_id",
        "existing_entity_id",
        "entity_id",
        "new_type",
        "source_entity_id",
        "target_entity_id",
    )

    for key in direct_keys:
        value = case.get(key)
        if value not in (None, "", [], {}):
            merged[key] = value

    # Le contrat global utilise final_action pour les ACCEPT directs.
    final_action = first_nonempty(
        case.get("final_action"),
        merged.get("final_action"),
        merged.get("action"),
        merged.get("proposed_action"),
        merged.get("recommended_action"),
    )

    if final_action:
        merged["action"] = final_action

    return merged


# ============================================================
# 4. FAMILY B
# ============================================================

def resolve_b(case):
    """
    B REVIEW peut provenir notamment de :
    - REFINE_ENTITY_SPAN
    - entité manquante
    - relink possible

    On n'invente jamais le span.
    """

    ontology = vote_proposal(
        case,
        "ONTOLOGY_STRUCTURE",
    )

    proposed = metadata_of(
        case
    )

    action = first_nonempty(
        case.get("final_action"),
        case.get("action"),
        proposed.get(
            "action"
        ),
        proposed.get(
            "proposed_action"
        ),
        ontology.get(
            "action"
        ),
    )

    # --------------------------------------------------------
    # Explicit CREATE
    # --------------------------------------------------------

    if action in {
        "CREATE_FROM_EXPLICIT_EVIDENCE",
        "CREATE_AND_LINK",
    }:
        entity_type = first_nonempty(
            proposed.get(
                "expected_type"
            ),
            proposed.get(
                "entity_type"
            ),
        )

        entity_text = first_nonempty(
            proposed.get(
                "entity_text"
            ),
            proposed.get(
                "text"
            ),
        )

        endpoint = first_nonempty(
            proposed.get(
                "missing_endpoint"
            ),
            proposed.get(
                "endpoint_id"
            ),
        )

        relation_id = first_nonempty(proposed.get("relation_id"), proposed.get("target_relation_id"))
        role = str(first_nonempty(proposed.get("role"), proposed.get("endpoint_role")) or "").upper()

        if (
            entity_type
            and entity_text
            and endpoint
            and relation_id
            and role in {"SOURCE", "TARGET"}
        ):
            return {
                "status":
                    "ACTIONABLE",

                "action":
                    "CREATE_FROM_EXPLICIT_EVIDENCE",

                "parameters": {
                    "missing_endpoint":
                        endpoint,

                    "entity_type":
                        entity_type,

                    "entity_text":
                        entity_text,
                    "relation_id":
                        relation_id,
                    "role":
                        role,
                    "relation_type":
                        proposed.get("relation_type"),
                    "page_number":
                        proposed.get("page_number"),
                },

                "reason":
                    (
                        "Création B entièrement spécifiée après adjudication."
                    ),
            }

    # --------------------------------------------------------
    # Explicit RELINK
    # --------------------------------------------------------

    if action in {
        "RELINK",
        "RELINK_EXISTING_ENTITY",
    }:
        old_endpoint = first_nonempty(
            proposed.get(
                "old_endpoint"
            ),
            proposed.get(
                "missing_endpoint"
            ),
        )

        new_entity_id = first_nonempty(
            proposed.get(
                "new_entity_id"
            ),
            proposed.get(
                "existing_entity_id"
            ),
        )

        if (
            old_endpoint
            and new_entity_id
        ):
            return {
                "status":
                    "ACTIONABLE",

                "action":
                    "RELINK",

                "parameters": {
                    "old_endpoint":
                        old_endpoint,

                    "new_entity_id":
                        new_entity_id,
                },

                "reason":
                    (
                        "RELINK B entièrement spécifié après adjudication."
                    ),
            }

    # --------------------------------------------------------
    # REFINE_ENTITY_SPAN
    # --------------------------------------------------------

    if action == "REFINE_ENTITY_SPAN":
        return {
            "status":
                "NO_ACTION",

            "action":
                "NONE",

            "parameters":
                {},

            "reason":
                (
                    "Le span clinique exact n'est pas explicitement "
                    "résolu par l'adjudication. Création interdite."
                ),
        }

    return {
        "status":
            "NO_ACTION",

        "action":
            "NONE",

        "parameters":
            {},

        "reason":
            (
                "Le consensus B ne contient pas assez de paramètres "
                "pour une correction automatique."
            ),
    }


# ============================================================
# 5. FAMILY C
# ============================================================

def resolve_c(case):
    proposed = metadata_of(
        case
    )

    action = proposed.get(
        "action"
    )

    # --------------------------------------------------------
    # REMOVE
    # --------------------------------------------------------

    if action == "REMOVE_REIFIED_ENTITY":
        entity_id = proposed.get(
            "entity_id"
        )

        if entity_id:
            return {
                "status":
                    "ACTIONABLE",

                "action":
                    "REMOVE_REIFIED_ENTITY",

                "parameters": {
                    "entity_id":
                        entity_id,
                },

                "reason":
                    (
                        "Suppression C explicitement soutenue par "
                        "le consensus structurel."
                    ),
            }

    # --------------------------------------------------------
    # MERGE
    # --------------------------------------------------------

    if action == "MERGE":
        source_id = proposed.get(
            "source_entity_id"
        )

        target_id = proposed.get(
            "target_entity_id"
        )

        if (
            source_id
            and target_id
            and str(
                source_id
            )
            != str(
                target_id
            )
        ):
            return {
                "status":
                    "ACTIONABLE",

                "action":
                    "MERGE",

                "parameters": {
                    "source_entity_id":
                        source_id,

                    "target_entity_id":
                        target_id,
                },

                "reason":
                    (
                        "MERGE C entièrement spécifié."
                    ),
            }

    return {
        "status":
            "NO_ACTION",

        "action":
            "NONE",

        "parameters":
            {},

        "reason":
            (
                "Aucune action C destructive suffisamment spécifiée."
            ),
    }


# ============================================================
# 6. FAMILY D
# ============================================================

def resolve_d(case):
    ontology = vote_proposal(
        case,
        "ONTOLOGY_STRUCTURE",
    )

    proposed = metadata_of(
        case
    )

    action = first_nonempty(
        proposed.get(
            "action"
        ),
        ontology.get(
            "action"
        ),
    )

    # --------------------------------------------------------
    # RETYPE
    # --------------------------------------------------------

    if action == "RETYPE_ENTITY":
        entity_id = first_nonempty(
            proposed.get(
                "entity_id"
            ),
            ontology.get(
                "entity_id"
            ),
        )

        new_type = first_nonempty(
            proposed.get(
                "new_type"
            ),
            proposed.get(
                "expected_type"
            ),
            ontology.get(
                "new_type"
            ),
        )

        if (
            entity_id
            and new_type
        ):
            return {
                "status":
                    "ACTIONABLE",

                "action":
                    "RETYPE_ENTITY",

                "parameters": {
                    "entity_id":
                        entity_id,

                    "new_type":
                        new_type,
                },

                "reason":
                    (
                        "RETYPE D explicitement reconstruit "
                        "à partir du vote ontologique."
                    ),
            }

    # --------------------------------------------------------
    # RELINK
    # --------------------------------------------------------

    if action == "RELINK":
        old_endpoint = first_nonempty(
            proposed.get(
                "old_endpoint"
            ),
            proposed.get(
                "entity_id"
            ),
        )

        new_entity_id = proposed.get(
            "new_entity_id"
        )

        relation_id = proposed.get(
            "relation_id"
        )

        if (
            old_endpoint
            and new_entity_id
        ):
            return {
                "status":
                    "ACTIONABLE",

                "action":
                    "RELINK",

                "parameters": {
                    "old_endpoint":
                        old_endpoint,

                    "new_entity_id":
                        new_entity_id,

                    "relation_id":
                        relation_id,
                },

                "reason":
                    (
                        "RELINK D entièrement spécifié."
                    ),
            }

    # --------------------------------------------------------
    # REMOVE RELATION
    # --------------------------------------------------------

    if action == "REMOVE_INVALID_RELATION":
        relation_id = proposed.get(
            "relation_id"
        )

        if relation_id:
            return {
                "status":
                    "ACTIONABLE",

                "action":
                    "REMOVE_INVALID_RELATION",

                "parameters": {
                    "relation_id":
                        relation_id,
                },

                "reason":
                    (
                        "Relation D explicitement identifiée comme "
                        "actionnable après consensus."
                    ),
            }

    return {
        "status":
            "NO_ACTION",

        "action":
            "NONE",

        "parameters":
            {},

        "reason":
            (
                "Le cas D est classifié mais aucune action complète "
                "n'est reconstruite."
            ),
    }


# ============================================================
# 7. PATIENT / REFERENCE
# ============================================================

def resolve_patient_reference(
    case,
):
    clinical = vote_proposal(
        case,
        "CLINICAL_COHERENCE",
    )

    ontology = vote_proposal(
        case,
        "ONTOLOGY_STRUCTURE",
    )

    action = first_nonempty(
        clinical.get(
            "action"
        ),
        ontology.get(
            "action"
        ),
    )

    # KEEP is safe and non-destructive.
    if action == "KEEP":
        return {
            "status":
                "ACTIONABLE",

            "action":
                "KEEP",

            "parameters":
                {},

            "reason":
                (
                    "Consensus patient : conservation explicite."
                ),
        }

    # REFERENCE is a classification, NOT a delete operation.
    if action == "CLASSIFY_REFERENCE":
        return {
            "status":
                "CLASSIFICATION_ONLY",

            "action":
                "CLASSIFY_REFERENCE",

            "parameters":
                {},

            "reason":
                (
                    "Contenu référentiel identifié, mais aucune "
                    "suppression automatique n'est autorisée."
                ),
        }

    return {
        "status":
            "NO_ACTION",

        "action":
            "NONE",

        "parameters":
            {},

        "reason":
            (
                "Classification Patient/Référence non actionnable."
            ),
    }


# ============================================================
# 8. MASTER RESOLVER
# ============================================================

def resolve_case(case):
    status = case.get(
        "adjudication_status"
    )

    family = case.get(
        "family"
    )

    # Never act on unresolved cases.
    if status == "UNRESOLVED":
        return {
            "status":
                "PROTECTED",

            "action":
                "NONE",

            "parameters":
                {},

            "reason":
                (
                    "Cas encore UNRESOLVED après adjudication."
                ),
        }

    if family == "B":
        return resolve_b(
            case
        )

    if family == "C":
        return resolve_c(
            case
        )

    if family == "D":
        return resolve_d(
            case
        )

    if family == "PATIENT_REFERENCE":
        return resolve_patient_reference(
            case
        )

    return {
        "status":
            "PROTECTED",

        "action":
            "NONE",

        "parameters":
            {},

        "reason":
            (
                f"Famille non supportée : {family}"
            ),
    }


# ============================================================
# 9. MAIN
# ============================================================

def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Rapport adjudication introuvable : "
            f"{INPUT_FILE}"
        )

    report = load_json(
        INPUT_FILE
    )

    cases = (
        report.get(
            "cases",
            []
        )
        or []
    )

    resolved_actions = []

    for case in cases:
        result = resolve_case(
            case
        )

        resolved_actions.append({
            "family":
                case.get(
                    "family"
                ),

            "candidate_id":
                case.get(
                    "candidate_id"
                ),

            "document":
                case.get(
                    "document"
                ),

            "adjudication_status":
                case.get(
                    "adjudication_status"
                ),

            "support_vote_count":
                case.get(
                    "support_vote_count"
                ),

            "veto_vote_count":
                case.get(
                    "veto_vote_count"
                ),

            "mean_support_score":
                case.get(
                    "mean_support_score"
                ),

            **result,
        })

    status_counts = Counter(
        item.get(
            "status"
        )
        for item in resolved_actions
    )

    action_counts = Counter(
        item.get(
            "action"
        )
        for item in resolved_actions
    )

    family_actionable = Counter(
        item.get(
            "family"
        )
        for item in resolved_actions
        if item.get(
            "status"
        )
        == "ACTIONABLE"
    )

    output = {
        "resolver":
            "multiagent_action_resolver",

        "input_report":
            str(
                INPUT_FILE
            ),

        "summary": {
            "cases_received":
                len(
                    cases
                ),

            "actionable":
                status_counts.get(
                    "ACTIONABLE",
                    0,
                ),

            "classification_only":
                status_counts.get(
                    "CLASSIFICATION_ONLY",
                    0,
                ),

            "no_action":
                status_counts.get(
                    "NO_ACTION",
                    0,
                ),

            "protected":
                status_counts.get(
                    "PROTECTED",
                    0,
                ),

            "status_counts":
                dict(
                    status_counts
                ),

            "action_counts":
                dict(
                    action_counts
                ),

            "actionable_by_family":
                dict(
                    family_actionable
                ),
        },

        "resolved_actions":
            resolved_actions,
    }

    save_json(
        OUTPUT_FILE,
        output,
    )

    print("=" * 104)
    print("TRACE / SGCE - MULTI-AGENT ACTION RESOLVER")
    print("=" * 104)

    print(
        f"Cas reçus                           : "
        f"{len(cases)}"
    )

    print(
        f"ACTIONABLE                          : "
        f"{status_counts.get('ACTIONABLE', 0)}"
    )

    print(
        f"CLASSIFICATION_ONLY                 : "
        f"{status_counts.get('CLASSIFICATION_ONLY', 0)}"
    )

    print(
        f"NO_ACTION                           : "
        f"{status_counts.get('NO_ACTION', 0)}"
    )

    print(
        f"PROTECTED                           : "
        f"{status_counts.get('PROTECTED', 0)}"
    )

    print()

    print("ACTIONS RESOLUES")
    print("-" * 104)

    for action, count in (
        action_counts.most_common()
    ):
        print(
            f"{str(action):<48}: {count}"
        )

    print()

    print("ACTIONABLE PAR FAMILLE")
    print("-" * 104)

    if family_actionable:
        for family, count in (
            family_actionable.items()
        ):
            print(
                f"{family:<40}: {count}"
            )
    else:
        print(
            "Aucune action corrective entièrement spécifiée."
        )

    print()

    print(
        f"Sortie                               : "
        f"{OUTPUT_FILE}"
    )

    print()

    print(
        "Aucune donnée clinique n'a été modifiée."
    )


if __name__ == "__main__":
    main()
