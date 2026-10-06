# -*- coding: utf-8 -*-
"""
run_chain_3_to_8.py

Relance dans l'ordre les Etages 3 -> 4 -> 5 -> 6 -> 7 -> 8 de TRACE, chacun avec son runner,
et s'arrete a la premiere erreur. A utiliser apres fix_etage3_input.py, puis lancer l'ablation.

    python run_chain_3_to_8.py --dry-run     # liste les runners trouves, ne lance rien
    python run_chain_3_to_8.py               # lance toute la chaine
    python run_chain_3_to_8.py --from 5      # reprend a l'Etage 5

Les journaux sont ecrits dans <projet>\\run_logs_chaine\\.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

# (numero, dossier, runner attendu ou None = a decouvrir)
STAGES = [
    (3, "document_grounding Etage 3", "run_document_grounding.py"),
    (4, "ontology Etage 4", "run_ontology.py"),
    (5, "numeric_unit Etage 5", "run_numeric_unit.py"),
    (6, "temporal Etage 6", None),
    (7, "negation Etage 7", "run_negation.py"),
    (8, "confidence Etage 8", "run_confidence.py"),
]


def find_project():
    for p in [HERE, *HERE.parents]:
        if (p / "document_grounding Etage 3").is_dir():
            return p
    return None


def find_runner(folder: Path, expected):
    if expected and (folder / expected).exists():
        return folder / expected, ""
    cands = sorted(folder.glob("run_*.py"))
    if expected and not cands:
        return None, f"{expected} introuvable"
    if len(cands) == 1:
        return cands[0], "(decouvert)"
    named = [c for c in cands if "temporal" in c.name.lower()]
    if len(named) == 1:
        return named[0], "(decouvert)"
    if not cands:
        return None, "aucun run_*.py"
    return None, "plusieurs runners : " + ", ".join(c.name for c in cands)


def main():
    dry = "--dry-run" in sys.argv
    start_at = 3
    if "--from" in sys.argv:
        start_at = int(sys.argv[sys.argv.index("--from") + 1])

    project = find_project()
    if project is None:
        print("ERREUR : projet introuvable (dossier 'document_grounding Etage 3' absent).")
        return 2
    print("=" * 100)
    print("TRACE - CHAINE ETAGES 3 -> 8")
    print("=" * 100)
    print(f"Projet : {project}\nPython : {sys.executable}\n")

    plan, bad = [], []
    for num, folder_name, expected in STAGES:
        folder = project / folder_name
        if not folder.is_dir():
            bad.append(f"Etage {num} : dossier introuvable : {folder}")
            continue
        runner, note = find_runner(folder, expected)
        if runner is None:
            bad.append(f"Etage {num} : {note} dans {folder}")
            continue
        plan.append((num, folder_name, runner))
        print(f"  Etage {num}  {runner.relative_to(project)} {note}")
    if bad:
        print("\nPROBLEME(S) :")
        for b in bad:
            print("  -", b)
        return 2
    if dry:
        print("\n(dry-run : rien n'a ete lance)")
        return 0

    log_dir = project / "run_logs_chaine"
    log_dir.mkdir(exist_ok=True)
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    t_all = time.perf_counter()
    for num, folder_name, runner in plan:
        if num < start_at:
            continue
        print("\n" + "=" * 100)
        print(f"ETAGE {num} - {folder_name}")
        print("=" * 100)
        log = log_dir / f"etage_{num}.log"
        t0 = time.perf_counter()
        with open(log, "w", encoding="utf-8") as lf:
            proc = subprocess.Popen([sys.executable, str(runner)], cwd=str(runner.parent),
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace", env=env)
            for line in proc.stdout:
                sys.stdout.write(line)
                lf.write(line)
            rc = proc.wait()
        secs = time.perf_counter() - t0
        if rc != 0:
            print(f"\nCHAINE ARRETEE - ECHEC Etage {num} (code {rc}). Journal : {log}")
            return 1
        print(f"\n[OK] Etage {num} - {secs:.0f} s")

    print("\n" + "=" * 100)
    print(f"CHAINE 3 -> 8 TERMINEE - {time.perf_counter() - t_all:.0f} s")
    print("=" * 100)
    print("Etape suivante :")
    print('  cd "' + str(project / "Evaluation" / "TRACE_Ablation_F1") + '"')
    print("  python run_ablation_f1_TRACE.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
