# Figure : pipeline d'extraction multimodale, étage 0 de TRACE (chapitre 4)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle

plt.rcParams.update({"font.family": "DejaVu Sans"})
fig = plt.figure(figsize=(13, 6.0))
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 130); ax.set_ylim(0, 60); ax.axis("off")
INK, MUTED, EDGE = "#1f1f1d", "#52514e", "#b9b7af"
PREP, MLLM, GUIDE, FILT, OUT = "#2a78d6", "#d9622b", "#6250d6", "#1b8f66", "#1d3f73"

def box(x, y, w, h, fc, ec, lw=1.2, r=1.0, ls="-"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}", fc=fc, ec=ec, lw=lw, ls=ls))

def panel(x, y, w, h, color, tint, title):
    box(x, y, w, h, tint, color, lw=1.4)
    box(x, y + h - 4.6, w, 4.6, color, "none")
    ax.add_patch(plt.Rectangle((x, y + h - 4.6), w, 2.0, fc=color, ec="none"))
    ax.text(x + w / 2, y + h - 2.3, title, ha="center", va="center", color="white", fontsize=9.6, fontweight="bold")

def card(x, y, w, h, lines, bold_first=True, size=8.0, ec=EDGE):
    box(x, y, w, h, "white", ec, lw=0.9, r=0.7)
    n = len(lines); top = y + h / 2 + (n - 1) * 1.25
    for i, ln in enumerate(lines):
        ax.text(x + w / 2, top - i * 2.5, ln, ha="center", va="center", fontsize=size, color=INK,
                fontweight="bold" if (i == 0 and bold_first) else "normal")

def arrow(p, q, color="#6b6a64", ls="-", lw=1.6, rad=0.0):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=14, color=color, lw=lw, ls=ls,
                 shrinkA=1, shrinkB=1, connectionstyle=f"arc3,rad={rad}"))

ymid = 27
# 1. entrée
panel(1.5, 13, 17.5, 28, PREP, "#eef4fc", "Dossiers et images")
card(3, 27.2, 14.5, 8.0, ["Dossiers scannés", "PDF sans couche texte,", "pseudonymisés"])
card(3, 16.2, 14.5, 8.0, ["Conversion en images", "500 dpi,", "page par page"])
arrow((10.25, 27.2), (10.25, 24.2))

# 2. MLLM : trois appels successifs par page
mx, mw = 23, 54
panel(mx, 13, mw, 28, MLLM, "#fdf1ec", "Extraction par un MLLM, pour chaque page")
cw, cy, ch = 15.2, 22.5, 11.5
xs = [mx + 2, mx + 19.4, mx + 36.8]
card(xs[0], cy, cw, ch, ["1. Transcription", "texte de la page"])
card(xs[1], cy, cw, ch, ["2. Entités (NER)", "« CRP 245 mg/L »", "→ BIOMARQUEUR"])
card(xs[2], cy, cw, ch, ["3. Relations (RE)", "Amiklin →", "traitement_administre_a", "→ Patient"], size=7.6)
arrow((xs[0] + cw, cy + ch / 2), (xs[1], cy + ch / 2))
arrow((xs[1] + cw, cy + ch / 2), (xs[2], cy + ch / 2))
ax.text(mx + mw / 2, 17.6, "Qwen2.5-VL (local, GPU universitaire)     ou     Mistral Small 4 (API, température 0)",
        ha="center", va="center", fontsize=8.0, color=MUTED)
ax.text(mx + mw / 2, 15.0, "Sortie de chaque étape au format JSON", ha="center", va="center",
        fontsize=7.8, color=MUTED, style="italic")
arrow((19, ymid), (mx, ymid))

# guideline au-dessus, qui alimente les trois consignes
gx, gw, gy, gh = mx, mw, 46, 11
box(gx, gy, gw, gh, "#f1effc", GUIDE, lw=1.4)
ax.text(gx + gw / 2, gy + gh - 2.6, "TRACE-Sepsis Annotation Guideline v2.0", ha="center", va="center",
        fontsize=9.6, fontweight="bold", color=GUIDE)
ax.text(gx + gw / 2, gy + 4.6, "Consignes construites uniquement à partir du guideline :", ha="center", va="center",
        fontsize=8.0, color=INK)
ax.text(gx + gw / 2, gy + 2.2, "20 types d'entités, 34 relations à signature fixe, règles d'annotation, format JSON",
        ha="center", va="center", fontsize=8.0, color=INK)
for x in xs:
    arrow((x + cw / 2, gy), (x + cw / 2, cy + ch), color=GUIDE, ls=(0, (3, 2.5)), lw=1.1)

# 3. filtres
fx, fw = 81, 22
panel(fx, 13, fw, 28, FILT, "#ecf7f2", "Filtres et fusion")
card(fx + 1.5, 29.0, fw - 3, 6.6, ["Entité retrouvée mot", "pour mot dans la page"], bold_first=False, size=7.8)
card(fx + 1.5, 21.6, fw - 3, 6.6, ["Relation dans les", "34 signatures"], bold_first=False, size=7.8)
card(fx + 1.5, 14.2, fw - 3, 6.6, ["Fusion des pages", "par dossier"], bold_first=False, size=7.8)
arrow((mx + mw, ymid), (fx, ymid))

# 4. sortie
ox, ow = 107, 21.5
panel(ox, 13, ow, 28, OUT, "#e9eef6", "Sortie brute")
card(ox + 1.5, 24.0, ow - 3, 10.0, ["Un JSON par dossier", "entités et relations,", "avec preuve et page"], size=7.8)
ax.text(ox + ow / 2, 18.8, "Point de départ", ha="center", va="center", fontsize=8.2, color=OUT, fontweight="bold")
ax.text(ox + ow / 2, 16.3, "de TRACE (étage 0b)", ha="center", va="center", fontsize=8.2, color=OUT, fontweight="bold")
arrow((fx + fw, ymid), (ox, ymid))

# bandeau : étage 0
ax.plot([1.5, 1.5, 128.5, 128.5], [9.6, 8.4, 8.4, 9.6], color=MLLM, lw=1.4)
ax.text(65, 6.0, "Étage 0 de TRACE : extraction multimodale (chapitre 4)", ha="center", va="center",
        fontsize=9.2, fontweight="bold", color=MLLM)

out = "/home/user/43255/figures_memoire/fig_pipeline_extraction"
fig.savefig(out + ".pdf"); fig.savefig(out + ".png", dpi=300)
print("ok")
