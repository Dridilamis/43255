# -*- coding: utf-8 -*-
"""
orphan_relation_decision_validator.py
=====================================

Valide les décisions de résolution des relations orphelines par simulation.

SAFE_ACCEPT si :
- l'anomalie orpheline est résolue
- aucune nouvelle anomalie structurelle n'est créée

Entrée clinique :
  SGCE/relation_repair/corrected

Sortie :
  MultiAgent/orphan_relation/outputs/orphan_relation_validated_decisions.json
"""

import copy
import json
from collections import Counter
from pathlib import Path

ORPHAN_DIR = Path(__file__).resolve().parent
SGCE_DIR = ORPHAN_DIR.parent
BASE_DIR = SGCE_DIR.parent

INPUT_FILE = (
    ORPHAN_DIR
    / "outputs"
    / "orphan_relation_decisions.json"
)

CLINICAL_DIR = SGCE_DIR / "relation_repair" / "corrected"

GUIDELINE_CANDIDATES = [
    BASE_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
    BASE_DIR.parent / "Guideline_TRACE_Sepsis_v1.6.json",
    Path.cwd() / "Guideline_TRACE_Sepsis_v1.6.json",
    ORPHAN_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
]

OUTPUT_FILE = (
    ORPHAN_DIR
    / "outputs"
    / "orphan_relation_validated_decisions.json"
)

def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_guideline():
    for p in GUIDELINE_CANDIDATES:
        if p.exists():
            return p

    raise FileNotFoundError(
        "Guideline introuvable."
    )


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
    if isinstance(
        doc.get("global_entities"),
        list,
    ):
        return doc["global_entities"]

    out=[]

    for p in doc.get("pages",[]) or []:
        out.extend(p.get("entities",[]) or [])

    return out


def get_relations(doc):
    if isinstance(
        doc.get("global_relations"),
        list,
    ):
        return doc["global_relations"]

    out=[]

    for p in doc.get("pages",[]) or []:
        out.extend(p.get("relations",[]) or [])

    return out


def relation_lists(doc):
    lists=[]

    if isinstance(
        doc.get("global_relations"),
        list,
    ):
        lists.append(
            doc["global_relations"]
        )

    for p in doc.get("pages",[]) or []:
        if isinstance(
            p.get("relations"),
            list,
        ):
            lists.append(
                p["relations"]
            )

    return lists


def find_relation(doc,target_id):
    return next(
        (
            r
            for r in get_relations(doc)
            if str(relation_id(r))==str(target_id)
        ),
        None,
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


def load_signatures():
    data=load_json(
        resolve_guideline()
    )

    root=data.get(
        "ontologie_sepsis_graph",
        data,
    )

    locked=root.get(
        "signatures_relations_verrouillees_v1_5",
        {},
    )

    result={}

    for name,spec in (
        locked.items()
        if isinstance(locked,dict)
        else []
    ):
        if (
            isinstance(spec,dict)
            and spec.get("domaine")
            and spec.get("image")
        ):
            result[name]={
                "domaine":spec["domaine"],
                "image":spec["image"],
            }

    return result


def audit(doc,sigs):
    entities={
        str(entity_id(e)):e
        for e in get_entities(doc)
        if entity_id(e) is not None
    }

    anomalies=set()

    for r in get_relations(doc):
        rid=str(relation_id(r))
        rt=relation_type(r)
        sid=relation_source(r)
        tid=relation_target(r)

        s=entities.get(str(sid))
        t=entities.get(str(tid))

        if s is None:
            anomalies.add(
                ("ORPHAN_SOURCE",rid,str(sid))
            )

        if t is None:
            anomalies.add(
                ("ORPHAN_TARGET",rid,str(tid))
            )

        sig=sigs.get(rt)

        if not sig:
            continue

        if (
            s is not None
            and entity_type(s)!=sig["domaine"]
        ):
            anomalies.add(
                (
                    "INVALID_SOURCE_TYPE",
                    rid,
                    entity_type(s),
                    sig["domaine"],
                )
            )

        if (
            t is not None
            and entity_type(t)!=sig["image"]
        ):
            anomalies.add(
                (
                    "INVALID_TARGET_TYPE",
                    rid,
                    entity_type(t),
                    sig["image"],
                )
            )

    return anomalies


def simulate(doc,item):
    sim=copy.deepcopy(doc)

    d=item.get(
        "agent_decision"
    ) or {}

    action=item.get(
        "action"
    ) or d.get(
        "action"
    )

    params=item.get(
        "parameters"
    ) or d.get(
        "parameters"
    ) or {}

    relation=find_relation(
        sim,
        params.get(
            "relation_id"
        ),
    )

    if relation is None:
        return None,"RELATION_NOT_FOUND"

    if action=="RELINK_EXISTING_ENTITY":
        role=params.get(
            "endpoint_role"
        )

        new_id=params.get(
            "new_entity_id"
        )

        if role=="SOURCE":
            set_relation_source(
                relation,
                new_id,
            )

        elif role=="TARGET":
            set_relation_target(
                relation,
                new_id,
            )

        else:
            return None,"INVALID_ENDPOINT_ROLE"

        return sim,"OK"

    if action=="REMOVE_INVALID_RELATION":
        rid=str(
            params.get(
                "relation_id"
            )
        )

        for rlist in relation_lists(sim):
            rlist[:]=[
                r
                for r in rlist
                if str(relation_id(r))!=rid
            ]

        return sim,"OK"

    return None,"UNSUPPORTED_ACTION"


def main():
    payload=load_json(
        INPUT_FILE
    )

    decisions=payload.get(
        "decisions",
        [],
    )

    sigs=load_signatures()

    docs={}

    for p in CLINICAL_DIR.glob("*.json"):
        if p.name.endswith("_report.json"):
            continue

        try:
            docs[p.name]=load_json(p)
        except:
            pass

    validated=[]

    for item in decisions:
        if item.get("decision")!="CORRECT":
            validated.append({
                "candidate_id":
                    item.get("candidate_id"),

                "document":
                    item.get("document"),

                "agent_decision":
                    item,

                "final_status":
                    "REVIEW",

                "final_action":
                    "NONE",

                "reason":
                    "Aucune correction proposée.",
            })

            continue

        doc=docs.get(
            item.get("document")
        )

        if doc is None:
            validated.append({
                "candidate_id":
                    item.get("candidate_id"),

                "document":
                    item.get("document"),

                "agent_decision":
                    item,

                "final_status":
                    "REVIEW",

                "final_action":
                    "NONE",

                "reason":
                    "Document introuvable.",
            })

            continue

        before=audit(
            doc,
            sigs,
        )

        wrapped={
            "action":
                item.get("action"),

            "parameters":
                item.get("parameters"),
        }

        sim_result=simulate(
            doc,
            wrapped,
        )

        if sim_result[0] is None:
            validated.append({
                "candidate_id":
                    item.get("candidate_id"),

                "document":
                    item.get("document"),

                "agent_decision":
                    item,

                "final_status":
                    "REVIEW",

                "final_action":
                    "NONE",

                "reason":
                    sim_result[1],
            })

            continue

        simulated=sim_result[0]

        after=audit(
            simulated,
            sigs,
        )

        new=after-before
        resolved=before-after

        if new:
            status="REJECT_HARMFUL"
            action="NONE"
            reason="La correction crée de nouvelles anomalies."

        elif resolved:
            status="ACCEPT"
            action=item.get("action")
            reason="La correction résout une anomalie sans en créer."

        else:
            status="NO_BENEFIT"
            action="NONE"
            reason="Aucune amélioration structurelle."

        validated.append({
            "candidate_id":
                item.get("candidate_id"),

            "document":
                item.get("document"),

            "agent_decision":
                item,

            "final_status":
                status,

            "final_action":
                action,

            "reason":
                reason,

            "new_anomaly_count":
                len(new),

            "resolved_anomaly_count":
                len(resolved),
        })

    sc=Counter(
        x.get("final_status")
        for x in validated
    )

    ac=Counter(
        x.get("final_action")
        for x in validated
    )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_FILE.write_text(
        json.dumps(
            {
                "validator":
                    "orphan_relation_decision_validator",

                "validated_decisions":
                    validated,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("="*104)
    print("TRACE / SGCE - ORPHAN RELATION DECISION VALIDATOR")
    print("="*104)
    print(f"Décisions reçues                      : {len(decisions)}")
    print()
    print("STATUTS FINAUX")
    print("-"*104)

    for k,v in sc.most_common():
        print(f"{str(k):<48}: {v}")

    print()
    print("ACTIONS FINALES")
    print("-"*104)

    for k,v in ac.most_common():
        print(f"{str(k):<48}: {v}")

    print()
    print(f"Sortie                                : {OUTPUT_FILE}")
    print()
    print("Aucune donnée clinique n'a été modifiée.")


if __name__=="__main__":
    main()
