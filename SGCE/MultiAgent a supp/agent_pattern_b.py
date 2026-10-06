# -*- coding: utf-8 -*-
"""
agent_pattern_b.py
==================

TRACE / SGCE â€” Agent Pattern B
Second recours avec ancrage documentaire textuel.

Supporte :
- B1 : endpoint / rÃ©fÃ©rence non rÃ©solu
- B2 : entitÃ© intermÃ©diaire manquante

Actions proposÃ©es :
- CREATE_FROM_EXPLICIT_EVIDENCE
- REVIEW / NONE

IMPORTANT
---------
- Aucun JSON clinique n'est modifiÃ©.
- Aucune entitÃ© n'est crÃ©Ã©e sans preuve textuelle explicite.
- Le script reste conservateur.
"""

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path


BASE_DIR = Path(
    r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM"
    r"\Reduction_hallucinations"
)

QUEUE_FILE = (
    BASE_DIR
    / "MultiAgent"
    / "queues"
    / "agent_b_queue_contextualized.json"
)

OUTPUT_DIR = (
    BASE_DIR
    / "MultiAgent"
    / "outputs"
)

OUTPUT_FILE = (
    OUTPUT_DIR
    / "agent_b_decisions.json"
)


# ============================================================
# 1. HELPERS
# ============================================================

def load_json(path):
    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


def normalize(text):
    text = "" if text is None else str(text)

    text = text.replace(
        "â€™",
        "'",
    )

    text = unicodedata.normalize(
        "NFKD",
        text,
    )

    text = "".join(
        c
        for c in text
        if not unicodedata.combining(c)
    )

    text = text.lower()

    text = re.sub(
        r"[^a-z0-9/+.-]+",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def sentence_split(text):
    parts = re.split(
        r"(?<=[.!?;:])\s+|\n+",
        text,
    )

    return [
        x.strip()
        for x in parts
        if x.strip()
    ]


# ============================================================
# 2. GENERIC TYPE LEXICON
# ============================================================

TYPE_LEXICON = {
    "IMAGERIE_PROCEDURE": [
        r"\btdm\b",
        r"\bscanner\b",
        r"\birm\b",
        r"\bradiograph",
        r"\bechograph",
        r"\bpet scan\b",
        r"\bimagerie\b",
    ],

    "TRAITEMENT": [
        r"\btraitement\b",
        r"\bantibiot",
        r"\btherapie\b",
        r"\bceftriax",
        r"\bamoxic",
        r"\bpiperac",
        r"\bvancomyc",
        r"\bamik",
        r"\bgentamic",
    ],

    "MICRO_ORGANISME": [
        r"\bstaphyloc",
        r"\bstreptoc",
        r"\bescherichia\b",
        r"\be coli\b",
        r"\bklebsiella\b",
        r"\bpseudomonas\b",
        r"\bcandida\b",
        r"\benteroc",
        r"\bgerme\b",
        r"\bbacter",
    ],

    "EVENEMENT_TEMPOREL": [
        r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
        r"\b\d{1,2}:\d{2}\b",
        r"\bj\d+\b",
        r"\bjour\s+\d+\b",
    ],

    "FOYER_INFECTIEUX": [
        r"\bpneumon",
        r"\bpulmonaire\b",
        r"\burinaire\b",
        r"\babdominal\b",
        r"\bfoyer\b",
        r"\binfection\b",
    ],

    "DEFAILLANCE_ORGANE": [
        r"\binsuffisance\b",
        r"\bdefaillance\b",
        r"\bira\b",
        r"\brespiratoire\b",
        r"\brenale\b",
        r"\bhepatique\b",
    ],

    "SYMPTOME": [
        r"\bdouleur\b",
        r"\bfievre\b",
        r"\btoux\b",
        r"\bdyspnee\b",
        r"\bvomissement\b",
        r"\bdiarrhee\b",
    ],

    "SIGNE_VITAL": [
        r"\btemperature\b",
        r"\bpression arterielle\b",
        r"\btension\b",
        r"\bfrequence cardiaque\b",
        r"\bsaturation\b",
        r"\bspo2\b",
    ],

    "BIOMARQUEUR": [
        r"\bcrp\b",
        r"\bpct\b",
        r"\bprocalcitonine\b",
        r"\bleucocyt",
        r"\bcreatinine\b",
        r"\blactate\b",
        r"\buree\b",
    ],

    "LABEL_NOSOLOGIQUE": [
        r"\bsepsis\b",
        r"\bchoc septique\b",
        r"\bdiagnostic\b",
        r"\bpneumonie\b",
    ],

    "POSOLOGIE": [
        r"\b\d+(?:[.,]\d+)?\s*(?:mg|g|mcg|ug|ml|ui)\b",
        r"\b\d+\s*[xÃ—]\s*\d+\b",
        r"\bpar jour\b",
        r"\b/j\b",
    ],

    "CONTEXTE_ACQUISITION": [
        r"\bnosocomial",
        r"\bcommunautaire\b",
        r"\bacquis\b",
        r"\bhospitalier\b",
    ],
}


# ============================================================
# 3. EVIDENCE SEARCH
# ============================================================

def extract_type_evidence(
    text,
    expected_type,
):
    if not text:
        return []

    patterns = TYPE_LEXICON.get(
        expected_type,
        [],
    )

    if not patterns:
        return []

    results = []

    for sentence in sentence_split(
        text
    ):
        normalized = normalize(
            sentence
        )

        matched = []

        for pattern in patterns:
            if re.search(
                pattern,
                normalized,
                flags=re.I,
            ):
                matched.append(
                    pattern
                )

        if matched:
            results.append({
                "text":
                    sentence,

                "matched_patterns":
                    matched,
            })

    # Deduplicate exact evidence sentences
    unique = []
    seen = set()

    for item in results:
        key = normalize(
            item[
                "text"
            ]
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        unique.append(
            item
        )

    return unique


# ============================================================
# 4. B1
# ============================================================

def decide_b1(item):
    symbolic = item.get(
        "symbolic_candidate",
        {},
    )

    endpoints = symbolic.get(
        "endpoint_validations",
        [],
    ) or []

    context = item.get(
        "text_context",
        {},
    )

    if not endpoints:
        return None

    endpoint = endpoints[0]

    expected_type = endpoint.get(
        "expected_type",
        "",
    )

    endpoint_value = endpoint.get(
        "endpoint_value",
        "",
    )

    page_text = context.get(
        "page_text",
        "",
    )

    evidence = extract_type_evidence(
        page_text,
        expected_type,
    )

    # Unique explicit evidence
    if len(evidence) == 1:
        return {
            "candidate_id":
                item.get(
                    "candidate_id"
                ),

            "document":
                item.get(
                    "document"
                ),

            "pattern":
                "B",

            "subpattern":
                "B1",

            "agent":
                "agent_pattern_b",

            "decision":
                "CORRECT",

            "action":
                "CREATE_FROM_EXPLICIT_EVIDENCE",

            "confidence":
                0.85,

            "evidence":
                evidence[
                    0
                ][
                    "text"
                ],

            "reason":
                (
                    "L'endpoint est absent du graphe, mais une seule preuve "
                    "textuelle explicite du type attendu est retrouvÃ©e."
                ),

            "proposed_entities": [
                {
                    "type":
                        expected_type,

                    "text":
                        evidence[
                            0
                        ][
                            "text"
                        ],
                }
            ],

            "proposed_relations":
                [],

            "metadata": {
                "missing_endpoint":
                    endpoint_value,

                "expected_type":
                    expected_type,

                "page_number":
                    context.get(
                        "page_number"
                    ),

                "text_file":
                    context.get(
                        "text_file"
                    ),

                "used_global_text_fallback":
                    context.get(
                        "used_global_text_fallback"
                    ),

                "evidence_candidates":
                    evidence,
            },
        }

    # Multiple possibilities
    if len(evidence) > 1:
        return {
            "candidate_id":
                item.get(
                    "candidate_id"
                ),

            "document":
                item.get(
                    "document"
                ),

            "pattern":
                "B",

            "subpattern":
                "B1",

            "agent":
                "agent_pattern_b",

            "decision":
                "REVIEW",

            "action":
                "NONE",

            "confidence":
                0.55,

            "evidence":
                " | ".join(
                    x[
                        "text"
                    ]
                    for x in evidence[
                        :5
                    ]
                ),

            "reason":
                (
                    "Plusieurs preuves textuelles du type attendu existent. "
                    "Aucune ne peut Ãªtre associÃ©e de faÃ§on unique Ã  l'endpoint."
                ),

            "proposed_entities":
                [],

            "proposed_relations":
                [],

            "metadata": {
                "missing_endpoint":
                    endpoint_value,

                "expected_type":
                    expected_type,

                "page_number":
                    context.get(
                        "page_number"
                    ),

                "text_file":
                    context.get(
                        "text_file"
                    ),

                "evidence_candidates":
                    evidence,
            },
        }

    # No evidence
    return {
        "candidate_id":
            item.get(
                "candidate_id"
            ),

        "document":
            item.get(
                "document"
            ),

        "pattern":
            "B",

        "subpattern":
            "B1",

        "agent":
            "agent_pattern_b",

        "decision":
            "REVIEW",

        "action":
            "NONE",

        "confidence":
            0.35,

        "evidence":
            "",

        "reason":
            (
                "Aucune preuve textuelle explicite du type attendu "
                "n'est retrouvÃ©e. La crÃ©ation automatique est interdite."
            ),

        "proposed_entities":
            [],

        "proposed_relations":
            [],

        "metadata": {
            "missing_endpoint":
                endpoint_value,

            "expected_type":
                expected_type,

            "page_number":
                context.get(
                    "page_number"
                ),

            "text_file":
                context.get(
                    "text_file"
                ),
        },
    }


# ============================================================
# 5. B2
# ============================================================

def decide_b2(item):
    symbolic = item.get(
        "symbolic_candidate",
        {},
    )

    missing_type = (
        symbolic.get(
            "middle_type_missing"
        )
        or symbolic.get(
            "missing_type"
        )
        or symbolic.get(
            "expected_intermediate_type"
        )
        or ""
    )

    if not missing_type:
        return None

    context = item.get(
        "text_context",
        {},
    )

    page_text = context.get(
        "page_text",
        "",
    )

    evidence = extract_type_evidence(
        page_text,
        missing_type,
    )

    if len(evidence) == 1:
        return {
            "candidate_id":
                item.get(
                    "candidate_id"
                ),

            "document":
                item.get(
                    "document"
                ),

            "pattern":
                "B",

            "subpattern":
                "B2",

            "agent":
                "agent_pattern_b",

            "decision":
                "CORRECT",

            "action":
                "CREATE_FROM_EXPLICIT_EVIDENCE",

            "confidence":
                0.85,

            "evidence":
                evidence[
                    0
                ][
                    "text"
                ],

            "reason":
                (
                    "Une preuve textuelle explicite et unique supporte "
                    "l'entitÃ© intermÃ©diaire manquante."
                ),

            "proposed_entities": [
                {
                    "type":
                        missing_type,

                    "text":
                        evidence[
                            0
                        ][
                            "text"
                        ],
                }
            ],

            "proposed_relations":
                [],

            "metadata": {
                "missing_type":
                    missing_type,

                "evidence_candidates":
                    evidence,
            },
        }

    return {
        "candidate_id":
            item.get(
                "candidate_id"
            ),

        "document":
            item.get(
                "document"
            ),

        "pattern":
            "B",

        "subpattern":
            "B2",

        "agent":
            "agent_pattern_b",

        "decision":
            "REVIEW",

        "action":
            "NONE",

        "confidence":
            0.40,

        "evidence":
            (
                " | ".join(
                    x[
                        "text"
                    ]
                    for x in evidence[
                        :5
                    ]
                )
                if evidence
                else ""
            ),

        "reason":
            (
                "Aucune preuve unique ne permet de reconstruire "
                "l'entitÃ© intermÃ©diaire de faÃ§on sÃ»re."
            ),

        "proposed_entities":
            [],

        "proposed_relations":
            [],

        "metadata": {
            "missing_type":
                missing_type,

            "evidence_candidates":
                evidence,
        },
    }


# ============================================================
# 6. MASTER
# ============================================================

def decide(item):
    subpattern = str(
        item.get(
            "subpattern",
            "",
        )
    ).upper()

    symbolic = item.get(
        "symbolic_candidate",
        {},
    )

    if (
        subpattern == "B1"
        or symbolic.get(
            "endpoint_validations"
        )
    ):
        result = decide_b1(
            item
        )

        if result is not None:
            return result

    if (
        subpattern == "B2"
        or symbolic.get(
            "middle_type_missing"
        )
        or symbolic.get(
            "missing_type"
        )
        or symbolic.get(
            "expected_intermediate_type"
        )
    ):
        result = decide_b2(
            item
        )

        if result is not None:
            return result

    return {
        "candidate_id":
            item.get(
                "candidate_id"
            ),

        "document":
            item.get(
                "document"
            ),

        "pattern":
            "B",

        "subpattern":
            subpattern,

        "agent":
            "agent_pattern_b",

        "decision":
            "REVIEW",

        "action":
            "NONE",

        "confidence":
            0.20,

        "evidence":
            "",

        "reason":
            "Structure Pattern B non reconnue.",

        "proposed_entities":
            [],

        "proposed_relations":
            [],

        "metadata":
            {},
    }


# ============================================================
# 7. MAIN
# ============================================================

def main():
    if not QUEUE_FILE.exists():
        raise FileNotFoundError(
            f"Queue contextualisÃ©e Pattern B introuvable : "
            f"{QUEUE_FILE}"
        )

    queue = load_json(
        QUEUE_FILE
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    decisions = [
        decide(
            item
        )
        for item in queue
    ]

    decision_counts = Counter(
        d[
            "decision"
        ]
        for d in decisions
    )

    action_counts = Counter(
        d[
            "action"
        ]
        for d in decisions
    )

    output = {
        "agent":
            "agent_pattern_b",

        "mode":
            "TEXT_DOCUMENT_GROUNDED",

        "summary": {
            "cases_received":
                len(
                    queue
                ),

            "decisions_written":
                len(
                    decisions
                ),

            "decision_counts":
                dict(
                    decision_counts
                ),

            "action_counts":
                dict(
                    action_counts
                ),
        },

        "decisions":
            decisions,
    }

    OUTPUT_FILE.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=" * 92)
    print("TRACE / SGCE - AGENT PATTERN B")
    print("=" * 92)

    print(
        f"Cas reÃ§us                         : "
        f"{len(queue)}"
    )

    print(
        f"DÃ©cisions produites               : "
        f"{len(decisions)}"
    )

    print()

    print("DECISIONS")
    print("-" * 92)

    for name, count in (
        decision_counts.most_common()
    ):
        print(
            f"{name:<40}: {count}"
        )

    print()

    print("ACTIONS PROPOSEES")
    print("-" * 92)

    for name, count in (
        action_counts.most_common()
    ):
        print(
            f"{name:<40}: {count}"
        )

    print()

    print(
        f"Sortie                            : "
        f"{OUTPUT_FILE}"
    )

    print()

    print(
        "Aucun JSON clinique n'a Ã©tÃ© modifiÃ©."
    )


if __name__ == "__main__":
    main()

