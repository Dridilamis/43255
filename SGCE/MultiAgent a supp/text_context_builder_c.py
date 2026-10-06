# -*- coding: utf-8 -*-
"""
text_context_builder_c.py
=========================

TRACE / SGCE â€” Text Context Builder pour Pattern C

EntrÃ©e :
  MultiAgent/queues/agent_c_queue.json

Textes :
  MultiAgent/Sortie_Textes_Brut_MistralSmall4/*.txt

Sortie :
  MultiAgent/queues/agent_c_queue_contextualized.json

But :
- retrouver le TXT correspondant au document
- retrouver la page concernÃ©e
- ajouter le texte source au candidat C
- ne modifier aucun JSON clinique
"""

import json
import re
from pathlib import Path


BASE_DIR = Path(
    r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM"
    r"\Reduction_hallucinations"
)

MULTIAGENT_DIR = BASE_DIR / "MultiAgent"

QUEUE_FILE = (
    MULTIAGENT_DIR
    / "queues"
    / "agent_c_queue.json"
)

OUTPUT_FILE = (
    MULTIAGENT_DIR
    / "queues"
    / "agent_c_queue_contextualized.json"
)

TEXT_DIR_CANDIDATES = [
    MULTIAGENT_DIR
    / "Sortie_Textes_Brut_MistralSmall4"
]

MAX_CONTEXT_CHARS = 5000


def load_json(path):
    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


def normalize_name(name):
    name = Path(name).stem.lower()

    suffixes = [
        "_trace_sepsis_v1.6-v6.5-selective_precision",
        "_trace_sepsis_v1.6",
        "_trace_sepsis",
        "_selective_precision",
        "_mistral",
        "_qwen",
        "_brut",
    ]

    for suffix in suffixes:
        name = name.replace(
            suffix,
            "",
        )

    return re.sub(
        r"[^a-z0-9]+",
        "",
        name,
    )


def discover_text_files():
    files = []

    for directory in TEXT_DIR_CANDIDATES:
        if not directory.exists():
            print(
                f"[ATTENTION] Dossier texte introuvable : {directory}"
            )
            continue

        for path in directory.rglob("*.txt"):
            if path.is_file():
                files.append(path)

    return files


def find_text_file(
    document_name,
    text_files,
):
    target = normalize_name(
        document_name
    )

    exact = []

    for path in text_files:
        current = normalize_name(
            path.name
        )

        if current == target:
            exact.append(path)

    if exact:
        return sorted(exact)[0]

    candidates = []

    for path in text_files:
        current = normalize_name(
            path.name
        )

        if (
            target in current
            or current in target
        ):
            candidates.append(path)

    if len(candidates) == 1:
        return candidates[0]

    return None


def extract_page_number(item):
    symbolic = (
        item.get("symbolic_candidate")
        or {}
    )

    # 1. candidat rÃ©ifiÃ©
    for key in (
        "reified_entity",
        "entity",
        "candidate_entity",
        "middle_entity",
    ):
        value = symbolic.get(key)

        if isinstance(value, dict):
            page = (
                value.get("page")
                or value.get("page_number")
                or value.get("numero_page")
            )

            if page is not None:
                try:
                    return int(page)
                except Exception:
                    pass

            eid = (
                value.get("identifiant_entite")
                or value.get("id")
                or value.get("entity_id")
            )

            if eid:
                match = re.match(
                    r"P(\d+)_E\d+",
                    str(eid),
                )

                if match:
                    return int(
                        match.group(1)
                    )

    # 2. metadata possible
    metadata = item.get("metadata") or {}

    page = (
        metadata.get("page_number")
        or metadata.get("page")
    )

    if page is not None:
        try:
            return int(page)
        except Exception:
            pass

    # 3. symbolic direct
    page = (
        symbolic.get("page")
        or symbolic.get("page_number")
    )

    if page is not None:
        try:
            return int(page)
        except Exception:
            pass

    # 4. scan rÃ©cursif des IDs Pn_Exxx
    blob = json.dumps(
        symbolic,
        ensure_ascii=False,
    )

    match = re.search(
        r"\bP(\d+)_E\d+\b",
        blob,
    )

    if match:
        return int(
            match.group(1)
        )

    return None


def split_pages(text):
    patterns = [
        r"\n\s*={3,}\s*PAGE\s+(\d+)\s*={3,}\s*\n",
        r"\n\s*-{3,}\s*PAGE\s+(\d+)\s*-{3,}\s*\n",
        r"\n\s*PAGE\s+(\d+)\s*\n",
        r"\n\s*Page\s+(\d+)\s*\n",
        r"\n\s*\[PAGE\s+(\d+)\]\s*\n",
        r"\n\s*===\s*Page\s+(\d+)\s*===\s*\n",
    ]

    for pattern in patterns:
        matches = list(
            re.finditer(
                pattern,
                text,
                flags=re.I,
            )
        )

        if not matches:
            continue

        pages = {}

        for i, match in enumerate(matches):
            page_no = int(
                match.group(1)
            )

            start = match.end()

            end = (
                matches[i + 1].start()
                if i + 1 < len(matches)
                else len(text)
            )

            pages[page_no] = text[
                start:end
            ].strip()

        return pages

    if "\f" in text:
        parts = text.split("\f")

        return {
            i + 1: part.strip()
            for i, part in enumerate(parts)
            if part.strip()
        }

    return {
        1: text.strip()
    }


def compact_text(text):
    if not text:
        return ""

    if len(text) <= MAX_CONTEXT_CHARS:
        return text.strip()

    half = MAX_CONTEXT_CHARS // 2

    return (
        text[:half].strip()
        + "\n...\n"
        + text[-half:].strip()
    )


def main():
    if not QUEUE_FILE.exists():
        raise FileNotFoundError(
            f"Queue C introuvable : {QUEUE_FILE}"
        )

    queue = load_json(
        QUEUE_FILE
    )

    text_files = discover_text_files()

    contextualized = []

    found = 0
    explicit_page_found = 0
    global_fallback = 0
    missing = 0

    for item in queue:
        enriched = dict(item)

        document = item.get(
            "document",
            "",
        )

        page_number = extract_page_number(
            item
        )

        text_file = find_text_file(
            document,
            text_files,
        )

        context = {
            "text_file":
                None,

            "page_number":
                page_number,

            "page_text":
                "",

            "document_text_available":
                False,

            "page_text_available":
                False,

            "used_global_text_fallback":
                False,
        }

        if text_file is None:
            missing += 1
            enriched[
                "text_context"
            ] = context

            contextualized.append(
                enriched
            )
            continue

        found += 1

        text = text_file.read_text(
            encoding="utf-8",
            errors="ignore",
        )

        pages = split_pages(
            text
        )

        page_text = ""
        used_fallback = False

        if (
            page_number is not None
            and page_number in pages
            and len(pages) > 1
        ):
            page_text = pages[
                page_number
            ]

            explicit_page_found += 1

        elif len(pages) == 1:
            page_text = next(
                iter(
                    pages.values()
                )
            )

            used_fallback = True
            global_fallback += 1

        else:
            page_text = "\n".join(
                value
                for _, value
                in sorted(
                    pages.items()
                )
            )

            used_fallback = True
            global_fallback += 1

        context = {
            "text_file":
                str(
                    text_file
                ),

            "page_number":
                page_number,

            "page_text":
                compact_text(
                    page_text
                ),

            "document_text_available":
                True,

            "page_text_available":
                bool(
                    page_text.strip()
                ),

            "used_global_text_fallback":
                used_fallback,
        }

        enriched[
            "text_context"
        ] = context

        contextualized.append(
            enriched
        )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_FILE.write_text(
        json.dumps(
            contextualized,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=" * 96)
    print("TRACE / SGCE - TEXT CONTEXT BUILDER C")
    print("=" * 96)

    print(
        f"Cas Pattern C                  : {len(queue)}"
    )

    print(
        f"Fichiers texte dÃ©couverts      : {len(text_files)}"
    )

    print(
        f"Documents texte retrouvÃ©s      : {found}"
    )

    print(
        f"Pages retrouvÃ©es explicitement : {explicit_page_found}"
    )

    print(
        f"Fallback texte global          : {global_fallback}"
    )

    print(
        f"Documents texte manquants      : {missing}"
    )

    print()
    print(
        f"Sortie                         : {OUTPUT_FILE}"
    )

    print()
    print(
        "Aucune donnÃ©e clinique n'a Ã©tÃ© modifiÃ©e."
    )


if __name__ == "__main__":
    main()

