SGCE F1 OPTIMIZER AUDIT

Lancer depuis ce dossier :
python run_SGCE_F1_optimizer_audit.py

Le script :
- découvre automatiquement les dossiers corrected de SGCE contenant les documents cliniques ;
- calcule Relation Precision / Recall / F1 avec le même matcher ;
- affiche Δ F1 vs baseline et vs sortie précédente ;
- affiche FP/FN ;
- identifie les transitions où le F1 chute le plus ;
- ne modifie aucun JSON clinique.

Baseline de référence relaxed validée :
P=74.51%, R=63.62%, F1=68.64%.

Après exécution, envoyer la section :
TABLEAU SGCE — RELAXED
et
TOP 5 TRANSITIONS A EXAMINER EN PRIORITE.
