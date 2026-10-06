from disputelens.keyword_search import tokenize, retrieve_keyword


def unit(name, text, **metadata):
    return {'chunk_id': name, 'text': text, 'metadata': {
        'corpus': 'real', 'provider': 'Stripe', 'scheme': None,
        'status': 'snapshot', **metadata}}


def test_reason_codes_stay_distinct():
    assert tokenize('VISA 13.1, 13.10; 12.6.1 and 4853') == ['visa', '13.1', '13.10', '12.6.1', 'and', '4853']


def test_keyword_ranking_filters_before_scoring_and_returns_no_unmatched_fillers():
    filters = {'corpus': 'real', 'provider': 'Stripe', 'scheme': 'Visa', 'region': 'UK'}
    eligible = [unit('correct', 'Condition 13.1 goods not received'),
                unit('different-code', 'Condition 13.10'),
                unit('refund', 'refund receipt'), unit('delivery', 'delivery tracking')]
    wrong = [unit('wrong-provider', '13.1 ' * 50, provider='Adyen'),
             unit('old', '13.1', status='superseded'),
             unit('fixture', '13.1', corpus='fixture'),
             unit('wrong-scheme', '13.1', scheme='Mastercard'),
             unit('wrong-region', '13.1', region='US')]
    baseline = retrieve_keyword(eligible, '13.1', filters, 5)
    assert [r['unit']['chunk_id'] for r in baseline] == ['correct']
    assert retrieve_keyword(eligible + wrong, '13.1', filters, 5) == baseline
    assert retrieve_keyword(eligible, 'unfindableterm', filters, 5) == []
    assert retrieve_keyword(eligible, '13.1', {**filters, 'provider': None}, 5) == []
