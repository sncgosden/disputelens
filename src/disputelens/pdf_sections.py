"""Preserve publisher PDF bookmark hierarchy without changing evidence text."""
import re


def normalized_heading(text):
    return re.sub(r'\s+', ' ', text).strip().casefold()


def contains_heading(text, title):
    """Match standalone headings, including up to three wrapped PDF lines."""
    lines = [normalized_heading(line) for line in text.splitlines() if line.strip()]
    target = normalized_heading(title)
    return any(' '.join(lines[start:start + size]) == target
               for start in range(len(lines)) for size in (1, 2, 3))


def bookmark_sections(reader):
    events = []

    def walk(items, parents):
        last_path = parents
        for item in items:
            if isinstance(item, list):
                walk(item, last_path)
                continue
            title = str(item.get('/Title', '')).strip()
            last_path = parents + ([title] if title else [])
            page = reader.get_destination_page_number(item)
            if title and page is not None and page >= 0:
                events.append({'page': page + 1, 'title': title, 'path': last_path})

    walk(reader.outline, [])
    return sorted(events, key=lambda event: event['page'])


def apply_section_headings(blocks, events, document_title):
    """Use textual bookmark boundaries within pages and carry hierarchy forward.

    Unmatched boundaries are reported; no table reconstruction or text edits.
    """
    by_page = {}
    for event in events:
        by_page.setdefault(event['page'], []).append(event)
    page_blocks = {}
    for block in blocks:
        page_blocks.setdefault(block['pdf_page'], []).append(block)
    active = []
    unmatched = []
    previous_page = 0
    for page, records in sorted(page_blocks.items()):
        # A section's bookmark remains authoritative on following pages even if
        # its title was not recognized in the extracted start-page text.
        for event in events:
            if previous_page <= event['page'] < page:
                active = event['path']
        boundaries = by_page.get(page, [])
        matched = set()
        for block in records:
            found = [(index, event) for index, event in enumerate(boundaries)
                     if index not in matched and contains_heading(block['text'], event['title'])]
            if found:
                index, event = found[-1]
                active = event['path']
                matched.update(index for index, _ in found)
            if active:
                block['headings'] = [document_title, *active]
                block['heading_provenance'] = 'publisher_pdf_bookmarks'
        unmatched.extend({'page': page, 'title': event['title']}
                         for index, event in enumerate(boundaries) if index not in matched)
        previous_page = page
    return {'bookmark_count': len(events), 'unmatched_text_boundaries': unmatched,
            'note': 'Bookmark hierarchy preserves sections; unmatched within-page boundaries require review.'}
