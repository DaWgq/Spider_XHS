"""Clear-Cookie API tests with an isolated database and no platform requests."""
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException
from fastapi.testclient import TestClient

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
test_root = root / 'local_data'
test_root.mkdir(exist_ok=True)
_temp = tempfile.TemporaryDirectory(prefix='clear-login-tests-', dir=test_root)
os.environ['XHS_DATA_DIR'] = _temp.name
from backend.app import app, check_login
from backend.db import Base, engine, initialize, session, Login, Task, Blogger, Note, Comment
from backend.qr_login import qr_manager, QRSession

COOKIE = 'a1=local-test-device; web_session=local-test-secret'


class ClearLoginTests(unittest.TestCase):
    def setUp(self):
        qr_manager.discard_all()
        Base.metadata.drop_all(engine)
        initialize()
        self.client = TestClient(app)
        self.client.post('/api/auth/login', json={'username': 'dawg', 'password': '123456'})
        self.client.put('/api/login', json={'cookie': COOKIE})
        with session() as db:
            row = db.get(Login, 1)
            row.status, row.account = 'valid', {'user_id': 'old-user', 'nickname': '旧账号'}

    def tearDown(self):
        qr_manager.discard_all()
        self.client.close()

    def test_clear_removes_credentials_preserves_data_and_allows_new_account(self):
        with session() as db:
            db.add(Task(id='task', kind='keyword', target='测试', params={}, status='completed'))
            db.add(Blogger(id='blogger', nickname='测试'))
            db.add(Note(id='note', nickname='测试'))
            db.add(Comment(id='comment', note_id='note', level=1))
        result = self.client.delete('/api/login')
        self.assertEqual(result.status_code, 200)
        self.assertFalse(result.json()['configured'])
        self.assertEqual(result.json()['account'], {})
        self.assertEqual(result.json()['masked'], '未配置')
        self.assertNotIn('local-test-secret', result.text)
        with session() as db:
            self.assertEqual(db.get(Login, 1).cookie, '')
            self.assertIsNotNone(db.get(Task, 'task'))
            self.assertIsNotNone(db.get(Blogger, 'blogger'))
            self.assertIsNotNone(db.get(Note, 'note'))
            self.assertIsNotNone(db.get(Comment, 'comment'))
        self.assertTrue(self.client.get('/api/auth/session').json()['authenticated'])
        self.assertEqual(self.client.post('/api/login/check').status_code, 400)
        self.assertEqual(self.client.delete('/api/login').status_code, 200)
        self.assertEqual(self.client.put('/api/login', json={'cookie': 'a1=new-device; web_session=new-account'}).status_code, 200)

    def test_running_task_protection_and_system_login_required(self):
        item = QRSession(id='pending', owner='owner', initial_updated_at='old', state='waiting')
        qr_manager.sessions[item.id] = item
        with session() as db:
            db.add(Task(id='task', kind='keyword', target='测试', params={}, status='running'))
        for status in ('running', 'stopping'):
            with session() as db:
                db.get(Task, 'task').status = status
            self.assertEqual(self.client.delete('/api/login').status_code, 409)
            self.assertEqual(item.state, 'waiting')
            with session() as db:
                self.assertEqual(db.get(Login, 1).cookie, COOKIE)
        with session() as db:
            db.get(Task, 'task').status = 'stopped'
        self.assertEqual(self.client.delete('/api/login').status_code, 200)
        self.assertTrue(item.stop.is_set())
        self.assertEqual(qr_manager.sessions, {})
        anonymous = TestClient(app)
        try:
            self.assertEqual(anonymous.delete('/api/login').status_code, 401)
        finally:
            anonymous.close()

    def test_pending_cookie_check_cannot_restore_cleared_account(self):
        entered, release = threading.Event(), threading.Event()
        outcome = []
        class Collector:
            def __init__(self, *_): pass
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def account(self):
                entered.set()
                release.wait(2)
                return {'user_id': 'old-user'}
        def run():
            try: check_login()
            except HTTPException as error: outcome.append(error.status_code)
        with patch('backend.app.Collector', Collector):
            worker = threading.Thread(target=run)
            worker.start()
            try:
                self.assertTrue(entered.wait(1))
                self.assertEqual(self.client.delete('/api/login').status_code, 200)
            finally:
                release.set()
                worker.join(2)
        self.assertEqual(outcome, [409])
        self.assertFalse(self.client.get('/api/login').json()['configured'])
        self.assertEqual(self.client.get('/api/login').json()['account'], {})

    def test_clear_cancels_qr_before_late_verification_commits(self):
        entered, release = threading.Event(), threading.Event()
        class API:
            count = 0
            def generate_init_cookies(self): return {'a1': 'new-device', 'web_session': 'new-session'}
            def generate_qrcode(self, cookies): return True, '', {'cookies': cookies, 'qr_id': 'id', 'code': 'code', 'qr_url': 'https://example.invalid/qr'}
            def check_qrcode_status(self, *args):
                self.count += 1
                return self.count > 1, '请扫描二维码' if self.count == 1 else '验证成功', args[-1]
            def ensure_webprofile(self, cookies): pass
            def get_user_info(self, cookies):
                entered.set()
                release.wait(2)
                return True, {'guest': False, 'user_id': 'new-user'}, cookies
            def cookies_to_str(self, cookies): return 'a1=new-device; web_session=new-session'
            def close(self): pass
        with patch('backend.qr_login.proxy_ready'), patch('backend.qr_login.install_transport_guard'), patch('backend.qr_login.check_runtime'), patch('backend.qr_login.build_login_api', return_value=API()), patch('backend.qr_login.qr_image', return_value='test-image'):
            result = self.client.post('/api/login/qrcode')
            self.assertEqual(result.status_code, 202)
            sid = result.json()['id']
            worker = qr_manager.sessions[sid].thread
            try:
                self.assertTrue(entered.wait(1))
                self.assertEqual(self.client.delete('/api/login').status_code, 200)
            finally:
                release.set()
                worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertFalse(self.client.get('/api/login').json()['configured'])
        with session() as db:
            self.assertEqual(db.get(Login, 1).cookie, '')


def tearDownModule():
    engine.dispose()
    _temp.cleanup()


if __name__ == '__main__':
    unittest.main(verbosity=2)
