# -*- coding: utf-8 -*-
"""Resume des relations rejetees par la validation de l'extraction (aucune donnee patient affichee).

    python extraction_mistral\\analyser_rejets_extraction.py extraction_mistral\\extraction_v2_0
"""
import json
import sys
from collections import Counter
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

dossier = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "extraction_v2_0")
raisons, motifs, gardees = Counter(), Counter(), Counter()
for f in sorted(dossier.glob("*_trace_*.json")):
    data = json.loads(f.read_text(encoding="utf-8"))
    for p in data.get("pages", []):
        for r in p.get("relations", []):
            gardees[r["type_relation"]] += 1
        for r in p.get("relations_rejetees", []):
            raison = "sens_inverse" if r.get("sens_inverse") else r["raison"]
            raisons[raison] += 1
            motifs[(r["type_relation"], " -> ".join(r.get("types_obtenus", [])), " -> ".join(r.get("signature", [])))] += 1
print(f"Relations gardees : {sum(gardees.values())} | rejetees : {sum(raisons.values())}")
print("Raisons :", dict(raisons))
print("\nRejets les plus frequents (relation | types obtenus | signature attendue) :")
for (t, obt, sig), n in motifs.most_common(25):
    print(f"  {n:4}  {t} | {obt} | {sig}")
