# -*- coding: utf-8 -*-
from pathlib import Path
import subprocess,sys,os
HERE=Path(__file__).resolve().parent
SCRIPTS=[
"00_diagnostic_etage9.py",
"00_entity_candidate_builder.py",
"00_entity_evidence_validator.py",
"00_safe_entity_recovery.py",
"00b_lexical_entity_candidate_builder.py",
"00b_lexical_entity_evidence_validator.py",
"00b_safe_lexical_entity_recovery.py",
"01_missing_link_candidate_builder.py",
"02_ontology_relation_filter.py",
"03_document_evidence_validator.py",
"04_multiagent_relation_adjudicator.py",
"05_safe_relation_recovery.py",
"06_relation_recovery_post_validator.py",
]
env=os.environ.copy(); env["PYTHONUTF8"]="1"; env["PYTHONIOENCODING"]="utf-8"
print("="*110); print("TRACE — ETAGE 9 V3 / ENTITY + RELATION RECOVERY"); print("="*110)
for i,s in enumerate(SCRIPTS,1):
    print(f"\n[{i}/{len(SCRIPTS)}] {s}\n"+"-"*110)
    p=subprocess.run([sys.executable,"-X","utf8",str(HERE/s)],cwd=str(HERE),env=env)
    if p.returncode: raise SystemExit(f"ECHEC : {s}")
print("\n"+"="*110); print("ETAGE 9 V3 TERMINE — PASS"); print("="*110)
