# -*- coding: utf-8 -*-
"""
pattern_d_validator.py
======================

SGCE — Pattern D Validator

Pattern D:
Violation de signature relationnelle (Domain–Range Mismatch)

Input:
  PatternD/pattern_d_detection/pattern_d_detection_report.json

ENTREE CLINIQUE STRICTE:
  PatternC/pattern_c_corrected

OBJECTIF
--------
Pour chaque violation D1/D2, distinguer automatiquement :

1) RELINK
   Une autre entité EXISTANTE du type attendu correspond clairement
   à l'endpoint fautif.

2) RETYPE_ENTITY
   Le graphe fournit un consensus structurel fort indiquant que
   l'entité elle-même est mal typée.

3) REMOVE_INVALID_RELATION
   Les types actuels des deux endpoints sont fortement supportés par
   leurs autres relations valides, aucune entité de remplacement n'est
   trouvée et la relation fautive apparaît isolée.

4) SKIP
   Preuve insuffisante ou ambiguë.

Aucun JSON clinique n'est modifié.

IMPORTANT
---------
Le validator n'utilise aucune connaissance médicale externe.
Il se base uniquement sur :
- les signatures TRACE-Sepsis verrouillées,
- les entités/relations déjà présentes,
- la similarité textuelle avec d'autres entités existantes.
"""

import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


# ============================================================
# 1. PATHS
# ============================================================

PATTERN_D_DIR = Path(__file__).resolve().parent
PATTERNS_DIR = PATTERN_D_DIR.parent
SGCE_DIR = PATTERNS_DIR.parent
BASE_DIR = SGCE_DIR.parent

PATTERN_C_DIR = PATTERNS_DIR / "PatternC"
INPUT_DIR = PATTERN_C_DIR / "corrected"

DETECTION_REPORT = PATTERN_D_DIR / "detection" / "pattern_d_detection_report.json"

GUIDELINE_CANDIDATES = [
    BASE_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
    BASE_DIR.parent / "Guideline_TRACE_Sepsis_v1.6.json",
    Path.cwd() / "Guideline_TRACE_Sepsis_v1.6.json",
    PATTERN_D_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
]

OUTPUT_DIR = PATTERN_D_DIR / "validation"
OUTPUT_JSON = OUTPUT_DIR / "pattern_d_validation_report.json"
OUTPUT_CSV = OUTPUT_DIR / "pattern_d_validation_candidates.csv"


# Conservative thresholds
RELINK_MIN_SCORE = 0.78
RELINK_MIN_MARGIN = 0.15

RETYPE_MIN_EXPECTED_VOTES = 2
RETYPE_MIN_PURITY = 0.90

REMOVE_MIN_CURRENT_TYPE_SUPPORT = 2


# ============================================================
# 2. HELPERS
# ============================================================

def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_guideline():
    for p in GUIDELINE_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError(
        "Guideline_TRACE_Sepsis_v1.6.json introuvable."
    )


def is_clinical_document(doc):
    return isinstance(doc, dict) and (
        isinstance(doc.get("global_entities"), list)
        or isinstance(doc.get("pages"), list)
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
        or ""
    )


def entity_text(e):
    values = []
    for key in (
        "preuve",
        "name",
        "valeur",
        "libelle",
        "parametre",
        "texte",
        "text",
    ):
        v = e.get(key)
        if v not in (None, ""):
            s = str(v).strip()
            if s and s not in values:
                values.append(s)

    return " | ".join(values)


def entity_page(e):
    if e.get("page") is not None:
        return e.get("page")
    return e.get("page_number")


def relation_id(r):
    return (
        r.get("identifiant_relation")
        or r.get("id")
        or r.get("relation_id")
    )


def relation_type(r):
    return (
        r.get("type_relation")
        or r.get("relation")
        or r.get("type")
        or ""
    )


def relation_source(r):
    return (
        r.get("identifiant_entite_sujet")
        or r.get("from_id")
        or r.get("subject_id")
    )


def relation_target(r):
    return (
        r.get("identifiant_entite_objet")
        or r.get("to_id")
        or r.get("object_id")
    )


def get_entities(doc):
    if isinstance(doc.get("global_entities"), list):
        return doc["global_entities"]

    out = []
    for page in doc.get("pages", []) or []:
        out.extend(page.get("entities", []) or [])

    return out


def get_relations(doc):
    if isinstance(doc.get("global_relations"), list):
        return doc["global_relations"]

    out = []
    for page in doc.get("pages", []) or []:
        out.extend(page.get("relations", []) or [])

    return out


def normalize(text):
    text = "" if text is None else str(text)
    text = text.replace("’", "'")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        c for c in text
        if not unicodedata.combining(c)
    )
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokens(text):
    return {
        t
        for t in re.findall(
            r"[a-z0-9]+",
            normalize(text)
        )
        if len(t) >= 2
    }


# ============================================================
# 3. GUIDELINE SIGNATURES
# ============================================================

def get_root(guideline):
    return guideline.get(
        "ontologie_sepsis_graph",
        guideline
    )


def get_locked_signatures(guideline):
    root = get_root(guideline)

    locked = root.get(
        "signatures_relations_verrouillees_v1_5",
        {}
    )

    out = {}

    for rtype, spec in locked.items():
        if not isinstance(spec, dict):
            continue

        dom = spec.get("domaine")
        img = spec.get("image")

        if dom and img:
            out[rtype] = (
                dom,
                img,
            )

    return out


# ============================================================
# 4. TEXTUAL MATCHING FOR RELINK
# ============================================================

def text_similarity(a, b):
    na = normalize(a)
    nb = normalize(b)

    if not na or not nb:
        return 0.0

    if na == nb:
        return 1.0

    # Strong containment
    if na in nb or nb in na:
        shorter = min(
            len(na),
            len(nb),
        )
        longer = max(
            len(na),
            len(nb),
        )
        return 0.85 + 0.15 * (
            shorter / max(1, longer)
        )

    ta = tokens(a)
    tb = tokens(b)

    if not ta or not tb:
        return 0.0

    inter = len(
        ta & tb
    )

    union = len(
        ta | tb
    )

    jaccard = (
        inter / union
        if union
        else 0.0
    )

    containment = (
        inter / min(
            len(ta),
            len(tb),
        )
        if min(len(ta), len(tb))
        else 0.0
    )

    return (
        0.45 * jaccard
        + 0.55 * containment
    )


def find_relink_candidate(
    invalid_entity,
    expected_type,
    entities,
):
    invalid_id = entity_id(
        invalid_entity
    )

    invalid_text = entity_text(
        invalid_entity
    )

    page = entity_page(
        invalid_entity
    )

    scored = []

    for e in entities:
        if entity_id(e) == invalid_id:
            continue

        if entity_type(e) != expected_type:
            continue

        # Prefer same page, but allow document-level fallback.
        same_page = (
            page is not None
            and str(entity_page(e))
            == str(page)
        )

        score = text_similarity(
            invalid_text,
            entity_text(e),
        )

        if same_page:
            score += 0.08

        scored.append({
            "entity": e,
            "score": min(score, 1.0),
            "same_page": same_page,
        })

    scored.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    if not scored:
        return None, []

    best = scored[0]
    second = (
        scored[1]
        if len(scored) > 1
        else None
    )

    margin = (
        best["score"]
        - second["score"]
        if second
        else best["score"]
    )

    if (
        best["score"] >= RELINK_MIN_SCORE
        and margin >= RELINK_MIN_MARGIN
    ):
        return best, scored[:5]

    return None, scored[:5]


# ============================================================
# 5. STRUCTURAL TYPE VOTING
# ============================================================

def expected_type_votes_for_entity(
    doc,
    eid,
    signatures,
    exclude_relation_id=None,
):
    """
    For every valid locked relation involving this entity,
    determine which type the signature expects for that role.
    """

    votes = Counter()
    supporting_relations = []

    for r in get_relations(doc):
        rid = relation_id(r)

        if (
            exclude_relation_id
            and str(rid)
            == str(exclude_relation_id)
        ):
            continue

        rtype = relation_type(r)

        if rtype not in signatures:
            continue

        src = relation_source(r)
        tgt = relation_target(r)

        expected_src, expected_tgt = (
            signatures[rtype]
        )

        if str(src) == str(eid):
            votes[
                expected_src
            ] += 1

            supporting_relations.append({
                "relation_id": rid,
                "relation_type": rtype,
                "role": "SOURCE",
                "expected_type": expected_src,
            })

        if str(tgt) == str(eid):
            votes[
                expected_tgt
            ] += 1

            supporting_relations.append({
                "relation_id": rid,
                "relation_type": rtype,
                "role": "TARGET",
                "expected_type": expected_tgt,
            })

    return votes, supporting_relations


def retype_decision(
    doc,
    invalid_entity,
    expected_type,
    signatures,
    current_relation_id,
):
    eid = entity_id(
        invalid_entity
    )

    actual = entity_type(
        invalid_entity
    )

    votes, supports = expected_type_votes_for_entity(
        doc,
        eid,
        signatures,
        exclude_relation_id=current_relation_id,
    )

    total = sum(
        votes.values()
    )

    expected_votes = votes.get(
        expected_type,
        0
    )

    actual_votes = votes.get(
        actual,
        0
    )

    purity = (
        expected_votes / total
        if total
        else 0.0
    )

    safe = (
        expected_votes >= RETYPE_MIN_EXPECTED_VOTES
        and purity >= RETYPE_MIN_PURITY
        and actual_votes == 0
    )

    return {
        "safe": safe,
        "votes": dict(votes),
        "supporting_relations": supports,
        "expected_votes": expected_votes,
        "actual_votes": actual_votes,
        "total_votes": total,
        "purity": round(purity, 4),
    }


# ============================================================
# 6. SUPPORT FOR CURRENT TYPES
# ============================================================

def current_type_support(
    doc,
    entity,
    signatures,
    exclude_relation_id,
):
    eid = entity_id(
        entity
    )

    actual = entity_type(
        entity
    )

    votes, supports = expected_type_votes_for_entity(
        doc,
        eid,
        signatures,
        exclude_relation_id=exclude_relation_id,
    )

    return {
        "actual_type": actual,
        "actual_type_votes": votes.get(
            actual,
            0
        ),
        "all_votes": dict(votes),
        "supporting_relations": supports,
    }


# ============================================================
# 7. VALIDATE CANDIDATE
# ============================================================

def validate_candidate(
    candidate,
    doc,
    signatures,
):
    relation_info = (
        candidate.get("relation")
        or {}
    )

    relation_id_value = (
        relation_info.get(
            "relation_id"
        )
    )

    relation_type_value = (
        relation_info.get(
            "relation_type"
        )
    )

    entities = get_entities(
        doc
    )

    entity_map = {
        entity_id(e): e
        for e in entities
        if entity_id(e)
    }

    src_id = relation_info.get(
        "source_id"
    )

    tgt_id = relation_info.get(
        "target_id"
    )

    source_entity = entity_map.get(
        src_id
    )

    target_entity = entity_map.get(
        tgt_id
    )

    result = {
        **candidate,
        "validation_status":
            None,

        "recommended_future_action":
            "NONE",

        "action_details":
            {},

        "validation_reason":
            "",
    }

    if (
        source_entity is None
        or target_entity is None
    ):
        result[
            "validation_status"
        ] = "SKIP_ORPHAN_ENDPOINT"

        result[
            "validation_reason"
        ] = (
            "Endpoint absent; ce cas appartient à B1, "
            "pas à Pattern D."
        )

        return result

    expected_source, expected_target = (
        signatures[
            relation_type_value
        ]
    )

    is_source_case = (
        candidate.get(
            "anomaly_type"
        )
        == "INVALID_RELATION_SOURCE_TYPE"
    )

    if is_source_case:
        invalid_entity = (
            source_entity
        )

        expected_type = (
            expected_source
        )

        role = "SOURCE"

    else:
        invalid_entity = (
            target_entity
        )

        expected_type = (
            expected_target
        )

        role = "TARGET"

    # --------------------------------------------------------
    # A. Try RELINK first
    # --------------------------------------------------------

    best_relink, top_matches = (
        find_relink_candidate(
            invalid_entity,
            expected_type,
            entities,
        )
    )

    if best_relink is not None:
        replacement = (
            best_relink[
                "entity"
            ]
        )

        result[
            "validation_status"
        ] = "CONFIRMED_RELINK"

        result[
            "recommended_future_action"
        ] = "RELINK"

        result[
            "action_details"
        ] = {
            "role":
                role,

            "old_entity_id":
                entity_id(
                    invalid_entity
                ),

            "new_entity_id":
                entity_id(
                    replacement
                ),

            "new_entity_type":
                entity_type(
                    replacement
                ),

            "new_entity_text":
                entity_text(
                    replacement
                ),

            "similarity_score":
                round(
                    best_relink[
                        "score"
                    ],
                    4,
                ),

            "same_page":
                best_relink[
                    "same_page"
                ],
        }

        result[
            "validation_reason"
        ] = (
            "Une entité existante du type attendu correspond "
            "de manière unique à l'endpoint fautif."
        )

        return result

    # --------------------------------------------------------
    # B. Try RETYPE_ENTITY
    # --------------------------------------------------------

    retype = retype_decision(
        doc,
        invalid_entity,
        expected_type,
        signatures,
        relation_id_value,
    )

    if retype["safe"]:
        result[
            "validation_status"
        ] = "CONFIRMED_RETYPE"

        result[
            "recommended_future_action"
        ] = "RETYPE_ENTITY"

        result[
            "action_details"
        ] = {
            "entity_id":
                entity_id(
                    invalid_entity
                ),

            "old_type":
                entity_type(
                    invalid_entity
                ),

            "new_type":
                expected_type,

            "votes":
                retype[
                    "votes"
                ],

            "purity":
                retype[
                    "purity"
                ],
        }

        result[
            "validation_reason"
        ] = (
            "Les autres relations de l'entité convergent fortement "
            "vers le type attendu."
        )

        return result

    # --------------------------------------------------------
    # C. Try REMOVE_INVALID_RELATION
    # --------------------------------------------------------

    source_support = current_type_support(
        doc,
        source_entity,
        signatures,
        relation_id_value,
    )

    target_support = current_type_support(
        doc,
        target_entity,
        signatures,
        relation_id_value,
    )

    source_supported = (
        source_support[
            "actual_type_votes"
        ]
        >= REMOVE_MIN_CURRENT_TYPE_SUPPORT
    )

    target_supported = (
        target_support[
            "actual_type_votes"
        ]
        >= REMOVE_MIN_CURRENT_TYPE_SUPPORT
    )

    # For removing the relation, both endpoints should be structurally
    # well-supported in their CURRENT types by other valid relations.
    if (
        source_supported
        and target_supported
    ):
        result[
            "validation_status"
        ] = "CONFIRMED_INVALID_RELATION"

        result[
            "recommended_future_action"
        ] = "REMOVE_INVALID_RELATION"

        result[
            "action_details"
        ] = {
            "relation_id":
                relation_id_value,

            "relation_type":
                relation_type_value,

            "source_current_type_support":
                source_support[
                    "actual_type_votes"
                ],

            "target_current_type_support":
                target_support[
                    "actual_type_votes"
                ],
        }

        result[
            "validation_reason"
        ] = (
            "Les deux endpoints sont fortement supportés dans leurs "
            "types actuels par d'autres relations valides; la relation "
            "fautive apparaît comme l'élément incohérent."
        )

        return result

    # --------------------------------------------------------
    # D. Protected
    # --------------------------------------------------------

    result[
        "validation_status"
    ] = "AMBIGUOUS"

    result[
        "recommended_future_action"
    ] = "NONE"

    result[
        "action_details"
    ] = {
        "role":
            role,

        "expected_type":
            expected_type,

        "actual_type":
            entity_type(
                invalid_entity
            ),

        "relink_top_matches": [
            {
                "entity_id":
                    entity_id(
                        x[
                            "entity"
                        ]
                    ),

                "entity_type":
                    entity_type(
                        x[
                            "entity"
                        ]
                    ),

                "entity_text":
                    entity_text(
                        x[
                            "entity"
                        ]
                    ),

                "score":
                    round(
                        x[
                            "score"
                        ],
                        4,
                    ),
            }
            for x in top_matches
        ],

        "retype_votes":
            retype[
                "votes"
            ],

        "retype_purity":
            retype[
                "purity"
            ],

        "source_current_type_support":
            source_support[
                "actual_type_votes"
            ],

        "target_current_type_support":
            target_support[
                "actual_type_votes"
            ],
    }

    result[
        "validation_reason"
    ] = (
        "Aucune correction automatique suffisamment sûre "
        "n'a été démontrée."
    )

    return result


# ============================================================
# 8. MAIN
# ============================================================

def main():

    if not INPUT_DIR.exists():
        raise FileNotFoundError(
            f"Entrée Pattern D introuvable : {INPUT_DIR}"
        )

    if not DETECTION_REPORT.exists():
        raise FileNotFoundError(
            f"Rapport détection Pattern D introuvable : "
            f"{DETECTION_REPORT}"
        )

    guideline_path = (
        resolve_guideline()
    )

    guideline = load_json(
        guideline_path
    )

    signatures = get_locked_signatures(
        guideline
    )

    detection = load_json(
        DETECTION_REPORT
    )

    candidates = detection.get(
        "candidates",
        []
    )

    documents = {}

    skipped_nonclinical = []

    errors = []

    for p in sorted(
        INPUT_DIR.glob(
            "*.json"
        )
    ):
        if p.name == (
            "pattern_c_correction_report.json"
        ):
            continue

        try:
            doc = load_json(
                p
            )

            if is_clinical_document(
                doc
            ):
                documents[
                    p.name
                ] = doc
            else:
                skipped_nonclinical.append(
                    p.name
                )

        except Exception as exc:
            errors.append({
                "document":
                    p.name,

                "error":
                    str(
                        exc
                    ),
            })

    validated = []

    for candidate in candidates:
        doc_name = candidate.get(
            "document"
        )

        doc = documents.get(
            doc_name
        )

        if doc is None:
            validated.append({
                **candidate,
                "validation_status":
                    "AMBIGUOUS",

                "recommended_future_action":
                    "NONE",

                "action_details":
                    {},

                "validation_reason":
                    "Document clinique introuvable.",
            })

            continue

        try:
            validated.append(
                validate_candidate(
                    candidate,
                    doc,
                    signatures,
                )
            )

        except Exception as exc:
            validated.append({
                **candidate,
                "validation_status":
                    "AMBIGUOUS",

                "recommended_future_action":
                    "NONE",

                "action_details":
                    {
                        "error":
                            str(exc)
                    },

                "validation_reason":
                    "Erreur pendant la validation automatique.",
            })

    status_counts = Counter(
        c.get(
            "validation_status",
            ""
        )
        for c in validated
    )

    action_counts = Counter(
        c.get(
            "recommended_future_action",
            ""
        )
        for c in validated
    )

    protected = sum(
        1
        for c in validated
        if c.get(
            "recommended_future_action"
        )
        in {
            "NONE",
            "SKIP",
        }
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    report = {
        "pattern":
            "D",

        "stage":
            "VALIDATION",

        "input_directory":
            str(
                INPUT_DIR
            ),

        "detection_report":
            str(
                DETECTION_REPORT
            ),

        "guideline":
            str(
                guideline_path
            ),

        "thresholds": {
            "relink_min_score":
                RELINK_MIN_SCORE,

            "relink_min_margin":
                RELINK_MIN_MARGIN,

            "retype_min_expected_votes":
                RETYPE_MIN_EXPECTED_VOTES,

            "retype_min_purity":
                RETYPE_MIN_PURITY,

            "remove_min_current_type_support":
                REMOVE_MIN_CURRENT_TYPE_SUPPORT,
        },

        "summary": {
            "clinical_documents":
                len(
                    documents
                ),

            "candidates_detected":
                len(
                    candidates
                ),

            "candidates_validated":
                len(
                    validated
                ),

            "confirmed_relink":
                status_counts.get(
                    "CONFIRMED_RELINK",
                    0,
                ),

            "confirmed_retype":
                status_counts.get(
                    "CONFIRMED_RETYPE",
                    0,
                ),

            "confirmed_invalid_relation":
                status_counts.get(
                    "CONFIRMED_INVALID_RELATION",
                    0,
                ),

            "ambiguous":
                status_counts.get(
                    "AMBIGUOUS",
                    0,
                ),

            "skip_orphan_endpoint":
                status_counts.get(
                    "SKIP_ORPHAN_ENDPOINT",
                    0,
                ),

            "future_relink":
                action_counts.get(
                    "RELINK",
                    0,
                ),

            "future_retype_entity":
                action_counts.get(
                    "RETYPE_ENTITY",
                    0,
                ),

            "future_remove_invalid_relation":
                action_counts.get(
                    "REMOVE_INVALID_RELATION",
                    0,
                ),

            "protected":
                protected,

            "errors":
                len(
                    errors
                ),
        },

        "validated_candidates":
            validated,

        "errors":
            errors,

        "nonclinical_json_skipped":
            skipped_nonclinical,
    }

    OUTPUT_JSON.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # ========================================================
    # CSV
    # ========================================================

    fields = [
        "candidate_id",
        "document",
        "subcase",
        "anomaly_type",
        "relation_id",
        "relation_type",
        "source_id",
        "source_type_actual",
        "source_type_expected",
        "target_id",
        "target_type_actual",
        "target_type_expected",
        "validation_status",
        "recommended_future_action",
        "action_details",
        "validation_reason",
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

        for c in validated:

            rel = (
                c.get(
                    "relation"
                )
                or {}
            )

            src = (
                c.get(
                    "source_entity"
                )
                or {}
            )

            tgt = (
                c.get(
                    "target_entity"
                )
                or {}
            )

            writer.writerow({
                "candidate_id":
                    c.get(
                        "candidate_id",
                        "",
                    ),

                "document":
                    c.get(
                        "document",
                        "",
                    ),

                "subcase":
                    c.get(
                        "subcase",
                        "",
                    ),

                "anomaly_type":
                    c.get(
                        "anomaly_type",
                        "",
                    ),

                "relation_id":
                    rel.get(
                        "relation_id",
                        "",
                    ),

                "relation_type":
                    rel.get(
                        "relation_type",
                        "",
                    ),

                "source_id":
                    src.get(
                        "id",
                        "",
                    ),

                "source_type_actual":
                    src.get(
                        "type_actual",
                        "",
                    ),

                "source_type_expected":
                    src.get(
                        "type_expected",
                        "",
                    ),

                "target_id":
                    tgt.get(
                        "id",
                        "",
                    ),

                "target_type_actual":
                    tgt.get(
                        "type_actual",
                        "",
                    ),

                "target_type_expected":
                    tgt.get(
                        "type_expected",
                        "",
                    ),

                "validation_status":
                    c.get(
                        "validation_status",
                        "",
                    ),

                "recommended_future_action":
                    c.get(
                        "recommended_future_action",
                        "",
                    ),

                "action_details":
                    json.dumps(
                        c.get(
                            "action_details",
                            {},
                        ),
                        ensure_ascii=False,
                    ),

                "validation_reason":
                    c.get(
                        "validation_reason",
                        "",
                    ),
            })

    # ========================================================
    # Console
    # ========================================================

    print("=" * 88)
    print("SGCE - PATTERN D VALIDATION")
    print("=" * 88)

    print(
        f"Entrée clinique                   : "
        f"{INPUT_DIR}"
    )

    print(
        f"Rapport détection                 : "
        f"{DETECTION_REPORT}"
    )

    print()

    print(
        f"Documents cliniques               : "
        f"{len(documents)}"
    )

    print(
        f"Candidats détectés                : "
        f"{len(candidates)}"
    )

    print(
        f"Candidats validés                 : "
        f"{len(validated)}"
    )

    print()

    print(
        f"CONFIRMED_RELINK                  : "
        f"{status_counts.get('CONFIRMED_RELINK', 0)}"
    )

    print(
        f"CONFIRMED_RETYPE                  : "
        f"{status_counts.get('CONFIRMED_RETYPE', 0)}"
    )

    print(
        f"CONFIRMED_INVALID_RELATION        : "
        f"{status_counts.get('CONFIRMED_INVALID_RELATION', 0)}"
    )

    print(
        f"AMBIGUOUS                         : "
        f"{status_counts.get('AMBIGUOUS', 0)}"
    )

    print(
        f"SKIP_ORPHAN_ENDPOINT              : "
        f"{status_counts.get('SKIP_ORPHAN_ENDPOINT', 0)}"
    )

    print()

    print(
        f"Futurs RELINK                     : "
        f"{action_counts.get('RELINK', 0)}"
    )

    print(
        f"Futurs RETYPE_ENTITY              : "
        f"{action_counts.get('RETYPE_ENTITY', 0)}"
    )

    print(
        f"Futurs REMOVE_INVALID_RELATION    : "
        f"{action_counts.get('REMOVE_INVALID_RELATION', 0)}"
    )

    print(
        f"Cas protégés                      : "
        f"{protected}"
    )

    print(
        f"Erreurs                           : "
        f"{len(errors)}"
    )

    print()

    print(
        f"Rapport JSON                      : "
        f"{OUTPUT_JSON}"
    )

    print(
        f"CSV validation                    : "
        f"{OUTPUT_CSV}"
    )

    print()

    print(
        "Aucun JSON clinique n'a été modifié."
    )


if __name__ == "__main__":
    main()
