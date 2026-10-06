import json
from pathlib import Path

DOSSIER = Path(
    r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM\Reduction_hallucinations"
    r"\MultiAgent\negation_audit\negation_safe_corrected_repaired"
)

for fichier in DOSSIER.glob("*.json"):
    if "report" in fichier.name.lower():
        continue

    with open(fichier, "r", encoding="utf-8") as f:
        data = json.load(f)

    relations = data.get("global_relations", [])

    if relations:
        print("=" * 100)
        print("FICHIER :", fichier.name)
        print("NOMBRE :", len(relations))
        print("=" * 100)

        for i, relation in enumerate(relations[:5], 1):
            print(f"\n--- RELATION {i} ---")
            print(json.dumps(relation, ensure_ascii=False, indent=2))

        break
