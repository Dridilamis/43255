# Fiche soutenance : « retour extérieur » et correction des LLMs

## 1. De quoi parle-t-on ?

- **Auto-correction intrinsèque** : le LLM relit sa propre réponse et la corrige, sans autre information.
  Huang et al. (ICLR 2024) montrent que, sur des tâches de raisonnement, il lui arrive de transformer une
  réponse juste en réponse fausse, et que ses performances baissent parfois après la correction.
- **Retour extérieur** : une information que le modèle ne produit pas lui-même et qui lui dit si sa sortie est juste.
  Kamoi et al. (TACL 2024) concluent que la correction fonctionne surtout quand ce retour est fiable.

## 2. Les types de retour extérieur (Pan et al., TACL 2024 ; Kamoi et al., TACL 2024)

| Type de retour | Exemple dans la littérature | Équivalent dans TRACE |
|---|---|---|
| Outil au verdict fiable | Exécution du code produit (Self-Debug, Chen et al., ICLR 2024) ; outils de CRITIC (Gou et al., ICLR 2024) | Vérification des 34 signatures du guideline (étage 3), contraintes de structure (étage 4) |
| Connaissance externe | Recherche de documents puis révision des affirmations non soutenues (RARR, Gao et al., ACL 2023) | Le texte du dossier lui-même : ancrage de chaque élément (étage 2) |
| Vérificateur appris | Modèle entraîné sur des exemples annotés pour juger une sortie | Vote appris du mode précision, en validation croisée (étage 7) |
| Retour humain | Annotation ou correction par un expert | Validation du guideline et du Gold Standard par le Pr Heming (en amont) |
| Autre LLM utilisé comme juge | « LLM-as-a-judge » | **Écarté** : peut halluciner, non reproductible, non explicable |

## 3. Questions probables du jury et réponses

**Q1. Pourquoi ne pas demander à un LLM de vérifier l'extraction ?**
Parce que sans retour extérieur fiable, un LLM ne se corrige pas de façon fiable (Huang 2024, Kamoi 2024).
Un juge LLM peut lui-même halluciner : on déplace le problème. Et ses décisions ne sont ni reproductibles
ni explicables, alors que le médecin doit savoir pourquoi un élément a été retiré.

**Q2. Mais TRACE n'utilise-t-il pas lui aussi une forme de retour ?**
Si, et c'est justement le point : TRACE fournit un retour extérieur fiable, au sens de la littérature.
Le texte du dossier joue le rôle de connaissance externe, le guideline celui d'un outil de vérification,
et le vote appris celui d'un vérificateur entraîné. La différence avec un juge LLM, c'est que chacun de ces
retours est déterministe et traçable.

**Q3. Les « agents » de SGCE et de l'étage 7 sont-ils des LLMs ?**
Non. Ce sont des programmes déterministes : règles explicites, comparaisons au texte et au schéma. Le mot
« agent » désigne un module spécialisé qui examine l'élément sous un seul angle, pas un modèle génératif.

**Q4. Avez-vous essayé une approche par LLM ?**
Oui, pour récupérer les oublis : des approches par cohérence (interroger plusieurs fois le modèle et garder
les réponses concordantes, Wang 2023, Manakul 2023). Les éléments ajoutés étaient majoritairement faux,
en particulier les relations (chapitre 5, choix de conception).

**Q5. Le vérificateur appris n'utilise-t-il pas le Gold, donc la réponse ?**
Il est appris en validation croisée : chaque dossier est jugé par un modèle entraîné uniquement sur l'autre
moitié du corpus. Il n'a donc jamais vu l'annotation du dossier qu'il juge.

**Q6. Quelle perspective ?**
Fermer la boucle : renvoyer au modèle d'extraction les signaux de TRACE (élément non ancré, signature
violée, relation orpheline) comme retour extérieur, pour qu'il corrige sa sortie, à la manière de CRITIC ou
RARR. Ce retour étant fiable, c'est précisément le cas où la littérature montre que la correction fonctionne.
Une autre piste est le retour humain ciblé : ne soumettre au médecin que les éléments au score incertain.

## Références
- Huang et al., *Large Language Models Cannot Self-Correct Reasoning Yet*, ICLR 2024.
- Kamoi et al., *When Can LLMs Actually Correct Their Own Mistakes?*, TACL 12, 2024, p. 1417-1440.
- Pan et al., *Automatically Correcting Large Language Models*, TACL 12, 2024, p. 484-506.
- Gou et al., *CRITIC*, ICLR 2024.
- Gao et al., *RARR*, ACL 2023, p. 16477-16508.
- Chen et al., *Teaching Large Language Models to Self-Debug*, ICLR 2024.
