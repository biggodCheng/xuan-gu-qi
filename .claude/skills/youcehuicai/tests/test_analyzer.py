"""右侧趋势回踩判定纯函数单测。"""
from screener.analyzer import (
    index_above_ma20,
    market_stabilized,
    is_right_side_pullback,
)


def _bar(open_, close, high, low, volume):
    return {"day": "x", "open": open_, "close": close, "high": high, "low": low, "volume": volume}


def _idx_bars(n, close_fn):
    return [{"date": "x", "open": 0, "high": 0, "low": 0, "close": close_fn(i), "volume": 0} for i in range(n)]


# ---- 企稳门控 ----

def test_index_above_ma20_above():
    bars = _idx_bars(25, lambda i: 100.0 + i)  # 上升，close>MA20
    assert index_above_ma20(bars) is True


def test_index_above_ma20_below():
    bars = _idx_bars(25, lambda i: 100.0 - i)  # 下降，close<MA20
    assert index_above_ma20(bars) is False


def test_market_stabilized_all_above():
    up = _idx_bars(25, lambda i: 100.0 + i)
    stab, det = market_stabilized({"上证": up, "沪深300": up, "创业板": up})
    assert stab is True
    assert len(det) == 3


def test_market_stabilized_one_below():
    stab, _ = market_stabilized({
        "上证": _idx_bars(25, lambda i: 100.0 + i),
        "创业板": _idx_bars(25, lambda i: 100.0 - i),
    })
    assert stab is False


# ---- 右侧回踩 ----

def _good_pullback_bars():
    """构造满足4条的上涨趋势回踩K线(60条)。

    前40日上升(10→13.9)，中17日横盘15.0，末3日缩量且close15.3回踩MA10(~15.03)。
    """
    bars = []
    for i in range(40):
        c = 10.0 + 0.1 * i
        bars.append(_bar(c, c, c + 0.5, c - 0.5, 100))
    for _ in range(17):
        bars.append(_bar(15.0, 15.0, 15.5, 14.5, 100))
    bars.append(_bar(15.0, 15.0, 15.5, 14.5, 50))  # 57 缩量
    bars.append(_bar(15.0, 15.0, 15.5, 14.5, 50))  # 58
    bars.append(_bar(15.0, 15.3, 15.6, 14.8, 50))  # 59 close15.3 回踩MA10
    return bars


def test_pullback_all_pass():
    r = is_right_side_pullback(_good_pullback_bars(), 200.0)
    assert r is not None
    assert r["pullback_ma"] == "MA10"


def test_pullback_not_uptrend():
    bars = _good_pullback_bars()
    bars[-1]["close"] = 10.0  # 跌破MA20，非多头
    assert is_right_side_pullback(bars, 200.0) is None


def test_pullback_not_at_ma():
    bars = _good_pullback_bars()
    bars[-1]["close"] = 16.0  # 远离MA10/MA20 (>2%)
    assert is_right_side_pullback(bars, 200.0) is None


def test_pullback_not_shrinking():
    bars = _good_pullback_bars()
    for b in bars[-3:]:
        b["volume"] = 100  # 近3日不缩量
    assert is_right_side_pullback(bars, 200.0) is None


def test_pullback_cap_too_small():
    assert is_right_side_pullback(_good_pullback_bars(), 50.0) is None


def test_pullback_cap_too_large():
    assert is_right_side_pullback(_good_pullback_bars(), 600.0) is None


def test_pullback_insufficient_bars():
    assert is_right_side_pullback(_good_pullback_bars()[:55], 200.0) is None
