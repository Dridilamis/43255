# -*- coding: utf-8 -*-
"""
ETAGE 4 - REPARATION STRUCTURELLE (SGCE)
Seule responsabilite : reparer la forme du graphe avec le SGCE existant, inchange :
  Patterns A1-A6 -> B1-B2 -> C -> D -> Relation Repair -> Orphan Resolution -> Multi-Agent.

Le dossier SGCE du projet n'est JAMAIS modifie. Cet etage :
  1. copie SGCE dans un atelier temporaire (dossier systeme, chemin court pour Windows),
     avec la structure <...>/OCR vers LLM/Reduction_hallucinations/ attendue par ses scripts ;
  2. y place la sortie de l'Etage 3 comme SortieJson_Postprocessing, le texte brut et le
     guideline (le vrai fichier s'il existe, sinon les signatures v1.6 figees) ;
  3. corrige les chemins codes en dur DANS LA COPIE (run_sgce.py --patch-paths --apply) ;
  4. lance run_sgce.py, puis recupere SGCE/MultiAgent/corrected ;
  5. marque trace_v2.sgce = CREEE pour chaque relation ajoutee par SGCE.

Usage : python etage4_sgce.py [--garder-atelier]
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from trace_lib import config as C
from trace_lib import ontologie
from trace_lib.documents import Graph, trace
from trace_lib.etage import run_stage

EXCLUDE = {"MultiAgent a supp", "F1_optimizer_audit", "__pycache__"}


def _copy_sgce(dst):
    def ignore(_, names):
        return [n for n in names if n in EXCLUDE]
    shutil.copytree(C.SGCE_DIR, dst, ignore=ignore)


def _write_guideline(base, red):
    real = next((p for p in C.GUIDELINE_CANDIDATES if p.exists()), None)
    for target in (base / "Guideline_TRACE_Sepsis_v1.6.json", red / "Guideline_TRACE_Sepsis_v1.6.json"):
        if real:
            shutil.copy2(real, target)
        else:
            target.write_text(json.dumps({"ontologie_sepsis_graph": {
                "signatures_relations_verrouillees_v1_5": ontologie.load_signatures()}},
                ensure_ascii=False, indent=1), encoding="utf-8")
    return str(real) if real else "signatures figees (ontologie_signatures_v1.6.json)"


def _run(cmd, cwd, log):
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(f"\n$ {' '.join(map(str, cmd))}\n")
        fh.flush()
        rc = subprocess.run(cmd, cwd=str(cwd), stdout=fh, stderr=subprocess.STDOUT,
                            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}).returncode
    return rc


def run_sgce(in_dir, keep=False):
    atelier = Path(tempfile.mkdtemp(prefix="tv2_sgce_"))
    base = atelier / "OCR vers LLM"
    red = base / "Reduction_hallucinations"
    red.mkdir(parents=True)
    log = C.OUT / "04_sgce.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("", encoding="utf-8")
    try:
        print(f"Atelier SGCE : {atelier}")
        _copy_sgce(red / "SGCE")
        inp = red / "SortieJson_Postprocessing"
        inp.mkdir()
        for p in Path(in_dir).glob("*.json"):
            if not p.name.startswith("_rapport"):
                shutil.copy2(p, inp / p.name)
        shutil.copytree(C.RAW_TEXT_DIR, red / C.RAW_TEXT_DIR.name)
        guideline = _write_guideline(base, red)
        print(f"Guideline : {guideline}")
        if _run([sys.executable, "run_sgce.py", "--patch-paths", "--apply"], red / "SGCE", log):
            raise RuntimeError(f"correction des chemins SGCE en echec (journal : {log})")
        print("SGCE en cours (Patterns A->D, Relation Repair, Orphan Resolution, Multi-Agent) ...")
        if _run([sys.executable, "run_sgce.py"], red / "SGCE", log):
            raise RuntimeError(f"SGCE en echec (journal : {log})")
        out = C.OUT / "_sgce_brut"
        if out.exists():
            shutil.rmtree(out)
        shutil.copytree(red / "SGCE" / "MultiAgent" / "corrected", out)
        return out, guideline
    finally:
        if keep:
            print(f"Atelier conserve : {atelier}")
        else:
            shutil.rmtree(atelier, ignore_errors=True)


def process(path, data):
    c = Counter()
    for rel in Graph(data).relations:
        if "ancrage" not in rel.get("trace_v2", {}):
            trace(rel, "sgce", "CREEE")
            c["relations_creees_par_sgce"] += 1
    c["relations_sortie"] = len(data["global_relations"])
    c["entites_sortie"] = len(data["global_entities"])
    return c


def main(in_dir=None, keep=False):
    in_dir = Path(in_dir or C.STAGE_DIRS[3])
    sgce_out, guideline = run_sgce(in_dir, keep)
    n_in = sum(len(json.loads(p.read_text(encoding="utf-8-sig")).get("global_relations", []))
               for p in in_dir.glob("img*.json"))
    run_stage(4, "REPARATION STRUCTURELLE (SGCE)", sgce_out, process,
              extra_report=lambda: {"guideline": guideline, "relations_entree": n_in,
                                    "journal": str(C.OUT / "04_sgce.log")})
    shutil.rmtree(sgce_out, ignore_errors=True)
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sys.exit(main(args[0] if args else None, "--garder-atelier" in sys.argv))
