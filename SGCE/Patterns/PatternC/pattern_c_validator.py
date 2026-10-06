# -*- coding: utf-8 -*-
"""
pattern_c_validator.py
======================

SGCE — Pattern C Validator

Pattern C:
Relation réifiée en chaîne.

Input:
  PatternC/pattern_c_detection/pattern_c_detection_report.json

Goal:
Reduce noisy lexical candidates and keep only structurally plausible cases.

Validation logic:
1) Ignore WEAK candidates automatically.
2) Keep only MEDIUM/STRONG candidates.
3) Require a unique best relation hypothesis.
4) Require exactly one compatible domain endpoint and one compatible image endpoint
   for the top relation hypothesis.
5) If a valid direct TRACE-Sepsis relation already exists between those endpoints:
      -> ALREADY_RELATIONAL / SKIP
6) If no direct relation exists and the entity text is strongly relation-like:
      -> CONFIRMED_REIFIED_RELATION
7) If multiple endpoints/hypotheses remain:
      -> AMBIGUOUS
8) No clinical JSON is modified.

Future correction for CONFIRMED_REIFIED_RELATION:
- remove the reified entity
- create the validated relation between existing endpoints
Only after a separate actionability/correction step.
"""

import csv
import json
from collections import Counter
from pathlib import Path


PATTERN_C_DIR = Path(__file__).resolve().parent
PATTERNS_DIR = PATTERN_C_DIR.parent
SGCE_DIR = PATTERNS_DIR.parent
BASE_DIR = SGCE_DIR.parent

PATTERN_B2_DIR = PATTERNS_DIR / "PatternB" / "PatternB2"

INPUT_DIR = PATTERN_B2_DIR / "corrected"
DETECTION_REPORT = PATTERN_C_DIR / "detection" / "pattern_c_detection_report.json"

OUTPUT_DIR = PATTERN_C_DIR / "validation"
OUTPUT_JSON = OUTPUT_DIR / "pattern_c_validation_report.json"
OUTPUT_CSV = OUTPUT_DIR / "pattern_c_validation_candidates.csv"

# ============================================================
# HELPERS
# ============================================================

def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def is_clinical_document(doc):
    return isinstance(doc, dict) and (
        isinstance(doc.get("global_entities"), list)
        or isinstance(doc.get("pages"), list)
    )


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


def get_relations(doc):
    if isinstance(doc.get("global_relations"), list):
        return doc["global_relations"]

    out = []
    for p in doc.get("pages", []) or []:
        out.extend(p.get("relations", []) or [])
    return out


def resolve_input_dir():
    if not INPUT_DIR.exists():
        raise FileNotFoundError(
            f"Sortie finale Pattern B introuvable : {INPUT_DIR}"
        )

    if not any(INPUT_DIR.glob("*.json")):
        raise FileNotFoundError(
            f"Aucun JSON clinique trouvé dans : {INPUT_DIR}"
        )

    return INPUT_DIR


def direct_relation_exists(doc, relation_name, src_id, tgt_id):
    return any(
        relation_type(r) == relation_name
        and str(relation_source(r)) == str(src_id)
        and str(relation_target(r)) == str(tgt_id)
        for r in get_relations(doc)
    )


def entity_is_referenced(doc, eid):
    """Return relations that already use the candidate reified entity."""
    refs = []
    for r in get_relations(doc):
        if str(relation_source(r)) == str(eid) or str(relation_target(r)) == str(eid):
            refs.append({
                "relation_id": relation_id(r),
                "relation_type": relation_type(r),
                "source": relation_source(r),
                "target": relation_target(r),
            })
    return refs


# ============================================================
# VALIDATION
# ============================================================

def validate_candidate(candidate, doc):
    strength = candidate.get("strength", "")
    hypotheses = candidate.get("best_relation_hypotheses") or []

    base = {
        **candidate,
        "validation_status": None,
        "recommended_future_action": "NONE",
        "validated_relation": None,
        "validated_source_entity": None,
        "validated_target_entity": None,
        "validation_reason": "",
    }

    # --------------------------------------------------------
    # 1. WEAK = protected automatically
    # --------------------------------------------------------

    if strength == "WEAK":
        base["validation_status"] = "WEAK_PROTECTED"
        base["validation_reason"] = (
            "Signal lexical faible; aucune correction automatique autorisée."
        )
        return base

    # --------------------------------------------------------
    # 2. No hypothesis
    # --------------------------------------------------------

    if not hypotheses:
        base["validation_status"] = "AMBIGUOUS"
        base["validation_reason"] = "Aucune hypothèse relationnelle disponible."
        return base

    # --------------------------------------------------------
    # 3. Unique best hypothesis
    # --------------------------------------------------------

    top = hypotheses[0]
    top_score = float(top.get("similarity_score", 0.0))

    # If another hypothesis is too close, protect.
    if len(hypotheses) > 1:
        second_score = float(hypotheses[1].get("similarity_score", 0.0))
        if abs(top_score - second_score) < 0.10:
            base["validation_status"] = "AMBIGUOUS"
            base["validation_reason"] = (
                "Plusieurs relations candidates ont des scores trop proches."
            )
            return base

    relation_name = top.get("relation_name")
    domains = top.get("domain_candidates") or []
    images = top.get("image_candidates") or []

    # --------------------------------------------------------
    # 4. Need unique endpoints
    # --------------------------------------------------------

    if len(domains) != 1 or len(images) != 1:
        base["validation_status"] = "AMBIGUOUS"
        base["validation_reason"] = (
            "Les endpoints compatibles ne sont pas uniques "
            f"(domain={len(domains)}, image={len(images)})."
        )
        return base

    source = domains[0]
    target = images[0]

    src_id = source.get("id")
    tgt_id = target.get("id")

    if not src_id or not tgt_id:
        base["validation_status"] = "AMBIGUOUS"
        base["validation_reason"] = (
            "Endpoint source ou cible sans identifiant exploitable."
        )
        return base

    # --------------------------------------------------------
    # 5. Already represented relationally
    # --------------------------------------------------------

    if direct_relation_exists(
        doc,
        relation_name,
        src_id,
        tgt_id,
    ):
        base["validation_status"] = "ALREADY_RELATIONAL"
        base["recommended_future_action"] = "SKIP"
        base["validated_relation"] = relation_name
        base["validated_source_entity"] = source
        base["validated_target_entity"] = target
        base["validation_reason"] = (
            "La relation TRACE-Sepsis correspondante existe déjà entre "
            "les endpoints compatibles; l'entité candidate ne doit pas être "
            "transformée automatiquement."
        )
        return base

    # --------------------------------------------------------
    # 6. Structural isolation required for safe replacement
    # --------------------------------------------------------
    reified = candidate.get("reified_entity") or {}
    reified_id = reified.get("id")
    references = entity_is_referenced(doc, reified_id) if reified_id else []

    if references:
        base["validation_status"] = "AMBIGUOUS"
        base["recommended_future_action"] = "NONE"
        base["validated_relation"] = relation_name
        base["validated_source_entity"] = source
        base["validated_target_entity"] = target
        base["validation_reason"] = (
            "L'entité réifiée participe déjà à une ou plusieurs relations; "
            "son remplacement automatique pourrait supprimer de l'information."
        )
        base["existing_relation_references"] = references
        return base

    # --------------------------------------------------------
    # 7. Confirm only strong enough lexical/structural evidence
    # --------------------------------------------------------

    if strength == "STRONG" and top_score >= 0.75:
        base["validation_status"] = "CONFIRMED_REIFIED_RELATION"
        base["recommended_future_action"] = "REPLACE_ENTITY_WITH_RELATION"
        base["validated_relation"] = relation_name
        base["validated_source_entity"] = source
        base["validated_target_entity"] = target
        base["validation_reason"] = (
            "Entité fortement relationnelle, hypothèse unique et endpoints uniques, "
            "sans relation TRACE-Sepsis directe déjà présente."
        )
        return base

    # MEDIUM remains protected unless extremely clear.
    if strength == "MEDIUM" and top_score >= 0.70:
        base["validation_status"] = "POTENTIAL_REIFIED_RELATION"
        base["recommended_future_action"] = "NONE"
        base["validated_relation"] = relation_name
        base["validated_source_entity"] = source
        base["validated_target_entity"] = target
        base["validation_reason"] = (
            "Structure plausible mais confiance insuffisante pour correction automatique."
        )
        return base

    base["validation_status"] = "AMBIGUOUS"
    base["validation_reason"] = (
        "Preuve insuffisante pour transformer l'entité en relation."
    )
    return base


# ============================================================
# MAIN
# ============================================================

def main():
    input_dir = resolve_input_dir()

    if not DETECTION_REPORT.exists():
        raise FileNotFoundError(
            f"Rapport détection Pattern C introuvable : {DETECTION_REPORT}"
        )

    detection = load_json(DETECTION_REPORT)
    candidates = detection.get("candidates", [])

    docs = {}
    nonclinical = []
    errors = []

    for p in sorted(input_dir.glob("*.json")):
        try:
            doc = load_json(p)

            if is_clinical_document(doc):
                docs[p.name] = doc
            else:
                nonclinical.append(p.name)

        except Exception as exc:
            errors.append({
                "document": p.name,
                "error": str(exc),
            })

    validated = []

    for c in candidates:
        doc_name = c.get("document")
        doc = docs.get(doc_name)

        if doc is None:
            item = {
                **c,
                "validation_status": "AMBIGUOUS",
                "recommended_future_action": "NONE",
                "validation_reason": "Document clinique correspondant introuvable.",
            }
            validated.append(item)
            continue

        try:
            validated.append(
                validate_candidate(c, doc)
            )
        except Exception as exc:
            validated.append({
                **c,
                "validation_status": "AMBIGUOUS",
                "recommended_future_action": "NONE",
                "validation_reason": f"Erreur validation : {exc}",
            })

    status_counts = Counter(
        c.get("validation_status", "")
        for c in validated
    )

    action_counts = Counter(
        c.get("recommended_future_action", "")
        for c in validated
    )

    protected = sum(
        1 for c in validated
        if c.get("recommended_future_action") in {"NONE", "SKIP"}
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    report = {
        "pattern": "C",
        "stage": "VALIDATION",
        "input_directory": str(input_dir),
        "detection_report": str(DETECTION_REPORT),
        "summary": {
            "clinical_documents": len(docs),
            "candidates_detected": len(candidates),
            "candidates_validated": len(validated),

            "weak_protected":
                status_counts.get("WEAK_PROTECTED", 0),

            "already_relational":
                status_counts.get("ALREADY_RELATIONAL", 0),

            "confirmed_reified_relation":
                status_counts.get("CONFIRMED_REIFIED_RELATION", 0),

            "potential_reified_relation":
                status_counts.get("POTENTIAL_REIFIED_RELATION", 0),

            "ambiguous":
                status_counts.get("AMBIGUOUS", 0),

            "future_replace_entity_with_relation":
                action_counts.get("REPLACE_ENTITY_WITH_RELATION", 0),

            "protected":
                protected,

            "errors":
                len(errors),
        },
        "validated_candidates": validated,
        "nonclinical_json_skipped": nonclinical,
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
        "candidate_id",
        "document",
        "strength",
        "entity_id",
        "entity_type",
        "entity_text",
        "validation_status",
        "recommended_future_action",
        "validated_relation",
        "source_id",
        "source_type",
        "source_text",
        "target_id",
        "target_type",
        "target_text",
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
            reified = c.get("reified_entity") or {}
            src = c.get("validated_source_entity") or {}
            tgt = c.get("validated_target_entity") or {}

            writer.writerow({
                "candidate_id":
                    c.get("candidate_id", ""),

                "document":
                    c.get("document", ""),

                "strength":
                    c.get("strength", ""),

                "entity_id":
                    reified.get("id", ""),

                "entity_type":
                    reified.get("type", ""),

                "entity_text":
                    reified.get("text", ""),

                "validation_status":
                    c.get("validation_status", ""),

                "recommended_future_action":
                    c.get("recommended_future_action", ""),

                "validated_relation":
                    c.get("validated_relation", "") or "",

                "source_id":
                    src.get("id", ""),

                "source_type":
                    src.get("type", ""),

                "source_text":
                    src.get("text", ""),

                "target_id":
                    tgt.get("id", ""),

                "target_type":
                    tgt.get("type", ""),

                "target_text":
                    tgt.get("text", ""),

                "validation_reason":
                    c.get("validation_reason", ""),
            })

    print("=" * 82)
    print("SGCE - PATTERN C VALIDATION")
    print("=" * 82)

    print(f"Entrée clinique                  : {input_dir}")
    print(f"Rapport détection                : {DETECTION_REPORT}")
    print()
    print(f"Documents cliniques              : {len(docs)}")
    print(f"Candidats détectés               : {len(candidates)}")
    print(f"Candidats validés                : {len(validated)}")
    print()
    print(
        f"WEAK_PROTECTED                   : "
        f"{status_counts.get('WEAK_PROTECTED', 0)}"
    )
    print(
        f"ALREADY_RELATIONAL               : "
        f"{status_counts.get('ALREADY_RELATIONAL', 0)}"
    )
    print(
        f"CONFIRMED_REIFIED_RELATION       : "
        f"{status_counts.get('CONFIRMED_REIFIED_RELATION', 0)}"
    )
    print(
        f"POTENTIAL_REIFIED_RELATION       : "
        f"{status_counts.get('POTENTIAL_REIFIED_RELATION', 0)}"
    )
    print(
        f"AMBIGUOUS                        : "
        f"{status_counts.get('AMBIGUOUS', 0)}"
    )
    print()
    print(
        f"Futurs REPLACE_ENTITY_WITH_RELATION : "
        f"{action_counts.get('REPLACE_ENTITY_WITH_RELATION', 0)}"
    )
    print(f"Cas protégés                     : {protected}")
    print(f"Erreurs                          : {len(errors)}")
    print()
    print(f"Rapport JSON                     : {OUTPUT_JSON}")
    print(f"CSV validation                   : {OUTPUT_CSV}")
    print()
    print("Aucun JSON clinique n'a été modifié.")


if __name__ == "__main__":
    main()
