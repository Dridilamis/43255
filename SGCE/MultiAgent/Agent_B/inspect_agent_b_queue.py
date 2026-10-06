# -*- coding: utf-8 -*-
"""
inspect_agent_b_queue.py
========================

Diagnostic non destructif de la queue Pattern B.

Affiche :
- nombre de cas
- subpatterns B1/B2
- statuts originaux
- clés les plus fréquentes dans symbolic_candidate
- présence de endpoint_validations
- présence des champs B2
- exemples compacts de candidats

Aucun fichier clinique n'est modifié.
"""

import json
from collections import Counter
from pathlib import Path


AGENT_DIR = Path(__file__).resolve().parent
MULTIAGENT_DIR = AGENT_DIR.parent
SGCE_DIR = MULTIAGENT_DIR.parent
BASE_DIR = SGCE_DIR.parent
M = MULTIAGENT_DIR
PATTERNS_DIR = SGCE_DIR / "Patterns"
QUEUE_FILE = (
    MULTIAGENT_DIR
    / "queues"
    / "agent_b_queue.json"
)


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main():
    if not QUEUE_FILE.exists():
        raise FileNotFoundError(
            f"Queue B introuvable : {QUEUE_FILE}"
        )

    queue = load_json(QUEUE_FILE)

    subpatterns = Counter()
    statuses = Counter()
    symbolic_keys = Counter()

    endpoint_validation_count = 0
    endpoint_validation_lengths = Counter()

    b2_missing_type_fields = Counter()
    evidence_fields = Counter()

    endpoint_keys = Counter()

    examples = []

    for item in queue:
        subpatterns[
            str(item.get("subpattern", "<NONE>"))
        ] += 1

        statuses[
            str(item.get("original_status", "<NONE>"))
        ] += 1

        symbolic = item.get(
            "symbolic_candidate",
            {}
        )

        if not isinstance(symbolic, dict):
            continue

        for key in symbolic.keys():
            symbolic_keys[key] += 1

        endpoints = symbolic.get(
            "endpoint_validations"
        )

        if isinstance(endpoints, list):
            endpoint_validation_count += 1
            endpoint_validation_lengths[
                len(endpoints)
            ] += 1

            for ep in endpoints:
                if isinstance(ep, dict):
                    for key in ep.keys():
                        endpoint_keys[key] += 1

        for key in (
            "middle_type_missing",
            "missing_type",
            "expected_intermediate_type",
            "expected_entity_type",
            "missing_entity_type",
        ):
            if symbolic.get(key) not in (None, "", [], {}):
                b2_missing_type_fields[key] += 1

        for key in (
            "evidence_terms",
            "candidate_evidence",
            "selected_evidence",
            "evidence",
            "proof",
            "preuve",
        ):
            if symbolic.get(key) not in (None, "", [], {}):
                evidence_fields[key] += 1

        if len(examples) < 3:
            examples.append({
                "candidate_id":
                    item.get("candidate_id"),

                "document":
                    item.get("document"),

                "subpattern":
                    item.get("subpattern"),

                "original_status":
                    item.get("original_status"),

                "symbolic_keys":
                    sorted(symbolic.keys()),

                "endpoint_validations":
                    endpoints,

                "selected_fields": {
                    key: symbolic.get(key)
                    for key in (
                        "middle_type_missing",
                        "missing_type",
                        "expected_intermediate_type",
                        "expected_entity_type",
                        "missing_entity_type",
                        "evidence_terms",
                        "candidate_evidence",
                        "selected_evidence",
                    )
                    if key in symbolic
                },
            })

    print("=" * 96)
    print("TRACE / SGCE - DIAGNOSTIC AGENT B QUEUE")
    print("=" * 96)

    print()
    print(f"Cas totaux : {len(queue)}")

    print()
    print("SUBPATTERNS")
    print("-" * 96)
    for key, count in subpatterns.most_common():
        print(f"{key:<40}: {count}")

    print()
    print("STATUTS ORIGINAUX")
    print("-" * 96)
    for key, count in statuses.most_common():
        print(f"{key:<40}: {count}")

    print()
    print("CLES SYMBOLIC_CANDIDATE LES PLUS FREQUENTES")
    print("-" * 96)
    for key, count in symbolic_keys.most_common(30):
        print(f"{key:<45}: {count}")

    print()
    print("ENDPOINT_VALIDATIONS")
    print("-" * 96)
    print(
        f"Candidats avec endpoint_validations : "
        f"{endpoint_validation_count}"
    )

    print(
        f"Tailles endpoint_validations        : "
        f"{dict(endpoint_validation_lengths)}"
    )

    print()
    print("CLES INTERNES DES ENDPOINTS")
    print("-" * 96)

    if endpoint_keys:
        for key, count in endpoint_keys.most_common():
            print(f"{key:<45}: {count}")
    else:
        print("Aucune.")

    print()
    print("CHAMPS B2 PRESENTS")
    print("-" * 96)

    if b2_missing_type_fields:
        for key, count in b2_missing_type_fields.most_common():
            print(f"{key:<45}: {count}")
    else:
        print("Aucun.")

    print()
    print("CHAMPS DE PREUVE PRESENTS")
    print("-" * 96)

    if evidence_fields:
        for key, count in evidence_fields.most_common():
            print(f"{key:<45}: {count}")
    else:
        print("Aucun.")

    print()
    print("EXEMPLES COMPACTS")
    print("-" * 96)

    for i, ex in enumerate(examples, start=1):
        print()
        print(f"EXEMPLE {i}")
        print(json.dumps(
            ex,
            ensure_ascii=False,
            indent=2,
        ))

    print()
    print("Aucune donnée clinique n'a été modifiée.")


if __name__ == "__main__":
    main()
