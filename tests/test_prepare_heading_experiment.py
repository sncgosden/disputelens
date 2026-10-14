import copy

from disputelens.prepare_heading_experiment import evidence_signature


def test_only_headings_can_change_without_changing_evidence_signature():
    original = [{'parent_id': 'a', 'metadata': {'scheme': 'Mastercard'},
                 'source_sha256': 'hash', 'blocks': [
                     {'passage_id': 'p', 'text': 'exact text', 'locator': {'pdf_page': 229},
                      'headings': ['Issuer']}]}]
    changed = copy.deepcopy(original)
    changed[0]['blocks'][0]['headings'] = ['Refund', 'Issuer']
    assert evidence_signature(original) == evidence_signature(changed)
    changed[0]['blocks'][0]['text'] = 'different'
    assert evidence_signature(original) != evidence_signature(changed)
    changed = copy.deepcopy(original)
    changed[0]['metadata']['scheme'] = 'Visa'
    assert evidence_signature(original) != evidence_signature(changed)
