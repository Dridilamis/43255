# -*- coding: utf-8 -*-
"""
TRACE - ETAGE 0b (suite) - FILTRE DE LA SECONDE PASSE MISTRAL

La seconde passe brute ajoute surtout du bruit (mesure sur les 43 documents : 27 % des
entites ajoutees et 15 % des relations ajoutees sont justes ; le F1 baisse). Ce filtre ne
garde que les ajouts d'un type fiable.

Regle (fixee une fois, sans relire le gold a l'execution) :
  - entite ajoutee gardee si
      * son type est MICRO_ORGANISME, TRAITEMENT, BIOMARQUEUR ou EVOLUTION_PRONOSTIC,
      * elle revient dans les 3 reponses de Mistral (vote 3/3),
      * elle n'est pas niee ;
  - toutes les relations ajoutees sont retirees.

Comment la regle a ete choisie : les types ont ete retenus parce que leurs ajouts sont
justes au moins 35 % du temps sur CHACUNE des deux moities du corpus (documents pairs et
impairs) ; au-dessus d'environ un tiers de justes, un ajout fait monter le F1. Valide en
croise (types choisis sur une moitie, effet mesure sur l'autre) : F1 entites +0,3 et +0,7
point. Aucun filtre de relations n'ameliore le F1 sur les deux moities.

Usage (depuis Reduction_hallucinations) :
    python extraction_mistral\\filtre_seconde_passe.py
    cd TRACE_v2 ; python run_trace_v2.py --entree ..\\extraction_mistral\\seconde_passe_filtree
"""
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_IN = HERE / "seconde_passe"
DEFAULT_OUT = HERE / "seconde_passe_filtree"

TYPES_GARDES = {"MICRO_ORGANISME", "TRAITEMENT", "BIOMARQUEUR", "EVOLUTION_PRONOSTIC"}
VOTES_REQUIS = "3/3"


def ajoutee(e):
    return str(e.get("type_inference")) == "seconde_passe_mistral"


def garder(e):
    return (str(e.get("type") or e.get("categorie") or "").upper() in TYPES_GARDES
            and e.get("_seconde_passe_votes") == VOTES_REQUIS and e.get("nie") is not True)


def filtrer(data, c):
    retirees = set()
    for page in data.get("pages", []) or []:
        if not isinstance(page, dict):
            continue
        key = "entities" if isinstance(page.get("entities"), list) else "entites"
        kept = []
        for e in page.get(key, []) or []:
            if isinstance(e, dict) and ajoutee(e):
                if garder(e):
                    c["entites_gardees"] += 1
                else:
                    c["entites_retirees"] += 1
                    retirees.add(e.get("identifiant_entite"))
                    continue
            kept.append(e)
        page[key] = kept
    data["global_entities"] = [e for e in data.get("global_entities", []) or []
                               if not (isinstance(e, dict) and ajoutee(e)
                                       and e.get("identifiant_entite") in retirees)]
    rels = data.get("global_relations", []) or []
    data["global_relations"] = [r for r in rels if str(r.get("type_inference")) != "seconde_passe_mistral"]
    c["relations_retirees"] += len(rels) - len(data["global_relations"])


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_IN
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUT
    files = sorted(src.glob("img*.json"))
    if not files:
        sys.exit(f"Aucun JSON dans {src}")
    out.mkdir(parents=True, exist_ok=True)
    c = Counter()
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        filtrer(data, c)
        (out / path.name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(files)} documents -> {out}")
    print(dict(c))
    return 0


if __name__ == "__main__":
    sys.exit(main())
