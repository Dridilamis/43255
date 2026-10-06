# -*- coding: utf-8 -*-
"""
pattern_a_detector_all.py
SGCE - DÃ©tecteur global Pattern A (A1-A6)

IMPORTANT
---------
Ce script est un DETECTEUR :
- il ne modifie jamais les JSON Mistral ;
- il ne crÃ©e pas automatiquement d'entitÃ©s ;
- il produit des CANDIDATS Ã  valider avant correction.

Sous-cas :
A1 TRAITEMENT + POSOLOGIE
A2 COMORBIDITE_ANTECEDENT + CONTEXTE_ACQUISITION
A3 IMAGERIE_PROCEDURE + FOYER_INFECTIEUX
A4 IMAGERIE_PROCEDURE + DEFAILLANCE_ORGANE
A5 IMAGERIE_PROCEDURE + COMORBIDITE_ANTECEDENT
A6 DONNEE_PATIENT + SYMPTOME
"""

import json
import re
import unicodedata
from pathlib import Path
from collections import Counter, defaultdict

BASE_DIR = Path(
    r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM"
    r"\Reduction_hallucinations"
)

INPUT_DIR = BASE_DIR / "SortieJson_Postprocessing"
OUTPUT_DIR = BASE_DIR / "pattern_a_all"
GLOBAL_REPORT = OUTPUT_DIR / "pattern_a_global_report.json"

# ------------------------------------------------------------
# Normalisation
# ------------------------------------------------------------

def norm(text):
    text = "" if text is None else str(text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower()).strip()

def entity_type(e):
    return e.get("categorie") or e.get("type") or ""

def entity_id(e):
    return e.get("identifiant_entite") or e.get("id")

def entity_page(e):
    return e.get("page")

def entity_text(e):
    parts = []
    for k in ("preuve", "name", "valeur", "parametre"):
        v = e.get(k)
        if v not in (None, ""):
            s = str(v).strip()
            if s and s not in parts:
                parts.append(s)
    return " | ".join(parts)

def relation_type(r):
    return r.get("type_relation") or r.get("relation") or r.get("type")

def relation_subject(r):
    return r.get("identifiant_entite_sujet") or r.get("from_id")

def relation_object(r):
    return r.get("identifiant_entite_objet") or r.get("to_id")

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

# ------------------------------------------------------------
# A1 : POSOLOGIE
# ------------------------------------------------------------

RX_DOSE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:mg|g|Âµg|mcg|ug|ml|mL|ui|UI|u|mmol)\b",
    re.I,
)
RX_ROUTE = re.compile(
    r"\b(?:IV|I\.V\.|intraveineu(?:x|se)|SC|S\.C\.|sous[- ]cutanee?|"
    r"IM|I\.M\.|intramusculaire|orale?|per os|PO|inhal(?:e|ee|ation)|"
    r"nebulisation)\b",
    re.I,
)
RX_FREQ = re.compile(
    r"\b(?:\d+\s*(?:x|fois)?\s*/\s*(?:j|jour|24h)|"
    r"x\s*\d+\s*/\s*j|\d+\s*/\s*j|"
    r"toutes?\s+les\s+\d+\s*(?:h|heures?)|"
    r"\d+\s*(?:cp|comprime|gouttes?)\s*(?:x|\*)\s*\d+\s*/\s*j)\b",
    re.I,
)
RX_DURATION = re.compile(
    r"\b(?:pendant|durant|pour)\s+\d+\s*(?:j|jours?|h|heures?|semaines?|mois)\b",
    re.I,
)

def detect_a1(text):
    found = {}
    for key, rx in (
        ("dose", RX_DOSE),
        ("route", RX_ROUTE),
        ("frequency", RX_FREQ),
        ("duration", RX_DURATION),
    ):
        m = rx.search(text)
        if m:
            found[key] = m.group(0)
    return found

# ------------------------------------------------------------
# A2 : CONTEXTE_ACQUISITION
#
# Ce sont des INDICES lexicaux explicites, pas des diagnostics.
# Ils servent Ã  proposer un candidat pour validation.
# ------------------------------------------------------------

CONTEXT_PATTERNS = {
    "nosocomial": [
        r"\bnosocomial(?:e)?\b",
        r"\bacquis(?:e)?\s+a\s+l[' ]hopital\b",
        r"\bhospital[- ]acquired\b",
    ],
    "recent_hospitalization": [
        r"\bhospitalis(?:e|ee|ation)\b.{0,35}\b(?:recent|recente|derniers?\s+\d+\s+(?:jours?|mois))\b",
    ],
    "recent_antibiotics": [
        r"\b(?:antibiotherapie|antibiotique)s?\b.{0,35}\b(?:recent|recente|prealable|anterieur)\b",
    ],
    "healthcare_exposure": [
        r"\b(?:EHPAD|maison de retraite|soins a domicile|hemodialyse|dialyse chronique)\b",
    ],
}

def detect_a2(text):
    t = norm(text)
    found = {}
    for label, patterns in CONTEXT_PATTERNS.items():
        for p in patterns:
            m = re.search(p, t, re.I)
            if m:
                found[label] = m.group(0)
                break
    return found

# ------------------------------------------------------------
# A3-A5 : IMAGERIE + cible explicitement dÃ©crite
#
# Ici on cherche des marqueurs textuels EXPLICITES.
# Le dÃ©tecteur ne conclut jamais cliniquement Ã  partir d'une valeur.
# ------------------------------------------------------------

FOYER_PATTERNS = [
    r"\bfoyer(?:\s+infectieux)?\b",
    r"\bpneumopathie\b",
    r"\bpneumonie\b",
    r"\babc[eÃ¨]s\b",
    r"\bcollection(?:\s+infectee?)?\b",
    r"\bpyelonephrite\b",
    r"\bcholangite\b",
]

DEFAILLANCE_PATTERNS = [
    r"\bdefaillance\s+(?:respiratoire|renale|cardiaque|hepatique|neurologique)\b",
    r"\binsuffisance\s+(?:respiratoire|renale|cardiaque|hepatique)\s+aigue\b",
    r"\bdysfonction\s+(?:ventriculaire|cardiaque|renale|hepatique|respiratoire)\b",
    r"\bSDRA\b",
]

COMORBIDITY_PATTERNS = [
    r"\bBPCO\b",
    r"\bemphyseme\b",
    r"\bcirrhose\b",
    r"\bdiabete\b",
    r"\binsuffisance\s+(?:renale|cardiaque|respiratoire)\s+chronique\b",
    r"\bcancer\b",
    r"\bneoplasie\b",
]

def find_explicit(patterns, text):
    t = norm(text)
    hits = []
    for p in patterns:
        for m in re.finditer(p, t, re.I):
            value = m.group(0).strip()
            if value not in hits:
                hits.append(value)
    return hits

# ------------------------------------------------------------
# A6 : DONNEE_PATIENT + SYMPTOME
#
# Lexique initial conservateur. Les rÃ©sultats restent candidats.
# ------------------------------------------------------------

SYMPTOM_PATTERNS = [
    r"\bdyspnee\b",
    r"\bdouleur(?:s)?\s+(?:thoracique|abdominale|lombaire|pelvienne)\b",
    r"\bnausees?\b",
    r"\bvomissements?\b",
    r"\bdiarrhee\b",
    r"\btoux\b",
    r"\bfrissons?\b",
    r"\bcephalees?\b",
    r"\bconfusion\b",
    r"\basthenie\b",
    r"\bmalaise\b",
    r"\bpolypnee\b",
    r"\bdesaturation\b",
    r"\bfievre\b",
]

def detect_symptoms(text):
    return find_explicit(SYMPTOM_PATTERNS, text)

# ------------------------------------------------------------
# VÃ©rification de structure dÃ©jÃ  existante
# ------------------------------------------------------------

RULES = {
    "A1_TRAITEMENT_POSOLOGIE": {
        "source": "TRAITEMENT",
        "target": "POSOLOGIE",
        "relation": "traitement_a_pour_posologie",
        "mode": "DETERMINISTIC",
    },
    "A2_COMORBIDITE_CONTEXTE": {
        "source": "COMORBIDITE_ANTECEDENT",
        "target": "CONTEXTE_ACQUISITION",
        "relation": "a_pour_contexte_acquisition",
        "mode": "CONDITIONAL",
    },
    "A3_IMAGERIE_FOYER": {
        "source": "IMAGERIE_PROCEDURE",
        "target": "FOYER_INFECTIEUX",
        "relation": "imagerie_objective_foyer",
        "mode": "CONDITIONAL",
    },
    "A4_IMAGERIE_DEFAILLANCE": {
        "source": "IMAGERIE_PROCEDURE",
        "target": "DEFAILLANCE_ORGANE",
        "relation": "imagerie_objective_defaillance",
        "mode": "CONDITIONAL",
    },
    "A5_IMAGERIE_COMORBIDITE": {
        "source": "IMAGERIE_PROCEDURE",
        "target": "COMORBIDITE_ANTECEDENT",
        "relation": "imagerie_objective_comorbidite",
        "mode": "CONDITIONAL",
    },
    "A6_PATIENT_SYMPTOME": {
        "source": "DONNEE_PATIENT",
        "target": "SYMPTOME",
        "relation": "presente_symptome",
        "mode": "CONDITIONAL",
    },
}

def outgoing_targets(relations, source_id, rel_type):
    return [
        relation_object(r)
        for r in relations
        if relation_subject(r) == source_id and relation_type(r) == rel_type
    ]

def target_entities_on_page(entities, target_type, page):
    return [
        e for e in entities
        if entity_type(e) == target_type and entity_page(e) == page
    ]

def make_candidate(docname, subcase, source, evidence, detected):
    rule = RULES[subcase]
    return {
        "document": docname,
        "pattern": "A",
        "pattern_name": "COMPOSITE_NON_DECOMPOSE",
        "subcase": subcase,
        "source_entity": {
            "id": entity_id(source),
            "type": entity_type(source),
            "name": source.get("name"),
            "preuve": source.get("preuve"),
            "value": source.get("valeur"),
            "page": entity_page(source),
        },
        "detection_text": evidence,
        "detected_components": detected,
        "expected_structure": {
            "source_type": rule["source"],
            "target_type": rule["target"],
            "relation": rule["relation"],
        },
        "mode": rule["mode"],
        "status": "candidate",
        "correction": None,
    }

# ------------------------------------------------------------
# DÃ©tection par document
# ------------------------------------------------------------

def detect_document(path):
    with path.open("r", encoding="utf-8") as f:
        doc = json.load(f)

    entities = get_entities(doc)
    relations = get_relations(doc)
    candidates = []

    for e in entities:
        etype = entity_type(e)
        eid = entity_id(e)
        page = entity_page(e)
        text = entity_text(e)

        if not eid or not text:
            continue

        # A1
        if etype == "TRAITEMENT":
            components = detect_a1(text)
            if components:
                targets = outgoing_targets(
                    relations, eid,
                    RULES["A1_TRAITEMENT_POSOLOGIE"]["relation"]
                )
                # DÃ©tection conservatrice : mÃªme si une structure existe,
                # on garde l'information pour le validateur.
                c = make_candidate(
                    path.name,
                    "A1_TRAITEMENT_POSOLOGIE",
                    e, text, components
                )
                c["existing_relation_targets"] = targets
                c["number_of_detected_components"] = len(components)
                if len(components) >= 2:
                    c["status"] = "candidate"
                else:
                    c["status"] = "suspected"
                candidates.append(c)

        # A2
        elif etype in {"COMORBIDITE_ANTECEDENT", "COMORBIDITE"}:
            contexts = detect_a2(text)
            if contexts:
                c = make_candidate(
                    path.name,
                    "A2_COMORBIDITE_CONTEXTE",
                    e, text, contexts
                )
                c["existing_relation_targets"] = outgoing_targets(
                    relations, eid,
                    RULES["A2_COMORBIDITE_CONTEXTE"]["relation"]
                )
                c["same_page_target_entities"] = [
                    entity_id(x)
                    for x in target_entities_on_page(
                        entities, "CONTEXTE_ACQUISITION", page
                    )
                ]
                candidates.append(c)

        # A3-A5
        elif etype == "IMAGERIE_PROCEDURE":
            foyer = find_explicit(FOYER_PATTERNS, text)
            if foyer:
                c = make_candidate(
                    path.name, "A3_IMAGERIE_FOYER",
                    e, text, {"explicit_targets": foyer}
                )
                c["existing_relation_targets"] = outgoing_targets(
                    relations, eid,
                    RULES["A3_IMAGERIE_FOYER"]["relation"]
                )
                c["same_page_target_entities"] = [
                    entity_id(x)
                    for x in target_entities_on_page(
                        entities, "FOYER_INFECTIEUX", page
                    )
                ]
                candidates.append(c)

            failures = find_explicit(DEFAILLANCE_PATTERNS, text)
            if failures:
                c = make_candidate(
                    path.name, "A4_IMAGERIE_DEFAILLANCE",
                    e, text, {"explicit_targets": failures}
                )
                c["existing_relation_targets"] = outgoing_targets(
                    relations, eid,
                    RULES["A4_IMAGERIE_DEFAILLANCE"]["relation"]
                )
                c["same_page_target_entities"] = [
                    entity_id(x)
                    for x in target_entities_on_page(
                        entities, "DEFAILLANCE_ORGANE", page
                    )
                ]
                candidates.append(c)

            comorbidities = find_explicit(COMORBIDITY_PATTERNS, text)
            if comorbidities:
                c = make_candidate(
                    path.name, "A5_IMAGERIE_COMORBIDITE",
                    e, text, {"explicit_targets": comorbidities}
                )
                c["existing_relation_targets"] = outgoing_targets(
                    relations, eid,
                    RULES["A5_IMAGERIE_COMORBIDITE"]["relation"]
                )
                c["same_page_target_entities"] = [
                    entity_id(x)
                    for x in target_entities_on_page(
                        entities, "COMORBIDITE_ANTECEDENT", page
                    )
                ]
                candidates.append(c)

        # A6
        elif etype == "DONNEE_PATIENT":
            symptoms = detect_symptoms(text)
            if symptoms:
                c = make_candidate(
                    path.name, "A6_PATIENT_SYMPTOME",
                    e, text, {"explicit_targets": symptoms}
                )
                c["existing_relation_targets"] = outgoing_targets(
                    relations, eid,
                    RULES["A6_PATIENT_SYMPTOME"]["relation"]
                )
                c["same_page_target_entities"] = [
                    entity_id(x)
                    for x in target_entities_on_page(
                        entities, "SYMPTOME", page
                    )
                ]
                candidates.append(c)

    return doc, candidates

# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    files = sorted(INPUT_DIR.glob("*.json"))
    print("=" * 72)
    print("SGCE - PATTERN A GLOBAL DETECTOR (A1-A6)")
    print("=" * 72)
    print(f"EntrÃ©e : {INPUT_DIR}")
    print(f"Sortie : {OUTPUT_DIR}")
    print(f"JSON trouvÃ©s : {len(files)}")
    print()

    all_candidates = []
    doc_summaries = []

    for path in files:
        try:
            doc, candidates = detect_document(path)
            all_candidates.extend(candidates)

            counts = Counter(c["subcase"] for c in candidates)
            doc_summaries.append({
                "document": path.name,
                "number_of_candidates": len(candidates),
                "by_subcase": dict(counts),
            })

            report = {
                "document": path.name,
                "pattern": "A",
                "pattern_name": "COMPOSITE_NON_DECOMPOSE",
                "number_of_candidates": len(candidates),
                "by_subcase": dict(counts),
                "candidates": candidates,
            }

            out = OUTPUT_DIR / f"{path.stem}_pattern_a.json"
            with out.open("w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)

            print(
                f"[OK] {path.name} : {len(candidates)} candidat(s)"
                + (
                    " | " +
                    ", ".join(f"{k}={v}" for k, v in counts.items())
                    if counts else ""
                )
            )

        except Exception as exc:
            print(f"[ERREUR] {path.name}: {exc}")
            doc_summaries.append({
                "document": path.name,
                "error": str(exc),
            })

    counts = Counter(c["subcase"] for c in all_candidates)
    status_counts = Counter(c["status"] for c in all_candidates)

    global_report = {
        "pattern": "A",
        "pattern_name": "COMPOSITE_NON_DECOMPOSE",
        "principle": (
            "Un candidat Pattern A est signalÃ© lorsqu'une entitÃ© source "
            "semble contenir explicitement une information que TRACE-Sepsis "
            "modÃ©lise comme une entitÃ© cible distincte. "
            "La dÃ©tection ne constitue pas une confirmation."
        ),
        "rules": RULES,
        "documents_analysed": len(files),
        "total_candidates": len(all_candidates),
        "counts_by_subcase": dict(counts),
        "counts_by_detector_status": dict(status_counts),
        "documents": doc_summaries,
        "candidates": all_candidates,
    }

    with GLOBAL_REPORT.open("w", encoding="utf-8") as f:
        json.dump(global_report, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 72)
    print("RÃ‰SUMÃ‰ GLOBAL")
    print("=" * 72)
    print(f"Documents analysÃ©s : {len(files)}")
    print(f"Candidats Pattern A : {len(all_candidates)}")
    for subcase in RULES:
        print(f"{subcase:34s}: {counts.get(subcase, 0)}")

    print()
    print(f"Rapport global : {GLOBAL_REPORT}")
    print("Aucun JSON Mistral n'a Ã©tÃ© modifiÃ©.")

if __name__ == "__main__":
    main()

