import pytest

from disputelens.claude_answer_trial import final_text
from disputelens.client import ModelError


def test_final_text_excludes_thinking():
    data = {'stop_reason': 'end_turn', 'content': [
        {'type': 'thinking', 'thinking': 'private intermediate output'},
        {'type': 'text', 'text': '{"status":"answered"}'}]}
    assert final_text(data) == '{"status":"answered"}'


@pytest.mark.parametrize('reason', ['max_tokens', 'pause_turn', 'tool_use', None])
def test_incomplete_claude_response_not_scored(reason):
    with pytest.raises(ModelError, match='did not finish normally'):
        final_text({'stop_reason': reason, 'content': [{'type': 'text', 'text': 'partial'}]})


def test_reasoning_only_not_scored():
    with pytest.raises(ModelError, match='no final answer'):
        final_text({'stop_reason': 'end_turn', 'content': [{'type': 'thinking', 'thinking': 'analysis'}]})
