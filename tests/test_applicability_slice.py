from disputelens.applicability_slice_trial import load_slice
from disputelens.experimental_applicability import decide_applicability


def test_reviewed_spans_do_not_include_other_payment_rails_or_goods_types():
    config, originals = load_slice()
    for mapping in config['maps']:
        if mapping['disposition'] != 'reviewed_span':
            continue
        text = originals[mapping['passage_id']]['occurrences'][0]['evidence'][0]['text']
        span = text[mapping['span_start']:mapping['span_end']]
        assert span and span != text
        assert 'Maestro' not in span and 'Intangible Goods' not in span and 'QR Code' not in span


def test_reviewed_matching_missing_and_conflicting_scope_are_distinct():
    config, _ = load_slice()
    for mapping in config['maps']:
        if mapping['review_status'] != 'reviewed':
            assert decide_applicability(mapping,{})['decision']=='unreviewed'
            continue
        requirements=mapping['requirements']
        assert decide_applicability(mapping,requirements)['decision']=='applicable'
        for key,value in requirements.items():
            missing={k:v for k,v in requirements.items() if k!=key}
            assert key in decide_applicability(mapping,missing)['missing']
            conflicting={**requirements,key: not value if type(value) is bool else 'contradictory_fixture'}
            assert decide_applicability(mapping,conflicting)['decision']=='inapplicable'


def test_incomplete_exception_clauses_are_outside_authorized_spans():
    config, originals = load_slice()
    for mapping in config['maps']:
        if mapping['passage_id'] in ['mastercard-chargeback-guide:page-419:paragraph-2',
                                     'mastercard-chargeback-guide:page-419:paragraph-3']:
            text=originals[mapping['passage_id']]['occurrences'][0]['evidence'][0]['text']
            span=text[mapping['span_start']:mapping['span_end']]
            assert 'This requirement does not apply' not in span
            assert 'The issuer listed' not in span
            assert mapping['disposition']=='reviewed_span'
