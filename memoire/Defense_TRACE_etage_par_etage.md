# TRACE, étage par étage : ce qu'il faut savoir pour défendre l'architecture

---

## 0. L'idée en trois phrases (à savoir par cœur)

1. **Le problème.** Mistral Small 4 lit des dossiers médicaux scannés et en extrait un graphe de connaissances. Une part
   importante de ce qu'il produit est fausse : des entités et surtout des relations que le dossier ne justifie pas.
2. **La solution.** TRACE est une chaîne de contrôles **après l'extraction**. Chaque étage traite **un seul type
   d'hallucination**, le **texte du dossier est la seule référence**, et **aucun LLM ne sert de juge**.
3. **Le résultat.** En mode standard, TRACE améliore la qualité du graphe sans rien sacrifier. En mode précision, il réduit
   fortement les hallucinations, au prix d'une partie du rappel. Chaque retrait est **explicable** : on sait quel étage l'a
   décidé et pourquoi.

## Les 7 principes (ce qui rend l'architecture défendable)

| Principe | Pourquoi |
|---|---|
| Le texte source est la seule référence | En extraction, l'erreur grave est le manque de **fidélité** au dossier, pas l'erreur sur des connaissances générales (Huang et al.) |
| Pas de LLM juge | Un LLM ne se corrige pas de façon fiable sans retour extérieur (Kamoi et al. ; Huang J. et al.) |
| Une responsabilité par étage | Chaque gain ou perte peut être attribué à un étage, ce qui permet les ablations |
| Annoter avant de décider | Les étages intermédiaires ajoutent de l'information ; un seul étage tranche, avec tout en main |
| Un seul étage décide | Pas de conflits entre étages, pas de suppressions incontrôlées |
| Un seul étage lit le gold | Aucune règle n'est réglée sur la référence, donc l'évaluation reste honnête |
| Validation croisée | Un réglage n'est retenu que s'il améliore deux moitiés indépendantes du corpus |

## Vue d'ensemble

```
PDF scanné
  │ 0  Extraction Mistral (image → texte → entités → relations)
  │ 0b Seconde passe et filtre (rappel)
  │ 1  Préparation (nettoyage, identifiants)
  │ 2  Ancrage dans le texte ............ hallucination FACTUELLE
  │ 3  Ontologie (signatures) ........... hallucination ONTOLOGIQUE
  │ 4  SGCE (réparation de la forme) .... hallucination STRUCTURELLE
  │ 4b Récupération ciblée (rappel)
  │ 5  Dédoublonnage .................... STRUCTURELLE (doublons)
  │ 6  Attributs cliniques .............. CONTEXTUELLE et TEMPORELLE
  │ 7  Arbitrage (seul étage qui décide)
  ▼ 8  Évaluation (seul étage qui lit le gold)
Graphe de connaissances, avec un niveau de confiance pour chaque élément
```

---

## Étage 0 — Extraction par Mistral Small 4

**Ce qu'il fait.** Chaque page est convertie en image haute résolution. Mistral **lit directement l'image**, sans OCR
intermédiaire, puis produit successivement la transcription, les entités et les relations, au format JSON. Les consignes
données au modèle sont construites **uniquement à partir du guideline**.

**Pourquoi ce choix.**
- Les MLLM lisent mieux que les OCR classiques des documents cliniques bruités (Neveditsin et al.).
- Leur lecture se dégrade quand la résolution baisse (Inoue), d'où une conversion en haute résolution.
- Une température nulle rend les réponses reproductibles.

**Ce qu'il ne fait pas.** Il ne corrige rien : c'est la sortie **brute**, avec ses hallucinations. Tout le reste de TRACE part de là.

**Point d'honnêteté à mettre en avant.** L'ancien moteur contenait des règles construites en regardant la référence. La
nouvelle extraction n'en contient **aucune** : c'est une extraction brute honnête.

> **Question du jury :** « Pourquoi ne pas faire un OCR, puis un LLM sur le texte ? »
> **Réponse :** Les dossiers contiennent du manuscrit, des tampons et des photocopies. Un OCR y fait des erreurs qui se
> propagent ensuite au graphe. Le MLLM lit mieux, mais il hallucine : c'est précisément ce que TRACE contrôle.

---

## Étage 0b — Seconde passe et filtre (rappel)

**Problème traité.** Les **oublis** : Mistral ne trouve pas tout.

**Ce qu'il fait.**
- On remontre à Mistral la page et ce qu'il a déjà trouvé, et on lui demande ce qui manque.
- La demande est répétée plusieurs fois, et un élément n'est gardé que s'il revient **majoritairement**.
- Une entité n'est acceptée que si sa preuve est écrite mot pour mot dans la page.

**Ce que la mesure a montré.** Sans filtre, la seconde passe ajoute surtout du faux, en particulier des relations : elle
**dégrade** la qualité. Le filtre ne garde donc que :
- les entités de types fiables, votées à l'unanimité et non niées ;
- les entités confirmées par une seconde passe indépendante ;
- **aucune relation ajoutée**.

**Littérature.** C'est le principe de la *self-consistency* (Wang et al.) et de SelfCheckGPT (Manakul et al.) : une
information que le modèle connaît vraiment revient d'un essai à l'autre.

> **Question du jury :** « Demander à un LLM ce qu'il a oublié, ça ne crée pas d'hallucinations ? »
> **Réponse :** Si, et je l'ai mesuré : la plupart des relations ajoutées étaient fausses. C'est pourquoi je les retire
> toutes et ne garde que les entités confirmées par le vote et par le texte. Je ne fais pas confiance au LLM pour se
> corriger lui-même.

---

## Étage 1 — Préparation

**Ce qu'il fait.**
- Il retire les relations produites par l'ancien post-traitement, dont les règles avaient été construites en regardant la référence.
- Il normalise l'écriture (caractères Unicode équivalents, par exemple deux « µ » différents).
- Il donne un identifiant unique à chaque élément.

**Pourquoi.** C'est un étage d'**honnêteté expérimentale**. Garder des règles réglées sur la référence gonflerait
artificiellement les scores. Les retirer fait baisser les chiffres, mais rend l'évaluation valide.

> **Question du jury :** « Pourquoi retirer des relations qui étaient peut-être justes ? »
> **Réponse :** Parce qu'elles venaient de règles écrites en regardant la réponse. Une évaluation honnête exige
> qu'aucune étape ne soit réglée sur la référence. Seul l'étage 8 la lit.

---

## Étage 2 — Ancrage documentaire (hallucination **factuelle**)

**Problème traité.** Le modèle **invente** une entité ou une relation absente du dossier.

**Ce qu'il fait.**
- **Pour chaque entité**, il vérifie :
  - qu'elle est présente dans le document, soit à l'identique, soit avec l'essentiel de ses mots et **tous ses nombres** ;
  - qu'elle est écrite **mot pour mot** dans sa page.
- **Pour chaque relation**, il évalue :
  - la **preuve** citée : attestée, inventée ou absente ;
  - la **distance** entre les deux entités : même ligne, même paragraphe ou éloignées ;
  - la **section** du dossier où elle apparaît.
- Il ne **retire que l'impossible** :
  - une entité absente de tout le document ;
  - une relation dont une extrémité est absente du texte ;
  - une preuve inventée ;
  - deux entités qui ne sont jamais proches l'une de l'autre.
- Tout le reste est **annoté**, pas supprimé.

**Exemple.** Le modèle produit « CRP à 186 » alors que la page indique « CRP 86 ». Le nombre n'est pas dans le texte,
donc l'entité n'est pas ancrée.

**Pourquoi exiger tous les nombres.** En médecine, l'erreur la plus dangereuse est un chiffre faux : une valeur
biologique ou une posologie.

**Littérature.** C'est la fidélité à la source (Ji et al. ; Huang et al.). RAPTOR+ appelle cet échec les « extractions non ancrées ».

> **Question du jury :** « Pourquoi ne pas tout retirer dès qu'un élément n'est pas mot pour mot ? »
> **Réponse :** Parce que le modèle reformule souvent correctement : il développe une abréviation, accorde un mot.
> Retirer à ce stade ferait perdre du juste. L'étage 2 ne retire que l'impossible ; le reste est tranché à l'étage 7,
> où j'ai vérifié que la majorité des retraits sont bien des erreurs.

---

## Étage 3 — Validation ontologique (hallucination **ontologique**)

**Problème traité.** Une relation **interdite par le schéma** : par exemple, une relation prévue entre un traitement et
un micro-organisme, mais posée sur un symptôme.

**Ce qu'il fait.** Il compare chaque relation aux **signatures** du guideline, c'est-à-dire au type de sujet et au type
d'objet autorisés. Chaque relation est déclarée conforme, ou en violation de domaine ou d'image.

**Il ne retire rien, et c'est voulu.** La vérification à la main a montré que, dans la majorité des cas, la relation
était juste : c'est le **type d'une entité** qui était faux, pas le lien. Supprimer la relation ferait perdre une
information correcte. La violation devient donc **un indice** :
- pour SGCE, qui peut retyper l'entité ;
- pour le vote de l'étage 7.

**Littérature.** Validation par contraintes (SHACL) ; LLM et programmation logique (Tran et al.). Leur limite commune :
un graphe valide n'est pas forcément fidèle au document.

> **Question du jury :** « Une relation hors schéma, c'est forcément une erreur, non ? »
> **Réponse :** C'est une erreur de **forme**, mais le fond est souvent juste. Mieux vaut réparer le type que
> supprimer le lien.

---

## Étage 4 — SGCE (hallucination **structurelle**)

**Problème traité.** Un graphe **mal formé** :
- des entités qui regroupent deux concepts ;
- des entités intermédiaires manquantes ;
- un lien extrait comme une entité ;
- des violations de signature ;
- des relations orphelines.

**Ce qu'il fait.** SGCE applique des **motifs d'erreur typés** :

| Motif | Erreur | Réparation |
|---|---|---|
| A | Entité composite, par exemple « Augmentin 1 g × 3 » | Découper en traitement et posologie, puis les relier |
| B1 | Relation pointant vers une référence absente | Rattacher, ou créer l'entité si le texte la contient |
| B2 | Nœud intermédiaire manquant | Le créer à partir du texte |
| C | Lien extrait comme une entité | Le réécrire en relation |
| D | Violation de signature | Retyper ou rediriger |
| Relation Repair / Orphan Resolution | Relation mal typée, entité isolée | Corriger ou rattacher |
| Multi-agent | Cas ambigus | Agents **déterministes** et vote par consensus ; sinon **abstention** |

Chaque correction suit le cycle **détection, validation, correction, post-validation**. Une correction n'est conservée
que si la structure s'améliore.

**Ce qu'il apporte.** Le graphe devient plus connexe et plus conforme au schéma, **sans dégrader** la qualité des
éléments extraits.

**Comment le présenter.** SGCE répare la **forme**, pas le fond. Son rôle n'est pas de réduire les hallucinations
factuelles, mais de rendre le graphe **exploitable** (requêtes, raisonnement).

**Littérature.** Raffinement de graphes (Paulheim) ; réparation minimale sous contraintes (Chu et al., HoloClean) ;
abstention (Geifman et El-Yaniv).

> **Question du jury :** « SGCE change peu le F1, à quoi sert-il ? »
> **Réponse :** Le F1 juge les éléments un par un ; il ne voit pas qu'un graphe est éclaté en morceaux isolés. Or un
> graphe clinique doit être **connexe et conforme** pour être interrogé. SGCE apporte cela sans aucune perte.

---

## Étage 4b — Récupération ciblée (rappel sans risque)

**Problème traité.** Les oublis dans les **blocs à forme fixe**, que le modèle saute souvent.

**Ce qu'il fait.** Il **copie le texte de la page** et n'invente jamais rien :
- **B1** : une ligne de biologie (« libellé, valeur, normes, unité ») devient un biomarqueur. Une liste d'exclusion écarte
  les valeurs témoins du laboratoire et les réglages du ventilateur.
- **B2** : une ligne d'ordonnance devient un traitement et une posologie.
- **B3** : sur cette même ligne, il crée la relation entre le traitement et sa posologie.
- **B4**, qui reliait chaque traitement au patient, a été **testé puis écarté**, car il ajoutait trop d'erreurs.

**Ce qu'il apporte.** Du rappel, avec très peu de risque, puisque tout est copié du texte.

> **Question du jury :** « Des règles écrites à la main, ce n'est pas du sur-mesure sur votre corpus ? »
> **Réponse :** Elles décrivent un **format** (une ligne de biologie, une ligne d'ordonnance), pas des réponses de la
> référence. Et j'ai écarté B4 parce qu'il n'était pas utile : une règle n'est gardée que si la mesure le justifie.

---

## Étage 5 — Dédoublonnage (structurelle)

**Ce qu'il fait.**
- Il fusionne les entités strictement identiques et reporte leurs relations.
- Il retire les relations strictement identiques.
- Il **annote** les répétitions d'un même fait sous des identifiants différents, sans les retirer.

**Pourquoi seulement annoter les répétitions.** Une répétition est un **indice**. Le vote apprend qu'un doublon est
souvent faux, mais certains sont légitimes, comme une même valeur mesurée deux jours de suite.

---

## Étage 6 — Attributs cliniques (hallucinations **contextuelle** et **temporelle**)

**Problème traité.** Une entité **présente dans le texte**, mais **fausse cliniquement** :
- « **absence de** fièvre » extrait comme une fièvre ;
- « **suspicion de** pneumopathie » extrait comme un diagnostic certain ;
- un **antécédent** ou un traitement de sortie pris pour un fait du séjour.

**Ce qu'il fait.** Il **annote** sans retirer :
- la **négation** : un mot déclencheur (« pas de », « absence de », « sans », « éliminé »…) juste avant la mention ;
- l'**hypothèse** : « suspicion de », « probable », « à discuter »… ;
- la **temporalité**, déduite de la section : antérieur, séjour ou sortie ;
- les **unités** des valeurs.

**Pourquoi c'est important.** C'est l'erreur que **l'ancrage ne voit pas** : le mot « fièvre » est bien écrit dans le texte.

**Littérature.** NegEx (Chapman et al.), ConText (Harkema et al.) et leur adaptation au français (Deléger et Grouin).

> **Question du jury :** « Comment fixez-vous la portée de la négation ? »
> **Réponse :** Comme NegEx, par une courte fenêtre avant la mention. Elle couvre « pas de X » sans attraper la négation
> d'une autre phrase. La limite est connue : « arrêt du Lasilix » ressemble à une négation, alors que c'est un fait
> réel (voir l'étage 7).

---

## Étage 7 — Arbitrage (le **seul étage qui décide**)

**Rôle.** C'est le « jury ». Il lit toutes les annotations des étages précédents et décide, pour chaque élément, de le
garder, de le retirer ou de lui attribuer un niveau de confiance.

### Mode standard : des règles fixées à l'avance

| Règle | Retire |
|---|---|
| E1 | une entité qui n'est pas écrite mot pour mot dans sa page |
| E2 | une entité niée |
| E3 | une entité dont le modèle lui-même se dit peu sûr |
| R2 | une relation qui affirme une entité niée |
| R3 | une relation créée par SGCE qui n'est pas ancrée |
| Cascade | les relations d'une entité retirée |

**Le critère de décision.** Un retrait n'est rentable que s'il enlève **nettement plus de faux que de vrai**. J'ai
vérifié que chaque règle respecte ce critère : **la grande majorité des retraits sont des erreurs**.

**La confiance des relations.** On compte des signaux faibles et on attribue un niveau **élevé**, **moyen** ou **faible**.
Rien n'est supprimé : le médecin voit simplement quelles relations vérifier en priorité.

### Mode précision : un score de fiabilité appris

**Comment il fonctionne.**
- Chaque élément est décrit par des **cases oui/non** : type, section, preuve, provenance, proximité, mots, croisements de ces critères.
- Une **régression logistique** apprend un **poids** pour chaque case. Par exemple :
  - un biomarqueur accompagné d'un chiffre est très fiable ;
  - un doublon est suspect ;
  - un élément issu de la lecture directe est plus fiable qu'un élément inféré.
- On obtient un score de fiabilité entre 0 et 1, et on garde la part des éléments la mieux notée. C'est un **curseur**
  entre précision et rappel, à régler selon l'usage.
- **Validation croisée** : le modèle apprend sur une moitié des dossiers et note l'autre, puis l'inverse. Aucun dossier
  n'est noté par un modèle qui l'a vu.

**Pourquoi une régression logistique, et pas un LLM juge ou un réseau profond ?**
- **Interprétable** : chaque poids a un sens clinique et peut être montré.
- **Frugale** : elle s'apprend sur un petit corpus.
- **Déterministe** : elle ne peut pas halluciner à son tour (Kamoi et al.).

**Littérature.** Snorkel (Ratner et al.) pour l'agrégation pondérée de règles imparfaites ; Chow, puis Geifman et
El-Yaniv, pour la décision sélective (s'abstenir quand le risque est trop élevé).

> **Question du jury :** « Votre vote apprend sur la référence : ce n'est pas tricher ? »
> **Réponse :** Non, grâce à la validation croisée : un dossier n'est jamais noté par un modèle qui l'a vu. Je ne retiens
> que le résultat obtenu sur les dossiers non vus, même s'il est moins flatteur.
>
> **Question du jury :** « E2 retire des faits vrais ? »
> **Réponse :** Parfois, par exemple « arrêt Lasilix ». Je le présente comme une limite. La règle reste rentable, car
> elle enlève beaucoup plus de faux que de vrai.

---

## Étage 8 — Évaluation (le **seul étage qui lit la référence**)

**Ce qu'il fait.**
- Il apparie les entités page par page : même type, et texte identique, inclus ou très proche.
- Il apparie les relations comme des triplets sujet–relation–objet.
- Un mauvais type compte à la fois comme **une erreur et un oubli**, ce qui est sévère mais honnête.
- Il calcule la précision, le rappel, le F1 et le taux d'hallucination **après chaque étage**.
- Il applique une validation croisée au mode précision.

**Pourquoi mesurer après chaque étage.** C'est la preuve de l'architecture : on voit ce que chaque étage apporte, et
qu'aucun ne dégrade le résultat.

---

## Les limites (à dire avant que le jury les dise)

1. **Le plafond d'un post-traitement.** TRACE ne peut pas retrouver ce que le modèle n'a jamais extrait. Pour aller
   plus loin, il faut agir sur l'extraction elle-même.
2. **Le compromis du mode précision.** Moins d'hallucinations se paie en rappel. C'est un choix d'usage, assumé.
3. **Des hallucinations non couvertes.** Les erreurs de **raisonnement** clinique ne sont pas traitées (perspective).
   Les erreurs **visuelles** ne le sont qu'indirectement, quand la valeur mal lue n'apparaît pas dans le texte.
4. **Une seule annotatrice.** Il n'y a pas d'accord inter-annotateurs ; la validation médicale du guideline limite ce biais.
5. **Un corpus restreint et monocentrique.** Les poids appris devront être confirmés sur d'autres données.

## Ta contribution, en une phrase pour la conclusion

> « TRACE montre qu'on peut réduire fortement les hallucinations d'un modèle multimodal extracteur sans recourir à un
> LLM juge, en séparant la vérification en étages spécialisés qui annotent, puis en confiant la décision à un arbitre
> unique, interprétable et validé sans fuite de la référence. »
