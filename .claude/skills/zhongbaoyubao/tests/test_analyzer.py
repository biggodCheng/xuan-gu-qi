import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from screener.analyzer import filter_announcements


def test_keeps_preannounce_above_threshold():
    items = [{"code": "A", "predict_type": "预增", "yoy_lower": 50.0, "yoy_upper": 80.0}]
    out = filter_announcements(items)
    assert len(out) == 1 and out[0]["code"] == "A"


def test_rejects_below_threshold():
    items = [{"code": "B", "predict_type": "预增", "yoy_lower": 49.9, "yoy_upper": 60.0}]
    assert filter_announcements(items) == []


def test_rejects_non_preannounce():
    items = [{"code": "C", "predict_type": "扭亏", "yoy_lower": 999.0}]
    assert filter_announcements(items) == []


def test_rejects_missing_yoy_lower():
    items = [{"code": "D", "predict_type": "预增", "yoy_lower": None}]
    assert filter_announcements(items) == []

from screener.analyzer import compute_chg_total, compute_chg_today, build_daily, held_days


def test_chg_total_basic():
    assert compute_chg_total(10.0, 11.0) == 10.0


def test_chg_total_zero_base_protected():
    assert compute_chg_total(0.0, 5.0) is None


def test_chg_today_basic():
    assert compute_chg_today(10.0, 11.0) == 10.0


def test_chg_today_none_when_no_prev():
    assert compute_chg_today(None, 11.0) is None


def test_build_daily_first_row_chg_today_equals_total():
    kline = [{"date": "2026-07-11", "open": 10.0, "close": 10.5}]
    daily = build_daily(kline, base_price=10.0)
    assert len(daily) == 1
    assert daily[0]["chg_total"] == 5.0
    assert daily[0]["chg_today"] == 5.0  # 首日=累计


def test_build_daily_multi_rows():
    kline = [
        {"date": "2026-07-11", "open": 10.0, "close": 10.0},
        {"date": "2026-07-14", "open": 10.1, "close": 11.0},
    ]
    daily = build_daily(kline, base_price=10.0)
    assert daily[0]["chg_total"] == 0.0
    assert daily[1]["chg_total"] == 10.0
    assert daily[1]["chg_today"] == 10.0  # (11-10)/10


def test_held_days():
    kline = [{"date": f"2026-07-{d}", "open": 10.0, "close": 10.0} for d in (11, 12, 13)]
    daily = build_daily(kline, 10.0)
    assert held_days(daily) == 2  # len-1


def test_build_daily_empty():
    assert build_daily([], 10.0) == []

from screener.analyzer import should_expire


def test_not_expired_at_29():
    assert should_expire(29) is False


def test_expired_at_30():
    assert should_expire(30) is True


def test_expired_above_30():
    assert should_expire(35) is True


def test_custom_hold_days():
    assert should_expire(9, hold_days=10) is False
    assert should_expire(10, hold_days=10) is True
