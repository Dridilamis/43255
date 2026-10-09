# -*- coding: utf-8 -*-
"""
ETAGE 4b - RECUPERATION STRUCTUREE (rappel)
Seule responsabilite : ajouter les entites que le LLM a oubliees dans les blocs du compte
rendu dont la forme est fixe. Rien n'est invente : chaque entite ajoutee est un morceau
de ligne copie du texte de sa page (elle passe donc la regle E1 de l'Etage 7).

  B1  biologie (section BIOLOGIE_IMAGERIE) : une ligne "libelle valeur [norme] [unite]",
      ex. "Leucocytes 40.8 4.0-10.0 x10*9/L"  -> BIOMARQUEUR (la ligne entiere) ;
  B2  ordonnances (TRAITEMENT_HABITUEL, SORTIE) : une ligne "medicament posologie",
      ex. "Tahor 10mg 0-0-1" -> TRAITEMENT "Tahor" et POSOLOGIE "10mg 0-0-1".
  B3  sur une ligne d'ordonnance, relie le traitement a sa posologie
      (traitement_a_pour_posologie), preuve = la ligne ;
  B4  (desactive, LINK_PATIENT) relierait le traitement au patient (traitement_administre_a).
  B3 s'applique au traitement et a la posologie de la ligne, qu'ils viennent du LLM ou de
  B2, et seulement si la relation n'existe pas deja (memes extremites).

Une entite n'est ajoutee que si aucune entite de meme type de la page ne la recouvre deja.
Elle est ajoutee a pages[] (mention) et a global_entities (noeud).

Mesure (43 documents, documents pairs et impairs separement) : F1 entites +0,4 point sur
chaque moitie. B3 : 128 relations ajoutees, 53 justes (41 %) ; F1 relations en sortie
d'etage 62,38 -> 62,66 % (pairs 64,41 -> 64,80, impairs 59,82 -> 59,93). B4 ecarte :
139 relations, 23 justes (17 %), F1 relations en baisse. Ecarte : dupliquer une entite pour chaque occurrence dans le texte
(+1061 entites, precision -5 points, F1 en baisse).
"""
import copy
import re
import sys
from collections import Counter

from trace_lib import config as C
from trace_lib.documents import PATIENT_RE, Graph, trace
from trace_lib.etage import run_stage
from trace_lib.texte import iter_page_lines, norm

BIO_RE = re.compile(r"^([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9 ./°()'’*+-]{1,40}?)\s+([<>]?-?\d+(?:[.,]\d+)?)(?:\s+.*)?$")
MED_SKIP = re.compile(r"^(m[ée]dicaments?|autres?|dans le service|aucun|ras|traitements?|prescriptions?)\b", re.I)
LINK_POSOLOGY = True
LINK_PATIENT = False
DOSE_START = re.compile(r"\s(?=\d|PO\b|SC\b|IV\b|si besoin|jusqu|matin|soir|\d-\d-\d)", re.I)


def _covering(page_entities, name, types):
    """Entite de la page, d'un des types, qui recouvre `name` (ou None)."""
    n = norm(name)
    for e in page_entities:
        if str(e.get("type") or e.get("categorie") or "").upper() not in types:
            continue
        en = norm(Graph.mention(e))
        if len(en) >= 3 and (en in n or n in en):
            return e
    return None


def _covered(page_entities, name, types):
    return _covering(page_entities, name, types) is not None


def _link(g, page, subj, rel_type, obj, line, rule, c):
    """Ajoute la relation subj -rel_type-> obj si elle n'existe pas deja."""
    sid, oid = subj.get("identifiant_entite"), obj.get("identifiant_entite")
    if not sid or not oid or sid not in g.entities or oid not in g.entities:
        return
    for r in g.relations:
        if r.get("type_relation") != rel_type or r.get("identifiant_entite_sujet") != sid:
            continue
        o, on = g.endpoint(r, "object")
        if r.get("identifiant_entite_objet") == oid or norm(on) == norm(g.entity_name(obj)) \
                or (g.is_patient(obj) and g.is_patient(o, on)):
            return
    num = sum(1 for r in g.relations if str(r.get("identifiant_relation", "")).startswith("R_B")) + 1
    rel = {"identifiant_relation": f"R_B{num:04d}", "identifiant_entite_sujet": sid,
           "entite_sujet": g.entity_name(subj), "type_relation": rel_type,
           "identifiant_entite_objet": oid, "entite_objet": g.entity_name(obj),
           "preuve": line, "type_inference": "recuperation_structuree", "confiance": "elevee",
           "page": page.get("page")}
    trace(rel, "recuperation", rule)
    g.relations.append(rel)
    c[f"{rule}_{rel_type}"] += 1


def _add(g, page, key, name, etype, rule, c):
    ents = page[key]
    num = sum(1 for e in ents if str(e.get("identifiant_entite", "")).startswith(f"P{page.get('page')}_B")) + 1
    e = {"identifiant_entite": f"P{page.get('page')}_B{num:03d}", "name": name, "preuve": name,
         "type": etype, "categorie": etype, "page": page.get("page"), "nie": False,
         "confiance": "elevee", "type_inference": "recuperation_structuree"}
    trace(e, "recuperation", rule)
    trace(e, "ancrage", {"atteste": True, "mot_pour_mot": True})
    ents.append(e)
    g.data["global_entities"].append(copy.deepcopy(e))
    g.entities[e["identifiant_entite"]] = g.data["global_entities"][-1]
    c[f"{rule}_{etype}"] += 1
    return e


def process(path, data):
    c = Counter()
    g = Graph(data)
    patient = next((e for e in g.entities.values() if PATIENT_RE.match(norm(g.entity_name(e)))), None)
    for page, section, line in iter_page_lines(data.get("pages")):
        key = "entities" if isinstance(page.get("entities"), list) else "entites"
        ents = page.setdefault(key, [])
        if line.endswith(":"):
            continue
        if section == "BIOLOGIE_IMAGERIE" and len(line) <= 80 and BIO_RE.match(line):
            if not _covered(ents, line, {"BIOMARQUEUR", "SIGNE_VITAL"}):
                _add(g, page, key, line, "BIOMARQUEUR", "B1", c)
        elif section in ("TRAITEMENT_HABITUEL", "SORTIE") and 3 <= len(line) <= 90 \
                and re.match(r"^[A-Za-zÀ-ÿ]", line) and not MED_SKIP.match(line):
            parts = DOSE_START.split(line, maxsplit=1)
            drug = parts[0].strip(" ,;-")
            dose = parts[1].strip() if len(parts) > 1 else ""
            treat = dosage = None
            if len(drug) >= 3 and len(drug.split()) <= 4:
                treat = _covering(ents, drug, {"TRAITEMENT"}) or _add(g, page, key, drug, "TRAITEMENT", "B2", c)
            if dose and re.search(r"\d", dose):
                dosage = _covering(ents, dose, {"POSOLOGIE"}) or _add(g, page, key, dose, "POSOLOGIE", "B2", c)
            if LINK_POSOLOGY and treat and dosage:
                _link(g, page, treat, "traitement_a_pour_posologie", dosage, line, "B3", c)
            if LINK_PATIENT and treat and patient:
                _link(g, page, treat, "traitement_administre_a", patient, line, "B4", c)
    c["entites_page_sortie"] = len(g.page_entities())
    c["relations_sortie"] = len(g.relations)
    return c


def main(in_dir=None):
    run_stage("4b", "RECUPERATION STRUCTUREE", in_dir or C.STAGE_DIRS[4], process)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
