"""Offline regression tests for parallel checkpointing and provider isolation."""
import importlib.util
import copy
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
    assert json.loads(saved)['error']['category'] == 'provider_auth'
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


@pytest.mark.parametrize('path,value', [
    (('models',), {'not': 'a list'}),
    (('max_repairs',), True),
    (('max_critiques',), 1.5),
    (('max_tool_calls',), True),
    (('max_tool_calls',), -1),
    (('max_tool_calls',), 1.5),
    (('max_tool_calls',), 21),
    (('transport_retries',), '2'),
    (('request_timeout_seconds',), float('nan')),
    (('models', 0, 'model_id'), None),
    (('models', 0, 'provider', 'base_url'), 'https://example.test/v1#fragment'),
    (('models', 0, 'provider', 'base_url'), 'https://example.test:bad/v1'),
    (('models', 0, 'request_kwargs'), []),
    (('models', 0, 'request_kwargs'), {'max_completion_tokens': 0}),
    (('models', 0, 'request_kwargs'), {'max_tokens': 100, 'max_completion_tokens': 100}),
    (('models', 0, 'request_kwargs'), {'n': 2}),
    (('models', 0, 'request_kwargs'), {'timeout': None}),
    (('models', 0, 'request_kwargs'), {'extra_body': {'model': 'different-model'}}),
    (('models', 0, 'request_kwargs'), {'extra_body': {'n': 2}}),
    (('models', 0, 'pricing', 'input_per_million'), -1),
    (('models', 0, 'pricing', 'output_per_million'), float('inf')),
])
def test_invalid_config_fails_before_requests(config, path, value):
    config = copy.deepcopy(config)
    target = config
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        parallel.normalize_config(config)


def test_legacy_token_limit_is_not_silently_overridden(config):
    config['request_kwargs'] = {'max_tokens': 256}
    normalized = parallel.normalize_config(config)
    assert normalized['models'][0]['request_kwargs'] == {'max_tokens': 256}


@pytest.mark.parametrize('field', ['tools', 'tool_choice', 'parallel_tool_calls', 'functions', 'function_call'])
@pytest.mark.parametrize('nested', [False, True])
def test_tool_configuration_cannot_override_agent_boundaries(config, field, nested):
    setting = {field: 'override'}
    config['models'][0]['request_kwargs'] = {'extra_body': setting} if nested else setting
    with pytest.raises(ValueError, match='Reserved|cannot override'):
        parallel.normalize_config(config)


def test_zero_tool_budget_keeps_requests_tool_free(config, cases, tmp_path):
    config['max_tool_calls'] = 0
    requests = []
    report = parallel.run_parallel(config, cases, tmp_path, model_names=['A'], limit_cases=1,
                                  client_factory=factory_for(requests), progress=None)
    result = report['models']['A']['results'][0]
    assert result['correct'] and result['tool_calls'] == 0
    assert len(requests) == 3
    assert all('tools' not in body and 'tool_choice' not in body for _, _, body in requests)


def test_inspection_calls_reach_models_and_retain_all_usage(config, tmp_path):
    database = parallel.load_database('s01_retail', tmp_path)
    before = database.path.read_bytes()
    case = dict(id='inspect', schema_id='s01_retail', question='Count catalog products',
                expected_sql='SELECT COUNT(*) FROM products', difficulty='easy')
    expected = database.execute(case['expected_sql'])
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        system = body['messages'][0]['content']
        finish = 'stop'
        if system.startswith('You are the input classifier'):
            assert 'tools' not in body and 'tool_choice' not in body
            message = {'role': 'assistant', 'content': json.dumps({'valid': True, 'explanation': 'Answerable.'})}
        else:
            critic = 'SQL critique agent' in system
            name = 'get_column_profile' if critic else 'get_column_values'
            call_id = 'critic-profile' if critic else 'generator-values'
            tool_messages = [item for item in body['messages'] if item['role'] == 'tool']
            if not tool_messages:
                assert {tool['function']['name'] for tool in body['tools']} == {
                    'get_column_values', 'get_column_profile'}
                finish = 'tool_calls'
                message = {'role': 'assistant', 'content': None, 'tool_calls': [{
                    'id': call_id, 'type': 'function', 'function': {
                        'name': name, 'arguments': json.dumps({
                            'table': 'products', 'column': 'price' if critic else 'category', 'limit': 10})}}]}
            else:
                assert len(tool_messages) == 1 and tool_messages[0]['tool_call_id'] == call_id
                assistant = next(item for item in body['messages'] if item.get('tool_calls'))
                assert assistant['tool_calls'][0]['id'] == call_id
                content = json.dumps(json.loads(tool_messages[0]['content']), sort_keys=True)
                if critic:
                    assert '"row_count": 6' in content
                    result = {'approved': True, 'issues': []}
                else:
                    assert 'Electronics' in content and 'Stationery' in content
                    result = {'sql': case['expected_sql'], 'explanation': 'Count all catalog products.'}
                message = {'role': 'assistant', 'content': json.dumps(result)}
        return httpx.Response(200, json={
            'id': f'call-{len(requests)}', 'object': 'chat.completion', 'created': 0,
            'model': body['model'], 'choices': [{'index': 0, 'finish_reason': finish, 'message': message}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}})

    def client_factory(**kwargs):
        return OpenAI(http_client=httpx.Client(transport=httpx.MockTransport(respond)), **kwargs)

    normalized = parallel.normalize_config(config)
    result = parallel.evaluate(normalized['models'][0], case, database, expected,
                               tmp_path / 'history.db', normalized, threading.Event(), client_factory)
    assert result['correct'], result['error']
    assert result['tool_calls'] == 2
    assert result['attempts'] == result['critique_rounds'] == 1
    assert result['stage_calls'] == {'classify': 1, 'generate': 2, 'critique': 2}
    assert result['http_attempts'] == len(requests) == 5
    assert [call['finish_reason'] for call in result['calls']] == [
        'stop', 'tool_calls', 'stop', 'tool_calls', 'stop']
    assert sum(call['usage']['input_tokens'] for call in result['calls']) == 50
    assert sum(call['usage']['output_tokens'] for call in result['calls']) == 25
    assert sum(call['usage']['estimated_cost_usd'] for call in result['calls']) == pytest.approx(.0001)
    assert database.path.read_bytes() == before


def test_checkpoint_only_repairs_an_unterminated_final_record(tmp_path):
    path = tmp_path / 'cases.jsonl'
    path.write_bytes(b'{"id": 1}\n{"id":')
    assert parallel.read_records(path) == [{'id': 1}]
    assert path.read_bytes() == b'{"id": 1}\n'
    path.write_bytes(b'{"id": 1}')
    assert parallel.read_records(path) == [{'id': 1}]
    assert path.read_bytes().endswith(b'\n')
    corrupt = b'{"id": 1}\n{invalid}\n'
    path.write_bytes(corrupt)
    with pytest.raises(ValueError, match='corruption'):
        parallel.read_records(path)
    assert path.read_bytes() == corrupt


def test_orphan_checkpoint_is_not_adopted(config, cases, tmp_path):
    (tmp_path / 'cases.jsonl').write_text('{}\n')
    with pytest.raises(ValueError, match='no manifest'):
        parallel.run_parallel(config, cases, tmp_path, dry_run=True)
    assert not (tmp_path / 'manifest.json').exists()


def test_resume_rejects_foreign_checkpoint_and_runtime_changes(config, cases, tmp_path, monkeypatch):
    requests = []
    parallel.run_parallel(config, cases, tmp_path, model_names=['A'], limit_cases=1,
                          client_factory=factory_for(requests), progress=None)
    original = (tmp_path / 'cases.jsonl').read_text()
    record = json.loads(original)
    record['model_id'] = 'foreign-model'
    (tmp_path / 'cases.jsonl').write_text(json.dumps(record) + '\n')
    with pytest.raises(ValueError, match='unknown model or case'):
        parallel.run_parallel(config, cases, tmp_path, dry_run=True)
    (tmp_path / 'cases.jsonl').write_text(original)
    monkeypatch.setattr(parallel.sqlite3, 'sqlite_version', 'different-runtime')
    with pytest.raises(ValueError, match='Resume refused'):
        parallel.run_parallel(config, cases, tmp_path, dry_run=True)
    assert len(requests) == 3


def test_completed_selection_resumes_without_credentials(config, cases, tmp_path, monkeypatch):
    requests = []
    factory = factory_for(requests)
    pilot = parallel.run_parallel(config, cases, tmp_path, model_names=['A'], limit_cases=1,
                                  client_factory=factory, progress=None)
    assert pilot['selection_complete']
    monkeypatch.delenv('BENCH_A_KEY')
    resumed = parallel.run_parallel(config, cases, tmp_path, model_names=['A'], limit_cases=1,
                                    client_factory=factory, progress=None)
    assert resumed['selection_complete']
    assert len(requests) == 3


def test_worker_crash_does_not_discard_other_models(config, cases, tmp_path, monkeypatch):
    evaluate = parallel.evaluate
    def crash(model, *args, **kwargs):
        if model['label'] == 'A':
            raise RuntimeError('worker failed secret-a')
        return evaluate(model, *args, **kwargs)
    monkeypatch.setattr(parallel, 'evaluate', crash)
    report = parallel.run_parallel(config, cases, tmp_path, workers=2, per_model_workers=1,
                                    client_factory=factory_for([]), progress=None)
    assert not report['selection_complete']
    assert report['models']['A']['completed_cases'] == 0
    assert report['models']['B']['completed_cases'] == 2
    records = [json.loads(line) for line in (tmp_path / 'cases.jsonl').read_text().splitlines()]
    blocked = next(record for record in records if record['model'] == 'A')
    assert blocked['error']['category'] == 'worker_failure'
    assert 'secret-a' not in (tmp_path / 'cases.jsonl').read_text()


def test_cleanup_error_preserves_paid_response_records(config, cases, tmp_path):
    factory = factory_for([])
    def client_factory(**kwargs):
        client = factory(**kwargs)
        close = client.close
        def bad_close():
            close()
            raise RuntimeError('cleanup failed')
        client.close = bad_close
        return client
    report = parallel.run_parallel(config, cases, tmp_path, model_names=['A'], limit_cases=1,
                                    client_factory=client_factory, progress=None)
    result = report['models']['A']['results'][0]
    assert result['correct']
    assert len(result['calls']) == 3
    assert result['cleanup_error']['message'] == 'cleanup failed'


def test_client_setup_failure_is_not_scored_as_model_error(config, cases, tmp_path):
    def broken_client(**kwargs):
        raise OSError('cannot initialize client with secret-a')
    report = parallel.run_parallel(config, cases, tmp_path, model_names=['A'], workers=1,
                                    per_model_workers=1, client_factory=broken_client, progress=None)
    assert report['models']['A']['completed_cases'] == 0
    assert not report['selection_complete']
    record = json.loads((tmp_path / 'cases.jsonl').read_text())
    assert record['error']['category'] == 'worker_setup'
    assert 'secret-a' not in (tmp_path / 'cases.jsonl').read_text()


def test_invalid_sdk_parameter_blocks_configuration_without_scoring_model(config, cases, tmp_path):
    config['models'][0]['request_kwargs'] = {'nonexistent_parameter': True}
    requests = []
    report = parallel.run_parallel(config, cases, tmp_path, model_names=['A'], workers=1,
                                    per_model_workers=1, client_factory=factory_for(requests), progress=None)
    assert requests == []
    assert report['models']['A']['completed_cases'] == 0
    record = json.loads((tmp_path / 'cases.jsonl').read_text())
    assert record['error']['category'] == 'provider_configuration'


@pytest.mark.parametrize('status', [408, 409])
def test_retryable_request_statuses_are_retried(config, cases, tmp_path, status):
    config['transport_retries'] = 1
    requests = []
    def fail(request, body, number):
        if number == 1:
            return httpx.Response(status, json={'error': {'message': 'retry'}})
    report = parallel.run_parallel(config, cases, tmp_path, model_names=['A'], limit_cases=1,
                                    client_factory=factory_for(requests, fail=fail), progress=None)
    assert report['models']['A']['results'][0]['correct']
    assert len(requests) == 4


@pytest.mark.parametrize('complete,interrupted,exit_code', [(True, False, 0), (False, False, 1), (False, True, 130)])
def test_cli_exit_status_tracks_requested_selection(tmp_path, monkeypatch, complete, interrupted, exit_code):
    config_path, cases_path = tmp_path / 'config.json', tmp_path / 'cases.json'
    config_path.write_text('{}')
    cases_path.write_text('[]')
    monkeypatch.setattr(parallel, 'run_parallel', lambda *args, **kwargs: {
        'models': {}, 'selection_complete': complete, 'interrupted': interrupted})
    assert parallel.main(['--config', str(config_path), '--cases', str(cases_path),
                          '--output-dir', str(tmp_path / 'output')]) == exit_code
