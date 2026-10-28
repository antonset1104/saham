from datetime import datetime, timezone, timedelta

import pandas as pd

from global_indices import format_index_lines


def test_global_indices_show_actual_session_dates_and_no_stale_open() -> None:
    dates = pd.to_datetime(["2026-10-27", "2026-10-28"])
    columns = pd.MultiIndex.from_product(
        [["Open", "Close"], ["^GSPC", "^N225"]], names=["Price", "Ticker"]
    )
    data = pd.DataFrame(index=dates, columns=columns, dtype=float)
    data.loc[dates[0], ("Close", "^GSPC")] = 6000
    data.loc[dates[0], ("Open", "^GSPC")] = 5950
    data.loc[dates[0], ("Close", "^N225")] = 50000
    data.loc[dates[1], ("Open", "^N225")] = 50200
    now = datetime(2026, 10, 28, 10, tzinfo=timezone(timedelta(hours=7)))

    lines = format_index_lines(data, now)

    sp = next(line for line in lines if "S&amp;P" in line or "S&P" in line)
    nikkei = next(line for line in lines if "Nikkei 225" in line)
    assert "6,000.00 (27/10)" in sp
    assert "belum buka / data belum tersedia" in sp
    assert "50,200.00" in nikkei


def test_global_indices_report_missing_data_without_inventing_quotes() -> None:
    now = datetime(2026, 10, 28, 10, tzinfo=timezone(timedelta(hours=7)))
    lines = format_index_lines(pd.DataFrame(), now)
    assert all("data belum tersedia" in line for line in lines[2:-1])
