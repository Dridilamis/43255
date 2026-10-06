# -*- coding: utf-8 -*-
"""
agent_pattern_a.py
==================

Generic TRACE/SGCE Agent A
Pattern A = composite non dÃ©composÃ©.

Possible actions:
- SPLIT
- KEEP
- REVIEW

No clinical JSON is modified.
"""

import json
import re
from pathlib import Path
from Reduction_hallucinations.SGCE.MultiAgent.multiagent_common import load_json, write_json, safe_decision


BASE_DIR = Path(
    r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM\Reduction_hallucinations"
)

QUEUE_FILE = BASE_DIR / "MultiAgent" / "queues" / "agent_a_queue.json"
OUTPUT_FILE = BASE_DIR / "MultiAgent" / "outputs" / "agent_a_decisions.json"


DOSE_PATTERNS = [
    r"\b\d+(?:[.,]\d+)?\s*(?:mg|g|mcg|Âµg|ml|mL|ui|UI)\b",
    r"\b\d+\s*[xÃ—]\s*\d+\s*(?:/jour|par jour|j)\b",
]

DURATION_PATTERNS = [
    r"\bpendant\s+\d+\s*(?:jour|jours|j)\b",
    r"\b\d+\s*(?:jour|jours|j)\b",
]

FREQUENCY_PATTERNS = [
    r"\b\d+\s*(?:fois|x)\s*(?:par jour|/jour|/j)\b",
]


def candidate_text(candidate):
    symbolic = candidate.get("symbolic_candidate", {})

    possible = []

    for key in (
        "entity",
        "source_entity",
        "target_entity",
        "reified_entity",
    ):
        obj = symbolic.get(key)
        if isinstance(obj, dict):
            for tkey in ("text", "name", "preuve", "valeur"):
                if obj.get(tkey):
                    possible.append(str(obj[tkey]))

    for key in (
        "text",
        "entity_text",
        "value",
        "preuve",
    ):
        if symbolic.get(key):
            possible.append(str(symbolic[key]))

    return " | ".join(dict.fromkeys(possible))


def detect_components(text):
    found = []

    for pattern in DOSE_PATTERNS:
        for m in re.finditer(pattern, text, flags=re.I):
            found.append({
                "type": "POSOLOGIE",
                "text": m.group(0),
            })

    for pattern in FREQUENCY_PATTERNS:
        for m in re.finditer(pattern, text, flags=re.I):
            found.append({
                "type": "POSOLOGIE",
                "text": m.group(0),
            })

    for pattern in DURATION_PATTERNS:
        for m in re.finditer(pattern, text, flags=re.I):
            found.append({
                "type": "EVENEMENT_TEMPOREL",
                "text": m.group(0),
            })

    unique = []
    seen = set()

    for x in found:
        key = (x["type"], x["text"].lower())
        if key not in seen:
            seen.add(key)
            unique.append(x)

    return unique


def decide(item):
    cid = item.get("candidate_id")
    document = item.get("document")
    text = candidate_text(item)

    components = detect_components(text)

    if components:
        return safe_decision(
            cid,
            document,
            "A",
            "agent_pattern_a",
            decision="CORRECT",
            action="SPLIT",
            confidence=0.88,
            evidence=text,
            reason=(
                "Le contenu composite contient des sous-informations "
                "explicitement identifiables."
            ),
            proposed_entities=components,
            metadata={
                "component_count": len(components),
                "original_status": item.get("original_status"),
            },
        )

    return safe_decision(
        cid,
        document,
        "A",
        "agent_pattern_a",
        decision="REVIEW",
        action="NONE",
        confidence=0.45,
        evidence=text,
        reason=(
            "Aucune dÃ©composition explicite suffisamment fiable "
            "n'a Ã©tÃ© trouvÃ©e automatiquement."
        ),
        metadata={
            "original_status": item.get("original_status"),
        },
    )


def main():
    if not QUEUE_FILE.exists():
        raise FileNotFoundError(f"Queue A introuvable : {QUEUE_FILE}")

    queue = load_json(QUEUE_FILE)
    decisions = [decide(item) for item in queue]

    write_json(
        OUTPUT_FILE,
        {
            "agent": "agent_pattern_a",
            "cases_received": len(queue),
            "decisions": decisions,
        },
    )

    counts = {}

    for d in decisions:
        counts[d["action"]] = counts.get(d["action"], 0) + 1

    print("=" * 84)
    print("TRACE / SGCE - GENERIC AGENT PATTERN A")
    print("=" * 84)
    print(f"Cas reÃ§us     : {len(queue)}")
    print(f"DÃ©cisions     : {len(decisions)}")

    for action, count in sorted(counts.items()):
        print(f"{action:<32}: {count}")

    print(f"Sortie        : {OUTPUT_FILE}")
    print("Aucun JSON clinique n'a Ã©tÃ© modifiÃ©.")


if __name__ == "__main__":
    main()

