# -*- coding: utf-8 -*-
"""
TRACE — Ablation F1 par étage.

Objectif :
- évaluer chaque sortie officielle avec EXACTEMENT les mêmes matchers que la baseline ;
- ne modifier ni les seuils ni les règles de matching ;
- produire un tableau CSV/JSON des métriques relaxed (et conserver tous les rapports détaillés).

IMPORTANT :
Les chemins STAGES ci-dessous reflètent l'architecture TRACE actuelle.
Si un dossier n'existe pas, il est marqué MISSING et l'évaluation continue.
"""
from pathlib import Path
import os, sys, subprocess, re, csv, json

# Force UTF-8 for child Python processes (Windows/PowerShell cp1252 fix)
os.environ['PYTHONUTF8'] = '1'
os.environ['PYTHONIOENCODING'] = 'utf-8'

HERE = Path(__file__).resolve().parent

if os.name == "nt":
    BASE = Path(r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM")
else:
    BASE = Path.home() / "TRACE" / "OCR vers LLM"

RED = BASE / "Reduction_hallucinations"
GOLD = BASE / "gold_canonical_par_documentF"

# Baseline = EXACTEMENT le dossier évalué avant TRACE.
STAGES = [
    ("00_BASELINE_MISTRAL",
     BASE / "Mistral" / "POSTPROCESSING_FINAL_V7_6_PRECISION_RECALL_GATED_43"),

    ("02_SGCE",
     RED / "SGCE" / "MultiAgent" / "corrected"),

    ("03_DOCUMENT_FACTUAL_GROUNDING",
     RED / "document_grounding Etage 3" / "semantic_factual" / "semantic_factual_safe_corrected"),

    ("04_ONTOLOGY_VALIDATION",
     RED / "ontology Etage 4" / "ontology_duplicates" / "duplicate_entities" / "duplicate_entity_safe_merged"),

    ("05_NUMERIC_UNIT",
     RED / "numeric_unit Etage 5" / "numeric_unit_safe_corrected"),

    ("06_TEMPORAL",
     RED / "temporal Etage 6" / "temporal_status_safe_corrected"),

    ("07_NEGATION",
     RED / "negation Etage 7" / "negation_safe_corrected"),

    ("08_CONFIDENCE",
     RED / "confidence Etage 8" / "confidence_assessed_safe"),

    ("08b_GROUNDING_GATE",
     RED / "grounding_gate Etage 8b" / "grounding_gate_safe"),
]

OUT = RED / "evaluation_ablation_F1_TRACE"
OUT.mkdir(parents=True, exist_ok=True)

ENTITY_SCRIPT = HERE / "Matching_entites_ABLATION.py"
RELATION_SCRIPT = HERE / "Matching_relations_ABLATION.py"

if not GOLD.is_dir():
    raise SystemExit(f"Gold Standard introuvable : {GOLD}")

def run_and_capture(script, gold, pred, output):
    output.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(
        [sys.executable, '-X', 'utf8', str(script), str(gold), str(pred), str(output)],
        cwd=str(HERE),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(p.stdout)
    return p.returncode, p.stdout

def metric(text, section, label):
    # Restrict parsing to the requested section.
    m = re.search(
        rf"---\s*{re.escape(section)}\s*---(.*?)(?=\n\s*---|\Z)",
        text, flags=re.I | re.S
    )
    if not m:
        return None
    block = m.group(1)
    x = re.search(rf"{re.escape(label)}\s*:\s*([0-9.]+)", block, flags=re.I)
    return float(x.group(1)) if x else None

def count(text, label):
    x = re.search(rf"{re.escape(label)}\s*:\s*(\d+)", text, flags=re.I)
    return int(x.group(1)) if x else None

rows = []

print("=" * 110)
print("TRACE — ABLATION F1 PAR ETAGE")
print("=" * 110)
print("Gold :", GOLD)
print("Les règles et seuils des matchers baseline ne sont pas modifiés.")

for stage, pred in STAGES:
    print("\n" + "#" * 110)
    print(stage)
    print("PRED :", pred)
    print("#" * 110)

    row = {"stage": stage, "prediction_dir": str(pred)}

    if not pred.is_dir():
        if stage == "00_BASELINE_MISTRAL":
            print("Baseline brute absente : utilisation des métriques baseline validées déjà obtenues avec ces mêmes matchers.")
            row.update({
                "status": "REFERENCE",
                "entity_precision": 0.7446,
                "entity_recall": 0.6810,
                "entity_f1": 0.7114,
                "entity_macro_f1": 0.7184,
                "relation_precision": 0.7451,
                "relation_recall": 0.6362,
                "relation_f1": 0.6864,
                "relation_macro_f1": 0.6831,
            })
            rows.append(row)
            continue
        print("DOSSIER ABSENT — étape ignorée.")
        row["status"] = "MISSING"
        rows.append(row)
        continue

    stage_out = OUT / stage
    ent_out = stage_out / "entities"
    rel_out = stage_out / "relations"

    rc_e, txt_e = run_and_capture(ENTITY_SCRIPT, GOLD, pred, ent_out)
    (stage_out / "terminal_entities.txt").write_text(txt_e, encoding="utf-8")

    rc_r, txt_r = run_and_capture(RELATION_SCRIPT, GOLD, pred, rel_out)
    (stage_out / "terminal_relations.txt").write_text(txt_r, encoding="utf-8")

    row["status"] = "PASS" if rc_e == 0 and rc_r == 0 else "FAIL"

    # Relaxed metrics = principal comparison requested.
    row["entity_precision"] = metric(txt_e, "RELAXED", "Micro Precision")
    row["entity_recall"] = metric(txt_e, "RELAXED", "Micro Recall")
    row["entity_f1"] = metric(txt_e, "RELAXED", "Micro F1")
    row["entity_macro_f1"] = metric(txt_e, "RELAXED", "Macro F1 docs")

    row["relation_precision"] = metric(txt_r, "RELAXED", "Micro Precision")
    row["relation_recall"] = metric(txt_r, "RELAXED", "Micro Recall")
    row["relation_f1"] = metric(txt_r, "RELAXED", "Micro F1")
    row["relation_macro_f1"] = metric(txt_r, "RELAXED", "Macro F1 docs")

    # Counts useful to explain F1 movements.
    row["entity_tp_exact"] = count(txt_e, "TP exact")
    row["entity_tp_containment"] = count(txt_e, "TP containment")
    row["entity_tp_relaxed"] = count(txt_e, "TP relaxed")
    row["entity_wrong_type"] = count(txt_e, "Wrong type")
    row["entity_fp"] = count(txt_e, "FP restants")
    row["entity_fn"] = count(txt_e, "FN restants")

    row["relation_tp_exact"] = count(txt_r, "TP exact")
    row["relation_tp_boundary"] = count(txt_r, "TP boundary")
    row["relation_tp_relaxed"] = count(txt_r, "TP relaxed")
    row["relation_wrong_type"] = count(txt_r, "Wrong relation type")
    row["relation_fp"] = count(txt_r, "FP restants")
    row["relation_fn"] = count(txt_r, "FN restants")

    rows.append(row)

# Deltas vs baseline calculated only when baseline was successfully evaluated.
baseline = next((r for r in rows if r["stage"] == "00_BASELINE_MISTRAL" and r.get("status") in ("PASS", "REFERENCE")), None)
if baseline:
    for r in rows:
        if r.get("status") not in ("PASS", "REFERENCE"):
            continue
        for kind in ("entity", "relation"):
            for met in ("precision", "recall", "f1", "macro_f1"):
                key = f"{kind}_{met}"
                a, b = r.get(key), baseline.get(key)
                r[f"delta_{key}"] = round(a - b, 6) if a is not None and b is not None else None

fields = [
    "stage","status","prediction_dir",
    "entity_precision","entity_recall","entity_f1","entity_macro_f1",
    "delta_entity_precision","delta_entity_recall","delta_entity_f1","delta_entity_macro_f1",
    "entity_tp_exact","entity_tp_containment","entity_tp_relaxed","entity_wrong_type","entity_fp","entity_fn",
    "relation_precision","relation_recall","relation_f1","relation_macro_f1",
    "delta_relation_precision","delta_relation_recall","delta_relation_f1","delta_relation_macro_f1",
    "relation_tp_exact","relation_tp_boundary","relation_tp_relaxed","relation_wrong_type","relation_fp","relation_fn",
]
csv_path = OUT / "TRACE_ablation_F1_summary.csv"
with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)

json_path = OUT / "TRACE_ablation_F1_summary.json"
json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

print("\n" + "=" * 110)
print("TABLEAU FINAL — RELAXED")
print("=" * 110)
print(f"{'ETAGE':34} | {'Ent P':>7} {'Ent R':>7} {'Ent F1':>7} {'ΔF1':>7} | {'Rel P':>7} {'Rel R':>7} {'Rel F1':>7} {'ΔF1':>7}")
print("-" * 110)
for r in rows:
    if r.get("status") not in ("PASS", "REFERENCE"):
        print(f"{r['stage'][:34]:34} | {r.get('status','?')}")
        continue
    def pct(v):
        return f"{100*v:6.2f}%" if isinstance(v, (float,int)) else "   N/A "
    print(
        f"{r['stage'][:34]:34} | "
        f"{pct(r.get('entity_precision'))} {pct(r.get('entity_recall'))} {pct(r.get('entity_f1'))} {pct(r.get('delta_entity_f1'))} | "
        f"{pct(r.get('relation_precision'))} {pct(r.get('relation_recall'))} {pct(r.get('relation_f1'))} {pct(r.get('delta_relation_f1'))}"
    )

print("\nRésultats :", OUT)
print("Résumé CSV :", csv_path)
print("Résumé JSON:", json_path)
print("\nIMPORTANT : une baisse ou hausse est rapportée telle quelle ; aucun seuil n'est optimisé sur le Gold Standard.")
