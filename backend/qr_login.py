"""Browser-free QR login using the upstream PC login client."""
import base64
import secrets
import threading
import time
import shutil
import subprocess
import logging
from urllib.parse import urlparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select
from .collector import Guard, Cancelled, AccessBlocked, active_guard, install_transport_guard
from .config import proxy_ready, network_proxies, ProxyUnavailable, ROOT
from .db import session, Login, Task, now

ACTIVE_STATES = {'initializing', 'waiting', 'scanned', 'verifying'}
INIT_TIMEOUT = 120
SCAN_TIMEOUT = 180
VERIFY_TIMEOUT = 45


class QRLoginError(RuntimeError):
    """Predefined diagnostic text, never raw upstream secrets."""


def check_runtime():
    node = shutil.which('node')
    if not node:
        raise QRLoginError('服务器找不到 Node.js，请确认后端进程的 PATH 中包含 node')
    try:
        result = subprocess.run([node, '-e', "require('crypto-js');process.stdout.write('ok')"],
            cwd=ROOT, capture_output=True, text=True, timeout=5)
    except subprocess.TimeoutExpired:
        raise QRLoginError('Node.js 运行检查超时，请检查服务器运行环境') from None
    if result.returncode != 0:
        raise QRLoginError('根目录 crypto-js 依赖不可用，请在 Spider_XHS 根目录安装 Node 依赖')
    try:
        from qrcode.image.svg import SvgPathImage
    except ImportError:
        raise QRLoginError('后端缺少 qrcode 依赖，请在当前 Python 虚拟环境安装项目依赖') from None


def build_login_api():
    from apis.xhs_pc_login_apis import XHSLoginApi
    from xhs_utils.xhs_pc.http import PcHttpClient
    proxies = network_proxies()
    http = PcHttpClient(proxies=proxies)
    if not any(proxies.values()):
        http.session.trust_env = False
    try:
        return XHSLoginApi(proxies=proxies, http_client=http)
    except Exception:
        http.close()
        raise


def qr_image(url):
    import qrcode
    from qrcode.image.svg import SvgPathImage
    svg = qrcode.make(url, image_factory=SvgPathImage, border=4).to_string()
    return 'data:image/svg+xml;base64,' + base64.b64encode(svg).decode('ascii')


@dataclass
class QRSession:
    id: str
    owner: str = field(repr=False)
    initial_updated_at: str = field(repr=False)
    state: str = 'initializing'
    message: str = '正在初始化登录环境并生成二维码，请稍候'
    image: str | None = None
    account: dict = field(default_factory=dict)
    started_at: float = field(default_factory=time.monotonic, repr=False)
    stage: str = 'runtime'
    stage_label: str = '检查运行环境'
    request_count: int = 0
    request: str = ''
    phase_timeout_seconds: int = INIT_TIMEOUT
    deadline: float = field(default_factory=lambda: time.monotonic() + INIT_TIMEOUT, repr=False)
    expires_at: str = field(default_factory=lambda: datetime.fromtimestamp(time.time() + 180, timezone.utc).isoformat())
    stop: threading.Event = field(default_factory=threading.Event, repr=False)
    thread: threading.Thread | None = field(default=None, repr=False)
    timer: threading.Timer | None = field(default=None, repr=False)


class QRLoginManager:
    def __init__(self):
        self.lock = threading.RLock()
        self.sessions = {}

    def start(self, owner):
        with session() as db:
            if db.scalar(select(Task.id).where(Task.status.in_(['running', 'stopping', 'pausing'])).limit(1)):
                raise HTTPException(409, '请先停止正在运行的采集任务，再切换小红书登录账号')
            updated = db.get(Login, 1).updated_at
        with self.lock:
            self.cancel_all()
            # Keep only a bounded number of recent cached outcomes.
            while len(self.sessions) >= 20:
                self.sessions.pop(next(iter(self.sessions)))
            item = QRSession(id=secrets.token_urlsafe(24), owner=owner, initial_updated_at=updated)
            self.sessions[item.id] = item
            self.arm_timeout(item, INIT_TIMEOUT)
            item.thread = threading.Thread(target=self.run, args=(item,), daemon=True, name='xhs-qr-login')
            item.thread.start()
            return self.snapshot(item)

    def snapshot(self, item):
        # Cookie, QR exchange secrets and device state must never leave this process.
        return {'id': item.id, 'state': item.state, 'message': item.message,
                'image': item.image, 'account': dict(item.account), 'expires_at': item.expires_at,
                'stage': item.stage, 'stage_label': item.stage_label, 'request_count': item.request_count,
                'request': item.request, 'elapsed_seconds': int(time.monotonic() - item.started_at),
                'phase_timeout_seconds': item.phase_timeout_seconds,
                'remaining_seconds': max(0, int(item.deadline - time.monotonic() + 0.999))}

    def get(self, sid, owner):
        with self.lock:
            item = self.sessions.get(sid)
            if not item or item.owner != owner:
                raise HTTPException(404, '二维码会话不存在或已失效，请重新生成')
            self.expire(item, item.deadline)
            return self.snapshot(item)

    def cancel(self, sid, owner):
        with self.lock:
            self.get(sid, owner)
            self._cancel(self.sessions[sid])
            return self.snapshot(self.sessions[sid])

    def _cancel(self, item):
        if item.state in ACTIVE_STATES:
            item.stop.set()
            item.state, item.message, item.image = 'cancelled', '已取消扫码登录', None
            if item.timer:
                item.timer.cancel()

    def arm_timeout(self, item, seconds):
        with self.lock:
            if item.timer:
                item.timer.cancel()
            item.deadline = time.monotonic() + seconds
            item.phase_timeout_seconds = seconds
            item.expires_at = datetime.fromtimestamp(time.time() + seconds, timezone.utc).isoformat()
            item.timer = threading.Timer(seconds, self.expire, args=(item, item.deadline))
            item.timer.daemon = True
            item.timer.start()

    def expire(self, item, expected_deadline):
        with self.lock:
            if item.deadline != expected_deadline or item.state not in ACTIVE_STATES or time.monotonic() < item.deadline:
                return
            item.stop.set()
            if item.state in ('waiting', 'scanned'):
                item.state, item.message = 'expired', '等待扫码超时，请重新生成二维码'
            else:
                item.state, item.message = 'failed', f'{item.stage_label}超时，已停止等待。请检查服务器网络和 Node.js 运行环境；原 Cookie 未修改'
            item.image = None
            logging.getLogger('uvicorn.error').warning('QR login timeout: stage=%s request=%s', item.stage, item.request)

    def stage(self, item, key, label):
        self.change(item, 'initializing', label, stage=key, stage_label=label, request='')

    def progress(self, item, method, url, event):
        parsed = urlparse(url)
        safe_request = f'{method.upper()} {parsed.hostname or ""}{parsed.path}'
        with self.lock:
            if item.stop.is_set():
                raise Cancelled('扫码登录已结束')
            item.request = safe_request
            if event == 'requesting':
                item.request_count += 1
                if item.state in ('initializing', 'verifying'):
                    item.message = f'{item.stage_label}：正在请求平台（单次最长 15 秒）'
            elif event == 'received':
                if item.state in ('initializing', 'verifying'):
                    item.message = f'{item.stage_label}：请求已返回，正在处理响应与下一步签名'
            else:
                if item.state in ('initializing', 'verifying'):
                    item.message = f'{item.stage_label}：正在准备请求'

    def diagnostic(self, item, exc):
        # Classify known failures without returning their raw text or traceback.
        reason = str(exc).lower()
        if isinstance(exc, QRLoginError):
            return str(exc)
        if 'abrequestid' in reason:
            return '平台主页未返回匿名设备标识，服务器访问可能受到限制'
        if 'crypto-js' in reason or 'cannot find module' in reason:
            return '服务器 Node 签名依赖缺失，请检查根目录 npm 依赖'
        if 'timeout' in reason or 'timed out' in reason or '超时' in reason:
            return '网络请求或本地签名计算超时，请检查服务器运行环境'
        if 'gid' in reason or 'webprofile' in reason:
            return '平台设备校验未通过，请检查服务器网络或在官方客户端处理验证'
        if 'scripting' in reason or 'seccallback' in reason or 'secpoisonid' in reason or 'getdss' in reason:
            return '平台安全初始化返回异常，未取得有效登录环境'
        if 'activate' in reason or 'ssk' in reason:
            return '匿名登录会话建立失败，平台没有返回完整登录参数'
        return f'{item.stage_label}失败，请检查网络、Node.js 依赖或平台验证状态'

    def cancel_all(self):
        with self.lock:
            for item in self.sessions.values():
                self._cancel(item)

    def cancel_owner(self, owner):
        with self.lock:
            for item in self.sessions.values():
                if item.owner == owner:
                    self._cancel(item)

    def discard_all(self):
        with self.lock:
            self.cancel_all()
            self.sessions.clear()

    def change(self, item, state, message, **values):
        with self.lock:
            if item.stop.is_set():
                raise Cancelled('扫码登录已取消')
            item.state, item.message = state, message
            for key, value in values.items():
                setattr(item, key, value)

    def run(self, item):
        # Preserve the upstream authentication handshake cadence. Collection
        # pacing must not add a 3–5 second sleep to every cold-start SDK request.
        guard = Guard(item.stop, 0, 0)
        guard.qr_login = True
        guard.progress = lambda method, url, event: self.progress(item, method, url, event)
        token = active_guard.set(guard)
        api = None
        try:
            proxy_ready()
            install_transport_guard()
            self.stage(item, 'runtime', '检查 Node.js 与二维码依赖')
            check_runtime()
            api = build_login_api()
            guard.check()
            self.stage(item, 'anonymous', '初始化小红书匿名设备与安全会话')
            cookies = api.generate_init_cookies()
            guard.check()
            self.stage(item, 'create_qr', '向小红书申请二维码')
            success, _, data = api.generate_qrcode(cookies)
            guard.check()
            if not success or not isinstance(data, dict) or not all(data.get(k) for k in ('qr_id', 'code', 'qr_url')):
                raise RuntimeError('二维码创建失败')
            cookies = data['cookies']
            self.stage(item, 'precheck', '预检查二维码状态')
            # Preserve upstream ordering: create -> anonymous precheck -> webprofile.
            success, message, cookies = api.check_qrcode_status(data['qr_id'], data['code'], cookies)
            guard.check()
            if success or message != '请扫描二维码':
                raise RuntimeError('二维码预检查失败')
            self.stage(item, 'webprofile', '校验登录设备信息')
            api.ensure_webprofile(cookies)
            guard.check()
            guard.interval_min, guard.interval_max = 3, 5
            self.arm_timeout(item, SCAN_TIMEOUT)
            self.change(item, 'waiting', '请使用小红书 App 扫码，并在手机上确认登录', image=qr_image(data['qr_url']), stage='scan', stage_label='等待扫码与手机确认')
            while time.monotonic() < item.deadline:
                guard.check()
                success, message, cookies = api.check_qrcode_status(data['qr_id'], data['code'], cookies)
                guard.check()
                if success:
                    self.arm_timeout(item, VERIFY_TIMEOUT)
                    self.change(item, 'verifying', '已确认，正在验证正式登录状态', stage='verify', stage_label='验证正式登录账号')
                    success, user, cookies = api.get_user_info(cookies)
                    guard.check()
                    if not success or user.get('guest') is not False or not user.get('user_id'):
                        raise AccessBlocked('扫码后未取得有效的正式登录状态，请重试')
                    fields = {key: user.get(key) for key in ('user_id', 'nickname', 'red_id', 'avatar')}
                    saved_cookie = api.cookies_to_str(cookies)
                    if not cookies.get('web_session') or not cookies.get('a1'):
                        raise AccessBlocked('扫码登录未返回完整凭证，请重试')
                    with self.lock, session() as db:
                        guard.check()
                        row = db.get(Login, 1)
                        if row.updated_at != item.initial_updated_at:
                            raise Cancelled('登录配置已更新，本次扫码结果不再覆盖')
                        row.cookie, row.status, row.account, row.updated_at = saved_cookie, 'valid', fields, now()
                        item.state, item.message, item.account, item.image = 'succeeded', '登录成功，Cookie 已自动保存在后端', fields, None
                    return
                if message == '二维码已过期':
                    self.change(item, 'expired', '二维码已过期，请重新生成', image=None)
                    return
                if message == '请确认登录':
                    self.change(item, 'scanned', '已扫码，请在小红书 App 中确认登录')
                elif message == '请扫描二维码':
                    self.change(item, 'waiting', '请使用小红书 App 扫描二维码')
                else:
                    raise AccessBlocked('扫码状态异常或平台要求进一步验证，请在官方客户端处理后重试')
                # The transport guard enforces random 3–5 second request spacing.
                guard.wait(0.25)
            self.change(item, 'expired', '等待扫码超时，请重新生成二维码', image=None)
        except Cancelled:
            with self.lock:
                if item.state in ACTIVE_STATES:
                    item.state, item.message, item.image = 'cancelled', '扫码登录已取消或配置已更新', None
        except (ProxyUnavailable, AccessBlocked) as exc:
            with self.lock:
                if not item.stop.is_set():
                    item.state, item.message, item.image = 'failed', str(exc), None
        except Exception as exc:
            with self.lock:
                if not item.stop.is_set():
                    error = guard.fatal or exc
                    message = str(error) if isinstance(error, (ProxyUnavailable, AccessBlocked)) else self.diagnostic(item, error)
                    item.state, item.message, item.image = 'failed', message + '；原 Cookie 未修改', None
                    logging.getLogger('uvicorn.error').warning('QR login failed: stage=%s request=%s error_type=%s', item.stage, item.request, type(error).__name__)
        finally:
            if item.timer:
                item.timer.cancel()
            try:
                if api:
                    api.close()
            finally:
                active_guard.reset(token)


qr_manager = QRLoginManager()
