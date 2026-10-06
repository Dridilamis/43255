# -*- coding: utf-8 -*-

"""
TRACE / SGCE
ONTOLOGY RELATION REVIEW VALIDATOR V2
CONSERVATIVE MULTI-EVIDENCE SAFETY GATE

Objectif
--------
Valider les décisions produites par :
    ontology_relation_review_resolver.py

Le validator traite :
    - AUDIT_TYPE_ALREADY_CORRECT
    - POSSIBLE_ENDPOINT_MISTYPING
    - POSSIBLE_RELATION_INVERSION
    - RELATION_SCHEMA_MISMATCH
    - NEGATION_SENSITIVE
    - VALID_BUT_GUIDELINE_TOO_STRICT
    - UNRESOLVED

Principes de sécurité
---------------------
1. Une violation domain/range ne suffit jamais à retyper une entité.
2. Une mention explicite du patient est protégée.
3. Une dose dans une phrase ne suffit pas à classer toute la phrase
   comme POSOLOGIE.
4. Le type actuel est protégé lorsqu'il possède un ancrage clinique
   intrinsèque fort.
5. Une inversion n'est SAFE que dans des configurations non ambiguës.
6. Les négations ne sont jamais corrigées automatiquement.
7. SAFE_NO_CHANGE signifie que le corpus est déjà correct.
8. Ce script ne modifie AUCUN JSON clinique.
"""

import json
import re

from pathlib import Path
from collections import Counter, defaultdict


# =====================================================================
# CONFIGURATION
# =====================================================================

ROOT = Path(__file__).resolve().parent
INPUT_JSON = ROOT / "outputs" / "ontology_relation_review_resolved.json"
OUTPUT_JSON = ROOT / "outputs" / "ontology_relation_review_validated.json"
OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)


# =====================================================================
# CONSTANTES
# =====================================================================

PATIENT_TERMS = {
    "patient",
    "le patient",
    "la patiente",
    "patiente",
    "le malade",
    "la malade",
    "malade",
}

NEGATION_PATTERNS = [
    r"\bpas de\b",
    r"\babsence de\b",
    r"\bsans\b",
    r"\baucun\b",
    r"\baucune\b",
    r"\bnon\b",
    r"\bnégatif\b",
    r"\bnegatif\b",
    r"\bnégative\b",
    r"\bnegative\b",
    r"\bni\b",
]


# =====================================================================
# UTILITAIRES
# =====================================================================

def norm(value):
    if value is None:
        return ""
    return str(value).strip()


def norm_lower(value):
    return norm(value).lower()


def load_json(path):
    return json.loads(
        Path(path).read_text(
            encoding="utf-8"
        )
    )


def dump_json(path, data):
    Path(path).parent.mkdir(
        parents=True,
        exist_ok=True
    )

    Path(path).write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


# =====================================================================
# NEGATION
# =====================================================================

def has_negation(text):

    text = norm_lower(text)

    if not text:
        return False

    for pattern in NEGATION_PATTERNS:

        if re.search(
            pattern,
            text,
            flags=re.IGNORECASE
        ):
            return True

    return False


# =====================================================================
# DETECTION PATIENT
# =====================================================================

def is_explicit_patient(text):

    text = norm_lower(text)

    if not text:
        return False

    if text in PATIENT_TERMS:
        return True

    # Exemple :
    # "Le patient | patient"

    pieces = [
        part.strip()
        for part in text.split("|")
        if part.strip()
    ]

    return any(
        part in PATIENT_TERMS
        for part in pieces
    )


# =====================================================================
# SUPPORT LEXICAL
# =====================================================================

def lexical_support(text, expected_type):
    """
    Retourne un support lexical approximatif entre 0 et 1.

    IMPORTANT :
    Ce score n'autorise JAMAIS à lui seul un retypage.

    Il s'agit seulement d'un signal parmi plusieurs preuves.
    """

    text = norm_lower(text)
    expected_type = norm(expected_type).upper()

    if not text or not expected_type:
        return 0.0

    # =================================================================
    # DONNEE_PATIENT
    # =================================================================

    if expected_type == "DONNEE_PATIENT":

        if is_explicit_patient(text):
            return 1.0

        return 0.0

    # =================================================================
    # SYMPTOME
    # =================================================================

    if expected_type == "SYMPTOME":

        terms = [
            "douleur",
            "dyspnée",
            "dyspnee",
            "toux",
            "fièvre",
            "fievre",
            "frisson",
            "vomissement",
            "nausée",
            "nausee",
            "diarrhée",
            "diarrhee",
            "céphalée",
            "cephalee",
            "asthénie",
            "asthenie",
            "confusion",
            "extrémités froides",
            "extremites froides",
            "extrémités chaudes",
            "extremites chaudes",
            "souffle",
        ]

        if any(
            term in text
            for term in terms
        ):
            return 0.90

        return 0.0

    # =================================================================
    # DEFAILLANCE_ORGANE
    # =================================================================

    if expected_type == "DEFAILLANCE_ORGANE":

        terms = [
            "défaillance",
            "defaillance",
            "dysfonction",
            "insuffisance rénale",
            "insuffisance renale",
            "insuffisance respiratoire",
            "ira",
            "choc",
            "hémodynamique",
            "hemodynamique",
            "aggravation",
            "catécholamine",
            "catecholamine",
            "catécholamines",
            "catecholamines",
        ]

        if any(
            term in text
            for term in terms
        ):
            return 0.90

        return 0.0

    # =================================================================
    # LABEL_NOSOLOGIQUE
    # =================================================================

    if expected_type == "LABEL_NOSOLOGIQUE":

        terms = [
            "sepsis",
            "choc septique",
            "infection",
            "pneumonie",
            "endocardite",
            "méningite",
            "meningite",
            "pyélonéphrite",
            "pyelonephrite",
        ]

        if any(
            term in text
            for term in terms
        ):
            return 0.80

        return 0.0

    # =================================================================
    # FOYER_INFECTIEUX
    # =================================================================

    if expected_type == "FOYER_INFECTIEUX":

        terms = [
            "foyer",
            "pulmonaire",
            "urinaire",
            "digestif",
            "cutané",
            "cutane",
            "abdominal",
            "pneumopathie",
        ]

        if any(
            term in text
            for term in terms
        ):
            return 0.70

        return 0.0

    # =================================================================
    # MICRO_ORGANISME
    # =================================================================

    if expected_type == "MICRO_ORGANISME":

        terms = [
            "staphylococcus",
            "streptococcus",
            "escherichia",
            "coli",
            "klebsiella",
            "pseudomonas",
            "enterococcus",
            "campylobacter",
            "candida",
        ]

        if any(
            term in text
            for term in terms
        ):
            return 0.90

        return 0.0

    # =================================================================
    # TRAITEMENT
    # =================================================================

    if expected_type == "TRAITEMENT":

        terms = [
            "antibiotique",
            "amoxicilline",
            "amikacine",
            "amiklin",
            "vancomycine",
            "ceftriaxone",
            "pipéracilline",
            "piperacilline",
            "tazocilline",
            "noradrénaline",
            "noradrenaline",
            "adrénaline",
            "adrenaline",
            "catécholamine",
            "catecholamine",
        ]

        if any(
            term in text
            for term in terms
        ):
            return 0.80

        return 0.0

    # =================================================================
    # POSOLOGIE
    # =================================================================

    if expected_type == "POSOLOGIE":

        # -------------------------------------------------------------
        # Détection d'une information de dose
        # -------------------------------------------------------------

        dosage_patterns = [
            r"\b\d+(?:[.,]\d+)?\s*(?:mg|g|µg|mcg)\b",
            r"\b\d+(?:[.,]\d+)?\s*(?:mg|g|µg|mcg)\s*/\s*(?:kg|h|j)\b",
            r"\b\d+(?:[.,]\d+)?\s*ml\b",
            r"\bx\s*\d+\s*/\s*j\b",
            r"\b\d+\s*fois\s+par\s+jour\b",
        ]

        has_dose = any(
            re.search(
                pattern,
                text,
                flags=re.IGNORECASE
            )
            for pattern in dosage_patterns
        )

        if not has_dose:
            return 0.0

        # -------------------------------------------------------------
        # Protection :
        # une dose incluse dans une description de défaillance
        # ne transforme pas toute l'entité en POSOLOGIE.
        #
        # Exemple réel :
        #
        # "aggravation nécessitant une réaugmentation des
        # catécholamines jusqu'à 3 mg/h"
        #
        # Il existe bien "3 mg/h", mais l'entité décrit
        # principalement une aggravation hémodynamique.
        # -------------------------------------------------------------

        competing_clinical_terms = [
            "aggravation",
            "défaillance",
            "defaillance",
            "dysfonction",
            "hémodynamique",
            "hemodynamique",
            "insuffisance",
            "choc",
        ]

        if any(
            term in text
            for term in competing_clinical_terms
        ):
            return 0.30

        return 0.90

    # =================================================================
    # COMORBIDITE_ANTECEDENT
    # =================================================================

    if expected_type == "COMORBIDITE_ANTECEDENT":

        terms = [
            "antécédent",
            "antecedent",
            "cirrhose",
            "diabète",
            "diabete",
            "hypertension",
            "cancer",
            "néoplasie",
            "neoplasie",
        ]

        if any(
            term in text
            for term in terms
        ):
            return 0.80

        return 0.0

    # =================================================================
    # EVOLUTION_PRONOSTIC
    # =================================================================

    if expected_type == "EVOLUTION_PRONOSTIC":

        terms = [
            "amélioration",
            "amelioration",
            "aggravation",
            "évolution",
            "evolution",
            "décès",
            "deces",
            "sortie",
            "guérison",
            "guerison",
        ]

        if any(
            term in text
            for term in terms
        ):
            return 0.70

        return 0.0

    return 0.0


# =====================================================================
# SUPPORT DU TYPE ACTUEL
# =====================================================================

def current_type_intrinsic_support(
    text,
    current_type
):
    """
    Évalue si le contenu de l'entité soutient son type actuel.
    """

    text = norm(text)
    current_type = norm(current_type)

    if not text or not current_type:
        return 0.0

    # -------------------------------------------------------------
    # Patient explicitement identifié
    # -------------------------------------------------------------

    if (
        current_type == "DONNEE_PATIENT"
        and is_explicit_patient(text)
    ):
        return 1.0

    return lexical_support(
        text,
        current_type
    )


# =====================================================================
# VALIDATION POSSIBLE MISTYPING
# =====================================================================

def validate_possible_mistyping(case):
    """
    Validation conservatrice d'un possible mauvais typage.

    Un retypage n'est SAFE que si :
        - le nouveau type possède un support intrinsèque très fort ;
        - le type actuel possède très peu de support ;
        - aucune règle de protection ne s'applique.

    La signature de la relation n'est jamais considérée comme une
    preuve suffisante à elle seule.
    """

    anomaly_type = norm(
        case.get("anomaly_type")
    )

    expected_type = norm(
        case.get("expected_type")
    )

    # =================================================================
    # ENDPOINT AFFECTE
    # =================================================================

    if anomaly_type == "INVALID_RELATION_SOURCE_TYPE":

        affected_id = norm(
            case.get("source_id")
        )

        affected_text = norm(
            case.get("source_text")
        )

        current_type = norm(
            case.get("source_type")
        )

        category = norm(
            case.get("source_category")
        )

        parameter = norm(
            case.get("source_parameter")
        )

        proof = norm(
            case.get("source_proof")
        )

    else:

        affected_id = norm(
            case.get("target_id")
        )

        affected_text = norm(
            case.get("target_text")
        )

        current_type = norm(
            case.get("target_type")
        )

        category = norm(
            case.get("target_category")
        )

        parameter = norm(
            case.get("target_parameter")
        )

        proof = norm(
            case.get("target_proof")
        )

    # =================================================================
    # PROTECTION 1 : PATIENT
    # =================================================================

    if (
        current_type == "DONNEE_PATIENT"
        and is_explicit_patient(
            affected_text
        )
    ):

        return {
            "final_status":
                "PROTECTED_ENDPOINT",

            "final_action":
                "NONE",

            "validator_confidence":
                0.99,

            "validator_reason":
                (
                    "L'entité est une mention explicite du patient "
                    "et son type DONNEE_PATIENT est fortement ancré. "
                    "Le retypage proposé est refusé."
                ),

            "affected_entity_id":
                affected_id,

            "current_type":
                current_type,

            "proposed_new_type":
                expected_type,

            "expected_support":
                0.0,

            "current_support":
                1.0,
        }

    # =================================================================
    # CONSTRUCTION DES PREUVES INTRINSEQUES
    # =================================================================

    evidence_text = " | ".join(
        value
        for value in [
            affected_text,
            parameter,
            proof
        ]
        if value
    )

    expected_support = lexical_support(
        evidence_text,
        expected_type
    )

    current_support = (
        current_type_intrinsic_support(
            evidence_text,
            current_type
        )
    )

    # =================================================================
    # SUPPORT DE CATEGORIE
    # =================================================================

    category_support = 0.0

    if (
        category
        and expected_type
        and category == expected_type
    ):
        category_support = 0.80

    # =================================================================
    # PROTECTION 2 :
    # DEFAILLANCE_ORGANE -> POSOLOGIE
    #
    # Empêche le faux positif observé sur P4_E031.
    # =================================================================

    if (
        expected_type == "POSOLOGIE"
        and current_type == "DEFAILLANCE_ORGANE"
    ):

        failure_terms = [
            "aggravation",
            "défaillance",
            "defaillance",
            "dysfonction",
            "hémodynamique",
            "hemodynamique",
            "insuffisance",
            "choc",
        ]

        clinical_text = norm_lower(
            evidence_text
        )

        if any(
            term in clinical_text
            for term in failure_terms
        ):

            return {
                "final_status":
                    "PROTECTED_CURRENT_TYPE",

                "final_action":
                    "NONE",

                "validator_confidence":
                    0.99,

                "validator_reason":
                    (
                        "La présence d'une dose dans la mention ne "
                        "suffit pas à définir une POSOLOGIE. "
                        "Le contenu décrit intrinsèquement une "
                        "défaillance ou dysfonction clinique. "
                        "Le type DEFAILLANCE_ORGANE est protégé."
                    ),

                "affected_entity_id":
                    affected_id,

                "current_type":
                    current_type,

                "proposed_new_type":
                    expected_type,

                "expected_support":
                    expected_support,

                "current_support":
                    max(
                        current_support,
                        0.99
                    ),
            }

    # =================================================================
    # PROTECTION 3 :
    # TYPE ACTUEL FORTEMENT SOUTENU
    # =================================================================

    if (
        current_support >= 0.90
        and current_support > expected_support
    ):

        return {
            "final_status":
                "PROTECTED_CURRENT_TYPE",

            "final_action":
                "NONE",

            "validator_confidence":
                0.95,

            "validator_reason":
                (
                    "Le contenu intrinsèque de l'entité soutient "
                    "fortement son type actuel. Une incompatibilité "
                    "avec la signature de la relation ne suffit pas "
                    "à autoriser son retypage."
                ),

            "affected_entity_id":
                affected_id,

            "current_type":
                current_type,

            "proposed_new_type":
                expected_type,

            "expected_support":
                expected_support,

            "current_support":
                current_support,
        }

    # =================================================================
    # CALCUL SUPPORT NOUVEAU TYPE
    # =================================================================

    strong_expected = max(
        expected_support,
        category_support
    )

    # =================================================================
    # SAFE RETYPE
    # =================================================================

    if (
        expected_type
        and current_type
        and expected_type != current_type
        and strong_expected >= 0.90
        and current_support <= 0.20
    ):

        return {
            "final_status":
                "SAFE_RETYPE",

            "final_action":
                "RETYPE_ENTITY",

            "validator_confidence":
                0.95,

            "validator_reason":
                (
                    "Le nouveau type possède un support intrinsèque "
                    "fort et indépendant de la relation, tandis que "
                    "le type actuel n'est pas soutenu. Le retypage "
                    "peut être proposé comme correction SAFE."
                ),

            "affected_entity_id":
                affected_id,

            "current_type":
                current_type,

            "proposed_new_type":
                expected_type,

            "expected_support":
                strong_expected,

            "current_support":
                current_support,
        }

    # =================================================================
    # REVIEW
    # =================================================================

    return {
        "final_status":
            "REVIEW_ENTITY_TYPE",

        "final_action":
            "NONE",

        "validator_confidence":
            0.60,

        "validator_reason":
            (
                "Les preuves intrinsèques sont insuffisantes pour "
                "autoriser un retypage sûr. La violation de signature "
                "de relation ne suffit pas à elle seule."
            ),

        "affected_entity_id":
            affected_id,

        "current_type":
            current_type,

        "proposed_new_type":
            expected_type,

        "expected_support":
            strong_expected,

        "current_support":
            current_support,
    }


# =====================================================================
# VALIDATION INVERSION
# =====================================================================

def validate_inversion(case):
    """
    Valide une inversion uniquement pour les relations dont
    l'orientation est non ambiguë à partir des endpoints.
    """

    relation_name = norm(
        case.get("relation_name")
    )

    source_type = norm(
        case.get("source_type")
    )

    target_type = norm(
        case.get("target_type")
    )

    source_text = norm(
        case.get("source_text")
    )

    target_text = norm(
        case.get("target_text")
    )

    proof = norm(
        case.get("relation_proof")
    )

    # =================================================================
    # NEGATION
    # =================================================================

    if (
        has_negation(proof)
        or case.get("source_negated") is True
        or case.get("target_negated") is True
    ):

        return {
            "final_status":
                "REVIEW_NEGATION",

            "final_action":
                "NONE",

            "validator_confidence":
                0.99,

            "validator_reason":
                (
                    "Une négation est associée à la relation "
                    "ou à l'un de ses endpoints. "
                    "L'inversion automatique est interdite."
                ),
        }

    # =================================================================
    # PRESENTE_SYMPTOME
    #
    # incorrect :
    # SYMPTOME -> PATIENT
    #
    # attendu :
    # PATIENT -> SYMPTOME
    # =================================================================

    if (
        relation_name == "presente_symptome"
        and source_type == "SYMPTOME"
        and target_type == "DONNEE_PATIENT"
        and is_explicit_patient(target_text)
        and not is_explicit_patient(source_text)
    ):

        return {
            "final_status":
                "SAFE_INVERT",

            "final_action":
                "INVERT_RELATION",

            "validator_confidence":
                0.99,

            "validator_reason":
                (
                    "La relation presente_symptome est orientée "
                    "SYMPTOME -> DONNEE_PATIENT. Les endpoints "
                    "identifient explicitement le symptôme et le "
                    "patient. L'orientation patient -> symptôme "
                    "est structurellement non ambiguë."
                ),
        }

    # =================================================================
    # PRESENTE_DYSFONCTION_ORGANE
    # =================================================================

    if (
        relation_name == "presente_dysfonction_organe"
        and source_type == "DEFAILLANCE_ORGANE"
        and target_type == "DONNEE_PATIENT"
        and is_explicit_patient(target_text)
        and not is_explicit_patient(source_text)
    ):

        return {
            "final_status":
                "SAFE_INVERT",

            "final_action":
                "INVERT_RELATION",

            "validator_confidence":
                0.99,

            "validator_reason":
                (
                    "La relation presente_dysfonction_organe est "
                    "orientée DEFAILLANCE_ORGANE -> DONNEE_PATIENT. "
                    "Les endpoints permettent de confirmer "
                    "l'orientation patient -> défaillance."
                ),
        }

    # =================================================================
    # A_POUR_LABEL_NOSOLOGIQUE
    # =================================================================

    if (
        relation_name == "a_pour_label_nosologique"
        and source_type == "LABEL_NOSOLOGIQUE"
        and target_type == "DONNEE_PATIENT"
        and is_explicit_patient(target_text)
        and not is_explicit_patient(source_text)
    ):

        return {
            "final_status":
                "SAFE_INVERT",

            "final_action":
                "INVERT_RELATION",

            "validator_confidence":
                0.99,

            "validator_reason":
                (
                    "La relation a_pour_label_nosologique possède "
                    "des endpoints permettant de confirmer une "
                    "orientation inverse patient -> label."
                ),
        }

    # =================================================================
    # REVIEW
    # =================================================================

    return {
        "final_status":
            "REVIEW_POSSIBLE_INVERSION",

        "final_action":
            "NONE",

        "validator_confidence":
            0.70,

        "validator_reason":
            (
                "Une inversion est plausible mais les preuves "
                "disponibles ne permettent pas de l'autoriser "
                "automatiquement."
            ),
    }


# =====================================================================
# VALIDATION PRINCIPALE
# =====================================================================

def validate_case(case):

    resolution = norm(
        case.get("resolution")
    )

    # =================================================================
    # 1. AUDIT TYPE ALREADY CORRECT
    # =================================================================

    if resolution == "AUDIT_TYPE_ALREADY_CORRECT":

        anomaly_type = norm(
            case.get("anomaly_type")
        )

        expected = norm(
            case.get("expected_type")
        )

        if anomaly_type == "INVALID_RELATION_SOURCE_TYPE":

            actual = norm(
                case.get("source_type")
            )

        else:

            actual = norm(
                case.get("target_type")
            )

        if (
            actual
            and expected
            and actual == expected
        ):

            return {
                "final_status":
                    "SAFE_NO_CHANGE",

                "final_action":
                    "NONE",

                "validator_confidence":
                    0.99,

                "validator_reason":
                    (
                        "Le type ontologique final présent dans le "
                        "JSON clinique correspond déjà au type attendu. "
                        "Aucune correction clinique n'est nécessaire."
                    ),
            }

        return {
            "final_status":
                "REVIEW_AUDIT",

            "final_action":
                "NONE",

            "validator_confidence":
                0.50,

            "validator_reason":
                (
                    "Le validator n'a pas pu confirmer que le "
                    "type actuel correspond au type attendu."
                ),
        }

    # =================================================================
    # 2. POSSIBLE ENDPOINT MISTYPING
    # =================================================================

    if resolution == "POSSIBLE_ENDPOINT_MISTYPING":

        return validate_possible_mistyping(
            case
        )

    # =================================================================
    # 3. POSSIBLE RELATION INVERSION
    # =================================================================

    if resolution == "POSSIBLE_RELATION_INVERSION":

        return validate_inversion(
            case
        )

    # =================================================================
    # 4. NEGATION
    # =================================================================

    if resolution == "NEGATION_SENSITIVE":

        return {
            "final_status":
                "REVIEW_NEGATION",

            "final_action":
                "NONE",

            "validator_confidence":
                0.99,

            "validator_reason":
                (
                    "Le cas contient un signal de négation. "
                    "Aucune correction automatique n'est autorisée."
                ),
        }

    # =================================================================
    # 5. RELATION SCHEMA MISMATCH
    # =================================================================

    if resolution == "RELATION_SCHEMA_MISMATCH":

        return {
            "final_status":
                "REVIEW_RELATION_SCHEMA",

            "final_action":
                "NONE",

            "validator_confidence":
                0.95,

            "validator_reason":
                (
                    "Les endpoints semblent intrinsèquement bien "
                    "typés. Le conflit concerne la relation ou sa "
                    "signature ontologique. Aucun retypage automatique."
                ),
        }

    # =================================================================
    # 6. GUIDELINE
    # =================================================================

    if resolution == "VALID_BUT_GUIDELINE_TOO_STRICT":

        return {
            "final_status":
                "REVIEW_GUIDELINE",

            "final_action":
                "NONE",

            "validator_confidence":
                0.70,

            "validator_reason":
                (
                    "Le cas nécessite une revue du schéma ou du "
                    "guideline. Aucune modification clinique "
                    "automatique n'est autorisée."
                ),
        }

    # =================================================================
    # 7. UNRESOLVED / FALLBACK
    # =================================================================

    return {
        "final_status":
            "REVIEW",

        "final_action":
            "NONE",

        "validator_confidence":
            0.0,

        "validator_reason":
            (
                "Le cas n'entre dans aucune règle de validation "
                "suffisamment sûre."
            ),
    }


# =====================================================================
# MAIN
# =====================================================================

def main():

    print("=" * 120)

    print(
        "TRACE / SGCE - "
        "ONTOLOGY RELATION REVIEW VALIDATOR V2 "
        "- CONSERVATIVE MULTI-EVIDENCE SAFETY GATE"
    )

    print("=" * 120)

    # =================================================================
    # ENTREE
    # =================================================================

    if not INPUT_JSON.exists():

        raise RuntimeError(
            f"Entrée introuvable : {INPUT_JSON}"
        )

    data = load_json(
        INPUT_JSON
    )

    cases = data.get(
        "resolved_reviews",
        []
    )

    print(
        f"Cas reçus                           : "
        f"{len(cases)}"
    )

    # =================================================================
    # COMPTEURS
    # =================================================================

    input_counter = Counter()
    status_counter = Counter()
    action_counter = Counter()

    relation_status_counter = defaultdict(
        Counter
    )

    validated = []

    # =================================================================
    # VALIDATION
    # =================================================================

    for case in cases:

        input_resolution = norm(
            case.get("resolution")
        )

        input_counter[
            input_resolution
        ] += 1

        decision = validate_case(
            case
        )

        result = dict(
            case
        )

        result.update(
            decision
        )

        validated.append(
            result
        )

        status = norm(
            result.get("final_status")
        )

        action = norm(
            result.get("final_action")
        )

        relation = (
            norm(
                result.get("relation_name")
            )
            or "<VIDE>"
        )

        status_counter[
            status
        ] += 1

        action_counter[
            action
        ] += 1

        relation_status_counter[
            relation
        ][
            status
        ] += 1

    # =================================================================
    # EXTRACTION DES DIFFERENTES CLASSES
    # =================================================================

    safe_retypes = [
        x
        for x in validated
        if x.get("final_action")
        == "RETYPE_ENTITY"
    ]

    safe_inversions = [
        x
        for x in validated
        if x.get("final_action")
        == "INVERT_RELATION"
    ]

    safe_no_change = [
        x
        for x in validated
        if x.get("final_status")
        == "SAFE_NO_CHANGE"
    ]

    protected_current_types = [
        x
        for x in validated
        if x.get("final_status")
        == "PROTECTED_CURRENT_TYPE"
    ]

    protected_endpoints = [
        x
        for x in validated
        if x.get("final_status")
        == "PROTECTED_ENDPOINT"
    ]

    reviews = [
        x
        for x in validated
        if x.get("final_action")
        == "NONE"
        and x.get("final_status")
        not in {
            "SAFE_NO_CHANGE",
            "PROTECTED_CURRENT_TYPE",
            "PROTECTED_ENDPOINT",
        }
    ]

    # =================================================================
    # OUTPUT
    # =================================================================

    output = {

        "validator":
            "ontology_relation_review_validator",

        "version":
            "V2_CONSERVATIVE_MULTI_EVIDENCE",

        "input":
            str(INPUT_JSON),

        "summary": {

            "cases_received":
                len(cases),

            "input_resolution_counts":
                dict(input_counter),

            "final_status_counts":
                dict(status_counter),

            "final_action_counts":
                dict(action_counter),

            "safe_no_change_count":
                len(safe_no_change),

            "safe_retype_count":
                len(safe_retypes),

            "safe_inversion_count":
                len(safe_inversions),

            "protected_current_type_count":
                len(protected_current_types),

            "protected_endpoint_count":
                len(protected_endpoints),

            "review_count":
                len(reviews),
        },

        "validated_reviews":
            validated,

        "safe_no_change":
            safe_no_change,

        "safe_retypes":
            safe_retypes,

        "safe_inversions":
            safe_inversions,

        "protected_current_types":
            protected_current_types,

        "protected_endpoints":
            protected_endpoints,

        "reviews":
            reviews,
    }

    dump_json(
        OUTPUT_JSON,
        output
    )

    # =================================================================
    # CONSOLE
    # =================================================================

    print()

    print(
        "RESOLUTIONS EN ENTREE"
    )

    print("-" * 120)

    for key, value in input_counter.most_common():

        print(
            f"{key:<60}: {value}"
        )

    # =================================================================
    # STATUTS
    # =================================================================

    print()

    print(
        "STATUTS FINAUX"
    )

    print("-" * 120)

    for key, value in status_counter.most_common():

        print(
            f"{key:<60}: {value}"
        )

    # =================================================================
    # ACTIONS
    # =================================================================

    print()

    print(
        "ACTIONS FINALES"
    )

    print("-" * 120)

    for key, value in action_counter.most_common():

        print(
            f"{key:<60}: {value}"
        )

    # =================================================================
    # RESUME SAFE
    # =================================================================

    print()

    print(
        "RESUME SAFE"
    )

    print("-" * 120)

    print(
        f"SAFE_NO_CHANGE                     : "
        f"{len(safe_no_change)}"
    )

    print(
        f"SAFE_RETYPE                        : "
        f"{len(safe_retypes)}"
    )

    print(
        f"SAFE_INVERT                        : "
        f"{len(safe_inversions)}"
    )

    print(
        f"PROTECTED_CURRENT_TYPE             : "
        f"{len(protected_current_types)}"
    )

    print(
        f"PROTECTED_ENDPOINT                 : "
        f"{len(protected_endpoints)}"
    )

    # =================================================================
    # RETYPAGES SAFE
    # =================================================================

    if safe_retypes:

        print()

        print(
            "RETYPAGES SAFE PROPOSES"
        )

        print("-" * 120)

        for x in safe_retypes:

            print(
                f"{x.get('document')} | "
                f"{x.get('affected_entity_id')} | "
                f"{x.get('current_type')} -> "
                f"{x.get('proposed_new_type')} | "
                f"confidence="
                f"{x.get('validator_confidence')}"
            )

    else:

        print()

        print(
            "RETYPAGES SAFE PROPOSES"
        )

        print("-" * 120)

        print(
            "Aucun retypage automatique autorisé."
        )

    # =================================================================
    # TYPES ACTUELS PROTEGES
    # =================================================================

    if protected_current_types:

        print()

        print(
            "TYPES ACTUELS PROTEGES"
        )

        print("-" * 120)

        for x in protected_current_types:

            print(
                f"{x.get('document')} | "
                f"{x.get('affected_entity_id')} | "
                f"{x.get('current_type')} "
                f"(retypage vers "
                f"{x.get('proposed_new_type')} refusé)"
            )

    # =================================================================
    # INVERSIONS SAFE
    # =================================================================

    if safe_inversions:

        print()

        print(
            "INVERSIONS SAFE PROPOSEES"
        )

        print("-" * 120)

        for x in safe_inversions:

            print()

            print(
                f"{x.get('document')} | "
                f"{x.get('relation_id')} | "
                f"{x.get('relation_name')}"
            )

            print(
                "  ACTUEL : "
                f"{x.get('source_text')} "
                f"[{x.get('source_type')}] "
                f"--> "
                f"{x.get('target_text')} "
                f"[{x.get('target_type')}]"
            )

            print(
                "  APRES  : "
                f"{x.get('target_text')} "
                f"[{x.get('target_type')}] "
                f"--> "
                f"{x.get('source_text')} "
                f"[{x.get('source_type')}]"
            )

    # =================================================================
    # STATUTS PAR RELATION
    # =================================================================

    print()

    print(
        "STATUTS PAR RELATION"
    )

    print("-" * 120)

    for relation in sorted(
        relation_status_counter
    ):

        counts = relation_status_counter[
            relation
        ]

        details = ", ".join(
            f"{status}={count}"
            for status, count
            in counts.most_common()
        )

        total = sum(
            counts.values()
        )

        print(
            f"{relation:<50}: "
            f"{total:<5} | "
            f"{details}"
        )

    # =================================================================
    # SORTIE
    # =================================================================

    print()

    print(
        f"Sortie                              : "
        f"{OUTPUT_JSON}"
    )

    print()

    print(
        "Aucune entité et aucune relation clinique "
        "n'ont été modifiées."
    )


# =====================================================================
# EXECUTION
# =====================================================================

if __name__ == "__main__":
    main()