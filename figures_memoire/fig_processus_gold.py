# Figure : processus de construction du Gold Standard (chapitre 3)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

plt.rcParams.update({"font.family": "DejaVu Sans"})
fig = plt.figure(figsize=(12, 7.85))
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 120); ax.set_ylim(0, 78.5); ax.axis("off")

INK, MUTED, EDGE = "#1f1f1d", "#52514e", "#b9b7af"
C = {  # bandeau, fond
 "data": ("#2a78d6", "#eef4fc"), "guide": ("#6250d6", "#f1effc"),
 "annot": ("#eb6834", "#fdf1ec"), "ctrl": ("#1b8f66", "#ecf7f2"),
 "med": ("#c2365a", "#fbecf0"), "gold": ("#1d3f73", "#e9eef6")}

def panel(x, y, w, h, key, num, title, lines, sub=None):
    head, body = C[key]
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.2",
                 fc=body, ec=head, lw=1.3))
    ax.add_patch(FancyBboxPatch((x, y + h - 5.2), w, 5.2, boxstyle="round,pad=0,rounding_size=1.2",
                 fc=head, ec="none"))
    ax.add_patch(plt.Rectangle((x, y + h - 5.2), w, 2.4, fc=head, ec="none"))
    ax.text(x + 1.6, y + h - 2.6, f"{num}", color="white", fontsize=12, fontweight="bold", va="center")
    ax.text(x + 4.6, y + h - 2.6, title, color="white", fontsize=10.5, fontweight="bold", va="center")
    yy = y + h - 8.2
    for ln in lines:
        if ln.startswith("#"):   # encadré de sous-étape
            ax.add_patch(FancyBboxPatch((x + 1.6, yy - 1.75), w - 3.2, 3.5,
                         boxstyle="round,pad=0,rounding_size=0.6", fc="white", ec=EDGE, lw=0.8))
            ax.text(x + w / 2, yy, ln[1:], ha="center", va="center", fontsize=8.6, color=INK)
            yy -= 4.3
        elif ln.startswith("~"):
            ax.text(x + 4.3, yy + 0.9, ln[1:], va="center", fontsize=8.6, color=INK)
            yy -= 2.0
        else:
            ax.text(x + 2.2, yy, "•  " + ln, va="center", fontsize=8.6, color=INK)
            yy -= 2.9
    if sub:
        ax.text(x + w / 2, y + 1.6, sub, ha="center", va="center", fontsize=8, color=MUTED, style="italic")

def arrow(p, q, rad=0.0, color="#6b6a64", ls="-", lw=1.6):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=14, color=color,
                 lw=lw, ls=ls, connectionstyle=f"arc3,rad={rad}", shrinkA=2, shrinkB=2))

W, H = 34, 27
x1, x2, x3 = 4, 43, 82
ytop, ybot = 44, 10

panel(x1, ytop, W, H, "data", "1", "Corpus clinique",
      ["246 dossiers scannés, cohorte APROCCHSS",
       "Réanimation, Hôpital Raymond-Poincaré",
       "~(AP-HP), 2008–2015",
       "#Pseudonymisation manuelle par l'AP-HP",
       "#Sous-corpus : 49 dossiers, 291 pages"],
      sub="Deux lots, pris dans l'ordre de mise à disposition")
panel(x2, ytop, W, H, "guide", "2", "TRACE-Sepsis Guideline",
      ["#Rédaction de la première version",
       "#Application aux premiers dossiers et révision",
       "#Validation médicale (environ 5 h)",
       "Version 2.0 : 20 types d'entités,",
       "~34 relations à signature fixe"],
      sub="Sepsis-2, Sepsis-3, SSC 2021, KDIGO, SOFA, EUCAST")
panel(x3, ytop, W, H, "annot", "3", "Annotation manuelle",
      ["Outil : Label Studio",
       "Unité de travail : la page",
       "#1. Entités    →    2. Relations",
       "Sans pré-annotation, sans modèle",
       "Annotatrice : l'auteure (environ 25 jours)"],
      sub="Cas ambigus signalés pour révision")
panel(x3, ybot, W, H, "ctrl", "4", "Contrôle et consolidation",
      ["Contrôle : types, frontières, doublons,",
       "~relations orphelines, signatures, négation",
       "#Consolidation à l'échelle du dossier",
       "#Mise en conformité avec la version 2.0"],
      sub="Résultat : Gold Standard initial")
panel(x2, ybot, W, H, "med", "5", "Validation médicale",
      ["Pr N. Heming, réanimateur",
       "#Revue et corrections directes (≈ 2,5 h / dossier)",
       "#Extension des corrections générales",
       "#Revue finale par le médecin"],
      sub="Cas contraires au guideline rediscutés")
panel(x1, ybot, W, H, "gold", "6", "Gold Standard final",
      ["49 dossiers, 291 pages",
       "#12 174 entités",
       "#5 543 relations",
       "Conforme au schéma TRACE-Sepsis v2.0",
       "Indépendant des modèles évalués"],
      sub="Référence unique de l'évaluation")

# flux principal
arrow((x1 + W, ytop + H / 2), (x2, ytop + H / 2))
arrow((x2 + W, ytop + H / 2), (x3, ytop + H / 2))
arrow((x3 + W / 2, ytop), (x3 + W / 2, ybot + H))
arrow((x3, ybot + H / 2), (x2 + W, ybot + H / 2))
arrow((x2, ybot + H / 2), (x1 + W, ybot + H / 2))
# boucle de révision du guideline
arrow((x3 + 8, ytop + H), (x2 + W - 8, ytop + H), rad=0.32, color="#6250d6", ls=(0, (4, 3)), lw=1.3)
ax.text((x2 + x3 + W) / 2, ytop + H + 4.9, "précision du guideline à partir des cas ambigus",
        ha="center", fontsize=8.2, color="#6250d6", style="italic")

# bandeau RGPD
ax.add_patch(FancyBboxPatch((x1, 1.2), x3 + W - x1, 5.2, boxstyle="round,pad=0,rounding_size=1",
             fc="#f4f3ef", ec=EDGE, lw=0.9))
ax.text((x1 + x3 + W) / 2, 3.8,
        "Protection des données (RGPD) : données pseudonymisées, minimisation, aucune information directement identifiante annotée",
        ha="center", va="center", fontsize=8.4, color=MUTED)

out = "/home/user/43255/figures_memoire/fig_processus_gold"
fig.savefig(out + ".pdf"); fig.savefig(out + ".png", dpi=300)
print("ok")
