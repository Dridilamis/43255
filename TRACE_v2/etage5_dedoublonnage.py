# -*- coding: utf-8 -*-
"""
ETAGE 5 - DEDOUBLONNAGE
Seule responsabilite : supprimer la redondance sans perdre d'information.

  D1  fusionne les entites strictement identiques (meme type, nom, page, preuve, valeur,
      unite, negation, horodatage) : les relations sont reportees sur l'entite gardee ;
  D2  retire les relations strictement identiques (meme sujet, meme type, meme objet,
      par identifiant) ;
  D3  annote (sans retirer) les relations qui repetent un triplet deja vu sous d'autres
      identifiants (meme noms normalises) : trace_v2.doublon = true. Le compte rendu peut
      citer deux fois le meme fait ; c'est l'Etage 7 qui decide.
"""
import sys
from collections import Counter

from trace_lib import config as C
from trace_lib.documents import Graph, trace
from trace_lib.etage import run_stage
from trace_lib.texte import norm

IDENTITY_KEYS = ("type", "categorie", "name", "page", "preuve", "valeur", "unite", "nie", "horodatage")


def process(path, data):
    c = Counter()
    g = Graph(data)

    # D1
    keep_for, canonical = {}, {}
    for eid, e in g.entities.items():
        key = tuple(str(e.get(k)) for k in IDENTITY_KEYS)
        if key in canonical:
            keep_for[eid] = canonical[key]
        else:
            canonical[key] = eid
    if keep_for:
        for rel in g.relations:
            for k in ("identifiant_entite_sujet", "identifiant_entite_objet"):
                if rel.get(k) in keep_for:
                    rel[k] = keep_for[rel[k]]
        data["global_entities"] = [e for e in data["global_entities"]
                                   if not (isinstance(e, dict) and e.get("identifiant_entite") in keep_for)]
        c["D1_entites_fusionnees"] = len(keep_for)
        g = Graph(data)

    # D2 + D3
    seen_ids, seen_names, remove = set(), set(), []
    for rel in g.relations:
        t = rel.get("type_relation")
        ids = (rel.get("identifiant_entite_sujet"), t, rel.get("identifiant_entite_objet"))
        if ids in seen_ids:
            remove.append(rel.get("identifiant_relation"))
            continue
        seen_ids.add(ids)
        names = (norm(g.endpoint(rel, "subject")[1]), t, norm(g.endpoint(rel, "object")[1]))
        dup = names in seen_names
        seen_names.add(names)
        trace(rel, "doublon", dup)
        c["D3_doublons_de_nom_annotes"] += dup
    c["D2_relations_identiques_retirees"] = g.remove_relations(remove)
    c["relations_sortie"] = len(g.relations)
    c["entites_sortie"] = len(data["global_entities"])
    return c


def main(in_dir=None):
    run_stage(5, "DEDOUBLONNAGE", in_dir or C.STAGE_DIRS["4b"], process)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
