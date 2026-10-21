# TRACE-Sepsis v2.0 — corrections par rapport à la v1.7

Point de départ : la v1.7 validée par le médecin (décisions en attente tranchées).
La v2.0 ajoute trois règles, validées par le médecin.

## 1. LABEL_NOSOLOGIQUE = épisode d'hospitalisation actuel uniquement

Un LABEL_NOSOLOGIQUE décrit **uniquement un diagnostic de l'hospitalisation en cours**.

Tout diagnostic rapporté à un **épisode antérieur** n'est jamais un LABEL_NOSOLOGIQUE, même s'il figure dans la liste des valeurs autorisées. C'est le cas d'un diagnostic :
- placé dans la section antécédents ;
- accompagné d'une date antérieure ;
- introduit par « antécédent de », « ATCD de » ou « déjà hospitalisé pour ».

- Nouvelle règle de typage : `LABEL_NOSOLOGIQUE_episode_actuel_vs_COMORBIDITE_ANTECEDENT`.
- Nouvelle règle générale : `R12_episode_actuel`.

## 2. COMORBIDITE_ANTECEDENT = antécédents, y compris les épisodes antérieurs

COMORBIDITE_ANTECEDENT regroupe :
- les comorbidités chroniques ;
- les antécédents ;
- **les diagnostics des épisodes antérieurs**, y compris les infections (pneumopathie, sepsis, pyélonéphrite… d'une hospitalisation précédente). Ils sont typés avec `type_antecedent` = infectieux.

## 3. FOYER_INFECTIEUX = toujours la localisation d'un diagnostic

Un foyer n'est plus relié directement au patient. Il est relié au diagnostic dont il est la localisation :

| Épisode | Relation | Signature |
|---|---|---|
| actuel | `label_nosologique_a_pour_foyer` (nouvelle) | LABEL_NOSOLOGIQUE → FOYER_INFECTIEUX |
| antérieur | `comorbidite_a_pour_foyer` (nouvelle) | COMORBIDITE_ANTECEDENT → FOYER_INFECTIEUX |

- `presente_suspicion_infection` (DONNEE_PATIENT → FOYER_INFECTIEUX) est **retirée**. Le lien patient → infection passe par `a_pour_label_nosologique` (y compris la valeur `suspicion_infection`), puis par `label_nosologique_a_pour_foyer`.
- Si aucun diagnostic n'est écrit, le foyer est annoté **sans relation de rattachement**. On n'infère rien.
- Nouvelle règle générale : `R13_rattachement_foyer`.

## Exemples

| Texte | Annotation v2.0 |
|---|---|
| « choc septique à point de départ urinaire » (motif d'hospitalisation) | LABEL `choc septique` → `label_nosologique_a_pour_foyer` → FOYER `point de départ urinaire` |
| « antécédent de pneumopathie en 2012 » | COMORBIDITE_ANTECEDENT `pneumopathie` (infectieux) |
| « ATCD de pyélonéphrite droite » | COMORBIDITE_ANTECEDENT `pyélonéphrite` → `comorbidite_a_pour_foyer` → FOYER `droite` |
| « hospitalisé en 2010 pour choc septique » | COMORBIDITE_ANTECEDENT `choc septique` |

## Bilan

- **Relations** : 34 → **35**.
  - Ajouts : `label_nosologique_a_pour_foyer`, `comorbidite_a_pour_foyer`.
  - Retrait : `presente_suspicion_infection`.
- **Types d'entités** : 20, inchangés. Les définitions de trois d'entre eux sont modifiées.
- **Fichiers** :
  - `Guideline_TRACE_Sepsis_v2.0.json`
  - `labeling_interface_TRACE_Sepsis_v2.0.xml`
