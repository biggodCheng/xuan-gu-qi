"""市值估算纯函数单测。"""
from backtest.market_cap import compute_float_shares, estimate_cap_yi, in_cap_band, shares_at_date


def test_compute_float_shares():
    # 流通市值 150 亿, 收盘价 15 元 -> 股本 10 亿股
    assert compute_float_shares(cap_yi=150.0, close=15.0) == 1_000_000_000.0


def test_estimate_cap_yi():
    # 股本 10 亿股, 历史不复权价 12 元 -> 市值 120 亿
    assert estimate_cap_yi(close_unadj=12.0, float_shares=1_000_000_000.0) == 120.0


def test_in_cap_band():
    assert in_cap_band(30.0) is True
    assert in_cap_band(100.0) is True
    assert in_cap_band(29.9) is False
    assert in_cap_band(100.1) is False


def test_shares_at_date_before_split():
    # 当前1000股,2024-06-19 10送10 -> 2024-01-01股本=500
    records = [{"ex_date": "2024-06-19", "song": 10, "zhuan": 0}]
    assert shares_at_date(1000, records, "2024-01-01") == 500.0


def test_shares_at_date_after_split():
    records = [{"ex_date": "2024-06-19", "song": 10, "zhuan": 0}]
    assert shares_at_date(1000, records, "2024-12-01") == 1000.0


def test_shares_at_date_multiple_splits():
    # 2023-06 10送5, 2024-06 10转5 -> 2022-01 = 1000/(1.5*1.5)
    records = [{"ex_date": "2023-06-19", "song": 5, "zhuan": 0},
               {"ex_date": "2024-06-19", "song": 0, "zhuan": 5}]
    assert abs(shares_at_date(1000, records, "2022-01-01") - 1000 / 2.25) < 0.01


def test_shares_at_date_no_record():
    assert shares_at_date(1000, [], "2020-01-01") == 1000.0


def test_shares_at_date_cash_dividend_ignored():
    # 仅派息(送转=0)不影响股本
    records = [{"ex_date": "2024-06-19", "song": 0, "zhuan": 0}]
    assert shares_at_date(1000, records, "2024-01-01") == 1000.0
