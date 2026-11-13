# -*- coding: utf-8 -*-
"""
Valide le graphe RDF produit par construire_graphe.py avec les contraintes SHACL des
34 signatures, puis lance les requetes SPARQL de requetes.sparql.

    pip install rdflib pyshacl
    python valider_graphe.py                       # sorties/ par defaut
    python valider_graphe.py --sortie DOSSIER

La validation se fait SANS inference RDFS : avec l'inference, rdfs:domain et rdfs:range
donneraient a chaque extremite le type attendu, et aucune violation ne serait visible.
"""
import argparse
import re
import sys
from collections import Counter
from pathlib import Path

ICI = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sortie", default=str(ICI / "sorties"))
    ap.add_argument("--sans-requetes", action="store_true")
    a = ap.parse_args()
    try:
        import rdflib
        import pyshacl
    except ImportError:
        sys.exit("Installer d'abord : pip install rdflib pyshacl")

    out = Path(a.sortie)
    data, onto, shapes = rdflib.Graph(), rdflib.Graph(), rdflib.Graph()
    data.parse(out / "graphe" / "graphe_trace_sepsis.ttl", format="turtle")
    onto.parse(out / "ontologie" / "trace_sepsis.ttl", format="turtle")
    shapes.parse(out / "ontologie" / "trace_sepsis_shapes.ttl", format="turtle")
    print(f"Graphe : {len(data)} triplets ; ontologie : {len(onto)} ; SHACL : {len(shapes)}")

    conforme, _, texte = pyshacl.validate(data, shacl_graph=shapes, ont_graph=onto, inference="none")
    messages = Counter(re.findall(r"Message: (.*)", texte))
    print(f"Conforme aux 34 signatures : {'oui' if conforme else 'non'} "
          f"({sum(messages.values())} violation(s))")
    for m, n in messages.most_common():
        print(f"  {n:4d}  {m}")
    (out / "rapport_shacl.txt").write_text(texte, encoding="utf-8")
    print(f"Rapport complet : {out / 'rapport_shacl.txt'}")

    if a.sans_requetes:
        return 0
    g = data + onto
    texte = (ICI / "requetes.sparql").read_text(encoding="utf-8")
    for bloc in re.split(r"^# ---", texte, flags=re.M):
        lignes = bloc.strip().splitlines()
        titre = lignes[0].lstrip("# ").strip() if lignes else "requete"
        requete = "\n".join(l for l in lignes[1:] if not l.startswith("#")).strip()
        if not requete:
            continue
        print(f"\n== {titre}")
        for i, ligne in enumerate(g.query(requete)):
            if i == 10:
                print("  ...")
                break
            print("  " + " | ".join(str(x) for x in ligne))
    return 0


if __name__ == "__main__":
    sys.exit(main())
