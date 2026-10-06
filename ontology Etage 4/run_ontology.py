# -*- coding: utf-8 -*-
"""
TRACE — ETAGE 4 / ONTOLOGY VALIDATION — RUNNER GLOBAL

Ordre:
1. Entity Validation
2. Relation Validation
3. Duplicate Relations
4. Duplicate Entities

Patient Canonicalization n'est PAS incluse dans l'Etage 4.
Elle est reportee a l'etape de KG Normalization & Canonicalization.

Placer ce fichier directement dans:
Reduction_hallucinations\ontology Etage 4\
"""

from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable

STEPS = [
    (
        "ENTITY VALIDATION",
        ROOT / "entity_validation" / "run_entity_validation.py",
    ),
    (
        "RELATION VALIDATION",
        ROOT / "relation_validation" / "run_relation_validation.py",
    ),
    (
        "DUPLICATE RELATIONS + DUPLICATE ENTITIES",
        ROOT / "ontology_duplicates" / "run_duplicates.py",
    ),
]

FINAL_DIR = (
    ROOT
    / "ontology_duplicates"
    / "duplicate_entities"
    / "duplicate_entity_safe_merged"
)


def clinical_json_files(folder: Path):
    """Retourne uniquement les JSON cliniques, en excluant les rapports."""
    if not folder.exists():
        return []

    excluded_suffixes = (
        "_report.json",
        "_summary.json",
        "_decisions.json",
        "_validated.json",
        "_candidates.json",
    )

    return [
        p
        for p in folder.glob("*.json")
        if not p.name.endswith(excluded_suffixes)
    ]


def run_step(label: str, script: Path, index: int, total: int):
    print("\n" + "=" * 110)
    print(f"[{index}/{total}] {label}")
    print("=" * 110)
    print(f"Script : {script}")

    if not script.exists():
        print(f"\n[ECHEC] Script introuvable : {script}")
        raise SystemExit(2)

    result = subprocess.run(
        [PYTHON, str(script)],
        cwd=str(script.parent),
        check=False,
    )

    if result.returncode != 0:
        print("\n" + "!" * 110)
        print(f"[STOP] {label} a echoue — code {result.returncode}")
        print("Les etapes suivantes ne seront pas executees.")
        print("!" * 110)
        raise SystemExit(result.returncode)

    print(f"\n[OK] {label}")


def main():
    print("=" * 110)
    print("TRACE — ETAGE 4 / ONTOLOGY VALIDATION — RUNNER GLOBAL")
    print("=" * 110)
    print(f"Dossier Etage 4 : {ROOT}")
    print(f"Python           : {PYTHON}")
    print("\nPipeline:")
    print("  1. Entity Validation")
    print("  2. Relation Validation")
    print("  3. Duplicate Relations")
    print("  4. Duplicate Entities")
    print("\nPatient Canonicalization : NON incluse dans l'Etage 4")

    start = time.perf_counter()

    for i, (label, script) in enumerate(STEPS, 1):
        run_step(label, script, i, len(STEPS))

    if not FINAL_DIR.exists():
        print("\n[ECHEC] La sortie finale attendue n'existe pas :")
        print(FINAL_DIR)
        raise SystemExit(3)

    docs = clinical_json_files(FINAL_DIR)

    print("\n" + "=" * 110)
    print("TRACE — ETAGE 4 / ONTOLOGY VALIDATION ")
    print("=" * 110)
    print(f"Documents cliniques detectes : {len(docs)}")
    print(f"Sortie officielle            : {FINAL_DIR}")
    print(f"Duree totale                 : {time.perf_counter() - start:.2f} s")
    print("=" * 110)


if __name__ == "__main__":
    main()
