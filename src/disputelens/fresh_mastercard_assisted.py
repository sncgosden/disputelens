"""Assisted (non-independent) scoring for mastercard-fresh-v1. Separate module: the frozen runner is untouched.

Applies the same score_rows as the independent path, but can never produce a shipping decision.
"""
import json
import sys

from .fresh_mastercard import FOLDER, out_dir, score_rows, sha

LABELS = FOLDER / 'labels-assisted.json'


def assisted_result(rows, labels):
    res = score_rows(rows, labels)
    res['declared_decision_if_independent'] = res['decision']
    res['decision'] = 'assisted_only_no_decision'
    return res


def main():
    data = json.loads(LABELS.read_text())
    if data.get('independent') is not False:
        print('STOP: this module is for non-independent labels only.', file=sys.stderr)
        return 1
    det = json.loads((out_dir() / 'detectors.json').read_text())
    rows = [{'case': cid, **c} for cid, v in det.items() for c in v['claims']]
    for cid, v in det.items():
        if len(data['ratings'][cid]) != len(v['claims']):
            print(f'STOP: ratings for {cid} do not match claim count.', file=sys.stderr)
            return 1
    res = assisted_result(rows, data['ratings'])
    res['labels_sha256'] = sha(LABELS)
    res['independent'] = False
    res['claims_rated'] = len(rows)
    (FOLDER / 'result-assisted.json').write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
