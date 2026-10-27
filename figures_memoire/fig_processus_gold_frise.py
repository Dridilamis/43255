# Figure : processus de construction du Gold Standard, en frise (chapitre 3)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle

plt.rcParams.update({"font.family": "DejaVu Sans"})
fig = plt.figure(figsize=(13, 6.6))
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 130); ax.set_ylim(0, 66); ax.axis("off")
INK, MUTED, EDGE = "#1f1f1d", "#52514e", "#b9b7af"
PREP, ANNOT, VALID, GOLD, GUIDE = "#2a78d6", "#d9622b", "#c2365a", "#1d3f73", "#6250d6"

def box(x, y, w, h, fc, ec, lw=1.2, r=1.0, ls="-"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                 fc=fc, ec=ec, lw=lw, ls=ls))

def arrow(p, q, color="#6b6a64", ls="-", lw=1.5, rad=0.0):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=13, color=color, lw=lw,
                 ls=ls, shrinkA=1, shrinkB=1, connectionstyle=f"arc3,rad={rad}"))

def bullets(x, y, lines, size=7.9, color=INK, step=2.55, ink=None):
    ink = ink or (color if color in ("white", INK) else INK)
    for ln in lines:
        if ln.startswith("~"):
            ax.text(x + 1.6, y, ln[1:], fontsize=size, color=ink, va="center")
        else:
            ax.text(x, y, "•", fontsize=size + 1, color=color, va="center", fontweight="bold")
            ax.text(x + 1.6, y, ln, fontsize=size, color=ink, va="center")
        y -= step

# ---------- bandeau supérieur : le guideline ----------
yt, ht = 47, 16
box(1.5, yt, 18.5, ht, "#eef4fc", PREP)
ax.text(10.75, yt + ht - 2.2, "Construction\ndu guideline", ha="center", va="center",
        fontsize=8.6, fontweight="bold", color=PREP, linespacing=1.05)
bullets(2.6, yt + ht - 6.6, ["Sepsis-2, Sepsis-3,", "~SSC 2021, KDIGO 2012,", "~SOFA, EUCAST v14.0",
                             "Observation des", "~premiers dossiers"], size=7.4, step=1.95)
box(22, yt, 18.5, ht, "#fbecf0", VALID)
ax.text(31.25, yt + ht - 2.2, "Validation médicale\ndu guideline", ha="center", va="center",
        fontsize=8.6, fontweight="bold", color=VALID, linespacing=1.05)
bullets(23.1, yt + ht - 6.6, ["Pr N. Heming,", "~médecine intensive–", "~réanimation",
                              "Catégories, relations,", "~vocabulaires, règles"], size=7.4, step=1.95)
arrow((20, yt + ht / 2), (22, yt + ht / 2))
gx, gw = 44, 72
box(gx, yt, gw, ht, "#f1effc", GUIDE, lw=1.4)
box(gx, yt + ht - 4.4, gw, 4.4, GUIDE, "none")
ax.add_patch(plt.Rectangle((gx, yt + ht - 4.4), gw, 2.0, fc=GUIDE, ec="none"))
ax.text(gx + gw / 2, yt + ht - 2.2, "TRACE-Sepsis Annotation Guideline, version 2.0 (validée par le médecin)",
        ha="center", va="center", fontsize=9.6, fontweight="bold", color="white")
bullets(gx + 2.5, yt + ht - 7.2, [
    "20 types d'entités et 34 relations orientées, chacune avec une signature domaine → portée verrouillée",
    "Règles : ancrage documentaire, négation, incertitude, temporalité, valeurs et unités, cas ambigus",
    "Consolidé par versions successives à partir des cas rencontrés, puis validé par le médecin (environ 5 h)"],
    size=8.0, step=2.6)
arrow((40.5, yt + ht / 2), (gx, yt + ht / 2))

# ---------- frise des 7 étapes ----------
yl = 35
xs = [9.5, 27.2, 44.9, 62.6, 80.3, 98, 119]
col = [PREP, PREP, ANNOT, ANNOT, ANNOT, VALID, GOLD]
ax.plot([xs[0], xs[5] + 6], [yl, yl], color="#c9c8c2", lw=2.2, zorder=0)
for i in range(6):
    arrow((xs[i] + 3.2, yl), (xs[i + 1] - 3.2, yl) if i < 5 else (110.4, yl), color="#8a8983", lw=1.5)

# le guideline encadre l'annotation, le contrôle et la validation
for xi in (xs[2], xs[3], xs[5]):
    arrow((xi, yt), (xi, yl + 3.4), color=GUIDE, ls=(0, (3, 2.5)), lw=1.1)
ax.text(xs[2] + 1.0, (yt + yl + 3.4) / 2 + 0.6, "applique les règles", fontsize=7.2, color=GUIDE, style="italic")
ax.text(xs[3] + 1.0, (yt + yl + 3.4) / 2 + 0.6, "vérifie les règles", fontsize=7.2, color=GUIDE, style="italic")
ax.text(xs[5] + 1.0, (yt + yl + 3.4) / 2 + 0.6, "référentiel de la revue", fontsize=7.2, color=GUIDE, style="italic")

steps = [
 ("Corpus clinique", ["246 dossiers patients", "Cohorte APROCCHSS", "~(AP-HP, 2008–2015)", "Pseudonymisés"]),
 ("Sélection du\nsous-corpus", ["49 dossiers (≈ 20 %)", "291 pages", "Deux lots, ordre de", "~mise à disposition"]),
 ("Annotation\nmanuelle", ["Label Studio", "Page = unité de tâche", "Entités puis relations", "Sans pré-annotation", "~ni modèle"]),
 ("Contrôle et\nconsolidation", ["Types, frontières", "Signatures", "~domaine → portée", "Négation, inférences", "~non justifiées", "Fusion par dossier", "Mise en conformité v2.0"]),
 ("Gold Standard\ninitial", ["Contrôle structurel", "Prêt pour la revue", "~médicale"]),
 ("Validation\nmédicale", ["Pr N. Heming", "Confirmer, modifier,", "~supprimer, ajouter", "≈ 2,5 h par dossier", "Extension des", "~corrections", "Revue finale"]),
]
for i, (title, lines) in enumerate(steps):
    x = xs[i]
    ax.add_patch(Circle((x, yl), 3.0, fc=col[i], ec="white", lw=2, zorder=3))
    ax.text(x, yl, str(i + 1), ha="center", va="center", color="white", fontsize=11, fontweight="bold", zorder=4)
    ax.text(x, yl - 6.0, title, ha="center", va="center", fontsize=8.8, fontweight="bold", color=INK, linespacing=1.05)
    bullets(x - 7.6, yl - 10.6, lines, size=7.7, color=col[i] if i != 4 else ANNOT, step=2.35)

# étape 7 : encadré du Gold Standard final
bx, bw = 110.6, 18.4
box(bx, 10.5, bw, 28.5, GOLD, GOLD, r=1.2)
ax.add_patch(Circle((bx + bw / 2, 39.0), 3.0, fc=GOLD, ec="white", lw=2, zorder=3))
ax.text(bx + bw / 2, 39.0, "7", ha="center", va="center", color="white", fontsize=11, fontweight="bold", zorder=4)
ax.text(bx + bw / 2, 33.6, "Gold Standard\nfinal", ha="center", va="center", fontsize=9.6,
        fontweight="bold", color="white", linespacing=1.05)
bullets(bx + 1.4, 28.6, ["12 174 entités", "5 543 relations", "Consolidation finale", "Référence unique", "~de l'évaluation",
                         "Traçable jusqu'au", "~document", "Indépendant des", "~modèles évalués"],
        size=7.7, color="white", step=2.05)

# ---------- phases ----------
def phase(x0, x1, label, c):
    y = 4.2
    ax.plot([x0, x0, x1, x1], [y + 1.2, y, y, y + 1.2], color=c, lw=1.4)
    ax.text((x0 + x1) / 2, y - 2.0, label, ha="center", va="center", fontsize=9, fontweight="bold", color=c)
phase(1.5, 34, "Préparation du corpus", PREP)
phase(36.5, 88, "Annotation et contrôle", ANNOT)
phase(90.5, 129, "Validation et Gold Standard", VALID)

out = "/home/user/43255/figures_memoire/fig_processus_gold_frise"
fig.savefig(out + ".pdf"); fig.savefig(out + ".png", dpi=300)
print("ok")
