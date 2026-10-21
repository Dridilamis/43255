# -*- coding: utf-8 -*-
"""
Met l'annotation Label Studio v1.7 en conformite avec le guideline TRACE-Sepsis v2.0 et produit un
fichier importable dans Label Studio.

Usage :
    python -I guideline/corriger_annotation_v2_0.py <annotation_v1.7_label_studio.json> <dossier_sortie>

Sorties (dans <dossier_sortie>) :
    Annotation_49_Pdfs_v2.0_LabelStudio.json   taches + annotations corrigees (import Label Studio)
    journal_corrections_v2.0.csv               chaque modification appliquee
    a_revoir_v2.0.csv                          cas ambigus, a valider par l'annotatrice

Regles appliquees (tirees du guideline v2.0 uniquement, aucune sortie de modele n'est lue) :
  V1  presente_suspicion_infection (DONNEE_PATIENT -> FOYER_INFECTIEUX), retiree en v2.0, devient
      label_nosologique_a_pour_foyer (LABEL_NOSOLOGIQUE -> FOYER_INFECTIEUX), le LABEL etant celui
      de la meme page :
        - un seul LABEL sur la meme ligne, a moins de 80 caracteres : conversion automatique ;
        - plusieurs LABEL sur la ligne : le plus proche est choisi, cas liste a revoir ;
        - aucun LABEL sur la ligne : le LABEL INFECTIEUX le plus proche de la page est propose (a revoir) ;
        - aucun LABEL infectieux sur la page : la relation est retiree, le foyer reste sans rattachement
          (a revoir).
  V2  FOYER_INFECTIEUX rattache a une COMORBIDITE_ANTECEDENT (FOYER reserve aux LABEL en v2.0) :
        - une COMORBIDITE colle au foyer (au plus 3 caracteres d'ecart, ex. 'tuberculose | pulmonaire')
          et aucun LABEL sur la ligne : le foyer est retire avec ses relations ;
        - une COMORBIDITE est le diagnostic le plus proche sur la ligne, sans LABEL sur la ligne :
          cas liste a revoir, rien n'est retire.
  Les relations deja existantes ne sont jamais dupliquees.
"""
import csv
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

LIGNE = 80          # meme ligne, distance maximale en caracteres
COLLE = 3           # foyer colle a une comorbidite
# diagnostics infectieux de la liste LABEL_NOSOLOGIQUE v2.0 (les seuls dont un foyer peut etre la localisation)
INFECTIEUX = re.compile(r"seps|septi|bacteriemie|infection|pneumo|pneumonie|pavm|abces|pyelo|erysipele|sinusite|"
                        r"gangrene")


def norm(text):
    text = unicodedata.normalize("NFD", str(text or "").lower())
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")


def lab(r):
    return r["value"]["labels"][0]


def dist(a, b):
    """Ecart en caracteres entre deux regions (0 si elles se chevauchent)."""
    a0, a1, b0, b1 = a["value"]["start"], a["value"]["end"], b["value"]["start"], b["value"]["end"]
    return max(0, max(a0, b0) - min(a1, b1))


def meme_ligne(txt, a, b):
    lo = min(a["value"]["start"], b["value"]["start"])
    hi = max(a["value"]["end"], b["value"]["end"])
    return "\n" not in txt[lo:hi]


def ligne(txt, r):
    s, e = r["value"]["start"], r["value"]["end"]
    ls = txt.rfind("\n", 0, s) + 1
    le = txt.find("\n", e)
    return txt[ls:len(txt) if le < 0 else le].strip()


def corriger_tache(task, journal, revoir, c):
    doc, page = task["data"].get("document", ""), task["data"].get("page", "")
    txt = task["data"].get("text", "")
    res = task["annotations"][0]["result"]
    ents = {r["id"]: r for r in res if r.get("type") == "labels"}
    rels = [r for r in res if r.get("type") == "relation"]
    labels = [e for e in ents.values() if lab(e) == "LABEL_NOSOLOGIQUE"]
    infectieux = [l for l in labels if INFECTIEUX.search(norm(l["value"]["text"]))]
    comorb = [e for e in ents.values() if lab(e) == "COMORBIDITE_ANTECEDENT"]
    existing = {(r["from_id"], r["to_id"], (r.get("labels") or [""])[0]) for r in rels}

    def label_ligne(f):
        return sorted((dist(f, l), l["id"]) for l in labels if meme_ligne(txt, f, l) and dist(f, l) <= LIGNE)

    # ---- V2 : foyers rattaches a une comorbidite
    retires = set()
    for f in [e for e in ents.values() if lab(e) == "FOYER_INFECTIEUX"]:
        if label_ligne(f):
            continue
        sur_ligne = sorted((dist(f, m), m["id"]) for m in comorb if meme_ligne(txt, f, m) and dist(f, m) <= LIGNE)
        if not sur_ligne:
            continue
        d, mid = sur_ligne[0]
        m = ents[mid]
        if d <= COLLE:
            retires.add(f["id"])
            c["V2_foyer_comorbidite_retire"] += 1
            journal.append((doc, page, "V2", f["value"]["text"], f"FOYER retire : localisation de la comorbidite '{m['value']['text']}'"))
        else:
            c["V2_a_revoir"] += 1
            revoir.append((doc, page, "foyer_pres_d_une_comorbidite", f["value"]["text"],
                           f"comorbidite proche : '{m['value']['text']}'", "Retirer le FOYER s'il localise la comorbidite",
                           ligne(txt, f)))

    # ---- V1 : conversion de presente_suspicion_infection
    kept = []
    for r in rels:
        a, b, rl = r["from_id"], r["to_id"], (r.get("labels") or [""])[0]
        if a in retires or b in retires:
            c["relations_retirees_avec_foyer"] += 1
            journal.append((doc, page, "V2", f"{ents[a]['value']['text']} -{rl}-> {ents[b]['value']['text']}",
                            "relation retiree avec son foyer"))
            continue
        if rl != "presente_suspicion_infection":
            kept.append(r)
            continue
        f = ents[b]
        cand = label_ligne(f)
        if len(cand) == 1:
            lid, statut = cand[0][1], None
        elif len(cand) > 1:
            lid, statut = cand[0][1], "plusieurs_labels_sur_la_ligne"
        elif infectieux:
            lid, statut = min((dist(f, l), l["id"]) for l in infectieux)[1], "label_infectieux_hors_ligne_propose"
        else:
            c["V1_retiree_sans_label"] += 1
            journal.append((doc, page, "V1", f"patient -presente_suspicion_infection-> {f['value']['text']}",
                            "relation retiree : aucun LABEL infectieux sur la page"))
            revoir.append((doc, page, "foyer_sans_label_infectieux", f["value"]["text"], "",
                           "Rattacher a un LABEL d'une autre page ou laisser sans rattachement", ligne(txt, f)))
            continue
        lbl = ents[lid]
        key = (lid, b, "label_nosologique_a_pour_foyer")
        if key in existing:
            c["V1_doublon_evite"] += 1
            journal.append((doc, page, "V1", f"patient -> {f['value']['text']}", "retiree : le lien LABEL -> FOYER existe deja"))
            continue
        existing.add(key)
        r = dict(r, from_id=lid, to_id=b, labels=["label_nosologique_a_pour_foyer"], direction="right")
        kept.append(r)
        c["V1_convertie" + ("" if statut is None else "_a_revoir")] += 1
        journal.append((doc, page, "V1", f"patient -presente_suspicion_infection-> {f['value']['text']}",
                        f"-> '{lbl['value']['text']}' -label_nosologique_a_pour_foyer-> '{f['value']['text']}'"))
        if statut:
            revoir.append((doc, page, statut, f["value"]["text"], f"LABEL choisi : '{lbl['value']['text']}'",
                           "Verifier le LABEL dont ce foyer est la localisation", ligne(txt, f)))

    task["annotations"][0]["result"] = [r for r in res if r.get("type") != "relation" and r.get("id") not in retires] + kept
    c["taches"] += 1


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    tasks = json.loads(src.read_text(encoding="utf-8"))
    journal, revoir, c = [], [], Counter()
    avant = Counter(r.get("type") for t in tasks for r in t["annotations"][0]["result"])
    for t in tasks:
        corriger_tache(t, journal, revoir, c)
    apres = Counter(r.get("type") for t in tasks for r in t["annotations"][0]["result"])
    reste = sum(1 for t in tasks for r in t["annotations"][0]["result"]
                if r.get("type") == "relation" and (r.get("labels") or [""])[0] == "presente_suspicion_infection")
    assert reste == 0, reste
    importable = [{"data": t["data"], "annotations": [{"result": t["annotations"][0]["result"], "ground_truth": True}]}
                  for t in tasks]
    (out / "Annotation_49_Pdfs_v2.0_LabelStudio.json").write_text(
        json.dumps(importable, ensure_ascii=False, indent=1), encoding="utf-8")
    for name, header, rows in (
            ("journal_corrections_v2.0.csv", ("document", "page", "regle", "element", "modification"), journal),
            ("a_revoir_v2.0.csv", ("document", "page", "categorie", "foyer", "detail", "action_proposee", "ligne"), revoir)):
        with open(out / name, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(header)
            w.writerows(rows)
    print(f"Taches : {c['taches']} | entites {avant['labels']} -> {apres['labels']} | relations {avant['relation']} -> {apres['relation']}")
    for k, v in sorted(c.items()):
        if k != "taches":
            print(f"  {k:36} {v}")
    print(f"A revoir : {len(revoir)} lignes : {dict(Counter(r[2] for r in revoir))}")


if __name__ == "__main__":
    main()
