# -*- coding: utf-8 -*-

"""
semantic_factual_candidate_builder.py
TRACE / SGCE - SEMANTIC FACTUAL CANDIDATE BUILDER V2
Entrée : root_cause/root_cause_entity_safe_corrected
Sortie : semantic_factual/queues/semantic_factual_candidates.json
Aucune donnée clinique n'est modifiée.
"""
import json, re, unicodedata
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent
STAGE3_DIR = ROOT.parent
REDUCTION_DIR = STAGE3_DIR.parent
PROJECT_DIR = REDUCTION_DIR.parent

# Entrée clinique officielle : sortie validée de Root Cause.
SOURCE_DIR = STAGE3_DIR / "root_cause" / "root_cause_entity_safe_corrected"

# Textes bruts produits par Mistral, conservés à la racine du projet OCR vers LLM.
TEXT_DIR = PROJECT_DIR / "Sortie_Textes_Brut_MistralSmall4"
INPUT_DIR = SOURCE_DIR
OUTPUT_FILE = ROOT / "queues" / "semantic_factual_candidates.json"

def load_json(p):
    with Path(p).open("r",encoding="utf-8") as f:return json.load(f)

def clinical_files(d):
    out=[]
    for p in sorted(Path(d).glob("*.json")):
        if p.name.endswith("_report.json"):continue
        try:x=load_json(p)
        except Exception:continue
        if isinstance(x,dict) and any(k in x for k in ("pages","global_entities","global_relations")):out.append(p)
    return out

def eid(e): return e.get("identifiant_entite") or e.get("id") or e.get("entity_id")
def etype(e): return e.get("categorie") or e.get("type") or e.get("entity_type") or ""
def etext(e):
    vals=[]
    for k in ("preuve","texte","text","name","nom","libelle","parametre","valeur"):
        v=e.get(k)
        if v not in (None,""):
            s=str(v).strip()
            if s and s not in vals:vals.append(s)
    return " | ".join(vals)
def r_id(r): return r.get("identifiant_relation") or r.get("id") or r.get("relation_id")
def r_type(r): return r.get("type_relation") or r.get("relation") or r.get("relation_type") or r.get("predicate") or r.get("type") or ""
def r_src(r): return r.get("identifiant_entite_sujet") or r.get("from_id") or r.get("subject_id") or r.get("source")
def r_tgt(r): return r.get("identifiant_entite_objet") or r.get("to_id") or r.get("object_id") or r.get("target")
def entities(doc):
    if isinstance(doc.get("global_entities"),list): return doc["global_entities"]
    return [e for p in doc.get("pages",[]) or [] for e in p.get("entities",[]) or []]
def relations(doc):
    if isinstance(doc.get("global_relations"),list): return doc["global_relations"]
    return [r for p in doc.get("pages",[]) or [] for r in p.get("relations",[]) or []]

def clinical_status(e):
    for k in ("trace_context_status","trace_temporal_status","trace_temporal_status_audit","temporal_status_annotation"):
        a=e.get(k)
        if isinstance(a,dict):
            return a.get("clinical_status") or a.get("status") or a.get("assertion_status")
    if e.get("nie") is True:return "NEGATED"
    return None

def find_text_file(name):
    stem=Path(name).stem
    xs=list(TEXT_DIR.glob(f"{stem}*.txt"))
    if xs:return xs[0]
    short=stem.split("_trace_sepsis")[0]
    xs=list(TEXT_DIR.glob(f"{short}*.txt"))
    return xs[0] if xs else None

def norm(s):
    s=unicodedata.normalize("NFKD",str(s or ""))
    s="".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+"," ",s).strip()

def main():
    if not INPUT_DIR.exists():raise FileNotFoundError(f"Entrée introuvable : {INPUT_DIR}")
    rows=[]; docs=0; unresolved_s=0; unresolved_t=0; missing_text=0
    for p in clinical_files(INPUT_DIR):
        docs+=1; doc=load_json(p)
        emap={str(eid(e)):e for e in entities(doc) if eid(e) is not None}
        tf=find_text_file(p.name)
        text=tf.read_text(encoding="utf-8",errors="ignore") if tf else ""
        if not tf:missing_text+=1
        for r in relations(doc):
            s=emap.get(str(r_src(r))); t=emap.get(str(r_tgt(r)))
            if s is None:unresolved_s+=1
            if t is None:unresolved_t+=1
            rows.append({
                "candidate_id":f"SF_{len(rows)+1:06d}",
                "document":p.name,
                "relation_id":r_id(r),
                "relation_type":r_type(r),
                "source_id":r_src(r),"target_id":r_tgt(r),
                "source_resolved":s is not None,"target_resolved":t is not None,
                "source_type":etype(s) if s else None,"target_type":etype(t) if t else None,
                "source_text":etext(s) if s else None,"target_text":etext(t) if t else None,
                "source_clinical_status":clinical_status(s) if s else None,
                "target_clinical_status":clinical_status(t) if t else None,
                "source_proof":s.get("preuve") if s else None,
                "target_proof":t.get("preuve") if t else None,
                "document_text_available":bool(text),
                "source_in_document":norm(etext(s)) in norm(text) if s and etext(s) and text else False,
                "target_in_document":norm(etext(t)) in norm(text) if t and etext(t) and text else False,
                "text_file":str(tf) if tf else None
            })
    OUTPUT_FILE.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps({"builder":"semantic_factual_candidate_builder","mode":"CONSERVATIVE_RELATION_FACT_AUDIT_V2",
      "source_directory":str(INPUT_DIR),"summary":{"documents_analysed":docs,"candidates_built":len(rows),
      "unresolved_sources":unresolved_s,"unresolved_targets":unresolved_t,"missing_texts":missing_text},"candidates":rows},
      ensure_ascii=False,indent=2),encoding="utf-8")
    print("="*112);print("TRACE / SGCE - SEMANTIC FACTUAL CANDIDATE BUILDER V2");print("="*112)
    print(f"Documents analysés                 : {docs}");print(f"Relations candidates               : {len(rows)}")
    print(f"Sources non résolues               : {unresolved_s}");print(f"Cibles non résolues                : {unresolved_t}")
    print(f"Textes manquants                   : {missing_text}");print(f"\nSortie                             : {OUTPUT_FILE}")
    print("\nAucune donnée clinique n'a été modifiée.")
if __name__=="__main__":main()
