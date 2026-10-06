# -*- coding: utf-8 -*-
"""
negation_classifier.py
TRACE / SGCE - NEGATION CLASSIFIER - CONSERVATIVE LOCAL SCOPE V4

EntrÃ©e:
  MultiAgent/negation_audit/queues/negation_candidates.json

Sortie:
  MultiAgent/negation_audit/outputs/negation_scope_decisions.json

Principe:
- aucune donnÃ©e clinique n'est modifiÃ©e ;
- une nÃ©gation n'est proposÃ©e que si son scope local contient/ancre la mention ;
- la simple prÃ©sence de "pas/sans/absence/nÃ©gatif" dans la phrase ne suffit pas.
"""

import json
import re
import unicodedata
from pathlib import Path
from collections import Counter

BASE_DIR = Path(
    r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM"
    r"\Reduction_hallucinations"
)

INPUT_FILE = (
    BASE_DIR / "negation Etage 7"
    / "queues" / "negation_candidates.json"
)
OUTPUT_FILE = (
    BASE_DIR / "negation Etage 7"
    / "outputs" / "negation_scope_decisions.json"
)
OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

PREFIX_PATTERNS = [
    r"(?:^|[\s,;:(])absence\s+d(?:e|['â€™])\s*$",
    r"(?:^|[\s,;:(])en\s+l['â€™]absence\s+d(?:e|['â€™])\s*$",
    r"(?:^|[\s,;:(])sans\s+$",
    r"(?:^|[\s,;:(])pas\s+d(?:e|['â€™])\s*$",
    r"(?:^|[\s,;:(])aucun(?:e)?\s+$",
    r"(?:^|[\s,;:(])ni\s+$",
]

# Ces marqueurs doivent suivre immÃ©diatement ou quasi immÃ©diatement la mention.
SUFFIX_PATTERNS = [
    r"^\s*(?:est|sont|reste|restent)?\s*"
    r"(?:n[e']?gatif|negative|negatifs|negatives)\b",
    r"^\s*(?:non\s+retrouvee?|non\s+retrouve|non\s+objectivee?|non\s+objective)\b",
    r"^\s*:\s*(?:negatif|negative|negatifs|negatives)\b",
]

def load_json(path):
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)

def norm(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("â€™", "'").replace("`", "'")
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()

def local_scope(item):
    sentence = str(item.get("sentence") or "")
    mention = str(item.get("entity_text") or "")
    ms = item.get("mention_start")
    me = item.get("mention_end")

    if not item.get("mention_found") or ms is None or me is None:
        return None

    try:
        ms, me = int(ms), int(me)
    except Exception:
        return None

    if ms < 0 or me <= ms or me > len(sentence):
        return None

    actual = sentence[ms:me]
    # garde anti-offset: la zone doit correspondre Ã  la mention normalisÃ©e
    if norm(actual) != norm(mention):
        return None

    # FenÃªtres locales: assez grandes pour "en l'absence de", mais pas toute la phrase.
    left = sentence[max(0, ms - 55):ms]
    right = sentence[me:min(len(sentence), me + 45)]

    left_n = norm(left)
    right_n = norm(right)

    for pat in PREFIX_PATTERNS:
        m = re.search(pat, left_n, flags=re.IGNORECASE)
        if m:
            cue_text = left[m.start():] if m.start() < len(left) else left
            return {
                "resolver_pass": "DIRECT_LOCAL_SCOPE",
                "cue_side": "LEFT",
                "cue_text": cue_text.strip(),
                "scope_text": sentence[max(0, ms - 55):me],
                "full_offset_containment": True,
                "target_match_score": 1.0,
            }

    for pat in SUFFIX_PATTERNS:
        m = re.search(pat, right_n, flags=re.IGNORECASE)
        if m:
            return {
                "resolver_pass": "DIRECT_LOCAL_SCOPE",
                "cue_side": "RIGHT",
                "cue_text": right[:max(1, m.end())].strip(),
                "scope_text": sentence[ms:min(len(sentence), me + 45)],
                "full_offset_containment": True,
                "target_match_score": 1.0,
            }

    return None


# Semantic guard: lexical negation must negate the extracted clinical target itself.
# These constructions negate a meta-state / decision, not automatically the nearby
# disease, treatment, symptom, biomarker, etc.
SEMANTIC_META_NEGATION_PATTERNS = [
    r"\babsence\s+d['â€™]?\s*amelioration\b",
    r"\babsence\s+de\s+reponse\b",
    r"\babsence\s+d['â€™]?\s*evolution\b",
    r"\bpas\s+d['â€™]?\s*amelioration\b",
    r"\bpas\s+d['â€™]?\s*indication\b",
    r"\baucune?\s+indication\b",
    r"\bpas\s+necessaire\b",
    r"\bne\s+necessite\s+pas\b",
]

def semantic_negation_guard(item, scope):
    """Return (protected, reason). Conservative: protect ambiguous meta-negation."""
    if scope is None:
        return False, None
    sentence = norm(item.get("sentence") or "")
    mention = norm(item.get("entity_text") or "")
    if not sentence or not mention:
        return True, "Mention ou contexte insuffisant pour confirmer la cible sÃ©mantique."

    for pat in SEMANTIC_META_NEGATION_PATTERNS:
        if re.search(pat, sentence, flags=re.IGNORECASE):
            # If the extracted mention itself is the negated meta-concept
            # (e.g. "amÃ©lioration"), it may legitimately be negated.
            meta_terms = ("amelioration", "reponse", "evolution", "indication")
            if not any(t in mention for t in meta_terms):
                return True, (
                    "NÃ©gation mÃ©ta-clinique/dÃ©cisionnelle dÃ©tectÃ©e; "
                    "elle ne prouve pas la nÃ©gation de l'entitÃ© cible."
                )
    return False, None


def classify(item):
    current = str(item.get("current_clinical_status") or "").upper()
    scope = local_scope(item)
    protected, guard_reason = semantic_negation_guard(item, scope)

    row = dict(item)
    row.update({
        "decision": "NO_SUPPORTED_NEGATION",
        "proposed_action": "NONE",
        "confidence": 0.0,
        "selected_scope": scope,
        "classifier_reason": "Aucun scope local de nÃ©gation dÃ©montrÃ© pour cette mention.",
    })

    if scope is not None and protected:
        row["decision"] = "REVIEW_SEMANTIC_SCOPE"
        row["proposed_action"] = "NONE"
        row["confidence"] = 0.0
        row["classifier_reason"] = guard_reason
    elif scope is not None:
        row["decision"] = "SUPPORTED_NEGATION"
        row["confidence"] = 1.0
        if current == "NEGATED":
            row["proposed_action"] = "KEEP_NEGATED"
            row["classifier_reason"] = "Statut NEGATED existant confirmÃ© par un scope local explicite."
        else:
            row["proposed_action"] = "SET_NEGATED"
            row["classifier_reason"] = "NÃ©gation locale explicitement ancrÃ©e Ã  la mention."
    elif current == "NEGATED":
        row["decision"] = "REVIEW_EXISTING_NEGATION"
        row["classifier_reason"] = (
            "Statut NEGATED existant sans preuve locale suffisamment sÃ»re; aucune modification automatique."
        )

    return row

def main():
    payload = load_json(INPUT_FILE)
    candidates = payload.get("candidates", [])
    decisions = []
    dc = Counter()
    ac = Counter()

    for item in candidates:
        row = classify(item)
        decisions.append(row)
        dc[row["decision"]] += 1
        ac[row["proposed_action"]] += 1

    OUTPUT_FILE.write_text(
        json.dumps({
            "classifier": "negation_classifier",
            "mode": "CONSERVATIVE_LOCAL_SCOPE_V4",
            "source_candidate_count": len(candidates),
            "summary": {
                "candidates_received": len(candidates),
                "decisions_written": len(decisions),
                "decision_counts": dict(dc),
                "action_counts": dict(ac),
            },
            "decisions": decisions,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("=" * 112)
    print("TRACE / SGCE - NEGATION CLASSIFIER ")
    print("=" * 112)
    print(f"Candidats reÃ§us                     : {len(candidates)}")
    print(f"DÃ©cisions Ã©crites                   : {len(decisions)}")
    print("\nDECISIONS")
    print("-" * 112)
    for k, v in dc.items():
        print(f"{k:<52}: {v}")
    print("\nACTIONS PROPOSEES")
    print("-" * 112)
    for k, v in ac.items():
        print(f"{k:<52}: {v}")
    print(f"\nSortie                              : {OUTPUT_FILE}")
    print("\nAucune donnÃ©e clinique n'a Ã©tÃ© modifiÃ©e.")

if __name__ == "__main__":
    main()

