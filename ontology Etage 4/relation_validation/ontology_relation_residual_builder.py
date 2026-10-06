# -*- coding: utf-8 -*-

"""
TRACE / SGCE - ONTOLOGY RELATION RESIDUAL BUILDER V1

OBJECTIF
--------
Construire les candidats correspondant aux violations ontologiques
relationnelles restantes APRES le retypage SAFE des entités.

Le builder analyse uniquement :

    INVALID_RELATION_SOURCE_TYPE
    INVALID_RELATION_TARGET_TYPE

Il ne traite PAS :

    DUPLICATE_ENTITY_CONTENT

Pour chaque anomalie, il reconstruit :

- le document ;
- la relation ;
- l'entité source ;
- l'entité cible ;
- leurs types actuels ;
- le domain/range attendu ;
- le rôle fautif : SOURCE ou TARGET ;
- le texte des endpoints ;
- les informations cliniques disponibles ;
- les occurrences physiques ;
- les anomalies multiples associées à la même relation.

AUCUNE DONNEE CLINIQUE N'EST MODIFIEE.
"""

# GENERICITY PATCH: TRACE_BASE_DIR can be supplied through the environment.

import os
import json
import csv

from pathlib import Path
from collections import Counter, defaultdict


# =====================================================================
# CONFIGURATION
# =====================================================================

ROOT = Path(__file__).resolve().parent
STAGE4_DIR = ROOT.parent
REDUCTION_DIR = STAGE4_DIR.parent
PROJECT_DIR = REDUCTION_DIR.parent

# Entrée clinique : sortie officielle de Entity Validation
CLINICAL_DIR = (
    STAGE4_DIR
    / "entity_validation"
    / "entity_validation_safe_corrected"
)

# Audit recalculé sur cette sortie
AUDIT_DIR = ROOT / "audit_after_entity_validation"
AUDIT_REPORT = AUDIT_DIR / "final_ontology_audit_report.json"
AUDIT_ANOMALIES_CSV = AUDIT_DIR / "final_ontology_anomalies.csv"

GUIDELINE_FILE = PROJECT_DIR / "Guideline_TRACE_Sepsis_v1.6.json"

QUEUE_DIR = ROOT / "queues"
OUTPUT_FILE = QUEUE_DIR / "ontology_relation_residual_candidates.json"
CSV_OUTPUT = QUEUE_DIR / "ontology_relation_residual_candidates.csv"
QUEUE_DIR.mkdir(parents=True, exist_ok=True)


# =====================================================================
# CONSTANTES
# =====================================================================

TARGET_ANOMALIES = {
    "INVALID_RELATION_SOURCE_TYPE",
    "INVALID_RELATION_TARGET_TYPE",
}

ENTITY_ID_KEYS = (
    "identifiant_entite",
    "entity_id",
    "id_entite",
)

RELATION_ID_KEYS = (
    "identifiant_relation",
    "relation_id",
    "id_relation",
)

TYPE_KEYS = (
    "type",          # type ontologique final prioritaire
    "type_entite",
    "entity_type",
    "categorie",
    "label",
)

TEXT_KEYS = (
    "texte",
    "text",
    "entity_text",
    "mention",
    "valeur",
    "value",
)

RELATION_NAME_KEYS = (
    "type_relation",
    "relation",
    "relation_name",
    "nom_relation",
)

SOURCE_ID_KEYS = (
    "identifiant_entite_sujet",
    "source_id",
    "subject_id",
    "sujet_id",
)

TARGET_ID_KEYS = (
    "identifiant_entite_objet",
    "target_id",
    "object_id",
    "objet_id",
)


# =====================================================================
# JSON
# =====================================================================

def load_json(path):

    return json.loads(
        Path(path).read_text(
            encoding="utf-8"
        )
    )


def dump_json(path, obj):

    Path(path).parent.mkdir(
        parents=True,
        exist_ok=True
    )

    Path(path).write_text(
        json.dumps(
            obj,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


# =====================================================================
# NORMALISATION
# =====================================================================

def clean(value):

    if value is None:
        return ""

    return str(value).strip()


def norm(value):

    return clean(value).casefold()


def upper(value):

    return clean(value).upper()


def first_value(obj, keys):

    if not isinstance(obj, dict):
        return None

    for key in keys:

        if key in obj:

            value = obj.get(key)

            if value is not None:
                return value

    return None


# =====================================================================
# ENTITES
# =====================================================================

def entity_id(entity):

    return clean(
        first_value(
            entity,
            ENTITY_ID_KEYS
        )
    )


def entity_type(entity):

    return upper(
        first_value(
            entity,
            TYPE_KEYS
        )
    )


def entity_text(entity):

    value = first_value(
        entity,
        TEXT_KEYS
    )

    if value is not None:
        return clean(value)

    # Certains JSON TRACE peuvent stocker l'information
    # dans des champs plus spécialisés.

    for key in (
        "nom",
        "libelle",
        "parametre",
        "description",
        "concept",
    ):

        if key in entity:

            value = entity.get(key)

            if isinstance(value, str):
                return clean(value)

    return ""


# =====================================================================
# RELATIONS
# =====================================================================

def relation_id(relation):

    return clean(
        first_value(
            relation,
            RELATION_ID_KEYS
        )
    )


def relation_name(relation):

    return clean(
        first_value(
            relation,
            RELATION_NAME_KEYS
        )
    )


def relation_source_id(relation):

    return clean(
        first_value(
            relation,
            SOURCE_ID_KEYS
        )
    )


def relation_target_id(relation):

    return clean(
        first_value(
            relation,
            TARGET_ID_KEYS
        )
    )


# =====================================================================
# PARCOURS RECURSIF
# =====================================================================

def walk_objects(obj, path="$"):

    if isinstance(obj, dict):

        yield obj, path

        for key, value in obj.items():

            yield from walk_objects(
                value,
                f"{path}.{key}"
            )

    elif isinstance(obj, list):

        for index, value in enumerate(obj):

            yield from walk_objects(
                value,
                f"{path}[{index}]"
            )


# =====================================================================
# INDEX DOCUMENT
# =====================================================================

def build_document_index(document):

    """
    Indexe les entités et relations du document.

    Plusieurs occurrences physiques d'une même entité/relation
    peuvent exister.
    """

    entities = defaultdict(list)
    relations = defaultdict(list)

    for obj, path in walk_objects(document):

        # -------------------------------------------------------------
        # Entité
        # -------------------------------------------------------------

        eid = entity_id(obj)

        if eid:

            # Éviter qu'une relation contenant des références
            # vers les entités soit interprétée comme une entité.

            if "identifiant_entite_sujet" not in obj \
                    and "identifiant_entite_objet" not in obj:

                entities[eid].append({
                    "object": obj,
                    "path": path
                })

        # -------------------------------------------------------------
        # Relation
        # -------------------------------------------------------------

        rid = relation_id(obj)

        if rid:

            source = relation_source_id(obj)
            target = relation_target_id(obj)

            if source or target:

                relations[rid].append({
                    "object": obj,
                    "path": path
                })

    return entities, relations


# =====================================================================
# REPRESENTATION CANONIQUE D'UNE ENTITE
# =====================================================================

def choose_entity_occurrence(occurrences):

    """
    Choisit la représentation la plus informative.

    Aucune donnée n'est modifiée.
    """

    if not occurrences:
        return None

    def score(item):

        obj = item["object"]

        s = 0

        if entity_type(obj):
            s += 10

        if entity_text(obj):
            s += 5

        # Plus de champs = souvent représentation clinique principale
        s += min(
            len(obj),
            20
        )

        return s

    return max(
        occurrences,
        key=score
    )


# =====================================================================
# REPRESENTATION CANONIQUE RELATION
# =====================================================================

def choose_relation_occurrence(occurrences):

    if not occurrences:
        return None

    def score(item):

        obj = item["object"]

        s = 0

        if relation_name(obj):
            s += 10

        if relation_source_id(obj):
            s += 5

        if relation_target_id(obj):
            s += 5

        s += min(
            len(obj),
            20
        )

        return s

    return max(
        occurrences,
        key=score
    )


# =====================================================================
# LECTURE CSV AUDIT
# =====================================================================

def load_audit_anomalies():

    if not AUDIT_ANOMALIES_CSV.exists():

        raise FileNotFoundError(
            f"CSV anomalies introuvable : "
            f"{AUDIT_ANOMALIES_CSV}"
        )

    rows = []

    # utf-8-sig gère également un éventuel BOM
    with AUDIT_ANOMALIES_CSV.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        reader = csv.DictReader(f)

        for row in reader:

            # Trouver le champ portant le type d'anomalie
            anomaly_type = ""

            for key in (
                "anomaly_type",
                "type_anomalie",
                "type",
                "anomaly",
            ):

                if key in row and row[key]:

                    anomaly_type = clean(
                        row[key]
                    )

                    break

            if anomaly_type not in TARGET_ANOMALIES:
                continue

            row["_anomaly_type"] = anomaly_type

            rows.append(row)

    return rows


# =====================================================================
# CHAMPS AUDIT
# =====================================================================

def audit_value(row, *possible_keys):

    for key in possible_keys:

        if key in row:

            value = row.get(key)

            if value is not None \
                    and clean(value):

                return clean(value)

    return ""


# =====================================================================
# EXTRACTION DES SIGNATURES DU GUIDELINE
# =====================================================================

def extract_relation_signatures(obj):

    """
    Recherche récursivement les définitions de relations du guideline.

    Produit :
        relation_name ->
            {
                source_types: set(),
                target_types: set()
            }

    Cette fonction reste volontairement générique afin de supporter
    plusieurs structures de guideline.
    """

    signatures = defaultdict(
        lambda: {
            "source_types": set(),
            "target_types": set()
        }
    )

    for item, _ in walk_objects(obj):

        if not isinstance(item, dict):
            continue

        rname = clean(
            first_value(
                item,
                (
                    "type_relation",
                    "relation",
                    "nom_relation",
                    "relation_name",
                )
            )
        )

        if not rname:
            continue

        source = first_value(
            item,
            (
                "source_type",
                "type_source",
                "domain",
                "domaine",
                "source",
            )
        )

        target = first_value(
            item,
            (
                "target_type",
                "type_cible",
                "range",
                "cible",
                "target",
            )
        )

        # -------------------------------------------------------------
        # Source
        # -------------------------------------------------------------

        source_values = []

        if isinstance(source, list):

            source_values = source

        elif isinstance(source, str):

            source_values = [source]

        # -------------------------------------------------------------
        # Target
        # -------------------------------------------------------------

        target_values = []

        if isinstance(target, list):

            target_values = target

        elif isinstance(target, str):

            target_values = [target]

        for value in source_values:

            value = upper(value)

            if value:
                signatures[
                    rname
                ][
                    "source_types"
                ].add(value)

        for value in target_values:

            value = upper(value)

            if value:
                signatures[
                    rname
                ][
                    "target_types"
                ].add(value)

    return signatures


# =====================================================================
# HYPOTHESE INITIALE
# =====================================================================

def initial_hypothesis(
    anomaly_type,
    source_type,
    target_type,
    expected_source_types,
    expected_target_types
):

    """
    IMPORTANT :
    Le builder ne décide PAS quelle correction appliquer.

    Il indique seulement le type de problème à analyser.
    """

    if anomaly_type == "INVALID_RELATION_SOURCE_TYPE":

        if (
            expected_source_types
            and source_type not in expected_source_types
        ):

            return "SOURCE_DOMAIN_CONFLICT"

    if anomaly_type == "INVALID_RELATION_TARGET_TYPE":

        if (
            expected_target_types
            and target_type not in expected_target_types
        ):

            return "TARGET_RANGE_CONFLICT"

    return "RELATION_ONTOLOGY_CONFLICT"


# =====================================================================
# MAIN
# =====================================================================

def main():

    print("=" * 120)

    print(
        "TRACE / SGCE - ONTOLOGY RELATION RESIDUAL "
        "BUILDER V1 - POST RETYPING RELATION AUDIT"
    )

    print("=" * 120)

    # =================================================================
    # Vérifications
    # =================================================================

    if not CLINICAL_DIR.exists():

        raise FileNotFoundError(
            f"Dossier clinique introuvable : "
            f"{CLINICAL_DIR}"
        )

    if not GUIDELINE_FILE.exists():

        raise FileNotFoundError(
            f"Guideline introuvable : "
            f"{GUIDELINE_FILE}"
        )

    # =================================================================
    # Audit
    # =================================================================

    anomalies = load_audit_anomalies()

    # =================================================================
    # Guideline
    # =================================================================

    guideline = load_json(
        GUIDELINE_FILE
    )

    signatures = extract_relation_signatures(
        guideline
    )

    # =================================================================
    # Cache documents
    # =================================================================

    document_cache = {}

    index_cache = {}

    missing_documents = set()

    # =================================================================
    # Compteurs
    # =================================================================

    anomaly_counter = Counter()

    role_counter = Counter()

    relation_counter = Counter()

    hypothesis_counter = Counter()

    source_type_counter = Counter()

    target_type_counter = Counter()

    expected_type_counter = Counter()

    relation_resolution_counter = Counter()

    source_resolution_counter = Counter()

    target_resolution_counter = Counter()

    # =================================================================
    # Candidats
    # =================================================================

    candidates = []

    # =================================================================
    # Parcours anomalies
    # =================================================================

    for index, anomaly in enumerate(
        anomalies,
        start=1
    ):

        anomaly_type = anomaly[
            "_anomaly_type"
        ]

        # -------------------------------------------------------------
        # Document
        # -------------------------------------------------------------

        document_name = audit_value(
            anomaly,
            "document",
            "document_name",
            "filename",
            "file",
            "fichier"
        )

        # -------------------------------------------------------------
        # Relation
        # -------------------------------------------------------------

        rid = audit_value(
            anomaly,
            "relation_id",
            "identifiant_relation",
            "id_relation"
        )

        rname_audit = audit_value(
            anomaly,
            "relation",
            "relation_name",
            "type_relation",
            "nom_relation"
        )

        # -------------------------------------------------------------
        # Types attendus éventuellement déjà présents dans audit
        # -------------------------------------------------------------

        expected_type_from_audit = audit_value(
            anomaly,
            "expected_type",
            "type_attendu",
            "expected"
        )

        # -------------------------------------------------------------
        # Charger document
        # -------------------------------------------------------------

        if document_name not in document_cache:

            path = (
                CLINICAL_DIR
                / document_name
            )

            if not path.exists():

                missing_documents.add(
                    document_name
                )

                document_cache[
                    document_name
                ] = None

                index_cache[
                    document_name
                ] = (
                    {},
                    {}
                )

            else:

                document = load_json(
                    path
                )

                document_cache[
                    document_name
                ] = document

                index_cache[
                    document_name
                ] = build_document_index(
                    document
                )

        document = document_cache.get(
            document_name
        )

        entities_index, relations_index = (
            index_cache.get(
                document_name,
                ({}, {})
            )
        )

        # -------------------------------------------------------------
        # Résolution relation
        # -------------------------------------------------------------

        relation_occurrences = (
            relations_index.get(
                rid,
                []
            )
            if rid
            else []
        )

        relation_choice = (
            choose_relation_occurrence(
                relation_occurrences
            )
        )

        if relation_choice:

            relation_obj = (
                relation_choice["object"]
            )

            relation_resolution = (
                "ID_EXACT"
            )

        else:

            relation_obj = {}

            relation_resolution = (
                "UNRESOLVED"
            )

        relation_resolution_counter[
            relation_resolution
        ] += 1

        # -------------------------------------------------------------
        # Nom relation
        # -------------------------------------------------------------

        rname = (
            relation_name(
                relation_obj
            )
            or rname_audit
        )

        # -------------------------------------------------------------
        # IDs endpoints
        # -------------------------------------------------------------

        source_id = relation_source_id(
            relation_obj
        )

        target_id = relation_target_id(
            relation_obj
        )

        # fallback audit
        if not source_id:

            source_id = audit_value(
                anomaly,
                "source_id",
                "identifiant_entite_sujet",
                "subject_id"
            )

        if not target_id:

            target_id = audit_value(
                anomaly,
                "target_id",
                "identifiant_entite_objet",
                "object_id"
            )

        # -------------------------------------------------------------
        # Source
        # -------------------------------------------------------------

        source_occurrences = (
            entities_index.get(
                source_id,
                []
            )
        )

        source_choice = (
            choose_entity_occurrence(
                source_occurrences
            )
        )

        if source_choice:

            source_obj = (
                source_choice["object"]
            )

            source_resolution = (
                "ID_EXACT"
            )

        else:

            source_obj = {}

            source_resolution = (
                "UNRESOLVED"
            )

        source_resolution_counter[
            source_resolution
        ] += 1

        # -------------------------------------------------------------
        # Target
        # -------------------------------------------------------------

        target_occurrences = (
            entities_index.get(
                target_id,
                []
            )
        )

        target_choice = (
            choose_entity_occurrence(
                target_occurrences
            )
        )

        if target_choice:

            target_obj = (
                target_choice["object"]
            )

            target_resolution = (
                "ID_EXACT"
            )

        else:

            target_obj = {}

            target_resolution = (
                "UNRESOLVED"
            )

        target_resolution_counter[
            target_resolution
        ] += 1

        # -------------------------------------------------------------
        # Infos endpoints
        # -------------------------------------------------------------

        source_type = entity_type(
            source_obj
        )

        target_type = entity_type(
            target_obj
        )

        source_text = entity_text(
            source_obj
        )

        target_text = entity_text(
            target_obj
        )

        # -------------------------------------------------------------
        # Domain / Range guideline
        # -------------------------------------------------------------

        signature = signatures.get(
            rname,
            {
                "source_types": set(),
                "target_types": set()
            }
        )

        expected_source_types = sorted(
            signature[
                "source_types"
            ]
        )

        expected_target_types = sorted(
            signature[
                "target_types"
            ]
        )

        # -------------------------------------------------------------
        # Rôle fautif
        # -------------------------------------------------------------

        if anomaly_type == (
            "INVALID_RELATION_SOURCE_TYPE"
        ):

            affected_role = "SOURCE"

            expected_types = (
                expected_source_types
            )

        else:

            affected_role = "TARGET"

            expected_types = (
                expected_target_types
            )

        # Si l'audit fournit déjà le type attendu,
        # on le conserve également.
        if (
            expected_type_from_audit
            and expected_type_from_audit
            not in expected_types
        ):

            expected_types = (
                expected_types
                + [
                    upper(
                        expected_type_from_audit
                    )
                ]
            )

        expected_types = sorted(
            set(expected_types)
        )

        # -------------------------------------------------------------
        # Hypothèse
        # -------------------------------------------------------------

        hypothesis = initial_hypothesis(
            anomaly_type,
            source_type,
            target_type,
            set(expected_source_types),
            set(expected_target_types)
        )

        # -------------------------------------------------------------
        # Candidate
        # -------------------------------------------------------------

        candidate = {

            "candidate_id":
                f"ORR_{index:05d}",

            "document":
                document_name,

            "anomaly_type":
                anomaly_type,

            "affected_role":
                affected_role,

            # ---------------------------------------------------------
            # Relation
            # ---------------------------------------------------------

            "relation_id":
                rid,

            "relation_name":
                rname,

            "relation_resolution":
                relation_resolution,

            "relation_occurrences":
                len(
                    relation_occurrences
                ),

            "relation_path":
                (
                    relation_choice["path"]
                    if relation_choice
                    else None
                ),

            # ---------------------------------------------------------
            # Source
            # ---------------------------------------------------------

            "source_id":
                source_id,

            "source_text":
                source_text,

            "source_type":
                source_type,

            "source_resolution":
                source_resolution,

            "source_occurrences":
                len(
                    source_occurrences
                ),

            "source_path":
                (
                    source_choice["path"]
                    if source_choice
                    else None
                ),

            # ---------------------------------------------------------
            # Target
            # ---------------------------------------------------------

            "target_id":
                target_id,

            "target_text":
                target_text,

            "target_type":
                target_type,

            "target_resolution":
                target_resolution,

            "target_occurrences":
                len(
                    target_occurrences
                ),

            "target_path":
                (
                    target_choice["path"]
                    if target_choice
                    else None
                ),

            # ---------------------------------------------------------
            # Ontologie
            # ---------------------------------------------------------

            "expected_source_types":
                expected_source_types,

            "expected_target_types":
                expected_target_types,

            "expected_types_for_affected_role":
                expected_types,

            # ---------------------------------------------------------
            # Analyse initiale
            # ---------------------------------------------------------

            "initial_hypothesis":
                hypothesis,

            # ---------------------------------------------------------
            # Données brutes audit
            # ---------------------------------------------------------

            "audit_row":
                {
                    k: v
                    for k, v in anomaly.items()
                    if not k.startswith("_")
                }
        }

        candidates.append(
            candidate
        )

        # -------------------------------------------------------------
        # Stats
        # -------------------------------------------------------------

        anomaly_counter[
            anomaly_type
        ] += 1

        role_counter[
            affected_role
        ] += 1

        relation_counter[
            rname or "<UNKNOWN>"
        ] += 1

        hypothesis_counter[
            hypothesis
        ] += 1

        source_type_counter[
            source_type or "<UNKNOWN>"
        ] += 1

        target_type_counter[
            target_type or "<UNKNOWN>"
        ] += 1

        for t in expected_types:

            expected_type_counter[
                t
            ] += 1

    # =================================================================
    # GROUPER PAR RELATION LOGIQUE
    # =================================================================

    groups = defaultdict(list)

    for candidate in candidates:

        key = (
            candidate["document"],
            candidate["relation_id"]
        )

        groups[key].append(
            candidate
        )

    grouped_relations = []

    for (
        document,
        rid
    ), items in groups.items():

        first = items[0]

        grouped_relations.append({

            "document":
                document,

            "relation_id":
                rid,

            "relation_name":
                first.get(
                    "relation_name"
                ),

            "source_id":
                first.get(
                    "source_id"
                ),

            "source_text":
                first.get(
                    "source_text"
                ),

            "source_type":
                first.get(
                    "source_type"
                ),

            "target_id":
                first.get(
                    "target_id"
                ),

            "target_text":
                first.get(
                    "target_text"
                ),

            "target_type":
                first.get(
                    "target_type"
                ),

            "expected_source_types":
                first.get(
                    "expected_source_types"
                ),

            "expected_target_types":
                first.get(
                    "expected_target_types"
                ),

            "anomaly_types":
                sorted(
                    set(
                        x["anomaly_type"]
                        for x in items
                    )
                ),

            "affected_roles":
                sorted(
                    set(
                        x["affected_role"]
                        for x in items
                    )
                ),

            "number_of_anomalies":
                len(items),

            "candidate_ids":
                [
                    x["candidate_id"]
                    for x in items
                ],
        })

    # =================================================================
    # SORTIE JSON
    # =================================================================

    result = {

        "builder":
            "ontology_relation_residual_builder",

        "version":
            "V1_POST_SAFE_RETYPING",

        "input_clinical_directory":
            str(CLINICAL_DIR),

        "input_audit":
            str(AUDIT_ANOMALIES_CSV),

        "guideline":
            str(GUIDELINE_FILE),

        "summary": {

            "anomalies_received":
                len(anomalies),

            "candidates_built":
                len(candidates),

            "logical_relation_groups":
                len(grouped_relations),

            "documents_missing":
                len(missing_documents),

            "anomaly_type_counts":
                dict(
                    anomaly_counter
                ),

            "affected_role_counts":
                dict(
                    role_counter
                ),

            "initial_hypothesis_counts":
                dict(
                    hypothesis_counter
                ),

            "relation_resolution_counts":
                dict(
                    relation_resolution_counter
                ),

            "source_resolution_counts":
                dict(
                    source_resolution_counter
                ),

            "target_resolution_counts":
                dict(
                    target_resolution_counter
                ),
        },

        "missing_documents":
            sorted(
                missing_documents
            ),

        "relation_counts":
            dict(
                relation_counter.most_common()
            ),

        "source_type_counts":
            dict(
                source_type_counter.most_common()
            ),

        "target_type_counts":
            dict(
                target_type_counter.most_common()
            ),

        "expected_type_counts":
            dict(
                expected_type_counter.most_common()
            ),

        "relation_groups":
            grouped_relations,

        "candidates":
            candidates,
    }

    dump_json(
        OUTPUT_FILE,
        result
    )

    # =================================================================
    # CSV
    # =================================================================

    csv_fields = [
        "candidate_id",
        "document",
        "anomaly_type",
        "affected_role",
        "relation_id",
        "relation_name",
        "source_id",
        "source_text",
        "source_type",
        "target_id",
        "target_text",
        "target_type",
        "expected_source_types",
        "expected_target_types",
        "expected_types_for_affected_role",
        "initial_hypothesis",
        "relation_resolution",
        "source_resolution",
        "target_resolution",
    ]

    with CSV_OUTPUT.open(
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=csv_fields
        )

        writer.writeheader()

        for candidate in candidates:

            row = {}

            for field in csv_fields:

                value = candidate.get(
                    field
                )

                if isinstance(
                    value,
                    list
                ):

                    value = " | ".join(
                        str(x)
                        for x in value
                    )

                row[field] = value

            writer.writerow(
                row
            )

    # =================================================================
    # TERMINAL
    # =================================================================

    print(
        f"Anomalies relationnelles reçues    : "
        f"{len(anomalies)}"
    )

    print(
        f"Candidats construits               : "
        f"{len(candidates)}"
    )

    print(
        f"Relations logiques concernées       : "
        f"{len(grouped_relations)}"
    )

    print(
        f"Documents manquants                : "
        f"{len(missing_documents)}"
    )

    print()

    print("ANOMALIES")
    print("-" * 120)

    for key, value in (
        anomaly_counter.most_common()
    ):

        print(
            f"{key:<60}: {value}"
        )

    print()

    print("ROLES AFFECTES")
    print("-" * 120)

    for key, value in (
        role_counter.most_common()
    ):

        print(
            f"{key:<60}: {value}"
        )

    print()

    print("HYPOTHESES INITIALES")
    print("-" * 120)

    for key, value in (
        hypothesis_counter.most_common()
    ):

        print(
            f"{key:<60}: {value}"
        )

    print()

    print("RESOLUTION DES RELATIONS")
    print("-" * 120)

    for key, value in (
        relation_resolution_counter.most_common()
    ):

        print(
            f"{key:<60}: {value}"
        )

    print()

    print("RESOLUTION DES SOURCES")
    print("-" * 120)

    for key, value in (
        source_resolution_counter.most_common()
    ):

        print(
            f"{key:<60}: {value}"
        )

    print()

    print("RESOLUTION DES CIBLES")
    print("-" * 120)

    for key, value in (
        target_resolution_counter.most_common()
    ):

        print(
            f"{key:<60}: {value}"
        )

    print()

    print("RELATIONS LES PLUS CONCERNEES")
    print("-" * 120)

    for key, value in (
        relation_counter.most_common(20)
    ):

        print(
            f"{key:<60}: {value}"
        )

    print()

    print(
        f"Sortie JSON                         : "
        f"{OUTPUT_FILE}"
    )

    print(
        f"Sortie CSV                          : "
        f"{CSV_OUTPUT}"
    )

    print()

    print(
        "Aucune donnée clinique n'a été modifiée."
    )


if __name__ == "__main__":
    main()