# -*- coding: utf-8 -*-
"""
Canonicalisation symétrique + évaluation F1 de toutes les sorties TRACE officielles.
"""
from pathlib import Path
import os, sys, subprocess, re, csv, json, shutil

os.environ["PYTHONUTF8"]="1"
os.environ["PYTHONIOENCODING"]="utf-8"

BASE = (
    Path(r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM")
)

RED = BASE / "Reduction_hallucinations"
GOLD = BASE / "gold_canonical_par_documentF"

HERE = Path(__file__).resolve().parent

CONV = HERE / "TRACE_to_canonical.py"
ENT = HERE / "Matching_entites_CANONICAL.py"
REL = HERE / "Matching_relations_CANONICAL.py"

OUT = RED / "evaluation_canonical_TRACE"

STAGES = [
    (
        "02_SGCE",
        RED / "SGCE" / "MultiAgent" / "corrected"
    ),
    (
        "03_DOCUMENT_FACTUAL",
        RED / "document_grounding Etage 3"
        / "semantic_factual"
        / "semantic_factual_safe_corrected"
    ),
    (
        "04_ONTOLOGY",
        RED / "ontology Etage 4"
        / "ontology_duplicates"
        / "duplicate_entities"
        / "duplicate_entity_safe_merged"
    ),
    (
        "05_NUMERIC_UNIT",
        RED / "numeric_unit Etage 5"
        / "numeric_unit_safe_corrected"
    ),
    (
        "06_TEMPORAL",
        RED / "temporal Etage 6"
        / "temporal_status_safe_corrected"
    ),
    (
        "07_NEGATION",
        RED / "negation Etage 7"
        / "negation_safe_corrected"
    ),
    (
        "08_CONFIDENCE",
        RED / "confidence Etage 8"
        / "confidence_assessed_safe"
    ),
    
]
def run(cmd, cwd=None):
    p=subprocess.run(cmd,cwd=cwd,env=os.environ.copy(),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                     text=True,encoding="utf-8",errors="replace")
    print(p.stdout)
    return p.returncode,p.stdout

def metric(txt,label):
    m=re.search(r"---\s*RELAXED\s*---(.*?)(?=\n\s*---|\Z)",txt,re.I|re.S)
    if not m:return None
    x=re.search(rf"{re.escape(label)}\s*:\s*([0-9.]+)",m.group(1),re.I)
    return float(x.group(1)) if x else None

OUT.mkdir(parents=True,exist_ok=True)
rows=[]

for stage,pred in STAGES:
    print("\n"+"="*110+"\n"+stage+"\n"+"="*110)
    if not pred.is_dir():
        rows.append({"stage":stage,"status":"MISSING","source":str(pred)})
        continue

    root=OUT/stage
    canonical=root/"canonical_prediction"
    if canonical.exists(): shutil.rmtree(canonical)
    canonical.mkdir(parents=True)

    rc0,t0=run([sys.executable,"-X","utf8",str(CONV),str(pred),str(canonical)],str(HERE))
    if rc0:
        rows.append({"stage":stage,"status":"CONVERSION_FAIL","source":str(pred)})
        continue

    rc1,te=run([sys.executable,"-X","utf8",str(ENT),str(GOLD),str(canonical),str(root/"entities")],str(HERE))
    rc2,tr=run([sys.executable,"-X","utf8",str(REL),str(GOLD),str(canonical),str(root/"relations")],str(HERE))
    (root/"terminal_entities.txt").write_text(te,encoding="utf-8")
    (root/"terminal_relations.txt").write_text(tr,encoding="utf-8")

    rows.append({
      "stage":stage,"status":"PASS" if rc1==0 and rc2==0 else "FAIL","source":str(pred),
      "entity_precision":metric(te,"Micro Precision"),"entity_recall":metric(te,"Micro Recall"),
      "entity_f1":metric(te,"Micro F1"),"entity_macro_f1":metric(te,"Macro F1 docs"),
      "relation_precision":metric(tr,"Micro Precision"),"relation_recall":metric(tr,"Micro Recall"),
      "relation_f1":metric(tr,"Micro F1"),"relation_macro_f1":metric(tr,"Macro F1 docs"),
    })

fields=["stage","status","source","entity_precision","entity_recall","entity_f1","entity_macro_f1",
        "relation_precision","relation_recall","relation_f1","relation_macro_f1"]
with (OUT/"canonical_F1_summary.csv").open("w",newline="",encoding="utf-8-sig") as f:
    w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore");w.writeheader();w.writerows(rows)
(OUT/"canonical_F1_summary.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")

print("\n"+"="*105)
print("TABLEAU FINAL — CANONICAL + RELAXED")
print("="*105)
print(f"{'ETAGE':28} | {'Ent P':>8} {'Ent R':>8} {'Ent F1':>8} | {'Rel P':>8} {'Rel R':>8} {'Rel F1':>8}")
print("-"*105)
for r in rows:
    if r.get("status")!="PASS":
        print(f"{r['stage']:28} | {r.get('status')}")
        continue
    pc=lambda x:f"{100*x:7.2f}%" if isinstance(x,(float,int)) else " N/A"
    print(f"{r['stage']:28} | {pc(r['entity_precision'])} {pc(r['entity_recall'])} {pc(r['entity_f1'])} | "
          f"{pc(r['relation_precision'])} {pc(r['relation_recall'])} {pc(r['relation_f1'])}")
print("\nRésultats :",OUT)
