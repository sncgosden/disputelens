"""Claude-authored source-grounded evaluation drafts, with resumable paid calls."""
import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'eval/expanded'


def prepare():
    data = json.loads((ROOT / 'data/normalized-expanded/documents.json').read_text())
    docs = {d['parent_id']: d for d in data['documents']}
    seeds = []

    def add(sid, blocks, topic, behaviour='answerable'):
        d = docs[sid]
        i = len(seeds) + 1
        seeds.append({'case_id': f'E{i:02}', 'split': 'holdout' if i % 4 == 0 else 'dev',
            'filters': {k: d['metadata'].get(k) for k in ['corpus', 'provider', 'scheme']},
            'topic': topic, 'answerability': behaviour,
            'source_version': d['metadata']['version'], 'source_region': d['metadata'].get('region'),
            'evidence': [{'passage_id': b['passage_id'], 'headings': b['headings'],
                'text': b['text'], 'locator': b['locator']} for b in blocks]})

    visa = docs['visa-dispute-management-june-2024']['blocks']
    for page in [40, 26, 30, 31, 32, 33, 34, 35, 36, 37, 38, 43]:
        bs = [b for b in visa if b['locator']['pdf_page'] == page and len(b['text'].split()) > 15]
        body = [b for b in bs if 'provide' in b['text'].lower() or 'processed' in b['text'].lower()]
        add('visa-dispute-management-june-2024', (body or bs)[:2],
            'Exact reason code or its merchant-language paraphrase; preserve date/condition qualifications')
    mc = docs['mastercard-chargeback-guide']['blocks']
    targets = ['4837', '4853', 'Goods or Services Not Provided',
        'Goods or Services Were Either Not as Described', 'recurring',
        'Credit Not Processed', 'Duplicate Transaction', 'ATM', 'Digital Goods',
        'Refund properly documented', 'No Cardholder Authorization', 'Transaction Amount']
    selected_blocks = [(410, [5]), (127, [6, 7]), (713, [5, 7]), (134, [2, 3]),
        (261, [3, 4]), (229, [3, 4]), (704, [2, 4, 9]), (689, [11]),
        (131, [2, 3]), (85, [2, 3]), (418, [3, 4]), (606, [4])]
    for term, (page, paragraphs) in zip(targets, selected_blocks):
        ids = {f'mastercard-chargeback-guide:page-{page}:paragraph-{i}' for i in paragraphs}
        context = [b for b in mc if b['passage_id'] in ids]
        if len(context) != len(ids) or any('.....' in b['text'] for b in context):
            raise ValueError('Invalid substantive Mastercard selection')
        topic = 'Translation requirements and arbitration escalation' if page == 131 else term
        add('mastercard-chargeback-guide', context, 'Mastercard ' + topic + '; preserve actor, system and regional scope')
    selections = {
        'adyen-dispute-flow': [(6,), (7,), (8,), (12,)],
        'adyen-visa-chargebacks': [(3, 4), (27, 28), (30, 49), (65, 66)],
        'square-uk-disputes': [(6,), (7,), (8,), (11,), (28,), (33,), (48,), (50,)],
        'paypal-uk-seller-protection': [(4, 5), (10,), (12,), (15,), (18,), (24, 28), (26, 27), (44, 45)],
        'stripe-respond-to-disputes': [(14, 15), (37, 38), (39,), (48, 49, 50), (51, 54), (23,)]}
    for sid, sets in selections.items():
        for numbers in sets:
            blocks = [b for b in docs[sid]['blocks'] if b['passage_id'] in
                {f'{sid}:block-{n}' for n in numbers}]
            if len(blocks) != len(numbers):
                raise ValueError('Missing selected evidence')
            add(sid, blocks, 'Provider-specific merchant workflow; do not generalise to other providers')
    old = json.loads((ROOT / 'eval/dev-cases.json').read_text())
    if isinstance(old, dict):
        old = old.get('cases', [])
    lookup = {b['passage_id']: b for d in docs.values() for b in d['blocks']}
    for original_id in ['E01', 'E02', 'E03', 'E08', 'E09']:
        original = next(c for c in old if c['case_id'] == original_id)
        blocks = [lookup[p] for p in original['relevant_passage_ids']]
        add(blocks[0]['parent_id'], blocks,
            'Controlled fixture scenario: ' + original['question'], original['answerability'])
    d = docs['subscription-policy']
    add('subscription-policy', d['blocks'],
        'Ask whether the fixture specifies a bank response deadline in days; it does not. Distinguish missing source policy from cancellation policy.',
        'not_in_sources')
    assert len(seeds) == 60 and sum(s['split'] == 'holdout' for s in seeds) == 15
    OUT.mkdir(parents=True, exist_ok=True)
    record = {'normalized_sha256': hashlib.sha256((ROOT / 'data/normalized-expanded/documents.json').read_bytes()).hexdigest(),
              'seed_provenance': 'Codex selected evidence and coverage before Claude drafted questions.', 'seeds': seeds}
    (OUT / 'draft-seeds.json').write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n')
    print('Prepared 60 evidence seeds; 45 development and 15 holdout assigned before drafting.')


def draft():
    load_dotenv(ROOT / '.env')
    model = os.getenv('CLAUDE_MODEL')
    if model != 'claude-sonnet-5-5' or not os.getenv('ANTHROPIC_API_KEY'):
        raise SystemExit('Requires configured Claude Sonnet 5.5 and private API key.')
    seeds = json.loads((OUT / 'draft-seeds.json').read_text())['seeds']
    rawdir = OUT / 'raw'
    rawdir.mkdir(parents=True, exist_ok=True)
    schema = json.loads((ROOT / 'eval/case.schema.json').read_text())
    system = ('Create realistic small-merchant RAG evaluation questions. Return ONLY a JSON array. '
        'One case per seed in order, matching IDs/splits/filters/answerability exactly. '
        'Use only seed evidence for gold claims. Claims must preserve conditions, dates, regions, '
        'and actor distinctions (merchant/acquirer/issuer); do not turn issuer rules into merchant deadlines. '
        'No invented rules, guaranteed wins, or inference from another provider. '
        'Questions should describe a merchant problem, sometimes paraphrased and sometimes including exact codes, '
        'without supplying the answer. Use 1-3 concise expected_claims with supporting_passage_ids. '
        'Relevant IDs must be seed evidence IDs. For missing-source questions claim only that the supplied '
        'scope does not specify the requested fact. review_status must be draft. '
        'The last six cases are expressly fictional and the question must say so. '
        'Follow this JSON schema for every case: ' + json.dumps(schema))
    discarded = []
    for old in sorted((rawdir / 'discarded').glob('*.json')):
        r = json.loads(old.read_text())
        u = r['usage']
        discarded.append({'file': str(old.relative_to(OUT)), 'usage': u,
            'cost_usd': u['input_tokens'] * 2 / 1_000_000 + u['output_tokens'] * 10 / 1_000_000,
            'reason': 'Replaced after substantive-source review of Mastercard seeds'})
    cases, ledger = [], []
    for batch in range(6):
        selected = seeds[batch * 10:(batch + 1) * 10]
        prompt = json.dumps(selected, ensure_ascii=False)
        path = rawdir / f'claude-batch-{batch + 1}.json'
        if path.exists():
            response = json.loads(path.read_text())
        else:
            # Conservative byte-based input allowance and bounded output/call count.
            # Eight total paid requests including two deliberately discarded
            # source-correction batches. No automatic transport/JSON retries.
            if len(list(rawdir.glob('claude-batch-*.json'))) + len(discarded) >= 8:
                raise SystemExit('Eight-request total allowance exhausted.')
            if len((system + prompt).encode()) > 50000:
                raise SystemExit('Input allowance exceeded; shorten evidence before paying.')
            print(f'Claude draft batch {batch + 1}/6: ten cases. Waiting...', flush=True)
            started = time.perf_counter()
            with httpx.Client(timeout=httpx.Timeout(240, connect=10)) as client:
                r = client.post('https://api.anthropic.com/v1/messages',
                    headers={'x-api-key': os.environ['ANTHROPIC_API_KEY'], 'anthropic-version': '2023-06-01'},
                    json={'model': model, 'max_tokens': 12000, 'system': system,
                          'messages': [{'role': 'user', 'content': prompt}]})
                if r.status_code != 200:
                    raise SystemExit(f'Claude returned HTTP {r.status_code}; no automatic retry.')
                response = r.json()
            response['local_elapsed_seconds'] = round(time.perf_counter() - started, 2)
            path.write_text(json.dumps(response, indent=2, ensure_ascii=False) + '\n')
        usage = response['usage']
        cost = usage['input_tokens'] * 2 / 1_000_000 + usage['output_tokens'] * 10 / 1_000_000
        ledger.append({'batch': batch + 1, 'model': response['model'], 'usage': usage,
                       'cost_usd': cost, 'seconds': response.get('local_elapsed_seconds'),
                       'stop_reason': response['stop_reason']})
        (OUT / 'claude-drafting-usage.json').write_text(json.dumps({'pricing_source':
            'https://platform.claude.com/docs/en/about-claude/pricing',
            'pricing_checked_on': '2026-10-06', 'input_usd_per_million': 2,
            'output_usd_per_million': 10, 'max_requests': 8, 'max_output_tokens_per_request': 12000,
            'conservative_request_allowance_usd': 2.00, 'automatic_retries': 0,
            'discarded_runs': discarded, 'runs': ledger,
            'total_cost_usd': sum(x['cost_usd'] for x in ledger + discarded)}, indent=2) + '\n')
        if response['stop_reason'] != 'end_turn':
            raise SystemExit('Draft was incomplete; saved raw response and paid usage, no retry.')
        content = ''.join(b['text'] for b in response['content'] if b['type'] == 'text')
        content = re.sub(r'^```(?:json)?\s*|\s*```$', '', content.strip())
        drafted = json.loads(content)
        if len(drafted) != 10:
            raise ValueError('Expected exactly ten cases')
        for case, seed in zip(drafted, selected):
            for field in ['case_id', 'split', 'filters', 'answerability']:
                if case[field] != seed[field]:
                    raise ValueError('Draft changed seed field: ' + field)
            permitted = {b['passage_id'] for b in seed['evidence']}
            cited = set(case['relevant_passage_ids']) | {p for c in case['expected_claims'] for p in c['supporting_passage_ids']}
            if not cited <= permitted or not case['question'].strip() or case['review_status'] != 'draft':
                raise ValueError('Draft contains unsupported IDs or invalid status')
        cases.extend(drafted)
        print(f'Validated IDs in batch {batch + 1}. Paid usage ${cost:.4f}.', flush=True)
    (OUT / 'claude-drafts.json').write_text(json.dumps(cases, indent=2, ensure_ascii=False) + '\n')
    print(f'SAVED 60 Claude drafts. Total API spend ${sum(x["cost_usd"] for x in ledger + discarded):.4f}. Source review still required.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'draft'])
    args = parser.parse_args()
    (prepare if args.action == 'prepare' else draft)()


if __name__ == '__main__':
    main()
