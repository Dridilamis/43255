# -*- coding: utf-8 -*-
"""
temporal_status_classifier.py
=============================

AUTONOMOUS TEXT-GUIDED

DÃ©duit une temporalitÃ© UNIQUEMENT si un marqueur explicite et local
est prÃ©sent dans la phrase de l'entitÃ©.

TemporalitÃ©s corrigibles :
- HISTORICAL
- AT_ADMISSION
- DURING_HOSPITALIZATION
- AFTER_TREATMENT

UNKNOWN reste UNKNOWN lorsqu'aucune preuve explicite n'est disponible.

Le script peut aussi signaler des conflits de statut clinique explicites,
mais il ne les corrige pas automatiquement.
"""

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
    / "queues"
    / "temporal_status_candidates.json"
)

OUTPUT_FILE = (
    BASE_DIR / "temporal Etage 6"
    / "outputs"
    / "temporal_status_decisions.json"
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

CLINICAL_PATTERNS = {
    "NEGATED": [
        r"\babsence de\b",
        r"\bsans\b",
        r"\bpas de\b",
        r"\baucun(?:e)?\b",
        r"\bnie\b",
    ],

    "SUSPECTED": [
        r"\bsuspicion de\b",
        r"\bsuspect(?:Ã©|Ã©e)?\b",
        r"\bprobable\b",
        r"\bpossible\b",
        r"\bÃ©voquant\b",
        r"\bcompatible avec\b",
    ],

    "PLANNED": [
        r"\bprÃ©vu(?:e)?\b",
        r"\bprogrammÃ©(?:e)?\b",
        r"\bÃ  rÃ©aliser\b",
        r"\benvisagÃ©(?:e)?\b",
    ],

    "RESOLVED": [
        r"\brÃ©solu(?:e)?\b",
        r"\bdisparu(?:e)?\b",
        r"\bnormalisation\b",
        r"\brÃ©gression\b",
    ],
}


def find_hits(sentence, patterns):
    hits = []

    for label, regexes in patterns.items():
        for rx in regexes:
            for match in re.finditer(
                rx,
                sentence,
                flags=re.IGNORECASE,
            ):
                hits.append({
                    "label":
                        label,

                    "match":
                        match.group(0),

                    "start":
                        match.start(),

                    "end":
                        match.end(),
                })

    return hits


def distance_to_mention(hit, mention_start, mention_end):
    if mention_start is None:
        return 999999

    if hit["end"] <= mention_start:
        return mention_start - hit["end"]

    if hit["start"] >= mention_end:
        return hit["start"] - mention_end

    return 0


def choose_local_temporal(item):
    sentence = item.get("sentence", "")

    if not sentence:
        return None, None

    hits = find_hits(
        sentence,
        TEMPORAL_PATTERNS,
    )

    for hit in hits:
        hit["distance"] = distance_to_mention(
            hit,
            item.get("mention_start"),
            item.get("mention_end"),
        )

    hits = [
        h
        for h in hits
        if h["distance"] <= MAX_DISTANCE
    ]

    if not hits:
        return None, None

    by_label = {}

    for hit in hits:
        by_label.setdefault(
            hit["label"],
            [],
        ).append(hit)

    if len(by_label) != 1:
        return "AMBIGUOUS", hits

    label = next(iter(by_label))

    best = sorted(
        by_label[label],
        key=lambda x: x["distance"],
    )[0]

    return label, best


def detect_clinical_conflict(item):
    sentence = item.get("sentence", "")

    if not sentence:
        return None

    hits = find_hits(
        sentence,
        CLINICAL_PATTERNS,
    )

    for hit in hits:
        hit["distance"] = distance_to_mention(
            hit,
            item.get("mention_start"),
            item.get("mention_end"),
        )

    hits = [
        h
        for h in hits
        if h["distance"] <= 50
    ]

    if not hits:
        return None

    current = str(
        item.get("current_clinical_status")
        or ""
    ).upper()

    labels = {
        h["label"]
        for h in hits
    }

    if len(labels) == 1:
        explicit = next(iter(labels))

        if current and current != explicit:
            return {
                "explicit_status":
                    explicit,

                "hits":
                    hits,
            }

    return None


def classify(item):
    temporal_label, evidence = choose_local_temporal(item)

    clinical_conflict = detect_clinical_conflict(item)

    current_temporal = str(
        item.get("current_temporal_status")
        or "UNKNOWN"
    ).upper()

    if temporal_label == "AMBIGUOUS":
        return {
            "decision":
                "REVIEW",

            "proposed_action":
                "NONE",

            "proposed_temporal_status":
                None,

            "confidence":
                0.50,

            "reason":
                "Plusieurs marqueurs temporels explicites concurrents dans le contexte local.",

            "temporal_evidence":
                evidence,

            "clinical_conflict":
                clinical_conflict,
        }

    if temporal_label is not None:
        if current_temporal == temporal_label:
            return {
                "decision":
                    "KEEP",

                "proposed_action":
                    "NONE",

                "proposed_temporal_status":
                    temporal_label,

                "confidence":
                    0.98,

                "reason":
                    "La temporalitÃ© actuelle est confirmÃ©e par le texte.",

                "temporal_evidence":
                    evidence,

                "clinical_conflict":
                    clinical_conflict,
            }

        return {
            "decision":
                "CORRECT",

            "proposed_action":
                "SET_TEMPORAL_STATUS",

            "proposed_temporal_status":
                temporal_label,

            "confidence":
                0.95,

            "reason":
                (
                    f"Marqueur textuel explicite compatible avec "
                    f"{temporal_label}."
                ),

            "temporal_evidence":
                evidence,

            "clinical_conflict":
                clinical_conflict,
        }

    if clinical_conflict is not None:
        return {
            "decision":
                "REVIEW",

            "proposed_action":
                "NONE",

            "proposed_temporal_status":
                None,

            "confidence":
                0.60,

            "reason":
                "Conflit potentiel de statut clinique dÃ©tectÃ© dans le texte.",

            "temporal_evidence":
                None,

            "clinical_conflict":
                clinical_conflict,
        }

    return {
        "decision":
            "KEEP",

        "proposed_action":
            "NONE",

        "proposed_temporal_status":
            current_temporal,

        "confidence":
            1.0,

        "reason":
            "Aucune temporalitÃ© supplÃ©mentaire n'est explicitement dÃ©montrÃ©e par le texte.",

        "temporal_evidence":
            None,

        "clinical_conflict":
            None,
    }


def main():
    payload = json.loads(
        INPUT_FILE.read_text(
            encoding="utf-8"
        )
    )

    candidates = payload.get(
        "candidates",
        [],
    )

    decisions = []

    decision_counts = Counter()
    action_counts = Counter()
    temporal_counts = Counter()

    for item in candidates:
        result = classify(item)

        row = {
            **item,
            **result,
        }

        decisions.append(row)

        decision_counts[
            result["decision"]
        ] += 1

        action_counts[
            result["proposed_action"]
        ] += 1

        if result.get(
            "proposed_temporal_status"
        ):
            temporal_counts[
                result[
                    "proposed_temporal_status"
                ]
            ] += 1

    OUTPUT_FILE.write_text(
        json.dumps(
            {
                "classifier":
                    "temporal_status_classifier",

                "mode":
                    "AUTONOMOUS_TEXT_GUIDED",

                "summary": {
                    "cases_received":
                        len(candidates),

                    "decision_counts":
                        dict(decision_counts),

                    "action_counts":
                        dict(action_counts),

                    "proposed_temporal_counts":
                        dict(temporal_counts),
                },

                "decisions":
                    decisions,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=" * 112)
    print("TRACE / SGCE - TEMPORAL STATUS CLASSIFIER - TEXT-GUIDED REPAIR")
    print("=" * 112)
    print(
        f"Cas reÃ§us                           : {len(candidates)}"
    )
    print()
    print("DECISIONS")
    print("-" * 112)

    for key, value in decision_counts.items():
        print(
            f"{key:<52}: {value}"
        )

    print()
    print("ACTIONS PROPOSEES")
    print("-" * 112)

    for key, value in action_counts.items():
        print(
            f"{key:<52}: {value}"
        )

    print()
    print("TEMPORALITES PROPOSEES")
    print("-" * 112)

    for key, value in temporal_counts.items():
        print(
            f"{key:<52}: {value}"
        )

    print()
    print(
        f"Sortie                              : {OUTPUT_FILE}"
    )
    print()
    print(
        "Aucune donnÃ©e clinique n'a Ã©tÃ© modifiÃ©e."
    )


if __name__ == "__main__":
    main()

