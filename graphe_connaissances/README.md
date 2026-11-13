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

## Ce qui est produit (`graphe_connaissances/sorties/`)

| Fichier | Contenu | Outil |
|---|---|---|
| `ontologie/trace_sepsis.ttl` | 20 classes d'entités (disjointes), 34 propriétés d'objet avec domaine et image, regroupées en 8 familles, propriétés de données, règles dérivées en annotation | Protégé, GraphDB |
| `ontologie/trace_sepsis_shapes.ttl` | une forme SHACL par signature | pySHACL, GraphDB, TopBraid |
| `graphe/graphe_trace_sepsis.ttl` | dossiers, un nœud patient par dossier, entités, relations, et pour chaque relation une assertion réifiée (preuve, page, confiance TRACE, signaux faibles) | GraphDB, Jena, rdflib |
| `neo4j/import_neo4j.cypher` | import complet dans Neo4j, sans APOC | Neo4j Browser, cypher-shell |
| `neo4j/noeuds.csv`, `relations.csv` | le même graphe en tables | Gephi, pandas, Excel |
| `graphe/graphe.html` | visualisation d'un dossier à la fois, autonome (fonctionne hors ligne) | navigateur |
| `resume.json` | effectifs, relations ignorées, relations hors signature | — |

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
