# -*- coding: utf-8 -*-
"""
ETAGE 7 - AGENTS ET ARBITRAGE
Seule responsabilite : DECIDER, pour chaque entite et chaque relation, de la garder ou de la
retirer, et donner un niveau de confiance aux relations. C'est le seul etage qui juge une relation sur des signaux
(l'Etage 2 ne retire que ce que le texte rend impossible).

Agents (deterministes, sans LLM, sans gold) - chacun lit les annotations des etages 2, 3, 5
et 6 ou, pour une relation creee par SGCE, appelle le meme service :
  AgentAncrage      preuve, distance entre extremites, section            (Etage 2)
  AgentOntologie    signature domaine/image                               (Etage 3)
  AgentRedondance   triplet deja vu sous d'autres identifiants            (Etage 5)
  AgentContexte     negation, hypothese, temporalite de l'entite clinique (Etage 6)
  AgentProvenance   extraction directe ou inference structurelle

Politique de decision pour les ENTITES (entites de pages[], fixee a priori) :
  RETRAIT  E1  l'entite ne figure pas mot pour mot dans le texte de sa page (reformulation
               ou invention du LLM)
           E2  l'entite est niee dans le texte ("pas de fievre") ou marquee nie=True : un
               fait absent n'est pas une entite clinique presente
           E3  le LLM lui-meme a donne une confiance "moyenne" ou "faible"
  Une entite retiree emporte les relations qui pointent vers elle.

Politique de decision pour les RELATIONS (fixee a priori) :
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
  --mode standard   (defaut) E1-E3, R2-R3.
  --mode precision  en plus, E4 et R4 : vote appris des agents (modele/vote_agents.json,
                    entraine par l'Etage 8). Garde la part --garder-entites des entites et
                    --garder des relations les mieux notees (defaut 80 % chacun). Sans
                    modele : retire seulement les relations LOW.
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
from trace_lib.texte import load_source, norm

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


LOW_LLM_CONFIDENCE = {"moyenne", "faible"}


def entity_signals(g, e, linked_ids, seen):
    t = g.entity_type(e)
    name = g.mention(e)
    key = (norm(name), t)
    seen[key] += 1
    tr = e.get("trace_v2", {})
    att = tr.get("attributs", {})
    ti = str(e.get("type_inference") or "")
    return {
        "type": t,
        "section": att.get("section", "INCONNUE"),
        "reliee": e.get("identifiant_entite") in linked_ids,
        "longueur": "court" if len(name) <= 12 else ("moyen" if len(name) <= 35 else "long"),
        "inference": "directe" if ti == "extraction_directe" else (ti or "aucune"),
        "repetee": seen[key] > 1,
        "hypothese": bool(att.get("hypothese")),
        "negation": bool(att.get("negation")),
        "mot_pour_mot": tr.get("ancrage", {}).get("mot_pour_mot", True),
        "confiance_llm": str(e.get("confiance") or ""),
    }


def decide_entity(s, mode, model=None, keep=80):
    motifs = []
    if not s["mot_pour_mot"]:
        motifs.append("E1_PAS_MOT_POUR_MOT")
    if s["negation"]:
        motifs.append("E2_NIEE")
    if s["confiance_llm"] in LOW_LLM_CONFIDENCE:
        motifs.append("E3_CONFIANCE_LLM_BASSE")
    p = None
    if mode == "precision" and model:
        p = vote.score(model["poids"], vote.entity_features(s))
        if not motifs and p < model["seuils_garder"][str(keep)]:
            motifs.append("E4_VOTE_AGENTS")
    return motifs, p


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


def make_process(mode, keep=80, keep_ent=80, models=None):
    if models is None:
        models = (vote.load() or {}) if mode == "precision" else {}
    m_rel, m_ent = models.get("relations"), models.get("entites")
    if mode == "precision":
        print(f"Vote des agents : {'modele ' + str(C.MODEL_FILE) if models else 'pas de modele -> retrait des LOW'}"
              f" | garder {keep_ent} % des entites, {keep} % des relations")

    def process(path, data):
        c = Counter()
        g, doc = Graph(data), load_source(data, path)

        # 1. entites (celles de pages[])
        linked = {r.get(k) for r in g.relations for k in ("identifiant_entite_sujet", "identifiant_entite_objet")}
        seen, drop = Counter(), []
        for _, e in g.page_entities():
            s = entity_signals(g, e, linked, seen)
            motifs, p = decide_entity(s, mode, m_ent, keep_ent)
            trace(e, "arbitrage", {"decision": "RETIREE" if motifs else "GARDEE", "motifs": motifs,
                                   "score_vote": p, "mode": mode})
            for m in motifs:
                c[m] += 1
            if motifs:
                drop.append(e)
        n_ent, _, n_rel = g.remove_entities(drop)
        c["entites_retirees"] = n_ent
        c["relations_retirees_avec_leur_entite"] = n_rel
        c["entites_sortie"] = len(g.page_entities())

        # 2. relations
        remove = []
        for rel in g.relations:
            s = signals(g, doc, rel)
            motifs, level, weak, p = decide(s, mode, str(rel.get("type_relation") or ""), m_rel, keep)
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


def main(in_dir=None, mode="standard", out_dir=None, keep=80, keep_ent=80, models=None):
    run_stage(7, f"AGENTS ET ARBITRAGE (mode {mode})", in_dir or C.STAGE_DIRS[6],
              make_process(mode, keep, keep_ent, models),
              out_dir=out_dir or (C.STAGE_DIRS[7] if mode == "standard" else C.OUT / "07_arbitrage_precision"))
    return 0


if __name__ == "__main__":
    mode = sys.argv[sys.argv.index("--mode") + 1] if "--mode" in sys.argv else "standard"
    keep = int(sys.argv[sys.argv.index("--garder") + 1]) if "--garder" in sys.argv else 80
    keep_ent = int(sys.argv[sys.argv.index("--garder-entites") + 1]) if "--garder-entites" in sys.argv else 80
    if mode not in ("standard", "precision"):
        sys.exit("mode inconnu : standard | precision")
    sys.exit(main(mode=mode, keep=keep, keep_ent=keep_ent))
