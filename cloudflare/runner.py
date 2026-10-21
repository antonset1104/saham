"""Start Streamlit with private scheduled-job control and durable state sync."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import logging
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

from state_client import ROOT, StateClient


LOG = logging.getLogger(__name__)
CLIENT = StateClient()
JOB_LOCK = threading.Lock()
STOP = threading.Event()


class ControlHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/health":
            self.send_error(404)
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_POST(self) -> None:
        if self.path != "/run/eod":
            self.send_error(404)
            return
        if not JOB_LOCK.acquire(blocking=False):
            self.send_error(409, "job already running")
            return
        try:
            result = subprocess.run(
                [sys.executable, "trading_pipeline.py", "--skip-if-current-eod"],
                cwd=ROOT, timeout=840, check=False, capture_output=True, text=True,
            )
            if result.returncode != 0:
                LOG.error("EOD failed: %s", result.stderr[-1000:])
                self.send_error(500, "EOD failed")
                return
            LOG.info("EOD completed: %s", result.stdout[-1000:])
            CLIENT.sync()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        except (subprocess.TimeoutExpired, OSError):
            LOG.exception("EOD execution failed")
            self.send_error(500, "EOD failed")
        finally:
            JOB_LOCK.release()


def sync_loop() -> None:
    while not STOP.wait(30):
        if JOB_LOCK.locked():
            continue
        try:
            CLIENT.sync()
        except Exception:
            LOG.exception("Periodic state sync failed")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    os.chdir(ROOT)
    restored = CLIENT.hydrate()
    LOG.info("Restored %d state files", restored)
    server = ThreadingHTTPServer(("0.0.0.0", 8503), ControlHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=sync_loop, daemon=True).start()

    child = subprocess.Popen([
        sys.executable, "-m", "streamlit", "run", "app.py",
        "--server.address=0.0.0.0", "--server.port=8501",
        "--server.headless=true", "--server.enableCORS=true",
        "--server.enableXsrfProtection=true", "--browser.gatherUsageStats=false",
    ], cwd=ROOT)

    def stop(_signum: int, _frame: object) -> None:
        STOP.set()
        child.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        return child.wait()
    finally:
        STOP.set()
        server.shutdown()
        try:
            CLIENT.sync()
        except Exception:
            LOG.exception("Final state sync failed")


if __name__ == "__main__":
    raise SystemExit(main())
