"""Parse the selected corpus into inspectable local records without AI calls."""

import hashlib
import json
import re
from pathlib import Path

from pypdf import PdfReader

from .read_html import read_article
from .read_markdown import read_policy


ROOT = Path(__file__).resolve().parents[2]
PDF_HASH = '5505594a9ae3a062c84a85294adcf5c621ac80d292f5ab7e0c24bd2b26a16cd4'
PDF_SELECTION = {40: '13.1', 41: '13.1', 42: '13.2', 48: '13.6'}
PDF_REVIEW = {
    'source_sha256': PDF_HASH,
    'reviewed_pdf_pages': [40, 41, 42, 48],
    'method': 'Visual comparison of rendered original pages against extracted text',
    'reviewed_on': '2026-10-06',
    'findings': 'Response condition/action ordering retained. Page 41 continues 13.1. Page 42 footnote markers corrected; regional footnote text retained.',
    'limitation': 'Review covers only these four pages of this exact file, not arbitrary PDF layouts.',
}


def clean_text(text: str, pdf: bool = False) -> str:
    """Normalize spacing; retain lines, bullets, amounts and qualifications."""
    lines = []
    for line in text.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        line = re.sub(r'[^\S\n]+', ' ', line).strip()
        if pdf and (line == '3 Dispute Conditions'
                    or line.startswith('Dispute Management Guidelines for Visa Merchants |')
                    or line.startswith('© 2024 Visa. All Rights Reserved.')):
            continue
        if line or (lines and lines[-1]):
            lines.append(line)
    return '\n'.join(lines).strip()


def parse_source(source: dict) -> dict:
    fingerprint = hashlib.sha256((ROOT / source['path']).read_bytes()).hexdigest()
    kind = source['document_type']
    warnings = []
    if kind == 'markdown':
        record = read_policy(source)
        blocks = [{**section, 'block_id': section['section_id'], 'type': 'section',
                   'locator': f"{source['path']}:line-{section['start_line']}"}
                  for section in record['sections']]
    elif kind == 'html':
        blocks = read_article(source)['blocks']
    elif kind == 'pdf':
        if fingerprint != PDF_HASH:
            raise ValueError('Visa PDF changed: review page selection before extracting.')
        reader = PdfReader(ROOT / source['path'])
        if reader.is_encrypted:
            raise ValueError('Encrypted PDF requires review.')
        texts = [page.extract_text() or '' for page in reader.pages]
        if not any('June 2024' in text for text in texts[:6]):
            raise ValueError('Expected Visa June 2024 edition not confirmed.')
        provenance = json.loads((ROOT / source['provenance_path']).read_text())
        if provenance['sha256'] != fingerprint:
            raise ValueError('PDF provenance fingerprint mismatch.')
        blocks = []
        for number, condition in PDF_SELECTION.items():
            text = texts[number - 1]
            if not text.strip():
                raise ValueError(f'No readable text on selected PDF page {number}; review scan/OCR.')
            if number != 41 and f'Condition {condition}' not in text:
                raise ValueError(f'Unexpected condition on PDF page {number}.')
            blocks.append({
                'block_id': f"{source['source_id']}:page-{number}",
                'type': 'pdf_page', 'headings': [source['title'], f'Condition {condition}'],
                'pdf_page': number, 'pdf_page_label': reader.page_labels[number - 1],
                'locator': f"{source['url']}#page={number}", 'text': text,
                'structure_review_required': False,
                'structure_review': PDF_REVIEW,
            })
        warnings.append('Selected page layout reviewed for this fingerprint; footnotes retained. Other PDF layouts require separate review.')
        warnings.append('Only selected pages 40, 41, 42 and 48 included; other pages intentionally excluded.')
        source = {**source, 'version': 'June 2024 edition; confirmed from extracted text'}
    else:
        raise ValueError(f'Unsupported document type: {kind}')
    for block in blocks:
        block['raw_text'] = block['text']
        block['text'] = clean_text(block['text'], pdf=kind == 'pdf')
        if kind == 'pdf':
            # Exact fixes verified against the rendered four-page selection.
            if block['pdf_page'] == 42:
                block['text'] = block['text'].replace(
                    'the cardholder’s account was closed.4\n3',
                    'the cardholder’s account was closed. [Footnotes 3 and 4 below]')
            block['text'] = re.sub(r'\n(?:39|45)$', '', block['text'])
            # Split response alternatives as complete units; never split condition from action.
            passages = []
            section = 'How should I respond?' if block['pdf_page'] == 41 else 'Introduction'
            lines = []
            def flush_passage():
                if lines:
                    passages.append({'passage_id': f"{block['block_id']}:passage-{len(passages)+1}",
                                     'section': section, 'text': '\n'.join(lines).strip(),
                                     'locator': block['locator']})
                    lines.clear()
            for line in block['text'].splitlines():
                if line in ('Why did I get this notification?', 'What caused the dispute?',
                            'How should I respond?', 'How to avoid this dispute in the future'):
                    flush_passage()
                    section = line
                elif section == 'How should I respond?' and line.startswith('– '):
                    flush_passage()
                    lines.append(line)
                else:
                    lines.append(line)
            flush_passage()
            block['passages'] = passages
    return {'source': source, 'source_sha256': fingerprint,
            'blocks': blocks, 'warnings': warnings}


def main():
    manifest = json.loads((ROOT / 'data/source-manifest.json').read_text())
    output = ROOT / 'data/parsed'
    output.mkdir(parents=True, exist_ok=True)
    report = []
    failures = 0
    for source in manifest['sources']:
        try:
            record = parse_source(source)
            (output / f"{source['source_id']}.json").write_text(
                json.dumps(record, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
            print(f"PARSED {source['source_id']}: {len(record['blocks'])} blocks")
            report.append({'source_id': source['source_id'], 'status': 'parsed',
                           'blocks': len(record['blocks']), 'warnings': record['warnings']})
        except Exception as error:
            failures += 1
            # Do not leave stale successful output for a failed source.
            (output / f"{source['source_id']}.json").unlink(missing_ok=True)
            report.append({'source_id': source['source_id'], 'status': 'failed', 'error': str(error)})
            print(f"FAILED {source['source_id']}: {error}")
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f'Parsed records saved locally to data/parsed. Failures: {failures}.')
    print('No embeddings, indexing, model calls or GitHub sync performed.')
    raise SystemExit(1 if failures else 0)


if __name__ == '__main__':
    main()
