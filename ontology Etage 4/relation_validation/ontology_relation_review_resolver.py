# -*- coding: utf-8 -*-

"""
TRACE / SGCE - ONTOLOGY RELATION REVIEW RESOLVER V2
REAL TRACE JSON STRUCTURE - POST SAFE-REMOVAL

Objectif
--------
Analyser les anomalies relationnelles résiduelles après :
1. retypage ontologique SAFE des entités ;
2. suppression des relations SAFE_REMOVE ;
3. nouvel audit ontologique.

Le script distingue notamment :
- POSSIBLE_RELATION_INVERSION
- POSSIBLE_ENDPOINT_MISTYPING
- RELATION_SCHEMA_MISMATCH
- VALID_BUT_GUIDELINE_TOO_STRICT
- NEGATION_SENSITIVE
- UNRESOLVED

IMPORTANT
---------
- Aucune donnée clinique n'est modifiée.
- Aucune relation n'est inversée automatiquement.
- Aucun type d'entité n'est modifié automatiquement.
- Une violation domain/range n'est pas automatiquement une hallucination.
"""

# GENERICITY PATCH: TRACE_BASE_DIR can be supplied through the environment.

import csv
import os
import json
import re

from pathlib import Path
from collections import Counter, defaultdict


# =====================================================================
# CONFIGURATION
# =====================================================================

ROOT = Path(__file__).resolve().parent

CLINICAL_DIR = ROOT / "ontology_relation_safe_corrected"
AUDIT_DIR = ROOT / "audit_after_safe_remove"
ANOMALIES_CSV = AUDIT_DIR / "final_ontology_anomalies.csv"

OUTPUT_DIR = ROOT / "outputs"
OUTPUT_JSON = OUTPUT_DIR / "ontology_relation_review_resolved.json"
OUTPUT_CSV = OUTPUT_DIR / "ontology_relation_review_resolved.csv"
OUTPUT_TXT = OUTPUT_DIR / "ontology_relation_review_summary.txt"


# =====================================================================
# CONSTANTES
# =====================================================================

RELATION_ANOMALIES = {
    "INVALID_RELATION_SOURCE_TYPE",
    "INVALID_RELATION_TARGET_TYPE",
}

PATIENT_TERMS = set()  # version générique: aucun lexique métier codé en dur

NEGATION_PATTERNS = [
    r"\bpas de\b",
    r"\babsence de\b",
    r"\bsans\b",
    r"\baucun\b",
    r"\baucune\b",
    r"\bnon\b",
    r"\bnégatif\b",
    r"\bnegatif\b",
    r"\bnégative\b",
    r"\bnegative\b",
    r"\bni\b",
]


# =====================================================================
# UTILITAIRES
# =====================================================================

def norm(value):
    if value is None:
        return ""
    return str(value).strip()


def norm_lower(value):
    return norm(value).lower()


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


def read_csv(path):
    with Path(path).open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:
        return list(csv.DictReader(f))


# =====================================================================
# STRUCTURE RELATION TRACE
# =====================================================================

def get_relation_id(rel):
    if not isinstance(rel, dict):
        return ""

    return norm(
        rel.get("identifiant_relation")
        or rel.get("relation_id")
        or rel.get("id_relation")
        or rel.get("id")
    )


def get_relation_type(rel):
    if not isinstance(rel, dict):
        return ""

    return norm(
        rel.get("type_relation")
        or rel.get("relation_name")
        or rel.get("relation")
        or rel.get("predicate")
    )


def get_source_id(rel):
    if not isinstance(rel, dict):
        return ""

    return norm(
        rel.get("identifiant_entite_sujet")
        or rel.get("source_id")
        or rel.get("subject_id")
    )


def get_target_id(rel):
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
# STRUCTURE ENTITE TRACE REELLE
# =====================================================================

def get_entity_id(entity):
    """
    Structure réelle observée :
        identifiant_entite = P2_E029
    """

    if not isinstance(entity, dict):
        return ""

    return norm(
        entity.get("identifiant_entite")
        or entity.get("entity_id")
        or entity.get("id_entite")
        or entity.get("id")
    )


def entity_type(entity):
    """
    Type ontologique FINAL.

    IMPORTANT :
    priorité à `type`.

    Exemple réel :
        categorie = DONNEE_PATIENT
        type      = SYMPTOME

    Dans l'étage ontologique, SYMPTOME est le type à utiliser.
    """

    if not isinstance(entity, dict):
        return ""

    return norm(
        entity.get("type")
        or entity.get("type_entite")
        or entity.get("entity_type")
        or entity.get("categorie")
        or entity.get("label")
    )


def entity_category(entity):
    """
    Conserve aussi la catégorie originale pour analyse.
    """

    if not isinstance(entity, dict):
        return ""

    return norm(
        entity.get("categorie")
    )


def entity_text(entity):
    """
    Surface clinique représentative.

    Dans TRACE réel :
        name = surface normalisée/finale
        preuve = preuve textuelle
        parametre = paramètre structuré

    Priorité à name.
    """

    if not isinstance(entity, dict):
        return ""

    candidates = [
        entity.get("name"),
        entity.get("texte"),
        entity.get("text"),
        entity.get("entite"),
        entity.get("entity_text"),
        entity.get("mention"),
        entity.get("preuve"),
        entity.get("valeur"),
        entity.get("parametre"),
        entity.get("nom"),
    ]

    for value in candidates:
        value = norm(value)

        if value:
            return value

    return ""


def entity_proof(entity):
    if not isinstance(entity, dict):
        return ""

    return norm(
        entity.get("preuve")
    )


def entity_parameter(entity):
    if not isinstance(entity, dict):
        return ""

    return norm(
        entity.get("parametre")
    )


def entity_negated(entity):
    """
    TRACE réel utilise notamment :
        nie: false
    """

    if not isinstance(entity, dict):
        return False

    value = entity.get("nie")

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in {
            "true",
            "1",
            "yes",
            "oui"
        }

    return False


# =====================================================================
# INDEXATION TRACE
# =====================================================================

def collect_trace_objects(
    obj,
    path="$",
    entities=None,
    relations=None
):
    """
    Parcours récursif du JSON.

    Compatible avec :
    - global_entities
    - global_relations
    - structures par page
    - copies physiques éventuelles

    La même entité peut apparaître plusieurs fois.
    """

    if entities is None:
        entities = []

    if relations is None:
        relations = []

    if isinstance(obj, dict):

        # -------------------------------------------------------------
        # Détection relation
        # -------------------------------------------------------------

        relation_id = get_relation_id(obj)

        if (
            relation_id
            and (
                "type_relation" in obj
                or "identifiant_entite_sujet" in obj
                or "identifiant_entite_objet" in obj
            )
        ):
            relations.append({
                "path": path,
                "data": obj
            })

        # -------------------------------------------------------------
        # Détection entité TRACE réelle
        # -------------------------------------------------------------

        entity_id = get_entity_id(obj)

        ent_type = entity_type(obj)

        # Empêcher qu'une relation soit prise pour une entité
        is_relation = bool(
            relation_id
            and (
                "identifiant_entite_sujet" in obj
                or "identifiant_entite_objet" in obj
                or "type_relation" in obj
            )
        )

        if (
            entity_id
            and ent_type
            and not is_relation
        ):
            entities.append({
                "path": path,
                "data": obj
            })

        # -------------------------------------------------------------
        # Récursion
        # -------------------------------------------------------------

        for key, value in obj.items():
            collect_trace_objects(
                value,
                f"{path}.{key}",
                entities,
                relations
            )

    elif isinstance(obj, list):

        for i, item in enumerate(obj):
            collect_trace_objects(
                item,
                f"{path}[{i}]",
                entities,
                relations
            )

    return entities, relations


# =====================================================================
# INDEX DOCUMENT
# =====================================================================

def build_document_index(data):

    entities, relations = collect_trace_objects(data)

    entity_index = defaultdict(list)
    relation_index = defaultdict(list)

    for item in entities:

        entity = item["data"]

        eid = get_entity_id(entity)

        if eid:
            entity_index[eid].append(item)

    for item in relations:

        rel = item["data"]

        rid = get_relation_id(rel)

        if rid:
            relation_index[rid].append(item)

    return entity_index, relation_index


# =====================================================================
# PREUVE RELATION
# =====================================================================

def relation_proof(rel):

    if not isinstance(rel, dict):
        return ""

    return norm(
        rel.get("preuve")
        or rel.get("proof")
        or rel.get("evidence")
        or rel.get("contexte")
    )


def relation_note(rel):

    if not isinstance(rel, dict):
        return ""

    return norm(
        rel.get("note_clinique")
        or rel.get("note")
    )


# =====================================================================
# NEGATION
# =====================================================================

def has_negation(text):

    text = norm_lower(text)

    if not text:
        return False

    for pattern in NEGATION_PATTERNS:

        if re.search(
            pattern,
            text,
            flags=re.IGNORECASE
        ):
            return True

    return False


# =====================================================================
# PATIENT
# =====================================================================

def is_explicit_patient(text):

    text = norm_lower(text)

    if not text:
        return False

    if text in PATIENT_TERMS:
        return True

    # Exemple :
    # "Le patient | patient"
    pieces = [
        part.strip()
        for part in text.split("|")
        if part.strip()
    ]

    if any(
        part in PATIENT_TERMS
        for part in pieces
    ):
        return True

    return False


# =====================================================================
# TYPE SUPPORT
# =====================================================================

def type_matches_expected(
    actual_type,
    expected_type
):
    actual_type = norm(actual_type)
    expected_type = norm(expected_type)

    if not actual_type or not expected_type:
        return False

    return actual_type == expected_type


# =====================================================================
# INVERSION
# =====================================================================

def detect_possible_inversion(
    relation_name,
    source_text,
    source_type,
    target_text,
    target_type,
    anomaly_type,
    expected_type
):
    """
    Détection conservatrice d'une inversion potentielle.

    ATTENTION :
    cette fonction ne corrige rien.

    Elle produit seulement :
        POSSIBLE_RELATION_INVERSION
    """

    relation_name = norm(relation_name)

    source_type = norm(source_type)
    target_type = norm(target_type)

    expected_type = norm(expected_type)

    # =============================================================
    # 1. presente_symptome
    #
    # attendu conceptuellement :
    # patient -> symptôme
    #
    # Cas observé :
    # symptôme -> patient
    # =============================================================

    if relation_name == "presente_symptome":

        if (
            source_type == "SYMPTOME"
            and target_type == "DONNEE_PATIENT"
            and is_explicit_patient(target_text)
        ):
            return True

    # =============================================================
    # 2. presente_dysfonction_organe
    #
    # attendu :
    # patient -> défaillance
    # =============================================================

    if relation_name == "presente_dysfonction_organe":

        if (
            source_type == "DEFAILLANCE_ORGANE"
            and target_type == "DONNEE_PATIENT"
            and is_explicit_patient(target_text)
        ):
            return True

    # =============================================================
    # 3. a_pour_label_nosologique
    #
    # attendu :
    # patient -> label
    # =============================================================

    if relation_name == "a_pour_label_nosologique":

        if (
            source_type == "LABEL_NOSOLOGIQUE"
            and target_type == "DONNEE_PATIENT"
            and is_explicit_patient(target_text)
        ):
            return True

    # =============================================================
    # 4. Heuristique générique limitée
    #
    # Si l'anomalie concerne la TARGET et que la SOURCE possède
    # exactement le type attendu pour la TARGET, cela peut signaler
    # une inversion.
    #
    # Ce n'est PAS suffisant pour corriger automatiquement.
    # =============================================================

    if (
        anomaly_type == "INVALID_RELATION_TARGET_TYPE"
        and expected_type
        and source_type == expected_type
    ):
        return True

    # Même principe pour SOURCE
    if (
        anomaly_type == "INVALID_RELATION_SOURCE_TYPE"
        and expected_type
        and target_type == expected_type
    ):
        return True

    return False


# =====================================================================
# CLASSIFICATION
# =====================================================================

def classify_case(
    row,
    relation,
    source_entity,
    target_entity
):

    anomaly_type = norm(
        row.get("type")
    )

    relation_name = (
        get_relation_type(relation)
        or norm(row.get("relation_type"))
    )

    source_type = entity_type(
        source_entity
    )

    target_type = entity_type(
        target_entity
    )

    source_text = entity_text(
        source_entity
    )

    target_text = entity_text(
        target_entity
    )

    # Fallback relation
    if not source_text:
        source_text = get_source_text(
            relation
        )

    if not target_text:
        target_text = get_target_text(
            relation
        )

    # Fallback audit
    audit_entity_text = norm(
        row.get("entity_text")
    )

    expected_type = norm(
        row.get("expected_type")
    )

    actual_type = norm(
        row.get("actual_type")
    )

    proof = relation_proof(
        relation
    )

    note = relation_note(
        relation
    )

    # =============================================================
    # ENDPOINT AFFECTE
    # =============================================================

    if anomaly_type == "INVALID_RELATION_SOURCE_TYPE":

        affected_entity = source_entity
        affected_text = source_text
        affected_type = source_type

    elif anomaly_type == "INVALID_RELATION_TARGET_TYPE":

        affected_entity = target_entity
        affected_text = target_text
        affected_type = target_type

    else:

        affected_entity = {}
        affected_text = audit_entity_text
        affected_type = actual_type

    # =============================================================
    # 1. ENDPOINTS NON RESOLUS
    # =============================================================

    if not source_entity or not target_entity:

        return {
            "resolution": "UNRESOLVED",
            "proposed_action": "REVIEW",
            "confidence": 0.0,
            "reason": (
                "Au moins un endpoint de la relation "
                "n'a pas été retrouvé dans la structure TRACE."
            )
        }

    # =============================================================
    # 2. NEGATION
    # =============================================================

    if (
        entity_negated(source_entity)
        or entity_negated(target_entity)
        or has_negation(proof)
        or has_negation(note)
    ):

        return {
            "resolution": "NEGATION_SENSITIVE",
            "proposed_action": "REVIEW_NEGATION",
            "confidence": 0.95,
            "reason": (
                "La relation ou l'un de ses endpoints présente "
                "un signal de négation. Aucun changement "
                "automatique n'est autorisé."
            )
        }

    # =============================================================
    # 3. POSSIBLE INVERSION
    # =============================================================

    if detect_possible_inversion(
        relation_name=relation_name,
        source_text=source_text,
        source_type=source_type,
        target_text=target_text,
        target_type=target_type,
        anomaly_type=anomaly_type,
        expected_type=expected_type
    ):

        return {
            "resolution": "POSSIBLE_RELATION_INVERSION",
            "proposed_action": "PROPOSE_INVERT_RELATION",
            "confidence": 0.90,
            "reason": (
                "L'orientation actuelle de la relation paraît "
                "incompatible avec les types de ses endpoints, "
                "alors que le sens inverse est sémantiquement "
                "plausible. Une validation indépendante est "
                "requise avant toute inversion."
            )
        }

    # =============================================================
    # 4. PATIENT FORTEMENT ANCRE
    # =============================================================

    if (
        is_explicit_patient(affected_text)
        and affected_type == "DONNEE_PATIENT"
        and expected_type
        and expected_type != "DONNEE_PATIENT"
    ):

        return {
            "resolution": "RELATION_SCHEMA_MISMATCH",
            "proposed_action": "REVIEW_RELATION",
            "confidence": 0.99,
            "reason": (
                "L'endpoint est explicitement une mention du "
                "patient et son type DONNEE_PATIENT est fortement "
                "ancré. Il ne doit pas être retypé uniquement "
                "pour satisfaire le domain/range de la relation."
            )
        }

    # =============================================================
    # 5. LE TYPE REEL EST DEJA LE TYPE ATTENDU
    #
    # Important si l'audit a été construit avec une ancienne
    # représentation ou si categorie/type divergent.
    # =============================================================

    if (
        expected_type
        and type_matches_expected(
            affected_type,
            expected_type
        )
    ):

        return {
            "resolution": "AUDIT_TYPE_ALREADY_CORRECT",
            "proposed_action": "RECHECK_AUDIT",
            "confidence": 0.99,
            "reason": (
                "Le type ontologique final de l'endpoint dans "
                "le JSON TRACE correspond déjà au type attendu. "
                "L'anomalie doit être revérifiée au niveau de "
                "l'audit plutôt que corrigée dans la donnée."
            )
        }

    # =============================================================
    # 6. POSSIBLE ENDPOINT MISTYPING
    # =============================================================

    if (
        expected_type
        and affected_type
        and affected_type != expected_type
    ):

        # Patient protégé traité plus haut.
        # Ici on ne fait qu'une proposition de revue.

        return {
            "resolution": "POSSIBLE_ENDPOINT_MISTYPING",
            "proposed_action": "REVIEW_ENTITY_TYPE",
            "confidence": 0.60,
            "reason": (
                "Le type ontologique final de l'endpoint reste "
                "incompatible avec le type attendu par la relation. "
                "Les preuves disponibles ne sont toutefois pas "
                "suffisantes pour autoriser un retypage automatique."
            )
        }

    # =============================================================
    # 7. PREUVE DOCUMENTAIRE MAIS SCHEMA INCOMPATIBLE
    # =============================================================

    if proof:

        return {
            "resolution": "VALID_BUT_GUIDELINE_TOO_STRICT",
            "proposed_action": "REVIEW_GUIDELINE",
            "confidence": 0.50,
            "reason": (
                "La relation possède une preuve documentaire, "
                "mais sa signature reste incompatible avec le "
                "schéma TRACE. Le guideline doit être examiné "
                "avant toute modification de la donnée clinique."
            )
        }

    # =============================================================
    # 8. NON RESOLU
    # =============================================================

    return {
        "resolution": "UNRESOLVED",
        "proposed_action": "REVIEW",
        "confidence": 0.0,
        "reason": (
            "Les informations disponibles ne permettent pas "
            "de déterminer de manière suffisamment sûre si "
            "l'anomalie vient de l'entité, de la relation ou "
            "du schéma ontologique."
        )
    }


# =====================================================================
# MAIN
# =====================================================================

def main():

    print("=" * 120)

    print(
        "TRACE / SGCE - "
        "ONTOLOGY RELATION REVIEW RESOLVER V2 "
        "- REAL TRACE JSON STRUCTURE"
    )

    print("=" * 120)

    # =================================================================
    # VERIFICATION ENTREES
    # =================================================================

    if not CLINICAL_DIR.exists():

        raise RuntimeError(
            f"Dossier clinique introuvable : {CLINICAL_DIR}"
        )

    if not ANOMALIES_CSV.exists():

        raise RuntimeError(
            f"CSV anomalies introuvable : {ANOMALIES_CSV}"
        )

    # =================================================================
    # AUDIT
    # =================================================================

    rows = read_csv(
        ANOMALIES_CSV
    )

    relation_rows = [
        row
        for row in rows
        if norm(row.get("type"))
        in RELATION_ANOMALIES
    ]

    print(
        f"Anomalies totales audit             : "
        f"{len(rows)}"
    )

    print(
        f"Anomalies relationnelles reçues     : "
        f"{len(relation_rows)}"
    )

    # =================================================================
    # CACHE
    # =================================================================

    document_cache = {}
    index_cache = {}

    missing_documents = set()

    # =================================================================
    # COMPTEURS
    # =================================================================

    results = []

    resolution_counter = Counter()
    action_counter = Counter()
    relation_counter = Counter()
    anomaly_counter = Counter()

    unresolved_relations = 0
    unresolved_sources = 0
    unresolved_targets = 0

    relations_found = 0
    sources_found = 0
    targets_found = 0

    # =================================================================
    # TRAITEMENT
    # =================================================================

    for i, row in enumerate(
        relation_rows,
        start=1
    ):

        document = norm(
            row.get("document")
        )

        anomaly_type = norm(
            row.get("type")
        )

        relation_id = norm(
            row.get("relation_id")
        )

        source_id = norm(
            row.get("source_id")
        )

        target_id = norm(
            row.get("target_id")
        )

        path = (
            CLINICAL_DIR
            / document
        )

        # -------------------------------------------------------------
        # DOCUMENT MANQUANT
        # -------------------------------------------------------------

        if not path.exists():

            missing_documents.add(
                document
            )

            result = {
                "review_id": f"ORR_REVIEW_{i:05d}",
                "document": document,
                "anomaly_type": anomaly_type,
                "relation_id": relation_id,
                "source_id": source_id,
                "target_id": target_id,
                "resolution": "UNRESOLVED",
                "proposed_action": "REVIEW",
                "confidence": 0.0,
                "reason": "Document clinique introuvable."
            }

            results.append(result)

            resolution_counter[
                "UNRESOLVED"
            ] += 1

            action_counter[
                "REVIEW"
            ] += 1

            continue

        # -------------------------------------------------------------
        # CHARGEMENT/CACHE
        # -------------------------------------------------------------

        if document not in document_cache:

            data = load_json(
                path
            )

            document_cache[
                document
            ] = data

            index_cache[
                document
            ] = build_document_index(
                data
            )

        entity_index, relation_index = (
            index_cache[document]
        )

        # -------------------------------------------------------------
        # RELATION
        # -------------------------------------------------------------

        rel_occurrences = (
            relation_index.get(
                relation_id,
                []
            )
        )

        if rel_occurrences:

            relations_found += 1

            relation = (
                rel_occurrences[0]["data"]
            )

            relation_path = (
                rel_occurrences[0]["path"]
            )

        else:

            relation = {}
            relation_path = ""

            unresolved_relations += 1

        # -------------------------------------------------------------
        # SOURCE
        # -------------------------------------------------------------

        source_occurrences = (
            entity_index.get(
                source_id,
                []
            )
        )

        if source_occurrences:

            sources_found += 1

            source_entity = (
                source_occurrences[0]["data"]
            )

            source_path = (
                source_occurrences[0]["path"]
            )

        else:

            source_entity = {}
            source_path = ""

            unresolved_sources += 1

        # -------------------------------------------------------------
        # TARGET
        # -------------------------------------------------------------

        target_occurrences = (
            entity_index.get(
                target_id,
                []
            )
        )

        if target_occurrences:

            targets_found += 1

            target_entity = (
                target_occurrences[0]["data"]
            )

            target_path = (
                target_occurrences[0]["path"]
            )

        else:

            target_entity = {}
            target_path = ""

            unresolved_targets += 1

        # -------------------------------------------------------------
        # INFORMATIONS REELLES
        # -------------------------------------------------------------

        relation_name = (
            get_relation_type(relation)
            or norm(row.get("relation_type"))
        )

        source_text = (
            entity_text(source_entity)
            or get_source_text(relation)
        )

        target_text = (
            entity_text(target_entity)
            or get_target_text(relation)
        )

        source_type = entity_type(
            source_entity
        )

        target_type = entity_type(
            target_entity
        )

        # -------------------------------------------------------------
        # CLASSIFICATION
        # -------------------------------------------------------------

        decision = classify_case(
            row=row,
            relation=relation,
            source_entity=source_entity,
            target_entity=target_entity
        )

        # -------------------------------------------------------------
        # RESULTAT
        # -------------------------------------------------------------

        result = {

            "review_id":
                f"ORR_REVIEW_{i:05d}",

            "document":
                document,

            "anomaly_type":
                anomaly_type,

            "relation_id":
                relation_id,

            "relation_name":
                relation_name,

            "relation_path":
                relation_path,

            "relation_occurrences":
                len(rel_occurrences),

            # SOURCE
            "source_id":
                source_id,

            "source_text":
                source_text,

            "source_type":
                source_type,

            "source_category":
                entity_category(
                    source_entity
                ),

            "source_parameter":
                entity_parameter(
                    source_entity
                ),

            "source_proof":
                entity_proof(
                    source_entity
                ),

            "source_negated":
                entity_negated(
                    source_entity
                ),

            "source_path":
                source_path,

            "source_occurrences":
                len(source_occurrences),

            # TARGET
            "target_id":
                target_id,

            "target_text":
                target_text,

            "target_type":
                target_type,

            "target_category":
                entity_category(
                    target_entity
                ),

            "target_parameter":
                entity_parameter(
                    target_entity
                ),

            "target_proof":
                entity_proof(
                    target_entity
                ),

            "target_negated":
                entity_negated(
                    target_entity
                ),

            "target_path":
                target_path,

            "target_occurrences":
                len(target_occurrences),

            # AUDIT
            "audit_entity_id":
                norm(
                    row.get("entity_id")
                ),

            "audit_entity_text":
                norm(
                    row.get("entity_text")
                ),

            "audit_actual_type":
                norm(
                    row.get("actual_type")
                ),

            "expected_type":
                norm(
                    row.get("expected_type")
                ),

            "audit_details":
                norm(
                    row.get("details")
                ),

            # RELATION CONTEXT
            "relation_proof":
                relation_proof(
                    relation
                ),

            "relation_note":
                relation_note(
                    relation
                ),

            # DECISION
            "resolution":
                decision["resolution"],

            "proposed_action":
                decision["proposed_action"],

            "confidence":
                decision["confidence"],

            "reason":
                decision["reason"]
        }

        results.append(
            result
        )

        resolution_counter[
            result["resolution"]
        ] += 1

        action_counter[
            result["proposed_action"]
        ] += 1

        relation_counter[
            relation_name or "<VIDE>"
        ] += 1

        anomaly_counter[
            anomaly_type
        ] += 1

    # =================================================================
    # OUTPUT JSON
    # =================================================================

    output = {

        "resolver":
            "ontology_relation_review_resolver",

        "version":
            "V2_REAL_TRACE_JSON_STRUCTURE",

        "input_clinical_directory":
            str(CLINICAL_DIR),

        "input_audit":
            str(ANOMALIES_CSV),

        "summary": {

            "audit_anomalies_total":
                len(rows),

            "relation_anomalies_received":
                len(relation_rows),

            "documents_loaded":
                len(document_cache),

            "documents_missing":
                len(missing_documents),

            "relations_found":
                relations_found,

            "relations_unresolved":
                unresolved_relations,

            "sources_found":
                sources_found,

            "sources_unresolved":
                unresolved_sources,

            "targets_found":
                targets_found,

            "targets_unresolved":
                unresolved_targets,

            "resolution_counts":
                dict(
                    resolution_counter
                ),

            "action_counts":
                dict(
                    action_counter
                ),

            "relation_counts":
                dict(
                    relation_counter
                )
        },

        "resolved_reviews":
            results
    }

    dump_json(
        OUTPUT_JSON,
        output
    )

    # =================================================================
    # OUTPUT CSV
    # =================================================================

    OUTPUT_CSV.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    fields = [
        "review_id",
        "document",
        "anomaly_type",

        "relation_id",
        "relation_name",

        "source_id",
        "source_text",
        "source_type",
        "source_category",
        "source_parameter",
        "source_negated",

        "target_id",
        "target_text",
        "target_type",
        "target_category",
        "target_parameter",
        "target_negated",

        "audit_actual_type",
        "expected_type",

        "relation_proof",

        "resolution",
        "proposed_action",
        "confidence",
        "reason",
    ]

    with OUTPUT_CSV.open(
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fields,
            extrasaction="ignore"
        )

        writer.writeheader()

        writer.writerows(
            results
        )

    # =================================================================
    # TXT
    # =================================================================

    lines = []

    lines.append("=" * 120)

    lines.append(
        "TRACE / SGCE - "
        "ONTOLOGY RELATION REVIEW RESOLVER V2"
    )

    lines.append("=" * 120)

    lines.append(
        f"Anomalies totales audit             : {len(rows)}"
    )

    lines.append(
        f"Anomalies relationnelles reçues     : {len(relation_rows)}"
    )

    lines.append(
        f"Documents chargés                   : {len(document_cache)}"
    )

    lines.append(
        f"Documents manquants                 : {len(missing_documents)}"
    )

    lines.append("")

    # -----------------------------------------------------------------
    # ANOMALIES
    # -----------------------------------------------------------------

    lines.append(
        "ANOMALIES EN ENTREE"
    )

    lines.append("-" * 120)

    for key, value in anomaly_counter.most_common():

        lines.append(
            f"{key:<60}: {value}"
        )

    # -----------------------------------------------------------------
    # RESOLUTIONS
    # -----------------------------------------------------------------

    lines.append("")

    lines.append(
        "RESOLUTIONS"
    )

    lines.append("-" * 120)

    for key, value in resolution_counter.most_common():

        lines.append(
            f"{key:<60}: {value}"
        )

    # -----------------------------------------------------------------
    # ACTIONS
    # -----------------------------------------------------------------

    lines.append("")

    lines.append(
        "ACTIONS PROPOSEES"
    )

    lines.append("-" * 120)

    for key, value in action_counter.most_common():

        lines.append(
            f"{key:<60}: {value}"
        )

    # -----------------------------------------------------------------
    # RELATIONS
    # -----------------------------------------------------------------

    lines.append("")

    lines.append(
        "RELATIONS CONCERNEES"
    )

    lines.append("-" * 120)

    for key, value in relation_counter.most_common():

        lines.append(
            f"{key:<60}: {value}"
        )

    # -----------------------------------------------------------------
    # RESOLUTION TRACE
    # -----------------------------------------------------------------

    lines.append("")

    lines.append(
        "RESOLUTION STRUCTURE TRACE"
    )

    lines.append("-" * 120)

    lines.append(
        f"Relations retrouvées                : {relations_found}"
    )

    lines.append(
        f"Relations non résolues              : {unresolved_relations}"
    )

    lines.append(
        f"Sources retrouvées                  : {sources_found}"
    )

    lines.append(
        f"Sources non résolues                : {unresolved_sources}"
    )

    lines.append(
        f"Cibles retrouvées                   : {targets_found}"
    )

    lines.append(
        f"Cibles non résolues                 : {unresolved_targets}"
    )

    # -----------------------------------------------------------------
    # EXEMPLES INVERSIONS
    # -----------------------------------------------------------------

    inversions = [
        x
        for x in results
        if x["resolution"]
        == "POSSIBLE_RELATION_INVERSION"
    ]

    lines.append("")

    lines.append(
        "EXEMPLES POSSIBLE_RELATION_INVERSION"
    )

    lines.append("-" * 120)

    if not inversions:

        lines.append("Aucun.")

    else:

        for x in inversions[:20]:

            lines.append("")

            lines.append(
                f"{x['document']} | "
                f"{x['relation_id']}"
            )

            lines.append(
                f"ACTUEL : "
                f"{x['source_text']} "
                f"[{x['source_type']}] "
                f"--{x['relation_name']}--> "
                f"{x['target_text']} "
                f"[{x['target_type']}]"
            )

            lines.append(
                f"PREUVE : "
                f"{x['relation_proof']!r}"
            )

    lines.append("")

    lines.append(
        "Aucune donnée clinique n'a été modifiée."
    )

    OUTPUT_TXT.write_text(
        "\n".join(lines),
        encoding="utf-8"
    )

    # =================================================================
    # CONSOLE
    # =================================================================

    print()

    print(
        "ANOMALIES EN ENTREE"
    )

    print("-" * 120)

    for key, value in anomaly_counter.most_common():

        print(
            f"{key:<60}: {value}"
        )

    print()

    print(
        "RESOLUTIONS"
    )

    print("-" * 120)

    for key, value in resolution_counter.most_common():

        print(
            f"{key:<60}: {value}"
        )

    print()

    print(
        "ACTIONS PROPOSEES"
    )

    print("-" * 120)

    for key, value in action_counter.most_common():

        print(
            f"{key:<60}: {value}"
        )

    print()

    print(
        "RESOLUTION STRUCTURE TRACE"
    )

    print("-" * 120)

    print(
        f"Relations retrouvées                : "
        f"{relations_found}"
    )

    print(
        f"Relations non résolues              : "
        f"{unresolved_relations}"
    )

    print(
        f"Sources retrouvées                  : "
        f"{sources_found}"
    )

    print(
        f"Sources non résolues                : "
        f"{unresolved_sources}"
    )

    print(
        f"Cibles retrouvées                   : "
        f"{targets_found}"
    )

    print(
        f"Cibles non résolues                 : "
        f"{unresolved_targets}"
    )

    print()

    print(
        f"Inversions potentielles             : "
        f"{len(inversions)}"
    )

    print()

    print(
        f"Sortie JSON                         : "
        f"{OUTPUT_JSON}"
    )

    print(
        f"Sortie CSV                          : "
        f"{OUTPUT_CSV}"
    )

    print(
        f"Résumé TXT                          : "
        f"{OUTPUT_TXT}"
    )

    print()

    print(
        "Aucune donnée clinique n'a été modifiée."
    )


# =====================================================================
# EXECUTION
# =====================================================================

if __name__ == "__main__":
    main()