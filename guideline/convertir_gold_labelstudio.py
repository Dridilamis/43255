# -*- coding: utf-8 -*-
"""
TRACE - CONVERSION DU GOLD LABEL STUDIO VERS LE FORMAT DE L'EVALUATEUR

Entree : l'export JSON de Label Studio (une tache par page, champs data.document, data.page,
data.text, annotations[0].result).
Sortie : un fichier par dossier, au format lu par les matchers de TRACE
(document, source_file, pages[].entities / relations, global_entities, global_relations).

Le contenu n'est pas modifie : on recopie les entites et relations annotees. Les sorties
contiennent le texte des pages : les garder en local, ne jamais les publier.

Usage (depuis Reduction_hallucinations) :
    python guideline\\convertir_gold_labelstudio.py EXPORT.json  gold_v2_0
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def norm_name(text):
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def convertir_tache(tache):
    data = tache["data"]
    page_no = int(data["page"])
    annotations = tache.get("annotations") or []
    result = annotations[0].get("result", []) if annotations else []
    by_id, entites, relations = {}, [], []
    for r in result:
        if r.get("type") != "labels":
            continue
        v = r["value"]
        nom = re.sub(r"\s+", " ", v["text"]).strip()
        e = {"name": nom, "normalized_name": norm_name(nom), "type": v["labels"][0],
             "page": page_no, "start": v["start"], "end": v["end"]}
        by_id[r["id"]] = e
        entites.append(e)
    for r in result:
        if r.get("type") != "relation" or not r.get("labels"):
            continue
        s, o = by_id.get(r["from_id"]), by_id.get(r["to_id"])
        if not s or not o:
            continue
        relations.append({"subject": s["name"], "subject_normalized": s["normalized_name"],
                          "subject_type": s["type"], "relation": r["labels"][0],
                          "object": o["name"], "object_normalized": o["normalized_name"],
                          "object_type": o["type"], "page": page_no})
    return {"page": page_no, "text": data.get("text", ""), "entities": entites, "relations": relations}


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    export, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    docs = defaultdict(list)
    for tache in json.loads(export.read_text(encoding="utf-8")):
        doc = re.sub(r"_texte_brut$", "", str(tache["data"]["document"]))
        docs[doc].append(convertir_tache(tache))
    n_e = n_r = 0
    for doc, pages in sorted(docs.items()):
        pages.sort(key=lambda p: p["page"])
        ents, rels, vus_e, vus_r = [], [], set(), set()
        for p in pages:
            for e in p["entities"]:
                k = (e["normalized_name"], e["type"])
                if k not in vus_e:
                    vus_e.add(k)
                    ents.append({"name": e["name"], "normalized_name": e["normalized_name"], "type": e["type"]})
            for r in p["relations"]:
                k = (r["subject_normalized"], r["relation"], r["object_normalized"])
                if k not in vus_r:
                    vus_r.add(k)
                    rels.append({k2: v for k2, v in r.items() if k2 != "page"})
            n_e += len(p["entities"])
            n_r += len(p["relations"])
        (out / f"{doc}.json").write_text(json.dumps(
            {"document": doc, "source_file": f"{doc}.pdf", "pages": pages,
             "global_entities": ents, "global_relations": rels}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(docs)} dossiers | {n_e} entites et {n_r} relations (pages) -> {out}")


if __name__ == "__main__":
    main()
