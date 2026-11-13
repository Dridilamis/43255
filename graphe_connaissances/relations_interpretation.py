# -*- coding: utf-8 -*-
"""
Recupere des relations d'interpretation que l'extraction n'a pas le droit de produire.

Les regles strictes apprises (guide_appris_v2_0.json) interdisent a Mistral les types de
relation dont moins de 30 % des exemples etaient justes : micro_organisme_isole_dans,
label_nosologique_a_pour_foyer, imagerie_objective_foyer... Le graphe obtenu ne relie donc
ni les germes ni les localisations. Ce script les relie a posteriori, par des regles
deterministes ancrees dans le texte, sans appel au modele :

  micro_organisme_isole_dans      un germe et un foyer cites dans la meme phrase, a moins de
                                  80 caracteres, ou le germe ecrit dans la mention du foyer
                                  ("spondylodiscite a Pseudomonas") ; chaque germe est relie
                                  au foyer le plus proche ; un foyer qui nomme un autre germe
                                  ("pneumopathie a SARM") n'est pas relie a celui-ci.
  label_nosologique_a_pour_foyer  un diagnostic et une localisation dans la meme phrase, a
                                  moins de 40 caracteres ; chaque localisation est reliee au
                                  diagnostic le plus proche ("pneumopathie du lobe inferieur
                                  droit", "choc septique a point de depart pulmonaire").
  imagerie_objective_foyer        (option --imagerie) un examen d'imagerie et un foyer dans la
                                  meme phrase, a moins de 80 caracteres. Precision mesuree
                                  faible sur le gold v1.6 (environ 40 %) : desactive par defaut.

Seules les entites conservees par TRACE et non niees sont reliees. Chaque relation ajoutee
porte sa phrase comme preuve, l'origine "regle_interpretation" et une confiance moyenne.

    python graphe_connaissances/relations_interpretation.py --entree TRACE_v2/sorties_v2_0/07_arbitrage
    python graphe_connaissances/relations_interpretation.py --entree ... --gold gold_v2_0    # + mesure
    python graphe_connaissances/construire_graphe.py --entree graphe_connaissances/sorties/avec_interpretation

La mesure (--gold) apparie une relation a la reference si elle a le meme type et si la
moyenne des similarites de son sujet et de son objet atteint 0,80 (meme principe que le
mode Relaxed, chapitre 4) ; elle est approchee, a confirmer avec l'etage 8 de TRACE.
"""
import argparse
import difflib
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ICI = Path(__file__).resolve().parent
SORTIE_DEFAUT = ICI / "sorties" / "avec_interpretation"

PHRASE = re.compile(r"(?<=[.;!?])\s+|\n")


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def contient(grand, petit):
    return bool(petit) and f" {petit} " in f" {grand} "


def positions(phrase_n, mention):
    m = norm(mention)
    if len(m) < 3:
        return []
    return [x.start() for x in re.finditer(r"(?<![a-z0-9])" + re.escape(m) + r"(?![a-z0-9])", phrase_n)]


def type_entite(e):
    return str(e.get("type") or e.get("categorie") or "")


def nom(e):
    return e.get("name") or e.get("preuve") or ""


# ---------------------------------------------------------------------------- regles

def relier(phrase_n, sujets, objets, fenetre, cote, filtre=None):
    """Couples (sujet, objet, distance) : pour chaque entite du cote choisi, l'entite de
    l'autre type la plus proche dans la phrase, a moins de `fenetre` caracteres."""
    res = []
    ancres, autres = (sujets, objets) if cote == "sujet" else (objets, sujets)
    for a in ancres:
        pa = positions(phrase_n, nom(a))
        if not pa:
            continue
        meilleur = None
        for b in autres:
            pb = positions(phrase_n, nom(b))
            if not pb:
                continue
            s, o = (a, b) if cote == "sujet" else (b, a)
            d = filtre(s, o) if filtre else None
            if d is False:
                continue
            dist = 0 if d == 0 else min(abs(x - y) for x in pa for y in pb)
            if dist <= fenetre and (meilleur is None or dist < meilleur[2]):
                meilleur = (s, o, dist)
        if meilleur:
            res.append(meilleur)
    return res


def filtre_germe(germes_page):
    noms = [norm(nom(g)) for g in germes_page]

    def f(germe, foyer):
        gn, fn = norm(nom(germe)), norm(nom(foyer))
        if not fn or fn == gn or contient(gn, fn):
            return False                     # le "foyer" est le germe lui-meme
        if contient(fn, gn):
            return 0                         # "spondylodiscite a Pseudomonas"
        autre = any(n != gn and len(n) >= 3 and contient(fn, n) and not contient(n, gn) for n in noms)
        if autre or re.search(r"\ba [a-z]", fn):
            return False                     # le foyer nomme un autre germe
        return None
    return f


def filtre_distinct(sujet, objet):
    """Refuse deux mentions dont l'une contient l'autre ("pneumopathie communautaire" et
    "pneumopathie") : c'est une meme information extraite deux fois, pas un lien."""
    sn, on = norm(nom(sujet)), norm(nom(objet))
    if not sn or not on or sn == on or contient(sn, on) or contient(on, sn):
        return False
    return None


REGLES = {
    "micro_organisme_isole_dans": ("MICRO_ORGANISME", "FOYER_INFECTIEUX", 80, "sujet", True),
    "label_nosologique_a_pour_foyer": ("LABEL_NOSOLOGIQUE", "FOYER_INFECTIEUX", 40, "objet", False),
    "imagerie_objective_foyer": ("IMAGERIE_PROCEDURE", "FOYER_INFECTIEUX", 80, "sujet", False),
}


def traiter(data, types):
    ids_globaux = {e.get("identifiant_entite") for e in data.get("global_entities") or []}
    existantes = {(r.get("identifiant_entite_sujet"), r.get("type_relation"), r.get("identifiant_entite_objet"))
                  for r in data.get("global_relations") or []}
    ajout, n = [], Counter()
    for p in data.get("pages") or []:
        texte = p.get("texte_brut") or ""
        ents = [e for e in p.get("entities") or []
                if e.get("identifiant_entite") in ids_globaux and not e.get("nie")
                and not ((e.get("trace_v2") or {}).get("attributs") or {}).get("negation")]
        for rel in types:
            ts, to, fenetre, cote, germe = REGLES[rel]
            sujets = [e for e in ents if type_entite(e) == ts]
            objets = [e for e in ents if type_entite(e) == to]
            if not sujets or not objets:
                continue
            filtre = filtre_germe(sujets) if germe else filtre_distinct
            for phrase in PHRASE.split(texte):
                pn = norm(phrase)
                if not pn:
                    continue
                for s, o, dist in relier(pn, sujets, objets, fenetre, cote, filtre):
                    cle = (s["identifiant_entite"], rel, o["identifiant_entite"])
                    if cle in existantes:
                        continue
                    existantes.add(cle)
                    n[rel] += 1
                    ajout.append({
                        "identifiant_relation": f"R_INTERP_{len(ajout) + 1:05d}",
                        "identifiant_entite_sujet": s["identifiant_entite"], "entite_sujet": nom(s),
                        "type_relation": rel,
                        "identifiant_entite_objet": o["identifiant_entite"], "entite_objet": nom(o),
                        "preuve": " ".join(phrase.split())[:300], "type_inference": "regle_interpretation",
                        "confiance": "moyenne", "page": p.get("page"),
                        "trace_confidence": {"level": "MEDIUM", "method": "REGLE_INTERPRETATION",
                                             "is_probability": False, "signaux_faibles": ["origine_regle"]},
                        "trace_v2": {"interpretation": {"regle": rel, "distance": dist}},
                    })
    data.setdefault("global_relations", []).extend(ajout)
    return ajout, n


# ---------------------------------------------------------------------------- mesure

def sim(a, b):
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    r = difflib.SequenceMatcher(None, a, b).ratio()
    court, long_ = sorted((a, b), key=len)
    return max(r, 0.85) if len(court) >= 4 and contient(long_, court) else r


def mesurer(ajout_par_doc, gold_dir, types, entites_par_doc=None):
    tp, prod, ref, atteignable = Counter(), Counter(), Counter(), Counter()
    for doc, ajout in ajout_par_doc.items():
        f = Path(gold_dir) / f"{doc}.json"
        if not f.exists():
            continue
        g = json.loads(f.read_text(encoding="utf-8-sig"))
        gold = [(r.get("relation"), r.get("subject"), r.get("object")) for r in g.get("global_relations") or []
                if r.get("relation") in types]
        ents = (entites_par_doc or {}).get(doc, [])
        for t, gs, go in gold:
            ref[t] += 1
            ts, to = REGLES[t][0], REGLES[t][1]
            # plafond : les deux extremites ont-elles ete extraites (bon type, meme dossier) ?
            if any(type_entite(e) == ts and sim(nom(e), gs) >= 0.8 for e in ents) and \
               any(type_entite(e) == to and sim(nom(e), go) >= 0.8 for e in ents):
                atteignable[t] += 1
        pris = set()
        for r in ajout:
            t = r["type_relation"]
            prod[t] += 1
            best, bi = 0.0, None
            for i, (gt, gs, go) in enumerate(gold):
                if i in pris or gt != t:
                    continue
                sc = (sim(r["entite_sujet"], gs) + sim(r["entite_objet"], go)) / 2
                if sc > best:
                    best, bi = sc, i
            if best >= 0.80:
                pris.add(bi)
                tp[t] += 1
    print("\nMesure sur le Gold Standard (appariement approche, seuil 0,80) :")
    for t in types:
        p = tp[t] / prod[t] if prod[t] else 0
        r = tp[t] / ref[t] if ref[t] else 0
        print(f"  {t:32s} ajoutees {prod[t]:4d} | justes {tp[t]:4d} | reference {ref[t]:4d}"
              f" | precision {p:6.1%} | rappel {r:6.1%}")
        if entites_par_doc is not None:
            print(f"  {'':32s} plafond : {atteignable[t]} relation(s) de reference sur {ref[t]} ont leurs"
                  f" deux extremites extraites avec le bon type")
    return tp, prod, ref


# ---------------------------------------------------------------------------- principal

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--entree", required=True, help="dossier des JSON TRACE (sortie de l'etage 7)")
    ap.add_argument("--sortie", default=str(SORTIE_DEFAUT))
    ap.add_argument("--gold", help="dossier du Gold Standard (format de l'evaluateur) pour mesurer la precision")
    ap.add_argument("--imagerie", action="store_true", help="ajoute aussi imagerie_objective_foyer")
    a = ap.parse_args()
    types = ["micro_organisme_isole_dans", "label_nosologique_a_pour_foyer"] + \
            (["imagerie_objective_foyer"] if a.imagerie else [])

    out = Path(a.sortie)
    out.mkdir(parents=True, exist_ok=True)
    total, par_doc, entites = Counter(), {}, {}
    fichiers = [f for f in sorted(Path(a.entree).glob("*.json")) if not f.name.startswith("_")]
    if not fichiers:
        sys.exit(f"Aucun JSON dans {a.entree}")
    for f in fichiers:
        data = json.loads(f.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict) or not isinstance(data.get("global_entities"), list):
            continue
        ajout, n = traiter(data, types)
        total.update(n)
        doc = re.split(r"_trace_sepsis", f.stem)[0]
        par_doc[doc] = ajout
        entites[doc] = [e for e in data.get("global_entities") or [] if not e.get("nie")]
        (out / f.name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(par_doc)} dossiers -> {out}")
    for t in types:
        print(f"  {t:32s} {total[t]:4d} relation(s) ajoutee(s)")
    if a.gold:
        mesurer(par_doc, a.gold, types, entites)
        compte = Counter(type_entite(e) for es in entites.values() for e in es)
        print(f"\nEntites extraites (non niees) : MICRO_ORGANISME {compte['MICRO_ORGANISME']}, "
              f"FOYER_INFECTIEUX {compte['FOYER_INFECTIEUX']}, LABEL_NOSOLOGIQUE {compte['LABEL_NOSOLOGIQUE']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
