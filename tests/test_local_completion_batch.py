import pytest
from disputelens.client import ModelError
from disputelens.local_completion_batch import check_loaded


def test_single_target_allowed():
    check_loaded(['qwen3.5-4b'],'qwen3.5-4b')


@pytest.mark.parametrize('loaded',[[],['qwen3.5-9b-mlx']])
def test_missing_requested_model_stops_before_generation(loaded):
    with pytest.raises(ModelError):
        check_loaded(loaded,'qwen3.5-4b')


def test_both_loaded_models_are_allowed_and_target_still_required():
    check_loaded(['qwen3.5-4b','qwen3.5-9b-mlx'],'qwen3.5-9b-mlx')
