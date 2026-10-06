# -*- coding: utf-8 -*-
"""
pattern_a3_detector.py
======================

SGCE — Pattern A3 Detection Only

A3:
IMAGERIE_PROCEDURE + FOYER_INFECTIEUX

Relation TRACE-Sepsis:
    IMAGERIE_PROCEDURE
        --imagerie_objective_foyer-->
    FOYER_INFECTIEUX

Objectif
--------
Détecter automatiquement les candidats où une entité IMAGERIE_PROCEDURE
semble contenir ou exprimer directement un foyer infectieux qui devrait
être représenté comme FOYER_INFECTIEUX séparé et relié.

IMPORTANT
---------
- Détection uniquement.
- Aucun JSON clinique n'est modifié.
- Les candidats ne sont PAS encore considérés comme des hallucinations
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

PATTERN_A3_DIR = Path(__file__).resolve().parent
PATTERN_A_DIR = PATTERN_A3_DIR.parent
PATTERNS_DIR = PATTERN_A_DIR.parent
SGCE_DIR = PATTERNS_DIR.parent
BASE_DIR = SGCE_DIR.parent
PATTERN_A2_DIR = PATTERN_A_DIR / "PatternA2"

INPUT_DIR_CANDIDATES = [
    PATTERN_A2_DIR / "corrected",
]

OUTPUT_DIR = PATTERN_A3_DIR / "detection"
OUTPUT_JSON = OUTPUT_DIR / "pattern_a3_detection_report.json"
OUTPUT_CSV = OUTPUT_DIR / "pattern_a3_candidates.csv"

SOURCE_TYPE = "IMAGERIE_PROCEDURE"
TARGET_TYPE = "FOYER_INFECTIEUX"
RELATION_TYPE = "imagerie_objective_foyer"


# ============================================================
# 2. SIGNALS
# ============================================================

# Signaux très orientés "foyer infectieux" observables dans un texte d'imagerie.
# On reste conservateur et textuel : pas d'inférence médicale externe.
PATTERNS = {
    "FOYER_PULMONAIRE": [
        r"\bpneumopathie\b",
        r"\bpneumonie\b",
        r"\bfoyer\s+(?:pulmonaire|parenchymateux)\b",
        r"\bcondensation(?:s)?\s+(?:alv[eé]olaire|pulmonaire)?\b",
        r"\binfiltrat(?:s)?\s+pulmonaire(?:s)?\b",
        r"\babc[eè]s\s+pulmonaire\b",
    ],
    "FOYER_ABDOMINAL": [
        r"\babc[eè]s\s+(?:abdominal|intra[-\s]?abdominal)\b",
        r"\bcollection\s+(?:abdominale|intra[-\s]?abdominale)\b",
        r"\bfoyer\s+(?:abdominal|digestif)\b",
        r"\bp[eé]ritonit(?:e|es)\b",
    ],
    "FOYER_URINAIRE": [
        r"\bpy[eé]lon[eé]phrite\b",
        r"\bfoyer\s+urinaire\b",
        r"\binfection\s+urinaire\b",
    ],
    "FOYER_CUTANE_TISSUS_MOUS": [
        r"\babc[eè]s\b",
        r"\bcollection\s+(?:infect[eé]e|suppur[eé]e)\b",
        r"\bcellulite\b",
        r"\bfasciite\b",
    ],
    "FOYER_OS_ARTICULATION": [
        r"\bost[eé]ite\b",
        r"\bost[eé]omy[eé]lite\b",
        r"\barthrite\s+septique\b",
        r"\bspondylodiscite\b",
    ],
    "FOYER_ENDOVASCULAIRE": [
        r"\bendocardite\b",
        r"\bv[eé]g[eé]tation(?:s)?\b",
    ],
    "FOYER_INFECTIEUX_GENERIQUE": [
        r"\bfoyer\s+infectieux\b",
        r"\bcollection\s+infect[eé]e\b",
        r"\bprocessus\s+infectieux\b",
        r"\babc[eè]s\b",
        r"\bsuppuration\b",
    ],
}

# Signaux qui indiquent qu'on est bien dans un contexte d'imagerie/procédure.
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
    r"\bthorac(?:ique|o[-\s]?abdomino[-\s]?pelvien)\b",
    r"\babdomino[-\s]?pelvien\b",
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
    values = []
    for key in (
        "preuve", "name", "valeur", "libelle",
        "parametre", "texte", "text"
    ):
        value = e.get(key)
        if value not in (None, ""):
            value = str(value).strip()
            if value and value not in values:
                values.append(value)
    return " | ".join(values)


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

    result = []
    for page in doc.get("pages", []) or []:
        result.extend(page.get("entities", []) or [])
    return result


def get_relations(doc):
    if isinstance(doc.get("global_relations"), list):
        return doc["global_relations"]

    result = []
    for page in doc.get("pages", []) or []:
        result.extend(page.get("relations", []) or [])
    return result


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
        t
        for t in re.findall(r"[a-z0-9]+", normalize(text))
        if len(t) >= 3
    }


def token_overlap(a, b):
    ta, tb = token_set(a), token_set(b)

    if not ta or not tb:
        return 0.0

    return len(ta & tb) / min(len(ta), len(tb))


# ============================================================
# 4. SIGNAL DETECTION
# ============================================================

def detect_focus_signals(text):
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

    for pattern in IMAGING_HINTS:
        if re.search(pattern, norm, flags=re.IGNORECASE):
            return True

    return False


# ============================================================
# 5. TARGET MATCHING
# ============================================================

def find_same_page_focus_targets(source, entities):
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


def relation_exists(source_id, target_id, relations):
    return any(
        relation_type(r) == RELATION_TYPE
        and relation_source(r) == source_id
        and relation_target(r) == target_id
        for r in relations
    )


# ============================================================
# 6. STRENGTH
# ============================================================

def classify_strength(signals, same_page_targets, imaging_hint):
    """
    Candidate evidence only.

    STRONG
      - >=2 independent foyer families
      OR
      - explicit foyer signal + reliable existing FOYER_INFECTIEUX target

    MEDIUM
      - >=1 explicit foyer family

    WEAK
      - only reliable nested/same-page target

    imaging_hint is informative only because source is already typed
    IMAGERIE_PROCEDURE.
    """
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

    focus_entities = [
        e for e in entities
        if entity_type(e) == TARGET_TYPE
    ]

    candidates = []

    for source in imaging_entities:
        text = entity_text(source)

        signals = detect_focus_signals(text)

        targets = find_same_page_focus_targets(
            source,
            entities,
        )

        imaging_hint = has_imaging_hint(text)

        strength = classify_strength(
            signals,
            targets,
            imaging_hint,
        )

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
            "pattern": "A3",
            "subcase": "IMAGERIE_PROCEDURE_FOYER_INFECTIEUX",
            "source_entity": {
                "entity_id": sid,
                "type": SOURCE_TYPE,
                "page": entity_page(source),
                "text": text,
            },
            "detected_focus_families": list(signals.keys()),
            "detected_focus_signals": signals,
            "imaging_hint_present": imaging_hint,
            "same_page_focus_targets": enriched_targets,
            "same_page_focus_target_count": len(enriched_targets),
            "strength": strength,
            "status": "A3_CANDIDATE",
        })

    return (
        len(imaging_entities),
        len(focus_entities),
        candidates,
    )


# ============================================================
# 8. MAIN
# ============================================================

def main():
    input_dir = resolve_input_dir()

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    all_json_files = sorted(
        input_dir.glob("*.json")
    )

    clinical_files = []
    skipped_nonclinical = []
    load_errors = []
    loaded = {}

    for path in all_json_files:
        try:
            with path.open(
                "r",
                encoding="utf-8",
            ) as f:
                doc = json.load(f)

            if not is_clinical_document(doc):
                skipped_nonclinical.append(
                    path.name
                )
                continue

            clinical_files.append(path)
            loaded[path] = doc

        except Exception as exc:
            load_errors.append({
                "document": path.name,
                "error": str(exc),
            })

    candidates = []
    document_summaries = []

    total_imaging = 0
    total_focus = 0
    errors = list(load_errors)

    for path in clinical_files:
        try:
            n_img, n_focus, cands = detect_document(
                path,
                loaded[path],
            )

            total_imaging += n_img
            total_focus += n_focus
            candidates.extend(cands)

            document_summaries.append({
                "document": path.name,
                "imaging_entities_scanned": n_img,
                "focus_entities_existing": n_focus,
                "a3_candidates": len(cands),
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
        for fam in c["detected_focus_families"]:
            families[fam] += 1

    report = {
        "pattern": "A3",
        "name": (
            "IMAGERIE_PROCEDURE + "
            "FOYER_INFECTIEUX"
        ),
        "relation": RELATION_TYPE,
        "methodological_status": (
            "DETECTION_ONLY_NO_CORRECTION"
        ),
        "input_directory": str(input_dir),

        "summary": {
            "json_files_found": len(all_json_files),
            "clinical_documents_scanned": len(clinical_files),
            "nonclinical_json_skipped": len(skipped_nonclinical),
            "imaging_entities_scanned": total_imaging,
            "existing_focus_entities": total_focus,
            "a3_candidates": len(candidates),
            "weak": strengths.get("WEAK", 0),
            "medium": strengths.get("MEDIUM", 0),
            "strong": strengths.get("STRONG", 0),
            "errors": len(errors),
        },

        "nonclinical_json_skipped": skipped_nonclinical,
        "signal_family_counts": dict(families),
        "documents": document_summaries,
        "candidates": candidates,
        "errors": errors,
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
        "imaging_hint_present",
        "same_page_focus_target_count",
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
                "same_page_focus_targets"
            ]

            best = (
                targets[0]
                if targets
                else {}
            )

            writer.writerow({
                "document": c["document"],
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
                        c[
                            "detected_focus_families"
                        ]
                    ),
                "imaging_hint_present":
                    c["imaging_hint_present"],
                "same_page_focus_target_count":
                    c[
                        "same_page_focus_target_count"
                    ],
                "best_target_id":
                    best.get("entity_id", ""),
                "best_target_text":
                    best.get("text", ""),
                "best_target_overlap":
                    best.get("token_overlap", ""),
                "best_target_containment":
                    best.get(
                        "text_containment",
                        "",
                    ),
                "relation_already_exists":
                    best.get(
                        "relation_already_exists",
                        "",
                    ),
            })

    print("=" * 76)
    print("SGCE - PATTERN A3 DETECTION")
    print("=" * 76)
    print(f"Entrée                  : {input_dir}")
    print(f"JSON trouvés            : {len(all_json_files)}")
    print(f"Documents cliniques     : {len(clinical_files)}")
    print(f"JSON non cliniques ignorés : {len(skipped_nonclinical)}")
    print(f"IMAGERIE analysées      : {total_imaging}")
    print(f"FOYER existants         : {total_focus}")
    print()
    print(f"Candidats A3            : {len(candidates)}")
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

    if skipped_nonclinical:
        print("JSON non cliniques ignorés :")
        for name in skipped_nonclinical:
            print(f"  - {name}")
        print()

    print(f"Rapport JSON            : {OUTPUT_JSON}")
    print(f"CSV candidats           : {OUTPUT_CSV}")
    print()
    print("Aucun JSON clinique n'a été modifié.")


if __name__ == "__main__":
    main()
