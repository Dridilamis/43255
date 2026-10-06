# -*- coding: utf-8 -*-
"""
pattern_b2_detector.py
======================

SGCE — Pattern B2
Détection exhaustive des chaînes relationnelles A -> B -> C
où l'entité intermédiaire B pourrait être absente.

IMPORTANT
---------
- Détection uniquement : aucun JSON clinique n'est modifié.
- Les chaînes sont générées AUTOMATIQUEMENT depuis les signatures
  verrouillées TRACE-Sepsis v1.6 :
      image(R1) == domaine(R2)
- Toutes les combinaisons structurellement compatibles sont considérées.
- La présence de A et C avec absence de B produit seulement un CANDIDAT B2.
  Elle ne suffit jamais à créer B.
- La validation B2 ultérieure devra exiger un ancrage documentaire explicite.

Entrée clinique attendue :
  ...\PatternB1\pattern_b1_corrected

Guideline attendu :
  Guideline_TRACE_Sepsis_v1.6.json
  (plusieurs emplacements sont essayés automatiquement)

Sorties :
  ...\PatternB2\pattern_b2_detection\pattern_b2_detection_report.json
  ...\PatternB2\pattern_b2_detection\pattern_b2_candidates.csv
  ...\PatternB2\pattern_b2_detection\pattern_b2_chain_catalog.csv
"""

import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


PATTERN_B2_DIR = Path(__file__).resolve().parent
PATTERN_B_DIR = PATTERN_B2_DIR.parent
PATTERNS_DIR = PATTERN_B_DIR.parent
SGCE_DIR = PATTERNS_DIR.parent
BASE_DIR = SGCE_DIR.parent

PATTERN_B1_DIR = PATTERN_B_DIR / "PatternB1"

INPUT_DIR_CANDIDATES = [PATTERN_B1_DIR / "corrected"]

GUIDELINE_CANDIDATES = [
    BASE_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
    BASE_DIR.parent / "Guideline_TRACE_Sepsis_v1.6.json",
    Path.cwd() / "Guideline_TRACE_Sepsis_v1.6.json",
    PATTERN_B2_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
]

OUTPUT_DIR = PATTERN_B2_DIR / "detection"
REPORT_PATH = OUTPUT_DIR / "pattern_b2_detection_report.json"
CSV_PATH = OUTPUT_DIR / "pattern_b2_candidates.csv"
CHAIN_CSV_PATH = OUTPUT_DIR / "pattern_b2_chain_catalog.csv"

TEXT_FIELDS = (
    "name", "nom", "valeur", "libelle", "preuve",
    "parametre", "texte", "text", "surface",
)
TYPE_FIELDS = ("type", "label", "entity_type", "type_entite", "categorie")
ID_FIELDS = ("id", "entity_id", "identifiant", "identifiant_entite")
PAGE_FIELDS = ("page", "page_num", "page_number", "numero_page")


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize_text(value):
    if value is None:
        return ""
    s = str(value).strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s)
    return s


def first_value(d, fields):
    if not isinstance(d, dict):
        return None
    for f in fields:
        v = d.get(f)
        if v is not None and str(v).strip():
            return v
    return None


def entity_type(e):
    v = first_value(e, TYPE_FIELDS)
    return str(v).strip() if v is not None else ""


def entity_id(e):
    v = first_value(e, ID_FIELDS)
    return str(v).strip() if v is not None else ""


def entity_text(e):
    for f in TEXT_FIELDS:
        v = e.get(f) if isinstance(e, dict) else None
        if v is not None and str(v).strip():
            return str(v).strip()
    # Fallback informatif uniquement
    return entity_id(e)


def entity_page(e, fallback=None):
    if not isinstance(e, dict):
        return fallback
    for f in PAGE_FIELDS:
        if f in e and e[f] not in (None, ""):
            try:
                return int(e[f])
            except Exception:
                return str(e[f])
    return fallback


def is_clinical_document(doc):
    return isinstance(doc, dict) and (
        isinstance(doc.get("global_entities"), list)
        or isinstance(doc.get("pages"), list)
    )


def collect_entities(doc):
    """
    Retourne une liste dédupliquée d'entités.
    Priorité aux global_entities; complète avec pages si nécessaire.
    """
    entities = []
    seen = set()

    def add_entity(e, fallback_page=None):
        if not isinstance(e, dict):
            return
        et = entity_type(e)
        eid = entity_id(e)
        txt = normalize_text(entity_text(e))
        pg = entity_page(e, fallback_page)

        # clé robuste contre les structures global/page miroir
        if eid:
            key = ("id", eid)
        else:
            key = ("anon", et, txt, str(pg))

        if key in seen:
            return
        seen.add(key)

        item = dict(e)
        if "_b2_page" not in item:
            item["_b2_page"] = pg
        entities.append(item)

    for e in doc.get("global_entities", []) or []:
        add_entity(e)

    for page in doc.get("pages", []) or []:
        if not isinstance(page, dict):
            continue
        pnum = first_value(page, PAGE_FIELDS)
        if pnum is None:
            pnum = page.get("page_index")
        for key in ("entities", "entites"):
            for e in page.get(key, []) or []:
                add_entity(e, pnum)

    return entities


def resolve_input_dir():
    for p in INPUT_DIR_CANDIDATES:
        if p.exists() and any(p.glob("*.json")):
            return p
    raise FileNotFoundError(
        "Entrée clinique introuvable. Vérifiez PatternB1/pattern_b1_corrected."
    )


def resolve_guideline():
    for p in GUIDELINE_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError(
        "Guideline_TRACE_Sepsis_v1.6.json introuvable. "
        "Placez-le à côté du script ou dans Reduction_hallucinations."
    )


def get_root(guideline):
    if "ontologie_sepsis_graph" in guideline:
        return guideline["ontologie_sepsis_graph"]
    return guideline


def extract_locked_signatures(guideline):
    root = get_root(guideline)

    locked = root.get("signatures_relations_verrouillees_v1_5")
    if isinstance(locked, dict) and locked:
        signatures = {}
        for rel, spec in locked.items():
            if not isinstance(spec, dict):
                continue
            dom = spec.get("domaine")
            img = spec.get("image")
            if dom and img:
                signatures[rel] = {
                    "domaine": dom,
                    "image": img,
                    "groupe": spec.get("groupe", ""),
                }
        return signatures

    # Fallback : section relations
    signatures = {}
    relations = root.get("relations", {})
    for group_name, group in relations.items():
        if not isinstance(group, dict):
            continue
        for rel, spec in group.items():
            if not isinstance(spec, dict):
                continue
            dom = spec.get("domaine")
            img = spec.get("image")
            if dom and img:
                signatures[rel] = {
                    "domaine": dom,
                    "image": img,
                    "groupe": group_name,
                }
    return signatures


def generate_all_two_hop_chains(signatures):
    """
    Toutes les compositions R1,R2 telles que image(R1)=domaine(R2).
    """
    chains = []
    for r1, s1 in signatures.items():
        for r2, s2 in signatures.items():
            if s1["image"] == s2["domaine"]:
                chains.append({
                    "chain_id": f"{r1}__THEN__{r2}",
                    "source_type": s1["domaine"],
                    "relation_1": r1,
                    "middle_type": s1["image"],
                    "relation_2": r2,
                    "target_type": s2["image"],
                    "group_1": s1.get("groupe", ""),
                    "group_2": s2.get("groupe", ""),
                })
    chains.sort(
        key=lambda x: (
            x["source_type"], x["middle_type"],
            x["target_type"], x["relation_1"], x["relation_2"]
        )
    )
    return chains


def same_page(a, c):
    pa = a.get("_b2_page")
    pc = c.get("_b2_page")
    return pa is not None and pc is not None and str(pa) == str(pc)


def candidate_strength(a, c, middle_entities):
    """
    Détection seulement.

    STRONG :
      A et C sont sur la même page ET aucune B dans le document.
    MEDIUM :
      A et C présents dans le document, aucune B dans le document,
      mais pages différentes/inconnues.

    Aucun candidat si une B du type intermédiaire existe déjà dans le document.
    """
    if middle_entities:
        return None
    if same_page(a, c):
        return "STRONG"
    return "MEDIUM"


def compact_entity(e):
    return {
        "id": entity_id(e),
        "type": entity_type(e),
        "text": entity_text(e),
        "page": e.get("_b2_page"),
    }


def main():
    input_dir = resolve_input_dir()
    guideline_path = resolve_guideline()
    guideline = load_json(guideline_path)

    signatures = extract_locked_signatures(guideline)
    if not signatures:
        raise RuntimeError("Aucune signature relationnelle trouvée dans le guideline.")

    chains = generate_all_two_hop_chains(signatures)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Catalogue exhaustif des chaînes
    with CHAIN_CSV_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        fields = [
            "chain_id", "source_type", "relation_1",
            "middle_type", "relation_2", "target_type",
            "group_1", "group_2",
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(chains)

    candidates = []
    errors = []
    nonclinical = []
    docs_clinical = 0
    entities_total = 0

    # Pour éviter une explosion combinatoire dans le rapport,
    # un candidat = chaîne + document + paire A/C.
    for path in sorted(input_dir.glob("*.json")):
        try:
            doc = load_json(path)
            if not is_clinical_document(doc):
                nonclinical.append(path.name)
                continue

            docs_clinical += 1
            entities = collect_entities(doc)
            entities_total += len(entities)

            by_type = defaultdict(list)
            for e in entities:
                et = entity_type(e)
                if et:
                    by_type[et].append(e)

            for chain in chains:
                srcs = by_type.get(chain["source_type"], [])
                mids = by_type.get(chain["middle_type"], [])
                tgts = by_type.get(chain["target_type"], [])

                if not srcs or not tgts:
                    continue

                # B2 : l'entité intermédiaire est absente du document.
                if mids:
                    continue

                for a in srcs:
                    for c in tgts:
                        # Cas A/B/C de même type : éviter de réutiliser exactement
                        # la même entité comme deux positions distinctes.
                        if (
                            chain["source_type"] == chain["target_type"]
                            and entity_id(a)
                            and entity_id(a) == entity_id(c)
                        ):
                            continue

                        strength = candidate_strength(a, c, mids)
                        if not strength:
                            continue

                        candidates.append({
                            "candidate_id": f"B2_{len(candidates)+1:06d}",
                            "document": path.name,
                            "candidate_type": "MISSING_INTERMEDIATE_ENTITY",
                            "strength": strength,
                            "chain_id": chain["chain_id"],
                            "source_type": chain["source_type"],
                            "relation_1": chain["relation_1"],
                            "middle_type_missing": chain["middle_type"],
                            "relation_2": chain["relation_2"],
                            "target_type": chain["target_type"],
                            "source_entity": compact_entity(a),
                            "target_entity": compact_entity(c),
                            "reason": (
                                "A et C présents sur la même page, B absent du document"
                                if strength == "STRONG"
                                else
                                "A et C présents dans le document, B absent du document"
                            ),
                            "requires_document_grounding": True,
                            "safe_to_correct": False,
                        })

        except Exception as exc:
            errors.append({"document": path.name, "error": str(exc)})

    strength_counts = Counter(c["strength"] for c in candidates)
    chain_candidate_counts = Counter(c["chain_id"] for c in candidates)
    middle_counts = Counter(c["middle_type_missing"] for c in candidates)

    report = {
        "pattern": "B2",
        "mode": "DETECTION_ONLY",
        "definition": (
            "Chaîne autorisée A->B->C où A et C sont présents "
            "mais aucune entité B du type intermédiaire n'existe dans le document."
        ),
        "warning": (
            "Un candidat B2 n'est PAS une hallucination confirmée et ne justifie "
            "PAS la création de B sans preuve documentaire explicite."
        ),
        "input_directory": str(input_dir),
        "guideline": str(guideline_path),
        "output_directory": str(OUTPUT_DIR),
        "summary": {
            "authorized_relations": len(signatures),
            "compatible_two_hop_chains": len(chains),
            "clinical_documents": docs_clinical,
            "nonclinical_json_skipped": len(nonclinical),
            "entities_analyzed": entities_total,
            "candidates": len(candidates),
            "strong": strength_counts.get("STRONG", 0),
            "medium": strength_counts.get("MEDIUM", 0),
            "errors": len(errors),
        },
        "signatures": signatures,
        "compatible_chains": chains,
        "candidate_counts_by_chain": dict(chain_candidate_counts),
        "candidate_counts_by_missing_middle_type": dict(middle_counts),
        "candidates": candidates,
        "nonclinical_json_skipped": nonclinical,
        "errors": errors,
    }

    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # CSV aplati
    fields = [
        "candidate_id", "document", "strength",
        "source_type", "relation_1", "middle_type_missing",
        "relation_2", "target_type",
        "source_id", "source_text", "source_page",
        "target_id", "target_text", "target_page",
        "reason",
    ]

    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for c in candidates:
            w.writerow({
                "candidate_id": c["candidate_id"],
                "document": c["document"],
                "strength": c["strength"],
                "source_type": c["source_type"],
                "relation_1": c["relation_1"],
                "middle_type_missing": c["middle_type_missing"],
                "relation_2": c["relation_2"],
                "target_type": c["target_type"],
                "source_id": c["source_entity"]["id"],
                "source_text": c["source_entity"]["text"],
                "source_page": c["source_entity"]["page"],
                "target_id": c["target_entity"]["id"],
                "target_text": c["target_entity"]["text"],
                "target_page": c["target_entity"]["page"],
                "reason": c["reason"],
            })

    print("=" * 82)
    print("SGCE - PATTERN B2 DETECTION")
    print("=" * 82)
    print(f"Entrée clinique          : {input_dir}")
    print(f"Guideline                : {guideline_path}")
    print()
    print(f"Relations autorisées     : {len(signatures)}")
    print(f"Chaînes compatibles A-B-C: {len(chains)}")
    print()
    print(f"Documents cliniques      : {docs_clinical}")
    print(f"JSON non cliniques ignorés : {len(nonclinical)}")
    print(f"Entités analysées        : {entities_total}")
    print()
    print(f"Candidats B2             : {len(candidates)}")
    print(f"STRONG                   : {strength_counts.get('STRONG', 0)}")
    print(f"MEDIUM                   : {strength_counts.get('MEDIUM', 0)}")
    print(f"Erreurs                  : {len(errors)}")
    print()
    print("Types intermédiaires absents les plus fréquents :")
    for typ, n in middle_counts.most_common(15):
        print(f"  {typ:<32}: {n}")
    print()
    print(f"Rapport JSON             : {REPORT_PATH}")
    print(f"CSV candidats            : {CSV_PATH}")
    print(f"Catalogue des chaînes    : {CHAIN_CSV_PATH}")
    print()
    print("Aucun JSON clinique n'a été modifié.")
    print("Les candidats doivent être validés avant toute correction.")


if __name__ == "__main__":
    main()
