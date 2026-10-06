# -*- coding: utf-8 -*-
"""
TRACE — Etage 3 : Document / Factual Grounding
Runner global :
    1. Root Cause
    2. Semantic / Factual

Architecture attendue :

document_grounding Etage 3/
├── run_document_grounding.py
├── root_cause/
│   └── run_root_cause.py
└── semantic_factual/
    └── run_semantic_factual.py
"""

from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable

ROOT_CAUSE_RUNNER = ROOT / "root_cause" / "run_root_cause.py"
SEMANTIC_FACTUAL_RUNNER = ROOT / "semantic_factual" / "run_semantic_factual.py"

ROOT_CAUSE_OUTPUT = (
    ROOT / "root_cause" / "root_cause_entity_safe_corrected"
)

SEMANTIC_FACTUAL_OUTPUT = (
    ROOT / "semantic_factual" / "semantic_factual_safe_corrected"
)

STAGES = [
    (
        "ROOT CAUSE",
        ROOT_CAUSE_RUNNER,
        ROOT_CAUSE_OUTPUT,
    ),
    (
        "SEMANTIC / FACTUAL",
        SEMANTIC_FACTUAL_RUNNER,
        SEMANTIC_FACTUAL_OUTPUT,
    ),
]


def separator():
    print("=" * 108)


def count_clinical_json(folder: Path) -> int:
    if not folder.exists():
        return 0

    return len([
        p for p in folder.glob("*.json")
        if not p.name.endswith("_report.json")
    ])


def run_stage(index, total, name, runner, expected_output):
    print()
    separator()
    print(f"[{index}/{total}] {name}")
    separator()
    print(f"Runner : {runner}")

    if not runner.exists():
        print(f"\nERREUR : runner introuvable : {runner}")
        raise SystemExit(2)

    start = time.perf_counter()

    result = subprocess.run(
        [PYTHON, str(runner)],
        cwd=str(runner.parent),
        check=False,
    )

    elapsed = time.perf_counter() - start

    if result.returncode != 0:
        print()
        separator()
        print(f"ETAGE 3 ARRETE — ECHEC : {name}")
        print(f"Code retour : {result.returncode}")
        print(f"Durée       : {elapsed:.2f} s")
        separator()
        raise SystemExit(result.returncode)

    if not expected_output.exists():
        print()
        separator()
        print(f"ETAGE 3 ARRETE — SORTIE ABSENTE : {name}")
        print(f"Sortie attendue : {expected_output}")
        separator()
        raise SystemExit(3)

    n_json = count_clinical_json(expected_output)

    print()
    print(f"[OK] {name}")
    print(f"Sortie : {expected_output}")
    print(f"JSON cliniques : {n_json}")
    print(f"Durée : {elapsed:.2f} s")


def main():
    separator()
    print("TRACE — ETAGE 3 / DOCUMENT & FACTUAL GROUNDING")
    separator()
    print(f"Racine : {ROOT}")
    print(f"Python : {PYTHON}")
    print()
    print("Pipeline : ROOT CAUSE -> SEMANTIC / FACTUAL")

    # Vérification avant lancement pour éviter un pipeline partiel
    missing = [
        runner
        for _, runner, _ in STAGES
        if not runner.exists()
    ]

    if missing:
        print("\nERREUR — runner(s) manquant(s) :")
        for runner in missing:
            print(f"  - {runner}")
        raise SystemExit(2)

    global_start = time.perf_counter()

    for index, (name, runner, output) in enumerate(
        STAGES,
        start=1,
    ):
        run_stage(
            index,
            len(STAGES),
            name,
            runner,
            output,
        )

    elapsed = time.perf_counter() - global_start

    print()
    separator()
    print("TRACE — ETAGE 3 TERMINE AVEC SUCCES")
    separator()
    print("Root Cause       : OK")
    print("Semantic/Factual : OK")
    print()
    print(f"Sortie finale : {SEMANTIC_FACTUAL_OUTPUT}")
    print(
        "JSON cliniques : "
        f"{count_clinical_json(SEMANTIC_FACTUAL_OUTPUT)}"
    )
    print(f"Durée totale  : {elapsed:.2f} s")
    separator()


if __name__ == "__main__":
    main()
