# -*- coding: utf-8 -*-

"""
TRACE / SGCE - ONTOLOGY RELATION FINAL VALIDATOR V1
CONSERVATIVE RELATION SAFETY GATE

Entrée :
    ontology_relation_deep_review.json

Objectif :
    Valider les propositions issues du deep reviewer avant toute
    modification des relations cliniques.

Principe :
    Une incompatibilité domain/range ne suffit PAS à supprimer
    automatiquement une relation.

Sorties possibles :
    SAFE_REMOVE
    SAFE_KEEP
    REVIEW
    REVIEW_NEGATION
    REVIEW_POSSIBLE_INVERSION

Actions :
    REMOVE_RELATION
    NONE

IMPORTANT :
    Ce script ne modifie aucune donnée clinique.
"""

import json
import re
import unicodedata

from pathlib import Path
from collections import Counter, defaultdict


# ======================================================================
# CONFIGURATION
# ======================================================================

ROOT = Path(__file__).resolve().parent
INPUT_FILE = ROOT / "outputs" / "ontology_relation_deep_review.json"
OUTPUT_FILE = ROOT / "outputs" / "ontology_relation_final_validated.json"
OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)


# ======================================================================
# I/O
# ======================================================================

def load_json(path):

    return json.loads(
        Path(path).read_text(
            encoding="utf-8"
        )
    )


def dump_json(path, obj):

    Path(path).parent.mkdir(
        parents=True,
        exist_ok=True
    )

    Path(path).write_text(
        json.dumps(
            obj,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


# ======================================================================
# NORMALISATION
# ======================================================================

def normalize(value):

    if value is None:
        return ""

    value = str(value)

    value = unicodedata.normalize(
        "NFKD",
        value
    )

    value = "".join(
        c for c in value
        if not unicodedata.combining(c)
    )

    value = value.lower()
    value = value.replace("_", " ")

    value = re.sub(
        r"[^\w\s%/+.-]",
        " ",
        value
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


# ======================================================================
# REGLES SEMANTIQUES FORTES
# ======================================================================

PATIENT_TERMS = {
    "patient",
    "patiente",
    "le patient",
    "la patiente",
    "ce patient",
    "cette patiente"
}


def is_patient_text(value):

    n = normalize(value)

    return n in PATIENT_TERMS


def is_same_type(a, b):

    return (
        normalize(a)
        == normalize(b)
    )


# ======================================================================
# DETECTION DE POSSIBLE INVERSION
# ======================================================================

def possible_relation_inversion(case):
    """
    Détecte uniquement les cas où l'anomalie ressemble fortement
    à une inversion sujet/objet.

    ATTENTION :
    Cette fonction ne corrige PAS la relation.
    Elle envoie le cas en REVIEW_POSSIBLE_INVERSION.
    """

    relation = case.get(
        "relation_name",
        ""
    )

    source_type = case.get(
        "source_real_type"
    ) or case.get(
        "source_type",
        ""
    )

    target_type = case.get(
        "target_real_type"
    ) or case.get(
        "target_type",
        ""
    )

    source_text = (
        case.get("source_proof")
        or case.get("source_text")
        or ""
    )

    target_text = (
        case.get("target_proof")
        or case.get("target_text")
        or ""
    )

    # --------------------------------------------------
    # presente_symptome
    #
    # Forme sémantiquement naturelle :
    #
    # patient -> presente_symptome -> symptome
    #
    # Si on trouve :
    #
    # symptome-like -> presente_symptome -> patient
    #
    # on suspecte une inversion.
    # --------------------------------------------------

    if relation == "presente_symptome":

        if (
            target_type == "DONNEE_PATIENT"
            and is_patient_text(target_text)
            and not is_patient_text(source_text)
        ):
            return True

    # --------------------------------------------------
    # presente_dysfonction_organe
    #
    # Forme attendue :
    #
    # patient -> presente_dysfonction_organe
    #         -> defaillance
    # --------------------------------------------------

    if relation == "presente_dysfonction_organe":

        if (
            target_type == "DONNEE_PATIENT"
            and is_patient_text(target_text)
            and source_type != "DONNEE_PATIENT"
        ):
            return True

    # --------------------------------------------------
    # a_pour_label_nosologique
    #
    # patient -> label
    # --------------------------------------------------

    if relation == "a_pour_label_nosologique":

        if (
            target_type == "DONNEE_PATIENT"
            and is_patient_text(target_text)
            and source_type != "DONNEE_PATIENT"
        ):
            return True

    # --------------------------------------------------
    # patient_a_pour_evolution
    # --------------------------------------------------

    if relation == "patient_a_pour_evolution":

        if (
            target_type == "DONNEE_PATIENT"
            and is_patient_text(target_text)
            and source_type != "DONNEE_PATIENT"
        ):
            return True

    return False


# ======================================================================
# VALIDATION INDIVIDUELLE
# ======================================================================

def validate_case(case):

    deep_classification = case.get(
        "deep_classification",
        ""
    )

    deep_action = case.get(
        "deep_action",
        "NONE"
    )

    source_found = (
        case.get("source_found")
        is True
    )

    target_found = (
        case.get("target_found")
        is True
    )

    relation_found = (
        case.get("relation_found")
        is True
    )

    source_match = (
        case.get("source_text_match")
        is True
    )

    target_match = (
        case.get("target_text_match")
        is True
    )

    source_negated = (
        case.get("source_negated")
        is True
    )

    target_negated = (
        case.get("target_negated")
        is True
    )

    expected_types = (
        case.get("expected_types")
        or case.get(
            "expected_types_for_affected_role"
        )
        or []
    )

    affected_role = case.get(
        "affected_role"
    )

    source_type = (
        case.get("source_real_type")
        or case.get("source_type")
    )

    target_type = (
        case.get("target_real_type")
        or case.get("target_type")
    )

    if affected_role == "SOURCE":
        affected_type = source_type

    elif affected_role == "TARGET":
        affected_type = target_type

    else:
        affected_type = None

    type_conflict_still_present = (
        bool(expected_types)
        and affected_type is not None
        and affected_type not in expected_types
    )

    # ==================================================================
    # 1. ENDPOINTS NON RESOLUS
    # ==================================================================

    if not source_found or not target_found:

        return {
            "final_status":
                "REVIEW",

            "final_action":
                "NONE",

            "final_confidence":
                0.0,

            "validator_reason":
                "Au moins un endpoint n'est pas résolu. "
                "Aucune correction automatique n'est autorisée."
        }

    # ==================================================================
    # 2. RELATION NON RESOLUE
    # ==================================================================

    if not relation_found:

        return {
            "final_status":
                "REVIEW",

            "final_action":
                "NONE",

            "final_confidence":
                0.0,

            "validator_reason":
                "La relation n'a pas été retrouvée dans le JSON clinique."
        }

    # ==================================================================
    # 3. NEGATION
    # ==================================================================

    if (
        deep_classification
        == "NEGATION_SENSITIVE_RELATION"
        or source_negated
        or target_negated
    ):

        return {
            "final_status":
                "REVIEW_NEGATION",

            "final_action":
                "NONE",

            "final_confidence":
                0.99,

            "validator_reason":
                "La relation implique un endpoint nié. "
                "La négation peut modifier l'interprétation clinique ; "
                "aucune suppression automatique n'est autorisée."
        }

    # ==================================================================
    # 4. POSSIBLE INVERSION
    # ==================================================================

    if possible_relation_inversion(case):

        return {
            "final_status":
                "REVIEW_POSSIBLE_INVERSION",

            "final_action":
                "NONE",

            "final_confidence":
                0.99,

            "validator_reason":
                "Les endpoints semblent correctement identifiés, "
                "mais leur orientation suggère une possible inversion "
                "sujet/objet. La relation ne doit pas être supprimée "
                "avant vérification."
        }

    # ==================================================================
    # 5. SUPPORT PARTIEL
    # ==================================================================

    if (
        deep_classification
        == "PARTIAL_DOCUMENT_SUPPORT"
    ):

        return {
            "final_status":
                "REVIEW",

            "final_action":
                "NONE",

            "final_confidence":
                0.75,

            "validator_reason":
                "Le support documentaire est seulement partiel. "
                "Il est insuffisant pour supprimer ou modifier "
                "automatiquement la relation."
        }

    # ==================================================================
    # 6. CONFLIT ONTOLOGIQUE CONFIRME
    # ==================================================================

    if (
        deep_classification
        == "RELATION_ONTOLOGY_CONFLICT_CONFIRMED"
    ):

        # --------------------------------------------------------------
        # sécurité : les deux endpoints doivent être textuellement
        # ancrés
        # --------------------------------------------------------------

        if not (
            source_match
            and target_match
        ):

            return {
                "final_status":
                    "REVIEW",

                "final_action":
                    "NONE",

                "final_confidence":
                    0.75,

                "validator_reason":
                    "Le conflit ontologique est détecté mais "
                    "l'ancrage documentaire des deux endpoints "
                    "n'est pas suffisamment fort."
            }

        # --------------------------------------------------------------
        # sécurité : le conflit doit toujours être présent
        # --------------------------------------------------------------

        if not type_conflict_still_present:

            return {
                "final_status":
                    "SAFE_KEEP",

                "final_action":
                    "NONE",

                "final_confidence":
                    0.99,

                "validator_reason":
                    "Après résolution des endpoints, le type affecté "
                    "n'est plus incompatible avec les types attendus. "
                    "La relation est conservée."
            }

        # --------------------------------------------------------------
        # sécurité : il faut réellement avoir une proposition
        # de suppression du deep reviewer
        # --------------------------------------------------------------

        if (
            deep_action
            != "PROPOSE_REMOVE_RELATION"
        ):

            return {
                "final_status":
                    "REVIEW",

                "final_action":
                    "NONE",

                "final_confidence":
                    0.75,

                "validator_reason":
                    "Le conflit reste présent mais le deep reviewer "
                    "n'a pas proposé explicitement la suppression."
            }

        # --------------------------------------------------------------
        # GATE FINAL
        #
        # Ici :
        # - endpoints résolus
        # - relation résolue
        # - endpoints textuellement ancrés
        # - aucune négation
        # - pas d'inversion évidente
        # - type toujours incompatible
        # - deep reviewer propose suppression
        #
        # => candidat SAFE_REMOVE
        # --------------------------------------------------------------

        return {
            "final_status":
                "SAFE_REMOVE",

            "final_action":
                "REMOVE_RELATION",

            "final_confidence":
                0.99,

            "validator_reason":
                "Les endpoints et la relation sont résolus, "
                "les deux endpoints sont documentés, aucune négation "
                "ni inversion évidente n'est détectée, et le conflit "
                "ontologique persiste malgré la protection des types "
                "d'entité. La suppression de la relation est validée."
        }

    # ==================================================================
    # 7. AUTRES CAS
    # ==================================================================

    return {
        "final_status":
            "REVIEW",

        "final_action":
            "NONE",

        "final_confidence":
            0.50,

        "validator_reason":
            "Le cas ne satisfait aucune règle de correction automatique "
            "suffisamment sûre."
    }


# ======================================================================
# MAIN
# ======================================================================

def main():

    print("=" * 120)

    print(
        "TRACE / SGCE - ONTOLOGY RELATION FINAL VALIDATOR V1 "
        "- CONSERVATIVE RELATION SAFETY GATE"
    )

    print("=" * 120)

    data = load_json(
        INPUT_FILE
    )

    cases = data.get(
        "deep_reviews",
        []
    )

    results = []

    input_counter = Counter()
    status_counter = Counter()
    action_counter = Counter()

    by_relation = defaultdict(
        Counter
    )

    # ==================================================================
    # VALIDATION
    # ==================================================================

    for case in cases:

        deep_cls = case.get(
            "deep_classification",
            "UNKNOWN"
        )

        input_counter[
            deep_cls
        ] += 1

        validation = validate_case(
            case
        )

        row = {
            **case,
            **validation
        }

        results.append(
            row
        )

        status = validation[
            "final_status"
        ]

        action = validation[
            "final_action"
        ]

        status_counter[
            status
        ] += 1

        action_counter[
            action
        ] += 1

        relation = case.get(
            "relation_name",
            "<VIDE>"
        )

        by_relation[
            relation
        ][
            status
        ] += 1

    # ==================================================================
    # SAFE REMOVE
    # ==================================================================

    safe_remove = [
        x
        for x in results
        if (
            x.get("final_status")
            == "SAFE_REMOVE"
            and x.get("final_action")
            == "REMOVE_RELATION"
        )
    ]

    # ==================================================================
    # OUTPUT
    # ==================================================================

    output = {

        "validator":
            "ontology_relation_final_validator",

        "version":
            "V1_CONSERVATIVE_RELATION_SAFETY_GATE",

        "input":
            str(INPUT_FILE),

        "summary": {

            "cases_received":
                len(cases),

            "deep_classification_counts":
                dict(
                    input_counter
                ),

            "final_status_counts":
                dict(
                    status_counter
                ),

            "final_action_counts":
                dict(
                    action_counter
                ),

            "safe_remove_count":
                len(safe_remove),
        },

        "validated_relations":
            results,

        "safe_remove_relations": [
            {
                "document":
                    x.get("document"),

                "candidate_id":
                    x.get("candidate_id"),

                "relation_id":
                    x.get("relation_id"),

                "relation_name":
                    x.get("relation_name"),

                "source_id":
                    x.get("source_id"),

                "source_text":
                    x.get("source_text"),

                "source_type":
                    (
                        x.get("source_real_type")
                        or x.get("source_type")
                    ),

                "target_id":
                    x.get("target_id"),

                "target_text":
                    x.get("target_text"),

                "target_type":
                    (
                        x.get("target_real_type")
                        or x.get("target_type")
                    ),

                "reason":
                    x.get("validator_reason"),

                "confidence":
                    x.get("final_confidence"),
            }

            for x in safe_remove
        ]
    }

    dump_json(
        OUTPUT_FILE,
        output
    )

    # ==================================================================
    # AFFICHAGE
    # ==================================================================

    print(
        f"Cas reçus                           : "
        f"{len(cases)}"
    )

    print()

    print(
        "CLASSIFICATIONS DEEP REVIEW"
    )

    print("-" * 120)

    for key, value in (
        input_counter.most_common()
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
        status_counter.most_common()
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
        action_counter.most_common()
    ):

        print(
            f"{key:<60}: {value}"
        )

    print()

    print(
        "RESULTATS PAR RELATION"
    )

    print("-" * 120)

    relation_totals = Counter(
        x.get(
            "relation_name",
            "<VIDE>"
        )
        for x in results
    )

    for relation, total in (
        relation_totals.most_common()
    ):

        details = ", ".join(
            f"{status}={count}"
            for status, count
            in by_relation[
                relation
            ].most_common()
        )

        print(
            f"{relation:<50}: "
            f"{total:<5} | "
            f"{details}"
        )

    print()

    print(
        "RESUME"
    )

    print("-" * 120)

    print(
        f"Relations SAFE_REMOVE               : "
        f"{len(safe_remove)}"
    )

    print(
        f"Relations SAFE_KEEP                 : "
        f"{status_counter.get('SAFE_KEEP', 0)}"
    )

    print(
        f"Possible inversion                  : "
        f"{status_counter.get('REVIEW_POSSIBLE_INVERSION', 0)}"
    )

    print(
        f"Review négation                     : "
        f"{status_counter.get('REVIEW_NEGATION', 0)}"
    )

    print(
        f"Autres REVIEW                       : "
        f"{status_counter.get('REVIEW', 0)}"
    )

    print()

    print(
        f"Sortie                              : "
        f"{OUTPUT_FILE}"
    )

    print()

    print(
        "Aucune entité et aucune relation clinique "
        "n'ont été modifiées."
    )


if __name__ == "__main__":
    main()