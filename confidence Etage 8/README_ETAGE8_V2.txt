TRACE — ETAGE 8 V2 — EVIDENCE-BASED CONFIDENCE ASSESSMENT

Correction adaptée à la structure réelle TRACE-Sepsis:
- global_entities
- global_relations
- identifiant_entite
- identifiant_relation
- identifiant_entite_sujet / identifiant_entite_objet
- preuve
- schema.entity_types / schema.relation_types

Un fichier n'est considéré comme dossier clinique que s'il contient:
source_file + global_entities + global_relations.
Les JSON de rapport sont donc ignorés.

Entrée:
negation Etage 7\negation_safe_corrected

Textes:
Sortie_Textes_Brut_MistralSmall4

Sortie:
confidence Etage 8\confidence_assessed_safe

Exécution:
python run_confidence.py

Règles:
HIGH / MEDIUM / LOW / REVIEW sont qualitatives.
Aucun coefficient.
Aucune probabilité.
Aucune suppression.
Aucune modification clinique.
Seule trace_confidence est ajoutée.
Le post-validateur doit être PASS.
