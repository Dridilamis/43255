# -*- coding: utf-8 -*-
"""
Vote appris des agents (regression logistique, numpy seul).

Les signaux des agents (Etage 7) deviennent des variables binaires ; le modele apprend
leur poids. Il est ENTRAINE par l'Etage 8 (seul etage qui lit le gold) et APPLIQUE par
l'Etage 7 en mode precision. Sa qualite est mesuree par validation croisee sur des
documents qui n'ont pas servi a l'entrainement.
"""
import json
import math

import numpy as np

from . import config as C


def features(s, rel_type):
    a = s["ancrage"]
    ctx = s["contexte"]
    f = {
        "biais": 1,
        f"preuve={a['preuve']}": 1,
        f"distance={a['distance']}": 1,
        f"section={a['section']}": 1,
        f"section*relation={a['section']}*{rel_type}": 1,
        f"relation={rel_type}": 1,
        f"ontologie={s['ontologie']}": 1,
        f"provenance={s['provenance']}": 1,
        f"temporalite={ctx.get('temporalite', 'INCONNUE')}": 1,
    }
    for k in ("doublon",):
        if s[k]:
            f[k] = 1
    for k in ("negation", "hypothese"):
        if ctx.get(k):
            f[k] = 1
    return f


def fit(rows, labels, l2=1.0, iterations=3000, lr=0.5):
    vocab = sorted({k for r in rows for k in r})
    idx = {k: i for i, k in enumerate(vocab)}
    X = np.zeros((len(rows), len(vocab)))
    for i, r in enumerate(rows):
        for k in r:
            X[i, idx[k]] = 1
    y = np.asarray(labels, float)
    w = np.zeros(len(vocab))
    for _ in range(iterations):
        p = 1 / (1 + np.exp(-X @ w))
        w -= lr * (X.T @ (p - y) + l2 * w) / len(y)
    return {k: float(w[i]) for k, i in idx.items()}


def score(weights, f):
    z = sum(weights.get(k, 0.0) for k in f)
    return 1 / (1 + math.exp(-z))


def save(model):
    C.MODEL_FILE.parent.mkdir(parents=True, exist_ok=True)
    C.MODEL_FILE.write_text(json.dumps(model, ensure_ascii=False, indent=1), encoding="utf-8")


def load():
    if C.MODEL_FILE.exists():
        return json.loads(C.MODEL_FILE.read_text(encoding="utf-8"))
    return None
