"""Audit actual embedding input sizes before a three-passage local trial."""
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from .client import ModelError, configured_models
from .embedding_units import make_embedding_units


def safe_error(error):
    """Keep the useful SDK error while removing configured credentials."""
    message = str(error)
    for name in ('LM_API_TOKEN', 'ANTHROPIC_API_KEY'):
        secret = os.getenv(name)
        if secret:
            message = message.replace(secret, '[redacted]')
    message = re.sub(r'(?i)(bearer\s+)\S+', r'\1[redacted]', message)
    return f'{type(error).__name__}: {message[:800]}'


def audit_chunks(chunks, tokenizer, context_length, prefix, progress=None):
    """Count the exact submitted text; reserve eight tokens for runtime framing."""
    if not isinstance(context_length, int) or context_length <= 8:
        raise ModelError('The embedding model did not report a usable context limit.')
    rows = []
    for index, chunk in enumerate(chunks, 1):
        text = chunk['text']
        if not isinstance(text, str) or not text.strip():
            raise ModelError(f"Empty chunk: {chunk['chunk_id']}")
        count = len(tokenizer(prefix + text))
        rows.append({'chunk_id': chunk['chunk_id'], 'tokens': count,
                     'fits': count + 8 <= context_length,
                     'exceeds_word_target': chunk['exceeds_target']})
        if progress and (index % 100 == 0 or index == len(chunks)):
            progress(index, len(chunks))
    return rows


def select_trial(chunks):
    """Use three real source snapshots or current documents, preserving provenance."""
    selected, parents = [], set()
    for chunk in chunks:
        if (chunk['metadata']['corpus'] == 'real'
                and chunk['metadata']['status'] in ('current', 'snapshot')
                and chunk['parent_id'] not in parents
                and chunk['word_count'] >= 40 and not chunk['exceeds_target']):
            selected.append(chunk)
            parents.add(chunk['parent_id'])
        if len(selected) == 3:
            return selected
    raise ModelError('Need three real source snapshots or current documents for this trial.')


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    temporary.replace(path)


def loaded_embedding_model(sdk, model_id):
    """Discover the local SDK service; do not reuse the HTTP API port or load models."""
    for model in sdk.list_loaded_models('embedding'):
        if model.identifier == model_id:
            return model
    raise ModelError(f'Load the embedding model with API ID {model_id} in LM Studio.')


def main():
    models = configured_models()
    stage = 'importing the LM Studio SDK'
    try:
        import lmstudio as lms
        config = json.loads(Path('data/pipeline-config.json').read_text())
        chunk_path = Path(config['chunk_paths'][0])
        chunk_bytes = chunk_path.read_bytes()
        chunks = json.loads(chunk_bytes)['chunks']
        model_id = os.getenv('LM_EMBEDDING_MODEL')
        if not model_id:
            raise ModelError('Set LM_EMBEDDING_MODEL in .env.')
        address = urlparse(models.base)
        if address.scheme != 'http' or not address.hostname or address.path.rstrip('/') != '/v1':
            raise ModelError('This local trial requires LM_BASE_URL=http://host:port/v1.')
        if address.hostname not in ('localhost', '127.0.0.1', '::1'):
            raise ModelError('This trial uses local SDK discovery; LM_BASE_URL must point to this Mac.')
        stage = 'connecting to LM Studio and selecting the embedding model'
        print(f'Connecting to LM Studio for token checking: {model_id}', flush=True)
        if os.getenv('LM_API_TOKEN'):
            raise ModelError('The pinned LM Studio SDK does not support token authentication. '
                             'We need to update the SDK before this token-checking trial.')
        embedding_model = loaded_embedding_model(lms, model_id)
        stage = 'reading the loaded embedding model input limit'
        limit = embedding_model.get_context_length()
        prefix = os.getenv('EMBED_DOCUMENT_PREFIX', 'search_document: ')
        print(f'Embedding model: {model_id}', flush=True)
        print(f'Loaded input limit: {limit} tokens; framing reserve: 8 tokens.', flush=True)
        print(f'Checking all {len(chunks)} chunks before embedding...', flush=True)
        started = time.perf_counter()
        stage = 'counting chunk tokens'
        rows = audit_chunks(chunks, embedding_model.tokenize, limit, prefix,
                            lambda n, total: print(f'Checked {n}/{total}.', flush=True))
        fingerprint = hashlib.sha256(chunk_bytes).hexdigest()
        oversized = [row for row in rows if not row['fits']]
        audit_path = Path('data/indexes/embedding-input-audit.json')
        write_json(audit_path, {'schema_version': '1.0', 'model': model_id,
            'chunk_path': str(chunk_path), 'chunks_sha256': fingerprint,
            'context_length': limit, 'framing_reserve': 8, 'document_prefix': prefix,
            'checked_chunks': len(rows), 'too_large': len(oversized), 'chunks': rows})
        print(f'SAVED AUDIT: {audit_path}', flush=True)
        if oversized:
            print(f'Creating token-safe pieces for {len(oversized)} oversized chunks...', flush=True)
        stage = 'building token-safe search units'
        units = make_embedding_units(chunks, rows, embedding_model.tokenize, limit, prefix)
        units_path = Path('data/indexes/embedding-units.json')
        write_json(units_path, {'schema_version': '1.0', 'source_chunk_path': str(chunk_path),
            'source_chunks_sha256': fingerprint, 'model': model_id,
            'context_length': limit, 'document_prefix': prefix, 'chunks': units,
            'evaluation_note': 'Partial evidence must be scored by character coverage. '
                               'Do not credit a child unit for its entire parent passage.'})
        units_fingerprint = hashlib.sha256(units_path.read_bytes()).hexdigest()
        print(f'PASS: all {len(units)} search units fit; every original chunk character retained.', flush=True)
        print(f'SAVED SEARCH UNITS: {units_path}', flush=True)
        selected = select_trial(units)
        stage = 'creating the three trial embeddings'
        vectors = models.embed([chunk['text'] for chunk in selected])
        if vectors.shape[0] != len(selected):
            raise ModelError('Embedding response did not match the trial batch.')
        output = Path('data/indexes/embedding-trial.json')
        write_json(output, {'schema_version': '1.0', 'model': model_id,
            'chunks_sha256': fingerprint, 'document_prefix': prefix,
            'embedding_units_path': str(units_path), 'embedding_units_sha256': units_fingerprint,
            'dimension': vectors.shape[1], 'context_length': limit,
            'records': [{'chunk_id': chunk['chunk_id'], 'parent_chunk_id': chunk['parent_chunk_id'],
                         'metadata': chunk['metadata'],
                         'passage_ids': chunk['passage_ids'], 'vector': vector.tolist()}
                        for chunk, vector in zip(selected, vectors)]})
        print(f'Original chunks: {len(rows)}; chunks requiring smaller search units: {len(oversized)}.')
        print(f'PASS: {len(selected)} real passages embedded; dimension: {vectors.shape[1]}.')
        print(f'SAVED: {output}')
        print(f'Seconds: {time.perf_counter() - started:.1f}')
        print('This is an embedding trial. Qdrant indexing and retrieval evaluation come next.')
    except ImportError:
        print('STOP: Install project dependencies with python -m pip install -e ".[dev]".', file=sys.stderr)
        return 1
    except (ModelError, OSError, ValueError, KeyError) as error:
        print(f'STOP: {error}', file=sys.stderr)
        return 1
    except Exception as error:
        print(f'STOP while {stage}: {safe_error(error)}', file=sys.stderr)
        return 1
    finally:
        models.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
