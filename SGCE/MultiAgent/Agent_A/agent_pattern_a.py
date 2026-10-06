# -*- coding: utf-8 -*-
# Helpers intégrés localement; aucune dépendance common.py.
import json
import re
import unicodedata
from pathlib import Path


ALLOWED_DECISIONS = {
    "CORRECT",
    "REJECT",
    "KEEP",
    "REVIEW",
}

ALLOWED_ACTIONS = {
    "SPLIT",
    "RELINK",
    "CREATE_FROM_EXPLICIT_EVIDENCE",
    "MERGE",
    "REMOVE_RELATION",
    "KEEP",
    "NONE",
}


def load_json(path):
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def normalize(text):
    text = "" if text is None else str(text)
    text = text.replace("’", "'")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        c for c in text
        if not unicodedata.combining(c)
    )
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokens(text):
    return {
        x for x in re.findall(r"[a-z0-9]+", normalize(text))
        if len(x) >= 2
    }


def text_similarity(a, b):
    na = normalize(a)
    nb = normalize(b)

    if not na or not nb:
        return 0.0

    if na == nb:
        return 1.0

    if na in nb or nb in na:
        shorter = min(len(na), len(nb))
        longer = max(len(na), len(nb))
        return 0.85 + 0.15 * (shorter / max(1, longer))

    ta = tokens(a)
    tb = tokens(b)

    if not ta or not tb:
        return 0.0

    inter = len(ta & tb)
    union = len(ta | tb)

    jaccard = inter / union if union else 0.0
    containment = inter / min(len(ta), len(tb))

    return 0.45 * jaccard + 0.55 * containment


def validate_decision(decision):
    errors = []

    if decision.get("decision") not in ALLOWED_DECISIONS:
        errors.append("decision non autorisée")

    if decision.get("action") not in ALLOWED_ACTIONS:
        errors.append("action non autorisée")

    try:
        confidence = float(decision.get("confidence", 0))
    except Exception:
        errors.append("confidence invalide")
        confidence = -1

    if not 0.0 <= confidence <= 1.0:
        errors.append("confidence hors [0,1]")

    if (
        decision.get("action") == "CREATE_FROM_EXPLICIT_EVIDENCE"
        and not str(decision.get("evidence", "")).strip()
    ):
        errors.append("création sans preuve explicite interdite")

    return errors


def safe_decision(
    candidate_id,
    document,
    pattern,
    agent,
    decision="REVIEW",
    action="NONE",
    confidence=0.0,
    evidence="",
    reason="",
    proposed_entities=None,
    proposed_relations=None,
    metadata=None,
):
    result = {
        "candidate_id": candidate_id,
        "document": document,
        "pattern": pattern,
        "agent": agent,
        "decision": decision,
        "action": action,
        "confidence": float(confidence),
        "evidence": evidence or "",
        "reason": reason or "",
        "proposed_entities": proposed_entities or [],
        "proposed_relations": proposed_relations or [],
        "metadata": metadata or {},
    }

    errors = validate_decision(result)

    if errors:
        result["decision"] = "REVIEW"
        result["action"] = "NONE"
        result["confidence"] = 0.0
        result["reason"] = (
            "Décision rejetée par le contrôle de schéma : "
            + "; ".join(errors)
        )
        result["metadata"]["schema_errors"] = errors

    return result


"""
agent_pattern_a.py
==================

Generic TRACE/SGCE Agent A
Pattern A = composite non décomposé.

Possible actions:
- SPLIT
- KEEP
- REVIEW

No clinical JSON is modified.
"""

import json
import re
from pathlib import Path



AGENT_DIR = Path(__file__).resolve().parent
MULTIAGENT_DIR = AGENT_DIR.parent
SGCE_DIR = MULTIAGENT_DIR.parent
BASE_DIR = SGCE_DIR.parent
M = MULTIAGENT_DIR
PATTERNS_DIR = SGCE_DIR / "Patterns"
QUEUE_FILE = MULTIAGENT_DIR / "queues" / "agent_a_queue.json"
OUTPUT_FILE = MULTIAGENT_DIR / "outputs" / "agent_a_decisions.json"


DOSE_PATTERNS = [
    r"\b\d+(?:[.,]\d+)?\s*(?:mg|g|mcg|µg|ml|mL|ui|UI)\b",
    r"\b\d+\s*[x×]\s*\d+\s*(?:/jour|par jour|j)\b",
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
            "Aucune décomposition explicite suffisamment fiable "
            "n'a été trouvée automatiquement."
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
    print(f"Cas reçus     : {len(queue)}")
    print(f"Décisions     : {len(decisions)}")

    for action, count in sorted(counts.items()):
        print(f"{action:<32}: {count}")

    print(f"Sortie        : {OUTPUT_FILE}")
    print("Aucun JSON clinique n'a été modifié.")


if __name__ == "__main__":
    main()
