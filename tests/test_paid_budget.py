import pytest
from disputelens.client import ModelError
from disputelens.paid_budget import reserve_entry, token_cost


def budget():
    return {'model': 'm', 'max_output_tokens': 8192, 'max_calls': 2, 'max_usd': 0.15,
            'jobs': [{'prompt_sha256': 'p', 'reserved_usd': 0.1}], 'reservations': {}}


def test_price_math_and_invalid_usage():
    assert token_cost(1000, 100, {'input_usd_per_million': 2, 'output_usd_per_million': 10}) == 0.003
    with pytest.raises(ModelError): token_cost(None, 100, {})


def test_spend_reservation_survives_failed_request_and_blocks_next():
    b = reserve_entry(budget(), 'first', 'p', 'm', 8192)
    with pytest.raises(ModelError, match='allowance would be exceeded'):
        reserve_entry(b, 'second', 'p', 'm', 8192)
    assert len(b['reservations']) == 1


def test_repeated_attempt_cannot_reset_allowance():
    b = reserve_entry(budget(), 'first', 'p', 'm', 8192)
    with pytest.raises(ModelError, match='already reserved'):
        reserve_entry(b, 'first', 'p', 'm', 8192)


def test_count_limit_and_unbudgeted_prompt_rejected():
    b = budget(); b['max_calls'] = 0
    with pytest.raises(ModelError, match='count limit'): reserve_entry(b, 'x', 'p', 'm', 8192)
    with pytest.raises(ModelError, match='outside'): reserve_entry(budget(), 'x', 'changed', 'm', 8192)


def test_changed_model_or_output_cap_rejected():
    with pytest.raises(ModelError, match='differs'): reserve_entry(budget(), 'x', 'p', 'other', 8192)
