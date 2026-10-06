# -*- coding: utf-8 -*-
"""
run_all_agents.py
=================

Run all generic TRACE/SGCE agents.

The script works even when some queues are empty.

Order:
1) Pattern A
2) Pattern B
3) Pattern C
4) Patient / Reference

No clinical JSON is modified.
"""

import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent

SCRIPTS = [
    "agent_pattern_a.py",
    "agent_pattern_b.py",
    "agent_pattern_c.py",
    "agent_patient_reference.py",
]


def main():
    print("=" * 84)
    print("TRACE / SGCE - RUN ALL GENERIC AGENTS")
    print("=" * 84)

    failures = []

    for script in SCRIPTS:
        path = HERE / script

        if not path.exists():
            print(f"[SKIP] {script} introuvable")
            continue

        print()
        print("-" * 84)
        print(f"RUN {script}")
        print("-" * 84)

        result = subprocess.run(
            [sys.executable, str(path)],
            cwd=str(HERE),
        )

        if result.returncode != 0:
            failures.append(script)

    print()
    print("=" * 84)

    if failures:
        print("FIN AVEC ERREURS")
        for name in failures:
            print(f"  - {name}")
    else:
        print("FIN OK")

    print("=" * 84)


if __name__ == "__main__":
    main()
