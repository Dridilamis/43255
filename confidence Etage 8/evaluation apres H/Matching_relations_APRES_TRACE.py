# -*- coding: utf-8 -*-

import os
import sys
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

# Même racine que pour le matching des entités V6.5 FULL.
if os.name == "nt":
    BASE_DIR = (
        Path(r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM")
    )
else:
    BASE_DIR = Path.home() / "TRACE" / "OCR vers LLM"

GOLD_DIR = str(
    Path(sys.argv[1])
    if len(sys.argv) >= 2
    else BASE_DIR / "gold_canonical_par_documentF"
)
PRED_DIR = str(
    Path(sys.argv[2])
    if len(sys.argv) >= 3
    else BASE_DIR / "Reduction_hallucinations" / "confidence Etage 8" / "confidence_assessed_safe"
)

OUTPUT_DIR = str(
    Path(sys.argv[3])
    if len(sys.argv) >= 4
    else BASE_DIR / "Reduction_hallucinations" / "evaluation_apres_TRACE" / "relations"
)

if not os.path.isdir(GOLD_DIR):
    raise FileNotFoundError(f"Dossier Gold introuvable : {GOLD_DIR}")
if not os.path.isdir(PRED_DIR):
    raise FileNotFoundError(f"Dossier des prédictions TRACE introuvable : {PRED_DIR}")

RELAXED_THRESHOLD = 0.80
WRONG_TYPE_THRESHOLD = 0.80

os.makedirs(OUTPUT_DIR, exist_ok=True)

print("\n=== CONFIGURATION EVALUATION RELATIONS V6.9k RECALL-BOOST CONTROLLED ===")
print("GOLD_DIR =", GOLD_DIR)
print("PRED_DIR =", PRED_DIR)
print("OUTPUT_DIR =", OUTPUT_DIR)
print("RELAXED_THRESHOLD =", RELAXED_THRESHOLD)
print("====================================================\n")


# ============================================================
# NORMALISATION
# ============================================================

def remove_accents(text):
    if text is None:
        return ""

    text = unicodedata.normalize("NFD", str(text))

    return "".join(
        c
        for c in text
        if unicodedata.category(c) != "Mn"
    )


def normalize_text(text):
    if text is None:
        return ""

    text = str(text).strip().lower()
    text = remove_accents(text)

    text = (
        text
        .replace("’", "'")
        .replace("`", "'")
        .replace("_", " ")
    )

    # virgule décimale -> point
    text = re.sub(
        r"(?<=\d),(?=\d)",
        ".",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def normalize_relation_type(value):
    if value is None:
        return ""

    return str(value).strip()


def normalize_document_key(filename):
    """
    Exemples :
      img20250709_16142502.json
        -> img20250709_16142502

      img20250709_16142502_trace_sepsis_V1.6.json
        -> img20250709_16142502

      img20250709_16142502_mistral_trace_sepsis_V1.6.json
        -> img20250709_16142502
    """
    name = os.path.basename(str(filename))

    match = re.search(
        r"(img\d+_\d+)",
        name,
        flags=re.IGNORECASE
    )

    if match:
        return match.group(1)

    name = os.path.splitext(name)[0]

    name = re.sub(
        r"_(?:gemini|qwen|pixtral|mixtral|mistral(?:_small4)?|mistral_small_4)"
        r"_trace_sepsis(?:_v)?\d+(?:\.\d+)?$",
        "",
        name,
        flags=re.IGNORECASE
    )

    name = re.sub(
        r"_trace_sepsis(?:_v)?\d+(?:\.\d+)?$",
        "",
        name,
        flags=re.IGNORECASE
    )

    return name


# ============================================================
# SIMILARITÉ
# ============================================================

def levenshtein_distance(a, b):
    a = normalize_text(a)
    b = normalize_text(b)

    if a == b:
        return 0

    if not a:
        return len(b)

    if not b:
        return len(a)

    previous = list(range(len(b) + 1))

    for i, ca in enumerate(a, start=1):
        current = [i]

        for j, cb in enumerate(b, start=1):
            current.append(
                min(
                    current[j - 1] + 1,
                    previous[j] + 1,
                    previous[j - 1] + (0 if ca == cb else 1)
                )
            )

        previous = current

    return previous[-1]


def similarity(a, b):
    a = normalize_text(a)
    b = normalize_text(b)

    if not a and not b:
        return 1.0

    if not a or not b:
        return 0.0

    if a == b:
        return 1.0

    distance = levenshtein_distance(a, b)

    return 1.0 - (
        distance / max(len(a), len(b))
    )


def containment_score(a, b):
    a = normalize_text(a)
    b = normalize_text(b)

    if not a or not b:
        return 0.0

    if a == b:
        return 1.0

    shorter = a if len(a) <= len(b) else b
    longer = b if len(a) <= len(b) else a

    if len(shorter) < 4:
        return 0.0

    pattern = (
        r"(?<!\w)"
        + re.escape(shorter)
        + r"(?!\w)"
    )

    if not re.search(pattern, longer):
        return 0.0

    return len(shorter) / len(longer)


def endpoint_score(gold_text, pred_text):
    return max(
        similarity(
            gold_text,
            pred_text
        ),
        containment_score(
            gold_text,
            pred_text
        )
    )


def relation_similarity(gold, pred):
    subject_score = endpoint_score(
        gold["subject"],
        pred["subject"]
    )

    object_score = endpoint_score(
        gold["object"],
        pred["object"]
    )

    return (
        subject_score
        + object_score
    ) / 2.0


# ============================================================
# JSON
# ============================================================

def load_json(path):
    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:
        return json.load(f)


# ============================================================
# GOLD
# ============================================================

def extract_gold_relations(data):
    """
    Structure observée dans ton Gold canonicalisé :

    {
      "global_relations": [
        {
          "subject": "Patient",
          "subject_normalized": "patient",
          "subject_type": "DONNEE_PATIENT",
          "relation": "presente_symptome",
          "object": "Confusion",
          "object_normalized": "confusion",
          "object_type": "SYMPTOME"
        }
      ]
    }

    global_relations est privilégié parce qu'il est déjà consolidé
    à l'échelle du document et évite les doublons page/global.
    """
    output = []

    if not isinstance(data, dict):
        return output

    relations = data.get(
        "global_relations",
        []
    )

    # Fallback si global_relations absent.
    if not isinstance(relations, list) or not relations:
        relations = []

        for page in data.get("pages", []):
            if not isinstance(page, dict):
                continue

            for relation in page.get(
                "relations",
                []
            ):
                if isinstance(relation, dict):
                    rel = dict(relation)
                    rel.setdefault(
                        "page",
                        page.get("page")
                    )
                    relations.append(rel)

    for index, relation in enumerate(relations):
        if not isinstance(relation, dict):
            continue

        rtype = (
            relation.get("relation")
            or relation.get("type_relation")
            or ""
        )

        subject = (
            relation.get("subject_normalized")
            or relation.get("subject")
            or relation.get("entite_sujet")
            or ""
        )

        obj = (
            relation.get("object_normalized")
            or relation.get("object")
            or relation.get("entite_objet")
            or ""
        )

        if not rtype or not subject or not obj:
            continue

        output.append({
            "subject": str(subject).strip(),
            "subject_type": str(
                relation.get(
                    "subject_type",
                    ""
                )
            ).strip(),

            "relation": str(rtype).strip(),

            "object": str(obj).strip(),
            "object_type": str(
                relation.get(
                    "object_type",
                    ""
                )
            ).strip(),

            "page": relation.get("page"),
            "matched": False,
            "index": index
        })

    return output


# ============================================================
# PRED MLLM
# ============================================================

def get_pred_entity_name(entity):
    """
    Pour le matching de relations on privilégie `name`,
    c.-à-d. la forme canonicalisée destinée au matching.
    """
    if not isinstance(entity, dict):
        return ""

    return str(
        entity.get("name")
        or entity.get("preuve")
        or entity.get("nom_medicament")
        or entity.get("nom_micro_organisme")
        or entity.get("nom_comorbidite")
        or entity.get("nom_service")
        or entity.get("nom_foyer")
        or entity.get("parametre")
        or ""
    ).strip()


def get_pred_entity_type(entity):
    if not isinstance(entity, dict):
        return ""

    return str(
        entity.get("type")
        or entity.get("categorie")
        or ""
    ).strip()


def build_pred_entity_map(data):
    """
    identifiant_entite -> entité
    """
    entity_map = {}

    # 1. global_entities
    for entity in data.get(
        "global_entities",
        []
    ):
        if not isinstance(entity, dict):
            continue

        eid = entity.get(
            "identifiant_entite"
        )

        if not eid:
            continue

        entity_map[str(eid)] = {
            "name": get_pred_entity_name(
                entity
            ),
            "type": get_pred_entity_type(
                entity
            ),
            "page": entity.get("page")
        }

    # 2. compléter avec pages[].entities si nécessaire
    for page in data.get(
        "pages",
        []
    ):
        if not isinstance(page, dict):
            continue

        entities = page.get(
            "entities",
            []
        )

        if not isinstance(entities, list):
            entities = page.get(
                "entites",
                []
            )

        for entity in entities:
            if not isinstance(entity, dict):
                continue

            eid = entity.get(
                "identifiant_entite"
            )

            if not eid:
                continue

            entity_map.setdefault(
                str(eid),
                {
                    "name": get_pred_entity_name(
                        entity
                    ),
                    "type": get_pred_entity_type(
                        entity
                    ),
                    "page": page.get("page")
                }
            )

    return entity_map


def extract_pred_relations(data):
    """
    Structure observée dans ton Mistral :

    {
      "global_relations": [
        {
          "identifiant_entite_sujet": "P2_E009",
          "entite_sujet": "sodium_130_mmol_par_L",
          "type_relation": "biomarqueur_est_critere_de",
          "identifiant_entite_objet": "P2_E008",
          "entite_objet": "SIADH"
        }
      ]
    }

    IMPORTANT :
    nous résolvons les IDs vers global_entities pour récupérer le `name`
    canonicalisé, au lieu d'utiliser directement `entite_sujet` /
    `entite_objet`, qui peuvent être des noms de graphe avec underscores.
    """
    output = []

    if not isinstance(data, dict):
        return output

    entity_map = build_pred_entity_map(
        data
    )

    relations = data.get(
        "global_relations",
        []
    )

    # Fallback relations pages si global absent.
    if not isinstance(relations, list) or not relations:
        relations = []

        for page in data.get("pages", []):
            if not isinstance(page, dict):
                continue

            for relation in page.get(
                "relations",
                []
            ):
                if isinstance(relation, dict):
                    relations.append(
                        relation
                    )

    for index, relation in enumerate(relations):
        if not isinstance(relation, dict):
            continue

        rtype = (
            relation.get(
                "type_relation"
            )
            or relation.get(
                "relation"
            )
            or ""
        )

        if not rtype:
            continue

        sid = str(
            relation.get(
                "identifiant_entite_sujet"
            )
            or relation.get(
                "subject_id"
            )
            or relation.get(
                "from_id"
            )
            or ""
        )

        oid = str(
            relation.get(
                "identifiant_entite_objet"
            )
            or relation.get(
                "object_id"
            )
            or relation.get(
                "to_id"
            )
            or ""
        )

        subject_entity = entity_map.get(
            sid,
            {}
        )

        object_entity = entity_map.get(
            oid,
            {}
        )

        subject_name = (
            subject_entity.get("name")
            or relation.get(
                "entite_sujet"
            )
            or relation.get(
                "subject"
            )
            or ""
        )

        object_name = (
            object_entity.get("name")
            or relation.get(
                "entite_objet"
            )
            or relation.get(
                "object"
            )
            or ""
        )

        if not subject_name or not object_name:
            continue

        output.append({
            "subject": str(
                subject_name
            ).strip(),

            "subject_type": str(
                subject_entity.get(
                    "type",
                    ""
                )
            ).strip(),

            "relation": str(
                rtype
            ).strip(),

            "object": str(
                object_name
            ).strip(),

            "object_type": str(
                object_entity.get(
                    "type",
                    ""
                )
            ).strip(),

            "page": (
                subject_entity.get("page")
                or object_entity.get("page")
            ),

            "matched": False,
            "index": index
        })

    return output


# ============================================================
# MATCHING
# ============================================================

def same_relation_type(gold, pred):
    return (
        normalize_relation_type(
            gold["relation"]
        )
        ==
        normalize_relation_type(
            pred["relation"]
        )
    )


def exact_match(gold, pred):
    return (
        same_relation_type(
            gold,
            pred
        )
        and normalize_text(
            gold["subject"]
        )
        == normalize_text(
            pred["subject"]
        )
        and normalize_text(
            gold["object"]
        )
        == normalize_text(
            pred["object"]
        )
    )


def boundary_match(gold, pred):
    if not same_relation_type(
        gold,
        pred
    ):
        return False

    subject_ok = (
        normalize_text(
            gold["subject"]
        )
        == normalize_text(
            pred["subject"]
        )
        or containment_score(
            gold["subject"],
            pred["subject"]
        ) > 0
    )

    object_ok = (
        normalize_text(
            gold["object"]
        )
        == normalize_text(
            pred["object"]
        )
        or containment_score(
            gold["object"],
            pred["object"]
        ) > 0
    )

    return (
        subject_ok
        and object_ok
    )


def relaxed_match_score(gold, pred):
    if not same_relation_type(
        gold,
        pred
    ):
        return 0.0

    return relation_similarity(
        gold,
        pred
    )


# ============================================================
# ÉVALUATION D'UN DOCUMENT
# ============================================================

def make_row(
    document,
    status,
    gold=None,
    pred=None,
    score=None
):
    return {
        "document": document,
        "status": status,

        "gold_subject": (
            gold.get("subject")
            if gold else None
        ),
        "gold_subject_type": (
            gold.get("subject_type")
            if gold else None
        ),
        "gold_relation": (
            gold.get("relation")
            if gold else None
        ),
        "gold_object": (
            gold.get("object")
            if gold else None
        ),
        "gold_object_type": (
            gold.get("object_type")
            if gold else None
        ),

        "pred_subject": (
            pred.get("subject")
            if pred else None
        ),
        "pred_subject_type": (
            pred.get("subject_type")
            if pred else None
        ),
        "pred_relation": (
            pred.get("relation")
            if pred else None
        ),
        "pred_object": (
            pred.get("object")
            if pred else None
        ),
        "pred_object_type": (
            pred.get("object_type")
            if pred else None
        ),

        "similarity": score
    }


def evaluate_document(
    document,
    gold_relations,
    pred_relations
):
    gold_relations = [
        dict(r, matched=False)
        for r in gold_relations
    ]

    pred_relations = [
        dict(r, matched=False)
        for r in pred_relations
    ]

    rows = []

    # --------------------------------------------------------
    # 1. EXACT
    # --------------------------------------------------------
    for gold in gold_relations:
        found = None

        for i, pred in enumerate(
            pred_relations
        ):
            if pred["matched"]:
                continue

            if exact_match(
                gold,
                pred
            ):
                found = i
                break

        if found is not None:
            gold["matched"] = True
            pred_relations[
                found
            ]["matched"] = True

            rows.append(
                make_row(
                    document,
                    "TP_EXACT",
                    gold,
                    pred_relations[
                        found
                    ],
                    1.0
                )
            )

    # --------------------------------------------------------
    # 2. BOUNDARY
    # --------------------------------------------------------
    for gold in gold_relations:
        if gold["matched"]:
            continue

        best_index = None
        best_score = -1.0

        for i, pred in enumerate(
            pred_relations
        ):
            if pred["matched"]:
                continue

            if not boundary_match(
                gold,
                pred
            ):
                continue

            score = relation_similarity(
                gold,
                pred
            )

            if score > best_score:
                best_score = score
                best_index = i

        if best_index is not None:
            gold["matched"] = True
            pred_relations[
                best_index
            ]["matched"] = True

            rows.append(
                make_row(
                    document,
                    "TP_BOUNDARY",
                    gold,
                    pred_relations[
                        best_index
                    ],
                    best_score
                )
            )

    # --------------------------------------------------------
    # 3. RELAXED
    # --------------------------------------------------------
    for gold in gold_relations:
        if gold["matched"]:
            continue

        best_index = None
        best_score = -1.0

        for i, pred in enumerate(
            pred_relations
        ):
            if pred["matched"]:
                continue

            score = relaxed_match_score(
                gold,
                pred
            )

            if (
                score >= RELAXED_THRESHOLD
                and score > best_score
            ):
                best_score = score
                best_index = i

        if best_index is not None:
            gold["matched"] = True
            pred_relations[
                best_index
            ]["matched"] = True

            rows.append(
                make_row(
                    document,
                    "TP_RELAXED",
                    gold,
                    pred_relations[
                        best_index
                    ],
                    best_score
                )
            )

    # --------------------------------------------------------
    # 4. WRONG RELATION TYPE
    # --------------------------------------------------------
    # Même sujet + même objet, mais type de relation différent.
    # Ce cas est affiché séparément et comptera comme 1 FP + 1 FN.
    for gold in gold_relations:
        if gold["matched"]:
            continue

        best_index = None
        best_score = -1.0

        for i, pred in enumerate(pred_relations):
            if pred["matched"]:
                continue

            if same_relation_type(gold, pred):
                continue

            subject_score = endpoint_score(
                gold["subject"],
                pred["subject"]
            )
            object_score = endpoint_score(
                gold["object"],
                pred["object"]
            )

            if (
                subject_score < WRONG_TYPE_THRESHOLD
                or object_score < WRONG_TYPE_THRESHOLD
            ):
                continue

            score = (subject_score + object_score) / 2.0

            if score > best_score:
                best_score = score
                best_index = i

        if best_index is not None:
            gold["matched"] = True
            pred_relations[best_index]["matched"] = True

            rows.append(
                make_row(
                    document,
                    "WRONG_TYPE",
                    gold,
                    pred_relations[best_index],
                    best_score
                )
            )

    # --------------------------------------------------------
    # FN
    # --------------------------------------------------------
    for gold in gold_relations:
        if not gold["matched"]:
            rows.append(
                make_row(
                    document,
                    "FN",
                    gold=gold
                )
            )

    # --------------------------------------------------------
    # FP
    # --------------------------------------------------------
    for pred in pred_relations:
        if not pred["matched"]:
            rows.append(
                make_row(
                    document,
                    "FP",
                    pred=pred
                )
            )

    return rows


# ============================================================
# MÉTRIQUES
# ============================================================

def safe_div(a, b):
    return a / b if b else 0.0


def prf(tp, fp, fn):
    precision = safe_div(
        tp,
        tp + fp
    )

    recall = safe_div(
        tp,
        tp + fn
    )

    f1 = (
        2 * precision * recall
        / (precision + recall)
        if precision + recall
        else 0.0
    )

    return (
        precision,
        recall,
        f1
    )


# ============================================================
# INDEX DES DOSSIERS
# ============================================================

def index_json_folder(folder):
    if not os.path.isdir(folder):
        raise FileNotFoundError(
            f"Dossier absent : {folder}"
        )

    result = {}

    for filename in os.listdir(
        folder
    ):
        if not filename.lower().endswith(
            ".json"
        ):
            continue

        key = normalize_document_key(
            filename
        )

        result[key] = os.path.join(
            folder,
            filename
        )

    return result


# ============================================================
# MAIN
# ============================================================

def main():
    gold_files = index_json_folder(
        GOLD_DIR
    )

    pred_files = index_json_folder(
        PRED_DIR
    )

    common_documents = sorted(
        set(gold_files.keys())
        & set(pred_files.keys())
    )

    print(
        f"\nDocuments Gold : "
        f"{len(gold_files)}"
    )

    print(
        f"Documents MLLM : "
        f"{len(pred_files)}"
    )

    print(
        f"Documents appariés : "
        f"{len(common_documents)}"
    )

    all_rows = []
    document_rows = []

    for document in common_documents:
        gold_data = load_json(
            gold_files[
                document
            ]
        )

        pred_data = load_json(
            pred_files[
                document
            ]
        )

        gold_relations = extract_gold_relations(
            gold_data
        )

        pred_relations = extract_pred_relations(
            pred_data
        )

        # Diagnostic indispensable : si ceci affiche zéro,
        # le problème est dans les fichiers/dossiers, pas le matching.
        print(
            f"\n🔎 {document} : "
            f"Gold relations chargées={len(gold_relations)} | "
            f"Pred relations chargées={len(pred_relations)}"
        )

        if gold_relations:
            g0 = gold_relations[0]
            print(
                "   Exemple GOLD : "
                f"{g0['subject']} "
                f"--{g0['relation']}--> "
                f"{g0['object']}"
            )

        if pred_relations:
            p0 = pred_relations[0]
            print(
                "   Exemple PRED : "
                f"{p0['subject']} "
                f"--{p0['relation']}--> "
                f"{p0['object']}"
            )

        rows = evaluate_document(
            document,
            gold_relations,
            pred_relations
        )

        all_rows.extend(
            rows
        )

        counts = Counter(
            row["status"]
            for row in rows
        )

        exact = counts[
            "TP_EXACT"
        ]

        boundary = counts[
            "TP_BOUNDARY"
        ]

        relaxed = counts[
            "TP_RELAXED"
        ]

        wrong_type = counts["WRONG_TYPE"]
        fp = counts["FP"]
        fn = counts["FN"]

        strict_p_doc, strict_r_doc, strict_f1_doc = prf(
            exact,
            fp + boundary + relaxed + wrong_type,
            fn + boundary + relaxed + wrong_type
        )

        boundary_tp_doc = exact + boundary
        boundary_p_doc, boundary_r_doc, boundary_f1_doc = prf(
            boundary_tp_doc,
            fp + relaxed + wrong_type,
            fn + relaxed + wrong_type
        )

        tp_total = exact + boundary + relaxed
        p, r, f1 = prf(
            tp_total,
            fp + wrong_type,
            fn + wrong_type
        )

        document_rows.append({
            "document": document,
            "gold_relations": len(gold_relations),
            "pred_relations": len(pred_relations),
            "tp_exact": exact,
            "tp_boundary": boundary,
            "tp_relaxed": relaxed,
            "wrong_type": wrong_type,
            "fp": fp,
            "fn": fn,
            "precision_strict": strict_p_doc,
            "recall_strict": strict_r_doc,
            "f1_strict": strict_f1_doc,
            "precision_boundary": boundary_p_doc,
            "recall_boundary": boundary_r_doc,
            "f1_boundary": boundary_f1_doc,
            "precision_relaxed": p,
            "recall_relaxed": r,
            "f1_relaxed": f1
        })

        print(
            f"✅ {document} | "
            f"Gold={len(gold_relations)} | "
            f"Pred={len(pred_relations)} | "
            f"Exact={exact} | "
            f"Boundary={boundary} | "
            f"Relaxed={relaxed} | "
            f"WrongType={wrong_type} | "
            f"FP={fp} | "
            f"FN={fn}"
        )

    # ========================================================
    # GLOBAL
    # ========================================================

    counts = Counter(
        row["status"]
        for row in all_rows
    )

    exact = counts[
        "TP_EXACT"
    ]

    boundary = counts[
        "TP_BOUNDARY"
    ]

    relaxed = counts[
        "TP_RELAXED"
    ]

    wrong_type = counts["WRONG_TYPE"]
    fp = counts["FP"]
    fn = counts["FN"]

    # WRONG_TYPE compte comme 1 FP + 1 FN.
    strict_tp = exact
    strict_fp = fp + boundary + relaxed + wrong_type
    strict_fn = fn + boundary + relaxed + wrong_type

    strict_p, strict_r, strict_f1 = prf(
        strict_tp,
        strict_fp,
        strict_fn
    )

    boundary_tp_total = exact + boundary
    boundary_fp_total = fp + relaxed + wrong_type
    boundary_fn_total = fn + relaxed + wrong_type

    boundary_p, boundary_r, boundary_f1 = prf(
        boundary_tp_total,
        boundary_fp_total,
        boundary_fn_total
    )

    relaxed_tp_total = exact + boundary + relaxed
    relaxed_p, relaxed_r, relaxed_f1 = prf(
        relaxed_tp_total,
        fp + wrong_type,
        fn + wrong_type
    )

    macro_strict_f1 = (
        sum(row["f1_strict"] for row in document_rows) / len(document_rows)
        if document_rows else 0.0
    )
    macro_boundary_f1 = (
        sum(row["f1_boundary"] for row in document_rows) / len(document_rows)
        if document_rows else 0.0
    )
    macro_relaxed_f1 = (
        sum(row["f1_relaxed"] for row in document_rows) / len(document_rows)
        if document_rows else 0.0
    )

    print(
        "\n"
        "============================================================"
    )

    print(
        "ÉVALUATION DES RELATIONS TERMINÉE"
    )

    print(
        "============================================================"
    )

    print(
        f"Documents évalués      : "
        f"{len(common_documents)}"
    )

    print(
        f"TP exact                : "
        f"{exact}"
    )

    print(
        f"TP boundary             : "
        f"{boundary}"
    )

    print(
        f"TP relaxed              : "
        f"{relaxed}"
    )

    print(
        f"Wrong relation type     : "
        f"{wrong_type}"
    )

    print(
        f"FP restants             : "
        f"{fp}"
    )

    print(
        f"FN restants             : "
        f"{fn}"
    )

    print(
        "\n--- STRICT ---"
    )

    print(
        f"Micro Precision : "
        f"{strict_p:.4f}"
    )

    print(
        f"Micro Recall    : "
        f"{strict_r:.4f}"
    )

    print(
        f"Micro F1        : "
        f"{strict_f1:.4f}"
    )
    print(
        f"Macro F1 docs   : "
        f"{macro_strict_f1:.4f}"
    )

    print(
        "\n--- BOUNDARY RELAXED ---"
    )

    print(
        f"Micro Precision : "
        f"{boundary_p:.4f}"
    )

    print(
        f"Micro Recall    : "
        f"{boundary_r:.4f}"
    )

    print(
        f"Micro F1        : "
        f"{boundary_f1:.4f}"
    )
    print(
        f"Macro F1 docs   : "
        f"{macro_boundary_f1:.4f}"
    )

    print(
        "\n--- RELAXED ---"
    )

    print(
        f"Micro Precision : "
        f"{relaxed_p:.4f}"
    )

    print(
        f"Micro Recall    : "
        f"{relaxed_r:.4f}"
    )

    print(
        f"Micro F1        : "
        f"{relaxed_f1:.4f}"
    )
    print(
        f"Macro F1 docs   : "
        f"{macro_relaxed_f1:.4f}"
    )

    # ========================================================
    # CSV DÉTAILLÉ
    # ========================================================

    detailed_columns = [
        "document",
        "status",
        "gold_subject",
        "gold_subject_type",
        "gold_relation",
        "gold_object",
        "gold_object_type",
        "pred_subject",
        "pred_subject_type",
        "pred_relation",
        "pred_object",
        "pred_object_type",
        "similarity"
    ]

    detailed_df = pd.DataFrame(
        all_rows,
        columns=detailed_columns
    )

    detailed_df.to_csv(
        os.path.join(
            OUTPUT_DIR,
            "relation_matches_detailed.csv"
        ),
        index=False,
        encoding="utf-8-sig"
    )

    # ========================================================
    # PAR DOCUMENT
    # ========================================================

    document_df = pd.DataFrame(
        document_rows
    )

    document_df.to_csv(
        os.path.join(
            OUTPUT_DIR,
            "relation_metrics_by_document.csv"
        ),
        index=False,
        encoding="utf-8-sig"
    )

    # ========================================================
    # PAR TYPE
    # ========================================================

    relation_types = set()

    for row in all_rows:
        if row.get(
            "gold_relation"
        ):
            relation_types.add(
                row[
                    "gold_relation"
                ]
            )

        if row.get(
            "pred_relation"
        ):
            relation_types.add(
                row[
                    "pred_relation"
                ]
            )

    type_rows = []

    for relation_type in sorted(
        relation_types
    ):
        exact_t = sum(
            1
            for row in all_rows
            if (
                row["status"] == "TP_EXACT"
                and row.get(
                    "gold_relation"
                ) == relation_type
            )
        )

        boundary_t = sum(
            1
            for row in all_rows
            if (
                row["status"] == "TP_BOUNDARY"
                and row.get(
                    "gold_relation"
                ) == relation_type
            )
        )

        relaxed_t = sum(
            1
            for row in all_rows
            if (
                row["status"] == "TP_RELAXED"
                and row.get(
                    "gold_relation"
                ) == relation_type
            )
        )

        wrong_as_pred_t = sum(
            1
            for row in all_rows
            if (
                row["status"] == "WRONG_TYPE"
                and row.get("pred_relation") == relation_type
            )
        )

        wrong_as_gold_t = sum(
            1
            for row in all_rows
            if (
                row["status"] == "WRONG_TYPE"
                and row.get("gold_relation") == relation_type
            )
        )

        fp_t = sum(
            1
            for row in all_rows
            if (
                row["status"] == "FP"
                and row.get("pred_relation") == relation_type
            )
        )

        fn_t = sum(
            1
            for row in all_rows
            if (
                row["status"] == "FN"
                and row.get("gold_relation") == relation_type
            )
        )

        tp_t = exact_t + boundary_t + relaxed_t

        p_t, r_t, f1_t = prf(
            tp_t,
            fp_t + wrong_as_pred_t,
            fn_t + wrong_as_gold_t
        )

        type_rows.append({
            "relation_type": relation_type,
            "tp_exact": exact_t,
            "tp_boundary": boundary_t,
            "tp_relaxed": relaxed_t,
            "wrong_type_as_pred": wrong_as_pred_t,
            "wrong_type_as_gold": wrong_as_gold_t,
            "fp": fp_t,
            "fn": fn_t,
            "precision_relaxed": p_t,
            "recall_relaxed": r_t,
            "f1_relaxed": f1_t
        })

    type_df = pd.DataFrame(
        type_rows
    )

    type_df.to_csv(
        os.path.join(
            OUTPUT_DIR,
            "relation_metrics_by_type.csv"
        ),
        index=False,
        encoding="utf-8-sig"
    )

    print(
        f"\nRésultats relations V6.9k RECALL-BOOST CONTROLLED : "
        f"{OUTPUT_DIR}"
    )


if __name__ == "__main__":
    main()
