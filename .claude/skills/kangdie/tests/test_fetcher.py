# -*- coding: utf-8 -*-
"""fetcher 本地优先(招商证券 vipdoc) + 新浪 fallback 单测。

三 skill(chaodiefantan/kangdie/youcehuicai)共用 kangdie/screener/fetcher.py,
改这里 = 三 skill 数据源全迁本地。本地 vol(手) 与新浪 volume 逐位等价(实测比值 1.0)。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from screener import fetcher  # noqa: E402


def _fake_local_rows():
    """本地 read_day 风格(3 条, 茅台真实尾段)。"""
    return [
        {"date": "2026-07-17", "open": 1269.01, "high": 1269.33, "low": 1238.98,
         "close": 1253.00, "volume": 5841730, "amount": 7.32e9},
        {"date": "2026-07-20", "open": 1270.00, "high": 1329.00, "low": 1266.00,
         "close": 1327.50, "volume": 10615115, "amount": 1.39e10},
        {"date": "2026-07-21", "open": 1338.98, "high": 1344.70, "low": 1296.87,
         "close": 1308.00, "volume": 7714770, "amount": 1.02e10},
    ]


def _boom(*a, **k):
    raise AssertionError("不应触网: 本地应有数据")


def test_get_stock_kline_uses_local_first(monkeypatch):
    """本地有数据 → 返回 {day,open,high,low,close,volume}, 不触网。"""
    monkeypatch.setattr(fetcher.local_kline, "read_day", lambda sym: _fake_local_rows())
    monkeypatch.setattr(fetcher._session, "get", _boom)
    rows = fetcher.get_stock_kline("600519", days=70)
    assert len(rows) == 3
    assert set(rows[0]) == {"day", "open", "high", "low", "close", "volume"}
    assert rows[-1]["day"] == "2026-07-21"
    assert rows[-1]["close"] == 1308.00
    assert rows[-1]["volume"] == 7714770.0  # 本地 vol(手), 与新浪 volume 等价


def test_get_stock_kline_truncates_to_days(monkeypatch):
    monkeypatch.setattr(fetcher.local_kline, "read_day", lambda sym: _fake_local_rows())
    monkeypatch.setattr(fetcher._session, "get", _boom)
    rows = fetcher.get_stock_kline("600519", days=2)
    assert len(rows) == 2
    assert rows[0]["day"] == "2026-07-20"  # 末尾 2 条


def test_get_stock_kline_symbol_prefix_built(monkeypatch):
    """纯数字 code → 本地读取加 sh/sz 前缀(本地文件名 sh600519.day)。"""
    seen = {}

    def fake_read(sym):
        seen["sym"] = sym
        return _fake_local_rows()
    monkeypatch.setattr(fetcher.local_kline, "read_day", fake_read)
    monkeypatch.setattr(fetcher._session, "get", _boom)
    fetcher.get_stock_kline("600519")
    assert seen["sym"] == "sh600519"


def test_get_stock_kline_falls_back_to_sina_when_local_empty(monkeypatch):
    """本地为空 → fallback 新浪。"""
    monkeypatch.setattr(fetcher.local_kline, "read_day", lambda sym: [])

    class FakeResp:
        def json(self):
            return [{"day": "2026-07-21", "open": 1.0, "close": 2.0,
                     "high": 3.0, "low": 0.5, "volume": 100.0}]
    monkeypatch.setattr(fetcher._session, "get", lambda *a, **k: FakeResp())
    rows = fetcher.get_stock_kline("600519", days=70)
    assert len(rows) == 1
    assert rows[0]["close"] == 2.0


def test_get_index_kline_uses_local_first(monkeypatch):
    """指数 symbol 已带前缀(sh000001), 直传本地, 返回 {date,...}。"""
    seen = {}

    def fake_read(sym):
        seen["sym"] = sym
        return _fake_local_rows()
    monkeypatch.setattr(fetcher.local_kline, "read_day", fake_read)
    monkeypatch.setattr(fetcher._session, "get", _boom)
    rows = fetcher.get_index_kline("sh000001", days=60)
    assert seen["sym"] == "sh000001"
    assert set(rows[0]) == {"date", "open", "high", "low", "close", "volume"}
    assert rows[-1]["date"] == "2026-07-21"
