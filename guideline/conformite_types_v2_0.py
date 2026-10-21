# -*- coding: utf-8 -*-
"""
Applique au gold les regles de TYPAGE du guideline TRACE-Sepsis v2.0 aux entites FOYER_INFECTIEUX
(a lancer apres corriger_annotation_v2_0.py).

Usage :
    python -I guideline/conformite_types_v2_0.py <annotation_label_studio.json> <sortie.json> <journal.csv>

Regles (guideline v2.0 uniquement) :
  T1  Un FOYER_INFECTIEUX dont la mention est un diagnostic de la liste LABEL_NOSOLOGIQUE
      (ex. 'gangrene gazeuse', 'pyelo obstructive', 'septicemie') est retype LABEL_NOSOLOGIQUE
      (regle 'diagnostic de la liste = toujours LABEL').
  T2  Si la mention ecrit le diagnostic ET sa localisation ('gangrene gazeuse du membre inferieur
      gauche', 'septicemie sur CVC jugulaire'), elle est coupee en deux entites, chacune sur sa propre
      surface : LABEL_NOSOLOGIQUE (diagnostic) + FOYER_INFECTIEUX (localisation), reliees par
      label_nosologique_a_pour_foyer ; les relations qui visaient le foyer passent sur la localisation
      (regle LABEL_NOSOLOGIQUE_vs_FOYER_INFECTIEUX : 'une mention recoit un seul type').
  T3  'Infection nosocomiale' (ou communautaire, associee aux soins) n'est pas une localisation :
      CONTEXTE_ACQUISITION (valeurs_autorisees_type_acquisition).
  T4  Deux entites strictement identiques (meme surface, meme position, meme type), par exemple apres
      un retypage, sont fusionnees : leurs relations sont reportees sur l'entite gardee, sans doublon.
  Toute relation devenue hors signature apres retypage est retiree et journalisee.
  Les autres FOYER_INFECTIEUX restent des localisations (le guideline liste par exemple pleural,
  osteo_articulaire, cutane_tissu_mou, digestif, catheter_acces_vasculaire, endocardite).
"""
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

GUIDELINE = Path(__file__).resolve().parent / "Guideline_TRACE_Sepsis_v2.0.json"
DIAG = r"(gangrene gazeuse|septicemie(?: a [a-z]+)?|pyelonephrite|pyelo|pneumopathie|pneumonie|abces|erysipele|sinusite)"
SEUL = re.compile(rf"^{DIAG}(?: [a-z]+)?$")                       # diagnostic seul (ex. 'pyelo obstructive')
COUPE = re.compile(rf"^{DIAG}\s+(?:du |de la |de l |des |de |sur )(.+)$")
CONTEXTE = re.compile(r"\b(nosocomiale?|communautaire|associee aux soins)\b")


def norm(s):
    s = unicodedata.normalize("NFD", str(s).lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[’'\n]", " ", s)).strip()


def main():
    src, dst, jpath = sys.argv[1:4]
    sig = {k: (v["domaine"], v["image"]) for k, v in
           json.load(open(GUIDELINE, encoding="utf-8"))["ontologie_sepsis_graph"]["signatures_relations"].items()}
    tasks = json.load(open(src, encoding="utf-8"))
    journal, n = [], {"T1": 0, "T2": 0, "T3": 0, "T4": 0, "relations_retirees": 0, "relations_deplacees": 0}
    for t in tasks:
        doc, page, txt = t["data"]["document"], t["data"]["page"], t["data"]["text"]
        res = t["annotations"][0]["result"]
        ents = {r["id"]: r for r in res if r["type"] == "labels"}
        moved = {}
        for eid, e in list(ents.items()):
            if e["value"]["labels"][0] != "FOYER_INFECTIEUX":
                continue
            m_txt = e["value"]["text"]
            n_txt = norm(m_txt)
            if CONTEXTE.search(n_txt) and n_txt.startswith("infection"):
                e["value"]["labels"] = ["CONTEXTE_ACQUISITION"]
                n["T3"] += 1
                journal.append((doc, page, "T3", m_txt, "FOYER -> CONTEXTE_ACQUISITION"))
                continue
            cut = COUPE.match(n_txt)
            if cut:
                # position de la localisation dans la surface d'origine (meme nombre de mots que le motif)
                words = list(re.finditer(r"\S+", m_txt))
                k = len(n_txt.split()) - len(cut.group(2).split())
                s0, e0 = e["value"]["start"], e["value"]["end"]
                diag_end = s0 + words[len(cut.group(1).split()) - 1].end()
                loc_start = s0 + words[k].start()
                nid = f"{eid}_loc"
                ents[nid] = {"value": {"start": loc_start, "end": e0, "text": txt[loc_start:e0],
                                       "labels": ["FOYER_INFECTIEUX"]},
                             "id": nid, "from_name": "label", "to_name": "text", "type": "labels", "origin": "manual"}
                res.append(ents[nid])
                e["value"].update(end=diag_end, text=txt[s0:diag_end], labels=["LABEL_NOSOLOGIQUE"])
                res.append({"from_id": eid, "to_id": nid, "type": "relation", "direction": "right",
                            "labels": ["label_nosologique_a_pour_foyer"]})
                moved[eid] = nid
                n["T2"] += 1
                journal.append((doc, page, "T2", m_txt, f"LABEL '{e['value']['text']}' + FOYER '{ents[nid]['value']['text']}', relies"))
            elif SEUL.match(n_txt):
                e["value"]["labels"] = ["LABEL_NOSOLOGIQUE"]
                n["T1"] += 1
                journal.append((doc, page, "T1", m_txt, "FOYER -> LABEL_NOSOLOGIQUE"))
        # T4 : fusion des entites strictement identiques
        first, alias = {}, {}
        for eid, e in ents.items():
            key = (e["value"]["start"], e["value"]["end"], e["value"]["labels"][0])
            if key in first:
                alias[eid] = first[key]
                n["T4"] += 1
                journal.append((doc, page, "T4", e["value"]["text"], "entite en double fusionnee"))
            else:
                first[key] = eid
        res = [r for r in res if not (r["type"] == "labels" and r["id"] in alias)]
        for r in res:
            if r["type"] == "relation":
                r["from_id"], r["to_id"] = alias.get(r["from_id"], r["from_id"]), alias.get(r["to_id"], r["to_id"])
        kept, vus = [], set()
        for r in res:
            if r["type"] != "relation":
                continue
            rl = (r.get("labels") or [""])[0]
            if r["to_id"] in moved and sig.get(rl, ("", ""))[1] == "FOYER_INFECTIEUX" and rl != "label_nosologique_a_pour_foyer":
                r["to_id"] = moved[r["to_id"]]
                n["relations_deplacees"] += 1
                journal.append((doc, page, "T2", rl, "relation deplacee sur la localisation"))
            a, b = ents[r["from_id"]]["value"]["labels"][0], ents[r["to_id"]]["value"]["labels"][0]
            if sig.get(rl) != (a, b) or r["from_id"] == r["to_id"]:
                n["relations_retirees"] += 1
                journal.append((doc, page, "HORS_SIGNATURE", f"{ents[r['from_id']]['value']['text']} -{rl}-> "
                                f"{ents[r['to_id']]['value']['text']}", f"retiree ({a} -> {b})"))
                continue
            cle = (r["from_id"], r["to_id"], rl)
            if cle in vus:
                continue
            vus.add(cle)
            kept.append(r)
        t["annotations"][0]["result"] = [r for r in res if r["type"] != "relation"] + kept
    json.dump(tasks, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(jpath, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(("document", "page", "regle", "element", "modification"))
        w.writerows(journal)
    print(n)


if __name__ == "__main__":
    main()
