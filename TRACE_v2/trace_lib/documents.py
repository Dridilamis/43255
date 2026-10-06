# -*- coding: utf-8 -*-
"""
Service GRAPHE (unique) : lecture/ecriture des JSON TRACE, acces aux entites et aux
extremites des relations, noeud patient, retrait d'une relation (global + pages), trace
par etage dans chaque relation (`trace_v2`).
"""
import json
import re
import shutil
from pathlib import Path

from .texte import norm

PATIENT_RE = re.compile(r"^(le |la |l |cette |ce )?patiente?s?$")
PATIENT_TYPE = "DONNEE_PATIENT"


def is_clinical(data):
    return isinstance(data, dict) and isinstance(data.get("global_relations"), list) \
        and isinstance(data.get("global_entities"), list)


def iter_documents(in_dir):
    for path in sorted(Path(in_dir).glob("*.json")):
        yield path, json.loads(path.read_text(encoding="utf-8-sig"))


def prepare_output(out_dir):
    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)              # sortie derivee, regenerable
    out_dir.mkdir(parents=True)
    return out_dir


def write_document(out_dir, path, data):
    (Path(out_dir) / Path(path).name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


class Graph:
    """Vue sur un document : entites indexees, extremites des relations."""

    def __init__(self, data):
        self.data = data
        self.entities = {e.get("identifiant_entite"): e for e in data.get("global_entities", []) or []
                         if isinstance(e, dict) and e.get("identifiant_entite")}

    @property
    def relations(self):
        return self.data["global_relations"]

    @staticmethod
    def entity_type(e):
        return str((e or {}).get("type") or (e or {}).get("categorie") or "").upper()

    @staticmethod
    def entity_name(e):
        e = e or {}
        return str(e.get("name") or e.get("preuve") or e.get("parametre") or "")

    def is_patient(self, e, name=None):
        name = self.entity_name(e) if name is None else name
        return PATIENT_RE.match(norm(name)) is not None or self.entity_type(e) == PATIENT_TYPE

    def endpoint(self, rel, side):
        """(entite, nom) de l'extremite `subject` ou `object`, avec repli sur les champs
        de la relation si l'entite est absente."""
        key = "identifiant_entite_sujet" if side == "subject" else "identifiant_entite_objet"
        e = self.entities.get(rel.get(key))
        if e:
            return e, self.entity_name(e)
        fields = ("entite_sujet", "subject") if side == "subject" else ("entite_objet", "object")
        return None, str(next((rel[f] for f in fields if rel.get(f)), ""))

    def clinical_endpoint(self, rel):
        """L'extremite qui porte l'information clinique, et l'autre.
        Retourne (nom_clinique, nom_autre, autre_est_patient)."""
        se, sn = self.endpoint(rel, "subject")
        oe, on = self.endpoint(rel, "object")
        if self.is_patient(se, sn):
            return on, sn, True
        return sn, on, self.is_patient(oe, on)

    # -- entites par page (ce sont elles que le matcher d'entites evalue)
    @staticmethod
    def mention(e):
        """Nom d'une entite tel que l'evaluation le lit (name, mention, text, preuve, valeur)."""
        for k in ("name", "mention", "text", "preuve", "valeur"):
            v = (e or {}).get(k)
            if v is not None and str(v).strip():
                return str(v).strip()
        return ""

    def page_entities(self):
        """Liste de (page, entite) pour toutes les entites de pages[]."""
        out = []
        for page in self.data.get("pages", []) or []:
            if not isinstance(page, dict):
                continue
            key = "entities" if isinstance(page.get("entities"), list) else "entites"
            for e in page.get(key, []) or []:
                if isinstance(e, dict):
                    out.append((page, e))
        return out

    def remove_entities(self, page_entity_objs):
        """Retire des entites de pages[] ; retire aussi l'entite globale de meme identifiant
        quand plus aucune page ne la cite, et les relations qui pointent vers elle (un lien
        vers une entite retiree n'a plus de sens). Retourne (entites, globales, relations)."""
        drop = {id(e) for e in page_entity_objs}
        if not drop:
            return 0, 0, 0
        removed = 0
        for page in self.data.get("pages", []) or []:
            if not isinstance(page, dict):
                continue
            key = "entities" if isinstance(page.get("entities"), list) else "entites"
            if isinstance(page.get(key), list):
                before = len(page[key])
                page[key] = [e for e in page[key] if id(e) not in drop]
                removed += before - len(page[key])
        still = {e.get("identifiant_entite") for _, e in self.page_entities()}
        gone = {e.get("identifiant_entite") for e in page_entity_objs} - still - {None}
        before_g = len(self.data["global_entities"])
        self.data["global_entities"] = [e for e in self.data["global_entities"]
                                        if not (isinstance(e, dict) and e.get("identifiant_entite") in gone)]
        n_rel = self.remove_relations([r.get("identifiant_relation") for r in self.relations
                                       if r.get("identifiant_entite_sujet") in gone
                                       or r.get("identifiant_entite_objet") in gone])
        self.entities = {k: v for k, v in self.entities.items() if k not in gone}
        return removed, before_g - len(self.data["global_entities"]), n_rel

    def remove_relations(self, ids):
        """Retire des relations par identifiant, dans global_relations ET dans pages[]."""
        ids = {i for i in ids if i}
        if not ids:
            return 0
        before = len(self.relations)
        self.data["global_relations"] = [r for r in self.relations
                                         if not (isinstance(r, dict) and r.get("identifiant_relation") in ids)]
        for page in self.data.get("pages", []) or []:
            if isinstance(page, dict) and isinstance(page.get("relations"), list):
                page["relations"] = [r for r in page["relations"]
                                     if not (isinstance(r, dict) and r.get("identifiant_relation") in ids)]
        return before - len(self.relations)


def trace(obj, stage, payload):
    """Ecrit le resultat d'un etage dans obj['trace_v2'][stage]."""
    obj.setdefault("trace_v2", {})[stage] = payload
