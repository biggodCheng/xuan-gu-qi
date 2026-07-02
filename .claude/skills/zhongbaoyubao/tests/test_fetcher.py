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
    assert fetcher.get_kline_since("600000", "2026-07-10") == []


def test_get_announcements_parses_rows(monkeypatch):
    payload = {
        "success": True,
        "result": {"data": [
            {"SECURITY_CODE": "600160", "SECURITY_NAME_ABBR": "巨化股份",
             "NOTICE_DATE": "2026-07-10 00:00:00", "REPORTDATE": "2026-06-30",
             "FORECASTTYPE": "预增", "INCREASEL": 80.0, "INCREASET": 120.0,
             "PUBLISHNAME": "化学制品"},
        ]},
    }
    monkeypatch.setattr(fetcher, "_request_announcements",
                        lambda report_date, page: (payload, True))
    out = fetcher.get_announcements(report_date="2026-06-30")
    assert out[0]["code"] == "600160"
    assert out[0]["name"] == "巨化股份"
    assert out[0]["notice_date"] == "2026-07-10"
    assert out[0]["yoy_lower"] == 80.0
    assert out[0]["yoy_upper"] == 120.0


def test_get_announcements_empty_when_api_fails(monkeypatch):
    monkeypatch.setattr(fetcher, "_request_announcements",
                        lambda report_date, page: ({}, False))
    assert fetcher.get_announcements() == []
