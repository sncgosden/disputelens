"""Measure context evidence retention on saved scoped-hybrid development results."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

from .build_index import digest
from .client import ModelError
from .context_pack import build_context
from .embed_batch import safe_error, write_json
from .semantic_search import evidence_coverage


def coverage_score(coverage):
    if not coverage:
        return {'passage_recall': None, 'fractional_passage_recall': None,
                'all_expected_evidence': None}
    return {'passage_recall': sum(e['fully_retrieved'] for e in coverage) / len(coverage),
            'fractional_passage_recall': sum(e['covered_characters'] / e['total_characters']
                                           for e in coverage) / len(coverage),
            'all_expected_evidence': all(e['fully_retrieved'] for e in coverage)}


def retention_change(before, after):
    a, b = before['passage_recall'], after['passage_recall']
    if (a is None) != (b is None):
        raise ModelError('Context comparison changed the evidence denominator.')
    if a is None:
        return 'no_gold'
    if b > a + 1e-12:
        raise ModelError('Context claims evidence absent from the retrieved candidate pool.')
    return 'lost_evidence' if b < a - 1e-12 else 'unchanged'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-words', type=int, default=6000)
    args = parser.parse_args()
    try:
        config = json.loads(Path('data/pipeline-config.json').read_text())
        case_path = Path(config['dev_cases_path'])
        cases = json.loads(case_path.read_text())
        if len(cases) != 45 or any(c['split'] != 'dev' for c in cases):
            raise ModelError('Expected the fixed 45 development cases; holdout is not loaded.')
        pointer = json.loads(Path('data/indexes/section-scope/hybrid-latest.json').read_text())
        comparison_path = Path(pointer['comparison_path'])
        directory = comparison_path.parent
        comparison = json.loads(comparison_path.read_text())
        source_identity = comparison['identity']
        if (comparison['status'] != 'complete' or source_identity['strategy'] != 'hybrid'
                or source_identity['dev_cases_sha256'] != digest(case_path)
                or source_identity['embedding_units_sha256'] != digest(config['embedding_units_path'])
                or source_identity['code_sha256']['section_scope.py'] != digest(Path(__file__).with_name('section_scope.py'))):
            raise ModelError('Saved retrieval configuration differs from current inputs/guards.')
        scope_path = directory / 'passage-scope-map.json'
        scope_data = json.loads(scope_path.read_text())
        if scope_data['identity'] != source_identity:
            raise ModelError('Scope map does not match saved retrieval.')
        units = json.loads(Path(config['embedding_units_path']).read_text())['chunks']
        by_id = {u['chunk_id']: u for u in units}
        identity = {'max_words': args.max_words, 'dev_cases_sha256': digest(case_path),
                    'retrieval_comparison_sha256': digest(comparison_path),
                    'scope_map_sha256': digest(scope_path),
                    'builder_code_sha256': digest(Path(__file__).with_name('context_pack.py')),
                    'coverage_code_sha256': digest(Path(__file__).with_name('semantic_search.py')),
                    'evaluator_code_sha256': digest(__file__)}
        run_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
        output = Path('data/indexes/context-eval') / run_id
        records = []
        for n, case in enumerate(cases, 1):
            saved_path = directory / 'cases' / (case['case_id'] + '.json')
            saved = json.loads(saved_path.read_text())
            if (saved['identity'] != source_identity or saved['question'] != case['question']
                    or saved['filters'] != case['filters']
                    or any(by_id.get(r['unit']['chunk_id']) != r['unit'] for r in saved['results'])):
                raise ModelError('Saved candidate identity, scope or payload mismatch.')
            # No expected evidence reaches the context builder.
            pack = build_context(saved['results'], saved['filters'], scope_data['passages'], args.max_words)
            context_results = [{'rank': rank, 'unit': {
                'passage_ids': [e['passage_id'] for e in group['evidence']],
                'evidence': group['evidence']}}
                for rank, group in enumerate(pack['groups'], 1)]
            before_coverage = evidence_coverage(saved['results'], case['relevant_passage_ids'], units)
            after_coverage = evidence_coverage(context_results, case['relevant_passage_ids'], units)
            before, after = coverage_score(before_coverage), coverage_score(after_coverage)
            change = retention_change(before, after)
            pack['question'] = saved['question']
            pack['evaluation_identity'] = identity
            write_json(output / 'packs' / (case['case_id'] + '.json'), pack)
            record = {'case_id': case['case_id'], 'question': case['question'], 'filters': case['filters'],
                      'retrieved': before, 'context': after, 'retention_change': change,
                      'retrieved_evidence_coverage': before_coverage,
                      'context_evidence_coverage': after_coverage,
                      'input_units': pack['input_units'], 'included_units': pack['included_units'],
                      'words': pack['budget']['used'], 'omitted_groups': pack['omitted_groups'],
                      'candidate_file_sha256': digest(saved_path)}
            write_json(output / 'cases' / (case['case_id'] + '.json'), record)
            records.append(record)
            value = after['passage_recall']
            print(f'{n}/45 {case["case_id"]}: context recall '
                  + (f'{value:.0%}' if value is not None else 'no gold')
                  + f'; {change}; {pack["included_units"]}/{pack["input_units"]} units.', flush=True)
        summary = {'status': 'complete', 'identity': identity, 'case_count': len(records),
                   'gold_case_count': sum(r['context']['passage_recall'] is not None for r in records),
                   'loss_case_ids': [r['case_id'] for r in records if r['retention_change'] == 'lost_evidence'],
                   'incomplete_context_case_ids': [r['case_id'] for r in records
                                                   if r['context']['all_expected_evidence'] is False],
                   'no_gold_case_ids': [r['case_id'] for r in records if r['retention_change'] == 'no_gold'],
                   'limitations': 'Context coverage only, not answer correctness or citation faithfulness. '
                                  'Word cap is not a model-token guarantee.'}
        for stage in ('retrieved', 'context'):
            scores = [r[stage]['passage_recall'] for r in records if r[stage]['passage_recall'] is not None]
            summary[stage] = {'macro_passage_recall': sum(scores) / len(scores) if scores else None,
                              'all_expected_evidence_cases': sum(r[stage]['all_expected_evidence'] is True
                                                                 for r in records)}
        write_json(output / 'summary.json', summary)
        write_json(Path('data/indexes/context-eval/latest.json'), {'summary_path': str(output / 'summary.json')})
        print(f'RECALL: retrieved {summary["retrieved"]["macro_passage_recall"]:.1%} -> '
              f'context {summary["context"]["macro_passage_recall"]:.1%}')
        print(f'COMPLETE EVIDENCE: retrieved {summary["retrieved"]["all_expected_evidence_cases"]}/'
              f'{summary["gold_case_count"]} -> '
              f'context {summary["context"]["all_expected_evidence_cases"]}/{summary["gold_case_count"]}')
        print('LOST DURING PACKING: ' + (', '.join(summary['loss_case_ids']) or 'none'))
        print(f'SAVED: {output / "summary.json"}\nNo model calls, holdout, index changes or GitHub sync.')
    except Exception as error:
        print('STOP: ' + safe_error(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
