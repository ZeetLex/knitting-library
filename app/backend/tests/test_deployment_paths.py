"""Exercise deployment configuration in fresh processes to catch startup leaks."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

BACKEND_DIR = Path(__file__).resolve().parents[1]
PATH_VARIABLES = ("KNITTING_DATA_DIR", "KNITTING_LOG_DIR", "KNITTING_STATIC_DIR")


class DeploymentPathTests(unittest.TestCase):
    def run_backend(self, script, overrides=None):
        env = {key: value for key, value in os.environ.items() if key not in PATH_VARIABLES}
        env.update(overrides or {})
        return subprocess.run(
            [sys.executable, "-c", textwrap.dedent(script)],
            cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=60,
        )

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_defaults_and_blank_values_have_no_import_side_effects(self):
        script = """
            import json
            import sys
            from unittest.mock import patch
            with patch('pathlib.Path.mkdir', side_effect=AssertionError('unexpected mkdir')):
                from app.core import paths
            assert 'app.core.foundation' not in sys.modules
            print(json.dumps([str(paths.DATA_ROOT), str(paths.LOG_DIR), str(paths.STATIC_DIR)]))
        """
        expected = [str(Path('/data')), str(Path('/logs')), str(Path('/app/frontend/build'))]
        for overrides in ({}, {name: ' \t ' for name in PATH_VARIABLES}):
            with self.subTest(overrides=overrides):
                result = self.run_backend(script, overrides)
                self.assert_success(result)
                self.assertEqual(json.loads(result.stdout), expected)

    def test_relative_override_is_rejected_for_each_variable(self):
        for name in PATH_VARIABLES:
            with self.subTest(variable=name):
                result = self.run_backend('from app.core import paths', {name: 'relative/path'})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f'{name} must be an absolute path', result.stderr)

    def test_cli_uses_custom_database_without_initializing_server(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_backend("""
                import sys
                from pathlib import Path
                from unittest.mock import patch
                with patch('pathlib.Path.mkdir', side_effect=AssertionError('unexpected mkdir')):
                    from app import cli
                from app.core.paths import DATA_ROOT
                assert cli.DEFAULT_DB_PATH == DATA_ROOT / 'recipes.db'
                assert not DATA_ROOT.exists()
                assert 'app.core.foundation' not in sys.modules
                with patch.object(cli.getpass, 'getpass', return_value='recovery-password'), \
                     patch.object(cli, 'reset_password') as reset:
                    assert cli.main(['reset-password', 'admin']) == 0
                    reset.assert_called_once_with(cli.DEFAULT_DB_PATH, 'admin', 'recovery-password')
            """, {'KNITTING_DATA_DIR': str(Path(directory) / 'not-created')})
            self.assert_success(result)

    def test_startup_failure_reports_directory_and_preserves_cause(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_backend("""
                from pathlib import Path
                from unittest.mock import patch
                from app.core import paths
                with patch.object(Path, 'mkdir', side_effect=PermissionError('permission denied')):
                    try:
                        paths.ensure_data_directories()
                    except RuntimeError as exc:
                        assert str(paths.DATA_DIR) in str(exc)
                        assert isinstance(exc.__cause__, PermissionError)
                    else:
                        raise AssertionError('permission error was swallowed')
            """, {'KNITTING_DATA_DIR': directory})
            self.assert_success(result)

    def test_unavailable_log_directory_falls_back_to_stderr(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            blocked_logs = root / 'logs-is-a-file'
            blocked_logs.write_text('not a directory', encoding='utf-8')
            result = self.run_backend("""
                import logging
                from app.core import foundation
                assert len(foundation._auth_log.handlers) == 1
                assert type(foundation._auth_log.handlers[0]) is logging.StreamHandler
                foundation._auth_log.warning('fallback-auth-event')
            """, {
                'KNITTING_DATA_DIR': str(root / 'data'),
                'KNITTING_LOG_DIR': str(blocked_logs),
            })
            self.assert_success(result)
            self.assertIn('fallback-auth-event', result.stderr)

    def test_custom_paths_work_across_server_features(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            static_dir = root / 'frontend assets'
            static_dir.mkdir()
            (static_dir / 'index.html').write_text('<html>custom frontend</html>', encoding='utf-8')
            result = self.run_backend("""
                import io
                import zipfile
                from PIL import Image
                from fastapi.testclient import TestClient
                from app.main import app
                from app.core import paths, foundation
                from app.cli import reset_password

                client = TestClient(app)
                assert client.get('/').text == '<html>custom frontend</html>'
                assert client.get('/api/health').status_code == 200
                response = client.post('/api/setup/admin', json={
                    'username': 'admin', 'password': 'initial-password-123',
                })
                assert response.status_code == 200, response.text
                token = response.json()['token']
                client.cookies.clear()
                client.headers['X-Session-Token'] = token

                image = io.BytesIO()
                Image.new('RGB', (80, 100), 'blue').save(image, format='PNG')
                image_bytes = image.getvalue()
                response = client.post('/api/recipes', data={'title': 'Test pattern'},
                    files=[('files', ('pattern.png', image_bytes, 'image/png'))])
                assert response.status_code == 200, response.text
                recipe_id = response.json()['id']
                assert (paths.DATA_DIR / recipe_id / 'pattern.png').read_bytes() == image_bytes

                response = client.post('/api/yarns', data={'name': 'Test wool'},
                    files={'image': ('wool.png', image_bytes, 'image/png')})
                assert response.status_code == 200, response.text
                yarn_id = response.json()['id']
                assert (paths.YARN_DIR / yarn_id / 'yarn.png').read_bytes() == image_bytes
                assert client.get(f'/api/yarns/{yarn_id}/image').content == image_bytes

                response = client.post('/api/admin/branding/icon',
                    files={'icon': ('icon.png', image_bytes, 'image/png')})
                assert response.status_code == 200, response.text
                assert response.json()['has_custom_icon']
                assert client.get('/api/branding/icon/512.png').status_code == 200
                assert (paths.BRANDING_DIR / 'icon-512.png').is_file()

                response = client.get('/api/export')
                assert response.status_code == 200, response.text
                with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                    assert 'recipes.db' in archive.namelist()
                    assert archive.read('branding/icon-512.png') == (paths.BRANDING_DIR / 'icon-512.png').read_bytes()
                    # ZIP entry separators remain platform-dependent in existing exports.
                    names = [name.replace(chr(92), '/') for name in archive.namelist()]
                    assert f'recipes/{recipe_id}/pattern.png' in names
                    assert f'yarns/{yarn_id}/yarn.png' in names

                foundation._auth_log.info('custom-path-test')
                (paths.LOG_DIR / 'uvicorn.log').write_text('custom-server-output\\n', encoding='utf-8')
                response = client.get('/api/admin/logs')
                assert response.status_code == 200, response.text
                assert any('custom-path-test' in line for line in response.json()['lines'])
                assert any('custom-server-output' in line for line in response.json()['lines'])
                reset_password(paths.DB_PATH, 'admin', 'recovered-password-123')
                assert client.get('/api/auth/me').status_code == 401
                response = client.post('/api/auth/login', json={
                    'username': 'admin', 'password': 'recovered-password-123',
                })
                assert response.status_code == 200, response.text
            """, {
                'KNITTING_DATA_DIR': str(root / 'custom data'),
                'KNITTING_LOG_DIR': str(root / 'custom logs'),
                'KNITTING_STATIC_DIR': str(static_dir),
            })
            self.assert_success(result)


if __name__ == '__main__':
    unittest.main()
