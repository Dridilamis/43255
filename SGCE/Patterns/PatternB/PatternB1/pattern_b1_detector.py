# -*- coding: utf-8 -*-
"""
pattern_b1_detector.py
======================

SGCE — Pattern B1 Detection Only

Pattern B:
Entité manquante implicite.

B1 détecte les cas les plus sûrs :
une relation clinique référence une entité source ou cible qui n'existe pas
dans la liste des entités du document.

Exemples structurels :
    relation(source=X, target=Y)
    mais X ou Y est absent des entités.

Cette étape :
- NE CRÉE aucune entité ;
- NE MODIFIE aucun JSON clinique ;
- produit uniquement des candidats B1.

Entrée :
PatternA6/pattern_a6_corrected
"""

import csv
import json
from collections import Counter
from pathlib import Path


# ============================================================
# 1. PATHS
# ============================================================

PATTERN_B1_DIR = Path(__file__).resolve().parent
PATTERN_B_DIR = PATTERN_B1_DIR.parent
PATTERNS_DIR = PATTERN_B_DIR.parent
SGCE_DIR = PATTERNS_DIR.parent
BASE_DIR = SGCE_DIR.parent

PATTERN_A6_DIR = PATTERNS_DIR / "PatternA" / "PatternA6"

INPUT_DIR_CANDIDATES = [
    PATTERN_A6_DIR / "corrected",
]

OUTPUT_DIR = PATTERN_B1_DIR / "detection"
OUTPUT_JSON = OUTPUT_DIR / "pattern_b1_detection_report.json"
OUTPUT_CSV = OUTPUT_DIR / "pattern_b1_candidates.csv"

# ============================================================
# 2. HELPERS
# ============================================================

def resolve_input_dir():
    for p in INPUT_DIR_CANDIDATES:
        if p.exists() and any(p.glob("*.json")):
            return p
    raise FileNotFoundError("Dossier d'entrée clinique introuvable.")


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


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


def entity_name(e):
    for k in ("name", "valeur", "libelle", "preuve", "texte", "text"):
        v = e.get(k)
        if v not in (None, ""):
            return str(v).strip()
    return ""


def entity_type(e):
    return e.get("categorie") or e.get("type") or ""


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
        out.extend(page.get("entities", []) or [])
    return out


def get_relations(doc):
    if isinstance(doc.get("global_relations"), list):
        return doc["global_relations"]

    out = []
    for page in doc.get("pages", []) or []:
        out.extend(page.get("relations", []) or [])
    return out


# ============================================================
# 3. ENDPOINT RESOLUTION
# ============================================================

def build_entity_indexes(entities):
    """
    Deux index :
    - IDs
    - noms textuels exacts

    Ceci permet de fonctionner avec des JSON où les relations utilisent
    soit des IDs, soit des noms d'entités.
    """

    by_id = {}
    by_name = {}

    for e in entities:
        eid = entity_id(e)
        name = entity_name(e)

        if eid:
            by_id[str(eid).strip()] = e

        if name:
            by_name.setdefault(name.strip().lower(), []).append(e)

    return by_id, by_name


def resolve_endpoint(value, by_id, by_name):
    if value in (None, ""):
        return None, "EMPTY"

    value = str(value).strip()

    if value in by_id:
        return by_id[value], "ID"

    name_key = value.lower()
    matches = by_name.get(name_key, [])

    if len(matches) == 1:
        return matches[0], "NAME"

    if len(matches) > 1:
        return None, "AMBIGUOUS_NAME"

    return None, "NOT_FOUND"


# ============================================================
# 4. MAIN DETECTION
# ============================================================

def main():
    input_dir = resolve_input_dir()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    json_files = sorted(input_dir.glob("*.json"))

    clinical_documents = 0
    skipped_nonclinical = []
    errors = []

    total_entities = 0
    total_relations = 0

    candidates = []

    for path in json_files:
        try:
            doc = load_json(path)

            if not is_clinical_document(doc):
                skipped_nonclinical.append(path.name)
                continue

            clinical_documents += 1

            entities = get_entities(doc)
            relations = get_relations(doc)

            total_entities += len(entities)
            total_relations += len(relations)

            by_id, by_name = build_entity_indexes(entities)

            for rel in relations:
                rid = relation_id(rel)
                rtype = relation_type(rel)
                src_value = relation_source(rel)
                tgt_value = relation_target(rel)

                src_ent, src_mode = resolve_endpoint(
                    src_value,
                    by_id,
                    by_name,
                )

                tgt_ent, tgt_mode = resolve_endpoint(
                    tgt_value,
                    by_id,
                    by_name,
                )

                source_missing = (
                    src_ent is None
                    and src_mode == "NOT_FOUND"
                )

                target_missing = (
                    tgt_ent is None
                    and tgt_mode == "NOT_FOUND"
                )

                empty_endpoint = (
                    src_mode == "EMPTY"
                    or tgt_mode == "EMPTY"
                )

                ambiguous_endpoint = (
                    src_mode == "AMBIGUOUS_NAME"
                    or tgt_mode == "AMBIGUOUS_NAME"
                )

                # B1 = endpoint explicit dans la relation mais entité absente.
                if not (
                    source_missing
                    or target_missing
                    or empty_endpoint
                    or ambiguous_endpoint
                ):
                    continue

                if source_missing or target_missing:
                    strength = "STRONG"
                    candidate_kind = "MISSING_ENTITY_ENDPOINT"

                elif empty_endpoint:
                    strength = "MEDIUM"
                    candidate_kind = "EMPTY_RELATION_ENDPOINT"

                else:
                    strength = "WEAK"
                    candidate_kind = "AMBIGUOUS_RELATION_ENDPOINT"

                missing_roles = []

                if source_missing:
                    missing_roles.append("SOURCE")

                if target_missing:
                    missing_roles.append("TARGET")

                if src_mode == "EMPTY":
                    missing_roles.append("SOURCE_EMPTY")

                if tgt_mode == "EMPTY":
                    missing_roles.append("TARGET_EMPTY")

                if src_mode == "AMBIGUOUS_NAME":
                    missing_roles.append("SOURCE_AMBIGUOUS_NAME")

                if tgt_mode == "AMBIGUOUS_NAME":
                    missing_roles.append("TARGET_AMBIGUOUS_NAME")

                candidates.append({
                    "document": path.name,
                    "pattern": "B1",
                    "candidate_kind": candidate_kind,
                    "strength": strength,

                    "relation": {
                        "relation_id": rid,
                        "relation_type": rtype,
                        "page": relation_page(rel),
                        "source_value": src_value,
                        "target_value": tgt_value,
                    },

                    "source_resolution": {
                        "mode": src_mode,
                        "resolved_entity_id":
                            entity_id(src_ent) if src_ent else None,
                        "resolved_entity_type":
                            entity_type(src_ent) if src_ent else None,
                        "resolved_entity_name":
                            entity_name(src_ent) if src_ent else None,
                    },

                    "target_resolution": {
                        "mode": tgt_mode,
                        "resolved_entity_id":
                            entity_id(tgt_ent) if tgt_ent else None,
                        "resolved_entity_type":
                            entity_type(tgt_ent) if tgt_ent else None,
                        "resolved_entity_name":
                            entity_name(tgt_ent) if tgt_ent else None,
                    },

                    "missing_roles": missing_roles,

                    "status": "B1_CANDIDATE",
                })

        except Exception as exc:
            errors.append({
                "document": path.name,
                "error": str(exc),
            })

    strength_counts = Counter(
        c["strength"]
        for c in candidates
    )

    kind_counts = Counter(
        c["candidate_kind"]
        for c in candidates
    )

    report = {
        "pattern": "B1",
        "pattern_family": "B",
        "name": "Entité manquante implicite - endpoint relationnel absent",
        "methodological_status": "DETECTION_ONLY_NO_CORRECTION",

        "input_directory": str(input_dir),

        "summary": {
            "json_files_found": len(json_files),
            "clinical_documents_scanned": clinical_documents,
            "nonclinical_json_skipped": len(skipped_nonclinical),

            "entities_scanned": total_entities,
            "relations_scanned": total_relations,

            "b1_candidates": len(candidates),

            "weak": strength_counts.get("WEAK", 0),
            "medium": strength_counts.get("MEDIUM", 0),
            "strong": strength_counts.get("STRONG", 0),

            "errors": len(errors),
        },

        "candidate_kind_counts": dict(kind_counts),
        "candidates": candidates,
        "nonclinical_json_skipped": skipped_nonclinical,
        "errors": errors,
    }

    OUTPUT_JSON.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    fields = [
        "document",
        "relation_id",
        "relation_type",
        "page",
        "source_value",
        "target_value",
        "source_resolution",
        "target_resolution",
        "missing_roles",
        "candidate_kind",
        "strength",
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

        for c in candidates:
            rel = c["relation"]

            writer.writerow({
                "document":
                    c["document"],

                "relation_id":
                    rel["relation_id"],

                "relation_type":
                    rel["relation_type"],

                "page":
                    rel["page"],

                "source_value":
                    rel["source_value"],

                "target_value":
                    rel["target_value"],

                "source_resolution":
                    c["source_resolution"]["mode"],

                "target_resolution":
                    c["target_resolution"]["mode"],

                "missing_roles":
                    "; ".join(c["missing_roles"]),

                "candidate_kind":
                    c["candidate_kind"],

                "strength":
                    c["strength"],
            })

    print("=" * 78)
    print("SGCE - PATTERN B1 DETECTION")
    print("=" * 78)
    print(f"Entrée                  : {input_dir}")
    print(f"JSON trouvés            : {len(json_files)}")
    print(f"Documents cliniques     : {clinical_documents}")
    print(f"JSON non cliniques ignorés : {len(skipped_nonclinical)}")
    print()
    print(f"Entités analysées       : {total_entities}")
    print(f"Relations analysées     : {total_relations}")
    print()
    print(f"Candidats B1            : {len(candidates)}")
    print(f"WEAK                    : {strength_counts.get('WEAK', 0)}")
    print(f"MEDIUM                  : {strength_counts.get('MEDIUM', 0)}")
    print(f"STRONG                  : {strength_counts.get('STRONG', 0)}")
    print(f"Erreurs                 : {len(errors)}")
    print()
    print("Types de candidats :")

    if kind_counts:
        for kind, count in kind_counts.most_common():
            print(f"  {kind:<38} : {count}")
    else:
        print("  Aucun candidat B1 détecté.")

    print()
    print(f"Rapport JSON            : {OUTPUT_JSON}")
    print(f"CSV candidats           : {OUTPUT_CSV}")
    print()
    print("Aucun JSON clinique n'a été modifié.")


if __name__ == "__main__":
    main()
