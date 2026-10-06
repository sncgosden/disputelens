"""Download and register selected additional official sources; no model calls."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]


def main():
    selected = json.loads((ROOT / 'data/expansion-sources.json').read_text())['sources']
    manifest_path = ROOT / 'data/source-manifest.json'
    manifest = json.loads(manifest_path.read_text())
    report = []
    for spec in selected:
        directory = ROOT / 'data/raw' / spec['source_id']
        raw_path = directory / ('source.pdf' if spec['document_type'] == 'pdf' else 'source.html')
        provenance_path = directory / 'provenance.json'
        if raw_path.exists() and provenance_path.exists():
            provenance = json.loads(provenance_path.read_text())
            if hashlib.sha256(raw_path.read_bytes()).hexdigest() != provenance['sha256']:
                raise SystemExit(f"Existing snapshot fingerprint mismatch: {spec['source_id']}")
        else:
            with httpx.Client(timeout=120, follow_redirects=True) as client:
                response = client.get(spec['url'], headers={'User-Agent': 'DisputeLens-learning-project/0.1',
                    'Accept': 'application/pdf' if spec['document_type'] == 'pdf' else 'text/html'})
                response.raise_for_status()
            content = response.content
            if spec['document_type'] == 'pdf' and not content.startswith(b'%PDF-'):
                raise SystemExit('Expected a PDF, received another format.')
            if spec['document_type'] == 'html' and b'<html' not in content.lower():
                raise SystemExit('Expected HTML; review response.')
            provenance = {**spec, 'requested_url': spec['url'], 'resolved_url': str(response.url),
                'fetched_at_utc': datetime.now(timezone.utc).isoformat(),
                'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content),
                'content_type': response.headers.get('content-type'),
                'last_modified': response.headers.get('last-modified')}
            directory.mkdir(parents=True, exist_ok=True)
            raw_path.write_bytes(content)
            provenance_path.write_text(json.dumps(provenance, indent=2) + '\n')
        record = {**spec, 'path': str(raw_path.relative_to(ROOT)),
            'provenance_path': str(provenance_path.relative_to(ROOT)), 'corpus': 'real',
            'status': 'snapshot', 'effective_date': None,
            'version': 'snapshot-' + provenance['fetched_at_utc'][:10],
            'authority': (spec['provider'] or spec['scheme']) + ' official public guidance',
            'scope': spec['title'] + '; preserve regional and effective-date qualifications'}
        selectors = {'adyen-dispute-flow': 'article[data-element="article"]',
                     'adyen-visa-chargebacks': 'article[data-element="article"]',
                     'square-uk-disputes': '#article-body',
                     'paypal-uk-seller-protection': 'section.section-wrapper'}
        if spec['document_type'] == 'html':
            record['article_selector'] = selectors[spec['source_id']]
        if spec['source_id'] == 'mastercard-chargeback-guide':
            record['version'] = '13 May 2025 edition'
            record['publication_date'] = '2025-05-13'
        manifest['sources'] = [s for s in manifest['sources'] if s['source_id'] != spec['source_id']] + [record]
        report.append({'source_id': spec['source_id'], 'bytes': provenance['bytes'], 'status': 'downloaded'})
        print(f"SAVED {spec['source_id']}: {provenance['bytes']:,} bytes")
        # Save each success: a later failed download does not hide completed work.
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    visa = next(s for s in manifest['sources'] if s['source_id'] == 'visa-dispute-management-june-2024')
    visa['scope'] = 'Full Visa Dispute Management Guidelines; all PDF pages'
    visa.pop('selected_conditions', None)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    (ROOT / 'data/raw/expansion-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Registered three additional providers and Mastercard; Visa scope expanded to all pages.')


if __name__ == '__main__':
    main()
