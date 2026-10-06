"""Map frozen gold passages to chunk layouts without changing gold labels."""

import hashlib
import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def map_layout(layout: dict, cases: list[dict], documents: dict) -> dict:
    passages = {
        block['passage_id']: (block, document['metadata'])
        for document in documents['documents'] for block in document['blocks']
    }
    result = {}
    for case in cases:
        referenced = set(case['relevant_passage_ids']) | {
            pid for claim in case['expected_claims'] for pid in claim['supporting_passage_ids']
        }
        mapping = {}
        for passage_id in sorted(referenced):
            if passage_id not in passages:
                raise ValueError(f'Unknown gold passage: {passage_id}')
            block, metadata = passages[passage_id]
            filters = case['filters']
            if metadata['corpus'] != filters['corpus'] or metadata['status'] == 'superseded':
                raise ValueError(f'Inapplicable gold passage for {case["case_id"]}: {passage_id}')
            for field in ('provider', 'scheme'):
                if metadata[field] is not None and metadata[field] != filters[field]:
                    raise ValueError(f'Gold {field} mismatch: {passage_id}')
            matches = []
            for chunk in layout['chunks']:
                if passage_id not in chunk['passage_ids']:
                    continue
                retained = [b for b in chunk['evidence'] if b['passage_id'] == passage_id]
                if len(retained) != 1 or retained[0]['text'] != block['text']:
                    raise ValueError(f'Incomplete evidence: {passage_id} in {chunk["chunk_id"]}')
                if block['text'] not in chunk['text']:
                    raise ValueError(f'Gold text absent from retrievable text: {passage_id}')
                matches.append(chunk['chunk_id'])
            if not matches:
                raise ValueError(f'No chunk contains gold evidence: {passage_id}')
            mapping[passage_id] = matches
        result[case['case_id']] = {
            'split': case['split'],
            'relevant_passage_ids': case['relevant_passage_ids'],
            'passage_to_chunk_ids': mapping,
        }
    return result


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expanded', action='store_true')
    args = parser.parse_args()
    suffix = '-expanded' if args.expanded else ''
    normalized_path = ROOT / ('data/normalized' + suffix) / 'documents.json'
    documents = json.loads(normalized_path.read_text())
    if digest(ROOT / 'data/source-manifest.json') != documents['manifest_sha256']:
        raise SystemExit('Manifest changed: normalize and chunk again.')
    case_directory = ROOT / ('eval/expanded' if args.expanded else 'eval')
    case_paths = [case_directory / 'dev-cases.json', case_directory / 'holdout-cases.json']
    cases = [case for path in case_paths for case in json.loads(path.read_text())]
    output = {
        'schema_version': '1.0',
        'purpose': 'Text-preservation mapping only; holdout labels must not guide tuning.',
        'case_sha256': {p.name: digest(p) for p in case_paths},
        'layouts': {},
    }
    for filename in ('chunks-400-overlap-40.json', 'chunks-250-overlap-40.json'):
        path = ROOT / ('data/chunks' + suffix) / filename
        layout = json.loads(path.read_text())
        if layout['normalized_sha256'] != digest(normalized_path):
            raise SystemExit(f'Stale chunks: {filename}. Rebuild them.')
        output['layouts'][filename] = {
            'chunk_file_sha256': digest(path),
            'cases': map_layout(layout, cases, documents),
        }
        print(f'PASS: {filename}: all gold evidence retained for {len(cases)} cases.')
    path = ROOT / ('data/chunks' + suffix) / 'gold-evidence-map.json'
    path.write_text(json.dumps(output, indent=2) + '\n', encoding='utf-8')
    print('SAVED: ' + str(path.relative_to(ROOT)))
    print('Mapping is not a retrieval result. No gold text sent to a model; no index or GitHub sync.')


if __name__ == '__main__':
    main()
