# Ontologie et graphe de connaissances TRACE-Sepsis

Convertit les JSON produits par TRACE en une **ontologie OWL**, des **contraintes SHACL**
et un **graphe de connaissances** (RDF, Neo4j, CSV, page HTML interactive).

## Lancer

Depuis `Reduction_hallucinations` (racine du projet) :

```
python graphe_connaissances/construire_graphe.py
```

Par défaut, l'entrée est la sortie de l'arbitrage (`TRACE_v2/sorties/07_arbitrage`) et le
guideline est `guideline/Guideline_TRACE_Sepsis_v2.0_valide_medecin.json`. Pour une autre
entrée (mode précision, run v2.0, extraction brute…) :

```
python graphe_connaissances/construire_graphe.py --entree TRACE_v2/sorties_v2_0/07_arbitrage_precision
python graphe_connaissances/construire_graphe.py --ontologie-seule     # ontologie et SHACL seulement
```

Le script n'utilise que la bibliothèque standard de Python. La validation SHACL et les requêtes
SPARQL demandent `pip install rdflib pyshacl` :

```
python graphe_connaissances/valider_graphe.py
```

## Ouvrir l'ontologie dans Protégé

1. Installer Protégé (protege.stanford.edu, version 5.6 ou plus récente).
2. **File → Open…** et choisir `graphe_connaissances/ontologie/trace_sepsis.owl`
   (ou `trace_sepsis.ttl` : Protégé lit les deux).
3. Onglets utiles :
   - **Entities → Classes** : `EntiteClinique` et ses 20 sous-classes (une par type du guideline),
     `Patient` sous `DONNEE_PATIENT`, `Dossier`, `AssertionRelation`, `RegleDerivee` ;
   - **Entities → Object properties** : `relationClinique`, ses 8 familles et les 34 relations,
     chacune avec son domaine et son image (*Domains*, *Ranges*) ;
   - **Entities → Annotation properties** : descriptions du guideline (`rdfs:comment`),
     valeurs autorisées (`skos:example`), sources (`dcterms:source`) ;
   - **Individuals by class → RegleDerivee** : les règles dérivées D1 à D11 ;
   - **OntoGraf** (Window → Tabs → OntoGraf) : vue graphique des classes et des relations.
4. **Reasoner → HermiT → Start reasoner** : l'ontologie est cohérente, sans classe insatisfiable
   (vérifié avec HermiT).

Pour voir aussi des **individus** (patients, entités, relations), ouvrir
`sorties/protege/trace_sepsis_3_dossiers.ttl`, produit par `construire_graphe.py`. Ce fichier contient
l'ontologie et les individus de 3 dossiers (option `--protege N` pour en mettre plus ; au-delà
d'une dizaine, Protégé devient lent). Les relations hors signature en sont exclues : avec les
domaines, les images et les classes disjointes, le raisonneur les jugerait incohérentes ; elles
restent dans le graphe complet, où la validation SHACL les liste. Les fiches des relations (`AssertionRelation` : preuve, page, confiance) n'y sont pas, car elles
encombrent OntoGraf ; option `--protege-assertions` pour les ajouter. Ce fichier contient des données
de dossiers : il est dans `sorties/` et n'est pas versionné.

## Ce qui est produit (`graphe_connaissances/sorties/`)

| Fichier | Contenu | Outil |
|---|---|---|
| `ontologie/trace_sepsis.owl` | la même ontologie en RDF/XML (si `rdflib` est installé) | Protégé |
| `ontologie/trace_sepsis.ttl` | 20 classes d'entités (disjointes), 34 propriétés d'objet avec domaine et image, regroupées en 8 familles, propriétés de données, règles dérivées en annotation | Protégé, GraphDB |
| `ontologie/trace_sepsis_shapes.ttl` | une forme SHACL par signature | pySHACL, GraphDB, TopBraid |
| `graphe/graphe_trace_sepsis.ttl` | dossiers, un nœud patient par dossier, entités, relations, et pour chaque relation une assertion réifiée (preuve, page, confiance TRACE, signaux faibles) | GraphDB, Jena, rdflib |
| `neo4j/import_neo4j.cypher` | import complet dans Neo4j, sans APOC | Neo4j Browser, cypher-shell |
| `neo4j/noeuds.csv`, `relations.csv` | le même graphe en tables | Gephi, pandas, Excel |
| `protege/trace_sepsis_3_dossiers.ttl` | ontologie + individus de 3 dossiers, cohérent pour HermiT | Protégé |
| `graphe/graphe.html` | visualisation d'un dossier à la fois, autonome (fonctionne hors ligne) | navigateur |
| `resume.json` | effectifs, relations ignorées, relations hors signature | — |

## Relations d'interprétation (germes, foyers, localisations)

Les règles strictes apprises (`extraction_mistral/guide_appris_v2_0.json`) interdisent à
l'extraction 18 à 19 types de relations d'interprétation, trop rarement justes : le graphe ne
relie alors ni les germes ni les localisations. `relations_interpretation.py` les retrouve a
posteriori par des règles déterministes, ancrées dans une phrase du dossier, sans appel au modèle :

- `micro_organisme_isole_dans` : germe et foyer cités dans la même phrase (moins de 80 caractères),
  ou germe écrit dans la mention du foyer ; chaque germe est relié au foyer le plus proche ;
- `label_nosologique_a_pour_foyer` : diagnostic et localisation dans la même phrase (moins de
  40 caractères) ; chaque localisation est reliée au diagnostic le plus proche ;
- `imagerie_objective_foyer` (option `--imagerie`, désactivée par défaut, voir ci-dessous).

```
python graphe_connaissances/relations_interpretation.py --entree TRACE_v2/sorties_v2_0/07_arbitrage --gold gold_v2_0
python graphe_connaissances/construire_graphe.py --entree graphe_connaissances/sorties/avec_interpretation
```

Chaque relation ajoutée porte sa phrase comme preuve, l'origine `regle_interpretation` et une
confiance moyenne. Mesure sur le Gold Standard v1.6 (43 dossiers), en retirant d'abord les
relations du modèle pour simuler l'interdiction :

| Relation | Ajoutées | Justes | Précision | Rappel | Modèle (run v1.6) |
|---|---|---|---|---|---|
| `micro_organisme_isole_dans` | 37 | 24 | 64,9 % | 20,0 % | 65,7 % / 19,2 % |
| `imagerie_objective_foyer` | 18 | 7 | 38,9 % | 8,9 % | 66,7 % / 12,7 % |

La règle germe → foyer fait aussi bien que le modèle. Le rappel est borné par l'extraction : sur
les 120 relations de référence, 40 seulement ont leurs deux extrémités extraites sur la même page.
La règle d'imagerie fait moins bien que le modèle et reste désactivée.
`label_nosologique_a_pour_foyer` n'existe pas dans le gold v1.6 : sa précision doit être mesurée
avec `--gold gold_v2_0`, comme celle des deux autres règles sur le schéma v2.0.

**Sur le run final v2.0 (49 dossiers, gold v2.0), ces règles ne fonctionnent pas** : 5 relations
germe → foyer ajoutées, aucune juste (87 dans la référence) ; 10 relations diagnostic →
localisation, 2 justes (74 dans la référence). En v2.0, `FOYER_INFECTIEUX` ne désigne plus
qu'une localisation, rarement extraite comme entité distincte : les règles n'ont presque rien à
relier, et les « foyers » restants sont souvent mal typés (des dates). La limite est en amont,
dans l'extraction des localisations, pas dans la liaison. Ne pas utiliser ces relations dans le
graphe v2.0 ; la ligne « plafond » de `--gold` indique combien de relations de référence
auraient pu être retrouvées.

## Choix de modélisation

- **Un nœud patient par dossier.** Les mentions « le patient », « la patiente »… sont fusionnées
  en un nœud `Patient` (sous-classe de `DONNEE_PATIENT`). Les autres `DONNEE_PATIENT` (âge, sexe…)
  restent des entités.
- **Chaque entité reste traçable** : mention, page, preuve, section, négation, hypothèse,
  temporalité (étage 6) et identifiant d'origine dans le JSON TRACE.
- **Les entités niées sont conservées** avec `:nie true` (règle G5 du guideline) ; TRACE a déjà
  retiré les relations qui les donnaient comme présentes.
- **Les relations hors schéma v2.0 sont ignorées** et comptées dans `resume.json`. Les relations
  du schéma dont une extrémité a un type inattendu sont **gardées et signalées** : la validation
  SHACL les liste.
- La validation SHACL se fait **sans inférence RDFS**, sinon `rdfs:domain` et `rdfs:range`
  donneraient le bon type à toute extrémité et masqueraient les violations.
- L'espace de noms par défaut est `http://example.org/trace-sepsis/` (option `--base`).

## Requêtes

`requetes.sparql` (lancées par `valider_graphe.py`) et `requetes.cypher` donnent des exemples :
diagnostics par patient, traitements des patients en choc septique pendant le séjour, lactates
d'au moins 2 mmol/L (règle D1), germes et foyers, relations à vérifier en priorité.

## Données

Les sorties contiennent des informations issues des dossiers, même pseudonymisés :
`graphe_connaissances/sorties/` est ignoré par git et ne doit pas être publié. L'ontologie et les formes SHACL, qui ne contiennent aucune donnée de dossier, sont aussi versionnées dans `ontologie/`. La page HTML
embarque vis-network 9.1.9 (licence Apache-2.0 ou MIT, `vendor/`) et ne charge rien depuis
Internet.
