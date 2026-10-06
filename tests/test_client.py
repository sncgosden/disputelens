import httpx
import pytest
from disputelens.client import Models, ModelError

def make(handler):
    return Models(httpx.Client(transport=httpx.MockTransport(handler)))

def test_local_answer(monkeypatch):
    monkeypatch.setenv('LM_CHAT_MODEL', 'test')
    c=make(lambda r: httpx.Response(200,json={'choices':[{'message':{'content':'Answer'},'finish_reason':'stop'}]}))
    assert c.chat('Question').text == 'Answer'

def test_timeout(monkeypatch):
    monkeypatch.setenv('LM_CHAT_MODEL', 'test')
    def timeout(r): raise httpx.ReadTimeout('timeout')
    with pytest.raises(ModelError,match='timed out'): make(timeout).chat('Q')

def test_auth_error_is_sanitised():
    with pytest.raises(ModelError,match='HTTP 401'): make(lambda r:httpx.Response(401,text='secret')).models()

def test_embedding_order(monkeypatch):
    monkeypatch.setenv('LM_EMBEDDING_MODEL','embed')
    c=make(lambda r:httpx.Response(200,json={'data':[{'index':1,'embedding':[0,1]},{'index':0,'embedding':[1,0]}]}))
    assert c.embed(['a','b']).tolist() == [[1,0],[0,1]]

def test_zero_vectors(monkeypatch):
    monkeypatch.setenv('LM_EMBEDDING_MODEL','embed')
    c=make(lambda r:httpx.Response(200,json={'data':[{'index':0,'embedding':[0,0]}]}))
    with pytest.raises(ModelError,match='Invalid embedding'): c.embed(['a'])

def test_claude_request(monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY','test-only')
    monkeypatch.setenv('CLAUDE_MODEL','test')
    def handler(r):
        assert r.headers['anthropic-version']=='2023-06-01'
        return httpx.Response(200,json={'content':[{'type':'text','text':'Answer'}],'stop_reason':'end_turn','usage':{'input_tokens':5}})
    assert make(handler).chat('Q',provider='claude').usage['input_tokens']==5

def test_no_final_answer(monkeypatch):
    monkeypatch.setenv('LM_CHAT_MODEL','test')
    c=make(lambda r:httpx.Response(200,json={'choices':[{'message':{'content':''},'finish_reason':'length'}]}))
    with pytest.raises(ModelError,match='No final answer'):c.chat('Q')
