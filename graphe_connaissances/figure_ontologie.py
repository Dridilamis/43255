# -*- coding: utf-8 -*-
"""
Figure de l'ontologie TRACE-Sepsis (schema : 20 classes, 34 relations) pour le memoire
et la soutenance, plus lisible qu'OntoGraf.

    python graphe_connaissances/figure_ontologie.py
    python graphe_connaissances/figure_ontologie.py --resume graphe_connaissances/sorties/resume.json

Sans --resume : les 34 relations du guideline, colorees par famille.
Avec --resume (produit par construire_graphe.py) : seconde figure ou les relations presentes
dans le graphe sont en trait plein avec leur effectif, les autres en pointille gris.

Ecrit des fichiers .dot ; si Graphviz est installe (commande `dot`, https://graphviz.org),
produit aussi .svg, .pdf et .png. Sinon, coller le .dot sur https://dreampuf.github.io/GraphvizOnline
ou installer Graphviz (Windows : winget install graphviz).
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent
GUIDELINE = ICI.parent / "guideline" / "Guideline_TRACE_Sepsis_v2.0_valide_medecin.json"

# familles de classes : (titre, couleur de fond, couleur de bord, classes)
FAMILLES = [
    ("Patient et parcours", "#dbe8fb", "#2a6fdb",
     ["DONNEE_PATIENT", "SERVICE_MEDICAL", "EVENEMENT_TEMPOREL", "EVOLUTION_PRONOSTIC"]),
    ("Diagnostic et gravité", "#fbe0dd", "#c0392b",
     ["LABEL_NOSOLOGIQUE", "FOYER_INFECTIEUX", "DEFAILLANCE_ORGANE", "STADE_IRA",
      "SCORE_SOFA", "SCORE_qSOFA", "SCORE_NEUROLOGIQUE"]),
    ("Thérapeutique", "#d9f2ea", "#16a085", ["TRAITEMENT", "POSOLOGIE"]),
    ("Biologie et microbiologie", "#efe6f8", "#7d3c98", ["BIOMARQUEUR", "MICRO_ORGANISME", "SIGNE_VITAL"]),
    ("Clinique et imagerie", "#fdf3d6", "#b7950b", ["SYMPTOME", "IMAGERIE_PROCEDURE"]),
    ("Terrain", "#ececec", "#7f8c8d", ["COMORBIDITE_ANTECEDENT", "CONTEXTE_ACQUISITION"]),
]
COULEUR_GROUPE = {
    "RELATIONS_DIAGNOSTIQUES": "#c0392b", "RELATIONS_THERAPEUTIQUES": "#16a085",
    "RELATIONS_SIGNES_VITAUX": "#5dade2", "RELATIONS_BIOMARQUEURS_ET_MICROBIO": "#7d3c98",
    "RELATIONS_TERRAIN_ET_RISQUE": "#7f8c8d", "RELATIONS_TEMPORELLES_ET_PRONOSTIC": "#34495e",
    "RELATIONS_IMAGERIE": "#b7950b", "RELATIONS_SYMPTOMES": "#b7950b",
}
NOMS = {
    "DONNEE_PATIENT": "Patient", "LABEL_NOSOLOGIQUE": "Diagnostic", "FOYER_INFECTIEUX": "Foyer infectieux",
    "DEFAILLANCE_ORGANE": "Défaillance d'organe", "STADE_IRA": "Stade d'IRA", "SCORE_SOFA": "Score SOFA",
    "SCORE_qSOFA": "Score qSOFA", "SCORE_NEUROLOGIQUE": "Score neurologique", "TRAITEMENT": "Traitement",
    "POSOLOGIE": "Posologie", "BIOMARQUEUR": "Biomarqueur", "MICRO_ORGANISME": "Micro-organisme",
    "SIGNE_VITAL": "Signe vital", "SYMPTOME": "Symptôme", "IMAGERIE_PROCEDURE": "Imagerie / procédure",
    "COMORBIDITE_ANTECEDENT": "Comorbidité / antécédent", "CONTEXTE_ACQUISITION": "Contexte d'acquisition",
    "SERVICE_MEDICAL": "Service médical", "EVENEMENT_TEMPOREL": "Événement temporel",
    "EVOLUTION_PRONOSTIC": "Évolution / pronostic",
}


def etiquette_relation(nom):
    """Libelle court, sur deux lignes au plus."""
    mots = nom.replace("_", " ").split()
    if len(" ".join(mots)) <= 22:
        return " ".join(mots)
    milieu = len(mots) // 2
    return " ".join(mots[:milieu]) + "\\n" + " ".join(mots[milieu:])


def dot_ontologie(signatures, effectifs=None, titre="", cadres=False):
    L = ["digraph ontologie {",
         '  graph [layout=dot, rankdir=LR, splines=true, nodesep=0.35, ranksep=1.1, pad=0.3,',
         '         fontname="Helvetica", fontsize=20, labelloc=t, label="%s", bgcolor="white"];' % titre,
         '  node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=13, penwidth=1.6,',
         '        margin="0.18,0.08"];',
         '  edge [fontname="Helvetica", fontsize=9, arrowsize=0.7, penwidth=1.2];']
    for i, (titre_f, fond, bord, classes) in enumerate(FAMILLES):
        if cadres:
            L.append(f'  subgraph cluster_{i} {{ label="{titre_f}"; fontsize=12; fontcolor="{bord}"; '
                     f'style="rounded,dashed"; color="{bord}";')
        for c in classes:
            extra = ', fontsize=17, penwidth=2.6, margin="0.3,0.15"' if c == "DONNEE_PATIENT" else ""
            L.append(f'    {c} [label="{NOMS.get(c, c)}", fillcolor="{fond}", color="{bord}"{extra}];')
        if cadres:
            L.append("  }")
    if not cadres:   # legende des familles
        lignes = "".join(f'<TR><TD BGCOLOR="{fond}" WIDTH="18"></TD><TD ALIGN="LEFT"><FONT COLOR="{bord}">'
                         f'{t}</FONT></TD></TR>' for t, fond, bord, _ in FAMILLES)
        L.append(f'  legende [shape=plaintext, style="", fontsize=11, label=<<TABLE BORDER="0" CELLSPACING="3">'
                 f'{lignes}</TABLE>>];')
    for rel, (dom, img, groupe) in signatures.items():
        coul = COULEUR_GROUPE.get(groupe, "#555555")
        lab = etiquette_relation(rel)
        # le Patient reste a gauche : une relation qui arrive au Patient est tracee depuis lui,
        # avec la fleche inversee (dir=back) pour garder son vrai sens
        if img == "DONNEE_PATIENT" and dom != img:
            a_, b_, sens = img, dom, ", dir=back"
        else:
            a_, b_, sens = dom, img, ""
        if effectifs is None:
            L.append(f'  {a_} -> {b_} [label="{lab}", color="{coul}", fontcolor="{coul}"{sens}];')
        elif effectifs.get(rel):
            n = effectifs[rel]
            larg = 1.2 + min(4.0, n / 300)
            L.append(f'  {a_} -> {b_} [label="{lab}\\n({n})", color="{coul}", fontcolor="{coul}", '
                     f'penwidth={larg:.1f}{sens}];')
        else:
            L.append(f'  {a_} -> {b_} [label="{lab}", color="#c8c8c8", fontcolor="#a8a8a8", '
                     f'style=dashed{sens}];')
    L.append("}")
    return "\n".join(L)


def rendre(dot_txt, base):
    base.parent.mkdir(parents=True, exist_ok=True)
    (base.with_suffix(".dot")).write_text(dot_txt, encoding="utf-8")
    dot = shutil.which("dot")
    if not dot:
        print(f"  {base.with_suffix('.dot')} (Graphviz absent : pas de .svg/.pdf/.png)")
        return
    for fmt, opts in (("svg", []), ("pdf", []), ("png", ["-Gdpi=200"])):
        subprocess.run([dot, f"-T{fmt}", *opts, "-o", str(base.with_suffix("." + fmt)),
                        str(base.with_suffix(".dot"))], check=True)
    print(f"  {base}.svg / .pdf / .png")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--guideline", default=str(GUIDELINE))
    ap.add_argument("--resume", help="resume.json de construire_graphe.py (effectifs des relations)")
    ap.add_argument("--sortie", default=str(ICI / "figures"))
    a = ap.parse_args()
    g = json.loads(Path(a.guideline).read_text(encoding="utf-8-sig"))
    g = g.get("ontologie_sepsis_graph", g)
    signatures = {n: (s["domaine"], s["image"], s.get("groupe", "")) for n, s in g["signatures_relations"].items()}
    out = Path(a.sortie)
    print("Figures :")
    rendre(dot_ontologie(signatures, titre=""), out / "ontologie_trace_sepsis")
    if a.resume:
        eff = json.loads(Path(a.resume).read_text(encoding="utf-8")).get("relations_par_type", {})
        rendre(dot_ontologie(signatures, eff, titre=""), out / "ontologie_relations_observees")
    return 0


if __name__ == "__main__":
    sys.exit(main())
