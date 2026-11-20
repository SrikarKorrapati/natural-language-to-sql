"""Parallel, resumable evaluation of the SQL agent; resume is automatic."""
from __future__ import annotations
import argparse
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import random
import sqlite3
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit
from dotenv import load_dotenv
from openai import APIConnectionError, APIStatusError, OpenAI
from app.agent import ModelResponseError, SQLAgent
from app.completion import parse_model_response
from app.db import History
from app.retrieval import Retriever
from benchmarks.run import SCHEMAS, load_database, rows_equal, validate_cases
ROOT = SCHEMAS.parent.parent


class ProviderConfigurationError(ValueError):
    """The SDK could not construct the configured request."""


def now():
    return datetime.now(timezone.utc).isoformat()


def normalize_config(raw):
    if not isinstance(raw, dict) or not isinstance(raw.get('models'), list) or not raw['models']:
        raise ValueError('Config requires a nonempty models list')
    config = {key: raw.get(key, default) for key, default in (
        ('max_repairs', 5), ('max_critiques', 3), ('max_tool_calls', 4),
        ('request_timeout_seconds', 120), ('transport_retries', 2))}
    for key, minimum in (('max_repairs', 0), ('max_critiques', 1), ('max_tool_calls', 0), ('transport_retries', 0)):
        if type(config[key]) is not int or config[key] < minimum:
            raise ValueError(f'{key} must be an integer of at least {minimum}')
    if config['transport_retries'] > 10:
        raise ValueError('transport_retries must be at most 10')
    if config['max_tool_calls'] > 20:
        raise ValueError('max_tool_calls must be at most 20')
    timeout = config['request_timeout_seconds']
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('request_timeout_seconds must be a positive finite number')
    if not isinstance(raw.get('request_kwargs', {}), dict):
        raise ValueError('request_kwargs must be an object')
    config['models'] = []
    for item in raw['models']:
        if not isinstance(item, dict) or not isinstance(item.get('provider'), dict):
            raise ValueError('Each model requires a provider object')
        model_id = item.get('model_id')
        provider = item['provider']
        label = item.get('label', model_id)
        url, key_env = provider.get('base_url'), provider.get('key_env')
        if any(not isinstance(value, str) or not value.strip() for value in (model_id, label, url, key_env)):
            raise ValueError('Model ID, label, provider URL, and key_env must be nonempty strings')
        try:
            parsed = urlsplit(url)
            valid_url = (parsed.scheme in {'https', 'http'} and parsed.hostname
                         and not (parsed.username or parsed.password or parsed.query or parsed.fragment))
            parsed.port  # Validate a supplied port before constructing the SDK client.
        except ValueError:
            valid_url = False
        if not valid_url or any(char.isspace() for char in url):
            raise ValueError('Invalid model or provider URL')
        if not key_env.isidentifier():
            raise ValueError('key_env must name an environment variable')
        if not isinstance(item.get('request_kwargs', {}), dict):
            raise ValueError('request_kwargs must be an object')
        kwargs = {**raw.get('request_kwargs', {}), **item.get('request_kwargs', {})}
        reserved = {'api_key','base_url','messages','model','stream','response_format','extra_headers','timeout',
                    'tools','tool_choice','parallel_tool_calls','functions','function_call'}
        if reserved.intersection(kwargs):
            raise ValueError('Reserved request_kwargs')
        if 'extra_body' in kwargs and (not isinstance(kwargs['extra_body'], dict)
                or reserved.union({'max_tokens', 'max_completion_tokens', 'n'}).intersection(kwargs['extra_body'])):
            raise ValueError('extra_body cannot override benchmark request fields')
        if 'max_tokens' in kwargs and 'max_completion_tokens' in kwargs:
            raise ValueError('Specify only one completion token limit')
        if 'max_tokens' not in kwargs:
            kwargs.setdefault('max_completion_tokens', 4096)
        for key in ('max_tokens', 'max_completion_tokens'):
            if key in kwargs and (type(kwargs[key]) is not int or kwargs[key] <= 0):
                raise ValueError(f'{key} must be a positive integer')
        if kwargs.get('n', 1) != 1 or type(kwargs.get('n', 1)) is not int:
            raise ValueError('The benchmark requires exactly one completion (n=1)')
        pricing = item.get('pricing', {})
        if not isinstance(pricing, dict) or any(
            value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0)
            for value in pricing.values()
        ):
            raise ValueError('Pricing must contain nonnegative finite numbers or null')
        try:
            json.dumps(kwargs, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError('request_kwargs must contain finite JSON values') from exc
        config['models'].append({'model_id': model_id, 'label': label,
            'provider': {'base_url': url.rstrip('/'), 'key_env': key_env},
            'request_kwargs': kwargs, 'pricing': pricing})
    if len({m['label'] for m in config['models']}) != len(config['models']):
        raise ValueError('Model labels must be unique')
    return config


def fingerprint(config, cases):
    paths = list((ROOT / 'app').rglob('*.py')) + [SCHEMAS.parent / 'run.py']
    paths += [SCHEMAS / (name + '.sql') for name in sorted({c['schema_id'] for c in cases})]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    hashes['benchmarks/parallel.py'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    runtime = {'python': sys.version, 'sqlite': sqlite3.sqlite_version,
               'openai': version('openai'), 'langgraph': version('langgraph')}
    data = json.dumps({'version': 2, 'config': config, 'cases': cases, 'code': hashes,
                       'runtime': runtime}, sort_keys=True)
    return hashlib.sha256(data.encode()).hexdigest(), hashes


def error_record(exc, secret=''):
    status = getattr(exc, 'status_code', None)
    category = 'execution'
    if isinstance(exc, (APIStatusError, APIConnectionError)):
        message = 'Provider request failed' + (f' (HTTP {status})' if status else ' (connection/timeout)')
        category = ('provider_connection' if status is None else
                    'provider_auth' if status in (401, 403) else
                    'provider_rate_limit' if status == 429 else
                    'provider_unavailable' if status >= 500 else 'provider_request')
    elif isinstance(exc, InterruptedError):
        message = 'Run interrupted before the next model request'
        category = 'interrupted'
    elif isinstance(exc, ProviderConfigurationError):
        message = 'Invalid provider request configuration'
        category = 'provider_configuration'
    else:
        message = str(exc)[:500]
        if isinstance(exc, ModelResponseError):
            category = 'model_response'
    if secret:
        message = message.replace(secret, '[REDACTED]')
    return {'type': type(exc).__name__, 'status_code': status, 'category': category, 'message': message}


def usage_record(response, pricing):
    usage = getattr(response, 'usage', None)
    data = usage.model_dump() if usage is not None else {}
    inp, out = data.get('prompt_tokens'), data.get('completion_tokens')
    cached = (data.get('prompt_tokens_details') or {}).get('cached_tokens')
    reasoning = (data.get('completion_tokens_details') or {}).get('reasoning_tokens')
    cost = data.get('cost')
    if not isinstance(cost, (int, float)) or cost < 0:
        cost = None
    estimate = None
    if inp is not None and out is not None and all(pricing.get(k) is not None for k in ('input_per_million','output_per_million')):
        cached_price = pricing.get('cached_input_per_million')
        if cached_price is None:
            cached_price = pricing['input_per_million']
        estimate = ((inp - (cached or 0)) * pricing['input_per_million']
            + (cached or 0) * cached_price
            + out * pricing['output_per_million']) / 1_000_000
    return {'input_tokens': inp, 'output_tokens': out, 'total_tokens': data.get('total_tokens'),
        'cached_input_tokens': cached, 'reasoning_tokens': reasoning,
        'provider_cost_usd': cost, 'estimated_cost_usd': estimate, 'raw': data}


class Recorder:
    def __init__(self, model, config, stop, client_factory):
        self.model, self.config, self.stop = model, config, stop
        self.key = os.environ[model['provider']['key_env']]
        self.calls, self.stage_calls = [], Counter()
        self.client = client_factory(api_key=self.key, base_url=model['provider']['base_url'],
            timeout=config['request_timeout_seconds'], max_retries=0)

    def callback(self, stage):
        def complete(model_id, messages, *, tools=None, tool_choice=None):
            self.stage_calls[stage] += 1
            logical_call = sum(self.stage_calls.values())
            tool_kwargs = {}
            if tools:
                tool_kwargs['tools'] = tools
                if tool_choice is not None:
                    tool_kwargs['tool_choice'] = tool_choice
            for attempt in range(self.config['transport_retries'] + 1):
                if self.stop.is_set():
                    raise InterruptedError()
                started = time.perf_counter()
                record = {'stage': stage, 'logical_call': logical_call, 'transport_attempt': attempt + 1,
                    'started_at': now(), 'requested_model': model_id}
                try:
                    response = self.client.chat.completions.create(model=model_id, messages=messages,
                        response_format={'type':'json_object'}, **tool_kwargs, **self.model['request_kwargs'])
                except Exception as exc:
                    record.update(service_latency_ms=round((time.perf_counter()-started)*1000,2),
                        succeeded=False, error=error_record(exc, self.key))
                    self.calls.append(record)
                    if isinstance(exc, (TypeError, ValueError)):
                        raise ProviderConfigurationError() from exc
                    status = getattr(exc, 'status_code', None)
                    transient = isinstance(exc, APIConnectionError) or isinstance(exc, APIStatusError) and (status in (408, 409, 429) or status >= 500)
                    if not transient or attempt == self.config['transport_retries']:
                        raise
                    delay = min(8, 0.5 * 2**attempt + random.uniform(0,0.25))
                    try:
                        delay = max(delay, min(30, float(exc.response.headers.get('retry-after', 0))))
                    except (AttributeError, TypeError, ValueError):
                        pass
                    if self.stop.wait(delay):
                        raise InterruptedError()
                    continue
                finish_reason = (getattr(response.choices[0], 'finish_reason', None)
                    if isinstance(response.choices, list) and response.choices else None)
                record.update(service_latency_ms=round((time.perf_counter()-started)*1000,2),
                    succeeded=True, response_id=response.id, response_model=response.model,
                    finish_reason=finish_reason,
                    usage=usage_record(response, self.model['pricing']))
                self.calls.append(record)
                return parse_model_response(response, allow_tools=bool(tools) and tool_choice != 'none')
        complete.supports_tools = True
        return complete


def initial_result(model, case):
    return {'model':model['label'], 'model_id':model['model_id'], 'id':case['id'],
        'schema_id':case['schema_id'], 'difficulty':case.get('difficulty'), 'question':case['question'],
        'status':'completed', 'valid_sql':False, 'correct':False, 'attempts':0, 'sql':None,
        'retrieval_mode':None, 'input_valid':None, 'classification_explanation':None,
        'critique_rounds':0, 'critique_approved':None, 'critique_issues':[], 'tool_calls':0,
        'error':None, 'started_at':now()}


def evaluate(model, case, database, expected, history_path, config, stop, client_factory):
    result = initial_result(model, case)
    recorder = None
    setup_complete = False
    started = time.perf_counter()
    try:
        history = History(history_path, dataset=str(database.path))
        recorder = Recorder(model, config, stop, client_factory)
        agent = SQLAgent(database, history, complete=recorder.callback('generate'),
            classify_complete=recorder.callback('classify'), critique_complete=recorder.callback('critique'),
            retriever=Retriever(), max_repairs=config['max_repairs'], max_critiques=config['max_critiques'],
            max_tool_calls=config['max_tool_calls'])
        setup_complete = True
        started = time.perf_counter()
        proposal = agent.propose(case['question'], 'benchmark', model['model_id'])
        for field in ('sql','attempts','retrieval_mode','input_valid','classification_explanation',
                      'critique_rounds','critique_approved','critique_issues','tool_calls'):
            result[field] = proposal.get(field)
        if proposal['sql'] is None:
            raise ValueError('No SQL generated: ' + proposal['explanation'])
        database.validate(proposal['sql'])
        result['valid_sql'] = True
        actual = database.execute(proposal['sql'])
        if actual['truncated']:
            raise ValueError('Generated result is truncated.')
        result['correct'] = len(actual['columns']) == len(expected['columns']) and rows_equal(
            actual['rows'], expected['rows'], case.get('order_sensitive',False))
    except Exception as exc:
        result['error'] = error_record(exc, os.environ.get(model['provider']['key_env'], ''))
        if isinstance(exc, (APIStatusError, APIConnectionError, ProviderConfigurationError)):
            # Infrastructure failures remain resumable, excluded from model accuracy.
            result['status'] = 'blocked'
        elif isinstance(exc, InterruptedError):
            result['status'] = 'interrupted'
        elif not setup_complete:
            result['status'] = 'blocked'
            result['error']['category'] = 'worker_setup'
        elif not isinstance(exc, (ModelResponseError, sqlite3.Error, ValueError)):
            result['status'] = 'blocked'
            result['error']['category'] = 'worker_failure'
    finally:
        result['latency_ms'] = round((time.perf_counter()-started)*1000,2)
        result['finished_at'] = now()
        result['calls'] = recorder.calls if recorder else []
        result['stage_calls'] = dict(recorder.stage_calls) if recorder else {}
        result['http_attempts'] = len(result['calls'])
        if recorder:
            try:
                recorder.client.close()
            except Exception as exc:
                # A cleanup failure must not discard paid responses and their usage.
                result['cleanup_error'] = error_record(exc, recorder.key)
    return result


def atomic_json(path, data):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    temp.replace(path)


@contextmanager
def locked_output(path):
    path.mkdir(parents=True, exist_ok=True)
    with (path / '.runner.lock').open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('Another process is using this output directory') from exc
        yield


def read_records(path):
    if not path.exists():
        return []
    records = []
    with path.open('rb+') as handle:
        while True:
            offset = handle.tell()
            line = handle.readline()
            if not line:
                break
            try:
                records.append(json.loads(line))
                if not line.endswith(b'\n'):
                    handle.seek(0, 2)
                    handle.write(b'\n')
            except (json.JSONDecodeError, UnicodeDecodeError):
                if line.endswith(b'\n') or handle.read():
                    raise ValueError('Checkpoint corruption in a complete record')
                handle.seek(offset)
                handle.truncate()
                break
    return records


def validate_records(records, config, cases):
    """Do not skip paid work based on a foreign or malformed checkpoint."""
    models = {model['label']: model['model_id'] for model in config['models']}
    schemas = {case['id']: case['schema_id'] for case in cases}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError('Checkpoint records must be objects')
        label, case_id = record.get('model'), record.get('id')
        if (not isinstance(label, str) or label not in models
                or not isinstance(case_id, str) or case_id not in schemas
                or record.get('model_id') != models[label]
                or record.get('schema_id') != schemas[case_id]):
            raise ValueError('Checkpoint contains an unknown model or case')
        if (not isinstance(record.get('status'), str)
                or record['status'] not in {'completed', 'blocked', 'interrupted'}
                or any(type(record.get(field)) is not bool for field in ('correct', 'valid_sql'))
                or 'input_valid' not in record
                or (record['input_valid'] is not None and type(record['input_valid']) is not bool)
                or type(record.get('latency_ms')) not in (int, float)
                or not math.isfinite(record['latency_ms']) or record['latency_ms'] < 0
                or not isinstance(record.get('calls'), list)
                or any(not isinstance(call, dict) for call in record['calls'])):
            raise ValueError('Checkpoint contains a malformed result')
        for call in record['calls']:
            usage = call.get('usage')
            if usage is not None and (not isinstance(usage, dict) or any(
                usage.get(field) is not None and (type(usage[field]) not in (int, float)
                    or not math.isfinite(usage[field]) or usage[field] < 0)
                for field in ('input_tokens', 'output_tokens', 'cached_input_tokens', 'reasoning_tokens',
                              'provider_cost_usd', 'estimated_cost_usd')
            )):
                raise ValueError('Checkpoint contains malformed usage')


def aggregate(config, cases, records, identity, interrupted=False, blocked=()):
    latest = {(r['model'], r['id']):r for r in records}
    order = {case['id']:i for i,case in enumerate(cases)}
    report = {'updated_at':now(), 'fingerprint':identity, 'interrupted':interrupted,
        'blocked_models':sorted(blocked), 'models':{}}
    for model in config['models']:
        label = model['label']
        results = sorted((r for (name,_),r in latest.items() if name == label and r['status'] == 'completed'), key=lambda r:order[r['id']])
        calls = [call for r in records if r['model'] == label for call in r['calls']]
        usages = [c['usage'] for c in calls if c.get('usage') is not None]
        totals = {}
        for field in ('input_tokens','output_tokens','cached_input_tokens','reasoning_tokens','provider_cost_usd','estimated_cost_usd'):
            values = [u[field] for u in usages if u.get(field) is not None]
            totals[field] = sum(values) if values else None
            totals[field + '_complete'] = bool(calls) and len(values) == len(calls)
        n = len(results)
        latencies = sorted(r['latency_ms'] for r in results)
        by_difficulty = {}
        for level in sorted({case.get('difficulty') or 'unspecified' for case in cases}):
            subset = [r for r in results if (r.get('difficulty') or 'unspecified') == level]
            by_difficulty[level] = {'cases':len(subset), 'correct':sum(r['correct'] for r in subset),
                'execution_accuracy':sum(r['correct'] for r in subset)/len(subset) if subset else None}
        report['models'][label] = {'model_id':model['model_id'], 'completed_cases':n, 'total_cases':len(cases),
            'status':'complete' if n == len(cases) else 'partial',
            'execution_accuracy':sum(r['correct'] for r in results)/n if n else None,
            'valid_sql_rate':sum(r['valid_sql'] for r in results)/n if n else None,
            'classifier_acceptance_rate':sum(r['input_valid'] is True for r in results)/n if n else None,
            'average_latency_ms':round(sum(latencies)/n,2) if n else None,
            'p50_latency_ms':latencies[(n-1)//2] if n else None,
            'p95_latency_ms':latencies[min(n-1,int(n*.95))] if n else None,
            'http_attempts':len(calls), 'usage':totals, 'by_difficulty':by_difficulty, 'results':results}
    return report


def run_parallel(raw_config, cases, output_dir, *, model_names=None, limit_cases=None, case_ids=None,
                 workers=24, per_model_workers=3, dry_run=False, client_factory=OpenAI, progress=print):
    config = normalize_config(raw_config)
    if type(workers) is not int or type(per_model_workers) is not int or workers < 1 or per_model_workers < 1:
        raise ValueError('Worker limits must be positive')
    validate_cases(cases)
    requested = set(model_names or [])
    models = [m for m in config['models'] if not requested or m['label'] in requested or m['model_id'] in requested]
    if requested - {name for m in models for name in (m['label'],m['model_id'])}:
        raise ValueError('Unknown --models entry')
    selected = [c for c in cases if not case_ids or c['id'] in set(case_ids)]
    if case_ids and set(case_ids) - {c['id'] for c in cases}:
        raise ValueError('Unknown --case-ids entry')
    if limit_cases is not None:
        if type(limit_cases) is not int or limit_cases < 1:
            raise ValueError('--limit-cases must be positive')
        selected = selected[:limit_cases]
    identity, hashes = fingerprint(config, cases)
    output_dir = Path(output_dir)
    with locked_output(output_dir), tempfile.TemporaryDirectory(prefix='nl2sql-parallel-') as temp:
        manifest_path = output_dir / 'manifest.json'
        checkpoint_path = output_dir / 'cases.jsonl'
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            if manifest['fingerprint'] != identity:
                raise ValueError('Resume refused: config/source/dataset changed; use a new output directory')
        else:
            if checkpoint_path.exists() and checkpoint_path.stat().st_size:
                raise ValueError('Resume refused: checkpoint has no manifest; use a new output directory')
            manifest = {'created_at':now(), 'fingerprint':identity, 'config':config,
                'source_hashes':hashes, 'dataset_cases':len(cases), 'launches':[]}
        manifest['launches'].append({'at':now(), 'workers':workers, 'per_model_workers':per_model_workers,
            'models':[m['label'] for m in models], 'case_ids':[c['id'] for c in selected], 'dry_run':dry_run})
        atomic_json(manifest_path, manifest)
        root = Path(temp)
        databases = {schema_id:load_database(schema_id,root) for schema_id in sorted({c['schema_id'] for c in cases})}
        expected = {}
        for case in cases:
            result = databases[case['schema_id']].execute(case['expected_sql'])
            if result['truncated']:
                raise ValueError('Truncated reference: ' + case['id'])
            expected[case['id']] = result
        records = read_records(checkpoint_path)
        validate_records(records, config, cases)
        latest = {(r['model'],r['id']):r for r in records}
        pending_cases = {m['label']:[c for c in selected if (m['label'],c['id']) not in latest or latest[(m['label'],c['id'])]['status'] != 'completed'] for m in models}
        if dry_run:
            plan = {'fingerprint':identity, 'models':len(models), 'cases_per_model':len(selected),
                'pending_cases':sum(len(items) for items in pending_cases.values()),
                'schemas_validated':len(databases), 'references_validated':len(expected), 'dry_run':True}
            atomic_json(output_dir / 'dry-run.json',plan)
            return plan
        missing = sorted({m['provider']['key_env'] for m in models if pending_cases[m['label']] and not os.environ.get(m['provider']['key_env'])})
        if missing:
            raise ValueError('Missing credential environment variables: ' + ', '.join(missing))
        report = schedule(config,cases,models,{label:iter(items) for label,items in pending_cases.items()},
            databases,expected,root,records,checkpoint_path,output_dir,identity,workers,per_model_workers,
            client_factory,progress)
        wanted = {case['id'] for case in selected}
        report['selection_complete'] = all(wanted <= {r['id'] for r in report['models'][model['label']]['results']}
                                           for model in models)
        atomic_json(output_dir / 'results.json', report)
        return report


def schedule(config,cases,models,pending,databases,expected,root,records,checkpoint_path,output_dir,
             identity,workers,per_model_workers,client_factory,progress):
    stop = threading.Event()
    running, active, exhausted, blocked = {}, Counter(), set(), set()
    cursor, interrupted = 0, False
    with checkpoint_path.open('a') as checkpoint, ThreadPoolExecutor(max_workers=workers) as pool:
        while True:
            try:
                misses = 0
                while len(running) < workers and not stop.is_set() and misses < len(models):
                    model = models[cursor % len(models)]
                    cursor += 1
                    label = model['label']
                    if label in exhausted or label in blocked or active[label] >= per_model_workers:
                        misses += 1
                        continue
                    case = next(pending[label], None)
                    if case is None:
                        exhausted.add(label)
                        misses += 1
                        continue
                    misses = 0
                    token = hashlib.sha256((label + '\0' + case['id']).encode()).hexdigest()[:24]
                    future = pool.submit(evaluate,model,case,databases[case['schema_id']],expected[case['id']],
                        root / ('history-' + token + '.db'),config,stop,client_factory)
                    running[future] = (model, case, time.perf_counter())
                    active[label] += 1
                if not running:
                    break
                finished,_ = wait(running,timeout=.25,return_when=FIRST_COMPLETED)
                for future in finished:
                    model, case, started = running.pop(future)
                    label = model['label']
                    active[label] -= 1
                    try:
                        record = future.result()
                    except Exception as exc:
                        # Preserve other in-flight results if a worker itself crashes.
                        record = initial_result(model, case)
                        record.update(status='blocked', finished_at=now(), calls=[], stage_calls={},
                                      http_attempts=0, latency_ms=round((time.perf_counter()-started)*1000, 2),
                                      error=error_record(exc, os.environ.get(model['provider']['key_env'], '')))
                        record['error']['category'] = 'worker_failure'
                    records.append(record)
                    checkpoint.write(json.dumps(record,ensure_ascii=False) + '\n')
                    checkpoint.flush()
                    os.fsync(checkpoint.fileno())
                    if record['status'] == 'blocked':
                        blocked.add(label)
                    atomic_json(output_dir / 'results.json',aggregate(config,cases,records,identity,interrupted,blocked))
                    if progress:
                        progress(f"{label} {record['id']}: {record['status']} / {'correct' if record['correct'] else 'failed'} ({record['latency_ms']:.0f} ms)")
            except KeyboardInterrupt:
                interrupted = True
                stop.set()
                if progress:
                    progress('Stopping new requests; checkpointing in-flight cases…')
    report = aggregate(config,cases,records,identity,interrupted,blocked)
    atomic_json(output_dir / 'results.json',report)
    return report


def main(argv=None):
    load_dotenv(ROOT / '.env',override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--cases',type=Path,default=SCHEMAS.parent / 'cases.json')
    parser.add_argument('--models',nargs='+')
    parser.add_argument('--workers',type=int,default=24)
    parser.add_argument('--per-model-workers',type=int,default=3)
    parser.add_argument('--limit-cases',type=int)
    parser.add_argument('--case-ids',nargs='+')
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--resume',action='store_true',help='Resume is automatic; flag accepted for clarity')
    args = parser.parse_args(argv)
    try:
        report = run_parallel(json.loads(args.config.read_text()),json.loads(args.cases.read_text()),args.output_dir,
            model_names=args.models,limit_cases=args.limit_cases,case_ids=args.case_ids,workers=args.workers,
            per_model_workers=args.per_model_workers,dry_run=args.dry_run)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    if args.dry_run:
        print(json.dumps(report,indent=2))
    else:
        for label,summary in report['models'].items():
            value = summary['execution_accuracy']
            score = f'{value:.1%}' if value is not None else 'pending'
            print(f"{label}: {summary['completed_cases']}/{summary['total_cases']} cases; accuracy {score}")
        print(f"Results: {args.output_dir / 'results.json'}")
    if report.get('interrupted'):
        return 130
    return 0 if args.dry_run or report.get('selection_complete') else 1


if __name__ == '__main__':
    raise SystemExit(main())
