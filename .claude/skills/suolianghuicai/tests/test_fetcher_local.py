# -*- coding: utf-8 -*-
"""suolianghuicai fetcher 本地优先(招商证券 vipdoc)单测。

原腾讯 qfq 前复权 → 本地不复权(用户接受降级, 短期回踩窗口影响小)。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from screener import fetcher  # noqa: E402


def _fake():
    return [{"date": "2026-07-21", "open": 1.0, "high": 1.1, "low": 0.9,
             "close": 1.05, "volume": 100, "amount": 1e6}]


def _boom(*a, **k):
    raise AssertionError("不应触网: 本地应有数据")


def test_get_stock_kline_uses_local_first(monkeypatch):
    monkeypatch.setattr(fetcher.local_kline, "read_day", lambda s: _fake())
    monkeypatch.setattr(fetcher, "_fetch_tencent_kline", _boom)
    rows = fetcher.get_stock_kline("600519", days=30)
    assert set(rows[0]) == {"date", "close", "volume"}
    assert rows[0]["close"] == 1.05
