# -*- coding: utf-8 -*-
"""
relation_repair_batch_safe_corrector.py
=======================================

Applique UNIQUEMENT le lot SAFE_ACCEPT produit par :
  relation_repair_batch_impact_validator.py

Source :
  MultiAgent/multiagent_safe_final_corrected

Sortie :
  MultiAgent/relation_repair/relation_repair_safe_corrected
"""

import json
import shutil
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
SGCE_DIR = HERE.parent
BASE_DIR = SGCE_DIR.parent
INPUT_FILE = HERE / "outputs" / "relation_repair_batch_safe_actions.json"
SOURCE_DIR = SGCE_DIR / "Patterns" / "PatternD" / "corrected"
OUTPUT_DIR = HERE / "corrected"
REPORT_FILE = OUTPUT_DIR / "relation_repair_safe_correction_report.json"


def load_json(path):
    with path.open("r",encoding="utf-8") as f:
        return json.load(f)


def save_json(path,data):
    path.write_text(
        json.dumps(data,ensure_ascii=False,indent=2),
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


def get_entities(doc):
    if isinstance(doc.get("global_entities"),list):
        return doc["global_entities"]
    out=[]
    for p in doc.get("pages",[]) or []:
        out.extend(p.get("entities",[]) or [])
    return out


def get_relations(doc):
    if isinstance(doc.get("global_relations"),list):
        return doc["global_relations"]
    out=[]
    for p in doc.get("pages",[]) or []:
        out.extend(p.get("relations",[]) or [])
    return out


def find_entity(doc,target_id):
    return next(
        (e for e in get_entities(doc) if str(entity_id(e))==str(target_id)),
        None
    )


def find_relation(doc,target_id):
    return next(
        (r for r in get_relations(doc) if str(relation_id(r))==str(target_id)),
        None
    )


def set_entity_type(e,new_type):
    if "categorie" in e:
        e["categorie"]=new_type
    elif "entity_type" in e:
        e["entity_type"]=new_type
    else:
        e["type"]=new_type


def set_relation_type(r,new_type):
    if "type_relation" in r:
        r["type_relation"]=new_type
    elif "relation_type" in r:
        r["relation_type"]=new_type
    elif "predicate" in r:
        r["predicate"]=new_type
    elif "relation" in r:
        r["relation"]=new_type
    else:
        r["type"]=new_type


def main():
    payload=load_json(INPUT_FILE)
    safe_actions=payload.get("safe_actions",[]) or []

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
    counts=Counter()
    errors=0

    for item in safe_actions:
        document=item.get("document")
        action=item.get("action")
        params=item.get("parameters") or {}

        path=OUTPUT_DIR/str(document)

        if not path.exists():
            errors+=1
            operations.append({
                "candidate_id":item.get("candidate_id"),
                "document":document,
                "action":action,
                "status":"ERROR",
                "reason":"DOCUMENT_NOT_FOUND",
            })
            continue

        try:
            doc=load_json(path)

            if action=="REPLACE_RELATION":
                relation=find_relation(doc,params.get("relation_id"))

                if relation is None:
                    status="SKIP"
                    reason="RELATION_NOT_FOUND"
                else:
                    set_relation_type(
                        relation,
                        params.get("new_relation_type"),
                    )
                    status="APPLIED"
                    reason="SAFE_ACCEPT"

            elif action in ("RETYPE_SOURCE","RETYPE_TARGET"):
                entity=find_entity(doc,params.get("entity_id"))

                if entity is None:
                    status="SKIP"
                    reason="ENTITY_NOT_FOUND"
                else:
                    set_entity_type(
                        entity,
                        params.get("new_type"),
                    )
                    status="APPLIED"
                    reason="SAFE_ACCEPT"

            else:
                status="SKIP"
                reason="UNSUPPORTED_ACTION"

            if status=="APPLIED":
                save_json(path,doc)
                modified.add(document)
                counts[action]+=1

            operations.append({
                "candidate_id":item.get("candidate_id"),
                "document":document,
                "action":action,
                "parameters":params,
                "status":status,
                "reason":reason,
            })

        except Exception as exc:
            errors+=1
            operations.append({
                "candidate_id":item.get("candidate_id"),
                "document":document,
                "action":action,
                "status":"ERROR",
                "reason":repr(exc),
            })

    report={
        "corrector":"relation_repair_batch_safe_corrector",
        "source_directory":str(SOURCE_DIR),
        "output_directory":str(OUTPUT_DIR),

        "summary":{
            "documents_copied":copied,
            "safe_actions_received":len(safe_actions),
            "operations_applied":sum(counts.values()),
            "documents_modified":len(modified),
            "errors":errors,
            "actions_applied":dict(counts),
        },

        "modified_documents":sorted(modified),
        "operations":operations,
    }

    save_json(REPORT_FILE,report)

    print("="*108)
    print("TRACE / SGCE - RELATION REPAIR BATCH SAFE CORRECTOR")
    print("="*108)
    print(f"Actions SAFE_ACCEPT reçues         : {len(safe_actions)}")
    print(f"Documents copiés                  : {copied}")
    print(f"Opérations appliquées             : {sum(counts.values())}")
    print(f"Documents modifiés                : {len(modified)}")
    print(f"Erreurs                           : {errors}")
    print()
    print("ACTIONS APPLIQUEES")
    print("-"*108)

    for name,count in counts.most_common():
        print(f"{str(name):<48}: {count}")

    print()
    print(f"Sortie clinique                   : {OUTPUT_DIR}")
    print(f"Rapport                           : {REPORT_FILE}")
    print()
    print("Les fichiers sources n'ont pas été modifiés.")


if __name__=="__main__":
    main()
