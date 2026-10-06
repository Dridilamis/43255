# -*- coding: utf-8 -*-
"""
ETAGE 2 - ANCRAGE DOCUMENTAIRE
Seule responsabilite : confronter chaque relation au texte source du compte rendu.

Pour chaque relation, il ecrit trace_v2.ancrage :
  sujet_atteste / objet_atteste   l'extremite figure-t-elle dans le texte ? (patient : oui)
  preuve      ATTESTEE | INVENTEE | ABSENTE | NOTE_SYSTEME
  distance    PATIENT | LIGNE | PARAGRAPHE | LOIN | INTROUVABLE
  section     section du compte rendu ou la relation est citee

Il retire SEULEMENT ce que le document rend impossible (pas un jugement de pertinence) :
  A1  une extremite (hors patient) n'existe pas dans le texte        -> entite inventee
  A2  la citation de preuve n'existe pas dans le texte               -> preuve inventee
  A3  les deux extremites n'apparaissent jamais a moins de 300 car.  -> lien invente
Tout le reste est decide a l'Etage 7.
"""
import re
import sys
from collections import Counter

from trace_lib import config as C
from trace_lib.documents import Graph, trace
from trace_lib.etage import run_stage
from trace_lib.texte import load_source

PLACEHOLDER_RE = re.compile(r"^\s*V\d+(\.\d+)?\b.*->|recovered entity", re.IGNORECASE)


def assess(g, doc, rel):
    """Signaux d'ancrage d'une relation (utilise aussi par l'Etage 7 pour les relations
    creees apres cet etage)."""
    se, sn = g.endpoint(rel, "subject")
    oe, on = g.endpoint(rel, "object")
    s_pat, o_pat = g.is_patient(se, sn), g.is_patient(oe, on)
    a = {"sujet_atteste": s_pat or doc.attests(sn), "objet_atteste": o_pat or doc.attests(on)}

    preuve = str(rel.get("preuve") or "")
    if not preuve.strip():
        a["preuve"] = "ABSENTE"
    elif PLACEHOLDER_RE.search(preuve):
        a["preuve"] = "NOTE_SYSTEME"
    else:
        a["preuve"] = "ATTESTEE" if doc.attests(preuve) else "INVENTEE"

    if s_pat or o_pat:
        a["distance"] = "PATIENT"
    else:
        d = doc.distance(sn, on)
        a["distance"] = ("INTROUVABLE" if d is None else "LIGNE" if d <= C.LINE_WINDOW
                         else "PARAGRAPHE" if d <= C.COOCCURRENCE_WINDOW else "LOIN")

    clinical = on if s_pat else sn
    pos = (doc.find_exact(preuve) if a["preuve"] == "ATTESTEE" else []) or doc.locate(clinical)
    a["section"] = doc.section_at(pos[0] if pos else None)

    motifs = []
    if not (a["sujet_atteste"] and a["objet_atteste"]):
        motifs.append("A1_ENTITE_ABSENTE_DU_TEXTE")
    if a["preuve"] == "INVENTEE":
        motifs.append("A2_PREUVE_ABSENTE_DU_TEXTE")
    if a["distance"] == "LOIN":
        motifs.append("A3_EXTREMITES_JAMAIS_PROCHES")
    a["motifs_retrait"] = motifs
    return a


def process(path, data):
    c = Counter()
    g, doc = Graph(data), load_source(data, path)
    remove = []
    for rel in g.relations:
        a = assess(g, doc, rel)
        trace(rel, "ancrage", a)
        c[f"preuve_{a['preuve']}"] += 1
        for m in a["motifs_retrait"]:
            c[m] += 1
        if a["motifs_retrait"]:
            remove.append(rel.get("identifiant_relation"))
    c["relations_retirees"] = g.remove_relations(remove)
    c["relations_sortie"] = len(g.relations)
    return c


def main(in_dir=None):
    run_stage(2, "ANCRAGE DOCUMENTAIRE", in_dir or C.STAGE_DIRS[1], process)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
