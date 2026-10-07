# -*- coding: utf-8 -*-
"""
TRACE-Sepsis — V6.6c ENTITES PRECISION+ — 43 documents

ENTREE :
    BEST_43_Entites_V6_6b_CONSERVATIVE

SORTIE :
    BEST_43_Entites_V6_6c_PRECISION_PLUS

Aucun appel Mistral/API.

Cette version vise principalement la réduction des faux positifs :
1) déduplication temporelle par containment (on garde la forme la plus courte) ;
2) suppression des symptômes explicitement négatifs ;
3) suppression du contexte d'acquisition générique "infection nosocomiale" ;
4) suppression du traitement générique "antibiothérapie" ;
5) suppression du faux traitement "NA" ;
6) déduplication d'imagerie par containment (on garde la forme la plus précise/longue) ;
7) déduplication SCORE_NEUROLOGIQUE (on garde la forme la plus précise/longue) ;
8) suppression de quelques durées horaires isolées très souvent non annotées.

Le matcher et son seuil relaxed 0.85 ne sont PAS modifiés.
"""

import copy
import json
import os
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path


# ============================================================
# CHEMINS
# ============================================================

if os.name == "nt":
    BASE_DIR = (
        Path(os.environ.get("USERPROFILE", str(Path.home())))
        / "Desktop"
        / "TRACE"
        / "OCR vers LLM"
    )
else:
    BASE_DIR = Path.home() / "TRACE" / "OCR vers LLM"


DEFAULT_INPUT_DIR = (
    BASE_DIR
    / "BEST_43_Entites_V6_6b_CONSERVATIVE"
)

DEFAULT_OUTPUT_DIR = (
    BASE_DIR
    / "BEST_43_Entites_V6_6c_PRECISION_PLUS"
)


# ============================================================
# NORMALISATION
# ============================================================

def remove_accents(value):
    value = "" if value is None else str(value)
    value = unicodedata.normalize("NFD", value)
    return "".join(
        char
        for char in value
        if unicodedata.category(char) != "Mn"
    )


def normalize(value):
    value = remove_accents(value).lower()

    value = (
        value
        .replace("’", "'")
        .replace("`", "'")
        .replace("\u00a0", " ")
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    value = value.strip(
        " \t\r\n,;:.()[]{}"
    )

    return value


def entity_id(entity):
    return str(
        entity.get("identifiant_entite")
        or entity.get("id")
        or ""
    ).strip()


def entity_type(entity):
    return str(
        entity.get("categorie")
        or entity.get("type")
        or ""
    ).strip()


def entity_surface(entity):
    return str(
        entity.get("preuve")
        or entity.get("name")
        or entity.get("nom")
        or ""
    ).strip()


# ============================================================
# RELATION IDS
# ============================================================

def relation_subject_id(relation):
    return str(
        relation.get("identifiant_entite_sujet")
        or relation.get("subject_id")
        or relation.get("from_id")
        or ""
    ).strip()


def relation_object_id(relation):
    return str(
        relation.get("identifiant_entite_objet")
        or relation.get("object_id")
        or relation.get("to_id")
        or ""
    ).strip()


# ============================================================
# UNION-FIND POUR DEDUP
# ============================================================

def build_containment_clusters(entities):
    """
    Construit des clusters d'entités dont les surfaces se contiennent.
    Le clustering reste local à une page et à un type donné.
    """
    if len(entities) < 2:
        return []

    parent = list(range(len(entities)))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(first, second):
        root_a = find(first)
        root_b = find(second)

        if root_a != root_b:
            parent[root_b] = root_a

    normalized = [
        normalize(
            entity_surface(entity)
        )
        for entity in entities
    ]

    for i in range(len(entities)):
        a = normalized[i]

        if len(a) < 4:
            continue

        for j in range(i + 1, len(entities)):
            b = normalized[j]

            if len(b) < 4:
                continue

            if (
                a in b
                or b in a
            ):
                union(i, j)

    grouped = {}

    for index in range(len(entities)):
        root = find(index)

        grouped.setdefault(
            root,
            []
        ).append(
            index
        )

    return [
        indexes
        for indexes in grouped.values()
        if len(indexes) > 1
    ]


def dedup_by_containment(
    entities,
    category,
    keep_mode,
    stats
):
    """
    keep_mode:
      - "shortest" : garde la surface la plus courte.
      - "longest"  : garde la surface la plus longue.
    """
    indexes = [
        index
        for index, entity in enumerate(entities)
        if (
            isinstance(entity, dict)
            and entity_type(entity) == category
        )
    ]

    selected_entities = [
        entities[index]
        for index in indexes
    ]

    clusters = build_containment_clusters(
        selected_entities
    )

    remove_ids = set()

    for cluster in clusters:
        cluster_entities = [
            selected_entities[index]
            for index in cluster
        ]

        if keep_mode == "shortest":
            keeper = min(
                cluster_entities,
                key=lambda entity: (
                    len(
                        normalize(
                            entity_surface(entity)
                        )
                    ),
                    normalize(
                        entity_surface(entity)
                    ),
                )
            )

        elif keep_mode == "longest":
            keeper = max(
                cluster_entities,
                key=lambda entity: (
                    len(
                        normalize(
                            entity_surface(entity)
                        )
                    ),
                    normalize(
                        entity_surface(entity)
                    ),
                )
            )

        else:
            raise ValueError(
                f"keep_mode invalide : {keep_mode}"
            )

        keeper_id = entity_id(
            keeper
        )

        for entity in cluster_entities:
            current_id = entity_id(
                entity
            )

            if (
                current_id
                and current_id != keeper_id
            ):
                remove_ids.add(
                    current_id
                )

    if not remove_ids:
        return entities, set()

    output = []

    for entity in entities:
        current_id = entity_id(
            entity
        )

        if current_id in remove_ids:
            stats[
                f"removed_duplicate_{category}"
            ] += 1
            continue

        output.append(
            entity
        )

    return output, remove_ids


# ============================================================
# FILTRES
# ============================================================

NEGATIVE_SYMPTOM_PATTERN = re.compile(
    r"""
    ^(?:
        pas\s+de\b|
        pas\s+d'|
        absence\s+de\b|
        sans\b|
        aucun\b|
        aucune\b
    )
    """,
    re.IGNORECASE | re.VERBOSE
)


BAD_ISOLATED_HOURS = {
    "00h",
    "2h",
    "6h",
    "8h",
    "12h",
    "18h",
    "24h",
    "48h",
    "72h",
}


def should_remove_entity(
    entity,
    stats
):
    category = entity_type(
        entity
    )

    surface = entity_surface(
        entity
    )

    normalized = normalize(
        surface
    )

    # --------------------------------------------------------
    # 1) SYMPTOMES NÉGATIFS
    # --------------------------------------------------------
    if (
        category == "SYMPTOME"
        and NEGATIVE_SYMPTOM_PATTERN.search(
            normalized
        )
    ):
        stats[
            "removed_negative_SYMPTOME"
        ] += 1

        return True

    # --------------------------------------------------------
    # 2) CONTEXTE_ACQUISITION trop générique
    # --------------------------------------------------------
    if (
        category == "CONTEXTE_ACQUISITION"
        and normalized == "infection nosocomiale"
    ):
        stats[
            "removed_generic_CONTEXTE_ACQUISITION"
        ] += 1

        return True

    # --------------------------------------------------------
    # 3) TRAITEMENT générique
    # --------------------------------------------------------
    if (
        category == "TRAITEMENT"
        and normalized == "antibiotherapie"
    ):
        stats[
            "removed_generic_TRAITEMENT_antibiotherapie"
        ] += 1

        return True

    # "NA" a été observé comme faux traitement.
    if (
        category == "TRAITEMENT"
        and normalized == "na"
    ):
        stats[
            "removed_invalid_TRAITEMENT_NA"
        ] += 1

        return True

    # --------------------------------------------------------
    # 4) EVENEMENT_TEMPOREL - heures isolées à faible précision
    # --------------------------------------------------------
    if (
        category == "EVENEMENT_TEMPOREL"
        and normalized in BAD_ISOLATED_HOURS
    ):
        stats[
            "removed_isolated_hour_EVENT"
        ] += 1

        return True

    return False


# ============================================================
# NETTOYAGE RELATIONS
# ============================================================

def clean_relations(
    relations,
    valid_entity_ids,
    stats,
    counter_name
):
    if not isinstance(
        relations,
        list
    ):
        return []

    output = []

    for relation in relations:
        if not isinstance(
            relation,
            dict
        ):
            continue

        subject = relation_subject_id(
            relation
        )

        obj = relation_object_id(
            relation
        )

        # Si la relation n'utilise pas des IDs reconnaissables,
        # on la conserve pour ne pas casser un autre format.
        if not subject and not obj:
            output.append(
                relation
            )
            continue

        if (
            subject
            and subject not in valid_entity_ids
        ):
            stats[
                counter_name
            ] += 1
            continue

        if (
            obj
            and obj not in valid_entity_ids
        ):
            stats[
                counter_name
            ] += 1
            continue

        output.append(
            relation
        )

    return output


# ============================================================
# PAGE
# ============================================================

def process_page(
    page,
    stats
):
    page = copy.deepcopy(
        page
    )

    entities = page.get(
        "entities"
    )

    if not isinstance(
        entities,
        list
    ):
        entities = page.get(
            "entites",
            []
        )

    if not isinstance(
        entities,
        list
    ):
        entities = []

    entities = [
        copy.deepcopy(entity)
        for entity in entities
        if isinstance(
            entity,
            dict
        )
    ]

    # --------------------------------------------------------
    # A. FILTRES LEXICAUX
    # --------------------------------------------------------
    filtered = []

    for entity in entities:
        if should_remove_entity(
            entity,
            stats
        ):
            continue

        filtered.append(
            entity
        )

    entities = filtered

    # --------------------------------------------------------
    # B. TEMPORAL : garder la forme la plus courte
    #
    # Exemples :
    #   le 07/12/2014 + 07/12/2014 -> garder 07/12/2014
    #   depuis le 01/12 + 01/12 -> garder 01/12
    # --------------------------------------------------------
    entities, _ = dedup_by_containment(
        entities=entities,
        category="EVENEMENT_TEMPOREL",
        keep_mode="shortest",
        stats=stats
    )

    # --------------------------------------------------------
    # C. IMAGERIE : garder la forme la plus précise
    #
    # Exemples :
    #   radiographie + radiographie thoracique
    #   -> garder radiographie thoracique
    # --------------------------------------------------------
    entities, _ = dedup_by_containment(
        entities=entities,
        category="IMAGERIE_PROCEDURE",
        keep_mode="longest",
        stats=stats
    )

    # --------------------------------------------------------
    # D. SCORE NEURO : garder la forme la plus complète
    # --------------------------------------------------------
    entities, _ = dedup_by_containment(
        entities=entities,
        category="SCORE_NEUROLOGIQUE",
        keep_mode="longest",
        stats=stats
    )

    valid_ids = {
        entity_id(entity)
        for entity in entities
        if entity_id(entity)
    }

    page["entities"] = entities

    if "entites" in page:
        page["entites"] = entities

    if "relations" in page:
        page["relations"] = clean_relations(
            relations=page.get(
                "relations",
                []
            ),
            valid_entity_ids=valid_ids,
            stats=stats,
            counter_name=(
                "removed_page_relation_due_to_removed_entity"
            )
        )

    return page


# ============================================================
# DOCUMENT
# ============================================================

def process_document(
    data
):
    output = copy.deepcopy(
        data
    )

    stats = Counter()

    pages = output.get(
        "pages",
        []
    )

    if not isinstance(
        pages,
        list
    ):
        pages = []

    new_pages = []
    global_entities = []

    for page in pages:
        if not isinstance(
            page,
            dict
        ):
            new_pages.append(
                page
            )
            continue

        processed = process_page(
            page,
            stats
        )

        new_pages.append(
            processed
        )

        page_number = processed.get(
            "page"
        )

        for entity in processed.get(
            "entities",
            []
        ):
            if not isinstance(
                entity,
                dict
            ):
                continue

            entity_copy = copy.deepcopy(
                entity
            )

            entity_copy["page"] = (
                page_number
            )

            global_entities.append(
                entity_copy
            )

    output["pages"] = (
        new_pages
    )

    output["global_entities"] = (
        global_entities
    )

    valid_global_ids = {
        entity_id(entity)
        for entity in global_entities
        if entity_id(entity)
    }

    if "global_relations" in output:
        output["global_relations"] = (
            clean_relations(
                relations=output.get(
                    "global_relations",
                    []
                ),
                valid_entity_ids=valid_global_ids,
                stats=stats,
                counter_name=(
                    "removed_global_relation_due_to_removed_entity"
                )
            )
        )

    if isinstance(
        output.get(
            "document_summary"
        ),
        dict
    ):
        output[
            "document_summary"
        ][
            "total_entities"
        ] = len(
            global_entities
        )

        if isinstance(
            output.get(
                "global_relations"
            ),
            list
        ):
            output[
                "document_summary"
            ][
                "total_relations"
            ] = len(
                output[
                    "global_relations"
                ]
            )

    output[
        "entity_postprocessing_v66c"
    ] = {
        "version":
            "V6.6c_ENTITY_PRECISION_PLUS",

        "source":
            "V6.6b_ENTITY_CONSERVATIVE",

        "stats":
            dict(
                stats
            ),

        "total_entities":
            len(
                global_entities
            ),
    }

    return output, stats


# ============================================================
# DOSSIER
# ============================================================

def process_folder(
    input_dir,
    output_dir
):
    input_dir = Path(
        input_dir
    )

    output_dir = Path(
        output_dir
    )

    if not input_dir.is_dir():
        raise FileNotFoundError(
            f"Dossier d'entrée introuvable : {input_dir}"
        )

    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    for old_file in output_dir.glob(
        "*.json"
    ):
        try:
            old_file.unlink()
        except OSError:
            pass

    json_files = sorted(
        input_dir.glob(
            "*.json"
        )
    )

    print(
        "\n============================================================"
    )
    print(
        "TRACE-Sepsis — V6.6c ENTITES PRECISION+"
    )
    print(
        "============================================================"
    )
    print(
        "INPUT  :",
        input_dir
    )
    print(
        "OUTPUT :",
        output_dir
    )
    print(
        "JSON   :",
        len(
            json_files
        )
    )
    print(
        "============================================================\n"
    )

    if len(
        json_files
    ) != 43:
        print(
            f"⚠️ 43 documents attendus ; "
            f"{len(json_files)} trouvés."
        )

    global_stats = Counter()

    for index, source in enumerate(
        json_files,
        start=1
    ):
        with source.open(
            "r",
            encoding="utf-8"
        ) as file:
            data = json.load(
                file
            )

        before = len(
            data.get(
                "global_entities",
                []
            )
        )

        result, stats = (
            process_document(
                data
            )
        )

        global_stats.update(
            stats
        )

        after = len(
            result.get(
                "global_entities",
                []
            )
        )

        destination = (
            output_dir
            / source.name
        )

        with destination.open(
            "w",
            encoding="utf-8"
        ) as file:
            json.dump(
                result,
                file,
                ensure_ascii=False,
                indent=2
            )

        print(
            f"✅ {index:02d}/{len(json_files)} "
            f"{source.name} | "
            f"entités {before} -> {after}"
        )

    print(
        "\n--- CORRECTIONS V6.6c PRECISION+ ---"
    )

    for key, value in sorted(
        global_stats.items()
    ):
        print(
            f"{key:65s} : {value}"
        )

    print(
        "\n🏁 V6.6c ENTITES PRECISION+ terminée."
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    input_dir = (
        Path(
            sys.argv[1]
        )
        if len(sys.argv) >= 2
        else DEFAULT_INPUT_DIR
    )

    output_dir = (
        Path(
            sys.argv[2]
        )
        if len(sys.argv) >= 3
        else DEFAULT_OUTPUT_DIR
    )

    process_folder(
        input_dir,
        output_dir
    )
