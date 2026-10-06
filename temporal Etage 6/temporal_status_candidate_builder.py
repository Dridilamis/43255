# -*- coding: utf-8 -*-
"""
temporal_status_candidate_builder.py
====================================

TRACE / SGCE - TEMPORAL / STATUS AUTONOMOUS FULL TEMPORAL AUDIT

But :
- reprendre uniquement les 2 REVIEW du repair prÃ©cÃ©dent ;
- ajouter les entitÃ©s dont temporal_status = UNKNOWN ;
- rÃ©cupÃ©rer le contexte textuel exact depuis les fichiers TXT ;
- ne pas toucher aux 1311 KEEP dÃ©jÃ  stables sauf si leur temporalitÃ© est UNKNOWN.

Aucune donnÃ©e clinique n'est modifiÃ©e.
"""

import json
import re
from pathlib import Path
from collections import Counter

BASE_DIR = Path(
    r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM"
    r"\Reduction_hallucinations"
)

CLINICAL_DIR = (
    BASE_DIR / "numeric_unit Etage 5"
    / "numeric_unit_safe_corrected"
)


TEXT_DIR = (
    BASE_DIR / "Sortie_Textes_Brut_MistralSmall4"
)

OUTPUT_FILE = (
    BASE_DIR / "temporal Etage 6"
    / "queues"
    / "temporal_status_candidates.json"
)

OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def entity_id(e):
    return e.get("identifiant_entite") or e.get("id") or e.get("entity_id")


def entity_text(e):
    for key in ("preuve", "texte", "text", "nom", "name", "contenu", "libelle"):
        value = e.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def entity_type(e):
    return e.get("categorie") or e.get("type") or e.get("entity_type") or ""


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


def get_annotation(e):
    for key in (
        "trace_context_status",
        "trace_temporal_status",
        "trace_temporal_status_audit",
        "temporal_status_annotation",
    ):
        value = e.get(key)
        if isinstance(value, dict):
            return key, value
    return None, None


def get_entities(doc):
    if isinstance(doc.get("global_entities"), list):
        return doc["global_entities"]
    return [
        e
        for page in doc.get("pages", []) or []
        for e in page.get("entities", []) or []
    ]


def normalize_doc_key(name):
    """Construit une clÃ© documentaire stable sans supposer des suffixes identiques JSON/TXT."""
    stem = Path(name).stem.lower()
    stem = re.sub(r"_trace_sepsis.*$", "", stem)
    stem = re.sub(r"(?:_page|_p)[-_ ]?\d+$", "", stem)
    return re.sub(r"[^a-z0-9]+", "", stem)


def build_text_index():
    """Indexe une seule fois tous les TXT du corpus brut."""
    index = {}
    if not TEXT_DIR.exists():
        return index
    for txt in TEXT_DIR.rglob("*.txt"):
        key = normalize_doc_key(txt.name)
        if key:
            index.setdefault(key, []).append(txt)
    return index


def find_text_file(document_name, text_index):
    key = normalize_doc_key(document_name)
    matches = text_index.get(key, [])
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        # dÃ©terministe : fichier dont le stem partage le plus long prÃ©fixe avec le document
        docstem = Path(document_name).stem.lower()
        return sorted(matches, key=lambda p: (-len(__import__('os').path.commonprefix([docstem, p.stem.lower()])), str(p)))[0]

    # secours conservateur par identifiant de document avant _trace_sepsis
    short = Path(document_name).stem.lower().split("_trace_sepsis")[0]
    partial = sorted(TEXT_DIR.rglob(f"{short}*.txt")) if TEXT_DIR.exists() else []
    return partial[0] if len(partial) == 1 else None


TEMPORAL_CUE_RX = re.compile(
    r"(?:\bant[Ã©e]c[Ã©e]dent(?:s)?\b|\bhistoire de\b|\bancien(?:ne)?\b|"
    r"\bant[Ã©e]rieur(?:e)?\b|\bavait pr[Ã©e]sent[Ã©e]\b|\bconnu(?:e)? pour\b|"
    r"\b(?:Ã |a|lors de) l['â€™]admission\b|\b(?:Ã |a) l['â€™]entr[Ã©e]e\b|"
    r"\bdurant l['â€™]hospitalisation\b|\bpendant l['â€™]hospitalisation\b|"
    r"\bau cours (?:de l['â€™]hospitalisation|du s[Ã©e]jour)\b|\bpendant le s[Ã©e]jour\b|"
    r"\ben r[Ã©e]animation\b|\bapr[Ã¨e]s (?:traitement|antibioth[Ã©e]rapie|introduction|instauration|administration)\b|"
    r"\bsous traitement\b|\bdepuis\b|\bavant\b|\bapr[Ã¨e]s\b|\bactuellement\b|"
    r"\baujourd['â€™]hui\b|\bhier\b|\bdemain\b|\bJ[+-]?\d+\b|"
    r"\b\d{1,2}[/-]\d{1,2}[/-](?:\d{2}|\d{4})\b|\b(?:19|20)\d{2}\b)",
    re.IGNORECASE,
)


def has_temporal_cue(ctx):
    local = " ".join([
        str(ctx.get("previous_sentence") or ""),
        str(ctx.get("sentence") or ""),
        str(ctx.get("next_sentence") or ""),
    ])
    return bool(TEMPORAL_CUE_RX.search(local))

def split_sentences(text):
    if not text:
        return []

    # conserve les lignes cliniques comme unitÃ©s locales quand possible
    chunks = re.split(
        r"(?<=[\.\!\?\;\n])\s+",
        text
    )

    return [
        x.strip()
        for x in chunks
        if x.strip()
    ]


def find_best_context(sentences, mention):
    if not mention:
        return None

    low_mention = mention.lower()

    matches = []

    for i, sentence in enumerate(sentences):
        pos = sentence.lower().find(low_mention)

        if pos != -1:
            matches.append((i, pos, sentence))

    if not matches:
        return None

    i, pos, sentence = matches[0]

    return {
        "sentence_index": i,
        "sentence": sentence,
        "previous_sentence": sentences[i - 1] if i > 0 else "",
        "next_sentence": sentences[i + 1] if i + 1 < len(sentences) else "",
        "mention_start": pos,
        "mention_end": pos + len(mention),
    }



def main():
    candidates = []
    docs = 0
    reason_counts = Counter()
    missing_text_docs = 0
    mention_not_found = 0
    entities_audited = 0
    docs_with_text = 0
    text_index = build_text_index()

    for path in sorted(CLINICAL_DIR.glob("*.json")):
        if not is_clinical(path):
            continue

        doc = load_json(path)
        docs += 1

        text_file = find_text_file(path.name, text_index)

        if text_file:
            docs_with_text += 1
            text = text_file.read_text(
                encoding="utf-8",
                errors="ignore",
            )
            sentences = split_sentences(text)
        else:
            missing_text_docs += 1
            text = ""
            sentences = []

        for e in get_entities(doc):
            entities_audited += 1
            eid = entity_id(e)
            if eid is None:
                continue

            annotation_key, ann = get_annotation(e)
            ann = ann if isinstance(ann, dict) else {}

            temporal_status = (
                ann.get("temporal_status")
                or ann.get("temporality")
                or ann.get("statut_temporel")
            )

            clinical_status = (
                ann.get("clinical_status")
                or ann.get("status")
                or ann.get("statut_clinique")
            )

            mention = entity_text(e)
            ctx = find_best_context(sentences, mention)

            if ctx is None:
                mention_not_found += 1
                ctx = {
                    "sentence_index": None, "sentence": "",
                    "previous_sentence": "", "next_sentence": "",
                    "mention_start": None, "mention_end": None,
                }

            # Une absence d'annotation temporelle n'est PAS une anomalie.
            # On ne crÃ©e un candidat que si le texte local porte un indice temporel
            # ou si une annotation temporelle existante mÃ©rite un audit.
            if temporal_status not in (None, ""):
                if str(temporal_status).upper() == "UNKNOWN":
                    selection_reason = "TEMPORAL_UNKNOWN_WITH_CONTEXT" if has_temporal_cue(ctx) else "TEMPORAL_UNKNOWN"
                else:
                    selection_reason = "AUDIT_EXISTING_TEMPORAL_STATUS"
            elif has_temporal_cue(ctx):
                selection_reason = "EXPLICIT_TEMPORAL_CONTEXT"
            else:
                continue

            reason_counts[selection_reason] += 1

            candidates.append({
                "candidate_id":
                    f"TSR_{len(candidates)+1:06d}",

                "document":
                    path.name,

                "entity_id":
                    eid,

                "entity_type":
                    entity_type(e),

                "entity_text":
                    mention,

                "annotation_key":
                    annotation_key,

                "selection_reason":
                    selection_reason,

                "current_clinical_status":
                    clinical_status,

                "current_temporal_status":
                    temporal_status,

                "sentence":
                    ctx["sentence"],

                "previous_sentence":
                    ctx["previous_sentence"],

                "next_sentence":
                    ctx["next_sentence"],

                "mention_start":
                    ctx["mention_start"],

                "mention_end":
                    ctx["mention_end"],

                "text_file":
                    str(text_file) if text_file else None,
            })

    payload = {
        "builder":
            "temporal_status_candidate_builder",

        "mode":
            "TEXT_GUIDED_SAFE_REPAIR",

        "summary": {
            "documents_analysed":
                docs,

            "candidates_built":
                len(candidates),

            "selection_reason_counts":
                dict(reason_counts),

            "entities_audited": entities_audited,
            "documents_with_text": docs_with_text,
            "documents_text_missing": missing_text_docs,
            "mentions_not_found": mention_not_found,
        },

        "candidates":
            candidates,
    }

    OUTPUT_FILE.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=" * 112)
    print("TRACE / SGCE - TEMPORAL STATUS CANDIDATE BUILDER - AUTONOMOUS FULL TEMPORAL AUDIT")
    print("=" * 112)
    print(f"Documents analysÃ©s                 : {docs}")
    print(f"EntitÃ©s auditÃ©es                   : {entities_audited}")
    print(f"Documents avec texte retrouvÃ©      : {docs_with_text}")
    print(f"Documents sans texte               : {missing_text_docs}")
    print(f"Candidats temporels construits     : {len(candidates)}")
    for key, value in sorted(reason_counts.items()):
        print(f"{key:<36}: {value}")
    print(f"Mentions non retrouvÃ©es            : {mention_not_found}")
    print()
    print(f"Sortie                             : {OUTPUT_FILE}")
    print()
    print("Aucune donnÃ©e clinique n'a Ã©tÃ© modifiÃ©e.")


if __name__ == "__main__":
    main()

