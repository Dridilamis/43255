# -*- coding: utf-8 -*-
"""Runner global SGCE Pattern B : B1 -> B2 -> post-validation globale."""
import subprocess
import sys
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent

PIPELINE = [
    ("PatternB1", HERE / "PatternB1" / "run_pattern_b1_all.py"),
    ("PatternB2", HERE / "PatternB2" / "run_pattern_b2_all.py"),
]

def run_part(name, script):
    if not script.exists():
        raise FileNotFoundError(f"Runner introuvable : {script}")
    print("\n" + "=" * 100)
    print(f"RUNNING : {name}")
    print("=" * 100)
    start = time.time()
    r = subprocess.run([sys.executable, str(script)], cwd=str(script.parent))
    if r.returncode != 0:
        raise RuntimeError(f"Échec de {name} (code={r.returncode})")
    print(f"[OK] {name} — {time.time()-start:.2f} sec")

def main():
    print("=" * 100)
    print("TRACE / SGCE - PATTERN B COMPLET")
    print("=" * 100)
    for name, script in PIPELINE:
        run_part(name, script)
    print("\n" + "=" * 100)
    print("PATTERN B TERMINÉ AVEC SUCCÈS")
    print("=" * 100)
    print("Sortie finale :", HERE / "PatternB2" / "corrected")
    print("Audit global  :", HERE / "post_validation")

if __name__ == "__main__":
    main()
