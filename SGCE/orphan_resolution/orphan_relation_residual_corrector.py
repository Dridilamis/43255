# -*- coding: utf-8 -*-
"""
TRACE / SGCE - Orphan Relation Residual Router

After the safe corrector, unresolved orphan relations are NOT deleted.
They are preserved in the clinical corpus and exported to a residual queue
for the downstream Multi-Agent stage.
"""
import copy
import json
import shutil
from pathlib import Path
from collections import Counter

ORPHAN_DIR = Path(__file__).resolve().parent
INPUT_DIR = ORPHAN_DIR / "safe_corrected"
OUTPUT_DIR = ORPHAN_DIR / "corrected"
QUEUE_FILE = ORPHAN_DIR / "outputs" / "orphan_relation_unresolved_queue.json"
REPORT_FILE = OUTPUT_DIR / "orphan_relation_residual_routing_report.json"

def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def entity_id(e):
    return e.get("identifiant_entite") or e.get("id") or e.get("entity_id")

def entity_type(e):
    return e.get("categorie") or e.get("type") or e.get("entity_type") or ""

def entity_text(e):
    vals=[]
    for k in ("preuve","name","valeur","libelle","parametre","texte","text"):
        v=e.get(k)
        if v not in (None,""):
            s=str(v).strip()
            if s and s not in vals: vals.append(s)
    return " | ".join(vals)

def relation_id(r):
    return r.get("identifiant_relation") or r.get("id") or r.get("relation_id")

def relation_type(r):
    return r.get("type_relation") or r.get("relation") or r.get("relation_type") or r.get("predicate") or r.get("type") or ""

def relation_source(r):
    return r.get("identifiant_entite_sujet") or r.get("from_id") or r.get("subject_id") or r.get("source")

def relation_target(r):
    return r.get("identifiant_entite_objet") or r.get("to_id") or r.get("object_id") or r.get("target")

def get_entities(doc):
    if isinstance(doc.get("global_entities"), list):
        return doc["global_entities"]
    out=[]
    for page in doc.get("pages",[]) or []:
        out.extend(page.get("entities",[]) or [])
    return out

def get_relations(doc):
    if isinstance(doc.get("global_relations"), list):
        return doc["global_relations"]
    out=[]
    for page in doc.get("pages",[]) or []:
        out.extend(page.get("relations",[]) or [])
    return out

def main():
    if not INPUT_DIR.exists():
        raise FileNotFoundError(f"Entrée introuvable : {INPUT_DIR}")

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    residual=[]
    docs=0
    docs_with_residual=set()
    errors=[]

    for path in sorted(INPUT_DIR.glob("*.json")):
        if path.name.endswith("_report.json"):
            continue
        try:
            doc=load_json(path)
        except Exception as exc:
            errors.append({"document":path.name,"error":str(exc)})
            continue

        # Preserve the safe-corrected corpus exactly.
        shutil.copy2(path, OUTPUT_DIR/path.name)
        docs += 1

        entities=get_entities(doc)
        emap={str(entity_id(e)):e for e in entities if entity_id(e) is not None}
        catalog=[{
            "entity_id":str(entity_id(e)),
            "entity_type":entity_type(e),
            "entity_text":entity_text(e),
        } for e in entities if entity_id(e) is not None]

        for r in get_relations(doc):
            sid,tid=relation_source(r),relation_target(r)
            sm=str(sid) not in emap
            tm=str(tid) not in emap
            if not (sm or tm):
                continue
            docs_with_residual.add(path.name)
            residual.append({
                "candidate_id":f"OR_RES_{len(residual)+1:06d}",
                "document":path.name,
                "relation_id":relation_id(r),
                "relation_type":relation_type(r),
                "source_id":sid,
                "target_id":tid,
                "source_missing":sm,
                "target_missing":tm,
                "existing_source_entity": None if sm else {
                    "entity_id":str(entity_id(emap[str(sid)])),
                    "entity_type":entity_type(emap[str(sid)]),
                    "entity_text":entity_text(emap[str(sid)]),
                },
                "existing_target_entity": None if tm else {
                    "entity_id":str(entity_id(emap[str(tid)])),
                    "entity_type":entity_type(emap[str(tid)]),
                    "entity_text":entity_text(emap[str(tid)]),
                },
                "entity_catalog":catalog,
                "routing_status":"REVIEW",
                "recommended_next_stage":"MULTI_AGENT",
                "protected":True,
            })

    queue={
        "stage":"ORPHAN_RELATION_RESIDUAL_ROUTING",
        "policy":"PRESERVE_AND_ROUTE_TO_MULTI_AGENT",
        "source_directory":str(INPUT_DIR),
        "summary":{
            "documents_processed":docs,
            "documents_with_unresolved_orphans":len(docs_with_residual),
            "unresolved_orphan_relations":len(residual),
            "relations_removed":0,
            "errors":len(errors),
        },
        "candidates":residual,
        "errors":errors,
    }
    save_json(QUEUE_FILE,queue)

    report={
        "stage":"ORPHAN_RELATION_RESIDUAL_ROUTING",
        "status":"PASS" if not errors else "REVIEW",
        "input_directory":str(INPUT_DIR),
        "output_directory":str(OUTPUT_DIR),
        "unresolved_queue":str(QUEUE_FILE),
        "summary":queue["summary"],
        "policy":{
            "delete_unresolved_orphans":False,
            "preserve_clinical_corpus":True,
            "route_unresolved_to_multi_agent":True,
        },
        "errors":errors,
    }
    save_json(REPORT_FILE,report)

    print("="*112)
    print("TRACE / SGCE - ORPHAN RELATION RESIDUAL ROUTER")
    print("="*112)
    print(f"Documents traités                   : {docs}")
    print(f"Relations orphelines résiduelles    : {len(residual)}")
    print(f"Documents concernés                 : {len(docs_with_residual)}")
    print("Relations résiduelles supprimées    : 0")
    print(f"Erreurs                             : {len(errors)}")
    print()
    print("POLITIQUE")
    print("-"*112)
    print("PRESERVE_AND_ROUTE_TO_MULTI_AGENT")
    print()
    print(f"Sortie clinique                     : {OUTPUT_DIR}")
    print(f"Queue Multi-Agent                   : {QUEUE_FILE}")
    print(f"Rapport                             : {REPORT_FILE}")
    print()
    print("Les relations REVIEW sont conservées; aucune suppression résiduelle automatique n'est effectuée.")

if __name__=="__main__":
    main()
