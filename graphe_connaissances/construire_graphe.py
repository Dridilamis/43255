# -*- coding: utf-8 -*-
"""
Construit l'ontologie TRACE-Sepsis et le graphe de connaissances a partir des JSON TRACE.

Entrees
  --guideline  fichier du guideline (ontologie_sepsis_graph), par defaut v2.0 valide medecin
  --entree     dossier des JSON a convertir, par defaut la sortie de l'arbitrage
               (TRACE_v2/sorties/07_arbitrage) ; tout JSON au format de l'extraction convient
  --sortie     dossier de sortie, par defaut graphe_connaissances/sorties
  --base       espace de noms des IRI (par defaut http://example.org/trace-sepsis/)

Sorties
  ontologie/trace_sepsis.ttl          ontologie OWL : 20 classes d'entites, 34 proprietes
                                      d'objet (domaine, image, groupe), proprietes de donnees
  ontologie/trace_sepsis_shapes.ttl   contraintes SHACL des 34 signatures
  graphe/graphe_trace_sepsis.ttl      individus RDF : dossiers, patients, entites, relations,
                                      et pour chaque relation sa preuve et sa confiance
  neo4j/import_neo4j.cypher           script d'import Neo4j (sans APOC)
  neo4j/noeuds.csv, relations.csv     le meme graphe en CSV (Gephi, pandas, Neo4j...)
  graphe/graphe.html                  visualisation interactive, un dossier a la fois
  resume.json                         effectifs et relations hors signature

Uniquement la bibliotheque standard. Les sorties contiennent des donnees de dossiers
(pseudonymises) : elles ne doivent pas etre publiees (dossier ignore par git).
"""
import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ICI = Path(__file__).resolve().parent
PROJET = ICI.parent
GUIDELINE_DEFAUT = PROJET / "guideline" / "Guideline_TRACE_Sepsis_v2.0_valide_medecin.json"
ENTREE_DEFAUT = PROJET / "TRACE_v2" / "sorties" / "07_arbitrage"
SORTIE_DEFAUT = ICI / "sorties"
BASE_DEFAUT = "http://example.org/trace-sepsis/"

TYPES_TECHNIQUES = {"METADONNEES_PIPELINE"}
PATIENT_TYPE = "DONNEE_PATIENT"
PATIENT_RE = re.compile(r"^(le |la |l |cette |ce |du |de la )?(patiente?s?|malade|mme|mr|m|monsieur|madame)$")

GROUPES = {
    "RELATIONS_DIAGNOSTIQUES": "relation diagnostique",
    "RELATIONS_THERAPEUTIQUES": "relation thérapeutique",
    "RELATIONS_SIGNES_VITAUX": "relation des signes vitaux",
    "RELATIONS_BIOMARQUEURS_ET_MICROBIO": "relation des biomarqueurs et de la microbiologie",
    "RELATIONS_TERRAIN_ET_RISQUE": "relation du terrain et du risque",
    "RELATIONS_TEMPORELLES_ET_PRONOSTIC": "relation temporelle et pronostique",
    "RELATIONS_IMAGERIE": "relation d'imagerie",
    "RELATIONS_SYMPTOMES": "relation des symptômes",
}

COULEURS = {
    "DONNEE_PATIENT": "#2a6fdb", "LABEL_NOSOLOGIQUE": "#c0392b", "FOYER_INFECTIEUX": "#e67e22",
    "MICRO_ORGANISME": "#8e44ad", "TRAITEMENT": "#16a085", "POSOLOGIE": "#48c9b0",
    "BIOMARQUEUR": "#2980b9", "SIGNE_VITAL": "#5dade2", "SYMPTOME": "#f1c40f",
    "DEFAILLANCE_ORGANE": "#d35400", "COMORBIDITE_ANTECEDENT": "#7f8c8d",
    "EVENEMENT_TEMPOREL": "#95a5a6", "EVOLUTION_PRONOSTIC": "#34495e", "IMAGERIE_PROCEDURE": "#a569bd",
    "SERVICE_MEDICAL": "#1abc9c", "CONTEXTE_ACQUISITION": "#bdc3c7", "SCORE_SOFA": "#e74c3c",
    "SCORE_qSOFA": "#ec7063", "SCORE_NEUROLOGIQUE": "#af7ac5", "STADE_IRA": "#dc7633",
}


# ---------------------------------------------------------------------------- utilitaires

def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def lit(v):
    """Litteral Turtle (chaine echappee)."""
    s = str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", " ")
    return f'"{s}"'


def nom_local(s):
    s = re.sub(r"[^A-Za-z0-9_]+", "_", str(s)).strip("_")
    return s if s and not s[0].isdigit() else "x" + s


def nombre(v):
    try:
        x = float(str(v).replace(",", ".").strip())
        return x if x == x else None
    except (TypeError, ValueError):
        return None


def lire_guideline(path):
    g = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    g = g.get("ontologie_sepsis_graph", g)
    entites = {k: v for k, v in g["entites"].items() if k not in TYPES_TECHNIQUES}
    groupe_de, desc_rel = {}, {}
    for groupe, rels in (g.get("relations") or {}).items():
        for nom, r in rels.items():
            groupe_de[nom] = groupe
            desc_rel[nom] = r.get("description", "")
    signatures = {nom: (s["domaine"], s["image"], s.get("groupe") or groupe_de.get(nom, ""))
                  for nom, s in g["signatures_relations"].items()}
    return g, entites, signatures, desc_rel


# ---------------------------------------------------------------------------- ontologie

PROPRIETES_DONNEES = [
    ("mention", "mention", "Mention telle qu'elle est écrite dans la page."),
    ("parametre", "paramètre", "Forme canonique du concept (guideline)."),
    ("valeur", "valeur", "Valeur écrite (texte)."),
    ("valeurNumerique", "valeur numérique", "Valeur convertie en nombre lorsque c'est possible."),
    ("unite", "unité", "Unité de la valeur."),
    ("horodatage", "horodatage", "Date ou heure écrite avec l'entité."),
    ("page", "page", "Page du dossier où l'élément est écrit."),
    ("preuve", "preuve", "Passage du dossier qui justifie l'élément."),
    ("nie", "niée", "Vrai si l'entité est explicitement niée (absence conservée comme information)."),
    ("hypothese", "hypothèse", "Vrai si l'entité est seulement suspectée ou évoquée."),
    ("temporalite", "temporalité", "ANTERIEUR, SEJOUR ou SORTIE (étage 6 de TRACE)."),
    ("section", "section", "Section du compte rendu où l'élément est cité."),
    ("confianceModele", "confiance du modèle", "Confiance déclarée par le modèle à l'extraction."),
    ("niveauConfiance", "niveau de confiance TRACE", "HIGH, MEDIUM ou LOW (arbitrage de TRACE)."),
    ("signalFaible", "signal faible", "Signal faible relevé par l'arbitrage."),
    ("origine", "origine", "extraction directe, réparation SGCE ou récupération structurée."),
    ("identifiantSource", "identifiant source", "Identifiant de l'élément dans le JSON TRACE."),
]


def ecrire_ontologie(out, base, g, entites, signatures, desc_rel):
    o = [f"@prefix : <{base}onto#> .",
         "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
         "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
         "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
         "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
         "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .",
         "@prefix dcterms: <http://purl.org/dc/terms/> .", "",
         f"<{base}onto> a owl:Ontology ;",
         f"    rdfs:label {lit('Ontologie ' + str(g.get('nom_guideline', 'TRACE-Sepsis')))}@fr ;",
         f"    owl:versionInfo {lit(g.get('version', ''))} ;",
         "    rdfs:comment \"Ontologie générée à partir du TRACE-Sepsis Annotation Guideline : "
         "types d'entités, signatures des relations et règles dérivées.\"@fr ;"]
    for ref in g.get("references_fondatrices", []) or []:
        o.append(f"    dcterms:source {lit(ref)} ;")
    o[-1] = o[-1].rstrip(" ;") + " ."
    o.append("")

    # classes de structure
    o += [":Dossier a owl:Class ; rdfs:label \"Dossier\"@fr ;",
          "    rdfs:comment \"Dossier médical scanné (identifiant pseudonymisé).\"@fr .",
          ":EntiteClinique a owl:Class ; rdfs:label \"Entité clinique\"@fr .",
          ":Patient a owl:Class ; rdfs:subClassOf :DONNEE_PATIENT ; rdfs:label \"Patient\"@fr ;",
          "    rdfs:comment \"Nœud unique du patient d'un dossier, qui réunit ses mentions (\\\"le patient\\\", \\\"la patiente\\\"...).\"@fr .",
          ":AssertionRelation a owl:Class ;",
          "    rdfs:label \"Assertion de relation\"@fr ;",
          "    rdfs:comment \"Réification d'une relation extraite, qui porte sa preuve, sa page et sa confiance.\"@fr .",
          ":RegleDerivee a owl:Class ; rdfs:label \"Règle dérivée\"@fr ;",
          "    rdfs:comment \"Règle clinique dérivée du guideline, à formaliser en SWRL ou SHACL-SPARQL.\"@fr .",
          "skos:example a owl:AnnotationProperty .",
          "dcterms:source a owl:AnnotationProperty .",
          ":typeRelation a owl:AnnotationProperty ; rdfs:label \"type de relation\"@fr ;",
          "    rdfs:comment \"Propriété (relation du guideline) portée par une assertion.\"@fr .",
          ""]
    # classes d'entites
    for nom, e in entites.items():
        o.append(f":{nom_local(nom)} a owl:Class ; rdfs:subClassOf :EntiteClinique ;")
        o.append(f"    rdfs:label {lit(nom.replace('_', ' ').lower())}@fr ;")
        for v in (e.get("valeurs_autorisees") or [])[:200]:
            o.append(f"    skos:example {lit(v)} ;")
        o.append(f"    rdfs:comment {lit(e.get('description', ''))}@fr .")
    # disjonction des types (une mention = un seul type)
    noms = [f":{nom_local(n)}" for n in entites]
    o += ["", "[] a owl:AllDisjointClasses ; owl:members ( " + " ".join(noms) + " ) .", ""]

    # proprietes de structure
    o += [":issuDuDossier a owl:ObjectProperty ; rdfs:range :Dossier ;",
          "    rdfs:label \"issu du dossier\"@fr .",
          ":aPourPatient a owl:ObjectProperty , owl:FunctionalProperty ; rdfs:domain :Dossier ; rdfs:range :Patient ;",
          "    rdfs:label \"a pour patient\"@fr .",
          ":relationClinique a owl:ObjectProperty ; rdfs:domain :EntiteClinique ; rdfs:range :EntiteClinique ;",
          "    rdfs:label \"relation clinique\"@fr .", ""]
    for groupe, label in GROUPES.items():
        o.append(f":{nom_local(groupe)} a owl:ObjectProperty ; rdfs:subPropertyOf :relationClinique ; rdfs:label {lit(label)}@fr .")
    o.append("")
    for nom, (dom, img, groupe) in signatures.items():
        o.append(f":{nom_local(nom)} a owl:ObjectProperty ;")
        if groupe:
            o.append(f"    rdfs:subPropertyOf :{nom_local(groupe)} ;")
        o.append(f"    rdfs:domain :{nom_local(dom)} ; rdfs:range :{nom_local(img)} ;")
        o.append(f"    rdfs:label {lit(nom.replace('_', ' '))}@fr" + (" ;" if desc_rel.get(nom) else " ."))
        if desc_rel.get(nom):
            o.append(f"    rdfs:comment {lit(desc_rel[nom])}@fr .")
    o.append("")
    for p, label, com in PROPRIETES_DONNEES:
        rng = {"valeurNumerique": "xsd:decimal", "page": "xsd:integer", "nie": "xsd:boolean",
               "hypothese": "xsd:boolean"}.get(p, "xsd:string")
        o.append(f":{p} a owl:DatatypeProperty ; rdfs:range {rng} ; rdfs:label {lit(label)}@fr ; rdfs:comment {lit(com)}@fr .")
    o += ["", ":assertionSujet a owl:ObjectProperty , owl:FunctionalProperty ; rdfs:domain :AssertionRelation ;",
          "    rdfs:range :EntiteClinique ; rdfs:label \"sujet de l'assertion\"@fr .",
          ":assertionObjet a owl:ObjectProperty , owl:FunctionalProperty ; rdfs:domain :AssertionRelation ;",
          "    rdfs:range :EntiteClinique ; rdfs:label \"objet de l'assertion\"@fr .", ""]

    # regles derivees, gardees comme annotations (a formaliser en SWRL / SHACL-SPARQL)
    rd = g.get("regles_derivees") or {}
    for k, v in rd.items():
        if k == "description" or not isinstance(v, str):
            continue
        o.append(f":regle_{nom_local(k)} a owl:NamedIndividual , :RegleDerivee ; rdfs:label {lit(k)} ; rdfs:comment {lit(v)}@fr .")

    (out / "ontologie").mkdir(parents=True, exist_ok=True)
    (out / "ontologie" / "trace_sepsis.ttl").write_text("\n".join(o) + "\n", encoding="utf-8")

    # SHACL : une forme par signature
    s = [f"@prefix : <{base}onto#> .", "@prefix sh: <http://www.w3.org/ns/shacl#> .", ""]
    for nom, (dom, img, _) in signatures.items():
        n = nom_local(nom)
        s += [f":Forme_{n} a sh:NodeShape ;",
              f"    sh:targetSubjectsOf :{n} ;",
              f"    sh:class :{nom_local(dom)} ;",
              f"    sh:message {lit('Le sujet de ' + nom + ' doit etre un ' + dom)} ;",
              f"    sh:property [ sh:path :{n} ; sh:class :{nom_local(img)} ;",
              f"                  sh:message {lit('L objet de ' + nom + ' doit etre un ' + img)} ] .", ""]
    (out / "ontologie" / "trace_sepsis_shapes.ttl").write_text("\n".join(s), encoding="utf-8")


# ---------------------------------------------------------------------------- graphe

def type_entite(e):
    return str(e.get("type") or e.get("categorie") or "").strip()


def nom_dossier(path):
    return re.split(r"_trace_sepsis", Path(path).stem)[0]


def charger(entree):
    docs = []
    for path in sorted(Path(entree).glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            d = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  ignore {path.name} : {exc}")
            continue
        if isinstance(d, dict) and isinstance(d.get("global_entities"), list):
            docs.append((nom_dossier(path), d))
    return docs


def construire(docs, types_valides, signatures):
    """Noeuds et aretes, avec un noeud patient unique par dossier."""
    noeuds, aretes, stats = [], [], Counter()
    hors_signature = Counter()
    for doc, d in docs:
        pid = f"{doc}__patient"
        noeuds.append({"id": pid, "type": "Patient", "classe": PATIENT_TYPE, "label": "Patient",
                       "dossier": doc})
        alias = {}
        for e in d.get("global_entities") or []:
            t, eid = type_entite(e), e.get("identifiant_entite")
            if not eid or t not in types_valides:
                stats["entites_ignorees"] += 1
                continue
            att = (e.get("trace_v2") or {}).get("attributs") or {}
            nom = e.get("name") or e.get("preuve") or e.get("parametre") or ""
            if t == PATIENT_TYPE and PATIENT_RE.match(norm(nom)):
                alias[eid] = pid
                stats["mentions_patient_fusionnees"] += 1
                continue
            nid = f"{doc}__{eid}"
            alias[eid] = nid
            noeuds.append({
                "id": nid, "type": t, "classe": t, "label": str(nom)[:120], "dossier": doc,
                "source": eid, "page": e.get("page"), "parametre": e.get("parametre"),
                "valeur": e.get("valeur"), "unite": att.get("unite") or e.get("unite"),
                "horodatage": e.get("horodatage"), "preuve": e.get("preuve"),
                "nie": bool(att.get("negation", e.get("nie"))), "hypothese": bool(att.get("hypothese")),
                "temporalite": att.get("temporalite"), "section": att.get("section"),
                "confiance_modele": e.get("confiance"), "origine": e.get("type_inference"),
            })
            stats[f"entites:{t}"] += 1
        for r in d.get("global_relations") or []:
            s, o = alias.get(r.get("identifiant_entite_sujet")), alias.get(r.get("identifiant_entite_objet"))
            rel = str(r.get("type_relation") or "")
            if not s or not o or rel not in signatures:
                stats["relations_ignorees"] += 1
                stats["ignoree:" + (rel if rel not in signatures else "extremite_inconnue")] += 1
                continue
            tc = r.get("trace_confidence") or {}
            arb = ((r.get("trace_v2") or {}).get("arbitrage")) or {}
            aretes.append({
                "id": f"{doc}__{r.get('identifiant_relation') or len(aretes)}", "source": s, "cible": o,
                "type": rel, "dossier": doc, "page": r.get("page") or r.get("_page"),
                "preuve": r.get("preuve"), "niveau_confiance": tc.get("level") or arb.get("niveau_confiance"),
                "signaux_faibles": tc.get("signaux_faibles") or arb.get("signaux_faibles") or [],
                "confiance_modele": r.get("confiance"), "origine": r.get("type_inference"),
                "identifiant_source": r.get("identifiant_relation"),
            })
            stats[f"relations:{rel}"] += 1
    # conformite des signatures sur le graphe produit
    classe = {n["id"]: n["classe"] for n in noeuds}
    for a in aretes:
        dom, img, _ = signatures[a["type"]]
        if classe[a["source"]] != dom or classe[a["cible"]] != img:
            a["hors_signature"] = True
            hors_signature[a["type"]] += 1
    return noeuds, aretes, stats, hors_signature


def ecrire_rdf(out, base, noeuds, aretes, dossiers, chemin=None, avant="", assertions=True):
    O, G = f"{base}onto#", f"{base}graphe/"
    L = [f"@prefix : <{O}> .", f"@prefix g: <{G}> .",
         "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
         "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
         "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
         "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .", ""]
    if avant:
        L = [avant, ""]                     # ontologie + individus dans un seul fichier (Protege)
    for doc in dossiers:
        L.append(f"g:{nom_local(doc)} a owl:NamedIndividual , :Dossier ; rdfs:label {lit(doc)} ; :aPourPatient g:{nom_local(doc + '__patient')} .")
    L.append("")
    for n in noeuds:
        iri = f"g:{nom_local(n['id'])}"
        cls = ":Patient" if n["type"] == "Patient" else f":{nom_local(n['classe'])}"
        p = [f"{iri} a owl:NamedIndividual , {cls}", f"rdfs:label {lit(n['label'])}", f":issuDuDossier g:{nom_local(n['dossier'])}"]
        if n["type"] != "Patient":
            p.append(f":mention {lit(n['label'])}")
            for k, prop in (("parametre", "parametre"), ("valeur", "valeur"), ("unite", "unite"),
                            ("horodatage", "horodatage"), ("preuve", "preuve"), ("temporalite", "temporalite"),
                            ("section", "section"), ("confiance_modele", "confianceModele"),
                            ("origine", "origine"), ("source", "identifiantSource")):
                if n.get(k) not in (None, "", []):
                    p.append(f":{prop} {lit(n[k])}")
            x = nombre(n.get("valeur"))
            if x is not None:
                p.append(f':valeurNumerique "{x}"^^xsd:decimal')
            if isinstance(n.get("page"), int):
                p.append(f':page "{n["page"]}"^^xsd:integer')
            p.append(f':nie "{str(n["nie"]).lower()}"^^xsd:boolean')
            p.append(f':hypothese "{str(n["hypothese"]).lower()}"^^xsd:boolean')
        L.append(" ;\n    ".join(p) + " .")
    L.append("")
    etiquette = {n["id"]: n["label"] for n in noeuds}
    for a in aretes:
        s, o, rel = f"g:{nom_local(a['source'])}", f"g:{nom_local(a['cible'])}", f":{nom_local(a['type'])}"
        L.append(f"{s} {rel} {o} .")
        if not assertions:
            continue
        titre = (f"{etiquette.get(a['source'], '?')[:40]} -- {a['type']} --> "
                 f"{etiquette.get(a['cible'], '?')[:40]}")
        p = [f"g:{nom_local('assertion__' + a['id'])} a owl:NamedIndividual , :AssertionRelation",
             f"rdfs:label {lit(titre)}", f":assertionSujet {s}",
             f":typeRelation {rel}", f":assertionObjet {o}", f":issuDuDossier g:{nom_local(a['dossier'])}"]
        for k, prop in (("preuve", "preuve"), ("niveau_confiance", "niveauConfiance"),
                        ("confiance_modele", "confianceModele"), ("origine", "origine"),
                        ("identifiant_source", "identifiantSource")):
            if a.get(k) not in (None, "", []):
                p.append(f":{prop} {lit(a[k])}")
        for sf in a.get("signaux_faibles") or []:
            p.append(f":signalFaible {lit(sf)}")
        if isinstance(a.get("page"), int):
            p.append(f':page "{a["page"]}"^^xsd:integer')
        L.append(" ;\n    ".join(p) + " .")
    chemin = Path(chemin or out / "graphe" / "graphe_trace_sepsis.ttl")
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text("\n".join(L) + "\n", encoding="utf-8")


def ecrire_protege(out, base, noeuds, aretes, dossiers, n, assertions=False):
    """Fichier unique ontologie + individus de n dossiers, a ouvrir dans Protege.

    Les relations hors signature sont exclues : avec rdfs:domain/range et les classes
    disjointes, elles rendraient l'ontologie incoherente pour le raisonneur (HermiT, Pellet).
    La validation SHACL les liste a part. Les fiches des relations (AssertionRelation) ne
    sont ajoutees qu'avec --protege-assertions : elles encombrent OntoGraf ; elles restent
    dans graphe_trace_sepsis.ttl."""
    choix = set(dossiers[:n])
    onto = (out / "ontologie" / "trace_sepsis.ttl").read_text(encoding="utf-8")
    onto = onto.replace(f"<{base}onto> a owl:Ontology ;",
                        f"<{base}protege> a owl:Ontology ;\n    rdfs:seeAlso <{base}onto> ;", 1)
    onto = f"@prefix g: <{base}graphe/> .\n" + onto
    ns = [x for x in noeuds if x["dossier"] in choix]
    ar = [a for a in aretes if a["dossier"] in choix and not a.get("hors_signature")]
    chemin = out / "protege" / f"trace_sepsis_{len(choix)}_dossiers.ttl"
    ecrire_rdf(out, base, ns, ar, [d for d in dossiers if d in choix], chemin=chemin, avant=onto,
               assertions=assertions)
    return chemin, len(ns), len(ar)


def ecrire_owl_xml(out):
    """Copie RDF/XML (.owl) de l'ontologie, si rdflib est installe."""
    try:
        import rdflib
    except ImportError:
        return None
    g = rdflib.Graph()
    g.parse(out / "ontologie" / "trace_sepsis.ttl", format="turtle")
    chemin = out / "ontologie" / "trace_sepsis.owl"
    g.serialize(chemin, format="xml")
    return chemin


def ecrire_neo4j(out, noeuds, aretes):
    d = out / "neo4j"
    d.mkdir(parents=True, exist_ok=True)
    champs_n = ["id", "type", "label", "dossier", "page", "parametre", "valeur", "unite", "horodatage",
                "nie", "hypothese", "temporalite", "section", "confiance_modele", "origine", "preuve"]
    with open(d / "noeuds.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=champs_n, extrasaction="ignore")
        w.writeheader()
        w.writerows(noeuds)
    champs_a = ["id", "source", "cible", "type", "dossier", "page", "niveau_confiance", "confiance_modele",
                "origine", "preuve"]
    with open(d / "relations.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=champs_a, extrasaction="ignore")
        w.writeheader()
        w.writerows(aretes)

    def propre(x):
        return {k: v for k, v in x.items() if v not in (None, "", []) and not isinstance(v, (list, dict))}

    c = ["// Import du graphe TRACE-Sepsis dans Neo4j (Neo4j Browser ou cypher-shell, sans APOC).",
         "// Efface d'abord le graphe existant : a ne lancer que sur une base dediee.",
         "MATCH (n) DETACH DELETE n;",
         "CREATE CONSTRAINT entite_id IF NOT EXISTS FOR (n:Entite) REQUIRE n.id IS UNIQUE;",
         "CREATE CONSTRAINT dossier_id IF NOT EXISTS FOR (d:Dossier) REQUIRE d.id IS UNIQUE;"]
    for doc in sorted({n["dossier"] for n in noeuds}):
        c.append(f"CREATE (:Dossier {{id: {json.dumps(doc)}}});")
    par_type = defaultdict(list)
    for n in noeuds:
        par_type[n["type"]].append(propre(n))
    for t, lst in par_type.items():
        for i in range(0, len(lst), 500):
            c.append(f"UNWIND {json.dumps(lst[i:i + 500], ensure_ascii=False)} AS p "
                     f"CREATE (n:Entite:{t}) SET n = p;")
    c.append("MATCH (n:Entite), (d:Dossier {id: n.dossier}) CREATE (n)-[:ISSU_DU_DOSSIER]->(d);")
    par_rel = defaultdict(list)
    for a in aretes:
        par_rel[a["type"]].append(propre(a))
    for t, lst in par_rel.items():
        for i in range(0, len(lst), 500):
            c.append(f"UNWIND {json.dumps(lst[i:i + 500], ensure_ascii=False)} AS p "
                     f"MATCH (s:Entite {{id: p.source}}), (o:Entite {{id: p.cible}}) "
                     f"CREATE (s)-[r:{t.upper()}]->(o) SET r = p;")
    (d / "import_neo4j.cypher").write_text("\n".join(c) + "\n", encoding="utf-8")


HTML = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Graphe TRACE-Sepsis</title>
__VIS__
<style>
:root{--bg:#fff;--fg:#1d2433;--muted:#5b6475;--panel:#f4f6fa;--line:#d9dee7}
@media (prefers-color-scheme: dark){:root{--bg:#14171d;--fg:#e8ebf1;--muted:#9aa3b2;--panel:#1d212a;--line:#2e3442}}
body{margin:0;font:14px system-ui,sans-serif;background:var(--bg);color:var(--fg);display:flex;flex-direction:column;height:100vh}
header{display:flex;gap:12px;align-items:center;flex-wrap:wrap;padding:10px 16px;border-bottom:1px solid var(--line)}
select,input{font:inherit;padding:4px 6px;background:var(--panel);color:var(--fg);border:1px solid var(--line);border-radius:6px}
main{flex:1;display:flex;min-height:0}#g{flex:1}
aside{width:320px;overflow:auto;padding:12px 16px;border-left:1px solid var(--line);background:var(--panel)}
.leg{display:flex;flex-wrap:wrap;gap:6px 12px;font-size:12px;color:var(--muted)}
.leg span::before{content:"";display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:4px;background:var(--c)}
dt{color:var(--muted);font-size:12px;margin-top:8px}dd{margin:0}
@media (max-width:700px){main{flex-direction:column}aside{width:auto;max-height:40vh;border-left:0;border-top:1px solid var(--line)}}
</style></head><body>
<header><strong>Graphe TRACE-Sepsis</strong>
<label>Dossier <select id="doc"></select></label>
<label><input type="checkbox" id="nie" checked> entités niées</label>
<label><input type="checkbox" id="iso"> entités sans relation</label>
<span id="info" style="color:var(--muted)"></span></header>
<div class="leg" id="leg" style="padding:6px 16px"></div>
<main><div id="g"></div><aside id="det">Cliquez sur un nœud ou une relation.</aside></main>
<script>
const D = __DATA__, C = __COULEURS__;
const sel = document.getElementById('doc');
Object.keys(D).sort().forEach(k => sel.add(new Option(k + ' (' + D[k].n.length + ' nœuds)', k)));
document.getElementById('leg').innerHTML = Object.entries(C).map(([k,c]) => `<span style="--c:${c}">${k}</span>`).join('');
let net;
function esc(s){return String(s ?? '').replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function show(){
  const d = D[sel.value], keep = document.getElementById('nie').checked;
  const iso = document.getElementById('iso').checked;
  let ns = d.n.filter(n => keep || !n.nie), ids = new Set(ns.map(n => n.id));
  const es = d.e.filter(e => ids.has(e.source) && ids.has(e.cible));
  if (!iso) { const lies = new Set(es.flatMap(e => [e.source, e.cible]));
    ns = ns.filter(n => n.type === 'Patient' || lies.has(n.id)); }
  const nodes = new vis.DataSet(ns.map(n => ({id:n.id, label:(n.nie?'¬ ':'') + (n.label||'').slice(0,40),
     color:{background:n.type==='Patient'?'#2a6fdb':(C[n.type]||'#999'), border:n.nie?'#c0392b':'#0000'},
     borderWidth:n.nie?3:1, shape:n.type==='Patient'?'star':'dot', size:n.type==='Patient'?28:12,
     font:{color:getComputedStyle(document.body).color}, raw:n})));
  const edges = new vis.DataSet(es.map(e => ({id:e.id, from:e.source, to:e.cible, arrows:'to',
     label:e.type, font:{size:9, color:'#888', strokeWidth:0}, color:{color:'#8a94a6'},
     dashes:e.niveau_confiance && e.niveau_confiance !== 'HIGH', raw:e})));
  document.getElementById('info').textContent = ns.length + ' nœuds, ' + es.length + ' relations';
  if (net) net.destroy();
  net = new vis.Network(document.getElementById('g'), {nodes, edges},
     {physics:{solver:'forceAtlas2Based', stabilization:{iterations:300}}, interaction:{hover:true}});
  net.once('stabilizationIterationsDone', () => net.setOptions({physics:false}));
  net.on('click', p => {
    const x = p.nodes.length ? nodes.get(p.nodes[0]).raw : p.edges.length ? edges.get(p.edges[0]).raw : null;
    if (!x) return;
    document.getElementById('det').innerHTML = '<dl>' + Object.entries(x).filter(([k,v]) => v !== null && v !== '' && !(Array.isArray(v) && !v.length))
      .map(([k,v]) => `<dt>${esc(k)}</dt><dd>${esc(Array.isArray(v)?v.join(', '):v)}</dd>`).join('') + '</dl>';
  });
}
sel.onchange = show; document.getElementById('nie').onchange = show; document.getElementById('iso').onchange = show; show();
</script></body></html>
"""


def ecrire_html(out, noeuds, aretes):
    par_doc = defaultdict(lambda: {"n": [], "e": []})
    for n in noeuds:
        par_doc[n["dossier"]]["n"].append({k: n.get(k) for k in ("id", "type", "label", "page", "valeur", "unite",
                                                                   "nie", "hypothese", "temporalite", "section",
                                                                   "preuve")})
    for a in aretes:
        par_doc[a["dossier"]]["e"].append({k: a.get(k) for k in ("id", "source", "cible", "type", "page",
                                                                  "niveau_confiance", "signaux_faibles", "preuve")})
    vis = ICI / "vendor" / "vis-network.min.js"     # vis-network 9.1.9, Apache-2.0 OR MIT
    if vis.exists():                                 # page autonome, lisible hors ligne
        balise = "<script>" + vis.read_text(encoding="utf-8").replace("</script", "<\\/script") + "</script>"
    else:
        balise = '<script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>'
    html = HTML.replace("__VIS__", balise).replace("__DATA__", json.dumps(par_doc, ensure_ascii=False).replace("</", "<\\/")) \
               .replace("__COULEURS__", json.dumps(COULEURS))
    (out / "graphe" / "graphe.html").write_text(html, encoding="utf-8")


# ---------------------------------------------------------------------------- principal

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--guideline", default=str(GUIDELINE_DEFAUT))
    ap.add_argument("--entree", default=str(ENTREE_DEFAUT))
    ap.add_argument("--sortie", default=str(SORTIE_DEFAUT))
    ap.add_argument("--base", default=BASE_DEFAUT)
    ap.add_argument("--ontologie-seule", action="store_true", help="ne produit que l'ontologie et SHACL")
    ap.add_argument("--protege-assertions", action="store_true",
                    help="ajoute au fichier Protege les fiches des relations (preuve, confiance)")
    ap.add_argument("--protege", type=int, default=3, metavar="N",
                    help="nombre de dossiers dans le fichier Protege ontologie + individus (0 : aucun)")
    a = ap.parse_args()
    base = a.base if a.base.endswith("/") else a.base + "/"
    out = Path(a.sortie)
    out.mkdir(parents=True, exist_ok=True)

    g, entites, signatures, desc_rel = lire_guideline(a.guideline)
    ecrire_ontologie(out, base, g, entites, signatures, desc_rel)
    print(f"Ontologie : {len(entites)} classes d'entites, {len(signatures)} relations -> {out / 'ontologie'}")
    owl = ecrire_owl_xml(out)
    print(f"  copie RDF/XML : {owl}" if owl else "  (pip install rdflib pour une copie RDF/XML .owl)")
    if a.ontologie_seule:
        return 0

    docs = charger(a.entree)
    if not docs:
        sys.exit(f"Aucun JSON TRACE dans {a.entree}")
    noeuds, aretes, stats, hors = construire(docs, set(entites), signatures)
    dossiers = [d for d, _ in docs]
    ecrire_rdf(out, base, noeuds, aretes, dossiers)
    ecrire_neo4j(out, noeuds, aretes)
    ecrire_html(out, noeuds, aretes)
    if a.protege > 0:
        chemin, nn, na = ecrire_protege(out, base, noeuds, aretes, dossiers, a.protege, a.protege_assertions)
        print(f"Protege : {chemin} ({nn} individus, {na} relations)")

    resume = {
        "entree": str(a.entree), "guideline": str(a.guideline), "dossiers": len(dossiers),
        "noeuds": len(noeuds), "patients": len(dossiers), "relations": len(aretes),
        "mentions_patient_fusionnees": stats["mentions_patient_fusionnees"],
        "entites_ignorees_type_hors_schema": stats["entites_ignorees"],
        "relations_ignorees_extremite_ou_type_inconnu": stats["relations_ignorees"],
        "relations_ignorees_detail": {k.split(":", 1)[1]: v for k, v in sorted(stats.items()) if k.startswith("ignoree:")},
        "relations_hors_signature": dict(hors.most_common()),
        "entites_par_type": {k.split(":", 1)[1]: v for k, v in sorted(stats.items()) if k.startswith("entites:")},
        "relations_par_type": {k.split(":", 1)[1]: v for k, v in sorted(stats.items()) if k.startswith("relations:")},
    }
    (out / "resume.json").write_text(json.dumps(resume, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Graphe : {len(dossiers)} dossiers, {len(noeuds)} noeuds, {len(aretes)} relations "
          f"({sum(hors.values())} hors signature) -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
