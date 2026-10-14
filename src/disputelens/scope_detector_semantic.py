"""Semantic subtype detector. Rule and thresholds: eval/experiments/scope-detector-semantic-v1/protocol.json.

Stages: calibrate (pairs.json, writes chosen.json), test (nearmiss.json, once only), report.
Embeddings come from the local model via configured_models().embed and are cached by hash.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

import numpy as np

from .scope_detector import BUNDLE, PHRASES, unestablished

FOLDER = Path('eval/experiments/scope-detector-semantic-v1')
PROTOCOL = FOLDER / 'protocol.json'
CHUNKS = Path('data/indexes/section-hierarchy/71bf6051f48778a5e9ca12c1/chunks.json')
PAIRS = Path('eval/stress/mastercard-scope-v1/pairs.json')
NEARMISS = Path('eval/stress/mastercard-scope-v1/nearmiss.json')
CACHE = Path('data/indexes/scope-detector-semantic/cache.json')
TAUS = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]
DELTAS = [0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06]


def clean(title):
    return ' '.join(re.sub(r'\([^)]*\)', ' ', title.replace('\xa0', ' ')).split())


def candidate_titles(chunks):
    out = set()
    for chunk in chunks:
        h = chunk.get('headings') or []
        if len(h) >= 4 and 'Chapter 2' in h[1].replace('\xa0', ' ') and clean(h[3]):
            out.add(clean(h[3]))
    return sorted(out)


def load_chunks():
    data = json.loads(CHUNKS.read_text())
    return data['chunks'] if 'chunks' in data else next(v for v in data.values() if isinstance(v, list))


def nearest(question_vec, title_vecs, titles):
    """Return (best title, best cosine, margin over second best)."""
    q = np.asarray(question_vec, float)
    t = np.asarray(title_vecs, float)
    sims = (t @ q) / (np.linalg.norm(t, axis=1) * np.linalg.norm(q))
    order = np.argsort(-sims)
    second = sims[order[1]] if len(order) > 1 else -1.0
    return titles[order[0]], float(sims[order[0]]), float(sims[order[0]] - second)


def is_established(own_title, best, sim, margin, tau, delta):
    return best == own_title and sim >= tau and margin >= delta


def decide(base_flags, established):
    """base_flags: v2 flags for the passage. If subtype established, keep only phrase qualifiers."""
    if base_flags and established:
        return [x for x in base_flags if x in PHRASES]
    return list(base_flags)


def grid_flags(row, tau, delta):
    est = is_established(row['own'], row['best'], row['sim'], row['margin'], tau, delta)
    return bool(decide(row['base'], est))


def score_grid(rows):
    out = []
    for tau in TAUS:
        for delta in DELTAS:
            flagged = [grid_flags(r, tau, delta) for r in rows]
            out.append({'tau': tau, 'delta': delta,
                        'unscoped_flagged': sum(f for f, r in zip(flagged, rows) if r['label'] == 'unscoped'),
                        'scoped_false_flags': sum(f for f, r in zip(flagged, rows) if r['label'] == 'scoped')})
    return out


def select(grid):
    full = max(g['unscoped_flagged'] for g in grid)
    pool = [g for g in grid if g['unscoped_flagged'] == full]
    return sorted(pool, key=lambda g: (g['scoped_false_flags'], -g['tau'], -g['delta']))[0]


class Embedder:
    def __init__(self, client=None):
        self.client = client
        self.cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}

    def vectors(self, texts, kind):
        keys = [hashlib.sha256(f'{kind}\x00{t}'.encode()).hexdigest() for t in texts]
        missing = [(k, t) for k, t in zip(keys, texts) if k not in self.cache]
        if missing:
            if self.client is None:
                from .client import configured_models
                self.client = configured_models()
            for i in range(0, len(missing), 16):
                batch = missing[i:i + 16]
                vecs = self.client.embed([t for _, t in batch], kind=kind)
                for (k, _), v in zip(batch, vecs):
                    self.cache[k] = [float(x) for x in v]
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(self.cache))
        return np.asarray([self.cache[k] for k in keys])


def build_rows(rows, titles, title_vecs, embedder):
    qvecs = embedder.vectors([r['question'] for r in rows], 'query')
    out = []
    for r, qv in zip(rows, qvecs):
        h = r['cited_headings']
        best, sim, margin = nearest(qv, title_vecs, titles)
        out.append({'id': r['id'], 'label': r['label'], 'own': clean(h[3]) if len(h) >= 4 else None,
                    'base': unestablished(h, r['question'], 2), 'best': best, 'sim': round(sim, 4), 'margin': round(margin, 4)})
    return out


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def setup(embedder):
    titles = candidate_titles(load_chunks())
    return titles, embedder.vectors(titles, 'document')


def calibrate(embedder=None):
    embedder = embedder or Embedder()
    chosen_path = FOLDER / 'chosen.json'
    if chosen_path.exists():
        raise SystemExit('chosen.json exists: calibration is done once.')
    titles, tv = setup(embedder)
    rows = build_rows(json.loads(PAIRS.read_text())['rows'], titles, tv, embedder)
    grid = score_grid(rows)
    pick = select(grid)
    scoped = sum(r['label'] == 'scoped' for r in rows)
    unscoped = len(rows) - scoped
    result = {'protocol_sha256': sha(PROTOCOL), 'pairs_sha256': sha(PAIRS), 'titles': len(titles),
              'chosen': pick, 'S2': {'unscoped_flagged': pick['unscoped_flagged'], 'of_unscoped': unscoped,
                                     'scoped_false_flags': pick['scoped_false_flags'], 'of_scoped': scoped,
                                     'pass': pick['unscoped_flagged'] >= 11 and pick['scoped_false_flags'] <= 4},
              'rows': rows, 'grid': grid}
    chosen_path.write_text(json.dumps(result, indent=2))
    result['chosen_sha256'] = sha(chosen_path)
    chosen_path.write_text(json.dumps(result, indent=2))
    print(json.dumps({k: result[k] for k in ('chosen', 'S2', 'titles')}, indent=1))
    return result


def dev_regression(pick, titles, tv, embedder):
    cases = json.loads(BUNDLE.read_text())['cases']
    valid = [c for c in cases if c['saved_status'] == 'citation_valid_requires_review']
    qv = embedder.vectors([c['question'] for c in valid], 'query')
    flagged_v2, flagged_sem = {}, {}
    for c, q in zip(valid, qv):
        index = {e['citation_id']: e for g in c['frozen_context_pack']['groups'] for e in g['evidence']}
        cited = {x['id'] for cl in c['answer']['claims'] for x in cl['citations'] if x['id'] in index}
        best, sim, margin = nearest(q, tv, titles)
        for i in cited:
            h = index[i]['headings']
            base = unestablished(h, c['question'], 2)
            est = len(h) >= 4 and is_established(clean(h[3]), best, sim, margin, pick['tau'], pick['delta'])
            if base:
                flagged_v2.setdefault(c['case_id'], []).append(i)
            if decide(base, est):
                flagged_sem.setdefault(c['case_id'], []).append(i)
    same = {k: sorted(v) for k, v in flagged_v2.items()} == {k: sorted(v) for k, v in flagged_sem.items()}
    return {'v2': flagged_v2, 'semantic': flagged_sem, 'S3': same and set(flagged_sem) == {'E13', 'E22'}}


def test(embedder=None):
    embedder = embedder or Embedder()
    done = FOLDER / 'result.json'
    if done.exists():
        raise SystemExit('Test already run once; refusing a second run.')
    chosen_path = FOLDER / 'chosen.json'
    if not chosen_path.exists():
        raise SystemExit('Run calibrate first.')
    chosen = json.loads(chosen_path.read_text())
    pick = chosen['chosen']
    titles, tv = setup(embedder)
    rows = build_rows(json.loads(NEARMISS.read_text())['rows'], titles, tv, embedder)
    cleared = sum(not grid_flags(r, pick['tau'], pick['delta']) for r in rows)
    dev = dev_regression(pick, titles, tv, embedder)
    result = {'protocol_sha256': sha(PROTOCOL), 'chosen_sha256': chosen['chosen_sha256'], 'nearmiss_sha256': sha(NEARMISS),
              'chosen': pick, 'nearmiss_cleared': cleared, 'of': len(rows), 'near_miss_rows': rows, 'development': dev,
              'verdict': {'S1': cleared <= 3, 'S2': chosen['S2']['pass'], 'S3': dev['S3']}}
    result['verdict']['S4_note'] = 'unit tests run separately: pytest tests/test_scope_detector_semantic.py'
    result['verdict']['pass_excluding_S4'] = all(result['verdict'][k] for k in ('S1', 'S2', 'S3'))
    done.write_text(json.dumps(result, indent=2))
    print(json.dumps({k: result[k] for k in ('chosen', 'nearmiss_cleared', 'of', 'verdict')}, indent=1))
    print('development flagged:', json.dumps(dev['semantic']))
    return result


def known_e16(embedder=None):
    """Reported, not thresholded: E16 (holdout false positive) under the chosen detector. Known case."""
    embedder = embedder or Embedder()
    pick = json.loads((FOLDER / 'chosen.json').read_text())['chosen']
    titles, tv = setup(embedder)
    base = Path('data/indexes/holdout-final/a5db01e43953f6c1d4a77706')
    question = json.loads((base / 'retrieval/E16.json').read_text())['question']
    pack = json.loads((base / 'packs/E16.json').read_text())
    answer = json.loads((base / 'answers/E16.json').read_text())['answer']
    index = {e['citation_id']: e for g in pack['groups'] for e in g['evidence']}
    cited = sorted({c['id'] for cl in answer['claims'] for c in cl['citations'] if c['id'] in index})
    best, sim, margin = nearest(embedder.vectors([question], 'query')[0], tv, titles)
    rows = []
    for i in cited:
        h = index[i]['headings']
        b = unestablished(h, question, 2)
        est = len(h) >= 4 and is_established(clean(h[3]), best, sim, margin, pick['tau'], pick['delta'])
        rows.append({'id': i, 'subtype': h[3] if len(h) >= 4 else None, 'v2_flags': b, 'semantic_flags': decide(b, est)})
    out = {'chosen': pick, 'nearest': best, 'sim': round(sim, 4), 'margin': round(margin, 4), 'passages': rows,
           'note': 'known case, designed after seeing it; not validation'}
    (FOLDER / 'known-e16.json').write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=1))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--stage', choices=['calibrate', 'test', 'known'], required=True)
    a = p.parse_args()
    {'calibrate': calibrate, 'test': test, 'known': known_e16}[a.stage]()


if __name__ == '__main__':
    main()
