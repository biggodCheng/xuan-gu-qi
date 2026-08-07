# -*- coding: utf-8 -*-
"""is_band_rebound 单测 — 波段超跌反弹判定(20日超跌+T日放量阳包阴,去长下影)。"""
from backtest.band_signal import is_band_rebound


def _bar(date, o, h, l, c, v):
    return {"date": date, "open": o, "high": h, "low": l, "close": c, "volume": v}


def _down_bars(n, start_close=100.0, end_close=75.0, base_vol=1000):
    """生成 n 根递减阴线(每根 open>close, 从 start_close 跌到 end_close)。"""
    bars = []
    step = (start_close - end_close) / (n - 1)
    for i in range(n):
        c = start_close - step * i
        bars.append(_bar(f"2024-01-{i+1:02d}", c + 0.5, c + 1, c - 1, c, base_vol))
    return bars


def _build(prev_close_t1, t_open, t_high, t_low, t_close, t_vol, n_prev=20, start_close=100.0):
    """前 n_prev 根跌到 prev_close_t1, 再加一根 T 日(给定 OHLCV)。"""
    bars = _down_bars(n_prev, start_close, prev_close_t1)
    bars.append(_bar("2024-01-21", t_open, t_high, t_low, t_close, t_vol))
    return bars


def test_pass_basic():
    # 20日 100→70(-30%) + T日阳包阴放量
    bars = _build(prev_close_t1=70.0, t_open=70.3, t_high=71.5, t_low=69.0,
                  t_close=72.0, t_vol=2000)
    r = is_band_rebound(bars, drop_pct=20.0, vol_ratio=1.5)
    assert r is not None
    assert r["drop20"] <= -20
    assert r["stop_loss"] == 69.0           # T-1 最低
    assert r["vol_ratio"] == 2.0


def test_fail_no_oversold():
    # 20日 100→85, T日 close=87 → drop20=-13%, 不满足 -20%
    bars = _build(prev_close_t1=85.0, t_open=85.3, t_high=86.5, t_low=84,
                  t_close=87, t_vol=2000, start_close=100.0)
    assert is_band_rebound(bars, drop_pct=20.0, vol_ratio=1.5) is None


def test_fail_not_yangbaoyin():
    # T 日收阴(不阳包阴)
    bars = _build(prev_close_t1=70.0, t_open=72.0, t_high=72.5, t_low=69,
                  t_close=70.5, t_vol=2000)   # close70.5 < open72 → 阴线
    assert is_band_rebound(bars, drop_pct=20.0, vol_ratio=1.5) is None


def test_fail_no_volume():
    # T 日未放量(vol=1200 < 1500 阈值)
    bars = _build(prev_close_t1=70.0, t_open=70.3, t_high=71.5, t_low=69,
                  t_close=72, t_vol=1200)
    assert is_band_rebound(bars, drop_pct=20.0, vol_ratio=1.5) is None


def test_shrink_on_rejects_churning():
    # use_shrink=True: T-1 未缩量(vol[T-1]=1000=前4日均量)→ 应被拒
    bars = _build(prev_close_t1=70.0, t_open=70.3, t_high=71.5, t_low=69,
                  t_close=72, t_vol=2000)   # 所有 bar vol=1000, T-1 未缩量
    assert is_band_rebound(bars, drop_pct=20.0, vol_ratio=1.5, use_shrink=True) is None


def test_short_history_returns_none():
    bars = _down_bars(15, 100, 70)          # 只有 15 根 < 21
    assert is_band_rebound(bars, drop_pct=20.0, vol_ratio=1.5) is None


def test_t1_drop_avoids_rebound_offset():
    # T 日反弹使含T口径跌幅被抵消, 不含T口径露出真实超跌。
    # n_prev=21 → len=22(use_t1_drop 需 close[T-21]=bars[-22])。
    # 含T drop20=close[T]/close[T-20]=79/98.5=-19.8%; 不含T=close[T-1]/close[T-21]=70/100=-30%
    bars = _build(prev_close_t1=70.0, t_open=75.0, t_high=80.0, t_low=74,
                  t_close=79.0, t_vol=2000, n_prev=21)
    r_default = is_band_rebound(bars, drop_pct=25.0, vol_ratio=1.5)               # 含T: -19.8%
    r_t1 = is_band_rebound(bars, drop_pct=25.0, vol_ratio=1.5, use_t1_drop=True)  # 不含T: -30%
    assert r_default is None        # 含T口径 -19.8% 被反弹抵消, 不满足 -25%
    assert r_t1 is not None         # 不含T口径 -30% 满足
    assert r_t1["drop20"] <= -25
