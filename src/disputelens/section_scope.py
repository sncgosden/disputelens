"""Narrow public-guidance scope guards from publisher headings, never query inference."""
from .applicability import applicable
from .client import ModelError


def classify_section(headings):
    path = ' > '.join(headings).casefold()
    return {
        'non_mastercard_bin_maestro': 'non-mastercard bin maestro' in path,
        'merchant_presented_qr': 'mastercard merchant presented qr' in path,
        'heading_path': list(headings),
    }


def section_applicable(unit, filters, passage_scopes, payment_rail=None):
    """Apply document scope first, then check every evidence span before ranking.

    This is a limited explicit-exclusion policy, not complete regional, date,
    message-system or tenant authorization. Missing QR settings fail closed for QR.
    A mixed-scope unit is rejected if any contained passage fails the guard.
    """
    if payment_rail not in (None, 'card', 'merchant_presented_qr'):
        raise ModelError('Use a trusted card or merchant_presented_qr setting; do not infer it from text.')
    if not applicable(unit['metadata'], **filters):
        return False
    if unit['metadata']['source_id'] != 'mastercard-chargeback-guide':
        return True
    if not unit['passage_ids']:
        raise ModelError('Mastercard search unit lacks evidence IDs.')
    for pid in unit['passage_ids']:
        if pid not in passage_scopes:
            raise ModelError('Missing publisher section scope; review the source mapping before ranking.')
        scope = passage_scopes[pid]
        if scope['non_mastercard_bin_maestro']:
            return False  # This product currently supports Visa/Mastercard, not this separate rail.
        if scope['merchant_presented_qr'] and payment_rail != 'merchant_presented_qr':
            return False
    return True
