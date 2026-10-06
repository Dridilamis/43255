# -*- coding: utf-8 -*-

"""
TRACE / SGCE
BUILD AGENT D QUEUE FROM RELATION REPAIR

Objectif
--------
Agent D ne doit plus reprendre les 110 cas AMBIGUOUS historiques
de Pattern D.

Il reçoit uniquement les cas REVIEW restant après Relation Repair.

Aucune donnée clinique n'est modifiée.
"""

import json
from pathlib import Path


# ============================================================
# PATHS
# ============================================================

HERE = Path(__file__).resolve().parent
MULTIAGENT_DIR = HERE.parent
SGCE_DIR = MULTIAGENT_DIR.parent

RELATION_REPAIR_DIR = SGCE_DIR / "relation_repair"

OUTPUT_FILE = (
    MULTIAGENT_DIR
    / "queues"
    / "agent_d_queue.json"
)


# ============================================================
# IO
# ============================================================

def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )


# ============================================================
# EXTRACTION DES LISTES
# ============================================================

def extract_items(data):

    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return []

    possible_keys = (
        "results",
        "validated_decisions",
        "decisions",
        "candidates",
        "items",
        "cases",
    )

    for key in possible_keys:

        value = data.get(key)

        if isinstance(value, list):
            return value

    return []


# ============================================================
# STATUT
# ============================================================

def get_status(item):

    if not isinstance(item, dict):
        return ""

    value = (
        item.get("final_status")
        or item.get("validation_status")
        or item.get("status")
        or item.get("decision")
        or ""
    )

    return str(value).upper().strip()


# ============================================================
# RECHERCHE DU RAPPORT RELATION REPAIR
# ============================================================

def find_relation_repair_report():

    if not RELATION_REPAIR_DIR.exists():

        raise FileNotFoundError(
            "Dossier Relation Repair introuvable : "
            f"{RELATION_REPAIR_DIR}"
        )

    candidates = []

    for path in RELATION_REPAIR_DIR.rglob("*.json"):

        try:

            data = load_json(path)

        except Exception:

            continue

        items = extract_items(data)

        if not items:
            continue

        review_items = [
            item
            for item in items
            if isinstance(item, dict)
            and get_status(item) == "REVIEW"
        ]

        if review_items:

            candidates.append(
                (
                    path,
                    items,
                    len(review_items),
                )
            )

    if not candidates:

        raise FileNotFoundError(
            "Aucun rapport Relation Repair contenant "
            "des cas REVIEW n'a été trouvé dans : "
            f"{RELATION_REPAIR_DIR}"
        )

    # --------------------------------------------------------
    # On privilégie le rapport contenant le plus de REVIEW
    # résiduels.
    # --------------------------------------------------------

    candidates.sort(
        key=lambda x: x[2],
        reverse=True,
    )

    return candidates[0]


# ============================================================
# IDENTIFIANT DE RELATION
# ============================================================

def get_relation_id(item):

    parameters = item.get("parameters")

    if isinstance(parameters, dict):

        value = parameters.get("relation_id")

        if value:
            return value

    value = item.get("relation_id")

    if value:
        return value

    symbolic = item.get("symbolic_candidate")

    if isinstance(symbolic, dict):

        value = symbolic.get("relation_id")

        if value:
            return value

        relation = symbolic.get("relation")

        if isinstance(relation, dict):

            return (
                relation.get("identifiant_relation")
                or relation.get("relation_id")
                or relation.get("id")
            )

    return None


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 100)

    print(
        "TRACE / SGCE - "
        "BUILD AGENT D QUEUE FROM RELATION REPAIR"
    )

    print("=" * 100)

    # --------------------------------------------------------
    # 1. Trouver le rapport Relation Repair
    # --------------------------------------------------------

    (
        report_path,
        items,
        review_count,
    ) = find_relation_repair_report()

    print(
        f"Rapport Relation Repair            : "
        f"{report_path}"
    )

    print(
        f"REVIEW détectés dans le rapport    : "
        f"{review_count}"
    )

    # --------------------------------------------------------
    # 2. Construire la queue Agent D
    # --------------------------------------------------------

    queue = []

    seen = set()

    for index, item in enumerate(items):

        if not isinstance(item, dict):
            continue

        if get_status(item) != "REVIEW":
            continue

        candidate_id = (
            item.get("candidate_id")
            or f"RR_REVIEW_{index:06d}"
        )

        document = item.get("document")

        relation_id = get_relation_id(item)

        # ----------------------------------------------------
        # Déduplication
        # ----------------------------------------------------

        dedup_key = (
            str(document),
            str(candidate_id),
            str(relation_id),
        )

        if dedup_key in seen:
            continue

        seen.add(dedup_key)

        # ----------------------------------------------------
        # Cas envoyé à Agent D
        # ----------------------------------------------------

        queue.append(
            {
                "candidate_id": candidate_id,

                "document": document,

                "pattern": "D",

                "subpattern":
                    "RELATION_REPAIR_RESIDUAL",

                "original_status":
                    "REVIEW",

                "source_stage":
                    "relation_repair",

                "relation_id":
                    relation_id,

                "symbolic_candidate":
                    item,
            }
        )

    # --------------------------------------------------------
    # 3. Sauvegarde
    # --------------------------------------------------------

    save_json(
        OUTPUT_FILE,
        queue,
    )

    # --------------------------------------------------------
    # 4. Rapport console
    # --------------------------------------------------------

    print()

    print(
        f"REVIEW résiduels routés vers D     : "
        f"{len(queue)}"
    )

    print(
        f"Sortie                              : "
        f"{OUTPUT_FILE}"
    )

    print()

    print(
        "Aucune donnée clinique "
        "n'a été modifiée."
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()