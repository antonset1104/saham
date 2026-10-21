"""Causal 14:45 WIB overnight signal: enter 15:15, exit next session 09:05."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from market_history_store import JAKARTA
from mesin_forecast import BUY_FEE, SELL_FEE
from trading_research import SLIPPAGE_PER_SIDE


MODEL_VERSION = "overnight-1445-v1"
FEATURES = ["day_return", "recent_return", "range_pct", "close_position", "log_turnover"]
MIN_PRICE = 100
MIN_TURNOVER = 1_000_000_000
MIN_SYMBOLS = 5
MIN_DATES = 40
MIN_TRAIN_DATES = 20
MIN_TRAIN_ROWS = 100
TOP_K = 3
THRESHOLD = 0.55


@dataclass(frozen=True)
class PeriodMetrics:
    total_return_pct: float
    benchmark_return_pct: float
    max_drawdown_pct: float
    trade_days: int
    tested_days: int
    brier: float
    prior_brier: float
    scored_rows: int
    observed_before_signal_days: int


def overnight_net_return(entry: float, exit_price: float) -> float:
    return exit_price * (1 - SELL_FEE - SLIPPAGE_PER_SIDE) / (
        entry * (1 + BUY_FEE + SLIPPAGE_PER_SIDE)
    ) - 1


def build_overnight_panel(bars: pd.DataFrame) -> pd.DataFrame:
    required = {"ticker", "bar_time", "open", "high", "low", "close", "volume", "first_seen_at"}
    if not required.issubset(bars.columns):
        raise ValueError(f"Kolom intraday kurang: {sorted(required - set(bars.columns))}")
    data = bars.copy()
    data["bar_time"] = pd.to_datetime(data["bar_time"], utc=True).dt.tz_convert(JAKARTA)
    data["first_seen_at"] = pd.to_datetime(data["first_seen_at"], utc=True).dt.tz_convert(JAKARTA)
    data["trade_date"] = data["bar_time"].dt.date
    data["clock"] = data["bar_time"].dt.strftime("%H:%M")
    data = data.drop_duplicates(["ticker", "bar_time"]).sort_values(["ticker", "bar_time"])
    dates = sorted(data["trade_date"].unique())
    next_date = dict(zip(dates[:-1], dates[1:]))
    lookup = {
        (ticker, date, clock): row
        for (ticker, date, clock), row in data.groupby(["ticker", "trade_date", "clock"]).first().iterrows()
    }
    rows: list[dict[str, Any]] = []
    for (ticker, date), day in data.groupby(["ticker", "trade_date"], sort=True):
        first_morning = day[(day["clock"] >= "09:00") & (day["clock"] <= "09:30")]
        morning = first_morning.iloc[0] if not first_morning.empty else None
        signal = lookup.get((ticker, date, "14:30"))
        recent = lookup.get((ticker, date, "14:00"))
        if morning is None or signal is None or recent is None:
            continue
        known = day[day["clock"] <= "14:30"]
        if len(known) < 30 or signal.close < MIN_PRICE or signal.volume <= 0:
            continue
        turnover = float((known["close"] * known["volume"]).sum())
        if turnover < MIN_TURNOVER:
            continue
        high, low = float(known["high"].max()), float(known["low"].min())
        trade_day = pd.Timestamp(date)
        signal_deadline = pd.Timestamp(datetime.combine(date, time(15)), tz=JAKARTA)
        entry = lookup.get((ticker, date, "15:15"))
        following = next_date.get(date)
        exit_bar = lookup.get((ticker, following, "09:05")) if following else None
        entry_open = float(entry.open) if entry is not None and entry.volume > 0 else np.nan
        exit_open = float(exit_bar.open) if exit_bar is not None and exit_bar.volume > 0 else np.nan
        net_return = (overnight_net_return(entry_open, exit_open)
                      if np.isfinite(entry_open) and np.isfinite(exit_open) else np.nan)
        rows.append({
            "ticker": ticker, "trade_date": trade_day,
            "exit_date": pd.Timestamp(following) if following else pd.NaT,
            "signal_close": float(signal.close), "entry_open": entry_open,
            "exit_open": exit_open, "net_return": net_return,
            "positive": int(np.isfinite(net_return) and net_return > 0),
            "day_return": float(signal.close / morning.open - 1),
            "recent_return": float(signal.close / recent.open - 1),
            "range_pct": float(high / low - 1),
            "close_position": float((signal.close - low) / (high - low)) if high > low else 0.5,
            "log_turnover": float(np.log1p(turnover)),
            "observed_before_signal": bool(known["first_seen_at"].max() <= signal_deadline),
        })
    if not rows:
        raise ValueError("Belum ada candle 5 menit lengkap pada 14:30 untuk saham likuid.")
    panel = pd.DataFrame(rows).replace([np.inf, -np.inf], np.nan).dropna(subset=FEATURES)
    return panel.sort_values(["trade_date", "ticker"]).reset_index(drop=True)


def fit_overnight_model(panel: pd.DataFrame, signal_date: pd.Timestamp) -> tuple[Any, float]:
    matured = panel[(panel["exit_date"] < signal_date) & panel["net_return"].notna()]
    if len(matured) < MIN_TRAIN_ROWS or matured["trade_date"].nunique() < MIN_TRAIN_DATES:
        raise ValueError("Data transaksi overnight yang matang belum cukup untuk melatih model.")
    if matured["positive"].nunique() != 2:
        raise ValueError("Label latih overnight hanya memiliki satu kelas.")
    model = make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=500))
    model.fit(matured[FEATURES].to_numpy(dtype=float), matured["positive"].to_numpy(dtype=int))
    return model, float(matured["positive"].mean())


def evaluate_period(scored: pd.DataFrame) -> PeriodMetrics:
    if scored.empty:
        raise ValueError("Periode uji overnight kosong.")
    returns: list[float] = []
    baseline: list[float] = []
    traded = 0
    observed_days = 0
    for _, day in scored.groupby("trade_date", sort=True):
        selected = day[day["probability"] >= THRESHOLD].nlargest(TOP_K, "probability")
        momentum = day.nlargest(TOP_K, "day_return")
        traded += int(not selected.empty)
        observed_days += int(day["observed_before_signal"].sum() >= MIN_SYMBOLS)
        for picks, bucket in ((selected, returns), (momentum, baseline)):
            if picks.empty:
                bucket.append(0.0)
                continue
            # No entry means no fill; missing exit after entry is conservatively a full loss.
            outcomes = picks["net_return"].where(picks["entry_open"].notna(), 0.0).fillna(-1.0)
            bucket.append(float(outcomes.mean()))
    equity = np.cumprod(1 + np.asarray(returns))
    high_water = np.maximum.accumulate(np.r_[1.0, equity])[1:]
    labeled = scored[scored["net_return"].notna()]
    if labeled.empty:
        raise ValueError("Periode uji overnight belum memiliki hasil transaksi.")
    actual = labeled["positive"].to_numpy(dtype=int)
    return PeriodMetrics(
        total_return_pct=round(float((equity[-1] - 1) * 100), 2),
        benchmark_return_pct=round(float((np.prod(1 + np.asarray(baseline)) - 1) * 100), 2),
        max_drawdown_pct=round(float(np.min(equity / high_water - 1) * 100), 2),
        trade_days=traded, tested_days=len(returns),
        brier=round(float(brier_score_loss(actual, labeled["probability"])), 4),
        prior_brier=round(float(brier_score_loss(actual, labeled["prior_probability"])), 4),
        scored_rows=len(labeled), observed_before_signal_days=observed_days,
    )


def research_overnight(bars: pd.DataFrame, *, now: datetime | None = None) -> dict[str, Any]:
    panel = build_overnight_panel(bars)
    labeled_dates = pd.DatetimeIndex(sorted(panel.loc[panel["net_return"].notna(), "trade_date"].unique()))
    if len(labeled_dates) < MIN_DATES:
        raise ValueError(f"Butuh minimal {MIN_DATES} hari transaksi overnight lengkap; tersedia {len(labeled_dates)}.")
    validation_start = labeled_dates[int(len(labeled_dates) * 0.60)]
    holdout_start = labeled_dates[int(len(labeled_dates) * 0.80)]
    scored_days: list[pd.DataFrame] = []
    for date in labeled_dates[labeled_dates >= validation_start]:
        model, prior = fit_overnight_model(panel, date)
        day = panel[panel["trade_date"] == date].copy()
        day["probability"] = model.predict_proba(day[FEATURES].to_numpy(dtype=float))[:, 1]
        day["prior_probability"] = prior
        scored_days.append(day)
    scored = pd.concat(scored_days, ignore_index=True)
    validation_rows = scored[scored["trade_date"] < holdout_start]
    holdout_rows = scored[scored["trade_date"] >= holdout_start]
    validation = evaluate_period(validation_rows)
    holdout = evaluate_period(holdout_rows)
    timely_validation_rows = validation_rows[validation_rows["observed_before_signal"]]
    timely_holdout_rows = holdout_rows[holdout_rows["observed_before_signal"]]
    timely_validation = (evaluate_period(timely_validation_rows)
                         if timely_validation_rows["trade_date"].nunique() >= 10
                         and timely_validation_rows["net_return"].notna().any() else None)
    timely_holdout = (evaluate_period(timely_holdout_rows)
                      if timely_holdout_rows["trade_date"].nunique() >= 10
                      and timely_holdout_rows["net_return"].notna().any() else None)

    def passes(metrics: PeriodMetrics) -> bool:
        return (metrics.trade_days >= 10 and metrics.observed_before_signal_days >= 10
                and metrics.total_return_pct > max(0.0, metrics.benchmark_return_pct + 1.0)
                and metrics.brier < metrics.prior_brier)

    approved = (timely_validation is not None and timely_holdout is not None
                and passes(timely_validation) and passes(timely_holdout))
    collecting = timely_validation is None or timely_holdout is None
    current = now or datetime.now(JAKARTA)
    current = current.astimezone(JAKARTA) if current.tzinfo else current.replace(tzinfo=JAKARTA)
    latest_date = panel["trade_date"].max()
    latest = panel[panel["trade_date"] == latest_date].copy()
    timely_latest = latest[latest["observed_before_signal"]].copy()
    actionable = (latest_date.date() == current.date()
                  and time(14, 45) <= current.time() < time(15)
                  and len(timely_latest) >= max(MIN_SYMBOLS, int(np.ceil(0.9 * len(latest))))
                  and len(latest) >= MIN_SYMBOLS)
    if len(latest) < MIN_SYMBOLS:
        raise ValueError("Cakupan ticker 14:30 pada tanggal terbaru terlalu kecil.")
    model, _ = fit_overnight_model(panel, latest_date)
    latest["probability"] = model.predict_proba(latest[FEATURES].to_numpy(dtype=float))[:, 1]
    ranking = (latest[latest["observed_before_signal"]] if actionable else latest).nlargest(
        10, "probability"
    )
    candidates = [
        {"ticker": row.ticker, "probability_pct": round(row.probability * 100, 1),
         "signal_close": round(row.signal_close, 2)}
        for row in ranking.itertuples(index=False)
    ]
    signals = [candidate for candidate in candidates[:TOP_K]
               if candidate["probability_pct"] >= THRESHOLD * 100] if approved and actionable else []
    return {
        "status": ("ready" if signals else "collecting_point_in_time" if collecting
                   else "stale" if approved and not actionable else "no_edge"),
        "message": ("Pengamatan 14:30 yang tersedia sebelum 15:00 WIB belum mencapai 10 hari "
                    "pada masing-masing periode validasi dan holdout."
                    if collecting else ""),
        "approved": approved, "actionable": actionable, "version": MODEL_VERSION,
        "data_asof": latest_date.date().isoformat(), "symbols_with_signal_bar": len(latest),
        "symbols_observed_before_signal": len(timely_latest),
        "validation_from": validation_start.date().isoformat(),
        "holdout_from": holdout_start.date().isoformat(),
        "validation": asdict(validation), "holdout": asdict(holdout),
        "timely_validation": asdict(timely_validation) if timely_validation else None,
        "timely_holdout": asdict(timely_holdout) if timely_holdout else None,
        "signals": signals, "research_ranking": candidates,
        "execution": {"signal_window_wib": "14:45-15:00", "signal_bar_wib": "14:30",
                      "buy_wib": "15:15", "sell_next_session_wib": "09:05",
                      "buy_fee_pct": BUY_FEE * 100, "sell_fee_pct": SELL_FEE * 100,
                      "slippage_each_side_pct": SLIPPAGE_PER_SIDE * 100},
    }
