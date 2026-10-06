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

Une entite n'est ajoutee que si aucune entite de meme type de la page ne la recouvre deja.
Elle est ajoutee a pages[] (mention) et a global_entities (noeud), sans relation.

Mesure (43 documents, documents pairs et impairs separement) : F1 entites +0,4 point sur
chaque moitie. Ecarte : dupliquer une entite pour chaque occurrence dans le texte
(+1061 entites, precision -5 points, F1 en baisse).
"""
import copy
import re
import sys
from collections import Counter

from trace_lib import config as C
from trace_lib.documents import Graph, trace
from trace_lib.etage import run_stage
from trace_lib.texte import iter_page_lines, norm

BIO_RE = re.compile(r"^([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9 ./°()'’*+-]{1,40}?)\s+([<>]?-?\d+(?:[.,]\d+)?)(?:\s+.*)?$")
MED_SKIP = re.compile(r"^(m[ée]dicaments?|autres?|dans le service|aucun|ras|traitements?)\b", re.I)
DOSE_START = re.compile(r"\s(?=\d|PO\b|SC\b|IV\b|si besoin|jusqu|matin|soir|\d-\d-\d)", re.I)


def _covered(page_entities, name, types):
    n = norm(name)
    for e in page_entities:
        if str(e.get("type") or e.get("categorie") or "").upper() not in types:
            continue
        en = norm(Graph.mention(e))
        if len(en) >= 3 and (en in n or n in en):
            return True
    return False


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
    c[f"{rule}_{etype}"] += 1


def process(path, data):
    c = Counter()
    g = Graph(data)
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
            if len(drug) >= 3 and len(drug.split()) <= 4 and not _covered(ents, drug, {"TRAITEMENT"}):
                _add(g, page, key, drug, "TRAITEMENT", "B2", c)
            if dose and re.search(r"\d", dose) and not _covered(ents, dose, {"POSOLOGIE"}):
                _add(g, page, key, dose, "POSOLOGIE", "B2", c)
    c["entites_page_sortie"] = len(g.page_entities())
    return c


def main(in_dir=None):
    run_stage("4b", "RECUPERATION STRUCTUREE", in_dir or C.STAGE_DIRS[4], process)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
