import os
import socket
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get('XHS_DATA_DIR', ROOT / 'local_data')).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
PROXIES = {'http': 'http://127.0.0.1:7897', 'https': 'http://127.0.0.1:7897'}
# Deployment works without a local proxy; proxy mode is an explicit opt-in.
NETWORK_MODE = os.environ.get('XHS_NETWORK_MODE', 'direct').strip().lower()
if NETWORK_MODE not in ('proxy', 'direct'):
    raise ValueError('XHS_NETWORK_MODE 只允许 proxy（本地代理）或 direct（云端直连）')


def network_proxies():
    # Explicit empty proxies also disable libcurl's inherited proxy selection.
    return dict(PROXIES) if NETWORK_MODE == 'proxy' else {'http': '', 'https': ''}


class ProxyUnavailable(RuntimeError):
    pass


def proxy_ready():
    if NETWORK_MODE == 'direct':
        for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY'):
            os.environ[key] = ''
            os.environ[key.lower()] = ''
        os.environ['NO_PROXY'] = '*'
        os.environ['no_proxy'] = '*'
        return
    values = dict(HTTP_PROXY=PROXIES['http'], HTTPS_PROXY=PROXIES['https'],
                  ALL_PROXY='socks5://127.0.0.1:7898', NO_PROXY='localhost,127.0.0.1,::1')
    for key, value in values.items():
        os.environ[key] = value
        os.environ[key.lower()] = value
    try:
        with socket.create_connection(('127.0.0.1', 7897), timeout=0.8):
            pass
    except OSError:
        raise ProxyUnavailable('本机代理 127.0.0.1:7897 不可用，已停止请求；请启动 Clash/Mihomo') from None
