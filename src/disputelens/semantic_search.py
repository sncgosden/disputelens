"""Inspect semantic retrieval with trusted public-guidance applicability filters."""
import argparse
import json
import os
import sys
import time
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny, IsEmptyCondition, PayloadField

from .applicability import applicable
from .build_index import checked_vectors, digest
from .client import ModelError, configured_models
from .embed_batch import loaded_embedding_model, safe_error, write_json


def scope_filter(*, corpus, provider=None, scheme=None, region=None):
    """Filter before nearest-neighbour ranking; no account inference from query text."""
    conditions = [FieldCondition(key='metadata.corpus', match=MatchValue(value=corpus))]
    for name, value in (('provider', provider), ('scheme', scheme)):
        options = [IsEmptyCondition(is_empty=PayloadField(key='metadata.' + name))]
        if value is not None:
            options.append(FieldCondition(key='metadata.' + name, match=MatchValue(value=value)))
        conditions.append(Filter(should=options))
    regions = ['', 'global', 'multiple'] + ([region] if region else [])
    conditions.append(Filter(should=[
        IsEmptyCondition(is_empty=PayloadField(key='metadata.region')),
        FieldCondition(key='metadata.region', match=MatchAny(any=regions))]))
    return Filter(must=conditions, must_not=[
        FieldCondition(key='metadata.status', match=MatchValue(value='superseded'))])


def retrieve(client, collection, vector, filters, top_k=5):
    if not 1 <= top_k <= 50:
        raise ModelError('Choose between 1 and 50 results.')
    points = client.query_points(collection, query=vector,
        query_filter=scope_filter(**filters), limit=top_k,
        with_payload=True, with_vectors=False).points
    results = []
    for point in points:
        payload = point.payload
        if not payload or not applicable(payload['metadata'], **filters):
            raise ModelError('Retrieved passage failed the independent applicability check.')
        results.append({'rank': len(results)+1, 'similarity': point.score, 'unit': payload})
    return results


def evidence_coverage(results, passage_ids, units):
    """Report character coverage, never give a fragment credit for its full parent."""
    report = []
    for passage_id in passage_ids:
        lengths = {e['original_evidence_characters'] for u in units for e in u['evidence']
                   if e['passage_id'] == passage_id}
        if len(lengths) != 1:
            raise ModelError(f'Expected evidence length is missing or inconsistent: {passage_id}')
        length = lengths.pop()
        spans = sorted((e['evidence_character_start'], e['evidence_character_end'])
            for r in results for e in r['unit']['evidence'] if e['passage_id'] == passage_id)
        covered, right = 0, 0
        for start, end in spans:
            if not 0 <= start <= end <= length:
                raise ModelError('Invalid evidence span in retrieved payload.')
            covered += max(0, end-max(start, right))
            right = max(right, end)
        report.append({'passage_id': passage_id, 'covered_characters': covered,
                       'total_characters': length, 'fully_retrieved': covered == length,
                       'ranks': [r['rank'] for r in results if passage_id in r['unit']['passage_ids']]})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('question', nargs='?')
    parser.add_argument('--dev-case', help='Saved development case ID; holdout cases are not loaded')
    parser.add_argument('--provider', choices=['Stripe', 'Adyen', 'Square', 'PayPal',
                                                             'DisputeLens fictional provider'])
    parser.add_argument('--scheme', choices=['Visa', 'Mastercard'])
    parser.add_argument('--region', help='Trusted merchant region, for example UK')
    parser.add_argument('--corpus', choices=['real', 'fixture'])
    parser.add_argument('--top-k', type=int, default=5)
    parser.add_argument('--strategy', choices=['vector', 'bm25', 'hybrid'], default='vector')
    parser.add_argument('--candidate-k', type=int, default=20, help='Candidates per method for hybrid fusion')
    parser.add_argument('--preview-chars', type=int, default=1000)
    args = parser.parse_args()
    models, client = configured_models(), None
    try:
        case = None
        if args.dev_case:
            if args.question is not None or any(v is not None for v in
                    (args.provider, args.scheme, args.region, args.corpus)):
                raise ModelError('Use a saved development case without overriding its question or filters.')
            config = json.loads(Path('data/pipeline-config.json').read_text())
            cases = json.loads(Path(config['dev_cases_path']).read_text())
            case = next((c for c in cases if c['case_id'] == args.dev_case and c['split'] == 'dev'), None)
            if case is None:
                raise ModelError('Unknown development case ID. No holdout cases are loaded.')
            question, filters = case['question'], case['filters']
            print(f'Development case: {case["case_id"]}\nQuestion: {question}', flush=True)
        else:
            if not args.question or not all((args.provider, args.scheme, args.region)):
                raise ModelError('Supply a question, provider, scheme and region, or use --dev-case.')
            question = args.question
            filters = {'corpus': args.corpus or 'real', 'provider': args.provider,
                       'scheme': args.scheme, 'region': args.region}
        if not 1 <= args.top_k <= 50 or not 100 <= args.preview_chars <= 3000:
            raise ModelError('Use top-k between 1 and 50 and preview-chars between 100 and 3000.')
        if not 1 <= args.candidate_k <= 50:
            raise ModelError('Use candidate-k between 1 and 50.')
        manifest = json.loads(Path('data/indexes/index-manifest.json').read_text())
        if manifest['status'] != 'complete':
            raise ModelError('Finish build_index before searching.')
        if (manifest['model'] != os.getenv('LM_EMBEDDING_MODEL')
                or manifest['document_prefix'] != os.getenv('EMBED_DOCUMENT_PREFIX', 'search_document: ')
                or digest(manifest['embedding_units_path']) != manifest['embedding_units_sha256']):
            raise ModelError('Embedding configuration or search units changed. Rebuild the index first.')
        if not question.strip():
            raise ModelError('Enter a non-empty merchant question.')
        print('Trusted merchant settings: ' + json.dumps(filters), flush=True)
        units = json.loads(Path(manifest['embedding_units_path']).read_text())['chunks']
        started = time.perf_counter()
        query_prefix, bm25_config, fusion_config, candidates = None, None, None, None
        if args.strategy in ('vector', 'hybrid'):
            import lmstudio as lms
            if os.getenv('LM_API_TOKEN'):
                raise ModelError('The pinned SDK does not support authenticated token checking.')
            from urllib.parse import urlparse
            if urlparse(models.base).hostname not in ('localhost', '127.0.0.1', '::1'):
                raise ModelError('This search step requires LM Studio on this Mac.')
            query_prefix = os.getenv('EMBED_QUERY_PREFIX', 'search_query: ')
            embedding_model = loaded_embedding_model(lms, manifest['model'])
            if len(embedding_model.tokenize(query_prefix + question)) + 8 > embedding_model.get_context_length():
                raise ModelError('Question is too long for the embedding model. Shorten it.')
            print('Embedding the question, then searching local Qdrant...', flush=True)
            started = time.perf_counter()
            vector = checked_vectors(models.embed([question], kind='query'), 1, manifest['dimension'])[0]
            client = QdrantClient(path=manifest['qdrant_path'])
            results = retrieve(client, manifest['collection_name'], vector.tolist(), filters,
                               args.candidate_k if args.strategy == 'hybrid' else args.top_k)
            if args.strategy == 'hybrid':
                from .keyword_search import retrieve_keyword, BM25_CONFIG
                from .hybrid_search import fuse_rankings
                vector_results = results
                keyword_results = retrieve_keyword(units, question, filters, args.candidate_k)
                candidates = {'vector': vector_results, 'bm25': keyword_results}
                bm25_config = BM25_CONFIG
                fusion_config = {'method': 'reciprocal-rank-fusion', 'rank_constant': 60,
                                 'weights': {'vector': 1, 'bm25': 1},
                                 'candidate_k_per_method': args.candidate_k}
                results = fuse_rankings(vector_results, keyword_results, args.top_k)
                print(f'Fused {len(vector_results)} vector and {len(keyword_results)} BM25 candidates.', flush=True)
        else:
            from .keyword_search import retrieve_keyword, BM25_CONFIG
            print('Searching words and exact codes locally with BM25; no model calls...', flush=True)
            results = retrieve_keyword(units, question, filters, args.top_k)
            bm25_config = BM25_CONFIG
        seconds = time.perf_counter()-started
        if any(not applicable(r['unit']['metadata'], **filters) for r in results):
            raise ModelError('Final results failed the applicability check.')
        coverage = evidence_coverage(results, case['relevant_passage_ids'], units) if case else []
        filename_prefix = {'vector': 'semantic-search', 'bm25': 'keyword-search',
                           'hybrid': 'hybrid-search'}[args.strategy]
        output = Path('data/indexes') / (f'{filename_prefix}-{case["case_id"]}.json' if case else f'{filename_prefix}-latest.json')
        write_json(output, {'case_id': case['case_id'] if case else None,
            'strategy': args.strategy, 'bm25_config': bm25_config,
            'fusion_config': fusion_config, 'component_candidates': candidates,
            'question': question, 'filters': filters, 'expected_evidence_coverage': coverage,
            'collection': manifest['collection_name'], 'embedding_model': manifest['model'],
            'query_prefix': query_prefix, 'embedding_units_sha256': manifest['embedding_units_sha256'],
            'top_k': args.top_k, 'seconds': seconds, 'results': results})
        for result in results:
            unit = result['unit']
            label, score = (('similarity', result['similarity']) if args.strategy == 'vector'
                            else ('BM25 score', result['bm25_score']) if args.strategy == 'bm25'
                            else ('RRF score', result['rrf_score']))
            print(f'\n{result["rank"]}. {unit["metadata"]["title"]} — {label} {score:.3f}')
            if args.strategy == 'hybrid':
                print('   Original ranks: ' + json.dumps(result['component_ranks']))
            print(f'   Source: {unit["metadata"]["source_id"]}; unit: {unit["chunk_id"]}')
            locators = list(dict.fromkeys(str(e['locator']) for e in unit['evidence']))
            print('   Evidence locations: ' + '; '.join(locators))
            print(unit['text'][:args.preview_chars] + ('\n[Console preview shortened; full passage saved.]'
                if len(unit['text']) > args.preview_chars else ''))
        for entry in coverage:
            status = 'FULL' if entry['fully_retrieved'] else 'PARTIAL' if entry['covered_characters'] else 'MISSING'
            print(f'GOLD EVIDENCE {status}: {entry["passage_id"]}; '
                  f'{entry["covered_characters"]}/{entry["total_characters"]} characters; ranks {entry["ranks"]}')
        print(f'\nPASS: {len(results)} passages returned; all satisfy the merchant settings.')
        print(f'Seconds: {seconds:.1f}; SAVED: {output}')
        print('Retrieval scores are not correctness or confidence; vector and BM25 scores use different scales.')
        print('No answer generated yet. No chat models, Claude calls or GitHub sync.')
    except Exception as error:
        print(f'STOP: {safe_error(error)}', file=sys.stderr)
        return 1
    finally:
        if client is not None:
            client.close()
        models.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
