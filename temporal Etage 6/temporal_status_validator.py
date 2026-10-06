# -*- coding: utf-8 -*-

import json
import re
from pathlib import Path
from collections import Counter

BASE_DIR = Path(
    r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM"
    r"\Reduction_hallucinations"
)

INPUT_FILE = (
    BASE_DIR / "temporal Etage 6"
    / "outputs"
    / "temporal_status_decisions.json"
)

OUTPUT_FILE = (
    BASE_DIR / "temporal Etage 6"
    / "outputs"
    / "temporal_status_validated_decisions.json"
)

OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

MAX_DISTANCE = 70


TEMPORAL_PATTERNS = {

    "HISTORICAL": [
        r"\bantÃ©cÃ©dent(?:s)? de\b",
        r"\bantÃ©cÃ©dent(?:s)?\b",
        r"\bhistoire de\b",
        r"\bancien(?:ne)?\b",
        r"\bantÃ©rieur(?:e)?\b",
        r"\bavait prÃ©sentÃ©\b",
        r"\bconnu(?:e)? pour\b",
    ],

    "AT_ADMISSION": [
        r"\bÃ  l'admission\b",
        r"\blors de l'admission\b",
        r"\bÃ  son admission\b",
        r"\bÃ  l'entrÃ©e\b",
        r"\blors de son entrÃ©e\b",
    ],

    "DURING_HOSPITALIZATION": [
        r"\bdurant l'hospitalisation\b",
        r"\bpendant l'hospitalisation\b",
        r"\bau cours de l'hospitalisation\b",
        r"\bau cours du sÃ©jour\b",
        r"\bpendant le sÃ©jour\b",
        r"\ben rÃ©animation\b",
    ],

    "AFTER_TREATMENT": [
        r"\baprÃ¨s traitement\b",
        r"\baprÃ¨s antibiothÃ©rapie\b",
        r"\bsous traitement\b",
        r"\baprÃ¨s introduction\b",
        r"\baprÃ¨s instauration\b",
        r"\baprÃ¨s administration\b",
    ],
}


def find_hits(sentence):
    hits = []

    for label, regexes in TEMPORAL_PATTERNS.items():
        for rx in regexes:
            for match in re.finditer(
                rx,
                sentence,
                flags=re.IGNORECASE,
            ):
                hits.append({
                    "label": label,
                    "match": match.group(0),
                    "start": match.start(),
                    "end": match.end(),
                })

    return hits


def distance_to_mention(
    hit,
    mention_start,
    mention_end,
):
    if (
        mention_start is None
        or mention_end is None
    ):
        return 999999

    if hit["end"] <= mention_start:
        return mention_start - hit["end"]

    if hit["start"] >= mention_end:
        return hit["start"] - mention_end

    return 0


def independent_temporal_check(item):

    sentence = str(
        item.get("sentence") or ""
    )

    mention_start = item.get(
        "mention_start"
    )

    mention_end = item.get(
        "mention_end"
    )

    if not sentence:
        return {
            "status": "NO_SENTENCE",
            "label": None,
            "hits": [],
        }

    if (
        mention_start is None
        or mention_end is None
    ):
        return {
            "status": "NO_MENTION_POSITION",
            "label": None,
            "hits": [],
        }

    hits = find_hits(sentence)

    local_hits = []

    for hit in hits:

        hit = dict(hit)

        hit["distance"] = (
            distance_to_mention(
                hit,
                mention_start,
                mention_end,
            )
        )

        if hit["distance"] <= MAX_DISTANCE:
            local_hits.append(hit)

    if not local_hits:
        return {
            "status": "NO_LOCAL_MARKER",
            "label": None,
            "hits": [],
        }

    labels = {
        hit["label"]
        for hit in local_hits
    }

    if len(labels) != 1:
        return {
            "status": "AMBIGUOUS",
            "label": None,
            "hits": local_hits,
        }

    label = next(iter(labels))

    return {
        "status": "CONFIRMED",
        "label": label,
        "hits": local_hits,
    }


def validate(item):

    decision = item.get("decision")

    action = item.get(
        "proposed_action"
    )

    proposed = item.get(
        "proposed_temporal_status"
    )

    try:
        confidence = float(
            item.get("confidence", 0)
            or 0
        )
    except (TypeError, ValueError):
        confidence = 0.0

    # ----------------------------------------
    # Aucun changement proposÃ©
    # ----------------------------------------

    if decision == "KEEP":

        return {
            "final_status": "KEEP",
            "final_action": "NONE",
            "validation_reason":
                "Aucune correction temporelle proposÃ©e.",
            "validator_check": None,
        }

    # ----------------------------------------
    # REVIEW du classifier reste REVIEW
    # ----------------------------------------

    if decision != "CORRECT":

        return {
            "final_status": "REVIEW",
            "final_action": "NONE",
            "validation_reason":
                "Le classifier n'a pas proposÃ© "
                "une correction automatique.",
            "validator_check": None,
        }

    # ----------------------------------------
    # VÃ©rification de l'action
    # ----------------------------------------

    if action != "SET_TEMPORAL_STATUS":

        return {
            "final_status": "REVIEW",
            "final_action": "NONE",
            "validation_reason":
                "Action incompatible avec une "
                "correction temporelle.",
            "validator_check": None,
        }

    # ----------------------------------------
    # VÃ©rification temporalitÃ© cible
    # ----------------------------------------

    if proposed not in TEMPORAL_PATTERNS:

        return {
            "final_status": "REVIEW",
            "final_action": "NONE",
            "validation_reason":
                "TemporalitÃ© proposÃ©e non autorisÃ©e.",
            "validator_check": None,
        }

    # ----------------------------------------
    # Confiance
    # ----------------------------------------

    if confidence < 0.90:

        return {
            "final_status": "REVIEW",
            "final_action": "NONE",
            "validation_reason":
                "Confiance insuffisante.",
            "validator_check": None,
        }

    # ----------------------------------------
    # Validation indÃ©pendante
    # ----------------------------------------

    check = independent_temporal_check(
        item
    )

    if check["status"] != "CONFIRMED":

        return {
            "final_status": "REVIEW",
            "final_action": "NONE",
            "validation_reason":
                f"Validation indÃ©pendante Ã©chouÃ©e : "
                f"{check['status']}.",
            "validator_check": check,
        }

    # ----------------------------------------
    # Le validator doit retrouver
    # EXACTEMENT la mÃªme temporalitÃ©
    # ----------------------------------------

    if check["label"] != proposed:

        return {
            "final_status": "REVIEW",
            "final_action": "NONE",
            "validation_reason":
                "DÃ©saccord entre classifier et validator.",
            "validator_check": check,
        }

    # ----------------------------------------
    # VÃ©rifier l'evidence produite
    # par le classifier
    # ----------------------------------------

    evidence = item.get(
        "temporal_evidence"
    )

    if not isinstance(evidence, dict):

        return {
            "final_status": "REVIEW",
            "final_action": "NONE",
            "validation_reason":
                "Preuve temporelle structurÃ©e absente.",
            "validator_check": check,
        }

    if evidence.get("label") != proposed:

        return {
            "final_status": "REVIEW",
            "final_action": "NONE",
            "validation_reason":
                "La preuve du classifier ne correspond "
                "pas Ã  la temporalitÃ© proposÃ©e.",
            "validator_check": check,
        }

    try:
        evidence_distance = int(
            evidence.get(
                "distance",
                999999,
            )
        )
    except (TypeError, ValueError):
        evidence_distance = 999999

    if evidence_distance > MAX_DISTANCE:

        return {
            "final_status": "REVIEW",
            "final_action": "NONE",
            "validation_reason":
                "Marqueur temporel trop Ã©loignÃ© "
                "de l'entitÃ©.",
            "validator_check": check,
        }

    # ----------------------------------------
    # SAFE ACCEPT
    # ----------------------------------------

    return {
        "final_status": "SAFE_ACCEPT",
        "final_action": "SET_TEMPORAL_STATUS",
        "validation_reason":
            "TemporalitÃ© confirmÃ©e indÃ©pendamment "
            "dans le contexte local.",
        "validator_check": check,
    }


def main():

    payload = json.loads(
        INPUT_FILE.read_text(
            encoding="utf-8"
        )
    )

    decisions = payload.get(
        "decisions",
        [],
    )

    validated = []

    status_counts = Counter()
    action_counts = Counter()
    review_reasons = Counter()

    for item in decisions:

        result = validate(item)

        row = {
            **item,
            **result,
        }

        validated.append(row)

        status_counts[
            result["final_status"]
        ] += 1

        action_counts[
            result["final_action"]
        ] += 1

        if result["final_status"] == "REVIEW":
            review_reasons[
                result["validation_reason"]
            ] += 1

    OUTPUT_FILE.write_text(
        json.dumps(
            {
                "validator":
                    "temporal_status_validator",

                "mode":
                    "INDEPENDENT_LOCAL_REVALIDATION",

                "summary": {

                    "decisions_received":
                        len(decisions),

                    "status_counts":
                        dict(status_counts),

                    "action_counts":
                        dict(action_counts),

                    "review_reasons":
                        dict(review_reasons),
                },

                "validated":
                    validated,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=" * 112)
    print(
        "TRACE / SGCE - TEMPORAL STATUS VALIDATOR "
        "- INDEPENDENT LOCAL REVALIDATION"
    )
    print("=" * 112)

    print(
        f"DÃ©cisions reÃ§ues                    : "
        f"{len(decisions)}"
    )

    print()
    print("STATUTS FINAUX")
    print("-" * 112)

    for key, value in status_counts.items():
        print(
            f"{key:<52}: {value}"
        )

    print()
    print("ACTIONS FINALES")
    print("-" * 112)

    for key, value in action_counts.items():
        print(
            f"{key:<52}: {value}"
        )

    print()
    print("RAISONS REVIEW")
    print("-" * 112)

    for key, value in review_reasons.items():
        print(
            f"{key:<80}: {value}"
        )

    print()
    print(
        f"Sortie                              : "
        f"{OUTPUT_FILE}"
    )

    print()
    print(
        "Aucune donnÃ©e clinique n'a Ã©tÃ© modifiÃ©e."
    )


if __name__ == "__main__":
    main()
