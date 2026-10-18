# -*- coding: utf-8 -*-
"""
Applique a l'export Label Studio du gold les corrections AUTOMATISABLES du guideline
TRACE-Sepsis v1.7 et produit un fichier importable dans Label Studio.

Usage :
    python guideline/corriger_annotation_v1_7.py <export_label_studio.json> <dossier_sortie>

Sorties (dans <dossier_sortie>) :
    Annotation_49_Pdfs_v1.7_LabelStudio.json   taches + annotations corrigees (import Label Studio)
    journal_corrections_v1.7.csv               chaque modification appliquee
    a_revoir_v1.7.csv                          cas qui demandent un jugement humain

Regles appliquees (toutes tirees du guideline v1.7, aucune sortie de modele n'est lue) :
  G1  pneumopathie, abces, pyelonephrite, erysipele, sinusite typees FOYER_INFECTIEUX
      -> LABEL_NOSOLOGIQUE (diagnostics ; le foyer ne represente que la localisation)
  G2  presente_suspicion_infection (patient -> diagnostic retype en G1) -> a_pour_label_nosologique
  G3  LABEL_NOSOLOGIQUE hors liste v1.7 (ACFA, flutter, AVC, SIADH, MAT, SHU, myasthenie,
      encephalopathie hepatique, etat de mal epileptique, syndrome hepato-renal) : retire
  G4  SCORE_NEUROLOGIQUE score myasthenique : retire
  G5  SYMPTOME retires de la liste v1.7 (dysphonie, mastication, mandibule, hypersalivation,
      hoquet, convulsions, trismus, myosis, mydriase, anisocorie, ptosis, oedemes) : retire
  G6  IMAGERIE_PROCEDURE myelogramme : retire
  G7  relations imagerie_objective_defaillance et imagerie_objective_comorbidite (retirees du
      schema v1.7) : retirees
  G8  relation devenue hors signature apres G1 : retiree et listee a revoir
  Une entite retiree emporte ses relations.

Non automatisable (liste a revoir) : localisation a separer d'un diagnostic, stade d'IRA
ecrit (relation ira_a_pour_stade), relations deja hors signature dans l'export.
"""
import csv
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

GUIDELINE = Path(__file__).resolve().parent / "Guideline_TRACE_Sepsis_v1.7.json"

DIAG_FOYER = re.compile(r"pneumopathie|pneumonie|\bpavm\b|pleuropneumo|bronchopneumo|broncho-pneumo|"
                        r"\babces\b|abcede|pyelonephrite|\bpna\b|erysipele|sinusite")
LABEL_RETIRES = re.compile(r"\bacfa\b|flutter|\bsiadh\b|\bavc\b|\bmat\b|\bshu\b|myasth|encephalopathie hepatique"
                           r"|etat de mal|hepato.?renal")
SCORE_RETIRE = re.compile(r"myasth")
SYMPTOME_RETIRES = re.compile(r"dysphonie|mastication|mandibule|hypersalivation|hoquet|convuls|trismus|myosis|"
                              r"mydriase|anisocorie|ptosis|oedeme|œdeme")
IMAGERIE_RETIREE = re.compile(r"myelogramme")
RELATIONS_RETIREES = {"imagerie_objective_defaillance", "imagerie_objective_comorbidite"}
LOCALISATION = re.compile(r"point de depart|lobe|\blig\b|\blid\b|\blsd\b|\blsg\b|base|bilateral|apical|basal|"
                          r"droit|gauche|pulmonaire|renal|cutane|membre|maxillaire|frontal")
STADE_IRA = re.compile(r"(\bira\b|insuffisance renale aigue|\baki\b)[^.\n]{0,60}?(stade|kdigo)\s*([123]|i{1,3}\b)")


def norm(text):
    text = unicodedata.normalize("NFD", str(text or "").lower())
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")


def signatures():
    g = json.loads(GUIDELINE.read_text(encoding="utf-8"))["ontologie_sepsis_graph"]
    return {k: (v["domaine"], v["image"]) for k, v in g["signatures_relations"].items()}


def corriger_tache(task, sig, journal, revoir, c):
    doc, page = task["data"].get("document", ""), task["data"].get("page", "")
    ann = task["annotations"][0]
    ents = {r["id"]: r for r in ann["result"] if r.get("type") == "labels"}
    rels = [r for r in ann["result"] if r.get("type") == "relation"]
    retirees, retypees = set(), set()

    for eid, r in ents.items():
        lab, txt = r["value"]["labels"][0], r["value"].get("text", "")
        n = norm(txt)
        regle = None
        if lab == "FOYER_INFECTIEUX" and DIAG_FOYER.search(n):
            r["value"]["labels"] = ["LABEL_NOSOLOGIQUE"]
            retypees.add(eid)
            c["G1_foyer_vers_label"] += 1
            journal.append((doc, page, "G1", txt, "FOYER_INFECTIEUX -> LABEL_NOSOLOGIQUE"))
            if len(txt) > 40:
                revoir.append((doc, page, "typage_a_verifier", txt,
                               "Mention longue retypee en LABEL_NOSOLOGIQUE : verifier le typage et la frontiere"))
            elif LOCALISATION.search(n):
                revoir.append((doc, page, "localisation_a_separer", txt,
                               "Creer une entite FOYER_INFECTIEUX sur la localisation ecrite"))
            continue
        if lab == "LABEL_NOSOLOGIQUE" and LABEL_RETIRES.search(n):
            if len(txt) > 40:                    # mention longue : le terme retire n'est peut-etre pas le concept principal
                revoir.append((doc, page, "label_a_verifier", txt,
                               "Contient un diagnostic retire de la liste v1.7 : garder, retyper ou retirer"))
                continue
            regle = "G3"
        elif lab == "SCORE_NEUROLOGIQUE" and SCORE_RETIRE.search(n):
            regle = "G4"
        elif lab == "SYMPTOME" and SYMPTOME_RETIRES.search(n):
            regle = "G5"
        elif lab == "IMAGERIE_PROCEDURE" and IMAGERIE_RETIREE.search(n):
            regle = "G6"
        if regle:
            retirees.add(eid)
            c[f"{regle}_entite_retiree"] += 1
            journal.append((doc, page, regle, txt, f"{lab} hors liste v1.7 : retire"))
            if regle == "G3":
                revoir.append((doc, page, "label_retire", txt,
                               "Verifier s'il faut le retyper (antecedent -> COMORBIDITE_ANTECEDENT, encephalopathie -> DEFAILLANCE_ORGANE)"))
        elif lab == "LABEL_NOSOLOGIQUE" and "point de depart" in n:
            revoir.append((doc, page, "localisation_a_separer", txt,
                           "Separer LABEL (ex. 'choc septique') et FOYER_INFECTIEUX ('point de depart ...')"))

    for m in STADE_IRA.finditer(norm(task["data"].get("text", ""))):
        revoir.append((doc, page, "stade_ira_a_annoter", task["data"]["text"][m.start():m.end()],
                       "Annoter STADE_IRA et la relation ira_a_pour_stade"))

    def label(eid):
        return ents[eid]["value"]["labels"][0] if eid in ents else None

    kept, seen = [], set()
    for r in rels:
        a, b, rel = r.get("from_id"), r.get("to_id"), (r.get("labels") or [""])[0]
        txt = f"{ents.get(a, {}).get('value', {}).get('text', a)} -{rel}-> {ents.get(b, {}).get('value', {}).get('text', b)}"
        if a in retirees or b in retirees:
            c["relations_retirees_avec_entite"] += 1
            continue
        if rel in RELATIONS_RETIREES:
            c["G7_relation_imagerie_retiree"] += 1
            journal.append((doc, page, "G7", txt, "relation retiree du schema v1.7"))
            continue
        touchee = a in retypees or b in retypees
        if touchee and rel == "presente_suspicion_infection" and label(a) == "DONNEE_PATIENT":
            r["labels"] = ["a_pour_label_nosologique"]
            rel = "a_pour_label_nosologique"
            c["G2_suspicion_vers_label"] += 1
            journal.append((doc, page, "G2", txt, "presente_suspicion_infection -> a_pour_label_nosologique"))
        valide = sig.get(rel) == (label(a), label(b))
        if touchee and not valide:
            c["G8_relation_hors_signature_retiree"] += 1
            journal.append((doc, page, "G8", txt, "signature invalide apres retypage : retiree"))
            revoir.append((doc, page, "relation_retiree", txt,
                           "Rattacher a la localisation ecrite (FOYER_INFECTIEUX) si elle existe"))
            continue
        key = (a, b, rel)
        if touchee and key in seen:
            c["doublons_crees_par_G2_retires"] += 1
            continue
        seen.add(key)
        if not valide:
            revoir.append((doc, page, "relation_hors_signature_existante",
                           f"{txt} ({label(a)} -> {label(b)})", "Deja hors signature : retyper une extremite ou retirer"))
        kept.append(r)

    ann["result"] = [r for r in ann["result"] if r.get("type") != "relation" and r.get("id") not in retirees] + kept
    c["taches"] += 1


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    tasks = json.loads(src.read_text(encoding="utf-8"))
    sig, journal, revoir, c = signatures(), [], [], Counter()
    avant = Counter(r.get("type") for t in tasks for r in t["annotations"][0]["result"])
    for t in tasks:
        corriger_tache(t, sig, journal, revoir, c)
    apres = Counter(r.get("type") for t in tasks for r in t["annotations"][0]["result"])
    # format d'import Label Studio : donnees + annotation (sans identifiants internes du projet d'origine)
    importable = [{"data": t["data"],
                   "annotations": [{"result": t["annotations"][0]["result"], "ground_truth": True}]}
                  for t in tasks]
    (out / "Annotation_49_Pdfs_v1.7_LabelStudio.json").write_text(
        json.dumps(importable, ensure_ascii=False, indent=1), encoding="utf-8")
    for name, header, rows in (("journal_corrections_v1.7.csv", ("document", "page", "regle", "element", "modification"), journal),
                               ("a_revoir_v1.7.csv", ("document", "page", "categorie", "element", "action_proposee"), revoir)):
        with open(out / name, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(header)
            w.writerows(rows)
    print(f"Taches : {c['taches']} | entites {avant['labels']} -> {apres['labels']} | relations {avant['relation']} -> {apres['relation']}")
    for k, v in sorted(c.items()):
        if k != "taches":
            print(f"  {k:40} {v}")
    print(f"A revoir : {len(revoir)} lignes : {dict(Counter(r[2] for r in revoir))}")


if __name__ == "__main__":
    main()
