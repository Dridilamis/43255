# TRACE-Sepsis v2.0 — corrections par rapport à la v1.7

Point de départ : la v1.7 validée par le médecin, dont les décisions en attente ont été tranchées.
La v2.0 précise la frontière entre LABEL_NOSOLOGIQUE et COMORBIDITE_ANTECEDENT, et rattache chaque foyer à son diagnostic. Ces règles ont été validées par le médecin.

## 1. LABEL_NOSOLOGIQUE : toujours pour les diagnostics de la liste

Un diagnostic de la liste `valeurs_autorisees` de LABEL_NOSOLOGIQUE est **toujours** un LABEL_NOSOLOGIQUE, **quel que soit l'épisode**, actuel ou antérieur. C'est le cas, par exemple, de la pneumopathie, du choc septique ou de la pyélonéphrite.

Le texte suffit à porter la temporalité : « antécédent de pneumopathie en 2012 » reste un LABEL_NOSOLOGIQUE.

- Nouvelle règle de typage : `LABEL_NOSOLOGIQUE_vs_COMORBIDITE_ANTECEDENT`.
- Nouvelle règle générale : `R12_label_vs_comorbidite`.

## 2. COMORBIDITE_ANTECEDENT : tout antécédent hors de cette liste

COMORBIDITE_ANTECEDENT regroupe :
- les pathologies chroniques et le terrain : diabète, insuffisance rénale chronique, cancer… ;
- les antécédents et les épisodes antérieurs **dont le nom n'est pas dans la liste LABEL_NOSOLOGIQUE**, y compris les antécédents infectieux, par exemple une tuberculose ancienne.

## 3. FOYER_INFECTIEUX : toujours la localisation d'un diagnostic

Le foyer n'est plus relié directement au patient. Il est relié au diagnostic dont il est la localisation :

| Le foyer localise… | Relation | Signature |
|---|---|---|
| un LABEL_NOSOLOGIQUE | `label_nosologique_a_pour_foyer` (nouvelle) | LABEL_NOSOLOGIQUE → FOYER_INFECTIEUX |
| une COMORBIDITE_ANTECEDENT | `comorbidite_a_pour_foyer` (nouvelle) | COMORBIDITE_ANTECEDENT → FOYER_INFECTIEUX |

- **Relation retirée** : `presente_suspicion_infection` (DONNEE_PATIENT → FOYER_INFECTIEUX). Le lien patient → infection passe désormais par `a_pour_label_nosologique`, qui couvre aussi la valeur `suspicion_infection`.
- **Foyer sans diagnostic écrit** : le foyer est annoté **sans relation de rattachement**. On n'infère rien.
- **Nouvelle règle générale** : `R13_rattachement_foyer`.

## Exemples

| Texte | Annotation v2.0 |
|---|---|
| « choc septique à point de départ urinaire » | LABEL `choc septique` → `label_nosologique_a_pour_foyer` → FOYER `point de départ urinaire` |
| « antécédent de pneumopathie en 2012 » | LABEL `pneumopathie` |
| « ATCD de pyélonéphrite droite » | LABEL `pyélonéphrite` → `label_nosologique_a_pour_foyer` → FOYER `droite` |
| « diabète de type 2 » | COMORBIDITE_ANTECEDENT (endocrinien) |
| « ATCD de tuberculose pulmonaire » | COMORBIDITE `tuberculose` → `comorbidite_a_pour_foyer` → FOYER `pulmonaire` |

## Bilan

- **Relations** : 34 → **35**.
  - Ajouts : `label_nosologique_a_pour_foyer`, `comorbidite_a_pour_foyer`.
  - Retrait : `presente_suspicion_infection`.
- **Types d'entités** : 20, inchangés. Les définitions de trois types sont précisées : LABEL_NOSOLOGIQUE, COMORBIDITE_ANTECEDENT et FOYER_INFECTIEUX.
- **Fichiers** :
  - `Guideline_TRACE_Sepsis_v2.0.json`
  - `labeling_interface_TRACE_Sepsis_v2.0.xml`
