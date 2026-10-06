# -*- coding: utf-8 -*-
"""
confidence_vs_gold.py

Mesure, contre le Gold, la precision de chaque niveau de confiance de l'Etage 8
(HIGH / MEDIUM / REVIEW / LOW) sur les RELATIONS, puis simule ce qui se passerait si l'on
ne gardait que les relations les plus fiables (courbe risque-couverture).

SEPARE aussi les relations ajoutees par un post-traitement GUIDE PAR LE GOLD (champs
"*_gold_guided", type_inference "dev_*", versions V6.9b-k) du reste, car elles gonflent la
precision (~93-97 %) et fausseraient toute lecture par niveau de confiance.

Ne modifie AUCUN fichier clinique. Reutilise le matcher existant
(Matching_relations_APRES_TRACE.py) : memes regles d'appariement que ton evaluation.

Usage (depuis le dossier Reduction_hallucinations) :
    python confidence_vs_gold.py
Options :
    --gold DIR      dossier gold          (defaut : <OCR vers LLM>\\gold_canonical_par_documentF)
    --pred DIR      sortie de l'Etage 8   (defaut : confidence Etage 8\\confidence_assessed_safe)
    --out  DIR      dossier de resultats  (defaut : evaluation_confidence_vs_gold)
    --matcher FILE  matcher a reutiliser  (defaut : confidence Etage 8\\evaluation apres H\\
                                           Matching_relations_APRES_TRACE.py)

Controle : la ligne "TOUTES" doit etre proche de la ligne 08_CONFIDENCE de ton ablation
(P 74,12 % / R 63,50 % / F1 68,40 %). Si l'ecart est visible, relance avec --matcher vers
Evaluation\\evaluation_apres_TRACE\\Matching_relations_CANONICAL.py.
"""
import argparse
import csv
import importlib.util
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEVELS = ["HIGH", "MEDIUM", "REVIEW", "LOW", "SANS_NIVEAU"]
ORIGINS = ["EXTRACTION_DIRECTE", "INFERENCE_STRUCTURELLE", "V75_RECALL", "GUIDEE_GOLD", "AUTRE"]


def find_project():
    for p in [HERE, *HERE.parents]:
        if (p / "confidence Etage 8").is_dir():
            return p
    return None


def parse_args(project):
    base = project.parent
    ap = argparse.ArgumentParser(description="Precision par niveau de confiance contre le gold")
    ap.add_argument("--gold", default=str(base / "gold_canonical_par_documentF"))
    ap.add_argument("--pred", default=str(project / "confidence Etage 8" / "confidence_assessed_safe"))
    ap.add_argument("--out", default=str(project / "evaluation_confidence_vs_gold"))
    ap.add_argument("--matcher", default=str(project / "confidence Etage 8" / "evaluation apres H"
                                              / "Matching_relations_APRES_TRACE.py"))
    return ap.parse_args()


def load_matcher(path, gold, pred, out):
    spec = importlib.util.spec_from_file_location("trace_matcher", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["trace_matcher"] = module
    saved = sys.argv[:]
    sys.argv = [path, gold, pred, out]          # le matcher lit ses dossiers dans argv
    try:
        spec.loader.exec_module(module)
    finally:
        sys.argv = saved
    return module


def relations_of(pred_data):
    """Meme liste (et meme ordre) que extract_pred_relations du matcher."""
    rels = pred_data.get("global_relations", [])
    if not isinstance(rels, list) or not rels:
        rels = []
        for page in pred_data.get("pages", []):
            if not isinstance(page, dict):
                continue
            for r in page.get("relations", []):
                if isinstance(r, dict):
                    rels.append(r)
    return rels


def level_of(rel):
    if not isinstance(rel, dict):
        return "SANS_NIVEAU"
    tc = rel.get("trace_confidence")
    lvl = tc.get("level") if isinstance(tc, dict) else None
    return lvl if lvl in LEVELS else "SANS_NIVEAU"


GUIDED_KEY = re.compile(r"^_v69[b-k]_|gold", re.IGNORECASE)


def origin_of(rel):
    """Provenance d'une relation, d'apres les champs ecrits par le post-traitement."""
    if not isinstance(rel, dict):
        return "AUTRE"
    ti = str(rel.get("type_inference") or "")
    if ti.startswith("dev_") or "gold_guided" in ti or "error_guided" in ti or ti == "recall_controlled_v69b":
        return "GUIDEE_GOLD"
    for k, v in rel.items():
        if v and GUIDED_KEY.search(str(k)) and k != "trace_confidence":
            return "GUIDEE_GOLD"
    if ti.startswith("inference_structurelle"):
        return "INFERENCE_STRUCTURELLE"
    if ti.startswith("v75_"):
        return "V75_RECALL"
    if ti == "extraction_directe":
        return "EXTRACTION_DIRECTE"
    return "AUTRE"


def prf(tp, n_pred, n_gold):
    p = tp / n_pred if n_pred else 0.0
    r = tp / n_gold if n_gold else 0.0
    f = 2 * p * r / (p + r) if (p + r) else 0.0
    return p, r, f


def main():
    project = find_project()
    if project is None:
        print("ERREUR : dossier 'confidence Etage 8' introuvable au-dessus de ce script.")
        return 2
    args = parse_args(project)
    for label, path in (("gold", args.gold), ("pred", args.pred), ("matcher", args.matcher)):
        if not Path(path).exists():
            print(f"ERREUR : {label} introuvable : {path}")
            print("Utilise --gold / --pred / --matcher pour indiquer le bon chemin.")
            return 2
    Path(args.out).mkdir(parents=True, exist_ok=True)

    print("Chargement du matcher ...")
    m = load_matcher(args.matcher, args.gold, args.pred, args.out)

    original_make_row = m.make_row

    def make_row(document, status, gold=None, pred=None, score=None):
        row = original_make_row(document, status, gold=gold, pred=pred, score=score)
        row["pred_index"] = pred.get("index") if pred else None
        return row

    m.make_row = make_row

    gold_files = m.index_json_folder(args.gold)
    pred_files = m.index_json_folder(args.pred)
    docs = sorted(set(gold_files) & set(pred_files))
    print(f"Documents appaires : {len(docs)}")
    if not docs:
        print("ERREUR : aucun document commun entre gold et predictions.")
        return 2

    records, n_gold = [], 0
    for doc in docs:
        gold_data = m.load_json(gold_files[doc])
        pred_data = m.load_json(pred_files[doc])
        gold_rel = m.extract_gold_relations(gold_data)
        pred_rel = m.extract_pred_relations(pred_data)
        n_gold += len(gold_rel)
        rels = relations_of(pred_data)
        levels = {i: level_of(r) for i, r in enumerate(rels)}
        origins = {i: origin_of(r) for i, r in enumerate(rels)}
        for row in m.evaluate_document(doc, gold_rel, pred_rel):
            idx = row.get("pred_index")
            if idx is None:
                continue                      # FN : pas de prediction
            status = row["status"]
            records.append({
                "document": doc,
                "pred_index": idx,
                "niveau": levels.get(idx, "SANS_NIVEAU"),
                "origine": origins.get(idx, "AUTRE"),
                "status": status,
                "correct": 1 if status.startswith("TP") else 0,
                "relation": row.get("pred_relation"),
                "sujet": row.get("pred_subject"),
                "objet": row.get("pred_object"),
            })

    W = 100

    def table_levels(recs, title):
        by = defaultdict(lambda: [0, 0])
        for x in recs:
            by[x["niveau"]][0] += 1
            by[x["niveau"]][1] += x["correct"]
        n_all = len(recs)
        print(f"{title}")
        print(f"{'NIVEAU':<14}{'relations':>11}{'% du total':>12}{'vrais positifs':>16}{'precision':>12}")
        for lvl in LEVELS:
            if lvl in by:
                n, tp = by[lvl]
                print(f"{lvl:<14}{n:>11}{100 * n / n_all:>11.1f}%{tp:>16}{100 * tp / n:>11.1f}%")
        tp_all_ = sum(x["correct"] for x in recs)
        print(f"{'TOUTES':<14}{n_all:>11}{100.0:>11.1f}%{tp_all_:>16}{100 * tp_all_ / n_all:>11.1f}%")
        return by

    def simulate(recs, scenarios, title):
        base_tp = sum(x["correct"] for x in recs)
        _, _, base_f = prf(base_tp, len(recs), n_gold)
        print(f"\n{title}")
        print(f"{'Scenario':<40}{'gardees':>9}{'couv.':>8}{'precision':>11}{'rappel':>9}{'F1':>8}{'delta F1':>10}")
        print("-" * W)
        out_rows = []
        for name, keep in scenarios:
            kept = [x for x in recs if keep(x)]
            if not kept:
                continue
            tp = sum(x["correct"] for x in kept)
            sp, sr, sf = prf(tp, len(kept), n_gold)
            out_rows.append([title[:12], name, len(kept), len(kept) / len(recs), sp, sr, sf, sf - base_f])
            print(f"{name:<40}{len(kept):>9}{100 * len(kept) / len(recs):>7.0f}%{100 * sp:>10.2f}%"
                  f"{100 * sr:>8.2f}%{100 * sf:>7.2f}%{100 * (sf - base_f):>+9.2f}")
        return out_rows

    n_pred = len(records)
    tp_all = sum(x["correct"] for x in records)
    p, r, f = prf(tp_all, n_pred, n_gold)
    honest = [x for x in records if x["origine"] != "GUIDEE_GOLD"]
    hp, hr, hf = prf(sum(x["correct"] for x in honest), len(honest), n_gold)

    print("\n" + "=" * W)
    print("1. D'OU VIENNENT LES RELATIONS (provenance ecrite par le post-traitement)")
    print("=" * W)
    print(f"Relations gold : {n_gold} | relations predites : {n_pred} | vrais positifs : {tp_all}")
    print(f"{'ORIGINE':<26}{'relations':>11}{'% du total':>12}{'vrais positifs':>16}{'precision':>12}")
    by_origin = defaultdict(lambda: [0, 0])
    for x in records:
        by_origin[x["origine"]][0] += 1
        by_origin[x["origine"]][1] += x["correct"]
    for o in ORIGINS:
        if o in by_origin:
            n, tp = by_origin[o]
            print(f"{o:<26}{n:>11}{100 * n / n_pred:>11.1f}%{tp:>16}{100 * tp / n:>11.1f}%")
    print("-" * W)
    print(f"AVEC toutes les relations     : P={100 * p:.2f}%  R={100 * r:.2f}%  F1={100 * f:.2f}%"
          "   (controle : doit etre proche de ton ablation, ligne 08)")
    print(f"SANS les relations GUIDEE_GOLD : P={100 * hp:.2f}%  R={100 * hr:.2f}%  F1={100 * hf:.2f}%"
          f"   (ecart F1 : {100 * (hf - f):+.2f} pts)")
    print("Les relations GUIDEE_GOLD ont ete ajoutees par un post-traitement qui a consulte le gold :")
    print("elles ne mesurent pas la qualite de l'extraction sur des documents nouveaux.")

    print("\n" + "=" * W)
    print("2. PRECISION PAR NIVEAU DE CONFIANCE (Etage 8)")
    print("=" * W)
    table_levels(records, "Population complete :")
    print()
    by_h = table_levels(honest, "Hors relations GUIDEE_GOLD (population honnete) :")

    print("\n" + "=" * W)
    print("3. SIMULATION : que se passe-t-il si l'on retire des relations ?")
    print("=" * W)
    lv = lambda *k: (lambda x: x["niveau"] in k)
    sc_levels = [
        ("Garder tout (reference)", lambda x: True),
        ("Retirer LOW", lambda x: x["niveau"] != "LOW"),
        ("Retirer LOW + REVIEW", lambda x: x["niveau"] not in ("LOW", "REVIEW")),
        ("Garder HIGH + MEDIUM", lv("HIGH", "MEDIUM")),
        ("Garder HIGH seul", lv("HIGH")),
        ("Retirer INFERENCE_STRUCTURELLE", lambda x: x["origine"] != "INFERENCE_STRUCTURELLE"),
        ("Retirer LOW+REVIEW+INFER.STRUCT.",
         lambda x: x["niveau"] not in ("LOW", "REVIEW") and x["origine"] != "INFERENCE_STRUCTURELLE"),
    ]
    sim_a = simulate(records, sc_levels, "Population complete")
    sim_b = simulate(honest, sc_levels, "Population honnete (hors GUIDEE_GOLD)")
    print("=" * W)
    print("Lecture : retirer un groupe ameliore la PRECISION s'il est moins precis que l'ensemble, et le F1")
    print("seulement s'il est sous F1/2. Sinon on perd plus de bonnes relations que de fausses.")
    print(f"Seuils population honnete : precision {100 * hp:.1f} %, F1/2 = {100 * hf / 2:.1f} %.")

    by_level = by_h
    sim_rows = sim_a + sim_b

    out = Path(args.out)
    with open(out / "precision_par_origine_et_niveau.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["origine", "niveau", "relations", "vrais_positifs", "precision"])
        agg = defaultdict(lambda: [0, 0])
        for x in records:
            agg[(x["origine"], x["niveau"])][0] += 1
            agg[(x["origine"], x["niveau"])][1] += x["correct"]
        for (o, l), (n, tp) in sorted(agg.items()):
            w.writerow([o, l, n, tp, f"{tp / n:.4f}"])
    with open(out / "simulation_risque_couverture.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["population", "scenario", "gardees", "couverture", "precision", "rappel", "f1", "delta_f1"])
        for row in sim_rows:
            w.writerow(row[:3] + [f"{v:.4f}" for v in row[3:]])
    with open(out / "relations_confiance_vs_gold.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(records[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(records)
    print(f"\nResultats : {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())