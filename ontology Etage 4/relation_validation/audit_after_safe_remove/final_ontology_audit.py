# -*- coding: utf-8 -*-
"""
final_ontology_audit.py
=======================

TRACE / SGCE — Final Ontology Audit

Input:
  MultiAgent/multiagent_safe_final_corrected

Guideline:
  Guideline_TRACE_Sepsis_v1.6.json

Purpose:
- audit the final safe clinical graph
- count residual ontology / structure anomalies
- produce detailed JSON + CSV reports
- DO NOT modify any clinical JSON

Detected anomaly families:
- ORPHAN_RELATION_SOURCE
- ORPHAN_RELATION_TARGET
- INVALID_RELATION_SOURCE_TYPE
- INVALID_RELATION_TARGET_TYPE
- UNAUTHORIZED_RELATION
- DUPLICATE_RELATION
- DUPLICATE_ENTITY_ID
- DUPLICATE_ENTITY_CONTENT

Outputs:
  MultiAgent/final_ontology_audit/final_ontology_audit_report.json
  MultiAgent/final_ontology_audit/final_ontology_anomalies.csv
  MultiAgent/final_ontology_audit/final_ontology_summary_by_type.csv
  MultiAgent/final_ontology_audit/final_ontology_summary_by_relation.csv
  MultiAgent/final_ontology_audit/final_ontology_summary_by_document.csv
"""

import csv
import json
from pathlib import Path
from collections import Counter, defaultdict


# ============================================================
# 1. PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent
RELATION_DIR = ROOT.parent
STAGE4_DIR = RELATION_DIR.parent
REDUCTION_DIR = STAGE4_DIR.parent
PROJECT_DIR = REDUCTION_DIR.parent

INPUT_DIR = RELATION_DIR / "ontology_relation_safe_corrected"

GUIDELINE_CANDIDATES = [
    PROJECT_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
    REDUCTION_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
    Path.cwd() / "Guideline_TRACE_Sepsis_v1.6.json",
]

OUTPUT_DIR = ROOT
REPORT_JSON = OUTPUT_DIR / "final_ontology_audit_report.json"
ANOMALIES_CSV = OUTPUT_DIR / "final_ontology_anomalies.csv"
SUMMARY_TYPE_CSV = OUTPUT_DIR / "final_ontology_summary_by_type.csv"
SUMMARY_RELATION_CSV = OUTPUT_DIR / "final_ontology_summary_by_relation.csv"
SUMMARY_DOCUMENT_CSV = OUTPUT_DIR / "final_ontology_summary_by_document.csv"


# ============================================================
# 2. IO
# ============================================================

def load_json(path):
    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


def resolve_guideline():
    for path in GUIDELINE_CANDIDATES:
        if path.exists():
            return path

    raise FileNotFoundError(
        "Guideline_TRACE_Sepsis_v1.6.json introuvable."
    )


# ============================================================
# 3. ENTITY / RELATION HELPERS
# ============================================================

def entity_id(entity):
    return (
        entity.get(
            "identifiant_entite"
        )
        or entity.get(
            "id"
        )
        or entity.get(
            "entity_id"
        )
    )


def entity_type(entity):
    return (
        entity.get(
            "categorie"
        )
        or entity.get(
            "type"
        )
        or entity.get(
            "entity_type"
        )
        or ""
    )


def entity_text(entity):
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
        value = entity.get(
            key
        )

        if value not in (
            None,
            "",
        ):
            text = str(
                value
            ).strip()

            if (
                text
                and text not in values
            ):
                values.append(
                    text
                )

    return " | ".join(
        values
    )


def relation_id(relation):
    return (
        relation.get(
            "identifiant_relation"
        )
        or relation.get(
            "id"
        )
        or relation.get(
            "relation_id"
        )
    )


def relation_type(relation):
    return (
        relation.get(
            "type_relation"
        )
        or relation.get(
            "relation"
        )
        or relation.get(
            "relation_type"
        )
        or relation.get(
            "predicate"
        )
        or relation.get(
            "type"
        )
        or ""
    )


def relation_source(relation):
    return (
        relation.get(
            "identifiant_entite_sujet"
        )
        or relation.get(
            "from_id"
        )
        or relation.get(
            "subject_id"
        )
        or relation.get(
            "source"
        )
    )


def relation_target(relation):
    return (
        relation.get(
            "identifiant_entite_objet"
        )
        or relation.get(
            "to_id"
        )
        or relation.get(
            "object_id"
        )
        or relation.get(
            "target"
        )
    )


def relation_page(relation):
    return (
        relation.get(
            "page"
        )
        or relation.get(
            "page_number"
        )
        or relation.get(
            "numero_page"
        )
    )


def get_entities(doc):
    if isinstance(
        doc.get(
            "global_entities"
        ),
        list,
    ):
        return doc[
            "global_entities"
        ]

    output = []

    for page in (
        doc.get(
            "pages",
            []
        )
        or []
    ):
        output.extend(
            page.get(
                "entities",
                []
            )
            or []
        )

    return output


def get_relations(doc):
    if isinstance(
        doc.get(
            "global_relations"
        ),
        list,
    ):
        return doc[
            "global_relations"
        ]

    output = []

    for page in (
        doc.get(
            "pages",
            []
        )
        or []
    ):
        output.extend(
            page.get(
                "relations",
                []
            )
            or []
        )

    return output


# ============================================================
# 4. GUIDELINE PARSING
# ============================================================

def load_signatures(
    guideline,
):
    root = guideline.get(
        "ontologie_sepsis_graph",
        guideline,
    )

    candidates = [
        root.get(
            "signatures_relations_verrouillees_v1_5"
        ),
        root.get(
            "signatures_relations"
        ),
        root.get(
            "relations"
        ),
    ]

    signatures = {}

    for block in candidates:
        if not isinstance(
            block,
            dict,
        ):
            continue

        for name, spec in block.items():
            if not isinstance(
                spec,
                dict,
            ):
                continue

            domain = (
                spec.get(
                    "domaine"
                )
                or spec.get(
                    "domain"
                )
                or spec.get(
                    "source_type"
                )
            )

            image = (
                spec.get(
                    "image"
                )
                or spec.get(
                    "range"
                )
                or spec.get(
                    "target_type"
                )
            )

            if domain and image:
                signatures[
                    name
                ] = {
                    "domaine":
                        domain,

                    "image":
                        image,
                }

        if signatures:
            break

    return signatures


# ============================================================
# 5. CLINICAL FILE DISCOVERY
# ============================================================

def clinical_files(
    directory,
):
    result = {}

    for path in sorted(
        directory.glob(
            "*.json"
        )
    ):
        if path.name.endswith(
            "_report.json"
        ):
            continue

        try:
            data = load_json(
                path
            )

            if (
                isinstance(
                    data,
                    dict,
                )
                and any(
                    key in data
                    for key in (
                        "pages",
                        "global_entities",
                        "global_relations",
                    )
                )
            ):
                result[
                    path.name
                ] = data

        except Exception:
            pass

    return result


# ============================================================
# 6. AUDIT
# ============================================================

def audit_document(
    document_name,
    doc,
    signatures,
):
    anomalies = []

    entities = get_entities(
        doc
    )

    relations = get_relations(
        doc
    )

    # --------------------------------------------------------
    # Entity ID index + duplicate IDs
    # --------------------------------------------------------

    entity_groups = defaultdict(
        list
    )

    for entity in entities:
        eid = entity_id(
            entity
        )

        if eid is not None:
            entity_groups[
                str(
                    eid
                )
            ].append(
                entity
            )

    entity_index = {
        eid:
            values[
                0
            ]
        for eid, values in entity_groups.items()
    }

    for eid, values in entity_groups.items():
        if len(
            values
        ) > 1:
            anomalies.append({
                "document":
                    document_name,

                "type":
                    "DUPLICATE_ENTITY_ID",

                "entity_id":
                    eid,

                "entity_type":
                    entity_type(
                        values[
                            0
                        ]
                    ),

                "entity_text":
                    entity_text(
                        values[
                            0
                        ]
                    ),

                "relation_id":
                    None,

                "relation_type":
                    None,

                "source_id":
                    None,

                "target_id":
                    None,

                "actual_type":
                    None,

                "expected_type":
                    None,

                "page":
                    None,

                "details":
                    f"{len(values)} occurrences du même identifiant",
            })

    # --------------------------------------------------------
    # Duplicate entity content
    # --------------------------------------------------------

    content_groups = defaultdict(
        list
    )

    for entity in entities:
        key = (
            entity_type(
                entity
            ),
            entity_text(
                entity
            ).strip(),
        )

        if (
            key[
                0
            ]
            and key[
                1
            ]
        ):
            content_groups[
                key
            ].append(
                entity
            )

    for (
        etype,
        etext,
    ), values in content_groups.items():
        ids = {
            str(
                entity_id(
                    e
                )
            )
            for e in values
            if entity_id(
                e
            )
            is not None
        }

        if len(
            ids
        ) > 1:
            anomalies.append({
                "document":
                    document_name,

                "type":
                    "DUPLICATE_ENTITY_CONTENT",

                "entity_id":
                    ",".join(
                        sorted(
                            ids
                        )
                    ),

                "entity_type":
                    etype,

                "entity_text":
                    etext,

                "relation_id":
                    None,

                "relation_type":
                    None,

                "source_id":
                    None,

                "target_id":
                    None,

                "actual_type":
                    None,

                "expected_type":
                    None,

                "page":
                    None,

                "details":
                    "Même type + même contenu avec plusieurs IDs",
            })

    # --------------------------------------------------------
    # Relation duplicate key
    # --------------------------------------------------------

    relation_groups = defaultdict(
        list
    )

    for relation in relations:
        key = (
            relation_type(
                relation
            ),
            str(
                relation_source(
                    relation
                )
            ),
            str(
                relation_target(
                    relation
                )
            ),
        )

        relation_groups[
            key
        ].append(
            relation
        )

    for (
        rtype,
        source_id,
        target_id,
    ), values in relation_groups.items():
        if len(
            values
        ) > 1:
            anomalies.append({
                "document":
                    document_name,

                "type":
                    "DUPLICATE_RELATION",

                "entity_id":
                    None,

                "entity_type":
                    None,

                "entity_text":
                    None,

                "relation_id":
                    ",".join(
                        str(
                            relation_id(
                                r
                            )
                        )
                        for r in values
                    ),

                "relation_type":
                    rtype,

                "source_id":
                    source_id,

                "target_id":
                    target_id,

                "actual_type":
                    None,

                "expected_type":
                    None,

                "page":
                    relation_page(
                        values[
                            0
                        ]
                    ),

                "details":
                    f"{len(values)} relations identiques",
            })

    # --------------------------------------------------------
    # Relation structural / ontology validation
    # --------------------------------------------------------

    for relation in relations:
        rid = relation_id(
            relation
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

        page = relation_page(
            relation
        )

        source = entity_index.get(
            str(
                source_id
            )
        )

        target = entity_index.get(
            str(
                target_id
            )
        )

        # orphan source
        if source is None:
            anomalies.append({
                "document":
                    document_name,

                "type":
                    "ORPHAN_RELATION_SOURCE",

                "entity_id":
                    None,

                "entity_type":
                    None,

                "entity_text":
                    None,

                "relation_id":
                    rid,

                "relation_type":
                    rtype,

                "source_id":
                    source_id,

                "target_id":
                    target_id,

                "actual_type":
                    None,

                "expected_type":
                    None,

                "page":
                    page,

                "details":
                    "Source absente du graphe",
            })

        # orphan target
        if target is None:
            anomalies.append({
                "document":
                    document_name,

                "type":
                    "ORPHAN_RELATION_TARGET",

                "entity_id":
                    None,

                "entity_type":
                    None,

                "entity_text":
                    None,

                "relation_id":
                    rid,

                "relation_type":
                    rtype,

                "source_id":
                    source_id,

                "target_id":
                    target_id,

                "actual_type":
                    None,

                "expected_type":
                    None,

                "page":
                    page,

                "details":
                    "Cible absente du graphe",
            })

        # unauthorized relation
        if (
            rtype
            and rtype not in signatures
        ):
            anomalies.append({
                "document":
                    document_name,

                "type":
                    "UNAUTHORIZED_RELATION",

                "entity_id":
                    None,

                "entity_type":
                    None,

                "entity_text":
                    None,

                "relation_id":
                    rid,

                "relation_type":
                    rtype,

                "source_id":
                    source_id,

                "target_id":
                    target_id,

                "actual_type":
                    None,

                "expected_type":
                    None,

                "page":
                    page,

                "details":
                    "Relation absente des signatures TRACE chargées",
            })

            continue

        signature = signatures.get(
            rtype
        )

        if not signature:
            continue

        # source mismatch
        if source is not None:
            actual_source_type = entity_type(
                source
            )

            if (
                actual_source_type
                != signature[
                    "domaine"
                ]
            ):
                anomalies.append({
                    "document":
                        document_name,

                    "type":
                        "INVALID_RELATION_SOURCE_TYPE",

                    "entity_id":
                        source_id,

                    "entity_type":
                        actual_source_type,

                    "entity_text":
                        entity_text(
                            source
                        ),

                    "relation_id":
                        rid,

                    "relation_type":
                        rtype,

                    "source_id":
                        source_id,

                    "target_id":
                        target_id,

                    "actual_type":
                        actual_source_type,

                    "expected_type":
                        signature[
                            "domaine"
                        ],

                    "page":
                        page,

                    "details":
                        "Le type source ne respecte pas le domaine TRACE",
                })

        # target mismatch
        if target is not None:
            actual_target_type = entity_type(
                target
            )

            if (
                actual_target_type
                != signature[
                    "image"
                ]
            ):
                anomalies.append({
                    "document":
                        document_name,

                    "type":
                        "INVALID_RELATION_TARGET_TYPE",

                    "entity_id":
                        target_id,

                    "entity_type":
                        actual_target_type,

                    "entity_text":
                        entity_text(
                            target
                        ),

                    "relation_id":
                        rid,

                    "relation_type":
                        rtype,

                    "source_id":
                        source_id,

                    "target_id":
                        target_id,

                    "actual_type":
                        actual_target_type,

                    "expected_type":
                        signature[
                            "image"
                        ],

                    "page":
                        page,

                    "details":
                        "Le type cible ne respecte pas l'image TRACE",
                })

    return anomalies


# ============================================================
# 7. CSV HELPERS
# ============================================================

def write_csv(
    path,
    rows,
    fieldnames,
):
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

        writer.writerows(
            rows
        )


# ============================================================
# 8. MAIN
# ============================================================

def main():
    if not INPUT_DIR.exists():
        raise FileNotFoundError(
            f"Sortie clinique finale introuvable : {INPUT_DIR}"
        )

    guideline_path = resolve_guideline()

    guideline = load_json(
        guideline_path
    )

    signatures = load_signatures(
        guideline
    )

    docs = clinical_files(
        INPUT_DIR
    )

    all_anomalies = []

    entity_count = 0
    relation_count = 0

    for document_name, doc in docs.items():
        entity_count += len(
            get_entities(
                doc
            )
        )

        relation_count += len(
            get_relations(
                doc
            )
        )

        all_anomalies.extend(
            audit_document(
                document_name,
                doc,
                signatures,
            )
        )

    # --------------------------------------------------------
    # Summaries
    # --------------------------------------------------------

    by_type = Counter(
        anomaly.get(
            "type"
        )
        for anomaly in all_anomalies
    )

    by_relation = Counter(
        anomaly.get(
            "relation_type"
        )
        for anomaly in all_anomalies
        if anomaly.get(
            "relation_type"
        )
    )

    by_document = Counter(
        anomaly.get(
            "document"
        )
        for anomaly in all_anomalies
    )

    # --------------------------------------------------------
    # Output directory
    # --------------------------------------------------------

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # detailed CSV
    anomaly_fields = [
        "document",
        "type",
        "entity_id",
        "entity_type",
        "entity_text",
        "relation_id",
        "relation_type",
        "source_id",
        "target_id",
        "actual_type",
        "expected_type",
        "page",
        "details",
    ]

    write_csv(
        ANOMALIES_CSV,
        all_anomalies,
        anomaly_fields,
    )

    # by type
    write_csv(
        SUMMARY_TYPE_CSV,
        [
            {
                "anomaly_type":
                    key,

                "count":
                    value,
            }
            for key, value in by_type.most_common()
        ],
        [
            "anomaly_type",
            "count",
        ],
    )

    # by relation
    write_csv(
        SUMMARY_RELATION_CSV,
        [
            {
                "relation_type":
                    key,

                "count":
                    value,
            }
            for key, value in by_relation.most_common()
        ],
        [
            "relation_type",
            "count",
        ],
    )

    # by document
    write_csv(
        SUMMARY_DOCUMENT_CSV,
        [
            {
                "document":
                    key,

                "count":
                    value,
            }
            for key, value in by_document.most_common()
        ],
        [
            "document",
            "count",
        ],
    )

    # --------------------------------------------------------
    # JSON report
    # --------------------------------------------------------

    report = {
        "audit":
            "final_ontology_audit",

        "input_directory":
            str(
                INPUT_DIR
            ),

        "guideline":
            str(
                guideline_path
            ),

        "summary": {
            "documents":
                len(
                    docs
                ),

            "entities":
                entity_count,

            "relations":
                relation_count,

            "trace_signatures_loaded":
                len(
                    signatures
                ),

            "total_anomalies":
                len(
                    all_anomalies
                ),

            "anomalies_by_type":
                dict(
                    by_type
                ),

            "anomalies_by_relation":
                dict(
                    by_relation
                ),
        },

        "anomalies":
            all_anomalies,
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
    print("TRACE / SGCE - FINAL ONTOLOGY AUDIT")
    print("=" * 104)

    print(
        f"Entrée clinique                    : {INPUT_DIR}"
    )

    print(
        f"Guideline                          : {guideline_path}"
    )

    print()

    print(
        f"Documents cliniques                : {len(docs)}"
    )

    print(
        f"Entités analysées                  : {entity_count}"
    )

    print(
        f"Relations analysées                : {relation_count}"
    )

    print(
        f"Signatures TRACE chargées          : {len(signatures)}"
    )

    print()

    print(
        f"Anomalies résiduelles totales      : {len(all_anomalies)}"
    )

    print()

    print("ANOMALIES PAR TYPE")
    print("-" * 104)

    if by_type:
        for name, count in by_type.most_common():
            print(
                f"{str(name):<52}: {count}"
            )
    else:
        print(
            "Aucune anomalie détectée."
        )

    print()

    print("RELATIONS LES PLUS CONCERNEES")
    print("-" * 104)

    for name, count in by_relation.most_common(
        20
    ):
        print(
            f"{str(name):<52}: {count}"
        )

    print()

    print(
        f"Rapport JSON                       : {REPORT_JSON}"
    )

    print(
        f"CSV anomalies                      : {ANOMALIES_CSV}"
    )

    print(
        f"CSV résumé par type                : {SUMMARY_TYPE_CSV}"
    )

    print(
        f"CSV résumé par relation            : {SUMMARY_RELATION_CSV}"
    )

    print(
        f"CSV résumé par document            : {SUMMARY_DOCUMENT_CSV}"
    )

    print()

    print(
        "Aucun JSON clinique n'a été modifié."
    )


if __name__ == "__main__":
    main()
