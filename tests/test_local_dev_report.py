import json

from disputelens.local_dev_report import claude_failures, summarise


def row(status, seconds, answer=None, error=None):
    r = {'status': status, 'generation_seconds': seconds}
    if answer:
        r['answer'] = {'status': answer}
    if error:
        r['error'] = error
    return r


def test_summary_counts_and_overlap():
    rows = {'E01': row('complete_requires_review', 60, 'answered'), 'E02': row('failed', 300.1, error='timed out'),
            'E03': row('complete_requires_review', 120, 'partial'), 'E04': row('started', 0)}
    s = summarise(rows, {'E02', 'E09'})
    assert (s['attempted'], s['citation_valid'], s['failed_or_interrupted']) == (4, 2, 2)
    assert s['answer_status_counts'] == {'answered': 1, 'partial': 1}
    assert s['also_failed_for_claude'] == ['E02'] and s['failed_cases'] == ['E02', 'E04']
    assert s['seconds']['max'] == 300.1


def test_empty_run_does_not_crash():
    assert summarise({})['seconds'] is None


def test_claude_failures_come_from_final_summary_only(tmp_path):
    path = tmp_path / 's.json'
    path.write_text(json.dumps({'cases': [{'case_id': 'E01', 'status': 'citation_valid_requires_review'},
                                          {'case_id': 'E06', 'status': 'generation_or_validation_failed'}]}))
    assert claude_failures(path) == {'E06'}
