# TRACE-Sepsis v1.7 : corrections après validation médicale

Base : TRACE-Sepsis v1.6 FINAL. Réunion de validation avec le médecin référent : 12/10/2026.
Fichier corrigé : `Guideline_TRACE_Sepsis_v1.7.json` (JSON valide). Chaque correction y porte un
statut : `valide` (intégrée) ou `a_valider` (décision encore à prendre).

Les **32 signatures de relations v1.5 ne changent pas** (vérifié automatiquement : elles sont
identiques à celles de TRACE et de SGCE). Une **33e relation** est ajoutée après validation
médicale : `ira_a_pour_stade` (DEFAILLANCE_ORGANE → STADE_IRA). La liste de référence est
désormais `signatures_relations_v1_7` (33 relations).

## Corrections intégrées (statut `valide`)

| # | Entité | Correction du médecin | Où dans le JSON |
|---|---|---|---|
| 1 | Règle générale | Prendre en compte les synonymes et les abréviations lors de l'extraction | `regles_generales_annotation_v1_6.R11_synonymes_abreviations_v1_7` |
| 2 | DONNEE_PATIENT | Les informations du patient sont prises à l'admission | `DONNEE_PATIENT.regles_validation.moment_reference_v1_7` |
| 3 | LABEL_NOSOLOGIQUE | Retrait de 12 valeurs hors sepsis : syndrome hépato-rénal, encéphalopathie hépatique, état de mal épileptique, crise et aggravation myasthéniques, ACFA, flutter, SIADH, MAT, SHU, AVC, AVC hémorragique probable | `valeurs_retirees_v1_7` |
| 4 | BIOMARQUEUR | Orientation clinique : lactate → choc septique (≥ 2 mmol/L) et insuffisance hépatique ; créatinine, urée, DFG → IRA (AKI) ; bilirubines, ASAT, ALAT, γGT, PAL → insuffisance hépatique ; plaquettes, TP, TCA, fibrinogène, D-dimères, facteurs II, V, VII, X → CIVD ; pH, PaO2, PaCO2, bicarbonates, CO2 total, SaO2, PaO2/FiO2 → SDRA ; antigénurie → infection | `orientation_clinique_v1_7` |
| 5 | Règle R1 | Seuil du lactate : **≥ 2** mmol/L au lieu de > 2 | `regles_derivees.R1` |
| 6 | SCORE_SOFA | Définition des composantes : respiratoire = PaO2/FiO2 ; coagulation = plaquettes ; hépatique = bilirubine totale ; cardiovasculaire = pression artérielle et besoin de vasopresseurs ; neurologique = Glasgow ; rénal = créatinine et diurèse des 24 h | `definition_composantes_v1_7` |
| 7 | SCORE_NEUROLOGIQUE | Glasgow total = somme des 3 sous-scores ; score myasthénique retiré ; MMS = antécédent ou conséquence du sepsis ; testing musculaire = conséquence du sepsis | `regles_v1_7`, `valeurs_retirees_v1_7`, `notes_v1_7` |
| 8 | MICRO_ORGANISME | Gram positif ou négatif précisé en cocci (synonyme : coque) ou bacille | attribut `morphologie` |
| 9 | MICRO_ORGANISME | Le type de prélèvement renseigne le site d'infection ; site exact pour un prélèvement per-opératoire et pour une biopsie | attribut `site_prelevement` |
| 10 | MICRO_ORGANISME | BHRE = bactérie hautement résistante émergente | `definitions_phenotype_resistance` |
| 11 | DEFAILLANCE_ORGANE | Cardiovasculaire = synonyme d'hémodynamique ; métabolique = lié à l'IRA | `synonymes_organes_v1_7`, `notes_organes_v1_7` |
| 12 | COMORBIDITE_ANTECEDENT | Le type endocrinien inclut le diabète | `notes_type_antecedent_v1_7` |
| 13 | Relations | Nouvelle relation `ira_a_pour_stade` : DEFAILLANCE_ORGANE (IRA) → STADE_IRA, seulement si le stade est écrit dans le document | `relations.RELATIONS_DIAGNOSTIQUES.ira_a_pour_stade`, `signatures_relations_v1_7` |

## Décisions à prendre (statut `a_valider`)

| # | Remarque du médecin | Pourquoi elle n'est pas appliquée |
|---|---|---|
| B | STADE_IRA : « à réfléchir » | L'entité est gardée telle quelle. Elle est rare dans les comptes rendus. |
| C | SOFA cardiovasculaire : relier le score aux vasopresseurs | La composante dépend du besoin en vasopresseurs, qui sont des TRAITEMENT, mais aucune relation ne relie SCORE_SOFA à un TRAITEMENT. Il faudrait une nouvelle relation (`score_sofa_inclut_traitement`, limitée aux vasopresseurs). Proposition dans `propositions_v1_7.R_SOFA_VASOPRESSEUR`. |

## Impact sur le gold et sur les résultats

- **46 entités du gold** (sur 11 073, soit 0,4 %) utilisent une valeur retirée : 41 LABEL_NOSOLOGIQUE (ACFA 11, encéphalopathie hépatique 7, état de mal épileptique 7, flutter 4, MAT 3, myasthénie 3, AVC 2, syndrome hépato-rénal 2, SHU 1, SIADH 1) et 5 scores myasthéniques.
- **Les résultats actuels (chapitre 6) ont été obtenus avec le guideline v1.6.** Pour passer à v1.7, il faut appliquer les mêmes corrections au gold et au prompt d'extraction, puis tout ré-évaluer. Il ne faut pas mélanger un gold v1.6 avec une extraction v1.7.
- Le gold doit être révisé selon v1.7 **par l'annotatrice ou le médecin**, à partir du guideline, et jamais à partir des sorties du modèle.
- **Nouvelle relation `ira_a_pour_stade`** : le gold actuel contient 21 IRA typées DEFAILLANCE_ORGANE mais **aucune entité STADE_IRA** et donc aucune relation de ce type. Il faut l'annoter dans le gold là où un stade est écrit ; sinon cette relation n'aura aucun exemple pour l'évaluation.
- **TRACE** : les 32 anciennes signatures sont inchangées. Pour que l'étage 3 reconnaisse la nouvelle relation, il faudra lui donner les 33 signatures v1.7. Sans cela, il la marquera « non conforme » (simple indice, sans retrait).
