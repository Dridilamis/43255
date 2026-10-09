# -*- coding: utf-8 -*-
"""
TRACE - ETAGE 0b - SECONDE PASSE MISTRAL (rappel)

Pourquoi : la premiere extraction oublie environ 3400 entites et 2200 relations du gold,
surtout dans le texte libre (Evolution, Histoire de la maladie). Un post-traitement ne peut
pas les inventer ; il faut demander a nouveau au LLM, en lui montrant ce qui existe deja.

Ce que fait ce script, page par page :
  1. ENTITES MANQUANTES : on donne a Mistral le texte de la page et la liste des entites
     deja extraites ; il ne renvoie que celles qui manquent.
  2. RELATIONS MANQUANTES : on lui donne toutes les entites (anciennes + nouvelles) et les
     relations deja presentes ; il ne renvoie que les relations qui manquent.
  3. VOTE : chaque demande est faite N fois (--echantillons, defaut 3) ; un element n'est
     garde que s'il revient dans au moins --vote reponses (defaut 2).
  4. PREUVE OBLIGATOIRE : une entite n'est gardee que si sa preuve figure MOT POUR MOT dans
     le texte de la page ; une relation, que si sa signature respecte l'ontologie v1.6 et que
     ses deux entites existent. Rien n'est ajoute sans preuve.

Les fichiers d'entree ne sont jamais modifies. Chaque reponse de Mistral est mise en cache
(dossier cache/) : si le script s'arrete, relancez-le, il reprend ou il en etait sans
repayer les appels deja faits.

Lancer (PowerShell, depuis Reduction_hallucinations) :
    $env:MISTRAL_API_KEY="votre_cle"
    python extraction_mistral\\seconde_passe_mistral.py --docs 2        # essai sur 2 documents
    python extraction_mistral\\seconde_passe_mistral.py                 # les 43 documents

Puis poussez le dossier de sortie :
    git add extraction_mistral/seconde_passe
    git commit -m "Seconde passe Mistral"
    git push origin claude/epic-darwin-ygtsx2
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import requests

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
DEFAULT_IN = PROJECT / "SortieJson_Postprocessing_PROPRE"
DEFAULT_OUT = HERE / "seconde_passe"
SIGNATURES = json.loads((PROJECT / "TRACE_v2" / "trace_lib" / "ontologie_signatures_v1.6.json")
                        .read_text(encoding="utf-8"))

URL = "https://api.mistral.ai/v1/chat/completions"
MODEL = "mistral-small-2603"

CATEGORIES = ["DONNEE_PATIENT", "LABEL_NOSOLOGIQUE", "SIGNE_VITAL", "BIOMARQUEUR", "SCORE_SOFA",
              "SCORE_qSOFA", "SCORE_NEUROLOGIQUE", "STADE_IRA", "FOYER_INFECTIEUX", "MICRO_ORGANISME",
              "DEFAILLANCE_ORGANE", "TRAITEMENT", "POSOLOGIE", "CONTEXTE_ACQUISITION",
              "COMORBIDITE_ANTECEDENT", "EVENEMENT_TEMPOREL", "EVOLUTION_PRONOSTIC", "SERVICE_MEDICAL",
              "IMAGERIE_PROCEDURE", "SYMPTOME"]


# ------------------------------------------------------------------ texte
def norm(text):
    text = unicodedata.normalize("NFD", str(text or "").lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def find_verbatim(span, page_text):
    """Retrouve la preuve dans le texte de la page (espaces et casse ignores) et renvoie la
    forme exacte du texte, ou None si elle n'y figure pas."""
    span = str(span or "").strip()
    if len(span) < 2:
        return None
    pattern = r"\s+".join(re.escape(tok) for tok in span.split())
    m = re.search(pattern, page_text, re.IGNORECASE)
    return m.group(0) if m else None


def etype(e):
    return str(e.get("type") or e.get("categorie") or "").upper().replace("SCORE_QSOFA", "SCORE_qSOFA")


def ename(e):
    for k in ("name", "preuve", "parametre"):
        if e.get(k):
            return str(e[k])
    return ""


# ------------------------------------------------------------------ API Mistral
class Mistral:
    def __init__(self, cache_dir, temperature, pause=1.5):
        self.key = os.getenv("MISTRAL_API_KEY", "").strip()
        if not self.key:
            sys.exit("MISTRAL_API_KEY absente. PowerShell : $env:MISTRAL_API_KEY=\"votre_cle\"")
        self.session = requests.Session()
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.temperature = temperature
        self.calls = 0
        self.pause = pause              # secondes minimum entre deux appels (limite de debit)
        self.last = 0.0

    def ask(self, prompt, sample):
        key = hashlib.sha256(f"{MODEL}|{self.temperature}|{sample}|{prompt}".encode("utf-8")).hexdigest()
        cached = self.cache / f"{key}.json"
        if cached.exists():
            return json.loads(cached.read_text(encoding="utf-8"))
        payload = {"model": MODEL, "temperature": self.temperature, "max_tokens": 6000,
                   "random_seed": 1000 + sample, "response_format": {"type": "json_object"},
                   "messages": [{"role": "user", "content": prompt}]}
        for attempt in range(15):
            wait_more = self.pause - (time.monotonic() - self.last)
            if wait_more > 0:
                time.sleep(wait_more)
            self.last = time.monotonic()
            try:
                r = self.session.post(URL, json=payload, timeout=(30, 240),
                                      headers={"Authorization": f"Bearer {self.key}",
                                               "Content-Type": "application/json"})
            except requests.RequestException as exc:
                wait = min(60, 2 ** attempt)
                print(f"    reseau : {exc} - nouvel essai dans {wait} s")
                time.sleep(wait)
                continue
            if r.status_code in (429, 500, 502, 503, 504):
                try:
                    retry_after = float(r.headers.get("Retry-After", 0))
                except ValueError:
                    retry_after = 0
                wait = max(retry_after, min(60, 5 * 2 ** attempt))
                if r.status_code == 429 and attempt == 0:
                    print(f"    Mistral 429 (limite de debit) : {r.text[:200]}")
                    self.pause = min(10.0, self.pause * 1.5)    # ralentit pour la suite
                    print(f"    pause entre appels portee a {self.pause:.1f} s")
                print(f"    Mistral {r.status_code} - nouvel essai dans {wait:.0f} s")
                time.sleep(wait)
                continue
            if r.status_code == 401:
                raise RuntimeError("Mistral 401 : cle API refusee. Verifiez la cle (console.mistral.ai).")
            if r.status_code != 200:
                raise RuntimeError(f"Mistral {r.status_code} : {r.text[:300]}")
            self.calls += 1
            content = r.json()["choices"][0]["message"]["content"]
            data = parse_json(content)
            cached.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return data
        raise RuntimeError("Mistral refuse encore apres 15 essais (limite de debit ou quota). "
                           "Attendez quelques minutes puis relancez avec une pause plus longue, "
                           "ex. --pause 5 : les reponses deja obtenues sont en cache.")


def parse_json(text):
    text = str(text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return {}


# ------------------------------------------------------------------ prompts
def prompt_entities(page_text, existing):
    deja = "\n".join(f"- [{etype(e)}] {ename(e)}" for e in existing) or "(aucune)"
    return f"""Tu es un expert en extraction d'information clinique orientee sepsis (guideline TRACE-Sepsis v1.6).

Une premiere extraction a deja ete faite sur la page ci-dessous. Elle a OUBLIE des entites.
MISSION : renvoyer UNIQUEMENT les entites cliniques ABSENTES de la liste "DEJA EXTRAITES".

REGLES :
- Chaque entite doit avoir une "preuve" copiee MOT POUR MOT depuis le texte (meme orthographe).
- La preuve est le plus court groupe de mots qui designe l'entite (pas une phrase entiere).
  Ex. "Amiklin pendant 5 jours" -> TRAITEMENT "Amiklin" et POSOLOGIE "pendant 5 jours".
- Une entite par occurrence pertinente ; ne recopie pas une entite deja extraite.
- Cherche surtout dans le texte libre (evolution, histoire de la maladie, conclusion) :
  traitements et gestes (VNI, intubation, transfusion, dialyse, chirurgie...), posologies,
  symptomes et signes cliniques, biomarqueurs avec valeur, defaillances d'organe, diagnostics,
  foyers infectieux, germes, examens et imageries, evolution, dates.
- Une negation explicite ("pas de fievre") : garde l'expression negative et mets "nie": true.
- N'invente rien, ne deduis rien, n'utilise aucune connaissance externe.
- Categories autorisees : {", ".join(CATEGORIES)}.

DEJA EXTRAITES :
{deja}

TEXTE DE LA PAGE :
\"\"\"
{page_text}
\"\"\"

Reponds UNIQUEMENT par un objet JSON :
{{"entites": [{{"categorie": "TRAITEMENT", "preuve": "Amiklin", "nie": false, "confiance": "elevee"}}]}}
Si rien ne manque : {{"entites": []}}"""


def prompt_relations(page_text, entities, existing_rel):
    lst = "\n".join(f"- {e['identifiant_entite']} [{etype(e)}] {ename(e)}" for e in entities)
    rel = "\n".join(f"- {r['identifiant_entite_sujet']} {r['type_relation']} {r['identifiant_entite_objet']}"
                    for r in existing_rel) or "(aucune)"
    sig = "\n".join(f"- {v['domaine']} -> {k} -> {v['image']}" for k, v in SIGNATURES.items())
    return f"""Tu es un expert en extraction de relations cliniques orientees sepsis (TRACE-Sepsis v1.6).

Des relations ont deja ete extraites sur cette page, mais certaines ont ete OUBLIEES.
MISSION : renvoyer UNIQUEMENT les relations explicitement soutenues par le texte et ABSENTES
de "RELATIONS DEJA PRESENTES".

REGLES :
- Utilise uniquement les identifiants de la liste ENTITES ; respecte le sens sujet -> objet.
- Seules les 32 signatures ci-dessous sont autorisees.
- "preuve" = court extrait copie MOT POUR MOT du texte qui justifie la relation.
- traitement_administre_a : seulement si le traitement est reellement donne/prescrit au patient.
- traitement_a_pour_posologie : seulement si la posologie se rapporte a ce traitement.
- Aucune relation positive vers une entite niee ; aucune relation seulement plausible.

SIGNATURES AUTORISEES :
{sig}

ENTITES :
{lst}

RELATIONS DEJA PRESENTES :
{rel}

TEXTE DE LA PAGE :
\"\"\"
{page_text}
\"\"\"

Reponds UNIQUEMENT par un objet JSON :
{{"relations": [{{"identifiant_entite_sujet": "P1_E003", "type_relation": "traitement_administre_a", "identifiant_entite_objet": "P1_E001", "preuve": "..."}}]}}
Si rien ne manque : {{"relations": []}}"""


# ------------------------------------------------------------------ une page
def overlaps(name, typ, entities):
    n = norm(name)
    for e in entities:
        if etype(e) != typ:
            continue
        en = norm(ename(e))
        if en and (en == n or (len(en) >= 4 and en in n) or (len(n) >= 4 and n in en)):
            return True
    return False


def complete_page(api, page, doc_relations, n_samples, min_votes, counters):
    text = page.get("texte_brut") or ""
    if len(text.strip()) < 30:
        return [], []
    key = "entities" if isinstance(page.get("entities"), list) else "entites"
    existing = [e for e in page.get(key, []) or [] if isinstance(e, dict)]
    pnum = page.get("page")

    # 1. entites manquantes, avec vote
    votes, sample_of = Counter(), {}
    for s in range(n_samples):
        seen = set()
        for item in (api.ask(prompt_entities(text, existing), s).get("entites") or []):
            if not isinstance(item, dict):
                continue
            typ = str(item.get("categorie") or "").strip().upper().replace("SCORE_QSOFA", "SCORE_qSOFA")
            surface = find_verbatim(item.get("preuve"), text)
            if typ not in CATEGORIES or not surface:
                counters["entites_rejetees_sans_preuve_ou_type"] += 1
                continue
            k = (norm(surface), typ)
            if k in seen:
                continue
            seen.add(k)
            votes[k] += 1
            sample_of.setdefault(k, (surface, typ, bool(item.get("nie"))))
    new_entities = []
    for k, v in votes.items():
        if v < min_votes:
            counters["entites_rejetees_vote"] += 1
            continue
        surface, typ, nie = sample_of[k]
        if overlaps(surface, typ, existing + new_entities):
            counters["entites_rejetees_deja_presentes"] += 1
            continue
        new_entities.append({
            "identifiant_entite": f"P{pnum}_S{len(new_entities) + 1:03d}",
            "categorie": typ, "type": typ, "name": surface, "preuve": surface, "page": pnum,
            "nie": nie, "confiance": "elevee", "type_inference": "seconde_passe_mistral",
            "_seconde_passe_votes": f"{v}/{n_samples}"})

    # 2. relations manquantes, avec vote
    all_entities = existing + new_entities
    by_id = {e.get("identifiant_entite"): e for e in all_entities if e.get("identifiant_entite")}
    page_rel = [r for r in doc_relations
                if r.get("identifiant_entite_sujet") in by_id and r.get("identifiant_entite_objet") in by_id]
    have = {(r["identifiant_entite_sujet"], r["type_relation"], r["identifiant_entite_objet"]) for r in page_rel}
    rvotes, rproof = Counter(), {}
    for s in range(n_samples):
        seen = set()
        for item in (api.ask(prompt_relations(text, all_entities, page_rel), s).get("relations") or []):
            if not isinstance(item, dict):
                continue
            sid, oid = item.get("identifiant_entite_sujet"), item.get("identifiant_entite_objet")
            rt = str(item.get("type_relation") or "").strip()
            spec = SIGNATURES.get(rt)
            if sid not in by_id or oid not in by_id or not spec \
                    or etype(by_id[sid]) != spec["domaine"].upper().replace("SCORE_QSOFA", "SCORE_qSOFA") \
                    or etype(by_id[oid]) != spec["image"].upper().replace("SCORE_QSOFA", "SCORE_qSOFA") \
                    or by_id[oid].get("nie") is True or by_id[sid].get("nie") is True:
                counters["relations_rejetees_signature"] += 1
                continue
            k = (sid, rt, oid)
            if k in seen or k in have:
                continue
            seen.add(k)
            rvotes[k] += 1
            proof = find_verbatim(item.get("preuve"), text)
            if proof:
                rproof.setdefault(k, proof)
    new_relations = []
    for k, v in rvotes.items():
        if v < min_votes:
            counters["relations_rejetees_vote"] += 1
            continue
        if k not in rproof:
            counters["relations_rejetees_sans_preuve"] += 1
            continue
        sid, rt, oid = k
        new_relations.append({
            "identifiant_entite_sujet": sid, "entite_sujet": ename(by_id[sid]), "type_relation": rt,
            "identifiant_entite_objet": oid, "entite_objet": ename(by_id[oid]), "preuve": rproof[k],
            "type_inference": "seconde_passe_mistral", "confiance": "elevee", "page": pnum,
            "subject": ename(by_id[sid]), "object": ename(by_id[oid]),
            "_seconde_passe_votes": f"{v}/{n_samples}"})
    page.setdefault(key, []).extend(new_entities)
    return new_entities, new_relations


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description="Seconde passe Mistral (rappel), avec preuve et vote.")
    ap.add_argument("--entree", default=str(DEFAULT_IN))
    ap.add_argument("--sortie", default=str(DEFAULT_OUT))
    ap.add_argument("--docs", type=int, default=0, help="ne traiter que les N premiers documents (essai)")
    ap.add_argument("--echantillons", type=int, default=3)
    ap.add_argument("--vote", type=int, default=2)
    ap.add_argument("--temperature", type=float, default=0.3)
    ap.add_argument("--pause", type=float, default=1.5,
                    help="secondes minimum entre deux appels Mistral (limite de debit ; defaut 1.5)")
    args = ap.parse_args()

    src, out = Path(args.entree), Path(args.sortie)
    files = sorted(p for p in src.glob("*.json") if p.name.startswith("img"))
    if args.docs:
        files = files[:args.docs]
    if not files:
        sys.exit(f"Aucun JSON dans {src}")
    out.mkdir(parents=True, exist_ok=True)
    api = Mistral(HERE / "cache_seconde_passe", args.temperature, args.pause)
    total = Counter()
    print(f"Entree : {src} ({len(files)} documents) | sortie : {out}")
    print(f"Modele {MODEL} | {args.echantillons} echantillons, vote >= {args.vote}, temperature {args.temperature}")
    for i, path in enumerate(files, 1):
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        counters = Counter()
        rels = data.get("global_relations", []) or []
        added_e = added_r = 0
        for page in data.get("pages", []) or []:
            if not isinstance(page, dict):
                continue
            ents, new_rels = complete_page(api, page, rels, args.echantillons, args.vote, counters)
            data.setdefault("global_entities", []).extend(json.loads(json.dumps(ents)))
            for j, r in enumerate(new_rels, 1):
                r["identifiant_relation"] = f"R_S2_P{page.get('page')}_{added_r + j:03d}"
            rels.extend(new_rels)
            added_e += len(ents)
            added_r += len(new_rels)
        data["global_relations"] = rels
        data["seconde_passe_trace"] = {"modele": MODEL, "echantillons": args.echantillons, "vote": args.vote,
                                       "temperature": args.temperature, "entites_ajoutees": added_e,
                                       "relations_ajoutees": added_r, "rejets": dict(counters)}
        (out / path.name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        total.update(counters)
        total["entites_ajoutees"] += added_e
        total["relations_ajoutees"] += added_r
        print(f"[{i}/{len(files)}] {path.name[:20]} : +{added_e} entites, +{added_r} relations "
              f"(appels Mistral : {api.calls})")
    print("\nTotal :", dict(total))
    print(f"Sortie : {out}")


if __name__ == "__main__":
    main()
