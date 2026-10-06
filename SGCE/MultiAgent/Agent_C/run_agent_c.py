# -*- coding: utf-8 -*-
import subprocess, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
STEPS=['agent_pattern_c.py']
def main():
    print("="*100); print("Agent_C"); print("="*100)
    for name in STEPS:
        p=HERE/name
        if not p.exists(): raise FileNotFoundError(p)
        print("\nRUN :",name)
        r=subprocess.run([sys.executable,str(p)],cwd=str(HERE))
        if r.returncode: raise SystemExit(f"Echec {name} (code={r.returncode})")
    print("\nAgent_C : FIN OK")
if __name__=="__main__": main()
