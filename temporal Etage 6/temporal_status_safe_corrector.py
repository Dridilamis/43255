# -*- coding: utf-8 -*-

"""
temporal_status_safe_corrector.py
=================================

TRACE / SGCE â€” Temporal Status Safe Corrector

AUTONOMOUS TEXT-GUIDED

Objectif
--------
Appliquer uniquement les dÃ©cisions validÃ©es :

    SAFE_ACCEPT + SET_TEMPORAL_STATUS

Le correcteur :
- repart de la sortie officielle de residual_auto_correctable ;
- retrouve l'entitÃ© par son identifiant ;
- crÃ©e trace_context_status s'il n'existe pas ;
- conserve les autres champs existants ;
- modifie uniquement temporal_status ;
- ajoute une trace de la correction ;
- applique la correction Ã  toutes les occurrences physiques
  correspondant au mÃªme entity_id ;
- ne modifie jamais les fichiers sources.

EntrÃ©e clinique
---------------
MultiAgent/
    residual_auto_correctable/
        residual_auto_correctable_safe_corrected/

DÃ©cisions
---------
MultiAgent/
    temporal_status/
        outputs/
            temporal_status_validated_decisions.json

Sortie
------
MultiAgent/
    temporal_status/
        temporal_status_safe_corrected/

Rapport
-------
MultiAgent/
    temporal_status/
        temporal_status_safe_corrected/
            temporal_status_correction_report.json
"""

import json
import shutil
from pathlib import Path
from collections import Counter


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(
    r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM"
    r"\Reduction_hallucinations"
)

M = BASE_DIR / "temporal Etage 6"


SOURCE_DIR = (
    BASE_DIR / "numeric_unit Etage 5"
    / "numeric_unit_safe_corrected"
)


INPUT_FILE = (
    M / "outputs"
    / "temporal_status_validated_decisions.json"
)


OUTPUT_DIR = (
    M / "temporal_status_safe_corrected"
)


REPORT_FILE = (
    OUTPUT_DIR
    / "temporal_status_correction_report.json"
)


# ============================================================
# ANNOTATION KEYS
# ============================================================

ANNOTATION_KEYS = (
    "trace_context_status",
    "trace_temporal_status",
    "trace_temporal_status_audit",
    "temporal_status_annotation",
)


# ============================================================
# JSON
# ============================================================

def load_json(path):
    with Path(path).open(
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


def save_json(path, data):
    path = Path(path)

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


# ============================================================
# ENTITY HELPERS
# ============================================================

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


def entity_text(entity):
    values = []

    for key in (
        "preuve",
        "texte",
        "text",
        "nom",
        "name",
        "contenu",
        "libelle",
        "valeur",
    ):
        value = entity.get(key)

        if value not in (None, ""):
            value = str(value).strip()

            if value and value not in values:
                values.append(value)

    return " | ".join(values)


# ============================================================
# CLINICAL DOCUMENT DETECTION
# ============================================================

def is_clinical(path):

    if path.name.endswith("_report.json"):
        return False

    try:
        doc = load_json(path)
    except Exception:
        return False

    if not isinstance(doc, dict):
        return False

    return any(
        key in doc
        for key in (
            "pages",
            "global_entities",
            "global_relations",
        )
    )


def clinical_files(directory):

    result = []

    directory = Path(directory)

    if not directory.exists():
        return result

    for path in sorted(
        directory.glob("*.json")
    ):
        if is_clinical(path):
            result.append(path)

    return result


# ============================================================
# ENTITY CONTAINERS
# ============================================================

def entity_lists(doc):
    """
    Retourne toutes les listes physiques d'entitÃ©s.

    Une mÃªme entitÃ© logique peut Ãªtre prÃ©sente :
    - dans global_entities ;
    - dans pages[x].entities.

    Le correcteur synchronise toutes les occurrences physiques
    possÃ©dant le mÃªme entity_id.
    """

    lists = []

    if isinstance(
        doc.get("global_entities"),
        list,
    ):
        lists.append(
            doc["global_entities"]
        )

    for page in doc.get(
        "pages",
        [],
    ) or []:

        if not isinstance(
            page,
            dict,
        ):
            continue

        if isinstance(
            page.get("entities"),
            list,
        ):
            lists.append(
                page["entities"]
            )

    return lists


# ============================================================
# TEMPORAL ANNOTATION
# ============================================================

def get_existing_annotation(entity):
    """
    Recherche une annotation temporelle dÃ©jÃ  prÃ©sente.

    Retour :
        (annotation_key, annotation_dict)

    ou :
        (None, None)
    """

    for key in ANNOTATION_KEYS:

        value = entity.get(key)

        if isinstance(
            value,
            dict,
        ):
            return key, value

    return None, None


def get_current_temporal_status(annotation):

    if not isinstance(
        annotation,
        dict,
    ):
        return None

    return (
        annotation.get(
            "temporal_status"
        )
        or annotation.get(
            "temporality"
        )
        or annotation.get(
            "statut_temporel"
        )
    )


def set_temporal_status(
    entity,
    proposed_status,
    action,
):
    """
    Applique une correction temporelle sÃ»re.

    Si aucune annotation temporelle n'existe,
    trace_context_status est crÃ©Ã©.

    Si une annotation existe dÃ©jÃ  sous une clÃ©
    supportÃ©e, elle est conservÃ©e et enrichie.

    Retour :
        {
            changed,
            annotation_key,
            previous_status,
            new_status,
            reason
        }
    """

    annotation_key, annotation = (
        get_existing_annotation(entity)
    )

    # --------------------------------------------------------
    # Aucune annotation existante
    # --------------------------------------------------------

    if annotation is None:

        # Protection :
        # si trace_context_status existe mais n'est pas un dict,
        # on ne l'Ã©crase pas.
        existing_raw = entity.get(
            "trace_context_status"
        )

        if (
            existing_raw is not None
            and not isinstance(
                existing_raw,
                dict,
            )
        ):
            return {
                "changed": False,
                "annotation_key":
                    "trace_context_status",
                "previous_status": None,
                "new_status":
                    proposed_status,
                "reason":
                    "INVALID_EXISTING_ANNOTATION_STRUCTURE",
            }

        annotation_key = (
            "trace_context_status"
        )

        entity[
            annotation_key
        ] = {}

        annotation = entity[
            annotation_key
        ]

    # --------------------------------------------------------
    # Statut actuel
    # --------------------------------------------------------

    previous_status = (
        get_current_temporal_status(
            annotation
        )
    )

    # --------------------------------------------------------
    # DÃ©jÃ  satisfait
    # --------------------------------------------------------

    if (
        previous_status
        == proposed_status
    ):
        return {
            "changed": False,
            "annotation_key":
                annotation_key,
            "previous_status":
                previous_status,
            "new_status":
                proposed_status,
            "reason":
                "ALREADY_SATISFIED",
        }

    # --------------------------------------------------------
    # Choisir le champ temporel existant
    # --------------------------------------------------------

    if "temporality" in annotation:

        temporal_field = (
            "temporality"
        )

    elif (
        "statut_temporel"
        in annotation
    ):

        temporal_field = (
            "statut_temporel"
        )

    else:

        temporal_field = (
            "temporal_status"
        )

    # --------------------------------------------------------
    # Appliquer
    # --------------------------------------------------------

    annotation[
        temporal_field
    ] = proposed_status

    # --------------------------------------------------------
    # Provenance / audit
    # --------------------------------------------------------

    annotation[
        "temporal_repair"
    ] = {

        "previous_temporal_status":
            previous_status,

        "new_temporal_status":
            proposed_status,

        "evidence":
            action.get(
                "temporal_evidence"
            ),

        "confidence":
            action.get(
                "confidence"
            ),

        "classifier_decision":
            action.get(
                "decision"
            ),

        "validator_status":
            action.get(
                "final_status"
            ),

        "validator_reason":
            action.get(
                "validation_reason"
            ),

        "source":
            "TRACE_SGCE_TEMPORAL_STATUS",

        "mode":
            "AUTONOMOUS_TEXT_GUIDED",
    }

    return {
        "changed": True,
        "annotation_key":
            annotation_key,
        "previous_status":
            previous_status,
        "new_status":
            proposed_status,
        "reason":
            "UPDATED",
    }


# ============================================================
# LOAD SAFE ACTIONS
# ============================================================

def load_safe_actions():

    if not INPUT_FILE.exists():

        raise FileNotFoundError(
            "Fichier de dÃ©cisions validÃ©es "
            f"introuvable : {INPUT_FILE}"
        )

    payload = load_json(
        INPUT_FILE
    )

    validated = payload.get(
        "validated",
        [],
    )

    actions = []

    for item in validated:

        if (
            item.get(
                "final_status"
            )
            != "SAFE_ACCEPT"
        ):
            continue

        if (
            item.get(
                "final_action"
            )
            != "SET_TEMPORAL_STATUS"
        ):
            continue

        proposed = item.get(
            "proposed_temporal_status"
        )

        if proposed in (
            None,
            "",
            "UNKNOWN",
        ):
            continue

        actions.append(
            item
        )

    return actions


# ============================================================
# MAIN
# ============================================================

def main():

    # --------------------------------------------------------
    # VÃ©rifications
    # --------------------------------------------------------

    if not SOURCE_DIR.exists():

        raise FileNotFoundError(
            "EntrÃ©e clinique introuvable : "
            f"{SOURCE_DIR}"
        )

    actions = (
        load_safe_actions()
    )

    # --------------------------------------------------------
    # RecrÃ©er sortie propre
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
    # Copier corpus source
    # --------------------------------------------------------

    docs = clinical_files(
        SOURCE_DIR
    )

    for src in docs:

        shutil.copy2(
            src,
            OUTPUT_DIR
            / src.name,
        )

    # --------------------------------------------------------
    # Indexer les actions par document
    # --------------------------------------------------------

    actions_by_document = {}

    for action in actions:

        document = action.get(
            "document"
        )

        if not document:
            continue

        actions_by_document.setdefault(
            str(document),
            [],
        ).append(
            action
        )

    # --------------------------------------------------------
    # Statistiques
    # --------------------------------------------------------

    operations = []

    errors = []

    modified_docs = set()

    operation_status_counts = (
        Counter()
    )

    physical_occurrences_changed = 0

    logical_operations_applied = 0

    already_satisfied = 0

    entities_not_found = 0

    invalid_annotation_structures = 0

    # --------------------------------------------------------
    # Traitement document par document
    # --------------------------------------------------------

    for document, doc_actions in (
        actions_by_document.items()
    ):

        path = (
            OUTPUT_DIR
            / document
        )

        # ----------------------------------------------------
        # Document absent
        # ----------------------------------------------------

        if not path.exists():

            for action in doc_actions:

                error = {
                    "candidate_id":
                        action.get(
                            "candidate_id"
                        ),

                    "document":
                        document,

                    "entity_id":
                        action.get(
                            "entity_id"
                        ),

                    "error":
                        "DOCUMENT_NOT_FOUND",
                }

                errors.append(
                    error
                )

            continue

        # ----------------------------------------------------
        # Charger document
        # ----------------------------------------------------

        try:

            doc = load_json(
                path
            )

        except Exception as exc:

            for action in doc_actions:

                errors.append({

                    "candidate_id":
                        action.get(
                            "candidate_id"
                        ),

                    "document":
                        document,

                    "entity_id":
                        action.get(
                            "entity_id"
                        ),

                    "error":
                        "DOCUMENT_LOAD_ERROR",

                    "detail":
                        str(exc),
                })

            continue

        document_changed = False

        # ----------------------------------------------------
        # Actions du document
        # ----------------------------------------------------

        for action in doc_actions:

            target_id_raw = (
                action.get(
                    "entity_id"
                )
            )

            if target_id_raw is None:

                errors.append({

                    "candidate_id":
                        action.get(
                            "candidate_id"
                        ),

                    "document":
                        document,

                    "entity_id":
                        None,

                    "error":
                        "MISSING_ENTITY_ID",
                })

                continue

            target_id = str(
                target_id_raw
            )

            proposed = action.get(
                "proposed_temporal_status"
            )

            # -----------------------------------------------
            # Protection
            # -----------------------------------------------

            if proposed in (
                None,
                "",
                "UNKNOWN",
            ):

                errors.append({

                    "candidate_id":
                        action.get(
                            "candidate_id"
                        ),

                    "document":
                        document,

                    "entity_id":
                        target_id,

                    "error":
                        "INVALID_PROPOSED_TEMPORAL_STATUS",
                })

                continue

            # -----------------------------------------------
            # Chercher toutes les occurrences physiques
            # -----------------------------------------------

            found = 0

            changed = 0

            satisfied = 0

            invalid_structure = 0

            previous_statuses = []

            annotation_keys = []

            # -----------------------------------------------
            # Toutes les listes physiques
            # -----------------------------------------------

            for e_list in entity_lists(
                doc
            ):

                for entity in e_list:

                    eid = entity_id(
                        entity
                    )

                    if eid is None:
                        continue

                    if str(eid) != target_id:
                        continue

                    found += 1

                    result = (
                        set_temporal_status(
                            entity,
                            proposed,
                            action,
                        )
                    )

                    annotation_keys.append(
                        result.get(
                            "annotation_key"
                        )
                    )

                    previous_statuses.append(
                        result.get(
                            "previous_status"
                        )
                    )

                    if result[
                        "changed"
                    ]:

                        changed += 1

                    elif (
                        result[
                            "reason"
                        ]
                        == "ALREADY_SATISFIED"
                    ):

                        satisfied += 1

                    elif (
                        result[
                            "reason"
                        ]
                        == "INVALID_EXISTING_ANNOTATION_STRUCTURE"
                    ):

                        invalid_structure += 1

            # -----------------------------------------------
            # EntitÃ© absente
            # -----------------------------------------------

            if found == 0:

                entities_not_found += 1

                operation_status_counts[
                    "ENTITY_NOT_FOUND"
                ] += 1

                errors.append({

                    "candidate_id":
                        action.get(
                            "candidate_id"
                        ),

                    "document":
                        document,

                    "entity_id":
                        target_id,

                    "error":
                        "ENTITY_NOT_FOUND",
                })

                operations.append({

                    "candidate_id":
                        action.get(
                            "candidate_id"
                        ),

                    "document":
                        document,

                    "entity_id":
                        target_id,

                    "new_temporal_status":
                        proposed,

                    "physical_occurrences_found":
                        0,

                    "physical_occurrences_changed":
                        0,

                    "status":
                        "ENTITY_NOT_FOUND",
                })

                continue

            # -----------------------------------------------
            # Structure invalide partout
            # -----------------------------------------------

            if (
                changed == 0
                and satisfied == 0
                and invalid_structure > 0
            ):

                invalid_annotation_structures += 1

                operation_status_counts[
                    "INVALID_ANNOTATION_STRUCTURE"
                ] += 1

                errors.append({

                    "candidate_id":
                        action.get(
                            "candidate_id"
                        ),

                    "document":
                        document,

                    "entity_id":
                        target_id,

                    "error":
                        "INVALID_ANNOTATION_STRUCTURE",
                })

                operations.append({

                    "candidate_id":
                        action.get(
                            "candidate_id"
                        ),

                    "document":
                        document,

                    "entity_id":
                        target_id,

                    "new_temporal_status":
                        proposed,

                    "physical_occurrences_found":
                        found,

                    "physical_occurrences_changed":
                        0,

                    "status":
                        "INVALID_ANNOTATION_STRUCTURE",
                })

                continue

            # -----------------------------------------------
            # APPLIED
            # -----------------------------------------------

            if changed > 0:

                status = (
                    "APPLIED"
                )

                logical_operations_applied += 1

                physical_occurrences_changed += (
                    changed
                )

                document_changed = True

                operation_status_counts[
                    status
                ] += 1

            # -----------------------------------------------
            # DÃ©jÃ  satisfait
            # -----------------------------------------------

            else:

                status = (
                    "ALREADY_SATISFIED"
                )

                already_satisfied += 1

                operation_status_counts[
                    status
                ] += 1

            # -----------------------------------------------
            # Rapport opÃ©ration
            # -----------------------------------------------

            operations.append({

                "candidate_id":
                    action.get(
                        "candidate_id"
                    ),

                "document":
                    document,

                "entity_id":
                    target_id,

                "entity_text":
                    action.get(
                        "entity_text"
                    ),

                "entity_type":
                    action.get(
                        "entity_type"
                    ),

                "previous_temporal_status":
                    action.get(
                        "current_temporal_status"
                    ),

                "previous_statuses_found":
                    previous_statuses,

                "new_temporal_status":
                    proposed,

                "annotation_keys":
                    sorted(
                        {
                            str(x)
                            for x in annotation_keys
                            if x
                        }
                    ),

                "physical_occurrences_found":
                    found,

                "physical_occurrences_changed":
                    changed,

                "physical_occurrences_already_satisfied":
                    satisfied,

                "physical_occurrences_invalid_structure":
                    invalid_structure,

                "temporal_evidence":
                    action.get(
                        "temporal_evidence"
                    ),

                "confidence":
                    action.get(
                        "confidence"
                    ),

                "status":
                    status,
            })

        # ----------------------------------------------------
        # Sauvegarder une seule fois le document
        # ----------------------------------------------------

        if document_changed:

            save_json(
                path,
                doc,
            )

            modified_docs.add(
                document
            )

    # ========================================================
    # RAPPORT
    # ========================================================

    report = {

        "corrector":
            "temporal_status_safe_corrector",

        "mode":
            "AUTONOMOUS_TEXT_GUIDED",

        "source_directory":
            str(
                SOURCE_DIR
            ),

        "validated_decisions":
            str(
                INPUT_FILE
            ),

        "output_directory":
            str(
                OUTPUT_DIR
            ),

        "summary": {

            "safe_actions_received":
                len(actions),

            "documents_copied":
                len(docs),

            "logical_operations_applied":
                logical_operations_applied,

            "physical_occurrences_changed":
                physical_occurrences_changed,

            "already_satisfied":
                already_satisfied,

            "documents_modified":
                len(
                    modified_docs
                ),

            "entities_not_found":
                entities_not_found,

            "invalid_annotation_structures":
                invalid_annotation_structures,

            "errors":
                len(
                    errors
                ),

            "operation_status_counts":
                dict(
                    operation_status_counts
                ),
        },

        "modified_documents":
            sorted(
                modified_docs
            ),

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
    # AFFICHAGE
    # ========================================================

    print("=" * 120)

    print(
        "TRACE / SGCE - TEMPORAL STATUS SAFE CORRECTOR "
        "- AUTONOMOUS TEXT-GUIDED"
    )

    print("=" * 120)

    print(
        f"Actions SAFE_ACCEPT reÃ§ues          : "
        f"{len(actions)}"
    )

    print(
        f"Documents copiÃ©s                    : "
        f"{len(docs)}"
    )

    print(
        f"Corrections logiques appliquÃ©es     : "
        f"{logical_operations_applied}"
    )

    print(
        f"Occurrences physiques modifiÃ©es     : "
        f"{physical_occurrences_changed}"
    )

    print(
        f"DÃ©jÃ  satisfaites                     : "
        f"{already_satisfied}"
    )

    print(
        f"Documents modifiÃ©s                  : "
        f"{len(modified_docs)}"
    )

    print(
        f"EntitÃ©s non retrouvÃ©es              : "
        f"{entities_not_found}"
    )

    print(
        f"Structures annotation invalides     : "
        f"{invalid_annotation_structures}"
    )

    print(
        f"Erreurs                             : "
        f"{len(errors)}"
    )

    print()

    print("STATUTS DES OPERATIONS")
    print("-" * 120)

    for key, value in (
        operation_status_counts.items()
    ):

        print(
            f"{key:<52}: {value}"
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
        "Les fichiers sources n'ont pas Ã©tÃ© modifiÃ©s."
    )


if __name__ == "__main__":
    main()
