# -*- coding: utf-8 -*-
"""
numeric_unit_candidate_builder.py
=================================

TRACE / SGCE - NUMERIC / UNIT AUTONOMOUS CANDIDATE BUILDER

Version V7 améliorée :
- NE LIT PLUS numeric_unit_validated.json
- redétecte directement les anomalies numériques depuis la baseline clinique
- repart de :
    ontology Etage 4/ontology_duplicates/duplicate_entities/duplicate_entity_safe_merged
- récupère le contexte textuel exact
- produit les champs attendus par numeric_unit_validator.py

Anomalies détectées :
- NON_NUMERIC_VALUE
- MISSING_UNIT
- UNIT_PARAMETER_MISMATCH
- IMPLAUSIBLE_VALUE

Aucune donnée clinique n'est modifiée.
"""

import json
import re
import unicodedata
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent
REDUCTION_DIR = ROOT.parent

CLINICAL_DIR = (
    REDUCTION_DIR / "ontology Etage 4"
    / "ontology_duplicates"
    / "duplicate_entities"
    / "duplicate_entity_safe_merged"
)

TEXT_DIR = REDUCTION_DIR / "Sortie_Textes_Brut_MistralSmall4"

OUTPUT_FILE = ROOT / "queues" / "numeric_unit_candidates.json"
OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------
# UNITES ATTENDUES / PLAUSIBILITE
# ---------------------------------------------------------------------

UNIT_ALIASES = {
    "l/min": "L/min",
    "ml/min": "mL/min",
    "l/h": "L/h",
    "ml/h": "mL/h",
    "mg/min": "mg/min",
    "mg/h": "mg/h",
    "g/h": "g/h",

    "ug/kg/min": "µg/kg/min",
    "µg/kg/min": "µg/kg/min",
    "mcg/kg/min": "µg/kg/min",

    "mg/kg/min": "mg/kg/min",
    "mg/kg/h": "mg/kg/h",

    "mmol/l": "mmol/L",
    "mg/l": "mg/L",
    "ug/l": "µg/L",
    "µg/l": "µg/L",
    "mcg/l": "µg/L",
    "umol/l": "µmol/L",
    "µmol/l": "µmol/L",
    "g/l": "g/L",
    "g/dl": "g/dL",
    "mg/dl": "mg/dL",

    "mmhg": "mmHg",
    "kpa": "kPa",
    "%": "%",
    "°c": "°C",
    "bpm": "bpm",
    "/min": "/min",
    "cycles/min": "cycles/min",

    "ml": "mL",
    "l": "L",
    "mg": "mg",
    "g": "g",
    "ug": "µg",
    "µg": "µg",
    "mcg": "µg",
    "ui": "UI",
    "u": "U",
}

EXPECTED_UNITS = {
    "temperature_corporelle": {"°C"},
    "temperature": {"°C"},

    "spo2": {"%"},
    "sao2": {"%"},

    "frequence_cardiaque": {"bpm", "/min"},
    "fc": {"bpm", "/min"},

    "frequence_respiratoire": {"cycles/min", "/min"},
    "fr": {"cycles/min", "/min"},

    "pression_arterielle_systolique": {"mmHg"},
    "pression_arterielle_diastolique": {"mmHg"},
    "pression_arterielle_moyenne": {"mmHg"},
    "pam": {"mmHg"},
    "pas": {"mmHg"},
    "pad": {"mmHg"},

    "lactate": {"mmol/L"},
    "lactate_plasmatique": {"mmol/L"},

    "proteine_c_reactive": {"mg/L"},
    "crp": {"mg/L"},

    "procalcitonine": {"µg/L", "ng/mL"},
    "pct": {"µg/L", "ng/mL"},

    "paco2": {"kPa", "mmHg"},
    "pao2": {"kPa", "mmHg"},

    "debit_oxygene": {"L/min"},
    "oxygen_flow": {"L/min"},
    "debit_o2": {"L/min"},
}

PLAUSIBLE_RANGES = {
    "temperature_corporelle": (25, 45),
    "temperature": (25, 45),

    "spo2": (0, 100),
    "sao2": (0, 100),

    "frequence_cardiaque": (0, 300),
    "fc": (0, 300),

    "frequence_respiratoire": (0, 100),
    "fr": (0, 100),

    "pression_arterielle_systolique": (20, 300),
    "pression_arterielle_diastolique": (10, 200),
    "pression_arterielle_moyenne": (10, 250),
    "pam": (10, 250),

    "lactate": (0, 50),
    "lactate_plasmatique": (0, 50),

    "ph": (6.5, 8.0),
    "ph_arteriel": (6.5, 8.0),
}


# ---------------------------------------------------------------------
# UTILITAIRES
# ---------------------------------------------------------------------

def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize_text(value):
    text = unicodedata.normalize(
        "NFKD",
        str(value or "").lower()
    )

    text = "".join(
        c for c in text
        if not unicodedata.combining(c)
    )

    text = text.replace("μ", "µ")
    text = re.sub(r"\s*/\s*", "/", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def normalize_parameter(value):
    text = normalize_text(value)
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def canonical_unit(value):
    if value in (None, ""):
        return None

    key = normalize_text(value)
    return UNIT_ALIASES.get(
        key,
        str(value).strip(),
    )


def parse_number(value):
    if value in (None, ""):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().replace(",", ".")

    if re.fullmatch(
        r"[-+]?\d+(?:\.\d+)?",
        text,
    ):
        try:
            return float(text)
        except Exception:
            return None

    return None


def contains_number(value):
    if value in (None, ""):
        return False

    return bool(
        re.search(
            r"[-+]?\d+(?:[.,]\d+)?",
            str(value),
        )
    )


def entity_id(e):
    return (
        e.get("identifiant_entite")
        or e.get("id")
        or e.get("entity_id")
    )


def entity_type(e):
    return (
        e.get("categorie")
        or e.get("type")
        or e.get("entity_type")
        or ""
    )


def entity_text(e):
    vals = []

    for key in (
        "preuve",
        "texte",
        "text",
        "nom",
        "name",
        "libelle",
        "parametre",
        "valeur",
    ):
        value = e.get(key)

        if value not in (None, ""):
            s = str(value).strip()

            if s and s not in vals:
                vals.append(s)

    return " | ".join(vals)


def get_parameter(entity):
    for key in (
        "parametre",
        "parameter",
        "nom_parametre",
        "type_mesure",
        "libelle",
        "name",
        "nom",
    ):
        value = entity.get(key)

        if value not in (None, ""):
            return str(value).strip()

    return entity_type(entity)


def is_clinical(path):
    if path.name.endswith("_report.json"):
        return False

    try:
        doc = load_json(path)
    except Exception:
        return False

    return (
        isinstance(doc, dict)
        and any(
            k in doc
            for k in (
                "pages",
                "global_entities",
                "global_relations",
            )
        )
    )


def get_entities(doc):
    if isinstance(
        doc.get("global_entities"),
        list,
    ):
        return doc["global_entities"]

    return [
        e
        for page in doc.get("pages", []) or []
        for e in page.get("entities", []) or []
    ]


# ---------------------------------------------------------------------
# EXTRACTION VALEUR / UNITE DEPUIS L'ENTITE
# ---------------------------------------------------------------------

def numeric_slots(entity):
    """
    Retourne une ou plusieurs représentations numériques possibles.
    Chaque slot possède :
      mode
      raw_value
      raw_unit
    """

    slots = []

    # valeur générique
    generic_value = None
    generic_unit = None

    for key in (
        "valeur",
        "value",
        "valeur_mesuree",
    ):
        if key in entity:
            generic_value = entity.get(key)
            break

    for key in (
        "unite",
        "unit",
        "unite_mesure",
    ):
        if key in entity:
            generic_unit = entity.get(key)
            break

    if generic_value not in (None, ""):
        slots.append({
            "mode":
                "VALUE",

            "raw_value":
                generic_value,

            "raw_unit":
                generic_unit,
        })

    # posologie dose
    if entity.get("dose_valeur") not in (None, ""):
        slots.append({
            "mode":
                "POSOLOGY_DOSE",

            "raw_value":
                entity.get("dose_valeur"),

            "raw_unit":
                entity.get("unite_dose"),
        })

    # posologie débit
    if entity.get("debit") not in (None, ""):
        slots.append({
            "mode":
                "POSOLOGY_FLOW",

            "raw_value":
                entity.get("debit"),

            "raw_unit":
                entity.get("unite_debit"),
        })

    # posologie volume
    if entity.get("volume") not in (None, ""):
        slots.append({
            "mode":
                "POSOLOGY_VOLUME",

            "raw_value":
                entity.get("volume"),

            "raw_unit":
                entity.get("unite_volume"),
        })

    return slots


# ---------------------------------------------------------------------
# DETECTION DES ANOMALIES
# ---------------------------------------------------------------------

def detect_issues(parameter, raw_value, raw_unit):
    issues = []

    p = normalize_parameter(
        parameter
    )

    number = parse_number(
        raw_value
    )

    unit = canonical_unit(
        raw_unit
    )

    # Cas comme "3L/min", "500 ml", "7mg/h"
    if (
        raw_value not in (
            None,
            "",
        )
        and number is None
        and contains_number(
            raw_value
        )
    ):
        issues.append(
            "NON_NUMERIC_VALUE"
        )

    # unité absente
    if (
        raw_value not in (
            None,
            "",
        )
        and raw_unit in (
            None,
            "",
        )
    ):
        issues.append(
            "MISSING_UNIT"
        )

    # unité incompatible avec paramètre connu
    expected = EXPECTED_UNITS.get(
        p
    )

    if (
        unit is not None
        and expected
        and unit not in expected
    ):
        issues.append(
            "UNIT_PARAMETER_MISMATCH"
        )

    # valeur implausible
    plausible = PLAUSIBLE_RANGES.get(
        p
    )

    if (
        number is not None
        and plausible
        and not (
            plausible[0]
            <= number
            <= plausible[1]
        )
    ):
        issues.append(
            "IMPLAUSIBLE_VALUE"
        )

    return issues


# ---------------------------------------------------------------------
# CONTEXTE TEXTE
# ---------------------------------------------------------------------

def find_text_file(document_name):
    stem = Path(
        document_name
    ).stem

    exact = list(
        TEXT_DIR.glob(
            f"{stem}*.txt"
        )
    )

    if exact:
        return exact[0]

    short_stem = stem.split(
        "_trace_sepsis"
    )[0]

    partial = list(
        TEXT_DIR.glob(
            f"{short_stem}*.txt"
        )
    )

    return (
        partial[0]
        if partial
        else None
    )


def split_sentences(text):
    if not text:
        return []

    chunks = re.split(
        r"(?<=[\.\!\?\;\n])\s+",
        text,
    )

    return [
        x.strip()
        for x in chunks
        if x.strip()
    ]


def find_best_context(sentences, entity, raw_value):
    candidates = []

    # Priorité à raw_value, car c'est ce qu'on cherche à corriger.
    if raw_value not in (None, ""):
        candidates.append(
            str(raw_value).strip()
        )

    # Puis preuve / texte complet de l'entité.
    for part in entity_text(
        entity
    ).split("|"):
        part = part.strip()

        if (
            part
            and part
            not in candidates
        ):
            candidates.append(
                part
            )

    for mention in candidates:
        low = mention.lower()

        for idx, sentence in enumerate(
            sentences
        ):
            pos = sentence.lower().find(
                low
            )

            if pos != -1:
                return {
                    "matched_mention":
                        mention,

                    "sentence":
                        sentence,

                    "previous_sentence":
                        (
                            sentences[
                                idx - 1
                            ]
                            if idx > 0
                            else ""
                        ),

                    "next_sentence":
                        (
                            sentences[
                                idx + 1
                            ]
                            if idx + 1
                            < len(sentences)
                            else ""
                        ),

                    "mention_start":
                        pos,

                    "mention_end":
                        pos
                        + len(
                            mention
                        ),
                }

    return None


# ---------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------

def main():
    candidates = []

    docs = 0
    issue_counts = Counter()

    missing_texts = 0
    mentions_not_found = 0

    # Pour éviter de dupliquer une même entité logique.
    seen_candidates = set()

    for path in sorted(
        CLINICAL_DIR.glob(
            "*.json"
        )
    ):
        if not is_clinical(
            path
        ):
            continue

        doc = load_json(
            path
        )

        docs += 1

        text_file = find_text_file(
            path.name
        )

        if text_file:
            text = text_file.read_text(
                encoding="utf-8",
                errors="ignore",
            )

            sentences = split_sentences(
                text
            )

        else:
            sentences = []
            missing_texts += 1

        for entity in get_entities(
            doc
        ):
            eid = entity_id(
                entity
            )

            if eid is None:
                continue

            parameter = get_parameter(
                entity
            )

            for slot in numeric_slots(
                entity
            ):
                mode = slot[
                    "mode"
                ]

                raw_value = slot[
                    "raw_value"
                ]

                raw_unit = slot[
                    "raw_unit"
                ]

                issues = detect_issues(
                    parameter,
                    raw_value,
                    raw_unit,
                )

                if not issues:
                    continue

                logical_key = (
                    path.name,
                    str(
                        eid
                    ),
                    mode,
                )

                if logical_key in seen_candidates:
                    continue

                seen_candidates.add(
                    logical_key
                )

                for issue in issues:
                    issue_counts[
                        issue
                    ] += 1

                context = find_best_context(
                    sentences,
                    entity,
                    raw_value,
                )

                if context is None:
                    mentions_not_found += 1

                    context = {
                        "matched_mention":
                            None,

                        "sentence":
                            "",

                        "previous_sentence":
                            "",

                        "next_sentence":
                            "",

                        "mention_start":
                            None,

                        "mention_end":
                            None,
                    }

                candidates.append({
                    "candidate_id":
                        f"NUR_{len(candidates)+1:06d}",

                    "document":
                        path.name,

                    "entity_id":
                        eid,

                    "entity_type":
                        entity_type(
                            entity
                        ),

                    "parameter":
                        parameter,

                    "mode":
                        mode,

                    "raw_value":
                        raw_value,

                    "raw_unit":
                        raw_unit,

                    "previous_issues":
                        issues,

                    "entity_text":
                        entity_text(
                            entity
                        ),

                    "sentence":
                        context[
                            "sentence"
                        ],

                    "previous_sentence":
                        context[
                            "previous_sentence"
                        ],

                    "next_sentence":
                        context[
                            "next_sentence"
                        ],

                    "matched_mention":
                        context[
                            "matched_mention"
                        ],

                    "mention_start":
                        context[
                            "mention_start"
                        ],

                    "mention_end":
                        context[
                            "mention_end"
                        ],

                    "text_file":
                        (
                            str(
                                text_file
                            )
                            if text_file
                            else None
                        ),
                })

    payload = {
        "builder":
            "numeric_unit_candidate_builder",

        "mode":
            "AUTONOMOUS_REDETECTION_TEXT_GUIDED",

        "clinical_directory":
            str(
                CLINICAL_DIR
            ),

        "summary": {
            "documents_analysed":
                docs,

            "candidates_built":
                len(
                    candidates
                ),

            "issue_counts":
                dict(
                    issue_counts
                ),

            "missing_texts":
                missing_texts,

            "mentions_not_found":
                mentions_not_found,
        },

        "candidates":
            candidates,
    }

    OUTPUT_FILE.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=" * 112)
    print(
        "TRACE / SGCE - NUMERIC UNIT CANDIDATE BUILDER "
        "- AUTONOMOUS REDETECTION"
    )
    print("=" * 112)

    print(
        f"Documents analysés                 : {docs}"
    )

    print(
        f"Candidats construits               : {len(candidates)}"
    )

    print(
        f"Textes manquants                   : {missing_texts}"
    )

    print(
        f"Mentions non retrouvées            : {mentions_not_found}"
    )

    print()
    print("ANOMALIES REDETECTEES")
    print("-" * 112)

    for key, value in issue_counts.items():
        print(
            f"{key:<52}: {value}"
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
