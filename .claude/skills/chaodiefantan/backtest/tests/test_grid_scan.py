# -*- coding: utf-8 -*-
"""scan_band_signals 单测 — 逐日逐股扫描波段信号。"""
from backtest.grid_backtest import scan_band_signals


def _bar(date, o, h, l, c, v):
    return {"date": date, "open": o, "high": h, "low": l, "close": c, "volume": v}


def test_scan_finds_signal_on_qualified_day():
    # 前20日跌 100→70, 第21日(T)阳包阴放量
    bars = []
    for i in range(20):
        c = 100 - (100 - 70) / 19 * i
        bars.append(_bar(f"2024-01-{i+1:02d}", c + 0.5, c + 1, c - 1, c, 1000))
    bars.append(_bar("2024-01-21", 70.3, 71.5, 69, 72, 2000))   # T 日合格

    klines = {"600001": bars}
    dates = ["2024-01-21"]
    shares = lambda code, date: 1e8                      # 1亿股
    names = {"600001": "测试股"}
    unadj = {"600001": {"2024-01-21": 72.0}}             # 不复权收盘

    sigs = scan_band_signals(klines, shares, names, dates, unadj,
                            drop_pct=20.0, vol_ratio=1.5, use_shrink=False)
    assert len(sigs) == 1
    s = sigs[0]
    assert s["code"] == "600001" and s["name"] == "测试股"
    assert s["signal_date"] == "2024-01-21"
    assert s["stop_loss"] == 69.0
    assert s["market_cap_T"] > 0


def test_scan_skips_non_target_date():
    bars = [_bar(f"2024-01-{i+1:02d}", 10, 11, 9, 10, 100) for i in range(25)]
    sigs = scan_band_signals({"600001": bars}, lambda c, d: 1e8,
                            {"600001": "X"}, ["2099-12-31"], {},
                            drop_pct=20.0, vol_ratio=1.5, use_shrink=False)
    assert sigs == []                                    # T 日不在 dates → 无信号
