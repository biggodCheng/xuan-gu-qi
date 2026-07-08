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
    # 前100日内有高点12（index80，在20日窗口外），近20日最高10，均未创新高
    closes = [8.0] * 80 + [12.0] + [8.0] * 19 + [10.0] * 20
    r = check_new_high(_kline(closes))
    assert r["pass"] is False
    assert "距高点" in r["label"]


def test_new_high_insufficient_data():
    r = check_new_high(_kline([10.0] * 50))
    assert r["pass"] is False
    assert "数据不足" in r["label"]


from screener.analyzer import check_recent_zt


def test_recent_zt_hit():
    # 最近15日内有一天涨幅 10%（>= 9.5%）
    closes = [10.0] * 20 + [11.0] + [10.5] * 5  # 第21日 +10%
    k = [{"date": f"d{i}", "close": c, "volume": 100.0} for i, c in enumerate(closes)]
    r = check_recent_zt(k, threshold=9.5)
    assert r["pass"] is True
    assert r["count"] == 1
    assert r["dates"][0]["chg"] == 10.0


def test_recent_zt_outside_window():
    # 涨停在20天前（窗口外）
    closes = [10.0] * 5 + [11.0] + [10.0] * 20
    k = [{"date": f"d{i}", "close": c, "volume": 100.0} for i, c in enumerate(closes)]
    r = check_recent_zt(k, threshold=9.5)
    assert r["pass"] is False
    assert r["count"] == 0


def test_recent_zt_raw_keeps_close_volume():
    closes = [10.0] * 10 + [11.0]
    k = [{"date": f"d{i}", "close": c, "volume": float(i) * 100} for i, c in enumerate(closes)]
    r = check_recent_zt(k, threshold=9.5)
    assert r["_raw"][0]["close"] == 11.0
    assert r["_raw"][0]["volume"] == 1000.0
