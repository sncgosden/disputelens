"""Inspect a downloaded PDF page with its source metadata; no model calls."""

import argparse
import hashlib
import json
from pathlib import Path

from pypdf import PdfReader


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def read_page(source: dict, page_number: int, root: Path = PROJECT_ROOT) -> dict:
    """Use one-based PDF file pages, which may differ from printed page labels."""
    path = root / source['path']
    provenance = json.loads((root / source['provenance_path']).read_text())
    fingerprint = hashlib.sha256(path.read_bytes()).hexdigest()
    if fingerprint != provenance['sha256']:
        raise ValueError('PDF differs from the saved download fingerprint.')
    reader = PdfReader(path)
    if reader.is_encrypted:
        raise ValueError('Encrypted PDF: review access before extracting text.')
    if not 1 <= page_number <= len(reader.pages):
        raise ValueError(f'Page must be between 1 and {len(reader.pages)}.')
    text = reader.pages[page_number - 1].extract_text() or ''
    labels = reader.page_labels
    return {
        'source': dict(source),
        'sha256': fingerprint,
        'page_count': len(reader.pages),
        'pdf_page': page_number,
        'pdf_page_label': labels[page_number - 1],
        'locator': f"{source['source_id']}:pdf-page-{page_number}",
        'text': text,
        'warnings': [] if text.strip() else [
            'No text extracted. Page may be blank or scanned; inspect the original.'
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default='visa-dispute-management-june-2024')
    parser.add_argument('--page', type=int, default=1, help='PDF file page, starting at 1')
    args = parser.parse_args()
    manifest = json.loads((PROJECT_ROOT / 'data/source-manifest.json').read_text())
    matches = [s for s in manifest['sources'] if s['source_id'] == args.source]
    if len(matches) != 1 or matches[0]['document_type'] != 'pdf':
        parser.error('Choose exactly one PDF source ID from the manifest.')
    try:
        result = read_page(matches[0], args.page)
    except Exception as error:
        parser.exit(1, f'PDF extraction failed ({type(error).__name__}): {error}\n')
    details = {key: value for key, value in result.items() if key != 'text'}
    print(json.dumps(details, indent=2, ensure_ascii=False))
    print('\n--- EXTRACTED PAGE TEXT ---\n')
    print(result['text'] if result['text'].strip() else '[No readable text extracted]')
    print('\nExtraction inspection only: no files changed, indexing or model calls.')


if __name__ == '__main__':
    main()
