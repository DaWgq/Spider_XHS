import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse, quote
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, func
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .db import initialize, session, Login, Task, TaskLog, Blogger, Note, Comment, now, as_dict
from .scheduler import scheduler, create_task, stop_task, pause_task, resume_task, MUTEX
from .schemas import CookieInput, TaskInput, BatchDeleteInput
from .collector import Collector, AccessBlocked
from .config import ProxyUnavailable, ROOT
from .queries import MODELS, query_data, records, task_records
from .exports import export_file, export_filename
from .auth import router as auth_router, authenticated, COOKIE_NAME, session_key
from .qr_login import qr_manager
from .deletion import delete_task_record, delete_data_record, delete_data_records


@asynccontextmanager
async def lifespan(app):
    initialize()
    scheduler.start()
    yield
    scheduler.close()
    qr_manager.cancel_all()


app = FastAPI(title='小红书数据采集系统', version='1.0.0', lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', '[::1]', 'testserver'])
app.include_router(auth_router)


@app.middleware('http')
async def local_origin(request: Request, call_next):
    origin = request.headers.get('origin')
    same_origin = f'{request.url.scheme}://{request.url.netloc}'
    if origin and origin != same_origin and origin not in {'http://127.0.0.1:5173', 'http://localhost:5173', 'http://127.0.0.1:8000', 'http://localhost:8000'}:
        return JSONResponse({'detail': '仅接受本机管理页面请求'}, status_code=403)
    public_paths = {'/api/health', '/api/auth/login', '/api/auth/session', '/api/auth/logout'}
    if request.url.path.startswith('/api/') and request.url.path not in public_paths and not authenticated(request):
        return JSONResponse({'detail': '请先登录系统'}, status_code=401, headers={'Cache-Control': 'no-store'})
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Never echo request bodies (in particular Cookie) in validation responses.
    return JSONResponse({'detail': [{'loc': e['loc'], 'msg': e['msg'], 'type': e['type']} for e in exc.errors()]}, status_code=422)


@app.get('/api/health')
def health():
    return {'status': 'ok', 'timezone': 'UTC', 'display_timezone': 'Asia/Shanghai'}


@app.get('/api/login')
def login_status():
    with session() as db:
        row = db.get(Login, 1)
        return {'configured': bool(row.cookie), 'masked': '已保存（内容隐藏）' if row.cookie else '未配置',
                'status': row.status, 'account': row.account, 'updated_at': row.updated_at}


@app.put('/api/login')
def set_login(body: CookieInput):
    qr_manager.cancel_all()
    with MUTEX, session() as db:
        row = db.get(Login, 1)
        row.cookie, row.status, row.account, row.updated_at = body.cookie.get_secret_value().strip(), 'unchecked', {}, now()
    return login_status()


@app.delete('/api/login')
def clear_login():
    # Match the QR commit lock order so a late scan cannot restore cleared credentials.
    with qr_manager.lock, MUTEX, session() as db:
        if db.scalar(select(Task.id).where(Task.status.in_(['running', 'stopping', 'pausing'])).limit(1)):
            raise HTTPException(409, '请先停止正在运行的采集任务，等待结束后再清除 Cookie')
        qr_manager.discard_all()
        row = db.get(Login, 1)
        row.cookie, row.status, row.account, row.updated_at = '', 'unchecked', {}, now()
    return login_status()


@app.post('/api/login/qrcode', status_code=202)
def start_qrcode(request: Request):
    return qr_manager.start(session_key(request.cookies.get(COOKIE_NAME, '')))


@app.get('/api/login/qrcode/{sid}')
def qrcode_status(sid: str, request: Request):
    return qr_manager.get(sid, session_key(request.cookies.get(COOKIE_NAME, '')))


@app.delete('/api/login/qrcode/{sid}')
def cancel_qrcode(sid: str, request: Request):
    return qr_manager.cancel(sid, session_key(request.cookies.get(COOKIE_NAME, '')))


@app.post('/api/login/check')
def check_login():
    with session() as db:
        cookie = db.get(Login, 1).cookie
    if not cookie:
        raise HTTPException(400, '请先保存 Cookie')
    try:
        with Collector(cookie, threading.Event(), {'interval_min': 3, 'interval_max': 5, 'retries': 1}, lambda *_: None) as collector:
            account = collector.account()
    except ProxyUnavailable as exc:
        raise HTTPException(503, str(exc)) from None
    except Exception:
        with MUTEX, session() as db:
            row = db.get(Login, 1)
            if row.cookie == cookie:
                row.status, row.account = 'invalid', {}
        raise HTTPException(400, '登录检测失败：Cookie 失效、平台验证或本地签名环境异常，请检查 Cookie 与 Node 依赖') from None
    with MUTEX, session() as db:
        row = db.get(Login, 1)
        if row.cookie != cookie:
            raise HTTPException(409, '检测期间 Cookie 已更新，请重新检测')
        row.status, row.account = 'valid', account
    return login_status()


@app.post('/api/tasks', status_code=201)
def add_task(body: TaskInput):
    return create_task(body)


@app.get('/api/tasks')
def list_tasks(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
               status: str = '', kind: Literal['', 'blogger', 'keyword', 'notes'] = '', q: str = ''):
    stmt = select(Task)
    if status:
        stmt = stmt.where(Task.status == status)
    if kind:
        stmt = stmt.where(Task.kind == kind)
    if q:
        stmt = stmt.where(Task.target.contains(q, autoescape=True))
    with session() as db:
        total = db.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = db.scalars(stmt.order_by(Task.created_at.desc(), Task.id).offset((page - 1) * page_size).limit(page_size))
        return {'items': task_records(db, rows), 'total': total, 'page': page, 'page_size': page_size}


@app.get('/api/tasks/{tid}')
def task_detail(tid: str):
    with session() as db:
        row = db.get(Task, tid)
        if not row:
            raise HTTPException(404, '任务不存在')
        return task_records(db, [row])[0]


@app.post('/api/tasks/{tid}/pause')
def pause(tid: str):
    return pause_task(tid)


@app.post('/api/tasks/{tid}/stop')
def stop(tid: str):
    result = stop_task(tid)
    if not result:
        raise HTTPException(404, '任务不存在')
    return result


@app.delete('/api/tasks/{tid}')
def delete_task(tid: str):
    return delete_task_record(tid)


@app.post('/api/tasks/{tid}/retry', status_code=201)
def retry(tid: str):
    old = task_detail(tid)
    if old['status'] not in ('partial_failed', 'failed', 'interrupted', 'stopped'):
        raise HTTPException(409, '当前任务没有可重试的失败项')
    params = dict(old['params'])
    failed_urls = [x['url'] for x in old['failures'] if x.get('url')]
    source_failed = any(x.get('target') for x in old['failures'])
    if failed_urls and not source_failed:
        params.update(kind='notes', target=failed_urls[0], urls=failed_urls)
    elif old['status'] in ('stopped', 'interrupted'):
        raise HTTPException(409, '该任务被停止或中断；请使用原参数新建任务。失败项重试仅针对已记录的失败项')
    return create_task(TaskInput(**params))


@app.post('/api/tasks/{tid}/resume')
def resume(tid: str):
    return resume_task(tid)


@app.get('/api/tasks/{tid}/logs')
def logs(tid: str, after: int = Query(0, ge=0), limit: int = Query(200, ge=1, le=1000)):
    task_detail(tid)
    with session() as db:
        rows = db.scalars(select(TaskLog).where(TaskLog.task_id == tid, TaskLog.id > after).order_by(TaskLog.id).limit(limit)).all()
        return {'items': [as_dict(row) for row in rows], 'next_cursor': rows[-1].id if rows else after}


@app.get('/api/stats')
def stats():
    with session() as db:
        result = {key: db.scalar(select(func.count()).select_from(model)) for key, model in dict(bloggers=Blogger, notes=Note, comments=Comment, tasks=Task).items()}
        result['running'] = db.scalar(select(func.count()).select_from(Task).where(Task.status.in_(['running', 'stopping', 'pausing'])))
        result['pending'] = db.scalar(select(func.count()).select_from(Task).where(Task.status == 'pending'))
        result['recent'] = task_records(db, db.scalars(select(Task).order_by(Task.created_at.desc()).limit(6)))
        return result


@app.get('/api/data/{entity}')
def list_data(entity: Literal['bloggers', 'notes', 'comments'], page: int = Query(1, ge=1),
              page_size: int = Query(20, ge=1, le=100), q: str = '', user_id: str = '', note_id: str = '',
              keyword: str = '', note_type: Literal['', 'normal', 'video'] = '', level: int | None = Query(None, ge=1, le=2),
              task_id: str = '', published_from: str | None = None, published_to: str | None = None,
              sort: Literal['collected_at', 'id', 'published_at'] = 'collected_at', order: Literal['asc', 'desc'] = 'desc'):
    filters = locals().copy()
    stmt = query_data(entity, **{k: v for k, v in filters.items() if k != 'entity'})
    model = MODELS[entity]
    if not hasattr(model, sort):
        raise HTTPException(422, '此数据类型不支持该排序字段')
    col = getattr(model, sort)
    with session() as db:
        total = db.scalar(select(func.count()).select_from(stmt.subquery()))
        items = records(db, entity, stmt.order_by(col.asc() if order == 'asc' else col.desc(), model.id).offset((page - 1) * page_size).limit(page_size))
        return {'items': items, 'total': total, 'page': page, 'page_size': page_size}


@app.get('/api/notes/{nid}')
def note_detail(nid: str):
    with session() as db:
        note = db.get(Note, nid)
        if not note:
            raise HTTPException(404, '笔记不存在')
        return records(db, 'notes', select(Note).where(Note.id == nid))[0]


@app.delete('/api/data/{entity}/{data_id}')
def delete_data(entity: Literal['bloggers', 'notes', 'comments'], data_id: str):
    return delete_data_record(entity, data_id)


@app.post('/api/data/{entity}/batch-delete')
def batch_delete_data(entity: Literal['notes', 'comments'], body: BatchDeleteInput):
    return delete_data_records(entity, body.ids)


@app.get('/api/export')
def export(fmt: Literal['xlsx', 'csv'] = 'xlsx', entity: Literal['bloggers', 'notes', 'comments'] = 'notes',
           task_id: str = '', q: str = '', user_id: str = '', note_id: str = '', keyword: str = '',
           note_type: Literal['', 'normal', 'video'] = '', level: int | None = Query(None, ge=1, le=2),
           published_from: str | None = None, published_to: str | None = None):
    filters = locals().copy()
    filters.pop('fmt')
    filters.pop('entity')
    with session() as db:
        payload = export_file(db, fmt, entity, filters)
        filename = export_filename(db, fmt, entity, filters)
    mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if fmt == 'xlsx' else 'text/csv; charset=utf-8'
    disposition = f'attachment; filename="xhs-{entity}.{fmt}"; filename*=UTF-8\'\'{quote(filename, safe="")}'
    return Response(payload, media_type=mime, headers={'Content-Disposition': disposition})


frontend = ROOT / 'frontend' / 'dist'
if (frontend / 'assets').is_dir():
    app.mount('/assets', StaticFiles(directory=frontend / 'assets'), name='assets')


@app.get('/{path:path}', include_in_schema=False)
def spa(path: str):
    if path.startswith('api/') or not (frontend / 'index.html').exists():
        raise HTTPException(404, '接口不存在或前端尚未构建；API 文档见 /docs')
    return FileResponse(frontend / 'index.html')
