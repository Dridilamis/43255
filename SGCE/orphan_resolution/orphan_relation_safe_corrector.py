# -*- coding: utf-8 -*-
"""
orphan_relation_safe_corrector.py
=================================

Applique uniquement les décisions ACCEPT.

Source :
  SGCE/relation_repair/corrected

Sortie :
  SGCE/orphan_resolution/safe_corrected
"""

import json
import shutil
from collections import Counter
from pathlib import Path

ORPHAN_DIR = Path(__file__).resolve().parent
SGCE_DIR = ORPHAN_DIR.parent
BASE_DIR = SGCE_DIR.parent

INPUT_FILE = (
    ORPHAN_DIR
    / "outputs"
    / "orphan_relation_validated_decisions.json"
)

SOURCE_DIR = SGCE_DIR / "relation_repair" / "corrected"

OUTPUT_DIR = ORPHAN_DIR / "safe_corrected"

REPORT_FILE = (
    OUTPUT_DIR
    / "orphan_relation_correction_report.json"
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
    return r.get("identifiant_relation") or r.get("id") or r.get("relation_id")


def relation_lists(doc):
    lists=[]

    if isinstance(doc.get("global_relations"),list):
        lists.append(doc["global_relations"])

    for p in doc.get("pages",[]) or []:
        if isinstance(p.get("relations"),list):
            lists.append(p["relations"])

    return lists


def find_relation(doc,target_id):
    for rlist in relation_lists(doc):
        for r in rlist:
            if str(relation_id(r))==str(target_id):
                return r

    return None


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


def main():
    payload=load_json(
        INPUT_FILE
    )

    accepted=[
        x
        for x in payload.get("validated_decisions",[])
        if x.get("final_status")=="ACCEPT"
    ]

    if OUTPUT_DIR.exists():
        shutil.rmtree(
            OUTPUT_DIR
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

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

        shutil.copy2(
            src,
            OUTPUT_DIR/src.name,
        )

        copied+=1

    modified=set()
    operations=[]
    counts=Counter()
    errors=0

    for item in accepted:
        document=item.get("document")
        decision=item.get("agent_decision") or {}
        action=item.get("final_action")
        params=decision.get("parameters") or {}

        path=OUTPUT_DIR/str(document)

        if not path.exists():
            errors+=1
            continue

        try:
            doc=load_json(path)

            if action=="RELINK_EXISTING_ENTITY":
                relation=find_relation(
                    doc,
                    params.get("relation_id"),
                )

                if relation is None:
                    status="SKIP"
                    reason="RELATION_NOT_FOUND"

                else:
                    role=params.get("endpoint_role")

                    if role=="SOURCE":
                        set_relation_source(
                            relation,
                            params.get("new_entity_id"),
                        )

                    elif role=="TARGET":
                        set_relation_target(
                            relation,
                            params.get("new_entity_id"),
                        )

                    else:
                        status="SKIP"
                        reason="INVALID_ENDPOINT_ROLE"
                        operations.append({
                            "candidate_id":item.get("candidate_id"),
                            "document":document,
                            "action":action,
                            "status":status,
                            "reason":reason,
                        })
                        continue

                    status="APPLIED"
                    reason="OK"

            elif action=="REMOVE_INVALID_RELATION":
                rid=str(
                    params.get("relation_id")
                )

                removed=0

                for rlist in relation_lists(doc):
                    before=len(rlist)

                    rlist[:]=[
                        r
                        for r in rlist
                        if str(relation_id(r))!=rid
                    ]

                    removed+=(
                        before-len(rlist)
                    )

                if removed>0:
                    status="APPLIED"
                    reason="OK"

                else:
                    status="SKIP"
                    reason="RELATION_NOT_FOUND"

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
        "corrector":"orphan_relation_safe_corrector",
        "source_directory":str(SOURCE_DIR),
        "output_directory":str(OUTPUT_DIR),

        "summary":{
            "documents_copied":copied,
            "accepted_actions":len(accepted),
            "operations_applied":sum(counts.values()),
            "documents_modified":len(modified),
            "errors":errors,
            "actions_applied":dict(counts),
        },

        "modified_documents":sorted(modified),
        "operations":operations,
    }

    save_json(
        REPORT_FILE,
        report,
    )

    print("="*104)
    print("TRACE / SGCE - ORPHAN RELATION SAFE CORRECTOR")
    print("="*104)
    print(f"Actions ACCEPT reçues                 : {len(accepted)}")
    print(f"Documents copiés                      : {copied}")
    print(f"Opérations appliquées                 : {sum(counts.values())}")
    print(f"Documents modifiés                    : {len(modified)}")
    print(f"Erreurs                               : {errors}")
    print()
    print("ACTIONS APPLIQUEES")
    print("-"*104)

    for k,v in counts.most_common():
        print(f"{str(k):<48}: {v}")

    print()
    print(f"Sortie clinique                       : {OUTPUT_DIR}")
    print(f"Rapport                               : {REPORT_FILE}")
    print()
    print("Les fichiers sources n'ont pas été modifiés.")


if __name__=="__main__":
    main()
