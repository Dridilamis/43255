# -*- coding: utf-8 -*-

"""
TRACE / SGCE - ONTOLOGY RELATION SAFE CORRECTOR V3
REAL TRACE JSON STRUCTURE + VALIDATED_RELATIONS SUPPORT

Objectif
--------
Appliquer UNIQUEMENT les corrections relationnelles validées :

    final_status == "SAFE_REMOVE"
    final_action == "REMOVE_RELATION"

Structure réelle TRACE :
    identifiant_relation
    identifiant_entite_sujet
    type_relation
    identifiant_entite_objet

Structure réelle du validator :
    validated_relations      : 257
    safe_remove_relations    : 154

Sécurité
--------
- Les fichiers sources ne sont jamais modifiés.
- Le corpus est copié dans un nouveau dossier.
- Suppression uniquement par identifiant_relation exact.
- Vérification supplémentaire du type_relation.
- Vérification des endpoints lorsqu'ils sont disponibles.
- Aucune entité n'est modifiée.
- Aucune relation non validée n'est supprimée.
- Une incohérence entre validator et corrector bloque l'exécution.
- Rapport détaillé de toutes les opérations.
"""

# GENERICITY PATCH: TRACE_BASE_DIR can be supplied through the environment.

import os
import json
import shutil

from pathlib import Path
from collections import Counter, defaultdict
from copy import deepcopy


# =====================================================================
# CONFIGURATION
# =====================================================================

ROOT = Path(__file__).resolve().parent
STAGE4_DIR = ROOT.parent

INPUT_DIR = (
    STAGE4_DIR
    / "entity_validation"
    / "entity_validation_safe_corrected"
)
VALIDATED_FILE = ROOT / "outputs" / "ontology_relation_final_validated.json"
OUTPUT_DIR = ROOT / "ontology_relation_safe_corrected"
REPORT_FILE = OUTPUT_DIR / "ontology_relation_correction_report.json"


# =====================================================================
# UTILITAIRES JSON
# =====================================================================

def load_json(path):

    return json.loads(
        Path(path).read_text(
            encoding="utf-8"
        )
    )


def dump_json(path, obj):

    Path(path).parent.mkdir(
        parents=True,
        exist_ok=True
    )

    Path(path).write_text(
        json.dumps(
            obj,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


def norm(value):

    if value is None:
        return ""

    return str(value).strip()


# =====================================================================
# LECTURE DES DECISIONS DU VALIDATOR
# =====================================================================

def extract_decisions(data):
    """
    Extrait toutes les décisions finales.

    Structure réelle actuelle :

        validated_relations : 257 cas

    Des fallbacks sont conservés uniquement pour compatibilité.
    """

    if isinstance(data, dict):

        # -------------------------------------------------------------
        # STRUCTURE REELLE
        # -------------------------------------------------------------

        if isinstance(
            data.get("validated_relations"),
            list
        ):

            return data["validated_relations"]

        # -------------------------------------------------------------
        # FALLBACKS
        # -------------------------------------------------------------

        for key in [

            "validated_decisions",
            "final_decisions",
            "decisions",
            "results",
            "cases"

        ]:

            value = data.get(key)

            if isinstance(value, list):

                return value

    if isinstance(data, list):

        return data

    return []


# =====================================================================
# STRUCTURE RELATION TRACE
# =====================================================================

def get_relation_id(rel):
    """
    Retourne l'identifiant relationnel.

    Structure TRACE réelle :
        identifiant_relation
    """

    if not isinstance(rel, dict):

        return ""

    return norm(

        rel.get("identifiant_relation")

        or rel.get("relation_id")

        or rel.get("id_relation")

        or rel.get("id")
    )


def get_relation_type(rel):
    """
    Retourne le type de relation.

    Structure TRACE réelle :
        type_relation
    """

    if not isinstance(rel, dict):

        return ""

    return norm(

        rel.get("type_relation")

        or rel.get("relation_name")

        or rel.get("relation")

        or rel.get("predicate")

        or rel.get("type")
    )


def get_source_id(rel):
    """
    Retourne l'identifiant du sujet.

    Structure TRACE réelle :
        identifiant_entite_sujet
    """

    if not isinstance(rel, dict):

        return ""

    return norm(

        rel.get("identifiant_entite_sujet")

        or rel.get("source_id")

        or rel.get("subject_id")
    )


def get_target_id(rel):
    """
    Retourne l'identifiant de l'objet.

    Structure TRACE réelle :
        identifiant_entite_objet
    """

    if not isinstance(rel, dict):

        return ""

    return norm(

        rel.get("identifiant_entite_objet")

        or rel.get("target_id")

        or rel.get("object_id")
    )


def get_source_text(rel):

    if not isinstance(rel, dict):

        return ""

    return norm(

        rel.get("entite_sujet")

        or rel.get("subject")

        or rel.get("source")
    )


def get_target_text(rel):

    if not isinstance(rel, dict):

        return ""

    return norm(

        rel.get("entite_objet")

        or rel.get("object")

        or rel.get("target")
    )


# =====================================================================
# DETECTION D'UN OBJET RELATION TRACE
# =====================================================================

def is_trace_relation(obj):
    """
    Vérifie qu'un objet ressemble réellement à une relation TRACE.

    On exige au minimum :
        identifiant_relation

    et au moins une caractéristique relationnelle.
    """

    if not isinstance(obj, dict):

        return False

    rid = get_relation_id(obj)

    if not rid:

        return False

    relation_features = [

        "type_relation",

        "identifiant_entite_sujet",

        "identifiant_entite_objet",

        "relation_name",

        "source_id",

        "target_id"
    ]

    return any(
        key in obj
        for key in relation_features
    )


# =====================================================================
# RECHERCHE RECURSIVE DES OCCURRENCES D'UNE RELATION
# =====================================================================

def find_relation_occurrences(
    obj,
    wanted_relation_id,
    path="$",
    results=None
):
    """
    Recherche récursivement toutes les occurrences physiques
    d'une relation ayant exactement wanted_relation_id.

    Retourne :

        [
            {
                "parent_list": [...],
                "index": 12,
                "path": "$.global_relations[12]",
                "relation": {...}
            }
        ]
    """

    if results is None:

        results = []

    # -----------------------------------------------------------------
    # DICTIONNAIRE
    # -----------------------------------------------------------------

    if isinstance(obj, dict):

        for key, value in obj.items():

            child_path = (
                f"{path}.{key}"
            )

            find_relation_occurrences(
                value,
                wanted_relation_id,
                child_path,
                results
            )

    # -----------------------------------------------------------------
    # LISTE
    # -----------------------------------------------------------------

    elif isinstance(obj, list):

        for index, item in enumerate(obj):

            child_path = (
                f"{path}[{index}]"
            )

            # ---------------------------------------------------------
            # Relation TRACE ?
            # ---------------------------------------------------------

            if (
                isinstance(item, dict)
                and
                is_trace_relation(item)
                and
                get_relation_id(item)
                == wanted_relation_id
            ):

                results.append({

                    "parent_list":
                        obj,

                    "index":
                        index,

                    "path":
                        child_path,

                    "relation":
                        deepcopy(item)
                })

            # ---------------------------------------------------------
            # Continuer récursivement
            # ---------------------------------------------------------

            find_relation_occurrences(
                item,
                wanted_relation_id,
                child_path,
                results
            )

    return results


# =====================================================================
# VERIFICATION QU'UNE RELATION N'EXISTE PLUS
# =====================================================================

def count_relation_occurrences(
    data,
    relation_id
):

    return len(
        find_relation_occurrences(
            data,
            relation_id
        )
    )


# =====================================================================
# COPIE DU CORPUS
# =====================================================================

def prepare_output_directory():

    if OUTPUT_DIR.exists():

        shutil.rmtree(
            OUTPUT_DIR
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    copied = 0

    for source_file in sorted(
        INPUT_DIR.glob("*.json")
    ):

        # -------------------------------------------------------------
        # Exclure les rapports techniques
        # -------------------------------------------------------------

        lower_name = (
            source_file.name.lower()
        )

        if (
            "correction_report" in lower_name
            or
            "validation_report" in lower_name
            or
            "audit_report" in lower_name
        ):

            continue

        destination = (
            OUTPUT_DIR
            / source_file.name
        )

        shutil.copy2(
            source_file,
            destination
        )

        copied += 1

    return copied


# =====================================================================
# MAIN
# =====================================================================

def main():

    print("=" * 120)

    print(
        "TRACE / SGCE - "
        "ONTOLOGY RELATION SAFE CORRECTOR V3 "
        "- REAL TRACE JSON STRUCTURE"
    )

    print("=" * 120)

    # =================================================================
    # VERIFICATIONS DES ENTREES
    # =================================================================

    if not INPUT_DIR.exists():

        raise RuntimeError(

            "Dossier clinique introuvable :\n"
            f"{INPUT_DIR}"
        )

    if not VALIDATED_FILE.exists():

        raise RuntimeError(

            "Fichier de validation introuvable :\n"
            f"{VALIDATED_FILE}"
        )

    # =================================================================
    # CHARGEMENT VALIDATOR
    # =================================================================

    validated_data = load_json(
        VALIDATED_FILE
    )

    decisions = extract_decisions(
        validated_data
    )

    print(
        f"Décisions finales chargées          : "
        f"{len(decisions)}"
    )

    # -----------------------------------------------------------------
    # Sécurité
    # -----------------------------------------------------------------

    if len(decisions) == 0:

        raise RuntimeError(

            "SECURITE : aucune décision finale n'a été chargée.\n"
            "Aucune correction ne sera appliquée."
        )

    # =================================================================
    # EXTRACTION SAFE_REMOVE
    # =================================================================

    safe_remove = []

    for x in decisions:

        if not isinstance(x, dict):

            continue

        final_status = norm(
            x.get("final_status")
        )

        final_action = norm(
            x.get("final_action")
        )

        if (
            final_status == "SAFE_REMOVE"
            and
            final_action == "REMOVE_RELATION"
        ):

            safe_remove.append(x)

    print(
        f"Actions SAFE_REMOVE détectées       : "
        f"{len(safe_remove)}"
    )

    # =================================================================
    # COMPARAISON AVEC safe_remove_relations
    # =================================================================

    expected_safe = validated_data.get(
        "safe_remove_relations",
        []
    )

    if not isinstance(
        expected_safe,
        list
    ):

        expected_safe = []

    print(
        f"SAFE_REMOVE annoncées validator     : "
        f"{len(expected_safe)}"
    )

    # -----------------------------------------------------------------
    # Barrière de sécurité
    # -----------------------------------------------------------------

    if expected_safe:

        if (
            len(safe_remove)
            !=
            len(expected_safe)
        ):

            raise RuntimeError(

                "\nINCOHERENCE DE SECURITE\n"
                "-----------------------\n"
                f"SAFE_REMOVE détectées : "
                f"{len(safe_remove)}\n"
                f"SAFE_REMOVE annoncées : "
                f"{len(expected_safe)}\n\n"
                "Aucune correction n'a été appliquée."
            )

    # -----------------------------------------------------------------
    # Autre sécurité
    # -----------------------------------------------------------------

    if len(safe_remove) == 0:

        raise RuntimeError(

            "SECURITE : aucune relation SAFE_REMOVE détectée.\n"
            "Aucune correction ne sera appliquée."
        )

    # =================================================================
    # DEDUPLICATION
    # =================================================================

    unique_operations = {}

    duplicate_operations = []

    invalid_operations = []

    for x in safe_remove:

        document = norm(
            x.get("document")
        )

        rid = norm(
            x.get("relation_id")
        )

        if not document or not rid:

            invalid_operations.append({

                "document":
                    document,

                "relation_id":
                    rid,

                "reason":
                    "MISSING_DOCUMENT_OR_RELATION_ID"
            })

            continue

        key = (
            document,
            rid
        )

        if key in unique_operations:

            duplicate_operations.append({

                "document":
                    document,

                "relation_id":
                    rid
            })

            continue

        unique_operations[key] = x

    operations = list(
        unique_operations.values()
    )

    print(
        f"Opérations uniques                  : "
        f"{len(operations)}"
    )

    print(
        f"Doublons ignorés                    : "
        f"{len(duplicate_operations)}"
    )

    print(
        f"Opérations invalides                : "
        f"{len(invalid_operations)}"
    )

    # -----------------------------------------------------------------
    # Sécurité
    # -----------------------------------------------------------------

    if invalid_operations:

        raise RuntimeError(

            f"{len(invalid_operations)} opérations "
            "SAFE_REMOVE n'ont pas de document ou relation_id.\n"
            "Correction interrompue."
        )

    # =================================================================
    # COPIE DES DOCUMENTS
    # =================================================================

    copied = prepare_output_directory()

    print(
        f"Documents cliniques copiés          : "
        f"{copied}"
    )

    # =================================================================
    # GROUPEMENT PAR DOCUMENT
    # =================================================================

    operations_by_document = (
        defaultdict(list)
    )

    for op in operations:

        document = norm(
            op.get("document")
        )

        operations_by_document[
            document
        ].append(op)

    # =================================================================
    # COMPTEURS
    # =================================================================

    status_counter = Counter()

    removed_by_relation = Counter()

    documents_modified = set()

    report_operations = []

    logical_removed = 0

    physical_removed = 0

    # =================================================================
    # TRAITEMENT DOCUMENT PAR DOCUMENT
    # =================================================================

    for (
        document,
        document_operations
    ) in operations_by_document.items():

        document_path = (
            OUTPUT_DIR
            / document
        )

        # -------------------------------------------------------------
        # DOCUMENT ABSENT
        # -------------------------------------------------------------

        if not document_path.exists():

            for op in document_operations:

                status_counter[
                    "ERROR_DOCUMENT_NOT_FOUND"
                ] += 1

                report_operations.append({

                    "document":
                        document,

                    "candidate_id":
                        op.get("candidate_id"),

                    "relation_id":
                        op.get("relation_id"),

                    "relation_name":
                        op.get("relation_name"),

                    "status":
                        "ERROR_DOCUMENT_NOT_FOUND"
                })

            continue

        # -------------------------------------------------------------
        # CHARGER DOCUMENT
        # -------------------------------------------------------------

        clinical = load_json(
            document_path
        )

        document_changed = False

        # =============================================================
        # OPERATIONS
        # =============================================================

        for op in document_operations:

            rid = norm(
                op.get("relation_id")
            )

            expected_relation_name = norm(
                op.get("relation_name")
            )

            expected_source_id = norm(
                op.get("source_id")
            )

            expected_target_id = norm(
                op.get("target_id")
            )

            # ---------------------------------------------------------
            # RECHERCHE EXACTE PAR identifiant_relation
            # ---------------------------------------------------------

            occurrences = (
                find_relation_occurrences(
                    clinical,
                    rid
                )
            )

            before_count = len(
                occurrences
            )

            # ---------------------------------------------------------
            # RELATION ABSENTE
            # ---------------------------------------------------------

            if before_count == 0:

                status_counter[
                    "ERROR_RELATION_NOT_FOUND"
                ] += 1

                report_operations.append({

                    "document":
                        document,

                    "candidate_id":
                        op.get("candidate_id"),

                    "relation_id":
                        rid,

                    "relation_name":
                        expected_relation_name,

                    "status":
                        "ERROR_RELATION_NOT_FOUND",

                    "physical_occurrences_before":
                        0,

                    "physical_occurrences_removed":
                        0,

                    "physical_occurrences_after":
                        0
                })

                continue

            # =========================================================
            # VERIFICATION TYPE RELATION
            # =========================================================

            compatible = []

            type_mismatches = []

            for occurrence in occurrences:

                rel = occurrence[
                    "relation"
                ]

                actual_type = (
                    get_relation_type(rel)
                )

                # -----------------------------------------------------
                # Si les deux existent, ils doivent être identiques
                # -----------------------------------------------------

                if (
                    expected_relation_name
                    and
                    actual_type
                    and
                    actual_type
                    !=
                    expected_relation_name
                ):

                    type_mismatches.append(
                        actual_type
                    )

                    continue

                compatible.append(
                    occurrence
                )

            # ---------------------------------------------------------
            # Aucun type compatible
            # ---------------------------------------------------------

            if not compatible:

                status_counter[
                    "ERROR_RELATION_TYPE_MISMATCH"
                ] += 1

                report_operations.append({

                    "document":
                        document,

                    "candidate_id":
                        op.get("candidate_id"),

                    "relation_id":
                        rid,

                    "relation_name":
                        expected_relation_name,

                    "found_relation_types":
                        sorted(
                            set(type_mismatches)
                        ),

                    "status":
                        "ERROR_RELATION_TYPE_MISMATCH",

                    "physical_occurrences_before":
                        before_count,

                    "physical_occurrences_removed":
                        0,

                    "physical_occurrences_after":
                        before_count
                })

                continue

            # =========================================================
            # VERIFICATION ENDPOINTS
            # =========================================================

            endpoint_compatible = []

            for occurrence in compatible:

                rel = occurrence[
                    "relation"
                ]

                actual_source_id = (
                    get_source_id(rel)
                )

                actual_target_id = (
                    get_target_id(rel)
                )

                source_ok = (

                    not expected_source_id

                    or
                    not actual_source_id

                    or
                    expected_source_id
                    ==
                    actual_source_id
                )

                target_ok = (

                    not expected_target_id

                    or
                    not actual_target_id

                    or
                    expected_target_id
                    ==
                    actual_target_id
                )

                if (
                    source_ok
                    and
                    target_ok
                ):

                    endpoint_compatible.append(
                        occurrence
                    )

            # ---------------------------------------------------------
            # Si les endpoints étaient disponibles dans la décision
            # mais ne correspondent pas, on bloque.
            # ---------------------------------------------------------

            if (
                (
                    expected_source_id
                    or
                    expected_target_id
                )
                and
                not endpoint_compatible
            ):

                status_counter[
                    "ERROR_ENDPOINT_MISMATCH"
                ] += 1

                report_operations.append({

                    "document":
                        document,

                    "candidate_id":
                        op.get("candidate_id"),

                    "relation_id":
                        rid,

                    "relation_name":
                        expected_relation_name,

                    "expected_source_id":
                        expected_source_id,

                    "expected_target_id":
                        expected_target_id,

                    "status":
                        "ERROR_ENDPOINT_MISMATCH",

                    "physical_occurrences_before":
                        before_count,

                    "physical_occurrences_removed":
                        0,

                    "physical_occurrences_after":
                        before_count
                })

                continue

            # ---------------------------------------------------------
            # Utiliser endpoints compatibles si disponibles
            # ---------------------------------------------------------

            if endpoint_compatible:

                compatible = (
                    endpoint_compatible
                )

            # =========================================================
            # SUPPRESSION PHYSIQUE
            # =========================================================

            # Important :
            # supprimer les indices dans l'ordre décroissant
            # pour ne pas décaler la liste.

            grouped = defaultdict(list)

            for occurrence in compatible:

                parent_list = (
                    occurrence[
                        "parent_list"
                    ]
                )

                grouped[
                    id(parent_list)
                ].append(
                    occurrence
                )

            removed_count = 0

            removed_paths = []

            removed_snapshots = []

            for group in grouped.values():

                parent_list = (
                    group[0][
                        "parent_list"
                    ]
                )

                ordered = sorted(

                    group,

                    key=lambda x:
                        x["index"],

                    reverse=True
                )

                for occurrence in ordered:

                    index = (
                        occurrence[
                            "index"
                        ]
                    )

                    # -------------------------------------------------
                    # Sécurité index
                    # -------------------------------------------------

                    if not (
                        0
                        <= index
                        < len(parent_list)
                    ):

                        continue

                    current_relation = (
                        parent_list[index]
                    )

                    # -------------------------------------------------
                    # Dernière vérification ID
                    # -------------------------------------------------

                    if (
                        get_relation_id(
                            current_relation
                        )
                        !=
                        rid
                    ):

                        continue

                    # -------------------------------------------------
                    # Dernière vérification type
                    # -------------------------------------------------

                    current_type = (
                        get_relation_type(
                            current_relation
                        )
                    )

                    if (
                        expected_relation_name
                        and
                        current_type
                        and
                        current_type
                        !=
                        expected_relation_name
                    ):

                        continue

                    removed_paths.append(
                        occurrence[
                            "path"
                        ]
                    )

                    removed_snapshots.append(
                        deepcopy(
                            current_relation
                        )
                    )

                    del parent_list[index]

                    removed_count += 1

            # =========================================================
            # VERIFICATION APRES SUPPRESSION
            # =========================================================

            after_count = (
                count_relation_occurrences(
                    clinical,
                    rid
                )
            )

            # ---------------------------------------------------------
            # SUCCES
            # ---------------------------------------------------------

            if (
                removed_count > 0
                and
                after_count == 0
            ):

                status = "APPLIED"

                logical_removed += 1

                physical_removed += (
                    removed_count
                )

                document_changed = True

                documents_modified.add(
                    document
                )

                status_counter[
                    status
                ] += 1

                actual_relation_type = (
                    expected_relation_name
                )

                if (
                    not actual_relation_type
                    and
                    removed_snapshots
                ):

                    actual_relation_type = (
                        get_relation_type(
                            removed_snapshots[0]
                        )
                    )

                removed_by_relation[
                    actual_relation_type
                    or "<VIDE>"
                ] += 1

            # ---------------------------------------------------------
            # ECHEC
            # ---------------------------------------------------------

            else:

                status = (
                    "ERROR_INCOMPLETE_REMOVAL"
                )

                status_counter[
                    status
                ] += 1

            # =========================================================
            # RAPPORT OPERATION
            # =========================================================

            first_removed = (

                removed_snapshots[0]

                if removed_snapshots

                else {}
            )

            report_operations.append({

                "document":
                    document,

                "candidate_id":
                    op.get("candidate_id"),

                "relation_id":
                    rid,

                "relation_name":
                    expected_relation_name
                    or
                    get_relation_type(
                        first_removed
                    ),

                "source_id":
                    get_source_id(
                        first_removed
                    )
                    or
                    expected_source_id,

                "source_text":
                    get_source_text(
                        first_removed
                    ),

                "target_id":
                    get_target_id(
                        first_removed
                    )
                    or
                    expected_target_id,

                "target_text":
                    get_target_text(
                        first_removed
                    ),

                "final_status":
                    op.get(
                        "final_status"
                    ),

                "final_action":
                    op.get(
                        "final_action"
                    ),

                "status":
                    status,

                "physical_occurrences_before":
                    before_count,

                "physical_occurrences_removed":
                    removed_count,

                "physical_occurrences_after":
                    after_count,

                "removed_paths":
                    removed_paths,

                "removed_relations":
                    removed_snapshots
            })

        # =============================================================
        # SAUVEGARDE DOCUMENT
        # =============================================================

        if document_changed:

            dump_json(
                document_path,
                clinical
            )

    # =================================================================
    # CALCUL DES ERREURS
    # =================================================================

    errors = sum(

        count

        for status, count
        in status_counter.items()

        if status != "APPLIED"
    )

    # =================================================================
    # RAPPORT FINAL
    # =================================================================

    report = {

        "corrector":
            "ontology_relation_safe_corrector",

        "version":
            "V3_REAL_TRACE_STRUCTURE",

        "mode":
            "SAFE_REMOVE_ONLY",

        "input_directory":
            str(INPUT_DIR),

        "validated_file":
            str(VALIDATED_FILE),

        "output_directory":
            str(OUTPUT_DIR),

        "summary": {

            "validated_relations_received":
                len(decisions),

            "safe_remove_detected":
                len(safe_remove),

            "safe_remove_announced":
                len(expected_safe),

            "unique_operations":
                len(operations),

            "duplicate_operations_ignored":
                len(duplicate_operations),

            "clinical_documents_copied":
                copied,

            "logical_relations_removed":
                logical_removed,

            "physical_occurrences_removed":
                physical_removed,

            "documents_modified":
                len(documents_modified),

            "errors":
                errors
        },

        "status_counts":
            dict(
                status_counter
            ),

        "removed_by_relation_type":
            dict(
                removed_by_relation.most_common()
            ),

        "duplicate_operations_ignored":
            duplicate_operations,

        "operations":
            report_operations
    }

    dump_json(
        REPORT_FILE,
        report
    )

    # =================================================================
    # AFFICHAGE
    # =================================================================

    print()

    print(
        f"Relations logiques supprimées       : "
        f"{logical_removed}"
    )

    print(
        f"Occurrences physiques supprimées    : "
        f"{physical_removed}"
    )

    print(
        f"Documents modifiés                  : "
        f"{len(documents_modified)}"
    )

    print(
        f"Erreurs                             : "
        f"{errors}"
    )

    # -----------------------------------------------------------------
    # STATUTS
    # -----------------------------------------------------------------

    print()

    print(
        "STATUTS DES OPERATIONS"
    )

    print("-" * 120)

    if status_counter:

        for (
            status,
            count
        ) in status_counter.most_common():

            print(
                f"{status:<60}: "
                f"{count}"
            )

    else:

        print("Aucun.")

    # -----------------------------------------------------------------
    # RELATIONS
    # -----------------------------------------------------------------

    print()

    print(
        "SUPPRESSIONS PAR TYPE DE RELATION"
    )

    print("-" * 120)

    if removed_by_relation:

        for (
            relation_name,
            count
        ) in removed_by_relation.most_common():

            print(
                f"{relation_name:<60}: "
                f"{count}"
            )

    else:

        print("Aucune.")

    # -----------------------------------------------------------------
    # ERREURS
    # -----------------------------------------------------------------

    failed = [

        x

        for x in report_operations

        if x.get("status")
        !=
        "APPLIED"
    ]

    if failed:

        print()

        print(
            "OPERATIONS NON APPLIQUEES"
        )

        print("-" * 120)

        for x in failed:

            print(

                f"{x.get('document')} | "
                f"{x.get('relation_id')} | "
                f"{x.get('relation_name')} | "
                f"{x.get('status')}"
            )

    # -----------------------------------------------------------------
    # FIN
    # -----------------------------------------------------------------

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

    # =================================================================
    # VERDICT
    # =================================================================

    if (
        errors == 0
        and
        logical_removed
        ==
        len(operations)
    ):

        print(
            "Toutes les suppressions SAFE ont été "
            "appliquées sans erreur."
        )

    else:

        print(
            "ATTENTION : le correcteur n'a pas appliqué "
            "toutes les opérations attendues."
        )

        print(
            "Ne pas utiliser cette sortie comme corpus final "
            "avant post-validation."
        )

    print()

    print(
        "Les fichiers sources n'ont pas été modifiés."
    )


# =====================================================================
# EXECUTION
# =====================================================================

if __name__ == "__main__":

    main()