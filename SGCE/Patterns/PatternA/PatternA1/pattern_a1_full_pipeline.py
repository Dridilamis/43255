# -*- coding: utf-8 -*-
"""
pattern_a1_full_pipeline.py

SGCE Pattern A1 : TRAITEMENT -> POSOLOGIE

Pipeline complet :
1) Détection large des TRAITEMENT contenant des composants posologiques.
2) Validation prudente contre les POSOLOGIE existantes.
3) Classification :
   - ALREADY_CORRECT
   - MISSING_RELATION
   - CONFIRMED_PATTERN_A
   - AMBIGUOUS
4) Correction automatique UNIQUEMENT :
   - MISSING_RELATION -> LINK
   - CONFIRMED_PATTERN_A -> SPLIT
5) Post-validation des fichiers corrigés.

IMPORTANT :
- Les originaux ne sont jamais modifiés.
- Une route seule / dose seule / fréquence seule ne déclenche jamais un SPLIT.
- Le matching n'est jamais fondé uniquement sur une dose/fréquence/route partagée.
"""

import copy
import json
import re
import shutil
import unicodedata
from collections import Counter
from pathlib import Path

PATTERN_A1_DIR = Path(__file__).resolve().parent
PATTERN_A_DIR = PATTERN_A1_DIR.parent
PATTERNS_DIR = PATTERN_A_DIR.parent
SGCE_DIR = PATTERNS_DIR.parent
BASE_DIR = SGCE_DIR.parent

INPUT_DIR = BASE_DIR / "SortieJson_Postprocessing"
OUT_DIR = PATTERN_A1_DIR / "full_pipeline_corrected"
REPORT = OUT_DIR / "pattern_a1_full_report.json"

REL_TYPE = "traitement_a_pour_posologie"

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def norm(s):
    s = "" if s is None else str(s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("’", "'")
    return re.sub(r"\s+", " ", s).strip()

def etype(e):
    return e.get("categorie") or e.get("type") or ""

def eid(e):
    return e.get("identifiant_entite") or e.get("id")

def page(e):
    return e.get("page")

def rtype(r):
    return r.get("type_relation") or r.get("relation") or r.get("type")

def rsrc(r):
    return r.get("identifiant_entite_sujet") or r.get("from_id")

def rtgt(r):
    return r.get("identifiant_entite_objet") or r.get("to_id")

def text_of(e):
    vals = []
    for k in ("preuve", "name", "valeur", "parametre"):
        v = e.get(k)
        if v not in (None, ""):
            v = str(v).strip()
            if v and v not in vals:
                vals.append(v)
    return " | ".join(vals)

def medication_text(e):
    # Le nom est prioritaire pour l'ancrage médicament.
    return str(e.get("name") or e.get("valeur") or "").strip()

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

def find_entity(doc, x):
    for e in get_entities(doc):
        if eid(e) == x:
            return e
    return None

def find_page_obj(doc, pageno):
    for p in doc.get("pages", []) or []:
        if p.get("page") == pageno or p.get("page_number") == pageno:
            return p
    return None

# ------------------------------------------------------------------
# Composants posologiques
# ------------------------------------------------------------------

RX = {
    "dose": re.compile(
        r"(?<!\w)\d+(?:[.,]\d+)?\s*(?:mg|g|µg|mcg|ug|ml|ui|iu|mmol)(?!\w)", re.I
    ),
    "frequency": re.compile(
        r"\b(?:\d+\s*(?:x|fois)?\s*/\s*(?:j|jour|24h)|"
        r"\d+\s*/\s*(?:h|heure)|"
        r"x\s*\d+\s*/\s*j|"
        r"\d+\s*(?:cp|comprime|ampoule|amp|gouttes?)\s*(?:x|\*)\s*\d+\s*/\s*j|"
        r"toutes?\s+les\s+\d+\s*(?:h|heures?))\b", re.I
    ),
    "route": re.compile(
        r"\b(?:iv|i\.v\.|intraveineu(?:x|se)|sc|s\.c\.|sous[- ]cutanee?|"
        r"im|i\.m\.|intramusculaire|per os|orale?|po|inhal(?:e|ee|ation)|"
        r"nebulisation)\b", re.I
    ),
    "duration": re.compile(
        r"\b(?:pendant|durant|pour)\s+\d+\s*(?:j|jours?|h|heures?|semaines?|mois)\b",
        re.I
    ),
    "rate": re.compile(
        r"(?<!\w)\d+(?:[.,]\d+)?\s*(?:mg|g|µg|mcg|ug|ml)\s*/\s*(?:h|heure|24h|min)(?!\w)",
        re.I
    ),
}

def components(text):
    out = {}
    for k, rx in RX.items():
        vals = []
        for m in rx.finditer(text):
            v = m.group(0).strip()
            if norm(v) not in [norm(x) for x in vals]:
                vals.append(v)
        if vals:
            out[k] = vals
    return out

def flattened(comp):
    return [x for vals in comp.values() for x in vals]

def strong_for_split(comp):
    # Au moins 2 familles explicites. Une route seule, une dose seule, etc. = jamais SPLIT.
    return len(comp.keys()) >= 2

# ------------------------------------------------------------------
# Matching médicament -> POSOLOGIE
# ------------------------------------------------------------------

STOP = {
    "traitement","par","avec","sous","de","du","des","le","la","les","un","une",
    "iv","sc","im","po","per","os","orale","intraveineux","intraveineuse"
}

def tokens(s):
    return {
        x for x in re.findall(r"[a-z0-9]+", norm(s))
        if len(x) >= 3 and x not in STOP and not x.isdigit()
    }

def med_anchor_score(treatment, posology):
    med = tokens(medication_text(treatment))
    if not med:
        return 0.0

    ptxt = tokens(text_of(posology))
    if not ptxt:
        return 0.0

    inter = med & ptxt
    return len(inter) / max(1, len(med))

def component_score(comp, posology):
    ptxt = norm(text_of(posology))
    vals = flattened(comp)
    if not vals:
        return 0.0
    hits = sum(1 for v in vals if norm(v) in ptxt)
    return hits / len(vals)

def same_page_score(a, b):
    return 1.0 if page(a) is not None and page(a) == page(b) else 0.0

def proof_overlap_score(a, b):
    ta, tb = tokens(text_of(a)), tokens(text_of(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(1, min(len(ta), len(tb)))

def match_posology(treatment, posologies, comp):
    ranked = []
    for p in posologies:
        anchor = med_anchor_score(treatment, p)
        cs = component_score(comp, p)
        sp = same_page_score(treatment, p)
        ov = proof_overlap_score(treatment, p)

        # Même logique prudente que le validateur corrigé :
        # l'identité du médicament doit être ancrée.
        final = 0.50 * anchor + 0.25 * cs + 0.15 * sp + 0.10 * ov

        ranked.append({
            "entity": p,
            "target_id": eid(p),
            "target_text": text_of(p),
            "medication_anchor": round(anchor, 4),
            "component_score": round(cs, 4),
            "same_page": round(sp, 4),
            "proof_overlap": round(ov, 4),
            "final_score": round(final, 4),
            "reliable": anchor >= 0.60 and final >= 0.65,
        })
    ranked.sort(key=lambda x: x["final_score"], reverse=True)
    return ranked

def relation_exists(relations, source, target):
    return any(
        rtype(r) == REL_TYPE and rsrc(r) == source and rtgt(r) == target
        for r in relations
    )

# ------------------------------------------------------------------
# IDs / insertion
# ------------------------------------------------------------------

def next_local_id(doc, pageno, kind):
    # kind E ou R
    prefix = f"P{pageno}_{kind}"
    ids = []
    items = get_entities(doc) if kind == "E" else get_relations(doc)
    getter = eid if kind == "E" else lambda r: r.get("identifiant_relation") or r.get("id")
    for item in items:
        x = getter(item)
        if isinstance(x, str) and x.startswith(prefix):
            m = re.search(r"(\d+)$", x)
            if m:
                ids.append(int(m.group(1)))
    return f"{prefix}{max(ids, default=0)+1:03d}"

def add_entity(doc, ent):
    doc.setdefault("global_entities", []).append(ent)
    p = find_page_obj(doc, ent.get("page"))
    if p is not None:
        p.setdefault("entities", []).append(copy.deepcopy(ent))

def add_relation(doc, rel, pageno):
    doc.setdefault("global_relations", []).append(rel)
    p = find_page_obj(doc, pageno)
    if p is not None:
        p.setdefault("relations", []).append(copy.deepcopy(rel))

def make_posology(source, comp, new_id):
    value = " ".join(flattened(comp))
    return {
        "identifiant_entite": new_id,
        "categorie": "POSOLOGIE",
        "name": value,
        "preuve": value,
        "page": page(source),
        "_sgce_generated": True,
        "_sgce_pattern": "A1_TRAITEMENT_POSOLOGIE",
        "_sgce_operation": "SPLIT",
        "_sgce_source_entity": eid(source),
    }

def make_relation(source_id, target_id, pageno, rid, operation):
    return {
        "identifiant_relation": rid,
        "type_relation": REL_TYPE,
        "identifiant_entite_sujet": source_id,
        "identifiant_entite_objet": target_id,
        "page": pageno,
        "_sgce_generated": True,
        "_sgce_pattern": "A1_TRAITEMENT_POSOLOGIE",
        "_sgce_operation": operation,
    }

# ------------------------------------------------------------------
# Validation + correction
# ------------------------------------------------------------------

def process_document(path):
    with path.open("r", encoding="utf-8") as f:
        original = json.load(f)

    doc = copy.deepcopy(original)
    entities = get_entities(original)
    relations = get_relations(original)
    treatments = [e for e in entities if etype(e) == "TRAITEMENT"]
    posologies = [e for e in entities if etype(e) == "POSOLOGIE"]

    candidates = []
    applied = []

    for t in treatments:
        txt = text_of(t)
        comp = components(txt)
        if not comp:
            continue

        ranked = match_posology(t, posologies, comp)
        reliable = [x for x in ranked if x["reliable"]]
        best = reliable[0] if reliable else None

        existing_targets = [
            rtgt(r) for r in relations
            if rtype(r) == REL_TYPE and rsrc(r) == eid(t)
        ]

        record = {
            "source_id": eid(t),
            "source_name": t.get("name"),
            "source_text": txt,
            "page": page(t),
            "detected_components": comp,
            "existing_relation_targets": existing_targets,
            "best_match": (
                {k:v for k,v in best.items() if k != "entity"} if best else None
            ),
            "status": None,
            "action": None,
        }

        # 1. Relation correcte déjà présente vers un match fiable.
        if best and best["target_id"] in existing_targets:
            record["status"] = "ALREADY_CORRECT"

        # 2. Cible fiable existe, relation absente.
        elif best:
            record["status"] = "MISSING_RELATION"
            record["action"] = "LINK"

            # Correction
            if not relation_exists(get_relations(doc), eid(t), best["target_id"]):
                rid = next_local_id(doc, page(t), "R")
                rel = make_relation(eid(t), best["target_id"], page(t), rid, "LINK")
                add_relation(doc, rel, page(t))
                applied.append({
                    "operation": "LINK",
                    "source_id": eid(t),
                    "target_id": best["target_id"],
                    "relation_id": rid,
                })

        # 3. Aucun match fiable : SPLIT seulement si >=2 familles explicites.
        elif strong_for_split(comp):
            record["status"] = "CONFIRMED_PATTERN_A"
            record["action"] = "SPLIT"

            new_eid = next_local_id(doc, page(t), "E")
            new_pos = make_posology(t, comp, new_eid)
            add_entity(doc, new_pos)

            rid = next_local_id(doc, page(t), "R")
            rel = make_relation(eid(t), new_eid, page(t), rid, "SPLIT")
            add_relation(doc, rel, page(t))

            applied.append({
                "operation": "SPLIT",
                "source_id": eid(t),
                "target_id": new_eid,
                "relation_id": rid,
                "created_posology": new_pos.get("name"),
            })

        # 4. Signal faible : aucune correction.
        else:
            record["status"] = "AMBIGUOUS"

        candidates.append(record)

    # provenance
    if applied:
        doc["sgce_pattern_a1_full_correction"] = {
            "operations_applied": len(applied),
            "operations": applied,
        }

    return original, doc, candidates, applied

# ------------------------------------------------------------------
# Post-validation
# ------------------------------------------------------------------

def post_validate(doc, operations):
    errors = []
    entities = get_entities(doc)
    relations = get_relations(doc)
    entity_ids = [eid(e) for e in entities if eid(e)]
    relation_ids = [
        r.get("identifiant_relation") or r.get("id")
        for r in relations
        if r.get("identifiant_relation") or r.get("id")
    ]

    if len(entity_ids) != len(set(entity_ids)):
        errors.append("DUPLICATE_ENTITY_ID")
    if len(relation_ids) != len(set(relation_ids)):
        errors.append("DUPLICATE_RELATION_ID")

    seen = set()
    for r in relations:
        key = (rtype(r), rsrc(r), rtgt(r))
        if key in seen:
            errors.append(f"DUPLICATE_RELATION:{key}")
        seen.add(key)

        if rsrc(r) and rsrc(r) not in entity_ids:
            errors.append(f"INVALID_RELATION_SOURCE:{rsrc(r)}")
        if rtgt(r) and rtgt(r) not in entity_ids:
            errors.append(f"INVALID_RELATION_TARGET:{rtgt(r)}")

    for op in operations:
        s, t = op["source_id"], op["target_id"]
        if s not in entity_ids:
            errors.append(f"APPLIED_SOURCE_MISSING:{s}")
        if t not in entity_ids:
            errors.append(f"APPLIED_TARGET_MISSING:{t}")
        if not relation_exists(relations, s, t):
            errors.append(f"APPLIED_RELATION_MISSING:{s}->{t}")
        te = next((e for e in entities if eid(e) == t), None)
        if not te or etype(te) != "POSOLOGIE":
            errors.append(f"TARGET_NOT_POSOLOGIE:{t}")

    return sorted(set(errors))

# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(INPUT_DIR.glob("*.json"))

    print("=" * 78)
    print("SGCE - PATTERN A1 FULL PIPELINE")
    print("=" * 78)
    print(f"Entrée : {INPUT_DIR}")
    print(f"Sortie : {OUT_DIR}")
    print(f"Documents : {len(files)}")
    print()

    all_candidates = []
    all_operations = []
    doc_reports = []
    global_errors = []

    for path in files:
        try:
            original, corrected, candidates, operations = process_document(path)
            post_errors = post_validate(corrected, operations)

            out = OUT_DIR / path.name
            with out.open("w", encoding="utf-8") as f:
                json.dump(corrected, f, ensure_ascii=False, indent=2)

            counts = Counter(x["status"] for x in candidates)
            doc_reports.append({
                "document": path.name,
                "candidates": len(candidates),
                "status_counts": dict(counts),
                "operations": operations,
                "post_validation_errors": post_errors,
            })

            for c in candidates:
                c["document"] = path.name
                all_candidates.append(c)
            for op in operations:
                x = dict(op)
                x["document"] = path.name
                all_operations.append(x)

            if post_errors:
                global_errors.extend(
                    {"document": path.name, "error": x} for x in post_errors
                )

            print(
                f"[OK] {path.name} | cand={len(candidates)} "
                f"| correct={counts.get('ALREADY_CORRECT',0)} "
                f"| link={counts.get('MISSING_RELATION',0)} "
                f"| split={counts.get('CONFIRMED_PATTERN_A',0)} "
                f"| ambiguous={counts.get('AMBIGUOUS',0)} "
                f"| post_errors={len(post_errors)}"
            )

        except Exception as exc:
            print(f"[ERREUR] {path.name}: {exc}")
            global_errors.append({"document": path.name, "error": str(exc)})

    status = Counter(x["status"] for x in all_candidates)
    ops = Counter(x["operation"] for x in all_operations)

    report = {
        "pattern": "A1_TRAITEMENT_POSOLOGIE",
        "warning": (
            "Les candidats ne sont pas des hallucinations confirmées. "
            "La correction automatique est limitée aux cas satisfaisant "
            "les règles déterministes du script."
        ),
        "documents_analysed": len(files),
        "total_candidates": len(all_candidates),
        "status_counts": dict(status),
        "operations_applied": len(all_operations),
        "operation_counts": dict(ops),
        "post_validation_errors": global_errors,
        "documents": doc_reports,
        "candidates": all_candidates,
    }

    with REPORT.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 78)
    print("RÉSUMÉ GLOBAL")
    print("=" * 78)
    print(f"Documents analysés       : {len(files)}")
    print(f"Candidats larges         : {len(all_candidates)}")
    print(f"ALREADY_CORRECT          : {status.get('ALREADY_CORRECT',0)}")
    print(f"MISSING_RELATION -> LINK : {status.get('MISSING_RELATION',0)}")
    print(f"CONFIRMED_A1 -> SPLIT    : {status.get('CONFIRMED_PATTERN_A',0)}")
    print(f"AMBIGUOUS (non modifiés) : {status.get('AMBIGUOUS',0)}")
    print(f"Corrections appliquées   : {len(all_operations)}")
    print(f"  LINK                   : {ops.get('LINK',0)}")
    print(f"  SPLIT                  : {ops.get('SPLIT',0)}")
    print(f"Erreurs post-validation  : {len(global_errors)}")
    print(f"Rapport                   : {REPORT}")
    print()
    print("Les fichiers originaux n'ont pas été modifiés.")

if __name__ == "__main__":
    main()
