# -*- coding: utf-8 -*-
"""
duplicate_relation_safe_cleaner.py
==================================

Supprime uniquement les relations exactement dupliquées.

Règle :
- garder une seule relation par triplet
  (relation_type, source_id, target_id)
- garder de préférence le plus petit ID lexicalement
- supprimer les autres copies

Source :
  MultiAgent/duplicate_entity/duplicate_entity_safe_merged

Sortie :
  MultiAgent/duplicate_relation/duplicate_relation_cleaned
"""

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STAGE4_DIR = ROOT.parent

INPUT_FILE = (
    ROOT
    / "queues"
    / "duplicate_relation_candidates.json"
)

SOURCE_DIR = (
    STAGE4_DIR
    / "relation_validation"
    / "relation_validation_safe_corrected"
)

OUTPUT_DIR = (
    ROOT
    / "duplicate_relation_cleaned"
)

REPORT_FILE = (
    OUTPUT_DIR
    / "duplicate_relation_cleaning_report.json"
)


def load_json(path):
    with path.open("r",encoding="utf-8") as f:
        return json.load(f)


def save_json(path,data):
    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def relation_id(r):
    return (
        r.get("identifiant_relation")
        or r.get("id")
        or r.get("relation_id")
    )


def relation_lists(doc):
    lists=[]

    if isinstance(doc.get("global_relations"),list):
        lists.append(doc["global_relations"])

    for p in doc.get("pages",[]) or []:
        if isinstance(p.get("relations"),list):
            lists.append(p["relations"])

    return lists


def main():
    candidates=load_json(INPUT_FILE)

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)

    OUTPUT_DIR.mkdir(parents=True,exist_ok=True)

    copied=0

    for src in SOURCE_DIR.glob("*.json"):
        if src.name.endswith("_report.json"):
            continue

        try:
            doc=load_json(src)

            if not (
                isinstance(doc,dict)
                and any(
                    k in doc
                    for k in (
                        "pages",
                        "global_entities",
                        "global_relations",
                    )
                )
            ):
                continue

        except:
            continue

        shutil.copy2(src,OUTPUT_DIR/src.name)
        copied+=1

    operations=[]
    modified=set()
    removed_total=0
    errors=0

    for item in candidates:
        document=item.get("document")
        relation_ids=[
            str(x)
            for x in item.get("relation_ids",[])
        ]

        if len(relation_ids)<=1:
            continue

        keep_id=sorted(relation_ids)[0]
        remove_ids=set(relation_ids)-{keep_id}

        path=OUTPUT_DIR/str(document)

        if not path.exists():
            errors+=1
            operations.append({
                "candidate_id":item.get("candidate_id"),
                "document":document,
                "status":"ERROR",
                "reason":"DOCUMENT_NOT_FOUND",
            })
            continue

        try:
            doc=load_json(path)

            removed=0

            for rlist in relation_lists(doc):
                before=len(rlist)

                rlist[:]=[
                    r
                    for r in rlist
                    if str(relation_id(r)) not in remove_ids
                ]

                removed+=(
                    before-len(rlist)
                )

            if removed>0:
                save_json(path,doc)
                modified.add(document)
                removed_total+=removed

                status="APPLIED"
                reason="DUPLICATES_REMOVED"

            else:
                status="SKIP"
                reason="NO_DUPLICATE_FOUND"

            operations.append({
                "candidate_id":item.get("candidate_id"),
                "document":document,
                "keep_relation_id":keep_id,
                "removed_relation_ids":sorted(remove_ids),
                "removed_count":removed,
                "status":status,
                "reason":reason,
            })

        except Exception as exc:
            errors+=1

            operations.append({
                "candidate_id":item.get("candidate_id"),
                "document":document,
                "status":"ERROR",
                "reason":repr(exc),
            })

    report={
        "cleaner":"duplicate_relation_safe_cleaner",
        "source_directory":str(SOURCE_DIR),
        "output_directory":str(OUTPUT_DIR),

        "summary":{
            "documents_copied":copied,
            "candidate_groups":len(candidates),
            "relations_removed":removed_total,
            "documents_modified":len(modified),
            "errors":errors,
        },

        "modified_documents":sorted(modified),
        "operations":operations,
    }

    save_json(REPORT_FILE,report)

    print("="*104)
    print("TRACE / SGCE - DUPLICATE RELATION SAFE CLEANER")
    print("="*104)
    print(f"Groupes candidats                    : {len(candidates)}")
    print(f"Documents copiés                     : {copied}")
    print(f"Relations dupliquées supprimées      : {removed_total}")
    print(f"Documents modifiés                   : {len(modified)}")
    print(f"Erreurs                              : {errors}")
    print()
    print(f"Sortie clinique                      : {OUTPUT_DIR}")
    print(f"Rapport                              : {REPORT_FILE}")
    print()
    print("Les fichiers sources n'ont pas été modifiés.")


if __name__=="__main__":
    main()
