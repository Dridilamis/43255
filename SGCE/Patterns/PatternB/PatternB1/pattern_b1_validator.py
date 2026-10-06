# -*- coding: utf-8 -*-
"""
pattern_b1_validator.py
=======================

SGCE — Pattern B1 Validator

Pattern B1:
Entité manquante implicite détectée à travers un endpoint relationnel absent.

IMPORTANT
---------
La détection B1 prouve seulement qu'une relation possède un endpoint qui
ne se résout pas vers une entité existante.

Cette validation distingue automatiquement :

1. RESOLVABLE_REFERENCE
   L'endpoint absent peut être rattaché de manière sûre à une entité
   déjà existante (normalisation textuelle / correspondance unique).
   Future action: RELINK

2. CONFIRMED_MISSING_ENTITY
   Aucune entité existante ne correspond, mais :
   - le type attendu de l'endpoint est inféré avec forte confiance
     à partir des relations valides du corpus ;
   - l'endpoint contient une valeur textuelle clinique exploitable,
     et non un identifiant opaque.
   Future action: CREATE_AND_LINK

3. UNRESOLVABLE_REFERENCE
   L'endpoint absent ressemble à un identifiant opaque.
   Impossible de reconstruire une entité sans inventer son contenu.
   Future action: NONE

4. AMBIGUOUS
   Plusieurs correspondances ou schéma relationnel insuffisamment stable.
   Future action: NONE

Aucun JSON clinique n'est modifié.
"""

import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


# ============================================================
# 1. PATHS
# ============================================================

PATTERN_B1_DIR = Path(__file__).resolve().parent
PATTERN_B_DIR = PATTERN_B1_DIR.parent
PATTERNS_DIR = PATTERN_B_DIR.parent
SGCE_DIR = PATTERNS_DIR.parent
BASE_DIR = SGCE_DIR.parent

PATTERN_A6_DIR = PATTERNS_DIR / "PatternA" / "PatternA6"

INPUT_DIR_CANDIDATES = [
    PATTERN_A6_DIR / "corrected",
]

DETECTION_REPORT_CANDIDATES = [
    PATTERN_B1_DIR / "detection" / "pattern_b1_detection_report.json",
]

OUTPUT_DIR = PATTERN_B1_DIR / "validation"
OUTPUT_JSON = OUTPUT_DIR / "pattern_b1_validation_report.json"
OUTPUT_CSV = OUTPUT_DIR / "pattern_b1_validation_candidates.csv"

# Schéma appris du corpus :
MIN_SCHEMA_SUPPORT = 3
MIN_SCHEMA_PURITY = 0.95


# ============================================================
# 2. HELPERS
# ============================================================

def normalize(text):
    text = "" if text is None else str(text)
    text = text.replace("’", "'")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        c for c in text
        if not unicodedata.combining(c)
    )
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def resolve_input_dir():
    for p in INPUT_DIR_CANDIDATES:
        if p.exists() and any(p.glob("*.json")):
            return p

    raise FileNotFoundError(
        "Dossier clinique d'entrée B1 introuvable."
    )


def resolve_detection_report():
    for p in DETECTION_REPORT_CANDIDATES:
        if p.exists():
            return p

    raise FileNotFoundError(
        "Rapport de détection B1 introuvable."
    )


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def is_clinical_document(doc):
    return (
        isinstance(doc, dict)
        and (
            isinstance(doc.get("global_entities"), list)
            or isinstance(doc.get("pages"), list)
        )
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
        or ""
    )


def entity_page(e):
    if e.get("page") is not None:
        return e.get("page")
    return e.get("page_number")


def entity_text_values(e):
    vals = []

    for key in (
        "name",
        "valeur",
        "libelle",
        "preuve",
        "parametre",
        "texte",
        "text",
    ):
        value = e.get(key)

        if value not in (None, ""):
            value = str(value).strip()

            if value and value not in vals:
                vals.append(value)

    return vals


def primary_entity_text(e):
    vals = entity_text_values(e)
    return vals[0] if vals else ""


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
        or r.get("type")
        or ""
    )


def relation_source(r):
    return (
        r.get("identifiant_entite_sujet")
        or r.get("from_id")
        or r.get("subject_id")
        or r.get("sujet")
        or r.get("subject")
    )


def relation_target(r):
    return (
        r.get("identifiant_entite_objet")
        or r.get("to_id")
        or r.get("object_id")
        or r.get("objet")
        or r.get("object")
    )


def relation_page(r):
    if r.get("page") is not None:
        return r.get("page")
    return r.get("page_number")


def get_entities(doc):
    if isinstance(doc.get("global_entities"), list):
        return doc["global_entities"]

    out = []

    for page in doc.get("pages", []) or []:
        out.extend(
            page.get("entities", []) or []
        )

    return out


def get_relations(doc):
    if isinstance(doc.get("global_relations"), list):
        return doc["global_relations"]

    out = []

    for page in doc.get("pages", []) or []:
        out.extend(
            page.get("relations", []) or []
        )

    return out


def build_indexes(entities):
    by_id = {}
    by_norm_text = defaultdict(list)

    for e in entities:
        eid = entity_id(e)

        if eid:
            by_id[str(eid).strip()] = e

        for value in entity_text_values(e):
            nv = normalize(value)

            if nv:
                by_norm_text[nv].append(e)

    return by_id, by_norm_text


def looks_like_opaque_id(value):
    """
    Détecte les références qui ressemblent davantage à un identifiant
    technique qu'à une mention clinique reconstructible.

    Exemples probables:
    P1_E023
    E_004
    ent_123
    entity-54
    P3E17
    """

    if value in (None, ""):
        return True

    raw = str(value).strip()

    patterns = [
        r"^[A-Za-z]*\d+[A-Za-z_\-]*\d*$",
        r"^[A-Za-z]+[_\-]\d+$",
        r"^P\d+[_\-]?E\d+$",
        r"^(ent|entity|e|id)[_\-]?\d+$",
        r"^[A-Za-z0-9_\-]{1,20}$",
    ]

    # Si la valeur contient un espace ou une ponctuation clinique,
    # elle est probablement textuelle.
    if " " in raw:
        return False

    # Mot alphabétique seul assez long : peut être une vraie mention.
    if raw.isalpha() and len(raw) >= 4:
        return False

    return any(
        re.fullmatch(p, raw, flags=re.IGNORECASE)
        for p in patterns
    )


# ============================================================
# 3. CORPUS-LEARNED RELATION SCHEMA
# ============================================================

def learn_relation_schema(documents):
    """
    Apprend uniquement à partir des relations dont les deux endpoints
    se résolvent correctement dans le corpus.

    Pour chaque type de relation :
      source type distribution
      target type distribution

    Aucun schéma externe n'est injecté.
    """

    source_counts = defaultdict(Counter)
    target_counts = defaultdict(Counter)

    for doc in documents.values():
        entities = get_entities(doc)
        relations = get_relations(doc)

        by_id, by_norm_text = build_indexes(entities)

        for r in relations:
            rtype = relation_type(r)

            if not rtype:
                continue

            src_val = relation_source(r)
            tgt_val = relation_target(r)

            src = resolve_existing_entity(
                src_val,
                by_id,
                by_norm_text,
                relation_page(r),
            )

            tgt = resolve_existing_entity(
                tgt_val,
                by_id,
                by_norm_text,
                relation_page(r),
            )

            if src["status"] == "UNIQUE" and tgt["status"] == "UNIQUE":
                src_type = entity_type(src["entity"])
                tgt_type = entity_type(tgt["entity"])

                if src_type:
                    source_counts[rtype][src_type] += 1

                if tgt_type:
                    target_counts[rtype][tgt_type] += 1

    schema = {}

    all_relations = (
        set(source_counts.keys())
        | set(target_counts.keys())
    )

    for rtype in all_relations:
        src_counter = source_counts[rtype]
        tgt_counter = target_counts[rtype]

        src_best, src_support, src_purity = dominant_type(src_counter)
        tgt_best, tgt_support, tgt_purity = dominant_type(tgt_counter)

        schema[rtype] = {
            "source": {
                "type": src_best,
                "support": src_support,
                "purity": src_purity,
                "reliable": (
                    src_support >= MIN_SCHEMA_SUPPORT
                    and src_purity >= MIN_SCHEMA_PURITY
                ),
                "distribution": dict(src_counter),
            },
            "target": {
                "type": tgt_best,
                "support": tgt_support,
                "purity": tgt_purity,
                "reliable": (
                    tgt_support >= MIN_SCHEMA_SUPPORT
                    and tgt_purity >= MIN_SCHEMA_PURITY
                ),
                "distribution": dict(tgt_counter),
            },
        }

    return schema


def dominant_type(counter):
    if not counter:
        return None, 0, 0.0

    total = sum(counter.values())
    best_type, best_count = counter.most_common(1)[0]

    purity = (
        best_count / total
        if total
        else 0.0
    )

    return (
        best_type,
        best_count,
        round(purity, 4),
    )


# ============================================================
# 4. SAFE EXISTING-ENTITY RESOLUTION
# ============================================================

def resolve_existing_entity(
    value,
    by_id,
    by_norm_text,
    preferred_page=None,
):
    if value in (None, ""):
        return {
            "status": "EMPTY",
            "entity": None,
            "candidates": [],
        }

    raw = str(value).strip()

    # Exact ID
    if raw in by_id:
        return {
            "status": "UNIQUE",
            "entity": by_id[raw],
            "candidates": [by_id[raw]],
            "method": "EXACT_ID",
        }

    # Normalized text
    nv = normalize(raw)
    matches = list(by_norm_text.get(nv, []))

    # Déduplique par entity ID
    unique = {}
    for e in matches:
        key = entity_id(e) or id(e)
        unique[key] = e

    matches = list(unique.values())

    # Priorité à la même page lorsque connue
    if preferred_page is not None and len(matches) > 1:
        same_page = [
            e for e in matches
            if entity_page(e) == preferred_page
        ]

        if len(same_page) == 1:
            return {
                "status": "UNIQUE",
                "entity": same_page[0],
                "candidates": same_page,
                "method": "NORMALIZED_TEXT_SAME_PAGE",
            }

        if same_page:
            matches = same_page

    if len(matches) == 1:
        return {
            "status": "UNIQUE",
            "entity": matches[0],
            "candidates": matches,
            "method": "NORMALIZED_TEXT",
        }

    if len(matches) > 1:
        return {
            "status": "AMBIGUOUS",
            "entity": None,
            "candidates": matches,
            "method": "NORMALIZED_TEXT_MULTIPLE",
        }

    return {
        "status": "NOT_FOUND",
        "entity": None,
        "candidates": [],
        "method": "NONE",
    }


# ============================================================
# 5. VALIDATE ONE MISSING ENDPOINT
# ============================================================

def validate_missing_endpoint(
    role,
    endpoint_value,
    relation,
    entities,
    schema,
):
    by_id, by_norm_text = build_indexes(entities)

    resolved = resolve_existing_entity(
        endpoint_value,
        by_id,
        by_norm_text,
        relation_page(relation),
    )

    rtype = relation_type(relation)

    role_schema = (
        schema.get(rtype, {})
        .get(role.lower(), {})
    )

    expected_type = role_schema.get("type")
    schema_reliable = bool(
        role_schema.get("reliable")
    )

    result = {
        "role": role,
        "endpoint_value": endpoint_value,
        "resolution_status":
            resolved["status"],
        "resolution_method":
            resolved.get("method"),
        "expected_type":
            expected_type,
        "schema_support":
            role_schema.get("support", 0),
        "schema_purity":
            role_schema.get("purity", 0.0),
        "schema_reliable":
            schema_reliable,
    }

    # --------------------------------------------------------
    # 1. Existing entity recovered safely
    # --------------------------------------------------------

    if resolved["status"] == "UNIQUE":
        e = resolved["entity"]

        type_ok = (
            expected_type is None
            or entity_type(e) == expected_type
        )

        result.update({
            "status": (
                "RESOLVABLE_REFERENCE"
                if type_ok
                else "AMBIGUOUS"
            ),
            "recommended_future_action": (
                "RELINK"
                if type_ok
                else "NONE"
            ),
            "resolved_entity_id":
                entity_id(e),
            "resolved_entity_type":
                entity_type(e),
            "resolved_entity_text":
                primary_entity_text(e),
            "reason": (
                "Endpoint rattachable de manière unique "
                "à une entité existante."
                if type_ok
                else
                "Correspondance existante trouvée mais "
                "son type est incompatible avec le schéma "
                "relationnel appris."
            ),
        })

        return result

    # --------------------------------------------------------
    # 2. Multiple matches => protected
    # --------------------------------------------------------

    if resolved["status"] == "AMBIGUOUS":
        result.update({
            "status": "AMBIGUOUS",
            "recommended_future_action": "NONE",
            "candidate_entity_ids": [
                entity_id(e)
                for e in resolved["candidates"]
            ],
            "reason": (
                "Plusieurs entités existantes correspondent "
                "à l'endpoint ; aucune décision automatique sûre."
            ),
        })

        return result

    # --------------------------------------------------------
    # 3. Empty endpoint => cannot reconstruct
    # --------------------------------------------------------

    if resolved["status"] == "EMPTY":
        result.update({
            "status": "UNRESOLVABLE_REFERENCE",
            "recommended_future_action": "NONE",
            "reason": (
                "Endpoint vide : aucune mention clinique "
                "permettant de reconstruire une entité."
            ),
        })

        return result

    # --------------------------------------------------------
    # 4. Missing but opaque technical ID => do NOT fabricate
    # --------------------------------------------------------

    if looks_like_opaque_id(endpoint_value):
        result.update({
            "status": "UNRESOLVABLE_REFERENCE",
            "recommended_future_action": "NONE",
            "reason": (
                "Endpoint absent sous forme d'identifiant opaque. "
                "Le contenu clinique de l'entité ne peut pas être "
                "reconstruit automatiquement sans invention."
            ),
        })

        return result

    # --------------------------------------------------------
    # 5. Human-readable endpoint + reliable inferred type
    # --------------------------------------------------------

    if schema_reliable and expected_type:
        result.update({
            "status": "CONFIRMED_MISSING_ENTITY",
            "recommended_future_action": "CREATE_AND_LINK",
            "proposed_entity_type": expected_type,
            "proposed_entity_text":
                str(endpoint_value).strip(),
            "reason": (
                "Aucune entité existante ne correspond, "
                "mais l'endpoint contient une mention textuelle "
                "exploitable et le type attendu est appris avec "
                "forte confiance à partir du corpus."
            ),
        })

        return result

    # --------------------------------------------------------
    # 6. Not enough structural evidence
    # --------------------------------------------------------

    result.update({
        "status": "AMBIGUOUS",
        "recommended_future_action": "NONE",
        "reason": (
            "Mention textuelle disponible mais schéma relationnel "
            "insuffisamment stable pour créer automatiquement "
            "une nouvelle entité."
        ),
    })

    return result


# ============================================================
# 6. MAIN
# ============================================================

def main():
    input_dir = resolve_input_dir()
    detection_report_path = resolve_detection_report()

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    detection = load_json(
        detection_report_path
    )

    candidates = detection.get(
        "candidates",
        []
    )

    documents = {}
    skipped_nonclinical = []
    errors = []

    for path in sorted(
        input_dir.glob("*.json")
    ):
        try:
            doc = load_json(path)

            if not is_clinical_document(doc):
                skipped_nonclinical.append(
                    path.name
                )
                continue

            documents[path.name] = doc

        except Exception as exc:
            errors.append({
                "document": path.name,
                "error": str(exc),
            })

    # Apprentissage structurel à partir des relations valides
    schema = learn_relation_schema(
        documents
    )

    validated_candidates = []

    for candidate in candidates:
        filename = candidate.get("document")
        doc = documents.get(filename)

        if doc is None:
            errors.append({
                "document": filename,
                "error":
                    "Document clinique correspondant introuvable.",
            })
            continue

        entities = get_entities(doc)
        relations = get_relations(doc)

        relation_info = candidate.get(
            "relation",
            {},
        )

        rid = relation_info.get(
            "relation_id"
        )

        # Retrouver relation originale
        relation = next(
            (
                r for r in relations
                if relation_id(r) == rid
            ),
            None,
        )

        # fallback par type/source/target
        if relation is None:
            relation = next(
                (
                    r for r in relations
                    if (
                        relation_type(r)
                        == relation_info.get("relation_type")
                        and str(relation_source(r))
                        == str(relation_info.get("source_value"))
                        and str(relation_target(r))
                        == str(relation_info.get("target_value"))
                    )
                ),
                None,
            )

        if relation is None:
            validated_candidates.append({
                **candidate,
                "validation_status":
                    "AMBIGUOUS",
                "recommended_future_action":
                    "NONE",
                "validation_reason":
                    "Relation candidate introuvable dans le document.",
                "endpoint_validations":
                    [],
            })
            continue

        endpoint_validations = []

        missing_roles = candidate.get(
            "missing_roles",
            [],
        )

        if (
            "SOURCE" in missing_roles
            or "SOURCE_EMPTY" in missing_roles
            or "SOURCE_AMBIGUOUS_NAME" in missing_roles
        ):
            endpoint_validations.append(
                validate_missing_endpoint(
                    "SOURCE",
                    relation_source(relation),
                    relation,
                    entities,
                    schema,
                )
            )

        if (
            "TARGET" in missing_roles
            or "TARGET_EMPTY" in missing_roles
            or "TARGET_AMBIGUOUS_NAME" in missing_roles
        ):
            endpoint_validations.append(
                validate_missing_endpoint(
                    "TARGET",
                    relation_target(relation),
                    relation,
                    entities,
                    schema,
                )
            )

        statuses = [
            e["status"]
            for e in endpoint_validations
        ]

        actions = [
            e["recommended_future_action"]
            for e in endpoint_validations
        ]

        # Candidate global status
        if (
            endpoint_validations
            and all(
                s == "RESOLVABLE_REFERENCE"
                for s in statuses
            )
        ):
            global_status = "RESOLVABLE_REFERENCE"

        elif (
            endpoint_validations
            and all(
                s in {
                    "RESOLVABLE_REFERENCE",
                    "CONFIRMED_MISSING_ENTITY",
                }
                for s in statuses
            )
            and any(
                s == "CONFIRMED_MISSING_ENTITY"
                for s in statuses
            )
        ):
            global_status = "CONFIRMED_MISSING_ENTITY"

        elif any(
            s == "UNRESOLVABLE_REFERENCE"
            for s in statuses
        ):
            global_status = "UNRESOLVABLE_REFERENCE"

        else:
            global_status = "AMBIGUOUS"

        # Future action
        if (
            actions
            and all(a == "RELINK" for a in actions)
        ):
            future_action = "RELINK"

        elif any(
            a == "CREATE_AND_LINK"
            for a in actions
        ):
            # Creation only if every other endpoint issue is safely resolved
            if all(
                a in {
                    "RELINK",
                    "CREATE_AND_LINK",
                }
                for a in actions
            ):
                future_action = "CREATE_AND_LINK"
            else:
                future_action = "NONE"

        else:
            future_action = "NONE"

        validated_candidates.append({
            **candidate,

            "validation_status":
                global_status,

            "recommended_future_action":
                future_action,

            "endpoint_validations":
                endpoint_validations,
        })

    status_counts = Counter(
        c["validation_status"]
        for c in validated_candidates
    )

    action_counts = Counter(
        c["recommended_future_action"]
        for c in validated_candidates
    )

    protected = sum(
        1
        for c in validated_candidates
        if c["recommended_future_action"] == "NONE"
    )

    report = {
        "pattern": "B1",
        "pattern_family": "B",
        "name":
            "Entité manquante implicite - validation endpoint relationnel",

        "methodological_status":
            "VALIDATION_ONLY_NO_CORRECTION",

        "input_directory":
            str(input_dir),

        "detection_report":
            str(detection_report_path),

        "schema_learning": {
            "minimum_support":
                MIN_SCHEMA_SUPPORT,

            "minimum_purity":
                MIN_SCHEMA_PURITY,

            "learned_relation_schema":
                schema,
        },

        "summary": {
            "clinical_documents_loaded":
                len(documents),

            "candidates_detected":
                len(candidates),

            "candidates_validated":
                len(validated_candidates),

            "resolvable_reference":
                status_counts.get(
                    "RESOLVABLE_REFERENCE",
                    0,
                ),

            "confirmed_missing_entity":
                status_counts.get(
                    "CONFIRMED_MISSING_ENTITY",
                    0,
                ),

            "unresolvable_reference":
                status_counts.get(
                    "UNRESOLVABLE_REFERENCE",
                    0,
                ),

            "ambiguous":
                status_counts.get(
                    "AMBIGUOUS",
                    0,
                ),

            "future_relink":
                action_counts.get(
                    "RELINK",
                    0,
                ),

            "future_create_and_link":
                action_counts.get(
                    "CREATE_AND_LINK",
                    0,
                ),

            "protected":
                protected,

            "errors":
                len(errors),
        },

        "validated_candidates":
            validated_candidates,

        "nonclinical_json_skipped":
            skipped_nonclinical,

        "errors":
            errors,
    }

    OUTPUT_JSON.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    fields = [
        "document",
        "relation_id",
        "relation_type",
        "source_value",
        "target_value",
        "missing_roles",
        "validation_status",
        "recommended_future_action",
        "endpoint_details",
    ]

    with OUTPUT_CSV.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fields,
        )

        writer.writeheader()

        for c in validated_candidates:
            rel = c.get(
                "relation",
                {},
            )

            details = []

            for ep in c.get(
                "endpoint_validations",
                [],
            ):
                details.append(
                    (
                        f"{ep.get('role')}:"
                        f"{ep.get('status')}:"
                        f"{ep.get('expected_type') or ''}:"
                        f"{ep.get('recommended_future_action')}"
                    )
                )

            writer.writerow({
                "document":
                    c.get("document", ""),

                "relation_id":
                    rel.get("relation_id", ""),

                "relation_type":
                    rel.get("relation_type", ""),

                "source_value":
                    rel.get("source_value", ""),

                "target_value":
                    rel.get("target_value", ""),

                "missing_roles":
                    "; ".join(
                        c.get("missing_roles", [])
                    ),

                "validation_status":
                    c.get("validation_status", ""),

                "recommended_future_action":
                    c.get(
                        "recommended_future_action",
                        "",
                    ),

                "endpoint_details":
                    " | ".join(details),
            })

    print("=" * 78)
    print("SGCE - PATTERN B1 VALIDATION")
    print("=" * 78)

    print(
        f"Entrée clinique           : "
        f"{input_dir}"
    )

    print(
        f"Rapport détection         : "
        f"{detection_report_path}"
    )

    print(
        f"Documents cliniques       : "
        f"{len(documents)}"
    )

    print()

    print(
        f"Candidats détectés        : "
        f"{len(candidates)}"
    )

    print(
        f"Candidats validés         : "
        f"{len(validated_candidates)}"
    )

    print()

    print(
        f"RESOLVABLE_REFERENCE      : "
        f"{status_counts.get('RESOLVABLE_REFERENCE', 0)}"
    )

    print(
        f"CONFIRMED_MISSING_ENTITY  : "
        f"{status_counts.get('CONFIRMED_MISSING_ENTITY', 0)}"
    )

    print(
        f"UNRESOLVABLE_REFERENCE    : "
        f"{status_counts.get('UNRESOLVABLE_REFERENCE', 0)}"
    )

    print(
        f"AMBIGUOUS                 : "
        f"{status_counts.get('AMBIGUOUS', 0)}"
    )

    print()

    print(
        f"Futurs RELINK             : "
        f"{action_counts.get('RELINK', 0)}"
    )

    print(
        f"Futurs CREATE_AND_LINK    : "
        f"{action_counts.get('CREATE_AND_LINK', 0)}"
    )

    print(
        f"Cas protégés              : "
        f"{protected}"
    )

    print(
        f"Erreurs                   : "
        f"{len(errors)}"
    )

    print()

    print(
        f"Rapport JSON              : "
        f"{OUTPUT_JSON}"
    )

    print(
        f"CSV validation            : "
        f"{OUTPUT_CSV}"
    )

    print()
    print(
        "Aucun JSON clinique n'a été modifié."
    )


if __name__ == "__main__":
    main()
