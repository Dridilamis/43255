# TRACE, étage par étage : ce qu'il faut savoir pour défendre l'architecture

> Chiffres : guideline v1.6, 43 dossiers, appariement souple, micro-moyenne
> (`TRACE_v2/sorties/08_evaluation/tableau.csv`). Ils seront recalculés en v1.7.
> H = taux d'hallucination = part des éléments produits qui sont faux = 1 − précision.

---

## 0. L'idée en trois phrases (à savoir par cœur)

1. **Le problème.** Mistral Small 4 lit des dossiers scannés et produit un graphe, mais
   **1 entité sur 4 et plus d'1 relation sur 2** qu'il produit sont fausses (H entités 25 %, H relations 54 %).
2. **La solution.** TRACE est une chaîne de contrôles **après extraction**. Chaque étage traite
   **un seul type d'hallucination**. Le **texte du dossier est la seule référence**, et **aucun LLM ne joue le rôle de juge**.
3. **Le résultat.** En mode standard, TRACE améliore le F1 sans rien sacrifier. En mode précision, il fait
   passer les hallucinations d'entités de **25 % à 18 %** et celles des relations de **54 % à 23 %**.
   Chaque retrait est **explicable** : on sait quel étage l'a décidé, et pourquoi.

## Les 7 principes (ce qui rend l'architecture défendable)

| Principe | Pourquoi |
|---|---|
| Le texte source est la seule référence | En extraction, l'erreur grave est le manque de **fidélité** au dossier (Huang et al., 2025), plus que l'erreur factuelle générale |
| Pas de LLM juge | Un LLM qui se corrige sans retour extérieur fiable ne s'améliore pas (Kamoi et al., 2024 ; Huang J. et al., 2024) |
| Une responsabilité par étage | Chaque gain ou perte est attribuable à un étage, ce qui permet les ablations |
| Annoter avant de décider | Les étages 2 à 6 ajoutent des informations ; un seul étage tranche, avec toutes les informations en main |
| Un seul étage décide (7) | Pas de conflit entre étages ni de suppression en cascade incontrôlée |
| Un seul étage lit le gold (8) | Aucune règle n'est réglée sur la référence : l'évaluation reste honnête |
| Validation croisée pairs / impairs | Un réglage n'est retenu que s'il améliore les deux moitiés du corpus |

## Vue d'ensemble

```
PDF scanné
  │ 0  Extraction Mistral (image → texte → entités → relations)
  │ 0b Seconde passe + filtre (rappel)
  │ 1  Préparation (nettoyage, identifiants)
  │ 2  Ancrage dans le texte ............ hallucination FACTUELLE
  │ 3  Ontologie (signatures) ........... hallucination ONTOLOGIQUE
  │ 4  SGCE (réparation de la forme) .... hallucination STRUCTURELLE
  │ 4b Récupération ciblée (rappel)
  │ 5  Dédoublonnage .................... STRUCTURELLE (doublons)
  │ 6  Attributs cliniques .............. CONTEXTUELLE et TEMPORELLE
  │ 7  Arbitrage (seul étage qui décide)
  ▼ 8  Évaluation (seul étage qui lit le gold)
Graphe de connaissances + niveau de confiance de chaque élément
```

---

## Étage 0 — Extraction par Mistral Small 4

**Ce qu'il fait.** Chaque page est convertie en image PNG à 500 dpi. Mistral **lit l'image directement**,
sans OCR intermédiaire, puis il fait trois appels à température 0 : transcription, entités, relations.
Chaque appel renvoie un JSON. Les consignes données au modèle sont construites **uniquement à partir du guideline**.

**Pourquoi ce choix.**
- Les MLLM lisent mieux que les OCR classiques des documents cliniques bruités : par exemple, un CER de 0,031
  contre 0,189 pour Tesseract chez Neveditsin et al. (2026).
- La résolution compte : sous 150 ppi, les MLLM s'effondrent (Inoue, 2025). D'où les 500 dpi.
- La température 0 rend les réponses reproductibles.

**Ce qu'il ne fait pas.** Il ne corrige rien : c'est la sortie **brute**, avec ses hallucinations.
Tout le reste de TRACE part de là.

**Point d'honnêteté à mettre en avant.** L'ancien moteur contenait des règles écrites en regardant le gold.
La nouvelle extraction v1.7 n'en contient **aucune** : c'est une extraction brute honnête.

> **Question du jury :** « Pourquoi pas un OCR, puis un LLM sur le texte ? »
> **Réponse :** Les dossiers sont manuscrits ou bruités (tampons, photocopies). Un OCR y fait beaucoup d'erreurs
> qui se propagent ensuite au graphe. Le MLLM lit mieux, mais il hallucine : c'est précisément ce que TRACE contrôle.

---

## Étage 0b — Seconde passe et filtre (rappel)

**Problème traité.** Les **oublis**. Mistral ne trouve pas tout (rappel d'environ 60 %).

**Ce qu'il fait.**
- On remontre à Mistral la page et ce qu'il a déjà trouvé, et on lui demande ce qui manque.
- La demande est faite **3 fois**, et un élément n'est gardé que s'il revient **au moins 2 fois** (vote).
- Une entité n'est acceptée que si sa preuve est écrite mot pour mot dans la page.

**Le résultat qui justifie le filtre.** Sans filtre, seuls **27 % des entités** et **15 % des relations**
ajoutées sont justes : la seconde passe brute **dégrade** le F1. Le filtre garde donc uniquement :
- les entités de types fiables (micro-organisme, traitement, biomarqueur, évolution) votées 3 sur 3 et non niées ;
- les entités confirmées par une seconde passe indépendante ;
- **aucune relation ajoutée.**

Au final, 421 entités sont gardées, et le F1 des entités passe de 71,99 % à 72,60 %.

**Littérature.** C'est le principe de la *self-consistency* (Wang et al., 2023) et de SelfCheckGPT (Manakul et al., 2023) :
une information que le modèle connaît vraiment revient d'un échantillon à l'autre.

> **Question du jury :** « Demander à un LLM ce qu'il a oublié, ça ne crée pas d'hallucinations ? »
> **Réponse :** Si, et je l'ai mesuré : seulement 15 % des relations ajoutées étaient justes. C'est pour cela que je les
> retire toutes et que je ne garde que les entités confirmées par le vote et par le texte. Ce chiffre montre que je ne
> fais pas confiance au LLM pour se corriger lui-même.

---

## Étage 1 — Préparation

**Ce qu'il fait.**
- Il retire **455 relations** produites par l'ancien post-traitement, dont les règles avaient été construites en regardant le gold.
- Il normalise l'écriture (Unicode NFKC, deux caractères « µ » différents) et donne un identifiant unique à chaque élément.

**Pourquoi.** C'est un étage d'**honnêteté expérimentale**. Garder des règles réglées sur la référence gonflerait
artificiellement les scores. Le retirer **baisse** mes chiffres, mais rend l'évaluation valide.

> **Question du jury :** « Pourquoi retirer des relations qui étaient peut-être justes ? »
> **Réponse :** Parce qu'elles venaient de règles écrites en regardant la réponse. Une évaluation honnête exige qu'aucune
> étape ne soit réglée sur le gold. Seul l'étage 8 le lit.

---

## Étage 2 — Ancrage documentaire (hallucination **factuelle**)

**Problème traité.** Le modèle **invente** une entité ou une relation que le dossier ne contient pas.

**Ce qu'il fait.**
- **Pour chaque entité**, il vérifie si elle est présente dans le document : texte exact, ou à défaut au moins
  50 % des mots porteurs de sens et **tous les nombres** de la mention. Il vérifie aussi si elle est écrite **mot pour mot** dans sa page.
- **Pour chaque relation**, il évalue :
  - la **preuve** citée par le modèle : attestée, inventée ou absente ;
  - la **distance** entre les deux entités : même ligne, même paragraphe, loin ;
  - la **section** du dossier où elle se trouve.
- Il ne **retire que l'impossible** :
  - **A0** : entité absente de tout le document ;
  - **A1** : extrémité d'une relation absente du texte ;
  - **A2** : preuve inventée ;
  - **A3** : entités jamais à moins de 300 caractères l'une de l'autre.
- Tout le reste est **annoté**, pas supprimé.

**Exemple.** Mistral produit « CRP à 186 » alors que la page indique « CRP 86 ». Le nombre 186 n'est pas dans le texte,
donc l'entité n'est pas ancrée.

**Pourquoi « tous les nombres ».** En médecine, l'erreur la plus dangereuse est un chiffre faux : une valeur biologique ou une posologie.

**Littérature.** C'est la fidélité à la source (Ji et al., 2023 ; Huang et al., 2025). RAPTOR+ (2026) appelle cet échec les
« extractions non ancrées ».

> **Question du jury :** « Pourquoi ne pas tout retirer dès qu'un élément n'est pas mot pour mot ? »
> **Réponse :** Parce que le modèle reformule souvent correctement (abréviation développée, accord grammatical).
> Retirer à cet endroit ferait perdre du juste. L'étage 2 retire seulement ce qui est impossible ; le cas « pas mot pour mot »
> est tranché à l'étage 7 (règle E1), où l'on a vérifié qu'environ 3 retraits sur 4 sont bien des erreurs.

---

## Étage 3 — Validation ontologique (hallucination **ontologique**)

**Problème traité.** Une relation **interdite par le schéma**, par exemple « traitement → micro-organisme »
utilisé avec un symptôme comme objet.

**Ce qu'il fait.** Il compare chaque relation aux **signatures** du guideline (34 en v1.7) : domaine (type du sujet)
→ image (type de l'objet). Le verdict est conforme, domaine invalide ou image invalide.

**Il ne retire rien, et c'est voulu.** J'ai vérifié à la main : sur 43 relations en violation, **31 étaient justes**.
C'est presque toujours le **type d'une entité** qui est faux, pas le lien. Supprimer la relation ferait perdre une information
juste. La violation devient donc **un indice** pour SGCE (Pattern D, qui retype l'entité) et pour le vote de l'étage 7.

**Littérature.** C'est le principe de la validation par contraintes (SHACL, W3C 2017) et de Tran et al. (2025, LLM + ASP).
Une limite connue : un graphe valide n'est pas forcément fidèle au document.

> **Question du jury :** « Une relation hors schéma, c'est forcément une erreur, non ? »
> **Réponse :** C'est une erreur de **forme**, mais le fond est souvent juste (31 sur 43). Mieux vaut réparer le type
> (SGCE) que supprimer le lien.

---

## Étage 4 — SGCE (hallucination **structurelle**)

**Problème traité.** Un graphe **mal formé** :
- une entité qui regroupe deux concepts ;
- une entité intermédiaire manquante ;
- un lien extrait comme s'il était une entité ;
- une violation de signature ;
- une relation orpheline.

**Ce qu'il fait.** SGCE (contribution existante, exécutée sans modification) applique des **motifs d'erreur typés** :

| Pattern | Erreur | Réparation |
|---|---|---|
| A (A1–A6) | Entité composite, par exemple « Augmentin 1 g × 3 » | La découper en traitement + posologie, puis les relier |
| B1 | Une relation pointe vers une référence absente | La rattacher, ou créer l'entité si le texte la contient |
| B2 | Il manque un nœud intermédiaire exigé par le schéma | Créer ce nœud, à partir du texte |
| C | Un lien a été extrait comme une entité | Le réécrire en relation |
| D | Violation de signature | Retyper l'entité ou rediriger la relation |
| Relation Repair / Orphan Resolution | Relation mal typée, entité isolée | Corriger ou rattacher |
| Multi-agent | Cas ambigus | Agents **déterministes** et vote (3/3, ou 2/3 sans veto avec preuve) ; sinon **abstention** |

Chaque correction suit le cycle **détection → validation → correction → post-validation**. Une correction n'est gardée
que si la structure s'améliore.

**Résultat.** Les relations orphelines passent de **15 à 6** et les violations d'ontologie de **45 à 42**, **sans baisse du F1**
(72,00 → 72,00 pour les entités ; 62,36 → 62,40 pour les relations).

**Comment le présenter.** SGCE répare la **forme** du graphe, pas le fond. Son rôle n'est pas de réduire les hallucinations
factuelles, mais de rendre le graphe **exploitable** (requêtes, raisonnement) sans rien dégrader.

**Littérature.** Raffinement de graphes (Paulheim, 2017) ; réparation minimale sous contraintes (Chu et al., 2013 ;
HoloClean, 2017) ; abstention (Geifman et El-Yaniv, 2017).

> **Question du jury :** « SGCE ne change pas le F1, alors à quoi sert-il ? »
> **Réponse :** Le F1 mesure les éléments un par un ; il ne voit pas qu'un graphe a 15 morceaux isolés. Un graphe clinique
> doit être **connexe et conforme** pour être interrogé. SGCE apporte cela sans aucune perte.

---

## Étage 4b — Récupération ciblée (rappel sans risque)

**Problème traité.** Les oublis dans les **blocs à forme fixe**, que Mistral saute souvent.

**Ce qu'il fait.** Toutes ses règles **copient le texte de la page**, sans rien inventer :
- **B1** : une ligne de biologie « Leucocytes 40,8 4,0–10,0 G/L » devient un BIOMARQUEUR, avec une liste d'exclusion
  pour les valeurs témoins du laboratoire et les réglages du ventilateur ;
- **B2** : une ligne d'ordonnance « Tahor 10 mg 0-0-1 » devient un TRAITEMENT et une POSOLOGIE ;
- **B3** : sur cette même ligne, une relation `traitement_a_pour_posologie` est créée (128 relations, dont 53 justes).
- **B4** (relier traitement → patient) a été **testé et écarté** : seulement 17 % de ses ajouts étaient justes.

**Résultat.** Le rappel des entités passe de 70,3 à **71,1 %**, celui des relations de 55,1 à **56,2 %**, et le F1 relations de 62,40 à 62,65.

> **Question du jury :** « Des règles écrites à la main, ce n'est pas du sur-mesure sur votre corpus ? »
> **Réponse :** Elles décrivent un **format** (une ligne de biologie, une ligne d'ordonnance), pas des réponses du gold.
> J'ai aussi écarté B4, qui n'apportait pas assez : je garde une règle seulement si elle est mesurée comme utile.

---

## Étage 5 — Dédoublonnage (structurelle)

**Ce qu'il fait.**
- **D1** : il fusionne les entités strictement identiques et reporte leurs relations.
- **D2** : il retire les relations strictement identiques (3, créées par SGCE).
- **D3** : il **annote** les répétitions d'un même fait sous des identifiants différents, sans les retirer.

**Pourquoi D3 n'est qu'une annotation.** Une répétition est un **indice** : le vote apprend qu'un doublon est souvent faux
(poids −1,77), mais certains sont légitimes, comme une même valeur mesurée deux jours de suite.

---

## Étage 6 — Attributs cliniques (hallucinations **contextuelle** et **temporelle**)

**Problème traité.** Une entité **présente dans le texte** mais **fausse cliniquement** :
- « **absence de** fièvre » extrait comme fièvre ;
- « **suspicion de** pneumopathie » extrait comme un diagnostic certain ;
- un **antécédent** ou un traitement de sortie pris pour un fait du séjour.

**Ce qu'il fait.** Il **annote** sans retirer :
- **négation** : un déclencheur (« pas de », « absence de », « sans », « éliminé »…) dans les 40 caractères qui précèdent,
  ou un marquage du modèle ;
- **hypothèse** : « suspicion de », « probable », « à discuter »… ;
- **temporalité**, déduite de la section : antérieur, séjour ou sortie ;
- **unités** des valeurs.

**Pourquoi c'est important.** C'est le type d'erreur que **l'ancrage ne voit pas** : le mot « fièvre » est bien dans le texte.

**Littérature.** NegEx (Chapman et al., 2001), ConText (Harkema et al., 2009), et leur adaptation au français
(Deléger et Grouin, 2012 : F-mesure de 0,867).

> **Question du jury :** « Pourquoi une fenêtre de 40 caractères ? »
> **Réponse :** C'est l'équivalent de la fenêtre de quelques mots de NegEx. Elle couvre « pas de X » et « absence de X »
> sans attraper une négation de la phrase précédente. La limite est connue : « arrêt du Lasilix » contient un mot de rupture
> mais reste un fait réel (voir l'étage 7).

---

## Étage 7 — Arbitrage (le **seul étage qui décide**)

**Rôle.** C'est le « jury » : il lit toutes les annotations des étages 2 à 6 et décide, pour chaque élément, de le garder,
de le retirer ou de lui attribuer un niveau de confiance.

### Mode standard : des règles fixées à l'avance

| Règle | Retire | Retraits | Part de justes parmi les retraits |
|---|---|---|---|
| E1 | entité non écrite mot pour mot dans sa page | 131 | 28 % |
| E2 | entité niée | 194 | 27 % |
| E3 | entité dont Mistral se dit peu sûr | 21 | 11 % |
| R2 | relation qui affirme une entité niée | — | — |
| R3 | relation créée par SGCE et non ancrée | — | — |
| Cascade | relations d'une entité retirée | 75 relations | — |

**Le critère de décision.** Un retrait est rentable si la part de justes parmi les éléments retirés est inférieure à environ
**F1 / 2 ≈ 36 %**. Les trois règles respectent ce seuil : **environ 3 retraits sur 4 sont des erreurs**.

**Résultat.** La précision des entités passe de 73,6 à **75,1 %**, le F1 de 72,3 à **72,65 %**, et H entités de 26,4 à **24,9 %**.
Les relations progressent aussi (précision 70,9 → 71,6 %).

**Confiance des relations.** Elle est calculée à partir de 7 signaux faibles :
- **HIGH** : aucun signal (3 070 relations) ;
- **MEDIUM** : un signal (640) ;
- **LOW** : deux signaux ou plus (82).

Rien n'est supprimé : le médecin voit simplement quelles relations vérifier.

### Mode précision : un score de fiabilité appris

**Comment il fonctionne.**
- Chaque élément est décrit par des **cases oui/non** : type, section, preuve, provenance, distance, mots, croisements.
  Il y en a environ 8 000 pour les entités et 4 600 pour les relations.
- Une **régression logistique** apprend un **poids** par case. Exemples :
  - biomarqueur avec un chiffre : **+1,60** ;
  - doublon : **−1,77** ;
  - traitement avec un chiffre : **−0,94** ;
  - provenance directe : **+0,86**.
- Le score obtenu va de 0 à 1. On garde les X % les mieux notés.
  Par exemple, « CRP à 86 » obtient 0,95 et est gardée ; « hyponatrémie hypotonique » obtient 0,10 et est retirée.
- **Validation croisée** : les poids sont appris sur les dossiers pairs pour noter les impairs, puis l'inverse. Aucun dossier
  n'est noté par un modèle qui l'a déjà vu.

**Résultat (validation croisée, en gardant 80 %).**
- Entités : précision **82,4 %**, H **25 → 17,6 %**.
- Relations : précision **77,0 %**, H **54 → 23 %** (par rapport à la sortie brute).
- Le rappel baisse : c'est un **curseur** entre précision et rappel, à régler selon l'usage.

**Pourquoi une régression logistique, et pas un LLM juge ou un réseau profond ?**
- Elle est **interprétable** : chaque poids a un sens clinique et se lit dans un tableau.
- Elle est **frugale** : 49 dossiers suffisent pour l'apprendre.
- Elle est **déterministe** : elle ne peut pas halluciner (Kamoi et al., 2024).

**Littérature.** Snorkel (Ratner et al., 2017) agrège des règles imparfaites en les pondérant. Chow (1970) et
Geifman et El-Yaniv (2017) formalisent la décision sélective : on s'abstient quand le risque est trop élevé.

> **Question du jury :** « Votre vote apprend sur le gold : ce n'est pas tricher ? »
> **Réponse :** Non, grâce à la validation croisée : un dossier n'est jamais noté par un modèle qui l'a vu. Le tableau de
> l'étage 8 évalué sur les documents d'entraînement donnerait 86 % de précision ; je ne retiens que le chiffre honnête, 82,4 %.
>
> **Question du jury :** « E2 retire des faits vrais ? »
> **Réponse :** Oui, environ 27 % de ses retraits. Par exemple, « arrêt Lasilix » est un fait réel retiré comme une négation.
> Je le présente comme une limite, et le critère montre que la règle reste globalement rentable.

---

## Étage 8 — Évaluation (le **seul étage qui lit le gold**)

**Ce qu'il fait.**
- **Appariement des entités**, page par page : même type, et nom exact, inclus (au moins 4 caractères) ou similaire (≥ 0,85).
- **Appariement des relations** : triplet sujet–relation–objet, avec les mêmes règles sur les deux extrémités.
- Un mauvais type compte comme **une erreur et un oubli** à la fois (FP + FN), ce qui est sévère mais honnête.
- **Métriques** : précision, rappel, F1 et taux d'hallucination, en micro (officielle), macro et strict. Elles sont **mesurées après chaque étage**,
  ce qui donne l'effet de chacun.
- **Validation croisée** à 2 plis pour le mode précision.

**Pourquoi mesurer après chaque étage.** C'est la preuve de l'architecture : on voit étage par étage ce que chacun apporte.

| Après l'étage | F1 entités | H entités | F1 relations | H relations |
|---|---|---|---|---|
| 1 Préparation | 71,97 | 26,2 % | 62,29 | 28,1 % |
| 2 Ancrage | 72,00 | 26,2 % | 62,36 | 27,8 % |
| 4 SGCE | 72,00 | 26,2 % | 62,40 | 28,1 % |
| 4b Récupération | 72,31 | 26,4 % | 62,65 | 29,1 % |
| 7 Standard | **72,65** | **24,9 %** | 62,58 | 28,4 % |
| 7 Précision 80 % (validation croisée) | 71,28 | **17,6 %** | 58,14 | **23,0 %** |

---

## Les limites (à dire avant que le jury les dise)

1. **Le plafond d'un post-traitement.** Même un filtre parfait ne dépasse pas un F1 d'environ 81 % (entités), car TRACE
   ne peut pas retrouver ce que Mistral n'a jamais extrait (environ 3 500 entités du gold). Pour aller plus loin, il faut agir à l'extraction.
2. **Le compromis du mode précision.** Moins d'hallucinations se paie en rappel. C'est un choix d'usage, assumé.
3. **Les hallucinations non couvertes.** L'erreur de **raisonnement** clinique n'est pas traitée (perspective). L'erreur
   **visuelle** n'est couverte qu'indirectement, quand la valeur mal lue n'est pas dans le texte.
4. **Une seule annotatrice.** Il n'y a pas d'accord inter-annotateurs. La validation médicale du guideline par le Pr Heming limite ce biais.
5. **La taille du corpus.** 43 à 49 dossiers d'un seul centre : les poids du vote devront être confirmés sur d'autres données.

## Ta contribution, en une phrase pour la conclusion

> « TRACE montre qu'on peut réduire fortement les hallucinations d'un MLLM extracteur sans LLM juge, en séparant la
> vérification en étages spécialisés qui annotent, puis en confiant la décision à un arbitre unique, interprétable et
> validé sans fuite de la référence : les hallucinations d'entités passent de 25 % à 18 %, et celles des relations de
> 54 % à 23 %. »
