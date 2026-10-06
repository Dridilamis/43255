# -*- coding: utf-8 -*-
"""
ontology_relation_review_safe_corrector.py
==========================================

TRACE / SGCE
ONTOLOGY RELATION REVIEW SAFE CORRECTOR V1
GENERIC VALIDATOR-DRIVEN SAFE CORRECTION

OBJECTIF
--------
Appliquer uniquement les corrections explicitement validées par :

    ontology_relation_review_validator.py

Actions autorisées :
    - RETYPE_ENTITY
    - INVERT_RELATION

Le script :
    1. lit les décisions validées ;
    2. copie le corpus clinique source ;
    3. résout les entités / relations par identifiant ;
    4. vérifie l'état courant avant modification ;
    5. applique uniquement les actions SAFE ;
    6. synchronise les représentations globales et par page ;
    7. produit un rapport détaillé.

IMPORTANT
---------
Aucune règle clinique spécifique n'est codée en dur.

Le corrector ne décide PAS qu'une correction est correcte.
Il applique uniquement une décision déjà validée.

ENTREE CLINIQUE
---------------
MultiAgent/
    ontology_relation_residual/
        ontology_relation_safe_corrected/

DECISIONS
---------
MultiAgent/
    ontology_relation_review/
        outputs/
            ontology_relation_review_validated.json

SORTIE
------
MultiAgent/
    ontology_relation_review/
        ontology_relation_review_safe_corrected/

RAPPORT
-------
ontology_relation_review_correction_report.json
"""

import os
import json
import shutil

from pathlib import Path
from collections import Counter


# =====================================================================
# 1. CONFIGURATION
# =====================================================================

ROOT = Path(__file__).resolve().parent
INPUT_CLINICAL_DIR = ROOT / "ontology_relation_safe_corrected"
VALIDATED_FILE = ROOT / "outputs" / "ontology_relation_review_validated.json"
OUTPUT_DIR = ROOT / "relation_validation_safe_corrected"
REPORT_FILE = OUTPUT_DIR / "ontology_relation_review_correction_report.json"


# =====================================================================
# 2. ACTIONS AUTORISEES
# =====================================================================

SAFE_ACTIONS = {
    "RETYPE_ENTITY",
    "INVERT_RELATION",
}


# =====================================================================
# 3. IO
# =====================================================================

def load_json(path):

    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(
            f"Fichier introuvable : {path}"
        )

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def dump_json(path, obj):

    path = Path(path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    path.write_text(
        json.dumps(
            obj,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


def clean(value):

    if value is None:
        return ""

    return str(value).strip()


def normalize_type(value):

    return clean(value).upper()


# =====================================================================
# 4. HELPERS ENTITES
# =====================================================================

def entity_id(entity):

    if not isinstance(entity, dict):
        return ""

    return clean(
        entity.get("identifiant_entite")
        or entity.get("id")
        or entity.get("entity_id")
    )


def entity_type(entity):

    if not isinstance(entity, dict):
        return ""

    return normalize_type(
        entity.get("type")
        or entity.get("categorie")
        or entity.get("entity_type")
    )


def entity_text(entity):

    if not isinstance(entity, dict):
        return ""

    for key in (
        "name",
        "preuve",
        "texte",
        "text",
        "libelle",
        "valeur",
        "parametre",
    ):

        value = entity.get(key)

        if value not in (
            None,
            ""
        ):
            return clean(value)

    return ""


# =====================================================================
# 5. HELPERS RELATIONS
# =====================================================================

def relation_id(relation):

    if not isinstance(relation, dict):
        return ""

    return clean(
        relation.get("identifiant_relation")
        or relation.get("id")
        or relation.get("relation_id")
    )


def relation_type(relation):

    if not isinstance(relation, dict):
        return ""

    return clean(
        relation.get("type_relation")
        or relation.get("relation")
        or relation.get("relation_type")
        or relation.get("predicate")
        or relation.get("type")
    )


def relation_source_id(relation):

    if not isinstance(relation, dict):
        return ""

    return clean(
        relation.get("identifiant_entite_sujet")
        or relation.get("subject_id")
        or relation.get("from_id")
        or relation.get("source_id")
        or relation.get("source")
    )


def relation_target_id(relation):

    if not isinstance(relation, dict):
        return ""

    return clean(
        relation.get("identifiant_entite_objet")
        or relation.get("object_id")
        or relation.get("to_id")
        or relation.get("target_id")
        or relation.get("target")
    )


# =====================================================================
# 6. EXTRACTION STRUCTURE CLINIQUE
# =====================================================================

def get_global_entities(doc):

    entities = doc.get(
        "global_entities"
    )

    if isinstance(
        entities,
        list
    ):
        return entities

    return []


def get_global_relations(doc):

    relations = doc.get(
        "global_relations"
    )

    if isinstance(
        relations,
        list
    ):
        return relations

    return []


def get_page_entities(doc):

    output = []

    pages = (
        doc.get("pages")
        or []
    )

    if not isinstance(
        pages,
        list
    ):
        return output

    for page_index, page in enumerate(
        pages
    ):

        if not isinstance(
            page,
            dict
        ):
            continue

        for key in (
            "entities",
            "entites",
        ):

            values = page.get(
                key
            )

            if isinstance(
                values,
                list
            ):

                for entity in values:

                    if isinstance(
                        entity,
                        dict
                    ):

                        output.append(
                            (
                                page_index,
                                key,
                                entity
                            )
                        )

    return output


def get_page_relations(doc):

    output = []

    pages = (
        doc.get("pages")
        or []
    )

    if not isinstance(
        pages,
        list
    ):
        return output

    for page_index, page in enumerate(
        pages
    ):

        if not isinstance(
            page,
            dict
        ):
            continue

        for key in (
            "relations",
            "relation",
        ):

            values = page.get(
                key
            )

            if isinstance(
                values,
                list
            ):

                for relation in values:

                    if isinstance(
                        relation,
                        dict
                    ):

                        output.append(
                            (
                                page_index,
                                key,
                                relation
                            )
                        )

    return output


# =====================================================================
# 7. INDEX DES ENTITES
# =====================================================================

def build_entity_occurrence_index(doc):

    """
    Retourne toutes les occurrences physiques d'une entité.

    Exemple :

        {
            "P1_E001": [
                {"location": "global", "entity": {...}},
                {"location": "page", "entity": {...}}
            ]
        }

    Cela permet de modifier global_entities ET pages si nécessaire.
    """

    index = {}

    # -------------------------------------------------------------
    # Global entities
    # -------------------------------------------------------------

    for entity in get_global_entities(
        doc
    ):

        eid = entity_id(
            entity
        )

        if not eid:
            continue

        index.setdefault(
            eid,
            []
        ).append(
            {
                "location": "global",
                "entity": entity,
            }
        )

    # -------------------------------------------------------------
    # Page entities
    # -------------------------------------------------------------

    for (
        page_index,
        container_key,
        entity
    ) in get_page_entities(
        doc
    ):

        eid = entity_id(
            entity
        )

        if not eid:
            continue

        index.setdefault(
            eid,
            []
        ).append(
            {
                "location": "page",
                "page_index": page_index,
                "container_key": container_key,
                "entity": entity,
            }
        )

    return index


# =====================================================================
# 8. INDEX DES RELATIONS
# =====================================================================

def build_relation_occurrence_index(doc):

    """
    Retourne toutes les occurrences physiques d'une relation.

    Cela permet de synchroniser global_relations et les relations
    éventuellement stockées dans pages.
    """

    index = {}

    # -------------------------------------------------------------
    # Global relations
    # -------------------------------------------------------------

    for relation in get_global_relations(
        doc
    ):

        rid = relation_id(
            relation
        )

        if not rid:
            continue

        index.setdefault(
            rid,
            []
        ).append(
            {
                "location": "global",
                "relation": relation,
            }
        )

    # -------------------------------------------------------------
    # Page relations
    # -------------------------------------------------------------

    for (
        page_index,
        container_key,
        relation
    ) in get_page_relations(
        doc
    ):

        rid = relation_id(
            relation
        )

        if not rid:
            continue

        index.setdefault(
            rid,
            []
        ).append(
            {
                "location": "page",
                "page_index": page_index,
                "container_key": container_key,
                "relation": relation,
            }
        )

    return index


# =====================================================================
# 9. EXTRACTION DES DECISIONS DU VALIDATOR
# =====================================================================

def extract_validated_cases(data):
    """
    Extrait la liste principale des décisions validées.

    La fonction reste générique :
    elle teste plusieurs noms de clés possibles afin de rester
    compatible avec différentes versions du validator.
    """

    possible_keys = (
        "validated_reviews",      # structure actuelle
        "validated_cases",
        "validated_relations",
        "validated_decisions",
        "validated_groups",
        "decisions",
        "results",
        "cases",
    )

    for key in possible_keys:
        value = data.get(key)

        if isinstance(value, list):
            return value

    return []


# =====================================================================
# 10. EXTRACTION GENERIQUE DES CHAMPS D'UNE DECISION
# =====================================================================

def decision_document(case):

    return clean(
        case.get("document")
        or case.get("document_name")
        or case.get("file")
        or case.get("filename")
    )


def decision_action(case):

    return clean(
        case.get("final_action")
        or case.get("action")
    ).upper()


def decision_entity_id(case):

    return clean(
        case.get("entity_id")
        or case.get("affected_entity_id")
    )


def decision_relation_id(case):

    return clean(
        case.get("relation_id")
        or case.get("affected_relation_id")
    )


def decision_new_type(case):

    return normalize_type(
        case.get("new_type")
        or case.get("proposed_new_type")
        or case.get("expected_type")
        or case.get("target_type")
    )


def decision_old_type(case):

    return normalize_type(
        case.get("current_type")
        or case.get("old_type")
        or case.get("actual_type")
        or case.get("entity_type")
    )


# =====================================================================
# 11. RETYPAGE GENERIQUE
# =====================================================================

def set_entity_type(
    entity,
    new_type
):

    """
    Met à jour les champs de type réellement présents.

    Pour la structure TRACE actuelle :
        categorie
        type

    Mais le script accepte également :
        entity_type

    Si aucun champ n'existe, on ajoute 'type'.
    """

    changed_fields = []

    existing_type_fields = []

    for key in (
        "categorie",
        "type",
        "entity_type",
    ):

        if key in entity:
            existing_type_fields.append(
                key
            )

    if not existing_type_fields:

        entity["type"] = new_type

        changed_fields.append(
            "type"
        )

        return changed_fields

    for key in existing_type_fields:

        old_value = normalize_type(
            entity.get(key)
        )

        if old_value != new_type:

            entity[key] = new_type

            changed_fields.append(
                key
            )

    return changed_fields


# =====================================================================
# 12. INVERSION GENERIQUE D'UNE RELATION
# =====================================================================

def invert_relation(
    relation,
    entity_index
):

    """
    Inverse les endpoints d'une relation :

        source <-> target

    et synchronise également les représentations textuelles
    lorsqu'elles existent.
    """

    old_source_id = relation_source_id(
        relation
    )

    old_target_id = relation_target_id(
        relation
    )

    if not old_source_id or not old_target_id:

        return {
            "success": False,
            "reason": "SOURCE_OR_TARGET_ID_MISSING",
        }

    # -------------------------------------------------------------
    # Modification des IDs
    # -------------------------------------------------------------

    source_keys = (
        "identifiant_entite_sujet",
        "subject_id",
        "from_id",
        "source_id",
    )

    target_keys = (
        "identifiant_entite_objet",
        "object_id",
        "to_id",
        "target_id",
    )

    source_fields_found = [
        key
        for key in source_keys
        if key in relation
    ]

    target_fields_found = [
        key
        for key in target_keys
        if key in relation
    ]

    # Structure inconnue
    if (
        not source_fields_found
        or not target_fields_found
    ):

        return {
            "success": False,
            "reason": "RELATION_ENDPOINT_FIELDS_NOT_RESOLVED",
        }

    for key in source_fields_found:

        relation[
            key
        ] = old_target_id

    for key in target_fields_found:

        relation[
            key
        ] = old_source_id

    # -------------------------------------------------------------
    # Récupération des textes des nouvelles extrémités
    # -------------------------------------------------------------

    new_source_text = ""

    new_target_text = ""

    target_occurrences = entity_index.get(
        old_target_id,
        []
    )

    source_occurrences = entity_index.get(
        old_source_id,
        []
    )

    if target_occurrences:

        new_source_text = entity_text(
            target_occurrences[0][
                "entity"
            ]
        )

    if source_occurrences:

        new_target_text = entity_text(
            source_occurrences[0][
                "entity"
            ]
        )

    # -------------------------------------------------------------
    # Synchronisation champs texte
    # -------------------------------------------------------------

    source_text_keys = (
        "entite_sujet",
        "subject",
        "source_text",
    )

    target_text_keys = (
        "entite_objet",
        "object",
        "target_text",
    )

    if new_source_text:

        for key in source_text_keys:

            if key in relation:

                relation[
                    key
                ] = new_source_text

    if new_target_text:

        for key in target_text_keys:

            if key in relation:

                relation[
                    key
                ] = new_target_text

    return {
        "success": True,
        "old_source_id": old_source_id,
        "old_target_id": old_target_id,
        "new_source_id": old_target_id,
        "new_target_id": old_source_id,
        "new_source_text": new_source_text,
        "new_target_text": new_target_text,
    }


# =====================================================================
# 13. COPIE DU CORPUS
# =====================================================================

def prepare_output_directory():

    if not INPUT_CLINICAL_DIR.exists():

        raise FileNotFoundError(
            "Corpus clinique source introuvable : "
            f"{INPUT_CLINICAL_DIR}"
        )

    # On évite de conserver des fichiers d'une ancienne exécution.
    if OUTPUT_DIR.exists():

        shutil.rmtree(
            OUTPUT_DIR
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    copied = 0

    for source_path in sorted(
        INPUT_CLINICAL_DIR.glob(
            "*.json"
        )
    ):

        # Ne pas recopier les rapports techniques.
        if source_path.name.endswith(
            "_report.json"
        ):
            continue

        destination = (
            OUTPUT_DIR
            / source_path.name
        )

        shutil.copy2(
            source_path,
            destination
        )

        copied += 1

    return copied


# =====================================================================
# 14. APPLICATION RETYPE_ENTITY
# =====================================================================

def apply_retype_entity(
    case,
    document_name,
    doc,
    entity_index
):

    eid = decision_entity_id(
        case
    )

    new_type = decision_new_type(
        case
    )

    expected_old_type = decision_old_type(
        case
    )

    if not eid:

        return {
            "status": "ERROR",
            "action": "RETYPE_ENTITY",
            "document": document_name,
            "reason": "ENTITY_ID_MISSING",
        }

    if not new_type:

        return {
            "status": "ERROR",
            "action": "RETYPE_ENTITY",
            "document": document_name,
            "entity_id": eid,
            "reason": "NEW_TYPE_MISSING",
        }

    occurrences = entity_index.get(
        eid,
        []
    )

    if not occurrences:

        return {
            "status": "ERROR",
            "action": "RETYPE_ENTITY",
            "document": document_name,
            "entity_id": eid,
            "new_type": new_type,
            "reason": "ENTITY_NOT_FOUND",
        }

    current_types = {
        entity_type(
            occurrence[
                "entity"
            ]
        )
        for occurrence in occurrences
        if entity_type(
            occurrence[
                "entity"
            ]
        )
    }

    # -------------------------------------------------------------
    # Sécurité : occurrences incohérentes
    # -------------------------------------------------------------

    if len(
        current_types
    ) > 1:

        return {
            "status": "SKIPPED_UNSAFE",
            "action": "RETYPE_ENTITY",
            "document": document_name,
            "entity_id": eid,
            "new_type": new_type,
            "current_types": sorted(
                current_types
            ),
            "reason": "MULTIPLE_CURRENT_TYPES",
        }

    actual_type = (
        next(
            iter(
                current_types
            )
        )
        if current_types
        else ""
    )

    # -------------------------------------------------------------
    # Vérification de l'ancien type annoncé
    # -------------------------------------------------------------

    if (
        expected_old_type
        and actual_type
        and expected_old_type
        != actual_type
    ):

        return {
            "status": "SKIPPED_UNSAFE",
            "action": "RETYPE_ENTITY",
            "document": document_name,
            "entity_id": eid,
            "expected_old_type": expected_old_type,
            "actual_type": actual_type,
            "new_type": new_type,
            "reason": "CURRENT_TYPE_CHANGED_SINCE_VALIDATION",
        }

    # -------------------------------------------------------------
    # Déjà corrigé
    # -------------------------------------------------------------

    if (
        actual_type
        == new_type
    ):

        return {
            "status": "ALREADY_APPLIED",
            "action": "RETYPE_ENTITY",
            "document": document_name,
            "entity_id": eid,
            "old_type": actual_type,
            "new_type": new_type,
            "physical_occurrences": len(
                occurrences
            ),
            "reason": "ENTITY_ALREADY_HAS_TARGET_TYPE",
        }

    # -------------------------------------------------------------
    # Application
    # -------------------------------------------------------------

    changed_occurrences = 0

    changed_fields = Counter()

    for occurrence in occurrences:

        fields = set_entity_type(
            occurrence[
                "entity"
            ],
            new_type
        )

        if fields:

            changed_occurrences += 1

            for field in fields:

                changed_fields[
                    field
                ] += 1

    return {
        "status": "APPLIED",
        "action": "RETYPE_ENTITY",
        "document": document_name,
        "entity_id": eid,
        "old_type": actual_type,
        "new_type": new_type,
        "physical_occurrences": len(
            occurrences
        ),
        "changed_occurrences": changed_occurrences,
        "changed_fields": dict(
            changed_fields
        ),
    }


# =====================================================================
# 15. APPLICATION INVERT_RELATION
# =====================================================================

def apply_invert_relation(
    case,
    document_name,
    doc,
    entity_index,
    relation_index
):

    rid = decision_relation_id(
        case
    )

    if not rid:

        return {
            "status": "ERROR",
            "action": "INVERT_RELATION",
            "document": document_name,
            "reason": "RELATION_ID_MISSING",
        }

    occurrences = relation_index.get(
        rid,
        []
    )

    if not occurrences:

        return {
            "status": "ERROR",
            "action": "INVERT_RELATION",
            "document": document_name,
            "relation_id": rid,
            "reason": "RELATION_NOT_FOUND",
        }

    # -------------------------------------------------------------
    # Vérification cohérence des occurrences physiques
    # -------------------------------------------------------------

    endpoint_pairs = {
        (
            relation_source_id(
                occurrence[
                    "relation"
                ]
            ),
            relation_target_id(
                occurrence[
                    "relation"
                ]
            )
        )
        for occurrence in occurrences
    }

    if len(
        endpoint_pairs
    ) > 1:

        return {
            "status": "SKIPPED_UNSAFE",
            "action": "INVERT_RELATION",
            "document": document_name,
            "relation_id": rid,
            "endpoint_pairs": [
                list(x)
                for x in endpoint_pairs
            ],
            "reason": "RELATION_OCCURRENCES_HAVE_DIFFERENT_ENDPOINTS",
        }

    old_source_id, old_target_id = next(
        iter(
            endpoint_pairs
        )
    )

    if (
        not old_source_id
        or not old_target_id
    ):

        return {
            "status": "ERROR",
            "action": "INVERT_RELATION",
            "document": document_name,
            "relation_id": rid,
            "reason": "SOURCE_OR_TARGET_ID_MISSING",
        }

    # -------------------------------------------------------------
    # Si le validator fournit les endpoints avant correction,
    # on vérifie qu'ils correspondent toujours.
    # -------------------------------------------------------------

    expected_source = clean(
        case.get("source_id")
        or case.get("current_source_id")
        or case.get("old_source_id")
    )

    expected_target = clean(
        case.get("target_id")
        or case.get("current_target_id")
        or case.get("old_target_id")
    )

    if (
        expected_source
        and expected_source
        != old_source_id
    ):

        return {
            "status": "SKIPPED_UNSAFE",
            "action": "INVERT_RELATION",
            "document": document_name,
            "relation_id": rid,
            "expected_source_id": expected_source,
            "actual_source_id": old_source_id,
            "reason": "SOURCE_CHANGED_SINCE_VALIDATION",
        }

    if (
        expected_target
        and expected_target
        != old_target_id
    ):

        return {
            "status": "SKIPPED_UNSAFE",
            "action": "INVERT_RELATION",
            "document": document_name,
            "relation_id": rid,
            "expected_target_id": expected_target,
            "actual_target_id": old_target_id,
            "reason": "TARGET_CHANGED_SINCE_VALIDATION",
        }

    # -------------------------------------------------------------
    # Application sur toutes les occurrences physiques
    # -------------------------------------------------------------

    changed_occurrences = 0

    results = []

    for occurrence in occurrences:

        result = invert_relation(
            occurrence[
                "relation"
            ],
            entity_index
        )

        results.append(
            result
        )

        if result.get(
            "success"
        ):
            changed_occurrences += 1

    if changed_occurrences != len(
        occurrences
    ):

        return {
            "status": "ERROR",
            "action": "INVERT_RELATION",
            "document": document_name,
            "relation_id": rid,
            "physical_occurrences": len(
                occurrences
            ),
            "changed_occurrences": changed_occurrences,
            "reason": "NOT_ALL_OCCURRENCES_COULD_BE_INVERTED",
            "details": results,
        }

    return {
        "status": "APPLIED",
        "action": "INVERT_RELATION",
        "document": document_name,
        "relation_id": rid,
        "relation_type": relation_type(
            occurrences[0][
                "relation"
            ]
        ),
        "old_source_id": old_source_id,
        "old_target_id": old_target_id,
        "new_source_id": old_target_id,
        "new_target_id": old_source_id,
        "physical_occurrences": len(
            occurrences
        ),
        "changed_occurrences": changed_occurrences,
    }


# =====================================================================
# 16. DEDUPLICATION DES OPERATIONS
# =====================================================================

def operation_key(case):

    action = decision_action(
        case
    )

    document = decision_document(
        case
    )

    if action == "RETYPE_ENTITY":

        return (
            action,
            document,
            decision_entity_id(
                case
            ),
            decision_new_type(
                case
            )
        )

    if action == "INVERT_RELATION":

        return (
            action,
            document,
            decision_relation_id(
                case
            )
        )

    return (
        action,
        document,
        json.dumps(
            case,
            ensure_ascii=False,
            sort_keys=True
        )
    )


def deduplicate_safe_operations(cases):

    unique = []

    seen = set()

    duplicates = 0

    for case in cases:

        action = decision_action(
            case
        )

        if action not in SAFE_ACTIONS:
            continue

        key = operation_key(
            case
        )

        if key in seen:

            duplicates += 1
            continue

        seen.add(
            key
        )

        unique.append(
            case
        )

    return (
        unique,
        duplicates
    )


# =====================================================================
# 17. MAIN
# =====================================================================

def main():

    print("=" * 120)

    print(
        "TRACE / SGCE - ONTOLOGY RELATION REVIEW SAFE CORRECTOR V1 "
        "- GENERIC VALIDATOR-DRIVEN"
    )

    print("=" * 120)

    # =================================================================
    # Vérification des entrées
    # =================================================================

    if not VALIDATED_FILE.exists():

        raise FileNotFoundError(
            "Fichier de validation introuvable : "
            f"{VALIDATED_FILE}"
        )

    if not INPUT_CLINICAL_DIR.exists():

        raise FileNotFoundError(
            "Corpus clinique source introuvable : "
            f"{INPUT_CLINICAL_DIR}"
        )

    # =================================================================
    # Charger validator
    # =================================================================

    validated_data = load_json(
        VALIDATED_FILE
    )

    cases = extract_validated_cases(
        validated_data
    )

    # =================================================================
    # Actions SAFE uniquement
    # =================================================================

    safe_cases = [
        case
        for case in cases
        if decision_action(
            case
        )
        in SAFE_ACTIONS
    ]

    (
        operations,
        duplicate_operations
    ) = deduplicate_safe_operations(
        safe_cases
    )

    # =================================================================
    # Copier corpus
    # =================================================================

    copied_documents = (
        prepare_output_directory()
    )

    # =================================================================
    # Counters
    # =================================================================

    status_counter = Counter()

    action_counter = Counter()

    applied_action_counter = Counter()

    document_counter = Counter()

    type_changes = Counter()

    relation_inversions = Counter()

    operation_reports = []

    modified_documents = set()

    errors = []

    # =================================================================
    # Grouper opérations par document
    # =================================================================

    operations_by_document = {}

    for case in operations:

        document = decision_document(
            case
        )

        if not document:

            report = {
                "status": "ERROR",
                "action": decision_action(
                    case
                ),
                "reason": "DOCUMENT_MISSING_IN_VALIDATOR_DECISION",
            }

            operation_reports.append(
                report
            )

            errors.append(
                report
            )

            status_counter[
                "ERROR"
            ] += 1

            continue

        operations_by_document.setdefault(
            document,
            []
        ).append(
            case
        )

    # =================================================================
    # Traitement document par document
    # =================================================================

    for (
        document_name,
        document_operations
    ) in operations_by_document.items():

        document_path = (
            OUTPUT_DIR
            / document_name
        )

        if not document_path.exists():

            for case in document_operations:

                report = {
                    "status": "ERROR",
                    "action": decision_action(
                        case
                    ),
                    "document": document_name,
                    "reason": "CLINICAL_DOCUMENT_NOT_FOUND",
                }

                operation_reports.append(
                    report
                )

                errors.append(
                    report
                )

                status_counter[
                    "ERROR"
                ] += 1

            continue

        # -------------------------------------------------------------
        # Charger document
        # -------------------------------------------------------------

        try:

            doc = load_json(
                document_path
            )

        except Exception as exc:

            for case in document_operations:

                report = {
                    "status": "ERROR",
                    "action": decision_action(
                        case
                    ),
                    "document": document_name,
                    "reason": "DOCUMENT_LOAD_ERROR",
                    "error": str(
                        exc
                    ),
                }

                operation_reports.append(
                    report
                )

                errors.append(
                    report
                )

                status_counter[
                    "ERROR"
                ] += 1

            continue

        # -------------------------------------------------------------
        # Construire index
        # -------------------------------------------------------------

        entity_index = (
            build_entity_occurrence_index(
                doc
            )
        )

        relation_index = (
            build_relation_occurrence_index(
                doc
            )
        )

        document_modified = False

        # -------------------------------------------------------------
        # Appliquer opérations
        # -------------------------------------------------------------

        for case in document_operations:

            action = decision_action(
                case
            )

            action_counter[
                action
            ] += 1

            if action == "RETYPE_ENTITY":

                report = apply_retype_entity(
                    case,
                    document_name,
                    doc,
                    entity_index
                )

            elif action == "INVERT_RELATION":

                report = apply_invert_relation(
                    case,
                    document_name,
                    doc,
                    entity_index,
                    relation_index
                )

            else:

                report = {
                    "status": "SKIPPED_UNSAFE",
                    "action": action,
                    "document": document_name,
                    "reason": "ACTION_NOT_WHITELISTED",
                }

            # ---------------------------------------------------------
            # Counters
            # ---------------------------------------------------------

            status = clean(
                report.get(
                    "status"
                )
            )

            status_counter[
                status
            ] += 1

            operation_reports.append(
                report
            )

            if status == "APPLIED":

                document_modified = True

                applied_action_counter[
                    action
                ] += 1

                if action == "RETYPE_ENTITY":

                    transition = (
                        report.get(
                            "old_type"
                        ),
                        report.get(
                            "new_type"
                        )
                    )

                    type_changes[
                        transition
                    ] += 1

                elif action == "INVERT_RELATION":

                    relation_inversions[
                        report.get(
                            "relation_type"
                        )
                        or "UNKNOWN"
                    ] += 1

            if status == "ERROR":

                errors.append(
                    report
                )

        # -------------------------------------------------------------
        # Sauvegarder seulement après toutes les opérations du document
        # -------------------------------------------------------------

        if document_modified:

            dump_json(
                document_path,
                doc
            )

            modified_documents.add(
                document_name
            )

            document_counter[
                document_name
            ] += 1

    # =================================================================
    # Rapport
    # =================================================================

    report = {

        "corrector":
            "ontology_relation_review_safe_corrector",

        "version":
            "V1_GENERIC_VALIDATOR_DRIVEN",

        "mode":
            "SAFE_CORRECTION",

        "input_clinical_directory":
            str(
                INPUT_CLINICAL_DIR
            ),

        "validated_decisions_file":
            str(
                VALIDATED_FILE
            ),

        "output_clinical_directory":
            str(
                OUTPUT_DIR
            ),

        "summary": {

            "validated_cases_received":
                len(
                    cases
                ),

            "safe_cases_detected":
                len(
                    safe_cases
                ),

            "unique_operations":
                len(
                    operations
                ),

            "duplicate_operations_ignored":
                duplicate_operations,

            "clinical_documents_copied":
                copied_documents,

            "documents_modified":
                len(
                    modified_documents
                ),

            "status_counts":
                dict(
                    status_counter
                ),

            "requested_action_counts":
                dict(
                    action_counter
                ),

            "applied_action_counts":
                dict(
                    applied_action_counter
                ),

            "errors":
                len(
                    errors
                ),
        },

        "type_changes": [

            {
                "from_type": old_type,
                "to_type": new_type,
                "count": count,
            }

            for (
                old_type,
                new_type
            ), count
            in type_changes.most_common()
        ],

        "relation_inversions": [

            {
                "relation_type": relation_name,
                "count": count,
            }

            for (
                relation_name,
                count
            )
            in relation_inversions.most_common()
        ],

        "modified_documents":
            sorted(
                modified_documents
            ),

        "operations":
            operation_reports,

        "errors":
            errors,
    }

    dump_json(
        REPORT_FILE,
        report
    )

    # =================================================================
    # AFFICHAGE
    # =================================================================

    print(
        f"Cas validés reçus                   : "
        f"{len(cases)}"
    )

    print(
        f"Actions SAFE détectées              : "
        f"{len(safe_cases)}"
    )

    print(
        f"Opérations uniques                  : "
        f"{len(operations)}"
    )

    print(
        f"Doublons ignorés                    : "
        f"{duplicate_operations}"
    )

    print(
        f"Documents cliniques copiés          : "
        f"{copied_documents}"
    )

    print()

    print(
        "ACTIONS SAFE DEMANDEES"
    )

    print("-" * 120)

    if action_counter:

        for (
            action,
            count
        ) in action_counter.most_common():

            print(
                f"{action:<60}: {count}"
            )

    else:

        print(
            "Aucune action SAFE."
        )

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
                f"{status:<60}: {count}"
            )

    else:

        print(
            "Aucune opération."
        )

    print()

    print(
        "CORRECTIONS APPLIQUEES"
    )

    print("-" * 120)

    print(
        f"RETYPE_ENTITY                       : "
        f"{applied_action_counter.get('RETYPE_ENTITY', 0)}"
    )

    print(
        f"INVERT_RELATION                     : "
        f"{applied_action_counter.get('INVERT_RELATION', 0)}"
    )

    print()

    print(
        "RETYPAGES"
    )

    print("-" * 120)

    if type_changes:

        for (
            old_type,
            new_type
        ), count in type_changes.most_common():

            transition = (
                f"{old_type} -> {new_type}"
            )

            print(
                f"{transition:<60}: {count}"
            )

    else:

        print(
            "Aucun retypage appliqué."
        )

    print()

    print(
        "INVERSIONS DE RELATIONS"
    )

    print("-" * 120)

    if relation_inversions:

        for (
            relation_name,
            count
        ) in relation_inversions.most_common():

            print(
                f"{relation_name:<60}: {count}"
            )

    else:

        print(
            "Aucune relation inversée."
        )

    print()

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
            "ATTENTION : certaines opérations n'ont pas "
            "pu être appliquées."
        )

        print(
            "Consulter le rapport avant de poursuivre."
        )

    else:

        print(
            "Toutes les corrections SAFE validées ont été "
            "traitées sans erreur."
        )

    print()

    print(
        "Les fichiers sources n'ont pas été modifiés."
    )


# =====================================================================
# 18. ENTRY POINT
# =====================================================================

if __name__ == "__main__":
    main()