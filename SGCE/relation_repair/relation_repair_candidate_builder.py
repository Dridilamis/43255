# -*- coding: utf-8 -*-
"""Construit les candidats Relation Repair depuis PatternD/corrected."""
import json
from pathlib import Path
from collections import Counter

HERE = Path(__file__).resolve().parent
SGCE_DIR = HERE.parent
BASE_DIR = SGCE_DIR.parent
INPUT_DIR = SGCE_DIR / "Patterns" / "PatternD" / "corrected"
QUEUE_FILE = HERE / "queues" / "relation_repair_queue.json"
GUIDELINE_CANDIDATES = [
    BASE_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
    BASE_DIR.parent / "Guideline_TRACE_Sepsis_v1.6.json",
    Path.cwd() / "Guideline_TRACE_Sepsis_v1.6.json",
    HERE / "Guideline_TRACE_Sepsis_v1.6.json",
]

def load_json(p):
    with p.open("r", encoding="utf-8") as f: return json.load(f)
def guideline():
    for p in GUIDELINE_CANDIDATES:
        if p.exists(): return load_json(p)
    raise FileNotFoundError("Guideline_TRACE_Sepsis_v1.6.json introuvable.")
def eid(e): return e.get("identifiant_entite") or e.get("id") or e.get("entity_id")
def etype(e): return e.get("categorie") or e.get("type") or e.get("entity_type") or ""
def etext(e):
    vals=[]
    for k in ("preuve","name","valeur","libelle","parametre","texte","text"):
        v=e.get(k)
        if v not in (None,""):
            s=str(v).strip()
            if s and s not in vals: vals.append(s)
    return " | ".join(vals)
def rid(r): return r.get("identifiant_relation") or r.get("id") or r.get("relation_id")
def rtype(r): return r.get("type_relation") or r.get("relation") or r.get("relation_type") or r.get("predicate") or r.get("type") or ""
def rsrc(r): return r.get("identifiant_entite_sujet") or r.get("from_id") or r.get("subject_id") or r.get("source")
def rtgt(r): return r.get("identifiant_entite_objet") or r.get("to_id") or r.get("object_id") or r.get("target")
def ents(d):
    if isinstance(d.get("global_entities"),list): return d["global_entities"]
    return [e for p in d.get("pages",[]) or [] for e in (p.get("entities",[]) or [])]
def rels(d):
    if isinstance(d.get("global_relations"),list): return d["global_relations"]
    return [r for p in d.get("pages",[]) or [] for r in (p.get("relations",[]) or [])]
def signatures():
    data=guideline(); root=data.get("ontologie_sepsis_graph",data)
    locked=root.get("signatures_relations_verrouillees_v1_5",{})
    return {n:{"domaine":s["domaine"],"image":s["image"]} for n,s in locked.items()
            if isinstance(s,dict) and s.get("domaine") and s.get("image")}

def main():
    if not INPUT_DIR.exists(): raise FileNotFoundError(f"Entrée introuvable : {INPUT_DIR}")
    sigs=signatures(); rows=[]; orphans=0; unauthorized=0; ndocs=0
    for p in sorted(INPUT_DIR.glob("*.json")):
        if p.name.endswith("_report.json"): continue
        try: d=load_json(p)
        except Exception: continue
        if not isinstance(d,dict): continue
        es=ents(d); rs=rels(d)
        if not es and not rs: continue
        ndocs+=1
        em={str(eid(e)):e for e in es if eid(e) is not None}
        for r in rs:
            s=em.get(str(rsrc(r))); t=em.get(str(rtgt(r)))
            if s is None or t is None:
                orphans+=1; continue
            sig=sigs.get(rtype(r))
            if sig is None:
                unauthorized+=1; continue
            so,to=etype(s),etype(t); se,te=sig["domaine"],sig["image"]
            sb,tb=so!=se,to!=te
            if not sb and not tb: continue
            mk="BOTH_MISMATCH" if sb and tb else ("SOURCE_MISMATCH" if sb else "TARGET_MISMATCH")
            rows.append({
                "candidate_id":f"RR_{len(rows)+1:06d}","document":p.name,
                "relation_id":rid(r),"relation_type":rtype(r),"mismatch_kind":mk,
                "source_id":rsrc(r),"source_text":etext(s),
                "source_type_observed":so,"source_type_expected":se,
                "target_id":rtgt(r),"target_text":etext(t),
                "target_type_observed":to,"target_type_expected":te,
            })
    QUEUE_FILE.parent.mkdir(parents=True,exist_ok=True)
    QUEUE_FILE.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
    c=Counter(x["mismatch_kind"] for x in rows)
    print("="*104); print("TRACE / SGCE - RELATION REPAIR CANDIDATE BUILDER"); print("="*104)
    print(f"Documents analysés                 : {ndocs}")
    print(f"Candidats                          : {len(rows)}")
    print(f"Orphelines réservées étape suivante: {orphans}")
    print(f"Relations non autorisées réservées : {unauthorized}")
    for k,v in c.items(): print(f"{k:<40}: {v}")
    print(f"Sortie                             : {QUEUE_FILE}")
if __name__=="__main__": main()
