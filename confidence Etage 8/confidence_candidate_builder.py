# -*- coding: utf-8 -*-

"""
TRACE — ETAGE 8 V2 — Candidate Builder
Structure TRACE-Sepsis réelle:
  global_entities / global_relations
Un JSON clinique doit contenir source_file + global_entities + global_relations.
Les rapports JSON sont ignorés.
"""
from pathlib import Path
import json, re, unicodedata
from collections import Counter

HERE=Path(__file__).resolve().parent
BASE=HERE.parent
INPUT_DIR=BASE/"negation Etage 7"/"negation_safe_corrected"
TEXT_DIR=BASE/"Sortie_Textes_Brut_MistralSmall4"
OUTDIR=HERE/"queues"
OUT=OUTDIR/"confidence_candidates.json"

def norm(x):
    x="" if x is None else str(x)
    x=unicodedata.normalize("NFKD",x)
    x="".join(c for c in x if not unicodedata.combining(c)).lower().replace("’","'")
    return re.sub(r"\s+"," ",x).strip()

def is_clinical(d):
    return (isinstance(d,dict) and isinstance(d.get("source_file"),str)
            and isinstance(d.get("global_entities"),list)
            and isinstance(d.get("global_relations"),list))

def find_text(d,jp):
    src=Path(d.get("source_file","")).stem
    candidates=list(TEXT_DIR.glob("*.txt"))
    exact={norm(p.stem):p for p in candidates}
    for s in (src,jp.stem,jp.stem.split("_trace_sepsis")[0]):
        if norm(s) in exact: return exact[norm(s)]
    ns=norm(src)
    for p in candidates:
        np=norm(p.stem)
        if ns and (ns in np or np in ns): return p
    return None

def grounding(mention, raw):
    m,t=norm(mention),norm(raw)
    if not m or not t: return {"status":"NOT_FOUND","quality":"none"}
    if m in t: return {"status":"FOUND","quality":"exact_normalized"}
    toks=[z for z in re.findall(r"\w+",m) if len(z)>2]
    if len(toks)>=2:
        ratio=sum(z in t for z in toks)/len(toks)
        if ratio>=.80:return {"status":"PARTIAL","quality":"strong_token_overlap"}
        if ratio>=.50:return {"status":"AMBIGUOUS","quality":"partial_token_overlap"}
    return {"status":"NOT_FOUND","quality":"none"}

def main():
    OUTDIR.mkdir(parents=True,exist_ok=True)
    stats=Counter(); items=[]; ignored=[]
    for jp in sorted(INPUT_DIR.glob("*.json")):
        try: d=json.loads(jp.read_text(encoding="utf-8"))
        except Exception:
            stats["invalid_json_ignored"]+=1; ignored.append(jp.name); continue
        if not is_clinical(d):
            stats["non_clinical_json_ignored"]+=1; ignored.append(jp.name); continue

        stats["clinical_documents"]+=1
        tp=find_text(d,jp)
        raw=tp.read_text(encoding="utf-8",errors="ignore") if tp else ""
        stats["texts_found" if tp else "texts_missing"]+=1

        schema=d.get("schema",{})
        allowed_entities=set(schema.get("entity_types",[]))
        allowed_relations=set(schema.get("relation_types",[]))
        ents=d["global_entities"]; rels=d["global_relations"]
        ids={str(e.get("identifiant_entite","")):e for e in ents}

        for e in ents:
            eid=str(e.get("identifiant_entite",""))
            mention=e.get("preuve") or e.get("name") or ""
            typ=e.get("type") or e.get("categorie") or ""
            g=grounding(mention,raw)
            trace_keys=sorted(k for k in e if str(k).startswith("trace_"))
            items.append({
                "document":jp.name,"source_file":d["source_file"],"kind":"ENTITY","id":eid,
                "mention":mention,"type":typ,"grounding":g,
                "ontology_type_valid": (typ in allowed_entities) if allowed_entities else None,
                "trace_validation_keys":trace_keys
            })
            stats["entities_audited"]+=1; stats["entity_"+g["status"]]+=1

        for r in rels:
            rid=str(r.get("identifiant_relation",""))
            src=str(r.get("identifiant_entite_sujet",""))
            tgt=str(r.get("identifiant_entite_objet",""))
            typ=r.get("type_relation","")
            proof=r.get("preuve") or ""
            g=grounding(proof,raw)
            trace_keys=sorted(k for k in r if str(k).startswith("trace_"))
            items.append({
                "document":jp.name,"source_file":d["source_file"],"kind":"RELATION","id":rid,
                "relation_type":typ,"source":src,"target":tgt,"proof":proof,"grounding":g,
                "source_exists":src in ids,"target_exists":tgt in ids,
                "ontology_relation_valid":(typ in allowed_relations) if allowed_relations else None,
                "trace_validation_keys":trace_keys
            })
            stats["relations_audited"]+=1; stats["relation_"+g["status"]]+=1

    payload={"stage":"TRACE_STAGE_8_V2_CANDIDATES","stats":dict(stats),
             "ignored_json_files":ignored,"items":items}
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    print("="*110); print("TRACE / ETAGE 8 V2 - CONFIDENCE CANDIDATE BUILDER"); print("="*110)
    for k,v in stats.items(): print(f"{k:38}: {v}")
    if ignored: print("JSON non cliniques ignores       :",", ".join(ignored))
    print("Sortie :",OUT)
    if stats["clinical_documents"]==0 or stats["entities_audited"]==0:
        raise SystemExit("ECHEC: aucune structure clinique TRACE reconnue.")
    if stats["texts_missing"]:
        raise SystemExit("ECHEC: au moins un dossier clinique ne possède pas de texte brut correspondant.")

if __name__=="__main__": main()
