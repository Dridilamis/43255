# -*- coding: utf-8 -*-
"""
ETAGE 7 - AGENTS ET ARBITRAGE
Seule responsabilite : DECIDER, pour chaque relation, de la garder ou de la retirer, et lui
donner un niveau de confiance. C'est le seul etage qui juge une relation sur des signaux
(l'Etage 2 ne retire que ce que le texte rend impossible).

Agents (deterministes, sans LLM, sans gold) - chacun lit les annotations des etages 2, 3, 5
et 6 ou, pour une relation creee par SGCE, appelle le meme service :
  AgentAncrage      preuve, distance entre extremites, section            (Etage 2)
  AgentOntologie    signature domaine/image                               (Etage 3)
  AgentRedondance   triplet deja vu sous d'autres identifiants            (Etage 5)
  AgentContexte     negation, hypothese, temporalite de l'entite clinique (Etage 6)
  AgentProvenance   extraction directe ou inference structurelle

Politique de decision (fixee a priori) :
  RETRAIT  R2  l'extraction a marque l'entite clinique comme niee (nie=True) alors que la
               relation l'affirme
           R3  relation creee par SGCE qui echoue a l'ancrage (memes regles que l'Etage 2)
  CONFIANCE  HIGH   aucun signal faible
             MEDIUM 1 signal faible   (preuve absente / note systeme, extremites eloignees,
             LOW    2 signaux faibles ou plus     inference structurelle, doublon, indice de
                                                  negation ou d'hypothese dans le texte,
                                                  violation d'ontologie non reparee)

  Une violation d'ontologie (domaine/image) n'est PAS un motif de retrait : mesure sur les
  43 documents, 31 des 43 relations concernees sont correctes - c'est le TYPE de l'entite
  qui est faux, pas le lien. Elle baisse seulement la confiance.

Modes :
  --mode standard   (defaut) R2-R3.
  --mode precision  R2-R3 + R4 : vote appris des agents (modele/vote_agents.json, entraine
                    par l'Etage 8). Garde la part --garder des relations les mieux notees
                    (defaut 80 %). Sans modele : retire les relations LOW.
                    Reduit les hallucinations au prix de rappel ; l'Etage 8 mesure le
                    compromis sur des documents non vus a l'entrainement.
"""
import sys
from collections import Counter

import etage2_ancrage
import etage3_ontologie
from trace_lib import config as C
from trace_lib.documents import Graph, trace
from trace_lib.etage import run_stage
from trace_lib import vote
from trace_lib.texte import load_source

WEAK = {
    "preuve_non_citee": lambda s: s["ancrage"]["preuve"] in ("ABSENTE", "NOTE_SYSTEME"),
    "extremites_eloignees": lambda s: s["ancrage"]["distance"] in ("PARAGRAPHE", "INTROUVABLE"),
    "inference_structurelle": lambda s: s["provenance"] != "directe",
    "doublon": lambda s: s["doublon"],
    "indice_negation": lambda s: s["contexte"].get("negation", False),
    "indice_hypothese": lambda s: s["contexte"].get("hypothese", False),
    "ontologie_non_conforme": lambda s: s["ontologie"] != "CONFORME",
}


def signals(g, doc, rel):
    t = rel.get("trace_v2", {})
    anc = t.get("ancrage") or etage2_ancrage.assess(g, doc, rel)
    ont = etage3_ontologie.assess(g, rel)          # recalcule : SGCE a pu relier autrement
    clinical_side = "object" if g.is_patient(*g.endpoint(rel, "subject")) else "subject"
    ent, _ = g.endpoint(rel, clinical_side)
    ti = str(rel.get("type_inference") or "")
    return {
        "ancrage": anc,
        "ontologie": ont["statut"],
        "doublon": bool(t.get("doublon")),
        "contexte": (ent or {}).get("trace_v2", {}).get("attributs", {}),
        "nie": bool(ent and ent.get("nie") is True),
        "provenance": "directe" if ti == "extraction_directe" else ("sgce" if t.get("sgce") else "inference"),
        "creee_par_sgce": t.get("sgce") == "CREEE",
    }


def decide(s, mode, rel_type="", model=None, keep=80):
    motifs = []
    if s["nie"]:
        motifs.append("R2_ENTITE_NIEE_AFFIRMEE")
    if s["creee_par_sgce"] and s["ancrage"]["motifs_retrait"]:
        motifs.append("R3_SGCE_NON_ANCREE")
    weak = [k for k, f in WEAK.items() if f(s)]
    level = "HIGH" if not weak else ("MEDIUM" if len(weak) == 1 else "LOW")
    p = None
    if mode == "precision":
        if model:
            p = vote.score(model["poids"], vote.features(s, rel_type))
            if p < model["seuils_garder"][str(keep)]:
                motifs.append("R4_VOTE_AGENTS")
        elif level == "LOW":
            motifs.append("R4_CONFIANCE_LOW")
    return motifs, level, weak, p


def make_process(mode, keep=80):
    model = vote.load() if mode == "precision" else None
    if mode == "precision":
        print(f"Vote des agents : {'modele ' + str(C.MODEL_FILE) + f' (garder {keep} %)' if model else 'pas de modele -> retrait des LOW'}")

    def process(path, data):
        c = Counter()
        g, doc = Graph(data), load_source(data, path)
        remove = []
        for rel in g.relations:
            s = signals(g, doc, rel)
            motifs, level, weak, p = decide(s, mode, str(rel.get("type_relation") or ""), model, keep)
            trace(rel, "arbitrage", {"decision": "RETIREE" if motifs else "GARDEE", "motifs": motifs,
                                     "niveau_confiance": level, "signaux_faibles": weak,
                                     "score_vote": p, "ontologie": s["ontologie"], "mode": mode})
            rel["trace_confidence"] = {"level": level, "method": "TRACE_V2_AGENTS",
                                       "is_probability": False, "signaux_faibles": weak}
            if motifs:
                remove.append(rel.get("identifiant_relation"))
                for m in motifs:
                    c[m] += 1
            else:
                c[f"confiance_{level}"] += 1
        c["relations_retirees"] = g.remove_relations(remove)
        c["relations_sortie"] = len(g.relations)
        return c
    return process


def main(in_dir=None, mode="standard", out_dir=None, keep=80):
    run_stage(7, f"AGENTS ET ARBITRAGE (mode {mode})", in_dir or C.STAGE_DIRS[6], make_process(mode, keep),
              out_dir=out_dir or (C.STAGE_DIRS[7] if mode == "standard" else C.OUT / "07_arbitrage_precision"))
    return 0


if __name__ == "__main__":
    mode = sys.argv[sys.argv.index("--mode") + 1] if "--mode" in sys.argv else "standard"
    keep = int(sys.argv[sys.argv.index("--garder") + 1]) if "--garder" in sys.argv else 80
    if mode not in ("standard", "precision"):
        sys.exit("mode inconnu : standard | precision")
    sys.exit(main(mode=mode, keep=keep))
