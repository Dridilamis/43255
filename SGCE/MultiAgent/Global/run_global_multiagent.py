# -*- coding: utf-8 -*-
import subprocess, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
STEPS=[
 'validate_missing_agent_decisions.py',
 'multiagent_adjudicator.py',
 'inject_specialized_accepts.py',
 'multiagent_action_resolver.py',
 'multiagent_provisional_corrector.py',
 'multiagent_action_validator.py',
 'multiagent_corrector.py',
 'multiagent_post_validator.py'
]
def main():
    print("="*100); print("Global - POST AGENTS"); print("="*100)
    for name in STEPS:
        p=HERE/name
        print("\nRUN :",name)
        r=subprocess.run([sys.executable,str(p)],cwd=str(HERE))
        if r.returncode: raise SystemExit(f"Echec {name} (code={r.returncode})")
    print("\nGlobal : FIN OK")
if __name__=="__main__": main()
