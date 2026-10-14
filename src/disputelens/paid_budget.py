"""Persistent conservative reservations, shared across invocations of a budget."""
import fcntl
import json
from pathlib import Path

from .client import ModelError
from .build_index import digest
from .embed_batch import write_json


def token_cost(inputs, outputs, pricing):
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in (inputs, outputs)):
        raise ModelError('Token counts must be nonnegative integers.')
    return (inputs * pricing['input_usd_per_million'] +
            outputs * pricing['output_usd_per_million']) / 1_000_000


def reserve_entry(budget, attempt_id, prompt_sha, model, max_tokens):
    if model != budget['model'] or max_tokens != budget['max_output_tokens']:
        raise ModelError('Model or output allowance differs from budget.')
    job = next((j for j in budget['jobs'] if j['prompt_sha256'] == prompt_sha), None)
    if job is None:
        raise ModelError('Prompt is outside the counted budget.')
    reservations = budget['reservations']
    if attempt_id in reservations:
        raise ModelError('Attempt already reserved; no automatic retry or budget reset.')
    if len(reservations) >= budget['max_calls']:
        raise ModelError('Paid request count limit reached.')
    reserved = sum(r['reserved_usd'] for r in reservations.values())
    allowance = job['reserved_usd']
    if reserved + allowance > budget['max_usd'] + 1e-12:
        raise ModelError('Conservative budget allowance would be exceeded.')
    reservations[attempt_id] = {'status': 'reserved', 'reserved_usd': allowance,
                                'prompt_sha256': prompt_sha}
    return budget


def reserve_paid_request(path, attempt_id, prompt_sha, model, max_tokens):
    path = Path(path)
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        budget = json.loads(path.read_text())
        if budget['identity']['pricing_sha256'] != digest('data/claude-pricing.json'):
            raise ModelError('Pricing changed after budget preparation; recount before execution.')
        reserve_entry(budget, attempt_id, prompt_sha, model, max_tokens)
        write_json(path, budget)
