# -*- coding: utf-8 -*-
"""
TRACE - EXTRACTION MISTRAL SMALL 4 SELON LE GUIDELINE TRACE-Sepsis (v2.0 par defaut)

Nouvelle extraction des dossiers (PDF scannes), page par page :
  1. la page est convertie en image (500 dpi) et lue par Mistral (lecture visuelle directe) ;
  2. Mistral extrait les entites, avec un prompt construit A PARTIR DU GUIDELINE
     (types, valeurs autorisees, regles de typage, synonymes) ;
  3. Mistral extrait les relations parmi les signatures du guideline (34) ;
  4. validation deterministe, fondee uniquement sur le guideline et le texte de la page :
     entite retrouvee mot pour mot dans le texte, type autorise, signature de relation valide.

Contrairement a l'ancienne chaine (mistral_engine.py), AUCUNE regle n'est construite a partir
du gold : pas de rappel "Gold-like", pas de seuils choisis sur les erreurs observees. La sortie
est donc une extraction "brute v1.7" honnete, directement utilisable par TRACE v2.

Usage (depuis Reduction_hallucinations) :
    python extraction_mistral\\extraction_v1_7.py --essai                 # 1 dossier, pour verifier
    python extraction_mistral\\extraction_v1_7.py                         # tous les PDF du dossier
    python extraction_mistral\\extraction_v1_7.py --pdfs "C:\\...\\mes_pdfs" --pause 3
    python extraction_mistral\\extraction_v1_7.py --guideline guideline\\Guideline_TRACE_Sepsis_v1.7.json

La cle API est lue dans MISTRAL_API_KEY, sinon demandee au clavier (jamais ecrite sur disque).
Toutes les reponses de Mistral sont mises en cache : une relance ne repaie pas les appels faits.
"""
import argparse
import getpass
import hashlib
import json
from collections import Counter
import math
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
GUIDELINE = PROJECT / "guideline" / "Guideline_TRACE_Sepsis_v2.0.json"
DEFAULT_PDFS = PROJECT.parent / "suite pdfs annotés"
DEFAULT_OUT = HERE / "extraction_v2_0"
URL = "https://api.mistral.ai/v1/chat/completions"
MODEL = "mistral-small-2603"
VERSION = "extraction_guideline_seul"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# ------------------------------------------------------------------ outils
def norm(text):
    text = unicodedata.normalize("NFD", str(text or "").lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def find_spans(surface, page_text):
    """Toutes les positions de la surface dans le texte de la page (casse et espaces ignores)."""
    surface = str(surface or "").strip()
    if len(surface) < 2:
        return []
    pattern = r"\s+".join(re.escape(t) for t in surface.split())
    return [(m.start(), m.end(), m.group(0)) for m in re.finditer(pattern, page_text, re.IGNORECASE)]


def find_span(surface, page_text):
    """Premiere position de la surface dans la page, ou None."""
    spans = find_spans(surface, page_text)
    return spans[0] if spans else None


def parse_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", str(text or "").strip(), flags=re.MULTILINE).strip()
    for candidate in (text, (re.search(r"\{.*\}", text, re.DOTALL) or [None])[0]):
        if candidate:
            try:
                data = json.loads(candidate)
                if isinstance(data, dict):
                    return data
            except (json.JSONDecodeError, TypeError):
                pass
    return {}


# ------------------------------------------------------------------ API Mistral
class Mistral:
    def __init__(self, cache_dir, pause=1.5):
        self.key = os.getenv("MISTRAL_API_KEY", "").strip()
        self.session = requests.Session()
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.pause, self.last, self.calls = pause, 0.0, 0

    def ask(self, content, json_mode, max_tokens):
        key = hashlib.sha256(f"{MODEL}|{json_mode}|{json.dumps(content, ensure_ascii=False)}".encode()).hexdigest()
        cached = self.cache / f"{key}.json"
        if cached.exists():
            return json.loads(cached.read_text(encoding="utf-8"))["reponse"]
        if not self.key:
            raise RuntimeError("MISTRAL_API_KEY absente.")
        payload = {"model": MODEL, "temperature": 0, "max_tokens": max_tokens,
                   "messages": [{"role": "user", "content": content}]}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        for attempt in range(15):
            wait_more = self.pause - (time.monotonic() - self.last)
            if wait_more > 0:
                time.sleep(wait_more)
            self.last = time.monotonic()
            try:
                r = self.session.post(URL, json=payload, timeout=(30, 300),
                                      headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
            except requests.RequestException as exc:
                time.sleep(min(60, 2 ** attempt))
                print(f"    reseau : {exc} - nouvel essai")
                continue
            if r.status_code in (429, 500, 502, 503, 504):
                try:
                    retry_after = float(r.headers.get("Retry-After", 0))
                except ValueError:
                    retry_after = 0
                if r.status_code == 429:
                    self.pause = min(10.0, self.pause * 1.5)
                wait = max(retry_after, min(60, 5 * 2 ** attempt))
                print(f"    Mistral {r.status_code} - nouvel essai dans {wait:.0f} s (pause {self.pause:.1f} s)")
                time.sleep(wait)
                continue
            if r.status_code == 401:
                raise RuntimeError("Mistral 401 : cle API refusee.")
            if r.status_code != 200:
                raise RuntimeError(f"Mistral {r.status_code} : {r.text[:300]}")
            self.calls += 1
            reponse = r.json()["choices"][0]["message"]["content"]
            cached.write_text(json.dumps({"reponse": reponse}, ensure_ascii=False), encoding="utf-8")
            return reponse
        raise RuntimeError("Mistral refuse apres 15 essais : relancez plus tard avec --pause 5 (cache conserve).")


# ------------------------------------------------------------------ prompts construits depuis le guideline
TRANSCRIPTION = """Tu es un modele vision-langage medical. Transcris fidelement le texte visible de cette page.
- Ne resume pas, ne reformule pas, ne corrige pas l'orthographe.
- Ne complete aucune information absente ; une zone illisible s'ecrit [?].
- Conserve les abreviations, les retours a la ligne et l'ordre de lecture.
- Retourne uniquement le texte, sans commentaire ni Markdown."""


def guideline():
    return json.loads(GUIDELINE.read_text(encoding="utf-8"))["ontologie_sepsis_graph"]


def nom_guideline(g):
    return g.get("nom_guideline") or f"TRACE-Sepsis v{g.get('version', '?')}"


def _vals(spec):
    for k in ("valeurs_autorisees", "localisations", "types", "organes", "manifestations_autorisees",
              "valeurs_autorisees_type_service", "composantes"):
        if isinstance(spec.get(k), list):
            yield k, spec[k]


def prompt_entites(g, page_text, exemples=""):
    blocs = []
    for t, spec in g["entites"].items():
        if t == "METADONNEES_PIPELINE":
            continue
        lignes = [f"### {t}\n{spec.get('description', '')}"]
        for k, v in _vals(spec):
            lignes.append(f"  {k} : {', '.join(map(str, v))}")
        for k in ("notes", "notes_valeurs", "regles", "regles_validation", "note"):
            if spec.get(k):
                lignes.append(f"  {k} : {json.dumps(spec[k], ensure_ascii=False)}")
        blocs.append("\n".join(lignes))
    typage = "\n".join(f"- {k} : {v['regle']} Exemples : {json.dumps(v.get('exemples', {}), ensure_ascii=False)}"
                       for k, v in g["regles_de_typage"].items())
    regles = "\n".join(f"- {k} : {v}" for k, v in g["regles_generales_annotation"].items())
    synonymes = json.dumps({k: v for k, v in g["normalisation_terminologique"].items() if isinstance(v, dict)},
                           ensure_ascii=False)
    return f"""Tu es un expert en extraction d'information clinique sur le sepsis. Applique strictement le
guideline {nom_guideline(g)} ci-dessous a la page de compte rendu fournie.

MISSION : extraire de facon EXHAUSTIVE toutes les entites cliniques explicitement ecrites dans la page.

REGLES ABSOLUES :
- "texte" = la surface EXACTE, copiee mot pour mot dans la page (la plus courte expression autonome).
- Une mention recoit UN SEUL type. Aucune entite deduite de connaissances medicales externes.
- Un diagnostic infectieux (pneumopathie, PAVM, abces, pyelonephrite, erysipele, sinusite) est un
  LABEL_NOSOLOGIQUE ; sa localisation, si elle est ecrite, est une entite FOYER_INFECTIEUX distincte.
- Une information niee est extraite avec "nie": true ; une hypothese avec "hypothese": true.
- Reconnais les synonymes et abreviations ; "parametre" = forme canonique (voir synonymes).
- Les donnees du patient sont celles de l'admission. N'extrais pas de donnee directement identifiante.
- TRAITEMENT et POSOLOGIE sont deux entites DISTINCTES (definition de POSOLOGIE ci-dessous) :
  le TRAITEMENT est le nom du medicament ou de l'intervention seul ("Claforan") ; la dose, le
  schema horaire, le debit, la voie et la duree forment une entite POSOLOGIE separee
  ("1g x 3 par jour"). Ne mets jamais la posologie dans le texte du TRAITEMENT.
- Le patient lui-meme est une entite DONNEE_PATIENT : chaque mention qui le designe dans la page
  ("patient", "la patiente", "Mr X.", "patient de 66 ans") est extraite en DONNEE_PATIENT, car
  c'est elle qui sert de sujet ou d'objet aux relations du patient (a_pour_label_nosologique,
  traitement_administre_a, presente_symptome...). DONNEE_PATIENT ne s'applique JAMAIS a un titre de
  section ("Examen cutane", "Biologie"), a un examen, a un resultat ni a un evenement.
- Les traitements des listes d'ordonnance (traitement habituel, traitement de sortie) sont aussi
  extraits : un TRAITEMENT par medicament et sa POSOLOGIE.

REGLES GENERALES :
{regles}

REGLES DE TYPAGE :
{typage}

SYNONYMES (surface -> forme canonique) :
{synonymes}

TYPES D'ENTITES :
{chr(10).join(blocs)}

FORMAT DE SORTIE (JSON uniquement) :
{{"entites": [{{"categorie": "TYPE", "texte": "surface exacte", "parametre": "forme canonique ou null",
  "valeur": null, "unite": null, "nie": false, "hypothese": false, "confiance": "elevee|moyenne|faible",
  "type_inference": "extraction_directe"}}]}}

{exemples}
PAGE :
\"\"\"{page_text}\"\"\""""


FAMILLE_TRAITEMENT = ("TRAITEMENT", "POSOLOGIE")
PAR_FAMILLES = False  # option --par-familles : une consigne par famille d'entites (essai : pas de gain)
# DONNEE_PATIENT (guideline) : le patient et ses donnees demographiques. Une mention de ce type doit
# designer le patient ou porter une de ces donnees ; un titre ("Sur le plan renal") est rejete.
PATIENT_OK_RE = re.compile(r"\b(patiente?s?|mr|mme|monsieur|madame|homme|femme|sexe|ans?|age|ag[ée]e?|"
                           r"poids|kg|taille|cm|imc|n[ée]e?\s+le|date\s+de\s+naissance)\b|\bm\.", re.IGNORECASE)
PATIENT_RE = re.compile(r"\b(?:(?:le|la|un|une|cette|ce|du|de la)\s+)?patiente?\b(?:\s+de\s+\d{1,3}\s*ans)?",
                        re.IGNORECASE)


def prompt_traitements(g, page_text, exemples=""):
    """Seconde consigne, ciblee : traitements et posologies seulement (definitions du guideline)."""
    blocs = []
    for t in FAMILLE_TRAITEMENT:
        spec = g["entites"][t]
        lignes = [f"### {t}\n{spec.get('description', '')}"]
        for k, v in _vals(spec):
            lignes.append(f"  {k} : {', '.join(map(str, v))}")
        for k in ("note", "notes_valeurs", "attributs", "note_attributs"):
            if spec.get(k):
                lignes.append(f"  {k} : {json.dumps(spec[k], ensure_ascii=False)}")
        blocs.append("\n".join(lignes))
    regle = g["regles_de_typage"].get("TRAITEMENT_reel_vs_envisage", {})
    return f"""Tu es un expert en pharmacologie clinique. Applique le guideline {nom_guideline(g)} a la page fournie.

MISSION : extraire de facon EXHAUSTIVE tous les TRAITEMENTS et toutes les POSOLOGIES ecrits dans la
page, y compris dans les listes d'ordonnance (traitement habituel, traitement de sortie), les
tableaux et les formulaires.

REGLES :
- Un TRAITEMENT = un medicament ou une intervention, avec son nom seul tel qu'ecrit ("Claforan",
  "noradrenaline", "remplissage"). Une ligne qui cite plusieurs medicaments donne plusieurs TRAITEMENT.
- La dose, le schema horaire, le debit, la voie et la duree forment une POSOLOGIE separee, copiee
  telle qu'ecrite ("1g x 3 par jour", "1-0-1", "12 mg/h"). Ne mets jamais la posologie dans le
  texte du TRAITEMENT.
- "texte" = surface EXACTE, copiee mot pour mot dans la page.
- Traitement seulement envisage, discute ou propose : "hypothese": true. Traitement nie ou arrete : "nie": true.
  {regle.get('regle', '')}

DEFINITIONS :
{chr(10).join(blocs)}

FORMAT DE SORTIE (JSON uniquement) :
{{"entites": [{{"categorie": "TRAITEMENT|POSOLOGIE", "texte": "surface exacte", "parametre": null,
  "valeur": null, "unite": null, "nie": false, "hypothese": false, "confiance": "elevee|moyenne|faible",
  "type_inference": "extraction_directe"}}]}}

{exemples}
PAGE :
\"\"\"{page_text}\"\"\""""


FAMILLES = {
    "biologie": {
        "types": ("BIOMARQUEUR", "SIGNE_VITAL", "SCORE_SOFA", "SCORE_qSOFA", "SCORE_NEUROLOGIQUE", "STADE_IRA"),
        "expert": "biologie clinique et reanimation",
        "mission": "tous les resultats biologiques, parametres vitaux et scores ecrits dans la page, y compris"
                   " dans les tableaux de biologie et les gaz du sang",
        "regles": ["Une mesure = UNE entite qui reunit le nom du parametre, sa valeur et son unite, telle"
                   " qu'ecrite (\"CRP 245 mg/L\", \"FC 120/min\", \"Glasgow 8\").",
                   "Chaque ligne d'un tableau de biologie qui donne une valeur est une entite.",
                   "Un nom de parametre sans valeur, ou une valeur sans parametre, n'est pas extrait."]},
    "clinique": {
        "types": ("SYMPTOME", "DEFAILLANCE_ORGANE"),
        "expert": "semiologie medicale",
        "mission": "tous les symptomes et signes cliniques (interrogatoire, examen clinique) et toutes les"
                   " defaillances d'organe ecrits dans la page",
        "regles": ["Un signe present est une mention courte (\"marbrures\", \"dyspnee\").",
                   "Une absence (\"pas de toux\", \"absence de marbrures\") est UNE seule mention couvrant la"
                   " proposition niee, avec \"nie\": true.",
                   "Une DEFAILLANCE_ORGANE n'est extraite que si la dysfonction est ecrite ; une valeur"
                   " biologique anormale seule n'est pas une defaillance."]},
    "diagnostic": {
        "types": ("LABEL_NOSOLOGIQUE", "COMORBIDITE_ANTECEDENT", "FOYER_INFECTIEUX", "MICRO_ORGANISME",
                  "CONTEXTE_ACQUISITION", "IMAGERIE_PROCEDURE"),
        "expert": "infectiologie et reanimation",
        "mission": "tous les diagnostics, antecedents, foyers infectieux, germes, contextes d'acquisition et"
                   " examens d'imagerie ou procedures ecrits dans la page",
        "regles": ["Un diagnostic de la liste LABEL_NOSOLOGIQUE reste LABEL_NOSOLOGIQUE meme s'il est ancien ;"
                   " tout autre antecedent est une COMORBIDITE_ANTECEDENT.",
                   "FOYER_INFECTIEUX = seulement la localisation ecrite d'un diagnostic infectieux.",
                   "Un germe est extrait tel qu'ecrit (\"E. coli\", \"pneumocoque\")."]},
    "parcours": {
        "types": ("DONNEE_PATIENT", "EVENEMENT_TEMPOREL", "EVOLUTION_PRONOSTIC", "SERVICE_MEDICAL"),
        "expert": "dossier patient",
        "mission": "le patient (ses mentions et ses donnees demographiques), les evenements dates, l'evolution"
                   " et les services de prise en charge ecrits dans la page",
        "regles": ["DONNEE_PATIENT : les mentions qui designent le patient (\"le patient\", \"la patiente de"
                   " 77 ans\") et ses donnees demographiques (\"77 ans\", \"Poids : 70 kg\"). Jamais un titre.",
                   "EVENEMENT_TEMPOREL : une date ou un moment ecrit (\"le 03/05/2013\", \"J3\").",
                   "SERVICE_MEDICAL : le type de service (\"reanimation\", \"urgences\"), sans nom d'hopital."]},
}


def prompt_famille(g, page_text, famille, exemples=""):
    """Consigne ciblee sur une famille d'entites (definitions et regles de typage du guideline)."""
    f = FAMILLES[famille]
    blocs = []
    for t in f["types"]:
        spec = g["entites"][t]
        lignes = [f"### {t}\n{spec.get('description', '')}"]
        for k, v in _vals(spec):
            lignes.append(f"  {k} : {', '.join(map(str, v))}")
        for k in ("notes", "notes_valeurs", "regles", "regles_validation", "note"):
            if spec.get(k):
                lignes.append(f"  {k} : {json.dumps(spec[k], ensure_ascii=False)}")
        blocs.append("\n".join(lignes))
    typage = "\n".join(f"- {k} : {v['regle']}" for k, v in g["regles_de_typage"].items()
                       if any(t.split("_")[0] in k for t in f["types"]))
    synonymes = json.dumps({k: v for k, v in g["normalisation_terminologique"].items()
                            if isinstance(v, dict) and k in f["types"]}, ensure_ascii=False)
    return f"""Tu es un expert en {f['expert']}. Applique le guideline {nom_guideline(g)} a la page fournie.

MISSION : extraire de facon EXHAUSTIVE {f['mission']}. N'extrais AUCUN autre type que : {', '.join(f['types'])}.

REGLES :
- "texte" = surface EXACTE, copiee mot pour mot dans la page. Aucune entite deduite de connaissances externes.
{chr(10).join('- ' + r for r in f['regles'])}
- Une hypothese ou une suspicion : "hypothese": true.
{typage}

SYNONYMES : {synonymes}

DEFINITIONS :
{chr(10).join(blocs)}

FORMAT DE SORTIE (JSON uniquement) :
{{"entites": [{{"categorie": "TYPE", "texte": "surface exacte", "parametre": "forme canonique ou null",
  "valeur": null, "unite": null, "nie": false, "hypothese": false, "confiance": "elevee|moyenne|faible",
  "type_inference": "extraction_directe"}}]}}

{exemples}
PAGE :
\"\"\"{page_text}\"\"\""""


def ancre_patient(entites, page_text, page_no):
    """Regle deterministe : si la page nomme le patient ("le patient", "la patiente de 77 ans") et
    qu'aucune entite DONNEE_PATIENT ne le designe deja, la premiere mention devient l'entite patient
    de la page (sujet ou objet des relations du patient). Aucune information clinique n'est creee."""
    if any(e["categorie"] == "DONNEE_PATIENT" and PATIENT_RE.search(e["name"]) for e in entites):
        return None
    m = PATIENT_RE.search(page_text)
    if not m:
        return None
    return {"identifiant_entite": f"P{page_no}_E{len(entites) + 1:03d}", "categorie": "DONNEE_PATIENT",
            "type": "DONNEE_PATIENT", "name": m.group(0), "preuve": m.group(0), "parametre": None,
            "valeur": None, "unite": None, "nie": False, "hypothese": False, "confiance": "elevee",
            "type_inference": "regle_ancre_patient", "page": page_no, "start": m.start(), "end": m.end()}


# ------------------------------------------------------------------ exemples annotes (validation croisee)


POOL = {}       # cle de dossier -> pages annotees de l'AUTRE moitie (candidates comme exemples)
N_EXEMPLES = 2
_MOT = re.compile(r"[a-z0-9]{3,}")


def _sac(texte):
    return Counter(_MOT.findall(norm(texte)))


def preparer_exemples(gold_dir, n_pages):
    """Exemples annotes en VALIDATION CROISEE a 2 plis, avec les memes plis que l'etage 8 de TRACE
    (dossiers tries, rangs pairs / impairs) : un dossier ne recoit que des pages annotees de
    l'AUTRE moitie, jamais sa propre annotation. Pour chaque page a extraire, on choisit les pages
    annotees les plus SEMBLABLES (similarite cosinus TF-IDF des mots) : une page de biologie recoit
    des exemples de biologie, une ordonnance des exemples d'ordonnance."""
    global N_EXEMPLES
    N_EXEMPLES = n_pages
    docs = sorted((json.loads(f.read_text(encoding="utf-8")) for f in Path(gold_dir).glob("*.json")),
                  key=lambda d: d["document"])
    plis = [docs[0::2], docs[1::2]]
    for k in (0, 1):
        pages = []
        for d in plis[1 - k]:
            for pg in d["pages"]:
                if pg["entities"] and 300 <= len(pg.get("text", "")) <= 3000:
                    pages.append({"texte": pg["text"].strip(), "sac": _sac(pg["text"]),
                                  "entites": [{"categorie": x["type"], "texte": x["name"]} for x in pg["entities"]],
                                  "relations": [f"{r['subject']} [{r['subject_type']}] | {r['relation']} | "
                                                f"{r['object']} [{r['object_type']}]" for r in pg["relations"]]})
        df = Counter(m for pg in pages for m in pg["sac"])
        n = len(pages)
        for pg in pages:
            pg["vec"] = {m: c * math.log(n / df[m]) for m, c in pg["sac"].items()}
            pg["norme"] = math.sqrt(sum(v * v for v in pg["vec"].values())) or 1.0
        for d in plis[k]:
            POOL[d["document"]] = (pages, df, n)


def _semblables(doc, page_text):
    pages, df, n = POOL[doc]
    sac = _sac(page_text)
    vec = {m: c * math.log(n / df[m]) for m, c in sac.items() if m in df}
    norme = math.sqrt(sum(v * v for v in vec.values())) or 1.0
    score = [(sum(v * pg["vec"].get(m, 0.0) for m, v in vec.items()) / (norme * pg["norme"]), i)
             for i, pg in enumerate(pages)]
    score.sort(key=lambda x: (-x[0], x[1]))
    choix, vus = [], set()
    for _, i in score:
        if pages[i]["texte"][:200] not in vus:     # pas deux fois la meme page
            vus.add(pages[i]["texte"][:200])
            choix.append(pages[i])
        if len(choix) == N_EXEMPLES:
            break
    return choix


def bloc_exemples(doc, cle, page_text=""):
    if doc not in POOL:
        return ""
    blocs = []
    for i, pg in enumerate(_semblables(doc, page_text), start=1):
        if cle == "relations":
            contenu = "relations annotees :\n" + "\n".join(pg["relations"])
        elif cle in FAMILLES:
            contenu = "entites annotees :\n" + json.dumps(
                {"entites": [x for x in pg["entites"] if x["categorie"] in FAMILLES[cle]["types"]]},
                ensure_ascii=False)
        elif cle == "traitements":
            contenu = "traitements et posologies annotes :\n" + json.dumps(
                {"entites": [x for x in pg["entites"] if x["categorie"] in FAMILLE_TRAITEMENT]}, ensure_ascii=False)
        else:
            contenu = "entites annotees :\n" + json.dumps({"entites": pg["entites"]}, ensure_ascii=False)
        blocs.append(f"EXEMPLE {i} - texte :\n\"\"\"{pg['texte']}\"\"\"\n{contenu}")
    return ("\nEXEMPLES ANNOTES (pages semblables d'autres dossiers, meme guideline) : ils montrent la"
            " convention d'annotation (decoupage des mentions, types, posologie separee, mention du patient,"
            " absences). Ne recopie jamais leur contenu : extrais uniquement ce qui est ecrit dans la PAGE.\n"
            + "\n\n".join(blocs) + "\n")


# ------------------------------------------------------------------ regles strictes apprises (validation croisee)
GUIDE = {}      # cle de dossier -> regles de sa moitie (apprises sur l'AUTRE moitie, apprendre_guide.py)
NEG_MENTION = re.compile(r"^\s*(pas d|absence|sans |ni |non |aucun)", re.IGNORECASE)


def charger_guide(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for pli in data["plis"]:
        regles = {"relations_interdites": set(pli["relations_interdites"]),
                  "profils_interdits": {tuple(x) for x in pli["profils_interdits"]},
                  "precision_types": pli["precision_types"], "longueur_mots_gold": pli["longueur_mots_gold"]}
        for d in pli["documents"]:
            GUIDE[d] = regles


def profil_entite(cat, texte):
    texte = str(texte or "")
    return (cat, bool(NEG_MENTION.match(texte)), bool(re.search(r"\d", texte)), len(texte.split()) >= 6)


def entite_interdite(doc, cat, texte):
    r = GUIDE.get(doc)
    p = profil_entite(cat, texte)
    return bool(r) and not p[1] and p in r["profils_interdits"]


def _decrire_profils(profils):
    par = {}
    for cat, neg, chiffre, long_ in sorted(profils):
        if not neg:
            par.setdefault((cat, chiffre), set()).add(long_)
    out = []
    for (cat, chiffre), longs in sorted(par.items()):
        s = f"{cat} " + ("contenant un chiffre" if chiffre else "sans aucun chiffre ni date")
        if longs == {True}:
            s += " de 6 mots ou plus"
        elif longs == {False}:
            s += " de moins de 6 mots"
        out.append(s)
    return out


def bloc_regles(doc, cle, types=None):
    r = GUIDE.get(doc)
    if not r:
        return ""
    if types:
        r = {**r, "profils_interdits": {p for p in r["profils_interdits"] if p[0] in types},
             "precision_types": {k: v for k, v in r["precision_types"].items() if k in types},
             "longueur_mots_gold": {k: v for k, v in r["longueur_mots_gold"].items() if k in types}}
    if cle == "relations":
        return ("\nREGLES STRICTES (apprises sur d'autres dossiers annotes, a respecter imperativement) :\n"
                "- N'utilise QUE les relations listees ci-dessus ; les relations d'interpretation suivantes sont"
                f" INTERDITES : {', '.join(sorted(r['relations_interdites']))}.\n"
                "- Aucune relation vers une entite niee (absence, \"pas de ...\") : une absence n'a pas de relation.\n"
                "- Une relation exige une phrase de la page qui l'enonce. En cas de doute, ne l'extrais pas.\n")
    peu_fiables = sorted(t for t, p in r["precision_types"].items() if p < 0.5)
    longueurs = ", ".join(f"{t} <= {int(round(v)) + 1} mots" for t, v in sorted(r["longueur_mots_gold"].items()))
    lignes = ["", "REGLES STRICTES (apprises sur d'autres dossiers annotes, a respecter imperativement) :",
              ("- N'extrais JAMAIS : " + " ; ".join(_decrire_profils(r["profils_interdits"])) + ".")
              if _decrire_profils(r["profils_interdits"]) else "",
              f"- Mentions COURTES, sans phrase entiere ni titre de section : {longueurs}.",
              ("- Types peu fiables : " + ", ".join(peu_fiables) + ". N'extrais ces types que si la mention"
               " correspond exactement a leur definition du guideline ; en cas de doute, ne l'extrais pas.")
              if peu_fiables else "",
              "- Une absence (\"pas de toux\", \"absence de marbrures\") est UNE seule mention couvrant la"
              " proposition niee, avec \"nie\": true.", ""]
    return "\n".join(lignes)


def relations_possibles(g, entites, interdites=()):
    """Relations du guideline realisables sur la page : un sujet du type domaine ET un objet du
    type image existent parmi les entites validees. Avec, pour chacune, les identifiants permis."""
    par_type = {}
    for e in entites:
        par_type.setdefault(e["categorie"], []).append(e["identifiant_entite"])
    out = []
    for groupe, rels in g["relations"].items():
        for k, v in rels.items():
            sujets, objets = par_type.get(v["domaine"], []), par_type.get(v["image"], [])
            if sujets and objets and k not in interdites:
                out.append((k, v, sujets, objets))
    return out


def prompt_relations(g, page_text, entites, exemples="", interdites=()):
    ordre = sorted(entites, key=lambda e: (e["categorie"], e["identifiant_entite"]))
    liste = "\n".join(f"- {e['identifiant_entite']} [{e['categorie']}] {e['name']}" for e in ordre)
    sigs = []
    for k, v, sujets, objets in relations_possibles(g, entites, interdites):
        sigs.append(f"- {k} : {v['domaine']} -> {v['image']}. {v.get('description', '')}\n"
                    f"    sujet parmi : {', '.join(sujets)}\n    objet parmi : {', '.join(objets)}")
    regles = "\n".join(f"- {k} : {v}" for k, v in g["regles_generales_annotation"].items()
                       if k in ("R6_hypothese_traitement", "R7_relations", "R8_inference", "R10_baseline",
                                "R13_rattachement_foyer"))
    return f"""Tu es un expert en extraction de relations cliniques sur le sepsis (guideline {nom_guideline(g)}).
A partir de la page et de la liste d'entites ci-dessous, extrais TOUTES les relations explicitement
supportees par le texte de la page, et uniquement celles-ci.

REGLES :
- Utilise uniquement les relations listees ci-dessous. Pour chacune, le sujet DOIT etre choisi dans
  sa liste "sujet parmi" et l'objet dans sa liste "objet parmi" : verifie le type entre crochets
  de chaque identifiant avant de l'utiliser.
- Si aucune entite du bon type ne correspond au lien ecrit, ne cree pas la relation : n'utilise
  jamais une entite d'un autre type a la place.
- N'inverse jamais le sens d'une relation pour la rendre valide.
- Une relation plausible mais non ecrite dans la page n'est pas extraite. Deux entites presentes
  sur la meme page ne sont pas liees pour autant : les relations d'interpretation (indication,
  cible, facteur de risque, critere, orientation) exigent une phrase qui enonce le lien.
- "preuve" = le passage exact de la page qui justifie la relation.
{regles}

RELATIONS POSSIBLES SUR CETTE PAGE ({len(sigs)}) :
{chr(10).join(sigs)}

ENTITES (classees par type) :
{liste}

FORMAT DE SORTIE (JSON uniquement) :
{{"relations": [{{"sujet": "ID", "type_relation": "nom", "objet": "ID", "preuve": "passage exact",
  "confiance": "elevee|moyenne|faible"}}]}}

{exemples}
PAGE :
\"\"\"{page_text}\"\"\""""


# ------------------------------------------------------------------ validation deterministe (guideline seul)
def valider_entites(g, raw, page_text, page_no, c):
    types = set(g["entites"]) - {"METADONNEES_PIPELINE"}
    out, vus = [], set()
    for e in raw.get("entites", []) or []:
        if not isinstance(e, dict):
            continue
        cat = str(e.get("categorie") or "").strip().upper().replace("SCORE_QSOFA", "SCORE_qSOFA")
        if cat not in types:
            c["entites_type_inconnu"] += 1
            continue
        if cat == "DONNEE_PATIENT" and not PATIENT_OK_RE.search(str(e.get("texte") or "")):
            c["entites_patient_invalides"] += 1
            continue
        spans = find_spans(e.get("texte"), page_text)
        if not spans:
            c["entites_non_ancrees"] += 1
            continue
        # une mention repetee (ex. "1-0-0" sur chaque ligne d'ordonnance) prend l'occurrence
        # suivante encore libre, au lieu d'etre fusionnee avec la premiere
        libre = [s for s in spans if (cat, s[0], s[1]) not in vus]
        if not libre:
            c["entites_doublons"] += 1
            continue
        start, end, surface = libre[0]
        cle = (cat, start, end)
        vus.add(cle)
        out.append({"identifiant_entite": f"P{page_no}_E{len(out) + 1:03d}", "categorie": cat, "type": cat,
                    "name": surface, "preuve": surface, "parametre": e.get("parametre"),
                    "valeur": e.get("valeur"), "unite": e.get("unite"), "nie": bool(e.get("nie")),
                    "hypothese": bool(e.get("hypothese")), "confiance": e.get("confiance") or "elevee",
                    "type_inference": e.get("type_inference") or "extraction_directe",
                    "page": page_no, "start": start, "end": end})
    c["entites_gardees"] += len(out)
    return out


def valider_relations(g, raw, entites, page_no, c, n0, rejets=None):
    sig = {k: (v["domaine"], v["image"]) for k, v in g["signatures_relations"].items()}
    by = {e["identifiant_entite"]: e for e in entites}
    out, vus = [], set()
    for r in raw.get("relations", []) or []:
        if not isinstance(r, dict):
            continue
        a, b, t = r.get("sujet"), r.get("objet"), str(r.get("type_relation") or "").strip()
        if a not in by or b not in by:
            c["relations_extremite_inconnue"] += 1
            if rejets is not None:
                rejets.append({"type_relation": t, "raison": "extremite_inconnue", "sujet": a, "objet": b})
            continue
        if sig.get(t) != (by[a]["categorie"], by[b]["categorie"]):
            c["relations_hors_signature"] += 1
            if rejets is not None:
                obtenu = (by[a]["categorie"], by[b]["categorie"])
                rejets.append({"type_relation": t, "raison": "hors_signature" if t in sig else "relation_inconnue",
                               "types_obtenus": list(obtenu), "signature": list(sig.get(t, ())),
                               "sens_inverse": sig.get(t) == obtenu[::-1],
                               "sujet": by[a]["name"], "objet": by[b]["name"]})
            continue
        if (a, t, b) in vus:
            continue
        vus.add((a, t, b))
        out.append({"identifiant_relation": f"R{n0 + len(out) + 1:05d}", "identifiant_entite_sujet": a,
                    "entite_sujet": by[a]["name"], "type_relation": t, "identifiant_entite_objet": b,
                    "entite_objet": by[b]["name"], "subject": by[a]["name"], "object": by[b]["name"],
                    "preuve": r.get("preuve"), "confiance": r.get("confiance") or "elevee",
                    "type_inference": "extraction_directe", "page": page_no})
    c["relations_gardees"] += len(out)
    return out


# ------------------------------------------------------------------ traitement d'un PDF
def traiter_pdf(api, g, pdf, out_dir, c):
    try:
        import pymupdf as fitz  # PyMuPDF recent
    except ImportError:
        import fitz  # PyMuPDF ancien
    version = g.get("version", "x")
    cible = out_dir / f"{pdf.stem}_trace_sepsis_v{version}.json"
    if cible.exists():
        print(f"  deja fait : {cible.name}")
        return
    img_dir = out_dir / "_images"
    img_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(pdf))
    pages, ents_g, rels_g = [], [], []
    for i, page in enumerate(doc, start=1):
        png = img_dir / f"{pdf.stem}_p{i}.png"
        if not png.exists():
            page.get_pixmap(dpi=500).save(str(png))
        import base64
        b64 = base64.b64encode(png.read_bytes()).decode()
        texte = api.ask([{"type": "text", "text": TRANSCRIPTION},
                         {"type": "image_url", "image_url": f"data:image/png;base64,{b64}"}],
                        json_mode=False, max_tokens=4000).strip()
        del b64
        png.unlink(missing_ok=True)   # image de 500 dpi tres lourde : supprimee une fois lue
        doc = pdf.stem
        if PAR_FAMILLES:
            # une consigne ciblee par famille d'entites (au lieu de la consigne generale)
            raw_e = {"entites": []}
            for fam, spec in FAMILLES.items():
                rep = parse_json(api.ask(prompt_famille(g, texte, fam, bloc_regles(doc, "entites", spec["types"])
                                                        + bloc_exemples(doc, fam, texte)),
                                         json_mode=True, max_tokens=8000))
                raw_e["entites"] += [e for e in rep.get("entites", []) or [] if isinstance(e, dict)
                                     and str(e.get("categorie") or "").strip().upper().replace("SCORE_QSOFA", "SCORE_qSOFA")
                                     in spec["types"]]
        else:
            raw_e = parse_json(api.ask(prompt_entites(g, texte, bloc_regles(doc, "entites") + bloc_exemples(doc, "entites", texte)),
                                       json_mode=True, max_tokens=12000))
        raw_t = parse_json(api.ask(prompt_traitements(g, texte, bloc_regles(doc, "entites") + bloc_exemples(doc, "traitements", texte)),
                                   json_mode=True, max_tokens=8000))
        # traitements et posologies : la consigne ciblee remplace ceux de la consigne generale
        raw_e = {"entites": [e for e in raw_e.get("entites", []) or []
                             if isinstance(e, dict)
                             and str(e.get("categorie") or "").upper() not in FAMILLE_TRAITEMENT]
                 + [e for e in raw_t.get("entites", []) or []
                    if isinstance(e, dict) and str(e.get("categorie") or "").upper() in FAMILLE_TRAITEMENT]}
        ents = valider_entites(g, raw_e, texte, i, c)
        # une meme mention typee deux fois par deux consignes : on garde le type le plus fiable
        prec = GUIDE.get(doc, {}).get("precision_types", {})
        meilleur = {}
        for e in ents:
            k = (e["start"], e["end"])
            if k not in meilleur or prec.get(e["categorie"], 0.5) > prec.get(meilleur[k]["categorie"], 0.5):
                meilleur[k] = e
        c["entites_double_type"] += len(ents) - len(meilleur)
        ents = [e for e in ents if meilleur[(e["start"], e["end"])] is e]
        # regle stricte : profils d'entites interdits pour cette moitie (jamais une mention niee)
        avant = len(ents)
        ents = [e for e in ents if not entite_interdite(doc, e["categorie"], e["name"])]
        c["entites_interdites_guide"] += avant - len(ents)
        ancre = ancre_patient(ents, texte, i)
        if ancre:
            ents.append(ancre)
            c["ancre_patient_ajoutee"] += 1
        interdites = GUIDE.get(doc, {}).get("relations_interdites", set())
        raw_r = parse_json(api.ask(prompt_relations(g, texte, ents,
                                                    bloc_regles(doc, "relations") + bloc_exemples(doc, "relations", texte),
                                                    interdites),
                                   json_mode=True, max_tokens=8000)) \
            if relations_possibles(g, ents, interdites) else {}
        rejets = []
        rels = valider_relations(g, raw_r, ents, i, c, len(rels_g), rejets)
        # regles strictes : types de relation interdits, et aucune relation vers une absence
        nies = {e["identifiant_entite"] for e in ents if e.get("nie") or NEG_MENTION.match(e["name"])}
        avant = len(rels)
        rels = [r for r in rels if r["type_relation"] not in interdites
                and r["identifiant_entite_sujet"] not in nies and r["identifiant_entite_objet"] not in nies]
        c["relations_interdites_guide"] += avant - len(rels)
        pages.append({"page": i, "texte_brut": texte, "entities": ents, "relations": rels,
                      "relations_rejetees": rejets, "statut": "ok"})
        ents_g += ents
        rels_g += rels
        print(f"  page {i} : {len(ents)} entites, {len(rels)} relations")
    data = {"source_file": pdf.name, "type_extraction": VERSION,
            "schema": {"guideline": nom_guideline(g), "modele": MODEL, "temperature": 0},
            "pages": pages, "global_entities": ents_g, "global_relations": rels_g}
    cible.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "textes_bruts").mkdir(exist_ok=True)
    (out_dir / "textes_bruts" / f"{pdf.stem}_brut.txt").write_text(
        "\n\n".join(f"=== PAGE {p['page']} ===\n{p['texte_brut']}" for p in pages), encoding="utf-8")
    c["documents"] += 1


def main():
    global GUIDELINE, MODEL
    ap = argparse.ArgumentParser(description="Extraction Mistral selon le guideline TRACE-Sepsis")
    ap.add_argument("--guideline", default=str(GUIDELINE))
    ap.add_argument("--gold-exemples", default="", help="gold converti (dossier gold_v2_0) : active les exemples annotes")
    ap.add_argument("--exemples", type=int, default=3, help="pages annotees semblables montrees par consigne (defaut 3)")
    ap.add_argument("--guide", default="", help="regles strictes apprises (apprendre_guide.py), par moitie de corpus")
    ap.add_argument("--modele", default=MODEL,
                    help="modele Mistral (defaut mistral-small-2603 ; ex. mistral-medium-latest, mistral-large-latest)")
    ap.add_argument("--par-familles", action="store_true",
                    help="une consigne par famille d'entites au lieu de la consigne generale (moins bon a l'essai)")
    ap.add_argument("--pdfs", default=str(DEFAULT_PDFS))
    ap.add_argument("--sortie", default=str(DEFAULT_OUT))
    ap.add_argument("--essai", action="store_true", help="un seul dossier, pour verifier")
    ap.add_argument("--docs", type=int, default=0)
    ap.add_argument("--pause", type=float, default=1.5)
    args = ap.parse_args()
    GUIDELINE = Path(args.guideline)
    from collections import Counter
    pdfs = sorted(p for p in Path(args.pdfs).glob("*") if p.suffix.lower() == ".pdf")
    if not pdfs:
        sys.exit(f"Aucun PDF dans {args.pdfs} (option --pdfs pour indiquer le dossier).")
    if args.essai:
        pdfs = pdfs[:1]
    elif args.docs:
        pdfs = pdfs[:args.docs]
    if not os.getenv("MISTRAL_API_KEY", "").strip():
        os.environ["MISTRAL_API_KEY"] = getpass.getpass("Cle API Mistral (rien ne s'affiche) : ").strip()
    out = Path(args.sortie)
    out.mkdir(parents=True, exist_ok=True)
    g, c = guideline(), Counter()
    global PAR_FAMILLES
    PAR_FAMILLES = args.par_familles
    MODEL = args.modele
    if args.guide:
        charger_guide(args.guide)
        print(f"Regles strictes apprises : {args.guide} ({len(GUIDE)} dossiers couverts)")
    if args.gold_exemples:
        preparer_exemples(args.gold_exemples, args.exemples)
        print(f"Exemples annotes : {args.exemples} page(s) par consigne, pris dans l'autre moitie des dossiers"
              f" ({len(POOL)} dossiers couverts)")
    api = Mistral(out / "_cache", args.pause)
    print(f"Guideline : {GUIDELINE.name} | {len(g['signatures_relations'])} relations | {len(pdfs)} dossier(s)")
    for k, pdf in enumerate(pdfs, start=1):
        print(f"[{k}/{len(pdfs)}] {pdf.name}")
        traiter_pdf(api, g, pdf, out, c)
    print(f"\nTermine : {dict(c)} | appels Mistral payes : {api.calls}")
    print(f"Sorties : {out}")


if __name__ == "__main__":
    main()
