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
python run_trace_v2.py --from 4b                # reprendre à l'étage 4b
python run_trace_v2.py --from 7 --entrainer-vote  # réentraîner les votes des agents (~10 min)
python run_trace_v2.py --garder 80 --garder-entites 80   # mode précision (défaut 80 %)
```

Chaque étage se lance aussi seul (`python etage2_ancrage.py`, etc.).

## Étage 0b — seconde passe Mistral (rappel)

`extraction_mistral/seconde_passe_mistral.py` redemande à Mistral, page par page, les
entités puis les relations **oubliées** (en lui montrant ce qui existe déjà). Chaque demande
est faite 3 fois et un élément n'est gardé que s'il revient au moins 2 fois. Une entité
n'est ajoutée que si sa preuve figure mot pour mot dans le texte de la page ; une relation,
que si sa signature respecte l'ontologie. Les réponses sont mises en cache (reprise possible).

**En une commande** (depuis `Reduction_hallucinations`) : la clé est demandée au clavier et
n'est jamais enregistrée ; la seconde passe puis TRACE v2 s'enchaînent et les résultats
avant / après s'affichent.

```
python lancer_trace_complet.py --essai    # essai : 2 documents, vérifie la clé
python lancer_trace_complet.py            # tout (seconde passe + TRACE v2 + votes, ~1 h)
```

Étape par étape :

```
$env:MISTRAL_API_KEY="votre_cle"
python extraction_mistral\seconde_passe_mistral.py --docs 2   # essai
python extraction_mistral\seconde_passe_mistral.py            # 43 documents
cd TRACE_v2
python run_trace_v2.py --entree ..\extraction_mistral\seconde_passe --entrainer-vote
```

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
| 4b | `etage4b_recuperation` | **Rappel** : ajoute les entités oubliées dans les blocs à forme fixe — lignes de biologie (« Leucocytes 40.8 4.0-10.0 x10*9/L ») et lignes d'ordonnance (« Tahor 10mg 0-0-1 » → traitement + posologie) — et relie le traitement à sa posologie sur la même ligne (B3 : 128 relations, 53 justes). Chaque ajout est copié du texte de sa page | non (ajoute) |
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
| Mistral brut (sans post-traitement) | 74,99 % | 60,43 % | 66,93 % | 25,0 % | 45,70 % | 50,69 % | 48,06 % | 54,3 % |
| Mistral brut + TRACE v2 (sans post-traitement, sans SGCE ²) | 76,19 % | 63,23 % | 69,11 % | 23,8 % | 48,37 % | 49,46 % | 48,91 % | 51,6 % |
| Ancienne chaîne (08b) | 74,40 % | 68,15 % | 71,14 % | 25,6 % | 72,03 % | 54,98 % | 62,36 % | 28,0 % |
| **v2, mode standard** | **75,76 %** | **68,57 %** | **71,99 %** | 24,2 % | 71,65 % | 55,58 % | 62,60 % | 28,4 % |
| v2, mode précision 98 % ¹ | 76,43 % | 68,19 % | 72,08 % | 23,6 % | 72,22 % | 55,03 % | 62,46 % | 27,8 % |
| v2, mode précision 95 % ¹ | 77,46 % | 67,19 % | 71,96 % | 22,5 % | 72,66 % | 53,76 % | 61,80 % | 27,3 % |
| **v2, mode précision 90 %** ¹ | 78,86 % | 65,81 % | 71,74 % | 21,1 % | 73,88 % | 52,12 % | 61,12 % | 26,1 % |
| **v2, mode précision 80 %** ¹ | **82,81 %** | 61,41 % | 70,52 % | **17,2 %** | **77,21 %** | 46,33 % | 57,91 % | **22,8 %** |
| v2, mode précision 70 % ¹ | 86,45 % | 55,09 % | 67,30 % | 13,6 % | 79,77 % | 38,83 % | 52,24 % | 20,2 % |
| v2, mode précision 60 % / 50 % ¹ ³ | 89,32 % / 91,97 % | 48,09 % / 40,05 % | 62,52 % / 55,80 % | 10,7 % / 8,0 % | 81,66 % / 82,22 % | 29,72 % / 15,80 % | 43,58 % / 26,51 % | 18,3 % / 17,8 % |

¹ Votes avec agents lexicaux (mots de la mention) : à précision presque égale, rappel et
F1 meilleurs à chaque niveau que sans les mots. La ligne `07_arbitrage_precision` du
tableau de l'étage 8 (≈ 86 % / 85 % de précision) est évaluée sur les documents
d'entraînement : l'écart avec ces chiffres montre que les mots sur-apprennent en partie ;
seuls les chiffres ci-dessus valent pour des documents nouveaux.

³ Mesurés avant l'ajout de B3 (non remesurés).

² Sur l'extraction brute, le multi-agent de SGCE s'arrête (« aucun rapport Relation Repair
contenant des cas REVIEW ») : l'étage 4 est sauté pour cette ligne.

Validation croisée du système complet : les votes sont entraînés sur les documents
pairs, l'étage 7 est appliqué et évalué sur les impairs, puis l'inverse. Chaque document
est donc traité par des modèles qui ne l'ont jamais vu. La ligne `07_arbitrage_precision`
du tableau de l'étage 8 est plus optimiste, car le modèle final est entraîné sur ces
mêmes documents.

**Réglage sans perte de rappel** : `--garder-entites 98 --garder 100` (entités : précision
76,4 %, rappel 68,2 %, F1 72,1 % ; relations inchangées par rapport au mode standard).
Retirer moins de 2 % des entités est le seul moyen de baisser les hallucinations sans
toucher au rappel : au-delà, chaque point d'hallucination en moins coûte du rappel.

En mode standard, précision, rappel et F1 des entités montent tous les trois ; pour les
relations, le rappel (+0,7 point) et le F1 (+0,3 point) montent grâce à B3, la précision
baisse légèrement (71,93 % → 71,65 %). En mode précision 80 %, la part d'entités
hallucinées baisse d'environ un tiers (25,5 % → 17,2 %) et celle des relations d'environ un
cinquième (28,1 % → 22,8 %), au prix de rappel.

**Plafond d'un post-traitement.** Même un filtre parfait (100 % de précision) ne dépasse
pas F1 ≈ 81 % pour les entités et ≈ 71 % pour les relations, car le rappel est borné par
ce que Mistral extrait (≈ 3500 entités et 2200 relations du gold jamais extraites). Un
F1 de 85 % demande d'agir à l'extraction.

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

- Le **mode standard** améliore précision, rappel et F1 des entités, et rappel et F1 des
  relations. Le **mode précision** réduit fortement les hallucinations mais baisse le rappel et
  le F1 : c'est un réglage à choisir selon l'usage.
- Le gold mélange `µ` (515 fois) et `μ` (338 fois). Les mentions par page restent donc
  identiques au texte ; seules les entités globales (nœuds du graphe) sont normalisées.
- Testé et écarté pour le rappel : dupliquer une entité pour chaque occurrence dans le
  texte (+1061 entités, précision −5 points, F1 en baisse) ; relier les entités isolées
  au patient ; l'étage 9 ; étendre les posologies.
- Toutes les mesures portent sur les 43 mêmes documents. Les votes sont mesurés sur des
  documents non vus ; les autres règles ont été fixées a priori.
- Pour faire monter précision, rappel et F1 ensemble, il faut agir à l'extraction
  (étage 0, Mistral).
