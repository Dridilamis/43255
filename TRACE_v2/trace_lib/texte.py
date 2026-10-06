# -*- coding: utf-8 -*-
"""
Service TEXTE (unique) : normalisation, presence d'une mention dans le document source,
positions, distance entre deux mentions, section du compte rendu, indices de negation et
d'hypothese. Tous les etages passent par ce module ; aucun ne recode ces tests.
"""
import re
import unicodedata
from pathlib import Path

from . import config as C

STOPWORDS = set("""
le la les l un une des du de d et ou a au aux en dans par pour sur sous avec sans
ce cet cette ces se sa son ses leur leurs il elle ils elles on est sont ete etre
qui que quoi dont y ne pas plus tres puis lors apres avant entre chez
""".split())


def norm(text):
    """Minuscules, sans accents, ponctuation -> espace."""
    text = unicodedata.normalize("NFD", str(text or "").lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def content_tokens(text):
    return [t for t in norm(text).split() if t not in STOPWORDS and (len(t) >= 3 or t.isdigit())]


# ------------------------------------------------------------------ sections
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
_SECTION_RE = [(re.compile(r"^(" + p + r")\b"), s) for p, s in SECTION_HEADERS]

NEG_CUES = re.compile(r"\b(pas d[e ]?|pas de|ne .{0,20}pas|absence d[e ]?|aucune?|sans|nie|negati[fv]e?s?"
                      r"|elimine[e]?s?|non retrouve[e]?s?|disparition d[e ]?)\s*$")
HYP_CUES = re.compile(r"\b(suspicion d[e ]?|suspect[e]?s?|evoque[e]?s?|possible|probable|eventuel(le)?"
                      r"|a eliminer|a discuter|hypothese d[e ]?|doute|risque d[e ]?)\s*$")


class Document:
    """Texte source d'un document, indexe une seule fois pour tous les tests."""

    def __init__(self, raw_text):
        self.lines, self.starts, self.sections = [], [], []
        pos, current = 0, "DEBUT"
        for line in raw_text.splitlines():
            n = norm(line)
            if not n:
                continue
            if len(n) <= 60:
                for rx, sec in _SECTION_RE:
                    if rx.match(n):
                        current = sec
                        break
            self.lines.append(n)
            self.starts.append(pos)
            self.sections.append(current)
            pos += len(n) + 1
        self.text = " ".join(self.lines)
        self.positions = {}
        for m in re.finditer(r"\S+", self.text):
            self.positions.setdefault(m.group(), []).append(m.start())
        self.tokens = set(self.positions)
        self.prefixes = {t[:C.PREFIX_LEN] for t in self.tokens if len(t) >= C.PREFIX_LEN}
        self.numbers = set(re.findall(r"\d+", self.text))

    # -- presence
    def _has_token(self, tok):
        if tok in self.tokens:
            return True
        if tok.isdigit():
            return tok in self.numbers
        return len(tok) >= C.PREFIX_LEN and tok[:C.PREFIX_LEN] in self.prefixes

    def attests(self, text):
        """La mention figure-t-elle dans le texte (forme exacte, ou majorite de ses mots et
        tous ses nombres) ?"""
        n = norm(text)
        if n and n in self.text:
            return True
        toks = content_tokens(text)
        if not toks or sum(self._has_token(t) for t in toks) / len(toks) < C.MIN_TOKEN_COVERAGE:
            return False
        return all(num in self.numbers for num in re.findall(r"\d+", n))

    # -- positions
    def find_exact(self, text):
        n = norm(text)
        if not n:
            return []
        return [m.start() for m in re.finditer(r"(?<![a-z0-9])" + re.escape(n) + r"(?![a-z0-9])", self.text)]

    def locate(self, text):
        pos = self.find_exact(text)
        if pos:
            return pos
        for tok in content_tokens(text):
            if tok in self.positions:
                pos.extend(self.positions[tok])
            elif not tok.isdigit() and len(tok) >= C.PREFIX_LEN:
                for t, p in self.positions.items():
                    if t[:C.PREFIX_LEN] == tok[:C.PREFIX_LEN]:
                        pos.extend(p)
        return sorted(pos)

    def distance(self, a, b):
        """Plus petite distance (caracteres) entre une mention de a et une de b ; None si
        l'une est introuvable."""
        pa, pb = self.locate(a), self.locate(b)
        if not pa or not pb:
            return None
        i = j = 0
        best = None
        while i < len(pa) and j < len(pb):
            d = abs(pa[i] - pb[j])
            best = d if best is None else min(best, d)
            if pa[i] < pb[j]:
                i += 1
            else:
                j += 1
        return best

    # -- sections et indices
    def section_at(self, pos):
        if pos is None or not self.starts:
            return "INCONNUE"
        lo, hi = 0, len(self.starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.starts[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        return self.sections[lo]

    def cues_before(self, text):
        """(negation, hypothese) : un indice precede-t-il une mention exacte de `text` ?"""
        neg = hyp = False
        for p in self.find_exact(text):
            before = self.text[max(0, p - C.CUE_WINDOW):p]
            neg |= bool(NEG_CUES.search(before))
            hyp |= bool(HYP_CUES.search(before))
        return neg, hyp


def iter_page_lines(pages):
    """(page, section, ligne) pour chaque ligne non vide des pages, la section courante
    etant suivie d'une page a l'autre."""
    current = "DEBUT"
    for page in pages or []:
        if not isinstance(page, dict):
            continue
        for line in (page.get("texte_brut") or "").splitlines():
            n = norm(line)
            if not n:
                continue
            if len(n) <= 60:
                for rx, sec in _SECTION_RE:
                    if rx.match(n):
                        current = sec
                        break
            yield page, current, line.strip()


def doc_key(path):
    return Path(path).name.split("_trace_")[0]


def load_source(data, path):
    """Texte brut du document : fichier *_brut.txt, sinon pages[].texte_brut."""
    raw = C.RAW_TEXT_DIR / f"{doc_key(path)}_brut.txt"
    parts = []
    if raw.exists():
        parts.append(raw.read_text(encoding="utf-8-sig", errors="replace"))
    parts += [p.get("texte_brut", "") for p in data.get("pages", []) or [] if isinstance(p, dict)]
    return Document("\n".join(parts))
