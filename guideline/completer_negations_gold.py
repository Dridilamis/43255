# -*- coding: utf-8 -*-
"""
TRACE - COMPLETER LES NEGATIONS DU GOLD (Label Studio), sans aucun modele

Demande de l'encadrante : l'absence d'un signe ("pas de fievre") est une information clinique et
doit figurer dans la reference. Convention du medecin (dossiers corriges) : la mention niee couvre
la proposition entiere ("pas de sueurs", "Pas de foyer franc"), sans relation.

Regle deterministe, appliquee au TEXTE DU GOLD (independante de Mistral et de TRACE) :
  1. une proposition niee commence par un declencheur (pas de / pas d', absence de, sans, aucun(e))
     et s'arrete a la ponctuation, a une conjonction (et, mais, pour, avec...), au declencheur
     suivant ou apres 6 mots ;
  2. son type est celui du terme clinique qu'elle contient, d'apres le lexique des entites deja
     annotees dans le gold (type majoritaire ; terme d'au moins 4 lettres, le plus long gagne) ;
     sans terme connu, rien n'est ajoute ;
  3. une entite positive deja annotee a l'interieur de la proposition (ex. "sueurs" dans
     "pas de sueurs") est ETENDUE a la proposition niee et perd ses relations (erreur de polarite) ;
  4. sinon, une entite niee est ajoutee, sans relation.
Chaque changement est ecrit dans un journal CSV pour verification.

    python guideline\\completer_negations_gold.py ENTREE_LabelStudio.json SORTIE_LabelStudio.json
"""
import csv
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TYPES = {"SYMPTOME", "DEFAILLANCE_ORGANE", "FOYER_INFECTIEUX", "LABEL_NOSOLOGIQUE", "COMORBIDITE_ANTECEDENT",
         "IMAGERIE_PROCEDURE", "MICRO_ORGANISME", "SIGNE_VITAL"}
CUE = re.compile(r"(?i)(?<![\w’'])(pas\s+d(?:e\s+|['’]\s*)|absence\s+d(?:e\s+|['’]\s*)|sans\s+|aucune?\s+)")
STOP = re.compile(r"(?i)[.;,:\n()\[\]]|\s(?:et|mais|pour|avec|car|donc|qui|alors|puis|chez|malgr[ée]|lors|en\s+faveur|"
                  r"sur|aux?|dans|en\s+dehors|retrouv\w*|pas\s+d|absence\s+d|sans|aucune?)(?=\s|['’])")
DEJA_NIE = re.compile(r"(?i)^\s*(pas\s+d|absence|sans|aucun|ni\s|non\s)")


def norm(s):
    s = unicodedata.normalize("NFD", str(s).lower())
    return re.sub(r"\s+", " ", "".join(c for c in s if unicodedata.category(c) != "Mn")).strip()


def lexique(taches):
    votes = defaultdict(Counter)
    for t in taches:
        for r in t["annotations"][0]["result"]:
            if r["type"] == "labels" and r["value"]["labels"][0] in TYPES and not DEJA_NIE.match(r["value"]["text"]):
                n = norm(r["value"]["text"])
                if 4 <= len(n) <= 40:
                    votes[n][r["value"]["labels"][0]] += 1
    return {n: c.most_common(1)[0][0] for n, c in votes.items()}


def propositions(text):
    for m in CUE.finditer(text):
        debut = m.start()
        reste = text[m.end():]
        stop = STOP.search(reste)
        seg = reste[:stop.start()] if stop else reste
        mots = seg.split()
        if not mots:
            continue
        seg = " ".join(mots[:6]) if len(mots) > 6 else seg.rstrip()
        fin = m.end() + len(seg.rstrip())
        yield debut, fin


def proche_du_declencheur(prop, debut_terme):
    """Le terme nie doit commencer dans les 3 premiers mots qui suivent le declencheur
    ("pas de signe de choc" oui ; "pas d'origine centrale pour expliquer l'anemie" non)."""
    m = CUE.match(prop)
    apres = prop[m.end() if m else 0:debut_terme]
    return len(apres.split()) <= 3


def type_de(prop, lex):
    n = norm(prop)
    best = None
    for terme, typ in lex.items():
        if len(terme) > (len(best[0]) if best else 0):
            m = re.search(r"(?<!\w)" + re.escape(terme) + r"(?!\w)", n)
            if m and proche_du_declencheur(n, m.start()):
                best = (terme, typ)
    return best


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    taches = json.loads(src.read_text(encoding="utf-8"))
    lex = lexique(taches)
    journal, c = [], Counter()
    for t in taches:
        text, res = t["data"]["text"], t["annotations"][0]["result"]
        doc, page = t["data"]["document"].replace("_texte_brut", ""), t["data"]["page"]
        ents = [r for r in res if r["type"] == "labels"]
        n_id = len(ents)
        for debut, fin in propositions(text):
            prop = text[debut:fin]
            dedans = [r for r in ents if r["value"]["start"] >= debut and r["value"]["end"] <= fin]
            chevauche = [r for r in ents if r["value"]["start"] < fin and debut < r["value"]["end"] and r not in dedans]
            if any(DEJA_NIE.match(r["value"]["text"]) for r in dedans + chevauche) or chevauche:
                c["ignoree_deja_annotee_ou_chevauchement"] += 1
                continue
            if dedans:
                cible = max(dedans, key=lambda r: r["value"]["end"] - r["value"]["start"])
                # un examen realise n'est pas nie ("absence de thymome sur le TDM") ; le terme nie doit
                # suivre de pres le declencheur
                if (cible["value"]["labels"][0] not in TYPES or cible["value"]["labels"][0] == "IMAGERIE_PROCEDURE"
                        or not proche_du_declencheur(text[debut:fin], cible["value"]["start"] - debut)):
                    c["ignoree_type_non_clinique"] += 1
                    continue
                ancien = cible["value"]["text"]
                cible["value"].update(start=debut, end=fin, text=prop)
                retirees = [r for r in res if r["type"] == "relation" and cible["id"] in (r["from_id"], r["to_id"])]
                for r in retirees:
                    res.remove(r)
                for r in dedans:
                    if r is not cible:
                        res.remove(r)
                        ents.remove(r)
                c["polarite_corrigee"] += 1
                c["relations_retirees"] += len(retirees)
                journal.append([doc, page, "polarite_corrigee", cible["value"]["labels"][0], ancien, prop, len(retirees)])
                continue
            trouve = type_de(prop, lex)
            if not trouve:
                c["ignoree_sans_terme_connu"] += 1
                continue
            n_id += 1
            r = {"value": {"start": debut, "end": fin, "text": prop, "labels": [trouve[1]]}, "id": f"neg{n_id}",
                 "from_name": "label", "to_name": "text", "type": "labels", "origin": "regle_negation"}
            res.append(r)
            ents.append(r)
            c["negation_ajoutee"] += 1
            journal.append([doc, page, "negation_ajoutee", trouve[1], trouve[0], prop, 0])
    dst.write_text(json.dumps(taches, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(dst.with_name(dst.stem + "_journal_negations.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["dossier", "page", "action", "type", "terme_ou_ancienne_mention", "mention_niee", "relations_retirees"])
        w.writerows(journal)
    print(dict(c))
    print(f"Sortie : {dst}")


if __name__ == "__main__":
    main()
