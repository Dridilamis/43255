# TRACE v2 — une responsabilité par étage, entités et relations

TRACE v2 réorganise la chaîne de réduction des hallucinations. Chaque contrôle
(texte, ontologie, doublons, négation…) est écrit **une seule fois** dans
`trace_lib/`. Chaque étage a **une seule responsabilité**. Les **entités** comme les
**relations** sont traitées. Le code existant (SGCE, étages 3 à 9, 8b) n'est pas
modifié : TRACE v2 l'utilise ou le remplace, et écrit tout dans `TRACE_v2/sorties/`.

## Lancer

Depuis `Reduction_hallucinations\TRACE_v2` :

```
python run_trace_v2.py                          # étages 1 à 8 (~3 min, dont SGCE)
python run_trace_v2.py --from 5                 # reprendre à l'étage 5
python run_trace_v2.py --from 7 --entrainer-vote  # réentraîner les votes des agents (~10 min)
python run_trace_v2.py --garder 80 --garder-entites 80   # mode précision (défaut 80 %)
```

Chaque étage se lance aussi seul (`python etage2_ancrage.py`, etc.).

## Le constat de départ

Le matcher d'entités évalue les entités **par page** (`pages[].entities`). Tous les
étages de l'ancienne chaîne ne modifiaient que `global_entities` : aucun n'agissait
sur les entités évaluées, d'où un F1 entités figé à 71,14 % de l'étage 2 à l'étage 8b.
TRACE v2 traite les deux.

## Les étages

| # | Étage | Seule responsabilité | Retire ? |
|---|---|---|---|
| 1 | `etage1_preparation` | Retire les 455 relations guidées par le gold (définition de `run_pipeline_propre.py`, importée), normalise les noms des entités globales (NFKC), attribue les identifiants manquants | relations guidées par le gold |
| 2 | `etage2_ancrage` | Confronte **entités et relations** au texte source : présence, mot pour mot dans la page, preuve, distance, section | seulement l'impossible : entité absente du document (A0), extrémité absente (A1), preuve absente (A2), entités jamais proches (A3) |
| 3 | `etage3_ontologie` | Confronte chaque relation aux 32 signatures TRACE-Sepsis v1.6 | non (annote) |
| 4 | `etage4_sgce` | Répare la forme du graphe avec **votre SGCE inchangé** (Patterns A1-A6, B1-B2, C, D, Relation Repair, Orphan Resolution, Multi-Agent), lancé dans un atelier temporaire | ce que SGCE retire |
| 5 | `etage5_dedoublonnage` | Fusionne les entités strictement identiques, retire les relations strictement identiques, annote les répétitions | l'identique |
| 6 | `etage6_attributs` | Qualifie chaque entité (globale et par page) : unité, temporalité, négation, hypothèse | non (annote) |
| 7 | `etage7_arbitrage` | **Seul étage qui décide**, pour les entités puis les relations. Agents : ancrage, ontologie, redondance, contexte, provenance | voir ci-dessous |
| 8 | `etage8_evaluation` | **Seul étage qui lit le gold** : P/R/F1 et taux d'hallucination par étage (entités et relations), stabilité pairs/impairs, structure ; entraîne et valide les votes | — |

**Décisions de l'étage 7**

| | Mode standard (règles fixées a priori) | Mode précision (en plus) |
|---|---|---|
| Entités | E1 pas mot pour mot dans sa page · E2 niée dans le texte (« pas de… ») · E3 confiance du LLM « moyenne » ou « faible » | E4 vote des agents : garde les `--garder-entites` % mieux notées |
| Relations | R2 entité niée affirmée par la relation · R3 relation créée par SGCE non ancrée | R4 vote des agents : garde les `--garder` % mieux notées |

Une entité retirée emporte les relations qui pointent vers elle, pour garder un graphe
cohérent. Une violation d'ontologie baisse la confiance mais ne retire pas la relation
(testé : 31 des 43 relations concernées sont justes ; c'est le type de l'entité qui est
faux, pas le lien).

`trace_lib/` : `texte.py` (présence dans le texte, positions, sections, négation),
`documents.py` (graphe, entités par page, retraits cohérents), `ontologie.py`
(signatures : vrai guideline s'il est présent, sinon `ontologie_signatures_v1.6.json`),
`vote.py` (votes appris), `etage.py` (squelette commun).

Non repris : l'étage 9 (2194 relations ajoutées, 12,6 % justes).

## Résultats (43 documents, matching souple)

Taux d'hallucination = part des éléments produits qui sont faux (1 − précision).

| Sortie | Ent P | Ent R | Ent F1 | Ent halluc. | Rel P | Rel R | Rel F1 | Rel halluc. |
|---|---|---|---|---|---|---|---|---|
| Ancienne chaîne (08b) | 74,40 % | 68,15 % | 71,14 % | 25,6 % | 72,03 % | 54,98 % | 62,36 % | 28,0 % |
| **v2, mode standard** | 76,14 % | 67,39 % | **71,50 %** | 23,9 % | 72,74 % | 54,51 % | 62,32 % | 27,3 % |
| **v2, mode précision 90 %** ¹ | 79,95 % | 63,94 % | 71,06 % | 20,0 % | 75,92 % | 49,25 % | 59,75 % | 24,1 % |
| **v2, mode précision 80 %** ¹ | **83,38 %** | 59,27 % | 69,29 % | **16,6 %** | **77,71 %** | 44,32 % | 56,45 % | **22,3 %** |
| v2, mode précision 70 % ¹ | 86,10 % | 53,61 % | 66,08 % | 13,9 % | 79,51 % | 38,20 % | 51,60 % | 20,5 % |

¹ Validation croisée du système complet : les votes sont entraînés sur les documents
pairs, l'étage 7 est appliqué et évalué sur les impairs, puis l'inverse. Chaque document
est donc traité par des modèles qui ne l'ont jamais vu. La ligne `07_arbitrage_precision`
du tableau de l'étage 8 est plus optimiste, car le modèle final est entraîné sur ces
mêmes documents.

En mode précision 80 %, la part d'entités hallucinées baisse d'environ un tiers
(25,6 % → 16,6 %) et celle des relations d'environ un cinquième (28,0 % → 22,3 %), au
prix de rappel.

**Ce que les agents ont appris** (poids des votes) :
- entités : plus souvent fausses quand ce sont des défaillances d'organe ou des
  traitements cités dans l'examen clinique, ou des foyers infectieux très courts ; plus
  souvent justes quand ce sont des biomarqueurs ou imageries dans la biologie, des
  traitements dans les traitements habituels, des antécédents dans les antécédents ;
- relations : plus souvent fausses quand elles répètent un triplet déjà vu ou suivent une
  négation ; plus souvent justes en extraction directe.

**Structure (sans gold)**, entrée → sortie standard : relations orphelines 16 → 6,
relations identiques 0 → 0 (3 créées par SGCE, retirées à l'étage 5), entités et
relations absentes du texte 10 → 0.

## Ce qu'il faut savoir

- Le **mode standard** améliore la précision des entités et des relations sans perte de
  F1. Le **mode précision** réduit fortement les hallucinations mais baisse le rappel et
  le F1 : c'est un réglage à choisir selon l'usage.
- Le gold mélange `µ` (515 fois) et `μ` (338 fois). Les mentions par page restent donc
  identiques au texte ; seules les entités globales (nœuds du graphe) sont normalisées.
- Toutes les mesures portent sur les 43 mêmes documents. Les votes sont mesurés sur des
  documents non vus ; les autres règles ont été fixées a priori.
- Pour faire monter précision, rappel et F1 ensemble, il faut agir à l'extraction
  (étage 0, Mistral).
