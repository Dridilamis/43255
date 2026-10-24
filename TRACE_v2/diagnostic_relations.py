# -*- coding: utf-8 -*-
"""
Diagnostic des relations a un etage (par defaut 01_preparation = sortie Mistral avant TRACE).
N'affiche que des comptes et des types, plus les formes des entites DONNEE_PATIENT
(ex. "patient", "77 ans") : aucune donnee identifiante.

    python TRACE_v2\\diagnostic_relations.py
    python TRACE_v2\\diagnostic_relations.py 07_arbitrage
"""
import csv
import sys
from collections import Counter
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ETAGE = sys.argv[1] if len(sys.argv) > 1 else "01_preparation"
BASE = Path(__file__).resolve().parent / "sorties_v2_0" / "08_evaluation" / ETAGE / "relations"


def lire(nom):
    with open(BASE / nom, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


par_type = lire("relation_metrics_by_type.csv")
print(f"Etage : {ETAGE}\n")
print(f"{'relation':45} {'TP':>5} {'FP':>5} {'FN':>5} {'mauvais type':>12}")
for r in sorted(par_type, key=lambda r: -(int(r["fp"]) + int(r["fn"]))):
    tp = int(r["tp_exact"]) + int(r["tp_boundary"]) + int(r["tp_relaxed"])
    print(f"{r['relation_type']:45} {tp:5} {r['fp']:>5} {r['fn']:>5} {r['wrong_type_as_pred']:>12}")

detail = lire("relation_matches_detailed.csv")
print("\nStatuts :", dict(Counter(r["status"] for r in detail)))
fp = [r for r in detail if r["status"] == "FP"]
fn = [r for r in detail if r["status"] == "FN"]
print("\nFP : couples de types predits (sujet -> objet) les plus frequents")
for k, n in Counter((r["pred_relation"], r["pred_subject_type"], r["pred_object_type"]) for r in fp).most_common(12):
    print(f"  {n:5}  {k[0]} | {k[1]} -> {k[2]}")
print("\nForme de l'entite patient dans les relations predites (FP) / attendues (FN) :")
pat_pred = Counter(r["pred_object"].lower()[:20] for r in fp if r["pred_object_type"] == "DONNEE_PATIENT")
pat_pred += Counter(r["pred_subject"].lower()[:20] for r in fp if r["pred_subject_type"] == "DONNEE_PATIENT")
pat_gold = Counter(r["gold_object"].lower()[:20] for r in fn if r["gold_object_type"] == "DONNEE_PATIENT")
pat_gold += Counter(r["gold_subject"].lower()[:20] for r in fn if r["gold_subject_type"] == "DONNEE_PATIENT")
print("  predit :", pat_pred.most_common(10))
print("  attendu:", pat_gold.most_common(10))
