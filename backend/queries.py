from datetime import datetime, timezone
from urllib.parse import urlparse
from fastapi import HTTPException
from sqlalchemy import select, func, or_
from .db import Blogger, Note, Comment, Task, TaskData, as_dict

MODELS = {'bloggers': Blogger, 'notes': Note, 'comments': Comment}


def task_records(db, tasks):
    rows = [as_dict(task) for task in tasks]
    users = {
        row['id']: urlparse(row['target']).path.rstrip('/').split('/')[-1]
        for row in rows if row['kind'] == 'blogger'
    }
    names = {}
    if users:
        for uid, nickname in db.execute(select(Blogger.id, Blogger.nickname).where(Blogger.id.in_(set(users.values())))):
            if nickname and nickname.strip():
                names[uid] = nickname.strip()
        # Older tasks can retain notes after their blogger profile is deleted.
        missing = set(users.values()) - names.keys()
        if missing:
            for uid, nickname in db.execute(select(Note.user_id, Note.nickname).where(
                Note.user_id.in_(missing), Note.nickname.is_not(None)
            ).order_by(Note.collected_at.desc(), Note.id)):
                if nickname.strip():
                    names.setdefault(uid, nickname.strip())
    for row in rows:
        row['display_target'] = names.get(users[row['id']], '博主昵称待获取') if row['kind'] == 'blogger' else row['target']
    return rows


def query_data(entity, q='', user_id='', note_id='', keyword='', note_type='', level=None,
               task_id='', published_from=None, published_to=None, **_):
    model = MODELS[entity]
    stmt = select(model)
    if q:
        columns = {'bloggers': [Blogger.id, Blogger.nickname, Blogger.description],
                   'notes': [Note.id, Note.title, Note.content],
                   'comments': [Comment.id, Comment.content]}[entity]
        stmt = stmt.where(or_(*(col.contains(q, autoescape=True) for col in columns)))
    if entity == 'notes':
        if user_id:
            stmt = stmt.where(Note.user_id == user_id)
        if note_type:
            stmt = stmt.where(Note.note_type == note_type)
        for value, lower in ((published_from, True), (published_to, False)):
            if value:
                try:
                    dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
                    if dt.tzinfo is None:
                        raise ValueError()
                    stamp = dt.astimezone(timezone.utc).isoformat(timespec='milliseconds')
                except ValueError:
                    raise HTTPException(422, '发布时间须为带时区的 ISO 日期时间') from None
                stmt = stmt.where(Note.published_at >= stamp if lower else Note.published_at <= stamp)
        if keyword:
            ids = select(TaskData.data_id).join(Task, TaskData.task_id == Task.id).where(
                TaskData.entity == 'notes', Task.kind == 'keyword', Task.target.contains(keyword, autoescape=True))
            stmt = stmt.where(Note.id.in_(ids))
    if entity == 'comments':
        if note_id:
            stmt = stmt.where(Comment.note_id == note_id)
        if level:
            stmt = stmt.where(Comment.level == level)
    if task_id:
        stmt = stmt.where(model.id.in_(select(TaskData.data_id).where(TaskData.task_id == task_id, TaskData.entity == entity)))
    return stmt


def records(db, entity, stmt):
    rows = [as_dict(x) for x in db.scalars(stmt).all()]
    if entity == 'notes' and rows:
        counts = dict(db.execute(select(Comment.note_id, func.count()).where(Comment.note_id.in_([x['id'] for x in rows])).group_by(Comment.note_id)).all())
        for row in rows:
            row['collected_comment_count'] = counts.get(row['id'], 0)
    return rows
