# -*- coding: utf-8 -*-

import json
from pathlib import Path
from collections import Counter

# ============================================================
# PATHS
# ============================================================

BASE = Path(
    r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM"
    r"\Reduction_hallucinations"
)

SEMANTIC_ROOT = BASE / "MultiAgent" / "semantic_factual"

CANDIDATES_FILE = (
    SEMANTIC_ROOT
    / "queues"
    / "semantic_factual_candidates.json"
)

OUTPUT_FILE = (
    SEMANTIC_ROOT
    / "outputs"
    / "unresolved_endpoint_audit.json"
)


# ============================================================
# UTILITIES
# ============================================================

def load_json(path):
    return json.loads(
        Path(path).read_text(encoding="utf-8")
    )


def save_json(path, data):
    Path(path).parent.mkdir(
        parents=True,
        exist_ok=True
    )

    Path(path).write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


def normalize_text(value):
    if value is None:
        return ""

    return " ".join(
        str(value)
        .strip()
        .casefold()
        .split()
    )


# ============================================================
# ENTITY EXTRACTION
# ============================================================

def walk(obj, path=()):
    """
    Parcours rÃ©cursif du JSON.
    """

    if isinstance(obj, dict):

        yield obj, path

        for key, value in obj.items():
            yield from walk(
                value,
                path + (key,)
            )

    elif isinstance(obj, list):

        for index, value in enumerate(obj):
            yield from walk(
                value,
                path + (index,)
            )


def get_entity_id(entity):
    """
    Recherche gÃ©nÃ©rique de l'identifiant d'une entitÃ©.
    """

    if not isinstance(entity, dict):
        return ""

    possible_fields = (
        "identifiant_entite",
        "entity_id",
        "id",
        "uid",
        "ID"
    )

    for field in possible_fields:

        value = entity.get(field)

        if value not in (None, ""):
            return str(value).strip()

    return ""


def get_entity_text(entity):
    """
    Recherche gÃ©nÃ©rique du texte de l'entitÃ©.
    """

    if not isinstance(entity, dict):
        return ""

    possible_fields = (
        "text",
        "mention",
        "entite",
        "name",
        "nom"
    )

    for field in possible_fields:

        value = entity.get(field)

        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


def get_entity_type(entity):

    if not isinstance(entity, dict):
        return ""

    possible_fields = (
        "type_entite",
        "entity_type",
        "type",
        "label",
        "category"
    )

    for field in possible_fields:

        value = entity.get(field)

        if value not in (None, ""):
            return str(value).strip()

    return ""


def collect_entities(document):
    """
    Collecte toutes les entitÃ©s prÃ©sentes dans le JSON.
    """

    entities = []

    entity_container_names = {
        "entities",
        "entites",
        "global_entities",
        "entity_list",
        "extracted_entities"
    }

    for obj, path in walk(document):

        if not isinstance(obj, dict):
            continue

        for key, value in obj.items():

            if (
                str(key).lower()
                not in entity_container_names
            ):
                continue

            if not isinstance(value, list):
                continue

            for index, entity in enumerate(value):

                if not isinstance(entity, dict):
                    continue

                entity_id = get_entity_id(entity)
                entity_text = get_entity_text(entity)

                if not entity_id and not entity_text:
                    continue

                entities.append({
                    "id": entity_id,
                    "text": entity_text,
                    "type": get_entity_type(entity),
                    "path": list(
                        path + (key, index)
                    )
                })

    # DÃ©duplication logique
    unique = {}

    for entity in entities:

        key = (
            entity["id"],
            normalize_text(entity["text"]),
            entity["type"]
        )

        if key not in unique:
            unique[key] = entity

    return list(unique.values())


# ============================================================
# SEARCH MISSING ENDPOINT
# ============================================================

def audit_endpoint(
    expected_id,
    expected_text,
    entities
):

    expected_id = str(
        expected_id or ""
    ).strip()

    expected_norm = normalize_text(
        expected_text
    )

    # --------------------------------------------------------
    # 1. Exact ID
    # --------------------------------------------------------

    id_matches = [
        entity
        for entity in entities
        if entity["id"] == expected_id
    ]

    if len(id_matches) == 1:

        return {
            "classification":
                "ID_FOUND_AFTER_RESCAN",

            "safe_repair_possible":
                False,

            "matches":
                id_matches
        }

    # --------------------------------------------------------
    # 2. Same text under another ID
    # --------------------------------------------------------

    text_matches = [
        entity
        for entity in entities
        if (
            expected_norm
            and normalize_text(
                entity["text"]
            ) == expected_norm
        )
    ]

    if len(text_matches) == 1:

        candidate = text_matches[0]

        if (
            candidate["id"]
            and candidate["id"]
            != expected_id
        ):

            return {
                "classification":
                    "SAME_TEXT_OTHER_ID",

                "safe_repair_possible":
                    True,

                "proposed_new_id":
                    candidate["id"],

                "matches":
                    text_matches
            }

    # --------------------------------------------------------
    # 3. Several entities with same text
    # --------------------------------------------------------

    if len(text_matches) > 1:

        return {
            "classification":
                "AMBIGUOUS_MATCH",

            "safe_repair_possible":
                False,

            "matches":
                text_matches
        }

    # --------------------------------------------------------
    # 4. No match
    # --------------------------------------------------------

    return {
        "classification":
            "TRULY_MISSING",

        "safe_repair_possible":
            False,

        "matches":
            []
    }


# ============================================================
# MAIN
# ============================================================

print("=" * 115)
print(
    "TRACE / SGCE - UNRESOLVED ENDPOINT AUDIT "
    "- READ ONLY"
)
print("=" * 115)


data = load_json(
    CANDIDATES_FILE
)

candidates = data.get(
    "candidates",
    []
)


# ============================================================
# IDENTIFY UNRESOLVED RELATIONS
# ============================================================

SAFE_RESOLUTIONS = {
    "ID_EXACT",
    "ID_DUPLICATE_EQUIVALENT",
    "ID_PLUS_TEXT",
    "TEXT_EXACT"
}


unresolved_cases = []

for relation in candidates:

    source_resolution = relation.get(
        "source_resolution",
        ""
    )

    target_resolution = relation.get(
        "target_resolution",
        ""
    )

    if source_resolution not in SAFE_RESOLUTIONS:

        unresolved_cases.append({
            "endpoint": "SOURCE",
            "relation": relation
        })

    if target_resolution not in SAFE_RESOLUTIONS:

        unresolved_cases.append({
            "endpoint": "TARGET",
            "relation": relation
        })


print(
    f"Endpoints non rÃ©solus dÃ©tectÃ©s      : "
    f"{len(unresolved_cases)}"
)


# ============================================================
# CACHE DOCUMENTS
# ============================================================

document_cache = {}

results = []

classification_counts = Counter()


for case in unresolved_cases:

    relation = case["relation"]

    endpoint = case["endpoint"]

    document_name = relation.get(
        "document"
    )

    # --------------------------------------------------------
    # Locate clinical document
    # --------------------------------------------------------

    clinical_directory = (
        BASE
        / "MultiAgent"
        / "negation_audit"
        / "negation_safe_corrected_repaired"
    )

    document_path = (
        clinical_directory
        / document_name
    )

    if not document_path.exists():

        result = {
            "document": document_name,
            "relation_id":
                relation.get("relation_id"),

            "endpoint": endpoint,

            "classification":
                "DOCUMENT_NOT_FOUND",

            "safe_repair_possible":
                False
        }

        results.append(result)

        classification_counts[
            "DOCUMENT_NOT_FOUND"
        ] += 1

        continue

    # --------------------------------------------------------
    # Load document once
    # --------------------------------------------------------

    if document_name not in document_cache:

        document = load_json(
            document_path
        )

        entities = collect_entities(
            document
        )

        document_cache[
            document_name
        ] = entities

    else:

        entities = document_cache[
            document_name
        ]

    # --------------------------------------------------------
    # Endpoint information
    # --------------------------------------------------------

    if endpoint == "SOURCE":

        expected_id = relation.get(
            "source_id"
        )

        expected_text = (
            relation.get(
                "source_text_relation"
            )
            or relation.get(
                "source_text"
            )
        )

        original_resolution = (
            relation.get(
                "source_resolution"
            )
        )

    else:

        expected_id = relation.get(
            "target_id"
        )

        expected_text = (
            relation.get(
                "target_text_relation"
            )
            or relation.get(
                "target_text"
            )
        )

        original_resolution = (
            relation.get(
                "target_resolution"
            )
        )

    # --------------------------------------------------------
    # Audit
    # --------------------------------------------------------

    audit = audit_endpoint(
        expected_id,
        expected_text,
        entities
    )

    result = {
        "document":
            document_name,

        "relation_id":
            relation.get(
                "relation_id"
            ),

        "page":
            relation.get(
                "page"
            ),

        "relation_type":
            relation.get(
                "relation_name"
            ),

        "endpoint":
            endpoint,

        "original_resolution":
            original_resolution,

        "expected_id":
            expected_id,

        "expected_text":
            expected_text,

        "preuve":
            relation.get(
                "proof"
            ),

        **audit
    }

    results.append(
        result
    )

    classification_counts[
        audit["classification"]
    ] += 1


# ============================================================
# SAVE REPORT
# ============================================================

report = {

    "audit":
        "unresolved_endpoint_audit",

    "mode":
        "READ_ONLY",

    "summary": {

        "unresolved_endpoints":
            len(unresolved_cases),

        "classifications":
            dict(
                classification_counts
            ),

        "safe_repairs_detected":
            sum(
                1
                for result in results
                if result.get(
                    "safe_repair_possible"
                )
            )
    },

    "cases":
        results
}


save_json(
    OUTPUT_FILE,
    report
)


# ============================================================
# CONSOLE REPORT
# ============================================================

print()

print(
    "CLASSIFICATIONS"
)

print("-" * 115)

for classification, count in (
    classification_counts.most_common()
):

    print(
        f"{classification:<55}: "
        f"{count}"
    )


print()

print(
    "DETAIL DES ENDPOINTS"
)

print("-" * 115)


for result in results:

    print()

    print(
        f"{result.get('document')} | "
        f"{result.get('relation_id')} | "
        f"{result.get('endpoint')}"
    )

    print(
        f"  ID attendu    : "
        f"{result.get('expected_id')}"
    )

    print(
        f"  Texte attendu : "
        f"{result.get('expected_text')}"
    )

    print(
        f"  Relation      : "
        f"{result.get('relation_type')}"
    )

    print(
        f"  PREUVE        : "
        f"{result.get('preuve')!r}"
    )

    print(
        f"  RESULTAT      : "
        f"{result.get('classification')}"
    )

    if result.get(
        "classification"
    ) == "SAME_TEXT_OTHER_ID":

        print(
            f"  ID candidat   : "
            f"{result.get('proposed_new_id')}"
        )

        print(
            "  RÃ©paration ID potentiellement sÃ»re"
        )

    elif result.get(
        "classification"
    ) == "AMBIGUOUS_MATCH":

        print(
            f"  Correspondances : "
            f"{len(result.get('matches', []))}"
        )


print()

print("=" * 115)

print(
    f"Rapport                              : "
    f"{OUTPUT_FILE}"
)

print()

print(
    "Aucune donnÃ©e clinique n'a Ã©tÃ© modifiÃ©e."
)
