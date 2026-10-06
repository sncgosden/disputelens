"""Run explicitly selected smoke tests; Claude mode makes one paid call."""
import argparse
import json
import os
import time
from .client import configured_models, ModelError

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['models', 'chat', 'embed', 'claude'])
    args = parser.parse_args()
    client = configured_models()
    start = time.perf_counter()
    try:
        if args.mode == 'models':
            print(json.dumps(client.models(), indent=2))
        elif args.mode == 'embed':
            d = client.embed(['A fictional delivery policy requires proof of delivery.'])
            q = client.embed(['What proves delivery?'], kind='query')
            if d.shape != q.shape:
                raise ModelError('Query and document embedding dimensions differ.')
            print('Document/query embeddings valid. Dimension:', d.shape[1])
        else:
            if args.mode == 'chat':
                print('Local server:', client.base, flush=True)
                print('Selected model:', os.getenv('LM_CHAT_MODEL') or '(not configured)', flush=True)
                print('Question: Explain RAG in two short sentences.', flush=True)
                print('This is a local test; it does not call Claude.', flush=True)
            print('Waiting for final answer...', flush=True)
            r = client.chat('Explain RAG in two short sentences.', provider='claude' if args.mode == 'claude' else 'local')
            print('Model:', r.model)
            print('Answer:', r.text)
            print('Finish reason:', r.finish_reason)
            print('Usage:', json.dumps(r.usage))
        print('Seconds:', round(time.perf_counter() - start, 1))
    except ModelError as error:
        parser.exit(1, f'Error: {error}\n')
    finally:
        client.close()

if __name__ == '__main__':
    main()
