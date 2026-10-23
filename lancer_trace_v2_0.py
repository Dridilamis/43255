# -*- coding: utf-8 -*-
"""
TRACE - LANCEUR v2.0 : extraction Mistral (guideline v2.0) puis TRACE v2 (etages 1 a 8),
evaluee sur le gold v2.0 (49 dossiers).

Depuis le dossier Reduction_hallucinations :

    python lancer_trace_v2_0.py --gold-labelstudio "C:\\...\\Annotation_..._LabelStudio.json" --essai
    python lancer_trace_v2_0.py --gold-labelstudio "C:\\...\\Annotation_..._LabelStudio.json"

Etapes :
  1. verifie les bibliotheques et les fichiers ;
  2. convertit le gold Label Studio v2.0 au format de l'evaluateur (dossier gold_v2_0) ;
  3. extraction Mistral Small 4 des PDF, page par page, avec des prompts construits a partir du
     guideline v2.0 (extraction_mistral/extraction_v2_0 ; reponses en cache, reprise possible) ;
  4. TRACE v2, etages 1 a 8, sur cette extraction : signatures v2.0 aux etages 3 et 7, gold v2.0
     a l'etage 8, reentrainement des votes en validation croisee ;
  5. affiche les resultats par etage.

Rien n'ecrase les resultats precedents : tout va dans TRACE_v2/sorties_v2_0.
La cle Mistral est demandee au clavier si MISTRAL_API_KEY n'existe pas ; elle n'est jamais
ecrite dans un fichier.

Options :
  --pdfs DOSSIER         dossier des PDF a extraire (defaut : ..\\suite pdfs annotés)
  --gold-labelstudio F   export Label Studio du gold v2.0 (inutile si gold_v2_0 existe deja)
  --essai                extraction d'un seul dossier, sans TRACE (pour verifier la cle)
  --docs N               extraction des N premiers dossiers seulement
  --sans-extraction      reprendre directement a TRACE (extraction deja faite)
  --from E               reprendre TRACE a l'etage E (2, 3, 4, 4b, 5, 6, 7)
  --sans-reentrainer     ne pas reentrainer les votes (le mode precision reprend le modele existant)
  --garder P             part gardee par le mode precision, en % (defaut 80)
  --pause S              secondes minimum entre deux appels Mistral (defaut 1.5 ; 5 si erreurs 429)
"""
import argparse
import csv
import getpass
import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
GUIDELINE = ROOT / "guideline" / "Guideline_TRACE_Sepsis_v2.0.json"
EXTRACTION = ROOT / "extraction_mistral" / "extraction_v1_7.py"
CONVERTIR = ROOT / "guideline" / "convertir_gold_labelstudio.py"
EXTRAIT = ROOT / "extraction_mistral" / "extraction_v2_0"
GOLD = ROOT / "gold_v2_0"
TRACE_DIR = ROOT / "TRACE_v2"
SORTIES = TRACE_DIR / "sorties_v2_0"
EVAL_DIR = SORTIES / "08_evaluation"
NOMS = {"01_preparation": "Sortie Mistral (avant TRACE)", "02_ancrage": "Etage 2 ancrage",
        "03_conformite_guideline": "Etage 3 conformite", "04_sgce": "Etage 4 SGCE",
        "04b_recuperation": "Etage 4b recuperation", "05_dedoublonnage": "Etage 5 dedoublonnage",
        "06_attributs": "Etage 6 attributs", "07_arbitrage": "Etage 7 TRACE standard",
        "07_arbitrage_precision": "Etage 7 TRACE precision"}


def titre(texte):
    print("\n" + "=" * 78 + f"\n{texte}\n" + "=" * 78)


def lancer(cmd, cwd, env=None):
    print("> " + " ".join(str(c) for c in cmd) + "\n")
    code = subprocess.call([str(c) for c in cmd], cwd=str(cwd), env=env)
    if code != 0:
        sys.exit(f"\nEchec (code {code}). Corrigez l'erreur ci-dessus puis relancez : "
                 f"les appels Mistral deja faits sont en cache et ne seront pas repayes.")


def verifier(args):
    manquants = [m for m in ("requests", "numpy", "pandas") if importlib.util.find_spec(m) is None]
    if importlib.util.find_spec("pymupdf") is None and importlib.util.find_spec("fitz") is None:
        manquants.append("fitz")
    if manquants:
        pip = " ".join("pymupdf" if m == "fitz" else m for m in manquants)
        sys.exit(f"Bibliotheques manquantes : {' '.join(manquants)}\nInstallez-les : python -m pip install {pip}")
    for chemin in (GUIDELINE, EXTRACTION, CONVERTIR, TRACE_DIR / "run_trace_v2.py"):
        if not chemin.exists():
            sys.exit(f"Introuvable : {chemin}\nLancez ce script depuis le dossier Reduction_hallucinations.")
    if not GOLD.is_dir() and not args.gold_labelstudio and not args.essai:
        sys.exit("Gold v2.0 absent : indiquez l'export Label Studio avec --gold-labelstudio \"chemin.json\".")


def demander_cle():
    if os.getenv("MISTRAL_API_KEY", "").strip():
        print("Cle Mistral : lue dans la variable MISTRAL_API_KEY.")
        return
    cle = getpass.getpass("Collez votre cle API Mistral puis Entree (rien ne s'affiche) : ").strip()
    if not cle:
        sys.exit("Aucune cle saisie.")
    os.environ["MISTRAL_API_KEY"] = cle      # pour les sous-processus de cette execution seulement


def pct(v):
    v = float(v)
    return v * 100 if v <= 1 else v


def afficher_resultats():
    titre("RESULTATS SUR LE GOLD v2.0 (micro, appariement souple, en %)")
    chemin = EVAL_DIR / "tableau.csv"
    if not chemin.exists():
        print(f"Pas de tableau : {chemin}")
        return
    with open(chemin, encoding="utf-8-sig", newline="") as fh:
        lignes = list(csv.DictReader(fh, delimiter=";"))
    print(f"{'':30} | {'Ent P':>6} {'Ent R':>6} {'Ent F1':>6} {'H':>5} | {'Rel P':>6} {'Rel R':>6} {'Rel F1':>6} {'H':>5}")
    for r in lignes:
        try:
            e = [pct(r[k]) for k in ("ent_P", "ent_R", "ent_F1", "ent_hallucination")]
            rl = [pct(r[k]) for k in ("rel_P", "rel_R", "rel_F1", "rel_hallucination")]
        except (KeyError, ValueError):
            continue
        print(f"{NOMS.get(r['etage'], r['etage']):30} | " + " ".join(f"{x:6.2f}" for x in e[:3]) + f" {e[3]:5.1f} | "
              + " ".join(f"{x:6.2f}" for x in rl[:3]) + f" {rl[3]:5.1f}")
    cv = EVAL_DIR / "vote_agents_validation.csv"
    if cv.exists():
        with open(cv, encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh, delimiter=";"))
        print("\nMode precision, validation croisee (documents non vus a l'apprentissage) :")
        for r in rows:
            try:
                print(f"  garder {r['garder_pct']:>3} % | Ent P {pct(r['ent_P']):6.2f} R {pct(r['ent_R']):6.2f} "
                      f"F1 {pct(r['ent_F1']):6.2f} | Rel P {pct(r['rel_P']):6.2f} R {pct(r['rel_R']):6.2f} "
                      f"F1 {pct(r['rel_F1']):6.2f}")
            except (KeyError, ValueError):
                pass
    print(f"\nTableau complet : {chemin}")


def main():
    ap = argparse.ArgumentParser(description="Extraction Mistral v2.0 puis TRACE v2, evaluee sur le gold v2.0.")
    ap.add_argument("--pdfs", default=str(ROOT.parent / "suite pdfs annotés"))
    ap.add_argument("--gold-labelstudio", default="")
    ap.add_argument("--essai", action="store_true")
    ap.add_argument("--docs", type=int, default=0)
    ap.add_argument("--sans-extraction", action="store_true")
    ap.add_argument("--from", dest="depuis", default="")
    ap.add_argument("--sans-reentrainer", action="store_true")
    ap.add_argument("--garder", type=int, default=80)
    ap.add_argument("--pause", type=float, default=1.5)
    args = ap.parse_args()
    verifier(args)
    t0 = time.perf_counter()

    if args.gold_labelstudio:
        titre("1. GOLD v2.0 : conversion de l'export Label Studio")
        lancer([sys.executable, CONVERTIR, args.gold_labelstudio, GOLD], ROOT)

    if not args.sans_extraction:
        titre("2. EXTRACTION MISTRAL SMALL 4 (guideline v2.0)")
        demander_cle()
        cmd = [sys.executable, EXTRACTION, "--guideline", GUIDELINE, "--pdfs", args.pdfs,
               "--sortie", EXTRAIT, "--pause", str(args.pause)]
        if args.essai:
            cmd.append("--essai")
        elif args.docs:
            cmd += ["--docs", str(args.docs)]
        lancer(cmd, ROOT)
        if args.essai:
            print(f"\nEssai termine : verifiez {EXTRAIT}. Relancez sans --essai pour tous les dossiers.")
            return 0

    if not any(EXTRAIT.glob("*_trace_*.json")):
        sys.exit(f"Aucune extraction dans {EXTRAIT}.")
    titre("3. TRACE v2, ETAGES 1 A 8 (signatures et gold v2.0)")
    env = {**os.environ, "TRACE_ENTREE": str(EXTRAIT), "TRACE_TEXTES": str(EXTRAIT / "textes_bruts"),
           "TRACE_GOLD": str(GOLD), "TRACE_GUIDELINE": str(GUIDELINE), "TRACE_SORTIES": str(SORTIES),
           "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    env.pop("MISTRAL_API_KEY", None)         # TRACE n'appelle jamais Mistral
    cmd = [sys.executable, "run_trace_v2.py", "--garder", str(args.garder), "--garder-entites", str(args.garder)]
    if args.depuis:
        cmd += ["--from", args.depuis]
    if not args.sans_reentrainer:
        cmd.append("--entrainer-vote")
    lancer(cmd, TRACE_DIR, env)

    afficher_resultats()
    print(f"\nTermine en {(time.perf_counter() - t0) / 60:.0f} min. Sorties : {SORTIES}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
