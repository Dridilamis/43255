# -*- coding: utf-8 -*-
"""
TRACE - SGCE - AGENTS SPECIALISES (aucun LLM, aucun acces au gold)

Chaque agent regarde une relation sous un angle different et rend des SIGNAUX (pas une
decision). L'agregateur (vote_agents.py) apprend ensuite comment combiner ces signaux.

  SectionAgent     dans quelle section du compte rendu la relation est-elle attestee ?
                   (antecedents, traitements habituels, histoire, examen, biologie,
                   evolution, conclusion, prescription de sortie...)
  NegationAgent    l'extremite clinique est-elle precedee, dans sa phrase, d'une negation
                   ("pas de", "absence de", "elimine"...) ou d'une hypothese
                   ("suspicion de", "a discuter", "probable"...) ?
  ProximityAgent   a quelle distance les deux extremites sont-elles citees (meme ligne,
                   meme paragraphe, loin) ?
  ProvenanceAgent  qu'en disent les etages precedents (niveau de confiance de l'Etage 8,
                   type d'inference, preuve vide) ?
  RedundancyAgent  la relation repete-t-elle un triplet deja present ? l'entite est-elle
                   reliee plusieurs fois ?

Les agents reutilisent les outils d'ancrage de l'Etage 8b (grounding_gate.py) sans le modifier.
"""
import importlib.util
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]          # Agents_Specialises -> MultiAgent -> SGCE -> projet

_spec = importlib.util.spec_from_file_location(
    "grounding_gate", PROJECT / "grounding_gate Etage 8b" / "grounding_gate.py")
gg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gg)

norm = gg.norm

# ------------------------------------------------------------------ sections
# Titre de section normalise (debut de ligne) -> section canonique.
SECTION_HEADERS = [
    (r"motif de l hospitalisation", "MOTIF"),
    (r"antecedents|medicaux|chirurgicaux|familiaux|allergies|mode de vie", "ANTECEDENTS"),
    (r"traitements? habituels?|medicaments|traitements? a l entree", "TRAITEMENT_HABITUEL"),
    (r"histoire de la maladie", "HISTOIRE"),
    (r"examen|signes generaux", "EXAMEN"),
    (r"biologie|gaz du sang|iono|prot sang|enzy|numeration|hemogramme|hemostase|formule"
     r"|fibrinogene|tca|temps de quick|examens? (sanguins|urinaires)|ecg|radiographie"
     r"|examens complementaires", "BIOLOGIE_IMAGERIE"),
    (r"evolution|prise en charge|sur le plan", "EVOLUTION"),
    (r"conclusion", "CONCLUSION"),
    (r"prescription de sortie", "SORTIE"),
]
SECTION_RE = [(re.compile(r"^(" + p + r")\b"), s) for p, s in SECTION_HEADERS]
SECTIONS = ["DEBUT"] + sorted({s for _, s in SECTION_HEADERS})


class SectionMap:
    """Texte normalise ligne par ligne, avec la section de chaque position."""

    def __init__(self, raw_text):
        self.text_parts, self.starts, self.sections = [], [], []
        pos, current = 0, "DEBUT"
        for line in raw_text.splitlines():
            n = norm(line)
            if not n:
                continue
            if len(n) <= 60:
                for rx, sec in SECTION_RE:
                    if rx.match(n):
                        current = sec
                        break
            self.starts.append(pos)
            self.sections.append(current)
            self.text_parts.append(n)
            pos += len(n) + 1
        self.text = " ".join(self.text_parts)

    def section_at(self, pos):
        lo, hi = 0, len(self.starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.starts[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        return self.sections[lo] if self.sections else "DEBUT"

    def find(self, text):
        n = norm(text)
        if not n:
            return []
        return [m.start() for m in re.finditer(r"(?<![a-z0-9])" + re.escape(n) + r"(?![a-z0-9])", self.text)]


# ------------------------------------------------------------------ negation / hypothese
NEG_CUES = re.compile(r"\b(pas d[e ]?|pas de|ne .{0,20}pas|absence d[e ]?|aucune?|sans|nie|negati[fv]e?s?"
                      r"|elimine[e]?s?|non retrouve[e]?s?|disparition d[e ]?)\s*$")
HYP_CUES = re.compile(r"\b(suspicion d[e ]?|suspect[ee]?s?|evoque[e]?s?|possible|probable|eventuel(le)?"
                      r"|a eliminer|a discuter|hypothese d[e ]?|doute|risque d[e ]?)\s*$")
CUE_WINDOW = 40          # caracteres avant la mention, dans la meme ligne


class Agents:
    """Calcule les signaux des 5 agents pour toutes les relations d'un document."""

    def __init__(self, data, raw_text):
        self.data = data
        self.sm = SectionMap(raw_text)
        self.src = gg.SourceIndex(raw_text)
        self.entities = {e.get("identifiant_entite"): e for e in data.get("global_entities", []) or []
                         if isinstance(e, dict)}
        self.triples = Counter()
        self.entity_degree = Counter()
        for r in data.get("global_relations", []):
            s, o = self._names(r)
            self.triples[(norm(s), r.get("type_relation"), norm(o))] += 1
            self.entity_degree[r.get("identifiant_entite_sujet")] += 1
            self.entity_degree[r.get("identifiant_entite_objet")] += 1
        self._seen = Counter()

    def _names(self, rel):
        s = gg.entity_name(self.entities.get(rel.get("identifiant_entite_sujet")), rel, "subject")
        o = gg.entity_name(self.entities.get(rel.get("identifiant_entite_objet")), rel, "object")
        return s, o

    def _clinical_endpoint(self, rel):
        """L'extremite qui porte l'information clinique (pas le noeud patient)."""
        s, o = self._names(rel)
        se = self.entities.get(rel.get("identifiant_entite_sujet"))
        oe = self.entities.get(rel.get("identifiant_entite_objet"))
        if gg.is_patient(s, se):
            return o, gg.is_patient(o, oe), s
        return s, gg.is_patient(o, oe), o

    def _anchor(self, rel, clinical):
        """Position de la relation dans le texte : sa preuve, sinon son extremite clinique."""
        preuve = str(rel.get("preuve") or "")
        if preuve and not gg.PLACEHOLDER_RE.search(preuve):
            pos = self.sm.find(preuve)
            if pos:
                return pos[0], "preuve"
        pos = self.sm.find(clinical)
        if pos:
            return pos[0], "entite"
        return None, "absente"

    def signals(self, rel):
        clinical, other_is_patient, other = self._clinical_endpoint(rel)
        anchor, how = self._anchor(rel, clinical)
        sig = {}

        # SectionAgent
        sec = self.sm.section_at(anchor) if anchor is not None else "INCONNUE"
        sig["section"] = sec
        sig["ancrage"] = how

        # NegationAgent : indices juste avant les mentions de l'extremite clinique
        neg = hyp = False
        for p in self.sm.find(clinical) or []:
            before = self.sm.text[max(0, p - CUE_WINDOW):p]
            neg |= bool(NEG_CUES.search(before))
            hyp |= bool(HYP_CUES.search(before))
        sig["negation"] = neg
        sig["hypothese"] = hyp

        # ProximityAgent
        if other_is_patient:
            sig["distance"] = "PATIENT"
        else:
            pa, pb = self.src.locate(clinical), self.src.locate(other)
            if not pa or not pb:
                sig["distance"] = "INTROUVABLE"
            else:
                d = min(abs(a - b) for a in pa[:50] for b in pb[:50])
                sig["distance"] = "LIGNE" if d <= 80 else ("PARAGRAPHE" if d <= 300 else "LOIN")

        # ProvenanceAgent
        tc = rel.get("trace_confidence") or {}
        sig["niveau_8"] = str(tc.get("level") or "AUCUN")
        ti = str(rel.get("type_inference") or "aucune")
        sig["inference"] = "directe" if ti == "extraction_directe" else (
            "structurelle" if "structurel" in ti else "autre")
        sig["preuve_vide"] = not str(rel.get("preuve") or "").strip()

        # RedundancyAgent
        s, o = self._names(rel)
        key = (norm(s), rel.get("type_relation"), norm(o))
        self._seen[key] += 1
        sig["doublon"] = self._seen[key] > 1
        ent_id = rel.get("identifiant_entite_objet") if gg.is_patient(
            s, self.entities.get(rel.get("identifiant_entite_sujet"))) else rel.get("identifiant_entite_sujet")
        sig["entite_multi_liee"] = self.entity_degree[ent_id] > 1
        sig["type_relation"] = str(rel.get("type_relation") or "")
        return sig


def raw_text_for(data, path):
    raw = gg.RAW_TEXT_DIR / f"{gg.doc_key(Path(path))}_brut.txt"
    if raw.exists():
        return raw.read_text(encoding="utf-8-sig", errors="replace")
    return "\n".join(p.get("texte_brut", "") for p in data.get("pages", []) or [] if isinstance(p, dict))
