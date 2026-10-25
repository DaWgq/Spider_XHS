"""Seed only the dedicated UI regression database, never the user's database."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.config import DATA_DIR, ROOT
from backend.db import initialize, session, Task, Login
from backend.schemas import TaskInput
from backend.storage import save_note, save_comment

if DATA_DIR != (ROOT / 'local_data' / 'ui-test-run').resolve():
    raise SystemExit('Refusing to seed outside local_data/ui-test-run')
initialize()
with session() as db:
    if db.get(Login, 1).cookie:
        raise SystemExit('Refusing to seed a database with a configured platform Cookie')
    for tid, target in [('ui-delete-fixture', '本地删除验证任务'), ('ui-delete-detail', '本地删除详情任务')]:
        task = db.get(Task, tid)
        if task is None:
            db.add(Task(id=tid, kind='keyword', target=target,
                        params=TaskInput(kind='keyword', target=target).model_dump(),
                        status='completed', target_count=1))
        else:
            task.status = 'completed'
nid, uid, tid = 'f' * 24, 'e' * 24, 'ui-delete-fixture'
save_note({'id': nid, 'note_card': {'title': '本地删除验证笔记', 'desc': '仅供隔离浏览器测试', 'type': 'normal',
          'user': {'user_id': uid, 'nickname': '本地删除验证博主'}}},
          f'https://www.xiaohongshu.com/explore/{nid}', tid)
save_comment({'id': 'ui-delete-root', 'content': '本地删除验证评论', 'user_info': {'nickname': '测试评论者'}}, nid, 1, None, tid)
save_comment({'id': 'ui-delete-reply', 'content': '本地删除验证回复'}, nid, 2, 'ui-delete-root', tid)
print('Seeded isolated deletion fixtures.')
if '--batch' in sys.argv:
    for index in range(1, 23):
        batch_nid = f'{index + 1000:024x}'
        save_note({'id': batch_nid, 'note_card': {'title': f'本地批量验证笔记{index:02d}', 'type': 'normal',
                  'user': {'user_id': uid, 'nickname': '本地删除验证博主'}}},
                  f'https://www.xiaohongshu.com/explore/{batch_nid}', tid)
        root = f'ui-batch-root-{index}'
        save_comment({'id': root, 'content': f'批量验证根评论{index}'}, batch_nid, 1, None, tid)
        save_comment({'id': f'ui-batch-reply-{index}', 'content': f'批量验证回复{index}'}, batch_nid, 2, root, tid)
    print('Seeded 22 isolated batch notes with comments.')
if '--resume' in sys.argv:
    resume_id = 'ui-resume-fixture'
    profile = f'https://www.xiaohongshu.com/user/profile/{uid}?xsec_token=synthetic'
    with session() as db:
        task = db.get(Task, resume_id)
        if task is None:
            task = Task(id=resume_id, kind='blogger', target=profile,
                        params=TaskInput(kind='blogger', target=profile, max_notes=20).model_dump(), target_count=20)
            db.add(task)
        task.status, task.processed, task.success_count = 'partial_failed', 13, 13
    for index in range(13):
        resume_nid = f'{index + 30000:024x}'
        save_note({'id': resume_nid, 'note_card': {'title': f'本地继续验证笔记{index + 1}',
                  'user': {'user_id': uid, 'nickname': '本地继续验证博主'}}},
                  f'https://www.xiaohongshu.com/explore/{resume_nid}', resume_id)
    print('Seeded isolated 13/20 resume fixture; no platform Cookie configured.')
