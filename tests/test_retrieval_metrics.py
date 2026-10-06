import pytest

from disputelens.retrieval_metrics import score_retrieval


def unit(name, passage='p', start=0, end=10, length=10):
    return {'chunk_id': name, 'metadata': {'corpus': 'real', 'status': 'snapshot',
            'provider': None, 'scheme': 'Visa'}, 'passage_ids': [passage],
            'evidence': [{'passage_id': passage, 'evidence_character_start': start,
                          'evidence_character_end': end, 'original_evidence_characters': length}]}


def case(gold=None):
    return {'case_id': 'test', 'filters': {'corpus': 'real', 'provider': None,
            'scheme': 'Visa', 'region': None}, 'relevant_passage_ids': ['p'] if gold is None else gold}


def results(*units):
    return [{'rank': n, 'unit': u} for n, u in enumerate(units, 1)]


def test_complete_evidence_rank_discount_and_precision():
    good, wrong = unit('good'), unit('wrong', 'other')
    score = score_retrieval(results(wrong, good), case(), [good, wrong])
    assert score['passage_recall'] == 1
    assert score['gold_passage_precision'] == .5
    assert score['ndcg'] == pytest.approx(1/1.584962500721156)
    assert score_retrieval(results(wrong, good), case(), [good, wrong], k=1)['passage_recall'] == 0


def test_partial_overlap_does_not_inflate_recall_or_ndcg():
    first, overlap, rest = unit('a', start=0, end=5), unit('b', start=3, end=8), unit('c', start=5, end=10)
    score = score_retrieval(results(first, overlap), case(), [first, overlap, rest])
    assert score['passage_recall'] == 0
    assert score['fractional_passage_recall'] == .8
    assert 0 <= score['ndcg'] <= 1
    assert score_retrieval(results(first, rest), case(), [first, rest])['passage_recall'] == 1


def test_missing_gold_is_a_zero_score_and_no_gold_is_separate():
    wrong = unit('wrong', 'other')
    score = score_retrieval(results(wrong), case(), [wrong])
    assert score['passage_recall'] == score['ndcg'] == 0
    assert score['missing_gold_from_applicable_corpus'] == ['p']
    no_gold = score_retrieval([], case([]), [wrong])
    assert no_gold['passage_recall'] is None and no_gold['ndcg'] is None
    assert no_gold['no_gold_case']
