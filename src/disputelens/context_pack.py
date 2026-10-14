"""Construct cited evidence from retrieved units; no gold or model access."""
import copy
import json

from .client import ModelError
from .section_scope import section_applicable


def merge_evidence(pieces):
    """Merge touching/overlapping spans, checking overlapping source characters."""
    output = []
    by_passage = {}
    for piece in pieces:
        by_passage.setdefault(piece['passage_id'], []).append(piece)
    for passage_id, fragments in by_passage.items():
        fragments.sort(key=lambda e: (e['evidence_character_start'], e['evidence_character_end']))
        merged = []
        for original in fragments:
            piece = copy.deepcopy(original)
            start, end = piece['evidence_character_start'], piece['evidence_character_end']
            length = piece['original_evidence_characters']
            if not 0 <= start < end <= length or len(piece['text']) != end - start:
                raise ModelError('Context evidence has invalid character spans.')
            if merged:
                previous = merged[-1]
                if (previous['locator'] != piece['locator']
                        or previous['original_evidence_characters'] != length):
                    raise ModelError('Context fragments have inconsistent provenance.')
                right = previous['evidence_character_end']
                if start <= right:
                    overlap_end = min(right, end)
                    offset = start - previous['evidence_character_start']
                    if previous['text'][offset:offset + overlap_end - start] != piece['text'][:overlap_end - start]:
                        raise ModelError('Overlapping evidence characters disagree.')
                    if end > right:
                        previous['text'] += piece['text'][right - start:]
                        previous['evidence_character_end'] = end
                    previous['complete_evidence'] = (previous['evidence_character_start'] == 0
                        and previous['evidence_character_end'] == length)
                    continue
            piece['complete_evidence'] = start == 0 and end == length
            merged.append(piece)
        output.extend(merged)
    return output


def render_context(groups):
    sections = []
    sources = {}
    previous_section = None
    for group in groups:
        source = group['metadata']
        source_key = (source['source_id'], group['source_sha256'])
        if source_key not in sources:
            label = f'SOURCE{len(sources) + 1}'
            sources[source_key] = label
            sections.append(f'[{label}] ' + source['title'] + '\n'
                            + json.dumps({key: source.get(key) for key in (
                                'source_id', 'provider', 'scheme', 'region', 'version',
                                'status', 'effective_date', 'publication_date')}, ensure_ascii=False)
                            + '\nURL: ' + str(source.get('url', '')))
        label = sources[source_key]
        sections.append(f'EXTRACT GROUP FROM {label}; retrieval ranks: '
                        + ','.join(str(rank) for rank in group['retrieval_ranks']))
        for evidence in group['evidence']:
            section_key = (source_key, tuple(evidence['headings']))
            if section_key != previous_section:
                # Full paths remain available, but not repeated for every paragraph.
                path = evidence['headings']
                if path and path[0] == source['title']:
                    path = path[1:]
                sections.append('SECTION: ' + ' > '.join(path))
                previous_section = section_key
            locator = evidence['locator']
            if locator.get('pdf_page') is not None:
                location = f'PDF page {locator["pdf_page"]}'
                if (locator.get('pdf_page_label') is not None
                        and str(locator['pdf_page_label']) != str(locator['pdf_page'])):
                    location += f'; printed page {locator["pdf_page_label"]}'
            elif locator.get('start_line') is not None:
                location = f'line {locator["start_line"]}'
            else:
                location = str(locator['reference'])
            sections.append(f'[{evidence["citation_id"]}] {location}; '
                + f'chars {evidence["evidence_character_start"]}:{evidence["evidence_character_end"]}; '
                + ('complete' if evidence['complete_evidence'] else 'partial')
                + '\n' + evidence['text'])
    return '\n\n'.join(sections)


def build_context(results, filters, scopes, max_words=6000):
    """Budget intact groups in search-rank order; merge only retrieved neighbours.

    This word budget is an inspectable planning cap, not a model-token check.
    The eventual generation runner must count its complete prompt per model.
    """
    if isinstance(max_words, bool) or not isinstance(max_words, int) or max_words < 1:
        raise ModelError('Context word budget must be a positive integer.')
    ids = [r['unit']['chunk_id'] for r in results]
    if len(ids) != len(set(ids)) or [r['rank'] for r in results] != list(range(1, len(results) + 1)):
        raise ModelError('Context requires unique candidates with consecutive retrieval ranks.')
    parents = {}
    for result in results:
        unit = result['unit']
        if not section_applicable(unit, filters, scopes):
            raise ModelError('Context candidate failed section applicability.')
        parent = unit['parent_chunk_id']
        entry = parents.setdefault(parent, {'metadata': unit['metadata'],
            'source_sha256': unit['source_sha256'], 'headings': unit['headings'],
            'previous': unit['previous_chunk_id'], 'next': unit['next_chunk_id'],
            'ranks': [], 'units': [], 'evidence': []})
        if any(entry[key] != unit[key] for key in ('metadata', 'source_sha256', 'headings')):
            raise ModelError('Parent search fragments have inconsistent provenance.')
        entry['ranks'].append(result['rank'])
        entry['units'].append(unit['chunk_id'])
        entry['evidence'].extend(unit['evidence'])
    # Join only mutually linked neighbours with identical source/heading scope.
    links = {}
    for parent, entry in parents.items():
        following = entry['next']
        if following in parents:
            other = parents[following]
            if (other['previous'] == parent and entry['metadata'] == other['metadata']
                    and entry['headings'] == other['headings']
                    and entry['source_sha256'] == other['source_sha256']):
                links[parent] = following
    incoming = set(links.values())
    groups, visited = [], set()
    for first in parents:
        if first in incoming:
            continue
        chain, parent = [], first
        while parent is not None:
            if parent in visited:
                raise ModelError('Retrieved parent links contain a cycle.')
            visited.add(parent)
            chain.append(parent)
            parent = links.get(parent)
        entries = [parents[p] for p in chain]
        evidence = merge_evidence([e for entry in entries for e in entry['evidence']])
        for e in evidence:
            if e['passage_id'] in scopes:
                e['headings'] = scopes[e['passage_id']]['heading_path']
        groups.append({'parent_chunk_ids': chain,
            'unit_ids': [uid for entry in entries for uid in entry['units']],
            'retrieval_ranks': sorted(rank for entry in entries for rank in entry['ranks']),
            'metadata': entries[0]['metadata'], 'source_sha256': entries[0]['source_sha256'],
            'evidence': evidence})
    if len(visited) != len(parents):
        raise ModelError('Retrieved parent links contain an unresolved cycle.')
    groups.sort(key=lambda group: min(group['retrieval_ranks']))
    selected, omitted = [], []
    next_citation = 1
    for group in groups:
        for n, evidence in enumerate(group['evidence'], next_citation):
            evidence['citation_id'] = f'S{n:03d}'
        trial = selected + [group]
        if len(render_context(trial).split()) <= max_words:
            selected.append(group)
            next_citation += len(group['evidence'])
        else:
            omitted.append({'unit_ids': group['unit_ids'], 'retrieval_ranks': group['retrieval_ranks'],
                            'reason': 'intact retrieved-neighbour group exceeds remaining word budget'})
    text = render_context(selected)
    citations = {e['citation_id']: {'passage_id': e['passage_id'], 'locator': e['locator'],
                   'source_sha256': group['source_sha256'],
                   'character_start': e['evidence_character_start'],
                   'character_end': e['evidence_character_end'],
                   'complete_evidence': e['complete_evidence']}
                 for group in selected for e in group['evidence']}
    return {'schema_version': '1.0', 'trusted_settings': filters,
            'budget': {'kind': 'words_in_rendered_context', 'maximum': max_words,
                       'used': len(text.split()), 'model_token_check_pending': True},
            'input_units': len(results), 'included_units': sum(len(g['unit_ids']) for g in selected),
            'groups': selected, 'omitted_groups': omitted, 'citations': citations, 'text': text,
            'limitations': 'No answerability or conflict-resolution claim; no unretrieved neighbour expansion.'}
