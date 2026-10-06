# -*- coding: utf-8 -*-

"""
semantic_factual_review_analyzer.py
===================================

TRACE / SGCE - SEMANTIC FACTUAL REVIEW ANALYZER V2

Compatible avec :
    semantic_factual_validated.json

Analyse uniquement les cas :
    final_status == REVIEW

Catégories actuellement attendues :
    - UNSUPPORTED_FACT
    - NEGATION_SENSITIVE
    - DOCUMENT_LEVEL_SUPPORT
    - AMBIGUOUS
    - UNRESOLVED_ENDPOINT

Objectifs :
    - compter précisément les REVIEW ;
    - analyser leur répartition ;
    - regrouper les cas par type de relation ;
    - regrouper les signatures :
          relation | type sujet -> type objet
    - distinguer les cas où les endpoints sont présents
      dans le document mais où le lien relationnel
      n'est pas suffisamment démontré ;
    - isoler les cas sensibles à la négation ;
    - fournir des exemples pour l'étape suivante.

IMPORTANT :
    UNSUPPORTED_FACT != hallucination confirmée.

Une absence de preuve suffisante ne permet PAS
de supprimer automatiquement une relation.

Aucune donnée clinique n'est modifiée.
"""

import json
from pathlib import Path
from collections import Counter, defaultdict


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent
VALIDATED_FILE = ROOT / "outputs" / "semantic_factual_validated.json"
OUT_JSON = ROOT / "outputs" / "semantic_factual_review_analysis.json"
OUT_TXT = ROOT / "outputs" / "semantic_factual_review_analysis.txt"

MAX_EXAMPLES_PER_GROUP = 5
MAX_GROUPS_IN_TXT = 30

# ============================================================
# JSON
# ============================================================

def load_json(path):
    with Path(path).open(
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


def save_json(path, obj):
    path = Path(path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            obj,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


# ============================================================
# HELPERS
# ============================================================

def relation_name(item):
    """
    V2 utilise relation_type.
    Compatibilité éventuelle avec anciens fichiers.
    """

    return (
        item.get("relation_type")
        or item.get("relation_name")
        or item.get("relation")
        or item.get("predicate")
        or "<VIDE>"
    )


def safe_text(value):
    if value is None:
        return ""

    return str(value).strip()


def make_signature(item):
    relation = relation_name(item)

    source_type = (
        item.get("source_type")
        or "<VIDE>"
    )

    target_type = (
        item.get("target_type")
        or "<VIDE>"
    )

    return (
        relation,
        source_type,
        target_type,
    )


def compact_example(item):
    """
    Conserve uniquement les informations utiles
    pour analyser les 247 REVIEW.
    """

    return {
        "candidate_id":
            item.get("candidate_id"),

        "document":
            item.get("document"),

        "relation_id":
            item.get("relation_id"),

        "relation_type":
            relation_name(item),

        "source_id":
            item.get("source_id"),

        "source_type":
            item.get("source_type"),

        "source_text":
            item.get("source_text"),

        "source_proof":
            item.get("source_proof"),

        "source_clinical_status":
            item.get("source_clinical_status"),

        "source_in_document":
            item.get("source_in_document"),

        "target_id":
            item.get("target_id"),

        "target_type":
            item.get("target_type"),

        "target_text":
            item.get("target_text"),

        "target_proof":
            item.get("target_proof"),

        "target_clinical_status":
            item.get("target_clinical_status"),

        "target_in_document":
            item.get("target_in_document"),

        "source_resolved":
            item.get("source_resolved"),

        "target_resolved":
            item.get("target_resolved"),

        "document_text_available":
            item.get("document_text_available"),

        "classification":
            item.get("classification"),

        "confidence":
            item.get("confidence"),

        "classifier_reason":
            item.get("classifier_reason"),

        "validator_reason":
            item.get("validator_reason"),
    }


# ============================================================
# MAIN
# ============================================================

def main():

    # --------------------------------------------------------
    # Vérification entrée
    # --------------------------------------------------------

    if not VALIDATED_FILE.exists():
        raise FileNotFoundError(
            f"Fichier validé introuvable : "
            f"{VALIDATED_FILE}"
        )

    data = load_json(
        VALIDATED_FILE
    )

    # ========================================================
    # IMPORTANT :
    # semantic_factual_validator.py V2 écrit :
    #
    #     "validated": [...]
    #
    # et non :
    #
    #     "validated_decisions"
    # ========================================================

    cases = data.get(
        "validated",
        [],
    )

    if not isinstance(
        cases,
        list,
    ):
        raise TypeError(
            "Le champ 'validated' doit être une liste."
        )

    # --------------------------------------------------------
    # REVIEW
    # --------------------------------------------------------

    review = [
        item
        for item in cases
        if item.get(
            "final_status"
        ) == "REVIEW"
    ]

    # --------------------------------------------------------
    # Compteurs
    # --------------------------------------------------------

    by_classification = Counter()

    by_relation = Counter()

    by_signature = Counter()

    by_endpoint_presence = Counter()

    by_negation_pattern = Counter()

    examples_by_classification = defaultdict(
        list
    )

    examples_by_relation = defaultdict(
        list
    )

    examples_by_signature = defaultdict(
        list
    )

    # ========================================================
    # ANALYSE
    # ========================================================

    for item in review:

        classification = (
            item.get("classification")
            or "UNKNOWN"
        )

        relation = relation_name(
            item
        )

        signature = make_signature(
            item
        )

        # ----------------------------------------------------
        # Compteurs généraux
        # ----------------------------------------------------

        by_classification[
            classification
        ] += 1

        by_relation[
            relation
        ] += 1

        by_signature[
            signature
        ] += 1

        # ----------------------------------------------------
        # Présence des endpoints dans le texte
        # ----------------------------------------------------

        source_in_doc = (
            item.get(
                "source_in_document"
            )
            is True
        )

        target_in_doc = (
            item.get(
                "target_in_document"
            )
            is True
        )

        if (
            source_in_doc
            and target_in_doc
        ):
            endpoint_presence = (
                "BOTH_ENDPOINTS_IN_DOCUMENT"
            )

        elif source_in_doc:
            endpoint_presence = (
                "ONLY_SOURCE_IN_DOCUMENT"
            )

        elif target_in_doc:
            endpoint_presence = (
                "ONLY_TARGET_IN_DOCUMENT"
            )

        else:
            endpoint_presence = (
                "NO_ENDPOINT_FOUND_IN_DOCUMENT"
            )

        by_endpoint_presence[
            endpoint_presence
        ] += 1

        # ----------------------------------------------------
        # Analyse NEGATION_SENSITIVE
        # ----------------------------------------------------

        if (
            classification
            == "NEGATION_SENSITIVE"
        ):

            source_status = str(
                item.get(
                    "source_clinical_status"
                )
                or ""
            ).upper()

            target_status = str(
                item.get(
                    "target_clinical_status"
                )
                or ""
            ).upper()

            if (
                source_status == "NEGATED"
                and target_status == "NEGATED"
            ):
                negation_case = (
                    "SOURCE_AND_TARGET_NEGATED"
                )

            elif (
                source_status == "NEGATED"
            ):
                negation_case = (
                    "SOURCE_NEGATED"
                )

            elif (
                target_status == "NEGATED"
            ):
                negation_case = (
                    "TARGET_NEGATED"
                )

            else:
                negation_case = (
                    "NEGATION_STATUS_NOT_IDENTIFIED"
                )

            by_negation_pattern[
                negation_case
            ] += 1

        # ----------------------------------------------------
        # Exemples classification
        # ----------------------------------------------------

        if (
            len(
                examples_by_classification[
                    classification
                ]
            )
            < MAX_EXAMPLES_PER_GROUP
        ):
            examples_by_classification[
                classification
            ].append(
                compact_example(
                    item
                )
            )

        # ----------------------------------------------------
        # Exemples relation
        # ----------------------------------------------------

        if (
            len(
                examples_by_relation[
                    relation
                ]
            )
            < MAX_EXAMPLES_PER_GROUP
        ):
            examples_by_relation[
                relation
            ].append(
                compact_example(
                    item
                )
            )

        # ----------------------------------------------------
        # Exemples signature
        # ----------------------------------------------------

        signature_key = (
            f"{signature[0]} | "
            f"{signature[1]} -> "
            f"{signature[2]}"
        )

        if (
            len(
                examples_by_signature[
                    signature_key
                ]
            )
            < MAX_EXAMPLES_PER_GROUP
        ):
            examples_by_signature[
                signature_key
            ].append(
                compact_example(
                    item
                )
            )

    # ========================================================
    # CATÉGORIES PRINCIPALES
    # ========================================================

    unsupported_count = (
        by_classification.get(
            "UNSUPPORTED_FACT",
            0,
        )
    )

    negation_count = (
        by_classification.get(
            "NEGATION_SENSITIVE",
            0,
        )
    )

    document_support_count = (
        by_classification.get(
            "DOCUMENT_LEVEL_SUPPORT",
            0,
        )
    )

    ambiguous_count = (
        by_classification.get(
            "AMBIGUOUS",
            0,
        )
    )

    unresolved_count = (
        by_classification.get(
            "UNRESOLVED_ENDPOINT",
            0,
        )
    )

    # ========================================================
    # RÉSULTAT JSON
    # ========================================================

    result = {

        "analyzer":
            "semantic_factual_review_analyzer",

        "mode":
            "SEMANTIC_FACTUAL_V2_REVIEW_ANALYSIS",

        "source_file":
            str(VALIDATED_FILE),

        "summary": {

            "total_decisions":
                len(cases),

            "review_cases":
                len(review),

            "supported_keep":
                sum(
                    1
                    for x in cases
                    if x.get(
                        "final_status"
                    )
                    == "SUPPORTED_KEEP"
                ),

            "unsupported_fact":
                unsupported_count,

            "negation_sensitive":
                negation_count,

            "document_level_support":
                document_support_count,

            "ambiguous":
                ambiguous_count,

            "unresolved_endpoint":
                unresolved_count,

            "distinct_review_relations":
                len(by_relation),

            "distinct_review_signatures":
                len(by_signature),
        },

        "review_by_classification":
            dict(
                by_classification.most_common()
            ),

        "review_by_relation":
            dict(
                by_relation.most_common()
            ),

        "endpoint_presence":
            dict(
                by_endpoint_presence.most_common()
            ),

        "negation_patterns":
            dict(
                by_negation_pattern.most_common()
            ),

        "review_signatures": [
            {
                "relation":
                    relation,

                "source_type":
                    source_type,

                "target_type":
                    target_type,

                "count":
                    count,
            }

            for (
                relation,
                source_type,
                target_type,
            ), count
            in by_signature.most_common()
        ],

        "examples_by_classification":
            dict(
                examples_by_classification
            ),

        "examples_by_relation":
            dict(
                examples_by_relation
            ),

        "examples_by_signature":
            dict(
                examples_by_signature
            ),
    }

    save_json(
        OUT_JSON,
        result,
    )

    # ========================================================
    # RAPPORT TXT
    # ========================================================

    lines = []

    lines.append(
        "=" * 125
    )

    lines.append(
        "TRACE / SGCE - "
        "SEMANTIC FACTUAL REVIEW ANALYZER V2"
    )

    lines.append(
        "=" * 125
    )

    lines.append(
        f"Décisions totales                   : "
        f"{len(cases)}"
    )

    lines.append(
        f"SUPPORTED_KEEP                      : "
        f"{result['summary']['supported_keep']}"
    )

    lines.append(
        f"Cas REVIEW                          : "
        f"{len(review)}"
    )

    lines.append("")

    lines.append(
        f"UNSUPPORTED_FACT                    : "
        f"{unsupported_count}"
    )

    lines.append(
        f"NEGATION_SENSITIVE                  : "
        f"{negation_count}"
    )

    lines.append(
        f"DOCUMENT_LEVEL_SUPPORT              : "
        f"{document_support_count}"
    )

    lines.append(
        f"AMBIGUOUS                           : "
        f"{ambiguous_count}"
    )

    lines.append(
        f"UNRESOLVED_ENDPOINT                 : "
        f"{unresolved_count}"
    )

    lines.append("")

    lines.append(
        f"Types de relation concernés         : "
        f"{len(by_relation)}"
    )

    lines.append(
        f"Signatures distinctes               : "
        f"{len(by_signature)}"
    )

    # ========================================================
    # REVIEW PAR CLASSIFICATION
    # ========================================================

    lines.append("")
    lines.append(
        "REVIEW PAR CLASSIFICATION"
    )
    lines.append(
        "-" * 125
    )

    if by_classification:

        for key, value in (
            by_classification.most_common()
        ):
            lines.append(
                f"{key:<65}: {value}"
            )

    else:
        lines.append(
            "Aucun cas REVIEW."
        )

    # ========================================================
    # ENDPOINT PRESENCE
    # ========================================================

    lines.append("")
    lines.append(
        "PRESENCE DES ENDPOINTS "
        "DANS LE DOCUMENT"
    )
    lines.append(
        "-" * 125
    )

    if by_endpoint_presence:

        for key, value in (
            by_endpoint_presence.most_common()
        ):
            lines.append(
                f"{key:<65}: {value}"
            )

    else:
        lines.append(
            "Aucun."
        )

    # ========================================================
    # NEGATION
    # ========================================================

    lines.append("")
    lines.append(
        "CAS SENSIBLES A LA NEGATION"
    )
    lines.append(
        "-" * 125
    )

    if by_negation_pattern:

        for key, value in (
            by_negation_pattern.most_common()
        ):
            lines.append(
                f"{key:<65}: {value}"
            )

    else:
        lines.append(
            "Aucun."
        )

    # ========================================================
    # RELATIONS
    # ========================================================

    lines.append("")
    lines.append(
        "REVIEW PAR TYPE DE RELATION"
    )
    lines.append(
        "-" * 125
    )

    if by_relation:

        for relation, count in (
            by_relation.most_common()
        ):
            lines.append(
                f"{relation:<65}: {count}"
            )

    else:
        lines.append(
            "Aucun."
        )

    # ========================================================
    # SIGNATURES
    # ========================================================

    lines.append("")
    lines.append(
        "SIGNATURES "
        "RELATION | TYPE SUJET -> TYPE OBJET"
    )
    lines.append(
        "-" * 125
    )

    if by_signature:

        for (
            relation,
            source_type,
            target_type,
        ), count in (
            by_signature.most_common()
        ):

            signature = (
                f"{relation} | "
                f"{source_type} -> "
                f"{target_type}"
            )

            lines.append(
                f"{signature:<105}: "
                f"{count}"
            )

    else:
        lines.append(
            "Aucune."
        )

    # ========================================================
    # EXEMPLES UNSUPPORTED
    # ========================================================

    lines.append("")
    lines.append(
        "EXEMPLES UNSUPPORTED_FACT"
    )
    lines.append(
        "-" * 125
    )

    unsupported_examples = (
        examples_by_classification.get(
            "UNSUPPORTED_FACT",
            [],
        )
    )

    if unsupported_examples:

        for ex in unsupported_examples:

            lines.append("")

            lines.append(
                f"{ex['document']} | "
                f"{ex['relation_id']}"
            )

            lines.append(
                f"  {ex['source_text']} "
                f"[{ex['source_type']}]"
            )

            lines.append(
                f"       --"
                f"{ex['relation_type']}"
                f"-->"
            )

            lines.append(
                f"  {ex['target_text']} "
                f"[{ex['target_type']}]"
            )

            lines.append(
                f"  Source dans document : "
                f"{ex['source_in_document']}"
            )

            lines.append(
                f"  Target dans document : "
                f"{ex['target_in_document']}"
            )

            lines.append(
                f"  Preuve source : "
                f"{ex['source_proof']!r}"
            )

            lines.append(
                f"  Preuve target : "
                f"{ex['target_proof']!r}"
            )

    else:
        lines.append(
            "Aucun."
        )

    # ========================================================
    # EXEMPLES NEGATION
    # ========================================================

    lines.append("")
    lines.append(
        "EXEMPLES NEGATION_SENSITIVE"
    )
    lines.append(
        "-" * 125
    )

    negation_examples = (
        examples_by_classification.get(
            "NEGATION_SENSITIVE",
            [],
        )
    )

    if negation_examples:

        for ex in negation_examples:

            lines.append("")

            lines.append(
                f"{ex['document']} | "
                f"{ex['relation_id']}"
            )

            lines.append(
                f"  {ex['source_text']} "
                f"[{ex['source_type']}] "
                f"status="
                f"{ex['source_clinical_status']}"
            )

            lines.append(
                f"       --"
                f"{ex['relation_type']}"
                f"-->"
            )

            lines.append(
                f"  {ex['target_text']} "
                f"[{ex['target_type']}] "
                f"status="
                f"{ex['target_clinical_status']}"
            )

    else:
        lines.append(
            "Aucun."
        )

    # ========================================================
    # AVERTISSEMENT
    # ========================================================

    lines.append("")
    lines.append(
        "INTERPRETATION"
    )
    lines.append(
        "-" * 125
    )

    lines.append(
        "UNSUPPORTED_FACT signifie que le support "
        "textuel de la relation n'a pas été "
        "suffisamment démontré."
    )

    lines.append(
        "Il ne signifie PAS automatiquement que "
        "la relation est fausse ou hallucinée."
    )

    lines.append(
        "Aucune suppression automatique ne doit "
        "être effectuée sur cette seule base."
    )

    # ========================================================
    # WRITE
    # ========================================================

    text = "\n".join(
        lines
    )

    OUT_TXT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUT_TXT.write_text(
        text,
        encoding="utf-8",
    )

    print(text)

    print()

    print(
        f"Rapport JSON                        : "
        f"{OUT_JSON}"
    )

    print(
        f"Rapport TXT                         : "
        f"{OUT_TXT}"
    )

    print()

    print(
        "Aucune donnée clinique n'a été modifiée."
    )


if __name__ == "__main__":
    main()