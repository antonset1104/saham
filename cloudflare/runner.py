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
sys.path.insert(0, str(ROOT))
from notifikasi_telegram import MIN_AFTERNOON_ROWS, cek_dan_kirim_jadwal_1530, fresh_afternoon_rows, now_wib


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
        if self.path not in {"/run/eod", "/run/afternoon/refresh", "/run/afternoon/alert"}:
            self.send_error(404)
            return
        if not JOB_LOCK.acquire(blocking=False):
            self.send_error(409, "job already running")
            return
        try:
            if self.path == "/run/afternoon/alert":
                success, detail = cek_dan_kirim_jadwal_1530()
                if not success and "sudah pernah terkirim" not in detail:
                    LOG.warning("Afternoon alert skipped: %s", detail)
                    self.send_error(503, detail)
                    return
                if success:
                    CLIENT.sync()
                LOG.info("Afternoon alert: %s", detail)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")
                return

            if self.path == "/run/afternoon/refresh":
                import pandas as pd
                result_file = ROOT / "Database" / "hasil_screener.csv"
                if result_file.is_file():
                    existing = pd.read_csv(result_file)
                    existing_count = len(fresh_afternoon_rows(existing, now_wib()))
                    if existing_count >= max(MIN_AFTERNOON_ROWS, int(len(existing) * 0.7)):
                        LOG.info("Afternoon refresh already current: %d rows", existing_count)
                        self.send_response(200)
                        self.end_headers()
                        self.wfile.write(b"already current")
                        return
                result = subprocess.run(
                    [sys.executable, "update_data.py"],
                    cwd=ROOT, timeout=720, check=False, capture_output=True, text=True,
                )
                if result.returncode != 0:
                    LOG.error("Afternoon refresh failed: %s", result.stderr[-1000:])
                    self.send_error(500, "Afternoon refresh failed")
                    return
                screener = pd.read_csv(result_file)
                fresh_count = len(fresh_afternoon_rows(screener, now_wib()))
                if fresh_count < max(MIN_AFTERNOON_ROWS, int(len(screener) * 0.7)):
                    LOG.warning("Afternoon refresh has only %d current rows", fresh_count)
                    self.send_error(503, "Fresh price data unavailable")
                    return
                CLIENT.sync()
                LOG.info("Afternoon refresh completed: %d current rows", fresh_count)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")
                return

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
        except Exception:
            LOG.exception("Scheduled execution failed: %s", self.path)
            self.send_error(500, "Scheduled execution failed")
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
