"""Fixed retrieval metrics over source evidence, independent of generation."""
import math

from .applicability import applicable
from .client import ModelError


def covered_fraction(evidence, passage_id, length):
    if not length:
        return 0.
    spans = sorted((e['evidence_character_start'], e['evidence_character_end'])
                   for e in evidence if e['passage_id'] == passage_id)
    covered, right = 0, 0
    for start, end in spans:
        if not 0 <= start <= end <= length:
            raise ModelError('Invalid evidence span while scoring retrieval.')
        covered += max(0, end-max(start, right))
        right = max(right, end)
    return covered / length


def score_retrieval(results, case, units, k=5):
    if k < 1:
        raise ModelError('Metric cutoff must be positive.')
    selected = results[:k]
    if len({r['unit']['chunk_id'] for r in selected}) != len(selected):
        raise ModelError('Duplicate search-unit IDs must be removed before scoring.')
    if any(not applicable(r['unit']['metadata'], **case['filters']) for r in selected):
        raise ModelError('Inapplicable results cannot be scored as valid retrieval.')
    gold = set(case['relevant_passage_ids'])
    eligible = [u for u in units if applicable(u['metadata'], **case['filters'])]
    lengths = {}
    for unit in eligible:
        for evidence in unit['evidence']:
            pid = evidence['passage_id']
            if pid not in gold:
                continue
            length = evidence['original_evidence_characters']
            if pid in lengths and lengths[pid] != length:
                raise ModelError('Evidence length differs between source units.')
            lengths[pid] = length
    retrieved = {pid for r in selected for pid in r['unit']['passage_ids']}
    fragments = [e for r in selected for e in r['unit']['evidence']]
    fractions = {pid: covered_fraction(fragments, pid, lengths.get(pid)) for pid in gold}
    full = sum(value == 1. for value in fractions.values())
    def gain(unit):
        return max((covered_fraction(unit['evidence'], pid, lengths.get(pid))
                    for pid in gold), default=0.)
    def dcg(gains):
        return sum(g / math.log2(rank+2) for rank, g in enumerate(gains))
    ideal = dcg(sorted((gain(u) for u in eligible), reverse=True)[:k])
    actual = dcg([gain(r['unit']) for r in selected])
    # No-gold cases remain in the report, but have no recall/NDCG denominator.
    # Answerable cases whose gold is absent from the corpus receive zero, not omission.
    return {'case_id': case['case_id'], 'cutoff': k,
        'expected_passages': len(gold), 'retrieved_units': len(selected),
        'retrieved_unique_passages': len(retrieved),
        'fully_retrieved_expected_passages': full,
        'passage_recall': full/len(gold) if gold else None,
        'fractional_passage_recall': sum(fractions.values())/len(gold) if gold else None,
        'gold_passage_precision': full/len(retrieved) if retrieved else 0.,
        'ndcg': actual/ideal if ideal else 0. if gold else None,
        'all_expected_evidence_retrieved': full == len(gold) if gold else None,
        'missing_gold_from_applicable_corpus': sorted(gold-set(lengths)),
        'evidence_coverage': fractions,
        'no_gold_case': not gold}
