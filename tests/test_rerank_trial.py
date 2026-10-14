import pytest

from disputelens.client import ModelError
from disputelens.rerank_trial import check_budget, request_ranking, final_ranking_text


def test_full_prompt_and_output_must_fit_before_generation():
    budget = check_budget(1000, 3112, 2048)
    assert budget['required_tokens'] == 3112
    with pytest.raises(ModelError, match='No text truncated'):
        check_budget(1000, 3111, 2048)


@pytest.mark.parametrize('values', [(-1, 4000, 2048), (1000, 0, 2048),
                                  (1000, 4000, 0), (True, 4000, 2048)])
def test_invalid_budget_cannot_authorize_a_call(values):
    with pytest.raises(ModelError):
        check_budget(*values)


def test_native_request_explicitly_disables_reasoning_and_chat_storage():
    class FakeModels:
        base = 'http://localhost:1234/v1'

        def _local_headers(self):
            return {}

        def _request(self, method, url, **kwargs):
            assert method == 'POST'
            assert url == 'http://localhost:1234/api/v1/chat'
            payload = kwargs['json']
            assert payload['reasoning'] == 'off'
            assert payload['store'] is False
            assert payload['max_output_tokens'] == 2048
            assert payload['input'] == 'full prompt'
            return {'sent': True}

    assert request_ranking(FakeModels(), 'full prompt', 'qwen3.5-4b', 2048,
                           reasoning='off') == {'sent': True}


def test_default_mode_omits_unsupported_reasoning_switch():
    class FakeModels:
        base = 'http://localhost:1234/v1'

        def _local_headers(self):
            return {}

        def _request(self, method, url, **kwargs):
            assert 'reasoning' not in kwargs['json']
            assert kwargs['json']['max_output_tokens'] == 8192
            return {'sent': True}

    assert request_ranking(FakeModels(), 'prompt', 'qwen3.5-4b', 8192) == {'sent': True}


def response(text, tokens=30, reasoning=0):
    return {'output': [{'type': 'message', 'content': text}],
            'stats': {'total_output_tokens': tokens, 'reasoning_output_tokens': reasoning}}


def test_complete_native_response_and_failure_modes():
    assert final_ranking_text(response('{"ordered_ids":["a"]}'), 2048) == '{"ordered_ids":["a"]}'
    with pytest.raises(ModelError, match='output allowance'):
        final_ranking_text(response('partial', tokens=2048), 2048)
    with pytest.raises(ModelError, match='No final'):
        final_ranking_text(response(''), 2048)
    with pytest.raises(ModelError, match='despite reasoning=off'):
        final_ranking_text(response('answer', reasoning=10), 2048)
    with pytest.raises(ModelError, match='Unexpected native'):
        final_ranking_text({}, 2048)


def test_default_mode_scores_only_final_message_and_retains_limit_guard():
    data = response('{"ordered_ids":["a"]}', tokens=3000, reasoning=2900)
    data['output'].insert(0, {'type': 'reasoning', 'content': 'not final JSON'})
    assert final_ranking_text(data, 8192, allow_reasoning=True) == '{"ordered_ids":["a"]}'
    data['stats']['total_output_tokens'] = 8192
    with pytest.raises(ModelError, match='output allowance'):
        final_ranking_text(data, 8192, allow_reasoning=True)
