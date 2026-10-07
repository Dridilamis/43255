# -*- coding: utf-8 -*-
"""
ETAGE 8 - EVALUATION
Seule responsabilite : mesurer. C'est le SEUL etage qui lit le gold standard ; aucun autre
etage ne depend de ses resultats.

  E1  precision / rappel / F1 (RELAXED) des entites et des relations a la sortie de chaque
      etage, avec les matchers existants (Evaluation/TRACE_Ablation_F1, inchanges) ;
  E2  taux d'hallucination = 1 - precision, pour les entites et pour les relations ;
  E3  stabilite : memes mesures sur les documents pairs et impairs separement ;
  E4  metriques de structure (sans gold) : relations orphelines, violations d'ontologie,
      relations identiques, relations dont une extremite est absente du texte ;
  E5  (--entrainer-vote) entraine les deux votes des agents (entites, relations) sur la
      sortie de l'Etage 6, puis mesure le SYSTEME COMPLET en mode precision par validation
      croisee a 2 plis (documents pairs / impairs) : chaque document est traite par
      l'Etage 7 avec des modeles qui ne l'ont jamais vu. Le modele final (tous les
      documents) est ecrit dans modele/vote_agents.json.

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
import shutil

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
    ("04b_recuperation", C.STAGE_DIRS["4b"]),
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


KEEP_LEVELS = [98, 95, 90, 80, 70]     # part gardee par le mode precision (validation croisee)
THRESHOLD_LEVELS = [100, 98, 95, 90, 85, 80, 70, 60]


def _matcher(kind):
    name = "Matching_relations_ABLATION.py" if kind == "rel" else "Matching_entites_ABLATION.py"
    spec = importlib.util.spec_from_file_location(f"matcher_{kind}", C.MATCHERS_DIR / name)
    m = importlib.util.module_from_spec(spec)
    argv = sys.argv
    sys.argv = ["matcher", str(gold_dir()), str(C.STAGE_DIRS[6]), str(C.EVAL_DIR / "_matcher_tmp")]
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            spec.loader.exec_module(m)
    finally:
        sys.argv = argv
    return m


def _gold_files(m):
    return {m.normalize_document_key(p.name): p for p in gold_dir().glob("*.json")}


def _relation_samples():
    """(document, variables, juste ?) pour chaque relation de la sortie de l'Etage 6."""
    import etage7_arbitrage
    m = _matcher("rel")
    golds = _gold_files(m)
    samples = []
    for path, data in iter_documents(C.STAGE_DIRS[6]):
        key = m.normalize_document_key(path.name)
        if not is_clinical(data) or key not in golds:
            continue
        gold = m.extract_gold_relations(m.load_json(golds[key]))
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
    return samples


def _entity_samples():
    """(document, variables, juste ?) pour chaque entite de pages[] que les regles E1-E3 gardent."""
    import etage7_arbitrage
    m = _matcher("ent")
    golds = _gold_files(m)
    samples = []
    for path, data in iter_documents(C.STAGE_DIRS[6]):
        key = m.normalize_document_key(path.name)
        if not is_clinical(data) or key not in golds:
            continue
        with contextlib.redirect_stdout(io.StringIO()):
            results, _, _ = m.match_document(m.load_json(golds[key]), data)
        status = {}
        for r in results:
            if r["status"] != "FN":
                status.setdefault((r["page"], r["pred_name"], r["pred_type"]), []).append(r["status"])
        g = Graph(data)
        linked = {r.get(k) for r in g.relations for k in ("identifiant_entite_sujet", "identifiant_entite_objet")}
        seen = Counter()
        for page, e in g.page_entities():
            name, etype = m.get_entity_name(e), m.get_entity_type(e)
            if not name or not etype:
                continue
            ok = status[(page.get("page"), name, etype)].pop(0).startswith("TP")
            s = etage7_arbitrage.entity_signals(g, e, linked, seen)
            if not etage7_arbitrage.decide_entity(s, "standard")[0]:
                samples.append((key, vote.entity_features(s), ok))
    return samples


def _fit(samples, docs):
    rows = [(f, y) for d, f, y in samples if d in docs]
    weights = vote.fit([f for f, _ in rows], [y for _, y in rows])
    scores = np.array([vote.score(weights, f) for f, _ in rows])
    return {"poids": weights,
            "seuils_garder": {str(k): (float(np.quantile(scores, 1 - k / 100)) if k < 100 else 0.0)
                              for k in THRESHOLD_LEVELS}}


def _counts(df, docs):
    st = df[df["document"].isin(docs)]["status"].astype(str)
    return Counter(tp=int(st.str.startswith("TP").sum()), fp=int(st.isin(["FP", "WRONG_TYPE"]).sum()),
                   fn=int(st.isin(["FN", "WRONG_TYPE"]).sum()))


def _prf_counts(c):
    p = c["tp"] / (c["tp"] + c["fp"]) if c["tp"] + c["fp"] else 0.0
    r = c["tp"] / (c["tp"] + c["fn"]) if c["tp"] + c["fn"] else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def train_vote():
    """Entraine les deux votes et mesure le SYSTEME COMPLET (Etage 7 en mode precision) par
    validation croisee : modeles entraines sur les documents pairs, Etage 7 applique et evalue
    sur les impairs, puis l'inverse. Ecrit le modele final (tous les documents)."""
    import etage7_arbitrage
    out = C.EVAL_DIR
    out.mkdir(parents=True, exist_ok=True)
    print("Collecte des signaux et des etiquettes (gold) ...")
    rel_s, ent_s = _relation_samples(), _entity_samples()
    docs = sorted({d for d, _, _ in rel_s} | {d for d, _, _ in ent_s})
    folds = [set(docs[0::2]), set(docs[1::2])]
    tmp = out / "_cv"
    totals = {k: {"ent": Counter(), "rel": Counter()} for k in KEEP_LEVELS}
    for i, test in enumerate(folds):
        train = set(docs) - test
        models = {"relations": _fit(rel_s, train), "entites": _fit(ent_s, train)}
        for k in KEEP_LEVELS:
            print(f"  pli {i + 1}/2, garder {k} % : Etage 7 + evaluation sur {len(test)} documents non vus")
            with contextlib.redirect_stdout(io.StringIO()):
                etage7_arbitrage.main(mode="precision", out_dir=tmp / "json", keep=k, keep_ent=k, models=models)
            totals[k]["rel"].update(_counts(match("rel", tmp / "json", tmp / "rel"), test))
            totals[k]["ent"].update(_counts(match("ent", tmp / "json", tmp / "ent"), test))
    shutil.rmtree(tmp, ignore_errors=True)

    rows = []
    for k in KEEP_LEVELS:
        ep, er, ef = _prf_counts(totals[k]["ent"])
        rp, rr, rf = _prf_counts(totals[k]["rel"])
        rows.append({"garder_pct": k, "ent_P": ep, "ent_R": er, "ent_F1": ef, "ent_hallucination": 1 - ep,
                     "rel_P": rp, "rel_R": rr, "rel_F1": rf, "rel_hallucination": 1 - rp})
    with open(out / "vote_agents_validation.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), delimiter=";")
        w.writeheader()
        w.writerows(rows)

    final = {"relations": _fit(rel_s, set(docs)), "entites": _fit(ent_s, set(docs)),
             "entraine_sur": f"sortie Etage 6, {len(docs)} documents (gold)", "validation_croisee": rows}
    vote.save(final)
    _print_cv(rows)
    for kind in ("entites", "relations"):
        top = sorted(final[kind]["poids"].items(), key=lambda kv: kv[1])
        print(f"\n[{kind}] signaux qui font baisser le score :", ", ".join(f"{a} ({v:+.2f})" for a, v in top[:6]))
        print(f"[{kind}] signaux qui font monter le score  :", ", ".join(f"{a} ({v:+.2f})" for a, v in top[-4:]))
    print(f"Modele : {C.MODEL_FILE}")
    return 0


def _print_cv(rows):
    print("\nMODE PRECISION - validation croisee (chaque document traite par des modeles qui ne l'ont pas vu)")
    print(f"{'garder':>7} | {'Ent P':>7} {'Ent R':>7} {'Ent F1':>7} {'halluc':>7} | "
          f"{'Rel P':>7} {'Rel R':>7} {'Rel F1':>7} {'halluc':>7}")
    for r in rows:
        print(f"{r['garder_pct']:6}% | {r['ent_P']:7.2%} {r['ent_R']:7.2%} {r['ent_F1']:7.2%} "
              f"{r['ent_hallucination']:7.2%} | {r['rel_P']:7.2%} {r['rel_R']:7.2%} {r['rel_F1']:7.2%} "
              f"{r['rel_hallucination']:7.2%}")


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
        row = {"etage": name, "ent_P": ep, "ent_R": er, "ent_F1": ef, "ent_hallucination": 1 - ep,
               "rel_P": rp, "rel_R": rr, "rel_F1": rf, "rel_FP": rfp, "rel_hallucination": 1 - rp,
               "pairs_P": pa, "pairs_R": ra, "pairs_F1": fa, "impairs_P": pb, "impairs_R": rb, "impairs_F1": fb,
               **{f"struct_{k}": v for k, v in s.items()}}
        rows.append(row)
        print(f"[OK] {name:24} Ent P {ep:.2%} F1 {ef:.2%} | Rel P {rp:.2%} F1 {rf:.2%} "
              f"| ontologie {s['violations_ontologie']} identiques {s['identiques']}")

    with open(out / "tableau.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(rows)
    write_json(out / "tableau.json", rows)

    print("\n" + "=" * 118)
    print(f"{'ETAGE':24} | {'Ent P':>7} {'Ent R':>7} {'Ent F1':>7} {'halluc':>7} | {'Rel P':>7} {'Rel R':>7} "
          f"{'Rel F1':>7} {'halluc':>7} | {'RelF1 pairs':>11} {'impairs':>8}")
    print("-" * 118)
    for r in rows:
        print(f"{r['etage']:24} | {r['ent_P']:7.2%} {r['ent_R']:7.2%} {r['ent_F1']:7.2%} {r['ent_hallucination']:7.2%} | "
              f"{r['rel_P']:7.2%} {r['rel_R']:7.2%} {r['rel_F1']:7.2%} {r['rel_hallucination']:7.2%} | "
              f"{r['pairs_F1']:11.2%} {r['impairs_F1']:8.2%}")
    model = vote.load()
    if model and model.get("validation_croisee") and "ent_P" in model["validation_croisee"][0]:
        cv = model["validation_croisee"]
        with open(out / "vote_agents_validation.csv", "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=list(cv[0]), delimiter=";")
            w.writeheader()
            w.writerows(cv)
        _print_cv(cv)
    if any(r["etage"] == "07_arbitrage_precision" for r in rows):
        print("\nATTENTION : 07_arbitrage_precision est evalue sur les documents qui ont servi a entrainer le")
        print("vote des agents : ces chiffres sont optimistes. La mesure honnete (documents non vus) est")
        print(f"dans {out / 'vote_agents_validation.csv'} (python etage8_evaluation.py --entrainer-vote).")
    print(f"\nResultats : {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
