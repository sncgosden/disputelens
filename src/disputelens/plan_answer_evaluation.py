"""Create a frozen-input development answer plan offline; no model execution."""
import hashlib
import json
import sys
from pathlib import Path

from .build_index import digest
from .client import ModelError
from .embed_batch import safe_error, write_json
from .grounded_answer import SYSTEM, build_answer_prompt


def planned_jobs(case_id, pack_path, pack, model_ids):
    prompt = build_answer_prompt(pack['question'], pack)
    prompt_sha = hashlib.sha256((SYSTEM + '\n' + prompt).encode()).hexdigest()
    return [{'case_id': case_id, 'model': model,
             'provider': 'local' if model.startswith('qwen') else 'claude',
             'context_source': 'full', 'context_pack_path': str(pack_path),
             'context_pack_sha256': digest(pack_path), 'prompt_sha256': prompt_sha,
             'max_tokens': 8192, 'semantic_review': 'pending'} for model in model_ids]


def compatible_attempts(job, paths):
    matches = []
    for path in paths:
        record = json.loads(path.read_text())
        identity = record.get('identity', {})
        if all(identity.get(k) == job[k] for k in
               ('case_id', 'model', 'context_pack_sha256', 'prompt_sha256', 'max_tokens')):
            matches.append({'path': str(path), 'original_status': record['status'],
                            'validator_matches_current': identity.get('answer_code_sha256')
                                == digest(Path(__file__).with_name('grounded_answer.py')),
                            'generation_seconds': record.get('generation_seconds')})
    return matches


def main():
    try:
        config = json.loads(Path('data/pipeline-config.json').read_text())
        case_path = Path(config['dev_cases_path'])
        cases = json.loads(case_path.read_text())
        if (len(cases) != 45 or len({c['case_id'] for c in cases}) != 45
                or any(c['split'] != 'dev' for c in cases)):
            raise ModelError('Expected 45 unique development cases only.')
        model_ids = config['generation_models']
        if len(model_ids) != 3 or len(set(model_ids)) != 3:
            raise ModelError('Expected three distinct comparison models.')
        summary_path = Path(json.loads(Path('data/indexes/context-eval/latest.json').read_text())['summary_path'])
        summary = json.loads(summary_path.read_text())
        package = Path(__file__).parent
        if (summary['status'] != 'complete' or summary['case_count'] != 45
                or summary['identity']['dev_cases_sha256'] != digest(case_path)
                or summary['identity']['builder_code_sha256'] != digest(package / 'context_pack.py')):
            raise ModelError('Reference context evaluation incomplete or stale.')
        jobs = []
        for case in cases:
            pack_path = summary_path.parent / 'packs' / (case['case_id'] + '.json')
            pack = json.loads(pack_path.read_text())
            if (pack['evaluation_identity'] != summary['identity'] or pack['question'] != case['question']
                    or pack['trusted_settings'] != case['filters']):
                raise ModelError('Reference pack identity, question or settings mismatch.')
            jobs.extend(planned_jobs(case['case_id'], pack_path, pack, model_ids))
        attempts = list(Path('data/indexes/answer-trials').glob('*.json'))
        for job in jobs:
            job['matching_historical_attempts'] = compatible_attempts(job, attempts)
        identity = {'experiment': 'full-context-three-model-dev-plan-v1',
                    'dev_cases_sha256': digest(case_path), 'model_ids': model_ids,
                    'context_summary_sha256': digest(summary_path),
                    'answer_code_sha256': digest(package / 'grounded_answer.py'),
                    'planner_code_sha256': digest(__file__),
                    'source_manifest_sha256': digest(config['manifest_path']),
                    'embedding_units_sha256': digest(config['embedding_units_path']),
                    'max_output_tokens_per_request': 8192}
        run_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
        directory = Path('data/indexes/answer-eval-plan') / run_id
        plan = {'status': 'planned_not_executed', 'identity': identity, 'case_count': 45,
                'planned_requests': len(jobs), 'paid_requests_before_reuse': 45,
                'paid_output_token_ceiling_before_reuse': 45 * 8192,
                'jobs': jobs,
                'execution_prerequisites': ['Explicit spending/call controls and checked pricing in step 79.',
                    'Local model-specific prompt token/context checks before each request.',
                    'Exact input matching, validator rechecks and explicit failure handling before reusing historical attempts.'],
                'limitations': ['Model settings differ: local temperature 0.2/default reasoning; Claude provider defaults.',
                    'Output-token ceiling is not a cost estimate or input-token budget.',
                    'No overall answer-quality result; independent human scoring remains pending.',
                    'Known incomplete E17/E18 reference evidence stays in the evaluation denominator.',
                    'Do not run all three full batches until pilot completion/latency gates are specified.']}
        write_json(directory / 'plan.json', plan)
        write_json(Path('data/indexes/answer-eval-plan/latest.json'), {'plan_path': str(directory / 'plan.json')})
        print('PLAN: 45 development questions; identical reference evidence across three models.')
        for model in model_ids:
            selected = [j for j in jobs if j['model'] == model]
            matched = sum(bool(j['matching_historical_attempts']) for j in selected)
            print(f'{model}: 45 planned outputs; {matched} questions have input-matching historical attempts (not automatically reused).')
        print(f'CALL CEILING BEFORE REUSE: {len(jobs)} total; 45 paid Claude requests.')
        print('CLAUDE OUTPUT CEILING: 368640 tokens; input tokens and prices not yet budgeted.')
        print('EXECUTION BLOCKED BY DESIGN: finish step 79 and local completion gates first.')
        print(f'SAVED PLAN: {directory / "plan.json"}')
        print('No model loading, embeddings, API requests, holdout or GitHub sync.')
        return 0
    except Exception as error:
        print('STOP: ' + safe_error(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
