# -*- coding: utf-8 -*-
"""
pattern_a4_detector.py
======================

SGCE — Pattern A4 Detection Only

A4:
IMAGERIE_PROCEDURE + DEFAILLANCE_ORGANE

Relation TRACE-Sepsis:
    IMAGERIE_PROCEDURE
        --imagerie_objective_defaillance-->
    DEFAILLANCE_ORGANE

Objectif
--------
Détecter automatiquement les candidats où une entité IMAGERIE_PROCEDURE
semble contenir ou exprimer directement une défaillance d'organe qui devrait
être représentée comme DEFAILLANCE_ORGANE séparée et reliée.

IMPORTANT
---------
- Détection uniquement.
- Aucun JSON clinique n'est modifié.
- Les candidats ne sont PAS encore considérés comme hallucinations
  structurelles confirmées.
"""

import csv
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path


# ============================================================
# 1. PATHS
# ============================================================

PATTERN_A4_DIR = Path(__file__).resolve().parent
PATTERN_A_DIR = PATTERN_A4_DIR.parent
PATTERNS_DIR = PATTERN_A_DIR.parent
SGCE_DIR = PATTERNS_DIR.parent
BASE_DIR = SGCE_DIR.parent
PATTERN_A3_DIR = PATTERN_A_DIR / "PatternA3"

INPUT_DIR_CANDIDATES = [
    PATTERN_A3_DIR / "corrected",
]

OUTPUT_DIR = PATTERN_A4_DIR / "detection"
OUTPUT_JSON = OUTPUT_DIR / "pattern_a4_detection_report.json"
OUTPUT_CSV = OUTPUT_DIR / "pattern_a4_candidates.csv"

SOURCE_TYPE = "IMAGERIE_PROCEDURE"
TARGET_TYPE = "DEFAILLANCE_ORGANE"
RELATION_TYPE = "imagerie_objective_defaillance"


# ============================================================
# 2. SIGNALS
# ============================================================

# Signaux textuels conservateurs de défaillance/dysfonction d'organe
# susceptibles d'être explicitement décrits dans une imagerie.
PATTERNS = {
    "DEFAILLANCE_RESPIRATOIRE": [
        r"\bd[eé]tresse\s+respiratoire\b",
        r"\binsuffisance\s+respiratoire\b",
        r"\bSDRA\b",
        r"\bsyndrome\s+de\s+d[eé]tresse\s+respiratoire\b",
    ],
    "DEFAILLANCE_RENALE": [
        r"\binsuffisance\s+r[eé]nale\b",
        r"\bIRA\b",
        r"\bacute\s+kidney\s+injury\b",
    ],
    "DEFAILLANCE_HEPATIQUE": [
        r"\binsuffisance\s+h[eé]patique\b",
        r"\bd[eé]faillance\s+h[eé]patique\b",
    ],
    "DEFAILLANCE_CARDIAQUE": [
        r"\binsuffisance\s+cardiaque\b",
        r"\bd[eé]faillance\s+cardiaque\b",
    ],
    "DEFAILLANCE_NEUROLOGIQUE": [
        r"\bd[eé]faillance\s+neurologique\b",
        r"\bcoma\b",
    ],
    "DEFAILLANCE_CIRCULATOIRE": [
        r"\bchoc\s+septique\b",
        r"\bchoc\s+circulatoire\b",
        r"\bd[eé]faillance\s+h[eé]modynamique\b",
    ],
    "DEFAILLANCE_GENERIQUE": [
        r"\bd[eé]faillance\s+d[' ]?organe\b",
        r"\bdysfonction\s+d[' ]?organe\b",
        r"\binsuffisance\s+multivisc[eé]rale\b",
        r"\bd[eé]faillance\s+multivisc[eé]rale\b",
    ],
}

IMAGING_HINTS = [
    r"\bTDM\b",
    r"\bscanner\b",
    r"\bIRM\b",
    r"\b[eé]chograph(?:ie|ique)\b",
    r"\bradiograph(?:ie|ique)\b",
    r"\bRX\b",
    r"\bTEP\b",
    r"\bPET[-\s]?scan\b",
    r"\bimagerie\b",
]


# ============================================================
# 3. HELPERS
# ============================================================

def normalize(text):
    text = "" if text is None else str(text)
    text = text.replace("’", "'")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    return re.sub(r"\s+", " ", text).strip()


def resolve_input_dir():
    for p in INPUT_DIR_CANDIDATES:
        if p.exists() and any(p.glob("*.json")):
            return p
    raise FileNotFoundError("Aucun dossier JSON clinique trouvé.")


def entity_id(e):
    return e.get("identifiant_entite") or e.get("id") or e.get("entity_id")


def entity_type(e):
    return e.get("categorie") or e.get("type") or ""


def entity_page(e):
    if e.get("page") is not None:
        return e.get("page")
    return e.get("page_number")


def entity_text(e):
    vals = []
    for k in ("preuve", "name", "valeur", "libelle", "parametre", "texte", "text"):
        v = e.get(k)
        if v not in (None, ""):
            s = str(v).strip()
            if s and s not in vals:
                vals.append(s)
    return " | ".join(vals)


def relation_type(r):
    return r.get("type_relation") or r.get("relation") or r.get("type") or ""


def relation_source(r):
    return (
        r.get("identifiant_entite_sujet")
        or r.get("from_id")
        or r.get("subject_id")
    )


def relation_target(r):
    return (
        r.get("identifiant_entite_objet")
        or r.get("to_id")
        or r.get("object_id")
    )


def get_entities(doc):
    if isinstance(doc.get("global_entities"), list):
        return doc["global_entities"]

    out = []
    for p in doc.get("pages", []) or []:
        out.extend(p.get("entities", []) or [])
    return out


def get_relations(doc):
    if isinstance(doc.get("global_relations"), list):
        return doc["global_relations"]

    out = []
    for p in doc.get("pages", []) or []:
        out.extend(p.get("relations", []) or [])
    return out


def is_clinical_document(doc):
    return (
        isinstance(doc, dict)
        and (
            isinstance(doc.get("global_entities"), list)
            or isinstance(doc.get("pages"), list)
        )
    )


def token_set(text):
    return {
        t for t in re.findall(r"[a-z0-9]+", normalize(text))
        if len(t) >= 3
    }


def token_overlap(a, b):
    ta, tb = token_set(a), token_set(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def relation_exists(source_id, target_id, relations):
    return any(
        relation_type(r) == RELATION_TYPE
        and relation_source(r) == source_id
        and relation_target(r) == target_id
        for r in relations
    )


# ============================================================
# 4. SIGNAL DETECTION
# ============================================================

def detect_failure_signals(text):
    norm = normalize(text)
    detected = {}

    for family, regexes in PATTERNS.items():
        hits = []

        for pattern in regexes:
            for m in re.finditer(pattern, norm, flags=re.IGNORECASE):
                value = m.group(0).strip()
                if value and value not in hits:
                    hits.append(value)

        if hits:
            detected[family] = hits

    return detected


def has_imaging_hint(text):
    norm = normalize(text)
    return any(
        re.search(p, norm, flags=re.IGNORECASE)
        for p in IMAGING_HINTS
    )


# ============================================================
# 5. TARGET MATCHING
# ============================================================

def find_same_page_targets(source, entities):
    src_page = entity_page(source)
    src_text = entity_text(source)
    src_norm = normalize(src_text)

    targets = []

    for e in entities:
        if entity_type(e) != TARGET_TYPE:
            continue

        if entity_page(e) != src_page:
            continue

        tgt_text = entity_text(e)
        tgt_norm = normalize(tgt_text)

        containment = bool(
            src_norm and tgt_norm
            and (
                tgt_norm in src_norm
                or src_norm in tgt_norm
            )
        )

        overlap = token_overlap(src_text, tgt_text)

        targets.append({
            "entity_id": entity_id(e),
            "page": entity_page(e),
            "text": tgt_text,
            "text_containment": containment,
            "token_overlap": round(overlap, 4),
        })

    targets.sort(
        key=lambda x: (
            x["text_containment"],
            x["token_overlap"],
        ),
        reverse=True,
    )

    return targets


# ============================================================
# 6. STRENGTH
# ============================================================

def classify_strength(signals, same_page_targets):
    n_families = len(signals)

    reliable_target = any(
        t["text_containment"]
        or t["token_overlap"] >= 0.60
        for t in same_page_targets
    )

    if n_families >= 2:
        return "STRONG"

    if n_families >= 1 and reliable_target:
        return "STRONG"

    if n_families >= 1:
        return "MEDIUM"

    if reliable_target:
        return "WEAK"

    return None


# ============================================================
# 7. DOCUMENT DETECTION
# ============================================================

def detect_document(path, doc):
    entities = get_entities(doc)
    relations = get_relations(doc)

    imaging_entities = [
        e for e in entities
        if entity_type(e) == SOURCE_TYPE
    ]

    failure_entities = [
        e for e in entities
        if entity_type(e) == TARGET_TYPE
    ]

    candidates = []

    for source in imaging_entities:
        text = entity_text(source)

        signals = detect_failure_signals(text)
        targets = find_same_page_targets(source, entities)

        strength = classify_strength(signals, targets)

        if strength is None:
            continue

        sid = entity_id(source)

        enriched_targets = []

        for target in targets:
            x = dict(target)
            x["relation_already_exists"] = relation_exists(
                sid,
                x["entity_id"],
                relations,
            )
            enriched_targets.append(x)

        candidates.append({
            "document": path.name,
            "pattern": "A4",
            "subcase": "IMAGERIE_PROCEDURE_DEFAILLANCE_ORGANE",
            "source_entity": {
                "entity_id": sid,
                "type": SOURCE_TYPE,
                "page": entity_page(source),
                "text": text,
            },
            "detected_failure_families": list(signals.keys()),
            "detected_failure_signals": signals,
            "imaging_hint_present": has_imaging_hint(text),
            "same_page_failure_targets": enriched_targets,
            "same_page_failure_target_count": len(enriched_targets),
            "strength": strength,
            "status": "A4_CANDIDATE",
        })

    return len(imaging_entities), len(failure_entities), candidates


# ============================================================
# 8. MAIN
# ============================================================

def main():
    input_dir = resolve_input_dir()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_json_files = sorted(input_dir.glob("*.json"))

    clinical_files = []
    skipped_nonclinical = []
    errors = []
    loaded = {}

    for path in all_json_files:
        try:
            with path.open("r", encoding="utf-8") as f:
                doc = json.load(f)

            if not is_clinical_document(doc):
                skipped_nonclinical.append(path.name)
                continue

            clinical_files.append(path)
            loaded[path] = doc

        except Exception as exc:
            errors.append({
                "document": path.name,
                "error": str(exc),
            })

    candidates = []
    document_summaries = []

    total_imaging = 0
    total_failure = 0

    for path in clinical_files:
        try:
            n_img, n_fail, cands = detect_document(
                path,
                loaded[path],
            )

            total_imaging += n_img
            total_failure += n_fail
            candidates.extend(cands)

            document_summaries.append({
                "document": path.name,
                "imaging_entities_scanned": n_img,
                "failure_entities_existing": n_fail,
                "a4_candidates": len(cands),
            })

        except Exception as exc:
            errors.append({
                "document": path.name,
                "error": str(exc),
            })

    strengths = Counter(c["strength"] for c in candidates)

    families = Counter()
    for c in candidates:
        for fam in c["detected_failure_families"]:
            families[fam] += 1

    report = {
        "pattern": "A4",
        "name": "IMAGERIE_PROCEDURE + DEFAILLANCE_ORGANE",
        "relation": RELATION_TYPE,
        "methodological_status": "DETECTION_ONLY_NO_CORRECTION",
        "input_directory": str(input_dir),

        "summary": {
            "json_files_found": len(all_json_files),
            "clinical_documents_scanned": len(clinical_files),
            "nonclinical_json_skipped": len(skipped_nonclinical),
            "imaging_entities_scanned": total_imaging,
            "existing_failure_entities": total_failure,
            "a4_candidates": len(candidates),
            "weak": strengths.get("WEAK", 0),
            "medium": strengths.get("MEDIUM", 0),
            "strong": strengths.get("STRONG", 0),
            "errors": len(errors),
        },

        "signal_family_counts": dict(families),
        "nonclinical_json_skipped": skipped_nonclinical,
        "documents": document_summaries,
        "candidates": candidates,
        "errors": errors,
    }

    OUTPUT_JSON.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    fields = [
        "document",
        "source_entity_id",
        "page",
        "source_text",
        "strength",
        "families",
        "same_page_failure_target_count",
        "best_target_id",
        "best_target_text",
        "best_target_overlap",
        "best_target_containment",
        "relation_already_exists",
    ]

    with OUTPUT_CSV.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()

        for c in candidates:
            targets = c["same_page_failure_targets"]
            best = targets[0] if targets else {}

            writer.writerow({
                "document": c["document"],
                "source_entity_id": c["source_entity"]["entity_id"],
                "page": c["source_entity"]["page"],
                "source_text": c["source_entity"]["text"],
                "strength": c["strength"],
                "families": "; ".join(
                    c["detected_failure_families"]
                ),
                "same_page_failure_target_count":
                    c["same_page_failure_target_count"],
                "best_target_id": best.get("entity_id", ""),
                "best_target_text": best.get("text", ""),
                "best_target_overlap": best.get("token_overlap", ""),
                "best_target_containment": best.get("text_containment", ""),
                "relation_already_exists":
                    best.get("relation_already_exists", ""),
            })

    print("=" * 76)
    print("SGCE - PATTERN A4 DETECTION")
    print("=" * 76)
    print(f"Entrée                  : {input_dir}")
    print(f"JSON trouvés            : {len(all_json_files)}")
    print(f"Documents cliniques     : {len(clinical_files)}")
    print(f"JSON non cliniques ignorés : {len(skipped_nonclinical)}")
    print(f"IMAGERIE analysées      : {total_imaging}")
    print(f"DEFAILLANCE existantes  : {total_failure}")
    print()
    print(f"Candidats A4            : {len(candidates)}")
    print(f"WEAK                    : {strengths.get('WEAK', 0)}")
    print(f"MEDIUM                  : {strengths.get('MEDIUM', 0)}")
    print(f"STRONG                  : {strengths.get('STRONG', 0)}")
    print(f"Erreurs                 : {len(errors)}")
    print()
    print("Familles de signaux :")

    if families:
        for family, count in families.most_common():
            print(f"  {family:<34} : {count}")
    else:
        print("  Aucun signal détecté.")

    print()
    print(f"Rapport JSON            : {OUTPUT_JSON}")
    print(f"CSV candidats           : {OUTPUT_CSV}")
    print()
    print("Aucun JSON clinique n'a été modifié.")


if __name__ == "__main__":
    main()
