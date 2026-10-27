# Figure : appariement des entités en trois passes et modes d'évaluation emboîtés (chapitre 4)
# Les scores affichés sont calculés avec les fonctions de Evaluation/TRACE_Ablation_F1/Matching_entites_ABLATION.py
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

plt.rcParams.update({"font.family": "DejaVu Sans"})
fig = plt.figure(figsize=(13, 7.0))
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 130); ax.set_ylim(0, 70); ax.axis("off")
INK, MUTED = "#1f1f1d", "#52514e"
GREY, BLUE, VIOLET, GREEN, RED = "#6b6a64", "#2a78d6", "#6250d6", "#1b8f66", "#c0392b"

def box(x, y, w, h, fc, ec, lw=1.2, r=1.0, ls="-"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                                fc=fc, ec=ec, lw=lw, ls=ls))

def header(x, y, w, h, color, tint, title):
    box(x, y, w, h, tint, color, lw=1.4)
    box(x, y + h - 5, w, 5, color, "none")
    ax.add_patch(plt.Rectangle((x, y + h - 5), w, 2.2, fc=color, ec="none"))
    ax.text(x + w / 2, y + h - 2.5, title, ha="center", va="center", color="white",
            fontsize=10, fontweight="bold")

def arrow(p, q, color=GREY, lw=1.7):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=15, color=color,
                                 lw=lw, shrinkA=1, shrinkB=1))

def pair(x, y, gold, pred):
    ax.text(x, y, "Gold :", fontsize=8.4, color=MUTED, va="center")
    ax.text(x + 8, y, gold, fontsize=8.6, color=INK, va="center", style="italic")
    ax.text(x, y - 3.4, "Prédit :", fontsize=8.4, color=MUTED, va="center")
    ax.text(x + 8, y - 3.4, pred, fontsize=8.6, color=INK, va="center", style="italic")

# ---------- pré-conditions et normalisation ----------
header(2, 33, 24, 31, GREY, "#f3f2ee", "Normalisation")
ax.text(14, 54.5, "minuscules, accents retirés,\nponctuation → espace,\nvirgule décimale → point",
        ha="center", va="center", fontsize=8.4, color=INK, linespacing=1.4)
ax.text(14, 45.2, "« Température 37,2 »", ha="center", fontsize=8.6, style="italic", color=INK)
ax.text(14, 42.2, "↓", ha="center", fontsize=11, color=GREY)
ax.text(14, 39.0, "« temperature 37.2 »", ha="center", fontsize=8.6, style="italic", color=INK)
ax.text(14, 35.3, "Candidats : même page\net même type d'entité", ha="center", va="center",
        fontsize=8.0, color=MUTED, linespacing=1.3)

# ---------- trois passes ----------
passes = [
    (31, BLUE, "#eef4fc", "Passe 1 — exacte",
     "mentions normalisées\nidentiques",
     ("Insuffisance rénale aiguë", "insuffisance renale aigue"), "identiques après normalisation"),
    (63, VIOLET, "#f1effc", "Passe 2 — inclusion",
     "la plus courte est incluse\n(mots entiers, ≥ 4 caractères)",
     ("Noradrénaline", "noradrénaline IVSE"), "inc = 0,72"),
    (95, GREEN, "#ebf6f1", "Passe 3 — approximative",
     "similarité de chaînes\nsim ≥ 0,85",
     ("choc septique", "choc sceptique"), "sim = 0,96"),
]
W = 30
for x, c, tint, title, crit, (g, p), score in passes:
    header(x, 33, W, 31, c, tint, title)
    ax.text(x + W / 2, 54.5, crit, ha="center", va="center", fontsize=8.4, color=INK, linespacing=1.4)
    pair(x + 2, 47.5, g, p)
    box(x + 2.5, 35.2, W - 5, 4.2, "white", c, lw=1.1, r=0.8)
    ax.text(x + W / 2, 37.3, score, ha="center", va="center", fontsize=8.8, color=c, fontweight="bold")
for x0, x1 in [(26, 31), (61, 63), (93, 95)]:
    arrow((x0 + 0.3, 48.5), (x1 - 0.3, 48.5))
ax.text(62, 66.8, "chaque élément n'est apparié qu'une fois ; les éléments restants passent à la passe suivante",
        ha="center", fontsize=8.4, color=MUTED, style="italic")

# ---------- modes emboîtés ----------
def bracket(x0, x1, y, color, label):
    ax.plot([x0, x0, x1, x1], [y + 1.6, y, y, y + 1.6], color=color, lw=2.0, solid_capstyle="round")
    ax.text((x0 + x1) / 2, y - 2.2, label, ha="center", va="center", fontsize=9.6,
            color=color, fontweight="bold")
bracket(31, 61, 28.5, BLUE, "Strict")
bracket(31, 93, 21.5, VIOLET, "Boundary-Relaxed")
bracket(31, 125, 14.5, GREEN, "Relaxed (mode par défaut)")
ax.text(2, 21.5, "Correspondances\ncomptées comme\nvrais positifs selon\nle mode d'évaluation",
        ha="left", va="center", fontsize=8.6, color=INK, linespacing=1.35)

# ---------- non apparié ----------
box(31, 1.5, 94, 8.2, "#fbeeee", RED, lw=1.2, r=0.8)
ax.text(33, 7.2, "Non apparié → 1 faux positif + 1 faux négatif", fontsize=9.2, color=RED,
        fontweight="bold", va="center")
ax.text(33, 3.6, "« Escherichia coli » / « E. coli » : sim = 0,52 < 0,85     ·     "
        "bonne mention mais mauvais type d'entité", fontsize=8.4, color=INK, va="center")

fig.savefig("fig_appariement_entites.pdf", bbox_inches="tight")
fig.savefig("fig_appariement_entites.png", dpi=200, bbox_inches="tight")
