"""BM25 over the same token-safe units, scoped before ranking."""
import re

from rank_bm25 import BM25Okapi

from .applicability import applicable
from .client import ModelError


BM25_CONFIG = {'algorithm': 'BM25Okapi', 'k1': 1.5, 'b': 0.75, 'epsilon': 0.25,
               'tokenizer': 'unicode-words-and-dotted-codes-v1',
               'statistics_scope': 'applicable-units-only', 'stopwords': False, 'stemming': False}


def tokenize(text):
    # Keep 13.1, 13.10 and 12.6.1 distinct rather than splitting their digits.
    return re.findall(r'\d+(?:\.\d+)+|[^\W_]+', text.casefold(), flags=re.UNICODE)


def retrieve_keyword(units, question, filters, top_k=5):
    if not 1 <= top_k <= 50:
        raise ModelError('Choose between 1 and 50 results.')
    query = tokenize(question)
    if not query:
        raise ModelError('Question contains no searchable words or codes.')
    eligible = [u for u in units if applicable(u['metadata'], **filters)]
    documents = [tokenize(u['text']) for u in eligible]
    pairs = [(u, tokens) for u, tokens in zip(eligible, documents) if tokens]
    if not pairs:
        return []
    eligible, documents = zip(*pairs)
    index = BM25Okapi(documents, k1=1.5, b=0.75, epsilon=0.25)
    scores = index.get_scores(query)
    terms = set(query)
    # No lexical match means no candidate, even when there are fewer than top_k matches.
    candidates = [n for n, tokens in enumerate(documents) if terms.intersection(tokens)]
    candidates.sort(key=lambda n: (-float(scores[n]), eligible[n]['chunk_id']))
    return [{'rank': rank, 'bm25_score': float(scores[n]), 'unit': eligible[n]}
            for rank, n in enumerate(candidates[:top_k], 1)]
