# -*- coding: utf-8 -*-
"""
pattern_a6_detector.py
======================

SGCE — Pattern A6 Detection Only

A6:
DONNEE_PATIENT + SYMPTOME

Relation TRACE-Sepsis:
    DONNEE_PATIENT
        --presente_symptome-->
    SYMPTOME

Détection uniquement : aucun JSON clinique n'est modifié.
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

PATTERN_A6_DIR = Path(__file__).resolve().parent
PATTERN_A_DIR = PATTERN_A6_DIR.parent
PATTERNS_DIR = PATTERN_A_DIR.parent
SGCE_DIR = PATTERNS_DIR.parent
BASE_DIR = SGCE_DIR.parent
PATTERN_A5_DIR = PATTERN_A_DIR / "PatternA5"

INPUT_DIR_CANDIDATES = [
    PATTERN_A5_DIR / "corrected",
]

OUTPUT_DIR = PATTERN_A6_DIR / "detection"
OUTPUT_JSON = OUTPUT_DIR / "pattern_a6_detection_report.json"
OUTPUT_CSV = OUTPUT_DIR / "pattern_a6_candidates.csv"

SOURCE_TYPE = "DONNEE_PATIENT"
TARGET_TYPE = "SYMPTOME"
RELATION_TYPE = "presente_symptome"

RELIABLE_OVERLAP_THRESHOLD = 0.60


# ============================================================
# 2. CONSERVATIVE EXPLICIT SYMPTOM SIGNALS
# ============================================================

# Objectif :
# détecter seulement des symptômes explicitement présents dans le texte
# de DONNEE_PATIENT. Aucun raisonnement clinique externe.

PATTERNS = {
    "DOULEUR": [
        r"\bdouleur(?:s)?\b",
        r"\bdouloureux\b",
        r"\bdouloureuse\b",
        r"\balgie\b",
    ],
    "DYSPNEE_RESPIRATOIRE": [
        r"\bdyspn[eé]e\b",
        r"\bessoufflement\b",
        r"\bg[eê]ne respiratoire\b",
    ],
    "FIEVRE_FRISSONS": [
        r"\bfi[eè]vre\b",
        r"\bfrisson(?:s)?\b",
    ],
    "TOUX_EXPECTORATION": [
        r"\btoux\b",
        r"\bexpector(?:ation|ations)\b",
    ],
    "DIGESTIF": [
        r"\bnaus[eé]e(?:s)?\b",
        r"\bvomissement(?:s)?\b",
        r"\bdiarrh[eé]e\b",
        r"\bconstipation\b",
        r"\bdouleur abdominale\b",
    ],
    "NEUROLOGIQUE": [
        r"\bconfusion\b",
        r"\bagitation\b",
        r"\bsomnolence\b",
        r"\bvertige(?:s)?\b",
        r"\bc[eé]phal[eé]e(?:s)?\b",
    ],
    "URINAIRE": [
        r"\bdysurie\b",
        r"\bbr[uû]lure(?:s)? mictionnelle(?:s)?\b",
        r"\bpollakiurie\b",
    ],
    "CUTANE": [
        r"\bprurit\b",
        r"\b[eé]ruption(?:s)?\b",
    ],
    "GENERAUX": [
        r"\basth[eé]nie\b",
        r"\bfatigue\b",
        r"\bmalaise\b",
        r"\banorexie\b",
    ],
}


# ============================================================
# 3. HELPERS
# ============================================================

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
    if e.get("page") is not None:
        return e.get("page")
    return e.get("page_number")


def entity_text(e):
    vals = []
    for k in (
        "preuve",
        "name",
        "valeur",
        "libelle",
        "parametre",
        "texte",
        "text",
    ):
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
    for page in doc.get("pages", []) or []:
        out.extend(page.get("entities", []) or [])
    return out


def get_relations(doc):
    if isinstance(doc.get("global_relations"), list):
        return doc["global_relations"]

    out = []
    for page in doc.get("pages", []) or []:
        out.extend(page.get("relations", []) or [])
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
    ta = token_set(a)
    tb = token_set(b)

    if not ta or not tb:
        return 0.0

    return len(ta & tb) / min(len(ta), len(tb))


# ============================================================
# 4. SIGNAL DETECTION
# ============================================================

def detect_symptom_signals(text):
    norm = normalize(text)
    result = {}

    for family, regexes in PATTERNS.items():
        hits = []

        for pattern in regexes:
            for m in re.finditer(pattern, norm, re.IGNORECASE):
                hit = m.group(0)
                if hit not in hits:
                    hits.append(hit)

        if hits:
            result[family] = hits

    return result


# ============================================================
# 5. SAME-PAGE TARGET SEARCH
# ============================================================

def find_same_page_symptom_targets(source, entities, relations):
    src_text = entity_text(source)
    src_norm = normalize(src_text)
    sid = entity_id(source)
    page = entity_page(source)

    targets = []

    for e in entities:
        if entity_type(e) != TARGET_TYPE:
            continue

        if entity_page(e) != page:
            continue

        tgt_text = entity_text(e)
        tgt_norm = normalize(tgt_text)

        containment = bool(
            src_norm
            and tgt_norm
            and (
                tgt_norm in src_norm
                or src_norm in tgt_norm
            )
        )

        overlap = token_overlap(
            src_text,
            tgt_text,
        )

        reliable = (
            containment
            or overlap >= RELIABLE_OVERLAP_THRESHOLD
        )

        rel_exists = any(
            relation_type(r) == RELATION_TYPE
            and relation_source(r) == sid
            and relation_target(r) == entity_id(e)
            for r in relations
        )

        targets.append({
            "entity_id": entity_id(e),
            "page": page,
            "text": tgt_text,
            "containment": containment,
            "token_overlap": round(overlap, 4),
            "reliable": reliable,
            "relation_already_exists": rel_exists,
        })

    targets.sort(
        key=lambda x: (
            x["reliable"],
            x["containment"],
            x["token_overlap"],
        ),
        reverse=True,
    )

    return targets


# ============================================================
# 6. STRENGTH
# ============================================================

def classify_strength(signals, targets):
    reliable_target = any(t["reliable"] for t in targets)
    n_signal_families = len(signals)

    if n_signal_families >= 2:
        return "STRONG"

    if n_signal_families >= 1 and reliable_target:
        return "STRONG"

    if n_signal_families >= 1:
        return "MEDIUM"

    if reliable_target:
        return "WEAK"

    return None


# ============================================================
# 7. MAIN
# ============================================================

def main():
    input_dir = resolve_input_dir()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    json_files = sorted(input_dir.glob("*.json"))

    candidates = []
    skipped_nonclinical = []
    errors = []

    clinical_documents = 0
    total_patient = 0
    total_symptom = 0

    for path in json_files:
        try:
            doc = json.loads(
                path.read_text(encoding="utf-8")
            )

            if not is_clinical_document(doc):
                skipped_nonclinical.append(path.name)
                continue

            clinical_documents += 1

            entities = get_entities(doc)
            relations = get_relations(doc)

            patient_entities = [
                e for e in entities
                if entity_type(e) == SOURCE_TYPE
            ]

            symptom_entities = [
                e for e in entities
                if entity_type(e) == TARGET_TYPE
            ]

            total_patient += len(patient_entities)
            total_symptom += len(symptom_entities)

            for source in patient_entities:
                source_text = entity_text(source)

                signals = detect_symptom_signals(
                    source_text
                )

                targets = find_same_page_symptom_targets(
                    source,
                    entities,
                    relations,
                )

                strength = classify_strength(
                    signals,
                    targets,
                )

                if not strength:
                    continue

                candidates.append({
                    "document": path.name,
                    "pattern": "A6",
                    "subcase": "DONNEE_PATIENT_SYMPTOME",

                    "source_entity": {
                        "entity_id": entity_id(source),
                        "type": SOURCE_TYPE,
                        "page": entity_page(source),
                        "text": source_text,
                    },

                    "detected_symptom_families":
                        list(signals.keys()),

                    "detected_symptom_signals":
                        signals,

                    "same_page_symptom_targets":
                        targets,

                    "same_page_symptom_target_count":
                        len(targets),

                    "strength":
                        strength,

                    "status":
                        "A6_CANDIDATE",
                })

        except Exception as exc:
            errors.append({
                "document": path.name,
                "error": str(exc),
            })

    strengths = Counter(
        c["strength"]
        for c in candidates
    )

    families = Counter()

    for c in candidates:
        for fam in c["detected_symptom_families"]:
            families[fam] += 1

    report = {
        "pattern": "A6",
        "name": "DONNEE_PATIENT + SYMPTOME",
        "relation": RELATION_TYPE,
        "methodological_status":
            "DETECTION_ONLY_NO_CORRECTION",

        "input_directory":
            str(input_dir),

        "summary": {
            "json_files_found":
                len(json_files),

            "clinical_documents_scanned":
                clinical_documents,

            "nonclinical_json_skipped":
                len(skipped_nonclinical),

            "patient_entities_scanned":
                total_patient,

            "existing_symptom_entities":
                total_symptom,

            "a6_candidates":
                len(candidates),

            "weak":
                strengths.get("WEAK", 0),

            "medium":
                strengths.get("MEDIUM", 0),

            "strong":
                strengths.get("STRONG", 0),

            "errors":
                len(errors),
        },

        "signal_family_counts":
            dict(families),

        "candidates":
            candidates,

        "nonclinical_json_skipped":
            skipped_nonclinical,

        "errors":
            errors,
    }

    OUTPUT_JSON.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    fields = [
        "document",
        "source_entity_id",
        "page",
        "source_text",
        "strength",
        "families",
        "same_page_symptom_target_count",
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

        writer = csv.DictWriter(
            f,
            fieldnames=fields,
        )

        writer.writeheader()

        for c in candidates:
            targets = c[
                "same_page_symptom_targets"
            ]

            best = (
                targets[0]
                if targets
                else {}
            )

            writer.writerow({
                "document":
                    c["document"],

                "source_entity_id":
                    c["source_entity"]["entity_id"],

                "page":
                    c["source_entity"]["page"],

                "source_text":
                    c["source_entity"]["text"],

                "strength":
                    c["strength"],

                "families":
                    "; ".join(
                        c["detected_symptom_families"]
                    ),

                "same_page_symptom_target_count":
                    c["same_page_symptom_target_count"],

                "best_target_id":
                    best.get("entity_id", ""),

                "best_target_text":
                    best.get("text", ""),

                "best_target_overlap":
                    best.get("token_overlap", ""),

                "best_target_containment":
                    best.get("containment", ""),

                "relation_already_exists":
                    best.get("relation_already_exists", ""),
            })

    print("=" * 76)
    print("SGCE - PATTERN A6 DETECTION")
    print("=" * 76)
    print(f"Entrée                  : {input_dir}")
    print(f"JSON trouvés            : {len(json_files)}")
    print(f"Documents cliniques     : {clinical_documents}")
    print(f"JSON non cliniques ignorés : {len(skipped_nonclinical)}")
    print(f"DONNEE_PATIENT analysées: {total_patient}")
    print(f"SYMPTOME existants      : {total_symptom}")
    print()
    print(f"Candidats A6            : {len(candidates)}")
    print(f"WEAK                    : {strengths.get('WEAK', 0)}")
    print(f"MEDIUM                  : {strengths.get('MEDIUM', 0)}")
    print(f"STRONG                  : {strengths.get('STRONG', 0)}")
    print(f"Erreurs                 : {len(errors)}")
    print()
    print("Familles de signaux :")

    if families:
        for family, count in families.most_common():
            print(f"  {family:<32} : {count}")
    else:
        print("  Aucun signal détecté.")

    print()
    print(f"Rapport JSON            : {OUTPUT_JSON}")
    print(f"CSV candidats           : {OUTPUT_CSV}")
    print()
    print("Aucun JSON clinique n'a été modifié.")


if __name__ == "__main__":
    main()
