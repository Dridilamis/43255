# -*- coding: utf-8 -*-

"""
TRACE / SGCE - ONTOLOGY RELATION RESIDUAL CLASSIFIER V1
CONSERVATIVE ENDPOINT-FIRST CLASSIFICATION

OBJECTIF
--------
Classifier les violations ontologiques relationnelles restantes après
le retypage SAFE des entités.

Entrée :
    ontology_relation_residual_candidates.json

Sortie :
    ontology_relation_residual_decisions.json

CLASSIFICATIONS
---------------
1. ENDPOINT_TYPE_STRONGLY_GROUNDED
   Le type actuel de l'endpoint fautif est fortement soutenu par
   sa sémantique intrinsèque. Il ne faut PAS le retyper simplement
   pour satisfaire le domain/range de la relation.

2. POSSIBLE_ENTITY_TYPE_ERROR
   Le type actuel de l'endpoint semble potentiellement incorrect,
   mais la preuve n'est pas assez forte pour une correction automatique.

3. RELATION_TYPE_ERROR_CANDIDATE
   Les endpoints semblent cohérents mais la relation est incompatible
   avec leurs types. La relation elle-même doit être auditée.

4. UNSUPPORTED_RELATION_CANDIDATE
   La relation est ontologiquement incompatible et les informations
   disponibles ne permettent pas de justifier sa conservation.

5. AMBIGUOUS
   Preuve insuffisante.

6. UNRESOLVED
   Relation ou endpoint non résolu.

IMPORTANT
---------
Ce classifier :
- NE MODIFIE AUCUNE DONNEE CLINIQUE ;
- NE RETYPE AUCUNE ENTITE ;
- NE SUPPRIME AUCUNE RELATION ;
- ne produit que des propositions à valider ensuite.
"""

# GENERICITY PATCH: TRACE_BASE_DIR can be supplied through the environment.

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
INPUT_FILE = ROOT / "queues" / "ontology_relation_residual_candidates.json"
OUTPUT_FILE = ROOT / "outputs" / "ontology_relation_residual_decisions.json"
OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)


# =====================================================================
# NORMALISATION
# =====================================================================

def clean(value):

    if value is None:
        return ""

    return str(value).strip()


def upper(value):

    return clean(value).upper()


def normalize_text(value):

    value = clean(value).casefold()

    value = unicodedata.normalize(
        "NFKD",
        value
    )

    value = "".join(
        c for c in value
        if not unicodedata.combining(c)
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


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


# =====================================================================
# ANCRAGES SEMANTIQUES FORTS
# =====================================================================

# ---------------------------------------------------------------------
# DONNEE_PATIENT
# ---------------------------------------------------------------------

PATIENT_PATTERNS = [

    r"^patient$",
    r"^patiente$",

    r"^le patient$",
    r"^la patiente$",

    r"^un patient$",
    r"^une patiente$",

    r"^ce patient$",
    r"^cette patiente$",

    r"^notre patient$",
    r"^notre patiente$",

    r"^chez le patient$",
    r"^chez la patiente$",
]


# ---------------------------------------------------------------------
# Types avec indices lexicaux raisonnablement forts
# ---------------------------------------------------------------------

TYPE_LEXICAL_HINTS = {

    "DONNEE_PATIENT": [
        "patient",
        "patiente",
        "homme",
        "femme",
    ],

    "SYMPTOME": [
        "douleur",
        "dyspnee",
        "toux",
        "fievre",
        "asthenie",
        "vomissement",
        "nausee",
        "frisson",
        "confusion",
        "diarrhee",
    ],

    "DEFAILLANCE_ORGANE": [
        "insuffisance renale",
        "insuffisance respiratoire",
        "insuffisance hepatique",
        "defaillance renale",
        "defaillance respiratoire",
        "defaillance hepatique",
        "defaillance neurologique",
        "choc",
        "dysfonction",
    ],

    "LABEL_NOSOLOGIQUE": [
        "sepsis",
        "choc septique",
        "infection",
        "pneumonie",
        "endocardite",
        "meningite",
        "diagnostic",
    ],

    "TRAITEMENT": [
        "antibiotique",
        "antibiotherapie",
        "noradrenaline",
        "adrenaline",
        "amikacine",
        "amiklin",
        "tazocilline",
        "lasilix",
        "remplissage",
        "oxygene",
    ],

    "IMAGERIE_PROCEDURE": [
        "scanner",
        "tdm",
        "irm",
        "radiographie",
        "echographie",
        "echo",
    ],

    "MICRO_ORGANISME": [
        "staphylococcus",
        "streptococcus",
        "escherichia",
        "coli",
        "campylobacter",
        "pseudomonas",
        "candida",
    ],

    "FOYER_INFECTIEUX": [
        "foyer",
        "pulmonaire",
        "urinaire",
        "digestif",
        "cutane",
        "abdominal",
    ],

    "POSOLOGIE": [
        "mg",
        "µg",
        "ug",
        "gramme",
        "dose",
        "ml",
        "g/j",
        "mg/j",
        "mg/h",
    ],
}


# =====================================================================
# RELATIONS PARTICULIEREMENT INFORMATIVES
# =====================================================================

# Ces relations ont un sens suffisamment spécifique pour que la présence
# d'un endpoint "patient/patiente" à la place de leur cible attendue
# soit un signal fort que le problème est probablement la relation,
# et non le type DONNEE_PATIENT.

RELATION_EXPECTATION = {

    "traitement_cible_defaillance": {
        "expected_target": {
            "DEFAILLANCE_ORGANE"
        }
    },

    "traitement_indique_par_label_nosologique": {
        "expected_target": {
            "LABEL_NOSOLOGIQUE"
        }
    },

    "presente_symptome": {
        "expected_source": {
            "DONNEE_PATIENT"
        },
        "expected_target": {
            "SYMPTOME"
        }
    },

    "presente_dysfonction_organe": {
        "expected_source": {
            "DONNEE_PATIENT"
        },
        "expected_target": {
            "DEFAILLANCE_ORGANE"
        }
    },

    "a_pour_label_nosologique": {
        "expected_source": {
            "DONNEE_PATIENT"
        },
        "expected_target": {
            "LABEL_NOSOLOGIQUE"
        }
    },

    "patient_a_pour_evolution": {
        "expected_source": {
            "DONNEE_PATIENT"
        },
        "expected_target": {
            "EVOLUTION_PRONOSTIC"
        }
    },

    "traitement_a_pour_posologie": {
        "expected_source": {
            "TRAITEMENT"
        },
        "expected_target": {
            "POSOLOGIE"
        }
    },

    "traitement_administre_a": {
        "expected_source": {
            "TRAITEMENT"
        },
        "expected_target": {
            "DONNEE_PATIENT"
        }
    },

    "imagerie_objective_foyer": {
        "expected_source": {
            "IMAGERIE_PROCEDURE"
        },
        "expected_target": {
            "FOYER_INFECTIEUX"
        }
    },

    "imagerie_objective_defaillance": {
        "expected_source": {
            "IMAGERIE_PROCEDURE"
        },
        "expected_target": {
            "DEFAILLANCE_ORGANE"
        }
    },

    "imagerie_objective_comorbidite": {
        "expected_source": {
            "IMAGERIE_PROCEDURE"
        },
        "expected_target": {
            "COMORBIDITE_ANTECEDENT"
        }
    },

    "micro_organisme_isole_dans": {
        "expected_source": {
            "MICRO_ORGANISME"
        },
        "expected_target": {
            "FOYER_INFECTIEUX"
        }
    },

    "biomarqueur_supporte_defaillance_organe": {
        "expected_source": {
            "BIOMARQUEUR"
        },
        "expected_target": {
            "DEFAILLANCE_ORGANE"
        }
    },

    "signe_vital_supporte_defaillance_organe": {
        "expected_source": {
            "SIGNE_VITAL"
        },
        "expected_target": {
            "DEFAILLANCE_ORGANE"
        }
    },
}


# =====================================================================
# TEST PATIENT
# =====================================================================

def is_explicit_patient_mention(text):

    text = normalize_text(text)

    if not text:
        return False

    for pattern in PATIENT_PATTERNS:

        if re.fullmatch(
            pattern,
            text
        ):
            return True

    return False


# =====================================================================
# INDICES LEXICAUX
# =====================================================================

def lexical_support_for_type(text, entity_type):

    """
    Retourne un score lexical conservateur entre 0 et 1.

    Ce score n'est PAS utilisé seul pour effectuer une correction.
    """

    text_n = normalize_text(text)
    entity_type = upper(entity_type)

    if not text_n or not entity_type:
        return 0.0

    # Patient explicite
    if (
        entity_type == "DONNEE_PATIENT"
        and is_explicit_patient_mention(text_n)
    ):
        return 1.0

    hints = TYPE_LEXICAL_HINTS.get(
        entity_type,
        []
    )

    if not hints:
        return 0.0

    matches = []

    for hint in hints:

        hint_n = normalize_text(hint)

        if hint_n in text_n:
            matches.append(hint_n)

    if not matches:
        return 0.0

    # Une correspondance exacte ou quasi exacte
    if any(
        text_n == hint
        for hint in matches
    ):
        return 0.95

    # Au moins un indice présent
    return 0.75


# =====================================================================
# COMPATIBILITE
# =====================================================================

def compatible(
    current_type,
    expected_types
):

    current_type = upper(
        current_type
    )

    expected_types = {
        upper(x)
        for x in (
            expected_types or []
        )
        if clean(x)
    }

    if not current_type:
        return False

    if not expected_types:
        return False

    return current_type in expected_types


# =====================================================================
# ANALYSE D'UN CANDIDAT
# =====================================================================

def classify_candidate(candidate):

    anomaly_type = clean(
        candidate.get(
            "anomaly_type"
        )
    )

    affected_role = upper(
        candidate.get(
            "affected_role"
        )
    )

    relation_name = clean(
        candidate.get(
            "relation_name"
        )
    )

    source_text = clean(
        candidate.get(
            "source_text"
        )
    )

    source_type = upper(
        candidate.get(
            "source_type"
        )
    )

    target_text = clean(
        candidate.get(
            "target_text"
        )
    )

    target_type = upper(
        candidate.get(
            "target_type"
        )
    )

    expected_source = [
        upper(x)
        for x in candidate.get(
            "expected_source_types",
            []
        )
    ]

    expected_target = [
        upper(x)
        for x in candidate.get(
            "expected_target_types",
            []
        )
    ]

    relation_resolution = clean(
        candidate.get(
            "relation_resolution"
        )
    )

    source_resolution = clean(
        candidate.get(
            "source_resolution"
        )
    )

    target_resolution = clean(
        candidate.get(
            "target_resolution"
        )
    )

    # =================================================================
    # Résolution obligatoire
    # =================================================================

    if relation_resolution != "ID_EXACT":

        return {
            "classification": "UNRESOLVED",
            "proposed_action": "NONE",
            "confidence": 0.0,
            "reason":
                "La relation n'a pas été résolue de manière exacte."
        }

    if source_resolution != "ID_EXACT":

        return {
            "classification": "UNRESOLVED",
            "proposed_action": "NONE",
            "confidence": 0.0,
            "reason":
                "L'entité source n'a pas été résolue de manière exacte."
        }

    if target_resolution != "ID_EXACT":

        return {
            "classification": "UNRESOLVED",
            "proposed_action": "NONE",
            "confidence": 0.0,
            "reason":
                "L'entité cible n'a pas été résolue de manière exacte."
        }

    # =================================================================
    # Endpoint fautif
    # =================================================================

    if affected_role == "SOURCE":

        affected_text = source_text
        affected_type = source_type
        expected_types = expected_source

    elif affected_role == "TARGET":

        affected_text = target_text
        affected_type = target_type
        expected_types = expected_target

    else:

        return {
            "classification": "AMBIGUOUS",
            "proposed_action": "NONE",
            "confidence": 0.0,
            "reason":
                "Le rôle affecté par l'anomalie n'est pas déterminé."
        }

    # =================================================================
    # Scores lexicaux
    # =================================================================

    current_type_support = lexical_support_for_type(
        affected_text,
        affected_type
    )

    expected_type_scores = {}

    for expected_type in expected_types:

        expected_type_scores[
            expected_type
        ] = lexical_support_for_type(
            affected_text,
            expected_type
        )

    best_expected_type = None
    best_expected_score = 0.0

    if expected_type_scores:

        best_expected_type = max(
            expected_type_scores,
            key=expected_type_scores.get
        )

        best_expected_score = (
            expected_type_scores[
                best_expected_type
            ]
        )

    # =================================================================
    # REGLE 1
    # Patient/patiente explicitement DONNEE_PATIENT
    # =================================================================

    if False:  # règle patient spécifique désactivée dans la version générique

        return {
            "classification":
                "ENDPOINT_TYPE_STRONGLY_GROUNDED",

            "proposed_action":
                "REVIEW_RELATION",

            "confidence":
                0.99,

            "reason":
                "L'endpoint est une mention explicite du patient et "
                "son type DONNEE_PATIENT est intrinsèquement fortement "
                "ancré. Il ne doit pas être retypé uniquement pour "
                "satisfaire le domain/range de la relation.",

            "affected_text":
                affected_text,

            "affected_type":
                affected_type,

            "best_expected_type":
                best_expected_type,

            "current_type_support":
                current_type_support,

            "best_expected_type_support":
                best_expected_score,
        }

    # =================================================================
    # REGLE 2
    # Type actuel fortement soutenu lexicalement
    # =================================================================

    if (
        current_type_support >= 0.95
        and best_expected_score < 0.75
    ):

        return {
            "classification":
                "ENDPOINT_TYPE_STRONGLY_GROUNDED",

            "proposed_action":
                "REVIEW_RELATION",

            "confidence":
                0.95,

            "reason":
                "Le type actuel de l'endpoint est fortement soutenu "
                "par sa mention textuelle tandis que le type attendu "
                "par la relation n'est pas suffisamment soutenu.",

            "affected_text":
                affected_text,

            "affected_type":
                affected_type,

            "best_expected_type":
                best_expected_type,

            "current_type_support":
                current_type_support,

            "best_expected_type_support":
                best_expected_score,
        }

    # =================================================================
    # REGLE 3
    # Le texte soutient fortement le type attendu
    # =================================================================

    if (
        best_expected_type
        and best_expected_score >= 0.95
        and current_type_support < 0.75
    ):

        return {
            "classification":
                "POSSIBLE_ENTITY_TYPE_ERROR",

            "proposed_action":
                "REVIEW_ENTITY_TYPE",

            "confidence":
                0.90,

            "reason":
                "La mention textuelle soutient fortement un type "
                "attendu par la relation et soutient peu le type "
                "actuellement attribué. Un retypage est plausible "
                "mais nécessite une validation indépendante.",

            "affected_text":
                affected_text,

            "affected_type":
                affected_type,

            "best_expected_type":
                best_expected_type,

            "current_type_support":
                current_type_support,

            "best_expected_type_support":
                best_expected_score,
        }

    # =================================================================
    # REGLE 4
    # Les DEUX endpoints sont sémantiquement bien ancrés
    # mais la relation reste incompatible.
    # =================================================================

    source_support = lexical_support_for_type(
        source_text,
        source_type
    )

    target_support = lexical_support_for_type(
        target_text,
        target_type
    )

    if (
        source_support >= 0.75
        and target_support >= 0.75
    ):

        return {
            "classification":
                "RELATION_TYPE_ERROR_CANDIDATE",

            "proposed_action":
                "REVIEW_RELATION",

            "confidence":
                0.90,

            "reason":
                "Les deux endpoints disposent d'un support sémantique "
                "pour leurs types actuels, mais la relation reste "
                "incompatible avec le domain/range attendu. La relation "
                "doit être auditée avant tout retypage.",

            "affected_text":
                affected_text,

            "affected_type":
                affected_type,

            "best_expected_type":
                best_expected_type,

            "current_type_support":
                current_type_support,

            "best_expected_type_support":
                best_expected_score,

            "source_type_support":
                source_support,

            "target_type_support":
                target_support,
        }

    # =================================================================
    # REGLE 5
    # Relation connue + endpoint actuel incompatible
    # mais aucun type attendu n'est lexicalement démontré.
    # =================================================================

    if (
        relation_name in RELATION_EXPECTATION
        and current_type_support >= 0.75
        and best_expected_score < 0.75
    ):

        return {
            "classification":
                "RELATION_TYPE_ERROR_CANDIDATE",

            "proposed_action":
                "REVIEW_RELATION",

            "confidence":
                0.85,

            "reason":
                "La relation possède une sémantique ontologique "
                "spécifique mais l'endpoint actuel est mieux soutenu "
                "que le type requis par cette relation. Le problème "
                "semble davantage porter sur la relation que sur "
                "l'entité.",

            "affected_text":
                affected_text,

            "affected_type":
                affected_type,

            "best_expected_type":
                best_expected_type,

            "current_type_support":
                current_type_support,

            "best_expected_type_support":
                best_expected_score,
        }

    # =================================================================
    # REGLE 6
    # Type attendu moyennement soutenu
    # =================================================================

    if (
        best_expected_type
        and best_expected_score >= 0.75
        and current_type_support < best_expected_score
    ):

        return {
            "classification":
                "POSSIBLE_ENTITY_TYPE_ERROR",

            "proposed_action":
                "REVIEW_ENTITY_TYPE",

            "confidence":
                0.75,

            "reason":
                "Le type attendu par la relation dispose d'un indice "
                "lexical supérieur au type actuel, mais la preuve "
                "reste insuffisante pour autoriser un retypage.",

            "affected_text":
                affected_text,

            "affected_type":
                affected_type,

            "best_expected_type":
                best_expected_type,

            "current_type_support":
                current_type_support,

            "best_expected_type_support":
                best_expected_score,
        }

    # =================================================================
    # REGLE 7
    # Aucun support convaincant
    # =================================================================

    if (
        current_type_support == 0.0
        and best_expected_score == 0.0
    ):

        return {
            "classification":
                "UNSUPPORTED_RELATION_CANDIDATE",

            "proposed_action":
                "DEEP_REVIEW_RELATION",

            "confidence":
                0.60,

            "reason":
                "Ni le type actuel de l'endpoint ni le type attendu "
                "par la relation ne sont suffisamment démontrés par "
                "la mention seule. Une analyse contextuelle profonde "
                "est nécessaire avant toute correction.",

            "affected_text":
                affected_text,

            "affected_type":
                affected_type,

            "best_expected_type":
                best_expected_type,

            "current_type_support":
                current_type_support,

            "best_expected_type_support":
                best_expected_score,
        }

    # =================================================================
    # FALLBACK
    # =================================================================

    return {
        "classification":
            "AMBIGUOUS",

        "proposed_action":
            "NONE",

        "confidence":
            0.50,

        "reason":
            "Les indices disponibles ne permettent pas de déterminer "
            "de manière sûre si l'anomalie provient du type de "
            "l'entité ou de la relation.",

        "affected_text":
            affected_text,

        "affected_type":
            affected_type,

        "best_expected_type":
            best_expected_type,

        "current_type_support":
            current_type_support,

        "best_expected_type_support":
            best_expected_score,
    }


# =====================================================================
# MAIN
# =====================================================================

def main():

    print("=" * 120)

    print(
        "TRACE / SGCE - ONTOLOGY RELATION RESIDUAL "
        "CLASSIFIER V1 - CONSERVATIVE ENDPOINT-FIRST"
    )

    print("=" * 120)

    if not INPUT_FILE.exists():

        raise FileNotFoundError(
            f"Fichier d'entrée introuvable : {INPUT_FILE}"
        )

    data = load_json(
        INPUT_FILE
    )

    candidates = data.get(
        "candidates",
        []
    )

    decisions = []

    classification_counter = Counter()
    action_counter = Counter()
    confidence_counter = Counter()
    relation_counter = Counter()
    role_counter = Counter()

    # Permet d'étudier les relations les plus problématiques
    classification_by_relation = defaultdict(
        Counter
    )

    # =================================================================
    # CLASSIFICATION
    # =================================================================

    for candidate in candidates:

        result = classify_candidate(
            candidate
        )

        decision = {
            **candidate,
            **result,
        }

        decisions.append(
            decision
        )

        classification = result.get(
            "classification",
            "UNKNOWN"
        )

        action = result.get(
            "proposed_action",
            "NONE"
        )

        confidence = result.get(
            "confidence",
            0.0
        )

        relation_name = candidate.get(
            "relation_name"
        ) or "<UNKNOWN>"

        affected_role = candidate.get(
            "affected_role"
        ) or "<UNKNOWN>"

        classification_counter[
            classification
        ] += 1

        action_counter[
            action
        ] += 1

        confidence_counter[
            str(confidence)
        ] += 1

        relation_counter[
            relation_name
        ] += 1

        role_counter[
            affected_role
        ] += 1

        classification_by_relation[
            relation_name
        ][
            classification
        ] += 1

    # =================================================================
    # RESUME PAR RELATION
    # =================================================================

    relation_analysis = []

    for relation_name, counts in sorted(
        classification_by_relation.items(),
        key=lambda x: -sum(x[1].values())
    ):

        relation_analysis.append({

            "relation_name":
                relation_name,

            "total":
                sum(
                    counts.values()
                ),

            "classifications":
                dict(counts)
        })

    # =================================================================
    # SORTIE
    # =================================================================

    output = {

        "classifier":
            "ontology_relation_residual_classifier",

        "version":
            "V1_CONSERVATIVE_ENDPOINT_FIRST",

        "input":
            str(INPUT_FILE),

        "summary": {

            "candidates_received":
                len(candidates),

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

            "affected_role_counts":
                dict(
                    role_counter
                ),
        },

        "relation_analysis":
            relation_analysis,

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

    print()

    print("CLASSIFICATIONS")
    print("-" * 120)

    for key, value in (
        classification_counter.most_common()
    ):

        print(
            f"{key:<60}: {value}"
        )

    print()

    print("ACTIONS PROPOSEES")
    print("-" * 120)

    for key, value in (
        action_counter.most_common()
    ):

        print(
            f"{key:<60}: {value}"
        )

    print()

    print("CONFIANCES")
    print("-" * 120)

    def confidence_sort(item):

        try:
            return -float(item[0])

        except Exception:
            return 0

    for key, value in sorted(
        confidence_counter.items(),
        key=confidence_sort
    ):

        print(
            f"{key:<60}: {value}"
        )

    print()

    print("CLASSIFICATIONS PAR RELATION")
    print("-" * 120)

    for row in relation_analysis[:20]:

        relation_name = row[
            "relation_name"
        ]

        total = row[
            "total"
        ]

        classes = ", ".join(
            f"{k}={v}"
            for k, v in row[
                "classifications"
            ].items()
        )

        print(
            f"{relation_name:<50}: "
            f"{total:<5} | {classes}"
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