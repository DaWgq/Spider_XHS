"""Offline network-mode regressions; sockets are always mocked."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class NetworkConfigTests(unittest.TestCase):
    def setUp(self):
        test_root = Path(__file__).resolve().parents[1] / 'local_data'
        test_root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='network-config-', dir=test_root)
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {'XHS_DATA_DIR': self.temp.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        os.environ.pop('XHS_NETWORK_MODE', None)

    def config(self, mode=None):
        if mode is not None:
            os.environ['XHS_NETWORK_MODE'] = mode
        path = Path(__file__).resolve().parents[1] / 'backend' / 'config.py'
        spec = importlib.util.spec_from_file_location('network_config_test', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_default_direct_ignores_inherited_proxy_without_socket(self):
        for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY'):
            os.environ[key] = 'stale-proxy'
            os.environ[key.lower()] = 'stale-proxy'
        config = self.config()
        with patch.object(config.socket, 'create_connection') as connect:
            config.proxy_ready()
        connect.assert_not_called()
        self.assertEqual(config.NETWORK_MODE, 'direct')
        self.assertEqual(config.network_proxies(), {'http': '', 'https': ''})
        for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY'):
            self.assertEqual(os.environ[key], '')
            self.assertEqual(os.environ[key.lower()], '')
        self.assertEqual(os.environ['NO_PROXY'], '*')
        self.assertEqual(os.environ['no_proxy'], '*')

    def test_explicit_direct_skips_socket(self):
        config = self.config('direct')
        with patch.object(config.socket, 'create_connection') as connect:
            config.proxy_ready()
        connect.assert_not_called()
        self.assertEqual(config.network_proxies(), {'http': '', 'https': ''})

    def test_proxy_unavailable_stops_without_direct_fallback(self):
        config = self.config('proxy')
        with patch.object(config.socket, 'create_connection', side_effect=OSError) as connect:
            with self.assertRaises(config.ProxyUnavailable):
                config.proxy_ready()
        connect.assert_called_once_with(('127.0.0.1', 7897), timeout=0.8)
        self.assertEqual(config.network_proxies(), config.PROXIES)
        for key, value in (
            ('HTTP_PROXY', 'http://127.0.0.1:7897'),
            ('HTTPS_PROXY', 'http://127.0.0.1:7897'),
            ('ALL_PROXY', 'socks5://127.0.0.1:7898'),
            ('NO_PROXY', 'localhost,127.0.0.1,::1'),
        ):
            self.assertEqual(os.environ[key], value)
            self.assertEqual(os.environ[key.lower()], value)

    def test_invalid_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            self.config('invalid')


if __name__ == '__main__':
    unittest.main()
