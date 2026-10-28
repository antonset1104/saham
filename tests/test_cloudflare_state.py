from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
from typing import Any
from urllib.parse import parse_qs, urlparse

import cloudflare.state_client as state_module


class FakeResponse:
    def __init__(self, payload: Any = None, content: bytes = b"") -> None:
        self.payload = payload
        self.content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self.payload


class FakeSession:
    def __init__(self) -> None:
        self.files: dict[str, dict[str, Any]] = {}
        self.chunks: dict[tuple[str, str, int], bytes] = {}

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        if parsed.path == "/manifest":
            return FakeResponse(list(self.files.values()))
        path = query["path"][0]
        index = int(query["index"][0]) if "index" in query else 0
        if method == "PUT":
            self.chunks[path, query["version"][0], index] = kwargs["data"]
            return FakeResponse()
        if method == "POST":
            data = kwargs["json"]
            self.files[path] = {"path": path, **data}
            return FakeResponse()
        version = self.files[path]["version"]
        return FakeResponse(content=self.chunks[path, version, index])


def test_cloudflare_state_roundtrip_and_sqlite_snapshot(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(state_module, "ROOT", tmp_path)
    database = tmp_path / "Database"
    database.mkdir()
    (database / "hasil_screener.csv").write_text("ticker,price\nBBCA,8000\n", encoding="utf-8")
    sqlite_path = database / "market_history.sqlite3"
    with closing(sqlite3.connect(sqlite_path)) as connection:
        connection.execute("CREATE TABLE prices(ticker TEXT, price INTEGER)")
        connection.execute("INSERT INTO prices VALUES('BBCA',8000)")
        connection.commit()

    session = FakeSession()
    writer = state_module.StateClient(session)  # type: ignore[arg-type]
    assert writer.sync() == 2
    assert writer.sync() == 0
    assert set(session.files) == {"Database/hasil_screener.csv", "Database/market_history.sqlite3"}

    (database / "hasil_screener.csv").unlink()
    sqlite_path.unlink()
    reader = state_module.StateClient(session)  # type: ignore[arg-type]
    assert reader.hydrate() == 2
    assert (database / "hasil_screener.csv").read_text(encoding="utf-8").endswith("BBCA,8000\n")
    with closing(sqlite3.connect(sqlite_path)) as connection:
        assert connection.execute("SELECT price FROM prices").fetchone()[0] == 8000


def test_cloudflare_state_excludes_credentials(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(state_module, "ROOT", tmp_path)
    database = tmp_path / "Database"
    database.mkdir()
    (tmp_path / ".env").write_text("STOCKBIT_TOKEN=secret", encoding="utf-8")
    (database / "notes.txt").write_text("private", encoding="utf-8")
    assert state_module.data_files() == []
    assert not state_module.eligible("Database/../.env")


def test_afternoon_delivery_marker_is_persistent(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(state_module, "ROOT", tmp_path)
    database = tmp_path / "Database"
    database.mkdir()
    marker = database / "telegram_1530_sent.json"
    marker.write_text('{"last_sent_date":"2026-10-26"}', encoding="utf-8")
    assert state_module.data_files() == [marker]


def test_morning_delivery_marker_is_persistent(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(state_module, "ROOT", tmp_path)
    database = tmp_path / "Database"
    database.mkdir()
    marker = database / "telegram_1000_sent.json"
    marker.write_text('{"last_sent_date":"2026-10-28"}', encoding="utf-8")
    assert state_module.data_files() == [marker]
