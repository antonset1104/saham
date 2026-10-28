from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import global_indices
import notifikasi_telegram as telegram
import pandas as pd
import tracker_ai


def test_morning_report_sends_indices_without_stale_picks_and_deduplicates(
    tmp_path: Path, monkeypatch: Any,
) -> None:
    morning_marker = tmp_path / "telegram_1000_sent.json"
    monkeypatch.setattr(telegram, "FILE_LAST_SENT_1000", str(morning_marker))
    monkeypatch.setattr(telegram, "FILE_LAST_SENT_1530", str(tmp_path / "missing.json"))
    monkeypatch.setattr(telegram, "is_telegram_configured", lambda: True)
    monkeypatch.setattr(tracker_ai, "load_tracker_data", lambda: [])
    monkeypatch.setattr(global_indices, "morning_index_lines", lambda now: ["INDEKS TES"])
    sent: list[str] = []
    monkeypatch.setattr(telegram, "kirim_pesan_telegram", lambda message: sent.append(message) or True)
    current = datetime(2026, 10, 28, 3, 0, tzinfo=timezone.utc)

    success, _ = telegram.cek_dan_kirim_jadwal_1000(now=current)
    assert success
    assert len(sent) == 1
    assert "INDEKS TES" in sent[0]
    assert "Tidak ada daftar BSJP" in sent[0]
    assert json.loads(morning_marker.read_text(encoding="utf-8"))["last_sent_date"] == "2026-10-28"

    success, detail = telegram.cek_dan_kirim_jadwal_1000(now=current.replace(minute=5))
    assert not success
    assert "sudah pernah terkirim" in detail
    assert len(sent) == 1


def test_single_ticker_multiindex_yahoo_quote(monkeypatch: Any) -> None:
    import yfinance as yf

    columns = pd.MultiIndex.from_product(
        [["Close", "High", "Open", "Low"], ["BBCA.JK"]]
    )
    rows = pd.DataFrame(
        [[5025.0, 5100.0, 4920.0, 4900.0]],
        index=pd.to_datetime(["2026-10-28"]), columns=columns,
    )
    monkeypatch.setattr(yf, "download", lambda *args, **kwargs: rows)
    result = telegram._ambil_data_realtime_emiten(["BBCA"], pd.DataFrame())
    assert result["BBCA"]["price"] == 5025.0
    assert result["BBCA"]["date"] == "2026-10-28"
