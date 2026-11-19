"""Offline regression tests for parallel checkpointing and provider isolation."""
import importlib.util
import json
import os
from pathlib import Path
import threading
import time

import httpx
from openai import OpenAI
import pytest

if os.getenv('BENCHMARK_PARALLEL_MODULE'):
    spec = importlib.util.spec_from_file_location('parallel_under_test', os.environ['BENCHMARK_PARALLEL_MODULE'])
    parallel = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parallel)
else:
    from benchmarks import parallel


@pytest.fixture
def cases():
    return [dict(id='one',schema_id='s01_retail',question='Return one',expected_sql='SELECT 1',difficulty='easy'),
            dict(id='two',schema_id='s02_hr',question='Return one again',expected_sql='SELECT 1',difficulty='hard')]


@pytest.fixture
def config(monkeypatch):
    monkeypatch.setenv('BENCH_A_KEY', 'secret-a')
    monkeypatch.setenv('BENCH_B_KEY', 'secret-b')
    monkeypatch.setenv('OPENAI_BASE_URL', 'https://wrong-global.test/v1')
    return {'models':[
        {'model_id':'model-a','label':'A','provider':{'base_url':'https://provider-a.test/v1','key_env':'BENCH_A_KEY'},'pricing':{'input_per_million':1,'output_per_million':2}},
        {'model_id':'model-b','label':'B','provider':{'base_url':'https://provider-b.test/v1','key_env':'BENCH_B_KEY'},'pricing':{'input_per_million':1,'output_per_million':2}},
    ], 'transport_retries':0}


def factory_for(requests, fail=None, activity=None):
    lock = threading.Lock()
    def respond(request):
        body = json.loads(request.content)
        with lock:
            requests.append((str(request.url),request.headers['authorization'],body))
            number = len(requests)
            if activity is not None:
                activity['current'] += 1
                activity['peak'] = max(activity['peak'],activity['current'])
        try:
            if fail:
                error = fail(request,body,number)
                if error is not None:
                    return error
            time.sleep(.01)
            system = body['messages'][0]['content']
            if system.startswith('You are the input classifier'):
                result = {'valid':True,'explanation':'Answerable.'}
            elif 'SQL critique agent' in system:
                result = {'approved':True,'issues':[]}
            else:
                result = {'sql':'SELECT 1','explanation':'One.'}
            return httpx.Response(200,json={'id':f'call-{number}','object':'chat.completion','created':0,
                'model':body['model'],'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':json.dumps(result)}}],
                'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15,
                         'prompt_tokens_details':{'cached_tokens':2},'completion_tokens_details':{'reasoning_tokens':1}}})
        finally:
            if activity is not None:
                with lock:
                    activity['current'] -= 1
    def factory(**kwargs):
        return OpenAI(http_client=httpx.Client(transport=httpx.MockTransport(respond)),**kwargs)
    return factory


def test_parallel_provider_isolation_and_pilot_resume(config,cases,tmp_path):
    requests,activity = [],{'current':0,'peak':0}
    factory = factory_for(requests,activity=activity)
    pilot = parallel.run_parallel(config,cases,tmp_path,limit_cases=1,workers=2,per_model_workers=1,client_factory=factory,progress=None)
    assert len(requests) == 6
    assert all(m['completed_cases']==1 for m in pilot['models'].values())
    full = parallel.run_parallel(config,cases,tmp_path,workers=2,per_model_workers=1,client_factory=factory,progress=None)
    assert len(requests) == 12
    assert activity['peak'] == 2
    for label,model in full['models'].items():
        assert model['completed_cases'] == 2
        assert model['execution_accuracy'] == 1
        assert model['http_attempts'] == 6
        assert model['usage']['input_tokens'] == 60
        assert model['usage']['output_tokens'] == 30
        assert model['usage']['estimated_cost_usd'] == pytest.approx(.00012)
        assert [r['id'] for r in model['results']] == ['one','two']
        assert all(r['stage_calls']=={'classify':1,'generate':1,'critique':1} for r in model['results'])
    for url,authorization,body in requests:
        suffix = body['model'][-1]
        assert url == f'https://provider-{suffix}.test/v1/chat/completions'
        assert authorization == f'Bearer secret-{suffix}'
        assert body['response_format']=={'type':'json_object'}
    parallel.run_parallel(config,cases,tmp_path,client_factory=factory,progress=None)
    assert len(requests)==12
    assert len((tmp_path/'cases.jsonl').read_text().splitlines())==4
    assert 'secret-a' not in (tmp_path/'manifest.json').read_text()
    changed = {**config,'max_repairs':0}
    with pytest.raises(ValueError,match='Resume refused'):
        parallel.run_parallel(changed,cases,tmp_path,client_factory=factory,progress=None)


def test_provider_failure_is_redacted_blocked_and_resumable(config,cases,tmp_path):
    requests = []
    def fail(request,body,number):
        return httpx.Response(403,json={'error':{'message':'Sensitive body contains secret-a and private detail'}})
    first = parallel.run_parallel(config,cases,tmp_path,model_names=['A'],workers=1,per_model_workers=1,
        client_factory=factory_for(requests,fail=fail),progress=None)
    assert len(requests)==1
    assert first['models']['A']['completed_cases']==0
    assert first['models']['A']['execution_accuracy'] is None
    assert first['blocked_models']==['A']
    saved = (tmp_path/'cases.jsonl').read_text()
    assert 'secret-a' not in saved and 'private detail' not in saved
    second = parallel.run_parallel(config,cases,tmp_path,model_names=['A'],workers=1,per_model_workers=1,
        client_factory=factory_for(requests),progress=None)
    assert len(requests)==7
    assert second['models']['A']['completed_cases']==2
    assert second['models']['A']['http_attempts']==7
    assert second['models']['A']['usage']['input_tokens_complete'] is False


def test_transient_retry_usage_and_stages(config,cases,tmp_path):
    requests = []
    config = {**config,'transport_retries':2}
    def fail(request,body,number):
        if number==1:
            return httpx.Response(429,json={'error':{'message':'busy'}},headers={'retry-after':'0'})
    report = parallel.run_parallel(config,cases,tmp_path,model_names=['A'],limit_cases=1,
        client_factory=factory_for(requests,fail=fail),progress=None)
    result = report['models']['A']['results'][0]
    assert len(requests)==4
    assert result['stage_calls']=={'classify':1,'generate':1,'critique':1}
    assert [c['transport_attempt'] for c in result['calls']]==[1,2,1,1]
    assert result['correct']


def test_dry_run_prepares_references_without_credentials(config,cases,tmp_path,monkeypatch):
    monkeypatch.delenv('BENCH_A_KEY')
    monkeypatch.delenv('BENCH_B_KEY')
    result = parallel.run_parallel(config,cases,tmp_path,dry_run=True,
        client_factory=lambda **_:pytest.fail('dry run must not create clients'))
    assert result['pending_cases']==4
    assert result['schemas_validated']==2
    assert result['references_validated']==2
    assert not (tmp_path/'cases.jsonl').exists()


def test_length_truncation_retains_usage_and_null_cached_price(config,cases,tmp_path):
    requests = []
    config['models'][0]['pricing']['cached_input_per_million'] = None
    def truncated(request,body,number):
        return httpx.Response(200,json={'id':'truncated-call','object':'chat.completion','created':0,
            'model':'resolved-model-a','choices':[{'index':0,'finish_reason':'length',
                'message':{'role':'assistant','content':'{"valid":'}}],
            'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15,
                'prompt_tokens_details':{'cached_tokens':2},
                'completion_tokens_details':{'reasoning_tokens':4},'provider_extra':{'value':7}}})
    report = parallel.run_parallel(config,cases,tmp_path,model_names=['A'],limit_cases=1,
        client_factory=factory_for(requests,fail=truncated),progress=None)
    result = report['models']['A']['results'][0]
    assert result['status'] == 'completed' and result['correct'] is False
    assert 'finish_reason=length' in result['error']['message']
    call = result['calls'][0]
    assert call['finish_reason'] == 'length'
    assert call['response_model'] == 'resolved-model-a'
    assert call['usage']['raw']['provider_extra'] == {'value':7}
    assert call['usage']['raw']['completion_tokens_details']['reasoning_tokens'] == 4
    assert call['usage']['estimated_cost_usd'] == pytest.approx(.00002)
