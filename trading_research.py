"""Causal cross-sectional signals and non-overlapping walk-forward paper backtest."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from mesin_forecast import BUY_FEE, FEATURE_COLUMNS, SELL_FEE, build_forecast_features


MODEL_VERSION = "pooled-next-open-v3"
HORIZONS = (1, 5)
SLIPPAGE_PER_SIDE = 0.001
MIN_MEDIAN_TURNOVER = 1_000_000_000
MIN_PRICE = 100
MIN_TICKERS = 5
MIN_TRAIN_ROWS = 250
MIN_TRAIN_DATES = 120
MIN_BACKTEST_DATES = 300
PROBABILITY_THRESHOLD = 0.55
TOP_K = 3
RETRAIN_EVERY = 20
FEATURES = FEATURE_COLUMNS + ["market_ret_5", "relative_ret_5", "log_turnover"]
JAKARTA = ZoneInfo("Asia/Jakarta")


def signal_is_actionable(asof: str, now: datetime | None = None) -> bool:
    """A close signal expires when the next regular session opens at 09:00 WIB."""
    current = now or datetime.now(JAKARTA)
    current = current.astimezone(JAKARTA) if current.tzinfo else current.replace(tzinfo=JAKARTA)
    origin = datetime.fromisoformat(asof).date()
    if origin > current.date() or (current.date() - origin).days > 4:
        return False
    if origin == current.date():
        return current.time() >= time(17, 30)
    next_weekday = origin + timedelta(days=1)
    while next_weekday.weekday() >= 5:
        next_weekday += timedelta(days=1)
    return current.date() == next_weekday and current.time() < time(9, 0)


@dataclass(frozen=True)
class BacktestMetrics:
    total_return_pct: float
    benchmark_return_pct: float
    matched_benchmark_return_pct: float
    max_drawdown_pct: float
    trade_cohorts: int
    tested_cohorts: int
    winning_cohorts: int
    brier: float
    prior_brier: float
    scored_rows: int


def net_trade_return(entry_open: pd.Series, exit_close: pd.Series) -> pd.Series:
    """Costs are applied on actual next-open purchase and later close sale."""
    return (exit_close * (1 - SELL_FEE - SLIPPAGE_PER_SIDE)
            / (entry_open * (1 + BUY_FEE + SLIPPAGE_PER_SIDE)) - 1)


def build_research_panel(bars: pd.DataFrame, horizon: int) -> pd.DataFrame:
    if horizon not in HORIZONS:
        raise ValueError("Horizon riset harus 1 atau 5 hari bursa.")
    required = {"ticker", "trade_date", "open", "high", "low", "close", "volume"}
    if not required.issubset(bars.columns):
        raise ValueError(f"Kolom OHLCV kurang: {sorted(required - set(bars.columns))}")
    clean = bars.copy()
    clean["trade_date"] = pd.to_datetime(clean["trade_date"])
    clean = clean.drop_duplicates(["ticker", "trade_date"], keep="first")
    clean = clean.sort_values(["ticker", "trade_date"])
    dates = pd.DatetimeIndex(sorted(clean["trade_date"].unique()))
    if len(dates) < MIN_BACKTEST_DATES:
        raise ValueError(f"Butuh minimal {MIN_BACKTEST_DATES} tanggal pasar historis.")
    if clean["ticker"].nunique() < MIN_TICKERS:
        raise ValueError(f"Butuh minimal {MIN_TICKERS} ticker untuk model lintas saham.")

    market_close = clean.pivot(index="trade_date", columns="ticker", values="close").reindex(dates)
    market_ret_5 = market_close.pct_change(5, fill_method=None).median(axis=1, skipna=True)
    frames: list[pd.DataFrame] = []
    for ticker, group in clean.groupby("ticker", sort=True):
        frame = group.set_index("trade_date").reindex(dates)
        price = pd.DataFrame({
            "Open": frame["open"], "High": frame["high"], "Low": frame["low"],
            "Close": frame["close"], "Volume": frame["volume"],
        })
        features = build_forecast_features(price)[FEATURE_COLUMNS].copy()
        features["market_ret_5"] = market_ret_5
        features["relative_ret_5"] = features["ret_5"] - market_ret_5
        turnover = price["Close"] * price["Volume"]
        features["log_turnover"] = np.log1p(turnover.rolling(20, min_periods=20).median())
        liquid = (turnover.rolling(20, min_periods=20).median() >= MIN_MEDIAN_TURNOVER)
        valid = (price["Close"] >= MIN_PRICE) & (price["Volume"] > 0) & liquid
        features["ticker"] = ticker
        features["trade_date"] = dates
        features["close"] = price["Close"].to_numpy()
        features["entry_open"] = price["Open"].shift(-1).to_numpy()
        features["exit_close"] = price["Close"].shift(-horizon).to_numpy()
        features["exit_date"] = pd.Series(dates, index=dates).shift(-horizon).to_numpy()
        features["momentum_5"] = features["ret_5"]
        features = features.loc[valid]
        frames.append(features)
    panel = pd.concat(frames, ignore_index=True)
    panel = panel.replace([np.inf, -np.inf], np.nan).dropna(subset=FEATURES + ["close"])
    panel["net_return"] = net_trade_return(panel["entry_open"], panel["exit_close"])
    panel["positive"] = (panel["net_return"] > 0).astype(int)
    return panel.sort_values(["trade_date", "ticker"]).reset_index(drop=True)


def _fit_model(panel: pd.DataFrame, signal_date: pd.Timestamp) -> tuple[Any, float]:
    matured = panel[
        panel["exit_date"].notna()
        & (panel["exit_date"] <= signal_date)
        & panel["net_return"].notna()
    ]
    if len(matured) < MIN_TRAIN_ROWS or matured["trade_date"].nunique() < MIN_TRAIN_DATES:
        raise ValueError("Data berlabel matang belum cukup untuk melatih model.")
    if matured["positive"].nunique() != 2:
        raise ValueError("Label latih hanya memiliki satu kelas.")
    model = make_pipeline(
        StandardScaler(), LogisticRegression(C=0.1, max_iter=500, solver="lbfgs")
    )
    model.fit(matured[FEATURES].to_numpy(dtype=float), matured["positive"].to_numpy(dtype=int))
    return model, float(matured["positive"].mean())


def walk_forward_scores(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.Timestamp, pd.Timestamp]:
    """Refit from labels known at each signal close, including during holdout."""
    labeled_dates = pd.DatetimeIndex(sorted(panel.loc[panel["net_return"].notna(), "trade_date"].unique()))
    if len(labeled_dates) < MIN_BACKTEST_DATES:
        raise ValueError("Tanggal dengan transaksi lengkap belum cukup untuk backtest.")
    validation_start = labeled_dates[int(len(labeled_dates) * 0.60)]
    test_start = labeled_dates[int(len(labeled_dates) * 0.80)]
    score_dates = pd.DatetimeIndex(sorted(panel.loc[
        (panel["trade_date"] >= validation_start)
        & (panel["trade_date"] <= labeled_dates[-1]), "trade_date"].unique()))
    scored: list[pd.DataFrame] = []
    model: Any = None
    prior = 0.5
    for position, date in enumerate(score_dates):
        if model is None or position % RETRAIN_EVERY == 0:
            model, prior = _fit_model(panel, date)
        day = panel.loc[panel["trade_date"] == date].copy()
        day["probability"] = model.predict_proba(day[FEATURES].to_numpy(dtype=float))[:, 1]
        day["prior_probability"] = prior
        scored.append(day)
    return pd.concat(scored, ignore_index=True), validation_start, test_start


def _selected_return(day: pd.DataFrame, *, model: bool, top_k: int) -> tuple[float, bool]:
    if model:
        selected = day[day["probability"] >= PROBABILITY_THRESHOLD].nlargest(top_k, "probability")
    else:
        selected = day.nlargest(top_k, "momentum_5")
    if selected.empty:
        return 0.0, False
    # A missing next open is unfilled; an unavailable exit is treated as a full loss.
    returns = selected["net_return"].copy()
    returns = returns.where(selected["entry_open"].notna(), 0.0).fillna(-1.0)
    return float(returns.mean()), True


def evaluate_nonoverlap(
    scored: pd.DataFrame, horizon: int, *, top_k: int = TOP_K,
    rebalance_dates: pd.DatetimeIndex | None = None,
) -> BacktestMetrics:
    """Buy next open, exit on horizon close, then rebalance without overlap."""
    if horizon not in HORIZONS or top_k < 1:
        raise ValueError("Horizon atau jumlah kandidat tidak valid.")
    available_dates = pd.DatetimeIndex(sorted(scored["trade_date"].unique()))
    dates = available_dates[::horizon] if rebalance_dates is None else pd.DatetimeIndex(rebalance_dates)
    if len(dates) == 0:
        raise ValueError("Tidak ada tanggal backtest.")
    if not dates.isin(available_dates).all():
        raise ValueError("Tanggal transaksi harus berada di periode backtest.")
    scored_by_date = {date: day for date, day in scored.groupby("trade_date", sort=False)}
    model_returns: list[float] = []
    benchmark_returns: list[float] = []
    matched_benchmark_returns: list[float] = []
    traded = 0
    for date in dates:
        day = scored_by_date[date]
        model_return, did_trade = _selected_return(day, model=True, top_k=top_k)
        benchmark_return, _ = _selected_return(day, model=False, top_k=top_k)
        # Keep the momentum comparison on the model's dates and position count.
        model_positions = min(top_k, int((day["probability"] >= PROBABILITY_THRESHOLD).sum()))
        matched_return = (
            _selected_return(day, model=False, top_k=model_positions)[0]
            if model_positions else 0.0
        )
        model_returns.append(model_return)
        benchmark_returns.append(benchmark_return)
        matched_benchmark_returns.append(matched_return)
        traded += int(did_trade)
    equity = np.cumprod(1 + np.asarray(model_returns))
    high_water = np.maximum.accumulate(np.r_[1.0, equity])[1:]
    labeled = scored[scored["net_return"].notna()]
    if labeled.empty:
        raise ValueError("Hasil transaksi belum tersedia untuk skor kalibrasi.")
    actual = labeled["positive"].to_numpy(dtype=int)
    return BacktestMetrics(
        total_return_pct=round(float((equity[-1] - 1) * 100), 2),
        benchmark_return_pct=round(float((np.prod(1 + np.asarray(benchmark_returns)) - 1) * 100), 2),
        matched_benchmark_return_pct=round(
            float((np.prod(1 + np.asarray(matched_benchmark_returns)) - 1) * 100), 2
        ),
        max_drawdown_pct=round(float(np.min(equity / high_water - 1) * 100), 2),
        trade_cohorts=traded,
        tested_cohorts=len(model_returns),
        winning_cohorts=sum(value > 0 for value in model_returns),
        brier=round(float(brier_score_loss(actual, labeled["probability"])), 4),
        prior_brier=round(float(brier_score_loss(actual, labeled["prior_probability"])), 4),
        scored_rows=len(labeled),
    )


def split_rebalance_dates(
    scored: pd.DataFrame, horizon: int, test_start: pd.Timestamp,
) -> tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
    """Preserve one non-overlapping phase and purge trades crossing the holdout boundary."""
    dates = pd.DatetimeIndex(sorted(scored["trade_date"].unique()))
    positions = np.arange(0, len(dates), horizon)
    validation = [dates[position] for position in positions
                  if dates[position] < test_start
                  and position + horizon < len(dates)
                  and dates[position + horizon] < test_start]
    holdout = [dates[position] for position in positions if dates[position] >= test_start]
    if not validation or not holdout:
        raise ValueError("Cohort validasi atau holdout terlalu sedikit setelah purge horizon.")
    return pd.DatetimeIndex(validation), pd.DatetimeIndex(holdout)


def research_signals(bars: pd.DataFrame, horizon: int) -> dict[str, Any]:
    panel = build_research_panel(bars, horizon)
    scored, validation_start, test_start = walk_forward_scores(panel)
    validation_dates, holdout_dates = split_rebalance_dates(scored, horizon, test_start)
    validation = evaluate_nonoverlap(
        scored[scored["trade_date"] < test_start], horizon, rebalance_dates=validation_dates
    )
    holdout = evaluate_nonoverlap(
        scored[scored["trade_date"] >= test_start], horizon, rebalance_dates=holdout_dates
    )
    # A single favorable total return is insufficient; require two independent periods.
    def passes(metrics: BacktestMetrics) -> bool:
        return (
            metrics.trade_cohorts >= 10
            and metrics.total_return_pct > max(0.0, metrics.matched_benchmark_return_pct + 1.0)
            and metrics.brier < metrics.prior_brier
        )

    approved = passes(validation) and passes(holdout)
    latest_date = panel["trade_date"].max()
    latest = panel[panel["trade_date"] == latest_date].copy()
    if len(latest) < MIN_TICKERS:
        raise ValueError("Terlalu sedikit saham likuid dengan candle pada tanggal terbaru.")
    final_model, _ = _fit_model(panel, latest_date)
    latest["probability"] = final_model.predict_proba(latest[FEATURES].to_numpy(dtype=float))[:, 1]
    ranking = latest.nlargest(10, "probability")
    candidates = [
        {"ticker": row.ticker, "probability_pct": round(float(row.probability * 100), 1),
         "last_close": round(float(row.close), 2), "momentum_5_pct": round(float(row.momentum_5 * 100), 2)}
        for row in ranking.itertuples(index=False)
    ]
    eligible_tickers = set(ranking.head(TOP_K).loc[
        ranking.head(TOP_K)["probability"] >= PROBABILITY_THRESHOLD, "ticker"
    ])
    signals = [candidate for candidate in candidates if candidate["ticker"] in eligible_tickers] if approved else []
    return {
        "status": "ready" if signals else "no_edge",
        "approved": approved,
        "version": MODEL_VERSION,
        "horizon": horizon,
        "data_asof": latest_date.date().isoformat(),
        "validation_from": validation_start.date().isoformat(),
        "holdout_from": test_start.date().isoformat(),
        "symbols_with_latest_bar": len(latest),
        "validation": asdict(validation),
        "holdout": asdict(holdout),
        "signals": signals,
        "research_ranking": candidates,
        "assumptions": {
            "buy_fee_pct": BUY_FEE * 100,
            "sell_fee_pct": SELL_FEE * 100,
            "slippage_each_side_pct": SLIPPAGE_PER_SIDE * 100,
            "minimum_median_turnover_idr": MIN_MEDIAN_TURNOVER,
            "probability_threshold_pct": PROBABILITY_THRESHOLD * 100,
            "top_k": TOP_K,
        },
    }
