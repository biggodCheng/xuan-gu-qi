import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from screener.analyzer import check_new_high


def _kline(closes):
    """按收盘价列表构造 K 线，日期用占位。"""
    return [{"date": f"2026-01-{i+1:02d}", "close": c, "volume": 100.0} for i, c in enumerate(closes)]


def test_new_high_today():
    # 前100日最高10，今日11 → 今日新高
    closes = [8.0] * 99 + [10.0] + [11.0]
    r = check_new_high(_kline(closes))
    assert r["pass"] is True
    assert "今日新高" in r["label"]


def test_new_high_within_recent_20():
    # 今天没新高（今日10 < 前高11），但3天前创过新高(11>=此前最高10)
    closes = [9.0] * 97 + [11.0, 10.5, 10.2, 10.0]
    r = check_new_high(_kline(closes))
    assert r["pass"] is True
    assert "近" in r["label"] and "日前" in r["label"]


def test_new_high_fail():
    # 近20日均未创新高：前100日最高12（远在20日外），近20日最高10
    closes = [12.0] + [8.0] * 99 + [10.0] * 20
    r = check_new_high(_kline(closes))
    assert r["pass"] is False
    assert "距高点" in r["label"]


def test_new_high_insufficient_data():
    r = check_new_high(_kline([10.0] * 50))
    assert r["pass"] is False
    assert "数据不足" in r["label"]
