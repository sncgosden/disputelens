"""Evaluate a declared query-aware context policy on development data."""
import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path

from .build_index import digest
from .client import ModelError
from .context_pack import build_context
from .embed_batch import safe_error, write_json
from .evaluate_context import coverage_score
from .evaluate_retrieval import query_type
from .semantic_search import evidence_coverage


def choose_strategy(question):
    """Query text chooses ranking strategy, never merchant access or gold evidence."""
    return 'bm25' if query_type(question) == 'exact_code' else 'hybrid'


def experiment_pointer(top_k, max_words):
    if (top_k, max_words) == (5, 2500):
        return Path('data/indexes/focused-context/latest.json')
    return Path(f'data/indexes/focused-context/latest-top{top_k}-words{max_words}.json')


def find_bm25(hybrid_identity):
    matches = []
    for path in Path('data/indexes/section-scope').glob('*/comparison.json'):
        data = json.loads(path.read_text())
        identity = data.get('identity', {})
        if (data.get('status') == 'complete' and identity.get('strategy') == 'bm25'
                and all(identity.get(key) == hybrid_identity.get(key) for key in (
                    'embedding_units_sha256', 'section_documents_sha256', 'dev_cases_sha256', 'payment_rail'))
                and identity.get('code_sha256', {}).get('section_scope.py')
                    == hybrid_identity['code_sha256']['section_scope.py']):
            matches.append(path)
    if not matches:
        raise ModelError('No matching completed section-scoped BM25 evaluation found.')
    return max(matches, key=lambda path: (path.stat().st_mtime_ns, str(path)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--top-k', type=int, choices=(5, 10, 20), default=5)
    parser.add_argument('--max-words', type=int, choices=(2500, 4500, 6000), default=2500)
    args = parser.parse_args()
    try:
        config = json.loads(Path('data/pipeline-config.json').read_text())
        case_path = Path(config['dev_cases_path'])
        cases = json.loads(case_path.read_text())
        if len(cases) != 45 or any(c['split'] != 'dev' for c in cases):
            raise ModelError('Expected the fixed 45 development cases only.')
        pointer = json.loads(Path('data/indexes/section-scope/hybrid-latest.json').read_text())
        hybrid_path = Path(pointer['comparison_path'])
        hybrid = json.loads(hybrid_path.read_text())
        hidentity = hybrid['identity']
        package = Path(__file__).parent
        if (hybrid['status'] != 'complete' or hidentity['strategy'] != 'hybrid'
                or hidentity['dev_cases_sha256'] != digest(case_path)
                or hidentity['embedding_units_sha256'] != digest(config['embedding_units_path'])
                or hidentity['code_sha256']['section_scope.py'] != digest(package / 'section_scope.py')):
            raise ModelError('Scoped hybrid evaluation differs from current cases, units or scope code.')
        bm25_path = find_bm25(hidentity)
        bm25 = json.loads(bm25_path.read_text())
        comparisons = {'hybrid': (hybrid_path, hybrid), 'bm25': (bm25_path, bm25)}
        full_pointer = json.loads(Path('data/indexes/context-eval/latest.json').read_text())
        full_path = Path(full_pointer['summary_path'])
        full = json.loads(full_path.read_text())
        if (full['status'] != 'complete'
                or full['identity']['dev_cases_sha256'] != digest(case_path)
                or full['identity']['retrieval_comparison_sha256'] != digest(hybrid_path)
                or full['identity']['builder_code_sha256'] != digest(package / 'context_pack.py')):
            raise ModelError('Full-context comparison is stale or uses a different candidate run.')
        units = json.loads(Path(config['embedding_units_path']).read_text())['chunks']
        by_id = {u['chunk_id']: u for u in units}
        scope_data = json.loads((hybrid_path.parent / 'passage-scope-map.json').read_text())
        if scope_data['identity'] != hidentity:
            raise ModelError('Publisher scope map differs from hybrid run.')
        identity = {'policy': 'explicit-code-bm25-otherwise-hybrid-fixed-prefix-v2',
                    'top_k': args.top_k, 'max_words': args.max_words,
                    'dev_cases_sha256': digest(case_path),
                    'embedding_units_sha256': digest(config['embedding_units_path']),
                    'builder_code_sha256': digest(package / 'context_pack.py'),
                    'selector_code_sha256': digest(__file__),
                    'query_classifier_sha256': digest(package / 'evaluate_retrieval.py'),
                    'coverage_code_sha256': digest(package / 'semantic_search.py'),
                    'full_context_summary_sha256': digest(full_path),
                    'scoped_comparison_sha256': {name: digest(path) for name, (path, _) in comparisons.items()}}
        run_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
        output = Path('data/indexes/focused-context') / run_id
        rows = []
        for case in cases:
            strategy = choose_strategy(case['question'])
            path, comparison = comparisons[strategy]
            saved_path = path.parent / 'cases' / (case['case_id'] + '.json')
            saved = json.loads(saved_path.read_text())
            if (saved['identity'] != comparison['identity'] or saved['question'] != case['question']
                    or saved['filters'] != case['filters']
                    or any(by_id.get(r['unit']['chunk_id']) != r['unit'] for r in saved['results'])):
                raise ModelError('Focused candidate payload/question/scope mismatch.')
            candidates = saved['results'][:args.top_k]
            # Fixed routing and selection occur without expected answers or passage IDs.
            pack = build_context(candidates, saved['filters'], scope_data['passages'], max_words=args.max_words)
            pack['question'] = saved['question']
            pack['evaluation_identity'] = identity
            pack['selection_strategy'] = strategy
            results = [{'rank': n, 'unit': {'passage_ids': [e['passage_id'] for e in g['evidence']],
                                           'evidence': g['evidence']}}
                       for n, g in enumerate(pack['groups'], 1)]
            coverage = evidence_coverage(results, case['relevant_passage_ids'], units)
            score = coverage_score(coverage)
            old = json.loads((full_path.parent / 'cases' / (case['case_id'] + '.json')).read_text())
            if old['question'] != case['question'] or old['filters'] != case['filters']:
                raise ModelError('Full-context question or scope differs.')
            a, b = old['context']['passage_recall'], score['passage_recall']
            if (a is None) != (b is None):
                raise ModelError('Focused comparison changed gold denominators.')
            change = 'no_gold' if a is None else ('improved' if b > a + 1e-12 else
                                                'worsened' if b < a - 1e-12 else 'unchanged')
            record = {'case_id': case['case_id'], 'strategy': strategy,
                      'question': case['question'], 'filters': case['filters'],
                      'full_context': old['context'], 'focused_context': score,
                      'change': change, 'coverage': coverage,
                      'words': pack['budget']['used'], 'included_units': pack['included_units'],
                      'citation_count': len(pack['citations']), 'omitted_groups': pack['omitted_groups'],
                      'candidate_file_sha256': digest(saved_path)}
            write_json(output / 'packs' / (case['case_id'] + '.json'), pack)
            write_json(output / 'cases' / (case['case_id'] + '.json'), record)
            rows.append(record)
            print(f'{case["case_id"]}: {strategy}; {pack["included_units"]}/{args.top_k} units; '
                  f'{pack["budget"]["used"]} words; {change}', flush=True)
        summary = {'status': 'complete', 'identity': identity, 'case_count': len(rows),
                   'gold_case_count': sum(r['focused_context']['passage_recall'] is not None for r in rows),
                   'improved_case_ids': [r['case_id'] for r in rows if r['change'] == 'improved'],
                   'worsened_case_ids': [r['case_id'] for r in rows if r['change'] == 'worsened'],
                   'limitations': 'Fixed smaller-context experiment; not promoted. No answer generation or model-token checks.'}
        summary['median_words'] = statistics.median(r['words'] for r in rows)
        summary['median_citations'] = statistics.median(r['citation_count'] for r in rows)
        for stage in ('full_context', 'focused_context'):
            values = [r[stage]['passage_recall'] for r in rows if r[stage]['passage_recall'] is not None]
            summary[stage] = {'macro_passage_recall': sum(values) / len(values) if values else None,
                              'complete_evidence_cases': sum(r[stage]['all_expected_evidence'] is True for r in rows)}
        write_json(output / 'summary.json', summary)
        write_json(experiment_pointer(args.top_k, args.max_words), {'summary_path': str(output / 'summary.json')})
        print(f'RECALL: full {summary["full_context"]["macro_passage_recall"]:.1%} -> '
              f'focused {summary["focused_context"]["macro_passage_recall"]:.1%}')
        print(f'COMPLETE EVIDENCE: full {summary["full_context"]["complete_evidence_cases"]}/'
              f'{summary["gold_case_count"]} -> focused {summary["focused_context"]["complete_evidence_cases"]}/'
              f'{summary["gold_case_count"]}')
        print('WORSENED: ' + (', '.join(summary['worsened_case_ids']) or 'none'))
        e14 = next(r for r in rows if r['case_id'] == 'E14')
        print(f'E14: {e14["words"]} words; {e14["citation_count"]} citations; '
              f'recall {e14["focused_context"]["passage_recall"]:.0%}')
        e31 = next(r for r in rows if r['case_id'] == 'E31')
        print(f'E31: {e31["words"]} words; {e31["citation_count"]} citations; '
              f'recall {e31["focused_context"]["passage_recall"]:.0%}')
        print(f'MEDIAN PACK: {summary["median_words"]} words; {summary["median_citations"]} citations')
        print(f'SAVED: {output / "summary.json"}\nNo model calls, holdout, index changes or GitHub sync.')
    except Exception as error:
        print('STOP: ' + safe_error(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
