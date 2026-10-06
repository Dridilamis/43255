# -*- coding: utf-8 -*-
"""
duplicate_entity_candidate_builder.py
=====================================

Construit les groupes de doublons d'entités à partir de la sortie clinique courante.

Entrée :
  MultiAgent/relation_repair/relation_repair_safe_corrected

Critère candidat :
- même document
- même type
- même contenu textuel normalisé
- IDs différents

Sortie :
  MultiAgent/duplicate_entity/queues/duplicate_entity_candidates.json

Aucune donnée clinique n'est modifiée.
"""

import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ONTOLOGY_DUPLICATES_DIR = ROOT.parent
STAGE4_DIR = ONTOLOGY_DUPLICATES_DIR.parent
REDUCTION_DIR = STAGE4_DIR.parent
PROJECT_DIR = REDUCTION_DIR.parent

INPUT_DIR = ONTOLOGY_DUPLICATES_DIR / "duplicate_relations" / "duplicate_relation_cleaned"
OUTPUT_FILE = ROOT / "queues" / "duplicate_entity_candidates.json"


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize(text):
    text = unicodedata.normalize(
        "NFKD",
        str(text or "").lower(),
    )

    text = "".join(
        c for c in text
        if not unicodedata.combining(c)
    )

    text = re.sub(
        r"[^a-z0-9/+.-]+",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def entity_id(e):
    return (
        e.get("identifiant_entite")
        or e.get("id")
        or e.get("entity_id")
    )


def entity_type(e):
    return (
        e.get("categorie")
        or e.get("type")
        or e.get("entity_type")
        or ""
    )


def entity_text(e):
    vals = []

    for key in (
        "preuve",
        "name",
        "valeur",
        "libelle",
        "parametre",
        "texte",
        "text",
    ):
        value = e.get(key)

        if value not in (None, ""):
            value = str(value).strip()

            if value and value not in vals:
                vals.append(value)

    return " | ".join(vals)


def entity_page(e):
    page = (
        e.get("page")
        or e.get("page_number")
        or e.get("numero_page")
    )

    if page is not None:
        return page

    eid = str(entity_id(e) or "")

    m = re.match(
        r"P(\d+)_E\d+",
        eid,
    )

    return int(m.group(1)) if m else None


def get_entities(doc):
    if isinstance(
        doc.get("global_entities"),
        list,
    ):
        return doc["global_entities"]

    out = []

    for page in doc.get("pages", []) or []:
        out.extend(
            page.get("entities", []) or []
        )

    return out


def get_relations(doc):
    if isinstance(
        doc.get("global_relations"),
        list,
    ):
        return doc["global_relations"]

    out = []

    for page in doc.get("pages", []) or []:
        out.extend(
            page.get("relations", []) or []
        )

    return out


def relation_source(r):
    return (
        r.get("identifiant_entite_sujet")
        or r.get("from_id")
        or r.get("subject_id")
        or r.get("source")
    )


def relation_target(r):
    return (
        r.get("identifiant_entite_objet")
        or r.get("to_id")
        or r.get("object_id")
        or r.get("target")
    )


def relation_type(r):
    return (
        r.get("type_relation")
        or r.get("relation")
        or r.get("relation_type")
        or r.get("predicate")
        or r.get("type")
        or ""
    )


def relation_signature_for_entity(
    relations,
    eid,
):
    incoming = []
    outgoing = []

    for r in relations:
        src = relation_source(r)
        tgt = relation_target(r)
        rt = relation_type(r)

        if str(src) == str(eid):
            outgoing.append(
                (
                    rt,
                    str(tgt),
                )
            )

        if str(tgt) == str(eid):
            incoming.append(
                (
                    rt,
                    str(src),
                )
            )

    return {
        "incoming":
            sorted(incoming),

        "outgoing":
            sorted(outgoing),
    }


def main():
    if not INPUT_DIR.exists():
        raise FileNotFoundError(
            f"Entrée clinique introuvable : {INPUT_DIR}"
        )

    candidates = []

    candidate_index = 1

    documents = 0

    for path in sorted(
        INPUT_DIR.glob("*.json")
    ):
        if path.name.endswith("_report.json"):
            continue

        try:
            doc = load_json(path)
        except Exception:
            continue

        if not isinstance(doc, dict):
            continue

        documents += 1

        entities = get_entities(doc)
        relations = get_relations(doc)

        groups = defaultdict(list)

        for e in entities:
            eid = entity_id(e)
            etype = entity_type(e)
            text = entity_text(e)
            norm_text = normalize(text)

            if (
                eid is None
                or not etype
                or not norm_text
            ):
                continue

            key = (
                etype,
                norm_text,
            )

            groups[key].append(e)

        for (
            etype,
            norm_text,
        ), values in groups.items():

            ids = {
                str(entity_id(e))
                for e in values
            }

            if len(ids) <= 1:
                continue

            candidate_entities = []

            for e in values:
                eid = str(entity_id(e))

                candidate_entities.append({
                    "entity_id":
                        eid,

                    "entity_type":
                        entity_type(e),

                    "entity_text":
                        entity_text(e),

                    "normalized_text":
                        norm_text,

                    "page":
                        entity_page(e),

                    "relations":
                        relation_signature_for_entity(
                            relations,
                            eid,
                        ),
                })

            candidates.append({
                "candidate_id":
                    f"DE_{candidate_index:06d}",

                "document":
                    path.name,

                "entity_type":
                    etype,

                "normalized_text":
                    norm_text,

                "entity_count":
                    len(candidate_entities),

                "entities":
                    candidate_entities,
            })

            candidate_index += 1

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_FILE.write_text(
        json.dumps(
            candidates,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=" * 104)
    print("TRACE / SGCE - DUPLICATE ENTITY CANDIDATE BUILDER")
    print("=" * 104)
    print(f"Documents analysés                   : {documents}")
    print(f"Groupes candidats doublons           : {len(candidates)}")
    print(f"Sortie                               : {OUTPUT_FILE}")
    print()
    print("Aucune donnée clinique n'a été modifiée.")


if __name__ == "__main__":
    main()
