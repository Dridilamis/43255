# -*- coding: utf-8 -*-

"""
semantic_factual_second_pass.py
===============================

TRACE / SGCE - SEMANTIC FACTUAL SECOND PASS V1

Réanalyse UNIQUEMENT les cas REVIEW produits par :
    semantic_factual_validator.py

Deux familles :

1. UNSUPPORTED_FACT
   -> recherche textuelle plus robuste :
      - normalisation Unicode ;
      - accents ;
      - espaces ;
      - apostrophes ;
      - x / X / × ;
      - ponctuation ;
      - variantes simples d'unités ;
      - recherche source / cible ;
      - recherche de cooccurrence locale.

2. NEGATION_SENSITIVE
   -> analyse conservatrice de cohérence avec
      les statuts cliniques déjà validés.

IMPORTANT :
- STILL_UNSUPPORTED n'est PAS une hallucination.
- aucune suppression automatique ici.
- aucune donnée clinique n'est modifiée.
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

INPUT_FILE = ROOT / "outputs" / "semantic_factual_validated.json"
OUTPUT_FILE = ROOT / "outputs" / "semantic_factual_second_pass.json"

# ============================================================
# CONSTANTES
# ============================================================

LOCAL_WINDOW = 500

NEGATION_STATUSES = {
    "NEGATED",
    "ABSENT",
    "EXCLUDED",
    "RULED_OUT",
}

STOP_ENDPOINTS = {
    "",
    "patient",
    "le patient",
    "la patiente",
    "patient(e)",
}


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

    # Unicode
    text = unicodedata.normalize(
        "NFKC",
        text,
    )

    # Apostrophes
    text = (
        text
        .replace("’", "'")
        .replace("‘", "'")
        .replace("`", "'")
    )

    # Multiplication
    text = (
        text
        .replace("×", " x ")
        .replace("✕", " x ")
        .replace("X", " x ")
    )

    # Micro
    text = (
        text
        .replace("μ", "µ")
    )

    # espaces avant unités
    text = re.sub(
        r"(\d)(mg|g|kg|ml|mL|l|L|µg|ug|mmhg|kpa|%)\b",
        r"\1 \2",
        text,
        flags=re.I,
    )

    # / j
    text = re.sub(
        r"\s*/\s*",
        "/",
        text,
    )

    # espaces
    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    text = text.strip().lower()

    return text


def normalize_relaxed(value):

    text = normalize_text(
        value
    )

    # accents
    decomposed = unicodedata.normalize(
        "NFD",
        text,
    )

    text = "".join(
        c
        for c in decomposed
        if unicodedata.category(c)
        != "Mn"
    )

    # ponctuation non essentielle
    text = re.sub(
        r"[,:;()\[\]{}]",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return text


# ============================================================
# ENDPOINT TEXT
# ============================================================

def clean_endpoint_text(value):

    text = normalize_relaxed(
        value
    )

    if not text:
        return ""

    # Certaines preuves contiennent :
    # "Amiklin | antibiotique"
    #
    # On conserve d'abord la partie principale.
    if "|" in text:
        first = text.split("|")[0].strip()

        if first:
            text = first

    return text


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
# SEARCH
# ============================================================

def find_occurrences(
    text,
    mention,
):

    if not text or not mention:
        return []

    positions = []

    start = 0

    while True:

        pos = text.find(
            mention,
            start,
        )

        if pos < 0:
            break

        positions.append(
            pos
        )

        start = (
            pos
            + max(
                len(mention),
                1,
            )
        )

    return positions


def minimum_distance(
    source_positions,
    target_positions,
):

    if (
        not source_positions
        or not target_positions
    ):
        return None

    best = None

    for s in source_positions:

        for t in target_positions:

            d = abs(
                s - t
            )

            if (
                best is None
                or d < best
            ):
                best = d

    return best


def best_local_context(
    text,
    source_positions,
    target_positions,
):

    if (
        not source_positions
        or not target_positions
    ):
        return ""

    best_pair = None
    best_distance = None

    for s in source_positions:

        for t in target_positions:

            distance = abs(
                s - t
            )

            if (
                best_distance is None
                or distance < best_distance
            ):
                best_distance = distance
                best_pair = (
                    s,
                    t,
                )

    if best_pair is None:
        return ""

    left = max(
        0,
        min(best_pair)
        - 200,
    )

    right = min(
        len(text),
        max(best_pair)
        + 300,
    )

    return text[
        left:right
    ]


# ============================================================
# SUPPORT RECHECK
# ============================================================

def recheck_support(
    item,
    normalized_document,
):

    source_raw = (
        item.get("source_text")
        or item.get("source_proof")
        or ""
    )

    target_raw = (
        item.get("target_text")
        or item.get("target_proof")
        or ""
    )

    source = clean_endpoint_text(
        source_raw
    )

    target = clean_endpoint_text(
        target_raw
    )

    # --------------------------------------------------------
    # Éviter les endpoints génériques
    # --------------------------------------------------------

    source_generic = (
        source in STOP_ENDPOINTS
    )

    target_generic = (
        target in STOP_ENDPOINTS
    )

    source_positions = (
        []
        if source_generic
        else find_occurrences(
            normalized_document,
            source,
        )
    )

    target_positions = (
        []
        if target_generic
        else find_occurrences(
            normalized_document,
            target,
        )
    )

    source_found = bool(
        source_positions
    )

    target_found = bool(
        target_positions
    )

    distance = minimum_distance(
        source_positions,
        target_positions,
    )

    context = best_local_context(
        normalized_document,
        source_positions,
        target_positions,
    )

    # --------------------------------------------------------
    # Classification
    # --------------------------------------------------------

    if (
        source_found
        and target_found
        and distance is not None
        and distance <= LOCAL_WINDOW
    ):

        classification = (
            "SUPPORTED_AFTER_RECHECK"
        )

        confidence = 0.99

        reason = (
            "Les deux endpoints sont retrouvés "
            "dans une fenêtre textuelle locale commune."
        )

    elif (
        source_found
        and target_found
    ):

        classification = (
            "DOCUMENT_LEVEL_SUPPORT"
        )

        confidence = 0.75

        reason = (
            "Les deux endpoints sont présents "
            "dans le document mais leur proximité "
            "locale ne démontre pas suffisamment "
            "la relation."
        )

    elif (
        source_found
        or target_found
    ):

        classification = (
            "PARTIAL_SUPPORT"
        )

        confidence = 0.50

        reason = (
            "Un seul endpoint a été retrouvé "
            "après normalisation."
        )

    else:

        classification = (
            "STILL_UNSUPPORTED"
        )

        confidence = 0.0

        reason = (
            "Aucun support textuel suffisamment "
            "robuste n'a été retrouvé. "
            "Cela ne constitue pas une preuve "
            "d'hallucination."
        )

    return {
        "second_pass_classification":
            classification,

        "second_pass_confidence":
            confidence,

        "second_pass_reason":
            reason,

        "normalized_source":
            source,

        "normalized_target":
            target,

        "source_found_after_normalization":
            source_found,

        "target_found_after_normalization":
            target_found,

        "minimum_endpoint_distance":
            distance,

        "local_context":
            context,
    }


# ============================================================
# NEGATION RECHECK
# ============================================================

def analyze_negation(
    item,
):

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

    relation = (
        item.get("relation_type")
        or item.get("relation_name")
        or ""
    )

    source_negated = (
        source_status
        in NEGATION_STATUSES
    )

    target_negated = (
        target_status
        in NEGATION_STATUSES
    )

    # --------------------------------------------------------
    # Aucun endpoint réellement négaté
    # --------------------------------------------------------

    if (
        not source_negated
        and not target_negated
    ):

        return {
            "second_pass_classification":
                "NEGATION_STATUS_UNCLEAR",

            "second_pass_confidence":
                0.0,

            "second_pass_reason":
                "Le cas était marqué sensible à "
                "la négation mais aucun endpoint "
                "n'a un statut négatif exploitable.",

            "negated_endpoint":
                None,

            "relation":
                relation,
        }

    # --------------------------------------------------------
    # Les deux négatés
    # --------------------------------------------------------

    if (
        source_negated
        and target_negated
    ):

        return {
            "second_pass_classification":
                "AMBIGUOUS_NEGATION",

            "second_pass_confidence":
                0.50,

            "second_pass_reason":
                "Les deux endpoints portent un "
                "statut négatif. Une décision "
                "automatique sur la relation serait "
                "trop risquée.",

            "negated_endpoint":
                "BOTH",

            "relation":
                relation,
        }

    # --------------------------------------------------------
    # Traitement négaté
    #
    # Exemple :
    # arrêt Lasilix -> patient
    #
    # On ne supprime PAS automatiquement :
    # cela peut représenter un traitement antérieur
    # puis arrêté.
    # --------------------------------------------------------

    if (
        source_negated
        and relation
        == "traitement_administre_a"
    ):

        return {
            "second_pass_classification":
                "TEMPORALLY_AMBIGUOUS_NEGATION",

            "second_pass_confidence":
                0.60,

            "second_pass_reason":
                "Le traitement est négaté ou arrêté, "
                "mais cela ne démontre pas qu'il "
                "n'a jamais été administré. "
                "Conflit temporel potentiel.",

            "negated_endpoint":
                "SOURCE",

            "relation":
                relation,
        }

    # --------------------------------------------------------
    # Cible négatée
    #
    # Ex :
    # biomarqueur -> défaillance NEGATED
    #
    # Potentiellement contradictoire, mais pas encore
    # SAFE_REMOVE automatiquement.
    # --------------------------------------------------------

    if target_negated:

        return {
            "second_pass_classification":
                "POTENTIAL_NEGATION_CONTRADICTION",

            "second_pass_confidence":
                0.85,

            "second_pass_reason":
                "La relation affirme un lien vers "
                "une cible portant un statut négatif. "
                "Une vérification contextuelle explicite "
                "est nécessaire avant toute suppression.",

            "negated_endpoint":
                "TARGET",

            "relation":
                relation,
        }

    # --------------------------------------------------------
    # Source négatée, autre relation
    # --------------------------------------------------------

    return {
        "second_pass_classification":
            "POTENTIAL_NEGATION_CONTRADICTION",

        "second_pass_confidence":
            0.80,

        "second_pass_reason":
            "La source de la relation porte un "
            "statut négatif. Vérification contextuelle "
            "requise avant modification.",

        "negated_endpoint":
            "SOURCE",

        "relation":
            relation,
    }


# ============================================================
# MAIN
# ============================================================

def main():

    if not INPUT_FILE.exists():

        raise FileNotFoundError(
            f"Fichier introuvable : "
            f"{INPUT_FILE}"
        )

    payload = load_json(
        INPUT_FILE
    )

    decisions = payload.get(
        "validated",
        [],
    )

    review = [
        x
        for x in decisions
        if x.get(
            "final_status"
        ) == "REVIEW"
    ]

    results = []

    classifications = Counter()

    initial_classes = Counter()

    missing_text = 0

    text_cache = {}

    # ========================================================
    # REVIEW
    # ========================================================

    for item in review:

        initial = (
            item.get("classification")
            or "UNKNOWN"
        )

        initial_classes[
            initial
        ] += 1

        document = item.get(
            "document"
        )

        # ----------------------------------------------------
        # UNSUPPORTED FACT
        # ----------------------------------------------------

        if (
            initial
            == "UNSUPPORTED_FACT"
        ):

            if document not in text_cache:

                text_file = find_text_file(
                    document
                )

                if text_file is None:

                    text_cache[
                        document
                    ] = None

                else:

                    raw = text_file.read_text(
                        encoding="utf-8",
                        errors="ignore",
                    )

                    text_cache[
                        document
                    ] = normalize_relaxed(
                        raw
                    )

            normalized_document = (
                text_cache[
                    document
                ]
            )

            if normalized_document is None:

                missing_text += 1

                result = {
                    "second_pass_classification":
                        "TEXT_MISSING",

                    "second_pass_confidence":
                        0.0,

                    "second_pass_reason":
                        "Texte brut du document introuvable.",
                }

            else:

                result = recheck_support(
                    item,
                    normalized_document,
                )

        # ----------------------------------------------------
        # NEGATION
        # ----------------------------------------------------

        elif (
            initial
            == "NEGATION_SENSITIVE"
        ):

            result = analyze_negation(
                item
            )

        # ----------------------------------------------------
        # Autre REVIEW
        # ----------------------------------------------------

        else:

            result = {
                "second_pass_classification":
                    "UNHANDLED_REVIEW_CLASS",

                "second_pass_confidence":
                    0.0,

                "second_pass_reason":
                    (
                        "Classification REVIEW non "
                        "prise en charge automatiquement."
                    ),
            }

        row = {
            **item,
            **result,
        }

        results.append(
            row
        )

        classifications[
            result[
                "second_pass_classification"
            ]
        ] += 1

    # ========================================================
    # OUTPUT
    # ========================================================

    output = {

        "analyzer":
            "semantic_factual_second_pass",

        "mode":
            "CONSERVATIVE_NORMALIZED_TEXT_RECHECK",

        "summary": {

            "validated_decisions_received":
                len(decisions),

            "review_received":
                len(review),

            "initial_review_classes":
                dict(initial_classes),

            "second_pass_classifications":
                dict(classifications),

            "documents_text_missing":
                missing_text,
        },

        "second_pass":
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
        "SEMANTIC FACTUAL SECOND PASS V1"
    )

    print("=" * 120)

    print(
        f"Décisions validées reçues           : "
        f"{len(decisions)}"
    )

    print(
        f"Cas REVIEW reçus                    : "
        f"{len(review)}"
    )

    print(
        f"Textes manquants                    : "
        f"{missing_text}"
    )

    print()

    print(
        "CLASSIFICATIONS INITIALES"
    )

    print("-" * 120)

    for key, value in (
        initial_classes.most_common()
    ):

        print(
            f"{key:<60}: {value}"
        )

    print()

    print(
        "RESULTATS SECOND PASS"
    )

    print("-" * 120)

    for key, value in (
        classifications.most_common()
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


if __name__ == "__main__":
    main()