# -*- coding: utf-8 -*-
"""
TRACE - REGLES STRICTES APPRISES SUR LE GOLD, EN VALIDATION CROISEE (post-traitement de l'extraction)

Les dossiers sont separes en deux moities (dossiers tries, rangs pairs / impairs : memes plis que
l'etage 8). Pour chaque moitie, les regles sont APPRISES sur l'autre moitie (extraction comparee a
son gold) puis APPLIQUEES a celle-ci. Aucun dossier n'est filtre avec des regles apprises sur son
propre gold.

Regles apprises (seuil fixe a priori : precision < SEUIL sur l'autre moitie => retrait) :
  - entites : precision par "profil" = type x mention niee x presence d'un chiffre x mention longue
    (>= 6 mots). Ex. EVENEMENT_TEMPOREL sans date. Les mentions NIEES ("pas de sueurs") ne sont
    jamais retirees : l'absence d'un signe est une information clinique ;
  - relations : precision par type de relation (les relations d'interpretation rarement justes).
Une entite retiree emporte ses relations.

Usage (depuis Reduction_hallucinations) :
    python extraction_mistral\\regles_apprises.py extraction_mistral\\extraction_v2_0 gold_v2_0 extraction_mistral\\extraction_v2_0_regles
"""
import csv
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SEUIL = 0.20
PROJECT = Path(__file__).resolve().parent.parent
MATCHERS = PROJECT / "Evaluation" / "TRACE_Ablation_F1"
NEG_RE = re.compile(r"^\s*(pas d|absence|sans |ni |non |aucun)", re.IGNORECASE)


def cle_doc(path):
    return Path(path).name.split("_trace_")[0].replace(".json", "")


def norm(s):
    s = unicodedata.normalize("NFD", str(s or "").lower())
    return re.sub(r"\s+", " ", "".join(c for c in s if unicodedata.category(c) != "Mn")).strip()


def profil(e):
    n = str(e.get("name") or "")
    return (e.get("categorie") or e.get("type"), bool(NEG_RE.match(n)), bool(re.search(r"\d", n)),
            len(n.split()) >= 6)


def evaluer(pred_files, gold_files):
    """Lance les deux matchers de TRACE sur un sous-ensemble ; renvoie leurs tableaux detailles."""
    tmp = Path(tempfile.mkdtemp(prefix="regles_"))
    try:
        for sous, fichiers in (("pred", pred_files), ("gold", gold_files)):
            (tmp / sous).mkdir()
            for f in fichiers:
                shutil.copy2(f, tmp / sous / Path(f).name)
        out = {}
        for nom, script, csv_name in (("ent", "Matching_entites_ABLATION.py", "entity_matches_detailed.csv"),
                                      ("rel", "Matching_relations_ABLATION.py", "relation_matches_detailed.csv")):
            subprocess.run([sys.executable, str(MATCHERS / script), str(tmp / "gold"), str(tmp / "pred"),
                            str(tmp / nom)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           env={**__import__("os").environ, "PYTHONUTF8": "1"}, check=True)
            with open(tmp / nom / csv_name, encoding="utf-8-sig", newline="") as fh:
                out[nom] = list(csv.DictReader(fh))
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def apprendre(pred_files, gold_files):
    det = evaluer(pred_files, gold_files)
    # etiquette de chaque entite predite (document, page, type, nom) -> juste ou non
    lab = defaultdict(list)
    for r in det["ent"]:
        if r["pred_name"]:
            lab[(r["document"], str(r["page"]), r["pred_type"], norm(r["pred_name"]))].append(
                1 if r["status"].startswith("TP") else 0)
    prof = defaultdict(lambda: [0, 0])
    for f in pred_files:
        data = json.loads(Path(f).read_text(encoding="utf-8"))
        doc = cle_doc(f)
        for p in data.get("pages", []):
            for e in p.get("entities", []):
                labs = lab.get((doc, str(p.get("page")), e.get("categorie"), norm(e.get("name"))))
                if labs:
                    y = labs.pop(0)
                    prof[profil(e)][y] += 1
    rel = defaultdict(lambda: [0, 0])
    for r in det["rel"]:
        if r["status"].startswith("TP"):
            rel[r["gold_relation"]][1] += 1
        elif r["status"] in ("FP", "WRONG_TYPE"):
            rel[r["pred_relation"]][0] += 1
    # une mention niee ("pas de sueurs") n'est jamais retiree : l'absence est une information clinique
    mauvais_profils = {k for k, (f, t) in prof.items() if f + t >= 5 and t / (f + t) < SEUIL and not k[1]}
    mauvaises_relations = {k for k, (f, t) in rel.items() if f + t >= 5 and t / (f + t) < SEUIL}
    return mauvais_profils, mauvaises_relations


def appliquer(data, mauvais_profils, mauvaises_relations, c):
    for p in data.get("pages", []):
        retirees = {e["identifiant_entite"] for e in p.get("entities", []) if profil(e) in mauvais_profils}
        c["entites_retirees"] += len(retirees)
        p["entities"] = [e for e in p.get("entities", []) if e["identifiant_entite"] not in retirees]
        garder = []
        for r in p.get("relations", []):
            if r.get("identifiant_entite_sujet") in retirees or r.get("identifiant_entite_objet") in retirees:
                c["relations_retirees_avec_entite"] += 1
            elif r.get("type_relation") in mauvaises_relations:
                c["relations_retirees_type"] += 1
            else:
                garder.append(r)
        p["relations"] = garder
    data["global_entities"] = [e for p in data.get("pages", []) for e in p.get("entities", [])]
    data["global_relations"] = [r for p in data.get("pages", []) for r in p.get("relations", [])]
    return data


def main():
    dev = "--developpement" in sys.argv
    argv = [a for a in sys.argv[1:] if a != "--developpement"]
    if len(argv) != 3:
        sys.exit(__doc__)
    src, gold, out = map(Path, argv)
    out.mkdir(parents=True, exist_ok=True)
    preds = {cle_doc(f): f for f in src.glob("*_trace_*.json")}
    golds = {cle_doc(f): f for f in gold.glob("*.json")}
    docs = sorted(set(preds) & set(golds))
    # validation croisee (defaut) : chaque moitie corrigee avec ce qui est appris sur l'autre.
    # --developpement : appris sur TOUS les dossiers puis applique a ces memes dossiers (comme
    # l'ancienne chaine V1.6) ; resultats a presenter comme "corpus de developpement" (optimistes).
    plis = [docs, docs] if dev else [docs[0::2], docs[1::2]]
    if dev:
        print("MODE DEVELOPPEMENT : regles apprises sur tous les dossiers evalues (resultats optimistes)")
    c = Counter()
    rapport = {}
    for k in ((0,) if dev else (0, 1)):
        autres = plis[1 - k]
        mp, mr = apprendre([preds[d] for d in autres], [golds[d] for d in autres])
        rapport[f"pli_{k + 1}"] = {"profils_entites_retires": sorted(map(str, mp)),
                                    "relations_retirees": sorted(mr)}
        print(f"Pli {k + 1} : regles apprises sur {len(autres)} dossiers -> {len(mp)} profils d'entites, "
              f"{len(mr)} types de relations retires")
        for d in plis[k]:
            data = json.loads(Path(preds[d]).read_text(encoding="utf-8"))
            (out / Path(preds[d]).name).write_text(json.dumps(appliquer(data, mp, mr, c), ensure_ascii=False,
                                                              indent=1), encoding="utf-8")
    (out / "_regles_apprises.json").write_text(json.dumps(rapport, ensure_ascii=False, indent=1), encoding="utf-8")
    textes = src / "textes_bruts"
    if textes.is_dir():
        shutil.copytree(textes, out / "textes_bruts", dirs_exist_ok=True)
    print(dict(c))
    print(f"Sortie : {out}")


if __name__ == "__main__":
    main()
