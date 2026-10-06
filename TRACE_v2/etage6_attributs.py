# -*- coding: utf-8 -*-
"""
ETAGE 6 - ATTRIBUTS CLINIQUES
Seule responsabilite : qualifier chaque entite, en une passe et avec le meme decoupage du
texte (Document : lignes, sections). Il ANNOTE, il ne retire rien.

  T1 valeur/unite   BIOMARQUEUR, SIGNE_VITAL, POSOLOGIE, SCORE_* sans unite : si le nom de
                    l'entite contient "<nombre> <unite>", l'unite est renseignee (champ
                    `unite`) - la seule modification de contenu de cet etage ;
  T2 temporalite    ANTERIEUR (antecedents, traitements habituels), SORTIE (prescription de
                    sortie) ou SEJOUR, d'apres la section ou l'entite est citee ;
  T3 negation       un indice de negation ("pas de", "absence de", "elimine"...) precede la
                    mention dans le texte, ou l'extraction l'a marquee nie=True ;
  T4 hypothese      un indice d'incertitude ("suspicion de", "probable", "a discuter"...).

Resultat dans entite.trace_v2.attributs.
"""
import re
import sys
from collections import Counter

from trace_lib import config as C
from trace_lib.documents import Graph, trace
from trace_lib.etage import run_stage
from trace_lib.texte import load_source

NUMERIC_TYPES = {"BIOMARQUEUR", "SIGNE_VITAL", "POSOLOGIE", "SCORE_SOFA", "SCORE_QSOFA", "SCORE_NEUROLOGIQUE"}
UNITS = (r"mmol/l|µmol/l|μmol/l|micromol/l|g/dl|g/l|mg/l|mg/dl|ng/ml|ui/l|u/l|meq/l|mmhg|kpa|cmh2o"
         r"|bpm|/min|°c|%|mg/kg/h|mg/h|µg/kg/min|μg/kg/min|µg/h|μg/h|ml/h|l/min|mg|µg|μg|g|ml|l|ui")
VALUE_UNIT_RE = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)\s*(" + UNITS + r")(?![a-z])", re.IGNORECASE)
TIME_SECTIONS = {"ANTECEDENTS": "ANTERIEUR", "TRAITEMENT_HABITUEL": "ANTERIEUR", "SORTIE": "SORTIE"}


def process(path, data):
    c = Counter()
    g, doc = Graph(data), load_source(data, path)
    for e in g.entities.values():
        name = g.entity_name(e)
        att = {}

        if g.entity_type(e) in NUMERIC_TYPES and not e.get("unite"):
            m = VALUE_UNIT_RE.search(name)
            if m:
                e["unite"] = m.group(2)
                att["unite_renseignee"] = {"valeur": m.group(1), "unite": m.group(2)}
                c["T1_unites_renseignees"] += 1

        pos = doc.find_exact(name) or doc.locate(name)
        section = doc.section_at(pos[0] if pos else None)
        att["section"] = section
        att["temporalite"] = TIME_SECTIONS.get(section, "SEJOUR")
        c[f"T2_{att['temporalite']}"] += 1

        neg, hyp = doc.cues_before(name)
        att["negation"] = neg or e.get("nie") is True
        att["hypothese"] = hyp
        c["T3_negation"] += att["negation"]
        c["T4_hypothese"] += hyp
        trace(e, "attributs", att)
    return c


def main(in_dir=None):
    run_stage(6, "ATTRIBUTS CLINIQUES", in_dir or C.STAGE_DIRS[5], process)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
