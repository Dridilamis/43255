# -*- coding: utf-8 -*-
"""
pattern_a2_validator.py
=======================

SGCE — Pattern A2 Validator
COMORBIDITE_ANTECEDENT + CONTEXTE_ACQUISITION

TRACE-Sepsis v1.6
-----------------
Relation autorisée :
    COMORBIDITE_ANTECEDENT
        --a_pour_contexte_acquisition-->
    CONTEXTE_ACQUISITION

Entrées
-------
- JSON cliniques après A1
- rapport de détection A2

Sorties
-------
- pattern_a2_validation_report.json
- pattern_a2_validation_candidates.csv

Décisions automatiques
-----------------------
ALREADY_CORRECT
    Une cible CONTEXTE_ACQUISITION fiable est trouvée ET la relation
    a_pour_contexte_acquisition existe déjà.

MISSING_RELATION
    Une cible CONTEXTE_ACQUISITION fiable est trouvée MAIS la relation
    a_pour_contexte_acquisition est absente.

CONFIRMED_PATTERN_A
    Le candidat est STRONG, contient un contexte explicite, et aucune cible
    CONTEXTE_ACQUISITION fiable déjà séparée ne correspond.

AMBIGUOUS
    Les preuves sont insuffisantes pour une décision structurelle automatique.

IMPORTANT
---------
- Aucune correction.
- Aucun JSON clinique modifié.
- CONFIRMED_PATTERN_A signifie "confirmé selon les règles structurelles
  déterministes SGCE", pas "hallucination clinique confirmée".
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

PATTERN_A2_DIR = Path(__file__).resolve().parent
PATTERN_A_DIR = PATTERN_A2_DIR.parent
PATTERNS_DIR = PATTERN_A_DIR.parent
SGCE_DIR = PATTERNS_DIR.parent
BASE_DIR = SGCE_DIR.parent
PATTERN_A1_DIR = PATTERN_A_DIR / "PatternA1"

INPUT_DIR_CANDIDATES = [PATTERN_A1_DIR / "corrected"]
DETECTION_REPORT_CANDIDATES = [
    PATTERN_A2_DIR / "detection" / "pattern_a2_detection_report.json"
]
OUTPUT_DIR = PATTERN_A2_DIR / "validation"
OUTPUT_JSON = OUTPUT_DIR / "pattern_a2_validation_report.json"
OUTPUT_CSV = OUTPUT_DIR / "pattern_a2_validation_candidates.csv"

SOURCE_TYPE = "COMORBIDITE_ANTECEDENT"
TARGET_TYPE = "CONTEXTE_ACQUISITION"
RELATION_TYPE = "a_pour_contexte_acquisition"

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


def resolve_existing(candidates, kind):
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(
        f"{kind} introuvable.\n"
        + "\n".join(f"- {p}" for p in candidates)
    )


def resolve_input_dir():
    for p in INPUT_DIR_CANDIDATES:
        if p.exists() and any(p.glob("*.json")):
            return p
    raise FileNotFoundError("Aucun dossier JSON clinique trouvé.")


def entity_id(e):
    return (
        e.get("identifiant_entite")
        or e.get("id")
        or e.get("entity_id")
    )


def entity_type(e):
    return e.get("categorie") or e.get("type") or ""


def entity_page(e):
    if e.get("page") is not None:
        return e.get("page")
    return e.get("page_number")


def entity_text(e):
    values = []
    for key in (
        "preuve", "name", "valeur", "libelle",
        "parametre", "texte", "text"
    ):
        value = e.get(key)
        if value not in (None, ""):
            value = str(value).strip()
            if value and value not in values:
                values.append(value)
    return " | ".join(values)


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

    result = []
    for page in doc.get("pages", []) or []:
        result.extend(page.get("entities", []) or [])
    return result


def get_relations(doc):
    if isinstance(doc.get("global_relations"), list):
        return doc["global_relations"]

    result = []
    for page in doc.get("pages", []) or []:
        result.extend(page.get("relations", []) or [])
    return result


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
    a_tokens = token_set(a)
    b_tokens = token_set(b)

    if not a_tokens or not b_tokens:
        return 0.0

    return len(a_tokens & b_tokens) / min(
        len(a_tokens), len(b_tokens)
    )


def relation_exists(source_id, target_id, relations):
    return any(
        relation_type(r) == RELATION_TYPE
        and relation_source(r) == source_id
        and relation_target(r) == target_id
        for r in relations
    )


# ============================================================
# 3. MATCHING CIBLE CONTEXTE
# ============================================================

def score_context_target(source_text, target_text):
    """
    Score structurel conservateur.

    Composantes :
    - containment textuel : 0.55
    - overlap lexical      : 0.45

    Une cible est fiable si :
    - containment explicite, OU
    - overlap >= 0.60.

    Le score n'est pas une confiance clinique.
    """
    src = normalize(source_text)
    tgt = normalize(target_text)

    containment = bool(
        src and tgt and (tgt in src or src in tgt)
    )

    overlap = token_overlap(source_text, target_text)

    score = (
        (0.55 if containment else 0.0)
        + 0.45 * overlap
    )

    reliable = (
        containment
        or overlap >= RELIABLE_OVERLAP_THRESHOLD
    )

    return {
        "containment": containment,
        "token_overlap": round(overlap, 4),
        "score": round(score, 4),
        "reliable": reliable,
    }


def find_context_targets(source, entities, relations):
    """
    Recherche uniquement les CONTEXTE_ACQUISITION de la même page.
    """
    src_page = entity_page(source)
    src_text = entity_text(source)
    src_id = entity_id(source)

    matches = []

    for target in entities:
        if entity_type(target) != TARGET_TYPE:
            continue

        if entity_page(target) != src_page:
            continue

        target_text = entity_text(target)
        metrics = score_context_target(
            src_text,
            target_text,
        )

        matches.append({
            "entity_id": entity_id(target),
            "page": entity_page(target),
            "text": target_text,
            **metrics,
            "relation_exists": relation_exists(
                src_id,
                entity_id(target),
                relations,
            ),
        })

    matches.sort(
        key=lambda x: (
            x["reliable"],
            x["containment"],
            x["token_overlap"],
            x["score"],
        ),
        reverse=True,
    )

    return matches


# ============================================================
# 4. VALIDATION D'UN CANDIDAT
# ============================================================

def validate_candidate(candidate, doc):
    entities = get_entities(doc)
    relations = get_relations(doc)

    source_info = candidate.get("source_entity", {})
    source_id = source_info.get("entity_id")
    page = source_info.get("page")

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
            "validation_reason": (
                "Source COMORBIDITE_ANTECEDENT introuvable "
                "dans le JSON clinique."
            ),
            "reliable_target": None,
            "all_same_page_targets": [],
        }

    targets = find_context_targets(
        source,
        entities,
        relations,
    )

    reliable_targets = [
        t for t in targets if t["reliable"]
    ]

    best = (
        reliable_targets[0]
        if reliable_targets
        else None
    )

    strength = candidate.get("strength", "")
    signal_families = (
        candidate.get("detected_context_families")
        or []
    )
    authorized_hits = (
        candidate.get("authorized_type_acquisition_hits")
        or []
    )

    explicit_context = bool(
        signal_families or authorized_hits
    )

    # --------------------------------------------------------
    # CAS 1 : cible fiable déjà séparée + relation existante
    # --------------------------------------------------------
    if best and best["relation_exists"]:
        status = "ALREADY_CORRECT"
        action = "SKIP"
        reason = (
            "Un CONTEXTE_ACQUISITION fiable est déjà séparé "
            "sur la même page et la relation "
            "a_pour_contexte_acquisition existe déjà."
        )

    # --------------------------------------------------------
    # CAS 2 : cible fiable déjà séparée, relation absente
    # --------------------------------------------------------
    elif best and not best["relation_exists"]:
        status = "MISSING_RELATION"
        action = "LINK"
        reason = (
            "Un CONTEXTE_ACQUISITION fiable est déjà séparé "
            "sur la même page, mais la relation "
            "a_pour_contexte_acquisition est absente."
        )

    # --------------------------------------------------------
    # CAS 3 : composite structurel
    # --------------------------------------------------------
    elif (
        strength == "STRONG"
        and explicit_context
        and not reliable_targets
    ):
        status = "CONFIRMED_PATTERN_A"
        action = "SPLIT"
        reason = (
            "Le candidat STRONG contient un contexte "
            "d'acquisition explicite, sans "
            "CONTEXTE_ACQUISITION fiable déjà séparé."
        )

    # --------------------------------------------------------
    # CAS 4 : protection
    # --------------------------------------------------------
    else:
        status = "AMBIGUOUS"
        action = "NONE"
        reason = (
            "Les preuves structurelles sont insuffisantes "
            "pour une correction automatique sûre."
        )

    return {
        **candidate,
        "validation_status": status,
        "recommended_future_action": action,
        "validation_reason": reason,
        "reliable_target": best,
        "same_page_context_targets_recomputed": targets,
    }


# ============================================================
# 5. MAIN
# ============================================================

def main():
    input_dir = resolve_input_dir()

    detection_report = resolve_existing(
        DETECTION_REPORT_CANDIDATES,
        "Rapport de détection A2",
    )

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

    # Charger uniquement les vrais JSON cliniques.
    docs = {}
    nonclinical_skipped = []
    load_errors = []

    for path in sorted(input_dir.glob("*.json")):
        try:
            with path.open(
                "r",
                encoding="utf-8",
            ) as f:
                doc = json.load(f)

            if not is_clinical_document(doc):
                nonclinical_skipped.append(
                    path.name
                )
                continue

            docs[path.name] = doc

        except Exception as exc:
            load_errors.append({
                "document": path.name,
                "error": str(exc),
            })

    validated = []
    errors = list(load_errors)

    for candidate in candidates:
        filename = candidate.get("document")

        doc = docs.get(filename)

        if doc is None:
            errors.append({
                "document": filename,
                "source_entity_id": (
                    candidate
                    .get("source_entity", {})
                    .get("entity_id")
                ),
                "error": (
                    "Document clinique correspondant "
                    "introuvable."
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
                    candidate
                    .get("source_entity", {})
                    .get("entity_id")
                ),
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

    strength_status = {}

    for strength in (
        "WEAK",
        "MEDIUM",
        "STRONG",
    ):
        subset = [
            v for v in validated
            if v.get("strength") == strength
        ]

        strength_status[strength] = dict(
            Counter(
                v["validation_status"]
                for v in subset
            )
        )

    report = {
        "pattern": "A2",
        "name": (
            "COMORBIDITE_ANTECEDENT + "
            "CONTEXTE_ACQUISITION"
        ),
        "trace_sepsis_relation": RELATION_TYPE,
        "methodological_status": (
            "VALIDATION_ONLY_NO_CORRECTION"
        ),
        "input_directory": str(input_dir),
        "detection_report": str(
            detection_report
        ),
        "summary": {
            "clinical_documents_loaded": len(docs),
            "candidates_detected": len(candidates),
            "candidates_validated": len(validated),

            "already_correct": statuses.get(
                "ALREADY_CORRECT", 0
            ),
            "missing_relation": statuses.get(
                "MISSING_RELATION", 0
            ),
            "confirmed_pattern_a": statuses.get(
                "CONFIRMED_PATTERN_A", 0
            ),
            "ambiguous": statuses.get(
                "AMBIGUOUS", 0
            ),

            "future_link": actions.get(
                "LINK", 0
            ),
            "future_split": actions.get(
                "SPLIT", 0
            ),
            "protected_no_action": (
                actions.get("SKIP", 0)
                + actions.get("NONE", 0)
            ),

            "errors": len(errors),
        },
        "by_strength": strength_status,
        "nonclinical_json_skipped": (
            nonclinical_skipped
        ),
        "validated_candidates": validated,
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
        "authorized_type_acquisition_hits",
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
                "source_entity",
                {},
            )
            target = (
                item.get("reliable_target")
                or {}
            )

            writer.writerow({
                "document": item.get(
                    "document", ""
                ),
                "source_entity_id": source.get(
                    "entity_id", ""
                ),
                "page": source.get(
                    "page", ""
                ),
                "source_text": source.get(
                    "text", ""
                ),
                "strength": item.get(
                    "strength", ""
                ),
                "families": "; ".join(
                    item.get(
                        "detected_context_families",
                        [],
                    )
                ),
                "authorized_type_acquisition_hits":
                    "; ".join(
                        item.get(
                            "authorized_type_acquisition_hits",
                            [],
                        )
                    ),
                "validation_status": item.get(
                    "validation_status", ""
                ),
                "recommended_future_action":
                    item.get(
                        "recommended_future_action",
                        "",
                    ),
                "reliable_target_id": target.get(
                    "entity_id", ""
                ),
                "reliable_target_text": target.get(
                    "text", ""
                ),
                "reliable_target_overlap": target.get(
                    "token_overlap", ""
                ),
                "reliable_target_containment":
                    target.get(
                        "containment", ""
                    ),
                "relation_exists": target.get(
                    "relation_exists", ""
                ),
                "validation_reason": item.get(
                    "validation_reason", ""
                ),
            })

    print("=" * 76)
    print("SGCE - PATTERN A2 VALIDATION")
    print("=" * 76)
    print(
        f"Entrée clinique           : "
        f"{input_dir}"
    )
    print(
        f"Rapport détection         : "
        f"{detection_report}"
    )
    print(
        f"Documents cliniques       : "
        f"{len(docs)}"
    )
    print()
    print(
        f"Candidats détectés        : "
        f"{len(candidates)}"
    )
    print(
        f"Candidats validés         : "
        f"{len(validated)}"
    )
    print()
    print(
        f"ALREADY_CORRECT           : "
        f"{statuses.get('ALREADY_CORRECT', 0)}"
    )
    print(
        f"MISSING_RELATION          : "
        f"{statuses.get('MISSING_RELATION', 0)}"
    )
    print(
        f"CONFIRMED_PATTERN_A       : "
        f"{statuses.get('CONFIRMED_PATTERN_A', 0)}"
    )
    print(
        f"AMBIGUOUS                 : "
        f"{statuses.get('AMBIGUOUS', 0)}"
    )
    print()
    print(
        f"Futurs LINK               : "
        f"{actions.get('LINK', 0)}"
    )
    print(
        f"Futurs SPLIT              : "
        f"{actions.get('SPLIT', 0)}"
    )
    print(
        f"Cas protégés              : "
        f"{actions.get('SKIP', 0) + actions.get('NONE', 0)}"
    )
    print(
        f"Erreurs                   : "
        f"{len(errors)}"
    )
    print()
    print("Par force :")

    for strength in (
        "WEAK",
        "MEDIUM",
        "STRONG",
    ):
        vals = strength_status.get(
            strength,
            {},
        )
        total = sum(vals.values())

        if total:
            print(
                f"  {strength:<8} : "
                + ", ".join(
                    f"{k}={v}"
                    for k, v in vals.items()
                )
            )

    print()
    print(
        f"Rapport JSON              : "
        f"{OUTPUT_JSON}"
    )
    print(
        f"CSV validation            : "
        f"{OUTPUT_CSV}"
    )
    print()
    print(
        "Aucun JSON clinique n'a été modifié."
    )


if __name__ == "__main__":
    main()
