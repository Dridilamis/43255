# -*- coding: utf-8 -*-
"""
TRACE v2 - lanceur global. Une responsabilite par etage :

  1 Preparation           retire les relations guidees par le gold, normalise
  2 Ancrage documentaire  confronte entites et relations au texte ; retire l'impossible
  3 Validation ontologie  confronte chaque relation aux signatures v1.6 (annote)
  4 SGCE                  Patterns A-D, Relation Repair, Orphelins, Multi-Agent (code existant)
  4b Recuperation         ajoute les entites oubliees dans la biologie et les ordonnances
  5 Dedoublonnage         fusionne/retire l'identique, annote les repetitions
  6 Attributs cliniques   unite, temporalite, negation, hypothese des entites (annote)
  7 Agents et arbitrage   seul etage qui decide (entites et relations) ; modes standard / precision
  8 Evaluation            seul etage qui lit le gold

Usage (depuis Reduction_hallucinations\\TRACE_v2) :
    python run_trace_v2.py                  # etages 1 a 8
    python run_trace_v2.py --from 5         # reprend a l'etage 5
    python run_trace_v2.py --entrainer-vote # reentraine le vote des agents (gold) avant l'etage 7
    python run_trace_v2.py --entree ..\\extraction_mistral\\seconde_passe
                                            # autre entree (ex. sortie de la seconde passe Mistral)
    python run_trace_v2.py --garder 80 --garder-entites 80
                                            # parts gardees par le mode precision (defaut 80)
Aucun fichier du projet existant n'est modifie : tout est ecrit dans TRACE_v2/sorties.
"""
import sys
import time

import etage1_preparation
import etage2_ancrage
import etage3_ontologie
import etage4_sgce
import etage4b_recuperation
import etage5_dedoublonnage
import etage6_attributs
import etage7_arbitrage
import etage8_evaluation


def main():
    argv = sys.argv[1:]
    start = float(argv[argv.index("--from") + 1].replace("b", ".5")) if "--from" in argv else 1
    keep = int(argv[argv.index("--garder") + 1]) if "--garder" in argv else 80
    keep_ent = int(argv[argv.index("--garder-entites") + 1]) if "--garder-entites" in argv else 80
    entree = argv[argv.index("--entree") + 1] if "--entree" in argv else None
    t0 = time.perf_counter()
    steps = [
        (1, lambda: etage1_preparation.main(entree)),
        (2, etage2_ancrage.main),
        (3, etage3_ontologie.main),
        (4, etage4_sgce.main),
        (4.5, etage4b_recuperation.main),
        (5, etage5_dedoublonnage.main),
        (6, etage6_attributs.main),
    ]
    for num, fn in steps:
        if num >= start:
            fn()
            print()
    if start <= 7:
        if "--entrainer-vote" in argv:
            sys.argv = [sys.argv[0], "--entrainer-vote"]
            etage8_evaluation.train_vote()
            print()
        etage7_arbitrage.main(mode="standard")
        print()
        etage7_arbitrage.main(mode="precision", keep=keep, keep_ent=keep_ent)
        print()
    sys.argv = [sys.argv[0]]
    etage8_evaluation.main()
    print(f"\nTRACE v2 TERMINE - {time.perf_counter() - t0:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
