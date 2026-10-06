# -*- coding: utf-8 -*-
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent

STEPS = [
    ROOT / "duplicate_relation_candidate_builder.py",
    ROOT / "duplicate_relation_safe_cleaner.py",
    ROOT / "duplicate_relation_post_validator.py",
]

def main():
    start = time.perf_counter()

    print("=" * 108)
    print("TRACE — ETAGE 4 / DUPLICATE RELATIONS")
    print("=" * 108)

    for i, script in enumerate(STEPS, 1):
        print("\n" + "=" * 108)
        print(f"[{i}/{len(STEPS)}] {script.name}")
        print("=" * 108)

        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(ROOT),
            check=False,
        )

        if result.returncode != 0:
            raise SystemExit(result.returncode)

    final_dir = ROOT / "duplicate_relation_cleaned"

    print("\n" + "=" * 108)
    print("DUPLICATE RELATIONS TERMINE")
    print("=" * 108)
    print(f"Sortie officielle : {final_dir}")
    print(f"Duree totale      : {time.perf_counter() - start:.2f} s")

if __name__ == "__main__":
    main()
