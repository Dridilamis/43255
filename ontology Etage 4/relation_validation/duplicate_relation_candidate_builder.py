# -*- coding: utf-8 -*-
"""
duplicate_relation_candidate_builder.py
=======================================

Détecte les relations exactement dupliquées.

Entrée :
  MultiAgent/duplicate_entity/duplicate_entity_safe_merged

Critère :
  même document
  même type de relation
  même source
  même cible
  IDs de relation différents

Sortie :
  MultiAgent/duplicate_relation/queues/duplicate_relation_candidates.json

Aucune donnée clinique n'est modifiée.
"""

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STAGE4_DIR = ROOT.parent

INPUT_DIR = (
    STAGE4_DIR
    / "relation_validation"
    / "relation_validation_safe_corrected"
)

OUTPUT_FILE = (
    ROOT
    / "queues"
    / "duplicate_relation_candidates.json"
)


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


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


def get_relations(doc):
    if isinstance(doc.get("global_relations"), list):
        return doc["global_relations"]

    out=[]

    for p in doc.get("pages",[]) or []:
        out.extend(p.get("relations",[]) or [])

    return out


def main():
    if not INPUT_DIR.exists():
        raise FileNotFoundError(
            f"Entrée introuvable : {INPUT_DIR}"
        )

    candidates=[]
    idx=1
    docs=0

    for path in sorted(INPUT_DIR.glob("*.json")):
        if path.name.endswith("_report.json"):
            continue

        try:
            doc=load_json(path)
        except:
            continue

        docs+=1

        groups=defaultdict(list)

        for r in get_relations(doc):
            key=(
                relation_type(r),
                str(relation_source(r)),
                str(relation_target(r)),
            )

            groups[key].append(r)

        for (
            rtype,
            source_id,
            target_id,
        ), values in groups.items():

            if len(values)<=1:
                continue

            relation_ids=[
                str(relation_id(r))
                for r in values
            ]

            candidates.append({
                "candidate_id":
                    f"DR_{idx:06d}",

                "document":
                    path.name,

                "relation_type":
                    rtype,

                "source_id":
                    source_id,

                "target_id":
                    target_id,

                "relation_ids":
                    relation_ids,

                "relation_count":
                    len(relation_ids),
            })

            idx+=1

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

    print("="*104)
    print("TRACE / SGCE - DUPLICATE RELATION CANDIDATE BUILDER")
    print("="*104)
    print(f"Documents analysés                   : {docs}")
    print(f"Groupes relations dupliquées         : {len(candidates)}")
    print(f"Sortie                               : {OUTPUT_FILE}")
    print()
    print("Aucune donnée clinique n'a été modifiée.")


if __name__=="__main__":
    main()
