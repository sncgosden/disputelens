from disputelens.claude_answer_pilot import CASES, summarize


def test_pilot_counts_failures_and_does_not_claim_semantic_accuracy():
    result = summarize([
        {'status': 'complete_requires_review', 'generation_seconds': 2,
         'usage': {'input_tokens': 100, 'output_tokens': 20}},
        {'status': 'failed', 'generation_seconds': 10,
         'usage': {'input_tokens': 200, 'output_tokens': 30}},
        {'status': 'unavailable'}])
    assert result['citation_valid_answers'] == 1
    assert result['failed_or_unavailable'] == 2
    assert result['median_attempt_seconds'] == 6
    assert result['input_tokens'] == 300
    assert result['output_tokens'] == 50
    assert 'not scored' in result['semantic_quality']


def test_fixed_pilot_includes_real_workflows_and_controlled_safety_cases():
    assert CASES == ('E31', 'E33', 'E51', 'E57', 'E58')
