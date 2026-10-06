# -*- coding: utf-8 -*-
from pathlib import Path
import json, re, shutil, hashlib
from collections import Counter

BASE_DIR = Path(r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM\Reduction_hallucinations")
M = BASE_DIR / "MultiAgent"
CLINICAL_DIR = M / "agent_c_corrected"

def load_json(p):
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)

def save_json(p, x):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(x, ensure_ascii=False, indent=2), encoding="utf-8")

def eid(e):
    return e.get("identifiant_entite") or e.get("id") or e.get("entity_id")

def entities(doc):
    if isinstance(doc.get("global_entities"), list):
        return doc["global_entities"]
    z=[]
    for p in doc.get("pages",[]) or []: z += p.get("entities",[]) or []
    return z

def relations(doc):
    if isinstance(doc.get("global_relations"), list):
        return doc["global_relations"]
    z=[]
    for p in doc.get("pages",[]) or []: z += p.get("relations",[]) or []
    return z

def rsrc(r):
    return r.get("identifiant_entite_sujet") or r.get("from_id") or r.get("subject_id") or r.get("source")

def rtgt(r):
    return r.get("identifiant_entite_objet") or r.get("to_id") or r.get("object_id") or r.get("target")

QUEUE = M / "queues" / "agent_patient_reference_queue_contextualized.json"
OUT = M / "outputs" / "agent_patient_reference_decisions.json"

PATIENT = ("patient","chez le patient","prÃ©sente","presente","hospitalisÃ©","hospitalise","traitement","Ã©volution","evolution","admis","admission")
REFERENCE = ("dÃ©finition","definition","seuil","seuils","critÃ¨re","critere","classification","recommandation","selon","rÃ©fÃ©rence","reference","tableau","norme")

def norm(s):
    import unicodedata
    s=unicodedata.normalize("NFKD",str(s or "").lower())
    s="".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+"," ",re.sub(r"[^a-z0-9]+"," ",s)).strip()

def candidate_entity_id(item):
    blob=json.dumps(item.get("symbolic_candidate") or item,ensure_ascii=False)
    m=re.search(r"\b(P\d+_E\d+)\b",blob)
    return m.group(1) if m else None

def entity_text(e):
    return " | ".join(str(e.get(k)).strip() for k in ("preuve","name","valeur","libelle","parametre","texte","text") if e.get(k))

def main():
    q=load_json(QUEUE)
    docs={}
    for p in CLINICAL_DIR.glob("*.json"):
        try:
            d=load_json(p)
            if any(k in d for k in ("pages","global_entities","global_relations")): docs[p.name]=d
        except: pass
    decisions=[]
    for item in q:
        doc=docs.get(item.get("document"))
        cid=candidate_entity_id(item)
        ent=next((e for e in entities(doc or {}) if str(eid(e))==str(cid)),None)
        ev=entity_text(ent) if ent else ""
        txt=(item.get("text_context") or {}).get("page_text","")
        grounded=bool(ev and norm(ev) and any(part in norm(txt) for part in [norm(x) for x in ev.split("|") if len(norm(x))>=4]))
        ph=sum(norm(x) in norm(txt) for x in PATIENT)
        rh=sum(norm(x) in norm(txt) for x in REFERENCE)
        # Conservative: classification only. Removal is never proposed from lexical cues alone.
        if not grounded:
            dec,act,conf,reason="REVIEW","NONE",0.30,"Preuve textuelle insuffisante."
        elif rh>=2 and ph==0:
            dec,act,conf,reason="REFERENCE","NONE",0.78,"Contexte probablement rÃ©fÃ©rentiel; exclusion automatique interdite sans validation structurelle."
        elif ph>=1 and rh==0:
            dec,act,conf,reason="PATIENT","KEEP",0.82,"Contexte explicitement orientÃ© patient."
        else:
            dec,act,conf,reason="REVIEW","NONE",0.50,"Contexte patient/rÃ©fÃ©rence ambigu."
        decisions.append({
            "candidate_id":item.get("candidate_id"),"document":item.get("document"),
            "agent":"agent_patient_reference","decision":dec,"action":act,"confidence":conf,
            "reason":reason,"evidence":ev,
            "metadata":{"candidate_entity_id":cid,"text_grounded":grounded,
                        "patient_hits":ph,"reference_hits":rh,
                        "page_number":(item.get("text_context") or {}).get("page_number"),
                        "text_file":(item.get("text_context") or {}).get("text_file")}
        })
    dc=Counter(x["decision"] for x in decisions); ac=Counter(x["action"] for x in decisions)
    save_json(OUT,{"agent":"agent_patient_reference","mode":"DOCUMENT_GROUNDED_CONSERVATIVE",
                   "clinical_context_directory":str(CLINICAL_DIR),"decisions":decisions})
    print("="*96);print("TRACE / SGCE - AGENT PATIENT / REFERENCE");print("="*96)
    print(f"Cas reÃ§us                         : {len(q)}")
    print("\nDECISIONS");print("-"*96)
    for k,v in dc.items():print(f"{k:<40}: {v}")
    print("\nACTIONS PROPOSEES");print("-"*96)
    for k,v in ac.items():print(f"{k:<40}: {v}")
    print(f"\nSortie                            : {OUT}")
    print("\nAucun JSON clinique n'a Ã©tÃ© modifiÃ©.")
if __name__=="__main__": main()

