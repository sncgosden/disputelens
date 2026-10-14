import json
import tempfile
from pathlib import Path

from disputelens import holdout_final as h
from disputelens.client import ModelError

PROTOCOL = {'frozen_files_sha256': {}}


def with_preconditions(content):
    d = Path(tempfile.mkdtemp())
    path = d / 'pre.json'
    if content is not None:
        path.write_text(json.dumps(content))
    old = h.PRECONDITIONS
    h.PRECONDITIONS = path
    return old, d


def good_log(d, ok=True):
    log = d / 'run.log'
    log.write_text('START\n1 passed in 0.1s\nFINISH: command_exit=%d log_exit=0\n' % (0 if ok else 1))
    return str(log)


def test_missing_preconditions_block_everything():
    old, _ = with_preconditions(None)
    try:
        status = h.precondition_status(PROTOCOL)
        assert not status['go_ahead'][0] and status['frozen_hashes'][0]
        try:
            h.require_preconditions(PROTOCOL)
        except ModelError as error:
            assert 'nothing was loaded' in str(error)
        else:
            raise AssertionError('should block')
    finally:
        h.PRECONDITIONS = old


def test_all_preconditions_met():
    d = Path(tempfile.mkdtemp())
    old, d = with_preconditions({'go_ahead': {'by': 'Sebastian', 'holdout_authorised': True, 'at': '2026-10-09'},
                                 'budget': {'max_calls': 15, 'max_usd': 2.0}, 'pytest_log': good_log(d),
                                 'review_plan': 'assisted_accepted'})
    try:
        h.require_preconditions(PROTOCOL)
    finally:
        h.PRECONDITIONS = old


def test_failing_pytest_log_or_wrong_budget_or_not_sebastian_blocks():
    d = Path(tempfile.mkdtemp())
    base = {'go_ahead': {'by': 'Sebastian', 'holdout_authorised': True, 'at': 'x'},
            'budget': {'max_calls': 15, 'max_usd': 2.0}, 'pytest_log': good_log(d), 'review_plan': 'assisted_accepted'}
    variants = [dict(base, pytest_log=good_log(d, ok=False)),
                dict(base, budget={'max_calls': 15, 'max_usd': 5.0}),
                dict(base, budget={'max_calls': 20, 'max_usd': 2.0}),
                dict(base, go_ahead={'by': 'Claude', 'holdout_authorised': True, 'at': 'x'}),
                dict(base, go_ahead={'by': 'Sebastian', 'holdout_authorised': False, 'at': 'x'}),
                dict(base, review_plan='none')]
    for variant in variants:
        old, _ = with_preconditions(variant)
        try:
            try:
                h.require_preconditions(PROTOCOL)
            except ModelError:
                continue
            raise AssertionError(variant)
        finally:
            h.PRECONDITIONS = old


def test_changed_frozen_file_blocks():
    f = Path(tempfile.mkdtemp()) / 'x.txt'
    f.write_text('a')
    protocol = {'frozen_files_sha256': {str(f): h.sha(f)}}
    assert h.frozen_status(protocol)[str(f)]
    f.write_text('b')
    assert not h.frozen_status(protocol)[str(f)]


def test_p90_and_median():
    assert h.p90_nearest_rank(list(range(1, 11))) == 9
    assert h.p90_nearest_rank([5]) == 5 and h.p90_nearest_rank([]) is None
    assert h.median([1, 3, 2]) == 2 and h.median([1, 2, 3, 4]) == 2.5


def test_apply_arms_uses_gate_variants():
    ev = lambda i, hs: {'citation_id': i, 'headings': ['G', 'Ch', *hs], 'text': 'x'}
    pack = {'question': 'about 4837', 'groups': [{'evidence': [ev('S1', ['Sec (Message Reason Code 4837)', 'Participating Countries']),
                                                               ev('S2', ['Sec (Message Reason Code 4837)'])]}]}
    answer = {'status': 'answered', 'missing_information': [],
              'claims': [{'text': 'Core', 'citations': [{'id': 'S2', 'quote': 'q'}]},
                         {'text': 'Program rule', 'citations': [{'id': 'S1', 'quote': 'q'}]}]}
    outputs, audit = h.apply_arms(pack, answer)
    assert outputs['A_baseline'] is answer and audit['B'] == 'conditionalised'
    assert outputs['B_gate_v2']['claims'][1]['text'].startswith('Only if your dispute is')
