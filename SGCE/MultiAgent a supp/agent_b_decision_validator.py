# -*- coding: utf-8 -*-
"""
agent_b_decision_validator.py
=============================

TRACE / SGCE â€” Validateur dÃ©terministe des dÃ©cisions de l'Agent B

Objectif
--------
Valider les propositions de l'Agent B sans modifier les JSON cliniques.

Pour CREATE_FROM_EXPLICIT_EVIDENCE :
1) type proposÃ© == type attendu
2) preuve prÃ©sente dans le texte source
3) texte proposÃ© supportÃ© par la preuve
4) relation TRACE rÃ©cupÃ©rÃ©e correctement (str/dict/nested/fallback)
5) rÃ´le SOURCE/TARGET compatible avec la signature domaine/image
6) endpoint rÃ©ellement manquant
7) absence de doublon exact
8) proposition suffisamment atomique pour devenir une entitÃ© KG

Sorties :
- ACCEPT
- REVIEW
- REJECT

Important
---------
- Une impossibilitÃ© technique de rÃ©cupÃ©rer la relation ne provoque plus
  un faux REJECT : le cas passe en REVIEW.
- Une phrase clinique entiÃ¨re non atomique n'est pas automatiquement crÃ©Ã©e.
"""

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path


# ============================================================
# 1. PATHS
# ============================================================

BASE_DIR = Path(
    r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM"
    r"\Reduction_hallucinations"
)

MULTIAGENT_DIR = BASE_DIR / "MultiAgent"

AGENT_DECISIONS = (
    MULTIAGENT_DIR
    / "outputs"
    / "agent_b_decisions.json"
)

CONTEXT_QUEUE = (
    MULTIAGENT_DIR
    / "queues"
    / "agent_b_queue_contextualized.json"
)

GUIDELINE_CANDIDATES = [
    BASE_DIR / "Guideline_TRACE_Sepsis_v1.6.json",
    BASE_DIR.parent / "Guideline_TRACE_Sepsis_v1.6.json",
    Path.cwd() / "Guideline_TRACE_Sepsis_v1.6.json",
    Path(__file__).resolve().parent / "Guideline_TRACE_Sepsis_v1.6.json",
]

CLINICAL_INPUT_CANDIDATES = [
    BASE_DIR / "PatternD" / "pattern_d_corrected",
    BASE_DIR / "PatternC" / "pattern_c_corrected",
]

OUTPUT_DIR = MULTIAGENT_DIR / "outputs"

OUTPUT_FILE = (
    OUTPUT_DIR
    / "agent_b_validated_decisions.json"
)


# ============================================================
# 2. BASIC HELPERS
# ============================================================

def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_guideline():
    for path in GUIDELINE_CANDIDATES:
        if path.exists():
            return path

    raise FileNotFoundError(
        "Guideline_TRACE_Sepsis_v1.6.json introuvable."
    )


def resolve_clinical_input():
    for path in CLINICAL_INPUT_CANDIDATES:
        if path.exists() and any(path.glob("*.json")):
            return path

    return None


def normalize(text):
    text = "" if text is None else str(text)
    text = text.replace("â€™", "'")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        c for c in text
        if not unicodedata.combining(c)
    )
    text = text.lower()
    text = re.sub(r"[^a-z0-9/+.-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def is_clinical_document(doc):
    return isinstance(doc, dict) and (
        isinstance(doc.get("global_entities"), list)
        or isinstance(doc.get("pages"), list)
    )


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

        if value not in (None, ""):
            value = str(value).strip()

            if value and value not in values:
                values.append(value)

    return " | ".join(values)


def get_entities(doc):
    if isinstance(doc.get("global_entities"), list):
        return doc["global_entities"]

    out = []

    for page in doc.get("pages", []) or []:
        out.extend(page.get("entities", []) or [])

    return out


# ============================================================
# 3. RELATION EXTRACTION â€” CORRECTED
# ============================================================

RELATION_KEYS = (
    "type_relation",
    "relation_type",
    "relation",
    "predicate",
    "type",
    "label",
    "name",
)


def _extract_relation_from_value(value):
    """
    Supporte :
      "imagerie_objective_foyer"
      {"type_relation": "..."}
      {"relation": "..."}
      {"predicate": "..."}
      {"relation": {"type": "..."}}
    """

    if isinstance(value, str):
        return value.strip()

    if not isinstance(value, dict):
        return ""

    for key in RELATION_KEYS:
        candidate = value.get(key)

        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()

        if isinstance(candidate, dict):
            nested = _extract_relation_from_value(candidate)

            if nested:
                return nested

    # Search nested dictionaries conservatively
    for nested_value in value.values():
        if isinstance(nested_value, dict):
            nested = _extract_relation_from_value(nested_value)

            if nested:
                return nested

    return ""


def extract_relation_type(symbolic):
    """
    Extraction gÃ©nÃ©rique du type de relation depuis le candidat B1/B2.
    """

    # 1. Champ principal
    rtype = _extract_relation_from_value(
        symbolic.get("relation")
    )

    if rtype:
        return rtype

    # 2. Champs top-level
    for key in (
        "type_relation",
        "relation_type",
        "predicate",
    ):
        value = symbolic.get(key)

        if isinstance(value, str) and value.strip():
            return value.strip()

    # 3. Structures produites par certains dÃ©tecteurs/validateurs
    for container_key in (
        "source_resolution",
        "target_resolution",
        "relation_info",
        "relation_data",
        "relation_candidate",
    ):
        container = symbolic.get(container_key)

        rtype = _extract_relation_from_value(
            container
        )

        if rtype:
            return rtype

    return ""


# ============================================================
# 4. GUIDELINE SIGNATURES
# ============================================================

def get_locked_signatures(guideline):
    root = guideline.get(
        "ontologie_sepsis_graph",
        guideline,
    )

    locked = root.get(
        "signatures_relations_verrouillees_v1_5",
        {},
    )

    signatures = {}

    if not isinstance(locked, dict):
        return signatures

    for rtype, spec in locked.items():
        if not isinstance(spec, dict):
            continue

        domain = spec.get("domaine")
        image = spec.get("image")

        if domain and image:
            signatures[rtype] = {
                "domaine": domain,
                "image": image,
            }

    return signatures


# ============================================================
# 5. LOAD CLINICAL DOCS
# ============================================================

def load_clinical_docs():
    input_dir = resolve_clinical_input()

    if input_dir is None:
        return {}, None

    docs = {}

    for path in sorted(input_dir.glob("*.json")):
        try:
            doc = load_json(path)

            if is_clinical_document(doc):
                docs[path.name] = doc

        except Exception:
            pass

    return docs, input_dir


# ============================================================
# 6. ATOMICITY CHECK
# ============================================================

ATOMIC_SHORT_TYPES = {
    "IMAGERIE_PROCEDURE",
    "SYMPTOME",
    "MICRO_ORGANISME",
    "BIOMARQUEUR",
    "SIGNE_VITAL",
    "POSOLOGIE",
    "SERVICE_MEDICAL",
    "CONTEXTE_ACQUISITION",
}

# For these types, a slightly longer clinical phrase may still be acceptable,
# but not a complete narrative sentence with multiple events.
ATOMIC_MEDIUM_TYPES = {
    "LABEL_NOSOLOGIQUE",
    "DEFAILLANCE_ORGANE",
    "FOYER_INFECTIEUX",
    "COMORBIDITE_ANTECEDENT",
    "TRAITEMENT",
}


def atomicity_check(text, entity_type_name):
    """
    Conservative generic heuristic.
    Does NOT alter/extract a shorter span.
    It only decides whether the proposed text is atomic enough.
    """

    text = str(text or "").strip()

    if not text:
        return False, "EMPTY_PROPOSED_TEXT"

    words = re.findall(
        r"\b[\wÃ€-Ã¿'-]+\b",
        text,
        flags=re.UNICODE,
    )

    word_count = len(words)

    # Strong indicators that the proposal is a narrative sentence,
    # not an entity surface.
    narrative_markers = (
        " le patient ",
        " aprÃ¨s ",
        " apres ",
        " durant ",
        " motivant ",
        " associÃ© ",
        " associe ",
        " compliquÃ©e ",
        " compliquee ",
        " sous ",
        " puis ",
        " avec ",
        " et ",
        " ce qui ",
    )

    normalized_with_spaces = f" {normalize(text)} "

    narrative_hits = sum(
        1
        for marker in narrative_markers
        if normalize(marker) in normalized_with_spaces
    )

    # Multiple medication names / coordination often means composite treatment.
    plus_count = text.count("+")
    semicolon_count = text.count(";")

    if entity_type_name in ATOMIC_SHORT_TYPES:
        if word_count <= 8 and narrative_hits <= 1:
            return True, "ATOMIC_SHORT"

        return False, (
            f"NON_ATOMIC_SHORT_TYPE_WORDS_{word_count}"
        )

    if entity_type_name in ATOMIC_MEDIUM_TYPES:
        if (
            word_count <= 12
            and narrative_hits <= 2
            and plus_count <= 1
            and semicolon_count <= 1
        ):
            return True, "ATOMIC_MEDIUM"

        return False, (
            f"NON_ATOMIC_MEDIUM_TYPE_WORDS_{word_count}"
        )

    # Unknown/future types: generic conservative threshold.
    if word_count <= 10 and narrative_hits <= 1:
        return True, "ATOMIC_GENERIC"

    return False, (
        f"NON_ATOMIC_GENERIC_WORDS_{word_count}"
    )


# ============================================================
# 7. CONTEXT MAP
# ============================================================

def build_context_map(queue):
    return {
        item.get("candidate_id"): item
        for item in queue
        if item.get("candidate_id")
    }


# ============================================================
# 8. VALIDATE CREATE
# ============================================================

def validate_create(
    decision,
    context_item,
    doc,
    signatures,
):
    checks = []

    proposed_entities = (
        decision.get("proposed_entities")
        or []
    )

    if len(proposed_entities) != 1:
        return {
            "final_status": "REJECT",
            "final_action": "NONE",
            "checks": [
                {
                    "check": "EXACTLY_ONE_PROPOSED_ENTITY",
                    "passed": False,
                    "count": len(proposed_entities),
                }
            ],
            "reason": (
                "CREATE_FROM_EXPLICIT_EVIDENCE doit proposer "
                "exactement une entitÃ©."
            ),
        }

    proposed = proposed_entities[0]

    proposed_type = str(
        proposed.get("type") or ""
    ).strip()

    proposed_text = str(
        proposed.get("text") or ""
    ).strip()

    evidence = str(
        decision.get("evidence") or ""
    ).strip()

    symbolic = context_item.get(
        "symbolic_candidate",
        {},
    )

    endpoints = (
        symbolic.get("endpoint_validations")
        or []
    )

    if len(endpoints) != 1:
        return {
            "final_status": "REVIEW",
            "final_action": "NONE",
            "checks": [
                {
                    "check": "UNIQUE_ENDPOINT_VALIDATION",
                    "passed": False,
                    "count": len(endpoints),
                }
            ],
            "reason": (
                "Le candidat ne contient pas exactement un endpoint "
                "Ã  reconstruire; revue nÃ©cessaire."
            ),
        }

    endpoint = endpoints[0]

    expected_type = str(
        endpoint.get("expected_type")
        or ""
    ).strip()

    role = str(
        endpoint.get("role")
        or ""
    ).upper().strip()

    endpoint_value = (
        endpoint.get("endpoint_value")
    )

    rtype = extract_relation_type(
        symbolic
    )

    text_context = context_item.get(
        "text_context",
        {},
    )

    page_text = str(
        text_context.get("page_text")
        or ""
    )

    # --------------------------------------------------------
    # 1. TYPE
    # --------------------------------------------------------

    type_ok = (
        bool(proposed_type)
        and bool(expected_type)
        and proposed_type == expected_type
    )

    checks.append({
        "check": "TYPE_MATCHES_EXPECTED",
        "passed": type_ok,
        "actual": proposed_type,
        "expected": expected_type,
    })

    # --------------------------------------------------------
    # 2. EVIDENCE IN SOURCE TEXT
    # --------------------------------------------------------

    evidence_ok = (
        bool(evidence)
        and bool(page_text)
        and normalize(evidence)
        in normalize(page_text)
    )

    checks.append({
        "check": "EVIDENCE_PRESENT_IN_TEXT_CONTEXT",
        "passed": evidence_ok,
    })

    # --------------------------------------------------------
    # 3. PROPOSED TEXT SUPPORTED BY EVIDENCE
    # --------------------------------------------------------

    proposed_text_ok = (
        bool(proposed_text)
        and bool(evidence)
        and (
            normalize(proposed_text)
            in normalize(evidence)
            or normalize(evidence)
            in normalize(proposed_text)
        )
    )

    checks.append({
        "check": "PROPOSED_TEXT_SUPPORTED_BY_EVIDENCE",
        "passed": proposed_text_ok,
    })

    # --------------------------------------------------------
    # 4. RELATION TYPE â€” corrected extraction
    # --------------------------------------------------------

    relation_available = bool(
        rtype
    )

    checks.append({
        "check": "RELATION_TYPE_RECOVERED",
        "passed": relation_available,
        "relation_type": rtype,
    })

    relation_authorized = (
        relation_available
        and rtype in signatures
    )

    checks.append({
        "check": "RELATION_AUTHORIZED",
        "passed": relation_authorized,
        "relation_type": rtype,
    })

    # --------------------------------------------------------
    # 5. ROLE / DOMAIN-RANGE
    # --------------------------------------------------------

    role_ok = False
    expected_by_signature = None

    if relation_authorized:
        signature = signatures[
            rtype
        ]

        if role == "SOURCE":
            expected_by_signature = (
                signature["domaine"]
            )

            role_ok = (
                proposed_type
                == expected_by_signature
            )

        elif role == "TARGET":
            expected_by_signature = (
                signature["image"]
            )

            role_ok = (
                proposed_type
                == expected_by_signature
            )

    checks.append({
        "check": "ROLE_SIGNATURE_COMPATIBLE",
        "passed": role_ok,
        "role": role,
        "expected_by_signature": expected_by_signature,
        "actual_type": proposed_type,
    })

    # --------------------------------------------------------
    # 6. DUPLICATE
    # --------------------------------------------------------

    duplicate_found = False
    duplicate_entity_id = None

    if doc is not None:
        for entity in get_entities(doc):
            if (
                entity_type(entity) == proposed_type
                and normalize(
                    entity_text(entity)
                )
                == normalize(
                    proposed_text
                )
            ):
                duplicate_found = True
                duplicate_entity_id = entity_id(
                    entity
                )
                break

    checks.append({
        "check": "NO_EXACT_DUPLICATE_ENTITY",
        "passed": not duplicate_found,
        "duplicate_entity_id": duplicate_entity_id,
    })

    # --------------------------------------------------------
    # 7. ENDPOINT STILL MISSING
    # --------------------------------------------------------

    endpoint_missing = True

    if doc is not None and endpoint_value:
        endpoint_missing = not any(
            str(entity_id(entity))
            == str(endpoint_value)
            for entity in get_entities(doc)
        )

    checks.append({
        "check": "ENDPOINT_STILL_MISSING",
        "passed": endpoint_missing,
        "endpoint_value": endpoint_value,
    })

    # --------------------------------------------------------
    # 8. ATOMICITY
    # --------------------------------------------------------

    atomic_ok, atomic_reason = atomicity_check(
        proposed_text,
        proposed_type,
    )

    checks.append({
        "check": "PROPOSED_ENTITY_ATOMIC",
        "passed": atomic_ok,
        "reason": atomic_reason,
        "word_count": len(
            re.findall(
                r"\b[\wÃ€-Ã¿'-]+\b",
                proposed_text,
                flags=re.UNICODE,
            )
        ),
    })

    # ========================================================
    # FINAL LOGIC
    # ========================================================

    # Technical inability to recover relation metadata:
    # NEVER turn that into a false semantic rejection.
    if not relation_available:
        return {
            "final_status": "REVIEW",
            "final_action": "NONE",
            "checks": checks,
            "reason": (
                "La preuve et le type proposÃ© peuvent Ãªtre valides, "
                "mais le type de relation n'a pas pu Ãªtre rÃ©cupÃ©rÃ© "
                "dans le candidat symbolique. Revue nÃ©cessaire."
            ),
        }

    # Relation exists but is not part of TRACE:
    # this is a real structural rejection.
    if relation_available and not relation_authorized:
        return {
            "final_status": "REJECT",
            "final_action": "NONE",
            "checks": checks,
            "reason": (
                f"La relation '{rtype}' n'appartient pas aux "
                "signatures TRACE-Sepsis autorisÃ©es."
            ),
        }

    # Existing identical entity => do not create a duplicate.
    if (
        duplicate_found
        and type_ok
        and evidence_ok
        and proposed_text_ok
        and relation_authorized
        and role_ok
    ):
        return {
            "final_status": "REVIEW",
            "final_action": "RELINK_EXISTING_ENTITY",
            "checks": checks,
            "existing_entity_id": duplicate_entity_id,
            "reason": (
                "Une entitÃ© identique existe dÃ©jÃ . "
                "La crÃ©ation est bloquÃ©e; un RELINK doit Ãªtre Ã©tudiÃ©."
            ),
        }

    # Non-atomic proposal:
    # evidence may be correct, but entity surface must be refined.
    if (
        type_ok
        and evidence_ok
        and proposed_text_ok
        and relation_authorized
        and role_ok
        and endpoint_missing
        and not atomic_ok
    ):
        return {
            "final_status": "REVIEW",
            "final_action": "REFINE_ENTITY_SPAN",
            "checks": checks,
            "reason": (
                "La preuve, le type et la relation sont cohÃ©rents, "
                "mais le texte proposÃ© n'est pas suffisamment atomique "
                "pour Ãªtre crÃ©Ã© tel quel comme entitÃ©."
            ),
        }

    # Full safe acceptance
    critical_checks = [
        type_ok,
        evidence_ok,
        proposed_text_ok,
        relation_authorized,
        role_ok,
        endpoint_missing,
        not duplicate_found,
        atomic_ok,
    ]

    if all(critical_checks):
        return {
            "final_status": "ACCEPT",
            "final_action": "CREATE_FROM_EXPLICIT_EVIDENCE",
            "checks": checks,
            "reason": (
                "La proposition est explicitement ancrÃ©e dans le texte, "
                "atomique, conforme au type attendu et Ã  la signature "
                "TRACE-Sepsis, sans doublon."
            ),
        }

    # Otherwise, distinguish uncertainty from real inconsistency.
    hard_fail = (
        not type_ok
        or not evidence_ok
        or not proposed_text_ok
        or not role_ok
        or not endpoint_missing
    )

    if hard_fail:
        return {
            "final_status": "REJECT",
            "final_action": "NONE",
            "checks": checks,
            "reason": (
                "Au moins un contrÃ´le critique de contenu, "
                "de typage ou de signature a Ã©chouÃ©."
            ),
        }

    return {
        "final_status": "REVIEW",
        "final_action": "NONE",
        "checks": checks,
        "reason": (
            "La proposition reste insuffisamment dÃ©terminÃ©e pour "
            "une correction automatique."
        ),
    }


# ============================================================
# 9. MASTER VALIDATION
# ============================================================

def validate_decision(
    decision,
    context_item,
    doc,
    signatures,
):
    action = decision.get(
        "action"
    )

    if action == "CREATE_FROM_EXPLICIT_EVIDENCE":
        return validate_create(
            decision,
            context_item,
            doc,
            signatures,
        )

    if action == "NONE":
        return {
            "final_status": "REVIEW",
            "final_action": "NONE",
            "checks": [],
            "reason": (
                "L'Agent B n'a proposÃ© aucune correction automatique."
            ),
        }

    return {
        "final_status": "REVIEW",
        "final_action": action or "NONE",
        "checks": [],
        "reason": (
            "Action proposÃ©e non couverte automatiquement par ce "
            "validateur; revue nÃ©cessaire."
        ),
    }


# ============================================================
# 10. MAIN
# ============================================================

def main():
    if not AGENT_DECISIONS.exists():
        raise FileNotFoundError(
            f"DÃ©cisions Agent B introuvables : {AGENT_DECISIONS}"
        )

    if not CONTEXT_QUEUE.exists():
        raise FileNotFoundError(
            f"Queue contextualisÃ©e B introuvable : {CONTEXT_QUEUE}"
        )

    guideline_path = resolve_guideline()

    guideline = load_json(
        guideline_path
    )

    signatures = get_locked_signatures(
        guideline
    )

    docs, clinical_input = load_clinical_docs()

    agent_output = load_json(
        AGENT_DECISIONS
    )

    if isinstance(agent_output, dict):
        decisions = agent_output.get(
            "decisions",
            [],
        )
    elif isinstance(agent_output, list):
        decisions = agent_output
    else:
        decisions = []

    context_queue = load_json(
        CONTEXT_QUEUE
    )

    context_map = build_context_map(
        context_queue
    )

    validated = []

    for decision in decisions:
        cid = decision.get(
            "candidate_id"
        )

        context_item = context_map.get(
            cid
        )

        document = decision.get(
            "document"
        )

        doc = docs.get(
            document
        )

        if context_item is None:
            validated.append({
                "candidate_id": cid,
                "document": document,
                "agent_decision": decision,
                "final_status": "REJECT",
                "final_action": "NONE",
                "reason": "Contexte correspondant introuvable.",
                "checks": [],
            })

            continue

        result = validate_decision(
            decision,
            context_item,
            doc,
            signatures,
        )

        validated.append({
            "candidate_id": cid,
            "document": document,
            "agent_decision": decision,
            **result,
        })

    status_counts = Counter(
        item["final_status"]
        for item in validated
    )

    action_counts = Counter(
        item["final_action"]
        for item in validated
    )

    output = {
        "validator": "agent_b_decision_validator",
        "version": "2.0",
        "guideline": str(guideline_path),
        "clinical_context_directory": (
            str(clinical_input)
            if clinical_input
            else None
        ),
        "summary": {
            "decisions_received": len(decisions),
            "validated": len(validated),
            "status_counts": dict(status_counts),
            "action_counts": dict(action_counts),
            "locked_signatures_loaded": len(signatures),
        },
        "validated_decisions": validated,
    }

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_FILE.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=" * 96)
    print("TRACE / SGCE - AGENT B DECISION VALIDATOR")
    print("=" * 96)

    print(
        f"DÃ©cisions reÃ§ues                  : "
        f"{len(decisions)}"
    )

    print(
        f"DÃ©cisions validÃ©es                : "
        f"{len(validated)}"
    )

    print(
        f"Signatures TRACE chargÃ©es         : "
        f"{len(signatures)}"
    )

    print()

    print("STATUTS FINAUX")
    print("-" * 96)

    for name, count in status_counts.most_common():
        print(
            f"{name:<40}: {count}"
        )

    print()

    print("ACTIONS FINALES")
    print("-" * 96)

    for name, count in action_counts.most_common():
        print(
            f"{name:<40}: {count}"
        )

    print()

    print(
        f"Sortie                            : "
        f"{OUTPUT_FILE}"
    )

    print()

    print(
        "Aucune donnÃ©e clinique n'a Ã©tÃ© modifiÃ©e."
    )


if __name__ == "__main__":
    main()

