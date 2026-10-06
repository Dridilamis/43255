# -*- coding: utf-8 -*-

"""
semantic_factual_post_validator.py
==================================

TRACE / SGCE - SEMANTIC FACTUAL POST-VALIDATION V1

OBJECTIF
--------
Vérifier après semantic_factual_safe_corrector.py que :

1. tous les documents sources existent après correction ;
2. aucun document clinique supplémentaire n'a été créé ;
3. chaque SAFE_REMOVE a réellement disparu ;
4. aucune entité n'a été modifiée ;
5. aucune relation non autorisée n'a été supprimée ;
6. aucune nouvelle relation n'a été ajoutée ;
7. les suppressions correspondent au rapport du correcteur.

STATUT FINAL
------------
PASS
    toutes les vérifications passent.

FAIL
    au moins une anomalie est détectée.

Ce script ne modifie aucune donnée clinique.
"""

import json
from pathlib import Path
from collections import Counter


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent
STAGE3_DIR = ROOT.parent
REDUCTION_DIR = STAGE3_DIR.parent
PROJECT_DIR = REDUCTION_DIR.parent

# Entrée clinique officielle : sortie validée de Root Cause.
SOURCE_DIR = STAGE3_DIR / "root_cause" / "root_cause_entity_safe_corrected"

# Textes bruts produits par Mistral, conservés à la racine du projet OCR vers LLM.
TEXT_DIR = PROJECT_DIR / "Sortie_Textes_Brut_MistralSmall4"

OUTPUT_DIR = ROOT / "semantic_factual_safe_corrected"
CORRECTION_REPORT = OUTPUT_DIR / "semantic_factual_correction_report.json"
POST_DIR = ROOT / "post_validation"
POST_REPORT = POST_DIR / "semantic_factual_post_validation_report.json"

# ============================================================
# JSON
# ============================================================

def load_json(path):

    with Path(path).open(
        "r",
        encoding="utf-8",
    ) as f:

        return json.load(f)


def save_json(path, obj):

    path = Path(path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            obj,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


# ============================================================
# CLINICAL FILE
# ============================================================

def is_clinical(path):

    if path.name.endswith(
        "_report.json"
    ):
        return False

    try:
        doc = load_json(
            path
        )

    except Exception:
        return False

    return (
        isinstance(doc, dict)
        and any(
            key in doc
            for key in (
                "pages",
                "global_entities",
                "global_relations",
            )
        )
    )


def clinical_files(directory):

    result = {}

    directory = Path(
        directory
    )

    if not directory.exists():
        return result

    for path in sorted(
        directory.glob(
            "*.json"
        )
    ):

        if is_clinical(
            path
        ):

            result[
                path.name
            ] = path

    return result


# ============================================================
# CANONICAL JSON
# ============================================================

def canonical(value):

    """
    Sérialisation déterministe utilisée pour comparer
    les structures JSON.
    """

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
    )


# ============================================================
# ENTITIES
# ============================================================

def entity_occurrences(doc):

    """
    Capture toutes les occurrences physiques d'entités
    avec leur emplacement.

    Cela permet de vérifier qu'aucune entité n'a changé.
    """

    result = []

    global_entities = doc.get(
        "global_entities"
    )

    if isinstance(
        global_entities,
        list,
    ):

        for index, entity in enumerate(
            global_entities
        ):

            result.append({

                "location":
                    "global_entities",

                "page":
                    None,

                "index":
                    index,

                "entity":
                    entity,
            })

    for page_index, page in enumerate(
        doc.get(
            "pages",
            [],
        )
        or []
    ):

        if not isinstance(
            page,
            dict,
        ):
            continue

        entities = page.get(
            "entities"
        )

        if not isinstance(
            entities,
            list,
        ):
            continue

        page_number = (
            page.get("page")
            or page.get("page_number")
            or page.get("numero_page")
            or page_index + 1
        )

        for index, entity in enumerate(
            entities
        ):

            result.append({

                "location":
                    "page",

                "page":
                    page_number,

                "index":
                    index,

                "entity":
                    entity,
            })

    return result


# ============================================================
# RELATIONS
# ============================================================

def relation_id(relation):

    if not isinstance(
        relation,
        dict,
    ):
        return None

    return (
        relation.get("identifiant_relation")
        or relation.get("relation_id")
        or relation.get("id")
    )


def relation_type(relation):

    if not isinstance(
        relation,
        dict,
    ):
        return ""

    return (
        relation.get("relation")
        or relation.get("relation_name")
        or relation.get("relation_type")
        or relation.get("type")
        or relation.get("predicate")
        or ""
    )


def relation_source(relation):

    if not isinstance(
        relation,
        dict,
    ):
        return None

    return (
        relation.get("source")
        or relation.get("source_id")
        or relation.get("sujet")
        or relation.get("subject")
        or relation.get("from")
    )


def relation_target(relation):

    if not isinstance(
        relation,
        dict,
    ):
        return None

    return (
        relation.get("target")
        or relation.get("target_id")
        or relation.get("objet")
        or relation.get("object")
        or relation.get("to")
    )


def relation_occurrences(doc):

    result = []

    global_relations = doc.get(
        "global_relations"
    )

    if isinstance(
        global_relations,
        list,
    ):

        for index, relation in enumerate(
            global_relations
        ):

            result.append({

                "location":
                    "global_relations",

                "page":
                    None,

                "index":
                    index,

                "relation":
                    relation,
            })

    for page_index, page in enumerate(
        doc.get(
            "pages",
            [],
        )
        or []
    ):

        if not isinstance(
            page,
            dict,
        ):
            continue

        relations = page.get(
            "relations"
        )

        if not isinstance(
            relations,
            list,
        ):
            continue

        page_number = (
            page.get("page")
            or page.get("page_number")
            or page.get("numero_page")
            or page_index + 1
        )

        for index, relation in enumerate(
            relations
        ):

            result.append({

                "location":
                    "page",

                "page":
                    page_number,

                "index":
                    index,

                "relation":
                    relation,
            })

    return result


# ============================================================
# RELATION LOGICAL KEY
# ============================================================

def relation_key(relation):

    rid = relation_id(
        relation
    )

    if rid not in (
        None,
        "",
    ):

        return (
            "ID",
            str(
                rid
            ),
        )

    return (

        "SIGNATURE",

        str(
            relation_type(
                relation
            )
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


# ============================================================
# COUNTERS
# ============================================================

def relation_counter(doc):

    """
    Compte les occurrences physiques par clé logique.
    """

    counter = Counter()

    for occurrence in relation_occurrences(
        doc
    ):

        key = relation_key(
            occurrence[
                "relation"
            ]
        )

        counter[
            key
        ] += 1

    return counter


# ============================================================
# NON-RELATION STRUCTURE
# ============================================================

def document_without_relations(doc):

    """
    Copie logique du document en retirant uniquement
    les listes de relations.

    Si le résultat BEFORE != AFTER, cela signifie qu'autre
    chose qu'une relation a été modifié.
    """

    clone = json.loads(
        json.dumps(
            doc,
            ensure_ascii=False,
        )
    )

    if "global_relations" in clone:

        clone[
            "global_relations"
        ] = []

    for page in clone.get(
        "pages",
        [],
    ) or []:

        if (
            isinstance(
                page,
                dict,
            )
            and "relations" in page
        ):

            page[
                "relations"
            ] = []

    return clone


# ============================================================
# MAIN
# ============================================================

def main():

    if not SOURCE_DIR.exists():

        raise FileNotFoundError(
            f"Source BEFORE introuvable : "
            f"{SOURCE_DIR}"
        )

    if not OUTPUT_DIR.exists():

        raise FileNotFoundError(
            f"Sortie AFTER introuvable : "
            f"{OUTPUT_DIR}"
        )

    if not CORRECTION_REPORT.exists():

        raise FileNotFoundError(
            f"Rapport correcteur introuvable : "
            f"{CORRECTION_REPORT}"
        )

    before_files = clinical_files(
        SOURCE_DIR
    )

    after_files = clinical_files(
        OUTPUT_DIR
    )

    correction_report = load_json(
        CORRECTION_REPORT
    )

    applied_operations = [

        operation
        for operation in correction_report.get(
            "operations",
            [],
        )

        if operation.get(
            "status"
        )
        == "APPLIED"
    ]

    # ========================================================
    # FILE SET
    # ========================================================

    before_names = set(
        before_files
    )

    after_names = set(
        after_files
    )

    missing_documents = sorted(
        before_names
        - after_names
    )

    extra_documents = sorted(
        after_names
        - before_names
    )

    # ========================================================
    # EXPECTED REMOVALS
    # ========================================================

    expected_by_document = {}

    for operation in applied_operations:

        document = str(
            operation.get(
                "document"
            )
        )

        expected_by_document.setdefault(
            document,
            []
        ).append(
            operation
        )

    # ========================================================
    # VALIDATION
    # ========================================================

    unexpected_non_relation_changes = []

    unexpected_relation_removals = []

    unexpected_relation_additions = []

    expected_removal_failures = []

    verified_operations = []

    documents_with_expected_changes = set()

    # ========================================================
    # DOCUMENT BY DOCUMENT
    # ========================================================

    for name in sorted(
        before_names
        & after_names
    ):

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

        # ----------------------------------------------------
        # VERIFY EVERYTHING EXCEPT RELATIONS IS IDENTICAL
        # ----------------------------------------------------

        before_non_rel = document_without_relations(
            before_doc
        )

        after_non_rel = document_without_relations(
            after_doc
        )

        if canonical(
            before_non_rel
        ) != canonical(
            after_non_rel
        ):

            unexpected_non_relation_changes.append({

                "document":
                    name,

                "error":
                    "NON_RELATION_DATA_CHANGED",
            })

        # ----------------------------------------------------
        # RELATION COUNTS
        # ----------------------------------------------------

        before_counter = relation_counter(
            before_doc
        )

        after_counter = relation_counter(
            after_doc
        )

        removed_counter = (
            before_counter
            - after_counter
        )

        added_counter = (
            after_counter
            - before_counter
        )

        # ----------------------------------------------------
        # EXPECTED KEYS FOR DOCUMENT
        # ----------------------------------------------------

        operations = expected_by_document.get(
            name,
            [],
        )

        expected_keys = Counter()

        for operation in operations:

            rid = operation.get(
                "relation_id"
            )

            if rid not in (
                None,
                "",
            ):

                key = (
                    "ID",
                    str(
                        rid
                    ),
                )

            else:

                key = (

                    "SIGNATURE",

                    str(
                        operation.get(
                            "relation_type"
                        )
                    ),

                    str(
                        operation.get(
                            "source_id"
                        )
                    ),

                    str(
                        operation.get(
                            "target_id"
                        )
                    ),
                )

            expected_physical = int(
                operation.get(
                    "physical_occurrences_removed",
                    0,
                )
                or 0
            )

            expected_keys[
                key
            ] += expected_physical

        # ----------------------------------------------------
        # VERIFY EXPECTED REMOVALS
        # ----------------------------------------------------

        for key, expected_count in (
            expected_keys.items()
        ):

            actual_removed = removed_counter.get(
                key,
                0,
            )

            status = (
                "PASS"
                if actual_removed
                == expected_count
                else "FAIL"
            )

            verified_operations.append({

                "document":
                    name,

                "relation_key":
                    list(
                        key
                    ),

                "expected_physical_removals":
                    expected_count,

                "actual_physical_removals":
                    actual_removed,

                "status":
                    status,
            })

            if status == "FAIL":

                expected_removal_failures.append({

                    "document":
                        name,

                    "relation_key":
                        list(
                            key
                        ),

                    "expected":
                        expected_count,

                    "actual":
                        actual_removed,
                })

            else:

                documents_with_expected_changes.add(
                    name
                )

        # ----------------------------------------------------
        # UNEXPECTED REMOVALS
        # ----------------------------------------------------

        for key, count in (
            removed_counter.items()
        ):

            allowed = expected_keys.get(
                key,
                0,
            )

            if count > allowed:

                unexpected_relation_removals.append({

                    "document":
                        name,

                    "relation_key":
                        list(
                            key
                        ),

                    "removed":
                        count,

                    "allowed":
                        allowed,

                    "unexpected":
                        count - allowed,
                })

        # ----------------------------------------------------
        # NO ADDITION IS EVER ALLOWED
        # ----------------------------------------------------

        for key, count in (
            added_counter.items()
        ):

            if count > 0:

                unexpected_relation_additions.append({

                    "document":
                        name,

                    "relation_key":
                        list(
                            key
                        ),

                    "added":
                        count,
                })

    # ========================================================
    # FINAL STATUS
    # ========================================================

    operation_failures = sum(
        1
        for operation in verified_operations
        if operation.get(
            "status"
        )
        == "FAIL"
    )

    fail_conditions = [

        bool(
            missing_documents
        ),

        bool(
            extra_documents
        ),

        bool(
            unexpected_non_relation_changes
        ),

        bool(
            unexpected_relation_removals
        ),

        bool(
            unexpected_relation_additions
        ),

        bool(
            expected_removal_failures
        ),

        operation_failures > 0,
    ]

    final_status = (
        "FAIL"
        if any(
            fail_conditions
        )
        else "PASS"
    )

    # ========================================================
    # REPORT
    # ========================================================

    report = {

        "post_validator":
            "semantic_factual_post_validator",

        "mode":
            "STRICT_BEFORE_AFTER_RELATION_INTEGRITY",

        "summary": {

            "documents_checked":
                len(
                    before_names
                    & after_names
                ),

            "expected_logical_removals":
                len(
                    applied_operations
                ),

            "verified_operations":
                len(
                    verified_operations
                ),

            "operation_failures":
                operation_failures,

            "documents_with_expected_changes":
                len(
                    documents_with_expected_changes
                ),

            "unexpected_non_relation_changes":
                len(
                    unexpected_non_relation_changes
                ),

            "unexpected_relation_removals":
                len(
                    unexpected_relation_removals
                ),

            "unexpected_relation_additions":
                len(
                    unexpected_relation_additions
                ),

            "missing_documents_after":
                len(
                    missing_documents
                ),

            "extra_documents_after":
                len(
                    extra_documents
                ),

            "status":
                final_status,
        },

        "missing_documents_after":
            missing_documents,

        "extra_documents_after":
            extra_documents,

        "verified_operations":
            verified_operations,

        "expected_removal_failures":
            expected_removal_failures,

        "unexpected_non_relation_changes":
            unexpected_non_relation_changes,

        "unexpected_relation_removals":
            unexpected_relation_removals,

        "unexpected_relation_additions":
            unexpected_relation_additions,
    }

    save_json(
        POST_REPORT,
        report,
    )

    # ========================================================
    # PRINT
    # ========================================================

    print("=" * 120)

    print(
        "TRACE / SGCE - "
        "SEMANTIC FACTUAL POST-VALIDATION V1"
    )

    print("=" * 120)

    print(
        f"Documents vérifiés                  : "
        f"{len(before_names & after_names)}"
    )

    print(
        f"Suppressions logiques attendues     : "
        f"{len(applied_operations)}"
    )

    print(
        f"Opérations vérifiées                : "
        f"{len(verified_operations)}"
    )

    print(
        f"Opérations FAIL                     : "
        f"{operation_failures}"
    )

    print()

    print(
        f"Changements hors relations          : "
        f"{len(unexpected_non_relation_changes)}"
    )

    print(
        f"Suppressions relations inattendues  : "
        f"{len(unexpected_relation_removals)}"
    )

    print(
        f"Ajouts relations inattendus         : "
        f"{len(unexpected_relation_additions)}"
    )

    print()

    print(
        f"Docs manquants APRES                : "
        f"{len(missing_documents)}"
    )

    print(
        f"Docs supplémentaires APRES          : "
        f"{len(extra_documents)}"
    )

    print()

    print(
        "STATUT FINAL SEMANTIC FACTUAL REPAIR: "
        f"{final_status}"
    )

    print()

    print(
        f"Rapport                             : "
        f"{POST_REPORT}"
    )

    print()

    print(
        "Aucune donnée clinique n'a été modifiée "
        "par ce post-validateur."
    )


if __name__ == "__main__":
    main()