from disputelens.evaluate_focused_context import choose_strategy, experiment_pointer


def test_explicit_codes_choose_keyword_search_without_gold():
    assert choose_strategy('When can an issuer use Mastercard reason code 4853?') == 'bm25'
    assert choose_strategy('What does Visa Condition 13.1 mean?') == 'bm25'
    assert choose_strategy('The promised refund never arrived. What evidence should I send?') == 'hybrid'


def test_ordinary_amounts_do_not_trigger_code_routing():
    assert choose_strategy('A customer disputes a £100 purchase made in 2026.') == 'hybrid'


def test_wider_experiment_does_not_replace_five_candidate_pointer():
    assert str(experiment_pointer(5, 2500)) == 'data/indexes/focused-context/latest.json'
    assert str(experiment_pointer(10, 4500)) == 'data/indexes/focused-context/latest-top10-words4500.json'
    assert experiment_pointer(10, 4500) != experiment_pointer(5, 2500)
