"""Equal-weight reciprocal rank fusion with an inspectable component trace."""
from .client import ModelError


def fuse_rankings(vector_results, keyword_results, top_k=5, rank_constant=60):
    if not 1 <= top_k <= 50 or rank_constant < 1:
        raise ModelError('Invalid fusion limit or rank constant.')
    combined = {}
    for method, results, score_key in (('vector', vector_results, 'similarity'),
                                      ('bm25', keyword_results, 'bm25_score')):
        seen = set()
        for rank, result in enumerate(results, 1):
            unit_id = result['unit']['chunk_id']
            if unit_id in seen or result['rank'] != rank:
                raise ModelError('Each component ranking must contain unique IDs and consecutive ranks.')
            seen.add(unit_id)
            entry = combined.setdefault(unit_id, {'unit': result['unit'], 'rrf_score': 0.,
                'component_ranks': {'vector': None, 'bm25': None},
                'component_scores': {'vector': None, 'bm25': None}})
            if entry['unit'] != result['unit']:
                raise ModelError('The same search unit has different payloads across retrieval methods.')
            entry['rrf_score'] += 1. / (rank_constant + rank)
            entry['component_ranks'][method] = rank
            entry['component_scores'][method] = result[score_key]
    ordered = sorted(combined.values(), key=lambda e: (-e['rrf_score'], e['unit']['chunk_id']))
    return [{'rank': rank, **entry} for rank, entry in enumerate(ordered[:top_k], 1)]
