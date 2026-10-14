from disputelens.evaluate_claude_answers import summarize


def test_summary_keeps_failed_and_unrun_in_denominator_and_missing_cost_visible():
    result = summarize([
        {'status': 'citation_valid_requires_review', 'generation_seconds': 2, 'calculated_api_cost_usd': .03},
        {'status': 'generation_or_validation_failed', 'generation_seconds': 300},
        {'status': 'not_run'}])
    assert result['expected_cases'] == 3
    assert result['citation_valid'] == result['failed'] == result['not_run'] == 1
    assert result['attempts_without_priced_usage'] == 1
    assert result['calculated_cost_usd_for_known_usage'] == .03
    assert result['semantic_accuracy'] == 'not scored'
