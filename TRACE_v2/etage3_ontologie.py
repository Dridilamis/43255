# -*- coding: utf-8 -*-
"""
ETAGE 3 - VALIDATION ONTOLOGIQUE
Seule responsabilite : confronter chaque relation aux signatures TRACE-Sepsis v1.6
(relation autorisee ? type du sujet = domaine ? type de l'objet = image ?).

Il ANNOTE seulement (trace_v2.ontologie). Il ne retire rien : une violation peut etre
reparee par SGCE (Pattern D, RELINK) a l'Etage 4 ; la decision finale est a l'Etage 7.
"""
import sys
from collections import Counter

from trace_lib import config as C
from trace_lib import ontologie
from trace_lib.documents import Graph, trace
from trace_lib.etage import run_stage


def assess(g, rel):
    se, _ = g.endpoint(rel, "subject")
    oe, _ = g.endpoint(rel, "object")
    return {"statut": ontologie.check(str(rel.get("type_relation") or ""),
                                      g.entity_type(se), g.entity_type(oe)),
            "type_sujet": g.entity_type(se), "type_objet": g.entity_type(oe)}


def process(path, data):
    c = Counter()
    g = Graph(data)
    for rel in g.relations:
        a = assess(g, rel)
        trace(rel, "ontologie", a)
        c[a["statut"]] += 1
    return c


def main(in_dir=None):
    run_stage(3, "VALIDATION ONTOLOGIQUE", in_dir or C.STAGE_DIRS[2], process,
              extra_report=lambda: {"signatures": ontologie.source(),
                                    "nombre_signatures": len(ontologie.load_signatures())})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
