# Figure : répartition des 5 543 relations du Gold Standard, par famille et par type (chapitre 3)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

fam = [
 ("Thérapeutiques", [("traitement_administre_a",1861),("traitement_a_pour_posologie",1012),
   ("traitement_cible_defaillance",65),("traitement_indique_par_label_nosologique",58),
   ("antibiotique_adequat_pour",37),("antibiotique_inadequat_pour",8)]),
 ("Symptômes", [("presente_symptome",936)]),
 ("Diagnostiques", [("presente_dysfonction_organe",410),("a_pour_label_nosologique",326),
   ("label_nosologique_a_pour_foyer",80),("score_sofa_calcule_pour",3)]),
 ("Biomarqueurs et microbiologie", [("biomarqueur_supporte_defaillance_organe",114),
   ("micro_organisme_isole_dans",98),("biomarqueur_est_critere_de",57),("biomarqueur_obtenu_a",22)]),
 ("Temporelles et pronostiques", [("patient_a_pour_evolution",163),("service_medical_accueille",145),
   ("evenement_associe_evolution",20),("precede",2)]),
 ("Imagerie", [("imagerie_objective_foyer",69)]),
 ("Signes vitaux", [("signe_vital_supporte_defaillance_organe",39)]),
 ("Terrain et risque", [("comorbidite_est_facteur_risque_de",15),
   ("contexte_acquisition_influence_risque_resistance",3)]),
]
fam.sort(key=lambda f: -sum(v for _, v in f[1]))
total = sum(v for _, r in fam for _, v in r)
assert total == 5543
ACCENT, GREY, INK, MUTED, RULE = "#2a78d6", "#9a9890", "#0b0b0b", "#52514e", "#dcdbd5"
def fr(x): return f"{x:,}".replace(",", " ")
def pct(v):
    p = 100 * v / total
    return "< 0,1 %" if p < 0.1 else f"{p:.1f} %".replace(".", ",")

rows = []   # (y, label, value, family_start)
y = 0
for name, rels in fam:
    ftot = sum(v for _, v in rels)
    rows.append(("fam", y, f"{name}  ({fr(ftot)} ; {pct(ftot)})"))
    y -= 1.05
    for r, v in rels:
        rows.append(("rel", y, r, v)); y -= 1
    y -= 0.35

plt.rcParams.update({"font.family": "DejaVu Sans"})
fig, ax = plt.subplots(figsize=(7.2, 8.6))
for row in rows:
    if row[0] == "fam":
        _, yy, lab = row
        ax.text(-30, yy, lab, ha="left", va="center", fontsize=8.6, fontweight="bold", color=INK,
                transform=ax.get_yaxis_transform() if False else ax.transData)
        ax.axhline(yy + 0.62, color=RULE, lw=0.8, xmin=0, xmax=1)
    else:
        _, yy, lab, v = row
        c = ACCENT if lab in ("traitement_administre_a", "traitement_a_pour_posologie") else GREY
        ax.barh(yy, v, height=0.66, color=c, edgecolor="none")
        ax.text(-20, yy, lab, ha="right", va="center", fontsize=7.6, color=INK)
        ax.text(v + 18, yy, f"{fr(v)}  ({pct(v)})", ha="left", va="center", fontsize=7.4, color=INK)
ax.set_xlim(0, 2350); ax.set_ylim(y + 0.4, 0.9)
ax.axis("off")
fig.subplots_adjust(left=0.44, right=0.98, top=0.99, bottom=0.01)
# titres de famille alignés à gauche de la figure
for t in ax.texts:
    if t.get_fontweight() == "bold":
        t.set_transform(fig.transFigure.__class__ and ax.get_yaxis_transform())
        t.set_x(-0.78)
out = "/home/user/43255/figures_memoire/fig_repartition_relations"
fig.savefig(out + ".pdf"); fig.savefig(out + ".png", dpi=300)
print("ok", total)
