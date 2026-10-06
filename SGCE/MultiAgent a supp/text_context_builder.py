# -*- coding: utf-8 -*-
"""
text_context_builder.py
=======================

TRACE / SGCE â€” Text Context Builder

But
---
Enrichir les candidats Pattern B avec le texte dÃ©jÃ  extrait des PDF.

EntrÃ©e :
  MultiAgent/queues/agent_b_queue.json

Textes :
  MultiAgent/Sortie_Textes_Brut_MistralSmall4/*.txt

Sortie :
  MultiAgent/queues/agent_b_queue_contextualized.json

Aucun JSON clinique n'est modifiÃ©.
"""

import json
import re
from pathlib import Path


BASE_DIR = Path(
    r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM"
    r"\Reduction_hallucinations"
)

MULTIAGENT_DIR = (
    BASE_DIR
    / "MultiAgent"
)

QUEUE_FILE = (
    MULTIAGENT_DIR
    / "queues"
    / "agent_b_queue.json"
)

OUTPUT_FILE = (
    MULTIAGENT_DIR
    / "queues"
    / "agent_b_queue_contextualized.json"
)

# Dossier rÃ©el des textes
TEXT_DIR_CANDIDATES = [
    MULTIAGENT_DIR
    / "Sortie_Textes_Brut_MistralSmall4"
]

# Taille maximale du contexte si le texte n'est pas sÃ©parÃ© par pages.
MAX_CONTEXT_CHARS = 5000


# ============================================================
# 1. HELPERS
# ============================================================

def load_json(path):
    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


def normalize_name(name):
    """
    Rend comparables :
      img20250709_16142502_trace_sepsis_V1.6-V6.5-SELECTIVE_PRECISION.json
      img20250709_16142502_brut.txt
    """

    name = Path(
        name
    ).stem.lower()

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

    directories = (
        [TEXT_DIR_CANDIDATES]
        if isinstance(
            TEXT_DIR_CANDIDATES,
            Path,
        )
        else TEXT_DIR_CANDIDATES
    )

    for directory in directories:
        if not directory.exists():
            print(
                f"[ATTENTION] Dossier texte introuvable : "
                f"{directory}"
            )
            continue

        for path in directory.rglob(
            "*.txt"
        ):
            if path.is_file():
                files.append(
                    path
                )

    return files


def find_text_file(
    document_name,
    text_files,
):
    target = normalize_name(
        document_name
    )

    # Exact normalized match
    exact = []

    for path in text_files:
        current = normalize_name(
            path.name
        )

        if current == target:
            exact.append(
                path
            )

    if len(exact) == 1:
        return exact[0]

    if len(exact) > 1:
        # Deterministic choice
        return sorted(
            exact
        )[0]

    # Containment fallback
    candidates = []

    for path in text_files:
        current = normalize_name(
            path.name
        )

        if (
            target in current
            or current in target
        ):
            candidates.append(
                path
            )

    if len(candidates) == 1:
        return candidates[0]

    return None


# ============================================================
# 2. PAGE EXTRACTION
# ============================================================

def extract_page_number(item):
    symbolic = item.get(
        "symbolic_candidate",
        {},
    )

    # B1 opaque endpoint example: P2_E044
    endpoints = symbolic.get(
        "endpoint_validations",
        [],
    ) or []

    for endpoint in endpoints:
        endpoint_value = (
            endpoint.get(
                "endpoint_value"
            )
            or ""
        )

        match = re.match(
            r"P(\d+)_E\d+",
            str(
                endpoint_value
            ),
        )

        if match:
            return int(
                match.group(1)
            )

    # Relation metadata fallback
    relation = symbolic.get(
        "relation"
    )

    if isinstance(
        relation,
        dict,
    ):
        page = (
            relation.get(
                "page"
            )
            or relation.get(
                "page_number"
            )
        )

        if page is not None:
            try:
                return int(
                    page
                )
            except Exception:
                pass

    return None


def split_pages(text):
    """
    Essaie plusieurs formats de sÃ©parateur de page.
    Si aucun sÃ©parateur n'existe, retourne tout le texte comme page 1.
    """

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

        for i, match in enumerate(
            matches
        ):
            page_no = int(
                match.group(1)
            )

            start = match.end()

            end = (
                matches[
                    i + 1
                ].start()
                if i + 1 < len(
                    matches
                )
                else len(
                    text
                )
            )

            pages[
                page_no
            ] = text[
                start:end
            ].strip()

        return pages

    # Form-feed
    if "\f" in text:
        parts = text.split(
            "\f"
        )

        return {
            i + 1:
                part.strip()
            for i, part in enumerate(
                parts
            )
            if part.strip()
        }

    # No explicit page separators
    return {
        1: text.strip()
    }


# ============================================================
# 3. ENDPOINT INFO
# ============================================================

def get_endpoint_info(item):
    symbolic = item.get(
        "symbolic_candidate",
        {},
    )

    endpoints = symbolic.get(
        "endpoint_validations",
        [],
    ) or []

    if not endpoints:
        return {}

    endpoint = endpoints[0]

    return {
        "role":
            endpoint.get(
                "role"
            ),

        "endpoint_value":
            endpoint.get(
                "endpoint_value"
            ),

        "expected_type":
            endpoint.get(
                "expected_type"
            ),

        "resolution_status":
            endpoint.get(
                "resolution_status"
            ),

        "status":
            endpoint.get(
                "status"
            ),

        "reason":
            endpoint.get(
                "reason"
            ),
    }


def compact_text(text):
    if not text:
        return ""

    if len(text) <= MAX_CONTEXT_CHARS:
        return text.strip()

    half = MAX_CONTEXT_CHARS // 2

    return (
        text[
            :half
        ].strip()
        + "\n...\n"
        + text[
            -half:
        ].strip()
    )


# ============================================================
# 4. MAIN
# ============================================================

def main():
    if not QUEUE_FILE.exists():
        raise FileNotFoundError(
            f"Queue B introuvable : "
            f"{QUEUE_FILE}"
        )

    queue = load_json(
        QUEUE_FILE
    )

    text_files = discover_text_files()

    contextualized = []

    documents_found = 0
    explicit_pages_found = 0
    fallback_global_text = 0
    missing_text = 0

    missing_documents = []

    for item in queue:
        enriched = dict(
            item
        )

        document = item.get(
            "document",
            "",
        )

        endpoint_info = get_endpoint_info(
            item
        )

        page_number = extract_page_number(
            item
        )

        text_file = find_text_file(
            document,
            text_files,
        )

        text_context = {
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

            "endpoint":
                endpoint_info,
        }

        if text_file is None:
            missing_text += 1
            missing_documents.append(
                document
            )

            enriched[
                "text_context"
            ] = text_context

            contextualized.append(
                enriched
            )

            continue

        documents_found += 1

        text = text_file.read_text(
            encoding="utf-8",
            errors="ignore",
        )

        pages = split_pages(
            text
        )

        page_text = ""
        used_global_fallback = False

        # Exact page found
        if (
            page_number is not None
            and page_number in pages
            and len(pages) > 1
        ):
            page_text = pages[
                page_number
            ]

            explicit_pages_found += 1

        # Text file has no page markers:
        # use the whole extracted text as context.
        elif len(pages) == 1:
            page_text = next(
                iter(
                    pages.values()
                )
            )

            used_global_fallback = True
            fallback_global_text += 1

        # Page markers exist but requested page absent:
        # use document-wide concatenation as fallback.
        else:
            page_text = "\n".join(
                value
                for _, value in sorted(
                    pages.items()
                )
            )

            used_global_fallback = True
            fallback_global_text += 1

        text_context = {
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
                used_global_fallback,

            "endpoint":
                endpoint_info,
        }

        enriched[
            "text_context"
        ] = text_context

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

    print("=" * 92)
    print("TRACE / SGCE - TEXT CONTEXT BUILDER")
    print("=" * 92)

    print(
        f"Cas Pattern B                  : "
        f"{len(queue)}"
    )

    print(
        f"Fichiers texte dÃ©couverts      : "
        f"{len(text_files)}"
    )

    print(
        f"Documents texte retrouvÃ©s      : "
        f"{documents_found}"
    )

    print(
        f"Pages retrouvÃ©es explicitement : "
        f"{explicit_pages_found}"
    )

    print(
        f"Fallback texte global          : "
        f"{fallback_global_text}"
    )

    print(
        f"Documents texte manquants      : "
        f"{missing_text}"
    )

    if missing_documents:
        print()
        print("Documents texte non retrouvÃ©s :")

        for name in sorted(
            set(
                missing_documents
            )
        ):
            print(
                f"  - {name}"
            )

    print()

    print(
        f"Sortie                         : "
        f"{OUTPUT_FILE}"
    )

    print()

    print(
        "Aucune donnÃ©e clinique n'a Ã©tÃ© modifiÃ©e."
    )


if __name__ == "__main__":
    main()

