"""Restrict Qdrant to section-eligible point IDs before nearest-neighbour cutoff."""
import hashlib
import json
from uuid import NAMESPACE_URL, uuid5

from qdrant_client.models import Filter, HasIdCondition

from .client import ModelError
from .section_scope import section_applicable
from .semantic_search import scope_filter


def index_identity(manifest):
    fields = ('schema_version', 'embedding_units_path', 'embedding_units_sha256',
              'model', 'document_prefix', 'dimension')
    identity = {key: manifest[key] for key in fields}
    run_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    if manifest['collection_name'] != 'disputelens_' + run_id[:24]:
        raise ModelError('Index collection does not match the original stable point-ID contract.')
    return run_id


def point_id(manifest, unit_id):
    return str(uuid5(NAMESPACE_URL, index_identity(manifest) + ':' + unit_id))


def retrieve_scoped(client, manifest, vector, filters, eligible, scopes, top_k=20):
    if not 1 <= top_k <= 50:
        raise ModelError('Choose between 1 and 50 section-scoped results.')
    run_id = index_identity(manifest)
    by_id = {u['chunk_id']: u for u in eligible}
    if len(by_id) != len(eligible):
        raise ModelError('Duplicate section-eligible search units.')
    if any(not section_applicable(u, filters, scopes) for u in eligible):
        raise ModelError('Inapplicable unit entered the vector allowlist.')
    if not eligible:
        return []
    ids = [str(uuid5(NAMESPACE_URL, run_id + ':' + uid)) for uid in by_id]
    query_filter = Filter(must=[scope_filter(**filters), HasIdCondition(has_id=ids)])
    points = client.query_points(manifest['collection_name'], query=vector,
                                 query_filter=query_filter, limit=top_k,
                                 with_payload=True, with_vectors=False).points
    results = []
    for point in points:
        unit = point.payload
        if (not unit or by_id.get(unit.get('chunk_id')) != unit
                or not section_applicable(unit, filters, scopes)):
            raise ModelError('Qdrant result failed the independent section/payload check.')
        results.append({'rank': len(results) + 1, 'similarity': point.score, 'unit': unit})
    return results
