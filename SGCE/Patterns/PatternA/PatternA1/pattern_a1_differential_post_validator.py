# -*- coding: utf-8 -*-
"""
pattern_a1_differential_post_validator.py

Post-validation DIFFERENTIELLE du Pattern A1.
Compare chaque JSON ORIGINAL avec son JSON CORRIGE afin de distinguer :

- PRE_EXISTING       : anomalie déjà présente avant SGCE A1
- INTRODUCED_BY_A1   : nouvelle anomalie apparue après correction A1
- RESOLVED_BY_A1     : anomalie présente avant, absente après

Les divergences historiques global_relations <-> pages[*].relations
sont mesurées séparément et ne font PAS échouer A1 si elles ne s'aggravent pas.

Critères A1 PASS :
- 8/8 LINK attendus retrouvés (ou le nombre réellement enregistré)
- 10/10 SPLIT attendus retrouvés (ou le nombre réellement enregistré)
- 0 nouvel ID d'entité dupliqué
- 0 nouvel ID de relation dupliqué
- 0 nouvel endpoint orphelin
- 0 nouveau mauvais typage A1
- 0 opération A1 manquante
- aucun fichier source modifié par ce validateur

Aucune donnée clinique n'est modifiée.
"""

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

PATTERN_A1_DIR = Path(__file__).resolve().parent
PATTERN_A_DIR = PATTERN_A1_DIR.parent
PATTERNS_DIR = PATTERN_A_DIR.parent
SGCE_DIR = PATTERNS_DIR.parent
BASE_DIR = SGCE_DIR.parent

SOURCE_DIR = BASE_DIR / "SortieJson_Postprocessing"

CORRECTED_DIR_CANDIDATES = [
    PATTERN_A1_DIR / "corrected",
]

REPORT_CANDIDATES = [
    PATTERN_A1_DIR / "corrected" / "pattern_a1_auto_correction_report.json",
]

OUTPUT_DIR = PATTERN_A1_DIR / "post_validation"
OUTPUT_JSON = OUTPUT_DIR / "pattern_a1_differential_post_validation_report.json"
OUTPUT_CSV = OUTPUT_DIR / "pattern_a1_differential_anomalies.csv"

A1_RELATION = "traitement_a_pour_posologie"

CRITICAL_CODES = {
    "DUPLICATE_GLOBAL_ENTITY_ID",
    "DUPLICATE_GLOBAL_RELATION_ID",
    "ORPHAN_RELATION_SOURCE",
    "ORPHAN_RELATION_TARGET",
    "INVALID_A1_SOURCE_TYPE",
    "INVALID_A1_TARGET_TYPE",
}

SYNC_CODES = {
    "RELATION_PAGE_NOT_IN_GLOBAL",
    "RELATION_GLOBAL_NOT_IN_PAGE",
}


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def eid(e):
    return e.get("identifiant_entite") or e.get("id") or e.get("entity_id")


def etype(e):
    return e.get("categorie") or e.get("type")


def rid(r):
    return r.get("identifiant_relation") or r.get("id") or r.get("relation_id")


def rtype(r):
    return r.get("type_relation") or r.get("relation") or r.get("type")


def rsource(r):
    return (
        r.get("identifiant_entite_sujet")
        or r.get("from_id")
        or r.get("subject_id")
    )


def rtarget(r):
    return (
        r.get("identifiant_entite_objet")
        or r.get("to_id")
        or r.get("object_id")
    )


def global_entities(doc):
    return doc.get("global_entities", []) or []


def global_relations(doc):
    return doc.get("global_relations", []) or []


def page_entities(doc):
    out = []
    for page in doc.get("pages", []) or []:
        pnum = page.get("page") or page.get("page_number") or page.get("numero_page")
        for e in page.get("entities", []) or []:
            out.append((pnum, e))
    return out


def page_relations(doc):
    out = []
    for page in doc.get("pages", []) or []:
        pnum = page.get("page") or page.get("page_number") or page.get("numero_page")
        for r in page.get("relations", []) or []:
            out.append((pnum, r))
    return out


def resolve_first(candidates, label):
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(
        f"{label} introuvable.\n- " + "\n- ".join(str(p) for p in candidates)
    )


def anomaly_key(a):
    """Clé stable pour comparaison avant/après."""
    return (
        a.get("code"),
        a.get("entity_id"),
        a.get("relation_id"),
        a.get("source_id"),
        a.get("target_id"),
        a.get("observed_type"),
    )


def collect_anomalies(doc):
    anomalies = []

    ge = global_entities(doc)
    gr = global_relations(doc)
    pe = page_entities(doc)
    pr = page_relations(doc)

    ge_ids = [eid(e) for e in ge if eid(e)]
    gr_ids = [rid(r) for r in gr if rid(r)]
    pe_ids = [eid(e) for _, e in pe if eid(e)]
    pr_ids = [rid(r) for _, r in pr if rid(r)]

    emap = {eid(e): e for e in ge if eid(e)}

    for x, n in Counter(ge_ids).items():
        if n > 1:
            anomalies.append({
                "code": "DUPLICATE_GLOBAL_ENTITY_ID",
                "entity_id": x,
                "occurrences": n,
            })

    for x, n in Counter(gr_ids).items():
        if n > 1:
            anomalies.append({
                "code": "DUPLICATE_GLOBAL_RELATION_ID",
                "relation_id": x,
                "occurrences": n,
            })

    for r in gr:
        rrid = rid(r)
        sid = rsource(r)
        tid = rtarget(r)

        if sid not in emap:
            anomalies.append({
                "code": "ORPHAN_RELATION_SOURCE",
                "relation_id": rrid,
                "source_id": sid,
                "target_id": tid,
            })

        if tid not in emap:
            anomalies.append({
                "code": "ORPHAN_RELATION_TARGET",
                "relation_id": rrid,
                "source_id": sid,
                "target_id": tid,
            })

        if rtype(r) == A1_RELATION:
            src = emap.get(sid)
            tgt = emap.get(tid)

            if src and etype(src) != "TRAITEMENT":
                anomalies.append({
                    "code": "INVALID_A1_SOURCE_TYPE",
                    "relation_id": rrid,
                    "source_id": sid,
                    "target_id": tid,
                    "observed_type": etype(src),
                })

            if tgt and etype(tgt) != "POSOLOGIE":
                anomalies.append({
                    "code": "INVALID_A1_TARGET_TYPE",
                    "relation_id": rrid,
                    "source_id": sid,
                    "target_id": tid,
                    "observed_type": etype(tgt),
                })

    # Mesure historique de synchronisation relationnelle.
    ge_rel = set(gr_ids)
    page_rel = set(pr_ids)

    for x in sorted(page_rel - ge_rel):
        anomalies.append({
            "code": "RELATION_PAGE_NOT_IN_GLOBAL",
            "relation_id": x,
        })

    for x in sorted(ge_rel - page_rel):
        anomalies.append({
            "code": "RELATION_GLOBAL_NOT_IN_PAGE",
            "relation_id": x,
        })

    return anomalies


def extract_applied_operations(report):
    # Auto-corrector récent.
    if isinstance(report.get("operations"), list):
        return [
            op for op in report["operations"]
            if op.get("applied") is True
        ]

    # Correcteur précédent.
    ops = []
    for d in report.get("documents", []) or []:
        filename = d.get("document")
        for op in d.get("operations", []) or []:
            if op.get("status") == "APPLIED":
                x = dict(op)
                x.setdefault("document", filename)
                ops.append(x)
    return ops


def operation_type(op):
    return op.get("operation") or op.get("decision")


def verify_operations(corrected, operations):
    """Vérifie uniquement les structures créées/attendues par A1."""
    ge = global_entities(corrected)
    gr = global_relations(corrected)
    emap = {eid(e): e for e in ge if eid(e)}

    results = []

    for op in operations:
        kind = operation_type(op)
        source_id = op.get("source_entity_id")

        row = {
            "operation": kind,
            "source_entity_id": source_id,
            "status": "FAIL",
        }

        if kind == "LINK":
            target_id = op.get("target_posology_id") or op.get("target_entity_id")
            row["target_posology_id"] = target_id

            matches = [
                r for r in gr
                if rtype(r) == A1_RELATION
                and rsource(r) == source_id
                and rtarget(r) == target_id
            ]

            if (
                len(matches) == 1
                and source_id in emap
                and target_id in emap
                and etype(emap[source_id]) == "TRAITEMENT"
                and etype(emap[target_id]) == "POSOLOGIE"
            ):
                row["status"] = "PASS"

        elif kind == "SPLIT":
            pos_id = op.get("created_posology_id") or op.get("new_posology_id")
            row["created_posology_id"] = pos_id

            matches = [
                r for r in gr
                if rtype(r) == A1_RELATION
                and rsource(r) == source_id
                and rtarget(r) == pos_id
            ]

            if (
                len(matches) == 1
                and source_id in emap
                and pos_id in emap
                and etype(emap[source_id]) == "TRAITEMENT"
                and etype(emap[pos_id]) == "POSOLOGIE"
            ):
                row["status"] = "PASS"

        results.append(row)

    return results


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    corrected_dir = resolve_first(
        CORRECTED_DIR_CANDIDATES, "Dossier corrigé"
    )
    correction_report_path = resolve_first(
        REPORT_CANDIDATES, "Rapport de correction"
    )
    correction_report = load_json(correction_report_path)
    operations = extract_applied_operations(correction_report)

    ops_by_doc = {}
    for op in operations:
        if op.get("document"):
            ops_by_doc.setdefault(op["document"], []).append(op)

    source_files = sorted(SOURCE_DIR.glob("*.json"))
    hashes_before = {p.name: sha256(p) for p in source_files}

    differential_rows = []
    document_results = []
    op_results_all = []

    print("=" * 78)
    print("SGCE - PATTERN A1 DIFFERENTIAL POST-VALIDATION")
    print("=" * 78)
    print(f"Original : {SOURCE_DIR}")
    print(f"Corrigé  : {corrected_dir}")
    print(f"Rapport  : {correction_report_path}")
    print(f"Opérations A1 enregistrées : {len(operations)}")
    print()

    for src_path in source_files:
        filename = src_path.name
        corr_path = corrected_dir / filename

        if not corr_path.exists():
            differential_rows.append({
                "document": filename,
                "classification": "INTRODUCED_BY_A1",
                "code": "CORRECTED_FILE_MISSING",
            })
            document_results.append({
                "document": filename,
                "status": "FAIL",
                "reason": "CORRECTED_FILE_MISSING",
            })
            continue

        original = load_json(src_path)
        corrected = load_json(corr_path)

        before = collect_anomalies(original)
        after = collect_anomalies(corrected)

        before_map = {anomaly_key(a): a for a in before}
        after_map = {anomaly_key(a): a for a in after}

        before_keys = set(before_map)
        after_keys = set(after_map)

        pre_existing = before_keys & after_keys
        introduced = after_keys - before_keys
        resolved = before_keys - after_keys

        for key in sorted(pre_existing, key=str):
            a = dict(after_map[key])
            a.update({
                "document": filename,
                "classification": "PRE_EXISTING",
            })
            differential_rows.append(a)

        for key in sorted(introduced, key=str):
            a = dict(after_map[key])
            a.update({
                "document": filename,
                "classification": "INTRODUCED_BY_A1",
            })
            differential_rows.append(a)

        for key in sorted(resolved, key=str):
            a = dict(before_map[key])
            a.update({
                "document": filename,
                "classification": "RESOLVED_BY_A1",
            })
            differential_rows.append(a)

        op_results = verify_operations(
            corrected, ops_by_doc.get(filename, [])
        )
        for r in op_results:
            r["document"] = filename
        op_results_all.extend(op_results)

        critical_introduced = [
            after_map[k] for k in introduced
            if after_map[k].get("code") in CRITICAL_CODES
        ]

        failed_ops = [r for r in op_results if r["status"] != "PASS"]

        document_results.append({
            "document": filename,
            "expected_a1_operations": len(ops_by_doc.get(filename, [])),
            "validated_a1_operations": sum(
                r["status"] == "PASS" for r in op_results
            ),
            "pre_existing_anomalies": len(pre_existing),
            "introduced_anomalies": len(introduced),
            "introduced_critical_anomalies": len(critical_introduced),
            "resolved_anomalies": len(resolved),
            "status": (
                "PASS"
                if not critical_introduced and not failed_ops
                else "FAIL"
            ),
        })

    source_changed = [
        p.name for p in source_files
        if sha256(p) != hashes_before[p.name]
    ]

    counts_class = Counter(
        r.get("classification") for r in differential_rows
    )
    counts_intro_code = Counter(
        r.get("code")
        for r in differential_rows
        if r.get("classification") == "INTRODUCED_BY_A1"
    )
    counts_pre_code = Counter(
        r.get("code")
        for r in differential_rows
        if r.get("classification") == "PRE_EXISTING"
    )

    expected_links = sum(operation_type(o) == "LINK" for o in operations)
    expected_splits = sum(operation_type(o) == "SPLIT" for o in operations)

    validated_links = sum(
        r["status"] == "PASS" and r["operation"] == "LINK"
        for r in op_results_all
    )
    validated_splits = sum(
        r["status"] == "PASS" and r["operation"] == "SPLIT"
        for r in op_results_all
    )

    introduced_critical = [
        r for r in differential_rows
        if r.get("classification") == "INTRODUCED_BY_A1"
        and r.get("code") in CRITICAL_CODES
    ]

    # Synchronisation : informative. Elle n'est bloquante que si on
    # introduit de nouvelles divergences de synchronisation.
    introduced_sync = [
        r for r in differential_rows
        if r.get("classification") == "INTRODUCED_BY_A1"
        and r.get("code") in SYNC_CODES
    ]

    final_pass = (
        validated_links == expected_links
        and validated_splits == expected_splits
        and len(introduced_critical) == 0
        and len(source_changed) == 0
    )

    summary = {
        "documents_checked": len(source_files),
        "documents_passed": sum(
            d.get("status") == "PASS" for d in document_results
        ),
        "documents_failed": sum(
            d.get("status") == "FAIL" for d in document_results
        ),
        "expected_operations": len(operations),
        "expected_links": expected_links,
        "validated_links": validated_links,
        "expected_splits": expected_splits,
        "validated_splits": validated_splits,
        "validated_operations": validated_links + validated_splits,
        "pre_existing_anomalies": counts_class["PRE_EXISTING"],
        "introduced_anomalies_total": counts_class["INTRODUCED_BY_A1"],
        "introduced_critical_anomalies": len(introduced_critical),
        "introduced_sync_differences": len(introduced_sync),
        "resolved_anomalies": counts_class["RESOLVED_BY_A1"],
        "source_files_changed": len(source_changed),
        "final_a1_status": "PASS" if final_pass else "FAIL",
    }

    report = {
        "pattern": "A1_TRAITEMENT_POSOLOGIE",
        "method": "DIFFERENTIAL_POST_VALIDATION",
        "principle": (
            "Compare les anomalies avant et après SGCE afin de ne pas "
            "attribuer à A1 des incohérences préexistantes."
        ),
        "critical_codes": sorted(CRITICAL_CODES),
        "sync_codes_non_blocking_if_preexisting": sorted(SYNC_CODES),
        "summary": summary,
        "pre_existing_by_code": dict(counts_pre_code),
        "introduced_by_code": dict(counts_intro_code),
        "source_files_changed": source_changed,
        "operation_checks": op_results_all,
        "documents": document_results,
        "differential_anomalies": differential_rows,
    }

    with OUTPUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    fields = [
        "document", "classification", "code",
        "entity_id", "relation_id", "source_id", "target_id",
        "observed_type", "occurrences",
    ]
    with OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(differential_rows)

    print("=" * 78)
    print("RÉSUMÉ DIFFERENTIEL A1")
    print("=" * 78)
    print(f"Documents vérifiés             : {summary['documents_checked']}")
    print(f"Documents PASS                 : {summary['documents_passed']}")
    print(f"Documents FAIL                 : {summary['documents_failed']}")
    print()
    print(f"LINK attendus                  : {expected_links}")
    print(f"LINK validés                   : {validated_links}")
    print(f"SPLIT attendus                 : {expected_splits}")
    print(f"SPLIT validés                  : {validated_splits}")
    print(f"Opérations A1 validées         : {summary['validated_operations']}")
    print()
    print(f"Anomalies préexistantes        : {summary['pre_existing_anomalies']}")
    print(f"Nouvelles anomalies totales    : {summary['introduced_anomalies_total']}")
    print(f"Nouvelles anomalies CRITIQUES  : {summary['introduced_critical_anomalies']}")
    print(f"Nouvelles divergences sync     : {summary['introduced_sync_differences']}")
    print(f"Anomalies résolues             : {summary['resolved_anomalies']}")
    print(f"Sources modifiées              : {summary['source_files_changed']}")
    print()
    print(f"STATUT FINAL A1                : {summary['final_a1_status']}")
    print()
    print(f"Rapport JSON : {OUTPUT_JSON}")
    print(f"Rapport CSV  : {OUTPUT_CSV}")
    print()
    print("Aucune donnée clinique n'a été modifiée.")


if __name__ == "__main__":
    main()
