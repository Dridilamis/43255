# -*- coding: utf-8 -*-
"""
pattern_c_detector.py
=====================

SGCE — Pattern C Detection Only
Pattern C : relation réifiée en chaîne

OBJECTIF
--------
Détecter les cas où une information relationnelle semble avoir été extraite
comme une ENTITÉ alors qu'elle devrait potentiellement être représentée
par une RELATION TRACE-Sepsis autorisée.

IMPORTANT
---------
- Aucun JSON clinique n'est modifié.
- Pattern C lit UNIQUEMENT la sortie finale de Pattern B :
      PatternB2/pattern_b2_corrected
- Aucun fallback vers Pattern B1 ou Pattern A.
- Les 32 relations autorisées sont lues depuis le guideline TRACE-Sepsis v1.6.

SORTIES
-------
PatternC/pattern_c_detection/pattern_c_detection_report.json
PatternC/pattern_c_detection/pattern_c_candidates.csv
"""

import csv
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path


# ============================================================
# 1. PATHS
# ============================================================

PATTERN_C_DIR = Path(__file__).resolve().parent
PATTERNS_DIR = PATTERN_C_DIR.parent
SGCE_DIR = PATTERNS_DIR.parent
BASE_DIR = SGCE_DIR.parent

PATTERN_B2_DIR = PATTERNS_DIR / "PatternB" / "PatternB2"

# Pattern C lit STRICTEMENT la sortie finale de Pattern B.
INPUT_DIR = PATTERN_B2_DIR / "corrected"

GUIDELINE_CANDIDATES = [
    BASE_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
    BASE_DIR.parent / "Guideline_TRACE_Sepsis_v1.6.json",
    Path.cwd() / "Guideline_TRACE_Sepsis_v1.6.json",
    PATTERN_C_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
]

OUTPUT_DIR = PATTERN_C_DIR / "detection"
OUTPUT_JSON = OUTPUT_DIR / "pattern_c_detection_report.json"
OUTPUT_CSV = OUTPUT_DIR / "pattern_c_candidates.csv"

# ============================================================
# 2. GENERIC FIELD NAMES
# ============================================================

TEXT_FIELDS = (
    "preuve",
    "name",
    "valeur",
    "libelle",
    "parametre",
    "texte",
    "text",
)

TYPE_FIELDS = (
    "categorie",
    "type",
    "entity_type",
    "type_entite",
)

ID_FIELDS = (
    "identifiant_entite",
    "id",
    "entity_id",
    "identifiant",
)

PAGE_FIELDS = (
    "page",
    "page_number",
    "numero_page",
)


# Types qui peuvent naturellement contenir un vocabulaire relationnel.
# On évite de les classer trop facilement comme relation réifiée.
PROTECTED_ENTITY_TYPES = {
    "EVENEMENT_TEMPOREL",
    "EVOLUTION_PRONOSTIC",
    "CONTEXTE_ACQUISITION",
    "SERVICE_MEDICAL",
}


# ============================================================
# 3. BASIC HELPERS
# ============================================================

def load_json(path):
    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


def normalize(text):
    text = "" if text is None else str(text)

    text = text.replace(
        "’",
        "'",
    )

    text = unicodedata.normalize(
        "NFKD",
        text,
    )

    text = "".join(
        c
        for c in text
        if not unicodedata.combining(c)
    )

    text = text.lower()

    text = text.replace(
        "_",
        " ",
    )

    text = re.sub(
        r"[^a-z0-9+./ -]+",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def first_value(
    data,
    keys,
):
    if not isinstance(
        data,
        dict,
    ):
        return None

    for key in keys:
        value = data.get(
            key
        )

        if value not in (
            None,
            "",
        ):
            return value

    return None


def entity_id(entity):
    value = first_value(
        entity,
        ID_FIELDS,
    )

    if value is None:
        return ""

    return str(
        value
    ).strip()


def entity_type(entity):
    value = first_value(
        entity,
        TYPE_FIELDS,
    )

    if value is None:
        return ""

    return str(
        value
    ).strip()


def entity_page(
    entity,
    fallback=None,
):
    value = first_value(
        entity,
        PAGE_FIELDS,
    )

    if value is None:
        return fallback

    return value


def entity_text(entity):
    values = []

    if not isinstance(
        entity,
        dict,
    ):
        return ""

    for key in TEXT_FIELDS:
        value = entity.get(
            key
        )

        if value not in (
            None,
            "",
        ):
            text = str(
                value
            ).strip()

            if (
                text
                and text not in values
            ):
                values.append(
                    text
                )

    return " | ".join(
        values
    )


def is_clinical_document(doc):
    return (
        isinstance(
            doc,
            dict,
        )
        and (
            isinstance(
                doc.get(
                    "global_entities"
                ),
                list,
            )
            or isinstance(
                doc.get(
                    "pages"
                ),
                list,
            )
        )
    )


# ============================================================
# 4. STRICT INPUT RESOLUTION
# ============================================================

def resolve_input_dir():
    """
    Pattern C lit STRICTEMENT la sortie finale de Pattern B.
    Aucun fallback.
    """

    if not isinstance(
        INPUT_DIR,
        Path,
    ):
        raise TypeError(
            "INPUT_DIR doit être un objet pathlib.Path. "
            f"Type actuel : {type(INPUT_DIR)}"
        )

    if not INPUT_DIR.exists():
        raise FileNotFoundError(
            "La sortie finale de Pattern B est introuvable :\n"
            f"{INPUT_DIR}"
        )

    clinical_jsons = [
        p
        for p in INPUT_DIR.glob(
            "*.json"
        )
        if p.is_file()
    ]

    if not clinical_jsons:
        raise FileNotFoundError(
            "Aucun fichier JSON trouvé dans la sortie finale Pattern B :\n"
            f"{INPUT_DIR}"
        )

    return INPUT_DIR


def resolve_guideline():
    for path in GUIDELINE_CANDIDATES:
        if path.exists():
            return path

    raise FileNotFoundError(
        "Guideline_TRACE_Sepsis_v1.6.json introuvable.\n"
        "Place-le soit dans :\n"
        f"- {BASE_DIR}\n"
        f"- {BASE_DIR.parent}\n"
        "- le dossier PatternC\n"
        "- ou le dossier courant."
    )


# ============================================================
# 5. ENTITY COLLECTION
# ============================================================

def get_entities(doc):
    """
    Priorité à global_entities.
    Sinon lecture des entités page par page.
    """

    if isinstance(
        doc.get(
            "global_entities"
        ),
        list,
    ):
        return doc[
            "global_entities"
        ]

    entities = []

    for page in (
        doc.get(
            "pages",
            []
        )
        or []
    ):
        if not isinstance(
            page,
            dict,
        ):
            continue

        page_number = first_value(
            page,
            PAGE_FIELDS,
        )

        for key in (
            "entities",
            "entites",
        ):
            for entity in (
                page.get(
                    key,
                    []
                )
                or []
            ):
                if not isinstance(
                    entity,
                    dict,
                ):
                    continue

                item = dict(
                    entity
                )

                if (
                    first_value(
                        item,
                        PAGE_FIELDS,
                    )
                    is None
                    and page_number
                    is not None
                ):
                    item[
                        "page"
                    ] = page_number

                entities.append(
                    item
                )

    return entities


# ============================================================
# 6. GUIDELINE RELATIONS
# ============================================================

def get_guideline_root(
    guideline,
):
    return guideline.get(
        "ontologie_sepsis_graph",
        guideline,
    )


def extract_relation_specs(
    guideline,
):
    """
    Charge les signatures domaine/image verrouillées v1.5
    et récupère les descriptions depuis la section relations.
    """

    root = get_guideline_root(
        guideline
    )

    locked = root.get(
        "signatures_relations_verrouillees_v1_5",
        {},
    )

    relation_descriptions = {}

    relations_section = root.get(
        "relations",
        {},
    )

    if isinstance(
        relations_section,
        dict,
    ):
        for group_name, group in (
            relations_section.items()
        ):
            if not isinstance(
                group,
                dict,
            ):
                continue

            for relation_name, spec in (
                group.items()
            ):
                if not isinstance(
                    spec,
                    dict,
                ):
                    continue

                relation_descriptions[
                    relation_name
                ] = {
                    "description":
                        spec.get(
                            "description",
                            "",
                        ),

                    "group":
                        group_name,
                }

    specs = {}

    if not isinstance(
        locked,
        dict,
    ):
        return specs

    for relation_name, spec in (
        locked.items()
    ):
        if not isinstance(
            spec,
            dict,
        ):
            continue

        domain = spec.get(
            "domaine"
        )

        image = spec.get(
            "image"
        )

        if not (
            domain
            and image
        ):
            continue

        description_info = (
            relation_descriptions.get(
                relation_name,
                {},
            )
        )

        specs[
            relation_name
        ] = {
            "domaine":
                domain,

            "image":
                image,

            "groupe":
                spec.get(
                    "groupe",
                    description_info.get(
                        "group",
                        "",
                    ),
                ),

            "description":
                description_info.get(
                    "description",
                    "",
                ),
        }

    return specs


# ============================================================
# 7. RELATION LEXICON
# ============================================================

STOPWORDS = {
    "a",
    "au",
    "aux",
    "de",
    "des",
    "du",
    "d",
    "la",
    "le",
    "les",
    "un",
    "une",
    "et",
    "en",
    "pour",
    "par",
    "avec",
    "dans",
    "sur",
    "vers",
    "son",
    "sa",
    "ses",
    "est",
    "etre",
    "entre",
    "patient",
    "relation",
    "lien",
}


def tokenize(text):
    return [
        token
        for token in re.findall(
            r"[a-z0-9]+",
            normalize(
                text
            ),
        )
        if (
            len(
                token
            )
            >= 3
            and token
            not in STOPWORDS
        )
    ]


def build_relation_lexicon(
    relation_specs,
):
    lexicon = {}

    for relation_name, spec in (
        relation_specs.items()
    ):

        name_tokens = set(
            tokenize(
                relation_name
            )
        )

        description_tokens = set(
            tokenize(
                spec.get(
                    "description",
                    "",
                )
            )
        )

        all_tokens = (
            name_tokens
            | description_tokens
        )

        all_tokens = {
            token
            for token in all_tokens
            if len(
                token
            )
            >= 4
        }

        lexicon[
            relation_name
        ] = {
            "tokens":
                sorted(
                    all_tokens
                ),

            "name_tokens":
                sorted(
                    name_tokens
                ),
        }

    return lexicon


# ============================================================
# 8. RELATION-LIKE SIMILARITY
# ============================================================

def relation_similarity(
    entity_text_value,
    relation_name,
    lexicon_entry,
):
    text_tokens = set(
        tokenize(
            entity_text_value
        )
    )

    if not text_tokens:
        return (
            0.0,
            [],
        )

    relation_tokens = set(
        lexicon_entry.get(
            "tokens",
            [],
        )
    )

    relation_name_tokens = set(
        lexicon_entry.get(
            "name_tokens",
            [],
        )
    )

    overlap_all = (
        text_tokens
        & relation_tokens
    )

    overlap_name = (
        text_tokens
        & relation_name_tokens
    )

    if not overlap_all:
        return (
            0.0,
            [],
        )

    name_score = (
        len(
            overlap_name
        )
        / max(
            1,
            len(
                relation_name_tokens
            ),
        )
    )

    all_score = (
        len(
            overlap_all
        )
        / max(
            1,
            len(
                relation_tokens
            ),
        )
    )

    score = (
        0.65
        * name_score
        +
        0.35
        * all_score
    )

    if len(
        overlap_all
    ) >= 2:
        score += 0.15

    return (
        min(
            score,
            1.0,
        ),
        sorted(
            overlap_all
        ),
    )


# ============================================================
# 9. COMPATIBLE ENDPOINTS
# ============================================================

def find_compatible_endpoints(
    reified_entity,
    entities,
    domain_type,
    image_type,
):
    page = entity_page(
        reified_entity
    )

    reified_id = entity_id(
        reified_entity
    )

    same_page_domain = []
    same_page_image = []

    document_domain = []
    document_image = []

    for entity in entities:
        if (
            entity_id(
                entity
            )
            == reified_id
        ):
            continue

        current_type = entity_type(
            entity
        )

        if (
            current_type
            == domain_type
        ):
            document_domain.append(
                entity
            )

            if (
                page is not None
                and str(
                    entity_page(
                        entity
                    )
                )
                == str(
                    page
                )
            ):
                same_page_domain.append(
                    entity
                )

        if (
            current_type
            == image_type
        ):
            document_image.append(
                entity
            )

            if (
                page is not None
                and str(
                    entity_page(
                        entity
                    )
                )
                == str(
                    page
                )
            ):
                same_page_image.append(
                    entity
                )

    domains = (
        same_page_domain
        if same_page_domain
        else document_domain
    )

    images = (
        same_page_image
        if same_page_image
        else document_image
    )

    return (
        domains,
        images,
    )


def compact_entity(
    entity,
):
    return {
        "id":
            entity_id(
                entity
            ),

        "type":
            entity_type(
                entity
            ),

        "text":
            entity_text(
                entity
            ),

        "page":
            entity_page(
                entity
            ),
    }


# ============================================================
# 10. MAIN
# ============================================================

def main():

    # --------------------------------------------------------
    # Strict input
    # --------------------------------------------------------

    input_dir = resolve_input_dir()

    guideline_path = resolve_guideline()

    guideline = load_json(
        guideline_path
    )

    relation_specs = extract_relation_specs(
        guideline
    )

    if not relation_specs:
        raise RuntimeError(
            "Aucune relation TRACE-Sepsis n'a été chargée "
            "depuis le guideline."
        )

    relation_lexicon = build_relation_lexicon(
        relation_specs
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    candidates = []

    skipped_nonclinical = []

    errors = []

    clinical_documents = 0

    total_entities = 0

    # --------------------------------------------------------
    # Scan documents
    # --------------------------------------------------------

    for path in sorted(
        input_dir.glob(
            "*.json"
        )
    ):

        try:
            doc = load_json(
                path
            )

            if not is_clinical_document(
                doc
            ):
                skipped_nonclinical.append(
                    path.name
                )
                continue

            clinical_documents += 1

            entities = get_entities(
                doc
            )

            total_entities += len(
                entities
            )

            # ------------------------------------------------
            # Scan each entity
            # ------------------------------------------------

            for entity in entities:

                current_type = entity_type(
                    entity
                )

                current_text = entity_text(
                    entity
                )

                if not current_text:
                    continue

                if (
                    current_type
                    in PROTECTED_ENTITY_TYPES
                ):
                    continue

                hypotheses = []

                # --------------------------------------------
                # Compare entity text to all authorized relations
                # --------------------------------------------

                for relation_name, spec in (
                    relation_specs.items()
                ):

                    score, matched_tokens = (
                        relation_similarity(
                            current_text,
                            relation_name,
                            relation_lexicon[
                                relation_name
                            ],
                        )
                    )

                    if score < 0.45:
                        continue

                    domains, images = (
                        find_compatible_endpoints(
                            entity,
                            entities,
                            spec[
                                "domaine"
                            ],
                            spec[
                                "image"
                            ],
                        )
                    )

                    # A relation reification candidate requires
                    # at least one possible endpoint on both sides.
                    if not domains:
                        continue

                    if not images:
                        continue

                    hypotheses.append({
                        "relation_name":
                            relation_name,

                        "domain_type":
                            spec[
                                "domaine"
                            ],

                        "image_type":
                            spec[
                                "image"
                            ],

                        "relation_group":
                            spec.get(
                                "groupe",
                                "",
                            ),

                        "relation_description":
                            spec.get(
                                "description",
                                "",
                            ),

                        "similarity_score":
                            round(
                                score,
                                4,
                            ),

                        "matched_tokens":
                            matched_tokens,

                        "domain_candidates": [
                            compact_entity(
                                x
                            )
                            for x in domains[
                                :10
                            ]
                        ],

                        "image_candidates": [
                            compact_entity(
                                x
                            )
                            for x in images[
                                :10
                            ]
                        ],
                    })

                if not hypotheses:
                    continue

                hypotheses.sort(
                    key=lambda x:
                        x[
                            "similarity_score"
                        ],
                    reverse=True,
                )

                top_score = (
                    hypotheses[
                        0
                    ][
                        "similarity_score"
                    ]
                )

                if (
                    top_score
                    >= 0.75
                ):
                    strength = (
                        "STRONG"
                    )

                elif (
                    top_score
                    >= 0.60
                ):
                    strength = (
                        "MEDIUM"
                    )

                else:
                    strength = (
                        "WEAK"
                    )

                candidates.append({
                    "candidate_id":
                        (
                            f"C_"
                            f"{len(candidates)+1:06d}"
                        ),

                    "document":
                        path.name,

                    "pattern":
                        "C",

                    "candidate_type":
                        "REIFIED_RELATION_ENTITY",

                    "strength":
                        strength,

                    "reified_entity":
                        compact_entity(
                            entity
                        ),

                    "best_relation_hypotheses":
                        hypotheses[
                            :5
                        ],

                    "top_similarity_score":
                        top_score,

                    "status":
                        "C_CANDIDATE",

                    "safe_to_correct":
                        False,
                })

        except Exception as exc:
            errors.append({
                "document":
                    path.name,

                "error":
                    str(
                        exc
                    ),
            })

    # --------------------------------------------------------
    # Statistics
    # --------------------------------------------------------

    strength_counts = Counter(
        candidate[
            "strength"
        ]
        for candidate
        in candidates
    )

    relation_counts = Counter()

    for candidate in candidates:
        hypotheses = candidate.get(
            "best_relation_hypotheses",
            [],
        )

        if hypotheses:
            relation_counts[
                hypotheses[
                    0
                ][
                    "relation_name"
                ]
            ] += 1

    # --------------------------------------------------------
    # JSON report
    # --------------------------------------------------------

    report = {
        "pattern":
            "C",

        "name":
            "Relation réifiée en chaîne",

        "mode":
            "DETECTION_ONLY",

        "input_directory":
            str(
                input_dir
            ),

        "guideline":
            str(
                guideline_path
            ),

        "summary": {
            "clinical_documents":
                clinical_documents,

            "nonclinical_json_skipped":
                len(
                    skipped_nonclinical
                ),

            "entities_analyzed":
                total_entities,

            "authorized_relations":
                len(
                    relation_specs
                ),

            "candidates":
                len(
                    candidates
                ),

            "weak":
                strength_counts.get(
                    "WEAK",
                    0,
                ),

            "medium":
                strength_counts.get(
                    "MEDIUM",
                    0,
                ),

            "strong":
                strength_counts.get(
                    "STRONG",
                    0,
                ),

            "errors":
                len(
                    errors
                ),
        },

        "candidate_counts_by_top_relation":
            dict(
                relation_counts
            ),

        "candidates":
            candidates,

        "nonclinical_json_skipped":
            skipped_nonclinical,

        "errors":
            errors,
    }

    OUTPUT_JSON.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # CSV
    # --------------------------------------------------------

    fields = [
        "candidate_id",
        "document",
        "strength",
        "entity_id",
        "entity_type",
        "entity_text",
        "entity_page",
        "top_relation",
        "domain_type",
        "image_type",
        "score",
        "matched_tokens",
        "domain_candidate_count",
        "image_candidate_count",
    ]

    with OUTPUT_CSV.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fields,
        )

        writer.writeheader()

        for candidate in candidates:

            reified = candidate[
                "reified_entity"
            ]

            hypothesis = (
                candidate[
                    "best_relation_hypotheses"
                ][
                    0
                ]
            )

            writer.writerow({
                "candidate_id":
                    candidate[
                        "candidate_id"
                    ],

                "document":
                    candidate[
                        "document"
                    ],

                "strength":
                    candidate[
                        "strength"
                    ],

                "entity_id":
                    reified[
                        "id"
                    ],

                "entity_type":
                    reified[
                        "type"
                    ],

                "entity_text":
                    reified[
                        "text"
                    ],

                "entity_page":
                    reified[
                        "page"
                    ],

                "top_relation":
                    hypothesis[
                        "relation_name"
                    ],

                "domain_type":
                    hypothesis[
                        "domain_type"
                    ],

                "image_type":
                    hypothesis[
                        "image_type"
                    ],

                "score":
                    hypothesis[
                        "similarity_score"
                    ],

                "matched_tokens":
                    " | ".join(
                        hypothesis[
                            "matched_tokens"
                        ]
                    ),

                "domain_candidate_count":
                    len(
                        hypothesis[
                            "domain_candidates"
                        ]
                    ),

                "image_candidate_count":
                    len(
                        hypothesis[
                            "image_candidates"
                        ]
                    ),
            })

    # --------------------------------------------------------
    # Console
    # --------------------------------------------------------

    print(
        "="
        * 82
    )

    print(
        "SGCE - PATTERN C DETECTION"
    )

    print(
        "="
        * 82
    )

    print(
        f"Entrée clinique           : "
        f"{input_dir}"
    )

    print(
        f"Guideline                 : "
        f"{guideline_path}"
    )

    print()

    print(
        f"Documents cliniques       : "
        f"{clinical_documents}"
    )

    print(
        f"JSON non cliniques ignorés: "
        f"{len(skipped_nonclinical)}"
    )

    print(
        f"Entités analysées         : "
        f"{total_entities}"
    )

    print(
        f"Relations TRACE autorisées: "
        f"{len(relation_specs)}"
    )

    print()

    print(
        f"Candidats Pattern C       : "
        f"{len(candidates)}"
    )

    print(
        f"WEAK                      : "
        f"{strength_counts.get('WEAK', 0)}"
    )

    print(
        f"MEDIUM                    : "
        f"{strength_counts.get('MEDIUM', 0)}"
    )

    print(
        f"STRONG                    : "
        f"{strength_counts.get('STRONG', 0)}"
    )

    print(
        f"Erreurs                   : "
        f"{len(errors)}"
    )

    print()

    print(
        "Relations les plus souvent suspectées :"
    )

    if relation_counts:
        for relation_name, count in (
            relation_counts.most_common(
                15
            )
        ):
            print(
                f"  "
                f"{relation_name:<45}"
                f": {count}"
            )

    else:
        print(
            "  Aucun candidat détecté."
        )

    print()

    print(
        f"Rapport JSON              : "
        f"{OUTPUT_JSON}"
    )

    print(
        f"CSV candidats             : "
        f"{OUTPUT_CSV}"
    )

    print()

    print(
        "Aucun JSON clinique n'a été modifié."
    )


if __name__ == "__main__":
    main()
