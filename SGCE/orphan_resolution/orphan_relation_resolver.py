# -*- coding: utf-8 -*-
"""
orphan_relation_resolver.py
===========================

Résout les relations orphelines de façon conservatrice.

Actions possibles :
- RELINK_EXISTING_ENTITY
- REMOVE_INVALID_RELATION
- REVIEW

Règles :
1) Relink uniquement si UNE entité existante du document :
   - a le type attendu par la signature TRACE
   - correspond textuellement à l'ID/endpoint orphelin de manière exploitable
     ou est l'unique candidat compatible de la page/document
2) REMOVE seulement si aucune entité compatible n'existe
   ET si l'autre endpoint est valide
3) sinon REVIEW

Aucune donnée clinique n'est modifiée.
"""

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

ORPHAN_DIR = Path(__file__).resolve().parent
SGCE_DIR = ORPHAN_DIR.parent
BASE_DIR = SGCE_DIR.parent

INPUT_FILE = (
    ORPHAN_DIR
    / "queues"
    / "orphan_relation_candidates.json"
)

GUIDELINE_CANDIDATES = [
    BASE_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
    BASE_DIR.parent / "Guideline_TRACE_Sepsis_v1.6.json",
    Path.cwd() / "Guideline_TRACE_Sepsis_v1.6.json",
    ORPHAN_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
]

OUTPUT_FILE = (
    ORPHAN_DIR
    / "outputs"
    / "orphan_relation_decisions.json"
)

def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_guideline():
    for p in GUIDELINE_CANDIDATES:
        if p.exists():
            return p

    raise FileNotFoundError(
        "Guideline TRACE introuvable."
    )


def normalize(text):
    text = unicodedata.normalize(
        "NFKD",
        str(text or "").lower(),
    )

    text = "".join(
        c
        for c in text
        if not unicodedata.combining(c)
    )

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


def load_signatures():
    data = load_json(
        resolve_guideline()
    )

    root = data.get(
        "ontologie_sepsis_graph",
        data,
    )

    locked = root.get(
        "signatures_relations_verrouillees_v1_5",
        {},
    )

    result = {}

    for name, spec in (
        locked.items()
        if isinstance(locked, dict)
        else []
    ):
        if (
            isinstance(spec, dict)
            and spec.get("domaine")
            and spec.get("image")
        ):
            result[name] = {
                "domaine": spec["domaine"],
                "image": spec["image"],
            }

    return result


def page_of_id(value):
    m = re.match(
        r"P(\d+)_E\d+",
        str(value or ""),
    )

    return int(m.group(1)) if m else None


def compatible_candidates(
    catalog,
    expected_type,
    missing_id,
):
    page = page_of_id(
        missing_id
    )

    candidates = []

    for e in catalog:
        if e.get("entity_type") != expected_type:
            continue

        eid = str(
            e.get("entity_id")
            or ""
        )

        if page is not None:
            if page_of_id(eid) != page:
                continue

        candidates.append(e)

    return candidates


def decide(item, signatures):
    rtype = item.get(
        "relation_type"
    )

    sig = signatures.get(
        rtype
    )

    if not sig:
        return {
            "decision":
                "REVIEW",

            "action":
                "NONE",

            "reason":
                "Relation absente des signatures TRACE.",

            "parameters":
                {},
        }

    source_missing = item.get(
        "source_missing"
    ) is True

    target_missing = item.get(
        "target_missing"
    ) is True

    # Both missing -> too risky
    if source_missing and target_missing:
        return {
            "decision":
                "REVIEW",

            "action":
                "NONE",

            "reason":
                "Source et cible toutes deux absentes.",

            "parameters":
                {},
        }

    catalog = item.get(
        "entity_catalog",
        []
    ) or []

    if source_missing:
        expected_type = sig[
            "domaine"
        ]

        candidates = compatible_candidates(
            catalog,
            expected_type,
            item.get(
                "source_id"
            ),
        )

        if len(candidates) == 1:
            return {
                "decision":
                    "CORRECT",

                "action":
                    "RELINK_EXISTING_ENTITY",

                "reason":
                    "Une seule entité source compatible avec la signature TRACE.",

                "parameters": {
                    "relation_id":
                        item.get(
                            "relation_id"
                        ),

                    "endpoint_role":
                        "SOURCE",

                    "old_endpoint":
                        item.get(
                            "source_id"
                        ),

                    "new_entity_id":
                        candidates[
                            0
                        ][
                            "entity_id"
                        ],

                    "expected_type":
                        expected_type,
                },
            }

        if len(candidates) == 0:
            return {
                "decision":
                    "CORRECT",

                "action":
                    "REMOVE_INVALID_RELATION",

                "reason":
                    "Aucune entité source compatible n'existe dans le document.",

                "parameters": {
                    "relation_id":
                        item.get(
                            "relation_id"
                        ),
                },
            }

    if target_missing:
        expected_type = sig[
            "image"
        ]

        candidates = compatible_candidates(
            catalog,
            expected_type,
            item.get(
                "target_id"
            ),
        )

        if len(candidates) == 1:
            return {
                "decision":
                    "CORRECT",

                "action":
                    "RELINK_EXISTING_ENTITY",

                "reason":
                    "Une seule entité cible compatible avec la signature TRACE.",

                "parameters": {
                    "relation_id":
                        item.get(
                            "relation_id"
                        ),

                    "endpoint_role":
                        "TARGET",

                    "old_endpoint":
                        item.get(
                            "target_id"
                        ),

                    "new_entity_id":
                        candidates[
                            0
                        ][
                            "entity_id"
                        ],

                    "expected_type":
                        expected_type,
                },
            }

        if len(candidates) == 0:
            return {
                "decision":
                    "CORRECT",

                "action":
                    "REMOVE_INVALID_RELATION",

                "reason":
                    "Aucune entité cible compatible n'existe dans le document.",

                "parameters": {
                    "relation_id":
                        item.get(
                            "relation_id"
                        ),
                },
            }

    return {
        "decision":
            "REVIEW",

        "action":
            "NONE",

        "reason":
            "Plusieurs entités compatibles possibles.",

        "parameters":
            {},
    }


def main():
    candidates = load_json(
        INPUT_FILE
    )

    signatures = load_signatures()

    decisions = []

    for item in candidates:
        result = decide(
            item,
            signatures,
        )

        decisions.append({
            "candidate_id":
                item.get(
                    "candidate_id"
                ),

            "document":
                item.get(
                    "document"
                ),

            "relation_id":
                item.get(
                    "relation_id"
                ),

            "relation_type":
                item.get(
                    "relation_type"
                ),

            **result,
        })

    dc = Counter(
        x[
            "decision"
        ]
        for x in decisions
    )

    ac = Counter(
        x[
            "action"
        ]
        for x in decisions
    )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_FILE.write_text(
        json.dumps(
            {
                "resolver":
                    "orphan_relation_resolver",

                "signatures_loaded":
                    len(
                        signatures
                    ),

                "decisions":
                    decisions,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=" * 104)
    print("TRACE / SGCE - ORPHAN RELATION RESOLVER")
    print("=" * 104)
    print(f"Cas reçus                             : {len(candidates)}")
    print()
    print("DECISIONS")
    print("-" * 104)

    for k, v in dc.most_common():
        print(f"{k:<48}: {v}")

    print()
    print("ACTIONS PROPOSEES")
    print("-" * 104)

    for k, v in ac.most_common():
        print(f"{k:<48}: {v}")

    print()
    print(f"Sortie                                : {OUTPUT_FILE}")
    print()
    print("Aucune donnée clinique n'a été modifiée.")


if __name__ == "__main__":
    main()
