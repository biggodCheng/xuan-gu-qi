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
    assert "1 次" in r["label"]


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


from screener.analyzer import check_pullback


def _kline_cv(series):
    """series: [(close, volume), ...] → kline。"""
    return [{"date": f"d{i}", "close": c, "volume": v} for i, (c, v) in enumerate(series)]


def test_pullback_hit():
    # 涨停日 d5: close=11 vol=1000；之后连续2天 close<11 且量递减(<prev*0.8)
    zt = [{"date": "d5", "chg": 10.0, "close": 11.0, "volume": 1000.0}]
    k = _kline_cv([(10, 100)] * 5 + [(11, 1000), (10.5, 700), (10.2, 500), (10.0, 800)])
    r = check_pullback(k, zt)
    assert r["pass"] is True
    assert "d6" in r["label"]


def test_pullback_no_zt():
    assert check_pullback(_kline_cv([(10, 100), (11, 200)]), []).get("pass") is False


def test_pullback_volume_not_shrink():
    # 涨停后价格回落但量不缩 → 不命中
    zt = [{"date": "d1", "chg": 10.0, "close": 11.0, "volume": 1000.0}]
    k = _kline_cv([(10, 100), (11, 1000), (10.5, 950), (10.2, 920)])  # 量仅微降
    r = check_pullback(k, zt)
    assert r["pass"] is False


def test_pullback_price_recovers_resets():
    # 中途价格回到>=涨停收盘，则中断
    zt = [{"date": "d1", "chg": 10.0, "close": 11.0, "volume": 1000.0}]
    k = _kline_cv([(10, 100), (11, 1000), (10.5, 700), (11.5, 600), (10.8, 400), (10.6, 300)])
    r = check_pullback(k, zt)
    # d4/d5/d6 连续缩量2天 → 命中
    assert r["pass"] is True


from screener.analyzer import check_marketcap


def test_marketcap_pass():
    r = check_marketcap(150.0)
    assert r["pass"] is True and r["total"] == 150.0


def test_marketcap_fail():
    r = check_marketcap(851.15)
    assert r["pass"] is False


def test_marketcap_none():
    r = check_marketcap(None)
    assert r["pass"] is False and "不可用" in r["label"]
