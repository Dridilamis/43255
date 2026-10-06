# -*- coding: utf-8 -*-
"""
text_context_builder_relation.py
================================

Ajoute le contexte texte de la page aux candidats de rÃ©paration relationnelle.

EntrÃ©e :
  MultiAgent/relation_repair/queues/relation_repair_queue.json

Textes :
  MultiAgent/Sortie_Textes_Brut_MistralSmall4

Sortie :
  MultiAgent/relation_repair/queues/relation_repair_queue_contextualized.json
"""

import json
import re
from pathlib import Path

BASE_DIR = Path(
    r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM"
    r"\Reduction_hallucinations"
)

M = BASE_DIR / "MultiAgent"

QUEUE_FILE = (
    M
    / "relation_repair"
    / "queues"
    / "relation_repair_queue.json"
)

OUTPUT_FILE = (
    M
    / "relation_repair"
    / "queues"
    / "relation_repair_queue_contextualized.json"
)

TEXT_DIRS = [
    M / "Sortie_Textes_Brut_MistralSmall4"
]


def load_json(path):
    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


def normalize_name(name):
    name = Path(name).stem.lower()

    for suffix in (
        "_trace_sepsis_v1.6-v6.5-selective_precision",
        "_trace_sepsis_v1.6",
        "_trace_sepsis",
        "_mistral",
        "_qwen",
        "_brut",
    ):
        name = name.replace(
            suffix,
            "",
        )

    return re.sub(
        r"[^a-z0-9]+",
        "",
        name,
    )


def page_from_entity_id(value):
    m = re.match(
        r"P(\d+)_E\d+",
        str(value or ""),
    )

    return int(
        m.group(1)
    ) if m else None


def split_pages(text):
    patterns = [
        r"\n\s*={3,}\s*PAGE\s+(\d+)\s*={3,}\s*\n",
        r"\n\s*-{3,}\s*PAGE\s+(\d+)\s*-{3,}\s*\n",
        r"\n\s*\[?PAGE\s+(\d+)\]?\s*\n",
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

        if matches:
            pages = {}

            for i, match in enumerate(matches):
                end = (
                    matches[i + 1].start()
                    if i + 1 < len(matches)
                    else len(text)
                )

                pages[
                    int(
                        match.group(1)
                    )
                ] = text[
                    match.end():end
                ].strip()

            return pages

    if "\f" in text:
        return {
            i + 1: part.strip()
            for i, part in enumerate(text.split("\f"))
            if part.strip()
        }

    return {
        1: text.strip()
    }


def main():
    queue = load_json(
        QUEUE_FILE
    )

    txt_files = []

    for directory in TEXT_DIRS:
        if directory.exists():
            txt_files.extend(
                directory.rglob("*.txt")
            )

    contextualized = []

    found = 0
    pages_found = 0
    fallback = 0
    missing = 0

    for item in queue:
        target_name = normalize_name(
            item.get(
                "document",
                "",
            )
        )

        matches = [
            p
            for p in txt_files
            if normalize_name(
                p.name
            ) == target_name
        ]

        if not matches:
            matches = [
                p
                for p in txt_files
                if (
                    target_name
                    in normalize_name(p.name)
                    or normalize_name(p.name)
                    in target_name
                )
            ]

        text_file = (
            matches[0]
            if len(matches) == 1
            else None
        )

        page_number = (
            page_from_entity_id(
                item.get(
                    "source_id"
                )
            )
            or page_from_entity_id(
                item.get(
                    "target_id"
                )
            )
        )

        context = {
            "text_file":
                None,

            "page_number":
                page_number,

            "page_text":
                "",

            "text_available":
                False,

            "used_global_text_fallback":
                False,
        }

        if text_file is None:
            missing += 1

        else:
            found += 1

            text = text_file.read_text(
                encoding="utf-8",
                errors="ignore",
            )

            pages = split_pages(
                text
            )

            if (
                page_number in pages
                and len(pages) > 1
            ):
                context[
                    "page_text"
                ] = pages[
                    page_number
                ]

                pages_found += 1

            elif len(pages) == 1:
                context[
                    "page_text"
                ] = next(
                    iter(
                        pages.values()
                    )
                )

                context[
                    "used_global_text_fallback"
                ] = True

                fallback += 1

            else:
                context[
                    "page_text"
                ] = "\n".join(
                    pages.values()
                )

                context[
                    "used_global_text_fallback"
                ] = True

                fallback += 1

            context[
                "text_file"
            ] = str(
                text_file
            )

            context[
                "text_available"
            ] = bool(
                context[
                    "page_text"
                ].strip()
            )

        enriched = dict(
            item
        )

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

    print("=" * 104)
    print("TRACE / SGCE - RELATION TEXT CONTEXT BUILDER")
    print("=" * 104)
    print(f"Cas reÃ§us                             : {len(queue)}")
    print(f"Fichiers texte dÃ©couverts             : {len(txt_files)}")
    print(f"Documents texte retrouvÃ©s             : {found}")
    print(f"Pages retrouvÃ©es explicitement        : {pages_found}")
    print(f"Fallback texte global                 : {fallback}")
    print(f"Documents texte manquants             : {missing}")
    print()
    print(f"Sortie                                : {OUTPUT_FILE}")
    print()
    print("Aucune donnÃ©e clinique n'a Ã©tÃ© modifiÃ©e.")


if __name__ == "__main__":
    main()

