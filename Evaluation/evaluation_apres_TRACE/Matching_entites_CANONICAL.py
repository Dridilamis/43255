import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import os
import json
import csv
import re
import unicodedata
from difflib import SequenceMatcher
from collections import defaultdict
from pathlib import Path


# ============================================================
# CONFIGURATION — BEST ENTITES V6.5 / 43 DOCUMENTS
# ============================================================

import sys

if os.name == "nt":
    BASE_DIR = (
        Path(r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM")
    )
else:
    BASE_DIR = Path.home() / "TRACE" / "OCR vers LLM"

# Usage facultatif :
# python Matching_entites_BEST_43_V6_5.py GOLD_DIR PRED_DIR OUTPUT_DIR
#
# Sans argument, les chemins suivants sont utilisés.
GOLD_DIR = str(
    Path(sys.argv[1])
    if len(sys.argv) >= 2
    else BASE_DIR / "gold_canonical_par_documentF"
)

MLLM_DIR = str(
    Path(sys.argv[2])
    if len(sys.argv) >= 3
    else BASE_DIR / "Mistral" / "POSTPROCESSING_FINAL_V7_6_PRECISION_RECALL_GATED_43"
)

OUTPUT_DIR = str(
    Path(sys.argv[3])
    if len(sys.argv) >= 4
    else BASE_DIR / "evaluation_entities_V6_6c_PRECISION_PLUS_43"
)

if not os.path.isdir(GOLD_DIR):
    raise FileNotFoundError(
        "\nDossier Gold introuvable : "
        f"{GOLD_DIR}\n"
        "Le matching nécessite les Gold canonicalisés des documents.\n"
        "Si ton dossier Gold porte un autre nom, lance par exemple :\n"
        'python .\\Matching_entites_BEST_43_V6_5.py '
        '"C:\\chemin\\vers\\gold" '
        '"C:\\Users\\techlabo\\Desktop\\TRACE\\OCR vers LLM\\BEST_43_Entites_V6_5_FINAL"'
    )

if not os.path.isdir(MLLM_DIR):
    raise FileNotFoundError(
        "\nDossier des prédictions canonicalisées introuvable : "
        f"{MLLM_DIR}\n"
        "Lance d'abord la canonicalisation V6.5."
    )

os.makedirs(OUTPUT_DIR, exist_ok=True)

print("\n=== MATCHING ENTITES — V6.6c PRECISION+ / 43 DOCUMENTS ===")
print("GOLD_DIR   =", GOLD_DIR)
print("PRED_DIR   =", MLLM_DIR)
print("OUTPUT_DIR =", OUTPUT_DIR)
print("====================================================\n")

# Matching fuzzy
RELAXED_THRESHOLD = 0.85

# Containment :
# éviter qu'un mot très court comme "rein", "foie", "IV" matche
# automatiquement une expression longue.
MIN_CONTAINMENT_LENGTH = 4


# ============================================================
# NORMALISATION
# ============================================================

def remove_accents(text):
    """
    Supprime les accents uniquement pour le matching.

    Exemple :
        "altération" -> "alteration"
    """
    if text is None:
        return ""

    text = unicodedata.normalize("NFD", str(text))

    return "".join(
        char
        for char in text
        if unicodedata.category(char) != "Mn"
    )


def normalize_text(text):
    """
    Normalisation générique pour comparaison.

    Exemple :
        "Altération_de_l'état_général"
        -> "alteration de l etat general"

        "37,2 °C"
        -> "37.2 °c"
    """

    if text is None:
        return ""

    text = str(text).strip().lower()

    # Unicode
    text = remove_accents(text)

    # apostrophes différentes
    text = text.replace("’", "'")
    text = text.replace("`", "'")

    # underscore -> espace
    text = text.replace("_", " ")

    # virgule décimale
    text = re.sub(
        r"(?<=\d),(?=\d)",
        ".",
        text
    )

    # apostrophe -> espace
    # ex: l'état -> l etat
    text = text.replace("'", " ")

    # ponctuation interne -> espace
    text = re.sub(
        r"[()\[\]{}:;,!?/\\|]+",
        " ",
        text
    )

    # tirets multiples / dash unicode
    text = re.sub(
        r"[-–—]+",
        " ",
        text
    )

    # espaces multiples
    text = re.sub(
        r"\s+",
        " ",
        text
    )

    # ponctuation périphérique
    text = text.strip(
        " \t\n\r.,;:!?()[]{}\"'"
    )

    return text


def normalize_entity_type(entity_type):
    if entity_type is None:
        return ""

    raw = str(entity_type).strip()
    if not raw:
        return ""

    key = normalize_text(raw).replace(" ", "_").upper()

    aliases = {
        "COMORBIDITE": "COMORBIDITE_ANTECEDENT",
        "COMORBIDITE_ANTECEDENT": "COMORBIDITE_ANTECEDENT",
        "SCORE_QSOFA": "SCORE_qSOFA",
        "SCORE_Q_SOFA": "SCORE_qSOFA",
        "SCORE_SOFA": "SCORE_SOFA",
        "DONNEE_PATIENT": "DONNEE_PATIENT",
        "LABEL_NOSOLOGIQUE": "LABEL_NOSOLOGIQUE",
        "SIGNE_VITAL": "SIGNE_VITAL",
        "BIOMARQUEUR": "BIOMARQUEUR",
        "SCORE_NEUROLOGIQUE": "SCORE_NEUROLOGIQUE",
        "STADE_IRA": "STADE_IRA",
        "FOYER_INFECTIEUX": "FOYER_INFECTIEUX",
        "MICRO_ORGANISME": "MICRO_ORGANISME",
        "DEFAILLANCE_ORGANE": "DEFAILLANCE_ORGANE",
        "TRAITEMENT": "TRAITEMENT",
        "POSOLOGIE": "POSOLOGIE",
        "CONTEXTE_ACQUISITION": "CONTEXTE_ACQUISITION",
        "EVENEMENT_TEMPOREL": "EVENEMENT_TEMPOREL",
        "EVOLUTION_PRONOSTIC": "EVOLUTION_PRONOSTIC",
        "SERVICE_MEDICAL": "SERVICE_MEDICAL",
        "IMAGERIE_PROCEDURE": "IMAGERIE_PROCEDURE",
        "SYMPTOME": "SYMPTOME",
        "METADONNEES_PIPELINE": "METADONNEES_PIPELINE",
    }

    return aliases.get(key, raw.strip())


def get_entity_name(entity):
    for field in ("name", "mention", "text", "preuve"):
        value = entity.get(field)
        if value is not None and str(value).strip():
            return str(value).strip()

    value = entity.get("valeur")
    if value is not None and str(value).strip():
        return str(value).strip()

    return ""


def get_entity_type(entity):
    for field in ("type", "categorie", "label"):
        value = entity.get(field)
        if value is not None and str(value).strip():
            return normalize_entity_type(value)
    return ""


# ============================================================
# SIMILARITÉ
# ============================================================

def similarity(a, b):

    a = normalize_text(a)
    b = normalize_text(b)

    if not a or not b:
        return 0.0

    if a == b:
        return 1.0

    return SequenceMatcher(
        None,
        a,
        b
    ).ratio()


# ============================================================
# CONTAINMENT
# ============================================================

def containment_score(a, b):
    a = normalize_text(a)
    b = normalize_text(b)

    if not a or not b or a == b:
        return 0.0

    shorter = a if len(a) <= len(b) else b
    longer = b if len(a) <= len(b) else a

    if len(shorter) < MIN_CONTAINMENT_LENGTH:
        return 0.0

    pattern = r"(?<!\w)" + re.escape(shorter) + r"(?!\w)"
    if not re.search(pattern, longer):
        return 0.0

    score = len(shorter) / len(longer)

    if score < 0.35:
        return 0.0

    return score


# ============================================================
# CHARGEMENT JSON
# ============================================================

def load_json(path):

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


# ============================================================
# EXTRACTION DES ENTITÉS
# ============================================================

def extract_entities(document_json):
    entities = []

    if not isinstance(document_json, dict):
        return entities

    pages = document_json.get("pages", [])

    if isinstance(pages, list) and pages:
        for page in pages:
            if not isinstance(page, dict):
                continue

            page_number = page.get("page")

            page_entities = page.get("entities")
            if not isinstance(page_entities, list):
                page_entities = page.get("entites", [])

            if not isinstance(page_entities, list):
                continue

            for occurrence_index, entity in enumerate(page_entities):
                if not isinstance(entity, dict):
                    continue

                name = get_entity_name(entity)
                entity_type = get_entity_type(entity)

                if not name or not entity_type:
                    continue

                entities.append({
                    "page": page_number,
                    "name": name,
                    "normalized_name": normalize_text(name),
                    "type": entity_type,
                    "matched": False,
                    "occurrence_index": occurrence_index,
                    "entity_id": (
                        entity.get("identifiant_entite")
                        or entity.get("id")
                        or ""
                    )
                })

        return entities

    top_entities = None
    for field in (
        "entities",
        "entites",
        "global_entities",
        "global_entites"
    ):
        value = document_json.get(field)
        if isinstance(value, list):
            top_entities = value
            break

    if not isinstance(top_entities, list):
        return entities

    for occurrence_index, entity in enumerate(top_entities):
        if not isinstance(entity, dict):
            continue

        name = get_entity_name(entity)
        entity_type = get_entity_type(entity)

        if not name or not entity_type:
            continue

        page_number = entity.get("page")

        entities.append({
            "page": page_number,
            "name": name,
            "normalized_name": normalize_text(name),
            "type": entity_type,
            "matched": False,
            "occurrence_index": occurrence_index,
            "entity_id": (
                entity.get("identifiant_entite")
                or entity.get("id")
                or ""
            )
        })

    return entities


# ============================================================
# UTILITAIRE RÉSULTAT
# ============================================================

def build_match_result(
    gold,
    pred,
    status,
    score
):

    return {
        "page": gold["page"],

        "gold_name": gold["name"],
        "gold_type": gold["type"],

        "pred_name": pred["name"],
        "pred_type": pred["type"],

        "similarity": round(score, 4),

        "status": status
    }


# ============================================================
# 1. MATCH EXACT
# ============================================================

def exact_matching(
    gold_entities,
    pred_entities
):

    matches = []

    for gold in gold_entities:

        if gold["matched"]:
            continue

        for pred in pred_entities:

            if pred["matched"]:
                continue

            if gold["page"] != pred["page"]:
                continue

            if gold["type"] != pred["type"]:
                continue

            if (
                gold["normalized_name"]
                != pred["normalized_name"]
            ):
                continue

            gold["matched"] = True
            pred["matched"] = True

            matches.append(
                build_match_result(
                    gold,
                    pred,
                    "TP_EXACT",
                    1.0
                )
            )

            break

    return matches


# ============================================================
# 2. MATCH CONTAINMENT
# ============================================================

def containment_matching(
    gold_entities,
    pred_entities
):

    candidates = []

    for g_index, gold in enumerate(
        gold_entities
    ):

        if gold["matched"]:
            continue

        for p_index, pred in enumerate(
            pred_entities
        ):

            if pred["matched"]:
                continue

            if gold["page"] != pred["page"]:
                continue

            # même type obligatoire
            if gold["type"] != pred["type"]:
                continue

            score = containment_score(
                gold["name"],
                pred["name"]
            )

            if score > 0:

                candidates.append(
                    (
                        score,
                        g_index,
                        p_index
                    )
                )

    # meilleurs containments d'abord
    candidates.sort(
        key=lambda x: x[0],
        reverse=True
    )

    matches = []

    for score, g_index, p_index in candidates:

        gold = gold_entities[g_index]
        pred = pred_entities[p_index]

        if gold["matched"] or pred["matched"]:
            continue

        gold["matched"] = True
        pred["matched"] = True

        matches.append(
            build_match_result(
                gold,
                pred,
                "TP_CONTAINMENT",
                score
            )
        )

    return matches


# ============================================================
# 3. MATCH RELAXED / FUZZY
# ============================================================

def relaxed_matching(
    gold_entities,
    pred_entities,
    threshold
):

    candidates = []

    for g_index, gold in enumerate(
        gold_entities
    ):

        if gold["matched"]:
            continue

        for p_index, pred in enumerate(
            pred_entities
        ):

            if pred["matched"]:
                continue

            if gold["page"] != pred["page"]:
                continue

            if gold["type"] != pred["type"]:
                continue

            score = similarity(
                gold["name"],
                pred["name"]
            )

            if score >= threshold:

                candidates.append(
                    (
                        score,
                        g_index,
                        p_index
                    )
                )

    candidates.sort(
        key=lambda x: x[0],
        reverse=True
    )

    matches = []

    for score, g_index, p_index in candidates:

        gold = gold_entities[g_index]
        pred = pred_entities[p_index]

        if gold["matched"] or pred["matched"]:
            continue

        gold["matched"] = True
        pred["matched"] = True

        matches.append(
            build_match_result(
                gold,
                pred,
                "TP_RELAXED",
                score
            )
        )

    return matches


# ============================================================
# 4. WRONG TYPE
# ============================================================

def wrong_type_matching(
    gold_entities,
    pred_entities
):

    """
    Après tous les matches valides.

    Même page + nom exact normalisé
    MAIS catégorie différente.
    """

    candidates = []

    for g_index, gold in enumerate(
        gold_entities
    ):

        if gold["matched"]:
            continue

        for p_index, pred in enumerate(
            pred_entities
        ):

            if pred["matched"]:
                continue

            if gold["page"] != pred["page"]:
                continue

            if gold["type"] == pred["type"]:
                continue

            score = similarity(
                gold["name"],
                pred["name"]
            )

            # exact nom normalisé
            if (
                gold["normalized_name"]
                == pred["normalized_name"]
            ):
                score = 1.0

            else:
                # on autorise aussi une forte similarité
                # pour détecter les erreurs de catégorie
                if score < RELAXED_THRESHOLD:
                    continue

            candidates.append(
                (
                    score,
                    g_index,
                    p_index
                )
            )

    candidates.sort(
        key=lambda x: x[0],
        reverse=True
    )

    matches = []

    for score, g_index, p_index in candidates:

        gold = gold_entities[g_index]
        pred = pred_entities[p_index]

        if gold["matched"] or pred["matched"]:
            continue

        gold["matched"] = True
        pred["matched"] = True

        matches.append(
            build_match_result(
                gold,
                pred,
                "WRONG_TYPE",
                score
            )
        )

    return matches


# ============================================================
# 5. FALSE NEGATIVES
# ============================================================

def collect_false_negatives(
    gold_entities
):

    results = []

    for gold in gold_entities:

        if gold["matched"]:
            continue

        results.append({
            "page": gold["page"],

            "gold_name": gold["name"],
            "gold_type": gold["type"],

            "pred_name": "",
            "pred_type": "",

            "similarity": 0.0,

            "status": "FN"
        })

    return results


# ============================================================
# 6. FALSE POSITIVES
# ============================================================

def collect_false_positives(
    pred_entities
):

    results = []

    for pred in pred_entities:

        if pred["matched"]:
            continue

        results.append({
            "page": pred["page"],

            "gold_name": "",
            "gold_type": "",

            "pred_name": pred["name"],
            "pred_type": pred["type"],

            "similarity": 0.0,

            "status": "FP"
        })

    return results


# ============================================================
# MATCHING COMPLET D'UN DOCUMENT
# ============================================================

def match_document(
    gold_json,
    pred_json
):

    gold_entities = extract_entities(
        gold_json
    )

    pred_entities = extract_entities(
        pred_json
    )

    if not gold_entities:
        print("⚠️ Aucune entité Gold lue dans ce document.")
    if not pred_entities:
        print("⚠️ Aucune entité MLLM lue dans ce document.")

    results = []

    # ordre IMPORTANT

    # 1 exact
    results.extend(
        exact_matching(
            gold_entities,
            pred_entities
        )
    )

    # 2 containment
    results.extend(
        containment_matching(
            gold_entities,
            pred_entities
        )
    )

    # 3 relaxed
    results.extend(
        relaxed_matching(
            gold_entities,
            pred_entities,
            RELAXED_THRESHOLD
        )
    )

    # 4 mauvais type
    results.extend(
        wrong_type_matching(
            gold_entities,
            pred_entities
        )
    )

    # 5 FN
    results.extend(
        collect_false_negatives(
            gold_entities
        )
    )

    # 6 FP
    results.extend(
        collect_false_positives(
            pred_entities
        )
    )

    return (
        results,
        len(gold_entities),
        len(pred_entities)
    )


# ============================================================
# NORMALISATION DES NOMS DE DOCUMENTS
# ============================================================

def normalize_document_key(filename):
    """
    Extrait directement l'identifiant original du document.

    Exemples acceptés :
        img20250709_16142502.json
        img20250709_16142502_trace_sepsis_V1.6.json
        img20250709_16142502_trace_sepsis_V1.6-V6.json
        img20250709_16142502_mistral_trace_sepsis_V1.6.json
        img20250709_16142502_texte_brut.json

    Tous deviennent :
        img20250709_16142502
    """

    name = os.path.basename(filename)

    match = re.search(
        r"(img\d{8}_\d+)",
        name,
        flags=re.IGNORECASE
    )

    if match:
        return match.group(1)

    # Fallback si un futur fichier n'utilise pas le format imgXXXXXXXX_XXXX
    name = os.path.splitext(name)[0]

    name = re.sub(
        r"[-_]V\d+$",
        "",
        name,
        flags=re.IGNORECASE
    )

    name = re.sub(
        r"_trace_sepsis(?:_V)?\d+(?:\.\d+)?$",
        "",
        name,
        flags=re.IGNORECASE
    )

    return name


# ============================================================
# APPARIEMENT DES FICHIERS
# ============================================================

gold_files = {
    normalize_document_key(f): f
    for f in os.listdir(GOLD_DIR)
    if f.lower().endswith(".json")
}

pred_files = {
    normalize_document_key(f): f
    for f in os.listdir(MLLM_DIR)
    if f.lower().endswith(".json")
}

common_documents = sorted(
    set(gold_files.keys())
    &
    set(pred_files.keys())
)

missing_prediction = sorted(
    set(gold_files.keys())
    -
    set(pred_files.keys())
)

missing_gold = sorted(
    set(pred_files.keys())
    -
    set(gold_files.keys())
)


print(
    f"\nDocuments Gold : {len(gold_files)}"
)

print(
    f"Documents MLLM : {len(pred_files)}"
)

print(
    f"Documents appariés : {len(common_documents)}"
)

if len(gold_files) == 43 and len(pred_files) == 43 and len(common_documents) == 43:
    print("✅ Matching complet : 43 Gold / 43 prédictions / 43 appariés.")
else:
    print(
        f"⚠️ Matching non complet pour 43 documents : "
        f"Gold={len(gold_files)}, "
        f"Pred={len(pred_files)}, "
        f"Appariés={len(common_documents)}."
    )


if missing_prediction:

    print(
        "\n⚠️ Gold sans prédiction :"
    )

    for doc in missing_prediction:
        print("   ", doc)


if missing_gold:

    print(
        "\n⚠️ Prédiction sans Gold :"
    )

    for doc in missing_gold:
        print("   ", doc)


# ============================================================
# MÉTRIQUES
# ============================================================

def safe_metrics(
    tp,
    fp,
    fn
):

    precision = (
        tp / (tp + fp)
        if (tp + fp) > 0
        else 0.0
    )

    recall = (
        tp / (tp + fn)
        if (tp + fn) > 0
        else 0.0
    )

    f1 = (
        2 * precision * recall
        / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    return (
        precision,
        recall,
        f1
    )


# ============================================================
# ÉVALUATION DE TOUS LES DOCUMENTS
# ============================================================

all_results = []

document_summaries = []


for document in common_documents:

    gold_path = os.path.join(
        GOLD_DIR,
        gold_files[document]
    )

    pred_path = os.path.join(
        MLLM_DIR,
        pred_files[document]
    )

    gold_json = load_json(
        gold_path
    )

    pred_json = load_json(
        pred_path
    )

    (
        results,
        gold_count,
        pred_count
    ) = match_document(
        gold_json,
        pred_json
    )


    for row in results:

        row["document"] = document

        all_results.append(
            row
        )


    # --------------------------------------------------------
    # COMPTAGE
    # --------------------------------------------------------

    tp_exact = sum(
        1
        for r in results
        if r["status"] == "TP_EXACT"
    )

    tp_containment = sum(
        1
        for r in results
        if r["status"] == "TP_CONTAINMENT"
    )

    tp_relaxed = sum(
        1
        for r in results
        if r["status"] == "TP_RELAXED"
    )

    wrong_type = sum(
        1
        for r in results
        if r["status"] == "WRONG_TYPE"
    )

    fp_raw = sum(
        1
        for r in results
        if r["status"] == "FP"
    )

    fn_raw = sum(
        1
        for r in results
        if r["status"] == "FN"
    )


    # ========================================================
    # STRICT
    #
    # seul TP_EXACT est accepté
    # ========================================================

    strict_tp = tp_exact

    strict_fp = (
        fp_raw
        + tp_containment
        + tp_relaxed
        + wrong_type
    )

    strict_fn = (
        fn_raw
        + tp_containment
        + tp_relaxed
        + wrong_type
    )

    (
        strict_precision,
        strict_recall,
        strict_f1
    ) = safe_metrics(
        strict_tp,
        strict_fp,
        strict_fn
    )


    # ========================================================
    # BOUNDARY RELAXED
    #
    # exact + containment
    # ========================================================

    boundary_tp = (
        tp_exact
        + tp_containment
    )

    boundary_fp = (
        fp_raw
        + tp_relaxed
        + wrong_type
    )

    boundary_fn = (
        fn_raw
        + tp_relaxed
        + wrong_type
    )

    (
        boundary_precision,
        boundary_recall,
        boundary_f1
    ) = safe_metrics(
        boundary_tp,
        boundary_fp,
        boundary_fn
    )


    # ========================================================
    # RELAXED
    #
    # exact + containment + fuzzy
    # ========================================================

    relaxed_tp_total = (
        tp_exact
        + tp_containment
        + tp_relaxed
    )

    relaxed_fp_total = (
        fp_raw
        + wrong_type
    )

    relaxed_fn_total = (
        fn_raw
        + wrong_type
    )

    (
        relaxed_precision,
        relaxed_recall,
        relaxed_f1
    ) = safe_metrics(
        relaxed_tp_total,
        relaxed_fp_total,
        relaxed_fn_total
    )


    document_summaries.append({

        "document":
            document,

        "gold_entities":
            gold_count,

        "pred_entities":
            pred_count,

        "tp_exact":
            tp_exact,

        "tp_containment":
            tp_containment,

        "tp_relaxed":
            tp_relaxed,

        "wrong_type":
            wrong_type,

        "fp":
            fp_raw,

        "fn":
            fn_raw,

        # strict
        "precision_strict":
            round(
                strict_precision,
                4
            ),

        "recall_strict":
            round(
                strict_recall,
                4
            ),

        "f1_strict":
            round(
                strict_f1,
                4
            ),

        # boundary relaxed
        "precision_boundary":
            round(
                boundary_precision,
                4
            ),

        "recall_boundary":
            round(
                boundary_recall,
                4
            ),

        "f1_boundary":
            round(
                boundary_f1,
                4
            ),

        # relaxed
        "precision_relaxed":
            round(
                relaxed_precision,
                4
            ),

        "recall_relaxed":
            round(
                relaxed_recall,
                4
            ),

        "f1_relaxed":
            round(
                relaxed_f1,
                4
            )
    })


    print(
        f"✅ {document}"
        f" | Gold={gold_count}"
        f" | Pred={pred_count}"
        f" | Exact={tp_exact}"
        f" | Containment={tp_containment}"
        f" | Relaxed={tp_relaxed}"
        f" | WrongType={wrong_type}"
        f" | FP={fp_raw}"
        f" | FN={fn_raw}"
    )


# ============================================================
# EXPORT MATCHING DÉTAILLÉ
# ============================================================

DETAIL_CSV = os.path.join(
    OUTPUT_DIR,
    "entity_matches_detailed.csv"
)

fieldnames = [
    "document",
    "page",

    "gold_name",
    "gold_type",

    "pred_name",
    "pred_type",

    "similarity",
    "status"
]

with open(
    DETAIL_CSV,
    "w",
    newline="",
    encoding="utf-8-sig"
) as f:

    writer = csv.DictWriter(
        f,
        fieldnames=fieldnames
    )

    writer.writeheader()

    for row in all_results:

        writer.writerow({
            key: row.get(
                key,
                ""
            )
            for key in fieldnames
        })


# ============================================================
# EXPORT PAR DOCUMENT
# ============================================================

DOC_CSV = os.path.join(
    OUTPUT_DIR,
    "entity_metrics_by_document.csv"
)

if document_summaries:

    with open(
        DOC_CSV,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=
                document_summaries[
                    0
                ].keys()
        )

        writer.writeheader()

        writer.writerows(
            document_summaries
        )


# ============================================================
# MÉTRIQUES PAR TYPE
# ============================================================

type_stats = defaultdict(
    lambda: {
        "tp_exact": 0,
        "tp_containment": 0,
        "tp_relaxed": 0,
        "fp": 0,
        "fn": 0,
        "wrong_type_gold": 0,
        "wrong_type_pred": 0
    }
)


for row in all_results:

    status = row["status"]

    gold_type = row.get(
        "gold_type",
        ""
    )

    pred_type = row.get(
        "pred_type",
        ""
    )


    if status == "TP_EXACT":

        type_stats[
            gold_type
        ]["tp_exact"] += 1


    elif status == "TP_CONTAINMENT":

        type_stats[
            gold_type
        ]["tp_containment"] += 1


    elif status == "TP_RELAXED":

        type_stats[
            gold_type
        ]["tp_relaxed"] += 1


    elif status == "FN":

        type_stats[
            gold_type
        ]["fn"] += 1


    elif status == "FP":

        type_stats[
            pred_type
        ]["fp"] += 1


    elif status == "WRONG_TYPE":

        type_stats[
            gold_type
        ]["wrong_type_gold"] += 1

        type_stats[
            pred_type
        ]["wrong_type_pred"] += 1


TYPE_CSV = os.path.join(
    OUTPUT_DIR,
    "entity_metrics_by_type.csv"
)

type_rows = []


for entity_type, stat in sorted(
    type_stats.items()
):

    # relaxed complet
    tp = (
        stat["tp_exact"]
        + stat["tp_containment"]
        + stat["tp_relaxed"]
    )

    fp = (
        stat["fp"]
        + stat["wrong_type_pred"]
    )

    fn = (
        stat["fn"]
        + stat["wrong_type_gold"]
    )

    (
        precision,
        recall,
        f1
    ) = safe_metrics(
        tp,
        fp,
        fn
    )


    type_rows.append({

        "entity_type":
            entity_type,

        "tp_exact":
            stat["tp_exact"],

        "tp_containment":
            stat["tp_containment"],

        "tp_relaxed":
            stat["tp_relaxed"],

        "wrong_type_gold":
            stat["wrong_type_gold"],

        "wrong_type_pred":
            stat["wrong_type_pred"],

        "fp":
            fp,

        "fn":
            fn,

        "precision_relaxed":
            round(
                precision,
                4
            ),

        "recall_relaxed":
            round(
                recall,
                4
            ),

        "f1_relaxed":
            round(
                f1,
                4
            )
    })


with open(
    TYPE_CSV,
    "w",
    newline="",
    encoding="utf-8-sig"
) as f:

    writer = csv.DictWriter(
        f,
        fieldnames=[
            "entity_type",
            "tp_exact",
            "tp_containment",
            "tp_relaxed",
            "wrong_type_gold",
            "wrong_type_pred",
            "fp",
            "fn",
            "precision_relaxed",
            "recall_relaxed",
            "f1_relaxed"
        ]
    )

    writer.writeheader()

    writer.writerows(
        type_rows
    )


# ============================================================
# RÉSUMÉ GLOBAL
# ============================================================

global_tp_exact = sum(
    1
    for x in all_results
    if x["status"] == "TP_EXACT"
)

global_tp_containment = sum(
    1
    for x in all_results
    if x["status"] == "TP_CONTAINMENT"
)

global_tp_relaxed = sum(
    1
    for x in all_results
    if x["status"] == "TP_RELAXED"
)

global_wrong_type = sum(
    1
    for x in all_results
    if x["status"] == "WRONG_TYPE"
)

global_fp_raw = sum(
    1
    for x in all_results
    if x["status"] == "FP"
)

global_fn_raw = sum(
    1
    for x in all_results
    if x["status"] == "FN"
)


# ============================================================
# STRICT GLOBAL
# ============================================================

strict_tp = global_tp_exact

strict_fp = (
    global_fp_raw
    + global_tp_containment
    + global_tp_relaxed
    + global_wrong_type
)

strict_fn = (
    global_fn_raw
    + global_tp_containment
    + global_tp_relaxed
    + global_wrong_type
)

(
    strict_precision,
    strict_recall,
    strict_f1
) = safe_metrics(
    strict_tp,
    strict_fp,
    strict_fn
)


# ============================================================
# BOUNDARY GLOBAL
# ============================================================

boundary_tp = (
    global_tp_exact
    + global_tp_containment
)

boundary_fp = (
    global_fp_raw
    + global_tp_relaxed
    + global_wrong_type
)

boundary_fn = (
    global_fn_raw
    + global_tp_relaxed
    + global_wrong_type
)

(
    boundary_precision,
    boundary_recall,
    boundary_f1
) = safe_metrics(
    boundary_tp,
    boundary_fp,
    boundary_fn
)


# ============================================================
# RELAXED GLOBAL
# ============================================================

relaxed_tp_total = (
    global_tp_exact
    + global_tp_containment
    + global_tp_relaxed
)

relaxed_fp_total = (
    global_fp_raw
    + global_wrong_type
)

relaxed_fn_total = (
    global_fn_raw
    + global_wrong_type
)

(
    relaxed_precision,
    relaxed_recall,
    relaxed_f1
) = safe_metrics(
    relaxed_tp_total,
    relaxed_fp_total,
    relaxed_fn_total
)


# ============================================================
# MACRO F1 PAR DOCUMENT
# ============================================================

if document_summaries:

    macro_f1_strict = sum(
        x["f1_strict"]
        for x in document_summaries
    ) / len(document_summaries)

    macro_f1_boundary = sum(
        x["f1_boundary"]
        for x in document_summaries
    ) / len(document_summaries)

    macro_f1_relaxed = sum(
        x["f1_relaxed"]
        for x in document_summaries
    ) / len(document_summaries)

else:

    macro_f1_strict = 0.0
    macro_f1_boundary = 0.0
    macro_f1_relaxed = 0.0


# ============================================================
# JSON SUMMARY
# ============================================================

summary = {

    "documents_evaluated":
        len(common_documents),

    "configuration": {
        "relaxed_threshold":
            RELAXED_THRESHOLD,

        "min_containment_length":
            MIN_CONTAINMENT_LENGTH
    },

    "counts": {

        "tp_exact":
            global_tp_exact,

        "tp_containment":
            global_tp_containment,

        "tp_relaxed":
            global_tp_relaxed,

        "wrong_type":
            global_wrong_type,

        "fp_remaining":
            global_fp_raw,

        "fn_remaining":
            global_fn_raw
    },

    "strict": {

        "definition":
            "TP_EXACT uniquement",

        "micro_precision":
            round(
                strict_precision,
                4
            ),

        "micro_recall":
            round(
                strict_recall,
                4
            ),

        "micro_f1":
            round(
                strict_f1,
                4
            ),

        "macro_f1_documents":
            round(
                macro_f1_strict,
                4
            )
    },

    "boundary_relaxed": {

        "definition":
            "TP_EXACT + TP_CONTAINMENT",

        "micro_precision":
            round(
                boundary_precision,
                4
            ),

        "micro_recall":
            round(
                boundary_recall,
                4
            ),

        "micro_f1":
            round(
                boundary_f1,
                4
            ),

        "macro_f1_documents":
            round(
                macro_f1_boundary,
                4
            )
    },

    "relaxed": {

        "definition":
            "TP_EXACT + TP_CONTAINMENT + TP_RELAXED",

        "micro_precision":
            round(
                relaxed_precision,
                4
            ),

        "micro_recall":
            round(
                relaxed_recall,
                4
            ),

        "micro_f1":
            round(
                relaxed_f1,
                4
            ),

        "macro_f1_documents":
            round(
                macro_f1_relaxed,
                4
            )
    },

    "missing_prediction":
        missing_prediction,

    "missing_gold":
        missing_gold
}


SUMMARY_JSON = os.path.join(
    OUTPUT_DIR,
    "entity_evaluation_summary.json"
)


with open(
    SUMMARY_JSON,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        summary,
        f,
        ensure_ascii=False,
        indent=2
    )


# ============================================================
# FIN
# ============================================================

print("\n")
print("=" * 75)
print("ÉVALUATION DES ENTITÉS V6.6c PRECISION+ TERMINÉE")
print("=" * 75)

print(
    f"Documents évalués      : {len(common_documents)}"
)

print(
    f"TP exact                : {global_tp_exact}"
)

print(
    f"TP containment          : {global_tp_containment}"
)

print(
    f"TP relaxed              : {global_tp_relaxed}"
)

print(
    f"Wrong type              : {global_wrong_type}"
)

print(
    f"FP restants             : {global_fp_raw}"
)

print(
    f"FN restants             : {global_fn_raw}"
)


print("\n--- STRICT ---")

print(
    "Micro Precision :",
    round(
        strict_precision,
        4
    )
)

print(
    "Micro Recall    :",
    round(
        strict_recall,
        4
    )
)

print(
    "Micro F1        :",
    round(
        strict_f1,
        4
    )
)

print(
    "Macro F1 docs   :",
    round(
        macro_f1_strict,
        4
    )
)


print("\n--- BOUNDARY RELAXED ---")

print(
    "Micro Precision :",
    round(
        boundary_precision,
        4
    )
)

print(
    "Micro Recall    :",
    round(
        boundary_recall,
        4
    )
)

print(
    "Micro F1        :",
    round(
        boundary_f1,
        4
    )
)

print(
    "Macro F1 docs   :",
    round(
        macro_f1_boundary,
        4
    )
)


print("\n--- RELAXED ---")

print(
    "Micro Precision :",
    round(
        relaxed_precision,
        4
    )
)

print(
    "Micro Recall    :",
    round(
        relaxed_recall,
        4
    )
)

print(
    "Micro F1        :",
    round(
        relaxed_f1,
        4
    )
)

print(
    "Macro F1 docs   :",
    round(
        macro_f1_relaxed,
        4
    )
)


print(
    "\nRésultats :",
    OUTPUT_DIR
)