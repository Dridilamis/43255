# -*- coding: utf-8 -*-
from pathlib import Path
import json, re, os, sys, shutil, unicodedata
from collections import Counter, defaultdict
from pathlib import Path
import os

# ============================================================
# PATHS â€” TRACE Ã‰TAGE 9
# ============================================================

BASE = (
    Path(r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM")
)

RED = BASE / "Reduction_hallucinations"

# EntrÃ©e officielle : sortie validÃ©e de l'Ã‰tage 8
INPUT_DIR = Path(
    r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM"
    r"\Reduction_hallucinations\SGCE\MultiAgent\corrected"
)

# Ã‰tage 9 â€” Entity + Relation Recovery
STAGE = RED / "relation_recovery Etage 9"

# Textes bruts Mistral
TEXT_DIR = RED / "Sortie_Textes_Brut_MistralSmall4"

# Ontologie TRACE-Sepsis
GUIDELINE = BASE / "ontologie_sepsis_graph_v1.6.json"

# CrÃ©ation du dossier de sortie
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
    """Preuve forte : les deux mentions apparaissent dans la mÃªme phrase ou deux phrases adjacentes."""
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


def main():
    print("="*100); print("ETAGE 9 - DIAGNOSTIC"); print("="*100)
    print("INPUT :",INPUT_DIR, "=>", INPUT_DIR.exists())
    print("TEXT  :",TEXT_DIR, "=>", TEXT_DIR.exists())
    print("GUIDE :",GUIDELINE, "=>", GUIDELINE.exists())
    docs=clinical_files(INPUT_DIR) if INPUT_DIR.exists() else []
    print("Documents cliniques :",len(docs))
    if GUIDELINE.exists():
        sig=signatures(); print("Signatures relationnelles :",len(sig))
        print("Exemples :",list(sig.keys())[:10])
    if docs:
        ec=sum(len(d.get("global_entities",[])) for _,d in docs)
        rc=sum(len(d.get("global_relations",[])) for _,d in docs)
        print("EntitÃ©s :",ec); print("Relations :",rc)
if __name__=="__main__": main()

