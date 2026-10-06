# -*- coding: utf-8 -*-

"""
TRACE / SGCE
VALIDATE SPECIALIZED AGENT DECISIONS

Rôle
----
Valider les décisions produites par les agents spécialisés B, C et D
avant l'adjudication globale.

IMPORTANT
---------
Le fichier multiagent_direct_accepts.json est RECONSTRUIT entièrement
à chaque exécution.

Aucun ACCEPT provenant d'un ancien run n'est conservé.

Aucune donnée clinique n'est modifiée.
"""

import json
from pathlib import Path
from collections import Counter


# ============================================================
# PATHS
# ============================================================

HERE = Path(__file__).resolve().parent
MULTIAGENT_DIR = HERE.parent

OUTPUTS_DIR = MULTIAGENT_DIR / "outputs"

AGENT_FILES = {
    "B": OUTPUTS_DIR / "agent_b_decisions.json",
    "C": OUTPUTS_DIR / "agent_c_decisions.json",
    "D": OUTPUTS_DIR / "agent_d_decisions.json",
}

VALIDATED_FILES = {
    "B": OUTPUTS_DIR / "agent_b_validated_decisions.json",
    "C": OUTPUTS_DIR / "agent_c_validated_decisions.json",
    "D": OUTPUTS_DIR / "agent_d_validated_decisions.json",
}

DIRECT_ACCEPTS_FILE = (
    OUTPUTS_DIR / "multiagent_direct_accepts.json"
)


# ============================================================
# IO
# ============================================================

def load_json(path: Path):

    if not path.exists():
        return None

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
# EXTRACT DECISIONS
# ============================================================

def extract_decisions(payload):

    if payload is None:
        return []

    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    possible_keys = (
        "validated_decisions",
        "decisions",
        "results",
        "cases",
        "items",
    )

    for key in possible_keys:

        value = payload.get(key)

        if isinstance(value, list):
            return value

    return []


# ============================================================
# NORMALIZATION
# ============================================================

def norm(value):

    if value is None:
        return ""

    return str(value).strip().upper()


def get_decision(item):

    return norm(
        item.get("decision")
        or item.get("status")
        or item.get("final_status")
        or item.get("validation_status")
    )


def get_action(item):

    return norm(
        item.get("action")
        or item.get("proposed_action")
        or item.get("recommended_action")
        or item.get("final_action")
    )


# ============================================================
# VALIDATION
# ============================================================

def validate_decision(family, item):

    """
    Validation conservatrice.

    CORRECT est transformé en ACCEPT uniquement lorsqu'une action
    explicite et autorisée est présente.

    REVIEW reste REVIEW.

    Tout cas incertain reste REVIEW.
    """

    decision = get_decision(item)
    action = get_action(item)

    result = dict(item)

    result["family"] = family

    # --------------------------------------------------------
    # REVIEW
    # --------------------------------------------------------

    if decision in {
        "REVIEW",
        "AMBIGUOUS",
        "UNRESOLVED",
        "PROTECTED",
    }:

        result["validation_status"] = "REVIEW"
        result["final_status"] = "REVIEW"
        result["final_action"] = "NONE"

        return result

    # --------------------------------------------------------
    # CORRECT / ACCEPT
    # --------------------------------------------------------

    if decision in {
        "CORRECT",
        "ACCEPT",
        "CONFIRMED",
    }:

        if action and action != "NONE":

            result["validation_status"] = "ACCEPT"
            result["final_status"] = "ACCEPT"
            result["final_action"] = get_action(result)

            return result

        result["validation_status"] = "REVIEW"

        return result

    # --------------------------------------------------------
    # Tout autre statut est protégé
    # --------------------------------------------------------

    result["validation_status"] = "REVIEW"

    return result


# ============================================================
# DEDUPLICATION DES ACCEPT
# ============================================================

def accept_key(item):

    family = item.get("family")

    candidate_id = (
        item.get("candidate_id")
        or item.get("case_id")
        or item.get("id")
    )

    document = item.get("document")

    action = get_action(item)

    return (
        str(family),
        str(document),
        str(candidate_id),
        str(action),
    )


def deduplicate_accepts(items):

    output = []

    seen = set()

    for item in items:

        key = accept_key(item)

        if key in seen:
            continue

        seen.add(key)

        output.append(item)

    return output


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 100)
    print(
        "TRACE / SGCE - "
        "VALIDATE SPECIALIZED AGENT DECISIONS"
    )
    print("=" * 100)

    # --------------------------------------------------------
    # IMPORTANT :
    # aucune lecture de l'ancien direct_accepts.
    #
    # Cette liste repart TOUJOURS de zéro.
    # --------------------------------------------------------

    direct_accepts = []

    summary = {}

    for family in ("B", "C", "D"):

        source_file = AGENT_FILES[family]

        payload = load_json(source_file)

        decisions = extract_decisions(payload)

        validated = []

        for item in decisions:

            if not isinstance(item, dict):
                continue

            result = validate_decision(
                family,
                item,
            )

            validated.append(result)

            if (
                result.get("validation_status")
                == "ACCEPT"
            ):

                direct_accepts.append(result)

        # ----------------------------------------------------
        # Sauvegarder les décisions validées de cette famille
        # ----------------------------------------------------

        validated_payload = {
            "family": family,
            "source_file": str(source_file),
            "total": len(validated),
            "validated_decisions": validated,
        }

        save_json(
            VALIDATED_FILES[family],
            validated_payload,
        )

        counts = Counter(
            item.get(
                "validation_status",
                "UNKNOWN",
            )
            for item in validated
        )

        summary[family] = {
            "total": len(validated),
            "ACCEPT": counts.get(
                "ACCEPT",
                0,
            ),
            "REVIEW": counts.get(
                "REVIEW",
                0,
            ),
        }

        print(
            f"{family}: "
            f"{len(validated)} -> "
            f"ACCEPT={counts.get('ACCEPT', 0)}, "
            f"REVIEW={counts.get('REVIEW', 0)}"
        )

    # ========================================================
    # DEDUPLICATION
    # ========================================================

    direct_accepts = deduplicate_accepts(
        direct_accepts
    )

    # ========================================================
    # RECONSTRUCTION COMPLETE DU FICHIER
    # ========================================================

    direct_payload = {
        "generated_from_current_run_only": True,
        "total": len(direct_accepts),
        "summary": summary,
        "direct_accepts": direct_accepts,
    }

    # IMPORTANT :
    # mode "w" dans save_json()
    # => ancien contenu entièrement remplacé.
    save_json(
        DIRECT_ACCEPTS_FILE,
        direct_payload,
    )

    print()
    print("-" * 100)

    print(
        "Direct ACCEPT reconstruits         : "
        f"{len(direct_accepts)}"
    )

    family_counts = Counter(
        item.get("family")
        for item in direct_accepts
    )

    print(
        "Direct ACCEPT par famille          : "
        f"{dict(family_counts)}"
    )

    print(
        "Fichier                           : "
        f"{DIRECT_ACCEPTS_FILE}"
    )

    print()
    print(
        "Aucun ACCEPT provenant d'un ancien "
        "run n'a été conservé."
    )

    print(
        "Aucune donnée clinique n'a été modifiée."
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()