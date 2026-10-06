# -*- coding: utf-8 -*-
import subprocess, sys
from pathlib import Path

HERE=Path(__file__).resolve().parent

STEPS=[
    ("PREPARATION", HERE/"Global"/"orchestrator.py"),
    ("PREPARATION", HERE/"Global"/"merge_orphan_review_into_b.py"),
    ("PREPARATION", HERE/"Global"/"text_context_builder.py"),
    ("PREPARATION", HERE/"Global"/"build_agent_d_queue.py"),
    ("PREPARATION", HERE/"Global"/"contextualize_remaining_queues.py"),

    ("Agent_A", HERE/"Agent_A"/"run_agent_a.py"),
    ("Agent_B", HERE/"Agent_B"/"run_agent_b.py"),
    ("Agent_C", HERE/"Agent_C"/"run_agent_c.py"),
    ("Agent_Patient_Reference", HERE/"Agent_Patient_Reference"/"run_agent_patient_reference.py"),

    # Queue D is already built and contextualized above: run the decision agent only.
    ("Agent_D", HERE/"Agent_D"/"agent_pattern_d.py"),

    ("GLOBAL", HERE/"Global"/"validate_missing_agent_decisions.py"),
    ("GLOBAL", HERE/"Global"/"multiagent_adjudicator.py"),
    ("GLOBAL", HERE/"Global"/"inject_specialized_accepts.py"),
    ("GLOBAL", HERE/"Global"/"multiagent_action_resolver.py"),
    ("GLOBAL", HERE/"Global"/"multiagent_provisional_corrector.py"),
    ("GLOBAL", HERE/"Global"/"multiagent_action_validator.py"),
    ("GLOBAL", HERE/"Global"/"multiagent_corrector.py"),
    ("GLOBAL", HERE/"Global"/"multiagent_post_validator.py"),
]

def run(label,p):
    print("\n"+"="*108)
    print(f"RUN : {label} / {p.name}")
    print("="*108)
    if not p.exists():
        raise FileNotFoundError(p)
    r=subprocess.run([sys.executable,str(p)],cwd=str(p.parent))
    if r.returncode:
        raise SystemExit(f"Echec {p.name} (code={r.returncode})")

def main():
    print("="*108)
    print("TRACE / SGCE - MULTI-AGENT COMPLET")
    print("="*108)
    print("Baseline clinique : SGCE/orphan_resolution/corrected")
    print("Préparation des queues AVANT exécution des agents.")
    for label,p in STEPS:
        run(label,p)
    print("\n"+"="*108)
    print("MULTI-AGENT TERMINE")
    print("="*108)
    print(f"Sortie : {HERE/'corrected'}")
    print(f"Post-validation : {HERE/'post_validation'}")

if __name__=="__main__":
    main()
