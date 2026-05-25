import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from screener.analyzer import (
    calc_moving_averages,
    find_swing_points,
    check_higher_highs,
    check_higher_lows,
    check_ma_bullish,
    calc_trend_score,
    analyze_sector,
    rank_sectors,
)


def _make_kline(closes, highs=None, lows=None):
    """辅助函数：从收盘价列表生成 K 线数据。"""
    kline = []
    for i, c in enumerate(closes):
        h = highs[i] if highs else c + abs(c) * 0.02
        l = lows[i] if lows else c - abs(c) * 0.02
        kline.append({
            "date": f"2026-{(i // 30) + 1:02d}-{(i % 30) + 1:02d}",
            "open": c - 0.5,
            "close": c,
            "high": h,
            "low": l,
            "volume": 1000000,
        })
    return kline


def _make_trending_up_kline(n=120):
    """生成一个明确上升趋势的 K 线数据，有明显波段高低点。"""
    import math
    closes = [100 + i * 0.5 + math.sin(i * 0.15) * 8 for i in range(n)]
    # highs/lows 更宽，确保波段点可检测
    highs = [c + 5 + abs(math.cos(i * 0.15)) * 3 for i, c in enumerate(closes)]
    lows = [c - 5 - abs(math.cos(i * 0.15)) * 3 for i, c in enumerate(closes)]
    return _make_kline(closes, highs, lows)


def _make_trending_down_kline(n=120):
    """生成一个明确下降趋势的 K 线数据。"""
    import math
    closes = [200 - i * 0.5 + math.sin(i * 0.15) * 8 for i in range(n)]
    highs = [c + 5 + abs(math.cos(i * 0.15)) * 3 for i, c in enumerate(closes)]
    lows = [c - 5 - abs(math.cos(i * 0.15)) * 3 for i, c in enumerate(closes)]
    return _make_kline(closes, highs, lows)


def _make_sideways_kline(n=120):
    """生成一个横盘震荡的 K 线数据。"""
    import math
    closes = [150 + math.sin(i * 0.15) * 10 for i in range(n)]
    highs = [c + 5 for c in closes]
    lows = [c - 5 for c in closes]
    return _make_kline(closes, highs, lows)


# --- calc_moving_averages ---

def test_calc_moving_averages_basic():
    closes = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    ma = calc_moving_averages(closes, [3, 5])
    assert ma[3][:2] == [None, None]
    assert ma[3][2] == pytest.approx(2.0)
    assert ma[3][9] == pytest.approx(9.0)
    assert ma[5][:4] == [None, None, None, None]
    assert ma[5][4] == pytest.approx(3.0)
    assert ma[5][9] == pytest.approx(8.0)


def test_calc_moving_averages_single_period():
    closes = [10, 20, 30]
    ma = calc_moving_averages(closes, [2])
    assert ma[2][0] is None
    assert ma[2][1] == pytest.approx(15.0)
    assert ma[2][2] == pytest.approx(25.0)


# --- find_swing_points ---

def test_find_swing_points_basic():
    # 构建一个有明确高低点的序列
    closes = [10, 12, 15, 13, 11, 10, 12, 16, 14, 12, 10, 13, 17, 15, 13]
    highs = [12, 14, 17, 15, 13, 12, 14, 18, 16, 14, 12, 15, 19, 17, 15]
    lows = [8, 10, 13, 11, 9, 8, 10, 14, 12, 10, 8, 11, 15, 13, 11]
    kline = _make_kline(closes, highs, lows)
    swing = find_swing_points(kline, window=2)

    assert len(swing["highs"]) > 0 or len(swing["lows"]) > 0


def test_find_swing_points_empty():
    kline = _make_kline([100] * 15)
    swing = find_swing_points(kline, window=2)
    # 全部相同价格，不应有明确的高低点
    assert len(swing["highs"]) == 0
    assert len(swing["lows"]) == 0


# --- check_higher_highs / check_higher_lows ---

def test_check_higher_highs_true():
    highs = [
        {"index": 1, "date": "2026-01-01", "price": 100},
        {"index": 2, "date": "2026-01-02", "price": 110},
        {"index": 3, "date": "2026-01-03", "price": 120},
    ]
    assert check_higher_highs(highs) is True


def test_check_higher_highs_false():
    highs = [
        {"index": 1, "date": "2026-01-01", "price": 120},
        {"index": 2, "date": "2026-01-02", "price": 110},
        {"index": 3, "date": "2026-01-03", "price": 100},
    ]
    assert check_higher_highs(highs) is False


def test_check_higher_highs_insufficient():
    assert check_higher_highs([]) is False
    assert check_higher_highs([{"index": 0, "date": "", "price": 100}]) is False


def test_check_higher_lows_true():
    lows = [
        {"index": 1, "date": "2026-01-01", "price": 80},
        {"index": 2, "date": "2026-01-02", "price": 90},
        {"index": 3, "date": "2026-01-03", "price": 100},
    ]
    assert check_higher_lows(lows) is True


def test_check_higher_lows_false():
    lows = [
        {"index": 1, "date": "2026-01-01", "price": 100},
        {"index": 2, "date": "2026-01-02", "price": 90},
        {"index": 3, "date": "2026-01-03", "price": 80},
    ]
    assert check_higher_lows(lows) is False


# --- check_ma_bullish ---

def test_check_ma_bullish_true():
    ma = {
        5: [None] * 59 + [120],
        10: [None] * 59 + [110],
        20: [None] * 59 + [100],
        60: [None] * 59 + [90],
    }
    assert check_ma_bullish(ma, 59) is True


def test_check_ma_bullish_false():
    ma = {
        5: [None] * 59 + [90],
        10: [None] * 59 + [100],
        20: [None] * 59 + [110],
        60: [None] * 59 + [120],
    }
    assert check_ma_bullish(ma, 59) is False


def test_check_ma_bullish_none_values():
    ma = {
        5: [None] * 60,
        10: [None] * 60,
        20: [None] * 60,
        60: [None] * 60,
    }
    assert check_ma_bullish(ma, 59) is False


# --- calc_trend_score ---

def test_calc_trend_score_uptrend():
    kline = _make_trending_up_kline(120)
    closes = [k["close"] for k in kline]
    ma = calc_moving_averages(closes, [5, 10, 20, 60])
    swing = find_swing_points(kline, window=5)
    score = calc_trend_score(kline, swing, ma)
    assert score >= 50


def test_calc_trend_score_downtrend():
    kline = _make_trending_down_kline(120)
    closes = [k["close"] for k in kline]
    ma = calc_moving_averages(closes, [5, 10, 20, 60])
    swing = find_swing_points(kline, window=5)
    score = calc_trend_score(kline, swing, ma)
    assert score < 50


# --- analyze_sector ---

def test_analyze_sector_insufficient_data():
    kline = _make_kline([100] * 30)
    assert analyze_sector(kline) is None


def test_analyze_sector_uptrend_passes():
    kline = _make_trending_up_kline(120)
    result = analyze_sector(kline)
    assert result is not None
    assert result["trend_score"] >= 50
    assert "trend_score" in result
    assert "ma5" in result
    assert "reason" in result


def test_analyze_sector_downtrend_fails():
    kline = _make_trending_down_kline(120)
    result = analyze_sector(kline)
    assert result is None


def test_analyze_sector_sideways_low_score():
    kline = _make_sideways_kline(120)
    result = analyze_sector(kline, min_score=0)
    # 横盘趋势得分应该较低
    if result is not None:
        assert result["trend_score"] < 60


# --- rank_sectors ---

def test_rank_sectors_basic():
    sectors = [
        {"name": "A", "trend_score": 70, "period_return_20d": 5.0},
        {"name": "B", "trend_score": 85, "period_return_20d": 10.0},
        {"name": "C", "trend_score": 60, "period_return_20d": 3.0},
    ]
    ranked = rank_sectors(sectors, top_n=2)
    assert len(ranked) == 2
    assert ranked[0]["name"] == "B"
    assert ranked[1]["name"] == "A"


def test_rank_sectors_fewer_than_top_n():
    sectors = [
        {"name": "A", "trend_score": 70, "period_return_20d": 5.0},
    ]
    ranked = rank_sectors(sectors, top_n=10)
    assert len(ranked) == 1
