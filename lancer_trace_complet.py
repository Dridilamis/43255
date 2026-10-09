# -*- coding: utf-8 -*-
"""
TRACE - LANCEUR COMPLET : seconde passe Mistral (etage 0b) puis TRACE v2 (etages 1 a 8).

Une seule commande, depuis le dossier Reduction_hallucinations :

    python lancer_trace_complet.py            # tout : seconde passe (43 documents) + TRACE v2
    python lancer_trace_complet.py --essai    # essai : seconde passe sur 2 documents seulement

La cle Mistral est demandee au clavier (rien ne s'affiche quand vous tapez) si la variable
MISTRAL_API_KEY n'existe pas. Elle n'est jamais ecrite dans un fichier : elle n'existe que
pendant l'execution.

Etapes :
  1. verifie les bibliotheques et les dossiers ;
  2. seconde passe Mistral : ajoute les entites et relations oubliees, avec preuve et vote
     (reprise possible : les reponses deja obtenues sont en cache) ;
  3. TRACE v2 sur la sortie de la seconde passe, avec reentrainement des votes et validation
     croisee (~30 min) ;
  4. affiche avant / apres.

Options :
  --essai              seconde passe sur 2 documents, sans TRACE (pour verifier la cle)
  --docs N             seconde passe sur les N premiers documents seulement
  --sans-trace         s'arreter apres la seconde passe
  --sans-reentrainer   TRACE v2 sans reentrainer les votes (rapide, ~3 min ; le mode
                       precision utilise alors l'ancien modele)
  --echantillons N     appels par question pour le vote (defaut 3)
  --vote N             nombre minimal de reponses concordantes (defaut 2)
  --pause S            secondes minimum entre deux appels Mistral (defaut 1.5) ; si Mistral
                       repond 429 (trop de requetes), relancez avec --pause 5
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
SECONDE_PASSE = ROOT / "extraction_mistral" / "seconde_passe_mistral.py"
ENTREE = ROOT / "SortieJson_Postprocessing_PROPRE"
SORTIE = ROOT / "extraction_mistral" / "seconde_passe"
TRACE_DIR = ROOT / "TRACE_v2"
EVAL_DIR = TRACE_DIR / "sorties" / "08_evaluation"

# Reference : TRACE v2 sur l'entree actuelle (sans seconde passe), voir TRACE_v2/README.md
AVANT = {
    "Avant TRACE (ancienne chaine)": (74.46, 68.10, 71.14, 71.93, 54.92, 62.29),
    "TRACE v2 standard, sans seconde passe": (75.76, 68.57, 71.99, 71.65, 55.58, 62.60),
}


def titre(texte):
    print("\n" + "=" * 78 + f"\n{texte}\n" + "=" * 78)


def verifier():
    manquants = [m for m in ("requests", "numpy", "pandas") if importlib.util.find_spec(m) is None]
    if manquants:
        sys.exit(f"Bibliotheques manquantes : {' '.join(manquants)}\n"
                 f"Installez-les : python -m pip install {' '.join(manquants)}")
    for chemin in (SECONDE_PASSE, ENTREE, TRACE_DIR / "run_trace_v2.py"):
        if not chemin.exists():
            sys.exit(f"Introuvable : {chemin}\nLancez ce script depuis le dossier Reduction_hallucinations.")


def demander_cle():
    if os.getenv("MISTRAL_API_KEY", "").strip():
        print("Cle Mistral : lue dans la variable MISTRAL_API_KEY.")
        return
    cle = getpass.getpass("Collez votre cle API Mistral puis Entree (rien ne s'affiche) : ").strip()
    if not cle:
        sys.exit("Aucune cle saisie.")
    os.environ["MISTRAL_API_KEY"] = cle      # pour les sous-processus de cette execution seulement


def lancer(cmd, cwd):
    print("> " + " ".join(str(c) for c in cmd) + "\n")
    t0 = time.perf_counter()
    code = subprocess.call([str(c) for c in cmd], cwd=str(cwd))
    if code != 0:
        sys.exit(f"\nEchec (code {code}). Corrigez l'erreur ci-dessus puis relancez : "
                 f"les appels Mistral deja faits sont en cache et ne seront pas repayes.")
    return time.perf_counter() - t0


def lire_csv(path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh, delimiter=";"))


def pct(v):
    v = float(v)
    return v * 100 if v <= 1 else v


def afficher_resultats():
    titre("RESULTATS (43 documents, matching souple)")
    print(f"{'':42} | {'Ent P':>6} {'Ent R':>6} {'Ent F1':>6} | {'Rel P':>6} {'Rel R':>6} {'Rel F1':>6}")
    for nom, v in AVANT.items():
        print(f"{nom:42} | " + " ".join(f"{x:6.2f}" for x in v[:3]) + " | " + " ".join(f"{x:6.2f}" for x in v[3:]))
    lignes = {r.get("etage", r.get("﻿etage", "")): r for r in lire_csv(EVAL_DIR / "tableau.csv")}
    for etage, nom in (("01_preparation", "Avec seconde passe, avant TRACE"),
                       ("07_arbitrage", "Avec seconde passe + TRACE v2 standard")):
        r = lignes.get(etage)
        if r:
            try:
                vals = [pct(r[k]) for k in ("ent_P", "ent_R", "ent_F1", "rel_P", "rel_R", "rel_F1")]
                print(f"{nom:42} | " + " ".join(f"{x:6.2f}" for x in vals[:3]) + " | "
                      + " ".join(f"{x:6.2f}" for x in vals[3:]))
            except (KeyError, ValueError):
                pass
    cv = lire_csv(EVAL_DIR / "vote_agents_validation.csv")
    if cv:
        print("\nMode precision avec seconde passe (validation croisee, documents non vus) :")
        for r in cv:
            print(f"  garder {r['garder_pct']:>3} % | Ent P {pct(r['ent_P']):6.2f} R {pct(r['ent_R']):6.2f} "
                  f"F1 {pct(r['ent_F1']):6.2f} | Rel P {pct(r['rel_P']):6.2f} R {pct(r['rel_R']):6.2f} "
                  f"F1 {pct(r['rel_F1']):6.2f}")
    print(f"\nTableau complet : {EVAL_DIR / 'tableau.csv'}")


def main():
    ap = argparse.ArgumentParser(description="Seconde passe Mistral puis TRACE v2, en une commande.")
    ap.add_argument("--essai", action="store_true")
    ap.add_argument("--docs", type=int, default=0)
    ap.add_argument("--sans-trace", action="store_true")
    ap.add_argument("--sans-reentrainer", action="store_true")
    ap.add_argument("--echantillons", type=int, default=3)
    ap.add_argument("--vote", type=int, default=2)
    ap.add_argument("--pause", type=float, default=1.5)
    args = ap.parse_args()
    if args.essai:
        args.docs, args.sans_trace = 2, True

    verifier()
    demander_cle()

    titre("1/2  SECONDE PASSE MISTRAL (etage 0b)")
    cmd = [sys.executable, SECONDE_PASSE, "--entree", ENTREE, "--sortie", SORTIE,
           "--echantillons", args.echantillons, "--vote", args.vote, "--pause", args.pause]
    if args.docs:
        cmd += ["--docs", args.docs]
    duree = lancer(cmd, ROOT)
    print(f"\nSeconde passe terminee en {duree / 60:.1f} min. Sortie : {SORTIE}")

    if args.sans_trace:
        if args.essai:
            print("\nEssai reussi. Lancez maintenant le calcul complet :\n    python lancer_trace_complet.py")
        return 0
    if args.docs:
        print(f"\nAttention : seule une partie des documents ({args.docs}) est passee par la seconde "
              "passe ; TRACE v2 n'evaluera que ces documents.")

    titre("2/2  TRACE v2 (etages 1 a 8) sur la sortie de la seconde passe")
    cmd = [sys.executable, "run_trace_v2.py", "--entree", SORTIE]
    if not args.sans_reentrainer:
        cmd.append("--entrainer-vote")
    duree = lancer(cmd, TRACE_DIR)
    print(f"\nTRACE v2 termine en {duree / 60:.1f} min.")

    afficher_resultats()
    print("\nPour m'envoyer les resultats :\n"
          "    git add extraction_mistral/seconde_passe TRACE_v2/sorties/08_evaluation TRACE_v2/modele\n"
          "    git commit -m \"Seconde passe Mistral + TRACE v2\"\n"
          "    git push origin claude/epic-darwin-ygtsx2")
    return 0


if __name__ == "__main__":
    sys.exit(main())
