import json

from disputelens.plan_answer_evaluation import planned_jobs


def test_models_receive_same_input_and_gold_never_enters_prompt(tmp_path):
    p = tmp_path / 'pack.json'
    pack = {'question': 'What triggered this dispute?', 'trusted_settings': {'scheme': 'Visa'},
            'text': '[S001] A transaction was processed after a Decline.',
            'citations': {'S001': {}}, 'expected_answer': 'SECRET GOLD'}
    p.write_text(json.dumps(pack))
    first = planned_jobs('E03', p, pack, ['qwen3.5-4b', 'qwen3.5-9b-mlx', 'claude-sonnet-5-5'])
    pack['expected_answer'] = 'DIFFERENT GOLD'
    second = planned_jobs('E03', p, pack, ['qwen3.5-4b', 'qwen3.5-9b-mlx', 'claude-sonnet-5-5'])
    assert len({j['prompt_sha256'] for j in first}) == 1
    assert first[0]['prompt_sha256'] == second[0]['prompt_sha256']
    assert [j['provider'] for j in first] == ['local', 'local', 'claude']
