"""Create a separate bookmark-heading experiment from verified saved extraction."""
import copy
import hashlib
import json
import sys
from pathlib import Path

from pypdf import PdfReader

from .chunk_documents import make_chunks
from .client import ModelError
from .document_records import normalize_document
from .embed_batch import safe_error, write_json
from .pdf_sections import apply_section_headings, bookmark_sections


def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def evidence_signature(documents):
    """Compare everything except headings and heading provenance."""
    signature = []
    for doc in documents:
        signature.append({'parent_id': doc['parent_id'], 'metadata': doc['metadata'],
                          'source_sha256': doc['source_sha256'],
                          'blocks': [{key: value for key, value in block.items()
                                      if key not in ('headings', 'heading_provenance')}
                                     for block in doc['blocks']]})
    return signature


def main():
    try:
        config = json.loads(Path('data/pipeline-config.json').read_text())
        normalized_path = Path(config['normalized_path'])
        original = json.loads(normalized_path.read_text())
        updated = copy.deepcopy(original)
        doc = next(d for d in updated['documents'] if d['parent_id'] == 'mastercard-chargeback-guide')
        parsed_path = Path('data/parsed-expanded/mastercard-chargeback-guide.json')
        parsed = json.loads(parsed_path.read_text())
        if fingerprint(parsed_path) != doc['parsed_record_sha256']:
            raise ModelError('Saved extraction differs from the normalized baseline; review before proceeding.')
        if fingerprint(doc['metadata']['path']) != doc['source_sha256']:
            raise ModelError('Mastercard source changed; this would not be a headings-only comparison.')
        parsed['source'] = doc['metadata']
        reader = PdfReader(doc['metadata']['path'])
        events = bookmark_sections(reader)
        if not events:
            raise ModelError('No publisher bookmarks available; no guessed headings applied.')
        audit = apply_section_headings(parsed['blocks'], events, doc['metadata']['title'])
        replacement = normalize_document(parsed)
        replacement['parsed_record_sha256'] = doc['parsed_record_sha256']
        replacement['heading_transformation'] = 'publisher-bookmarks-v1'
        updated['documents'] = [replacement if d['parent_id'] == doc['parent_id'] else d
                                for d in updated['documents']]
        if evidence_signature(original['documents']) != evidence_signature(updated['documents']):
            raise ModelError('Evidence or scope metadata changed. Experiment stopped.')
        chunks = [chunk for d in updated['documents'] for chunk in make_chunks(d, 400, 40)]
        expected = [b['passage_id'] for d in updated['documents'] for b in d['blocks']]
        actual = list(dict.fromkeys(pid for chunk in chunks for pid in chunk['passage_ids']))
        if actual != expected or len({c['chunk_id'] for c in chunks}) != len(chunks):
            raise ModelError('Evidence coverage/order or unique chunk IDs failed.')
        identity = {'baseline_normalized_sha256': fingerprint(normalized_path),
                    'parsed_record_sha256': fingerprint(parsed_path),
                    'source_sha256': doc['source_sha256'],
                    'section_code_sha256': fingerprint(Path(__file__).with_name('pdf_sections.py')),
                    'preparation_code_sha256': fingerprint(__file__),
                    'chunk_code_sha256': fingerprint(Path(__file__).with_name('chunk_documents.py')),
                    'target_words': 400, 'overlap_words': 40}
        run_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
        directory = Path('data/indexes/section-hierarchy') / run_id
        normalized_output = directory / 'documents.json'
        chunk_output = directory / 'chunks.json'
        write_json(normalized_output, updated)
        write_json(chunk_output, {'schema_version': '1.0',
                                'normalized_sha256': fingerprint(normalized_output), 'chunks': chunks})
        by_id = {b['passage_id']: b for b in replacement['blocks']}
        examples = [{'passage_id': pid, 'headings': by_id[pid]['headings']} for pid in (
            'mastercard-chargeback-guide:page-228:paragraph-6',
            'mastercard-chargeback-guide:page-229:paragraph-3',
            'mastercard-chargeback-guide:page-229:paragraph-4')]
        write_json(directory / 'heading-audit.json', {**audit, 'examples': examples})
        manifest = {'status': 'prepared_not_evaluated', 'identity': identity,
                    'directory': str(directory), 'normalized_path': str(normalized_output),
                    'chunk_path': str(chunk_output), 'baseline_normalized_path': str(normalized_path),
                    'evidence_blocks': len(expected), 'chunks': len(chunks),
                    'evidence_and_scope_unchanged': True,
                    'limitation': 'Section applicability unchanged. New hierarchy changes chunk boundaries too; '
                                  'this is a structure-aware ingestion experiment, not a pure heading-text ablation.'}
        write_json(directory / 'experiment.json', manifest)
        write_json(Path('data/indexes/section-hierarchy/latest.json'),
                   {'experiment_path': str(directory / 'experiment.json')})
        print(f'PASS: {len(expected)} evidence blocks and all scope metadata unchanged.')
        print(f'PREPARED: {len(chunks)} chunks using {len(events)} publisher bookmarks.')
        print(f'REVIEW: {len(audit["unmatched_text_boundaries"])} bookmark titles not matched within their start page.')
        for example in examples:
            print(example['passage_id'] + '\n  ' + ' > '.join(example['headings']))
        print(f'SAVED: {directory}\nOriginal corpus, index and results preserved. '
              'No tokenization, embeddings, generation, holdout or GitHub sync.')
    except Exception as error:
        print('STOP: ' + safe_error(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
