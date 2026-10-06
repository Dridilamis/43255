# -*- coding: utf-8 -*-
"""
pattern_a1_validator.py
=======================

Validation des candidats produits par pattern_a1_detector_v2.py.

Entrées :
- SortieJson_Postprocessing/*.json
- pattern_a1_detection/pattern_a1_detection_report.json

Sortie :
- pattern_a1_validation/pattern_a1_validation_report.json

Classes :
- ALREADY_CORRECT
- MISSING_RELATION
- CONFIRMED_PATTERN_A
- AMBIGUOUS

IMPORTANT :
- aucune correction ;
- aucun JSON Mistral modifié ;
- un candidat WEAK sans cible fiable reste AMBIGUOUS ;
- un SPLIT potentiel n'est confirmé que pour un signal MEDIUM/STRONG
  sans POSOLOGIE fiable correspondante.
"""

import json
import re
import unicodedata
from pathlib import Path
from collections import Counter, defaultdict

PATTERN_A1_DIR = Path(__file__).resolve().parent
PATTERN_A_DIR = PATTERN_A1_DIR.parent
PATTERNS_DIR = PATTERN_A_DIR.parent
SGCE_DIR = PATTERNS_DIR.parent
BASE_DIR = SGCE_DIR.parent

INPUT_DIR = BASE_DIR / "SortieJson_Postprocessing"
DETECTION_REPORT = PATTERN_A1_DIR / "detection" / "pattern_a1_detection_v2_report.json"

OUTPUT_DIR = PATTERN_A1_DIR / "validation"
GLOBAL_REPORT = OUTPUT_DIR / "pattern_a1_validation_v2_report.json"

RELATION_TYPE = "traitement_a_pour_posologie"

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def normalize(text):
    text = "" if text is None else str(text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace("’", "'")
    return re.sub(r"\s+", " ", text).strip()

def entity_type(e):
    return e.get("categorie") or e.get("type") or ""

def entity_id(e):
    return e.get("identifiant_entite") or e.get("id")

def entity_page(e):
    return e.get("page")

def relation_type(r):
    return r.get("type_relation") or r.get("relation") or r.get("type")

def relation_source(r):
    return r.get("identifiant_entite_sujet") or r.get("from_id")

def relation_target(r):
    return r.get("identifiant_entite_objet") or r.get("to_id")

def get_entities(doc):
    if isinstance(doc.get("global_entities"), list):
        return doc["global_entities"]

    result = []
    for p in doc.get("pages", []) or []:
        result.extend(p.get("entities", []) or [])
    return result

def get_relations(doc):
    if isinstance(doc.get("global_relations"), list):
        return doc["global_relations"]

    result = []
    for p in doc.get("pages", []) or []:
        result.extend(p.get("relations", []) or [])
    return result

def entity_text(e):
    values = []
    for key in ("preuve", "name", "valeur", "parametre"):
        value = e.get(key)
        if value not in (None, ""):
            value = str(value).strip()
            if value and value not in values:
                values.append(value)
    return " | ".join(values)

# ------------------------------------------------------------
# Matching conservateur
# ------------------------------------------------------------

STOPWORDS = {
    "traitement", "par", "avec", "sous", "de", "du", "des",
    "le", "la", "les", "un", "une", "et", "en", "pour",
    "iv", "sc", "im", "po", "per", "os", "orale",
    "intraveineux", "intraveineuse", "souscutanee",
}

def tokens(text):
    return {
        token
        for token in re.findall(r"[a-z0-9]+", normalize(text))
        if len(token) >= 3
        and token not in STOPWORDS
        and not token.isdigit()
    }

def medication_anchor(treatment, posology):
    """
    Le matching ne doit jamais être basé uniquement sur
    une dose/fréquence/voie partagée.

    On exige un ancrage lexical du médicament dans la POSOLOGIE/preuve.
    """
    med_text = treatment.get("name") or treatment.get("valeur") or ""
    med_tokens = tokens(med_text)
    pos_tokens = tokens(entity_text(posology))

    if not med_tokens or not pos_tokens:
        return 0.0

    return len(med_tokens & pos_tokens) / len(med_tokens)

def component_overlap(candidate, posology):
    values = []
    for component_values in candidate.get("detected_components", {}).values():
        if isinstance(component_values, list):
            values.extend(component_values)
        elif component_values:
            values.append(component_values)

    if not values:
        return 0.0

    pos_text = normalize(entity_text(posology))
    hits = sum(
        1 for value in values
        if normalize(value) and normalize(value) in pos_text
    )

    return hits / len(values)

def proof_overlap(treatment, posology):
    a = tokens(entity_text(treatment))
    b = tokens(entity_text(posology))

    if not a or not b:
        return 0.0

    return len(a & b) / min(len(a), len(b))

def same_page(treatment, posology):
    p1 = entity_page(treatment)
    p2 = entity_page(posology)
    return 1.0 if p1 is not None and p1 == p2 else 0.0

def score_match(treatment, posology, candidate):
    anchor = medication_anchor(treatment, posology)
    components = component_overlap(candidate, posology)
    page_score = same_page(treatment, posology)
    overlap = proof_overlap(treatment, posology)

    final_score = (
        0.50 * anchor
        + 0.25 * components
        + 0.15 * page_score
        + 0.10 * overlap
    )

    reliable = (
        anchor >= 0.60
        and final_score >= 0.65
    )

    return {
        "target_id": entity_id(posology),
        "target_name": posology.get("name"),
        "target_preuve": posology.get("preuve"),
        "target_page": entity_page(posology),
        "medication_anchor": round(anchor, 4),
        "component_overlap": round(components, 4),
        "same_page": round(page_score, 4),
        "proof_overlap": round(overlap, 4),
        "final_score": round(final_score, 4),
        "reliable": reliable,
    }

# ------------------------------------------------------------
# Validation
# ------------------------------------------------------------

def validate_candidate(candidate, document):
    entities = get_entities(document)
    relations = get_relations(document)

    entity_map = {
        entity_id(e): e
        for e in entities
        if entity_id(e)
    }

    source_info = candidate.get("source_entity", {})
    source_id = source_info.get("id")
    treatment = entity_map.get(source_id)

    result = dict(candidate)

    if treatment is None:
        result["validation_status"] = "AMBIGUOUS"
        result["validation_reason"] = "SOURCE_ENTITY_NOT_FOUND"
        result["best_posology_match"] = None
        return result

    posologies = [
        e for e in entities
        if entity_type(e) == "POSOLOGIE"
    ]

    existing_targets = [
        relation_target(r)
        for r in relations
        if relation_type(r) == RELATION_TYPE
        and relation_source(r) == source_id
    ]

    ranked = [
        score_match(treatment, p, candidate)
        for p in posologies
    ]

    ranked.sort(
        key=lambda x: x["final_score"],
        reverse=True
    )

    reliable_matches = [
        match for match in ranked
        if match["reliable"]
    ]

    best = reliable_matches[0] if reliable_matches else None

    result["existing_relation_targets"] = existing_targets
    result["best_posology_match"] = best
    result["top_3_matches"] = ranked[:3]

    # 1. Structure déjà correcte
    if best and best["target_id"] in existing_targets:
        result["validation_status"] = "ALREADY_CORRECT"
        result["validation_reason"] = (
            "POSOLOGIE fiable trouvée et relation déjà présente."
        )
        result["recommended_action"] = "NONE"
        return result

    # 2. POSOLOGIE fiable présente, relation absente
    if best:
        result["validation_status"] = "MISSING_RELATION"
        result["validation_reason"] = (
            "POSOLOGIE fiable trouvée mais relation "
            "traitement_a_pour_posologie absente."
        )
        result["recommended_action"] = "LINK"
        return result

    # 3. Aucun match fiable.
    # WEAK ne peut jamais déclencher automatiquement SPLIT.
    strength = candidate.get("signal_strength")

    if strength == "WEAK":
        result["validation_status"] = "AMBIGUOUS"
        result["validation_reason"] = (
            "Un seul type de composant posologique détecté "
            "et aucune POSOLOGIE fiable correspondante."
        )
        result["recommended_action"] = "NONE"
        return result

    # MEDIUM/STRONG : plusieurs familles posologiques explicites.
    # On marque CONFIRMED_PATTERN_A pour la règle déterministe,
    # mais le correcteur sera encore séparé.
    if strength in {"MEDIUM", "STRONG"}:
        result["validation_status"] = "CONFIRMED_PATTERN_A"
        result["validation_reason"] = (
            "Plusieurs types de composants posologiques sont explicitement "
            "fusionnés dans TRAITEMENT et aucune POSOLOGIE fiable "
            "correspondante n'a été trouvée."
        )
        result["recommended_action"] = "SPLIT"
        return result

    result["validation_status"] = "AMBIGUOUS"
    result["validation_reason"] = "SIGNAL_STRENGTH_UNKNOWN"
    result["recommended_action"] = "NONE"
    return result

# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not DETECTION_REPORT.exists():
        raise FileNotFoundError(
            "Rapport de détection introuvable. "
            "Lance d'abord pattern_a1_detector_v2.py : "
            + str(DETECTION_REPORT)
        )

    with DETECTION_REPORT.open("r", encoding="utf-8") as f:
        detection = json.load(f)

    candidates = detection.get("candidates", [])

    by_document = defaultdict(list)

    for candidate in candidates:
        document_name = candidate.get("document")
        if document_name:
            by_document[document_name].append(candidate)

    all_results = []
    document_reports = []
    errors = []

    print("=" * 78)
    print("SGCE - PATTERN A1 VALIDATOR V2")
    print("=" * 78)
    print(f"Candidats reçus : {len(candidates)}")
    print(f"Documents concernés : {len(by_document)}")
    print()

    for document_name, document_candidates in sorted(by_document.items()):
        json_path = INPUT_DIR / document_name

        try:
            with json_path.open("r", encoding="utf-8") as f:
                document = json.load(f)

            results = [
                validate_candidate(candidate, document)
                for candidate in document_candidates
            ]

            all_results.extend(results)

            counts = Counter(
                r["validation_status"]
                for r in results
            )

            document_reports.append({
                "document": document_name,
                "candidates": len(results),
                "status_counts": dict(counts),
            })

            individual_path = (
                OUTPUT_DIR
                / f"{Path(document_name).stem}_A1_validation.json"
            )

            with individual_path.open("w", encoding="utf-8") as f:
                json.dump(
                    {
                        "document": document_name,
                        "pattern": "A1_TRAITEMENT_POSOLOGIE",
                        "candidates": len(results),
                        "status_counts": dict(counts),
                        "results": results,
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

            print(
                f"[OK] {document_name}"
                f" | candidats={len(results)}"
                f" | CORRECT={counts.get('ALREADY_CORRECT', 0)}"
                f" | LINK={counts.get('MISSING_RELATION', 0)}"
                f" | SPLIT={counts.get('CONFIRMED_PATTERN_A', 0)}"
                f" | AMBIGUOUS={counts.get('AMBIGUOUS', 0)}"
            )

        except Exception as exc:
            errors.append({
                "document": document_name,
                "error": str(exc),
            })

            print(
                f"[ERREUR] {document_name}: {exc}"
            )

    global_counts = Counter(
        r["validation_status"]
        for r in all_results
    )

    # Ventilation par force initiale
    by_strength = {}

    for strength in ("WEAK", "MEDIUM", "STRONG"):
        subset = [
            r for r in all_results
            if r.get("signal_strength") == strength
        ]

        by_strength[strength] = dict(
            Counter(
                r["validation_status"]
                for r in subset
            )
        )

    report = {
        "pattern": "A1_TRAITEMENT_POSOLOGIE",
        "detection_candidates": len(candidates),
        "validated_candidates": len(all_results),
        "status_counts": dict(global_counts),
        "status_by_signal_strength": by_strength,
        "matching_thresholds": {
            "minimum_medication_anchor": 0.60,
            "minimum_final_score": 0.65,
            "weights": {
                "medication_anchor": 0.50,
                "component_overlap": 0.25,
                "same_page": 0.15,
                "proof_overlap": 0.10,
            },
        },
        "important_note": (
            "ALREADY_CORRECT = aucune correction. "
            "MISSING_RELATION = candidat LINK. "
            "CONFIRMED_PATTERN_A = candidat SPLIT selon la règle "
            "déterministe A1. "
            "AMBIGUOUS = aucune correction automatique."
        ),
        "documents": document_reports,
        "results": all_results,
        "errors": errors,
    }

    with GLOBAL_REPORT.open("w", encoding="utf-8") as f:
        json.dump(
            report,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print()
    print("=" * 78)
    print("RÉSUMÉ GLOBAL A1 - VALIDATION")
    print("=" * 78)

    print(f"Candidats détectés      : {len(candidates)}")
    print(f"Candidats validés       : {len(all_results)}")
    print(
        f"ALREADY_CORRECT         : "
        f"{global_counts.get('ALREADY_CORRECT', 0)}"
    )
    print(
        f"MISSING_RELATION        : "
        f"{global_counts.get('MISSING_RELATION', 0)}"
    )
    print(
        f"CONFIRMED_PATTERN_A     : "
        f"{global_counts.get('CONFIRMED_PATTERN_A', 0)}"
    )
    print(
        f"AMBIGUOUS               : "
        f"{global_counts.get('AMBIGUOUS', 0)}"
    )
    print(f"Erreurs                 : {len(errors)}")

    print()
    print("PAR FORCE DU SIGNAL")
    print("-" * 78)

    for strength in ("WEAK", "MEDIUM", "STRONG"):
        print(
            f"{strength:8s}: "
            f"{by_strength.get(strength, {})}"
        )

    print()
    print(f"Rapport : {GLOBAL_REPORT}")
    print()
    print("Aucun JSON Mistral n'a été modifié.")
    print("Ne lance pas encore de correcteur.")

if __name__ == "__main__":
    main()
