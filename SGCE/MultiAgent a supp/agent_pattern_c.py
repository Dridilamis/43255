# -*- coding: utf-8 -*-
"""
agent_pattern_c.py
==================

TRACE / SGCE â€” Agent Pattern C document-grounded

EntrÃ©e :
  MultiAgent/queues/agent_c_queue_contextualized.json

Contexte clinique :
  MultiAgent/agent_b_corrected

Sortie :
  MultiAgent/outputs/agent_c_decisions.json

Principe :
- utiliser le graphe ET le texte source
- ne proposer aucune suppression / fusion sans preuve documentaire
- aucun JSON clinique n'est modifiÃ©
"""

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path


BASE_DIR = Path(
    r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM"
    r"\Reduction_hallucinations"
)

MULTIAGENT_DIR = BASE_DIR / "MultiAgent"

QUEUE_FILE = (
    MULTIAGENT_DIR
    / "queues"
    / "agent_c_queue_contextualized.json"
)

OUTPUT_FILE = (
    MULTIAGENT_DIR
    / "outputs"
    / "agent_c_decisions.json"
)

CLINICAL_INPUT_CANDIDATES = [
    MULTIAGENT_DIR
    / "agent_b_corrected",

    BASE_DIR
    / "PatternD"
    / "pattern_d_corrected",
]


# ============================================================
# HELPERS
# ============================================================

def load_json(path):
    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


def resolve_clinical_input():
    for path in CLINICAL_INPUT_CANDIDATES:
        if (
            path.exists()
            and any(
                path.glob("*.json")
            )
        ):
            return path

    return None


def normalize(text):
    text = "" if text is None else str(text)

    text = text.replace(
        "â€™",
        "'",
    )

    text = unicodedata.normalize(
        "NFKD",
        text,
    )

    text = "".join(
        c
        for c in text
        if not unicodedata.combining(c)
    )

    text = text.lower()

    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def entity_id(e):
    return (
        e.get("identifiant_entite")
        or e.get("id")
        or e.get("entity_id")
    )


def entity_type(e):
    return (
        e.get("categorie")
        or e.get("type")
        or e.get("entity_type")
        or ""
    )


def entity_text(e):
    values = []

    for key in (
        "preuve",
        "name",
        "valeur",
        "libelle",
        "parametre",
        "texte",
        "text",
    ):
        value = e.get(key)

        if value not in (
            None,
            "",
        ):
            value = str(
                value
            ).strip()

            if (
                value
                and value not in values
            ):
                values.append(
                    value
                )

    return " | ".join(
        values
    )


def relation_id(r):
    return (
        r.get("identifiant_relation")
        or r.get("id")
        or r.get("relation_id")
    )


def relation_type(r):
    return (
        r.get("type_relation")
        or r.get("relation")
        or r.get("relation_type")
        or r.get("predicate")
        or r.get("type")
        or ""
    )


def relation_source(r):
    return (
        r.get("identifiant_entite_sujet")
        or r.get("from_id")
        or r.get("subject_id")
        or r.get("source")
    )


def relation_target(r):
    return (
        r.get("identifiant_entite_objet")
        or r.get("to_id")
        or r.get("object_id")
        or r.get("target")
    )


def get_entities(doc):
    if isinstance(
        doc.get(
            "global_entities"
        ),
        list,
    ):
        return doc[
            "global_entities"
        ]

    out = []

    for page in (
        doc.get(
            "pages",
            []
        )
        or []
    ):
        out.extend(
            page.get(
                "entities",
                []
            )
            or []
        )

    return out


def get_relations(doc):
    if isinstance(
        doc.get(
            "global_relations"
        ),
        list,
    ):
        return doc[
            "global_relations"
        ]

    out = []

    for page in (
        doc.get(
            "pages",
            []
        )
        or []
    ):
        out.extend(
            page.get(
                "relations",
                []
            )
            or []
        )

    return out


def entity_index(doc):
    return {
        str(
            entity_id(
                e
            )
        ):
            e
        for e in get_entities(
            doc
        )
        if entity_id(
            e
        )
        is not None
    }


def load_clinical_docs():
    input_dir = resolve_clinical_input()

    if input_dir is None:
        return {}, None

    docs = {}

    for path in sorted(
        input_dir.glob(
            "*.json"
        )
    ):
        try:
            docs[
                path.name
            ] = load_json(
                path
            )

        except Exception:
            pass

    return docs, input_dir


# ============================================================
# CANDIDATE PARSING
# ============================================================

def get_symbolic(item):
    return (
        item.get(
            "symbolic_candidate"
        )
        or {}
    )


def extract_candidate_entity(
    symbolic,
):
    for key in (
        "reified_entity",
        "entity",
        "candidate_entity",
        "middle_entity",
    ):
        value = symbolic.get(
            key
        )

        if isinstance(
            value,
            dict,
        ):
            return value

    return None


def enrich_graph_context(
    symbolic,
    doc,
):
    if doc is None:
        return {
            "candidate_entity":
                None,

            "relations":
                [],
        }

    candidate = extract_candidate_entity(
        symbolic
    )

    cid = (
        entity_id(
            candidate
        )
        if candidate
        else None
    )

    current_entity = None

    if cid:
        current_entity = entity_index(
            doc
        ).get(
            str(
                cid
            )
        )

    relations = []

    if cid:
        for relation in get_relations(
            doc
        ):
            if (
                str(
                    relation_source(
                        relation
                    )
                )
                == str(
                    cid
                )
                or str(
                    relation_target(
                        relation
                    )
                )
                == str(
                    cid
                )
            ):
                relations.append(
                    relation
                )

    return {
        "candidate_entity":
            current_entity,

        "relations":
            relations,
    }


# ============================================================
# DOCUMENT GROUNDING
# ============================================================

GENERIC_REFERENCE_TERMS = {
    "seuil",
    "seuils",
    "reference",
    "rÃ©fÃ©rence",
    "norme",
    "classification",
    "critere",
    "critÃ¨res",
    "score",
    "tableau",
    "definition",
    "dÃ©finition",
}

PATIENT_TERMS = {
    "patient",
    "chez ce patient",
    "chez le patient",
    "prÃ©sente",
    "presente",
    "hospitalisation",
    "Ã©volution",
    "evolution",
    "traitÃ©",
    "traite",
}

TEMPORAL_TERMS = {
    "evolution",
    "Ã©volution",
    "amÃ©lioration",
    "amelioration",
    "aggravation",
    "initialement",
    "secondairement",
    "puis",
    "ensuite",
    "aprÃ¨s",
    "apres",
    "avant",
    "jour",
}


def count_terms(
    text,
    terms,
):
    normalized = normalize(
        text
    )

    return sum(
        1
        for term in terms
        if normalize(
            term
        )
        in normalized
    )


def evidence_present(
    candidate_text,
    page_text,
):
    """
    VÃ©rifie que le contenu clinique du candidat est rÃ©ellement
    prÃ©sent dans le texte source.
    """

    if not candidate_text or not page_text:
        return False

    candidate_parts = [
        normalize(
            x
        )
        for x in str(
            candidate_text
        ).split("|")
        if normalize(
            x
        )
    ]

    page_norm = normalize(
        page_text
    )

    if not candidate_parts:
        return False

    # Au moins un span clinique significatif doit Ãªtre prÃ©sent.
    return any(
        part in page_norm
        for part in candidate_parts
        if len(
            part
        )
        >= 4
    )


# ============================================================
# DECISION
# ============================================================

def decide(
    item,
    doc,
):
    cid = item.get(
        "candidate_id"
    )

    document = item.get(
        "document"
    )

    symbolic = get_symbolic(
        item
    )

    graph = enrich_graph_context(
        symbolic,
        doc,
    )

    candidate = (
        graph.get(
            "candidate_entity"
        )
        or extract_candidate_entity(
            symbolic
        )
    )

    candidate_id_value = (
        entity_id(
            candidate
        )
        if candidate
        else None
    )

    candidate_type_value = (
        entity_type(
            candidate
        )
        if candidate
        else ""
    )

    candidate_text_value = (
        entity_text(
            candidate
        )
        if candidate
        else ""
    )

    relations = (
        graph.get(
            "relations"
        )
        or []
    )

    relation_count = len(
        relations
    )

    text_context = (
        item.get(
            "text_context"
        )
        or {}
    )

    page_text = str(
        text_context.get(
            "page_text"
        )
        or ""
    )

    grounded = evidence_present(
        candidate_text_value,
        page_text,
    )

    reference_hits = count_terms(
        page_text,
        GENERIC_REFERENCE_TERMS,
    )

    patient_hits = count_terms(
        page_text,
        PATIENT_TERMS,
    )

    temporal_hits = count_terms(
        page_text,
        TEMPORAL_TERMS,
    )

    # --------------------------------------------------------
    # No document evidence
    # --------------------------------------------------------

    if not grounded:
        return {
            "candidate_id":
                cid,

            "document":
                document,

            "pattern":
                "C",

            "agent":
                "agent_pattern_c",

            "decision":
                "REVIEW",

            "action":
                "NONE",

            "confidence":
                0.35,

            "reason":
                (
                    "Le candidat n'est pas suffisamment ancrÃ© dans "
                    "le texte source. Aucune restructuration automatique."
                ),

            "evidence":
                candidate_text_value,

            "proposed_entities":
                [],

            "proposed_relations":
                [],

            "metadata": {
                "candidate_entity_id":
                    candidate_id_value,

                "candidate_entity_type":
                    candidate_type_value,

                "text_grounded":
                    False,

                "attached_relation_count":
                    relation_count,

                "page_number":
                    text_context.get(
                        "page_number"
                    ),

                "text_file":
                    text_context.get(
                        "text_file"
                    ),
            },
        }

    # --------------------------------------------------------
    # Referential/generic content
    # --------------------------------------------------------

    if (
        reference_hits > 0
        and patient_hits == 0
    ):
        return {
            "candidate_id":
                cid,

            "document":
                document,

            "pattern":
                "C",

            "agent":
                "agent_pattern_c",

            "decision":
                "REVIEW",

            "action":
                "NONE",

            "confidence":
                0.70,

            "reason":
                (
                    "Le candidat est ancrÃ© dans le texte, mais le contexte "
                    "semble rÃ©fÃ©rentiel/gÃ©nÃ©rique. Routage Patient/RÃ©fÃ©rence."
                ),

            "evidence":
                candidate_text_value,

            "proposed_entities":
                [],

            "proposed_relations":
                [],

            "metadata": {
                "candidate_entity_id":
                    candidate_id_value,

                "candidate_entity_type":
                    candidate_type_value,

                "text_grounded":
                    True,

                "route_patient_reference":
                    True,

                "reference_hits":
                    reference_hits,

                "patient_hits":
                    patient_hits,

                "temporal_hits":
                    temporal_hits,

                "attached_relation_count":
                    relation_count,

                "page_number":
                    text_context.get(
                        "page_number"
                    ),

                "text_file":
                    text_context.get(
                        "text_file"
                    ),
            },
        }

    # --------------------------------------------------------
    # Isolated reified entity
    # --------------------------------------------------------

    if (
        candidate
        and relation_count == 0
        and grounded
    ):
        return {
            "candidate_id":
                cid,

            "document":
                document,

            "pattern":
                "C",

            "agent":
                "agent_pattern_c",

            "decision":
                "CORRECT",

            "action":
                "REMOVE_REIFIED_ENTITY",

            "confidence":
                0.86,

            "reason":
                (
                    "L'entitÃ© est explicitement retrouvÃ©e dans le texte "
                    "source mais reste isolÃ©e dans le graphe. "
                    "Suppression de la rÃ©ification proposÃ©e."
                ),

            "evidence":
                candidate_text_value,

            "proposed_entities":
                [],

            "proposed_relations":
                [],

            "metadata": {
                "candidate_entity_id":
                    candidate_id_value,

                "candidate_entity_type":
                    candidate_type_value,

                "text_grounded":
                    True,

                "attached_relation_count":
                    0,

                "page_number":
                    text_context.get(
                        "page_number"
                    ),

                "text_file":
                    text_context.get(
                        "text_file"
                    ),

                "reference_hits":
                    reference_hits,

                "patient_hits":
                    patient_hits,

                "temporal_hits":
                    temporal_hits,
            },
        }

    # --------------------------------------------------------
    # Temporal patient case
    # --------------------------------------------------------

    if (
        temporal_hits > 0
        and patient_hits > 0
        and grounded
    ):
        # Important:
        # on ne propose plus MERGE sans cible explicite.
        return {
            "candidate_id":
                cid,

            "document":
                document,

            "pattern":
                "C",

            "agent":
                "agent_pattern_c",

            "decision":
                "REVIEW",

            "action":
                "NONE",

            "confidence":
                0.65,

            "reason":
                (
                    "Le contexte documente une Ã©volution patient, "
                    "mais aucune cible de fusion explicite n'est fournie. "
                    "MERGE automatique interdit."
                ),

            "evidence":
                candidate_text_value,

            "proposed_entities":
                [],

            "proposed_relations":
                [],

            "metadata": {
                "candidate_entity_id":
                    candidate_id_value,

                "candidate_entity_type":
                    candidate_type_value,

                "text_grounded":
                    True,

                "temporal_hits":
                    temporal_hits,

                "patient_hits":
                    patient_hits,

                "attached_relation_count":
                    relation_count,

                "page_number":
                    text_context.get(
                        "page_number"
                    ),

                "text_file":
                    text_context.get(
                        "text_file"
                    ),
            },
        }

    # --------------------------------------------------------
    # Connected reified entity
    # --------------------------------------------------------

    if (
        candidate
        and relation_count > 0
    ):
        return {
            "candidate_id":
                cid,

            "document":
                document,

            "pattern":
                "C",

            "agent":
                "agent_pattern_c",

            "decision":
                "REVIEW",

            "action":
                "NONE",

            "confidence":
                0.60,

            "reason":
                (
                    "Le candidat est document-grounded mais participe "
                    "Ã  une ou plusieurs relations. Une restructuration "
                    "directe nÃ©cessite une relation cible explicite."
                ),

            "evidence":
                candidate_text_value,

            "proposed_entities":
                [],

            "proposed_relations":
                [],

            "metadata": {
                "candidate_entity_id":
                    candidate_id_value,

                "candidate_entity_type":
                    candidate_type_value,

                "text_grounded":
                    True,

                "attached_relation_count":
                    relation_count,

                "attached_relations": [
                    {
                        "relation_id":
                            relation_id(
                                r
                            ),

                        "relation_type":
                            relation_type(
                                r
                            ),

                        "source":
                            relation_source(
                                r
                            ),

                        "target":
                            relation_target(
                                r
                            ),
                    }
                    for r in relations
                ],

                "page_number":
                    text_context.get(
                        "page_number"
                    ),

                "text_file":
                    text_context.get(
                        "text_file"
                    ),
            },
        }

    # --------------------------------------------------------
    # Fallback
    # --------------------------------------------------------

    return {
        "candidate_id":
            cid,

        "document":
            document,

        "pattern":
            "C",

        "agent":
            "agent_pattern_c",

        "decision":
            "REVIEW",

        "action":
            "NONE",

        "confidence":
            0.40,

        "reason":
            (
                "Contexte insuffisant pour une correction Pattern C sÃ»re."
            ),

        "evidence":
            candidate_text_value,

        "proposed_entities":
            [],

        "proposed_relations":
            [],

        "metadata": {
            "candidate_entity_id":
                candidate_id_value,

            "candidate_entity_type":
                candidate_type_value,

            "text_grounded":
                grounded,

            "attached_relation_count":
                relation_count,
        },
    }


# ============================================================
# MAIN
# ============================================================

def main():
    if not QUEUE_FILE.exists():
        raise FileNotFoundError(
            f"Queue C contextualisÃ©e introuvable : {QUEUE_FILE}"
        )

    queue = load_json(
        QUEUE_FILE
    )

    docs, clinical_input = load_clinical_docs()

    decisions = []

    for item in queue:
        document = item.get(
            "document"
        )

        doc = docs.get(
            document
        )

        decisions.append(
            decide(
                item,
                doc,
            )
        )

    decision_counts = Counter(
        d.get(
            "decision"
        )
        for d in decisions
    )

    action_counts = Counter(
        d.get(
            "action"
        )
        for d in decisions
    )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_FILE.write_text(
        json.dumps(
            {
                "agent":
                    "agent_pattern_c",

                "mode":
                    "DOCUMENT_GROUNDED_PATTERN_C",

                "clinical_context_directory":
                    str(
                        clinical_input
                    ),

                "summary": {
                    "cases_received":
                        len(
                            queue
                        ),

                    "decisions_written":
                        len(
                            decisions
                        ),

                    "decision_counts":
                        dict(
                            decision_counts
                        ),

                    "action_counts":
                        dict(
                            action_counts
                        ),
                },

                "decisions":
                    decisions,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=" * 96)
    print("TRACE / SGCE - AGENT PATTERN C DOCUMENT-GROUNDED")
    print("=" * 96)

    print(
        f"Contexte clinique                 : {clinical_input}"
    )

    print(
        f"Cas reÃ§us                         : {len(queue)}"
    )

    print(
        f"DÃ©cisions produites               : {len(decisions)}"
    )

    print()
    print("DECISIONS")
    print("-" * 96)

    for name, count in (
        decision_counts.most_common()
    ):
        print(
            f"{str(name):<40}: {count}"
        )

    print()
    print("ACTIONS PROPOSEES")
    print("-" * 96)

    for name, count in (
        action_counts.most_common()
    ):
        print(
            f"{str(name):<40}: {count}"
        )

    print()
    print(
        f"Sortie                            : {OUTPUT_FILE}"
    )

    print()
    print(
        "Aucun JSON clinique n'a Ã©tÃ© modifiÃ©."
    )


if __name__ == "__main__":
    main()

