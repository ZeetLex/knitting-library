import asyncio
import concurrent.futures
import contextlib
import importlib
import io
import json
from pathlib import Path
import tempfile
import time
import threading
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.core import foundation
from app.ai import jobs, chatgpt_connection as connection, chatgpt_protocol as protocol
from app.service_registry import SERVICE_MODULES


class SubscriptionScenarios(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.root.joinpath('recipes').mkdir()
        self.root.joinpath('yarns').mkdir()
        for name in SERVICE_MODULES:
            module = importlib.import_module(name)
            for key, value in {'DB_PATH': self.root / 'test.db', 'DATA_DIR': self.root / 'recipes',
                               'YARN_DIR': self.root / 'yarns', 'DATA_ROOT': self.root}.items():
                if hasattr(module, key):
                    self.stack.enter_context(patch.object(module, key, value))
        self.stack.enter_context(patch.object(connection, 'DATA_ROOT', self.root))
        self.stack.enter_context(patch.object(jobs, '_ensure_ai_queue_processor', lambda: None))
        foundation.init_db()
        self.owner = TestClient(app)
        response = self.owner.post('/api/setup/admin', json={'username': 'owner', 'password': 'subscription-test-password'})
        self.assertEqual(response.status_code, 200)
        self.owner_id = response.json()['user']['id']
        self.owner.headers['X-CSRF-Token'] = self.owner.cookies['knitting_csrf']
        self.other_id = self.owner.post('/api/admin/users', json={'username': 'household', 'password': 'subscription-test-password'}).json()['id']
        self.other = TestClient(app)
        self.assertEqual(self.other.post('/api/auth/login', json={'username': 'household', 'password': 'subscription-test-password'}).status_code, 200)
        self.other.headers['X-CSRF-Token'] = self.other.cookies['knitting_csrf']
        buf = io.BytesIO()
        Image.new('RGB', (60, 90), 'white').save(buf, 'PNG')
        response = self.owner.post('/api/recipes', data={'title': 'Subscription recipe'}, files=[
            ('files', ('first.png', buf.getvalue(), 'image/png')),
            ('files', ('second.png', buf.getvalue(), 'image/png')),
        ])
        self.assertEqual(response.status_code, 200)
        self.recipe_id = response.json()['id']
        self.credentials = {'access_token': 'test-access-secret', 'refresh_token': 'test-refresh-secret',
                            'id_token': 'test-id', 'client_id': 'issued-client', 'scope': protocol.SCOPES, 'expires_at': time.time() + 3600}
        with connection.locked():
            connection._write('connection', {'connection_id': 'connection-one', 'owner_id': self.owner_id, 'owner_name': 'owner',
                'email': 'test@example.invalid', 'subject': 'subject', 'credentials': self.credentials,
                'health': 'connected', 'models': [{'id': 'test-model', 'name': 'Test model'}]})
        self.save_settings()

    def save_settings(self, **changes):
        values = {'ai_enabled': 'true', 'ai_provider': 'chatgpt_subscription', 'ai_chatgpt_model': 'test-model',
                  'ai_chatgpt_mode': 'legacy', 'ai_chatgpt_concurrency': '1',
                  'ai_cleanup_enabled': 'false', **changes}
        self.assertEqual(self.owner.put('/api/admin/ai', json=values).status_code, 200)

    def enqueue(self, actor=None):
        response = (actor or self.other).post(f'/api/recipes/{self.recipe_id}/text-version/jobs', json={'language': 'no'})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['job']

    def row(self, job_id):
        conn = foundation.get_db()
        try:
            return dict(conn.execute('SELECT * FROM ai_text_jobs WHERE id=?', (job_id,)).fetchone())
        finally:
            conn.close()

    def context(self, job_id):
        return next(job for job in self.owner.get('/api/work-queue').json()['ai_jobs'] if job['id'] == job_id)

    def approve(self, job_id):
        context = self.context(job_id)
        response = self.owner.post(f'/api/work-queue/ai/{job_id}/approve', json={'approval_token': context['approval_token']})
        self.assertEqual(response.status_code, 200, response.text)

    def run_job(self, job_id, side_effect=None):
        with patch.object(connection, 'request', side_effect=side_effect,
                          return_value={'text': 'Recipe text', 'usage': {'prompt_tokens': 5, 'completion_tokens': 3, 'total_tokens': 8}}) as request:
            asyncio.run(jobs._run_ai_text_job(job_id))
        return request

    def test_household_waits_and_direct_endpoints_cannot_bypass(self):
        job = self.enqueue()
        self.assertEqual(job['status'], 'awaiting_approval')
        self.assertNotIn('config_snapshot', job)
        self.assertNotIn('checkpoint_json', job)
        self.assertEqual(self.enqueue()['id'], job['id'])
        self.assertEqual(self.other.post(f"/api/work-queue/ai/{job['id']}/approve", json={}).status_code, 403)
        direct = self.other.post(f'/api/recipes/{self.recipe_id}/text-version/generate', json={})
        self.assertEqual(direct.status_code, 200)
        self.assertEqual(direct.json()['job']['id'], job['id'])
        with patch.object(connection, 'request') as request:
            asyncio.run(jobs._run_ai_text_job(job['id']))
            request.assert_not_called()
        self.assertTrue(self.other.get(f'/api/recipes/{self.recipe_id}/text-version').json()['requires_owner_approval'])

    def test_owner_approval_runs_scanning_and_cleanup_and_records_usage(self):
        self.save_settings(ai_cleanup_enabled='true')
        job = self.enqueue()
        self.approve(job['id'])
        request = self.run_job(job['id'])
        self.assertEqual(request.call_count, 4)
        self.assertEqual(self.row(job['id'])['status'], 'ready_to_review')
        conn = foundation.get_db()
        usage = conn.execute('SELECT * FROM ai_usage_events WHERE job_id=?', (job['id'],)).fetchone()
        self.assertEqual(usage['total_tokens'], 32)
        conn.close()

    def test_owner_submission_is_immediately_approved(self):
        job = self.enqueue(self.owner)
        self.assertEqual(job['status'], 'queued')
        self.assertEqual(self.row(job['id'])['approved_by'], self.owner_id)

    def test_stale_confirmation_cannot_approve_changed_settings(self):
        job = self.enqueue()
        context = self.context(job['id'])
        self.save_settings(ai_cleanup_enabled='true')
        response = self.owner.post(f"/api/work-queue/ai/{job['id']}/approve", json={'approval_token': context['approval_token']})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.row(job['id'])['status'], 'awaiting_approval')

    def test_source_change_invalidates_existing_approval(self):
        job = self.enqueue(self.owner)
        path = self.root / 'recipes' / self.recipe_id / 'first.png'
        Image.new('RGB', (70, 90), 'blue').save(path)
        request = self.run_job(job['id'])
        request.assert_not_called()
        self.assertEqual(self.row(job['id'])['status'], 'awaiting_approval')

    def test_partial_pages_survive_usage_limit_and_are_not_sent_twice(self):
        job = self.enqueue(self.owner)
        response = {'text': 'First page', 'usage': {'prompt_tokens': 5, 'completion_tokens': 3, 'total_tokens': 8}}
        self.run_job(job['id'], [response, protocol.ChatGPTError('subscription_sharing_usage_limit_exceeded')])
        first = self.row(job['id'])
        self.assertEqual(first['status'], 'blocked_usage')
        self.assertEqual(len(json.loads(first['checkpoint_json'])), 1)
        self.approve(job['id'])
        request = self.run_job(job['id'])
        self.assertEqual(request.call_count, 1)
        self.assertEqual(self.row(job['id'])['status'], 'ready_to_review')
        conn = foundation.get_db()
        usage = conn.execute('SELECT * FROM ai_usage_events WHERE job_id=?', (job['id'],)).fetchall()
        self.assertEqual(len(usage), 1)
        self.assertIsNone(usage[0]['total_tokens'])  # failed attempt usage is unknown
        known = conn.execute("SELECT SUM(total_tokens) FROM ai_request_metrics WHERE job_id=?", (job['id'],)).fetchone()[0]
        self.assertEqual(known, 16)
        conn.close()

    def test_setting_change_during_scan_stops_the_next_request(self):
        job = self.enqueue(self.owner)
        def response(*args, **kwargs):
            self.save_settings(ai_cleanup_enabled='true')
            return {'text': 'First page', 'usage': {'total_tokens': 8}}
        request = self.run_job(job['id'], response)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(self.row(job['id'])['status'], 'awaiting_approval')

    def test_cancelled_and_disabled_jobs_do_not_spend(self):
        job = self.enqueue(self.owner)
        self.assertEqual(self.owner.post(f"/api/work-queue/ai/{job['id']}/cancel").status_code, 200)
        self.run_job(job['id']).assert_not_called()
        self.save_settings(ai_enabled='false')
        self.assertEqual(self.owner.post(f'/api/recipes/{self.recipe_id}/text-version/jobs', json={}).status_code, 400)

    def test_container_restart_does_not_auto_retry_subscription_jobs(self):
        job = self.enqueue(self.owner)
        conn = foundation.get_db()
        conn.execute("UPDATE ai_text_jobs SET status='running' WHERE id=?", (job['id'],))
        conn.commit()
        conn.close()
        from app.ai import request_metrics
        attempt, _ = request_metrics.start(job['id'],1,'scan','test-model',{},0)
        foundation.init_db()
        self.assertEqual(self.row(job['id'])['status'], 'interrupted')
        self.assertIsNone(json.loads(self.row(job['id'])['provider_usage_json'])['total_tokens'])
        conn = foundation.get_db()
        self.assertEqual(conn.execute('SELECT outcome FROM ai_request_metrics WHERE id=?',(attempt,)).fetchone()[0], 'interrupted')
        conn.close()

    def test_non_owner_cannot_test_inference_or_access_credentials(self):
        self.assertEqual(self.other.get('/api/admin/ai/chatgpt').status_code, 403)
        result = self.owner.get('/api/admin/ai/chatgpt')
        self.assertNotIn('test-access-secret', result.text)
        self.assertNotIn('test-refresh-secret', result.text)
        self.assertNotIn('credentials', result.text)
        self.assertNotIn(b'test-access-secret', (self.root / '.chatgpt/connection.enc').read_bytes())

    def test_encrypted_import_is_single_use_and_keeps_host_id(self):
        setup = connection.begin_setup({'id': self.owner_id, 'username': 'owner'})
        host_id = setup['host_id']
        envelope = protocol.seal_connection(setup, self.credentials)
        with patch.object(protocol, 'validate_identity', return_value={'subject': 'subject', 'email': 'test@example.invalid'}), \
             patch.object(protocol, 'refresh_credentials', return_value=self.credentials), \
             patch.object(protocol, 'list_models', return_value=[{'id': 'test-model', 'name': 'Test'}]):
            imported = connection.import_connection(envelope, {'id': self.owner_id, 'username': 'owner'})
            self.assertTrue(imported['connected'])
            with self.assertRaises(protocol.ChatGPTError):
                connection.import_connection(envelope, {'id': self.owner_id, 'username': 'owner'})
        self.assertEqual(connection.begin_setup({'id': self.owner_id, 'username': 'owner'})['host_id'], host_id)

    def test_concurrent_refreshes_rotate_only_once(self):
        with connection.locked():
            record = connection._read('connection')
            record['credentials']['expires_at'] = 0
            connection._write('connection', record)
        replacement = {**self.credentials, 'access_token': 'renewed', 'refresh_token': 'rotated'}
        with patch.object(protocol, 'refresh_credentials', return_value=replacement) as refresh:
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(lambda _: connection.access_token('connection-one'), range(4)))
        self.assertEqual(results, ['renewed'] * 4)
        self.assertEqual(refresh.call_count, 1)
        self.assertEqual(connection.connection()['credentials']['refresh_token'], 'rotated')

    def test_disconnect_attempts_revocation_and_removes_connection(self):
        from unittest.mock import Mock
        with patch.object(connection.httpx, 'get', return_value=Mock(json=lambda: {
                'revocation_endpoint': protocol.AUTH_ORIGIN + '/oauth/revoke'})), \
             patch.object(connection.httpx, 'post', return_value=Mock(status_code=200)) as revoke:
            response = self.owner.delete('/api/admin/ai/chatgpt')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['revocation_confirmed'])
        revoke.assert_called_once()
        self.assertFalse(connection.status()['connected'])
        self.assertFalse((self.root / '.chatgpt/connection.enc').exists())

    def test_household_cannot_hide_another_owners_job(self):
        job = self.enqueue(self.owner)
        conn = foundation.get_db()
        conn.execute("UPDATE ai_text_jobs SET status='interrupted' WHERE id=?", (job['id'],))
        conn.commit()
        conn.close()
        self.assertEqual(self.other.post(f"/api/work-queue/ai/{job['id']}/dismiss").status_code, 403)

    def test_static_traversal_cannot_serve_runtime_credentials(self):
        from app.core import static
        from starlette.requests import Request
        from starlette.responses import Response
        async def not_found(request):
            return Response(status_code=404)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'public').mkdir()
            (root / 'secret').write_text('private-credential')
            with patch.object(static, 'STATIC_DIR', root / 'public'), patch.object(static, '_static_app', object()):
                request = Request({'type': 'http', 'path': '/../secret', 'method': 'GET', 'headers': []})
                result = asyncio.run(static.spa_static_middleware(request, not_found))
                self.assertEqual(result.status_code, 404)

    def test_formatted_parallel_pages_finish_out_of_order_without_lost_usage(self):
        self.save_settings(ai_chatgpt_mode='formatted', ai_chatgpt_concurrency='2', ai_cleanup_enabled='true')
        job = self.enqueue(self.owner)
        second_started = threading.Event()
        state = {'active': 0, 'maximum': 0}
        lock = threading.Lock()
        def response(model, prompt, *args, **kwargs):
            with lock:
                state['active'] += 1
                state['maximum'] = max(state['maximum'], state['active'])
            try:
                if 'Page 1/2.' in prompt:
                    self.assertTrue(second_started.wait(3))
                    time.sleep(.03)
                    text = 'First page'
                else:
                    second_started.set()
                    text = 'Second page'
                self.assertEqual(kwargs['reasoning'], 'low')
                self.assertEqual(kwargs['detail'], 'original')
                return {'text': text, 'usage': {'prompt_tokens': 5, 'completion_tokens': 3, 'total_tokens': 8},
                        'token_details': {'reasoning_tokens': 1, 'cached_tokens': 0}}
            finally:
                with lock: state['active'] -= 1
        request = self.run_job(job['id'], response)
        self.assertEqual(request.call_count, 2)  # formatted mode never runs cleanup
        self.assertEqual(state['maximum'], 2)
        row = self.row(job['id'])
        self.assertEqual(row['status'], 'ready_to_review')
        self.assertEqual(row['active_pages_json'], '[]')
        self.assertEqual([p['reviewed_text'] for p in json.loads(row['checkpoint_json'])], ['First page', 'Second page'])
        diagnostics = self.owner.get(f"/api/admin/ai/chatgpt/jobs/{job['id']}/diagnostics").json()
        self.assertEqual(diagnostics['usage']['total_tokens'], 16)
        self.assertEqual(diagnostics['usage']['reasoning_tokens'], 2)
        self.assertEqual(len(diagnostics['requests']), 2)
        self.assertNotIn('First page', json.dumps(diagnostics))
        self.assertEqual(self.other.get(f"/api/admin/ai/chatgpt/jobs/{job['id']}/diagnostics").status_code, 403)
        session = self.owner.get(f'/api/recipes/{self.recipe_id}/review-session').json()
        self.assertEqual(session['format_version'], 'gfm-v1')
        for page in session['pages']:
            self.owner.put(f"/api/review-sessions/{session['id']}/pages/{page['id']}",json={'reviewed_text':page['reviewed_text'],'status':'accepted'}).raise_for_status()
        self.owner.post(f"/api/review-sessions/{session['id']}/complete").raise_for_status()
        published = self.owner.get(f'/api/recipes/{self.recipe_id}/text-version').json()
        self.assertEqual(published['content_markdown'], 'First page\n\nSecond page')
        self.assertEqual(published['format_version'], 'gfm-v1')
        self.assertEqual(self.row(job['id'])['status'],'finished')

    def test_parallel_failure_settles_inflight_and_does_not_dispatch_next_page(self):
        Image.new('RGB', (60,90), 'white').save(self.root / 'recipes' / self.recipe_id / 'third.png')
        self.save_settings(ai_chatgpt_mode='formatted', ai_chatgpt_concurrency='2')
        job = self.enqueue(self.owner)
        second_failed = threading.Event()
        def response(model, prompt, *args, **kwargs):
            if 'Page 1/3.' in prompt:
                self.assertTrue(second_failed.wait(3))
                time.sleep(.05)
                return {'text':'Preserved first page','usage':{'total_tokens':8}}
            second_failed.set()
            raise protocol.ChatGPTError('usage_limited')
        request = self.run_job(job['id'], response)
        self.assertEqual(request.call_count, 2)
        row = self.row(job['id'])
        self.assertEqual(row['status'], 'blocked_usage')
        self.assertEqual(len(json.loads(row['checkpoint_json'])), 1)
        self.assertEqual(row['active_pages_json'], '[]')

    def test_processing_changes_require_fresh_owner_approval(self):
        job = self.enqueue()
        for key,value in [('ai_chatgpt_mode','formatted'), ('ai_chatgpt_reasoning','medium'),
                          ('ai_chatgpt_detail','high'), ('ai_chatgpt_concurrency','2')]:
            self.save_settings(ai_chatgpt_mode='legacy', ai_chatgpt_reasoning='low', ai_chatgpt_detail='original', ai_chatgpt_concurrency='1')
            context = self.context(job['id'])
            self.save_settings(**{key:value})
            response = self.owner.post(f"/api/work-queue/ai/{job['id']}/approve", json={'approval_token':context['approval_token']})
            self.assertEqual(response.status_code,409)

    def test_unverified_no_reasoning_model_is_rejected_without_inference(self):
        response = self.owner.put('/api/admin/ai',json={'ai_chatgpt_reasoning':'none'})
        self.assertEqual(response.status_code,400)
        self.assertEqual(response.json()['detail'],'unsupported_reasoning')

    def test_inference_error_is_not_automatically_retried(self):
        with patch.object(connection, 'access_token', return_value='secret'), \
             patch.object(protocol, 'infer', side_effect=protocol.ChatGPTError('subscription_sharing_usage_unavailable')) as infer:
            with self.assertRaises(protocol.ChatGPTError):
                connection.request('test-model','text',connection_id='connection-one')
        self.assertEqual(infer.call_count,1)

    def test_cancellation_during_parallel_work_stops_new_dispatch(self):
        Image.new('RGB',(60,90),'white').save(self.root / 'recipes' / self.recipe_id / 'third.png')
        self.save_settings(ai_chatgpt_mode='formatted',ai_chatgpt_concurrency='2')
        job = self.enqueue(self.owner)
        both_started = threading.Barrier(2)
        def response(*args,**kwargs):
            both_started.wait(timeout=3)
            conn = foundation.get_db()
            conn.execute("UPDATE ai_text_jobs SET status='cancelled' WHERE id=?",(job['id'],))
            conn.commit(); conn.close()
            return {'text':'Completed in flight','usage':{'total_tokens':8}}
        request = self.run_job(job['id'],response)
        self.assertEqual(request.call_count,2)
        row = self.row(job['id'])
        self.assertEqual(row['status'],'cancelled')
        self.assertEqual(row['active_pages_json'],'[]')
        self.assertEqual(len(json.loads(row['checkpoint_json'])),2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
