# -*- coding: utf-8 -*-
"""
multiagent_adjudicator.py
=========================

TRACE / SGCE â€” Multi-Agent Adjudicator

But
---
RÃ©examiner les REVIEW persistants provenant de :
- Agent B
- Agent C
- Agent D
- Agent Patient/RÃ©fÃ©rence

Trois votes indÃ©pendants sont calculÃ©s :

1) DOCUMENT_EVIDENCE
   La dÃ©cision est-elle explicitement soutenue par le texte source ?

2) ONTOLOGY_STRUCTURE
   La dÃ©cision respecte-t-elle le graphe TRACE-Sepsis,
   les relations domaine/image et l'Ã©tat courant du KG ?

3) CLINICAL_COHERENCE
   La dÃ©cision est-elle cohÃ©rente avec le contexte clinique local,
   sans contradiction Ã©vidente ?

Politique de consensus
----------------------
- 3/3 SUPPORT       -> RESOLVED
- 2/3 SUPPORT
  + aucune VETO
  + preuve documentaire explicite
                     -> RESOLVED
- sinon             -> UNRESOLVED

Important
---------
- Aucun JSON clinique n'est modifiÃ©.
- Les dÃ©cisions de suppression/retype/relink/create ne sont proposÃ©es
  que lorsqu'une action explicite est reconstruite et suffisamment Ã©tayÃ©e.
- Les cas sans correction sÃ»re restent UNRESOLVED.
"""

import json
import re
import unicodedata
from pathlib import Path
from collections import Counter


# ============================================================
# 1. PATHS
# ============================================================

BASE_DIR = Path(
    r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM"
    r"\Reduction_hallucinations"
)

M = BASE_DIR / "MultiAgent"

INPUTS = {
    "B": (
        M
        / "outputs"
        / "agent_b_validated_decisions.json"
    ),

    "C": (
        M
        / "outputs"
        / "agent_c_validated_decisions.json"
    ),

    "D": (
        M
        / "outputs"
        / "agent_d_validated_decisions.json"
    ),

    "PATIENT_REFERENCE": (
        M
        / "outputs"
        / "agent_patient_reference_validated_decisions.json"
    ),
}

CONTEXT_QUEUES = {
    "B": (
        M
        / "queues"
        / "agent_b_queue_contextualized.json"
    ),

    "C": (
        M
        / "queues"
        / "agent_c_queue_contextualized.json"
    ),

    "D": (
        M
        / "queues"
        / "agent_d_queue_contextualized.json"
    ),

    "PATIENT_REFERENCE": (
        M
        / "queues"
        / "agent_patient_reference_queue_contextualized.json"
    ),
}

CLINICAL_DIR_CANDIDATES = [
    M / "agent_d_corrected",
    M / "agent_patient_reference_corrected",
    M / "agent_c_corrected",
    M / "agent_b_corrected",
]

GUIDELINE_CANDIDATES = [
    BASE_DIR
    / "Guideline_TRACE_Sepsis_v1.6.json",

    BASE_DIR.parent
    / "Guideline_TRACE_Sepsis_v1.6.json",
]

OUT = (
    M
    / "outputs"
    / "multiagent_adjudication_report.json"
)


# ============================================================
# 2. GENERIC HELPERS
# ============================================================

def load_json(path):
    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


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
        r"[^a-z0-9/+.-]+",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def resolve_clinical_dir():
    for directory in CLINICAL_DIR_CANDIDATES:
        if (
            directory.exists()
            and any(
                directory.glob(
                    "*.json"
                )
            )
        ):
            return directory

    raise FileNotFoundError(
        "Aucun contexte clinique courant trouvÃ©."
    )


def resolve_guideline():
    for path in GUIDELINE_CANDIDATES:
        if path.exists():
            return path

    return None


# ============================================================
# 3. ENTITY / RELATION HELPERS
# ============================================================

def entity_id(entity):
    return (
        entity.get(
            "identifiant_entite"
        )
        or entity.get(
            "id"
        )
        or entity.get(
            "entity_id"
        )
    )


def entity_type(entity):
    return (
        entity.get(
            "categorie"
        )
        or entity.get(
            "type"
        )
        or entity.get(
            "entity_type"
        )
        or ""
    )


def entity_text(entity):
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
        value = entity.get(
            key
        )

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


def relation_id(relation):
    return (
        relation.get(
            "identifiant_relation"
        )
        or relation.get(
            "id"
        )
        or relation.get(
            "relation_id"
        )
    )


def relation_type(relation):
    return (
        relation.get(
            "type_relation"
        )
        or relation.get(
            "relation"
        )
        or relation.get(
            "relation_type"
        )
        or relation.get(
            "predicate"
        )
        or relation.get(
            "type"
        )
        or ""
    )


def relation_source(relation):
    return (
        relation.get(
            "identifiant_entite_sujet"
        )
        or relation.get(
            "from_id"
        )
        or relation.get(
            "subject_id"
        )
        or relation.get(
            "source"
        )
    )


def relation_target(relation):
    return (
        relation.get(
            "identifiant_entite_objet"
        )
        or relation.get(
            "to_id"
        )
        or relation.get(
            "object_id"
        )
        or relation.get(
            "target"
        )
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

    output = []

    for page in (
        doc.get(
            "pages",
            []
        )
        or []
    ):
        output.extend(
            page.get(
                "entities",
                []
            )
            or []
        )

    return output


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

    output = []

    for page in (
        doc.get(
            "pages",
            []
        )
        or []
    ):
        output.extend(
            page.get(
                "relations",
                []
            )
            or []
        )

    return output


def find_entity(
    doc,
    target_id,
):
    for entity in get_entities(
        doc
    ):
        if str(
            entity_id(
                entity
            )
        ) == str(
            target_id
        ):
            return entity

    return None


def find_relation(
    doc,
    target_id,
):
    for relation in get_relations(
        doc
    ):
        if str(
            relation_id(
                relation
            )
        ) == str(
            target_id
        ):
            return relation

    return None


def relations_for_entity(
    doc,
    target_id,
):
    return [
        relation
        for relation
        in get_relations(
            doc
        )
        if (
            str(
                relation_source(
                    relation
                )
            )
            == str(
                target_id
            )
            or
            str(
                relation_target(
                    relation
                )
            )
            == str(
                target_id
            )
        )
    ]


# ============================================================
# 4. LOAD CURRENT CLINICAL CONTEXT
# ============================================================

def load_clinical_docs(
    directory,
):
    docs = {}

    for path in directory.glob(
        "*.json"
    ):
        if path.name.endswith(
            "_report.json"
        ):
            continue

        try:
            data = load_json(
                path
            )

            if (
                isinstance(
                    data,
                    dict,
                )
                and any(
                    key in data
                    for key in (
                        "pages",
                        "global_entities",
                        "global_relations",
                    )
                )
            ):
                docs[
                    path.name
                ] = data

        except Exception:
            pass

    return docs


# ============================================================
# 5. CONTEXT QUEUES
# ============================================================

def load_context_maps():
    result = {}

    for family, path in CONTEXT_QUEUES.items():
        result[
            family
        ] = {}

        if not path.exists():
            continue

        try:
            queue = load_json(
                path
            )
        except Exception:
            continue

        if not isinstance(
            queue,
            list,
        ):
            continue

        for item in queue:
            candidate_id = item.get(
                "candidate_id"
            )

            if candidate_id:
                result[
                    family
                ][
                    candidate_id
                ] = item

    return result


# ============================================================
# 6. GUIDELINE
# ============================================================

def get_signatures():
    path = resolve_guideline()

    if path is None:
        return {}

    data = load_json(
        path
    )

    root = data.get(
        "ontologie_sepsis_graph",
        data,
    )

    locked = root.get(
        "signatures_relations_verrouillees_v1_5",
        {},
    )

    output = {}

    if not isinstance(
        locked,
        dict,
    ):
        return output

    for name, spec in locked.items():
        if not isinstance(
            spec,
            dict,
        ):
            continue

        domain = spec.get(
            "domaine"
        )

        image = spec.get(
            "image"
        )

        if domain and image:
            output[
                name
            ] = {
                "domaine":
                    domain,

                "image":
                    image,
            }

    return output


# ============================================================
# 7. VOTE OBJECT
# ============================================================

def vote(
    agent,
    verdict,
    score,
    reason,
    *,
    hard_veto=False,
    proposal=None,
):
    return {
        "agent":
            agent,

        "verdict":
            verdict,

        "score":
            round(
                float(
                    score
                ),
                4,
            ),

        "hard_veto":
            bool(
                hard_veto
            ),

        "reason":
            reason,

        "proposal":
            proposal,
    }


# ============================================================
# 8. DOCUMENTARY VOTE
# ============================================================

def documentary_vote(
    family,
    item,
    context_item,
):
    agent_decision = (
        item.get(
            "agent_decision"
        )
        or {}
    )

    evidence = str(
        agent_decision.get(
            "evidence"
        )
        or ""
    ).strip()

    metadata = (
        agent_decision.get(
            "metadata"
        )
        or {}
    )

    text_context = (
        (
            context_item
            or {}
        ).get(
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

    if (
        not evidence
        or not page_text
    ):
        return vote(
            "DOCUMENT_EVIDENCE",
            "ABSTAIN",
            0.0,
            "Preuve ou contexte textuel absent.",
        )

    evidence_parts = [
        normalize(
            part
        )
        for part in evidence.split(
            "|"
        )
        if len(
            normalize(
                part
            )
        )
        >= 4
    ]

    page_norm = normalize(
        page_text
    )

    grounded_parts = [
        part
        for part in evidence_parts
        if part in page_norm
    ]

    grounded = bool(
        grounded_parts
    )

    if not grounded:
        return vote(
            "DOCUMENT_EVIDENCE",
            "VETO",
            0.0,
            "La preuve proposÃ©e n'est pas retrouvÃ©e dans le texte source.",
            hard_veto=True,
        )

    ratio = (
        len(
            grounded_parts
        )
        / max(
            1,
            len(
                evidence_parts
            ),
        )
    )

    return vote(
        "DOCUMENT_EVIDENCE",
        "SUPPORT",
        0.7
        + 0.3
        * ratio,
        "La preuve clinique est explicitement retrouvÃ©e dans le texte source.",
    )


# ============================================================
# 9. ONTOLOGY / STRUCTURE VOTE
# ============================================================

def ontology_vote(
    family,
    item,
    doc,
    signatures,
):
    agent_decision = (
        item.get(
            "agent_decision"
        )
        or {}
    )

    metadata = (
        agent_decision.get(
            "metadata"
        )
        or {}
    )

    final_action = item.get(
        "final_action"
    )

    # --------------------------------------------------------
    # B
    # --------------------------------------------------------

    if family == "B":
        if final_action == "REFINE_ENTITY_SPAN":
            expected_type = (
                metadata.get(
                    "expected_type"
                )
                or metadata.get(
                    "missing_type"
                )
            )

            if expected_type:
                return vote(
                    "ONTOLOGY_STRUCTURE",
                    "SUPPORT",
                    0.75,
                    "Le type attendu est dÃ©jÃ  dÃ©terminÃ© par le schÃ©ma B.",
                    proposal={
                        "action":
                            "REFINE_ENTITY_SPAN",

                        "expected_type":
                            expected_type,
                    },
                )

        return vote(
            "ONTOLOGY_STRUCTURE",
            "ABSTAIN",
            0.3,
            "Aucune action structurelle B suffisamment explicite.",
        )

    # --------------------------------------------------------
    # C
    # --------------------------------------------------------

    if family == "C":
        entity_id_value = metadata.get(
            "candidate_entity_id"
        )

        entity = (
            find_entity(
                doc,
                entity_id_value,
            )
            if doc
            and entity_id_value
            else None
        )

        if not entity:
            return vote(
                "ONTOLOGY_STRUCTURE",
                "ABSTAIN",
                0.2,
                "EntitÃ© Pattern C introuvable dans le graphe courant.",
            )

        linked = relations_for_entity(
            doc,
            entity_id_value,
        )

        if len(
            linked
        ) == 0:
            return vote(
                "ONTOLOGY_STRUCTURE",
                "SUPPORT",
                0.82,
                "L'entitÃ© Pattern C est isolÃ©e du graphe courant.",
                proposal={
                    "action":
                        "REMOVE_REIFIED_ENTITY",

                    "entity_id":
                        entity_id_value,
                },
            )

        return vote(
            "ONTOLOGY_STRUCTURE",
            "VETO",
            0.0,
            "L'entitÃ© Pattern C possÃ¨de encore des relations actives.",
            hard_veto=True,
        )

    # --------------------------------------------------------
    # D
    # --------------------------------------------------------

    if family == "D":
        entity_id_value = metadata.get(
            "entity_id"
        )

        expected_type = metadata.get(
            "expected_type"
        )

        relation_id_value = metadata.get(
            "relation_id"
        )

        role = str(
            metadata.get(
                "role"
            )
            or ""
        ).upper()

        entity = (
            find_entity(
                doc,
                entity_id_value,
            )
            if doc
            and entity_id_value
            else None
        )

        relation = (
            find_relation(
                doc,
                relation_id_value,
            )
            if doc
            and relation_id_value
            else None
        )

        if (
            entity
            and expected_type
            and entity_type(
                entity
            )
            != expected_type
        ):
            return vote(
                "ONTOLOGY_STRUCTURE",
                "SUPPORT",
                0.86,
                "Le type courant viole encore le type attendu identifiÃ© par Pattern D.",
                proposal={
                    "action":
                        "RETYPE_ENTITY",

                    "entity_id":
                        entity_id_value,

                    "new_type":
                        expected_type,
                },
            )

        if relation:
            rtype = relation_type(
                relation
            )

            signature = signatures.get(
                rtype
            )

            if signature:
                source = find_entity(
                    doc,
                    relation_source(
                        relation
                    ),
                )

                target = find_entity(
                    doc,
                    relation_target(
                        relation
                    ),
                )

                source_ok = (
                    source
                    and entity_type(
                        source
                    )
                    == signature[
                        "domaine"
                    ]
                )

                target_ok = (
                    target
                    and entity_type(
                        target
                    )
                    == signature[
                        "image"
                    ]
                )

                if (
                    source_ok
                    and target_ok
                ):
                    return vote(
                        "ONTOLOGY_STRUCTURE",
                        "VETO",
                        0.0,
                        "La relation est dÃ©sormais conforme Ã  sa signature TRACE.",
                        hard_veto=True,
                    )

        return vote(
            "ONTOLOGY_STRUCTURE",
            "ABSTAIN",
            0.35,
            "La structure ne permet pas une action D unique.",
        )

    # --------------------------------------------------------
    # PATIENT / REFERENCE
    # --------------------------------------------------------

    if family == "PATIENT_REFERENCE":
        decision = agent_decision.get(
            "decision"
        )

        if decision == "PATIENT":
            return vote(
                "ONTOLOGY_STRUCTURE",
                "SUPPORT",
                0.8,
                "Le cas a Ã©tÃ© reconnu comme information patient par l'agent spÃ©cialisÃ©.",
                proposal={
                    "action":
                        "KEEP",
                },
            )

        if decision == "REFERENCE":
            return vote(
                "ONTOLOGY_STRUCTURE",
                "ABSTAIN",
                0.5,
                "RÃ©fÃ©rence probable, mais aucune suppression structurelle n'est autorisÃ©e automatiquement.",
            )

        return vote(
            "ONTOLOGY_STRUCTURE",
            "ABSTAIN",
            0.3,
            "Classification patient/rÃ©fÃ©rence encore ambiguÃ«.",
        )

    return vote(
        "ONTOLOGY_STRUCTURE",
        "ABSTAIN",
        0.0,
        "Famille inconnue.",
    )


# ============================================================
# 10. CLINICAL COHERENCE VOTE
# ============================================================

PATIENT_TERMS = (
    "patient",
    "chez le patient",
    "admis",
    "hospitalise",
    "hospitalisÃ©",
    "presente",
    "prÃ©sente",
    "evolution",
    "Ã©volution",
    "traitement",
    "apyrexie",
)

REFERENCE_TERMS = (
    "definition",
    "dÃ©finition",
    "seuil",
    "seuils",
    "critere",
    "critÃ¨re",
    "classification",
    "reference",
    "rÃ©fÃ©rence",
    "recommandation",
    "tableau",
    "norme",
)


def count_terms(
    text,
    vocabulary,
):
    normalized = normalize(
        text
    )

    return sum(
        1
        for term in vocabulary
        if normalize(
            term
        )
        in normalized
    )


def clinical_vote(
    family,
    item,
    context_item,
):
    text_context = (
        (
            context_item
            or {}
        ).get(
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

    if not page_text:
        return vote(
            "CLINICAL_COHERENCE",
            "ABSTAIN",
            0.0,
            "Contexte clinique textuel absent.",
        )

    patient_hits = count_terms(
        page_text,
        PATIENT_TERMS,
    )

    reference_hits = count_terms(
        page_text,
        REFERENCE_TERMS,
    )

    agent_decision = (
        item.get(
            "agent_decision"
        )
        or {}
    )

    metadata = (
        agent_decision.get(
            "metadata"
        )
        or {}
    )

    # --------------------------------------------------------
    # Patient/reference
    # --------------------------------------------------------

    if family == "PATIENT_REFERENCE":
        if (
            patient_hits >= 2
            and reference_hits == 0
        ):
            return vote(
                "CLINICAL_COHERENCE",
                "SUPPORT",
                0.9,
                "Le contexte local contient plusieurs marqueurs patient sans marqueur rÃ©fÃ©rentiel.",
                proposal={
                    "action":
                        "KEEP",
                },
            )

        if (
            reference_hits >= 2
            and patient_hits == 0
        ):
            return vote(
                "CLINICAL_COHERENCE",
                "SUPPORT",
                0.85,
                "Le contexte local est fortement rÃ©fÃ©rentiel.",
                proposal={
                    "action":
                        "CLASSIFY_REFERENCE",
                },
            )

        return vote(
            "CLINICAL_COHERENCE",
            "ABSTAIN",
            0.45,
            "Les indices patient/rÃ©fÃ©rence restent mixtes.",
        )

    # --------------------------------------------------------
    # C
    # --------------------------------------------------------

    if family == "C":
        if (
            patient_hits > 0
            and reference_hits == 0
        ):
            return vote(
                "CLINICAL_COHERENCE",
                "SUPPORT",
                0.7,
                "Le passage dÃ©crit un contexte clinique patient.",
            )

        if (
            reference_hits > patient_hits
        ):
            return vote(
                "CLINICAL_COHERENCE",
                "ABSTAIN",
                0.45,
                "Le passage peut correspondre Ã  du contenu rÃ©fÃ©rentiel.",
            )

        return vote(
            "CLINICAL_COHERENCE",
            "SUPPORT",
            0.6,
            "Aucune contradiction clinique explicite avec la proposition.",
        )

    # --------------------------------------------------------
    # D
    # --------------------------------------------------------

    if family == "D":
        lexicon_support = (
            metadata.get(
                "lexicon_support"
            )
            or []
        )

        if lexicon_support:
            return vote(
                "CLINICAL_COHERENCE",
                "SUPPORT",
                min(
                    0.95,
                    0.72
                    + 0.05
                    * len(
                        lexicon_support
                    ),
                ),
                "Le contexte contient des indices cliniques compatibles avec le type attendu.",
            )

        return vote(
            "CLINICAL_COHERENCE",
            "ABSTAIN",
            0.35,
            "Pas d'indice clinique lexical suffisamment discriminant.",
        )

    # --------------------------------------------------------
    # B
    # --------------------------------------------------------

    if family == "B":
        evidence = str(
            agent_decision.get(
                "evidence"
            )
            or ""
        )

        if (
            evidence
            and normalize(
                evidence
            )
            in normalize(
                page_text
            )
        ):
            return vote(
                "CLINICAL_COHERENCE",
                "SUPPORT",
                0.72,
                "La proposition est cohÃ©rente avec le passage clinique source.",
            )

        return vote(
            "CLINICAL_COHERENCE",
            "ABSTAIN",
            0.35,
            "La cohÃ©rence clinique B ne peut pas Ãªtre tranchÃ©e.",
        )

    return vote(
        "CLINICAL_COHERENCE",
        "ABSTAIN",
        0.0,
        "Famille inconnue.",
    )


# ============================================================
# 11. CONSENSUS
# ============================================================

def choose_action(
    family,
    item,
    votes,
):
    proposals = [
        v.get(
            "proposal"
        )
        for v in votes
        if (
            v.get(
                "verdict"
            )
            == "SUPPORT"
            and isinstance(
                v.get(
                    "proposal"
                ),
                dict,
            )
        )
    ]

    if not proposals:
        return None

    # Prefer exact identical action proposals.
    action_counter = Counter(
        p.get(
            "action"
        )
        for p in proposals
        if p.get(
            "action"
        )
    )

    if not action_counter:
        return None

    action, count = action_counter.most_common(
        1
    )[0]

    if count >= 2:
        matching = [
            p
            for p in proposals
            if p.get(
                "action"
            )
            == action
        ]

        merged = {
            "action":
                action,
        }

        for proposal in matching:
            for key, value in proposal.items():
                if (
                    key != "action"
                    and value not in (
                        None,
                        "",
                    )
                ):
                    merged[
                        key
                    ] = value

        return merged

    # One explicit proposal can still be used only for non-destructive KEEP.
    if (
        action
        == "KEEP"
        and count
        == 1
    ):
        return {
            "action":
                "KEEP",
        }

    return None


def adjudicate_case(
    family,
    item,
    context_item,
    doc,
    signatures,
):
    votes = [
        documentary_vote(
            family,
            item,
            context_item,
        ),

        ontology_vote(
            family,
            item,
            doc,
            signatures,
        ),

        clinical_vote(
            family,
            item,
            context_item,
        ),
    ]

    support_votes = [
        v
        for v in votes
        if v[
            "verdict"
        ]
        == "SUPPORT"
    ]

    veto_votes = [
        v
        for v in votes
        if (
            v[
                "verdict"
            ]
            == "VETO"
            or v.get(
                "hard_veto"
            )
        )
    ]

    documentary_support = any(
        (
            v[
                "agent"
            ]
            == "DOCUMENT_EVIDENCE"
            and v[
                "verdict"
            ]
            == "SUPPORT"
        )
        for v in votes
    )

    mean_support = (
        sum(
            v[
                "score"
            ]
            for v in support_votes
        )
        / len(
            support_votes
        )
        if support_votes
        else 0.0
    )

    action = choose_action(
        family,
        item,
        votes,
    )

    # -----------------------------------------
    # Resolution criteria
    # -----------------------------------------

    resolved = False

    if not veto_votes:
        if (
            len(
                support_votes
            )
            == 3
            and documentary_support
        ):
            resolved = True

        elif (
            len(
                support_votes
            )
            >= 2
            and documentary_support
            and mean_support
            >= 0.72
        ):
            resolved = True

    # A resolved case without an actionable or KEEP proposal
    # is only classified, not corrected.
    if resolved:
        if action:
            status = "RESOLVED"
            final_action = action.get(
                "action"
            )

        else:
            status = "RESOLVED_CLASSIFICATION_ONLY"
            final_action = "NONE"

    else:
        status = "UNRESOLVED"
        final_action = "NONE"
        action = None

    return {
        "family":
            family,

        "candidate_id":
            item.get(
                "candidate_id"
            ),

        "document":
            item.get(
                "document"
            ),

        "specialized_status":
            item.get(
                "final_status"
            ),

        "specialized_action":
            item.get(
                "final_action"
            ),

        "votes":
            votes,

        "support_vote_count":
            len(
                support_votes
            ),

        "veto_vote_count":
            len(
                veto_votes
            ),

        "mean_support_score":
            round(
                mean_support,
                4,
            ),

        "documentary_support":
            documentary_support,

        "adjudication_status":
            status,

        "adjudication_action":
            final_action,

        "proposed_correction":
            action,

        "reason":
            (
                "Consensus multi-agent suffisant."
                if resolved
                else
                "Consensus insuffisant ou prÃ©sence d'un veto."
            ),
    }


# ============================================================
# 12. MAIN
# ============================================================

def main():
    clinical_dir = resolve_clinical_dir()

    docs = load_clinical_docs(
        clinical_dir
    )

    contexts = load_context_maps()

    signatures = get_signatures()

    review_cases = []

    for family, path in INPUTS.items():
        if not path.exists():
            continue

        data = load_json(
            path
        )

        validated = (
            data.get(
                "validated_decisions",
                []
            )
            if isinstance(
                data,
                dict,
            )
            else []
        )

        for item in validated:
            if item.get(
                "final_status"
            ) != "REVIEW":
                continue

            review_cases.append(
                (
                    family,
                    item,
                )
            )

    results = []

    for family, item in review_cases:
        candidate_id = item.get(
            "candidate_id"
        )

        document = item.get(
            "document"
        )

        context_item = (
            contexts.get(
                family,
                {}
            ).get(
                candidate_id
            )
        )

        doc = docs.get(
            document
        )

        results.append(
            adjudicate_case(
                family,
                item,
                context_item,
                doc,
                signatures,
            )
        )

    status_counts = Counter(
        x[
            "adjudication_status"
        ]
        for x in results
    )

    action_counts = Counter(
        x[
            "adjudication_action"
        ]
        for x in results
    )

    family_counts = Counter(
        x[
            "family"
        ]
        for x in results
    )

    resolved_by_family = Counter(
        x[
            "family"
        ]
        for x in results
        if x[
            "adjudication_status"
        ].startswith(
            "RESOLVED"
        )
    )

    OUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUT.write_text(
        json.dumps(
            {
                "adjudicator":
                    "multiagent_adjudicator",

                "mode":
                    "THREE_VOTE_DOCUMENT_ONTOLOGY_CLINICAL",

                "clinical_context_directory":
                    str(
                        clinical_dir
                    ),

                "policy": {
                    "votes":
                        [
                            "DOCUMENT_EVIDENCE",
                            "ONTOLOGY_STRUCTURE",
                            "CLINICAL_COHERENCE",
                        ],

                    "resolution_rule":
                        (
                            "3/3 SUPPORT, or >=2 SUPPORT with "
                            "documentary support, mean score >=0.72, "
                            "and no veto"
                        ),
                },

                "summary": {
                    "review_cases_received":
                        len(
                            results
                        ),

                    "resolved":
                        sum(
                            1
                            for x in results
                            if x[
                                "adjudication_status"
                            ].startswith(
                                "RESOLVED"
                            )
                        ),

                    "unresolved":
                        status_counts.get(
                            "UNRESOLVED",
                            0,
                        ),

                    "status_counts":
                        dict(
                            status_counts
                        ),

                    "action_counts":
                        dict(
                            action_counts
                        ),

                    "by_family":
                        dict(
                            family_counts
                        ),

                    "resolved_by_family":
                        dict(
                            resolved_by_family
                        ),
                },

                "cases":
                    results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=" * 104)
    print("TRACE / SGCE - MULTI-AGENT ADJUDICATOR")
    print("=" * 104)

    print(
        f"Contexte clinique                    : "
        f"{clinical_dir}"
    )

    print(
        f"Cas REVIEW reÃ§us                     : "
        f"{len(results)}"
    )

    print(
        f"RÃ©solus par consensus                : "
        f"{sum(1 for x in results if x['adjudication_status'].startswith('RESOLVED'))}"
    )

    print(
        f"UNRESOLVED                           : "
        f"{status_counts.get('UNRESOLVED', 0)}"
    )

    print()

    print("STATUTS")
    print("-" * 104)

    for name, count in status_counts.most_common():
        print(
            f"{name:<48}: {count}"
        )

    print()

    print("ACTIONS ADJUDIQUEES")
    print("-" * 104)

    for name, count in action_counts.most_common():
        print(
            f"{str(name):<48}: {count}"
        )

    print()

    print("PAR FAMILLE")
    print("-" * 104)

    for family, count in family_counts.items():
        resolved = resolved_by_family.get(
            family,
            0,
        )

        print(
            f"{family:<30}: total={count:<4} rÃ©solus={resolved}"
        )

    print()

    print(
        f"Sortie                               : "
        f"{OUT}"
    )

    print()

    print(
        "Aucune donnÃ©e clinique n'a Ã©tÃ© modifiÃ©e."
    )


if __name__ == "__main__":
    main()

