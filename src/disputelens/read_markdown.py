"""Read policy Markdown into sections with source metadata (no model calls)."""

import argparse
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def read_policy(source: dict, root: Path = PROJECT_ROOT) -> dict:
    """Preserve heading hierarchy and paragraph text; separate header metadata."""
    text = (root / source['path']).read_text(encoding='utf-8')
    sections = []
    headings = []
    lines = []
    start_line = None
    in_header = True
    metadata_labels = ('Source ID:', 'Version:', 'Effective date:', 'Status:',
                       'Authority:', 'Scope:')

    def flush():
        if lines and any(line.strip() for line in lines):
            sections.append({
                'section_id': f"{source['source_id']}:section-{len(sections) + 1}",
                'headings': [heading for _, heading in headings],
                'start_line': start_line,
                'text': '\n'.join(lines).strip(),
            })
        lines.clear()

    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        prefix = len(line) - len(line.lstrip('#'))
        is_heading = 1 <= prefix <= 6 and line[prefix:prefix + 1] == ' '
        if is_heading:
            flush()
            while headings and headings[-1][0] >= prefix:
                headings.pop()
            headings.append((prefix, line[prefix:].strip()))
            start_line = number + 1
            if prefix > 1:
                in_header = False
            continue
        if in_header and stripped.startswith(metadata_labels):
            continue
        if stripped:
            in_header = False
        if not lines and stripped:
            start_line = number
        lines.append(line)
    flush()
    if not sections:
        raise ValueError(f"No policy text found: {source['path']}")
    return {'source': dict(source), 'sections': sections}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default='delivery-policy', help='Manifest source ID')
    args = parser.parse_args()
    manifest = json.loads((PROJECT_ROOT / 'data/source-manifest.json').read_text())
    matches = [source for source in manifest['sources'] if source['source_id'] == args.source]
    if len(matches) != 1 or matches[0]['document_type'] != 'markdown':
        parser.error('Choose exactly one Markdown source ID from the manifest.')
    try:
        result = read_policy(matches[0])
    except (OSError, ValueError) as error:
        parser.exit(1, f'Read failed: {error}\n')
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nREAD: {len(result['sections'])} sections. No files changed or model calls made.")


if __name__ == '__main__':
    main()
