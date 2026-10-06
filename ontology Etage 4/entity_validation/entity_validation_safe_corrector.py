# -*- coding: utf-8 -*-

"""
TRACE / SGCE - ENTITY VALIDATION SAFE CORRECTOR V2

Applique UNIQUEMENT les retypages validés SAFE_ACCEPT.

Principes de sécurité :
- travaille sur une copie des JSON cliniques ;
- ne modifie jamais les fichiers sources ;
- recherche récursivement les entités via "identifiant_entite" ;
- modifie uniquement le type/catégorie de l'entité ciblée ;
- ne modifie aucune relation ;
- gère les représentations dupliquées d'une même entité ;
- vérifie le type actuel avant modification ;
- produit un rapport complet.
"""

# GENERICITY PATCH: configuration via environment; no corpus-example lexicon.

import os
import json
import shutil
from pathlib import Path
from collections import Counter


# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parent
STAGE4_DIR = ROOT.parent
REDUCTION_DIR = STAGE4_DIR.parent
STAGE3_DIR = REDUCTION_DIR / "document_grounding Etage 3"

SOURCE_DIR = STAGE3_DIR / "semantic_factual" / "semantic_factual_safe_corrected"
VALIDATED_FILE = ROOT / "outputs" / "entity_validation_validated.json"
OUTPUT_DIR = ROOT / "entity_validation_safe_corrected"
REPORT_FILE = OUTPUT_DIR / "entity_validation_correction_report.json"


# ============================================================
# UTILITAIRES
# ============================================================

def load_json(path):
    return json.loads(
        Path(path).read_text(encoding="utf-8")
    )


def save_json(path, data):
    Path(path).write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


def is_clinical_json(path):
    """
    Évite de considérer les rapports comme documents cliniques.
    """

    name = path.name.lower()

    excluded = (
        "report",
        "summary",
        "audit",
        "analysis",
        "validated",
        "decisions",
        "candidates",
    )

    return (
        path.suffix.lower() == ".json"
        and not any(x in name for x in excluded)
    )


# ============================================================
# RECHERCHE RECURSIVE DES ENTITES
# ============================================================

def find_entity_occurrences(obj, entity_id, path="$"):
    """
    Recherche récursivement toutes les représentations physiques
    d'une entité.

    Une entité TRACE est identifiée par :

        "identifiant_entite": "P2_E034"

    Important :
    "identifiant_entite_sujet" et "identifiant_entite_objet"
    appartiennent aux relations et ne sont PAS modifiés.
    """

    found = []

    if isinstance(obj, dict):

        if obj.get("identifiant_entite") == entity_id:
            found.append({
                "object": obj,
                "path": path
            })

        for key, value in obj.items():

            found.extend(
                find_entity_occurrences(
                    value,
                    entity_id,
                    f"{path}.{key}"
                )
            )

    elif isinstance(obj, list):

        for index, value in enumerate(obj):

            found.extend(
                find_entity_occurrences(
                    value,
                    entity_id,
                    f"{path}[{index}]"
                )
            )

    return found


# ============================================================
# TYPE REEL DE L'ENTITE
# ============================================================

def get_entity_type(entity):
    """
    Cherche le type réel dans les variantes présentes
    dans les JSON TRACE.
    """

    for key in (
        "type",
        "type_entite",
        "entity_type",
        "categorie",
        "label"
    ):
        value = entity.get(key)

        if isinstance(value, str) and value.strip():
            return key, value.strip()

    return None, None


# ============================================================
# RETYPAGE
# ============================================================

def retype_entity(entity, expected_old_type, new_type):
    """
    Modifie uniquement le champ qui porte réellement
    le type ontologique.

    Retour :
        status
        field
        old
        new
    """

    field, current_type = get_entity_type(entity)

    if field is None:
        return {
            "status": "ERROR_TYPE_FIELD_NOT_FOUND",
            "field": None,
            "old": None,
            "new": None
        }

    # Sécurité : on ne retype pas une entité dont le type réel
    # ne correspond pas au type attendu par le validateur.

    if expected_old_type and current_type != expected_old_type:

        # Cas où cette occurrence a déjà été corrigée
        if current_type == new_type:
            return {
                "status": "ALREADY_CORRECT",
                "field": field,
                "old": current_type,
                "new": new_type
            }

        return {
            "status": "ERROR_CURRENT_TYPE_MISMATCH",
            "field": field,
            "old": current_type,
            "expected": expected_old_type,
            "new": new_type
        }

    if current_type == new_type:
        return {
            "status": "ALREADY_CORRECT",
            "field": field,
            "old": current_type,
            "new": new_type
        }

    entity[field] = new_type

    return {
        "status": "APPLIED",
        "field": field,
        "old": current_type,
        "new": new_type
    }


# ============================================================
# SIGNATURE DES RELATIONS
# ============================================================

def collect_relations(obj):
    """
    Capture les relations avant/après pour vérifier
    qu'aucune relation n'est modifiée.
    """

    relations = []

    def walk(x):

        if isinstance(x, dict):

            if "identifiant_relation" in x:

                relations.append({
                    "identifiant_relation":
                        x.get("identifiant_relation"),

                    "identifiant_entite_sujet":
                        x.get("identifiant_entite_sujet"),

                    "type_relation":
                        x.get("type_relation"),

                    "identifiant_entite_objet":
                        x.get("identifiant_entite_objet")
                })

            for value in x.values():
                walk(value)

        elif isinstance(x, list):

            for value in x:
                walk(value)

    walk(obj)

    return relations


# ============================================================
# PROGRAMME PRINCIPAL
# ============================================================

def main():

    print("=" * 120)
    print(
        "TRACE / SGCE - "
        "ENTITY VALIDATION SAFE CORRECTOR V2 "
        "- REAL TRACE JSON STRUCTURE"
    )
    print("=" * 120)

    if not SOURCE_DIR.exists():
        raise FileNotFoundError(
            f"Dossier source introuvable : {SOURCE_DIR}"
        )

    if not VALIDATED_FILE.exists():
        raise FileNotFoundError(
            f"Fichier validé introuvable : {VALIDATED_FILE}"
        )

    validated = load_json(VALIDATED_FILE)

    groups = validated.get("validated_groups", [])

    safe_groups = [
        g for g in groups
        if g.get("final_status") == "SAFE_ACCEPT"
        and g.get("final_action") == "RETYPE_ENTITY"
    ]

    print(
        f"Actions SAFE_ACCEPT reçues          : "
        f"{len(safe_groups)}"
    )

    # --------------------------------------------------------
    # Nettoyer l'ancienne sortie
    # --------------------------------------------------------

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------
    # Copier uniquement les JSON cliniques
    # --------------------------------------------------------

    clinical_files = [
        p for p in SOURCE_DIR.glob("*.json")
        if is_clinical_json(p)
    ]

    for src in clinical_files:
        shutil.copy2(
            src,
            OUTPUT_DIR / src.name
        )

    print(
        f"Documents cliniques copiés         : "
        f"{len(clinical_files)}"
    )

    # --------------------------------------------------------
    # Grouper les opérations par document
    # --------------------------------------------------------

    operations_by_doc = {}

    for group in safe_groups:

        document = group.get("document")

        if not document:
            continue

        operations_by_doc.setdefault(
            document,
            []
        ).append(group)

    # --------------------------------------------------------
    # Statistiques
    # --------------------------------------------------------

    logical_retypes = 0
    physical_changes = 0

    modified_documents = set()

    errors = []

    operation_reports = []

    status_counter = Counter()

    relation_alterations = 0

    # --------------------------------------------------------
    # Traitement document par document
    # --------------------------------------------------------

    for document, operations in operations_by_doc.items():

        path = OUTPUT_DIR / document

        if not path.exists():

            for op in operations:

                report = {
                    "document": document,
                    "entity_id": op.get("entity_id"),
                    "status": "ERROR_DOCUMENT_NOT_FOUND"
                }

                operation_reports.append(report)
                errors.append(report)

                status_counter[
                    "ERROR_DOCUMENT_NOT_FOUND"
                ] += 1

            continue

        data = load_json(path)

        # Sauvegarde logique des relations AVANT
        relations_before = collect_relations(data)

        document_changed = False

        for op in operations:

            entity_id = op.get("entity_id")

            old_type = (
                op.get("current_type")
                or op.get("old_type")
            )

            new_type = (
                op.get("proposed_new_type")
                or op.get("new_type")
            )

            entity_text = op.get("entity_text")

            occurrences = find_entity_occurrences(
                data,
                entity_id
            )

            if not occurrences:

                report = {
                    "document": document,
                    "entity_id": entity_id,
                    "entity_text": entity_text,
                    "old_type": old_type,
                    "new_type": new_type,
                    "status": "ERROR_ENTITY_NOT_FOUND"
                }

                operation_reports.append(report)
                errors.append(report)

                status_counter[
                    "ERROR_ENTITY_NOT_FOUND"
                ] += 1

                continue

            occurrence_reports = []

            applied_here = 0
            already_correct = 0
            mismatch = 0

            for occurrence in occurrences:

                entity = occurrence["object"]

                result = retype_entity(
                    entity,
                    old_type,
                    new_type
                )

                occurrence_reports.append({
                    "path": occurrence["path"],
                    **result
                })

                if result["status"] == "APPLIED":

                    applied_here += 1
                    physical_changes += 1
                    document_changed = True

                elif result["status"] == "ALREADY_CORRECT":

                    already_correct += 1

                else:

                    mismatch += 1

            # ------------------------------------------------
            # Statut logique de l'opération
            # ------------------------------------------------

            if applied_here > 0:

                logical_retypes += 1

                status = "APPLIED"

            elif already_correct == len(occurrences):

                status = "ALREADY_CORRECT"

            else:

                status = "ERROR_OCCURRENCE_TYPE_MISMATCH"

            status_counter[status] += 1

            report = {
                "document": document,
                "entity_id": entity_id,
                "entity_text": entity_text,
                "old_type": old_type,
                "new_type": new_type,
                "occurrences_found":
                    len(occurrences),
                "occurrences_modified":
                    applied_here,
                "occurrences_already_correct":
                    already_correct,
                "occurrences_mismatch":
                    mismatch,
                "status": status,
                "details": occurrence_reports
            }

            operation_reports.append(report)

            if status.startswith("ERROR"):
                errors.append(report)

        # ----------------------------------------------------
        # Vérifier relations APRÈS
        # ----------------------------------------------------

        relations_after = collect_relations(data)

        if relations_before != relations_after:

            relation_alterations += 1

            errors.append({
                "document": document,
                "status":
                    "ERROR_RELATION_STRUCTURE_CHANGED"
            })

        # ----------------------------------------------------
        # Sauvegarder document corrigé
        # ----------------------------------------------------

        if document_changed:

            save_json(
                path,
                data
            )

            modified_documents.add(document)

    # ========================================================
    # RAPPORT
    # ========================================================

    report = {

        "corrector":
            "entity_validation_safe_corrector_v2",

        "mode":
            "REAL_TRACE_JSON_STRUCTURE_SAFE_RETYPE",

        "source_directory":
            str(SOURCE_DIR),

        "output_directory":
            str(OUTPUT_DIR),

        "summary": {

            "safe_accept_received":
                len(safe_groups),

            "clinical_documents_copied":
                len(clinical_files),

            "logical_retypes_applied":
                logical_retypes,

            "physical_occurrences_modified":
                physical_changes,

            "documents_modified":
                len(modified_documents),

            "errors":
                len(errors),

            "relation_alterations":
                relation_alterations,

            "status_counts":
                dict(status_counter)
        },

        "operations":
            operation_reports,

        "errors":
            errors
    }

    save_json(
        REPORT_FILE,
        report
    )

    # ========================================================
    # AFFICHAGE
    # ========================================================

    print(
        f"Retypages logiques appliqués        : "
        f"{logical_retypes}"
    )

    print(
        f"Occurrences physiques modifiées     : "
        f"{physical_changes}"
    )

    print(
        f"Documents modifiés                  : "
        f"{len(modified_documents)}"
    )

    print(
        f"Erreurs                             : "
        f"{len(errors)}"
    )

    print(
        f"Altérations de relations            : "
        f"{relation_alterations}"
    )

    print()

    print("STATUTS DES OPERATIONS")
    print("-" * 120)

    for status, count in status_counter.items():

        print(
            f"{status:<60}: {count}"
        )

    print()

    print("RETYPAGES APPLIQUES")
    print("-" * 120)

    applied = [
        x for x in operation_reports
        if x.get("status") == "APPLIED"
    ]

    if not applied:

        print("Aucun retypage appliqué.")

    else:

        for x in applied:

            print(
                f"{x['document']} | "
                f"{x['entity_id']} | "
                f"{x.get('entity_text')} | "
                f"{x.get('old_type')} -> "
                f"{x.get('new_type')} | "
                f"occurrences="
                f"{x.get('occurrences_modified')}"
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

    if errors:

        print(
            "ATTENTION : certaines opérations "
            "nécessitent une vérification."
        )

    else:

        print(
            "Toutes les corrections SAFE ont été "
            "appliquées sans erreur."
        )

    print()
    print(
        "Les fichiers sources n'ont pas été modifiés."
    )


if __name__ == "__main__":
    main()