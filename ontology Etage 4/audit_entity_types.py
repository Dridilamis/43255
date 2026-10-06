# -*- coding: utf-8 -*-
"""
audit_entity_types.py

Audit des types d'entitÃ©s prÃ©sents dans les JSON Mistral post-traitÃ©s.
Objectif : interprÃ©ter correctement les rÃ©sultats A2-A6 du Pattern A.

Aucune modification des JSON.
"""

import json
from collections import Counter, defaultdict
from pathlib import Path

BASE_DIR = Path(
    r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM"
    r"\Reduction_hallucinations"
)

INPUT_DIR = BASE_DIR / "SortieJson_Postprocessing"
OUTPUT_FILE = BASE_DIR / "entity_types_audit.json"

IMPORTANT_TYPES = [
    "TRAITEMENT",
    "POSOLOGIE",
    "COMORBIDITE_ANTECEDENT",
    "CONTEXTE_ACQUISITION",
    "IMAGERIE_PROCEDURE",
    "FOYER_INFECTIEUX",
    "DEFAILLANCE_ORGANE",
    "DONNEE_PATIENT",
    "SYMPTOME",
]

def get_entities(doc):
    """PrivilÃ©gie global_entities pour Ã©viter de compter deux fois."""
    if isinstance(doc.get("global_entities"), list):
        return doc["global_entities"]

    entities = []
    for page in doc.get("pages", []) or []:
        entities.extend(page.get("entities", []) or [])
    return entities

def get_type(entity):
    return (
        entity.get("categorie")
        or entity.get("type")
        or "TYPE_INCONNU"
    )

def main():
    files = sorted(INPUT_DIR.glob("*.json"))

    global_counts = Counter()
    docs_per_type = defaultdict(set)
    per_document = {}
    errors = []

    print("=" * 76)
    print("AUDIT DES TYPES D'ENTITÃ‰S - JSON MISTRAL")
    print("=" * 76)
    print(f"Dossier : {INPUT_DIR}")
    print(f"Documents trouvÃ©s : {len(files)}")
    print()

    for path in files:
        try:
            with path.open("r", encoding="utf-8") as f:
                doc = json.load(f)

            entities = get_entities(doc)
            counts = Counter(get_type(e) for e in entities)

            global_counts.update(counts)

            for entity_type, count in counts.items():
                if count > 0:
                    docs_per_type[entity_type].add(path.name)

            per_document[path.name] = {
                "total_entities": len(entities),
                "types": dict(sorted(counts.items()))
            }

        except Exception as exc:
            errors.append({
                "document": path.name,
                "error": str(exc)
            })

    print("TOUS LES TYPES")
    print("-" * 76)

    for entity_type, count in global_counts.most_common():
        n_docs = len(docs_per_type[entity_type])
        print(
            f"{entity_type:35s} "
            f"{count:6d} entitÃ©(s) | "
            f"{n_docs:2d}/{len(files)} document(s)"
        )

    print()
    print("=" * 76)
    print("TYPES IMPORTANTS POUR PATTERN A")
    print("=" * 76)

    audit_pattern_a = {}

    for entity_type in IMPORTANT_TYPES:
        count = global_counts.get(entity_type, 0)
        n_docs = len(docs_per_type.get(entity_type, set()))

        audit_pattern_a[entity_type] = {
            "total_entities": count,
            "documents_containing_type": n_docs,
            "documents_total": len(files),
        }

        state = "PRÃ‰SENT" if count else "ABSENT"
        print(
            f"{entity_type:35s}: "
            f"{count:5d} | docs={n_docs:2d}/{len(files)} | {state}"
        )

    # InterprÃ©tation automatique des possibilitÃ©s de test A2-A6.
    source_requirements = {
        "A2_COMORBIDITE_CONTEXTE": "COMORBIDITE_ANTECEDENT",
        "A3_IMAGERIE_FOYER": "IMAGERIE_PROCEDURE",
        "A4_IMAGERIE_DEFAILLANCE": "IMAGERIE_PROCEDURE",
        "A5_IMAGERIE_COMORBIDITE": "IMAGERIE_PROCEDURE",
        "A6_PATIENT_SYMPTOME": "DONNEE_PATIENT",
    }

    print()
    print("=" * 76)
    print("COUVERTURE DES SOUS-CAS A2-A6")
    print("=" * 76)

    coverage = {}

    for subcase, source_type in source_requirements.items():
        count = global_counts.get(source_type, 0)
        docs = len(docs_per_type.get(source_type, set()))

        if count == 0:
            interpretation = (
                "NON TESTABLE SUR CE CORPUS : aucune entitÃ© source de ce type."
            )
        else:
            interpretation = (
                "TESTABLE : des entitÃ©s sources existent. "
                "Un rÃ©sultat de 0 candidat doit Ãªtre interprÃ©tÃ© comme "
                "aucun composite dÃ©tectÃ© par la rÃ¨gle actuelle, "
                "et non comme absence absolue du phÃ©nomÃ¨ne."
            )

        coverage[subcase] = {
            "required_source_type": source_type,
            "source_entities": count,
            "documents_with_source": docs,
            "testable": count > 0,
            "interpretation": interpretation,
        }

        print(f"{subcase}")
        print(f"  source : {source_type}")
        print(f"  nombre : {count} dans {docs} document(s)")
        print(f"  -> {interpretation}")
        print()

    report = {
        "documents_analysed": len(files),
        "documents_with_errors": len(errors),
        "total_entities": sum(global_counts.values()),
        "global_type_counts": dict(global_counts.most_common()),
        "pattern_a_important_types": audit_pattern_a,
        "pattern_a_subcase_coverage": coverage,
        "documents_per_type": {
            k: sorted(v)
            for k, v in docs_per_type.items()
        },
        "per_document": per_document,
        "errors": errors,
    }

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("=" * 76)
    print("RÃ‰SUMÃ‰")
    print("=" * 76)
    print(f"Documents analysÃ©s : {len(files)}")
    print(f"EntitÃ©s totales     : {sum(global_counts.values())}")
    print(f"Erreurs             : {len(errors)}")
    print(f"Rapport             : {OUTPUT_FILE}")
    print()
    print("Aucun JSON Mistral n'a Ã©tÃ© modifiÃ©.")

if __name__ == "__main__":
    main()

