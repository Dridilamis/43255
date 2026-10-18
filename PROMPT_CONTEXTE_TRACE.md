# CONTEXTE DU PROJET TRACE (à lire entièrement avant de répondre)

Tu vas m'aider sur mon mémoire de master. Voici le contexte complet de mon travail : le projet, les données, le guideline d'annotation, l'architecture de réduction des hallucinations étage par étage, les résultats déjà obtenus et l'état d'avancement. Lis tout avant de répondre. Ma demande précise se trouve à la fin, dans la section « MA DEMANDE ».

---

## 1. Le projet en bref

- **Titre** : TRACE, réduction des hallucinations des modèles de langage multimodaux (MLLM) dans l'extraction de graphes de connaissances cliniques sur le sepsis.
- **Cadre** : IHU PROMETHEUS, Work Package 6 (recherche sur le sepsis). Le travail prolonge le cadre KG-EDS (Knowledge Graph for Early Diagnosis of Sepsis), qui reposait sur l'apprentissage en contexte, sans corpus annoté.
- **Objectif** : extraire automatiquement, à partir de comptes rendus d'hospitalisation scannés, un graphe de connaissances (entités et relations), puis **détecter et réduire les hallucinations** du modèle, c'est-à-dire les éléments que le document ne justifie pas.
- **Modèle principal** : Mistral Small 4 (`mistral-small-2603`), utilisé par l'API Mistral, avec une température de 0.
- **Modèle de comparaison** : Qwen2.5-VL, exécuté sur le GPU interne de l'université (une Tesla). Le GPU sert uniquement à Qwen.

## 2. Les données

- **Cohorte** : APROCCHSS (essai multicentrique hydrocortisone + fludrocortisone dans le choc septique, Annane et al., 2018), données AP-HP. Le service est la médecine intensive–réanimation de l'Hôpital Raymond-Poincaré, sur la période 2008–2015.
- **Corpus** : 246 dossiers PDF scannés, sans couche texte. Les dossiers ont été pseudonymisés à la main avant numérisation : les noms ont été partiellement masqués au stylo. Ce sont donc des données pseudonymisées au sens du RGPD, et non anonymisées.
- **Sous-corpus de référence (gold standard)** : **49 dossiers, 291 pages** (de 4 à 8 pages par dossier). L'annotation a été faite dans Label Studio, page par page, puis consolidée par dossier.
- **Annotation** : réalisée par une seule annotatrice (l'auteure), puis validée médicalement par le **Pr Nicholas Heming**, réanimateur spécialiste du sepsis.
- **Mise à jour v1.7 du gold** : le gold a été mis en conformité avec le guideline v1.7 par des **règles déterministes, sans modèle de langage**. Chaque proposition a été validée par l'annotatrice. Le gold final compte 12 095 entités et 5 695 relations.
- **Point important** : les dossiers datant de 2008 à 2015, ils emploient souvent la terminologie **Sepsis-2** (« sepsis sévère », critères SIRS). L'annotation conserve la terminologie écrite.

## 3. Le guideline TRACE-Sepsis v1.7 (validé par le médecin)

- **Fondements** : Sepsis-3 (Singer et al., 2016), Sepsis-2 (Levy et al., 2003), Surviving Sepsis Campaign 2021, KDIGO 2012 (insuffisance rénale aiguë), EUCAST v14.0, barème SOFA (Vincent et al., 1996).
- **20 types d'entités** : DONNEE_PATIENT, LABEL_NOSOLOGIQUE, SIGNE_VITAL, BIOMARQUEUR, SCORE_SOFA, SCORE_qSOFA, SCORE_NEUROLOGIQUE, STADE_IRA, FOYER_INFECTIEUX, MICRO_ORGANISME, DEFAILLANCE_ORGANE, TRAITEMENT, POSOLOGIE, CONTEXTE_ACQUISITION, COMORBIDITE_ANTECEDENT, EVENEMENT_TEMPOREL, EVOLUTION_PRONOSTIC, SERVICE_MEDICAL, IMAGERIE_PROCEDURE, SYMPTOME. S'y ajoute un bloc technique, METADONNEES_PIPELINE (identifiant, page, bbox, confiance, type d'inférence, négation `nie`), qui n'est pas une entité clinique.
- **34 relations orientées** (sujet → relation → objet), chacune avec une signature domaine → image verrouillée. Elles sont regroupées en familles : diagnostiques, thérapeutiques, signes vitaux, biomarqueurs et microbiologie, terrain et risque, temporelles et pronostic, imagerie, symptômes.
  - 30 des 32 relations de la v1.5/v1.6 sont conservées.
  - 2 relations d'imagerie sont retirées : imagerie → défaillance et imagerie → comorbidité.
  - 4 relations sont ajoutées : `ira_a_pour_stade` (DEFAILLANCE_ORGANE → STADE_IRA), `micro_organisme_infecte_site` (MICRO_ORGANISME → FOYER_INFECTIEUX, site infecté, à distinguer de `micro_organisme_isole_dans`, site de prélèvement), `symptome_oriente_foyer` (SYMPTOME → FOYER_INFECTIEUX) et `symptome_associe_gravite_initiale` (SYMPTOME → SCORE_SOFA).
- **Règles clés** :
  - **ancrage textuel** : rien n'est créé par connaissance médicale externe ;
  - la **surface originale** est conservée et la normalisation stockée à part ;
  - **une mention = un seul type** ;
  - une **pneumopathie** (de même que l'abcès, la pyélonéphrite, l'érysipèle ou la sinusite) est un **diagnostic** (LABEL_NOSOLOGIQUE), et FOYER_INFECTIEUX ne représente que la **localisation** ;
  - le site d'infection ne se déduit jamais de l'espèce du germe (un pneumocoque n'est pas forcément pulmonaire) ;
  - un traitement envisagé ne reçoit pas de `traitement_administre_a` ;
  - pas de relation plausible mais non écrite ;
  - les données du patient sont prises à l'admission ;
  - synonymes et abréviations sont reconnus.
- **Règles dérivées** (connaissances, servent à vérifier et non à créer) :
  - R1 : choc septique (Sepsis-3) = vasopresseurs **et** lactate ≥ 2 mmol/L ;
  - R2 : délai de l'antibiotique supérieur à 60 minutes associé à la mortalité ;
  - R3 et R4 : critères qSOFA (fréquence respiratoire ≥ 22, PAS ≤ 100) ;
  - R4bis : confusion ou Glasgow < 15 ;
  - R5 : corticoïdes indiqués dans le choc septique réfractaire ;
  - R7 : risque de BMR (acquisition nosocomiale, antibiotiques récents, voyage dans un pays à forte prévalence de BMR) ;
  - R8 et R9 : pas d'inférence pour l'imagerie et les symptômes ;
  - R10 : stade d'IRA seulement s'il est écrit ;
  - R11 : site d'infection.
- **Traitements, en sous-groupes** :
  - traitement de l'infection (anti-infectieux, chirurgie, drainage) ;
  - traitement symptomatique des défaillances d'organe : hémodynamique, respiratoire, rénal ;
  - autres traitements de support.

## 4. Taxonomie des hallucinations (mes 7 catégories, à garder telles quelles)

| Catégorie | Définition | Traitement dans TRACE |
|---|---|---|
| **Visuelle** | Erreur de lecture de l'image (chiffre mal lu…) | Indirect : une mention absente du texte est repérée par l'ancrage. Sinon, non couverte. |
| **Factuelle** | Information inexistante ou reformulée | Étages 2 et 7 : retrait |
| **Contextuelle** | Fait nié, hypothétique ou ne concernant pas le patient | Étages 4 (agent patient/référence de SGCE), 6 et 7 |
| **Temporelle** | Antécédent pris pour un fait actuel, traitement de sortie pris pour un traitement du séjour | Étage 6 (annotation), indice du vote |
| **Structurelle** | Graphe mal formé : élément composite, entité implicite manquante, doublon, relation orpheline | Étages 4 (SGCE) et 5 |
| **Ontologique** | Mauvais type, signature interdite | Étage 3, puis indice du vote (pas de retrait automatique) |
| **Raisonnement** | Conclusion clinique incohérente avec les signes | Non couverte (perspective) |

## 5. Principes de conception de TRACE

1. **Le texte source est la seule référence.**
2. **Pas de LLM juge** : toutes les vérifications sont des règles explicites.
3. **Une seule responsabilité par étage**, sans redondance.
4. **Annoter avant de décider** : les étages 2 à 6 annotent sans supprimer, sauf les cas impossibles.
5. **Un seul étage décide** : l'étage 7.
6. **Un seul étage lit le gold** : l'étage 8 (évaluation, apprentissage des poids du vote).
7. **Validation croisée** : toute règle ou tout réglage n'est retenu que s'il améliore les deux moitiés du corpus (documents pairs et impairs).

## 6. L'architecture TRACE v2, étage par étage (architecture retenue, à ne pas modifier)

### Étage 0 — Extraction (Mistral Small 4)
- Chaque page PDF est convertie en image PNG à 500 dpi (PyMuPDF), puis Mistral lit directement l'image et transcrit le texte (sans OCR intermédiaire).
- Trois appels sont faits par page : transcription, entités, relations. Ils sont faits à température 0 et renvoient du JSON.
- **Nouvelle extraction v1.7 (en cours)** : les prompts sont construits **uniquement à partir du guideline v1.7**. La validation est déterministe : une entité doit être retrouvée mot pour mot dans la page, son type doit être autorisé, et une relation doit respecter l'une des 34 signatures.
- L'ancien moteur (v1.6) contenait des règles construites en regardant le gold (« rappel construit à partir des FN observés »). La nouvelle extraction n'en a aucune : c'est une extraction brute honnête.

### Étage 0b — Seconde passe Mistral et filtre
- On remontre à Mistral la page et ce qu'il a déjà trouvé, puis on lui demande ce qui manque.
- Il y a 3 échantillons à température 0,3, avec un vote ≥ 2 sur 3. La preuve doit être mot pour mot et la signature valide.
- **Filtre** :
  - une entité ajoutée est gardée si son type est fiable (MICRO_ORGANISME, TRAITEMENT, BIOMARQUEUR, EVOLUTION_PRONOSTIC), si elle obtient un vote de 3/3 et si elle n'est pas niée ;
  - elle est aussi gardée si une deuxième passe avec exemples propose la même entité ;
  - **toutes les relations ajoutées sont retirées**.
- **Constat** : sans filtre, seuls 27 % des entités et 15 % des relations ajoutées étaient justes. Avec le filtre, 421 entités ont été gardées.

### Étage 1 — Préparation
- Retrait des **455 relations guidées par le gold** de l'ancien post-traitement, pour une évaluation honnête.
- Normalisation des noms (NFKC, deux caractères « µ » différents) et attribution d'identifiants uniques.

### Étage 2 — Ancrage documentaire (hallucinations factuelles)
- **Pour une entité** :
  - est-elle **présente** dans le document ? Il faut le texte exact, sinon au moins 50 % des mots porteurs de sens (un mot étant retrouvé par ses 5 premières lettres) et tous les nombres de la mention ;
  - est-elle écrite **mot pour mot** dans sa page ?
- **Pour une relation** :
  - la **preuve** est-elle attestée, inventée, absente ou une note système ?
  - quelle est la **distance** entre les deux extrémités : patient, même ligne (≤ 80 caractères), paragraphe (≤ 300), loin ou introuvable ?
  - dans quelle **section** est-elle citée ?
- **Retraits (seulement les cas impossibles)** :
  - **A0** : entité absente de tout le document ;
  - **A1** : extrémité d'une relation absente du texte ;
  - **A2** : preuve inventée ;
  - **A3** : les deux extrémités ne sont jamais à moins de 300 caractères.
- Le reste est seulement annoté.

### Étage 3 — Validation ontologique
- Chaque relation est comparée aux signatures du guideline (34 en v1.7) : conforme, domaine invalide ou image invalide.
- **Rien n'est retiré** : une violation est un indice. Les vérifications à la main ont montré que c'est le plus souvent le type de l'entité qui est faux, pas le lien.

### Étage 4 — SGCE (contribution existante, exécutée sans modification)
- SGCE est exécuté dans une copie temporaire :
  - **Pattern A** (A1 à A6) : décomposer un élément composite ;
  - **Pattern B** (B1, B2) : ajouter une entité implicite nécessaire ;
  - **Pattern C** : compléter ou réorienter une chaîne de relations ;
  - **Pattern D** : réparer une violation d'ontologie ;
  - **Relation Repair**, **Orphan Resolution**, et un **multi-agent** comprenant l'agent qui distingue le patient d'une référence générale.
- SGCE répare la **forme** du graphe ; les autres étages vérifient le **fond**.

### Étage 4b — Récupération ciblée (rappel sans risque)
- **B1** : les lignes de biologie « libellé valeur [norme] [unité] » de la section biologie deviennent des BIOMARQUEUR. Une liste d'exclusion BIO_SKIP écarte les faux biomarqueurs (« Témoin », « FiO2 »…).
- **B2** : les lignes d'ordonnance (traitement habituel, sortie) donnent un TRAITEMENT et une POSOLOGIE.
- **B3** : sur une ligne d'ordonnance, une relation `traitement_a_pour_posologie` est créée, avec la ligne comme preuve.
- **B4**, le lien traitement → patient, a été **testé et écarté** : seuls 17 % de ses ajouts étaient justes.
- Tout ajout est copié du texte de sa page.

### Étage 5 — Dédoublonnage
- **D1** : fusion des entités strictement identiques, avec report de leurs relations.
- **D2** : retrait des relations strictement identiques.
- **D3** : les répétitions d'un même fait sous d'autres identifiants sont **annotées** « doublon », sans être retirées.

### Étage 6 — Attributs cliniques (hallucinations contextuelles et temporelles)
- **Négation** : un mot déclencheur (« pas de », « absence de », « sans », « éliminé »…) figure dans les 40 caractères qui précèdent la mention, ou Mistral a marqué l'élément `nie = true`. C'est le principe de NegEx et de ConText.
- **Hypothèse** : « suspicion de », « probable », « à discuter »…
- **Temporalité**, déduite de la section : antérieur (antécédents, traitements habituels), séjour ou sortie.
- **Unités** des valeurs.
- L'étage annote seulement.

### Étage 7 — Arbitrage : agents et décision (le seul étage qui décide)
- **Agents** déterministes : ancrage, ontologie, redondance, contexte, provenance, vocabulaire.
- **Mode standard** (règles certaines) :
  - **E1** retire une entité non écrite mot pour mot dans sa page ;
  - **E2** retire une entité niée ;
  - **E3** retire une entité à laquelle Mistral a donné une confiance moyenne ou faible ;
  - **R2** retire une relation qui affirme une entité niée ;
  - **R3** retire une relation créée par SGCE qui échoue à l'ancrage ;
  - une entité retirée emporte ses relations (cascade).
- **Confiance des relations** : on compte 7 signaux faibles. Aucun signal donne HIGH, un signal donne MEDIUM, deux ou plus donnent LOW.
- **Mode précision : le vote appris des agents** (E4 pour les entités, R4 pour les relations) :
  - chaque élément est décrit par des **cases binaires** :
    - catégories en one-hot (type, section, preuve, provenance, ontologie, temporalité) ;
    - valeurs numériques rangées en tranches (distance, longueur) ;
    - sac de mots ;
    - croisements (type × section, type × reliée, type × chiffre, type × mot…) ;
  - une **régression logistique** (numpy, descente de gradient, 3 000 itérations, pas de 0,5, régularisation L2 avec λ = 1) apprend un poids par case ;
  - le score vaut σ(somme des poids des cases cochées) ;
  - on garde la part X % la mieux notée (98, 95, 90, 85, 80, 70 ou 60 %), le **seuil** étant le quantile correspondant ;
  - deux modèles sont appris, un pour les entités et un pour les relations ;
  - les poids sont appris à l'étage 8, puis appliqués à l'étage 7 sans jamais regarder le gold.

### Étage 8 — Évaluation (le seul étage qui lit le gold)
- **Appariement des entités, page par page** : même type, et nom exact, ou l'un inclus dans l'autre (au moins 4 caractères), ou similarité ≥ 0,85.
- **Appariement des relations** : triplet sujet–relation–objet, avec les mêmes règles sur les deux extrémités.
- Un **mauvais type compte à la fois comme FP et comme FN**.
- **Métriques** : précision, rappel, F1 et taux d'hallucination (H = 1 − précision), en micro (métrique officielle), en macro (moyenne par document) et en strict (exact seul), mesurées après chaque étage.
- L'attribut `nie` n'intervient pas dans l'appariement : le gold ne code la négation que par la surface (« pas de marbrures »).
- **Validation croisée à 2 plis** (documents pairs et impairs) pour mesurer honnêtement le mode précision.

## 7. Résultats déjà obtenus (ancienne version : guideline v1.6, 43 documents, ancienne extraction)

Ces chiffres sont **provisoires** : ils seront recalculés avec le guideline v1.7, la nouvelle extraction et le gold v1.7. Valeurs en micro, appariement souple, en % :

| Configuration | Entités P / R / F1 | H entités | Relations P / R / F1 | H relations |
|---|---|---|---|---|
| Extraction brute Mistral | 74,99 / 60,43 / 66,93 | 25,0 | 45,70 / 50,69 / 48,06 | 54,3 |
| Avant TRACE (post-traitement sans règles guidées) | 74,46 / 68,10 / 71,14 | 25,5 | 71,93 / 54,92 / 62,29 | 28,1 |
| TRACE v2 standard | 75,13 / 70,32 / 72,65 | 24,9 | 71,60 / 55,58 / 62,58 | 28,4 |
| TRACE précision, garder 80 % (validation croisée) | 82,40 / 62,81 / 71,28 | 17,6 | 77,03 / 46,69 / 58,14 | 23,0 |

**Autres résultats** :
- E1 et E2 retirent des éléments qui sont absents du gold dans environ 3 cas sur 4.
- **Limite principale** : E2 retire aussi des faits que le gold annote, par exemple « arrêt Lasilix ».
- Les relations de raisonnement (antibiotique adéquat, imagerie → défaillance…) ne sont presque jamais produites.

**Résultats publiés séparément** dans mon article, avec un protocole d'évaluation préliminaire **différent**, qui ne doit pas servir de point de départ chiffré à TRACE :
- Mistral Small 4 : entités 67,38 / 71,89 / 69,57 ; relations 67,42 / 58,17 / 62,43 ;
- Qwen2.5-VL : entités 64,10 / 63,67 / 63,88 ; relations 50,83 / 30,31 / 37,98.

## 8. Où j'en suis

**Fait** :
- guideline v1.7 validé par le médecin ;
- gold v1.7 corrigé et importable dans Label Studio ;
- interface Label Studio v1.7 ;
- script de nouvelle extraction v1.7 ;
- TRACE v2 complet (étages 0 à 8) ;
- chapitre 3 (données, guideline, gold) et chapitre 6 (expérimentations, résultats v1.6) rédigés.

**En cours** : nouvelle extraction Mistral des **49 dossiers** selon le guideline v1.7, lancée sur mon PC.

**Ensuite** :
1. convertir le gold v1.7 au format de l'évaluateur ;
2. faire passer l'étage 3 à 34 signatures ;
3. relancer TRACE v2 (même architecture) ;
4. réentraîner le vote en validation croisée ;
5. refaire les tableaux du chapitre 6 ;
6. mettre à jour le chapitre 3 (mise en conformité v1.7 du gold, assistée par des règles et validée).

**Décisions encore ouvertes avec le médecin** :
- seuils du barème SOFA ;
- relation SOFA → vasopresseurs ;
- relations germe → diagnostic et imagerie → diagnostic, quand aucune localisation n'est écrite ;
- prise en compte de la dialyse et de la diurèse dans le stade IRA.

## 9. Règles à respecter dans ta réponse

- **N'invente aucun chiffre, aucun résultat, aucune référence.** Si une valeur manque, écris « [à compléter] ».
- **Ne propose jamais** de règle construite à partir du gold, ni de présenter les résultats de l'article comme « avant TRACE ».
- **Garde l'architecture TRACE v2 telle quelle** (étages 0 à 8) et les noms des 7 catégories d'hallucination.
- Écris en **français académique**, clair et précis, au niveau d'un mémoire de master. Explique les idées avant les détails techniques. Pas de code, sauf si je le demande.
- Si tu cites l'état de l'art, utilise des références réelles et vérifiables : Ji et al. 2023 ; Huang et al. 2023 ; Bai et al. 2024 ; Manakul et al. 2023 (SelfCheckGPT) ; Wang et al. 2023 (self-consistency) ; Rashkin et al. 2023 ; Chapman et al. 2001 (NegEx) ; Harkema et al. 2009 (ConText) ; Ratner et al. 2017 (Snorkel) ; Geifman & El-Yaniv 2017 ; Paulheim 2017 ; Uzuner et al. 2011 ; Pal et al. 2023 (Med-HALT).

---

## MA DEMANDE

[Écris ici ce que tu veux obtenir, par exemple : « Rédige la section 5.3 du chapitre 5, qui décrit l'étage 7 (arbitrage et mode précision), en LaTeX, en 2 pages, avec un tableau des règles E1 à E3 et R2, R3. »]
