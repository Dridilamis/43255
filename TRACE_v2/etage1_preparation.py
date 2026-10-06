# -*- coding: utf-8 -*-
"""
ETAGE 1 - PREPARATION
Seule responsabilite : rendre l'entree propre et uniforme. Ne juge aucune relation.

  P1  retire les relations ajoutees/validees avec l'aide du gold (V6.9b-k), avec la meme
      definition que run_pipeline_propre.py (importee, pas recopiee) ;
  P2  met les noms des entites GLOBALES (noeuds du graphe) en forme Unicode NFKC
      ("µ" -> "μ"). Les entites de pages[] sont des MENTIONS : elles restent telles que
      dans le texte (le compte rendu ecrit "µ"), ce que verifie la regle E1 de l'Etage 7 ;
  P3  verifie que chaque relation a un identifiant (en attribue un sinon).

Entree : SortieJson_Postprocessing (jamais modifiee).
"""
import importlib.util
import sys
import unicodedata
from collections import Counter

from trace_lib import config as C
from trace_lib.documents import Graph
from trace_lib.etage import run_stage

_spec = importlib.util.spec_from_file_location("run_pipeline_propre", C.PROJECT / "run_pipeline_propre.py")
_propre = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_propre)


def process(path, data):
    c = Counter()
    g = Graph(data)
    guided = [r.get("identifiant_relation") for r in g.relations if _propre.is_guided(r)]
    c["P1_relations_guidees_gold_retirees"] = g.remove_relations(guided)
    # relations guidees sans identifiant
    before = len(data["global_relations"])
    data["global_relations"] = [r for r in data["global_relations"] if not _propre.is_guided(r)]
    c["P1_relations_guidees_gold_retirees"] += before - len(data["global_relations"])

    for e in data["global_entities"]:
        if isinstance(e, dict) and isinstance(e.get("name"), str):
            new = unicodedata.normalize("NFKC", e["name"])
            if new != e["name"]:
                e["name"] = new
                c["P2_noms_normalises_nfkc"] += 1

    doc = path.name.split("_trace_")[0]
    for i, r in enumerate(data["global_relations"]):
        if not r.get("identifiant_relation"):
            r["identifiant_relation"] = f"V2_{doc}_R{i:05d}"
            c["P3_identifiants_attribues"] += 1
    c["relations_sortie"] = len(data["global_relations"])
    c["entites_sortie"] = len(data["global_entities"])
    return c


def main(in_dir=None):
    run_stage(1, "PREPARATION", in_dir or C.INPUT_DIR, process)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
