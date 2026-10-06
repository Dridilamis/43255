# -*- coding: utf-8 -*-
"""
run_pipeline_propre.py  -  TRACE : repartir d'une base PROPRE, de bout en bout

Probleme corrige
----------------
SortieJson_Postprocessing contient des relations ajoutees par un post-traitement qui a
consulte le gold (V6.9b-k : champs *_gold_guided, _v69e_gold_subject, type_inference "dev_*").
Ta propre note le dit : "V6.9c-k est Gold-guided sur ce DEV". Les F1 mesures depuis cette
entree ne sont donc pas une estimation sur des documents nouveaux.

Ce que fait ce script (une seule commande)
------------------------------------------
 1. Verifie que les 2 correctifs deja appliques sont en place
    (relation_repair sans REPLACE_RELATION ; Etage 3 qui lit SGCE).
 2. Construit SortieJson_Postprocessing_PROPRE = l'entree SANS les relations guidees par le
    gold (l'original n'est jamais modifie ; ses SHA-256 sont verifies avant/apres).
 3. Echange temporairement les deux dossiers (renommages, rien n'est supprime).
 4. Relance : SGCE (Etage 2) -> Etages 3 a 8 -> ablation F1 -> precision par niveau de confiance.
 5. Remet TOUJOURS ton dossier d'origine en place, meme en cas d'erreur.

Usage (depuis le dossier Reduction_hallucinations) :
    python run_pipeline_propre.py --dry-run     # verifie et montre ce qui serait fait
    python run_pipeline_propre.py               # execute tout
    python run_pipeline_propre.py --unswap      # secours : remet l'original si une execution a ete coupee
Options : --skip-ablation  --skip-confidence  --no-unswap

Limite : ce nettoyage retire les relations AJOUTEES avec le gold. Les relations SUPPRIMEES avec
l'aide du gold (V6.9 'zero_tp', V6.9d 'low_precision_object') ne peuvent pas etre restaurees
depuis le JSON final : la contamination restante est donc un minimum a corriger plus tard.
"""
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
IN_NAME = "SortieJson_Postprocessing"
CLEAN_NAME = "SortieJson_Postprocessing_PROPRE"
ORIG_NAME = "SortieJson_Postprocessing_ORIGINAL_GOLD_GUIDED"

GUIDED_ADDED = re.compile(r"^_v69[b-k]_added$")
GUIDED_ANY = re.compile(r"^_v69[c-k]_|_gold_|gold_guided|^_v69b_rule$", re.IGNORECASE)


def find_project():
    for p in [HERE, *HERE.parents]:
        if (p / "SGCE").is_dir() and (p / "document_grounding Etage 3").is_dir():
            return p
    return None


# ------------------------------------------------------------------ nettoyage
def is_guided(rel):
    """Relation ajoutee, selectionnee ou validee avec l'aide du gold."""
    if not isinstance(rel, dict):
        return False
    ti = str(rel.get("type_inference") or "")
    if ti.startswith("dev_") or "gold_guided" in ti or "error_guided" in ti or ti == "recall_controlled_v69b":
        return True
    for k, v in rel.items():
        if not v:
            continue
        if GUIDED_ADDED.match(str(k)) or GUIDED_ANY.search(str(k)):
            return True
    return False


def version_of(rel):
    for k, v in rel.items():
        m = re.match(r"^_v69([b-k])_added$", str(k))
        if m and v:
            return "V6.9" + m.group(1)
    return "V6.9?"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_dir(d):
    return {p.name: sha256_file(p) for p in sorted(Path(d).glob("*.json"))}


def build_clean(src: Path, dst: Path, report_dir: Path):
    if dst.exists():
        shutil.rmtree(dst)               # derive et regenerable : seul dossier supprime
    dst.mkdir(parents=True)
    rows, by_version, removed_total, kept_total = [], Counter(), 0, 0
    for p in sorted(src.glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict) or "global_relations" not in data:
            shutil.copy2(p, dst / p.name)
            continue
        removed_ids, removed_here = set(), 0
        kept = []
        for r in data.get("global_relations", []) or []:
            if is_guided(r):
                removed_here += 1
                by_version[version_of(r)] += 1
                rid = r.get("identifiant_relation")
                if rid:
                    removed_ids.add(rid)
            else:
                kept.append(r)
        n_before = len(data.get("global_relations", []) or [])
        data["global_relations"] = kept
        page_removed = 0
        for page in data.get("pages", []) or []:
            if isinstance(page, dict) and isinstance(page.get("relations"), list):
                keep_p = []
                for r in page["relations"]:
                    if is_guided(r) or (isinstance(r, dict) and r.get("identifiant_relation") in removed_ids):
                        page_removed += 1
                    else:
                        keep_p.append(r)
                page["relations"] = keep_p
        data["postprocessing_clean_trace"] = {
            "operation": "REMOVE_GOLD_GUIDED_RELATIONS",
            "criteres": "type_inference dev_*/gold_guided/error_guided ou champs _v69b-k_added, _v69c-k_*, *_gold_*",
            "relations_globales_avant": n_before,
            "relations_globales_retirees": removed_here,
            "relations_pages_retirees": page_removed,
            "limite": "les suppressions guidees par le gold (V6.9, V6.9d) ne sont pas restaurees",
        }
        (dst / p.name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        removed_total += removed_here
        kept_total += len(kept)
        rows.append([p.name, n_before, removed_here, len(kept), page_removed])
    report_dir.mkdir(parents=True, exist_ok=True)
    with open(report_dir / "nettoyage_relations_guidees.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["document", "relations_avant", "retirees", "relations_apres", "retirees_dans_pages"])
        w.writerows(rows)
    return removed_total, kept_total, by_version, len(rows)


# ------------------------------------------------------------------ echange
def rename_retry(a: Path, b: Path):
    last = None
    for _ in range(5):
        try:
            a.rename(b)
            return
        except OSError as exc:
            last = exc
            time.sleep(1.0)
    raise RuntimeError(f"Renommage impossible {a.name} -> {b.name} : {last}. "
                       "Ferme les fenetres/applications qui utilisent ce dossier.")


def swap(project: Path):
    cur, clean, orig = project / IN_NAME, project / CLEAN_NAME, project / ORIG_NAME
    rename_retry(cur, orig)
    try:
        rename_retry(clean, cur)
    except Exception:
        rename_retry(orig, cur)
        raise


def unswap(project: Path):
    cur, clean, orig = project / IN_NAME, project / CLEAN_NAME, project / ORIG_NAME
    if not orig.exists():
        return False
    if clean.exists():
        shutil.rmtree(clean)             # copie derivee, regenerable
    rename_retry(cur, clean)
    rename_retry(orig, cur)
    return True


# ------------------------------------------------------------------ verifications
def preflight(project: Path):
    problems = []
    sg = project / "SGCE"
    for rel in ["SGCE/run_sgce.py", "Evaluation/TRACE_Ablation_F1/run_ablation_f1_TRACE.py",
                "run_chain_3_to_8.py"]:
        if not (project / rel).exists():
            problems.append(f"fichier manquant : {rel}")
    rr = sg / "relation_repair" / "relation_repair_agent.py"
    if rr.exists():
        if "ALLOW_REPLACE_RELATION = False" not in rr.read_bytes().decode("utf-8-sig", errors="ignore"):
            problems.append("correctif relation_repair absent : lance d'abord  python SGCE\\fix_relation_repair.py")
    else:
        problems.append("SGCE\\relation_repair\\relation_repair_agent.py introuvable")
    rc = project / "document_grounding Etage 3" / "root_cause" / "root_cause_entity_candidate_builder.py"
    if rc.exists():
        txt = rc.read_bytes().decode("utf-8-sig", errors="ignore")
        m = re.search(r"^INPUT_DIR\s*=\s*Path\((.*?)\)\s*$", txt, re.S | re.M)
        block = txt[txt.find("INPUT_DIR"):txt.find("INPUT_DIR") + 400]
        if "relation_recovery" in block.split("\n\n")[0]:
            problems.append("l'Etage 3 lit encore l'Etage 9 : lance d'abord  python fix_etage3_input.py")
    else:
        problems.append("Etage 3 root_cause introuvable")
    if not (project / IN_NAME).is_dir() and not (project / ORIG_NAME).is_dir():
        problems.append(f"dossier d'entree introuvable : {IN_NAME}")
    return problems


def run_step(label, cmd, cwd, log_dir, env):
    print("\n" + "#" * 100)
    print(f"# {label}")
    print("#" * 100)
    log = log_dir / (re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_") + ".log")
    t0 = time.perf_counter()
    with open(log, "w", encoding="utf-8") as lf:
        proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace", env=env)
        for line in proc.stdout:
            sys.stdout.write(line)
            lf.write(line)
        rc = proc.wait()
    print(f"\n[{'OK' if rc == 0 else 'ECHEC'}] {label} - {time.perf_counter() - t0:.0f} s  (journal : {log.name})")
    return rc


# ------------------------------------------------------------------ main
def main():
    argv = sys.argv[1:]
    dry = "--dry-run" in argv
    project = find_project()
    if project is None:
        print("ERREUR : projet introuvable (dossiers SGCE et document_grounding Etage 3 attendus).")
        return 2
    print("=" * 100)
    print("TRACE - PIPELINE PROPRE, DE BOUT EN BOUT")
    print("=" * 100)
    print(f"Projet : {project}")

    if "--unswap" in argv:
        print("Remise en place de l'original :", "OK" if unswap(project) else "rien a faire")
        return 0

    if (project / ORIG_NAME).exists():
        print(f"\nUne execution precedente a ete interrompue ({ORIG_NAME} existe).")
        print("Lance d'abord :  python run_pipeline_propre.py --unswap")
        return 2

    problems = preflight(project)
    if problems:
        print("\nPROBLEME(S) :")
        for p in problems:
            print("  -", p)
        return 2

    src = project / IN_NAME
    n_json = len(list(src.glob("*.json")))
    print(f"Entree : {src} ({n_json} fichiers JSON)")
    log_dir = project / "run_logs_propre" / datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir.mkdir(parents=True, exist_ok=True)

    steps = [("Etage 2 SGCE", [sys.executable, "run_sgce.py"], project / "SGCE"),
             ("Etages 3 a 8", [sys.executable, "run_chain_3_to_8.py"], project)]
    if "--skip-ablation" not in argv:
        steps.append(("Ablation F1", [sys.executable, "run_ablation_f1_TRACE.py"],
                      project / "Evaluation" / "TRACE_Ablation_F1"))
    if "--skip-confidence" not in argv and (project / "confidence_vs_gold.py").exists():
        steps.append(("Precision par niveau de confiance", [sys.executable, "confidence_vs_gold.py"], project))

    if dry:
        removed, kept, by_v, _ = build_clean(src, project / CLEAN_NAME, log_dir)
        print(f"\n[dry-run] base propre construite dans {CLEAN_NAME} : "
              f"{removed} relations guidees retirees, {kept} gardees ({dict(by_v)})")
        print("[dry-run] etapes qui seraient lancees :")
        for label, cmd, cwd in steps:
            print(f"   - {label}  ({Path(cmd[1]).name} dans {cwd.name})")
        print("[dry-run] rien n'a ete echange ni lance.")
        return 0

    hashes_before = hash_dir(src)
    print("\nConstruction de la base propre ...")
    removed, kept, by_v, ndocs = build_clean(src, project / CLEAN_NAME, log_dir)
    print(f"  {ndocs} documents | {removed} relations guidees par le gold retirees : {dict(by_v)}")
    print(f"  {kept} relations conservees  ->  dossier {CLEAN_NAME}")

    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    status, failed = 0, None
    swapped = False
    try:
        swap(project)
        swapped = True
        print(f"\nEchange effectue : '{IN_NAME}' est maintenant la version PROPRE "
              f"(l'original est dans '{ORIG_NAME}').")
        for label, cmd, cwd in steps:
            rc = run_step(label, cmd, cwd, log_dir, env)
            if rc != 0:
                status, failed = 1, label
                break
    finally:
        if swapped and "--no-unswap" not in argv:
            try:
                unswap(project)
                print("\nDossier d'origine remis en place.")
            except Exception as exc:
                print(f"\nATTENTION : remise en place impossible ({exc}).")
                print("Lance :  python run_pipeline_propre.py --unswap")
                status = status or 3

    same = hash_dir(project / IN_NAME) == hashes_before if (project / IN_NAME).exists() else None
    print("\n" + "=" * 100)
    if failed:
        print(f"ARRET : echec a l'etape '{failed}'. Journaux : {log_dir}")
    else:
        print("PIPELINE PROPRE TERMINE")
    print(f"Original intact (SHA-256 identiques) : {same}")
    print(f"Journaux et rapport de nettoyage : {log_dir}")
    print("=" * 100)
    return status


if __name__ == "__main__":
    sys.exit(main())
