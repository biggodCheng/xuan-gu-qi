"""抗跌反弹跟踪纯函数单测。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from screener.track_analyzer import align_after


def _bars(closes, key="day"):
    """构造 K 线序列（按日期正序），close 序列 → bars。key=day(个股)/date(指数)。"""
    return [{
        key: f"2026-07-{10 + i:02d}",
        "open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 100.0,
    } for i, c in enumerate(closes)]


def test_align_after_found():
    bars = _bars([100.0, 101.0, 99.0])
    after, d_close = align_after(bars, "2026-07-10")
    assert d_close == 100.0
    assert len(after) == 2
    assert after[0]["close"] == 101.0


def test_align_after_index_uses_date_key():
    bars = _bars([200.0, 198.0], key="date")
    after, d_close = align_after(bars, "2026-07-10")
    assert d_close == 200.0
    assert len(after) == 1


def test_align_after_not_found():
    bars = _bars([100.0, 101.0])
    assert align_after(bars, "2025-01-01") is None


def test_align_after_d_is_last():
    bars = _bars([100.0, 101.0])
    after, d_close = align_after(bars, "2026-07-11")
    assert d_close == 101.0
    assert after == []


from screener.track_analyzer import window_return


def test_window_return_normal():
    after = _bars([101.0, 102.0, 103.0, 104.0, 105.0])
    assert window_return(after, 100.0, 5) == 5.0


def test_window_return_insufficient():
    after = _bars([101.0, 102.0])
    assert window_return(after, 100.0, 5) is None


def test_window_return_negative():
    after = _bars([98.0, 97.0, 96.0])
    assert window_return(after, 100.0, 3) == -4.0


def test_window_return_zero_base():
    after = _bars([101.0])
    assert window_return(after, 0.0, 1) is None
