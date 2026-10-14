import json

from disputelens.local_dev_batch import dev_case_ids, pending, saved_attempts


def write(directory, name, model, case, status, source='full', tokens=8192):
    (directory / name).write_text(json.dumps({'status': status, 'identity': {
        'model': model, 'case_id': case, 'context_source': source, 'max_tokens': tokens}}))


def test_only_dev_cases_are_selected():
    cases = [{'case_id': 'E01', 'split': 'dev'}, {'case_id': 'E02', 'split': 'holdout'}]
    assert dev_case_ids(cases) == ['E01']


def test_saved_attempts_reused_only_for_same_model_and_settings(tmp_path):
    write(tmp_path, 'a.json', 'qwen3.5-4b', 'E01', 'complete_requires_review')
    write(tmp_path, 'b.json', 'qwen3.5-4b', 'E02', 'failed')
    write(tmp_path, 'c.json', 'qwen3.5-9b-mlx', 'E03', 'complete_requires_review')
    write(tmp_path, 'd.json', 'qwen3.5-4b', 'E04', 'complete_requires_review', source='focused')
    write(tmp_path, 'e.json', 'qwen3.5-4b', 'E05', 'complete_requires_review', tokens=1024)
    (tmp_path / 'x-check.json').write_text(json.dumps({'status': 'context_checked', 'identity': {'model': 'qwen3.5-4b', 'case_id': 'E06'}}))
    attempts = saved_attempts('qwen3.5-4b', tmp_path)
    assert attempts == {'E01': 'complete_requires_review', 'E02': 'failed'}
    assert pending(['E01', 'E02', 'E03', 'E04'], attempts) == ['E03', 'E04']
