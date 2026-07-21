# -*- coding: utf-8 -*-
"""eval-stock fetcher 本地优先(招商证券 vipdoc)单测。

eval-stock 原用新浪 getKLineData 不复权, 迁本地不复权 = 等价。
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


def test_fetch_kline_uses_local_first(monkeypatch):
    monkeypatch.setattr(fetcher.local_kline, "read_day", lambda s: _fake())
    monkeypatch.setattr(fetcher._session, "get", _boom)
    rows = fetcher.fetch_kline("600519", days=130)
    assert len(rows) == 1
    assert set(rows[0]) == {"date", "open", "close", "high", "low", "volume"}
    assert rows[0]["close"] == 1.05


def test_fetch_kline_truncates_to_days(monkeypatch):
    monkeypatch.setattr(fetcher.local_kline, "read_day", lambda s: _fake() * 5)
    monkeypatch.setattr(fetcher._session, "get", _boom)
    rows = fetcher.fetch_kline("600519", days=3)
    assert len(rows) == 3
