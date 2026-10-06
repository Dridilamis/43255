# -*- coding: utf-8 -*-
"""
TRACE — Evaluation finale après réduction des hallucinations.

IMPORTANT :
- même Gold Standard ;
- mêmes algorithmes de matching que l'évaluation baseline ;
- aucune canonicalisation supplémentaire ;
- entrée = sortie validée de l'Etage 8.
"""
from pathlib import Path
import os
import subprocess
import sys

HERE = Path(__file__).resolve().parent

if os.name == "nt":
    BASE_DIR = (
        Path(r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM")
    )
else:
    BASE_DIR = Path.home() / "TRACE" / "OCR vers LLM"

GOLD_DIR = BASE_DIR / "gold_canonical_par_documentF"
PRED_DIR = (
    BASE_DIR / "Reduction_hallucinations"
    / "confidence Etage 8" / "confidence_assessed_safe"
)
OUTPUT_ROOT = (
    BASE_DIR / "Reduction_hallucinations"
    / "evaluation_apres_TRACE"
)
ENTITY_OUT = OUTPUT_ROOT / "entities"
RELATION_OUT = OUTPUT_ROOT / "relations"

for p, label in [(GOLD_DIR, "Gold Standard"), (PRED_DIR, "sortie TRACE")]:
    if not p.is_dir():
        raise SystemExit(f"ECHEC : dossier {label} introuvable : {p}")

ENTITY_OUT.mkdir(parents=True, exist_ok=True)
RELATION_OUT.mkdir(parents=True, exist_ok=True)

print("=" * 100)
print("TRACE — EVALUATION APRES REDUCTION DES HALLUCINATIONS")
print("=" * 100)
print("Gold Standard :", GOLD_DIR)
print("Predictions   :", PRED_DIR)
print("Sorties       :", OUTPUT_ROOT)
print("\nAucun post-processing n'est relance avant l'evaluation.")
print("Les mêmes matchers que pour la baseline sont utilisés.")

commands = [
    (
        "ENTITES",
        HERE / "Matching_entites_APRES_TRACE.py",
        ENTITY_OUT,
    ),
    (
        "RELATIONS",
        HERE / "Matching_relations_APRES_TRACE.py",
        RELATION_OUT,
    ),
]

for label, script, output_dir in commands:
    print("\n" + "=" * 100)
    print(f"EVALUATION {label}")
    print("=" * 100)
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            str(GOLD_DIR),
            str(PRED_DIR),
            str(output_dir),
        ],
        cwd=str(HERE),
    )
    if result.returncode != 0:
        raise SystemExit(
            f"ECHEC pendant l'evaluation {label} "
            f"(code {result.returncode})."
        )

print("\n" + "=" * 100)
print("EVALUATION APRES TRACE : TERMINEE")
print("=" * 100)
print("Entites   :", ENTITY_OUT)
print("Relations :", RELATION_OUT)
