TRACE — CANONICAL EVALUATION

But :
Convertir chaque sortie TRACE vers la même représentation documentaire canonique que le Gold,
puis appliquer les mêmes matchers entités/relations.

La conversion reprend de gold_to_canonic.py :
- normalize_text : NFKC, lowercase, NBSP, espaces ;
- global entity key = normalized_name + type ;
- global relation key = subject_normalized + subject_type + relation + object_normalized + object_type ;
- structure global_entities/global_relations.

IMPORTANT :
Le convertisseur n'ouvre jamais le Gold Standard et ne modifie aucune prédiction en fonction du F1.

Lancement :
python run_canonical_evaluation_TRACE.py

Résultat :
Reduction_hallucinations/evaluation_canonical_TRACE/canonical_F1_summary.csv
