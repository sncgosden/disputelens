"""Blinded model-assisted second review of saved development answers.

Two commands:
  prepare  Offline only. Builds blinded review inputs and a protocol file.
  run      Executes the prepared local-model review. Refuses to start without
           --execute, an exact --model and a --max-calls that fits the protocol.

Blinding: inputs hold only the question, trusted filters, the frozen context
text and the original saved answer. Previous ratings, assisted dispositions,
gold and diagnostic supplementation are never included. The 15-case holdout is
not touched: only the development bundle is read.
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import httpx

from disputelens.client import ModelError, Models, configured_models

BUNDLE = 'data/indexes/answer-eval-plan/c36f49c3b45e0291a3d40299/independent-review-bundle.json'
OUT_ROOT = Path('data/indexes/second-review')
SELECTED = ['E13', 'E18', 'E22', 'E23', 'E10', 'E30', 'E46']
DIMENSIONS = ['correctness', 'applicability', 'citation_support', 'question_completeness', 'relevance']
PROTOCOL = {
    'label': 'model-assisted second review (not independent human validation)',
    'cases': SELECTED,
    'provider': 'local',
    'max_calls': len(SELECTED),
    'timeout_seconds': 300,
    'max_output_tokens': 1500,
    'retries': 0,
    'stop_on_first_failure': True,
    'cost_usd': 0,
    'external_transfer': False,
    'gold_in_prompt': False,
    'previous_ratings_in_prompt': False,
    'scoring': {'2': 'meets', '1': 'minor issue', '0': 'material issue'},
    'limits': [
        'Reviewer model is not independent of generator-family biases and is far smaller than the generator.',
        'Gold completeness is scored in a separate later step, not here.',
        'A timeout or invalid output is recorded as a failed review, never retried or scored.',
    ],
}
SYSTEM = (
    'You are a strict reviewer of a merchant-dispute answer. Use ONLY the supplied frozen evidence, '
    'never outside knowledge. Score each dimension 2 (meets), 1 (minor issue) or 0 (material issue): '
    'correctness (claims match the evidence), applicability (the cited rule applies to the question\'s '
    'scheme, region, product and scope, with no superseded or specialised-scope rule presented as general), '
    'citation_support (each quote actually supports its claim), question_completeness (the answer covers '
    'what the question needs that the evidence contains) and relevance (no unasked material). '
    'Every score below 2 needs a concrete issue citing a source ID such as S012. State uncertainty '
    'explicitly. Reply with one JSON object only: {"scores": {"correctness": n, "applicability": n, '
    '"citation_support": n, "question_completeness": n, "relevance": n}, "issues": [{"dimension": str, '
    '"source_ids": [str], "description": str}], "uncertainty": str}.'
)


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def render_answer(answer):
    lines = [f"status: {answer.get('status')}"]
    for number, claim in enumerate(answer.get('claims', []), 1):
        lines.append(f"Claim {number}: {claim['text']}")
        for cite in claim.get('citations', []):
            lines.append(f"  cites {cite['id']}: \"{cite['quote']}\"")
    for item in answer.get('missing_information', []):
        lines.append(f'Missing information: {item}')
    return '\n'.join(lines)


def build_inputs(bundle):
    by_id = {case['case_id']: case for case in bundle['cases']}
    missing = [c for c in SELECTED if c not in by_id]
    if missing:
        raise ModelError(f'Selected cases missing from bundle: {missing}')
    inputs = []
    for case_id in SELECTED:
        case = by_id[case_id]
        if case['saved_status'] != 'citation_valid_requires_review':
            raise ModelError(f'{case_id} is not a citation-valid answer; record it as failure/N/A instead.')
        pack = case['frozen_context_pack']
        user = '\n\n'.join([
            f"QUESTION:\n{case['question']}",
            f"TRUSTED FILTERS: {json.dumps(case['trusted_filters'], sort_keys=True)}",
            f"FROZEN EVIDENCE:\n{pack['text']}",
            f"SAVED ANSWER TO REVIEW:\n{render_answer(case['answer'])}",
        ])
        inputs.append({'case_id': case_id, 'system': SYSTEM, 'user': user,
                       'input_sha256': sha(SYSTEM + '\n' + user), 'attempt_sha256': case['attempt_sha256'],
                       'context_pack_sha256': case['context_pack_sha256'], 'words': len(user.split())})
    return inputs


def prepare():
    bundle_text = Path(BUNDLE).read_text()
    inputs = build_inputs(json.loads(bundle_text))
    protocol = dict(PROTOCOL, bundle_sha256=sha(bundle_text), input_hashes={i['case_id']: i['input_sha256'] for i in inputs})
    protocol_text = json.dumps(protocol, indent=2, sort_keys=True)
    out = OUT_ROOT / sha(protocol_text)[:24]
    out.mkdir(parents=True, exist_ok=True)
    (out / 'protocol.json').write_text(protocol_text)
    (out / 'inputs.json').write_text(json.dumps(inputs, indent=2))
    print(f'Prepared {len(inputs)} blinded inputs in {out}; no model call made.')
    for item in inputs:
        print(f"  {item['case_id']}: {item['words']} words")
    return out


def parse_review(text):
    start, end = text.find('{'), text.rfind('}')
    try:
        data = json.loads(text[start:end + 1])
        scores = data['scores']
        assert set(scores) == set(DIMENSIONS) and all(v in (0, 1, 2) for v in scores.values())
        assert isinstance(data.get('issues', []), list) and isinstance(data.get('uncertainty', ''), str)
        for issue in data.get('issues', []):
            assert issue['source_ids'] and issue['description']
        return data
    except (ValueError, KeyError, AssertionError, TypeError):
        raise ModelError('Reviewer output was not valid review JSON; recorded as failed, not scored.') from None


def run(directory, model, max_calls):
    out = Path(directory)
    protocol = json.loads((out / 'protocol.json').read_text())
    inputs = json.loads((out / 'inputs.json').read_text())
    if max_calls > protocol['max_calls']:
        sys.exit(f"--max-calls {max_calls} exceeds protocol allowance {protocol['max_calls']}.")
    for item in inputs:
        if sha(item['system'] + '\n' + item['user']) != protocol['input_hashes'][item['case_id']]:
            sys.exit(f"Input hash mismatch for {item['case_id']}; re-run prepare.")
    models = configured_models()
    models.http = httpx.Client(timeout=httpx.Timeout(protocol['timeout_seconds'], connect=5))
    results = []
    try:
        for item in inputs[:max_calls]:
            started = time.time()
            record = {'case_id': item['case_id'], 'model': model, 'input_sha256': item['input_sha256']}
            try:
                reply = models.chat(item['user'], model=model, system=item['system'], provider='local',
                                    max_tokens=protocol['max_output_tokens'])
                record.update(raw=reply.text, review=parse_review(reply.text), status='reviewed', usage=reply.usage)
            except ModelError as error:
                record.update(status='failed', error=str(error))
            record['seconds'] = round(time.time() - started, 1)
            results.append(record)
            (out / 'results.json').write_text(json.dumps({'protocol_label': protocol['label'], 'results': results}, indent=2))
            print(f"{item['case_id']}: {record['status']} in {record['seconds']}s")
            if record['status'] == 'failed' and protocol['stop_on_first_failure']:
                print('Stopped on first failure; no retry.')
                break
    finally:
        models.close()


ASSISTED = 'data/indexes/answer-eval-plan/c36f49c3b45e0291a3d40299/second-assisted-priority-review.json'


def overall(scores):
    return 'material_issue' if 0 in scores.values() else 'minor_issue' if 1 in scores.values() else 'meets'


def compare(directory):
    """Unblind only after the run: join reviewer output to the earlier assisted dispositions."""
    out = Path(directory)
    results = json.loads((out / 'results.json').read_text())['results']
    assisted = {c['case_id']: c['disposition'] for c in json.loads(Path(ASSISTED).read_text())['cases']}
    done = {r['case_id']: r for r in results}
    rows = []
    for case_id in SELECTED:
        record = done.get(case_id)
        if record is None:
            rows.append({'case_id': case_id, 'reviewer_status': 'not_run', 'assisted': assisted.get(case_id)})
        elif record['status'] != 'reviewed':
            rows.append({'case_id': case_id, 'reviewer_status': 'failed', 'error': record['error'], 'assisted': assisted.get(case_id)})
        else:
            scores = record['review']['scores']
            verdict = overall(scores)
            agree = (verdict == 'meets') == (assisted.get(case_id) == 'meets')
            rows.append({'case_id': case_id, 'reviewer_status': 'reviewed', 'scores': scores, 'reviewer_overall': verdict,
                         'assisted': assisted.get(case_id), 'agree_meets_vs_issue': agree,
                         'issues': record['review'].get('issues', []), 'uncertainty': record['review'].get('uncertainty')})
    summary = {'reviewed': sum(r['reviewer_status'] == 'reviewed' for r in rows),
               'failed_or_not_run': sum(r['reviewer_status'] != 'reviewed' for r in rows),
               'agreements': sum(r.get('agree_meets_vs_issue') is True for r in rows),
               'disagreements': [r['case_id'] for r in rows if r.get('agree_meets_vs_issue') is False]}
    report = {'label': 'model-assisted second review; small reviewer model, not independent human validation; 7 of 45 cases; no aggregate accuracy claim',
              'summary': summary, 'cases': rows}
    (out / 'comparison.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(summary, indent=2))
    for r in rows:
        print(r['case_id'], r['reviewer_status'], r.get('reviewer_overall', '-'), 'vs assisted:', r['assisted'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('prepare')
    sub.add_parser('compare').add_argument('directory')
    runner = sub.add_parser('run')
    runner.add_argument('directory')
    runner.add_argument('--model', required=True)
    runner.add_argument('--max-calls', type=int, required=True)
    runner.add_argument('--execute', action='store_true', required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare()
    elif args.command == 'compare':
        compare(args.directory)
    else:
        run(args.directory, args.model, args.max_calls)


if __name__ == '__main__':
    main()
