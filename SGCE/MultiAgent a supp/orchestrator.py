# -*- coding: utf-8 -*-
"""
orchestrator_v2.py
==================

TRACE / SGCE â€” Orchestrateur multi-agent V2
Second recours uniquement.

PRINCIPE
--------
Le symbolique tranche d'abord.
Un cas est envoyÃ© Ã  un agent seulement si le mÃ©canisme symbolique a dÃ©tectÃ©
un pattern mais ne peut pas choisir une correction unique et sÃ»re.

STRUCTURE ATTENDUE
------------------
Reduction_hallucinations/
â”‚
â”œâ”€â”€ PatternA/
â”‚   â”œâ”€â”€ PatternA1/
â”‚   â”œâ”€â”€ PatternA2/
â”‚   â”œâ”€â”€ ...
â”‚   â””â”€â”€ PatternA6/
â”‚
â”œâ”€â”€ PatternB/
â”‚   â”œâ”€â”€ PatternB1/
â”‚   â”œâ”€â”€ PatternB2/
â”‚   â””â”€â”€ pattern_b_post_validation/
â”‚
â”œâ”€â”€ PatternC/
â”‚   â”œâ”€â”€ pattern_c_validation/
â”‚   â””â”€â”€ ...
â”‚
â”œâ”€â”€ PatternD/
â”‚   â”œâ”€â”€ pattern_d_validation/
â”‚   â””â”€â”€ ...
â”‚
â””â”€â”€ MultiAgent/
    â”œâ”€â”€ orchestrator_v2.py
    â”œâ”€â”€ schemas.py
    â”œâ”€â”€ queues/
    â””â”€â”€ outputs/

IMPORTANT
---------
- Pattern D n'est PAS routÃ© vers les agents A/B/C ici.
  Il correspond Ã  la validation ontologique/structurelle.
- Les agents concernent principalement les ambiguÃ¯tÃ©s SGCE A/B/C.
- Patient/RÃ©fÃ©rence est une ROUTE SECONDAIRE de certains cas C,
  pas un nouveau cas unique.
- Aucun JSON clinique n'est modifiÃ©.
"""

import json
from collections import Counter, defaultdict
from pathlib import Path


# ============================================================
# 1. PATHS
# ============================================================

BASE_DIR = Path(
    r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM"
    r"\Reduction_hallucinations"
)

MULTIAGENT_DIR = BASE_DIR / "MultiAgent"
QUEUE_DIR = MULTIAGENT_DIR / "queues"

QUEUE_A = QUEUE_DIR / "agent_a_queue.json"
QUEUE_B = QUEUE_DIR / "agent_b_queue.json"
QUEUE_C = QUEUE_DIR / "agent_c_queue.json"
QUEUE_PATIENT_REFERENCE = QUEUE_DIR / "patient_reference_queue.json"

REPORT_PATH = QUEUE_DIR / "orchestration_report.json"


# ============================================================
# 2. STATUSES TO ROUTE
# ============================================================

PATTERN_A_AMBIGUOUS_STATUSES = {
    "AMBIGUOUS",
    "REVIEW",
}

PATTERN_B_AMBIGUOUS_STATUSES = {
    "AMBIGUOUS",
    "UNRESOLVABLE_REFERENCE",
    "UNVERIFIABLE_NO_SOURCE_TEXT",
    "REVIEW",
}

PATTERN_C_AMBIGUOUS_STATUSES = {
    "AMBIGUOUS",
    "POTENTIAL_REIFIED_RELATION",
    "REVIEW",
}


# ============================================================
# 3. HELPERS
# ============================================================

def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def safe_load(path):
    try:
        return load_json(path), None
    except Exception as exc:
        return None, str(exc)


def candidate_id(candidate, fallback_prefix, index):
    return (
        candidate.get("candidate_id")
        or candidate.get("id")
        or f"{fallback_prefix}_{index:06d}"
    )


def candidate_status(candidate):
    return (
        candidate.get("validation_status")
        or candidate.get("status")
        or candidate.get("decision_status")
        or ""
    )


def extract_candidates(report):
    """
    Supporte les diffÃ©rents noms utilisÃ©s par nos scripts.
    """
    for key in (
        "validated_candidates",
        "candidates",
        "results",
        "items",
    ):
        value = report.get(key)
        if isinstance(value, list):
            return value

    return []


def make_task(
    *,
    pattern,
    subpattern,
    source_report,
    candidate,
    index,
    route_to,
    routing_reason,
    allowed_actions,
):
    cid = candidate_id(
        candidate,
        f"{pattern}{subpattern or ''}",
        index,
    )

    return {
        "task_id": f"{route_to}::{cid}",
        "candidate_id": cid,
        "document": candidate.get("document"),

        "pattern": pattern,
        "subpattern": subpattern,

        "original_status": candidate_status(candidate),

        "route_to": route_to,
        "routing_reason": routing_reason,

        "source_report": str(source_report),

        "allowed_actions": allowed_actions,

        # On conserve intÃ©gralement la sortie symbolique.
        "symbolic_candidate": candidate,

        # Enrichi plus tard par un context builder / agent.
        "document_context": None,
        "local_entities": [],
        "local_relations": [],

        "second_recourse_only": True,
    }


# ============================================================
# 4. DISCOVER PATTERN A VALIDATION REPORTS
# ============================================================

def discover_pattern_a_reports():
    """
    Recherche automatiquement les validations A1...A6.

    Exemples acceptÃ©s :
    PatternA/PatternA1/pattern_a1_validation/pattern_a1_validation_report.json
    PatternA/PatternA2/pattern_a2_validation/pattern_a2_validation_report.json
    ...
    """

    root = BASE_DIR / "PatternA"

    if not root.exists():
        return []

    reports = []

    for path in sorted(
        root.rglob("pattern_a*_validation_report.json")
    ):
        if path.is_file():
            reports.append(path)

    return reports


# ============================================================
# 5. PATTERN A
# ============================================================

def collect_pattern_a():
    reports = discover_pattern_a_reports()

    queue = []
    metadata = []

    seen_candidate_keys = set()

    for report_path in reports:
        report, error = safe_load(report_path)

        if error:
            metadata.append({
                "report": str(report_path),
                "error": error,
                "selected": 0,
            })
            continue

        candidates = extract_candidates(report)
        selected = 0

        # PatternA1, PatternA2, ...
        subpattern = report_path.parts[-3] if len(report_path.parts) >= 3 else ""

        for i, candidate in enumerate(candidates, start=1):
            status = candidate_status(candidate)

            if status not in PATTERN_A_AMBIGUOUS_STATUSES:
                continue

            cid = candidate_id(
                candidate,
                "A",
                i,
            )

            dedup_key = (
                candidate.get("document"),
                cid,
                str(report_path),
            )

            if dedup_key in seen_candidate_keys:
                continue

            seen_candidate_keys.add(dedup_key)

            queue.append(
                make_task(
                    pattern="A",
                    subpattern=subpattern,
                    source_report=report_path,
                    candidate=candidate,
                    index=i,
                    route_to="agent_pattern_a",
                    routing_reason=(
                        "Pattern A dÃ©tectÃ©, mais aucune action SPLIT/KEEP "
                        "unique et sÃ»re n'a Ã©tÃ© dÃ©terminÃ©e symboliquement."
                    ),
                    allowed_actions=[
                        "SPLIT",
                        "KEEP",
                        "REVIEW",
                    ],
                )
            )

            selected += 1

        metadata.append({
            "report": str(report_path),
            "candidate_count": len(candidates),
            "selected": selected,
        })

    return queue, {
        "reports_found": len(reports),
        "reports": metadata,
        "selected_total": len(queue),
    }


# ============================================================
# 6. PATTERN B
# ============================================================

def discover_pattern_b_reports():
    root = BASE_DIR / "PatternB"

    if not root.exists():
        return []

    reports = []

    for path in sorted(
        root.rglob("pattern_b*_validation_report.json")
    ):
        if path.is_file():
            reports.append(path)

    return reports


def collect_pattern_b():
    reports = discover_pattern_b_reports()

    queue = []
    metadata = []

    seen = set()

    for report_path in reports:
        report, error = safe_load(report_path)

        if error:
            metadata.append({
                "report": str(report_path),
                "error": error,
                "selected": 0,
            })
            continue

        candidates = extract_candidates(report)

        folder_text = str(report_path).lower()

        if "patternb1" in folder_text or "pattern_b1" in folder_text:
            subpattern = "B1"
        elif "patternb2" in folder_text or "pattern_b2" in folder_text:
            subpattern = "B2"
        else:
            subpattern = "B"

        selected = 0

        for i, candidate in enumerate(candidates, start=1):
            status = candidate_status(candidate)

            if status not in PATTERN_B_AMBIGUOUS_STATUSES:
                continue

            cid = candidate_id(
                candidate,
                subpattern,
                i,
            )

            key = (
                candidate.get("document"),
                cid,
                subpattern,
            )

            if key in seen:
                continue

            seen.add(key)

            queue.append(
                make_task(
                    pattern="B",
                    subpattern=subpattern,
                    source_report=report_path,
                    candidate=candidate,
                    index=i,
                    route_to="agent_pattern_b",
                    routing_reason=(
                        "Une entitÃ© / rÃ©fÃ©rence / endpoint manque ou reste "
                        "ambigu. La crÃ©ation ou le relink ne peuvent pas Ãªtre "
                        "dÃ©duits de faÃ§on sÃ»re par une rÃ¨gle fixe."
                    ),
                    allowed_actions=[
                        "RELINK",
                        "CREATE_FROM_EXPLICIT_EVIDENCE",
                        "REMOVE_RELATION",
                        "KEEP",
                        "REVIEW",
                    ],
                )
            )

            selected += 1

        metadata.append({
            "report": str(report_path),
            "subpattern": subpattern,
            "candidate_count": len(candidates),
            "selected": selected,
        })

    return queue, {
        "reports_found": len(reports),
        "reports": metadata,
        "selected_total": len(queue),
    }


# ============================================================
# 7. PATTERN C
# ============================================================

def discover_pattern_c_report():
    candidates = [
        BASE_DIR
        / "PatternC"
        / "pattern_c_validation"
        / "pattern_c_validation_report.json",
    ]

    for p in candidates:
        if p.exists():
            return p

    # Fallback de dÃ©couverte uniquement dans PatternC.
    root = BASE_DIR / "PatternC"

    if root.exists():
        found = sorted(
            root.rglob("pattern_c_validation_report.json")
        )

        if found:
            return found[0]

    return None


def collect_pattern_c():
    report_path = discover_pattern_c_report()

    if report_path is None:
        return [], {
            "available": False,
            "selected_total": 0,
            "reason": "pattern_c_validation_report.json introuvable",
        }

    report, error = safe_load(report_path)

    if error:
        return [], {
            "available": False,
            "selected_total": 0,
            "report": str(report_path),
            "error": error,
        }

    candidates = extract_candidates(report)

    queue = []

    for i, candidate in enumerate(candidates, start=1):
        status = candidate_status(candidate)

        if status not in PATTERN_C_AMBIGUOUS_STATUSES:
            continue

        queue.append(
            make_task(
                pattern="C",
                subpattern="C",
                source_report=report_path,
                candidate=candidate,
                index=i,
                route_to="agent_pattern_c",
                routing_reason=(
                    "Structure relationnelle/rÃ©ifiÃ©e dÃ©tectÃ©e, mais la "
                    "dÃ©cision MERGE / KEEP / REVIEW dÃ©pend du contexte."
                ),
                allowed_actions=[
                    "MERGE",
                    "KEEP",
                    "REVIEW",
                    "REMOVE_RELATION",
                ],
            )
        )

    return queue, {
        "available": True,
        "report": str(report_path),
        "candidate_count": len(candidates),
        "selected_total": len(queue),
    }


# ============================================================
# 8. PATIENT / REFERENCE SECONDARY ROUTING
# ============================================================

REFERENCE_KEYWORDS = {
    "seuil",
    "seuils",
    "barÃ¨me",
    "bareme",
    "rÃ©fÃ©rence",
    "reference",
    "interprÃ©tation",
    "interpretation",
    "norme",
    "classification",
    "critÃ¨re",
    "critere",
    "score",
    "cutoff",
    "cut-off",
    "valeur normale",
    "valeurs normales",
}


def needs_patient_reference_review(task):
    """
    DÃ©termine si un cas C nÃ©cessite en plus une discrimination
    Patient / RÃ©fÃ©rence.

    Ce n'est PAS un nouveau candidat unique.
    """

    blob = json.dumps(
        task.get("symbolic_candidate", {}),
        ensure_ascii=False,
    ).lower()

    return any(
        keyword in blob
        for keyword in REFERENCE_KEYWORDS
    )


def build_patient_reference_queue(c_queue):
    queue = []

    for task in c_queue:
        if not needs_patient_reference_review(task):
            continue

        secondary = dict(task)

        secondary["task_id"] = (
            f"agent_patient_reference::{task['candidate_id']}"
        )

        secondary["route_to"] = "agent_patient_reference"

        secondary["routing_reason"] = (
            "ContrÃ´le contextuel secondaire : dÃ©terminer si le contenu "
            "concerne rÃ©ellement le patient ou reprÃ©sente une information "
            "gÃ©nÃ©rique/de rÃ©fÃ©rence."
        )

        secondary["allowed_actions"] = [
            "KEEP_AS_PATIENT",
            "EXCLUDE_AS_REFERENCE",
            "REVIEW",
        ]

        secondary["secondary_route"] = True
        secondary["parent_agent"] = "agent_pattern_c"

        queue.append(secondary)

    return queue


# ============================================================
# 9. OPTIONAL PATTERN D CONTEXT
# ============================================================

def pattern_d_context():
    """
    Pattern D = validation ontologique/structurelle.
    On ne le route pas vers A/B/C.

    On expose seulement ses statistiques dans le rapport,
    pour garder la traÃ§abilitÃ© du pipeline.
    """

    report_path = (
        BASE_DIR
        / "PatternD"
        / "pattern_d_post_validation"
        / "pattern_d_post_validation_report.json"
    )

    if not report_path.exists():
        return {
            "available": False,
        }

    report, error = safe_load(report_path)

    if error:
        return {
            "available": False,
            "error": error,
            "report": str(report_path),
        }

    return {
        "available": True,
        "report": str(report_path),
        "summary": report.get("summary", {}),
    }


# ============================================================
# 10. WRITE QUEUES
# ============================================================

def write_json(path, data):
    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


# ============================================================
# 11. MAIN
# ============================================================

def main():
    QUEUE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Symbolic unresolved cases
    # --------------------------------------------------------

    a_queue, a_meta = collect_pattern_a()
    b_queue, b_meta = collect_pattern_b()
    c_queue, c_meta = collect_pattern_c()

    # --------------------------------------------------------
    # Secondary context route
    # --------------------------------------------------------

    patient_reference_queue = (
        build_patient_reference_queue(
            c_queue
        )
    )

    # --------------------------------------------------------
    # Write queues
    # --------------------------------------------------------

    write_json(
        QUEUE_A,
        a_queue,
    )

    write_json(
        QUEUE_B,
        b_queue,
    )

    write_json(
        QUEUE_C,
        c_queue,
    )

    write_json(
        QUEUE_PATIENT_REFERENCE,
        patient_reference_queue,
    )

    # --------------------------------------------------------
    # Unique candidates
    # --------------------------------------------------------

    primary_tasks = (
        a_queue
        + b_queue
        + c_queue
    )

    unique_keys = {
        (
            task.get("pattern"),
            task.get("subpattern"),
            task.get("document"),
            task.get("candidate_id"),
        )
        for task in primary_tasks
    }

    unique_case_count = len(
        unique_keys
    )

    secondary_route_count = len(
        patient_reference_queue
    )

    total_agent_calls_planned = (
        len(primary_tasks)
        + secondary_route_count
    )

    # --------------------------------------------------------
    # Stats by status
    # --------------------------------------------------------

    status_counts = Counter(
        task.get("original_status", "")
        for task in primary_tasks
    )

    pattern_counts = Counter(
        task.get("pattern", "")
        for task in primary_tasks
    )

    # --------------------------------------------------------
    # Report
    # --------------------------------------------------------

    report = {
        "version": "2.0",

        "principle":
            "SECOND_RECOURSE_ONLY",

        "description": (
            "Les mÃ©canismes symboliques sont prioritaires. "
            "Seuls les cas dÃ©tectÃ©s mais non rÃ©solus de faÃ§on dÃ©terministe "
            "sont routÃ©s vers les agents."
        ),

        "base_directory":
            str(BASE_DIR),

        "sources": {
            "pattern_a":
                a_meta,

            "pattern_b":
                b_meta,

            "pattern_c":
                c_meta,

            "pattern_d_context":
                pattern_d_context(),
        },

        "primary_queue_counts": {
            "agent_pattern_a":
                len(a_queue),

            "agent_pattern_b":
                len(b_queue),

            "agent_pattern_c":
                len(c_queue),
        },

        "secondary_queue_counts": {
            "agent_patient_reference":
                secondary_route_count,
        },

        "unique_cases_routed":
            unique_case_count,

        "secondary_routes":
            secondary_route_count,

        "planned_agent_calls":
            total_agent_calls_planned,

        "unique_cases_by_pattern":
            dict(pattern_counts),

        "unique_cases_by_original_status":
            dict(status_counts),

        "queues": {
            "agent_pattern_a":
                str(QUEUE_A),

            "agent_pattern_b":
                str(QUEUE_B),

            "agent_pattern_c":
                str(QUEUE_C),

            "agent_patient_reference":
                str(QUEUE_PATIENT_REFERENCE),
        },

        "notes": [
            (
                "Patient/RÃ©fÃ©rence est une route secondaire. "
                "Elle ne doit pas Ãªtre additionnÃ©e au nombre de cas uniques."
            ),
            (
                "Pattern D est utilisÃ© comme contexte de validation ontologique "
                "mais n'est pas routÃ© vers les agents A/B/C."
            ),
            (
                "Aucun agent n'est autorisÃ© Ã  modifier directement un JSON clinique."
            ),
        ],
    }

    write_json(
        REPORT_PATH,
        report,
    )

    # --------------------------------------------------------
    # Console
    # --------------------------------------------------------

    print("=" * 88)
    print("TRACE / SGCE - MULTI-AGENT ORCHESTRATOR V2")
    print("=" * 88)

    print()
    print("Principe : second recours uniquement")
    print()

    print("ROUTES PRIMAIRES")
    print("-" * 88)

    print(
        f"Agent Pattern A                 : "
        f"{len(a_queue)}"
    )

    print(
        f"Agent Pattern B                 : "
        f"{len(b_queue)}"
    )

    print(
        f"Agent Pattern C                 : "
        f"{len(c_queue)}"
    )

    print()

    print("ROUTE SECONDAIRE")
    print("-" * 88)

    print(
        f"Agent Patient/RÃ©fÃ©rence         : "
        f"{secondary_route_count}"
    )

    print()

    print("COMPTAGE CORRECT")
    print("-" * 88)

    print(
        f"Cas uniques routÃ©s              : "
        f"{unique_case_count}"
    )

    print(
        f"Routes secondaires              : "
        f"{secondary_route_count}"
    )

    print(
        f"Appels agentiques prÃ©vus        : "
        f"{total_agent_calls_planned}"
    )

    print()

    print(
        f"Rapport                         : "
        f"{REPORT_PATH}"
    )

    print()

    print(
        "Aucune donnÃ©e clinique n'a Ã©tÃ© modifiÃ©e."
    )


if __name__ == "__main__":
    main()

