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


def find_span(surface, page_text):
    """Position de la surface dans le texte de la page (casse et espaces ignores), ou None."""
    surface = str(surface or "").strip()
    if len(surface) < 2:
        return None
    pattern = r"\s+".join(re.escape(t) for t in surface.split())
    m = re.search(pattern, page_text, re.IGNORECASE)
    return (m.start(), m.end(), m.group(0)) if m else None


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


def prompt_entites(g, page_text):
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
  traitement_administre_a, presente_symptome...).

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

PAGE :
\"\"\"{page_text}\"\"\""""


def relations_possibles(g, entites):
    """Relations du guideline realisables sur la page : un sujet du type domaine ET un objet du
    type image existent parmi les entites validees. Avec, pour chacune, les identifiants permis."""
    par_type = {}
    for e in entites:
        par_type.setdefault(e["categorie"], []).append(e["identifiant_entite"])
    out = []
    for groupe, rels in g["relations"].items():
        for k, v in rels.items():
            sujets, objets = par_type.get(v["domaine"], []), par_type.get(v["image"], [])
            if sujets and objets:
                out.append((k, v, sujets, objets))
    return out


def prompt_relations(g, page_text, entites):
    ordre = sorted(entites, key=lambda e: (e["categorie"], e["identifiant_entite"]))
    liste = "\n".join(f"- {e['identifiant_entite']} [{e['categorie']}] {e['name']}" for e in ordre)
    sigs = []
    for k, v, sujets, objets in relations_possibles(g, entites):
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
        span = find_span(e.get("texte"), page_text)
        if not span:
            c["entites_non_ancrees"] += 1
            continue
        start, end, surface = span
        cle = (cat, start, end)
        if cle in vus:
            c["entites_doublons"] += 1
            continue
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
        raw_e = parse_json(api.ask(prompt_entites(g, texte), json_mode=True, max_tokens=12000))
        ents = valider_entites(g, raw_e, texte, i, c)
        raw_r = parse_json(api.ask(prompt_relations(g, texte, ents), json_mode=True, max_tokens=8000)) \
            if relations_possibles(g, ents) else {}
        rejets = []
        rels = valider_relations(g, raw_r, ents, i, c, len(rels_g), rejets)
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
    global GUIDELINE
    ap = argparse.ArgumentParser(description="Extraction Mistral selon le guideline TRACE-Sepsis")
    ap.add_argument("--guideline", default=str(GUIDELINE))
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
    api = Mistral(out / "_cache", args.pause)
    print(f"Guideline : {GUIDELINE.name} | {len(g['signatures_relations'])} relations | {len(pdfs)} dossier(s)")
    for k, pdf in enumerate(pdfs, start=1):
        print(f"[{k}/{len(pdfs)}] {pdf.name}")
        traiter_pdf(api, g, pdf, out, c)
    print(f"\nTermine : {dict(c)} | appels Mistral payes : {api.calls}")
    print(f"Sorties : {out}")


if __name__ == "__main__":
    main()
