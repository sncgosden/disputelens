"""Recheck a saved answer offline, preserving its original outcome."""
import argparse
import json
import sys
from pathlib import Path

from .build_index import digest
from .client import ModelError
from .embed_batch import safe_error, write_json
from .grounded_answer import validate_answer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('saved_answer', type=Path)
    args = parser.parse_args()
    try:
        original = json.loads(args.saved_answer.read_text())
        pack_path = Path(original['context_pack_path'])
        if digest(pack_path) != original['identity']['context_pack_sha256']:
            raise ModelError('Saved pack fingerprint changed; cannot revalidate.')
        text = original.get('raw_response')
        if not isinstance(text, str) or not text.strip():
            raise ModelError('No saved final answer to revalidate.')
        checked = validate_answer(text, json.loads(pack_path.read_text()))
        validator_sha = digest(Path(__file__).with_name('grounded_answer.py'))
        output = args.saved_answer.with_name(args.saved_answer.stem + '-review-' + validator_sha[:12] + '.json')
        write_json(output, {'status': 'revalidated_requires_semantic_review',
            'original_attempt_path': str(args.saved_answer),
            'original_attempt_sha256': digest(args.saved_answer),
            'original_status': original['status'], 'validator_sha256': validator_sha, **checked})
        print('PASS: saved answer citation IDs and exact extracts checked.')
        print('ANSWER STATUS: ' + checked['answer']['status'])
        print('Semantic correctness and completeness still require review.')
        print(f'SAVED REVIEW: {output}')
        print('Original attempt preserved. No API calls, holdout or GitHub sync.')
        return 0
    except Exception as error:
        print('STOP: ' + safe_error(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
