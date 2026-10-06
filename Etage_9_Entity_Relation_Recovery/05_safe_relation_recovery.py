# -*- coding: utf-8 -*-
from pathlib import Path
import json, re, os, sys, shutil, unicodedata
from collections import Counter, defaultdict

BASE = Path(r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM")
RED = BASE / "Reduction_hallucinations"
STAGE = RED / "relation_recovery Etage 9"
INPUT_DIR = STAGE / "entity_recovery_v3_safe_corrected"
TEXT_DIR = RED / "Sortie_Textes_Brut_MistralSmall4"
GUIDELINE = BASE / "ontologie_sepsis_graph_v1.6.json"
STAGE.mkdir(parents=True, exist_ok=True)

def norm(x):
    x="" if x is None else str(x)
    x=unicodedata.normalize("NFKC",x).lower().replace("\u00a0"," ")
    return re.sub(r"\s+"," ",x).strip()

def eid(e): return str(e.get("identifiant_entite") or e.get("id") or e.get("entity_id") or "").strip()
def etype(e): return str(e.get("type") or e.get("categorie") or e.get("label") or "").strip().upper()
def etext(e):
    for k in ("name","mention","text","preuve"):
        if e.get(k) is not None and str(e.get(k)).strip(): return str(e.get(k)).strip()
    p=str(e.get("parametre") or "").strip()
    v="" if e.get("valeur") is None else str(e.get("valeur")).strip()
    u="" if e.get("unite") is None else str(e.get("unite")).strip()
    return " ".join(x for x in (p,v,u) if x).strip()

def rid(r): return str(r.get("identifiant_relation") or r.get("id") or "").strip()
def rtype(r): return str(r.get("type_relation") or r.get("relation") or r.get("label") or "").strip()
def rs(r): return str(r.get("identifiant_entite_sujet") or r.get("subject_id") or "").strip()
def ro(r): return str(r.get("identifiant_entite_objet") or r.get("object_id") or "").strip()

def load(p): return json.loads(Path(p).read_text(encoding="utf-8-sig"))
def dump(p,x): Path(p).parent.mkdir(parents=True,exist_ok=True); Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding="utf-8")

def clinical_files(folder):
    out=[]
    for p in sorted(Path(folder).glob("*.json")):
        try:
            d=load(p)
            if isinstance(d,dict) and isinstance(d.get("global_entities"),list) and isinstance(d.get("global_relations"),list):
                out.append((p,d))
        except Exception: pass
    return out

def walk(o):
    if isinstance(o,dict):
        yield o
        for v in o.values(): yield from walk(v)
    elif isinstance(o,list):
        for v in o: yield from walk(v)

def ontology_root():
    g=load(GUIDELINE)
    return g.get("ontologie_sepsis_graph", g)

def signatures():
    """Parse exactement V1.6: relations/<groupe>/<relation>/{domaine,image}."""
    g=ontology_root()
    sig=defaultdict(lambda:{"source":set(),"target":set()})
    for group_name, group in (g.get("relations") or {}).items():
        if not isinstance(group,dict): continue
        for rn,spec in group.items():
            if not isinstance(spec,dict): continue
            dom=spec.get("domaine"); img=spec.get("image")
            if isinstance(dom,str) and dom.strip(): sig[rn]["source"].add(dom.strip().upper())
            if isinstance(img,str) and img.strip(): sig[rn]["target"].add(img.strip().upper())
    return sig

def ontology_entity_types():
    return {str(k).upper() for k in (ontology_root().get("entites") or {}).keys()}

def text_for(stem):
    candidates=[TEXT_DIR/f"{stem}.txt",TEXT_DIR/f"{stem}_texte_brut.txt",TEXT_DIR/f"{stem}_text_brut.txt"]
    for p in candidates:
        if p.exists(): return p.read_text(encoding="utf-8-sig",errors="replace")
    for p in TEXT_DIR.glob("*.txt"):
        if stem.lower() in p.stem.lower(): return p.read_text(encoding="utf-8-sig",errors="replace")
    return ""

def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?;])\s+|\n+",text) if s.strip()]

def direct_context(text,a,b):
    """Preuve forte : les deux mentions apparaissent dans la même phrase ou deux phrases adjacentes."""
    na,nb=norm(a),norm(b)
    if not na or not nb: return None
    ss=sentences(text)
    for i,s in enumerate(ss):
        ns=norm(s)
        if na in ns and nb in ns: return {"strength":"SAME_SENTENCE","evidence":s}
    for i in range(len(ss)-1):
        ns=norm(ss[i]+" "+ss[i+1])
        if na in ns and nb in ns: return {"strength":"ADJACENT_SENTENCES","evidence":ss[i]+" "+ss[i+1]}
    return None

def relation_exists(rels,s,rn,o):
    return any(rs(r)==s and ro(r)==o and rtype(r)==rn for r in rels)

IN=STAGE/"04_adjudicated.json"; OUTDIR=STAGE/"relation_recovery_safe_corrected"

def main():
    data=load(IN); bydoc=defaultdict(list)
    for x in data["candidates"]:
        if x.get("adjudication")=="SAFE_ACCEPT":
            bydoc[x["document"]].append(x)

    if OUTDIR.exists(): shutil.rmtree(OUTDIR)
    OUTDIR.mkdir(parents=True)

    ops=[]; docsmod=0
    for p,d in clinical_files(INPUT_DIR):
        out=json.loads(json.dumps(d))
        rels=out["global_relations"]
        changed=0
        used={rid(r) for r in rels}
        existing={(rs(r),rtype(r),ro(r)) for r in rels}
        seq=1

        for x in bydoc.get(p.name,[]):
            sig=(x["source_id"],x["relation"],x["target_id"])
            if sig in existing:
                continue

            while f"RR9_R{seq:05d}" in used:
                seq+=1

            nr={
              "identifiant_relation":f"RR9_R{seq:05d}",
              "identifiant_entite_sujet":x["source_id"],
              "entite_sujet":x["source_text"],
              "type_relation":x["relation"],
              "identifiant_entite_objet":x["target_id"],
              "entite_objet":x["target_text"],
              "subject":x["source_text"],
              "object":x["target_text"],
              "preuve":x["evidence"],
              "note_clinique":"Etage 9 Relation Recovery - conservative direct evidence",
              "type_inference":"relation_recovery_etage_9",
              "confiance":"elevee",
              "trace_recovery":{
                  "stage":9,
                  "gold_used":False,
                  "evidence_strength":x.get("evidence_strength"),
                  "endpoint_distance":x.get("endpoint_distance"),
                  "adjudication":"SAFE_ACCEPT"
              }
            }
            rels.append(nr)
            used.add(nr["identifiant_relation"])
            existing.add(sig)
            changed+=1
            ops.append({
                "document":p.name,
                "candidate_id":x["candidate_id"],
                "relation_id":nr["identifiant_relation"],
                "source":x["source_text"],
                "relation":x["relation"],
                "target":x["target_text"],
                "evidence":x["evidence"]
            })
            seq+=1

        dump(OUTDIR/p.name,out)
        if changed: docsmod+=1

    dump(STAGE/"05_applied_operations.json",{
        "gold_used":False,
        "operations":ops,
        "summary":{"operations":len(ops),"documents_modified":docsmod}
    })
    print("ETAGE 9 / 5 - SAFE RELATION RECOVERY")
    print("Operations :",len(ops))
    print("Documents modifiés :",docsmod)
    print("Gold utilisé : NON")
    print("Sortie :",OUTDIR)

if __name__=="__main__":
    main()
