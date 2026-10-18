# -*- coding: utf-8 -*-
"""
Pre-annotation assistee par REGLES (aucun modele de langage) pour completer le gold selon le
guideline TRACE-Sepsis v1.7. Les propositions sont livrees comme PREDICTIONS Label Studio :
l'annotatrice les accepte, les corrige ou les supprime ; seule sa validation en fait le gold.

Usage :
    python guideline/suggerer_annotation_v1_7.py <export_label_studio.json> <dossier_sortie> [--integrer]
    --integrer : integre les suggestions S1-S3 validees dans l'annotation et retire les relations
                 hors signature (politique R5) ; S4 reste en prediction.
    --avec-biologie : (avec --integrer) integre aussi les biomarqueurs S4 valides.

Etapes :
  1. corrections automatisables v1.7 (corriger_annotation_v1_7.py) -> champ "annotations" ;
  2. suggestions, ajoutees a une copie de l'annotation corrigee -> champ "predictions" ;
     chaque region suggeree porte une note "SUGGESTION Sx" visible dans Label Studio.

Suggestions :
  S1  diagnostic + localisation dans la meme mention ("pneumopathie des lobes inferieurs") :
      LABEL_NOSOLOGIQUE reduit au diagnostic + FOYER_INFECTIEUX sur la localisation ;
      patient -> presente_suspicion_infection -> foyer ; relations germe / imagerie retirees
      a l'etape 1 rattachees au foyer.
  S2  relation germe / imagerie retiree a l'etape 1 sans localisation dans la mention :
      rattachee au FOYER_INFECTIEUX de la page s'il est unique.
  S3  diagnostic retire de la liste v1.7 mais ecrit dans les antecedents : propose en
      COMORBIDITE_ANTECEDENT ; encephalopathie hepatique proposee en DEFAILLANCE_ORGANE.
  S4  ligne de biologie (section biologie) "parametre valeur" non annotee : BIOMARQUEUR
      (parametre + valeur, sans l'intervalle de reference).
  S5  ligne d'ordonnance (traitement habituel, sortie) non annotee : TRAITEMENT + POSOLOGIE
      + traitement_a_pour_posologie.
"""
import copy
import csv
import importlib.util
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("corriger", HERE / "corriger_annotation_v1_7.py")
corr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(corr)

MODEL_VERSION = "suggestions_regles_guideline_v1.7"

SECTION_HEADERS = [
    (r"motif de l hospitalisation", "MOTIF"),
    (r"antecedents|medicaux|chirurgicaux|familiaux|allergies|mode de vie", "ANTECEDENTS"),
    (r"traitements? habituels?|medicaments|traitements? a l entree", "TRAITEMENT_HABITUEL"),
    (r"histoire de la maladie", "HISTOIRE"),
    (r"examen|signes generaux", "EXAMEN"),
    (r"biologie|gaz du sang|iono|prot sang|enzy|numeration|hemogramme|hemostase|formule"
     r"|fibrinogene|tca|temps de quick|examens? (sanguins|urinaires)|examens complementaires", "BIOLOGIE"),
    (r"evolution|prise en charge|sur le plan", "EVOLUTION"),
    (r"conclusion", "CONCLUSION"),
    (r"prescription de sortie|ordonnance de sortie", "SORTIE"),
]
SECTION_RE = [(re.compile(r"^(" + p + r")\b"), s) for p, s in SECTION_HEADERS]

HEAD = re.compile(r"^(?P<head>(?:foyer de )?(?:broncho-?)?(?:pneumopathies?|pneumonie|pavm|abc[eè]s|pyélonéphrite|"
                  r"pyelonephrite|érysipèle|erysipele|(?:pan)?sinusite|choc septique)"
                  r"(?:\s+(?:aigu[eë]?|communautaire|nosocomiale|d['’]\s?inhalation|abcédée|infectieuse|hypoxémiante|"
                  r"précoce|tardive|grave|sévère|chronique|multiloculée?|superficiel(?:le)?))*)", re.I)
CONNECTOR = re.compile(r"^\s*(?:à(?= point de d)|des|du|de la|de l['’]|de|aux|au|à la|en)?\s*", re.I)
LOC_WORD = re.compile(r"lobe|\blig\b|\blid\b|\blsd\b|\blsg\b|base|bilat|apical|apex|basal|droit|gauche|pulmonaire|"
                      r"point de d[ée]part|psoas|paroi|bras|membre|jambe|cuisse|maxillaire|sph[ée]no|frontal|"
                      r"ethmo|r[ée]nal|cutan|post[ée]ro|lat[ée]ro|inf[ée]rieur|sup[ée]rieur|moyen", re.I)
GERM_START = re.compile(r"^\s*à\s+(?!point)", re.I)

BIO_RE = re.compile(r"^(?P<lab>[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9 ./°()'’*+-]{1,40}?)\s+(?P<val>[<>]?-?\d+(?:[.,]\d+)?)"
                    r"(?P<unit>\s*(?:%|mmol/l|µmol/l|umol/l|mg/l|g/l|g/dl|ui/l|u/l|ng/ml|mmhg|meq/l|s|sec|giga/l|g/l))?", re.I)
BIO_SKIP = re.compile(r"^(t[ée]moins?|patient|fio2|peep|d[ée]bit|volume|axe|mode|vt|fr|le |la |les |du |de |il |elle |"
                      r"j\d|page|date|n°|age|âge|poids|taille)\b", re.I)
MED_SKIP = re.compile(r"^(m[ée]dicaments?|autres?|dans le service|aucun|ras|traitements?|prescriptions?|le |la |les |"
                      r"il |elle |patient|ordonnance|date|dr |docteur)\b", re.I)
# parametres de la liste BIOMARQUEUR du guideline v1.7 (avec abreviations usuelles)
BIO_LISTE = re.compile(r"^(lactates?|c\.?r\.?p\.?|prot[ée]ine c|procalciton|pct|cr[ée]at(?!ine kinase)|ur[ée]e|dfg|sodium|na\b|potassium|k\b|"
                       r"chlore|chlorure|calcium|phosph|magn[ée]sium|glyc[ée]mie|glucose|bili|asat|alat|sgot|sgpt|g\.?g\.?t|gamma|"
                       r"phosphatases? alc|pal\b|ldh|cpk|cr[ée]atine kinase|lipase|amylase|albumine|pr[ée]albumine|protides|prot[ée]ines totales|"
                       r"leucocytes|g\.?b\b|globules blancs|polynucl|pnn|neutrophiles|lymphocytes|monocytes|[ée]osinophiles|basophiles|"
                       r"h[ée]moglobine|hb\b|h[ée]matocrite|hte?\b|h[ée]maties|v\.?g\.?m|plaquettes|plq|tp\b|taux de prothrombine|tca\b|"
                       r"fibrinog|d-?dim|facteur|ph\b|pao2|pco2|paco2|po2|hco3|bicar|co2|sao2|troponine|bnp|nt-?probnp|cortisol|tsh|ferritine|"
                       r"triglyc|haptoglobine|schizocytes|r[ée]ticulocytes|prot[ée]inurie|natriur|ammoni)", re.I)
REGLAGE = re.compile(r":|r[ée]glage|temps|type|rapport|pente|alarme|alrme|dur[ée]e|fr[ée]quence|\bfr\b|fio2|ventilat|ipap|epap|mode|"
                     r"trigger|volume|pression|d[ée]bit", re.I)
DOSE_START = re.compile(r"\s(?=\d|PO\b|SC\b|IV\b|si besoin|jusqu|matin|soir|\d-\d-\d)", re.I)


def norm(text):
    text = unicodedata.normalize("NFD", str(text or "").lower())
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")


def note(region, rule, why):
    region["meta"] = {"text": [f"SUGGESTION {rule} (regles guideline v1.7) : {why}"]}
    return region


def ent(rid, start, end, text, label, rule, why):
    return note({"value": {"start": start, "end": end, "text": text, "labels": [label]}, "id": rid,
                 "from_name": "label", "to_name": "text", "type": "labels", "origin": "prediction"}, rule, why)


def rel(a, b, label):
    return {"from_id": a, "to_id": b, "type": "relation", "direction": "right", "labels": [label]}


def overlaps(regions, start, end):
    return any(r["value"]["start"] < end and start < r["value"]["end"] for r in regions)


def suggerer(task, sig, section_in, rows, c):
    text = task["data"].get("text", "")
    doc, page = task["data"].get("document", ""), task["data"].get("page", "")
    pred = copy.deepcopy(task["annotations"][0]["result"])
    ents = {r["id"]: r for r in pred if r.get("type") == "labels"}
    rels = [r for r in pred if r.get("type") == "relation"]
    lab = lambda i: ents[i]["value"]["labels"][0] if i in ents else None
    patient = next((i for i, r in ents.items() if lab(i) == "DONNEE_PATIENT"), None)
    new_ents, new_rels = [], []
    n_id = [0]

    def nid(prefix):
        n_id[0] += 1
        return f"{prefix}{n_id[0]}"

    def add_rel(a, b, label, rule, why):
        if sig.get(label) != (lab(a) or kind.get(a), lab(b) or kind.get(b)):
            return False
        if any(r["from_id"] == a and r["to_id"] == b and r["labels"][0] == label for r in rels + new_rels):
            return False
        new_rels.append(rel(a, b, label))
        rows.append((doc, page, rule, f"relation {label}", why))
        c[f"{rule}_relation"] += 1
        return True

    kind = {}
    dropped = task.get("_dropped", [])
    reattached = set()

    # ---- S1 : separer diagnostic et localisation
    for i, r in list(ents.items()):
        if lab(i) != "LABEL_NOSOLOGIQUE":
            continue
        t = r["value"]["text"]
        m = HEAD.match(t)
        if not m:
            continue
        rest = t[m.end():]
        if not rest.strip() or GERM_START.match(rest):
            continue
        cut = re.split(r"[,;(]|\bavec\b|\bsur\b|\bcompliqu|\s+à\s+(?!point)", rest, maxsplit=1)[0]
        lead = CONNECTOR.match(cut).end()
        loc = re.sub(r"(?:\s+(?:aigu[eë]?|communautaire|nosocomiale|chronique|hypox[ée]miante|grave|s[ée]v[eè]re))+$", "", cut[lead:].rstrip(" ."), flags=re.I)
        if len(loc) < 3 or not LOC_WORD.search(loc):
            continue
        s0 = r["value"]["start"]
        ls = s0 + m.end() + lead
        le = ls + len(loc)
        if text[ls:le] != loc:
            continue
        head = m.group("head")
        r["value"]["end"] = s0 + len(head)
        r["value"]["text"] = head
        note(r, "S1", f"diagnostic separe de sa localisation (mention d'origine : « {t} »)")
        fid = nid("s1f")
        kind[fid] = "FOYER_INFECTIEUX"
        new_ents.append(ent(fid, ls, le, loc, "FOYER_INFECTIEUX", "S1", f"localisation du diagnostic « {head} »"))
        rows.append((doc, page, "S1", f"{t} -> LABEL « {head} » + FOYER « {loc} »", "separation diagnostic / localisation"))
        c["S1_separation"] += 1
        if patient and any(x["from_id"] == patient and x["to_id"] == i for x in rels):
            add_rel(patient, fid, "presente_suspicion_infection", "S1", "patient -> localisation")
        for d in dropped:
            if d["to_id"] == i and d["labels"][0] in ("micro_organisme_isole_dans", "imagerie_objective_foyer"):
                if add_rel(d["from_id"], fid, d["labels"][0], "S1", "relation retiree rattachee a la localisation"):
                    reattached.add(id(d))

    # ---- S2 : rattacher au foyer unique de la page
    foyers = [i for i in ents if lab(i) == "FOYER_INFECTIEUX"] + [e["id"] for e in new_ents if e["value"]["labels"][0] == "FOYER_INFECTIEUX"]
    if len(foyers) == 1:
        for d in dropped:
            if id(d) not in reattached and d["labels"][0] in ("micro_organisme_isole_dans", "imagerie_objective_foyer") \
                    and d["from_id"] in ents:
                add_rel(d["from_id"], foyers[0], d["labels"][0], "S2", "relation retiree rattachee au foyer unique de la page")

    # ---- sections ligne par ligne (S3 a S5)
    section = section_in
    line_sections = []
    for m in re.finditer(r"[^\n]+", text):
        n = norm(m.group()).strip()
        if n and len(n) <= 60:
            for rx, sec in SECTION_RE:
                if rx.match(n):
                    section = sec
                    break
        line_sections.append((m.start(), m.end(), section, m.group()))

    def section_at(pos):
        cur = section_in
        for s, e, sec, _ in line_sections:
            if s <= pos:
                cur = sec
        return cur

    # ---- S3 : diagnostics retires -> retypage propose
    for regle, r in task.get("_removed", []):
        if regle != "G3":
            continue
        t, st = r["value"]["text"], r["value"]["start"]
        new = None
        if section_at(st) == "ANTECEDENTS" or re.search(r"ant[ée]c[ée]dent", text[max(0, st - 120):st], re.I):
            new = "COMORBIDITE_ANTECEDENT"
        elif re.search(r"enc[ée]phalopathie", t, re.I):
            new = "DEFAILLANCE_ORGANE"
        if new and not overlaps(list(ents.values()) + new_ents, st, r["value"]["end"]):
            e2 = ent(nid("s3e"), st, r["value"]["end"], t, new, "S3", f"diagnostic retire de la liste v1.7, propose en {new}")
            new_ents.append(e2)
            kind[e2["id"]] = new
            rows.append((doc, page, "S3", f"{t} -> {new}", "retypage au lieu de la suppression"))
            c["S3_retypage"] += 1

    # ---- S4 / S5 : lignes de biologie et d'ordonnance non annotees
    regions = list(ents.values()) + new_ents
    for s, e, sec, line in line_sections:
        raw = line.strip()
        off = s + (len(line) - len(line.lstrip()))
        if not raw or raw.endswith(":"):
            continue
        if sec == "BIOLOGIE" and len(raw) <= 80 and not BIO_SKIP.match(raw):
            m = BIO_RE.match(raw)
            if m and BIO_LISTE.match(raw) and not overlaps(regions, off, off + len(raw)):
                span = raw[:m.end()].rstrip()
                e2 = ent(nid("s4b"), off, off + len(span), span, "BIOMARQUEUR", "S4", "ligne de biologie non annotee")
                new_ents.append(e2)
                regions.append(e2)
                rows.append((doc, page, "S4", span, "biomarqueur"))
                c["S4_biomarqueur"] += 1
        elif sec in ("TRAITEMENT_HABITUEL", "SORTIE") and 3 <= len(raw) <= 90 and re.match(r"^[A-Za-zÀ-ÿ]", raw) \
                and not MED_SKIP.match(raw) and not overlaps(regions, off, off + len(raw)):
            parts = DOSE_START.split(raw, maxsplit=1)
            drug = parts[0].strip(" ,;-")
            dose = parts[1].strip() if len(parts) > 1 else ""
            if len(drug) < 3 or len(drug.split()) > 4 or not dose or not re.search(r"\d", dose) or REGLAGE.search(drug):
                continue
            ds = off + raw.index(drug)
            ps = off + raw.index(dose, len(drug))
            if text[ds:ds + len(drug)] != drug or text[ps:ps + len(dose)] != dose:
                continue
            t_id, p_id = nid("s5t"), nid("s5p")
            kind[t_id], kind[p_id] = "TRAITEMENT", "POSOLOGIE"
            for e2 in (ent(t_id, ds, ds + len(drug), drug, "TRAITEMENT", "S5", "ligne d'ordonnance non annotee"),
                       ent(p_id, ps, ps + len(dose), dose, "POSOLOGIE", "S5", f"posologie de « {drug} »")):
                new_ents.append(e2)
                regions.append(e2)
            add_rel(t_id, p_id, "traitement_a_pour_posologie", "S5", "traitement -> posologie sur la meme ligne")
            rows.append((doc, page, "S5", f"{drug} | {dose}", "traitement + posologie"))
            c["S5_ordonnance"] += 1

    task["predictions"] = [{"model_version": MODEL_VERSION, "result": pred + new_ents + new_rels}]
    c["suggestions_entites"] += len(new_ents)
    return section


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 2:
        sys.exit(__doc__)
    src, out = Path(args[0]), Path(args[1])
    out.mkdir(parents=True, exist_ok=True)
    tasks = json.loads(src.read_text(encoding="utf-8"))
    sig, journal, revoir, c1 = corr.signatures(), [], [], Counter()
    for t in tasks:
        corr.corriger_tache(t, sig, journal, revoir, c1)
    order = sorted(range(len(tasks)), key=lambda k: (tasks[k]["data"].get("document", ""), int(str(tasks[k]["data"].get("page", "0")) or 0)))
    rows, c, section, last_doc = [], Counter(), "DEBUT", None
    for k in order:
        t = tasks[k]
        if t["data"].get("document") != last_doc:
            section, last_doc = "DEBUT", t["data"].get("document")
        section = suggerer(t, sig, section, rows, c)
    if "--integrer" in sys.argv:
        # validation de l'annotatrice : S1-S3 integrees ; relations hors signature retirees (politique R5) ;
        # S4 (biologie) laisse en prediction a valider
        fin_rows = []
        for t in tasks:
            res = t["predictions"][0]["result"]
            avec_bio = "--avec-biologie" in sys.argv
            keep = [r for r in res if avec_bio or not (r.get("type") == "labels" and str(r.get("id", "")).startswith("s4"))]
            ids = {r["id"]: r["value"]["labels"][0] for r in keep if r.get("type") == "labels"}
            final = []
            for r in keep:
                if r.get("type") == "relation":
                    lab = (r.get("labels") or [""])[0]
                    if r["from_id"] not in ids or r["to_id"] not in ids:
                        continue
                    if sig.get(lab) != (ids[r["from_id"]], ids[r["to_id"]]):
                        fin_rows.append((t["data"].get("document"), t["data"].get("page"), "R5", lab, "relation hors signature retiree"))
                        continue
                else:
                    r = copy.deepcopy(r)
                    if "meta" in r:
                        fin_rows.append((t["data"].get("document"), t["data"].get("page"), "VALIDE",
                                         r["value"]["text"], r["meta"]["text"][0]))
                        r.pop("meta")
                        r["origin"] = "manual"
                final.append(r)
            t["annotations"][0]["result"] = final
            s4 = [] if avec_bio else [r for r in res if r.get("type") == "labels" and str(r.get("id", "")).startswith("s4")]
            t["predictions"] = [{"model_version": MODEL_VERSION + "_biologie_a_valider",
                                 "result": copy.deepcopy(final) + s4}] if s4 else []
        journal += [(d, p_, r_, e, m) for d, p_, r_, e, m in fin_rows]
        c["integre_R5_relations_retirees"] = sum(1 for x in fin_rows if x[2] == "R5")
    importable = [{"data": t["data"],
                   "annotations": [{"result": t["annotations"][0]["result"], "ground_truth": True}],
                   "predictions": t["predictions"]} for t in tasks]
    name = "Annotation_49_Pdfs_v1.7_FINALE_LabelStudio.json" if "--integrer" in sys.argv else "Annotation_49_Pdfs_v1.7_avec_suggestions_LabelStudio.json"
    (out / name).write_text(
        json.dumps(importable, ensure_ascii=False, indent=1), encoding="utf-8")
    for name, header, data in (("journal_corrections_v1.7.csv", ("document", "page", "regle", "element", "modification"), journal),
                               ("a_revoir_v1.7.csv", ("document", "page", "categorie", "element", "action_proposee"), revoir),
                               ("suggestions_v1.7.csv", ("document", "page", "regle", "element", "nature"), rows)):
        with open(out / name, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(header)
            w.writerows(data)
    print("Corrections :", dict(sorted((k, v) for k, v in c1.items() if k != "taches")))
    print("Suggestions :", dict(sorted(c.items())))


if __name__ == "__main__":
    main()
