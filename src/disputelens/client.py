"""Small explicit clients: no retries or automatic cloud fallback."""
import os
from dataclasses import dataclass
import httpx
import numpy as np
from dotenv import load_dotenv

class ModelError(RuntimeError):
    pass

@dataclass
class Reply:
    text: str
    model: str
    finish_reason: str | None
    usage: dict

class Models:
    def __init__(self, client=None):
        self.http = client or httpx.Client(timeout=httpx.Timeout(120, connect=5))
        self.base = os.getenv('LM_BASE_URL', 'http://localhost:1234/v1').rstrip('/')

    def close(self):
        self.http.close()

    def _request(self, method, url, **kwargs):
        try:
            response = self.http.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException:
            raise ModelError('Model request timed out. Check loading, reasoning settings and output allowance.') from None
        except httpx.ConnectError:
            raise ModelError('Cannot connect. Check the server address and whether LM Studio is running.') from None
        except httpx.HTTPStatusError as error:
            raise ModelError(f'HTTP {error.response.status_code}: check model ID, authentication and provider configuration.') from None
        except (httpx.HTTPError, ValueError):
            raise ModelError('Request failed or returned invalid JSON. Inspect provider logs.') from None

    def _local_headers(self):
        token = os.getenv('LM_API_TOKEN')
        return {'Authorization': f'Bearer {token}'} if token else {}

    def models(self):
        data = self._request('GET', self.base + '/models', headers=self._local_headers())
        try:
            return [item['id'] for item in data['data']]
        except (KeyError, TypeError):
            raise ModelError('Unexpected model-list response.') from None

    def chat(self, question, model=None, system='Answer concisely.', provider='local', max_tokens=1024):
        if provider not in ('local', 'claude'):
            raise ModelError('Provider must be local or claude.')
        if provider == 'claude':
            key = os.getenv('ANTHROPIC_API_KEY')
            model = model or os.getenv('CLAUDE_MODEL')
            if not key or not model:
                raise ModelError('Set ANTHROPIC_API_KEY and CLAUDE_MODEL in the ignored .env file.')
            data = self._request('POST', 'https://api.anthropic.com/v1/messages',
                headers={'x-api-key': key, 'anthropic-version': '2023-06-01'},
                json={'model': model, 'max_tokens': max_tokens, 'system': system,
                      'messages': [{'role': 'user', 'content': question}]})
            try:
                text = ''.join(b['text'] for b in data['content'] if b.get('type') == 'text')
                reason = data.get('stop_reason')
            except (KeyError, TypeError):
                raise ModelError('Unexpected Claude message response.') from None
        else:
            model = model or os.getenv('LM_CHAT_MODEL')
            if not model:
                raise ModelError('Set LM_CHAT_MODEL to the exact API ID in .env.')
            data = self._request('POST', self.base + '/chat/completions', headers=self._local_headers(),
                json={'model': model, 'temperature': 0.2, 'max_tokens': max_tokens,
                      'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': question}]})
            try:
                text = data['choices'][0]['message'].get('content') or ''
                reason = data['choices'][0].get('finish_reason')
            except (KeyError, TypeError, IndexError):
                raise ModelError('Unexpected local chat response.') from None
        if not text.strip():
            raise ModelError('No final answer. Check reasoning settings and output allowance.')
        if reason in ('length', 'max_tokens'):
            raise ModelError('Answer hit the output limit; do not score it as complete.')
        return Reply(text, model, reason, data.get('usage', {}))

    def embed(self, texts, kind='document'):
        model = os.getenv('LM_EMBEDDING_MODEL')
        if not model:
            raise ModelError('Set LM_EMBEDDING_MODEL to a separate embedding model API ID.')
        if kind not in ('document', 'query') or not texts:
            raise ModelError('Provide non-empty texts and kind=document or query.')
        # Configure empty prefixes for models/runtimes that already apply them.
        prefix = os.getenv('EMBED_DOCUMENT_PREFIX', 'search_document: ') if kind == 'document' else os.getenv('EMBED_QUERY_PREFIX', 'search_query: ')
        data = self._request('POST', self.base + '/embeddings', headers=self._local_headers(),
            json={'model': model, 'input': [prefix + t for t in texts]})
        try:
            items = sorted(data['data'], key=lambda x: x['index'])
            if [x['index'] for x in items] != list(range(len(texts))):
                raise ValueError('Mismatched indices')
            vectors = np.asarray([x['embedding'] for x in items], dtype=float)
            if vectors.ndim != 2 or vectors.shape[1] == 0 or not np.isfinite(vectors).all() or (np.linalg.norm(vectors, axis=1) == 0).any():
                raise ValueError('Invalid vectors')
            return vectors
        except (KeyError, TypeError, ValueError):
            raise ModelError('Invalid embedding vectors or response ordering.') from None

def configured_models():
    load_dotenv('.env')
    return Models()
