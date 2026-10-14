import copy
import json

import pytest

from disputelens.client import ModelError
from disputelens.grounded_answer import SYSTEM
from disputelens.prepare_completeness_audit import CONFIG, draft_system, verify_review


def config():
    return json.loads(CONFIG.read_text())


def test_review_has_two_development_cases_and_separate_applicability():
    rows, packs = verify_review(config())
    assert set(packs) == {'E18', 'E23'}
    assert any(r['coverage'] == 'omitted' and r['applicability'] == 'conditional_facts_unknown' for r in rows)
    assert any(r['coverage'] == 'acknowledged_source_gap' for r in rows)


@pytest.mark.parametrize('field', ['attempt_sha256', 'context_pack_sha256'])
def test_stale_input_cannot_inherit_reviews(field):
    data = config(); data['cases'][0][field] = 'changed'
    with pytest.raises(ModelError, match='input changed'):
        verify_review(data)


def test_included_clause_needs_a_real_claim_reference():
    data = config(); data['cases'][0]['clauses'][0]['answer_claim_numbers'] = [999]
    with pytest.raises(ModelError, match='claim references'):
        verify_review(data)


def test_clause_cannot_reference_missing_evidence():
    data = config(); data['cases'][0]['clauses'][0]['citation_ids'] = ['S999']
    with pytest.raises(ModelError, match='source is missing'):
        verify_review(data)


def test_duplicate_clause_ids_are_rejected():
    data = config(); data['cases'][0]['clauses'].append(copy.deepcopy(data['cases'][0]['clauses'][0]))
    with pytest.raises(ModelError, match='unique'):
        verify_review(data)


def test_draft_changes_brevity_but_preserves_schema_and_quote_guards():
    draft = draft_system()
    assert 'at most four concise claims' not in draft
    assert 'as many concise claims as necessary' in draft
    assert 'exception waives only' in draft
    assert 'Distinguish missing merchant facts from missing evidence' in draft
    assert SYSTEM.split('Return ONLY JSON', 1)[1] == draft.split('Return ONLY JSON', 1)[1]
