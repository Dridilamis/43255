# -*- coding: utf-8 -*-
"""
pattern_a2_auto_corrector.py
============================

SGCE — Pattern A2 Auto-Corrector
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
- Rapport A2 Validator

Actions automatiques
--------------------
ALREADY_CORRECT
    -> SKIP

AMBIGUOUS
    -> SKIP

MISSING_RELATION
    -> LINK
       Ajoute uniquement a_pour_contexte_acquisition vers la cible
       CONTEXTE_ACQUISITION déjà séparée et validée.

CONFIRMED_PATTERN_A
    -> SPLIT
       Crée un CONTEXTE_ACQUISITION à partir des informations
       explicitement détectées dans la COMORBIDITE_ANTECEDENT,
       puis crée a_pour_contexte_acquisition.

Principes de sécurité
---------------------
- Aucun raisonnement médical externe.
- Aucune correction des cas ambigus.
- Aucun remplacement arbitraire du texte source.
- L'entité source COMORBIDITE_ANTECEDENT est conservée.
- Seule l'information de contexte explicitement détectée est structurée
  dans une nouvelle entité CONTEXTE_ACQUISITION.
- Les fichiers sources restent inchangés ; les corrections sont écrites
  dans un nouveau dossier.
"""

import copy
import json
import re
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
VALIDATION_REPORT_CANDIDATES = [
    PATTERN_A2_DIR / "validation" / "pattern_a2_validation_report.json"
]
OUTPUT_DIR = PATTERN_A2_DIR / "corrected"
CORRECTION_REPORT = OUTPUT_DIR / "pattern_a2_correction_report.json"

SOURCE_TYPE = "COMORBIDITE_ANTECEDENT"
TARGET_TYPE = "CONTEXTE_ACQUISITION"
RELATION_TYPE = "a_pour_contexte_acquisition"


# ============================================================
# 2. HELPERS
# ============================================================

def resolve_input_dir():
    for p in INPUT_DIR_CANDIDATES:
        if p.exists() and any(p.glob("*.json")):
            return p
    raise FileNotFoundError("Aucun dossier JSON clinique trouvé.")


def resolve_validation_report():
    for p in VALIDATION_REPORT_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError(
        "Rapport de validation A2 introuvable.\n"
        + "\n".join(f"- {p}" for p in VALIDATION_REPORT_CANDIDATES)
    )


def entity_id(e):
    return e.get("identifiant_entite") or e.get("id") or e.get("entity_id")


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


def is_clinical_document(doc):
    return (
        isinstance(doc, dict)
        and (
            isinstance(doc.get("global_entities"), list)
            or isinstance(doc.get("pages"), list)
        )
    )


def find_page(doc, page_number):
    for page in doc.get("pages", []) or []:
        pnum = page.get("page")
        if pnum is None:
            pnum = page.get("page_number")
        if pnum == page_number:
            return page
    return None


def source_entity(doc, source_id):
    for e in get_entities(doc):
        if entity_id(e) == source_id and entity_type(e) == SOURCE_TYPE:
            return e
    return None


def target_entity(doc, target_id):
    for e in get_entities(doc):
        if entity_id(e) == target_id and entity_type(e) == TARGET_TYPE:
            return e
    return None


def relation_exists(doc, source_id, target_id):
    return any(
        relation_type(r) == RELATION_TYPE
        and relation_source(r) == source_id
        and relation_target(r) == target_id
        for r in get_relations(doc)
    )


# ============================================================
# 3. IDs
# ============================================================

ENTITY_ID_RE = re.compile(r"^P(?P<page>\d+)_E(?P<num>\d+)$")
REL_ID_RE = re.compile(r"^P(?P<page>\d+)_R(?P<num>\d+)$")


def next_entity_id(doc, page_number):
    max_num = 0

    for e in get_entities(doc):
        eid = entity_id(e)
        if not eid:
            continue

        m = ENTITY_ID_RE.match(str(eid))
        if m and int(m.group("page")) == int(page_number):
            max_num = max(max_num, int(m.group("num")))

    return f"P{int(page_number)}_E{max_num + 1:03d}"


def next_relation_id(doc, page_number):
    max_num = 0

    for r in get_relations(doc):
        rid = relation_id(r)
        if not rid:
            continue

        m = REL_ID_RE.match(str(rid))
        if m and int(m.group("page")) == int(page_number):
            max_num = max(max_num, int(m.group("num")))

    return f"P{int(page_number)}_R{max_num + 1:03d}"


# ============================================================
# 4. CONSTRUCTION CONTEXTE
# ============================================================

def extract_surface(candidate):
    """
    Construit la surface cible uniquement à partir des signaux
    explicitement détectés par A2 Detector.
    """

    ordered_families = [
        "TYPE_ACQUISITION",
        "HOSPITALISATION_PREALABLE",
        "EXPOSITION_ANTIBIOTIQUE_RECENTE",
        "DISPOSITIF_INVASIF",
    ]

    signals = candidate.get("detected_context_signals") or {}
    parts = []

    for family in ordered_families:
        values = signals.get(family) or []
        for value in values:
            value = str(value).strip()
            if value and value not in parts:
                parts.append(value)

    # Si le detector a une valeur canonique mais aucune surface exploitable.
    if not parts:
        for value in candidate.get("authorized_type_acquisition_hits") or []:
            value = str(value).strip()
            if value and value not in parts:
                parts.append(value)

    return " ; ".join(parts).strip()


def infer_type_acquisition(candidate):
    hits = candidate.get("authorized_type_acquisition_hits") or []
    if len(hits) == 1:
        return hits[0]
    return None


def build_context_entity(new_id, source, candidate):
    surface = extract_surface(candidate)
    page = entity_page(source)

    entity = {
        "identifiant_entite": new_id,
        "categorie": TARGET_TYPE,
        "parametre": "contexte_acquisition",
        "valeur": surface or None,
        "unite": None,
        "horodatage": None,
        "preuve": surface or candidate.get("source_entity", {}).get("text"),
        "nie": False,
        "confiance": "elevee",
        "type_inference": "correction_structurelle_sgce",
        "page": page,
        "valeur_reference": None,
        "name": surface or TARGET_TYPE,
        "type": TARGET_TYPE,

        # Attribut TRACE-Sepsis v1.6 renseigné seulement si déterminable.
        "type_acquisition": infer_type_acquisition(candidate),

        # Provenance SGCE.
        "_sgce_created": True,
        "_sgce_pattern": "A",
        "_sgce_subcase": "A2_COMORBIDITE_CONTEXTE_ACQUISITION",
        "_sgce_operation": "SPLIT",
        "_sgce_source_entity_id": entity_id(source),
    }

    return entity


def build_relation(new_id, source_id, target_id, page, operation):
    return {
        "identifiant_relation": new_id,
        "type_relation": RELATION_TYPE,
        "identifiant_entite_sujet": source_id,
        "identifiant_entite_objet": target_id,
        "page": page,

        # Champs alternatifs pour compatibilité.
        "relation": RELATION_TYPE,
        "from_id": source_id,
        "to_id": target_id,
        "type": RELATION_TYPE,

        # Provenance SGCE.
        "_sgce_created": True,
        "_sgce_pattern": "A",
        "_sgce_subcase": "A2_COMORBIDITE_CONTEXTE_ACQUISITION",
        "_sgce_operation": operation,
    }


# ============================================================
# 5. AJOUTS SYNCHRONISES
# ============================================================

def add_entity(doc, entity):
    """
    Ajoute dans global_entities et, si disponible, dans la page.
    """
    eid = entity_id(entity)

    if isinstance(doc.get("global_entities"), list):
        if not any(entity_id(e) == eid for e in doc["global_entities"]):
            doc["global_entities"].append(copy.deepcopy(entity))

    page = find_page(doc, entity_page(entity))
    if page is not None:
        if not isinstance(page.get("entities"), list):
            page["entities"] = []

        if not any(entity_id(e) == eid for e in page["entities"]):
            page["entities"].append(copy.deepcopy(entity))

    # Cas sans global_entities.
    if not isinstance(doc.get("global_entities"), list) and page is None:
        raise ValueError(
            f"Impossible d'ajouter l'entité {eid}: page introuvable."
        )


def add_relation(doc, relation):
    """
    Ajoute dans global_relations et, si disponible, dans la page.
    """
    rid = relation_id(relation)

    if isinstance(doc.get("global_relations"), list):
        if not any(relation_id(r) == rid for r in doc["global_relations"]):
            doc["global_relations"].append(copy.deepcopy(relation))

    page = find_page(doc, relation.get("page"))
    if page is not None:
        if not isinstance(page.get("relations"), list):
            page["relations"] = []

        if not any(relation_id(r) == rid for r in page["relations"]):
            page["relations"].append(copy.deepcopy(relation))

    if not isinstance(doc.get("global_relations"), list) and page is None:
        raise ValueError(
            f"Impossible d'ajouter la relation {rid}: page introuvable."
        )


# ============================================================
# 6. CORRECTION D'UN CANDIDAT
# ============================================================

def correct_candidate(doc, item):
    status = item.get("validation_status")
    action = item.get("recommended_future_action")

    source_info = item.get("source_entity") or {}
    source_id = source_info.get("entity_id")

    source = source_entity(doc, source_id)
    if source is None:
        raise ValueError(
            f"Source {source_id} introuvable."
        )

    page = entity_page(source)

    # --------------------------------------------------------
    # Protection
    # --------------------------------------------------------
    if status in {"ALREADY_CORRECT", "AMBIGUOUS"}:
        return {
            "operation": "SKIP",
            "source_entity_id": source_id,
            "reason": status,
            "modified": False,
        }

    # --------------------------------------------------------
    # LINK
    # --------------------------------------------------------
    if status == "MISSING_RELATION" and action == "LINK":
        target_info = item.get("reliable_target") or {}
        target_id = target_info.get("entity_id")

        if not target_id:
            raise ValueError(
                f"Cible fiable manquante pour LINK {source_id}."
            )

        target = target_entity(doc, target_id)
        if target is None:
            raise ValueError(
                f"Cible {target_id} introuvable pour LINK."
            )

        if relation_exists(doc, source_id, target_id):
            return {
                "operation": "SKIP",
                "source_entity_id": source_id,
                "target_entity_id": target_id,
                "reason": "RELATION_ALREADY_EXISTS_AT_CORRECTION_TIME",
                "modified": False,
            }

        rid = next_relation_id(doc, page)

        relation = build_relation(
            rid,
            source_id,
            target_id,
            page,
            "LINK",
        )

        add_relation(doc, relation)

        return {
            "operation": "LINK",
            "source_entity_id": source_id,
            "target_entity_id": target_id,
            "relation_id": rid,
            "relation_type": RELATION_TYPE,
            "modified": True,
        }

    # --------------------------------------------------------
    # SPLIT
    # --------------------------------------------------------
    if status == "CONFIRMED_PATTERN_A" and action == "SPLIT":
        surface = extract_surface(item)

        if not surface:
            return {
                "operation": "SKIP",
                "source_entity_id": source_id,
                "reason": "NO_EXPLICIT_CONTEXT_SURFACE",
                "modified": False,
            }

        new_target_id = next_entity_id(doc, page)

        new_target = build_context_entity(
            new_target_id,
            source,
            item,
        )

        add_entity(doc, new_target)

        rid = next_relation_id(doc, page)

        relation = build_relation(
            rid,
            source_id,
            new_target_id,
            page,
            "SPLIT",
        )

        add_relation(doc, relation)

        return {
            "operation": "SPLIT",
            "source_entity_id": source_id,
            "created_target_entity_id": new_target_id,
            "created_target_type": TARGET_TYPE,
            "created_target_surface": surface,
            "relation_id": rid,
            "relation_type": RELATION_TYPE,
            "modified": True,
        }

    return {
        "operation": "SKIP",
        "source_entity_id": source_id,
        "reason": "UNSUPPORTED_STATUS_ACTION_COMBINATION",
        "modified": False,
    }


# ============================================================
# 7. MAIN
# ============================================================

def main():
    input_dir = resolve_input_dir()
    validation_report = resolve_validation_report()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with validation_report.open("r", encoding="utf-8") as f:
        validation = json.load(f)

    validated = validation.get("validated_candidates", [])

    # Index des candidats par document.
    by_document = {}
    for item in validated:
        filename = item.get("document")
        by_document.setdefault(filename, []).append(item)

    json_files = sorted(input_dir.glob("*.json"))

    operations = []
    errors = []
    copied_documents = 0
    modified_documents = 0
    skipped_nonclinical = []

    for path in json_files:
        try:
            with path.open("r", encoding="utf-8") as f:
                original = json.load(f)

            if not is_clinical_document(original):
                skipped_nonclinical.append(path.name)
                continue

            doc = copy.deepcopy(original)
            doc_operations = []

            for item in by_document.get(path.name, []):
                try:
                    op = correct_candidate(doc, item)
                    op["document"] = path.name
                    doc_operations.append(op)
                    operations.append(op)
                except Exception as exc:
                    err = {
                        "document": path.name,
                        "source_entity_id": (
                            item.get("source_entity") or {}
                        ).get("entity_id"),
                        "error": str(exc),
                    }
                    errors.append(err)

            out_path = OUTPUT_DIR / path.name
            out_path.write_text(
                json.dumps(doc, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            copied_documents += 1

            if any(op.get("modified") for op in doc_operations):
                modified_documents += 1

        except Exception as exc:
            errors.append({
                "document": path.name,
                "error": str(exc),
            })

    counts = Counter(op["operation"] for op in operations)

    report = {
        "pattern": "A2",
        "name": "COMORBIDITE_ANTECEDENT + CONTEXTE_ACQUISITION",
        "relation": RELATION_TYPE,
        "input_directory": str(input_dir),
        "validation_report": str(validation_report),
        "output_directory": str(OUTPUT_DIR),

        "summary": {
            "validated_candidates": len(validated),
            "operations_total": sum(
                1 for op in operations if op.get("modified")
            ),
            "link": counts.get("LINK", 0),
            "split": counts.get("SPLIT", 0),
            "skip": counts.get("SKIP", 0),
            "documents_copied": copied_documents,
            "documents_modified": modified_documents,
            "nonclinical_json_skipped": len(skipped_nonclinical),
            "errors": len(errors),
        },

        "operations": operations,
        "nonclinical_json_skipped": skipped_nonclinical,
        "errors": errors,
    }

    CORRECTION_REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("=" * 76)
    print("SGCE - PATTERN A2 AUTOMATIC CORRECTION")
    print("=" * 76)
    print(f"Entrée                  : {input_dir}")
    print(f"Validation              : {validation_report}")
    print(f"Sortie                  : {OUTPUT_DIR}")
    print()
    print(f"Candidats validés       : {len(validated)}")
    print(f"Opérations appliquées   : {report['summary']['operations_total']}")
    print(f"LINK                    : {counts.get('LINK', 0)}")
    print(f"SPLIT                   : {counts.get('SPLIT', 0)}")
    print(f"SKIP                    : {counts.get('SKIP', 0)}")
    print()
    print(f"Documents copiés        : {copied_documents}")
    print(f"Documents modifiés      : {modified_documents}")
    print(f"JSON non cliniques ignorés : {len(skipped_nonclinical)}")
    print(f"Erreurs                 : {len(errors)}")
    print()
    print(f"Rapport                  : {CORRECTION_REPORT}")
    print()
    print("Les fichiers sources n'ont pas été modifiés.")


if __name__ == "__main__":
    main()
