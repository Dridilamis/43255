# -*- coding: utf-8 -*-
import json
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent
MULTIAGENT_DIR = AGENT_DIR.parent
SGCE_DIR = MULTIAGENT_DIR.parent
BASE_DIR = SGCE_DIR.parent
M = MULTIAGENT_DIR
PATTERNS_DIR = SGCE_DIR / "Patterns"
INPUT_CANDIDATES = [
    PATTERNS_DIR / "PatternD" / "validation" / "pattern_d_validation_report.json",
    PATTERNS_DIR / "PatternD" / "validation" / "pattern_d_validation_report.json",
]
OUT = M / "queues" / "agent_d_queue.json"

def load_json(p):
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)

def resolve_input():
    for p in INPUT_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError("Rapport Pattern D validation introuvable.")

def iter_dicts(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from iter_dicts(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from iter_dicts(v)

def status_of(d):
    for k in ("validation_status","status","final_status","decision"):
        v = d.get(k)
        if isinstance(v, str):
            return v.upper().strip()
    return ""

def main():
    src = resolve_input()
    data = load_json(src)
    found = []
    seen = set()

    for d in iter_dicts(data):
        if status_of(d) != "AMBIGUOUS":
            continue

        candidate_id = d.get("candidate_id") or d.get("id") or d.get("candidate")
        document = d.get("document") or d.get("document_name") or d.get("file") or d.get("filename")

        if not candidate_id and not document:
            continue

        key = (str(candidate_id), str(document), json.dumps(d, ensure_ascii=False, sort_keys=True))
        if key in seen:
            continue
        seen.add(key)

        found.append({
            "candidate_id": candidate_id,
            "document": document,
            "pattern": "D",
            "original_status": "AMBIGUOUS",
            "symbolic_candidate": d,
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(found, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 96)
    print("TRACE / SGCE - BUILD AGENT D QUEUE")
    print("=" * 96)
    print(f"Rapport source                    : {src}")
    print(f"Cas AMBIGUOUS routés             : {len(found)}")
    print(f"Sortie                            : {OUT}")
    print("\nAucune donnée clinique n'a été modifiée.")

if __name__ == "__main__":
    main()
