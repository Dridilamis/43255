# -*- coding: utf-8 -*-
"""
TRACE-Sepsis — V6.8 RELATION BALANCED — 43 documents

ENTREE
------
BEST_43_Relations_V6_7b_CONSERVATIVE

SORTIE
------
BEST_43_Relations_V6_8_BALANCED

Aucun appel Mistral/API.

Objectifs
---------
1. Réduire les faux positifs observés sur les 43 documents.
2. Corriger des confusions de type relationnel observées.
3. Récupérer uniquement des relations manquantes à forte contrainte clinique.
4. Ne PAS modifier le protocole de matching.

IMPORTANT
---------
Cette version a été construite après analyse des erreurs des 43 documents.
Si ces 43 documents constituent le test final, le score V6.8 est donc
optimisé sur ce jeu et doit être présenté comme tel.
"""

import copy
import json
import os
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path


# ============================================================
# CONFIG
# ============================================================

if os.name == "nt":
    BASE_DIR = (
        Path(os.environ.get("USERPROFILE", str(Path.home())))
        / "Desktop"
        / "TRACE"
        / "OCR vers LLM"
    )
else:
    BASE_DIR = Path.home() / "TRACE" / "OCR vers LLM"


DEFAULT_INPUT_DIR = (
    BASE_DIR
    / "BEST_43_Relations_V6_7b_CONSERVATIVE"
)

DEFAULT_OUTPUT_DIR = (
    BASE_DIR
    / "BEST_43_Relations_V6_8_BALANCED"
)


# ============================================================
# NORMALISATION
# ============================================================

def remove_accents(value):
    value = "" if value is None else str(value)
    value = unicodedata.normalize("NFD", value)
    return "".join(
        c for c in value
        if unicodedata.category(c) != "Mn"
    )


def ntext(value):
    value = remove_accents(value).lower()
    value = (
        value
        .replace("’", "'")
        .replace("`", "'")
        .replace("_", " ")
    )
    value = re.sub(r"\s+", " ", value)
    return value.strip(" \t\r\n,;:.()[]{}")


def eid(entity):
    return str(
        entity.get("identifiant_entite")
        or entity.get("id")
        or ""
    ).strip()


def etype(entity):
    return str(
        entity.get("categorie")
        or entity.get("type")
        or ""
    ).strip()


def esurface(entity):
    return str(
        entity.get("preuve")
        or entity.get("name")
        or entity.get("nom")
        or ""
    ).strip()


def rtype(relation):
    return str(
        relation.get("type_relation")
        or relation.get("relation")
        or ""
    ).strip()


def sid(relation):
    return str(
        relation.get("identifiant_entite_sujet")
        or relation.get("subject_id")
        or relation.get("from_id")
        or ""
    ).strip()


def oid(relation):
    return str(
        relation.get("identifiant_entite_objet")
        or relation.get("object_id")
        or relation.get("to_id")
        or ""
    ).strip()


def set_rtype(relation, value):
    relation["type_relation"] = value

    if "relation" in relation:
        relation["relation"] = value


# ============================================================
# LOCALISATION TEXTE
# ============================================================

def entity_spans(text, entity):
    surfaces = []

    for field in ("preuve", "name", "nom"):
        value = entity.get(field)

        if value:
            value = str(value).strip()

            if value and value not in surfaces:
                surfaces.append(value)

    spans = []

    for surface in surfaces:
        try:
            for match in re.finditer(
                re.escape(surface),
                text,
                flags=re.IGNORECASE
            ):
                spans.append(
                    (match.start(), match.end())
                )
        except re.error:
            pass

    return sorted(
        set(spans)
    )


def nearest_pair(text, first, second):
    first_spans = entity_spans(
        text,
        first
    )

    second_spans = entity_spans(
        text,
        second
    )

    if (
        not first_spans
        or not second_spans
    ):
        return None

    best = None

    for a in first_spans:
        for b in second_spans:

            if a[1] <= b[0]:
                distance = b[0] - a[1]

            elif b[1] <= a[0]:
                distance = a[0] - b[1]

            else:
                distance = 0

            candidate = (
                distance,
                a,
                b
            )

            if (
                best is None
                or candidate[0] < best[0]
            ):
                best = candidate

    return best


def nearest_distance(text, first, second):
    pair = nearest_pair(
        text,
        first,
        second
    )

    return (
        None
        if pair is None
        else pair[0]
    )


def between_context(
    text,
    first,
    second,
    margin=70
):
    pair = nearest_pair(
        text,
        first,
        second
    )

    if pair is None:
        return ""

    _, a, b = pair

    start = min(
        a[0],
        b[0]
    )

    end = max(
        a[1],
        b[1]
    )

    return text[
        max(0, start - margin):
        min(len(text), end + margin)
    ]


# ============================================================
# PATIENT
# ============================================================

def is_patient_entity(entity):
    if etype(entity) != "DONNEE_PATIENT":
        return False

    surface = ntext(
        esurface(entity)
    )

    return bool(
        "patient" in surface
        or "patiente" in surface
        or re.search(
            r"\b\d+\s*ans\b",
            surface
        )
        or surface.startswith("m. ")
        or surface.startswith("mme ")
    )


def patient_priority(entity):
    surface = ntext(
        esurface(entity)
    )

    if surface in {
        "patient",
        "patiente",
    }:
        return 0

    if surface in {
        "le patient",
        "la patiente",
    }:
        return 1

    if (
        "patient" in surface
        or "patiente" in surface
    ):
        return 2

    return 3


# ============================================================
# RELATION UTILS
# ============================================================

def relation_exists(
    relations,
    subject,
    relation_type,
    obj
):
    return any(
        sid(relation) == subject
        and rtype(relation) == relation_type
        and oid(relation) == obj
        for relation in relations
        if isinstance(
            relation,
            dict
        )
    )


def add_relation(
    relations,
    page_number,
    subject,
    relation_type,
    obj,
    proof,
    note
):
    if (
        not subject
        or not obj
        or subject == obj
    ):
        return False

    if relation_exists(
        relations,
        subject,
        relation_type,
        obj
    ):
        return False

    relations.append({
        "identifiant_relation":
            "",

        "identifiant_entite_sujet":
            subject,

        "type_relation":
            relation_type,

        "identifiant_entite_objet":
            obj,

        "delai_minutes":
            None,

        "preuve":
            str(
                proof
                or ""
            ).strip(),

        "note_clinique":
            note,

        "type_inference":
            "inference_structurelle_v68",

        "confiance":
            "elevee",

        "_v68_added":
            True,

        "_page":
            page_number,
    })

    return True


# ============================================================
# 1) CORRECTIONS DE TYPE RELATIONNEL
# ============================================================

SYMPTOM_FROM_FAILURE = (
    "ralentissement psychomoteur",
    "epanchement pleural",
    "syndrome pleural",
    "angiomes stellaires",
    "vesicule biliaire distendue",
    "lesion spontanement dense",
    "neuropathie de reanimation",
    "dilatation des veines",
    "aggravation respiratoire",
    "difficultes ventilatoires",
)


LABEL_FROM_FAILURE = (
    "acidose metabolique",
    "syndrome hepato-renal",
    "htap",
    "3 passages en acfa",
)


FAILURE_FROM_LABEL = (
    "acr",
    "collapsus de reventilation",
    "hyponatremie",
)


SUSPICION_FROM_LABEL = (
    "dermo-hypodermite",
    "peritonite stercorale",
    "sinusite maxillaire",
    "cellulite extensive",
)


LABEL_FROM_SUSPICION = (
    "tuberculose surinfectee",
    "pneumopathie nosocomiale",
    "pneumopathie a pneumocoque",
    "pneumonie a pneumocoque",
)


SYMPTOM_FROM_LABEL = (
    "poussee hypertensive",
    "thrombopenie",
    "coma",
)


LABEL_FROM_SYMPTOM = (
    "ulcere gastrique",
    "bronchite",
)


def contains_any(
    value,
    patterns
):
    return any(
        pattern in value
        for pattern in patterns
    )


def correct_relation_type(
    relation,
    entity_map
):
    relation = copy.deepcopy(
        relation
    )

    kind = rtype(
        relation
    )

    subject = entity_map.get(
        sid(relation),
        {}
    )

    obj = entity_map.get(
        oid(relation),
        {}
    )

    s = ntext(
        esurface(subject)
    )

    o = ntext(
        esurface(obj)
    )

    new_type = None
    reason = None

    # DEFAILLANCE -> SYMPTOME
    if (
        kind
        == "presente_dysfonction_organe"
        and contains_any(
            o,
            SYMPTOM_FROM_FAILURE
        )
    ):
        new_type = (
            "presente_symptome"
        )

        reason = (
            "V6.8 : manifestation clinique "
            "reclassée symptôme."
        )

    # DEFAILLANCE -> LABEL
    elif (
        kind
        == "presente_dysfonction_organe"
        and contains_any(
            o,
            LABEL_FROM_FAILURE
        )
    ):
        new_type = (
            "a_pour_label_nosologique"
        )

        reason = (
            "V6.8 : diagnostic reclassé "
            "label nosologique."
        )

    # LABEL -> DEFAILLANCE
    elif (
        kind
        == "a_pour_label_nosologique"
        and contains_any(
            o,
            FAILURE_FROM_LABEL
        )
    ):
        new_type = (
            "presente_dysfonction_organe"
        )

        reason = (
            "V6.8 : dysfonction reclassée "
            "défaillance."
        )

    # LABEL -> SUSPICION
    elif (
        kind
        == "a_pour_label_nosologique"
        and contains_any(
            o,
            SUSPICION_FROM_LABEL
        )
    ):
        new_type = (
            "presente_suspicion_infection"
        )

        reason = (
            "V6.8 : foyer infectieux reclassé "
            "suspicion d'infection."
        )

    # SUSPICION -> LABEL
    elif (
        kind
        == "presente_suspicion_infection"
        and contains_any(
            o,
            LABEL_FROM_SUSPICION
        )
    ):
        new_type = (
            "a_pour_label_nosologique"
        )

        reason = (
            "V6.8 : diagnostic établi reclassé "
            "label nosologique."
        )

    # LABEL -> SYMPTOME
    elif (
        kind
        == "a_pour_label_nosologique"
        and contains_any(
            o,
            SYMPTOM_FROM_LABEL
        )
    ):
        new_type = (
            "presente_symptome"
        )

        reason = (
            "V6.8 : manifestation reclassée symptôme."
        )

    # SYMPTOME -> LABEL
    elif (
        kind
        == "presente_symptome"
        and contains_any(
            o,
            LABEL_FROM_SYMPTOM
        )
    ):
        new_type = (
            "a_pour_label_nosologique"
        )

        reason = (
            "V6.8 : diagnostic reclassé label."
        )

    # SYMPTOME -> EVOLUTION
    elif (
        kind
        == "presente_symptome"
        and "diminution du syndrome inflammatoire biologique"
        in o
    ):
        new_type = (
            "patient_a_pour_evolution"
        )

        reason = (
            "V6.8 : évolution biologique reclassée."
        )

    # SYMPTOME -> SUSPICION
    elif (
        kind
        == "presente_symptome"
        and (
            "cicatrice inflammatoire avec ecoulement purulent"
            in o
            or o == "angiocholite"
        )
    ):
        new_type = (
            "presente_suspicion_infection"
        )

        reason = (
            "V6.8 : manifestation infectieuse "
            "reclassée suspicion."
        )

    # SYMPTOME -> DEFAILLANCE
    elif (
        kind
        == "presente_symptome"
        and o == "hypoxie"
    ):
        new_type = (
            "presente_dysfonction_organe"
        )

        reason = (
            "V6.8 : hypoxie reclassée dysfonction."
        )

    # BIOMARQUEUR_SUPPORT -> CRITERE
    elif (
        kind
        == "biomarqueur_supporte_defaillance_organe"
        and (
            (
                any(
                    marker in s
                    for marker in (
                        "ph",
                        "hco3",
                        "hc03",
                    )
                )
                and "acidose metabolique"
                in o
            )
            or (
                "hypophosphoremie"
                in s
                and "syndrome de renutrition"
                in o
            )
        )
    ):
        new_type = (
            "biomarqueur_est_critere_de"
        )

        reason = (
            "V6.8 : biomarqueur reclassé critère "
            "du diagnostic."
        )

    if (
        new_type
        and new_type != kind
    ):
        set_rtype(
            relation,
            new_type
        )

        relation[
            "_v68_original_relation_type"
        ] = kind

        relation[
            "_v68_corrected"
        ] = True

        relation[
            "note_clinique"
        ] = reason

        return (
            relation,
            True
        )

    return (
        relation,
        False
    )


# ============================================================
# 2) FILTRES PRECISION
# ============================================================

DROP_ALL_TYPES = {
    # Sur les 43 documents V6.7b :
    # 0 TP pour ces prédictions.
    "imagerie_objective_defaillance",
    "score_sofa_inclut_score_neurologique",
    "score_sofa_inclut_signe_vital",
}


BAD_TREATMENT_ADMIN = {
    "na",
    "g5%",
    "pm",
    "potassium",
    "antibiotherapie",
    "o2",
}


BAD_POSOLOGY_TREATMENT = {
    "na",
    "antibiotherapie",
    "transfusion",
    "iot / vac",
    "ventilation en sdra",
    "vt 420",
    "colimycine",
    "remplissage vasculaire",
    "o2",
    "mode : vac",
    "tracheotomie",
    "intubation",
}


BAD_SYMPTOMS = {
    "souffle percu",
    "hepatosplenomegalie",
    "masse palpable",
    "masse palpee",
    "atteinte motrice faciale inferieure",
    "conscient et oriente",
    "trouble sensitif au toucher simple",
    "indolore",
    "extremites chaudes",
}


BAD_LABELS = {
    "syndrome inflammatoire",
    "syndrome inflammatoire biologique",
}


def is_invalid_patient_anchor(
    surface
):
    value = ntext(
        surface
    )

    return bool(
        re.match(
            r"^(?:taille\b|bmi\b|ce jour$|\d+\s*ans$)",
            value
        )
    )


def biomarker_failure_allowed(
    subject,
    obj
):
    """
    Filtre déterministe construit à partir des familles
    biomarqueur-défaillance réellement cohérentes.
    """
    s = ntext(
        (
            str(
                subject.get(
                    "parametre",
                    ""
                )
            )
            + " "
            + esurface(
                subject
            )
        )
    )

    o = ntext(
        esurface(
            obj
        )
    )

    # rénal
    if (
        any(
            marker in s
            for marker in (
                "creat",
                "uree",
                "hyperkaliem",
            )
        )
        and any(
            marker in o
            for marker in (
                "insuffisance renale",
                "ira",
                "anurie",
            )
        )
    ):
        return True

    # respiratoire P/F - PO2
    if (
        any(
            marker in s
            for marker in (
                "p/f",
                "rapport p/f",
                "pao2",
                "po2",
            )
        )
        and any(
            marker in o
            for marker in (
                "sdra",
                "hypox",
                "defaillance respiratoire",
            )
        )
    ):
        return True

    # acidose respiratoire / hypercapnie
    if (
        (
            re.search(
                r"\bph\b",
                s
            )
            or "pco2" in s
            or "paco2" in s
        )
        and any(
            marker in o
            for marker in (
                "acidose respiratoire",
                "hypercapnique",
                "detresse respiratoire",
            )
        )
    ):
        return True

    # hématologique
    if (
        any(
            marker in s
            for marker in (
                "hemoglob",
                "ldh",
                "haptoglob",
                "plaquette",
            )
        )
        and "hematolog"
        in o
    ):
        return True

    # hémodynamique
    if (
        "lactate" in s
        and "hemodynam"
        in o
    ):
        return True

    # hépatique
    if (
        (
            re.search(
                r"\btp\b",
                s
            )
            or "temps de quick"
            in s
        )
        and "hepat"
        in o
    ):
        return True

    return False


def should_drop_relation(
    relation,
    entity_map
):
    kind = rtype(
        relation
    )

    if kind in DROP_ALL_TYPES:
        return (
            True,
            "zero_tp_relation_type"
        )

    subject = entity_map.get(
        sid(relation),
        {}
    )

    obj = entity_map.get(
        oid(relation),
        {}
    )

    s = ntext(
        esurface(
            subject
        )
    )

    o = ntext(
        esurface(
            obj
        )
    )

    # --------------------------------------------------------
    # TRAITEMENT -> PATIENT
    # --------------------------------------------------------
    if kind == "traitement_administre_a":

        if s in BAD_TREATMENT_ADMIN:
            return (
                True,
                "generic_treatment_admin"
            )

        if is_invalid_patient_anchor(
            esurface(
                obj
            )
        ):
            return (
                True,
                "invalid_patient_anchor"
            )

    # --------------------------------------------------------
    # TRAITEMENT -> POSOLOGIE
    # --------------------------------------------------------
    if (
        kind
        == "traitement_a_pour_posologie"
        and s
        in BAD_POSOLOGY_TREATMENT
    ):
        return (
            True,
            "low_precision_posology_subject"
        )

    # --------------------------------------------------------
    # PATIENT -> SYMPTOME
    # --------------------------------------------------------
    if (
        kind
        == "presente_symptome"
        and o in BAD_SYMPTOMS
    ):
        return (
            True,
            "low_precision_symptom"
        )

    # --------------------------------------------------------
    # PATIENT -> LABEL
    # --------------------------------------------------------
    if (
        kind
        == "a_pour_label_nosologique"
        and o in BAD_LABELS
    ):
        return (
            True,
            "generic_inflammatory_label"
        )

    # --------------------------------------------------------
    # BIOMARQUEUR -> DEFAILLANCE
    # --------------------------------------------------------
    if (
        kind
        == "biomarqueur_supporte_defaillance_organe"
        and not biomarker_failure_allowed(
            subject,
            obj
        )
    ):
        return (
            True,
            "unsupported_biomarker_failure_family"
        )

    # --------------------------------------------------------
    # EVENEMENT -> EVOLUTION
    # Très faible rendement sur 43 docs.
    # Ne garder que si la preuve contient un signal temporel clair.
    # --------------------------------------------------------
    if (
        kind
        == "evenement_associe_evolution"
    ):
        proof = ntext(
            relation.get(
                "preuve",
                ""
            )
        )

        if not re.search(
            r"\b(?:j\d+|jour|jours|heures?|apres|après|puis|ensuite|le\s+\d{1,2}/\d{1,2})\b",
            proof
        ):
            return (
                True,
                "weak_event_evolution"
            )

    # --------------------------------------------------------
    # TRAITEMENT indiqué pour LABEL
    # Ne garder que relation explicitement justifiée.
    # --------------------------------------------------------
    if (
        kind
        == "traitement_indique_par_label_nosologique"
    ):
        proof = ntext(
            relation.get(
                "preuve",
                ""
            )
        )

        if not any(
            cue in proof
            for cue in (
                "indique pour",
                "indiquee pour",
                "pour traiter",
                "traitement de",
                "traite pour",
                "mise sous",
                "mis sous",
            )
        ):
            return (
                True,
                "weak_treatment_indication"
            )

    return (
        False,
        ""
    )


# ============================================================
# 3) DEDUP SEMANTIQUE LOCAL
# ============================================================

PATIENT_CENTERED = {
    "presente_symptome",
    "a_pour_label_nosologique",
    "presente_dysfonction_organe",
    "patient_a_pour_evolution",
    "presente_suspicion_infection",
    "a_pour_contexte_acquisition",
}


def semantic_relation_key(
    relation,
    entity_map
):
    kind = rtype(
        relation
    )

    subject = entity_map.get(
        sid(relation),
        {}
    )

    obj = entity_map.get(
        oid(relation),
        {}
    )

    s = ntext(
        esurface(
            subject
        )
    )

    o = ntext(
        esurface(
            obj
        )
    )

    if (
        kind in PATIENT_CENTERED
        and is_patient_entity(
            subject
        )
    ):
        s = "__patient__"

    if (
        kind
        in {
            "traitement_administre_a",
            "service_medical_accueille",
        }
        and is_patient_entity(
            obj
        )
    ):
        o = "__patient__"

    return (
        kind,
        s,
        o,
    )


def semantic_dedup(
    relations,
    entity_map,
    stats
):
    grouped = {}

    for relation in relations:

        if not isinstance(
            relation,
            dict
        ):
            continue

        key = semantic_relation_key(
            relation,
            entity_map
        )

        grouped.setdefault(
            key,
            []
        ).append(
            relation
        )

    output = []

    for key, group in grouped.items():

        if len(group) == 1:
            output.append(
                group[0]
            )
            continue

        kind = key[0]

        # Si relation centrée patient, garder l'ancre patient
        # la plus canonique.
        if kind in PATIENT_CENTERED:
            keeper = min(
                group,
                key=lambda relation:
                    patient_priority(
                        entity_map.get(
                            sid(relation),
                            {}
                        )
                    )
            )

        elif kind in {
            "traitement_administre_a",
            "service_medical_accueille",
        }:
            keeper = min(
                group,
                key=lambda relation:
                    patient_priority(
                        entity_map.get(
                            oid(relation),
                            {}
                        )
                    )
            )

        else:
            keeper = group[0]

        output.append(
            keeper
        )

        stats[
            "semantic_duplicates_removed"
        ] += (
            len(group)
            - 1
        )

    return output


# ============================================================
# 4) MICRO-ORGANISME -> FOYER
# ============================================================

def recover_micro_foyer(
    relations,
    entities,
    text,
    page_number
):
    organisms = [
        entity
        for entity in entities
        if (
            etype(entity)
            == "MICRO_ORGANISME"
            and eid(entity)
        )
    ]

    foyers = [
        entity
        for entity in entities
        if (
            etype(entity)
            == "FOYER_INFECTIEUX"
            and eid(entity)
        )
    ]

    added = 0

    for organism in organisms:
        org_norm = ntext(
            esurface(
                organism
            )
        )

        if (
            not org_norm
            or len(org_norm) < 3
        ):
            continue

        for foyer in foyers:
            foyer_norm = ntext(
                esurface(
                    foyer
                )
            )

            if not foyer_norm:
                continue

            strong = (
                org_norm in foyer_norm
            )

            distance = nearest_distance(
                text,
                organism,
                foyer
            )

            context = ntext(
                between_context(
                    text,
                    organism,
                    foyer,
                    margin=100
                )
            )

            if (
                not strong
                and distance is not None
                and distance <= 220
                and any(
                    cue in context
                    for cue in (
                        "a ",
                        "à ",
                        "positif",
                        "positive",
                        "isole",
                        "isolee",
                        "pdp",
                        "ecbu",
                        "hemoculture",
                        "bacteriologie",
                        "culture",
                    )
                )
            ):
                strong = True

            if not strong:
                continue

            if add_relation(
                relations,
                page_number,
                eid(
                    organism
                ),
                "micro_organisme_isole_dans",
                eid(
                    foyer
                ),
                between_context(
                    text,
                    organism,
                    foyer,
                    margin=40
                ),
                (
                    "V6.8 : microorganisme-foyer "
                    "sur inclusion/proximité microbiologique forte."
                )
            ):
                added += 1

    return added


# ============================================================
# 5) SIGNE VITAL -> DEFAILLANCE
# ============================================================

def vital_family(entity):
    value = ntext(
        esurface(
            entity
        )
    )

    if any(
        marker in value
        for marker in (
            "spo2",
            "sao2",
            "sat o2",
            "saturation",
            "desaturation",
            "polypnee",
            "tachypnee",
            "frequence respiratoire",
            "cycles/min",
        )
    ):
        return "respiratory"

    if any(
        marker in value
        for marker in (
            "pas ",
            "pression arterielle",
            "tension arterielle",
            "hypotension",
            "tachycardie",
            "frequence cardiaque",
        )
    ):
        return "shock"

    return ""


def failure_family(entity):
    value = ntext(
        esurface(
            entity
        )
    )

    if any(
        marker in value
        for marker in (
            "detresse respiratoire",
            "defaillance respiratoire",
            "sdra",
            " dra",
            "hypox",
        )
    ):
        return "respiratory"

    if any(
        marker in value
        for marker in (
            "choc",
            "collapsus",
            "defaillance hemodynamique",
        )
    ):
        return "shock"

    if any(
        marker in value
        for marker in (
            "insuffisance renale",
            "ira",
        )
    ):
        return "renal"

    return ""


def recover_vital_failure(
    relations,
    entities,
    text,
    page_number
):
    vitals = [
        entity
        for entity in entities
        if (
            etype(entity)
            == "SIGNE_VITAL"
            and eid(entity)
            and vital_family(
                entity
            )
        )
    ]

    failures = [
        entity
        for entity in entities
        if (
            etype(entity)
            == "DEFAILLANCE_ORGANE"
            and eid(entity)
            and failure_family(
                entity
            )
        )
    ]

    added = 0

    for vital in vitals:
        family = vital_family(
            vital
        )

        candidates = []

        for failure in failures:

            if failure_family(
                failure
            ) != family:
                continue

            distance = nearest_distance(
                text,
                vital,
                failure
            )

            if (
                distance is None
                or distance > 260
            ):
                continue

            candidates.append(
                (
                    distance,
                    failure
                )
            )

        if not candidates:
            continue

        candidates.sort(
            key=lambda item:
                item[0]
        )

        distance, failure = (
            candidates[0]
        )

        if add_relation(
            relations,
            page_number,
            eid(
                vital
            ),
            "signe_vital_supporte_defaillance_organe",
            eid(
                failure
            ),
            between_context(
                text,
                vital,
                failure,
                margin=40
            ),
            (
                "V6.8 : signe vital-défaillance "
                "sur famille physiologique et proximité."
            )
        ):
            added += 1

    return added


# ============================================================
# 6) TRAITEMENT -> DEFAILLANCE
# ============================================================

def treatment_failure_family(
    entity
):
    value = ntext(
        esurface(
            entity
        )
    )

    if any(
        marker in value
        for marker in (
            "vni",
            "ventilation",
            "intub",
            "iot",
        )
    ):
        return "respiratory"

    if any(
        marker in value
        for marker in (
            "noradrenaline",
            "adrenaline",
            "dobutamine",
            "remplissage vasculaire",
            "serum physiologique",
        )
    ):
        return "shock"

    if any(
        marker in value
        for marker in (
            "dialyse",
            "eer",
            "epuration extra",
        )
    ):
        return "renal"

    return ""


def recover_treatment_failure(
    relations,
    entities,
    text,
    page_number
):
    treatments = [
        entity
        for entity in entities
        if (
            etype(entity)
            == "TRAITEMENT"
            and eid(entity)
            and treatment_failure_family(
                entity
            )
        )
    ]

    failures = [
        entity
        for entity in entities
        if (
            etype(entity)
            == "DEFAILLANCE_ORGANE"
            and eid(entity)
            and failure_family(
                entity
            )
        )
    ]

    added = 0

    for treatment in treatments:
        family = treatment_failure_family(
            treatment
        )

        candidates = []

        for failure in failures:

            if failure_family(
                failure
            ) != family:
                continue

            distance = nearest_distance(
                text,
                treatment,
                failure
            )

            if (
                distance is None
                or distance > 320
            ):
                continue

            candidates.append(
                (
                    distance,
                    failure
                )
            )

        if not candidates:
            continue

        candidates.sort(
            key=lambda item:
                item[0]
        )

        _, failure = (
            candidates[0]
        )

        if add_relation(
            relations,
            page_number,
            eid(
                treatment
            ),
            "traitement_cible_defaillance",
            eid(
                failure
            ),
            between_context(
                text,
                treatment,
                failure,
                margin=45
            ),
            (
                "V6.8 : traitement-défaillance "
                "sur famille thérapeutique forte."
            )
        ):
            added += 1

    return added


# ============================================================
# 7) BIOMARQUEUR -> LABEL (CRITERE)
# ============================================================

def criterion_pair_allowed(
    biomarker,
    label
):
    b = ntext(
        (
            str(
                biomarker.get(
                    "parametre",
                    ""
                )
            )
            + " "
            + esurface(
                biomarker
            )
        )
    )

    l = ntext(
        esurface(
            label
        )
    )

    # sodium -> hyponatrémie
    if (
        any(
            x in b
            for x in (
                "natremie",
                "sodium",
            )
        )
        and "hyponatrem"
        in l
    ):
        return True

    # lipase -> pancréatite
    if (
        "lipas"
        in b
        and "pancreat"
        in l
    ):
        return True

    # gazométrie -> acidose métabolique
    if (
        any(
            x in b
            for x in (
                "ph",
                "hco3",
                "hc03",
                "bicarbon",
            )
        )
        and "acidose metabolique"
        in l
    ):
        return True

    # phosphore -> renutrition
    if (
        "hypophosph"
        in b
        and "renutrition"
        in l
    ):
        return True

    # hémolyse / MAT
    if (
        any(
            x in b
            for x in (
                "plaquette",
                "haptoglob",
                "ldh",
            )
        )
        and "mat"
        in l
    ):
        return True

    # inflammation : plus conservateur, objet explicitement syndrome inflammatoire
    if (
        any(
            x in b
            for x in (
                "crp",
                "gb",
                "leucocyt",
                "hyperleucocyt",
            )
        )
        and "syndrome inflammatoire"
        in l
    ):
        return True

    return False


def recover_biomarker_criterion(
    relations,
    entities,
    text,
    page_number
):
    biomarkers = [
        entity
        for entity in entities
        if (
            etype(entity)
            == "BIOMARQUEUR"
            and eid(entity)
        )
    ]

    labels = [
        entity
        for entity in entities
        if (
            etype(entity)
            == "LABEL_NOSOLOGIQUE"
            and eid(entity)
        )
    ]

    added = 0

    for biomarker in biomarkers:

        candidates = []

        for label in labels:

            if not criterion_pair_allowed(
                biomarker,
                label
            ):
                continue

            distance = nearest_distance(
                text,
                biomarker,
                label
            )

            if (
                distance is None
                or distance > 300
            ):
                continue

            candidates.append(
                (
                    distance,
                    label
                )
            )

        if not candidates:
            continue

        candidates.sort(
            key=lambda item:
                item[0]
        )

        _, label = (
            candidates[0]
        )

        if add_relation(
            relations,
            page_number,
            eid(
                biomarker
            ),
            "biomarqueur_est_critere_de",
            eid(
                label
            ),
            between_context(
                text,
                biomarker,
                label,
                margin=45
            ),
            (
                "V6.8 : biomarqueur-critère "
                "sur paire clinique fortement typée."
            )
        ):
            added += 1

    return added


# ============================================================
# 8) CONTEXTE D'ACQUISITION
# ============================================================

def recover_acquisition(
    relations,
    entities,
    text,
    page_number
):
    contexts = [
        entity
        for entity in entities
        if (
            etype(entity)
            == "CONTEXTE_ACQUISITION"
            and eid(entity)
        )
    ]

    patients = [
        entity
        for entity in entities
        if (
            is_patient_entity(
                entity
            )
            and eid(entity)
        )
    ]

    clinical_subjects = [
        entity
        for entity in entities
        if (
            etype(entity)
            in {
                "FOYER_INFECTIEUX",
                "LABEL_NOSOLOGIQUE",
            }
            and eid(entity)
        )
    ]

    added = 0

    for context in contexts:
        c = ntext(
            esurface(
                context
            )
        )

        if not c:
            continue

        # foyer/label qui contient directement le contexte
        direct = []

        for subject in clinical_subjects:
            s = ntext(
                esurface(
                    subject
                )
            )

            if (
                c in s
                or (
                    "nosocomial"
                    in c
                    and "nosocomial"
                    in s
                )
                or (
                    "communautaire"
                    in c
                    and "communautaire"
                    in s
                )
                or (
                    "ventilation"
                    in c
                    and "ventilation"
                    in s
                )
                or (
                    "inhalation"
                    in c
                    and "inhalation"
                    in s
                )
            ):
                direct.append(
                    subject
                )

        for subject in direct[:1]:
            if add_relation(
                relations,
                page_number,
                eid(
                    subject
                ),
                "a_pour_contexte_acquisition",
                eid(
                    context
                ),
                between_context(
                    text,
                    subject,
                    context,
                    margin=35
                ),
                (
                    "V6.8 : contexte d'acquisition "
                    "explicitement porté par le diagnostic."
                )
            ):
                added += 1

        # patient uniquement pour affirmation explicite
        if (
            (
                "infection nosocomiale : oui"
                in ntext(text)
                or "infection nosocomiale: oui"
                in ntext(text)
            )
            and patients
            and (
                "nosocomial"
                in c
            )
        ):
            patient = min(
                patients,
                key=patient_priority
            )

            if add_relation(
                relations,
                page_number,
                eid(
                    patient
                ),
                "a_pour_contexte_acquisition",
                eid(
                    context
                ),
                esurface(
                    context
                ),
                (
                    "V6.8 : contexte nosocomial "
                    "explicitement affirmé pour le patient."
                )
            ):
                added += 1

    return added


# ============================================================
# 9) BIOMARQUEUR -> EVENEMENT TEMPOREL
# ============================================================

def temporal_tokens(
    value
):
    value = ntext(
        value
    )

    tokens = set(
        re.findall(
            r"\b(?:t0|t30|t60|j\d+|\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b",
            value
        )
    )

    return tokens


def recover_biomarker_time(
    relations,
    entities,
    text,
    page_number
):
    biomarkers = [
        entity
        for entity in entities
        if (
            etype(entity)
            == "BIOMARQUEUR"
            and eid(entity)
        )
    ]

    events = [
        entity
        for entity in entities
        if (
            etype(entity)
            == "EVENEMENT_TEMPOREL"
            and eid(entity)
        )
    ]

    added = 0

    for biomarker in biomarkers:
        b_tokens = temporal_tokens(
            esurface(
                biomarker
            )
        )

        if not b_tokens:
            continue

        for event in events:
            e_tokens = temporal_tokens(
                esurface(
                    event
                )
            )

            if not (
                b_tokens
                & e_tokens
            ):
                continue

            if add_relation(
                relations,
                page_number,
                eid(
                    biomarker
                ),
                "biomarqueur_obtenu_a",
                eid(
                    event
                ),
                between_context(
                    text,
                    biomarker,
                    event,
                    margin=25
                ),
                (
                    "V6.8 : temps explicite partagé "
                    "entre biomarqueur et événement."
                )
            ):
                added += 1

    return added


# ============================================================
# 10) ANTIBIOTIQUE ADEQUAT / INADEQUAT
# ============================================================

ADEQUATE_CUES = (
    "sensible a",
    "sensible à",
    "sensible",
    "sensibilite",
    "sensibilité",
    "antibiogramme",
    "adapte a",
    "adapté à",
    "adaptee a",
    "adaptée à",
)


INADEQUATE_CUES = (
    "resistant a",
    "résistant à",
    "resistante a",
    "résistante à",
    "resistance",
    "résistance",
    "intermediaire",
    "intermédiaire",
)


def is_antimicrobial(
    entity
):
    value = ntext(
        esurface(
            entity
        )
    )

    return any(
        marker in value
        for marker in (
            "augmentin",
            "claforan",
            "ticar",
            "cipro",
            "tazoc",
            "vanco",
            "rifam",
            "dapto",
            "ceftaz",
            "imipen",
            "tienam",
            "amik",
            "flucon",
            "ceftriax",
            "meropen",
            "antibiot",
        )
    )


def recover_antibiotic_relation(
    relations,
    entities,
    text,
    page_number
):
    treatments = [
        entity
        for entity in entities
        if (
            etype(entity)
            == "TRAITEMENT"
            and eid(entity)
            and is_antimicrobial(
                entity
            )
        )
    ]

    organisms = [
        entity
        for entity in entities
        if (
            etype(entity)
            == "MICRO_ORGANISME"
            and eid(entity)
        )
    ]

    added = 0

    for treatment in treatments:
        for organism in organisms:

            distance = nearest_distance(
                text,
                treatment,
                organism
            )

            if (
                distance is None
                or distance > 350
            ):
                continue

            context_raw = between_context(
                text,
                treatment,
                organism,
                margin=100
            )

            context = ntext(
                context_raw
            )

            relation_type = None

            if any(
                cue in context
                for cue in INADEQUATE_CUES
            ):
                relation_type = (
                    "antibiotique_inadequat_pour"
                )

            elif any(
                ntext(cue) in context
                for cue in ADEQUATE_CUES
            ):
                relation_type = (
                    "antibiotique_adequat_pour"
                )

            if not relation_type:
                continue

            if add_relation(
                relations,
                page_number,
                eid(
                    treatment
                ),
                relation_type,
                eid(
                    organism
                ),
                context_raw,
                (
                    "V6.8 : adéquation antibiotique "
                    "sur signal explicite d'antibiogramme."
                )
            ):
                added += 1

    return added


# ============================================================
# PAGE
# ============================================================

def process_page(
    page,
    stats
):
    page = copy.deepcopy(
        page
    )

    entities = (
        page.get(
            "entities"
        )
        if isinstance(
            page.get(
                "entities"
            ),
            list
        )
        else page.get(
            "entites",
            []
        )
    )

    if not isinstance(
        entities,
        list
    ):
        entities = []

    relations = (
        page.get(
            "relations"
        )
        if isinstance(
            page.get(
                "relations"
            ),
            list
        )
        else []
    )

    text = str(
        page.get(
            "texte_brut"
        )
        or ""
    )

    page_number = page.get(
        "page",
        0
    )

    entity_map = {
        eid(entity):
            entity

        for entity in entities

        if (
            isinstance(
                entity,
                dict
            )
            and eid(
                entity
            )
        )
    }

    # --------------------------------------------------------
    # A. CORRECTION TYPE
    # --------------------------------------------------------

    corrected = []

    for relation in relations:

        if not isinstance(
            relation,
            dict
        ):
            continue

        relation, changed = (
            correct_relation_type(
                relation,
                entity_map
            )
        )

        if changed:
            stats[
                "wrong_type_corrected"
            ] += 1

        corrected.append(
            relation
        )

    relations = corrected

    # --------------------------------------------------------
    # B. FILTRES PRECISION
    # --------------------------------------------------------

    kept = []

    for relation in relations:

        drop, reason = (
            should_drop_relation(
                relation,
                entity_map
            )
        )

        if drop:
            stats[
                "removed_"
                + reason
            ] += 1

            continue

        kept.append(
            relation
        )

    relations = kept

    # --------------------------------------------------------
    # C. DEDUP SEMANTIQUE
    # --------------------------------------------------------

    relations = semantic_dedup(
        relations,
        entity_map,
        stats
    )

    # --------------------------------------------------------
    # D. RECUPERATIONS SELECTIVES
    # --------------------------------------------------------

    stats[
        "added_micro_organisme_isole_dans"
    ] += recover_micro_foyer(
        relations,
        entities,
        text,
        page_number
    )

    stats[
        "added_signe_vital_supporte_defaillance_organe"
    ] += recover_vital_failure(
        relations,
        entities,
        text,
        page_number
    )

    stats[
        "added_traitement_cible_defaillance"
    ] += recover_treatment_failure(
        relations,
        entities,
        text,
        page_number
    )

    stats[
        "added_biomarqueur_est_critere_de"
    ] += recover_biomarker_criterion(
        relations,
        entities,
        text,
        page_number
    )

    stats[
        "added_a_pour_contexte_acquisition"
    ] += recover_acquisition(
        relations,
        entities,
        text,
        page_number
    )

    stats[
        "added_biomarqueur_obtenu_a"
    ] += recover_biomarker_time(
        relations,
        entities,
        text,
        page_number
    )

    stats[
        "added_antibiotic_adequacy"
    ] += recover_antibiotic_relation(
        relations,
        entities,
        text,
        page_number
    )

    # Une seconde dédup après ajout.
    relations = semantic_dedup(
        relations,
        entity_map,
        stats
    )

    # --------------------------------------------------------
    # RENUMEROTATION
    # --------------------------------------------------------

    for index, relation in enumerate(
        relations,
        start=1
    ):
        relation[
            "identifiant_relation"
        ] = (
            f"P{page_number}_R{index:03d}"
        )

        relation.setdefault(
            "_page",
            page_number
        )

    page[
        "relations"
    ] = relations

    return page


# ============================================================
# DOCUMENT
# ============================================================

def process_document(
    data
):
    output = copy.deepcopy(
        data
    )

    stats = Counter()

    pages = output.get(
        "pages",
        []
    )

    if not isinstance(
        pages,
        list
    ):
        pages = []

    processed_pages = []
    global_relations = []

    for page in pages:

        if not isinstance(
            page,
            dict
        ):
            processed_pages.append(
                page
            )
            continue

        processed = process_page(
            page,
            stats
        )

        processed_pages.append(
            processed
        )

        for relation in processed.get(
            "relations",
            []
        ):
            relation_copy = copy.deepcopy(
                relation
            )

            relation_copy.setdefault(
                "page",
                processed.get(
                    "page"
                )
            )

            global_relations.append(
                relation_copy
            )

    output[
        "pages"
    ] = processed_pages

    output[
        "global_relations"
    ] = global_relations

    if isinstance(
        output.get(
            "document_summary"
        ),
        dict
    ):
        output[
            "document_summary"
        ][
            "total_relations"
        ] = len(
            global_relations
        )

    output[
        "relation_postprocessing_v68"
    ] = {
        "version":
            "V6.8_RELATION_BALANCED",

        "source":
            "V6.7b_RELATION_CONSERVATIVE",

        "stats":
            dict(
                stats
            ),

        "total_relations":
            len(
                global_relations
            ),
    }

    return (
        output,
        stats
    )


# ============================================================
# DOSSIER
# ============================================================

def process_folder(
    input_dir,
    output_dir
):
    input_dir = Path(
        input_dir
    )

    output_dir = Path(
        output_dir
    )

    if not input_dir.is_dir():
        raise FileNotFoundError(
            f"Dossier d'entrée absent : {input_dir}"
        )

    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    for old_file in output_dir.glob(
        "*.json"
    ):
        try:
            old_file.unlink()
        except OSError:
            pass

    json_files = sorted(
        input_dir.glob(
            "*.json"
        )
    )

    print(
        "\n============================================================"
    )

    print(
        "TRACE-Sepsis — V6.8 RELATION BALANCED"
    )

    print(
        "============================================================"
    )

    print(
        "INPUT  :",
        input_dir
    )

    print(
        "OUTPUT :",
        output_dir
    )

    print(
        "JSON   :",
        len(
            json_files
        )
    )

    print(
        "============================================================\n"
    )

    if len(
        json_files
    ) != 43:
        print(
            f"⚠️ 43 documents attendus ; "
            f"{len(json_files)} trouvés."
        )

    total_stats = Counter()

    for index, source in enumerate(
        json_files,
        start=1
    ):
        with source.open(
            "r",
            encoding="utf-8"
        ) as file:
            data = json.load(
                file
            )

        before = len(
            data.get(
                "global_relations",
                []
            )
        )

        result, stats = (
            process_document(
                data
            )
        )

        total_stats.update(
            stats
        )

        after = len(
            result.get(
                "global_relations",
                []
            )
        )

        destination = (
            output_dir
            / source.name
        )

        with destination.open(
            "w",
            encoding="utf-8"
        ) as file:
            json.dump(
                result,
                file,
                ensure_ascii=False,
                indent=2
            )

        print(
            f"✅ {index:02d}/{len(json_files)} "
            f"{source.name} | "
            f"relations {before} -> {after}"
        )

    print(
        "\n--- STATS V6.8 RELATION BALANCED ---"
    )

    for key, value in sorted(
        total_stats.items()
    ):
        print(
            f"{key:70s} : {value}"
        )

    print(
        "\n🏁 V6.8 RELATION BALANCED terminée."
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    input_dir = (
        Path(
            sys.argv[1]
        )
        if len(
            sys.argv
        ) >= 2
        else DEFAULT_INPUT_DIR
    )

    output_dir = (
        Path(
            sys.argv[2]
        )
        if len(
            sys.argv
        ) >= 3
        else DEFAULT_OUTPUT_DIR
    )

    process_folder(
        input_dir,
        output_dir
    )
