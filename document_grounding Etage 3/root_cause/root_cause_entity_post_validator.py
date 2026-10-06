# -*- coding: utf-8 -*-
"""
root_cause_entity_post_validator.py
===================================

TRACE / SGCE â€” Root-Cause Entity Post Validator

Compare :
  AVANT :
    SGCE/MultiAgent/corrected

  APRES :
    document_grounding Etage 3/root_cause/root_cause_entity_safe_corrected

PASS si :
- aucun document manquant/supplÃ©mentaire
- aucune modification inattendue
- aucune correction attendue absente
- aucune nouvelle anomalie structurelle
- nombre total d'anomalies structurelles diminue ou reste stable

Aucune donnÃ©e clinique n'est modifiÃ©e.
"""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STAGE3_DIR = ROOT.parent
REDUCTION_DIR = STAGE3_DIR.parent
SGCE_DIR = REDUCTION_DIR / "SGCE"

# AVANT = sortie officielle SGCE / Multi-Agent
INPUT_DIR = Path(__file__).resolve().parents[2] / "SGCE" / "MultiAgent" / "corrected"
BEFORE_DIR = INPUT_DIR

# APRES = sortie corrigÃ©e Root Cause
AFTER_DIR = ROOT / "root_cause_entity_safe_corrected"

CORRECTION_REPORT = AFTER_DIR / "root_cause_entity_correction_report.json"

GUIDELINE_CANDIDATES = [
    REDUCTION_DIR.parent / "ontologie_sepsis_graph_v1.6.json",
    REDUCTION_DIR / "ontologie_sepsis_graph_v1.6.json",
    Path(r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM\ontologie_sepsis_graph_v1.6.json"),
]

REPORT_FILE = ROOT / "post_validation" / "root_cause_entity_post_validation_report.json"



ROOT = Path(__file__).resolve().parent
STAGE3_DIR = ROOT.parent
REDUCTION_DIR = STAGE3_DIR.parent
SGCE_DIR = REDUCTION_DIR / "SGCE"

# EntrÃ©e officielle de l'Ã©tage 3 : sortie finale SGCE / Multi-Agent.

GUIDELINE_CANDIDATES = [
    REDUCTION_DIR.parent / "ontologie_sepsis_graph_v1.6.json",
    REDUCTION_DIR / "ontologie_sepsis_graph_v1.6.json",
    Path(r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM\ontologie_sepsis_graph_v1.6.json"),
]

INPUT_FILE = ROOT / "queues" / "root_cause_entity_candidates.json"
CLINICAL_DIR = INPUT_DIR
OUTPUT_FILE = ROOT / "outputs" / "root_cause_entity_validated.json"

MIN_SUPPORT = 2
MIN_SUPPORT_RATIO = 0.60

def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def resolve_guideline():
    for path in GUIDELINE_CANDIDATES:
        if path.exists():
            return path
    raise FileNotFoundError("ontologie_sepsis_graph_v1.6.json introuvable.")

def entity_id(entity):
    return (
        entity.get("identifiant_entite")
        or entity.get("id")
        or entity.get("entity_id")
    )


def entity_type(entity):
    return (
        entity.get("categorie")
        or entity.get("type")
        or entity.get("entity_type")
        or ""
    )


def relation_id(relation):
    return (
        relation.get("identifiant_relation")
        or relation.get("id")
        or relation.get("relation_id")
    )


def relation_type(relation):
    return (
        relation.get("type_relation")
        or relation.get("relation")
        or relation.get("relation_type")
        or relation.get("predicate")
        or relation.get("type")
        or ""
    )


def relation_source(relation):
    return (
        relation.get("identifiant_entite_sujet")
        or relation.get("from_id")
        or relation.get("subject_id")
        or relation.get("source")
    )


def relation_target(relation):
    return (
        relation.get("identifiant_entite_objet")
        or relation.get("to_id")
        or relation.get("object_id")
        or relation.get("target")
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


def load_signatures():
    guideline = load_json(resolve_guideline())
    root = guideline.get("ontologie_sepsis_graph", guideline)
    relations_root = root.get("relations", {}) or {}
    signatures = {}
    if not isinstance(relations_root, dict):
        return signatures
    for group in relations_root.values():
        if not isinstance(group, dict):
            continue
        for name, spec in group.items():
            if not isinstance(spec, dict):
                continue
            domaine = spec.get("domaine")
            image = spec.get("image")
            if domaine and image:
                signatures[name] = {"domaine": domaine, "image": image}
    return signatures

def audit_document(
    doc,
    signatures,
):
    entities = {
        str(entity_id(entity)):
            entity
        for entity in get_entities(doc)
        if entity_id(entity) is not None
    }

    anomalies = set()

    for relation in get_relations(doc):
        rid = str(
            relation_id(relation)
        )

        rtype = relation_type(
            relation
        )

        source_id = relation_source(
            relation
        )

        target_id = relation_target(
            relation
        )

        source = entities.get(
            str(source_id)
        )

        target = entities.get(
            str(target_id)
        )

        if source is None:
            anomalies.add(
                (
                    "ORPHAN_SOURCE",
                    rid,
                    str(source_id),
                )
            )

        if target is None:
            anomalies.add(
                (
                    "ORPHAN_TARGET",
                    rid,
                    str(target_id),
                )
            )

        signature = signatures.get(
            rtype
        )

        if not signature:
            continue

        if (
            source is not None
            and entity_type(source)
            != signature["domaine"]
        ):
            anomalies.add(
                (
                    "INVALID_SOURCE_TYPE",
                    rid,
                    entity_type(source),
                    signature["domaine"],
                )
            )

        if (
            target is not None
            and entity_type(target)
            != signature["image"]
        ):
            anomalies.add(
                (
                    "INVALID_TARGET_TYPE",
                    rid,
                    entity_type(target),
                    signature["image"],
                )
            )

    return anomalies


def clinical_docs(directory):
    docs = {}

    for path in directory.glob("*.json"):
        if path.name.endswith("_report.json"):
            continue

        try:
            doc = load_json(path)

            if (
                isinstance(doc, dict)
                and any(
                    key in doc
                    for key in (
                        "pages",
                        "global_entities",
                        "global_relations",
                    )
                )
            ):
                docs[path.name] = doc

        except Exception:
            pass

    return docs


def canonical_hash(doc):
    return hashlib.sha256(
        json.dumps(
            doc,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def main():
    before_docs = clinical_docs(
        BEFORE_DIR
    )

    after_docs = clinical_docs(
        AFTER_DIR
    )

    correction_report = load_json(
        CORRECTION_REPORT
    )

    signatures = load_signatures()

    before_names = set(
        before_docs
    )

    after_names = set(
        after_docs
    )

    common = (
        before_names
        & after_names
    )

    missing = (
        before_names
        - after_names
    )

    extra = (
        after_names
        - before_names
    )

    expected_modified = set(
        correction_report.get(
            "modified_documents",
            [],
        )
    )

    actual_modified = {
        name
        for name in common
        if canonical_hash(
            before_docs[name]
        )
        != canonical_hash(
            after_docs[name]
        )
    }

    unexpected_modified = (
        actual_modified
        - expected_modified
    )

    missing_expected = (
        expected_modified
        - actual_modified
    )

    before_map = {}

    after_map = {}

    for docname, doc in before_docs.items():
        for anomaly in audit_document(
            doc,
            signatures,
        ):
            before_map[
                (docname,) + tuple(anomaly)
            ] = anomaly

    for docname, doc in after_docs.items():
        for anomaly in audit_document(
            doc,
            signatures,
        ):
            after_map[
                (docname,) + tuple(anomaly)
            ] = anomaly

    new_anomalies = (
        set(after_map)
        - set(before_map)
    )

    resolved_anomalies = (
        set(before_map)
        - set(after_map)
    )

    final_pass = (
        not missing
        and not extra
        and not unexpected_modified
        and not missing_expected
        and len(new_anomalies) == 0
        and len(after_map)
        <= len(before_map)
    )

    report = {
        "validator":
            "root_cause_entity_post_validator",

        "status":
            "PASS"
            if final_pass
            else "FAIL",

        "summary": {
            "documents_checked":
                len(common),

            "expected_modified_documents":
                len(
                    expected_modified
                ),

            "actually_modified_documents":
                len(
                    actual_modified
                ),

            "unexpected_modifications":
                len(
                    unexpected_modified
                ),

            "missing_expected_corrections":
                len(
                    missing_expected
                ),

            "structural_anomalies_before":
                len(
                    before_map
                ),

            "structural_anomalies_after":
                len(
                    after_map
                ),

            "new_structural_anomalies":
                len(
                    new_anomalies
                ),

            "resolved_structural_anomalies":
                len(
                    resolved_anomalies
                ),

            "missing_documents":
                len(
                    missing
                ),

            "extra_documents":
                len(
                    extra
                ),
        },
    }

    save_json(
        REPORT_FILE,
        report,
    )

    print("=" * 108)
    print("TRACE / SGCE - ROOT CAUSE ENTITY POST-VALIDATION")
    print("=" * 108)

    print(
        f"Documents vÃ©rifiÃ©s                  : {len(common)}"
    )

    print(
        f"Documents attendus modifiÃ©s         : "
        f"{len(expected_modified)}"
    )

    print(
        f"Documents rÃ©ellement modifiÃ©s       : "
        f"{len(actual_modified)}"
    )

    print(
        f"Modifications inattendues           : "
        f"{len(unexpected_modified)}"
    )

    print(
        f"Corrections attendues absentes      : "
        f"{len(missing_expected)}"
    )

    print()

    print(
        f"Anomalies structurelles AVANT       : "
        f"{len(before_map)}"
    )

    print(
        f"Anomalies structurelles APRES       : "
        f"{len(after_map)}"
    )

    print(
        f"Nouvelles anomalies structurelles   : "
        f"{len(new_anomalies)}"
    )

    print(
        f"Anomalies structurelles rÃ©solues    : "
        f"{len(resolved_anomalies)}"
    )

    print()

    print(
        f"STATUT FINAL ROOT CAUSE ENTITY      : "
        f"{'PASS' if final_pass else 'FAIL'}"
    )

    print()

    print(
        f"Rapport                             : {REPORT_FILE}"
    )

    print()

    print(
        "Aucune donnÃ©e clinique n'a Ã©tÃ© modifiÃ©e par ce post-validateur."
    )


if __name__ == "__main__":
    main()

