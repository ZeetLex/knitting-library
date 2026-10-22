"""Bounded, owner-approved HTTP benchmark; never retries an inference job.

Run against an isolated server, with a corpus containing six PNG files and
reference.json (page filename -> expected text). The reservation ledger is
persistent: restarting the tool cannot spend another 24 requests.
"""
import argparse
import json
from pathlib import Path
import re
import time
import unicodedata

import httpx


def words(text):
    # Formatting is excluded, content and ordering are retained. Hyphenated
    # abbreviations and numeric punctuation are inspected separately below.
    text = re.sub(r"\\([\\`*_{}\[\]()#+\-.!|>])", r"\1", text)
    return re.findall(r"\w+", unicodedata.normalize("NFC", text).casefold())


def distance(a, b):
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        following = [i]
        for j, y in enumerate(b, 1):
            following.append(min(following[-1] + 1, row[j] + 1, row[j - 1] + (x != y)))
        row = following
    return row[-1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--username', required=True)
    parser.add_argument('--password-file', type=Path, required=True)
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--resume', action='store_true', help='Continue only completed recorded variants; never repeat a reserved variant.')
    parser.add_argument('--variants', nargs='+', choices=['baseline', 'balanced', 'no-reasoning', 'high-detail'],
                        default=['baseline', 'balanced', 'no-reasoning', 'high-detail'])
    args = parser.parse_args()
    references = json.loads((args.corpus / 'reference.json').read_text(encoding='utf-8'))
    assert len(references) == 6, 'Exactly six reference pages are required.'
    ledger = args.report.with_suffix('.reservations.json')
    if ledger.exists() and not args.resume:
        raise SystemExit('A reservation ledger already exists. Inspect previous results; do not retry automatically.')
    record = {'reserved_page_requests': 0, 'runs': [], 'corpus': args.corpus.name, 'model': 'gpt-5.6-sol'}
    if args.resume:
        record = json.loads(args.report.read_text(encoding='utf-8'))
        assert json.loads(ledger.read_text())['reserved'] == record['reserved_page_requests']
        assert all(run['status'] == 'ready_to_review' for run in record['runs'])
    client = httpx.Client(base_url=args.url, timeout=120)
    login = client.post('/api/auth/login', json={'username': args.username, 'password': args.password_file.read_text()})
    login.raise_for_status()
    client.headers['X-CSRF-Token'] = client.cookies['knitting_csrf']
    models = client.get('/api/admin/ai/chatgpt').json().get('models', [])
    assert any(m['id'] == record['model'] for m in models), 'Requested model is unavailable.'
    if 'recipe_id' not in record:
        files = [('files', (name, (args.corpus / name).read_bytes(), 'image/png')) for name in references]
        recipe = client.post('/api/recipes', data={'title': 'Bounded transcription benchmark'}, files=files)
        recipe.raise_for_status()
        record['recipe_id'] = recipe.json()['id']
    recipe_id = record['recipe_id']
    variants = [('baseline', 'legacy', 'medium', 'original', '1'),
                ('balanced', 'formatted', 'low', 'original', '2'),
                ('no-reasoning', 'formatted', 'none', 'original', '2'),
                ('high-detail', 'formatted', 'low', 'high', '2')]
    for name, mode, reasoning, detail, concurrency in variants:
        if name not in args.variants:
            continue
        if any(run['name'] == name for run in record['runs']):
            continue
        assert record['reserved_page_requests'] + 6 <= 24
        settings = {'ai_enabled': 'true', 'ai_provider': 'chatgpt_subscription', 'ai_chatgpt_model': record['model'],
                    'ai_cleanup_enabled': 'false', 'ai_prompt_mode': 'default', 'ai_max_pages': '6',
                    'ai_chatgpt_mode': mode, 'ai_chatgpt_reasoning': reasoning,
                    'ai_chatgpt_detail': detail, 'ai_chatgpt_concurrency': concurrency}
        response = client.put('/api/admin/ai', json=settings); response.raise_for_status()
        record['reserved_page_requests'] += 6
        ledger.write_text(json.dumps({'reserved': record['reserved_page_requests'], 'cap': 24}))
        started = time.monotonic()
        response = client.post(f'/api/recipes/{recipe_id}/text-version/jobs', json={'language': 'en'})
        response.raise_for_status()
        job_id = response.json()['job']['id']
        record['runs'].append({'name': name, 'job_id': job_id, 'status': 'submitted'})
        args.report.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        first_page_seconds = None
        while time.monotonic() - started < 1800:
            queue = client.get('/api/work-queue').json()['ai_jobs']
            job = next(j for j in queue if j['id'] == job_id)
            if job.get('completed_pages', 0) and first_page_seconds is None:
                first_page_seconds = time.monotonic() - started
            if job['status'] not in ('queued', 'running'):
                break
            time.sleep(1)
        elapsed = time.monotonic() - started
        diagnostics = client.get(f'/api/admin/ai/chatgpt/jobs/{job_id}/diagnostics').json()
        run = {'name': name, 'job_id': job_id, 'settings': settings, 'status': job['status'],
               'elapsed_seconds': elapsed, 'first_page_seconds': first_page_seconds, 'diagnostics': diagnostics}
        record['runs'][-1] = run
        if job['status'] != 'ready_to_review':
            args.report.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
            raise SystemExit('Benchmark stopped without retry: ' + job['status'])
        session = client.get(f'/api/recipes/{recipe_id}/review-session').json()
        evaluations = []
        for page in session['pages']:
            reference = references[page['page_key']]
            actual = page['reviewed_text']
            expected_words, actual_words = words(reference), words(actual)
            expected_numbers = re.findall(r'\d+(?:[.,]\d+)?', reference)
            actual_numbers = re.findall(r'\d+(?:[.,]\d+)?', actual)
            evaluations.append({'page': page['page_key'], 'word_errors': distance(expected_words, actual_words),
                'reference_words': len(expected_words), 'numeric_sequence_exact': expected_numbers == actual_numbers,
                'reference': reference, 'actual': actual})
        run['pages'] = evaluations
        args.report.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({k: run[k] for k in ('name', 'status', 'elapsed_seconds', 'first_page_seconds')}), flush=True)
    assert sum(len(run['diagnostics']['requests']) for run in record['runs']) <= 24


if __name__ == '__main__':
    main()
