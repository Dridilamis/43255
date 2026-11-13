// Requêtes d'exemple pour le graphe importé dans Neo4j (import_neo4j.cypher).

// Vue d'un dossier : le patient et tout ce qui lui est relié
MATCH (p:Patient {dossier: $dossier})-[r]-(x) RETURN p, r, x;

// Diagnostics par patient (diagnostics niés exclus)
MATCH (p:Patient)-[:A_POUR_LABEL_NOSOLOGIQUE]->(d:LABEL_NOSOLOGIQUE)
WHERE NOT d.nie
RETURN p.dossier AS dossier, collect(d.label) AS diagnostics ORDER BY dossier;

// Traitements administrés pendant le séjour aux patients en choc septique
MATCH (p:Patient)-[:A_POUR_LABEL_NOSOLOGIQUE]->(d:LABEL_NOSOLOGIQUE)
WHERE toLower(d.label) CONTAINS 'choc' AND NOT d.nie
MATCH (t:TRAITEMENT)-[:TRAITEMENT_ADMINISTRE_A]->(p)
WHERE coalesce(t.temporalite, 'SEJOUR') <> 'ANTERIEUR'
RETURN p.dossier AS dossier, collect(DISTINCT t.label) AS traitements;

// Traitement et posologie
MATCH (t:TRAITEMENT)-[:TRAITEMENT_A_POUR_POSOLOGIE]->(po:POSOLOGIE)
RETURN t.dossier, t.label, po.label LIMIT 50;

// Relations à vérifier en priorité
MATCH (s)-[r]->(o) WHERE r.niveau_confiance = 'LOW'
RETURN s.dossier, s.label, type(r), o.label, r.preuve LIMIT 50;
