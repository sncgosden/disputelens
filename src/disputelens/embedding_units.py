"""Token-safe search units linked to unchanged source chunks and evidence spans."""
import hashlib
import re

from .client import ModelError


def split_ranges(text, headings, tokenize, limit, prefix, start=0, end=None):
    end = len(text) if end is None else end
    heading_prefix = (' > '.join(headings) + '\n\n') if start else ''
    submitted = heading_prefix + text[start:end]
    if len(tokenize(prefix + submitted)) + 8 <= limit:
        return [(start, end, submitted)]
    if end - start <= 1:
        raise ModelError('Heading or single character cannot fit the embedding input limit.')
    midpoint = (start + end) // 2
    # Prefer paragraph/row boundaries near the midpoint; retain every character.
    candidates = [start + m.end() for m in re.finditer(r'\n+', text[start:end])]
    candidates = [p for p in candidates if start + (end-start)//4 <= p <= end - (end-start)//4]
    if not candidates:
        candidates = [start + m.end() for m in re.finditer(r'\s+', text[start:end])]
        candidates = [p for p in candidates if start < p < end]
    cut = min(candidates, key=lambda p: abs(p-midpoint)) if candidates else midpoint
    return (split_ranges(text, headings, tokenize, limit, prefix, start, cut)
            + split_ranges(text, headings, tokenize, limit, prefix, cut, end))


def make_embedding_units(chunks, audit_rows, tokenize, limit, prefix):
    audited = {row['chunk_id']: row for row in audit_rows}
    if set(audited) != {chunk['chunk_id'] for chunk in chunks}:
        raise ModelError('Token audit does not match the source chunks.')
    units = []
    for chunk in chunks:
        text = chunk['text']
        ranges = ([(0, len(text), text)] if audited[chunk['chunk_id']]['fits']
                  else split_ranges(text, chunk['headings'], tokenize, limit, prefix))
        if ''.join(text[a:b] for a, b, _ in ranges) != text:
            raise ModelError('Embedding unit text-preservation check failed.')
        blocks, cursor = [], len(' > '.join(chunk['headings'])) + 2
        for evidence in chunk['evidence']:
            location = text.find(evidence['text'], cursor)
            if location < 0:
                raise ModelError('Source evidence is missing from its original chunk.')
            blocks.append((evidence, location, location + len(evidence['text'])))
            cursor = location + len(evidence['text'])
        for start, end, submitted in ranges:
            fragments = []
            for evidence, block_start, block_end in blocks:
                left, right = max(start, block_start), min(end, block_end)
                if left >= right:
                    continue
                fragments.append({**evidence, 'text': text[left:right],
                    'evidence_character_start': left-block_start,
                    'evidence_character_end': right-block_start,
                    'original_evidence_characters': block_end-block_start,
                    'complete_evidence': left == block_start and right == block_end})
            identity = f'{chunk["chunk_id"]}:{start}:{end}:{submitted}:{limit}:{prefix}'
            unit_id = chunk['chunk_id'] if len(ranges) == 1 else (
                chunk['parent_id'] + ':unit-' + hashlib.sha256(identity.encode()).hexdigest()[:20])
            units.append({**chunk, 'chunk_id': unit_id,
                'parent_chunk_id': chunk['chunk_id'], 'character_start': start,
                'character_end': end, 'original_chunk_characters': len(text),
                'text': submitted, 'word_count': len(submitted.split()),
                'exceeds_target': len(submitted.split()) > chunk['config']['target_words'],
                'passage_ids': [b['passage_id'] for b in fragments], 'evidence': fragments,
                'embedding_tokens': audited[chunk['chunk_id']]['tokens'] if len(ranges) == 1
                                    else len(tokenize(prefix + submitted)),
                'unit_config': {'version': '1.0', 'context_length': limit,
                                'framing_reserve': 8, 'document_prefix': prefix}})
    for index, unit in enumerate(units):
        unit['previous_chunk_id'] = (units[index-1]['chunk_id'] if index and
                                    units[index-1]['parent_id'] == unit['parent_id'] else None)
        unit['next_chunk_id'] = (units[index+1]['chunk_id'] if index+1 < len(units) and
                                units[index+1]['parent_id'] == unit['parent_id'] else None)
    if any(unit['embedding_tokens'] + 8 > limit for unit in units):
        raise ModelError('A search unit still exceeds the embedding input limit.')
    return units
