# -*- coding: utf-8 -*-
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable

STEPS = [
    ("AUDIT APRES ENTITY VALIDATION",
     ROOT / "audit_after_entity_validation" / "final_ontology_audit.py"),

    ("RELATION RESIDUAL — BUILDER",
     ROOT / "ontology_relation_residual_builder.py"),

    ("RELATION RESIDUAL — CLASSIFIER",
     ROOT / "ontology_relation_residual_classifier.py"),

    ("RELATION RESIDUAL — VALIDATOR",
     ROOT / "ontology_relation_residual_validator.py"),

    ("RELATION — DEEP REVIEWER",
     ROOT / "ontology_relation_deep_reviewer.py"),

    ("RELATION — FINAL VALIDATOR",
     ROOT / "ontology_relation_final_validator.py"),

    ("RELATION — SAFE REMOVE CORRECTOR",
     ROOT / "ontology_relation_safe_corrector.py"),

    ("AUDIT APRES SAFE REMOVE",
     ROOT / "audit_after_safe_remove" / "final_ontology_audit.py"),

    ("RELATION REVIEW — RESOLVER",
     ROOT / "ontology_relation_review_resolver.py"),

    ("RELATION REVIEW — VALIDATOR",
     ROOT / "ontology_relation_review_validator.py"),

    ("RELATION REVIEW — SAFE CORRECTOR",
     ROOT / "ontology_relation_review_safe_corrector.py"),
]

def run_step(label, script, index, total):
    print("\n" + "=" * 110)
    print(f"[{index}/{total}] {label}")
    print(f"Script : {script.name}")
    print("=" * 110)

    if not script.exists():
        raise FileNotFoundError(f"Script introuvable : {script}")

    result = subprocess.run(
        [PYTHON, str(script)],
        cwd=str(script.parent),
        check=False,
    )

    if result.returncode != 0:
        print(f"\n[ECHEC] {label} — code {result.returncode}")
        raise SystemExit(result.returncode)

    print(f"\n[OK] {label}")

def main():
    print("=" * 110)
    print("TRACE — ETAGE 4 / RELATION VALIDATION")
    print("=" * 110)
    print(f"Dossier : {ROOT}")
    print(f"Python  : {PYTHON}")

    start = time.perf_counter()

    for i, (label, script) in enumerate(STEPS, 1):
        run_step(label, script, i, len(STEPS))

    final_dir = ROOT / "relation_validation_safe_corrected"

    if not final_dir.exists():
        raise FileNotFoundError(
            f"La sortie finale attendue n'existe pas : {final_dir}"
        )

    clinical_json = [
        p for p in final_dir.glob("*.json")
        if not p.name.endswith("_report.json")
    ]

    print("\n" + "=" * 110)
    print("RELATION VALIDATION TERMINEE")
    print("=" * 110)
    print(f"Documents cliniques : {len(clinical_json)}")
    print(f"Sortie officielle   : {final_dir}")
    print(f"Duree totale        : {time.perf_counter() - start:.2f} s")

if __name__ == "__main__":
    main()
