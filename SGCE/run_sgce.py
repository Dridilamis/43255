# -*- coding: utf-8 -*-
"""
TRACE / SGCE - Runner global  (V2 corrigee)

Remplace run_sgce.py (V1). Meme chaine :
    Patterns A -> B -> C -> D  ->  Relation Repair  ->  Orphan Resolution  ->  Multi-Agent

Corrections par rapport a la V1
-------------------------------
 1. PREFLIGHT   : runners, dossier d'entree, ontologie, chemins codes en dur
                  (A: "C:\\Users\\techlabo\\..." ; B: USERPROFILE\\Desktop\\TRACE ... dans 18 scripts
                  d'audit/evaluation/Etage 9).
 2. ENTREE FIGEE: SHA-256 de SortieJson_Postprocessing avant / apres CHAQUE etape.
                  Echec immediat si un JSON d'entree est modifie.
 3. AUDIT       : audit structurel integre apres chaque etape, memes definitions que
                  final_ontology_audit.py (orphelins, doublons, signatures), avec
                  anomalies NOUVELLES / RESOLUES par rapport a l'etape precedente.
 4. GARDE-FOUS : document perdu ou ajoute ; post-validateur en FAIL (rapports produits
                  pendant ce run uniquement, jamais d'anciens rapports).
 5. TRACABILITE : journal par etape (run_logs/) + manifeste JSON reproductible.
 6. OPTIONS     : --audit-only, --from-stage, --only, --strict, --dry-run, --patch-paths.

Le gold n'est JAMAIS lu ici : decision (SGCE) et evaluation (F1) restent separees.
Pour l'evaluation, lancer ensuite run_SGCE_F1_optimizer_audit.py.

Codes de sortie : 0 OK | 1 etape en echec | 2 preflight | 3 garde-fou (--strict) | 4 entree modifiee
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

RUNNER_VERSION = "2.0"
ROOT = Path(__file__).resolve().parent

EXIT_OK, EXIT_STAGE, EXIT_PREFLIGHT, EXIT_GATE, EXIT_INPUT = 0, 1, 2, 3, 4

GUIDELINE_NAME = "Guideline_TRACE_Sepsis_v1.6.json"
HARDCODED_RE = re.compile(r'[A-Za-z]:\\Users\\[^"\'\r\n]*?OCR vers LLM')
# Famille B : chemin reconstruit depuis le profil Windows (suppose Desktop\\TRACE\\OCR vers LLM)
USERPROFILE_RE = re.compile(
    r'Path\(\s*os\.environ\.get\(\s*"USERPROFILE"\s*,\s*str\(\s*Path\.home\(\s*\)\s*\)\s*\)\s*\)'
    r'\s*/\s*"Desktop"\s*/\s*"TRACE"\s*/\s*"OCR vers LLM"')
ENTITY_TEXT_KEYS = ("preuve", "name", "valeur", "libelle", "parametre", "texte", "text")


# ============================================================
# 1. ETAPES
# ============================================================

@dataclass(frozen=True)
class Stage:
    key: str
    label: str
    runner: Path      # script maitre de l'etape
    output: Path      # dossier de JSON cliniques produit par l'etape
    scan: Path        # arborescence ou chercher les rapports de post-validation


def build_stages(root: Path):
    return [
        Stage("patterns", "PATTERNS A -> B -> C -> D",
              root / "Patterns" / "run_all_patterns.py",
              root / "Patterns" / "PatternD" / "corrected",
              root / "Patterns"),
        Stage("relation_repair", "RELATION REPAIR",
              root / "relation_repair" / "run_relation_repair_all.py",
              root / "relation_repair" / "corrected",
              root / "relation_repair"),
        Stage("orphan_resolution", "ORPHAN RESOLUTION",
              root / "orphan_resolution" / "run_orphan_relations_all.py",
              root / "orphan_resolution" / "corrected",
              root / "orphan_resolution"),
        Stage("multiagent", "MULTI-AGENT",
              root / "MultiAgent" / "run_all_parts.py",
              root / "MultiAgent" / "corrected",
              root / "MultiAgent"),
    ]


# ============================================================
# 2. OUTILS FICHIERS
# ============================================================

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def iter_clinical(directory):
    """Meme regle que final_ontology_audit.clinical_files."""
    if not directory:
        return
    d = Path(directory)
    if not d.is_dir():
        return
    for p in sorted(d.glob("*.json")):
        if p.name.endswith("_report.json"):
            continue
        try:
            data = load_json(p)
        except Exception:
            continue
        if isinstance(data, dict) and any(k in data for k in ("pages", "global_entities", "global_relations")):
            yield p.name, data


def hash_directory(directory) -> dict:
    d = Path(directory)
    if not d.is_dir():
        return {}
    return {p.name: sha256_file(p) for p in sorted(d.glob("*.json"))}


def digest_of(hashes: dict) -> str:
    h = hashlib.sha256()
    for name in sorted(hashes):
        h.update(name.encode("utf-8"))
        h.update(hashes[name].encode("ascii"))
    return h.hexdigest()


# ============================================================
# 3. AUDIT STRUCTUREL (definitions identiques a final_ontology_audit.py)
# ============================================================

def entity_id(e):
    return e.get("identifiant_entite") or e.get("id") or e.get("entity_id")


def entity_type(e):
    return e.get("categorie") or e.get("type") or e.get("entity_type") or ""


def entity_text(e):
    values = []
    for key in ENTITY_TEXT_KEYS:
        v = e.get(key)
        if v not in (None, ""):
            t = str(v).strip()
            if t and t not in values:
                values.append(t)
    return " | ".join(values)


def relation_type(r):
    return (r.get("type_relation") or r.get("relation") or r.get("relation_type")
            or r.get("predicate") or r.get("type") or "")


def relation_source(r):
    return r.get("identifiant_entite_sujet") or r.get("from_id") or r.get("subject_id") or r.get("source")


def relation_target(r):
    return r.get("identifiant_entite_objet") or r.get("to_id") or r.get("object_id") or r.get("target")


def get_entities(doc):
    if isinstance(doc.get("global_entities"), list):
        return doc["global_entities"]
    out = []
    for page in (doc.get("pages", []) or []):
        out.extend(page.get("entities", []) or [])
    return out


def get_relations(doc):
    if isinstance(doc.get("global_relations"), list):
        return doc["global_relations"]
    out = []
    for page in (doc.get("pages", []) or []):
        out.extend(page.get("relations", []) or [])
    return out


def _collect_signatures(block, depth=0):
    sigs = {}
    if not isinstance(block, dict) or depth > 3:
        return sigs
    for name, spec in block.items():
        if not isinstance(spec, dict):
            continue
        dom = spec.get("domaine") or spec.get("domain") or spec.get("source_type")
        img = spec.get("image") or spec.get("range") or spec.get("target_type")
        if dom and img:
            sigs[name] = {"domaine": dom, "image": img}
        else:
            sigs.update(_collect_signatures(spec, depth + 1))
    return sigs


def load_signatures(guideline_path):
    if not guideline_path:
        return {}
    data = load_json(Path(guideline_path))
    root = data.get("ontologie_sepsis_graph", data)
    for block in (root.get("signatures_relations_verrouillees_v1_5"),
                  root.get("signatures_relations"),
                  root.get("relations")):
        sigs = _collect_signatures(block)
        if sigs:
            return sigs
    return {}


def _type_ok(actual, expected):
    if isinstance(expected, (list, tuple, set)):
        return actual in expected
    return actual == expected


def audit_document(name, doc, signatures):
    """Retourne une liste de (type_anomalie, cle_stable)."""
    out = []
    entities = get_entities(doc)
    relations = get_relations(doc)

    by_id = defaultdict(list)
    for e in entities:
        eid = entity_id(e)
        if eid is not None:
            by_id[str(eid)].append(e)
    index = {eid: vals[0] for eid, vals in by_id.items()}

    for eid, vals in by_id.items():
        if len(vals) > 1:
            out.append(("DUPLICATE_ENTITY_ID", (name, "DUPLICATE_ENTITY_ID", eid)))

    groups = defaultdict(set)
    for e in entities:
        key = (entity_type(e), entity_text(e).strip())
        eid = entity_id(e)
        if key[0] and key[1] and eid is not None:
            groups[key].add(str(eid))
    for (etype, etext), ids in groups.items():
        if len(ids) > 1:
            out.append(("DUPLICATE_ENTITY_CONTENT", (name, "DUPLICATE_ENTITY_CONTENT", etype, etext)))

    rgroups = defaultdict(int)
    for r in relations:
        rgroups[(relation_type(r), str(relation_source(r)), str(relation_target(r)))] += 1
    for (rt, s, t), n in rgroups.items():
        if n > 1:
            out.append(("DUPLICATE_RELATION", (name, "DUPLICATE_RELATION", rt, s, t)))

    for r in relations:
        rt, sid, tid = relation_type(r), relation_source(r), relation_target(r)
        base = (rt, str(sid), str(tid))
        src, tgt = index.get(str(sid)), index.get(str(tid))
        if src is None:
            out.append(("ORPHAN_RELATION_SOURCE", (name, "ORPHAN_RELATION_SOURCE") + base))
        if tgt is None:
            out.append(("ORPHAN_RELATION_TARGET", (name, "ORPHAN_RELATION_TARGET") + base))
        if not signatures:
            continue
        if rt and rt not in signatures:
            out.append(("UNAUTHORIZED_RELATION", (name, "UNAUTHORIZED_RELATION") + base))
            continue
        sig = signatures.get(rt)
        if not sig:
            continue
        if src is not None and not _type_ok(entity_type(src), sig["domaine"]):
            out.append(("INVALID_RELATION_SOURCE_TYPE", (name, "INVALID_RELATION_SOURCE_TYPE") + base))
        if tgt is not None and not _type_ok(entity_type(tgt), sig["image"]):
            out.append(("INVALID_RELATION_TARGET_TYPE", (name, "INVALID_RELATION_TARGET_TYPE") + base))
    return out


def audit_directory(directory, signatures):
    counts, keys, names, n_docs = Counter(), set(), set(), 0
    for name, doc in iter_clinical(directory):
        n_docs += 1
        names.add(name)
        for atype, key in audit_document(name, doc, signatures):
            counts[atype] += 1
            keys.add(key)
    return {"n_docs": n_docs, "counts": counts, "keys": keys, "names": names}


# ============================================================
# 4. CHEMINS CODES EN DUR
# ============================================================

def _norm(p: str) -> str:
    return p.replace("\\", "/").rstrip("/").lower()


def _py_files(root: Path):
    me = Path(__file__).resolve()
    for p in sorted(root.rglob("*.py")):
        if "__pycache__" in p.parts or p.resolve() == me:
            continue
        yield p


def _read(p: Path) -> str:
    try:
        return p.read_bytes().decode("utf-8", errors="ignore")
    except OSError:
        return ""


def find_path_issues(root: Path, expected_base: Path):
    """Retourne (famille_A, famille_B) : {fichier: nb} pour les chemins qui ne
    correspondent PAS a expected_base (= dossier 'OCR vers LLM' reel)."""
    exp = _norm(str(expected_base))
    implied_b = _norm(str(Path.home() / "Desktop" / "TRACE" / "OCR vers LLM"))
    fam_a, fam_b = {}, {}
    for p in _py_files(root):
        text = _read(p)
        a = [h for h in HARDCODED_RE.findall(text) if _norm(h) != exp]
        if a:
            fam_a[p] = len(a)
        if implied_b != exp:
            b = USERPROFILE_RE.findall(text)
            if b:
                fam_b[p] = len(b)
    return fam_a, fam_b


def patch_paths(root: Path, expected_base: Path, apply: bool) -> int:
    fam_a, fam_b = find_path_issues(root, expected_base)
    files = sorted(set(fam_a) | set(fam_b))
    print(f"Base reelle : {expected_base}")
    print(f"Famille A (chemin absolu 'techlabo' ...) : {len(fam_a)} fichier(s)")
    print(f"Famille B (USERPROFILE\\Desktop\\TRACE ...) : {len(fam_b)} fichier(s)")
    for p in files:
        tag = ("A" if p in fam_a else "") + ("B" if p in fam_b else "")
        print(("  [PATCH %s] " if apply else "  [DRY   %s] ") % tag.ljust(2) + str(p.relative_to(root)))
        if not apply:
            continue
        raw = p.read_bytes()
        bak = p.with_suffix(p.suffix + ".bak")
        if not bak.exists():
            bak.write_bytes(raw)
        text = raw.decode("utf-8")
        text = HARDCODED_RE.sub(lambda m: str(expected_base), text)
        text = USERPROFILE_RE.sub(lambda m: 'Path(r"%s")' % expected_base, text)
        p.write_bytes(text.encode("utf-8"))
    if files and not apply:
        print("Aucune modification faite. Relancer avec --apply pour ecrire (copies .bak creees).")
    return len(files)


# ============================================================
# 5. EXECUTION D'UNE ETAPE + RAPPORTS
# ============================================================

def run_stage(index, total, stage: Stage, log_dir: Path):
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{index:02d}_{stage.key}.log"
    print("\n" + "=" * 108)
    print(f"[{index}/{total}] {stage.label}")
    print("=" * 108)
    print(f"Script : {stage.runner}")
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    start = time.perf_counter()
    with open(log_path, "w", encoding="utf-8") as lf:
        proc = subprocess.Popen([sys.executable, str(stage.runner)], cwd=str(stage.runner.parent),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace", env=env)
        for line in proc.stdout:
            sys.stdout.write(line)
            lf.write(line)
        rc = proc.wait()
    return rc, time.perf_counter() - start, log_path


def _status_of(data):
    if not isinstance(data, dict):
        return None
    for holder in (data, data.get("summary") if isinstance(data.get("summary"), dict) else {}):
        for k in ("final_status", "status", "verdict"):
            v = holder.get(k)
            if isinstance(v, str):
                return v.strip().upper()
    return None


def scan_reports(base: Path, since: float):
    """Rapports JSON modifies depuis `since` (donc produits par CE run) avec leur statut."""
    out = []
    if not base.is_dir():
        return out
    for p in base.rglob("*.json"):
        n = p.name.lower()
        if "report" not in n and "post_validation" not in n:
            continue
        try:
            st = p.stat()
            if st.st_mtime < since - 1 or st.st_size > 5_000_000:
                continue
            status = _status_of(load_json(p))
        except Exception:
            continue
        if status:
            out.append({"report": str(p.relative_to(base)), "status": status})
    return out


# ============================================================
# 6. PRESENTATION
# ============================================================

def print_table(rows):
    head = f"{'Etape':<28}{'docs':>5}{'anomalies':>11}{'nouvelles':>11}{'resolues':>10}"
    print("\n" + "=" * len(head))
    print("AUDIT STRUCTUREL PAR ETAPE")
    print("=" * len(head))
    print(head)
    print("-" * len(head))
    for r in rows:
        nw = "-" if r["new"] is None else str(r["new"])
        rs = "-" if r["resolved"] is None else str(r["resolved"])
        print(f"{r['label']:<28}{r['n_docs']:>5}{r['total']:>11}{nw:>11}{rs:>10}")
    print("=" * len(head))


def print_types(first, last):
    types = sorted(set(first["counts"]) | set(last["counts"]))
    if not types:
        return
    print(f"\n{'Type d anomalie':<34}{'entree':>8}{'sortie':>8}{'delta':>8}")
    for t in types:
        a, b = first["counts"].get(t, 0), last["counts"].get(t, 0)
        print(f"{t:<34}{a:>8}{b:>8}{b - a:>+8}")


def write_manifest(log_dir: Path, manifest: dict):
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"run_manifest_{datetime.now():%Y%m%d_%H%M%S}.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# ============================================================
# 7. MAIN
# ============================================================

def parse_args(argv):
    ap = argparse.ArgumentParser(description="TRACE / SGCE - runner global V2")
    ap.add_argument("--input-dir", help="dossier SortieJson_Postprocessing (defaut: ../SortieJson_Postprocessing)")
    ap.add_argument("--ontology", help=f"chemin de {GUIDELINE_NAME} (signatures domaine/image)")
    ap.add_argument("--from-stage", type=int, default=1, help="premiere etape a executer (1-4)")
    ap.add_argument("--only", type=int, help="executer une seule etape (1-4)")
    ap.add_argument("--audit-only", action="store_true", help="ne rien executer, auditer les sorties existantes")
    ap.add_argument("--strict", action="store_true", help="echec si une etape cree de nouvelles anomalies")
    ap.add_argument("--dry-run", action="store_true", help="preflight + plan, sans execution")
    ap.add_argument("--patch-paths", action="store_true", help="corriger les chemins codes en dur (dry-run par defaut)")
    ap.add_argument("--apply", action="store_true", help="avec --patch-paths : ecrire les modifications")
    ap.add_argument("--patch-scope", choices=("sgce", "project"), default="sgce",
                    help="avec --patch-paths : 'sgce' (defaut) ou 'project' = aussi Etages 8, 9, evaluation...")
    return ap.parse_args(argv)


def main(argv=None, root: Path = ROOT) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    args = parse_args(argv)
    project = root.parent
    expected_base = project.parent
    log_dir = root / "run_logs"
    stages = build_stages(root)
    total = len(stages)

    print("=" * 108)
    print(f"TRACE / SGCE - PIPELINE COMPLET (runner V{RUNNER_VERSION})")
    print("=" * 108)
    print(f"Racine : {root}\nPython : {sys.executable} ({platform.python_version()})")
    print("Chaine : " + " -> ".join(s.label for s in stages))

    if args.patch_paths:
        patch_paths(project if args.patch_scope == "project" else root, expected_base, args.apply)
        return EXIT_OK

    problems, warnings = [], []

    # ---------- PREFLIGHT ----------
    if sys.version_info < (3, 8):
        problems.append("Python >= 3.8 requis.")
    for s in stages:
        if not s.runner.exists():
            problems.append(f"runner introuvable : {s.runner}")
    if project.name != "Reduction_hallucinations":
        warnings.append(f"dossier projet = '{project.name}' (les sous-scripts supposent 'Reduction_hallucinations').")

    input_dir = Path(args.input_dir) if args.input_dir else project / "SortieJson_Postprocessing"
    input_hashes = hash_directory(input_dir)
    if not input_hashes:
        (warnings if args.audit_only else problems).append(f"entree introuvable ou vide : {input_dir}")

    guideline = None
    cands = [Path(args.ontology)] if args.ontology else [
        project / GUIDELINE_NAME, project.parent / GUIDELINE_NAME, root / GUIDELINE_NAME]
    for c in cands:
        if c.exists():
            guideline = c
            break
    signatures = {}
    if guideline:
        try:
            signatures = load_signatures(guideline)
        except Exception as exc:
            warnings.append(f"ontologie illisible ({exc})")
    if not signatures:
        warnings.append("signatures TRACE non chargees : INVALID_RELATION_*_TYPE et UNAUTHORIZED_RELATION NON audites.")

    fam_a, fam_b = find_path_issues(root, expected_base)
    if fam_a and not args.audit_only:
        problems.append(f"{len(fam_a)} sous-script(s) codent un chemin different de {expected_base} "
                        f"(ex. {next(iter(fam_a)).name}). Lancer : python run_sgce.py --patch-paths --apply")
    if fam_b:
        warnings.append(f"{len(fam_b)} script(s) d'audit/evaluation de SGCE construisent un chemin "
                        f"USERPROFILE\\Desktop\\TRACE incorrect pour {expected_base} "
                        f"(ex. {next(iter(fam_b)).name}) : --patch-paths --apply les corrige.")

    first = args.only if args.only else args.from_stage
    last = args.only if args.only else total
    if not (1 <= first <= total and first <= last <= total):
        problems.append(f"numero d'etape invalide (1-{total}).")

    for w in warnings:
        print(f"ATTENTION : {w}")
    if problems:
        print("\nERREUR(S) PREFLIGHT :")
        for p in problems:
            print(f"  - {p}")
        return EXIT_PREFLIGHT

    print(f"Entree : {input_dir} ({len(input_hashes)} fichiers JSON)")
    print(f"Ontologie : {guideline if signatures else 'non chargee'} ({len(signatures)} signatures)")

    selected = stages[first - 1:last]
    if args.dry_run:
        print("\nPlan (dry-run) :")
        for i, s in enumerate(selected, first):
            print(f"  {i}. {s.label}  ->  sortie {s.output}")
        return EXIT_OK

    manifest = {
        "runner_version": RUNNER_VERSION, "started": datetime.now().isoformat(timespec="seconds"),
        "python": sys.version, "platform": platform.platform(), "root": str(root),
        "mode": "audit-only" if args.audit_only else "run",
        "input": {"dir": str(input_dir), "n_files": len(input_hashes), "digest": digest_of(input_hashes),
                  "files": input_hashes},
        "ontology": {"path": str(guideline) if guideline else None, "n_signatures": len(signatures),
                     "sha256": sha256_file(guideline) if guideline else None},
        "warnings": warnings, "stages": [], "audit": [], "gates": {},
    }

    # ---------- AUDIT DE REFERENCE ----------
    prev_dir = input_dir
    if first > 1 and stages[first - 2].output.is_dir():
        prev_dir = stages[first - 2].output
    prev = audit_directory(prev_dir, signatures)
    base_audit = prev
    rows = [{"label": "ENTREE" if prev_dir == input_dir else f"APRES {stages[first - 2].key}",
             "n_docs": prev["n_docs"], "total": sum(prev["counts"].values()), "new": None, "resolved": None}]
    manifest["audit"].append({"stage": "input", "dir": str(prev_dir), "counts": dict(prev["counts"])})
    gate_fail = False
    t0 = time.perf_counter()

    # ---------- BOUCLE ----------
    for i, s in enumerate(selected, first):
        record = {"index": i, "key": s.key, "label": s.label, "runner": str(s.runner), "output": str(s.output)}
        if not args.audit_only:
            started_at = time.time()
            rc, secs, log_path = run_stage(i, total, s, log_dir)
            record.update(returncode=rc, seconds=round(secs, 2), log=str(log_path))
            if rc != 0:
                record["status"] = "FAIL_RETURNCODE"
                manifest["stages"].append(record)
                manifest["status"] = f"FAIL at stage {i}"
                write_manifest(log_dir, manifest)
                print(f"\nSGCE ARRETE - ECHEC : {s.label} (code {rc}). Journal : {log_path}")
                return EXIT_STAGE

            # G1 : entree intacte
            after = hash_directory(input_dir)
            if after != input_hashes:
                changed = sorted(k for k in set(after) | set(input_hashes) if after.get(k) != input_hashes.get(k))
                record["status"] = "FAIL_INPUT_MODIFIED"
                manifest["stages"].append(record)
                manifest["status"] = f"FAIL input modified at stage {i}"
                write_manifest(log_dir, manifest)
                print(f"\nSGCE ARRETE - ENTREE MODIFIEE par {s.label} : {changed[:5]}")
                return EXIT_INPUT

            # G3 : post-validateurs produits pendant ce run
            reports = scan_reports(s.scan, started_at)
            record["reports"] = reports
            failed = [r for r in reports if r["status"].startswith(("FAIL", "ERROR"))]
            if failed:
                record["status"] = "FAIL_POST_VALIDATION"
                manifest["stages"].append(record)
                manifest["status"] = f"FAIL post-validation at stage {i}"
                write_manifest(log_dir, manifest)
                print(f"\nSGCE ARRETE - post-validateur en FAIL : {failed[:3]}")
                return EXIT_STAGE

        if not s.output.is_dir():
            record["status"] = "NO_OUTPUT"
            manifest["stages"].append(record)
            if args.audit_only:
                print(f"[audit] {s.key} : sortie absente ({s.output}) - ignore")
                continue
            manifest["status"] = f"FAIL no output at stage {i}"
            write_manifest(log_dir, manifest)
            print(f"\nSGCE ARRETE - dossier de sortie absent : {s.output}")
            return EXIT_STAGE

        cur = audit_directory(s.output, signatures)
        # G2 : aucun document perdu ni ajoute
        lost, extra = sorted(prev["names"] - cur["names"]), sorted(cur["names"] - prev["names"])
        if lost or extra:
            record.update(status="FAIL_DOCUMENTS", lost=lost, extra=extra)
            manifest["stages"].append(record)
            manifest["status"] = f"FAIL documents at stage {i}"
            write_manifest(log_dir, manifest)
            print(f"\nSGCE ARRETE - documents perdus {lost[:3]} / ajoutes {extra[:3]}")
            return EXIT_STAGE

        new_keys = cur["keys"] - prev["keys"]
        resolved = prev["keys"] - cur["keys"]
        record.update(status="OK", n_docs=cur["n_docs"], anomalies=sum(cur["counts"].values()),
                      new_anomalies=len(new_keys), resolved_anomalies=len(resolved),
                      counts=dict(cur["counts"]))
        if new_keys:
            msg = f"{s.key} cree {len(new_keys)} nouvelle(s) anomalie(s)"
            warnings.append(msg)
            print(f"ATTENTION : {msg}")
            if args.strict:
                gate_fail = True
                record["status"] = "FAIL_NEW_ANOMALIES"
        manifest["stages"].append(record)
        manifest["audit"].append({"stage": s.key, "dir": str(s.output), "counts": dict(cur["counts"])})
        rows.append({"label": s.key, "n_docs": cur["n_docs"], "total": sum(cur["counts"].values()),
                     "new": len(new_keys), "resolved": len(resolved)})
        prev, prev_dir = cur, s.output

    # ---------- BILAN ----------
    print_table(rows)
    if len(rows) > 1:
        print_types(base_audit, prev)
    manifest["gates"] = {"input_unchanged": True if not args.audit_only else None,
                         "strict_new_anomalies": "FAIL" if gate_fail else "OK"}
    manifest["status"] = "FAIL strict" if gate_fail else "OK"
    manifest["seconds_total"] = round(time.perf_counter() - t0, 2)
    path = write_manifest(log_dir, manifest)
    print(f"\nManifeste : {path}")
    print("Evaluation F1 (gold) : lancer separement run_SGCE_F1_optimizer_audit.py")
    print("TRACE / SGCE - " + ("TERMINE AVEC ECHEC (--strict)" if gate_fail else "TERMINE AVEC SUCCES"))
    return EXIT_GATE if gate_fail else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
