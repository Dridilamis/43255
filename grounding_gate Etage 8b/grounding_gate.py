# -*- coding: utf-8 -*-
"""
TRACE - ETAGE 8b - GROUNDING GATE (garde-fou final d'ancrage documentaire)

Probleme
--------
Les Etages 2 a 8 annotent les relations (niveau de confiance, negation, temporalite...)
mais n'en retirent presque aucune : 3731 relations en entree propre, 3744 en sortie de
l'Etage 8. Une relation dont l'entite ou la preuve n'existe pas dans le document source
reste donc dans le graphe final : c'est une hallucination du LLM qui n'est jamais filtree.

Ce que fait cet etage
---------------------
Il relit chaque relation de `confidence_assessed_safe` et la confronte au TEXTE SOURCE
du document (pages[].texte_brut + Sortie_Textes_Brut_MistralSmall4/<doc>_brut.txt).
Une relation est retiree si au moins une regle ci-dessous est violee :

  G1 ENDPOINT_NOT_IN_SOURCE  une extremite (hors noeud patient) n'est pas attestee dans
                             le texte : moins de la moitie de ses mots porteurs de sens
                             (ou un de ses nombres) y figurent -> entite inventee.
  G2 FABRICATED_EVIDENCE     la preuve est une citation qui n'est pas attestee dans le texte
                             (moins de la moitie de ses mots porteurs de sens y figurent,
                             ou un de ses nombres en est absent) -> citation inventee.
                             Une preuve vide ou une note systeme ("V7.5 recovered entity ->")
                             n'est pas une citation : la relation est alors jugee sur G5.
  G3 NEGATED_ENDPOINT        une extremite est marquee `nie=True` alors que la relation
                             l'affirme -> contradiction interne.
  G5 NO_LOCAL_COOCCURRENCE   les deux extremites (hors noeud patient) ne sont jamais citees
                             a moins de COOCCURRENCE_WINDOW caracteres l'une de l'autre dans
                             le texte -> lien invente entre deux entites reelles.
  G4 DUPLICATE (option)      meme triplet (sujet, relation, objet) normalise qu'une relation
                             deja gardee. Desactive par defaut : le gold compte les mentions
                             repetees, ce n'est pas une hallucination. Activer avec --dedupe.

Toutes les regles et le seuil (1/2) sont fixes a priori : AUCUN acces au gold standard,
aucun seuil optimise sur le gold. L'entree n'est jamais modifiee.

Sorties
-------
  grounding_gate_safe/<doc>.json                  JSON filtres (+ champ grounding_gate_trace)
  reports/grounding_gate_removed_relations.csv    chaque relation retiree et sa regle
  reports/grounding_gate_summary.json             compteurs par regle et par document

Usage :
    python grounding_gate.py            # filtre G1+G2+G3+G5
    python grounding_gate.py --dedupe   # ajoute G4
    python grounding_gate.py --dry-run  # rapports seulement, aucun JSON ecrit
"""
import csv
import json
import re
import shutil
import sys
import unicodedata
from collections import Counter
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
INPUT_DIR = PROJECT / "confidence Etage 8" / "confidence_assessed_safe"
RAW_TEXT_DIR = PROJECT / "Sortie_Textes_Brut_MistralSmall4"
OUTPUT_DIR = HERE / "grounding_gate_safe"
REPORT_DIR = HERE / "reports"

# Fraction minimale de mots porteurs de sens qui doivent figurer dans le texte source.
# Fixee a priori (majorite simple), jamais ajustee sur le gold.
MIN_TOKEN_COVERAGE = 0.5
PREFIX_LEN = 5          # tolere flexions/accords : "asthenie" ~ "asthenique"
# Distance maximale (caracteres du texte normalise) entre deux extremites liees : environ un
# paragraphe de compte rendu. Fixee a priori, jamais ajustee sur le gold.
COOCCURRENCE_WINDOW = 300

PLACEHOLDER_RE = re.compile(r"^\s*V\d+(\.\d+)?\b.*->|recovered entity", re.IGNORECASE)

PATIENT_RE = re.compile(r"^(le |la |l )?patiente?s?$")
PATIENT_TYPES = {"DONNEE_PATIENT"}

STOPWORDS = set("""
le la les l un une des du de d et ou a au aux en dans par pour sur sous avec sans
ce cet cette ces se sa son ses leur leurs il elle ils elles on est sont ete etre
qui que quoi dont y ne pas plus tres puis lors apres avant entre chez
""".split())


# ------------------------------------------------------------------ texte
def norm(text):
    text = unicodedata.normalize("NFD", str(text or "").lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def content_tokens(text):
    return [t for t in norm(text).split() if t not in STOPWORDS and (len(t) >= 3 or t.isdigit())]


class SourceIndex:
    """Vocabulaire du document source, pour verifier qu'un mot y est atteste."""

    def __init__(self, text):
        self.text = norm(text)
        self.positions = {}
        for m in re.finditer(r"\S+", self.text):
            self.positions.setdefault(m.group(), []).append(m.start())
        self.tokens = set(self.positions)
        self.prefixes = {t[:PREFIX_LEN] for t in self.tokens if len(t) >= PREFIX_LEN}
        self.numbers = set(re.findall(r"\d+", self.text))

    def has_token(self, tok):
        if tok in self.tokens:
            return True
        if tok.isdigit():
            return tok in self.numbers
        return len(tok) >= PREFIX_LEN and tok[:PREFIX_LEN] in self.prefixes

    def coverage(self, text):
        toks = content_tokens(text)
        if not toks:
            return None
        return sum(self.has_token(t) for t in toks) / len(toks)

    def attests(self, text):
        n = norm(text)
        if n and n in self.text:
            return True
        cov = self.coverage(text)
        if cov is None or cov < MIN_TOKEN_COVERAGE:
            return False
        # un nombre absent du document (dose, valeur biologique) suffit a invalider
        return all(num in self.numbers for num in re.findall(r"\d+", n))

    def locate(self, text):
        """Positions ou l'entite est citee (forme complete, sinon ses mots porteurs de sens)."""
        n = norm(text)
        pos = [m.start() for m in re.finditer(re.escape(n), self.text)] if n else []
        if pos:
            return pos
        for tok in content_tokens(text):
            if tok in self.positions:
                pos.extend(self.positions[tok])
            elif not tok.isdigit() and len(tok) >= PREFIX_LEN:
                for t, p in self.positions.items():
                    if t[:PREFIX_LEN] == tok[:PREFIX_LEN]:
                        pos.extend(p)
        return sorted(pos)

    def cooccur(self, a, b, window=COOCCURRENCE_WINDOW):
        pa, pb = self.locate(a), self.locate(b)
        if not pa or not pb:
            return False
        i = j = 0
        while i < len(pa) and j < len(pb):
            if abs(pa[i] - pb[j]) <= window:
                return True
            if pa[i] < pb[j]:
                i += 1
            else:
                j += 1
        return False


def doc_key(path):
    return path.name.split("_trace_")[0]


def source_text(data, path):
    parts = [p.get("texte_brut", "") for p in data.get("pages", []) or [] if isinstance(p, dict)]
    raw = RAW_TEXT_DIR / f"{doc_key(path)}_brut.txt"
    if raw.exists():
        parts.append(raw.read_text(encoding="utf-8-sig", errors="replace"))
    return "\n".join(parts)


# ------------------------------------------------------------------ regles
def entity_name(ent, rel, side):
    if ent:
        for k in ("name", "preuve", "parametre"):
            if ent.get(k):
                return str(ent[k])
    keys = ("entite_sujet", "subject") if side == "subject" else ("entite_objet", "object")
    return str(next((rel[k] for k in keys if rel.get(k)), ""))


def is_patient(name, ent):
    return PATIENT_RE.match(norm(name)) is not None or (ent or {}).get("type") in PATIENT_TYPES \
        or (ent or {}).get("categorie") in PATIENT_TYPES


def check_relation(rel, entities, src):
    reasons, names, grounded_others = [], {}, []
    for side, id_key in (("subject", "identifiant_entite_sujet"), ("object", "identifiant_entite_objet")):
        ent = entities.get(rel.get(id_key))
        name = entity_name(ent, rel, side)
        names[side] = name
        if ent and ent.get("nie") is True:
            reasons.append(f"G3_NEGATED_ENDPOINT:{side}")
        if is_patient(name, ent):
            continue
        if src.attests(name):
            grounded_others.append(name)
        else:
            reasons.append(f"G1_ENDPOINT_NOT_IN_SOURCE:{side}")
    preuve = str(rel.get("preuve") or "")
    if preuve.strip() and not PLACEHOLDER_RE.search(preuve) and not src.attests(preuve):
        reasons.append("G2_FABRICATED_EVIDENCE")
    if len(grounded_others) == 2 and not src.cooccur(*grounded_others):
        reasons.append("G5_NO_LOCAL_COOCCURRENCE")
    return reasons, names


# ------------------------------------------------------------------ main
def main():
    argv = sys.argv[1:]
    dedupe = "--dedupe" in argv
    dry = "--dry-run" in argv

    files = sorted(INPUT_DIR.glob("*.json"))
    if not files:
        print(f"ECHEC : aucun JSON dans {INPUT_DIR}")
        return 2

    print("=" * 100)
    print("TRACE - ETAGE 8b - GROUNDING GATE")
    print("=" * 100)
    print(f"Entree  : {INPUT_DIR} ({len(files)} documents)")
    print(f"Sortie  : {OUTPUT_DIR}{'  (dry-run : rien ecrit)' if dry else ''}")
    print(f"Regles  : G1 G2 G3 G5{' G4' if dedupe else ''} | couverture min = {MIN_TOKEN_COVERAGE}"
          f" | fenetre = {COOCCURRENCE_WINDOW} car.")

    if not dry:
        if OUTPUT_DIR.exists():
            shutil.rmtree(OUTPUT_DIR)       # derive et regenerable
        OUTPUT_DIR.mkdir(parents=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    removed_rows, per_doc = [], {}
    by_rule, total_before, total_after = Counter(), 0, 0
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict) or not isinstance(data.get("global_relations"), list):
            if not dry:
                shutil.copy2(path, OUTPUT_DIR / path.name)
            continue
        src = SourceIndex(source_text(data, path))
        entities = {e.get("identifiant_entite"): e for e in data.get("global_entities", []) or []
                    if isinstance(e, dict)}

        kept, removed_ids, seen = [], set(), set()
        doc_rules = Counter()
        for rel in data["global_relations"]:
            if not isinstance(rel, dict):
                kept.append(rel)
                continue
            reasons, names = check_relation(rel, entities, src)
            triple = (norm(names["subject"]), str(rel.get("type_relation") or ""), norm(names["object"]))
            if dedupe and not reasons and triple in seen:
                reasons.append("G4_DUPLICATE")
            if reasons:
                rid = rel.get("identifiant_relation")
                if rid:
                    removed_ids.add(rid)
                for r in {x.split(":")[0] for x in reasons}:
                    doc_rules[r] += 1
                removed_rows.append([doc_key(path), rid, names["subject"], rel.get("type_relation"),
                                     names["object"], " | ".join(reasons), rel.get("type_inference"),
                                     (rel.get("trace_confidence") or {}).get("level"),
                                     str(rel.get("preuve") or "").replace("\n", " ")[:300]])
            else:
                seen.add(triple)
                kept.append(rel)

        n_before, n_after = len(data["global_relations"]), len(kept)
        data["global_relations"] = kept
        for page in data.get("pages", []) or []:
            if isinstance(page, dict) and isinstance(page.get("relations"), list):
                page["relations"] = [r for r in page["relations"]
                                     if not (isinstance(r, dict) and r.get("identifiant_relation") in removed_ids)]
        data["grounding_gate_trace"] = {
            "operation": "REMOVE_UNGROUNDED_RELATIONS",
            "regles": ["G1_ENDPOINT_NOT_IN_SOURCE", "G2_FABRICATED_EVIDENCE", "G3_NEGATED_ENDPOINT",
                       "G5_NO_LOCAL_COOCCURRENCE"]
                      + (["G4_DUPLICATE"] if dedupe else []),
            "couverture_min": MIN_TOKEN_COVERAGE,
            "fenetre_cooccurrence": COOCCURRENCE_WINDOW,
            "gold_utilise": False,
            "relations_avant": n_before,
            "relations_retirees": n_before - n_after,
            "par_regle": dict(doc_rules),
        }
        if not dry:
            (OUTPUT_DIR / path.name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        by_rule.update(doc_rules)
        total_before += n_before
        total_after += n_after
        per_doc[doc_key(path)] = {"avant": n_before, "apres": n_after, "par_regle": dict(doc_rules)}
        print(f"[OK] {doc_key(path)} | relations {n_before} -> {n_after} | {dict(doc_rules) or '-'}")

    with open(REPORT_DIR / "grounding_gate_removed_relations.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["document", "identifiant_relation", "sujet", "type_relation", "objet",
                    "regles", "type_inference", "niveau_confiance", "preuve"])
        w.writerows(removed_rows)
    summary = {"documents": len(per_doc), "relations_avant": total_before, "relations_apres": total_after,
               "relations_retirees": total_before - total_after, "par_regle": dict(by_rule),
               "dedupe": dedupe, "couverture_min": MIN_TOKEN_COVERAGE,
               "fenetre_cooccurrence": COOCCURRENCE_WINDOW, "gold_utilise": False,
               "par_document": per_doc}
    (REPORT_DIR / "grounding_gate_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 100)
    print(f"Relations : {total_before} -> {total_after}  (retirees : {total_before - total_after})")
    for rule, n in sorted(by_rule.items()):
        print(f"  {rule:28} {n}")
    print("(une relation peut violer plusieurs regles)")
    print(f"Rapports : {REPORT_DIR}")
    print("GROUNDING GATE ETAGE 8b : PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
