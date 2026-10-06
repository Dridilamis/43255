# -*- coding: utf-8 -*-
"""
negation_validator.py
TRACE / SGCE - NEGATION VALIDATOR - CONSERVATIVE LOCAL SCOPE V4

SAFE_ACCEPT uniquement si le classifier courant fournit:
- SUPPORTED_NEGATION
- SET_NEGATED
- mention localisÃ©e
- containment exact
- target_match_score == 1.0
- confidence == 1.0
- resolver_pass == DIRECT_LOCAL_SCOPE

Le validateur vÃ©rifie aussi que le nombre de dÃ©cisions correspond
au nombre de candidats de l'exÃ©cution courante.
"""

import json
from pathlib import Path
from collections import Counter

BASE_DIR = Path(
    r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM"
    r"\Reduction_hallucinations"
)

CANDIDATE_FILE = (
    BASE_DIR / "negation Etage 7"
    / "queues" / "negation_candidates.json"
)
INPUT_FILE = (
    BASE_DIR / "negation Etage 7"
    / "outputs" / "negation_scope_decisions.json"
)
OUTPUT_FILE = (
    BASE_DIR / "negation Etage 7"
    / "outputs" / "negation_validated.json"
)
OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

def load_json(path):
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)

def validate(x):
    proposed = x.get("proposed_action", "NONE")
    scope = x.get("selected_scope") or {}

    if proposed == "KEEP_NEGATED":
        if (
            x.get("decision") == "SUPPORTED_NEGATION"
            and x.get("mention_found") is True
            and scope.get("resolver_pass") == "DIRECT_LOCAL_SCOPE"
            and scope.get("full_offset_containment") is True
            and float(scope.get("target_match_score", 0) or 0) == 1.0
            and float(x.get("confidence", 0) or 0) == 1.0
        ):
            return "ALREADY_SATISFIED", "NONE", "NEGATED existant confirmÃ© par un scope local exact."
        return "REVIEW", "NONE", "NEGATED existant non suffisamment confirmÃ©."

    if proposed == "SET_NEGATED":
        safe = (
            x.get("decision") == "SUPPORTED_NEGATION"
            and x.get("mention_found") is True
            and x.get("match_quality") in {"EXACT", "NORMALIZED"}
            and scope.get("resolver_pass") == "DIRECT_LOCAL_SCOPE"
            and scope.get("full_offset_containment") is True
            and float(scope.get("target_match_score", 0) or 0) == 1.0
            and float(x.get("confidence", 0) or 0) == 1.0
        )
        if safe:
            return "SAFE_ACCEPT", "SET_NEGATED", "NÃ©gation explicitement ancrÃ©e Ã  la mention dans un scope local."
        return "REJECT_HARMFUL", "NONE", "Correction bloquÃ©e: scope local insuffisant ou ambigu."

    return "UNRESOLVED", "NONE", "Aucune correction automatique dÃ©montrÃ©e."

def main():
    candidates_payload = load_json(CANDIDATE_FILE)
    decisions_payload = load_json(INPUT_FILE)

    candidates = candidates_payload.get("candidates", [])
    decisions = decisions_payload.get("decisions", [])

    # Protection essentielle contre les anciens fichiers de dÃ©cisions.
    if len(decisions) != len(candidates):
        raise RuntimeError(
            "INCOHERENCE D'EXECUTION: "
            f"{len(candidates)} candidats actuels mais {len(decisions)} dÃ©cisions. "
            "RÃ©exÃ©cutez negation_classifier.py avant le validator."
        )

    candidate_ids = [str(x.get("candidate_id")) for x in candidates]
    decision_ids = [str(x.get("candidate_id")) for x in decisions]
    if candidate_ids != decision_ids:
        raise RuntimeError(
            "INCOHERENCE D'EXECUTION: les candidate_id des dÃ©cisions "
            "ne correspondent pas exactement aux candidats actuels."
        )

    rows = []
    sc = Counter()
    ac = Counter()
    rc = Counter()

    for x in decisions:
        final, action, reason = validate(x)
        y = {
            **x,
            "final_status": final,
            "final_action": action,
            "validator_reason": reason,
        }
        rows.append(y)
        sc[final] += 1
        ac[action] += 1
        if final in {"REVIEW", "REJECT_HARMFUL", "UNRESOLVED"}:
            rc[reason] += 1

    OUTPUT_FILE.write_text(
        json.dumps({
            "validator": "negation_validator",
            "mode": "CONSERVATIVE_LOCAL_SCOPE_V4",
            "summary": {
                "candidates_current_run": len(candidates),
                "decisions_received": len(decisions),
                "final_status_counts": dict(sc),
                "final_action_counts": dict(ac),
            },
            "validated_decisions": rows,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("=" * 112)
    print("TRACE / SGCE - NEGATION VALIDATOR  ")
    print("=" * 112)
    print(f"Candidats exÃ©cution courante        : {len(candidates)}")
    print(f"DÃ©cisions reÃ§ues                    : {len(decisions)}")
    print("\nSTATUTS FINAUX")
    print("-" * 112)
    for k, v in sc.items():
        print(f"{k:<52}: {v}")
    print("\nACTIONS FINALES")
    print("-" * 112)
    for k, v in ac.items():
        print(f"{k:<52}: {v}")
    if rc:
        print("\nRAISONS NON-AUTOMATIQUES")
        print("-" * 112)
        for k, v in rc.items():
            print(f"{k:<90}: {v}")
    print(f"\nSortie                              : {OUTPUT_FILE}")
    print("\nAucune donnÃ©e clinique n'a Ã©tÃ© modifiÃ©e.")

if __name__ == "__main__":
    main()

