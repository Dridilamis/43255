# -*- coding: utf-8 -*-

"""
TRACE / SGCE
ENTITY VALIDATION CANDIDATE BUILDER 

Objectif
--------
Construire les candidats correspondant aux anomalies ontologiques
résiduelles détectées par final_ontology_audit.py.

Cette version est adaptée à la structure réelle des JSON TRACE-Sepsis :

ENTITES :
    global_entities
    identifiant_entite
    categorie
    type
    name
    preuve
    page

RELATIONS :
    global_relations
    identifiant_relation
    identifiant_entite_sujet
    identifiant_entite_objet
    entite_sujet
    entite_objet
    type_relation
    preuve
    page

Important
---------
- Aucun JSON clinique n'est modifié.
- Résolution prioritaire par identifiant.
- Fallback texte + page uniquement si nécessaire.
- Les anomalies DUPLICATE_ENTITY_CONTENT sont exclues ici.
- On traite uniquement :
      INVALID_RELATION_SOURCE_TYPE
      INVALID_RELATION_TARGET_TYPE
"""

# GENERICITY PATCH: configuration via environment; no corpus-example lexicon.

import os
import csv
import json
import re
import unicodedata

from pathlib import Path
from collections import Counter


# =====================================================================
# CONFIGURATION
# =====================================================================

ROOT = Path(__file__).resolve().parent
STAGE4_DIR = ROOT.parent
REDUCTION_DIR = STAGE4_DIR.parent
STAGE3_DIR = REDUCTION_DIR / "document_grounding Etage 3"

CLINICAL_DIR = STAGE3_DIR / "semantic_factual" / "semantic_factual_safe_corrected"
AUDIT_DIR = ROOT / "audit_initial"

ANOMALIES_CSV = AUDIT_DIR / "final_ontology_anomalies.csv"
ANOMALIES_JSON = AUDIT_DIR / "final_ontology_audit_report.json"

OUTPUT_DIR = ROOT / "queues"
OUTPUT_FILE = OUTPUT_DIR / "entity_validation_candidates.json"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SUPPORTED_ANOMALIES = {
    "INVALID_RELATION_SOURCE_TYPE",
    "INVALID_RELATION_TARGET_TYPE",
}


# =====================================================================
# UTILITAIRES
# =====================================================================

def load_json(path):
    return json.loads(
        Path(path).read_text(encoding="utf-8")
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


def clean(value):
    if value is None:
        return ""

    return str(value).strip()


def normalize(value):
    """
    Normalisation uniquement utilisée pour les fallbacks.
    Elle ne modifie jamais les données cliniques.
    """

    value = clean(value)

    value = unicodedata.normalize(
        "NFKD",
        value
    )

    value = "".join(
        c
        for c in value
        if not unicodedata.combining(c)
    )

    value = value.lower()

    value = value.replace("’", "'")
    value = value.replace("`", "'")

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


def safe_int(value):
    try:
        return int(value)
    except Exception:
        return None


def first_nonempty(*values):
    for value in values:
        if clean(value):
            return value

    return None


# =====================================================================
# EXTRACTION DES ENTITES / RELATIONS
# =====================================================================

def get_entities(document):
    """
    Structure principale observée dans les JSON TRACE.
    """

    entities = document.get(
        "global_entities",
        []
    )

    if isinstance(entities, list):
        return entities

    return []


def get_relations(document):
    """
    Structure principale observée dans les JSON TRACE.
    """

    relations = document.get(
        "global_relations",
        []
    )

    if isinstance(relations, list):
        return relations

    return []


# =====================================================================
# IDENTIFIANTS
# =====================================================================

def entity_id(entity):
    return clean(
        first_nonempty(
            entity.get("identifiant_entite"),
            entity.get("entity_id"),
            entity.get("id")
        )
    )


def relation_id(relation):
    return clean(
        first_nonempty(
            relation.get("identifiant_relation"),
            relation.get("relation_id"),
            relation.get("id")
        )
    )


def entity_type(entity):
    return clean(
        first_nonempty(
            entity.get("type"),
            entity.get("type_entite"),
            entity.get("entity_type"),
            entity.get("categorie")
        )
    )


def entity_text(entity):
    return clean(
        first_nonempty(
            entity.get("name"),
            entity.get("preuve"),
            entity.get("texte"),
            entity.get("text"),
            entity.get("parametre")
        )
    )


def entity_proof(entity):
    return clean(
        first_nonempty(
            entity.get("preuve"),
            entity.get("name")
        )
    )


def entity_page(entity):
    return safe_int(
        entity.get("page")
    )


# =====================================================================
# INDEXATION DOCUMENT
# =====================================================================

def build_document_index(document):
    entities = get_entities(document)
    relations = get_relations(document)

    entities_by_id = {}

    entities_by_text = {}

    relations_by_id = {}

    for entity in entities:

        eid = entity_id(entity)

        if eid:
            entities_by_id.setdefault(
                eid,
                []
            ).append(entity)

        texts = {
            normalize(entity.get("name")),
            normalize(entity.get("preuve")),
            normalize(entity.get("parametre"))
        }

        for text in texts:

            if not text:
                continue

            entities_by_text.setdefault(
                text,
                []
            ).append(entity)

    for relation in relations:

        rid = relation_id(relation)

        if rid:
            relations_by_id.setdefault(
                rid,
                []
            ).append(relation)

    return {
        "entities": entities,
        "relations": relations,
        "entities_by_id": entities_by_id,
        "entities_by_text": entities_by_text,
        "relations_by_id": relations_by_id,
    }


# =====================================================================
# LECTURE DU CSV D'ANOMALIES
# =====================================================================

def read_anomalies_csv():
    if not ANOMALIES_CSV.exists():
        raise FileNotFoundError(
            f"CSV anomalies introuvable : {ANOMALIES_CSV}"
        )

    with ANOMALIES_CSV.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        reader = csv.DictReader(f)

        return [
            dict(row)
            for row in reader
        ]


# =====================================================================
# ACCES FLEXIBLE AUX COLONNES DU RAPPORT
# =====================================================================

def get_field(row, *names):
    """
    Permet de tolérer plusieurs noms de colonnes provenant
    du final_ontology_audit.
    """

    for name in names:

        if name in row:

            value = row.get(name)

            if clean(value):
                return value

    return None


def anomaly_type(row):
    return clean(
        get_field(
            row,
            "anomaly_type",
            "type_anomalie",
            "anomaly",
            "type"
        )
    )


def anomaly_document(row):
    return clean(
        get_field(
            row,
            "document",
            "filename",
            "file",
            "source_file"
        )
    )


def anomaly_relation_id(row):
    return clean(
        get_field(
            row,
            "relation_id",
            "identifiant_relation",
            "relation_identifier"
        )
    )


def anomaly_relation_name(row):
    return clean(
        get_field(
            row,
            "relation_name",
            "type_relation",
            "relation",
            "predicate"
        )
    )


def anomaly_entity_id(row):
    return clean(
        get_field(
            row,
            "entity_id",
            "identifiant_entite",
            "endpoint_id"
        )
    )


def anomaly_page(row):
    return safe_int(
        get_field(
            row,
            "page",
            "relation_page",
            "entity_page"
        )
    )


def anomaly_actual_type(row):
    return clean(
        get_field(
            row,
            "actual_type",
            "observed_type",
            "entity_type",
            "current_type"
        )
    )


def anomaly_expected_type(row):
    return clean(
        get_field(
            row,
            "expected_type",
            "required_type",
            "domain_or_range_type",
            "allowed_type"
        )
    )


def anomaly_entity_text(row):
    return clean(
        get_field(
            row,
            "entity_text",
            "entity_name",
            "endpoint_text",
            "source_text",
            "target_text",
            "name",
            "preuve"
        )
    )


# =====================================================================
# RESOLUTION DOCUMENT
# =====================================================================

def resolve_document(filename):
    if not filename:
        return None

    exact = CLINICAL_DIR / filename

    if exact.exists():
        return exact

    target = Path(filename).name

    matches = list(
        CLINICAL_DIR.glob(target)
    )

    if len(matches) == 1:
        return matches[0]

    norm_target = normalize(target)

    for path in CLINICAL_DIR.glob("*.json"):

        if normalize(path.name) == norm_target:
            return path

    return None


# =====================================================================
# RESOLUTION RELATION
# =====================================================================

def resolve_relation(
    row,
    index
):
    rid = anomaly_relation_id(row)

    # ---------------------------------------------------------------
    # 1. IDENTIFIANT EXACT
    # ---------------------------------------------------------------

    if rid:

        matches = index[
            "relations_by_id"
        ].get(
            rid,
            []
        )

        if len(matches) == 1:
            return (
                matches[0],
                "ID_EXACT"
            )

        if len(matches) > 1:
            return (
                matches[0],
                "ID_DUPLICATE"
            )

    # ---------------------------------------------------------------
    # 2. FALLBACK TYPE RELATION + PAGE
    # ---------------------------------------------------------------

    rel_name = normalize(
        anomaly_relation_name(row)
    )

    page = anomaly_page(row)

    candidates = []

    for relation in index["relations"]:

        current_name = normalize(
            first_nonempty(
                relation.get("type_relation"),
                relation.get("relation_name"),
                relation.get("relation")
            )
        )

        if rel_name and current_name != rel_name:
            continue

        rel_page = safe_int(
            relation.get("page")
        )

        if (
            page is not None
            and rel_page is not None
            and page != rel_page
        ):
            continue

        candidates.append(relation)

    if len(candidates) == 1:
        return (
            candidates[0],
            "TYPE_PLUS_PAGE"
        )

    return (
        None,
        "UNRESOLVED"
    )


# =====================================================================
# ENDPOINTS D'UNE RELATION
# =====================================================================

def relation_source_id(relation):
    return clean(
        first_nonempty(
            relation.get("identifiant_entite_sujet"),
            relation.get("source_id"),
            relation.get("subject_id"),
            relation.get("from_id")
        )
    )


def relation_target_id(relation):
    return clean(
        first_nonempty(
            relation.get("identifiant_entite_objet"),
            relation.get("target_id"),
            relation.get("object_id"),
            relation.get("to_id")
        )
    )


def relation_source_text(relation):
    return clean(
        first_nonempty(
            relation.get("entite_sujet"),
            relation.get("source"),
            relation.get("subject")
        )
    )


def relation_target_text(relation):
    return clean(
        first_nonempty(
            relation.get("entite_objet"),
            relation.get("target"),
            relation.get("object")
        )
    )


# =====================================================================
# RESOLUTION ENTITE
# =====================================================================

def resolve_entity_by_id(
    eid,
    index
):
    if not eid:
        return (
            None,
            "NO_ID"
        )

    matches = index[
        "entities_by_id"
    ].get(
        eid,
        []
    )

    if len(matches) == 1:
        return (
            matches[0],
            "ID_EXACT"
        )

    if len(matches) > 1:

        first = matches[0]

        equivalent = all(
            normalize(entity_text(x))
            == normalize(entity_text(first))
            and
            entity_type(x)
            == entity_type(first)
            for x in matches
        )

        if equivalent:
            return (
                first,
                "ID_DUPLICATE_EQUIVALENT"
            )

        return (
            None,
            "ID_AMBIGUOUS"
        )

    return (
        None,
        "ID_NOT_FOUND"
    )


def resolve_entity_by_text(
    text,
    page,
    index
):
    norm_text = normalize(text)

    if not norm_text:
        return (
            None,
            "NO_TEXT"
        )

    matches = index[
        "entities_by_text"
    ].get(
        norm_text,
        []
    )

    if page is not None:

        same_page = [
            entity
            for entity in matches
            if entity_page(entity) == page
        ]

        if len(same_page) == 1:
            return (
                same_page[0],
                "TEXT_EXACT_PLUS_PAGE"
            )

        if len(same_page) > 1:

            types = {
                entity_type(x)
                for x in same_page
            }

            if len(types) == 1:
                return (
                    same_page[0],
                    "TEXT_DUPLICATE_EQUIVALENT"
                )

    if len(matches) == 1:
        return (
            matches[0],
            "TEXT_EXACT"
        )

    if len(matches) > 1:

        types = {
            entity_type(x)
            for x in matches
        }

        if len(types) == 1:
            return (
                matches[0],
                "TEXT_DUPLICATE_EQUIVALENT"
            )

        return (
            None,
            "TEXT_AMBIGUOUS"
        )

    return (
        None,
        "TEXT_NOT_FOUND"
    )


def resolve_endpoint(
    row,
    relation,
    role,
    index
):
    """
    role = SOURCE ou TARGET
    """

    if role == "SOURCE":

        rid = relation_source_id(
            relation
        ) if relation else ""

        rtext = relation_source_text(
            relation
        ) if relation else ""

    else:

        rid = relation_target_id(
            relation
        ) if relation else ""

        rtext = relation_target_text(
            relation
        ) if relation else ""

    # ---------------------------------------------------------------
    # ID de la relation
    # ---------------------------------------------------------------

    entity, method = resolve_entity_by_id(
        rid,
        index
    )

    if entity is not None:
        return entity, method

    # ---------------------------------------------------------------
    # ID présent dans le rapport d'audit
    # ---------------------------------------------------------------

    audit_eid = anomaly_entity_id(row)

    entity, method2 = resolve_entity_by_id(
        audit_eid,
        index
    )

    if entity is not None:
        return entity, "AUDIT_" + method2

    # ---------------------------------------------------------------
    # Texte porté par la relation
    # ---------------------------------------------------------------

    page = anomaly_page(row)

    entity, method3 = resolve_entity_by_text(
        rtext,
        page,
        index
    )

    if entity is not None:
        return entity, "RELATION_" + method3

    # ---------------------------------------------------------------
    # Texte porté par le rapport
    # ---------------------------------------------------------------

    audit_text = anomaly_entity_text(row)

    entity, method4 = resolve_entity_by_text(
        audit_text,
        page,
        index
    )

    if entity is not None:
        return entity, "AUDIT_" + method4

    return (
        None,
        "UNRESOLVED"
    )


# =====================================================================
# CONSTRUCTION CANDIDAT
# =====================================================================

def build_candidate(
    row,
    document_name,
    relation,
    relation_resolution,
    entity,
    entity_resolution,
    role
):
    atype = anomaly_type(row)

    expected_type = anomaly_expected_type(
        row
    )

    actual_type = (
        entity_type(entity)
        if entity
        else anomaly_actual_type(row)
    )

    # ---------------------------------------------------------------
    # Hypothèse initiale
    # ---------------------------------------------------------------

    if (
        entity is not None
        and expected_type
        and actual_type
        and expected_type != actual_type
    ):
        hypothesis = (
            "POSSIBLE_ENTITY_MISTYPING"
        )

    else:
        hypothesis = (
            "ONTOLOGY_RELATION_CONFLICT"
        )

    candidate = {
        "document": document_name,

        "anomaly_type": atype,

        "role": role,

        "relation_id": (
            relation_id(relation)
            if relation
            else anomaly_relation_id(row)
        ),

        "relation_name": (
            clean(
                first_nonempty(
                    relation.get("type_relation"),
                    relation.get("relation_name"),
                    relation.get("relation")
                )
            )
            if relation
            else anomaly_relation_name(row)
        ),

        "relation_resolution": (
            relation_resolution
        ),

        "entity_id": (
            entity_id(entity)
            if entity
            else anomaly_entity_id(row)
        ),

        "entity_resolution": (
            entity_resolution
        ),

        "entity_type": (
            entity_type(entity)
            if entity
            else anomaly_actual_type(row)
        ),

        "expected_type": (
            expected_type
        ),

        "entity_text": (
            entity_text(entity)
            if entity
            else anomaly_entity_text(row)
        ),

        "entity_proof": (
            entity_proof(entity)
            if entity
            else None
        ),

        "entity_page": (
            entity_page(entity)
            if entity
            else anomaly_page(row)
        ),

        "initial_hypothesis": (
            hypothesis
        ),

        "source_audit_row": row
    }

    if relation:

        candidate[
            "relation_source_id"
        ] = relation_source_id(
            relation
        )

        candidate[
            "relation_target_id"
        ] = relation_target_id(
            relation
        )

        candidate[
            "relation_source_text"
        ] = relation_source_text(
            relation
        )

        candidate[
            "relation_target_text"
        ] = relation_target_text(
            relation
        )

        candidate[
            "relation_proof"
        ] = clean(
            relation.get("preuve")
        )

        candidate[
            "relation_page"
        ] = safe_int(
            relation.get("page")
        )

    return candidate


# =====================================================================
# MAIN
# =====================================================================

def main():

    print("=" * 120)
    print(
        "TRACE / SGCE - "
        "ENTITY VALIDATION CANDIDATE BUILDER V2 "
        "- REAL TRACE JSON STRUCTURE"
    )
    print("=" * 120)

    anomalies = read_anomalies_csv()

    selected = [
        row
        for row in anomalies
        if anomaly_type(row)
        in SUPPORTED_ANOMALIES
    ]

    # ---------------------------------------------------------------
    # Documents concernés
    # ---------------------------------------------------------------

    documents_requested = {
        anomaly_document(row)
        for row in selected
        if anomaly_document(row)
    }

    document_cache = {}

    missing_documents = []

    for filename in sorted(
        documents_requested
    ):

        path = resolve_document(
            filename
        )

        if path is None:

            missing_documents.append(
                filename
            )

            continue

        document = load_json(
            path
        )

        document_cache[
            filename
        ] = {
            "path": path,
            "document": document,
            "index": build_document_index(
                document
            )
        }

    # ---------------------------------------------------------------
    # Compteurs
    # ---------------------------------------------------------------

    candidates = []

    anomaly_counts = Counter()

    role_counts = Counter()

    expected_counts = Counter()

    hypothesis_counts = Counter()

    relation_resolution_counts = Counter()

    entity_resolution_counts = Counter()

    unresolved_entities = 0

    unresolved_relations = 0

    # nombre d'anomalies par entité
    anomaly_per_entity = Counter()

    # ---------------------------------------------------------------
    # Construction
    # ---------------------------------------------------------------

    for row in selected:

        atype = anomaly_type(
            row
        )

        filename = anomaly_document(
            row
        )

        if filename not in document_cache:
            continue

        index = document_cache[
            filename
        ]["index"]

        # -----------------------------------------------------------
        # ROLE
        # -----------------------------------------------------------

        if (
            atype
            == "INVALID_RELATION_SOURCE_TYPE"
        ):
            role = "SOURCE"

        elif (
            atype
            == "INVALID_RELATION_TARGET_TYPE"
        ):
            role = "TARGET"

        else:
            continue

        # -----------------------------------------------------------
        # RELATION
        # -----------------------------------------------------------

        relation, rel_method = (
            resolve_relation(
                row,
                index
            )
        )

        relation_resolution_counts[
            rel_method
        ] += 1

        if relation is None:
            unresolved_relations += 1

        # -----------------------------------------------------------
        # ENTITE
        # -----------------------------------------------------------

        entity, entity_method = (
            resolve_endpoint(
                row,
                relation,
                role,
                index
            )
        )

        entity_resolution_counts[
            entity_method
        ] += 1

        if entity is None:
            unresolved_entities += 1

        # -----------------------------------------------------------
        # CANDIDAT
        # -----------------------------------------------------------

        candidate = build_candidate(
            row=row,
            document_name=filename,
            relation=relation,
            relation_resolution=rel_method,
            entity=entity,
            entity_resolution=entity_method,
            role=role
        )

        candidates.append(
            candidate
        )

        anomaly_counts[
            atype
        ] += 1

        role_counts[
            role
        ] += 1

        expected = candidate.get(
            "expected_type"
        ) or "<VIDE>"

        expected_counts[
            expected
        ] += 1

        hypothesis_counts[
            candidate[
                "initial_hypothesis"
            ]
        ] += 1

        eid = candidate.get(
            "entity_id"
        )

        if eid:
            anomaly_per_entity[
                (
                    filename,
                    eid
                )
            ] += 1

    # ---------------------------------------------------------------
    # Entités causant plusieurs anomalies
    # ---------------------------------------------------------------

    multiple_anomaly_entities = sum(
        1
        for count in anomaly_per_entity.values()
        if count > 1
    )

    # ---------------------------------------------------------------
    # OUTPUT
    # ---------------------------------------------------------------

    result = {
        "builder": (
            "entity_validation_candidate_builder"
        ),

        "version": "V2_REAL_TRACE_STRUCTURE",

        "source_clinical_directory": str(
            CLINICAL_DIR
        ),

        "source_anomaly_file": str(
            ANOMALIES_CSV
        ),

        "summary": {
            "documents_with_anomalies":
                len(documents_requested),

            "documents_loaded":
                len(document_cache),

            "documents_missing":
                len(missing_documents),

            "candidates_built":
                len(candidates),

            "anomaly_type_counts":
                dict(anomaly_counts),

            "unresolved_entities":
                unresolved_entities,

            "unresolved_relations":
                unresolved_relations,

            "entities_causing_multiple_anomalies":
                multiple_anomaly_entities,

            "initial_hypothesis_counts":
                dict(hypothesis_counts),

            "role_counts":
                dict(role_counts),

            "expected_type_counts":
                dict(expected_counts),

            "relation_resolution_counts":
                dict(
                    relation_resolution_counts
                ),

            "entity_resolution_counts":
                dict(
                    entity_resolution_counts
                ),
        },

        "missing_documents":
            missing_documents,

        "candidates":
            candidates
    }

    dump_json(
        OUTPUT_FILE,
        result
    )

    # =================================================================
    # AFFICHAGE
    # =================================================================

    print(
        f"Documents avec anomalies           : "
        f"{len(documents_requested)}"
    )

    print(
        f"Documents chargés                  : "
        f"{len(document_cache)}"
    )

    print(
        f"Documents manquants                : "
        f"{len(missing_documents)}"
    )

    print(
        f"Candidats construits               : "
        f"{len(candidates)}"
    )

    for key in [
        "INVALID_RELATION_SOURCE_TYPE",
        "INVALID_RELATION_TARGET_TYPE"
    ]:

        print(
            f"{key:<36}: "
            f"{anomaly_counts.get(key, 0)}"
        )

    print(
        f"Entités non résolues               : "
        f"{unresolved_entities}"
    )

    print(
        f"Relations non résolues             : "
        f"{unresolved_relations}"
    )

    print(
        f"Entités causant plusieurs anomalies: "
        f"{multiple_anomaly_entities}"
    )

    # ---------------------------------------------------------------
    # HYPOTHESES
    # ---------------------------------------------------------------

    print()
    print(
        "HYPOTHESES INITIALES"
    )
    print("-" * 120)

    for key, value in (
        hypothesis_counts.most_common()
    ):
        print(
            f"{key:<60}: {value}"
        )

    # ---------------------------------------------------------------
    # ROLES
    # ---------------------------------------------------------------

    print()
    print(
        "ROLES AFFECTES"
    )
    print("-" * 120)

    for key, value in (
        role_counts.most_common()
    ):
        print(
            f"{key:<60}: {value}"
        )

    # ---------------------------------------------------------------
    # TYPES ATTENDUS
    # ---------------------------------------------------------------

    print()
    print(
        "TYPES ATTENDUS"
    )
    print("-" * 120)

    for key, value in (
        expected_counts.most_common()
    ):
        print(
            f"{key:<60}: {value}"
        )

    # ---------------------------------------------------------------
    # RESOLUTION RELATIONS
    # ---------------------------------------------------------------

    print()
    print(
        "RESOLUTION DES RELATIONS"
    )
    print("-" * 120)

    for key, value in (
        relation_resolution_counts.most_common()
    ):
        print(
            f"{key:<60}: {value}"
        )

    # ---------------------------------------------------------------
    # RESOLUTION ENTITES
    # ---------------------------------------------------------------

    print()
    print(
        "RESOLUTION DES ENTITES"
    )
    print("-" * 120)

    for key, value in (
        entity_resolution_counts.most_common()
    ):
        print(
            f"{key:<60}: {value}"
        )

    print()
    print(
        f"Sortie                              : "
        f"{OUTPUT_FILE}"
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