# -*- coding: utf-8 -*-
"""
pattern_d_detector.py
=====================

SGCE — Pattern D Detection Only

Pattern D:
Violation de signature relationnelle (Domain–Range Mismatch)

Sous-cas:
D1 = INVALID_RELATION_SOURCE_TYPE
D2 = INVALID_RELATION_TARGET_TYPE

Objectif
--------
Détecter toutes les relations TRACE-Sepsis autorisées dont:
- le type réel de la source ne correspond pas au domaine attendu, et/ou
- le type réel de la cible ne correspond pas à l'image attendue.

IMPORTANT
---------
- Aucun JSON clinique n'est modifié.
- Entrée STRICTE : PatternC/pattern_c_corrected
- Aucun fallback vers Pattern B ou A.
- Les 32 signatures verrouillées du guideline sont utilisées.

Sorties
-------
PatternD/pattern_d_detection/pattern_d_detection_report.json
PatternD/pattern_d_detection/pattern_d_candidates.csv
"""

import csv
import json
from collections import Counter
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

GUIDELINE_CANDIDATES = [
    BASE_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
    BASE_DIR.parent / "Guideline_TRACE_Sepsis_v1.6.json",
    Path.cwd() / "Guideline_TRACE_Sepsis_v1.6.json",
    PATTERN_D_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
]

OUTPUT_DIR = PATTERN_D_DIR / "detection"
OUTPUT_JSON = OUTPUT_DIR / "pattern_d_detection_report.json"
OUTPUT_CSV = OUTPUT_DIR / "pattern_d_candidates.csv"


# ============================================================
# 2. HELPERS
# ============================================================

def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_input_dir():
    if not INPUT_DIR.exists():
        raise FileNotFoundError(
            f"Sortie finale Pattern C introuvable : {INPUT_DIR}"
        )

    if not any(INPUT_DIR.glob("*.json")):
        raise FileNotFoundError(
            f"Aucun JSON trouvé dans : {INPUT_DIR}"
        )

    return INPUT_DIR


def resolve_guideline():
    for path in GUIDELINE_CANDIDATES:
        if path.exists():
            return path

    raise FileNotFoundError(
        "Guideline_TRACE_Sepsis_v1.6.json introuvable."
    )


def is_clinical_document(doc):
    return (
        isinstance(doc, dict)
        and (
            isinstance(doc.get("global_entities"), list)
            or isinstance(doc.get("pages"), list)
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
        or ""
    )


def entity_text(e):
    for key in (
        "preuve",
        "name",
        "valeur",
        "libelle",
        "parametre",
        "texte",
        "text",
    ):
        value = e.get(key)
        if value not in (None, ""):
            return str(value).strip()

    return ""


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
        or r.get("sujet")
        or r.get("subject")
    )


def relation_target(r):
    return (
        r.get("identifiant_entite_objet")
        or r.get("to_id")
        or r.get("object_id")
        or r.get("objet")
        or r.get("object")
    )


def relation_page(r):
    if r.get("page") is not None:
        return r.get("page")

    return r.get("page_number")


def get_entities(doc):
    if isinstance(doc.get("global_entities"), list):
        return doc["global_entities"]

    out = []

    for page in doc.get("pages", []) or []:
        out.extend(
            page.get("entities", []) or []
        )

    return out


def get_relations(doc):
    if isinstance(doc.get("global_relations"), list):
        return doc["global_relations"]

    out = []

    for page in doc.get("pages", []) or []:
        out.extend(
            page.get("relations", []) or []
        )

    return out


# ============================================================
# 3. GUIDELINE SIGNATURES
# ============================================================

def get_root(guideline):
    return guideline.get(
        "ontologie_sepsis_graph",
        guideline,
    )


def get_locked_signatures(guideline):
    root = get_root(guideline)

    locked = root.get(
        "signatures_relations_verrouillees_v1_5",
        {},
    )

    signatures = {}

    if not isinstance(locked, dict):
        return signatures

    for rtype, spec in locked.items():
        if not isinstance(spec, dict):
            continue

        domain = spec.get("domaine")
        image = spec.get("image")

        if not (domain and image):
            continue

        signatures[rtype] = {
            "domaine": domain,
            "image": image,
            "groupe": spec.get("groupe", ""),
        }

    return signatures


# ============================================================
# 4. MAIN DETECTION
# ============================================================

def main():
    input_dir = resolve_input_dir()
    guideline_path = resolve_guideline()

    guideline = load_json(
        guideline_path
    )

    signatures = get_locked_signatures(
        guideline
    )

    if not signatures:
        raise RuntimeError(
            "Aucune signature TRACE-Sepsis verrouillée chargée."
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    candidates = []
    errors = []
    skipped_nonclinical = []

    clinical_documents = 0
    total_entities = 0
    total_relations = 0
    authorized_relations_checked = 0

    for path in sorted(
        input_dir.glob("*.json")
    ):
        if path.name == "pattern_c_correction_report.json":
            continue

        try:
            doc = load_json(path)

            if not is_clinical_document(doc):
                skipped_nonclinical.append(
                    path.name
                )
                continue

            clinical_documents += 1

            entities = get_entities(doc)
            relations = get_relations(doc)

            total_entities += len(entities)
            total_relations += len(relations)

            entity_map = {
                entity_id(e): e
                for e in entities
                if entity_id(e)
            }

            for relation in relations:
                rtype = relation_type(
                    relation
                )

                # Pattern D only concerns authorized relation types.
                if rtype not in signatures:
                    continue

                authorized_relations_checked += 1

                rid = relation_id(
                    relation
                )

                source_id = relation_source(
                    relation
                )

                target_id = relation_target(
                    relation
                )

                source_entity = entity_map.get(
                    source_id
                )

                target_entity = entity_map.get(
                    target_id
                )

                # Orphans are not Pattern D; they stay conceptually in B1.
                if source_entity is None or target_entity is None:
                    continue

                expected_source = signatures[
                    rtype
                ][
                    "domaine"
                ]

                expected_target = signatures[
                    rtype
                ][
                    "image"
                ]

                actual_source = entity_type(
                    source_entity
                )

                actual_target = entity_type(
                    target_entity
                )

                source_invalid = (
                    actual_source
                    != expected_source
                )

                target_invalid = (
                    actual_target
                    != expected_target
                )

                if not (
                    source_invalid
                    or target_invalid
                ):
                    continue

                # ------------------------------------------------
                # D1
                # ------------------------------------------------

                if source_invalid:
                    candidates.append({
                        "candidate_id":
                            f"D_{len(candidates)+1:06d}",

                        "document":
                            path.name,

                        "pattern":
                            "D",

                        "subcase":
                            "D1_INVALID_RELATION_SOURCE_TYPE",

                        "anomaly_type":
                            "INVALID_RELATION_SOURCE_TYPE",

                        "relation": {
                            "relation_id":
                                rid,

                            "relation_type":
                                rtype,

                            "page":
                                relation_page(
                                    relation
                                ),

                            "source_id":
                                source_id,

                            "target_id":
                                target_id,
                        },

                        "source_entity": {
                            "id":
                                source_id,

                            "type_actual":
                                actual_source,

                            "type_expected":
                                expected_source,

                            "text":
                                entity_text(
                                    source_entity
                                ),

                            "page":
                                entity_page(
                                    source_entity
                                ),
                        },

                        "target_entity": {
                            "id":
                                target_id,

                            "type_actual":
                                actual_target,

                            "type_expected":
                                expected_target,

                            "text":
                                entity_text(
                                    target_entity
                                ),

                            "page":
                                entity_page(
                                    target_entity
                                ),
                        },

                        "source_invalid":
                            True,

                        "target_invalid":
                            target_invalid,

                        "status":
                            "D_CANDIDATE",

                        "safe_to_correct":
                            False,
                    })

                # ------------------------------------------------
                # D2
                # ------------------------------------------------

                if target_invalid:
                    candidates.append({
                        "candidate_id":
                            f"D_{len(candidates)+1:06d}",

                        "document":
                            path.name,

                        "pattern":
                            "D",

                        "subcase":
                            "D2_INVALID_RELATION_TARGET_TYPE",

                        "anomaly_type":
                            "INVALID_RELATION_TARGET_TYPE",

                        "relation": {
                            "relation_id":
                                rid,

                            "relation_type":
                                rtype,

                            "page":
                                relation_page(
                                    relation
                                ),

                            "source_id":
                                source_id,

                            "target_id":
                                target_id,
                        },

                        "source_entity": {
                            "id":
                                source_id,

                            "type_actual":
                                actual_source,

                            "type_expected":
                                expected_source,

                            "text":
                                entity_text(
                                    source_entity
                                ),

                            "page":
                                entity_page(
                                    source_entity
                                ),
                        },

                        "target_entity": {
                            "id":
                                target_id,

                            "type_actual":
                                actual_target,

                            "type_expected":
                                expected_target,

                            "text":
                                entity_text(
                                    target_entity
                                ),

                            "page":
                                entity_page(
                                    target_entity
                                ),
                        },

                        "source_invalid":
                            source_invalid,

                        "target_invalid":
                            True,

                        "status":
                            "D_CANDIDATE",

                        "safe_to_correct":
                            False,
                    })

        except Exception as exc:
            errors.append({
                "document":
                    path.name,

                "error":
                    str(exc),
            })

    # ========================================================
    # Stats
    # ========================================================

    anomaly_counts = Counter(
        c["anomaly_type"]
        for c in candidates
    )

    relation_counts = Counter(
        c["relation"]["relation_type"]
        for c in candidates
    )

    source_type_mismatch_counts = Counter(
        (
            c["source_entity"]["type_actual"],
            c["source_entity"]["type_expected"],
        )
        for c in candidates
        if c["anomaly_type"]
        == "INVALID_RELATION_SOURCE_TYPE"
    )

    target_type_mismatch_counts = Counter(
        (
            c["target_entity"]["type_actual"],
            c["target_entity"]["type_expected"],
        )
        for c in candidates
        if c["anomaly_type"]
        == "INVALID_RELATION_TARGET_TYPE"
    )

    report = {
        "pattern":
            "D",

        "name":
            "Violation de signature relationnelle (Domain-Range Mismatch)",

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

            "entities_analyzed":
                total_entities,

            "relations_analyzed":
                total_relations,

            "locked_signatures_loaded":
                len(
                    signatures
                ),

            "authorized_relations_checked":
                authorized_relations_checked,

            "candidates":
                len(
                    candidates
                ),

            "d1_invalid_source_type":
                anomaly_counts.get(
                    "INVALID_RELATION_SOURCE_TYPE",
                    0,
                ),

            "d2_invalid_target_type":
                anomaly_counts.get(
                    "INVALID_RELATION_TARGET_TYPE",
                    0,
                ),

            "errors":
                len(
                    errors
                ),
        },

        "candidate_counts_by_relation":
            dict(
                relation_counts
            ),

        "source_type_mismatch_counts": [
            {
                "actual":
                    actual,

                "expected":
                    expected,

                "count":
                    count,
            }
            for (
                actual,
                expected
            ), count in (
                source_type_mismatch_counts.most_common()
            )
        ],

        "target_type_mismatch_counts": [
            {
                "actual":
                    actual,

                "expected":
                    expected,

                "count":
                    count,
            }
            for (
                actual,
                expected
            ), count in (
                target_type_mismatch_counts.most_common()
            )
        ],

        "candidates":
            candidates,

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
        "page",
        "source_id",
        "source_text",
        "source_type_actual",
        "source_type_expected",
        "target_id",
        "target_text",
        "target_type_actual",
        "target_type_expected",
        "source_invalid",
        "target_invalid",
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
            rel = candidate["relation"]
            src = candidate["source_entity"]
            tgt = candidate["target_entity"]

            writer.writerow({
                "candidate_id":
                    candidate[
                        "candidate_id"
                    ],

                "document":
                    candidate[
                        "document"
                    ],

                "subcase":
                    candidate[
                        "subcase"
                    ],

                "anomaly_type":
                    candidate[
                        "anomaly_type"
                    ],

                "relation_id":
                    rel[
                        "relation_id"
                    ],

                "relation_type":
                    rel[
                        "relation_type"
                    ],

                "page":
                    rel[
                        "page"
                    ],

                "source_id":
                    src[
                        "id"
                    ],

                "source_text":
                    src[
                        "text"
                    ],

                "source_type_actual":
                    src[
                        "type_actual"
                    ],

                "source_type_expected":
                    src[
                        "type_expected"
                    ],

                "target_id":
                    tgt[
                        "id"
                    ],

                "target_text":
                    tgt[
                        "text"
                    ],

                "target_type_actual":
                    tgt[
                        "type_actual"
                    ],

                "target_type_expected":
                    tgt[
                        "type_expected"
                    ],

                "source_invalid":
                    candidate[
                        "source_invalid"
                    ],

                "target_invalid":
                    candidate[
                        "target_invalid"
                    ],
            })

    # ========================================================
    # Console
    # ========================================================

    print("=" * 88)
    print("SGCE - PATTERN D DETECTION")
    print("=" * 88)

    print(
        f"Entrée clinique                  : "
        f"{input_dir}"
    )

    print(
        f"Guideline                        : "
        f"{guideline_path}"
    )

    print()

    print(
        f"Documents cliniques              : "
        f"{clinical_documents}"
    )

    print(
        f"Entités analysées                : "
        f"{total_entities}"
    )

    print(
        f"Relations analysées              : "
        f"{total_relations}"
    )

    print(
        f"Signatures TRACE chargées        : "
        f"{len(signatures)}"
    )

    print(
        f"Relations autorisées contrôlées  : "
        f"{authorized_relations_checked}"
    )

    print()

    print(
        f"Candidats Pattern D              : "
        f"{len(candidates)}"
    )

    print(
        f"D1 INVALID SOURCE TYPE           : "
        f"{anomaly_counts.get('INVALID_RELATION_SOURCE_TYPE', 0)}"
    )

    print(
        f"D2 INVALID TARGET TYPE           : "
        f"{anomaly_counts.get('INVALID_RELATION_TARGET_TYPE', 0)}"
    )

    print(
        f"Erreurs                          : "
        f"{len(errors)}"
    )

    print()

    print(
        "Relations les plus concernées :"
    )

    if relation_counts:
        for rtype, count in (
            relation_counts.most_common(
                15
            )
        ):
            print(
                f"  {rtype:<50}: {count}"
            )
    else:
        print(
            "  Aucun candidat Pattern D."
        )

    print()

    print(
        "Mismatch source les plus fréquents :"
    )

    if source_type_mismatch_counts:
        for (
            actual,
            expected
        ), count in (
            source_type_mismatch_counts.most_common(
                10
            )
        ):
            print(
                f"  {actual:<28} -> "
                f"{expected:<28} : "
                f"{count}"
            )
    else:
        print(
            "  Aucun."
        )

    print()

    print(
        "Mismatch cible les plus fréquents :"
    )

    if target_type_mismatch_counts:
        for (
            actual,
            expected
        ), count in (
            target_type_mismatch_counts.most_common(
                10
            )
        ):
            print(
                f"  {actual:<28} -> "
                f"{expected:<28} : "
                f"{count}"
            )
    else:
        print(
            "  Aucun."
        )

    print()

    print(
        f"Rapport JSON                     : "
        f"{OUTPUT_JSON}"
    )

    print(
        f"CSV candidats                    : "
        f"{OUTPUT_CSV}"
    )

    print()

    print(
        "Aucun JSON clinique n'a été modifié."
    )


if __name__ == "__main__":
    main()
