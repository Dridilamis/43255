# -*- coding: utf-8 -*-
"""Squelette commun d'un etage : lire l'etage precedent, traiter chaque document, ecrire
la sortie et un rapport. Les JSON non cliniques (rapports, manifestes) ne sont pas propages."""
import sys
import time
from collections import Counter

from . import config as C
from .documents import is_clinical, iter_documents, prepare_output, write_document, write_json

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def run_stage(num, title, in_dir, process, out_dir=None, extra_report=None):
    """`process(path, data) -> Counter` modifie `data` sur place et rend ses compteurs."""
    out_dir = prepare_output(out_dir or C.STAGE_DIRS[num])
    print("=" * 100)
    print(f"TRACE v2 - ETAGE {num} - {title}")
    print("=" * 100)
    print(f"Entree : {in_dir}")
    print(f"Sortie : {out_dir}")
    t0 = time.perf_counter()
    total, per_doc, n_docs, skipped = Counter(), {}, 0, []
    for path, data in iter_documents(in_dir):
        if not is_clinical(data):
            skipped.append(path.name)
            continue
        counts = process(path, data) or Counter()
        write_document(out_dir, path, data)
        total.update(counts)
        per_doc[path.name.split("_trace_")[0]] = dict(counts)
        n_docs += 1
    report = {"etage": num, "titre": title, "entree": str(in_dir), "sortie": str(out_dir),
              "documents": n_docs, "json_non_cliniques_ignores": skipped, "gold_utilise": False,
              "compteurs": dict(total), "par_document": per_doc}
    if extra_report:
        report.update(extra_report())
    write_json(out_dir / f"_rapport_etage_{num}.json", report)
    print(f"Documents : {n_docs}  ({len(skipped)} JSON non cliniques ignores)")
    for k, v in sorted(total.items()):
        print(f"  {k:40} {v}")
    print(f"ETAGE {num} : PASS ({time.perf_counter() - t0:.0f} s)")
    return report
