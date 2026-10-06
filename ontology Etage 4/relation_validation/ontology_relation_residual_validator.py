# -*- coding: utf-8 -*-

"""
TRACE / SGCE - ONTOLOGY RELATION RESIDUAL VALIDATOR V1

Validation conservatrice des décisions du classifier ontologique relationnel.

IMPORTANT
---------
- Une violation domain/range n'est PAS une preuve d'hallucination.
- Un endpoint fortement ancré n'est jamais retypé automatiquement.
- UNSUPPORTED_RELATION_CANDIDATE n'est jamais supprimé automatiquement.
- Aucune donnée clinique n'est modifiée.
"""

import json
from pathlib import Path
from collections import Counter


# =====================================================================
# CONFIGURATION
# =====================================================================

ROOT = Path(__file__).resolve().parent
INPUT_FILE = ROOT / "outputs" / "ontology_relation_residual_decisions.json"
OUTPUT_FILE = ROOT / "outputs" / "ontology_relation_residual_validated.json"
OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)


# =====================================================================
# IO
# =====================================================================

def load_json(path):
    return json.loads(
        Path(path).read_text(encoding="utf-8")
    )


def dump_json(path, obj):
    Path(path).write_text(
        json.dumps(
            obj,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


def clean(value):
    if value is None:
        return ""
    return str(value).strip()


# =====================================================================
# VALIDATION
# =====================================================================

def validate(x):

    classification = clean(
        x.get("classification")
    )

    proposed_action = clean(
        x.get("proposed_action")
    )

    confidence = float(
        x.get("confidence") or 0.0
    )

    relation_resolution = clean(
        x.get("relation_resolution")
    )

    source_resolution = clean(
        x.get("source_resolution")
    )

    target_resolution = clean(
        x.get("target_resolution")
    )

    # -----------------------------------------------------------------
    # Garde de résolution
    # -----------------------------------------------------------------

    exact_resolution = (
        relation_resolution == "ID_EXACT"
        and source_resolution == "ID_EXACT"
        and target_resolution == "ID_EXACT"
    )

    if not exact_resolution:
        return {
            "final_status": "REVIEW",
            "final_action": "NONE",
            "validator_confidence": 0.0,
            "validator_reason":
                "Relation ou endpoint non résolu exactement."
        }

    # -----------------------------------------------------------------
    # 1. Endpoint fortement ancré
    # -----------------------------------------------------------------

    if classification == "ENDPOINT_TYPE_STRONGLY_GROUNDED":

        if (
            proposed_action == "REVIEW_RELATION"
            and confidence >= 0.95
        ):
            return {
                "final_status": "PROTECTED_ENDPOINT_REVIEW_RELATION",
                "final_action": "NONE",
                "validator_confidence": confidence,
                "validator_reason":
                    "Le type actuel de l'endpoint est fortement "
                    "ancré. Aucun retypage n'est autorisé. "
                    "La relation doit être examinée séparément."
            }

        return {
            "final_status": "REVIEW",
            "final_action": "NONE",
            "validator_confidence": confidence,
            "validator_reason":
                "Endpoint potentiellement ancré mais niveau de "
                "confiance insuffisant pour le protéger automatiquement."
        }

    # -----------------------------------------------------------------
    # 2. Erreur possible du type d'entité
    # -----------------------------------------------------------------

    if classification == "POSSIBLE_ENTITY_TYPE_ERROR":

        return {
            "final_status": "REVIEW_ENTITY_TYPE",
            "final_action": "NONE",
            "validator_confidence": confidence,
            "validator_reason":
                "Le type d'entité est potentiellement incorrect, "
                "mais une violation domain/range ne suffit pas pour "
                "autoriser un retypage."
        }

    # -----------------------------------------------------------------
    # 3. Erreur possible de relation
    # -----------------------------------------------------------------

    if classification == "RELATION_TYPE_ERROR_CANDIDATE":

        return {
            "final_status": "REVIEW_RELATION_TYPE",
            "final_action": "NONE",
            "validator_confidence": confidence,
            "validator_reason":
                "Les endpoints paraissent mieux soutenus que la "
                "relation actuelle. Une analyse contextuelle de la "
                "relation est nécessaire."
        }

    # -----------------------------------------------------------------
    # 4. Relation non soutenue par le premier classifier
    # -----------------------------------------------------------------

    if classification == "UNSUPPORTED_RELATION_CANDIDATE":

        return {
            "final_status": "DEEP_REVIEW",
            "final_action": "NONE",
            "validator_confidence": confidence,
            "validator_reason":
                "L'absence de support lexical local n'est pas une "
                "preuve suffisante d'hallucination. Une recherche "
                "contextuelle documentaire est obligatoire."
        }

    # -----------------------------------------------------------------
    # 5. Ambigu
    # -----------------------------------------------------------------

    if classification == "AMBIGUOUS":

        return {
            "final_status": "REVIEW",
            "final_action": "NONE",
            "validator_confidence": confidence,
            "validator_reason":
                "Preuves insuffisantes pour déterminer si le conflit "
                "provient de l'entité, de la relation ou du schéma."
        }

    # -----------------------------------------------------------------
    # 6. Non résolu
    # -----------------------------------------------------------------

    if classification == "UNRESOLVED":

        return {
            "final_status": "REVIEW",
            "final_action": "NONE",
            "validator_confidence": 0.0,
            "validator_reason":
                "Cas non résolu par le classifier."
        }

    # -----------------------------------------------------------------
    # Fallback
    # -----------------------------------------------------------------

    return {
        "final_status": "REVIEW",
        "final_action": "NONE",
        "validator_confidence": confidence,
        "validator_reason":
            "Classification non reconnue ou insuffisante pour "
            "une action automatique."
    }


# =====================================================================
# MAIN
# =====================================================================

def main():

    print("=" * 120)
    print(
        "TRACE / SGCE - ONTOLOGY RELATION RESIDUAL "
        "VALIDATOR V1 - CONSERVATIVE SAFETY GATE"
    )
    print("=" * 120)

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Fichier introuvable : {INPUT_FILE}"
        )

    data = load_json(INPUT_FILE)

    decisions = data.get(
        "decisions",
        []
    )

    validated = []

    status_counter = Counter()
    action_counter = Counter()
    classification_counter = Counter()
    relation_counter = Counter()

    for x in decisions:

        result = validate(x)

        y = {
            **x,
            **result
        }

        validated.append(y)

        status_counter[
            result["final_status"]
        ] += 1

        action_counter[
            result["final_action"]
        ] += 1

        classification_counter[
            clean(x.get("classification")) or "<UNKNOWN>"
        ] += 1

        relation_counter[
            clean(x.get("relation_name")) or "<UNKNOWN>"
        ] += 1

    output = {
        "validator":
            "ontology_relation_residual_validator",

        "version":
            "V1_CONSERVATIVE_SAFETY_GATE",

        "input":
            str(INPUT_FILE),

        "summary": {
            "decisions_received":
                len(decisions),

            "final_status_counts":
                dict(status_counter),

            "final_action_counts":
                dict(action_counter),

            "classification_counts":
                dict(classification_counter),
        },

        "validated_decisions":
            validated
    }

    dump_json(
        OUTPUT_FILE,
        output
    )

    # -------------------------------------------------------------
    # AFFICHAGE
    # -------------------------------------------------------------

    print(
        f"Décisions reçues                    : {len(decisions)}"
    )

    print()
    print("CLASSIFICATIONS EN ENTREE")
    print("-" * 120)

    for k, v in classification_counter.most_common():
        print(f"{k:<60}: {v}")

    print()
    print("STATUTS FINAUX")
    print("-" * 120)

    for k, v in status_counter.most_common():
        print(f"{k:<60}: {v}")

    print()
    print("ACTIONS FINALES")
    print("-" * 120)

    for k, v in action_counter.most_common():
        print(f"{k:<60}: {v}")

    protected = status_counter.get(
        "PROTECTED_ENDPOINT_REVIEW_RELATION",
        0
    )

    deep_review = status_counter.get(
        "DEEP_REVIEW",
        0
    )

    relation_review = status_counter.get(
        "REVIEW_RELATION_TYPE",
        0
    )

    entity_review = status_counter.get(
        "REVIEW_ENTITY_TYPE",
        0
    )

    print()
    print("RESUME")
    print("-" * 120)

    print(
        f"Endpoints protégés                  : {protected}"
    )

    print(
        f"Relations en deep review            : {deep_review}"
    )

    print(
        f"Types de relation à revoir          : {relation_review}"
    )

    print(
        f"Types d'entité à revoir             : {entity_review}"
    )

    print()
    print(
        f"Sortie                              : {OUTPUT_FILE}"
    )

    print()
    print(
        "Aucune entité et aucune relation clinique "
        "n'ont été modifiées."
    )


if __name__ == "__main__":
    main()