# Figure : appariement d'une relation prédite avec une relation du Gold Standard (chapitre 4)
# Les scores affichés sont calculés avec les fonctions de Evaluation/TRACE_Ablation_F1/Matching_relations_ABLATION.py
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

plt.rcParams.update({"font.family": "DejaVu Sans"})
fig = plt.figure(figsize=(13, 6.2))
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 130); ax.set_ylim(0, 62); ax.axis("off")
INK, MUTED, GREY = "#1f1f1d", "#52514e", "#6b6a64"
GOLD, PRED, GREEN, RED = "#b07d12", "#2a78d6", "#1b8f66", "#c0392b"

def box(x, y, w, h, fc, ec, lw=1.2, r=1.0, ls="-"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                                fc=fc, ec=ec, lw=lw, ls=ls))

def arrow(p, q, color=GREY, lw=1.6, style="-|>", ls="-"):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle=style, mutation_scale=14, color=color,
                                 lw=lw, shrinkA=1, shrinkB=1, linestyle=ls))

def relation(y, color, tint, tag, subj, rel, obj):
    ax.text(3, y, tag, fontsize=9.6, color=color, fontweight="bold", va="center")
    box(16, y - 3, 20, 6, tint, color)
    ax.text(26, y, subj, ha="center", va="center", fontsize=9.2, color=INK)
    arrow((36.3, y), (61.7, y), color=color)
    ax.text(49, y + 1.6, rel, ha="center", va="bottom", fontsize=8.6, color=color, style="italic")
    box(62, y - 3, 22, 6, tint, color)
    ax.text(73, y, obj, ha="center", va="center", fontsize=9.2, color=INK)

ax.text(3, 59, "Candidats : même dossier et même type de relation", fontsize=9.0, color=MUTED, style="italic")
relation(50, GOLD, "#fbf4e4", "Gold", "Patient", "presente_symptome", "confusion")
relation(30, PRED, "#eef4fc", "Prédit", "patient", "presente_symptome", "confusions")

# scores des extrémités
for x, lab in [(26, "e(sujet) = 1,00"), (73, "e(objet) = 0,90")]:
    ax.plot([x, x], [46.6, 42.4], color=GREY, lw=1.1, ls=(0, (3, 2)))
    ax.plot([x, x], [37.6, 33.4], color=GREY, lw=1.1, ls=(0, (3, 2)))
    box(x - 8.5, 37.8, 17, 4.4, "white", GREY, lw=1.0, r=0.8)
    ax.text(x, 40, lab, ha="center", va="center", fontsize=8.8, color=INK, fontweight="bold")

# calcul
box(90, 30, 37, 26, "#f3f2ee", GREY, lw=1.2)
ax.text(108.5, 52.5, "Score d'une extrémité", ha="center", fontsize=9.4, fontweight="bold", color=INK)
ax.text(108.5, 48.6, "e = max(sim, inc)", ha="center", fontsize=9.2, color=INK)
ax.text(108.5, 43.6, "Score de la relation", ha="center", fontsize=9.4, fontweight="bold", color=INK)
ax.text(108.5, 39.7, "s = (e(sujet) + e(objet)) / 2", ha="center", fontsize=9.2, color=INK)
ax.text(108.5, 35.2, "s = (1,00 + 0,90) / 2 = 0,95", ha="center", fontsize=9.2, color=GREEN, fontweight="bold")
ax.text(108.5, 32.0, "≥ 0,80 → appariée (Relaxed)", ha="center", fontsize=8.8, color=GREEN)
arrow((84.6, 40), (89.6, 40))

# contre-exemples
box(3, 4, 124, 16, "#fbeeee", RED, lw=1.2, r=0.8)
ax.text(5, 16.6, "Non appariée → 1 faux positif + 1 faux négatif", fontsize=9.4, color=RED, fontweight="bold")
ax.text(5, 12.0, "Extrémité trop différente :", fontsize=8.8, color=INK, fontweight="bold")
ax.text(34, 12.0, "Patient —presente_symptome→ « désorientation »   :   s = (1,00 + 0,36) / 2 = 0,68 < 0,80",
        fontsize=8.8, color=INK)
ax.text(5, 7.4, "Mauvais type de relation :", fontsize=8.8, color=INK, fontweight="bold")
ax.text(34, 7.4, "mêmes extrémités, mais relation « presente_dysfonction_organe »  au lieu de  « presente_symptome »",
        fontsize=8.8, color=INK)

fig.savefig("fig_appariement_relations.pdf", bbox_inches="tight")
fig.savefig("fig_appariement_relations.png", dpi=200, bbox_inches="tight")
