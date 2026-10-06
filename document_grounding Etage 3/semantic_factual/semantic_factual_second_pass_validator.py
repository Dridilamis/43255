# -*- coding: utf-8 -*-

"""
semantic_factual_second_pass_validator.py
=========================================

TRACE / SGCE - SEMANTIC FACTUAL SECOND PASS VALIDATOR V1

Politique conservative :

SUPPORTED_AFTER_RECHECK
    -> SAFE_KEEP

DOCUMENT_LEVEL_SUPPORT
    -> REVIEW

PARTIAL_SUPPORT
    -> REVIEW

STILL_UNSUPPORTED
    -> REVIEW

TEMPORALLY_AMBIGUOUS_NEGATION
    -> REVIEW

POTENTIAL_NEGATION_CONTRADICTION
    -> REVIEW

AMBIGUOUS_NEGATION
    -> REVIEW

AUCUNE relation n'est supprimée automatiquement
par cette étape.

Pourquoi ?

Parce que :
    absence de preuve != preuve de fausseté.

Une suppression automatique nécessitera plus tard
une contradiction textuelle explicite et validée.

Aucune donnée clinique n'est modifiée.
"""

import json

from pathlib import Path
from collections import Counter


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent
INPUT_FILE = ROOT / "outputs" / "semantic_factual_second_pass.json"
OUTPUT_FILE = ROOT / "outputs" / "semantic_factual_second_pass_validated.json"

# ============================================================
# JSON
# ============================================================

def load_json(path):

    with Path(path).open(
        "r",
        encoding="utf-8",
    ) as f:

        return json.load(f)


def save_json(
    path,
    obj,
):

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

def validate(
    item,
):

    classification = (
        item.get(
            "second_pass_classification"
        )
        or ""
    )

    confidence = float(
        item.get(
            "second_pass_confidence",
            0,
        )
        or 0
    )

    # --------------------------------------------------------
    # Support retrouvé
    # --------------------------------------------------------

    if (
        classification
        == "SUPPORTED_AFTER_RECHECK"
        and confidence >= 0.95
    ):

        return {

            "second_pass_final_status":
                "SAFE_KEEP",

            "second_pass_final_action":
                "NONE",

            "second_pass_validator_reason":
                (
                    "Les deux endpoints sont "
                    "retrouvés dans une fenêtre "
                    "textuelle locale commune "
                    "après normalisation."
                ),
        }

    # --------------------------------------------------------
    # Support document seulement
    # --------------------------------------------------------

    if (
        classification
        == "DOCUMENT_LEVEL_SUPPORT"
    ):

        return {

            "second_pass_final_status":
                "REVIEW",

            "second_pass_final_action":
                "NONE",

            "second_pass_validator_reason":
                (
                    "Les endpoints existent dans "
                    "le document mais le lien "
                    "relationnel local n'est pas "
                    "suffisamment démontré."
                ),
        }

    # --------------------------------------------------------
    # Partial support
    # --------------------------------------------------------

    if (
        classification
        == "PARTIAL_SUPPORT"
    ):

        return {

            "second_pass_final_status":
                "REVIEW",

            "second_pass_final_action":
                "NONE",

            "second_pass_validator_reason":
                (
                    "Un seul endpoint a été retrouvé. "
                    "Impossible de valider ou de "
                    "supprimer automatiquement "
                    "la relation."
                ),
        }

    # --------------------------------------------------------
    # Unsupported
    # --------------------------------------------------------

    if (
        classification
        == "STILL_UNSUPPORTED"
    ):

        return {

            "second_pass_final_status":
                "REVIEW",

            "second_pass_final_action":
                "NONE",

            "second_pass_validator_reason":
                (
                    "L'absence de support retrouvé "
                    "ne constitue pas une preuve "
                    "de fausseté."
                ),
        }

    # --------------------------------------------------------
    # Négation temporellement ambiguë
    # --------------------------------------------------------

    if (
        classification
        == "TEMPORALLY_AMBIGUOUS_NEGATION"
    ):

        return {

            "second_pass_final_status":
                "REVIEW",

            "second_pass_final_action":
                "NONE",

            "second_pass_validator_reason":
                (
                    "Le statut négatif peut représenter "
                    "un arrêt ou un changement temporel "
                    "et ne démontre pas que la relation "
                    "était toujours fausse."
                ),
        }

    # --------------------------------------------------------
    # Contradiction potentielle
    # --------------------------------------------------------

    if (
        classification
        == "POTENTIAL_NEGATION_CONTRADICTION"
    ):

        return {

            "second_pass_final_status":
                "REVIEW_PRIORITY",

            "second_pass_final_action":
                "NONE",

            "second_pass_validator_reason":
                (
                    "Contradiction potentielle avec "
                    "une négation validée. Une preuve "
                    "textuelle explicite est nécessaire "
                    "avant toute suppression."
                ),
        }

    # --------------------------------------------------------
    # Ambiguous negation
    # --------------------------------------------------------

    if classification in {
        "AMBIGUOUS_NEGATION",
        "NEGATION_STATUS_UNCLEAR",
    }:

        return {

            "second_pass_final_status":
                "REVIEW",

            "second_pass_final_action":
                "NONE",

            "second_pass_validator_reason":
                (
                    "Le statut de négation ne permet "
                    "pas une décision automatique sûre."
                ),
        }

    # --------------------------------------------------------
    # Text missing
    # --------------------------------------------------------

    if (
        classification
        == "TEXT_MISSING"
    ):

        return {

            "second_pass_final_status":
                "REVIEW",

            "second_pass_final_action":
                "NONE",

            "second_pass_validator_reason":
                (
                    "Texte source indisponible."
                ),
        }

    # --------------------------------------------------------
    # Fallback
    # --------------------------------------------------------

    return {

        "second_pass_final_status":
            "REVIEW",

        "second_pass_final_action":
            "NONE",

        "second_pass_validator_reason":
            (
                "Cas non suffisamment démontré "
                "pour une action automatique."
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
        "second_pass",
        [],
    )

    validated = []

    status_counts = Counter()

    action_counts = Counter()

    classification_counts = Counter()

    for item in cases:

        classification_counts[
            item.get(
                "second_pass_classification",
                "UNKNOWN",
            )
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
                "second_pass_final_status"
            ]
        ] += 1

        action_counts[
            result[
                "second_pass_final_action"
            ]
        ] += 1

    output = {

        "validator":
            "semantic_factual_second_pass_validator",

        "mode":
            "CONSERVATIVE_NO_AUTOMATIC_DELETION",

        "summary": {

            "cases_received":
                len(cases),

            "input_classifications":
                dict(
                    classification_counts
                ),

            "final_status_counts":
                dict(
                    status_counts
                ),

            "final_action_counts":
                dict(
                    action_counts
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
        "SEMANTIC FACTUAL SECOND PASS VALIDATOR V1"
    )

    print("=" * 120)

    print(
        f"Cas reçus                           : "
        f"{len(cases)}"
    )

    print()

    print(
        "CLASSIFICATIONS SECOND PASS"
    )

    print("-" * 120)

    for key, value in (
        classification_counts.most_common()
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
        f"Sortie                              : "
        f"{OUTPUT_FILE}"
    )

    print()

    print(
        "Aucune relation clinique n'a été modifiée."
    )


if __name__ == "__main__":
    main()
    