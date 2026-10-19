# État de l'art — SGCE : correction structurelle sélective des graphes extraits par un LLM

> Document de travail pour le mémoire TRACE-Sepsis (IHU PROMETHEUS, WP6).
> Toutes les références de la bibliographie sont réelles. Les chiffres de la section 8
> proviennent de `TRACE_v2/sorties/08_evaluation/tableau.csv` (43 documents, matching souple).
> **À compléter** : développer le sigle SGCE de façon cohérente avec ses lettres
> (par exemple « Structural Grounding for Clinical Extraction »).

---

## 1. Ce qu'est SGCE (périmètre exact)

SGCE est l'étage 4 de TRACE. Il reçoit le graphe d'entités et de relations produit par
Mistral Small 4 à partir des dossiers numérisés, avec la **transcription textuelle** de
chaque document, et il en **répare la forme** sans relire les images. SGCE ne décide
pas si une information est vraie : il rend le graphe conforme au schéma TRACE-Sepsis,
sans inventer d'information absente du texte.

Il enchaîne quatre familles de motifs d'erreur (*patterns*), deux réparateurs et un
second recours multi-agent :

| Composant | Motif d'erreur traité | Correction type |
|---|---|---|
| **Pattern A** (A1–A6) | **entité composite** : deux concepts fusionnés en une mention (A1 traitement + posologie, A2 comorbidité + contexte d'acquisition, A3 à A5 imagerie + foyer, défaillance ou comorbidité, A6 patient + symptôme) | découper la mention et relier les parties |
| **Pattern B1** | **extrémité non résolue** : une relation pointe vers une référence absente | rattacher à l'entité existante, ou créer l'entité si le texte la contient |
| **Pattern B2** | **entité intermédiaire manquante** : la relation saute un nœud exigé par le schéma | créer le nœud intermédiaire, ancré dans le texte |
| **Pattern C** | **relation réifiée** : un lien a été extrait comme une *entité* | le réécrire comme une relation autorisée |
| **Pattern D** (D1, D2) | **violation de signature** : le type de la source ou de la cible ne correspond pas au domaine ou à l'image de la relation | retyper l'extrémité ou rediriger la relation |
| **Relation Repair** | relation mal typée ou mal orientée | corriger le type ou le sens |
| **Orphan Resolution** | entité isolée du graphe | la rattacher si le texte justifie un lien |
| **Multi-agent** | cas qu'un pattern a détectés sans pouvoir choisir une correction unique et sûre | agents A, B, C, D et Patient/Référence, **déterministes** ; consensus de trois votes (preuve documentaire, structure ontologique, cohérence clinique) ; sinon abstention (UNRESOLVED) |

Chaque composant suit le même cycle : **détection → validation → correction → post-validation**.
Un détecteur ne modifie rien. Une correction n'est appliquée que si le validateur
l'accepte, et SGCE s'arrête si un post-validateur échoue ou si un document est perdu.

Cette description fixe ce qu'il faut comparer à la littérature : SGCE est une
**réparation de graphe sous contraintes d'ontologie, guidée par des motifs, ancrée dans
le texte source, avec abstention**. Ce n'est ni un détecteur général d'hallucinations,
ni un modèle multimodal.

---

## 2. Axe 1 — Hallucinations des LLM : pourquoi une correction *externe* au modèle

**Définitions.** Ji et al. (2023) distinguent l'hallucination *intrinsèque* (contredite
par la source) de l'hallucination *extrinsèque* (invérifiable dans la source). Huang
et al. (2025) opposent les erreurs de *factualité* aux erreurs de *fidélité* au
contexte fourni. En extraction documentaire, c'est la **fidélité** qui compte : une
entité vraie en médecine mais absente du dossier reste une erreur.

**Détection.** On distingue quatre familles d'approches :
- **cohérence entre plusieurs générations** : SelfCheckGPT (Manakul et al., 2023),
  self-consistency (Wang et al., 2023) ;
- **décomposition en faits atomiques vérifiés un à un** : FActScore (Min et al., 2023) ;
- **vérification par récupération de documents** : RAG (Lewis et al., 2020), Self-RAG
  (Asai et al., 2024) ;
- **estimation de la confiance du modèle** (Kadavath et al., 2022).

Dans le domaine médical, Med-HALT (Pal et al., 2023) montre que les LLM hallucinent
aussi sur des tâches cliniques.

**Correction par le modèle lui-même.** Self-Refine (Madaan et al., 2023) et
Chain-of-Verification (Dhuliawala et al., 2024) font relire au modèle sa propre sortie.
Ces gains sont toutefois contestés :
- Huang, J. et al. (2024) montrent qu'un LLM **ne corrige pas son raisonnement sans
  retour extérieur** ;
- la revue critique de Kamoi et al. (2024) conclut que l'auto-correction n'est fiable
  que si le **retour provient d'une source extérieure fiable**, ou après un
  affinage à grande échelle.

**Conséquence pour SGCE.** C'est le premier argument du positionnement. SGCE ne demande
jamais au LLM de se juger. Ses retours viennent de **deux sources extérieures et
vérifiables** : le texte du dossier et les signatures de l'ontologie. Ses agents sont
déterministes, et ne peuvent donc pas halluciner à leur tour.

---

## 3. Axe 2 — Extraction clinique et construction de graphes par LLM

**Extraction clinique classique.** Les campagnes i2b2 (Uzuner et al., 2011) et les
systèmes comme cTAKES (Savova et al., 2010) ont fixé la tâche : repérer les problèmes,
examens et traitements, puis leurs relations. La revue systématique de Fraile Navarro
et al. (2023) couvre 94 études : 68 utilisent l'apprentissage automatique, 5 des règles,
22 les deux. Seules 3 rapportent un usage hors expérimentation. **La fiabilité en
conditions réelles reste donc le point faible du domaine.**

**Extraction par LLM.** Agrawal et al. (2022) montrent que les LLM sont de bons
extracteurs cliniques en *few-shot*, mais leurs sorties doivent être contrôlées. Pour la
construction de graphes de connaissances, Pan et al. (2024) et Zhu et al. (2024)
décrivent le LLM comme un générateur de triplets puissant mais **non contraint** :
types inventés, relations hors schéma, entités composites.

**Documents numérisés.** LayoutLM (Xu et al., 2020), LayoutLMv3 (Huang, Y. et al.,
2022) et Donut (Kim et al., 2022) exploitent ensemble la mise en page et le texte. Une
bonne lecture multimodale ne garantit pourtant pas une représentation structurée
correcte : les erreurs que traite SGCE (composites, liens réifiés, types inversés)
apparaissent **après** la lecture, au moment de structurer.

**Conséquence pour SGCE.** SGCE se place **en aval** de l'extraction multimodale de
l'étage 0. Il ne réentraîne pas le modèle et ne regarde pas l'image : il corrige la
sortie structurée et utilise la transcription comme preuve.

---

## 4. Axe 3 — Validation structurelle par contraintes

**Contraintes déclaratives.** SHACL (Knublauch & Kontokostas, 2017) vérifie qu'un graphe
RDF respecte des formes : types, propriétés autorisées, cardinalités. Le résultat est
un **rapport de violations**. Les ontologies biomédicales comme l'UMLS (Bodenreider,
2004) fournissent le vocabulaire et les types.

**Contraintes à la génération.** On peut aussi contraindre le décodage du LLM par une
grammaire (Geng et al., 2023). Cela garantit une sortie bien formée (JSON valide,
étiquettes autorisées), mais pas des **liens** respectant les signatures domaine →
image, ni la fidélité au texte.

**Limite commune.** Un graphe peut respecter toutes les contraintes et contenir une
information fausse. SHACL **détecte** les violations sans les **réparer**.

**Conséquence pour SGCE.** L'étage 3 de TRACE joue le rôle d'un validateur de type
SHACL : il compare chaque relation aux signatures du guideline, 32 en v1.6 et 34 en
v1.7. Le Pattern D de SGCE va plus loin et **répare** les violations (D1 sur la source,
D2 sur la cible). La fidélité, elle, est vérifiée ailleurs (étages 2 et 7).

---

## 5. Axe 4 — Réparation de graphes et de données (fondement le plus direct)

**Raffinement de graphes de connaissances.** Paulheim (2017) distingue la *complétion*
(ajouter ce qui manque) de la *détection et correction d'erreurs* (retyper, retirer)
dans un graphe déjà construit. SGCE relève des deux : B1, B2 et Orphan Resolution
complètent, tandis que A, C, D et Relation Repair corrigent.

**Nettoyage de données par contraintes.** En bases de données, la réparation consiste à
trouver la **modification minimale** qui fait disparaître les violations de
contraintes :
- les dépendances fonctionnelles pour graphes (Fan, Wu & Xu, 2016) ;
- le nettoyage holistique, qui considère toutes les violations ensemble (Chu, Ilyas &
  Papotti, 2013) ;
- HoloClean (Rekatsinas et al., 2017), qui combine contraintes et inférence
  probabiliste.

SGCE adopte la même logique de réparation minimale : retyper une extrémité plutôt que
supprimer la relation, découper plutôt que recréer.

**Motifs de modélisation.** Les *Ontology Design Patterns* (Gangemi, 2005) codifient
des solutions types à des problèmes de modélisation récurrents. Les patterns de SGCE en
sont le pendant **correctif** : chacun associe un motif d'erreur typique à une réparation
type.
- Le **Pattern B2** (nœud intermédiaire manquant) et le **Pattern C** (relation
  extraite comme entité) correspondent au problème des relations *n*-aires et de la
  *réification* décrit par Noy & Rector (2006) : quand faut-il représenter un lien
  par un nœud, et quand par une arête ?

**Conséquence pour SGCE.** C'est l'axe où SGCE s'inscrit le plus clairement. Sa
différence est le **domaine d'application** : les méthodes de réparation travaillent
sur des données tabulaires ou des graphes déjà établis, alors que SGCE répare la sortie
d'un **générateur probabiliste**. Une correction n'y est donc admise **que si le texte
source la justifie**.

---

## 6. Axe 5 — Correction sélective, abstention et décision à plusieurs avis

**Abstention.** Chow (1970) formalise le compromis entre erreur et rejet : mieux vaut
s'abstenir que décider quand le risque est trop élevé. Geifman & El-Yaniv (2017)
transposent ce principe aux réseaux profonds avec la *prédiction sélective* : on fixe
un niveau de risque, et le modèle ne répond que lorsqu'il le respecte.

**Plusieurs avis.** Le débat multi-agents (Du et al., 2024) améliore la factualité en
confrontant plusieurs LLM. La supervision faible (Ratner et al., 2017) agrège plusieurs
sources d'étiquetage imparfaites. Les approches neuro-symboliques (Garcez & Lamb, 2023)
font travailler ensemble un modèle neuronal et un raisonnement symbolique explicite.

**Conséquence pour SGCE.** Le multi-agent de SGCE applique ces principes à la
correction :
- le **symbolique tranche d'abord**, et seuls les cas ambigus sont transmis ;
- trois votes indépendants (preuve documentaire, structure ontologique, cohérence
  clinique) ;
- correction seulement avec 3 votes sur 3, ou 2 sur 3 sans veto et avec une preuve ;
- **abstention** dans tous les autres cas.

À la différence de Du et al., les agents sont déterministes. C'est un choix délibéré au
regard de Kamoi et al. (2024) : un agent LLM pourrait réintroduire une hallucination au
moment même de la corriger.

---

## 7. Axe 6 — Contexte clinique : à qui se rapporte l'information ?

NegEx (Chapman et al., 2001) et ConText (Harkema et al., 2009) qualifient chaque mention
clinique par sa **négation**, sa **temporalité** et son **sujet** (*experiencer*) :
le patient ou un tiers. Dans un dossier, une phrase comme « lactate > 2 mmol/L
définit le choc septique » est une **connaissance générale**, pas une mesure du patient.

**Conséquence pour SGCE.** L'agent Patient/Référence transpose l'attribut *experiencer*
de ConText. Ses indices patient sont « chez le patient », « admis », « présente » ; ses
indices référence, « définition », « seuil », « critère », « selon ». En cas
d'ambiguïté, il s'abstient. La négation et la temporalité sont traitées à l'étage 6 de
TRACE, sur le modèle de NegEx et ConText.

---

## 8. Synthèse et positionnement

### 8.1 Tableau de positionnement

| Approche | Ce qu'elle apporte | Ce qui manque pour le problème de TRACE | Ce que SGCE en reprend |
|---|---|---|---|
| Détection d'hallucinations (SelfCheckGPT, FActScore) | repère les affirmations non étayées | détecte sans réparer ; ne connaît pas le schéma | — (rôle des étages 2 et 7) |
| Auto-correction par LLM (Self-Refine, CoVe) | correction sans annotation | peu fiable sans retour extérieur (Kamoi et al., 2024) | **rejetée** : les retours viennent du texte et de l'ontologie |
| Décodage contraint | sortie bien formée | ne garantit pas les signatures ni la fidélité | — |
| SHACL, validation par ontologie | détection explicite des violations | ne répare pas ; validité ≠ fidélité | les signatures domaine → image (étage 3, Pattern D) |
| Réparation de données (Fan, Chu, HoloClean) | modification minimale sous contraintes | conçue pour des données établies, sans preuve textuelle | la réparation minimale guidée par les contraintes |
| Raffinement de graphes (Paulheim) | complétion et correction d'un graphe existant | méthodes génériques, sans motifs cliniques | la séparation complétion / correction |
| Patrons d'ontologie, relations *n*-aires (Gangemi ; Noy & Rector) | solutions types de modélisation | constructifs, pas correctifs | les patterns comme motifs d'erreur typés (A, B2, C) |
| Prédiction sélective (Chow ; Geifman & El-Yaniv) | décider ou s'abstenir | conçue pour la classification | l'abstention (UNRESOLVED) |
| Débat multi-agents (Du et al.) | plusieurs avis, consensus | agents LLM, eux-mêmes faillibles | le consensus, avec des agents **déterministes** |
| ConText | sujet, négation, temporalité | ne touche pas la structure du graphe | l'agent Patient/Référence |

### 8.2 Ce qui est original

Pris séparément, aucun de ces éléments n'est nouveau : règles, ontologie, réparation
minimale, agents et abstention existent déjà. La contribution défendable est leur
**politique de décision commune**, appliquée à la sortie d'un LLM sur des dossiers
cliniques :

1. **motifs d'erreur typés** propres à l'extraction de graphes par LLM (composites,
   extrémités non résolues, nœuds manquants, liens réifiés, signatures violées) ;
2. **chaque correction exige une preuve dans le texte source** : aucune entité créée
   pour « rendre le graphe cohérent » ;
3. **abstention explicite**, avec un second recours par consensus d'agents
   déterministes ;
4. **post-validation monotone** : une correction n'est conservée que si la structure
   s'améliore et qu'aucune nouvelle anomalie n'apparaît.

### 8.3 Questions de recherche (hypothèses à tester, pas des lacunes démontrées)

- **QR1 :** les corrections par motif améliorent-elles la structure du graphe **sans
  dégrader** la précision et le rappel ?
- **QR2 :** quelle est la part de corrections justes, **par pattern** ?
- **QR3 :** l'abstention et le multi-agent évitent-ils des corrections nuisibles par
  rapport à une application systématique ?

---

## 9. Ce que montrent déjà les mesures (TRACE v2, 43 documents)

Mêmes documents, avant et après SGCE (lignes `03_ontologie` et `04_sgce` du tableau de
l'étage 8) :

| | Avant SGCE | Après SGCE |
|---|---|---|
| Entités : P / R / F1 | 73,83 / 70,26 / 72,00 | 73,77 / 70,31 / 72,00 |
| Relations : P / R / F1 | 72,17 / 54,90 / 62,36 | 71,92 / 55,11 / 62,40 |
| Relations orphelines | 15 | **6** |
| Violations d'ontologie | 45 | **42** |
| Relations créées par SGCE | — | 29 |

**Lecture honnête.** SGCE **améliore la structure** (−60 % d'orphelines, −3 violations)
**sans dégrader** le F1. Il ne réduit pas, à lui seul, les hallucinations. Ce résultat
confirme le positionnement : SGCE est une **correction structurelle sélective**, et la
réduction des hallucinations relève des étages 2 (ancrage), 6 (attributs) et
7 (arbitrage).

**Réserves :**
- l'entrée de TRACE v2 a déjà été post-traitée ;
- sur l'extraction brute, le multi-agent n'a aucun cas à traiter et l'étage 4 est
  sauté ;
- les mesures sont à refaire sur l'extraction v1.7.

### Protocole d'évaluation proposé

| Mesure | Comment l'obtenir |
|---|---|
| P, R, F1 entités et relations, avant et après | lignes 03 et 04 du tableau de l'étage 8 (disponible) |
| Anomalies résolues et nouvelles | colonnes `struct_*` du même tableau (disponible) |
| Précision des corrections, par pattern | éléments marqués `_sgce_pattern` / `_sgce_operation`, comparés au gold |
| Taux d'abstention | cas UNRESOLVED du multi-agent |
| Ablation | SGCE complet, contre SGCE sans multi-agent, contre aucun SGCE |

Le gold reste indépendant de SGCE : aucune règle n'est tirée de l'annotation.

---

## 10. Formulation proposée pour le mémoire

> Les travaux sur la fiabilité des LLM proposent de détecter les hallucinations
> (cohérence entre générations, vérification de faits atomiques, recherche documentaire)
> ou de les corriger par auto-révision. Ces corrections restent toutefois peu fiables
> sans retour extérieur (Kamoi et al., 2024). De leur côté, la validation par contraintes
> (SHACL) détecte les violations d'un schéma sans les réparer, et un graphe valide peut
> rester infidèle au document. Les méthodes de réparation de données (Chu et al., 2013 ;
> Fan et al., 2016 ; Rekatsinas et al., 2017) et de raffinement de graphes
> (Paulheim, 2017) cherchent la modification minimale qui rétablit la cohérence, mais
> elles visent des données établies, sans preuve textuelle.
>
> SGCE transpose ces principes à la sortie d'un LLM extrayant un graphe clinique. Il
> détecte des motifs d'erreur typés (entités composites, extrémités non résolues, nœuds
> intermédiaires manquants, relations réifiées, violations de signature) et applique à
> chacun une réparation minimale conditionnée à une preuve dans le texte source. Les cas
> ambigus sont soumis à des agents déterministes dont la décision exige un consensus ; à
> défaut, SGCE s'abstient (Geifman & El-Yaniv, 2017). Sur 43 dossiers, SGCE réduit de
> 15 à 6 les relations orphelines et de 45 à 42 les violations d'ontologie, sans
> dégrader la précision ni le rappel. Il s'agit donc d'une méthode de correction
> structurelle sélective, complémentaire des étages de TRACE dédiés à la réduction des
> hallucinations.

---

## Bibliographie

**Hallucinations et auto-correction**
- Asai, A., Wu, Z., Wang, Y., Sil, A. & Hajishirzi, H. (2024). Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection. *ICLR 2024*.
- Dhuliawala, S. et al. (2024). Chain-of-Verification Reduces Hallucination in Large Language Models. *Findings of ACL 2024*.
- Du, Y., Li, S., Torralba, A., Tenenbaum, J. B. & Mordatch, I. (2024). Improving Factuality and Reasoning in Language Models through Multiagent Debate. *ICML 2024*.
- Huang, J. et al. (2024). Large Language Models Cannot Self-Correct Reasoning Yet. *ICLR 2024*.
- Huang, L. et al. (2025). A Survey on Hallucination in Large Language Models: Principles, Taxonomy, Challenges, and Open Questions. *ACM Transactions on Information Systems*, 43(2).
- Ji, Z. et al. (2023). Survey of Hallucination in Natural Language Generation. *ACM Computing Surveys*, 55(12).
- Kadavath, S. et al. (2022). Language Models (Mostly) Know What They Know. *arXiv:2207.05221*.
- Kamoi, R., Zhang, Y., Zhang, N., Han, J. & Zhang, R. (2024). When Can LLMs Actually Correct Their Own Mistakes? A Critical Survey of Self-Correction of LLMs. *Transactions of the ACL*, 12, 1417–1440.
- Lewis, P. et al. (2020). Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. *NeurIPS 2020*.
- Madaan, A. et al. (2023). Self-Refine: Iterative Refinement with Self-Feedback. *NeurIPS 2023*.
- Manakul, P., Liusie, A. & Gales, M. (2023). SelfCheckGPT: Zero-Resource Black-Box Hallucination Detection for Generative Large Language Models. *EMNLP 2023*.
- Min, S. et al. (2023). FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation. *EMNLP 2023*.
- Pal, A., Umapathi, L. K. & Sankarasubbu, M. (2023). Med-HALT: Medical Domain Hallucination Test for Large Language Models. *CoNLL 2023*.
- Wang, X. et al. (2023). Self-Consistency Improves Chain of Thought Reasoning in Language Models. *ICLR 2023*.

**Extraction clinique, documents, graphes par LLM**
- Agrawal, M., Hegselmann, S., Lang, H., Kim, Y. & Sontag, D. (2022). Large Language Models are Few-Shot Clinical Information Extractors. *EMNLP 2022*.
- Fraile Navarro, D. et al. (2023). Clinical named entity recognition and relation extraction using natural language processing of medical free text: A systematic review. *International Journal of Medical Informatics*, 177, 105122.
- Huang, Y., Lv, T., Cui, L., Lu, Y. & Wei, F. (2022). LayoutLMv3: Pre-training for Document AI with Unified Text and Image Masking. *ACM Multimedia 2022*.
- Kim, G. et al. (2022). OCR-free Document Understanding Transformer (Donut). *ECCV 2022*.
- Pan, S. et al. (2024). Unifying Large Language Models and Knowledge Graphs: A Roadmap. *IEEE Transactions on Knowledge and Data Engineering*, 36(7).
- Savova, G. K. et al. (2010). Mayo clinical Text Analysis and Knowledge Extraction System (cTAKES). *JAMIA*, 17(5).
- Taha, Z., Morsey, M. M. & Ali, M. (2026). Ontology-grounded knowledge graphs for mitigating hallucinations in large language models for clinical question answering. *Journal of Biomedical Informatics*, 175, 104993. *(Résumé non consulté : vérifier les résultats avant de les citer.)*
- Uzuner, Ö., South, B. R., Shen, S. & DuVall, S. L. (2011). 2010 i2b2/VA challenge on concepts, assertions, and relations in clinical text. *JAMIA*, 18(5).
- Xu, Y. et al. (2020). LayoutLM: Pre-training of Text and Layout for Document Image Understanding. *KDD 2020*.
- Zhu, Y. et al. (2024). LLMs for Knowledge Graph Construction and Reasoning: Recent Capabilities and Future Opportunities. *World Wide Web*, 27.

**Contraintes, ontologies, réparation**
- Bodenreider, O. (2004). The Unified Medical Language System (UMLS). *Nucleic Acids Research*, 32(suppl_1).
- Chu, X., Ilyas, I. F. & Papotti, P. (2013). Holistic Data Cleaning: Putting Violations into Context. *ICDE 2013*.
- Fan, W., Wu, Y. & Xu, J. (2016). Functional Dependencies for Graphs. *SIGMOD 2016*.
- Gangemi, A. (2005). Ontology Design Patterns for Semantic Web Content. *ISWC 2005*, LNCS 3729.
- Geng, S., Josifoski, M., Peyrard, M. & West, R. (2023). Grammar-Constrained Decoding for Structured NLP Tasks without Finetuning. *EMNLP 2023*.
- Knublauch, H. & Kontokostas, D. (2017). Shapes Constraint Language (SHACL). *W3C Recommendation*.
- Noy, N. & Rector, A. (2006). Defining N-ary Relations on the Semantic Web. *W3C Working Group Note*.
- Paulheim, H. (2017). Knowledge Graph Refinement: A Survey of Approaches and Evaluation Methods. *Semantic Web*, 8(3).
- Rekatsinas, T., Chu, X., Ilyas, I. F. & Ré, C. (2017). HoloClean: Holistic Data Repairs with Probabilistic Inference. *PVLDB*, 10(11).

**Décision sélective, agrégation, contexte clinique**
- Chapman, W. W. et al. (2001). A Simple Algorithm for Identifying Negated Findings and Diseases in Discharge Summaries (NegEx). *Journal of Biomedical Informatics*, 34(5).
- Chow, C. K. (1970). On Optimum Recognition Error and Reject Tradeoff. *IEEE Transactions on Information Theory*, 16(1).
- Garcez, A. d'A. & Lamb, L. C. (2023). Neurosymbolic AI: The 3rd Wave. *Artificial Intelligence Review*, 56.
- Geifman, Y. & El-Yaniv, R. (2017). Selective Classification for Deep Neural Networks. *NeurIPS 2017*.
- Harkema, H., Dowling, J. N., Thornblade, T. & Chapman, W. W. (2009). ConText: An Algorithm for Determining Negation, Experiencer, and Temporal Status from Clinical Reports. *Journal of Biomedical Informatics*, 42(5).
- Ratner, A. et al. (2017). Snorkel: Rapid Training Data Creation with Weak Supervision. *PVLDB*, 11(3).
