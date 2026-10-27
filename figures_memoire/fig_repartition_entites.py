import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

data = [("BIOMARQUEUR",2989),("TRAITEMENT",2465),("SYMPTOME",1177),("POSOLOGIE",1056),
("COMORBIDITE_ANTECEDENT",585),("SIGNE_VITAL",565),("LABEL_NOSOLOGIQUE",500),
("DEFAILLANCE_ORGANE",485),("IMAGERIE_PROCEDURE",470),("DONNEE_PATIENT",438),
("EVENEMENT_TEMPOREL",403),("EVOLUTION_PRONOSTIC",240),("MICRO_ORGANISME",235),
("FOYER_INFECTIEUX",187),("SERVICE_MEDICAL",184),("CONTEXTE_ACQUISITION",125),
("SCORE_NEUROLOGIQUE",67),("SCORE_SOFA",3),("SCORE_qSOFA",0),("STADE_IRA",0)]
total = sum(v for _,v in data)
assert total == 12174

def fr(x): return f"{x:,}".replace(",", " ")
def pct(v):
    p = 100*v/total
    if v == 0: return "absent"
    if p < 0.1: return "< 0,1 %"
    return f"{p:.1f} %".replace(".", ",")

ACCENT, GREY = "#2a78d6", "#9a9890"
INK, MUTED = "#0b0b0b", "#52514e"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9})
fig, ax = plt.subplots(figsize=(6.3, 5.6))
labels = [n for n,_ in data][::-1]; vals = [v for _,v in data][::-1]
colors = [ACCENT if n in ("BIOMARQUEUR","TRAITEMENT") else GREY for n in labels]
bars = ax.barh(labels, vals, color=colors, height=0.68, edgecolor="none")
for b, v in zip(bars, vals):
    txt = f"{fr(v)}  ({pct(v)})" if v else "0  (absent)"
    ax.text(b.get_width() + 30, b.get_y() + b.get_height()/2, txt,
            va="center", ha="left", fontsize=8.2, color=INK if v else MUTED)
ax.set_xlim(0, 3700)
ax.xaxis.set_visible(False)
for s in ("top","right","bottom"): ax.spines[s].set_visible(False)
ax.spines["left"].set_color("#c9c8c2")
ax.tick_params(axis="y", length=0, labelsize=8.2, colors=INK)
for t in ax.get_yticklabels():
    if t.get_text() in ("SCORE_qSOFA","STADE_IRA"): t.set_color(MUTED)
ax.margins(y=0.01)
fig.tight_layout()
out = "/home/user/43255/figures_memoire/fig_repartition_entites"
fig.savefig(out + ".pdf"); fig.savefig(out + ".png", dpi=300)
print("ok", total)
