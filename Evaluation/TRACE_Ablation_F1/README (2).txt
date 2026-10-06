TRACE â€” ABLATION F1 PAR ETAGE

But
===
Mesurer l'Ã©volution de Precision / Recall / F1 aprÃ¨s chaque Ã©tage de TRACE,
avec les mÃªmes matchers que ceux utilisÃ©s pour la baseline.

Fichiers
========
- Matching_entites_ABLATION.py
- Matching_relations_ABLATION.py
- run_ablation_f1_TRACE.py

Lancement
=========
python run_ablation_f1_TRACE.py

Sorties
=======
C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM\Reduction_hallucinations\evaluation_ablation_F1_TRACE

Le dossier contient :
- un sous-dossier par Ã©tage ;
- les rÃ©sultats dÃ©taillÃ©s entitÃ©s/relations ;
- terminal_entities.txt / terminal_relations.txt ;
- TRACE_ablation_F1_summary.csv ;
- TRACE_ablation_F1_summary.json.

Principe scientifique
=====================
- mÃªme Gold Standard ;
- mÃªmes matchers ;
- mÃªmes seuils ;
- aucune optimisation en fonction des scores obtenus ;
- comparaison relaxed principale + conservation des rÃ©sultats dÃ©taillÃ©s des matchers.

