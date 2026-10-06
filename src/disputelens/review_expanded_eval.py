"""Persist Codex's explicit source-review corrections and expansion receipts."""
import hashlib
import json
from collections import Counter
from pathlib import Path

from .applicability import applicable

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'eval/expanded'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    cases = json.loads((OUT / 'claude-drafts.json').read_text())
    by_id = {c['case_id']: c for c in cases}
    documents = json.loads((ROOT / 'data/normalized-expanded/documents.json').read_text())
    passages = {b['passage_id']: (b, d['metadata']) for d in documents['documents'] for b in d['blocks']}
    edits = []

    def claim(case_id, text, ids):
        c = by_id[case_id]
        c['expected_claims'].append({'claim_id': case_id + '-R' + str(len(c['expected_claims']) + 1),
                                      'text': text, 'supporting_passage_ids': ids})
        c['relevant_passage_ids'] = list(dict.fromkeys(c['relevant_passage_ids'] + ids))

    by_id['E02']['question'] = ('A Visa Condition 10.4 dispute was processed on 1 November 2024 on an online sale. '
        'If it used Visa Secure, or we have earlier undisputed purchases from the same customer, '
        'what does this guide say to tell the processor and which details should we provide?')
    claim('E02', 'For disputes processed on or after 19 October 2024, provide the date merchandise/services were provided, '
        'the detailed description for the disputed and two previous transactions, and the matching device ID, '
        'device fingerprint or IP address plus an additional listed element (account/login ID, full delivery address, '
        'device ID, device fingerprint or IP address). Do not treat prior purchases alone as sufficient.',
        ['visa-dispute-management-june-2024:page-26:paragraph-4', 'visa-dispute-management-june-2024:page-26:paragraph-5'])
    edits.append({'case_id': 'E02', 'reason': 'Restore the adjacent continuation with matching-data and effective-date qualifications.'})
    by_id['E04']['question'] = 'For a transaction completed on 14 April 2024, my notice cites Visa 11.3, No Authorization/Late Presentment. What does that mean, and does this guide cover that transaction date?'
    claim('E04', 'This edition labels Condition 11.3 No Authorization/Late Presentment effective for transactions completed on or after 13 April 2024.',
          ['visa-dispute-management-june-2024:page-31:paragraph-1'])
    by_id['E05']['question'] = 'A Visa transaction completed on 10 April 2024 is disputed under Condition 12.1 Late Presentment. Does the edition cover that date, and how should I respond if it was processed on time, late, or already credited?'
    claim('E05', 'This edition labels Condition 12.1 Late Presentment effective through 12 April 2024; it must not be applied as the same rule to later transactions.',
          ['visa-dispute-management-june-2024:page-32:paragraph-1'])
    edits.extend([{'case_id': x, 'reason': 'Make the transaction date explicit and restore the heading effective date.'} for x in ['E04', 'E05']])
    by_id['E18']['question'] = by_id['E18']['question'].replace('Credit Not Processed', 'Refund Not Processed')
    edits.append({'case_id': 'E18', 'reason': 'Use Mastercard section terminology rather than the Visa category label.'})
    by_id['E21']['expected_claims'] = by_id['E21']['expected_claims'][1:]
    by_id['E21']['forbidden_claims'].append('English translations are always required in the earlier stages even when issuer and acquirer share a language.')
    edits.append({'case_id': 'E21', 'reason': 'Remove an unqualified general translation claim; retain the common-language exception and arbitration qualifications.'})
    by_id['E30']['question'] = ('I use Adyen. How long do I have to upload Visa Allocation defense documents for locally '
        'processed US payments with disputes opened on 2 June 2025 and 5 August 2025, '
        'and a Germany-processed payment with a dispute opened on 5 August 2025? Can I add documents later?')
    by_id['E30']['expected_claims'][1]['text'] = ('From 21 July 2025, the response timeframe is 9 days for disputes opened on payments processed locally '
        'in the US and Canada. Earlier US/Canada disputes and other countries/regions use 18 days. '
        'Thus the June US dispute uses 18 days, the August US dispute 9 days, and the August Germany dispute 18 days.')
    edits.append({'case_id': 'E30', 'reason': 'Exercise both sides of the natural regional/date exception, not just two 18-day examples.'})
    by_id['E33']['question'] = ('I use Square in the UK. Someone sent me an Adyen article mentioning a chargeback processing fee. '
        'What does Square say it charges me for handling a chargeback dispute?')
    by_id['E33']['forbidden_claims'].append('Adyen chargeback-processing fees apply to this Square UK merchant.')
    edits.append({'case_id': 'E33', 'reason': 'Introduce a real cross-provider distractor without changing trusted Square applicability.'})
    by_id['E41']['expected_claims'][0]['text'] = ('PayPal UK lists Unauthorised Transaction claims as a claim type to which protection may apply, '
        'when the buyer did not authorise or benefit from funds sent from their PayPal account and the transaction '
        'occurs in a PayPal-hosted environment. This is conditional on the program requirements and is not guaranteed eligibility.')
    claim('E41', 'PayPal determines eligibility under its program requirements and available information; being a listed claim type is not a guarantee of protection.',
          ['paypal-uk-seller-protection:block-2'])
    edits.append({'case_id': 'E41', 'reason': 'Restore conditional eligibility instead of implying a listed claim is automatically protected.'})
    by_id['E46']['expected_claims'][0]['text'] = ('For Item Not Received claims, the seller must provide proof of delivery. The physical-goods table '
        'requires shipping-company documentation with an online verifiable tracking number, delivery date and delivered status, '
        'and recipient-address information meeting its Transaction Details matching and stated address-detail requirements. '
        'Do not infer that a different delivery address is acceptable from minimum address granularity.')
    by_id['E46']['forbidden_claims'].append('Any address in the same city is sufficient even when it differs from the transaction shipping address.')
    edits.append({'case_id': 'E46', 'reason': 'Remove an invented OR between separate address requirements in the source table.'})
    claim('E47', 'Intangible-goods sales must also meet the program basic requirements as well as the additional intangible-goods requirements; these two listed conditions alone do not guarantee coverage.',
          ['paypal-uk-seller-protection:block-25'])
    edits.append({'case_id': 'E47', 'reason': 'Restore parent-section prerequisite; eligibility and digital delivery are not sufficient by themselves.'})
    by_id['E48']['question'] = ('I use PayPal in the UK. The item arrived, but the buyer told their card issuer it was not '
        'what they ordered. Is this Significantly Not as Described claim covered by Seller Protection?')
    by_id['E48']['expected_claims'] = by_id['E48']['expected_claims'][:1]
    by_id['E48']['relevant_passage_ids'] = ['paypal-uk-seller-protection:block-44']
    edits.append({'case_id': 'E48', 'reason': 'Remove the Item Not Received subquestion that duplicated a development gold fact; retain distinct held-out SNAD coverage.'})
    claim('E58', 'State the pending status and request clarification from the provider rather than inventing a settlement duration.',
          ['refund-policy:section-4'])
    edits.append({'case_id': 'E58', 'reason': 'Add the supported action expected for this clarification case.'})
    by_id['E60']['question'] = ('This is a fictional DisputeLens test scenario. How many pounds will my bank charge '
        'me to appeal a recurring-payment chargeback under these test-provider policies?')
    by_id['E60']['expected_claims'] = [{'claim_id': 'E60-C1',
        'text': 'The permitted fictional policies do not specify a bank appeal fee in pounds. State that the amount is unavailable and ask the bank/provider rather than estimating it.',
        'supporting_passage_ids': []}]
    by_id['E60']['relevant_passage_ids'] = []
    edits.append({'case_id': 'E60', 'reason': 'Test a fee absent from the whole applicable fixture corpus, rather than a deadline available in another fixture. No positive passage is gold for absent evidence; exclude from recall/NDCG denominators.'})
    for c in cases:
        c['review_status'] = 'approved'
        if c['filters']['provider'] in ('Square', 'PayPal'):
            c['filters']['region'] = 'UK'
        else:
            c['filters']['region'] = None
        if c['case_id'] in ('E02', 'E03', 'E04', 'E05', 'E06', 'E07', 'E08', 'E09', 'E10', 'E11', 'E12'):
            c['filters']['scheme'] = 'Visa'
        if c['case_id'] == 'E52':
            c['filters']['scheme'] = 'Mastercard'
        if c['case_id'] == 'E54':
            c['filters']['scheme'] = 'Visa'
        c['notes'] = (c.get('notes', '') + ' Source facts reviewed by Codex on 2026-10-06 under delegated PM judgement. '
            'Synthetic merchant scenario; source corpus determines whether policy is real or a fixture. '
            'Not independently human-labelled.').strip()
        refs = set(c['relevant_passage_ids']) | {p for g in c['expected_claims'] for p in g['supporting_passage_ids']}
        assert (refs or c['answerability'] == 'not_in_sources') and all(p in passages for p in refs), c['case_id']
        for p in refs:
            b, metadata = passages[p]
            assert applicable(metadata, **{k: c['filters'][k] for k in ('corpus', 'provider', 'scheme', 'region')}), (c['case_id'], p)
            assert b['text'].strip()
        assert len({g['claim_id'] for g in c['expected_claims']}) == len(c['expected_claims'])
    assert len(cases) == 60 and len({c['case_id'] for c in cases}) == 60
    for split in ('dev', 'holdout'):
        selected = [c for c in cases if c['split'] == split]
        (OUT / (split + '-cases.json')).write_text(json.dumps(selected, indent=2, ensure_ascii=False) + '\n')
    assert Counter(c['split'] for c in cases) == {'dev': 45, 'holdout': 15}
    review = {'reviewed_on': '2026-10-06', 'reviewer': 'Codex under user-delegated PM judgement',
        'draft_author': 'Claude Sonnet 5.5 API', 'independent_human_labelling': False,
        'sebastian_independent_review': 'Optional additional review, not recorded as completed',
        'method': 'All 60 questions and gold claims inspected against the selected original extracted passages. '
                  'Visa page 31 and Mastercard pages 85/689 sampled visually. Corrections preserve original drafts.',
        'reviewed_case_ids': [c['case_id'] for c in cases], 'corrections': edits,
        'split_rule': 'Every fourth case assigned to holdout before drafting; no retrieval/generation tuning has run.',
        'dev_sha256': digest(OUT / 'dev-cases.json'), 'holdout_sha256': digest(OUT / 'holdout-cases.json'),
        'normalized_sha256': digest(ROOT / 'data/normalized-expanded/documents.json'),
        'model_answer_runs': 0, 'retrieval_experiments': 0,
        'scope': '60 synthetic merchant questions: 54 use real policy, 6 use controlled fixtures. Source-referenced gold reviewed by the coding assistant, not an independent merchant sample.'}
    (OUT / 'source-review.json').write_text(json.dumps(review, indent=2) + '\n')
    usage = json.loads((OUT / 'claude-drafting-usage.json').read_text())
    parsed = json.loads((ROOT / 'data/parsed-expanded/report.json').read_text())
    assert all(x['status'] == 'parsed' for x in parsed)
    layouts = {}
    for size in (400, 250):
        file = ROOT / f'data/chunks-expanded/chunks-{size}-overlap-40.json'
        chunks = json.loads(file.read_text())['chunks']
        layouts[str(size)] = {'chunks': len(chunks), 'oversized_intact_blocks': sum(c['exceeds_target'] for c in chunks),
                             'sha256': digest(file)}
    receipt = {'completed_on': '2026-10-06', 'sources': len(documents['documents']),
        'real_sources': sum(d['metadata']['corpus'] == 'real' for d in documents['documents']),
        'fixture_sources': sum(d['metadata']['corpus'] == 'fixture' for d in documents['documents']),
        'pdf_pages': {x['source_id']: x['pages'] for x in parsed if x.get('pages')},
        'evidence_blocks': sum(len(d['blocks']) for d in documents['documents']),
        'layouts': layouts, 'questions': 60, 'development': 45, 'holdout': 15,
        'claude_cost_usd': usage['total_cost_usd'], 'paid_drafting_calls': len(usage['runs']) + len(usage['discarded_runs']),
        'git_sync': 'Not performed. Sebastian controls commits and pushes.',
        'next_gate': 'Token-capacity and oversized-block checks before embedding. No search-quality or model-answer results yet.'}
    (OUT / 'expansion-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('PASS: 60 source-reviewed cases; 45 dev / 15 holdout; all gold references applicable and resolvable.')
    print(f'RECEIPT: {receipt["sources"]} sources; {receipt["evidence_blocks"]} evidence blocks; ${usage["total_cost_usd"]:.4f} paid drafting.')


if __name__ == '__main__':
    main()
