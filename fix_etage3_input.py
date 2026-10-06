# -*- coding: utf-8 -*-
"""
fix_etage3_input.py

Fait lire a l'Etage 3 (root_cause) la sortie OFFICIELLE de SGCE
    SGCE\\MultiAgent\\corrected
au lieu de la sortie de l'Etage 9 (relation_recovery_safe_corrected).

Pourquoi
--------
Dans les 4 scripts root_cause, le commentaire dit "Entree officielle de l'etage 3 : sortie
finale SGCE / Multi-Agent", mais INPUT_DIR pointe vers l'Etage 9. L'Etage 9 ajoute 2194
relations ; mesure : +2190 predictions pour +15 vrais positifs (precision marginale ~0,7 %),
ce qui fait passer la precision relationnelle de 74,1 % a 48,9 % a l'Etage 3 (ablation F1).

Ce que fait le script
---------------------
Pour chacun des 4 fichiers : il lit l'affectation INPUT_DIR = Path( ... ), te montre ce
qu'elle contient, et ne la remplace QUE si elle pointe vers l'Etage 9 par
    INPUT_DIR = Path(__file__).resolve().parents[2] / "SGCE" / "MultiAgent" / "corrected"
(chemin relatif a l'emplacement du fichier : fonctionne sur n'importe quelle machine).
Si l'affectation pointe deja vers SGCE, ou ailleurs, il ne touche a rien et te le dit.

Usage (depuis n'importe quel sous-dossier du projet) :
    python fix_etage3_input.py --check    # montre l'etat, ne modifie rien
    python fix_etage3_input.py            # applique (copies .bak_etage3)
    python fix_etage3_input.py --revert   # restaure les copies
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STAGE3 = "document_grounding Etage 3"
FILES = [
    "root_cause_entity_candidate_builder.py",
    "root_cause_entity_validator.py",
    "root_cause_entity_safe_corrector.py",
    "root_cause_entity_post_validator.py",
]
NEW_EXPR = 'Path(__file__).resolve().parents[2] / "SGCE" / "MultiAgent" / "corrected"'
SUFFIX = ".bak_etage3"
BOM = b"\xef\xbb\xbf"


def find_project():
    for p in [HERE, *HERE.parents]:
        if (p / STAGE3).is_dir():
            return p
    return None


def find_statement(text, name="INPUT_DIR"):
    """Retourne (debut, fin) de l'affectation `name = Path( ... )` (parentheses equilibrees)."""
    start = None
    i = 0
    while True:
        j = text.find(name, i)
        if j < 0:
            return None
        line_start = text.rfind("\n", 0, j) + 1
        before = text[line_start:j]
        k = j + len(name)
        rest = text[k:k + 40].lstrip(" \t")
        if before.strip() == "" and rest.startswith("=") and "Path(" in text[k:k + 40]:
            start = j
            break
        i = j + len(name)
    p = text.index("Path(", start) + len("Path")
    depth, in_str, raw, esc = 0, None, False, False
    pos = p
    while pos < len(text):
        ch = text[pos]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\" and not raw:
                esc = True
            elif ch == in_str:
                in_str = None
        else:
            if ch in "\"'":
                in_str = ch
                raw = pos > 0 and text[pos - 1] in "rR"
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return start, pos + 1
        pos += 1
    return None


def classify(stmt):
    s = stmt.replace("\\", "/").lower()
    if "relation_recovery" in s or "etage 9" in s:
        return "ETAGE9"
    if "sgce" in s and "multiagent" in s:
        return "SGCE"
    return "AUTRE"


def one_line(stmt):
    return " ".join(stmt.split())


def main():
    mode = "apply"
    if "--check" in sys.argv:
        mode = "check"
    if "--revert" in sys.argv:
        mode = "revert"

    project = find_project()
    if project is None:
        print(f"ERREUR : dossier '{STAGE3}' introuvable au-dessus de ce script.")
        print("Place ce fichier dans Reduction_hallucinations (ou un de ses sous-dossiers).")
        return 2
    folder = project / STAGE3 / "root_cause"
    print(f"Projet : {project}")

    if mode == "revert":
        n = 0
        for name in FILES:
            f, b = folder / name, folder / (name + SUFFIX)
            if b.exists():
                f.write_bytes(b.read_bytes())
                n += 1
                print(f"  restaure : {name}")
        print(f"{n} fichier(s) restaure(s).")
        return 0

    changed = 0
    for name in FILES:
        f = folder / name
        if not f.exists():
            print(f"  [absent]  {name}")
            continue
        raw = f.read_bytes()
        has_bom = raw.startswith(BOM)
        text = (raw[len(BOM):] if has_bom else raw).decode("utf-8")
        loc = find_statement(text)
        if loc is None:
            print(f"  [?]       {name} : affectation INPUT_DIR = Path(...) introuvable")
            continue
        stmt = text[loc[0]:loc[1]]
        eol = text.find("\n", loc[1])
        full_line = text[loc[0]:(eol if eol >= 0 else len(text))]
        kind = classify(stmt + " " + full_line)
        label = {"ETAGE9": "ETAGE 9  ", "SGCE": "SGCE ok  ", "AUTRE": "AUTRE    "}[kind]
        print(f"  [{label}] {name}")
        print(f"            {one_line(full_line if kind == 'SGCE' else stmt)[:170]}")
        if kind != "ETAGE9" or mode == "check":
            continue
        new_text = text[:loc[0]] + "INPUT_DIR = " + NEW_EXPR + text[loc[1]:]
        compile(new_text, str(f), "exec")
        bak = folder / (name + SUFFIX)
        if not bak.exists():
            bak.write_bytes(raw)
        f.write_bytes((BOM if has_bom else b"") + new_text.encode("utf-8"))
        changed += 1

    if mode == "check":
        print("\n(mode --check : rien n'a ete modifie)")
    else:
        print(f"\n{changed} fichier(s) modifie(s).")
        if changed:
            print("Etape suivante : python run_chain_3_to_8.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())