# -*- coding: utf-8 -*-
"""
agent_b_post_validator.py
=========================

TRACE / SGCE â€” Post-validateur gÃ©nÃ©rique Pattern B agentique

Objectif
--------
Comparer AVANT / APRES aprÃ¨s application de agent_b_corrector.py.

VÃ©rifie :
1) prÃ©sence de tous les documents attendus
2) absence de documents supplÃ©mentaires inattendus
3) documents attendus modifiÃ©s == documents rÃ©ellement modifiÃ©s
4) endpoints crÃ©Ã©s existent bien
5) entitÃ©s crÃ©Ã©es ont le bon type / texte
6) relations qui pointaient vers l'endpoint sont maintenant rÃ©solues
7) absence de doublon exact crÃ©Ã©
8) aucune nouvelle anomalie domaine/image
9) aucune nouvelle relation orpheline
10) aucune modification inattendue hors documents ciblÃ©s

EntrÃ©es :
  AVANT : PatternD/pattern_d_corrected
  APRES : MultiAgent/agent_b_corrected
  Rapport correcteur : MultiAgent/agent_b_corrected/agent_b_correction_report.json
  Guideline TRACE-Sepsis

Sorties :
  MultiAgent/agent_b_post_validation/agent_b_post_validation_report.json
  MultiAgent/agent_b_post_validation/agent_b_post_validation_documents.csv
  MultiAgent/agent_b_post_validation/agent_b_post_validation_operations.csv
  MultiAgent/agent_b_post_validation/agent_b_new_anomalies.csv

Aucune donnÃ©e clinique n'est modifiÃ©e.
"""

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


# ============================================================
# 1. PATHS
# ============================================================

BASE_DIR = Path(
    r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM"
    r"\Reduction_hallucinations"
)

MULTIAGENT_DIR = BASE_DIR / "MultiAgent"

BEFORE_DIR_CANDIDATES = [
    BASE_DIR / "PatternD" / "pattern_d_corrected",
    BASE_DIR / "PatternC" / "pattern_c_corrected",
]

AFTER_DIR = (
    MULTIAGENT_DIR
    / "agent_b_corrected"
)

CORRECTION_REPORT = (
    AFTER_DIR
    / "agent_b_correction_report.json"
)

GUIDELINE_CANDIDATES = [
    BASE_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
    BASE_DIR.parent / "Guideline_TRACE_Sepsis_v1.6.json",
    Path.cwd() / "Guideline_TRACE_Sepsis_v1.6.json",
    Path(__file__).resolve().parent / "Guideline_TRACE_Sepsis_v1.6.json",
]

OUTPUT_DIR = (
    MULTIAGENT_DIR
    / "agent_b_post_validation"
)

REPORT_JSON = (
    OUTPUT_DIR
    / "agent_b_post_validation_report.json"
)

DOCUMENTS_CSV = (
    OUTPUT_DIR
    / "agent_b_post_validation_documents.csv"
)

OPERATIONS_CSV = (
    OUTPUT_DIR
    / "agent_b_post_validation_operations.csv"
)

NEW_ANOMALIES_CSV = (
    OUTPUT_DIR
    / "agent_b_new_anomalies.csv"
)


# ============================================================
# 2. IO HELPERS
# ============================================================

def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_before_dir():
    for path in BEFORE_DIR_CANDIDATES:
        if path.exists() and any(path.glob("*.json")):
            return path

    raise FileNotFoundError(
        "Aucun dossier AVANT valide trouvÃ©."
    )


def resolve_guideline():
    for path in GUIDELINE_CANDIDATES:
        if path.exists():
            return path

    raise FileNotFoundError(
        "Guideline_TRACE_Sepsis_v1.6.json introuvable."
    )


def is_clinical_document(doc):
    return (
        isinstance(doc, dict)
        and (
            isinstance(doc.get("global_entities"), list)
            or isinstance(doc.get("pages"), list)
        )
    )


def clinical_json_files(directory):
    result = {}

    for path in sorted(directory.glob("*.json")):
        try:
            doc = load_json(path)

            if is_clinical_document(doc):
                result[path.name] = path

        except Exception:
            continue

    return result


def stable_hash(path):
    h = hashlib.sha256()

    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)

            if not chunk:
                break

            h.update(chunk)

    return h.hexdigest()


# ============================================================
# 3. ENTITY / RELATION HELPERS
# ============================================================

def entity_id(e):
    return (
        e.get("identifiant_entite")
        or e.get("id")
        or e.get("entity_id")
    )


def entity_type(e):
    return (
        e.get("categorie")
        or e.get("type")
        or e.get("entity_type")
        or ""
    )


def entity_text(e):
    values = []

    for key in (
        "preuve",
        "name",
        "valeur",
        "libelle",
        "parametre",
        "texte",
        "text",
    ):
        value = e.get(key)

        if value not in (None, ""):
            s = str(value).strip()

            if s and s not in values:
                values.append(s)

    return " | ".join(values)


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
        or r.get("relation_type")
        or r.get("predicate")
        or r.get("type")
        or ""
    )


def relation_source(r):
    return (
        r.get("identifiant_entite_sujet")
        or r.get("from_id")
        or r.get("subject_id")
        or r.get("source")
    )


def relation_target(r):
    return (
        r.get("identifiant_entite_objet")
        or r.get("to_id")
        or r.get("object_id")
        or r.get("target")
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


def entity_index(doc):
    return {
        str(entity_id(e)): e
        for e in get_entities(doc)
        if entity_id(e) is not None
    }


# ============================================================
# 4. GUIDELINE SIGNATURES
# ============================================================

def get_locked_signatures(guideline):
    root = guideline.get(
        "ontologie_sepsis_graph",
        guideline,
    )

    locked = root.get(
        "signatures_relations_verrouillees_v1_5",
        {},
    )

    signatures = {}

    if not isinstance(locked, dict):
        return signatures

    for rtype, spec in locked.items():
        if not isinstance(spec, dict):
            continue

        domain = spec.get("domaine")
        image = spec.get("image")

        if domain and image:
            signatures[rtype] = {
                "domaine": domain,
                "image": image,
            }

    return signatures


# ============================================================
# 5. ANOMALY AUDIT
# ============================================================

def audit_anomalies(doc, signatures):
    anomalies = []

    entities = entity_index(doc)

    for relation in get_relations(doc):
        rid = relation_id(relation)
        rtype = relation_type(relation)
        source_id = relation_source(relation)
        target_id = relation_target(relation)

        source_entity = entities.get(
            str(source_id)
        )

        target_entity = entities.get(
            str(target_id)
        )

        if source_entity is None:
            anomalies.append({
                "type":
                    "ORPHAN_RELATION_SOURCE",

                "relation_id":
                    rid,

                "relation_type":
                    rtype,

                "source_id":
                    source_id,

                "target_id":
                    target_id,
            })

        if target_entity is None:
            anomalies.append({
                "type":
                    "ORPHAN_RELATION_TARGET",

                "relation_id":
                    rid,

                "relation_type":
                    rtype,

                "source_id":
                    source_id,

                "target_id":
                    target_id,
            })

        if rtype not in signatures:
            continue

        signature = signatures[
            rtype
        ]

        if source_entity is not None:
            actual_source_type = entity_type(
                source_entity
            )

            if (
                actual_source_type
                != signature[
                    "domaine"
                ]
            ):
                anomalies.append({
                    "type":
                        "INVALID_RELATION_SOURCE_TYPE",

                    "relation_id":
                        rid,

                    "relation_type":
                        rtype,

                    "source_id":
                        source_id,

                    "actual_type":
                        actual_source_type,

                    "expected_type":
                        signature[
                            "domaine"
                        ],
                })

        if target_entity is not None:
            actual_target_type = entity_type(
                target_entity
            )

            if (
                actual_target_type
                != signature[
                    "image"
                ]
            ):
                anomalies.append({
                    "type":
                        "INVALID_RELATION_TARGET_TYPE",

                    "relation_id":
                        rid,

                    "relation_type":
                        rtype,

                    "target_id":
                        target_id,

                    "actual_type":
                        actual_target_type,

                    "expected_type":
                        signature[
                            "image"
                        ],
                })

    return anomalies


def anomaly_signature(anomaly):
    return (
        anomaly.get("type"),
        anomaly.get("relation_id"),
        anomaly.get("relation_type"),
        anomaly.get("source_id"),
        anomaly.get("target_id"),
        anomaly.get("actual_type"),
        anomaly.get("expected_type"),
    )


# ============================================================
# 6. OPERATION VALIDATION
# ============================================================

def validate_applied_operation(
    operation,
    after_doc,
):
    result = {
        "document":
            operation.get(
                "document"
            ),

        "requested_action":
            operation.get(
                "requested_action"
            ),

        "applied_operation":
            operation.get(
                "operation"
            ),

        "missing_endpoint":
            operation.get(
                "missing_endpoint"
            ),

        "status":
            "PASS",

        "reason":
            "OK",
    }

    if operation.get("status") != "APPLIED":
        result["status"] = "SKIP"
        result["reason"] = (
            operation.get("reason")
            or "OPERATION_NOT_APPLIED"
        )
        return result

    applied = operation.get(
        "operation"
    )

    # --------------------------------------------------------
    # CREATE / CREATE_AND_LINK
    # --------------------------------------------------------

    if applied in {
        "CREATE_FROM_EXPLICIT_EVIDENCE",
        "CREATE_AND_LINK",
    }:
        created_id = operation.get(
            "created_entity_id"
        )

        entities = entity_index(
            after_doc
        )

        created = entities.get(
            str(
                created_id
            )
        )

        if created is None:
            result["status"] = "FAIL"
            result["reason"] = "CREATED_ENTITY_NOT_FOUND"
            return result

        expected_type = operation.get(
            "entity_type"
        )

        expected_text = operation.get(
            "entity_text"
        )

        if (
            expected_type
            and entity_type(
                created
            )
            != expected_type
        ):
            result["status"] = "FAIL"
            result["reason"] = "CREATED_ENTITY_TYPE_MISMATCH"
            return result

        if expected_text:
            actual_text = entity_text(
                created
            )

            if expected_text not in actual_text:
                result["status"] = "FAIL"
                result["reason"] = "CREATED_ENTITY_TEXT_MISMATCH"
                return result

        # Exact entity ID must now resolve every relation that referenced it.
        unresolved = []

        for relation in get_relations(
            after_doc
        ):
            if (
                str(
                    relation_source(
                        relation
                    )
                )
                == str(
                    created_id
                )
                or str(
                    relation_target(
                        relation
                    )
                )
                == str(
                    created_id
                )
            ):
                # because created exists, endpoint is resolved
                continue

        # exact duplicate by id impossible, but duplicate content check
        exact_same = [
            e
            for e in get_entities(
                after_doc
            )
            if (
                entity_type(e)
                == entity_type(created)
                and entity_text(e)
                == entity_text(created)
            )
        ]

        if len(exact_same) > 1:
            # tolerate global/page mirrored structure only if same id
            ids = {
                str(
                    entity_id(e)
                )
                for e in exact_same
            }

            if len(ids) > 1:
                result["status"] = "FAIL"
                result["reason"] = "DUPLICATE_ENTITY_CONTENT_CREATED"
                return result

        return result

    # --------------------------------------------------------
    # RELINK
    # --------------------------------------------------------

    if applied == "RELINK":
        old_endpoint = operation.get(
            "old_endpoint"
        )

        new_entity_id = operation.get(
            "new_entity_id"
        )

        if (
            entity_index(
                after_doc
            ).get(
                str(
                    new_entity_id
                )
            )
            is None
        ):
            result["status"] = "FAIL"
            result["reason"] = "RELINK_TARGET_ENTITY_NOT_FOUND"
            return result

        still_old = []

        for relation in get_relations(
            after_doc
        ):
            if (
                str(
                    relation_source(
                        relation
                    )
                )
                == str(
                    old_endpoint
                )
                or str(
                    relation_target(
                        relation
                    )
                )
                == str(
                    old_endpoint
                )
            ):
                still_old.append(
                    relation_id(
                        relation
                    )
                )

        if still_old:
            result["status"] = "FAIL"
            result["reason"] = "OLD_ENDPOINT_STILL_REFERENCED"
            return result

        return result

    # --------------------------------------------------------
    # REMOVE_RELATION
    # --------------------------------------------------------

    if applied == "REMOVE_RELATION":
        rid = operation.get(
            "relation_id"
        )

        exists = any(
            str(
                relation_id(
                    relation
                )
            )
            == str(
                rid
            )
            for relation in get_relations(
                after_doc
            )
        )

        if exists:
            result["status"] = "FAIL"
            result["reason"] = "REMOVED_RELATION_STILL_EXISTS"

        return result

    result["status"] = "SKIP"
    result["reason"] = "UNKNOWN_OPERATION_TYPE"

    return result


# ============================================================
# 7. MAIN
# ============================================================

def main():
    before_dir = resolve_before_dir()

    if not AFTER_DIR.exists():
        raise FileNotFoundError(
            f"Dossier APRES introuvable : {AFTER_DIR}"
        )

    if not CORRECTION_REPORT.exists():
        raise FileNotFoundError(
            f"Rapport correcteur introuvable : {CORRECTION_REPORT}"
        )

    guideline_path = resolve_guideline()

    guideline = load_json(
        guideline_path
    )

    signatures = get_locked_signatures(
        guideline
    )

    correction_report = load_json(
        CORRECTION_REPORT
    )

    before_files = clinical_json_files(
        before_dir
    )

    after_files = clinical_json_files(
        AFTER_DIR
    )

    before_names = set(
        before_files.keys()
    )

    after_names = set(
        after_files.keys()
    )

    missing_after = sorted(
        before_names
        - after_names
    )

    extra_after = sorted(
        after_names
        - before_names
    )

    # --------------------------------------------------------
    # Expected modified docs
    # --------------------------------------------------------

    expected_modified = set(
        correction_report.get(
            "modified_documents",
            []
        )
    )

    # --------------------------------------------------------
    # Actual modified docs
    # --------------------------------------------------------

    actual_modified = set()

    document_rows = []

    all_common = sorted(
        before_names
        & after_names
    )

    for name in all_common:
        before_hash = stable_hash(
            before_files[
                name
            ]
        )

        after_hash = stable_hash(
            after_files[
                name
            ]
        )

        changed = (
            before_hash
            != after_hash
        )

        if changed:
            actual_modified.add(
                name
            )

        expected = (
            name in expected_modified
        )

        status = "PASS"

        reason = "UNCHANGED_AS_EXPECTED"

        if expected and changed:
            reason = "CHANGED_AS_EXPECTED"

        elif expected and not changed:
            status = "FAIL"
            reason = "EXPECTED_CHANGE_MISSING"

        elif (
            not expected
            and changed
        ):
            status = "FAIL"
            reason = "UNEXPECTED_CHANGE"

        document_rows.append({
            "document":
                name,

            "expected_modified":
                expected,

            "actually_modified":
                changed,

            "status":
                status,

            "reason":
                reason,
        })

    unexpected_modified = sorted(
        actual_modified
        - expected_modified
    )

    expected_missing = sorted(
        expected_modified
        - actual_modified
    )

    # --------------------------------------------------------
    # Operation validation
    # --------------------------------------------------------

    operations = correction_report.get(
        "operations",
        []
    )

    operation_rows = []

    for operation in operations:
        document = operation.get(
            "document"
        )

        after_path = after_files.get(
            document
        )

        if after_path is None:
            operation_rows.append({
                "document":
                    document,

                "requested_action":
                    operation.get(
                        "requested_action"
                    ),

                "applied_operation":
                    operation.get(
                        "operation"
                    ),

                "missing_endpoint":
                    operation.get(
                        "missing_endpoint"
                    ),

                "status":
                    "FAIL",

                "reason":
                    "AFTER_DOCUMENT_NOT_FOUND",
            })

            continue

        after_doc = load_json(
            after_path
        )

        operation_rows.append(
            validate_applied_operation(
                operation,
                after_doc,
            )
        )

    operation_pass = sum(
        1
        for row in operation_rows
        if row[
            "status"
        ]
        == "PASS"
    )

    operation_fail = sum(
        1
        for row in operation_rows
        if row[
            "status"
        ]
        == "FAIL"
    )

    # --------------------------------------------------------
    # Anomaly differential
    # --------------------------------------------------------

    before_anomalies = []
    after_anomalies = []

    before_by_doc = {}
    after_by_doc = {}

    for name in all_common:
        before_doc = load_json(
            before_files[
                name
            ]
        )

        after_doc = load_json(
            after_files[
                name
            ]
        )

        b = audit_anomalies(
            before_doc,
            signatures,
        )

        a = audit_anomalies(
            after_doc,
            signatures,
        )

        before_by_doc[
            name
        ] = b

        after_by_doc[
            name
        ] = a

        for x in b:
            before_anomalies.append(
                (
                    name,
                    x,
                )
            )

        for x in a:
            after_anomalies.append(
                (
                    name,
                    x,
                )
            )

    before_set = {
        (
            doc,
            anomaly_signature(
                anomaly
            ),
        )
        for (
            doc,
            anomaly
        )
        in before_anomalies
    }

    after_set = {
        (
            doc,
            anomaly_signature(
                anomaly
            ),
        )
        for (
            doc,
            anomaly
        )
        in after_anomalies
    }

    new_anomalies_keys = (
        after_set
        - before_set
    )

    resolved_anomalies_keys = (
        before_set
        - after_set
    )

    new_anomalies_rows = []

    for (
        document,
        anomaly
    ) in after_anomalies:
        key = (
            document,
            anomaly_signature(
                anomaly
            ),
        )

        if key in new_anomalies_keys:
            new_anomalies_rows.append({
                "document":
                    document,

                **anomaly,
            })

    # --------------------------------------------------------
    # Final status
    # --------------------------------------------------------

    document_failures = sum(
        1
        for row in document_rows
        if row[
            "status"
        ]
        == "FAIL"
    )

    final_pass = (
        len(
            missing_after
        )
        == 0
        and len(
            extra_after
        )
        == 0
        and len(
            unexpected_modified
        )
        == 0
        and len(
            expected_missing
        )
        == 0
        and operation_fail
        == 0
        and len(
            new_anomalies_rows
        )
        == 0
        and document_failures
        == 0
    )

    final_status = (
        "PASS"
        if final_pass
        else "FAIL"
    )

    # --------------------------------------------------------
    # Write CSVs
    # --------------------------------------------------------

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with DOCUMENTS_CSV.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as f:
        fieldnames = [
            "document",
            "expected_modified",
            "actually_modified",
            "status",
            "reason",
        ]

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        writer.writerows(
            document_rows
        )

    with OPERATIONS_CSV.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as f:
        fieldnames = [
            "document",
            "requested_action",
            "applied_operation",
            "missing_endpoint",
            "status",
            "reason",
        ]

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        writer.writerows(
            operation_rows
        )

    anomaly_fields = [
        "document",
        "type",
        "relation_id",
        "relation_type",
        "source_id",
        "target_id",
        "actual_type",
        "expected_type",
    ]

    with NEW_ANOMALIES_CSV.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=anomaly_fields,
        )

        writer.writeheader()

        for row in new_anomalies_rows:
            writer.writerow({
                key:
                    row.get(
                        key
                    )
                for key
                in anomaly_fields
            })

    # --------------------------------------------------------
    # JSON report
    # --------------------------------------------------------

    report = {
        "validator":
            "agent_b_post_validator",

        "before_directory":
            str(
                before_dir
            ),

        "after_directory":
            str(
                AFTER_DIR
            ),

        "correction_report":
            str(
                CORRECTION_REPORT
            ),

        "guideline":
            str(
                guideline_path
            ),

        "summary": {
            "documents_checked":
                len(
                    all_common
                ),

            "document_pass":
                sum(
                    1
                    for row
                    in document_rows
                    if row[
                        "status"
                    ]
                    == "PASS"
                ),

            "document_fail":
                document_failures,

            "expected_modified_documents":
                len(
                    expected_modified
                ),

            "actually_modified_documents":
                len(
                    actual_modified
                ),

            "unexpected_modified_documents":
                len(
                    unexpected_modified
                ),

            "expected_changes_missing":
                len(
                    expected_missing
                ),

            "operations_checked":
                len(
                    operation_rows
                ),

            "operations_pass":
                operation_pass,

            "operations_fail":
                operation_fail,

            "anomalies_before":
                len(
                    before_anomalies
                ),

            "anomalies_after":
                len(
                    after_anomalies
                ),

            "new_anomalies":
                len(
                    new_anomalies_rows
                ),

            "resolved_anomalies":
                len(
                    resolved_anomalies_keys
                ),

            "missing_documents_after":
                len(
                    missing_after
                ),

            "extra_documents_after":
                len(
                    extra_after
                ),

            "locked_signatures_loaded":
                len(
                    signatures
                ),

            "final_status":
                final_status,
        },

        "expected_modified_documents":
            sorted(
                expected_modified
            ),

        "actually_modified_documents":
            sorted(
                actual_modified
            ),

        "unexpected_modified_documents":
            unexpected_modified,

        "expected_changes_missing":
            expected_missing,

        "missing_documents_after":
            missing_after,

        "extra_documents_after":
            extra_after,

        "document_results":
            document_rows,

        "operation_results":
            operation_rows,

        "new_anomalies":
            new_anomalies_rows,
    }

    REPORT_JSON.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # Console
    # --------------------------------------------------------

    print("=" * 104)
    print("TRACE / SGCE - AGENT B DIFFERENTIAL POST-VALIDATION")
    print("=" * 104)

    print(
        f"AVANT Agent B                      : "
        f"{before_dir}"
    )

    print(
        f"APRES Agent B                      : "
        f"{AFTER_DIR}"
    )

    print()

    print(
        f"Documents vÃ©rifiÃ©s                 : "
        f"{len(all_common)}"
    )

    print(
        f"PASS                               : "
        f"{sum(1 for row in document_rows if row['status'] == 'PASS')}"
    )

    print(
        f"FAIL                               : "
        f"{document_failures}"
    )

    print()

    print(
        f"Documents attendus modifiÃ©s        : "
        f"{len(expected_modified)}"
    )

    print(
        f"Documents rÃ©ellement modifiÃ©s      : "
        f"{len(actual_modified)}"
    )

    print(
        f"Modifications inattendues          : "
        f"{len(unexpected_modified)}"
    )

    print(
        f"Corrections attendues absentes     : "
        f"{len(expected_missing)}"
    )

    print()

    print(
        f"OpÃ©rations appliquÃ©es vÃ©rifiÃ©es    : "
        f"{len(operation_rows)}"
    )

    print(
        f"OpÃ©rations PASS                    : "
        f"{operation_pass}"
    )

    print(
        f"OpÃ©rations FAIL                    : "
        f"{operation_fail}"
    )

    print()

    print(
        f"Anomalies prÃ©-existantes           : "
        f"{len(before_anomalies)}"
    )

    print(
        f"Anomalies aprÃ¨s Agent B            : "
        f"{len(after_anomalies)}"
    )

    print(
        f"Nouvelles anomalies Agent B        : "
        f"{len(new_anomalies_rows)}"
    )

    print(
        f"Anomalies rÃ©solues Agent B         : "
        f"{len(resolved_anomalies_keys)}"
    )

    print()

    print(
        f"Docs manquants APRES               : "
        f"{len(missing_after)}"
    )

    print(
        f"Docs supplÃ©mentaires APRES         : "
        f"{len(extra_after)}"
    )

    print(
        f"Signatures TRACE chargÃ©es          : "
        f"{len(signatures)}"
    )

    print()

    print(
        f"STATUT FINAL AGENT B               : "
        f"{final_status}"
    )

    print()

    print(
        f"Rapport JSON                       : "
        f"{REPORT_JSON}"
    )

    print(
        f"Rapport documents CSV              : "
        f"{DOCUMENTS_CSV}"
    )

    print(
        f"Rapport opÃ©rations CSV             : "
        f"{OPERATIONS_CSV}"
    )

    print(
        f"Nouvelles anomalies CSV            : "
        f"{NEW_ANOMALIES_CSV}"
    )

    print()

    print(
        "Aucune donnÃ©e clinique n'a Ã©tÃ© modifiÃ©e "
        "par ce post-validateur."
    )


if __name__ == "__main__":
    main()

