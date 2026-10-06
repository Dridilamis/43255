# -*- coding: utf-8 -*-
"""TRACE / SGCE - Orphan Relation conservative final post-validation."""
import json, hashlib
from pathlib import Path

ORPHAN_DIR=Path(__file__).resolve().parent
BEFORE_DIR=ORPHAN_DIR/"safe_corrected"
AFTER_DIR=ORPHAN_DIR/"corrected"
ROUTING_REPORT=AFTER_DIR/"orphan_relation_residual_routing_report.json"
QUEUE_FILE=ORPHAN_DIR/"outputs"/"orphan_relation_unresolved_queue.json"
POST_DIR=ORPHAN_DIR/"post_validation"
POST_REPORT=POST_DIR/"orphan_relation_final_post_validation_report.json"

def load_json(p):
    with p.open("r",encoding="utf-8") as f:return json.load(f)
def save_json(p,d):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf-8")
def eid(e): return e.get("identifiant_entite") or e.get("id") or e.get("entity_id")
def rs(r): return r.get("identifiant_entite_sujet") or r.get("from_id") or r.get("subject_id") or r.get("source")
def rt(r): return r.get("identifiant_entite_objet") or r.get("to_id") or r.get("object_id") or r.get("target")
def ents(d):
    if isinstance(d.get("global_entities"),list):return d["global_entities"]
    return [e for p in d.get("pages",[]) or [] for e in (p.get("entities",[]) or [])]
def rels(d):
    if isinstance(d.get("global_relations"),list):return d["global_relations"]
    return [r for p in d.get("pages",[]) or [] for r in (p.get("relations",[]) or [])]
def orphan_count(d):
    ids={str(eid(e)) for e in ents(d) if eid(e) is not None}
    return sum(1 for r in rels(d) if str(rs(r)) not in ids or str(rt(r)) not in ids)
def clinical_files(folder):
    out={}
    for p in folder.glob("*.json"):
        if p.name.endswith("_report.json"):continue
        try:
            d=load_json(p)
            if isinstance(d,dict) and (isinstance(d.get("global_entities"),list) or isinstance(d.get("pages"),list)):
                out[p.name]=d
        except Exception:pass
    return out

def main():
    if not BEFORE_DIR.exists() or not AFTER_DIR.exists():
        raise FileNotFoundError("Entrée/sortie Orphan Resolution introuvable.")
    b,a=clinical_files(BEFORE_DIR),clinical_files(AFTER_DIR)
    before_orphans=sum(orphan_count(d) for d in b.values())
    after_orphans=sum(orphan_count(d) for d in a.values())
    queue=load_json(QUEUE_FILE) if QUEUE_FILE.exists() else {}
    routed=len(queue.get("candidates",[]))
    missing=sorted(set(b)-set(a)); extra=sorted(set(a)-set(b))
    changed=[]
    for n in sorted(set(b)&set(a)):
        # JSON semantic equality: router must not alter safe_corrected documents.
        if b[n] != a[n]: changed.append(n)

    controls={
        "all_documents_preserved": not missing and not extra,
        "residual_orphan_count_preserved": before_orphans==after_orphans,
        "all_residual_orphans_routed": routed==after_orphans,
        "no_clinical_mutation_by_residual_router": len(changed)==0,
        "no_residual_orphan_deleted_before_multi_agent": after_orphans==before_orphans,
    }
    status="PASS" if all(controls.values()) else "FAIL"
    report={
        "stage":"ORPHAN_RELATION_FINAL_POST_VALIDATION",
        "status":status,
        "before_directory":str(BEFORE_DIR),
        "after_directory":str(AFTER_DIR),
        "summary":{
            "documents_before":len(b),"documents_after":len(a),
            "orphan_relations_before":before_orphans,
            "orphan_relations_after":after_orphans,
            "unresolved_relations_routed_to_multi_agent":routed,
            "documents_changed_by_residual_router":len(changed),
            "missing_documents":len(missing),"extra_documents":len(extra),
        },
        "controls":controls,
        "changed_documents":changed,
        "missing_documents":missing,
        "extra_documents":extra,
    }
    save_json(POST_REPORT,report)

    print("="*112)
    print("TRACE / SGCE - ORPHAN RELATION FINAL POST-VALIDATION")
    print("="*112)
    print(f"Documents AVANT                    : {len(b)}")
    print(f"Documents APRES                    : {len(a)}")
    print(f"Relations orphelines AVANT         : {before_orphans}")
    print(f"Relations orphelines APRES         : {after_orphans}")
    print(f"Résiduelles routées Multi-Agent    : {routed}")
    print(f"Docs modifiés par routeur résiduel : {len(changed)}")
    print()
    print("CONTROLES")
    print("-"*112)
    for k,v in controls.items(): print(f"{k:<60}: {'PASS' if v else 'FAIL'}")
    print()
    print(f"STATUT FINAL ORPHAN RELATION       : {status}")
    print(f"Rapport                            : {POST_REPORT}")
    print()
    print("Aucune relation REVIEW n'est supprimée avant le Multi-Agent.")

if __name__=="__main__":
    main()
