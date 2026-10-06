# -*- coding: utf-8 -*-

"""
semantic_factual_third_pass.py
==============================

TRACE / SGCE - SEMANTIC FACTUAL THIRD PASS V1

Analyse uniquement les cas restant incertains après la Second Pass :

- PARTIAL_SUPPORT
- DOCUMENT_LEVEL_SUPPORT
- POTENTIAL_NEGATION_CONTRADICTION
- TEMPORALLY_AMBIGUOUS_NEGATION

Objectif :
1. approfondir la recherche documentaire pour les cas de support incomplet ;
2. vérifier la cohérence des relations avec une négation validée ;
3. distinguer :
       SUPPORTED_AFTER_DEEP_RECHECK
       COHERENT_WITH_NEGATION
       TEMPORALLY_COMPATIBLE
       EXPLICITLY_CONTRADICTED
       UNRESOLVED

IMPORTANT :
- absence de preuve != contradiction ;
- négation d'une entité != suppression automatique de toute relation ;
- "arrêt traitement" peut impliquer une administration antérieure ;
- seule une contradiction locale explicite peut être proposée
  comme candidat à une suppression ultérieure ;
- ce script ne modifie aucune donnée clinique.
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

INPUT_FILE = ROOT / "outputs" / "semantic_factual_second_pass_validated.json"
OUTPUT_FILE = ROOT / "outputs" / "semantic_factual_third_pass.json"

# ============================================================
# PARAMÈTRES
# ============================================================

# Fenêtre élargie pour la troisième passe.
DEEP_WINDOW = 1200

# Fenêtre plus stricte pour accepter une contradiction explicite.
NEGATION_WINDOW = 350

NEGATIVE_STATUSES = {
    "NEGATED",
    "ABSENT",
    "EXCLUDED",
    "RULED_OUT",
}

GENERIC_ENDPOINTS = {
    "",
    "patient",
    "le patient",
    "la patiente",
    "patient(e)",
    "sujet",
}


# ============================================================
# CUES
# ============================================================

NEGATION_CUES = [
    r"\bpas de\b",
    r"\babsence de\b",
    r"\babsent(?:e)?\b",
    r"\bsans\b",
    r"\baucun(?:e)?\b",
    r"\bnie\b",
    r"\bni[eé]e\b",
    r"\bexclu(?:e)?\b",
    r"\bnon retrouv[eé]e?\b",
    r"\bnon objectiv[eé]e?\b",
    r"\bnon pr[eé]sent(?:e)?\b",
    r"\bn[eé]gatif(?:ve)?\b",
]

STOP_TREATMENT_CUES = [
    r"\barr[eê]t\b",
    r"\barr[eê]t de\b",
    r"\barr[eê]t du\b",
    r"\barr[eê]t d[' ]",
    r"\bstopp[eé]\b",
    r"\bsuspendu(?:e)?\b",
    r"\bsuspension\b",
    r"\binterrompu(?:e)?\b",
    r"\binterruption\b",
]

HISTORICAL_CUES = [
    r"\bauparavant\b",
    r"\bpr[eé]c[eé]demment\b",
    r"\bant[eé]rieurement\b",
    r"\bavant\b",
    r"\bavait re[cç]u\b",
    r"\bavait [eé]t[eé] trait[eé]",
    r"\btraitement ant[eé]rieur\b",
]

ADMINISTRATION_CUES = [
    r"\badministr[eé]\b",
    r"\bre[cç]oit\b",
    r"\bre[cç]u\b",
    r"\btrait[eé] par\b",
    r"\bmis sous\b",
    r"\bintroduit\b",
    r"\bprescrit\b",
    r"\bdonn[eé]\b",
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
        .replace("×", " x ")
        .replace("✕", " x ")
        .replace("X", " x ")
        .replace("μ", "µ")
    )

    # Corrige quelques séquences fréquentes de mojibake
    # uniquement si elles existent.
    replacements = {
        "â€™": "'",
        "â€œ": '"',
        "â€": '"',
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
        r"(\d)(mg|g|kg|ml|mL|l|L|µg|ug|mmhg|kpa|%)\b",
        r"\1 \2",
        text,
        flags=re.I,
    )

    text = re.sub(
        r"\s*/\s*",
        "/",
        text,
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

    text = normalize_text(
        value
    )

    text = remove_accents(
        text
    )

    text = re.sub(
        r"[,:;()\[\]{}]",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# ============================================================
# ENDPOINTS
# ============================================================

def endpoint_candidates(item, side):

    """
    Construit plusieurs variantes pour SOURCE ou TARGET.

    Exemple :
        "Amiklin | antibiotique"
    devient :
        - amiklin
        - amiklin antibiotique
    """

    values = []

    for key in (
        f"{side}_text",
        f"{side}_proof",
    ):

        value = item.get(
            key
        )

        if value:
            values.append(
                str(value)
            )

    result = []

    seen = set()

    for value in values:

        normalized = normalize_relaxed(
            value
        )

        variants = [
            normalized
        ]

        if "|" in normalized:

            pieces = [
                x.strip()
                for x in normalized.split("|")
                if x.strip()
            ]

            variants.extend(
                pieces
            )

        for variant in variants:

            variant = re.sub(
                r"\s+",
                " ",
                variant,
            ).strip()

            if (
                not variant
                or variant in GENERIC_ENDPOINTS
                or variant in seen
            ):
                continue

            seen.add(
                variant
            )

            result.append(
                variant
            )

    # Les variantes longues d'abord.
    result.sort(
        key=len,
        reverse=True,
    )

    return result


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

    return (
        candidates[0]
        if candidates
        else None
    )


# ============================================================
# SEARCH
# ============================================================

def find_positions(
    text,
    variants,
):

    found = []

    for variant in variants:

        if not variant:
            continue

        start = 0

        while True:

            pos = text.find(
                variant,
                start,
            )

            if pos < 0:
                break

            found.append({
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

    # Déduplication
    unique = []

    seen = set()

    for x in found:

        key = (
            x["start"],
            x["end"],
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        unique.append(
            x
        )

    return unique


def best_pair(
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

            distance = abs(
                s["start"]
                - t["start"]
            )

            if (
                best is None
                or distance
                < best["distance"]
            ):

                best = {
                    "source":
                        s,

                    "target":
                        t,

                    "distance":
                        distance,
                }

    return best


def extract_context(
    text,
    pair,
    radius=250,
):

    if pair is None:
        return ""

    start = max(
        0,
        min(
            pair["source"]["start"],
            pair["target"]["start"],
        )
        - radius,
    )

    end = min(
        len(text),
        max(
            pair["source"]["end"],
            pair["target"]["end"],
        )
        + radius,
    )

    return text[
        start:end
    ]


def contains_any_pattern(
    text,
    patterns,
):

    for pattern in patterns:

        if re.search(
            pattern,
            text,
            flags=re.I,
        ):
            return True

    return False


# ============================================================
# DEEP SUPPORT
# ============================================================

def deep_support_analysis(
    item,
    document_text,
):

    source_variants = endpoint_candidates(
        item,
        "source",
    )

    target_variants = endpoint_candidates(
        item,
        "target",
    )

    source_positions = find_positions(
        document_text,
        source_variants,
    )

    target_positions = find_positions(
        document_text,
        target_variants,
    )

    pair = best_pair(
        source_positions,
        target_positions,
    )

    source_found = bool(
        source_positions
    )

    target_found = bool(
        target_positions
    )

    context = extract_context(
        document_text,
        pair,
        radius=350,
    )

    if (
        pair is not None
        and pair["distance"]
        <= DEEP_WINDOW
    ):

        return {
            "third_pass_classification":
                "SUPPORTED_AFTER_DEEP_RECHECK",

            "third_pass_confidence":
                0.97,

            "third_pass_reason":
                (
                    "Les endpoints ont été retrouvés "
                    "après recherche multi-variante "
                    "dans une fenêtre documentaire élargie."
                ),

            "source_variants":
                source_variants,

            "target_variants":
                target_variants,

            "source_found":
                source_found,

            "target_found":
                target_found,

            "minimum_distance":
                pair["distance"],

            "matched_source":
                pair["source"]["variant"],

            "matched_target":
                pair["target"]["variant"],

            "deep_context":
                context,
        }

    if (
        source_found
        and target_found
    ):

        return {
            "third_pass_classification":
                "UNRESOLVED",

            "third_pass_confidence":
                0.50,

            "third_pass_reason":
                (
                    "Les deux endpoints sont présents, "
                    "mais ils restent trop éloignés pour "
                    "démontrer automatiquement la relation."
                ),

            "source_variants":
                source_variants,

            "target_variants":
                target_variants,

            "source_found":
                True,

            "target_found":
                True,

            "minimum_distance":
                (
                    pair["distance"]
                    if pair
                    else None
                ),

            "deep_context":
                context,
        }

    return {
        "third_pass_classification":
            "UNRESOLVED",

        "third_pass_confidence":
            0.0,

        "third_pass_reason":
            (
                "Le support documentaire reste incomplet. "
                "L'absence de correspondance ne constitue "
                "pas une contradiction."
            ),

        "source_variants":
            source_variants,

        "target_variants":
            target_variants,

        "source_found":
            source_found,

        "target_found":
            target_found,

        "minimum_distance":
            None,

        "deep_context":
            "",
    }


# ============================================================
# NEGATION ANALYSIS
# ============================================================

def negation_analysis(
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

    source_negated = (
        source_status
        in NEGATIVE_STATUSES
    )

    target_negated = (
        target_status
        in NEGATIVE_STATUSES
    )

    source_variants = endpoint_candidates(
        item,
        "source",
    )

    target_variants = endpoint_candidates(
        item,
        "target",
    )

    source_positions = find_positions(
        document_text,
        source_variants,
    )

    target_positions = find_positions(
        document_text,
        target_variants,
    )

    pair = best_pair(
        source_positions,
        target_positions,
    )

    context = extract_context(
        document_text,
        pair,
        radius=NEGATION_WINDOW,
    )

    has_negation_cue = contains_any_pattern(
        context,
        NEGATION_CUES,
    )

    has_stop_cue = contains_any_pattern(
        context,
        STOP_TREATMENT_CUES,
    )

    has_historical_cue = contains_any_pattern(
        context,
        HISTORICAL_CUES,
    )

    has_administration_cue = contains_any_pattern(
        context,
        ADMINISTRATION_CUES,
    )

    # ========================================================
    # CAS 1 : arrêt d'un traitement
    # ========================================================

    if (
        relation
        == "traitement_administre_a"
        and source_negated
    ):

        if (
            has_stop_cue
            or has_historical_cue
            or has_administration_cue
        ):

            return {
                "third_pass_classification":
                    "TEMPORALLY_COMPATIBLE",

                "third_pass_confidence":
                    0.95,

                "third_pass_reason":
                    (
                        "Le contexte indique un arrêt, "
                        "une interruption ou une administration "
                        "temporellement antérieure. "
                        "La négation actuelle n'invalide donc "
                        "pas automatiquement la relation."
                    ),

                "local_context":
                    context,

                "negation_cue":
                    has_negation_cue,

                "stop_treatment_cue":
                    has_stop_cue,

                "historical_cue":
                    has_historical_cue,

                "administration_cue":
                    has_administration_cue,
            }

        return {
            "third_pass_classification":
                "UNRESOLVED",

            "third_pass_confidence":
                0.50,

            "third_pass_reason":
                (
                    "Le traitement est marqué négatif, "
                    "mais le contexte ne permet pas de "
                    "déterminer de façon sûre s'il s'agit "
                    "d'une absence ou d'un arrêt temporel."
                ),

            "local_context":
                context,

            "negation_cue":
                has_negation_cue,

            "stop_treatment_cue":
                has_stop_cue,

            "historical_cue":
                has_historical_cue,

            "administration_cue":
                has_administration_cue,
        }

    # ========================================================
    # CAS 2 : cible négatée
    # ========================================================

    if target_negated:

        # Pour parler de contradiction explicite :
        # - cible retrouvée ;
        # - contexte local ;
        # - cue négative ;
        # - proximité stricte.
        if (
            pair is not None
            and pair["distance"]
            <= NEGATION_WINDOW
            and has_negation_cue
        ):

            return {
                "third_pass_classification":
                    "EXPLICITLY_CONTRADICTED",

                "third_pass_confidence":
                    0.99,

                "third_pass_reason":
                    (
                        "La cible négatée est retrouvée "
                        "dans le contexte local de la relation "
                        "avec un marqueur explicite de négation."
                    ),

                "local_context":
                    context,

                "minimum_distance":
                    pair["distance"],

                "negation_cue":
                    True,

                "stop_treatment_cue":
                    has_stop_cue,

                "historical_cue":
                    has_historical_cue,

                "administration_cue":
                    has_administration_cue,
            }

        return {
            "third_pass_classification":
                "UNRESOLVED",

            "third_pass_confidence":
                0.50,

            "third_pass_reason":
                (
                    "La cible porte un statut négatif, "
                    "mais la contradiction relationnelle "
                    "n'est pas explicitement démontrée "
                    "dans le contexte local."
                ),

            "local_context":
                context,

            "negation_cue":
                has_negation_cue,
        }

    # ========================================================
    # CAS 3 : source négatée, autre relation
    # ========================================================

    if source_negated:

        if (
            pair is not None
            and pair["distance"]
            <= NEGATION_WINDOW
            and has_negation_cue
        ):

            return {
                "third_pass_classification":
                    "EXPLICITLY_CONTRADICTED",

                "third_pass_confidence":
                    0.99,

                "third_pass_reason":
                    (
                        "La source négatée est retrouvée "
                        "dans le contexte local avec un "
                        "marqueur explicite de négation."
                    ),

                "local_context":
                    context,

                "minimum_distance":
                    pair["distance"],

                "negation_cue":
                    True,
            }

        return {
            "third_pass_classification":
                "UNRESOLVED",

            "third_pass_confidence":
                0.50,

            "third_pass_reason":
                (
                    "La source est négatée mais la "
                    "contradiction avec la relation "
                    "n'est pas suffisamment démontrée."
                ),

            "local_context":
                context,

            "negation_cue":
                has_negation_cue,
        }

    # ========================================================
    # Aucun statut négatif exploitable
    # ========================================================

    return {
        "third_pass_classification":
            "COHERENT_WITH_NEGATION",

        "third_pass_confidence":
            0.90,

        "third_pass_reason":
            (
                "Aucun conflit explicite entre le statut "
                "des endpoints et la relation n'a été démontré."
            ),

        "local_context":
            context,

        "negation_cue":
            has_negation_cue,
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
        "validated",
        [],
    )

    # ========================================================
    # Seulement les 38 non résolus
    # ========================================================

    selected = [
        item
        for item in cases
        if item.get(
            "second_pass_final_status"
        )
        in {
            "REVIEW",
            "REVIEW_PRIORITY",
        }
    ]

    text_cache = {}

    results = []

    input_classes = Counter()
    output_classes = Counter()

    missing_text_documents = set()

    # ========================================================
    # ANALYSE
    # ========================================================

    for item in selected:

        second_class = (
            item.get(
                "second_pass_classification"
            )
            or "UNKNOWN"
        )

        input_classes[
            second_class
        ] += 1

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

                missing_text_documents.add(
                    document
                )

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

        # ----------------------------------------------------
        # Texte absent
        # ----------------------------------------------------

        if document_text is None:

            analysis = {
                "third_pass_classification":
                    "UNRESOLVED",

                "third_pass_confidence":
                    0.0,

                "third_pass_reason":
                    "Texte brut indisponible.",
            }

        # ----------------------------------------------------
        # Support documentaire
        # ----------------------------------------------------

        elif second_class in {
            "PARTIAL_SUPPORT",
            "DOCUMENT_LEVEL_SUPPORT",
        }:

            analysis = deep_support_analysis(
                item,
                document_text,
            )

        # ----------------------------------------------------
        # Négation
        # ----------------------------------------------------

        elif second_class in {
            "POTENTIAL_NEGATION_CONTRADICTION",
            "TEMPORALLY_AMBIGUOUS_NEGATION",
        }:

            analysis = negation_analysis(
                item,
                document_text,
            )

        # ----------------------------------------------------
        # Fallback
        # ----------------------------------------------------

        else:

            analysis = {
                "third_pass_classification":
                    "UNRESOLVED",

                "third_pass_confidence":
                    0.0,

                "third_pass_reason":
                    (
                        "Classe Second Pass non "
                        "prise en charge."
                    ),
            }

        row = {
            **item,
            **analysis,
        }

        results.append(
            row
        )

        output_classes[
            analysis[
                "third_pass_classification"
            ]
        ] += 1

    # ========================================================
    # OUTPUT
    # ========================================================

    output = {

        "analyzer":
            "semantic_factual_third_pass",

        "mode":
            "TARGETED_DEEP_RECHECK_AND_NEGATION_CONSISTENCY",

        "summary": {

            "second_pass_cases_received":
                len(cases),

            "cases_selected":
                len(selected),

            "input_classifications":
                dict(input_classes),

            "third_pass_classifications":
                dict(output_classes),

            "documents_text_missing":
                len(
                    missing_text_documents
                ),
        },

        "third_pass":
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
        "SEMANTIC FACTUAL THIRD PASS V1"
    )

    print("=" * 120)

    print(
        f"Cas Second Pass reçus               : "
        f"{len(cases)}"
    )

    print(
        f"Cas sélectionnés                    : "
        f"{len(selected)}"
    )

    print(
        f"Documents texte manquants           : "
        f"{len(missing_text_documents)}"
    )

    print()

    print(
        "CLASSIFICATIONS EN ENTREE"
    )

    print("-" * 120)

    for key, value in (
        input_classes.most_common()
    ):
        print(
            f"{key:<60}: {value}"
        )

    print()

    print(
        "RESULTATS THIRD PASS"
    )

    print("-" * 120)

    for key, value in (
        output_classes.most_common()
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
    