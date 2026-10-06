TRACE - ETAGE 8b - GROUNDING GATE
=================================

Pourquoi
--------
Sur la base PROPRE, les Etages 2 a 8 ne retirent presque aucune relation (3731 en entree,
3744 en sortie de l'Etage 8). Ils annotent, mais une relation dont l'entite ou la citation
n'existe pas dans le compte rendu reste dans le graphe final.

L'Etage 8b confronte chaque relation au texte source du document et retire celles qui ne
peuvent pas en provenir (regles detaillees en tete de grounding_gate.py) :
  G1  extremite (hors patient) absente du texte          -> entite inventee
  G2  citation de preuve absente du texte                 -> preuve inventee
  G3  extremite marquee nie=True dans une relation positive -> contradiction
  G5  extremites jamais citees a moins de 300 caracteres  -> lien invente
  G4  doublon exact (option --dedupe, desactivee par defaut)
  N1  normalisation Unicode NFKC des noms d'entites ("µ" -> "μ"), ne retire rien

Aucun acces au gold. Seuils (couverture 1/2, fenetre 300 caracteres) fixes a priori.

Lancer
------
  python grounding_gate.py             (ou via run_chain_3_to_8.py, Etage 8b)
  python grounding_gate.py --dedupe
  python grounding_gate.py --dry-run

Resultats mesures (43 documents, relations, RELAXED, meme matcher que l'ablation)
---------------------------------------------------------------------------------
                         relations    FP     Precision  Rappel   F1
08_CONFIDENCE              3744      1060     71.66%    54.92%   62.19%
08b (defaut G1 G2 G3 G5)   3729      1046     71.92%    54.90%   62.27%
08b defaut + N1 (actuel)   3729      1042     72.03%    54.98%   62.36%
08b --dedupe (sans N1)     3544       938     73.50%    53.33%   61.81%

Par defaut : 15 relations retirees, dont 14 faux positifs. N1 transforme en plus 4 FP en
vrais positifs (161 noms normalises) : precision, rappel et F1 montent ensemble, sur chacune
des deux moities du corpus (documents pairs / impairs). Entites : inchangees (F1 71.14%).
--dedupe   : 200 retirees, dont 122 faux positifs (le gold compte les mentions repetees,
             d'ou la baisse de rappel ; a activer si la cible est un graphe sans doublon).

Limite connue : G1 retire aussi une entite dont le nom a ete canonicalise loin du texte
("noradrenaline" pour "NAD", "vitamine B6" pour "vit b6"). Ces 6 relations etaient des
FP au sens du gold, mais il ne s'agit pas d'hallucinations au sens strict.

Les ~1046 FP restants sont, pour l'essentiel, ancres dans le texte (bonne entite, bonne
citation) : ce sont des desaccords d'annotation ou de frontiere avec le gold, pas des
inventions. Les retirer demande de sacrifier du rappel (voir confidence_vs_gold.py).

Pistes testees pour monter le rappel, et ecartees (mesures sur les 2 moities du corpus)
-------------------------------------------------------------------------------------
- Relier chaque entite isolee au patient / a son traitement selon l'ontologie
  (traitement_administre_a, presente_symptome, posologie, defaillance, evolution, label,
  foyer, service) : chaque regle fait baisser le F1. Ex. traitements isoles relies au
  patient : 304 ajouts, 41 corrects seulement. Le LLM avait raison de ne pas les relier.
- Etage 9 (Relation Recovery) : 2194 relations ajoutees, 12.6 % correctes ; aucun type de
  relation ne depasse 18 %. Rappel 54.9 -> 64.0 % mais precision 72 -> 49 %, F1 -> 55 %.
- Etendre les posologies a leur rythme ("1mg" -> "1mg/heure") : effet nul a negatif.

Ou se trouve la marge restante :
- 842 des ~1046 FP n'ont aucune relation gold proche : ils sont ancres dans le texte mais
  le gold ne les annote pas.
- ~2150 des ~2200 FN n'ont aucune relation predite correspondante, et 974 (44 %) ont une
  extremite qu'aucune entite predite ne recouvre (meme partiellement).
Ces deux ecarts se jouent a l'EXTRACTION (prompt Mistral, consignes d'annotation), pas en
post-traitement : c'est la que precision, rappel et F1 peuvent progresser ensemble.
