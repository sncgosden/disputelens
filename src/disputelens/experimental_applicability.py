"""Experimental reviewed scope decisions; not wired into production retrieval."""
from .client import ModelError

ALLOWED = {'provider', 'scheme', 'message_system', 'reason_code', 'dispute_subtype',
           'region', 'participating_countries_membership', 'payment_flow', 'goods_type', 'claim_type'}


def decide_applicability(source_scope, trusted_scope):
    """None means unknown in settings or unrestricted in reviewed requirements.

    Callers must establish provenance before passing trusted settings. This function
    cannot authenticate a caller or infer source requirements from headings/text.
    """
    if not isinstance(source_scope, dict) or not isinstance(trusted_scope, dict):
        raise ModelError('Scope inputs must be objects.')
    if source_scope.get('review_status') != 'reviewed':
        return {'decision': 'unreviewed', 'missing': [], 'conflicts': []}
    requirements = source_scope.get('requirements')
    if not isinstance(requirements, dict) or not requirements:
        raise ModelError('Reviewed source needs explicit requirements.')
    if (set(requirements) - ALLOWED) or (set(trusted_scope) - ALLOWED):
        raise ModelError('Unknown scope field.')
    for settings in (requirements, trusted_scope):
        for key, value in settings.items():
            if value is None:
                continue
            if key == 'participating_countries_membership':
                if type(value) is not bool:
                    raise ModelError('Membership must be an explicit boolean.')
            elif not isinstance(value, str) or not value.strip():
                raise ModelError('Scope values must be nonempty strings or None.')
    missing, conflicts = [], []
    for key, required in requirements.items():
        if required is None:
            continue
        actual = trusted_scope.get(key)
        if actual is None:
            missing.append(key)
        elif actual != required:
            conflicts.append(key)
    return {'decision': 'inapplicable' if conflicts else 'requires_clarification' if missing else 'applicable',
            'missing': sorted(missing), 'conflicts': sorted(conflicts)}
