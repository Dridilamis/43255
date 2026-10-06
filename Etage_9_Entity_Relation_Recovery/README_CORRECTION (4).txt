ETAGE 9 V4 — UNIQUEMENT LES 5 .PY CORRIGES

Correction ciblée :
Le JSON TRACE et le TXT brut n'ont pas le même nom.

Exemple réel :
JSON : img20250709_16142502_trace_sepsis_V1.6-V6.5-SELECTIVE_PRECISION.json
TXT  : img20250709_16142502_brut.txt

La fonction text_for() extrait maintenant la base documentaire avant
'_trace_sepsis' puis cherche '<base>_brut.txt'.

Fichiers à remplacer :
- 00_entity_candidate_builder.py
- 00b_lexical_entity_candidate_builder.py
- 00b_lexical_entity_evidence_validator.py
- 01_missing_link_candidate_builder.py
- 03_document_evidence_validator.py

Tous les autres fichiers de V3 restent inchangés.

Après remplacement :
python run_etage9.py
