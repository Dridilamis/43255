# -*- coding: utf-8 -*-
"""
pattern_a1_auto_corrector.py

Correction automatique CONSERVATRICE du Pattern A1:
TRAITEMENT + POSOLOGIE.

Entrée:
- SortieJson_Postprocessing/*.json
- rapport de validation A1 V2

Décisions:
- ALREADY_CORRECT -> SKIP
- AMBIGUOUS -> SKIP
- MISSING_RELATION -> LINK automatique si match fiable
- CONFIRMED_PATTERN_A -> SPLIT automatique seulement si:
    * signal MEDIUM/STRONG
    * >= 2 familles posologiques indépendantes
    * composants explicitement présents dans la preuve/texte source
    * aucune POSOLOGIE fiable correspondante

Sortie:
- pattern_a1_auto_corrected/*.json
- pattern_a1_auto_corrected/pattern_a1_auto_correction_report.json

Les originaux ne sont jamais modifiés.
"""

import copy
import json
import re
import unicodedata
from pathlib import Path
from collections import Counter

PATTERN_A1_DIR = Path(__file__).resolve().parent
PATTERN_A_DIR = PATTERN_A1_DIR.parent
PATTERNS_DIR = PATTERN_A_DIR.parent
SGCE_DIR = PATTERNS_DIR.parent
BASE_DIR = SGCE_DIR.parent

INPUT_DIR = BASE_DIR / "SortieJson_Postprocessing"

VALIDATION_REPORTS = [
    PATTERN_A1_DIR / "validation" / "pattern_a1_validation_v2_report.json",
]

OUTPUT_DIR = PATTERN_A1_DIR / "corrected"
OUTPUT_REPORT = OUTPUT_DIR / "pattern_a1_auto_correction_report.json"

RELATION_TYPE = "traitement_a_pour_posologie"
MIN_ANCHOR = 0.60
MIN_MATCH_SCORE = 0.65


def norm(x):
    x = "" if x is None else str(x)
    x = unicodedata.normalize("NFKD", x)
    x = "".join(c for c in x if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", x.lower()).strip()


def eid(e):
    return e.get("identifiant_entite") or e.get("id")


def etype(e):
    return e.get("categorie") or e.get("type") or ""


def rid(r):
    return r.get("identifiant_relation") or r.get("id")


def rtype(r):
    return r.get("type_relation") or r.get("relation") or r.get("type")


def rsource(r):
    return r.get("identifiant_entite_sujet") or r.get("from_id")


def rtarget(r):
    return r.get("identifiant_entite_objet") or r.get("to_id")


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


def page_number(e):
    return e.get("page")


def source_text(result):
    src = result.get("source_entity") or {}
    return " | ".join(
        str(v).strip()
        for v in (
            src.get("preuve"),
            src.get("name"),
            src.get("valeur"),
            result.get("detection_text"),
        )
        if v not in (None, "")
    )


def explicit_independent_components(result):
    """
    V2 a déjà supprimé les sous-matches imbriqués.
    On exige ici >=2 familles distinctes ET que chaque valeur soit
    explicitement retrouvée dans le texte source.
    """
    components = result.get("detected_components") or {}
    text = norm(source_text(result))
    valid = {}

    for family, values in components.items():
        if not isinstance(values, list):
            values = [values]

        explicit = []
        for value in values:
            nv = norm(value)
            if nv and nv in text:
                explicit.append(str(value).strip())

        if explicit:
            valid[family] = explicit

    return valid


def next_entity_id(doc, page):
    prefix = f"P{page}_E" if page is not None else "E"
    nums = []

    for e in get_entities(doc):
        x = eid(e)
        if not x:
            continue
        m = re.fullmatch(re.escape(prefix) + r"(\d+)", str(x))
        if m:
            nums.append(int(m.group(1)))

    return f"{prefix}{max(nums, default=0) + 1:03d}"


def next_relation_id(doc, page):
    prefix = f"P{page}_R" if page is not None else "R"
    nums = []

    for r in get_relations(doc):
        x = rid(r)
        if not x:
            continue
        m = re.fullmatch(re.escape(prefix) + r"(\d+)", str(x))
        if m:
            nums.append(int(m.group(1)))

    return f"{prefix}{max(nums, default=0) + 1:03d}"


def find_entity(doc, entity_id):
    for e in get_entities(doc):
        if eid(e) == entity_id:
            return e
    return None


def relation_exists(doc, source_id, target_id):
    return any(
        rtype(r) == RELATION_TYPE
        and rsource(r) == source_id
        and rtarget(r) == target_id
        for r in get_relations(doc)
    )


def append_relation(doc, relation, page):
    if isinstance(doc.get("global_relations"), list):
        doc["global_relations"].append(relation)

    # Synchroniser pages si elles existent.
    for p in doc.get("pages", []) or []:
        pnum = p.get("page") or p.get("page_number") or p.get("numero_page")
        if page is not None and pnum == page:
            p.setdefault("relations", []).append(copy.deepcopy(relation))
            break


def append_entity(doc, entity, page):
    if isinstance(doc.get("global_entities"), list):
        doc["global_entities"].append(entity)

    for p in doc.get("pages", []) or []:
        pnum = p.get("page") or p.get("page_number") or p.get("numero_page")
        if page is not None and pnum == page:
            p.setdefault("entities", []).append(copy.deepcopy(entity))
            break


def make_relation(doc, source_id, target_id, page):
    return {
        "identifiant_relation": next_relation_id(doc, page),
        "type_relation": RELATION_TYPE,
        "identifiant_entite_sujet": source_id,
        "identifiant_entite_objet": target_id,
        "page": page,
        "provenance_sgce": {
            "pattern": "A1",
            "method": "automatic_conservative",
        },
    }


def build_posology_text(components):
    """
    Conserve uniquement l'information explicitement détectée.
    Aucun ajout/inférence.
    """
    ordered = ("dose", "rate", "frequency", "route", "duration")
    values = []

    for family in ordered:
        for value in components.get(family, []):
            if value not in values:
                values.append(value)

    return " ".join(values).strip()


def make_posology(doc, result, components):
    src = result.get("source_entity") or {}
    page = src.get("page")
    value = build_posology_text(components)

    return {
        "identifiant_entite": next_entity_id(doc, page),
        "categorie": "POSOLOGIE",
        "name": value,
        "valeur": value,
        "preuve": src.get("preuve") or result.get("detection_text"),
        "page": page,
        "provenance_sgce": {
            "pattern": "A1",
            "method": "automatic_conservative",
            "source_entity_id": src.get("id"),
            "explicit_components": components,
        },
    }


def choose_validation_report():
    for p in VALIDATION_REPORTS:
        if p.exists():
            return p
    raise FileNotFoundError(
        "Rapport de validation A1 introuvable:\n- "
        + "\n- ".join(str(p) for p in VALIDATION_REPORTS)
    )


def decide(result):
    status = result.get("validation_status")

    if status in {"ALREADY_CORRECT", "AMBIGUOUS"}:
        return "SKIP", status

    if status == "MISSING_RELATION":
        best = result.get("best_posology_match") or {}

        if (
            best.get("target_id")
            and float(best.get("medication_anchor") or 0) >= MIN_ANCHOR
            and float(best.get("final_score") or 0) >= MIN_MATCH_SCORE
        ):
            return "LINK", "AUTO_APPROVED_LINK"

        return "SKIP", "LINK_NOT_RELIABLE_ENOUGH"

    if status == "CONFIRMED_PATTERN_A":
        components = explicit_independent_components(result)

        if (
            result.get("signal_strength") in {"MEDIUM", "STRONG"}
            and len(components) >= 2
            and not result.get("best_posology_match")
        ):
            return "SPLIT", "AUTO_APPROVED_SPLIT"

        return "SKIP", "SPLIT_NOT_RELIABLE_ENOUGH"

    return "SKIP", "UNKNOWN_STATUS"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    validation_path = choose_validation_report()

    with validation_path.open("r", encoding="utf-8") as f:
        validation = json.load(f)

    results = validation.get("results", [])
    by_doc = {}

    for r in results:
        name = r.get("document")
        if name:
            by_doc.setdefault(name, []).append(r)

    operations = []
    counters = Counter()
    errors = []

    print("=" * 78)
    print("PATTERN A1 - AUTO CORRECTOR")
    print("=" * 78)
    print(f"Validation : {validation_path}")
    print(f"Candidats  : {len(results)}")
    print()

    # Copier/corriger TOUS les JSON d'entrée.
    for input_path in sorted(INPUT_DIR.glob("*.json")):
        try:
            with input_path.open("r", encoding="utf-8") as f:
                doc = json.load(f)

            doc_results = by_doc.get(input_path.name, [])

            for result in doc_results:
                action, reason = decide(result)
                status = result.get("validation_status")
                src = result.get("source_entity") or {}
                source_id = src.get("id")
                page = src.get("page")

                op = {
                    "document": input_path.name,
                    "source_entity_id": source_id,
                    "source_name": src.get("name"),
                    "source_preuve": src.get("preuve"),
                    "validation_status": status,
                    "decision": action,
                    "decision_reason": reason,
                    "applied": False,
                }

                if action == "SKIP":
                    counters["skipped"] += 1
                    counters[f"skip_{reason}"] += 1
                    operations.append(op)
                    continue

                if action == "LINK":
                    best = result.get("best_posology_match") or {}
                    target_id = best.get("target_id")

                    if not find_entity(doc, source_id):
                        op["error"] = "SOURCE_NOT_FOUND"
                        counters["errors"] += 1
                        operations.append(op)
                        continue

                    target = find_entity(doc, target_id)
                    if not target or etype(target) != "POSOLOGIE":
                        op["error"] = "POSOLOGIE_TARGET_NOT_FOUND"
                        counters["errors"] += 1
                        operations.append(op)
                        continue

                    if relation_exists(doc, source_id, target_id):
                        op["decision"] = "SKIP"
                        op["decision_reason"] = "RELATION_ALREADY_EXISTS"
                        counters["skipped"] += 1
                        operations.append(op)
                        continue

                    rel = make_relation(doc, source_id, target_id, page)
                    append_relation(doc, rel, page)

                    op["target_entity_id"] = target_id
                    op["new_relation_id"] = rid(rel)
                    op["applied"] = True
                    counters["links_applied"] += 1
                    counters["operations_applied"] += 1
                    operations.append(op)
                    continue

                if action == "SPLIT":
                    if not find_entity(doc, source_id):
                        op["error"] = "SOURCE_NOT_FOUND"
                        counters["errors"] += 1
                        operations.append(op)
                        continue

                    components = explicit_independent_components(result)
                    posology = make_posology(doc, result, components)

                    if not posology.get("name"):
                        op["error"] = "EMPTY_POSOLOGY"
                        counters["errors"] += 1
                        operations.append(op)
                        continue

                    append_entity(doc, posology, page)

                    rel = make_relation(
                        doc,
                        source_id,
                        eid(posology),
                        page,
                    )
                    append_relation(doc, rel, page)

                    op["new_posology_id"] = eid(posology)
                    op["new_posology_text"] = posology.get("name")
                    op["new_relation_id"] = rid(rel)
                    op["explicit_components"] = components
                    op["applied"] = True

                    counters["splits_applied"] += 1
                    counters["operations_applied"] += 1
                    operations.append(op)

            output_path = OUTPUT_DIR / input_path.name

            with output_path.open("w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False, indent=2)

            counters["documents_copied"] += 1

            applied_here = sum(
                1 for o in operations
                if o["document"] == input_path.name and o["applied"]
            )

            if applied_here:
                counters["documents_modified"] += 1
                print(
                    f"[MODIFIÉ] {input_path.name} "
                    f"| opérations={applied_here}"
                )

        except Exception as exc:
            errors.append({
                "document": input_path.name,
                "error": str(exc),
            })
            counters["errors"] += 1
            print(f"[ERREUR] {input_path.name}: {exc}")

    actionable_input = sum(
        1 for r in results
        if r.get("validation_status")
        in {"MISSING_RELATION", "CONFIRMED_PATTERN_A"}
    )

    report = {
        "pattern": "A1_TRAITEMENT_POSOLOGIE",
        "mode": "AUTOMATIC_CONSERVATIVE",
        "validation_report": str(validation_path),
        "input_candidates": len(results),
        "input_actionable_cases": actionable_input,
        "automatic_rules": {
            "LINK": {
                "minimum_medication_anchor": MIN_ANCHOR,
                "minimum_final_score": MIN_MATCH_SCORE,
            },
            "SPLIT": {
                "allowed_signal_strength": ["MEDIUM", "STRONG"],
                "minimum_independent_explicit_component_families": 2,
                "requires_no_reliable_existing_posology": True,
            },
            "ambiguous_policy": "NEVER_MODIFY",
        },
        "summary": dict(counters),
        "operations": operations,
        "errors": errors,
    }

    with OUTPUT_REPORT.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 78)
    print("RÉSUMÉ CORRECTION AUTOMATIQUE A1")
    print("=" * 78)
    print(f"Cas actionnables en entrée : {actionable_input}")
    print(f"LINK appliqués             : {counters['links_applied']}")
    print(f"SPLIT appliqués            : {counters['splits_applied']}")
    print(f"Opérations appliquées      : {counters['operations_applied']}")
    print(f"Cas ignorés / protégés     : {counters['skipped']}")
    print(f"Documents copiés           : {counters['documents_copied']}")
    print(f"Documents modifiés         : {counters['documents_modified']}")
    print(f"Erreurs                    : {counters['errors']}")
    print()
    print(f"Sortie  : {OUTPUT_DIR}")
    print(f"Rapport : {OUTPUT_REPORT}")
    print()
    print("Les fichiers originaux n'ont pas été modifiés.")


if __name__ == "__main__":
    main()
