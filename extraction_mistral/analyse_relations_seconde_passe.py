# -*- coding: utf-8 -*-
"""
TRACE - ETAGE 0b - ANALYSE DES RELATIONS AJOUTEES PAR LA SECONDE PASSE

Repond a la question : faut-il garder une partie des relations ajoutees par la seconde passe ?

  1. F1 des relations sans / avec les relations ajoutees, sur les documents pairs et impairs ;
  2. part de justes des relations ajoutees par groupe (vote, confiance, preuve, distance,
     ancrage de l'Etage 2, type de relation), comparee au seuil F1/2 ;
  3. validation croisee : groupes au-dessus du seuil choisis sur une moitie, effet sur l'autre.

Lit le gold (comme l'Etage 8) : c'est une ANALYSE, elle ne modifie aucun fichier.

Usage (depuis la racine du depot) :
    python -I extraction_mistral/analyse_relations_seconde_passe.py <dossier_sortie_hors_depot>
Le fichier resultats.json contient des extraits du texte des comptes rendus : ne pas le committer.
"""
import sys, json, io, contextlib, importlib.util, copy, collections
from pathlib import Path
R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R/'TRACE_v2'))
from trace_lib.documents import Graph
from trace_lib.texte import load_source
import etage2_ancrage
spec = importlib.util.spec_from_file_location('mr', R/'Evaluation/TRACE_Ablation_F1/Matching_relations_ABLATION.py')
m = importlib.util.module_from_spec(spec)
gold_dir = R/'SGCE/gold_canonical_par_documentF'
_args = sys.argv[:]
sys.argv = ['x', str(gold_dir), str(R/'extraction_mistral/seconde_passe'), '/tmp/xx']
with contextlib.redirect_stdout(io.StringIO()):
    spec.loader.exec_module(m)
sys.argv = _args
golds = {m.normalize_document_key(p.name): p for p in gold_dir.glob('*.json')}
ADD = 'seconde_passe_mistral'
OUT = Path(_args[1]) if len(_args) > 1 else Path('.')
OUT.mkdir(parents=True, exist_ok=True)

def counts(key, data):
    gold = m.extract_gold_relations(m.load_json(golds[key]))
    preds = m.extract_pred_relations(data)
    rows = m.evaluate_document(key, gold, preds)
    st = collections.Counter()
    status = {}
    for r in rows:
        s = str(r['status'])
        st['tp'] += s.startswith('TP'); st['fp'] += s in ('FP','WRONG_TYPE'); st['fn'] += s in ('FN','WRONG_TYPE')
        if s != 'FN':
            status.setdefault((r['pred_subject'], r['pred_relation'], r['pred_object']), []).append(s)
    lab = {}
    for p in preds:
        l = status.get((p['subject'], p['relation'], p['object']))
        if l: lab[p['index']] = l.pop(0).startswith('TP')
    return st, lab

def strip(data, keep_ids):
    d = copy.deepcopy(data)
    d['global_relations'] = [r for r in d['global_relations'] if r.get('type_inference') != ADD or r.get('identifiant_relation') in keep_ids]
    for p in d.get('pages', []) or []:
        if isinstance(p, dict) and isinstance(p.get('relations'), list):
            p['relations'] = [r for r in p['relations'] if r.get('type_inference') != ADD or r.get('identifiant_relation') in keep_ids]
    return d

docs = {}
for f in sorted((R/'extraction_mistral/seconde_passe').glob('*.json')):
    key = m.normalize_document_key(f.name)
    if key in golds:
        docs[key] = (f, json.load(open(f, encoding='utf-8-sig')))
keys = sorted(docs)
halves = {'pairs': set(keys[0::2]), 'impairs': set(keys[1::2])}

samples = []
base, full = {}, {}
for k in keys:
    f, data = docs[k]
    base[k], _ = counts(k, strip(data, set()))
    full[k], lab = counts(k, data)
    g, doc = Graph(data), load_source(data, f)
    for i, r in enumerate(data['global_relations']):
        if r.get('type_inference') == ADD and i in lab:
            a = etage2_ancrage.assess(g, doc, r)
            samples.append(dict(doc=k, id=r.get('identifiant_relation'), ok=lab[i], type=r.get('type_relation'),
                                votes=r.get('_seconde_passe_votes'), conf=r.get('confiance'), preuve=a['preuve'],
                                distance=a['distance'], ancre=not a['motifs_retrait'],
                                txt=f"{r.get('entite_sujet')} -{r.get('type_relation')}-> {r.get('entite_objet')} | {str(r.get('preuve'))[:110]}"))

def prf(c):
    p = c['tp']/(c['tp']+c['fp']) if c['tp']+c['fp'] else 0; r_ = c['tp']/(c['tp']+c['fn']) if c['tp']+c['fn'] else 0
    return p, r_, 2*p*r_/(p+r_) if p+r_ else 0
def tot(d, ks):
    c = collections.Counter()
    for k in ks: c.update(d[k])
    return c

out = {}
for h, ks in halves.items():
    b, fu = prf(tot(base, ks)), prf(tot(full, ks))
    s = [x for x in samples if x['doc'] in ks]
    out[h] = dict(F1_sans=b[2], F1_avec=fu[2], P_sans=b[0], R_sans=b[1], P_avec=fu[0], R_avec=fu[1], seuil=b[2]/2,
                  ajoutees=len(s), justes=sum(x['ok'] for x in s))
print(json.dumps(out, indent=1))

def by(feat):
    res = {}
    for h, ks in halves.items():
        grp = collections.defaultdict(list)
        for x in samples:
            if x['doc'] in ks: grp[x[feat]].append(x['ok'])
        res[h] = {v: (len(l), sum(l)/len(l)) for v, l in grp.items()}
    return res
for feat in ('votes','conf','preuve','distance','ancre','type'):
    r = by(feat)
    print('\n==', feat)
    for v in sorted(set(r['pairs'])|set(r['impairs']), key=str):
        a = r['pairs'].get(v, (0,0)); b = r['impairs'].get(v, (0,0))
        print(f"  {str(v):45} pairs n={a[0]:4} juste={a[1]:.0%} | impairs n={b[0]:4} juste={b[1]:.0%}")

# filtre choisi sur une moitie (groupes au-dessus du seuil, n>=5), mesure sur l'autre
feats = ('votes','conf','preuve','distance','ancre','type')
print('\n== validation croisee des filtres')
cv = {}
for feat in feats + ('combo',):
    for train, test in (('pairs','impairs'),('impairs','pairs')):
        key = (lambda x: (x['votes'], x['ancre'], x['distance'])) if feat == 'combo' else (lambda x, f=feat: x[f])
        grp = collections.defaultdict(list)
        for x in samples:
            if x['doc'] in halves[train]: grp[key(x)].append(x['ok'])
        good = {v for v, l in grp.items() if len(l) >= 5 and sum(l)/len(l) > out[train]['seuil']}
        keep = {x['id'] for x in samples if x['doc'] in halves[test] and key(x) in good}
        c = collections.Counter()
        for k in halves[test]:
            st, _ = counts(k, strip(docs[k][1], keep)); c.update(st)
        f1 = prf(c)[2]
        cv[(feat, test)] = (len(good), len(keep), f1 - out[test]['F1_sans'])
        print(f"  {feat:9} choisi sur {train:7} -> {test:7}: groupes {len(good):3}, relations gardees {len(keep):4}, delta F1 {100*(f1-out[test]['F1_sans']):+.2f} pt")
json.dump(dict(out=out, samples=samples), open(OUT/'resultats.json','w', encoding='utf-8'), ensure_ascii=False, indent=1)
