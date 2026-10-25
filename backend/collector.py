"""The only bridge to upstream APIs. No signing implementation is copied here."""
import contextvars
import threading
import time
import random
from urllib.parse import urlparse, parse_qs, urlencode
from .config import proxy_ready, ProxyUnavailable, network_proxies
from .storage import save_blogger, save_note, save_comment


class Cancelled(RuntimeError):
    pass


class AccessBlocked(RuntimeError):
    pass


class ItemError(RuntimeError):
    pass


active_guard = contextvars.ContextVar('collector_guard', default=None)
_installed = False
_install_lock = threading.Lock()


class Guard:
    def __init__(self, stop, interval_min=3, interval_max=None):
        self.stop = stop
        self.interval_min = interval_min
        self.interval_max = interval_min if interval_max is None else interval_max
        self.last_request = 0
        self.fatal = None
        self.transport_failed = False

    def check(self):
        if self.stop.is_set():
            raise Cancelled('用户停止任务')
        if self.fatal:
            raise self.fatal

    def wait(self, seconds):
        if self.stop.wait(max(0, seconds)):
            raise Cancelled('用户停止任务')

    def before(self):
        self.check()
        if self.last_request:
            interval = random.uniform(self.interval_min, self.interval_max)
            self.wait(interval - (time.monotonic() - self.last_request))
        proxy_ready()
        self.check()


def install_transport_guard():
    global _installed
    with _install_lock:
        if _installed:
            return
        from loguru import logger
        # Upstream logger.exception includes traceback locals; disable it in this app.
        logger.disable('apis')
        logger.disable('xhs_utils')
        from xhs_utils.xhs_core.http import BrowserHttpClient
        original = BrowserHttpClient.request

        def guarded(client, method, url, **kwargs):
            guard = active_guard.get()
            if guard is None:
                raise AccessBlocked('采集请求缺少代理及停止控制上下文')
            try:
                guard.before()
                kwargs['proxies'] = network_proxies()
                kwargs['timeout'] = 15
                kwargs['allow_redirects'] = False
                try:
                    response = original(client, method, url, **kwargs)
                except Exception:
                    guard.transport_failed = True
                    proxy_ready()  # Recheck before any bounded retry.
                    raise ItemError('网络请求失败：连接超时、重置或平台不可达') from None
                if response.status_code in (401, 403, 406, 429, 461, 471):
                    raise AccessBlocked(f'平台拒绝访问（HTTP {response.status_code}），请检查 Cookie 或在官方客户端处理验证')
                try:
                    body = response.json()
                except Exception:
                    body = {}
                code = str(body.get('code', '')) if isinstance(body, dict) else ''
                message = str(body.get('msg', '')) if isinstance(body, dict) else ''
                if code in ('-100', '-101', '-102', '300012', '300013') or any(x in message.lower() for x in ('登录', '验证码', '访问频繁', '访问限制', '风控', 'captcha', 'login', '限流', '验证')):
                    raise AccessBlocked('Cookie 失效或平台要求验证/限制访问；任务已停止，请人工处理后重试')
                return response
            except (Cancelled, AccessBlocked, ProxyUnavailable) as exc:
                guard.fatal = exc
                raise
            finally:
                guard.last_request = time.monotonic()

        BrowserHttpClient.request = guarded
        _installed = True


class Collector:
    def __init__(self, cookie, stop, params, log):
        self.cookie, self.params, self.log = cookie, params, log
        # Old tasks with only `interval=4` use the new random default as well.
        self.guard = Guard(stop, params.get('interval_min', 3), params.get('interval_max', 5))
        self.auth = None

    def __enter__(self):
        proxy_ready()
        install_transport_guard()
        self.token = active_guard.set(self.guard)
        try:
            from apis.xhs_pc_apis import XHS_Apis
            from xhs_utils.xhs_pc import XHSPcAuth
            from xhs_utils.xhs_pc.http import PcHttpClient
            proxies = network_proxies()
            self.http = PcHttpClient(proxies=proxies)
            if not any(proxies.values()):
                self.http.session.trust_env = False
            self.auth = XHSPcAuth.from_cookie(self.cookie, proxies=proxies, http_client=self.http)
            self.api = XHS_Apis(self.auth)
            self.guard.check()
            return self
        except Exception:
            active_guard.reset(self.token)
            if self.auth:
                self.auth.close()
            elif hasattr(self, 'http'):
                self.http.close()
            if self.guard.fatal:
                raise self.guard.fatal
            raise AccessBlocked('登录初始化失败：请检查 Cookie、Node.js 和 crypto-js 依赖') from None

    def __exit__(self, *_):
        try:
            if self.auth:
                self.auth.close()
        finally:
            active_guard.reset(self.token)

    def call(self, method, *args, **kwargs):
        for attempt in range(self.params.get('retries', 2) + 1):
            self.guard.check()
            self.guard.transport_failed = False
            try:
                success, _, result = method(*args, **kwargs)
            except (Cancelled, AccessBlocked, ProxyUnavailable):
                raise
            except Exception:
                success, result = False, None
            self.guard.check()
            if success and isinstance(result, dict) and isinstance(result.get('data'), dict):
                return result['data']
            # Business failures are not retried. Only transport failures get backoff.
            if not self.guard.transport_failed or attempt >= self.params.get('retries', 2):
                code = (result or {}).get('code') if isinstance(result, dict) else None
                raise ItemError(f'平台接口 {method.__name__} 未成功返回数据（code={code}），请检查链接或访问权限')
            proxy_ready()
            self.log('网络请求失败，有限退避后重试', 'warning')
            self.guard.wait(min(8, 2 ** attempt))

    def account(self):
        data = self.call(self.api.get_user_me)
        if not data.get('user_id') or data.get('guest') is True:
            raise AccessBlocked('当前 Cookie 未登录或已失效')
        return {key: data.get(key) for key in ('user_id', 'nickname', 'red_id', 'avatar')}

    def targets(self, task_id):
        p = self.params
        if p['kind'] == 'notes':
            yield from ((url, None) for url in p['urls'])
            return
        parsed = urlparse(p['target'])
        query = parse_qs(parsed.query)
        uid = parsed.path.rstrip('/').split('/')[-1] if parsed.scheme else p['target']
        if p['kind'] == 'blogger':
            profile = self.call(self.api.get_user_info, uid)
            save_blogger(uid, profile, task_id)
        seen, cursors, cursor, page = set(), set(), '', 1
        from xhs_utils.xhs_pc.params import generate_search_id
        search_root = generate_search_id()
        while len(seen) < p['max_notes']:
            if p['kind'] == 'blogger':
                data = self.call(self.api.get_user_note_info, uid, cursor, query.get('xsec_token', [''])[0], query.get('xsec_source', ['pc_user'])[0])
                items = data.get('notes') or []
            else:
                data = self.call(self.api.search_note, p['target'], page=page, sort_type_choice=p['sort'], note_type=p['note_type'], search_id=generate_search_id(search_root))
                items = [x for x in data.get('items', []) if x.get('model_type', 'note') == 'note']
            added = 0
            for item in items:
                nid = item.get('note_id') or item.get('id')
                if not nid or nid in seen:
                    continue
                seen.add(nid)
                added += 1
                token = item.get('xsec_token', '')
                url = f'https://www.xiaohongshu.com/explore/{nid}?' + urlencode({'xsec_token': token, 'xsec_source': 'pc_user' if p['kind'] == 'blogger' else 'pc_search'})
                yield url, item
                if len(seen) >= p['max_notes']:
                    return
            if not data.get('has_more') or not items:
                self.log('平台已无下一页，按实际返回数量结束')
                return
            if added == 0:
                raise ItemError('分页未产生新笔记，已终止，防止重复请求')
            if p['kind'] == 'blogger':
                next_cursor = str(data.get('cursor') or '')
                if not next_cursor or next_cursor == cursor or next_cursor in cursors:
                    raise ItemError('博主分页游标未推进，已终止')
                cursors.add(next_cursor)
                cursor = next_cursor
            page += 1

    def collect_note(self, url, item, task_id):
        self.guard.check()
        if self.params['details'] or item is None:
            data = self.call(self.api.get_note_info, url)
            items = data.get('items') or []
            if not items:
                raise ItemError('笔记详情为空，可能已删除或无访问权限')
            item = items[0]
        nid = save_note(item, url, task_id)
        if self.params['comments'] and self.params['max_comments']:
            self.collect_comments(nid, parse_qs(urlparse(url).query).get('xsec_token', [''])[0], task_id)

    def collect_comments(self, nid, token, task_id):
        p = self.params
        roots, replies, cursors = set(), set(), set()
        cursor = ''
        while len(roots) < p['max_comments']:
            previous_count = len(roots)
            data = self.call(self.api.get_note_out_comment, nid, cursor, token)
            comments = data.get('comments') or []
            for comment in comments:
                self.guard.check()
                cid = comment.get('id')
                if not cid or cid in roots:
                    continue
                roots.add(cid)
                save_comment(comment, nid, 1, None, task_id)
                if p['replies'] and len(replies) < p['max_replies']:
                    nested = dict(comment, note_id=nid)
                    batch = nested.get('sub_comments') or []
                    sub_cursor = str(nested.get('sub_comment_cursor') or '')
                    has_more = nested.get('sub_comment_has_more', False)
                    sub_seen = set()
                    first_batch = True
                    while True:
                        previous_reply_count = len(replies)
                        for reply in batch:
                            self.guard.check()
                            rid = reply.get('id')
                            if rid and rid not in replies and len(replies) < p['max_replies']:
                                save_comment(reply, nid, 2, str(cid), task_id)
                                replies.add(rid)
                        if not has_more or len(replies) >= p['max_replies']:
                            break
                        if not first_batch and len(replies) == previous_reply_count:
                            raise ItemError('二级评论分页没有新增数据，已终止')
                        first_batch = False
                        if not sub_cursor or sub_cursor in sub_seen:
                            raise ItemError('二级评论游标未推进，已终止该笔记评论采集')
                        sub_seen.add(sub_cursor)
                        sub = self.call(self.api.get_note_inner_comment, nested, sub_cursor, token)
                        batch = sub.get('comments') or []
                        if not batch:
                            break
                        sub_cursor = str(sub.get('cursor') or '')
                        has_more = sub.get('has_more', False)
                if len(roots) >= p['max_comments']:
                    break
            if not data.get('has_more') or not comments or len(roots) >= p['max_comments']:
                break
            if len(roots) == previous_count:
                raise ItemError('一级评论分页没有新增数据，已终止')
            next_cursor = str(data.get('cursor') or '')
            if not next_cursor or next_cursor == cursor or next_cursor in cursors:
                raise ItemError('一级评论游标未推进，已终止该笔记评论采集')
            cursors.add(next_cursor)
            cursor = next_cursor
