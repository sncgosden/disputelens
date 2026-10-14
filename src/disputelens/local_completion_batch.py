"""User-run paired local gates; sequential models, no paid calls or retries."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from .build_index import digest
from .client import ModelError

MODELS = ('qwen3.5-4b', 'qwen3.5-9b-mlx')
PROTOCOL = Path('eval/experiments/local-completion-gate-v2/protocol.json')


def check_loaded(loaded, expected):
    if expected not in loaded:
        raise ModelError('Load the requested model ' + expected + ' before continuing.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true',help='Two sequential local calls; other loaded models allowed')
    args=parser.parse_args()
    try:
        protocol=json.loads(PROTOCOL.read_text())
        pack=Path('data/indexes/context-eval/9588eef5a0cd81e960abe04c/packs/E10.json')
        if digest(pack)!=protocol['context_pack_sha256']:
            raise ModelError('Frozen E10 pack changed.')
        existing={}
        for path in Path('data/indexes/answer-trials').glob('E10-*.json'):
            record=json.loads(path.read_text())
            identity=record.get('identity',{})
            model=identity.get('model')
            if model in MODELS:
                if (identity.get('context_pack_sha256')!=protocol['context_pack_sha256']
                        or identity.get('max_tokens')!=8192):
                    raise ModelError('Existing E10 local inputs differ; inspect before continuing.')
                existing[model]=record
        if not args.run:
            print('Prepared: same E10 full pack for4B then9B, output8192/temperature0.2/timeout300s.')
            print('No model/API calls. --run checks each requested model is loaded; other models and workloads allowed.')
            return 0
        import lmstudio as lms
        for model in MODELS:
            if model in existing:
                record=existing[model]
                if record.get('status')!='complete_requires_review':
                    raise ModelError(model+' has a pending/failed E10 attempt; inspect it, no retry.')
                from .grounded_answer import validate_answer
                validate_answer(record['raw_response'],json.loads(pack.read_text()))
                print('REUSED: '+model+' successful E10 output; no repeat call.',flush=True)
                continue
            check_loaded([m.identifier for m in lms.list_loaded_models('llm')],model)
            result=subprocess.run([sys.executable,'-u','-m','disputelens.generate_answer',
                                   '--dev-case','E10','--context-source','full','--model',model,'--run'],check=False)
            if result.returncode:
                print('STOP: completion gate failed; no next model, retries or broader evaluation.',flush=True)
                return result.returncode
        print('Both structural completion gates finished. Semantic review required before45-case runs.')
        return 0
    except (ModelError,EOFError) as error:
        print('STOP: '+str(error),file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
