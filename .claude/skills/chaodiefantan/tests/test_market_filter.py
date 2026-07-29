"""大盘环境开关(is_market_crash)纯函数单测。"""
from screener.market_filter import is_market_crash, _index_crash, INDICES


def _bars(closes, vols):
    return [{"date": f"d{i}", "close": c, "volume": v}
            for i, (c, v) in enumerate(zip(closes, vols))]


def _falling(n=21, start=100, end=80, vstart=100, vend=50):
    """下跌+缩量序列(n根):close 线性跌, vol 线性缩 → 空头排列+跌破MA20+缩量。"""
    closes = [start - (start - end) * i / (n - 1) for i in range(n)]
    vols = [vstart - (vstart - vend) * i / (n - 1) for i in range(n)]
    return _bars(closes, vols)


def _rising(n=21):
    """上涨序列:close 80→100 → 多头排列。"""
    closes = [80 + 20 * i / (n - 1) for i in range(n)]
    return _bars(closes, [100] * n)


def test_index_crash_on_falling_shrinking():
    assert _index_crash(_falling()) is True


def test_index_not_crash_when_rising():
    assert _index_crash(_rising()) is False


def test_index_not_crash_when_volume_expanding():
    """空头排列但放量(有承接)→不算缩量阴跌。"""
    assert _index_crash(_falling(vstart=50, vend=100)) is False


def test_index_not_crash_insufficient_history():
    assert _index_crash(_falling(n=15)) is False  # < MA_LONG+1=21


def test_market_crash_all_three_sync():
    klines = {sym: _falling() for sym, _ in INDICES}
    assert is_market_crash(klines) is True


def test_market_crash_one_strong_invalidates():
    """任一指数走强(多头)→整体不判crash。"""
    klines = {sym: _falling() for sym, _ in INDICES}
    klines["sh000300"] = _rising()
    assert is_market_crash(klines) is False


def test_market_crash_missing_index_not_crash():
    """缺任一指数数据 → 不轻易判crash(返回False)。"""
    klines = {"sh000001": _falling(), "sz399006": _falling()}  # 缺沪深300
    assert is_market_crash(klines) is False
