"""Offline pause/resume tests with a temporary database and fake collector."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
(root / 'local_data').mkdir(exist_ok=True)
temp = tempfile.TemporaryDirectory(prefix='pause-tests-', dir=root / 'local_data')
os.environ['XHS_DATA_DIR'] = temp.name
from backend.db import Base, engine, initialize, session, Task, TaskCompletedNote, Login
from backend.schemas import TaskInput
from backend.collector import Cancelled
from backend.deletion import delete_task_record
from fastapi import HTTPException
sched = importlib.import_module('backend.scheduler')


class PauseTests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(engine)
        initialize()
        self.worker = sched.Scheduler()
        self.patcher = patch.object(sched, 'scheduler', self.worker)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.params = TaskInput(kind='keyword', target='test', max_notes=2).model_dump()
        with session() as db:
            login = db.get(Login, 1)
            login.cookie, login.status = 'offline-cookie', 'valid'
            db.add(Task(id='task', kind='keyword', target='test', params=self.params, target_count=2))

    def state(self):
        with session() as db:
            return db.get(Task, 'task').status

    def test_pending_pause_and_resume_keep_same_task(self):
        self.assertEqual(sched.pause_task('task')['status'], 'paused')
        self.assertEqual(sched.pause_task('task')['status'], 'paused')
        self.assertEqual(sched.resume_task('task')['id'], 'task')
        self.assertEqual(self.state(), 'pending')

    def test_running_pause_keeps_completed_notes_and_resume_skips_them(self):
        sched.update('task', status='running')
        self.worker.current = 'task'
        collected = []
        test = self
        class FakeCollector:
            def __init__(self, cookie, stop, params, log):
                self.stop = stop
                self.guard = self
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def check(self):
                if self.stop.is_set(): raise Cancelled()
            def targets(self, tid):
                for nid in ('one', 'two'):
                    yield f'https://www.xiaohongshu.com/explore/{nid}', None
            def collect_note(self, url, item, tid):
                collected.append(url.rsplit('/', 1)[-1])
                if len(collected) == 1:
                    test.assertEqual(sched.pause_task(tid)['status'], 'pausing')
                    with test.assertRaises(HTTPException) as error:
                        delete_task_record(tid)
                    test.assertEqual(error.exception.status_code, 409)
        with patch.object(sched, 'Collector', FakeCollector):
            self.worker.run('task', self.params, 'offline-cookie')
            self.assertEqual(self.state(), 'paused')
            with session() as db:
                self.assertEqual(db.get(Task, 'task').success_count, 1)
                self.assertEqual(db.query(TaskCompletedNote).count(), 1)
            result = sched.resume_task('task')
            self.assertEqual(result['success_count'], 1)
            self.worker.cancel_event.clear()
            sched.update('task', status='running')
            self.worker.run('task', self.params, 'offline-cookie')
        self.assertEqual(collected, ['one', 'two'])
        self.assertEqual(self.state(), 'completed')

    def test_finished_task_cannot_pause(self):
        sched.update('task', status='completed')
        with self.assertRaises(HTTPException) as error:
            sched.pause_task('task')
        self.assertEqual(error.exception.status_code, 409)

    def test_restart_preserves_paused_and_interrupts_pausing(self):
        sched.pause_task('task')
        initialize()
        self.assertEqual(self.state(), 'paused')
        sched.update('task', status='pausing')
        initialize()
        self.assertEqual(self.state(), 'interrupted')

    def test_missing_task_returns_404(self):
        with self.assertRaises(HTTPException) as error:
            sched.pause_task('missing')
        self.assertEqual(error.exception.status_code, 404)


def tearDownModule():
    engine.dispose()
    temp.cleanup()


if __name__ == '__main__':
    unittest.main()
