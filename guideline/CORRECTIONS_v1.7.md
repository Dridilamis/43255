# TRACE-Sepsis v1.7 : corrections après validation médicale

Base : TRACE-Sepsis v1.6 FINAL. Réunion de validation avec le médecin référent : 12/10/2026.
Fichier corrigé : `Guideline_TRACE_Sepsis_v1.7.json` (JSON valide, version nettoyée : les corrections
sont intégrées directement dans les entités et les règles ; les points non tranchés sont regroupés
dans le bloc `decisions_en_attente`).

**Relations : 34 au total.** 30 des 32 signatures v1.5 sont conservées à l'identique (vérifié automatiquement). Deux relations d'imagerie sont retirées (`imagerie_objective_defaillance`, `imagerie_objective_comorbidite`) et quatre sont ajoutées après validation médicale : `ira_a_pour_stade`, `micro_organisme_infecte_site`, `symptome_oriente_foyer`, `symptome_associe_gravite_initiale`. La liste de référence est `signatures_relations`.

## Corrections intégrées

| # | Entité | Correction du médecin | Où dans le JSON |
|---|---|---|---|
| 1 | Règle générale | Prendre en compte les synonymes et les abréviations lors de l'extraction | `regles_generales_annotation.R11_synonymes_abreviations` |
| 2 | DONNEE_PATIENT | Les informations du patient sont prises à l'admission | `DONNEE_PATIENT.regles_validation.moment_reference` |
| 3 | LABEL_NOSOLOGIQUE | Retrait de 12 valeurs hors sepsis : syndrome hépato-rénal, encéphalopathie hépatique, état de mal épileptique, crise et aggravation myasthéniques, ACFA, flutter, SIADH, MAT, SHU, AVC, AVC hémorragique probable | `LABEL_NOSOLOGIQUE.valeurs_autorisees` (valeurs retirées) |
| 4 | BIOMARQUEUR | Orientation clinique : lactate → choc septique (≥ 2 mmol/L) et insuffisance hépatique ; créatinine, urée, DFG → IRA (AKI) ; bilirubines, ASAT, ALAT, γGT, PAL → insuffisance hépatique ; plaquettes, TP, TCA, fibrinogène, D-dimères, facteurs II, V, VII, X → CIVD ; pH, PaO2, PaCO2, bicarbonates, CO2 total, SaO2, PaO2/FiO2 → SDRA ; antigénurie → infection | `BIOMARQUEUR.orientation_clinique` |
| 5 | Règle R1 | Seuil du lactate : **≥ 2** mmol/L au lieu de > 2 | `regles_derivees.R1_lactate_critere_choc_septique` |
| 6 | SCORE_SOFA | Définition des composantes : respiratoire = PaO2/FiO2 ; coagulation = plaquettes ; hépatique = bilirubine totale ; cardiovasculaire = pression artérielle et besoin de vasopresseurs ; neurologique = Glasgow ; rénal = créatinine et diurèse des 24 h | `SCORE_SOFA.definition_composantes` |
| 7 | SCORE_NEUROLOGIQUE | Glasgow total = somme des 3 sous-scores ; score myasthénique retiré ; MMS = antécédent ou conséquence du sepsis ; testing musculaire = conséquence du sepsis | `SCORE_NEUROLOGIQUE.regles`, `valeurs_autorisees`, `notes` |
| 8 | MICRO_ORGANISME | Gram positif ou négatif précisé en cocci (synonyme : coque) ou bacille | attribut `morphologie` |
| 9 | MICRO_ORGANISME | Le type de prélèvement renseigne le site d'infection ; site exact pour un prélèvement per-opératoire et pour une biopsie | attribut `site_prelevement` |
| 10 | MICRO_ORGANISME | BHRE = bactérie hautement résistante émergente | `definitions_phenotype_resistance` |
| 11 | DEFAILLANCE_ORGANE | Cardiovasculaire = synonyme d'hémodynamique ; métabolique = lié à l'IRA | `DEFAILLANCE_ORGANE.synonymes_organes`, `notes_organes` |
| 12 | COMORBIDITE_ANTECEDENT | Le type endocrinien inclut le diabète | `COMORBIDITE_ANTECEDENT.notes_type_antecedent` |
| 13 | Relations | Nouvelle relation `ira_a_pour_stade` : DEFAILLANCE_ORGANE (IRA) → STADE_IRA, seulement si le stade est écrit dans le document | `relations.RELATIONS_DIAGNOSTIQUES.ira_a_pour_stade`, `signatures_relations`, `regles_derivees.R10_stade_IRA` |
| 14 | SCORE_SOFA | Barème des 6 composantes (seuils 0 → 4), entité source et relation pour chaque composante, exemple. Les définitions sont validées ; les **seuils** (barème de référence, Vincent et al., 1996) restent **à confirmer** par le médecin. Le barème sert à interpréter un SOFA écrit, jamais à en calculer un absent du texte | `SCORE_SOFA.bareme` |
| 15 | LABEL_NOSOLOGIQUE / FOYER_INFECTIEUX | La pneumopathie et ses types (communautaire, nosocomiale, inhalation, PAVM) sont des **diagnostics** donc LABEL_NOSOLOGIQUE ; FOYER_INFECTIEUX = **localisation seulement**. Diagnostic + localisation écrits → deux entités ; aucun FOYER déduit du mot « pneumopathie » | `regles_de_typage.LABEL_NOSOLOGIQUE_vs_FOYER_INFECTIEUX`, `FOYER_INFECTIEUX.description`, `normalisation_terminologique.LABEL_NOSOLOGIQUE` |
| 16 | Relations / MICRO_ORGANISME | Nouvelle relation `micro_organisme_infecte_site` (pathogène → site d'infection), distincte de `micro_organisme_isole_dans` (site de prélèvement). Règle : le site d'infection ne se déduit jamais de l'espèce — un pneumocoque (synonymes : *S. pneumoniae*, *Streptococcus pneumoniae*) n'est pas uniquement pulmonaire | `relations.RELATIONS_BIOMARQUEURS_ET_MICROBIO.micro_organisme_infecte_site`, `regles_derivees.R11_site_infection_pathogene` |
| 17 | TRAITEMENT | Sous-groupes : (1) traitement de l'infection (anti-infectieux, chirurgie) ; (2) traitement symptomatique des défaillances d'organe : a) hémodynamique, b) respiratoire, c) rénal ; les autres catégories sont conservées (« autres traitements de support ») | `TRAITEMENT.groupes_therapeutiques` |
| 18 | TRAITEMENT | Retirés (pas des traitements du sepsis ou non pertinents) : antalgique, anticoagulant, antiagrégant, diurétique, supplémentation électrolytique, kinésithérapie respiratoire et motrice, immunoglobulines, échange plasmatique, traitement habituel. Insuline et transfusion de CGR conservées. Ajoutés : décubitus ventral, ECMO. Notes : corticoïde (type et dose), sédatif (défaillance respiratoire, influence le Glasgow), nutrition entérale (liée à la ventilation) | `TRAITEMENT.valeurs_autorisees`, `notes_valeurs` |
| 19 | CONTEXTE_ACQUISITION | Ajout de l'attribut `hospitalisation_anterieure_recente` (dans les 6 mois) ; « post-opératoire » = infection du site opératoire ; valeur « indéterminée » retirée | `CONTEXTE_ACQUISITION` |
| 20 | EVOLUTION_PRONOSTIC | Ajouts : mortalité J90 et J180, décès en réanimation, durées de traitement par ventilation mécanique, par vasopresseur et par dialyse | `EVOLUTION_PRONOSTIC.types` |
| 21 | LABEL_NOSOLOGIQUE / FOYER_INFECTIEUX | « pneumonie » ajoutée aux valeurs des diagnostics ; « endocardite » ajoutée aux localisations | `valeurs_autorisees`, `localisations` |
| 22 | LABEL_NOSOLOGIQUE / FOYER_INFECTIEUX | Abcès, pyélonéphrite, érysipèle et sinusite sont des **diagnostics** (LABEL_NOSOLOGIQUE) ayant une localisation (FOYER_INFECTIEUX distinct si elle est écrite), comme la pneumopathie | `LABEL_NOSOLOGIQUE.valeurs_autorisees`, `regles_de_typage.LABEL_NOSOLOGIQUE_vs_FOYER_INFECTIEUX` |
| 23 | Références / principes | Les dossiers (2008–2015) emploient la terminologie et les seuils de **Sepsis-2** : la terminologie écrite est conservée (ex. « sepsis sévère ») ; ajout de la référence Sepsis-2 (Levy et al., 2003) | `references_fondatrices`, `principes_semantiques` |
| 24 | SERVICE_MEDICAL | Trajectoire du patient dès l'hospitalisation : ajout de lieu de vie, hors hôpital, maison de retraite, EHPAD | `SERVICE_MEDICAL` |
| 25 | METADONNEES_PIPELINE | Description générique « MLLM » (au lieu de Qwen2-VL) ; bbox et confiance visuelle non fournies par Mistral | `METADONNEES_PIPELINE` |
| 26 | IMAGERIE_PROCEDURE | Myélogramme retiré ; biopsie = liée au foyer, pour identifier le germe et guider l'antibiothérapie ; synonymes scanner = TDM = tomodensitométrie, ETT = échographie cardiaque trans-thoracique | `IMAGERIE_PROCEDURE`, `normalisation_terminologique.IMAGERIE_PROCEDURE` |
| 27 | SYMPTOME | Ajout : expectoration. Retirés : dysphonie, trouble de la mastication, chute de la mandibule, hypersalivation, hoquet, convulsions, trismus, myosis, mydriase, anisocorie, ptosis, œdèmes. Fausse route = oriente vers une pneumopathie d'inhalation | `SYMPTOME` |
| 28 | Relations d'imagerie | Seule `imagerie_objective_foyer` est conservée ; `imagerie_objective_defaillance` et `imagerie_objective_comorbidite` sont retirées | `relations.RELATIONS_IMAGERIE` |
| 29 | Relations symptôme | Ajout de `symptome_oriente_foyer` (SYMPTOME → FOYER_INFECTIEUX) et `symptome_associe_gravite_initiale` (SYMPTOME → SCORE_SOFA) | `relations.RELATIONS_SYMPTOMES` |
| 30 | Relations scores | `score_sofa_inclut_score_neurologique` (composante neurologique du SOFA) et `score_qsofa_inclut_score_neurologique` : validées | `relations.RELATIONS_DIAGNOSTIQUES` |
| 31 | Règle R1 | Choc septique (définition Sepsis-3) = **vasopresseurs + lactate ≥ 2 mmol/L** | `regles_derivees.R1_lactate_critere_choc_septique` |
| 32 | Règle R4bis | Critère neurologique du qSOFA = confusion ou Glasgow < 15 | `regles_derivees.R4bis_qsofa_critere_neurologique` |
| 33 | Règle R6 | Règle d'ordre chronologique prélèvement → antibiotique retirée | `regles_derivees` |
| 34 | Règle R7 | Risque de BMR : ajout du voyage récent dans un pays à forte prévalence de BMR (attribut `voyage_recent_etranger`) | `regles_derivees.R7`, `CONTEXTE_ACQUISITION` |
| 35 | Règle R8 | Relation d'imagerie seulement si l'examen et l'entité cible sont présents dans le document | `regles_derivees.R8_IMAGERIE_PROCEDURE` |

## Décisions à prendre

| # | Remarque du médecin | Pourquoi elle n'est pas appliquée |
|---|---|---|
| B | STADE_IRA | Gardé (utilisé par `ira_a_pour_stade`). À vérifier : prise en compte de la dialyse et de la diurèse dans le stade. |
| C | SOFA cardiovasculaire : relier le score aux vasopresseurs | La composante dépend du besoin en vasopresseurs, qui sont des TRAITEMENT, mais aucune relation ne relie SCORE_SOFA à un TRAITEMENT. Il faudrait une nouvelle relation (`score_sofa_inclut_traitement`, limitée aux vasopresseurs). Voir `decisions_en_attente.relation_SOFA_vasopresseurs`. |
| D | Relier un germe ou une imagerie à une pneumopathie quand aucune localisation n'est écrite | Aucune relation ne va de MICRO_ORGANISME ou IMAGERIE_PROCEDURE vers LABEL_NOSOLOGIQUE. Proposition : `micro_organisme_responsable_de` et `imagerie_objective_label`. |

## Impact sur le gold et sur les résultats

- **Pneumopathies (correction 15)** : 47 entités du gold (22 documents) sont des pneumopathies typées FOYER_INFECTIEUX et doivent passer en LABEL_NOSOLOGIQUE, en créant une entité FOYER séparée quand une localisation est écrite. 85 relations pointent vers elles (36 `micro_organisme_isole_dans`, 33 `presente_suspicion_infection`, 14 `imagerie_objective_foyer`, 2 `antibiotique_adequat_pour`) : à rattacher à la localisation si elle est écrite, ou à remplacer par `a_pour_label_nosologique` pour le patient ; sinon elles disparaissent (voir `decisions_en_attente.relations_germe_imagerie_vers_diagnostic`). 2 LABEL « choc septique à point de départ pulmonaire » sont à découper.
- **46 entités du gold** (sur 11 073, soit 0,4 %) utilisent une valeur retirée : 41 LABEL_NOSOLOGIQUE (ACFA 11, encéphalopathie hépatique 7, état de mal épileptique 7, flutter 4, MAT 3, myasthénie 3, AVC 2, syndrome hépato-rénal 2, SHU 1, SIADH 1) et 5 scores myasthéniques.
- **Les résultats actuels (chapitre 6) ont été obtenus avec le guideline v1.6.** Pour passer à v1.7, il faut appliquer les mêmes corrections au gold et au prompt d'extraction, puis tout ré-évaluer. Il ne faut pas mélanger un gold v1.6 avec une extraction v1.7.
- Le gold doit être révisé selon v1.7 **par l'annotatrice ou le médecin**, à partir du guideline, et jamais à partir des sorties du modèle.
- **Nouvelle relation `ira_a_pour_stade`** : le gold actuel contient 21 IRA typées DEFAILLANCE_ORGANE mais **aucune entité STADE_IRA** et donc aucune relation de ce type. Il faut l'annoter dans le gold là où un stade est écrit ; sinon cette relation n'aura aucun exemple pour l'évaluation.
- **Relations d'imagerie retirées** : le gold v1.6 contient des relations `imagerie_objective_defaillance` et `imagerie_objective_comorbidite`, qui deviennent hors schéma en v1.7.
- **TRACE** : il utilise encore les 32 signatures v1.6. Pour passer en v1.7, il faudra lui donner les 34 signatures de `signatures_relations`.
