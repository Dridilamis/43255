# -*- coding: utf-8 -*-
import json, re, unicodedata
from pathlib import Path
from collections import Counter

AGENT_DIR = Path(__file__).resolve().parent
MULTIAGENT_DIR = AGENT_DIR.parent
SGCE_DIR = MULTIAGENT_DIR.parent
BASE_DIR = SGCE_DIR.parent
M = MULTIAGENT_DIR
PATTERNS_DIR = SGCE_DIR / "Patterns"
QUEUE = M / "queues" / "agent_d_queue_contextualized.json"
OUT = M / "outputs" / "agent_d_decisions.json"

CLINICAL_DIR_CANDIDATES = [SGCE_DIR / "orphan_resolution" / "corrected"]

LEXICON = {
    "IMAGERIE_PROCEDURE": ("tdm","scanner","irm","radiographie","échographie","echographie","imagerie"),
    "TRAITEMENT": ("traitement","antibiotique","amoxicilline","vancomycine","amikacine","noradrénaline","adrenaline","adrénaline"),
    "MICRO_ORGANISME": ("staphylococcus","staphylocoque","streptococcus","streptocoque","e coli","escherichia","klebsiella","pseudomonas","candida","germe","bactérie","bacterie"),
    "SYMPTOME": ("douleur","fièvre","fievre","toux","dyspnée","dyspnee","vomissement","apyrexie"),
    "SIGNE_VITAL": ("température","temperature","tension","pression artérielle","pression arterielle","fréquence cardiaque","frequence cardiaque","spo2","saturation"),
    "BIOMARQUEUR": ("crp","pct","procalcitonine","créatinine","creatinine","lactate","leucocytes"),
    "LABEL_NOSOLOGIQUE": ("sepsis","choc septique","pneumonie","diagnostic","syndrome"),
    "DEFAILLANCE_ORGANE": ("insuffisance","défaillance","defaillance","ira","rénale","renale","respiratoire"),
    "FOYER_INFECTIEUX": ("foyer","pneumonie","pulmonaire","urinaire","abdominal","infection"),
    "POSOLOGIE": ("mg","g/j","mg/j","par jour","x2","x3","dose"),
    "CONTEXTE_ACQUISITION": ("nosocomial","communautaire","acquis","hospitalier"),
}

def load_json(p):
    with p.open("r",encoding="utf-8") as f:return json.load(f)

def resolve_clinical_dir():
    for d in CLINICAL_DIR_CANDIDATES:
        if d.exists() and any(d.glob("*.json")): return d
    raise FileNotFoundError("Contexte clinique Agent D introuvable.")

def norm(s):
    s=unicodedata.normalize("NFKD",str(s or "").lower())
    s="".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+"," ",re.sub(r"[^a-z0-9]+"," ",s)).strip()

def eid(e): return e.get("identifiant_entite") or e.get("id") or e.get("entity_id")
def etype(e): return e.get("categorie") or e.get("type") or e.get("entity_type") or ""
def etext(e): return " | ".join(str(e.get(k)).strip() for k in ("preuve","name","valeur","libelle","parametre","texte","text") if e.get(k))
def rid(r): return r.get("identifiant_relation") or r.get("id") or r.get("relation_id")
def rtype(r): return r.get("type_relation") or r.get("relation") or r.get("relation_type") or r.get("predicate") or r.get("type") or ""
def rsrc(r): return r.get("identifiant_entite_sujet") or r.get("from_id") or r.get("subject_id") or r.get("source")
def rtgt(r): return r.get("identifiant_entite_objet") or r.get("to_id") or r.get("object_id") or r.get("target")

def entities(doc):
    if isinstance(doc.get("global_entities"),list):return doc["global_entities"]
    z=[]
    for p in doc.get("pages",[]) or []: z += p.get("entities",[]) or []
    return z

def find_entity(doc,x):
    return next((e for e in entities(doc) if str(eid(e))==str(x)),None)

def deep_get_first(d, keys):
    if not isinstance(d,dict): return None
    for k in keys:
        if d.get(k) not in (None,""): return d.get(k)
    for v in d.values():
        if isinstance(v,dict):
            x=deep_get_first(v,keys)
            if x not in (None,""): return x
    return None

def parse_candidate(item):
    s=item.get("symbolic_candidate") or {}
    relation=deep_get_first(s,("relation","relation_data","relation_candidate"))
    if not isinstance(relation,dict): relation={}
    role=str(deep_get_first(s,("role","mismatch_role","invalid_role","endpoint_role")) or "").upper()
    actual=deep_get_first(s,("actual_type","current_type","observed_type","entity_type"))
    expected=deep_get_first(s,("expected_type","expected_entity_type","expected_source_type","expected_target_type"))
    entity_id=deep_get_first(s,("entity_id","endpoint_id","source_id","target_id","candidate_entity_id"))
    relation_id=rid(relation) or deep_get_first(s,("relation_id",))
    relation_type=rtype(relation) or deep_get_first(s,("relation_type","type_relation"))
    if role=="SOURCE": entity_id=entity_id or rsrc(relation)
    elif role=="TARGET": entity_id=entity_id or rtgt(relation)
    return {"role":role,"actual_type":actual,"expected_type":expected,"entity_id":entity_id,
            "relation_id":relation_id,"relation_type":relation_type}

def lexicon_support(text, expected_type):
    t=norm(text)
    return [v for v in LEXICON.get(expected_type,()) if norm(v) in t]

def main():
    q=load_json(QUEUE)
    cdir=resolve_clinical_dir()
    docs={}
    for p in cdir.glob("*.json"):
        try: docs[p.name]=load_json(p)
        except: pass

    decisions=[]
    for item in q:
        doc=docs.get(item.get("document"))
        p=parse_candidate(item)
        ctx=item.get("text_context") or {}
        page_text=ctx.get("page_text","")
        entity=find_entity(doc or {},p["entity_id"]) if p["entity_id"] else None
        ev=etext(entity) if entity else ""
        support=lexicon_support(ev+" "+page_text,p["expected_type"]) if p["expected_type"] else []

        if entity and p["expected_type"] and etype(entity)!=p["expected_type"] and support:
            decision,action,conf="CORRECT","RETYPE_ENTITY",0.84
            reason="Le type attendu est soutenu par le texte source et l'entité existe encore."
        else:
            decision,action,conf="REVIEW","NONE",0.45
            reason="Aucune correction DOMAIN/RANGE suffisamment déterminée par le texte et le graphe."

        decisions.append({
            "candidate_id":item.get("candidate_id"),
            "document":item.get("document"),
            "agent":"agent_pattern_d",
            "decision":decision,
            "action":action,
            "confidence":conf,
            "reason":reason,
            "evidence":ev,
            "metadata":{
                **p,
                "current_entity_type":etype(entity) if entity else None,
                "lexicon_support":support,
                "text_file":ctx.get("text_file"),
                "page_number":ctx.get("page_number"),
                "text_grounded":bool(support),
            }
        })

    dc=Counter(x["decision"] for x in decisions)
    ac=Counter(x["action"] for x in decisions)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps({"agent":"agent_pattern_d","clinical_context_directory":str(cdir),"decisions":decisions},ensure_ascii=False,indent=2),encoding="utf-8")

    print("="*96)
    print("TRACE / SGCE - AGENT PATTERN D")
    print("="*96)
    print(f"Contexte clinique                 : {cdir}")
    print(f"Cas reçus                         : {len(q)}")
    print("\nDECISIONS"); print("-"*96)
    for k,v in dc.items(): print(f"{k:<40}: {v}")
    print("\nACTIONS PROPOSEES"); print("-"*96)
    for k,v in ac.items(): print(f"{k:<40}: {v}")
    print(f"\nSortie                            : {OUT}")
    print("\nAucun JSON clinique n'a été modifié.")

if __name__=="__main__": main()
