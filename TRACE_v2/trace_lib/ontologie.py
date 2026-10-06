# -*- coding: utf-8 -*-
"""
Service ONTOLOGIE (unique) : signatures TRACE-Sepsis v1.6 (relation -> domaine, image).

Source : Guideline_TRACE_Sepsis_v1.6.json si le fichier est present (meme emplacement que
pour SGCE), sinon la copie figee `ontologie_signatures_v1.6.json`, extraite du rapport
Pattern B2 de SGCE (32 signatures, identiques au guideline).
"""
import json

from . import config as C

_CACHE = {}


def load_signatures():
    if "sig" in _CACHE:
        return _CACHE["sig"]
    sig, source = None, None
    for path in C.GUIDELINE_CANDIDATES:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            root = data.get("ontologie_sepsis_graph", data)
            locked = root.get("signatures_relations_verrouillees_v1_5", {})
            sig = {k: {"domaine": v["domaine"], "image": v["image"]} for k, v in locked.items()
                   if isinstance(v, dict) and v.get("domaine") and v.get("image")}
            source = str(path)
            break
    if not sig:
        sig = json.loads(C.SIGNATURES_SNAPSHOT.read_text(encoding="utf-8"))
        source = str(C.SIGNATURES_SNAPSHOT)
    _CACHE["sig"], _CACHE["source"] = sig, source
    return sig


def source():
    load_signatures()
    return _CACHE["source"]


def check(rel_type, subject_type, object_type):
    """CONFORME | RELATION_INCONNUE | DOMAINE_INVALIDE | IMAGE_INVALIDE | DOMAINE_ET_IMAGE_INVALIDES"""
    spec = load_signatures().get(rel_type)
    if spec is None:
        return "RELATION_INCONNUE"
    bad_d = bool(subject_type) and subject_type != spec["domaine"]
    bad_i = bool(object_type) and object_type != spec["image"]
    if bad_d and bad_i:
        return "DOMAINE_ET_IMAGE_INVALIDES"
    if bad_d:
        return "DOMAINE_INVALIDE"
    if bad_i:
        return "IMAGE_INVALIDE"
    return "CONFORME"
