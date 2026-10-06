# -*- coding: utf-8 -*-

"""
semantic_factual_third_pass_validator.py
========================================

TRACE / SGCE - SEMANTIC FACTUAL THIRD PASS VALIDATOR V1

Validation conservatrice.

SUPPORTED_AFTER_DEEP_RECHECK
    -> SAFE_KEEP

COHERENT_WITH_NEGATION
    -> SAFE_KEEP

TEMPORALLY_COMPATIBLE
    -> SAFE_KEEP

EXPLICITLY_CONTRADICTED
    -> SAFE_REMOVE_CANDIDATE
       seulement si confiance >= 0.99
       et preuve contextuelle disponible.

UNRESOLVED
    -> REVIEW

IMPORTANT :
SAFE_REMOVE_CANDIDATE n'effectue aucune suppression.
Une éventuelle correction physique devra être réalisée
par un correcteur séparé et post-validée.

Aucune donnée clinique n'est modifiée.
"""

import json

from pathlib import Path
from collections import Counter


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent
INPUT_FILE = ROOT / "outputs" / "semantic_factual_third_pass.json"
OUTPUT_FILE = ROOT / "outputs" / "semantic_factual_third_pass_validated.json"

# ============================================================
# JSON
# ============================================================

def load_json(path):

    with Path(path).open(
        "r",
        encoding="utf-8",
    ) as f:

        return json.load(f)


def save_json(path, obj):

    path = Path(path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            obj,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


# ============================================================
# VALIDATION
# ============================================================

def validate(item):

    classification = (
        item.get(
            "third_pass_classification"
        )
        or ""
    )

    confidence = float(
        item.get(
            "third_pass_confidence",
            0,
        )
        or 0
    )

    context = str(
        item.get(
            "local_context"
        )
        or item.get(
            "deep_context"
        )
        or ""
    ).strip()

    # ========================================================
    # SUPPORT RETROUVÉ
    # ========================================================

    if (
        classification
        == "SUPPORTED_AFTER_DEEP_RECHECK"
        and confidence >= 0.95
    ):

        return {
            "third_pass_final_status":
                "SAFE_KEEP",

            "third_pass_final_action":
                "NONE",

            "third_pass_validator_reason":
                (
                    "Support documentaire retrouvé "
                    "après recherche approfondie."
                ),
        }

    # ========================================================
    # COHÉRENCE AVEC NÉGATION
    # ========================================================

    if (
        classification
        == "COHERENT_WITH_NEGATION"
        and confidence >= 0.90
    ):

        return {
            "third_pass_final_status":
                "SAFE_KEEP",

            "third_pass_final_action":
                "NONE",

            "third_pass_validator_reason":
                (
                    "Aucune contradiction explicite "
                    "entre la relation et la négation."
                ),
        }

    # ========================================================
    # COMPATIBILITÉ TEMPORELLE
    # ========================================================

    if (
        classification
        == "TEMPORALLY_COMPATIBLE"
        and confidence >= 0.90
    ):

        return {
            "third_pass_final_status":
                "SAFE_KEEP",

            "third_pass_final_action":
                "NONE",

            "third_pass_validator_reason":
                (
                    "Le contexte indique qu'un arrêt "
                    "ou une modification temporelle "
                    "n'invalide pas l'existence antérieure "
                    "de la relation."
                ),
        }

    # ========================================================
    # CONTRADICTION EXPLICITE
    # ========================================================

    if (
        classification
        == "EXPLICITLY_CONTRADICTED"
        and confidence >= 0.99
        and context
        and item.get(
            "negation_cue"
        ) is True
    ):

        return {
            "third_pass_final_status":
                "SAFE_REMOVE_CANDIDATE",

            "third_pass_final_action":
                "PROPOSE_REMOVE_RELATION",

            "third_pass_validator_reason":
                (
                    "Une contradiction locale explicite "
                    "avec une négation est détectée. "
                    "La relation devient candidate à une "
                    "suppression contrôlée, mais n'est "
                    "pas encore modifiée."
                ),
        }

    # ========================================================
    # CONTRADICTION NON SUFFISAMMENT PROUVÉE
    # ========================================================

    if (
        classification
        == "EXPLICITLY_CONTRADICTED"
    ):

        return {
            "third_pass_final_status":
                "REVIEW_PRIORITY",

            "third_pass_final_action":
                "NONE",

            "third_pass_validator_reason":
                (
                    "Contradiction potentielle détectée, "
                    "mais les critères de sécurité ne sont "
                    "pas tous satisfaits."
                ),
        }

    # ========================================================
    # UNRESOLVED
    # ========================================================

    if (
        classification
        == "UNRESOLVED"
    ):

        return {
            "third_pass_final_status":
                "REVIEW",

            "third_pass_final_action":
                "NONE",

            "third_pass_validator_reason":
                (
                    "Le cas reste ambigu. "
                    "Aucune modification automatique sûre."
                ),
        }

    # ========================================================
    # FALLBACK
    # ========================================================

    return {
        "third_pass_final_status":
            "REVIEW",

        "third_pass_final_action":
            "NONE",

        "third_pass_validator_reason":
            (
                "Critères insuffisants pour une "
                "décision automatique."
            ),
    }


# ============================================================
# MAIN
# ============================================================

def main():

    if not INPUT_FILE.exists():

        raise FileNotFoundError(
            f"Entrée introuvable : "
            f"{INPUT_FILE}"
        )

    payload = load_json(
        INPUT_FILE
    )

    cases = payload.get(
        "third_pass",
        [],
    )

    validated = []

    input_counts = Counter()
    status_counts = Counter()
    action_counts = Counter()

    for item in cases:

        classification = (
            item.get(
                "third_pass_classification"
            )
            or "UNKNOWN"
        )

        input_counts[
            classification
        ] += 1

        result = validate(
            item
        )

        row = {
            **item,
            **result,
        }

        validated.append(
            row
        )

        status_counts[
            result[
                "third_pass_final_status"
            ]
        ] += 1

        action_counts[
            result[
                "third_pass_final_action"
            ]
        ] += 1

    # ========================================================
    # OUTPUT
    # ========================================================

    output = {

        "validator":
            "semantic_factual_third_pass_validator",

        "mode":
            "CONSERVATIVE_EXPLICIT_CONTRADICTION_ONLY",

        "summary": {

            "cases_received":
                len(cases),

            "input_classifications":
                dict(input_counts),

            "final_status_counts":
                dict(status_counts),

            "final_action_counts":
                dict(action_counts),

            "safe_remove_candidates":
                status_counts.get(
                    "SAFE_REMOVE_CANDIDATE",
                    0,
                ),
        },

        "validated":
            validated,
    }

    save_json(
        OUTPUT_FILE,
        output,
    )

    # ========================================================
    # PRINT
    # ========================================================

    print("=" * 120)

    print(
        "TRACE / SGCE - "
        "SEMANTIC FACTUAL THIRD PASS VALIDATOR V1"
    )

    print("=" * 120)

    print(
        f"Cas reçus                           : "
        f"{len(cases)}"
    )

    print()

    print(
        "CLASSIFICATIONS THIRD PASS"
    )

    print("-" * 120)

    for key, value in (
        input_counts.most_common()
    ):

        print(
            f"{key:<60}: {value}"
        )

    print()

    print(
        "STATUTS FINAUX"
    )

    print("-" * 120)

    for key, value in (
        status_counts.most_common()
    ):

        print(
            f"{key:<60}: {value}"
        )

    print()

    print(
        "ACTIONS FINALES"
    )

    print("-" * 120)

    for key, value in (
        action_counts.most_common()
    ):

        print(
            f"{key:<60}: {value}"
        )

    print()

    print(
        f"Candidats suppression sûre          : "
        f"{status_counts.get('SAFE_REMOVE_CANDIDATE', 0)}"
    )

    print()

    print(
        f"Sortie                              : "
        f"{OUTPUT_FILE}"
    )

    print()

    print(
        "Aucune relation clinique n'a été modifiée."
    )


if __name__ == "__main__":
    main()