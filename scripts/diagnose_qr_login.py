"""Generate an anonymous QR in an isolated database; never scan or save a user's Cookie."""
import os
import sys
import tempfile
import time
from pathlib import Path
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
test_root = root / 'local_data'
test_root.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='qr-check-', dir=test_root) as folder:
    os.environ['XHS_DATA_DIR'] = folder
    from backend.config import NETWORK_MODE
    from backend.db import initialize, engine
    from backend.qr_login import QRLoginManager
    initialize()
    manager = QRLoginManager()
    sid = None
    outcome = 1
    try:
        print(f'Network mode: {NETWORK_MODE}. Only checking QR creation; no existing Cookie is read.', flush=True)
        result = manager.start('local-diagnostics')
        sid = result['id']
        previous = None
        deadline = time.monotonic() + 125
        while time.monotonic() < deadline:
            result = manager.get(sid, 'local-diagnostics')
            current = (result['state'], result['stage'], result['request'], result['message'])
            if current != previous:
                print(f"[{result['elapsed_seconds']}s] {result['state']} | {result['stage_label']} | {result['message']}", flush=True)
                if result['request']:
                    print(f"  {result['request']}", flush=True)
                previous = current
            if result['state'] == 'waiting' and result['image']:
                print('QR creation succeeded. Cancelled without scanning or changing login configuration.', flush=True)
                outcome = 0
                break
            if result['state'] in ('failed', 'expired', 'cancelled'):
                break
            time.sleep(0.5)
    finally:
        manager.cancel_all()
        if sid and manager.sessions[sid].thread:
            manager.sessions[sid].thread.join(timeout=2)
        engine.dispose()
sys.exit(outcome)
