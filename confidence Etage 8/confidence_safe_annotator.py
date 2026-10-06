# -*- coding: utf-8 -*-
"""
TRACE — ETAGE 8 V2.1 — CONFIDENCE SAFE ANNOTATOR

Correction V2.1:
- n'utilise plus un dictionnaire id -> objet clinique pour écrire les annotations;
- annote les occurrences physiques de global_entities/global_relations dans leur ordre;
- associe les décisions par (document, kind, id) sous forme de files FIFO;
- protège les identifiants dupliqués;
- vérifie que chaque occurrence clinique reçoit exactement une trace_confidence;
- ne modifie aucune autre donnée clinique.
"""

from pathlib import Path
import json
import shutil
from collections import Counter, defaultdict, deque

HERE = Path(__file__).resolve().parent
BASE = HERE.parent

INPUT = BASE / "negation Etage 7" / "negation_safe_corrected"
DEC = HERE / "outputs" / "confidence_validated.json"
OUT = HERE / "confidence_assessed_safe"
REPORT = HERE / "outputs" / "confidence_annotation_report.json"


def is_clinical(d):
    return (
        isinstance(d, dict)
        and isinstance(d.get("source_file"), str)
        and isinstance(d.get("global_entities"), list)
        and isinstance(d.get("global_relations"), list)
    )


def object_id(obj, kind):
    if kind == "ENTITY":
        return str(obj.get("identifiant_entite", ""))
    return str(obj.get("identifiant_relation", ""))


def confidence_payload(z):
    return {
        **z["trace_confidence"],
        "document_evidence": z["evidence"]["document"],
        "contextual_evidence": z["evidence"]["context"],
        "ontology_evidence": z["evidence"]["ontology"],
        "previous_validation_evidence": z["evidence"]["previous_validation"],
    }


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)

    validated = json.loads(DEC.read_text(encoding="utf-8"))
    decisions = validated.get("items", [])

    # Une file FIFO par (document, kind, id).
    # Ainsi, si un même identifiant apparaît plusieurs fois physiquement,
    # aucune occurrence n'est écrasée.
    queues = defaultdict(deque)

    for z in decisions:
        key = (
            str(z.get("document", "")),
            str(z.get("kind", "")),
            str(z.get("id", "")),
        )
        queues[key].append(z)

    stats = Counter()
    details = {
        "unmatched_clinical_objects": [],
        "unused_decisions": [],
        "duplicate_ids": [],
    }

    for jp in sorted(INPUT.glob("*.json")):
        try:
            d = json.loads(jp.read_text(encoding="utf-8"))
        except Exception:
            continue

        if not is_clinical(d):
            continue

        stats["clinical_documents"] += 1

        # Diagnostic des IDs dupliqués dans le document.
        for kind, field in (
            ("ENTITY", "global_entities"),
            ("RELATION", "global_relations"),
        ):
            counts = Counter(object_id(obj, kind) for obj in d[field])
            for oid, n in counts.items():
                if n > 1:
                    stats["duplicate_id_groups"] += 1
                    stats["duplicate_id_occurrences"] += n
                    details["duplicate_ids"].append({
                        "document": jp.name,
                        "kind": kind,
                        "id": oid,
                        "occurrences": n,
                    })

        # Annotation OCCURRENCE PAR OCCURRENCE.
        for kind, field in (
            ("ENTITY", "global_entities"),
            ("RELATION", "global_relations"),
        ):
            for physical_index, obj in enumerate(d[field]):
                oid = object_id(obj, kind)
                stats["clinical_objects_total"] += 1
                stats[f"{kind}_total"] += 1

                key = (jp.name, kind, oid)
                q = queues.get(key)

                if not q:
                    stats["unmatched_clinical_objects"] += 1
                    stats[f"{kind}_unmatched"] += 1
                    details["unmatched_clinical_objects"].append({
                        "document": jp.name,
                        "kind": kind,
                        "id": oid,
                        "physical_index": physical_index,
                    })
                    continue

                z = q.popleft()
                obj["trace_confidence"] = confidence_payload(z)

                stats["annotations"] += 1
                stats[f"{kind}_annotations"] += 1
                stats[z["trace_confidence"]["level"]] += 1

        (OUT / jp.name).write_text(
            json.dumps(d, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # Toute décision non consommée signale aussi une incohérence.
    for (document, kind, oid), q in queues.items():
        while q:
            z = q.popleft()
            stats["unused_decisions"] += 1
            details["unused_decisions"].append({
                "document": document,
                "kind": kind,
                "id": oid,
                "level": z.get("trace_confidence", {}).get("level"),
            })

    stats["expected_annotations"] = (
        stats["ENTITY_total"] + stats["RELATION_total"]
    )
    stats["missing_annotations"] = (
        stats["expected_annotations"] - stats["annotations"]
    )

    report = {
        "stage": "TRACE_STAGE_8_V2_1_SAFE_ANNOTATOR",
        "stats": dict(stats),
        "details": details,
    }
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("=" * 110)
    print("TRACE / ETAGE 8 V2.1 - CONFIDENCE SAFE ANNOTATOR")
    print("=" * 110)
    ordered = [
        "clinical_documents",
        "ENTITY_total",
        "ENTITY_annotations",
        "ENTITY_unmatched",
        "RELATION_total",
        "RELATION_annotations",
        "RELATION_unmatched",
        "clinical_objects_total",
        "expected_annotations",
        "annotations",
        "missing_annotations",
        "unused_decisions",
        "duplicate_id_groups",
        "duplicate_id_occurrences",
        "HIGH",
        "MEDIUM",
        "LOW",
        "REVIEW",
    ]
    for k in ordered:
        print(f"{k:38}: {stats[k]}")

    print("Sortie clinique :", OUT)
    print("Rapport         :", REPORT)

    if (
        stats["unmatched_clinical_objects"] != 0
        or stats["unused_decisions"] != 0
        or stats["missing_annotations"] != 0
        or stats["annotations"] != stats["expected_annotations"]
    ):
        print("\nSTATUT ANNOTATION : FAIL")
        raise SystemExit(2)

    print("\nSTATUT ANNOTATION : PASS")


if __name__ == "__main__":
    main()
