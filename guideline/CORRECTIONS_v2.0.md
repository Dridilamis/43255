# TRACE-Sepsis v2.0 — corrections par rapport à la v1.7

Point de départ : la v1.7 validée par le médecin, dont les décisions en attente ont été tranchées.

## 1. LABEL_NOSOLOGIQUE : toujours pour les diagnostics de la liste

Un diagnostic de la liste `valeurs_autorisees` (pneumopathie, choc septique, pyélonéphrite…) est **toujours** un LABEL_NOSOLOGIQUE, **quel que soit l'épisode**, actuel ou antérieur. C'est le texte qui porte la temporalité.

- Nouvelle règle de typage : `LABEL_NOSOLOGIQUE_vs_COMORBIDITE_ANTECEDENT`.
- Nouvelle règle générale : `R12_label_vs_comorbidite`.

## 2. COMORBIDITE_ANTECEDENT : tout antécédent hors de cette liste

COMORBIDITE_ANTECEDENT regroupe :
- les pathologies chroniques et le terrain ;
- les antécédents et les épisodes antérieurs **dont le nom n'est pas dans la liste LABEL_NOSOLOGIQUE**, y compris les antécédents infectieux comme une tuberculose ancienne.

## 3. FOYER_INFECTIEUX : réservé à la localisation d'un LABEL_NOSOLOGIQUE

Un FOYER_INFECTIEUX est **uniquement** la localisation d'un LABEL_NOSOLOGIQUE.

| Situation | Annotation |
|---|---|
| Localisation d'un diagnostic | FOYER relié au LABEL par **`label_nosologique_a_pour_foyer`** (nouvelle relation) |
| Localisation d'une COMORBIDITE_ANTECEDENT | **pas de FOYER_INFECTIEUX** |
| Lien direct patient → foyer | **retiré** (`presente_suspicion_infection`) |

- Le lien patient → infection passe désormais par `a_pour_label_nosologique`, qui couvre aussi la valeur `suspicion_infection`, puis par `label_nosologique_a_pour_foyer`.
- Les autres relations vers un foyer sont **conservées** :
  - `micro_organisme_isole_dans` ;
  - `micro_organisme_infecte_site` ;
  - `imagerie_objective_foyer` ;
  - `symptome_oriente_foyer`.
- Si aucun LABEL n'est écrit, le foyer reste **sans relation de rattachement**. On n'infère rien.
- Nouvelle règle générale : `R13_rattachement_foyer`.

## Exemples

| Texte | Annotation v2.0 |
|---|---|
| « choc septique à point de départ urinaire » | LABEL `choc septique` → `label_nosologique_a_pour_foyer` → FOYER `point de départ urinaire` |
| « antécédent de pneumopathie en 2012 » | LABEL `pneumopathie` |
| « ATCD de pyélonéphrite droite » | LABEL `pyélonéphrite` → `label_nosologique_a_pour_foyer` → FOYER `droite` |
| « diabète de type 2 » | COMORBIDITE_ANTECEDENT (endocrinien) |
| « ATCD de tuberculose pulmonaire » | COMORBIDITE_ANTECEDENT `tuberculose`, **sans FOYER** |

## Bilan

- **Relations** : **34**, nombre inchangé.
  - Ajout : `label_nosologique_a_pour_foyer`.
  - Retrait : `presente_suspicion_infection`.
- **Types d'entités** : 20, inchangés. Les définitions de LABEL_NOSOLOGIQUE, COMORBIDITE_ANTECEDENT et FOYER_INFECTIEUX sont précisées.
- **Fichiers** :
  - `Guideline_TRACE_Sepsis_v2.0.json`
  - `labeling_interface_TRACE_Sepsis_v2.0.xml`
