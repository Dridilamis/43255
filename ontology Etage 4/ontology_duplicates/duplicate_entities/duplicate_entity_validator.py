# -*- coding: utf-8 -*-

"""
duplicate_entity_validator.py
=============================

TRACE / SGCE
DUPLICATE ENTITY VALIDATOR V3
GENERIC MULTI-EVIDENCE COREFERENCE VALIDATION

Objectif
--------
Valider les groupes d'entités potentiellement dupliquées produits par
duplicate_entity_candidate_builder.py.

Décisions possibles
-------------------
SAFE_MERGE
    La fusion est considérée suffisamment sûre.

KEEP_SEPARATE
    Une contradiction explicite ou une anomalie créée par la fusion
    indique que les entités doivent rester séparées.

REVIEW
    La fusion est plausible mais la coréférence n'est pas suffisamment
    démontrée pour une correction automatique.

Principes
---------
- Même texte + même type = candidat, pas preuve suffisante.
- Plusieurs pages ≠ contradiction.
- Plusieurs pages ≠ preuve de fusion.
- Absence de conflit ≠ preuve de coréférence.
- SAFE_MERGE nécessite plusieurs preuves positives indépendantes.
- Toute fusion est simulée avant validation.
- L'audit ontologique est comparé avant/après.
- Aucun JSON clinique n'est modifié par ce script.

Aucune règle spécifique à un type clinique particulier n'est codée ici.
"""


import copy
import json

from collections import Counter
from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parent
ONTOLOGY_DUPLICATES_DIR = ROOT.parent
STAGE4_DIR = ONTOLOGY_DUPLICATES_DIR.parent
REDUCTION_DIR = STAGE4_DIR.parent
PROJECT_DIR = REDUCTION_DIR.parent

INPUT_FILE = ROOT / "queues" / "duplicate_entity_candidates.json"
CLINICAL_DIR = ONTOLOGY_DUPLICATES_DIR / "duplicate_relations" / "duplicate_relation_cleaned"
OUTPUT_FILE = ROOT / "outputs" / "duplicate_entity_validated.json"

GUIDELINE_CANDIDATES = [
    PROJECT_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
    REDUCTION_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
    STAGE4_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
    Path.cwd() / "Guideline_TRACE_Sepsis_v1.6.json",
]

MIN_COREFERENCE_EVIDENCE = 2
RELATION_SIMILARITY_THRESHOLD = 0.75


# ============================================================
# JSON
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
        "Guideline TRACE introuvable."
    )


# ============================================================
# NORMALISATION
# ============================================================

def normalize_value(value):

    if value is None:
        return None

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value

    value = str(value).strip().casefold()

    if not value:
        return None

    # Valeurs génériques considérées comme absence
    if value in {
        "inconnu",
        "unknown",
        "none",
        "null",
        "n/a",
        "na",
        "non renseigne",
        "non renseigné",
        "non renseignee",
        "non renseignée",
    }:
        return None

    return value


def first_value(entity, keys):

    for key in keys:

        if key not in entity:
            continue

        value = normalize_value(
            entity.get(key)
        )

        if value is not None:
            return value

    return None


# ============================================================
# ENTITY HELPERS
# ============================================================

def entity_id(entity):

    return (
        entity.get("identifiant_entite")
        or entity.get("entity_id")
        or entity.get("id")
    )


def entity_type(entity):

    return (
        entity.get("categorie")
        or entity.get("type")
        or entity.get("entity_type")
        or ""
    )


def entity_page(entity):

    page = entity.get("page")

    if page is None:
        page = entity.get("_page")

    return page


def entity_negation(entity):

    return first_value(
        entity,
        (
            "nie",
            "negated",
            "negation",
            "is_negated",
        ),
    )


def entity_time(entity):

    return first_value(
        entity,
        (
            "horodatage",
            "timestamp",
            "datetime",
            "date",
            "time",
            "temporal_value",
        ),
    )


def entity_value(entity):

    return first_value(
        entity,
        (
            "valeur",
            "value",
            "numeric_value",
        ),
    )


def entity_unit(entity):

    return first_value(
        entity,
        (
            "unite",
            "unit",
        ),
    )


# ============================================================
# RELATION HELPERS
# ============================================================

def relation_id(relation):

    return (
        relation.get("identifiant_relation")
        or relation.get("relation_id")
        or relation.get("id")
    )


def relation_type(relation):

    return (
        relation.get("type_relation")
        or relation.get("relation_type")
        or relation.get("relation")
        or relation.get("predicate")
        or relation.get("type")
        or ""
    )


def relation_source(relation):

    return (
        relation.get("identifiant_entite_sujet")
        or relation.get("subject_id")
        or relation.get("from_id")
        or relation.get("source")
    )


def relation_target(relation):

    return (
        relation.get("identifiant_entite_objet")
        or relation.get("object_id")
        or relation.get("to_id")
        or relation.get("target")
    )


def set_relation_source(relation, new_id):

    for key in (
        "identifiant_entite_sujet",
        "subject_id",
        "from_id",
        "source",
    ):

        if key in relation:

            relation[key] = new_id
            return

    relation["source"] = new_id


def set_relation_target(relation, new_id):

    for key in (
        "identifiant_entite_objet",
        "object_id",
        "to_id",
        "target",
    ):

        if key in relation:

            relation[key] = new_id
            return

    relation["target"] = new_id


# ============================================================
# TRACE STRUCTURE
# ============================================================

def get_entities(doc):

    if isinstance(
        doc.get("global_entities"),
        list,
    ):
        return doc["global_entities"]

    entities = []

    for page in doc.get("pages", []) or []:

        entities.extend(
            page.get("entities", []) or []
        )

    return entities


def get_relations(doc):

    if isinstance(
        doc.get("global_relations"),
        list,
    ):
        return doc["global_relations"]

    relations = []

    for page in doc.get("pages", []) or []:

        relations.extend(
            page.get("relations", []) or []
        )

    return relations


def entity_lists(doc):

    lists = []

    if isinstance(
        doc.get("global_entities"),
        list,
    ):
        lists.append(
            doc["global_entities"]
        )

    for page in doc.get("pages", []) or []:

        if isinstance(
            page.get("entities"),
            list,
        ):
            lists.append(
                page["entities"]
            )

    return lists


def relation_lists(doc):

    lists = []

    if isinstance(
        doc.get("global_relations"),
        list,
    ):
        lists.append(
            doc["global_relations"]
        )

    for page in doc.get("pages", []) or []:

        if isinstance(
            page.get("relations"),
            list,
        ):
            lists.append(
                page["relations"]
            )

    return lists


# ============================================================
# ONTOLOGY SIGNATURES
# ============================================================

def load_signatures():

    guideline = load_json(
        resolve_guideline()
    )

    root = guideline.get(
        "ontologie_sepsis_graph",
        guideline,
    )

    locked = root.get(
        "signatures_relations_verrouillees_v1_5",
        {},
    )

    signatures = {}

    if not isinstance(locked, dict):
        return signatures

    for relation_name, specification in locked.items():

        if not isinstance(
            specification,
            dict,
        ):
            continue

        domain = specification.get(
            "domaine"
        )

        image = specification.get(
            "image"
        )

        if not domain or not image:
            continue

        signatures[
            relation_name
        ] = {
            "domaine": domain,
            "image": image,
        }

    return signatures


# ============================================================
# ONTOLOGY AUDIT
# ============================================================

def audit_document(doc, signatures):

    entities = {}

    for entity in get_entities(doc):

        eid = entity_id(entity)

        if eid is not None:

            entities[
                str(eid)
            ] = entity

    anomalies = set()

    for relation in get_relations(doc):

        rid = str(
            relation_id(relation)
        )

        rtype = relation_type(
            relation
        )

        sid = relation_source(
            relation
        )

        tid = relation_target(
            relation
        )

        source = entities.get(
            str(sid)
        )

        target = entities.get(
            str(tid)
        )

        # ----------------------------------------------------
        # Orphan source
        # ----------------------------------------------------

        if source is None:

            anomalies.add(
                (
                    "ORPHAN_SOURCE",
                    rid,
                    str(sid),
                )
            )

        # ----------------------------------------------------
        # Orphan target
        # ----------------------------------------------------

        if target is None:

            anomalies.add(
                (
                    "ORPHAN_TARGET",
                    rid,
                    str(tid),
                )
            )

        signature = signatures.get(
            rtype
        )

        if not signature:
            continue

        # ----------------------------------------------------
        # Domain
        # ----------------------------------------------------

        if (
            source is not None
            and entity_type(source)
            != signature["domaine"]
        ):

            anomalies.add(
                (
                    "INVALID_SOURCE_TYPE",
                    rid,
                    entity_type(source),
                    signature["domaine"],
                )
            )

        # ----------------------------------------------------
        # Range / image
        # ----------------------------------------------------

        if (
            target is not None
            and entity_type(target)
            != signature["image"]
        ):

            anomalies.add(
                (
                    "INVALID_TARGET_TYPE",
                    rid,
                    entity_type(target),
                    signature["image"],
                )
            )

    return anomalies


# ============================================================
# PAGE PROFILE
# ============================================================

def page_profile(entities):

    pages = set()

    for entity in entities:

        page = entity_page(
            entity
        )

        if page is not None:
            pages.add(page)

    sorted_pages = sorted(
        pages,
        key=lambda x: str(x),
    )

    return {

        "pages":
            sorted_pages,

        "same_page":
            len(pages) <= 1,

        "cross_page":
            len(pages) > 1,
    }


# ============================================================
# ATTRIBUTE COMPARISON
# ============================================================

def explicit_values(entities, getter):

    values = []

    for entity in entities:

        value = getter(
            entity
        )

        if value is not None:
            values.append(value)

    return values


def conflicting_values(
    entities,
    getter,
):

    values = explicit_values(
        entities,
        getter,
    )

    unique_values = set(
        values
    )

    return (
        len(unique_values) > 1,
        unique_values,
    )


def explicit_same_value(
    entities,
    getter,
):
    """
    Une preuve positive n'existe que si au moins deux
    occurrences ont explicitement la même valeur.
    """

    values = explicit_values(
        entities,
        getter,
    )

    if len(values) < 2:
        return False

    return (
        len(set(values)) == 1
    )


# ============================================================
# RELATIONAL CONTEXT
# ============================================================

def normalized_relation_types(entity):

    relations = (
        entity.get("relations", {})
        or {}
    )

    incoming = set()
    outgoing = set()

    for item in (
        relations.get(
            "incoming",
            [],
        )
        or []
    ):

        if (
            isinstance(
                item,
                (list, tuple),
            )
            and len(item) >= 1
        ):

            value = normalize_value(
                item[0]
            )

            if value is not None:
                incoming.add(value)

    for item in (
        relations.get(
            "outgoing",
            [],
        )
        or []
    ):

        if (
            isinstance(
                item,
                (list, tuple),
            )
            and len(item) >= 1
        ):

            value = normalize_value(
                item[0]
            )

            if value is not None:
                outgoing.add(value)

    return {
        "incoming": incoming,
        "outgoing": outgoing,
    }


def jaccard(a, b):

    if not a and not b:
        return None

    union = a | b

    if not union:
        return None

    return (
        len(a & b)
        / len(union)
    )


def relation_similarity(entities):

    profiles = [
        normalized_relation_types(
            entity
        )
        for entity in entities
    ]

    scores = []

    for i in range(
        len(profiles)
    ):

        for j in range(
            i + 1,
            len(profiles),
        ):

            a = (
                profiles[i]["incoming"]
                | profiles[i]["outgoing"]
            )

            b = (
                profiles[j]["incoming"]
                | profiles[j]["outgoing"]
            )

            score = jaccard(
                a,
                b,
            )

            if score is not None:
                scores.append(score)

    if not scores:
        return None

    return (
        sum(scores)
        / len(scores)
    )


def relation_context_profile(
    entities,
):

    profiles = [
        normalized_relation_types(
            entity
        )
        for entity in entities
    ]

    with_relations = 0

    for profile in profiles:

        if (
            profile["incoming"]
            or profile["outgoing"]
        ):
            with_relations += 1

    without_relations = (
        len(profiles)
        - with_relations
    )

    similarity = (
        relation_similarity(
            entities
        )
    )

    return {

        "entities_with_relations":
            with_relations,

        "entities_without_relations":
            without_relations,

        "relation_similarity":
            similarity,
    }


# ============================================================
# CONTEXT EVALUATION
# ============================================================

def evaluate_context(entities):

    negation_conflict, negation_values = (
        conflicting_values(
            entities,
            entity_negation,
        )
    )

    temporal_conflict, temporal_values = (
        conflicting_values(
            entities,
            entity_time,
        )
    )

    value_conflict, value_values = (
        conflicting_values(
            entities,
            entity_value,
        )
    )

    unit_conflict, unit_values = (
        conflicting_values(
            entities,
            entity_unit,
        )
    )

    pages = page_profile(
        entities
    )

    relations = (
        relation_context_profile(
            entities
        )
    )

    return {

        # ----------------------------------------------------
        # Conflicts
        # ----------------------------------------------------

        "negation_conflict":
            negation_conflict,

        "temporal_conflict":
            temporal_conflict,

        "value_conflict":
            value_conflict,

        "unit_conflict":
            unit_conflict,

        # ----------------------------------------------------
        # Explicit values
        # ----------------------------------------------------

        "negation_values":
            sorted(
                str(x)
                for x in negation_values
            ),

        "temporal_values":
            sorted(
                str(x)
                for x in temporal_values
            ),

        "value_values":
            sorted(
                str(x)
                for x in value_values
            ),

        "unit_values":
            sorted(
                str(x)
                for x in unit_values
            ),

        # ----------------------------------------------------
        # Page information
        # ----------------------------------------------------

        **pages,

        # ----------------------------------------------------
        # Relation information
        # ----------------------------------------------------

        **relations,
    }


# ============================================================
# COREFERENCE EVIDENCE
# ============================================================

def coreference_evidence(
    entities,
    context,
):

    evidence = []

    # --------------------------------------------------------
    # Same explicit temporal context
    # --------------------------------------------------------

    if explicit_same_value(
        entities,
        entity_time,
    ):

        evidence.append(
            "SAME_EXPLICIT_TEMPORAL_CONTEXT"
        )

    # --------------------------------------------------------
    # Same explicit value
    # --------------------------------------------------------

    if explicit_same_value(
        entities,
        entity_value,
    ):

        evidence.append(
            "SAME_EXPLICIT_VALUE"
        )

    # --------------------------------------------------------
    # Same explicit unit
    # --------------------------------------------------------

    if explicit_same_value(
        entities,
        entity_unit,
    ):

        evidence.append(
            "SAME_EXPLICIT_UNIT"
        )

    # --------------------------------------------------------
    # Same explicit negation state
    # --------------------------------------------------------

    if explicit_same_value(
        entities,
        entity_negation,
    ):

        evidence.append(
            "SAME_NEGATION_STATUS"
        )

    # --------------------------------------------------------
    # Strong relational similarity
    # --------------------------------------------------------

    relation_score = (
        context.get(
            "relation_similarity"
        )
    )

    if (
        relation_score is not None
        and relation_score
        >= RELATION_SIMILARITY_THRESHOLD
    ):

        evidence.append(
            "STRONG_RELATIONAL_CONTEXT_SIMILARITY"
        )

    return {

        "evidence":
            evidence,

        "evidence_count":
            len(evidence),

        "relation_similarity":
            relation_score,
    }


# ============================================================
# MERGE SIMULATION
# ============================================================

def merge_simulation(
    doc,
    keep_id,
    remove_ids,
):

    simulated = copy.deepcopy(
        doc
    )

    keep_id = str(
        keep_id
    )

    remove_ids = {
        str(x)
        for x in remove_ids
    }

    # --------------------------------------------------------
    # Redirect relations
    # --------------------------------------------------------

    for relation_list in relation_lists(
        simulated
    ):

        for relation in relation_list:

            source = relation_source(
                relation
            )

            target = relation_target(
                relation
            )

            if str(source) in remove_ids:

                set_relation_source(
                    relation,
                    keep_id,
                )

            if str(target) in remove_ids:

                set_relation_target(
                    relation,
                    keep_id,
                )

    # --------------------------------------------------------
    # Remove merged entities
    # --------------------------------------------------------

    for entity_list in entity_lists(
        simulated
    ):

        entity_list[:] = [

            entity

            for entity in entity_list

            if str(
                entity_id(entity)
            ) not in remove_ids
        ]

    # --------------------------------------------------------
    # Remove duplicate relations produced by rewiring
    # --------------------------------------------------------

    seen = set()

    for relation_list in relation_lists(
        simulated
    ):

        cleaned = []

        for relation in relation_list:

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

            if key in seen:
                continue

            seen.add(
                key
            )

            cleaned.append(
                relation
            )

        relation_list[:] = cleaned

    return simulated


# ============================================================
# CANDIDATE IDS
# ============================================================

def candidate_entity_ids(
    entities,
):

    ids = []

    for entity in entities:

        eid = (
            entity.get("entity_id")
            or entity.get(
                "identifiant_entite"
            )
            or entity.get("id")
        )

        if eid is not None:

            ids.append(
                str(eid)
            )

    return sorted(
        set(ids)
    )


# ============================================================
# DECISION ENGINE
# ============================================================

def decide_duplicate_entity(
    entities,
    context,
    new_anomalies,
):

    # ========================================================
    # 1. BLOCKING CLINICAL CONFLICTS
    # ========================================================

    blocking_conflicts = []

    if context.get(
        "negation_conflict"
    ):

        blocking_conflicts.append(
            "NEGATION_CONFLICT"
        )

    if context.get(
        "temporal_conflict"
    ):

        blocking_conflicts.append(
            "TEMPORAL_CONFLICT"
        )

    if context.get(
        "value_conflict"
    ):

        blocking_conflicts.append(
            "VALUE_CONFLICT"
        )

    if context.get(
        "unit_conflict"
    ):

        blocking_conflicts.append(
            "UNIT_CONFLICT"
        )

    if blocking_conflicts:

        return {

            "final_status":
                "KEEP_SEPARATE",

            "reason":
                (
                    "Conflit clinique explicite entre "
                    "les occurrences candidates."
                ),

            "blocking_conflicts":
                blocking_conflicts,

            "coreference":
                None,
        }

    # ========================================================
    # 2. ONTOLOGY / STRUCTURE SAFETY
    # ========================================================

    if new_anomalies:

        return {

            "final_status":
                "KEEP_SEPARATE",

            "reason":
                (
                    "La fusion simulée introduit de "
                    "nouvelles anomalies structurelles "
                    "ou ontologiques."
                ),

            "blocking_conflicts": [
                "NEW_ONTOLOGY_ANOMALY"
            ],

            "coreference":
                None,
        }

    # ========================================================
    # 3. POSITIVE COREFERENCE EVIDENCE
    # ========================================================

    coreference = (
        coreference_evidence(
            entities,
            context,
        )
    )

    evidence_count = (
        coreference[
            "evidence_count"
        ]
    )

    # ========================================================
    # 4. SAFE MERGE
    # ========================================================

    if (
        evidence_count
        >= MIN_COREFERENCE_EVIDENCE
    ):

        return {

            "final_status":
                "SAFE_MERGE",

            "reason":
                (
                    "Aucun conflit explicite, aucune "
                    "nouvelle anomalie après simulation "
                    "et plusieurs preuves positives "
                    "indépendantes de coréférence."
                ),

            "blocking_conflicts":
                [],

            "coreference":
                coreference,
        }

    # ========================================================
    # 5. REVIEW
    # ========================================================

    return {

        "final_status":
            "REVIEW",

        "reason":
            (
                "La fusion est structurellement possible, "
                "mais les preuves positives de coréférence "
                "sont insuffisantes pour autoriser une "
                "fusion automatique."
            ),

        "blocking_conflicts":
            [],

        "coreference":
            coreference,
    }


# ============================================================
# MAIN
# ============================================================

def main():

    # ========================================================
    # LOAD CANDIDATES
    # ========================================================

    candidates = load_json(
        INPUT_FILE
    )

    if not isinstance(
        candidates,
        list,
    ):

        raise ValueError(
            "duplicate_entity_candidates.json "
            "doit contenir une liste."
        )

    # ========================================================
    # LOAD ONTOLOGY
    # ========================================================

    signatures = (
        load_signatures()
    )

    # ========================================================
    # LOAD CLINICAL DOCUMENTS
    # ========================================================

    documents = {}

    for path in CLINICAL_DIR.glob(
        "*.json"
    ):

        if path.name.endswith(
            "_report.json"
        ):
            continue

        try:

            documents[
                path.name
            ] = load_json(path)

        except Exception:
            continue

    # ========================================================
    # VALIDATION
    # ========================================================

    validated = []

    for candidate in candidates:

        candidate_id = (
            candidate.get(
                "candidate_id"
            )
        )

        document_name = (
            candidate.get(
                "document"
            )
        )

        document = (
            documents.get(
                document_name
            )
        )

        entities = (
            candidate.get(
                "entities",
                [],
            )
            or []
        )

        # ====================================================
        # BASIC VALIDATION
        # ====================================================

        if document is None:

            validated.append({

                "candidate_id":
                    candidate_id,

                "document":
                    document_name,

                "final_status":
                    "REVIEW",

                "reason":
                    "Document clinique introuvable.",
            })

            continue

        if len(entities) < 2:

            validated.append({

                "candidate_id":
                    candidate_id,

                "document":
                    document_name,

                "final_status":
                    "REVIEW",

                "reason":
                    "Moins de deux entités candidates.",
            })

            continue

        # ====================================================
        # TYPE CHECK
        # ====================================================

        types = set()

        for entity in entities:

            value = normalize_value(
                entity.get(
                    "entity_type"
                )
            )

            if value is not None:
                types.add(value)

        # ====================================================
        # TEXT CHECK
        # ====================================================

        texts = set()

        for entity in entities:

            value = normalize_value(
                entity.get(
                    "normalized_text"
                )
            )

            if value is not None:
                texts.add(value)

        if (
            len(types) != 1
            or len(texts) != 1
        ):

            validated.append({

                "candidate_id":
                    candidate_id,

                "document":
                    document_name,

                "entity_type":
                    candidate.get(
                        "entity_type"
                    ),

                "normalized_text":
                    candidate.get(
                        "normalized_text"
                    ),

                "final_status":
                    "KEEP_SEPARATE",

                "reason":
                    (
                        "Types ou contenus normalisés "
                        "incompatibles."
                    ),
            })

            continue

        # ====================================================
        # CONTEXT
        # ====================================================

        context = evaluate_context(
            entities
        )

        # ====================================================
        # ENTITY IDS
        # ====================================================

        ids = candidate_entity_ids(
            entities
        )

        if len(ids) < 2:

            validated.append({

                "candidate_id":
                    candidate_id,

                "document":
                    document_name,

                "entity_type":
                    candidate.get(
                        "entity_type"
                    ),

                "normalized_text":
                    candidate.get(
                        "normalized_text"
                    ),

                "final_status":
                    "REVIEW",

                "reason":
                    (
                        "Identifiants d'entités "
                        "insuffisants."
                    ),

                "context":
                    context,
            })

            continue

        # ====================================================
        # CANONICAL ID FOR SIMULATION
        # ====================================================

        keep_id = ids[0]

        remove_ids = set(
            ids[1:]
        )

        # ====================================================
        # AUDIT BEFORE
        # ====================================================

        before = audit_document(
            document,
            signatures,
        )

        # ====================================================
        # SIMULATE MERGE
        # ====================================================

        simulated = merge_simulation(
            document,
            keep_id,
            remove_ids,
        )

        # ====================================================
        # AUDIT AFTER
        # ====================================================

        after = audit_document(
            simulated,
            signatures,
        )

        new_anomalies = (
            after - before
        )

        resolved_anomalies = (
            before - after
        )

        # ====================================================
        # DECISION
        # ====================================================

        decision = (
            decide_duplicate_entity(
                entities=entities,
                context=context,
                new_anomalies=new_anomalies,
            )
        )

        status = (
            decision[
                "final_status"
            ]
        )

        reason = (
            decision[
                "reason"
            ]
        )

        # ====================================================
        # STORE RESULT
        # ====================================================

        validated.append({

            "candidate_id":
                candidate_id,

            "document":
                document_name,

            "entity_type":
                candidate.get(
                    "entity_type"
                ),

            "normalized_text":
                candidate.get(
                    "normalized_text"
                ),

            "entity_count":
                len(entities),

            "final_status":
                status,

            "reason":
                reason,

            "keep_entity_id":
                keep_id,

            "remove_entity_ids":
                sorted(
                    remove_ids
                ),

            "cross_page":
                context.get(
                    "cross_page"
                ),

            "pages":
                context.get(
                    "pages",
                    [],
                ),

            "context":
                context,

            "blocking_conflicts":
                decision.get(
                    "blocking_conflicts",
                    [],
                ),

            "coreference":
                decision.get(
                    "coreference"
                ),

            "before_anomaly_count":
                len(before),

            "after_anomaly_count":
                len(after),

            "new_anomaly_count":
                len(new_anomalies),

            "resolved_anomaly_count":
                len(resolved_anomalies),
        })

    # ========================================================
    # STATISTICS
    # ========================================================

    status_counter = Counter(

        item.get(
            "final_status",
            "UNKNOWN",
        )

        for item in validated
    )

    type_status_counter = {}

    for item in validated:

        entity_type_name = (
            item.get(
                "entity_type"
            )
            or "UNKNOWN"
        )

        status = (
            item.get(
                "final_status"
            )
            or "UNKNOWN"
        )

        if (
            entity_type_name
            not in type_status_counter
        ):

            type_status_counter[
                entity_type_name
            ] = Counter()

        type_status_counter[
            entity_type_name
        ][status] += 1

    # ========================================================
    # SAFE MERGES
    # ========================================================

    safe_merges = [

        item

        for item in validated

        if item.get(
            "final_status"
        ) == "SAFE_MERGE"
    ]

    # ========================================================
    # REVIEWS
    # ========================================================

    reviews = [

        item

        for item in validated

        if item.get(
            "final_status"
        ) == "REVIEW"
    ]

    # ========================================================
    # KEEP SEPARATE
    # ========================================================

    keep_separate = [

        item

        for item in validated

        if item.get(
            "final_status"
        ) == "KEEP_SEPARATE"
    ]

    # ========================================================
    # OUTPUT
    # ========================================================

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output = {

        "validator":
            "duplicate_entity_validator",

        "version":
            "V3_GENERIC_MULTI_EVIDENCE",

        "input":
            str(INPUT_FILE),

        "clinical_input":
            str(CLINICAL_DIR),

        "configuration": {

            "minimum_coreference_evidence":
                MIN_COREFERENCE_EVIDENCE,

            "relation_similarity_threshold":
                RELATION_SIMILARITY_THRESHOLD,
        },

        "summary": {

            "candidate_count":
                len(candidates),

            "validated_count":
                len(validated),

            "safe_merge":
                len(safe_merges),

            "keep_separate":
                len(keep_separate),

            "review":
                len(reviews),

            "statuses":
                dict(status_counter),
        },

        "validated":
            validated,

        "safe_merges":
            safe_merges,

        "keep_separate":
            keep_separate,

        "reviews":
            reviews,
    }

    OUTPUT_FILE.write_text(

        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        ),

        encoding="utf-8",
    )

    # ========================================================
    # CONSOLE
    # ========================================================

    print(
        "=" * 104
    )

    print(
        "TRACE / SGCE - DUPLICATE ENTITY VALIDATOR "
        "V3 - GENERIC MULTI-EVIDENCE"
    )

    print(
        "=" * 104
    )

    print(
        f"Candidats reçus                      : "
        f"{len(candidates)}"
    )

    print(
        f"Candidats validés                    : "
        f"{len(validated)}"
    )

    print()

    # --------------------------------------------------------
    # Status
    # --------------------------------------------------------

    print(
        "STATUTS"
    )

    print(
        "-" * 104
    )

    for status, count in (
        status_counter.most_common()
    ):

        print(
            f"{status:<48}: {count}"
        )

    # --------------------------------------------------------
    # By type
    # --------------------------------------------------------

    print()

    print(
        "STATUTS PAR TYPE D'ENTITE"
    )

    print(
        "-" * 104
    )

    for type_name in sorted(
        type_status_counter
    ):

        counter = (
            type_status_counter[
                type_name
            ]
        )

        details = ", ".join(

            f"{status}={count}"

            for status, count
            in counter.most_common()
        )

        total = sum(
            counter.values()
        )

        print(
            f"{type_name:<40}: "
            f"{total:<5} | {details}"
        )

    # --------------------------------------------------------
    # Safe merge examples
    # --------------------------------------------------------

    print()

    print(
        "SAFE MERGE"
    )

    print(
        "-" * 104
    )

    if not safe_merges:

        print(
            "Aucune fusion automatique validée."
        )

    else:

        for item in safe_merges[:20]:

            coreference = (
                item.get(
                    "coreference"
                )
                or {}
            )

            evidence = (
                coreference.get(
                    "evidence",
                    [],
                )
            )

            print(
                f"{item.get('document')} | "
                f"{item.get('entity_type')} | "
                f"{item.get('normalized_text')} | "
                f"{item.get('keep_entity_id')} <- "
                f"{item.get('remove_entity_ids')} | "
                f"preuves={evidence}"
            )

        if len(safe_merges) > 20:

            print(
                f"... + "
                f"{len(safe_merges) - 20} "
                f"autres SAFE_MERGE"
            )

    # --------------------------------------------------------
    # Output
    # --------------------------------------------------------

    print()

    print(
        f"Sortie                               : "
        f"{OUTPUT_FILE}"
    )

    print()

    print(
        "Aucune donnée clinique n'a été modifiée."
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()