# -*- coding: utf-8 -*-

"""
TRACE / SGCE - ENTITY VALIDATION VALIDATOR V1
GROUP-LEVEL CONSERVATIVE RETYPING VALIDATION

Entrée :
    MultiAgent/entity_validation/outputs/
        entity_validation_decisions.json

Sortie :
    MultiAgent/entity_validation/outputs/
        entity_validation_validated.json

OBJECTIF
--------
Valider les propositions de retypage ontologique au niveau ENTITE.

IMPORTANT
---------
Le classifier travaille au niveau des anomalies/relation.
Une même entité peut donc produire 10, 20 ou 50 anomalies.

Le validator ne crée PAS une correction par anomalie.

Il crée au maximum :
    UNE opération RETYPE_ENTITY
    pour UNE entité physique dans UN document.

Conditions SAFE_ACCEPT :
    1. Au moins une décision ENTITY_MISTYPING_STRONG.
    2. Toutes les décisions STRONG convergent vers le même expected_type.
    3. Aucun expected_type concurrent dans les décisions STRONG.
    4. Le type actuel est connu.
    5. Le nouveau type diffère du type actuel.
    6. L'entité est résolue de manière fiable.
    7. Il existe au moins un signal lexical STRONG.
    8. Au moins deux violations convergent vers le type attendu.
    9. Le ratio de convergence est >= 0.80.

Le validator ne modifie AUCUNE donnée clinique.
"""

# GENERICITY PATCH: configuration via environment; no corpus-example lexicon.

import os
import json

from pathlib import Path
from collections import Counter, defaultdict


# =====================================================================
# CONFIGURATION
# =====================================================================

ROOT = Path(__file__).resolve().parent
INPUT_FILE = ROOT / "outputs" / "entity_validation_decisions.json"
OUTPUT_FILE = ROOT / "outputs" / "entity_validation_validated.json"
OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)


# =====================================================================
# PARAMETRES DE SECURITE
# =====================================================================

MIN_CONVERGENT_VIOLATIONS = int(os.environ.get("TRACE_MIN_CONVERGENT_VIOLATIONS", "2"))

MIN_DOMINANT_RATIO = float(os.environ.get("TRACE_MIN_DOMINANT_RATIO", "0.80"))

MIN_STRONG_CONFIDENCE = float(os.environ.get("TRACE_MIN_STRONG_CONFIDENCE", "0.99"))


# =====================================================================
# RESOLUTIONS D'ENTITE AUTORISEES
# =====================================================================

SAFE_ENTITY_RESOLUTIONS = {
    "ID_EXACT",
    "ID_DUPLICATE_EQUIVALENT",
    "AUDIT_ID_EXACT",
    "AUDIT_ID_DUPLICATE_EQUIVALENT",
}


# =====================================================================
# UTILITAIRES
# =====================================================================

def load_json(path):

    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(
            f"Fichier introuvable : {path}"
        )

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def dump_json(path, obj):

    path = Path(path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    path.write_text(
        json.dumps(
            obj,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


def clean(value):

    if value is None:
        return ""

    return str(value).strip()


def normalize_type(value):

    return clean(value).upper()


def safe_float(value, default=0.0):

    try:
        return float(value)

    except Exception:
        return default


# =====================================================================
# GROUPAGE PAR ENTITE
# =====================================================================

def build_entity_groups(decisions):

    groups = defaultdict(list)

    for decision in decisions:

        document = clean(
            decision.get("document")
        )

        entity_id = clean(
            decision.get("entity_id")
        )

        if not document or not entity_id:
            continue

        groups[
            (
                document,
                entity_id
            )
        ].append(decision)

    return groups


# =====================================================================
# SIGNAUX LEXICAUX
# =====================================================================

def collect_lexical_signals(group):

    signals = []

    seen = set()

    for decision in group:

        for signal in (
            decision.get("lexical_signals")
            or []
        ):

            if not isinstance(signal, dict):
                continue

            name = clean(
                signal.get("signal")
            )

            strength = clean(
                signal.get("strength")
            ).upper()

            key = (
                name,
                strength
            )

            if key in seen:
                continue

            seen.add(key)

            signals.append({
                "signal": name,
                "strength": strength
            })

    return signals


# =====================================================================
# ANALYSE D'UN GROUPE
# =====================================================================

def analyze_group(group):

    expected_all = Counter()

    expected_strong = Counter()

    current_types = Counter()

    classifications = Counter()

    resolutions = Counter()

    relations = Counter()

    strong_decisions = []

    for decision in group:

        classification = clean(
            decision.get("classification")
        )

        classifications[
            classification
        ] += 1

        expected = normalize_type(
            decision.get("expected_type")
        )

        current = normalize_type(
            decision.get("entity_type")
        )

        resolution = clean(
            decision.get("entity_resolution")
        )

        relation_name = clean(
            decision.get("relation_name")
        )

        if expected:
            expected_all[
                expected
            ] += 1

        if current:
            current_types[
                current
            ] += 1

        if resolution:
            resolutions[
                resolution
            ] += 1

        if relation_name:
            relations[
                relation_name
            ] += 1

        if (
            classification
            == "ENTITY_MISTYPING_STRONG"
        ):

            strong_decisions.append(
                decision
            )

            if expected:
                expected_strong[
                    expected
                ] += 1

    # -----------------------------------------------------------------
    # Dominant expected type sur TOUT le groupe
    # -----------------------------------------------------------------

    dominant_expected = None
    dominant_count = 0

    if expected_all:

        (
            dominant_expected,
            dominant_count
        ) = expected_all.most_common(1)[0]

    total = len(group)

    dominant_ratio = (
        dominant_count / total
        if total
        else 0.0
    )

    # -----------------------------------------------------------------
    # Expected type des STRONG
    # -----------------------------------------------------------------

    strong_expected_type = None

    if len(expected_strong) == 1:

        strong_expected_type = next(
            iter(expected_strong)
        )

    # -----------------------------------------------------------------
    # Type actuel
    # -----------------------------------------------------------------

    current_type = None

    if len(current_types) == 1:

        current_type = next(
            iter(current_types)
        )

    # -----------------------------------------------------------------
    # Résolutions
    # -----------------------------------------------------------------

    all_resolutions_safe = all(
        resolution
        in SAFE_ENTITY_RESOLUTIONS
        for resolution
        in resolutions
    )

    # -----------------------------------------------------------------
    # Signaux lexicaux
    # -----------------------------------------------------------------

    lexical_signals = (
        collect_lexical_signals(
            group
        )
    )

    has_strong_lexical = any(
        signal.get("strength")
        == "STRONG"
        for signal in lexical_signals
    )

    # -----------------------------------------------------------------
    # Confiance des STRONG
    # -----------------------------------------------------------------

    strong_confidences = [
        safe_float(
            decision.get("confidence")
        )
        for decision
        in strong_decisions
    ]

    all_strong_confidence_ok = (
        bool(strong_confidences)
        and all(
            confidence
            >= MIN_STRONG_CONFIDENCE
            for confidence
            in strong_confidences
        )
    )

    return {

        "number_of_decisions":
            total,

        "number_of_strong_decisions":
            len(strong_decisions),

        "classification_counts":
            dict(classifications),

        "expected_type_counts":
            dict(expected_all),

        "strong_expected_type_counts":
            dict(expected_strong),

        "current_type_counts":
            dict(current_types),

        "entity_resolution_counts":
            dict(resolutions),

        "relation_counts":
            dict(relations),

        "dominant_expected_type":
            dominant_expected,

        "dominant_expected_count":
            dominant_count,

        "dominant_expected_ratio":
            round(
                dominant_ratio,
                4
            ),

        "strong_expected_type":
            strong_expected_type,

        "current_type":
            current_type,

        "all_resolutions_safe":
            all_resolutions_safe,

        "lexical_signals":
            lexical_signals,

        "has_strong_lexical_signal":
            has_strong_lexical,

        "all_strong_confidence_ok":
            all_strong_confidence_ok,
    }


# =====================================================================
# VALIDATION D'UN GROUPE
# =====================================================================

def validate_group(
    document,
    entity_id,
    group,
    analysis
):

    first = group[0]

    entity_text = clean(
        first.get("entity_text")
    )

    current_type = normalize_type(
        analysis.get("current_type")
    )

    expected_type = normalize_type(
        analysis.get(
            "strong_expected_type"
        )
    )

    number_strong = int(
        analysis.get(
            "number_of_strong_decisions",
            0
        )
    )

    dominant_expected = normalize_type(
        analysis.get(
            "dominant_expected_type"
        )
    )

    dominant_count = int(
        analysis.get(
            "dominant_expected_count",
            0
        )
    )

    dominant_ratio = safe_float(
        analysis.get(
            "dominant_expected_ratio"
        )
    )

    # =================================================================
    # 1. Aucun STRONG
    # =================================================================

    if number_strong == 0:

        return {
            "final_status":
                "REVIEW",

            "final_action":
                "NONE",

            "reason":
                (
                    "Aucune décision ENTITY_MISTYPING_STRONG "
                    "n'est disponible pour cette entité."
                )
        }

    # =================================================================
    # 2. Plusieurs expected types parmi les STRONG
    # =================================================================

    if not expected_type:

        return {
            "final_status":
                "REJECT_UNSAFE",

            "final_action":
                "NONE",

            "reason":
                (
                    "Les décisions STRONG ne convergent pas vers "
                    "un unique type ontologique attendu."
                )
        }

    # =================================================================
    # 3. Plusieurs types actuels
    # =================================================================

    if not current_type:

        return {
            "final_status":
                "REJECT_UNSAFE",

            "final_action":
                "NONE",

            "reason":
                (
                    "Le même identifiant d'entité présente plusieurs "
                    "types actuels incompatibles."
                )
        }

    # =================================================================
    # 4. Même type avant / après
    # =================================================================

    if current_type == expected_type:

        return {
            "final_status":
                "ALREADY_SATISFIED",

            "final_action":
                "NONE",

            "reason":
                (
                    "Le type actuel correspond déjà au type attendu."
                )
        }

    # =================================================================
    # 5. Résolution non sûre
    # =================================================================

    if not analysis.get(
        "all_resolutions_safe"
    ):

        return {
            "final_status":
                "REVIEW",

            "final_action":
                "NONE",

            "reason":
                (
                    "Au moins une occurrence de l'entité n'a pas "
                    "été résolue par une méthode suffisamment sûre."
                )
        }

    # =================================================================
    # 6. Pas assez de violations convergentes
    # =================================================================

    if dominant_count < MIN_CONVERGENT_VIOLATIONS:

        return {
            "final_status":
                "REVIEW",

            "final_action":
                "NONE",

            "reason":
                (
                    "Nombre insuffisant de violations indépendantes "
                    "convergeant vers le même type."
                )
        }

    # =================================================================
    # 7. Type dominant différent du type STRONG
    # =================================================================

    if dominant_expected != expected_type:

        return {
            "final_status":
                "REJECT_UNSAFE",

            "final_action":
                "NONE",

            "reason":
                (
                    "Le type dominant de l'ensemble des violations "
                    "diffère du type proposé par les décisions STRONG."
                )
        }

    # =================================================================
    # 8. Ratio insuffisant
    # =================================================================

    if dominant_ratio < MIN_DOMINANT_RATIO:

        return {
            "final_status":
                "REVIEW",

            "final_action":
                "NONE",

            "reason":
                (
                    "La convergence des contraintes ontologiques "
                    "vers le type attendu est insuffisante."
                )
        }

    # =================================================================
    # 9. Absence de signal lexical STRONG
    # =================================================================

    if not analysis.get(
        "has_strong_lexical_signal"
    ):

        return {
            "final_status":
                "REVIEW",

            "final_action":
                "NONE",

            "reason":
                (
                    "Les contraintes relationnelles convergent, "
                    "mais aucune preuve lexicale STRONG indépendante "
                    "ne confirme le nouveau type."
                )
        }

    # =================================================================
    # 10. Confiance classifier
    # =================================================================

    if not analysis.get(
        "all_strong_confidence_ok"
    ):

        return {
            "final_status":
                "REVIEW",

            "final_action":
                "NONE",

            "reason":
                (
                    "La confiance des décisions STRONG est "
                    "insuffisante pour autoriser une correction."
                )
        }

    # =================================================================
    # SAFE ACCEPT
    # =================================================================

    return {
        "final_status":
            "SAFE_ACCEPT",

        "final_action":
            "RETYPE_ENTITY",

        "reason":
            (
                "Plusieurs violations ontologiques convergent vers "
                "un même type attendu, l'entité est résolue de façon "
                "fiable et une preuve lexicale STRONG indépendante "
                "soutient le retypage."
            )
    }


# =====================================================================
# MAIN
# =====================================================================

def main():

    print("=" * 120)

    print(
        "TRACE / SGCE - ENTITY VALIDATION VALIDATOR V1 "
        "- GROUP-LEVEL SAFE RETYPING"
    )

    print("=" * 120)

    data = load_json(
        INPUT_FILE
    )

    decisions = data.get(
        "decisions",
        []
    )

    groups = build_entity_groups(
        decisions
    )

    validated_groups = []

    status_counter = Counter()

    action_counter = Counter()

    type_changes = Counter()

    # =================================================================
    # VALIDATION GROUPE PAR GROUPE
    # =================================================================

    for index, (
        (
            document,
            entity_id
        ),
        group
    ) in enumerate(
        groups.items(),
        start=1
    ):

        analysis = analyze_group(
            group
        )

        validation = validate_group(
            document,
            entity_id,
            group,
            analysis
        )

        first = group[0]

        current_type = normalize_type(
            analysis.get(
                "current_type"
            )
        )

        new_type = normalize_type(
            analysis.get(
                "strong_expected_type"
            )
        )

        # -------------------------------------------------------------
        # Relations responsables
        # -------------------------------------------------------------

        related_anomalies = []

        for decision in group:

            related_anomalies.append({

                "decision_id":
                    decision.get(
                        "decision_id"
                    ),

                "relation_id":
                    decision.get(
                        "relation_id"
                    ),

                "relation_name":
                    decision.get(
                        "relation_name"
                    ),

                "role":
                    decision.get(
                        "role"
                    ),

                "current_type":
                    decision.get(
                        "entity_type"
                    ),

                "expected_type":
                    decision.get(
                        "expected_type"
                    ),

                "classification":
                    decision.get(
                        "classification"
                    ),

                "confidence":
                    decision.get(
                        "confidence"
                    ),

                "relation_resolution":
                    decision.get(
                        "relation_resolution"
                    ),

                "entity_resolution":
                    decision.get(
                        "entity_resolution"
                    ),
            })

        validated = {

            "validation_id":
                f"ONT_VAL_{index:05d}",

            "document":
                document,

            "entity_id":
                entity_id,

            "entity_text":
                first.get(
                    "entity_text"
                ),

            "entity_proof":
                first.get(
                    "entity_proof"
                ),

            "entity_page":
                first.get(
                    "entity_page"
                ),

            "current_type":
                current_type,

            "proposed_new_type":
                new_type,

            "analysis":
                analysis,

            "related_anomalies":
                related_anomalies,

            "final_status":
                validation[
                    "final_status"
                ],

            "final_action":
                validation[
                    "final_action"
                ],

            "validator_reason":
                validation[
                    "reason"
                ],
        }

        validated_groups.append(
            validated
        )

        status_counter[
            validated[
                "final_status"
            ]
        ] += 1

        action_counter[
            validated[
                "final_action"
            ]
        ] += 1

        if (
            validated[
                "final_action"
            ]
            == "RETYPE_ENTITY"
        ):

            type_changes[
                (
                    current_type,
                    new_type
                )
            ] += 1

    # =================================================================
    # NOMBRE D'ANOMALIES COUVERTES PAR SAFE ACCEPT
    # =================================================================

    anomalies_covered_by_safe_retype = 0

    strong_anomalies_covered = 0

    for group in validated_groups:

        if (
            group.get(
                "final_status"
            )
            != "SAFE_ACCEPT"
        ):
            continue

        related = group.get(
            "related_anomalies",
            []
        )

        anomalies_covered_by_safe_retype += len(
            related
        )

        strong_anomalies_covered += sum(
            1
            for x in related
            if x.get(
                "classification"
            )
            == "ENTITY_MISTYPING_STRONG"
        )

    # =================================================================
    # OUTPUT
    # =================================================================

    output = {

        "validator":
            "entity_validation_validator",

        "version":
            "V1_GROUP_LEVEL_SAFE_RETYPING",

        "mode":
            "NON_DESTRUCTIVE",

        "summary": {

            "decisions_received":
                len(decisions),

            "entity_groups_received":
                len(groups),

            "validated_entity_groups":
                len(validated_groups),

            "status_counts":
                dict(
                    status_counter
                ),

            "action_counts":
                dict(
                    action_counter
                ),

            "safe_retype_operations":
                action_counter.get(
                    "RETYPE_ENTITY",
                    0
                ),

            "anomalies_covered_by_safe_retype":
                anomalies_covered_by_safe_retype,

            "strong_anomalies_covered":
                strong_anomalies_covered,
        },

        "safe_type_changes": [

            {
                "from_type": old_type,
                "to_type": new_type,
                "count": count
            }

            for (
                old_type,
                new_type
            ), count
            in type_changes.most_common()
        ],

        "validated_groups":
            validated_groups,
    }

    dump_json(
        OUTPUT_FILE,
        output
    )

    # =================================================================
    # AFFICHAGE
    # =================================================================

    print(
        f"Décisions reçues                    : "
        f"{len(decisions)}"
    )

    print(
        f"Groupes d'entités reçus             : "
        f"{len(groups)}"
    )

    print(
        f"Groupes validés                      : "
        f"{len(validated_groups)}"
    )

    print()

    print(
        "STATUTS FINAUX"
    )

    print("-" * 120)

    for key, value in (
        status_counter.most_common()
    ):

        print(
            f"{key:<60}: {value}"
        )

    print()

    print(
        "ACTIONS FINALES"
    )

    print("-" * 120)

    for key, value in (
        action_counter.most_common()
    ):

        print(
            f"{key:<60}: {value}"
        )

    print()

    print(
        "RETYPAGES SAFE"
    )

    print("-" * 120)

    if type_changes:

        for (
            old_type,
            new_type
        ), count in (
            type_changes.most_common()
        ):

            transition = (
                f"{old_type} -> {new_type}"
            )

            print(
                f"{transition:<60}: {count}"
            )

    else:

        print(
            "Aucun retypage automatiquement validé."
        )

    print()

    print(
        "COUVERTURE"
    )

    print("-" * 120)

    print(
        f"Opérations logiques RETYPE_ENTITY   : "
        f"{action_counter.get('RETYPE_ENTITY', 0)}"
    )

    print(
        f"Anomalies couvertes par ces groupes : "
        f"{anomalies_covered_by_safe_retype}"
    )

    print(
        f"Anomalies STRONG couvertes          : "
        f"{strong_anomalies_covered}"
    )

    print()

    print(
        f"Sortie                              : "
        f"{OUTPUT_FILE}"
    )

    print()

    print(
        "Aucune donnée clinique n'a été modifiée."
    )


# =====================================================================
# ENTRY POINT
# =====================================================================

if __name__ == "__main__":
    main()