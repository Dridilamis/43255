# -*- coding: utf-8 -*-
import csv, json
from collections import Counter
from pathlib import Path

PATTERN_D_DIR = Path(__file__).resolve().parent
PATTERNS_DIR = PATTERN_D_DIR.parent
SGCE_DIR = PATTERNS_DIR.parent
BASE_DIR = SGCE_DIR.parent

PATTERN_C_DIR = PATTERNS_DIR / "PatternC"
INPUT_DIR = PATTERN_C_DIR / "corrected"

GUIDELINE_CANDIDATES = [
    BASE_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
    BASE_DIR.parent / "Guideline_TRACE_Sepsis_v1.6.json",
    Path.cwd() / "Guideline_TRACE_Sepsis_v1.6.json",
    PATTERN_D_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
]

OUTPUT_DIR = PATTERN_D_DIR / "audit"
OUTPUT_JSON = OUTPUT_DIR / "pattern_d_anomaly_audit_report.json"
ANOMALIES_CSV = OUTPUT_DIR / "pattern_d_anomalies.csv"
SUMMARY_TYPE_CSV = OUTPUT_DIR / "pattern_d_summary_by_type.csv"
SUMMARY_REL_CSV = OUTPUT_DIR / "pattern_d_summary_by_relation.csv"


def load_json(p):
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_guideline():
    for p in GUIDELINE_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError("Guideline_TRACE_Sepsis_v1.6.json introuvable.")


def is_clinical(doc):
    return isinstance(doc, dict) and (
        isinstance(doc.get("global_entities"), list)
        or isinstance(doc.get("pages"), list)
    )


def eid(e): return e.get("identifiant_entite") or e.get("id") or e.get("entity_id")
def etype(e): return e.get("categorie") or e.get("type") or ""
def rid(r): return r.get("identifiant_relation") or r.get("id") or r.get("relation_id")
def rtype(r): return r.get("type_relation") or r.get("relation") or r.get("type") or ""
def rsrc(r): return r.get("identifiant_entite_sujet") or r.get("from_id") or r.get("subject_id")
def rtgt(r): return r.get("identifiant_entite_objet") or r.get("to_id") or r.get("object_id")


def entities(doc):
    if isinstance(doc.get("global_entities"), list):
        return doc["global_entities"]
    out = []
    for p in doc.get("pages", []) or []:
        out += p.get("entities", []) or []
    return out


def relations(doc):
    if isinstance(doc.get("global_relations"), list):
        return doc["global_relations"]
    out = []
    for p in doc.get("pages", []) or []:
        out += p.get("relations", []) or []
    return out


def locked_signatures(guideline):
    root = guideline.get("ontologie_sepsis_graph", guideline)
    locked = root.get("signatures_relations_verrouillees_v1_5", {})
    out = {}
    for name, spec in locked.items():
        if isinstance(spec, dict) and spec.get("domaine") and spec.get("image"):
            out[name] = (spec["domaine"], spec["image"])
    return out


def audit_doc(name, doc, sigs):
    ents = entities(doc)
    rels = relations(doc)
    out = []

    ec = Counter(eid(e) for e in ents if eid(e))
    rc = Counter(rid(r) for r in rels if rid(r))
    emap = {eid(e): e for e in ents if eid(e)}

    for x, n in ec.items():
        if n > 1:
            out.append({"document":name,"anomaly_type":"DUPLICATE_ENTITY_ID","relation_type":"","relation_id":"","source_id":x,"source_type_actual":etype(emap.get(x,{})),"source_type_expected":"","target_id":"","target_type_actual":"","target_type_expected":"","details":f"{n} occurrences"})

    for x, n in rc.items():
        if n > 1:
            out.append({"document":name,"anomaly_type":"DUPLICATE_RELATION_ID","relation_type":"","relation_id":x,"source_id":"","source_type_actual":"","source_type_expected":"","target_id":"","target_type_actual":"","target_type_expected":"","details":f"{n} occurrences"})

    for r in rels:
        rrid, typ, s, t = rid(r), rtype(r), rsrc(r), rtgt(r)
        se, te = emap.get(s), emap.get(t)

        if s and se is None:
            out.append({"document":name,"anomaly_type":"ORPHAN_RELATION_SOURCE","relation_type":typ,"relation_id":rrid,"source_id":s,"source_type_actual":"","source_type_expected":sigs.get(typ,("",""))[0] if typ in sigs else "","target_id":t,"target_type_actual":etype(te) if te else "","target_type_expected":sigs.get(typ,("",""))[1] if typ in sigs else "","details":"source absente"})

        if t and te is None:
            out.append({"document":name,"anomaly_type":"ORPHAN_RELATION_TARGET","relation_type":typ,"relation_id":rrid,"source_id":s,"source_type_actual":etype(se) if se else "","source_type_expected":sigs.get(typ,("",""))[0] if typ in sigs else "","target_id":t,"target_type_actual":"","target_type_expected":sigs.get(typ,("",""))[1] if typ in sigs else "","details":"cible absente"})

        if typ and typ not in sigs:
            out.append({"document":name,"anomaly_type":"UNAUTHORIZED_RELATION_TYPE","relation_type":typ,"relation_id":rrid,"source_id":s,"source_type_actual":etype(se) if se else "","source_type_expected":"","target_id":t,"target_type_actual":etype(te) if te else "","target_type_expected":"","details":"relation non autorisée"})
            continue

        if typ in sigs:
            exp_s, exp_t = sigs[typ]
            if se is not None and etype(se) != exp_s:
                out.append({"document":name,"anomaly_type":"INVALID_RELATION_SOURCE_TYPE","relation_type":typ,"relation_id":rrid,"source_id":s,"source_type_actual":etype(se),"source_type_expected":exp_s,"target_id":t,"target_type_actual":etype(te) if te else "","target_type_expected":exp_t,"details":"mauvais type source"})
            if te is not None and etype(te) != exp_t:
                out.append({"document":name,"anomaly_type":"INVALID_RELATION_TARGET_TYPE","relation_type":typ,"relation_id":rrid,"source_id":s,"source_type_actual":etype(se) if se else "","source_type_expected":exp_s,"target_id":t,"target_type_actual":etype(te),"target_type_expected":exp_t,"details":"mauvais type cible"})
    return out


def main():
    if not INPUT_DIR.exists():
        raise FileNotFoundError(f"Entrée Pattern C introuvable : {INPUT_DIR}")

    gpath = resolve_guideline()
    sigs = locked_signatures(load_json(gpath))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_anoms, errors = [], []
    docs = ents_n = rels_n = 0

    for p in sorted(INPUT_DIR.glob("*.json")):
        if p.name == "pattern_c_correction_report.json":
            continue
        try:
            doc = load_json(p)
            if not is_clinical(doc):
                continue
            docs += 1
            ents_n += len(entities(doc))
            rels_n += len(relations(doc))
            all_anoms += audit_doc(p.name, doc, sigs)
        except Exception as e:
            errors.append({"document":p.name,"error":str(e)})

    by_type = Counter(a["anomaly_type"] for a in all_anoms)
    by_rel = Counter(a["relation_type"] or "<NONE>" for a in all_anoms)

    signature_mismatch = by_type["INVALID_RELATION_SOURCE_TYPE"] + by_type["INVALID_RELATION_TARGET_TYPE"]
    orphan = by_type["ORPHAN_RELATION_SOURCE"] + by_type["ORPHAN_RELATION_TARGET"]
    unauthorized = by_type["UNAUTHORIZED_RELATION_TYPE"]
    duplicate = by_type["DUPLICATE_ENTITY_ID"] + by_type["DUPLICATE_RELATION_ID"]

    families = {
        "DOMAIN_RANGE_MISMATCH": signature_mismatch,
        "ORPHAN_ENDPOINT": orphan,
        "UNAUTHORIZED_RELATION": unauthorized,
        "DUPLICATE_STRUCTURE": duplicate,
    }
    winner = max(families, key=families.get) if families else "NONE"

    report = {
        "stage":"PRE_PATTERN_D_ANOMALY_AUDIT",
        "input_directory":str(INPUT_DIR),
        "guideline":str(gpath),
        "summary":{
            "clinical_documents":docs,
            "entities_analyzed":ents_n,
            "relations_analyzed":rels_n,
            "locked_signatures_loaded":len(sigs),
            "total_anomalies":len(all_anoms),
            "errors":len(errors),
        },
        "anomaly_counts_by_type":dict(by_type),
        "anomaly_counts_by_relation":dict(by_rel),
        "pattern_d_recommendation":{
            "recommended_family":winner,
            "family_counts":families,
        },
        "anomalies":all_anoms,
        "errors":errors,
    }

    OUTPUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    fields = ["document","anomaly_type","relation_type","relation_id","source_id","source_type_actual","source_type_expected","target_id","target_type_actual","target_type_expected","details"]
    with ANOMALIES_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(all_anoms)

    with SUMMARY_TYPE_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["anomaly_type","count"])
        w.writeheader()
        for k,v in by_type.most_common():
            w.writerow({"anomaly_type":k,"count":v})

    with SUMMARY_REL_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["relation_type","count"])
        w.writeheader()
        for k,v in by_rel.most_common():
            w.writerow({"relation_type":k,"count":v})

    print("="*88)
    print("SGCE - PRE-PATTERN-D ANOMALY AUDIT")
    print("="*88)
    print(f"Entrée clinique                : {INPUT_DIR}")
    print(f"Guideline                      : {gpath}")
    print()
    print(f"Documents cliniques            : {docs}")
    print(f"Entités analysées              : {ents_n}")
    print(f"Relations analysées            : {rels_n}")
    print(f"Signatures TRACE chargées      : {len(sigs)}")
    print()
    print(f"Anomalies totales              : {len(all_anoms)}")
    print(f"Erreurs                        : {len(errors)}")
    print()
    print("ANOMALIES PAR TYPE")
    print("-"*88)
    for k,v in by_type.most_common():
        print(f"{k:<42}: {v}")
    print()
    print("RECOMMANDATION PATTERN D")
    print("-"*88)
    print(f"Famille recommandée            : {winner}")
    print(f"Répartition familles           : {families}")
    print()
    print(f"Rapport JSON                   : {OUTPUT_JSON}")
    print(f"CSV anomalies                  : {ANOMALIES_CSV}")
    print(f"CSV résumé par type            : {SUMMARY_TYPE_CSV}")
    print(f"CSV résumé par relation        : {SUMMARY_REL_CSV}")
    print()
    print("Aucun JSON clinique n'a été modifié.")


if __name__ == "__main__":
    main()
