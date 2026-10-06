# -*- coding: utf-8 -*-
"""
pattern_a6_validator.py
=======================

SGCE — Pattern A6 Validator

A6:
DONNEE_PATIENT + SYMPTOME

Relation:
    DONNEE_PATIENT
        --presente_symptome-->
    SYMPTOME

Décisions:
- ALREADY_CORRECT
- MISSING_RELATION
- CONFIRMED_PATTERN_A
- AMBIGUOUS

Règle de sécurité:
Un candidat WEAK sans signal textuel explicite ne peut jamais devenir
CONFIRMED_PATTERN_A et ne déclenche jamais un SPLIT automatique.

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

PATTERN_A6_DIR = Path(__file__).resolve().parent
PATTERN_A_DIR = PATTERN_A6_DIR.parent
PATTERNS_DIR = PATTERN_A_DIR.parent
SGCE_DIR = PATTERNS_DIR.parent
BASE_DIR = SGCE_DIR.parent
PATTERN_A5_DIR = PATTERN_A_DIR / "PatternA5"

INPUT_DIR_CANDIDATES = [
    PATTERN_A5_DIR / "corrected",
]

DETECTION_REPORT_CANDIDATES = [
    PATTERN_A6_DIR / "detection" / "pattern_a6_detection_report.json",
]

OUTPUT_DIR = PATTERN_A6_DIR / "validation"
OUTPUT_JSON = OUTPUT_DIR / "pattern_a6_validation_report.json"
OUTPUT_CSV = OUTPUT_DIR / "pattern_a6_validation_candidates.csv"

SOURCE_TYPE = "DONNEE_PATIENT"
TARGET_TYPE = "SYMPTOME"
RELATION_TYPE = "presente_symptome"

RELIABLE_OVERLAP_THRESHOLD = 0.60


# ============================================================
# 2. HELPERS
# ============================================================

def normalize(text):
    text = "" if text is None else str(text)
    text = text.replace("’", "'")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower()).strip()


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
        "Rapport de détection A6 introuvable.\n"
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
    ta = token_set(a)
    tb = token_set(b)

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

def find_symptom_targets(source, entities, relations):
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
            src_norm
            and tgt_norm
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
            "validation_reason": "Source DONNEE_PATIENT introuvable.",
            "reliable_target": None,
            "same_page_symptom_targets_recomputed": [],
        }

    targets = find_symptom_targets(
        source,
        entities,
        relations,
    )

    reliable_targets = [
        t for t in targets
        if t["reliable"]
    ]

    best = reliable_targets[0] if reliable_targets else None

    strength = candidate.get("strength", "")

    explicit_families = (
        candidate.get("detected_symptom_families")
        or []
    )

    explicit_signals = (
        candidate.get("detected_symptom_signals")
        or {}
    )

    has_explicit_signal = bool(
        explicit_families
        and any(explicit_signals.values())
    )

    # 1. Déjà correct
    if best and best["relation_exists"]:
        status = "ALREADY_CORRECT"
        action = "SKIP"
        reason = (
            "Un SYMPTOME fiable est déjà séparé et la relation "
            "presente_symptome existe déjà."
        )

    # 2. Cible fiable existante, relation absente
    elif best and not best["relation_exists"]:
        status = "MISSING_RELATION"
        action = "LINK"
        reason = (
            "Un SYMPTOME fiable existe sur la même page mais la relation "
            "presente_symptome est absente."
        )

    # 3. Composite explicite : SPLIT seulement si preuve textuelle explicite
    elif (
        strength in {"MEDIUM", "STRONG"}
        and has_explicit_signal
        and not reliable_targets
    ):
        status = "CONFIRMED_PATTERN_A"
        action = "SPLIT"
        reason = (
            "L'entité DONNEE_PATIENT contient un signal explicite de symptôme "
            "sans entité SYMPTOME fiable séparée."
        )

    # 4. Cas protégé
    else:
        status = "AMBIGUOUS"
        action = "NONE"
        reason = (
            "Preuve structurelle insuffisante. Le cas est protégé et "
            "aucune correction automatique n'est autorisée."
        )

    return {
        **candidate,
        "validation_status": status,
        "recommended_future_action": action,
        "validation_reason": reason,
        "reliable_target": best,
        "same_page_symptom_targets_recomputed": targets,
    }


# ============================================================
# 5. MAIN
# ============================================================

def main():
    input_dir = resolve_input_dir()
    detection_report = resolve_detection_report()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with detection_report.open("r", encoding="utf-8") as f:
        detection = json.load(f)

    candidates = detection.get("candidates", [])

    docs = {}
    skipped_nonclinical = []
    errors = []

    for path in sorted(input_dir.glob("*.json")):
        try:
            with path.open("r", encoding="utf-8") as f:
                doc = json.load(f)

            if not is_clinical_document(doc):
                skipped_nonclinical.append(path.name)
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
                    candidate.get("source_entity") or {}
                ).get("entity_id"),
                "error": "Document clinique correspondant introuvable.",
            })
            continue

        try:
            validated.append(
                validate_candidate(candidate, doc)
            )
        except Exception as exc:
            errors.append({
                "document": filename,
                "source_entity_id": (
                    candidate.get("source_entity") or {}
                ).get("entity_id"),
                "error": str(exc),
            })

    statuses = Counter(
        item["validation_status"]
        for item in validated
    )

    actions = Counter(
        item["recommended_future_action"]
        for item in validated
    )

    protected = (
        actions.get("SKIP", 0)
        + actions.get("NONE", 0)
    )

    report = {
        "pattern": "A6",
        "name": "DONNEE_PATIENT + SYMPTOME",
        "relation": RELATION_TYPE,
        "methodological_status": "VALIDATION_ONLY_NO_CORRECTION",
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
                protected,

            "errors":
                len(errors),
        },

        "validated_candidates": validated,
        "nonclinical_json_skipped": skipped_nonclinical,
        "errors": errors,
    }

    OUTPUT_JSON.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
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
            source = item.get("source_entity") or {}
            target = item.get("reliable_target") or {}

            writer.writerow({
                "document": item.get("document", ""),
                "source_entity_id": source.get("entity_id", ""),
                "page": source.get("page", ""),
                "source_text": source.get("text", ""),
                "strength": item.get("strength", ""),
                "families": "; ".join(
                    item.get("detected_symptom_families")
                    or []
                ),
                "validation_status":
                    item.get("validation_status", ""),
                "recommended_future_action":
                    item.get("recommended_future_action", ""),
                "reliable_target_id":
                    target.get("entity_id", ""),
                "reliable_target_text":
                    target.get("text", ""),
                "reliable_target_overlap":
                    target.get("token_overlap", ""),
                "reliable_target_containment":
                    target.get("containment", ""),
                "relation_exists":
                    target.get("relation_exists", ""),
                "validation_reason":
                    item.get("validation_reason", ""),
            })

    print("=" * 76)
    print("SGCE - PATTERN A6 VALIDATION")
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
    print(f"Cas protégés              : {protected}")
    print(f"Erreurs                   : {len(errors)}")
    print()
    print(f"Rapport JSON              : {OUTPUT_JSON}")
    print(f"CSV validation            : {OUTPUT_CSV}")
    print()
    print("Aucun JSON clinique n'a été modifié.")


if __name__ == "__main__":
    main()
