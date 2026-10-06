# -*- coding: utf-8 -*-
"""
duplicate_entity_safe_merger.py
===============================

Applique uniquement les SAFE_MERGE.

Source :
  MultiAgent/relation_repair/relation_repair_safe_corrected

Sortie :
  MultiAgent/duplicate_entity/duplicate_entity_safe_merged
"""

import json
import shutil
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ONTOLOGY_DUPLICATES_DIR = ROOT.parent
STAGE4_DIR = ONTOLOGY_DUPLICATES_DIR.parent
REDUCTION_DIR = STAGE4_DIR.parent
PROJECT_DIR = REDUCTION_DIR.parent

INPUT_FILE = ROOT / "outputs" / "duplicate_entity_validated.json"
SOURCE_DIR = ONTOLOGY_DUPLICATES_DIR / "duplicate_relations" / "duplicate_relation_cleaned"
OUTPUT_DIR = ROOT / "duplicate_entity_safe_merged"
REPORT_FILE = OUTPUT_DIR / "duplicate_entity_merge_report.json"


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


def entity_id(e):
    return e.get("identifiant_entite") or e.get("id") or e.get("entity_id")


def relation_id(r):
    return r.get("identifiant_relation") or r.get("id") or r.get("relation_id")


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


def set_relation_source(r,new_id):
    for key in (
        "identifiant_entite_sujet",
        "from_id",
        "subject_id",
        "source",
    ):
        if key in r:
            r[key]=new_id
            return

    r["source"]=new_id


def set_relation_target(r,new_id):
    for key in (
        "identifiant_entite_objet",
        "to_id",
        "object_id",
        "target",
    ):
        if key in r:
            r[key]=new_id
            return

    r["target"]=new_id


def entity_lists(doc):
    lists=[]

    if isinstance(doc.get("global_entities"),list):
        lists.append(doc["global_entities"])

    for p in doc.get("pages",[]) or []:
        if isinstance(p.get("entities"),list):
            lists.append(p["entities"])

    return lists


def relation_lists(doc):
    lists=[]

    if isinstance(doc.get("global_relations"),list):
        lists.append(doc["global_relations"])

    for p in doc.get("pages",[]) or []:
        if isinstance(p.get("relations"),list):
            lists.append(p["relations"])

    return lists


def merge_group(
    doc,
    keep_id,
    remove_ids,
):
    rewired=0
    removed=0
    duplicate_relations_removed=0

    remove_ids=set(
        str(x)
        for x in remove_ids
    )

    for rlist in relation_lists(doc):
        for r in rlist:
            if str(relation_source(r)) in remove_ids:
                set_relation_source(
                    r,
                    keep_id,
                )
                rewired+=1

            if str(relation_target(r)) in remove_ids:
                set_relation_target(
                    r,
                    keep_id,
                )
                rewired+=1

    for elist in entity_lists(doc):
        before=len(elist)

        elist[:]=[
            e
            for e in elist
            if str(entity_id(e)) not in remove_ids
        ]

        removed+=(
            before-len(elist)
        )

    # Deduplicate exact relations inside each relation list.
    global_seen=set()

    for rlist in relation_lists(doc):
        new=[]

        for r in rlist:
            key=(
                relation_type(r),
                str(relation_source(r)),
                str(relation_target(r)),
            )

            if key in global_seen:
                duplicate_relations_removed+=1
                continue

            global_seen.add(key)
            new.append(r)

        rlist[:]=new

    return {
        "rewired_endpoints":rewired,
        "entities_removed":removed,
        "duplicate_relations_removed":
            duplicate_relations_removed,
    }


def main():
    payload=load_json(
        INPUT_FILE
    )

    safe=[
        x
        for x in payload.get("validated",[])
        if x.get("final_status")=="SAFE_MERGE"
    ]

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    copied=0

    for src in SOURCE_DIR.glob("*.json"):
        if src.name.endswith("_report.json"):
            continue

        try:
            data=load_json(src)

            if not (
                isinstance(data,dict)
                and any(
                    k in data
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

        shutil.copy2(
            src,
            OUTPUT_DIR/src.name,
        )

        copied+=1

    operations=[]
    modified=set()
    counts=Counter()
    errors=0

    for item in safe:
        document=item.get("document")
        path=OUTPUT_DIR/str(document)

        if not path.exists():
            errors+=1
            continue

        try:
            doc=load_json(path)

            result=merge_group(
                doc,
                item.get("keep_entity_id"),
                item.get("remove_entity_ids",[]),
            )

            save_json(path,doc)

            modified.add(document)
            counts["SAFE_MERGE"]+=1

            operations.append({
                "candidate_id":item.get("candidate_id"),
                "document":document,
                "keep_entity_id":item.get("keep_entity_id"),
                "remove_entity_ids":item.get("remove_entity_ids",[]),
                "status":"APPLIED",
                **result,
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
        "corrector":"duplicate_entity_safe_merger",
        "source_directory":str(SOURCE_DIR),
        "output_directory":str(OUTPUT_DIR),

        "summary":{
            "documents_copied":copied,
            "safe_merge_received":len(safe),
            "operations_applied":counts.get("SAFE_MERGE",0),
            "documents_modified":len(modified),
            "errors":errors,
        },

        "modified_documents":sorted(modified),
        "operations":operations,
    }

    save_json(
        REPORT_FILE,
        report,
    )

    print("="*104)
    print("TRACE / SGCE - DUPLICATE ENTITY SAFE MERGER")
    print("="*104)
    print(f"SAFE_MERGE reçus                     : {len(safe)}")
    print(f"Documents copiés                     : {copied}")
    print(f"Fusions appliquées                   : {counts.get('SAFE_MERGE',0)}")
    print(f"Documents modifiés                   : {len(modified)}")
    print(f"Erreurs                              : {errors}")
    print()
    print(f"Sortie clinique                      : {OUTPUT_DIR}")
    print(f"Rapport                              : {REPORT_FILE}")
    print()
    print("Les fichiers sources n'ont pas été modifiés.")


if __name__=="__main__":
    main()
