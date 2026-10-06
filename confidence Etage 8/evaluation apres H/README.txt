TRACE â€” Evaluation aprÃ¨s rÃ©duction des hallucinations

1. Copier ce dossier, par exemple dans :
   C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM\Reduction_hallucinations\evaluation_apres_TRACE_code

2. VÃ©rifier :
   Gold :
   C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM\gold_canonical_par_documentF

   PrÃ©dictions :
   C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM\Reduction_hallucinations\confidence Etage 8\confidence_assessed_safe

3. Lancer :
   python run_evaluation_apres_TRACE.py

IMPORTANT :
Le script postprocessing_final n'est PAS relancÃ©.
La sortie de l'Etage 8 descend dÃ©jÃ  de la sortie post-traitÃ©e utilisÃ©e dans le pipeline TRACE.
Relancer le post-processing modifierait l'objet Ã©valuÃ© et rendrait la comparaison moins propre.

Les algorithmes de matching entitÃ©s/relations sont conservÃ©s.
Seuls les chemins d'entrÃ©e/sortie ont Ã©tÃ© adaptÃ©s.

