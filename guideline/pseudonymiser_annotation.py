# -*- coding: utf-8 -*-
"""
Efface le nom du patient dans une annotation Label Studio (demande du medecin : pseudonymisation).

Usage :
    python -I guideline/pseudonymiser_annotation.py <annotation_label_studio.json> <dossier_sortie>

Sorties (dans <dossier_sortie>) :
    <nom du fichier d'entree avec le suffixe _pseudo>.json   annotation importable, noms effaces
    journal_pseudonymisation.csv   chaque effacement (document, page, position, contexte DEJA masque)

Principe : chaque lettre du nom est remplacee par 'X', sans changer la longueur du texte. Les positions
(start / end) de toutes les annotations restent donc valides ; le champ 'text' des entites qui touchent
un nom efface est resynchronise. Aucun nom n'est ecrit dans le journal.

Noms recherches, dossier par dossier :
  En-tete : le champ 'Patient : ...' de la premiere page garde sa forme pseudonymisee (3 premieres
      lettres de chaque nom, ex. 'Patient : KAU BER'). P1 : si un nom y est ecrit en entier (4 lettres
      ou plus), seules ses 3 premieres lettres sont gardees (ex. 'VINOT' -> 'VINXX'). Les noms de
      l'en-tete servent aussi a retrouver les autres occurrences ;
  P2  un nom apres une civilite (M., Mr, Mme, Mlle, Monsieur, Madame, Mademoiselle), dans tout le texte ;
  P3  toute autre occurrence, dans tout le dossier, d'un nom trouve en P2, en P4 ou dans l'en-tete
      (mot de 4 lettres ou plus) ;
  P4  le nom d'un proche (frere, soeur, fils, fille, epoux, epouse, mari, femme, pere, mere, tuteur,
      curateur...) ecrit juste apres le lien de parente sous la forme 'NOM Prenom' (ex. 'Frere : NOM Prenom') ;
  P5  les numeros de telephone (chiffres remplaces par 'X').
"""
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

LETTRES = "A-Za-zÀ-ÖØ-öø-ÿ"
CIVILITE = re.compile(
    rf"(?<![{LETTRES}.])(M\.|Mr\.?|Mme\.?|Mlle\.?|Monsieur|Madame|Mademoiselle)\s+"
    rf"((?:[A-ZÀ-Ý][{LETTRES}'’\-]+)(?:\s*\[\?\])?(?:\s+[A-ZÀ-Ý]{{2,}}(?:\s*\[\?\])?)?)")
ENTETE = re.compile(r"(?im)^([^\n]{0,40}\bpatient\s*:[ \t]*)([^\n]*)$")
PROCHE = re.compile(
    r"(?i:\b(?:fr[eè]re|s(?:oe|œ)ur|fils|fille|[eé]pou(?:x|se)|mari|femme|p[eè]re|m[eè]re|tut(?:eur|rice)|"
    r"curat(?:eur|rice)|compagn(?:e|on)|neveu|ni[eè]ce|personne de confiance))\s*:?\s*"
    r"([A-ZÀ-Ý][A-ZÀ-Ý'’\-]{2,}\s+[A-ZÀ-Ý][a-zà-ÿ'’\-]+)(?![A-Za-zÀ-ÿ])")
TELEPHONE = re.compile(r"(?<!\d)0[1-9](?:[ .\-]?\d{2}){4}(?!\d)")
MOT = re.compile(rf"[{LETTRES}][{LETTRES}'’\-]*")


def masquer(s):
    return "".join("X" if ch.isalpha() else ch for ch in s)


def noms_du_dossier(pages):
    """Noms (minuscules) a rechercher dans tout le dossier."""
    noms = set()
    for txt in pages:
        for m in CIVILITE.finditer(txt):
            for w in MOT.findall(m.group(2)):
                if len(w) >= 3:
                    noms.add(w.lower())
        for m in ENTETE.finditer(txt):
            for w in MOT.findall(m.group(2).replace("[?]", " ")):
                if len(w) >= 4:
                    noms.add(w.lower())
        for m in PROCHE.finditer(txt):
            for w in MOT.findall(m.group(1)):
                if len(w) >= 3:
                    noms.add(w.lower())
    return noms


def spans(txt, noms):
    out = []
    for m in CIVILITE.finditer(txt):
        out.append((m.start(2), m.end(2), "P2"))
    for m in PROCHE.finditer(txt):
        out.append((m.start(1), m.end(1), "P4"))
    for m in TELEPHONE.finditer(txt):
        out.append((m.start(), m.end(), "P5"))
    for nom in noms:
        for m in re.finditer(rf"(?<![{LETTRES}]){re.escape(nom)}(?![{LETTRES}])(\s*\[\?\])?", txt, re.I):
            out.append((m.start(), m.end(), "P3"))
    return out


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    tasks = json.loads(src.read_text(encoding="utf-8"))
    par_doc = defaultdict(list)
    for t in tasks:
        par_doc[t["data"].get("document", "")].append(t["data"].get("text", ""))
    noms = {d: noms_du_dossier(p) for d, p in par_doc.items()}

    journal, c = [], Counter()
    for t in tasks:
        doc, page, txt = t["data"].get("document", ""), t["data"].get("page", ""), t["data"].get("text", "")
        chars = list(txt)
        touches = []
        entete = [(m.start(2), m.end(2)) for m in ENTETE.finditer(txt)]
        for a, b in entete:                    # P1 : en-tete, on ne garde que 3 lettres par nom
            for w in MOT.finditer(txt[a:b]):
                if len(w.group(0)) >= 4:
                    c["P1"] += 1
                    touches.append((a + w.start(), a + w.end(), "P1"))
                    for i in range(a + w.start() + 3, a + w.end()):
                        if chars[i].isalpha():
                            chars[i] = "X"
        for s, e, regle in spans(txt, noms[doc]):
            if any(s < b and a < e for a, b in entete):
                continue                       # l'en-tete 'Patient : ...' est conserve tel quel
            cible = (lambda ch: ch.isdigit()) if regle == "P5" else (lambda ch: ch.isalpha() and ch != "X")
            if any(cible(ch) for ch in chars[s:e]):
                c[regle] += 1
                touches.append((s, e, regle))
            for i in range(s, e):
                if cible(chars[i]):
                    chars[i] = "X"
        new = "".join(chars)
        assert len(new) == len(txt)
        t["data"]["text"] = new
        for s, e, regle in sorted(touches):
            journal.append((doc, page, regle, s, e, new[max(0, s - 40):e + 40].replace("\n", " ")))
        for r in t["annotations"][0]["result"]:
            v = r.get("value", {})
            if r.get("type") == "labels" and new[v["start"]:v["end"]] != v.get("text"):
                v["text"] = new[v["start"]:v["end"]]
                c["entites_resynchronisees"] += 1
        c["pages"] += 1

    name = src.stem + "_pseudo.json"
    (out / name).write_text(json.dumps(tasks, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(out / "journal_pseudonymisation.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(("document", "page", "regle", "debut", "fin", "contexte_masque"))
        w.writerows(journal)
    print(f"Pages : {c['pages']} | effacements : en-tete (noms complets tronques a 3 lettres) {c['P1']}, civilite {c['P2']}, autres occurrences {c['P3']}, "
          f"proches {c['P4']}, telephones {c['P5']}"
          f" | entites resynchronisees {c['entites_resynchronisees']}")
    print(f"Sortie : {out / name}")


if __name__ == "__main__":
    main()
