import threading
from uuid import uuid4
from urllib.parse import urlparse
from sqlalchemy import select
from .db import session, Task, TaskLog, Login, TaskData, TaskCompletedNote, Note, now, as_dict, DB_LOCK
from fastapi import HTTPException
from .collector import Collector, Cancelled, AccessBlocked, ItemError
from .config import ProxyUnavailable
from .schemas import TaskInput

MUTEX = DB_LOCK


def create_task(spec: TaskInput):
    tid = uuid4().hex
    with MUTEX, session() as db:
        task = Task(id=tid, kind=spec.kind, target=spec.target, params=spec.model_dump(), target_count=spec.max_notes)
        db.add(task)
        db.flush()
        result = as_dict(task)
    return result


def log(tid, message, level='info'):
    with MUTEX, session() as db:
        db.add(TaskLog(task_id=tid, message=message, level=level))


def update(tid, **values):
    with MUTEX, session() as db:
        task = db.get(Task, tid)
        for key, value in values.items():
            setattr(task, key, value)


def stop_task(tid):
    with MUTEX, session() as db:
        task = db.get(Task, tid)
        if not task:
            return None
        if task.status in ('pending', 'paused'):
            task.status, task.ended_at, task.reason = 'stopped', now(), '排队期间由用户停止'
        elif task.status in ('running', 'stopping', 'pausing'):
            task.status = 'stopping'
            scheduler.cancel(tid)
        return as_dict(task)


def pause_task(tid):
    with MUTEX, session() as db:
        task = db.get(Task, tid)
        if not task:
            raise HTTPException(404, '任务不存在')
        if task.status in ('pausing', 'paused'):
            return as_dict(task)
        if task.status not in ('pending', 'running'):
            raise HTTPException(409, '当前任务不能暂停')
        if task.status == 'pending':
            task.status, task.ended_at, task.reason = 'paused', now(), '排队期间由用户暂停，继续后重新排队'
        else:
            task.status, task.reason = 'pausing', '正在暂停，等待当前请求结束'
            scheduler.cancel(tid)
        db.add(TaskLog(task_id=tid, message='用户请求暂停采集，保留已完成进度'))
        return as_dict(task)


def completed_notes(db, tid):
    return set(db.scalars(select(TaskCompletedNote.note_id).where(TaskCompletedNote.task_id == tid)))


def resume_task(tid):
    with MUTEX, session() as db:
        task = db.get(Task, tid)
        if not task:
            raise HTTPException(404, '任务不存在')
        if task.status not in ('partial_failed', 'failed', 'stopped', 'interrupted', 'paused'):
            raise HTTPException(409, '当前任务正在排队、执行或已完成，不能继续采集')
        done = completed_notes(db, tid)
        # Upgrade legacy tasks using their insertion-ordered task associations.
        if not done and task.success_count:
            failed_ids = {urlparse(x['url']).path.rstrip('/').split('/')[-1] for x in task.failures if x.get('url')}
            rows = db.execute(select(Note.id, Note.url).join(TaskData, TaskData.data_id == Note.id).where(
                TaskData.task_id == tid, TaskData.entity == 'notes').order_by(TaskData.id)).all()
            successful = [(nid, url) for nid, url in rows if nid not in failed_ids][:task.success_count]
            if len(successful) < task.success_count:
                raise HTTPException(409, '旧任务已完成的笔记记录不完整，无法安全恢复进度，请新建任务')
            for nid, url in successful:
                db.add(TaskCompletedNote(task_id=tid, note_id=nid, url=url or ''))
            done = {nid for nid, _ in successful}
        if len(done) >= task.target_count:
            raise HTTPException(409, '目标笔记已全部完成，无需继续采集')
        login = db.get(Login, 1)
        if not login.cookie or login.status == 'invalid':
            raise HTTPException(409, '请先配置有效 Cookie，并在登录配置页检测通过后再继续采集')
        task.params = TaskInput(**task.params).model_dump()
        task.status, task.ended_at, task.last_error, task.reason = 'pending', None, None, '用户选择继续采集，已重新排队'
        task.success_count, task.processed, task.failure_count, task.failures = len(done), len(done), 0, []
        db.add(TaskLog(task_id=tid, message=f'继续采集：保留已完成 {len(done)} 篇，补采剩余 {task.target_count - len(done)} 篇；将重新遍历列表并跳过已完成笔记'))
        db.flush()
        return as_dict(task)


class Scheduler:
    def __init__(self):
        self.shutdown = threading.Event()
        self.cancel_event = threading.Event()
        self.current = None
        self.thread = None

    def start(self):
        self.shutdown.clear()
        self.thread = threading.Thread(target=self.loop, daemon=True, name='xhs-single-worker')
        self.thread.start()

    def cancel(self, tid):
        if tid == self.current:
            self.cancel_event.set()

    def close(self):
        self.shutdown.set()
        self.cancel_event.set()
        if self.thread:
            self.thread.join(timeout=2)

    def loop(self):
        while not self.shutdown.is_set():
            try:
                with MUTEX, session() as db:
                    task = db.scalar(select(Task).where(Task.status == 'pending').order_by(Task.created_at, Task.id).limit(1))
                    if task:
                        self.current = task.id
                        self.cancel_event.clear()
                        task.status, task.started_at = 'running', task.started_at or now()
                        params = TaskInput(**task.params).model_dump()
                        task.params = params
                        cookie = db.get(Login, 1).cookie
                if task:
                    self.run(task.id, params, cookie)
                    self.current = None
                else:
                    self.shutdown.wait(0.3)
            except Exception:
                if self.current:
                    update(self.current, status='failed', ended_at=now(), reason='任务调度发生内部错误，请检查本机数据目录权限')
                    self.current = None
                self.shutdown.wait(0.5)

    def run(self, tid, params, cookie):
        with session() as db:
            done = completed_notes(db, tid)
        succeeded, failed, processed, failures = len(done), 0, len(done), []
        state, reason = 'completed', '已达到目标数量或平台已无更多数据'
        log(tid, '任务开始；媒体只保存链接；时间统一存储为 UTC')
        try:
            if not cookie:
                raise AccessBlocked('尚未配置 Cookie，请在登录配置页保存有效 Cookie')
            with Collector(cookie, self.cancel_event, params, lambda message, level='info': log(tid, message, level)) as collector:
                for url, item in collector.targets(tid):
                    collector.guard.check()
                    nid = urlparse(url).path.rstrip('/').split('/')[-1]
                    if nid in done:
                        continue
                    if succeeded >= params['max_notes']:
                        break
                    try:
                        collector.collect_note(url, item, tid)
                        succeeded += 1
                        done.add(nid)
                        with session() as db:
                            db.add(TaskCompletedNote(task_id=tid, note_id=nid, url=url))
                        log(tid, f'第 {processed + 1} 篇笔记采集完成')
                    except ItemError as exc:
                        failed += 1
                        failures.append({'url': url, 'error': str(exc)})
                        log(tid, str(exc), 'error')
                        update(tid, last_error=str(exc))
                    processed += 1
                    update(tid, processed=processed, success_count=succeeded, failure_count=failed, failures=failures)
                collector.guard.check()
                if failed:
                    state = 'partial_failed' if succeeded else 'failed'
                    reason = '部分笔记或评论采集失败' if succeeded else '所有笔记采集失败'
        except Cancelled:
            state, reason = ('interrupted', '程序关闭，任务已中断') if self.shutdown.is_set() else ('stopped', '用户停止任务，已保存的数据保留')
        except (AccessBlocked, ProxyUnavailable, ItemError) as exc:
            state, reason = ('partial_failed' if succeeded else 'failed'), str(exc)
            if isinstance(exc, AccessBlocked):
                with session() as db:
                    login = db.get(Login, 1)
                    if login.cookie == cookie:
                        login.status, login.account = 'invalid', {}
            # Discovery/auth failures can be retried with the original source task.
            failures.append({'target': params['target'], 'error': reason})
            update(tid, last_error=reason, failures=failures)
        except Exception:
            state, reason = ('partial_failed' if succeeded else 'failed'), '采集处理异常：平台数据结构变化或本地运行环境异常'
            failures.append({'target': params['target'], 'error': reason})
            update(tid, last_error=reason, failures=failures)
        with MUTEX, session() as db:
            task = db.get(Task, tid)
            if task.status == 'stopping' and state == 'completed':
                state, reason = 'stopped', '用户停止任务，已保存的数据保留'
            if task.status == 'pausing' and state in ('stopped', 'completed'):
                if succeeded < params['max_notes']:
                    state, reason = 'paused', '用户暂停采集，已保存进度；可继续采集剩余笔记'
                else:
                    state, reason = 'completed', '已达到目标数量'
            task.status, task.ended_at, task.reason = state, now(), reason
        log(tid, reason, 'error' if state in ('failed', 'partial_failed') else 'info')


scheduler = Scheduler()
