# -*- coding: utf-8 -*-

"""
semantic_factual_safe_corrector.py
==================================

TRACE / SGCE - SEMANTIC FACTUAL SAFE CORRECTOR V1

OBJECTIF
--------
Appliquer uniquement les suppressions explicitement autorisées par :

    contradiction_final_status == "SAFE_REMOVE"
    contradiction_final_action == "REMOVE_RELATION"

Le script :

1. copie les documents cliniques sources dans un nouveau dossier ;
2. ne modifie jamais SOURCE_DIR ;
3. retrouve chaque relation validée ;
4. supprime uniquement cette relation ;
5. supprime toutes ses occurrences physiques équivalentes
   (global_relations + pages si duplication) ;
6. conserve toutes les entités ;
7. conserve toutes les autres relations ;
8. génère un rapport BEFORE -> AFTER.

IMPORTANT
---------
Les cas REVIEW ne sont jamais modifiés.
"""

import json
import shutil

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

INPUT_FILE = ROOT / "outputs" / "semantic_factual_contradiction_validated.json"
OUTPUT_DIR = ROOT / "semantic_factual_safe_corrected"
REPORT_FILE = OUTPUT_DIR / "semantic_factual_correction_report.json"

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


# ============================================================
# RELATION HELPERS
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


# ============================================================
# ACTION HELPERS
# ============================================================

def action_relation_id(action):

    return (
        action.get("relation_id")
        or action.get("id_relation")
        or action.get("identifiant_relation")
    )


def action_relation_type(action):

    return (
        action.get("relation_type")
        or action.get("relation_name")
        or action.get("relation")
        or ""
    )


def action_source_id(action):

    return (
        action.get("source_id")
        or action.get("source_entity_id")
    )


def action_target_id(action):

    return (
        action.get("target_id")
        or action.get("target_entity_id")
    )


# ============================================================
# NORMALISATION
# ============================================================

def norm(value):

    if value is None:
        return ""

    return str(
        value
    ).strip().lower()


# ============================================================
# RELATION MATCHING
# ============================================================

def relation_matches_action(
    relation,
    action,
):

    """
    Matching conservateur.

    Priorité :
        1. relation_id exact ;
        2. fallback signature :
           relation_type + source + target.

    Le fallback n'est utilisé que si aucun relation_id
    exploitable n'est disponible dans l'action.
    """

    rid_action = action_relation_id(
        action
    )

    rid_relation = relation_id(
        relation
    )

    # --------------------------------------------------------
    # MATCH PAR ID
    # --------------------------------------------------------

    if rid_action not in (
        None,
        "",
    ):

        return (
            str(rid_relation)
            == str(rid_action)
        )

    # --------------------------------------------------------
    # FALLBACK SIGNATURE
    # --------------------------------------------------------

    expected_type = norm(
        action_relation_type(
            action
        )
    )

    expected_source = norm(
        action_source_id(
            action
        )
    )

    expected_target = norm(
        action_target_id(
            action
        )
    )

    actual_type = norm(
        relation_type(
            relation
        )
    )

    actual_source = norm(
        relation_source(
            relation
        )
    )

    actual_target = norm(
        relation_target(
            relation
        )
    )

    # Il faut au minimum les trois composants
    # pour autoriser un fallback.
    if not (
        expected_type
        and expected_source
        and expected_target
    ):
        return False

    return (
        actual_type == expected_type
        and actual_source == expected_source
        and actual_target == expected_target
    )


# ============================================================
# RELATION LISTS
# ============================================================

def relation_lists(doc):

    """
    Retourne toutes les listes physiques de relations.

    Une même relation peut être présente :
    - dans global_relations ;
    - dans une page.

    On doit supprimer toutes les occurrences physiques
    correspondant à la même relation logique.
    """

    result = []

    global_relations = doc.get(
        "global_relations"
    )

    if isinstance(
        global_relations,
        list,
    ):

        result.append({
            "location":
                "global_relations",

            "page":
                None,

            "relations":
                global_relations,
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

        if isinstance(
            relations,
            list,
        ):

            result.append({
                "location":
                    "page",

                "page":
                    (
                        page.get("page")
                        or page.get("page_number")
                        or page.get("numero_page")
                        or page_index + 1
                    ),

                "relations":
                    relations,
            })

    return result


# ============================================================
# REMOVE RELATION
# ============================================================

def remove_relation(
    doc,
    action,
):

    """
    Supprime toutes les occurrences physiques de la relation
    correspondant à une action SAFE_REMOVE.

    Retourne :
        physical_removed
        removed_occurrences
    """

    physical_removed = 0

    removed_occurrences = []

    for container in relation_lists(
        doc
    ):

        relations = container[
            "relations"
        ]

        kept = []

        for relation in relations:

            if relation_matches_action(
                relation,
                action,
            ):

                physical_removed += 1

                removed_occurrences.append({

                    "location":
                        container[
                            "location"
                        ],

                    "page":
                        container[
                            "page"
                        ],

                    "relation":
                        relation,
                })

            else:

                kept.append(
                    relation
                )

        # Modification in-place de la liste originale.
        relations[:] = kept

    return (
        physical_removed,
        removed_occurrences,
    )


# ============================================================
# COUNT
# ============================================================

def count_entities(doc):

    count = 0

    if isinstance(
        doc.get(
            "global_entities"
        ),
        list,
    ):

        count += len(
            doc[
                "global_entities"
            ]
        )

    for page in doc.get(
        "pages",
        [],
    ) or []:

        if (
            isinstance(
                page,
                dict,
            )
            and isinstance(
                page.get(
                    "entities"
                ),
                list,
            )
        ):

            count += len(
                page[
                    "entities"
                ]
            )

    return count


def count_relations(doc):

    count = 0

    for container in relation_lists(
        doc
    ):

        count += len(
            container[
                "relations"
            ]
        )

    return count


# ============================================================
# MAIN
# ============================================================

def main():

    # --------------------------------------------------------
    # CHECKS
    # --------------------------------------------------------

    if not SOURCE_DIR.exists():

        raise FileNotFoundError(
            "Dossier clinique source introuvable : "
            f"{SOURCE_DIR}\n\n"
            "Vérifiez SOURCE_DIR avant d'exécuter "
            "le correcteur."
        )

    if not INPUT_FILE.exists():

        raise FileNotFoundError(
            f"Fichier de validation introuvable : "
            f"{INPUT_FILE}"
        )

    payload = load_json(
        INPUT_FILE
    )

    all_validated = payload.get(
        "contradiction_validated",
        [],
    )

    # --------------------------------------------------------
    # STRICT SAFE REMOVE
    # --------------------------------------------------------

    actions = [

        item
        for item in all_validated

        if (
            item.get(
                "contradiction_final_status"
            )
            == "SAFE_REMOVE"

            and item.get(
                "contradiction_final_action"
            )
            == "REMOVE_RELATION"
        )
    ]

    # --------------------------------------------------------
    # RESET OUTPUT
    # --------------------------------------------------------

    if OUTPUT_DIR.exists():

        shutil.rmtree(
            OUTPUT_DIR
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # CLINICAL DOCUMENTS
    # --------------------------------------------------------

    docs = [

        path
        for path in sorted(
            SOURCE_DIR.glob(
                "*.json"
            )
        )

        if is_clinical(
            path
        )
    ]

    # --------------------------------------------------------
    # COPY SOURCE -> OUTPUT
    # --------------------------------------------------------

    for src in docs:

        shutil.copy2(
            src,
            OUTPUT_DIR
            / src.name,
        )

    # --------------------------------------------------------
    # APPLY
    # --------------------------------------------------------

    operations = []

    errors = []

    modified_documents = set()

    total_physical_removed = 0

    # --------------------------------------------------------
    # Pour chaque action logique
    # --------------------------------------------------------

    for action in actions:

        document = action.get(
            "document"
        )

        rid = action_relation_id(
            action
        )

        path = (
            OUTPUT_DIR
            / str(document)
        )

        # ----------------------------------------------------
        # DOCUMENT ABSENT
        # ----------------------------------------------------

        if not path.exists():

            errors.append({

                "document":
                    document,

                "relation_id":
                    rid,

                "error":
                    "DOCUMENT_NOT_FOUND",
            })

            continue

        doc = load_json(
            path
        )

        entities_before = count_entities(
            doc
        )

        relations_before = count_relations(
            doc
        )

        # ----------------------------------------------------
        # REMOVE
        # ----------------------------------------------------

        (
            physical_removed,
            removed_occurrences,
        ) = remove_relation(
            doc,
            action,
        )

        entities_after = count_entities(
            doc
        )

        relations_after = count_relations(
            doc
        )

        # ----------------------------------------------------
        # NOT FOUND
        # ----------------------------------------------------

        if physical_removed == 0:

            errors.append({

                "document":
                    document,

                "relation_id":
                    rid,

                "relation_type":
                    action_relation_type(
                        action
                    ),

                "source_id":
                    action_source_id(
                        action
                    ),

                "target_id":
                    action_target_id(
                        action
                    ),

                "error":
                    "RELATION_NOT_FOUND",
            })

            operations.append({

                "document":
                    document,

                "relation_id":
                    rid,

                "relation_type":
                    action_relation_type(
                        action
                    ),

                "source_id":
                    action_source_id(
                        action
                    ),

                "target_id":
                    action_target_id(
                        action
                    ),

                "status":
                    "NOT_FOUND",

                "physical_occurrences_removed":
                    0,
            })

            continue

        # ----------------------------------------------------
        # SAFETY CHECK :
        # ENTITIES MUST NEVER CHANGE
        # ----------------------------------------------------

        if entities_before != entities_after:

            raise RuntimeError(
                "ERREUR DE SECURITE : "
                "le nombre d'entités a changé pendant "
                f"la suppression de {rid} dans {document}."
            )

        # ----------------------------------------------------
        # WRITE
        # ----------------------------------------------------

        save_json(
            path,
            doc,
        )

        modified_documents.add(
            str(document)
        )

        total_physical_removed += (
            physical_removed
        )

        # ----------------------------------------------------
        # REPORT
        # ----------------------------------------------------

        operations.append({

            "document":
                document,

            "relation_id":
                rid,

            "relation_type":
                action_relation_type(
                    action
                ),

            "source_id":
                action_source_id(
                    action
                ),

            "target_id":
                action_target_id(
                    action
                ),

            "source_text":
                (
                    action.get(
                        "source_text"
                    )
                    or action.get(
                        "source_proof"
                    )
                ),

            "target_text":
                (
                    action.get(
                        "target_text"
                    )
                    or action.get(
                        "target_proof"
                    )
                ),

            "negated_side":
                action.get(
                    "negated_side"
                ),

            "negation_cue":
                action.get(
                    "negation_cue"
                ),

            "negation_distance":
                action.get(
                    "negation_distance"
                ),

            "local_context":
                action.get(
                    "local_context"
                ),

            "contradiction_confidence":
                action.get(
                    "contradiction_confidence"
                ),

            "entities_before":
                entities_before,

            "entities_after":
                entities_after,

            "relations_before":
                relations_before,

            "relations_after":
                relations_after,

            "physical_occurrences_removed":
                physical_removed,

            "removed_occurrences":
                removed_occurrences,

            "status":
                "APPLIED",
        })

    # ========================================================
    # REPORT
    # ========================================================

    status_counts = Counter(
        operation[
            "status"
        ]
        for operation in operations
    )

    applied_operations = sum(
        1
        for operation in operations
        if operation[
            "status"
        ] == "APPLIED"
    )

    report = {

        "corrector":
            "semantic_factual_safe_corrector",

        "mode":
            "STRICT_SAFE_REMOVE_ONLY",

        "source_directory":
            str(
                SOURCE_DIR
            ),

        "output_directory":
            str(
                OUTPUT_DIR
            ),

        "summary": {

            "safe_remove_actions_received":
                len(
                    actions
                ),

            "documents_copied":
                len(
                    docs
                ),

            "logical_relations_removed":
                applied_operations,

            "physical_occurrences_removed":
                total_physical_removed,

            "documents_modified":
                len(
                    modified_documents
                ),

            "errors":
                len(
                    errors
                ),

            "operation_status_counts":
                dict(
                    status_counts
                ),
        },

        "operations":
            operations,

        "errors":
            errors,
    }

    save_json(
        REPORT_FILE,
        report,
    )

    # ========================================================
    # PRINT
    # ========================================================

    print("=" * 120)

    print(
        "TRACE / SGCE - "
        "SEMANTIC FACTUAL SAFE CORRECTOR V1"
    )

    print("=" * 120)

    print(
        f"Actions SAFE_REMOVE reçues          : "
        f"{len(actions)}"
    )

    print(
        f"Documents copiés                    : "
        f"{len(docs)}"
    )

    print(
        f"Relations logiques supprimées       : "
        f"{applied_operations}"
    )

    print(
        f"Occurrences physiques supprimées    : "
        f"{total_physical_removed}"
    )

    print(
        f"Documents modifiés                  : "
        f"{len(modified_documents)}"
    )

    print(
        f"Erreurs                             : "
        f"{len(errors)}"
    )

    print()

    print(
        "STATUTS DES OPERATIONS"
    )

    print("-" * 120)

    for key, value in (
        status_counts.most_common()
    ):

        print(
            f"{key:<60}: {value}"
        )

    print()

    print(
        "RELATIONS SUPPRIMEES"
    )

    print("-" * 120)

    for operation in operations:

        if (
            operation.get(
                "status"
            )
            != "APPLIED"
        ):
            continue

        print(
            f"{operation.get('document')} | "
            f"{operation.get('relation_id')} | "
            f"{operation.get('relation_type')}"
        )

        print(
            f"  {operation.get('source_text')} "
            f"--{operation.get('relation_type')}--> "
            f"{operation.get('target_text')}"
        )

        print(
            f"  occurrences physiques supprimées : "
            f"{operation.get('physical_occurrences_removed')}"
        )

        print()

    print(
        f"Sortie clinique                     : "
        f"{OUTPUT_DIR}"
    )

    print(
        f"Rapport                             : "
        f"{REPORT_FILE}"
    )

    print()

    print(
        "Les fichiers sources n'ont pas été modifiés."
    )


if __name__ == "__main__":
    main()