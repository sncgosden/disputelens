"""Extract the expanded corpus, preserving all PDF pages and page provenance."""

import hashlib
import json
import re
from pathlib import Path

from pypdf import PdfReader

from .parse_sources import parse_source
from .read_html import read_article
from .pdf_sections import bookmark_sections, apply_section_headings

ROOT = Path(__file__).resolve().parents[2]


def full_pdf(source):
    raw = ROOT / source['path']
    fingerprint = hashlib.sha256(raw.read_bytes()).hexdigest()
    provenance = json.loads((ROOT / source['provenance_path']).read_text())
    if fingerprint != provenance['sha256']:
        raise ValueError('Source fingerprint mismatch')
    reader = PdfReader(raw)
    if reader.is_encrypted:
        raise ValueError('Encrypted PDF requires review')
    legacy = {}
    if source['source_id'] == 'visa-dispute-management-june-2024':
        for block in parse_source(source)['blocks']:
            legacy.setdefault(block['pdf_page'], []).append(block)
    blocks = []
    empty = []
    for i, page in enumerate(reader.pages, 1):
        if i in legacy:
            blocks.extend(legacy[i])
            continue
        text = page.extract_text(extraction_mode='layout') or ''
        if not text.strip():
            empty.append(i)
            continue
        parts = [part.strip('\n') for part in re.split(r'\n[ \t]*\n', text) if part.strip()]
        title = ' '.join(parts[0].split())[:180] if parts else source['title']
        bounded = []
        for part in parts:
            lines = part.splitlines()
            # Multi-column tables remain intact. Prose can split at complete line
            # boundaries while retaining its original PDF block as the parent.
            table_like = sum(bool(re.search(r'\S {3,}\S',
                re.sub(r'^\s*[•–-]\s+', '', line).strip())) for line in lines) >= 3
            if len(part.split()) <= 180 or table_like:
                bounded.append((part, table_like))
                continue
            pending, words = [], 0
            for line in lines:
                size = len(line.split())
                if pending and words + size > 180:
                    bounded.append(('\n'.join(pending), False))
                    pending, words = [], 0
                pending.append(line)
                words += size
            if pending:
                bounded.append(('\n'.join(pending), False))
        parts = bounded
        # Retain layout spacing in table-like paragraphs. No invented row/column reconstruction.
        for j, (part, table_like) in enumerate(parts, 1):
            heading_match = re.search(r'Condition\s+(\d+\.\d+)', part)
            if heading_match:
                title = 'Condition ' + heading_match.group(1)
            blocks.append({
                'block_id': f"{source['source_id']}:page-{i}:paragraph-{j}",
                'type': 'pdf_paragraph', 'headings': [source['title'], title],
                'pdf_page': i, 'pdf_page_label': reader.page_labels[i - 1],
                'locator': f"{source['url']}#page={i}",
                'text': part, 'raw_text': part,
                'layout_preserved': True,
                'table_like': table_like,
                'structure_review_required': False,
                'structure_review_status': 'spot-check required; layout extraction is not proof of table fidelity',
            })
    if empty:
        raise ValueError(f'No text extracted on PDF pages {empty}; inspect blank/scanned pages before accepting full ingestion.')
    section_audit = None
    if source['source_id'] == 'mastercard-chargeback-guide':
        section_audit = apply_section_headings(blocks, bookmark_sections(reader), source['title'])
    return {'source': source, 'source_sha256': fingerprint, 'blocks': blocks,
            'section_heading_audit': section_audit,
            'warnings': ['Full PDF layout extraction preserves spacing; table/footnote/cross-reference fidelity requires sampling before retrieval experiments.'],
            'page_count': len(reader.pages), 'pages_extracted': len(reader.pages)}


def main():
    manifest = json.loads((ROOT / 'data/source-manifest.json').read_text())
    output = ROOT / 'data/parsed-expanded'
    output.mkdir(parents=True, exist_ok=True)
    report = []
    for source in manifest['sources']:
        try:
            if source['document_type'] == 'pdf':
                record = full_pdf(source)
            elif source['document_type'] == 'html' and source['source_id'] != 'stripe-respond-to-disputes':
                record = read_article(source)
                record['source_sha256'] = hashlib.sha256((ROOT / source['path']).read_bytes()).hexdigest()
                record['warnings'] = []
            else:
                record = parse_source(source)
            (output / (source['source_id'] + '.json')).write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n')
            report.append({'source_id': source['source_id'], 'corpus': source['corpus'],
                           'blocks': len(record['blocks']), 'pages': record.get('page_count'), 'status': 'parsed'})
            print(f"PARSED {source['source_id']}: {len(record['blocks'])} blocks; PDF pages {record.get('page_count', 'n/a')}", flush=True)
        except Exception as error:
            (output / (source['source_id'] + '.json')).unlink(missing_ok=True)
            report.append({'source_id': source['source_id'], 'status': 'failed', 'error': str(error)})
            print(f"FAILED {source['source_id']}: {error}", flush=True)
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    raise SystemExit(1 if any(r['status'] == 'failed' for r in report) else 0)


if __name__ == '__main__':
    main()
