"""Offline evidence routing experiment; not connected to production context packs."""
from .client import ModelError
from .experimental_applicability import decide_applicability


def route_evidence(evidence, reviewed_scopes, trusted_scope):
    """Keep originals and locators intact; emit decisions without altering input.

    Scope maps and trusted settings require caller-established provenance. Unmapped
    evidence is quarantined, never automatically treated as general guidance.
    """
    if not isinstance(evidence, list) or not isinstance(reviewed_scopes, dict):
        raise ModelError('Expected evidence list and reviewed scope map.')
    output = {'applicable': [], 'requires_clarification': [], 'inapplicable': [], 'unreviewed': []}
    seen = set()
    for item in evidence:
        pid = item.get('passage_id') if isinstance(item, dict) else None
        if not isinstance(pid, str) or not pid.strip() or pid in seen:
            raise ModelError('Evidence needs unique nonempty passage IDs.')
        seen.add(pid)
        decision = decide_applicability(reviewed_scopes.get(pid, {}), trusted_scope)
        output[decision['decision']].append({'evidence': item, 'scope_decision': decision})
    return output
