"""Transactional deletion, including links shared by multiple collection tasks."""
from fastapi import HTTPException
from sqlalchemy import delete, select, or_
from .db import session, Task, TaskLog, TaskData, TaskCompletedNote, Blogger, Note, Comment

MODELS = {'bloggers': Blogger, 'notes': Note, 'comments': Comment}


def delete_task_record(tid):
    with session() as db:
        task = db.get(Task, tid)
        if task is None:
            raise HTTPException(404, '任务不存在或已删除')
        if task.status in ('running', 'stopping', 'pausing'):
            raise HTTPException(409, '请先停止任务，等待状态变为已停止后再删除')
        db.execute(delete(TaskLog).where(TaskLog.task_id == tid))
        db.execute(delete(TaskData).where(TaskData.task_id == tid))
        db.execute(delete(TaskCompletedNote).where(TaskCompletedNote.task_id == tid))
        db.delete(task)
    return {'deleted': True, 'message': '任务及日志已删除，采集数据已保留'}


def delete_data_record(entity, data_id):
    return delete_data_records(entity, [data_id])


def delete_data_records(entity, data_ids):
    requested = set(data_ids)
    with session() as db:
        model = MODELS[entity]
        rows = db.scalars(select(model).where(model.id.in_(requested))).all()
        if len(rows) != len(requested):
            raise HTTPException(404, '数据不存在或已删除，请刷新列表后重新选择；本次未删除任何数据')
        if db.scalar(select(Task.id).where(Task.status.in_(['running', 'stopping', 'pausing'])).limit(1)):
            raise HTTPException(409, '当前有任务正在采集或停止中，请先停止并等待结束，再删除数据')
        deleted_comments = 0
        deleted_count = len(rows)
        if entity == 'notes':
            comment_ids = select(Comment.id).where(Comment.note_id.in_(requested))
            db.execute(delete(TaskData).where(TaskData.entity == 'comments', TaskData.data_id.in_(comment_ids)))
            deleted_comments = db.execute(delete(Comment).where(Comment.note_id.in_(requested))).rowcount
        elif entity == 'comments':
            # Only follow relationships actually stored from the platform response.
            groups = {}
            for row in rows:
                groups.setdefault(row.note_id, set()).add(row.id)
            ids = set(requested)
            for note_id, seeds in groups.items():
                frontier = seeds
                while frontier:
                    children = set(db.scalars(select(Comment.id).where(Comment.note_id == note_id,
                        or_(Comment.root_id.in_(frontier), Comment.parent_id.in_(frontier)))).all()) - ids
                    ids.update(children)
                    frontier = children
            db.execute(delete(TaskData).where(TaskData.entity == 'comments', TaskData.data_id.in_(ids)))
            deleted_comments = db.execute(delete(Comment).where(Comment.id.in_(ids))).rowcount
        if entity != 'comments':
            db.execute(delete(TaskData).where(TaskData.entity == entity, TaskData.data_id.in_(requested)))
            db.execute(delete(model).where(model.id.in_(requested)))
    return {'deleted': True, 'deleted_count': deleted_count, 'deleted_comments': deleted_comments,
            'message': {'bloggers': f'已删除 {deleted_count} 条博主记录，笔记与评论保留', 'notes': f'已删除 {deleted_count} 篇笔记及 {deleted_comments} 条评论', 'comments': f'已删除 {deleted_count} 条选中评论，共清理 {deleted_comments} 条评论及关联回复'}[entity]}
