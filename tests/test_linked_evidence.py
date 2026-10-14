from disputelens.linked_evidence_check import verify_linked_evidence


def test_document_option_has_continuation_and_separate_provenance():
    config=verify_linked_evidence()
    link=next(x for x in config['links'] if x['id']=='form0412-document-option')
    first,second=link['pieces']
    assert 'Form 0412' in first['text']
    assert 'authorize the transaction.' in second['text']
    assert first['passage_id']!=second['passage_id']


def test_complete_exceptions_do_not_waive_other_requirements():
    config=verify_linked_evidence()
    link=next(x for x in config['links'] if x['id']=='listing-and-exceptions')
    text=' '.join(' '.join(p['text'].split()) for p in link['pieces'])
    assert '180-calendar days or until card expiration (whichever is shorter)' in text
    assert 'transaction did not occur at a CAT 2 device' in text
    assert 'parameters are set to zero' in text and 'alternate host' in text
    assert 'The issuer closed' not in text and 'The issuer blocked' not in text
