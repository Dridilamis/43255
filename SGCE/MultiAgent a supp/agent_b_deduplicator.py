# -*- coding: utf-8 -*-
"""
agent_b_deduplicator.py
=======================

TRACE / SGCE â€” DÃ©duplication des dÃ©cisions validÃ©es de l'Agent B

EntrÃ©e :
  MultiAgent/outputs/agent_b_validated_decisions.json

Objectif
--------
DÃ©dupliquer les corrections ACCEPT avant toute modification clinique.

RÃ¨gles
------
1) MÃªme document + mÃªme endpoint + mÃªme type + mÃªme texte proposÃ©
   -> une seule correction unique.

2) MÃªme document + mÃªme endpoint mais propositions diffÃ©rentes
   -> CONFLICT / REVIEW, aucune correction automatique.

3) Les cas REVIEW / NONE / REFINE_ENTITY_SPAN sont conservÃ©s
   pour audit mais ne deviennent pas actionnables.

Sortie :
  MultiAgent/outputs/agent_b_deduplicated_decisions.json

Aucun JSON clinique n'est modifiÃ©.
"""

import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


# ============================================================
# 1. PATHS
# ============================================================

BASE_DIR = Path(
    r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM"
    r"\Reduction_hallucinations"
)

MULTIAGENT_DIR = BASE_DIR / "MultiAgent"

INPUT_FILE = (
    MULTIAGENT_DIR
    / "outputs"
    / "agent_b_validated_decisions.json"
)

OUTPUT_FILE = (
    MULTIAGENT_DIR
    / "outputs"
    / "agent_b_deduplicated_decisions.json"
)


# ============================================================
# 2. HELPERS
# ============================================================

def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize(text):
    text = "" if text is None else str(text)
    text = text.replace("â€™", "'")

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
        r"[^a-z0-9]+",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def extract_proposed_entity(item):
    agent_decision = (
        item.get("agent_decision")
        or {}
    )

    proposed = (
        agent_decision.get("proposed_entities")
        or []
    )

    if len(proposed) != 1:
        return None

    entity = proposed[0]

    return {
        "type":
            entity.get("type"),

        "text":
            entity.get("text"),
    }


def extract_missing_endpoint(item):
    agent_decision = (
        item.get("agent_decision")
        or {}
    )

    metadata = (
        agent_decision.get("metadata")
        or {}
    )

    return metadata.get(
        "missing_endpoint"
    )


def extract_page_number(item):
    agent_decision = (
        item.get("agent_decision")
        or {}
    )

    metadata = (
        agent_decision.get("metadata")
        or {}
    )

    return metadata.get(
        "page_number"
    )


def extract_relation_type(item):
    for check in item.get("checks", []) or []:
        if check.get("check") == "RELATION_TYPE_RECOVERED":
            return check.get("relation_type")

    return None


def extract_role(item):
    for check in item.get("checks", []) or []:
        if check.get("check") == "ROLE_SIGNATURE_COMPATIBLE":
            return check.get("role")

    return None


def correction_signature(item):
    """
    Signature sÃ©mantique d'une proposition ACCEPT.
    """

    proposed = extract_proposed_entity(
        item
    )

    if proposed is None:
        return None

    return (
        normalize(
            proposed.get("type")
        ),
        normalize(
            proposed.get("text")
        ),
    )


def endpoint_key(item):
    """
    La clÃ© d'identitÃ© de l'endpoint manquant.
    L'ID d'entitÃ© n'est unique qu'Ã  l'intÃ©rieur d'un document.
    """

    return (
        item.get("document"),
        extract_missing_endpoint(item),
    )


# ============================================================
# 3. DEDUPLICATION
# ============================================================

def deduplicate_accepts(accepted):
    groups = defaultdict(list)

    for item in accepted:
        groups[
            endpoint_key(item)
        ].append(item)

    unique_corrections = []
    conflicts = []
    duplicate_count = 0

    for key, items in groups.items():
        document, endpoint = key

        # Endpoint absent = impossible de dÃ©dupliquer de maniÃ¨re sÃ»re.
        if not document or not endpoint:
            conflicts.append({
                "document":
                    document,

                "missing_endpoint":
                    endpoint,

                "status":
                    "REVIEW",

                "action":
                    "NONE",

                "reason":
                    "DOCUMENT_OR_ENDPOINT_MISSING",

                "candidate_ids": [
                    item.get("candidate_id")
                    for item in items
                ],

                "proposals":
                    items,
            })

            continue

        signatures = defaultdict(list)

        for item in items:
            sig = correction_signature(
                item
            )

            signatures[
                sig
            ].append(item)

        # ----------------------------------------------------
        # Cas 1 : mÃªme endpoint + mÃªme proposition
        # ----------------------------------------------------

        if (
            len(signatures) == 1
            and None not in signatures
        ):
            sig = next(
                iter(signatures)
            )

            same_proposal = signatures[
                sig
            ]

            representative = same_proposal[
                0
            ]

            proposed = extract_proposed_entity(
                representative
            )

            candidate_ids = [
                item.get("candidate_id")
                for item in same_proposal
            ]

            relation_types = sorted({
                extract_relation_type(item)
                for item in same_proposal
                if extract_relation_type(item)
            })

            roles = sorted({
                extract_role(item)
                for item in same_proposal
                if extract_role(item)
            })

            duplicate_count += (
                len(
                    same_proposal
                )
                - 1
            )

            unique_corrections.append({
                "document":
                    document,

                "missing_endpoint":
                    endpoint,

                "page_number":
                    extract_page_number(
                        representative
                    ),

                "status":
                    "ACCEPT",

                "action":
                    "CREATE_FROM_EXPLICIT_EVIDENCE",

                "proposed_entity": {
                    "type":
                        proposed.get(
                            "type"
                        ),

                    "text":
                        proposed.get(
                            "text"
                        ),
                },

                "evidence":
                    (
                        representative.get(
                            "agent_decision",
                            {}
                        ).get(
                            "evidence",
                            ""
                        )
                    ),

                "relation_types":
                    relation_types,

                "roles":
                    roles,

                "source_candidate_ids":
                    candidate_ids,

                "duplicates_merged":
                    max(
                        0,
                        len(
                            same_proposal
                        )
                        - 1
                    ),

                "reason":
                    (
                        "Proposition validÃ©e unique pour cet endpoint. "
                        "Les candidats strictement identiques ont Ã©tÃ© fusionnÃ©s."
                    ),
            })

            continue

        # ----------------------------------------------------
        # Cas 2 : mÃªme endpoint mais propositions diffÃ©rentes
        # ----------------------------------------------------

        proposal_summaries = []

        for sig, proposal_items in signatures.items():
            first = proposal_items[
                0
            ]

            proposed = extract_proposed_entity(
                first
            )

            proposal_summaries.append({
                "signature":
                    sig,

                "proposed_entity":
                    proposed,

                "candidate_ids": [
                    item.get(
                        "candidate_id"
                    )
                    for item in proposal_items
                ],

                "relation_types":
                    sorted({
                        extract_relation_type(item)
                        for item in proposal_items
                        if extract_relation_type(item)
                    }),

                "roles":
                    sorted({
                        extract_role(item)
                        for item in proposal_items
                        if extract_role(item)
                    }),
            })

        conflicts.append({
            "document":
                document,

            "missing_endpoint":
                endpoint,

            "status":
                "REVIEW",

            "action":
                "NONE",

            "reason":
                "CONFLICTING_ACCEPTED_PROPOSALS_FOR_SAME_ENDPOINT",

            "candidate_ids": [
                item.get(
                    "candidate_id"
                )
                for item in items
            ],

            "proposals":
                proposal_summaries,
        })

    return (
        unique_corrections,
        conflicts,
        duplicate_count,
    )


# ============================================================
# 4. MAIN
# ============================================================

def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Rapport validÃ© introuvable : {INPUT_FILE}"
        )

    report = load_json(
        INPUT_FILE
    )

    validated = (
        report.get(
            "validated_decisions",
            []
        )
    )

    accepted = [
        item
        for item in validated
        if (
            item.get(
                "final_status"
            )
            == "ACCEPT"
            and item.get(
                "final_action"
            )
            == "CREATE_FROM_EXPLICIT_EVIDENCE"
        )
    ]

    refine_cases = [
        item
        for item in validated
        if item.get(
            "final_action"
        )
        == "REFINE_ENTITY_SPAN"
    ]

    review_none = [
        item
        for item in validated
        if (
            item.get(
                "final_status"
            )
            == "REVIEW"
            and item.get(
                "final_action"
            )
            == "NONE"
        )
    ]

    (
        unique_corrections,
        conflicts,
        duplicate_count,
    ) = deduplicate_accepts(
        accepted
    )

    output = {
        "deduplicator":
            "agent_b_deduplicator",

        "input_file":
            str(
                INPUT_FILE
            ),

        "summary": {
            "validated_decisions_received":
                len(
                    validated
                ),

            "raw_accepts":
                len(
                    accepted
                ),

            "unique_accepted_corrections":
                len(
                    unique_corrections
                ),

            "duplicates_merged":
                duplicate_count,

            "conflicts":
                len(
                    conflicts
                ),

            "refine_entity_span":
                len(
                    refine_cases
                ),

            "review_none":
                len(
                    review_none
                ),
        },

        "unique_corrections":
            unique_corrections,

        "conflicts":
            conflicts,

        "refine_entity_span_cases": [
            {
                "candidate_id":
                    item.get(
                        "candidate_id"
                    ),

                "document":
                    item.get(
                        "document"
                    ),

                "missing_endpoint":
                    extract_missing_endpoint(
                        item
                    ),

                "relation_type":
                    extract_relation_type(
                        item
                    ),

                "role":
                    extract_role(
                        item
                    ),

                "agent_decision":
                    item.get(
                        "agent_decision"
                    ),

                "reason":
                    item.get(
                        "reason"
                    ),
            }
            for item in refine_cases
        ],

        "review_none_cases": [
            {
                "candidate_id":
                    item.get(
                        "candidate_id"
                    ),

                "document":
                    item.get(
                        "document"
                    ),

                "missing_endpoint":
                    extract_missing_endpoint(
                        item
                    ),

                "reason":
                    item.get(
                        "reason"
                    ),
            }
            for item in review_none
        ],
    }

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_FILE.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=" * 96)
    print("TRACE / SGCE - AGENT B DEDUPLICATOR")
    print("=" * 96)

    print(
        f"DÃ©cisions validÃ©es reÃ§ues         : "
        f"{len(validated)}"
    )

    print(
        f"ACCEPT bruts                      : "
        f"{len(accepted)}"
    )

    print(
        f"Corrections ACCEPT uniques        : "
        f"{len(unique_corrections)}"
    )

    print(
        f"Doublons fusionnÃ©s                : "
        f"{duplicate_count}"
    )

    print(
        f"Conflits                          : "
        f"{len(conflicts)}"
    )

    print(
        f"REFINE_ENTITY_SPAN                : "
        f"{len(refine_cases)}"
    )

    print(
        f"REVIEW / NONE                     : "
        f"{len(review_none)}"
    )

    print()

    print("CORRECTIONS UNIQUES")
    print("-" * 96)

    if unique_corrections:
        for item in unique_corrections:
            entity = item[
                "proposed_entity"
            ]

            print(
                f"{item['document']} | "
                f"{item['missing_endpoint']} | "
                f"{entity.get('type')} | "
                f"{entity.get('text')} | "
                f"candidats={','.join(item['source_candidate_ids'])}"
            )
    else:
        print(
            "Aucune correction unique."
        )

    if conflicts:
        print()
        print("CONFLITS")
        print("-" * 96)

        for item in conflicts:
            print(
                f"{item.get('document')} | "
                f"{item.get('missing_endpoint')} | "
                f"{item.get('reason')}"
            )

    print()

    print(
        f"Sortie                            : "
        f"{OUTPUT_FILE}"
    )

    print()

    print(
        "Aucune donnÃ©e clinique n'a Ã©tÃ© modifiÃ©e."
    )


if __name__ == "__main__":
    main()

