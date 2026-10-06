# TRACE v2 — une responsabilité par étage

TRACE v2 réorganise la chaîne de réduction des hallucinations. Chaque contrôle
(texte, ontologie, doublons, négation…) est écrit **une seule fois** dans
`trace_lib/`. Chaque étage a **une seule responsabilité**. Le code existant (SGCE,
étages 3 à 9, 8b) n'est pas modifié : TRACE v2 l'utilise ou le remplace, et écrit
tout dans `TRACE_v2/sorties/`.

## Lancer

Depuis `Reduction_hallucinations\TRACE_v2` :

```
python run_trace_v2.py                   # étages 1 à 8 (~3 min, dont SGCE)
python run_trace_v2.py --from 5          # reprendre à l'étage 5
python run_trace_v2.py --entrainer-vote  # réentraîner le vote des agents avant l'étage 7
python run_trace_v2.py --garder 70       # part gardée par le mode précision (défaut 80)
```

Chaque étage se lance aussi seul (`python etage2_ancrage.py`, etc.).

## Les étages

| # | Étage | Seule responsabilité | Retire ? | Remplace |
|---|---|---|---|---|
| 1 | `etage1_preparation` | Retire les relations guidées par le gold (définition de `run_pipeline_propre.py`, importée), normalise les noms en Unicode NFKC, attribue les identifiants manquants | relations guidées par le gold | nettoyage de `run_pipeline_propre`, N1 de 8b |
| 2 | `etage2_ancrage` | Confronte chaque relation au texte source : entités présentes ? preuve réelle ? entités proches ? section ? | uniquement l'impossible : entité absente du texte (A1), preuve absente (A2), entités jamais proches (A3) | étage 3, 8b (G1, G2, G5), vote documentaire, preuve de l'étage 8, validateur de l'étage 9 |
| 3 | `etage3_ontologie` | Confronte chaque relation aux 32 signatures TRACE-Sepsis v1.6 | non (annote) | Pattern D (détection), étage 4 (validation), filtre de l'étage 9, vote ontologique |
| 4 | `etage4_sgce` | Répare la forme du graphe avec **votre SGCE inchangé** : Patterns A1-A6, B1-B2, C, D, Relation Repair, Orphan Resolution, Multi-Agent | ce que SGCE retire | SGCE (lancé dans un atelier temporaire, le dossier `SGCE` n'est jamais modifié) |
| 5 | `etage5_dedoublonnage` | Fusionne les entités strictement identiques, retire les relations strictement identiques, annote les répétitions | relations identiques | doublons de l'étage 4 (2 copies), dédoublonneur de l'agent B, G4 |
| 6 | `etage6_attributs` | Unité, temporalité (antérieur / séjour / sortie), négation, hypothèse — en une passe | non (annote) | étages 5, 6, 7, G3 de 8b |
| 7 | `etage7_arbitrage` | **Seul étage qui décide.** Cinq agents (ancrage, ontologie, redondance, contexte, provenance) lisent les annotations ; politique fixée a priori ; niveau de confiance | entité niée affirmée (R2), relation SGCE non ancrée (R3) ; en mode précision : vote des agents (R4) | multi-agent (adjudicateur, votes), étage 8 |
| 8 | `etage8_evaluation` | **Seul étage qui lit le gold** : P/R/F1 par étage, taux d'hallucination, stabilité pairs/impairs, métriques de structure ; entraîne et valide le vote des agents | — | scripts d'ablation (les matchers existants sont réutilisés tels quels) |

`trace_lib/` contient les services partagés : `texte.py` (présence dans le texte,
positions, sections, indices de négation), `documents.py` (graphe, patient, retrait
d'une relation), `ontologie.py` (signatures : vrai guideline s'il est présent, sinon la
copie figée `ontologie_signatures_v1.6.json`), `vote.py` (vote appris), `etage.py`
(squelette commun d'un étage).

Ce qui n'est pas repris : l'étage 9 (2194 relations ajoutées, 12,6 % justes).

## Résultats (43 documents, relations, matching souple)

| Sortie | Ent F1 | Rel P | Rel R | Rel F1 | Taux d'hallucination |
|---|---|---|---|---|---|
| Ancienne chaîne, 08_CONFIDENCE | 71,14 % | 71,66 % | 54,92 % | 62,19 % | 28,34 % |
| Ancienne chaîne, 08b | 71,14 % | 72,03 % | 54,98 % | 62,36 % | 27,97 % |
| **v2, 07 mode standard** | 71,14 % | 71,99 % | 55,05 % | **62,39 %** | 28,01 % |
| **v2, 07 mode précision (garder 80 %)**, validation croisée | 71,14 % | **76,39 %** | 46,31 % | 57,66 % | **23,61 %** |

Taux d'hallucination = part des relations produites qui sont fausses (1 − précision).

Le mode précision est mesuré par **validation croisée** : chaque document est noté par
un modèle qui ne l'a jamais vu (entraînement sur les documents pairs, test sur les
impairs, et inversement). La ligne `07_arbitrage_precision` du tableau de l'étage 8 est
plus optimiste (78,4 %), car le modèle final a été entraîné sur ces mêmes documents.

Autres points de fonctionnement du mode précision (validation croisée) :

| Garder | Précision | Rappel | F1 | Hallucinations |
|---|---|---|---|---|
| 90 % | 74,73 % | 50,19 % | 60,05 % | 25,27 % |
| 80 % | 76,39 % | 46,31 % | 57,66 % | 23,61 % |
| 70 % | 77,89 % | 41,82 % | 54,42 % | 22,11 % |
| 60 % | 78,96 % | 37,42 % | 50,78 % | 21,04 % |

Ce que les agents ont appris (poids du vote) : une relation est plus souvent fausse
quand elle répète un triplet déjà vu, quand un indice de négation précède l'entité, ou
selon la section (ex. « traitement administré » cité dans le motif ou la prescription de
sortie). Elle est plus souvent juste quand elle vient d'une extraction directe et que les
deux entités sont sur la même ligne.

Métriques de structure (sans gold), entrée → sortie standard : relations orphelines
16 → 6, violations d'ontologie 46 → 42, relations identiques 0 → 0 (3 créées par SGCE,
retirées à l'étage 5), relations dont une entité est absente du texte 10 → 0.

## Ce qu'il faut savoir

- **Les violations d'ontologie ne sont pas retirées.** Testé : sur 43 relations qui
  violent une signature, 31 sont justes. C'est le type de l'entité qui est faux, pas
  le lien. La violation baisse seulement la confiance.
- **Le mode précision échange du rappel contre de la précision.** Les signaux des agents
  séparent mal les vraies relations des fausses (voir le tableau ci-dessus) : la plupart des faux
  positifs restants sont bien présents dans le texte, mais non annotés par le gold.
  Pour faire monter précision, rappel et F1 ensemble, il faut agir à l'extraction
  (étage 0, Mistral).
- **Toutes les mesures portent sur les 43 mêmes documents.** Seul le vote des agents a
  une mesure sur documents non vus ; les autres règles ont été fixées a priori.
- L'étage 6 renseigne 516 unités manquantes (contre 35 pour l'ancien étage 5) ; le F1
  des entités ne change pas.
