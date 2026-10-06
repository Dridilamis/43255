# -*- coding: utf-8 -*-
"""
negation_candidate_builder.py
=============================

TRACE / SGCE - NEGATION CANDIDATE BUILDER

Corrections principales :
- amÃ©liore fortement la localisation de l'entitÃ© dans le texte ;
- essaye plusieurs variantes de mention ;
- normalise accents, apostrophes et espaces ;
- conserve les offsets de la mention rÃ©ellement retrouvÃ©e ;
- marque explicitement mention_found=False si aucune localisation fiable ;
- ne modifie aucune donnÃ©e clinique.

Baseline :
  MultiAgent/numeric_unit/numeric_unit_safe_corrected_repaired
"""

import json
import re
import unicodedata
from pathlib import Path
from collections import Counter

BASE_DIR = Path(
    r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM"
    r"\Reduction_hallucinations"
)

CLINICAL_DIR = (
    BASE_DIR / "temporal Etage 6" / "temporal_status_safe_corrected"
)

TEXT_DIR = (
    BASE_DIR / "Sortie_Textes_Brut_MistralSmall4"
)

OUTPUT_FILE = (
    BASE_DIR / "negation Etage 7"
    / "queues"
    / "negation_candidates.json"
)

OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

NEGATION_PATTERNS = [
    r"\babsence\s+d(?:e|['â€™])\b",
    r"\ben\s+l['â€™]absence\s+d(?:e|['â€™])\b",
    r"\bsans\b",
    r"\bpas\s+d(?:e|['â€™])\b",
    r"\baucun(?:e)?\b",
    r"\bne\s+retrouve\s+pas\b",
    r"\bne\s+retrouve\s+aucun(?:e)?\b",
    r"\bnon\s+retrouv[Ã©e]?\b",
    r"\bnon\s+objectiv[Ã©e]?\b",
    r"\bnÃ©gatif(?:ve)?\b",
]

def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def norm(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("â€™", "'").replace("`", "'")
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()

def entity_id(e):
    return e.get("identifiant_entite") or e.get("id") or e.get("entity_id")

def entity_type(e):
    return e.get("categorie") or e.get("type") or e.get("entity_type") or ""

def mention_variants(e):
    vals = []

    for key in (
        "preuve", "texte", "text", "nom", "name",
        "libelle", "contenu", "valeur"
    ):
        v = e.get(key)
        if v not in (None, ""):
            v = str(v).strip()
            if v and v not in vals:
                vals.append(v)

    # Les chaÃ®nes composites "CRP 245 mg/L" â†’ variantes plus courtes.
    extra = []
    for v in list(vals):
        if len(v) > 8:
            # supprime ponctuation pÃ©riphÃ©rique
            vv = v.strip(" -:;,.()[]")
            if vv and vv not in vals and vv not in extra:
                extra.append(vv)

            # si "paramÃ¨tre : valeur", garde chaque cÃ´tÃ©
            for sep in (":", "=", "â†’", "->"):
                if sep in v:
                    parts = [x.strip() for x in v.split(sep) if x.strip()]
                    for p in parts:
                        if len(p) >= 3 and p not in vals and p not in extra:
                            extra.append(p)

    vals.extend(extra)

    # PrioritÃ© aux mentions plus longues.
    vals = sorted(
        list(dict.fromkeys(vals)),
        key=lambda x: len(x),
        reverse=True
    )

    return vals

def get_context_status(e):
    value = e.get("trace_context_status")
    return value if isinstance(value, dict) else {}

def get_entities(doc):
    if isinstance(doc.get("global_entities"), list):
        return doc["global_entities"]

    return [
        e
        for page in doc.get("pages", []) or []
        for e in page.get("entities", []) or []
    ]

def is_clinical(path):
    if path.name.endswith("_report.json"):
        return False
    try:
        doc = load_json(path)
    except Exception:
        return False
    return isinstance(doc, dict) and any(
        k in doc for k in ("pages", "global_entities", "global_relations")
    )

def find_text_file(document_name):
    stem = Path(document_name).stem

    exact = list(TEXT_DIR.glob(f"{stem}*.txt"))
    if exact:
        return exact[0]

    short = stem.split("_trace_sepsis")[0]
    partial = list(TEXT_DIR.glob(f"{short}*.txt"))
    return partial[0] if partial else None

def sentence_spans(text):
    """
    Retourne des phrases/lignes avec offsets dans le texte original.
    """
    spans = []
    start = 0

    for m in re.finditer(r"(?<=[\.\!\?\;\n])\s+", text):
        end = m.start()
        chunk = text[start:end].strip()
        if chunk:
            real_start = start + (len(text[start:end]) - len(text[start:end].lstrip()))
            spans.append((chunk, real_start, real_start + len(chunk)))
        start = m.end()

    tail = text[start:].strip()
    if tail:
        real_start = start + (len(text[start:]) - len(text[start:].lstrip()))
        spans.append((tail, real_start, real_start + len(tail)))

    return spans

def find_context(text, entity):
    """
    Localisation robuste :
    - cherche les variantes dans le texte normalisÃ© ;
    - utilise la premiÃ¨re correspondance exacte normalisÃ©e ;
    - retourne les offsets dans la phrase locale.
    """
    variants = mention_variants(entity)
    spans = sentence_spans(text)

    for sentence, s_start, s_end in spans:
        ns = norm(sentence)

        for mention in variants:
            nm = norm(mention)

            if len(nm) < 3:
                continue

            pos = ns.find(nm)

            if pos != -1:
                # Les offsets normalisÃ©s peuvent diverger lÃ©gÃ¨rement de l'original.
                # On tente d'abord la recherche directe insensible Ã  la casse.
                direct = sentence.lower().find(mention.lower())

                if direct != -1:
                    m_start = direct
                    m_end = direct + len(mention)
                else:
                    # fallback approximatif uniquement pour scope local,
                    # mais on marque match_quality=NORMALIZED.
                    m_start = pos
                    m_end = min(len(sentence), pos + len(mention))

                return {
                    "sentence": sentence,
                    "mention": mention,
                    "mention_start": m_start,
                    "mention_end": m_end,
                    "match_quality": (
                        "EXACT"
                        if direct != -1
                        else "NORMALIZED"
                    ),
                }

    return None

def has_negation_cue(sentence):
    if not sentence:
        return False
    return any(
        re.search(p, sentence, flags=re.IGNORECASE)
        for p in NEGATION_PATTERNS
    )

def main():
    candidates = []
    docs = 0
    reasons = Counter()
    missing_texts = 0
    mention_found = 0
    mention_not_found = 0

    for path in sorted(CLINICAL_DIR.glob("*.json")):
        if not is_clinical(path):
            continue

        docs += 1
        doc = load_json(path)

        text_file = find_text_file(path.name)

        if text_file:
            text = text_file.read_text(
                encoding="utf-8",
                errors="ignore",
            )
        else:
            text = ""
            missing_texts += 1

        seen = set()

        for entity in get_entities(doc):
            eid = entity_id(entity)

            if eid is None:
                continue

            key = str(eid)

            if key in seen:
                continue

            seen.add(key)

            ctx_status = get_context_status(entity)
            current_status = ctx_status.get("clinical_status")

            context = find_context(text, entity) if text else None

            if context:
                mention_found += 1
                sentence = context["sentence"]
                cue_present = has_negation_cue(sentence)
            else:
                mention_not_found += 1
                sentence = ""
                cue_present = False

            selection_reasons = []

            if str(current_status).upper() == "NEGATED":
                selection_reasons.append("CURRENTLY_NEGATED")

            if cue_present:
                selection_reasons.append("LOCAL_NEGATION_CUE")

            if not selection_reasons:
                continue

            for reason in selection_reasons:
                reasons[reason] += 1

            candidates.append({
                "candidate_id": f"NGR_{len(candidates)+1:06d}",
                "document": path.name,
                "entity_id": eid,
                "entity_type": entity_type(entity),
                "entity_text": context["mention"] if context else (
                    mention_variants(entity)[0]
                    if mention_variants(entity)
                    else ""
                ),
                "current_clinical_status": current_status,
                "current_temporal_status": ctx_status.get("temporal_status"),
                "selection_reasons": selection_reasons,
                "mention_found": bool(context),
                "match_quality": (
                    context["match_quality"]
                    if context
                    else None
                ),
                "sentence": sentence,
                "mention_start": (
                    context["mention_start"]
                    if context
                    else None
                ),
                "mention_end": (
                    context["mention_end"]
                    if context
                    else None
                ),
                "text_file": str(text_file) if text_file else None,
            })

    payload = {
        "builder": "negation_candidate_builder",
        "mode": "CONSERVATIVE_V3_EXACT_MENTION",
        "clinical_directory": str(CLINICAL_DIR),
        "summary": {
            "documents_analysed": docs,
            "candidates_built": len(candidates),
            "selection_reason_counts": dict(reasons),
            "missing_texts": missing_texts,
            "mentions_found": mention_found,
            "mentions_not_found": mention_not_found,
        },
        "candidates": candidates,
    }

    OUTPUT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("=" * 112)
    print("TRACE / SGCE - NEGATION CANDIDATE BUILDER")
    print("=" * 112)
    print(f"Documents analysÃ©s                 : {docs}")
    print(f"Candidats construits               : {len(candidates)}")
    print(f"Mentions retrouvÃ©es                : {mention_found}")
    print(f"Mentions non retrouvÃ©es            : {mention_not_found}")
    print(f"Textes manquants                   : {missing_texts}")
    print()
    print("RAISONS DE SELECTION")
    print("-" * 112)
    for k, v in reasons.items():
        print(f"{k:<52}: {v}")
    print()
    print(f"Sortie                             : {OUTPUT_FILE}")
    print()
    print("Aucune donnÃ©e clinique n'a Ã©tÃ© modifiÃ©e.")

if __name__ == "__main__":
    main()

