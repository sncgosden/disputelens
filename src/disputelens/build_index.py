"""Resumable local embeddings and persistent Qdrant indexing."""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from .client import ModelError, configured_models
from .embed_batch import loaded_embedding_model, safe_error, write_json


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked_vectors(vectors, rows, dimension):
    array = np.asarray(vectors, dtype=float)
    if (array.shape != (rows, dimension) or not np.isfinite(array).all()
            or (np.linalg.norm(array, axis=1) == 0).any()):
        raise ModelError('Cached or returned vectors have invalid dimensions or values.')
    return array


def index_units(units, embed, client, directory, identity, dimension, batch_size=16):
    """Cache each successful batch before upsert; repeat upserts safely on resume."""
    if not 1 <= batch_size <= 64:
        raise ModelError('Batch size must be between 1 and 64.')
    if not units or len({u['chunk_id'] for u in units}) != len(units):
        raise ModelError('Search units must be non-empty and have unique IDs.')
    run_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    collection = 'disputelens_' + run_id[:24]
    cache = directory / 'embedding-cache' / run_id
    names = {c.name for c in client.get_collections().collections}
    if collection not in names:
        client.create_collection(collection, vectors_config=VectorParams(size=dimension, distance=Distance.COSINE))
    else:
        settings = client.get_collection(collection).config.params.vectors
        if settings.size != dimension or settings.distance != Distance.COSINE:
            raise ModelError('Existing collection does not match the embedding configuration.')
    reused, embedded = 0, 0
    for start in range(0, len(units), batch_size):
        batch = units[start:start+batch_size]
        ids = [u['chunk_id'] for u in batch]
        # Identify the exact batch; resume using the same batch size to reuse it.
        batch_key = hashlib.sha256(json.dumps(ids).encode()).hexdigest()
        path = cache / (batch_key + '.json')
        if path.exists():
            saved = json.loads(path.read_text())
            if saved['identity'] != identity or saved['chunk_ids'] != ids:
                raise ModelError('Embedding cache does not match this corpus and model.')
            vectors = checked_vectors(saved['vectors'], len(batch), dimension)
            reused += len(batch)
        else:
            print(f'Embedding {start+1}–{start+len(batch)} of {len(units)}...', flush=True)
            vectors = checked_vectors(embed([u['text'] for u in batch]), len(batch), dimension)
            write_json(path, {'identity': identity, 'chunk_ids': ids, 'vectors': vectors.tolist()})
            embedded += len(batch)
        client.upsert(collection, points=[PointStruct(
            id=str(uuid5(NAMESPACE_URL, run_id + ':' + unit['chunk_id'])),
            vector=vector.tolist(), payload=unit) for unit, vector in zip(batch, vectors)], wait=True)
        print(f'STORED: {start+len(batch)}/{len(units)}; reused embeddings: {reused}.', flush=True)
    count = client.count(collection, exact=True).count
    if count != len(units):
        raise ModelError(f'Index has {count} points; expected {len(units)}.')
    result = {**identity, 'collection_name': collection, 'points': count,
              'new_embeddings_this_run': embedded, 'cached_embeddings_this_run': reused,
              'qdrant_path': str(directory / 'qdrant'),
              'status': 'complete', 'distance': 'cosine'}
    write_json(directory / 'index-manifest.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch-size', type=int, default=16)
    args = parser.parse_args()
    models, qdrant = configured_models(), None
    try:
        import lmstudio as lms
        config = json.loads(Path('data/pipeline-config.json').read_text())
        units_path = Path(config['embedding_units_path'])
        data = json.loads(units_path.read_text())
        trial = json.loads(Path('data/indexes/embedding-trial.json').read_text())
        fingerprint = digest(units_path)
        model_id = os.getenv('LM_EMBEDDING_MODEL')
        prefix = os.getenv('EMBED_DOCUMENT_PREFIX', 'search_document: ')
        if (model_id != data['model'] or model_id != trial['model']
                or prefix != data['document_prefix'] or prefix != trial['document_prefix']
                or fingerprint != trial['embedding_units_sha256']):
            raise ModelError('Model, prefix or search units changed. Run embed_batch again first.')
        if digest(data['source_chunk_path']) != data['source_chunks_sha256']:
            raise ModelError('Original chunks changed. Rebuild the embedding trial first.')
        if os.getenv('LM_API_TOKEN'):
            raise ModelError('The pinned SDK does not support authenticated token checking.')
        from urllib.parse import urlparse
        if urlparse(models.base).hostname not in ('localhost', '127.0.0.1', '::1'):
            raise ModelError('This indexing step requires LM Studio on this Mac.')
        limit = loaded_embedding_model(lms, model_id).get_context_length()
        units = data['chunks']
        if any(u['embedding_tokens'] + 8 > limit for u in units):
            raise ModelError('Loaded input limit is now too small. Run embed_batch again.')
        dimension = trial['dimension']
        identity = {'schema_version': '1.0', 'embedding_units_path': str(units_path),
                    'embedding_units_sha256': fingerprint, 'model': model_id,
                    'document_prefix': prefix, 'dimension': dimension}
        directory = Path('data/indexes')
        qdrant = QdrantClient(path=str(directory / 'qdrant'))
        print(f'LOCAL INDEX: {len(units)} units; {model_id}; {dimension} dimensions.', flush=True)
        started = time.perf_counter()
        result = index_units(units, models.embed, qdrant, directory, identity, dimension, args.batch_size)
        print(f'PASS: {result["points"]} searchable points stored in local Qdrant.')
        print(f'Seconds: {time.perf_counter()-started:.1f}')
        print('SAVED: data/indexes/index-manifest.json')
        print('Sources, evidence spans and parent links retained. Retrieval quality is not yet evaluated.')
        print('No chat models, Claude calls or GitHub sync.')
    except KeyboardInterrupt:
        print('\nStopped. Run the same command to resume completed batches.', file=sys.stderr)
        return 1
    except Exception as error:
        print(f'STOP: {safe_error(error)}', file=sys.stderr)
        print('Completed batches are saved. Fix the cause and run the same command to resume.', file=sys.stderr)
        return 1
    finally:
        if qdrant is not None:
            qdrant.close()
        models.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
