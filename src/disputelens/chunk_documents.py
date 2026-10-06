"""Build heading-aware chunks without splitting reviewed evidence blocks."""

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def make_chunks(document: dict, target_words: int = 400, overlap_words: int = 0) -> list[dict]:
    if target_words < 1:
        raise ValueError('Chunk word target must be positive.')
    if overlap_words < 0 or overlap_words >= target_words:
        raise ValueError('Overlap must be non-negative and smaller than the word target.')
    config = {'version': '1.1' if overlap_words else '1.0', 'target_words': target_words,
              'boundaries': 'heading-path', 'split_evidence_blocks': False,
              'overlap_words': overlap_words}
    config_hash = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    chunks = []
    pending = []
    current_headings = None

    def flush():
        if not pending:
            return
        heading = ' > '.join(current_headings)
        text = heading + '\n\n' + '\n\n'.join(b['text'] for b in pending)
        passage_ids = [b['passage_id'] for b in pending]
        identity = json.dumps([document['parent_id'], document['source_sha256'],
                               config_hash, passage_ids, text], ensure_ascii=False)
        chunk_id = document['parent_id'] + ':chunk-' + hashlib.sha256(identity.encode()).hexdigest()[:20]
        chunks.append({
            'chunk_id': chunk_id,
            'parent_id': document['parent_id'],
            'source_sha256': document['source_sha256'],
            'config_sha256': config_hash,
            'config': config,
            'metadata': document['metadata'],
            'headings': list(current_headings),
            'text': text,
            'word_count': len(text.split()),
            'exceeds_target': len(text.split()) > target_words,
            'passage_ids': passage_ids,
            # Retain the exact evidence blocks: table rows, links and locators survive.
            'evidence': list(pending),
        })
        pending.clear()

    for block in document['blocks']:
        headings = tuple(block['headings'])
        if pending and headings != current_headings:
            flush()
        current_headings = headings
        proposed_words = (len(' > '.join(headings).split())
                          + sum(len(b['text'].split()) for b in pending)
                          + len(block['text'].split()))
        if pending and proposed_words > target_words:
            carry = []
            carried_words = 0
            for previous in reversed(pending):
                size = len(previous['text'].split())
                if carried_words + size > overlap_words:
                    break
                carry.insert(0, previous)
                carried_words += size
            flush()
            # Keep overlap only when it fits beside the next complete block.
            while carry and (len(' > '.join(headings).split())
                             + sum(len(b['text'].split()) for b in carry)
                             + len(block['text'].split()) > target_words):
                carry.pop(0)
            pending.extend(carry)
        pending.append(block)
    flush()
    # Link only inside this document/configuration, never into another policy.
    for index, chunk in enumerate(chunks):
        chunk['previous_chunk_id'] = chunks[index - 1]['chunk_id'] if index else None
        chunk['next_chunk_id'] = chunks[index + 1]['chunk_id'] if index + 1 < len(chunks) else None
    return chunks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--words', type=int, default=400)
    parser.add_argument('--overlap', type=int, default=0, help='Maximum overlap words in complete blocks')
    parser.add_argument('--expanded', action='store_true')
    args = parser.parse_args()
    if args.words < 1:
        parser.error('--words must be positive.')
    if args.overlap < 0 or args.overlap >= args.words:
        parser.error('--overlap must be non-negative and smaller than --words.')
    suffix_dir = '-expanded' if args.expanded else ''
    normalized_path = ROOT / ('data/normalized' + suffix_dir) / 'documents.json'
    data = json.loads(normalized_path.read_text())
    manifest_path = ROOT / 'data/source-manifest.json'
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != data['manifest_sha256']:
        parser.exit(1, 'Manifest changed. Normalize documents again before chunking.\n')
    for document in data['documents']:
        raw_path = ROOT / document['metadata']['path']
        if hashlib.sha256(raw_path.read_bytes()).hexdigest() != document['source_sha256']:
            parser.exit(1, f"Source changed: {document['parent_id']}. Parse and normalize again.\n")
    chunks = [c for d in data['documents'] for c in make_chunks(d, args.words, args.overlap)]
    expected = [b['passage_id'] for d in data['documents'] for b in d['blocks']]
    actual = [p for c in chunks for p in c['passage_ids']]
    first_occurrences = list(dict.fromkeys(actual))
    if first_occurrences != expected or len({c['chunk_id'] for c in chunks}) != len(chunks):
        parser.exit(1, 'Chunk coverage or unique-ID check failed.\n')
    output = ROOT / ('data/chunks' + suffix_dir)
    output.mkdir(parents=True, exist_ok=True)
    suffix = f'-overlap-{args.overlap}' if args.overlap else ''
    filename = output / f'chunks-{args.words}{suffix}.json'
    filename.write_text(json.dumps({
        'schema_version': '1.0',
        'normalized_sha256': hashlib.sha256(normalized_path.read_bytes()).hexdigest(),
        'chunks': chunks,
    }, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'SAVED: {len(chunks)} chunks from {len(data["documents"])} documents.')
    print(f'PASS: all {len(expected)} evidence blocks retained, in source order.')
    print(f'Word target: {args.words}; oversized intact blocks: {sum(c["exceeds_target"] for c in chunks)}.')
    print(f'Overlap ceiling: {args.overlap} words; repeated block occurrences: {len(actual) - len(expected)}.')
    print(f'Output: {filename.relative_to(ROOT)}')
    print('Parent and previous/next links retained within each source document.')
    print('No embeddings, model calls, indexing or GitHub sync.')


if __name__ == '__main__':
    main()
