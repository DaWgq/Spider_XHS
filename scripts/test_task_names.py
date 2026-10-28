"""Offline task-name regressions using an isolated in-memory database."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from backend.db import Base, Task, Blogger, Note
from backend.queries import task_records


class TaskNameTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)

    def task(self, target, kind='blogger'):
        task = Task(id='task', kind=kind, target=target, params={'target': target})
        self.db.add(task)
        self.db.flush()
        return task

    def test_existing_profile_url_displays_name_and_preserves_target(self):
        target = 'https://www.xiaohongshu.com/user/profile/abc/?xsec_token=original'
        task = self.task(target)
        self.db.add(Blogger(id='abc', nickname='博主昵称'))
        self.db.flush()
        result = task_records(self.db, [task])[0]
        self.assertEqual(result['display_target'], '博主昵称')
        self.assertEqual(result['target'], target)
        self.assertEqual(result['params']['target'], target)

    def test_bare_id_displays_name(self):
        task = self.task('abc')
        self.db.add(Blogger(id='abc', nickname='  博主昵称  '))
        self.db.flush()
        self.assertEqual(task_records(self.db, [task])[0]['display_target'], '博主昵称')

    def test_deleted_profile_uses_latest_matching_note_author(self):
        task = self.task('abc')
        self.db.add_all([
            Note(id='a', user_id='abc', nickname='旧昵称', collected_at='2026-10-27'),
            Note(id='b', user_id='abc', nickname='新昵称', collected_at='2026-10-28'),
            Note(id='c', user_id='other', nickname='其他博主', collected_at='2026-10-29'),
        ])
        self.db.flush()
        self.assertEqual(task_records(self.db, [task])[0]['display_target'], '新昵称')

    def test_missing_name_never_displays_link(self):
        task = self.task('https://www.xiaohongshu.com/user/profile/unknown')
        self.assertEqual(task_records(self.db, [task])[0]['display_target'], '博主昵称待获取')

    def test_keyword_target_is_unchanged(self):
        task = self.task('旅行', kind='keyword')
        self.assertEqual(task_records(self.db, [task])[0]['display_target'], '旅行')
        self.assertEqual(task_records(self.db, []), [])


if __name__ == '__main__':
    unittest.main()
