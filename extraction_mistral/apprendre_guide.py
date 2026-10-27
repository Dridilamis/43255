# -*- coding: utf-8 -*-
"""
TRACE - GUIDE D'EXTRACTION APPRIS SUR LE GOLD, EN VALIDATION CROISEE

Avant de relancer l'extraction, on apprend, pour chaque moitie du corpus, des regles qui GUIDENT
Mistral (elles sont ecrites dans ses consignes) et que la validation applique ensuite strictement.
Elles sont apprises sur l'AUTRE moitie (extraction precedente comparee a son gold, plus le gold
lui-meme), avec les memes plis que l'etage 8 : aucun dossier n'est guide par son propre gold.

Le guide contient, par moitie :
  - relations_interdites : types de relation rarement justes (precision < 30 %) ;
  - profils_interdits : profils d'entites presque toujours faux (type x chiffre x mention longue ;
    jamais une mention niee : l'absence d'un signe est une information clinique) ;
  - precision_types : precision de chaque type d'entite (types a extraire avec prudence) ;
  - longueur_mots_gold : longueur mediane (en mots) des mentions annotees, par type.
Il ne contient aucun texte de dossier.

    python extraction_mistral\\apprendre_guide.py ANCIENNE_EXTRACTION gold_v2_0 extraction_mistral\\guide_appris.json
"""
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import regles_apprises as RA  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def precision_types(pred_files, gold_files):
    det = RA.evaluer(pred_files, gold_files)
    c = defaultdict(lambda: [0, 0])
    for r in det["ent"]:
        if r["pred_name"]:
            c[r["pred_type"]][1 if r["status"].startswith("TP") else 0] += 1
    return {t: round(v[1] / (v[0] + v[1]), 3) for t, v in c.items() if sum(v) >= 5}


def longueurs(gold_files):
    L = defaultdict(list)
    for f in gold_files:
        for p in json.loads(Path(f).read_text(encoding="utf-8"))["pages"]:
            for e in p["entities"]:
                if not RA.NEG_RE.match(e["name"]):
                    L[e["type"]].append(len(e["name"].split()))
    return {t: statistics.median(v) for t, v in L.items()}


SEUIL_GUIDE = 0.30   # regles strictes : precision < 30 % sur l'autre moitie => interdit


def main():
    RA.SEUIL = SEUIL_GUIDE
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    src, gold, out = map(Path, sys.argv[1:])
    preds = {RA.cle_doc(f): f for f in src.glob("*_trace_*.json")}
    golds = {RA.cle_doc(f): f for f in gold.glob("*.json")}
    docs = sorted(set(preds) & set(golds))
    plis = [docs[0::2], docs[1::2]]
    guide = {"seuil": RA.SEUIL, "plis": []}
    for k in (0, 1):
        autres = plis[1 - k]
        pf, gf = [preds[d] for d in autres], [golds[d] for d in autres]
        mp, mr = RA.apprendre(pf, gf)
        guide["plis"].append({
            "documents": plis[k], "appris_sur": autres,
            "relations_interdites": sorted(mr),
            "profils_interdits": sorted([list(p) for p in mp]),
            "precision_types": precision_types(pf, gf),
            "longueur_mots_gold": longueurs(gf),
        })
        print(f"Pli {k + 1} : {len(mr)} relations interdites, {len(mp)} profils d'entites interdits "
              f"(appris sur {len(autres)} dossiers)")
    out.write_text(json.dumps(guide, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Guide : {out}")


if __name__ == "__main__":
    main()
