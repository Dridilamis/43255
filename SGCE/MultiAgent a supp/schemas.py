# -*- coding: utf-8 -*-
"""
schemas.py
==========

Schémas communs pour le sous-système multi-agent TRACE/SGCE.

Principe:
- Les agents ne modifient jamais directement les JSON cliniques.
- Ils produisent uniquement une proposition structurée.
- Un validateur déterministe contrôle ensuite la proposition.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any


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


@dataclass
class AgentDecision:
    candidate_id: str
    pattern: str
    agent: str

    decision: str
    action: str

    confidence: float = 0.0

    evidence: str = ""
    reason: str = ""

    proposed_entities: List[Dict[str, Any]] = field(default_factory=list)
    proposed_relations: List[Dict[str, Any]] = field(default_factory=list)

    metadata: Dict[str, Any] = field(default_factory=dict)

    def validate_schema(self):
        errors = []

        if self.decision not in ALLOWED_DECISIONS:
            errors.append(
                f"decision non autorisée: {self.decision}"
            )

        if self.action not in ALLOWED_ACTIONS:
            errors.append(
                f"action non autorisée: {self.action}"
            )

        if not (0.0 <= float(self.confidence) <= 1.0):
            errors.append(
                "confidence doit être comprise entre 0 et 1"
            )

        if self.action == "CREATE_FROM_EXPLICIT_EVIDENCE" and not self.evidence.strip():
            errors.append(
                "CREATE_FROM_EXPLICIT_EVIDENCE exige une preuve explicite."
            )

        return errors

    def to_dict(self):
        return asdict(self)
