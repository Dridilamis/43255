# -*- coding: utf-8 -*-
"""
pattern_a4_validator.py
=======================

SGCE — Pattern A4 Validator

A4:
IMAGERIE_PROCEDURE + DEFAILLANCE_ORGANE

Relation:
    IMAGERIE_PROCEDURE
        --imagerie_objective_defaillance-->
    DEFAILLANCE_ORGANE

Décisions
---------
ALREADY_CORRECT
    Une DEFAILLANCE_ORGANE fiable existe et la relation existe déjà.

MISSING_RELATION
    Une DEFAILLANCE_ORGANE fiable existe mais la relation manque.

CONFIRMED_PATTERN_A
    Réservé uniquement aux candidats MEDIUM/STRONG avec preuve textuelle
    explicite de défaillance dans IMAGERIE_PROCEDURE et sans cible fiable.

AMBIGUOUS
    Preuve insuffisante.

Sécurité
--------
Un candidat WEAK sans signal textuel explicite ne peut JAMAIS devenir
CONFIRMED_PATTERN_A.

Aucun JSON clinique n'est modifié.
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

PATTERN_A4_DIR = Path(__file__).resolve().parent
PATTERN_A_DIR = PATTERN_A4_DIR.parent
PATTERNS_DIR = PATTERN_A_DIR.parent
SGCE_DIR = PATTERNS_DIR.parent
BASE_DIR = SGCE_DIR.parent
PATTERN_A3_DIR = PATTERN_A_DIR / "PatternA3"

INPUT_DIR_CANDIDATES = [
    PATTERN_A3_DIR / "corrected",
]

DETECTION_REPORT_CANDIDATES = [
    PATTERN_A4_DIR / "detection" / "pattern_a4_detection_report.json",
]

OUTPUT_DIR = PATTERN_A4_DIR / "validation"
OUTPUT_JSON = OUTPUT_DIR / "pattern_a4_validation_report.json"
OUTPUT_CSV = OUTPUT_DIR / "pattern_a4_validation_candidates.csv"

SOURCE_TYPE = "IMAGERIE_PROCEDURE"
TARGET_TYPE = "DEFAILLANCE_ORGANE"
RELATION_TYPE = "imagerie_objective_defaillance"

RELIABLE_OVERLAP_THRESHOLD = 0.60


# ============================================================
# 2. HELPERS
# ============================================================

def normalize(text):
    text = "" if text is None else str(text)
    text = text.replace("’", "'")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    return re.sub(r"\s+", " ", text).strip()


def resolve_input_dir():
    for p in INPUT_DIR_CANDIDATES:
        if p.exists() and any(p.glob("*.json")):
            return p
    raise FileNotFoundError("Aucun dossier JSON clinique trouvé.")


def resolve_detection_report():
    for p in DETECTION_REPORT_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError(
        "Rapport de détection A4 introuvable.\n"
        + "\n".join(f"- {p}" for p in DETECTION_REPORT_CANDIDATES)
    )


def entity_id(e):
    return e.get("identifiant_entite") or e.get("id") or e.get("entity_id")


def entity_type(e):
    return e.get("categorie") or e.get("type") or ""


def entity_page(e):
    if e.get("page") is not None:
        return e.get("page")
    return e.get("page_number")


def entity_text(e):
    vals = []
    for k in ("preuve", "name", "valeur", "libelle", "parametre", "texte", "text"):
        v = e.get(k)
        if v not in (None, ""):
            s = str(v).strip()
            if s and s not in vals:
                vals.append(s)
    return " | ".join(vals)


def relation_type(r):
    return r.get("type_relation") or r.get("relation") or r.get("type") or ""


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
    for p in doc.get("pages", []) or []:
        out.extend(p.get("entities", []) or [])
    return out


def get_relations(doc):
    if isinstance(doc.get("global_relations"), list):
        return doc["global_relations"]

    out = []
    for p in doc.get("pages", []) or []:
        out.extend(p.get("relations", []) or [])
    return out


def is_clinical_document(doc):
    return (
        isinstance(doc, dict)
        and (
            isinstance(doc.get("global_entities"), list)
            or isinstance(doc.get("pages"), list)
        )
    )


def token_set(text):
    return {
        t for t in re.findall(r"[a-z0-9]+", normalize(text))
        if len(t) >= 3
    }


def token_overlap(a, b):
    ta, tb = token_set(a), token_set(b)

    if not ta or not tb:
        return 0.0

    return len(ta & tb) / min(len(ta), len(tb))


def relation_exists(source_id, target_id, relations):
    return any(
        relation_type(r) == RELATION_TYPE
        and relation_source(r) == source_id
        and relation_target(r) == target_id
        for r in relations
    )


# ============================================================
# 3. TARGET MATCHING
# ============================================================

def find_failure_targets(source, entities, relations):
    src_page = entity_page(source)
    src_text = entity_text(source)
    src_norm = normalize(src_text)
    src_id = entity_id(source)

    targets = []

    for e in entities:
        if entity_type(e) != TARGET_TYPE:
            continue

        if entity_page(e) != src_page:
            continue

        tgt_text = entity_text(e)
        tgt_norm = normalize(tgt_text)

        containment = bool(
            src_norm and tgt_norm
            and (
                tgt_norm in src_norm
                or src_norm in tgt_norm
            )
        )

        overlap = token_overlap(src_text, tgt_text)

        reliable = (
            containment
            or overlap >= RELIABLE_OVERLAP_THRESHOLD
        )

        score = (
            (0.55 if containment else 0.0)
            + 0.45 * overlap
        )

        targets.append({
            "entity_id": entity_id(e),
            "page": entity_page(e),
            "text": tgt_text,
            "containment": containment,
            "token_overlap": round(overlap, 4),
            "score": round(score, 4),
            "reliable": reliable,
            "relation_exists": relation_exists(
                src_id,
                entity_id(e),
                relations,
            ),
        })

    targets.sort(
        key=lambda x: (
            x["reliable"],
            x["containment"],
            x["token_overlap"],
            x["score"],
        ),
        reverse=True,
    )

    return targets


# ============================================================
# 4. VALIDATION
# ============================================================

def validate_candidate(candidate, doc):
    entities = get_entities(doc)
    relations = get_relations(doc)

    source_info = candidate.get("source_entity") or {}
    source_id = source_info.get("entity_id")

    source = next(
        (
            e for e in entities
            if entity_id(e) == source_id
            and entity_type(e) == SOURCE_TYPE
        ),
        None,
    )

    if source is None:
        return {
            **candidate,
            "validation_status": "AMBIGUOUS",
            "recommended_future_action": "NONE",
            "validation_reason": "Source IMAGERIE_PROCEDURE introuvable.",
            "reliable_target": None,
            "same_page_failure_targets_recomputed": [],
        }

    targets = find_failure_targets(
        source,
        entities,
        relations,
    )

    reliable_targets = [
        t for t in targets
        if t["reliable"]
    ]

    best = (
        reliable_targets[0]
        if reliable_targets
        else None
    )

    strength = candidate.get("strength", "")
    explicit_families = (
        candidate.get("detected_failure_families")
        or []
    )
    explicit_signals = (
        candidate.get("detected_failure_signals")
        or {}
    )

    has_explicit_failure_signal = bool(
        explicit_families
        and any(explicit_signals.values())
    )

    # 1. Relation déjà correcte
    if best and best["relation_exists"]:
        status = "ALREADY_CORRECT"
        action = "SKIP"
        reason = (
            "Une DEFAILLANCE_ORGANE fiable est déjà séparée "
            "et la relation imagerie_objective_defaillance existe déjà."
        )

    # 2. Cible existante, relation manquante
    elif best and not best["relation_exists"]:
        status = "MISSING_RELATION"
        action = "LINK"
        reason = (
            "Une DEFAILLANCE_ORGANE fiable est déjà séparée sur la même page, "
            "mais la relation imagerie_objective_defaillance est absente."
        )

    # 3. Composite explicite — jamais pour WEAK
    elif (
        strength in {"MEDIUM", "STRONG"}
        and has_explicit_failure_signal
        and not reliable_targets
    ):
        status = "CONFIRMED_PATTERN_A"
        action = "SPLIT"
        reason = (
            "L'entité IMAGERIE_PROCEDURE contient un signal explicite de "
            "défaillance d'organe sans DEFAILLANCE_ORGANE fiable séparée."
        )

    # 4. Protection
    else:
        status = "AMBIGUOUS"
        action = "NONE"
        reason = (
            "Preuve structurelle insuffisante. Un candidat WEAK sans signal "
            "textuel explicite n'est jamais automatiquement décomposé."
        )

    return {
        **candidate,
        "validation_status": status,
        "recommended_future_action": action,
        "validation_reason": reason,
        "reliable_target": best,
        "same_page_failure_targets_recomputed": targets,
    }


# ============================================================
# 5. MAIN
# ============================================================

def main():
    input_dir = resolve_input_dir()
    detection_report = resolve_detection_report()

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with detection_report.open(
        "r",
        encoding="utf-8",
    ) as f:
        detection = json.load(f)

    candidates = detection.get(
        "candidates",
        [],
    )

    docs = {}
    skipped_nonclinical = []
    errors = []

    for path in sorted(input_dir.glob("*.json")):
        try:
            with path.open(
                "r",
                encoding="utf-8",
            ) as f:
                doc = json.load(f)

            if not is_clinical_document(doc):
                skipped_nonclinical.append(
                    path.name
                )
                continue

            docs[path.name] = doc

        except Exception as exc:
            errors.append({
                "document": path.name,
                "error": str(exc),
            })

    validated = []

    for candidate in candidates:
        filename = candidate.get("document")
        doc = docs.get(filename)

        if doc is None:
            errors.append({
                "document": filename,
                "source_entity_id": (
                    candidate.get("source_entity")
                    or {}
                ).get("entity_id"),
                "error": (
                    "Document clinique correspondant introuvable."
                ),
            })
            continue

        try:
            validated.append(
                validate_candidate(
                    candidate,
                    doc,
                )
            )
        except Exception as exc:
            errors.append({
                "document": filename,
                "source_entity_id": (
                    candidate.get("source_entity")
                    or {}
                ).get("entity_id"),
                "error": str(exc),
            })

    statuses = Counter(
        v["validation_status"]
        for v in validated
    )

    actions = Counter(
        v["recommended_future_action"]
        for v in validated
    )

    report = {
        "pattern": "A4",
        "name": (
            "IMAGERIE_PROCEDURE + "
            "DEFAILLANCE_ORGANE"
        ),
        "relation": RELATION_TYPE,
        "methodological_status": (
            "VALIDATION_ONLY_NO_CORRECTION"
        ),
        "input_directory": str(input_dir),
        "detection_report": str(detection_report),

        "summary": {
            "clinical_documents_loaded": len(docs),
            "candidates_detected": len(candidates),
            "candidates_validated": len(validated),

            "already_correct":
                statuses.get("ALREADY_CORRECT", 0),

            "missing_relation":
                statuses.get("MISSING_RELATION", 0),

            "confirmed_pattern_a":
                statuses.get("CONFIRMED_PATTERN_A", 0),

            "ambiguous":
                statuses.get("AMBIGUOUS", 0),

            "future_link":
                actions.get("LINK", 0),

            "future_split":
                actions.get("SPLIT", 0),

            "protected":
                actions.get("SKIP", 0)
                + actions.get("NONE", 0),

            "errors": len(errors),
        },

        "validated_candidates": validated,
        "nonclinical_json_skipped": skipped_nonclinical,
        "errors": errors,
    }

    OUTPUT_JSON.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    fields = [
        "document",
        "source_entity_id",
        "page",
        "source_text",
        "strength",
        "families",
        "validation_status",
        "recommended_future_action",
        "reliable_target_id",
        "reliable_target_text",
        "reliable_target_overlap",
        "reliable_target_containment",
        "relation_exists",
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

        for item in validated:
            source = item.get(
                "source_entity"
            ) or {}

            target = item.get(
                "reliable_target"
            ) or {}

            writer.writerow({
                "document":
                    item.get("document", ""),

                "source_entity_id":
                    source.get("entity_id", ""),

                "page":
                    source.get("page", ""),

                "source_text":
                    source.get("text", ""),

                "strength":
                    item.get("strength", ""),

                "families":
                    "; ".join(
                        item.get(
                            "detected_failure_families"
                        )
                        or []
                    ),

                "validation_status":
                    item.get(
                        "validation_status",
                        "",
                    ),

                "recommended_future_action":
                    item.get(
                        "recommended_future_action",
                        "",
                    ),

                "reliable_target_id":
                    target.get("entity_id", ""),

                "reliable_target_text":
                    target.get("text", ""),

                "reliable_target_overlap":
                    target.get(
                        "token_overlap",
                        "",
                    ),

                "reliable_target_containment":
                    target.get(
                        "containment",
                        "",
                    ),

                "relation_exists":
                    target.get(
                        "relation_exists",
                        "",
                    ),

                "validation_reason":
                    item.get(
                        "validation_reason",
                        "",
                    ),
            })

    print("=" * 76)
    print("SGCE - PATTERN A4 VALIDATION")
    print("=" * 76)
    print(f"Entrée clinique           : {input_dir}")
    print(f"Rapport détection         : {detection_report}")
    print(f"Documents cliniques       : {len(docs)}")
    print()
    print(f"Candidats détectés        : {len(candidates)}")
    print(f"Candidats validés         : {len(validated)}")
    print()
    print(f"ALREADY_CORRECT           : {statuses.get('ALREADY_CORRECT', 0)}")
    print(f"MISSING_RELATION          : {statuses.get('MISSING_RELATION', 0)}")
    print(f"CONFIRMED_PATTERN_A       : {statuses.get('CONFIRMED_PATTERN_A', 0)}")
    print(f"AMBIGUOUS                 : {statuses.get('AMBIGUOUS', 0)}")
    print()
    print(f"Futurs LINK               : {actions.get('LINK', 0)}")
    print(f"Futurs SPLIT              : {actions.get('SPLIT', 0)}")
    print(f"Cas protégés              : {actions.get('SKIP', 0) + actions.get('NONE', 0)}")
    print(f"Erreurs                   : {len(errors)}")
    print()
    print(f"Rapport JSON              : {OUTPUT_JSON}")
    print(f"CSV validation            : {OUTPUT_CSV}")
    print()
    print("Aucun JSON clinique n'a été modifié.")


if __name__ == "__main__":
    main()
