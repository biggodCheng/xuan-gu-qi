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
