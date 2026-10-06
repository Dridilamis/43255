# -*- coding: utf-8 -*-

"""
semantic_factual_contradiction_validator.py
===========================================

TRACE / SGCE - SEMANTIC FACTUAL CONTRADICTION VALIDATOR V1

OBJECTIF
--------
Réexaminer UNIQUEMENT les relations classées :

    SAFE_REMOVE_CANDIDATE
    + PROPOSE_REMOVE_RELATION

par le semantic_factual_third_pass_validator.py.

Le but est d'éviter une suppression erronée lorsqu'un marqueur
de négation est simplement proche de la relation mais ne porte
pas réellement sur l'assertion source --relation--> cible.

SORTIES POSSIBLES
-----------------
SAFE_REMOVE
    Contradiction locale explicite, directement ancrée sur
    l'un des endpoints et compatible avec le type de relation.

SAFE_KEEP
    Le contexte montre que la relation peut rester valide
    malgré la négation, notamment dans les cas temporels
    comme l'arrêt d'un traitement déjà administré.

REVIEW
    La portée de la négation reste ambiguë.

IMPORTANT
---------
Ce script NE SUPPRIME aucune relation clinique.
Il produit uniquement une décision finale de validation.
"""

import json
import re
import unicodedata

from pathlib import Path
from collections import Counter


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent
STAGE3_DIR = ROOT.parent
REDUCTION_DIR = STAGE3_DIR.parent
PROJECT_DIR = REDUCTION_DIR.parent

# Entrée clinique officielle : sortie validée de Root Cause.
SOURCE_DIR = STAGE3_DIR / "root_cause" / "root_cause_entity_safe_corrected"

# Textes bruts produits par Mistral, conservés à la racine du projet OCR vers LLM.
TEXT_DIR = PROJECT_DIR / "Sortie_Textes_Brut_MistralSmall4"

INPUT_FILE = ROOT / "outputs" / "semantic_factual_third_pass_validated.json"
OUTPUT_FILE = ROOT / "outputs" / "semantic_factual_contradiction_validated.json"

# ============================================================
# CONFIGURATION
# ============================================================

# Fenêtre locale stricte autour de l'endpoint négaté.
NEGATION_RADIUS = 120

# Distance maximale entre cue de négation et endpoint.
MAX_NEGATION_DISTANCE = 80

# Une relation ne sera jamais SAFE_REMOVE sans
# contradiction explicitement localisée.
MIN_SAFE_REMOVE_CONFIDENCE = 0.99


# ============================================================
# CUES
# ============================================================

NEGATION_PATTERNS = [

    r"\bpas de\b",
    r"\bpas d[' ]",
    r"\babsence de\b",
    r"\babsence d[' ]",
    r"\bsans\b",
    r"\baucun(?:e)?\b",
    r"\bnie\b",
    r"\bni[eé]e\b",
    r"\bexclu(?:e)?\b",
    r"\bnon retrouv[eé]e?\b",
    r"\bnon objectiv[eé]e?\b",
    r"\bnon pr[eé]sent(?:e)?\b",
    r"\bn[eé]gatif(?:ve)?\b",
    r"\babsence\b",
]


# Ces expressions ne doivent PAS être interprétées
# automatiquement comme "le traitement n'a jamais existé".
STOP_PATTERNS = [

    r"\barr[eê]t\b",
    r"\barr[eê]t de\b",
    r"\barr[eê]t du\b",
    r"\barr[eê]t d[' ]",

    r"\bsuspension\b",
    r"\bsuspendu(?:e)?\b",

    r"\binterruption\b",
    r"\binterrompu(?:e)?\b",

    r"\bstopp[eé]\b",
]


HISTORICAL_PATTERNS = [

    r"\bauparavant\b",
    r"\bpr[eé]c[eé]demment\b",
    r"\bant[eé]rieurement\b",

    r"\bavait re[cç]u\b",
    r"\ba re[cç]u\b",

    r"\bavait [eé]t[eé] trait[eé]",
    r"\ba [eé]t[eé] trait[eé]",

    r"\btraitement ant[eé]rieur\b",
]


ADMINISTRATION_PATTERNS = [

    r"\badministr[eé]\b",
    r"\badministr[eé]e\b",
    r"\badministration\b",

    r"\bre[cç]oit\b",
    r"\bre[cç]u\b",

    r"\bmis sous\b",
    r"\bmise sous\b",

    r"\btrait[eé] par\b",
    r"\btrait[eé]e par\b",

    r"\bprescrit\b",
    r"\bprescrite\b",

    r"\bintroduit\b",
    r"\bintroduite\b",
]


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
# NORMALISATION
# ============================================================

def normalize_text(value):

    if value is None:
        return ""

    text = str(value)

    text = unicodedata.normalize(
        "NFKC",
        text,
    )

    text = (
        text
        .replace("’", "'")
        .replace("‘", "'")
        .replace("`", "'")
    )

    # Corrections de mojibake fréquentes
    replacements = {

        "â€™": "'",
        "Ã©": "é",
        "Ã¨": "è",
        "Ãª": "ê",
        "Ã ": "à",
        "Ã§": "ç",
        "Ã´": "ô",
        "Ã®": "î",
        "Ã¹": "ù",
    }

    for old, new in replacements.items():

        text = text.replace(
            old,
            new,
        )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip().lower()


def remove_accents(value):

    value = unicodedata.normalize(
        "NFD",
        value,
    )

    return "".join(
        c
        for c in value
        if unicodedata.category(c) != "Mn"
    )


def normalize_relaxed(value):

    value = normalize_text(
        value
    )

    value = remove_accents(
        value
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


# ============================================================
# TEXT FILE
# ============================================================

def find_text_file(document):

    stem = Path(
        str(document)
    ).stem

    candidates = list(
        TEXT_DIR.glob(
            f"{stem}*.txt"
        )
    )

    if candidates:
        return candidates[0]

    short = stem.split(
        "_trace_sepsis"
    )[0]

    candidates = list(
        TEXT_DIR.glob(
            f"{short}*.txt"
        )
    )

    if candidates:
        return candidates[0]

    return None


# ============================================================
# ENDPOINT TEXT
# ============================================================

def get_endpoint_variants(
    item,
    side,
):

    """
    Récupère différentes représentations
    textuelles d'un endpoint.
    """

    candidates = []

    keys = [

        f"{side}_text",
        f"{side}_proof",
        f"{side}_text_relation",
    ]

    for key in keys:

        value = item.get(
            key
        )

        if not value:
            continue

        value = normalize_relaxed(
            value
        )

        if value:
            candidates.append(
                value
            )

        if "|" in value:

            for part in value.split("|"):

                part = part.strip()

                if part:
                    candidates.append(
                        part
                    )

    # Déduplication
    result = []

    seen = set()

    for value in candidates:

        if value in seen:
            continue

        seen.add(
            value
        )

        result.append(
            value
        )

    # Les formes longues en premier.
    result.sort(
        key=len,
        reverse=True,
    )

    return result


# ============================================================
# PATTERN SEARCH
# ============================================================

def find_patterns(
    text,
    patterns,
):

    matches = []

    for pattern in patterns:

        for match in re.finditer(
            pattern,
            text,
            flags=re.I,
        ):

            matches.append({

                "pattern":
                    pattern,

                "text":
                    match.group(0),

                "start":
                    match.start(),

                "end":
                    match.end(),
            })

    return matches


def contains_pattern(
    text,
    patterns,
):

    return bool(
        find_patterns(
            text,
            patterns,
        )
    )


# ============================================================
# ENDPOINT POSITION
# ============================================================

def find_endpoint_positions(
    text,
    variants,
):

    positions = []

    for variant in variants:

        start = 0

        while True:

            pos = text.find(
                variant,
                start,
            )

            if pos < 0:
                break

            positions.append({

                "variant":
                    variant,

                "start":
                    pos,

                "end":
                    pos + len(variant),
            })

            start = (
                pos
                + max(
                    len(variant),
                    1,
                )
            )

    return positions


# ============================================================
# NEGATION -> ENDPOINT DISTANCE
# ============================================================

def distance_between(
    cue,
    endpoint,
):

    # Cue avant endpoint
    if cue["end"] <= endpoint["start"]:

        return (
            endpoint["start"]
            - cue["end"]
        )

    # Cue après endpoint
    if endpoint["end"] <= cue["start"]:

        return (
            cue["start"]
            - endpoint["end"]
        )

    # chevauchement
    return 0


def closest_negation(
    text,
    endpoint_positions,
):

    cues = find_patterns(
        text,
        NEGATION_PATTERNS,
    )

    best = None

    for endpoint in endpoint_positions:

        for cue in cues:

            distance = distance_between(
                cue,
                endpoint,
            )

            if (
                best is None
                or distance
                < best["distance"]
            ):

                best = {

                    "cue":
                        cue,

                    "endpoint":
                        endpoint,

                    "distance":
                        distance,
                }

    return best


# ============================================================
# LOCAL CONTEXT
# ============================================================

def get_local_context(
    text,
    endpoint,
):

    start = max(
        0,
        endpoint["start"]
        - NEGATION_RADIUS,
    )

    end = min(
        len(text),
        endpoint["end"]
        + NEGATION_RADIUS,
    )

    return text[
        start:end
    ]


# ============================================================
# VALIDATION D'UN CANDIDAT
# ============================================================

def validate_candidate(
    item,
    document_text,
):

    relation = (
        item.get("relation_type")
        or item.get("relation_name")
        or ""
    )

    source_status = str(
        item.get(
            "source_clinical_status"
        )
        or ""
    ).upper()

    target_status = str(
        item.get(
            "target_clinical_status"
        )
        or ""
    ).upper()

    source_variants = get_endpoint_variants(
        item,
        "source",
    )

    target_variants = get_endpoint_variants(
        item,
        "target",
    )

    source_positions = find_endpoint_positions(
        document_text,
        source_variants,
    )

    target_positions = find_endpoint_positions(
        document_text,
        target_variants,
    )

    source_negation = closest_negation(
        document_text,
        source_positions,
    )

    target_negation = closest_negation(
        document_text,
        target_positions,
    )

    # ========================================================
    # CHOISIR L'ENDPOINT QUI EST REELLEMENT NEGATE
    # ========================================================

    negative_statuses = {

        "NEGATED",
        "ABSENT",
        "EXCLUDED",
        "RULED_OUT",
    }

    selected = None
    selected_side = None

    if (
        source_status
        in negative_statuses
    ):

        selected = source_negation
        selected_side = "SOURCE"

    elif (
        target_status
        in negative_statuses
    ):

        selected = target_negation
        selected_side = "TARGET"

    else:

        # Le third pass a détecté une contradiction,
        # mais aucun endpoint ne porte réellement
        # un statut négatif exploitable.
        return {

            "contradiction_final_status":
                "REVIEW",

            "contradiction_final_action":
                "NONE",

            "contradiction_confidence":
                0.0,

            "contradiction_reason":
                (
                    "Aucun endpoint ne porte un statut "
                    "négatif explicite exploitable."
                ),
        }

    # ========================================================
    # ENDPOINT INTROUVABLE
    # ========================================================

    if selected is None:

        return {

            "contradiction_final_status":
                "REVIEW",

            "contradiction_final_action":
                "NONE",

            "contradiction_confidence":
                0.0,

            "contradiction_reason":
                (
                    "L'endpoint négaté n'a pas pu être "
                    "rattaché de façon sûre à un marqueur "
                    "de négation dans le document."
                ),
        }

    distance = selected[
        "distance"
    ]

    endpoint = selected[
        "endpoint"
    ]

    cue = selected[
        "cue"
    ]

    local_context = get_local_context(
        document_text,
        endpoint,
    )

    # ========================================================
    # GARDE 1 : DISTANCE
    # ========================================================

    if distance > MAX_NEGATION_DISTANCE:

        return {

            "contradiction_final_status":
                "REVIEW",

            "contradiction_final_action":
                "NONE",

            "contradiction_confidence":
                0.50,

            "contradiction_reason":
                (
                    "Un marqueur de négation existe, "
                    "mais il est trop éloigné de "
                    "l'endpoint concerné."
                ),

            "negated_side":
                selected_side,

            "negation_cue":
                cue["text"],

            "negation_distance":
                distance,

            "matched_endpoint":
                endpoint["variant"],

            "local_context":
                local_context,
        }

    # ========================================================
    # GARDE 2 : ARRET DE TRAITEMENT
    # ========================================================

    has_stop = contains_pattern(
        local_context,
        STOP_PATTERNS,
    )

    has_historical = contains_pattern(
        local_context,
        HISTORICAL_PATTERNS,
    )

    has_administration = contains_pattern(
        local_context,
        ADMINISTRATION_PATTERNS,
    )

    if (
        relation
        == "traitement_administre_a"
        and selected_side == "SOURCE"
        and (
            has_stop
            or has_historical
            or has_administration
        )
    ):

        return {

            "contradiction_final_status":
                "SAFE_KEEP",

            "contradiction_final_action":
                "NONE",

            "contradiction_confidence":
                0.99,

            "contradiction_reason":
                (
                    "La négation correspond à un arrêt, "
                    "une suspension ou un contexte temporel "
                    "compatible avec une administration "
                    "antérieure du traitement."
                ),

            "negated_side":
                selected_side,

            "negation_cue":
                cue["text"],

            "negation_distance":
                distance,

            "matched_endpoint":
                endpoint["variant"],

            "stop_cue":
                has_stop,

            "historical_cue":
                has_historical,

            "administration_cue":
                has_administration,

            "local_context":
                local_context,
        }

    # ========================================================
    # GARDE 3 : CUE DOIT ETRE AVANT OU AU CONTACT
    # ========================================================

    # En français clinique, les structures les plus sûres
    # sont typiquement :
    #
    #   absence de choc
    #   pas de pneumonie
    #   sans défaillance respiratoire
    #
    # Si la cue est après l'endpoint, on reste conservateur.

    cue_before_endpoint = (
        cue["start"]
        <= endpoint["start"]
    )

    if not cue_before_endpoint:

        return {

            "contradiction_final_status":
                "REVIEW",

            "contradiction_final_action":
                "NONE",

            "contradiction_confidence":
                0.60,

            "contradiction_reason":
                (
                    "La négation est proche de l'endpoint, "
                    "mais sa direction syntaxique n'est pas "
                    "suffisamment sûre."
                ),

            "negated_side":
                selected_side,

            "negation_cue":
                cue["text"],

            "negation_distance":
                distance,

            "matched_endpoint":
                endpoint["variant"],

            "local_context":
                local_context,
        }

    # ========================================================
    # GARDE 4 : DISTANCE TRES LOCALE
    # ========================================================

    # 40 caractères = forte liaison locale.
    if distance <= 40:

        confidence = 0.995

    elif distance <= 60:

        confidence = 0.99

    else:

        confidence = 0.95

    # ========================================================
    # SAFE REMOVE
    # ========================================================

    if (
        confidence
        >= MIN_SAFE_REMOVE_CONFIDENCE
    ):

        return {

            "contradiction_final_status":
                "SAFE_REMOVE",

            "contradiction_final_action":
                "REMOVE_RELATION",

            "contradiction_confidence":
                confidence,

            "contradiction_reason":
                (
                    "La négation est explicitement et "
                    "localement rattachée à l'endpoint "
                    "concerné. La relation est contradite "
                    "dans ce contexte."
                ),

            "negated_side":
                selected_side,

            "negation_cue":
                cue["text"],

            "negation_distance":
                distance,

            "matched_endpoint":
                endpoint["variant"],

            "local_context":
                local_context,
        }

    # ========================================================
    # REVIEW
    # ========================================================

    return {

        "contradiction_final_status":
            "REVIEW",

        "contradiction_final_action":
            "NONE",

        "contradiction_confidence":
            confidence,

        "contradiction_reason":
            (
                "Une négation locale est présente, "
                "mais l'ancrage n'est pas suffisamment "
                "fort pour autoriser une suppression."
            ),

        "negated_side":
            selected_side,

        "negation_cue":
            cue["text"],

        "negation_distance":
            distance,

        "matched_endpoint":
            endpoint["variant"],

        "local_context":
            local_context,
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

    validated = payload.get(
        "validated",
        [],
    )

    # ========================================================
    # UNIQUEMENT LES SAFE_REMOVE_CANDIDATE
    # ========================================================

    candidates = [

        item
        for item in validated

        if (
            item.get(
                "third_pass_final_status"
            )
            == "SAFE_REMOVE_CANDIDATE"

            and item.get(
                "third_pass_final_action"
            )
            == "PROPOSE_REMOVE_RELATION"
        )
    ]

    text_cache = {}

    results = []

    status_counts = Counter()
    action_counts = Counter()

    missing_text = 0

    # ========================================================
    # VALIDATION
    # ========================================================

    for item in candidates:

        document = item.get(
            "document"
        )

        if document not in text_cache:

            text_file = find_text_file(
                document
            )

            if text_file is None:

                text_cache[
                    document
                ] = None

            else:

                raw_text = (
                    text_file.read_text(
                        encoding="utf-8",
                        errors="ignore",
                    )
                )

                text_cache[
                    document
                ] = normalize_relaxed(
                    raw_text
                )

        document_text = (
            text_cache[
                document
            ]
        )

        if document_text is None:

            missing_text += 1

            result = {

                "contradiction_final_status":
                    "REVIEW",

                "contradiction_final_action":
                    "NONE",

                "contradiction_confidence":
                    0.0,

                "contradiction_reason":
                    "Texte brut indisponible.",
            }

        else:

            result = validate_candidate(
                item,
                document_text,
            )

        row = {

            **item,
            **result,
        }

        results.append(
            row
        )

        status_counts[
            result[
                "contradiction_final_status"
            ]
        ] += 1

        action_counts[
            result[
                "contradiction_final_action"
            ]
        ] += 1

    # ========================================================
    # OUTPUT
    # ========================================================

    output = {

        "validator":
            "semantic_factual_contradiction_validator",

        "mode":
            "STRICT_NEGATION_SCOPE_VALIDATION",

        "summary": {

            "third_pass_validated_received":
                len(validated),

            "safe_remove_candidates_received":
                len(candidates),

            "texts_missing":
                missing_text,

            "final_status_counts":
                dict(status_counts),

            "final_action_counts":
                dict(action_counts),

            "safe_remove":
                status_counts.get(
                    "SAFE_REMOVE",
                    0,
                ),

            "safe_keep":
                status_counts.get(
                    "SAFE_KEEP",
                    0,
                ),

            "review":
                status_counts.get(
                    "REVIEW",
                    0,
                ),
        },

        "contradiction_validated":
            results,
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
        "SEMANTIC FACTUAL CONTRADICTION VALIDATOR V1"
    )

    print("=" * 120)

    print(
        f"Third Pass reçus                    : "
        f"{len(validated)}"
    )

    print(
        f"SAFE_REMOVE_CANDIDATE reçus         : "
        f"{len(candidates)}"
    )

    print(
        f"Textes manquants                    : "
        f"{missing_text}"
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
        "RESUME"
    )

    print("-" * 120)

    print(
        f"Relations SAFE_REMOVE               : "
        f"{status_counts.get('SAFE_REMOVE', 0)}"
    )

    print(
        f"Relations récupérées SAFE_KEEP      : "
        f"{status_counts.get('SAFE_KEEP', 0)}"
    )

    print(
        f"Relations restant REVIEW            : "
        f"{status_counts.get('REVIEW', 0)}"
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