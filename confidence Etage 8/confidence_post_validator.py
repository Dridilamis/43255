# -*- coding: utf-8 -*-
"""
TRACE — ETAGE 8 V2.1 — POST VALIDATION STRICTE

Garanties:
- mêmes dossiers cliniques avant/après;
- mêmes nombres d'entités et relations;
- aucune modification clinique hors trace_confidence;
- 100 % des occurrences physiques ont trace_confidence;
- niveaux autorisés: HIGH / MEDIUM / LOW / REVIEW.
"""

from pathlib import Path
import json
from collections import Counter

HERE = Path(__file__).resolve().parent
BASE = HERE.parent

BEFORE = BASE / "negation Etage 7" / "negation_safe_corrected"
AFTER = HERE / "confidence_assessed_safe"

REPORT_DIR = HERE / "post_validation"
REPORT = REPORT_DIR / "confidence_post_validation_report.json"

ALLOWED = {"HIGH", "MEDIUM", "LOW", "REVIEW"}


def is_clinical(d):
    return (
        isinstance(d, dict)
        and isinstance(d.get("source_file"), str)
        and isinstance(d.get("global_entities"), list)
        and isinstance(d.get("global_relations"), list)
    )


def load_clinical(folder):
    out = {}
    for p in folder.glob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if is_clinical(d):
            out[p.name] = d
    return out


def strip_trace_confidence(x):
    if isinstance(x, dict):
        return {
            k: strip_trace_confidence(v)
            for k, v in x.items()
            if k != "trace_confidence"
        }
    if isinstance(x, list):
        return [strip_trace_confidence(v) for v in x]
    return x


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    before = load_clinical(BEFORE)
    after = load_clinical(AFTER)

    s = Counter()
    details = {
        "unexpected_clinical_changes": [],
        "missing_annotations": [],
        "invalid_annotations": [],
    }

    s["documents_before"] = len(before)
    s["documents_after"] = len(after)
    s["missing_after"] = len(set(before) - set(after))
    s["extra_after"] = len(set(after) - set(before))

    for name in sorted(set(before) & set(after)):
        bd = before[name]
        ad = after[name]

        be = bd["global_entities"]
        ae = ad["global_entities"]
        br = bd["global_relations"]
        ar = ad["global_relations"]

        s["entities_before"] += len(be)
        s["entities_after"] += len(ae)
        s["relations_before"] += len(br)
        s["relations_after"] += len(ar)

        # Toute différence autre que trace_confidence est interdite.
        if strip_trace_confidence(bd) != strip_trace_confidence(ad):
            s["unexpected_clinical_changes"] += 1
            details["unexpected_clinical_changes"].append(name)

        for kind, objects in (
            ("ENTITY", ae),
            ("RELATION", ar),
        ):
            for physical_index, obj in enumerate(objects):
                s["clinical_objects_after"] += 1
                tc = obj.get("trace_confidence")

                if tc is None:
                    s["missing_confidence_annotations"] += 1
                    s[f"{kind}_missing_confidence"] += 1
                    oid = (
                        obj.get("identifiant_entite")
                        if kind == "ENTITY"
                        else obj.get("identifiant_relation")
                    )
                    details["missing_annotations"].append({
                        "document": name,
                        "kind": kind,
                        "id": oid,
                        "physical_index": physical_index,
                    })
                    continue

                level = tc.get("level")
                if level not in ALLOWED:
                    s["invalid_confidence_annotations"] += 1
                    details["invalid_annotations"].append({
                        "document": name,
                        "kind": kind,
                        "physical_index": physical_index,
                        "level": level,
                    })
                    continue

                s["valid_confidence_annotations"] += 1
                s[f"{kind}_valid_confidence"] += 1
                s[level] += 1

    expected = s["entities_after"] + s["relations_after"]
    s["expected_confidence_annotations"] = expected

    fail = (
        s["missing_after"] != 0
        or s["extra_after"] != 0
        or s["entities_before"] != s["entities_after"]
        or s["relations_before"] != s["relations_after"]
        or s["unexpected_clinical_changes"] != 0
        or s["missing_confidence_annotations"] != 0
        or s["invalid_confidence_annotations"] != 0
        or s["valid_confidence_annotations"] != expected
    )

    status = "FAIL" if fail else "PASS"

    REPORT.write_text(
        json.dumps(
            {"status": status, "stats": dict(s), "details": details},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=" * 110)
    print("TRACE / ETAGE 8 V2.1 - POST VALIDATION")
    print("=" * 110)

    ordered = [
        "documents_before",
        "documents_after",
        "missing_after",
        "extra_after",
        "entities_before",
        "entities_after",
        "relations_before",
        "relations_after",
        "clinical_objects_after",
        "expected_confidence_annotations",
        "valid_confidence_annotations",
        "ENTITY_valid_confidence",
        "RELATION_valid_confidence",
        "HIGH",
        "MEDIUM",
        "LOW",
        "REVIEW",
        "missing_confidence_annotations",
        "invalid_confidence_annotations",
        "unexpected_clinical_changes",
    ]

    for k in ordered:
        print(f"{k:38}: {s[k]}")

    print("STATUT FINAL :", status)
    print("Rapport      :", REPORT)

    if status != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
