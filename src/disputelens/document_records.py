"""Normalize parsed sources into common parent documents and evidence blocks."""

import hashlib
import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def normalize_document(parsed: dict) -> dict:
    source = parsed['source']
    parent_id = source['source_id']
    evidence = []
    for block in parsed['blocks']:
        if block.get('structure_review_required'):
            raise ValueError(f"Unreviewed structure: {block['block_id']}")
        units = block.get('passages') or [{
            'passage_id': block['block_id'], 'text': block['text'],
            'locator': block['locator'],
        }]
        for unit in units:
            headings = list(block['headings'])
            if unit.get('section') and unit['section'] not in headings:
                headings.append(unit['section'])
            evidence.append({
                'passage_id': unit['passage_id'],
                'parent_id': parent_id,
                'source_block_id': block['block_id'],
                'type': block['type'],
                'headings': headings,
                'text': unit['text'],
                'locator': {
                    'reference': unit['locator'],
                    'pdf_page': block.get('pdf_page'),
                    'pdf_page_label': block.get('pdf_page_label'),
                    'start_line': block.get('start_line'),
                },
                'rows': block.get('rows'),
                'links': block.get('links', []),
            })
    if not evidence or len({b['passage_id'] for b in evidence}) != len(evidence):
        raise ValueError(f'Empty or duplicate evidence: {parent_id}')
    return {
        'schema_version': '1.0',
        'parent_id': parent_id,
        'source_sha256': parsed['source_sha256'],
        'metadata': source,
        'blocks': evidence,
        'warnings': parsed['warnings'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expanded', action='store_true')
    args = parser.parse_args()
    suffix = '-expanded' if args.expanded else ''
    manifest = json.loads((ROOT / 'data/source-manifest.json').read_text())
    documents = []
    try:
        for source in manifest['sources']:
            parsed_path = ROOT / ('data/parsed' + suffix) / (source['source_id'] + '.json')
            parsed_bytes = parsed_path.read_bytes()
            parsed = json.loads(parsed_bytes)
            fingerprint = hashlib.sha256((ROOT / source['path']).read_bytes()).hexdigest()
            if parsed['source']['source_id'] != source['source_id']:
                raise ValueError(f"Source identity mismatch: {source['source_id']}")
            if fingerprint != parsed['source_sha256']:
                raise ValueError(f"Stale extraction: {source['source_id']}; parse again.")
            # Refresh manifest metadata while retaining the verified PDF edition.
            metadata = dict(source)
            if source['document_type'] == 'pdf':
                metadata['version'] = parsed['source']['version']
            parsed['source'] = metadata
            document = normalize_document(parsed)
            document['parsed_record_sha256'] = hashlib.sha256(parsed_bytes).hexdigest()
            documents.append(document)
        ids = [b['passage_id'] for d in documents for b in d['blocks']]
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate passage IDs across documents.')
        if any(not b['text'].strip() or not b['locator']['reference']
               for d in documents for b in d['blocks']):
            raise ValueError('Empty evidence text or missing locator.')
    except (OSError, ValueError, KeyError) as error:
        raise SystemExit(f'Normalization stopped: {error}')
    output = ROOT / ('data/normalized' + suffix)
    output.mkdir(parents=True, exist_ok=True)
    result = {
        'schema_version': '1.0',
        'manifest_sha256': hashlib.sha256((ROOT / 'data/source-manifest.json').read_bytes()).hexdigest(),
        'documents': documents,
    }
    (output / 'documents.json').write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'SAVED: {len(documents)} parent documents; {len(ids)} unique evidence blocks.')
    for document in documents:
        source = document['metadata']
        print(f"  {document['parent_id']}: {source['document_type']}, {source['corpus']}, {len(document['blocks'])} blocks")
    print('Source hashes, metadata, headings, tables and locators retained. No AI calls or indexing.')


if __name__ == '__main__':
    main()
