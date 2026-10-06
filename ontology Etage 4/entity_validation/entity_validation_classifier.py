# -*- coding: utf-8 -*-

"""
TRACE / SGCE - ENTITY VALIDATION CLASSIFIER V1

Entrée :
    MultiAgent/entity_validation/queues/
        entity_validation_candidates.json

Sortie :
    MultiAgent/entity_validation/outputs/
        entity_validation_decisions.json

OBJECTIF
--------
Classifier les violations ontologiques résiduelles sans modifier les
données cliniques.

Une violation domain/range ne signifie PAS automatiquement :
    - que l'entité doit être retypée ;
    - que la relation doit être supprimée.

Le classifier recherche plusieurs indices concordants avant de proposer
un RETYPE.

CLASSIFICATIONS
---------------
ENTITY_MISTYPING_STRONG
ENTITY_MISTYPING_POSSIBLE
RELATION_ENDPOINT_SUSPECT
RELATION_ONTOLOGY_CONFLICT
UNRESOLVED_RELATION

ACTIONS PROPOSEES
-----------------
PROPOSE_RETYPE_ENTITY
REVIEW_ENTITY_TYPE
REVIEW_ENDPOINT
REVIEW_RELATION
NONE

Aucune donnée clinique n'est modifiée.
"""

# GENERICITY PATCH: configuration via environment; no corpus-example lexicon.

import os
import json
import re
import unicodedata

from pathlib import Path
from collections import Counter, defaultdict


# =====================================================================
# CONFIGURATION
# =====================================================================

ROOT = Path(__file__).resolve().parent
INPUT_FILE = ROOT / "queues" / "entity_validation_candidates.json"
OUTPUT_DIR = ROOT / "outputs"
OUTPUT_FILE = OUTPUT_DIR / "entity_validation_decisions.json"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# =====================================================================
# SEUILS CONSERVATEURS
# =====================================================================

# Une entité doit avoir au moins ce nombre de violations cohérentes
# pour que la répétition constitue un indice fort.
MIN_CONSISTENT_VIOLATIONS = int(os.environ.get("TRACE_MIN_CONSISTENT_VIOLATIONS", "2"))

# Ratio minimum d'accord entre les types attendus.
MIN_EXPECTED_TYPE_RATIO = float(os.environ.get("TRACE_MIN_EXPECTED_TYPE_RATIO", "0.80"))


# =====================================================================
# UTILITAIRES
# =====================================================================

def load_json(path):

    path = Path(path)

    if not path.exists():

        raise FileNotFoundError(
            f"Fichier introuvable : {path}"
        )

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def dump_json(path, obj):

    path = Path(path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    path.write_text(
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


def normalize(value):

    value = clean(value)

    value = unicodedata.normalize(
        "NFKD",
        value
    )

    value = "".join(
        c
        for c in value
        if not unicodedata.combining(c)
    )

    value = value.lower()

    value = value.replace(
        "_",
        " "
    )

    value = value.replace(
        "’",
        "'"
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


def normalize_type(value):

    return clean(value).upper()


# =====================================================================
# INDICES LEXICAUX TRES CONSERVATEURS
# =====================================================================

def lexical_support(text, expected_type):
    """
    Version générique.
    Aucun vocabulaire clinique ni type TRACE-Sepsis n'est codé en dur.
    Les contraintes domain/range ne sont pas considérées comme une preuve
    sémantique indépendante suffisante pour retyper automatiquement.
    """
    return []


# =====================================================================
# CONSTRUCTION DES GROUPES D'ENTITES
# =====================================================================

def build_entity_groups(candidates):
    """
    Regroupe les anomalies portant sur la même entité physique :

        document + entity_id

    Cela permet de détecter les cas où UNE entité mal typée provoque
    plusieurs violations ontologiques.
    """

    groups = defaultdict(list)

    for candidate in candidates:

        document = clean(
            candidate.get(
                "document"
            )
        )

        entity_id = clean(
            candidate.get(
                "entity_id"
            )
        )

        if not document or not entity_id:
            continue

        groups[
            (
                document,
                entity_id
            )
        ].append(
            candidate
        )

    return groups


# =====================================================================
# ANALYSE GROUPE
# =====================================================================

def analyze_entity_group(group):
    """
    Analyse toutes les anomalies provoquées par la même entité.
    """

    expected_counter = Counter()

    current_counter = Counter()

    relation_counter = Counter()

    roles = Counter()

    for candidate in group:

        expected = normalize_type(
            candidate.get(
                "expected_type"
            )
        )

        current = normalize_type(
            candidate.get(
                "entity_type"
            )
        )

        relation = clean(
            candidate.get(
                "relation_name"
            )
        )

        role = clean(
            candidate.get(
                "role"
            )
        )

        if expected:
            expected_counter[
                expected
            ] += 1

        if current:
            current_counter[
                current
            ] += 1

        if relation:
            relation_counter[
                relation
            ] += 1

        if role:
            roles[
                role
            ] += 1

    total = len(group)

    dominant_expected = None
    dominant_count = 0

    if expected_counter:

        dominant_expected, dominant_count = (
            expected_counter.most_common(
                1
            )[0]
        )

    ratio = (
        dominant_count / total
        if total
        else 0.0
    )

    return {
        "number_of_violations":
            total,

        "expected_type_counts":
            dict(
                expected_counter
            ),

        "current_type_counts":
            dict(
                current_counter
            ),

        "relation_counts":
            dict(
                relation_counter
            ),

        "role_counts":
            dict(
                roles
            ),

        "dominant_expected_type":
            dominant_expected,

        "dominant_expected_count":
            dominant_count,

        "dominant_expected_ratio":
            round(
                ratio,
                4
            ),
    }


# =====================================================================
# VERIFICATION DE LA RESOLUTION
# =====================================================================

def relation_is_resolved(candidate):

    resolution = clean(
        candidate.get(
            "relation_resolution"
        )
    )

    return resolution in {
        "ID_EXACT",
        "ID_DUPLICATE",
        "TYPE_PLUS_PAGE",
    }


def entity_is_resolved(candidate):

    resolution = clean(
        candidate.get(
            "entity_resolution"
        )
    )

    return resolution in {
        "ID_EXACT",
        "ID_DUPLICATE_EQUIVALENT",
        "AUDIT_ID_EXACT",
        "AUDIT_ID_DUPLICATE_EQUIVALENT",
        "RELATION_TEXT_EXACT",
        "RELATION_TEXT_EXACT_PLUS_PAGE",
        "RELATION_TEXT_DUPLICATE_EQUIVALENT",
        "AUDIT_TEXT_EXACT",
        "AUDIT_TEXT_EXACT_PLUS_PAGE",
        "AUDIT_TEXT_DUPLICATE_EQUIVALENT",
    }


# =====================================================================
# CLASSIFICATION
# =====================================================================

def classify_candidate(
    candidate,
    group_analysis
):

    current_type = normalize_type(
        candidate.get(
            "entity_type"
        )
    )

    expected_type = normalize_type(
        candidate.get(
            "expected_type"
        )
    )

    text = clean(
        candidate.get(
            "entity_text"
        )
    )

    relation_resolution = clean(
        candidate.get(
            "relation_resolution"
        )
    )

    entity_resolution = clean(
        candidate.get(
            "entity_resolution"
        )
    )

    signals = lexical_support(
        text,
        expected_type
    )

    strong_lexical = any(
        signal.get(
            "strength"
        ) == "STRONG"
        for signal in signals
    )

    medium_lexical = any(
        signal.get(
            "strength"
        ) == "MEDIUM"
        for signal in signals
    )

    n_violations = (
        group_analysis.get(
            "number_of_violations",
            0
        )
    )

    dominant_expected = (
        group_analysis.get(
            "dominant_expected_type"
        )
    )

    dominant_ratio = float(
        group_analysis.get(
            "dominant_expected_ratio",
            0
        )
    )

    repeated_consistent = (
        n_violations
        >= MIN_CONSISTENT_VIOLATIONS
        and
        dominant_expected
        == expected_type
        and
        dominant_ratio
        >= MIN_EXPECTED_TYPE_RATIO
    )

    # =================================================================
    # CAS 1 : RELATION NON RESOLUE
    # =================================================================

    if not relation_is_resolved(
        candidate
    ):

        return {
            "classification":
                "UNRESOLVED_RELATION",

            "confidence":
                0.0,

            "proposed_action":
                "NONE",

            "reason":
                (
                    "La relation n'a pas été résolue de manière "
                    "suffisamment fiable dans le JSON clinique."
                ),

            "lexical_signals":
                signals,
        }

    # =================================================================
    # CAS 2 : ENTITE NON RESOLUE
    # =================================================================

    if not entity_is_resolved(
        candidate
    ):

        return {
            "classification":
                "RELATION_ENDPOINT_SUSPECT",

            "confidence":
                0.0,

            "proposed_action":
                "REVIEW_ENDPOINT",

            "reason":
                (
                    "L'endpoint ontologique n'a pas été résolu de "
                    "manière suffisamment fiable."
                ),

            "lexical_signals":
                signals,
        }

    # =================================================================
    # CAS 3 : TYPE IDENTIQUE
    # =================================================================

    if (
        current_type
        and expected_type
        and current_type == expected_type
    ):

        return {
            "classification":
                "RELATION_ONTOLOGY_CONFLICT",

            "confidence":
                0.0,

            "proposed_action":
                "REVIEW_RELATION",

            "reason":
                (
                    "Le type actuel correspond déjà au type attendu. "
                    "La violation doit être réexaminée au niveau de "
                    "la relation ou de la règle ontologique."
                ),

            "lexical_signals":
                signals,
        }

    # =================================================================
    # CAS 4 : PREUVE FORTE
    #
    # Deux conditions indépendantes :
    #
    # A) indice lexical STRONG
    # B) plusieurs violations cohérentes pour la même entité
    #
    # =================================================================

    if (
        strong_lexical
        and repeated_consistent
    ):

        return {
            "classification":
                "ENTITY_MISTYPING_STRONG",

            "confidence":
                0.99,

            "proposed_action":
                "PROPOSE_RETYPE_ENTITY",

            "reason":
                (
                    "Le texte de l'entité soutient explicitement le "
                    "type attendu et plusieurs violations ontologiques "
                    "indépendantes convergent vers ce même type."
                ),

            "lexical_signals":
                signals,
        }

    # =================================================================
    # CAS 5 : INDICE LEXICAL FORT MAIS VIOLATION ISOLEE
    # =================================================================

    if strong_lexical:

        return {
            "classification":
                "ENTITY_MISTYPING_POSSIBLE",

            "confidence":
                0.85,

            "proposed_action":
                "REVIEW_ENTITY_TYPE",

            "reason":
                (
                    "Le texte soutient fortement le type attendu, "
                    "mais la convergence ontologique n'est pas "
                    "suffisante pour autoriser automatiquement un "
                    "retypage."
                ),

            "lexical_signals":
                signals,
        }

    # =================================================================
    # CAS 6 : PLUSIEURS RELATIONS CONVERGENT
    # =================================================================

    if repeated_consistent:

        return {
            "classification":
                "ENTITY_MISTYPING_POSSIBLE",

            "confidence":
                0.75,

            "proposed_action":
                "REVIEW_ENTITY_TYPE",

            "reason":
                (
                    "Plusieurs relations convergent vers le même type "
                    "attendu, mais aucune preuve lexicale explicite "
                    "suffisamment forte n'autorise un retypage "
                    "automatique."
                ),

            "lexical_signals":
                signals,
        }

    # =================================================================
    # CAS 7 : SIGNAL MOYEN
    # =================================================================

    if medium_lexical:

        return {
            "classification":
                "ENTITY_MISTYPING_POSSIBLE",

            "confidence":
                0.60,

            "proposed_action":
                "REVIEW_ENTITY_TYPE",

            "reason":
                (
                    "Un indice lexical compatible avec le type attendu "
                    "est présent, mais il n'est pas assez discriminant "
                    "pour une correction automatique."
                ),

            "lexical_signals":
                signals,
        }

    # =================================================================
    # CAS 8 : AUCUNE PREUVE DE RETYPAGE
    # =================================================================

    return {
        "classification":
            "RELATION_ONTOLOGY_CONFLICT",

        "confidence":
            0.0,

        "proposed_action":
            "REVIEW_RELATION",

        "reason":
            (
                "La violation domain/range est réelle selon le schéma, "
                "mais aucune preuve suffisamment forte ne permet "
                "d'attribuer automatiquement l'erreur au type de "
                "l'entité."
            ),

        "lexical_signals":
            signals,
    }


# =====================================================================
# MAIN
# =====================================================================

def main():

    print("=" * 120)

    print(
        "TRACE / SGCE - "
        "ENTITY VALIDATION CLASSIFIER V1 "
        "- CONSERVATIVE MULTI-EVIDENCE"
    )

    print("=" * 120)

    # -----------------------------------------------------------------
    # Chargement
    # -----------------------------------------------------------------

    data = load_json(
        INPUT_FILE
    )

    candidates = data.get(
        "candidates",
        []
    )

    # -----------------------------------------------------------------
    # Groupes d'entités
    # -----------------------------------------------------------------

    entity_groups = build_entity_groups(
        candidates
    )

    group_analyses = {}

    for key, group in (
        entity_groups.items()
    ):

        group_analyses[
            key
        ] = analyze_entity_group(
            group
        )

    # -----------------------------------------------------------------
    # Classification
    # -----------------------------------------------------------------

    decisions = []

    classification_counter = Counter()

    action_counter = Counter()

    confidence_counter = Counter()

    strong_groups = set()

    for i, candidate in enumerate(
        candidates,
        start=1
    ):

        document = clean(
            candidate.get(
                "document"
            )
        )

        eid = clean(
            candidate.get(
                "entity_id"
            )
        )

        group_key = (
            document,
            eid
        )

        group_analysis = (
            group_analyses.get(
                group_key,
                {
                    "number_of_violations": 1,
                    "expected_type_counts": {},
                    "current_type_counts": {},
                    "relation_counts": {},
                    "role_counts": {},
                    "dominant_expected_type": None,
                    "dominant_expected_count": 0,
                    "dominant_expected_ratio": 0.0,
                }
            )
        )

        result = classify_candidate(
            candidate,
            group_analysis
        )

        decision = {
            **candidate,

            "decision_id":
                f"ONTO_DEC_{i:05d}",

            "entity_group_analysis":
                group_analysis,

            "classification":
                result[
                    "classification"
                ],

            "confidence":
                result[
                    "confidence"
                ],

            "proposed_action":
                result[
                    "proposed_action"
                ],

            "classifier_reason":
                result[
                    "reason"
                ],

            "lexical_signals":
                result[
                    "lexical_signals"
                ],
        }

        decisions.append(
            decision
        )

        classification_counter[
            decision[
                "classification"
            ]
        ] += 1

        action_counter[
            decision[
                "proposed_action"
            ]
        ] += 1

        confidence_counter[
            str(
                decision[
                    "confidence"
                ]
            )
        ] += 1

        if (
            decision[
                "classification"
            ]
            == "ENTITY_MISTYPING_STRONG"
        ):
            strong_groups.add(
                group_key
            )

    # -----------------------------------------------------------------
    # Résumé des entités
    # -----------------------------------------------------------------

    entity_group_summary = []

    for (
        document,
        eid
    ), analysis in group_analyses.items():

        group_decisions = [
            x
            for x in decisions
            if clean(
                x.get("document")
            ) == document
            and clean(
                x.get("entity_id")
            ) == eid
        ]

        classifications = Counter(
            x.get(
                "classification"
            )
            for x in group_decisions
        )

        actions = Counter(
            x.get(
                "proposed_action"
            )
            for x in group_decisions
        )

        first = (
            group_decisions[0]
            if group_decisions
            else {}
        )

        entity_group_summary.append({
            "document":
                document,

            "entity_id":
                eid,

            "entity_text":
                first.get(
                    "entity_text"
                ),

            "current_type":
                first.get(
                    "entity_type"
                ),

            **analysis,

            "classification_counts":
                dict(
                    classifications
                ),

            "action_counts":
                dict(
                    actions
                ),
        })

    # -----------------------------------------------------------------
    # OUTPUT
    # -----------------------------------------------------------------

    output = {
        "classifier":
            "entity_validation_classifier",

        "version":
            "V1_CONSERVATIVE_MULTI_EVIDENCE",

        "mode":
            "NON_DESTRUCTIVE",

        "summary": {
            "candidates_received":
                len(candidates),

            "entity_groups":
                len(entity_groups),

            "strong_mistyping_entity_groups":
                len(strong_groups),

            "classification_counts":
                dict(
                    classification_counter
                ),

            "proposed_action_counts":
                dict(
                    action_counter
                ),

            "confidence_counts":
                dict(
                    confidence_counter
                ),
        },

        "entity_group_summary":
            entity_group_summary,

        "decisions":
            decisions,
    }

    dump_json(
        OUTPUT_FILE,
        output
    )

    # =================================================================
    # AFFICHAGE
    # =================================================================

    print(
        f"Candidats reçus                    : "
        f"{len(candidates)}"
    )

    print(
        f"Groupes d'entités                  : "
        f"{len(entity_groups)}"
    )

    print(
        f"Groupes mistyping STRONG           : "
        f"{len(strong_groups)}"
    )

    print()

    print(
        "CLASSIFICATIONS"
    )

    print("-" * 120)

    for key, value in (
        classification_counter.most_common()
    ):

        print(
            f"{key:<60}: {value}"
        )

    print()

    print(
        "ACTIONS PROPOSEES"
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
        "CONFIANCES"
    )

    print("-" * 120)

    for key, value in sorted(
        confidence_counter.items(),
        key=lambda x: float(x[0]),
        reverse=True
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
        "Aucune donnée clinique n'a été modifiée."
    )


# =====================================================================
# ENTRY POINT
# =====================================================================

if __name__ == "__main__":
    main()