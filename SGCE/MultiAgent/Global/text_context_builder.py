# -*- coding: utf-8 -*-
"""
text_context_builder.py
=======================

TRACE / SGCE — Text Context Builder

But
---
Enrichir les candidats Pattern B (y compris les orphelines résiduelles)
avec le texte brut Mistral correspondant au document.

Entrée :
  MultiAgent/queues/agent_b_queue.json

Textes :
  OCR vers LLM/Sortie_Textes_Brut_MistralSmall4/*.txt
  ou variable d'environnement TRACE_MULTIAGENT_TEXT_DIR

Sortie :
  MultiAgent/queues/agent_b_queue_contextualized.json

Aucun JSON clinique n'est modifié.
"""

import os
import json
import re
from pathlib import Path

# ============================================================
# 0. PATHS / CONFIGURATION
# ============================================================

HERE = Path(__file__).resolve().parent
MULTIAGENT_DIR = HERE.parent
SGCE_DIR = MULTIAGENT_DIR.parent
REDUCTION_DIR = SGCE_DIR.parent
OCR_LLM_DIR = REDUCTION_DIR.parent

QUEUE_DIR = MULTIAGENT_DIR / "queues"
QUEUE_FILE = QUEUE_DIR / "agent_b_queue.json"
OUTPUT_FILE = QUEUE_DIR / "agent_b_queue_contextualized.json"

MAX_CONTEXT_CHARS = 12000

QUEUE_DIR.mkdir(parents=True, exist_ok=True)


def resolve_text_dir():
    """
    Résout le dossier contenant les textes bruts.

    Priorité :
      1) TRACE_MULTIAGENT_TEXT_DIR
      2) OCR vers LLM/Sortie_Textes_Brut_MistralSmall4
      3) emplacements de compatibilité
    """
    env_path = os.environ.get("TRACE_MULTIAGENT_TEXT_DIR")

    if env_path:
        env_dir = Path(env_path).expanduser()

        if env_dir.exists() and env_dir.is_dir():
            print(
                "[OK] Dossier texte via TRACE_MULTIAGENT_TEXT_DIR : "
                f"{env_dir}"
            )
            return env_dir

        print(
            "[ATTENTION] TRACE_MULTIAGENT_TEXT_DIR défini "
            f"mais dossier introuvable : {env_dir}"
        )

    candidates = [
        OCR_LLM_DIR / "Sortie_Textes_Brut_MistralSmall4",
        REDUCTION_DIR / "Sortie_Textes_Brut_MistralSmall4",
        MULTIAGENT_DIR / "Sortie_Textes_Brut_MistralSmall4",
    ]

    seen = set()

    for candidate in candidates:
        key = str(candidate.resolve(strict=False)).lower()

        if key in seen:
            continue

        seen.add(key)

        if candidate.exists() and candidate.is_dir():
            print(
                "[OK] Dossier texte détecté automatiquement : "
                f"{candidate}"
            )
            return candidate

    print("[ERREUR] Aucun dossier de textes bruts trouvé.")
    print("Emplacements testés :")

    for candidate in candidates:
        print(f"  - {candidate}")

    return None


# Résolution effectuée une seule fois au chargement du script.
TEXT_DIR = resolve_text_dir()

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
    """
    Découvre récursivement les fichiers .txt du dossier texte résolu.
    """
    if TEXT_DIR is None:
        return []

    if not TEXT_DIR.exists() or not TEXT_DIR.is_dir():
        print(f"[ATTENTION] Dossier texte introuvable : {TEXT_DIR}")
        return []

    files = sorted(
        path
        for path in TEXT_DIR.rglob("*.txt")
        if path.is_file()
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
    Essaie plusieurs formats de séparateur de page.
    Si aucun séparateur n'existe, retourne tout le texte comme page 1.
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
        f"Fichiers texte découverts      : "
        f"{len(text_files)}"
    )

    print(
        f"Documents texte retrouvés      : "
        f"{documents_found}"
    )

    print(
        f"Pages retrouvées explicitement : "
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
        print("Documents texte non retrouvés :")

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
        "Aucune donnée clinique n'a été modifiée."
    )


if __name__ == "__main__":
    main()
