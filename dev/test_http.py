"""Run the browser regressions over an isolated loopback HTTP server."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
from threading import Thread

ROOT = Path(__file__).resolve().parents[1]


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


if __name__ == '__main__':
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(ROOT)))
    Thread(target=server.serve_forever, daemon=True).start()
    environment = os.environ.copy()
    environment['AUDIT_URL'] = f'http://127.0.0.1:{server.server_port}/index.html'
    environment['AUDIT_RESULT'] = 'regression-http-results.json'
    try:
        result = subprocess.run(['node', 'dev/test_audit.js'], cwd=ROOT, env=environment)
    finally:
        server.shutdown()
        server.server_close()
    raise SystemExit(result.returncode)
