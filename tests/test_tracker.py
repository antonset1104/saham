import os
import unittest
import pandas as pd
import numpy as np
from datetime import datetime

import tracker_ai
import scheduler_per_jam

class TestTrackerAIAndScheduler(unittest.TestCase):

    def test_filter_saham_9_rumus(self):
        """Memastikan filter 9 rumus berjalan pada DataFrame valid dan kosong tanpa crash"""
        # Test DataFrame kosong
        df_empty = pd.DataFrame()
        hasil_kosong = tracker_ai.filter_saham_9_rumus(df_empty)
        self.assertEqual(len(hasil_kosong), 9)
        self.assertTrue(all(df.empty for df in hasil_kosong.values()))

        # Test DataFrame terisi
        df_dummy = pd.DataFrame({
            "Ticker": ["BBCA", "BBRI", "BRIS"],
            "Status BB": ["Squeeze", "Squeeze", "Normal"],
            "Kondisi Supply": ["Supply Kering", "Normal", "Normal"],
            "Posisi VWAP": ["Di Atas VWAP (Kuat)", "Di Bawah VWAP", "Di Atas VWAP (Kuat)"],
            "Prediksi Machine Learning": ["Biasa", "🔥 ANOMALI BANDAR", "Biasa"],
            "OBV Trend": ["Netral", "Akumulasi (Naik)", "Netral"],
            "Total Score": [8, 9, 6]
        })
        hasil = tracker_ai.filter_saham_9_rumus(df_dummy)
        self.assertEqual(len(hasil), 9)
        # BBCA harus masuk Rumus 1 (Squeeze + Supply Kering + Di Atas VWAP)
        self.assertIn("BBCA", hasil["R1"]["Ticker"].values)
        # BBRI harus masuk Rumus 2 (Squeeze + Anomali ML + OBV Akumulasi)
        self.assertIn("BBRI", hasil["R2"]["Ticker"].values)

    def test_catat_dan_evaluasi_rekomendasi(self):
        """Memastikan pencatatan rekomendasi dan kalkulasi evaluasi T+1 tepat"""
        df_dummy = pd.DataFrame({
            "Ticker": ["ACES"],
            "Harga (Rp)": [800],
            "Status BB": ["Squeeze"],
            "Kondisi Supply": ["Supply Kering"],
            "Posisi VWAP": ["Di Atas VWAP (Kuat)"],
            "Total Score": [8]
        })
        
        tgl_test = "2026-08-01"
        dt_test = datetime.strptime(f"{tgl_test} 15:00", "%Y-%m-%d %H:%M")
        tracker_ai.catat_rekomendasi_per_jam(df_dummy, timestamp=dt_test)
        
        data = tracker_ai.load_tracker_data()
        item_test = next((x for x in data if x.get("id") == f"{tgl_test}_15:00_R1_ACES"), None)
        self.assertIsNotNone(item_test)
        self.assertEqual(item_test["harga_entry"], 800)
        
        # Simulasi harga T+1 hari berikutnya (High 824 = +3.0%)
        df_t1 = pd.DataFrame([{"Ticker": "ACES", "Open": 808, "High": 824, "Low": 800, "Harga (Rp)": 816}])
        tracker_ai.evaluasi_akurasi_rekomendasi(df_t1)
        
        data_after = tracker_ai.load_tracker_data()
        item_eval = next((x for x in data_after if x.get("id") == f"{tgl_test}_15:00_R1_ACES"), None)
        self.assertIsNotNone(item_eval)
        self.assertEqual(item_eval["max_gain_pct"], 3.0)
        self.assertEqual(item_eval["status_akurasi"], "🎯 AKURAT (HIT TP)")

    def test_hitung_ringkasan_statistik(self):
        """Memastikan kalkulasi win rate dan rata-rata return akurat"""
        stats = tracker_ai.hitung_ringkasan_statistik()
        self.assertIn("win_rate_total", stats)
        self.assertIn("avg_max_gain", stats)
        self.assertIn("rumus_terbaik", stats)
        self.assertIn("stat_per_rumus", stats)
        self.assertGreaterEqual(stats["win_rate_total"], 0.0)
        self.assertLessEqual(stats["win_rate_total"], 100.0)

    def test_scheduler_market_hours(self):
        """Memastikan fungsi jam bursa bekerja sesuai aturan jam kerja IDX"""
        # Hari Sabtu (weekend) harus False
        sat = datetime(2026, 9, 5, 10, 0)
        self.assertFalse(scheduler_per_jam.is_market_hours(sat))

        # Hari Senin jam 10:00 pagi (Sesi 1) harus True
        mon_open = datetime(2026, 9, 7, 10, 0)
        self.assertTrue(scheduler_per_jam.is_market_hours(mon_open))

        # Hari Senin jam 12:30 siang (Istirahat sesi) harus False
        mon_rest = datetime(2026, 9, 7, 12, 30)
        self.assertFalse(scheduler_per_jam.is_market_hours(mon_rest))

        # Hari Senin jam 14:30 sore (Sesi 2) harus True
        mon_sesi2 = datetime(2026, 9, 7, 14, 30)
        self.assertTrue(scheduler_per_jam.is_market_hours(mon_sesi2))

    def test_jadwal_1530_logic(self):
        """Memastikan logika pengecekan jadwal 15:30 WIB bekerja tepat sesuai waktu bursa"""
        from notifikasi_telegram import cek_dan_kirim_jadwal_1530
        
        # Weekend harus False
        sat = datetime(2026, 9, 5, 15, 35)
        sukses, msg = cek_dan_kirim_jadwal_1530(now=sat)
        self.assertFalse(sukses)
        self.assertIn("Weekend", msg)

        # Hari kerja jam 10:00 (belum 15:30) harus False
        mon_pagi = datetime(2026, 9, 7, 10, 0)
        sukses, msg = cek_dan_kirim_jadwal_1530(now=mon_pagi)
        self.assertFalse(sukses)
        self.assertIn("Belum", msg)

    def test_jadwal_1000_logic(self):
        """Memastikan logika pengecekan jadwal 10:00 WIB bekerja tepat sesuai waktu bursa pagi"""
        from notifikasi_telegram import cek_dan_kirim_jadwal_1000
        
        # Weekend harus False
        sun = datetime(2026, 9, 6, 10, 5)
        sukses, msg = cek_dan_kirim_jadwal_1000(now=sun)
        self.assertFalse(sukses)
        self.assertIn("Weekend", msg)

        # Jam 08:30 (belum jam 10:00) harus False
        mon_awal = datetime(2026, 9, 7, 8, 30)
        sukses, msg = cek_dan_kirim_jadwal_1000(now=mon_awal)
        self.assertFalse(sukses)
        self.assertIn("Belum", msg)

        # Jam 14:00 (lewat jam 10:00) harus False
        mon_siang = datetime(2026, 9, 7, 14, 0)
        sukses, msg = cek_dan_kirim_jadwal_1000(now=mon_siang)
        self.assertFalse(sukses)
        self.assertIn("Belum", msg)

if __name__ == "__main__":
    unittest.main()
