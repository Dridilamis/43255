TRACE — ETAGE 9 CORRIGE : ENTITY + RELATION RECOVERY

Corrections V2 :
1. diagnostic automatique des chemins et signatures ;
2. récupération d'entités uniquement depuis des endpoints orphelins typés et explicitement présents dans le texte ;
3. conservation de l'ID endpoint quand une entité manquante est reconstruite, afin de résoudre la relation existante ;
4. génération relationnelle depuis les signatures domaine/range du guideline ;
5. post-validation différentielle :
   - orphelins présents AVANT = PRE_EXISTING_ORPHANS ;
   - seuls les NOUVEAUX orphelins créés par l'Etage 9 provoquent FAIL.
6. aucun Gold Standard utilisé pour décider les ajouts.

Entrée :
confidence Etage 8/confidence_assessed_safe

Sortie :
relation_recovery Etage 9/relation_recovery_safe_corrected

Lancement :
python run_etage9.py

Après PASS, évaluer la sortie avec la canonicalisation + matching F1.
