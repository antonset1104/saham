"""Persist selected application data through the Container's private D1 handler."""

from __future__ import annotations

from contextlib import closing
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Any
from urllib.parse import quote
import uuid
import zlib

import requests


LOG = logging.getLogger(__name__)
BASE_URL = "http://state.internal"
CHUNK_SIZE = 512 * 1024
MAX_FILE_SIZE = 64 * 1024 * 1024
ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = ("config_web.json", "preset_kustom.json")
DATA_DIRS = ("Database", "Arsip_Data_Harian")
IGNORED_NAMES = {"scheduler_status.json", "telegram_1000_sent.json", "telegram_1530_sent.json", "last_sent_jumat_2000.json"}


def eligible(relative: str) -> bool:
    parts = Path(relative).parts
    if relative in ROOT_FILES:
        return True
    return (len(parts) == 2 and parts[0] in DATA_DIRS and
            parts[1] not in IGNORED_NAMES and
            Path(relative).suffix.lower() in {".csv", ".json", ".sqlite3"})


def data_files() -> list[Path]:
    files = [ROOT / item for item in ROOT_FILES if (ROOT / item).is_file()]
    for dirname in DATA_DIRS:
        directory = ROOT / dirname
        if directory.exists():
            files.extend(path for path in directory.iterdir() if path.is_file() and
                         eligible(path.relative_to(ROOT).as_posix()))
    return files


class StateClient:
    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()
        self.synced: dict[str, str] = {}

    def _request(self, method: str, route: str, **kwargs: Any) -> requests.Response:
        response = self.session.request(method, BASE_URL + route, timeout=45, **kwargs)
        response.raise_for_status()
        return response

    def manifest(self) -> list[dict[str, Any]]:
        records = self._request("GET", "/manifest").json()
        if not isinstance(records, list):
            raise ValueError("Invalid D1 state manifest")
        return records

    def hydrate(self) -> int:
        restored = 0
        for item in self.manifest():
            relative = item["path"]
            if not eligible(relative):
                LOG.warning("Ignoring unexpected state path: %s", relative)
                continue
            compressed = io.BytesIO()
            for index in range(int(item["chunk_count"])):
                route = f"/chunk?path={quote(relative)}&index={index}"
                compressed.write(self._request("GET", route).content)
            raw = zlib.decompress(compressed.getvalue())
            digest = hashlib.sha256(raw).hexdigest()
            if len(raw) != int(item["byte_size"]) or digest != item["sha256"]:
                raise ValueError(f"State integrity check failed: {relative}")
            target = ROOT / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as temp:
                temp.write(raw)
                temporary = Path(temp.name)
            try:
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
            self.synced[relative] = digest
            restored += 1
        return restored

    def _read_stable(self, path: Path) -> bytes:
        if path.suffix != ".sqlite3":
            return path.read_bytes()
        with tempfile.TemporaryDirectory() as dirname:
            snapshot = Path(dirname) / "snapshot.sqlite3"
            with closing(sqlite3.connect(path)) as source, closing(sqlite3.connect(snapshot)) as dest:
                source.backup(dest)
            return snapshot.read_bytes()

    def sync(self) -> int:
        updated = 0
        for path in data_files():
            relative = path.relative_to(ROOT).as_posix()
            if path.stat().st_size > MAX_FILE_SIZE:
                LOG.warning("Skipping oversized state file: %s", relative)
                continue
            try:
                raw = self._read_stable(path)
                if not raw:
                    continue
                digest = hashlib.sha256(raw).hexdigest()
                if self.synced.get(relative) == digest:
                    continue
                compressed = zlib.compress(raw, level=6)
                version = str(uuid.uuid4())
                chunks = [compressed[i:i + CHUNK_SIZE]
                          for i in range(0, len(compressed), CHUNK_SIZE)]
                for index, chunk in enumerate(chunks):
                    route = f"/chunk?path={quote(relative)}&version={version}&index={index}"
                    self._request("PUT", route, data=chunk)
                self._request("POST", f"/commit?path={quote(relative)}", json={
                    "version": version, "byte_size": len(raw), "sha256": digest,
                    "chunk_count": len(chunks),
                })
                self.synced[relative] = digest
                updated += 1
            except (OSError, sqlite3.Error, requests.RequestException, ValueError):
                LOG.exception("Could not persist %s; will retry", relative)
        return updated


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("hydrate", "sync"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    client = StateClient()
    count = client.hydrate() if args.action == "hydrate" else client.sync()
    print(json.dumps({"files": count}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
