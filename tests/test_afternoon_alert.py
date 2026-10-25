import unittest
from datetime import datetime, timedelta, timezone
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from notifikasi_telegram import (
    WIB, cek_dan_kirim_jadwal_1530, fresh_afternoon_rows,
    kirim_rekomendasi_rumus_2_dan_9,
)


class AfternoonAlertTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 10, 26, 15, 31, tzinfo=WIB)
        self.rows = pd.DataFrame({
            "Ticker": [f"T{i:03d}" for i in range(25)],
            "Terakhir Update": ["2026-10-26 15:12:00"] * 25,
            "Tanggal Data Harga": ["2026-10-26"] * 25,
        })

    def test_only_current_afternoon_bars_are_eligible(self) -> None:
        self.assertEqual(len(fresh_afternoon_rows(self.rows, self.now)), 25)
        stale = self.rows.copy()
        stale.loc[0, "Tanggal Data Harga"] = "2026-10-23"
        stale.loc[1, "Terakhir Update"] = "2026-10-26 14:59:00"
        self.assertEqual(len(fresh_afternoon_rows(stale, self.now)), 23)

    def test_expired_refresh_is_rejected(self) -> None:
        later = self.now + timedelta(minutes=30)
        self.assertTrue(fresh_afternoon_rows(self.rows, later).empty)

    def test_stale_data_never_reaches_telegram(self) -> None:
        stale = self.rows.assign(**{"Tanggal Data Harga": "2026-10-23"})
        with TemporaryDirectory() as directory, \
             patch("notifikasi_telegram.FILE_LAST_SENT_1530", f"{directory}/sent.json"), \
             patch("notifikasi_telegram.is_telegram_configured", return_value=True), \
             patch("notifikasi_telegram.kirim_pesan_telegram") as send:
            success, detail = kirim_rekomendasi_rumus_2_dan_9(
                stale, require_fresh=True, now=self.now,
            )
            self.assertFalse(success)
            self.assertIn("dibatalkan", detail)
            send.assert_not_called()

    def test_utc_schedule_is_interpreted_as_wib(self) -> None:
        utc_now = self.now.astimezone(timezone.utc)
        with patch("notifikasi_telegram.kirim_rekomendasi_rumus_2_dan_9", return_value=(True, "ok")) as send:
            self.assertEqual(cek_dan_kirim_jadwal_1530(now=utc_now), (True, "ok"))
            self.assertEqual(send.call_args.kwargs["now"].hour, 15)
            self.assertTrue(send.call_args.kwargs["require_fresh"])


if __name__ == "__main__":
    unittest.main()
