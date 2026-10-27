# Figure : pipeline d'extraction multimodale (chapitre 4), d'après la figure de l'auteure
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

plt.rcParams.update({"font.family": "DejaVu Sans"})
fig = plt.figure(figsize=(13, 6.4))
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 130); ax.set_ylim(0, 64); ax.axis("off")
INK, MUTED, EDGE = "#1f1f1d", "#52514e", "#b9b7af"
BLUE, NAVY, VIOLET, GREEN = "#2a78d6", "#1d3f73", "#6250d6", "#1b8f66"

def box(x, y, w, h, fc, ec, lw=1.2, r=1.0, ls="-"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}", fc=fc, ec=ec, lw=lw, ls=ls))

def panel(x, y, w, h, color, tint, title, hh=5.0):
    box(x, y, w, h, tint, color, lw=1.4)
    box(x, y + h - hh, w, hh, color, "none")
    ax.add_patch(plt.Rectangle((x, y + h - hh), w, 2.2, fc=color, ec="none"))
    ax.text(x + w / 2, y + h - hh / 2, title, ha="center", va="center", color="white", fontsize=9.6,
            fontweight="bold", linespacing=1.15)

R = fig.canvas.get_renderer()
def seq(x, y, parts):
    """Écrit des morceaux de texte à la suite, en mesurant chacun."""
    for txt, color, bold in parts:
        t = ax.text(x, y, txt, ha="left", va="center", fontsize=8.2, color=color,
                    fontweight="bold" if bold else "normal")
        bb = t.get_window_extent(renderer=R).transformed(ax.transData.inverted())
        x = bb.x1 + 0.9

def arrow(p, q, color="#6b6a64", lw=1.7):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=15, color=color, lw=lw, shrinkA=1, shrinkB=1))

# cadre d'ensemble en pointillés
box(0.8, 1.0, 128.4, 62.0, "none", "#7a8fb0", lw=1.0, r=0.6, ls=(0, (4, 3)))
ymid = 39

# 1. entrée
box(3, 42, 17, 13, "#eef4fc", BLUE, lw=1.2)
ax.text(11.5, 51.2, "Dossiers cliniques", ha="center", va="center", fontsize=8.8, fontweight="bold", color=INK)
ax.text(11.5, 48.4, "numérisés et", ha="center", va="center", fontsize=8.8, fontweight="bold", color=INK)
ax.text(11.5, 45.6, "pseudonymisés", ha="center", va="center", fontsize=8.8, fontweight="bold", color=INK)
arrow((11.5, 42), (11.5, 35.5))
box(3, 27, 17, 8.5, "#eef4fc", BLUE, lw=1.2)
ax.text(11.5, 31.25, "Conversion en images", ha="center", va="center", fontsize=8.8, fontweight="bold", color=INK)
ax.add_patch(FancyArrowPatch((20, 31.25), (23.5, 31.25), arrowstyle="-|>", mutation_scale=15, color="#6b6a64",
             lw=1.7, shrinkA=1, shrinkB=1))

# 2. couche d'extraction basée sur les MLLM
px, pw, py, ph = 23.5, 43, 22.5, 37
panel(px, py, pw, ph, BLUE, "#eef4fc", "Couche d'extraction d'informations cliniques\nbasée sur les MLLM", hh=7.0)
box(px + 2, py + 11, 18, 16.5, "white", EDGE, lw=0.9, r=0.7)
ax.text(px + 11, py + 23.8, "Qwen2.5-VL", ha="center", va="center", fontsize=9.2, fontweight="bold", color=INK)
ax.text(px + 11, py + 20.4, "Mistral Small 4", ha="center", va="center", fontsize=9.2, fontweight="bold", color=INK)
ax.text(px + 11, py + 15.4, "Modèles multimodaux", ha="center", va="center", fontsize=8.0, color=MUTED)
ax.text(px + 11, py + 13.0, "(MLLM)", ha="center", va="center", fontsize=8.0, color=MUTED)
ax.text(px + 21.5, py + 19.2, "+", ha="center", va="center", fontsize=18, color=MUTED)
box(px + 23, py + 11, 18, 16.5, "white", VIOLET, lw=0.9, r=0.7)
ax.text(px + 32, py + 23.4, "Guide d'extraction", ha="center", va="center", fontsize=9.0, fontweight="bold", color=VIOLET)
ax.text(px + 32, py + 20.2, "TRACE-Sepsis", ha="center", va="center", fontsize=9.0, fontweight="bold", color=VIOLET)
ax.text(px + 32, py + 14.2, "(guide d'annotation)", ha="center", va="center", fontsize=8.0, color=MUTED)
box(px + 2, py + 2.5, pw - 4, 7, BLUE, "none", r=0.7)
ax.text(px + pw / 2, py + 6.0, "Ingénierie de prompts guidée par le guide d'annotation", ha="center",
        va="center", fontsize=8.3, fontweight="bold", color="white")
arrow((px + pw, ymid), (px + pw + 4, ymid))

# 3. extraction structurée
ex, ew = 70.5, 40
panel(ex, py, ew, ph, NAVY, "#e9eef6", "Extraction structurée\nde l'information", hh=7.0)
def bloc(y, h, tag, title, color, lines):
    box(ex + 2, y, ew - 4, h, "white", EDGE, lw=0.9, r=0.7)
    box(ex + 3.2, y + h - 5.4, 6.4, 4.2, color, "none", r=0.6)
    ax.text(ex + 6.4, y + h - 3.3, tag, ha="center", va="center", fontsize=9.4, fontweight="bold", color="white")
    ax.text(ex + 11.0, y + h - 3.3, title, ha="left", va="center", fontsize=8.6, fontweight="bold", color=INK)
    for i, (a, b, c) in enumerate(lines):
        yy = y + h - 8.4 - i * 3.0
        parts = [(a, INK, False), ("→", MUTED, False), (b, color, True)]
        if c:
            parts += [("→", MUTED, False), (c, INK, False)]
        seq(ex + 4.0, yy, parts)
bloc(py + 15.0, 13.0, "NER", "Reconnaissance d'entités nommées", BLUE,
     [("« CRP 245 mg/L »", "BIOMARQUEUR", None), ("« Choc septique »", "LABEL_NOSOLOGIQUE", None)])
bloc(py + 2.5, 10.5, "RE", "Extraction des relations", GREEN,
     [("« Amiklin »", "traitement_administre_a", "« Patient »")])
# filtres et fusion, sous l'extraction
fx, fy, fw, fh = ex, 3.5, ew, 15.5
box(fx, fy, fw, fh, "#ecf7f2", GREEN, lw=1.4)
ax.text(fx + 2.5, fy + fh - 2.8, "Filtres et fusion", ha="left", va="center", fontsize=9.4, fontweight="bold", color=GREEN)
for i, ln in enumerate(["Entité retrouvée mot pour mot dans la page", "Relation dans les 34 signatures",
                        "Fusion des pages par dossier"]):
    yy = fy + fh - 6.6 - i * 3.0
    ax.text(fx + 3.2, yy, "•", fontsize=9.6, color=GREEN, va="center", fontweight="bold")
    ax.text(fx + 5.0, yy, ln, fontsize=8.4, color=INK, va="center")
arrow((ex + ew / 2, py), (ex + ew / 2, fy + fh))
jx = 114.5
arrow((fx + fw, fy + fh / 2), (jx, fy + fh / 2))

# 4. sortie JSON
jx = 114.5
box(jx, 3.25, 13.5, 16, "#e9eef6", NAVY, lw=1.2)
ax.text(jx + 6.75, 15.2, "JSON", ha="center", va="center", fontsize=13, fontweight="bold", color=NAVY)
ax.text(jx + 6.75, 10.8, "Sortie structurée :", ha="center", va="center", fontsize=8.2, color=INK)
ax.text(jx + 6.75, 7.8, "entités + relations", ha="center", va="center", fontsize=8.2, color=INK)

out = "/home/user/43255/figures_memoire/fig_pipeline_extraction"
fig.savefig(out + ".pdf"); fig.savefig(out + ".png", dpi=300)
print("ok")
