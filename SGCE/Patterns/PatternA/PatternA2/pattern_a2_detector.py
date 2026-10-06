# -*- coding: utf-8 -*-
"""
pattern_a2_detector_v2.py
=========================
SGCE Pattern A2 — Detection only

A2:
COMORBIDITE_ANTECEDENT -> CONTEXTE_ACQUISITION
relation TRACE-Sepsis v1.6: a_pour_contexte_acquisition

Corrections V2:
- exclut automatiquement les fichiers de rapport/manifest/csv JSON non cliniques ;
- ne compte que les JSON possédant une structure clinique ;
- aucune donnée clinique n'est modifiée.
"""

import csv
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

PATTERN_A2_DIR = Path(__file__).resolve().parent
PATTERN_A_DIR = PATTERN_A2_DIR.parent
PATTERNS_DIR = PATTERN_A_DIR.parent
SGCE_DIR = PATTERNS_DIR.parent
BASE_DIR = SGCE_DIR.parent
PATTERN_A1_DIR = PATTERN_A_DIR / "PatternA1"

INPUT_DIR_CANDIDATES = [PATTERN_A1_DIR / "corrected"]
OUTPUT_DIR = PATTERN_A2_DIR / "detection"
OUTPUT_JSON = OUTPUT_DIR / "pattern_a2_detection_report.json"
OUTPUT_CSV = OUTPUT_DIR / "pattern_a2_candidates.csv"

SOURCE_TYPE = "COMORBIDITE_ANTECEDENT"
TARGET_TYPE = "CONTEXTE_ACQUISITION"
RELATION_TYPE = "a_pour_contexte_acquisition"

PATTERNS = {
    "TYPE_ACQUISITION": [
        r"\bcommunautair(?:e|es)?\b",
        r"\bnosocomial(?:e|es|aux)?\b",
        r"\bassoci(?:e|ee|ees|es)\s+aux?\s+soins\b",
        r"\bacquis(?:e|es)?\s+sous\s+ventilation\s+m[eé]canique\b",
        r"\bsous\s+ventilation\s+m[eé]canique\b",
        r"\bpost[\s-]?op[eé]ratoire\b",
        r"\bpost[\s-]?chirurgical(?:e)?\b",
        r"\bind[eé]termin[eé]e?\b",
    ],
    "HOSPITALISATION_PREALABLE": [
        r"\bhospitalisation\s+(?:pr[eé]alable|r[eé]cente)\b",
        r"\b\d+\s*(?:j|jour|jours)\s+d['’]hospitalisation\b",
        r"\b(?:depuis|pendant|durant)\s+\d+\s*(?:j|jour|jours|semaines?|mois)\s+d['’]hospitalisation\b",
    ],
    "EXPOSITION_ANTIBIOTIQUE_RECENTE": [
        r"\bantibioth[eé]rapie\s+r[eé]cente\b",
        r"\bantibiotique(?:s)?\s+r[eé]cent(?:e|s|es)?\b",
        r"\bexposition\s+(?:r[eé]cente\s+)?(?:aux?\s+)?antibiotiques?\b",
        r"\btraitement\s+antibiotique\s+r[eé]cent\b",
        r"\bATB\s+r[eé]cent(?:e|s)?\b",
    ],
    "DISPOSITIF_INVASIF": [
        r"\bdispositif\s+invasif\b",
        r"\bcath[eé]ter(?:s)?\b",
        r"\bvoie\s+veineuse\s+centrale\b",
        r"\bVVC\b",
        r"\bsonde\s+urinaire\b",
        r"\bsondage\s+urinaire\b",
        r"\bventilation\s+m[eé]canique\b",
        r"\bintub(?:ation|e|é|ee|ée)\b",
        r"\btrach[eé]otomi(?:e|s[eé])\b",
    ],
}

AUTHORIZED_ALIASES = {
    "communautaire": ["communautaire"],
    "nosocomiale": ["nosocomiale", "nosocomial"],
    "associee_aux_soins": ["associee aux soins", "associe aux soins"],
    "acquise_sous_ventilation_mecanique": [
        "acquise sous ventilation mecanique",
        "sous ventilation mecanique",
    ],
    "post_operatoire": ["post operatoire", "post-operatoire", "postoperatoire"],
    "indeterminee": ["indeterminee", "indetermine"],
}


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
    """Évite de compter les fichiers de rapport comme documents cliniques."""
    return (
        isinstance(doc, dict)
        and (
            isinstance(doc.get("global_entities"), list)
            or isinstance(doc.get("pages"), list)
        )
    )


def load_clinical_json(path):
    try:
        with path.open("r", encoding="utf-8") as f:
            doc = json.load(f)
        if not is_clinical_document(doc):
            return None
        return doc
    except Exception:
        raise


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


def detect_context_signals(text):
    norm = normalize(text)
    detected = {}
    for family, regexes in PATTERNS.items():
        hits = []
        for pattern in regexes:
            for m in re.finditer(pattern, norm, flags=re.IGNORECASE):
                s = m.group(0).strip()
                if s and s not in hits:
                    hits.append(s)
        if hits:
            detected[family] = hits
    return detected


def acquisition_value_hits(text):
    norm = normalize(text)
    hits = []
    for canonical, forms in AUTHORIZED_ALIASES.items():
        if any(normalize(form) in norm for form in forms):
            hits.append(canonical)
    return hits


def find_same_page_context_targets(source, entities):
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
            src_norm and tgt_norm and
            (tgt_norm in src_norm or src_norm in tgt_norm)
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
        key=lambda x: (x["text_containment"], x["token_overlap"]),
        reverse=True
    )
    return targets


def relation_exists(source_id, target_id, relations):
    return any(
        relation_type(r) == RELATION_TYPE
        and relation_source(r) == source_id
        and relation_target(r) == target_id
        for r in relations
    )


def classify_strength(signal_families, authorized_values, same_page_targets):
    """
    V2 conservative:
    STRONG = >=2 independent context families
             OR explicit context signal + strong textual match to an already
             separated CONTEXTE_ACQUISITION.
    MEDIUM = one explicit family / authorized acquisition value.
    WEAK   = only strong textual proximity with an existing context entity.
    """
    n = len(signal_families)
    reliable_target = any(
        t["text_containment"] or t["token_overlap"] >= 0.60
        for t in same_page_targets
    )

    if n >= 2:
        return "STRONG"
    if (n >= 1 or authorized_values) and reliable_target:
        return "STRONG"
    if n >= 1 or authorized_values:
        return "MEDIUM"
    if reliable_target:
        return "WEAK"
    return None


def detect_document(path, doc):
    entities = get_entities(doc)
    relations = get_relations(doc)

    sources = [e for e in entities if entity_type(e) == SOURCE_TYPE]
    contexts = [e for e in entities if entity_type(e) == TARGET_TYPE]

    candidates = []

    for source in sources:
        text = entity_text(source)
        signals = detect_context_signals(text)
        authorized = acquisition_value_hits(text)
        targets = find_same_page_context_targets(source, entities)

        strength = classify_strength(signals, authorized, targets)
        if strength is None:
            continue

        sid = entity_id(source)
        enriched = []
        for t in targets:
            x = dict(t)
            x["relation_already_exists"] = relation_exists(
                sid, x["entity_id"], relations
            )
            enriched.append(x)

        candidates.append({
            "document": path.name,
            "pattern": "A2",
            "subcase": "COMORBIDITE_ANTECEDENT_CONTEXTE_ACQUISITION",
            "source_entity": {
                "entity_id": sid,
                "type": SOURCE_TYPE,
                "page": entity_page(source),
                "text": text,
            },
            "detected_context_families": list(signals.keys()),
            "detected_context_signals": signals,
            "authorized_type_acquisition_hits": authorized,
            "same_page_context_targets": enriched,
            "same_page_context_target_count": len(enriched),
            "strength": strength,
            "status": "A2_CANDIDATE",
        })

    return len(sources), len(contexts), candidates


def main():
    input_dir = resolve_input_dir()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_json_files = sorted(input_dir.glob("*.json"))
    clinical_files = []
    skipped_nonclinical = []
    load_errors = []

    loaded = {}

    for path in all_json_files:
        try:
            doc = load_clinical_json(path)
            if doc is None:
                skipped_nonclinical.append(path.name)
                continue
            clinical_files.append(path)
            loaded[path] = doc
        except Exception as exc:
            load_errors.append({"document": path.name, "error": str(exc)})

    candidates = []
    document_summaries = []
    total_sources = 0
    total_contexts = 0
    errors = list(load_errors)

    for path in clinical_files:
        try:
            n_src, n_ctx, cands = detect_document(path, loaded[path])
            total_sources += n_src
            total_contexts += n_ctx
            candidates.extend(cands)
            document_summaries.append({
                "document": path.name,
                "comorbidities_scanned": n_src,
                "existing_context_entities": n_ctx,
                "a2_candidates": len(cands),
            })
        except Exception as exc:
            errors.append({"document": path.name, "error": str(exc)})

    strengths = Counter(c["strength"] for c in candidates)
    families = Counter()
    for c in candidates:
        for fam in c["detected_context_families"]:
            families[fam] += 1

    report = {
        "pattern": "A2",
        "name": "COMORBIDITE_ANTECEDENT + CONTEXTE_ACQUISITION",
        "relation": RELATION_TYPE,
        "methodological_status": "DETECTION_ONLY_NO_CORRECTION",
        "input_directory": str(input_dir),
        "summary": {
            "json_files_found": len(all_json_files),
            "clinical_documents_scanned": len(clinical_files),
            "nonclinical_json_skipped": len(skipped_nonclinical),
            "comorbidities_scanned": total_sources,
            "existing_context_entities": total_contexts,
            "a2_candidates": len(candidates),
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
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    fields = [
        "document", "source_entity_id", "page", "source_text", "strength",
        "families", "authorized_type_acquisition_hits",
        "same_page_context_target_count", "best_target_id", "best_target_text",
        "best_target_overlap", "best_target_containment",
        "relation_already_exists",
    ]

    with OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()

        for c in candidates:
            targets = c["same_page_context_targets"]
            best = targets[0] if targets else {}
            w.writerow({
                "document": c["document"],
                "source_entity_id": c["source_entity"]["entity_id"],
                "page": c["source_entity"]["page"],
                "source_text": c["source_entity"]["text"],
                "strength": c["strength"],
                "families": "; ".join(c["detected_context_families"]),
                "authorized_type_acquisition_hits": "; ".join(
                    c["authorized_type_acquisition_hits"]
                ),
                "same_page_context_target_count": c["same_page_context_target_count"],
                "best_target_id": best.get("entity_id", ""),
                "best_target_text": best.get("text", ""),
                "best_target_overlap": best.get("token_overlap", ""),
                "best_target_containment": best.get("text_containment", ""),
                "relation_already_exists": best.get("relation_already_exists", ""),
            })

    print("=" * 76)
    print("SGCE - PATTERN A2 DETECTION V2")
    print("=" * 76)
    print(f"Entrée                  : {input_dir}")
    print(f"JSON trouvés            : {len(all_json_files)}")
    print(f"Documents cliniques     : {len(clinical_files)}")
    print(f"JSON non cliniques ignorés : {len(skipped_nonclinical)}")
    print(f"COMORBIDITE analysées   : {total_sources}")
    print(f"CONTEXTE existants      : {total_contexts}")
    print()
    print(f"Candidats A2            : {len(candidates)}")
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
