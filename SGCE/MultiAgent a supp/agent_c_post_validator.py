# -*- coding: utf-8 -*-
"""
agent_c_post_validator.py
TRACE / SGCE â€” Differential post-validation for Agent C

Compares:
  BEFORE = MultiAgent/agent_b_corrected
  AFTER  = MultiAgent/agent_c_corrected

Checks:
- expected modified documents
- unexpected modifications
- every APPLIED operation
- removed entities are really absent
- no relation still references removed entities
- no new orphan endpoints
- no missing/extra clinical documents

No clinical data is modified.
"""

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


BASE_DIR = Path(
    r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM"
    r"\Reduction_hallucinations"
)
MULTIAGENT_DIR = BASE_DIR / "MultiAgent"

BEFORE_DIR_CANDIDATES = [
    MULTIAGENT_DIR / "agent_b_corrected",
    BASE_DIR / "PatternD" / "pattern_d_corrected",
]

AFTER_DIR = MULTIAGENT_DIR / "agent_c_corrected"
CORRECTION_REPORT = AFTER_DIR / "agent_c_correction_report.json"

OUTPUT_DIR = MULTIAGENT_DIR / "agent_c_post_validation"
REPORT_FILE = OUTPUT_DIR / "agent_c_post_validation_report.json"
DOCS_CSV = OUTPUT_DIR / "agent_c_post_validation_documents.csv"
OPS_CSV = OUTPUT_DIR / "agent_c_post_validation_operations.csv"
NEW_ANOMALIES_CSV = OUTPUT_DIR / "agent_c_new_anomalies.csv"


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def resolve_before_dir():
    for directory in BEFORE_DIR_CANDIDATES:
        if directory.exists() and any(directory.glob("*.json")):
            return directory
    raise FileNotFoundError("Dossier AVANT introuvable.")


def entity_id(entity):
    return (
        entity.get("identifiant_entite")
        or entity.get("id")
        or entity.get("entity_id")
    )


def relation_id(rel):
    return (
        rel.get("identifiant_relation")
        or rel.get("id")
        or rel.get("relation_id")
    )


def relation_source(rel):
    return (
        rel.get("identifiant_entite_sujet")
        or rel.get("from_id")
        or rel.get("subject_id")
        or rel.get("source")
    )


def relation_target(rel):
    return (
        rel.get("identifiant_entite_objet")
        or rel.get("to_id")
        or rel.get("object_id")
        or rel.get("target")
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


def find_entity(doc, eid):
    return next(
        (
            e for e in get_entities(doc)
            if str(entity_id(e)) == str(eid)
        ),
        None,
    )


def canonical_hash(doc):
    blob = json.dumps(
        doc,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def clinical_files(directory):
    files = {}

    for path in directory.glob("*.json"):
        # Ignore correction/report JSONs.
        if path.name.endswith("_report.json"):
            continue

        try:
            data = load_json(path)
        except Exception:
            continue

        if not isinstance(data, dict):
            continue

        # Clinical files should contain entities/relations/pages.
        if not any(
            key in data
            for key in (
                "global_entities",
                "global_relations",
                "pages",
            )
        ):
            continue

        files[path.name] = data

    return files


def orphan_anomalies(doc, document):
    entities = {
        str(entity_id(e))
        for e in get_entities(doc)
        if entity_id(e) is not None
    }

    anomalies = []

    for rel in get_relations(doc):
        rid = relation_id(rel)
        source = relation_source(rel)
        target = relation_target(rel)

        if source is not None and str(source) not in entities:
            anomalies.append({
                "document": document,
                "type": "ORPHAN_RELATION_SOURCE",
                "relation_id": rid,
                "endpoint": source,
            })

        if target is not None and str(target) not in entities:
            anomalies.append({
                "document": document,
                "type": "ORPHAN_RELATION_TARGET",
                "relation_id": rid,
                "endpoint": target,
            })

    return anomalies


def anomaly_key(a):
    return (
        a.get("document"),
        a.get("type"),
        str(a.get("relation_id")),
        str(a.get("endpoint")),
    )


def write_csv(path, rows, fieldnames):
    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def main():
    before_dir = resolve_before_dir()

    if not AFTER_DIR.exists():
        raise FileNotFoundError(
            f"Dossier APRES introuvable : {AFTER_DIR}"
        )

    if not CORRECTION_REPORT.exists():
        raise FileNotFoundError(
            f"Rapport correction introuvable : {CORRECTION_REPORT}"
        )

    before_docs = clinical_files(before_dir)
    after_docs = clinical_files(AFTER_DIR)
    correction_report = load_json(CORRECTION_REPORT)

    operations = [
        op
        for op in correction_report.get("operations", [])
        if op.get("status") == "APPLIED"
    ]

    expected_modified = {
        op.get("document")
        for op in operations
        if op.get("document")
    }

    before_names = set(before_docs)
    after_names = set(after_docs)

    missing_after = sorted(before_names - after_names)
    extra_after = sorted(after_names - before_names)

    common = sorted(before_names & after_names)

    actually_modified = set()
    document_rows = []

    for name in common:
        changed = (
            canonical_hash(before_docs[name])
            != canonical_hash(after_docs[name])
        )

        if changed:
            actually_modified.add(name)

        expected = name in expected_modified

        if expected and changed:
            status = "PASS"
            reason = "EXPECTED_MODIFICATION_PRESENT"
        elif expected and not changed:
            status = "FAIL"
            reason = "EXPECTED_MODIFICATION_ABSENT"
        elif not expected and changed:
            status = "FAIL"
            reason = "UNEXPECTED_MODIFICATION"
        else:
            status = "PASS"
            reason = "UNCHANGED_AS_EXPECTED"

        document_rows.append({
            "document": name,
            "expected_modified": expected,
            "actually_modified": changed,
            "status": status,
            "reason": reason,
        })

    operation_rows = []
    operation_pass = 0
    operation_fail = 0

    for op in operations:
        document = op.get("document")
        action = op.get("action")
        candidate_id = op.get("candidate_id")

        after_doc = after_docs.get(document)

        passed = False
        reason = ""

        if after_doc is None:
            reason = "DOCUMENT_MISSING_AFTER"

        elif action == "REMOVE_REIFIED_ENTITY":
            eid = op.get("entity_id")

            entity_absent = (
                find_entity(after_doc, eid)
                is None
            )

            dangling = [
                r for r in get_relations(after_doc)
                if (
                    str(relation_source(r)) == str(eid)
                    or str(relation_target(r)) == str(eid)
                )
            ]

            passed = (
                entity_absent
                and len(dangling) == 0
            )

            reason = (
                "ENTITY_REMOVED_NO_DANGLING_RELATION"
                if passed
                else "REMOVE_POSTCONDITION_FAILED"
            )

        elif action == "MERGE":
            source_id = op.get("source_entity_id")
            target_id = op.get("target_entity_id")

            source_absent = (
                find_entity(after_doc, source_id)
                is None
            )

            target_present = (
                find_entity(after_doc, target_id)
                is not None
            )

            old_refs = [
                r for r in get_relations(after_doc)
                if (
                    str(relation_source(r)) == str(source_id)
                    or str(relation_target(r)) == str(source_id)
                )
            ]

            passed = (
                source_absent
                and target_present
                and len(old_refs) == 0
            )

            reason = (
                "MERGE_POSTCONDITIONS_SATISFIED"
                if passed
                else "MERGE_POSTCONDITION_FAILED"
            )

        else:
            reason = "UNSUPPORTED_APPLIED_ACTION"

        if passed:
            operation_pass += 1
            status = "PASS"
        else:
            operation_fail += 1
            status = "FAIL"

        operation_rows.append({
            "candidate_id": candidate_id,
            "document": document,
            "action": action,
            "status": status,
            "reason": reason,
        })

    before_anomalies = []
    after_anomalies = []

    for name, doc in before_docs.items():
        before_anomalies.extend(
            orphan_anomalies(doc, name)
        )

    for name, doc in after_docs.items():
        after_anomalies.extend(
            orphan_anomalies(doc, name)
        )

    before_map = {
        anomaly_key(a): a
        for a in before_anomalies
    }

    after_map = {
        anomaly_key(a): a
        for a in after_anomalies
    }

    new_keys = set(after_map) - set(before_map)
    resolved_keys = set(before_map) - set(after_map)

    new_anomalies = [
        after_map[k]
        for k in sorted(new_keys)
    ]

    resolved_anomalies = [
        before_map[k]
        for k in sorted(resolved_keys)
    ]

    unexpected_modified = sorted(
        actually_modified - expected_modified
    )

    absent_expected = sorted(
        expected_modified - actually_modified
    )

    docs_pass = sum(
        1
        for row in document_rows
        if row["status"] == "PASS"
    )

    docs_fail = sum(
        1
        for row in document_rows
        if row["status"] == "FAIL"
    )

    final_pass = (
        docs_fail == 0
        and operation_fail == 0
        and len(new_anomalies) == 0
        and len(missing_after) == 0
        and len(extra_after) == 0
        and len(unexpected_modified) == 0
        and len(absent_expected) == 0
    )

    report = {
        "validator": "agent_c_post_validator",
        "before_directory": str(before_dir),
        "after_directory": str(AFTER_DIR),
        "status": "PASS" if final_pass else "FAIL",
        "summary": {
            "documents_checked": len(common),
            "documents_pass": docs_pass,
            "documents_fail": docs_fail,
            "expected_modified_documents": len(expected_modified),
            "actually_modified_documents": len(actually_modified),
            "unexpected_modifications": len(unexpected_modified),
            "missing_expected_corrections": len(absent_expected),
            "operations_checked": len(operations),
            "operations_pass": operation_pass,
            "operations_fail": operation_fail,
            "preexisting_orphan_anomalies": len(before_anomalies),
            "after_orphan_anomalies": len(after_anomalies),
            "new_agent_c_anomalies": len(new_anomalies),
            "resolved_agent_c_anomalies": len(resolved_anomalies),
            "missing_documents_after": len(missing_after),
            "extra_documents_after": len(extra_after),
        },
        "unexpected_modified_documents": unexpected_modified,
        "missing_expected_corrections": absent_expected,
        "missing_documents_after": missing_after,
        "extra_documents_after": extra_after,
        "new_anomalies": new_anomalies,
        "resolved_anomalies": resolved_anomalies,
        "operations": operation_rows,
        "documents": document_rows,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    save_json(REPORT_FILE, report)

    write_csv(
        DOCS_CSV,
        document_rows,
        [
            "document",
            "expected_modified",
            "actually_modified",
            "status",
            "reason",
        ],
    )

    write_csv(
        OPS_CSV,
        operation_rows,
        [
            "candidate_id",
            "document",
            "action",
            "status",
            "reason",
        ],
    )

    write_csv(
        NEW_ANOMALIES_CSV,
        new_anomalies,
        [
            "document",
            "type",
            "relation_id",
            "endpoint",
        ],
    )

    print("=" * 100)
    print("TRACE / SGCE - AGENT C DIFFERENTIAL POST-VALIDATION")
    print("=" * 100)
    print(f"AVANT Agent C                      : {before_dir}")
    print(f"APRES Agent C                      : {AFTER_DIR}")
    print()
    print(f"Documents vÃ©rifiÃ©s                 : {len(common)}")
    print(f"PASS                               : {docs_pass}")
    print(f"FAIL                               : {docs_fail}")
    print()
    print(f"Documents attendus modifiÃ©s        : {len(expected_modified)}")
    print(f"Documents rÃ©ellement modifiÃ©s      : {len(actually_modified)}")
    print(f"Modifications inattendues          : {len(unexpected_modified)}")
    print(f"Corrections attendues absentes     : {len(absent_expected)}")
    print()
    print(f"OpÃ©rations appliquÃ©es vÃ©rifiÃ©es    : {len(operations)}")
    print(f"OpÃ©rations PASS                    : {operation_pass}")
    print(f"OpÃ©rations FAIL                    : {operation_fail}")
    print()
    print(f"Anomalies orphelines AVANT         : {len(before_anomalies)}")
    print(f"Anomalies orphelines APRES         : {len(after_anomalies)}")
    print(f"Nouvelles anomalies Agent C        : {len(new_anomalies)}")
    print(f"Anomalies rÃ©solues Agent C         : {len(resolved_anomalies)}")
    print()
    print(f"Docs manquants APRES               : {len(missing_after)}")
    print(f"Docs supplÃ©mentaires APRES         : {len(extra_after)}")
    print()
    print(
        f"STATUT FINAL AGENT C               : "
        f"{'PASS' if final_pass else 'FAIL'}"
    )
    print()
    print(f"Rapport JSON                       : {REPORT_FILE}")
    print(f"Rapport documents CSV              : {DOCS_CSV}")
    print(f"Rapport opÃ©rations CSV             : {OPS_CSV}")
    print(f"Nouvelles anomalies CSV            : {NEW_ANOMALIES_CSV}")
    print()
    print("Aucune donnÃ©e clinique n'a Ã©tÃ© modifiÃ©e par ce post-validateur.")


if __name__ == "__main__":
    main()

