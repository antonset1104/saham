import os
import unittest
import pandas as pd
import numpy as np

from update_akuisisi import analyze_acquisition_status
from bot_simulator import cek_saldo_tersedia, MODAL_AWAL, FEE_BELI, FEE_JUAL
from analysis_signal import calculate_signal_score
from data_multi_aset import TROY_OZ_TO_GRAM, get_gold_price_idr
from mesin_forecast import build_forecast_features
from notifikasi_telegram import is_telegram_configured

class TestScreenerAndBot(unittest.TestCase):

    def test_acquisition_analysis(self):
        """Memastikan logika deteksi sentimen berita akurat"""
        kata_rencana = ["rencana akuisisi", "jajaki merger"]
        kata_dalam = ["resmi akuisisi", "tuntas pengambilalihan"]

        # Kasus 1: Berita kosong
        self.assertEqual(analyze_acquisition_status("Tidak ada berita terbaru.", kata_rencana, kata_dalam), "TIDAK ADA")

        # Kasus 2: Rencana
        berita_rencana = "Emiten XYZ susun rencana akuisisi entitas baru tahun ini"
        self.assertEqual(analyze_acquisition_status(berita_rencana, kata_rencana, kata_dalam), "RENCANA AKUISISI")

        # Kasus 3: Selesai / Dalam Akuisisi (Prioritas Utama)
        berita_resmi = "Perusahaan resmi akuisisi 80% saham produsen farmasi"
        self.assertEqual(analyze_acquisition_status(berita_resmi, kata_rencana, kata_dalam), "DALAM AKUISISI")

    def test_bot_saldo_calculation(self):
        """Memastikan perhitungan saldo kas dan alokasi modal tepat dengan compounding dan mitigasi loss"""
        df_kosong = pd.DataFrame(columns=['Total_Modal'])
        self.assertEqual(cek_saldo_tersedia(df_kosong), MODAL_AWAL)

        df_terisi = pd.DataFrame([
            {'Total_Modal': 20_000_000},
            {'Total_Modal': 15_000_000}
        ])
        expected_saldo = MODAL_AWAL - 35_000_000
        self.assertEqual(cek_saldo_tersedia(df_terisi), expected_saldo)

        # Skenario Compounding Profit
        df_hist_profit = pd.DataFrame([
            {'Total_Return_Rp': 5_000_000},
            {'Total_Return_Rp': 3_000_000}
        ])
        expected_compounded = MODAL_AWAL + 8_000_000 - 35_000_000
        self.assertEqual(cek_saldo_tersedia(df_terisi, df_hist_profit), expected_compounded)

        # Skenario Realized Loss
        df_hist_loss = pd.DataFrame([
            {'Total_Return_Rp': -10_000_000}
        ])
        expected_reduced = MODAL_AWAL - 10_000_000 - 35_000_000
        self.assertEqual(cek_saldo_tersedia(df_terisi, df_hist_loss), expected_reduced)

    def test_fee_trading_calculation(self):
        """Memastikan perhitungan fee beli dan jual akurat"""
        harga_beli = 1000
        lot = 10
        lembar = lot * 100
        nilai_kotor_beli = harga_beli * lembar
        total_beli_plus_fee = nilai_kotor_beli * (1 + FEE_BELI)

        self.assertEqual(total_beli_plus_fee, 1_000_000 * 1.0015)

        harga_jual = 1100
        nilai_kotor_jual = harga_jual * lembar
        nilai_bersih_jual = nilai_kotor_jual - (nilai_kotor_jual * FEE_JUAL)

        self.assertEqual(nilai_bersih_jual, 1_100_000 * (1 - 0.0025))

        profit_rp = nilai_bersih_jual - total_beli_plus_fee
        self.assertGreater(profit_rp, 0)

    def test_konfigurasi_files_exist(self):
        """Memastikan file-file konfigurasi penting tersedia dan tidak kosong"""
        file_saham = "Konfigurasi/saham.txt"
        file_rencana = "Konfigurasi/RENCANA_AKUISISI.txt"
        file_dalam = "Konfigurasi/DALAM_AKUISISI.txt"

        self.assertTrue(os.path.exists(file_saham))
        self.assertTrue(os.path.exists(file_rencana))
        self.assertTrue(os.path.exists(file_dalam))

        with open(file_saham) as f:
            lines = [l.strip() for l in f if l.strip()]
            self.assertGreater(len(lines), 500)

    def test_multi_factor_signal_scoring(self):
        """Memastikan algoritma weighted scoring multi-faktor kuantitatif bekerja akurat"""
        # Skenario 1: DataFrame lengkap
        dates = pd.date_range("2026-01-01", periods=30)
        df_bullish = pd.DataFrame({
            "Close": [1000 + i * 10 for i in range(30)],
            "RSI (14D)": [28.0] * 30, # Oversold kuat
            "MA20": [1200] * 30,
            "MA50": [1100] * 30,      # Uptrend (MA20 > MA50)
            "Posisi VWAP": ["Di Atas VWAP (Kuat)"] * 30,
            "Status BB": ["Squeeze"] * 30,
            "Rasio Vol H-1": [2.0] * 30 # Volume spike
        }, index=dates)

        res = calculate_signal_score(df_bullish)
        self.assertIn("score", res)
        self.assertGreaterEqual(res["score"], 3.0)
        self.assertEqual(res["signal"], "STRONG BUY")
        self.assertTrue(len(res["reasons"]) >= 4)

        # Skenario 2: DataFrame mentah OHLCV + dictionary indikator (alur riil update_data.py)
        df_raw = pd.DataFrame({
            "Open": [1000] * 30,
            "High": [1050] * 30,
            "Low": [950] * 30,
            "Close": [1000] * 30,
            "Volume": [100000] * 30
        }, index=dates)
        ind_dict = {
            "RSI (14D)": 25.0,
            "Harga MA20": 1100,
            "MA50": 1000,
            "Posisi VWAP": "Di Atas VWAP (Kuat)",
            "Status BB": "Squeeze"
        }
        res_pipeline = calculate_signal_score(df_raw, indikator=ind_dict)
        self.assertGreater(res_pipeline["score"], 0.0)
        self.assertIn(res_pipeline["signal"], ["BUY", "STRONG BUY"])

    def test_gold_conversion_math(self):
        """Memastikan konversi harga emas Troy Oz ke Gram IDR presisi"""
        usd_rate = 16000.0
        gold_info = get_gold_price_idr(usd_idr=usd_rate)
        
        # 1 Troy Oz = 31.1034768 gram
        self.assertAlmostEqual(TROY_OZ_TO_GRAM, 31.1034768, places=4)
        expected_per_gram = (gold_info["usd_per_oz"] / TROY_OZ_TO_GRAM) * usd_rate
        self.assertAlmostEqual(gold_info["idr_per_gram"], expected_per_gram, places=1)
        self.assertGreater(gold_info["idr_per_gram"], 1_000_000)

    def test_forecast_feature_builder(self):
        """Memastikan pembentukan fitur regresi ML lengkap dan bebas NaN tak terduga"""
        dates = pd.bdate_range("2025-01-01", periods=60)
        df_dummy = pd.DataFrame({
            "Close": [5000 + (i % 5) * 50 for i in range(60)],
            "High": [5100 + (i % 5) * 50 for i in range(60)],
            "Low": [4900 + (i % 5) * 50 for i in range(60)],
            "Volume": [1000000 + i * 10000 for i in range(60)],
        }, index=dates)

        feat_df = build_forecast_features(df_dummy, lookback=5)
        self.assertIn("lag_1", feat_df.columns)
        self.assertIn("ma_5", feat_df.columns)
        self.assertIn("vol_ratio", feat_df.columns)
        self.assertIn("hl_pct", feat_df.columns)

        # Setelah dropna, harus ada data valid
        valid_rows = feat_df.dropna()
        self.assertGreater(len(valid_rows), 30)

    def test_telegram_config_state(self):
        """Memeriksa deteksi status konfigurasi bot Telegram"""
        # Jika belum diatur di env, fungsi harus return bool tanpa crash
        status = is_telegram_configured()
        self.assertIsInstance(status, bool)

if __name__ == "__main__":
    unittest.main()
