import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from screener import fetcher


def test_get_kline_since_filters_before_since(monkeypatch):
    raw = [
        ["2026-07-10", "9.80", "10.00", "10.1", "9.7", "1000"],  # 公告日当天(应排除)
        ["2026-07-11", "10.00", "10.50", "10.6", "9.9", "2000"], # 基准日(次日)
        ["2026-07-14", "10.40", "11.00", "11.1", "10.3", "3000"],
    ]

    def fake_tencent(code, start):
        return raw

    monkeypatch.setattr(fetcher, "_fetch_tencent_kline", fake_tencent)
    out = fetcher.get_kline_since("600000", "2026-07-10")
    assert [r["date"] for r in out] == ["2026-07-11", "2026-07-14"]
    assert out[0]["open"] == 10.00 and out[0]["close"] == 10.50


def test_get_kline_since_empty_when_fetch_fails(monkeypatch):
    monkeypatch.setattr(fetcher, "_fetch_tencent_kline", lambda c, s: [])
    monkeypatch.setattr(fetcher, "_fetch_sina_closes", lambda c: [])
    assert fetcher.get_kline_since("600000", "2026-07-10") == []
