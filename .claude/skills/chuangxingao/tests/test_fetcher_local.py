# -*- coding: utf-8 -*-
"""chuangxingao fetcher 本地优先(招商证券 vipdoc)单测。

原腾讯 qfq 前复权收盘价 → 本地不复权(用户接受降级)。
get_stock_history 返回纯 close 序列, 含 exclude_last 逻辑。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from screener import fetcher  # noqa: E402


def _bar(c, date="2026-07-21"):
    return {"date": date, "open": c, "high": c, "low": c, "close": c, "volume": 1, "amount": 1}


def _boom(*a, **k):
    raise AssertionError("不应触网: 本地应有数据")


def test_get_stock_history_uses_local_first(monkeypatch):
    monkeypatch.setattr(fetcher.local_kline, "read_day", lambda s: [_bar(1.05)])
    monkeypatch.setattr(fetcher, "_fetch_tencent_closes", _boom)
    closes = fetcher.get_stock_history("600519", days=100)
    assert closes == [1.05]


def test_get_stock_history_exclude_last(monkeypatch):
    """exclude_last=True → 丢弃最新一根(判新高不能用今日)。"""
    monkeypatch.setattr(fetcher.local_kline, "read_day",
                        lambda s: [_bar(1.0, "2026-07-20"), _bar(1.05, "2026-07-21")])
    monkeypatch.setattr(fetcher, "_fetch_tencent_closes", _boom)
    closes = fetcher.get_stock_history("600519", days=100, exclude_last=True)
    assert closes == [1.0]
