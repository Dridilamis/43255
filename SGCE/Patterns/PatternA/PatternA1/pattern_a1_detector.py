# -*- coding: utf-8 -*-
"""
PATTERN A1 DETECTOR V2
TRAITEMENT + POSOLOGIE

Correction principale :
- détecter d'abord les expressions complexes ;
- empêcher qu'une sous-expression soit recomptée.
Ex. "2 g/24h" = RATE uniquement, et non RATE + DOSE.

Aucune correction des JSON cliniques.
"""

import json
import re
from pathlib import Path
from collections import Counter

# ============================================================
# PATHS
# ============================================================

PATTERN_A1_DIR = Path(__file__).resolve().parent
PATTERN_A_DIR = PATTERN_A1_DIR.parent
PATTERNS_DIR = PATTERN_A_DIR.parent
SGCE_DIR = PATTERNS_DIR.parent
BASE_DIR = SGCE_DIR.parent

# Entrée clinique
INPUT_DIR = BASE_DIR / "SortieJson_Postprocessing"

# Sortie de la détection A1
OUTPUT_DIR = PATTERN_A1_DIR / "detection"

# Rapport global utilisé par le validator
GLOBAL_REPORT = OUTPUT_DIR / "pattern_a1_detection_v2_report.json"

# ---------- REGEX ----------

RX_RATE = re.compile(
    r"(?<!\w)\d+(?:[.,]\d+)?\s*(?:mg|g|µg|ug|mcg|ml|mL|UI|ui|IU)"
    r"\s*/\s*(?:h|heure|24\s*h|min|minute)(?!\w)",
    re.I,
)

# Fréquences complexes d'abord
RX_FREQUENCY = re.compile(
    r"(?:"
    r"\b\d+\s*(?:cp|comprim[eé]s?)\s*[x×*]\s*\d+\s*/\s*j\b"
    r"|\b\d+\s*[x×*]\s*/\s*j\b"
    r"|\bx\s*\d+\s*/\s*j\b"
    r"|\b\d+\s*fois\s*(?:/|par)\s*j(?:our)?\b"
    r"|\btoutes?\s+les\s+\d+\s*h(?:eures?)?\b"
    r"|\b\d+\s*/\s*(?:j|jour)\b"
    r")",
    re.I,
)

RX_DURATION = re.compile(
    r"\b(?:pendant|durant|pour)\s+\d+\s*"
    r"(?:j|jour|jours|h|heure|heures|semaine|semaines|mois)\b",
    re.I,
)

RX_DOSE = re.compile(
    r"(?<!\w)\d+(?:[.,]\d+)?\s*"
    r"(?:mg|g|µg|ug|mcg|ml|mL|UI|ui|IU|mmol)(?!\w)",
    re.I,
)

RX_ROUTE = re.compile(
    r"\b(?:IV|I\.V\.|intraveineu(?:x|se)|SC|S\.C\.|"
    r"sous[-\s]?cutan[eé]e?|IM|I\.M\.|intramusculaire|"
    r"per\s+os|orale?|PO|inhal[eé]e?|inhalation|"
    r"n[eé]bulisation)\b",
    re.I,
)

# ---------- HELPERS ----------

def get_type(e):
    return e.get("categorie") or e.get("type") or ""

def get_id(e):
    return e.get("identifiant_entite") or e.get("id")

def get_entities(doc):
    if isinstance(doc.get("global_entities"), list):
        return doc["global_entities"]
    out = []
    for page in doc.get("pages", []) or []:
        out.extend(page.get("entities", []) or [])
    return out

def get_text(e):
    vals = []
    for key in ("preuve", "name", "valeur", "parametre"):
        v = e.get(key)
        if v not in (None, ""):
            v = str(v).strip()
            if v and v not in vals:
                vals.append(v)
    return " | ".join(vals)

def overlaps(span, occupied):
    a, b = span
    return any(a < d and c < b for c, d in occupied)

def collect(regex, text, occupied=None):
    occupied = occupied or []
    found = []
    spans = []
    seen = set()

    for m in regex.finditer(text):
        if overlaps(m.span(), occupied):
            continue
        value = m.group(0).strip()
        key = value.lower()
        if key not in seen:
            seen.add(key)
            found.append(value)
            spans.append(m.span())

    return found, spans

def detect_components(text):
    """
    Priorité :
      1 RATE
      2 FREQUENCY
      3 DURATION
      4 DOSE
      5 ROUTE

    Les spans complexes occupent le texte et empêchent
    leurs sous-expressions d'être comptées à nouveau.
    """
    occupied = []
    components = {}

    for name, regex in (
        ("rate", RX_RATE),
        ("frequency", RX_FREQUENCY),
        ("duration", RX_DURATION),
        ("dose", RX_DOSE),
        ("route", RX_ROUTE),
    ):
        values, spans = collect(regex, text, occupied)
        if values:
            components[name] = values
            occupied.extend(spans)

    return components

def strength(components):
    n = len(components)
    if n >= 3:
        return "STRONG"
    if n == 2:
        return "MEDIUM"
    return "WEAK"

# ---------- DOCUMENT ----------

def process(path):
    with path.open("r", encoding="utf-8") as f:
        doc = json.load(f)

    treatments = [
        e for e in get_entities(doc)
        if get_type(e) == "TRAITEMENT"
    ]

    candidates = []

    for e in treatments:
        text = get_text(e)
        if not text:
            continue

        comp = detect_components(text)
        if not comp:
            continue

        candidates.append({
            "document": path.name,
            "pattern": "A1_TRAITEMENT_POSOLOGIE",
            "status": "CANDIDATE",
            "signal_strength": strength(comp),
            "source_entity": {
                "id": get_id(e),
                "type": get_type(e),
                "name": e.get("name"),
                "preuve": e.get("preuve"),
                "valeur": e.get("valeur"),
                "page": e.get("page"),
            },
            "detection_text": text,
            "detected_components": comp,
            "number_component_types": len(comp),
            "correction": None,
        })

    return len(treatments), candidates

# ---------- MAIN ----------

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(INPUT_DIR.glob("*.json"))

    total_treatments = 0
    all_candidates = []
    docs = []
    errors = []

    print("=" * 76)
    print("SGCE - PATTERN A1 DETECTOR V2")
    print("Correction des sous-matches imbriqués")
    print("=" * 76)
    print(f"Documents trouvés : {len(files)}")
    print()

    for path in files:
        try:
            n_treat, candidates = process(path)
            total_treatments += n_treat
            all_candidates.extend(candidates)

            counts = Counter(c["signal_strength"] for c in candidates)
            docs.append({
                "document": path.name,
                "treatments_analysed": n_treat,
                "candidates": len(candidates),
                "signal_counts": dict(counts),
            })

            out = OUTPUT_DIR / f"{path.stem}_A1_detection_v2.json"
            with out.open("w", encoding="utf-8") as f:
                json.dump({
                    "document": path.name,
                    "treatments_analysed": n_treat,
                    "number_candidates": len(candidates),
                    "signal_counts": dict(counts),
                    "candidates": candidates,
                }, f, ensure_ascii=False, indent=2)

            print(
                f"[OK] {path.name} | TRAITEMENT={n_treat}"
                f" | candidats={len(candidates)}"
                f" | WEAK={counts.get('WEAK',0)}"
                f" | MEDIUM={counts.get('MEDIUM',0)}"
                f" | STRONG={counts.get('STRONG',0)}"
            )

        except Exception as exc:
            errors.append({"document": path.name, "error": str(exc)})
            print(f"[ERREUR] {path.name}: {exc}")

    counts = Counter(c["signal_strength"] for c in all_candidates)

    report = {
        "pattern": "A1_TRAITEMENT_POSOLOGIE",
        "version": "V2_NO_NESTED_SUBMATCH",
        "documents_analysed": len(files),
        "treatments_analysed": total_treatments,
        "total_candidates": len(all_candidates),
        "signal_counts": {
            "WEAK": counts.get("WEAK", 0),
            "MEDIUM": counts.get("MEDIUM", 0),
            "STRONG": counts.get("STRONG", 0),
        },
        "method_note": (
            "Les expressions complexes sont détectées avant leurs "
            "sous-expressions. Exemple: 2 g/24h est RATE seulement, "
            "pas RATE + DOSE."
        ),
        "documents": docs,
        "candidates": all_candidates,
        "errors": errors,
    }

    with GLOBAL_REPORT.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 76)
    print("RÉSUMÉ GLOBAL A1 V2")
    print("=" * 76)
    print(f"Documents analysés : {len(files)}")
    print(f"TRAITEMENT analysés : {total_treatments}")
    print(f"Candidats A1        : {len(all_candidates)}")
    print(f"WEAK                : {counts.get('WEAK',0)}")
    print(f"MEDIUM              : {counts.get('MEDIUM',0)}")
    print(f"STRONG              : {counts.get('STRONG',0)}")
    print(f"Erreurs             : {len(errors)}")
    print()
    print(f"Rapport : {GLOBAL_REPORT}")
    print("Aucun JSON clinique n'a été modifié.")

if __name__ == "__main__":
    main()
