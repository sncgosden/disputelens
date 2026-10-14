"""Scope-invariance check: is a quoted sentence repeated across reason-code sections? Offline; stdlib only.

Rule and thresholds are fixed in eval/experiments/scope-invariance-v1/protocol.json.
"""
import json
import re
from pathlib import Path

DOCUMENTS = Path('data/indexes/section-hierarchy/71bf6051f48778a5e9ca12c1/documents.json')
PARENT = 'mastercard-chargeback-guide'
MIN_SECTIONS = 20
MIN_FAMILIES = 4
GAP = re.compile(r'(?<=-)\s+')
_CACHE = {}


def norm(text):
    return GAP.sub('', ' '.join(text.split()))


def order(passage_id):
    m = re.search(r':page-(\d+):paragraph-(\d+)', passage_id)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def sections():
    if 'sections' not in _CACHE:
        found = []
        def walk(x):
            if isinstance(x, dict):
                if 'passage_id' in x and 'text' in x and x.get('parent_id') == PARENT:
                    found.append(x)
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)
        walk(json.loads(DOCUMENTS.read_text()))
        grouped = {}
        for p in found:
            h = p['headings']
            if len(h) > 3 and h[1].startswith('Chapter 2'):
                grouped.setdefault(tuple(h[2:]), []).append(p)
        _CACHE['sections'] = {path: (path[0], norm(' '.join(p['text'] for p in sorted(ps, key=lambda p: order(p['passage_id'])))))
                              for path, ps in grouped.items()}
    return _CACHE['sections']


def match(quote):
    q = norm(quote)
    hit = [(path, fam) for path, (fam, text) in sections().items() if q in text]
    return {'sections': len(hit), 'families': len({fam for _, fam in hit})}


def is_invariant(quote):
    m = match(quote)
    return m['sections'] >= MIN_SECTIONS and m['families'] >= MIN_FAMILIES


# --- v2 (scope-invariance-v2 protocol) ---
MIN_WORDS = 8
FOLLOW_WORDS = 25
STABLE_SHARE = 0.75
SENTENCE = re.compile(r'(?<=[.!?])\s+')


def substantive(quote):
    return len(norm(quote).split()) >= MIN_WORDS


def following(quote):
    """For each section containing the quote: (path, family, next 25 words or '<end>')."""
    q = norm(quote)
    rows = []
    for path, (fam, text) in sections().items():
        i = text.find(q)
        if i >= 0:
            tail = text[i + len(q):].split()[:FOLLOW_WORDS]
            rows.append((path, fam, ' '.join(tail) if tail else '<end>'))
    return rows


def stability(rows):
    counts = {}
    for _, _, tail in rows:
        counts[tail] = counts.get(tail, 0) + 1
    if not rows:
        return 0.0, None
    modal = max(counts, key=lambda t: (counts[t], t))
    return counts[modal] / len(rows), modal


def quote_report(quote):
    rows = following(quote)
    share, modal = stability(rows)
    sections_n, families_n = len(rows), len({f for _, f, _ in rows})
    invariant = sections_n >= MIN_SECTIONS and families_n >= MIN_FAMILIES
    return {'sections': sections_n, 'families': families_n, 'invariant': invariant,
            'stable_share': round(share, 3), 'context_stable': share >= STABLE_SHARE,
            'substantive': substantive(quote)}


def claim_invariant(quotes):
    reports = [quote_report(q) for q in quotes if substantive(q)]
    return bool(reports) and all(r['invariant'] and r['context_stable'] for r in reports), reports


def repeated_set():
    """Every distinct sentence of >= 12 words found in >= 20 sections spanning >= 4 families, with its stability."""
    where = {}
    for path, (fam, text) in sections().items():
        for sentence in set(SENTENCE.split(text)):
            if len(sentence.split()) >= 12:
                where.setdefault(sentence, []).append((path, fam))
    out = []
    for sentence, places in where.items():
        if len({p for p, _ in places}) >= MIN_SECTIONS and len({f for _, f in places}) >= MIN_FAMILIES:
            share, _ = stability(following(sentence))
            out.append({'sentence': sentence[:90], 'sections': len(places), 'stable_share': round(share, 3),
                        'context_stable': share >= STABLE_SHARE})
    return out
