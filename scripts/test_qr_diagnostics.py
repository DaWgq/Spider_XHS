"""Offline diagnostics regressions; never accesses the actual database or platform."""
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_test_root = Path(__file__).resolve().parents[1] / 'local_data'
_test_root.mkdir(exist_ok=True)
_temp = tempfile.TemporaryDirectory(prefix='qr-diagnostics-', dir=_test_root)
os.environ['XHS_DATA_DIR'] = _temp.name
from backend.db import initialize, session, Login, engine
from backend.qr_login import QRLoginManager, QRSession, QRLoginError, check_runtime


class QRDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        initialize()
        with session() as db:
            db.get(Login, 1).cookie = 'existing-cookie-must-survive'
            db.get(Login, 1).updated_at = 'existing-version'
        self.manager = QRLoginManager()

    def tearDown(self):
        self.manager.cancel_all()
        for item in self.manager.sessions.values():
            if item.thread:
                item.thread.join(timeout=1)
            if item.timer:
                item.timer.cancel()

    def wait_terminal(self, sid):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            result = self.manager.get(sid, 'owner')
            if result['state'] in ('succeeded', 'failed', 'expired', 'cancelled'):
                return result
            time.sleep(0.005)
        self.fail('QR fixture did not terminate')

    def test_node_missing_and_crypto_dependency_error_are_specific(self):
        with patch('backend.qr_login.shutil.which', return_value=None):
            with self.assertRaisesRegex(QRLoginError, 'Node.js'):
                check_runtime()
        with patch('backend.qr_login.shutil.which', return_value='node'), patch('backend.qr_login.subprocess.run', return_value=SimpleNamespace(returncode=1)):
            with self.assertRaisesRegex(QRLoginError, 'crypto-js'):
                check_runtime()

    def test_request_progress_drops_query_secrets_and_preserves_scanned_message(self):
        item = QRSession(id='test', owner='owner', initial_updated_at='existing-version')
        self.manager.progress(item, 'GET', 'https://example.invalid/api/login?cookie=secret&code=private', 'requesting')
        result = self.manager.snapshot(item)
        self.assertEqual(result['request_count'], 1)
        self.assertEqual(result['request'], 'GET example.invalid/api/login')
        self.assertNotIn('private', str(result))
        self.assertNotIn('secret', str(result))
        item.state, item.message = 'scanned', '请在手机确认'
        self.manager.progress(item, 'POST', 'https://example.invalid/api/poll', 'preparing')
        self.assertEqual(item.message, '请在手机确认')

    def test_hung_initialization_times_out_before_upstream_returns(self):
        entered, release = threading.Event(), threading.Event()
        class SlowAPI:
            def generate_init_cookies(self):
                entered.set()
                release.wait(2)
                return {'a1': 'device'}
            def close(self): pass
        with patch('backend.qr_login.INIT_TIMEOUT', 0.05), patch('backend.qr_login.proxy_ready'), patch('backend.qr_login.install_transport_guard'), patch('backend.qr_login.check_runtime'), patch('backend.qr_login.build_login_api', return_value=SlowAPI()):
            sid = self.manager.start('owner')['id']
            try:
                self.assertTrue(entered.wait(1))
                result = self.wait_terminal(sid)
                self.assertEqual(result['state'], 'failed')
                self.assertEqual(result['stage'], 'anonymous')
                self.assertIn('超时', result['message'])
                self.assertTrue(self.manager.sessions[sid].thread.is_alive())
            finally:
                release.set()
                self.manager.sessions[sid].thread.join(1)
            self.assertEqual(self.manager.get(sid, 'owner')['state'], 'failed')
        with session() as db:
            self.assertEqual(db.get(Login, 1).cookie, 'existing-cookie-must-survive')

    def test_timeout_phase_reset_and_scan_expiry(self):
        item = QRSession(id='test', owner='owner', initial_updated_at='existing-version')
        self.manager.sessions[item.id] = item
        self.manager.arm_timeout(item, 1)
        old_deadline = item.deadline
        item.state = 'waiting'
        self.manager.arm_timeout(item, 180)
        self.manager.expire(item, old_deadline)
        self.assertEqual(item.state, 'waiting')
        item.deadline = time.monotonic() - 1
        self.manager.expire(item, item.deadline)
        self.assertEqual(item.state, 'expired')

    def test_failure_diagnostic_does_not_echo_upstream_secret(self):
        class BrokenAPI:
            def generate_init_cookies(self):
                raise RuntimeError('DS scripting response missing getdss; private-cookie-value')
            def close(self): pass
        with patch('backend.qr_login.proxy_ready'), patch('backend.qr_login.install_transport_guard'), patch('backend.qr_login.check_runtime'), patch('backend.qr_login.build_login_api', return_value=BrokenAPI()):
            sid = self.manager.start('owner')['id']
            result = self.wait_terminal(sid)
        self.assertIn('安全初始化', result['message'])
        self.assertNotIn('private-cookie-value', str(result))

    def test_success_after_precheck_still_saves_verified_cookie(self):
        from backend.collector import active_guard
        observed_intervals = []
        class API:
            count = 0
            def generate_init_cookies(self):
                guard = active_guard.get()
                observed_intervals.append((guard.interval_min, guard.interval_max))
                return {'a1': 'private-device', 'web_session': 'visitor'}
            def generate_qrcode(self, cookies): return True, '', {'cookies': cookies, 'qr_id': 'private-id', 'code': 'private-code', 'qr_url': 'https://example.invalid/qr'}
            def check_qrcode_status(self, *args):
                self.count += 1
                cookies = args[-1]
                if self.count == 1: return False, '请扫描二维码', cookies
                cookies['web_session'] = 'private-session'
                return True, '验证成功', cookies
            def ensure_webprofile(self, cookies): pass
            def get_user_info(self, cookies):
                guard = active_guard.get()
                observed_intervals.append((guard.interval_min, guard.interval_max))
                return True, {'guest': False, 'user_id': 'test-user', 'nickname': '测试'}, cookies
            def cookies_to_str(self, cookies): return '; '.join(f'{k}={v}' for k,v in cookies.items())
            def close(self): pass
        with patch('backend.qr_login.proxy_ready'), patch('backend.qr_login.install_transport_guard'), patch('backend.qr_login.check_runtime'), patch('backend.qr_login.build_login_api', return_value=API()), patch('backend.qr_login.qr_image', return_value='test-image'):
            sid = self.manager.start('owner')['id']
            result = self.wait_terminal(sid)
        self.assertEqual(result['state'], 'succeeded')
        self.assertEqual(observed_intervals, [(0, 0), (3, 5)])
        self.assertNotIn('private-session', str(result))
        with session() as db:
            self.assertEqual(db.get(Login, 1).status, 'valid')
            self.assertIn('private-session', db.get(Login, 1).cookie)


def tearDownModule():
    engine.dispose()
    _temp.cleanup()


if __name__ == '__main__':
    unittest.main(verbosity=2)
