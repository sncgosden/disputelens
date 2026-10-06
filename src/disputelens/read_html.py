"""Inspect structured article text from the saved Stripe HTML."""

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def read_article(source: dict, root: Path = PROJECT_ROOT) -> dict:
    raw = (root / source['path']).read_bytes()
    provenance = json.loads((root / source['provenance_path']).read_text())
    if hashlib.sha256(raw).hexdigest() != provenance['sha256']:
        raise ValueError('HTML differs from its saved download fingerprint.')
    soup = BeautifulSoup(raw, 'html.parser')
    article = soup.select_one('article#content')
    if article is None:
        raise ValueError('Expected article#content not found; review page structure.')
    for noise in article.select('script, style, nav, button, noscript, svg'):
        noise.decompose()
    base_url = provenance['resolved_url']
    headings = []
    anchor = None
    blocks = []
    for node in article.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li', 'table']):
        # A table is one unit; preserve its rows rather than duplicating inner text.
        if node.find_parent('table'):
            continue
        if node.name.startswith('h') and node.name[1:].isdigit():
            level = int(node.name[1])
            while headings and headings[-1][0] >= level:
                headings.pop()
            heading_text = node.get_text(' ', strip=True)
            headings.append((level, heading_text))
            anchor = node.get('id') or anchor
            continue
        # Lists may contain paragraphs and nested lists: emit each item's own text once.
        if node.name == 'p' and node.find_parent('li'):
            continue
        links = [
            {'text': link.get_text(' ', strip=True), 'url': urljoin(base_url, link['href'])}
            for link in node.find_all('a', href=True)
            if link.find_parent('li') is node or node.name != 'li'
        ]
        if node.name == 'table':
            rows = [[cell.get_text(' ', strip=True) for cell in row.find_all(['th', 'td'], recursive=False)]
                    for row in node.find_all('tr')]
            text = '\n'.join(' | '.join(row) for row in rows if row)
        elif node.name == 'li':
            copy = BeautifulSoup(str(node), 'html.parser').find('li')
            for nested in copy.find_all(['ul', 'ol']):
                nested.decompose()
            text = copy.get_text(' ', strip=True)
            rows = None
        else:
            text = node.get_text(' ', strip=True)
            rows = None
        if not text:
            continue
        block = {
            'block_id': f"{source['source_id']}:block-{len(blocks) + 1}",
            'type': {'li': 'list_item', 'p': 'paragraph', 'table': 'table'}[node.name],
            'headings': [title for _, title in headings],
            'locator': base_url + ('#' + anchor if anchor else ''),
            'text': text,
            'links': links,
        }
        if rows is not None:
            block['rows'] = rows
        blocks.append(block)
    if not blocks:
        raise ValueError('No article text extracted; review the saved HTML.')
    return {'source': dict(source), 'blocks': blocks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--heading', help='Display only blocks matching a heading')
    args = parser.parse_args()
    manifest = json.loads((PROJECT_ROOT / 'data/source-manifest.json').read_text())
    source = next(s for s in manifest['sources'] if s['source_id'] == 'stripe-respond-to-disputes')
    try:
        result = read_article(source)
    except (OSError, ValueError) as error:
        parser.exit(1, f'HTML extraction failed: {error}\n')
    blocks = result['blocks']
    if args.heading:
        blocks = [b for b in blocks if any(args.heading.lower() in h.lower() for h in b['headings'])]
        if not blocks:
            parser.error('No matching heading; try without --heading.')
    print(json.dumps({'source': result['source'], 'blocks': blocks}, indent=2, ensure_ascii=False))
    print(f"\nREAD: {len(blocks)} displayed blocks; {len(result['blocks'])} total article blocks.")
    print('Inspection only: no files changed, indexing or model calls.')


if __name__ == '__main__':
    main()
