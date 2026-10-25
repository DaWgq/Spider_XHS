"""Single local account with opaque, server-side sessions."""
import hashlib
import hmac
import secrets
import threading
import time
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, SecretStr

router = APIRouter(prefix='/api/auth', tags=['系统登录'])
COOKIE_NAME = 'xhs_admin_session'
SESSION_TTL = 12 * 60 * 60
PASSWORD_HASH = '0ecde93d302d953d5abddf3d7569a089e54e2499b403f453acb93712fea99c64'
_sessions = {}
_lock = threading.Lock()


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: SecretStr = Field(min_length=1, max_length=128)


def session_key(token):
    return hashlib.sha256(token.encode()).hexdigest()


def authenticated(request: Request):
    token = request.cookies.get(COOKIE_NAME, '')
    if not token:
        return False
    with _lock:
        key = session_key(token)
        expires = _sessions.get(key, 0)
        if expires <= time.time():
            _sessions.pop(key, None)
            return False
        return True


@router.get('/session')
def current_session(request: Request):
    valid = authenticated(request)
    return {'authenticated': valid, 'username': 'dawg' if valid else None}


@router.post('/login')
def sign_in(body: Credentials, request: Request, response: Response):
    password_hash = hashlib.pbkdf2_hmac('sha256', body.password.get_secret_value().encode(), b'xhs-local-single-user-v1', 200000).hex()
    if not (hmac.compare_digest(body.username.encode(), b'dawg') and hmac.compare_digest(password_hash, PASSWORD_HASH)):
        raise HTTPException(401, '账号或密码不正确')
    token = secrets.token_urlsafe(32)
    with _lock:
        expired = [key for key, value in _sessions.items() if value <= time.time()]
        for key in expired:
            _sessions.pop(key, None)
        old = request.cookies.get(COOKIE_NAME)
        if old:
            _sessions.pop(session_key(old), None)
        if len(_sessions) >= 128:
            _sessions.pop(next(iter(_sessions)))
        _sessions[session_key(token)] = time.time() + SESSION_TTL
    response.set_cookie(COOKIE_NAME, token, max_age=SESSION_TTL, httponly=True, samesite='strict', secure=False, path='/')
    return {'authenticated': True, 'username': 'dawg'}


@router.post('/logout')
def sign_out(request: Request, response: Response):
    from .qr_login import qr_manager
    qr_manager.cancel_owner(session_key(request.cookies.get(COOKIE_NAME, '')))
    with _lock:
        _sessions.pop(session_key(request.cookies.get(COOKIE_NAME, '')), None)
    response.delete_cookie(COOKIE_NAME, path='/')
    return {'authenticated': False}
