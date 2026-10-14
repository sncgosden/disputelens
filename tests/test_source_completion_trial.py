import copy
import hashlib
import json

import pytest

from disputelens.client import ModelError
from disputelens.context_pack import render_context
from disputelens.source_completion_trial import complete_context


@pytest.fixture
def inputs(tmp_path):
    def block(pid, text):
        return {'passage_id': 'guide:' + pid, 'text': text, 'headings': ['Refund'],
                'locator': {'reference': 'https://example.org/' + pid, 'pdf_page': 2}}
    blocks = [block('old', 'existing complaint details'), block('new', 'five missing complaint criteria')]
    source = tmp_path / 'documents.json'
    source.write_text(json.dumps({'documents': [{'blocks': blocks}]}))
    pieces = [{'passage_id': b['passage_id'], 'start': 0, 'end': len(b['text']), 'text': b['text'],
               'headings': b['headings'], 'locator': b['locator'],
               'source_text_sha256': hashlib.sha256(b['text'].encode()).hexdigest()} for b in blocks]
    metadata = {'source_id': 'guide', 'corpus': 'real', 'status': 'snapshot', 'title': 'Guide',
                'scheme': 'Mastercard', 'provider': None, 'region': None}
    e = {**blocks[0], 'evidence_character_start': 0, 'evidence_character_end': len(blocks[0]['text']),
         'original_evidence_characters': len(blocks[0]['text']), 'complete_evidence': True, 'citation_id': 'S011'}
    group = {'metadata': metadata, 'source_sha256': 'pdfhash', 'parent_chunk_ids': ['c1'],
             'unit_ids': ['c1'], 'retrieval_ranks': [1], 'evidence': [e]}
    pack = {'groups': [group], 'budget': {'maximum': 1000, 'used': 0},
            'trusted_settings': {'corpus': 'real', 'provider': None, 'scheme': 'Mastercard', 'region': None},
            'omitted_groups': [], 'input_units': 1, 'included_units': 1, 'evaluation_identity': 'frozen'}
    pack['text'] = render_context(pack['groups'])
    supplement = {'case_id': 'E18', 'status': 'separate_diagnostic_evidence_not_baseline',
                  'source_path': str(source), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                  'pieces': pieces}
    return pack, supplement


def test_new_evidence_keeps_ids_and_provenance_without_mutating_baseline(inputs):
    pack, supplement = inputs
    original = copy.deepcopy(pack)
    candidate = complete_context(pack, supplement)
    assert pack == original
    assert candidate['citations']['S011']['passage_id'] == 'guide:old'
    assert candidate['citations']['S012']['passage_id'] == 'guide:new'
    assert candidate['citations']['S012']['source_sha256'] == 'pdfhash'
    assert candidate['groups'][1]['evidence'][0]['text'] == supplement['pieces'][1]['text']
    assert 'not retrieved evidence' in candidate['text']
    assert 'evaluation_identity' not in candidate
    assert not candidate['diagnostic_completion']['baseline_attempt_reuse_allowed']


@pytest.mark.parametrize('field,value', [('text', 'invented'), ('headings', ['Wrong scope']),
    ('locator', {'reference': 'wrong'}), ('start', 1), ('source_text_sha256', 'wrong')])
def test_tampered_source_piece_is_rejected(inputs, field, value):
    pack, supplement = inputs
    supplement['pieces'][1][field] = value
    with pytest.raises(ModelError, match='provenance'):
        complete_context(pack, supplement)


def test_changed_source_file_fails_closed(inputs):
    pack, supplement = inputs
    supplement['source_sha256'] = 'stale'
    with pytest.raises(ModelError, match='source changed'):
        complete_context(pack, supplement)


def test_tight_budget_rejects_required_evidence_without_trimming(inputs):
    pack, supplement = inputs
    pack['budget']['maximum'] = 1
    with pytest.raises(ModelError, match='no partial trimming'):
        complete_context(pack, supplement)


def test_budget_displaces_low_priority_intact_group_but_keeps_linked_evidence(inputs):
    pack, supplement = inputs
    extra = copy.deepcopy(pack['groups'][0])
    extra['unit_ids'] = ['c2']; extra['parent_chunk_ids'] = ['c2']; extra['retrieval_ranks'] = [9]
    extra['evidence'][0].update(passage_id='guide:noise', citation_id='S020', text='noise ' * 500,
                              evidence_character_end=3000, original_evidence_characters=3000)
    pack['groups'].append(extra)
    pack['budget']['maximum'] = 100
    candidate = complete_context(pack, supplement)
    assert candidate['budget']['used'] <= 100
    assert set(candidate['citations']) == {'S011', 'S021'}
    assert candidate['omitted_groups'][-1]['unit_ids'] == ['c2']
    assert candidate['groups'][0]['evidence'][0] == pack['groups'][0]['evidence'][0]


def test_provider_scope_conflict_is_rejected(inputs):
    pack, supplement = inputs
    pack['groups'][0]['metadata']['provider'] = 'Adyen'
    pack['trusted_settings']['provider'] = 'Stripe'
    with pytest.raises(ModelError, match='applicability'):
        complete_context(pack, supplement)


def test_unlinked_evidence_cannot_be_added(inputs):
    pack, supplement = inputs
    supplement['pieces'] = supplement['pieces'][1:]
    with pytest.raises(ModelError, match='link to evidence'):
        complete_context(pack, supplement)


def test_partial_existing_evidence_requires_explicit_expansion_policy(inputs):
    pack, supplement = inputs
    old = pack['groups'][0]['evidence'][0]
    old.update(text=old['text'][:8], evidence_character_end=8, complete_evidence=False)
    with pytest.raises(ModelError, match='Partial baseline'):
        complete_context(pack, supplement)


def test_duplicate_frozen_labels_fail_closed(inputs):
    pack, supplement = inputs
    pack['groups'][0]['evidence'].append(copy.deepcopy(pack['groups'][0]['evidence'][0]))
    with pytest.raises(ModelError, match='Duplicate frozen'):
        complete_context(pack, supplement)


def publisher_map(inputs, tmp_path):
    pack, supplement = inputs
    docs = json.loads(open(supplement['source_path']).read())
    for block in docs['documents'][0]['blocks']:
        block['headings'] = ['Guide', 'Refund Not Processed', 'Issuer Chargeback']
    path = tmp_path / 'publisher.json'
    path.write_text(json.dumps(docs))
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'identity': {'baseline_normalized_sha256': supplement['source_sha256'],
        'source_sha256': 'pdfhash'}, 'normalized_path': str(path), 'evidence_and_scope_unchanged': True}))
    return {'normalized_path': str(path), 'normalized_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'manifest_path': str(manifest), 'manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest()}


def test_corrected_headings_used_before_rendering_and_budgeting(inputs, tmp_path):
    pack, supplement = inputs
    provenance = publisher_map(inputs, tmp_path)
    candidate = complete_context(pack, supplement, publisher_headings=provenance)
    assert candidate['groups'][1]['evidence'][0]['headings'] == ['Guide', 'Refund Not Processed', 'Issuer Chargeback']
    assert candidate['groups'][1]['evidence'][0]['text'] == supplement['pieces'][1]['text']
    assert candidate['groups'][0]['evidence'][0] == pack['groups'][0]['evidence'][0]
    assert candidate['budget']['used'] == len(candidate['text'].split())
    assert candidate['diagnostic_completion']['publisher_heading_provenance']['normalized_sha256'] == provenance['normalized_sha256']


def test_stale_publisher_heading_file_rejected(inputs, tmp_path):
    provenance = publisher_map(inputs, tmp_path)
    provenance['normalized_sha256'] = 'changed'
    with pytest.raises(ModelError, match='provenance changed'):
        complete_context(*inputs, publisher_headings=provenance)


def test_matching_hash_cannot_hide_changed_source_text(inputs, tmp_path):
    provenance = publisher_map(inputs, tmp_path)
    from pathlib import Path
    path = Path(provenance['normalized_path'])
    docs = json.loads(path.read_text()); docs['documents'][0]['blocks'][1]['text'] = 'wrong policy'
    path.write_text(json.dumps(docs)); provenance['normalized_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ModelError, match='changed source evidence'):
        complete_context(*inputs, publisher_headings=provenance)


def test_mastercard_completion_cannot_fall_back_to_coarse_headings(inputs):
    pack, supplement = inputs
    pack['groups'][0]['metadata']['source_id'] = 'mastercard-chargeback-guide'
    with pytest.raises(ModelError, match='Publisher headings required'):
        complete_context(pack, supplement)
