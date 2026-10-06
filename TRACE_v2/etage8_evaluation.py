# -*- coding: utf-8 -*-
"""
ETAGE 8 - EVALUATION
Seule responsabilite : mesurer. C'est le SEUL etage qui lit le gold standard ; aucun autre
etage ne depend de ses resultats.

  E1  precision / rappel / F1 (RELAXED) des entites et des relations a la sortie de chaque
      etage, avec les matchers existants (Evaluation/TRACE_Ablation_F1, inchanges) ;
  E2  taux d'hallucination = 1 - precision des relations ;
  E3  stabilite : memes mesures sur les documents pairs et impairs separement ;
  E4  metriques de structure (sans gold) : relations orphelines, violations d'ontologie,
      relations identiques, relations dont une extremite est absente du texte ;
  E5  (--entrainer-vote) entraine le vote des agents de l'Etage 7 sur la sortie de
      l'Etage 6 et mesure son compromis precision/rappel par validation croisee a 2 plis
      (documents pairs / impairs) : chaque document est note par un modele qui ne l'a
      jamais vu. Le modele final (tous les documents) est ecrit dans modele/vote_agents.json.

Usage :
    python etage8_evaluation.py                   # E1-E4
    python etage8_evaluation.py --entrainer-vote  # E5, puis relancer l'Etage 7 en mode precision

Sorties : sorties/08_evaluation/{tableau.csv, tableau.json, vote_agents_validation.csv, <etage>/...}
"""
import csv
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import contextlib
import importlib.util
import io

import numpy as np
import pandas as pd

from trace_lib import config as C
from trace_lib import ontologie, vote
from trace_lib.documents import Graph, is_clinical, iter_documents, write_json
from trace_lib.texte import load_source

STAGES = [
    ("01_preparation", C.STAGE_DIRS[1]),
    ("02_ancrage", C.STAGE_DIRS[2]),
    ("03_ontologie", C.STAGE_DIRS[3]),
    ("04_sgce", C.STAGE_DIRS[4]),
    ("05_dedoublonnage", C.STAGE_DIRS[5]),
    ("06_attributs", C.STAGE_DIRS[6]),
    ("07_arbitrage", C.STAGE_DIRS[7]),
    ("07_arbitrage_precision", C.OUT / "07_arbitrage_precision"),
]


def gold_dir():
    for p in C.GOLD_DIR_CANDIDATES:
        if p.is_dir():
            return p
    raise SystemExit("gold introuvable : " + ", ".join(map(str, C.GOLD_DIR_CANDIDATES)))


def match(kind, pred, out):
    script = C.MATCHERS_DIR / ("Matching_relations_ABLATION.py" if kind == "rel" else "Matching_entites_ABLATION.py")
    subprocess.run([sys.executable, str(script), str(gold_dir()), str(pred), str(out)],
                   capture_output=True, check=True)
    csv_name = "relation_matches_detailed.csv" if kind == "rel" else "entity_matches_detailed.csv"
    return pd.read_csv(Path(out) / csv_name)


def prf(df, docs=None):
    if docs is not None:
        df = df[df["document"].isin(docs)]
    st = df["status"].astype(str)
    tp = st.str.startswith("TP").sum()
    fp = st.isin(["FP", "WRONG_TYPE"]).sum()
    fn = st.isin(["FN", "WRONG_TYPE"]).sum()
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0), int(fp)


def structure(stage_dir):
    c = Counter()
    for path, data in iter_documents(stage_dir):
        if not is_clinical(data):
            continue
        g, doc = Graph(data), load_source(data, path)
        seen = set()
        for rel in g.relations:
            c["relations"] += 1
            se, sn = g.endpoint(rel, "subject")
            oe, on = g.endpoint(rel, "object")
            if se is None or oe is None:
                c["orphelines"] += 1
            if ontologie.check(str(rel.get("type_relation")), g.entity_type(se), g.entity_type(oe)) != "CONFORME":
                c["violations_ontologie"] += 1
            key = (rel.get("identifiant_entite_sujet"), rel.get("type_relation"), rel.get("identifiant_entite_objet"))
            c["identiques"] += key in seen
            seen.add(key)
            if not ((g.is_patient(se, sn) or doc.attests(sn)) and (g.is_patient(oe, on) or doc.attests(on))):
                c["extremite_absente_du_texte"] += 1
    return c


KEEP_LEVELS = [100, 90, 80, 70, 60]


def _matcher_module():
    spec = importlib.util.spec_from_file_location("matcher", C.MATCHERS_DIR / "Matching_relations_ABLATION.py")
    m = importlib.util.module_from_spec(spec)
    argv = sys.argv
    sys.argv = ["matcher", str(gold_dir()), str(C.STAGE_DIRS[6]), str(C.EVAL_DIR / "_matcher_tmp")]
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            spec.loader.exec_module(m)
    finally:
        sys.argv = argv
    return m


def _labelled_signals():
    """(document, features, label) pour chaque relation de la sortie de l'Etage 6, et le
    nombre de relations gold par document."""
    import etage7_arbitrage
    m = _matcher_module()
    gold_idx = m.index_json_folder(str(gold_dir()))
    samples, n_gold = [], {}
    for path, data in iter_documents(C.STAGE_DIRS[6]):
        key = m.normalize_document_key(path.name)
        if not is_clinical(data) or key not in gold_idx:
            continue
        gold = m.extract_gold_relations(m.load_json(gold_idx[key]))
        n_gold[key] = len(gold)
        preds = m.extract_pred_relations(data)
        status = {}
        for r in m.evaluate_document(key, gold, preds):
            if r["status"] != "FN":
                status.setdefault((r["pred_subject"], r["pred_relation"], r["pred_object"]), []).append(r["status"])
        label = {p["index"]: status[(p["subject"], p["relation"], p["object"])].pop(0).startswith("TP") for p in preds}
        g, doc = Graph(data), load_source(data, path)
        for i, rel in enumerate(g.relations):
            if i in label:
                s = etage7_arbitrage.signals(g, doc, rel)
                samples.append((key, vote.features(s, str(rel.get("type_relation") or "")), label[i]))
    return samples, n_gold


def train_vote():
    out = C.EVAL_DIR
    out.mkdir(parents=True, exist_ok=True)
    samples, n_gold = _labelled_signals()
    docs = sorted(n_gold)
    folds = [set(docs[0::2]), set(docs[1::2])]
    totals = {k: Counter() for k in KEEP_LEVELS}
    for test in folds:
        train = [s for s in samples if s[0] not in test]
        held = [s for s in samples if s[0] in test]
        w = vote.fit([f for _, f, _ in train], [y for _, _, y in train])
        tr_scores = np.array([vote.score(w, f) for _, f, _ in train])
        te_scores = np.array([vote.score(w, f) for _, f, _ in held])
        y_te = np.array([y for _, _, y in held])
        for k in KEEP_LEVELS:
            thr = np.quantile(tr_scores, 1 - k / 100) if k < 100 else -1
            keep = te_scores >= thr
            totals[k]["tp"] += int(y_te[keep].sum())
            totals[k]["kept"] += int(keep.sum())
            totals[k]["gold"] += sum(n_gold[d] for d in test)
    rows = []
    for k in KEEP_LEVELS:
        t = totals[k]
        p, r = t["tp"] / t["kept"], t["tp"] / t["gold"]
        rows.append({"garder_pct": k, "relations": t["kept"], "precision": p, "rappel": r,
                     "f1": 2 * p * r / (p + r), "taux_hallucination": 1 - p})
    with open(out / "vote_agents_validation.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), delimiter=";")
        w.writeheader()
        w.writerows(rows)

    weights = vote.fit([f for _, f, _ in samples], [y for _, _, y in samples])
    scores = np.array([vote.score(weights, f) for _, f, _ in samples])
    vote.save({"poids": weights, "entraine_sur": "sortie Etage 6, 43 documents (gold)",
               "seuils_garder": {str(k): (float(np.quantile(scores, 1 - k / 100)) if k < 100 else 0.0)
                                 for k in KEEP_LEVELS},
               "validation_croisee": rows})

    print("VOTE DES AGENTS - validation croisee (chaque document note par un modele qui ne l'a pas vu)")
    print(f"{'garder':>7} {'relations':>10} {'precision':>10} {'rappel':>8} {'F1':>8} {'halluc.':>8}")
    for r in rows:
        print(f"{r['garder_pct']:6}% {r['relations']:10} {r['precision']:10.2%} {r['rappel']:8.2%} "
              f"{r['f1']:8.2%} {r['taux_hallucination']:8.2%}")
    top = sorted(weights.items(), key=lambda kv: kv[1])
    print("\nSignaux qui font le plus baisser le score :", ", ".join(f"{k} ({v:+.2f})" for k, v in top[:8]))
    print("Signaux qui font le plus monter le score  :", ", ".join(f"{k} ({v:+.2f})" for k, v in top[-6:]))
    print(f"Modele : {C.MODEL_FILE}")
    return 0


def main():
    if "--entrainer-vote" in sys.argv:
        return train_vote()
    out = C.EVAL_DIR
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, d in STAGES:
        if not Path(d).is_dir():
            print(f"[--] {name} : absent, ignore")
            continue
        rel = match("rel", d, out / name / "relations")
        ent = match("ent", d, out / name / "entites")
        docs = sorted(rel["document"].unique())
        rp, rr, rf, rfp = prf(rel)
        ep, er, ef, _ = prf(ent)
        pa, ra, fa, _ = prf(rel, docs[0::2])
        pb, rb, fb, _ = prf(rel, docs[1::2])
        s = structure(d)
        row = {"etage": name, "ent_P": ep, "ent_R": er, "ent_F1": ef,
               "rel_P": rp, "rel_R": rr, "rel_F1": rf, "rel_FP": rfp, "taux_hallucination": 1 - rp,
               "pairs_P": pa, "pairs_R": ra, "pairs_F1": fa, "impairs_P": pb, "impairs_R": rb, "impairs_F1": fb,
               **{f"struct_{k}": v for k, v in s.items()}}
        rows.append(row)
        print(f"[OK] {name:24} Ent F1 {ef:.2%} | Rel P {rp:.2%} R {rr:.2%} F1 {rf:.2%} "
              f"| halluc. {1 - rp:.2%} | ontologie {s['violations_ontologie']} identiques {s['identiques']}")

    with open(out / "tableau.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(rows)
    write_json(out / "tableau.json", rows)

    print("\n" + "=" * 118)
    print(f"{'ETAGE':24} | {'Ent P':>7} {'Ent R':>7} {'Ent F1':>7} | {'Rel P':>7} {'Rel R':>7} {'Rel F1':>7} "
          f"{'FP':>5} {'Halluc':>7} | {'F1 pairs':>8} {'F1 impairs':>10}")
    print("-" * 118)
    for r in rows:
        print(f"{r['etage']:24} | {r['ent_P']:7.2%} {r['ent_R']:7.2%} {r['ent_F1']:7.2%} | {r['rel_P']:7.2%} "
              f"{r['rel_R']:7.2%} {r['rel_F1']:7.2%} {r['rel_FP']:5} {r['taux_hallucination']:7.2%} | "
              f"{r['pairs_F1']:8.2%} {r['impairs_F1']:10.2%}")
    model = vote.load()
    if model and model.get("validation_croisee"):
        cv = model["validation_croisee"]
        with open(out / "vote_agents_validation.csv", "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=list(cv[0]), delimiter=";")
            w.writeheader()
            w.writerows(cv)
        print("\nVote des agents, validation croisee (documents non vus) :")
        for r in cv:
            print(f"  garder {r['garder_pct']:3}% : P {r['precision']:.2%}  R {r['rappel']:.2%}  "
                  f"F1 {r['f1']:.2%}  hallucinations {r['taux_hallucination']:.2%}")
    if any(r["etage"] == "07_arbitrage_precision" for r in rows):
        print("\nATTENTION : 07_arbitrage_precision est evalue sur les documents qui ont servi a entrainer le")
        print("vote des agents : ces chiffres sont optimistes. La mesure honnete (documents non vus) est")
        print(f"dans {out / 'vote_agents_validation.csv'} (python etage8_evaluation.py --entrainer-vote).")
    print(f"\nResultats : {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
