import pytest

from disputelens.client import ModelError
from disputelens.embed_batch import audit_chunks, select_trial, safe_error, loaded_embedding_model


def chunk(name, text='A real passage about merchant dispute evidence.'):
    return {'chunk_id': name + ':chunk-1', 'parent_id': name, 'text': text,
            'word_count': 60, 'exceeds_target': False,
            'metadata': {'corpus': 'real', 'status': 'current'}}


def test_size_check_includes_prefix_and_reserve():
    seen = []
    def tokenize(text):
        seen.append(text)
        return list(range(len(text)))
    rows = audit_chunks([chunk('one', 'abc'), chunk('two', 'abcd')], tokenize, 13, 'D:')
    assert seen == ['D:abc', 'D:abcd']
    assert [row['fits'] for row in rows] == [True, False]


def test_diagnostic_redacts_credentials(monkeypatch):
    monkeypatch.setenv('LM_API_TOKEN', 'private-local-token')
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'private-cloud-key')
    message = safe_error(RuntimeError('private-local-token private-cloud-key Bearer other-token'))
    assert 'RuntimeError' in message
    assert 'private-local-token' not in message
    assert 'private-cloud-key' not in message
    assert 'other-token' not in message


def test_sdk_discovers_service_and_selects_only_matching_loaded_model():
    from types import SimpleNamespace
    selected = SimpleNamespace(identifier='nomic')
    class FakeSDK:
        def list_loaded_models(self, namespace):
            assert namespace == 'embedding'
            return [SimpleNamespace(identifier='other'), selected]
        def configure_default_client(self, host):
            pytest.fail('Do not force SDK connections onto the HTTP API port')
    assert loaded_embedding_model(FakeSDK(), 'nomic') is selected
    with pytest.raises(ModelError):
        loaded_embedding_model(FakeSDK(), 'missing')


def test_invalid_limit_and_empty_input_fail():
    with pytest.raises(ModelError):
        audit_chunks([chunk('one')], lambda text: [1], 8, '')
    with pytest.raises(ModelError):
        audit_chunks([chunk('one', '')], lambda text: [1], 2048, '')


def test_trial_excludes_fixtures_old_versions_and_repeated_parents():
    fixture, old = chunk('fixture'), chunk('old')
    fixture['metadata']['corpus'] = 'fixture'
    old['metadata']['status'] = 'superseded'
    visa = chunk('visa')
    visa['metadata']['status'] = 'snapshot'
    selected = select_trial([fixture, old, visa, chunk('visa'),
                             chunk('stripe'), chunk('mastercard')])
    assert [row['parent_id'] for row in selected] == ['visa', 'stripe', 'mastercard']
