TRACE — ETAGE 9 V3 : ENTITY + RELATION RECOVERY

V3 est adaptée à ontologie_sepsis_graph_v1.6.json.

Schéma réellement parsé :
ontologie_sepsis_graph
  ├─ entites : 21 types
  └─ relations
      └─ groupes
          └─ nom_relation
              ├─ domaine
              └─ image

L'ontologie V1.6 contient 32 signatures relationnelles.

Entity Recovery :
A) tentative de résolution des endpoints orphelins typés/document-grounded ;
B) récupération lexicale conservatrice depuis les valeurs explicitement listées par l'ontologie
   (valeurs_autorisees, noms_medicaments, localisations, organes, types, composantes, criteres).
Le Gold n'est jamais utilisé.

Relation Recovery :
- génération uniquement pour les 32 relations autorisées ;
- domaine/image obligatoires ;
- deux mentions document-grounded ;
- même phrase pour SAFE_ACCEPT ;
- validation ontologique + documentaire + adjudication ;
- aucune suppression clinique.

Sortie finale :
Reduction_hallucinations/relation_recovery Etage 9/relation_recovery_safe_corrected

Lancement :
python run_etage9.py

Puis : canonicalisation + évaluation Entity/Relation Precision Recall F1.
