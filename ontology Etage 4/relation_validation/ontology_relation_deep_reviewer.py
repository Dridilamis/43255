# -*- coding: utf-8 -*-

"""
TRACE / SGCE - ONTOLOGY RELATION DEEP REVIEWER V2
REAL TRACE JSON STRUCTURE

Objectif
--------
Réexaminer les anomalies relationnelles résiduelles après le retypage
ontologique SAFE.

Cette version utilise la structure réelle des JSON TRACE :
    - global_entities
    - global_relations
    - identifiant_entite
    - categorie / type
    - parametre
    - preuve
    - name
    - page
    - nie
    - horodatage

IMPORTANT :
- aucune donnée clinique n'est modifiée ;
- aucun endpoint n'est retypé ;
- aucune relation n'est supprimée ;
- ce script produit uniquement des décisions de deep review.
"""

# GENERICITY PATCH: TRACE_BASE_DIR can be supplied through the environment.

import os
import json
import re
import unicodedata

from pathlib import Path
from collections import Counter, defaultdict


# ======================================================================
# CONFIGURATION
# ======================================================================

ROOT = Path(__file__).resolve().parent
STAGE4_DIR = ROOT.parent

INPUT_FILE = ROOT / "outputs" / "ontology_relation_residual_validated.json"
CLINICAL_DIR = (
    STAGE4_DIR
    / "entity_validation"
    / "entity_validation_safe_corrected"
)
OUTPUT_FILE = ROOT / "outputs" / "ontology_relation_deep_review.json"
OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)


# ======================================================================
# I/O
# ======================================================================

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


# ======================================================================
# NORMALISATION
# ======================================================================

def normalize(value):
    if value is None:
        return ""

    value = str(value)

    value = unicodedata.normalize(
        "NFKD",
        value
    )

    value = "".join(
        c for c in value
        if not unicodedata.combining(c)
    )

    value = value.lower()

    value = value.replace("_", " ")

    value = re.sub(
        r"[^\w\s%/+.-]",
        " ",
        value
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


# ======================================================================
# ENTITES TRACE
# ======================================================================

def entity_id(entity):
    """
    Structure réelle TRACE :
        identifiant_entite
    """

    return (
        entity.get("identifiant_entite")
        or entity.get("entity_id")
        or entity.get("id")
    )


def entity_type(entity):
    """
    TRACE contient normalement categorie et type.
    """

    return (
        entity.get("type")
        or entity.get("categorie")
        or ""
    )


def entity_parameter(entity):
    return (
        entity.get("parametre")
        or ""
    )


def entity_proof(entity):
    """
    Retourne la meilleure preuve disponible.
    """

    candidates = [
        entity.get("preuve"),
        entity.get("name"),
        entity.get("nom_medicament"),
        entity.get("valeur"),
        entity.get("parametre"),
    ]

    for value in candidates:
        if value not in (
            None,
            "",
            "inconnu"
        ):
            return str(value)

    return ""


def entity_surface_candidates(entity):
    """
    Toutes les représentations textuelles utiles
    d'une entité.
    """

    values = []

    fields = [
        "preuve",
        "name",
        "parametre",
        "nom_medicament",
        "valeur",
        "valeur_reference"
    ]

    for field in fields:

        value = entity.get(field)

        if value not in (
            None,
            "",
            "inconnu"
        ):
            values.append(str(value))

    # déduplication
    result = []

    seen = set()

    for value in values:

        key = normalize(value)

        if key and key not in seen:
            seen.add(key)
            result.append(value)

    return result


# ======================================================================
# INDEX ENTITES
# ======================================================================

def build_entity_index(document):
    """
    Index principal :
        identifiant_entite -> entité

    global_entities est considéré comme source principale.
    """

    index = {}

    for entity in document.get(
        "global_entities",
        []
    ):

        eid = entity_id(entity)

        if eid:
            index[eid] = entity

    return index


def find_entity(document, eid):
    """
    Résolution robuste d'une entité TRACE.
    """

    if not eid:
        return None

    # --------------------------------------------------
    # 1. global_entities
    # --------------------------------------------------

    for entity in document.get(
        "global_entities",
        []
    ):

        if entity_id(entity) == eid:
            return entity

    # --------------------------------------------------
    # 2. pages
    # fallback uniquement
    # --------------------------------------------------

    pages = document.get(
        "pages",
        []
    )

    if isinstance(pages, list):

        for page in pages:

            if not isinstance(page, dict):
                continue

            possible_lists = [
                page.get("entities"),
                page.get("entites"),
                page.get("extracted_entities"),
            ]

            for entities in possible_lists:

                if not isinstance(
                    entities,
                    list
                ):
                    continue

                for entity in entities:

                    if not isinstance(
                        entity,
                        dict
                    ):
                        continue

                    if entity_id(entity) == eid:
                        return entity

    return None


# ======================================================================
# RELATIONS TRACE
# ======================================================================

def relation_id(relation):

    return (
        relation.get("identifiant_relation")
        or relation.get("relation_id")
        or relation.get("id")
    )


def relation_name(relation):

    return (
        relation.get("relation")
        or relation.get("type_relation")
        or relation.get("relation_type")
        or relation.get("type")
        or relation.get("name")
        or ""
    )


def find_relation(document, rid):
    """
    Recherche d'une relation dans global_relations.
    """

    if not rid:
        return None

    for relation in document.get(
        "global_relations",
        []
    ):

        if relation_id(relation) == rid:
            return relation

    return None


# ======================================================================
# PREUVES
# ======================================================================

def text_overlap(a, b):

    a = normalize(a)
    b = normalize(b)

    if not a or not b:
        return False

    return (
        a in b
        or b in a
    )


def token_overlap(a, b):

    a_tokens = set(
        normalize(a).split()
    )

    b_tokens = set(
        normalize(b).split()
    )

    if not a_tokens or not b_tokens:
        return 0.0

    intersection = (
        a_tokens
        & b_tokens
    )

    return len(intersection) / max(
        1,
        min(
            len(a_tokens),
            len(b_tokens)
        )
    )


def endpoint_matches_candidate(
    entity,
    candidate_text
):
    """
    Vérifie si le texte du candidat est compatible
    avec l'entité réellement résolue.
    """

    if not entity:
        return False

    if not candidate_text:
        return True

    for surface in entity_surface_candidates(
        entity
    ):

        if text_overlap(
            surface,
            candidate_text
        ):
            return True

        if token_overlap(
            surface,
            candidate_text
        ) >= 0.75:
            return True

    return False


# ======================================================================
# SUPPORT DOCUMENTAIRE
# ======================================================================

def get_page(entity):

    if not entity:
        return None

    return entity.get("page")


def same_page(source, target):

    sp = get_page(source)
    tp = get_page(target)

    return (
        sp is not None
        and tp is not None
        and sp == tp
    )


def close_pages(source, target):

    sp = get_page(source)
    tp = get_page(target)

    try:

        if sp is None or tp is None:
            return False

        return abs(
            int(sp) - int(tp)
        ) <= 1

    except Exception:
        return False


def endpoint_negated(entity):

    if not entity:
        return False

    return entity.get("nie") is True


def temporal_value(entity):

    if not entity:
        return None

    value = entity.get(
        "horodatage"
    )

    if value in (
        None,
        "",
        "inconnu"
    ):
        return None

    return value


# ======================================================================
# DEEP REVIEW
# ======================================================================

def review_case(
    case,
    document
):

    source_id = case.get(
        "source_id"
    )

    target_id = case.get(
        "target_id"
    )

    source = find_entity(
        document,
        source_id
    )

    target = find_entity(
        document,
        target_id
    )

    relation = find_relation(
        document,
        case.get("relation_id")
    )

    # --------------------------------------------------
    # ENTITE NON RESOLUE
    # --------------------------------------------------

    if source is None or target is None:

        return {
            "deep_classification":
                "UNRESOLVED_ENDPOINT",

            "deep_action":
                "NONE",

            "deep_confidence":
                0.0,

            "deep_reason":
                "Au moins un endpoint n'a pas pu être résolu "
                "par identifiant_entite dans le JSON TRACE.",

            "source_found":
                source is not None,

            "target_found":
                target is not None,

            "relation_found":
                relation is not None,
        }

    # --------------------------------------------------
    # INFORMATIONS REELLES
    # --------------------------------------------------

    source_real_type = entity_type(
        source
    )

    target_real_type = entity_type(
        target
    )

    source_proof = entity_proof(
        source
    )

    target_proof = entity_proof(
        target
    )

    source_page = get_page(
        source
    )

    target_page = get_page(
        target
    )

    source_negated = endpoint_negated(
        source
    )

    target_negated = endpoint_negated(
        target
    )

    source_temporal = temporal_value(
        source
    )

    target_temporal = temporal_value(
        target
    )

    source_text_match = (
        endpoint_matches_candidate(
            source,
            case.get("source_text")
        )
    )

    target_text_match = (
        endpoint_matches_candidate(
            target,
            case.get("target_text")
        )
    )

    affected_role = case.get(
        "affected_role"
    )

    expected_types = (
        case.get(
            "expected_types_for_affected_role"
        )
        or []
    )

    # --------------------------------------------------
    # TYPE ACTUEL DE L'ENDPOINT AFFECTE
    # --------------------------------------------------

    if affected_role == "SOURCE":

        affected_entity = source
        affected_real_type = (
            source_real_type
        )

    else:

        affected_entity = target
        affected_real_type = (
            target_real_type
        )

    type_still_invalid = (
        bool(expected_types)
        and affected_real_type
        not in expected_types
    )

    # --------------------------------------------------
    # NEGATION
    # --------------------------------------------------

    if source_negated or target_negated:

        return {
            "deep_classification":
                "NEGATION_SENSITIVE_RELATION",

            "deep_action":
                "REVIEW",

            "deep_confidence":
                0.99,

            "deep_reason":
                "Au moins un endpoint est explicitement nié. "
                "La relation ne doit pas être corrigée automatiquement.",

            "source_found":
                True,

            "target_found":
                True,

            "relation_found":
                relation is not None,

            "source_real_type":
                source_real_type,

            "target_real_type":
                target_real_type,

            "source_proof":
                source_proof,

            "target_proof":
                target_proof,

            "source_page":
                source_page,

            "target_page":
                target_page,

            "source_negated":
                source_negated,

            "target_negated":
                target_negated,

            "source_temporal":
                source_temporal,

            "target_temporal":
                target_temporal,
        }

    # --------------------------------------------------
    # ENDPOINT PROTEGE + TYPE TOUJOURS INCOMPATIBLE
    # --------------------------------------------------

    if (
        case.get("final_status")
        == "PROTECTED_ENDPOINT_REVIEW_RELATION"
        and type_still_invalid
    ):

        # Les deux endpoints sont bien identifiés,
        # leur contenu est ancré, mais la relation
        # viole toujours l'ontologie.

        if (
            source_text_match
            and target_text_match
        ):

            return {
                "deep_classification":
                    "RELATION_ONTOLOGY_CONFLICT_CONFIRMED",

                "deep_action":
                    "PROPOSE_REMOVE_RELATION",

                "deep_confidence":
                    0.99,

                "deep_reason":
                    "Les deux endpoints sont résolus et ancrés dans "
                    "le JSON TRACE. Le type de l'endpoint affecté "
                    "reste incompatible avec la signature ontologique. "
                    "L'endpoint étant protégé contre le retypage, "
                    "la relation elle-même devient candidate à suppression.",

                "source_found":
                    True,

                "target_found":
                    True,

                "relation_found":
                    relation is not None,

                "source_real_type":
                    source_real_type,

                "target_real_type":
                    target_real_type,

                "expected_types":
                    expected_types,

                "source_proof":
                    source_proof,

                "target_proof":
                    target_proof,

                "source_page":
                    source_page,

                "target_page":
                    target_page,

                "same_page":
                    same_page(
                        source,
                        target
                    ),

                "close_pages":
                    close_pages(
                        source,
                        target
                    ),

                "source_text_match":
                    source_text_match,

                "target_text_match":
                    target_text_match,

                "source_negated":
                    False,

                "target_negated":
                    False,

                "source_temporal":
                    source_temporal,

                "target_temporal":
                    target_temporal,
            }

    # --------------------------------------------------
    # ENDPOINTS BIEN ANCRES MAIS PREUVE PARTIELLE
    # --------------------------------------------------

    if (
        source_text_match
        or target_text_match
    ):

        return {
            "deep_classification":
                "PARTIAL_DOCUMENT_SUPPORT",

            "deep_action":
                "REVIEW",

            "deep_confidence":
                0.75,

            "deep_reason":
                "Au moins un endpoint est textuellement ancré, "
                "mais le support n'est pas suffisant pour autoriser "
                "une correction relationnelle automatique.",

            "source_found":
                True,

            "target_found":
                True,

            "relation_found":
                relation is not None,

            "source_real_type":
                source_real_type,

            "target_real_type":
                target_real_type,

            "source_proof":
                source_proof,

            "target_proof":
                target_proof,

            "source_page":
                source_page,

            "target_page":
                target_page,

            "source_text_match":
                source_text_match,

            "target_text_match":
                target_text_match,
        }

    # --------------------------------------------------
    # CAS RESTANT
    # --------------------------------------------------

    return {
        "deep_classification":
            "INSUFFICIENT_RELATION_SUPPORT",

        "deep_action":
            "REVIEW",

        "deep_confidence":
            0.50,

        "deep_reason":
            "Les endpoints sont résolus par identifiant, mais "
            "leur support textuel ne permet pas de confirmer "
            "sûrement la relation.",

        "source_found":
            True,

        "target_found":
            True,

        "relation_found":
            relation is not None,

        "source_real_type":
            source_real_type,

        "target_real_type":
            target_real_type,

        "source_proof":
            source_proof,

        "target_proof":
            target_proof,

        "source_page":
            source_page,

        "target_page":
            target_page,

        "source_text_match":
            source_text_match,

        "target_text_match":
            target_text_match,
    }


# ======================================================================
# MAIN
# ======================================================================

def main():

    print("=" * 120)

    print(
        "TRACE / SGCE - ONTOLOGY RELATION DEEP REVIEWER V2 "
        "- REAL TRACE JSON STRUCTURE"
    )

    print("=" * 120)

    data = load_json(
        INPUT_FILE
    )

    decisions = data.get(
        "validated_decisions",
        []
    )

    # --------------------------------------------------
    # CACHE DOCUMENTS
    # --------------------------------------------------

    document_cache = {}

    missing_documents = set()

    results = []

    input_status_counter = Counter()

    result_counter = Counter()

    action_counter = Counter()

    relation_counter = Counter()

    source_found = 0
    target_found = 0
    both_found = 0
    relation_found = 0

    # --------------------------------------------------
    # TRAITEMENT
    # --------------------------------------------------

    for case in decisions:

        status = case.get(
            "final_status",
            "UNKNOWN"
        )

        input_status_counter[
            status
        ] += 1

        document_name = case.get(
            "document"
        )

        if not document_name:

            continue

        # ----------------------------------------------
        # charger document
        # ----------------------------------------------

        if document_name not in document_cache:

            path = (
                CLINICAL_DIR
                / document_name
            )

            if not path.exists():

                missing_documents.add(
                    document_name
                )

                document_cache[
                    document_name
                ] = None

            else:

                try:

                    document_cache[
                        document_name
                    ] = load_json(
                        path
                    )

                except Exception:

                    missing_documents.add(
                        document_name
                    )

                    document_cache[
                        document_name
                    ] = None

        document = document_cache.get(
            document_name
        )

        # ----------------------------------------------
        # document absent
        # ----------------------------------------------

        if document is None:

            review = {
                "deep_classification":
                    "MISSING_DOCUMENT",

                "deep_action":
                    "NONE",

                "deep_confidence":
                    0.0,

                "deep_reason":
                    "Document clinique introuvable."
            }

        else:

            review = review_case(
                case,
                document
            )

        # ----------------------------------------------
        # fusion
        # ----------------------------------------------

        row = {
            **case,
            **review
        }

        results.append(
            row
        )

        classification = (
            review.get(
                "deep_classification",
                "UNKNOWN"
            )
        )

        action = review.get(
            "deep_action",
            "NONE"
        )

        result_counter[
            classification
        ] += 1

        action_counter[
            action
        ] += 1

        relation_counter[
            case.get(
                "relation_name",
                "<VIDE>"
            )
        ] += 1

        if review.get(
            "source_found"
        ):
            source_found += 1

        if review.get(
            "target_found"
        ):
            target_found += 1

        if (
            review.get(
                "source_found"
            )
            and review.get(
                "target_found"
            )
        ):
            both_found += 1

        if review.get(
            "relation_found"
        ):
            relation_found += 1

    # --------------------------------------------------
    # OUTPUT
    # --------------------------------------------------

    output = {

        "reviewer":
            "ontology_relation_deep_reviewer",

        "version":
            "V2_REAL_TRACE_JSON_STRUCTURE",

        "mode":
            "DOCUMENT_GROUNDED_CONSERVATIVE",

        "input":
            str(INPUT_FILE),

        "clinical_directory":
            str(CLINICAL_DIR),

        "summary": {

            "decisions_received":
                len(decisions),

            "results_generated":
                len(results),

            "missing_documents":
                len(missing_documents),

            "source_found":
                source_found,

            "target_found":
                target_found,

            "both_endpoints_found":
                both_found,

            "relation_found":
                relation_found,

            "input_status_counts":
                dict(
                    input_status_counter
                ),

            "deep_classification_counts":
                dict(
                    result_counter
                ),

            "deep_action_counts":
                dict(
                    action_counter
                ),
        },

        "missing_document_names":
            sorted(
                missing_documents
            ),

        "deep_reviews":
            results
    }

    dump_json(
        OUTPUT_FILE,
        output
    )

    # --------------------------------------------------
    # AFFICHAGE
    # --------------------------------------------------

    print(
        f"Décisions reçues                    : "
        f"{len(decisions)}"
    )

    print(
        f"Documents manquants                 : "
        f"{len(missing_documents)}"
    )

    print()

    print(
        "STATUTS EN ENTREE"
    )

    print("-" * 120)

    for key, value in (
        input_status_counter.most_common()
    ):

        print(
            f"{key:<60}: {value}"
        )

    print()

    print(
        "RESOLUTION STRUCTURE TRACE"
    )

    print("-" * 120)

    print(
        f"Sources retrouvées                  : "
        f"{source_found}"
    )

    print(
        f"Cibles retrouvées                   : "
        f"{target_found}"
    )

    print(
        f"Deux endpoints retrouvés            : "
        f"{both_found}"
    )

    print(
        f"Relations retrouvées                : "
        f"{relation_found}"
    )

    print()

    print(
        "RESULTATS DEEP REVIEW"
    )

    print("-" * 120)

    for key, value in (
        result_counter.most_common()
    ):

        print(
            f"{key:<60}: {value}"
        )

    print()

    print(
        "ACTIONS PROPOSEES"
    )

    print("-" * 120)

    for key, value in (
        action_counter.most_common()
    ):

        print(
            f"{key:<60}: {value}"
        )

    print()

    print(
        "RESULTATS PAR RELATION"
    )

    print("-" * 120)

    by_relation_result = defaultdict(
        Counter
    )

    for row in results:

        rel = row.get(
            "relation_name",
            "<VIDE>"
        )

        cls = row.get(
            "deep_classification",
            "UNKNOWN"
        )

        by_relation_result[
            rel
        ][
            cls
        ] += 1

    for relation, total in (
        relation_counter.most_common()
    ):

        details = ", ".join(
            f"{k}={v}"
            for k, v
            in by_relation_result[
                relation
            ].most_common()
        )

        print(
            f"{relation:<50}: "
            f"{total:<5} | "
            f"{details}"
        )

    print()

    print(
        f"Sortie                              : "
        f"{OUTPUT_FILE}"
    )

    print()

    print(
        "Aucune entité et aucune relation clinique "
        "n'ont été modifiées."
    )


if __name__ == "__main__":
    main()