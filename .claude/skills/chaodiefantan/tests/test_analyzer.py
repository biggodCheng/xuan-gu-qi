"""超跌反弹判定纯函数单测 — 构造数据测各条件边界。"""
from screener.analyzer import is_oversold_rebound


def _bar(open_, close, high, low, volume):
    return {"day": "x", "open": open_, "close": close, "high": high, "low": low, "volume": volume}


def _good_bars():
    """构造满足全部 5 条的超跌反弹 K 线（7 条）。

    前5日高位横盘 close=12.5, vol=100；T-1 长下影缩量；T 放量阳包阴。
    drop5 = (10.5-12.5)/12.5 = -16%。
    """
    bars = []
    for _ in range(5):
        bars.append(_bar(12.5, 12.5, 13.0, 12.0, 100))
    bars.append(_bar(10.0, 9.0, 10.5, 7.0, 50))   # T-1: 下影2/实体1=2倍, 缩量50<80
    bars.append(_bar(9.2, 10.5, 11.0, 9.0, 100))  # T: 阳, 放量100>75, 收复10, 突破10.5
    return bars


def test_all_pass():
    r = is_oversold_rebound(_good_bars(), 200.0)
    assert r is not None
    assert r["drop5"] == -16.0
    assert r["stop_loss"] == 7.0


def test_drop5_not_enough():
    bars = _good_bars()
    for b in bars[:5]:
        b["close"] = 11.5  # (10.5-11.5)/11.5 = -8.7% > -15
    assert is_oversold_rebound(bars, 200.0) is None


def test_no_long_shadow():
    bars = _good_bars()
    bars[-2]["low"] = 8.9  # 下影=min(10,9)-8.9=0.1 < 2*实体(1)
    assert is_oversold_rebound(bars, 200.0) is None


def test_not_shrinking():
    bars = _good_bars()
    bars[-2]["volume"] = 90  # 90 >= 80 未缩量
    assert is_oversold_rebound(bars, 200.0) is None


def test_not_yang_line():
    bars = _good_bars()
    bars[-1]["open"], bars[-1]["close"] = 10.5, 9.2  # 阴线
    assert is_oversold_rebound(bars, 200.0) is None


def test_not_volume_up():
    bars = _good_bars()
    bars[-1]["volume"] = 60  # 60 < 75 未放量
    assert is_oversold_rebound(bars, 200.0) is None


def test_not_recover_open():
    bars = _good_bars()
    bars[-1]["close"] = 9.5  # 9.5 < T-1.open=10 未收复前日开盘
    assert is_oversold_rebound(bars, 200.0) is None


def test_cap_too_small():
    assert is_oversold_rebound(_good_bars(), 30.0) is None


def test_cap_too_large():
    assert is_oversold_rebound(_good_bars(), 800.0) is None


def test_insufficient_bars():
    assert is_oversold_rebound(_good_bars()[:6], 200.0) is None
