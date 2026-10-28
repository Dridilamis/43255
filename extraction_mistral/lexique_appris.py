# -*- coding: utf-8 -*-
"""
TRACE - LEXIQUE APPRIS SUR LE GOLD, EN VALIDATION CROISEE (post-traitement de l'extraction)

Pour chaque moitie du corpus (memes plis que l'etage 8), un lexique est construit a partir du gold
de l'AUTRE moitie : chaque mention annotee (normalisee) avec son type. Il sert a trois corrections
deterministes de l'extraction Mistral :

  1. TYPE    une entite dont la mention est dans le lexique avec un type tres majoritaire
             (>= 80 %, vue au moins 2 fois) prend ce type ;
  2. BORNES  une entite trop longue qui contient un terme du lexique de meme type est recadree
             sur ce terme ("Claforan 1g x 3/j" -> "Claforan" si la posologie est a part) ;
  2b. VALEUR un BIOMARQUEUR extrait sans sa valeur ("Uree") recoit la valeur et l'unite ecrites
             juste apres ("Uree 33 mmol/L"), comme dans le gold ;
  3. RAPPEL  un terme du lexique tres fiable (quand il apparait dans un texte de l'autre moitie,
             il est annote avec ce type au moins 80 % du temps) et absent de l'extraction est
             ajoute la ou il est ecrit dans la page.
Aucun dossier n'est corrige avec son propre gold. Les mentions niees ne sont jamais modifiees.

    python extraction_mistral\\lexique_appris.py EXTRACTION gold_v2_0 SORTIE
"""
import json
import re
import shutil
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PART_TYPE = 0.80
PRECISION_RAPPEL = 0.80
MIN_VU = 2
NEG = re.compile(r"^\s*(pas d|absence|sans |ni |non |aucun)", re.IGNORECASE)
TYPES_RAPPEL = {"TRAITEMENT", "MICRO_ORGANISME", "IMAGERIE_PROCEDURE", "SYMPTOME", "DEFAILLANCE_ORGANE",
                "LABEL_NOSOLOGIQUE", "COMORBIDITE_ANTECEDENT", "SERVICE_MEDICAL", "SCORE_NEUROLOGIQUE"}


def cle_doc(path):
    return Path(path).name.split("_trace_")[0].replace(".json", "")


def norm(s):
    s = unicodedata.normalize("NFD", str(s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def motif(terme):
    return re.compile(r"(?<![A-Za-z0-9À-ÿ])" + r"[\s\W_]+".join(map(re.escape, terme.split())) + r"(?![A-Za-z0-9À-ÿ])",
                      re.IGNORECASE)


def sans_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def apprendre(golds):
    types = defaultdict(Counter)
    for g in golds:
        for p in g["pages"]:
            for e in p["entities"]:
                n = norm(e["name"])
                if len(n) >= 3 and not NEG.match(e["name"]):
                    types[n][e["type"]] += 1
    lex = {}
    for n, c in types.items():
        t, k = c.most_common(1)[0]
        if sum(c.values()) >= MIN_VU and k / sum(c.values()) >= PART_TYPE:
            lex[n] = t
    # fiabilite comme dictionnaire : quand le terme est ecrit dans une page de l'autre moitie,
    # est-il annote (chevauchement) avec ce type ?
    fiable = {}
    for n, t in lex.items():
        if t not in TYPES_RAPPEL or len(n) < 4:
            continue
        rx, vu, ok = motif(n), 0, 0
        for g in golds:
            for p in g["pages"]:
                txt = sans_accents(p.get("text", ""))
                for m in rx.finditer(txt):
                    vu += 1
                    ok += any(e["type"] == t and e["start"] < m.end() and m.start() < e["end"] for e in p["entities"])
        if vu >= MIN_VU and ok / vu >= PRECISION_RAPPEL:
            fiable[n] = t
    return lex, fiable


VALEUR_APRES = re.compile(r"^\s*(?:[:=]|est\s+(?:mesur[ée]e?\s+)?[àa]|[àa]|de)?\s*[<>]?\s*\d+(?:[.,]\d+)?"
                          r"(?:\s*(?:[a-zA-Zµ%/°*^0-9.]+(?:/[a-zA-Z0-9]+)?))?")


def completer_valeur(e, txt):
    """Convention du gold : un BIOMARQUEUR porte sa valeur ("Uree 33 mmol/L"). Si le modele n'a
    extrait que le nom ("Uree"), la valeur et l'unite ecrites juste apres sont ajoutees."""
    if e["categorie"] != "BIOMARQUEUR" or re.search(r"\d", e["name"]) or e.get("end") is None:
        return False
    m = VALEUR_APRES.match(txt[e["end"]:e["end"] + 40])
    if not m or not re.search(r"\d", m.group(0)):
        return False
    e["end"] += len(m.group(0).rstrip())
    e["name"] = e["preuve"] = txt[e["start"]:e["end"]]
    return True


def corriger(data, lex, fiable, c):
    for p in data.get("pages", []):
        txt = p.get("texte_brut", "")
        txt_sa = sans_accents(txt)
        ents = p.get("entities", [])
        for e in ents:
            if NEG.match(e["name"]):
                continue
            if completer_valeur(e, txt):
                c["biomarqueur_valeur_ajoutee"] += 1
                continue
            n = norm(e["name"])
            if n in lex and lex[n] != e["categorie"]:
                c[f"type_{e['categorie']}->{lex[n]}"] += 1
                e["categorie"] = e["type"] = lex[n]
                e["type_inference"] = "lexique_appris_type"
            elif n not in lex and len(n.split()) >= 3 and e.get("start") is not None:
                inclus = [t for t, ty in lex.items() if ty == e["categorie"] and len(t) >= 4 and f" {t} " in f" {n} "]
                if inclus:
                    t = max(inclus, key=len)
                    zone = txt_sa[e["start"]:e["end"]]
                    m = motif(t).search(zone)
                    if m:
                        e["start"], e["end"] = e["start"] + m.start(), e["start"] + m.end()
                        e["name"] = e["preuve"] = txt[e["start"]:e["end"]]
                        e["type_inference"] = "lexique_appris_bornes"
                        c["bornes_recadrees"] += 1
        occupe = [(e.get("start", -1), e.get("end", -1)) for e in ents]
        n_id = len(ents)
        for t, ty in fiable.items():
            for m in motif(t).finditer(txt_sa):
                if any(a < m.end() and m.start() < b for a, b in occupe):
                    continue
                n_id += 1
                surf = txt[m.start():m.end()]
                ents.append({"identifiant_entite": f"P{p['page']}_L{n_id:03d}", "categorie": ty, "type": ty,
                             "name": surf, "preuve": surf, "parametre": None, "valeur": None, "unite": None,
                             "nie": False, "hypothese": False, "confiance": "elevee",
                             "type_inference": "lexique_appris_rappel", "page": p["page"],
                             "start": m.start(), "end": m.end()})
                occupe.append((m.start(), m.end()))
                c[f"rappel_{ty}"] += 1
        p["entities"] = ents
    data["global_entities"] = [e for p in data.get("pages", []) for e in p.get("entities", [])]
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
    for k in ((0,) if dev else (0, 1)):
        lex, fiable = apprendre([json.loads(Path(golds[d]).read_text(encoding="utf-8")) for d in plis[1 - k]])
        print(f"Pli {k + 1} : lexique de {len(lex)} termes, dont {len(fiable)} fiables pour le rappel")
        for d in plis[k]:
            data = json.loads(Path(preds[d]).read_text(encoding="utf-8"))
            (out / Path(preds[d]).name).write_text(json.dumps(corriger(data, lex, fiable, c), ensure_ascii=False,
                                                              indent=1), encoding="utf-8")
    if (src / "textes_bruts").is_dir():
        shutil.copytree(src / "textes_bruts", out / "textes_bruts", dirs_exist_ok=True)
    print(dict(sorted(c.items(), key=lambda x: -x[1])[:25]))
    print(f"Sortie : {out}")


if __name__ == "__main__":
    main()
