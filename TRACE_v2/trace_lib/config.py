# -*- coding: utf-8 -*-
"""Chemins et constantes de TRACE v2. Tous les seuils sont fixes a priori, jamais sur le gold."""
import os
from pathlib import Path

V2 = Path(__file__).resolve().parents[1]          # .../Reduction_hallucinations/TRACE_v2
PROJECT = V2.parent                                # .../Reduction_hallucinations
BASE = PROJECT.parent                              # .../OCR vers LLM

# Entree : sortie brute du post-traitement Mistral (version qui contient encore les
# relations guidees par le gold ; l'Etage 1 les retire).
# Chaque chemin peut etre remplace par une variable d'environnement (utilise par
# lancer_trace_v2_0.py) ; sans variable, la configuration d'origine est inchangee.
def _env(name, default):
    value = os.environ.get(name, "").strip()
    return Path(value) if value else default


INPUT_DIR = _env("TRACE_ENTREE", PROJECT / "SortieJson_Postprocessing")
RAW_TEXT_DIR = _env("TRACE_TEXTES", PROJECT / "Sortie_Textes_Brut_MistralSmall4")
SGCE_DIR = PROJECT / "SGCE"
GOLD_DIR_CANDIDATES = [BASE / "gold_canonical_par_documentF", PROJECT / "SGCE" / "gold_canonical_par_documentF"]
if os.environ.get("TRACE_GOLD", "").strip():
    GOLD_DIR_CANDIDATES = [Path(os.environ["TRACE_GOLD"].strip())]
GUIDELINE_CANDIDATES = [BASE / "Guideline_TRACE_Sepsis_v1.6.json", PROJECT / "Guideline_TRACE_Sepsis_v1.6.json"]
# Guideline des etages 3 et 7 (signatures) ; SGCE garde GUIDELINE_CANDIDATES.
GUIDELINE_TRACE = _env("TRACE_GUIDELINE", None)
SIGNATURES_SNAPSHOT = Path(__file__).resolve().parent / "ontologie_signatures_v1.6.json"
MATCHERS_DIR = PROJECT / "Evaluation" / "TRACE_Ablation_F1"

OUT = _env("TRACE_SORTIES", V2 / "sorties")
STAGE_DIRS = {
    1: OUT / "01_preparation",
    2: OUT / "02_ancrage",
    3: OUT / "03_conformite_guideline",
    4: OUT / "04_sgce",
    "4b": OUT / "04b_recuperation",
    5: OUT / "05_dedoublonnage",
    6: OUT / "06_attributs",
    7: OUT / "07_arbitrage",
}
EVAL_DIR = OUT / "08_evaluation"
MODEL_FILE = (OUT / "modele" / "vote_agents.json") if os.environ.get("TRACE_SORTIES", "").strip() \
    else V2 / "modele" / "vote_agents.json"

# Ancrage documentaire
MIN_TOKEN_COVERAGE = 0.5        # majorite simple des mots porteurs de sens
PREFIX_LEN = 5                  # tolere flexions/accords
COOCCURRENCE_WINDOW = 300       # ~ un paragraphe de compte rendu
LINE_WINDOW = 80                # ~ une ligne
CUE_WINDOW = 40                 # indices de negation/hypothese juste avant la mention
