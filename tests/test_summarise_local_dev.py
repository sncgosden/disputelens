import json

from disputelens.summarise_local_dev import summarise


def test_summary_counts_failures_and_unattempted(tmp_path):
    def add(name, case, status, seconds, answer=None, error=''):
        (tmp_path / name).write_text(json.dumps({'status': status, 'generation_seconds': seconds, 'answer': answer, 'error': error,
            'identity': {'model': 'm', 'case_id': case, 'context_source': 'full', 'max_tokens': 8192}}))
    add('a.json', 'E01', 'complete_requires_review', 60, {'status': 'answered', 'claims': [1, 2]})
    add('b.json', 'E02', 'failed', 300.1, None, 'timed out')
    result = summarise('m', ['E01', 'E02', 'E03'], tmp_path)
    assert result['status_counts'] == {'complete_requires_review': 1, 'failed': 1, 'not_attempted': 1}
    assert result['answer_status_counts'] == {'answered': 1} and result['median_seconds_complete'] == 60
    assert result['rows'][0]['claims'] == 2
