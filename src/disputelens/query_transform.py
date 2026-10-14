"""Small declared terminology expansion; never infer access settings or reason codes."""
import re


RULES = (
    ('recurring', r'\b(cancel(?:l)?ed|cancellation|recurring|subscription|renewal)\b',
     'cancelled recurring transaction recurring payment cancellation'),
    ('non_receipt', r'\b(never showed up|never arrived|not received|never received|not delivered)\b',
     'goods or services not provided merchandise not received'),
    ('duplicate', r'\b(charged twice|double charge|double charged|duplicate)\b',
     'duplicate processing paid by other means'),
)


def transform_query(question):
    if not isinstance(question, str) or not question.strip():
        raise ValueError('Provide a nonempty question.')
    additions, applied = [], []
    text = question.casefold()
    for name, pattern, terms in RULES:
        # A refund not arriving is distinct from purchased goods not arriving.
        if name == 'non_receipt' and 'refund' in text:
            continue
        if re.search(pattern, text):
            applied.append(name)
            additions.append(terms)
    if 'refund' in text and re.search(r'\b(never arrived|not received|never received|not processed|never appeared)\b', text):
        applied.append('refund')
        additions.append('refund not processed credit not processed')
    return {'original': question, 'expanded': question + ('\n' + '\n'.join(additions) if additions else ''),
            'applied_rules': applied}


def fuse_queries(original, expanded, top_k=20):
    """Equal-weight RRF (constant 60); scores never mix across BM25 queries."""
    if not 1 <= top_k <= 50:
        raise ValueError('Choose between 1 and 50 final results.')
    combined = {}
    for name, results in (('original', original), ('expanded', expanded)):
        seen = set()
        for rank, result in enumerate(results, 1):
            unit = result['unit']
            key = unit['chunk_id']
            if key in seen or result['rank'] != rank:
                raise ValueError('Query rankings require unique units and consecutive ranks.')
            seen.add(key)
            entry = combined.setdefault(key, {'unit': unit, 'rrf_score': 0.,
                                               'query_ranks': {'original': None, 'expanded': None}})
            if entry['unit'] != unit:
                raise ValueError('Same unit has conflicting payloads across queries.')
            entry['rrf_score'] += 1 / (60 + rank)
            entry['query_ranks'][name] = rank
    ordered = sorted(combined.values(), key=lambda e: (-e['rrf_score'], e['unit']['chunk_id']))
    return [{'rank': rank, **entry} for rank, entry in enumerate(ordered[:top_k], 1)]
