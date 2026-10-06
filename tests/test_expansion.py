import json
from pathlib import Path

from disputelens.applicability import applicable

ROOT = Path(__file__).resolve().parents[1]


def test_provider_boundary_and_unknown_account():
    sources = json.loads((ROOT / 'data/source-manifest.json').read_text())['sources']
    for provider in ['Stripe', 'Adyen', 'Square', 'PayPal']:
        allowed = [s for s in sources if applicable(s, corpus='real', provider=provider,
                                                   scheme='Visa', region='UK')]
        assert allowed
        assert all(s['provider'] in (None, provider) for s in allowed)
        assert all(s['scheme'] in (None, 'Visa') for s in allowed)
    assert not any(applicable(s, corpus='real') for s in sources)


def test_scheme_region_and_fixture_isolation():
    sources = json.loads((ROOT / 'data/source-manifest.json').read_text())['sources']
    square = next(s for s in sources if s['source_id'] == 'square-uk-disputes')
    assert not applicable(square, corpus='real', provider='Square', region='US')
    assert applicable(square, corpus='real', provider='Square', region='UK')
    for s in sources:
        if s['corpus'] == 'fixture':
            assert not applicable(s, corpus='real', provider=s['provider'], scheme=s['scheme'])
        if s['scheme'] == 'Mastercard':
            assert not applicable(s, corpus='real', provider='Stripe', scheme='Visa', region='UK')


def test_every_pdf_page_is_present():
    for sid, count in [('visa-dispute-management-june-2024', 67), ('mastercard-chargeback-guide', 1153)]:
        path = ROOT / 'data/parsed-expanded' / (sid + '.json')
        if not path.exists():
            import pytest
            pytest.skip('Download and parse expanded sources first')
        d = json.loads(path.read_text())
        assert d['page_count'] == count
        assert {b['pdf_page'] for b in d['blocks']} == set(range(1, count + 1))


def test_expanded_eval_contract_and_reserved_split():
    import re
    schema = json.loads((ROOT / 'eval/case.schema.json').read_text())
    directory = ROOT / 'eval/expanded'
    if not (directory / 'dev-cases.json').exists():
        import pytest
        pytest.skip('Expanded question drafting and source review have not run')
    cases = []
    for split, count in [('dev', 45), ('holdout', 15)]:
        subset = json.loads((directory / (split + '-cases.json')).read_text())
        assert len(subset) == count
        assert all(c['split'] == split for c in subset)
        cases.extend(subset)
    assert len({c['case_id'] for c in cases}) == 60
    for case in cases:
        assert set(schema['required']) <= case.keys()
        assert case.keys() <= schema['properties'].keys()
        assert re.fullmatch(r'E[0-9]{2}', case['case_id'])
        assert isinstance(case['question'], str) and case['question'].strip()
        assert case['review_status'] == 'approved'
        assert case['answerability'] in schema['properties']['answerability']['enum']
        filters = case['filters']
        contract = schema['properties']['filters']
        assert set(contract['required']) <= filters.keys()
        assert filters.keys() <= contract['properties'].keys()
        assert filters['corpus'] in ('real', 'fixture')
        assert all(v is None or isinstance(v, str) for v in filters.values())
        assert len(case['relevant_passage_ids']) == len(set(case['relevant_passage_ids']))
        assert all(isinstance(p, str) for p in case['relevant_passage_ids'])
        assert case['expected_claims']
        for claim in case['expected_claims']:
            assert set(claim) == {'claim_id', 'text', 'supporting_passage_ids'}
            assert isinstance(claim['claim_id'], str)
            assert isinstance(claim['text'], str) and claim['text'].strip()
            assert claim['supporting_passage_ids'] or case['answerability'] == 'not_in_sources'
            assert set(claim['supporting_passage_ids']) <= set(case['relevant_passage_ids'])
        expected_split = 'holdout' if int(case['case_id'][1:]) % 4 == 0 else 'dev'
        assert case['split'] == expected_split
        assert isinstance(case.get('notes', ''), str)
        assert all(isinstance(x, str) for x in case.get('forbidden_claims', []))
