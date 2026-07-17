"""抗跌判定纯函数单测 — 构造数据测各筛选条件边界。

覆盖：
- market_new_low: 触发/不触发/数据不足
- compute_ret20: 正常/数据不足
- is_anticorrection: 全通过/各条件单独失败/数据不足
"""
from screener.analyzer import (
    OUTPERFORM_GAP,
    RET20_MAX,
    VOL_SHRINK_THRESHOLD,
    MARKET_CAP_MIN,
    MARKET_CAP_MAX,
    compute_ret20,
    is_anticorrection,
    market_big_drop,
)


# ---- 辅助：构造 K 线序列 ----

def _make_bars(n, close_fn, low_fn, vol_fn):
    """生成 n 条 K 线（按日期正序）。

    close_fn/low_fn/vol_fn 接收 bar index (0..n-1)，返回对应值。
    """
    bars = []
    for i in range(n):
        bars.append({
            "day": f"2026-01-{i + 1:02d}",
            "open": close_fn(i),
            "high": close_fn(i) + 1,
            "low": low_fn(i),
            "close": close_fn(i),
            "volume": vol_fn(i),
        })
    return bars


def _make_index_bars(n, close_fn, low_fn):
    """生成 n 条指数 K 线（用 date 键兼容指数格式）。"""
    bars = []
    for i in range(n):
        bars.append({
            "date": f"2026-01-{i + 1:02d}",
            "open": close_fn(i),
            "high": close_fn(i) + 1,
            "low": low_fn(i),
            "close": close_fn(i),
            "volume": 1000,
        })
    return bars


def _good_stock_bars(n=70):
    """构造满足全部抗跌条件的个股 K 线（ret20 控制在 ~10%，满足 RET20_MAX=15）。

    - 近20日 low ~11-12.2 ≥ 前40日 low ~8-11（不破前低）
    - close[-1]≈13.2, close[-21]≈12 → ret20≈10%
    - 近5日 volume=50 < 近20日 volume=100 × 0.8=80（缩量）
    """
    def close_fn(i):
        # 前50条 close 从 15 线性降到 12（制造 low=8 的历史）
        # 之后回升到 ~13.2（ret20≈10%，满足涨幅上限 15%）
        if i < 50:
            return 15.0 - 0.06 * i
        return 12.0 + 0.06 * (i - 49)

    def low_fn(i):
        if i < 50:
            return close_fn(i) - 4  # 历史 low 可低至 ~8
        return close_fn(i) - 1  # 近期 low ~12-19

    def vol_fn(i):
        if i >= n - 5:
            return 50.0  # 近5日缩量
        return 100.0

    return _make_bars(n, close_fn, low_fn, vol_fn)


# ============ market_big_drop ============

def test_market_big_drop_triggered():
    """今日跌幅 ≤ 阈值 → 触发。"""
    bars = _make_index_bars(5, lambda i: 100.0, lambda i: 99.0)
    bars[-2]["close"] = 100.0
    bars[-1]["close"] = 98.0  # 跌幅 -2% ≤ -1.5 → 触发
    is_drop, chg, close = market_big_drop(bars, threshold=-1.5)
    assert is_drop is True
    assert chg == -2.0
    assert close == 98.0


def test_market_big_drop_not_triggered():
    """今日跌幅 > 阈值 → 不触发。"""
    bars = _make_index_bars(5, lambda i: 100.0, lambda i: 99.0)
    bars[-2]["close"] = 100.0
    bars[-1]["close"] = 99.5  # 跌幅 -0.5% > -1.5 → 不触发
    is_drop, chg, close = market_big_drop(bars, threshold=-1.5)
    assert is_drop is False


def test_market_big_drop_insufficient_data():
    """数据不足 2 条 → 不触发。"""
    bars = _make_index_bars(1, lambda i: 100.0, lambda i: 99.0)
    is_drop, chg, close = market_big_drop(bars, threshold=-1.5)
    assert is_drop is False
    assert chg == 0.0


def test_market_big_drop_exact_equal():
    """跌幅恰好等于阈值 → 触发（≤）。"""
    bars = _make_index_bars(5, lambda i: 100.0, lambda i: 99.0)
    bars[-2]["close"] = 100.0
    bars[-1]["close"] = 98.5  # 跌幅 -1.5% = 阈值 → 触发
    is_drop, _, _ = market_big_drop(bars, threshold=-1.5)
    assert is_drop is True


# ============ compute_ret20 ============

def test_compute_ret20_normal():
    """(20-15)/15*100 = 33.33..."""
    bars = _make_bars(25, lambda i: 15.0 if i < 49 else 20.0, lambda i: 14.0, lambda i: 100)
    # 手动构造 close[-1]=20, close[-21]=15
    bars[-1]["close"] = 20.0
    bars[-21]["close"] = 15.0
    ret = compute_ret20(bars)
    assert ret is not None
    assert abs(ret - 33.33) < 0.5


def test_compute_ret20_insufficient():
    bars = _make_bars(10, lambda i: 10.0, lambda i: 9.0, lambda i: 100)
    assert compute_ret20(bars) is None


# ============ is_anticorrection ============

def test_is_anticorrection_all_pass():
    """4 条件全满足 → 通过。"""
    bars = _good_stock_bars(70)
    # ret20 ≈ 33%，index_ret20 = -5% → rs ≈ 38%
    result = is_anticorrection(bars, index_ret20=-5.0, market_cap=200.0)
    assert result is not None
    assert result["ret20"] > 0
    assert result["rs_vs_idx"] >= OUTPERFORM_GAP
    assert result["vol_shrink"] < VOL_SHRINK_THRESHOLD
    assert MARKET_CAP_MIN <= result["market_cap"] <= MARKET_CAP_MAX


def test_is_anticorrection_broke_low():
    """条件1失败：近20日跌破近60日最低。"""
    bars = _good_stock_bars(70)
    # 在倒数第10条插入一个极低 low
    bars[-10]["low"] = 3.0  # 低于近60日最低(~8)
    result = is_anticorrection(bars, index_ret20=-5.0, market_cap=200.0)
    assert result is None


def test_is_anticorrection_not_outperforming():
    """条件2失败：20日跑赢大盘不足 5 个百分点。"""
    bars = _good_stock_bars(70)
    # stock ret20 ≈ 10%，设 index_ret20 = 42% → rs ≈ -32% < 5
    result = is_anticorrection(bars, index_ret20=42.0, market_cap=200.0)
    assert result is None


def test_is_anticorrection_ret20_too_high():
    """条件2b失败：20日涨幅超过 RET20_MAX(15%) → 已暴涨高位股，排除。"""
    bars = _good_stock_bars(70)  # ret20 ≈ 10%
    bars[-1]["close"] = bars[-21]["close"] * 1.20  # 抬高收盘 → ret20 = 20%
    result = is_anticorrection(bars, index_ret20=-5.0, market_cap=200.0)
    assert result is None


def test_is_anticorrection_not_shrinking():
    """条件3失败：近5日未缩量。"""
    n = 70
    bars = _good_stock_bars(n)
    # 把近5日 volume 改为 90（≥ 100×0.8=80）
    for i in range(n - 5, n):
        bars[i]["volume"] = 90.0
    result = is_anticorrection(bars, index_ret20=-5.0, market_cap=200.0)
    assert result is None


def test_is_anticorrection_cap_too_small():
    """条件4失败：市值 < 50 亿。"""
    bars = _good_stock_bars(70)
    result = is_anticorrection(bars, index_ret20=-5.0, market_cap=30.0)
    assert result is None


def test_is_anticorrection_cap_too_large():
    """条件4失败：市值 > 500 亿。"""
    bars = _good_stock_bars(70)
    result = is_anticorrection(bars, index_ret20=-5.0, market_cap=800.0)
    assert result is None


def test_is_anticorrection_cap_boundary():
    """边界：市值恰好 50 和 500 → 通过。"""
    bars = _good_stock_bars(70)
    assert is_anticorrection(bars, -5.0, 50.0) is not None
    assert is_anticorrection(bars, -5.0, 500.0) is not None


def test_is_anticorrection_insufficient_bars():
    """数据不足 60 条 → 不通过。"""
    bars = _good_stock_bars(55)
    result = is_anticorrection(bars, index_ret20=-5.0, market_cap=200.0)
    assert result is None


def test_is_anticorrection_volume_key_compat():
    """volume 键兼容：用 vol 也能正确判定。"""
    n = 70
    bars = _good_stock_bars(n)
    # 把 volume 键改成 vol
    for b in bars:
        b["vol"] = b.pop("volume")
    result = is_anticorrection(bars, index_ret20=-5.0, market_cap=200.0)
    assert result is not None
