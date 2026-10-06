# -*- coding: utf-8 -*-
"""
pattern_a5_detector.py
======================

SGCE — Pattern A5 Detection Only

A5:
IMAGERIE_PROCEDURE + COMORBIDITE_ANTECEDENT

Relation TRACE-Sepsis:
    IMAGERIE_PROCEDURE
        --imagerie_objective_comorbidite-->
    COMORBIDITE_ANTECEDENT

Détection uniquement : aucun JSON clinique n'est modifié.
"""

import csv
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

PATTERN_A5_DIR = Path(__file__).resolve().parent
PATTERN_A_DIR = PATTERN_A5_DIR.parent
PATTERNS_DIR = PATTERN_A_DIR.parent
SGCE_DIR = PATTERNS_DIR.parent
BASE_DIR = SGCE_DIR.parent
PATTERN_A4_DIR = PATTERN_A_DIR / "PatternA4"

INPUT_DIR_CANDIDATES = [
    PATTERN_A4_DIR / "corrected",
]

OUTPUT_DIR = PATTERN_A5_DIR / "detection"
OUTPUT_JSON = OUTPUT_DIR / "pattern_a5_detection_report.json"
OUTPUT_CSV = OUTPUT_DIR / "pattern_a5_candidates.csv"

SOURCE_TYPE = "IMAGERIE_PROCEDURE"
TARGET_TYPE = "COMORBIDITE_ANTECEDENT"
RELATION_TYPE = "imagerie_objective_comorbidite"

# Signaux volontairement conservateurs : formulations explicitement
# compatibles avec une comorbidité / un antécédent dans le texte de l'entité.
PATTERNS = {
    "ANTECEDENT_EXPLICITE": [
        r"\bant[eé]c[eé]dent(?:s)?\b",
        r"\bATCD\b",
        r"\bant[eé]rieurement\b",
        r"\bancien(?:ne)?\b",
        r"\bchronique\b",
    ],
    "COMORBIDITE_EXPLICITE": [
        r"\bcomorbidit[eé]\b",
        r"\bpathologie\s+chronique\b",
        r"\bmaladie\s+chronique\b",
    ],
}


def normalize(text):
    text = "" if text is None else str(text)
    text = text.replace("’", "'")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower()).strip()


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
    return e.get("page") if e.get("page") is not None else e.get("page_number")


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
    return r.get("identifiant_entite_sujet") or r.get("from_id") or r.get("subject_id")


def relation_target(r):
    return r.get("identifiant_entite_objet") or r.get("to_id") or r.get("object_id")


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
    return isinstance(doc, dict) and (
        isinstance(doc.get("global_entities"), list)
        or isinstance(doc.get("pages"), list)
    )


def token_set(text):
    return {t for t in re.findall(r"[a-z0-9]+", normalize(text)) if len(t) >= 3}


def token_overlap(a, b):
    ta, tb = token_set(a), token_set(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def detect_signals(text):
    norm = normalize(text)
    result = {}
    for family, regexes in PATTERNS.items():
        hits = []
        for pattern in regexes:
            for m in re.finditer(pattern, norm, re.IGNORECASE):
                if m.group(0) not in hits:
                    hits.append(m.group(0))
        if hits:
            result[family] = hits
    return result


def find_same_page_targets(source, entities, relations):
    src_text = entity_text(source)
    src_norm = normalize(src_text)
    sid = entity_id(source)
    page = entity_page(source)
    out = []

    for e in entities:
        if entity_type(e) != TARGET_TYPE or entity_page(e) != page:
            continue

        tgt_text = entity_text(e)
        tgt_norm = normalize(tgt_text)

        containment = bool(
            src_norm and tgt_norm
            and (tgt_norm in src_norm or src_norm in tgt_norm)
        )
        overlap = token_overlap(src_text, tgt_text)
        reliable = containment or overlap >= 0.60

        rel_exists = any(
            relation_type(r) == RELATION_TYPE
            and relation_source(r) == sid
            and relation_target(r) == entity_id(e)
            for r in relations
        )

        out.append({
            "entity_id": entity_id(e),
            "page": page,
            "text": tgt_text,
            "containment": containment,
            "token_overlap": round(overlap, 4),
            "reliable": reliable,
            "relation_already_exists": rel_exists,
        })

    out.sort(
        key=lambda x: (x["reliable"], x["containment"], x["token_overlap"]),
        reverse=True,
    )
    return out


def classify(signals, targets):
    reliable = any(t["reliable"] for t in targets)
    n = len(signals)

    if n >= 2 or (n >= 1 and reliable):
        return "STRONG"
    if n >= 1:
        return "MEDIUM"
    if reliable:
        return "WEAK"
    return None


def main():
    input_dir = resolve_input_dir()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    json_files = sorted(input_dir.glob("*.json"))
    candidates = []
    skipped = []
    errors = []
    clinical = 0
    total_img = 0
    total_comorb = 0

    for path in json_files:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))

            if not is_clinical_document(doc):
                skipped.append(path.name)
                continue

            clinical += 1
            entities = get_entities(doc)
            relations = get_relations(doc)

            images = [e for e in entities if entity_type(e) == SOURCE_TYPE]
            comorbs = [e for e in entities if entity_type(e) == TARGET_TYPE]

            total_img += len(images)
            total_comorb += len(comorbs)

            for source in images:
                signals = detect_signals(entity_text(source))
                targets = find_same_page_targets(source, entities, relations)
                strength = classify(signals, targets)

                if not strength:
                    continue

                candidates.append({
                    "document": path.name,
                    "pattern": "A5",
                    "subcase": "IMAGERIE_PROCEDURE_COMORBIDITE_ANTECEDENT",
                    "source_entity": {
                        "entity_id": entity_id(source),
                        "type": SOURCE_TYPE,
                        "page": entity_page(source),
                        "text": entity_text(source),
                    },
                    "detected_comorbidity_families": list(signals.keys()),
                    "detected_comorbidity_signals": signals,
                    "same_page_comorbidity_targets": targets,
                    "same_page_comorbidity_target_count": len(targets),
                    "strength": strength,
                    "status": "A5_CANDIDATE",
                })

        except Exception as exc:
            errors.append({"document": path.name, "error": str(exc)})

    strengths = Counter(c["strength"] for c in candidates)
    families = Counter()
    for c in candidates:
        for fam in c["detected_comorbidity_families"]:
            families[fam] += 1

    report = {
        "pattern": "A5",
        "name": "IMAGERIE_PROCEDURE + COMORBIDITE_ANTECEDENT",
        "relation": RELATION_TYPE,
        "methodological_status": "DETECTION_ONLY_NO_CORRECTION",
        "input_directory": str(input_dir),
        "summary": {
            "json_files_found": len(json_files),
            "clinical_documents_scanned": clinical,
            "nonclinical_json_skipped": len(skipped),
            "imaging_entities_scanned": total_img,
            "existing_comorbidity_entities": total_comorb,
            "a5_candidates": len(candidates),
            "weak": strengths.get("WEAK", 0),
            "medium": strengths.get("MEDIUM", 0),
            "strong": strengths.get("STRONG", 0),
            "errors": len(errors),
        },
        "signal_family_counts": dict(families),
        "candidates": candidates,
        "nonclinical_json_skipped": skipped,
        "errors": errors,
    }

    OUTPUT_JSON.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        fields = [
            "document", "source_entity_id", "page", "source_text",
            "strength", "families", "same_page_comorbidity_target_count",
            "best_target_id", "best_target_text", "best_target_overlap",
            "best_target_containment", "relation_already_exists",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()

        for c in candidates:
            targets = c["same_page_comorbidity_targets"]
            best = targets[0] if targets else {}
            writer.writerow({
                "document": c["document"],
                "source_entity_id": c["source_entity"]["entity_id"],
                "page": c["source_entity"]["page"],
                "source_text": c["source_entity"]["text"],
                "strength": c["strength"],
                "families": "; ".join(c["detected_comorbidity_families"]),
                "same_page_comorbidity_target_count":
                    c["same_page_comorbidity_target_count"],
                "best_target_id": best.get("entity_id", ""),
                "best_target_text": best.get("text", ""),
                "best_target_overlap": best.get("token_overlap", ""),
                "best_target_containment": best.get("containment", ""),
                "relation_already_exists":
                    best.get("relation_already_exists", ""),
            })

    print("=" * 76)
    print("SGCE - PATTERN A5 DETECTION")
    print("=" * 76)
    print(f"Entrée                  : {input_dir}")
    print(f"JSON trouvés            : {len(json_files)}")
    print(f"Documents cliniques     : {clinical}")
    print(f"JSON non cliniques ignorés : {len(skipped)}")
    print(f"IMAGERIE analysées      : {total_img}")
    print(f"COMORBIDITE existantes  : {total_comorb}")
    print()
    print(f"Candidats A5            : {len(candidates)}")
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
