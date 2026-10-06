# -*- coding: utf-8 -*-
"""
fix_relation_repair.py

Correctif cible de SGCE/relation_repair/relation_repair_agent.py. Aucun pattern ajoute.

Probleme mesure (audit F1, 43 documents)
----------------------------------------
La regle 1 de decide() remplace le TYPE DE LA RELATION des qu'une seule signature TRACE
correspond aux types observes des deux entites, sans verifier aucune preuve textuelle.
Elle fait confiance aux types des entites, qui sont justement ce que Mistral confond
(DEFAILLANCE_ORGANE / SYMPTOME / LABEL_NOSOLOGIQUE).
  - 48 REPLACE_RELATION appliques (+ 4 RETYPE_TARGET)
  - TP_EXACT 1933 -> 1897 (-36) et WRONG_TYPE 2 -> 38 (+36)
  - F1 relaxed : -0,83 pt

Correction
----------
Un drapeau ALLOW_REPLACE_RELATION (False par defaut). Quand il est False, la regle 1 est
sautee : le cas passe aux regles suivantes (RETYPE_SOURCE / RETYPE_TARGET, soutenues par le
texte) ou tombe en REVIEW. Mettre True dans le fichier restaure l'ancien comportement.

Usage (depuis le dossier SGCE) :
    python fix_relation_repair.py            # applique, avec copie .bak
    python fix_relation_repair.py --check    # indique l'etat sans rien ecrire
    python fix_relation_repair.py --revert   # restaure la copie .bak
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TARGET = HERE / "relation_repair" / "relation_repair_agent.py"
BAK = TARGET.with_suffix(".py.bak_fix")

RULE1 = re.compile(
    r"if\s*\(\s*len\(candidates\)\s*==\s*1\s*and\s*candidates\[\s*0\s*\]\s*!=\s*relation_type\s*\)\s*:")
ANCHOR = re.compile(r'(OUTPUT_FILE\s*=\s*HERE\s*/\s*"outputs"\s*/\s*"relation_repair_decisions\.json"[^\r\n]*)')


def main():
    mode = "apply"
    if "--check" in sys.argv:
        mode = "check"
    if "--revert" in sys.argv:
        mode = "revert"

    if not TARGET.exists():
        print(f"ERREUR : fichier introuvable : {TARGET}")
        print("Lance ce script depuis le dossier SGCE.")
        return 2

    raw = TARGET.read_bytes()
    text = raw.decode("utf-8")
    applied = "ALLOW_REPLACE_RELATION" in text

    if mode == "check":
        print("Correctif DEJA APPLIQUE." if applied else "Correctif NON appliqué.")
        return 0

    if mode == "revert":
        if not BAK.exists():
            print("Aucune copie .bak_fix a restaurer.")
            return 2
        TARGET.write_bytes(BAK.read_bytes())
        print(f"Restaure depuis {BAK.name}.")
        return 0

    if applied:
        print("Correctif deja applique : rien a faire.")
        return 0

    nl = "\r\n" if b"\r\n" in raw else "\n"
    if len(RULE1.findall(text)) != 1 or len(ANCHOR.findall(text)) != 1:
        print("ERREUR : le fichier ne ressemble pas a la version attendue "
              "(regle 1 ou ligne OUTPUT_FILE introuvable). Rien n'a ete modifie.")
        print("Envoie-moi le fichier relation_repair_agent.py.")
        return 3

    flag = nl.join([
        "",
        "# --- Correctif A/B (fix_relation_repair.py) ---------------------------------",
        "# REPLACE_RELATION remplace le type de la relation sans preuve textuelle, en se",
        "# fiant aux types des entites. Mesure : 36 relations correctes deviennent WRONG_TYPE.",
        "# False = desactive ; True = ancien comportement.",
        "ALLOW_REPLACE_RELATION = False",
    ])
    text = ANCHOR.sub(lambda m: m.group(1) + flag, text, count=1)
    new_rule = nl.join([
        "if (",
        "        ALLOW_REPLACE_RELATION",
        "        and len(candidates) == 1",
        "        and candidates[0] != relation_type",
        "    ):",
    ])
    text = RULE1.sub(lambda m: new_rule, text, count=1)

    if not BAK.exists():
        BAK.write_bytes(raw)
    TARGET.write_bytes(text.encode("utf-8"))
    compile(text, str(TARGET), "exec")
    print("Correctif applique. Copie de securite :", BAK.name)
    print("Etape suivante : python run_sgce.py --from-stage 2")
    return 0


if __name__ == "__main__":
    sys.exit(main())
