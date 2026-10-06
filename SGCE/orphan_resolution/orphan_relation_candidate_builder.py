# -*- coding: utf-8 -*-
"""
orphan_relation_candidate_builder.py
====================================

Détecte les relations orphelines.

Entrée :
  SGCE/relation_repair/corrected

Sortie :
  MultiAgent/orphan_relation/queues/orphan_relation_candidates.json

Aucune donnée clinique n'est modifiée.
"""

import json
from pathlib import Path

ORPHAN_DIR = Path(__file__).resolve().parent
SGCE_DIR = ORPHAN_DIR.parent
BASE_DIR = SGCE_DIR.parent

INPUT_DIR = SGCE_DIR / "relation_repair" / "corrected"

OUTPUT_FILE = (
    ORPHAN_DIR
    / "queues"
    / "orphan_relation_candidates.json"
)

def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


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


def relation_id(r):
    return (
        r.get("identifiant_relation")
        or r.get("id")
        or r.get("relation_id")
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


def get_entities(doc):
    if isinstance(doc.get("global_entities"), list):
        return doc["global_entities"]

    out = []

    for page in doc.get("pages", []) or []:
        out.extend(page.get("entities", []) or [])

    return out


def get_relations(doc):
    if isinstance(doc.get("global_relations"), list):
        return doc["global_relations"]

    out = []

    for page in doc.get("pages", []) or []:
        out.extend(page.get("relations", []) or [])

    return out


def main():
    if not INPUT_DIR.exists():
        raise FileNotFoundError(
            f"Entrée clinique introuvable : {INPUT_DIR}"
        )

    candidates = []
    idx = 1
    docs = 0

    for path in sorted(INPUT_DIR.glob("*.json")):
        if path.name.endswith("_report.json"):
            continue

        try:
            doc = load_json(path)
        except Exception:
            continue

        docs += 1

        entities = get_entities(doc)

        entity_map = {
            str(entity_id(e)): e
            for e in entities
            if entity_id(e) is not None
        }

        entity_catalog = [
            {
                "entity_id": str(entity_id(e)),
                "entity_type": entity_type(e),
                "entity_text": entity_text(e),
            }
            for e in entities
            if entity_id(e) is not None
        ]

        for r in get_relations(doc):
            rid = relation_id(r)
            rtype = relation_type(r)

            sid = relation_source(r)
            tid = relation_target(r)

            source_missing = str(sid) not in entity_map
            target_missing = str(tid) not in entity_map

            if not source_missing and not target_missing:
                continue

            candidates.append({
                "candidate_id":
                    f"OR_{idx:06d}",

                "document":
                    path.name,

                "relation_id":
                    rid,

                "relation_type":
                    rtype,

                "source_id":
                    sid,

                "target_id":
                    tid,

                "source_missing":
                    source_missing,

                "target_missing":
                    target_missing,

                "existing_source":
                    (
                        {
                            "entity_id":
                                str(
                                    entity_id(
                                        entity_map[
                                            str(sid)
                                        ]
                                    )
                                ),

                            "entity_type":
                                entity_type(
                                    entity_map[
                                        str(sid)
                                    ]
                                ),

                            "entity_text":
                                entity_text(
                                    entity_map[
                                        str(sid)
                                    ]
                                ),
                        }
                        if not source_missing
                        else None
                    ),

                "existing_target":
                    (
                        {
                            "entity_id":
                                str(
                                    entity_id(
                                        entity_map[
                                            str(tid)
                                        ]
                                    )
                                ),

                            "entity_type":
                                entity_type(
                                    entity_map[
                                        str(tid)
                                    ]
                                ),

                            "entity_text":
                                entity_text(
                                    entity_map[
                                        str(tid)
                                    ]
                                ),
                        }
                        if not target_missing
                        else None
                    ),

                "entity_catalog":
                    entity_catalog,
            })

            idx += 1

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
    print("TRACE / SGCE - ORPHAN RELATION CANDIDATE BUILDER")
    print("=" * 104)
    print(f"Documents analysés                   : {docs}")
    print(f"Relations orphelines candidates      : {len(candidates)}")
    print(f"Sortie                               : {OUTPUT_FILE}")
    print()
    print("Aucune donnée clinique n'a été modifiée.")


if __name__ == "__main__":
    main()
