# -*- coding: utf-8 -*-
"""
TRACE -> représentation canonique d'évaluation.

Cette conversion reproduit la REPRESENTATION du gold_to_canonic.py :
- document/source_file/pages/global_entities/global_relations
- entités : name, normalized_name, type
- relations : subject, subject_normalized, subject_type,
              relation, object, object_normalized, object_type
- déduplication globale par les mêmes clés conceptuelles.

IMPORTANT :
- aucun accès au Gold Standard ;
- aucune correction clinique guidée par le Gold ;
- aucune suppression selon le score F1 ;
- résolution déterministe des endpoints de relations via les IDs TRACE.
"""
import json, os, re, sys, unicodedata
from pathlib import Path

def normalize_text(text):
    if text is None:
        return ""
    text = str(text)
    text = unicodedata.normalize("NFKC", text)
    text = text.lower()
    text = text.replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def clean_document_name(name):
    if not name:
        return "document_inconnu"
    name = os.path.basename(str(name))
    name = re.sub(r"\.(pdf|json|txt)$", "", name, flags=re.I)
    for suffix in ["_texte_brut", "_text_brut", "_texte", "_text"]:
        if name.lower().endswith(suffix):
            name = name[:-len(suffix)]
    return name.strip()

def entity_id(e):
    return str(e.get("identifiant_entite") or e.get("id") or e.get("entity_id") or "").strip()

def entity_name(e):
    # Priorité au champ canonique déjà produit par le pipeline.
    for k in ("name", "mention", "text", "preuve"):
        v = e.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    # Dernier fallback déterministe pour anciens JSON TRACE.
    p = str(e.get("parametre") or "").strip()
    v = "" if e.get("valeur") is None else str(e.get("valeur")).strip()
    u = "" if e.get("unite") is None else str(e.get("unite")).strip()
    return " ".join(x for x in (p, v, u) if x).strip()

def entity_type(e):
    return str(e.get("type") or e.get("categorie") or e.get("label") or "").strip()

def page_number(e, default=None):
    for k in ("page", "page_number", "numero_page"):
        if e.get(k) is not None:
            return e.get(k)
    return default

def clinical_json(d):
    return isinstance(d, dict) and (
        isinstance(d.get("global_entities"), list)
        or isinstance(d.get("global_relations"), list)
        or isinstance(d.get("pages"), list)
    )

def collect_entities(doc):
    # Prefer global_entities because this is the official document-level TRACE representation.
    ge = doc.get("global_entities")
    if isinstance(ge, list) and ge:
        return [(e, page_number(e)) for e in ge if isinstance(e, dict)]
    result = []
    for p in doc.get("pages", []) or []:
        pn = p.get("page", 0)
        for e in (p.get("entities") or p.get("entites") or []):
            if isinstance(e, dict):
                result.append((e, page_number(e, pn)))
    return result

def collect_relations(doc):
    gr = doc.get("global_relations")
    if isinstance(gr, list) and gr:
        return [(r, page_number(r)) for r in gr if isinstance(r, dict)]
    result = []
    for p in doc.get("pages", []) or []:
        pn = p.get("page", 0)
        for r in (p.get("relations") or []):
            if isinstance(r, dict):
                result.append((r, page_number(r, pn)))
    return result

def convert_one(doc, fallback_name):
    raw_source = doc.get("source_file") or doc.get("document") or fallback_name
    document_name = clean_document_name(raw_source)

    raw_entities = collect_entities(doc)
    idmap = {}
    canonical_entities_all = []

    for e, pg in raw_entities:
        name = entity_name(e)
        typ = entity_type(e)
        if not name or not typ:
            continue
        ce = {
            "name": name,
            "normalized_name": normalize_text(name),
            "type": typ,
        }
        if pg is not None:
            ce["page"] = pg
        eid = entity_id(e)
        if eid and eid not in idmap:
            idmap[eid] = ce
        canonical_entities_all.append(ce)

    raw_relations = collect_relations(doc)
    canonical_relations_all = []
    unresolved = 0

    for r, pg in raw_relations:
        rid_s = str(r.get("identifiant_entite_sujet") or r.get("subject_id") or "").strip()
        rid_o = str(r.get("identifiant_entite_objet") or r.get("object_id") or "").strip()
        se = idmap.get(rid_s)
        oe = idmap.get(rid_o)

        subject = str(r.get("subject") or r.get("sujet") or "").strip()
        obj = str(r.get("object") or r.get("objet") or "").strip()
        stype = str(r.get("subject_type") or r.get("type_sujet") or "").strip()
        otype = str(r.get("object_type") or r.get("type_objet") or "").strip()

        if se:
            subject, stype = se["name"], se["type"]
        if oe:
            obj, otype = oe["name"], oe["type"]

        reltype = str(r.get("relation") or r.get("type_relation") or r.get("label") or "").strip()

        if not subject or not obj or not reltype:
            unresolved += 1
            continue

        cr = {
            "subject": subject,
            "subject_normalized": normalize_text(subject),
            "subject_type": stype,
            "relation": reltype,
            "object": obj,
            "object_normalized": normalize_text(obj),
            "object_type": otype,
        }
        if pg is not None:
            cr["page"] = pg
        canonical_relations_all.append(cr)

    # Same global entity key as gold_to_canonic.py.
    global_entities, seen_e = [], set()
    for e in canonical_entities_all:
        key = (e["normalized_name"], e["type"])
        if key not in seen_e:
            seen_e.add(key)
            global_entities.append({
                "name": e["name"],
                "normalized_name": e["normalized_name"],
                "type": e["type"],
            })

    # Same global relation key as gold_to_canonic.py.
    global_relations, seen_r = [], set()
    for r in canonical_relations_all:
        key = (
            r["subject_normalized"], r["subject_type"], r["relation"],
            r["object_normalized"], r["object_type"]
        )
        if key not in seen_r:
            seen_r.add(key)
            global_relations.append({
                "subject": r["subject"],
                "subject_normalized": r["subject_normalized"],
                "subject_type": r["subject_type"],
                "relation": r["relation"],
                "object": r["object"],
                "object_normalized": r["object_normalized"],
                "object_type": r["object_type"],
            })

    # Pages are retained only when page information is available.
    pages = {}
    for e in canonical_entities_all:
        if "page" in e:
            pages.setdefault(e["page"], {"page": e["page"], "text": "", "entities": [], "relations": []})
            pages[e["page"]]["entities"].append(e)
    for r in canonical_relations_all:
        if "page" in r:
            pages.setdefault(r["page"], {"page": r["page"], "text": "", "entities": [], "relations": []})
            pages[r["page"]]["relations"].append(r)

    result = {
        "document": document_name,
        "source_file": f"{document_name}.pdf",
        "pages": list(pages.values()),
        "global_entities": global_entities,
        "global_relations": global_relations,
    }
    return result, unresolved

def main():
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python TRACE_to_canonical.py INPUT_DIR OUTPUT_DIR")
    inp, out = Path(sys.argv[1]), Path(sys.argv[2])
    if not inp.is_dir():
        raise SystemExit(f"Entrée introuvable : {inp}")
    out.mkdir(parents=True, exist_ok=True)

    docs = entities = relations = unresolved = ignored = 0
    for p in sorted(inp.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception:
            ignored += 1
            continue
        if not clinical_json(d):
            ignored += 1
            continue
        c, u = convert_one(d, p.stem)
        target = out / f"{c['document']}.json"
        target.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
        docs += 1
        entities += len(c["global_entities"])
        relations += len(c["global_relations"])
        unresolved += u

    print("="*80)
    print("TRACE -> CANONICAL EVALUATION FORMAT")
    print("="*80)
    print("Documents :", docs)
    print("Entités globales :", entities)
    print("Relations globales :", relations)
    print("Relations non résolues/ignorées :", unresolved)
    print("JSON non cliniques ignorés :", ignored)
    print("Sortie :", out)

if __name__ == "__main__":
    main()
