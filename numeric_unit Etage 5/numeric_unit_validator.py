# -*- coding: utf-8 -*-

"""
numeric_unit_validator.py
=========================

TRACE / SGCE
NUMERIC UNIT VALIDATOR - V7 CONTEXT-AWARE CONSERVATIVE SEMANTIC UNIT GUARD

Objectif
--------
Valider de manière conservatrice les candidats produits par :

    numeric_unit_candidate_builder.py

Principes
---------
1. Priorité à la valeur brute de l'entité.
2. Les unités composites sont reconnues AVANT les unités simples.
3. Une correction automatique n'est acceptée que si la valeur et
   l'unité sont explicitement démontrées.
4. Une expression "dose + fréquence" comme :

       40 mg 1/j
       500 mg 1/j

   n'est PAS transformée automatiquement en mg/j.

5. Une unité brute "G" majuscule n'est PAS automatiquement
   interprétée comme gramme.

6. Un volume >= 100 L est considéré comme suffisamment inhabituel
   pour nécessiter REVIEW.

7. Aucun JSON clinique n'est modifié par ce script.

Entrée
------
MultiAgent/numeric_unit/queues/numeric_unit_candidates.json

Sortie
------
MultiAgent/numeric_unit/outputs/numeric_unit_validated.json
"""

import json
import re
from pathlib import Path
from collections import Counter


# =====================================================================
# PATHS
# =====================================================================

ROOT = Path(__file__).resolve().parent
INPUT_FILE = ROOT / "queues" / "numeric_unit_candidates.json"
OUTPUT_FILE = ROOT / "outputs" / "numeric_unit_validated.json"
OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)


# =====================================================================
# BASIC HELPERS
# =====================================================================

def load_json(path):
    with Path(path).open(
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


def save_json(path, payload):
    path = Path(path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def normalize_spaces(value):
    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value),
    ).strip()


def normalize_decimal(value):
    if value is None:
        return None

    value = str(value).strip()
    value = value.replace(",", ".")

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# =====================================================================
# UNIT CANONICALIZATION
# =====================================================================

UNIT_ALIASES = {

    # ---------------------------------------------------------
    # MASS
    # ---------------------------------------------------------

    "mg": "mg",

    "µg": "µg",
    "μg": "µg",
    "ug": "µg",
    "mcg": "µg",

    "g": "g",

    # ---------------------------------------------------------
    # VOLUME
    # ---------------------------------------------------------

    "ml": "mL",
    "mL": "mL",

    "l": "L",
    "L": "L",

    # ---------------------------------------------------------
    # TIME COMPOSITES
    # ---------------------------------------------------------

    "mg/h": "mg/h",
    "mg /h": "mg/h",
    "mg/ h": "mg/h",
    "mg / h": "mg/h",

    "µg/h": "µg/h",
    "µg /h": "µg/h",
    "µg/ h": "µg/h",
    "µg / h": "µg/h",

    "μg/h": "µg/h",
    "ug/h": "µg/h",
    "mcg/h": "µg/h",

    "g/h": "g/h",

    "ml/h": "mL/h",
    "mL/h": "mL/h",

    "l/h": "L/h",
    "L/h": "L/h",

    # ---------------------------------------------------------
    # PER DAY
    # ---------------------------------------------------------

    "mg/j": "mg/j",
    "mg/jour": "mg/j",

    "µg/j": "µg/j",
    "μg/j": "µg/j",
    "ug/j": "µg/j",
    "mcg/j": "µg/j",

    "g/j": "g/j",
    "g/jour": "g/j",

    "ml/j": "mL/j",
    "ml / j": "mL/j",
    "ml/jour": "mL/j",
    "ml / jour": "mL/j",

    "mL/j": "mL/j",

    "l/j": "L/j",
    "L/j": "L/j",

    # ---------------------------------------------------------
    # PER 24 HOURS
    # ---------------------------------------------------------

    "mg/24h": "mg/24h",
    "mg/24H": "mg/24h",

    "µg/24h": "µg/24h",
    "μg/24h": "µg/24h",
    "ug/24h": "µg/24h",
    "mcg/24h": "µg/24h",

    "g/24h": "g/24h",
    "g/24H": "g/24h",

    "ml/24h": "mL/24h",
    "mL/24h": "mL/24h",

    "l/24h": "L/24h",
    "L/24h": "L/24h",

    # ---------------------------------------------------------
    # FLOW
    # ---------------------------------------------------------

    "l/min": "L/min",
    "L/min": "L/min",

    "ml/min": "mL/min",
    "mL/min": "mL/min",

    "mg/min": "mg/min",

    # ---------------------------------------------------------
    # LAB
    # ---------------------------------------------------------

    "mmol/l": "mmol/L",
    "mmol/L": "mmol/L",

    "mg/l": "mg/L",
    "mg/L": "mg/L",

    "µg/l": "µg/L",
    "µg/L": "µg/L",

    "ug/l": "µg/L",
    "ug/L": "µg/L",

    "g/l": "g/L",
    "g/L": "g/L",

    "mg/dl": "mg/dL",
    "mg/dL": "mg/dL",

    "g/dl": "g/dL",
    "g/dL": "g/dL",

    # ---------------------------------------------------------
    # OTHER
    # ---------------------------------------------------------

    "%": "%",
    "°c": "°C",
    "°C": "°C",

    "mmhg": "mmHg",
    "mmHg": "mmHg",

    "kpa": "kPa",
    "kPa": "kPa",

    "ui": "UI",
    "UI": "UI",

    "bpm": "bpm",
}


def canonical_unit(raw_unit):
    if raw_unit in (
        None,
        "",
    ):
        return None

    raw = str(raw_unit).strip()

    # Important:
    # garder la casse originale disponible pour les guards.
    compact = re.sub(
        r"\s*\/\s*",
        "/",
        raw,
    )

    compact = re.sub(
        r"/\s*24\s*[hH]",
        "/24h",
        compact,
    )

    compact = re.sub(
        r"/(?:jour|jours)$",
        "/j",
        compact,
        flags=re.IGNORECASE,
    )

    # recherche exacte d'abord
    if compact in UNIT_ALIASES:
        return UNIT_ALIASES[compact]

    # recherche normalisée
    lower = compact.lower()

    lower_aliases = {
        str(k).lower(): v
        for k, v in UNIT_ALIASES.items()
    }

    return lower_aliases.get(
        lower
    )


# =====================================================================
# UNIT REGEX
# =====================================================================

# IMPORTANT :
# unités composites AVANT les unités simples.

UNIT_PATTERN = r"""
(?:
    [µμu]g\s*/\s*kg\s*/\s*min
    |
    mcg\s*/\s*kg\s*/\s*min

    |
    [µμu]g\s*/\s*24\s*[hH]
    |
    mcg\s*/\s*24\s*[hH]
    |
    mg\s*/\s*24\s*[hH]
    |
    g\s*/\s*24\s*[hH]
    |
    m[lL]\s*/\s*24\s*[hH]
    |
    [lL]\s*/\s*24\s*[hH]

    |
    [µμu]g\s*/\s*(?:j|jour)
    |
    mcg\s*/\s*(?:j|jour)
    |
    mg\s*/\s*(?:j|jour)
    |
    g\s*/\s*(?:j|jour)
    |
    m[lL]\s*/\s*(?:j|jour)
    |
    [lL]\s*/\s*(?:j|jour)

    |
    [µμu]g\s*/\s*h
    |
    mcg\s*/\s*h
    |
    mg\s*/\s*h
    |
    g\s*/\s*h
    |
    m[lL]\s*/\s*h
    |
    [lL]\s*/\s*h

    |
    mg\s*/\s*min
    |
    m[lL]\s*/\s*min
    |
    [lL]\s*/\s*min

    |
    mmol\s*/\s*[lL]
    |
    mg\s*/\s*[lL]
    |
    [µμu]g\s*/\s*[lL]
    |
    mcg\s*/\s*[lL]
    |
    g\s*/\s*[lL]

    |
    mg\s*/\s*d[lL]
    |
    g\s*/\s*d[lL]

    |
    mmHg
    |
    kPa
    |
    bpm
    |
    °C
    |
    °c
    |
    %
    |
    UI

    |
    mL
    |
    ml
    |
    mg
    |
    µg
    |
    μg
    |
    ug
    |
    mcg
    |
    g
    |
    G
    |
    L
    |
    l
)
"""


VALUE_UNIT_RE = re.compile(
    rf"""
    (?<![\w.])
    (?P<value>
        [-+]?
        \d+
        (?:[.,]\d+)?
    )
    \s*
    (?P<unit>
        {UNIT_PATTERN}
    )
    (?!\w)
    """,
    re.IGNORECASE | re.VERBOSE,
)


# =====================================================================
# DOSE + FREQUENCY GUARD
# =====================================================================

DOSE_FREQUENCY_RE = re.compile(
    r"""
    (?<!\w)

    (?P<value>
        \d+(?:[.,]\d+)?
    )

    \s*

    (?P<unit>
        mg
        |
        g
        |
        µg
        |
        μg
        |
        ug
        |
        mcg
        |
        mL
        |
        ml
        |
        L
        |
        l
    )

    \s+

    (?P<frequency>
        \d+
        \s*
        /
        \s*
        (?:
            j
            |
            jour
            |
            24\s*[hH]
        )
    )

    (?!\w)
    """,
    re.IGNORECASE | re.VERBOSE,
)


def detect_dose_frequency(text):
    """
    Exemples bloqués :

        40 mg 1/j
        500 mg 1/j

    Ce n'est PAS équivalent automatiquement à :

        40 mg/j
        500 mg/j
    """

    if not text:
        return None

    match = DOSE_FREQUENCY_RE.search(
        str(text)
    )

    if not match:
        return None

    return {
        "value":
            match.group("value"),

        "unit":
            match.group("unit"),

        "frequency":
            match.group("frequency"),

        "matched_text":
            match.group(0),
    }


# =====================================================================
# EXTRACT VALUE + UNIT
# =====================================================================

def extract_value_unit(text):
    if not text:
        return None

    match = VALUE_UNIT_RE.search(
        str(text)
    )

    if not match:
        return None

    value_raw = match.group(
        "value"
    )

    raw_unit = match.group(
        "unit"
    )

    numeric_value = normalize_decimal(
        value_raw
    )

    unit = canonical_unit(
        raw_unit
    )

    if (
        numeric_value is None
        or unit is None
    ):
        return None

    return {
        "value":
            value_raw,

        "numeric_value":
            numeric_value,

        "unit":
            unit,

        "raw_unit":
            raw_unit,

        "start":
            match.start(),

        "end":
            match.end(),

        "matched_text":
            match.group(0),
    }




def extract_all_value_units(text):
    """Retourne toutes les expressions valeur+unité valides d'un texte."""
    out = []
    if not text:
        return out
    for match in VALUE_UNIT_RE.finditer(str(text)):
        value_raw = match.group("value")
        raw_unit = match.group("unit")
        numeric_value = normalize_decimal(value_raw)
        unit = canonical_unit(raw_unit)
        if numeric_value is None or unit is None:
            continue
        out.append({
            "value": value_raw, "numeric_value": numeric_value,
            "unit": unit, "raw_unit": raw_unit,
            "start": match.start(), "end": match.end(),
            "matched_text": match.group(0),
        })
    return out


def evidence_strength(source_name):
    return {"RAW_VALUE": 5, "ENTITY_TEXT": 4, "SENTENCE": 3,
            "PREVIOUS_SENTENCE": 1, "NEXT_SENTENCE": 1}.get(source_name, 0)

# =====================================================================
# CANDIDATE ACCESS
# =====================================================================

def first_value(item, keys):
    for key in keys:
        value = item.get(key)

        if value not in (
            None,
            "",
        ):
            return value

    return None


def candidate_raw_value(item):
    """
    RAW VALUE PRIORITY.

    On cherche d'abord la valeur brute réellement portée
    par l'entité avant d'utiliser la preuve/context.
    """

    return first_value(
        item,
        (
            "raw_value",
            "current_value",
            "entity_value",
            "valeur",
            "value",
        ),
    )


def candidate_current_unit(item):
    return first_value(
        item,
        (
            "current_unit",
            "entity_unit",
            "unite",
            "unit",
        ),
    )


def candidate_entity_text(item):
    return first_value(
        item,
        (
            "entity_text",
            "text",
            "entity_name",
            "mention",
            "preuve",
        ),
    )


def candidate_sentence(item):
    return first_value(
        item,
        (
            "sentence",
            "context_sentence",
            "local_context",
            "context",
        ),
    )


def candidate_previous_sentence(item):
    return first_value(
        item,
        (
            "previous_sentence",
            "previous_context",
        ),
    )


def candidate_next_sentence(item):
    return first_value(
        item,
        (
            "next_sentence",
            "next_context",
        ),
    )


# =====================================================================
# EVIDENCE SELECTION
# =====================================================================

def evidence_sources(item):
    """
    Ordre volontairement conservateur :

    1. valeur brute
    2. texte de l'entité
    3. phrase locale
    4. phrase précédente
    5. phrase suivante
    """

    sources = []

    values = [
        (
            "RAW_VALUE",
            candidate_raw_value(item),
        ),
        (
            "ENTITY_TEXT",
            candidate_entity_text(item),
        ),
        (
            "SENTENCE",
            candidate_sentence(item),
        ),
        (
            "PREVIOUS_SENTENCE",
            candidate_previous_sentence(item),
        ),
        (
            "NEXT_SENTENCE",
            candidate_next_sentence(item),
        ),
    ]

    seen = set()

    for source_name, value in values:
        if value in (
            None,
            "",
        ):
            continue

        text = str(value).strip()

        if not text:
            continue

        if text in seen:
            continue

        seen.add(text)

        sources.append(
            (
                source_name,
                text,
            )
        )

    return sources


# =====================================================================
# SAFETY GUARDS
# =====================================================================

def ambiguous_unit_guard(evidence):
    """
    Bloque les cas lexicalement détectés mais trop ambigus
    pour une correction automatique.
    """

    if not isinstance(
        evidence,
        dict,
    ):
        return None

    raw_unit = str(
        evidence.get(
            "raw_unit"
        )
        or ""
    ).strip()

    value = evidence.get(
        "numeric_value"
    )

    # ---------------------------------------------------------
    # 1. G majuscule
    # ---------------------------------------------------------

    if raw_unit == "G":
        return {
            "status":
                "REVIEW",

            "action":
                "NONE",

            "reason":
                (
                    "Unité brute 'G' majuscule ambiguë : "
                    "conversion automatique vers gramme interdite."
                ),
        }

    # ---------------------------------------------------------
    # 2. Très grand volume en litres
    # ---------------------------------------------------------

    if (
        raw_unit.lower() == "l"
        and value is not None
        and value >= 100
    ):
        return {
            "status":
                "REVIEW",

            "action":
                "NONE",

            "reason":
                (
                    "Volume >= 100 L : valeur suffisamment "
                    "inhabituelle pour exiger une validation "
                    "contextuelle."
                ),
        }

    return None



# =====================================================================
# COMPETING VALUE + UNIT EXPRESSIONS GUARD
# =====================================================================

def detect_competing_value_unit_expressions(raw_value):
    """
    Détecte plusieurs expressions valeur+unité concurrentes dans
    LA MEME valeur brute.

    REVIEW :
        2g 2g /24H
        3g 3g/24H
        10mg 10mg /h
        300 µg 300 µg /h
        10 mg 10 mg/h
        500 mg 500 mg/h

    Non bloqué :
        2g/24H
        300 µg/h
        500 mg
    """
    if raw_value is None or not isinstance(raw_value, str):
        return False, []

    text_value = raw_value.strip()
    if not text_value:
        return False, []

    expressions = []

    for match in VALUE_UNIT_RE.finditer(text_value):
        value_raw = match.group("value")
        raw_unit = match.group("unit")

        numeric_value = normalize_decimal(value_raw)
        unit = canonical_unit(raw_unit)

        if numeric_value is None or unit is None:
            continue

        expressions.append({
            "value": numeric_value,
            "unit": unit,
            "raw_unit": raw_unit,
            "matched_text": match.group(0).strip(),
            "start": match.start(),
            "end": match.end(),
        })

    if len(expressions) < 2:
        return False, expressions

    by_value = {}

    for expression in expressions:
        key = round(float(expression["value"]), 9)
        by_value.setdefault(key, []).append(expression)

    competing = []

    for group in by_value.values():
        units = {
            expression["unit"]
            for expression in group
            if expression.get("unit")
        }

        if len(units) >= 2:
            competing.extend(group)

    return bool(competing), competing

# =====================================================================
# EVIDENCE FINDER
# =====================================================================

def find_best_evidence(item):
    """
    V7: sélectionne la preuve la mieux ancrée au lieu de prendre la
    première mesure numérique de la phrase.

    Priorités sûres : RAW_VALUE > ENTITY_TEXT > SENTENCE > voisinage.
    Si la valeur JSON est numérique, une expression portant exactement
    cette valeur est préférée. Les unités incompatibles avec un paramètre
    connu ne peuvent pas devenir la meilleure preuve.
    """
    # Dose + fréquence : garde conservateur inchangé pour les sources fortes.
    for source_name, text in evidence_sources(item):
        if source_name not in {"RAW_VALUE", "ENTITY_TEXT"}:
            continue
        dose_frequency = detect_dose_frequency(text)
        if dose_frequency:
            return {"kind": "DOSE_FREQUENCY", "source": source_name,
                    "text": text, "dose_frequency": dose_frequency}

    current = candidate_raw_value(item)
    current_num = normalize_decimal(current)
    candidates = []
    for source_name, text in evidence_sources(item):
        for ev in extract_all_value_units(text):
            ev = {**ev, "source": source_name}
            semantic_problem = semantic_parameter_unit_guard(item, ev["unit"])
            compatible = semantic_problem is None
            value_match = current_num is not None and numeric_equal(current_num, ev["numeric_value"])
            score = evidence_strength(source_name) * 10
            if value_match:
                score += 100
            if compatible:
                score += 20
            else:
                score -= 100
            candidates.append((score, value_match, compatible, ev))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    best = candidates[0]

    # Une preuve contextuelle qui ne correspond pas à une valeur JSON déjà
    # numérique n'est jamais utilisée pour écraser/réparer cette valeur.
    if current_num is not None and not best[1]:
        return {"kind": "VALUE_CONFLICT", "evidence": best[3],
                "alternatives": [x[3] for x in candidates[:5]]}

    return {"kind": "VALUE_UNIT", "evidence": best[3],
            "evidence_score": best[0],
            "evidence_strength": evidence_strength(best[3]["source"]),
            "alternatives": [x[3] for x in candidates[1:5]]}


# =====================================================================
# VALUE COMPARISON
# =====================================================================

def numeric_equal(a, b, tolerance=1e-9):
    a_num = normalize_decimal(a)
    b_num = normalize_decimal(b)

    if (
        a_num is None
        or b_num is None
    ):
        return False

    return abs(
        a_num - b_num
    ) <= tolerance


def raw_value_is_numeric(value):
    if value in (
        None,
        "",
    ):
        return False

    return normalize_decimal(
        value
    ) is not None


# =====================================================================
# SEMANTIC / PARAMETER UNIT SAFETY GUARD
# =====================================================================

# High-confidence unit constraints for explicitly named physiologic parameters.
# This is intentionally conservative: it only blocks impossible unit assignments;
# it never invents a replacement value/unit.
PARAMETER_ALLOWED_UNITS = {
    "pression_arterielle_systolique": {"mmHg", "kPa"},
    "pression_arterielle_diastolique": {"mmHg", "kPa"},
    "pression_arterielle_moyenne": {"mmHg", "kPa"},
    "pas": {"mmHg", "kPa"},
    "pad": {"mmHg", "kPa"},
    "pam": {"mmHg", "kPa"},
    "temperature": {"°C"},
    "temperature_corporelle": {"°C"},
    "spo2": {"%"},
    "sao2": {"%"},
    "frequence_cardiaque": {"bpm", "/min"},
    "frequence_respiratoire": {"cycles/min", "/min"},
}

def normalize_parameter_name(value):
    if value is None:
        return ""
    value = str(value).strip().lower()
    value = value.replace("-", "_").replace(" ", "_")
    value = re.sub(r"_+", "_", value)
    return value

def candidate_parameter(item):
    return first_value(
        item,
        (
            "parameter",
            "parametre",
            "entity_parameter",
            "parameter_name",
        ),
    )

def semantic_parameter_unit_guard(item, proposed_unit):
    """
    Bloque uniquement les unités explicitement incompatibles avec un
    paramètre dont la contrainte d'unité est connue avec forte confiance.

    Exemple :
        pression_arterielle_systolique + mg -> REVIEW

    Le garde ne transforme jamais mg en mmHg automatiquement.
    """
    parameter = normalize_parameter_name(candidate_parameter(item))
    if not parameter:
        return None

    allowed = PARAMETER_ALLOWED_UNITS.get(parameter)
    if not allowed:
        return None

    canonical = canonical_unit(proposed_unit)
    if canonical is None:
        return None

    if canonical not in allowed:
        return {
            "status": "REVIEW",
            "action": "NONE",
            "reason": (
                f"Unité '{canonical}' incompatible avec le paramètre "
                f"'{parameter}'. Un rattachement numérique/contextuel "
                "ne suffit pas pour une correction automatique."
            ),
            "safety_guard": "PARAMETER_UNIT_SEMANTIC_MISMATCH",
            "allowed_units": sorted(allowed),
        }

    return None


# =====================================================================
# VALIDATION
# =====================================================================

def validate_candidate(item):
    """
    Produit :

        SAFE_ACCEPT
        REVIEW

    Actions possibles :

        SET_UNIT
        SET_VALUE_AND_UNIT
        NONE
    """

    result = {
        **item,
    }

    current_value = candidate_raw_value(
        item
    )

    current_unit = candidate_current_unit(
        item
    )

    # =========================================================
    # COMPETING VALUE + UNIT EXPRESSIONS
    # =========================================================
    has_competing, competing_expressions = (
        detect_competing_value_unit_expressions(
            current_value
        )
    )

    if has_competing:
        result.update({
            "status":
                "REVIEW",

            "action":
                "NONE",

            "validated_value":
                None,

            "validated_unit":
                None,

            "validated_evidence":
                None,

            "validation_reason":
                (
                    "Plusieurs expressions valeur+unité concurrentes "
                    "sont présentes dans la valeur brute de l'entité."
                ),

            "safety_guard":
                "COMPETING_VALUE_UNIT_EXPRESSIONS",

            "competing_expressions":
                competing_expressions,
        })

        return result

    evidence_result = find_best_evidence(
        item
    )

    # =========================================================
    # NO EVIDENCE
    # =========================================================

    if evidence_result is None:
        result.update({
            "status":
                "REVIEW",

            "action":
                "NONE",

            "validated_value":
                None,

            "validated_unit":
                None,

            "validated_evidence":
                None,

            "validation_reason":
                (
                    "Aucune preuve textuelle explicite et "
                    "non ambiguë de valeur + unité."
                ),
        })

        return result

    # =========================================================
    # DOSE + FREQUENCY
    # =========================================================

    if evidence_result.get("kind") == "VALUE_CONFLICT":
        evidence = evidence_result.get("evidence")
        result.update({
            "status": "REVIEW", "action": "NONE",
            "validated_value": None, "validated_unit": None,
            "validated_evidence": evidence,
            "review_category": "JSON_TEXT_CONFLICT",
            "validation_reason": (
                "La valeur JSON ne correspond à aucune preuve valeur+unité "
                "suffisamment ancrée ; correction automatique interdite."
            ),
            "evidence_alternatives": evidence_result.get("alternatives", []),
        })
        return result

    if (
        evidence_result.get("kind")
        == "DOSE_FREQUENCY"
    ):
        dose_frequency = evidence_result[
            "dose_frequency"
        ]

        result.update({
            "status":
                "REVIEW",

            "action":
                "NONE",

            "validated_value":
                None,

            "validated_unit":
                None,

            "validated_evidence": {
                "source":
                    evidence_result.get(
                        "source"
                    ),

                "matched_text":
                    dose_frequency.get(
                        "matched_text"
                    ),

                "dose_value":
                    dose_frequency.get(
                        "value"
                    ),

                "dose_unit":
                    dose_frequency.get(
                        "unit"
                    ),

                "frequency":
                    dose_frequency.get(
                        "frequency"
                    ),
            },

            "validation_reason":
                (
                    "Expression dose + fréquence détectée. "
                    "La fréquence ne doit pas être fusionnée "
                    "automatiquement avec l'unité."
                ),
        })

        return result

    # =========================================================
    # VALUE + UNIT
    # =========================================================

    evidence = evidence_result["evidence"]
    result["evidence_strength"] = evidence_result.get("evidence_strength")
    result["evidence_alternatives"] = evidence_result.get("alternatives", [])

    guard = ambiguous_unit_guard(
        evidence
    )

    if guard is not None:
        result.update({
            "status":
                guard["status"],

            "action":
                guard["action"],

            "validated_value":
                None,

            "validated_unit":
                None,

            "validated_evidence":
                evidence,

            "validation_reason":
                guard["reason"],
        })

        return result

    proposed_value = evidence[
        "numeric_value"
    ]

    proposed_unit = evidence[
        "unit"
    ]

    # =========================================================
    # SEMANTIC / PARAMETER UNIT GUARD
    # =========================================================
    semantic_problem = semantic_parameter_unit_guard(
        item,
        proposed_unit,
    )

    if semantic_problem is not None:
        result.update({
            "status": "REVIEW",
            "action": "NONE",
            "validated_value": None,
            "validated_unit": None,
            "validated_evidence": evidence,
            "validation_reason": semantic_problem["reason"],
            "safety_guard": semantic_problem["safety_guard"],
            "allowed_units": semantic_problem.get("allowed_units", []),
        })
        return result

    # =========================================================
    # CURRENT VALUE ALREADY NUMERIC
    # =========================================================

    if raw_value_is_numeric(
        current_value
    ):

        if not numeric_equal(
            current_value,
            proposed_value,
        ):
            result.update({
                "status":
                    "REVIEW",

                "action":
                    "NONE",

                "validated_value":
                    None,

                "validated_unit":
                    None,

                "validated_evidence":
                    evidence,

                "validation_reason":
                    (
                        "La valeur numérique du JSON ne correspond "
                        "pas à la valeur de la preuve textuelle."
                    ),
            })

            return result

        # -----------------------------------------------------
        # UNIT MISSING
        # -----------------------------------------------------

        if current_unit in (
            None,
            "",
        ):
            result.update({
                "status":
                    "SAFE_ACCEPT",

                "action":
                    "SET_UNIT",

                "validated_value":
                    proposed_value,

                "validated_unit":
                    proposed_unit,

                "validated_evidence":
                    evidence,

                "validation_reason":
                    (
                        "Valeur numérique déjà correcte et unité "
                        "explicitement démontrée par la preuve."
                    ),
            })

            return result

        current_canonical = canonical_unit(
            current_unit
        )

        # -----------------------------------------------------
        # SAME UNIT
        # -----------------------------------------------------

        if (
            current_canonical
            == proposed_unit
        ):
            result.update({
                "status":
                    "REVIEW",

                "action":
                    "NONE",

                "validated_value":
                    proposed_value,

                "validated_unit":
                    proposed_unit,

                "validated_evidence":
                    evidence,

                "validation_reason":
                    (
                        "Valeur et unité déjà cohérentes ; "
                        "aucune correction nécessaire."
                    ),
            })

            return result

        # -----------------------------------------------------
        # CONFLICTING UNIT
        # -----------------------------------------------------

        result.update({
            "status":
                "REVIEW",

            "action":
                "NONE",

            "validated_value":
                None,

            "validated_unit":
                None,

            "validated_evidence":
                evidence,

            "validation_reason":
                (
                    "Conflit entre l'unité existante et l'unité "
                    "détectée dans le texte."
                ),
        })

        return result

    # =========================================================
    # CURRENT VALUE NON-NUMERIC
    # =========================================================

    current_text = normalize_spaces(
        current_value
    )

    if not current_text:
        current_text = normalize_spaces(
            candidate_entity_text(item)
        )

    # ---------------------------------------------------------
    # Require value to actually be grounded in raw/entity text
    # ---------------------------------------------------------

    direct_evidence = extract_value_unit(
        current_text
    )

    if direct_evidence is None:
        result.update({
            "status":
                "REVIEW",

            "action":
                "NONE",

            "validated_value":
                None,

            "validated_unit":
                None,

            "validated_evidence":
                evidence,

            "validation_reason":
                (
                    "La preuve valeur+unité provient du contexte "
                    "mais n'est pas suffisamment ancrée dans "
                    "la valeur brute de l'entité."
                ),
        })

        return result

    # ---------------------------------------------------------
    # Apply guards AGAIN on raw direct evidence
    # ---------------------------------------------------------

    direct_guard = ambiguous_unit_guard(
        direct_evidence
    )

    if direct_guard is not None:
        result.update({
            "status":
                "REVIEW",

            "action":
                "NONE",

            "validated_value":
                None,

            "validated_unit":
                None,

            "validated_evidence":
                direct_evidence,

            "validation_reason":
                direct_guard["reason"],
        })

        return result

    # ---------------------------------------------------------
    # Raw value and evidence must agree
    # ---------------------------------------------------------

    if not numeric_equal(
        direct_evidence["numeric_value"],
        proposed_value,
    ):
        result.update({
            "status":
                "REVIEW",

            "action":
                "NONE",

            "validated_value":
                None,

            "validated_unit":
                None,

            "validated_evidence":
                evidence,

            "validation_reason":
                (
                    "La valeur numérique de l'entité et celle "
                    "de la preuve ne correspondent pas."
                ),
        })

        return result

    if (
        direct_evidence["unit"]
        != proposed_unit
    ):
        result.update({
            "status":
                "REVIEW",

            "action":
                "NONE",

            "validated_value":
                None,

            "validated_unit":
                None,

            "validated_evidence":
                evidence,

            "validation_reason":
                (
                    "L'unité de la valeur brute et l'unité "
                    "de la preuve contextuelle divergent."
                ),
        })

        return result

    # ---------------------------------------------------------
    # Existing unit compatibility
    # ---------------------------------------------------------

    if current_unit not in (
        None,
        "",
    ):
        current_canonical = canonical_unit(
            current_unit
        )

        if (
            current_canonical is not None
            and current_canonical
            != proposed_unit
        ):
            result.update({
                "status":
                    "REVIEW",

                "action":
                    "NONE",

                "validated_value":
                    None,

                "validated_unit":
                    None,

                "validated_evidence":
                    evidence,

                "validation_reason":
                    (
                        "L'unité existante est incompatible avec "
                        "l'unité explicitement détectée."
                    ),
            })

            return result

    # =========================================================
    # SAFE VALUE + UNIT NORMALIZATION
    # =========================================================

    result.update({
        "status":
            "SAFE_ACCEPT",

        "action":
            "SET_VALUE_AND_UNIT",

        "validated_value":
            proposed_value,

        "validated_unit":
            proposed_unit,

        "validated_evidence":
            evidence,

        "validation_reason":
            (
                "Valeur et unité explicitement présentes dans "
                "la valeur brute et confirmées sans ambiguïté."
            ),
    })

    return result


# =====================================================================
# INPUT FORMAT
# =====================================================================

def extract_candidates(payload):
    """
    Accepte les deux formats :

        [...]
    ou
        {"candidates": [...]}
    """

    if isinstance(
        payload,
        list,
    ):
        return payload

    if isinstance(
        payload,
        dict,
    ):
        candidates = payload.get(
            "candidates"
        )

        if isinstance(
            candidates,
            list,
        ):
            return candidates

    return []


# =====================================================================
# MAIN
# =====================================================================

def main():

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Fichier candidats introuvable : {INPUT_FILE}"
        )

    payload = load_json(
        INPUT_FILE
    )

    candidates = extract_candidates(
        payload
    )

    validated = []

    status_counts = Counter()
    action_counts = Counter()
    unit_counts = Counter()
    review_reasons = Counter()

    for candidate in candidates:

        try:
            result = validate_candidate(
                candidate
            )

        except Exception as exc:
            result = {
                **candidate,

                "status":
                    "REVIEW",

                "action":
                    "NONE",

                "validated_value":
                    None,

                "validated_unit":
                    None,

                "validated_evidence":
                    None,

                "validation_reason":
                    f"Erreur validation : {exc}",
            }

        validated.append(
            result
        )

        status = result.get(
            "status",
            "REVIEW",
        )

        action = result.get(
            "action",
            "NONE",
        )

        status_counts[
            status
        ] += 1

        action_counts[
            action
        ] += 1

        if (
            status == "SAFE_ACCEPT"
            and result.get(
                "validated_unit"
            )
        ):
            unit_counts[
                result[
                    "validated_unit"
                ]
            ] += 1

        if status == "REVIEW":
            reason = result.get(
                "validation_reason",
                "UNKNOWN",
            )

            review_reasons[
                reason
            ] += 1

    output = {
        "validator":
            "numeric_unit_validator",

        "version":
            "V6_CONSERVATIVE_SEMANTIC_UNIT_GUARD",

        "source":
            str(INPUT_FILE),

        "summary": {
            "candidates_received":
                len(candidates),

            "status_counts":
                dict(status_counts),

            "action_counts":
                dict(action_counts),

            "validated_units":
                dict(unit_counts),

            "review_reason_counts":
                dict(review_reasons),
        },

        "validated":
            validated,
    }

    save_json(
        OUTPUT_FILE,
        output,
    )

    print("=" * 112)
    print(
        "TRACE / SGCE - NUMERIC UNIT VALIDATOR "
        "- V7 CONTEXT-AWARE CONSERVATIVE SEMANTIC UNIT GUARD"
    )
    print("=" * 112)

    print(
        f"Candidats reçus                    : {len(candidates)}"
    )

    print()
    print("STATUTS")
    print("-" * 112)

    for key, value in status_counts.items():
        print(
            f"{key:<52}: {value}"
        )

    print()
    print("ACTIONS SURES")
    print("-" * 112)

    for key, value in action_counts.items():
        print(
            f"{key:<52}: {value}"
        )

    print()
    print("UNITES VALIDEES")
    print("-" * 112)

    for key, value in unit_counts.items():
        print(
            f"{key:<52}: {value}"
        )

    print()
    print("RAISONS REVIEW")
    print("-" * 112)

    # Afficher seulement les raisons existantes.
    for key, value in review_reasons.most_common():
        print(
            f"{key:<90}: {value}"
        )

    print()
    print(
        f"Sortie                             : {OUTPUT_FILE}"
    )

    print()
    print(
        "Aucune donnée clinique n'a été modifiée."
    )


if __name__ == "__main__":
    main()