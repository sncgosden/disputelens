import pytest

from disputelens.client import ModelError
from disputelens.section_scope import classify_section, section_applicable


FILTERS = {'corpus': 'real', 'provider': 'Stripe', 'scheme': 'Mastercard', 'region': 'UK'}


def unit(ids):
    return {'metadata': {'source_id': 'mastercard-chargeback-guide', 'corpus': 'real',
                         'scheme': 'Mastercard', 'provider': None, 'region': 'multiple',
                         'status': 'snapshot'}, 'passage_ids': ids}


def scopes():
    return {'general': classify_section(['Dual Message System Chargebacks', 'Refund Not Processed']),
            'maestro': classify_section(['Single Message System Chargebacks for Non-Mastercard BIN Maestro']),
            'qr': classify_section(['Mastercard Merchant Presented QR', 'Credit not processed'])}


def test_non_mastercard_and_qr_sections_excluded_without_trusted_rail():
    mapping = scopes()
    assert section_applicable(unit(['general']), FILTERS, mapping)
    assert not section_applicable(unit(['maestro']), FILTERS, mapping)
    assert not section_applicable(unit(['qr']), FILTERS, mapping)
    assert not section_applicable(unit(['qr']), FILTERS, mapping, payment_rail='card')
    assert section_applicable(unit(['qr']), FILTERS, mapping, payment_rail='merchant_presented_qr')


def test_mixed_scope_units_cannot_smuggle_in_disallowed_evidence():
    assert not section_applicable(unit(['general', 'maestro']), FILTERS, scopes())
    assert not section_applicable(unit(['general', 'qr']), FILTERS, scopes())


def test_missing_mapping_and_unsupported_settings_stop():
    with pytest.raises(ModelError, match='Missing publisher'):
        section_applicable(unit(['unknown']), FILTERS, scopes())
    with pytest.raises(ModelError, match='trusted'):
        section_applicable(unit(['general']), FILTERS, scopes(), payment_rail='guess_from_query')


def test_document_filter_still_rejects_wrong_scheme_and_corpus():
    assert not section_applicable(unit(['general']), {**FILTERS, 'scheme': 'Visa'}, scopes())
    assert not section_applicable(unit(['general']), {**FILTERS, 'corpus': 'fixture'}, scopes())
