# -*- coding: utf-8 -*-
"""
multiagent_common.py
====================

Common utilities for TRACE/SGCE multi-agent modules.

All agents:
- read queues only
- never modify clinical JSONs
- return a common decision schema
"""

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
