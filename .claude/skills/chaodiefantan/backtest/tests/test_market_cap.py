"""市值估算纯函数单测。"""
from backtest.market_cap import compute_float_shares, estimate_cap_yi, in_cap_band


def test_compute_float_shares():
    # 流通市值 150 亿, 收盘价 15 元 -> 股本 10 亿股
    assert compute_float_shares(cap_yi=150.0, close=15.0) == 1_000_000_000.0


def test_estimate_cap_yi():
    # 股本 10 亿股, 历史不复权价 12 元 -> 市值 120 亿
    assert estimate_cap_yi(close_unadj=12.0, float_shares=1_000_000_000.0) == 120.0


def test_in_cap_band():
    assert in_cap_band(50.0) is True
    assert in_cap_band(500.0) is True
    assert in_cap_band(49.9) is False
    assert in_cap_band(500.1) is False
