TRACE — ETAGE 4 / RELATION VALIDATION

PLACEMENT
---------
Reduction_hallucinations/
└── ontology Etage 4/
    ├── entity_validation/
    │   └── entity_validation_safe_corrected/
    └── relation_validation/
        └── [contenu de ce package]

ENTREE
------
../entity_validation/entity_validation_safe_corrected

ORDRE
-----
1. Audit après Entity Validation
2. Residual Builder
3. Residual Classifier
4. Residual Validator
5. Deep Reviewer
6. Final Validator
7. SAFE_REMOVE Corrector
8. Audit après SAFE_REMOVE
9. Review Resolver
10. Review Validator
11. Review Safe Corrector

SORTIE OFFICIELLE
-----------------
relation_validation_safe_corrected/

LANCEMENT
---------
python run_relation_validation.py

REMARQUE
--------
Les algorithmes métier des scripts fournis sont conservés.
Les modifications portent sur l'organisation, les chemins et le chaînage.
