# État de l'art — Fiabilité des graphes de connaissances extraits par des modèles de langage

> Document de travail pour le mémoire TRACE-Sepsis.
> Ce chapitre présente uniquement les travaux existants. La méthode proposée dans le
> mémoire n'y est pas décrite. Toutes les références de la bibliographie sont réelles.

---

## Introduction

Construire un graphe de connaissances clinique à partir de dossiers médicaux à l'aide
d'un grand modèle de langage (LLM) soulève trois questions :

1. Le modèle produit-il des informations absentes du document ?
2. La représentation produite respecte-t-elle le schéma attendu ?
3. Comment corriger les erreurs sans en introduire de nouvelles ?

La littérature traite ces questions dans des communautés distinctes. Ce chapitre les
présente selon six axes :
- les hallucinations des LLM ;
- l'extraction d'informations cliniques ;
- la validation structurelle par contraintes ;
- la réparation de données et de graphes ;
- la décision sélective et l'agrégation d'avis ;
- l'analyse du contexte clinique.

---

## 1. Hallucinations des grands modèles de langage

### 1.1 Définitions

Ji et al. (2023) distinguent deux types d'hallucination :
- l'hallucination **intrinsèque** est contredite par la source ;
- l'hallucination **extrinsèque** ne peut pas être vérifiée à partir de la source.

Huang, L. et al. (2025) proposent une taxonomie adaptée aux LLM, qui oppose les erreurs
de **factualité** (contraires aux connaissances du monde) aux erreurs de **fidélité**
(contraires au contexte fourni). En extraction documentaire, c'est la fidélité qui
importe : une information médicalement exacte mais absente du dossier reste une erreur.

### 1.2 Détection

On distingue quatre familles de méthodes.

- **Cohérence entre plusieurs générations.** SelfCheckGPT (Manakul et al., 2023)
  considère qu'une affirmation absente de générations alternatives est probablement
  hallucinée. La *self-consistency* (Wang et al., 2023) retient la réponse majoritaire
  sur plusieurs raisonnements.
- **Vérification de faits atomiques.** FActScore (Min et al., 2023) découpe un texte en
  faits élémentaires et les vérifie un à un contre une source.
- **Recherche documentaire.** La génération augmentée par récupération, ou RAG (Lewis
  et al., 2020), et Self-RAG (Asai et al., 2024) appuient la génération sur des
  documents récupérés.
- **Confiance du modèle.** Kadavath et al. (2022) montrent que les LLM sont en partie
  capables d'estimer la justesse de leurs propres réponses.

Dans le domaine médical, Med-HALT (Pal et al., 2023) propose un banc d'essai qui met en
évidence la fréquence des hallucinations sur des tâches cliniques.

### 1.3 Correction par le modèle lui-même

**Les approches.**
- Self-Refine (Madaan et al., 2023) fait réviser au modèle sa propre sortie, de façon
  itérative.
- Chain-of-Verification (Dhuliawala et al., 2024) lui fait d'abord générer des questions
  de vérification, puis y répondre.

**Leur portée est discutée.**
- Huang, J. et al. (2024) montrent qu'un LLM ne parvient pas à corriger son raisonnement
  sans retour extérieur.
- La revue critique de Kamoi et al. (2024) conclut que l'auto-correction n'est fiable que
  si le retour provient d'une **source extérieure fiable**, ou après un affinage à
  grande échelle.
- Pour le débat entre plusieurs modèles (Du et al., 2024), la factualité progresse, mais
  chaque agent reste lui-même susceptible d'halluciner.

### 1.4 Limites

- Les méthodes de détection signalent une erreur sans la réparer.
- Les méthodes d'auto-correction dépendent de la qualité d'un retour que le modèle ne
  peut pas toujours se fournir lui-même.
- Aucune méthode ne supprime à elle seule toutes les hallucinations (Huang, L. et al.,
  2025).

---

## 2. Extraction d'informations cliniques et construction de graphes

### 2.1 Approches classiques

Les campagnes i2b2 (Uzuner et al., 2011) ont fixé le cadre de l'extraction clinique :
repérer les problèmes, examens et traitements, ainsi que leurs relations. Des systèmes à
base de règles et de dictionnaires comme cTAKES (Savova et al., 2010) s'appuient sur des
ressources terminologiques telles que l'UMLS (Bodenreider, 2004).

La revue systématique de Fraile Navarro et al. (2023) porte sur 94 études : 68 utilisent
l'apprentissage automatique, 5 des règles, 22 combinent les deux. Seules 3 rapportent un
usage hors expérimentation. **Le passage en conditions réelles reste donc limité.**

### 2.2 Extraction par LLM

Agrawal et al. (2022) montrent que les LLM sont de bons extracteurs cliniques en
apprentissage à partir de quelques exemples (*few-shot*), à condition d'encadrer et de
vérifier leurs sorties.

Pour la construction de graphes de connaissances, Pan et al. (2024) et Zhu et al. (2024)
décrivent le LLM comme un générateur de triplets à la fois performant et peu contraint.
Ses erreurs typiques :
- types d'entités inadaptés ;
- relations hors schéma ;
- mentions regroupant plusieurs concepts ;
- liens représentés sous forme d'entités.

### 2.3 Documents numérisés

Les modèles de compréhension de documents exploitent conjointement le texte et la mise
en page : LayoutLM (Xu et al., 2020), LayoutLMv3 (Huang, Y. et al., 2022), et Donut
(Kim et al., 2022), qui travaille sans OCR.

Une bonne lecture du document ne garantit pas pour autant une représentation structurée
correcte : les erreurs de structuration surviennent **après** la lecture.

### 2.4 Graphes et ontologies contre les hallucinations

Taha, Morsey & Ali (2026) utilisent une ontologie clinique OWL et un graphe de
connaissances pour réduire les hallucinations dans la réponse à des questions médicales.
Ce travail porte sur la **génération de réponses**, et non sur la correction d'un graphe
extrait de documents.

### 2.5 Limites

- La plupart des travaux évaluent la qualité de l'extraction (précision, rappel), mais
  rarement le **contrôle a posteriori** de la structure produite.
- Les approches à base d'ontologie servent surtout à guider la génération, et peu à
  réparer une extraction existante.

---

## 3. Validation structurelle par contraintes

### 3.1 Contraintes déclaratives

SHACL (Knublauch & Kontokostas, 2017) permet de déclarer les formes qu'un graphe RDF doit
respecter : types, propriétés autorisées, cardinalités, domaine et image des relations.
La validation produit un **rapport de violations**.

Les ontologies fournissent les types et les relations autorisés. En médecine, elles
s'appuient sur des terminologies de référence comme l'UMLS (Bodenreider, 2004).

### 3.2 Contraintes pendant la génération

Le décodage contraint par une grammaire (Geng et al., 2023) oblige le LLM à produire une
sortie syntaxiquement valide : JSON bien formé, étiquettes prises dans une liste fermée.

### 3.3 Limites

- La validation par contraintes **détecte** les violations mais ne les **répare** pas.
- Le décodage contraint garantit la forme de la sortie, mais pas la cohérence des liens
  entre types (domaine → image).
- Surtout, **un graphe valide n'est pas forcément fidèle** : il peut respecter toutes
  les contraintes et contenir une information absente du document.

---

## 4. Réparation de données et de graphes

### 4.1 Raffinement de graphes de connaissances

Paulheim (2017) recense deux familles de méthodes appliquées à un graphe déjà construit :
- la **complétion** ajoute les faits ou les types manquants ;
- la **détection et correction d'erreurs** retype ou retire les éléments faux.

Paulheim souligne aussi la difficulté d'évaluer ces méthodes, faute de vérité de terrain
complète.

### 4.2 Réparation sous contraintes en bases de données

La réparation de données cherche la **modification minimale** qui fait disparaître les
violations de contraintes.
- Fan, Wu & Xu (2016) définissent des dépendances fonctionnelles pour les graphes.
- Chu, Ilyas & Papotti (2013) traitent toutes les violations ensemble (*holistic data
  cleaning*), car une même valeur erronée peut en causer plusieurs.
- HoloClean (Rekatsinas et al., 2017) combine contraintes, statistiques et inférence
  probabiliste pour proposer des réparations.

### 4.3 Patrons de modélisation

Les *Ontology Design Patterns* (Gangemi, 2005) codifient des solutions types à des
problèmes de modélisation récurrents.

Noy & Rector (2006) traitent le cas des relations *n*-aires : un lien qui porte
lui-même des informations doit-il être représenté par une arête, ou par un nœud
intermédiaire (*réification*) ?

### 4.4 Limites

- Ces méthodes sont conçues pour des données établies (bases, graphes publics), où
  l'erreur est rare et isolée.
- Elles ne s'appuient pas sur un **document source** pour justifier une réparation : la
  modification minimale rétablit la cohérence, mais rien ne garantit qu'elle est
  fidèle au document.
- Les patrons de modélisation sont **constructifs** (comment bien modéliser) plutôt que
  **correctifs** (comment réparer une modélisation fautive).

---

## 5. Décision sélective et agrégation d'avis

### 5.1 Abstention

Chow (1970) formalise le compromis entre erreur et rejet : un classifieur peut refuser
de décider quand le risque d'erreur est trop élevé. Geifman & El-Yaniv (2017) appliquent
ce principe aux réseaux profonds avec la *prédiction sélective*, qui garantit un risque
cible sur les cas acceptés.

### 5.2 Agréger plusieurs avis

- Le **débat multi-agents** (Du et al., 2024) confronte plusieurs LLM pour améliorer la
  factualité.
- La **supervision faible** (Ratner et al., 2017) combine plusieurs fonctions
  d'étiquetage imparfaites en un signal unique.
- Les approches **neuro-symboliques** (Garcez & Lamb, 2023) font coopérer apprentissage
  et raisonnement symbolique explicite.

### 5.3 Limites

- L'abstention est surtout étudiée pour la **classification**, rarement pour la décision
  de **corriger** ou non.
- Lorsque les agents sont eux-mêmes des LLM, l'agrégation peut propager une erreur
  partagée.

---

## 6. Contexte clinique des mentions

Dans un compte rendu, la présence d'un terme ne signifie pas que le patient présente la
pathologie correspondante.

- NegEx (Chapman et al., 2001) détecte la **négation** à l'aide de déclencheurs placés
  dans une fenêtre autour de la mention.
- ConText (Harkema et al., 2009) ajoute la **temporalité** (historique ou actuel) et le
  **sujet** (*experiencer* : le patient ou un tiers).

**Limite.** Ces algorithmes qualifient les mentions, mais ils n'agissent ni sur la
structure ni sur les relations d'un graphe.

---

## 7. Synthèse

| Axe | Approches représentatives | Apport | Limite |
|---|---|---|---|
| Détection d'hallucinations | SelfCheckGPT, FActScore, RAG | repère les informations non étayées | signale sans réparer |
| Auto-correction | Self-Refine, Chain-of-Verification, débat multi-agents | correction sans annotation | peu fiable sans retour extérieur |
| Extraction clinique | i2b2, cTAKES, LLM *few-shot* | entités et relations cliniques | peu de contrôle a posteriori ; peu de déploiement réel |
| Documents numérisés | LayoutLMv3, Donut | lecture texte et mise en page | ne garantit pas une structure correcte |
| Validation par contraintes | SHACL, décodage contraint | conformité explicite au schéma | détecte sans réparer ; valide ≠ fidèle |
| Réparation de données et de graphes | Paulheim, Chu et al., Fan et al., HoloClean | modification minimale sous contraintes | données établies ; pas de preuve documentaire |
| Décision sélective | Chow, Geifman & El-Yaniv | abstention à risque contrôlé | pensée pour la classification |
| Contexte clinique | NegEx, ConText | négation, temporalité, sujet | n'agit pas sur la structure du graphe |

### Questions ouvertes

L'examen de ces travaux fait ressortir plusieurs questions encore peu traitées
**ensemble** :

1. **Détecter et réparer.** Les méthodes de détection et les méthodes de réparation
   viennent de communautés différentes. Elles sont rarement combinées sur la sortie
   d'un LLM extracteur.
2. **Réparer avec une preuve.** Les méthodes de réparation rétablissent la cohérence
   sans exiger que la correction soit justifiée par le document source.
3. **Savoir ne pas corriger.** L'abstention est bien étudiée en classification, peu
   dans la décision de corriger un élément extrait.
4. **Évaluer les corrections.** La qualité d'une correction se mesure rarement à la fois
   par la réduction des anomalies et par l'absence de dégradation de la précision et du
   rappel face à une annotation de référence.

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
- Taha, Z., Morsey, M. M. & Ali, M. (2026). Ontology-grounded knowledge graphs for mitigating hallucinations in large language models for clinical question answering. *Journal of Biomedical Informatics*, 175, 104993. *(Résumé non consulté : vérifier avant de citer des résultats.)*
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
